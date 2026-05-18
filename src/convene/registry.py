"""Registry of known jurisdictions.

Adding a city is a config entry, not a code change. The whole point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Platform = Literal["legistar"]  # granicus, civicclerk to come


@dataclass(frozen=True)
class Jurisdiction:
    slug: str             # what the CLI takes: "philly", "nyc", ...
    name: str             # the human name
    platform: Platform
    client: str           # platform-specific identifier (Legistar uses "phila", "nyc", ...)
    portal_url: str       # public-facing portal


_JURISDICTIONS: dict[str, Jurisdiction] = {
    j.slug: j
    for j in [
        Jurisdiction("philly", "Philadelphia, PA", "legistar", "phila", "https://phila.legistar.com"),
        Jurisdiction("nyc", "New York City, NY", "legistar", "nyc", "https://legistar.council.nyc.gov"),
        Jurisdiction("chicago", "Chicago, IL", "legistar", "chicago", "https://chicago.legistar.com"),
        Jurisdiction("la", "Los Angeles, CA", "legistar", "lacity", "https://cityclerk.lacity.org"),
        Jurisdiction("sf", "San Francisco, CA", "legistar", "sfgov", "https://sfgov.legistar.com"),
        Jurisdiction("seattle", "Seattle, WA", "legistar", "seattle", "https://seattle.legistar.com"),
        Jurisdiction("boston", "Boston, MA", "legistar", "boston", "https://boston.legistar.com"),
        Jurisdiction("oakland", "Oakland, CA", "legistar", "oakland", "https://oakland.legistar.com"),
        Jurisdiction("baltimore", "Baltimore, MD", "legistar", "baltimore", "https://baltimore.legistar.com"),
        Jurisdiction("dc", "Washington, DC", "legistar", "dccouncil", "https://dccouncil.gov"),
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
