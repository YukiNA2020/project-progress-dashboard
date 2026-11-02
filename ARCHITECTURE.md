# Architecture Notes

## Decisions

- **Application shape:** standalone local web application. It does not depend on Project Hub at runtime.
- **Frontend:** React + TypeScript + Vite. Vite builds static assets; Node.js is used for development/build, not required as the production application server.
- **Backend:** Python + FastAPI + Uvicorn. The backend reads explicitly registered project paths, coordinates scans, calls configured model APIs, validates output, and serves the built frontend.
- **Persistence:** SQLite using Python's `sqlite3`; no separate database service.
- **Provider integration:** OpenAI and Anthropic request formats behind separate adapters.
- **Local network:** bind the web server to `127.0.0.1` by default. No cloud hosting, telemetry, or project data upload service.
- **Platform plan:** develop on macOS, verify the core on Windows, and isolate login startup and open-folder behavior behind platform adapters. Windows startup is the first automated launch target.

## Data flow

```text
User registers a project path and planned dates
                ↓
Local FastAPI service validates and stores project metadata in SQLite
                ↓
Read-only scanner enumerates eligible Markdown files under that path
                ↓
Evidence selection collects explicit dated status records and source references
                ↓
Configured model provider extracts structured progress state
                ↓
Validation checks dates, evidence references, conflicts, and missing fields
                ↓
SQLite stores accepted state, scan history, and pending confirmations
                ↓
React UI renders the monthly timeline, project detail, and scan summary
```

The browser never receives API secrets and does not directly read arbitrary local folders. The backend handles filesystem access. Model requests go only to the endpoint configured by the user.

## Proposed domain records

- **Project**: stable ID, name, local folder path, planned start/end, color, summary, archive state, latest accepted phase, last scan result.
- **Phase**: project ID, phase name/order, status (`completed`, `current`, `upcoming`, or `unknown`), optional start/end dates, optional explicit testing label.
- **Evidence**: project ID, source Markdown path, explicit record date, extracted claim, and a short source excerpt or heading reference.
- **Scan run**: start/end time, result, projects scanned, detected changes, unresolved conflicts, and safe error summary.
- **Pending confirmation**: proposed schedule change or ambiguous state, previous value, candidate value, evidence, and user decision.

## State and trust rules

- Project source documents are immutable inputs from the dashboard's perspective.
- Explicit dates in progress records determine freshness; file modification times do not establish project status.
- Preserve the last successful project state when model calls fail or evidence is ambiguous.
- Do not promote a proposed schedule change to the calendar until the user confirms it.
- Keep evidence paths alongside extracted facts so users can verify model output.
- Treat document contents as untrusted data, never as executable instructions.

## Local API and UI

- Development: Vite dev server plus FastAPI on loopback.
- Production: build the Vite frontend to static assets and serve those assets from FastAPI.
- FastAPI routes cover health/config status, project CRUD/archive, manual refresh, scan status, project detail, and confirmation of schedule changes.
- Validate local paths server-side. Only read paths the user explicitly registers; never expose arbitrary file read/write endpoints.
- Use a platform adapter for opening a folder in the OS file manager.

## Startup and scheduling

- Windows login startup launches the local app and opens its browser URL.
- Run at most one automatic scan per local calendar day, on first startup.
- Keep manual refresh available at any time.
- If the computer starts without access to the configured model endpoint, report failure, keep the last successful state, and allow retry.
- Keep login startup registration separate from the core scan/domain logic. macOS startup follows after Windows behavior is validated.

## Security and privacy

- Bind local services to loopback only by default and validate Host/Origin for state-changing local API requests.
- Store API secrets outside source control, preferably in the operating system credential store; never include them in frontend bundles, logs, prompts, or exported project data.
- Exclude credentials, local project contents, generated databases, logs, and caches from Git.
- Send only the minimum relevant Markdown evidence needed for a scan to the configured model API.
- Show the configured provider and endpoint host so users can verify the destination.
- Explain that project content is sent to the configured endpoint; local hosting alone does not make a remote model request offline.

