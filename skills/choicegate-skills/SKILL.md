---
name: choicegate-skills
description: Select one installed, registered, or candidate skill, or one registry-approved skill bundle. Use for skill selection and lifecycle eligibility only. Do not use for local CLIs, plugins, connectors, APIs, SDKs, providers, or executing a skill.
---

# ChoiceGate Skills

Emit one hash-bound skill or approved skill-bundle receipt.

- Accept only the exact accepted-registry inventory and lifecycle axes bound by `references/routing-contract.md`.
- Reject inactive, unauthorized, stale, superseded, duplicate-owner, surface-mismatched, or unpromoted candidates.
- Preserve bundle membership, fallback eligibility, and owner gates in the receipt.
- Route with `../../scripts/route_capabilities.py`; do not copy its registry, scoring, hashing, or schema logic.
- Never install, enable, expose, activate, promote, supersede, archive, or execute a skill.
