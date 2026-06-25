from __future__ import annotations

import ast
import importlib
import re
from dataclasses import FrozenInstanceError, fields as dc_fields
from pathlib import Path

import pytest

from app_backend.services.rag_evidence_governance import (
    RagEvidenceAssessment,
    RagEvidenceCandidate,
    RagEvidenceEligibility,
    RagEvidenceExclusionReason,
    RagEvidenceGovernanceError,
    assess_rag_evidence_candidate,
)


_VALID_SHA = "a" * 64
_VALID_URL = "https://example.com/path"
_VALID_DOMAIN = "example.com"
_VALID_FETCHED = "2026-06-24T10:00:00+00:00"
_MODULE_PATH = (
    Path(__file__).parents[2]
    / "src"
    / "app_backend"
    / "services"
    / "rag_evidence_governance.py"
)
_TEST_PATH = Path(__file__)


def _candidate(**overrides):
    base = dict(
        document_id=1,
        url=_VALID_URL,
        title="Sample document",
        source_domain=_VALID_DOMAIN,
        doc_type="policy_doc",
        fetched_at=_VALID_FETCHED,
        content_sha256=_VALID_SHA,
        is_stale=False,
    )
    base.update(overrides)
    return RagEvidenceCandidate(**base)


def _module_source() -> str:
    return _MODULE_PATH.read_text(encoding="utf-8")


def _assert_invalid_candidate(exc: pytest.ExceptionInfo[RagEvidenceGovernanceError]):
    assert exc.value.code == "invalid_candidate"
    rendered = f"{exc.value!s} {exc.value!r}"
    assert "secret" not in rendered
    assert "title" not in rendered.lower()
    assert "https://" not in rendered
    assert exc.value.__context__ is None


def _assert_no_multiline_docstrings(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [tree, *[node for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]]
    for node in nodes:
        doc = ast.get_docstring(node, clean=False)
        assert doc is None or "\n" not in doc


# ========== D0b. Exact candidate and exception-total boundary ==========

def test_d0b_none_is_invalid_candidate():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(None)
    _assert_invalid_candidate(exc)


def test_d0b_dict_is_invalid_candidate_without_leaking_values():
    payload = {"title": "secret title", "url": "https://secret.example/path"}
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(payload)
    _assert_invalid_candidate(exc)


def test_d0b_plain_object_is_invalid_candidate():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(object())
    _assert_invalid_candidate(exc)


def test_d0b_duck_typed_object_is_invalid_candidate():
    class DuckCandidate:
        document_id = 1
        url = "https://secret.example/path"
        title = "secret title"
        source_domain = "secret.example"
        doc_type = "policy_doc"
        fetched_at = _VALID_FETCHED
        content_sha256 = _VALID_SHA
        is_stale = False

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(DuckCandidate())
    _assert_invalid_candidate(exc)


def test_d0b_candidate_subclass_is_invalid_candidate():
    class CandidateSubclass(RagEvidenceCandidate):
        pass

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(CandidateSubclass(**_candidate().__dict__))
    _assert_invalid_candidate(exc)


def test_d0b_candidate_subclass_getattribute_trap_is_not_touched():
    class ExplodingCandidate(RagEvidenceCandidate):
        def __getattribute__(self, name):
            raise RuntimeError("secret attribute access")

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(ExplodingCandidate(**_candidate().__dict__))
    _assert_invalid_candidate(exc)


def test_d0b_non_candidate_secret_repr_is_not_called():
    class SecretRepr:
        def __repr__(self):
            raise RuntimeError("secret repr")

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(SecretRepr())
    _assert_invalid_candidate(exc)


def test_d0b_non_candidate_secret_str_is_not_called():
    class SecretStr:
        def __str__(self):
            raise RuntimeError("secret str")

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(SecretStr())
    _assert_invalid_candidate(exc)


def test_d0b_canonicalization_runtime_error_becomes_invalid_candidate(monkeypatch):
    import app_backend.services.rag_evidence_governance as mod

    def boom(value):
        raise RuntimeError("url secret")

    monkeypatch.setattr(mod, "canonicalize_document_url", boom)
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate())
    _assert_invalid_candidate(exc)


