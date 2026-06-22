> Legacy note:
> This document is a historical APP roadmap and is no longer the current
> execution source. It is superseded by `docs/current_project_state.md`,
> `docs/modeling_roadmap.md`, `docs/short_term_development_plan.md`,
> `docs/stage9_3b_one_shot_review.md`,
> `docs/stage9_3b_security_closeout.md`, and
> `docs/d19_historical_validation_v0.md`.
>
> Do not use this file to authorize DeepSeek Chat productization, Tavily,
> frontend AI UI, full-account external context, persistence, or API endpoints.
> External AI line remains frozen after Stage 9.3-B-2d. The current phase is
> Stage DF, and the next engineering task after DF-0 is D19 v1 historical
> evidence-row integration.

# Local Macro Portfolio AI DS APP 最终项目架构与开发计划定稿

## 0. 当前阶段判断

当前项目已经从 Python DS-first CLI 原型进入“APP 化前的稳定基底阶段”。已有能力包括：市场/宏观数据获取、provider fallback、provider health check、portfolio snapshot、market temperature、daily report、llm context pack、DeepSeek analyst memo、validator guardrails、pytest 最小测试、隐私文档。

APP 化方向确定为：先建设本地 FastAPI 后端 API，再做本地 Web UI，最后再考虑 Tauri Windows 桌面打包。短期不追求漂亮 UI，不追求一次性全功能，不做自动交易，不做后台自动任务，不做多用户，不做云同步。

项目的核心价值不是“做一个普通聊天机器人”，而是：

* 本地持仓与目标配置可维护。
* 市场与宏观数据可追踪。
* 数据源状态与缺失信息可诊断。
* AI 回答严格区分已确认数据、合理推断、缺失信息和不可判断事项。
* 自由聊天与正式 analyst memo 共存，但边界清楚。
* 用户始终保留人工审核权。

## 1. 产品定位

这是一个个人自用的本地投研工作台，长期形态是：

市场数据监控 + 资产配置记录 + AI 投资聊天助手 + 正式 analyst memo 生成器。

第一阶段重点不是 UI，而是稳定后端与数据接口。APP 第一版应优先解决：

1. 打开本地页面后能看到今日市场状态。
2. 能维护几类资产总额。
3. 能基于完整账户和市场上下文自由问 DeepSeek。
4. 需要新闻/IPO/政策时显式打开 Tavily 联网搜索。
5. 搜索结果必须引用来源。
6. 回答不能编造市场数据，不能给交易指令。

## 2. 非目标

明确不做：

* 不做自动交易。
* 不执行买卖。
* 不输出具体买卖指令。
* 不预测短期涨跌。
* 不做登录锁。
* 不做多用户。
* 不做云同步。
* 不做正式发布。
* 不做券商同步。
* 不做实时行情 WebSocket。
* 不把 API key 存进 SQLite。
* 不默认保存全部聊天。
* 不把 search-derived / proxy 数据混入正式判断链。
* 不在没有可靠来源时把 PE / forward PE / CAPE 当成确认事实。
* 第一轮不做 React、不做 Tauri、不做 SQLite holdings 写入、不做 DeepSeek chat、不做 Tavily。

## 3. 总体技术架构

### 3.1 后端

使用 Python FastAPI 作为本地后端服务。

启动方式：

```powershell
python scripts/run_app_backend.py
```

默认只监听：

```text
127.0.0.1:<fixed_port>
```

禁止绑定：

```text
0.0.0.0
```

固定端口，冲突时报清晰错误，不自动乱换端口。

第一阶段只提供只读 API，不做后台自动刷新，不触发 live provider 网络请求。

### 3.2 前端

未来使用：

```text
React + Vite + TypeScript
```

第一阶段不做前端。后端 API 稳定后再做本地 Web UI。Web UI 稳定后，再考虑 Tauri 打包。

### 3.3 桌面壳

Tauri 后置。只有当 FastAPI + 本地 Web UI 已稳定后，才进入 Tauri 打包阶段。

Tauri 第一版只负责：

* 启动/连接本地服务。
* 打开本地界面。
* 后端启动失败时提示。
* 端口冲突时提示。
* 日志只保留最近一次。

### 3.4 存储

长期计划：

