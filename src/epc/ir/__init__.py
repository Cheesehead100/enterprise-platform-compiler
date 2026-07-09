"""epc.ir re-exports the current IR version's public API. Everything in
epc/ (normalizer, dag, provider, pipeline) imports from here, not from
epc.ir.v1 directly, so bumping the current version later is a one-line
change in this file rather than a repo-wide import rewrite. See
epc.ir.v1.schema.IR_VERSION and the migration-layer note in that module.
"""

from .v1 import *  # noqa: F401,F403
from .v1 import __all__  # noqa: F401
