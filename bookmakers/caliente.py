
from .base import Bookmaker
import re
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .constants import MARKET_1X2, HOME, DRAW, AWAY
from models import Event, Market, Outcome

log = logging.getLogger(__name__)

CALIENTE_URL = "https://sports.caliente.mx/es_MX/Apuestas-Futbol-Mexico"
MX_TZ = ZoneInfo("America/Mexico_City")


class Caliente(Bookmaker):

    BOOKMAKER_NAME = "caliente"

    def get_events(self) -> list[Event]:
        html = self._fetch_initial_page()
        return self._parse_liga_mx(html)

    def _fetch_initial_page(self) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )

            context = browser.new_context(
                locale="es-MX",
                timezone_id="America/Mexico_City",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            # Apply stealth to the context so all pages inherit it.
            Stealth().apply_stealth_sync(context)

            page = context.new_page()

            page.goto(
                CALIENTE_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            #log.debug("Navigated to: %s", page.url)
            #log.debug("Page title: %s", page.title())

            # Wait for Cloudflare managed challenge to complete and redirect.
            if "cf_chl" in page.url or "momento" in page.title().lower() or "moment" in page.title().lower():
                #log.debug("CF challenge detected — waiting for redirect...")
                page.wait_for_function(
                    "() => !document.title.toLowerCase().includes('moment')",
                    timeout=30_000,
                )
                #log.debug("CF challenge passed. New URL: %s", page.url)

            # Dump snapshot for inspection.
            page.screenshot(path="/tmp/caliente_debug.png", full_page=True)
            with open("/tmp/caliente_debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            #log.debug("Page title after challenge: %s", page.title())

            # Wait specifically for the Liga MX regular-match table.
            page.wait_for_selector(
                ".coupon.coupon-horizontal.coupon-scoreboard.video-enabled .mkt",
                timeout=60_000,
            )

            html = page.content()

            browser.close()

            return html

    def _parse_liga_mx(self, html: str) -> list[Event]:
        soup = BeautifulSoup(html, "html.parser")

        rows = soup.select(
            ".coupon.coupon-horizontal.coupon-scoreboard.video-enabled .mkt"
        )

        events = []

        for row in rows:
            event_el = row.select_one(".ev")

            event_id = event_el["data-ev_id"]
            market_id = row["data-mkt_id"]

            time = event_el.select_one(".time").get_text(strip=True)
            date = event_el.select_one(".date").get_text(strip=True)

            selections = []

            for button in row.select('button[name="add-to-slip"]'):
                match = re.search(r"\bseln-(\d+)", " ".join(button.get("class", [])))
                if not match:
                    continue

                selection_id = match.group(1)

                name_el = button.select_one(
                    ".seln-name, .seln-draw-label"
                )

                odds_el = button.select_one(".price.dec")

                selections.append({
                    "selection_id": selection_id,
                    "name": name_el.get_text(strip=True),
                    "odds": float(odds_el.get_text(strip=True)),
                })

            if len(selections) != 3:
                continue

            start_time = self._parse_start_time(date, time)

            events.append(
                Event(
                    bookmaker=self.BOOKMAKER_NAME,
                    bookmaker_event_id=event_id,
                    sport="football",
                    league="Liga MX",
                    home_team=selections[0]["name"],
                    away_team=selections[2]["name"],
                    start_time=start_time,
                    markets=[
                        Market(
                            type=MARKET_1X2,
                            outcomes=[
                                Outcome(
                                    name=HOME,
                                    odds=selections[0]["odds"],
                                    bookmaker_outcome_id=selections[0]["selection_id"],
                                ),
                                Outcome(
                                    name=DRAW,
                                    odds=selections[1]["odds"],
                                    bookmaker_outcome_id=selections[1]["selection_id"],
                                ),
                                Outcome(
                                    name=AWAY,
                                    odds=selections[2]["odds"],
                                    bookmaker_outcome_id=selections[2]["selection_id"],
                                ),
                            ],
                            bookmaker_market_id=market_id,
                        )
                    ],
                )
            )

        return events

    def _parse_start_time(self, date: str, time: str) -> datetime:
        # date is like '25 Sep', time is like '19:00' — both in Mexico City local time
        year = datetime.now(tz=MX_TZ).year
        local_dt = datetime.strptime(f"{date} {year} {time}", "%d %b %Y %H:%M").replace(
            tzinfo=MX_TZ
        )
        return local_dt.astimezone(timezone.utc)
