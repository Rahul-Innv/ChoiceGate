# Changelog

## [Unreleased]

- Added Repository, Issues, and Changelog links to package metadata.
- Added a hash-pinned synthetic public registry profile and self-contained request that exercise the
  complete router without claiming owner-registry authority or Git provenance.
- Replaced shell-dependent wildcard compilation docs with a PowerShell-safe `compileall` command.
- Aligned all request, prior-receipt, and decision-receipt registry-profile schemas with runtime:
  explicit and legacy owner profiles require a Git commit; the synthetic demo requires null.

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
