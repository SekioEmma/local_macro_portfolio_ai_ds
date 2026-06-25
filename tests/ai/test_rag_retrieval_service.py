from __future__ import annotations

from dataclasses import dataclass

import pytest

from app_backend.services.rag_retrieval_service import RAGRetrievalService, RetrievedChunk, _rrf_fuse


# ---- stubs ----

@dataclass
class _FakeVecResult:
    doc_id: str
    chunk_index: int
    score: float


@dataclass
class _FakeBM25Result:
    doc_id: str
    chunk_index: int
    score: float


@dataclass
class _FakeRawChunk:
    text: str
    title: str
    doc_type: str
    source_domain: str
    external_llm_context_allowed: bool = True


class _StubEmbedding:
    def encode_one(self, text: str) -> list[float]:
        return [float(ord(c)) / 1000 for c in text[:3].ljust(3)]


class _StubVectorStore:
    def __init__(self, results: list[_FakeVecResult]) -> None:
        self._results = results

    def query(self, embedding, top_k, *, doc_type_filter=None):
        filtered = [r for r in self._results
                    if doc_type_filter is None or True]  # stub ignores filter
        return filtered[:top_k]


class _StubBM25Index:
    def __init__(self, results: list[_FakeBM25Result]) -> None:
        self._results = results

    def query(self, text: str, top_k: int = 5) -> list[_FakeBM25Result]:
        return self._results[:top_k]


class _StubRawStore:
    def __init__(self, data: dict[tuple[str, int], _FakeRawChunk]) -> None:
        self._data = data

    def get_chunk(self, doc_id: str, chunk_index: int) -> _FakeRawChunk | None:
        return self._data.get((doc_id, chunk_index))


def _make_svc(
    vec: list[_FakeVecResult] | None = None,
    bm25: list[_FakeBM25Result] | None = None,
    raw: dict[tuple[str, int], _FakeRawChunk] | None = None,
) -> RAGRetrievalService:
    vec = vec or []
    bm25 = bm25 or []
    raw = raw or {}
    return RAGRetrievalService(
        embedding_service=_StubEmbedding(),
        vector_store=_StubVectorStore(vec),
        bm25_index=_StubBM25Index(bm25),
        raw_text_store=_StubRawStore(raw),
    )


def _chunk(doc_id: str, cidx: int = 0) -> _FakeRawChunk:
    return _FakeRawChunk(
        text=f"text of {doc_id} chunk {cidx}",
        title=f"Title {doc_id}",
        doc_type="fomc",
        source_domain="federalreserve.gov",
    )


# ---- rrf_fuse unit tests ----

def test_rrf_fuse_empty_inputs():
    assert _rrf_fuse([], [], top_k=5) == []


def test_rrf_fuse_vector_only():
    vec = [_FakeVecResult("d1", 0, 0.9), _FakeVecResult("d2", 0, 0.8)]
    result = _rrf_fuse(vec, [], top_k=2)
    assert len(result) == 2
    keys = [k for k, _ in result]
    assert ("d1", 0) in keys
    assert ("d2", 0) in keys


def test_rrf_fuse_bm25_only():
    bm25 = [_FakeBM25Result("d1", 0, 5.0), _FakeBM25Result("d2", 1, 3.0)]
    result = _rrf_fuse([], bm25, top_k=2)
    assert len(result) == 2


def test_rrf_fuse_top_k_limits():
    vec = [_FakeVecResult(f"d{i}", 0, float(i)) for i in range(10)]
    result = _rrf_fuse(vec, [], top_k=3)
    assert len(result) == 3


def test_rrf_fuse_boosts_overlap():
    # d1 appears in both vec and bm25 → should rank above d2 which is vec-only
    vec = [_FakeVecResult("d1", 0, 0.9), _FakeVecResult("d2", 0, 0.8)]
    bm25 = [_FakeBM25Result("d1", 0, 5.0)]
    result = _rrf_fuse(vec, bm25, top_k=2)
    assert result[0][0] == ("d1", 0), "d1 should rank first due to dual-retriever boost"


