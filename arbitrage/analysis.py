from bookmakers.constants import MARKET_1X2, HOME, DRAW, AWAY
from models import Event, Market, Outcome, BestOutcome, ArbitrageResult


def _get_1x2_market(event: Event) -> Market | None:
    return next((m for m in event.markets if m.type == MARKET_1X2), None)


def _get_outcome(market: Market, name: str) -> Outcome | None:
    return next((o for o in market.outcomes if o.name == name), None)


def _best(name: str, *options: tuple[str, float]) -> BestOutcome:
    bookmaker, odds = max(options, key=lambda x: x[1])
    return BestOutcome(outcome_name=name, bookmaker=bookmaker, odds=odds)


def find_arbitrage(events: list[Event]) -> ArbitrageResult | None:
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
        is_arbitrage=inverse_sum < 1,
    )
