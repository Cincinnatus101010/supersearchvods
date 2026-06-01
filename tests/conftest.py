from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests import factory


@pytest.fixture
def make() -> type[factory]:
    return factory


@pytest.fixture
def sample_entries() -> list:
    return factory.default_entries()


@pytest.fixture
def transcript_cache_dir(tmp_path, monkeypatch) -> Iterator:
    path = tmp_path / "transcripts"
    monkeypatch.setenv("SUPERSEARCH_CACHE_DIR", str(path))
    import supersearch.cache as cache_mod

    monkeypatch.setattr(cache_mod, "_CACHE_DIR", path)
    return path
