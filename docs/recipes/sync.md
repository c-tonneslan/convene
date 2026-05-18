# Incremental sync

Once you have a local copy of a city's data, you don't want to re-pull the
whole archive every day. Legistar's `LastModifiedUtc` fields give you a clean
incremental cursor.

## Pull anything changed in the last 24 hours

```
$ convene events  philly --since-modified $(date -u -v-1d +%Y-%m-%dT%H:%M:%S) --to philly.db
$ convene matters philly --since-modified $(date -u -v-1d +%Y-%m-%dT%H:%M:%S) --to philly.db
```

That's it. The CLI writes upserts, so existing rows are updated in place and
new rows are inserted.

## On a schedule

A simple cron line on a server:

```
0 6 * * * convene events philly --since-modified $(date -u -v-1d +%Y-%m-%dT%H:%M:%S) --to /var/lib/convene/philly.db
```

For a hosted-on-GitHub version see the [GitHub Action recipe](github_action.md).

## Caveats

- `--since-modified` filters by `EventLastModifiedUtc` / `MatterLastModifiedUtc`,
  not by date. A meeting from 2018 that gets re-edited today will show up in
  today's pull.
- Granicus doesn't expose a last-modified field. For Granicus jurisdictions
  you pull the whole archive every time. It's fine for small cities.
- Vote records and matter actions are pulled fresh whenever their parent
  event/matter changes, so they stay consistent.
