# Project Progress Dashboard

A local-first, open-source dashboard for tracking project schedules and phase progress from Markdown documents.

## Status

Phase 0 (cross-platform foundation), Phase 1 (project registry and calendar), Phase 2 (read-only Markdown evidence scanner), and Phase 3 (OpenAI/Anthropic adapters with review rules) are implemented and checked on macOS. Windows runtime behavior still needs verification there.

## What the scanner reads

- Markdown only, and only inside project folders you register. `.git`, `node_modules`, `dist`, `build`, dependency, cache, and hidden directories are skipped.
- It records explicit dated progress, the phase sequence and current phase, phase dates when documented, a testing label, and candidate schedule changes — always with the source path, heading, and a short excerpt.
- Dates must include a year. Sentences with plan wording, and dates later than today, never make a project look fresher. File modification times are never used.
- Conflicting documents become "Needs confirmation"; the last accepted state is kept and nothing is guessed.
- Files are opened read-only. The scanner never writes, renames, or deletes anything in a project folder.

## How model review works

The rules stay authoritative for dates. A configured provider is used as a second opinion:

- Only a numbered evidence bundle is sent: up to 14 items, roughly 6,000 characters, relative paths only. Whole documents are never uploaded.
- The model must answer with JSON that cites an evidence id and quotes that evidence verbatim. The backend rejects an unknown id, a quote that is not in the source, a phase number absent from its own citation, or a schedule date absent from the evidence.
- Status only advances when the rules and the model agree. A disagreement, a model-reported conflict, malformed output, or a provider failure shows up in the UI as "needs confirmation" or "model not confirmed", and the last accepted state is kept.
- Schedule dates are always proposals. The calendar changes only after you accept them.
- The API key is stored outside the repository (OS credential store when `keyring` is available, otherwise a `0600` file in the app data directory) and is never returned to the browser.

## Technical route

- React + TypeScript + Vite frontend.
- Python + FastAPI + Uvicorn local backend.
- SQLite local storage.
- OpenAI and Anthropic provider adapters.
- Loopback-only local web app; no cloud hosting or telemetry.

See [ROADMAP.md](ROADMAP.md) for the phased implementation plan and [ARCHITECTURE.md](ARCHITECTURE.md) for system boundaries.

## MVP

- Add projects by entering their local folder path, name, planned start date, and planned end date.
- Show all projects on a month-oriented calendar timeline, with a colored bar spanning each project's dates.
- Open a project detail page with its phase timeline, latest dated progress, summary, and source documents.
- Read Markdown files only. Never modify project files.
- Run one automatic scan on the first computer startup each day, with a manual refresh button.
- Support configurable OpenAI and Anthropic API formats. Keep the app and its data local; make model requests only to the endpoint configured by the user.

## Development (Phase 0)

Prerequisites: Node.js 20+ and Python 3.9+. Run these commands from the repository root.

macOS / Linux:

```sh
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
npm ci
```

Windows PowerShell:

```powershell
py -3.9 -m venv backend/.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
npm ci
```

Start two terminals in the repository root. In terminal 1, activate the virtual environment as above, then run:

```sh
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In terminal 2:

```sh
npm run dev
```

Open the URL printed by Vite (normally `http://127.0.0.1:5173`). The UI calls the API through Vite's local proxy. For production-mode serving, build the frontend with `npm run build`, then start Uvicorn with the command above and open `http://127.0.0.1:8000`.

To check the scanner rules against the synthetic fixtures without touching your own data, run:

```sh
backend/.venv/bin/python backend/verify_phase2.py
```

It uses a temporary database, scans `backend/fixtures/synthetic/`, and asserts dated-update ordering, conflict handling, excluded directories, and that fixture files are byte-for-byte unchanged.

To check the model layer without a network or an API key, run:

```sh
backend/.venv/bin/python backend/verify_phase3.py
```

It drives the adapters with a fake transport and asserts that provider failures, malformed output, unknown citations, quotes not present in the source, invented dates, and rule/model disagreements are all visible and never replace the last accepted state. It also checks that the key stays out of request bodies and API responses.

The service binds to loopback only. Local runtime state, virtual environments, dependencies, build output, logs, SQLite files, and `.env` files are excluded from Git. SQLite data is written to the OS user data directory (`~/Library/Application Support/ProjectProgressDashboard` on macOS, `%LOCALAPPDATA%\\ProjectProgressDashboard` on Windows, or `$XDG_DATA_HOME/ProjectProgressDashboard` on Linux). Phase 2 reads Markdown from registered folders in read-only mode. A Windows path can be entered while developing on macOS; it is saved as text and is not accessed until the app runs on a computer that can reach that path.

## Documents

