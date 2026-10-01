import argparse
import logging
from dotenv import load_dotenv

from bookmakers.playdoit import Playdoit
from bookmakers.caliente import Caliente
from bookmakers.teammexico import TeamMexico
from arbitrage.matching import group_events
from arbitrage.analysis import find_arbitrage_1x2

load_dotenv()

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

logging.basicConfig(
    level=logging.DEBUG if args.debug else logging.WARNING,
    format="%(name)s %(levelname)s %(message)s",
)

if __name__ == "__main__":

    teammex = TeamMexico().get_events()
    playdoit = Playdoit().get_events()
    caliente = Caliente().get_events()

    all_events = teammex + playdoit + caliente

    for group in group_events(all_events):
        result = find_arbitrage_1x2(group)
        if result is None:
            continue
        print(
                f"{result.events[0].home_team} vs {result.events[0].away_team}"
                f"  |  arbitrage={result.is_arbitrage}"
                f"  |  margin={result.profit_margin:.2f}%"
            )
        print(f"  home: {result.best_home.bookmaker} @ {result.best_home.odds}")
        print(f"  draw: {result.best_draw.bookmaker} @ {result.best_draw.odds}")
        print(f"  away: {result.best_away.bookmaker} @ {result.best_away.odds}")
        print()
    