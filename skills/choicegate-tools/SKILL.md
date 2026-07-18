---
name: choicegate-tools
description: Select one local CLI, executable, script, or deterministic utility for a bounded task. Use only for local tool selection. Do not use for plugins, apps, connectors, MCP servers, APIs, SDKs, provider integrations, installation, or execution.
---

# ChoiceGate Tools

Emit one local-tool receipt without executing the tool.

- Inventory only relevant local, already-visible tool metadata and Windows compatibility evidence.
- Keep provider-backed interfaces in `choicegate-integrations`, even when they also ship a CLI wrapper.
- Preserve scope, private-data class, risk, setup, fallback, and evidence bindings.
- Route with `../../scripts/route_capabilities.py`; `rank_candidates.py` remains only a legacy unbound ranking aid.
- Never install, configure, authenticate, execute, or write through a selected tool.
