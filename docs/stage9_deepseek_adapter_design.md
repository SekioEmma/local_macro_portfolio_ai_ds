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

## Stage 9.3-B-1 Minimal Real DeepSeek Adapter Design + Config Contract

Status: completed 2026-06-15.

Stage 9.3-B-1 ships the **design contract** for a future real DeepSeek
adapter. It does NOT implement the network call, does NOT read API keys,
does NOT read `.env` / `external_llm.yaml`, does NOT add HTTP routes, and
does NOT touch any provider client library.

### New surface

* `DeepSeekProviderMessage` and `DeepSeekProviderPayload` Pydantic models
  in `src/app_backend/schemas/ai_external.py` with `extra="forbid"`.
  Provider message `role` is restricted to `"system"` / `"context"` /
  `"summary"` so the future adapter cannot package raw user-question
  transcripts as a `"user"` chat message.
* `src/app_backend/services/deepseek_provider_contract.py` exposes
  `build_deepseek_provider_payload(request: ExternalAIRequest) ->
  DeepSeekProviderPayload`. The builder runs `guard_request` first; any
  finding raises `BlockedAdapterError` and no payload is returned.
* The provider payload schema does NOT carry — and Pydantic
  `extra="forbid"` rejects — `api_key`, `api_key_env`, `base_url`,
  `endpoint`, `model`, `model_name`, `raw_question`, `raw_prompt`,
  `holdings_line_items`, `account_values`, `position_weights`,
  `transaction_history`, `raw_provider_payload`, `search_results`,
  `local_path`, `env_file_path`, and any other unlisted field.

### Minimal human workflow (Stage 9.3-B order)

1. User opens AI Context Manifest preview (`/api/ai/context-preview`).
2. User explicitly confirms this single send.
3. `build_external_ai_request_from_manifest(...)` builds an
   `ExternalAIRequest`.
4. `guard_request` passes.
5. `guard_external_ai_runtime_policy` passes (Stage 9.3-B-0).
6. `build_deepseek_provider_payload(request)` returns a sanitized
   `DeepSeekProviderPayload`.
7. **Stage 9.3-B-2** is the only later step that may wrap this payload
   in a real network call. Stage 9.3-B-2 must not modify or extend the
   payload schema with key/url/endpoint fields.
8. The response must pass `guard_response`.
9. The response must pass the Stage 9.2 generated-output validator
   (`ai_preview_service.validate_ai_preview_payload` or equivalent).
10. Human review is required.
11. Raw prompt / raw response are NOT saved by default; any save must be
    user-initiated and audited.

### Configuration plan (Stage 9.3-B-2; NOT implemented here)

Stage 9.3-B-1 does NOT read any configuration. The plan documented for
Stage 9.3-B-2 is:

* The API key may only be read from a single environment variable
  (suggested: `DEEPSEEK_API_KEY`), read by Stage 9.3-B-2 code only.
* `.env` files MUST NOT be auto-loaded. `configs/external_llm.yaml` MUST
  NOT be read.
* The key MUST NOT be read at application start, at page load, or in
  any background job. Read it only after `guard_external_ai_runtime_policy`
  returns `passed=True` and only immediately before the provider call.
* A missing or empty key MUST fail closed; the call must not proceed.
* The key MUST NOT be printed, returned in any HTTP response, written
  to any log, or persisted to disk.
* The model name and provider endpoint will be decided in
  Stage 9.3-B-2. They must not be added to the payload schema as
  user-controlled fields; the adapter is allowed to apply them
  internally when forming the actual HTTP request.

### Isolation

* `src/app_backend/main.py`, `ai_preview_service.py`,
  `ai_memo_renderer.py`, and `ai_context_service.py` do NOT import the
  provider contract module, the runtime policy module, the request
  builder, or the DeepSeek adapter.
* No new HTTP routes.
* 102 tests in `tests/test_deepseek_provider_contract.py` lock builder
  signature (no `question`/`prompt`/`api_key`/`endpoint`/`url`/`model`
  parameters), restricted message roles, guard fail-closed behavior,
  schema extra-field rejection, source-surface scan, Stage 9.2
  isolation, forbidden-routes absence, and route-table immutability on
  module import.