def test_d0b_validation_helper_runtime_error_becomes_invalid_candidate(monkeypatch):
    import app_backend.services.rag_evidence_governance as mod

    def boom(value):
        raise RuntimeError("internal secret")

    monkeypatch.setattr(mod, "_validate_title_shape", boom)
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate())
    _assert_invalid_candidate(exc)


def test_d0b_keyboardinterrupt_is_not_caught(monkeypatch):
    import app_backend.services.rag_evidence_governance as mod

    def boom(value):
        raise KeyboardInterrupt("secret interrupt")

    monkeypatch.setattr(mod, "_validated_document_id", boom)
    with pytest.raises(KeyboardInterrupt):
        assess_rag_evidence_candidate(_candidate())


def test_d0b_systemexit_is_not_caught(monkeypatch):
    import app_backend.services.rag_evidence_governance as mod

    def boom(value):
        raise SystemExit("secret exit")

    monkeypatch.setattr(mod, "_validated_document_id", boom)
    with pytest.raises(SystemExit):
        assess_rag_evidence_candidate(_candidate())


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"url": "http://example.com/p"}, "invalid_document_url"),
        ({"source_domain": "evil.example"}, "invalid_source_domain"),
        ({"title": ""}, "invalid_title"),
        ({"doc_type": "discard"}, "invalid_document_type"),
        ({"fetched_at": "2026-06-24T10:00:00"}, "invalid_fetched_at"),
        ({"content_sha256": "A" * 64}, "invalid_content_sha256"),
        ({"is_stale": 0}, "invalid_is_stale"),
    ],
)
def test_d0b_exact_candidate_field_errors_preserve_stable_codes(
    overrides,
    expected_code,
):
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(**overrides))
    assert exc.value.code == expected_code


def test_d0b_module_docstrings_are_single_line_or_absent():
    _assert_no_multiline_docstrings(_MODULE_PATH)


def test_d0b_test_docstrings_are_single_line_or_absent():
    _assert_no_multiline_docstrings(_TEST_PATH)


# ========== A. Normal admission path ==========

def test_a_valid_policy_doc_is_eligible():
    out = assess_rag_evidence_candidate(_candidate(doc_type="policy_doc"))
    assert out.eligibility == "eligible"
    assert out.exclusion_reason is None


def test_a_valid_research_report_is_eligible():
    out = assess_rag_evidence_candidate(_candidate(doc_type="research_report"))
    assert out.eligibility == "eligible"
    assert out.exclusion_reason is None


def test_a_eligibility_value_matches_enum_member():
    out = assess_rag_evidence_candidate(_candidate())
    assert out.eligibility == RagEvidenceEligibility.ELIGIBLE.value


def test_a_assessment_field_order_is_locked():
    names = [f.name for f in dc_fields(RagEvidenceAssessment)]
    assert names == [
        "document_id",
        "url",
        "source_domain",
        "doc_type",
        "fetched_at",
        "content_sha256",
        "eligibility",
        "exclusion_reason",
        "external_llm_context_allowed",
        "allowed_use",
    ]


def test_a_candidate_field_order_is_locked():
    names = [f.name for f in dc_fields(RagEvidenceCandidate)]
    assert names == [
        "document_id",
        "url",
        "title",
        "source_domain",
        "doc_type",
        "fetched_at",
        "content_sha256",
        "is_stale",
        "external_llm_context_allowed",
        "allowed_use",
    ]


def test_a_assessment_has_no_title_attribute():
    out = assess_rag_evidence_candidate(_candidate(title="HEADLINE SECRET"))
    assert not hasattr(out, "title")


