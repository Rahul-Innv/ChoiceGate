---
name: choicegate
description: Select exactly one atomic ChoiceGate family leaf for capability-selection work spanning skills, local tools, integrations, generators, measured context, or freshness. Use only for family dispatch. Do not use after a capability is already selected, and never execute, install, authorize, or configure the selected path.
---

# ChoiceGate

Return one narrow family leaf or `NO_SAFE_ROUTE`; do not perform leaf work here.

1. Preserve the task, scope, permissions, surface, and existing receipt bindings.
2. Express only evidence-backed typed claims to `../../scripts/select_family_leaf.py`.
3. Delegate exactly once to `choicegate-skills`, `choicegate-tools`, `choicegate-integrations`, `choicegate-generators`, `choicegate-context`, or `choicegate-refresh`.
4. Fail closed when multiple explicit domains compete, multiple inferred domains remain, or no domain is supported.
5. Pass the unchanged hash-bound route request to the shared router through the selected leaf.

Do not rank capabilities, call providers, mutate lifecycle state, or duplicate leaf logic.
