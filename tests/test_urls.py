from __future__ import annotations

import pytest

from supersearch.urls import (
    is_allowed_url,
    is_twitch_clip_url,
    is_twitch_live_url,
    is_twitch_vod_url,
    is_youtube_url,
    twitch_clip_slug,
)
from tests.factory import TWITCH_CLIP_URL, TWITCH_LIVE_URL, TWITCH_VOD_URL, YOUTUBE_URL


class TestYouTubeUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=abc123",
            "https://youtu.be/abc123",
            "https://m.youtube.com/watch?v=abc",
            "https://www.youtube-nocookie.com/embed/abc",
        ],
    )
    def test_allowed(self, url):
        assert is_youtube_url(url)

    @pytest.mark.parametrize(
        "url",
        ["https://example.com/video", "ftp://youtube.com/watch?v=x", ""],
    )
    def test_rejected(self, url):
        assert not is_youtube_url(url)


class TestTwitchUrls:
    def test_vod(self):
        assert is_twitch_vod_url(TWITCH_VOD_URL)
        assert not is_twitch_vod_url(TWITCH_LIVE_URL)

    def test_live_channel(self):
        assert is_twitch_live_url(TWITCH_LIVE_URL)
        assert not is_twitch_live_url("https://www.twitch.tv/videos/1")
        assert not is_twitch_live_url("https://www.twitch.tv/directory")

    def test_clip_slug(self):
        assert twitch_clip_slug(TWITCH_CLIP_URL) == "AwkwardHelplessSalamander"
        assert twitch_clip_slug("https://www.twitch.tv/ninja/clip/CoolClip-abc") == "CoolClip-abc"
        assert is_twitch_clip_url(TWITCH_CLIP_URL)


class TestAllowedUrl:
    def test_combines_sources(self):
        assert is_allowed_url(YOUTUBE_URL)
        assert is_allowed_url(TWITCH_VOD_URL)
        assert is_allowed_url(TWITCH_LIVE_URL)
        assert is_allowed_url(TWITCH_CLIP_URL)

    def test_rejects_unknown(self):
        assert not is_allowed_url("https://vimeo.com/123")
