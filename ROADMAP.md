# Roadmap

## Delivery approach

Build a local-first application that can be developed on macOS and continued on Windows from the same GitHub repository. Keep the domain and data model platform-neutral; isolate startup registration and opening a folder behind OS-specific adapters. Do not require real project folders or a model API to complete the first UI phase.

## Technical baseline

| Area | Choice | Responsibility |
|---|---|---|
| UI | React + TypeScript + Vite | Home calendar, project details, local forms, user feedback |
| Local API | Python + FastAPI + Uvicorn | Project file access, scan orchestration, provider calls, validation, local API |
| Persistence | SQLite via Python `sqlite3` | Project metadata, accepted progress, evidence references, scan history, pending confirmations |
| Model providers | OpenAI API format and Anthropic API format behind provider adapters | Convert requests and normalize structured responses |
| Local serving | FastAPI serves the built Vite assets; development uses the Vite server and local API | Browser opens a loopback URL; app binds to `127.0.0.1` only |
| Secrets | OS secure storage where practical; never committed or logged | Keep API credentials out of frontend bundles and source control |

Node.js is a development/build dependency for the frontend. Python runs the local application service. Keep dependency lockfiles and provide separate, documented setup commands for each OS. Do not add Docker, cloud hosting, telemetry, or a remote database to the MVP.

## Phase 0 — Cross-platform project foundation

**Status:** Completed on 2026-10-29. Product docs and the technical foundation are in place.

- Create a Vite React + TypeScript frontend and a Python FastAPI backend in this repository.
- Add a health endpoint and a minimal UI that calls it through a loopback-only local API.
- Configure development mode (Vite frontend + local API) and production mode (FastAPI serves the built frontend).
- Add dependency manifests and lockfiles; exclude `.env`, SQLite files, logs, caches, and local project data from Git.
- Document macOS development commands and Windows setup commands.
- Keep user data outside the source repository.

**Exit:** The app starts locally on macOS and Windows from documented commands, binds only to loopback, and displays backend health. Production serving is supported by FastAPI mounting the Vite build. No project folder or model API is needed.

## Phase 1 — Project registry and calendar UI

**Status:** Implemented and checked on macOS on 2026-10-29; Windows-specific runtime behavior still needs verification on Windows.

- Add project create and edit flows for name, full local folder path, planned start date, and planned end date.
- Validate dates and required fields; allow Windows paths to be entered while developing on macOS without trying to read them on macOS.
- Persist projects in SQLite. Support archive/unarchive instead of destructive delete.
- Render the home page as a month-oriented calendar: dates run left to right, projects are ordered by start date, and each project is a distinct color bar spanning its start and end dates.
- Display the current phase label when one is available; Phase 1 may use user-entered/sample state until the scanner exists.
- Clicking a bar navigates to that project's detail page. Show a concise summary placeholder, folder path, and phase timeline UI.
- Support changing months and showing the correct day offset across 4–6 calendar week rows.

**Exit:** A user can add, edit, archive, restore, and inspect synthetic projects; dates align correctly across month boundaries; data survives app restart; the UI works on macOS and Windows. No model API or project Markdown scan is required.

## Phase 2 — Read-only Markdown evidence scanner

- Read Markdown files only under registered, non-archived project paths.
- Exclude dependency/build/system directories by default, including `.git`, `node_modules`, `dist`, and `build`.
- Identify explicit progress record dates, project summary, phase sequence/current phase, phase dates, testing labels, and candidate schedule changes.
- Preserve source paths and short evidence excerpts/headings for review.
- Treat document text as data, not instructions. Never edit project files.
- Add explicit unknown/conflict outcomes; do not infer dates from file modification times.

**Exit:** Synthetic Markdown fixtures demonstrate that dated updates are ordered correctly, conflicts become “Needs confirmation,” and source files remain unchanged.

## Phase 3 — Model providers and review rules

