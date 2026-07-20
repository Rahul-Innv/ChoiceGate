"""Build the self-contained synthetic request used by the public full-router demo."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evals" / "choicegate" / "sample-route-request.json"
COMPONENT_PATHS = (
    "evals/choicegate/inventory-fixtures.json",
    "evals/choicegate/manifest.json",
    "evals/choicegate/routing-cases.json",
    "registry/bundles.json",
    "registry/capabilities.json",
    "registry/conflicts.json",
    "registry/dependencies.json",
    "registry/preconditions.json",
    "registry/schemas/bundle.schema.json",
    "registry/schemas/capability.schema.json",
    "registry/schemas/conflict.schema.json",
    "registry/schemas/dependency.schema.json",
    "registry/schemas/precondition.schema.json",
    "registry/schemas/supersession.schema.json",
    "registry/state-axes.json",
    "registry/supersessions.json",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def component_documents() -> dict[str, Any]:
    empty_collections = {
        "registry/bundles.json": {"bundles": []},
        "registry/conflicts.json": {"conflicts": []},
        "registry/dependencies.json": {"dependencies": []},
        "registry/preconditions.json": {"preconditions": []},
        "registry/supersessions.json": {"supersessions": []},
    }
    schema_documents = {
        path: {"title": f"Synthetic public demo {Path(path).stem} schema"}
        for path in COMPONENT_PATHS
        if path.startswith("registry/schemas/")
    }
    return {
        "evals/choicegate/inventory-fixtures.json": {
            "fixtures": [
                {
                    "id": "public-demo",
                    "discoverable_ids": ["demo-local-formatter"],
                    "state_overrides": {},
                    "bundle_overrides": {},
                    "supersession_overrides": [],
                    "synthetic_candidates": [],
                    "task_contract": {"local_files_only": True},
                }
            ]
        },
        "evals/choicegate/manifest.json": {
            "profile": "public-demo-v1",
            "purpose": "synthetic full-router verification",
        },
        "evals/choicegate/routing-cases.json": {"cases": ["public-demo-selects-local-formatter"]},
        "registry/capabilities.json": {
            "capabilities": [
                {
                    "id": 1,
                    "name": "demo-local-formatter",
                    "owner": "choicegate-public-demo",
                    "kind": "local-cli",
                    "risk": "low",
                    "source_state": "local-project",
                    "install_state": "installed",
                    "enablement_state": "enabled",
                    "exposure_state": "project-exposed",
                    "authorization_state": "not-required",
                    "activity_state": "available",
                    "promotion_state": "candidate-validated",
                }
            ]
        },
        "registry/state-axes.json": {
            "model_id": "orthogonal-seven-axis-v1",
            "axes": {
                "source_state": ["local-project"],
                "install_state": ["installed"],
                "enablement_state": ["enabled"],
                "exposure_state": ["project-exposed"],
                "authorization_state": ["not-required"],
                "activity_state": ["available"],
                "promotion_state": ["candidate-validated"],
            },
        },
        **empty_collections,
        **schema_documents,
    }


def build_request() -> dict[str, Any]:
    documents = component_documents()
    if tuple(sorted(documents)) != COMPONENT_PATHS:
        raise RuntimeError("public demo component set drifted")
    components: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for path in COMPONENT_PATHS:
        content = canonical_bytes(documents[path])
        digest = sha256_bytes(content)
        hashes[path] = digest
        components.append({"path": path, "sha256": digest, "content_utf8": content.decode("utf-8")})
    manifest = "".join(f"{path}\t{hashes[path]}\n" for path in COMPONENT_PATHS).encode("utf-8")

    policy_without_hash = {
        "policy_version": "choicegate-router-policy/v1",
        "normal_ceiling": 8,
        "freshness_policy_id": "accepted-snapshot-explicit-v1",
        "explicit_owner_approved_setup_paths": [],
    }
    policy = {**policy_without_hash, "policy_sha256": sha256_bytes(canonical_bytes(policy_without_hash))}
    local_only = {
        "local_files_only": True,
        "write_files": False,
        "remote_actions": False,
        "outward_messages": False,
        "paid_actions": False,
        "provider_use": False,
        "provider_configuration": False,
    }
    return {
        "contract_version": "choicegate.route-request/v1",
        "request_id": "public-full-router-demo",
        "evaluation_time_utc": "2026-07-19T00:00:00Z",
        "task": {
            "task_class": "format-public-json",
            "required_outcomes": ["formatted-json"],
            "allowed_scope": local_only,
            "surface": "local",
            "private_data_class": "public",
            "authorization_required": False,
            "explicit_browser_choice": False,
            "intrinsic_visual_testing": False,
            "risk_class": "low",
            "max_discoverable_capabilities": 1,
            "allow_setup_choice": False,
            "fixture_scope": True,
            "fixture_id": "public-demo",
            "requested_route_ids": ["demo-local-formatter"],
            "preconditions": {},
            "selected_path_failed": False,
        },
        "candidate_evidence": [
            {
                "route_type": "atomic",
                "route_id": "demo-local-formatter",
                "canonical_route_id": "demo-local-formatter",
                "version": None,
                "task_class_match": True,
                "covers_required_outcomes": ["formatted-json"],
                "necessary_member_roles": [],
                "task_fit": 5,
                "context_cost": 1,
                "expected_cost": 0,
                "evidence_refs": ["registry/capabilities.json#demo-local-formatter"],
                "evidence_fresh": True,
                "risk_flags": [],
                "required_scope": local_only,
                "required_private_data_class": "public",
            }
        ],
        "inventory": {
            "schema_version": 1,
            "registry_profile": "public-demo-v1",
            "accepted_registry_commit": None,
            "state_model_id": "orthogonal-seven-axis-v1",
            "manifest_algorithm": "sha256-path-hash-manifest-v1",
            "manifest_fingerprint": sha256_bytes(manifest),
            "components": components,
        },
        "policy": policy,
    }


def rendered_request() -> str:
    return json.dumps(build_request(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the committed sample is stale")
    args = parser.parse_args()
    rendered = rendered_request()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("public route demo is stale; run tools/build_public_route_demo.py")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
