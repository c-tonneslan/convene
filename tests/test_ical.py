from __future__ import annotations

from datetime import datetime

from convene.ical import to_ics
from convene.models import Event, Source


def _event(**overrides) -> Event:
    base = dict(
        id="ocd-event/phila-1",
        jurisdiction="philly",
        name="Committee on Rules",
        organization_name="Committee on Rules",
        start_date=datetime(2026, 6, 3, 14, 0, 0),
        location="Room 400, City Hall",
        status="scheduled",
        agenda_url="https://phila.legistar.com/agenda.pdf",
    )
    base.update(overrides)
    return Event(**base)


def test_to_ics_wraps_a_vcalendar():
    out = to_ics([_event()])
    assert out.startswith("BEGIN:VCALENDAR\r\n")
    assert out.rstrip().endswith("END:VCALENDAR")
    # RFC 5545 requires CRLF line endings.
    assert "\r\n" in out
    assert out.count("BEGIN:VEVENT") == 1
    assert out.count("END:VEVENT") == 1


def test_vevent_carries_the_event_fields():
    out = to_ics([_event()])
    assert "UID:ocd-event/phila-1@convene\r\n" in out
    assert "DTSTART:20260603T140000\r\n" in out
    assert "SUMMARY:Committee on Rules\r\n" in out
    assert "URL:https://phila.legistar.com/agenda.pdf\r\n" in out
    assert "STATUS:CONFIRMED\r\n" in out


def test_commas_in_text_are_escaped():
    # RFC 5545 3.3.11: a literal comma in a value must be backslash-escaped.
    out = to_ics([_event()])
    assert "LOCATION:Room 400\\, City Hall\r\n" in out


def test_cancelled_status_maps_through():
    out = to_ics([_event(status="cancelled")])
    assert "STATUS:CANCELLED\r\n" in out


def test_end_date_becomes_dtend():
    out = to_ics([_event(end_date=datetime(2026, 6, 3, 16, 30, 0))])
    assert "DTEND:20260603T163000\r\n" in out


def test_event_without_a_url_omits_the_url_line():
    out = to_ics([_event(agenda_url=None, sources=[])])
    assert "URL:" not in out


def test_url_falls_back_to_the_first_source():
    out = to_ics([_event(agenda_url=None, sources=[Source(url="https://example.gov/m/1")])])
    assert "URL:https://example.gov/m/1\r\n" in out


def test_calendar_name_becomes_x_wr_calname():
    # The comma also exercises RFC 5545 escaping on the calendar name.
    out = to_ics([_event()], name="New York, NY meetings")
    assert "X-WR-CALNAME:New York\\, NY meetings\r\n" in out


def test_calendar_name_is_omitted_by_default():
    assert "X-WR-CALNAME" not in to_ics([_event()])


def test_long_lines_are_folded_to_75_octets():
    out = to_ics([_event(name="A " + "very " * 40 + "long meeting name")])
    for line in out.split("\r\n"):
        # A folded continuation line starts with a space; either way no
        # single physical line should exceed the 75-octet limit.
        assert len(line.encode("utf-8")) <= 75
