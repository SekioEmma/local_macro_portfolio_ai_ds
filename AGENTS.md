# Codex 项目指南

本文件仅供 Codex 使用。`CLAUDE.md` 属于 Claude Code 的独立配置；除非用户明确要求，不修改、不重命名，也不把它配置为 Codex fallback。

## 启动与渐进读取

- 新对话先只做只读状态检查：`git status --short --branch`、`git branch -vv`、必要时查看最近提交。
- 不要在启动时通读整个仓库、整个 `docs/`、`docs/archive/`，也不要自动运行全量测试。
- 项目入口先读 `docs/INDEX.md`；只有需要确认当前路线时再读 `docs/ROADMAP.md`。
- Era 2 工作只读取任务相关部分：
  - 设计与阶段边界：`docs/era2_plan.md` 的对应 Phase/章节。
  - 实施清单与 DoD：`docs/era2_codex_brief.md` 的对应 TASK。
- 优先用 `rg` 定位标题、符号和文件，再读取小范围上下文；除非任务确实横跨全篇，不要整份加载大型文档。
- `docs/archive/` 只用于明确要求的历史追溯；默认不读。
- 模块技术文档按 `docs/INDEX.md` 的分类按需读取，不做全目录预读。

## 当前项目快照

- 主工作分支：`app-mvp`。
- 当前路线：Era 2，下一主线为 Phase A 治理与边界。
- 已有基础：D10–D19、Stage 8、AI-1/AI-1.5 本地研究预览、AI-2 单轮 DeepSeek 研究链。
- AI-2 当前边界：显式用户触发、单轮、默认不保存、不搜索、人工复核。
- 权威入口：`docs/INDEX.md` → `docs/ROADMAP.md` → `docs/GOVERNANCE.md` → 对应 Era 2 章节。
- 若代码、Git 状态与本快照不一致，以当前代码和 Git 状态为准，并指出快照可能过期；不要自行大范围同步文档。

## 工作区与变更边界

- 将现有未提交和未跟踪内容视为用户工作；不覆盖、不回滚、不顺手格式化无关文件。
- 先确认任务范围，再做最小改动。用户缩小范围时，以最新范围为准。
- 未明确要求时，不 commit、不 push。
- 大面积删除文件，或长时间、大范围操控电脑前，必须先征得用户明确许可。
- 新增 API、外部 AI、联网出口、持久化、持仓上下文等 L4 改动，先取得用户明确批准。
- 金融标签、阈值、评分、权重、触发条件以及 D10–D19 / Stage 8 解释边界变化，先取得用户确认。

## 永久安全与隐私边界

- 禁止读取、打印、修改或提交：`.env*`、真实外部配置、`*.sqlite*`、`data/holdings/`、`data/private/`、`data/private_notes/`、`outputs/`、缓存、日志、raw provider payload、API key。
- 不把 holdings/account/position/transaction、真实金额、账号或本地路径发送到外部模型或搜索 query。
- 不弱化现有 fail-closed runtime policy、request/response guard、validator 或 AI Context Manifest eligibility。
- 不修改 D10–D19 / Stage 8 financial semantics，除非任务明确授权。
- 不输出自动交易、真实下单、个股操作建议、概率胜率、择时或黑盒 portfolio optimizer。
- 网络访问只允许出现在任务明确批准且已有策略守门的 transport/provider 边界。

## 实施与验证

- Python 命令在项目约定的 `src/` 上下文运行；前端命令在 `app_frontend/` 运行，Windows 优先使用 `npm.cmd`/`npx.cmd`。
- 先跑与改动直接相关的 targeted tests；只有任务 DoD、风险等级或用户要求需要时才跑全量测试。
- 前端改动至少运行 typecheck；产品面改动按治理要求补 build、路由和隐私/禁止输出检查。
- 不写教学式注释；docstring 保持最多一行；避免为假想需求做抽象。
- 最终报告说明：改动文件、结果、实际运行的测试、隐私检查、剩余风险。未运行的检查要如实说明。
