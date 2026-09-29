"""Fixed-size chunking that respects paragraph boundaries first."""
from __future__ import annotations

import re


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    """Pack paragraphs into chunks of at most `size` chars.

    A paragraph longer than `size` is cut into `size`-char windows that overlap by
    `overlap`. When a chunk closes, the next one starts with the previous chunk's
    last `overlap` chars (if that still fits), so context crosses the boundary.
    """
    step = size - overlap
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if len(para) <= size:
            pieces += [para] if para else []
        else:
            pieces += [para[i : i + size] for i in range(0, len(para) - overlap, step)]

    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if not cur:
            cur = p
        elif len(cur) + 2 + len(p) <= size:
            cur = f"{cur}\n\n{p}"
        else:
            chunks.append(cur)
            tail = cur[-overlap:]
            cur = f"{tail}\n\n{p}" if len(tail) + 2 + len(p) <= size else p
    if cur:
        chunks.append(cur)
    return chunks
