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
- Final SQLite schema and migration approach.
- Secure credential storage implementation for macOS and Windows.
- Markdown selection/size limits and exclusion patterns beyond `.git`, `node_modules`, `dist`, and `build`.
- Exact model output schema and retry/backoff behavior.
- Windows startup installation/uninstallation flow and macOS follow-up.

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
- 最终 SQLite 表结构和迁移策略。
- macOS 与 Windows 的安全凭证存储实现。
- Markdown 文件选择／大小限制，以及默认排除规则。
- 模型响应结构和重试退避方式。
- Windows 开机启动的安装／卸载流程及 macOS 后续支持。
