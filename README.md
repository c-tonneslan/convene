# convene

Pull municipal meeting data from city government portals into one normalized
JSON shape. Built on the official Legistar Web API (not HTML scraping), with
support for adding a new city in one config entry.

Most US cities run their council meeting portals on Legistar (a Granicus
product). Legistar publishes a real REST/OData API at `webapi.legistar.com`,
but most existing libraries either ignore the API and scrape HTML or wrap it
in heavy Django/Mongo orchestration. convene is the simple thing in the
middle: hit the API, normalize the response, output JSON.

The output shape is loosely modeled on
[Open Civic Data](https://opencivicdata.readthedocs.io/), so it slots into
Councilmatic-style ingest scripts and other civic-tech tooling without much
remapping.

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

Pull recent legislation with sponsors:

```
$ convene matters chicago --since 2026-01-01 --include-sponsors
```

List council members and committees:

```
$ convene people philly
$ convene bodies philly
```

Stream large pulls as newline-delimited JSON so jq and friends can chew on
the output as it lands:

```
$ convene matters philly --since 2026-01-01 --format ndjson | jq -r '.identifier'
```

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

20 cities, all smoke-tested against the live API. Each entry is a one-line
`Jurisdiction` in [`src/convene/registry.py`](src/convene/registry.py):

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

NYC requires a free API token. Get one from
[council.nyc.gov/legislation/api/](https://council.nyc.gov/legislation/api/),
then pass `--token` or set `CONVENE_TOKEN`.

To add a new city see [docs/adding_a_city.md](docs/adding_a_city.md).

## How convene compares

|  | convene | python-legistar-scraper | pupa |
|---|---|---|---|
| Source | Official REST/OData API | HTML scraping | Pluggable, mostly HTML |
| Breaks when Granicus tweaks the UI | no | yes | depends |
| Output | OCD-shaped JSON | Python dicts | Pushes to Postgres/Mongo |
| Dependencies | httpx, pydantic, typer | requests, lxml, scrapelib | Django, Mongo, scrapelib, ... |
| Adding a city | one config entry | a Python class per city | a Python class + pupa wiring |
| Modern Python | 3.11+ | 3.6+, Py2 legacy code | 3.x with Py2 lineage |
| Votes | yes | partial | depends on per-city scraper |
| Matters | yes | partial | yes |

convene is what python-legistar-scraper would look like if it started over
today and trusted the official API.

## Development

```
git clone https://github.com/c-tonneslan/convene
cd convene
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

Tests run against frozen fixtures of real API responses through an
httpx `MockTransport`, so the suite never hits the network.

## License

MIT.
