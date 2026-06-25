from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llm.vector_store import VectorStore, VectorSearchResult, _item_id


# ---- in-memory stub Chroma client / collection ----

class _StubCollection:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def upsert(self, *, ids, embeddings, metadatas):
        for id_, emb, meta in zip(ids, embeddings, metadatas):
            self._store[id_] = {"embedding": emb, "metadata": meta}

    def query(self, *, query_embeddings, n_results, include, where=None):
        items = list(self._store.values())
        if where:
            items = [it for it in items if all(it["metadata"].get(k) == v for k, v in where.items())]
        q = query_embeddings[0]
        def _dot(a, b):
            return sum(x * y for x, y in zip(a, b))
        scored = sorted(items, key=lambda it: -_dot(q, it["embedding"]))[:n_results]
        ids_out, dists_out, metas_out = [], [], []
        for it in scored:
            ids_out.append(next(k for k, v in self._store.items() if v is it))
            dists_out.append(0.1)
            metas_out.append(it["metadata"])
        return {"ids": [ids_out], "distances": [dists_out], "metadatas": [metas_out]}

    def delete(self, *, ids):
        for id_ in ids:
            self._store.pop(id_, None)

    def get(self, *, where, include):
        items = self._store
        matched_ids = [k for k, v in items.items() if all(v["metadata"].get(k2) == v2 for k2, v2 in where.items())]
        return {"ids": matched_ids}

    def count(self):
        return len(self._store)


class _StubClient:
    def __init__(self) -> None:
        self._col = _StubCollection()

    def get_or_create_collection(self, *, name, metadata=None):
        return self._col


def _store(tmp_path: Path) -> VectorStore:
    return VectorStore(tmp_path, _client=_StubClient())


FAKE_EMB = [0.1, 0.2, 0.3]


# ---- construction ----

def test_construction_does_not_call_client(tmp_path):
    calls: list[str] = []

    class _TrackedClient:
        def get_or_create_collection(self, **kw):
            calls.append("get_or_create_collection")
            return _StubCollection()

    VectorStore(tmp_path, _client=_TrackedClient())
    assert calls == [], "client must not be called at construction"


def test_persist_dir_must_be_path():
    with pytest.raises(TypeError):
        VectorStore("/not/a/path")  # type: ignore[arg-type]


# ---- upsert + count ----

def test_upsert_single_chunk(tmp_path):
    vs = _store(tmp_path)
    vs.upsert("doc1", 0, FAKE_EMB)
    assert vs.count() == 1


def test_upsert_multiple_chunks(tmp_path):
    vs = _store(tmp_path)
    for i in range(3):
        vs.upsert("doc1", i, FAKE_EMB)
    assert vs.count() == 3


def test_upsert_is_idempotent(tmp_path):
    vs = _store(tmp_path)
    vs.upsert("doc1", 0, FAKE_EMB)
    vs.upsert("doc1", 0, FAKE_EMB)
    assert vs.count() == 1


def test_upsert_stores_metadata(tmp_path):
    vs = _store(tmp_path)
    vs.upsert("doc1", 0, FAKE_EMB, metadata={"title": "Test Doc"})
    results = vs.query(FAKE_EMB, top_k=1)
    assert results[0].metadata.get("title") == "Test Doc"


# ---- validation in upsert ----

def test_upsert_blank_doc_id_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(ValueError):
        vs.upsert("", 0, FAKE_EMB)


def test_upsert_negative_chunk_index_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(ValueError):
        vs.upsert("doc1", -1, FAKE_EMB)


def test_upsert_bool_chunk_index_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(ValueError):
        vs.upsert("doc1", True, FAKE_EMB)  # type: ignore[arg-type]


def test_upsert_empty_embedding_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(ValueError):
        vs.upsert("doc1", 0, [])


def test_upsert_non_list_embedding_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(TypeError):
        vs.upsert("doc1", 0, (0.1, 0.2))  # type: ignore[arg-type]


# ---- query ----

def test_query_returns_results(tmp_path):
    vs = _store(tmp_path)
    vs.upsert("doc1", 0, FAKE_EMB)
    results = vs.query(FAKE_EMB, top_k=1)
    assert len(results) == 1
    assert isinstance(results[0], VectorSearchResult)


def test_query_result_fields(tmp_path):
    vs = _store(tmp_path)
    vs.upsert("doc-x", 2, FAKE_EMB)
    result = vs.query(FAKE_EMB, top_k=1)[0]
    assert result.doc_id == "doc-x"
    assert result.chunk_index == 2
    assert isinstance(result.score, float)


def test_query_top_k_limits_results(tmp_path):
    vs = _store(tmp_path)
    for i in range(5):
        vs.upsert(f"doc{i}", 0, [float(i)] * 3)
    results = vs.query(FAKE_EMB, top_k=2)
    assert len(results) <= 2


def test_query_zero_top_k_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(ValueError):
        vs.query(FAKE_EMB, top_k=0)


def test_query_excessive_top_k_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(ValueError):
        vs.query(FAKE_EMB, top_k=9999)


def test_query_doc_type_filter(tmp_path):
    vs = _store(tmp_path)
    vs.upsert("doc-a", 0, FAKE_EMB, metadata={"doc_type": "fomc"})
    vs.upsert("doc-b", 0, FAKE_EMB, metadata={"doc_type": "research"})
    results = vs.query(FAKE_EMB, top_k=10, doc_type_filter="fomc")
    assert all(r.doc_id == "doc-a" for r in results)


# ---- delete ----

def test_delete_removes_chunks(tmp_path):
    vs = _store(tmp_path)
    vs.upsert("doc1", 0, FAKE_EMB)
    vs.upsert("doc1", 1, FAKE_EMB)
    count = vs.delete("doc1")
    assert count == 2
    assert vs.count() == 0


def test_delete_nonexistent_returns_zero(tmp_path):
    vs = _store(tmp_path)
    assert vs.delete("no-such-doc") == 0


def test_delete_blank_doc_id_raises(tmp_path):
    vs = _store(tmp_path)
    with pytest.raises(ValueError):
        vs.delete("")


# ---- missing chromadb gives clear error ----

def test_missing_chromadb_gives_import_error(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "chromadb", None)  # type: ignore[assignment]
    vs = VectorStore(tmp_path)
    with pytest.raises(ImportError, match="chromadb"):
        vs.upsert("d", 0, FAKE_EMB)
    monkeypatch.delitem(sys.modules, "chromadb")


# ---- item_id helper ----

def test_item_id_format():
    assert _item_id("doc1", 3) == "doc1::3"
