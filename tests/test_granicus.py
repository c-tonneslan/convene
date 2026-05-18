"""Tests for the Granicus HTML scraper against a frozen fixture."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from convene.adapters import GranicusAdapter
from convene.adapters.granicus import (
    GranicusError,
    _parse_aired_date,
    _split_body_and_date,
)
from convene.registry import get as get_jurisdiction

FIXTURE = (Path(__file__).parent / "fixtures" / "stpaul_view_37.html").read_text()


@pytest.fixture
def stpaul():
    return get_jurisdiction("stpaul")


@pytest.fixture
def mock_transport():
    """Returns the fixture HTML for the expected URL, 404 for others."""
    routes: dict[str, tuple[int, str]] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        key = str(req.url)
        if key in routes:
            status, body = routes[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    return routes, httpx.MockTransport(handler)


def test_events_parsed_from_fixture(stpaul, mock_transport):
    routes, transport = mock_transport
    routes["https://stpaul.granicus.com/ViewPublisher.php?view_id=37"] = (200, FIXTURE)

    with httpx.Client(transport=transport) as http:
        events = list(GranicusAdapter(stpaul, client=http).events())

    assert events, "expected at least one event from the fixture"
    e = events[0]
    assert e.jurisdiction == "stpaul"
    assert e.id.startswith("ocd-event/stpaul-37-")
    assert e.name  # non-empty body name
    assert e.start_date.year == 2026
    assert e.status == "passed"


def test_events_filtered_by_date(stpaul, mock_transport):
    routes, transport = mock_transport
    routes["https://stpaul.granicus.com/ViewPublisher.php?view_id=37"] = (200, FIXTURE)

    with httpx.Client(transport=transport) as http:
        adapter = GranicusAdapter(stpaul, client=http)
        all_events = list(adapter.events())
        narrow = list(adapter.events(since=date(2026, 5, 13), until=date(2026, 5, 13)))

    assert 0 < len(narrow) <= len(all_events)
    assert all(e.start_date.date() == date(2026, 5, 13) for e in narrow)


def test_events_include_video_and_agenda_links(stpaul, mock_transport):
    routes, transport = mock_transport
    routes["https://stpaul.granicus.com/ViewPublisher.php?view_id=37"] = (200, FIXTURE)

    with httpx.Client(transport=transport) as http:
        events = list(GranicusAdapter(stpaul, client=http).events())

    with_links = [e for e in events if e.agenda_url and e.video_url]
    assert with_links, "expected at least one event with both agenda and video links"
    e = with_links[0]
    assert e.agenda_url.startswith("https://stpaul.granicus.com/AgendaViewer.php?")
    assert e.video_url.startswith("https://stpaul.granicus.com/MediaPlayer.php?")


def test_404_raises(stpaul, mock_transport):
    routes, transport = mock_transport
    # Don't register the URL; the handler returns 404.
    with httpx.Client(transport=transport) as http:
        adapter = GranicusAdapter(stpaul, client=http)
        with pytest.raises(GranicusError, match="returned 404"):
            list(adapter.events())


def test_missing_archive_table_yields_nothing(stpaul, mock_transport):
    """A view with no archived meetings should just yield no events."""
    routes, transport = mock_transport
    routes["https://stpaul.granicus.com/ViewPublisher.php?view_id=37"] = (
        200, "<html><body><p>No meetings yet</p></body></html>"
    )

    with httpx.Client(transport=transport) as http:
        events = list(GranicusAdapter(stpaul, client=http).events())
    assert events == []


def test_rejects_non_granicus_jurisdiction():
    j = get_jurisdiction("philly")
    with pytest.raises(ValueError, match="not a Granicus"):
        GranicusAdapter(j)


def test_helpers():
    # Body + date splitter
    body, dt = _split_body_and_date("City Council on 2026-05-13 2:00 PM")
    assert body == "City Council"
    assert dt and dt.hour == 14

    body, dt = _split_body_and_date("Housing & Redevelopment Authority on 2026-05-13")
    assert body == "Housing & Redevelopment Authority"
    assert dt and dt.day == 13

    body, dt = _split_body_and_date("Weird unparseable string")
    assert body == "Weird unparseable string"
    assert dt is None

    # Aired-date parser
    assert _parse_aired_date("May 13, 2026 - 01:57 PM").hour == 13
    assert _parse_aired_date("May 13, 2026").day == 13
    assert _parse_aired_date("garbage") is None
    assert _parse_aired_date("-") is None
