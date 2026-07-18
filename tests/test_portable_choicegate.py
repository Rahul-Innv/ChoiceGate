from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "select_family_leaf.py"
SPEC = importlib.util.spec_from_file_location("choicegate_family_dispatch", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PortableChoicegateTests(unittest.TestCase):
    def request(self, claims: list[dict[str, str]], *, legacy: bool = False) -> dict:
        return {
            "contract_version": "choicegate.family-request/v1",
            "request_id": "portable-case",
            "claims": claims,
            "legacy_invocation": legacy,
        }

    def test_each_domain_has_one_exact_owner(self) -> None:
        expected = {
            "skills": "choicegate-skills",
            "tools": "choicegate-tools",
            "integrations": "choicegate-integrations",
            "generators": "choicegate-generators",
            "context": "choicegate-context",
            "refresh": "choicegate-refresh",
        }
        for domain, leaf in expected.items():
            with self.subTest(domain=domain):
                receipt = MODULE.dispatch(self.request([
                    {"domain": domain, "specificity": "explicit", "evidence_id": f"{domain}-evidence"}
                ]))
                self.assertEqual(receipt["decision"]["route_type"], "atomic-leaf")
                self.assertEqual(receipt["decision"]["leaf_id"], leaf)
                self.assertIn("receipt_sha256", receipt)

    def test_ambiguous_explicit_claims_fail_closed(self) -> None:
        receipt = MODULE.dispatch(self.request([
            {"domain": "skills", "specificity": "explicit", "evidence_id": "skills-evidence"},
            {"domain": "tools", "specificity": "explicit", "evidence_id": "tools-evidence"},
        ]))
        self.assertEqual(receipt["decision"], {
            "route_type": "no-safe-route",
            "leaf_id": None,
            "reason": "ambiguous-domain-claims",
        })

    def test_one_explicit_claim_precedes_inferred_claim(self) -> None:
        receipt = MODULE.dispatch(self.request([
            {"domain": "skills", "specificity": "inferred", "evidence_id": "skills-evidence"},
            {"domain": "tools", "specificity": "explicit", "evidence_id": "tools-evidence"},
        ]))
        self.assertEqual(receipt["decision"]["leaf_id"], "choicegate-tools")

    def test_legacy_alias_routes_only_to_dispatcher(self) -> None:
        receipt = MODULE.dispatch(self.request([], legacy=True))
        self.assertEqual(receipt["decision"], {
            "route_type": "dispatcher",
            "leaf_id": "choicegate",
            "reason": "explicit-legacy-alias",
        })

    def test_selection_never_grants_execution(self) -> None:
        receipt = MODULE.dispatch(self.request([
            {"domain": "integrations", "specificity": "explicit", "evidence_id": "integration-evidence"}
        ]))
        for action in ("authorize", "configure", "enable", "execute-selected-capability", "install"):
            self.assertIn(action, receipt["prohibited_actions"])


if __name__ == "__main__":
    unittest.main()
