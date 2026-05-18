"""Platform adapters. Each one knows how to talk to one kind of meeting portal."""

from convene.adapters.legistar import LegistarAdapter

__all__ = ["LegistarAdapter"]
