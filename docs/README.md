# Command Center docs

Supplementary documentation for SourceBox Sentry Command Center. The top-level `README.md` is the user-facing install + operation guide; `AGENTS.md` is the developer / LLM-facing architecture reference. The docs in this tree cover the things that don't fit cleanly in either.

## Architecture Decision Records (`docs/adr/`)

One decision per file, numbered in order. ADRs capture the *why* behind a non-obvious choice so future maintainers don't re-litigate it. Format follows Michael Nygard's template (Context / Decision / Consequences).

- [0001-sync-schema-vs-alembic.md](adr/0001-sync-schema-vs-alembic.md) — why we don't use Alembic for backend schema migrations
- [0002-viewer-hour-billing.md](adr/0002-viewer-hour-billing.md) — why monthly viewer-hours, not camera count, are the binding tier limit

## Writing new docs

- **ADR** — when you make a decision that was hard to make, or that someone else will almost certainly re-argue. Write it *while the tradeoffs are fresh*, not six months later.
- **Runbook** — when you catch yourself pasting the same sequence of commands into more than one support thread. Cheap to write, saves time forever. (None yet — add `docs/runbooks/` if/when one shows up.)
- **README / AGENTS** — these two are the primary docs and get updated in-place with every feature. Don't fork them into `docs/`.