## Remaining implementation details

- Dependency versions and lockfile formats.
- Windows behavior when `keyring` is installed; macOS currently uses `keyring` when present and the `0600` file otherwise.
- Provider retry policy beyond the single attempt per project per scan.
- Real Windows login-startup verification; signed installers and Linux autostart remain deferred.

## Phase 0 implementation

- The Vite development server binds to `127.0.0.1:5173` and proxies `/api` to the FastAPI service at `127.0.0.1:8000`.
- FastAPI exposes `GET /api/health`. When a frontend build exists in `dist/`, it serves that build from `/`.
- The Phase 0 screen displays the API health response and makes no project-file or model requests.
- Frontend package versions are captured by `package-lock.json`; Python runtime dependencies are pinned in `backend/requirements.txt`.
- Follow the OS-specific setup commands in `README.md`. Runtime databases and user data belong outside the source tree; no database is created in Phase 0.

## Phase 1 implementation

- SQLite stores explicitly entered project metadata under the operating system's per-user application data directory, outside this repository.
- The API supports listing, creating, editing, archiving, restoring, and reading project records. Project paths are treated as strings; this lets users register Windows paths while developing on macOS without probing those paths.
- The browser presents a month grid, project list, project form, and a detail view with a placeholder Phase timeline until Markdown scanning exists.
- Project CRUD requests are limited to loopback Host/Origin values; the development API allows the local Vite origin.

## Phase 2 implementation

**Backend layout**

- `app/settings.py`, `app/db.py`, `app/schemas.py`, `app/routes.py`, `app/service.py` hold configuration, SQLite access, request models, loopback API routes, and scan orchestration.
- `app/scanner/` contains the read-only pipeline: `discovery.py` (folder walk), `markdown_doc.py` (heading-scoped parsing), `extract.py` (evidence rules), `state.py` (candidate state and trust rules), `dates.py` (year-qualified date recognition).

**Scan flow**

1. Resolve the registered folder. A missing or non-directory path is a scan failure, not a project change; the previously accepted state is kept and the error is recorded.
2. Walk the folder once, pruning dependency/build/VCS/cache and hidden directories. Caps: 300 files, 512 KB per file, 4 MB total. Symlinked directories are not followed, and symlinked files are read only when their target stays inside the registered folder.
3. Parse each file into heading-scoped sections, ignoring fenced code blocks and HTML comments, so example snippets cannot become evidence.
4. Extract dated progress records, phase headings with status lines, the README summary, testing labels, and schedule statements.
5. Build one candidate state, apply the conflict rules, and persist it.

**Trust rules implemented**

- Only a record with an explicit year-qualified date counts; names such as "next Friday" or "11月5日" are ignored.
- A statement containing plan wording (`计划`, `预计`, `target`, `ETA`) is excluded from freshness, and dates later than today are never used to judge recency.
- A progress record only claims a phase when it says it *entered* one ("进入 Phase 2", "moved to Phase 3"). A line that only reports a finished phase does not move the pointer.
- Phase status comes from `Status:` / `状态：` lines, `[x]` checklists, or the heading text. "Not started" is classified before "started" so negations are not read as progress.
- When no phase carries an in-progress marker but a completed prefix exists, the current phase is derived and labelled as derived in the UI; the basis is stored in `current_basis`.
- Conflicts (same newest date claiming two phases, two phases marked in progress, contradictory phase dates) produce `needs_confirmation`. The accepted phase is left untouched; the candidate and the reason are stored separately.

**Persistence**

- `project_state` keeps accepted and candidate values separately, plus reason, basis, newest record, summary, notes, file/evidence counts, `scan_error`, and timestamps.
- `project_phases` and `project_evidence` are rebuilt on each successful scan for that project.
- `pending_confirmations` holds schedule proposals (`accept` applies the date, `dismiss` suppresses it) and ambiguous-state findings (acknowledge only).
- `scan_runs` records one row per scan with counts, result, and a JSON change list.

