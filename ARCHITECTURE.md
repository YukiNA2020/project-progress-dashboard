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
