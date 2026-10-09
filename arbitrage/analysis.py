from bookmakers.constants import (
    MARKET_1X2, HOME, DRAW, AWAY,
    MARKET_BTTS, YES, NO,
    MARKET_DOUBLE_CHANCE, HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY,
    MARKET_TOTAL, OVER, UNDER,
    MARKET_ASIAN_HANDICAP,
)
from models import Event, Market, Outcome, BestOutcome, ArbitrageResult, MarketArbitrageResult, EVBet

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


# ---------------------------------------------------------------------------
# +EV analysis — consensus no-vig fair price vs each bookmaker's offered odds
# ---------------------------------------------------------------------------

def _no_vig_probs(outcomes: list[Outcome]) -> dict[str, float]:
    raw = {o.name: 1 / o.odds for o in outcomes if o.odds > 0}
    total = sum(raw.values())
    return {name: p / total for name, p in raw.items()} if total > 0 else {}


def _fair_probs(
    events: list[Event],
    market_type: str,
    outcome_names: tuple[str, ...],
    line: float | None = None,
) -> dict[str, float] | None:
    """Average no-vig probabilities across all sources for a market/line."""
    all_probs: list[dict[str, float]] = []
    for event in events:
        for market in event.markets:
            if market.type != market_type:
                continue
            if line is not None and market.line != line:
                continue
            probs = _no_vig_probs(market.outcomes)
            if all(k in probs for k in outcome_names):
                all_probs.append(probs)
    if not all_probs:
        return None
    return {
        name: sum(p[name] for p in all_probs) / len(all_probs)
        for name in outcome_names
    }


def _collect_ev_bets(
    events: list[Event],
    market_type: str,
    outcome_names: tuple[str, ...],
    line: float | None = None,
) -> list[EVBet]:
    fair = _fair_probs(events, market_type, outcome_names, line)
    if not fair:
        return []
    bets = []
    for event in events:
        for market in event.markets:
            if market.type != market_type:
                continue
            if line is not None and market.line != line:
                continue
            for outcome in market.outcomes:
                fp = fair.get(outcome.name)
                if not fp:
                    continue
                edge = round((outcome.odds * fp - 1) * 100, 2)
                if edge > 0:
                    bets.append(EVBet(
                        event=event,
                        market_type=market_type,
                        line=market.line,
                        outcome_name=outcome.name,
                        bookmaker=event.bookmaker,
                        odds=outcome.odds,
                        fair_odds=round(1 / fp, 4),
                        edge=edge,
                    ))
    return sorted(bets, key=lambda b: b.edge, reverse=True)


def find_ev_bets_1x2(events: list[Event]) -> list[EVBet]:
    return _collect_ev_bets(events, MARKET_1X2, (HOME, DRAW, AWAY))


def find_ev_bets_btts(events: list[Event]) -> list[EVBet]:
    return _collect_ev_bets(events, MARKET_BTTS, (YES, NO))


def find_ev_bets_double_chance(events: list[Event]) -> list[EVBet]:
    return _collect_ev_bets(events, MARKET_DOUBLE_CHANCE, (HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY))


def find_ev_bets_total_goals(events: list[Event]) -> list[EVBet]:
    lines = sorted({
        m.line for e in events for m in e.markets
        if m.type == MARKET_TOTAL and m.line is not None
    })
    bets: list[EVBet] = []
    for line in lines:
        bets.extend(_collect_ev_bets(events, MARKET_TOTAL, (OVER, UNDER), line))
    return bets


def find_ev_bets_asian_handicap(events: list[Event]) -> list[EVBet]:
    lines = sorted({
        m.line for e in events for m in e.markets
        if m.type == MARKET_ASIAN_HANDICAP and m.line is not None
    })
    bets: list[EVBet] = []
    for line in lines:
        bets.extend(_collect_ev_bets(events, MARKET_ASIAN_HANDICAP, (HOME, AWAY), line))
    return bets