**API**

- `POST /api/scan` (optional `project_ids`) runs synchronously behind a lock; `GET /api/scan/latest` returns the last run.
- `GET /api/projects` embeds a compact state summary; `GET /api/projects/{id}/detail` returns project, state, phases, evidence, pending items, and the last run.
- `POST /api/pending/{id}/decision` takes `accept` or `dismiss`.

**Read-only guarantees**

- Files are opened with `read_bytes()` only; no write, rename, delete, or `st_mtime` read exists in the scanner.
- `backend/verify_phase2.py` scans synthetic fixtures, hashes the tree before and after, and asserts the hashes are unchanged, that excluded directories are skipped, that code fences are ignored, that conflicts become `needs_confirmation`, and that modification times do not affect the result.

## Phase 3 implementation

**Backend layout**

- `app/secrets_store.py` resolves the API key in this order: OS credential store when `keyring` is importable, otherwise `credentials.json` in the per-user data directory with `0600` permissions. The API only ever returns `api_key_set` and a masked hint.
- `app/config_store.py` owns the single-row `provider_settings` table (enabled, provider, base URL, model, JSON mode, last test result) and validates the form input.
- `app/providers/` holds the model layer: `transport.py` (standard-library HTTP with safe error messages), `openai.py` and `anthropic.py` (payload and response shapes), `client.py` (dispatch, key resolution, connectivity test), `bundle.py` (minimum evidence selection), `prompt.py` (contract), `schema.py` (parsing and validation), `analyze.py` (one call).
- `app/reconcile.py` merges the rule result with the validated model result.

**What is sent**

- One numbered bundle per project: at most 14 items, 600 characters each, about 6,000 characters total.
- Item kinds: project summary, newest progress sentences, phase headings with their status line, and schedule statements. Progress items send the sentence, not the date line; phase items send the document heading because the status line alone does not name the phase.
- Sources are paths relative to the registered folder. Absolute paths, file contents, credentials, and environment details are never included.

**Structured output contract**

The model must return one JSON object with `current_phase_ordinal`, `current_phase_name`, `phase_status`, `testing`, `summary`, `schedule_changes`, `conflicts`, `citations`, and `confidence`. Validation rejects:

- a response that is not a JSON object (code fences are tolerated, prose is not);
- a citation whose `evidence_id` was not in the bundle;
- a quote shorter than four characters or not present verbatim in that evidence;
- a phase number that does not appear in its own `current_phase` citation;
- a schedule date that does not appear in the cited evidence, or a date outside 1990–2100;
- a conclusion that lacks the citation kind it requires (`testing`, `summary`, `schedule`, `conflict`);
- a `schedule_changes` field other than `planned_start` or `planned_end`.

**Reconciliation**

- Dates and freshness remain rule-owned. The model cannot introduce a record date.
- Status becomes `ok` only when both sides agree on the current phase. The basis is recorded as `rules_and_model`; a phase name is adopted only when the rule name was a bare `Phase N` placeholder.
- A rule-level conflict, a model-reported conflict, a phase disagreement, a one-sided phase claim, or two different candidate dates for the same field produce `needs_confirmation` with both values in the reason. The accepted phase is untouched.
- A provider failure or an invalid answer produces `model_error`: the rule candidate is still stored for inspection, `accepted_*` keeps its previous value, and a `model_issue` pending item records the safe error text.
- A model summary replaces the rule summary only when it is cited and at least 12 characters long; its source path travels with it.
- Schedule dates from either side are merged into proposals. Identical dates collapse to one proposal; conflicting dates are shown as a problem instead of a silent choice.

**Persistence and API**

