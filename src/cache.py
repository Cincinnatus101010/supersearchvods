"""Disk cache for transcripts so repeat searches skip yt-dlp / Whisper."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict

from supersearch.core import TranscriptEntry

LOG = logging.getLogger(__name__)

_CACHE_DIR = Path(
    os.environ.get("SUPERSEARCH_CACHE_DIR", Path.home() / ".supersearch" / "transcripts")
)


class CachedTranscriptMeta(TypedDict):
    url: str
    source: str
    fetched_at: float
    entry_count: int


def cache_dir() -> Path:
    return _CACHE_DIR


def _cache_file(url: str) -> Path:
    key = hashlib.sha256(url.strip().encode()).hexdigest()[:40]
    return _CACHE_DIR / f"{key}.json"


def load(url: str) -> tuple[list[TranscriptEntry], str, float] | None:
    path = _cache_file(url)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            TranscriptEntry(start=e["start"], end=e["end"], text=e["text"]) for e in data["entries"]
        ]
        return entries, data.get("source", "unknown"), float(data.get("fetched_at", 0))
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        LOG.warning("cache read failed %s: %s", path.name, exc)
        return None


def save(url: str, entries: list[TranscriptEntry], source: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_file(url)
    payload = {
        "url": url.strip(),
        "source": source,
        "fetched_at": time.time(),
        "entries": [asdict(e) for e in entries],
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        LOG.info("cached %d entries for %.60s", len(entries), url)
    except OSError as exc:
        LOG.warning("cache write failed: %s", exc)


def clear(url: str) -> bool:
    path = _cache_file(url)
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True


def list_cached() -> list[CachedTranscriptMeta]:
    if not _CACHE_DIR.is_dir():
        return []
    rows: list[CachedTranscriptMeta] = []
    for path in _CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "url": data.get("url", ""),
                    "source": data.get("source", "unknown"),
                    "fetched_at": float(data.get("fetched_at", 0)),
                    "entry_count": len(data.get("entries") or []),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue
    rows.sort(key=lambda row: row["fetched_at"], reverse=True)
    return rows
