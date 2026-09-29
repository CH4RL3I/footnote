"""Retrievers: BM25, dense (cosine over stored vectors) and hybrid via reciprocal rank fusion."""

from __future__ import annotations

import re
from typing import Protocol

import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk
from .embeddings import Embedder

RRF_K = 60  # the constant from Cormack et al. (2009)
TOKEN_RE = re.compile(r"[a-z0-9](?:[a-z0-9,.]*[a-z0-9])?")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens that keep numbers intact ('391,035' is one token)."""
    return TOKEN_RE.findall(re.sub(r"['’]s\b", "", text.lower()))


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(d) = sum over rankings of 1 / (k + rank(d)), rank from 1."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    # Ties are broken by id so results are deterministic.
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        """Return up to k (chunk_id, score) pairs, best first."""


class BM25Retriever:
    def __init__(self, chunks: list[Chunk]):
        self.ids = [c.id for c in chunks]
        self.bm25 = BM25Okapi([tokenize(c.index_text) for c in chunks])

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        top = np.argsort(-scores, kind="stable")[:k]
        return [(self.ids[i], float(scores[i])) for i in top]


class DenseRetriever:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, embedder: Embedder):
        self.ids, self.vectors, self.embedder = [c.id for c in chunks], vectors, embedder

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        q = self.embedder.embed([query], "query")[0]
        scores = self.vectors @ q
        top = np.argsort(-scores, kind="stable")[:k]
        return [(self.ids[i], float(scores[i])) for i in top]


class HybridRetriever:
    def __init__(self, retrievers: list[Retriever], depth: int = 100, k: int = RRF_K):
        self.retrievers, self.depth, self.k = retrievers, depth, k

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        rankings = [[cid for cid, _ in r.search(query, self.depth)] for r in self.retrievers]
        return rrf(rankings, self.k)[:k]
