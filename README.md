# Project Progress Dashboard

A local-first, open-source dashboard for tracking project schedules and phase progress from Markdown documents.

## Status

Product and technical roadmap are documented. Implementation is planned to start on macOS and continue on Windows from the same repository.

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

The service binds to loopback only. Local runtime state, virtual environments, dependencies, build output, logs, SQLite files, and `.env` files are excluded from Git. SQLite data is written to the OS user data directory (`~/Library/Application Support/ProjectProgressDashboard` on macOS, `%LOCALAPPDATA%\\ProjectProgressDashboard` on Windows, or `$XDG_DATA_HOME/ProjectProgressDashboard` on Linux). Phase 1 stores only the metadata explicitly entered in the form; it does not read or modify project folders. You can enter a Windows path while developing on macOS; the path is saved as text and is not checked for existence.

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

产品定义和技术路线已完成。计划先在 macOS 开发，再从同一 GitHub 仓库在 Windows 上继续。

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
