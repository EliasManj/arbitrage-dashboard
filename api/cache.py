import threading
from .schemas import ResultsResponse

_lock = threading.Lock()
_cache: ResultsResponse | None = None


def get_cache() -> ResultsResponse | None:
    with _lock:
        return _cache


def set_cache(results: ResultsResponse) -> None:
    global _cache
    with _lock:
        _cache = results
