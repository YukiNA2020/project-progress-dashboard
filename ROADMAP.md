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

**Status:** Product docs completed; technical implementation not started.

- Create a Vite React + TypeScript frontend and a Python FastAPI backend in this repository.
- Add a health endpoint and a minimal UI that calls it through a loopback-only local API.
- Configure development mode (Vite frontend + local API) and production mode (FastAPI serves the built frontend).
- Add dependency manifests and lockfiles; exclude `.env`, SQLite files, logs, caches, and local project data from Git.
- Document macOS development commands and Windows setup commands.
- Keep user data outside the source repository.

**Exit:** The app starts locally on macOS and Windows from documented commands, binds only to loopback, and displays backend health. No project folder or model API is needed.

## Phase 1 — Project registry and calendar UI

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
