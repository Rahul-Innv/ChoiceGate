"""Standalone atomic-family contract tests extracted from the authority-bound suite.

Every test here runs offline from a bare checkout. The stronger authority-bound
suite additionally replays the router against the exact owner-accepted external
capability-registry snapshot and is maintained outside this repository.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from itertools import combinations
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
LEAVES = {
    "choicegate",
    "choicegate-context",
    "choicegate-generators",
    "choicegate-integrations",
    "choicegate-refresh",
    "choicegate-skills",
    "choicegate-tools",
}
DOMAINS = {"skills", "tools", "integrations", "generators", "context", "refresh"}


def load_dispatcher():
    spec = importlib.util.spec_from_file_location(
        "choicegate_family_dispatcher_contract",
        ROOT / "scripts" / "select_family_leaf.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_text_bytes(path: Path) -> bytes:
    text = path.read_bytes().decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def path_hash_fingerprint(root: Path, paths: list[str]) -> str:
    rows = "".join(
        f"{path}\t{sha256_bytes(normalized_text_bytes(root / path))}\n"
        for path in sorted(paths)
    )
    return sha256_bytes(rows.encode("utf-8"))


def read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def family_request(request_id: str, claims: list[dict[str, str]], legacy: bool = False) -> dict:
    return {
        "contract_version": "choicegate.family-request/v1",
        "request_id": request_id,
        "claims": claims,
        "legacy_invocation": legacy,
    }


class FamilyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = ROOT
        cls.dispatcher = load_dispatcher()
        cls.family = read_json(ROOT / "skills" / "family.json")
        cls.cases = read_json(ROOT / "evals" / "choicegate" / "atomic-family-cases.json")
        cls.request_schema = read_json(ROOT / "schemas" / "family-request.schema.json")
        cls.receipt_schema = read_json(ROOT / "schemas" / "family-dispatch-receipt.schema.json")

    def test_exact_seven_leaf_family_is_atomic_and_uses_one_neutral_core(self) -> None:
        leaves = self.family["leaves"]
        self.assertEqual(LEAVES, {item["id"] for item in leaves})
        self.assertEqual(7, len(leaves))
        dispatcher = next(item for item in leaves if item["id"] == "choicegate")
        self.assertEqual("dispatcher", dispatcher["kind"])
        self.assertEqual("scripts/select_family_leaf.py", dispatcher["core_entrypoint"])
        self.assertFalse(self.family["dispatcher_contract"]["contains_leaf_implementation"])
        atomic = [item for item in leaves if item["kind"] == "atomic-leaf"]
        self.assertEqual(6, len(atomic))
        self.assertEqual({"scripts/route_capabilities.py"}, {item["core_entrypoint"] for item in atomic})
        for item in leaves:
            self.assertTrue(item["intent_owner"])
            self.assertTrue(item["independently_measurable_output"])
            self.assertTrue(item["bounded_input"])
            self.assertTrue(item["bounded_output"])
            self.assertGreaterEqual(len(item["non_goals"]), 4)

    def test_skill_sources_have_exact_names_and_legacy_alias_is_explicit_only(self) -> None:
        for leaf in LEAVES:
            text = (self.root / "skills" / leaf / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n") or text.startswith("---\r\n"))
            self.assertIn(f"name: {leaf}", text)
            self.assertIn("description:", text)
            self.assertIn("Never" if leaf != "choicegate" else "Do not", text)
        alias = (self.root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: discover-better-tools", alias)
        self.assertIn("explicitly invokes $discover-better-tools", alias)
        self.assertIn("Do not trigger from natural-language requests", alias)
        self.assertEqual(
            [{
                "id": "discover-better-tools",
                "target": "choicegate",
                "invocation_policy": "explicit-legacy-name-only",
                "transition_state": "pending-separate-promotion",
                "canonical": False,
            }],
            self.family["compatibility_aliases"],
        )

    def test_trigger_and_near_miss_fixtures_cover_every_leaf_once(self) -> None:
        positives = self.cases["positive_cases"]
        near_misses = self.cases["near_miss_cases"]
        self.assertEqual(LEAVES, {item.get("expected_leaf", item.get("expected_skill")) for item in positives})
        self.assertEqual(LEAVES, {item["excluded_skill"] for item in near_misses})
        self.assertEqual(DOMAINS, {item["domain"] for item in positives if "domain" in item})
        for item in [*positives, *near_misses]:
            self.assertTrue(item["prompt"].strip())

    def test_single_domain_dispatch_is_deterministic_and_cli_equal(self) -> None:
        for domain in sorted(DOMAINS):
            with self.subTest(domain=domain):
                request = family_request(
                    f"single-{domain}",
                    [{"domain": domain, "specificity": "explicit", "evidence_id": f"intent-{domain}"}],
                )
                first = self.dispatcher.dispatch(copy.deepcopy(request))
                second = self.dispatcher.dispatch(copy.deepcopy(request))
                self.assertEqual(first, second)
                claimed = first["receipt_sha256"]
                self.assertEqual(
                    claimed,
                    self.dispatcher.canonical_sha256(
                        {key: value for key, value in first.items() if key != "receipt_sha256"}
                    ),
                )
                completed = subprocess.run(
                    [sys.executable, "-B", str(self.root / "scripts" / "select_family_leaf.py"), "-"],
                    input=self.dispatcher.canonical_bytes(request) + b"\n",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.root,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8"))
                self.assertEqual(self.dispatcher.canonical_bytes(first) + b"\n", completed.stdout)
                self.assertEqual(b"", completed.stderr)

    @unittest.skipUnless(Draft202012Validator is not None, "jsonschema is not installed")
    def test_single_domain_dispatch_matches_request_and_receipt_schemas(self) -> None:
        Draft202012Validator.check_schema(self.request_schema)
        Draft202012Validator.check_schema(self.receipt_schema)
        request_validator = Draft202012Validator(self.request_schema)
        receipt_validator = Draft202012Validator(self.receipt_schema)
        for domain in sorted(DOMAINS):
            with self.subTest(domain=domain):
                request = family_request(
                    f"single-{domain}",
                    [{"domain": domain, "specificity": "explicit", "evidence_id": f"intent-{domain}"}],
                )
                request_validator.validate(request)
                receipt_validator.validate(self.dispatcher.dispatch(copy.deepcopy(request)))

    def test_family_dispatch_cli_rejects_duplicate_json_keys_before_validation(self) -> None:
        duplicate_request = (
            b'{"contract_version":"choicegate.family-request/unsupported",'
            b'"contract_version":"choicegate.family-request/v1",'
            b'"request_id":"duplicate-contract-version","claims":[],"legacy_invocation":false}\n'
        )
        completed = subprocess.run(
            [sys.executable, "-B", str(self.root / "scripts" / "select_family_leaf.py"), "-"],
            input=duplicate_request,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        failure = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual("DUPLICATE_JSON_KEY", failure["error_code"])
        self.assertEqual(
            ["DUPLICATE_JSON_KEY: duplicate JSON key: contract_version"],
            completed.stderr.decode("utf-8").splitlines(),
        )

    def test_pairwise_collision_precedence_and_ambiguity_are_complete(self) -> None:
        collisions = self.cases["pairwise_collision_cases"]
        self.assertEqual(15, len(collisions))
        self.assertEqual(
            {frozenset(pair) for pair in combinations(DOMAINS, 2)},
            {frozenset((item["explicit"], item["inferred"])) for item in collisions},
        )
        for item in collisions:
            claims = [
                {"domain": item["explicit"], "specificity": "explicit", "evidence_id": f"{item['id']}-explicit"},
                {"domain": item["inferred"], "specificity": "inferred", "evidence_id": f"{item['id']}-inferred"},
            ]
            with self.subTest(case=item["id"], mode="explicit-precedence"):
                first = self.dispatcher.dispatch(family_request(item["id"], claims))
                second = self.dispatcher.dispatch(family_request(item["id"], list(reversed(claims))))
                self.assertEqual(first, second)
                self.assertEqual(item["expected_leaf"], first["decision"]["leaf_id"])
            ambiguous = copy.deepcopy(claims)
            for claim in ambiguous:
                claim["specificity"] = "inferred"
            with self.subTest(case=item["id"], mode="ambiguous-fail-closed"):
                receipt = self.dispatcher.dispatch(family_request(f"{item['id']}-ambiguous", ambiguous))
                self.assertEqual("no-safe-route", receipt["decision"]["route_type"])
                self.assertIsNone(receipt["decision"]["leaf_id"])
            competing_explicit = copy.deepcopy(claims)
            for claim in competing_explicit:
                claim["specificity"] = "explicit"
            with self.subTest(case=item["id"], mode="multiple-explicit-fail-closed"):
                receipt = self.dispatcher.dispatch(
                    family_request(f"{item['id']}-multiple-explicit", competing_explicit)
                )
                self.assertEqual("no-safe-route", receipt["decision"]["route_type"])
                self.assertIsNone(receipt["decision"]["leaf_id"])

    def test_legacy_alias_and_malformed_family_requests_fail_closed(self) -> None:
        legacy = self.dispatcher.dispatch(family_request("legacy-alias", [], legacy=True))
        self.assertEqual("choicegate", legacy["decision"]["leaf_id"])
        self.assertEqual("dispatcher", legacy["decision"]["route_type"])
        faults = (
            (
                family_request(
                    "legacy-collision",
                    [{"domain": "tools", "specificity": "explicit", "evidence_id": "tool-intent"}],
                    legacy=True,
                ),
                "LEGACY_ALIAS_COLLISION",
            ),
            (
                family_request(
                    "duplicate-domain",
                    [
                        {"domain": "tools", "specificity": "explicit", "evidence_id": "one"},
                        {"domain": "tools", "specificity": "inferred", "evidence_id": "two"},
                    ],
                ),
                "DUPLICATE_DOMAIN_CLAIM",
            ),
        )
        for request, code in faults:
            with self.subTest(code=code):
                with self.assertRaises(self.dispatcher.ContractError) as raised:
                    self.dispatcher.dispatch(request)
                self.assertEqual(code, raised.exception.code)

    def test_surface_adapters_bind_identical_canonical_family_and_leaf_bytes(self) -> None:
        manifests = {
            surface: read_json(self.root / "adapters" / surface / "manifest.json")
            for surface in ("codex", "claude-code")
        }
        family_path = self.root / "skills" / "family.json"
        family_sha = sha256_bytes(normalized_text_bytes(family_path))
        shared_fields = (
            "family",
            "canonical_owner",
            "canonical_hash_algorithm",
            "canonical_family_path",
            "canonical_family_sha256",
            "canonical_leaf_manifest_fingerprint",
            "shared_core_entrypoints",
            "skill_sources",
        )
        for surface, manifest in manifests.items():
            self.assertEqual(surface, manifest["surface"])
            self.assertEqual("sha256-utf8-lf-v1", manifest["canonical_hash_algorithm"])
            self.assertEqual(family_sha, manifest["canonical_family_sha256"])
            self.assertEqual(
                path_hash_fingerprint(self.root, manifest["skill_sources"]),
                manifest["canonical_leaf_manifest_fingerprint"],
            )
            for path in manifest["shared_core_entrypoints"]:
                self.assertTrue((self.root / path).is_file())
        self.assertEqual(
            {field: manifests["codex"][field] for field in shared_fields},
            {field: manifests["claude-code"][field] for field in shared_fields},
        )
        self.assertIn("invocation_metadata", manifests["codex"])
        self.assertNotIn("invocation_syntax", manifests["codex"])
        self.assertIn("invocation_syntax", manifests["claude-code"])
        self.assertNotIn("invocation_metadata", manifests["claude-code"])
        self.assertTrue((self.root / manifests["codex"]["invocation_metadata"]).is_file())


if __name__ == "__main__":
    unittest.main()
