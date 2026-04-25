# ADR 0001: Lightweight `sync_schema` instead of Alembic

- **Status:** Accepted
- **Date:** 2026-04
- **Deciders:** Command Center maintainers

## Context

Most schema changes Command Center has shipped over the last year are **single-column additions** to existing models — `Camera.video_codec`, `McpApiKey.scope_mode`, `CameraNode.last_error`, `Setting.payment_past_due_at`, `Camera.disabled_by_plan`, `OrgMonthlyUsage.viewer_seconds`, etc. SQLAlchemy's `Base.metadata.create_all()` handles fresh installs but never *alters* existing tables, so any deploy that adds a column to an existing model used to break every INSERT against that table on production.

The conventional fix is Alembic. It's a real migration tool with autogeneration, ordering, and rollback. We considered it and turned it down for now.

What Alembic buys you that we don't have:
- True up/down migrations (we only do up).
- Type changes, renames, drops, indexes, unique constraints.
- A canonical history that's harder to fork between environments.
- Autogenerate diffs from the model graph.

What Alembic costs:
- Every model change becomes a code change *plus* a generated revision file that has to be reviewed and committed. Easy to forget.
- Migration script ordering across long-running branches gets hairy fast.
- A new dev needs to learn the workflow on top of SQLAlchemy itself.
- Autogeneration produces unsafe SQL surprisingly often (column-default coercion, JSON columns, computed columns) that you have to hand-edit anyway.

For a backend whose schema changes are 95% "add a nullable column," that overhead doesn't pay for itself.

## Decision

`backend/app/core/migrations.py` ships a single function — `sync_schema(engine, metadata)` — that runs on every app boot:

1. Walk every table in `Base.metadata`.
2. For tables that already exist, compare the model's columns against the live `PRAGMA table_info()`.
3. For each missing column, emit `ALTER TABLE ... ADD COLUMN ...`. Nullable columns and columns with `server_default` go in cleanly; NOT-NULL-without-default columns get downgraded to nullable with a warning (SQLite limitation; the model's Python default still populates new rows).
4. Log every column added; otherwise log nothing on a clean boot.

Idempotent. Safe to run on every container restart. Tested in `tests/test_migrations.py`.

The companion function `sanitize_existing_codecs()` is a one-shot **data** migration that rewrites broken `avc1.*e00*`-class codec strings — a place you'd reach for Alembic in a more mature codebase. We co-locate it here so the migration story is one file, not two systems.

## Consequences

**Positive:**
- One file, ~120 lines, ~zero ongoing maintenance.
- New columns just need to be added to the model. No revision file, no `alembic upgrade head` step, no out-of-order migration anxiety.
- A long-running feature branch can be merged without rebasing migrations against the main branch's revision tree.
- The schema state of production matches the model definition, *always* — there's no "you forgot to run migrations" footgun.
- Tests run against the same code path as production (`Base.metadata.create_all` + `sync_schema`), so a column being missing in one place but not another is impossible.

**Negative:**
- **Renames, type changes, and drops still need hand-rolled migrations.** We have one in flight: the `webhook_endpoints` table (orphaned by commit `d4dd2db`'s outbound-webhook revert) doesn't go away just because the model went away. We add an explicit `drop_orphan_tables()` sweep when we need it; that's the same effort as one Alembic revision.
- No down migration. If a deploy ships a bad column we have to roll the deploy itself, not the migration.
- No native indexes or unique constraints via the sweep. Adding one of those means writing the SQL by hand.

**Neutral:**
- Switching to Alembic later is straightforward — `alembic stamp head` against the current production schema, then start writing revisions from there. We aren't painting ourselves into a corner.

## Revisiting this decision

Re-evaluate if any of the following become true:

- We routinely need **type changes** or **renames** (more than ~one a quarter).
- We need rollback for forward migrations — i.e. ops wants to deploy → see a problem → revert without restoring from backup.
- We add a second backend service that shares the same database — then we need a single source of truth for "what version of the schema is live."
- We grow past SQLite onto Postgres in a way that exposes schema-management gaps the sync_schema approach doesn't catch (PG-specific types, tablespaces, extensions, etc.).

In any of those cases, switching is mechanical: `pip install alembic`, `alembic init`, `alembic stamp head`, delete `migrations.py` (or keep `sanitize_existing_codecs` as a one-off until done).

## References

- `backend/app/core/migrations.py` — the implementation.
- `backend/app/main.py` — `Base.metadata.create_all(...)` + `sync_schema(...)` are called in order at module load.
- Michael Nygard, *Documenting Architecture Decisions* (2011) — the format of this file.
