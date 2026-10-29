# Roadmap

## Phase 0 — Product baseline

**Status:** Documented.

- Freeze the local-first product boundary and read-only source rule.
- Define home calendar, project detail page, progress freshness, ambiguity, and failure behavior.
- Record Windows-first scope and API provider requirements.

**Exit:** Product scope and open technical decisions are reviewed.

## Phase 1 — Local project registry and timeline

- Create a local app shell and project registration form.
- Store project name, local path, planned start/end dates, and color.
- Render the month-oriented home calendar ordered by project start date.
- Navigate from a project bar to its detail page.

**Exit:** A user can register synthetic projects and inspect timeline behavior without an AI API.

## Phase 2 — Markdown evidence scanner

- Read Markdown files under registered project folders.
- Exclude dependency/build/system directories, including `.git`, `node_modules`, `dist`, and `build`.
- Identify dated status records, phases, summaries, schedule dates, and testing labels.
- Preserve source paths and excerpts for review.

**Exit:** Synthetic fixtures demonstrate correct evidence capture and explicit unknown/conflict states.

## Phase 3 — Model providers and review rules

- Add configurable OpenAI and Anthropic API adapters.
- Keep credentials in local secure storage and provide a connection check.
- Request structured state with evidence references.
- Validate model output and flag missing/conflicting evidence.
- Require confirmation before changing planned project dates.

**Exit:** Provider failures, invalid output, and conflicting source records preserve the last successful state and are visible to the user.

## Phase 4 — Startup automation and daily summary

- Start the dashboard on Windows login.
- Run one automatic scan per local calendar day.
- Add manual refresh, scan summary, failure message, timestamp, and retry.
- Add “open project folder” action.

**Exit:** Restarting Windows does not cause duplicate same-day scans; manual retry works after failure.

## Phase 5 — Two-week personal validation

- Use the dashboard with a small set of real, authorized local project folders.
- Track time to understand project status and corrections to extracted phase/status.
- Review false positives, missed updates, and whether evidence links are sufficient.

**Exit:** Decide which extraction rules and UI details to revise before broader release.

## Deferred

- macOS/Linux startup integration and release verification.
- PDF, Word, spreadsheet, source-control, or issue-tracker ingestion.
- Multi-user synchronization, cloud hosting, telemetry, and collaboration.
- Automatic source document edits or unconfirmed schedule changes.
