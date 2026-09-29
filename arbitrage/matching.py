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


def group_events(events: list[Event]) -> list[list[Event]]:
    groups: list[list[Event]] = []

    for event in events:
        for group in groups:
            rep = group[0]
            if _teams_match(event.home_team, rep.home_team) and _teams_match(event.away_team, rep.away_team):
                group.append(event)
                break
        else:
            groups.append([event])

    return [g for g in groups if len(g) > 1]