* SQLite 作为 APP 状态库。
* Account phase 后，SQLite 成为账户真源。
* CSV 只作为兼容现有 pipeline 的导出文件。

短期阶段：

* Phase 0 / Phase 1 不切账户真源。
* Phase 0 不引入 SQLite。
* Phase 2 才建立 app state SQLite。
* Phase 5 才让 SQLite 成为 holdings 真源。

CSV 兼容方向固定为：

```text
SQLite -> data/holdings/current_holdings.csv
```

不做双向同步，避免冲突。

## 4. 隐私与安全边界

### 4.1 永不提交 / 不上传

以下内容不得进入 Git，不得进入 API 响应，不得进入日志：

* `.env`
* API keys
* `data/holdings/current_holdings.csv`
* `data/private`
* `outputs/reports`
* `outputs/analyst_memos`
* raw provider response
* raw prompt
* 完整持仓明细
* 完整 request body 中的账户上下文

### 4.2 DeepSeek 边界

Legacy / superseded note: the old full context plan below is not current and is
for historical APP-roadmap context only. Current Stage 9.3 and Stage DF
boundaries do not allow external AI context to include holdings line items,
account values, position weights, transaction history, full-account external
context, or complete holdings. The external AI line remains frozen.

旧计划曾假设用户接受默认 full context，由 DeepSeek 接收完整账户金额、资产配置、
市场摘要和配置规则。This is not current execution guidance and must not be used
to authorize provider payloads.

但 UI 必须明确显示：

```text
LEGACY / NOT CURRENT:
当前模式：完整账户上下文
该请求会发送账户金额、配置偏离和市场上下文给 DeepSeek
```

普通聊天默认不保存。只有用户点击收藏时，才保存：

* 问题
* 回答
* 模型
* 成本
* 引用
* 结构化 context snapshot

收藏时保存结构化 context JSON，不保存最终完整 prompt 文本。

### 4.3 Tavily 边界

Tavily 作为 Beta 开关，默认关闭。

Tavily 搜索只发送用户原问题，不发送账户上下文，不发送 holdings，不发送配置偏离。

搜索结果进入 DeepSeek prompt 作为引用材料。联网事实必须显示来源。搜索失败时，系统只能基于本地 context 回答，并明确说明搜索失败，不能编造最新信息。

普通搜索结果不长期缓存。只有当用户收藏回答时，才随收藏保存标题、URL、摘要、时间。

### 4.4 FastAPI 边界

FastAPI 只监听 `127.0.0.1`。

CORS 不允许 `*`。Phase 0 如果没有前端，可以不启用 CORS；Phase 1 后只允许：

```text
http://localhost:<frontend_port>
http://127.0.0.1:<frontend_port>
```

`/api/status` 不返回完整 `project_root`。可返回：

* app_name
* mode
* storage_mode
* git branch
* git commit short hash
* api_keys_configured true/false
* privacy_boundaries
* project_root_exists true/false

完整路径只允许作为 debug 内部信息，不在默认 API 响应展示。

## 5. 数据流

### 5.1 当前 CLI 数据流

继续保留：

```text
provider health check
-> market data check
-> daily report
-> llm context pack
-> analyst memo
```

CLI 永久保留，作为事实验证和调试入口。

### 5.2 APP 只读数据流

Phase 0 API 只读取已有状态，不主动触发刷新：

* provider health：读取 `outputs/reports/provider_health_check.json`
* dashboard summary：读取已有 compact output 或返回 missing
* status：读取环境变量 configured/missing 状态，不输出 key 值

如果输出文件不存在，返回：

```json
{
  "status": "missing",
  "next_action": "python scripts/xxx.py"
}
```

### 5.3 后续刷新数据流

后续才加入显式刷新端点：

```text
POST /api/provider-health/refresh
POST /api/refresh/market
```

这些端点必须由用户手动触发，不能页面打开自动触发 live API 请求。

## 6. Dashboard 数据模型

Dashboard 第一版必须围绕六大模块，不应先追求复杂估值数据。

六大模块：

1. `credit_stress`

   * high_yield_spread
   * investment_grade_spread if available
   * VIX

