# Codex 任务：为前端新增 AI 研究聊天页面

## 目标

在现有 React 前端中新增一个 **AI 研究聊天页面**（`AIChatPage.tsx`），接入后端已有的 DeepSeek 单轮研究 API（`POST /api/ai/research-deepseek`），让用户能在 UI 中输入宏观研究问题并获取 AI 分析结果。

---

## 项目技术栈

- **前端**: React 18 + Vite 5 + TypeScript 5.5，纯 CSS（无 UI 框架），中文 paper-style 研究 UI
- **后端**: FastAPI，已运行在 `http://127.0.0.1:8000`
- **设计语言**: 仿学术论文/研究报告风格，暖色调纸张质感，中文界面
- **现有组件**: `ResearchUI.tsx` 中有 `PageHeader`, `StatusBadge`, `SourceBadge`, `MetaStrip`, `BoundaryNotice`, `LoadingState`, `ErrorState` 等可复用组件
- **图标**: `ResearchIcon.tsx` 支持: `dashboard`, `evidence`, `scenario`, `history`, `ai`, `portfolio`, `diagnostics`, `close`, `chevron`, `search`, `copy`, `check`, `shield`, `database`, `clock`, `layers`

---

## 需要修改/新增的文件

### 1. 新增 `app_frontend/src/components/AIChatPage.tsx`

**页面布局**：上下两栏布局（不是传统聊天气泡）

```
┌─────────────────────────────────────────────┐
│  PageHeader: "AI 宏观研究"                    │
│  副标题: "基于本地证据的 DeepSeek 单轮分析"     │
├─────────────────────────────────────────────┤
│  ┌─ 控制栏 ──────────────────────────────┐  │
│  │ [answer_mode 下拉] [detail_level 下拉] │  │
│  │ [问题输入框 .......................... ]│  │
│  │ [发送按钮]                             │  │
│  └───────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│  ┌─ 结果面板（无结果时显示引导文案）──────┐  │
│  │                                         │  │
│  │  状态栏: elapsed_seconds, model_provider│  │
│  │  finish_reason, output_blocked 状态     │  │
│  │                                         │  │
│  │  ┌─ 研究备忘 ────────────────────────┐ │  │
│  │  │ deepseek_memo_output（清洗后输出） │ │  │
│  │  │ Markdown 渲染，支持 ## 标题分节    │ │  │
│  │  └──────────────────────────────────┘ │  │
│  │                                         │  │
│  │  ┌─ 元数据折叠面板 ─────────────────┐ │  │
│  │  │ ▸ Claim 元数据                    │ │  │
│  │  │   claim_type_counts 表格          │ │  │
│  │  │   threshold_source_counts 表格    │ │  │
│  │  │ ▸ Prompt 上下文                   │ │  │
│  │  │   selected_card_count / budget     │ │  │
│  │  │   token 使用情况                   │ │  │
│  │  │ ▸ 验证结果                        │ │  │
│  │  │   semantic_validator 结果          │ │  │
│  │  │   input_validation 结果           │ │  │
│  │  │ ▸ 隐私与安全                      │ │  │
│  │  │   privacy_summary                 │ │  │
│  │  │   interpretation_boundary         │ │  │
│  │  └──────────────────────────────────┘ │  │
│  │                                         │  │
│  │  BoundaryNotice: interpretation_boundary │  │
│  └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**API 请求 schema**:
```typescript
// POST /api/ai/research-deepseek
type AIDeepSeekResearchRequest = {
  answer_mode: AIAnswerMode;       // "daily_brief" | "risk_review" | "scenario_review" | "portfolio_overlay" | "evidence_audit" | "research_memo"
  detail_level: AIDetailLevel;     // "brief" | "standard" | "deep"
  user_question: string;           // 2-500 字符，用户的宏观研究问题
};
```

**API 响应 schema**（需要在 types.ts 中新增）:
```typescript
type AIDeepSeekClaimMetadata = {
  claim_type_counts: Record<string, number>;   // e.g. {"direct_evidence": 5, "cross_evidence_inference": 3}
  threshold_source_counts: Record<string, number>; // e.g. {"project_band": 4, "historical_percentile": 2}
  total_claims: number;
};

