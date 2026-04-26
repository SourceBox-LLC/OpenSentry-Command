# Command Center docs

Supplementary documentation for SourceBox Sentry Command Center. The top-level `README.md` is the user-facing install + operation guide; `AGENTS.md` is the developer / LLM-facing architecture reference. The docs in this tree cover the things that don't fit cleanly in either.

## [LAUNCH_HANDOFF.md](LAUNCH_HANDOFF.md) — what you need to do before paying customers

Twelve user-only items (Clerk prod keys, backup restore test, lawyer signoff, status page vendor, etc.) that every code-side launch blocker has been closed against. Start here if you're driving toward launch.

## Architecture Decision Records (`docs/adr/`)

One decision per file, numbered in order. ADRs capture the *why* behind a non-obvious choice so future maintainers don't re-litigate it. Format follows Michael Nygard's template (Context / Decision / Consequences).

- [0001-sync-schema-vs-alembic.md](adr/0001-sync-schema-vs-alembic.md) — why we don't use Alembic for backend schema migrations
- [0002-viewer-hour-billing.md](adr/0002-viewer-hour-billing.md) — why monthly viewer-hours, not camera count, are the binding tier limit

## Runbooks (`docs/runbooks/`)

Step-by-step responses to incidents that recur often enough to be
worth writing down. Optimised for being read under pressure — short
sections, command-oriented, not narrative.

- [ON_CALL.md](runbooks/ON_CALL.md) — eight scenarios covering Sentry
  alerts, customer-reported camera/stream outages, DB issues,
  multi-customer incidents, suspected breaches, deletion requests,
  and pre-deploy sanity checks. Has an append-only incident log
  section to populate as we respond to real ones.

## Legal templates (`docs/legal/`)

Working drafts of customer-facing legal documents. Each is marked `DRAFT — NOT FOR EXECUTION` at the top and **must** be reviewed by counsel before it is sent to a customer or relied on as binding. They live in source control so the engineering reality and the legal text don't drift apart unnoticed.

- [DPA.md](legal/DPA.md) — Data Processing Agreement template, including SCC parameter annexes for EEA / UK transfers.
- [SUB_PROCESSORS.md](legal/SUB_PROCESSORS.md) — public sub-processor list with notice policy.

## Writing new docs

- **ADR** — when you make a decision that was hard to make, or that someone else will almost certainly re-argue. Write it *while the tradeoffs are fresh*, not six months later.
- **Runbook** — when you catch yourself pasting the same sequence of commands into more than one support thread. Cheap to write, saves time forever. (None yet — add `docs/runbooks/` if/when one shows up.)
- **Legal templates** — `docs/legal/` is for drafts that capture engineering truth; the lawyer-reviewed binding version lives elsewhere (a signed PDF in your records system). Update the draft *whenever* the underlying processing changes (new sub-processor, new data category, new retention window) so the lawyer review stays small.
- **README / AGENTS** — these two are the primary docs and get updated in-place with every feature. Don't fork them into `docs/`.