def test_a_assessment_repr_does_not_include_title():
    out = assess_rag_evidence_candidate(_candidate(title="HEADLINE_NEEDLE_TOKEN"))
    assert "HEADLINE_NEEDLE_TOKEN" not in repr(out)


def test_a_fetched_at_z_suffix_normalised_to_offset():
    out = assess_rag_evidence_candidate(
        _candidate(fetched_at="2026-06-24T10:00:00Z")
    )
    assert out.fetched_at == "2026-06-24T10:00:00+00:00"


def test_a_fetched_at_offset_normalised_to_utc():
    out = assess_rag_evidence_candidate(
        _candidate(fetched_at="2026-06-24T10:00:00+05:00")
    )
    assert out.fetched_at == "2026-06-24T05:00:00+00:00"


def test_a_fetched_at_negative_offset_normalised_to_utc():
    out = assess_rag_evidence_candidate(
        _candidate(fetched_at="2026-06-24T10:00:00-04:00")
    )
    assert out.fetched_at == "2026-06-24T14:00:00+00:00"


def test_a_canonical_url_is_https_normalised_form():
    out = assess_rag_evidence_candidate(_candidate(url="https://example.com/path"))
    assert out.url == "https://example.com/path"


def test_a_source_domain_matches_canonical_hostname():
    out = assess_rag_evidence_candidate(_candidate())
    assert out.source_domain == "example.com"


def test_a_source_domain_mixed_case_is_normalised():
    out = assess_rag_evidence_candidate(_candidate(source_domain="Example.COM"))
    assert out.source_domain == "example.com"


def test_a_source_domain_trailing_dot_is_normalised():
    out = assess_rag_evidence_candidate(_candidate(source_domain="example.com."))
    assert out.source_domain == "example.com"


def test_a_candidate_is_frozen():
    cand = _candidate()
    with pytest.raises(FrozenInstanceError):
        cand.document_id = 999  # type: ignore[misc]


def test_a_assessment_is_frozen():
    out = assess_rag_evidence_candidate(_candidate())
    with pytest.raises(FrozenInstanceError):
        out.eligibility = "excluded"  # type: ignore[misc]


def test_a_assess_is_idempotent_for_same_input():
    cand = _candidate()
    assert assess_rag_evidence_candidate(cand) == assess_rag_evidence_candidate(cand)


def test_a_assess_does_not_mutate_candidate():
    cand = _candidate(title="Original Title")
    assess_rag_evidence_candidate(cand)
    assert cand.title == "Original Title"
    assert cand.document_id == 1


# ========== B. Fixed exclusion policy ==========

def test_b_stale_policy_doc_excluded_with_stale_reason():
    out = assess_rag_evidence_candidate(
        _candidate(doc_type="policy_doc", is_stale=True)
    )
    assert out.eligibility == "excluded"
    assert out.exclusion_reason == "stale_document"


def test_b_stale_research_report_excluded_with_stale_reason():
    out = assess_rag_evidence_candidate(
        _candidate(doc_type="research_report", is_stale=True)
    )
    assert out.eligibility == "excluded"
    assert out.exclusion_reason == "stale_document"


def test_b_stale_historical_data_priority_is_stale():
    out = assess_rag_evidence_candidate(
        _candidate(doc_type="historical_data", is_stale=True)
    )
    assert out.exclusion_reason == "stale_document"


def test_b_stale_one_shot_news_priority_is_stale():
    out = assess_rag_evidence_candidate(
        _candidate(doc_type="one_shot_news", is_stale=True)
    )
    assert out.exclusion_reason == "stale_document"


def test_b_historical_data_fresh_excluded_with_historical_reason():
    out = assess_rag_evidence_candidate(_candidate(doc_type="historical_data"))
    assert out.eligibility == "excluded"
    assert out.exclusion_reason == "historical_data_excluded"


