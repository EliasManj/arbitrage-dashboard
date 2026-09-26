# models.py

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Outcome:
    name: str
    odds: float
    bookmaker_outcome_id: str | None = None

@dataclass
class Market:
    type: str
    outcomes: list[Outcome]
    line: float | None = None
    bookmaker_market_id: str | None = None


@dataclass
class Event:
    bookmaker: str
    bookmaker_event_id: str | None
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime
    markets: list[Market]


@dataclass
class BestOutcome:
    outcome_name: str
    bookmaker: str
    odds: float


@dataclass
class ArbitrageResult:
    events: list[Event]          # replaces event_a / event_b
    best_home: BestOutcome
    best_draw: BestOutcome
    best_away: BestOutcome
    inverse_sum: float
    is_arbitrage: bool

    @property
    def profit_margin(self) -> float:
        return (1 - self.inverse_sum) * 100