- Implement OpenAI and Anthropic API adapters with locally configurable base URL, model name, and API key.
- Store secrets outside source control and keep model calls in the backend, not the browser.
- Send only the minimum relevant Markdown evidence needed for extraction.
- Require structured output containing claims and evidence references; validate before persistence.
- Automatically refresh status from the newest explicit dated record when unambiguous.
- Preserve the last accepted state when evidence conflicts or the provider fails.
- Show changed planned dates as proposals and wait for user confirmation before updating the calendar.

**Exit:** Provider failures, malformed output, missing evidence, and conflicting records are visible and never silently replace the last accepted state.

## Phase 4 — Startup integration and daily operation

- Add Windows login startup integration that launches the local service and opens the browser.
- Run at most one automatic scan per local calendar day, on the first startup that day.
- Add manual refresh, scan summary, failure timestamp, retained last-success state, and retry.
- Add “open project folder” using a platform adapter.
- Keep macOS startup support as a follow-on adapter; macOS remains the development platform for the initial implementation.

**Exit:** Windows startup opens the dashboard, duplicate same-day starts do not trigger duplicate automatic scans, and failed scans can be retried manually.

## Phase 5 — Two-week personal validation

- Use the dashboard with a small set of real, authorized local project folders.
- Track time to understand current status and how often extracted phase/status needs correction.
- Review false positives, missed updates, and whether evidence references are sufficient.
- Decide which parsing, timeline, and detail-page behavior to revise before a broader release.

**Exit:** Record a go/no-go decision for broader open-source use and prioritize changes based on actual corrections and usage.

## Deferred

- macOS/Linux login startup and packaged installers.
- PDF, Word, spreadsheet, source-control, and issue-tracker ingestion.
- Multi-user sync, cloud hosting, telemetry, and collaboration.
- Automatic source document edits or unconfirmed schedule changes.

---

# 路线图（中文版）

## 交付方式

应用优先本地运行，今晚在 macOS 开发，明天从同一 GitHub 仓库切换到 Windows 继续。业务逻辑与数据模型保持平台中立；开机启动和打开文件夹通过系统适配器隔离。完成第一阶段 UI 前不依赖真实项目文件夹或模型 API。

## 技术基线

| 领域 | 选择 | 职责 |
|---|---|---|
| 界面 | React + TypeScript + Vite | 首页日历、项目详情、本地表单和用户反馈 |
| 本地 API | Python + FastAPI + Uvicorn | 读项目文件、调度巡检、模型调用、结果校验和本地 API |
| 持久化 | Python `sqlite3` + SQLite | 项目元数据、已接受进度、证据引用、巡检历史和待确认项 |
| 模型服务商 | OpenAI API 格式和 Anthropic API 格式，分别使用适配器 | 转换请求并统一结构化响应 |
| 本地服务 | FastAPI 提供构建后的 Vite 静态资源；开发时使用 Vite 和本地 API | 浏览器打开本机地址；服务只绑定 `127.0.0.1` |
| 密钥 | 尽量使用操作系统安全凭证库；不提交、不记录 | API 凭证不进入浏览器前端包和源码库 |

Node.js 是前端开发／构建依赖，Python 用于运行本地服务。保留依赖锁文件，并分别记录 macOS、Windows 安装命令。MVP 不引入 Docker、云托管、遥测或远程数据库。

## Phase 0 — 跨平台项目基础

**状态：** 产品文档已完成；技术实现尚未开始。

- 在本仓库创建 Vite React + TypeScript 前端和 Python FastAPI 后端。
- 增加健康检查接口，以及一个通过本地 API 获取状态的最小界面。
- 配置开发模式（Vite 前端 + 本地 API）和正式模式（FastAPI 提供构建后的前端）。
- 添加依赖清单和锁文件；Git 排除 `.env`、SQLite 文件、日志、缓存及本地项目数据。
- 编写 macOS 开发命令和 Windows 安装／启动命令。
- 用户数据存放在源码仓库之外。