def test_b_one_shot_news_fresh_excluded_with_news_reason():
    out = assess_rag_evidence_candidate(_candidate(doc_type="one_shot_news"))
    assert out.eligibility == "excluded"
    assert out.exclusion_reason == "one_shot_news_excluded"


def test_b_eligible_has_none_reason():
    out = assess_rag_evidence_candidate(_candidate())
    assert out.exclusion_reason is None


def test_b_excluded_reason_is_non_empty_string():
    for dt in ("historical_data", "one_shot_news"):
        out = assess_rag_evidence_candidate(_candidate(doc_type=dt))
        assert isinstance(out.exclusion_reason, str)
        assert out.exclusion_reason


def test_b_stale_exclusion_reason_is_non_empty_string():
    out = assess_rag_evidence_candidate(_candidate(is_stale=True))
    assert isinstance(out.exclusion_reason, str)
    assert out.exclusion_reason == "stale_document"


def test_b_exclusion_reason_value_is_a_member_of_enum():
    out = assess_rag_evidence_candidate(_candidate(doc_type="historical_data"))
    assert out.exclusion_reason in {m.value for m in RagEvidenceExclusionReason}


def test_b_eligibility_value_is_a_member_of_enum():
    out = assess_rag_evidence_candidate(_candidate())
    assert out.eligibility in {m.value for m in RagEvidenceEligibility}


def test_b_policy_doc_explicitly_not_stale_remains_eligible():
    out = assess_rag_evidence_candidate(
        _candidate(doc_type="policy_doc", is_stale=False)
    )
    assert out.eligibility == "eligible"


def test_b_research_report_explicitly_not_stale_remains_eligible():
    out = assess_rag_evidence_candidate(
        _candidate(doc_type="research_report", is_stale=False)
    )
    assert out.eligibility == "eligible"


# ========== C. Metadata validation ==========

# ---- document_id ----

def test_c_document_id_zero_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(document_id=0))
    assert exc.value.code == "invalid_document_id"


def test_c_document_id_negative_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(document_id=-1))
    assert exc.value.code == "invalid_document_id"


def test_c_document_id_true_rejected_because_bool_is_not_int():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(document_id=True))
    assert exc.value.code == "invalid_document_id"


def test_c_document_id_false_rejected_because_bool_is_not_int():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(document_id=False))
    assert exc.value.code == "invalid_document_id"


def test_c_document_id_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(document_id="1"))
    assert exc.value.code == "invalid_document_id"


def test_c_document_id_float_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(document_id=1.0))
    assert exc.value.code == "invalid_document_id"


def test_c_document_id_none_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(document_id=None))
    assert exc.value.code == "invalid_document_id"


def test_c_document_id_large_int_accepted():
    out = assess_rag_evidence_candidate(_candidate(document_id=2**40))
    assert out.document_id == 2**40


# ---- URL ----

def test_c_url_http_scheme_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url="http://example.com/p"))
    assert exc.value.code == "invalid_document_url"


def test_c_url_with_query_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url="https://example.com/p?q=1"))
    assert exc.value.code == "invalid_document_url"


def test_c_url_with_fragment_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url="https://example.com/p#x"))
    assert exc.value.code == "invalid_document_url"


def test_c_url_with_userinfo_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url="https://user@example.com/p"))
    assert exc.value.code == "invalid_document_url"


def test_c_url_with_port_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url="https://example.com:8443/p"))
    assert exc.value.code == "invalid_document_url"


def test_c_url_localhost_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(url="https://localhost/p", source_domain="localhost")
        )
    assert exc.value.code == "invalid_document_url"


def test_c_url_ipv4_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(url="https://10.0.0.1/p", source_domain="10.0.0.1")
        )
    assert exc.value.code == "invalid_document_url"


def test_c_url_path_traversal_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url="https://example.com/../etc"))
    assert exc.value.code == "invalid_document_url"


def test_c_url_not_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url=12345))
    assert exc.value.code == "invalid_document_url"


def test_c_url_empty_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(url=""))
    assert exc.value.code == "invalid_document_url"


