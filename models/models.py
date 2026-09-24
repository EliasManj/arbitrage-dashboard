# models.py

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Outcome:
    name: str
    odds: float


@dataclass
class Market:
    type: str
    outcomes: list[Outcome]
    line: float | None = None


@dataclass
class Event:
    bookmaker: str
    bookmaker_event_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: datetime
    markets: list[Market]