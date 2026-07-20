# Project status

`choicegate` 0.2.0, alpha, prepared locally and built by Rahul Krishna; PyPI still serves 0.1.0.
The portable test suite (23 tests) and the GitLab pipeline pass offline from a bare checkout,
including a full-router replay against a
hash-pinned synthetic registry. A stronger suite replays the router against the
exact owner-accepted capability-registry snapshot pinned in `references/routing-contract.md`; that
snapshot is not part of this repository, so the stronger suite runs only in the maintainer's
environment. See [docs/public/VALIDATION.md](docs/public/VALIDATION.md) for both gates.

## Closed actions

ChoiceGate selects; it never acts. Nothing in this project will:

1. Create or change a git remote
2. Fetch
3. Pull
4. Push
5. Query a marketplace
6. Query a live registry (accepted snapshots arrive embedded in the request)
7. Authenticate
8. Call a model or API provider
9. Install a plugin or package
10. Enable a plugin or skill
11. Activate a skill
12. Promote a skill
13. Execute a selected capability
14. Delete anything

Selection is never execution. Every receipt carries an explicit `prohibited_actions` list, and a
receipt cannot grant permission to execute, install, authenticate, or configure the capability it
names.

## What installing the package does not claim

Version 0.1.0 is published on PyPI as
[`choicegate`](https://pypi.org/project/choicegate/). Installing it is not a marketplace entry, an
activation, or a lifecycle claim: lifecycle eligibility and routing priority remain owned by the
external capability registry, and ChoiceGate binds to one owner-accepted snapshot of that registry
by content hash without ever mutating it. Building the Claude Code and Codex surface packages
(`tools/build_surface_packages.py`) creates no marketplace entry either; surface activation remains
a separate registry lifecycle decision.

## Compatibility alias

The historical `discover-better-tools` name survives only as an explicit compatibility alias (root
`SKILL.md`). It never triggers from natural language, never owns capability-selection intent, and
cannot outrank a canonical ChoiceGate skill.
