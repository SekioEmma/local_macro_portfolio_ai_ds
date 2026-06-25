from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BM25Result:
    doc_id: str
    chunk_index: int
    score: float


class BM25Index:
    """BM25 keyword index over text chunks.

    Backed by rank_bm25 (BM25Okapi).  The index is built in-memory from a
    list of (doc_id, chunk_index, text) triples and queried by plain string.
    There is no persistent state — callers rebuild the index from the raw text
    store each time (suitable for knowledge bases of a few hundred documents).

    rank_bm25 is imported lazily so the module can be imported without it
    installed.  Tests inject a stub via _bm25_factory.
    """

    def __init__(self, *, _bm25_factory: Any = None) -> None:
        self._bm25_factory = _bm25_factory
        self._corpus: list[tuple[str, int]] = []
        self._tokenized: list[list[str]] = []
        self._bm25: Any = None
        self._built = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, chunks: list[tuple[str, int, str]]) -> None:
        """Build or rebuild the index from a list of (doc_id, chunk_index, text).

        Calling build() again replaces the previous index entirely.
        """
        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list")
        self._corpus = []
        self._tokenized = []
        for item in chunks:
            if len(item) != 3:
                raise ValueError("Each chunk must be (doc_id, chunk_index, text)")
            doc_id, chunk_index, text = item
            if not isinstance(doc_id, str) or not doc_id.strip():
                raise ValueError("doc_id must be a non-empty str")
            if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
                raise ValueError("chunk_index must be a non-negative int")
            if not isinstance(text, str):
                raise ValueError("text must be str")
            self._corpus.append((doc_id, chunk_index))
            self._tokenized.append(_tokenize(text))

        if self._tokenized:
            factory = self._bm25_factory or _default_bm25_factory
            self._bm25 = factory(self._tokenized)
        else:
            self._bm25 = None
        self._built = True

    def query(self, text: str, top_k: int = 5) -> list[BM25Result]:
        """Return up to top_k results ranked by BM25 score."""
        if not self._built:
            raise RuntimeError("Call build() before query()")
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if not text.strip():
            return []
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if self._bm25 is None:
            return []

        tokens = _tokenize(text)
        scores = self._bm25.get_scores(tokens)
        indexed = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k]
        results: list[BM25Result] = []
        for i, score in indexed:
            if score <= 0:
                continue
            doc_id, chunk_index = self._corpus[i]
            results.append(BM25Result(doc_id=doc_id, chunk_index=chunk_index, score=float(score)))
        return results

    @property
    def size(self) -> int:
        return len(self._corpus)

    @property
    def is_built(self) -> bool:
        return self._built


# ------------------------------------------------------------------
# Tokenizer
# ------------------------------------------------------------------

_CJK_RE = re.compile(r"[一-鿿㐀-䶿＀-￯　-〿]")


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + CJK char-level tokenizer.

    For Latin text: lowercase and split on non-word characters.
    For CJK characters: emit each character as its own token.
    Both are mixed in the same pass so bilingual text is handled.
    """
    tokens: list[str] = []
    parts = re.split(r"(\s+)", text.lower())
    for part in parts:
        if not part.strip():
            continue
        cjk_split = _CJK_RE.split(part)
        cjk_chars = _CJK_RE.findall(part)
        for i, seg in enumerate(cjk_split):
            for word in re.split(r"[^\w]+", seg):
                if word:
                    tokens.append(word)
            if i < len(cjk_chars):
                tokens.append(cjk_chars[i])
    return [t for t in tokens if t]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _default_bm25_factory(tokenized_corpus: list[list[str]]) -> Any:
    try:
        from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "rank-bm25 is not installed. Run: pip install rank-bm25"
        ) from exc
    return BM25Okapi(tokenized_corpus)
