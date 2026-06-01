from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import patch

import pytest

from supersearch.cli import (
    _format_time,
    _normalize_argv,
    _youtube_timestamp_url,
    cmd_cache_clear,
    cmd_cache_list,
    cmd_search,
    main,
)
from tests.factory import YOUTUBE_URL


class TestCliHelpers:
    def test_format_time(self):
        assert _format_time(65) == "1:05"
        assert _format_time(3661) == "1:01:01"

    def test_youtube_timestamp_watch(self):
        url = "https://www.youtube.com/watch?v=abc123"
        link = _youtube_timestamp_url(url, 90)
        assert link is not None
        assert "t=90" in link
        assert "v=abc123" in link

    def test_youtube_timestamp_short(self):
        link = _youtube_timestamp_url("https://youtu.be/abc123", 42)
        assert link == "https://youtu.be/abc123?t=42"

    def test_youtube_timestamp_non_youtube(self):
        assert _youtube_timestamp_url("https://twitch.tv/videos/1", 10) is None

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["search", "https://youtu.be/x", "hello"], ["search", "https://youtu.be/x", "hello"]),
            (["https://youtu.be/x", "hello"], ["search", "https://youtu.be/x", "hello"]),
            (["cache", "list"], ["cache", "list"]),
            (["--help"], ["--help"]),
        ],
    )
    def test_normalize_argv(self, argv, expected):
        assert _normalize_argv(argv) == expected


class TestCmdSearch:
    def test_json_output(self, capsys, make: type):
        fake_result = make.super_search_result(
            results=[make.search_hit_dict(start=0, end=10, score=0.9, context="hi", text="hi")]
        )
        args = Namespace(
            url=YOUTUBE_URL,
            query="test",
            url_flag=None,
            query_flag=None,
            n=8,
            whisper=False,
            refresh=False,
            window_sec=30.0,
            clip_before=3.0,
            clip_after=5.0,
            json=True,
            quiet=True,
            verbose=False,
        )
        with patch("supersearch.service.run_super_search", return_value=fake_result):
            assert cmd_search(args) == 0
        out = capsys.readouterr().out
        assert json.loads(out)["phase"] == "result"

    def test_missing_url_exits(self):
        args = Namespace(
            url=None,
            query="q",
            url_flag=None,
            query_flag=None,
            n=8,
            whisper=False,
            refresh=False,
            window_sec=30.0,
            clip_before=3.0,
            clip_after=5.0,
            json=False,
            quiet=True,
            verbose=False,
        )
        with pytest.raises(SystemExit):
            cmd_search(args)


class TestCmdCache:
    def test_clear_hit(self, transcript_cache_dir, sample_entries):
        from supersearch.cache import save

        save(YOUTUBE_URL, sample_entries, "captions")
        args = Namespace(url=YOUTUBE_URL)
        assert cmd_cache_clear(args) == 0

    def test_list_empty(self, transcript_cache_dir, capsys):
        assert cmd_cache_list(Namespace()) == 0
        assert "empty" in capsys.readouterr().out.lower()


class TestMain:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
