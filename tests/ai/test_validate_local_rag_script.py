from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_local_rag.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_local_rag", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_local_rag"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_local_rag_requires_index_generation_for_nonempty_index():
    module = _load_module()
    payload = {
        "manifest_audit": {"accepted_documents": 1},
        "consistency": {
            "eligible_manifest_documents": 1,
            "bm25_matches_searchable_chunks": True,
            "local_only_chunks": 0,
            "context_non_empty_under_4000_chars": True,
            "index_generation_present": False,
            "embedding_model_compatible": True,
        },
    }

    assert module._is_valid(payload) is False

    payload["consistency"]["index_generation_present"] = True
    assert module._is_valid(payload) is True
