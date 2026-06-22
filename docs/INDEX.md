# Local Macro Portfolio AI DS

本地优先宏观风险研究工作台。CS 学习 > 宏观研究 > 投资工具。

## 入口

| 文件 | 干什么 |
|---|---|
| [ROADMAP.md](ROADMAP.md) | 当前路线（Era 2 进行中） |
| [GOVERNANCE.md](GOVERNANCE.md) | 治理、隐私红线、L1–L4 task 体系、coding agent 协议 |
| [era2_plan.md](era2_plan.md) | Era 2 完整开发计划 |
| [era2_codex_brief.md](era2_codex_brief.md) | Era 2 codex 任务书 |
| [../CLAUDE.md](../CLAUDE.md) | 项目级硬安全约束 |

## 项目是什么

- 宏观风险证据系统
- 可解释金融 / 数学模型层
- 个人组合风险解释层
- AI 研究上下文基础
- 中文专业研报系统

## 项目不是什么

- 自动交易
- 短期预测引擎
- AI 选股
- 新闻情绪交易
- Portfolio optimizer
- 券商同步
- 实时行情终端

## 快速开始

```bash
# 后端
cd src && python -m uvicorn app_backend.main:app --reload --host 127.0.0.1 --port 8000

# 前端
cd app_frontend && npm run dev

# 测试
cd src && python -m pytest ../tests/ -x -q

# 前端 typecheck
cd app_frontend && npx tsc --noEmit
```

## 命名空间

### D-line 金融 / 宏观模型模块

新文档优先人话名，D ID 为 legacy alias。完整映射见 [GOVERNANCE.md §6](GOVERNANCE.md#6-命名规范)。

- Financial Stress Composite（D10）
- Pullback vs Systemic Risk Review（D11）
- Historical Risk Normalization（D13）
- Liquidity & Funding Stress（D14）
- Macro Regime Review（D15）
- Scenario Stress Matrix（D16）
- Growth & Inflation Context（D17）
- Valuation & Equity Structure Context（D18）
- Historical Validation Replay（D19）
- Portfolio Exposure Overlay（Stage 8）

### Era 路线

- Era 0：数据基座（完成）
- Era 1：前端美化（完成，tag `era1-frontend-redesign-complete`）
- **Era 2：AI Agent**（当前）
- Era 3：中国数据 + 移动端 + 自动化（未来）

详见 [ROADMAP.md](ROADMAP.md)。

## 模块技术文档

### dashboard/ — 服务架构与 pipeline

- [dashboard/dashboard_service_architecture.md](dashboard/dashboard_service_architecture.md)
- [dashboard/dashboard_evidence_table.md](dashboard/dashboard_evidence_table.md)
- [dashboard/dashboard_financial_spec_v1.md](dashboard/dashboard_financial_spec_v1.md)
- [dashboard/dashboard_historical_derived_integration.md](dashboard/dashboard_historical_derived_integration.md)
- [dashboard/dashboard_orchestration_audit.md](dashboard/dashboard_orchestration_audit.md)
- [dashboard/dashboard_show_all_detail.md](dashboard/dashboard_show_all_detail.md)
- [dashboard/audit_pipeline_architecture.md](dashboard/audit_pipeline_architecture.md)

### models/ — D10–D19 模型模块、指标、语义

- [models/financial_stress_composite.md](models/financial_stress_composite.md)
- [models/liquidity_funding_stress.md](models/liquidity_funding_stress.md)
- [models/pullback_systemic_checklist.md](models/pullback_systemic_checklist.md)
- [models/historical_derived_metrics.md](models/historical_derived_metrics.md)
- [models/historical_percentile_method_note.md](models/historical_percentile_method_note.md)
- [models/historical_percentile_metrics.md](models/historical_percentile_metrics.md)
- [models/historical_validation_event_notes.md](models/historical_validation_event_notes.md)
- [models/macro_display_semantics_and_labels.md](models/macro_display_semantics_and_labels.md)
- [models/metric_interpretation_boundaries.md](models/metric_interpretation_boundaries.md)
- [models/portfolio_deviation_compact.md](models/portfolio_deviation_compact.md)
- [models/proxy_breadth_metrics.md](models/proxy_breadth_metrics.md)
- [models/valuation_breadth_research_plan.md](models/valuation_breadth_research_plan.md)

### data/ — 数据源、provider、基础设施

- [data/app_state_sqlite.md](data/app_state_sqlite.md)
- [data/core_risk_history_backfill.md](data/core_risk_history_backfill.md)
- [data/data_foundation_g2_source_supplementation.md](data/data_foundation_g2_source_supplementation.md)
- [data/data_foundation_gap_fill_v1.md](data/data_foundation_gap_fill_v1.md)
- [data/data_foundation_local_refresh_g1.md](data/data_foundation_local_refresh_g1.md)
- [data/data_pipeline_coverage_audit.md](data/data_pipeline_coverage_audit.md)
- [data/last_good_cache.md](data/last_good_cache.md)
- [data/market_history_store.md](data/market_history_store.md)
- [data/official_macro_pack.md](data/official_macro_pack.md)
- [data/valuation_source_research.md](data/valuation_source_research.md)
- [data/yfinance_batch_history_provider.md](data/yfinance_batch_history_provider.md)

### ai/ — AI context、manifest、研究预览

- [ai/ai_context_manifest.md](ai/ai_context_manifest.md)
- [ai/ai_context_manifest_contract.md](ai/ai_context_manifest_contract.md)
- [ai/ai_memo_context_contract.md](ai/ai_memo_context_contract.md)
- [ai/ai_readiness_design.md](ai/ai_readiness_design.md)
- [ai/ai_research_quality_audit_2026-06-19.md](ai/ai_research_quality_audit_2026-06-19.md)
- [ai/ai_1_local_research_preview_closeout.md](ai/ai_1_local_research_preview_closeout.md)
- [ai/ai_1a_card_priority_semantic_foundation.md](ai/ai_1a_card_priority_semantic_foundation.md)

### frontend/ — UI 开发与架构

- [frontend/app_frontend_dev.md](frontend/app_frontend_dev.md)
- [frontend/frontend_information_architecture_audit.md](frontend/frontend_information_architecture_audit.md)
- [frontend/frontend_registry_architecture.md](frontend/frontend_registry_architecture.md)

### infra/ — 运维、缓存、性能、runbook

- [infra/local_runbook.md](infra/local_runbook.md)
- [infra/performance_baseline.md](infra/performance_baseline.md)
- [infra/m11_cache_risk_register.md](infra/m11_cache_risk_register.md)
- [infra/foundation_stabilization_backlog.md](infra/foundation_stabilization_backlog.md)

## 历史归档

`docs/archive/` 含已完成 stage 的收尾文档、旧路线图版本、旧 Era 2 计划补丁。一般不需要再读，仅作历史 traceability。

## 当前真相

- 分支：`app-mvp`
- 阶段：Era 2 进行中
- 上一里程碑：AI-2 单轮 DeepSeek V4 Pro 研究端点完成
- 下一里程碑：Era 2 Phase A（治理与边界）
- 详见 [ROADMAP.md](ROADMAP.md)
