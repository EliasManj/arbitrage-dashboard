from bookmakers.constants import (
    MARKET_1X2, HOME, DRAW, AWAY,
    MARKET_BTTS, YES, NO,
    MARKET_DOUBLE_CHANCE, HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY,
    MARKET_TOTAL, OVER, UNDER,
    MARKET_ASIAN_HANDICAP,
)
import math

from arbitrage.matching import group_events
from models import (
    Event,
    Market,
    Outcome,
    BestOutcome,
    ArbitrageResult,
    MarketArbitrageResult,
    EVBet,
    CorrelationLeg,
    CorrelationBet,
)

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
    """Average no-vig probabilities across all sources for a market/line.

    Requires at least two distinct bookmakers so the fair price is not
    self-referential (a single-source price would make edge calculations
    circular for correlation bets).
    """
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
    if len(all_probs) < 2:
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


# Legs with fair probability below this threshold have extreme odds where the
# correlation adjustment term dominates and produces inflated phantom edges.
_MIN_CORR_LEG_PROB = 0.10


def _best_legs_for_market(
    events: list[Event],
    market_type: str,
    outcome_names: tuple[str, ...],
    line: float | None = None,
) -> list[CorrelationLeg]:
    fair = _fair_probs(events, market_type, outcome_names, line)
    if not fair:
        return []

    best: dict[str, CorrelationLeg] = {}
    for event in events:
        for market in event.markets:
            if market.type != market_type:
                continue
            if line is not None and market.line != line:
                continue
            for outcome in market.outcomes:
                fp = fair.get(outcome.name)
                if fp is None or fp < _MIN_CORR_LEG_PROB:
                    continue
                candidate = CorrelationLeg(
                    market_type=market_type,
                    line=market.line,
                    outcome_name=outcome.name,
                    bookmaker=event.bookmaker,
                    odds=outcome.odds,
                    fair_prob=fp,
                    fair_odds=round(1 / fp, 4),
                )
                current = best.get(outcome.name)
                if current is None or candidate.odds > current.odds:
                    best[outcome.name] = candidate
    return list(best.values())


def _legs_are_compatible(left: CorrelationLeg, right: CorrelationLeg) -> bool:
    if left.market_type == right.market_type and left.line == right.line:
        return False
    if left.market_type == right.market_type and left.outcome_name == right.outcome_name:
        return False

    # Determine which leg is the handicap and which is the total (order-independent).
    ah, tot = None, None
    for leg in (left, right):
        if leg.market_type == MARKET_ASIAN_HANDICAP:
            ah = leg
        elif leg.market_type == MARKET_TOTAL:
            tot = leg

    # A handicap of N means the winning side scores at least ⌈N⌉ more goals than
    # the other side, so total goals >= N + 1. If the total-under line is <= that
    # minimum, the two outcomes are mutually exclusive.
    if ah is not None and tot is not None and ah.line is not None and tot.line is not None:
        if tot.outcome_name == UNDER and tot.line <= ah.line:
            return False

    return True


def _pair_correlation_strength(left: CorrelationLeg, right: CorrelationLeg) -> float:
    if left.market_type == MARKET_1X2 and right.market_type == MARKET_TOTAL:
        if left.outcome_name == HOME and right.outcome_name == OVER:
            return 0.18
        if left.outcome_name == AWAY and right.outcome_name == UNDER:
            return 0.18
        if left.outcome_name == HOME and right.outcome_name == UNDER:
            return 0.08
        if left.outcome_name == AWAY and right.outcome_name == OVER:
            return 0.08

    if left.market_type == MARKET_BTTS and right.market_type == MARKET_1X2:
        if left.outcome_name == YES and right.outcome_name == HOME:
            return 0.22
        if left.outcome_name == YES and right.outcome_name == AWAY:
            return 0.16
        if left.outcome_name == NO and right.outcome_name == DRAW:
            return 0.12

    if left.market_type == MARKET_TOTAL and right.market_type == MARKET_ASIAN_HANDICAP:
        if left.outcome_name == OVER and right.outcome_name == HOME:
            return 0.15
        if left.outcome_name == UNDER and right.outcome_name == AWAY:
            return 0.15

    if left.outcome_name == right.outcome_name:
        return 0.0

    if left.outcome_name in {HOME, YES, OVER} and right.outcome_name in {HOME, YES, OVER}:
        return 0.1

    if left.outcome_name in {AWAY, NO, UNDER} and right.outcome_name in {AWAY, NO, UNDER}:
        return 0.1

    return 0.04


def find_correlation_bets(events: list[Event]) -> list[CorrelationBet]:
    """Return positive-EV correlated combinations for a fixture group.

    This intentionally keeps the logic conservative: it only pairs outcomes from
    different market/line buckets, and only when their combined fair odds still
    produce a positive edge after a modest correlation adjustment.
    """
    if not events:
        return []

    grouped = group_events(events)

    results: list[CorrelationBet] = []
    for group in grouped:
        if len(group) < 2:
            continue

        market_keys: set[tuple[str, float | None]] = set()
        for event in group:
            for market in event.markets:
                market_keys.add((market.type, market.line))

        candidates: list[CorrelationLeg] = []
        for market_type, line in sorted(market_keys, key=lambda item: (item[0], item[1] or 0.0)):
            if market_type == MARKET_1X2:
                names = (HOME, DRAW, AWAY)
            elif market_type == MARKET_BTTS:
                names = (YES, NO)
            elif market_type == MARKET_DOUBLE_CHANCE:
                names = (HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY)
            elif market_type == MARKET_TOTAL:
                names = (OVER, UNDER)
            elif market_type == MARKET_ASIAN_HANDICAP:
                names = (HOME, AWAY)
            else:
                continue
            candidates.extend(_best_legs_for_market(group, market_type, names, line))

        # Remove duplicate legs from the same outcome/market so we keep the best odds only.
        unique_by_key: dict[tuple[str, float | None, str], CorrelationLeg] = {}
        for candidate in candidates:
            key = (candidate.market_type, candidate.line, candidate.outcome_name)
            previous = unique_by_key.get(key)
            if previous is None or candidate.odds > previous.odds:
                unique_by_key[key] = candidate
        candidates = list(unique_by_key.values())

        for i, left in enumerate(candidates):
            for right in candidates[i + 1:]:
                if not _legs_are_compatible(left, right):
                    continue

                corr = _pair_correlation_strength(left, right)
                if corr <= 0:
                    continue

                joint_probability = (
                    left.fair_prob * right.fair_prob
                    + corr * math.sqrt(
                        left.fair_prob * (1 - left.fair_prob)
                        * right.fair_prob * (1 - right.fair_prob)
                    )
                )
                if joint_probability <= 0 or joint_probability >= 1:
                    continue

                combined_odds = left.odds * right.odds
                fair_odds = 1 / joint_probability
                edge = (combined_odds * joint_probability - 1) * 100
                if edge <= 0.5:
                    continue

                results.append(
                    CorrelationBet(
                        event=group[0],
                        legs=[left, right],
                        joint_probability=round(joint_probability, 6),
                        combined_odds=round(combined_odds, 4),
                        fair_odds=round(fair_odds, 4),
                        edge=round(edge, 2),
                    )
                )

    return sorted(results, key=lambda bet: bet.edge, reverse=True)