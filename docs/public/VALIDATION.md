# Validation contract

## Portable repository gate

Run from any checkout with Python 3.11 or newer:

```powershell
python -B -m unittest discover -s tests -p "test_*.py"
python -B -m py_compile scripts/*.py tools/*.py
```

This verifies the standalone family dispatcher, exact seven-skill ownership, trigger and near-miss
fixture coverage, pairwise domain collisions, strict JSON duplicate-key rejection, receipt hashing,
surface-adapter hash bindings, plugin IDs and versions, packaging metadata, deterministic package
contents, and archive reproducibility.

## Authority-bound gate (maintainers)

A stronger authority-bound suite validates the router against the exact owner-accepted external
capability-registry snapshot pinned in `references/routing-contract.md`. That registry snapshot is
not part of this repository, so the authority-bound suite runs only in the maintainer's environment
and is not shipped here. A passing portable suite is not a substitute for that replay.

## Package build gate

```powershell
python -B -m build --no-isolation
python -B -m twine check dist/*
```

The sdist and wheel are produced by the deterministic, dependency-free in-tree backend in
`tools/choicegate_backend.py`. Two consecutive builds must produce byte-identical archives.

## Surface package dry run

```powershell
python -B tools/build_surface_packages.py --output dist/run-a
python -B tools/build_surface_packages.py --output dist/run-b
```

The two receipts and both surface archive hashes must match. The allowlist excludes evals, tests,
Git metadata, generated output, and machine-local data. A dry run does not query a registry, create
a marketplace entry, install a plugin, or publish an artifact.
