# Phase E 收益区间引擎设计文档（E1 — L4 人审门控）

> **状态**：E1 设计文档已获用户批准（2026-06-25）。
> E2 数值实现因 HY OAS 数据不足被正式阻断，见 §5 阻断项。
> 本文档是 CLAUDE.md §Era 2 E-Phase 授权的唯一依据。

---

## 0. 核心定义（正式批准文本）

> **情景化收益区间 = 基于历史共同变动载荷的、相对于"无增量冲击基线"的条件性情景增量总回报影响分析。**

四个否定界：

| 否定界 | 说明 |
|---|---|
| 非收益预测 | 不输出 "预期收益 X%" 类绝对量 |
| 非概率胜率 | 不输出 "X% 概率上涨" |
| 非个股操作 | 不输出 ETF 以外的持仓操作建议 |
| 非动态择时 | 不自动触发，每次均为用户显式请求 |
| 非黑盒最优化 | 不运行 portfolio optimizer，不调整权重 |

---

## 1. 计算逻辑总览

```
历史因子数据 (3M 滚动窗口)
        │
        ▼
OLS 因子敏感度估计 (HAC/Newey-West SE)
        │
        ▼
情景冲击向量 (来自历史事件模板的联合冲击)
        │
        ▼
ETF USD 总回报增量影响
        │
        ▼
USDCNY FX 转换 (DEXCHUS 历史均值/分位数)
        │
        ▼
组合加权汇总 → mild_impact / central_impact / severe_impact
```

**严禁**：独立抽取各因子百分位数作为冲击向量（破坏联合共动结构）。

---

## 2. 因子层定义

### 2.1 OLS 回归因子（共 6 个）

| 编号 | 字段名 | 定义 | 数据源 | 状态 |
|---|---|---|---|---|
| F1 | `real_yield_10y` | 10Y 名义 UST 收益率 − 5Y5Y 远期通胀预期（FRED `T5YIFR`） | FRED `DGS10` − `T5YIFR` | 可用 |
| F2 | `credit_spread_hy` | HY OAS（ICE BofA 美国高收益指数利差） | FRED `BAMLH0A0HYM2` | **⛔ 阻断**（见 §5） |
| F3 | `growth_momentum_zscore` | ISM 制造业 PMI z-score（与 24M 均值/标准差标准化） | 本地 D 系列数据 | 可用 |
| F4 | `vix_level` | VIX 现货收盘 | 本地 D 系列数据 | 可用 |
| F5 | `ust_slope` | 10Y − 2Y UST 期限利差 | FRED `DGS10` − `DGS2` | 可用 |
| F6 | `commodity_trend` | 原油 3M 动量（Brent 收益率，按月） | 本地商品价格数据 | 可用 |

**关键语义澄清**：
- `growth_momentum_zscore`：ISM PMI 的标准化水平，反映**增长动能**，NOT "增长惊喜（growth surprise）"
- `credit_spread_hy`（F2）与 `vix_level`（F4）：在 OLS 中均为**共动载荷**，解释 ETF 历史对这两个因子如何共同波动。它们不是独立因果驱动器，不可单独施加极端冲击
- `real_yield_10y`（F1）在 `systemic` 情景下的冲击方向由历史事件模板决定（NOT 预设为正或负）

### 2.2 FX 转换层（独立于 OLS，不入回归）

| 参数 | 值 |
|---|---|
| 授权 | CLAUDE.md Phase E DEXCHUS exception（由用户 2026-06-25 正式批准） |
| 序列 | DEXCHUS（FRED H.10 外汇数据，CNY per USD，日频） |
| 用途 | Phase E 历史转换（`fx_conversion_series=DEXCHUS`，`fx_pair=USDCNY`，`purpose=historical_conversion_only`，`phase_e_only=True`） |
| 禁止 | 不得用于 `/api/quote/fx`；不得作为实时离岸 CNH 汇率；USDCNH 仍 unavailable |
| 冲击 | 情景冲击向量可包含 DEXCHS 的联合冲击分量（从事件模板读取），不独立抽取百分位 |

---

## 3. 回归方法

### 3.1 滚动 OLS 窗口

- **主窗口**：10 年滚动（约 120M 观测，需数据满足最小 84M）
- **辅助窗口**：5 年滚动（约 60M，用于近期体制稳定性参考）
- **观测频率**：月度（3M 交叠返回，monthly return overlap）
  - 每月末计算前 3 个自然月的 ETF 总回报
  - 因子取同期月均或月末值（规格在 E2 代码中固定）