# ---- source_domain ----

def test_c_source_domain_mismatch_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(source_domain="other.example.com"))
    assert exc.value.code == "invalid_source_domain"


def test_c_source_domain_not_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(source_domain=12345))
    assert exc.value.code == "invalid_source_domain"


def test_c_source_domain_whitespace_only_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(source_domain="   "))
    assert exc.value.code == "invalid_source_domain"


def test_c_source_domain_str_subclass_rejected():
    class _StrSub(str):
        pass

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(source_domain=_StrSub("example.com"))
        )
    assert exc.value.code == "invalid_source_domain"


# ---- title ----

def test_c_title_empty_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(title=""))
    assert exc.value.code == "invalid_title"


def test_c_title_whitespace_only_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(title="   "))
    assert exc.value.code == "invalid_title"


def test_c_title_over_500_chars_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(title="x" * 501))
    assert exc.value.code == "invalid_title"


def test_c_title_exactly_500_chars_accepted():
    out = assess_rag_evidence_candidate(_candidate(title="x" * 500))
    assert out.eligibility == "eligible"


def test_c_title_not_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(title=42))
    assert exc.value.code == "invalid_title"


def test_c_title_str_subclass_rejected():
    class _StrSub(str):
        pass

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(title=_StrSub("hello")))
    assert exc.value.code == "invalid_title"


# ---- doc_type ----

def test_c_doc_type_unknown_string_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(doc_type="news_article"))
    assert exc.value.code == "invalid_document_type"


def test_c_doc_type_discard_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(doc_type="discard"))
    assert exc.value.code == "invalid_document_type"


def test_c_doc_type_research_needed_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(doc_type="research_needed"))
    assert exc.value.code == "invalid_document_type"


def test_c_doc_type_search_derived_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(doc_type="search-derived"))
    assert exc.value.code == "invalid_document_type"


def test_c_doc_type_str_subclass_rejected():
    class _StrSub(str):
        pass

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(doc_type=_StrSub("policy_doc")))
    assert exc.value.code == "invalid_document_type"


def test_c_doc_type_empty_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(doc_type=""))
    assert exc.value.code == "invalid_document_type"


def test_c_doc_type_not_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(doc_type=42))
    assert exc.value.code == "invalid_document_type"


# ---- fetched_at ----

def test_c_fetched_at_without_timezone_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(fetched_at="2026-06-24T10:00:00"))
    assert exc.value.code == "invalid_fetched_at"


def test_c_fetched_at_malformed_string_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(fetched_at="not a date"))
    assert exc.value.code == "invalid_fetched_at"


def test_c_fetched_at_not_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(fetched_at=20260624))
    assert exc.value.code == "invalid_fetched_at"


def test_c_fetched_at_str_subclass_rejected():
    class _StrSub(str):
        pass

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(fetched_at=_StrSub("2026-06-24T10:00:00+00:00"))
        )
    assert exc.value.code == "invalid_fetched_at"


def test_c_fetched_at_empty_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(fetched_at=""))
    assert exc.value.code == "invalid_fetched_at"


# ---- content_sha256 ----

def test_c_sha_too_short_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(content_sha256="a" * 63))
    assert exc.value.code == "invalid_content_sha256"


def test_c_sha_too_long_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(content_sha256="a" * 65))
    assert exc.value.code == "invalid_content_sha256"


def test_c_sha_uppercase_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(content_sha256="A" * 64))
    assert exc.value.code == "invalid_content_sha256"


def test_c_sha_non_hex_char_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(content_sha256="z" * 64))
    assert exc.value.code == "invalid_content_sha256"


def test_c_sha_str_subclass_rejected():
    class _StrSub(str):
        pass

    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(content_sha256=_StrSub("a" * 64))
        )
    assert exc.value.code == "invalid_content_sha256"


def test_c_sha_not_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(content_sha256=12345))
    assert exc.value.code == "invalid_content_sha256"


