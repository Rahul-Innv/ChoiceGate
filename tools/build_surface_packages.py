#!/usr/bin/env python3
"""Build deterministic, offline Choicegate surface archives from an explicit allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "packaging" / "surface-package.json"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_bytes().decode("utf-8"))
    if value.get("schema_version") != 1 or value.get("package_id") != "choicegate":
        raise ValueError("unsupported surface package contract")
    return value


def safe_relative(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe package path: {relative}")
    return relative


def collect_common(contract: dict[str, Any]) -> list[Path]:
    files: set[Path] = set()
    for relative in contract["common_files"]:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        files.add(path)
    for relative in contract["common_directories"]:
        root = ROOT / relative
        if not root.is_dir():
            raise FileNotFoundError(relative)
        for path in root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
                files.add(path)
    return sorted(files, key=lambda item: safe_relative(item))


def surface_files(contract: dict[str, Any], surface: str) -> list[Path]:
    spec = contract["surfaces"][surface]
    files = set(collect_common(contract))
    for relative in [spec["manifest"], *spec["extra_files"]]:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        files.add(path)
    return sorted(files, key=lambda item: safe_relative(item))


def build_archive(output: Path, surface: str, files: list[Path]) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in files:
            name = safe_relative(source)
            raw = source.read_bytes()
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            entries.append({"path": name, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    payload = output.read_bytes()
    return {
        "surface": surface,
        "archive_name": output.name,
        "entry_count": len(entries),
        "entries": entries,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build(output_dir: Path) -> dict[str, Any]:
    contract = load_contract()
    packages = []
    for surface in sorted(contract["surfaces"]):
        archive = output_dir / f"choicegate-{surface}-{contract['version']}.zip"
        packages.append(build_archive(archive, surface, surface_files(contract, surface)))
    return {
        "receipt_version": "choicegate.surface-package-dry-run/v1",
        "package_id": contract["package_id"],
        "version": contract["version"],
        "publication_state": contract["publication_state"],
        "packages": packages,
        "closed_actions": [
            "registry-query",
            "marketplace-write",
            "authentication",
            "installation",
            "publication"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="local output directory")
    args = parser.parse_args()
    receipt = build(args.output.resolve())
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