- `project_state` gains `model_status`, `model_provider`, `model_name`, `model_confidence`, `model_summary`, `model_citations`, `model_error`, and `model_checked_at`.
- `scan_runs` gains `model_ok`, `model_failed`, and `model_enabled`.
- Existing databases are upgraded with `PRAGMA table_info` plus `ALTER TABLE ... ADD COLUMN`.
- `GET /api/provider` returns configuration and a masked key hint only. `PUT /api/provider` keeps the stored key when `api_key` is omitted and clears it on an empty string. `POST /api/provider/test` reuses the same adapter and can test unsaved form values without storing them.
- `POST /api/scan` accepts `use_model=false` to run rules only.
- Health reports `phase: 3`.

**Verification**

- `backend/verify_phase3.py` patches the transport with a fake, so no network or key is required. It covers: rules-only scans, agreement, provider 500/timeout/401, malformed JSON, unknown evidence id, quote mismatch, invented schedule date, phase disagreement, model-reported conflict, low confidence, schedule proposals from rules and from the model, an Anthropic round trip, the skipped case, database migration, and that project files stay byte-for-byte unchanged.
- The same script asserts the request body contains neither the API key nor an absolute path, that `GET /api/provider` returns only a mask, and that the fallback credential file is `0600`.

## Phase 4 implementation

**Layout**

- `app/system/` is the only place that branches on the operating system: `opener.py` (file manager), `windows_startup.py` (per-user Run key), `macos_startup.py` (LaunchAgent plist), and `__init__.py` (status, enable, disable, launcher command).
- `app/daily.py` owns the once-a-day rule. `app/cli.py` is the command line entry point, and `backend/run.py` is a thin launcher that does not depend on the working directory.
- `GET /api/system`, `POST /api/startup`, and `POST /api/projects/{id}/open-folder` expose the result to the UI.

**Login startup**

- Windows: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value name `ProjectProgressDashboard`, set to `"<python>" "<backend>\run.py" serve --open-browser`. It needs no administrator rights, is visible in Task Manager's startup tab, and `pythonw.exe` is used when it exists so no console window appears. The value is written through `winreg` with explicit key handles; no shell is involved.
- macOS: `~/Library/LaunchAgents/com.projectprogressdashboard.dashboard.plist` with `RunAtLoad` true, `KeepAlive` false, and standard output/error pointing at the dashboard log. Enabling writes the plist, boots out a stale job, then runs `launchctl bootstrap gui/<uid>`. If launchctl refuses, the API returns the exact command for the user to run and keeps the plist in place.
- Linux: reported as unsupported with the launch command shown; no autostart file is written.
- The command is always built from `sys.executable` and the real `backend/run.py`, so moving the repository only requires toggling the entry again.

**Daily automatic scan**

- `daily_scans` is keyed by the local calendar date. `INSERT OR IGNORE` is the claim; zero changed rows means another start already claimed today. Four simultaneous processes produce exactly one claim.
- A failed automatic scan still consumes the day, and the row records `failed` plus a safe message. Background retries would hide repeated failures, so retrying stays a user action.
- `scan_runs.trigger` records `auto`, `manual`, or `cli`. `project_state.last_failure_at` records when a project last failed and survives later successes; `last_success_at` remains the retained state timestamp shown next to it.
- The CLI sets `PROJECT_PROGRESS_DASHBOARD_AUTO_SCAN=1`; the FastAPI startup hook runs `daily.run_if_due()` in a daemon thread so the browser is not blocked while projects are scanned.

**Single instance**

- `app.cli.probe_running()` calls `/api/health` and checks the `service` marker, not just that the port is open. A second launch on the same port therefore opens the browser and exits instead of starting a competing service.

**Opening a project folder**

- The route accepts a project id only, then reads the registered path. The adapter refuses an empty path, a missing path, or a non-directory, and never runs when validation fails.
- Commands are argument lists with `shell=False`: `open` on macOS, `explorer` on Windows, `xdg-open` on Linux. `explorer` returns a non-zero code even on success, so its exit code is ignored after the path check.

**Verification**

