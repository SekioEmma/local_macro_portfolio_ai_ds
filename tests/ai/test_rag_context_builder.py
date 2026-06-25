from __future__ import annotations

import pytest

from app_backend.services.rag_context_builder import (
    RAGContextBlock,
    build_rag_context,
    _SECTION_HEADER,
    _CHUNK_SEPARATOR,
)
from app_backend.services.rag_retrieval_service import RetrievedChunk


def _chunk(
    doc_id: str = "d",
    chunk_index: int = 0,
    text: str = "some text",
    title: str = "Test Title",
    doc_type: str = "fomc",
    source_domain: str = "fed.gov",
    rrf_score: float = 0.5,
) -> RetrievedChunk:
    return RetrievedChunk(
        doc_id=doc_id,
        chunk_index=chunk_index,
        text=text,
        rrf_score=rrf_score,
        title=title,
        doc_type=doc_type,
        source_domain=source_domain,
    )


# ---- empty input ----

def test_empty_chunks_returns_empty_block():
    result = build_rag_context([])
    assert result.text == ""
    assert result.char_count == 0
    assert result.chunk_count == 0
    assert result.truncated is False


# ---- single chunk ----

def test_single_chunk_included():
    result = build_rag_context([_chunk(text="hello world")])
    assert "hello world" in result.text
    assert result.chunk_count == 1
    assert result.truncated is False


def test_single_chunk_contains_title():
    result = build_rag_context([_chunk(title="My Report")])
    assert "My Report" in result.text


def test_single_chunk_contains_doc_type():
    result = build_rag_context([_chunk(doc_type="bls")])
    assert "bls" in result.text


# ---- header ----

def test_header_included_by_default():
    result = build_rag_context([_chunk()])
    assert _SECTION_HEADER in result.text


def test_header_excluded_when_disabled():
    result = build_rag_context([_chunk()], include_header=False)
    assert _SECTION_HEADER not in result.text


# ---- multiple chunks ----

def test_multiple_chunks_separated():
    chunks = [_chunk(text="chunk A"), _chunk(text="chunk B", chunk_index=1)]
    result = build_rag_context(chunks)
    assert "chunk A" in result.text
    assert "chunk B" in result.text
    assert _CHUNK_SEPARATOR in result.text
    assert result.chunk_count == 2


def test_chunk_count_matches_included():
    chunks = [_chunk(chunk_index=i) for i in range(5)]
    result = build_rag_context(chunks, max_chars=10000)
    assert result.chunk_count == 5


# ---- max_chars cap ----

def test_truncation_when_over_limit():
    long_text = "X" * 500
    chunks = [_chunk(text=long_text, chunk_index=i) for i in range(5)]
    result = build_rag_context(chunks, max_chars=600)
    assert result.truncated is True
    assert result.chunk_count < 5


def test_no_truncation_when_fits():
    chunks = [_chunk(text="short", chunk_index=i) for i in range(3)]
    result = build_rag_context(chunks, max_chars=10000)
    assert result.truncated is False
    assert result.chunk_count == 3


def test_char_count_does_not_include_header():
    result = build_rag_context([_chunk(text="abc")])
    assert _SECTION_HEADER not in result.text[result.char_count:]
    body = result.text[len(_SECTION_HEADER) + 1:]
    assert len(body) == result.char_count


def test_zero_max_chars_raises():
    with pytest.raises(ValueError):
        build_rag_context([_chunk()], max_chars=0)


# ---- RAGContextBlock is frozen ----

def test_result_is_frozen():
    result = build_rag_context([])
    with pytest.raises((AttributeError, TypeError)):
        result.text = "x"  # type: ignore[misc]


# ---- type validation ----

def test_non_list_raises():
    with pytest.raises(TypeError):
        build_rag_context("not a list")  # type: ignore[arg-type]


def test_non_chunk_element_raises():
    with pytest.raises(TypeError):
        build_rag_context(["not a chunk"])  # type: ignore[list-item]


# ---- no forbidden fields in output ----

def test_output_text_contains_no_source_domain_url():
    result = build_rag_context([_chunk(source_domain="very-private.internal")])
    assert "very-private.internal" not in result.text


def test_output_text_contains_no_doc_id():
    result = build_rag_context([_chunk(doc_id="secret-internal-path")])
    assert "secret-internal-path" not in result.text


def test_output_text_contains_no_rrf_score():
    result = build_rag_context([_chunk(rrf_score=0.123456)])
    assert "0.123456" not in result.text


# ---- order preserved ----

def test_output_order_matches_input_order():
    chunks = [_chunk(title=f"Doc {i}", chunk_index=i) for i in range(3)]
    result = build_rag_context(chunks, max_chars=10000)
    pos = [result.text.find(f"Doc {i}") for i in range(3)]
    assert pos[0] < pos[1] < pos[2]
