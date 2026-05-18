"""Tests against frozen fixtures of real Legistar API responses."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from convene.adapters import LegistarAdapter
from convene.adapters.legistar import LegistarError
from convene.registry import get as get_jurisdiction

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def philly():
    return get_jurisdiction("philly")


@pytest.fixture
def seattle():
    return get_jurisdiction("seattle")


@pytest.fixture
def sf():
    return get_jurisdiction("sf")


@pytest.fixture
def nyc():
    return get_jurisdiction("nyc")


@pytest.fixture
def mock_transport():
    """Map of (method, url) -> JSON body. Tests register fixtures into this."""
    routes: dict[tuple[str, str], object] = {}
    statuses: dict[tuple[str, str], int] = {}
    text_responses: dict[tuple[str, str], str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        key = (req.method, str(req.url))
        if key in text_responses:
            return httpx.Response(statuses.get(key, 200), text=text_responses[key])
        body = routes.get(key)
        if body is None:
            return httpx.Response(200, json=[])
        return httpx.Response(statuses.get(key, 200), json=body)

    return routes, statuses, text_responses, httpx.MockTransport(handler)


# ----- events / items


def test_events_normalize(philly, mock_transport):
    routes, _, _, transport = mock_transport
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
    assert e.start_date.hour == 14
    assert e.location
    assert e.sources[0].url.startswith("https://phila.legistar.com/")


def test_events_with_items(philly, mock_transport):
    routes, _, _, transport = mock_transport
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
        events = list(adapter.events(include_items=True))

    e = next(e for e in events if e.id.endswith("-6376"))
    assert e.items
    orders = [i.order for i in e.items]
    assert orders == sorted(orders)
    typed = [i for i in e.items if i.matter_type]
    assert typed
    assert typed[0].matter_type in {"Bill", "Resolution", "Communication"}


def test_events_since_modified_filter(philly, mock_transport):
    """`--since-modified` should add an EventLastModifiedUtc filter."""
    routes, _, _, transport = mock_transport
    expected_url = (
        "https://webapi.legistar.com/v1/phila/events"
        "?%24orderby=EventDate+desc"
        "&%24filter=EventLastModifiedUtc+ge+datetime%272026-05-10T00%3A00%3A00%27"
        "&%24top=1000&%24skip=0"
    )
    routes["GET", expected_url] = _load("phila_events.json")

    with httpx.Client(transport=transport) as http:
        adapter = LegistarAdapter(philly, client=http)
        events = list(adapter.events(since_modified=datetime(2026, 5, 10)))

    # If the filter URL was constructed differently, mock_transport returns []
    assert events, "since_modified didn't construct the expected URL"


def test_events_with_votes(seattle, mock_transport):
    routes, _, _, transport = mock_transport
    # Pretend Seattle has one event whose first item has roll-call votes
    routes[
        "GET",
        "https://webapi.legistar.com/v1/seattle/events?%24orderby=EventDate+desc&%24top=1000&%24skip=0"
    ] = [{
        "EventId": 6709,
        "EventGuid": "x",
        "EventBodyId": 1,
        "EventBodyName": "City Council",
        "EventDate": "2026-05-12T00:00:00",
        "EventTime": "2:00 PM",
        "EventAgendaStatusName": "Final",
        "EventMinutesStatusName": "Final",
        "EventInSiteURL": "https://seattle.legistar.com/MeetingDetail.aspx?LEGID=6709",
        "EventLocation": "City Hall",
    }]
    routes[
        "GET",
        "https://webapi.legistar.com/v1/seattle/events/6709/eventitems"
    ] = [{
        "EventItemId": 123047,
        "EventItemAgendaSequence": 1,
        "EventItemTitle": "Approval of CB 121234",
        "EventItemRollCallFlag": 0,
    }]
    routes[
        "GET",
        "https://webapi.legistar.com/v1/seattle/eventitems/123047/votes"
    ] = _load("seattle_votes_123047.json")

    with httpx.Client(transport=transport) as http:
        adapter = LegistarAdapter(seattle, client=http)
        events = list(adapter.events(include_items=True, include_votes=True))

    assert len(events) == 1
    item = events[0].items[0]
    assert len(item.votes) == 5
    # All votes in the fixture are "In Favor"
    assert all(v.option == "yes" for v in item.votes)
    assert all(v.raw_value == "In Favor" for v in item.votes)


def test_skip_endpoints_blocks_events(sf):
    # Without hitting the network, the adapter should refuse SF's /events
    adapter = LegistarAdapter(sf, client=httpx.Client(transport=httpx.MockTransport(
        lambda _r: httpx.Response(200, json=[])
    )))
    with pytest.raises(LegistarError, match="doesn't expose /events"):
        list(adapter.events())


# ----- bodies / people


def test_organizations(philly, mock_transport):
    routes, _, _, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/bodies?%24top=1000&%24skip=0"
    ] = _load("phila_bodies.json")

    with httpx.Client(transport=transport) as http:
        orgs = list(LegistarAdapter(philly, client=http).organizations())

    fixture = _load("phila_bodies.json")
    expected_active = sum(1 for b in fixture if b.get("BodyActiveFlag"))
    assert len(orgs) == expected_active
    for org in orgs:
        assert org.id.startswith("ocd-organization/phila-")
        assert org.name


def test_people(philly, mock_transport):
    routes, _, _, transport = mock_transport
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


# ----- matters / sponsors


def test_matters_normalize(philly, mock_transport):
    routes, _, _, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/matters?%24orderby=MatterIntroDate+desc&%24top=1000&%24skip=0"
    ] = _load("phila_matters.json")

    with httpx.Client(transport=transport) as http:
        matters = list(LegistarAdapter(philly, client=http).matters())

    assert len(matters) == 1
    m = matters[0]
    assert m.id == "ocd-bill/phila-27257"
    assert m.identifier == "260506"
    assert m.classification
    assert m.introduced_date == date(2026, 5, 14)
    assert m.title  # might be long or short, just not empty


def test_matters_with_sponsors(philly, mock_transport):
    routes, _, _, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/matters?%24orderby=MatterIntroDate+desc&%24top=1000&%24skip=0"
    ] = _load("phila_matters.json")
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/matters/27257/sponsors"
    ] = _load("phila_matter_27257_sponsors.json")

    with httpx.Client(transport=transport) as http:
        matters = list(LegistarAdapter(philly, client=http).matters(include_sponsors=True))

    assert len(matters) == 1
    m = matters[0]
    assert m.sponsors
    fixture = _load("phila_matter_27257_sponsors.json")
    assert len(m.sponsors) == len(fixture)


def test_matters_with_history(philly, mock_transport):
    routes, _, _, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/matters?%24orderby=MatterIntroDate+desc&%24top=1000&%24skip=0"
    ] = _load("phila_matters.json")
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/matters/27257/histories"
    ] = _load("phila_matter_27257_histories.json")

    with httpx.Client(transport=transport) as http:
        matters = list(LegistarAdapter(philly, client=http).matters(include_history=True))

    assert len(matters) == 1
    m = matters[0]
    assert m.actions
    action = m.actions[0]
    assert action.action  # e.g. "Introduced and Referred"
    assert action.body  # the originating body
    assert action.event_id and action.event_id.startswith("ocd-event/phila-")


def test_memberships(philly, mock_transport):
    routes, _, _, transport = mock_transport
    routes[
        "GET",
        "https://webapi.legistar.com/v1/phila/persons/2/officerecords"
    ] = _load("phila_person_2_officerecords.json")

    with httpx.Client(transport=transport) as http:
        memberships = list(LegistarAdapter(philly, client=http).memberships(2))

    assert memberships
    m = memberships[0]
    assert m.person_id == "ocd-person/phila-2"
    assert m.organization_name
    assert m.start_date  # the fixture entries all have date ranges


# ----- error handling


def test_400_includes_body_text(philly, mock_transport):
    routes, statuses, text_responses, transport = mock_transport
    url = "https://webapi.legistar.com/v1/phila/events?%24orderby=EventDate+desc&%24top=1000&%24skip=0"
    statuses["GET", url] = 400
    text_responses["GET", url] = "'Agenda Status' is not setup in settings."

    with httpx.Client(transport=transport) as http:
        adapter = LegistarAdapter(philly, client=http)
        with pytest.raises(LegistarError, match="not setup in settings"):
            list(adapter.events())


def test_403_hints_at_token(nyc, mock_transport):
    routes, statuses, _, transport = mock_transport
    url = "https://webapi.legistar.com/v1/nyc/events?%24orderby=EventDate+desc&%24top=1000&%24skip=0"
    statuses["GET", url] = 403
    routes["GET", url] = []  # mock_transport defaults to json body

    with httpx.Client(transport=transport) as http:
        adapter = LegistarAdapter(nyc, client=http)
        with pytest.raises(LegistarError, match="--token") as exc:
            list(adapter.events())
        assert "403" in str(exc.value)


def test_500_explains_legistar_config():
    """500 from a city we know works usually means tenant config is broken."""
    j = get_jurisdiction("boston")

    def handler(req):
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http:
        adapter = LegistarAdapter(j, client=http)
        with pytest.raises(LegistarError, match="per-tenant config"):
            list(adapter.events())


# ----- helpers


def test_unknown_jurisdiction():
    with pytest.raises(KeyError):
        get_jurisdiction("portland-but-not-really")


def test_time_parsing_edge_cases():
    from convene.adapters.legistar import _parse_meeting_start

    base = "2026-06-01T00:00:00"
    assert _parse_meeting_start(base, "2:00 PM").hour == 14
    assert _parse_meeting_start(base, "9 AM").hour == 9
    assert _parse_meeting_start(base, "13:00").hour == 13
    assert _parse_meeting_start(base, "TBD").hour == 0
    assert _parse_meeting_start(base, None).hour == 0


def test_vote_normalization():
    from convene.adapters.legistar import _normalize_vote

    assert _normalize_vote("In Favor") == "yes"
    assert _normalize_vote("Yea") == "yes"
    assert _normalize_vote("Aye") == "yes"
    assert _normalize_vote("Against") == "no"
    assert _normalize_vote("Nay") == "no"
    assert _normalize_vote("Excused") == "absent"
    assert _normalize_vote("Not Present") == "absent"
    assert _normalize_vote("Abstain") == "abstain"
    assert _normalize_vote("Maybe") == "other"
    assert _normalize_vote("") == "other"


def test_body_classification():
    from convene.adapters.legistar import _body_classification

    assert _body_classification("City Council") == "legislature"
    assert _body_classification("Standing Committee") == "committee"
    assert _body_classification("Office of the Mayor") == "department"
    assert _body_classification(None) is None
    assert _body_classification("Unknown Type") is None
