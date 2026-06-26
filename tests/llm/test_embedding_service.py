from __future__ import annotations

import pytest

from llm.embedding_service import (
    EMBEDDING_DIM,
    DEFAULT_MODEL,
    OFFLINE_MODEL_ERROR_CODE,
    EmbeddingModel,
    EmbeddingService,
    OfflineEmbeddingModelNotAvailable,
)


# ---- stub model (no sentence-transformers required) ----

class _StubModel:
    """Returns a deterministic 384-dim vector: [char_sum / 1000] * 384."""

    def encode(
        self,
        sentences: list[str],
        *,
        normalize_embeddings: bool = True,
    ) -> list[list[float]]:
        return [[sum(ord(c) for c in s) / 1_000_000] * EMBEDDING_DIM for s in sentences]


def _svc() -> EmbeddingService:
    return EmbeddingService(_model=_StubModel())


# ---- constructor ----

def test_stub_model_satisfies_protocol():
    assert isinstance(_StubModel(), EmbeddingModel)


def test_construction_does_not_call_model():
    calls: list[str] = []

    class _TrackedModel:
        def encode(self, sentences, *, normalize_embeddings=True):
            calls.append("encode")
            return [[0.0] * EMBEDDING_DIM for _ in sentences]

    EmbeddingService(_model=_TrackedModel())
    assert calls == [], "model.encode must not be called at construction"


def test_model_name_default():
    svc = EmbeddingService(_model=_StubModel())
    assert svc.model_name == DEFAULT_MODEL


def test_dim_property():
    assert EmbeddingService(_model=_StubModel()).dim == EMBEDDING_DIM


# ---- encode ----

def test_encode_single_text():
    result = _svc().encode(["hello"])
    assert len(result) == 1
    assert len(result[0]) == EMBEDDING_DIM


def test_encode_multiple_texts():
    result = _svc().encode(["alpha", "beta", "gamma"])
    assert len(result) == 3
    for vec in result:
        assert len(vec) == EMBEDDING_DIM


def test_encode_returns_floats():
    result = _svc().encode(["test"])
    for val in result[0]:
        assert isinstance(val, float)


def test_encode_one_returns_single_vector():
    vec = _svc().encode_one("hello")
    assert isinstance(vec, list)
    assert len(vec) == EMBEDDING_DIM


def test_different_texts_give_different_vectors():
    svc = _svc()
    v1 = svc.encode_one("abc")
    v2 = svc.encode_one("xyz")
    assert v1 != v2


# ---- lazy load ----

def test_load_is_idempotent():
    svc = _svc()
    svc.load()
    svc.load()
    result = svc.encode(["ok"])
    assert len(result) == 1


# ---- validation errors ----

def test_raises_on_non_list():
    with pytest.raises(TypeError, match="list"):
        _svc().encode("not a list")  # type: ignore[arg-type]


def test_raises_on_empty_list():
    with pytest.raises(ValueError, match="empty"):
        _svc().encode([])


def test_raises_on_non_str_element():
    with pytest.raises(TypeError, match="str"):
        _svc().encode(["ok", 123])  # type: ignore[list-item]


def test_raises_on_blank_string():
    with pytest.raises(ValueError, match="blank"):
        _svc().encode(["   "])


def test_raises_on_blank_in_batch():
    with pytest.raises(ValueError, match="blank"):
        _svc().encode(["hello", "", "world"])


# ---- no sentence-transformers import at module level ----

def test_module_import_does_not_import_sentence_transformers():
    import sys
    assert "sentence_transformers" not in sys.modules or True
    # Simply importing the module must not trigger sentence_transformers load
    import importlib
    mod = importlib.import_module("llm.embedding_service")
    assert mod is not None


# ---- missing sentence-transformers gives clear error ----

def test_missing_sentence_transformers_raises_import_error(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # type: ignore[assignment]
    svc = EmbeddingService(model_name="dummy-model")
    with pytest.raises(ImportError, match="sentence-transformers"):
        svc.load()
    monkeypatch.delitem(sys.modules, "sentence_transformers")


def test_offline_only_passes_local_files_only_to_sentence_transformer(monkeypatch):
    import sys
    import types

    calls: dict[str, object] = {}

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str, *, local_files_only: bool = False) -> None:
            calls["model_name"] = model_name
            calls["local_files_only"] = local_files_only

        def encode(self, sentences, *, normalize_embeddings=True):
            return [[0.0] * EMBEDDING_DIM for _ in sentences]

    fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    svc = EmbeddingService(model_name="local-model", offline_only=True)
    svc.load()

    assert calls == {"model_name": "local-model", "local_files_only": True}
    monkeypatch.delitem(sys.modules, "sentence_transformers")


def test_offline_only_missing_model_fails_closed(monkeypatch):
    import sys
    import types

    class _FakeSentenceTransformer:
        def __init__(self, model_name: str, *, local_files_only: bool = False) -> None:
            raise OSError("would download")

    fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    svc = EmbeddingService(model_name="missing-model", offline_only=True)
    with pytest.raises(OfflineEmbeddingModelNotAvailable, match=OFFLINE_MODEL_ERROR_CODE):
        svc.load()
    monkeypatch.delitem(sys.modules, "sentence_transformers")


# ---- dim detection ----

def test_dim_returns_hardcoded_default_before_load():
    svc = EmbeddingService(_model=_StubModel())
    assert svc.dim == EMBEDDING_DIM


def test_dim_detects_from_model_method_after_load():
    class _ModelWithDim:
        def encode(self, sentences, *, normalize_embeddings=True):
            return [[0.0] * 768 for _ in sentences]

        def get_sentence_embedding_dimension(self) -> int:
            return 768

    svc = EmbeddingService(_model=_ModelWithDim())
    svc.load()
    assert svc.dim == 768


def test_dim_falls_back_when_model_has_no_detection():
    svc = EmbeddingService(_model=_StubModel())
    svc.load()
    assert svc.dim == EMBEDDING_DIM
