from bookmakers.constants import (
    MARKET_1X2, HOME, DRAW, AWAY,
    MARKET_BTTS, YES, NO,
    MARKET_DOUBLE_CHANCE, HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY,
    MARKET_TOTAL, OVER, UNDER,
    MARKET_ASIAN_HANDICAP,
)
from models import Event, Market, Outcome, BestOutcome, ArbitrageResult, MarketArbitrageResult

# Require at least 0.5% margin to avoid false positives from same-bookmaker pricing
MIN_MARGIN = 0.005


def _get_1x2_market(event: Event) -> Market | None:
    return next((m for m in event.markets if m.type == MARKET_1X2), None)


def _get_outcome(market: Market, name: str) -> Outcome | None:
    return next((o for o in market.outcomes if o.name == name), None)


def _best(name: str, *options: tuple[str, float]) -> BestOutcome:
    bookmaker, odds = max(options, key=lambda x: x[1])
    return BestOutcome(outcome_name=name, bookmaker=bookmaker, odds=odds)


def find_arbitrage_1x2(events: list[Event]) -> ArbitrageResult | None:
    markets = [(e, _get_1x2_market(e)) for e in events]
    markets = [(e, m) for e, m in markets if m is not None]

    if not markets:
        return None

    outcome_options: dict[str, list[tuple[str, float]]] = {HOME: [], DRAW: [], AWAY: []}

    for event, market in markets:
        for outcome_name in (HOME, DRAW, AWAY):
            outcome = _get_outcome(market, outcome_name)
            if outcome is not None:
                outcome_options[outcome_name].append((event.bookmaker, outcome.odds))

    if any(len(opts) == 0 for opts in outcome_options.values()):
        return None

    best_home = _best(HOME, *outcome_options[HOME])
    best_draw = _best(DRAW, *outcome_options[DRAW])
    best_away = _best(AWAY, *outcome_options[AWAY])

    inverse_sum = 1 / best_home.odds + 1 / best_draw.odds + 1 / best_away.odds

    return ArbitrageResult(
        events=events,
        best_home=best_home,
        best_draw=best_draw,
        best_away=best_away,
        inverse_sum=inverse_sum,
        is_arbitrage=inverse_sum < 1 - MIN_MARGIN,
    )


def _find_arbitrage_flat(
    events: list[Event],
    market_type: str,
    outcome_names: tuple[str, ...],
) -> MarketArbitrageResult | None:
    """Arbitrage for markets with no line (BTTS, Double Chance)."""
    options: dict[str, list[tuple[str, float]]] = {n: [] for n in outcome_names}
    for event in events:
        market = next((m for m in event.markets if m.type == market_type), None)
        if market is None:
            continue
        for name in outcome_names:
            outcome = _get_outcome(market, name)
            if outcome is not None:
                options[name].append((event.bookmaker, outcome.odds))

    if any(len(v) == 0 for v in options.values()):
        return None

    best = [_best(name, *options[name]) for name in outcome_names]
    inverse_sum = sum(1 / b.odds for b in best)
    return MarketArbitrageResult(
        events=events, market_type=market_type, line=None,
        best_outcomes=best, inverse_sum=inverse_sum, is_arbitrage=inverse_sum < 1 - MIN_MARGIN,
    )


def _find_arbitrage_by_line(
    events: list[Event],
    market_type: str,
    outcome_names: tuple[str, str],
) -> list[MarketArbitrageResult]:
    """Arbitrage for markets with a line (Total Goals, Asian Handicap)."""
    by_line: dict[float, dict[str, list[tuple[str, float]]]] = {}
    for event in events:
        for market in event.markets:
            if market.type != market_type or market.line is None:
                continue
            by_line.setdefault(market.line, {n: [] for n in outcome_names})
            for name in outcome_names:
                outcome = _get_outcome(market, name)
                if outcome is not None:
                    by_line[market.line][name].append((event.bookmaker, outcome.odds))

    results = []
    for line, opts in sorted(by_line.items()):
        if any(len(v) == 0 for v in opts.values()):
            continue
        best = [_best(name, *opts[name]) for name in outcome_names]
        inverse_sum = sum(1 / b.odds for b in best)
        results.append(MarketArbitrageResult(
            events=events, market_type=market_type, line=line,
            best_outcomes=best, inverse_sum=inverse_sum, is_arbitrage=inverse_sum < 1 - MIN_MARGIN,
        ))
    return results


def find_arbitrage_btts(events: list[Event]) -> MarketArbitrageResult | None:
    return _find_arbitrage_flat(events, MARKET_BTTS, (YES, NO))


def find_arbitrage_double_chance(events: list[Event]) -> MarketArbitrageResult | None:
    return _find_arbitrage_flat(events, MARKET_DOUBLE_CHANCE, (HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY))


def find_arbitrage_total_goals(events: list[Event]) -> list[MarketArbitrageResult]:
    return _find_arbitrage_by_line(events, MARKET_TOTAL, (OVER, UNDER))


def find_arbitrage_asian_handicap(events: list[Event]) -> list[MarketArbitrageResult]:
    return _find_arbitrage_by_line(events, MARKET_ASIAN_HANDICAP, (HOME, AWAY))
