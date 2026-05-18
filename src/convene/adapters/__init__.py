"""Platform adapters. Each one knows how to talk to one kind of meeting portal."""

from convene.adapters.granicus import GranicusAdapter
from convene.adapters.legistar import LegistarAdapter

__all__ = ["GranicusAdapter", "LegistarAdapter"]


def for_jurisdiction(j):
    """Return the adapter class that handles this jurisdiction's platform."""
    if j.platform == "legistar":
        return LegistarAdapter
    if j.platform == "granicus":
        return GranicusAdapter
    raise ValueError(f"no adapter for platform {j.platform!r}")
