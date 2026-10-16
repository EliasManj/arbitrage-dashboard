from datetime import datetime

import httpx

from .base import Bookmaker
from .constants import (
    MARKET_1X2, MARKET_TOTAL, MARKET_BTTS, MARKET_DOUBLE_CHANCE, MARKET_ASIAN_HANDICAP,
    HOME, DRAW, AWAY,
    OVER, UNDER,
    YES, NO,
    HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY,
    LIGA_MX, PREMIER_LEAGUE, LA_LIGA, SERIE_A, BUNSEDLIGA, MLS, CHAMPIONS_LEAGUE, LIGUE_1, ARGENTINA_1, EREDIVISIE, BRASIL_A
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
}

class Polymarket(Bookmaker):

    BOOKMAKER_NAME = "polymarket"

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
        return self._parse_events(data, league)

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

    def _parse_events(self, data: dict, league: str) -> list[Event]:
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
            home_team = team_info.get("home", {}).get("name", "")
            away_team = team_info.get("away", {}).get("name", "")
            if not home_team or not away_team:
                continue

            markets_by_type: dict[str, list[dict]] = {}
            for m in raw_event.get("markets", []):
                t = m.get("sportsMarketType")
                if t:
                    markets_by_type.setdefault(t, []).append(m)

            event_markets: list[Market] = []

            m_1x2 = self._parse_1x2(markets_by_type.get("moneyline", []))
            if m_1x2:
                event_markets.append(m_1x2)
                dc = self._derive_double_chance(markets_by_type.get("moneyline", []))
                if dc:
                    event_markets.append(dc)

            for m in markets_by_type.get("both_teams_to_score", []):
                parsed = self._parse_btts(m)
                if parsed:
                    event_markets.append(parsed)
                    break  # one BTTS market per event

            for m in markets_by_type.get("totals", []):
                parsed = self._parse_total(m)
                if parsed:
                    event_markets.append(parsed)

            event_markets.extend(
                self._parse_spreads(markets_by_type.get("spreads", []), home_team)
            )

            if not event_markets:
                continue

            events.append(Event(
                bookmaker=self.BOOKMAKER_NAME,
                bookmaker_event_id=str(raw_event["id"]),
                sport="football",
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

        if not all(k in prices for k in ("home", "draw", "away")):
            return None

        odds = self._to_odds(prices["home"], prices["draw"], prices["away"])
        if len(odds) < 3:
            return None

        return Market(
            type=MARKET_1X2,
            outcomes=[
                Outcome(name=HOME, odds=odds[0]),
                Outcome(name=DRAW, odds=odds[1]),
                Outcome(name=AWAY, odds=odds[2]),
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
                Outcome(name=YES, odds=odds[0]),
                Outcome(name=NO, odds=odds[1]),
            ],
        )

    # Minimum plausible over-probability for match goals totals at each line.
    # Player props (e.g. "player scores over 0.5") have ~40-60% over probability,
    # which is far below what match-goal totals produce at the same line.
    _MIN_OVER_RATIO: dict[float, float] = {
        0.5: 0.75,   # over 0.5 match goals: ~88-95 % expected
        1.5: 0.55,   # over 1.5 match goals: ~65-85 % expected
        2.5: 0.35,   # over 2.5 match goals: ~45-70 % expected
    }

    def _parse_total(self, market: dict) -> Market | None:
        line = market.get("line")
        prices = market.get("outcomePrices", [])
        if line is None or len(prices) < 2:
            return None
        p_over, p_under = float(prices[0]), float(prices[1])
        if p_over <= 0 or p_under <= 0:
            return None
        total = p_over + p_under
        min_ratio = self._MIN_OVER_RATIO.get(float(line))
        if min_ratio is not None and p_over / total < min_ratio:
            return None  # likely a player prop, not a match-goals total
        odds = self._to_odds(p_over, p_under)
        return Market(
            type=MARKET_TOTAL,
            line=float(line),
            outcomes=[
                Outcome(name=OVER, odds=odds[0]),
                Outcome(name=UNDER, odds=odds[1]),
            ],
        )

    def _parse_spreads(
        self,
        spread_markets: list[dict],
        home_team_name: str,
    ) -> list[Market]:
        # outcomes[0] = team carrying the handicap; line = that team's handicap value
        seen_lines: set[float] = set()
        markets: list[Market] = []

        for m in spread_markets:
            line = m.get("line")
            outcomes = m.get("outcomes", [])
            prices = m.get("outcomePrices", [])

            if line is None or len(outcomes) < 2 or len(prices) < 2:
                continue

            p0, p1 = float(prices[0]), float(prices[1])
            if p0 <= 0 or p1 <= 0:
                continue

            if outcomes[0] == home_team_name:
                home_line = float(line)
                home_price, away_price = p0, p1
            else:
                # Away team carries the handicap; invert to home's perspective
                home_line = -float(line)
                home_price, away_price = p1, p0

            if home_line in seen_lines:
                continue
            seen_lines.add(home_line)

            odds = self._to_odds(home_price, away_price)
            markets.append(Market(
                type=MARKET_ASIAN_HANDICAP,
                line=home_line,
                outcomes=[
                    Outcome(name=HOME, odds=odds[0]),
                    Outcome(name=AWAY, odds=odds[1]),
                ],
            ))

        return markets
