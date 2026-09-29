# pii-masked-fork

Give an AI agent (or a contractor, or your laptop) a real copy of production
— minus the personal data. `pii-masked-fork` forks `main`, masks the columns
you list in `mask.yaml`, **scans every text column for anything that still
looks like an email, phone number or SSN**, and only then hands you the
masked branch. If anything leaks, the fork is deleted.

## Why this needs Kisenon

The usual way to get a safe dev database is a nightly dump → scrub → restore
pipeline that's hours stale and costs a second server. With Kisenon the copy
is a copy-on-write fork of `main` that is ready in a few seconds; masking rewrites only the
columns you name; production is never modified or exposed to the consumer
of the masked branch.

## What you need

- A Kisenon account, `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- `psql`, Python 3.11+, [uv](https://docs.astral.sh/uv/).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KISENON_PROJECT_ID` | `keon projects list -o json` | required | exit 2 |
| `KISENON_URL` | `keon connection-string main --project <id>` | setup only | you can't apply `setup.sql` |

No LLM or other third-party key is used.

## Setup

```bash
cd examples/pii-masked-fork
uv sync
cp .env.example .env        # fill in KISENON_PROJECT_ID and KISENON_URL
set -a; . ./.env; set +a
psql "$KISENON_URL" -f setup.sql
```

`setup.sql` creates schema `pii_masked_fork` with 5,000 synthetic customers
(email, name, phone, SSN, loyalty id, free-text notes) and 20,000 orders.

## Demo 1 — a masked branch

```bash
uv run pii-masked-fork
```

Real output (connection URL elided):

```text
[mask start: pii_masked_fork | tables=1]
[branch forked: 3a54fc8c-f614-4cf1-a973-da484bf19fe5 | duration_ms=2383]
[masked: customers.phone | rows=5000]
[masked: customers.ssn | rows=5000]
[masked: customers.loyalty_id | rows=5000]
[masked: customers.notes | rows=5000]
[masked: customers.email | rows=5000]
[masked: customers.full_name | rows=5000]
Masked branch: pii-masked-fork-f15a10de (3a54fc8c-f614-4cf1-a973-da484bf19fe5)
Verified: no PII detector hits (sampled up to 1000 rows per text column)
Connect: postgresql://…
{"branch": {"name": "pii-masked-fork-f15a10de", "id": "3a54fc8c-f614-4cf1-a973-da484bf19fe5", "url": "postgresql://…", "deleted": false}, "masked": {"customers.phone": 5000, "customers.ssn": 5000, "customers.loyalty_id": 5000, "customers.notes": 5000, "customers.email": 5000, "customers.full_name": 5000}, "leaks": [], "sample": 1000}
```

`duration_ms` is the whole `keon branches create --wait` round-trip (fork
plus waiting for the endpoint to be ready). On the masked branch:

```text
 id |          email          |     full_name     |  phone   | ssn |            loyalty_id            |  notes
----+-------------------------+-------------------+----------+-----+----------------------------------+----------
  1 | vanessa89@example.org   | Peter Montgomery  | REDACTED |     | 5d0c1ff283d87d6b0c5e085277890793 | REDACTED
  2 | corey15@example.com     | Theodore Mcgrath  | REDACTED |     | 2e4c6588aaaec030ac3b6c89a78c3535 | REDACTED
  3 | gomezleslie@example.net | Stephanie Collins | REDACTED |     | 97e82c5fc2974e333a9b5ec432f9fa56 | REDACTED
```

`main` still has `person1@acme-mail.com` for customer 1.

Point your agent at the `Connect:` URL. The branch stays until you delete it:
`keon branches delete --cascade <id>`.

## Demo 2 — forget a column, get caught

The `notes` column is free text that happens to contain emails and phone
numbers. Drop it from the spec:

```bash
sed '/notes:/d' mask.yaml > /tmp/mask-no-notes.yaml
uv run pii-masked-fork --mask /tmp/mask-no-notes.yaml; echo "exit=$?"
```

```text
[mask start: pii_masked_fork | tables=1]
[branch forked: 14445a9b-24e9-4192-8180-9c348d80ac7f | duration_ms=3619]
[masked: customers.phone | rows=5000]
[masked: customers.ssn | rows=5000]
[masked: customers.loyalty_id | rows=5000]
[masked: customers.email | rows=5000]
[masked: customers.full_name | rows=5000]
[branch deleted: 14445a9b-24e9-4192-8180-9c348d80ac7f]
LEAKS FOUND — masked branch deleted. Add these columns to mask.yaml:
  customers.notes          phone    103 hits  e.g. Cal***
  customers.notes          email    105 hits  e.g. Pre***
{"branch": {"name": "pii-masked-fork-58fd6bc4", "id": "14445a9b-24e9-4192-8180-9c348d80ac7f", "url": null, "deleted": true}, "masked": {"customers.phone": 5000, "customers.ssn": 5000, "customers.loyalty_id": 5000, "customers.email": 5000, "customers.full_name": 5000}, "leaks": [{"table": "customers", "column": "notes", "detector": "phone", "hits": 103, "example": "Cal***"}, {"table": "customers", "column": "notes", "detector": "email", "hits": 105, "example": "Pre***"}], "sample": 1000}
exit=1
```

Every text column in the schema is scanned, listed in `mask.yaml` or not.

## `mask.yaml`

```yaml
schema: pii_masked_fork
tables:
  customers:
    email: faker:safe_email   # any Faker provider: name, address, company, …
    full_name: faker:name
    phone: redact             # 'REDACTED' (NULLs stay NULL)
    ssn: "null"               # quote it — bare null also works
    loyalty_id: hash          # md5: stable, so joins on it still work
    notes: redact
```

Faker columns need a single-column primary key. Faker output is seeded, so
re-running produces the same fake values.

## Detectors

| Name | Pattern (simplified) | Notes |
|---|---|---|
| `email` | `x@domain.tld` | `example.com/org/net` allowed (what `faker:safe_email` emits) |
| `phone` | `+1-555-123-4567`, `555.123.4567 …` | separators required |
| `ssn` | `123-45-6789` | US format |

## Flags

| Flag | Meaning |
|---|---|
| `--mask PATH` | Spec. Default `mask.yaml`. |
| `--sample N` | Rows sampled per text column. Default 1000. |
| `--delete` | Delete the fork after verification (dry run). |
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `--pretty` | No JSON line. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Masked and verified; branch kept (unless `--delete`). |
| `1` | Detectors found PII; the fork was deleted. |
| `2` | Setup failure (bad spec, `keon` error, masking SQL failed); the fork was deleted. |

## Limitations

- Detection is regex sampling, not proof. Names, addresses and free-form
  secrets aren't detected — list those columns explicitly.
- The fork holds raw data for the few seconds between fork and masking.
  For masking that happens *before* anyone can connect, see
  `keon sandbox create --masking-policy <id>`.
- The printed connection URL contains the branch password; treat it like one.
- Only text-like columns are scanned; `jsonb` isn't.
