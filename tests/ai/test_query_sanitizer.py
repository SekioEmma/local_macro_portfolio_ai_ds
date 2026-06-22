from __future__ import annotations

import pytest

from app_backend.services.query_sanitizer import sanitize_query


@pytest.mark.parametrize(
    "query",
    [
        "当前美国通胀和就业数据说明了什么？",
        "What does the latest FOMC statement imply for real yields?",
        "SPY and QQQ performance during the last CPI release",
        "USDCNH 与美国国债收益率的近期关系",
        "CPI 2026-06-10 release preview",
        "Reuters headline about Federal Reserve policy",
        "Compare WTI and Brent supply conditions",
        "How did markets react on 2025-12-17?",
        "联系人指标是否影响劳动力市场分析",
        "王冠债券指数近期表现如何",
        "RMB exchange-rate outlook",
        "美元指数与人民币汇率关系",
        "USD index trend",
        "USDCNH 与 10Y yield 的关系",
    ],
)
def test_safe_macro_queries_pass_unchanged(query: str):
    result = sanitize_query(query)

    assert result.text == query
    assert result.blocked is False
    assert result.findings == []


@pytest.mark.parametrize(
    "query",
    [
        "portfolio value is $12,000",
        "账户规模 USD 50000",
        "现金为 ¥8,000",
        "预算 RMB 100000",
        "我的人民币资产约 20 万",
        "账户中有 3000 美元",
        "总金额是 25万元",
        "RMB 100000",
        "USD 5000",
        "人民币资产 20 万",
        "$12,000",
        "¥8000",
    ],
)
def test_amount_patterns_are_blocked(query: str):
    result = sanitize_query(query)

    assert result.blocked is True
    assert result.text == ""
    assert "amount" in result.findings


@pytest.mark.parametrize(
    "query",
    [
        "SPY:50%",
        "QQQ:0.2",
        "GLD : 10 %",
        "spy:0.15",
    ],
)
def test_ticker_weight_patterns_are_blocked(query: str):
    result = sanitize_query(query)

    assert result.blocked is True
    assert result.text == ""
    assert "ticker_weight" in result.findings


@pytest.mark.parametrize(
    "query",
    [
        "账号 123456789012",
        "账户号码：6222 1234 5678 9012",
        "银行卡号 6222-1234-5678-9012",
        "account number: 123456789",
        "card no. 4111 1111 1111 1111",
    ],
)
def test_account_number_patterns_are_blocked(query: str):
    result = sanitize_query(query)

    assert result.blocked is True
    assert result.text == ""
    assert "account_number" in result.findings


@pytest.mark.parametrize(
    "query",
    [
        r"read C:\Users\Alice\portfolio.csv",
        r"open G:\private\notes.txt",
        "read /Users/alice/portfolio.csv",
        "read /home/alice/notes.txt",
        "read /mnt/data/holdings.csv",
        "/home/a",
        "path=/home/a",
        "file:///Users/a",
        "file=/mnt/data/a",
        r"C:\a",
        "C:/a",
        r"G:\private\a",
    ],
)
def test_local_paths_are_blocked(query: str):
    result = sanitize_query(query)

    assert result.blocked is True
    assert result.text == ""
    assert "local_path" in result.findings


def test_29_character_token_is_allowed():
    token = "a" * 29

    assert sanitize_query(f"lookup {token}").blocked is False


def test_30_character_token_is_blocked():
    token = "a" * 30
    result = sanitize_query(f"lookup {token}")

    assert result.blocked is True
    assert result.text == ""
    assert result.findings == ["long_token"]


@pytest.mark.parametrize(
    "token",
    [
        "header.payload.signature-with-long_segment",
        "abc_def-ghi.jkl_mno-pqr.stu_vwx-yz123456",
        "eyJhbGciOiJIUzI1NiJ9.payload.signature",
    ],
)
def test_long_ascii_tokens_with_separators_are_blocked(token: str):
    result = sanitize_query(f"lookup {token}")

    assert result.blocked is True
    assert result.text == ""
    assert "long_token" in result.findings


@pytest.mark.parametrize(
    "query",
    [
        "姓名：王小明，查询最新宏观新闻",
        "联系人 李雷 的研究请求",
        "我叫张伟，请分析市场",
        "name is Alice Smith, search inflation",
        "contact: John Smith",
    ],
)
def test_explicit_person_name_context_is_blocked(query: str):
    result = sanitize_query(query)

    assert result.blocked is True
    assert result.text == ""
    assert "person_name" in result.findings


@pytest.mark.parametrize(
    "query",
    [
        "姓名字段是否属于隐私数据？",
        "联系人工客服了解 CPI 数据",
        "contact the Federal Reserve about its publication",
        "王冠债券指数近期表现",
        "李克强指数的历史定义是什么",
    ],
)
def test_non_name_context_does_not_trigger_name_guard(query: str):
    assert "person_name" not in sanitize_query(query).findings


def test_plain_ticker_and_macro_acronyms_are_not_weights():
    query = "SPY QQQ CPI FOMC USDCNH macro outlook"

    assert sanitize_query(query).blocked is False


def test_plain_numbers_and_dates_are_not_account_numbers():
    query = "CPI was 3.2 on 2026-06-10 and the 10Y yield moved"

    assert sanitize_query(query).blocked is False


def test_blocked_findings_never_echo_sensitive_input():
    sensitive = r"账号 123456789 and C:\Users\Alice\secret.txt"
    result = sanitize_query(sensitive)

    assert result.text == ""
    assert all("123456789" not in finding for finding in result.findings)
    assert all("Alice" not in finding for finding in result.findings)


def test_multiple_findings_are_stable_and_categorical():
    query = r"账户 123456789 has $500 and file C:\Users\Alice\data.csv"

    first = sanitize_query(query)
    second = sanitize_query(query)

    assert first == second
    assert first.findings == ["amount", "account_number", "local_path"]
    assert all(query not in finding for finding in first.findings)


def test_empty_query_fails_closed():
    result = sanitize_query("   ")

    assert result.blocked is True
    assert result.text == ""
    assert result.findings == ["empty_query"]


def test_normal_long_chinese_sentence_is_not_treated_as_secret_token():
    query = "请分析当前美国通胀就业金融条件和国债收益率之间是否存在相互矛盾的信号"

    assert sanitize_query(query).blocked is False