- **重叠处理**：Newey-West HAC SE，最小 lag = 2（3M 窗口自然序列相关修正）

### 3.2 多重共线性检查

- 拟合时计算 VIF（方差膨胀因子）与条件数（标准化因子矩阵的条件数）
- VIF > 10 或条件数 > 30 时：标记 `collinearity_warning=True`；仍输出结果，但在情景影响报告中附加警告
- 不自动剔除因子（剔除须人工审查）

### 3.3 体制稳定性标志

- 比较主窗口（10Y）与辅助窗口（5Y）的 β 符号与数量级
- 若同一因子两窗口的 β 符号相反或数量级差异 > 2×：标记 `regime_shift_flag=True`

---

## 4. 情景族与冲击向量

### 4.1 四个情景族（固定）

| 情景族 | 描述 | 典型历史锚 |
|---|---|---|
| `stagflation` | 高通胀 + 增长软化 + 利率压力 | 1973-74、2022 年加息周期 |
| `risk_off` | 信用利差走阔 + VIX 飙升 + 避险收益率 | 2008 GFC、2018 Q4 调整 |
| `growth_scare` | 增长减速 + 降息预期走强 + 信用分化 | 2015-16、2019 年预防性降息 |
| `systemic` | 系统性冲击，参数由历史事件模板决定 | 2008 Sep、2020 Mar COVID |

### 4.2 冲击向量构造规则

**严禁方式**：对每个因子独立抽取历史百分位（如 credit_spread 95th pct + VIX 95th pct + real_yield 30th pct），因为这样的向量在历史上从未同时发生。

**唯一允许方式**：使用历史联合窗口（historical joint window）：

1. 选取特定历史事件区间（如 2022-01 至 2022-12）
2. 计算该区间内各因子的**联合实现变化量**（Δ factor）
3. 以此作为情景冲击向量
4. `mild_impact`：事件区间历史变化量的 50%
5. `central_impact`：事件区间历史变化量的 100%
6. `severe_impact`：事件区间历史变化量的 150%（线性外推）

**关于 `systemic` 情景**：
- `real_yield_10y` 的冲击方向由所选历史事件模板决定（2008 年 systemic 中，长债收益率下行；2022 年 systemic 中，长债收益率上行）
- 不预设方向；调用时必须传入 `event_template_id`

---

## 5. HY OAS 正式阻断项

**阻断编号**：`E2-BLOCKER-HY-OAS-001`

| 项目 | 内容 |
|---|---|
| 受影响序列 | `BAMLH0A0HYM2`（ICE BofA 美国高收益 OAS） |
| 本地数据情况 | 仅约 3 年历史（2023-06 至 2026-06） |
| FRED 说明 | 2026 年 4 月起 FRED 注明 3 年数据可用性 |
| 主窗口需求 | 10 年滚动需至少 84 个月 — **当前严重不足** |
| 5 年辅助窗口 | 同样不足（需 ≥60M，现有 <36M） |
| 禁止替代方案 | `BAA10Y`（Moody's BAA 利差）**不得**替代 HY OAS — 信用层级、流动性特征均不同 |
| 阻断效果 | **E2 不得输出实质性情景影响数值**，直至 HY OAS 满足 84M 最小历史 |
| 框架代码许可 | E2 可实现因子数据加载器、诊断工具、合约框架，但所有含 F2 的 live 输出必须返回 `status: "insufficient_history"` |
| 解锁条件 | 用户找到并导入满足 84M 历史的 HY OAS 替代数据，或等待到 2031-06；需用户显式批准后方可解锁 |

---

## 6. 组合影响计算

### 6.1 ETF 权重（固定，Phase E 期间不优化）

| ETF | 权重 | 资产类别 |
|---|---|---|
| SPY | 50% | 美国大盘股 |
| QQQ | 20% | 美国科技/成长股 |
| SHY | 20% | 美国短期国债 |
| GLD | 10% | 黄金 |

### 6.2 三步计算

**步骤 1：ETF USD 增量总回报影响**

```
Δ_return_usd(ETF_i) = Σ_j [ β_ij × Δ_factor_j(scenario) ]
```

其中 β_ij 为 ETF_i 对因子 j 的 OLS 回归系数（主窗口）。

**步骤 2：FX 转换（DEXCHS 联合冲击）**

