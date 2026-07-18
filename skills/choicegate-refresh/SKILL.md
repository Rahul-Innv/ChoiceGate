---
name: choicegate-refresh
description: Decide whether prior capability-selection evidence is still fresh, produce one bounded evidence delta, and require rerouting when bindings or material facts changed. Do not silently reuse stale receipts, execute a capability, mutate sources, or browse without the applicable gate.
---

# ChoiceGate Refresh

Emit one freshness decision and evidence delta.

- Compare the complete prior receipt against exact inventory, router, task, permission, risk, availability, and authorization bindings.
- Treat changed fingerprints, router bytes, scope, owner gates, selected-path failure, or stale material evidence as reselection triggers.
- Suppress rediscovery only for a complete unchanged valid handoff.
- Route the refreshed frozen evidence with `../../scripts/route_capabilities.py`.
- Never patch a prior receipt, refresh by assumption, call a provider, or execute the selected capability.
