import re
from models import Event

_NOISE = re.compile(
    r"\b(f\.?c\.?|deportivo|club|uanl|unam|mx|de|del|los|fc|caliente)\b",
    re.IGNORECASE,
)

# NFL team abbreviations used by Altenar → expanded city/region tokens
# Only the first token of a name is expanded so soccer names are unaffected.
_NFL_ABBR: dict[str, list[str]] = {
    "arz": ["arizona"],
    "atl": ["atlanta"],
    "bal": ["baltimore"],
    "buf": ["buffalo"],
    "car": ["carolina"],
    "chi": ["chicago"],
    "cin": ["cincinnati"],
    "cle": ["cleveland"],
    "dal": ["dallas"],
    "den": ["denver"],
    "det": ["detroit"],
    "gb": ["green", "bay"],
    "hou": ["houston"],
    "ind": ["indianapolis"],
    "jax": ["jacksonville"],
    "kc": ["kansas", "city"],
    "la": ["los", "angeles"],
    "lac": ["los", "angeles"],
    "lar": ["los", "angeles"],
    "lv": ["las", "vegas"],
    "mia": ["miami"],
    "min": ["minnesota"],
    "ne": ["new", "england"],
    "no": ["new", "orleans"],
    "ny": ["new", "york"],
    "nyg": ["new", "york"],
    "nyj": ["new", "york"],
    "phi": ["philadelphia"],
    "pit": ["pittsburgh"],
    "sea": ["seattle"],
    "sf": ["san", "francisco"],
    "tb": ["tampa", "bay"],
    "ten": ["tennessee"],
    "wsh": ["washington"],
}


def normalize_team(name: str) -> str:
    lower = re.sub(r"\s+", " ", name.lower()).strip()
    tokens = lower.split()
    # Expand NFL abbreviations before noise filtering so "LA" → "los angeles" → noise strips "los"
    if tokens and tokens[0] in _NFL_ABBR:
        tokens = _NFL_ABBR[tokens[0]] + tokens[1:]
    expanded = " ".join(tokens)
    normalized = _NOISE.sub("", expanded)
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
