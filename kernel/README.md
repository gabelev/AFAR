# afar kernel

The Python side of AFAR: players, staff, conductor, append-only log.

```bash
uv sync --extra dev
uv run pytest
```

Requires the `ensemble` framework checked out at `../../moldzine/ensemble`
(editable path dep). All tests run offline against mocks; live runs need the
keys in `.env.example`.
