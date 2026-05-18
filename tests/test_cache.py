"""Tests for the on-disk HTTP cache transport."""

from __future__ import annotations

from pathlib import Path

import httpx

from convene.cache import CachingTransport


def _counted_inner(payloads: list[dict]) -> tuple[httpx.MockTransport, list[int]]:
    """Build an httpx transport that returns each payload in order and counts calls."""
    calls = [0]

    def handler(req):
        calls[0] += 1
        return httpx.Response(200, json=payloads[min(calls[0] - 1, len(payloads) - 1)])

    return httpx.MockTransport(handler), calls


def test_cache_hit_skips_inner(tmp_path: Path):
    inner, calls = _counted_inner([{"k": "v"}])
    cache = CachingTransport(tmp_path, inner=inner)
    client = httpx.Client(transport=cache)

    r1 = client.get("https://example.com/foo")
    r2 = client.get("https://example.com/foo")

    assert r1.json() == r2.json() == {"k": "v"}
    assert calls[0] == 1  # inner transport was only called once


def test_cache_differentiates_by_query(tmp_path: Path):
    inner, calls = _counted_inner([{"page": 1}, {"page": 2}])
    cache = CachingTransport(tmp_path, inner=inner)
    client = httpx.Client(transport=cache)

    client.get("https://example.com/foo", params={"p": 1})
    client.get("https://example.com/foo", params={"p": 2})

    assert calls[0] == 2  # different URLs, different cache entries


def test_cache_skips_non_200(tmp_path: Path):
    def handler(req):
        return httpx.Response(500, text="boom")

    cache = CachingTransport(tmp_path, inner=httpx.MockTransport(handler))
    client = httpx.Client(transport=cache)

    client.get("https://example.com/foo")
    # No file should have been written for a 5xx
    cached_files = list(tmp_path.rglob("*.json"))
    assert cached_files == []


def test_cache_passes_through_non_get(tmp_path: Path):
    posts = [0]

    def handler(req):
        if req.method == "POST":
            posts[0] += 1
        return httpx.Response(200, json={})

    cache = CachingTransport(tmp_path, inner=httpx.MockTransport(handler))
    client = httpx.Client(transport=cache)

    client.post("https://example.com/foo")
    client.post("https://example.com/foo")
    assert posts[0] == 2  # not cached
