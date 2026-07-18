"""Shared ChoiceGate routing core, packaged as the ``choicegate`` distribution.

Modules:

- ``select_family_leaf``: dispatch one typed family request to exactly one domain
  leaf, or return no safe route.
- ``route_capabilities``: route one hash-bound registry capability or approved
  bundle and emit a deterministic decision receipt.
- ``rank_candidates``: backward-compatible discovery ranking helper backed by the
  router module.
"""

from __future__ import annotations

__all__ = ["rank_candidates", "route_capabilities", "select_family_leaf"]
__version__ = "0.1.0"