type AIDeepSeekResearchResponse = {
  mode: "deepseek_single_turn";
  answer_mode: AIAnswerMode;
  detail_level: AIDetailLevel;
  user_question: string;
  deepseek_raw_output: string;          // 原始 DS 输出（含标签）
  deepseek_memo_output: string;         // 清洗后输出（标签已剥离），这是主要展示内容
  claim_metadata: AIDeepSeekClaimMetadata;
  finish_reason: string;                // "stop" | "length" 等
  selected_prompt_context: AISelectedPromptContext;
  prompt_budget: AIPromptBudgetSummary;
  prompt_text: string;                  // 完整 prompt（仅调试用，默认折叠）
  context_used_summary: {
    included_fact_count: number;
    excluded_fact_count: number;
    included_model_output_count: number;
    excluded_model_output_count: number;
  };
  privacy_summary: Record<string, boolean>;
  validator_result: {
    passed: boolean;
    blocked_terms: string[];
    privacy_findings: string[];
  };
  semantic_validator_result: AIResearchValidationResult;
  input_validation_passed: boolean;
  input_validation_findings: string[];
  output_blocked: boolean;
  human_review_required: boolean;        // 始终 true
  interpretation_boundary: string;
  elapsed_seconds: number | null;
  model_provider: string;                // "deepseek"
  not_saved_by_default: boolean;         // 始终 true
};
```

**功能需求**:

1. **answer_mode 选择器** — 复用 `LocalResearchPreviewPage` 中的 6 个模式选项（daily_brief, risk_review, scenario_review, portfolio_overlay, evidence_audit, research_memo），中文标签
2. **detail_level 选择器** — 三档：简要/标准/深度
3. **问题输入框** — `textarea`，placeholder "输入宏观研究问题..."，最大 500 字符，显示字符计数，支持 Ctrl+Enter 发送
4. **发送按钮** — 请求期间显示 loading spinner + "分析中..."文案 + 已用秒数计时器（每秒更新）
5. **结果主体** — `deepseek_memo_output` 字段作为主展示内容，用简单的 Markdown 渲染（`## ` 标题、`**` 加粗、`- ` 列表、换行）。不需要引入 markdown 库，用正则 + dangerouslySetInnerHTML 做简单渲染即可
6. **状态栏** — 显示 `model_provider`、`elapsed_seconds`（格式 "耗时 XX.Xs"）、`finish_reason`、如果 `output_blocked` 为 true 显示红色警告
7. **Claim 元数据面板**（可折叠）— 表格展示 `claim_metadata.claim_type_counts` 和 `threshold_source_counts`
8. **Prompt 上下文面板**（可折叠）— 显示 `prompt_budget` 中的 `selected_card_count`、`estimated_token_count` / `estimated_token_limit`、`ready` 状态
9. **验证结果面板**（可折叠）— 显示 `semantic_validator_result.passed`，如果有 findings 列出每条的 `severity` + `message_zh`
10. **隐私与安全面板**（可折叠）— 显示 `privacy_summary`、`interpretation_boundary`、`human_review_required` 标记
11. **复制按钮** — 一键复制 `deepseek_memo_output` 到剪贴板
12. **空状态** — 无结果时显示引导文案："选择分析模式，输入宏观研究问题，AI 将基于本地证据库进行单轮分析。"
13. **错误处理** — API 500 错误用 `ErrorState` 组件展示，网络错误友好提示
14. **请求超时** — fetch 设 180 秒超时（DS 调用可能需要 60-120 秒）

**样式要求**:

