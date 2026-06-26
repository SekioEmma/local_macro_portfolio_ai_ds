from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_COLLECTION = "macro_knowledge"
_MAX_QUERY_RESULTS = 50


@dataclass(frozen=True)
class VectorSearchResult:
    doc_id: str
    chunk_index: int
    score: float
    metadata: dict[str, Any]


class VectorStore:
    """Persistent local vector store backed by Chroma.

    The Chroma client and collection are created lazily on first use.
    Tests inject a stub client via _client to avoid the chromadb dependency.

    All documents are stored in a single flat collection keyed by
    "{doc_id}::{chunk_index}".  Metadata always includes doc_id and
    chunk_index so results are self-describing.
    """

    def __init__(
        self,
        persist_dir: Path,
        collection_name: str = DEFAULT_COLLECTION,
        *,
        _client: Any = None,
    ) -> None:
        if not isinstance(persist_dir, Path):
            raise TypeError("persist_dir must be a Path")
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._client_override = _client
        self._client: Any = None
        self._collection: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(
        self,
        doc_id: str,
        chunk_index: int,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace a chunk embedding."""
        _validate_doc_id(doc_id)
        _validate_chunk_index(chunk_index)
        _validate_embedding(embedding)
        col = self._get_collection()
        item_id = _item_id(doc_id, chunk_index)
        meta = dict(metadata or {})
        meta["doc_id"] = doc_id
        meta["chunk_index"] = chunk_index
        col.upsert(ids=[item_id], embeddings=[embedding], metadatas=[meta])

    def upsert_many(self, items: list[tuple[str, int, list[float], dict[str, Any]]]) -> None:
        if not isinstance(items, list):
            raise TypeError("items must be a list")
        if not items:
            return
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        for doc_id, chunk_index, embedding, metadata in items:
            _validate_doc_id(doc_id)
            _validate_chunk_index(chunk_index)
            _validate_embedding(embedding)
            meta = dict(metadata or {})
            meta["doc_id"] = doc_id
            meta["chunk_index"] = chunk_index
            ids.append(_item_id(doc_id, chunk_index))
            embeddings.append(embedding)
            metadatas.append(meta)
        self._get_collection().upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

    def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        *,
        doc_type_filter: str | None = None,
    ) -> list[VectorSearchResult]:
        """Return up to top_k nearest neighbours."""
        _validate_embedding(embedding)
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if top_k > _MAX_QUERY_RESULTS:
            raise ValueError(f"top_k must be <= {_MAX_QUERY_RESULTS}")
        col = self._get_collection()
        where = {"doc_type": doc_type_filter} if doc_type_filter else None
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": top_k,
            "include": ["metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        raw = col.query(**kwargs)
        return _parse_query_results(raw)

    def delete(self, doc_id: str) -> int:
        """Delete all chunks for doc_id. Returns count deleted."""
        _validate_doc_id(doc_id)
        col = self._get_collection()
        existing = col.get(where={"doc_id": doc_id}, include=["metadatas"])
        ids = existing.get("ids", [])
        if ids:
            col.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return self._get_collection().count()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        client = self._client_override or self._make_client()
        self._client = client
        self._collection = client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def _make_client(self) -> Any:
        try:
            import chromadb  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "chromadb is not installed. Run: pip install chromadb"
            ) from exc
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(self._persist_dir))


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _item_id(doc_id: str, chunk_index: int) -> str:
    return f"{doc_id}::{chunk_index}"


def _validate_doc_id(doc_id: str) -> None:
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError("doc_id must be a non-empty str")


def _validate_chunk_index(chunk_index: int) -> None:
    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
        raise ValueError("chunk_index must be a non-negative int")


def _validate_embedding(embedding: list[float]) -> None:
    if not isinstance(embedding, list):
        raise TypeError("embedding must be a list of float")
    if not embedding:
        raise ValueError("embedding must not be empty")


def _parse_query_results(raw: dict[str, Any]) -> list[VectorSearchResult]:
    ids_outer = raw.get("ids") or [[]]
    dists_outer = raw.get("distances") or [[]]
    metas_outer = raw.get("metadatas") or [[]]
    ids = ids_outer[0] if ids_outer else []
    dists = dists_outer[0] if dists_outer else []
    metas = metas_outer[0] if metas_outer else []

    results: list[VectorSearchResult] = []
    for item_id, dist, meta in zip(ids, dists, metas):
        meta = meta or {}
        doc_id = meta.get("doc_id", item_id.split("::")[0])
        chunk_index = int(meta.get("chunk_index", 0))
        score = float(1.0 - dist) if dist is not None else 0.0
        results.append(VectorSearchResult(
            doc_id=doc_id,
            chunk_index=chunk_index,
            score=score,
            metadata={k: v for k, v in meta.items() if k not in ("doc_id", "chunk_index")},
        ))
    return results
