import json
from pathlib import Path

import pytest

from app_backend.schemas.ai_memo import AIMemoPreview
from app_backend.services.ai_memo_renderer import (
    FORBIDDEN_GENERATED_OUTPUT_TERMS,
    PRIVACY_FORBIDDEN_TERMS,
    render_ai_memo_preview,
    validate_ai_memo_preview,
)


@pytest.mark.parametrize(
    "blocked_term",
    [
        "buy",
        "sell",
        "add position",
        "reduce position",
        "clear position",
        "hedge",
        "rebalance",
        "target allocation",
        "target weight",
        "ideal allocation",
        "expected return",
        "predicted return",
        "future return",
        "market direction probability",
        "crash probability",
        "recession probability",
        "trade signal",
        "strategy return",
        "trading performance",
        "Sharpe",
        "de-risk",
        "rotate into",
        "overweight",
        "underweight",
        "guaranteed",
        "will rise",
        "will fall",
    ],
)
def test_validator_blocks_forbidden_action_allocation_return_probability_fixtures(blocked_term):
    preview = _preview_with_content(blocked_term)

    result = validate_ai_memo_preview(preview)

    assert result.passed is False
    assert blocked_term.lower() in result.blocked_terms


@pytest.mark.parametrize(
    "privacy_term",
    [
        "holdings line items",
        "account values",
        "position weights",
        "raw provider payload",
        "raw prompt",
        "API key",
        ".env",
        "data/private",
        "current_holdings.csv",
        "transaction history",
        "credentials",
    ],
)
def test_validator_blocks_privacy_fixtures(privacy_term):
    preview = _preview_with_content(privacy_term)

    result = validate_ai_memo_preview(preview)

    assert result.passed is False
    assert privacy_term.lower() in result.privacy_findings


def test_validator_blocks_external_model_search_and_default_save_flags():
    preview = render_ai_memo_preview("daily_review_memo", _minimal_manifest())
    payload = preview.as_dict()
    payload["privacy_summary"]["external_model_called"] = True
    payload["privacy_summary"]["search_called"] = True
    payload["privacy_summary"]["saved_by_default"] = True

    result = validate_ai_memo_preview(payload)

    assert result.passed is False
    assert "external_model_called" in result.privacy_findings
    assert "search_called" in result.privacy_findings
    assert "saved_by_default" in result.privacy_findings


def test_validator_blocks_missing_human_review_or_boundary_notice():
    preview = render_ai_memo_preview("daily_review_memo", _minimal_manifest())
    payload = preview.as_dict()
    payload["human_review_required"] = False
    payload["interpretation_boundary"] = ""

    result = validate_ai_memo_preview(payload)

    assert result.passed is False
    assert "human_review_required_missing" in result.privacy_findings
    assert "interpretation_boundary_missing" in result.privacy_findings


def test_renderer_privacy_summary_is_fail_closed():
    preview = render_ai_memo_preview("portfolio_overlay_review", _minimal_manifest())

    assert preview.privacy_summary.uses_ai_context_manifest_only is True
    assert preview.privacy_summary.uses_holdings_line_items is False
    assert preview.privacy_summary.uses_raw_provider_payloads is False
    assert preview.privacy_summary.uses_raw_prompts is False
    assert preview.privacy_summary.external_model_called is False
    assert preview.privacy_summary.search_called is False
    assert preview.privacy_summary.saved_by_default is False


def test_stage_9_1_does_not_add_http_chat_or_memo_endpoints():
    main_text = Path("src/app_backend/main.py").read_text(encoding="utf-8").lower()

    assert "/api/chat" not in main_text
    assert "/api/ai/memo" not in main_text
    assert "/api/memo" not in main_text


def test_stage_9_1_does_not_modify_model_output_modules():
    changed = _git_changed_files()

    forbidden_prefixes = (
        "src/data_quality/",
        "src/modeling/",
        "src/llm/",
    )
    assert not [
        path
        for path in changed
        if path.startswith(forbidden_prefixes)
    ]


def test_stage_9_1_does_not_weaken_forbidden_term_sets():
    assert "target allocation" in FORBIDDEN_GENERATED_OUTPUT_TERMS
    assert "market direction probability" in FORBIDDEN_GENERATED_OUTPUT_TERMS
    assert "current_holdings.csv" in PRIVACY_FORBIDDEN_TERMS
    assert "raw prompt" in PRIVACY_FORBIDDEN_TERMS


def test_preview_schema_round_trips_without_private_flags():
    preview = render_ai_memo_preview("evidence_audit_report", _minimal_manifest())
    encoded_text = (
        preview.model_dump_json()
        if hasattr(preview, "model_dump_json")
        else preview.json()
    )
    encoded = json.loads(encoded_text)
    decoded = AIMemoPreview(**encoded)

    assert decoded.validator_result.passed is True
    assert decoded.privacy_summary.uses_holdings_line_items is False


def _preview_with_content(content):
    preview = render_ai_memo_preview("daily_review_memo", _minimal_manifest()).as_dict()
    preview["sections"][0]["content"] = content
    return preview


def _minimal_manifest():
    return {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "included_facts": [
            {
                "module": "credit_stress",
                "metric_key": "high_yield_spread",
                "display_name": "High yield spread",
                "status": "ok",
                "source_badge": "official",
                "freshness_status": "fresh",
                "interpretation_boundary": "Reference context only.",
            }
        ],
        "excluded_facts": [],
        "included_model_outputs": [],
        "excluded_model_outputs": [],
        "risk_boundaries": ["Reference context only."],
        "privacy_policy": {"returns_sanitized_evidence_rows_only": True},
        "search_policy": {"search_enabled": False},
        "portfolio_context_policy": {"mode": "compact_summary_only"},
        "persistence_policy": {"saves_manifest": False},
        "source_summary": {"total_evidence_rows": 1},
    }


def _git_changed_files():
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
