"""Tests for the SQLite sink."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from convene import sqlite_sink
from convene.models import (
    Event,
    EventItem,
    Matter,
    MatterAction,
    Membership,
    Organization,
    Person,
    Source,
    Vote,
)


def _event() -> Event:
    return Event(
        id="ocd-event/phila-1",
        jurisdiction="philly",
        name="City Council",
        organization_name="City Council",
        start_date=datetime(2026, 5, 1, 14, 0),
        location="Room 400",
        status="passed",
        items=[
            EventItem(
                order=1,
                title="A bill",
                matter_id="42",
                matter_status="ADOPTED",
                votes=[
                    Vote(person_name="Member A", option="yes", raw_value="In Favor"),
                    Vote(person_name="Member B", option="no", raw_value="Against"),
                ],
            ),
        ],
        sources=[Source(url="https://phila.legistar.com/MeetingDetail.aspx?LEGID=1")],
    )


def test_insert_event_creates_rows(tmp_path: Path):
    db = tmp_path / "t.db"
    conn = sqlite_sink.connect(db)
    n = sqlite_sink.insert_events(conn, [_event()])
    assert n == 1
    rows = conn.execute(
        "SELECT id, name, status FROM events"
    ).fetchall()
    assert rows == [("ocd-event/phila-1", "City Council", "passed")]

    items = conn.execute("SELECT title, matter_status FROM event_items").fetchall()
    assert items == [("A bill", "ADOPTED")]

    votes = conn.execute(
        "SELECT person_name, option, raw_value FROM votes ORDER BY person_name"
    ).fetchall()
    assert votes == [
        ("Member A", "yes", "In Favor"),
        ("Member B", "no", "Against"),
    ]
    conn.close()


def test_insert_event_is_idempotent(tmp_path: Path):
    """Re-inserting the same event should not double its items or votes."""
    db = tmp_path / "t.db"
    conn = sqlite_sink.connect(db)
    sqlite_sink.insert_events(conn, [_event()])
    sqlite_sink.insert_events(conn, [_event()])
    assert conn.execute("SELECT COUNT(*) FROM event_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 2
    conn.close()


def test_insert_matter_with_actions(tmp_path: Path):
    db = tmp_path / "t.db"
    conn = sqlite_sink.connect(db)
    m = Matter(
        id="ocd-bill/phila-42",
        jurisdiction="philly",
        identifier="260123",
        title="An Ordinance",
        classification="Bill",
        status="IN COMMITTEE",
        introduced_date=date(2026, 5, 1),
        sponsors=["Member A", "Member B"],
        actions=[
            MatterAction(
                date=datetime(2026, 5, 14, 10, 0),
                action="Introduced and Referred",
                body="CITY COUNCIL",
                event_id="ocd-event/phila-100",
                mover="Member A",
            ),
        ],
    )
    sqlite_sink.insert_matters(conn, [m])
    actions = conn.execute(
        "SELECT action, body, event_id, mover FROM matter_actions"
    ).fetchall()
    assert actions == [
        ("Introduced and Referred", "CITY COUNCIL", "ocd-event/phila-100", "Member A"),
    ]
    sponsors = conn.execute(
        "SELECT name FROM matter_sponsors ORDER BY sequence"
    ).fetchall()
    assert sponsors == [("Member A",), ("Member B",)]
    conn.close()


def test_insert_misc(tmp_path: Path):
    db = tmp_path / "t.db"
    conn = sqlite_sink.connect(db)
    sqlite_sink.insert_organizations(conn, [
        Organization(id="ocd-organization/phila-1", jurisdiction="philly",
                     name="City Council", classification="legislature"),
    ])
    sqlite_sink.insert_people(conn, [
        Person(id="ocd-person/phila-1", jurisdiction="philly", name="Member A"),
    ])
    sqlite_sink.insert_memberships(conn, [
        Membership(person_id="ocd-person/phila-1", person_name="Member A",
                   organization_name="City Council", role="Member"),
    ])
    assert conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM memberships").fetchone()[0] == 1
    conn.close()


def test_joinable_event_id(tmp_path: Path):
    """The MatterAction.event_id should be a real foreign key to events.id."""
    db = tmp_path / "t.db"
    conn = sqlite_sink.connect(db)
    sqlite_sink.insert_events(conn, [Event(
        id="ocd-event/phila-100",
        jurisdiction="philly",
        name="City Council",
        organization_name="City Council",
        start_date=datetime(2026, 5, 14, 10, 0),
    )])
    sqlite_sink.insert_matters(conn, [Matter(
        id="ocd-bill/phila-42",
        jurisdiction="philly",
        identifier="x",
        title="t",
        actions=[MatterAction(
            date=datetime(2026, 5, 14, 10, 0),
            action="Referred",
            event_id="ocd-event/phila-100",
        )],
    )])
    joined = conn.execute(
        "SELECT e.name, a.action FROM matter_actions a "
        "JOIN events e ON e.id = a.event_id"
    ).fetchall()
    assert joined == [("City Council", "Referred")]
    conn.close()