- [PRODUCT.md](PRODUCT.md) — users, workflow, requirements, and MVP boundaries.
- [ARCHITECTURE.md](ARCHITECTURE.md) — system structure, data flow, privacy, and implementation choices.
- [ROADMAP.md](ROADMAP.md) — technical baseline, phases, and exit criteria.
- [AGENTS.md](AGENTS.md) — project safety and development rules.

## Privacy

The dashboard does not host project data, upload it to a dashboard service, or collect telemetry. Project Markdown may be sent to the model endpoint the user configures. Users must configure an endpoint appropriate for their data. For the owner's intended setup, this is an internally deployed company model API.

---

# 项目进度看板

一个本地优先、开源的看板，用于从 Markdown 文档读取项目排期与阶段进展。

## 当前状态

Phase 0（跨平台基础）、Phase 1（项目登记与日历）、Phase 2（只读 Markdown 证据扫描）与 Phase 3（OpenAI／Anthropic 适配器与复核规则）已在 macOS 实现并检查，Windows 上的运行行为仍待验证。

## 模型复核怎么做

日期与新鲜度仍由本地规则决定，模型只作为第二意见：

- 只发送编号后的证据包：最多 14 条、约 6000 字符，来源都是相对路径，不发送整份文档。
- 模型必须返回 JSON，并给出证据编号和在该证据里逐字出现的引文。后端会拒绝：不存在的证据编号、原文里找不到的引文、引文里没有的阶段编号、证据里没有写出的排期日期。
- 只有规则与模型一致时才推进状态。分歧、模型自报冲突、格式错误或接口失败都会在界面上明确显示为“待确认”或“模型未确认”，并保留上次已接受状态。
- 排期日期永远只是提议，用户接受后才改日历。
- API 密钥保存在仓库之外（有 `keyring` 时用系统凭证库，否则用应用数据目录下权限 0600 的文件），接口只返回掩码，不返回密钥。

## 扫描器读取什么

- 只读 Markdown，且只在已登记的项目文件夹内读取；跳过 `.git`、`node_modules`、`dist`、`build`、依赖／缓存与隐藏目录。
- 抽取带明确日期的进展、Phase 顺序与当前阶段、文档中记录的阶段日期、测试标记和候选排期变化，并始终保留来源路径、标题与简短原文。
- 日期必须带年份；含计划措辞的语句和晚于今天的日期都不会让项目显得更新。文件修改时间从不参与判断。
- 文档互相冲突时标记“待确认”，保留上次已接受状态，不做猜测。
- 文件只以只读方式打开，扫描器绝不写入、重命名或删除项目文件夹内的任何文件。

运行 `backend/.venv/bin/python backend/verify_phase2.py` 可用合成样例自检上述规则，使用临时数据库，不会触碰你自己的数据。

运行 `backend/.venv/bin/python backend/verify_phase3.py` 可用假传输层自检模型层，不需要网络或 API 密钥：接口失败、格式错误、证据编号不存在、引文对不上、凭空日期、与规则分歧都会显式暴露，且不会覆盖上次已接受状态；同时检查密钥不出现在请求体和接口响应里。

## 技术路线

- React + TypeScript + Vite 前端。
- Python + FastAPI + Uvicorn 本地后端。
- SQLite 本地存储。
- 支持 OpenAI 与 Anthropic API 适配器。
- 仅监听本机，不做云端托管或遥测。

详见 [ROADMAP.md](ROADMAP.md) 中的分阶段实现计划，以及 [ARCHITECTURE.md](ARCHITECTURE.md) 中的系统边界。

## MVP

- 通过输入本地文件夹路径、项目名、计划开始日期和结束日期来添加项目。
- 在按月展示的时间轴上显示所有项目，每个项目用覆盖计划日期的彩色色块表示。
- 打开项目详情页，查看 Phase 时间线、最近一次有日期的进展、项目简介和来源文档。
- 只读取 Markdown 文件，不修改项目文件。
- 每天首次开机时自动巡检一次，并提供手动刷新按钮。
- 支持用户配置 OpenAI 和 Anthropic API 格式。看板和数据保存在本地，模型请求只发送到用户配置的 API。

## 文档

- [PRODUCT.md](PRODUCT.md) — 用户、工作流程、需求和 MVP 范围。
- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统结构、数据流、隐私和技术选择。
- [ROADMAP.md](ROADMAP.md) — 技术基线、实施阶段和验收标准。
- [AGENTS.md](AGENTS.md) — 项目安全和开发规则。

## 隐私

看板不托管项目数据、不把文件上传到看板服务，也不采集遥测。项目 Markdown 可能会发送到用户配置的模型 API。用户应选择适合其项目数据的 API。项目发起人的预期使用方式是连接公司内部部署的大模型 API。