def test_c_sha_valid_lowercase_hex_accepted():
    valid = "0123456789abcdef" * 4
    out = assess_rag_evidence_candidate(_candidate(content_sha256=valid))
    assert out.content_sha256 == valid


# ---- is_stale ----

def test_c_is_stale_zero_int_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(is_stale=0))
    assert exc.value.code == "invalid_is_stale"


def test_c_is_stale_one_int_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(is_stale=1))
    assert exc.value.code == "invalid_is_stale"


def test_c_is_stale_none_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(is_stale=None))
    assert exc.value.code == "invalid_is_stale"


def test_c_is_stale_string_true_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(_candidate(is_stale="true"))
    assert exc.value.code == "invalid_is_stale"


def test_c_is_stale_true_accepted():
    out = assess_rag_evidence_candidate(_candidate(is_stale=True))
    assert out.eligibility == "excluded"
    assert out.exclusion_reason == "stale_document"


def test_c_is_stale_false_accepted():
    out = assess_rag_evidence_candidate(_candidate(is_stale=False))
    assert out.eligibility == "eligible"


# ========== D. Privacy / boundary scan ==========

def test_d_candidate_field_set_locked():
    names = {f.name for f in dc_fields(RagEvidenceCandidate)}
    expected = {
        "document_id",
        "url",
        "title",
        "source_domain",
        "doc_type",
        "fetched_at",
        "content_sha256",
        "is_stale",
        "external_llm_context_allowed",
        "allowed_use",
    }
    assert names == expected


def test_d_candidate_has_no_forbidden_fields():
    names = {f.name for f in dc_fields(RagEvidenceCandidate)}
    forbidden = {
        "raw_text",
        "text",
        "chunk",
        "chunk_text",
        "raw_text_path",
        "path",
        "db_path",
        "embedding",
        "vector",
        "score",
        "similarity",
        "rank",
        "provider_payload",
        "search_result",
        "holdings",
        "account",
        "position",
        "transaction",
        "private_note",
        "private_notes",
        "prompt",
        "model_context",
    }
    assert not (names & forbidden)


def test_d_assessment_field_set_locked():
    names = {f.name for f in dc_fields(RagEvidenceAssessment)}
    expected = {
        "document_id",
        "url",
        "source_domain",
        "doc_type",
        "fetched_at",
        "content_sha256",
        "eligibility",
        "exclusion_reason",
        "external_llm_context_allowed",
        "allowed_use",
    }
    assert names == expected


def test_d_assessment_has_no_title_field():
    names = {f.name for f in dc_fields(RagEvidenceAssessment)}
    assert "title" not in names


def test_d_assessment_has_no_forbidden_fields():
    names = {f.name for f in dc_fields(RagEvidenceAssessment)}
    forbidden = {
        "title",
        "raw_text",
        "chunk",
        "raw_text_path",
        "db_path",
        "embedding",
        "vector",
        "score",
        "rank",
        "payload",
        "private_note",
        "private_notes",
        "holdings",
        "account",
    }
    assert not (names & forbidden)


def test_d_module_source_no_persistence_modules():
    src = _module_source()
    for token in ("sqlite3", "pathlib"):
        assert token not in src, f"{token!r} found in module"


def test_d_module_source_no_http_client_imports():
    src = _module_source()
    for token in ("httpx", "requests", "aiohttp"):
        assert token not in src, f"{token!r} found in module"


def test_d_module_source_no_env_or_dotenv():
    src = _module_source()
    for token in ("os.getenv", "os.environ", "dotenv"):
        assert token not in src, f"{token!r} found in module"


def test_d_module_source_no_fastapi_or_main():
    src = _module_source()
    for token in ("FastAPI", "APIRouter", "main.py", "fastapi"):
        assert token not in src, f"{token!r} found in module"


def test_d_module_source_no_external_provider_names():
    src = _module_source()
    for token in ("Tavily", "tavily", "DeepSeek", "deepseek"):
        assert token not in src, f"{token!r} found in module"


