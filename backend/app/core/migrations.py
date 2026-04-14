"""Lightweight schema sync for SQLite.

We use `Base.metadata.create_all()` to create new tables on startup. That's
enough for fresh installs, but it never *alters* existing tables — so whenever
a column is added to an existing model (e.g. `McpApiKey.scope_mode`), an
existing database gets stuck with the old schema and every INSERT breaks.

Rather than pulling in Alembic for what are almost always single-column
additions, this module does one thing: on startup it walks every SQLAlchemy
model, compares the model's columns to the live table, and `ALTER TABLE ADD
COLUMN` for anything missing. Idempotent, safe to run on every boot.

Caveats:
- SQLite can't add a NOT NULL column without a DEFAULT. If you add such a
  column and have existing rows, the ALTER will fail loudly — write a real
  migration in that case. Make new columns nullable or give them a default.
- SQLite ADD COLUMN doesn't create indexes or unique constraints. If you need
  those, add them manually or drop/recreate the table.
- This only handles columns added to existing tables. Renames, type changes,
  and drops still need a real migration.
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import Column

logger = logging.getLogger(__name__)


def _compile_column_ddl(column: Column, dialect) -> str:
    """Build an `ADD COLUMN` DDL fragment for a single column."""
    col_type = column.type.compile(dialect=dialect)
    parts = [f'"{column.name}"', col_type]

    # NULL-ability: default to nullable unless the column explicitly says NOT NULL
    # AND ships with something that can populate existing rows.
    has_server_default = column.server_default is not None
    if not column.nullable and not has_server_default:
        # SQLite rejects ADD COLUMN ... NOT NULL without a DEFAULT. Downgrade to
        # NULL here so existing rows survive; the model's Python default will
        # populate new rows. Operators who really need NOT NULL on existing data
        # should write a hand-rolled migration.
        logger.warning(
            "migrations: column %s.%s is NOT NULL with no server_default; "
            "adding as NULLABLE to keep existing rows valid",
            column.table.name,
            column.name,
        )
    elif not column.nullable:
        parts.append("NOT NULL")

    if has_server_default:
        # column.server_default.arg may be a string, a TextClause, or a callable
        default = column.server_default.arg
        if hasattr(default, "text"):
            default_sql = default.text
        else:
            default_sql = str(default)
        parts.append(f"DEFAULT {default_sql}")

    return " ".join(parts)


def _table_columns(engine: Engine, table_name: str) -> set[str]:
    insp = inspect(engine)
    return {c["name"] for c in insp.get_columns(table_name)}


def _existing_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def sync_schema(engine: Engine, metadata) -> list[str]:
    """Walk every table in `metadata` and add any columns missing from the DB.

    Returns a list of human-readable change descriptions, mainly for logs/tests.
    """
    changes: list[str] = []
    existing = _existing_tables(engine)
    dialect = engine.dialect

    for table in metadata.sorted_tables:
        if table.name not in existing:
            # create_all() will have taken care of this one.
            continue

        db_cols = _table_columns(engine, table.name)
        missing: Iterable[Column] = [c for c in table.columns if c.name not in db_cols]
        if not missing:
            continue

        with engine.begin() as conn:
            for column in missing:
                ddl_fragment = _compile_column_ddl(column, dialect)
                stmt = f'ALTER TABLE "{table.name}" ADD COLUMN {ddl_fragment}'
                try:
                    conn.execute(text(stmt))
                    changes.append(f"{table.name}.{column.name}")
                    logger.info("migrations: added column %s.%s", table.name, column.name)
                except Exception as exc:  # noqa: BLE001
                    # Log and keep going — one broken column shouldn't block app start.
                    logger.error(
                        "migrations: failed to add %s.%s (%s): %s",
                        table.name,
                        column.name,
                        stmt,
                        exc,
                    )

    if changes:
        logger.info("migrations: applied %d column additions: %s", len(changes), ", ".join(changes))
    else:
        logger.debug("migrations: schema already in sync")

    return changes
