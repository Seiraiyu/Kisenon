# rag-simple

Minimal retrieval-augmented generation on Kisenon in ~300 lines of Python:
chunk text files, embed them into `pgvector`, retrieve the top 5 chunks for a
question, and (optionally) have Claude answer with `[n]` citations.

It runs with no API keys at all: embeddings are computed locally with
[fastembed](https://github.com/qdrant/fastembed) (`BAAI/bge-small-en-v1.5`,
384 dimensions, CPU), and without `ANTHROPIC_API_KEY` `ask` prints the
retrieved chunks instead of an answer.

This is an integration example: it proves "pgvector RAG works on Kisenon".
For what branching adds — re-indexing on a fork and comparing retrieval
quality against `main` — see [`examples/rag-complex`](../rag-complex/).

## What you need

- A Kisenon account and a project. `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- ~150 MB of disk for the local embedding model (downloaded on first run).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <project-id>` | **Required** | Exits 2 with `DATABASE_URL is not set`. |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | Optional | `ask` prints the top 5 chunks instead of a cited answer. |
| `VOYAGE_API_KEY` | [dashboard.voyageai.com](https://dashboard.voyageai.com/) | Optional | Only needed for `--embedder voyage`; that flag exits 2 without it. |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) | Optional | Only needed for `--embedder openai`; that flag exits 2 without it. |

## Setup

```bash
cd examples/rag-simple
uv sync
cp .env.example .env
# edit .env: DATABASE_URL=<output of the command below>
keon connection-string main --project <project-id>
```

Everything lives in its own `rag_simple` schema (`rag_simple.chunks`,
`rag_simple.meta`), created on first `ingest`. The CLI runs
`CREATE EXTENSION IF NOT EXISTS vector` for you.

## Demo

### 1. Ingest the sample corpus

`corpus/` holds this repo's README plus three public-domain Project Gutenberg
excerpts (see [`SOURCES.md`](SOURCES.md)).

```bash
uv run rag-simple ingest corpus
```

```
[ingested: file=corpus/alice-ch1.txt | chunks=21]
[ingested: file=corpus/kisenon-readme.md | chunks=9]
[ingested: file=corpus/pride-and-prejudice-ch1.txt | chunks=8]
[ingested: file=corpus/sherlock-scandal-in-bohemia.txt | chunks=83]
Ingested 121 chunks from 4 files.
{"files": 4, "chunks": 121, "embedder": "fastembed", "dim": 384, "duration_ms": 16201}
```

Re-running `ingest` is idempotent: each file's old chunks are deleted before
its new ones are inserted.

### 2. Ask a question

```bash
uv run rag-simple ask "What does Kisenon give an AI agent?"
```

Without `ANTHROPIC_API_KEY`, the top 5 chunks are printed instead and stderr
says so (real output, chunk text trimmed):

```
[retrieved: hits=5 | top_score=0.8171]
[no ANTHROPIC_API_KEY: action=printing retrieved chunks instead of an answer]
[1] corpus/kisenon-readme.md (chunk 0, score 0.8171)
# Kisenon

> **The execution environment for AI database agents.**

Give Claude Code, Cursor, or your own AI agent a disposable fork of your PostgreSQL database. …

[2] corpus/kisenon-readme.md (chunk 1, score 0.7937)
…
[5] corpus/kisenon-readme.md (chunk 3, score 0.6615)
…
{"question": "What does Kisenon give an AI agent?", "answer": null, "model": null, "embedder": "fastembed", "hits": [{"source": "corpus/kisenon-readme.md", "ord": 0, "score": 0.8171}, {"source": "corpus/kisenon-readme.md", "ord": 1, "score": 0.7937}, {"source": "corpus/kisenon-readme.md", "ord": 5, "score": 0.74}, {"source": "corpus/kisenon-readme.md", "ord": 2, "score": 0.7272}, {"source": "corpus/kisenon-readme.md", "ord": 3, "score": 0.6615}]}
```

With `ANTHROPIC_API_KEY` set you get a cited answer, then the same sources
(shape only; this path was not run live, see Limitations):

```
[retrieved: hits=5 | top_score=0.8171]
Answer: <answer text with [n] citations>

Sources:
[1] corpus/kisenon-readme.md (chunk 0, score 0.8171)
...
{"question": "What does Kisenon give an AI agent?", "answer": "...", "model": "claude-sonnet-5", "embedder": "fastembed", "hits": [...]}
```

### 3. Switch embedders

```bash
uv run rag-simple ingest corpus --embedder voyage           # exits 2: dimension mismatch
uv run rag-simple ingest corpus --embedder voyage --reset   # 121 chunks, "dim": 1024
uv run rag-simple ask "Who is Irene Adler?" --embedder voyage
```

```
{"error": "chunks were embedded with dim=384, this embedder is dim=1024. Re-ingest with --reset (or use the embedder you ingested with)."}
...
[retrieved: hits=5 | top_score=0.6332]
[1] corpus/sherlock-scandal-in-bohemia.txt (chunk 27, score 0.6332)
...
```

Run `uv run rag-simple ingest corpus --reset` to go back to fastembed.

## Flags

| Command / flag | Meaning |
|---|---|
| `ingest DIR` | Chunk + embed every `.md`/`.txt` file under `DIR`. |
| `ingest --reset` | Drop and recreate `rag_simple.chunks` + `rag_simple.meta` first. |
| `ask QUESTION` | Retrieve and answer. |
| `ask --k N` | Chunks to retrieve (default 5). |
| `--embedder fastembed\|voyage\|openai` | Embedding model (default `fastembed`). Use the same one for `ingest` and `ask`. |

Chunking: paragraphs are packed into chunks of at most 800 characters; a
paragraph longer than that is cut into 800-character windows overlapping by
100, and each new chunk starts with the last 100 characters of the previous
one when that fits.

## Output and exit codes

Progress events go to **stderr**; the human answer and one JSON line go to
**stdout** (pipe to `jq`).

| Code | Meaning |
|---|---|
| `0` | OK |
| `1` | Nothing to do: no files ingested, or no chunks retrieved (run `ingest` first). |
| `2` | Setup error: missing `DATABASE_URL`/key, or embedding dimension mismatch. |

**Dimension mismatch.** The embedding dimension is stored in
`rag_simple.meta`. Switching embedders (384 → 1024 → 1536 dimensions) without
re-indexing exits 2 with `Re-ingest with --reset`.

## Limitations

- `.md` and `.txt` only; no PDF parsing (see `rag-complex`).
- Vector search only; no keyword/hybrid search or reranking (see `rag-complex`).
- Same-dimension embedder swaps are not detected, only dimension changes.
- Not verified live for this release: the Claude answer path
  (`ANTHROPIC_API_KEY`) and the `openai` embedder (`OPENAI_API_KEY`). Both are
  implemented and unit-tested offline; the fastembed and voyage paths were run
  live.
