# agent-memory

Long-term memory for an LLM agent, in plain Postgres. Every turn is stored as an
**episode**; durable **facts** are extracted by the LLM, embedded, de-duplicated by
similarity, and recalled with a **similarity x recency** score.

Bonus: `--what-if` runs a conversation on a throwaway fork of `main`, so everything the
agent "learns" there is discarded with the fork. Useful for testing prompts or
personas without polluting real memory.

## What you need

- A Kisenon project and `keon` logged in (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- `pgvector` (available on Kisenon; the example runs `CREATE EXTENSION IF NOT EXISTS vector`).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <id>` | required | exits 2 |
| `KISENON_PROJECT_ID` | `keon projects list -o json` | only for `--what-if` | `--what-if` exits 2 |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | optional | replies just list recalled facts; each user message is stored verbatim as a fact |
| `VOYAGE_API_KEY` | [dash.voyageai.com](https://dash.voyageai.com) | optional | `--embedder voyage` exits 2; default local `fastembed` works |

## Setup

```bash
cd examples/agent-memory
uv sync
cp .env.example .env   # fill in DATABASE_URL (+ KISENON_PROJECT_ID, keys as needed)
```

Tables are created on first run in schema `agent_memory` (`meta`, `episodes`, `facts`).
The first run downloads the `BAAI/bge-small-en-v1.5` model (about 70 MB) into `FASTEMBED_CACHE_PATH` (default: a temp dir). Set it to a persistent folder to skip re-downloads.

## Demos

### 1. Teach it something, then use it

```bash
uv run agent-memory say "I'm vegetarian and I just moved to Lisbon." "Where should I go for dinner tonight?"
```

Expected (stderr events, then stdout):

```
[recall: 0]
[fact added: User is vegetarian]
[fact added: User recently moved to Lisbon]
You: I'm vegetarian and I just moved to Lisbon.
Assistant: ...
[recall: 2]
You: Where should I go for dinner tonight?
Assistant: ... (suggests vegetarian places in Lisbon)
{"session":"default","turns":[...],"what_if":null,"embedder":"fastembed","model":"claude-sonnet-5"}
```

### 2. Inspect recall

```bash
uv run agent-memory recall "food preferences"
```

```
0.6xx  (sim 0.6xx, recency 1.00)  User is vegetarian
...
```

Say the same thing twice and the fact is **merged** (`[fact merged: ...]`, `hits` +1,
`last_seen` refreshed) instead of duplicated.

### 3. What-if: a conversation that leaves no trace

```bash
uv run agent-memory say --what-if "Actually, I started eating fish last month."
```

```
[fork created: agent-memory-1a2b3c4d | id=...]
[fact added: User started eating fish last month]
...
[fork deleted: ...]
{"...","what_if":{"branch":"agent-memory-1a2b3c4d","deleted":true,"main_facts_before":2,"main_facts_after":2}}
```

The fork is a copy-on-write clone of `main` (so recall sees all real memories), but the
new fact dies with it: `main_facts_before == main_facts_after`. Add `--keep` to keep the
fork for inspection (the cleanup command is printed).

### 4. Key-free

```bash
env -u ANTHROPIC_API_KEY uv run agent-memory say "I prefer window seats."
```

```
[no ANTHROPIC_API_KEY: key-free: user messages stored verbatim as facts]
[recall: ...]
[fact added: I prefer window seats.]
You: I prefer window seats.
Assistant: Recalled: ...
```

## Flags

| Flag | Meaning |
|---|---|
| `say MESSAGE...` | One or more user turns, in order. |
| `recall QUERY [--k 5]` | Show recalled facts with scores; no LLM. |
| `--session NAME` | Episode thread used as short-term history (default `default`). |
| `--embedder fastembed\|voyage` | Default `fastembed` (384-d). `voyage` = `voyage-4-lite` (1024-d). |
| `--reset` | Drop and recreate `agent_memory` (needed after switching embedder). |
| `--what-if` / `--keep` | Run on a throwaway fork / keep it afterwards. |
| `--model ID` | Anthropic model (default `claude-sonnet-5`). |

Exit codes: `0` ok · `2` setup error (missing env/key, `keon` missing, embedding-dimension mismatch).

## How it works

- `facts.embedding vector(N)` with an HNSW cosine index; `meta.embedding_dim` is checked on
  startup so a different embedder fails fast instead of corrupting the table.
- Dedupe: if the nearest existing fact has cosine similarity >= 0.9 the new one is merged.
- Recall: 50 nearest facts via HNSW, re-ranked by `similarity x 0.5^(age_days / 30)`.

## Limitations

- Facts are never contradicted or expired automatically ("I eat fish now" adds a fact, it
  doesn't retire "User is vegetarian").
- One user per database schema; add a `user_id` column for multi-tenant use.
- For a branching-first example see [`agent-sandbox`](../agent-sandbox/).
