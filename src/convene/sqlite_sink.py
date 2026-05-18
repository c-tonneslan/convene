"""Stream convene records into a SQLite database.

The goal here is to give journalists, researchers, and city council aides a
queryable local file. One command, one .db file you can open in DB Browser or
hit with `sqlite3` from the terminal.

Schemas are intentionally simple. Foreign keys are declared but not enforced
because Legistar's dataset isn't always referentially clean.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from convene.models import Event, Matter, Membership, Organization, Person

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    name TEXT NOT NULL,
    organization_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    location TEXT,
    status TEXT,
    agenda_url TEXT,
    minutes_url TEXT,
    video_url TEXT
);

CREATE TABLE IF NOT EXISTS event_items (
    event_id TEXT NOT NULL,
    item_order INTEGER NOT NULL,
    title TEXT NOT NULL,
    matter_id TEXT,
    matter_title TEXT,
    matter_type TEXT,
    matter_status TEXT,
    PRIMARY KEY (event_id, item_order, title)
);

CREATE TABLE IF NOT EXISTS votes (
    event_id TEXT NOT NULL,
    item_order INTEGER NOT NULL,
    person_name TEXT NOT NULL,
    option TEXT NOT NULL,
    raw_value TEXT
);

CREATE TABLE IF NOT EXISTS matters (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    identifier TEXT NOT NULL,
    title TEXT NOT NULL,
    classification TEXT,
    status TEXT,
    introduced_date TEXT
);

CREATE TABLE IF NOT EXISTS matter_sponsors (
    matter_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (matter_id, sequence)
);

CREATE TABLE IF NOT EXISTS matter_actions (
    matter_id TEXT NOT NULL,
    action_date TEXT NOT NULL,
    action TEXT NOT NULL,
    action_text TEXT,
    body TEXT,
    event_id TEXT,
    mover TEXT,
    seconder TEXT,
    tally TEXT,
    passed INTEGER
);

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    name TEXT NOT NULL,
    classification TEXT,
    parent_id TEXT
);

CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    name TEXT NOT NULL,
    given_name TEXT,
    family_name TEXT,
    email TEXT,
    image TEXT,
    party TEXT,
    district TEXT
);

CREATE TABLE IF NOT EXISTS memberships (
    person_id TEXT NOT NULL,
    person_name TEXT NOT NULL,
    organization_name TEXT NOT NULL,
    role TEXT,
    start_date TEXT,
    end_date TEXT
);

CREATE INDEX IF NOT EXISTS idx_event_items_event ON event_items(event_id);
CREATE INDEX IF NOT EXISTS idx_votes_event_item ON votes(event_id, item_order);
CREATE INDEX IF NOT EXISTS idx_matter_actions_matter ON matter_actions(matter_id);
CREATE INDEX IF NOT EXISTS idx_matter_actions_event ON matter_actions(event_id);
CREATE INDEX IF NOT EXISTS idx_matter_sponsors_matter ON matter_sponsors(matter_id);
CREATE INDEX IF NOT EXISTS idx_memberships_person ON memberships(person_id);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    return conn


def insert_events(conn: sqlite3.Connection, events: Iterable[Event]) -> int:
    n = 0
    for ev in events:
        conn.execute(
            "INSERT OR REPLACE INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ev.id, ev.jurisdiction, ev.name, ev.organization_name,
             ev.start_date.isoformat(),
             ev.end_date.isoformat() if ev.end_date else None,
             ev.location, ev.status, ev.agenda_url, ev.minutes_url, ev.video_url),
        )
        # Replace items + votes for this event so reruns don't double up
        conn.execute("DELETE FROM event_items WHERE event_id = ?", (ev.id,))
        conn.execute("DELETE FROM votes WHERE event_id = ?", (ev.id,))
        for item in ev.items:
            conn.execute(
                "INSERT OR REPLACE INTO event_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ev.id, item.order, item.title, item.matter_id,
                 item.matter_title, item.matter_type, item.matter_status),
            )
            for vote in item.votes:
                conn.execute(
                    "INSERT INTO votes VALUES (?, ?, ?, ?, ?)",
                    (ev.id, item.order, vote.person_name, vote.option, vote.raw_value),
                )
        n += 1
    conn.commit()
    return n


def insert_matters(conn: sqlite3.Connection, matters: Iterable[Matter]) -> int:
    n = 0
    for m in matters:
        conn.execute(
            "INSERT OR REPLACE INTO matters VALUES (?, ?, ?, ?, ?, ?, ?)",
            (m.id, m.jurisdiction, m.identifier, m.title, m.classification,
             m.status, m.introduced_date.isoformat() if m.introduced_date else None),
        )
        conn.execute("DELETE FROM matter_sponsors WHERE matter_id = ?", (m.id,))
        conn.execute("DELETE FROM matter_actions WHERE matter_id = ?", (m.id,))
        for i, name in enumerate(m.sponsors):
            conn.execute(
                "INSERT INTO matter_sponsors VALUES (?, ?, ?)",
                (m.id, i, name),
            )
        for action in m.actions:
            conn.execute(
                "INSERT INTO matter_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (m.id, action.date.isoformat(), action.action, action.action_text,
                 action.body, action.event_id, action.mover, action.seconder,
                 action.tally,
                 None if action.passed is None else int(action.passed)),
            )
        n += 1
    conn.commit()
    return n


def insert_organizations(conn: sqlite3.Connection, orgs: Iterable[Organization]) -> int:
    n = 0
    for org in orgs:
        conn.execute(
            "INSERT OR REPLACE INTO organizations VALUES (?, ?, ?, ?, ?)",
            (org.id, org.jurisdiction, org.name, org.classification, org.parent_id),
        )
        n += 1
    conn.commit()
    return n


def insert_people(conn: sqlite3.Connection, people: Iterable[Person]) -> int:
    n = 0
    for p in people:
        conn.execute(
            "INSERT OR REPLACE INTO people VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (p.id, p.jurisdiction, p.name, p.given_name, p.family_name,
             p.email, p.image, p.party, p.district),
        )
        n += 1
    conn.commit()
    return n


def insert_memberships(conn: sqlite3.Connection, memberships: Iterable[Membership]) -> int:
    n = 0
    for m in memberships:
        # Memberships don't have a natural primary key, so we just append.
        # Callers who need idempotency should clear the table first.
        conn.execute(
            "INSERT INTO memberships VALUES (?, ?, ?, ?, ?, ?)",
            (m.person_id, m.person_name, m.organization_name, m.role,
             m.start_date.isoformat() if m.start_date else None,
             m.end_date.isoformat() if m.end_date else None),
        )
        n += 1
    conn.commit()
    return n
