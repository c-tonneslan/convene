# Writing a new adapter

convene currently ships two adapters: `LegistarAdapter` and `GranicusAdapter`.
Other meeting platforms (CivicClerk, PrimeGov, eScribe) need their own.

An adapter is just a class that yields convene model instances. The contract
is small:

```python
class MyAdapter:
    def __init__(self, jurisdiction, *, client=None):
        ...

    def events(self, **kwargs) -> Iterator[Event]:
        ...

    # Optional: only implement these if the platform exposes them
    def organizations(self) -> Iterator[Organization]: ...
    def people(self) -> Iterator[Person]: ...
    def matters(self, **kwargs) -> Iterator[Matter]: ...
    def memberships(self, person_id) -> Iterator[Membership]: ...
```

Look at [`src/convene/adapters/legistar.py`](https://github.com/c-tonneslan/convene/blob/main/src/convene/adapters/legistar.py)
for the full-featured version and
[`src/convene/adapters/granicus.py`](https://github.com/c-tonneslan/convene/blob/main/src/convene/adapters/granicus.py)
for a thinner one.

## Tips

- Use `httpx.Client` and accept a `client` kwarg so tests can swap in a
  `MockTransport`. The convene test suite never hits the network.
- Wrap network and parse errors in a per-adapter exception type that subclasses
  `RuntimeError`. The CLI catches both `LegistarError` and `GranicusError`
  uniformly; yours should be added to that list.
- Build the OCD-style IDs as `f"ocd-event/{client}-{native_id}"`,
  `f"ocd-bill/{client}-{native_id}"`, etc. The shape is loose; the goal is
  uniqueness within a jurisdiction.
- Extend the `Platform` literal in `src/convene/registry.py` and add a branch
  in `convene.adapters.for_jurisdiction`.

## Tests

Mirror the existing tests: freeze a real response as a fixture, route an
`httpx.MockTransport` to it, and assert on the resulting models. The suite
in `tests/test_legistar.py` and `tests/test_granicus.py` covers about 80% of
what you'd want.
