# bookmakers/base.py

from abc import ABC, abstractmethod
from models import Event


class Bookmaker(ABC):

    SUPPORTED_LEAGUES: frozenset[str] = frozenset()

    @abstractmethod
    def get_events(
        self,
        sport: str,
        league: str,
    ) -> list[Event]:
        ...