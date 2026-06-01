"""Orchestrates transcript fetch and search."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from supersearch import cache
from supersearch.core import (
    SearchResult,
    TranscriptEntry,
    fetch_transcript,
    search_transcript,
    whisper_transcribe,
)
from supersearch.urls import INVALID_URL_MSG, is_allowed_url, is_twitch_url

ProgressFn = Callable[[dict], None]


def run_super_search(
    url: str,
    query: str,
    *,
    n: int = 8,
    window_sec: float = 30.0,
    clip_extra_before: float = 3.0,
    clip_extra_after: float = 5.0,
    use_whisper: bool = False,
    force_refresh: bool = False,
    on_progress: ProgressFn | None = None,
) -> dict:
    url = url.strip()
    query = query.strip()

    if not url:
        raise ValueError("url is required")
    if not query:
        raise ValueError("query is required")
    if not is_allowed_url(url):
        raise ValueError(INVALID_URL_MSG)

    if is_twitch_url(url):
        use_whisper = True

    entries, whisper_used, from_cache, cached_at, warning = _load_transcript(
        url,
        use_whisper=use_whisper,
        force_refresh=force_refresh,
        on_progress=on_progress,
    )

    if not entries:
        return _empty_result(warning)

    _emit(on_progress, {"phase": "searching", "msg": f"Searching {len(entries)} entries…"})
    hits = search_transcript(
        entries,
        query,
        n=min(max(n, 1), 20),
        window_sec=window_sec,
        clip_buffer_before=clip_extra_before,
        clip_buffer_after=clip_extra_after,
    )

    return {
        "phase": "result",
        "results": [_hit_dict(hit) for hit in hits],
        "warning": None,
        "whisper_used": whisper_used,
        "cached": from_cache,
        "cached_at": cached_at,
    }


def _load_transcript(
    url: str,
    *,
    use_whisper: bool,
    force_refresh: bool,
    on_progress: ProgressFn | None,
) -> tuple[list[TranscriptEntry], bool, bool, float | None, str | None]:
    entries: list[TranscriptEntry] = []
    whisper_used = False
    from_cache = False
    cached_at: float | None = None
    warning: str | None = None

    if not force_refresh:
        cached = cache.load(url)
        if cached is not None:
            entries, source, cached_at = cached
            from_cache = True
            whisper_used = source == "whisper"
            _emit(
                on_progress,
                {
                    "phase": "cache",
                    "msg": "Loaded transcript from cache.",
                    "cached_at": cached_at,
                    "whisper_used": whisper_used,
                },
            )

    if entries:
        return entries, whisper_used, from_cache, cached_at, warning

    if not use_whisper:
        _emit(on_progress, {"phase": "captions", "msg": "Fetching auto-generated captions…"})
        entries = fetch_transcript(url)
        if entries:
            cache.save(url, entries, "captions")
            return entries, False, from_cache, cached_at, warning

    try:
        entries = whisper_transcribe(url, on_progress=on_progress)
        whisper_used = True
        if entries:
            cache.save(url, entries, "whisper")
    except RuntimeError as exc:
        if use_whisper:
            raise
        warning = f"No captions found and Whisper transcription failed. {exc}"

    return entries, whisper_used, from_cache, cached_at, warning


def _empty_result(warning: str | None) -> dict:
    return {
        "phase": "result",
        "results": [],
        "warning": warning
        or "No transcript found. Enable Whisper or use a video with auto-captions.",
        "whisper_used": False,
        "cached": False,
        "cached_at": None,
    }


def _emit(on_progress: ProgressFn | None, event: dict) -> None:
    if on_progress:
        on_progress(event)


def _hit_dict(hit: SearchResult) -> dict:
    data = asdict(hit)
    data["text"] = (data.get("text") or "")[:400]
    return data
