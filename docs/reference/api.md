# Python API reference

All convene models are pydantic `BaseModel`s and serialize cleanly to JSON
with `model_dump_json()`.

## Top-level

```python
from convene import (
    Event, EventItem, Matter, MatterAction, Membership,
    Organization, Person, Vote, Jurisdiction, get, jurisdictions,
)
from convene.adapters import LegistarAdapter, GranicusAdapter, for_jurisdiction
```

`get(slug)` returns a `Jurisdiction`. `jurisdictions()` returns the full
preconfigured list. `for_jurisdiction(j)` returns the adapter class that
handles `j.platform`.

## Example: incremental sync

```python
from datetime import datetime, timedelta
from convene import get
from convene.adapters import LegistarAdapter
from convene.sqlite_sink import connect, insert_events

j = get("philly")
yesterday = datetime.utcnow() - timedelta(days=1)
conn = connect("philly.db")
with LegistarAdapter(j) as adapter:
    n = insert_events(conn, adapter.events(since_modified=yesterday,
                                           include_items=True))
print(f"upserted {n} events")
conn.close()
```

## Example: caching client

```python
from convene import get
from convene.adapters import LegistarAdapter
from convene.cache import build_client

with LegistarAdapter(get("philly"), client=build_client(cache=True)) as a:
    for e in a.events(include_items=True, include_votes=True):
        ...  # second run of the same query hits no network
```

## Models

| Model | Fields |
|---|---|
| `Event` | id, jurisdiction, name, organization_name, start_date, end_date, location, status, agenda_url, minutes_url, video_url, items, sources |
| `EventItem` | order, title, matter_id, matter_title, matter_type, matter_status, votes |
| `Vote` | person_name, option, raw_value |
| `Matter` | id, jurisdiction, identifier, title, classification, status, introduced_date, sponsors, actions, sources |
| `MatterAction` | date, action, action_text, body, event_id, mover, seconder, tally, passed |
| `Person` | id, jurisdiction, name, given_name, family_name, email, image, party, district, sources |
| `Organization` | id, jurisdiction, name, classification, parent_id, sources |
| `Membership` | person_id, person_name, organization_name, role, start_date, end_date |

The full schemas are defined in
[`src/convene/models.py`](https://github.com/c-tonneslan/convene/blob/main/src/convene/models.py).
