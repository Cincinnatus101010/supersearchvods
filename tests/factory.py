"""Test data factories for supersearch."""

from __future__ import annotations

from typing import Any

from supersearch.core import SearchResult, TranscriptEntry

YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
TWITCH_VOD_URL = "https://www.twitch.tv/videos/1234567890"
TWITCH_LIVE_URL = "https://www.twitch.tv/shroud"
TWITCH_CLIP_URL = "https://clips.twitch.tv/AwkwardHelplessSalamander"

SAMPLE_VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello <c>world</c>

00:00:05.000 --> 00:00:08.000
This is a funny moment in the stream

00:01:30.000 --> 00:01:35.000
Nothing relevant here
"""

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:04,000
Hello world

2
00:00:05,000 --> 00:00:08,000
funny moment returns again
"""


def transcript_entry(
    start: float = 0.0,
    end: float = 5.0,
    text: str = "hello world intro",
) -> TranscriptEntry:
    return TranscriptEntry(start=start, end=end, text=text)


def search_result(
    *,
    start: float = 0.0,
    end: float = 10.0,
    text: str = "funny moment in the stream",
    score: float = 0.85,
    context: str = "funny moment",
) -> SearchResult:
    return SearchResult(start=start, end=end, text=text, score=score, context=context)


def search_hit_dict(**overrides: Any) -> dict[str, Any]:
    """Dict shape returned by run_super_search results."""
    defaults: dict[str, Any] = {
        "start": 0.0,
        "end": 10.0,
        "text": "funny moment",
        "score": 0.85,
        "context": "funny moment",
    }
    defaults.update(overrides)
    return defaults


def super_search_result(**overrides: Any) -> dict[str, Any]:
    """Full run_super_search response payload."""
    defaults: dict[str, Any] = {
        "phase": "result",
        "results": [search_hit_dict()],
        "warning": None,
        "whisper_used": False,
        "cached": False,
        "cached_at": None,
    }
    defaults.update(overrides)
    return defaults


def progress_event(phase: str = "captions", **extra: Any) -> dict[str, Any]:
    event: dict[str, Any] = {"phase": phase}
    event.update(extra)
    return event


def default_entries() -> list[TranscriptEntry]:
    """Standard transcript used across search/cache tests."""
    return [
        transcript_entry(0.0, 5.0, "hello world intro"),
        transcript_entry(5.0, 10.0, "this funny moment is great"),
        transcript_entry(30.0, 35.0, "unrelated chatter about weather"),
        transcript_entry(60.0, 65.0, "another funny moment at the end"),
    ]


def phrase_match_entries() -> list[TranscriptEntry]:
    """Two windows for testing phrase ranking."""
    return [
        transcript_entry(0.0, 10.0, "we talked about cats and dogs"),
        transcript_entry(15.0, 25.0, "the funny moment everyone remembers"),
    ]
