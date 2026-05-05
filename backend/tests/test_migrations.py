"""Tests for `app.core.migrations`.

Each test uses its own throwaway in-memory engine so the orphan-table sweep
doesn't interfere with the shared session fixture used by the rest of the
suite.  ``conftest.py`` sets DATABASE_URL=:memory: globally, but the helpers
under test take an explicit ``engine`` argument, so we don't need to touch
the global one.

Note: ``drop_orphan_tables`` and ``sanitize_existing_codecs`` are no longer
in the boot path (pulled 2026-05-05 once their respective fixes had washed
through prod).  These tests still pin the helpers' behaviour for
snapshot-restore + future-orphan use cases — see module docstring in
``app/core/migrations.py``.
"""

from sqlalchemy import create_engine, inspect, text

from app.core import migrations
from app.core.migrations import drop_orphan_tables


def _engine_with(table_names: list[str]):
    """Build a fresh in-memory engine and create the given (empty) tables."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        for name in table_names:
            conn.execute(text(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY)'))
    return engine


# ── drop_orphan_tables ─────────────────────────────────────────────
#
# The current ``_ORPHAN_TABLES`` is empty — the only historical entry
# (``webhook_endpoints``) was dropped from prod and removed from the
# list on 2026-05-05.  The tests below inject a synthetic orphan via
# monkeypatch so they exercise the drop mechanism without binding to
# whatever entries happen to be in the list right now.  When a new
# orphan is added, the existing tests continue to cover it correctly.


def test_drop_orphan_tables_removes_present_orphan(monkeypatch):
    """If a registered orphan table exists, the sweep drops it.  Synthetic
    orphan injected via monkeypatch so the test keeps passing whether or
    not ``_ORPHAN_TABLES`` has any current entries."""
    monkeypatch.setattr(
        migrations, "_ORPHAN_TABLES",
        (("synthetic_orphan", "test fixture, never shipped"),),
    )
    engine = _engine_with(["synthetic_orphan", "cameras"])

    dropped = drop_orphan_tables(engine)

    assert dropped == ["synthetic_orphan"]
    remaining = set(inspect(engine).get_table_names())
    assert "synthetic_orphan" not in remaining
    # Non-orphan tables are untouched.
    assert "cameras" in remaining


def test_drop_orphan_tables_idempotent_when_orphan_already_gone(monkeypatch):
    """Second boot — the orphan was dropped on a previous boot — must noop
    cleanly.  Same synthetic-orphan injection so the test isn't coupled
    to the live ``_ORPHAN_TABLES`` contents."""
    monkeypatch.setattr(
        migrations, "_ORPHAN_TABLES",
        (("synthetic_orphan", "test fixture, never shipped"),),
    )
    engine = _engine_with(["cameras"])  # synthetic_orphan absent

    dropped = drop_orphan_tables(engine)

    assert dropped == []
    assert "cameras" in set(inspect(engine).get_table_names())


def test_drop_orphan_tables_survives_when_no_tables_exist():
    """Fresh-install path — empty DB shouldn't crash the sweep, regardless
    of what ``_ORPHAN_TABLES`` happens to contain."""
    engine = create_engine("sqlite:///:memory:")

    dropped = drop_orphan_tables(engine)

    assert dropped == []


def test_drop_orphan_tables_with_empty_registry_is_noop():
    """Current production state: ``_ORPHAN_TABLES`` is empty.  Helper
    must return ``[]`` cleanly without touching anything in the DB."""
    engine = _engine_with(["cameras", "settings", "audit_log"])

    dropped = drop_orphan_tables(engine)

    assert dropped == []
    # Nothing in the DB was touched.
    remaining = set(inspect(engine).get_table_names())
    assert remaining == {"cameras", "settings", "audit_log"}
