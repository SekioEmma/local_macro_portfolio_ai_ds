# Stage 9.3-A DeepSeek Adapter Design

完成时间：2026-06-15（commit on `app-mvp`，baseline `f2aae9a`）。

本文件描述 Stage 9.3-A DeepSeek 适配器骨架的设计、契约与边界。
Stage 9.3-A 只是骨架，**不**进行任何真实的外部模型调用，**不**读取任何 API key，
**不**读取 `.env`，**不**绑定任何 HTTP 端点。

---

## Stage 9.3-A 范围

* 引入内部 `ExternalAIAdapter` 基类（`src/app_backend/services/ai_external_adapter.py`）。
* 引入 `DeepSeekAdapter` 骨架与 `FakeDeepSeekAdapter`
  （`src/app_backend/services/deepseek_adapter.py`），默认 disabled，可选 fake 模式。
* 引入请求 / 响应 / 配置 Pydantic schema
  （`src/app_backend/schemas/ai_external.py`）。
* 引入 `guard_config` / `guard_request` / `guard_response` 校验函数与
  `BlockedAdapterError` 异常。
* 80 个 fail-closed 单元测试（adapter skeleton + guards）。
* 不修改任何 Stage 9.2 端点；不引入新端点；不导入网络客户端。

## Disabled-by-default 策略

`default_disabled_config()` 默认值：

| 字段 | 默认值 |
|------|--------|
| `provider` | `"deepseek"` |
| `enabled` | `False` |
| `mode` | `"disabled"` |
| `allow_network` | `False` |
| `requires_user_switch` | `True` |
| `requires_context_preview` | `True` |
| `requires_validator` | `True` |
| `save_raw_prompt` | `False` |
| `save_raw_response` | `False` |

* `mode="disabled"` 调用 `generate()` 时立刻抛 `BlockedAdapterError("adapter_disabled_in_stage_9_3_a")`。
* `mode="network"` 在 `guard_config` 阶段就被拒，不会进入 `generate()`。
* `allow_network=True` 在 `guard_config` 阶段拒绝。
* `save_raw_prompt=True` 或 `save_raw_response=True` 在 `guard_config` 阶段拒绝。

## Fake-client-only 行为

`FakeDeepSeekAdapter` 是 Stage 9.3-A 唯一可以真的执行 `generate()` 的子类。

* 它返回确定性本地文本 `"[fake-deepseek] Local fake adapter response. ..."`。
* `external_model_called=False`、`fake_response=True`、`not_saved_by_default=True`、
  `human_review_required=True` 始终硬编码。
* `privacy_summary` 始终：`uses_ai_context_manifest_only=True`、
  `external_model_called=False`、`search_called=False`、`saved_by_default=False`、
  `uses_holdings_line_items=False`、`uses_raw_provider_payloads=False`、
  `uses_raw_prompts=False`。
* 输出文本包含 boundary phrase（"not an action directive"），让 Stage 9.2 验证器在
  日后串联时不会误判 boundary 缺失。

## 无真实网络调用证明

`tests/test_deepseek_adapter_skeleton.py`：

* `test_deepseek_adapter_module_does_not_import_network_clients`：源码扫描
  `httpx` / `requests` / `aiohttp` / `urllib.request` / `socket.create_connection`，
  保证零引用。
* `test_ai_external_adapter_module_does_not_import_network_clients`：同上扫描
  `ai_external_adapter.py`。
* `test_no_network_modules_loaded_when_adapter_used`：monkeypatch
  `socket.create_connection` 让任何意外的网络访问直接 `AssertionError`，再执行
  `FakeDeepSeekAdapter().generate(...)`，证明 fake 路径不触网。
* `test_deepseek_module_does_not_read_env_or_external_llm_yaml` / 同名 external：
  源码扫描确认 `os.environ` / `os.getenv` / `.env` / `external_llm.yaml` / `open(`
  零引用。

## 请求契约

`ExternalAIRequest`（Pydantic）允许字段：

* `request_id`
* `provider`（`Literal["deepseek"]`）
* `mode`（`Literal["disabled","fake","network"]`，"network" 一律 fail-closed）
* `user_intent_summary`（sanitized 用户意图概要，**不是**原始问题）
* `context_preview_summary`
* `included_fact_count`
* `included_model_output_count`
* `excluded_context_summary`
* `boundary_notices: list[str]`（必须非空）
* `memo_type` / `preview_type`（可选）
* `validator_required: bool = True`（必须为 `True`）

