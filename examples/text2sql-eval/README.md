# text2sql-eval

Grade an LLM's text-to-SQL against a real copy of your database — including
questions that *change data*, like "delete inactive users who never ordered".
Every run gets a disposable Kisenon fork; writes are rolled back with
`keon branches reset` between cases, and the fork is deleted at the end.

## Why this needs Kisenon

Text-to-SQL evals usually stop at `SELECT`, because grading a `DELETE`
means running it. Against a shared staging database that corrupts every
later case; against production it's unthinkable. Here each run forks `main`
(a few seconds, including the wait until the fork accepts connections), the
model's SQL runs for real, and after any statement that wrote, the fork is
reset to `main` so the next case starts clean. Main is never written.

## What you need

- A Kisenon account, `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- `psql`, Python 3.11+, [uv](https://docs.astral.sh/uv/).
- An LLM key (see below).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KISENON_PROJECT_ID` | `keon projects list -o json` | required | exit 2 before anything runs |
| `KISENON_URL` | `keon connection-string main --project <id>` | setup only | you can't apply `setup.sql` |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | required for `--provider anthropic` (default) | exit 2: `ANTHROPIC_API_KEY is not set.` — no fork is created |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) | only for `--provider openai` | same, for that provider |

## Setup

```bash
cd examples/text2sql-eval
uv sync
cp .env.example .env        # fill in KISENON_PROJECT_ID, KISENON_URL, ANTHROPIC_API_KEY
set -a; . ./.env; set +a
psql "$KISENON_URL" -f setup.sql
```

`setup.sql` creates schema `text2sql_eval` on `main` with 1,000 users and
5,000 orders. The data is deterministic, so the expected answers in
`cases.yaml` are fixed.

## Demo

```bash
uv run text2sql-eval
```

Output (stderr events, then the table and one JSON line on stdout):

```text
[eval start: 9 | provider=anthropic | model=claude-sonnet-5]
[branch forked: db05a148-e3d0-4437-bfc3-d47759e3ee72 | duration_ms=6743]
[case: active-users | sql=SELECT COUNT(*) AS active_users_count FROM users WHERE active = TRUE]
[case done: active-users | match=exact | reason=exact match | reset=False]
...
[case: delete-inactive-no-orders | sql=DELETE FROM users WHERE active = false   AND NOT EXISTS (     SELECT 1 FROM orders WHERE orders.user_id = users.id   )]
[branch reset: db05a148-e3d0-4437-bfc3-d47759e3ee72]
[case done: delete-inactive-no-orders | match=rowcount | reason=rowcount 100 | reset=True]
[case: total-users-after-reset | sql=SELECT COUNT(*) AS total_users FROM users]
[case done: total-users-after-reset | match=exact | reason=exact match | reset=False]
[case: refund-pending | sql=UPDATE orders SET status = 'refunded' WHERE status = 'pending']
[branch reset: db05a148-e3d0-4437-bfc3-d47759e3ee72]
[case done: refund-pending | match=rowcount | reason=rowcount 500 | reset=True]
case                         exec  match     reason
active-users                 ok    exact     exact match
users-per-country            ok    exact     exact match
paid-revenue                 ok    exact     exact match
top-spenders                 ok    exact     exact match
pending-orders               ok    exact     exact match
stale-users                  ok    exact     exact match
delete-inactive-no-orders    ok    rowcount  rowcount 100
total-users-after-reset      ok    exact     exact match
refund-pending               ok    rowcount  rowcount 500
Score: 9/9 passed (exact 7, set 0, rowcount 2, executed 9, resets 2)
{"branch": {"name": "text2sql-eval-71fd7cc4", "id": "db05a148-e3d0-4437-bfc3-d47759e3ee72", "kept": false}, "provider": "anthropic", "model": "claude-sonnet-5", "passed": 9, "total": 9, "cases": [...]}
```

The whole run took about a minute. Each `branch reset` took about 1.7 s,
measured from the write to the `[branch reset]` event.

`total-users-after-reset` only passes if the fork really was reset after the
`DELETE` before it — that case is the proof.

## Writing your own cases

```yaml
cases:
  - id: my-case
    question: How many orders were refunded?
    expected_rows: [[500]]          # or expected_rowcount: N for writes
    ordered: false                  # true = row order must match too
```

Scoring: `exact` (same rows, same order), `set` (same rows, any order —
not allowed when `ordered: true`), `rowcount` (writes), or fail with a
reason. Point `--cases` at your file and your own schema's search_path by
editing `SCHEMA` in `runner.py`.

## Flags

| Flag | Meaning |
|---|---|
| `--cases PATH` | Case file. Default `cases.yaml`. |
| `--provider {anthropic,openai}` | Default `anthropic`. |
| `--model ID` | Default `claude-sonnet-5` / `gpt-5.1`. |
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `--keep` | Keep the fork afterwards (prints its id in the JSON). |
| `--pretty` | Only print the table, no JSON line. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every case passed. |
| `1` | At least one case failed. |
| `2` | Setup failure: missing env/key, bad `cases.yaml`, `keon` or LLM error. |

## Limitations

- One fork per run, reset after writes. The reset goes to `main`'s *current*
  head, so if something writes to `main` mid-run, later cases see it.
- The model sees column names and types only (no sample rows, no comments).
- One statement per case; the model is told so, but a multi-statement reply
  is executed as-is and graded on the last statement's result.
- `--provider openai` is untested unless noted in the PR.