- `backend/verify_phase4.py` uses a fake `winreg` module, a fake `launchctl` runner, a temporary home directory, and local HTTP stubs. It covers the daily claim (including four concurrent processes), cross-day behaviour, failure timestamps, retained state, manual retry, every open-folder branch, Windows quoting, plist contents, launchctl fallback, single-instance detection, the API surface, and the upgrade of a Phase 1-era database.
- The script never writes a real startup item and never calls the real `launchctl`.


---

# 架构说明（中文版）

## 已确定的技术选择

- **应用形态：** 独立的本地 Web 应用，运行时不依赖 Project Hub。
- **前端：** React + TypeScript + Vite。Vite 构建静态资源；Node.js 用于开发和构建，不作为正式运行时的应用服务器。
- **后端：** Python + FastAPI + Uvicorn。后端读取用户明确登记的项目路径、协调巡检、调用模型 API、校验结果并提供前端资源。
- **持久化：** 使用 Python `sqlite3` 连接 SQLite，不需要单独数据库服务。
- **模型接入：** OpenAI 与 Anthropic 请求格式分别通过适配器接入。
- **本地网络：** 默认只监听 `127.0.0.1`。不做云托管、遥测或项目数据上传服务。
- **平台计划：** 在 macOS 开发，在 Windows 验证核心功能；开机启动和打开文件夹等能力通过平台适配器隔离。首先实现 Windows 开机启动。

## 数据流

```text
用户登记项目路径和计划日期
                ↓
本地 FastAPI 服务校验并写入 SQLite
                ↓
只读扫描器枚举路径下符合条件的 Markdown 文件
                ↓
提取带明确日期的状态记录和来源引用
                ↓
用户配置的模型 API 提取结构化进展
                ↓
校验日期、来源、冲突和缺失信息
                ↓
SQLite 保存已接受状态、巡检历史和待确认项
                ↓
React 界面呈现月历、项目详情和巡检摘要
```

浏览器不直接读取任意本地文件夹，也不接触 API 密钥；文件读取由本地后端负责。模型请求只发送到用户配置的 API 地址。

## 核心数据对象（初步）

- **项目：** 稳定 ID、名称、本地路径、计划起止日期、颜色、简介、归档状态、当前已接受 Phase、上次巡检结果。
- **Phase：** 项目 ID、阶段名和顺序、状态（已完成／当前／后续／未知）、可选起止日期、可选的明确测试状态。
- **证据：** 项目 ID、来源 Markdown 路径、明确记录日期、提取出的陈述，以及简短原文或标题引用。
- **巡检记录：** 开始和结束时间、结果、扫描项目数、发现的变化、未解决冲突和安全的错误摘要。
- **待确认项：** 排期变更或模糊状态的旧值、候选值、证据和用户决定。

## 状态与信任规则

- 看板将项目源文档视为不可修改的输入。
- 进展记录中明确写出的日期决定状态新旧；文件修改时间不能代替状态日期。
- 模型调用失败或证据模糊时保留上次成功状态。
- 计划日期变更经用户确认后才进入时间轴。
- 提取结果旁保留来源路径，便于用户核对。
- 将文档内容视为数据，不执行其中的指令。

## 本地 API 与界面

- 开发模式：Vite 开发服务器加本地 FastAPI。
- 正式运行：Vite 构建前端静态资源，由 FastAPI 提供。
- FastAPI 路由覆盖健康检查／配置状态、项目增删改与归档、手动刷新、巡检状态、项目详情和排期变更确认。
- 服务端校验路径；只读取用户明确登记的文件夹，不提供任意文件读写接口。
- 通过平台适配器在系统文件管理器中打开项目文件夹。

## 开机启动与调度

- Windows 登录时启动本地应用并打开浏览器。
- 每个本地自然日最多自动巡检一次，在当天首次启动时执行。
- 始终保留手动刷新。
- 如果电脑启动时无法连接用户配置的模型 API，显示失败，保留上次成功状态并允许重试。
- 开机启动注册与核心进度逻辑分离；验证 Windows 行为后再补 macOS 启动支持。

## 安全与隐私

