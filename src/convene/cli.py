"""convene — pull municipal meeting data from one or many city portals.

    convene events philly --since 2026-01-01
    convene events seattle --include-items --include-votes > seattle.json
    convene matters chicago --since 2026-01-01 --include-sponsors
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

from convene.adapters import LegistarAdapter
from convene.adapters.legistar import LegistarError
from convene.cache import build_client
from convene.registry import Jurisdiction, jurisdictions
from convene.registry import get as get_jurisdiction

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Pull municipal meeting data from city portals into one JSON shape.",
)

console = Console()
err = Console(stderr=True)


# ----- shared option wrappers (keeps typer's noisy syntax out of the commands)

def _slug_arg():
    return typer.Argument(..., help="City slug (run `convene list`)")


def _token_opt():
    return typer.Option(
        None, "--token",
        help="Legistar API token (only needed for NYC). Reads $CONVENE_TOKEN if unset.",
        envvar="CONVENE_TOKEN",
    )


def _output_opt():
    return typer.Option(None, "-o", "--output", help="Write to file instead of stdout")


def _format_opt():
    return typer.Option("json", "--format", "-f",
                        help="Output format: 'json' or 'ndjson' (one record per line)")


def _cache_opt():
    return typer.Option(False, "--cache",
                        help="Cache GET responses on disk at ~/.cache/convene/ "
                             "(safe for read-only data; delete the dir to refresh)")


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
    include_items: bool = typer.Option(False, "--include-items",
                                       help="Fetch agenda items per event (slow)"),
    include_votes: bool = typer.Option(False, "--include-votes",
                                       help="Also fetch roll-call votes (implies --include-items)"),
    limit: int | None = typer.Option(None, "--limit", help="Stop after N events"),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
) -> None:
    """Stream meetings for a jurisdiction as JSON."""
    j = _lookup(slug)
    if include_votes:
        include_items = True
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        events = adapter.events(
            since=since.date() if since else None,
            until=until.date() if until else None,
            include_items=include_items,
            include_votes=include_votes,
        )
        _stream(_limit(events, limit), output, fmt)


@app.command("people")
def cmd_people(
    slug: str = _slug_arg(),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
) -> None:
    """List council members and other tracked people."""
    j = _lookup(slug)
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        _stream(adapter.people(), output, fmt)


@app.command("bodies")
def cmd_bodies(
    slug: str = _slug_arg(),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
) -> None:
    """List councils, committees, and departments."""
    j = _lookup(slug)
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        _stream(adapter.organizations(), output, fmt)


@app.command("matters")
def cmd_matters(
    slug: str = _slug_arg(),
    since: datetime | None = typer.Option(None, "--since",
                                          help="ISO date floor (MatterIntroDate)"),
    until: datetime | None = typer.Option(None, "--until",
                                          help="ISO date ceiling (MatterIntroDate)"),
    include_sponsors: bool = typer.Option(False, "--include-sponsors",
                                          help="Fetch sponsors per matter (slow)"),
    limit: int | None = typer.Option(None, "--limit", help="Stop after N matters"),
    token: str | None = _token_opt(),
    output: Path | None = _output_opt(),
    fmt: str = _format_opt(),
    cache: bool = _cache_opt(),
) -> None:
    """Stream legislation (bills, resolutions, communications) as JSON."""
    j = _lookup(slug)
    with LegistarAdapter(j, token=token, client=build_client(cache=cache)) as adapter:
        matters = adapter.matters(
            since=since.date() if since else None,
            until=until.date() if until else None,
            include_sponsors=include_sponsors,
        )
        _stream(_limit(matters, limit), output, fmt)


# ----- internals

def _lookup(slug: str) -> Jurisdiction:
    try:
        return get_jurisdiction(slug)
    except KeyError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from None


def _limit(it: Iterable, n: int | None) -> Iterable:
    if n is None:
        return it
    return (x for i, x in enumerate(it) if i < n)


def _stream(records: Iterable, output: Path | None, fmt: str) -> None:
    if fmt not in {"json", "ndjson"}:
        err.print(f"[red]unknown --format {fmt!r}; use 'json' or 'ndjson'[/red]")
        raise typer.Exit(code=2)
    try:
        out = output.open("w") if output else sys.stdout
        try:
            count = 0
            if fmt == "ndjson":
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
    except LegistarError as exc:
        err.print(f"[red]{exc}[/red]")
        msg = str(exc)
        if ("401" in msg or "403" in msg) and not os.environ.get("CONVENE_TOKEN"):
            err.print("[dim]set CONVENE_TOKEN or pass --token to retry[/dim]")
        raise typer.Exit(code=1) from None


if __name__ == "__main__":
    app()
