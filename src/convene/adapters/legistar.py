"""Adapter for the Legistar Web API.

Legistar (a Granicus product) powers most US municipal meeting portals: Philly,
Chicago, Seattle, and a few hundred others. They publish a real REST/OData API
at webapi.legistar.com, but most existing scrapers ignore it and scrape the
HTML instead. We use the API.

Docs: https://webapi.legistar.com/Help
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

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
    VoteOption,
)
from convene.registry import Jurisdiction

BASE = "https://webapi.legistar.com/v1"
PAGE = 1000  # API caps page size at 1000
MAX_RETRIES = 3
RETRY_BASE = 0.5  # seconds; doubled on each subsequent attempt


class LegistarError(RuntimeError):
    """Wraps an httpx error with a more helpful message."""


class LegistarAdapter:
    def __init__(self, jurisdiction: Jurisdiction, *, token: str | None = None,
                 client: httpx.Client | None = None):
        if jurisdiction.platform != "legistar":
            raise ValueError(f"{jurisdiction.slug} is not a Legistar jurisdiction")
        self.j = jurisdiction
        self.token = token
        if jurisdiction.needs_token and not token:
            # We let it through so the user can still hit unauthenticated endpoints
            # if any happen to work, but the next 4xx will explain.
            pass
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
               since_modified: datetime | None = None,
               include_items: bool = False, include_votes: bool = False) -> Iterator[Event]:
        """Yield meetings, newest first.

        `since` / `until` filter on EventDate; `since_modified` filters on
        EventLastModifiedUtc and is what you want for incremental sync.

        `include_items` triggers one extra request per event (the bulk events
        endpoint returns empty EventItems lists, so this is the only way to get
        them). `include_votes` further triggers one request per agenda item, so
        save it for when you actually need vote-level detail.
        """
        if "events" in self.j.skip_endpoints:
            raise LegistarError(
                f"{self.j.slug} doesn't expose /events through the Legistar API "
                f"({self.j.note or 'no further detail'})"
            )
        filters = []
        if since:
            filters.append(f"EventDate ge datetime'{since.isoformat()}'")
        if until:
            filters.append(f"EventDate le datetime'{until.isoformat()}'")
        if since_modified:
            filters.append(
                f"EventLastModifiedUtc ge datetime'{since_modified.isoformat()}'"
            )
        params = {"$orderby": "EventDate desc"}
        if filters:
            params["$filter"] = " and ".join(filters)

        for raw in self._paginate("events", params):
            event = self._event_from_raw(raw)
            if include_items:
                event.items = list(self._event_items(raw["EventId"], include_votes=include_votes))
            yield event

    def _event_items(self, event_id: int, *, include_votes: bool) -> Iterator[EventItem]:
        url = f"{BASE}/{self.j.client}/events/{event_id}/eventitems"
        raw_items = self._get(url, {})
        for raw in sorted(raw_items, key=lambda r: r.get("EventItemAgendaSequence") or 0):
            votes: list[Vote] = []
            # EventItemRollCallFlag is unreliable across cities (Seattle sets it
            # to 0 even on items that have 5+ votes). When the caller asked for
            # votes, just ask the API; the empty list is the answer for items
            # without a roll call.
            if include_votes:
                votes = list(self._item_votes(raw["EventItemId"]))
            yield EventItem(
                order=raw.get("EventItemAgendaSequence") or 0,
                title=raw.get("EventItemTitle") or raw.get("EventItemActionText") or "",
                matter_id=str(raw["EventItemMatterId"]) if raw.get("EventItemMatterId") else None,
                matter_title=raw.get("EventItemMatterName"),
                matter_type=raw.get("EventItemMatterType"),
                matter_status=raw.get("EventItemMatterStatus"),
                votes=votes,
            )

    def _item_votes(self, event_item_id: int) -> Iterator[Vote]:
        url = f"{BASE}/{self.j.client}/eventitems/{event_item_id}/votes"
        for raw in sorted(self._get(url, {}), key=lambda r: r.get("VoteSort") or 0):
            raw_value = raw.get("VoteValueName") or ""
            yield Vote(
                person_name=raw.get("VotePersonName") or "",
                option=_normalize_vote(raw_value),
                raw_value=raw_value or None,
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
                email=raw.get("PersonEmail") or None,
                image=raw.get("PersonWWW") or None,
                sources=[Source(url=self.j.portal_url)],
            )

    # ----------------------------------------------------------------- matters

    def matters(self, *, since: date | None = None, until: date | None = None,
                since_modified: datetime | None = None,
                include_sponsors: bool = False, include_history: bool = False) -> Iterator[Matter]:
        """Yield legislation items (bills, resolutions, etc.).

        `since` / `until` filter on MatterIntroDate; `since_modified` filters
        on MatterLastModifiedUtc and is what you want for incremental sync.

        `include_sponsors` does one extra request per matter to pull the
        sponsor list. `include_history` adds another request to pull the full
        action history.
        """
        filters = []
        if since:
            filters.append(f"MatterIntroDate ge datetime'{since.isoformat()}'")
        if until:
            filters.append(f"MatterIntroDate le datetime'{until.isoformat()}'")
        if since_modified:
            filters.append(
                f"MatterLastModifiedUtc ge datetime'{since_modified.isoformat()}'"
            )
        params = {"$orderby": "MatterIntroDate desc"}
        if filters:
            params["$filter"] = " and ".join(filters)

        for raw in self._paginate("matters", params):
            sponsors: list[str] = []
            actions: list[MatterAction] = []
            if include_sponsors:
                sponsors = list(self._matter_sponsors(raw["MatterId"]))
            if include_history:
                actions = list(self._matter_history(raw["MatterId"]))
            yield self._matter_from_raw(raw, sponsors, actions)

    def _matter_sponsors(self, matter_id: int) -> Iterator[str]:
        url = f"{BASE}/{self.j.client}/matters/{matter_id}/sponsors"
        raw_sponsors = sorted(self._get(url, {}), key=lambda r: r.get("MatterSponsorSequence") or 0)
        for raw in raw_sponsors:
            name = raw.get("MatterSponsorName")
            if name:
                yield name

    def _matter_history(self, matter_id: int) -> Iterator[MatterAction]:
        url = f"{BASE}/{self.j.client}/matters/{matter_id}/histories"
        for raw in self._get(url, {}):
            action_date_raw = raw.get("MatterHistoryActionDate")
            if not action_date_raw:
                continue
            event_id = raw.get("MatterHistoryEventId")
            yield MatterAction(
                date=datetime.fromisoformat(action_date_raw),
                action=raw.get("MatterHistoryActionName") or "",
                action_text=raw.get("MatterHistoryActionText"),
                body=raw.get("MatterHistoryActionBodyName"),
                event_id=(f"ocd-event/{self.j.client}-{event_id}"
                          if event_id else None),
                mover=raw.get("MatterHistoryMoverName"),
                seconder=raw.get("MatterHistorySeconderName"),
                tally=raw.get("MatterHistoryTally"),
                passed=_passed_flag(raw.get("MatterHistoryPassedFlagName")),
            )

    def _matter_from_raw(self, raw: dict[str, Any], sponsors: list[str],
                         actions: list[MatterAction]) -> Matter:
        intro = raw.get("MatterIntroDate")
        intro_date = _parse_date(intro) if intro else None
        return Matter(
            id=f"ocd-bill/{self.j.client}-{raw['MatterId']}",
            jurisdiction=self.j.slug,
            identifier=raw.get("MatterFile") or str(raw["MatterId"]),
            title=(raw.get("MatterTitle") or raw.get("MatterName") or "").strip(),
            classification=raw.get("MatterTypeName"),
            status=raw.get("MatterStatusName"),
            introduced_date=intro_date,
            sponsors=sponsors,
            actions=actions,
            sources=[Source(url=self.j.portal_url)],
        )

    # ------------------------------------------------------------- memberships

    def memberships(self, person_id: int) -> Iterator[Membership]:
        """Yield the committee/body seats a person has held."""
        url = f"{BASE}/{self.j.client}/persons/{person_id}/officerecords"
        for raw in self._get(url, {}):
            start_date = _parse_date(raw["OfficeRecordStartDate"]) if raw.get(
                "OfficeRecordStartDate") else None
            end_date = _parse_date(raw["OfficeRecordEndDate"]) if raw.get(
                "OfficeRecordEndDate") else None
            yield Membership(
                person_id=f"ocd-person/{self.j.client}-{raw['OfficeRecordPersonId']}",
                person_name=raw.get("OfficeRecordFullName") or "",
                organization_name=raw.get("OfficeRecordBodyName") or "",
                role=raw.get("OfficeRecordTitle") or raw.get("OfficeRecordMemberType"),
                start_date=start_date,
                end_date=end_date,
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
        resp = self._request_with_retry(url, params)
        if resp.status_code == 401 or resp.status_code == 403:
            hint = (" Pass --token (or set CONVENE_TOKEN)."
                    if self.j.needs_token and not self.token else "")
            raise LegistarError(
                f"{self.j.slug} returned {resp.status_code} on {url}.{hint}"
            )
        if resp.status_code >= 500:
            raise LegistarError(
                f"{self.j.slug} returned {resp.status_code} on {url}. "
                f"This usually means Legistar's per-tenant config is incomplete."
            )
        if resp.status_code == 400:
            # Legistar 400s carry useful body text (e.g. "Status Not Vievable...")
            body = resp.text.strip().strip('"')
            raise LegistarError(f"{self.j.slug} returned 400: {body}")
        resp.raise_for_status()
        data = resp.json()
        # /events returns a list, but a 404'd resource sometimes returns an empty obj
        return data if isinstance(data, list) else []

    def _request_with_retry(self, url: str, params: dict[str, str]) -> httpx.Response:
        """Send the request, retrying on transient failures.

        Legistar rate-limits and occasionally 502s under load. The 5xx
        path above still translates a final 5xx into a config-error
        message, but most of those are actually transient, a short
        retry catches them before the user sees a misleading error.
        """
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._http.get(url, params=params)
            except httpx.RequestError as exc:
                if attempt >= MAX_RETRIES:
                    raise LegistarError(
                        f"network error talking to Legistar: {exc}"
                    ) from exc
                time.sleep(RETRY_BASE * (2**attempt))
                continue
            if attempt < MAX_RETRIES and _is_retryable(resp.status_code):
                time.sleep(_retry_delay(resp, attempt))
                continue
            return resp
        # range(MAX_RETRIES + 1) always either returns or raises above; the
        # type checker doesn't see that, so close out with a clear error.
        raise LegistarError("legistar retry loop exhausted without a response")


# ----------------------------------------------------------------- helpers


def _parse_meeting_start(event_date: str | None, event_time: str | None) -> datetime:
    """Legistar splits date and time across two fields and time is freeform.

    EventDate looks like "2026-06-03T00:00:00" (always midnight).
    EventTime looks like "2:00 PM" or sometimes "9:30 AM" or None.
    We try to combine them; if EventTime is weird, fall back to the bare date.
    """
    if not event_date:
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


def _parse_date(raw: str) -> date:
    return datetime.fromisoformat(raw).date()


def _event_status(raw: dict[str, Any]) -> str | None:
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


def _passed_flag(value: str | None) -> bool | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in {"pass", "passed", "true", "yes"}:
        return True
    if v in {"fail", "failed", "false", "no"}:
        return False
    return None


_YES_VALUES = {"yes", "yea", "aye", "in favor", "for"}
_NO_VALUES = {"no", "nay", "against", "opposed"}
_ABSENT_VALUES = {"absent", "excused", "not present", "non voting"}
_ABSTAIN_VALUES = {"abstain", "abstention", "abstaining", "present"}


def _normalize_vote(value: str) -> VoteOption:
    v = value.strip().lower()
    if v in _YES_VALUES:
        return "yes"
    if v in _NO_VALUES:
        return "no"
    if v in _ABSTAIN_VALUES:
        return "abstain"
    if v in _ABSENT_VALUES:
        return "absent"
    return "other"


def _is_retryable(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    """Pick the wait time before the next retry.

    Prefers the server's Retry-After hint (either an integer number of
    seconds or an HTTP-date per RFC 7231 §7.1.3), falling back to
    exponential backoff from RETRY_BASE.
    """
    hint = resp.headers.get("Retry-After")
    if hint:
        hint = hint.strip()
        if hint.isdigit():
            return float(hint)
        try:
            target = parsedate_to_datetime(hint)
        except (TypeError, ValueError):
            target = None
        if target is not None:
            delta = (target - datetime.now(target.tzinfo)).total_seconds()
            if delta > 0:
                return delta
    return RETRY_BASE * (2**attempt)
