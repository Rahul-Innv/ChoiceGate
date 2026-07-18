from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "tools" / "build_surface_packages.py"
SPEC = importlib.util.spec_from_file_location("choicegate_package_builder", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class RepoReadinessTests(unittest.TestCase):
    def test_required_governance_and_gitlab_paths_exist(self) -> None:
        required = [
            ".gitattributes", ".gitignore", ".gitlab-ci.yml", "CHANGELOG.md", "CODE_OF_CONDUCT.md",
            "CONTRIBUTING.md", "LICENSE", "README.md", "ROADMAP.md", "SECURITY.md", "VERSION",
            "pyproject.toml",
            ".gitlab/issue_templates/Bug.md", ".gitlab/issue_templates/Feature.md",
            ".gitlab/merge_request_templates/Default.md", "assets/logo.svg", "assets/demo.svg",
            "docs/public/ARCHITECTURE.md", "docs/public/VALIDATION.md",
        ]
        self.assertEqual([item for item in required if not (ROOT / item).is_file()], [])

    def test_family_plugin_metadata_is_exact(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version, "0.1.0")
        for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            manifest = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            self.assertEqual(manifest["name"], "choicegate")
            self.assertEqual(manifest["version"], version)
            self.assertEqual(manifest["author"]["name"], "Rahul Krishna")
        family = json.loads((ROOT / "skills" / "family.json").read_text(encoding="utf-8"))
        self.assertEqual(family["authority_state"], "candidate-inactive")
        self.assertEqual([item["id"] for item in family["leaves"]], [
            "choicegate", "choicegate-skills", "choicegate-tools", "choicegate-integrations",
            "choicegate-generators", "choicegate-context", "choicegate-refresh",
        ])

    def test_python_distribution_metadata_is_exact(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["name"], "choicegate")
        self.assertEqual(project["version"], version)
        self.assertEqual(project["license"]["text"], "MIT")
        self.assertEqual(project["authors"], [{"name": "Rahul Krishna"}])
        self.assertIn("License :: OSI Approved :: MIT License", project["classifiers"])

    def test_public_docs_preserve_closed_action_language(self) -> None:
        combined = "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in (
            "README.md", "ROADMAP.md", "docs/public/ARCHITECTURE.md", "docs/public/VALIDATION.md"
        )).lower()
        for phrase in ("no marketplace", "capability registry", "selection is never execution", "fails closed"):
            self.assertIn(phrase, combined)
        canonical = "gitlab.com/krahul02004/choicegate"
        self.assertIn(canonical, combined)
        self.assertEqual(combined.count("gitlab.com/"), combined.count(canonical))

    def test_every_json_file_is_strict_utf8_and_parses(self) -> None:
        for path in ROOT.rglob("*.json"):
            if ".git" in path.parts or "dist" in path.parts:
                continue
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                json.loads(path.read_bytes().decode("utf-8"))

    def test_surface_packages_are_byte_deterministic_and_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "a"
            second = Path(temp) / "b"
            receipt_a = BUILDER.build(first)
            receipt_b = BUILDER.build(second)
            self.assertEqual(receipt_a, receipt_b)
            for package_a, package_b in zip(receipt_a["packages"], receipt_b["packages"], strict=True):
                path_a = first / package_a["archive_name"]
                path_b = second / package_b["archive_name"]
                self.assertEqual(path_a.read_bytes(), path_b.read_bytes())
                self.assertEqual(hashlib.sha256(path_a.read_bytes()).hexdigest(), package_a["sha256"])
                with zipfile.ZipFile(path_a) as archive:
                    names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertTrue(any(name.startswith("skills/choicegate") for name in names))
                self.assertFalse(any(name.startswith((".git/", "dist/", "evals/", "tests/")) for name in names))
                self.assertFalse(any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in names))

    def test_gitlab_ci_contains_only_local_validation_commands(self) -> None:
        text = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8").lower()
        for required in ("unittest", "py_compile"):
            self.assertIn(required, text)
        for forbidden in ("curl ", "wget ", "git push", "npm publish", "twine upload", "provider"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
