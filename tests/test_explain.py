"""explain_recompile against the same incremental_before/after fixtures
tests/test_incremental_report.py already exercises -- one fixture pair,
another real report derived from it.
"""

from epc.explain import explain_recompile, render_trace
from epc.normalizer import normalize
from epc.parser import parse

BEFORE = normalize(parse(open("tests/fixtures/incremental_before.yaml").read()))
AFTER = normalize(parse(open("tests/fixtures/incremental_after.yaml").read()))
ORDER = ["network.vpc", "storage.bucket1", "storage.bucket2", "secret.dbPassword", "compute.appServer", "governance.catalog"]
BEFORE.compute_hashes(ORDER)
AFTER.compute_hashes(ORDER + ["storage.archive"])


def test_edited_node_reports_its_own_property_diff():
    reason = explain_recompile(BEFORE, AFTER, "secret.dbPassword")
    assert reason.recompiled is True
    assert reason.own_properties_changed is True
    assert reason.property_diff == {"rotation": (90, 30)}
    assert reason.caused_by == []


def test_cascaded_node_points_at_its_changed_dependency_not_itself():
    reason = explain_recompile(BEFORE, AFTER, "compute.appServer")
    assert reason.recompiled is True
    assert reason.own_properties_changed is False
    assert [c.node_id for c in reason.caused_by] == ["secret.dbPassword"]
    assert reason.caused_by[0].own_properties_changed is True


def test_two_hop_cascade_reaches_the_original_edit():
    reason = explain_recompile(BEFORE, AFTER, "governance.catalog")
    assert reason.recompiled is True
    assert [c.node_id for c in reason.caused_by] == ["compute.appServer"]
    app_server = reason.caused_by[0]
    assert [c.node_id for c in app_server.caused_by] == ["secret.dbPassword"]
    db_password = app_server.caused_by[0]
    assert db_password.property_diff == {"rotation": (90, 30)}


def test_new_node_is_reported_as_new_not_a_dependency_change():
    reason = explain_recompile(BEFORE, AFTER, "storage.archive")
    assert reason.is_new is True
    assert reason.recompiled is True
    assert reason.caused_by == []


def test_untouched_node_is_not_recompiled():
    reason = explain_recompile(BEFORE, AFTER, "network.vpc")
    assert reason.recompiled is False
    assert reason.own_properties_changed is False
    assert reason.caused_by == []


def test_sibling_of_the_edited_node_is_also_not_recompiled():
    """bucket1 depends on vpc, same as dbPassword does -- but doesn't depend
    on dbPassword itself, so dbPassword's edit must not affect it."""
    reason = explain_recompile(BEFORE, AFTER, "storage.bucket1")
    assert reason.recompiled is False


def test_render_trace_shows_the_full_chain_to_the_root_cause():
    reason = explain_recompile(BEFORE, AFTER, "governance.catalog")
    text = render_trace(reason)
    assert "governance.catalog" in text
    assert "compute.appServer" in text
    assert "secret.dbPassword" in text
    assert "rotation: 90 -> 30" in text
    # the root cause is indented deeper than what it caused
    assert text.index("governance.catalog") < text.index("compute.appServer") < text.index("secret.dbPassword")
