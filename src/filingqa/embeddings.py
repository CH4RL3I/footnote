"""Embedding providers behind one small interface, plus an SQLite cache."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Literal, Protocol

import httpx
import numpy as np

from . import config

Kind = Literal["document", "query"]


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], kind: Kind) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalised vectors."""


def normalise(vectors: np.ndarray) -> np.ndarray:
    v = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(norms == 0, 1, norms)


class OllamaEmbedder:
    """Local embeddings through Ollama's HTTP API (default: nomic-embed-text)."""

    # nomic-embed-text was trained with task prefixes; skipping them hurts retrieval.
    PREFIX = {"document": "search_document: ", "query": "search_query: "}

    def __init__(self, model: str = config.EMBED_MODEL, url: str = config.OLLAMA_URL, batch=32):
        self.name, self.url, self.batch = f"ollama:{model}", url, batch
        self.model = model

    def embed(self, texts: list[str], kind: Kind) -> np.ndarray:
        out = []
        for i in range(0, len(texts), self.batch):
            batch = [self.PREFIX[kind] + t for t in texts[i : i + self.batch]]
            resp = httpx.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": batch, "truncate": True},
                timeout=300,
            )
            resp.raise_for_status()
            out.extend(resp.json()["embeddings"])
        return normalise(np.array(out))


class CachedEmbedder:
    """Wraps an Embedder with an SQLite cache keyed by (provider, kind, sha1(text))."""

    def __init__(self, inner: Embedder, path=None):
        self.inner, self.name = inner, inner.name
        path = path or config.CACHE_DIR / "embeddings.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("create table if not exists emb (k text primary key, v blob)")

    def _key(self, text: str, kind: Kind) -> str:
        return f"{self.name}|{kind}|{hashlib.sha1(text.encode()).hexdigest()}"

    def embed(self, texts: list[str], kind: Kind, progress=None) -> np.ndarray:
        keys = [self._key(t, kind) for t in texts]
        found: dict[str, np.ndarray] = {}
        for i in range(0, len(keys), 500):
            part = keys[i : i + 500]
            rows = self.db.execute(
                f"select k, v from emb where k in ({','.join('?' * len(part))})", part
            ).fetchall()
            found.update({k: np.frombuffer(v, dtype=np.float32) for k, v in rows})
        missing = [i for i, k in enumerate(keys) if k not in found]
        step = 256
        for s in range(0, len(missing), step):
            idx = missing[s : s + step]
            vecs = self.inner.embed([texts[i] for i in idx], kind)
            with self.db:
                self.db.executemany(
                    "insert or replace into emb values (?, ?)",
                    [(keys[i], v.tobytes()) for i, v in zip(idx, vecs, strict=True)],
                )
            found.update({keys[i]: v for i, v in zip(idx, vecs, strict=True)})
            if progress:
                progress(min(s + step, len(missing)), len(missing))
        return np.stack([found[k] for k in keys]) if keys else np.zeros((0, 0), np.float32)


def default_embedder() -> CachedEmbedder:
    return CachedEmbedder(OllamaEmbedder())
