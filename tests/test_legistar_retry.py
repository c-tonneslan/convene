"""Retry behavior for the Legistar adapter.

Legistar rate-limits aggressively and 502s under load; the adapter retries
429/5xx with exponential backoff and honors Retry-After. These tests pin
the contract.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from convene.adapters import LegistarAdapter
from convene.adapters import legistar as legistar_mod
from convene.adapters.legistar import LegistarError
from convene.registry import get as get_jurisdiction


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Avoid waiting real seconds in unit tests."""
    monkeypatch.setattr(legistar_mod.time, "sleep", lambda _seconds: None)


@pytest.fixture
def philly():
    return get_jurisdiction("philly")


def _adapter(j, handler):
    return LegistarAdapter(j, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_retries_on_429_then_succeeds(philly):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"msg": "slow down"})
        return httpx.Response(200, json=[])

    adapter = _adapter(philly, handler)
    assert list(adapter.events()) == []
    assert calls["n"] == 3


def test_retries_on_5xx_then_gives_up(philly):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(502, text="bad gateway")

    adapter = _adapter(philly, handler)
    with pytest.raises(LegistarError) as exc:
        list(adapter.events())
    # The default MAX_RETRIES is 3, so 1 initial + 3 retries = 4 attempts.
    assert calls["n"] == legistar_mod.MAX_RETRIES + 1
    assert "502" in str(exc.value)


def test_does_not_retry_400(philly):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text='"Status Not Vievable in the API"')

    adapter = _adapter(philly, handler)
    with pytest.raises(LegistarError) as exc:
        list(adapter.events())
    assert calls["n"] == 1
    assert "Status Not Vievable" in str(exc.value)


def test_retries_on_network_error_then_succeeds(philly, monkeypatch):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("connection reset", request=req)
        return httpx.Response(200, json=[])

    adapter = _adapter(philly, handler)
    assert list(adapter.events()) == []
    assert calls["n"] == 2


def test_retry_delay_honors_retry_after_seconds():
    resp = httpx.Response(429, headers={"Retry-After": "5"})
    assert legistar_mod._retry_delay(resp, attempt=0) == 5.0


def test_retry_delay_falls_back_to_exponential():
    resp = httpx.Response(503)
    assert legistar_mod._retry_delay(resp, attempt=0) == legistar_mod.RETRY_BASE
    assert legistar_mod._retry_delay(resp, attempt=1) == legistar_mod.RETRY_BASE * 2
    assert legistar_mod._retry_delay(resp, attempt=2) == legistar_mod.RETRY_BASE * 4
