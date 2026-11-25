# ARCHITECTURE.md · 技术架构

> 你说的 `agriculture.md` 我按 `ARCHITECTURE.md`（架构）理解了，文件按这个建。如果你要的其实是别的，说一声我改。

## v2 变更（2026-11-25）

第一版把"项目"当成了一个笼统的对象，用一张卡展示全部信息。实际业务里这两件事都不成立：**一笔订单下有三四个型号，每个型号的进度是独立的**；而十个项目同时铺开时，卡片形态一屏只能放两个。

v2 改了三处，其余不变：

| 改动 | 说明 |
|---|---|
| 项目 = 型号 | 一行一个型号。订单只做归组，不参与推进；轮次记同一型号内部的反复（PI v2、定型书第 3 版） |
| 两级布局 | 列表（一行四样信息，一屏十个）+ 右侧抽屉（线程、倒推链）。泳道视图独立，占满整宽 |
| 三层时间 | 硬节点（日历格子）、推导节点（闸门倒推）、软任务（无截止，单独一栏按挂了几天排序） |
| 阶段表 | 换成 9 段真实流程：报价 → 立项 → 开发 → HR过号 → 滚动计划 → 生产 → 抽检 → 发运 → 在售 |

新增字段存在 `projects.payload_json` 里（`threads` / `log` / 日期字段），不再逐个改表结构；列式字段只有 `model` / `order_id` / `round` 三个。

导入链路见 `MD_IMPORT.md`：公司 AI 导出 MD → 本地切块抽取 → 人工核对原文依据 → 合并入项目。解析器在 `assets/md-import.js`，纯前端，离线模式同样可用。

## 0. 核心约束（先看这个）

| 约束 | 后果 |
|---|---|
| 明天要在**公司 Windows 电脑**上跑 | 不能假设有 Python / Node；不能要求管理员权限；不能依赖联网装包 |
| 只一个人用 | 不做鉴权体系，只做本机回环 + 来源校验 |
| 数据含真实客户名与交期 | 一律不出本机；任何外发必须显式开关且默认关闭 |
| 现有前端形态已确认 | 不改视觉、不改交互，只换数据来源 |

**因此架构的第一原则：后端是增强，不是前提。** 前端在两种模式下都能完整工作。

---

## 1. 运行模式（双轨）

同一份 `index.html`，启动时探测环境，自动选择数据层：

```
                    ┌─────────────────────────────┐
                    │   index.html（唯一前端）      │
                    │   assets/store.js 数据层抽象  │
                    └──────────┬──────────────────┘
                               │ 启动时 GET /api/health
                 ┌─────────────┴─────────────┐
        200 OK   │                           │  失败 / 超时 / file://
                 ▼                           ▼
    ┌────────────────────────┐   ┌────────────────────────┐
    │  A. 后端模式（推荐）      │   │  B. 离线模式（保底）      │
    │  http://127.0.0.1:8787 │   │  双击 index.html 打开     │
    │  SQLite 落盘，永不丢      │   │  localStorage           │
    │  支持解析、导出、备份      │   │  纯前端，零依赖           │
    └────────────────────────┘   └────────────────────────┘
```

两者共用**同一套数据结构**与**同一个渲染代码**。切换只影响 `store.js` 里的三个方法：

```js
store.load()                       // 读全量数据
store.saveProject(project)         // 写项目
store.parse(text)                  // 自然语言 → 字段
```

- A 模式三者都走 HTTP
- B 模式 `load/saveProject` 走 localStorage，`parse` 调用内置的本地规则引擎（同一份算法，JS 端口）

**B 模式的数据逃生通道**：顶部常驻「导出备份」按钮，导出 JSON 文件；A 模式提供「导入」把 JSON 灌进 SQLite。这样即使明天先在离线模式录了一天，晚上带回自己的机器也能一条不丢地迁过去。

> 为什么值得这么做：Windows 电脑是否有 Python 是未知数。如果架构依赖"必须先装 Python"，明天就有极大概率卡在环境上，而这是唯一无法在今晚预先验证的风险。

