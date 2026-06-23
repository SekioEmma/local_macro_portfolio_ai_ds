# Era 2 B4 Tavily Transport Closeout

## 结论

Era 2 TASK-B4 已完成 Tavily real transport 边界实现与 L4 安全回归。B4 只新增 transport，不新增 API route、前端 UI、自动调用、后台任务、RAG 或 Agent。

`/api/search/tavily` 仍未实现，归属后续 TASK-B7。B5 Realtime quote service、B6 Commodity quote、B7 API routes 均未完成。

## 已实现边界

- 唯一搜索 HTTP 文件：`src/app_backend/services/tavily_real_transport.py`
- 唯一搜索 secret 名称：`TAVILY_API_KEY`
- key 只从 process environment 读取；transport 不读取 `.env`、dotenv 或配置文件
- 构造与 import 不读取环境、不读取文件、不创建连接
- `send()` 是唯一 HTTP 出口
- 固定 canonical endpoint：`https://api.tavily.com/search`
- 默认 timeout 为 30 秒，禁止 redirect、retry、fallback 与 background work
- provider response 上限为 1 MiB，通过 streaming read 在接收过程中强制执行，不是 post-read validation；超限立即停止读取并分类为 `malformed`
- response 只映射 `url`、`title`、`content -> snippet`
- transport 不保存 query、raw response、raw HTML、API key，不写 SQLite、outputs、cache 或日志
- 返回 URL 仅保留 HTTP/HTTPS、拒绝 userinfo、执行 domain allowlist 二次校验，并移除 query string 与 fragment
- transport 失败只输出 `timeout`、`http_error`、`malformed`、`missing_key` 或 `provider_refusal` 分类，不保留自由文本 detail

## 责任分层

B3 仍负责：

- query sanitizer
- SearchRuntimePolicy
- domain policy
- budget gate
- 最终 response guard

B4 只负责：

- canonical Tavily HTTP request
- process environment 中的单点 key 加载
- HTTP 失败分类
- provider JSON 最小映射
- URL allowlist 二次校验

B4 transport 的存在不代表 API、UI 或自动搜索已开放。真实调用仍必须由后续明确批准的用户触发链路接入全部 B3 守门。

## L4 回归覆盖

- `httpx` 在 `src/app_backend/` 中只出现在 `tavily_real_transport.py`
- transport 不含 dotenv、文件读写、FastAPI、main、holdings、private、outputs 或 cache 依赖
- `main.py` 不含 `/api/search/tavily`、`/api/chat`、`/api/ai/tavily`
- endpoint SSRF 与非 canonical endpoint fail-closed
- redirect 禁用
- 1 MiB response size 上限
- raw response、secret、query 与 provider body 不进入错误或 response
- exact domain、child domain、evil suffix 与 userinfo URL 回归
- adapter 对全部 `TavilyTransportError` 安全降级为 `search_available=false`
- transport 过滤结果仍需经过 adapter 最终 response guard，不能重新进入最终响应

所有 HTTP 测试均使用 `httpx.MockTransport` 或本地 spy client；未发起真实 Tavily 请求。
