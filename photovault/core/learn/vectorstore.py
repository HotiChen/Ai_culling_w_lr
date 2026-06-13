"""Keeper-embedding vector store (chromadb) with an in-memory fallback.

The store persists keeper CLIP embeddings so apply-time can ask "what did I keep
that looks like this?". The real backend is a local persistent ``chromadb``
collection (lazy import); when chromadb is absent the factory transparently
returns an :class:`InMemoryVectorStore`, so tests and lightweight installs work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

import numpy as np


@runtime_checkable
class VectorStore(Protocol):
    """Minimal cosine-distance vector store."""

    def add(
        self,
        ids: Sequence[str],
        vecs: Sequence[np.ndarray],
        metas: Sequence[dict],
    ) -> None:
        ...

    def query(self, vec: np.ndarray, k: int = 5) -> tuple[list[str], list[float]]:
        ...

    def count(self) -> int:
        ...


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v)
    return v if n == 0 else v / n


class InMemoryVectorStore:
    """Dependency-free store using cosine distance (``1 - cos`` similarity)."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vecs: list[np.ndarray] = []
        self._metas: list[dict] = []

    def add(
        self,
        ids: Sequence[str],
        vecs: Sequence[np.ndarray],
        metas: Sequence[dict],
    ) -> None:
        for i, v, m in zip(ids, vecs, metas):
            self._ids.append(i)
            self._vecs.append(_normalize(v))
            self._metas.append(m)

    def query(self, vec: np.ndarray, k: int = 5) -> tuple[list[str], list[float]]:
        if not self._vecs:
            return [], []
        q = _normalize(vec)
        dists = [1.0 - float(np.dot(q, v)) for v in self._vecs]
        order = np.argsort(dists)[: max(k, 0)]
        return [self._ids[i] for i in order], [dists[i] for i in order]

    def count(self) -> int:
        return len(self._ids)


class ChromaVectorStore:
    """Persistent :class:`VectorStore` backed by chromadb (lazy import)."""

    def __init__(self, persist_dir: str | Path, collection: str = "keepers") -> None:
        import chromadb  # lazy: heavy, optional dep

        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._col = self._client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"}
        )

    def add(
        self,
        ids: Sequence[str],
        vecs: Sequence[np.ndarray],
        metas: Sequence[dict],
    ) -> None:
        self._col.add(
            ids=list(ids),
            embeddings=[_normalize(v).tolist() for v in vecs],
            metadatas=[dict(m) for m in metas],
        )

    def query(self, vec: np.ndarray, k: int = 5) -> tuple[list[str], list[float]]:
        res = self._col.query(
            query_embeddings=[_normalize(vec).tolist()], n_results=k
        )
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        return list(ids), [float(d) for d in dists]

    def count(self) -> int:
        return int(self._col.count())


def get_vectorstore(persist_dir: str | Path | None = None) -> VectorStore:
    """Return a chromadb-backed store if possible, else an in-memory one."""
    if persist_dir is None:
        return InMemoryVectorStore()
    try:
        return ChromaVectorStore(persist_dir)
    except ImportError:
        return InMemoryVectorStore()
