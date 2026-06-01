"""HTTP API with SSE progress streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from supersearch import cache
from supersearch.service import run_super_search
from supersearch.urls import INVALID_URL_MSG, is_allowed_url

LOG = logging.getLogger(__name__)
SSE_PING_SEC = 15.0

app = FastAPI(
    title="Super Search",
    description="Find moments in YouTube and Twitch VODs by searching the transcript",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _bad_request(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=400)


async def _read_json(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _bad_request("Expected JSON body.")
    if not isinstance(body, dict):
        return _bad_request("Expected JSON object.")
    return body


@app.post("/api/super-search", response_model=None)
async def super_search(request: Request) -> StreamingResponse | JSONResponse:
    body = await _read_json(request)
    if isinstance(body, JSONResponse):
        return body

    url = str(body.get("url") or "").strip()
    query = str(body.get("query") or "").strip()
    if not url:
        return _bad_request("url is required.")
    if not query:
        return _bad_request("query is required.")
    if not is_allowed_url(url):
        return _bad_request(INVALID_URL_MSG)

    n = min(max(int(body.get("n") or 8), 1), 20)
    window_sec = float(body.get("window_sec") or 30.0)
    clip_extra_before = float(body.get("clip_extra_before") or 3.0)
    clip_extra_after = float(body.get("clip_extra_after") or 5.0)
    use_whisper = bool(body.get("whisper", False))
    force_refresh = bool(body.get("force_refresh", False))

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def progress(evt: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, evt)

    def worker() -> None:
        try:
            progress({"phase": "starting", "msg": "Starting search…"})
            progress(
                run_super_search(
                    url,
                    query,
                    n=n,
                    window_sec=window_sec,
                    clip_extra_before=clip_extra_before,
                    clip_extra_after=clip_extra_after,
                    use_whisper=use_whisper,
                    force_refresh=force_refresh,
                    on_progress=progress,
                )
            )
        except ValueError as exc:
            progress({"phase": "error", "detail": str(exc)})
        except Exception as exc:
            LOG.exception("super_search failed")
            progress({"phase": "error", "detail": str(exc)[-600:] or "Search failed."})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()

    async def event_stream():
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=SSE_PING_SEC)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if evt is None:
                return
            yield f"data: {json.dumps(evt, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.delete("/api/super-search/cache")
async def clear_cache(request: Request) -> JSONResponse:
    body = await _read_json(request)
    if isinstance(body, JSONResponse):
        return body
    url = str(body.get("url") or "").strip()
    if not url:
        return _bad_request("url is required.")
    return JSONResponse({"cleared": cache.clear(url)})


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "supersearch.api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
