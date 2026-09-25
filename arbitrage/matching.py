import re
from models import Event

_NOISE = re.compile(
    r"\b(f\.?c\.?|deportivo|club|uanl|unam|mx|de|del|los|fc|caliente)\b",
    re.IGNORECASE,
)


def normalize_team(name: str) -> str:
    normalized = _NOISE.sub("", name.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _teams_match(a: str, b: str) -> bool:
    return set(normalize_team(a).split()) == set(normalize_team(b).split())


def match_events(
    events_a: list[Event],
    events_b: list[Event],
) -> list[tuple[Event, Event]]:
    matches = []

    for a in events_a:
        for b in events_b:
            if _teams_match(a.home_team, b.home_team) and _teams_match(a.away_team, b.away_team):
                matches.append((a, b))

    return matches
