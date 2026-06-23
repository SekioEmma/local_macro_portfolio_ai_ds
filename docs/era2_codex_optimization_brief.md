# Codex 优化任务简报 — 工程化基建 / 门面瘦身 / 小清理

> 你是 Codex,在仓库 `local_macro_portfolio_ai_ds` 上工作。本简报自包含,完成下面三个任务。
> 任务 1(AI-2 DeepSeek 运行时策略治理)已由另一会话完成并合入分支 `claude/claude-md-review-f07zq9`,**不要重做**。

## 0. 必读约束(违反即视为失败)

1. **严格遵守 `CLAUDE.md` 的 Security Constraints**。尤其:
   - 不读/改/提交 `.env`、`configs/external_llm.yaml`、`*.sqlite*`、`data/holdings/`、`data/private/`、`outputs/`、`cache/`、`dist/`、`node_modules/`。
   - 不新增 `os.environ`/`os.getenv` 读取(已批准的 DeepSeek key 读取除外,且不要碰它)。
   - 不在已批准传输边界外 import `httpx`/`requests`/`aiohttp`;不新增真实网络调用。
   - 不改 D10–D19 / Stage 8 的金融语义;不放宽 AI Context Manifest 资格;不削弱任何 `guard_*`。
2. **行为等价优先**:除非任务明确要求,所有重构必须保持运行时行为与公开 API 不变。
3. **每个任务独立提交**,commit message 清晰说明动机与范围。
4. 提交分支沿用 `claude/claude-md-review-f07zq9`(或按维护者指示新建);**不要开 PR,除非维护者明确要求**。

## 1. 环境与测试运行方式(重要,避免踩坑)

```bash
# 安装依赖(fresh clone 默认未装)
pip install -r requirements.txt -r requirements-dev.txt
# 前端
cd app_frontend && npm install

# 跑测试:必须在【仓库根目录】运行,不能在 src/ 下运行。
# 部分契约测试用相对路径读取 src/app_backend/...,在 src/ 下会 FileNotFoundError。
python -m pytest tests/ -q          # pytest.ini 已配置 pythonpath=src,scripts

# 前端类型检查
cd app_frontend && npx tsc --noEmit
```

**已知基线失败**:fresh clone 缺 `outputs/reports/` 数据,
`tests/contracts/test_golden_output_contract.py::test_golden_audit_contract` 会失败
(`included_d15_model_output_count == 0`)。这是**数据缺失导致的环境性失败,与代码无关**,
已在任务 1 提交前用 `git stash` 验证为基线既有。处理见任务 A。

---

## 任务 A(优先级:中)— 最小工程化基建

**动机**:仓库有 1500+ 测试但没有任何 CI 强制执行;没有 lint/格式化/类型检查统一标准;
运行时依赖未锁版本,可复现性差。

### A1. 锁定运行时依赖版本
`requirements.txt` 当前 `pyyaml`、`yfinance`、`requests`、`python-dotenv` 无版本约束。
为这四个加上合理的版本下限/范围(参照 fastapi/uvicorn 已有的 `>=x,<y` 风格),
选用与当前已安装并通过测试的版本兼容的约束。不要升级到会破坏测试的大版本。

### A2. 引入 ruff(lint + 格式检查,不强制自动改写既有代码)
- 新增 `pyproject.toml`(仅放工具配置,不引入打包元数据除非必要)或 `ruff.toml`。
- 配置一个**务实、低噪音**的规则集(如 `E`,`F`,`I`;`line-length` 取一个不会让现有代码大面积报红的值,
  先实测 `ruff check src tests` 的报错量再定)。
- 目标:`ruff check` 在现有代码上**干净通过**。若个别历史问题难修,用 `per-file-ignores` 或最小修复,
  **不要为了过 lint 而改动金融语义或 guard 逻辑**。
- 不要运行 `ruff format` 对全仓库重排版(会产生巨大无关 diff);格式化留作后续。

### A3. 最小 CI(GitHub Actions)
新增 `.github/workflows/ci.yml`,在 push / PR 时:
1. setup Python 3.11;`pip install -r requirements.txt -r requirements-dev.txt`
2. `ruff check src tests`
3. `python -m pytest tests/ -q`(在仓库根目录运行)
4. setup Node;`cd app_frontend && npm ci && npx tsc --noEmit`

**关键**:CI 必须能绿。先解决任务 A 开头提到的 `test_golden_audit_contract` 数据依赖问题:
- 首选:排查它依赖哪些 `outputs/` 数据,若有可提交的最小 golden fixture 就提交并让测试读 fixture;
- 否则:给该测试加 `@pytest.mark.skipif`(检测数据缺失时跳过),并在 PR/commit 说明原因。
- **不要**简单删除断言或弱化测试。

### A4(可选,若时间允许)前端 lint
前端目前只有 `tsc`,无 eslint。可加最小 eslint(react + ts 推荐集)和 `npm run lint` 脚本,
并接入 CI。若引入噪音过大则跳过,不要硬塞。

**验收**:`ruff check src tests` 干净;`python -m pytest tests/ -q` 全绿(含对 golden 测试的处理);
`tsc --noEmit` 通过;CI workflow 文件存在且步骤正确。