- 所有样式写在 `App.css` 中，CSS 类名前缀 `chat-`
- 遵循现有设计语言：`var(--panel-bg)`, `var(--panel-border)`, `var(--text-primary)` 等 CSS 变量
- 输入区域使用 `var(--panel-subtle-bg)` 背景
- 结果面板使用 `var(--panel-bg)` 背景 + `var(--panel-border)` 边框
- 发送按钮使用 `var(--paper-accent)` 作为主色
- 字体：正文 `var(--font-body)`，代码/数据 `var(--font-mono)`，标题 `var(--font-display)`
- 折叠面板用 `<details><summary>` 原生实现
- 响应式：在窄屏幕下控制栏的下拉和输入框堆叠为列布局

### 2. 修改 `app_frontend/src/api/client.ts`

新增一个 API 调用函数：

```typescript
export function fetchDeepSeekResearch(
  answerMode: AIAnswerMode,
  detailLevel: AIDetailLevel,
  userQuestion: string
): Promise<ApiResult<AIDeepSeekResearchResponse>> {
  return requestJson<AIDeepSeekResearchResponse>("/api/ai/research-deepseek", {
    method: "POST",
    body: {
      answer_mode: answerMode,
      detail_level: detailLevel,
      user_question: userQuestion
    }
  });
}
```

注意：这个请求可能需要 60-120 秒。需要把 `requestJson` 内部的 `fetch` 加一个 `AbortController` + 180 秒超时，或者新函数单独处理。如果修改 `requestJson` 影响其他调用的话，单独给这个函数写超时逻辑。

### 3. 修改 `app_frontend/src/types.ts`

添加 `AIDeepSeekClaimMetadata` 和 `AIDeepSeekResearchResponse` 类型定义（见上方 schema）。

### 4. 修改 `app_frontend/src/components/AppShell.tsx`

在 `AppViewKey` 联合类型中添加 `"ai-chat"`：

```typescript
export type AppViewKey =
  | "dashboard"
  | "evidence"
  | "scenario"
  | "historical"
  | "ai-context"
  | "ai-chat"      // ← 新增
  | "portfolio"
  | "diagnostics";
```

在 `navItems` 数组中添加新导航项，放在 `ai-context` 之后：

```typescript
{
  key: "ai-chat",
  label: "AI 研究聊天",
  shortLabel: "AI 聊天",
  icon: "ai"        // 复用 ai 图标
}
```

### 5. 修改 `app_frontend/src/App.tsx`

- Import `AIChatPage`
- 添加路由分支:

```tsx
{activeView === "ai-chat" && (
  <AIChatPage />
)}
```

`AIChatPage` 不需要从 App 传入 props，它自己发 API 请求。

---

## 关键约束

1. **不要新增 npm 依赖** — 用原生 HTML/CSS/JS 实现所有功能，不引入 markdown 库、不引入 UI 框架
2. **不要修改后端代码** — 后端 API 已完成，只做前端
3. **中文界面** — 所有文案用中文
4. **隐私安全** — `prompt_text` 字段只在折叠面板中显示（默认折叠），标注"调试信息，仅本地可见"
5. **`deepseek_raw_output` 不要展示** — 只展示 `deepseek_memo_output`（清洗后版本）
6. **TypeScript 严格模式** — 必须通过 `npx tsc --noEmit`
7. **human_review_required 始终为 true** — 在结果面板顶部固定显示一条提示："此分析仅供参考，需要人工复核"

---

## 设计参考

查看 `app_frontend/src/components/LocalResearchPreviewPage.tsx` 了解现有的 AI 研究预览页面设计。新聊天页面应保持视觉一致性，但功能上是不同的：
- `LocalResearchPreviewPage` = 本地确定性预览（无 LLM 调用）
- `AIChatPage` = 实际调用 DeepSeek 模型的单轮研究

查看 `app_frontend/src/App.css` 了解现有的 CSS 变量和设计体系。

---

## 验证标准

1. `cd app_frontend && npx tsc --noEmit` 通过
2. 页面能正常加载，侧边栏新增 "AI 研究聊天" 入口
3. 选择模式 + 输入问题 + 点发送 → 能看到 loading 状态 → 返回结果正确渲染
4. 折叠面板可以展开/收起
5. 复制按钮能把 memo 输出复制到剪贴板
6. 空状态、错误状态正确显示
7. 样式与现有页面视觉一致
