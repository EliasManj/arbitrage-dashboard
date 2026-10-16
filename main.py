import argparse
import logging
from dotenv import load_dotenv

from bookmakers.playdoit import Playdoit
from bookmakers.caliente import Caliente
from bookmakers.teammexico import TeamMexico
from bookmakers.polymarket import Polymarket
from bookmakers.constants import LIGA_MX, PREMIER_LEAGUE, LA_LIGA, SERIE_A, BUNSEDLIGA, MLS, CHAMPIONS_LEAGUE, LIGUE_1, ARGENTINA_1, EREDIVISIE, BRASIL_A
from arbitrage.matching import group_events
from arbitrage.analysis import (
    find_arbitrage_1x2,
    find_arbitrage_btts,
    find_arbitrage_double_chance,
    find_arbitrage_total_goals,
    find_arbitrage_asian_handicap,
    find_ev_bets_1x2,
    find_ev_bets_btts,
    find_ev_bets_double_chance,
    find_ev_bets_total_goals,
    find_ev_bets_asian_handicap,
    find_correlation_bets,
)
from models import MarketArbitrageResult, EVBet, CorrelationBet

load_dotenv()

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

logging.basicConfig(
    level=logging.DEBUG if args.debug else logging.WARNING,
    format="%(name)s %(levelname)s %(message)s",
)

SPORT = "football"
LEAGUES_TO_RUN = [
    LIGA_MX,
    PREMIER_LEAGUE,
    LA_LIGA, 
    SERIE_A,
    BUNSEDLIGA, 
    MLS, 
    CHAMPIONS_LEAGUE
]


def _print_ev_bet(bet: EVBet) -> None:
    line_str = f" {bet.line}" if bet.line is not None else ""
    print(
        f"+EV  {bet.event.home_team} vs {bet.event.away_team}"
        f"  |  market={bet.market_type}{line_str}"
        f"  |  {bet.outcome_name} @ {bet.bookmaker}"
        f"  |  odds={bet.odds}  fair={bet.fair_odds}  edge=+{bet.edge:.2f}%"
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


def _print_correlation_bet(bet: CorrelationBet) -> None:
    event = bet.event
    legs = " + ".join(
        f"{leg.market_type}{f' {leg.line}' if leg.line is not None else ''}:{leg.outcome_name}@{leg.odds}({leg.bookmaker})"
        for leg in bet.legs
    )
    print(
        f"+Corr  {event.home_team} vs {event.away_team}"
        f"  |  legs={legs}"
        f"  |  combo_odds={bet.combined_odds:.2f}  fair={bet.fair_odds:.2f}"
        f"  |  edge=+{bet.edge:.2f}%"
    )


if __name__ == "__main__":

    bookmakers = [TeamMexico(), Playdoit(), Polymarket()]

    for league in LEAGUES_TO_RUN:
        all_events = []
        for bm in bookmakers:
            all_events.extend(bm.get_events(SPORT, league))

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

            for bet in find_ev_bets_1x2(group):
                _print_ev_bet(bet)
            for bet in find_ev_bets_btts(group):
                _print_ev_bet(bet)
            for bet in find_ev_bets_double_chance(group):
                _print_ev_bet(bet)
            for bet in find_ev_bets_total_goals(group):
                _print_ev_bet(bet)
            for bet in find_ev_bets_asian_handicap(group):
                _print_ev_bet(bet)

            for bet in find_correlation_bets(group):
                _print_correlation_bet(bet)
