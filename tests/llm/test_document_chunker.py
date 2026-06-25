from __future__ import annotations

import pytest

from llm.document_chunker import Chunk, chunk_text


# ---- basic structure ----

def test_empty_text_returns_empty():
    assert chunk_text("", doc_id="x") == []


def test_whitespace_only_returns_empty():
    assert chunk_text("   \n\n  ", doc_id="x") == []


def test_single_short_paragraph_is_one_chunk():
    text = "Hello world."
    result = chunk_text(text, doc_id="doc1")
    assert len(result) == 1
    assert result[0].text == "Hello world."
    assert result[0].doc_id == "doc1"
    assert result[0].chunk_index == 0


def test_chunk_dataclass_is_frozen():
    c = chunk_text("abc", doc_id="d")[0]
    with pytest.raises((AttributeError, TypeError)):
        c.text = "x"  # type: ignore[misc]


# ---- multiple paragraphs merge into one chunk ----

def test_two_short_paragraphs_merge():
    text = "Para one.\n\nPara two."
    result = chunk_text(text, doc_id="d", chunk_chars=200, overlap_chars=40)
    assert len(result) == 1
    assert "Para one" in result[0].text
    assert "Para two" in result[0].text


def test_paragraphs_split_when_combined_exceeds_limit():
    para_a = "A" * 60
    para_b = "B" * 60
    text = para_a + "\n\n" + para_b
    result = chunk_text(text, doc_id="d", chunk_chars=80, overlap_chars=10)
    assert len(result) == 2
    assert result[0].text == para_a
    assert result[1].text == para_b


# ---- chunk index is sequential ----

def test_chunk_indices_are_sequential():
    paras = [f"Paragraph {i}. " + "x" * 50 for i in range(5)]
    text = "\n\n".join(paras)
    result = chunk_text(text, doc_id="d", chunk_chars=80, overlap_chars=10)
    for i, chunk in enumerate(result):
        assert chunk.chunk_index == i


# ---- long single paragraph slides ----

def test_long_paragraph_is_slid():
    text = "W " * 1000
    result = chunk_text(text, doc_id="d", chunk_chars=100, overlap_chars=20)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk.text) <= 100 + 5  # small tolerance for strip


def test_slide_overlap_content_shared():
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4  # 104 chars
    result = chunk_text(text, doc_id="d", chunk_chars=30, overlap_chars=10)
    assert len(result) >= 2
    tail_of_first = result[0].text[-10:]
    head_of_second = result[1].text[:10]
    # There should be shared characters due to overlap
    assert any(c in head_of_second for c in tail_of_first)


# ---- char_start / char_end ----

def test_char_start_end_for_single_chunk():
    text = "  Hello world.  "
    result = chunk_text(text.strip(), doc_id="d")
    assert result[0].char_start == 0
    assert result[0].char_end == len("Hello world.")


def test_char_end_equals_start_plus_text_len():
    text = "Para one.\n\nPara two is here.\n\nPara three exists."
    result = chunk_text(text, doc_id="d", chunk_chars=20, overlap_chars=5)
    for chunk in result:
        assert chunk.char_end == chunk.char_start + len(chunk.text)


# ---- doc_id propagated ----

def test_doc_id_propagated_to_all_chunks():
    paras = [f"Para {i}. " + "x" * 50 for i in range(4)]
    text = "\n\n".join(paras)
    result = chunk_text(text, doc_id="my-doc-42", chunk_chars=80, overlap_chars=5)
    for chunk in result:
        assert chunk.doc_id == "my-doc-42"


# ---- parameter validation ----

def test_raises_on_non_str_text():
    with pytest.raises(TypeError):
        chunk_text(123, doc_id="d")  # type: ignore[arg-type]


def test_raises_on_zero_chunk_chars():
    with pytest.raises(ValueError):
        chunk_text("hello", doc_id="d", chunk_chars=0)


def test_raises_on_negative_overlap():
    with pytest.raises(ValueError):
        chunk_text("hello", doc_id="d", chunk_chars=100, overlap_chars=-1)


def test_raises_when_overlap_equals_chunk():
    with pytest.raises(ValueError):
        chunk_text("hello", doc_id="d", chunk_chars=100, overlap_chars=100)


# ---- Chinese text ----

def test_chinese_text_chunks():
    zh = "联储加息对债市的影响。" * 30
    result = chunk_text(zh, doc_id="zh-doc", chunk_chars=100, overlap_chars=20)
    assert len(result) >= 1
    for chunk in result:
        assert isinstance(chunk.text, str)
        assert len(chunk.text) > 0


# ---- no empty chunks ----

def test_no_empty_text_chunks():
    text = "A\n\n\n\nB\n\nC"
    result = chunk_text(text, doc_id="d", chunk_chars=5, overlap_chars=1)
    for chunk in result:
        assert chunk.text.strip() != ""