```
Δ_return_cny(ETF_i) = (1 + Δ_return_usd(ETF_i)) × (1 + Δ_usdcny_pct(scenario)) − 1
```

其中 `Δ_usdcny_pct(scenario)` 来自情景联合冲击向量的 FX 分量（同一历史事件模板）。
若情景无 FX 分量：`Δ_usdcny_pct = 0`（不假设 CNY 变动）。

**步骤 3：组合加权**

```
portfolio_impact(scenario, severity) = Σ_i [ w_i × Δ_return_cny(ETF_i) ]
= 0.50 × SPY_cny + 0.20 × QQQ_cny + 0.20 × SHY_cny + 0.10 × GLD_cny
```

### 6.3 输出命名（强制）

| 字段 | 含义 |
|---|---|
| `mild_impact` | 事件区间历史变化量的 50% |
| `central_impact` | 事件区间历史变化量的 100% |
| `severe_impact` | 事件区间历史变化量的 150% |

**禁止**：不使用 `base_case`、`bull_case`、`bear_case`、`best_case`、`worst_case`。
**禁止**：不输出概率权重（"70% 概率为 central"）。

---

## 7. 输出 schema（草案，E2 用 Pydantic 正式定义）

```python
class ETFScenarioImpact(BaseModel):
    etf_ticker: str                         # "SPY" / "QQQ" / "SHY" / "GLD"
    mild_impact: float                      # 组合增量影响，CNY 计价，百分比形式（如 -0.032）
    central_impact: float
    severe_impact: float
    beta_window_months: int                 # 主回归窗口使用月数（实际有效）
    regime_shift_flag: bool
    collinearity_warning: bool

class PortfolioScenarioImpact(BaseModel):
    scenario_family: Literal["stagflation", "risk_off", "growth_scare", "systemic"]
    event_template_id: str                  # 如 "2022_rate_shock" / "2020_covid_mar"
    calculation_date: date
    portfolio_mild_impact: float
    portfolio_central_impact: float
    portfolio_severe_impact: float
    etf_impacts: list[ETFScenarioImpact]
    hy_oas_blocker_active: bool             # True 时全部 impact 字段为 None
    status: Literal["ok", "insufficient_history", "blocked", "error"]
    warnings: list[str]
```

---

## 8. Fail-Closed 守门矩阵

| 守门条件 | 失败行为 |
|---|---|
| `hy_oas_blocker_active = True` | 返回 `status="insufficient_history"`；所有 impact = None |
| 主窗口有效月数 < 84 | 同上 |
| `regime_shift_flag = True` | 仍输出数值，但附 `warnings` 列表 |
| `collinearity_warning = True` | 仍输出数值，但附 `warnings` 列表 |
| 因子数据缺口 > 10% | 返回 `status="blocked"`；不插值 |
| `event_template_id` 不在白名单 | 返回 `status="error"` |
| `scenario_family` 不在四个固定值 | Pydantic Literal 阻断，返回 validation error |
| DEXCHUS 历史无法对齐 | FX 分量设为 0，附 warning，仍输出结果 |

---

## 9. E 阶段任务分解

### E1 — 设计文档（本文档）
**状态**：✅ 已获用户批准  
**产物**：本文档（`docs/era2_return_band_design.md`）  
**需同步更新**：CLAUDE.md + GOVERNANCE.md（DEXCHUS 例外条款，见 §10）

### E2 — 因子数据层（数值实现）
**状态**：⛔ 正式阻断（`E2-BLOCKER-HY-OAS-001`）  
**允许做**：因子数据加载器框架、诊断脚本、HY OAS 历史长度检测、Pydantic 合约定义  
**禁止做**：任何含 F2 (`credit_spread_hy`) 的实质情景影响数值输出

子任务：
- E2-a：因子 loader（FRED + 本地 D 系列 → pandas DataFrame，月度对齐）
- E2-b：HY OAS 历史诊断脚本（`scripts/diagnose_hy_oas_history.py`），输出现有月数
- E2-c：OLS 估计器（`src/modeling/factor_sensitivity_estimator.py`，依赖注入，可注入测试数据）
- E2-d：HAC SE 计算（Newey-West，`statsmodels.stats.sandwich_covariance` 或手动实现）
- E2-e：VIF + 条件数检测（`src/modeling/collinearity_diagnostics.py`）
- E2-f：Pydantic 合约（`src/app_backend/schemas/scenario_impact.py`，见 §7）
- **E2-g：live output 守门**：所有公开方法在 `hy_oas_blocker_active=True` 时必须 fail-closed