`guard_request` 拒绝：

* 空 `context_preview_summary`
* 空 `boundary_notices`
* `validator_required != True`
* `mode == "network"`
* 任何在 raw dict 中出现的禁止字段名（`raw_prompt` / `raw_question` /
  `api_key` / `holdings` / `account_values` / `position_weights` /
  `transaction_history` / `raw_provider_payload` / `raw_manifest` /
  `env_value` / `file_path` / `local_path` / `search_results` 等）
* 任何字符串字段中出现 `FORBIDDEN_REQUEST_TOKENS` 之一
  （`api_key`、`bearer `、`sk_live_`、`sk_test_`、
   `holdings line items`、`account values`、`position weights`、
   `transaction history`、`raw provider payload`、`current_holdings.csv`、
   `data/private`、本地路径前缀、`.env`、`external_llm.yaml` 等）。

## 响应契约

`ExternalAIResponse` 必须字段：`provider`、`mode`、`external_model_called`、
`fake_response`、`content`、`validator_result`、`privacy_summary`、
`not_saved_by_default`、`human_review_required`。

Stage 9.3-A `guard_response` 拒绝：

* `external_model_called=True`（顶层或 privacy_summary 任一）
* `search_called=True`
* `saved_by_default=True`
* `uses_holdings_line_items=True`
* `uses_raw_provider_payloads=True`
* `uses_raw_prompts=True`
* `uses_ai_context_manifest_only != True`
* `not_saved_by_default != True`
* `human_review_required != True`
* `mode == "network"`
* `mode == "fake"` 且 `fake_response != True`

## 隐私边界

适配器层不接触：

* `data/holdings/`、`data/private/`、`.env`、`configs/external_llm.yaml`
* SQLite DB、`outputs/`、`cache/`、provider raw payloads、本地日志
* API key 值（甚至不读取 env 变量来判断是否存在）

只接受经过 AI Context Manifest sanitize 之后的概要文本。

## 验证器门控

* `guard_config`、`guard_request`、`guard_response` 都返回 `ExternalAIGuardResult(passed,
  findings)`，任何 finding 都触发 `BlockedAdapterError`。
* `DeepSeekAdapter.__init__` 调用 `guard_config`；
  `DeepSeekAdapter.generate()` 在 fake 模式下调用 `guard_request` 与 `guard_response`，
  保证最终返回的对象一定通过响应守卫。

## Stage 9.2 端点不受影响

* `ai_preview_service.py` / `ai_memo_renderer.py` / `ai_context_service.py` /
  `main.py` 都不 import `deepseek_adapter` / `DeepSeekAdapter` / `ai_external_adapter`。
* FastAPI 路由表无新增；`/api/chat` / `/api/search` / `/api/ai/deepseek` /
  `/api/ai/tavily` / `/api/ai/external` 仍然不存在。
* Stage 9.2 闭环测试 (`tests/test_stage9_2_security_closeout.py`) 全过。

## Stage 9.3-B 真实 DeepSeek 适配器前置条件

Stage 9.3-A 完成**不**等于授权 Stage 9.3-B。Stage 9.3-B 启动必须满足：

1. 用户在单独任务中**明确批准**，本次闭环不构成批准。
2. 默认禁用：必须保留 user-controlled 开关（环境变量 + 单次请求 opt-in）。
3. 不得在应用启动 / 页面加载时自动触发。
4. 发送前必须先展示 AI Context Manifest preview，让用户能看到将被发送的内容范围。
5. 收到响应后必须运行 Stage 9.2 同款验证器（forbidden terms + privacy findings）。
6. 默认**不**持久化 raw prompt / raw response；任何保存都必须用户显式触发。
7. 必须复用本文档中的 `ExternalAIRequest` / `ExternalAIResponse` 契约与
   `guard_*` 守卫，不得放宽；如需扩展只能加字段，不能改语义。
8. 任何 `holdings line items` / `account values` / `position weights` /
   `transaction history` / API key / `.env` 内容都不得出现在 prompt 或响应中。
9. 网络层错误必须 fail-closed（不要回填假数据，不要忽略错误）。

## 已知风险

