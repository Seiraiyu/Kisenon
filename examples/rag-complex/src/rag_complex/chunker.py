"""Turn a MinerU `content_list.json` into chunks.

`block` (default): one chunk per MinerU block. Headers/footers/page numbers are
dropped, titles become their own chunk and set the running `heading_context`
that later chunks carry, tables stay HTML. `fixed` and `heading-merge` are
coarser strategies built on top of `block`, for `experiment` to compare.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

DROP_TYPES = {"header", "footer", "page_number", "aside_text", "page_footnote"}
# ponytail: ~2,000 tokens at ~4 chars/token; swap in a real tokenizer if exact limits matter.
MAX_CHARS = 8000


@dataclass(slots=True)
class Chunk:
    kind: str
    text: str
    heading_context: str
    page_start: int  # 1-based
    page_end: int


def block_text(item: dict) -> tuple[str, str] | None:
    """(kind, text) for one content_list item, or None if it should be dropped."""
    t = item.get("type")
    if t in DROP_TYPES:
        return None
    if t == "text":
        kind, text = ("title" if item.get("text_level") else "text"), item.get("text", "")
    elif t == "table":
        parts = [*item.get("table_caption", []), item.get("table_body", ""),
                 *item.get("table_footnote", [])]
        kind, text = "table", "\n".join(p for p in parts if p)
    elif t == "equation":
        kind, text = "equation", item.get("text", "")
    elif t == "list" and item.get("sub_type") != "ref_text":  # reference lists are noise
        kind, text = "list", "\n".join(item.get("list_items", []))
    elif t == "code":
        kind, text = "code", item.get("code_body", "")
    elif t in ("image", "chart"):
        kind, text = t, "\n".join(item.get(f"{t}_caption", []))
    else:
        return None
    text = text.strip()
    return (kind, text) if text else None


def block_chunks(items: list[dict]) -> list[Chunk]:
    headings: dict[int, str] = {}
    out: list[Chunk] = []
    for item in items:
        bt = block_text(item)
        if bt is None:
            continue
        kind, text = bt
        page = int(item.get("page_idx", 0)) + 1
        if kind == "title":
            level = int(item["text_level"])
            headings = {lv: h for lv, h in headings.items() if lv < level}
            headings[level] = text
        ctx = " > ".join(headings[lv] for lv in sorted(headings))
        if kind == "table" or len(text) <= MAX_CHARS:
            out.append(Chunk(kind, text, ctx, page, page))
        else:
            out += [Chunk(kind, text[i : i + MAX_CHARS], ctx, page, page)
                    for i in range(0, len(text), MAX_CHARS)]
    return out


def _merge(chunks: list[Chunk], max_chars: int, on_heading: bool) -> list[Chunk]:
    out: list[Chunk] = []
    for c in chunks:
        prev = out[-1] if out else None
        if (
            prev is None
            or len(prev.text) + len(c.text) > max_chars
            or (on_heading and c.heading_context != prev.heading_context)
        ):
            out.append(replace(c))
            continue
        prev.text = f"{prev.text}\n\n{c.text}"
        prev.page_end = c.page_end
        prev.kind = prev.kind if prev.kind == c.kind else "merged"
    return out


CHUNKERS = {
    "block": block_chunks,
    "fixed": lambda items: _merge(block_chunks(items), 2000, on_heading=False),
    "heading-merge": lambda items: _merge(block_chunks(items), MAX_CHARS, on_heading=True),
}


def embed_text(c: Chunk) -> str:
    return f"{c.heading_context}\n\n{c.text}" if c.heading_context else c.text
