from datetime import datetime

import httpx

from .base import Bookmaker
from .constants import (
    MARKET_1X2, MARKET_MONEYLINE, MARKET_BTTS, MARKET_DOUBLE_CHANCE,
    HOME, DRAW, AWAY,
    YES, NO,
    HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY,
    LIGA_MX, PREMIER_LEAGUE, LA_LIGA, SERIE_A, BUNSEDLIGA, MLS, CHAMPIONS_LEAGUE, LIGUE_1, ARGENTINA_1, EREDIVISIE, BRASIL_A, NFL, MLB, NBA
)
from models import Event, Market, Outcome
    
BASE_URL = "https://polymarket.com/api/sports"

LEAGUE_CONFIGS: dict[str, dict] = {
    LIGA_MX: {"series_id": 10290, "sport_slug": "mex"},
    PREMIER_LEAGUE: {"series_id": 10188, "sport_slug": "epl"},
    LA_LIGA: {"series_id": 10193, "sport_slug": "laliga"},
    SERIE_A: {"series_id": 10203, "sport_slug": "sea"},
    BUNSEDLIGA: {"series_id": 10194, "sport_slug": "bundesliga"},
    MLS: {"series_id": 10189, "sport_slug": "mls"},
    CHAMPIONS_LEAGUE: {"series_id": 10204, "sport_slug": "ucl"},
    LIGUE_1: {"series_id": 10195, "sport_slug": "ligue-1"},
    ARGENTINA_1: {"series_id": 10312, "sport_slug": "arg"},
    EREDIVISIE: {"series_id": 10286, "sport_slug": "ere"},
    BRASIL_A: {"series_id": 10359, "sport_slug": "bra"},
    NFL: {"series_id": 12185, "sport_slug": "nfl"},
    MLB: {"series_id": 3, "sport_slug": "mlb"},
    NBA: {"series_id": 10345, "sport_slug": "nba"},
}

