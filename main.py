import argparse
import logging
from dotenv import load_dotenv

from bookmakers.playdoit import Playdoit
from bookmakers.caliente import Caliente
from bookmakers.teammexico import TeamMexico
from bookmakers.polymarket import Polymarket
from arbitrage.matching import group_events
from arbitrage.analysis import (
    find_arbitrage_1x2,
    find_arbitrage_btts,
    find_arbitrage_double_chance,
    find_arbitrage_total_goals,
    find_arbitrage_asian_handicap,
)
from models import MarketArbitrageResult

load_dotenv()

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

logging.basicConfig(
    level=logging.DEBUG if args.debug else logging.WARNING,
    format="%(name)s %(levelname)s %(message)s",
)


def _print_market_result(result: MarketArbitrageResult) -> None:
    home = result.events[0].home_team
    away = result.events[0].away_team
    line_str = f" {result.line}" if result.line is not None else ""
    print(
        f"{home} vs {away}"
        f"  |  market={result.market_type}{line_str}"
        f"  |  arbitrage={result.is_arbitrage}"
        f"  |  margin={result.profit_margin:.2f}%"
    )
    for outcome in result.best_outcomes:
        print(f"best {outcome.outcome_name}: {outcome.bookmaker} @ {outcome.odds}")
    print()


if __name__ == "__main__":

    teammex = TeamMexico().get_events()
    playdoit = Playdoit().get_events()
    caliente = Caliente().get_events()
    polymarket = Polymarket().get_events()

    all_events = teammex + playdoit + caliente + polymarket

    for group in group_events(all_events):
        result = find_arbitrage_1x2(group)
        if result is not None:
            print(
                f"{result.events[0].home_team} vs {result.events[0].away_team}"
                f"  |  market=1x2"
                f"  |  arbitrage={result.is_arbitrage}"
                f"  |  margin={result.profit_margin:.2f}%"
            )
            print(f"  best home: {result.best_home.bookmaker} @ {result.best_home.odds}")
            print(f"  best draw: {result.best_draw.bookmaker} @ {result.best_draw.odds}")
            print(f"  best away: {result.best_away.bookmaker} @ {result.best_away.odds}")
            print()

        r = find_arbitrage_btts(group)
        if r is not None:
            _print_market_result(r)

        r = find_arbitrage_double_chance(group)
        if r is not None:
            _print_market_result(r)

        for r in find_arbitrage_total_goals(group):
            _print_market_result(r)

        for r in find_arbitrage_asian_handicap(group):
            _print_market_result(r)
    