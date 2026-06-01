"""YouTube and Twitch URL validation."""

from __future__ import annotations

import re
from urllib.parse import ParseResult, urlparse

_RESERVED_TWITCH = frozenset(
    {
        "videos",
        "clips",
        "clip",
        "directory",
        "downloads",
        "settings",
        "p",
        "search",
        "subscriptions",
        "wallet",
        "products",
        "turbo",
    }
)

_TWITCH_CLIP_SLUG = re.compile(r"[A-Za-z0-9_-]{4,200}")

INVALID_URL_MSG = (
    "URL must be a YouTube video, Twitch VOD (twitch.tv/videos/…), "
    "Twitch clip, or Twitch channel (twitch.tv/ChannelName)."
)


def _parse_http(url: str) -> ParseResult | None:
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    return p


def is_youtube_url(url: str) -> bool:
    p = _parse_http(url)
    if not p:
        return False
    h = p.hostname.lower()
    return (
        h == "youtu.be"
        or h == "youtube.com"
        or h.endswith(".youtube.com")
        or h.endswith(".youtube-nocookie.com")
    )


def is_twitch_vod_url(url: str) -> bool:
    p = _parse_http(url)
    if not p or not p.hostname.lower().endswith("twitch.tv"):
        return False
    path = (p.path or "").lower()
    return "/videos/" in path or bool(re.search(r"videos/\d+", path))


def is_twitch_live_url(url: str) -> bool:
    p = _parse_http(url)
    if not p or not p.hostname.lower().endswith("twitch.tv"):
        return False
    path = (p.path or "").strip("/")
    if not path:
        return False
    parts = path.split("/")
    if len(parts) != 1:
        return False
    slug = parts[0]
    return slug.lower() not in _RESERVED_TWITCH and bool(re.fullmatch(r"[A-Za-z0-9_]{2,65}", slug))


def twitch_clip_slug(url: str) -> str | None:
    p = _parse_http(url)
    if not p:
        return None
    host = p.hostname.lower()
    parts = [seg for seg in (p.path or "").split("/") if seg]
    if host == "clips.twitch.tv":
        slug = parts[0] if parts else None
    elif host == "twitch.tv" or host.endswith(".twitch.tv"):
        if len(parts) == 3 and parts[1] == "clip":
            slug = parts[2]
        elif len(parts) == 2 and parts[0] == "clip":
            slug = parts[1]
        else:
            return None
    else:
        return None
    return slug if slug and _TWITCH_CLIP_SLUG.fullmatch(slug) else None


def is_twitch_clip_url(url: str) -> bool:
    return twitch_clip_slug(url) is not None


def is_twitch_url(url: str) -> bool:
    return is_twitch_vod_url(url) or is_twitch_live_url(url) or is_twitch_clip_url(url)


def is_allowed_url(url: str) -> bool:
    return is_youtube_url(url) or is_twitch_url(url)
