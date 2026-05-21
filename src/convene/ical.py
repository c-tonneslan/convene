"""Render meeting events as an iCalendar (RFC 5545) feed.

A municipal calendar is one of the more useful things to do with this
data: point ``convene events <city> --format ics -o city.ics`` at a
calendar app and you have a subscribable feed of council meetings.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from convene.models import Event

_PRODID = "-//convene//convene//EN"

_STATUS = {
    "scheduled": "CONFIRMED",
    "passed": "CONFIRMED",
    "cancelled": "CANCELLED",
}


def to_ics(events: Iterable[Event], *, name: str | None = None) -> str:
    """Render events as a VCALENDAR string with RFC 5545 CRLF line endings.

    When ``name`` is given it's emitted as X-WR-CALNAME, the property
    Apple Calendar, Google Calendar and Outlook read to label a
    subscribed feed. Without it the feed shows up untitled.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
    ]
    if name:
        lines.append(f"X-WR-CALNAME:{_escape(name)}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for event in events:
        lines.extend(_vevent(event, stamp))
    lines.append("END:VCALENDAR")
    return "".join(_fold(line) + "\r\n" for line in lines)


def _vevent(event: Event, stamp: str) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{_escape(event.id)}@convene",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{_datetime(event.start_date)}",
    ]
    if event.end_date:
        lines.append(f"DTEND:{_datetime(event.end_date)}")
    lines.append(f"SUMMARY:{_escape(event.name)}")
    if event.location:
        lines.append(f"LOCATION:{_escape(event.location)}")
    url = event.agenda_url or event.video_url
    if not url and event.sources:
        url = event.sources[0].url
    if url:
        lines.append(f"URL:{_escape(url)}")
    description = _description(event)
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    status = _STATUS.get((event.status or "").lower())
    if status:
        lines.append(f"STATUS:{status}")
    lines.append("END:VEVENT")
    return lines


def _description(event: Event) -> str:
    parts = [event.organization_name]
    for label, url in (
        ("Agenda", event.agenda_url),
        ("Minutes", event.minutes_url),
        ("Video", event.video_url),
    ):
        if url:
            parts.append(f"{label}: {url}")
    return "\n".join(p for p in parts if p)


def _datetime(value: datetime) -> str:
    """Format as an RFC 5545 floating (local) DATE-TIME.

    convene's source data carries no timezone, and meeting times are
    inherently in the city's local zone, so a floating time is the honest
    representation: a calendar app renders it in the viewer's own zone.
    """
    return value.strftime("%Y%m%dT%H%M%S")


def _escape(text: str) -> str:
    # RFC 5545 3.3.11: escape backslash, newline, comma and semicolon.
    return (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _fold(line: str) -> str:
    """Fold a content line to <=75 octets per physical line, per RFC 5545 3.1.

    A continuation line is written as CRLF + one space, and that leading
    space counts toward the 75-octet budget, so continuations get 74.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks = []
    limit = 75  # the first physical line has no leading fold space
    while len(encoded) > limit:
        # Back off to a UTF-8 character boundary so a multi-byte rune
        # isn't split across the fold.
        cut = limit
        while cut > 1 and (encoded[cut] & 0xC0) == 0x80:
            cut -= 1
        chunks.append(encoded[:cut])
        encoded = encoded[cut:]
        limit = 74
    chunks.append(encoded)
    return "\r\n ".join(chunk.decode("utf-8") for chunk in chunks)
