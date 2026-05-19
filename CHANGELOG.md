# Changelog

## Unreleased

- Legistar adapter retries on 429 and 5xx with exponential backoff (3
  attempts by default, honors `Retry-After`). Network errors during the
  request are also retried. Daily-snapshot workflows that hit Legistar
  during peak hours stop failing on the first transient hiccup.

## 0.4.0 — 2026-05-17

Docs, distribution, automation.

- mkdocs-material docs site, deploys to gh-pages on push to main.
- Reusable `convene snapshot` composite action at
  `.github/actions/snapshot` for daily archival workflows.
- PyPI release workflow on tag push using trusted publishing.

## 0.3.0 — 2026-05-17

Granicus support.

- `GranicusAdapter` scrapes ViewPublisher HTML pages. Events only (body,
  date, agenda PDF, minutes PDF, video link); no matters or votes because
  Granicus doesn't expose that structure.
- 4 Granicus cities preconfigured: St Paul, Scranton, Duluth, New Orleans.
  All smoke-tested against live portals.
- CLI dispatches by `jurisdiction.platform`. Legistar-only commands
  (matters, people, bodies, memberships) fail with a clear message for
  Granicus jurisdictions.
- New `for_jurisdiction(j)` helper returns the right adapter class.

## 0.2.0 — 2026-05-17

Sync, history, memberships, SQLite.

- `--include-history` on matters pulls the `MatterAction` trail. Each
  action carries a joinable `event_id` that maps back to the originating
  meeting.
- `convene memberships <slug> <person-id>` lists which bodies a person
  has been seated on, with date ranges.
- `--since-modified` on events and matters filters by
  `EventLastModifiedUtc` / `MatterLastModifiedUtc` for incremental sync.
- `--to PATH` writes records into a SQLite database with a normalized
  schema (events, event_items, votes, matters, matter_sponsors,
  matter_actions, organizations, people, memberships). Upserts on the
  natural OCD ID, so reruns refresh rather than duplicate.
- Adds 8 more tests covering the new features (34 total).

## 0.1.0 — 2026-05-17

First release. Pulls municipal meeting data from the official Legistar Web API
into one normalized JSON shape.

- LegistarAdapter against webapi.legistar.com
  - `events` with `--since` / `--until` date filtering
  - `--include-items` does one extra request per event because the bulk
    endpoint returns empty EventItems arrays
  - `--include-votes` fetches roll-call votes for every agenda item (the
    EventItemRollCallFlag is unreliable across cities, so we just ask)
  - `bodies` for councils, committees, departments
  - `people` for active council members
  - `matters` for legislation, with `--include-sponsors`
- CLI: `convene list / events / people / bodies / matters`
- 20 US cities preconfigured and smoke-tested against the live API:
  philly, chicago, seattle, boston, oakland, baltimore, pittsburgh, detroit,
  kansascity, nashville, louisville, denver, phoenix, sacramento, sanjose,
  minneapolis, miamidade, charlotte, sf (bodies/persons/matters only;
  Legistar's per-tenant config rejects /events for SF), and nyc (requires a
  free API token, pass `--token` or set `CONVENE_TOKEN`)
- Output formats: pretty JSON (default) and `--format ndjson` for piping
- `--cache` writes GET responses to `~/.cache/convene/` for iterative work
- Friendly error messages for 400 (carries Legistar's body text), 401/403
  (hints at the token flag), and 5xx (most often per-tenant config errors)
- Output shape loosely models Open Civic Data so Councilmatic and friends
  ingest it with minimal remapping
- Event time parser handles `2:00 PM` / `9 AM` / `13:00` / None / unparseable
- Vote value normalizer maps "In Favor" / "Yea" / "Aye" → yes, "Against" /
  "Nay" → no, "Excused" / "Not Present" → absent, etc., and preserves the
  platform's verbatim label in `raw_value`
