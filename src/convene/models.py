"""Normalized output models, loosely modeled on the Open Civic Data spec.

Convene doesn't try to be a strict OCD implementation. It produces JSON that's
shaped like OCD so downstream tools (Councilmatic, custom ingest scripts) can
either drop it in directly or remap a couple of fields. Whatever a city's
adapter doesn't have, we leave None.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A pointer back to where this record came from."""

    url: str
    note: str | None = None


class Organization(BaseModel):
    """A council, committee, or department. Maps to OCD's organization."""

    id: str
    jurisdiction: str
    name: str
    classification: str | None = None  # "legislature", "committee", "department", ...
    parent_id: str | None = None
    sources: list[Source] = Field(default_factory=list)


class Person(BaseModel):
    """A council member or other named participant."""

    id: str
    jurisdiction: str
    name: str
    given_name: str | None = None
    family_name: str | None = None
    email: str | None = None
    image: str | None = None
    party: str | None = None
    district: str | None = None
    sources: list[Source] = Field(default_factory=list)


VoteOption = Literal["yes", "no", "abstain", "absent", "other"]


class Vote(BaseModel):
    person_name: str
    option: VoteOption
    raw_value: str | None = None  # the platform's verbatim label, e.g. "In Favor", "Excused"


class EventItem(BaseModel):
    """A single line on a meeting agenda."""

    order: int
    title: str
    matter_id: str | None = None
    matter_title: str | None = None
    matter_type: str | None = None
    matter_status: str | None = None
    votes: list[Vote] = Field(default_factory=list)


class Event(BaseModel):
    """A meeting. Maps to OCD's event."""

    id: str
    jurisdiction: str
    name: str
    organization_name: str
    start_date: datetime
    end_date: datetime | None = None
    location: str | None = None
    status: str | None = None  # "scheduled", "passed", "cancelled"
    agenda_url: str | None = None
    minutes_url: str | None = None
    video_url: str | None = None
    items: list[EventItem] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class MatterAction(BaseModel):
    """A single recorded action on a piece of legislation."""

    date: datetime
    action: str
    action_text: str | None = None
    body: str | None = None
    event_id: str | None = None  # ocd-event ID, joinable against Event.id
    mover: str | None = None
    seconder: str | None = None
    tally: str | None = None
    passed: bool | None = None


class Matter(BaseModel):
    """A piece of legislation, resolution, or other tracked item."""

    id: str
    jurisdiction: str
    identifier: str  # the human-readable bill number
    title: str
    classification: str | None = None
    status: str | None = None
    introduced_date: date | None = None
    sponsors: list[str] = Field(default_factory=list)
    actions: list[MatterAction] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class Membership(BaseModel):
    """A person's seat on a body, with optional date range."""

    person_id: str
    person_name: str
    organization_name: str
    role: str | None = None        # "Member", "Chair", "Vice Chair", ...
    start_date: date | None = None
    end_date: date | None = None
