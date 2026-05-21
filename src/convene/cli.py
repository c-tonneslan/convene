"""convene — pull municipal meeting data from one or many city portals.

    convene events philly --since 2026-01-01
    convene events seattle --include-items --include-votes > seattle.json
    convene matters chicago --since 2026-01-01 --include-sponsors --include-history
    convene memberships philly 2
    convene events philly --since-modified 2026-05-10 --to philly.db
    convene people seattle
    convene bodies philly
    convene list

NYC's API needs a free token. Get one at council.nyc.gov/legislation/api/, then
pass --token or set CONVENE_TOKEN.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from convene import sqlite_sink
from convene.adapters import GranicusAdapter, LegistarAdapter
from convene.adapters.granicus import GranicusError
from convene.adapters.legistar import LegistarError
from convene.cache import build_client
from convene.ical import to_ics
from convene.models import Event
from convene.registry import Jurisdiction, jurisdictions
from convene.registry import get as get_jurisdiction

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Pull municipal meeting data from city portals into one JSON shape.",
)

console = Console()
err = Console(stderr=True)


# ----- shared option wrappers

def _slug_arg():
    return typer.Argument(..., help="City slug (run `convene list`)")


def _token_opt():
    return typer.Option(
        None, "--token",
        help="Legistar API token (only needed for NYC). Reads $CONVENE_TOKEN if unset.",
        envvar="CONVENE_TOKEN",
    )


def _output_opt():
    return typer.Option(None, "-o", "--output", help="Write JSON to a file instead of stdout")


def _format_opt():
    return typer.Option("json", "--format", "-f",
                        help="Output format: 'json', 'ndjson', or 'ics' "
                             "(iCalendar, events only)")


def _cache_opt():
    return typer.Option(False, "--cache",
                        help="Cache GET responses on disk at ~/.cache/convene/")


def _db_opt():
    return typer.Option(None, "--to",
                        help="Append records to a SQLite database at PATH "
                             "(creates one if it doesn't exist)")


def _since_mod_opt():
    return typer.Option(None, "--since-modified",
                        help="Pull only records modified after this UTC datetime "
                             "(for incremental sync)")


# ----- commands

@app.command("list")
def cmd_list() -> None:
    """Show the cities convene knows about."""
    table = Table(title="Known jurisdictions")
    table.add_column("slug")
    table.add_column("name")
    table.add_column("platform")
    table.add_column("notes")
    for j in jurisdictions():
        notes = []
        if j.needs_token:
            notes.append("needs token")
        if j.skip_endpoints:
            notes.append(f"no /{'/'.join(j.skip_endpoints)}")
        table.add_row(j.slug, j.name, j.platform, ", ".join(notes) or "")
    console.print(table)


@app.command("events")
def cmd_events(
    slug: str = _slug_arg(),
    since: datetime | None = typer.Option(None, "--since", help="ISO date floor (EventDate)"),
    until: datetime | None = typer.Option(None, "--until", help="ISO date ceiling (EventDate)"),
    since_modified: datetime | None = _since_mod_opt(),
    include_items: bool = typer.Option(False, "--include-items",
                                       help="Fetch agenda items per event (Legistar only)"),
    include_votes: bool = typer.Option(False, "--include-votes",
                                       help="Roll-call votes (Legistar, implies --include-items)"),
    limit: int | None = typer.Option(None, "--limit", help="Stop after N events"),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
    db: Path | None = _db_opt(),
) -> None:
    """Stream meetings for a jurisdiction."""
    j = _lookup(slug)
    if include_votes:
        include_items = True

    if j.platform == "granicus":
        if include_items or include_votes or since_modified or token:
            err.print("[yellow]warning: --include-items / --include-votes / "
                      "--since-modified / --token are Legistar-only and will be ignored "
                      f"for granicus jurisdiction {slug!r}[/yellow]")
        with GranicusAdapter(j, client=build_client(cache=cache)) as adapter:
            events = adapter.events(
                since=since.date() if since else None,
                until=until.date() if until else None,
            )
            _emit(_limit(events, limit), output, fmt, db, sqlite_sink.insert_events,
                  cal_name=f"{j.name} meetings")
        return

    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        events = adapter.events(
            since=since.date() if since else None,
            until=until.date() if until else None,
            since_modified=since_modified,
            include_items=include_items,
            include_votes=include_votes,
        )
        _emit(_limit(events, limit), output, fmt, db, sqlite_sink.insert_events)


@app.command("people")
def cmd_people(
    slug: str = _slug_arg(),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
    db: Path | None = _db_opt(),
) -> None:
    """List council members and other tracked people."""
    j = _lookup(slug)
    _require_legistar(j, "people")
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        _emit(adapter.people(), output, fmt, db, sqlite_sink.insert_people)


@app.command("bodies")
def cmd_bodies(
    slug: str = _slug_arg(),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
    db: Path | None = _db_opt(),
) -> None:
    """List councils, committees, and departments."""
    j = _lookup(slug)
    _require_legistar(j, "bodies")
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        _emit(adapter.organizations(), output, fmt, db, sqlite_sink.insert_organizations)


@app.command("matters")
def cmd_matters(
    slug: str = _slug_arg(),
    since: datetime | None = typer.Option(None, "--since",
                                          help="ISO date floor (MatterIntroDate)"),
    until: datetime | None = typer.Option(None, "--until",
                                          help="ISO date ceiling (MatterIntroDate)"),
    since_modified: datetime | None = _since_mod_opt(),
    include_sponsors: bool = typer.Option(False, "--include-sponsors",
                                          help="Fetch sponsors per matter (slow)"),
    include_history: bool = typer.Option(False, "--include-history",
                                         help="Fetch the full action history per matter (slow)"),
    limit: int | None = typer.Option(None, "--limit", help="Stop after N matters"),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
    db: Path | None = _db_opt(),
) -> None:
    """Stream legislation (bills, resolutions, communications)."""
    j = _lookup(slug)
    _require_legistar(j, "matters")
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        matters = adapter.matters(
            since=since.date() if since else None,
            until=until.date() if until else None,
            since_modified=since_modified,
            include_sponsors=include_sponsors,
            include_history=include_history,
        )
        _emit(_limit(matters, limit), output, fmt, db, sqlite_sink.insert_matters)


@app.command("memberships")
def cmd_memberships(
    slug: str = _slug_arg(),
    person_id: int = typer.Argument(..., help="Legistar PersonId (numeric, from `convene people`)"),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
    db: Path | None = _db_opt(),
) -> None:
    """List a person's seats on councils and committees."""
    j = _lookup(slug)
    _require_legistar(j, "memberships")
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        _emit(adapter.memberships(person_id), output, fmt, db, sqlite_sink.insert_memberships)


