"""Retrieval and answer metrics. Pure functions, no I/O."""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence


def recall_at_k(ranked: Sequence[str], gold: Collection[str], k: int) -> float:
    """1.0 if any gold chunk is in the top k, else 0.0 (a single hit is enough to find the fact)."""
    return 1.0 if any(cid in set(gold) for cid in ranked[:k]) else 0.0


def reciprocal_rank(ranked: Sequence[str], gold: Collection[str]) -> float:
    """1 / rank of the first gold chunk, 0 if none was retrieved."""
    g = set(gold)
    for rank, cid in enumerate(ranked, start=1):
        if cid in g:
            return 1.0 / rank
    return 0.0


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def wilson_interval(successes: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; sensible even for small n."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def citation_correct(cited: Collection[str], gold: Collection[str]) -> bool:
    """A citation counts if at least one cited chunk id is a gold chunk."""
    return bool(set(cited) & set(gold))
