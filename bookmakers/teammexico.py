import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, Page

from bookmakers.base import Bookmaker
from bookmakers.constants import MARKET_1X2, HOME, DRAW, AWAY
from models import Event, Market, Outcome

logger = logging.getLogger(__name__)

MX_TZ = ZoneInfo("America/Mexico_City")


class TeamMexico(Bookmaker):

    BOOKMAKER_NAME = "teammexico"

    URL = (
        "https://www.teammexico.mx/"
        "sports#page=championship&championshipIds=10009"
    )

    EVENT_SELECTOR = '[class*="EventBoxRoot-sc-"]'
    ODDS_READY_SELECTOR = '[class*="OddValue-sc-"]'

    def get_events(self) -> list[Event]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            context = browser.new_context(
                locale="es-MX",
                timezone_id="America/Mexico_City",
            )

            page = context.new_page()

            page.goto(self.URL, wait_until="domcontentloaded", timeout=60_000)

            #logger.debug("Navigated to: %s", page.url)
            #logger.debug("Page title: %s", page.title())

            page.wait_for_selector(self.EVENT_SELECTOR, timeout=60_000)
            #logger.debug("Event boxes visible")
            # Odds are fetched asynchronously after event boxes appear
            page.wait_for_selector(self.ODDS_READY_SELECTOR, timeout=30_000)
            #logger.debug("Odds visible")
            page.wait_for_load_state("networkidle", timeout=30_000)
            #logger.debug("Network idle")

            events = self._extract_events(page)

            browser.close()

        return events

    def _extract_events(self, page: Page) -> list[Event]:
        # page.locator pierces shadow DOM; page.content() does not
        event_locators = page.locator(self.EVENT_SELECTOR).all()
        #logger.debug("TeamMexico: found %d live event elements", len(event_locators))

        events = []

        for el in event_locators:
            try:
                event = self._parse_event_locator(el)
                if event:
                    events.append(event)
                else:
                    #logger.debug("TeamMexico: _parse_event_locator returned None")
            except Exception:
                logger.exception("Failed to parse TeamMexico event")

        return events

    def _parse_event_locator(self, el) -> Event | None:
        competitors = el.locator('[class*="CompetitorName-sc-"]').all()

        if len(competitors) != 2:
            #logger.debug("TeamMexico: expected 2 competitors, got %d", len(competitors))
            return None

        home_team = competitors[0].text_content(timeout=5_000).strip()
        away_team = competitors[1].text_content(timeout=5_000).strip()
        #logger.debug("TeamMexico: parsing %s vs %s", home_team, away_team)

        datetime_el = el.locator('[class*="DateTime-sc-"]').first
        if not datetime_el.count():
            #logger.debug("TeamMexico: no datetime element for %s vs %s", home_team, away_team)
            return None

        start_time = self._parse_start_time(datetime_el.text_content(timeout=5_000).strip())

        # First MarketContainer is 1x2 (header labels: 1 | empate | 2)
        market_containers = el.locator('[class*="MarketContainer-sc-"]').all()

        if not market_containers:
            #logger.debug("TeamMexico: no market containers for %s vs %s", home_team, away_team)
            return None

        odd_elements = market_containers[0].locator('[class*="OddValue-sc-"]').all()

        if len(odd_elements) != 3:
            #logger.debug(
                "TeamMexico: expected 3 odds for %s vs %s, got %d",
                home_team, away_team, len(odd_elements),
            )
            return None

        odds = [
            self._american_to_decimal(o.text_content(timeout=5_000).strip())
            for o in odd_elements
        ]

        return Event(
            bookmaker=self.BOOKMAKER_NAME,
            bookmaker_event_id=None,
            sport="football",
            league="Liga MX",
            home_team=home_team,
            away_team=away_team,
            start_time=start_time,
            markets=[
                Market(
                    type=MARKET_1X2,
                    outcomes=[
                        Outcome(name=HOME, odds=odds[0]),
                        Outcome(name=DRAW, odds=odds[1]),
                        Outcome(name=AWAY, odds=odds[2]),
                    ],
                )
            ],
        )

    def _parse_start_time(self, value: str) -> datetime:
        # Format: "25/09 • 19:00" — Mexico City local time
        parts = value.split("•")
        if len(parts) != 2:
            raise ValueError(f"Unexpected TeamMexico datetime: {value!r}")
        date_part = parts[0].strip()  # "25/09"
        time_part = parts[1].strip()  # "19:00"
        year = datetime.now(tz=MX_TZ).year
        local_dt = datetime.strptime(
            f"{date_part}/{year} {time_part}", "%d/%m/%Y %H:%M"
        ).replace(tzinfo=MX_TZ)
        return local_dt.astimezone(timezone.utc)

    @staticmethod
    def _american_to_decimal(value: str) -> float:
        american = int(value)
        if american > 0:
            return round(1 + american / 100, 4)
        return round(1 + 100 / abs(american), 4)

