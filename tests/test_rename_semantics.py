"""What happens when a dependency is renamed -- compute.appServer pointing
from secret.dbPassword to secret.databasePassword. EPC has no rename
tracking (node identity is just capability.name), so this is, correctly,
"remove the old edge, add a new node, add the new edge" -- not a special
case. The interesting question isn't whether this compiles correctly (it
already did), it's whether the *explanation* stays clean: the first
implementation reported secret.databasePassword twice, once via caused_by
(new node) and once via added_dependencies (added edge) -- redundant, not
wrong. Fixed by excluding anything already covered by caused_by from
added_dependencies.
"""

from epc.explain import explain_recompile, previous_state_from_graph, render_trace
from epc.normalizer import normalize
from epc.parser import parse
from epc.passes import BatchPlanner

BEFORE = """
metadata: {name: rename-example}
spec:
  resources:
    - capability: secret
      name: dbPassword
      properties:
        rotation: 90
    - capability: compute
      name: appServer
      dependsOn: ["secret.dbPassword"]
"""

AFTER = """
metadata: {name: rename-example}
spec:
  resources:
    - capability: secret
      name: databasePassword
      properties:
        rotation: 90
    - capability: compute
      name: appServer
      dependsOn: ["secret.databasePassword"]
"""


def _compiled(spec_yaml: str):
    graph = normalize(parse(spec_yaml))
    graph.compute_hashes(BatchPlanner().plan(graph).ordered_node_ids)
    return graph


def test_rename_is_understood_as_a_new_node_not_a_mutation_of_the_old_one():
    before = _compiled(BEFORE)
    after = _compiled(AFTER)
    assert "secret.dbPassword" not in after.nodes
    assert "secret.databasePassword" in after.nodes


def test_appserver_names_both_the_old_and_new_dependency_exactly_once():
    before = _compiled(BEFORE)
    after = _compiled(AFTER)
    reason = explain_recompile(previous_state_from_graph(before), after, "compute.appServer")

    assert reason.recompiled is True
    assert reason.removed_dependencies == ["secret.dbPassword"]
    assert reason.added_dependencies == []  # not double-reported -- see caused_by instead
    assert [c.node_id for c in reason.caused_by] == ["secret.databasePassword"]
    assert reason.caused_by[0].is_new is True


def test_rendered_trace_does_not_redundantly_double_report_the_new_dependency():
    """The recursive causal chain naturally names a dependency twice -- once
    in the parent's "depends on changed: X" line, once in X's own recursive
    line explaining itself (the same pattern the dbPassword -> appServer ->
    catalog chain already uses). What's fixed is the THIRD, redundant
    mention this used to add via "added dependency: X" on the same line as
    "depends on changed: X" -- that phrase must not appear at all here."""
    before = _compiled(BEFORE)
    after = _compiled(AFTER)
    reason = explain_recompile(previous_state_from_graph(before), after, "compute.appServer")
    text = render_trace(reason)

    assert "added dependency: secret.databasePassword" not in text
    assert "depends on changed: secret.databasePassword" in text
    assert "removed dependency: secret.dbPassword" in text
