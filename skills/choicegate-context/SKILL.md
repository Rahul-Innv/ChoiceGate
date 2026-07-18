---
name: choicegate-context
description: Select one measured context intervention under an explicit budget, such as bounded retrieval, packing, mapping, filtering, or context reduction. Do not load or mutate context, run an unmeasured workflow, select a generic tool, or exceed the declared ceiling.
---

# ChoiceGate Context

Emit one budget-bound context-route receipt or `NO_SAFE_ROUTE`.

- Require a measurable context outcome, typed ceiling, evidence freshness, and exact scope.
- Reject over-bundled, unavailable, stale, surface-mismatched, or nonconvertible budget claims.
- Preserve `CONTEXT_BUDGET_EXCEEDED` as a hard exclusion that cannot be outscored.
- Route with `../../scripts/route_capabilities.py`; do not perform retrieval, packing, mapping, or filtering.
- Never silently widen context, translate incompatible metrics, or execute the intervention.
