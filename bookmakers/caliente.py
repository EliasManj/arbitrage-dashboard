
from .base import Bookmaker
import re
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .constants import (
    MARKET_1X2, MARKET_TOTAL, MARKET_BTTS, MARKET_DOUBLE_CHANCE, MARKET_ASIAN_HANDICAP,
    HOME, DRAW, AWAY, OVER, UNDER, YES, NO, HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY,
)
from models import Event, Market, Outcome

log = logging.getLogger(__name__)

CALIENTE_URL = "https://sports.caliente.mx/es_MX/Apuestas-Futbol-Mexico"
LEAGUE_URL = "https://sports.caliente.mx/es_MX/Liga-MX"
MX_TZ = ZoneInfo("America/Mexico_City")

# (mkt_sort query param, generic market type constant)
# AHRF uses the same table-row structure as the main page, handled separately
_EXTRA_MARKETS = [
    ("DBLC", MARKET_DOUBLE_CHANCE),
    ("BTSC", MARKET_BTTS),
    ("HCTG", MARKET_TOTAL),
]


def _parse_ah_line(hcap_text: str) -> float:
    # "0 / -0.5" → -0.25 (quarter line midpoint); "-1" → -1.0
    parts = [p.strip() for p in hcap_text.split("/")]
    return sum(float(p) for p in parts) / len(parts)


class Caliente(Bookmaker):

    BOOKMAKER_NAME = "caliente"

    def get_events(self) -> list[Event]:
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
            Stealth().apply_stealth_sync(context)
            page = context.new_page()

            # Main page — handles Cloudflare; retry up to 3 times if the connection times out
            for attempt in range(3):
                try:
                    page.goto(CALIENTE_URL, wait_until="domcontentloaded", timeout=120_000)
                    break
                except Exception:
                    if attempt == 2:
                        raise
            if "cf_chl" in page.url or "momento" in page.title().lower() or "moment" in page.title().lower():
                page.wait_for_function(
                    "() => !document.title.toLowerCase().includes('moment')",
                    timeout=30_000,
                )
            page.wait_for_selector(
                ".coupon.coupon-horizontal.coupon-scoreboard.video-enabled .mkt",
                timeout=120_000,
            )
            events_by_id = {
                e.bookmaker_event_id: e
                for e in self._parse_liga_mx(page.content())
            }

            # Navigate to each extra market page and merge by event ID
            for mkt_sort, market_type in _EXTRA_MARKETS:
                page.goto(
                    f"{LEAGUE_URL}?mkt_sort={mkt_sort}",
                    wait_until="domcontentloaded",
                    timeout=120_000,
                )
                page.wait_for_selector("div.mkt.expander[data-mkt_id]", timeout=30_000)
                soup = BeautifulSoup(page.content(), "html.parser")
                for expander in soup.select("div.mkt.expander[data-mkt_id]"):
                    event_id = self._get_event_id(expander)
                    if not event_id or event_id not in events_by_id:
                        continue
                    events_by_id[event_id].markets.extend(
                        self._parse_expander(expander, market_type)
                    )

            # AHRF uses the same tr-based scoreboard layout as the main page
            page.goto(
                f"{LEAGUE_URL}?mkt_sort=AHRF",
                wait_until="domcontentloaded",
                timeout=120_000,
            )
            page.wait_for_selector(
                ".coupon.coupon-horizontal.coupon-scoreboard .mkt",
                timeout=30_000,
            )
            soup = BeautifulSoup(page.content(), "html.parser")
            for row in soup.select("tr.mkt.pager-item[data-mkt_id]"):
                ev_el = row.select_one(".ev[data-ev_id]")
                if not ev_el:
                    continue
                event_id = ev_el["data-ev_id"]
                if event_id not in events_by_id:
                    continue
                market = self._parse_asian_handicap_row(row)
                if market:
                    events_by_id[event_id].markets.append(market)

            browser.close()

        return list(events_by_id.values())

    def _get_event_id(self, expander) -> str | None:
        for cls in expander.get("class", []):
            if cls.startswith("ev-") and cls[3:].isdigit():
                return cls[3:]
        return None

    def _parse_expander(self, expander, market_type: str) -> list[Market]:
        if market_type == MARKET_DOUBLE_CHANCE:
            m = self._parse_double_chance(expander)
            return [m] if m else []
        if market_type == MARKET_BTTS:
            m = self._parse_btts(expander)
            return [m] if m else []
        if market_type == MARKET_TOTAL:
            return self._parse_total(expander)
        return []

    def _parse_double_chance(self, expander) -> Market | None:
        # Outcomes appear in DOM order: 1X, 12, X2
        buttons = expander.select("button[name='add-to-slip']")
        if len(buttons) != 3:
            return None
        outcomes = []
        for btn, name in zip(buttons, [HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY]):
            odds_el = btn.select_one(".price.dec")
            if not odds_el:
                return None
            outcomes.append(Outcome(name=name, odds=float(odds_el.text.strip())))
        return Market(type=MARKET_DOUBLE_CHANCE, outcomes=outcomes)

    def _parse_btts(self, expander) -> Market | None:
        result: dict[str, float] = {}
        for btn in expander.select("button[name='add-to-slip']"):
            name_el = btn.select_one(".seln-name")
            odds_el = btn.select_one(".price.dec")
            if not name_el or not odds_el:
                continue
            label = name_el.text.strip().lower()
            odds = float(odds_el.text.strip())
            if label in ("sí", "si"):
                result[YES] = odds
            elif label == "no":
                result[NO] = odds
        if not all(k in result for k in (YES, NO)):
            return None
        return Market(
            type=MARKET_BTTS,
            outcomes=[
                Outcome(name=YES, odds=result[YES]),
                Outcome(name=NO, odds=result[NO]),
            ],
        )

    def _parse_asian_handicap_row(self, row) -> Market | None:
        buttons = row.select("button[name='add-to-slip']")
        if len(buttons) < 2:
            return None
        home_btn, away_btn = buttons[0], buttons[1]
        hcap_el = home_btn.select_one(".seln-hcap")
        home_odds_el = home_btn.select_one(".price.dec")
        away_odds_el = away_btn.select_one(".price.dec")
        if not hcap_el or not home_odds_el or not away_odds_el:
            return None
        try:
            return Market(
                type=MARKET_ASIAN_HANDICAP,
                line=_parse_ah_line(hcap_el.text.strip()),
                outcomes=[
                    Outcome(name=HOME, odds=float(home_odds_el.text.strip())),
                    Outcome(name=AWAY, odds=float(away_odds_el.text.strip())),
                ],
            )
        except ValueError:
            return None

    def _parse_total(self, expander) -> list[Market]:
        markets = []
        for row in expander.select("table.HC tbody tr"):
            cells = row.select("td.seln")
            if len(cells) != 2:
                continue
            over_btn = cells[0].select_one("button[name='add-to-slip']")
            under_btn = cells[1].select_one("button[name='add-to-slip']")
            if not over_btn or not under_btn:
                continue
            hcap_el = over_btn.select_one(".seln-hcap")
            over_odds_el = over_btn.select_one(".price.dec")
            under_odds_el = under_btn.select_one(".price.dec")
            if not hcap_el or not over_odds_el or not under_odds_el:
                continue
            try:
                markets.append(Market(
                    type=MARKET_TOTAL,
                    line=float(hcap_el.text.strip()),
                    outcomes=[
                        Outcome(name=OVER, odds=float(over_odds_el.text.strip())),
                        Outcome(name=UNDER, odds=float(under_odds_el.text.strip())),
                    ],
                ))
            except ValueError:
                continue
        return markets

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

