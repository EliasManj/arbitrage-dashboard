import os
import logging
from dotenv import load_dotenv

from bookmakers.playdoit import Playdoit
from bookmakers.caliente import Caliente
from arbitrage.matching import match_events
from arbitrage.analysis import find_arbitrage

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")

if __name__ == "__main__":

    playdoit = Playdoit().get_events()
    caliente = Caliente().get_events()

    for event_a, event_b in match_events(playdoit, caliente):
        result = find_arbitrage(event_a, event_b)
        if result is None:
            continue
        print(
            f"{result.event_a.home_team} vs {result.event_a.away_team}"
            f"  |  arbitrage={result.is_arbitrage}"
            f"  |  margin={result.profit_margin:.2f}%"
        )
        print(f"  home: {result.best_home.bookmaker} @ {result.best_home.odds}")
        print(f"  draw: {result.best_draw.bookmaker} @ {result.best_draw.odds}")
        print(f"  away: {result.best_away.bookmaker} @ {result.best_away.odds}")
        print()
    