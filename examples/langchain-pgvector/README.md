# langchain-pgvector

LangChain's Postgres vector store ([`langchain-postgres`](https://github.com/langchain-ai/langchain-postgres)
`PGVectorStore`) running on Kisenon, with ingest and a retrieval chain in one ~100-line file.
Embeddings are computed locally with `fastembed` (`BAAI/bge-small-en-v1.5`, 384-d), so
no embedding key is needed.

> `PGVector` (the older class) has been deprecated since langchain-postgres 0.0.14. This example
> uses `PGEngine` + `PGVectorStore`, which also let you choose the schema.

## What you need

- A Kisenon project (`keon login`), Python 3.11+, [uv](https://docs.astral.sh/uv/).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <id>` | required | exits 2 |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | optional | `ask` prints the 4 retrieved chunks instead of an answer |

## Setup

```bash
cd examples/langchain-pgvector
uv sync
cp .env.example .env   # set DATABASE_URL
```

The first run downloads the embedding model (~65 MB) from Hugging Face.

## Demo

```bash
uv run python app.py ingest corpus/
```
```
Ingested 3 chunks into langchain_pgvector.docs
{"chunks": 3, "table": "langchain_pgvector.docs"}
```

```bash
uv run python app.py ask "How long does it take to create a branch?"
```
```
Creating a branch takes a few seconds no matter how large the parent is, because no data is copied up front — the fork shares storage pages with its parent until either side writes. [branching.md]
{"question": "How long does it take to create a branch?", "answer": "Creating a branch takes a few seconds ...", "sources": ["branching.md", "sandboxes.md", "vectors.md"]}
```

Key-free: `ANTHROPIC_API_KEY= uv run python app.py ask "What is a sandbox budget?"` prints the
retrieved chunks, best match first (an empty value overrides `.env`; `env -u` does not, because
the app reloads `.env`):

```
[sandboxes.md]
# Sandboxes for AI agents

A sandbox is a branch with guard rails for autonomous agents. It has a budget: a
...
{"question": "What is a sandbox budget?", "answer": null, "sources": ["sandboxes.md", "branching.md", "vectors.md"]}
```

Re-running `ingest` drops and recreates the table (`overwrite_existing=True`).

## Swap the embedder

Replace `LocalEmbeddings()` with `VoyageAIEmbeddings(model="voyage-4-lite")` from
`langchain-voyageai` (needs `VOYAGE_API_KEY`), set `DIM = 1024`, then re-run `ingest`.

## LlamaIndex instead?

LlamaIndex's `PGVectorStore.from_params(...)` (`llama-index-vector-stores-postgres`) works
against the same `DATABASE_URL`; it creates its own table layout.

## Next

This example only shows that the stack works on Kisenon. To see why branching matters for RAG, see the
branching examples in the root README.
