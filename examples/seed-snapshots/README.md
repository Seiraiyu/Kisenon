# seed-snapshots

Stop re-seeding your test database. Build named fixture branches once —
`fixture-empty`, `fixture-small`, `fixture-prodlike` — then let a pytest
plugin fork the one you want per test session and **reset** the fork after
each test. Every test starts from the exact fixture state, however
destructive the previous test was.

## Why this needs Kisenon

Re-seeding a database for every test session (or every test) is the slow
part of most integration suites, and it grows with the dataset. A Kisenon
fork is copy-on-write, so forking a million-row fixture costs about the same
as forking an empty one, and `keon branches reset` rewinds a fork to its
parent in one call. `seed-snapshots timing` measures both against re-seeding
on your own project.

## What you need

- A Kisenon account and project, `keon` CLI logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KISENON_PROJECT_ID` | `keon projects list -o json` | required | CLI exits 2; the pytest plugin stops the session with exit 2 |
| Kisenon auth | `keon login`, or `KEON_API_KEY` (project-scoped `read_write` key) in CI | required | exits 2 with the `keon` error |

No third-party keys.

## Setup

```bash
cd examples/seed-snapshots
uv sync
cp .env.example .env     # fill KISENON_PROJECT_ID
```

Build the fixture branches once. Each is forked from `main` and seeded into
the `seed_snapshots` schema:

| Branch | users | orders |
|---|---|---|
| `fixture-empty` | 0 | 0 |
| `fixture-small` | 100 | 1,000 |
| `fixture-prodlike` | 100,000 | 1,000,000 |

```bash
uv run seed-snapshots build
```

```text
[built fixture-empty: 1097ms | id=...]
[built fixture-small: 1345ms | id=...]
[built fixture-prodlike: 12064ms | id=...]
built 3 fixture branch(es)
{"built": [{"fixture": "empty", "branch": "fixture-empty", "id": "...", "seed_ms": 1097}, ...]}
```

(Real run against a Kisenon project; `seed_ms` is the seeding time, not
counting the branch create.)

Existing fixture branches are skipped; `--rebuild` deletes and re-seeds
them, `--fixture small` limits the build to one.

## Demo 1 — destructive tests that don't leak

`demo_tests/test_orders.py` deletes every order, then checks the orders are
back; drops the users table, then checks users are back.

```bash
uv run pytest demo_tests -v
uv run pytest demo_tests -v --kisenon-fixture prodlike
```

```text
demo_tests/test_orders.py::test_delete_every_order PASSED
demo_tests/test_orders.py::test_orders_are_back_after_reset PASSED
demo_tests/test_orders.py::test_drop_users_table PASSED
demo_tests/test_orders.py::test_users_are_back_after_reset PASSED

4 passed in 28.69s
```

The prodlike run passed the same 4 tests in 27.21s. That wall time includes
the session fork, four `branches reset` calls and the fork's deletion.

Use it in your own suite by installing this package (the plugin registers
itself through the `pytest11` entry point) and requesting `kisenon_db`:

```python
import psycopg

def test_checkout(kisenon_db):          # a connection URL for the session fork
    with psycopg.connect(kisenon_db) as conn:
        ...
```

| Fixture / option | Meaning |
|---|---|
| `kisenon_db` | Function-scoped connection URL. The fork is reset to the fixture after each test. |
| `kisenon_fork` | Session-scoped `Branch(name, id)` forked from `fixture-<name>`; deleted at session end. |
| `--kisenon-fixture NAME` | Which fixture branch to fork. Default `small`. |
| `--kisenon-keep` | Keep the session fork; prints the delete command. |

## Demo 2 — timing: re-seed vs fork vs reset

```bash
uv run seed-snapshots timing --fixture prodlike --runs 3
```

Output shape (the numbers are yours to measure: `timing` was not run
during this example's verification, so no figures are claimed here):

```text
fixture=prodlike runs=3
method                    p50_ms  runs_ms
re-seed (SQL)                ...  [...]
fork fixture branch          ...  [...]
reset fork to fixture        ...  [...]
{"fixture": "prodlike", "runs": 3, "p50_ms": {...}, "runs_ms": {...}}
```

For scale: seeding `fixture-prodlike` during `build` took 12064 ms, and
each demo session above (one fork, four resets) took about 28 s in total.

Each "fork" and "reset" timing includes getting the connection string,
connecting, and counting orders — i.e. until the data is usable. The
re-seed uses server-side `generate_series`, the fastest seeding there is;
factory-based seeding in a real suite is slower, so the gap is a lower bound.

## Flags and exit codes

| Command | Flags |
|---|---|
| `build` | `--fixture {empty,small,prodlike}` (repeatable), `--rebuild`, `--project ID` |
| `timing` | `--fixture NAME` (default `prodlike`), `--runs N` (default 3), `--project ID` |

Exit codes: `0` ok, `1` a database error during a run, `2` setup error
(missing env, `keon` missing or failing, fixture branch not built).

## Removing the fixture branches

Fixture branches are long-lived by design. To delete them:

```bash
keon branches list --project "$KISENON_PROJECT_ID" -o json \
  | jq -r '.branches[] | select(.name | startswith("fixture-")) | .id' \
  | xargs -n1 keon branches delete --cascade
```

## Tests

```bash
uv run pytest       # offline: keon and Postgres are mocked
uv run ruff check .
```

## Limitations

- The plugin resets after every test, including read-only ones. If most of
  your tests only read, a session-scoped connection without resets is faster.
- Fixtures are forked from `main` when built; rebuild them
  (`build --rebuild`) after schema changes on `main`.
- The demo's "are back" tests rely on pytest's default in-file order. Under
  `pytest-xdist` each worker gets its own session fork, which works but
  multiplies forks.
