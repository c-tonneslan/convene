"""Registry of known jurisdictions.

Adding a city is a config entry, not a code change. The whole point.

Every entry below has been smoke-tested against the live Legistar Web API at
least once. If a city's portal returns 500s on a particular endpoint (which
happens when Legistar's per-tenant config is incomplete), the entry has a
note documenting which endpoints actually work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Platform = Literal["legistar", "granicus"]


@dataclass(frozen=True)
class Jurisdiction:
    slug: str             # what the CLI takes: "philly", "chicago", ...
    name: str             # the human-readable name
    platform: Platform
    client: str           # platform-specific identifier (Legistar uses "phila", ...)
    portal_url: str       # the public-facing portal
    needs_token: bool = False  # NYC requires a free API token; most don't
    skip_endpoints: tuple[str, ...] = field(default_factory=tuple)
    view_ids: tuple[int, ...] = field(default_factory=tuple)  # Granicus only
    note: str = ""


_JURISDICTIONS: dict[str, Jurisdiction] = {
    j.slug: j
    for j in [
        # Philly: fully working baseline.
        Jurisdiction("philly", "Philadelphia, PA", "legistar", "phila",
                     "https://phila.legistar.com"),
        Jurisdiction("chicago", "Chicago, IL", "legistar", "chicago",
                     "https://chicago.legistar.com"),
        Jurisdiction("seattle", "Seattle, WA", "legistar", "seattle",
                     "https://seattle.legistar.com",
                     note="One of the few cities that publishes roll-call votes."),
        Jurisdiction("boston", "Boston, MA", "legistar", "boston",
                     "https://boston.legistar.com"),
        Jurisdiction("oakland", "Oakland, CA", "legistar", "oakland",
                     "https://oakland.legistar.com"),
        Jurisdiction("baltimore", "Baltimore, MD", "legistar", "baltimore",
                     "https://baltimore.legistar.com"),
        Jurisdiction("pittsburgh", "Pittsburgh, PA", "legistar", "pittsburgh",
                     "https://pittsburgh.legistar.com"),
        Jurisdiction("detroit", "Detroit, MI", "legistar", "detroit",
                     "https://detroitmi.legistar.com"),
        Jurisdiction("kansascity", "Kansas City, MO", "legistar", "kansascity",
                     "https://cityclerk.kcmo.gov"),
        Jurisdiction("nashville", "Nashville, TN", "legistar", "nashville",
                     "https://nashville.legistar.com"),
        Jurisdiction("louisville", "Louisville, KY", "legistar", "louisville",
                     "https://louisville.legistar.com"),
        Jurisdiction("denver", "Denver, CO", "legistar", "denver",
                     "https://denver.legistar.com"),
        Jurisdiction("phoenix", "Phoenix, AZ", "legistar", "phoenix",
                     "https://phoenix.legistar.com"),
        Jurisdiction("sacramento", "Sacramento, CA", "legistar", "sacramento",
                     "https://sacramento.legistar.com"),
        Jurisdiction("sanjose", "San Jose, CA", "legistar", "sanjose",
                     "https://sanjose.legistar.com"),
        Jurisdiction("minneapolis", "Minneapolis, MN", "legistar", "minneapolismn",
                     "https://lims.minneapolismn.gov"),
        Jurisdiction("miamidade", "Miami-Dade County, FL", "legistar", "miamidade",
                     "https://miamidade.legistar.com"),
        Jurisdiction("charlotte", "Charlotte, NC", "legistar", "charlottenc",
                     "https://charlottenc.legistar.com"),
        # Cities whose Legistar config rejects /events but exposes bodies/persons/matters:
        Jurisdiction("sf", "San Francisco, CA", "legistar", "sfgov",
                     "https://sfgov.legistar.com",
                     skip_endpoints=("events",),
                     note="SF's tenant misconfigures EventAgendaStatus, so /events 400s. "
                          "Bodies, persons, and matters all work."),
        # Cities that require a token (which we don't ship):
        Jurisdiction("nyc", "New York City, NY", "legistar", "nyc",
                     "https://legistar.council.nyc.gov",
                     needs_token=True,
                     note="NYC gates the Web API behind a free API token. "
                          "Request one at council.nyc.gov/legislation/api/, then "
                          "pass --token or set CONVENE_TOKEN."),
        # ---- Granicus (HTML-scraped). Each city specifies one or more view_ids.
        # view_id is the council/committee picker on a Granicus portal; you can
        # see it in the URL of the meetings page.
        Jurisdiction("stpaul", "Saint Paul, MN", "granicus", "stpaul",
                     "https://stpaul.granicus.com",
                     view_ids=(37,),
                     note="HTML-scraped; events only, no matters/votes."),
        Jurisdiction("scranton", "Scranton, PA", "granicus", "scrantonpa",
                     "https://scrantonpa.granicus.com",
                     view_ids=(2,),
                     note="HTML-scraped; events only."),
        Jurisdiction("duluth", "Duluth, MN", "granicus", "duluth-mn",
                     "https://duluth-mn.granicus.com",
                     view_ids=(15,),
                     note="HTML-scraped; events only."),
        Jurisdiction("neworleans", "New Orleans, LA", "granicus", "cityofno",
                     "https://cityofno.granicus.com",
                     view_ids=(42,),
                     note="HTML-scraped; events only."),
    ]
}


def jurisdictions() -> list[Jurisdiction]:
    return sorted(_JURISDICTIONS.values(), key=lambda j: j.slug)


def get(slug: str) -> Jurisdiction:
    try:
        return _JURISDICTIONS[slug]
    except KeyError:
        known = ", ".join(sorted(_JURISDICTIONS))
        raise KeyError(f"unknown jurisdiction {slug!r}. known: {known}") from None
