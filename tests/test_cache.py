from __future__ import annotations

from supersearch.cache import cache_dir as get_cache_dir
from supersearch.cache import clear, list_cached, load, save
from tests.factory import YOUTUBE_URL


class TestTranscriptCache:
    def test_save_and_load(self, transcript_cache_dir, sample_entries):
        save(YOUTUBE_URL, sample_entries, "captions")
        loaded = load(YOUTUBE_URL)
        assert loaded is not None
        entries, source, fetched_at = loaded
        assert source == "captions"
        assert fetched_at > 0
        assert len(entries) == len(sample_entries)
        assert entries[0].text == sample_entries[0].text

    def test_load_miss(self, transcript_cache_dir):
        assert load("https://www.youtube.com/watch?v=nonexistent") is None

    def test_clear_existing(self, transcript_cache_dir, sample_entries):
        save(YOUTUBE_URL, sample_entries, "captions")
        assert clear(YOUTUBE_URL) is True
        assert load(YOUTUBE_URL) is None

    def test_clear_missing(self, transcript_cache_dir):
        assert clear(YOUTUBE_URL) is False

    def test_list_cached_newest_first(self, transcript_cache_dir, sample_entries):
        save(YOUTUBE_URL, sample_entries, "captions")
        rows = list_cached()
        assert len(rows) == 1
        assert rows[0]["url"] == YOUTUBE_URL
        assert rows[0]["entry_count"] == len(sample_entries)
        assert get_cache_dir() == transcript_cache_dir
