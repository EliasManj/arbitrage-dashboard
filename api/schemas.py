from datetime import datetime
from pydantic import BaseModel


class BestOutcomeSchema(BaseModel):
    outcome_name: str
    bookmaker: str
    odds: float


class ArbitrageSchema(BaseModel):
    market_type: str
    line: float | None
    is_arbitrage: bool
    profit_margin: float
    best_outcomes: list[BestOutcomeSchema]


class EVBetSchema(BaseModel):
    market_type: str
    line: float | None
    outcome_name: str
    bookmaker: str
    odds: float
    fair_odds: float
    edge: float


class CorrelationLegSchema(BaseModel):
    market_type: str
    line: float | None
    outcome_name: str
    bookmaker: str
    odds: float
    fair_odds: float


class CorrelationBetSchema(BaseModel):
    legs: list[CorrelationLegSchema]
    combined_odds: float
    fair_odds: float
    edge: float


class EventResultSchema(BaseModel):
    home_team: str
    away_team: str
    start_time: datetime
    league: str
    bookmakers: list[str]
    arbitrage: list[ArbitrageSchema]
    ev_bets: list[EVBetSchema]
    correlation_bets: list[CorrelationBetSchema]


class ResultsResponse(BaseModel):
    last_updated: datetime | None
    refresh_interval_seconds: int
    events: list[EventResultSchema]
