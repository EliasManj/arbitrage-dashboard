import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cache import get_cache, set_cache, load_from_disk, clear_cache
from .fetcher import fetch_all_results, REFRESH_INTERVAL_SECONDS

log = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


async def _do_refresh() -> None:
    log.info("Refreshing results...")
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(None, fetch_all_results)
        set_cache(results)
        log.info("Refresh complete: %d events", len(results.events))
    except Exception:
        log.exception("Refresh failed")


async def _refresh_loop() -> None:
    while True:
        await _do_refresh()
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_from_disk()
    task = asyncio.create_task(_refresh_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="LigaMX Arbitrage", lifespan=lifespan)


@app.get("/api/results")
async def get_results():
    cache = get_cache()
    if cache is None:
        return {
            "last_updated": None,
            "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS,
            "events": [],
        }
    return cache


@app.post("/api/refresh", status_code=202)
async def trigger_refresh():
    asyncio.create_task(_do_refresh())
    return {"message": "Refresh triggered"}


@app.delete("/api/cache", status_code=200)
async def delete_cache():
    clear_cache()
    return {"message": "Cache cleared"}


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")
