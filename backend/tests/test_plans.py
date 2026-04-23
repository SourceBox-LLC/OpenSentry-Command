"""Unit tests for ``app.core.plans``."""

from app.core.plans import wire_plan_slug


def test_wire_plan_slug_strips_org_suffix():
    """The internal ``free_org`` slug must render as ``free`` on the wire
    so the CloudNode pill badge reads ``[ FREE ]`` rather than
    ``[ FREE_ORG ]``."""
    assert wire_plan_slug("free_org") == "free"


def test_wire_plan_slug_passes_through_clean_slugs():
    """Paid plan slugs have no suffix and must pass through untouched."""
    assert wire_plan_slug("pro") == "pro"
    assert wire_plan_slug("business") == "business"


def test_wire_plan_slug_lowercases_and_trims():
    """Defensive: upstream sources have occasionally leaked casing/whitespace
    into stored plan strings. Normalize so the node always sees canonical
    lowercase."""
    assert wire_plan_slug("  PRO  ") == "pro"
    assert wire_plan_slug("Free_Org") == "free"


def test_wire_plan_slug_passes_unknown_tiers_through():
    """A future ``enterprise`` tier must render in the node UI even before
    we ship a node update — the badge falls back to the dimmed default
    rather than being hidden."""
    assert wire_plan_slug("enterprise") == "enterprise"


def test_wire_plan_slug_handles_empty_and_none():
    """Empty inputs collapse to ``free`` so the caller never has to guard
    against ``None`` before putting the value on the wire."""
    assert wire_plan_slug("") == "free"
    assert wire_plan_slug("   ") == "free"
    # The signature is ``str`` but the helper is robust to callers that
    # forget to coalesce a missing Setting value.
    assert wire_plan_slug(None) == "free"  # type: ignore[arg-type]
