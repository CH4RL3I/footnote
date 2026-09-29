"""Build, save and load an index: chunks (JSONL) + vectors (.npy) per chunking strategy."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from . import config
from .chunking import CHUNKERS, Chunk
from .corpus import load_corpus
from .embeddings import CachedEmbedder, Embedder, default_embedder
from .retrieval import BM25Retriever, DenseRetriever, HybridRetriever, Retriever


@dataclass
class Index:
    chunking: str
    chunks: list[Chunk]
    vectors: np.ndarray | None
    by_id: dict[str, Chunk]

    def retriever(self, kind: str, embedder: Embedder | None = None) -> Retriever:
        if kind == "bm25":
            return BM25Retriever(self.chunks)
        if self.vectors is None:
            raise SystemExit(
                f"Index '{self.chunking}' has no vectors. Run `filingqa index --chunking "
                f"{self.chunking} --retriever {kind}`."
            )
        dense = DenseRetriever(self.chunks, self.vectors, embedder or default_embedder())
        if kind == "dense":
            return dense
        if kind == "hybrid":
            return HybridRetriever([BM25Retriever(self.chunks), dense])
        raise ValueError(f"unknown retriever {kind!r}")


def _dir(chunking: str):
    return config.INDEX_DIR / chunking


def build_chunks(chunking: str) -> list[Chunk]:
    chunker = CHUNKERS[chunking]
    return [c for doc in load_corpus() for c in chunker(doc)]


def build_index(
    chunking: str,
    with_vectors: bool,
    embedder: CachedEmbedder | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Index:
    chunks = build_chunks(chunking)
    out = _dir(chunking)
    out.mkdir(parents=True, exist_ok=True)
    (out / "chunks.jsonl").write_text("\n".join(json.dumps(c.to_dict()) for c in chunks))
    vectors = None
    if with_vectors:
        embedder = embedder or default_embedder()
        vectors = embedder.embed([c.index_text for c in chunks], "document", progress=progress)
        np.save(out / "vectors.npy", vectors)
    elif (out / "vectors.npy").exists():
        (out / "vectors.npy").unlink()  # stale: chunks were rebuilt without re-embedding
    return Index(chunking, chunks, vectors, {c.id: c for c in chunks})


def load_index(chunking: str) -> Index:
    out = _dir(chunking)
    if not (out / "chunks.jsonl").exists():
        raise SystemExit(f"No index for '{chunking}'. Run `filingqa index` first.")
    chunks = [Chunk(**json.loads(x)) for x in (out / "chunks.jsonl").read_text().splitlines()]
    vec_path = out / "vectors.npy"
    vectors = np.load(vec_path) if vec_path.exists() else None
    return Index(chunking, chunks, vectors, {c.id: c for c in chunks})
