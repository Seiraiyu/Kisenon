# rag-complex

A production-shaped hybrid RAG pipeline over ten arXiv papers full of tables,
and an `experiment` command that re-indexes the whole corpus **on a
disposable fork of `main`** so you can compare a new chunker or embedder
against the live index before you touch it.

- **Parse:** [MinerU](https://github.com/opendatalab/MinerU) 3.4.5, `pipeline`
  backend (tables as HTML, formulas as LaTeX). The parsed output is committed
  in `corpus/parsed/`, so you never need MinerU or a GPU to run the demo.
- **Chunk:** one chunk per MinerU block; headers, footers and page numbers
  are dropped. Titles become their own chunk and set a running
  `heading_context` (`Paper > 3 Results > 3.1 Ablations`) carried by every
  chunk after them. Tables stay HTML.
- **Embed:** token-budget batching. A failing batch is halved recursively;
  a single chunk that still fails gets a zero vector and a warning, so one
  bad chunk never fails the job.
- **Store:** Postgres (`rag_complex` schema, pgvector HNSW) **and**
  Meilisearch (index `chunks_<branch>`).
- **Search:** pgvector top 2k and Meilisearch top 2k, fetched concurrently,
  fused with reciprocal rank fusion (k = 60), optionally reranked with Voyage
  `rerank-2`. Every hit shows *why* it ranked: `{vector, keyword, rerank}`.

## Why this needs Kisenon

Changing how you chunk or embed means re-indexing everything. Normally that
means a second database, or a maintenance window, or re-indexing `main` and
hoping retrieval didn't get worse.

`rag-complex experiment` forks `main` in a few seconds, re-chunks and
re-embeds the full corpus *into the fork* (and a fork-only Meilisearch
index), runs the same 30 eval questions against `main` and the fork, prints
recall and MRR side by side, then deletes the fork and its index. `main`
is never written. If the fork wins, you re-run `ingest --reset` on `main`
with the winning flags.

## What you need

- A Kisenon account and project; `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- Docker (for Meilisearch; MinerU only if you re-parse PDFs).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <project-id>` | **Required** | Exits 2. |
| `KISENON_PROJECT_ID` | `keon projects list -o json` | Required for `experiment` | `experiment` exits 2; other commands work. |
| `MEILI_MASTER_KEY` | Make one up: `openssl rand -hex 16` (local container) | **Required** | `docker compose up` refuses to start; CLI exits 2 "Meilisearch is not reachable". |
| `VOYAGE_API_KEY` | [dashboard.voyageai.com](https://dashboard.voyageai.com/) | Optional | No rerank step (stderr says `skipping rerank`); `--embedder voyage` exits 2. |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | Optional | `ask` prints the ranked hits instead of a cited answer. |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) | Optional | `--embedder openai` exits 2. |

## Setup

```bash
cd examples/rag-complex
uv sync
cp .env.example .env
# edit .env: DATABASE_URL, KISENON_PROJECT_ID, MEILI_MASTER_KEY (+ optional keys)
docker compose up -d          # Meilisearch on :7700
```

## Demo

### 1. Ingest (from the committed MinerU cache)

```bash
uv run rag-complex ingest
```

```
[ingested: source=2112.09118 | chunks=118 | duration_ms=13081]
[ingested: source=2201.03545 | chunks=135 | duration_ms=12662]
…
[ingested: source=2401.18059 | chunks=154 | duration_ms=13981]
Ingested 1278 chunks from 10 documents into chunks_main + rag_complex.chunks.
{"documents": 10, "chunks": 1278, "chunker": "block", "embedder": "fastembed", "dim": 384, "index": "chunks_main", "duration_ms": 118342}
```

The first run also downloads the fastembed model (`BAAI/bge-small-en-v1.5`).

### 2. Search, and see why each hit ranked

```bash
uv run rag-complex search "execution accuracy of Codex on the Spider dev set" --k 5
```

```
 1. [2204.00498 p.1] Evaluating the Text-to-SQL Capabilities of Large Language Models > 1 I
    rrf=0.03154 vector=6 keyword=1 rerank=0.9531
    We find that Codex achieves a competitive performance of up to 67% execution accuracy on the Spider development set. We analyze the predicted queries that autom
 2. [2204.00498 p.2] Evaluating the Text-to-SQL Capabilities of Large Language Models > 3 Z
    rrf=0.03202 vector=1 keyword=4 rerank=0.9023
    Codex provides a strong baseline for Text-to-SQL tasks In Table 1 the best performing model (davinci-codex, Create Table + Select 3) achieves 67% execution accu
 3. [2204.00498 p.2] Evaluating the Text-to-SQL Capabilities of Large Language Models > 2 E
    rrf=0.01613 vector=None keyword=2 rerank=0.8828
    Table 2: Spider development set performance across prompt styles on the davinci-codex model, as measured by percentage of predictions which are valid SQL (VA),
 …
{"query": "execution accuracy of Codex on the Spider dev set", "mode": "hybrid", "hits": [{"id": "483aa35c8863a80cf3ca23c7-10", "source": "2204.00498", "page_start": 1, "page_end": 1, "heading_context": "Evaluating the Text-to-SQL Capabilities of Large Language Models > 1 Introduction", "score": 0.03154, "contributions": {"vector": 6, "keyword": 1, "rerank": 0.9531}}, …]}
```

`vector` / `keyword` are 1-based ranks in each list (`null` = not in that
list's top 2k); `rerank` is the Voyage relevance score when rerank ran. Hit 3
never made the vector list: Meilisearch alone brought it in. Hit 1 was 6th by
vector but 1st by keyword, and the reranker put it on top.
`--mode semantic` or `--mode keyword` uses one list only.

Without `VOYAGE_API_KEY` the same pipeline runs with no rerank step:

```
$ uv run rag-complex search "tree of thoughts game of 24 success rate" --k 3
[no VOYAGE_API_KEY: action=skipping rerank]
 1. [2305.10601 p.5] Tree of Thoughts: Deliberate Problem Solving with Large Language Model
    rrf=0.032 vector=3 keyword=2 rerank=None
    Task Setup. We scrape data from 4nums.com, which has 1,362 games that are sorted from easy to hard by human solving time, and use a subset of relatively hard ga
 …
```

### 3. Ask

```bash
uv run rag-complex ask "How does GPTQ's runtime scale to 175B-parameter models?"
```

With `ANTHROPIC_API_KEY`, Claude answers from the top 8 hits and cites them
as `[2210.17323 p.N]`. Without it, the hits are printed.

### 4. Experiment on a fork

```bash
uv run rag-complex experiment --chunker heading-merge
uv run rag-complex experiment --chunker heading-merge --embedder voyage   # needs VOYAGE_API_KEY
```

First run (same embedder, coarser chunks):

```
[fork created: branch=rag-exp-ef0715 | id=51c8c6cd-4dcb-4c77-8daf-c80f189882b0 | duration_ms=2714]
[ingested: source=2112.09118 | chunks=31 | duration_ms=4448]
…
[ingested: source=2401.18059 | chunks=31 | duration_ms=4108]
[fork indexed: chunks=262 | duration_ms=38846]
[meili index deleted: index=chunks_rag-exp-ef0715]
[fork deleted: id=51c8c6cd-4dcb-4c77-8daf-c80f189882b0]
main: chunker=block embedder=fastembed   fork: chunker=heading-merge embedder=fastembed   questions=30 rerank=on

metric          main      fork     delta
recall@5       0.933     0.867    -0.066
recall@10      0.933       0.9    -0.033
mrr            0.821     0.796    -0.025
p50_ms         412.6     519.2  +106.600
{"branch": {"name": "rag-exp-ef0715", "id": "51c8c6cd-4dcb-4c77-8daf-c80f189882b0", "kept": false}, "questions": 30, "main": {"recall@5": 0.933, "recall@10": 0.933, "mrr": 0.821, "p50_ms": 412.6, "chunker": "block", "embedder": "fastembed"}, "fork": {"recall@5": 0.867, "recall@10": 0.9, "mrr": 0.796, "p50_ms": 519.2, "chunker": "heading-merge", "embedder": "fastembed"}}
```

Second run (coarser chunks and Voyage `voyage-4` embeddings):

```
main: chunker=block embedder=fastembed   fork: chunker=heading-merge embedder=voyage   questions=30 rerank=on

metric          main      fork     delta
recall@5       0.933       1.0    +0.067
recall@10      0.933       1.0    +0.067
mrr            0.821     0.907    +0.086
p50_ms         442.4     988.9  +546.500
```

With the small local model, `heading-merge` did worse than `block`; paired
with `voyage-4` it beat `main` on every retrieval metric. (The second run
changes two things at once; `--chunker block --embedder voyage` would separate
them.) The price is latency: each query then makes a Voyage embedding call as
well as the rerank call. `main` was never written during either run.

The fork and its Meilisearch index are deleted on success, on error, on
Ctrl-C and on SIGTERM. Pass `--keep` to keep both for inspection; delete them
later with `keon branches delete --cascade <id>` and
`curl -X DELETE -H "Authorization: Bearer $MEILI_MASTER_KEY" localhost:7700/indexes/chunks_<branch>`.

There is deliberately no `--promote`: to adopt the winner, re-index `main`
with the same flags:

```bash
uv run rag-complex ingest --reset --chunker heading-merge --embedder voyage
```

## Chunkers

| `--chunker` | What it does |
|---|---|
| `block` (default) | One chunk per MinerU block; titles are their own chunks; text longer than ~2,000 tokens is split. |
| `fixed` | Consecutive blocks merged into ~2,000-character chunks, ignoring headings. |
| `heading-merge` | Every block under the same heading merged into one chunk (split at ~2,000 tokens). |

## Eval set

`eval/questions.jsonl`, one question per line:

```json
{"id": "q01", "question": "…", "source": "2204.00498", "page": 2}
```

`source` is the PDF file stem in `corpus/pdfs/`, `page` the 1-based page
that answers it. A hit counts as relevant when its `source` matches and
`page_start <= page <= page_end`. Metrics: recall@5, recall@10, MRR (first
relevant hit within the top 10), p50 search latency.

`uv run python eval/check_questions.py` validates the file against
`corpus/parsed/` (30 questions, 3 per paper, every page indexable).

## Re-parsing the PDFs (optional)

Only needed if you add PDFs. CPU works (about 2 minutes per paper; the
first run also downloads ~2 GB of models into `.mineru-cache/`):

```bash
mkdir -p .mineru-cache
docker compose --profile mineru run --rm mineru
# keep only what ingest reads:
find corpus/parsed -type f ! -name '*_content_list.json' -delete
find corpus/parsed -type d -empty -delete
```

Output lands in `corpus/parsed/<stem>/auto/<stem>_content_list.json`, which
is where `ingest` looks.

Hugging Face rate-limits anonymous model downloads (HTTP 429), and MinerU
does not always report it: a run that fails with `Can't load the configuration
of …` or `… is not existed` has an incomplete model cache. Pass a token
(`docker compose --profile mineru run --rm -e HF_TOKEN=hf_… mineru`) or wait a
few minutes and re-run. Once the models are cached, adding
`-e HF_HUB_OFFLINE=1` skips the Hub entirely.

## Flags

| Command | Flags |
|---|---|
| `ingest` | `--chunker`, `--embedder fastembed\|voyage\|openai`, `--reset`, `--parsed-dir`, `--pdf-dir` |
| `search QUERY` | `--mode hybrid\|semantic\|keyword`, `--k 10`, `--no-rerank` |
| `ask QUESTION` | `--k 8`, `--no-rerank` |
| `experiment` | `--chunker`, `--embedder`, `--keep`, `--questions`, `--project`, `--no-rerank` |

`search`/`ask` use whichever embedder `main` was ingested with (read from
`rag_complex.meta`). Ingesting with a different embedder without `--reset`
exits 2 (`Re-ingest with --reset`).

## Output and exit codes

Progress to **stderr**; human output plus one JSON line to **stdout**.

| Code | Meaning |
|---|---|
| `0` | OK |
| `1` | Nothing found / nothing ingested. |
| `2` | Setup error: missing env or key, Meilisearch down, `keon` failure, embedder mismatch. |

## Limitations

- Text, tables, equations and captions only. Figures are not embedded.
- Token counts are estimated at ~4 characters per token.
- MinerU is pinned to 3.4.5: MinerU 4.x removed the `pipeline` backend and the
  `content_list.json` output this example reads.
- Two paths are implemented but were not verified live for this release: the
  `openai` embedder (`--embedder openai`) and Claude-written `ask` answers
  (`ANTHROPIC_API_KEY`). Neither was run against the real API.

## Credits

The corpus is ten CC BY 4.0 arXiv papers. Authors, titles and links are in
[`corpus/LICENSES.md`](corpus/LICENSES.md).