---

## 2. 技术选型

| 层 | 选择 | 理由 | 被否掉的方案 |
|---|---|---|---|
| 前端 | 原 `index.html` + 普通 `<script src>` | 视觉已定稿；普通 script 在 `file://` 下可加载，`type=module` 会因 CORS 失败 | 拆成 Vite/React：需要构建步骤，双击打不开，明天风险高 |
| 后端 | FastAPI + uvicorn | 上级项目已验证可跑；机器上 anaconda 已自带 | Flask（同样要装）；纯 `http.server`（路由/校验全手写，易出 bug 且难维护） |
| 存储 | SQLite 单文件 | 零服务、事务可靠、整文件可拷贝备份、可用 DB Browser 直接看 | JSON 文件（并发写易损坏）；Postgres（要装服务） |
| 解析 | 本地规则引擎（主）+ LLM（预留） | 见 §5 | 直接调 LLM：客户名出网，触红线 |
| 部署 | `127.0.0.1` 本地回环 | 单用户，无需暴露端口 | 局域网开放（无鉴权，等于裸奔） |

**依赖清单（仅 3 个）**：`fastapi`、`uvicorn`、`pydantic`。不引入 ORM、不引入 Alembic、不引入 reqwest 类客户端。

---

## 3. 目录结构

```
business-dashboard/
├── index.html                  # 前端（视觉不动，只改数据层调用）
├── assets/
│   ├── store.js                # 数据层抽象：双模式切换的唯一入口
│   └── local-parse.js          # 本地解析引擎的浏览器版本（B 模式用）
├── app/                        # 后端
│   ├── main.py                 # FastAPI 实例、静态托管、Host/Origin 守卫
│   ├── settings.py             # 数据目录、日志路径（跨平台）
│   ├── db.py                   # 连接、schema、版本化迁移
│   ├── schemas.py              # 请求模型（pydantic）
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── data.py             # CRUD：customers / phases / projects / milestones
│   │   ├── parse.py            # 解析接口
│   │   └── system.py           # health / export / import / backup
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── contract.py         # ParseResult 数据契约（前后端共用定义）
│   │   ├── local_rules.py      # 本地规则引擎（Python 版）
│   │   └── llm.py              # 预留，P2 才实现
│   └── providers/              # 从上级项目移植的 provider 范式
│       ├── transport.py        # urllib，零依赖
│       ├── client.py           # 分发 + 错误归一 + 凭据脱敏
│       ├── openai.py
│       └── anthropic.py
├── scripts/
│   ├── start.command           # macOS 双击启动
│   ├── start.bat               # Windows 双击启动
│   ├── check_env.py            # 环境自检（明天第一步跑这个）
│   └── smoke.py                # 冒烟测试
├── data/                       # SQLite（不进 git）
├── PRODUCT.md  ARCHITECTURE.md  ROADMAP.md  AGENTS.md  DECISIONS.md  README.md
```

后端运行时数据**不放在项目目录**，避免 git 误提交与同步工具冲突：

| 平台 | 数据目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\BusinessDashboard\` |
| macOS | `~/Library/Application Support/BusinessDashboard/` |

可用环境变量 `BIZBOARD_DATA_DIR` 覆盖（测试与便携模式用）。

---

## 4. 数据模型

### 4.1 设计原则

**内部规范化，出口贴合前端。** 数据库用外键保证一致性；API 输出刻意保持前端现有的 JSON 形状（`phase` 是名称字符串、`done` 是名称数组）。这样前端 `renderBoard()` 一行都不用改。

> 这是本次改造最重要的取舍。规整的 API 设计当然更"正确"，但会让前端 750 行渲染代码全部重写，明天之前完成不了，且必然引入新的 bug。

### 4.2 表结构

```sql
-- 客户
CREATE TABLE customers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  alias TEXT NOT NULL DEFAULT '',      -- 别名/简称，逗号分隔，供解析反查
  contact TEXT NOT NULL DEFAULT '',
  channel TEXT NOT NULL DEFAULT '',
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 阶段（全局定义，顺序即 ordinal）
CREATE TABLE phases (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  color TEXT NOT NULL,
  ordinal INTEGER NOT NULL
);

