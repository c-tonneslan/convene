# Adding a city to convene

If your city's council runs on Legistar, adding it is a one-line config
change. If they run on something else, you'll need an adapter.

## Step 1: Find out what your city uses

Open the council/meetings page on your city's website and look at the URL.

- `phila.legistar.com/...` → Legistar, client name `phila`
- `legistar.council.nyc.gov/...` → Legistar, client name `nyc`
- `chicago.legistar.com/...` → Legistar, client name `chicago`
- `boston.granicus.com/...` → Granicus (not yet supported by convene)
- something else (CivicPlus, CivicClerk, custom) → not yet supported

For Legistar, the part of the subdomain before `.legistar.com` is almost
always the client name. The exceptions are cities like NYC and DC that
front the portal with their own domain, in which case you can usually find
the client name by opening one of the in-page links and looking at the
underlying URL.

You can sanity-check the client name by hitting:

```
curl 'https://webapi.legistar.com/v1/<client>/events?$top=1' -H 'Accept: application/json'
```

A 200 with a meeting in it means you found the right one. A 404 means try
again.

## Step 2: Add the jurisdiction

Open [`src/convene/registry.py`](../src/convene/registry.py) and add a row:

```python
Jurisdiction(
    slug="pittsburgh",                         # what users type on the CLI
    name="Pittsburgh, PA",                     # human-readable
    platform="legistar",
    client="pittsburgh",                       # from step 1
    portal_url="https://pittsburgh.legistar.com",
),
```

Then run:

```
convene events pittsburgh --limit 3
```

If meetings come through, ship a PR.

## Step 3 (only if you're not on Legistar)

The Granicus and CivicClerk adapters aren't built yet. Both expose data,
but neither has a clean public API like Legistar does, so they need real
HTML scraping. If you want one, open an issue and link a few real portal
URLs to test against.

The `LegistarAdapter` is the reference shape any new adapter should match:
yield `Event`, `Person`, and `Organization` instances from
`convene.models`, and that's it.