# ----- internals

def _lookup(slug: str) -> Jurisdiction:
    try:
        return get_jurisdiction(slug)
    except KeyError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from None


def _require_legistar(j: Jurisdiction, action: str) -> None:
    if j.platform != "legistar":
        err.print(f"[red]{action} is Legistar-only; {j.slug} is on {j.platform}.[/red]")
        raise typer.Exit(code=2)


def _limit(it: Iterable, n: int | None) -> Iterable:
    if n is None:
        return it
    return (x for i, x in enumerate(it) if i < n)


def _emit(records: Iterable, output: Path | None, fmt: str,
          db: Path | None, db_inserter, cal_name: str | None = None) -> None:
    """Tee records to one or more sinks (stdout/file as JSON, and/or SQLite)."""
    try:
        if db:
            conn = sqlite_sink.connect(db)
            records = list(records)  # materialize so we can hand the same list to both
            n = db_inserter(conn, iter(records))
            conn.close()
            err.print(f"[green]wrote {n} records to {db}[/green]")
            if output is None and fmt == "json":
                # If they only asked for SQLite, don't dump JSON too.
                return

        if fmt not in {"json", "ndjson", "ics"}:
            err.print(f"[red]unknown --format {fmt!r}; use 'json', 'ndjson', or 'ics'[/red]")
            raise typer.Exit(code=2)

        if fmt == "ics":
            records = list(records)
            if any(not isinstance(r, Event) for r in records):
                err.print("[red]--format ics is only supported for `convene events`[/red]")
                raise typer.Exit(code=2)

        out = output.open("w", newline="") if output else sys.stdout
        try:
            count = 0
            if fmt == "ics":
                out.write(to_ics(records, name=cal_name))
                count = len(records)
            elif fmt == "ndjson":
                for r in records:
                    out.write(r.model_dump_json() + "\n")
                    count += 1
            else:
                payload = [r.model_dump(mode="json") for r in records]
                count = len(payload)
                json.dump(payload, out, indent=2, default=str)
                out.write("\n")
        finally:
            if output:
                out.close()
        if output:
            err.print(f"[green]wrote {count} records to {output}[/green]")
    except (LegistarError, GranicusError) as exc:
        err.print(f"[red]{exc}[/red]")
        msg = str(exc)
        if ("401" in msg or "403" in msg) and not os.environ.get("CONVENE_TOKEN"):
            err.print("[dim]set CONVENE_TOKEN or pass --token to retry[/dim]")
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
