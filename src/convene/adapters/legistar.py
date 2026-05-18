"""Adapter for the Legistar Web API.

Legistar (Granicus product) powers most US municipal meeting portals: Philly,
NYC, Chicago, Seattle, plus a few hundred others. They publish a real REST/OData
API at webapi.legistar.com, but most existing scrapers ignore it and scrape the
HTML instead. We use the API.

Docs: https://webapi.legistar.com/Help
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import httpx

from convene.models import Event, EventItem, Organization, Person, Source
from convene.registry import Jurisdiction

BASE = "https://webapi.legistar.com/v1"
PAGE = 1000  # API caps page size at 1000


class LegistarAdapter:
    def __init__(self, jurisdiction: Jurisdiction, *, token: str | None = None,
                 client: httpx.Client | None = None):
        if jurisdiction.platform != "legistar":
            raise ValueError(f"{jurisdiction.slug} is not a Legistar jurisdiction")
        self.j = jurisdiction
        self.token = token
        self._http = client or httpx.Client(timeout=30, headers={"Accept": "application/json"})
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> LegistarAdapter:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ events

    def events(self, *, since: date | None = None, until: date | None = None,
               include_items: bool = False) -> Iterator[Event]:
        """Yield meetings, newest first.

        If `include_items` is True, fetch each event's agenda items individually
        (one extra request per event). The bulk events endpoint returns empty
        EventItems lists, so this is the only way to get them.
        """
        filters = []
        if since:
            filters.append(f"EventDate ge datetime'{since.isoformat()}'")
        if until:
            filters.append(f"EventDate le datetime'{until.isoformat()}'")
        params = {"$orderby": "EventDate desc"}
        if filters:
            params["$filter"] = " and ".join(filters)

        for raw in self._paginate("events", params):
            event = self._event_from_raw(raw)
            if include_items:
                event.items = list(self._event_items(raw["EventId"]))
            yield event

    def _event_items(self, event_id: int) -> Iterator[EventItem]:
        url = f"{BASE}/{self.j.client}/events/{event_id}/eventitems"
        raw_items = self._get(url, {})
        for raw in sorted(raw_items, key=lambda r: r.get("EventItemAgendaSequence") or 0):
            yield EventItem(
                order=raw.get("EventItemAgendaSequence") or 0,
                title=raw.get("EventItemTitle") or raw.get("EventItemActionText") or "",
                matter_id=str(raw["EventItemMatterId"]) if raw.get("EventItemMatterId") else None,
                matter_title=raw.get("EventItemMatterName"),
                matter_type=raw.get("EventItemMatterType"),
                matter_status=raw.get("EventItemMatterStatus"),
            )

    def _event_from_raw(self, raw: dict[str, Any]) -> Event:
        start = _parse_meeting_start(raw.get("EventDate"), raw.get("EventTime"))
        return Event(
            id=f"ocd-event/{self.j.client}-{raw['EventId']}",
            jurisdiction=self.j.slug,
            name=raw.get("EventBodyName") or "",
            organization_name=raw.get("EventBodyName") or "",
            start_date=start,
            location=raw.get("EventLocation"),
            status=_event_status(raw),
            agenda_url=raw.get("EventAgendaFile"),
            minutes_url=raw.get("EventMinutesFile"),
            video_url=(raw.get("EventInSiteURL")
                       if raw.get("EventVideoStatus") == "Public" else None),
            sources=[Source(url=raw["EventInSiteURL"])] if raw.get("EventInSiteURL") else [],
        )

    # ------------------------------------------------------------ bodies/people

    def organizations(self) -> Iterator[Organization]:
        for raw in self._paginate("bodies", {}):
            if not raw.get("BodyActiveFlag"):
                continue
            yield Organization(
                id=f"ocd-organization/{self.j.client}-{raw['BodyId']}",
                jurisdiction=self.j.slug,
                name=raw.get("BodyName") or "",
                classification=_body_classification(raw.get("BodyTypeName")),
                sources=[Source(url=self.j.portal_url)],
            )

    def people(self) -> Iterator[Person]:
        for raw in self._paginate("persons", {}):
            if raw.get("PersonActiveFlag") != 1:
                continue
            yield Person(
                id=f"ocd-person/{self.j.client}-{raw['PersonId']}",
                jurisdiction=self.j.slug,
                name=raw.get("PersonFullName") or raw.get("PersonLastName") or "",
                given_name=raw.get("PersonFirstName"),
                family_name=raw.get("PersonLastName"),
                email=raw.get("PersonEmail"),
                image=raw.get("PersonWWW"),
                sources=[Source(url=self.j.portal_url)],
            )

    # --------------------------------------------------------------- internals

    def _paginate(self, resource: str, params: dict[str, str]) -> Iterator[dict[str, Any]]:
        url = f"{BASE}/{self.j.client}/{resource}"
        skip = 0
        while True:
            batch_params = {**params, "$top": str(PAGE), "$skip": str(skip)}
            batch = self._get(url, batch_params)
            if not batch:
                return
            yield from batch
            if len(batch) < PAGE:
                return
            skip += PAGE

    def _get(self, url: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if self.token:
            params = {**params, "token": self.token}
        resp = self._http.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        # /events returns a list, but a 404'd resource sometimes returns an empty obj
        return data if isinstance(data, list) else []


# ----------------------------------------------------------------- helpers


def _parse_meeting_start(event_date: str | None, event_time: str | None) -> datetime:
    """Legistar splits date and time across two fields and time is freeform.

    EventDate looks like "2026-06-03T00:00:00" (always midnight).
    EventTime looks like "2:00 PM" or sometimes "9:30 AM" or None.
    We try to combine them; if EventTime is weird, fall back to the bare date.
    """
    if not event_date:
        # the API shouldn't hand us this but a None here would crash pydantic
        raise ValueError("event missing EventDate")
    base = datetime.fromisoformat(event_date)
    if not event_time:
        return base
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            t = datetime.strptime(event_time.strip(), fmt).time()
            return base.replace(hour=t.hour, minute=t.minute)
        except ValueError:
            continue
    return base


def _event_status(raw: dict[str, Any]) -> str | None:
    # Legistar doesn't expose a clean status. We infer from agenda/minutes state.
    minutes = raw.get("EventMinutesStatusName")
    agenda = raw.get("EventAgendaStatusName")
    if minutes == "Final":
        return "passed"
    if agenda == "Final":
        return "scheduled"
    return None


def _body_classification(body_type: str | None) -> str | None:
    if not body_type:
        return None
    t = body_type.lower()
    if "committee" in t:
        return "committee"
    if "council" in t or "legislature" in t:
        return "legislature"
    if "department" in t or "office" in t:
        return "department"
    return None