def test_d_module_source_no_rag_runtime_terms():
    src = _module_source()
    for token in (
        "embedding",
        "sentence_transformers",
        "Chroma",
        "BM25",
        "vector",
        "retrieve",
    ):
        assert token not in src, f"{token!r} found in module"


def test_d_module_source_has_no_standalone_search_token():
    """The substring ``search`` may appear only inside safe compound terms."""
    src = _module_source()
    assert re.search(r"\bsearch\b", src) is None


def test_d_module_source_no_raw_or_private_path_tokens():
    src = _module_source()
    for token in ("raw_text", "raw_text_path", "private_notes"):
        assert token not in src, f"{token!r} found in module"


def test_d_module_does_not_import_knowledge_base_service():
    src = _module_source()
    assert "knowledge_base_service" not in src


def test_d_module_has_no_runtime_method_names():
    import app_backend.services.rag_evidence_governance as mod

    forbidden = {
        "read",
        "load",
        "chunk",
        "embed",
        "query",
        "retrieve",
        "search",
        "write",
        "ingest",
    }
    public = {name for name in dir(mod) if not name.startswith("_")}
    overlap = public & forbidden
    assert not overlap, f"forbidden public names: {overlap}"


def test_d_assess_function_is_exposed():
    import app_backend.services.rag_evidence_governance as mod

    fn = getattr(mod, "assess_rag_evidence_candidate", None)
    assert callable(fn)


def test_d_module_all_export_matches_expected():
    import app_backend.services.rag_evidence_governance as mod

    assert set(mod.__all__) == {
        "RagEvidenceAssessment",
        "RagEvidenceCandidate",
        "RagEvidenceEligibility",
        "RagEvidenceExclusionReason",
        "RagEvidenceGovernanceError",
        "assess_rag_evidence_candidate",
    }


def test_d_assessment_repr_does_not_leak_title_value():
    out = assess_rag_evidence_candidate(
        _candidate(title="LEAK_SENTINEL_TOKEN_TITLE")
    )
    assert "LEAK_SENTINEL_TOKEN_TITLE" not in repr(out)


def test_d_assessment_repr_does_not_carry_forbidden_tokens():
    out = assess_rag_evidence_candidate(_candidate())
    rendered = repr(out)
    for token in (
        "raw_text",
        "chunk",
        "embedding",
        "private_notes",
        "holdings",
        "account",
        "payload",
    ):
        assert token not in rendered, f"{token!r} appeared in assessment repr"


def test_d_module_import_creates_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import app_backend.services.rag_evidence_governance as mod

    saved = dict(mod.__dict__)
    before = sorted(p.name for p in tmp_path.iterdir())
    importlib.reload(mod)
    after = sorted(p.name for p in tmp_path.iterdir())
    # Restore pre-reload state so subsequent tests in the same process
    # see the original class objects from their top-level imports.
    mod.__dict__.clear()
    mod.__dict__.update(saved)
    assert before == after


def test_d_governance_error_carries_stable_code():
    err = RagEvidenceGovernanceError("invalid_document_id")
    assert err.code == "invalid_document_id"
    assert "invalid_document_id" in str(err)


def test_d_governance_error_is_valueerror_subclass():
    err = RagEvidenceGovernanceError("invalid_title")
    assert isinstance(err, ValueError)


# ========== E. Regression ==========

def test_e_knowledge_document_type_unchanged():
    from app_backend.services.knowledge_base_contracts import KnowledgeDocumentType

    assert KnowledgeDocumentType.POLICY_DOC.value == "policy_doc"
    assert KnowledgeDocumentType.RESEARCH_REPORT.value == "research_report"
    assert KnowledgeDocumentType.HISTORICAL_DATA.value == "historical_data"
    assert KnowledgeDocumentType.ONE_SHOT_NEWS.value == "one_shot_news"


