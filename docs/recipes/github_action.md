# Daily snapshot via GitHub Actions

convene ships a reusable composite action at
[`.github/actions/snapshot`](https://github.com/c-tonneslan/convene/tree/main/.github/actions/snapshot)
that pulls one or more jurisdictions and commits the JSON into a repository.
Schedule it nightly and you get a free, public, history-tracked archive of
your city's meetings.

## Minimal example

Create `.github/workflows/snapshot.yml` in your archive repo:

```yaml
name: snapshot

on:
  schedule:
    - cron: "0 6 * * *"   # 6 AM UTC daily
  workflow_dispatch:

permissions:
  contents: write

jobs:
  snapshot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: c-tonneslan/convene/.github/actions/snapshot@main
        with:
          jurisdictions: philly,seattle,nashville
          since-days: 30
          out-dir: snapshots/
      - name: commit
        run: |
          git config user.name github-actions
          git config user.email github-actions@github.com
          git add snapshots
          git diff --staged --quiet || git commit -m "snapshot $(date -u +%F)"
          git push
```

After the first run you'll have `snapshots/philly_events.json`,
`snapshots/seattle_events.json`, etc., committed to your default branch.

## Inputs

| Input | Default | Notes |
|---|---|---|
| `jurisdictions` | (required) | Comma-separated slugs |
| `since-days` | `30` | How many days of events/matters to pull |
| `out-dir` | `snapshots/` | Where to write the JSON |
| `include` | `events,matters,people,bodies` | Which collections to snapshot |
| `python-version` | `3.13` | Forwarded to actions/setup-python |
| `token` | "" | Pass a Legistar token for NYC |

## Why a repo?

Two reasons. One, git is a great free history-tracking layer for civic data
(you can `git log -p` to see exactly when a bill's status changed). Two, the
JSON files are public artifacts that anyone can pull without running anything
themselves.