2. `rate_pressure`

   * DGS10
   * DGS30
   * DGS10 / DGS30 5d avg
   * DGS10 / DGS30 10d avg
   * distance_to_5pct
   * breakout_confirmed

3. `real_yield_pressure`

   * real_yield_10y / DFII10

4. `inflation_energy_pressure`

   * core CPI
   * core PCE
   * PPIACO
   * WTI
   * Brent
   * WTI / Brent 30D change

5. `equity_trend`

   * S&P 500 30D / 60D
   * Nasdaq 100 30D / 60D

6. `portfolio_deviation`

   * 当前资产权重
   * 目标 5:2:2:1
   * 偏离方向
   * 偏离幅度
   * 不做偏离成因归因，除非有 attribution 数据

辅助模块：

* `provider_health`
* `missing_data`
* `data_freshness`

Dashboard 显示规则：

* 首页第一屏显示“今日市场状态 + 风险等级”。
* provider health 常驻小状态条。
* missing/research_needed 常驻小卡片。
* 市场温度可显示 0–100 UI 分，但不进入 AI factual context。
* 所有数据来源必须显示 badge：

  * official
  * fallback
  * proxy
  * search-derived
  * missing
  * research_needed

PE / forward PE / CAPE、market breadth、mega-cap concentration、FedWatch 等后置为 research/proxy，不进入第一阶段正式 dashboard 判断链。

## 7. AI 与搜索设计

### 7.1 普通聊天

默认：

* DeepSeek Flash
* full context
* ChatGPT 式自然解释
* 普通聊天不保存
* 投资分析类回答跑 validator
* 非投资闲聊不强制跑 validator

用户可手动切换：

* Pro 模型
* 结构化分析风格
* sanitized context
* Tavily 搜索

### 7.2 Analyst memo

保留正式 analyst memo 按钮。

Analyst memo 与普通聊天分离：

* 不混入普通聊天记录。
* 使用正式 memo prompt。
* 强制 human review。
* 显示 hard/soft flags。
* 适合作为每周/重大事件正式报告。

### 7.3 Validator

Validator 不是用来替代人工判断，而是用于阻断高风险错误：

* 编造未提供市场数据
* 引用未提供外部来源
* 编造 FedWatch / PE / Bloomberg / FactSet / Reuters
* 把 FRED daily DGS 写成盘中高点
* 把 stale data 写成 current
* 输出交易化指令
* 误用 cash reserve
* 把配置偏离归因于宏观因素

不再无限扩展 validator 规则。后续新增规则必须有真实样本或测试 case 支撑。

## 8. SQLite / CSV 兼容方案

### 8.1 Phase 0 / 1

不切账户真源。不做 holdings 写入。不做 SQLite。

### 8.2 Phase 2

建立 SQLite app state，但不迁移 holdings 真源。

表：

* app_settings
* refresh_runs
* chat_sessions
* chat_messages
* favorite_answers

API key 不入库。

普通聊天默认不保存；收藏才保存。

### 8.3 Phase 5

SQLite 成为账户真源。

holdings schema 支持基金级，但 UI 暂时只展示和编辑类别级。

UI MVP 编辑字段：

* asset_class
* current_value
* notes
* updated_at

schema 可保留但 UI 暂不重点使用：

* asset_name
* fund_code
* cost_basis
* profit_loss
* currency

保存规则：

* 保存前显示改动摘要。
* 用户确认后写 SQLite。
* 写入后导出 `data/holdings/current_holdings.csv`。
* 导出后复用现有 `portfolio_engine` 校验。
* 超过 7 天未更新，dashboard 显示 stale 提醒。

不做：

* 版本历史
* 回滚
* 交易流水
* 券商同步
* 收益率/成本分析

## 9. 分阶段 MVP 路线图

### Phase 0：FastAPI Backend Skeleton

目标：

建立本地 FastAPI 后端外壳，提供只读 API。

新增：

* `src/app_backend/`
* `src/app_backend/main.py`
* `src/app_backend/schemas/`
* `src/app_backend/services/`
* `scripts/run_app_backend.py`
* `tests/test_app_backend_api.py`

API：

* `GET /api/status`
* `GET /api/provider-health`
* `GET /api/dashboard/summary`

要求：

