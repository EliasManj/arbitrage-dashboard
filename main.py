import os
import logging
from dotenv import load_dotenv

from bookmakers.playdoit import Playdoit
from bookmakers.caliente import Caliente
from bookmakers.teammexico import TeamMexico
from arbitrage.matching import match_events
from arbitrage.analysis import find_arbitrage

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")

if __name__ == "__main__":

    teammex = TeamMexico().get_events()
    playdoit = Playdoit().get_events()
    caliente = Caliente().get_events()

    all_events = teammex + playdoit + caliente

    # Deduplicate by bookmaker for each pair combination
    bookmaker_lists = [teammex, playdoit, caliente]

    for i, list_a in enumerate(bookmaker_lists):
        for list_b in bookmaker_lists[i + 1:]:
            for event_a, event_b in match_events(list_a, list_b):
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
    