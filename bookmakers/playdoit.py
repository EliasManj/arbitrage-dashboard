from datetime import datetime

import httpx

from .base import Bookmaker
from .constants import (
    MARKET_1X2,
    HOME, DRAW, AWAY,
)
from models import Event, Market, Outcome


BASE_URL = "https://sb2frontend-altenar2.biahosted.com/api/widget"

COMMON_PARAMS = {
    "culture": "es-ES",
    "timezoneOffset": 360,
    "integration": "playdoit2",
    "deviceType": 1,
    "numFormat": "en-GB",
    "countryCode": "MX",
}


class Playdoit(Bookmaker):

    BOOKMAKER_NAME = "playdoit"

    def __init__(self):
        self.client = httpx.Client(
            base_url=BASE_URL,
            timeout=10,
        )

    def get_events(self) -> list[Event]:
        data = self._get_overview(champ_id=10009)

        return self._parse_events(
            data=data,
            league="Liga MX",
        )

    def _get_overview(self, champ_id: int) -> dict:
        params = {
            **COMMON_PARAMS,
            "eventCount": 0,
            "sportId": 0,
            "champIds": champ_id,
            "withLive": "false",
        }

        response = self.client.get(
            "/GetOverview",
            params=params,
        )

        response.raise_for_status()

        return response.json()

    def _parse_events(
        self,
        data: dict,
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

            market = self._find_1x2_market(
                raw_event,
                markets_by_id,
            )

            if market is None:
                continue

            outcomes = self._parse_1x2_outcomes(
                market,
                odds_by_id,
            )

            if outcomes is None:
                continue

            home_team, away_team = self._extract_teams(
                raw_event["name"]
            )

            events.append(
                Event(
                    bookmaker=self.BOOKMAKER_NAME,
                    bookmaker_event_id=str(raw_event["id"]),
                    sport="football",
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    start_time=datetime.fromisoformat(
                        raw_event["startDate"].replace(
                            "Z",
                            "+00:00",
                        )
                    ),
                    markets=[
                        Market(
                            type=MARKET_1X2,
                            outcomes=outcomes,
                        )
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
            Outcome(
                name=HOME,
                odds=result[HOME],
            ),
            Outcome(
                name=DRAW,
                odds=result[DRAW],
            ),
            Outcome(
                name=AWAY,
                odds=result[AWAY],
            ),
        ]            

    def _extract_teams(
        self,
        event_name: str,
    ) -> tuple[str, str]:

        home, away = event_name.split(" vs. ", maxsplit=1)

        return home.strip(), away.strip()    