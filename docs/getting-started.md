# Getting started

## Install

```
pip install convene
```

Python 3.11 or newer.

## Your first pull

List the cities convene already knows about:

```
$ convene list
```

Pick one and pull its recent meetings:

```
$ convene events philly --since 2026-01-01 --limit 10
```

Output is pretty-printed JSON to stdout. Pipe to a file:

```
$ convene events philly --since 2026-01-01 -o philly_meetings.json
```

Or stream as ndjson (newline-delimited JSON) for jq:

```
$ convene events philly --since 2026-01-01 --format ndjson \
    | jq -r '.start_date + " " + .name'
```

## Going deeper

The base events command gives you metadata. Add `--include-items` to fetch the
agenda for each meeting (one extra request per event):

```
$ convene events philly --since 2026-05-01 --include-items
```

Add `--include-votes` for roll-call votes (only a handful of cities publish
these; Seattle is the cleanest example):

```
$ convene events seattle --since 2026-04-01 --include-votes
```

## Legislation

```
$ convene matters chicago --since 2026-01-01 --include-sponsors --include-history
```

The `--include-history` flag pulls every recorded action on each bill
(introduced → referred → committee vote → passed), with a joinable event_id
so you can link actions back to meetings.

## People and committees

```
$ convene people philly
$ convene bodies philly
$ convene memberships philly 2     # PersonId comes from `convene people`
```

## SQLite output

For anything bigger than a few hundred records, pipe the same commands into a
local SQLite database with `--to`:

```
$ convene events philly --since 2026-01-01 --include-items --to philly.db
$ convene matters philly --since 2026-01-01 --include-history --to philly.db
$ sqlite3 philly.db
sqlite> SELECT name, start_date FROM events ORDER BY start_date DESC LIMIT 5;
```

The schema is documented in the [SQLite recipe](recipes/sqlite.md).

## Caching

While you're iterating, pass `--cache` so a second run with the same
parameters hits no network:

```
$ convene events philly --since 2026-01-01 --cache    # first run hits the network
$ convene events philly --since 2026-01-01 --cache    # second run is instant
```

Cache lives at `~/.cache/convene/`. Delete that directory when you want fresh
data.
