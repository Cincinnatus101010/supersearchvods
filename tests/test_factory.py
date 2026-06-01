from __future__ import annotations

from tests import factory


def test_transcript_entry_factory() -> None:
    entry = factory.transcript_entry(start=1.0, end=2.0, text="test clip")
    assert entry.start == 1.0
    assert entry.text == "test clip"


def test_default_entries_count() -> None:
    assert len(factory.default_entries()) == 4


def test_super_search_result_shape() -> None:
    result = factory.super_search_result(cached=True)
    assert result["phase"] == "result"
    assert result["cached"] is True
    assert len(result["results"]) == 1
