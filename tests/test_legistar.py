"""Tests against frozen fixtures of real Legistar API responses."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from convene.adapters import LegistarAdapter
from convene.registry import get as get_jurisdiction

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def philly():
    return get_jurisdiction("philly")


@pytest.fixture
def mock_transport():
    """Map of (method, url, query) -> JSON body. Tests register fixtures into this."""
    routes: dict[tuple[str, str], object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        body = routes.get((req.method, str(req.url)))
        if body is None:
            # Empty response = end of paginated stream
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=body)

    return routes, httpx.MockTransport(handler)


def test_events_normalize(philly, mock_transport):
    routes, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/events?%24orderby=EventDate+desc&%24top=1000&%24skip=0"
    ] = _load("phila_events.json")

    with httpx.Client(transport=transport) as http:
        adapter = LegistarAdapter(philly, client=http)
        events = list(adapter.events())

    assert len(events) == 3
    e = events[0]
    assert e.jurisdiction == "philly"
    assert e.id.startswith("ocd-event/phila-")
    assert e.organization_name
    # Real data, time should be parsed from "2:00 PM"
    assert e.start_date.hour == 14
    assert e.location
    assert e.sources[0].url.startswith("https://phila.legistar.com/")


def test_events_with_items(philly, mock_transport):
    routes, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/events?%24orderby=EventDate+desc&%24top=1000&%24skip=0"
    ] = _load("phila_events.json")
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/events/6376/eventitems"
    ] = _load("phila_event_6376_items.json")

    with httpx.Client(transport=transport) as http:
        adapter = LegistarAdapter(philly, client=http)
        # Only the first event will have items registered; the others get
        # empty responses, which is fine for this test.
        events = list(adapter.events(include_items=True))

    e = next(e for e in events if e.id.endswith("-6376"))
    assert e.items
    # Items should be sorted by EventItemAgendaSequence
    orders = [i.order for i in e.items]
    assert orders == sorted(orders)
    # At least one item should carry a matter type through from Legistar
    typed = [i for i in e.items if i.matter_type]
    assert typed
    assert typed[0].matter_type in {"Bill", "Resolution", "Communication"}


def test_organizations(philly, mock_transport):
    routes, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/bodies?%24top=1000&%24skip=0"
    ] = _load("phila_bodies.json")

    with httpx.Client(transport=transport) as http:
        orgs = list(LegistarAdapter(philly, client=http).organizations())

    # Inactive bodies should be filtered out
    fixture = _load("phila_bodies.json")
    expected_active = sum(1 for b in fixture if b.get("BodyActiveFlag"))
    assert len(orgs) == expected_active

    for org in orgs:
        assert org.id.startswith("ocd-organization/phila-")
        assert org.name


def test_people(philly, mock_transport):
    routes, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/persons?%24top=1000&%24skip=0"
    ] = _load("phila_persons.json")

    with httpx.Client(transport=transport) as http:
        people = list(LegistarAdapter(philly, client=http).people())

    fixture = _load("phila_persons.json")
    expected_active = sum(1 for p in fixture if p.get("PersonActiveFlag") == 1)
    assert len(people) == expected_active

    miller = next(p for p in people if p.family_name == "Miller")
    assert miller.email == "donna.miller@phila.gov"


def test_unknown_jurisdiction():
    with pytest.raises(KeyError):
        get_jurisdiction("portland-but-not-really")


def test_time_parsing_edge_cases():
    """EventTime in the wild shows up as '2:00 PM', '9 AM', occasionally '13:00'."""
    from convene.adapters.legistar import _parse_meeting_start

    base = "2026-06-01T00:00:00"
    assert _parse_meeting_start(base, "2:00 PM").hour == 14
    assert _parse_meeting_start(base, "9 AM").hour == 9
    assert _parse_meeting_start(base, "13:00").hour == 13
    # Unparseable falls back to bare date
    assert _parse_meeting_start(base, "TBD").hour == 0
    assert _parse_meeting_start(base, None).hour == 0
