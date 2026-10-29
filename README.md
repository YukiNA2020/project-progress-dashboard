# Project Progress Dashboard

A local-first, open-source dashboard for tracking project schedules and phase progress from Markdown documents.

## Status

Product discovery is documented. Implementation has not started.

## MVP

- Add a project with its local folder path, name, planned start date, and planned end date.
- Show all projects on a month-oriented calendar timeline. Each project is a distinct color bar spanning its planned dates, ordered by start date.
- Open a project detail page from its bar. Show a concise project summary, all phases, current phase, recent dated progress, and source documents.
- Read Markdown files only. Never modify project files.
- Run one automatic scan on the first computer startup each day, with a manual refresh button.
- Support configurable OpenAI and Anthropic API formats. Keep the app and its data local; make model requests only to the endpoint configured by the user.

## Documents

- [PRODUCT.md](PRODUCT.md) — users, workflow, requirements, and MVP boundaries.
- [ARCHITECTURE.md](ARCHITECTURE.md) — system shape, data flow, privacy, and open technical choices.
- [ROADMAP.md](ROADMAP.md) — implementation phases and acceptance criteria.
- [AGENTS.md](AGENTS.md) — project safety and development rules.

## Privacy

The dashboard does not host project data, upload it to a dashboard service, or collect telemetry. Project Markdown may be sent to the model endpoint the user configures. Users must configure an endpoint appropriate for their data. For the owner's intended setup, this is an internally deployed company model API.
