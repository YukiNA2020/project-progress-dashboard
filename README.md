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

## Documents

- [PRODUCT.md](PRODUCT.md) — users, workflow, requirements, and MVP boundaries.
- [ARCHITECTURE.md](ARCHITECTURE.md) — system structure, data flow, privacy, and implementation choices.
- [ROADMAP.md](ROADMAP.md) — technical baseline, phases, and exit criteria.
- [AGENTS.md](AGENTS.md) — project safety and development rules.

## Privacy

The dashboard does not host project data, upload it to a dashboard service, or collect telemetry. Project Markdown may be sent to the model endpoint the user configures. Users must configure an endpoint appropriate for their data. For the owner's intended setup, this is an internally deployed company model API.
