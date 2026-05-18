# convene

Pull municipal meeting data from city government portals into one normalized
JSON shape. Built on the official Legistar Web API and a Granicus HTML
scraper, with support for adding a new city in one config entry.

## Why

US municipal council meetings are public. Most cities publish them through one
of two products:

- **Legistar** (a Granicus product) exposes a real REST/OData API at
  `webapi.legistar.com`. Almost nobody uses it. Existing libraries either
  scrape the HTML pages or wrap the API in heavy Django/Mongo orchestration.
- **Granicus GovMeetings** ships archive pages at `<city>.granicus.com/ViewPublisher.php`.
  No API at all, but the DOM is consistent across cities.

convene hits the Legistar API directly and scrapes the Granicus pages. Output
is OCD-shaped JSON (loosely modeled on [Open Civic Data](https://opencivicdata.readthedocs.io/))
so downstream tools like [Councilmatic](https://www.councilmatic.org/) can
ingest it with minimal remapping.

## Install

```
pip install convene
```

Requires Python 3.11+.

## At a glance

```
$ convene list                                     # see preconfigured cities
$ convene events philly --since 2026-01-01         # upcoming + recent meetings
$ convene events seattle --include-votes           # with roll-call votes
$ convene matters chicago --include-sponsors --include-history
$ convene memberships philly 2                     # which committees a person sits on
$ convene events philly --since-modified 2026-05-15 # incremental sync
$ convene events philly --to philly.db             # build a local SQLite db
```

## What it covers

- **Legistar**: events, agenda items, roll-call votes, matters (legislation),
  matter sponsors, matter action history, councils/committees, people,
  committee memberships.
- **Granicus**: events (body, date, agenda PDF, minutes, video link). No
  votes, matters, or members.

## What it doesn't

- Anything published only as a PDF without structured data
- CivicClerk, PrimeGov, eScribe (not yet)
- Real-time push notifications (you poll on a schedule)

## Next steps

- [Getting started](getting-started.md) walks through your first pull.
- [Adding a city](adding_a_city.md) shows how to extend the registry.
- The [recipes](recipes/github_action.md) cover common workflows.