Stage 9.3-B-1 does not implement real DeepSeek network calls.
Stage 9.3-B-2 remains a separate task and requires explicit user
approval before work begins.

## Stage 9.3-B-2a Mocked Transport Adapter

Status: completed 2026-06-15.

Stage 9.3-B-2a wires the minimal adapter call chain through an injected
mocked transport only. It does not implement real HTTP, does not read an API
key, does not read environment variables, does not read `.env` or
`external_llm.yaml`, and does not add any endpoint.

New surface:

* `DeepSeekTransportRequest` and `DeepSeekTransportResponse` are sanitized
  schemas derived from `DeepSeekProviderPayload`. They do not carry API key,
  base URL, endpoint path, model name, raw prompt, raw response, holdings,
  account values, position weights, transaction history, search results, or
  local paths.
* `src/app_backend/services/deepseek_transport_contract.py` defines the
  `DeepSeekTransport` protocol, categorical `DeepSeekTransportError`, and
  deterministic `MockDeepSeekTransport` / `FakeDeepSeekTransport`.
* `DeepSeekNetworkAdapter` in
  `src/app_backend/services/deepseek_adapter.py` requires an injected
  transport and an explicit runtime policy. Its default config remains
  disabled and fail-closed.

Guard order for the mocked transport success path:

1. `guard_request(request)`.
2. `assert_external_ai_runtime_policy_allowed(policy)`.
3. `build_deepseek_provider_payload(request)`.
4. `build_transport_request_from_provider_payload(payload)`.
5. `transport.send(transport_request)`.
6. Construct `ExternalAIResponse`.
7. `guard_response(response)`.
8. Return response.

Fail-closed behavior:

* Default disabled adapter does not call transport.
* Missing transport fails closed.
* Runtime policy failure does not call transport.
* `guard_request` failure does not call transport.
* `mode="network"` request remains blocked by `guard_request`.
* Transport timeout-like, HTTP-error-like, malformed, and unexpected
  exceptions fail closed.
* Malformed transport response objects fail closed.
* Forbidden output terms and privacy tokens from mocked provider content are
  blocked by `guard_response`.

`guard_response` still blocks `external_model_called=True`, so Stage
9.3-B-2a intentionally returns `external_model_called=False` and
`fake_response=True`. The mocked transport represents a seam test, not a real
external provider call. Real `external_model_called=true` behavior and any
real API key/config/network transport remain a separate Stage 9.3-B-2b
decision review.

Stage 9.3-B-2a keeps a simulated `validator_result.passed=True` path for
contract compatibility. Stage 9.3-B-2b or 2c must connect the real
post-response validator such as `validate_ai_preview_payload` or an
equivalent validator before any real external response can be surfaced.

## Stage 9.3-B-2b Real Transport Contract

Status: completed 2026-06-15.

Stage 9.3-B-2b adds real DeepSeek transport code only. It does not add any
HTTP endpoint, does not connect a frontend chat UI, does not persist prompts
or responses, does not do Tavily/search, and does not trigger a live call on
app start, page load, background jobs, or tests.

New surface:

* `src/app_backend/services/deepseek_real_transport.py` implements
  `DeepSeekRealTransport`, which conforms to the existing
  `DeepSeekTransport` protocol.
* `load_deepseek_api_key_from_env() -> str` is the only function that reads
  `DEEPSEEK_API_KEY` from the process environment. It does not read local
  config files, and missing or blank keys raise
  `DeepSeekTransportError(kind="missing_key")`.
* `DeepSeekRealTransport.send(...)` accepts only
  `DeepSeekTransportRequest`, builds provider HTTP details internally, and
  returns only `DeepSeekTransportResponse`.
* API key, provider URL, and model name remain internal transport details and
  are not added to request or response schemas.

Error handling:

* Timeout-like failures become `DeepSeekTransportError(kind="timeout")`.
* Non-2xx provider status and connection failures become
  `DeepSeekTransportError(kind="http_error")`.
* Malformed JSON, missing choices, missing message, or missing content become
  `DeepSeekTransportError(kind="malformed")`.
* Provider refusal becomes `DeepSeekTransportError(kind="provider_refusal")`.
* Error details are categorical and sanitized. They do not include API keys,
  headers, raw provider payloads, raw prompts, holdings/account/position/
  transaction data, or local paths.

Isolation remains unchanged:

* Stage 9.2 files do not import the real transport, adapter, runtime policy,
  request builder, or provider payload builder.
* `guard_response` was not loosened. It still blocks
  `external_model_called=True`.
* The adapter still does not surface real external responses. Stage
  9.3-B-2c must review the `external_model_called` guard policy and wire the
  post-response validator before any real provider response can be shown to a
  user.

## Stage 9.3-B-2c External Response Guard + Validator

Status: completed 2026-06-15.

Stage 9.3-B-2c enables guarded external-response semantics only. It does not
add any API endpoint, frontend chat, persistence, Tavily/search, or automatic
external call.

Guard policy:

* `guard_response(response)` keeps its default Stage 9.3-A behavior and still
  blocks `external_model_called=True`.
* `guard_external_model_response(response)` is the explicit dedicated guard
  for real external responses.
* The explicit guard allows an external response only when all conditions hold:
  `external_model_called=True`, `fake_response=False`, `mode="network"`,
  `privacy_summary.external_model_called=True`,
  `uses_ai_context_manifest_only=True`, no holdings/account/position/
  transaction exposure, no raw provider payloads, no raw prompts,
  `search_called=False`, `saved_by_default=False`,
  `not_saved_by_default=True`, `human_review_required=True`, and
  `validator_result.passed=True`.
* Forbidden output terms and privacy tokens are still blocked.

Post-response validator:

* `validate_external_ai_response_content(content)` is the minimal Stage
  9.3-B-2c validator wrapper for external provider text. It scans for the
  same forbidden generated-output terms and privacy tokens that the response
  guard enforces.
* `DeepSeekNetworkAdapter.generate_external_response(...)` calls this
  validator before constructing the return path and then calls
  `guard_external_model_response(...)`.
* Validator failure prevents response return.

Isolation remains unchanged: Stage 9.2 endpoint files do not import the
adapter, real transport, runtime policy, provider builder, or new external
guard path. A later Stage 9.3-B-2d or security closeout must review any
manual one-shot invocation workflow before real responses are surfaced.

## Stage 9.3-B Security Closeout

Status: completed 2026-06-15.

The Stage 9.3-B closeout verifies the full external-AI seam from the disabled
adapter skeleton through external-response guard semantics. It adds no new
endpoint, frontend UI, persistence, Tavily/search, agent behavior, live test,
or automatic external call.

Verified boundaries:

* Route surface remains unchanged; no `/api/chat`, `/api/search`,
  `/api/ai/deepseek`, `/api/ai/external`, `/api/ai/tavily`, provider-payload,
  runtime-policy, send, complete, or generate route exists.
* Stage 9.2 preview files do not import DeepSeek adapter, real transport,
  runtime policy, provider builder, transport request builder, external guard,
  or key loader.
* Secret handling remains isolated to
  `load_deepseek_api_key_from_env()` in `deepseek_real_transport.py`; no `.env`
  or YAML loading is introduced.
* Manifest-only request, provider payload, and transport request contracts
  still exclude raw question, raw prompt, API key, URL, endpoint, model, raw
  response, holdings, account, position, transaction, search, and local paths.
* `guard_response` still defaults to fail-closed for
  `external_model_called=True`; only `guard_external_model_response` can allow a
  compliant external response.
* `generate_external_response(...)` requires request guard, runtime policy,
  provider payload builder, transport success, post-response validator, and
  explicit external-response guard before returning.

The dedicated closeout document is
`docs/stage9_3b_security_closeout.md`.