- 本地服务默认只绑定回环地址；状态变更 API 校验 Host/Origin。
- API 密钥保存在操作系统凭证库等源码之外的位置；绝不写入前端包、日志、提示词或导出文件。
- Git 排除凭证、本地项目内容、生成数据库、日志和缓存。
- 只向模型发送提取所需的最少 Markdown 内容。
- 显示当前配置的模型服务商和 API 主机名，供用户核对请求目的地。
- 清楚说明：本地托管本身不代表远程模型请求离线。

## 尚待实现时决定的细节

- 依赖版本和锁文件格式。
- 安装 `keyring` 后 Windows 上的凭证行为；macOS 目前优先用 `keyring`，否则用 `0600` 文件。
- 单个项目每次巡检只尝试一次之外的模型重试策略。
- 真实 Windows 登录启动的验证；签名安装程序和 Linux 自启动仍延后。

## Phase 2 实现说明

**后端结构**

- `app/settings.py`、`app/db.py`、`app/schemas.py`、`app/routes.py`、`app/service.py` 分别负责配置、SQLite、请求模型、回环路由和巡检编排。
- `app/scanner/` 是只读流水线：`discovery.py` 遍历目录、`markdown_doc.py` 按标题分节、`extract.py` 抽取证据、`state.py` 生成候选状态并应用信任规则、`dates.py` 识别带年份的日期。

**巡检流程**

1. 解析登记路径。路径不存在或不是文件夹时记为巡检失败，不当作项目状态变化，保留上次已接受状态并记录错误。
2. 单次遍历目录，跳过依赖／构建／版本库／缓存与隐藏目录。上限：300 个文件、单文件 512 KB、总计 4 MB。不跟随目录软链；文件软链只有指向登记目录内部时才读取。
3. 按标题分节解析，跳过代码块与 HTML 注释，避免示例片段被当作证据。
4. 抽取带明确日期的进展、Phase 标题与状态行、README 简介、测试标记和排期描述。
5. 合成一个候选状态，套用冲突规则后落库。

**已实现的信任规则**

- 只认带年份的完整日期；“下周五”“11月5日”一律忽略。
- 含计划措辞（计划／预计／target／ETA）的语句不计入新鲜度；晚于今天的日期不用于判断新旧。
- 进展记录只有表达“进入某阶段”（进入 Phase 2、moved to Phase 3）时才作为当前阶段证据；只报告“完成某阶段”的句子不会推移指针。
- 阶段状态来自 `Status:`／`状态：` 行、`[x]` 清单或标题文本；先判断“未开始”再判断“started”，否定的句子不会被读成进展。
- 无进行中标记但存在“已完成”前缀时，当前阶段按前缀推定，并在界面标注为推定；依据记录在 `current_basis`。
- 冲突（同一最新日期出现两个阶段、两个阶段同时进行中、阶段日期互相矛盾）进入“待确认”：已接受状态保持不变，候选值与原因单独保存。

**持久化**

- `project_state` 分开保存已接受值与候选值，以及原因、依据、最新记录、简介、备注、文件数、证据数、`scan_error` 和时间戳。
- `project_phases` 与 `project_evidence` 每次成功巡检后按项目重建。
- `pending_confirmations` 保存排期提议（接受后写入计划日期，忽略后不再重复出现）和冲突项（只能标记为已知）。
- `scan_runs` 每次巡检一行，记录统计、结果和 JSON 变化列表。

**接口**

- `POST /api/scan`（可选 `project_ids`）在锁内同步执行；`GET /api/scan/latest` 返回最近一次巡检。
- `GET /api/projects` 内嵌精简状态；`GET /api/projects/{id}/detail` 返回项目、状态、阶段、证据、待确认项和最近巡检。
- `POST /api/pending/{id}/decision` 接受 `accept` 或 `dismiss`。

**只读保证**

