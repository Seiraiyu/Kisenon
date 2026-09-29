# Kisenon

> **The execution environment for AI database agents.**

Give Claude Code, Cursor, or your own AI agent a disposable fork of your PostgreSQL database. Let it run **DELETE**, **ALTER**, **DROP**, **CREATE INDEX**, or any other SQL it needs to verify an answer.

When it's finished, the fork disappears.

**Production is never touched.**

---

## Why Kisenon exists

Today's AI coding agents have a problem.

They can write migrations.

They can suggest indexes.

They can generate SQL.

But they can't safely prove that their ideas actually work against production data.

So developers either:

* trust the AI,
* maintain a staging database that slowly drifts from reality,
* avoid letting the AI perform meaningful database work altogether.

None of those are satisfying.

Kisenon solves this by giving every AI task its own disposable database branch.

```
Production
      │
      ├── Branch (≈ seconds)
      │
      ▼
AI agent
  • ALTER TABLE
  • DELETE
  • CREATE INDEX
  • EXPLAIN ANALYZE
  • Run migrations
  • Execute tests
      │
      ▼
Evidence-backed answer
      │
      ▼
Branch destroyed
```

Instead of guessing...

...the AI can prove its answer.

---

## What makes Kisenon different?

Most database platforms help humans build applications.

Kisenon helps AI agents safely change databases.

Think of it like Git branches for data.

Every task gets an isolated copy of your database where the agent can experiment freely without risking production.

---

# See it in action

### Can an AI safely optimize a production query?

```
You:
"Would adding an index speed up our homepage query?"

↓

Kisenon creates a disposable database branch.

↓

The agent:

✓ runs EXPLAIN ANALYZE
✓ creates the index
✓ benchmarks again
✓ compares results

↓

Answer:

Before: 31.8 ms
After: 0.7 ms

45× faster.

↓

Sandbox destroyed.

Production unchanged.
```

The AI didn't guess.

It measured.

---

## Examples

The fastest way to understand Kisenon is to run one of the examples.

### AI agents & branching

#### AI Sandbox

Give an AI unrestricted SQL access to a disposable copy of production.

The agent can:

* DELETE rows
* DROP tables
* CREATE INDEX
* ALTER schemas
* inspect data
* benchmark queries

When the task completes, the database branch is automatically destroyed.

➡ **[examples/agent-sandbox](examples/agent-sandbox)**

---

#### AI Migration Verification

Let an AI generate and execute a migration against a disposable database.

Kisenon can:

* create the branch
* execute the migration
* run your tests
* generate a schema diff
* return the results
* destroy the branch

Your production database never changes until you decide.

➡ **[examples/agent-migrate](examples/agent-migrate)**

---

### RAG & search

#### Simple RAG

Chunk text files, embed them into pgvector, retrieve the top matches, and answer with citations. Runs with no API keys (local embeddings).

➡ **[examples/rag-simple](examples/rag-simple)**

#### Hybrid RAG + fork-based re-index experiments

pgvector + Meilisearch hybrid search with reciprocal rank fusion and reranking over ten table-heavy arXiv papers. `experiment` re-chunks and re-embeds the corpus on a disposable fork and reports recall/MRR against main, without touching main.

➡ **[examples/rag-complex](examples/rag-complex)**

---

### CI & workflow

#### Branch Testing

Run integration tests against isolated database branches.

Perfect for:

* CI
* pull requests
* feature previews
* migration validation

➡ **[examples/branch-test](examples/branch-test)**

---

### Quickstart

Connect and query a Kisenon branch from your language of choice — Node.js (`pg`), Drizzle + Next.js, or Python (`psycopg`).

➡ **[examples/quickstart](examples/quickstart)**

---

## Getting started

Kisenon is live at **[kisenon.com](https://kisenon.com)**. Create an account, then:

Install the CLI:

```bash
curl -fsSL https://kisenon.com/install.sh | bash
```

Login:

```bash
keon login
```

Create your first project:

```bash
keon projects create
```

Then pick one of the runnable examples above.

Prefer to connect directly? Grab a connection string from the dashboard and use any Postgres 17 client:

```bash
psql "postgresql://app:•••••@kisenon.com/main?endpoint=ep_…"
```

---

## Philosophy

AI agents shouldn't receive production credentials.

They should receive disposable execution environments.

A branch is more than a copy of a database.

It's a safe place for an autonomous system to think, experiment, and verify.

That is what Kisenon provides.

---

## Repository

This repository is the **public portal** for Kisenon. It contains:

* runnable examples
* integration samples
* GitHub Actions
* CLI examples
* issue tracking
* community discussions

The managed Kisenon platform itself is hosted at **[kisenon.com](https://kisenon.com)**; the platform source lives in a separate, private repository.

* **Issues** — bug reports, feature requests, design discussions: [open an issue](https://github.com/Seiraiyu/Kisenon/issues)
* **Discussions** — questions, architecture chats, feedback: [start a discussion](https://github.com/Seiraiyu/Kisenon/discussions)

### Reporting bugs

Use [GitHub issues](https://github.com/Seiraiyu/Kisenon/issues) for anything that's broken, surprising, or missing. When filing a bug:

* Include the **endpoint id** or **project slug** if it helps reproduce
* Paste the **error message** verbatim — we read every one
* Mention your **client** (psql, node-postgres, Drizzle, etc.) and version

For security issues, please email **security@kisenon.com** instead of opening a public issue.

---

## Status

* Generally available
* PostgreSQL 17
* Serverless compute
* Branching
* Cold-start endpoints
* Open-source examples
* Active development

Feedback is welcome. Please open an issue or discussion—we read every one.

---

## Data usage and privacy

When you use Kisenon, we store the data you put in your Postgres branches plus the metadata needed to operate the service (project + branch names, endpoint state, audit logs, request metrics).

We do not train models on your data. We do not share your data with third parties beyond the cloud regions you choose to run in. Full terms and privacy policy at [kisenon.com/legal](https://kisenon.com/legal).

---

## Support

* Public docs: [docs.kisenon.com](https://kisenon.com/docs)
* Email: **support@kisenon.com**
