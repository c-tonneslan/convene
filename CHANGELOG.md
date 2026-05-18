# Changelog

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
