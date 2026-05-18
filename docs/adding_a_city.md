# Adding a city

If your city's council runs on Legistar or Granicus, adding it is a one-line
config change in [`src/convene/registry.py`](https://github.com/c-tonneslan/convene/blob/main/src/convene/registry.py).

## Step 1: Find out what your city uses

Open the council/meetings page on your city's website and look at the URL.

| URL pattern | Platform | What to put in registry |
|---|---|---|
| `<name>.legistar.com/...` | Legistar | `client="<name>"` |
| `legistar.<city>.gov/...` | Legistar | open a sub-link to find the client name |
| `<name>.granicus.com/ViewPublisher.php?view_id=N` | Granicus | `client="<name>"`, `view_ids=(N,)` |
| `<city>.granicus.com/...` with no ViewPublisher | older Granicus tenant | not currently supported |
| anything else | CivicPlus, CivicClerk, custom | not yet supported |

You can sanity-check a Legistar client name with one curl:

```
curl 'https://webapi.legistar.com/v1/<client>/events?$top=1' -H 'Accept: application/json'
```

A 200 with a meeting in it means you found the right one. A 400 means the
tenant is partly misconfigured (still possibly usable; see below). A 500 means
move on, the tenant is broken.

## Step 2: Add the jurisdiction

### Legistar example

```python
Jurisdiction(
    slug="pittsburgh",                        # what users type on the CLI
    name="Pittsburgh, PA",                    # human-readable
    platform="legistar",
    client="pittsburgh",                      # from step 1
    portal_url="https://pittsburgh.legistar.com",
),
```

### Granicus example

Granicus tenants have multiple "views" (one per body), each identified by
`view_id`. Open the city's portal, find the body you care about, and look at
the URL.

```python
Jurisdiction(
    slug="stpaul",
    name="Saint Paul, MN",
    platform="granicus",
    client="stpaul",                          # from the subdomain
    portal_url="https://stpaul.granicus.com",
    view_ids=(37,),                           # comma-separated for multiple bodies
    note="HTML-scraped; events only.",
),
```

## Step 3: Run it

```
convene events pittsburgh --limit 3
```

If meetings come through, ship a PR.

## When the tenant is partly broken

Some Legistar tenants misconfigure individual endpoints. SF, for example,
rejects `/events` with a 400 because their `EventAgendaStatus` setting is
missing, but `/bodies`, `/persons`, and `/matters` all work. Register the
city anyway and mark which endpoints to skip:

```python
Jurisdiction(
    slug="sf",
    name="San Francisco, CA",
    platform="legistar",
    client="sfgov",
    portal_url="https://sfgov.legistar.com",
    skip_endpoints=("events",),
    note="Bodies/persons/matters work; events misconfigured upstream.",
),
```

`convene events sf` then fails with the recorded note instead of a confusing
HTTP error.