* `FORBIDDEN_REQUEST_TOKENS` 是 substring 匹配，可能产生误报；当前 Stage 9.3-A
  范围内可接受，Stage 9.3-B 上线时可以再评估。
* `ExternalAIAdapterConfig.mode` 字面量包含 `"network"`，仅作为占位，所有
  guard 路径都拒绝它；Stage 9.3-B 启动时必须修改 guard 才能放行，这是有意为之的
  显式开关。
* `FakeDeepSeekAdapter` 返回的 boundary phrase 与 Stage 9.2 验证器一致，避免日后
  接入时验证器误判 boundary 缺失。

## Stage 9.3-B Readiness Seam（必须遵循的处理顺序）

完成于 2026-06-15；2026-06-15 同日由 Stage 9.3-B-0 把第 5 步细化为 `guard_external_ai_runtime_policy`。Stage 9.3-B 真实 DeepSeek 接入时**必须**按下列顺序串联，不得跳步：

1. **AI Context Manifest preview**：用户先看到将被发送的 manifest 摘要、
   included/excluded 计数与 boundary notices。Stage 9.2 `/api/ai/context-preview`
   是当前唯一合法 preview surface。
2. **用户确认 preview**：用户在 UI / 流程上明确确认本次将要发送的内容，
   并触发用户开关。
3. **`build_external_ai_request_from_manifest(manifest, ...)`**
   （`src/app_backend/services/ai_external_request_builder.py`）：
   把 sanitize 之后的 manifest 折叠成 `ExternalAIRequest`。该 builder：
   * 不接受任何 `question` / `prompt` 参数（签名层面被测试锁定）；
   * 默认 `mode="fake"`；`mode="network"` 在入口直接拒绝；
   * 内部已经调用 `guard_request`，调用方拿不到未审查的请求对象。
4. **`guard_request(request, raw_request=...)`**：再次 fail-closed 检查，
   嵌套字段名 / 嵌套字符串值都会被递归扫描（2026-06-15 加固）。
5. **`guard_external_ai_runtime_policy(policy)`**
   （`src/app_backend/services/ai_external_runtime_policy.py`）：
   Stage 9.3-B-0 新增的运行时批准门。policy 必须由调用方在请求范围内显式构造，
   且必须同时满足：
   * 所有 approval gates 为 True：`external_ai_enabled` / `provider_network_enabled` /
     `user_controlled_switch_enabled` / `single_request_user_approved` /
     `context_preview_confirmed` / `request_built_from_manifest` /
     `request_guard_passed` / `response_guard_required` /
     `stage9_validator_required` / `human_review_required`；
   * 所有 dangerous permissions 为 False：`save_raw_prompt` /
     `save_raw_response` / `persist_chat_by_default` / `allow_search` /
     `allow_tavily` / `allow_background_call` / `allow_app_start_call` /
     `allow_page_load_call` / `allow_holdings_line_items` /
     `allow_account_values` / `allow_position_weights` /
     `allow_transaction_history`。
   * 默认 `default_external_ai_runtime_policy()` 完全 fail-closed，
     `passed=False`，第一条 finding 是 `external_ai_disabled`。
6. **外部模型调用**：Stage 9.3-A 与 Stage 9.3-B-0 都不实现。Stage 9.3-B 启动前必须
   先获得显式批准；adapter 必须 disabled-by-default，必须有用户开关。
7. **`guard_response(response)`**：fail-closed 检查 `external_model_called` / 隐私
   flag / forbidden 输出语言 / 隐私 token / `validator_result.passed`。
8. **Stage 9.2 generated-output validator**
   （`ai_preview_service.validate_ai_preview_payload` 或等价物）：若 Stage 9.3-B 响应
   通过 preview 端点 surface 给用户，必须再过一遍 Stage 9.2 validator，确保
   forbidden term / privacy finding / boundary notice / human_review_required 与
   Stage 9.2 闭环一致。
9. **Human review**：`human_review_required=True` 必须始终保留。
10. **不默认持久化**：raw prompt / raw response 必须默认不存盘；任何保存必须由用户
    显式触发，且必须独立审计。

只要任意一步被绕过，本闭环就视为 broken，Stage 9.3-B 必须 fail-closed 拒绝继续。

## Stage 9.3-B Readiness Audit 结论

Status: completed 2026-06-15（commit on `app-mvp`）。

