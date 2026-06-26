from __future__ import annotations

from dataclasses import dataclass

from app_backend.services.rag_retrieval_service import RetrievedChunk


_DEFAULT_MAX_CHARS = 4000
_CHUNK_SEPARATOR = "\n---\n"
_SECTION_HEADER = "[知识库参考]"


@dataclass(frozen=True)
class RAGContextBlock:
    """Formatted text block ready to be injected into an LLM prompt.

    text contains only sanitized, length-capped content — no URLs, no
    raw file paths, no API keys, no account data.
    char_count is the length of text (not including the header).
    chunk_count is how many source chunks were included.
    truncated is True when some chunks were dropped due to the char cap.
    excluded_count is how many chunks were filtered because
    external_llm_context_allowed=False (local-only documents).
    """

    text: str
    char_count: int
    chunk_count: int
    truncated: bool
    excluded_count: int = 0


def build_rag_context(
    chunks: list[RetrievedChunk],
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    include_header: bool = True,
) -> RAGContextBlock:
    """Format retrieved chunks into a prompt-ready context block.

    Chunks where external_llm_context_allowed=False are silently excluded
    before any other processing — they must never reach LLM context.
    Chunks are taken in order (caller is responsible for ranking).
    Each chunk is formatted as:
        标题：{title}  [doc_type]
        {text}
    Chunks are added until max_chars would be exceeded; the rest are dropped.
    Returns an empty block (text="") when chunks is empty or all excluded.
    """
    if not isinstance(chunks, list):
        raise TypeError("chunks must be a list")
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")

    parts: list[str] = []
    total = 0
    included = 0
    excluded = 0
    truncated = False

    for chunk in chunks:
        if not isinstance(chunk, RetrievedChunk):
            raise TypeError(f"expected RetrievedChunk, got {type(chunk).__name__}")
        if not chunk.external_llm_context_allowed:
            excluded += 1
            continue
        formatted = _format_chunk_with_tier(chunk)
        candidate_len = len(formatted) + (len(_CHUNK_SEPARATOR) if parts else 0)
        if total + candidate_len > max_chars:
            truncated = True
            break
        if parts:
            parts.append(_CHUNK_SEPARATOR)
            total += len(_CHUNK_SEPARATOR)
        parts.append(formatted)
        total += len(formatted)
        included += 1

    if not parts:
        return RAGContextBlock(
            text="", char_count=0, chunk_count=0, truncated=truncated,
            excluded_count=excluded,
        )

    body = "".join(parts)
    if include_header:
        text = f"{_SECTION_HEADER}\n{body}"
    else:
        text = body

    return RAGContextBlock(
        text=text,
        char_count=len(body),
        chunk_count=included,
        truncated=truncated,
        excluded_count=excluded,
    )


def _format_chunk_with_tier(chunk: RetrievedChunk) -> str:
    labels = [_tier_label(chunk)]
    if chunk.doc_type:
        labels.append(chunk.doc_type)
    if not chunk.is_official_source:
        labels.append("non-official")
    label = f"[{' | '.join(labels)}]"
    header_line = f"Title: {chunk.title} {label}".strip()
    return f"{header_line}\n{chunk.text}"


def _tier_label(chunk: RetrievedChunk) -> str:
    if chunk.evidence_tier == "official_evidence":
        return "OFFICIAL EVIDENCE"
    if chunk.evidence_tier == "institutional_view":
        return "INSTITUTIONAL VIEW"
    return "SOURCE"


def _format_chunk(chunk: RetrievedChunk) -> str:
    label = f"[{chunk.doc_type}]" if chunk.doc_type else ""
    header_line = f"标题：{chunk.title} {label}".strip()
    return f"{header_line}\n{chunk.text}"