def test_e_canonicalize_document_url_unchanged():
    from app_backend.services.knowledge_base_contracts import canonicalize_document_url

    canonical, hostname = canonicalize_document_url("https://example.com/p")
    assert canonical == "https://example.com/p"
    assert hostname == "example.com"


def test_e_knowledge_base_admission_error_unchanged():
    from app_backend.services.knowledge_base_contracts import (
        KnowledgeBaseAdmissionError,
    )

    err = KnowledgeBaseAdmissionError("invalid_url")
    assert err.code == "invalid_url"


def test_e_d0_does_not_register_api_route():
    """Loading the governance module must not modify the FastAPI app object."""
    from app_backend import main as main_module

    routes_before = list(main_module.app.routes)
    importlib.import_module("app_backend.services.rag_evidence_governance")
    assert list(main_module.app.routes) == routes_before


def test_e_d0_module_can_be_reimported_without_side_effects():
    import app_backend.services.rag_evidence_governance as mod

    saved = dict(mod.__dict__)
    first = mod.RagEvidenceEligibility.ELIGIBLE.value
    importlib.reload(mod)
    second = mod.RagEvidenceEligibility.ELIGIBLE.value
    mod.__dict__.clear()
    mod.__dict__.update(saved)
    assert first == second == "eligible"


# ========== F. external_llm_context_allowed + allowed_use fields ==========

def test_f_local_only_candidate_is_excluded():
    out = assess_rag_evidence_candidate(
        _candidate(external_llm_context_allowed=False, allowed_use="local_search_only")
    )
    assert out.eligibility == "excluded"
    assert out.exclusion_reason == "local_only_use"


def test_f_local_only_reason_is_lower_priority_than_stale():
    out = assess_rag_evidence_candidate(
        _candidate(is_stale=True, external_llm_context_allowed=False,
                   allowed_use="local_search_only")
    )
    assert out.exclusion_reason == "stale_document"


def test_f_local_only_reason_is_lower_priority_than_doc_type_exclusion():
    out = assess_rag_evidence_candidate(
        _candidate(doc_type="historical_data", external_llm_context_allowed=False,
                   allowed_use="local_search_only")
    )
    assert out.exclusion_reason == "historical_data_excluded"


def test_f_external_context_candidate_default_is_eligible():
    out = assess_rag_evidence_candidate(_candidate())
    assert out.external_llm_context_allowed is True
    assert out.allowed_use == "external_context_candidate"
    assert out.eligibility == "eligible"


def test_f_assessment_carries_external_llm_context_allowed():
    out = assess_rag_evidence_candidate(
        _candidate(external_llm_context_allowed=True, allowed_use="external_context_candidate")
    )
    assert out.external_llm_context_allowed is True


def test_f_assessment_carries_allowed_use():
    out = assess_rag_evidence_candidate(
        _candidate(external_llm_context_allowed=False, allowed_use="local_search_only")
    )
    assert out.allowed_use == "local_search_only"


def test_f_external_llm_context_allowed_int_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(external_llm_context_allowed=1)
        )
    assert exc.value.code == "invalid_external_llm_context_allowed"


def test_f_external_llm_context_allowed_none_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(external_llm_context_allowed=None)
        )
    assert exc.value.code == "invalid_external_llm_context_allowed"


def test_f_allowed_use_unknown_value_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(allowed_use="everything")
        )
    assert exc.value.code == "invalid_allowed_use"


def test_f_allowed_use_not_str_rejected():
    with pytest.raises(RagEvidenceGovernanceError) as exc:
        assess_rag_evidence_candidate(
            _candidate(allowed_use=True)
        )
    assert exc.value.code == "invalid_allowed_use"


def test_f_local_only_use_is_in_exclusion_reason_enum():
    from app_backend.services.rag_evidence_governance import RagEvidenceExclusionReason
    assert "local_only_use" in {m.value for m in RagEvidenceExclusionReason}
