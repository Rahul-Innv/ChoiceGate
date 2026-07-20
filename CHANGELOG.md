# Changelog

## [Unreleased]

## [0.2.0] - 2026-07-19

Minor release preparation: the full router now has a public, deterministic execution
path without weakening or exposing the separate owner-registry authority boundary.

- Added Repository, Issues, and Changelog links to package metadata.
- Added a hash-pinned synthetic public registry profile and self-contained request that exercise the
  complete router without claiming owner-registry authority or Git provenance.
- Replaced shell-dependent wildcard compilation docs with a PowerShell-safe `compileall` command.
- Aligned all request, prior-receipt, and decision-receipt registry-profile schemas with runtime:
  explicit and legacy owner profiles require a Git commit; the synthetic demo requires null.
- Packaged the router's two schema bindings and made binding resolution portable across source and
  installed-wheel layouts, with a wheel-layout regression that prevents missing runtime data.
- Reconciled current-facing launch and release-gate documentation with the public GitLab project
  and published PyPI 0.1.0 baseline without inventing a matching source tag or GitLab Release.

No version compare link is recorded for 0.2.0 because no matching 0.1.0 source tag exists.
The later tag, tag push, GitLab Release, and package publication remain separate owner actions.

## [0.1.0] - 2026-07-18

Version 0.1.0 is published on PyPI. No matching Git tag or GitLab Release provenance is
claimed; package publication does not grant installation, activation, or registry authority.

### Added

- Added one dispatch-only ChoiceGate router and six single-outcome capability-selection leaves.
- Added deterministic receipt schemas, lifecycle-aware ranking, strict JSON handling, surface parity,
  trigger/near-miss/collision fixtures, and a standalone offline repository test suite.
- Added explicit compatibility metadata for the historical `discover-better-tools` invocation.
- Added family-level Claude Code and Codex package manifests under the `choicegate` identity, plus a
  deterministic `choicegate` Python distribution built by a dependency-free in-tree backend.
- Added MIT governance, contribution, conduct, security, roadmap, demo, validation, and architecture
  documentation.

### Safety

- Kept every provider, marketplace, registry, installation, lifecycle, execution, host-settings,
  tag, GitLab Release, archive, and deletion action closed in the source lane. The separately
  recorded PyPI publication did not widen those boundaries.
