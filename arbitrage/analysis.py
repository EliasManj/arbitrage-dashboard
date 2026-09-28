from bookmakers.constants import MARKET_1X2, HOME, DRAW, AWAY
from models import Event, Market, Outcome, BestOutcome, ArbitrageResult


def _get_1x2_market(event: Event) -> Market | None:
    return next((m for m in event.markets if m.type == MARKET_1X2), None)


def _get_outcome(market: Market, name: str) -> Outcome | None:
    return next((o for o in market.outcomes if o.name == name), None)


def _best(name: str, *options: tuple[str, float]) -> BestOutcome:
    bookmaker, odds = max(options, key=lambda x: x[1])
    return BestOutcome(outcome_name=name, bookmaker=bookmaker, odds=odds)


def find_arbitrage(event_a: Event, event_b: Event) -> ArbitrageResult | None:
    market_a = _get_1x2_market(event_a)
    market_b = _get_1x2_market(event_b)

    if market_a is None or market_b is None:
        return None

    for outcome_name in (HOME, DRAW, AWAY):
        if _get_outcome(market_a, outcome_name) is None:
            return None
        if _get_outcome(market_b, outcome_name) is None:
            return None

    best_home = _best(
        HOME,
        (event_a.bookmaker, _get_outcome(market_a, HOME).odds),
        (event_b.bookmaker, _get_outcome(market_b, HOME).odds),
    )
    best_draw = _best(
        DRAW,
        (event_a.bookmaker, _get_outcome(market_a, DRAW).odds),
        (event_b.bookmaker, _get_outcome(market_b, DRAW).odds),
    )
    best_away = _best(
        AWAY,
        (event_a.bookmaker, _get_outcome(market_a, AWAY).odds),
        (event_b.bookmaker, _get_outcome(market_b, AWAY).odds),
    )

    inverse_sum = 1 / best_home.odds + 1 / best_draw.odds + 1 / best_away.odds

    return ArbitrageResult(
        events=[event_a, event_b],
        best_home=best_home,
        best_draw=best_draw,
        best_away=best_away,
        inverse_sum=inverse_sum,
        is_arbitrage=inverse_sum < 1,
    )
