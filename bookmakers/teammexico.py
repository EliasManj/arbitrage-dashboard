import json
from datetime import datetime
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .base import Bookmaker
from .constants import (
    MARKET_1X2, MARKET_MONEYLINE, MARKET_TOTAL, MARKET_BTTS, MARKET_DOUBLE_CHANCE, MARKET_ASIAN_HANDICAP,
    HOME, DRAW, AWAY,
    OVER, UNDER,
    YES, NO,
    HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY,
    LIGA_MX, PREMIER_LEAGUE, LA_LIGA, SERIE_A, BUNSEDLIGA, MLS, CHAMPIONS_LEAGUE, LIGUE_1, ARGENTINA_1, EREDIVISIE, BRASIL_A, NFL, MLB, NBA
)
from models import Event, Market, Outcome


BASE_URL = "https://sb2frontend-altenar2.biahosted.com/api/widget"

COMMON_PARAMS = {
    "culture": "es-ES",
    "timezoneOffset": 360,
    "integration": "teammexicobets_dark",
    "deviceType": 1,
    "numFormat": "en-GB",
    "countryCode": "MX",
}


class TeamMexico(Bookmaker):

    BOOKMAKER_NAME = "teammexico"
    SUPPORTED_LEAGUES = frozenset({
        LIGA_MX, PREMIER_LEAGUE, LA_LIGA, SERIE_A, BUNSEDLIGA, MLS,
        CHAMPIONS_LEAGUE, LIGUE_1, ARGENTINA_1, EREDIVISIE, BRASIL_A, NFL, MLB, NBA,
    })

    LEAGUE_CHAMP_IDS: dict[str, int] = {
        LIGA_MX: 10009,
        PREMIER_LEAGUE: 2936,
        LA_LIGA: 2941,
        SERIE_A: 2942,
        BUNSEDLIGA: 2950,
        MLS: 4610,
        CHAMPIONS_LEAGUE: 16808,
        LIGUE_1: 2943,
        ARGENTINA_1: 3075,
        EREDIVISIE: 3065,
        BRASIL_A: 11318,
        NFL: 3281,
        MLB: 3286,
        NBA: 2980,
    }

    def get_events(self, sport: str, league: str) -> list[Event]:
        champ_id = self.LEAGUE_CHAMP_IDS[league]
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            Stealth().apply_stealth_sync(context)
            self._page = context.new_page()
            try:
                data = self._get_events(champ_id=champ_id)
                return self._parse_events(data=data, sport=sport, league=league)
            finally:
                self._page = None

    def _get_events(self, champ_id: int) -> dict:
        params = {
            **COMMON_PARAMS,
            "eventCount": 100,
            "sportId": 0,
            "champIds": champ_id,
        }
        url = f"{BASE_URL}/GetEvents?{urlencode(params)}"
        self._page.goto(url, wait_until="networkidle", timeout=60_000)
        self._page.wait_for_function(
            "() => { try { JSON.parse(document.body.innerText); return true; } catch(e) { return false; } }",
            timeout=30_000,
        )
        return json.loads(self._page.inner_text("body"))

    def _get_event_details(self, event_id: int) -> dict:
        params = {
            **COMMON_PARAMS,
            "eventId": event_id,
            "showNonBoosts": "false",
        }
        url = f"{BASE_URL}/GetEventDetails?{urlencode(params)}"
        return self._page.evaluate(
            "async (url) => { const r = await fetch(url); return r.json(); }",
            url,
        )

    def _parse_events(
        self,
        data: dict,
        sport: str,
        league: str,
    ) -> list[Event]:

        markets_by_id = {
            market["id"]: market
            for market in data["markets"]
        }

        odds_by_id = {
            odd["id"]: odd
            for odd in data["odds"]
        }

        events = []

        for raw_event in data["events"]:

            market = self._find_1x2_market(raw_event, markets_by_id)
            if market is not None:
                outcomes = self._parse_1x2_outcomes(market, odds_by_id)
                primary_market_type = MARKET_1X2
            else:
                market = self._find_moneyline_market(raw_event, markets_by_id)
                if market is None:
                    continue
                outcomes = self._parse_moneyline_outcomes(market, odds_by_id)
                primary_market_type = MARKET_MONEYLINE

            if outcomes is None:
                continue

            home_team, away_team = self._extract_teams(
                raw_event["name"]
            )

            details = self._get_event_details(raw_event["id"])
            extra_markets = self._parse_extra_markets(details)

            events.append(
                Event(
                    bookmaker=self.BOOKMAKER_NAME,
                    bookmaker_event_id=str(raw_event["id"]),
                    sport=sport,
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    start_time=datetime.fromisoformat(
                        raw_event["startDate"].replace("Z", "+00:00")
                    ),
                    markets=[
                        Market(
                            type=primary_market_type,
                            outcomes=outcomes,
                        ),
                        *extra_markets,
                    ],
                )
            )

        return events

    def _find_1x2_market(
        self,
        event: dict,
        markets_by_id: dict,
    ) -> dict | None:

        for market_id in event["marketIds"]:
            market = markets_by_id.get(market_id)

            if market is None:
                continue

            if market["typeId"] == 1:
                return market

        return None

    def _find_moneyline_market(
        self,
        event: dict,
        markets_by_id: dict,
    ) -> dict | None:
        """2-way winner market used by American football (typeId=219) and baseball (typeId=251)."""
        for market_id in event["marketIds"]:
            market = markets_by_id.get(market_id)
            if market is not None and market["typeId"] in (219, 251):
                return market
        return None

    def _parse_1x2_outcomes(
        self,
        market: dict,
        odds_by_id: dict,
    ) -> list[Outcome] | None:

        result = {}

        for odd_id in market["oddIds"]:
            odd = odds_by_id[odd_id]

            if odd.get("oddStatus") != 0:
                continue

            match odd["typeId"]:
                case 1:
                    result[HOME] = odd["price"]

                case 2:
                    result[DRAW] = odd["price"]

                case 3:
                    result[AWAY] = odd["price"]

        if not all(
            key in result
            for key in (HOME, DRAW, AWAY)
        ):
            return None

        return [
            Outcome(name=HOME, odds=result[HOME]),
            Outcome(name=DRAW, odds=result[DRAW]),
            Outcome(name=AWAY, odds=result[AWAY]),
        ]

    def _parse_moneyline_outcomes(
        self,
        market: dict,
        odds_by_id: dict,
    ) -> list[Outcome] | None:
        """Parse a 2-way moneyline (home / away, no draw)."""
        result = {}

        for odd_id in market["oddIds"]:
            odd = odds_by_id[odd_id]

            if odd.get("oddStatus") != 0:
                continue

            match odd["typeId"]:
                case 1:
                    result[HOME] = odd["price"]
                case 3:
                    result[AWAY] = odd["price"]

        if not all(key in result for key in (HOME, AWAY)):
            return None

        return [
            Outcome(name=HOME, odds=result[HOME]),
            Outcome(name=AWAY, odds=result[AWAY]),
        ]

    def _parse_extra_markets(self, details: dict) -> list[Market]:
        odds_by_id = {o["id"]: o for o in details.get("odds", [])}
        markets = []
        seen_type_ids: set[int] = set()

        for m in details.get("markets", []):
            tid = m.get("typeId")
            if tid in seen_type_ids:
                continue
            seen_type_ids.add(tid)

            if tid == 18:
                markets.extend(self._parse_total_markets(m, odds_by_id))
            elif tid == 29:
                market = self._parse_btts_market(m, odds_by_id)
                if market:
                    markets.append(market)
            elif tid == 10:
                market = self._parse_double_chance_market(m, odds_by_id)
                if market:
                    markets.append(market)
            elif tid == 16:
                markets.extend(self._parse_asian_handicap_markets(m, odds_by_id))

        return markets

    def _parse_total_markets(
        self,
        market: dict,
        odds_by_id: dict,
    ) -> list[Market]:
        by_line: dict[float, dict[str, float]] = {}

        all_odd_ids = [oid for row in market.get("desktopOddIds", []) for oid in row]
        for oid in all_odd_ids:
            odd = odds_by_id.get(oid)
            if odd is None or odd.get("oddStatus") != 0 or odd.get("sv") is None:
                continue
            line = float(odd["sv"])
            by_line.setdefault(line, {})
            match odd["typeId"]:
                case 12:
                    by_line[line][OVER] = odd["price"]
                case 13:
                    by_line[line][UNDER] = odd["price"]

        return [
            Market(
                type=MARKET_TOTAL,
                line=line,
                outcomes=[
                    Outcome(name=OVER, odds=outcomes[OVER]),
                    Outcome(name=UNDER, odds=outcomes[UNDER]),
                ],
            )
            for line, outcomes in by_line.items()
            if OVER in outcomes and UNDER in outcomes
        ]

    def _parse_btts_market(
        self,
        market: dict,
        odds_by_id: dict,
    ) -> Market | None:
        result: dict[str, float] = {}

        all_odd_ids = [oid for row in market.get("desktopOddIds", []) for oid in row]
        for oid in all_odd_ids:
            odd = odds_by_id.get(oid)
            if odd is None or odd.get("oddStatus") != 0:
                continue
            match odd["typeId"]:
                case 74:
                    result[YES] = odd["price"]
                case 76:
                    result[NO] = odd["price"]

        if not all(k in result for k in (YES, NO)):
            return None

        return Market(
            type=MARKET_BTTS,
            outcomes=[
                Outcome(name=YES, odds=result[YES]),
                Outcome(name=NO, odds=result[NO]),
            ],
        )

    def _parse_double_chance_market(
        self,
        market: dict,
        odds_by_id: dict,
    ) -> Market | None:
        result: dict[str, float] = {}

        all_odd_ids = [oid for row in market.get("desktopOddIds", []) for oid in row]
        for oid in all_odd_ids:
            odd = odds_by_id.get(oid)
            if odd is None or odd.get("oddStatus") != 0:
                continue
            match odd["typeId"]:
                case 9:
                    result[HOME_OR_DRAW] = odd["price"]
                case 10:
                    result[HOME_OR_AWAY] = odd["price"]
                case 11:
                    result[DRAW_OR_AWAY] = odd["price"]

        if not all(k in result for k in (HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY)):
            return None

        return Market(
            type=MARKET_DOUBLE_CHANCE,
            outcomes=[
                Outcome(name=HOME_OR_DRAW, odds=result[HOME_OR_DRAW]),
                Outcome(name=HOME_OR_AWAY, odds=result[HOME_OR_AWAY]),
                Outcome(name=DRAW_OR_AWAY, odds=result[DRAW_OR_AWAY]),
            ],
        )

    def _parse_asian_handicap_markets(
        self,
        market: dict,
        odds_by_id: dict,
    ) -> list[Market]:
        rows = market.get("desktopOddIds", [])
        if len(rows) < 2:
            return []

        markets = []
        for home_oid, away_oid in zip(rows[0], rows[1]):
            home_odd = odds_by_id.get(home_oid)
            away_odd = odds_by_id.get(away_oid)

            if (
                home_odd is None or away_odd is None
                or home_odd.get("oddStatus") != 0
                or away_odd.get("oddStatus") != 0
                or home_odd.get("sv") is None
            ):
                continue

            markets.append(
                Market(
                    type=MARKET_ASIAN_HANDICAP,
                    line=float(home_odd["sv"]),
                    outcomes=[
                        Outcome(name=HOME, odds=home_odd["price"]),
                        Outcome(name=AWAY, odds=away_odd["price"]),
                    ],
                )
            )

        return markets

    def _extract_teams(
        self,
        event_name: str,
    ) -> tuple[str, str]:

        home, away = event_name.split(" vs. ", maxsplit=1)

        return home.strip(), away.strip()