-- 项目
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  customer_id TEXT REFERENCES customers(id) ON DELETE SET NULL,
  phase_id TEXT REFERENCES phases(id) ON DELETE SET NULL,
  start_date TEXT,
  end_date TEXT,
  color TEXT NOT NULL,
  contact TEXT NOT NULL DEFAULT '',
  dept TEXT NOT NULL DEFAULT '',
  dept_type TEXT NOT NULL DEFAULT '',           -- 内部 / 外部 / ''
  contact_way TEXT NOT NULL DEFAULT '',
  means TEXT NOT NULL DEFAULT '',               -- 信息获取手段
  channel TEXT NOT NULL DEFAULT '',             -- 来源渠道
  note TEXT NOT NULL DEFAULT '',                -- 卡点 / 进展
  next_action TEXT NOT NULL DEFAULT '',
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_projects_customer ON projects(customer_id);

-- 已走过阶段（前端 done[]，用名称对齐前端，删阶段时按名称清理）
CREATE TABLE done_phases (
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase_name TEXT NOT NULL,
  PRIMARY KEY (project_id, phase_name)
);

-- 关键时间点
CREATE TABLE milestones (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_milestones_project ON milestones(project_id);
CREATE INDEX idx_milestones_date ON milestones(date);

-- 待确认字段（前端 unsure[]）
CREATE TABLE field_flags (
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  field TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (project_id, field)
);

-- 录入原文 + 解析快照（溯源核心，只增不改）
CREATE TABLE captures (
  id TEXT PRIMARY KEY,
  raw_text TEXT NOT NULL,
  project_id TEXT,                      -- 落到哪个项目，未归属时为 NULL
  parser TEXT NOT NULL,                 -- local / manual / llm:openai:gpt-4o
  parsed_json TEXT NOT NULL,            -- 完整 ParseResult（含 confidence/evidence）
  applied_fields TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_captures_project ON captures(project_id, created_at);

-- 变更审计
CREATE TABLE change_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity TEXT NOT NULL,                 -- project / customer / phase / milestone
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,                 -- create / update / delete
  before_json TEXT,
  after_json TEXT,
  at TEXT NOT NULL
);

-- 键值设置
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- schema 版本，用于迁移
CREATE TABLE schema_meta (version INTEGER NOT NULL);
```

**为什么保留 `captures`：** 这个工具的价值不在"存了字段"，而在"字段有出处"。三个月后看到某个项目写着"模具要改"，能点开看到是哪天、谁说的、原话是什么。这也是管培生轮岗场景最需要的东西——你采集到的信息要能证明来源。

### 4.3 迁移策略

- 启动时 `initialize_database()`：`CREATE TABLE IF NOT EXISTS` + 按 `schema_meta.version` 递增执行迁移脚本
- 每次迁移前自动 `VACUUM INTO` 备份一份 `dashboard.sqlite3.bak.{version}`
- 只增列不删列，旧库永远能打开

---

## 5. 解析管线（核心难点）

### 5.1 现状问题

现有 `demoParse()` 是十几条正则叠加，问题很具体：

| 问题 | 例子 |
|---|---|
| 日期不通用 | 只认 `11/10` 和 `11月10日`，不认 `11.10`、`下周三`、`月底`、`12月初` |
| 无年份推断 | `12/5` 一律按今年，跨年就错 |
| 阶段靠子串 | `text.includes(阶段名)`，"报价中"会误命中"报价中心" |
| 客户靠全串 | 只认完整客户名，`Kalom`、`卡隆` 对不上 |
| 无出处 | 抽出来但说不清从哪句来的，用户无法判断该不该信 |
| 假置信度 | `unsure` 是"没匹配上"，不是"匹配了但不确定" |
| 下一步截断 | 正则 `[^。；，,]` 遇逗号就断，中文长句必断 |

### 5.2 契约优先

Python 版与浏览器版实现同一套算法，共用一份契约 `parsing/contract.py`：

```json
{
  "parser": "local",
  "text": "原始输入",
  "fields": {
    "name":     {"value": "洗碗机项目", "confidence": 0.92, "evidence": "洗碗机项目开发中"},
    "customer": {"value": "c_3", "confidence": 0.85, "evidence": "德国 Kalom",
                 "is_new": false, "suggest_name": "德国 Kalom"},
    "phase":    {"value": "开发中", "confidence": 0.95, "evidence": "开发中"},
    "start":    {"value": "2026-11-10", "confidence": 0.80, "evidence": "11/10",
                 "inferred_year": true},
    "end":      {"value": "2026-12-05", "confidence": 0.80, "evidence": "12/5"},
    "contact":  {"value": "老李", "confidence": 0.70, "evidence": "开发老李"},
    "dept":     {"value": "研发部", "confidence": 0.60, "evidence": "开发"},
    "deptType": {"value": "内部", "confidence": 0.75, "evidence": "开发老李"},
    "contactWay": {"value": "", "confidence": 0, "evidence": ""},
    "means":    {"value": "找开发要包装书", "confidence": 0.9, "evidence": "找开发老李要了包装书"},
    "next":     {"value": "催他确认图纸", "confidence": 0.88, "evidence": "下一步催他确认图纸"},
    "note":     {"value": "模具要改，出货可能延到 12/5", "confidence": 0.82,
                 "evidence": "模具要改，出货可能延到 12/5"}
  },
  "milestones": [
    {"date": "2026-12-05", "label": "出货 DDL", "confidence": 0.85,
     "evidence": "12/5 是出货 DDL"}
  ],
  "done_phases": ["未开始"],
  "unresolved": ["contactWay"],
  "warnings": ["「12/5」未写年份，按 2026 推断"]
}
```

前端规则：**`confidence < 0.7` 的字段自动打「待确认」标记**，鼠标悬停显示 `evidence`。这正好复用现有 UI 的 `.flag` 样式，不需要新设计。

### 5.3 本地引擎实现要点

分七个抽取器，各自独立可测：

1. **客户匹配**：先精确匹配名称，再匹配 `alias` 拆分项，最后归一化（去「公司/集团/股份」后缀、大小写、全半角）后模糊匹配。命中多客户时取最长匹配，并降 confidence。
2. **阶段匹配**：按名称长度降序做分词边界匹配，避免"报价中"命中"报价中心"。取最靠后的出现位置作为当前阶段（人说话习惯把最新状态放后面）。
3. **日期归一**：统一解析为 `{y,m,d,precision}`，支持
   - `2026-11-10` / `2026/11/10` / `2026.11.10`
   - `11/10` `11-10` `11.10` `11月10日` `11月10号`
   - `下周三` `下周一` `本周五` `月底` `下月初` `年底` `10天后`
   - 无年份时按"不超过今天 6 个月"推断年份，并置 `inferred_year: true`
4. **区间识别**：`11/10 到 12/5`、`11/10-12/5`、`从11/10开始`、`到12/5 结束`
5. **DDL 识别**：日期后 12 字符内出现 `DDL/deadline/截止/最晚/之前要交/必须交` → 生成 milestone，label 取上下文名词
6. **角色/部门**：`找X` `催X` `X经理` `开发老李` `采购玛丽`；部门靠后缀词表（部/部门/科/组/车间/工厂/中心）+ 内外判定词表
7. **动作与卡点**：动作触发词在句首（下一步/接下来/然后/要/得/需要），取到句末（`。！？\n`）而不是到逗号；卡点触发词（卡在/卡住/等/延迟/延到/要改/问题/不过/但是）

置信度来源（不是拍脑袋）：
```
confidence = 匹配强度(0~1) × 上下文加成 × 唯一性惩罚
```
例：客户名完整命中 0.95；靠 alias 命中 0.85；模糊命中且候选 >1 → ×0.7。

### 5.4 LLM 增强（P2，默认关闭）

默认 `parser=local`。LLM 路径只有在用户**手动**打开开关并配置密钥后可用，且必须满足：

1. UI 明确提示"本次将把 X 字文本发送至 Y 服务商"
2. 提供**脱敏预处理**：客户真实名 → `客户A/客户B` 映射后再发送，返回后本地还原
3. 密钥存 `%LOCALAPPDATA%\BusinessDashboard\credentials.json`，权限 0600，永不回传前端
4. 失败一律降级回 `local`，不阻塞录入

> 这条线的存在是为了将来，不是为了明天。**明天用它不需要、也不应该联网。**

---

## 6. API 契约

统一前缀 `/api`，JSON，同源访问。

### 6.1 启动

```
GET /api/health
→ {"ok":true,"version":"1.0.0","mode":"backend","db":"C:\\...\\dashboard.sqlite3",
   "parser":"local","counts":{"projects":6,"customers":3,"phases":7}}

GET /api/bootstrap
→ {"customers":[...],"phases":[...],"projects":[...]}   # 形状见 §6.2
```

`bootstrap` 一次返回全量，前端只需一次请求即可渲染整个看板（500 条项目以内无性能问题，这个规模不需要分页）。

### 6.2 项目对象（出口形状）

```json
{
  "id": "p_1",
  "name": "洗碗机项目",
  "customer": "c_3",
  "phase": "开发中",
  "start": "2026-11-10",
  "end": "2026-12-05",
  "color": "#1d9e75",
  "contact": "老李",
  "dept": "研发部",
  "deptType": "内部",
  "contactWay": "企业微信",
  "means": "找开发要包装书",
  "channel": "群聊",
  "note": "模具要改，出货可能延到 12/5",
  "next": "催老李确认图纸",
  "updated": "2026-11-24",
  "unsure": ["end"],
  "done": ["未开始"],
  "milestones": [{"id":"m_1","date":"2026-12-05","label":"出货 DDL","done":false}]
}
```

与现有前端 `DB.projects[]` 元素**字段完全一致**，仅新增 `milestones[].done`。

### 6.3 写入

前端一次编辑后把整份数据推回去，而不是逐条 diff：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/state` | **全量替换** customers / phases / projects（含里程碑、已完成阶段、待确认字段）。前端 `save()` 走这个。单事务，失败全回滚；`captures` 与 `change_log` 不受影响 |
| PATCH | `/api/projects/{id}` | 部分更新，只传变化字段 |
| DELETE | `/api/projects/{id}` | 软删除（`archived=1`），保留审计 |
| POST | `/api/customers` | 新建客户 |
| PATCH | `/api/customers/{id}` | 更新 |
| DELETE | `/api/customers/{id}` | 软删除，并把关联项目的 `customer_id` 置空（项目不删） |
| PUT | `/api/phases` | **整体替换**阶段列表。同名阶段复用原 id，避免项目丢失当前阶段 |

> **为什么有 `/api/state` 这种"不 REST"的端点**：前端的每一次编辑（改项目、加里程碑、调阶段顺序）最后都汇到同一个 `save()`，它手里只有整份内存数据，没有 diff。要精确知道改了什么，得重写全部 750 行写入逻辑。全量替换在 200KB 规模下一次约 3ms，代价可以忽略，换来的是**前端零改动**。细粒度端点保留给导入、脚本和测试用。

**写操作统一行为**：单事务、写 `change_log`、返回更新后的对象。

### 6.4 解析与录入

```
POST /api/parse
body: {"text":"...", "project_hint": "p_1" | null}
→ ParseResult（§5.2）

POST /api/captures
body: {
  "raw_text": "...",
  "project_id": "p_1",
  "parser": "local",
  "parsed": {...},              # 原样存快照
  "apply": {"phase":"开发中","next":"催老李确认图纸", ...}   # 用户核对后实际采用的字段
}
→ {"project": {...}, "capture_id": "cap_1"}
```

`apply` 与 `parsed` 分开存：`parsed` 是机器给的，`apply` 是人确认的。两者都要，才能事后评估解析质量。

### 6.5 数据搬运

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/export?format=json` | 导出全量 JSON（离线模式也能生成同一格式） |
| GET | `/api/export?format=csv` | 项目列表扁平 CSV，UTF-8 BOM（Excel/WPS 直接打开不乱码） |
| POST | `/api/import` | 导入 JSON；`mode=merge` 或 `replace` |
| GET | `/api/backup` | 直接下载 sqlite 文件（整库快照） |

### 6.6 错误格式

```json
{"error":{"code":"VALIDATION","message":"计划结束日期不能早于开始日期",
          "fields":{"end":"早于 start"}}}
```

码表：`VALIDATION` / `NOT_FOUND` / `CONFLICT` / `INTERNAL`。

---

## 7. 安全边界

单机单用户，但仍必须守住三条线：

1. **只绑回环**：`uvicorn --host 127.0.0.1`。不提供 `0.0.0.0` 参数，从物理上杜绝同网段他人访问。
2. **Host/Origin 守卫**：所有 `POST/PATCH/PUT/DELETE` 校验 `Host` ∈ {`127.0.0.1`,`localhost`,`[::1]`}，`Origin` 同理。防的是恶意网页通过浏览器向本地端口发请求（DNS rebinding / CSRF）。
3. **敏感信息不落日志**：日志只记录实体 id 与动作，**不记录 `raw_text`、客户名、项目名**。解析失败记录长度与错误类型即可。

若将来要开放局域网共享（当前明确不做），必须补：随机 token（存 cookie）+ 只读/读写分权 + HTTPS 或至少请求签名。`ROADMAP.md` P3 有记录。

---

## 8. 启动链路

### 8.1 macOS

`scripts/start.command`（双击）：
```
1. 定位 python3（优先 ./venv，其次 anaconda，最后 /usr/bin/python3）
2. 缺依赖则 pip install -r requirements.txt（失败不阻塞，转离线模式提示）
3. python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
4. open http://127.0.0.1:8787
```

### 8.2 Windows

`scripts\start.bat`（双击）：
```
1. 依次尝试 py -3 / python / C:\Python3*\python.exe / anaconda
2. 全部找不到 → 打印明确提示，并直接打开 index.html 走离线模式
3. 找到则起服务并 start http://127.0.0.1:8787
```

**关键：`start.bat` 在找不到 Python 时不是报错退出，而是直接打开离线版。** 这是明天不翻车的关键设计。

### 8.3 端口

默认 `8787`（避开 8000/5173 冲突）。被占用则自动向上探测 `8788..8800`。

---

## 9. 性能与容量

规模假设：≤ 50 个项目、≤ 300 个里程碑、单用户。全部数据 < 200 KB。

- `bootstrap` 全量返回，不做分页
- SQLite 开 `WAL`，`synchronous=NORMAL`
- 前端渲染已是一次性 innerHTML，无需虚拟滚动
- 月历只渲染当月，不预加载

不需要缓存层、不需要索引优化、不需要异步任务队列。

---

## 10. 已知风险

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| Windows 无 Python 且无安装权限 | 中 | 后端不可用 | 离线模式保底，功能完整只是不落盘；当天导出 JSON |
| Windows Defender 拦截脚本 | 中 | 双击没反应 | 提供手动命令行启动说明；`.bat` 不含混淆特征 |
| 公司网络代理拦截 localhost | 低 | 页面打不开 | 用 `127.0.0.1` 而非 `localhost`；或直接离线模式 |
| 浏览器禁用 localStorage（策略） | 低 | 离线模式不存 | 首次进入做写测试，失败则强提示"必须导出" |
| Excel 打开 CSV 乱码 | 中 | 导出不可读 | 强制 UTF-8 BOM |
| 阶段改名导致 `done_phases` 悬空 | 中 | 进度计算错 | `PUT /api/phases` 时按新列表清理，逻辑同前端 `savePhases()` |
