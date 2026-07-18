---
name: discover-better-tools
description: Compatibility-only ChoiceGate alias. Use only when the owner explicitly invokes $discover-better-tools or a verified legacy reference requires that exact name. Do not trigger from natural-language requests; canonical capability-selection intent belongs to the atomic ChoiceGate family.
---

# Discover Better Tools compatibility alias

Preserve the legacy invocation name without creating a second capability-selection authority.
ChoiceGate is the canonical owner of capability-selection intent.

## Delegate without widening scope

1. Confirm the invocation is explicitly `$discover-better-tools` or is bound to a verified legacy reference.
2. Delegate family selection to `skills/choicegate/SKILL.md` and preserve the original task, scope, permissions, and surface unchanged.
3. Use the shared neutral router at `scripts/route_capabilities.py`; do not copy ranking, schema, hashing, lifecycle, or receipt logic into this alias.
4. Apply the evidence workflow in `references/discovery-evaluation.md` only when the selected canonical leaf is `choicegate-integrations`.
5. Return the canonical ChoiceGate result. Never label this alias as the canonical owner.

This alias is explicit-invocation only. It never triggers from natural language and never outranks a canonical ChoiceGate skill.
