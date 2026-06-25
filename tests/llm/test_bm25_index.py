from __future__ import annotations

import pytest

from llm.bm25_index import BM25Index, BM25Result, _tokenize


# ---- stub BM25 that returns controllable scores ----

class _StubBM25:
    def __init__(self, corpus: list[list[str]]) -> None:
        self._corpus = corpus

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores = []
        for tokens in self._corpus:
            overlap = len(set(query_tokens) & set(tokens))
            scores.append(float(overlap))
        return scores


def _idx() -> BM25Index:
    return BM25Index(_bm25_factory=_StubBM25)


def _built(chunks: list[tuple[str, int, str]]) -> BM25Index:
    idx = _idx()
    idx.build(chunks)
    return idx


# ---- tokenizer ----

def test_tokenize_latin():
    tokens = _tokenize("hello world")
    assert "hello" in tokens
    assert "world" in tokens


def test_tokenize_cjk():
    tokens = _tokenize("通货膨胀")
    assert "通" in tokens
    assert "货" in tokens


def test_tokenize_mixed():
    tokens = _tokenize("Fed 利率 policy")
    assert "fed" in tokens
    assert "policy" in tokens
    assert "率" in tokens


def test_tokenize_empty():
    assert _tokenize("") == []


def test_tokenize_punctuation_only():
    tokens = _tokenize("!!! ---")
    assert tokens == []


# ---- build ----

def test_is_not_built_before_build():
    assert not _idx().is_built


def test_is_built_after_build():
    idx = _built([("d", 0, "hello world")])
    assert idx.is_built


def test_size_after_build():
    idx = _built([("d", 0, "a"), ("d", 1, "b"), ("d", 2, "c")])
    assert idx.size == 3


def test_build_empty_corpus():
    idx = _built([])
    assert idx.size == 0
    assert idx.is_built


def test_build_replaces_previous():
    idx = _built([("d", 0, "old")])
    idx.build([("d", 1, "new"), ("d", 2, "stuff")])
    assert idx.size == 2


def test_build_rejects_non_list():
    idx = _idx()
    with pytest.raises(TypeError):
        idx.build("not a list")  # type: ignore[arg-type]


def test_build_rejects_bad_tuple_length():
    idx = _idx()
    with pytest.raises(ValueError):
        idx.build([("d", 0)])  # type: ignore[arg-type]


def test_build_rejects_blank_doc_id():
    idx = _idx()
    with pytest.raises(ValueError):
        idx.build([("", 0, "text")])


def test_build_rejects_negative_chunk_index():
    idx = _idx()
    with pytest.raises(ValueError):
        idx.build([("d", -1, "text")])


def test_build_rejects_bool_chunk_index():
    idx = _idx()
    with pytest.raises(ValueError):
        idx.build([("d", True, "text")])  # type: ignore[arg-type]


# ---- query ----

def test_query_before_build_raises():
    with pytest.raises(RuntimeError, match="build"):
        _idx().query("hello")


def test_query_returns_results():
    idx = _built([
        ("doc1", 0, "federal reserve interest rate"),
        ("doc2", 0, "inflation cpi price"),
        ("doc3", 0, "equity market stock"),
    ])
    results = idx.query("interest rate")
    assert len(results) >= 1
    assert all(isinstance(r, BM25Result) for r in results)


def test_query_top_k_limits():
    chunks = [(f"d{i}", 0, f"word{i} shared") for i in range(10)]
    idx = _built(chunks)
    results = idx.query("shared", top_k=3)
    assert len(results) <= 3


def test_query_filters_zero_scores():
    idx = _built([
        ("doc1", 0, "apple orange"),
        ("doc2", 0, "car engine"),
    ])
    results = idx.query("apple")
    ids = [r.doc_id for r in results]
    assert "doc1" in ids
    assert "doc2" not in ids


def test_query_blank_returns_empty():
    idx = _built([("d", 0, "some text")])
    assert idx.query("   ") == []


def test_query_empty_corpus_returns_empty():
    idx = _built([])
    assert idx.query("hello") == []


def test_query_non_str_raises():
    idx = _built([("d", 0, "text")])
    with pytest.raises(TypeError):
        idx.query(123)  # type: ignore[arg-type]


def test_query_zero_top_k_raises():
    idx = _built([("d", 0, "text")])
    with pytest.raises(ValueError):
        idx.query("text", top_k=0)


def test_query_result_fields():
    idx = _built([("my-doc", 3, "federal reserve")])
    results = idx.query("federal reserve")
    assert results[0].doc_id == "my-doc"
    assert results[0].chunk_index == 3
    assert isinstance(results[0].score, float)


def test_query_ranking_order():
    idx = _built([
        ("weak", 0, "rate"),
        ("strong", 0, "interest rate policy"),
    ])
    results = idx.query("interest rate policy")
    assert results[0].doc_id == "strong"


# ---- missing rank_bm25 ----

def test_missing_rank_bm25_uses_local_fallback(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "rank_bm25", None)  # type: ignore[assignment]
    idx = BM25Index()
    idx.build([("d", 0, "federal reserve policy"), ("x", 0, "equity market")])

    results = idx.query("federal policy")

    assert results[0].doc_id == "d"
    monkeypatch.delitem(sys.modules, "rank_bm25")
