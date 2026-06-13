from __future__ import annotations

import numpy as np

from photovault.core.learn.vectorstore import InMemoryVectorStore, get_vectorstore


def test_add_and_query_returns_nearest():
    store = InMemoryVectorStore()
    store.add(
        ids=["a", "b", "c"],
        vecs=[
            np.array([1.0, 0.0], np.float32),
            np.array([0.0, 1.0], np.float32),
            np.array([-1.0, 0.0], np.float32),
        ],
        metas=[{"f": "a"}, {"f": "b"}, {"f": "c"}],
    )
    ids, dists = store.query(np.array([0.9, 0.1], np.float32), k=2)
    assert ids[0] == "a"
    assert len(ids) == 2
    assert dists[0] <= dists[1]


def test_query_respects_k():
    store = InMemoryVectorStore()
    store.add(ids=["a"], vecs=[np.array([1.0, 0.0], np.float32)], metas=[{}])
    ids, _ = store.query(np.array([1.0, 0.0], np.float32), k=5)
    assert ids == ["a"]


def test_count():
    store = InMemoryVectorStore()
    assert store.count() == 0
    store.add(ids=["a", "b"], vecs=[np.zeros(2, np.float32)] * 2, metas=[{}, {}])
    assert store.count() == 2


def test_get_vectorstore_falls_back_without_chromadb(tmp_path):
    # chromadb is optional; the factory must always return a usable store.
    store = get_vectorstore(tmp_path / "chroma")
    store.add(ids=["x"], vecs=[np.array([1.0, 0.0], np.float32)], metas=[{}])
    ids, _ = store.query(np.array([1.0, 0.0], np.float32), k=1)
    assert ids == ["x"]
