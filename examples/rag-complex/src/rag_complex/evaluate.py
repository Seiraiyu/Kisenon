"""Retrieval eval: recall@5, recall@10, MRR, p50 latency."""
from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path


def load_questions(path: Path) -> list[dict]:
    """JSONL: {"id", "question", "source" (PDF stem, e.g. "2210.17323"), "page" (1-based)}."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def first_relevant_rank(hits: list[dict], q: dict) -> int | None:
    for rank, h in enumerate(hits, 1):
        if h["source"] == q["source"] and h["page_start"] <= q["page"] <= h["page_end"]:
            return rank
    return None


def metrics(ranks: list[int | None], latencies_ms: list[float]) -> dict:
    n = len(ranks) or 1
    return {
        "recall@5": round(sum(1 for r in ranks if r and r <= 5) / n, 3),
        "recall@10": round(sum(1 for r in ranks if r and r <= 10) / n, 3),
        "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
        "p50_ms": round(statistics.median(latencies_ms), 1) if latencies_ms else 0.0,
    }


def run_eval(questions: list[dict], search_fn: Callable[[str], list[dict]]) -> dict:
    ranks: list[int | None] = []
    latencies: list[float] = []
    for q in questions:
        started = time.perf_counter()
        hits = search_fn(q["question"])
        latencies.append((time.perf_counter() - started) * 1000)
        ranks.append(first_relevant_rank(hits, q))
    return metrics(ranks, latencies)


def format_table(main: dict, fork: dict) -> str:
    lines = [f"{'metric':<10} {'main':>9} {'fork':>9} {'delta':>9}"]
    for key in ("recall@5", "recall@10", "mrr", "p50_ms"):
        lines.append(f"{key:<10} {main[key]:>9} {fork[key]:>9} {fork[key] - main[key]:>+9.3f}")
    return "\n".join(lines)
