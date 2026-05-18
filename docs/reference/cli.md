# CLI reference

All commands accept `--format json|ndjson`, `-o FILE`, `--to DB.db`, and
`--cache`.

## `convene list`

Show the cities convene knows about.

## `convene events <slug>`

Stream meetings.

| Flag | Notes |
|---|---|
| `--since DATETIME` | ISO floor on `EventDate` |
| `--until DATETIME` | ISO ceiling on `EventDate` |
| `--since-modified DATETIME` | Filter on `EventLastModifiedUtc` (Legistar only). Use this for incremental sync. |
| `--include-items` | Pull agenda items per event. One extra request per event. Legistar only. |
| `--include-votes` | Pull roll-call votes per item. Implies `--include-items`. Legistar only. |
| `--limit N` | Stop after N events |
| `--token TOKEN` | Legistar API token (NYC only). Reads `$CONVENE_TOKEN` if unset. |

## `convene matters <slug>`

Stream legislation. Legistar only.

| Flag | Notes |
|---|---|
| `--since DATETIME` | ISO floor on `MatterIntroDate` |
| `--until DATETIME` | ISO ceiling on `MatterIntroDate` |
| `--since-modified DATETIME` | Filter on `MatterLastModifiedUtc` |
| `--include-sponsors` | One extra request per matter |
| `--include-history` | Pull the full action trail per matter |
| `--limit N` | Stop after N matters |

## `convene people <slug>` / `convene bodies <slug>`

Stream active council members or active bodies. No filters.

## `convene memberships <slug> <person-id>`

A person's seats on bodies. `<person-id>` is a numeric Legistar PersonId,
which `convene people` gives you.

## Output sinks

- Default: pretty JSON array to stdout.
- `-o FILE` writes the same JSON to a file.
- `--format ndjson` switches to newline-delimited JSON (one record per line),
  good for piping into `jq` or streaming into another process.
- `--to FILE.db` writes records into a SQLite database. Compatible with any
  of the above; if you pass both `--to` and `-o`, you get both.

## Exit codes

- `0` on success
- `1` on a network or API error (with the message on stderr)
- `2` on a usage error (unknown city, bad flag combination, unsupported
  feature for the selected platform)
