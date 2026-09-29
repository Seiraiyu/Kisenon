"""Ingest: parsed MinerU output -> chunks -> embeddings -> Postgres + Meilisearch."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from rag_complex import store
from rag_complex.chunker import CHUNKERS, embed_text
from rag_complex.embed import Embedder, embed_batched


def event(label: str, **fields: Any) -> None:
    body = " | ".join(f"{k}={v}" for k, v in fields.items())
    sys.stderr.write(f"[{label}{': ' + body if body else ''}]\n")
    sys.stderr.flush()


def parsed_files(parsed_dir: Path) -> list[Path]:
    """MinerU layout: <parsed_dir>/<stem>/auto/<stem>_content_list.json"""
    return sorted(parsed_dir.glob("*/auto/*_content_list.json"))


def ingest(
    conn: Any, meili: Any, index: str, *, parsed_dir: Path, pdf_dir: Path,
    chunker: str, embedder: Embedder, reset: bool,
) -> dict:
    started = time.monotonic()
    store.ensure_schema(conn, embedder.name, embedder.dim, chunker, reset=reset)
    if reset:
        meili.delete_index(index)
    meili.ensure_index(index)
    files = parsed_files(parsed_dir)
    total = 0
    for path in files:
        t0 = time.monotonic()
        source = path.parent.parent.name
        doc_id = hashlib.sha256((pdf_dir / f"{source}.pdf").read_bytes()).hexdigest()[:24]
        items = json.loads(path.read_text(encoding="utf-8"))
        chunks = CHUNKERS[chunker](items)
        vectors = embed_batched([embed_text(c) for c in chunks], embedder)
        title = next((i["text"] for i in items if i.get("text_level") == 1), source)
        pages = max((int(i.get("page_idx", 0)) for i in items), default=0) + 1
        store.replace_document(conn, doc_id, source, title, pages, chunks, vectors)
        meili.replace_document(index, doc_id, [
            {"id": f"{doc_id}-{n}", "document_id": doc_id, "ord": n, "source": source,
             "text": c.text, "heading_context": c.heading_context,
             "page_start": c.page_start, "page_end": c.page_end}
            for n, c in enumerate(chunks)
        ])
        total += len(chunks)
        event("ingested", source=source, chunks=len(chunks),
              duration_ms=int((time.monotonic() - t0) * 1000))
    return {
        "documents": len(files), "chunks": total, "chunker": chunker,
        "embedder": embedder.name, "dim": embedder.dim, "index": index,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
