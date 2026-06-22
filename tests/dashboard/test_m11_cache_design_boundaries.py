from pathlib import Path


DESIGN_DOC = Path("docs/archive/p_m4a_m11_shared_context_cache_design.md")
RISK_REGISTER = Path("docs/infra/m11_cache_risk_register.md")


def test_m11_cache_design_docs_exist():
    assert DESIGN_DOC.exists()
    assert RISK_REGISTER.exists()


def test_design_doc_locks_design_only_scope_and_required_boundaries():
    text = DESIGN_DOC.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "No runtime cache implemented" in text
    assert "write_last_good" in text
    assert "cache_bypassed_for_write_last_good" in text
    assert "AI Context Manifest" in text
    assert "in-process only" in text
    assert "no holdings line items" in lowered
    assert "no account values" in lowered
    assert "no prompt persistence" in lowered
    assert "no raw external ai payloads" in lowered


def test_design_doc_does_not_authorize_forbidden_surfaces():
    combined = (
        DESIGN_DOC.read_text(encoding="utf-8")
        + "\n"
        + RISK_REGISTER.read_text(encoding="utf-8")
    ).lower()

    for phrase in (
        "external AI enabled",
        "DeepSeek enabled",
        "Tavily enabled",
        "live fetch enabled",
        "auto trading",
        "trading signal",
        "expected return",
        "scenario probability",
        "forecast path",
        "target allocation",
        "rebalance recommendation",
    ):
        assert phrase.lower() not in combined


def test_risk_register_covers_required_cache_risks():
    text = RISK_REGISTER.read_text(encoding="utf-8").lower()

    for required in (
        "write_last_good",
        "stale market_history db",
        "filtered evidence table",
        "privacy",
        "concurrent request",
    ):
        assert required in text


def test_design_doc_does_not_claim_runtime_cache_exists():
    text = DESIGN_DOC.read_text(encoding="utf-8").lower()

    forbidden_claims = (
        "runtime cache is implemented",
        "cross-request cache currently exists",
        "fastapi routes share a context across http requests",
        "disk persistence is enabled",
        "background refresh is enabled",
    )
    for claim in forbidden_claims:
        assert claim not in text
