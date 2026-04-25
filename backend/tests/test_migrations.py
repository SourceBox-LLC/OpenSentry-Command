"""Tests for `app.core.migrations`.

Each test uses its own throwaway in-memory engine so the orphan-table sweep
doesn't interfere with the shared session fixture used by the rest of the
suite.  ``conftest.py`` sets DATABASE_URL=:memory: globally, but the helpers
under test take an explicit ``engine`` argument, so we don't need to touch
the global one.
"""

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import drop_orphan_tables


def _engine_with(table_names: list[str]):
    """Build a fresh in-memory engine and create the given (empty) tables."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        for name in table_names:
            conn.execute(text(f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY)'))
    return engine


# ── drop_orphan_tables ─────────────────────────────────────────────


def test_drop_orphan_tables_removes_known_orphan_when_present():
    """If `webhook_endpoints` exists from a prior deploy, the sweep drops it."""
    engine = _engine_with(["webhook_endpoints", "cameras"])

    dropped = drop_orphan_tables(engine)

    assert dropped == ["webhook_endpoints"]
    remaining = set(inspect(engine).get_table_names())
    assert "webhook_endpoints" not in remaining
    # Non-orphan tables are untouched.
    assert "cameras" in remaining


def test_drop_orphan_tables_idempotent_when_orphan_already_gone():
    """Second boot — the orphan was dropped on a previous boot — must noop cleanly."""
    engine = _engine_with(["cameras"])  # no webhook_endpoints

    dropped = drop_orphan_tables(engine)

    assert dropped == []
    # cameras still there
    assert "cameras" in set(inspect(engine).get_table_names())


def test_drop_orphan_tables_survives_when_no_tables_exist():
    """Fresh-install path — empty DB shouldn't crash the sweep."""
    engine = create_engine("sqlite:///:memory:")

    dropped = drop_orphan_tables(engine)

    assert dropped == []
