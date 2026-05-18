# Building a local SQLite database

The `--to PATH` flag on every fetch command writes records into a SQLite
database. The same file accepts updates from multiple commands; rerunning a
command upserts based on the record's OCD ID, so refresh loops don't
duplicate rows.

```
$ convene events philly  --since 2026-01-01 --include-items   --to philly.db
$ convene matters philly --since 2026-01-01 --include-history --to philly.db
$ convene people  philly                                       --to philly.db
$ convene bodies  philly                                       --to philly.db
```

## Schema

| Table | Notes |
|---|---|
| `events` | One row per meeting, keyed by `id` |
| `event_items` | Agenda lines, keyed by `(event_id, item_order, title)` |
| `votes` | Roll-call votes, joinable on `event_id` + `item_order` |
| `matters` | Legislation rows, keyed by `id` |
| `matter_sponsors` | One row per (matter, sequence) |
| `matter_actions` | Bill action history. `event_id` joins to `events.id` |
| `organizations` | Councils, committees, departments |
| `people` | Council members and tracked individuals |
| `memberships` | A person's seats on bodies |

## Useful queries

Top 10 most-active bodies this year:

```sql
SELECT organization_name, COUNT(*) AS meetings
FROM events
WHERE start_date >= '2026-01-01'
GROUP BY organization_name
ORDER BY meetings DESC
LIMIT 10;
```

Bills introduced this month with their sponsors:

```sql
SELECT m.identifier, m.title, group_concat(s.name, ', ') AS sponsors
FROM matters m
LEFT JOIN matter_sponsors s ON s.matter_id = m.id
WHERE m.introduced_date >= date('now', 'start of month')
GROUP BY m.id;
```

Action history joined back to the originating meeting:

```sql
SELECT m.identifier, a.action_date, a.action, e.name AS meeting
FROM matter_actions a
JOIN matters m ON m.id = a.matter_id
LEFT JOIN events e ON e.id = a.event_id
ORDER BY a.action_date DESC
LIMIT 50;
```
