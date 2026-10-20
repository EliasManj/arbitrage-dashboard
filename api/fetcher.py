import logging
from datetime import datetime

from bookmakers.playdoit import Playdoit
from bookmakers.caliente import Caliente
from bookmakers.teammexico import TeamMexico
from bookmakers.polymarket import Polymarket
from arbitrage.matching import group_events
from arbitrage.analysis import (
    find_arbitrage_1x2,
    find_arbitrage_moneyline,
    find_arbitrage_btts,
    find_arbitrage_double_chance,
    find_arbitrage_total_goals,
    find_arbitrage_asian_handicap,
    find_ev_bets_1x2,
    find_ev_bets_moneyline,
    find_ev_bets_btts,
    find_ev_bets_double_chance,
    find_ev_bets_total_goals,
    find_ev_bets_asian_handicap,
    find_correlation_bets,
)
from bookmakers.constants import MARKET_1X2, LEAGUE_SPORT, LIGA_MX, PREMIER_LEAGUE, LA_LIGA, SERIE_A, BUNSEDLIGA, MLS, CHAMPIONS_LEAGUE, LIGUE_1, ARGENTINA_1, EREDIVISIE, BRASIL_A, NFL
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

LEAGUES_TO_RUN = [
    LIGA_MX,
    PREMIER_LEAGUE,
    LA_LIGA, 
    SERIE_A,
    BUNSEDLIGA, 
    MLS, 
    CHAMPIONS_LEAGUE,
    LIGUE_1,
    ARGENTINA_1,
    EREDIVISIE,
    BRASIL_A,
    NFL,
]

# Maps internal sport codes → display names shown in the UI
_SPORT_DISPLAY: dict[str, str] = {
    "football": "soccer",
    "american_football": "nfl",
}

def _display_sport(sport: str) -> str:
    return _SPORT_DISPLAY.get(sport, sport)

REFRESH_INTERVAL_SECONDS = 5 * 60

_TEAMMEXICO_SPORT_ID = 66  # Football/Soccer on the Altenar backend


def _bookmaker_url(bookmaker: str, event_id: str | None) -> str | None:
    if not event_id:
        return None
    if bookmaker == "teammexico":
        return f"https://www.teammexico.mx/sports-betting#page=event&eventId={event_id}&sportId={_TEAMMEXICO_SPORT_ID}"
    if bookmaker == "playdoit":
        return f"https://www.playdoit.mx/#page=event&eventId={event_id}&sportId={_TEAMMEXICO_SPORT_ID}"
    if bookmaker == "polymarket":
        return f"https://polymarket.com/sports/{event_id}"
    return None


def _fetch_bookmaker(name: str, bookmaker_cls, sport: str, league: str) -> list:
    if league not in bookmaker_cls.SUPPORTED_LEAGUES:
        log.debug("[%s] skipping league=%s (not in SUPPORTED_LEAGUES)", name, league)
        return []
    try:
        events = bookmaker_cls().get_events(sport, league)
        log.debug("[%s] league=%s sport=%s → %d event(s)", name, league, sport, len(events))
        if events:
            for ev in events:
                log.debug("  [%s] %s vs %s (%s)", name, ev.home_team, ev.away_team, ev.start_time)
        return events
    except Exception:
        log.exception("Failed to fetch %s for league=%s", name, league)
        return []


def _arb_1x2_to_schema(r: ArbitrageResult) -> ArbitrageSchema:
    return ArbitrageSchema(
        market_type=MARKET_1X2,
        line=None,
        is_arbitrage=r.is_arbitrage,
        profit_margin=r.profit_margin,
        best_outcomes=[
            BestOutcomeSchema(outcome_name=r.best_home.outcome_name, bookmaker=r.best_home.bookmaker, odds=r.best_home.odds, raw_price=r.best_home.raw_price),
            BestOutcomeSchema(outcome_name=r.best_draw.outcome_name, bookmaker=r.best_draw.bookmaker, odds=r.best_draw.odds, raw_price=r.best_draw.raw_price),
            BestOutcomeSchema(outcome_name=r.best_away.outcome_name, bookmaker=r.best_away.bookmaker, odds=r.best_away.odds, raw_price=r.best_away.raw_price),
        ],
    )


def _market_result_to_schema(r: MarketArbitrageResult) -> ArbitrageSchema:
    return ArbitrageSchema(
        market_type=r.market_type,
        line=r.line,
        is_arbitrage=r.is_arbitrage,
        profit_margin=r.profit_margin,
        best_outcomes=[
            BestOutcomeSchema(outcome_name=o.outcome_name, bookmaker=o.bookmaker, odds=o.odds, raw_price=o.raw_price)
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
        # ("Caliente", Caliente),
        ("Polymarket", Polymarket),
    ]

    all_events = []
    for league in LEAGUES_TO_RUN:
        sport = LEAGUE_SPORT.get(league, league)
        for name, cls in bookmakers:
            all_events.extend(_fetch_bookmaker(name, cls, sport, league))

    nfl_events = [e for e in all_events if e.league == NFL]
    log.info("[NFL] total raw events fetched: %d", len(nfl_events))
    for ev in nfl_events:
        log.info("  [NFL raw] bookmaker=%s  '%s' vs '%s'", ev.bookmaker, ev.home_team, ev.away_team)

    groups = group_events(all_events)
    nfl_groups = [g for g in groups if g[0].league == NFL]
    log.info("[NFL] event groups after matching (≥2 bookmakers): %d", len(nfl_groups))
    for g in nfl_groups:
        rep = g[0]
        log.info("  [NFL group] '%s' vs '%s' — bookmakers: %s",
                 rep.home_team, rep.away_team, sorted({e.bookmaker for e in g}))

    event_results: list[EventResultSchema] = []

    for group in groups:
        rep = group[0]
        arbitrage: list[ArbitrageSchema] = []
        ev_bets: list[EVBetSchema] = []
        correlation_bets: list[CorrelationBetSchema] = []

        r = find_arbitrage_1x2(group)
        if r is not None:
            arbitrage.append(_arb_1x2_to_schema(r))

        for fn in (find_arbitrage_moneyline, find_arbitrage_btts, find_arbitrage_double_chance):
            r = fn(group)
            if r is not None:
                arbitrage.append(_market_result_to_schema(r))

        for r in find_arbitrage_total_goals(group):
            arbitrage.append(_market_result_to_schema(r))

        for r in find_arbitrage_asian_handicap(group):
            arbitrage.append(_market_result_to_schema(r))

        for fn in (
            find_ev_bets_1x2,
            find_ev_bets_moneyline,
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
                sport=_display_sport(rep.sport),
                bookmakers=sorted({e.bookmaker for e in group}),
                bookmaker_urls={
                    e.bookmaker: url
                    for e in group
                    if (url := _bookmaker_url(e.bookmaker, e.bookmaker_event_id))
                },
                arbitrage=sorted(arbitrage, key=lambda a: a.profit_margin, reverse=True),
                ev_bets=ev_bets,
                correlation_bets=correlation_bets,
            )
        )

    return ResultsResponse(
        last_updated=datetime.now(),
        refresh_interval_seconds=REFRESH_INTERVAL_SECONDS,
        events=event_results,
    )
