# Product Definition

## Problem

The user tracks several active projects and dislikes maintaining a status table manually. Project progress, phase, testing state, and dates are already recorded in project folders, commonly across Markdown files such as `README.md`, `STATUS.md`, `TESTING.md`, and `ROADMAP.md`. The dashboard should read those records and make overall schedules easy to scan.

## Target user

First: one person running a local dashboard on Windows and using an internally deployed model API. The repository will be open source so others can self-host it and configure their own model API.

## Primary scenario

1. Add a project by entering its local folder path, project name, planned start date, and planned end date.
2. At computer startup, the dashboard launches and scans once that day. The user can also trigger a scan manually.
3. The dashboard reads the project's Markdown files and extracts the latest explicitly dated progress, current phase, phase dates when present, and relevant testing state.
4. The home calendar shows all projects as colored bars across their planned dates, ordered by start date.
5. Clicking a bar navigates to a project detail page with the project's phase timeline, latest progress, summary, and source references.
6. The user reviews the scan summary and resolves ambiguous states or schedule changes.

## User interface

### Home page

- Month-oriented calendar timeline, with a time axis left to right and projects ordered vertically by start date.
- Each project has a distinct color bar spanning its planned start and end dates. The bar identifies the current phase.
- Clicking a bar navigates to the project's detail page.
- A compact scan summary lists detected status changes, schedule changes, and items needing confirmation. If nothing changed, show that the project states are unchanged.
- Show scan failure and timestamp when a scan fails; retain the last successful state and offer manual retry.
- Provide a manual refresh button.

### Project detail page

- Show a concise overview derived from the project's README, the folder path, latest dated progress, and source Markdown references.
- Show the complete phase sequence. Completed phases are gray, the current phase is bold, and future phases use normal styling.
- If the current phase is explicitly marked as testing, show “Testing” beside it.
- Show phase start and end dates when documented. Missing dates remain unknown; do not infer them.
- Provide an action to open the local project folder.

## Progress and schedule rules

- Use explicit dates written in progress records to determine freshness; do not use file modification times as the status timestamp.
- The newest explicitly dated record is the current candidate state. Preserve links or paths to its source documents and the record date.
- If documents conflict, the current phase cannot be established, or evidence is missing, mark the project “Needs confirmation” and retain the last known state. Do not guess.
- The project start and end dates entered during setup define the initial overall bar.
- If a document reports a changed planned date, show old and new dates as a schedule change and wait for user confirmation before changing the timeline.
- Dashboard state may be updated; project source documents are read-only.

## API and privacy

- Support both OpenAI and Anthropic request formats, with user-configured API base URL, secret, and model name.
- Keep credentials in local configuration or the operating system's secure credential store; never commit them or log them.
- Do not host the dashboard or project data in the cloud. Do not upload files to a dashboard service. Do not add telemetry.
- Model requests go only to the endpoint configured by the user. A local application can still make network requests to that endpoint; the owner's intended endpoint is the company's internal model API.
- The open-source README and setup flow must explain that users are responsible for choosing an endpoint suitable for their project data.

## MVP scope

- Windows-first startup behavior and local folder navigation.
- Cross-platform core where practical; macOS/Linux support is not part of the first verified release.
- Explicit project registration by local path; no whole-disk discovery.
- Markdown-only source reading.
- Local dashboard state and source references.
- Daily first-start scan, manual refresh, change summary, failure state, and retry.

## Non-goals

- Editing project Markdown or other source files.
- Cloud hosting, cloud synchronization, or dashboard telemetry.
- Parsing PDF, Word, spreadsheets, or source code.
- Automatically changing planned dates without confirmation.
- Treating AI inference without dated evidence as a verified project status.
- Multi-user collaboration in the first release.

## Validation

Run a two-week personal trial. Check whether the dashboard makes all current phases and schedules quick to understand, and record how often status extraction requires correction. Set quantitative thresholds after collecting baseline usage rather than inventing an accuracy target before real project documents are evaluated.