* 不做前端。
* 不做 SQLite。
* 不做账户写入。
* 不调用 DeepSeek。
* 不调用 Tavily。
* 不触发 live provider check。
* 不读取真实 holdings 内容。
* 不读取 raw outputs。
* 不改现有 core pipeline。

`GET /api/provider-health` 只读：

```text
outputs/reports/provider_health_check.json
```

不存在时返回：

```json
{
  "overall_status": "not_run_yet",
  "summary": {},
  "checks": [],
  "next_action": "python scripts/run_provider_health_check.py --save"
}
```

后续 backlog：

```text
POST /api/provider-health/refresh
```

验收：

* `python scripts/run_app_backend.py` 能启动。
* 服务只监听 `127.0.0.1`。
* 端口冲突有清楚错误。
* API response 使用 Pydantic schema。
* 测试全部离线。
* pytest 全绿。
* 隐私扫描无命中。

### Phase 1：Read-only Local Web Shell

目标：

本地浏览器页面展示今日市场状态。

新增：

* React + Vite + TypeScript 前端。
* 三个路由占位：

  * 市场仪表盘
  * AI 对话
  * 账户概览

第一版 UI 只调用 Phase 0 API。

验收：

* 浏览器能打开本地页面。
* 能看到今日市场状态、风险等级、provider health、missing data。
* 前端 build 通过。
* 后端 API tests 继续通过。

不做：

* 不做 Tauri。
* 不做账户编辑。
* 不做 DeepSeek chat。
* 不做 Tavily。

### Phase 2：SQLite App State

目标：

建立 SQLite app state，但不切 holdings 真源。

新增：

* SQLite bootstrap / migration。
* app_settings
* refresh_runs
* chat_sessions
* chat_messages
* favorite_answers

验收：

* migration 幂等。
* API key 不落库。
* 设置和刷新记录可持久化。
* 隐私扫描通过。

不做：

* 不迁移 holdings 真源。
* 不保存普通聊天历史。
* 不做收益率分析。

### Phase 3：Chat MVP with DeepSeek

Legacy / superseded phase note: this phase is not a current short-term target
and does not authorize `/api/chat`, DeepSeek Chat productization, persistence,
frontend AI UI, or full-account external context. Current execution returns to
Stage DF data/modeling work.

目标：

实现 GPT 式自由聊天，不联网搜索。

新增：

* `POST /api/chat`
* `POST /api/favorites`
* DeepSeek chat service
* context assembler
* model tier toggle
* style toggle
* validator for investment analysis answers

默认：

* Flash
* full context
* natural explanation style
  -普通聊天不保存

验收：

* 能自由问答。
* 投资类回答可跑 validator。
* 成本详情可查看。
* 收藏回答保存结构化 context snapshot。
* mock DeepSeek 测试通过。

不做：

* 不做 Tavily。
* 不把 memo 混进聊天。
* 不保存所有聊天。

### Phase 4：Tavily Beta Search

Legacy / superseded phase note: this phase is not current and does not
authorize Tavily/search, `/api/search`, Chat UI, or search-derived product
integration. External AI and search productization remain frozen unless a
future task explicitly reopens them.

目标：

聊天可显式联网查询新闻/时事。

新增：

* Tavily adapter。
* 搜索 Beta 开关。
* `POST /api/search`
* `POST /api/chat` 增加 `search_enabled`

规则：

* 默认关闭。
* 只发送用户原问题。
* 不发送账户上下文。
* 搜索结果进入 DeepSeek prompt。
* 回答使用段落内脚注式引用。
* 搜索失败时基于本地 context 回答并说明失败。

验收：

* 能联网查询宏观新闻、公司/科技新闻、市场行情、机构观点、地缘政治。
* Tavily payload 测试确认不含账户上下文。
* 搜索失败降级测试通过。

不做：

* 不缓存普通搜索结果。
* 不把 search-derived 数据写入正式 dashboard 判断链。
* 不把搜索型估值当官方数据。

### Phase 5：Account Phase

目标：

SQLite 成为账户真源，账户页支持类别级编辑。

新增：

* holdings schema。
* `GET /api/account`
* `PUT /api/account`
* `POST /api/account/export-csv`

规则：

* DB 支持基金级。
* UI 暂时只编辑类别级 current_value + notes。
* 保存前显示改动摘要。
* 保存后导出 ignored CSV。
* 复用现有 pipeline 校验 CSV。

