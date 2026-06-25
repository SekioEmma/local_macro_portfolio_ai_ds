from __future__ import annotations

from typing import Protocol, runtime_checkable


DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIM = 384
OFFLINE_MODEL_ERROR_CODE = "embedding_model_not_available_offline"


class OfflineEmbeddingModelNotAvailable(ImportError):
    pass


@runtime_checkable
class EmbeddingModel(Protocol):
    """Minimal interface required by the embedding service."""

    def encode(
        self,
        sentences: list[str],
        *,
        normalize_embeddings: bool = True,
    ) -> list[list[float]]: ...


class EmbeddingService:
    """Wraps a sentence-transformers model with lazy loading and a clean encode API.

    The underlying model is NOT loaded at construction time.  Call encode()
    or load() explicitly.  This keeps import-time free of network / disk I/O
    and lets tests inject a stub via the constructor.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        _model: EmbeddingModel | None = None,
        offline_only: bool = False,
    ) -> None:
        self._model_name = model_name
        self._model: EmbeddingModel | None = _model
        self._offline_only = offline_only

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Explicitly load the model into memory (idempotent)."""
        if self._model is None:
            self._model = _load_sentence_transformer(self._model_name, offline_only=self._offline_only)

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text.

        Raises ValueError for empty lists or blank strings.
        Loads the model on first call if not already loaded.
        """
        if not isinstance(texts, list):
            raise TypeError("texts must be a list of str")
        if not texts:
            raise ValueError("texts must not be empty")
        for i, t in enumerate(texts):
            if not isinstance(t, str):
                raise TypeError(f"texts[{i}] must be str, got {type(t).__name__}")
            if not t.strip():
                raise ValueError(f"texts[{i}] is blank; blank strings cannot be embedded")

        if self._model is None:
            self.load()

        raw = self._model.encode(texts, normalize_embeddings=True)  # type: ignore[union-attr]
        return _to_float_list(raw)

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _load_sentence_transformer(model_name: str, *, offline_only: bool = False) -> EmbeddingModel:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers is not installed. "
            "Run: pip install sentence-transformers"
        ) from exc
    if not offline_only:
        return SentenceTransformer(model_name)  # type: ignore[return-value]
    try:
        return SentenceTransformer(model_name, local_files_only=True)  # type: ignore[return-value]
    except Exception as exc:
        raise OfflineEmbeddingModelNotAvailable(OFFLINE_MODEL_ERROR_CODE) from exc


def _to_float_list(raw: object) -> list[list[float]]:
    """Normalize ndarray or nested list to list[list[float]]."""
    try:
        import numpy as np  # type: ignore[import-untyped]

        if isinstance(raw, np.ndarray):
            return raw.tolist()
    except ImportError:
        pass
    if isinstance(raw, list):
        result: list[list[float]] = []
        for row in raw:
            if isinstance(row, list):
                result.append([float(x) for x in row])
            else:
                try:
                    result.append(row.tolist())
                except AttributeError:
                    result.append(list(row))
        return result
    raise TypeError(f"Unexpected embedding output type: {type(raw)}")
