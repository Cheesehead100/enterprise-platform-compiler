"""explain_recompile against the same incremental_before/after fixtures
tests/test_incremental_report.py already exercises -- one fixture pair,
another real report derived from it.
"""

from epc.explain import explain_recompile, previous_state_from_graph, render_trace
from epc.normalizer import normalize
from epc.parser import parse

BEFORE = normalize(parse(open("tests/fixtures/incremental_before.yaml").read()))
AFTER = normalize(parse(open("tests/fixtures/incremental_after.yaml").read()))
ORDER = ["network.vpc", "storage.bucket1", "storage.bucket2", "secret.dbPassword", "compute.appServer", "governance.catalog"]
BEFORE.compute_hashes(ORDER)
AFTER.compute_hashes(ORDER + ["storage.archive"])
PREVIOUS = previous_state_from_graph(BEFORE)


def test_edited_node_reports_its_own_property_diff():
    reason = explain_recompile(PREVIOUS, AFTER, "secret.dbPassword")
    assert reason.recompiled is True
    assert reason.own_properties_changed is True
    assert reason.property_diff == {"rotation": (90, 30)}
    assert reason.caused_by == []


def test_cascaded_node_points_at_its_changed_dependency_not_itself():
    reason = explain_recompile(PREVIOUS, AFTER, "compute.appServer")
    assert reason.recompiled is True
    assert reason.own_properties_changed is False
    assert [c.node_id for c in reason.caused_by] == ["secret.dbPassword"]
    assert reason.caused_by[0].own_properties_changed is True


def test_two_hop_cascade_reaches_the_original_edit():
    reason = explain_recompile(PREVIOUS, AFTER, "governance.catalog")
    assert reason.recompiled is True
    assert [c.node_id for c in reason.caused_by] == ["compute.appServer"]
    app_server = reason.caused_by[0]
    assert [c.node_id for c in app_server.caused_by] == ["secret.dbPassword"]
    db_password = app_server.caused_by[0]
    assert db_password.property_diff == {"rotation": (90, 30)}


def test_new_node_is_reported_as_new_not_a_dependency_change():
    reason = explain_recompile(PREVIOUS, AFTER, "storage.archive")
    assert reason.is_new is True
    assert reason.recompiled is True
    assert reason.caused_by == []


def test_untouched_node_is_not_recompiled():
    reason = explain_recompile(PREVIOUS, AFTER, "network.vpc")
    assert reason.recompiled is False
    assert reason.own_properties_changed is False
    assert reason.caused_by == []


def test_sibling_of_the_edited_node_is_also_not_recompiled():
    """bucket1 depends on vpc, same as dbPassword does -- but doesn't depend
    on dbPassword itself, so dbPassword's edit must not affect it."""
    reason = explain_recompile(PREVIOUS, AFTER, "storage.bucket1")
    assert reason.recompiled is False


def test_render_trace_shows_the_full_chain_to_the_root_cause():
    reason = explain_recompile(PREVIOUS, AFTER, "governance.catalog")
    text = render_trace(reason)
    assert "governance.catalog" in text
    assert "compute.appServer" in text
    assert "secret.dbPassword" in text
    assert "rotation: 90 -> 30" in text
    # the root cause is indented deeper than what it caused
    assert text.index("governance.catalog") < text.index("compute.appServer") < text.index("secret.dbPassword")


def test_previous_state_from_manifest_matches_previous_state_from_graph():
    """The two ways to build a PreviousState (in-memory graph vs. a loaded
    JSON manifest) must produce equivalent explanations -- this is what makes
    epc.cli's --explain flag trustworthy across separate process runs."""
    from epc.explain import previous_state_from_manifest

    manifest_shape = {
        node_id: {"hash": node.hash, "properties": node.properties, "depends_on": sorted(node.depends_on)}
        for node_id, node in BEFORE.nodes.items()
    }
    from_manifest = previous_state_from_manifest(manifest_shape)

    reason_from_graph = explain_recompile(PREVIOUS, AFTER, "governance.catalog")
    reason_from_manifest = explain_recompile(from_manifest, AFTER, "governance.catalog")
    assert reason_from_graph == reason_from_manifest


def _compiled(spec_yaml: str, order: list[str]):
    from epc.passes import BatchPlanner

    graph = normalize(parse(spec_yaml))
    graph.compute_hashes(order or BatchPlanner().plan(graph).ordered_node_ids)
    return graph


def test_removing_a_dependency_edge_is_detected_even_when_the_dependency_itself_is_unchanged():
    """Regression: a node whose dependency SET shrinks changes its own hash
    (the deps-hash-list is shorter) even though the removed dependency's own
    hash never changed. Walking only *current* dependencies and asking "did
    this one's hash change" silently misses this -- it has to be caught as a
    set difference against the previous edge list."""
    before_spec = """
metadata: {name: x}
spec:
  resources:
    - capability: network
      name: y
    - capability: network
      name: z
    - capability: compute
      name: app
      dependsOn: ["network.y", "network.z"]
"""
    after_spec = before_spec.replace('dependsOn: ["network.y", "network.z"]', 'dependsOn: ["network.y"]')

    before = _compiled(before_spec, [])
    after = _compiled(after_spec, [])
    assert before.nodes["compute.app"].hash != after.nodes["compute.app"].hash  # the pipeline WOULD recompile this

    reason = explain_recompile(previous_state_from_graph(before), after, "compute.app")
    assert reason.recompiled is True
    assert reason.removed_dependencies == ["network.z"]
    assert reason.caused_by == []  # network.z's own hash never changed -- this isn't a cascade


def test_adding_a_dependency_edge_to_an_unchanged_node_is_detected():
    """Symmetric case: wiring a node to an existing, untouched neighbor."""
    before_spec = """
metadata: {name: x}
spec:
  resources:
    - capability: network
      name: y
    - capability: network
      name: z
    - capability: compute
      name: app
      dependsOn: ["network.y"]
"""
    after_spec = before_spec.replace('dependsOn: ["network.y"]', 'dependsOn: ["network.y", "network.z"]')

    before = _compiled(before_spec, [])
    after = _compiled(after_spec, [])

    reason = explain_recompile(previous_state_from_graph(before), after, "compute.app")
    assert reason.recompiled is True
    assert reason.added_dependencies == ["network.z"]


def test_reordering_yaml_keys_does_not_change_the_hash():
    """properties dicts are hashed with sort_keys=True (IRGraph.compute_hashes)
    -- YAML key order is not semantic and must not look like a change."""
    original = """
metadata: {name: x}
spec:
  resources:
    - capability: storage
      name: bucket
      properties:
        tier: Standard_LRS
        region: eastus2
"""
    reordered = """
metadata: {name: x}
spec:
  resources:
    - capability: storage
      name: bucket
      properties:
        region: eastus2
        tier: Standard_LRS
"""
    a = _compiled(original, [])
    b = _compiled(reordered, [])
    assert a.nodes["storage.bucket"].hash == b.nodes["storage.bucket"].hash

    reason = explain_recompile(previous_state_from_graph(a), b, "storage.bucket")
    assert reason.recompiled is False