**退出条件：** 按文档命令可在 macOS 和 Windows 本地启动；服务只监听回环地址，界面能显示后端健康状态。不需要项目文件夹或模型 API。

## Phase 1 — 项目登记与日历界面

- 添加项目新增与编辑流程，字段为名称、完整本地文件夹路径、计划开始日期和计划结束日期。
- 校验必填字段与日期；在 macOS 开发时允许输入 Windows 路径，但不尝试在 macOS 读取它。
- 将项目持久化到 SQLite。支持归档／恢复，不做破坏性删除。
- 首页按月显示日历：日期从左至右，项目按开始日期从上至下排列；每个项目使用单独颜色的色块覆盖其起止日期。
- 如果已知当前 Phase，则在色块上显示；扫描器完成前可使用用户填写的示例状态。
- 点击色块进入项目详情页。先展示简短概况占位、路径和 Phase 时间线界面。
- 支持切换月份，并按 4–6 周的月历行正确呈现日期偏移。

**退出条件：** 用户可新增、编辑、归档、恢复并查看合成项目；跨月日期显示正确；重启应用后数据仍存在；macOS 和 Windows 界面可用。不依赖模型 API 或 Markdown 扫描。

## Phase 2 — 只读 Markdown 证据扫描

- 只读取已登记且未归档项目路径下的 Markdown 文件。
- 默认排除 `.git`、`node_modules`、`dist` 和 `build` 等依赖／构建／系统目录。
- 识别明确的进展日期、项目简介、Phase 顺序和当前阶段、阶段日期、测试标记和候选排期变化。
- 保留来源路径和简短证据片段／标题引用。
- 文档内容当作数据，不执行其指令；绝不修改项目文件。
- 明确处理未知状态与冲突；不根据文件修改时间推断日期。

**退出条件：** 合成 Markdown 样例证明日期顺序正确、冲突会标“待确认”，且源文件保持不变。

## Phase 3 — 模型服务商与复核规则

- 实现 OpenAI 与 Anthropic API 适配器，可在本地配置 API 地址、模型名和 API 密钥。
- 密钥不进源码库；模型调用放在后端，不从浏览器直接发起。
- 只向模型发送抽取所需的最少 Markdown 证据。
- 要求结构化结果包含陈述和证据引用，并在保存前校验。
- 证据无歧义时，按最新明确日期自动刷新进度。
- 证据冲突或服务商失败时保留上次已接受状态。
- 新计划日期作为提议展示，用户确认后才更新日历。

**退出条件：** 服务失败、响应格式错误、证据缺失和文档冲突均能显式提示，且不会静默覆盖上次状态。

## Phase 4 — 开机启动与日常运行

- 增加 Windows 登录启动功能，启动本地服务并打开浏览器。
- 每个本地自然日最多自动巡检一次，在当天首次启动时执行。
- 增加手动刷新、巡检摘要、失败时间、保留上次成功状态和重试。
- 通过系统适配器提供“打开项目文件夹”。
- macOS 开机启动作为后续适配；初始实现仍在 macOS 开发。

**退出条件：** Windows 开机可打开看板；当天重复启动不重复自动巡检；失败后可手动重试。

## Phase 5 — 两周个人验证

- 使用少量真实且经授权的本地项目文件夹。
- 记录理解项目状态所需时间，以及 Phase／状态提取被纠正的频次。
- 复盘误报、漏报和证据引用是否足够清楚。
- 根据真实使用结果决定在扩大开源使用前调整哪些解析规则和界面。

**退出条件：** 记录是否扩大开源使用的决定，并依据真实纠正与使用情况排出改进优先级。

## 延后事项

- macOS／Linux 登录启动与打包安装程序。
- PDF、Word、电子表格、源代码管理和 issue tracker 导入。
- 多用户同步、云托管、遥测和协作。
- 自动修改源文件或未经确认更改排期。