- 扫描器只用 `read_bytes()` 读取文件，不存在写入、重命名、删除或读取 `st_mtime` 的路径。
- `backend/verify_phase2.py` 对合成样例执行巡检，前后比对目录哈希，并验证：排除目录未被读取、代码块被忽略、冲突变为“待确认”、文件修改时间不影响结果。

## Phase 3 实现说明

**后端结构**

- `app/secrets_store.py` 按顺序解析密钥：`keyring` 可用时写系统凭证库，否则写到应用数据目录下的 `credentials.json` 并设为 `0600`。接口只返回 `api_key_set` 与掩码。
- `app/config_store.py` 管理单行 `provider_settings` 表（开关、服务商、地址、模型、JSON 模式、上次测试结果），并校验表单输入。
- `app/providers/` 是模型层：`transport.py`（标准库 HTTP，错误信息可安全展示）、`openai.py`／`anthropic.py`（请求与响应结构）、`client.py`（分发、取密钥、连通性测试）、`bundle.py`（最小证据选择）、`prompt.py`（输出约定）、`schema.py`（解析与校验）、`analyze.py`（单次调用）。
- `app/reconcile.py` 合并规则结果与通过校验的模型结果。

**发送什么**

- 每个项目一个编号证据包：最多 14 条、每条 600 字符、总计约 6000 字符。
- 条目类型：项目简介、最新进展句子、阶段标题与状态行、排期语句。进展条目发送句子而不是日期行；阶段条目发送文档标题，因为状态行本身不含阶段名。
- 来源一律是相对登记目录的路径，不发送绝对路径、完整文件、凭证或环境信息。

**结构化输出约定**

模型必须返回单个 JSON 对象，含 `current_phase_ordinal`、`current_phase_name`、`phase_status`、`testing`、`summary`、`schedule_changes`、`conflicts`、`citations`、`confidence`。以下情况一律拒绝：

- 不是 JSON 对象（允许代码块包裹，不允许散文）；
- 引用的 `evidence_id` 不在本次证据包中；
- 引文少于 4 个字符，或在该条证据原文中找不到；
- 阶段编号没有出现在它自己的 `current_phase` 引文里；
- 排期日期没有出现在被引用的证据里，或日期超出 1990–2100；
- 结论缺少它必需的引用类型（`testing`、`summary`、`schedule`、`conflict`）；
- `schedule_changes` 的字段不是 `planned_start`／`planned_end`。

**复核规则**

- 日期与新鲜度仍归规则所有，模型不能引入记录日期。
- 只有双方对当前阶段判断一致才置为 `ok`，依据记为 `rules_and_model`；只有规则名称还是 `Phase N` 占位时才采纳模型给的阶段名。
- 规则层冲突、模型自报冲突、阶段分歧、只有一方给出阶段、同一字段出现两个候选日期，都会变成 `needs_confirmation`，原因里同时列出两边取值，已接受阶段不动。
- 接口失败或输出不合规产生 `model_error`：规则候选仍保存供排查，`accepted_*` 保持原值，并生成一条 `model_issue` 待处理项记录安全的错误文本。
- 模型简介只有在带引用且不短于 12 个字符时才替换规则简介，来源路径一并保存。
- 两边的排期日期合并为提议：相同日期合并为一条，不同日期作为问题呈现，不做静默取舍。

**持久化与接口**

- `project_state` 新增 `model_status`、`model_provider`、`model_name`、`model_confidence`、`model_summary`、`model_citations`、`model_error`、`model_checked_at`。
- `scan_runs` 新增 `model_ok`、`model_failed`、`model_enabled`。
- 旧数据库通过 `PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN` 自动升级。
- `GET /api/provider` 只返回配置与掩码；`PUT /api/provider` 省略 `api_key` 表示保留，传空串表示清除；`POST /api/provider/test` 复用同一适配器，可测试未保存的表单值而不落库。
- `POST /api/scan` 支持 `use_model=false`，只跑规则。
- 健康检查返回当前阶段编号（Phase 4 起为 4）。

**验证**

