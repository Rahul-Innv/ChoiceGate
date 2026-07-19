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

    def test_registry_profile_schema_and_runtime_parity(self) -> None:
        demo_request = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        request_schema = json.loads((ROOT / "schemas" / "route-request.schema.json").read_text(encoding="utf-8"))
        receipt_schema = json.loads((ROOT / "schemas" / "decision-receipt.schema.json").read_text(encoding="utf-8"))
        definitions = (
            request_schema["$defs"]["inventory"],
            request_schema["$defs"]["priorInventoryBinding"],
            receipt_schema["$defs"]["inventoryBinding"],
        )
        expected_condition = {
            "if": {
                "properties": {"registry_profile": {"const": "public-demo-v1"}},
                "required": ["registry_profile"],
            },
            "then": {"properties": {"accepted_registry_commit": {"type": "null"}}},
            "else": {"properties": {"accepted_registry_commit": {"$ref": "#/$defs/gitCommit"}}},
        }
        for definition in definitions:
            self.assertEqual(
                definition["properties"]["registry_profile"],
                {"enum": ["owner-accepted", "public-demo-v1"]},
            )
            self.assertEqual(definition["allOf"], [expected_condition])

        owner_commit = "b" * 40
        explicit_owner = copy.deepcopy(demo_request)
        explicit_owner["inventory"]["registry_profile"] = "owner-accepted"
        explicit_owner["inventory"]["accepted_registry_commit"] = owner_commit
        legacy_owner = copy.deepcopy(explicit_owner)
        legacy_owner["inventory"].pop("registry_profile")
        invalid_owner_null = copy.deepcopy(explicit_owner)
        invalid_owner_null["inventory"]["accepted_registry_commit"] = None
        invalid_demo_string = copy.deepcopy(demo_request)
        invalid_demo_string["inventory"]["accepted_registry_commit"] = owner_commit

        original_commit = ROUTER.ACCEPTED_REGISTRY_COMMIT
        original_fingerprint = ROUTER.ACCEPTED_INVENTORY_FINGERPRINT
        try:
            # Bind the synthetic component bytes as an owner fixture only for this parity test.
            ROUTER.ACCEPTED_REGISTRY_COMMIT = owner_commit
            ROUTER.ACCEPTED_INVENTORY_FINGERPRINT = demo_request["inventory"]["manifest_fingerprint"]
            receipts = {
                "demo": ROUTER.route_request(copy.deepcopy(demo_request), "a" * 40),
                "explicit_owner": ROUTER.route_request(copy.deepcopy(explicit_owner), "a" * 40),
                "legacy_owner": ROUTER.route_request(copy.deepcopy(legacy_owner), "a" * 40),
            }
            self.assertEqual(
                receipts["explicit_owner"]["inventory_binding"]["registry_profile"],
                "owner-accepted",
            )
            self.assertEqual(
                receipts["explicit_owner"]["inventory_binding"]["accepted_registry_commit"],
                owner_commit,
            )
            self.assertNotIn("registry_profile", receipts["legacy_owner"]["inventory_binding"])
            for receipt in receipts.values():
                ROUTER.validate_prior_receipt_envelope(copy.deepcopy(receipt))
            with self.assertRaises(ROUTER.ContractError):
                ROUTER.route_request(invalid_owner_null, "a" * 40)
            with self.assertRaises(ROUTER.ContractError):
                ROUTER.route_request(invalid_demo_string, "a" * 40)

            invalid_receipts = []
            invalid_explicit_receipt = copy.deepcopy(receipts["explicit_owner"])
            invalid_explicit_receipt["inventory_binding"]["accepted_registry_commit"] = None
            invalid_receipts.append(invalid_explicit_receipt)
            invalid_demo_receipt = copy.deepcopy(receipts["demo"])
            invalid_demo_receipt["inventory_binding"]["accepted_registry_commit"] = owner_commit
            invalid_receipts.append(invalid_demo_receipt)
            invalid_legacy_receipt = copy.deepcopy(receipts["legacy_owner"])
            invalid_legacy_receipt["inventory_binding"]["accepted_registry_commit"] = None
            invalid_receipts.append(invalid_legacy_receipt)
            for invalid_receipt in invalid_receipts:
                with self.assertRaises(ROUTER.ContractError):
                    ROUTER.validate_prior_receipt_envelope(copy.deepcopy(invalid_receipt))
        finally:
            ROUTER.ACCEPTED_REGISTRY_COMMIT = original_commit
            ROUTER.ACCEPTED_INVENTORY_FINGERPRINT = original_fingerprint

        if Draft202012Validator is not None:
            Draft202012Validator.check_schema(request_schema)
            Draft202012Validator.check_schema(receipt_schema)
            request_validator = Draft202012Validator(request_schema)
            receipt_validator = Draft202012Validator(receipt_schema)
            for valid_request in (demo_request, explicit_owner, legacy_owner):
                self.assertEqual(list(request_validator.iter_errors(valid_request)), [])
            for invalid_request in (invalid_owner_null, invalid_demo_string):
                self.assertNotEqual(list(request_validator.iter_errors(invalid_request)), [])
            for receipt in receipts.values():
                self.assertEqual(list(receipt_validator.iter_errors(receipt)), [])
                request_with_prior = copy.deepcopy(demo_request)
                request_with_prior["prior_receipt"] = receipt
                self.assertEqual(list(request_validator.iter_errors(request_with_prior)), [])

            for invalid_receipt in invalid_receipts:
                self.assertNotEqual(list(receipt_validator.iter_errors(invalid_receipt)), [])
                request_with_invalid_prior = copy.deepcopy(demo_request)
                request_with_invalid_prior["prior_receipt"] = invalid_receipt
                self.assertNotEqual(list(request_validator.iter_errors(request_with_invalid_prior)), [])


if __name__ == "__main__":
    unittest.main()