class Polymarket(Bookmaker):

    BOOKMAKER_NAME = "polymarket"
    SUPPORTED_LEAGUES = frozenset(LEAGUE_CONFIGS)

    def __init__(self):
        self.client = httpx.Client(
            base_url=BASE_URL,
            timeout=20,
        )

    def get_events(self, sport: str, league: str) -> list[Event]:
        config = LEAGUE_CONFIGS[league]
        data = self._fetch_league_events(
            series_id=config["series_id"],
            sport_slug=config["sport_slug"],
        )
        return self._parse_events(data, sport, league)

    def _fetch_league_events(self, series_id: int, sport_slug: str) -> dict:
        params = {
            "seriesId": series_id,
            "sportSlug": sport_slug,
            "currentSlug": "",
            "locale": "en",
        }
        response = self.client.get("/league-events", params=params)
        response.raise_for_status()
        data = response.json()

        # Retry with the current season week if no open events came back
        if not data.get("sections", {}).get("expanded"):
            week = data.get("summary", {}).get("earliest_open_week")
            if week:
                response = self.client.get(
                    "/league-events", params={**params, "week": week}
                )
                response.raise_for_status()
                data = response.json()

        return data

    def _parse_events(self, data: dict, sport: str, league: str) -> list[Event]:
        events = []
        teams_by_slug = data.get("teams", {})

        # Only process events listed in the "expanded" (upcoming) section
        open_slugs: set[str] = set()
        for date_section in data.get("sections", {}).get("expanded", {}).values():
            open_slugs.update(date_section.get("events", []))

        for event_slug, raw_event in data.get("events", {}).items():
            if event_slug not in open_slugs:
                continue

            team_info = teams_by_slug.get(event_slug, {})
            home_team, away_team = self._extract_teams(team_info)
            if not home_team or not away_team:
                continue

            markets_by_type: dict[str, list[dict]] = {}
            for m in raw_event.get("markets", []):
                t = m.get("sportsMarketType")
                if not t:
                    continue
                if not (m.get("liquidityNum") or 0):
                    continue
                markets_by_type.setdefault(t, []).append(m)

            event_markets: list[Market] = []

            m_1x2 = self._parse_1x2(markets_by_type.get("moneyline", []))
            if m_1x2:
                event_markets.append(m_1x2)
                # Only derive double-chance for 3-way (soccer) markets
                if m_1x2.type == MARKET_1X2:
                    dc = self._derive_double_chance(markets_by_type.get("moneyline", []))
                    if dc:
                        event_markets.append(dc)
            else:
                # 2-way NFL moneyline (no negRisk, prices are indexed by team dict key order)
                m_ml = self._parse_nfl_moneyline(markets_by_type.get("moneyline", []), team_info)
                if m_ml:
                    event_markets.append(m_ml)

            for m in markets_by_type.get("both_teams_to_score", []):
                parsed = self._parse_btts(m)
                if parsed:
                    event_markets.append(parsed)
                    break  # one BTTS market per event

            # totals and spreads are excluded: the API exposes them as paired AMM contracts
            # (outcomePrices sum to 1.0), while the website displays independent negRisk
            # binary prices — comparing them produces false arbitrage signals.

            if not event_markets:
                continue

            sport_slug = LEAGUE_CONFIGS[league]["sport_slug"]
            events.append(Event(
                bookmaker=self.BOOKMAKER_NAME,
                bookmaker_event_id=f"{sport_slug}/{event_slug}",
                sport=sport,
                league=league,
                home_team=home_team,
                away_team=away_team,
                start_time=datetime.fromisoformat(
                    raw_event["startTime"].replace("Z", "+00:00")
                ),
                markets=event_markets,
            ))

        return events

    @staticmethod
    def _extract_teams(team_info: dict) -> tuple[str, str]:
        """Return (home_team, away_team) using hostStatus when available."""
        home_team = ""
        away_team = ""
        for side_key in ("home", "away"):
            team = team_info.get(side_key, {})
            name = team.get("name", "")
            # hostStatus is the reliable indicator; fall back to dict key name
            status = team.get("hostStatus") or side_key
            if status == "home":
                home_team = name
            elif status == "away":
                away_team = name
        return home_team, away_team

    def _parse_nfl_moneyline(self, moneyline_markets: list[dict], team_info: dict) -> Market | None:
        """Parse a 2-way NFL moneyline where outcomePrices are not split by negRiskSportsMarketType.

        outcomePrices[0] corresponds to team_info["home"] and [1] to team_info["away"].
        Use hostStatus to determine which is the actual home team.
        """
        ml = next(
            (m for m in moneyline_markets
             if m.get("sportsMarketType") == "moneyline"
             and m.get("negRiskSportsMarketType") is None
             and len(m.get("outcomePrices", [])) >= 2),
            None,
        )
        if not ml:
            return None

        p_dict_home = float(ml["outcomePrices"][0])  # price for team_info["home"] entry
        p_dict_away = float(ml["outcomePrices"][1])  # price for team_info["away"] entry

        home_key_status = team_info.get("home", {}).get("hostStatus", "home")
        if home_key_status == "home":
            p_home, p_away = p_dict_home, p_dict_away
        else:
            p_home, p_away = p_dict_away, p_dict_home

        if p_home <= 0 or p_away <= 0:
            return None

        odds = self._to_odds(p_home, p_away)
        if len(odds) < 2:
            return None

        return Market(
            type=MARKET_MONEYLINE,
            outcomes=[
                Outcome(name=HOME, odds=odds[0], raw_price=p_home),
                Outcome(name=AWAY, odds=odds[1], raw_price=p_away),
            ],
        )

    @staticmethod
    def _to_odds(*prices: float) -> list[float]:
        """Normalize probabilities to sum to 1, then return decimal odds."""
        total = sum(prices)
        if total <= 0:
            return []
        return [round(total / p, 4) if p > 0 else 0.0 for p in prices]

    def _parse_1x2(self, moneyline_markets: list[dict]) -> Market | None:
        # negRisk prices are independent binaries that can sum > 1 — normalize before converting
        prices: dict[str, float] = {}
        for m in moneyline_markets:
            t = m.get("negRiskSportsMarketType")
            op = m.get("outcomePrices", [])
            if t in ("home", "draw", "away") and op:
                prices[t] = float(op[0])

        has_draw = "draw" in prices
        if not all(k in prices for k in ("home", "away")):
            return None

        if has_draw:
            odds = self._to_odds(prices["home"], prices["draw"], prices["away"])
            if len(odds) < 3:
                return None
            return Market(
                type=MARKET_1X2,
                outcomes=[
                    Outcome(name=HOME, odds=odds[0], raw_price=prices["home"]),
                    Outcome(name=DRAW, odds=odds[1], raw_price=prices["draw"]),
                    Outcome(name=AWAY, odds=odds[2], raw_price=prices["away"]),
                ],
            )
        else:
            odds = self._to_odds(prices["home"], prices["away"])
            if len(odds) < 2:
                return None
            return Market(
                type=MARKET_MONEYLINE,
                outcomes=[
                    Outcome(name=HOME, odds=odds[0], raw_price=prices["home"]),
                    Outcome(name=AWAY, odds=odds[1], raw_price=prices["away"]),
                ],
            )

    def _derive_double_chance(self, moneyline_markets: list[dict]) -> Market | None:
        # Polymarket has no native double-chance type; derive from normalized 1x2 prices
        prices: dict[str, float] = {}
        for m in moneyline_markets:
            t = m.get("negRiskSportsMarketType")
            op = m.get("outcomePrices", [])
            if t in ("home", "draw", "away") and op:
                prices[t] = float(op[0])

        if not all(k in prices for k in ("home", "draw", "away")):
            return None

        total = prices["home"] + prices["draw"] + prices["away"]
        ph = prices["home"] / total
        pd = prices["draw"] / total
        pa = prices["away"] / total

        return Market(
            type=MARKET_DOUBLE_CHANCE,
            outcomes=[
                Outcome(name=HOME_OR_DRAW, odds=round(1 / (ph + pd), 4)),
                Outcome(name=HOME_OR_AWAY, odds=round(1 / (ph + pa), 4)),
                Outcome(name=DRAW_OR_AWAY, odds=round(1 / (pd + pa), 4)),
            ],
        )

    def _parse_btts(self, market: dict) -> Market | None:
        prices = market.get("outcomePrices", [])
        if len(prices) < 2:
            return None
        p_yes, p_no = float(prices[0]), float(prices[1])
        if p_yes <= 0 or p_no <= 0:
            return None
        odds = self._to_odds(p_yes, p_no)
        return Market(
            type=MARKET_BTTS,
            outcomes=[
                Outcome(name=YES, odds=odds[0], raw_price=p_yes),
                Outcome(name=NO, odds=odds[1], raw_price=p_no),
            ],
        )
