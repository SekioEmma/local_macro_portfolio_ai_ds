from __future__ import annotations

from pathlib import Path

import pytest

from llm.chunk_text_store import ChunkTextStore, StoredChunk


def _store(tmp_path: Path) -> ChunkTextStore:
    return ChunkTextStore(tmp_path / "chunks.sqlite")


def _chunk(doc_id: str = "doc1", chunk_index: int = 0, text: str = "hello") -> StoredChunk:
    return StoredChunk(
        doc_id=doc_id,
        chunk_index=chunk_index,
        text=text,
        title="Test Title",
        doc_type="research_report",
        source_domain="local",
    )


# ---- construction ----

def test_construction_non_path_raises():
    with pytest.raises(TypeError):
        ChunkTextStore("/not/a/path")  # type: ignore[arg-type]


def test_db_file_created_on_upsert(tmp_path):
    store = _store(tmp_path)
    store.upsert_chunk(_chunk())
    assert (tmp_path / "chunks.sqlite").exists()


# ---- upsert + get ----

def test_upsert_and_get_round_trip(tmp_path):
    store = _store(tmp_path)
    store.upsert_chunk(_chunk(text="the text"))
    result = store.get_chunk("doc1", 0)
    assert result is not None
    assert result.text == "the text"
    assert result.doc_id == "doc1"
    assert result.chunk_index == 0


def test_get_nonexistent_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.get_chunk("missing", 0) is None


def test_upsert_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.upsert_chunk(_chunk(text="v1"))
    store.upsert_chunk(_chunk(text="v2"))
    result = store.get_chunk("doc1", 0)
    assert result.text == "v2"
    assert store.count() == 1


def test_upsert_multiple_chunks(tmp_path):
    store = _store(tmp_path)
    for i in range(3):
        store.upsert_chunk(_chunk(chunk_index=i, text=f"text {i}"))
    assert store.count() == 3


# ---- delete ----

def test_delete_doc_removes_all_chunks(tmp_path):
    store = _store(tmp_path)
    for i in range(3):
        store.upsert_chunk(_chunk(chunk_index=i))
    count = store.delete_doc("doc1")
    assert count == 3
    assert store.count() == 0


def test_delete_doc_nonexistent_returns_zero(tmp_path):
    store = _store(tmp_path)
    assert store.delete_doc("no-such") == 0


def test_delete_doc_leaves_other_docs(tmp_path):
    store = _store(tmp_path)
    store.upsert_chunk(_chunk(doc_id="a", chunk_index=0))
    store.upsert_chunk(_chunk(doc_id="b", chunk_index=0))
    store.delete_doc("a")
    assert store.count() == 1
    assert store.get_chunk("b", 0) is not None


# ---- list_doc_ids ----

def test_list_doc_ids_empty(tmp_path):
    store = _store(tmp_path)
    assert store.list_doc_ids() == []


def test_list_doc_ids(tmp_path):
    store = _store(tmp_path)
    for did in ["z", "a", "m"]:
        store.upsert_chunk(_chunk(doc_id=did))
    ids = store.list_doc_ids()
    assert set(ids) == {"a", "m", "z"}
    assert ids == sorted(ids)


# ---- validation ----

def test_upsert_non_stored_chunk_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(TypeError):
        store.upsert_chunk("not a chunk")  # type: ignore[arg-type]


def test_upsert_blank_doc_id_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.upsert_chunk(StoredChunk("", 0, "t", "title", "research_report", "local"))


def test_upsert_negative_chunk_index_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.upsert_chunk(StoredChunk("d", -1, "t", "title", "research_report", "local"))


# ---- stored chunk is frozen ----

def test_stored_chunk_is_frozen():
    c = _chunk()
    with pytest.raises((AttributeError, TypeError)):
        c.text = "x"  # type: ignore[misc]


# ---- count ----

def test_count_zero_initially(tmp_path):
    store = _store(tmp_path)
    assert store.count() == 0


def test_count_after_inserts(tmp_path):
    store = _store(tmp_path)
    store.upsert_chunk(_chunk("a", 0))
    store.upsert_chunk(_chunk("b", 0))
    assert store.count() == 2
