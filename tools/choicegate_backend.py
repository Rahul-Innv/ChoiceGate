"""Deterministic, dependency-free PEP 517 build backend for the choicegate distribution.

The backend builds a reproducible sdist and wheel from the repository allowlist using
only the standard library. Entry timestamps, ordering, and permissions are fixed so
two consecutive builds produce byte-identical archives. It performs no network access
and writes only the requested output archives.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
TAR_TIME = 315532800  # 1980-01-01T00:00:00Z


def _load_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _project() -> dict:
    return _load_pyproject()["project"]


def _tool() -> dict:
    return _load_pyproject().get("tool", {}).get("choicegate-backend", {})


def _metadata_text() -> str:
    project = _project()
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {project['name']}",
        f"Version: {project['version']}",
        f"Summary: {project['description']}",
        f"Author: {project['authors'][0]['name']}",
        f"License: {project['license']['text']}",
    ]
    for keyword_list in (project.get("keywords"),):
        if keyword_list:
            lines.append("Keywords: " + ",".join(keyword_list))
    for classifier in project.get("classifiers", ()):
        lines.append(f"Classifier: {classifier}")
    for label, url in sorted(project.get("urls", {}).items()):
        lines.append(f"Project-URL: {label}, {url}")
    lines.append(f"Requires-Python: {project['requires-python']}")
    lines.append("Description-Content-Type: text/markdown")
    readme = (ROOT / project["readme"]).read_text(encoding="utf-8")
    return "\n".join(lines) + "\n\n" + readme


def _entry_points_text() -> str:
    scripts = _project().get("scripts", {})
    if not scripts:
        return ""
    rows = "".join(f"{name} = {target}\n" for name, target in sorted(scripts.items()))
    return f"[console_scripts]\n{rows}"


def _sdist_files() -> list[str]:
    entries: list[str] = []
    for included in _tool()["sdist-include"]:
        root = ROOT / included
        if root.is_file():
            entries.append(included)
            continue
        if not root.is_dir():
            raise FileNotFoundError(f"sdist allowlist entry is missing: {included}")
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            parts = PurePosixPath(relative).parts
            if "__pycache__" in parts or relative.endswith((".pyc", ".pyo")):
                continue
            entries.append(relative)
    return sorted(entries)


def _package_files() -> list[tuple[str, Path]]:
    tool = _tool()
    package = tool["package"]
    source = ROOT / tool["package-source"]
    pairs: list[tuple[str, Path]] = []
    for path in sorted(source.glob("*.py")):
        pairs.append((f"{package}/{path.name}", path))
    for relative in tool.get("package-data", ()):
        package_path = PurePosixPath(relative)
        if package_path.is_absolute() or ".." in package_path.parts:
            raise ValueError(f"unsafe package-data path: {relative}")
        data_source = ROOT.joinpath(*package_path.parts)
        if not data_source.is_file():
            raise FileNotFoundError(f"package-data entry is missing: {relative}")
        pairs.append((f"{package}/{package_path.as_posix()}", data_source))
    wheel_paths = [wheel_path for wheel_path, _ in pairs]
    if len(wheel_paths) != len(set(wheel_paths)):
        raise ValueError("duplicate wheel path in package files")
    return sorted(pairs)


def _record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# Optional PEP 517 hooks -------------------------------------------------------

def get_requires_for_build_sdist(config_settings=None):  # noqa: ARG001
    return []


def get_requires_for_build_wheel(config_settings=None):  # noqa: ARG001
    return []


# Mandatory PEP 517 hooks ------------------------------------------------------

def build_sdist(sdist_directory, config_settings=None):  # noqa: ARG001
    project = _project()
    base = f"{project['name']}-{project['version']}"
    sdist_path = Path(sdist_directory) / f"{base}.tar.gz"
    pkg_info = _metadata_text().encode("utf-8")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        def add_bytes(name: str, payload: bytes) -> None:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mtime = TAR_TIME
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(payload))

        add_bytes(f"{base}/PKG-INFO", pkg_info)
        for relative in _sdist_files():
            add_bytes(f"{base}/{relative}", (ROOT / relative).read_bytes())

    with open(sdist_path, "wb") as stream:
        with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:
            compressed.write(buffer.getvalue())
    return sdist_path.name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):  # noqa: ARG001
    project = _project()
    name = project["name"]
    version = project["version"]
    tag = "py3-none-any"
    wheel_name = f"{name}-{version}-{tag}.whl"
    dist_info = f"{name}-{version}.dist-info"

    entries: list[tuple[str, bytes]] = [
        *((wheel_path, source.read_bytes()) for wheel_path, source in _package_files()),
        (f"{dist_info}/METADATA", _metadata_text().encode("utf-8")),
        (
            f"{dist_info}/WHEEL",
            (
                "Wheel-Version: 1.0\n"
                f"Generator: choicegate-backend ({version})\n"
                "Root-Is-Purelib: true\n"
                f"Tag: {tag}\n"
            ).encode("utf-8"),
        ),
        (f"{dist_info}/LICENSE", (ROOT / "LICENSE").read_bytes()),
    ]
    entry_points = _entry_points_text()
    if entry_points:
        entries.append((f"{dist_info}/entry_points.txt", entry_points.encode("utf-8")))

    record_rows = [
        f"{path},{_record_hash(payload)},{len(payload)}" for path, payload in entries
    ]
    record_rows.append(f"{dist_info}/RECORD,,")
    entries.append((f"{dist_info}/RECORD", ("\n".join(record_rows) + "\n").encode("utf-8")))

    wheel_path = Path(wheel_directory) / wheel_name
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, payload in entries:
            info = zipfile.ZipInfo(path, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return wheel_name
