from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional developer dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "evals" / "choicegate" / "sample-route-request.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROUTER = load_module("choicegate_public_demo_router", ROOT / "scripts" / "route_capabilities.py")
BUILDER = load_module("choicegate_public_demo_builder", ROOT / "tools" / "build_public_route_demo.py")


class PublicRouteDemoTest(unittest.TestCase):
    def test_public_demo_exercises_full_router_and_rejects_profile_confusion(self) -> None:
        raw_text = SAMPLE_PATH.read_text(encoding="utf-8")
        request = json.loads(raw_text)
        self.assertEqual(raw_text, BUILDER.rendered_request())
        self.assertEqual(
            request["inventory"]["manifest_fingerprint"],
            ROUTER.PUBLIC_DEMO_INVENTORY_FINGERPRINT,
        )

        choicegate_commit = "a" * 40
        first = ROUTER.route_request(copy.deepcopy(request), choicegate_commit)
        second = ROUTER.route_request(copy.deepcopy(request), choicegate_commit)
        self.assertEqual(first, second)
        self.assertEqual(first["decision"], {
            "route_type": "atomic",
            "route_id": "demo-local-formatter",
            "version": None,
            "owner": "choicegate-public-demo",
            "executable": True,
            "reason": "highest-ranked-eligible-route",
        })
        self.assertEqual(first["inventory_binding"]["registry_profile"], "public-demo-v1")
        self.assertIsNone(first["inventory_binding"]["accepted_registry_commit"])
        claimed_receipt_hash = first.pop("receipt_sha256")
        self.assertEqual(claimed_receipt_hash, ROUTER.canonical_sha256(first))

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "route_capabilities.py"),
                str(SAMPLE_PATH),
                "--choicegate-commit",
                choicegate_commit,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["decision"]["route_id"], "demo-local-formatter")

        null_owner = copy.deepcopy(request)
        null_owner["inventory"].pop("registry_profile")
        with self.assertRaises(ROUTER.ContractError) as null_owner_error:
            ROUTER.route_request(null_owner, choicegate_commit)
        self.assertEqual(null_owner_error.exception.code, "INVALID_TYPE")

        string_demo = copy.deepcopy(request)
        string_demo["inventory"]["accepted_registry_commit"] = "b" * 40
        with self.assertRaises(ROUTER.ContractError) as string_demo_error:
            ROUTER.route_request(string_demo, choicegate_commit)
        self.assertEqual(string_demo_error.exception.code, "PUBLIC_DEMO_COMMIT_FORBIDDEN")

        owner_scope = copy.deepcopy(request)
        owner_scope["task"]["fixture_scope"] = False
        owner_scope["task"].pop("fixture_id")
        with self.assertRaises(ROUTER.ContractError) as scope_error:
            ROUTER.route_request(owner_scope, choicegate_commit)
        self.assertEqual(scope_error.exception.code, "PUBLIC_DEMO_SCOPE_REQUIRED")

        request_schema = json.loads((ROOT / "schemas" / "route-request.schema.json").read_text(encoding="utf-8"))
        receipt_schema = json.loads((ROOT / "schemas" / "decision-receipt.schema.json").read_text(encoding="utf-8"))
        for definition in (
            request_schema["$defs"]["inventory"],
            request_schema["$defs"]["priorInventoryBinding"],
            receipt_schema["$defs"]["inventoryBinding"],
        ):
            self.assertIn("allOf", definition)
            self.assertEqual(definition["properties"]["registry_profile"], {"const": "public-demo-v1"})

        if Draft202012Validator is not None:
            request_validator = Draft202012Validator(request_schema)
            self.assertEqual(list(request_validator.iter_errors(request)), [])
            self.assertNotEqual(list(request_validator.iter_errors(null_owner)), [])
            self.assertNotEqual(list(request_validator.iter_errors(string_demo)), [])
            receipt_validator = Draft202012Validator(receipt_schema)
            full_receipt = ROUTER.route_request(copy.deepcopy(request), choicegate_commit)
            self.assertEqual(list(receipt_validator.iter_errors(full_receipt)), [])
            invalid_owner_binding = copy.deepcopy(full_receipt)
            invalid_owner_binding["inventory_binding"].pop("registry_profile")
            self.assertNotEqual(list(receipt_validator.iter_errors(invalid_owner_binding)), [])
            invalid_demo_binding = copy.deepcopy(full_receipt)
            invalid_demo_binding["inventory_binding"]["accepted_registry_commit"] = "b" * 40
            self.assertNotEqual(list(receipt_validator.iter_errors(invalid_demo_binding)), [])


if __name__ == "__main__":
    unittest.main()
