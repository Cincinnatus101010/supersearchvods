from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from supersearch.api import app
from tests.factory import YOUTUBE_URL


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestSuperSearchEndpoint:
    def test_requires_json_body(self, client):
        r = client.post("/api/super-search", content="not json")
        assert r.status_code == 400

    def test_requires_url(self, client):
        r = client.post("/api/super-search", json={"query": "test"})
        assert r.status_code == 400
        assert "url" in r.json()["detail"].lower()

    def test_requires_query(self, client):
        r = client.post("/api/super-search", json={"url": YOUTUBE_URL})
        assert r.status_code == 400
        assert "query" in r.json()["detail"].lower()

    def test_rejects_invalid_url(self, client):
        r = client.post(
            "/api/super-search",
            json={"url": "https://vimeo.com/1", "query": "test"},
        )
        assert r.status_code == 400


class TestCacheEndpoint:
    def test_clear_requires_url(self, client):
        r = client.request("DELETE", "/api/super-search/cache", json={})
        assert r.status_code == 400

    def test_clear_returns_cleared_flag(self, client, transcript_cache_dir, sample_entries):
        from supersearch.cache import save

        save(YOUTUBE_URL, sample_entries, "captions")
        r = client.request("DELETE", "/api/super-search/cache", json={"url": YOUTUBE_URL})
        assert r.status_code == 200
        assert r.json()["cleared"] is True
