import logging
from datetime import datetime

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
    find_ev_bets_1x2,
    find_ev_bets_btts,
    find_ev_bets_double_chance,
    find_ev_bets_total_goals,
    find_ev_bets_asian_handicap,
    find_correlation_bets,
)
from bookmakers.constants import MARKET_1X2, LIGA_MX, PREMIER_LEAGUE
from models import ArbitrageResult, MarketArbitrageResult, EVBet, CorrelationBet

from .schemas import (
    ResultsResponse,
    EventResultSchema,
    ArbitrageSchema,
    BestOutcomeSchema,
    EVBetSchema,
    CorrelationBetSchema,
    CorrelationLegSchema,
)

log = logging.getLogger(__name__)

SPORT = "football"
LEAGUES_TO_RUN = [
    LIGA_MX,
    PREMIER_LEAGUE,
]

REFRESH_INTERVAL_SECONDS = 5 * 60


def _fetch_bookmaker(name: str, bookmaker_cls, sport: str, league: str) -> list:
    try:
        return bookmaker_cls().get_events(sport, league)
    except Exception:
        log.exception("Failed to fetch %s", name)
        return []


def _arb_1x2_to_schema(r: ArbitrageResult) -> ArbitrageSchema:
    return ArbitrageSchema(
        market_type=MARKET_1X2,
        line=None,
        is_arbitrage=r.is_arbitrage,
        profit_margin=r.profit_margin,
        best_outcomes=[
            BestOutcomeSchema(outcome_name=r.best_home.outcome_name, bookmaker=r.best_home.bookmaker, odds=r.best_home.odds),
            BestOutcomeSchema(outcome_name=r.best_draw.outcome_name, bookmaker=r.best_draw.bookmaker, odds=r.best_draw.odds),
            BestOutcomeSchema(outcome_name=r.best_away.outcome_name, bookmaker=r.best_away.bookmaker, odds=r.best_away.odds),
        ],
    )


def _market_result_to_schema(r: MarketArbitrageResult) -> ArbitrageSchema:
    return ArbitrageSchema(
        market_type=r.market_type,
        line=r.line,
        is_arbitrage=r.is_arbitrage,
        profit_margin=r.profit_margin,
        best_outcomes=[
            BestOutcomeSchema(outcome_name=o.outcome_name, bookmaker=o.bookmaker, odds=o.odds)
            for o in r.best_outcomes
        ],
    )


def _ev_bet_to_schema(bet: EVBet) -> EVBetSchema:
    return EVBetSchema(
        market_type=bet.market_type,
        line=bet.line,
        outcome_name=bet.outcome_name,
        bookmaker=bet.bookmaker,
        odds=bet.odds,
        fair_odds=bet.fair_odds,
        edge=bet.edge,
    )


def _correlation_bet_to_schema(bet: CorrelationBet) -> CorrelationBetSchema:
    return CorrelationBetSchema(
        legs=[
            CorrelationLegSchema(
                market_type=leg.market_type,
                line=leg.line,
                outcome_name=leg.outcome_name,
                bookmaker=leg.bookmaker,
                odds=leg.odds,
                fair_odds=leg.fair_odds,
            )
            for leg in bet.legs
        ],
        combined_odds=bet.combined_odds,
        fair_odds=bet.fair_odds,
        edge=bet.edge,
    )


def fetch_all_results() -> ResultsResponse:
    bookmakers = [
        ("TeamMexico", TeamMexico),
        ("Playdoit", Playdoit),
        ("Caliente", Caliente),
        ("Polymarket", Polymarket),
    ]

    all_events = []
    for league in LEAGUES_TO_RUN:
        for name, cls in bookmakers:
            all_events.extend(_fetch_bookmaker(name, cls, SPORT, league))

    event_results: list[EventResultSchema] = []

    for group in group_events(all_events):
        rep = group[0]
        arbitrage: list[ArbitrageSchema] = []
        ev_bets: list[EVBetSchema] = []
        correlation_bets: list[CorrelationBetSchema] = []

        r = find_arbitrage_1x2(group)
        if r is not None:
            arbitrage.append(_arb_1x2_to_schema(r))

        for fn in (find_arbitrage_btts, find_arbitrage_double_chance):
            r = fn(group)
            if r is not None:
                arbitrage.append(_market_result_to_schema(r))

        for r in find_arbitrage_total_goals(group):
            arbitrage.append(_market_result_to_schema(r))

        for r in find_arbitrage_asian_handicap(group):
            arbitrage.append(_market_result_to_schema(r))

        for fn in (
            find_ev_bets_1x2,
            find_ev_bets_btts,
            find_ev_bets_double_chance,
            find_ev_bets_total_goals,
            find_ev_bets_asian_handicap,
        ):
            for bet in fn(group):
                ev_bets.append(_ev_bet_to_schema(bet))

        for bet in find_correlation_bets(group):
            correlation_bets.append(_correlation_bet_to_schema(bet))

        event_results.append(
            EventResultSchema(
                home_team=rep.home_team,
                away_team=rep.away_team,
                start_time=rep.start_time,
                league=rep.league,
                bookmakers=sorted({e.bookmaker for e in group}),
                arbitrage=arbitrage,
                ev_bets=ev_bets,
                correlation_bets=correlation_bets,
            )
        )

    return ResultsResponse(
        last_updated=datetime.now(),
        refresh_interval_seconds=REFRESH_INTERVAL_SECONDS,
        events=event_results,
    )
