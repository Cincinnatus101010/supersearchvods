"""Backward-compatible re-exports — prefer tests.factory directly."""

from tests.factory import (
    SAMPLE_SRT,
    SAMPLE_VTT,
    TWITCH_CLIP_URL,
    TWITCH_LIVE_URL,
    TWITCH_VOD_URL,
    YOUTUBE_URL,
)

__all__ = [
    "SAMPLE_SRT",
    "SAMPLE_VTT",
    "TWITCH_CLIP_URL",
    "TWITCH_LIVE_URL",
    "TWITCH_VOD_URL",
    "YOUTUBE_URL",
]
