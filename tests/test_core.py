from __future__ import annotations

import pytest

from supersearch.core import (
    _parse_captions,
    _ts_to_sec,
    search_transcript,
)
from tests.factory import SAMPLE_SRT, SAMPLE_VTT


class TestTimestampParsing:
    def test_hms(self):
        assert _ts_to_sec("01:02:03.5") == pytest.approx(3723.5)

    def test_ms(self):
        assert _ts_to_sec("01:30,250") == pytest.approx(90.25)

    def test_invalid_returns_zero(self):
        assert _ts_to_sec("not-a-time") == 0.0


class TestCaptionParsing:
    def test_parse_vtt(self):
        entries = _parse_captions(SAMPLE_VTT, "vtt")
        assert len(entries) == 3
        assert entries[0].start == pytest.approx(1.0)
        assert entries[0].end == pytest.approx(4.0)
        assert "Hello" in entries[0].text
        assert "<c>" not in entries[0].text
        assert "funny moment" in entries[1].text.lower()

    def test_parse_srt(self):
        entries = _parse_captions(SAMPLE_SRT, "srt")
        assert len(entries) == 2
        assert entries[1].text == "funny moment returns again"


class TestSearchTranscript:
    def test_finds_matching_windows(self, sample_entries):
        hits = search_transcript(sample_entries, "funny moment", n=3, window_sec=30.0)
        assert len(hits) >= 1
        assert all(h.score > 0 for h in hits)
        assert hits[0].score >= hits[-1].score

    def test_clip_buffers_applied(self, sample_entries):
        hits = search_transcript(
            sample_entries,
            "funny moment",
            n=1,
            clip_buffer_before=5.0,
            clip_buffer_after=10.0,
        )
        assert len(hits) == 1
        assert hits[0].start >= 0.0
        assert hits[0].context

    def test_empty_query_returns_empty(self, sample_entries):
        assert search_transcript(sample_entries, "") == []
        assert search_transcript(sample_entries, "   ") == []

    def test_empty_entries_returns_empty(self):
        assert search_transcript([], "funny") == []

    def test_phrase_bonus_ranks_higher(self, make: type):
        hits = search_transcript(make.phrase_match_entries(), "funny moment", n=1, window_sec=30.0, step_sec=15.0)
        assert len(hits) == 1
        assert "funny moment" in hits[0].text.lower()

    def test_respects_n_limit(self, sample_entries):
        hits = search_transcript(sample_entries, "moment", n=1)
        assert len(hits) == 1
