from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int


def chunk_text(
    text: str,
    doc_id: str,
    *,
    chunk_chars: int = 1200,
    overlap_chars: int = 200,
) -> list[Chunk]:
    """Split text into overlapping chunks suitable for embedding.

    Strategy: paragraph-first (split on blank lines), then slide a character
    window when a single paragraph exceeds chunk_chars.  Overlap ensures
    queries that straddle chunk boundaries still find the relevant passage.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if chunk_chars < 1:
        raise ValueError("chunk_chars must be >= 1")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must be >= 0")
    if overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars must be < chunk_chars")

    text = text.strip()
    if not text:
        return []

    paragraphs = _split_paragraphs(text)
    raw_spans = _paragraphs_to_spans(paragraphs, text)

    chunks: list[Chunk] = []
    buf_text = ""
    buf_start = 0
    idx = 0

    for para, (p_start, p_end) in zip(paragraphs, raw_spans):
        if not para:
            continue

        if len(para) > chunk_chars:
            if buf_text:
                chunks.append(_make_chunk(doc_id, idx, buf_text, buf_start))
                idx += 1
                buf_text = ""

            for sub_text, sub_start in _slide(para, p_start, chunk_chars, overlap_chars):
                chunks.append(_make_chunk(doc_id, idx, sub_text, sub_start))
                idx += 1

            buf_text = ""
            continue

        pending = (buf_text + "\n\n" + para) if buf_text else para
        if len(pending) <= chunk_chars:
            if not buf_text:
                buf_start = p_start
            buf_text = pending
        else:
            if buf_text:
                chunks.append(_make_chunk(doc_id, idx, buf_text, buf_start))
                idx += 1
            buf_text = para
            buf_start = p_start

    if buf_text:
        chunks.append(_make_chunk(doc_id, idx, buf_text, buf_start))

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n{2,}", text)]


def _paragraphs_to_spans(paragraphs: list[str], text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for para in paragraphs:
        start = text.find(para, cursor)
        if start == -1:
            start = cursor
        end = start + len(para)
        spans.append((start, end))
        cursor = end
    return spans


def _slide(
    text: str,
    base_offset: int,
    chunk_chars: int,
    overlap_chars: int,
) -> list[tuple[str, int]]:
    step = chunk_chars - overlap_chars
    results: list[tuple[str, int]] = []
    pos = 0
    while pos < len(text):
        window = text[pos : pos + chunk_chars]
        results.append((window.strip(), base_offset + pos))
        if pos + chunk_chars >= len(text):
            break
        pos += step
    return results


def _make_chunk(doc_id: str, idx: int, text: str, char_start: int) -> Chunk:
    text = text.strip()
    return Chunk(
        doc_id=doc_id,
        chunk_index=idx,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )
