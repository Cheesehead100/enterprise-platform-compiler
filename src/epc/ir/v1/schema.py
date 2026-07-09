"""IR version marker. Every serialized IRGraph embeds this (see serializer.py)
so a provider or a future migration layer can tell what it's holding before
touching it — the same reason every wire protocol version-stamps its
messages.

ponytail: no generated JSON Schema document yet — deferred until an external
consumer (a provider SDK in another language, architecture doc §09) actually
needs to validate structurally against this without importing this package
directly. `epc.ir.v1.validator` is the in-process equivalent for now.
"""

IR_VERSION = "1.0"

NODE_KINDS = (
    "compute",
    "storage",
    "secret",
    "identity",
    "network",
    "policy",
    "pipeline",
    "data-platform",
)
