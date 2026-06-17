from llm.deepseek_prompt_package import build_deepseek_prompt_package


def _build_prompt(deviation_flags: dict | None) -> str:
    portfolio_context = {}
    if deviation_flags is not None:
        portfolio_context["deviation_flags"] = deviation_flags
    package = build_deepseek_prompt_package(
        question="当前组合方向是什么？",
        answer_style="brief",
        context_json={
            "confirmed_facts": {"portfolio": {}, "market": {}},
            "portfolio_context": portfolio_context,
        },
    )
    return package.prompt_text


def test_snapshot_vs_target_rules_use_dynamic_allocation_direction():
    prompt = _build_prompt(
        {
            "sp500": "overweight",
            "nasdaq100": "overweight",
            "short_bond": "underweight",
            "gold": "underweight",
        }
    )

    assert "sp500 当前相对目标高配" in prompt
    assert "nasdaq100 当前相对目标高配" in prompt
    assert "short_bond 当前相对目标低配" in prompt
    assert "gold 当前相对目标低配" in prompt
    assert "sp500 当前相对目标低配" not in prompt
    assert "nasdaq100 当前相对目标低配" not in prompt
    assert "short_bond 当前相对目标高配" not in prompt
    assert "gold 当前相对目标高配" not in prompt
    assert "不得把这些偏离归因于市场价格下跌、权益市值收缩、利率重定价或其他宏观/市场因素" in prompt


def test_snapshot_vs_target_rules_do_not_invent_direction_when_missing():
    prompt = _build_prompt(None)

    assert "当前 context 未提供可核验的配置偏离方向，不得自行判断高配/低配" in prompt
    assert "sp500 当前相对目标低配" not in prompt
    assert "nasdaq100 当前相对目标低配" not in prompt
    assert "short_bond 当前相对目标高配" not in prompt
    assert "gold 当前相对目标高配" not in prompt