验收：

* 每周手动维护持仓可用。
* dashboard 组合偏离正确更新。
* stale > 7 days 提醒。
* 不需要收益率/成本分析。

不做：

* 不做版本历史。
* 不做回滚。
* 不做券商同步。
* 不做交易流水。
* 不编辑基金明细 UI。

### Phase 6：Formal Memo and Tauri

Legacy / superseded phase note: this phase is not current and does not
authorize Tauri, memo productization, frontend AI UI, persistence, or new API
endpoints. Current work remains Stage DF data/modeling integration.

目标：

接入正式 analyst memo 按钮；Web 稳定后再 Tauri 打包。

新增：

* `POST /api/analyst-memo`
* memo 独立展示。
* Tauri packaging。

验收：

* 普通聊天和正式 memo 边界清楚。
* memo dry-run / mock DeepSeek 测试通过。
* outputs 不提交。
* Tauri app 可打开本地服务或提示后端错误。

不做：

* 不做跨平台同步。
* 不做自动后台刷新。
* 不做登录锁。

## 10. 分支、提交与 push 规则

### 分支

APP 开发使用：

```text
app-mvp
```

main 分支保持稳定 CLI 主线。

### push 规则

main 分支：

* 永远由用户手动 push。

app-mvp 分支：

* Codex 可以在测试通过后询问用户再 push。
* 不允许无报告自动 push。
* 不允许在隐私扫描失败时 push。
* 不允许在 pytest 失败时 push。
* 不允许在涉及 `.env`、真实 holdings、data/private、outputs 时 push。
* 涉及 DeepSeek prompt、provider 生产逻辑、portfolio 计算、Git ignore、隐私路径时，必须用户确认。

### commit 规则

每个小阶段可以一个 commit。commit message 必须清楚表达改动，例如：

```text
Add FastAPI app backend skeleton
Add read-only dashboard API
Add SQLite app state foundation
```

## 11. 发布 / 阶段验收阻断条件

以下任一发生即阻断：

1. `.env` 被 Git 跟踪。
2. API key 出现在代码、日志、测试 fixture、API 响应。
3. 真实 holdings 被 Git 跟踪。
4. `data/private` 被 Git 跟踪。
5. outputs 真实内容被 Git 跟踪。
6. pytest 失败。
7. 隐私扫描命中。
8. FastAPI 绑定 `0.0.0.0`。
9. CORS 使用 `allow_origins=["*"]`。
10. API 返回完整 project root。
11. GET provider-health 触发 live 网络请求。
12. API tests 访问外部网络。
13. dashboard 把 proxy/search-derived 数据当 official。
14. 聊天或 memo 输出交易化指令。
15. 模型编造市场数据且 validator/人工审核未拦截。

## 12. Backlog

后置任务：

* `POST /api/provider-health/refresh`
* `POST /api/refresh/market`
* React/Vite UI
* SQLite app state
* DeepSeek chat service
* Tavily Beta search
* account editing
* formal memo UI
* Tauri packaging
* PE / forward PE / CAPE research
* PPI final demand research
* EIA oil research
* market breadth / equal-weight proxy research
* iPad 访问电脑服务
* local model fallback

暂不做：

* 自动交易
* 自动定投执行
* 证券账户同步
* 多用户
* 云同步
* 登录锁
* 自动后台刷新
* 全量聊天保存
* 实时行情终端

## 13. 第一轮任务最终定义

第一轮只做：

```text
Phase 0 - FastAPI Backend Skeleton
```

目标：

* 新建 `app-mvp` 分支。
* 建立 FastAPI 后端骨架。
* 提供只读 status/provider/dashboard API。
* 添加最小 API tests。
* 不做前端。
* 不做 SQLite。
* 不调用 DeepSeek。
* 不调用 Tavily。
* 不改现有核心 pipeline。
* 不触发外部网络请求。

第一轮完成后，项目应具备：

* 本地 API 进程可启动。
* 只读 API 可被前端未来调用。
* provider health 可读取已有 compact JSON。
* dashboard summary 可返回六大模块的 missing/available 状态。
* 测试离线可重复。
* 隐私边界可验证。
