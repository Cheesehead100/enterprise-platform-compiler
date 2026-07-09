"""Stage 1 — Parse: YAML -> AST (architecture doc §03, pipeline stage 1)."""

from __future__ import annotations

from typing import Any

import yaml

from .ast import PlatformSpecAST, Ref, ResourceNode
from .errors import ParseError, SchemaError

REF_PREFIX = "ref:"


def _resolve_ref_values(properties: dict[str, Any]) -> dict[str, Any]:
    """Turn any `"ref:<path>"` string property into a Ref — still unresolved at this stage."""
    resolved: dict[str, Any] = {}
    for key, value in properties.items():
        if isinstance(value, str) and value.startswith(REF_PREFIX):
            resolved[key] = Ref(value[len(REF_PREFIX) :])
        else:
            resolved[key] = value
    return resolved


def parse(spec_yaml: str) -> PlatformSpecAST:
    try:
        doc = yaml.safe_load(spec_yaml)
    except yaml.YAMLError as exc:
        raise ParseError(str(exc)) from exc

    if not isinstance(doc, dict):
        raise SchemaError("PlatformSpec document must be a mapping")

    metadata = doc.get("metadata") or {}
    spec = doc.get("spec") or {}
    if "name" not in metadata:
        raise SchemaError("metadata.name is required")

    resources_raw = spec.get("resources") or []
    if not isinstance(resources_raw, list):
        raise SchemaError("spec.resources must be a list")

    spec_properties = {k: v for k, v in spec.items() if k != "resources"}

    resources: list[ResourceNode] = []
    for entry in resources_raw:
        if "capability" not in entry or "name" not in entry:
            raise SchemaError(f"resource entry missing 'capability' or 'name': {entry}")
        resources.append(
            ResourceNode(
                capability=entry["capability"],
                name=entry["name"],
                properties=_resolve_ref_values(entry.get("properties") or {}),
                depends_on=list(entry.get("dependsOn") or []),
            )
        )

    return PlatformSpecAST(name=metadata["name"], spec_properties=spec_properties, resources=resources)
