from __future__ import annotations

from unittest.mock import patch

import pytest

from supersearch.service import run_super_search
from tests.factory import TWITCH_VOD_URL, YOUTUBE_URL


class TestRunSuperSearch:
    def test_requires_url(self):
        with pytest.raises(ValueError, match="url"):
            run_super_search("", "query")

    def test_requires_query(self):
        with pytest.raises(ValueError, match="query"):
            run_super_search(YOUTUBE_URL, "")

    def test_rejects_invalid_url(self):
        with pytest.raises(ValueError, match="URL must"):
            run_super_search("https://vimeo.com/1", "test")

    def test_uses_cache(self, transcript_cache_dir, sample_entries):
        from supersearch.cache import save

        save(YOUTUBE_URL, sample_entries, "captions")
        events: list[dict] = []

        result = run_super_search(
            YOUTUBE_URL,
            "funny moment",
            on_progress=events.append,
        )

        assert result["phase"] == "result"
        assert result["cached"] is True
        assert len(result["results"]) >= 1
        assert any(e.get("phase") == "cache" for e in events)

    @patch("supersearch.service.fetch_transcript")
    def test_fetches_captions_on_miss(self, mock_fetch, transcript_cache_dir, sample_entries):
        mock_fetch.return_value = sample_entries
        events: list[dict] = []

        result = run_super_search(
            YOUTUBE_URL,
            "funny moment",
            on_progress=events.append,
        )

        mock_fetch.assert_called_once_with(YOUTUBE_URL)
        assert result["cached"] is False
        assert result["whisper_used"] is False
        assert len(result["results"]) >= 1
        assert any(e.get("phase") == "captions" for e in events)

    @patch("supersearch.service.whisper_transcribe")
    def test_twitch_enables_whisper(self, mock_whisper, transcript_cache_dir, sample_entries):
        mock_whisper.return_value = sample_entries

        result = run_super_search(TWITCH_VOD_URL, "boss fight")

        mock_whisper.assert_called_once()
        assert mock_whisper.call_args.args[0] == TWITCH_VOD_URL
        assert result["whisper_used"] is True

    @patch("supersearch.service.fetch_transcript", return_value=[])
    def test_empty_transcript_warning(self, _mock_fetch, transcript_cache_dir):
        result = run_super_search(YOUTUBE_URL, "anything")

        assert result["results"] == []
        assert result["warning"]

    def test_clamps_n(self, transcript_cache_dir, sample_entries):
        from supersearch.cache import save

        save(YOUTUBE_URL, sample_entries, "captions")
        result = run_super_search(YOUTUBE_URL, "moment", n=100)
        assert len(result["results"]) <= 20
