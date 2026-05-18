"""Adapter for Granicus's GovMeetings portals.

Unlike Legistar, Granicus's ViewPublisher pages have no clean public API, so
this adapter scrapes HTML. The DOM is stable across cities because Granicus
ships one template (the `<table class="listingTable" id="archive">` element),
but the field set is much thinner than Legistar's: you get the body name,
date, duration, and links to agenda / minutes / video. No matter IDs, no
roll-call votes, no committee memberships.

If your city is on Granicus *and* publishes legislation through Legistar
(many do; the two products are now sibling Granicus tools), prefer the
Legistar adapter.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from convene.models import Event, Source
from convene.registry import Jurisdiction


class GranicusError(RuntimeError):
    """Wraps an httpx/parse error with a more helpful message."""


_DATE_FMTS = (
    # "May 13, 2026" + optional " - 01:57 PM"
    "%B %d, %Y - %I:%M %p",
    "%B %d, %Y",
)


class GranicusAdapter:
    """Scrapes Granicus ViewPublisher archive pages.

    One Granicus tenant can host many views (City Council vs. Planning Board,
    etc.), so the registry stores a list of view_ids per jurisdiction. The
    adapter walks all of them and yields a flat stream of events.
    """

    def __init__(self, jurisdiction: Jurisdiction, *,
                 client: httpx.Client | None = None):
        if jurisdiction.platform != "granicus":
            raise ValueError(f"{jurisdiction.slug} is not a Granicus jurisdiction")
        if not jurisdiction.view_ids:
            raise ValueError(
                f"{jurisdiction.slug} has no view_ids configured. Open the city's "
                f"meetings page and copy the view_id from the URL into registry.py."
            )
        self.j = jurisdiction
        self._http = client or httpx.Client(
            timeout=30,
            headers={"User-Agent": "convene/0.2 (+https://github.com/c-tonneslan/convene)"},
            follow_redirects=True,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> GranicusAdapter:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def events(self, *, since: date | None = None,
               until: date | None = None) -> Iterator[Event]:
        """Yield meetings across all configured view_ids, newest first.

        Granicus has no server-side date filter, so since/until are applied
        client-side after parsing each row.
        """
        for view_id in self.j.view_ids:
            yield from self._events_for_view(view_id, since=since, until=until)

    def _events_for_view(self, view_id: int, *,
                         since: date | None, until: date | None) -> Iterator[Event]:
        url = f"https://{self.j.client}.granicus.com/ViewPublisher.php"
        try:
            resp = self._http.get(url, params={"view_id": view_id})
        except httpx.RequestError as exc:
            raise GranicusError(f"network error talking to Granicus: {exc}") from exc
        if resp.status_code != 200:
            raise GranicusError(
                f"{self.j.slug} view_id={view_id} returned {resp.status_code}. "
                f"Maybe the view_id changed; check the city's portal."
            )
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="archive")
        if table is None:
            # Sometimes the page renders without rows (no archived meetings yet)
            return
        for row in table.find_all("tr", class_="listingRow"):
            event = self._row_to_event(row, view_id)
            if event is None:
                continue
            if since and event.start_date.date() < since:
                continue
            if until and event.start_date.date() > until:
                continue
            yield event

    def _row_to_event(self, row: Tag, view_id: int) -> Event | None:
        cells = row.find_all("td", class_="listItem")
        if len(cells) < 2:
            return None
        # Cell 0 is the body name + date string, e.g.
        #   "Housing & Redevelopment Authority on 2026-05-13 2:00 PM"
        name_cell = _clean(cells[0].get_text())
        body_name, scheduled_date = _split_body_and_date(name_cell)

        # Cell 1 is the actual aired date, "May 13, 2026 - 01:57 PM"
        aired = _parse_aired_date(_clean(cells[1].get_text()))
        start_date = aired or scheduled_date or _epoch()

        agenda_url = _link_in_cell(cells, 3)
        minutes_url = _link_in_cell(cells, 4)
        video_url = _video_in_cell(cells, 5)

        clip_id = _extract_clip_id(agenda_url or video_url or "")
        if clip_id:
            event_id = f"ocd-event/{self.j.client}-{view_id}-{clip_id}"
        else:
            # Synthesize from body+date if there's no clip
            event_id = (f"ocd-event/{self.j.client}-{view_id}-"
                        f"{start_date.strftime('%Y%m%d%H%M')}")

        return Event(
            id=event_id,
            jurisdiction=self.j.slug,
            name=body_name,
            organization_name=body_name,
            start_date=start_date,
            location=None,
            status="passed",  # All Granicus archive rows are completed meetings
            agenda_url=agenda_url,
            minutes_url=minutes_url,
            video_url=video_url,
            sources=[Source(url=self.j.portal_url)],
        )


# ----------------------------------------------------------------- helpers


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _epoch() -> datetime:
    # Filler for the rare row with no parseable date
    return datetime(1970, 1, 1)


def _split_body_and_date(name_cell: str) -> tuple[str, datetime | None]:
    """The first cell on a row reads like 'Body Name on 2026-05-13 2:00 PM'."""
    m = re.match(r"^(.*?)\s+on\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}\s*[AP]M))?",
                 name_cell)
    if not m:
        return name_cell, None
    body = m.group(1)
    date_part = m.group(2)
    time_part = m.group(3)
    try:
        if time_part:
            dt = datetime.strptime(f"{date_part} {time_part.upper()}", "%Y-%m-%d %I:%M %p")
        else:
            dt = datetime.strptime(date_part, "%Y-%m-%d")
        return body, dt
    except ValueError:
        return body, None


def _parse_aired_date(s: str) -> datetime | None:
    if not s or s == "-":
        return None
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _link_in_cell(cells: list[Tag], index: int) -> str | None:
    if index >= len(cells):
        return None
    a = cells[index].find("a", href=True)
    if not a:
        return None
    href = a["href"]
    # Granicus emits protocol-relative URLs ("//host/...")
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return None  # too ambiguous; let caller skip
    return href


def _video_in_cell(cells: list[Tag], index: int) -> str | None:
    """The video link is opened via window.open in an onClick handler."""
    if index >= len(cells):
        return None
    onclick = cells[index].find("a", onclick=True)
    if not onclick:
        return None
    m = re.search(r"window\.open\('([^']+)'", onclick.get("onclick", ""))
    if not m:
        return None
    href = m.group(1)
    if href.startswith("//"):
        return "https:" + href
    return href


def _extract_clip_id(url: str) -> str | None:
    m = re.search(r"clip_id=(\d+)", url)
    return m.group(1) if m else None
