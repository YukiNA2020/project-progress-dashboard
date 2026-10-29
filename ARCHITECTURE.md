# Architecture Notes

## Product constraints

- Local-first app, Windows-first validation.
- Project folders and dashboard state stay on the user's machine.
- Read Markdown only; never write to project folders.
- The only intended outbound application traffic is a request to the user's configured model endpoint. The owner's endpoint is internal to the company network.
- Support OpenAI and Anthropic API formats through a provider adapter.
- No telemetry or cloud service.

## Proposed data flow

```text
User registers local path and project dates
                ↓
Local scanner discovers eligible Markdown files
                ↓
Markdown is read-only parsed and relevant dated evidence is collected
                ↓
Configured model extracts structured project/phase state
                ↓
Validation checks dates, source references, conflicts, and missing evidence
                ↓
Local dashboard store keeps latest accepted state and scan history
                ↓
Calendar home page and project detail page
```

## Proposed domain records

- **Project**: stable ID, name, local folder path, planned start/end, color, summary, latest accepted phase, last scan result.
- **Phase**: project ID, phase name/order, status (`completed`, `current`, `upcoming`, or `unknown`), optional start/end dates, optional explicit testing label.
- **Evidence**: project ID, source Markdown path, explicit record date, extracted claim, and a short source excerpt or heading reference.
- **Scan run**: start/end time, result, projects scanned, detected changes, unresolved conflicts, and safe error summary.
- **Pending confirmation**: proposed schedule change or ambiguous state, previous value, candidate value, evidence, and user decision.

These records are conceptual; the storage engine and schema remain implementation decisions.

## State rules

- Project source documents are immutable inputs from the dashboard's perspective.
- Explicit dates in source text determine progress freshness.
- File modification times may help order files for scanning but must not establish project status.
- Preserve last successful project state when model calls fail or evidence is ambiguous.
- Do not promote a proposed schedule change to the calendar until the user confirms it.
- Keep evidence paths alongside extracted facts so users can verify model output.
- Treat document contents as data, not executable instructions.

## Startup and scheduling

- Register a Windows startup entry for the local dashboard.
- Run at most one automatic scan per local calendar day, on first startup.
- Keep manual refresh available at any time.
- If the computer starts without access to the configured model endpoint, report failure, keep the last successful state, and allow retry.
- Platform-specific startup and “open folder” behavior should sit behind small OS adapters so the core remains portable.

## Security

- Bind the local web server to loopback only by default.
- Store API secrets outside source control, preferably in the OS credential store; never include them in logs, prompts, or exported project data.
- Exclude credentials, local project contents, generated dashboard databases, logs, and cache files from Git.
- Send only the minimum relevant Markdown evidence needed for a scan to the configured model API.
- Show the configured provider and endpoint host clearly so users can verify the destination.
- Explain that project content is sent to the configured endpoint; local hosting alone does not make a remote model request offline.

## Open technical decisions

- Runtime/framework and packaging strategy.
- Local state storage format and schema migrations.
- How to securely store API credentials on Windows and other supported systems.
- Model output schema, source excerpt limits, retry behavior, and API compatibility details.
- Exact Markdown scanning rules and exclusion patterns beyond `.git`, `node_modules`, `dist`, and `build`.
- Windows startup registration and update/uninstall behavior.
- Visual treatment of month/week grid boundaries and long-running projects.