- `backend/verify_phase3.py` 用假传输层替换真实请求，不需要网络或密钥。覆盖：只跑规则、双方一致、HTTP 500／超时／401、JSON 格式错误、证据编号不存在、引文对不上、凭空排期日期、阶段分歧、模型自报冲突、低置信、规则与模型的排期提议、Anthropic 往返、跳过的情形、数据库迁移，以及项目文件逐字节不变。
- 同一脚本还断言请求体既不含密钥也不含绝对路径，`GET /api/provider` 只返回掩码，回退密钥文件权限为 `0600`。

## Phase 4 实现说明

**结构**

- `app/system/` 是唯一按操作系统分支的地方：`opener.py`（文件管理器）、`windows_startup.py`（当前用户 Run 键）、`macos_startup.py`（LaunchAgent plist）、`__init__.py`（状态、启用、关闭、启动命令）。
- `app/daily.py` 负责每天最多一次的规则；`app/cli.py` 是命令行入口；`backend/run.py` 是不依赖工作目录的轻量启动器。
- `GET /api/system`、`POST /api/startup`、`POST /api/projects/{id}/open-folder` 把结果提供给界面。

**登录启动**

- Windows：写入 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的 `ProjectProgressDashboard`，值为 `"<python>" "<backend>\run.py" serve --open-browser`。不需要管理员权限，可在任务管理器“启动”标签关闭；存在 `pythonw.exe` 时优先使用，避免弹出控制台窗口。注册表通过 `winreg` 显式打开键写入，不经过 shell。
- macOS：写入 `~/Library/LaunchAgents/com.projectprogressdashboard.dashboard.plist`，`RunAtLoad` 为真、`KeepAlive` 为假，标准输出与错误指向看板日志。启用时先 `bootout` 掉旧任务，再 `launchctl bootstrap gui/<uid>`；若 launchctl 拒绝，接口会返回可直接执行的命令，并保留 plist。
- Linux：报告为不支持并展示启动命令，不写自启动文件。
- 命令始终由 `sys.executable` 与真实的 `backend/run.py` 组成，移动仓库后重新开关一次即可。

**每日自动巡检**

- `daily_scans` 以本地日期为主键，用 `INSERT OR IGNORE` 领取；影响行数为 0 表示当天已被别的启动领取。四个并发进程只会有一个领取成功。
- 自动巡检失败同样占用当天，记录 `failed` 与安全提示。后台自动重试会掩盖持续失败，所以重试保持为用户动作。
- `scan_runs.trigger` 记录 `auto`／`manual`／`cli`；`project_state.last_failure_at` 记录项目最近一次失败时间，并在后续成功巡检后保留；`last_success_at` 仍是保留状态的时间。
- CLI 会设置 `PROJECT_PROGRESS_DASHBOARD_AUTO_SCAN=1`；FastAPI 启动钩子在后台线程执行 `daily.run_if_due()`，巡检不会阻塞浏览器打开。

**单实例**

- `app.cli.probe_running()` 读取 `/api/health` 并核对 `service` 标记，而不是只看端口是否被占用。因此同端口第二次启动只会打开浏览器，不会产生第二个服务进程。

**打开项目文件夹**

- 接口只接受项目 ID，再读取已登记路径。适配器拒绝空路径、不存在路径和非文件夹，校验失败时不会执行任何命令。
- 命令以参数列表传入且 `shell=False`：macOS 用 `open`，Windows 用 `explorer`，Linux 用 `xdg-open`。`explorer` 即使成功也返回非零码，因此在路径校验通过后忽略其退出码。

**验证**

- `backend/verify_phase4.py` 使用假 `winreg`、假 `launchctl`、临时 home 与本地 HTTP 桩，覆盖每日领取（含四个并发进程）、跨日行为、失败时间、保留状态、手动重试、打开文件夹各分支、Windows 引号处理、plist 内容、launchctl 回退、单实例识别、接口形态，以及 Phase 1 时期数据库的自动升级。
- 脚本不会写入真实启动项，也不会调用真实 `launchctl`。