* Documentation drift fixed：`docs/current_project_state.md` 的 "current next step"
  从 "Stage 9.3-A closeout" 改为 "Stage 9.3-B readiness review"。
* Added `ai_external_request_builder.py`：manifest → `ExternalAIRequest` 唯一安全
  入口，已被测试证明不接受 `question` / `prompt` 参数，并且默认 fake 模式。
* Hardened `guard_request`：递归扫描 `raw_request` 嵌套 keys 与嵌套 string values，
  覆盖 list / dict / 任意嵌套深度。
* No new HTTP route added; no httpx/requests/aiohttp imported; no env / yaml
  / private file read.
* Stage 9.2 preview endpoints 仍然不 import builder 或 adapter，被新测试锁定。
* 全部 row count / manifest count 不变；validator boundaries 不变。
* Stage 9.3-B 仍然 blocked，等待显式批准。

## Stage 9.3-A Closeout / Guard Hardening

Status: completed 2026-06-15.

This closeout keeps Stage 9.3-A as a disabled-by-default, fake-client-only adapter contract. It does not implement Stage 9.3-B, does not call DeepSeek, does not read API keys or `.env`, and does not add HTTP routes.

Hardening changes:

* `ExternalAIAdapterConfig`, `ExternalAIRequest`, `ExternalAIPrivacySummary`, `ExternalAIResponse`, and `ExternalAIGuardResult` reject extra fields.
* `guard_response` blocks any response whose `validator_result.passed` is not true.
* `guard_response` blocks forbidden generated-output terms in `response.content`, mirroring the Stage 9.2 fail-closed policy for action, allocation, return-estimation, probability, guarantee, and directional phrasing.
* `guard_response` blocks privacy forbidden tokens in `response.content`, including API key markers, private path markers, holdings/account/position language, transaction history language, raw provider payload language, and external LLM config markers.
* `FakeDeepSeekAdapter` still passes the strengthened response guard.
* The default disabled adapter still blocks `generate()`.

Stage 9.3-B real DeepSeek adapter remains not implemented and not approved. A future Stage 9.3-B task must receive separate explicit approval before any real network adapter, API key handling, or external model call is introduced.

## Stage 9.3-B-0 Runtime Approval Gate / External AI Policy Contract

Status: completed 2026-06-15.

Stage 9.3-B-0 adds the runtime approval gate as code-level contract. It does
NOT implement a real DeepSeek adapter, does NOT call DeepSeek, does NOT add
HTTP routes, does NOT read API keys, and does NOT read `.env` /
`external_llm.yaml`.

New surface:

* `ExternalAIRuntimePolicy` Pydantic schema in
  `src/app_backend/schemas/ai_external.py` with `extra="forbid"`. Stores no
  API key, no env var name, no URL, no model endpoint, no raw prompt, no
  raw response.
* `default_external_ai_runtime_policy()` returns a fully fail-closed default.
* `src/app_backend/services/ai_external_runtime_policy.py` exposes
  `guard_external_ai_runtime_policy(policy) -> ExternalAIGuardResult` and
  `assert_external_ai_runtime_policy_allowed(policy) -> None` (raises
  `BlockedAdapterError` on failure).
* No network client, env read, or file open in the runtime policy module.

Gate behavior:

* Default policy fails closed with finding `external_ai_disabled`.
* Happy-path policy passes only when every approval gate is True AND every
  dangerous permission is False. Toggling any single gate breaks the pass.
* Search and Tavily are blocked by `allow_search=False` /
  `allow_tavily=False` regardless of other flags.
* Background, app-start, and page-load calls are blocked by
  `allow_background_call=False` / `allow_app_start_call=False` /
  `allow_page_load_call=False`.
* Holdings, account values, position weights, and transaction history
  exposure are blocked by their respective `allow_*` flags.

Isolation:

* `src/app_backend/main.py`,
  `src/app_backend/services/ai_preview_service.py`,
  `src/app_backend/services/ai_memo_renderer.py`,
  and `src/app_backend/services/ai_context_service.py` do not import the
  runtime policy module, the request builder, the DeepSeek adapter, or the
  fake adapter.
* No new HTTP routes; the forbidden-routes list is still empty.

Stage 9.3-B real DeepSeek adapter remains not implemented and requires
separate explicit user approval.
