# convene

Pull municipal meeting data from city government portals into one normalized
JSON shape. Built on the official Legistar Web API (not HTML scraping), with
support for adding a new city in one config entry.

Most US cities run their council meeting portals on Legistar (a Granicus
product) or Granicus's other tools. Legistar exposes a real REST/OData API
at `webapi.legistar.com`, but most existing libraries either ignore the API
and scrape HTML, or wrap it in heavy Django/Mongo orchestration. convene is
the simple thing in the middle: hit the API, normalize the response, output
JSON.

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

Include the full agenda for each meeting (one extra request per event, slower):

```
$ convene events philly --include-items --limit 5
```

List council members and committees:

```
$ convene people philly
$ convene bodies philly
```

## What you get

Each event looks like:

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
      "matter_type": "Bill",
      "matter_status": "ADOPTED"
    }
  ],
  "sources": [{ "url": "https://phila.legistar.com/MeetingDetail.aspx?..." }]
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
friends work.

## Adding a city

Find your city's Legistar client name (usually visible in the portal URL,
e.g. Philly's portal is `phila.legistar.com` so the client is `phila`), then
add a row to [`src/convene/registry.py`](src/convene/registry.py):

```python
Jurisdiction("pittsburgh", "Pittsburgh, PA", "legistar", "pittsburgh",
             "https://pittsburgh.legistar.com"),
```

That's it. If your city isn't on Legistar, see
[`docs/adding_a_city.md`](docs/adding_a_city.md) for finding the right client
name or for the (planned) Granicus and CivicClerk adapters.

## Why not just use python-legistar-scraper?

[python-legistar-scraper](https://github.com/opencivicdata/python-legistar-scraper)
scrapes the public HTML pages. That works but it's slow (one request per
meeting page), breaks when Granicus tweaks the UI, and doesn't give you
matter IDs in a way that's easy to join against. Legistar's actual API
exposes everything in clean JSON, including matter IDs, agenda sequence, and
the full body taxonomy.

convene is what python-legistar-scraper would look like if you started over
today and trusted the official API.

## License

MIT.