### E3 — 情景校准与影响引擎
**状态**：🔒 待 E2 解锁  
**依赖**：`E2-BLOCKER-HY-OAS-001` 正式解除

子任务：
- E3-a：历史事件模板库（`data/scenario_templates/` YAML fixtures，包含联合因子变化向量）
- E3-b：`ScenarioCalibrationService`（模板加载、校验、向量提取）
- E3-c：`ScenarioImpactEngine`（三步计算，§6.2；注入 β、模板、FX 序列）
- E3-d：情景影响守门（§8 矩阵全部实现）

### E4 — API 路由 + 前端展示
**状态**：🔒 待 E3 完成  

子任务：
- E4-a：`POST /api/portfolio/scenario_impact_band`（Pydantic 验证，fail-closed，只读，无 trade/forecast/probability 字段）
- E4-b：`ScenarioImpactBandPage.tsx`（4 个情景族选择，3 级 severity 展示，blocker 状态提示）
- E4-c：前端 TypeScript 类型（与 §7 schema 对齐）
- E4-d：无自动刷新，每次须用户显式触发

---

## 10. 必须同步更新的治理文档

在 E2 编码开始前（即使 E2 框架仍受 blocker），必须更新：

### CLAUDE.md 新增条款

```
### Era 2 Phase E DEXCHUS exception

- `fx_conversion_series=DEXCHUS` (`fx_pair=USDCNY`, CNY per USD) is authorized
  for Phase E historical factor regression and scenario FX conversion only.
  (`purpose=historical_conversion_only`, `phase_e_only=True`)
- DEXCHUS must NOT be used in `/api/quote/fx`, real-time pricing,
  offshore CNH quoting, or any path outside `ScenarioImpactEngine`.
- USDCNH remains unavailable. `DEXCHUS`/USD-CNY proxies remain forbidden
  in all non-Phase-E contexts.
- This exception does not unlock any new network call; DEXCHUS data is read
  from existing local FRED history already present in the data foundation.
```

### GOVERNANCE.md 新增条款

收益区间引擎章节（Phase E §X）需写明：
1. "情景化收益区间"五个否定字段（非收益预测、非概率胜率、非个股操作、非动态择时、非黑盒最优化）
2. DEXCHUS 授权范围（同上）
3. HY OAS 阻断编号 `E2-BLOCKER-HY-OAS-001` 及解锁条件

---

## 11. 数据依赖汇总

| 序列 | 源 | 用途 | 当前状态 |
|---|---|---|---|
| `DGS10` | FRED | F1 名义利率分子 | ✅ 本地已有 |
| `T5YIFR` | FRED | F1 通胀预期分母 | ✅ 本地已有（或需 G1/G2 补入） |
| `DGS2` | FRED | F5 短端利率 | ✅ 本地已有 |
| `BAMLH0A0HYM2` | FRED | F2 HY OAS | ⛔ 仅约 3 年（2023-06+） |
| ISM PMI | 本地 D 系列 | F3 增长动能 | ✅ 需确认月度对齐 |
| VIX | 本地 D 系列 | F4 波动率 | ✅ 需确认月度对齐 |
| Brent crude | 本地商品数据 | F6 大宗商品动量 | ✅ 需确认月度对齐 |
| DEXCHUS | FRED H.10 | FX 转换层 | ✅ Phase E exception 已批准 |
| SPY/QQQ/SHY/GLD | 本地 market_history | 因变量月度回报 | ✅ 本地已有 |

---

## 12. 开发前置核查清单

进入 E2 代码前，人工确认：

- [ ] 本文档已推送到 `claude/test-performance-optimization-5n3l9d`
- [ ] CLAUDE.md Phase E DEXCHUS exception 已写入
- [ ] GOVERNANCE.md 收益区间否定字段 + DEXCHUS 授权 + 阻断编号已写入
- [ ] `T5YIFR` 本地历史确认可用（或用 `DFII10` 实际通胀债替代，需用户决策）
- [ ] ISM PMI 月度序列确认可用（D 系列具体字段名确认）
- [ ] `BAMLH0A0HYM2` 本地历史月数诊断脚本执行结果已记录
- [ ] 用户正式批准 E2 框架代码开始（HY OAS 阻断已知，框架可开始）

---

*本文档由 AI 起草，经用户 2026-06-25 批准（E1 节点）。E2 编码须用户明确指示后方可开始。*
