"""convene — pull municipal meeting data from one or many city portals.

    convene events philly --since 2026-01-01
    convene events nyc --include-items > nyc_meetings.json
    convene people seattle
    convene list
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from convene.adapters import LegistarAdapter
from convene.registry import get as get_jurisdiction
from convene.registry import jurisdictions

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Pull meeting data from city portals into one JSON shape.",
)

console = Console()
err = Console(stderr=True)


@app.command("list")
def cmd_list() -> None:
    """Show the cities convene knows about."""
    table = Table(title="Known jurisdictions")
    table.add_column("slug")
    table.add_column("name")
    table.add_column("platform")
    table.add_column("portal")
    for j in jurisdictions():
        table.add_row(j.slug, j.name, j.platform, j.portal_url)
    console.print(table)


@app.command("events")
def cmd_events(
    slug: str = typer.Argument(..., help="City slug (run `convene list`)"),
    since: datetime | None = typer.Option(None, "--since", help="ISO date floor"),
    until: datetime | None = typer.Option(None, "--until", help="ISO date ceiling"),
    include_items: bool = typer.Option(False, "--include-items",
                                       help="Fetch agenda items per event (slow)"),
    limit: int | None = typer.Option(None, "--limit", help="Stop after N events"),
    output: Path | None = typer.Option(None, "-o", "--output",
                                          help="Write to file instead of stdout"),
) -> None:
    """Stream meetings for a jurisdiction as JSON."""
    j = _lookup(slug)
    with LegistarAdapter(j) as adapter:
        events = adapter.events(
            since=since.date() if since else None,
            until=until.date() if until else None,
            include_items=include_items,
        )
        if limit:
            events = (e for i, e in enumerate(events) if i < limit)
        _dump([e.model_dump(mode="json") for e in events], output)


@app.command("people")
def cmd_people(
    slug: str = typer.Argument(...),
    output: Path | None = typer.Option(None, "-o", "--output"),
) -> None:
    """List council members and other tracked people."""
    j = _lookup(slug)
    with LegistarAdapter(j) as adapter:
        _dump([p.model_dump(mode="json") for p in adapter.people()], output)


@app.command("bodies")
def cmd_bodies(
    slug: str = typer.Argument(...),
    output: Path | None = typer.Option(None, "-o", "--output"),
) -> None:
    """List councils, committees, and departments."""
    j = _lookup(slug)
    with LegistarAdapter(j) as adapter:
        _dump([o.model_dump(mode="json") for o in adapter.organizations()], output)


def _lookup(slug: str):
    try:
        return get_jurisdiction(slug)
    except KeyError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from None


def _dump(payload: list[dict], output: Path | None) -> None:
    text = json.dumps(payload, indent=2, default=str)
    if output:
        output.write_text(text)
        err.print(f"[green]wrote {len(payload)} records to {output}[/green]")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    app()
