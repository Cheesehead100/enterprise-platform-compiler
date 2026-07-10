"""The literal scenario -- a node still declaring a dependency on a resource
that's been deleted from the spec -- can't actually reach explain_recompile:
normalize() rejects it as UndefinedReferenceError before any IRGraph with
that shape exists (test_normalize_path_is_structurally_immune_to_this,
below). The real, reachable gap is one level down: explain_recompile is a
public function, not gated behind normalize()'s validation, so a hand-built
or otherwise corrupted IRGraph can still reach it directly.
"""

import pytest

from epc.explain import explain_recompile, previous_state_from_graph
from epc.ir import ComputeNode, IRGraph
from epc.normalizer import normalize
from epc.parser import parse
from epc.errors import UndefinedReferenceError


def test_normalize_path_is_structurally_immune_to_this():
    """A node depending on a resource that was never declared (or was
    deleted) is a compile error, not a silently-broken graph -- caught here,
    at normalize() time, long before explain_recompile could ever see it."""
    spec = """
metadata: {name: x}
spec:
  resources:
    - capability: compute
      name: app
      dependsOn: ["compute.primary"]
"""
    with pytest.raises(UndefinedReferenceError, match="compute.primary"):
        normalize(parse(spec))


def test_explain_recompile_fails_clearly_on_a_hand_built_inconsistent_graph():
    """The only way to reach this: bypass normalize() entirely and hand
    explain_recompile an IRGraph where a node's own depends_on references
    something that graph doesn't contain. Confirms it fails loud with the
    missing id named, not a bare KeyError with no context."""
    before = IRGraph(
        nodes={
            "compute.primary": ComputeNode(id="compute.primary", capability="compute", hash="abc"),
            "compute.app": ComputeNode(
                id="compute.app", capability="compute", depends_on={"compute.primary"}, hash="old-app-hash"
            ),
        }
    )
    previous = previous_state_from_graph(before)

    corrupted_after = IRGraph(
        nodes={
            "compute.app": ComputeNode(
                id="compute.app", capability="compute", depends_on={"compute.primary"}, hash="new-app-hash"
            ),
            # compute.primary is missing entirely -- app's own depends_on
            # still names it, but nothing backs that reference up
        }
    )

    with pytest.raises(KeyError, match="compute.primary"):
        explain_recompile(previous, corrupted_after, "compute.app")