def test_rrf_fuse_scores_are_float():
    vec = [_FakeVecResult("d", 0, 1.0)]
    result = _rrf_fuse(vec, [], top_k=1)
    assert isinstance(result[0][1], float)


# ---- RAGRetrievalService ----

def test_retrieve_returns_list():
    svc = _make_svc()
    result = svc.retrieve("inflation")
    assert isinstance(result, list)


def test_retrieve_empty_query_returns_empty():
    svc = _make_svc()
    assert svc.retrieve("") == []
    assert svc.retrieve("   ") == []


def test_retrieve_non_str_query_raises():
    svc = _make_svc()
    with pytest.raises(TypeError):
        svc.retrieve(123)  # type: ignore[arg-type]


def test_retrieve_zero_top_k_raises():
    svc = _make_svc()
    with pytest.raises(ValueError):
        svc.retrieve("hello", top_k=0)


def test_retrieve_result_is_retrieved_chunk():
    raw = {("doc1", 0): _chunk("doc1")}
    vec = [_FakeVecResult("doc1", 0, 0.9)]
    svc = _make_svc(vec=vec, raw=raw)
    results = svc.retrieve("hello")
    assert len(results) == 1
    assert isinstance(results[0], RetrievedChunk)


def test_retrieve_result_fields():
    raw = {("doc1", 0): _FakeRawChunk("full text", "My Title", "bls", "bls.gov")}
    vec = [_FakeVecResult("doc1", 0, 0.9)]
    svc = _make_svc(vec=vec, raw=raw)
    result = svc.retrieve("rate")[0]
    assert result.doc_id == "doc1"
    assert result.chunk_index == 0
    assert result.text == "full text"
    assert result.title == "My Title"
    assert result.doc_type == "bls"
    assert result.source_domain == "bls.gov"
    assert isinstance(result.rrf_score, float)


def test_retrieve_skips_missing_raw_chunks():
    # vec result has no corresponding raw chunk → omitted from output
    vec = [_FakeVecResult("missing-doc", 0, 0.9), _FakeVecResult("real-doc", 0, 0.5)]
    raw = {("real-doc", 0): _chunk("real-doc")}
    svc = _make_svc(vec=vec, raw=raw)
    results = svc.retrieve("rate")
    ids = [r.doc_id for r in results]
    assert "missing-doc" not in ids
    assert "real-doc" in ids


def test_retrieve_top_k_limits_output():
    raw = {(f"d{i}", 0): _chunk(f"d{i}") for i in range(10)}
    vec = [_FakeVecResult(f"d{i}", 0, float(i)) for i in range(10)]
    svc = _make_svc(vec=vec, raw=raw)
    results = svc.retrieve("text", top_k=3)
    assert len(results) <= 3


def test_retrieve_result_frozen():
    raw = {("d", 0): _chunk("d")}
    vec = [_FakeVecResult("d", 0, 0.9)]
    svc = _make_svc(vec=vec, raw=raw)
    result = svc.retrieve("hello")[0]
    with pytest.raises((AttributeError, TypeError)):
        result.text = "modified"  # type: ignore[misc]


def test_retrieve_both_retrievers_empty_returns_empty():
    svc = _make_svc(vec=[], bm25=[], raw={})
    assert svc.retrieve("anything") == []


def test_retrieve_bm25_result_fused():
    # Only BM25 returns a hit; vector returns nothing
    raw = {("bm25-doc", 0): _chunk("bm25-doc")}
    bm25 = [_FakeBM25Result("bm25-doc", 0, 8.0)]
    svc = _make_svc(bm25=bm25, raw=raw)
    results = svc.retrieve("keyword match")
    ids = [r.doc_id for r in results]
    assert "bm25-doc" in ids
