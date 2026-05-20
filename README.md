# convene

Pull municipal meeting data from city government portals into one normalized
JSON shape. Built on the official Legistar Web API plus a Granicus HTML
scraper. Adding a new city is a one-line registry entry.

Most US cities run their council meeting portals on Legistar (a Granicus
product) or Granicus's other tools. Legistar publishes a real REST/OData API
at `webapi.legistar.com`. Granicus's older "ViewPublisher" pages have no API
but a consistent DOM. convene uses the Legistar API directly and scrapes
Granicus's HTML. Output is OCD-shaped JSON (loosely modeled on
[Open Civic Data](https://opencivicdata.readthedocs.io/)) so downstream tools
like [Councilmatic](https://www.councilmatic.org/) can ingest it with minimal
remapping.

Full docs at [c-tonneslan.github.io/convene](https://c-tonneslan.github.io/convene/).

## Install

```
pip install convene
```

Requires Python 3.11+.

## Quick start

List the cities convene knows about:

```
$ convene list
```

Pull every upcoming meeting in Philly:

```
$ convene events philly --since 2026-01-01 -o philly_meetings.json
```

Include the full agenda for each meeting (one extra request per event):

```
$ convene events philly --include-items --limit 5
```

Get roll-call votes for every agenda item (only Seattle and a handful of
other cities actually publish these):

```
$ convene events seattle --since 2026-05-01 --include-votes --limit 10
```

Pull recent legislation with sponsors and the full action history:

```
$ convene matters chicago --since 2026-01-01 --include-sponsors --include-history
```

Which committees has a person sat on? (PersonId comes from `convene people`)

```
$ convene memberships philly 2
```

Pull only what's changed since yesterday (for incremental sync):

```
$ convene events philly --since-modified $(date -u -v-1d +%Y-%m-%dT%H:%M:%S)
```

Build a queryable local SQLite database:

```
$ convene events philly  --since 2026-01-01 --include-items   --to philly.db
$ convene matters philly --since 2026-01-01 --include-history --to philly.db
$ sqlite3 philly.db 'SELECT name, start_date FROM events LIMIT 5;'
```

Stream large pulls as newline-delimited JSON so jq and friends can chew on
the output as it lands:

```
$ convene matters philly --since 2026-01-01 --format ndjson | jq -r '.identifier'
```

Export upcoming meetings as an iCalendar feed and drop it into any calendar
app:

```
$ convene events philly --since 2026-01-01 --format ics -o philly.ics
```

Each meeting becomes a `VEVENT` with the start time, location, status, and a
link to the agenda. `--format ics` applies to `convene events` only.

Cache GET responses across runs (useful when iterating):

```
$ convene events philly --cache
$ convene events philly --cache  # second call hits no network
```

## What you get

Each event:

```json
{
  "id": "ocd-event/phila-6376",
  "jurisdiction": "philly",
  "name": "Committee on Rules",
  "organization_name": "Committee on Rules",
  "start_date": "2026-06-03T14:00:00",
  "location": "Room 400, City Hall",
  "status": "scheduled",
  "agenda_url": "https://philadelphia.legistar1.com/.../Meeting_Agenda.pdf",
  "items": [
    {
      "order": 1,
      "title": "An Ordinance amending...",
      "matter_id": "26715",
      "matter_type": "Bill",
      "matter_status": "ADOPTED",
      "votes": [
        { "person_name": "Alexis Mercedes Rinck", "option": "yes", "raw_value": "In Favor" }
      ]
    }
  ],
  "sources": [{ "url": "https://phila.legistar.com/MeetingDetail.aspx?..." }]
}
```

Each matter (legislation):

```json
{
  "id": "ocd-bill/phila-27257",
  "jurisdiction": "philly",
  "identifier": "260506",
  "title": "An Ordinance amending Chapter 14-1000 of...",
  "classification": "Bill",
  "status": "IN COMMITTEE",
  "introduced_date": "2026-05-14",
  "sponsors": ["Councilmember Bass", "Councilmember Squilla"],
  "sources": [{ "url": "https://phila.legistar.com" }]
}
```

## Use it as a library

The CLI is a thin wrapper. Underneath:

```python
from convene import get
from convene.adapters import LegistarAdapter

j = get("philly")
with LegistarAdapter(j) as adapter:
    for event in adapter.events(include_items=True):
        print(event.start_date, event.name)
        for item in event.items:
            print("  -", item.title)
```

Every model is a pydantic `BaseModel`, so `event.model_dump_json()` and
`Event.model_validate(payload)` work as expected.

## Cities preconfigured

24 cities (20 Legistar + 4 Granicus), all smoke-tested against the live API.
Each entry is a one-line `Jurisdiction` in
[`src/convene/registry.py`](src/convene/registry.py):

| slug | city | notes |
|---|---|---|
| baltimore | Baltimore, MD | |
| boston | Boston, MA | |
| charlotte | Charlotte, NC | |
| chicago | Chicago, IL | |
| denver | Denver, CO | |
| detroit | Detroit, MI | |
| kansascity | Kansas City, MO | |
| louisville | Louisville, KY | |
| miamidade | Miami-Dade County, FL | |
| minneapolis | Minneapolis, MN | |
| nashville | Nashville, TN | |
| nyc | New York City, NY | needs token |
| oakland | Oakland, CA | |
| philly | Philadelphia, PA | |
| phoenix | Phoenix, AZ | |
| pittsburgh | Pittsburgh, PA | |
| sacramento | Sacramento, CA | |
| sanjose | San Jose, CA | |
| seattle | Seattle, WA | publishes roll-call votes |
| sf | San Francisco, CA | bodies/persons/matters only (the tenant's Legistar config rejects /events) |
| duluth | Duluth, MN | Granicus; events only |
| neworleans | New Orleans, LA | Granicus; events only |
| scranton | Scranton, PA | Granicus; events only |
| stpaul | Saint Paul, MN | Granicus; events only |

NYC requires a free API token. Get one from
[council.nyc.gov/legislation/api/](https://council.nyc.gov/legislation/api/),
then pass `--token` or set `CONVENE_TOKEN`.

To add a new city see [docs/adding_a_city.md](docs/adding_a_city.md).

## How convene compares

|  | convene | python-legistar-scraper | pupa |
|---|---|---|---|
| Legistar source | Official REST/OData API | HTML scraping | Pluggable, mostly HTML |
| Granicus support | Yes (HTML scraper) | No | Per-city scrapers |
| Output | OCD-shaped JSON / SQLite | Python dicts | Pushes to Postgres/Mongo |
| Dependencies | httpx, pydantic, typer, bs4 | requests, lxml, scrapelib | Django, Mongo, scrapelib, ... |
| Adding a city | one config entry | a Python class per city | a Python class + pupa wiring |
| Modern Python | 3.11+ | 3.6+, Py2 legacy code | 3.x with Py2 lineage |
| Votes | yes (Seattle, others) | partial | depends on per-city scraper |
| Matters + history | yes | partial | yes |
| Incremental sync | yes (`--since-modified`) | no | yes |

convene is what python-legistar-scraper would look like if it started over
today and trusted the official API.

## Snapshot via GitHub Actions

There's a reusable composite action at
[`.github/actions/snapshot`](.github/actions/snapshot/action.yml) that pulls
one or more cities and writes JSON snapshots into a directory. Schedule it
nightly and you get a public, git-versioned archive of your city's meetings.
See [docs/recipes/github_action.md](docs/recipes/github_action.md).

## Development

```
git clone https://github.com/c-tonneslan/convene
cd convene
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs]"
pytest
ruff check .
mkdocs serve   # docs at http://127.0.0.1:8000
```

Tests run against frozen fixtures of real API responses through an
httpx `MockTransport`, so the suite never hits the network.

## License

MIT.
