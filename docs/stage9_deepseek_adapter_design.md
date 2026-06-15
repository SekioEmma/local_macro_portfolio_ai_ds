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
