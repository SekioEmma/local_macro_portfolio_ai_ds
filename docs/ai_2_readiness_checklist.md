# AI-2 Single-Turn External Model Pilot — Readiness Checklist

## Scope

此 checklist 必须全绿才允许启动 AI-2。任一项不通过，必须先解决再考虑
AI-2。本报告仅记录本地 AI-1.5 评估结果，不授权外部模型、搜索、持久化或
产品化工作。

## 检查项

- [x] **PASS — 所有 golden fixture 通过 7 段结构断言**

  证据：`python -m pytest tests/ai/test_ai_research_structure_contract.py -v`
  退出码 0。

  实测：`86 passed`；其中 fixture 契约 `85 / 85` 通过，fixture 目录规模、
  test_id 唯一性与文件名一致性检查 `1 / 1` 通过。

- [x] **PASS — 所有 adversarial 题正确拒绝**

  证据：`python -m pytest tests/ai/test_ai_research_adversarial.py -v`
  退出码 0；`docs/ai_research_quality_audit_2026-06-19.md`。

  实测：硬编码 adversarial 测试 `19 / 19` 通过；golden adversarial fixture
  的闭合请求契约 / output blocker / 明确拒绝边界合并处理率为
  `15 / 15 = 100.00%`。

- [x] **FAIL — semantic validator 在 adversarial 上 blocker 命中率 = 100%**

  证据：`docs/ai_research_quality_audit_2026-06-19.md`。

  实测：原始输出 semantic blocker 命中率为 `0 / 15 = 0.00%`，未达到
  `100%` 要求。

  原因：`AIResearchPreviewRequest` 禁止 free-form `question` 字段，越界问题
  在进入 renderer 前由闭合请求契约拒绝；安全预览随后输出固定拒绝边界，
  因此不会把已拒绝的用户文本作为“模型输出”再次标记为 blocker。

  缓解建议：在任何未来单轮外部模型入口之前增加独立的 input-boundary
  semantic validator，使动作、概率、私密账户内容与来源替代请求在输入层产生
  明确 blocker，并把该输入 blocker 纳入同一审计指标。完成后重新运行
  AI-1.5 全套验证。

- [x] **PASS — semantic validator 在普通题上误报率 < 5%**

  证据：`docs/ai_research_quality_audit_2026-06-19.md`。

  实测：`0 / 70 = 0.00%`。

- [x] **PASS — 所有 mode × detail_level 下 `prompt_budget.ready = true`**

  证据：`docs/ai_research_quality_audit_2026-06-19.md`。

  实测：六种 answer mode × 三种 detail level 共 `18 / 18` 组合均有覆盖；
  `ready=false` 数量为 `0`。85 个 fixture 的选中卡片数均为 `96 / 96`，
  估算 token 为 `7,577–8,324 / 12,000`。

- [x] **PASS — 全套 `pytest -q` 通过**

  证据：`python -m pytest -q` 退出码 0。

  实测：`1696 passed, 0 failed, 1 warning`，耗时 `244.18s`。warning 为既有
  Starlette TestClient / httpx deprecation warning。

- [x] **PASS — manifest 中没有 holdings / raw payload / raw prompt 泄漏**

  证据：`python scripts/dev_check_validator_boundaries.py` 退出码 0。

  实测：`allowed=9, blocked=8, regression=17`；manifest 手动检查：
  `returns_holdings_line_items=false`、`returns_provider_payloads=false`、
  `saves_prompt_text=false`。

- [x] **PASS — AI Context Manifest `model_destination` 仍为 `local_preview_only`**

  证据：手动执行 `ai_context_service.build_ai_context_manifest()` 并检查
  `_privacy_policy` / `model_destination`。

  实测：`destination=local_preview_only`；
  `returns_holdings_line_items=false`；
  `returns_provider_payloads=false`。

- [x] **PASS — `external_ai_enabled` / `chat_enabled` / `deepseek_enabled` / `tavily_enabled` 全部为 `False`**

  证据：源码 grep 与默认 policy / manifest 手动实例化。

  实测：

  - `external_ai_enabled=False`
  - `chat_enabled=False`
  - `deepseek_enabled=False`
  - `tavily_enabled=False`

- [x] **PASS — 数据底座 audit 通过**

  证据：

  - `python scripts/audit_data_foundation_gaps.py`：退出码 0，
    `status=PASS`，`errors=0`；
  - `python scripts/audit_data_pipeline_coverage.py`：退出码 0，
    `219` evidence rows，`125` included facts，`63` included model outputs。

  说明：coverage 报告的 `overall_status=degraded` 来自
  `portfolio_deviation: module_status=pressure`，属于当前数据状态，不是
  audit 合同错误或来源门禁失败。

- [x] **PASS — historical validation 边界 0 违反**

  证据：`python scripts/run_historical_validation.py --format text`
  退出码 0。

  实测：`11` events total，`2` available，`3` limited，`6` insufficient，
  `boundary_violations=0`。

- [x] **PASS — benchmark 通过**

  证据：`python scripts/benchmark_dashboard_pipeline.py` 退出码 0。

  实测：`45,243` market-history observations / `45` metrics；
  `219` evidence rows；shared summary/evidence/manifest total
  `2,085.16 ms`；`estimated_rebuilds_avoided=2`；数据库 metric/date 索引存在。

## 最终结论

- [x] **未全绿，不可提交 AI-2 启动请求。**
- [x] 已通过项：`11 / 12`。
- [x] 未通过项：`1 / 12`。
- [x] 未通过项：原始输出 semantic validator 在 adversarial fixture 上的
  blocker 命中率为 `0.00%`，未达到 `100%`。
- [x] 下一步仅应进行 AI-1.5 输入边界 blocker 设计与验证；完成并全绿前，
  不应启动 AI-2 或任何外部模型工作。

## 验证日期 & HEAD

日期：`2026-06-19`

验证基线 HEAD：`138fc521ce1f313598b4a27f3ee2bd71e90d7584`
