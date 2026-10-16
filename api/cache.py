import threading
import logging
from pathlib import Path
from .schemas import ResultsResponse

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: ResultsResponse | None = None

_CACHE_FILE = Path(__file__).parent.parent / "storage" / "results_cache.json"


def get_cache() -> ResultsResponse | None:
    with _lock:
        return _cache


def set_cache(results: ResultsResponse) -> None:
    global _cache
    with _lock:
        _cache = results
    _save_to_disk(results)


def load_from_disk() -> None:
    global _cache
    if not _CACHE_FILE.exists():
        return
    try:
        _cache = ResultsResponse.model_validate_json(_CACHE_FILE.read_text())
        log.info("Loaded %d cached events from disk", len(_cache.events))
    except Exception:
        log.warning("Could not load cache from disk; starting fresh", exc_info=True)


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None
    try:
        _CACHE_FILE.unlink(missing_ok=True)
        log.info("Cache cleared")
    except Exception:
        log.warning("Could not delete cache file", exc_info=True)


def _save_to_disk(results: ResultsResponse) -> None:
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        _CACHE_FILE.write_text(results.model_dump_json())
    except Exception:
        log.warning("Could not save cache to disk", exc_info=True)