---

## 任务 B(优先级:中,风险较高 — 谨慎)— 瘦身 `dashboard_service.py` 转发门面

**现状**(`src/app_backend/services/dashboard_service.py`):
- 文件约 870 行,其中前 ~199 行是带别名的转发 import(137 行 import),
  随后是 33 个私有函数,**绝大多数是纯转发包装**,仅为把模块级常量
  (如 `DEFAULT_MARKET_HISTORY_DB_PATH`、`METRIC_ALIASES`、`DERIVED_METRIC_KEYS`)绑进已抽出的子模块。
- 真正的公开 API 只有 2 个:`build_dashboard_summary`、`build_dashboard_evidence_table`。
- **约束焊死**:`tests/` 中约 79 处引用 `dashboard_service._私有名`,
  且 `tests/dashboard/test_dashboard_metric_builder_characterization.py` 用
  `assert dashboard_service._format_value is dashboard_metric_builder.format_value` 这类**身份相等**断言
  把门面与子模块焊在一起。

**这件事风险高,采用保守、分步、可回退的做法:**

1. **先调研,后动手**:统计所有 `dashboard_service._x` 的引用点(测试+源码),
   分类哪些是「纯别名转发」(身份相等)、哪些是「绑定常量的包装」(非身份相等)。
2. **不要一次性删光门面**。建议路径:
   - 对**纯别名**(身份相等的)转发:让测试与调用方直接 import 子模块,逐步移除门面里的别名再导出。
   - 对**绑定常量的包装函数**:把默认参数下沉到子模块(子模块函数提供默认值),
     或保留一层极薄包装但集中管理常量;优先减少重复样板。
3. **characterization 测试**:它们的存在目的是「锁定抽取前后行为一致」。抽取早已完成,
   这些身份断言现在主要是阻碍。可将其**改写为行为断言**(断言输出相等而非对象 `is` 相等),
   或在确认安全后删除并由子模块自身的单测覆盖。每一步都要让 `tests/dashboard/` 全绿。
4. **行为必须等价**:`build_dashboard_summary` / `build_dashboard_evidence_table` 的输出在重构前后
   对相同输入必须完全一致。建议先跑一遍 `tests/dashboard/ tests/contracts/` 作为基线再开工。

**验收**:`dashboard_service.py` 的转发样板显著减少(import 行数与纯转发函数数量明显下降);
公开 API 不变;`python -m pytest tests/dashboard/ tests/contracts/ -q` 全绿;
characterization 测试改为行为断言或被等价覆盖。
**若评估后认为收益不抵风险,可在 commit/PR 里写明理由,只做低风险的一部分(如仅删纯别名),不要勉强。**

---

## 任务 C(优先级:低)— 小清理

各自独立小提交即可。

### C1. 修端口漂移
- `CLAUDE.md` Quick Start 后端用 `--port 8000`;
- `app_frontend/src/api/client.ts:22` 默认 `http://127.0.0.1:8765`;
- `src/app_backend/main.py` CORS 允许前端源 `5173`(这条正确,是前端 dev server 端口)。
后端默认端口与前端默认连接端口不一致,按文档起服务时前端连不上(除非设 `VITE_API_BASE_URL`)。
**统一后端端口**(选 8000 或 8765 其一),让 `CLAUDE.md`、`client.ts` 默认值一致;
如有 `.env.example` / vite 配置也一并对齐。不要改 CORS 里的 5173。

### C2. `build_dashboard_summary` 缺 build_lock(可选,谨慎)
`src/app_backend/services/dashboard_service.py`:
- `build_dashboard_evidence_table`(约 line 359)用 `_SHARED_DASHBOARD_CONTEXT_CACHE.build_lock` 做双重检查锁防惊群;
- 但 `build_dashboard_summary`(约 line 206)**没用**该锁,并发时会各自重建。
可让 summary 路径也走相同的双重检查锁模式以保持一致。**注意死锁**:
evidence-table 在持锁期间会调用 `build_dashboard_summary`,二者用的是同一把 `RLock`(可重入,通常安全),
但务必跑并发/现有缓存测试确认无回归。**若不确定,跳过此项并在 PR 说明。**

### C3. 去掉 `build_dashboard_summary` 里的重复计算
同函数内 `_shared_cache_bypass_reason(...)` 用相同参数被算了两次(约 line 223 与 line 254),
写缓存前还多调一次 `.get()`(约 line 261,触发一次 Pydantic 深拷贝)仅为判断存在性。
可计算一次复用、避免多余深拷贝。保持行为等价。

**验收**:`python -m pytest tests/dashboard/ tests/contracts/ -q` 全绿;C1 三处端口一致。

---

## 总验收清单

- [ ] A:依赖锁版本 / ruff 干净 / CI workflow 可绿 / golden 测试数据依赖已妥善处理
- [ ] B:门面样板显著减少且行为等价,dashboard+contracts 测试全绿(或写明只做了低风险子集)
- [ ] C:端口统一;(可选)summary 锁一致;去重复计算;测试全绿
- [ ] 全程未触碰 CLAUDE.md 禁区,未改金融语义,未弱化 guard
- [ ] 每项独立提交,message 清晰
