#!/usr/bin/env python3
"""Route one hash-bound registry capability or approved bundle without side effects."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


ROUTER_VERSION = "choicegate-bundle-router/v1"
REQUEST_VERSION = "choicegate.route-request/v1"
RECEIPT_VERSION = "choicegate.decision-receipt/v1"
FAILURE_VERSION = "choicegate.route-failure/v1"
POLICY_VERSION = "choicegate-router-policy/v1"
FRESHNESS_POLICY = "accepted-snapshot-explicit-v1"
MANIFEST_ALGORITHM = "sha256-path-hash-manifest-v1"
ROUTER_TEXT_HASH_ALGORITHM = "sha256-utf8-lf-v1"
STATE_MODEL_ID = "orthogonal-seven-axis-v1"
ACCEPTED_REGISTRY_COMMIT = "354046f9627c4a83a2a912e09a656d1871ed6cc4"
ACCEPTED_INVENTORY_FINGERPRINT = "6ef1493691332e372106b652c991a4e9477c869d1a22e10af319845ae533198b"

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

STATE_AXES = (
    "source_state",
    "install_state",
    "enablement_state",
    "exposure_state",
    "authorization_state",
    "activity_state",
    "promotion_state",
)

PROHIBITED_ACTIONS = (
    "activate",
    "authorize",
    "browse-outside-explicit-exception",
    "configure-provider",
    "enable",
    "execute-selected-capability",
    "expose",
    "install",
    "modify-live-skill",
    "mutate-remote",
    "spend",
)

RESELECTION_TRIGGERS = (
    "authorization-changed",
    "availability-changed",
    "bundle-contract-changed",
    "evidence-freshness-changed",
    "inventory-fingerprint-changed",
    "owner-gate-changed",
    "permission-or-risk-changed",
    "router-binding-changed",
    "scope-changed",
    "selected-path-failed",
)

EXCLUSION_ORDER = (
    "UNSAFE_OR_UNVERIFIED",
    "NOT_PROMOTED_FOR_ROUTE",
    "STALE_EVIDENCE",
    "UNAVAILABLE_NO_APPROVED_SETUP",
    "SETUP_APPROVAL_REQUIRED",
    "AUTHORIZATION_MISMATCH",
    "SURFACE_MISMATCH",
    "DUPLICATE_CANONICAL_OWNER",
    "DEPENDENCY_UNSATISFIED",
    "PROVIDER_FAMILY_CONFLICT",
    "PRECONDITION_UNSATISFIED",
    "CONTEXT_BUDGET_EXCEEDED",
    "BUNDLE_NOT_APPROVED",
    "BUNDLE_MEMBER_UNAVAILABLE",
    "BUNDLE_UNNECESSARY",
    "SCOPE_OR_RISK_MISMATCH",
    "EXPLICIT_CHOICE_MISMATCH",
)

RISK_PENALTY = {
    "low": 0,
    "low-medium": 1,
    "medium": 2,
    "medium-high": 3,
    "high": 3,
    "critical": 4,
}

RISK_LEVEL = {
    "low": 0,
    "low-medium": 1,
    "medium": 2,
    "medium-high": 3,
    "high": 3,
    "critical": 4,
}

DATA_CLASS_LEVEL = {
    "none": 0,
    "public": 1,
    "private": 2,
    "sensitive": 3,
}

READY_PROMOTIONS = {
    "native-current",
    "policy-current",
    "baseline-implemented",
    "candidate-validated",
    "available",
}

FIXTURE_PROMOTIONS = READY_PROMOTIONS | {
    "cached-metadata",
    "planned",
    "selected-first-trial",
    "unregularized-no-paired-evidence",
}

LEGACY_STATUSES = {
    "installed_usable": 5,
    "requires_auth_or_config": 3,
    "available_to_install": 2,
    "unverified_or_risky": 0,
    "browser_or_manual_fallback": 0,
}
LEGACY_PROVENANCE = {
    "official_first_party": 5,
    "official_marketplace": 4,
    "verified_maintainer": 4,
    "community": 2,
    "unknown": 0,
}
LEGACY_RATING_WEIGHTS = {
    "task_fit": 6,
    "maintenance": 3,
    "least_privilege": 4,
    "data_access": 3,
    "privacy": 4,
    "security": 4,
    "cost": 2,
    "rate_limits": 1,
    "installation_friction": 2,
    "platform_compatibility": 3,
    "non_overlap": 3,
    "improvement_over_fallback": 5,
}
LEGACY_HARD_FLAGS = {
    "unsafe",
    "account_evasion",
    "requires_paid_action",
    "would_expose_secrets",
    "unverified_claims",
}

STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
UTC_RE = re.compile(
    r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T"
    r"([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]+)?Z$"
)


class ContractError(ValueError):
    """A deterministic caller, schema, hash, or invariant failure."""

    def __init__(self, code: str, message: str, details: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = tuple(sorted(str(item) for item in details))


class CandidateError(ValueError):
    """Backward-compatible discovery-candidate validation failure."""


def canonical_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ContractError("NON_CANONICAL_JSON", str(error)) from error
    return rendered.encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _reject_constant(value: str) -> None:
    raise ContractError("INVALID_JSON_NUMBER", f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: str, label: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except json.JSONDecodeError as error:
        raise ContractError(
            "INVALID_JSON",
            f"{label}: {error.msg} at line {error.lineno} column {error.colno}",
        ) from error


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("INVALID_TYPE", f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError("INVALID_TYPE", f"{label} must be an array")
    return value


def exact_keys(
    value: dict[str, Any],
    required: Iterable[str],
    optional: Iterable[str],
    label: str,
) -> None:
    required_set = set(required)
    optional_set = set(optional)
    actual = set(value)
    missing = sorted(required_set - actual)
    unknown = sorted(actual - required_set - optional_set)
    if missing or unknown:
        details = [*(f"missing:{item}" for item in missing), *(f"unknown:{item}" for item in unknown)]
        raise ContractError("STRICT_SCHEMA_VIOLATION", f"{label} has invalid fields", details)


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError("INVALID_TYPE", f"{label} must be boolean")
    return value


def require_int(value: Any, label: str, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError("INVALID_TYPE", f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ContractError("INVALID_VALUE", f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ContractError("INVALID_VALUE", f"{label} must be at most {maximum}")
    return value


def require_number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("INVALID_TYPE", f"{label} must be numeric")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ContractError("INVALID_VALUE", f"{label} must be between {minimum} and {maximum}")
    return result


def require_string(value: Any, label: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError("INVALID_TYPE", f"{label} must be a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ContractError("INVALID_VALUE", f"{label} has an invalid format")
    return value


def require_enum(value: Any, allowed: set[str], label: str) -> str:
    result = require_string(value, label)
    if result not in allowed:
        raise ContractError("INVALID_ENUM", f"{label} is not allowed: {result}")
    return result


def require_string_set(value: Any, label: str, allow_empty: bool = True) -> list[str]:
    items = require_list(value, label)
    if not allow_empty and not items:
        raise ContractError("INVALID_VALUE", f"{label} must not be empty")
    result = [require_string(item, f"{label}[{index}]", STABLE_ID) for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise ContractError("DUPLICATE_ID", f"{label} contains duplicates")
    return result


def validate_allowed_scope(raw: Any, label: str) -> dict[str, bool]:
    value = require_object(raw, label)
    fields = (
        "local_files_only",
        "write_files",
        "remote_actions",
        "outward_messages",
        "paid_actions",
        "provider_use",
        "provider_configuration",
    )
    exact_keys(value, fields, (), label)
    return {field: require_bool(value[field], f"{label}.{field}") for field in fields}


def validate_task(raw: Any) -> dict[str, Any]:
    value = require_object(raw, "task")
    required = (
        "task_class",
        "required_outcomes",
        "allowed_scope",
        "surface",
        "private_data_class",
        "authorization_required",
        "explicit_browser_choice",
        "intrinsic_visual_testing",
        "risk_class",
        "max_discoverable_capabilities",
        "allow_setup_choice",
        "fixture_scope",
        "requested_route_ids",
        "preconditions",
        "selected_path_failed",
    )
    optional = ("fixture_id", "owner_selected_route_id")
    exact_keys(value, required, optional, "task")
    task = copy.deepcopy(value)
    require_string(task["task_class"], "task.task_class", STABLE_ID)
    require_string_set(task["required_outcomes"], "task.required_outcomes", allow_empty=False)
    task["allowed_scope"] = validate_allowed_scope(task["allowed_scope"], "task.allowed_scope")
    require_enum(task["surface"], {"codex", "claude-code", "local", "browser", "manual"}, "task.surface")
    require_enum(task["private_data_class"], {"none", "public", "private", "sensitive"}, "task.private_data_class")
    require_bool(task["authorization_required"], "task.authorization_required")
    require_bool(task["explicit_browser_choice"], "task.explicit_browser_choice")
    require_bool(task["intrinsic_visual_testing"], "task.intrinsic_visual_testing")
    require_enum(task["risk_class"], {"low", "low-medium", "medium", "high", "critical"}, "task.risk_class")
    require_int(task["max_discoverable_capabilities"], "task.max_discoverable_capabilities", 1, 12)
    require_bool(task["allow_setup_choice"], "task.allow_setup_choice")
    fixture_scope = require_bool(task["fixture_scope"], "task.fixture_scope")
    if fixture_scope:
        require_string(task.get("fixture_id"), "task.fixture_id", STABLE_ID)
    elif "fixture_id" in task:
        raise ContractError("STRICT_SCHEMA_VIOLATION", "task.fixture_id requires fixture_scope")
    require_string_set(task["requested_route_ids"], "task.requested_route_ids")
    preconditions = require_object(task["preconditions"], "task.preconditions")
    for key, item in preconditions.items():
        require_string(key, "task.preconditions key", STABLE_ID)
        if isinstance(item, (dict, list)) or item is None:
            raise ContractError("INVALID_TYPE", f"task.preconditions.{key} must be scalar")
    require_bool(task["selected_path_failed"], "task.selected_path_failed")
    if "owner_selected_route_id" in task:
        require_string(task["owner_selected_route_id"], "task.owner_selected_route_id", STABLE_ID)
    elif task["selected_path_failed"]:
        raise ContractError("STRICT_SCHEMA_VIOLATION", "selected_path_failed requires owner_selected_route_id")
    return task


def validate_candidate(raw: Any, index: int) -> dict[str, Any]:
    label = f"candidate_evidence[{index}]"
    value = require_object(raw, label)
    required = (
        "route_type",
        "route_id",
        "canonical_route_id",
        "version",
        "task_class_match",
        "covers_required_outcomes",
        "necessary_member_roles",
        "task_fit",
        "context_cost",
        "expected_cost",
        "evidence_refs",
        "evidence_fresh",
        "risk_flags",
        "required_scope",
        "required_private_data_class",
    )
    exact_keys(value, required, (), label)
    candidate = copy.deepcopy(value)
    require_enum(candidate["route_type"], {"atomic", "bundle"}, f"{label}.route_type")
    require_string(candidate["route_id"], f"{label}.route_id", STABLE_ID)
    require_string(candidate["canonical_route_id"], f"{label}.canonical_route_id", STABLE_ID)
    if candidate["version"] is not None:
        require_string(candidate["version"], f"{label}.version")
    require_bool(candidate["task_class_match"], f"{label}.task_class_match")
    require_string_set(candidate["covers_required_outcomes"], f"{label}.covers_required_outcomes")
    require_string_set(candidate["necessary_member_roles"], f"{label}.necessary_member_roles")
    candidate["task_fit"] = require_number(candidate["task_fit"], f"{label}.task_fit", 0, 5)
    candidate["context_cost"] = require_number(candidate["context_cost"], f"{label}.context_cost", 0, 5)
    candidate["expected_cost"] = require_number(candidate["expected_cost"], f"{label}.expected_cost", 0, 5)
    refs = require_list(candidate["evidence_refs"], f"{label}.evidence_refs")
    if not refs or any(not isinstance(item, str) or not item for item in refs):
        raise ContractError("INVALID_VALUE", f"{label}.evidence_refs requires non-empty strings")
    if len(set(refs)) != len(refs):
        raise ContractError("DUPLICATE_ID", f"{label}.evidence_refs contains duplicates")
    require_bool(candidate["evidence_fresh"], f"{label}.evidence_fresh")
    flags = require_string_set(candidate["risk_flags"], f"{label}.risk_flags")
    unknown_flags = sorted(set(flags) - {
        "account-evasion",
        "critical-unresolved-risk",
        "secret-exposure",
        "unsafe",
        "unreviewed-setup",
        "unverified-claim",
    })
    if unknown_flags:
        raise ContractError("INVALID_ENUM", f"{label}.risk_flags contains unknown values", unknown_flags)
    candidate["required_scope"] = validate_allowed_scope(candidate["required_scope"], f"{label}.required_scope")
    require_enum(
        candidate["required_private_data_class"],
        set(DATA_CLASS_LEVEL),
        f"{label}.required_private_data_class",
    )
    return candidate


def validate_setup_path(raw: Any, index: int) -> dict[str, Any]:
    label = f"policy.explicit_owner_approved_setup_paths[{index}]"
    value = require_object(raw, label)
    fields = ("route_id", "approval_ids", "reversible", "reviewed_instructions", "allowed_actions")
    exact_keys(value, fields, (), label)
    result = copy.deepcopy(value)
    require_string(result["route_id"], f"{label}.route_id", STABLE_ID)
    require_string_set(result["approval_ids"], f"{label}.approval_ids", allow_empty=False)
    if require_bool(result["reversible"], f"{label}.reversible") is not True:
        raise ContractError("INVALID_VALUE", f"{label}.reversible must be true")
    if require_bool(result["reviewed_instructions"], f"{label}.reviewed_instructions") is not True:
        raise ContractError("INVALID_VALUE", f"{label}.reviewed_instructions must be true")
    actions = require_string_set(result["allowed_actions"], f"{label}.allowed_actions", allow_empty=False)
    if set(actions) - {"install", "enable", "expose", "authorize", "configure"}:
        raise ContractError("INVALID_ENUM", f"{label}.allowed_actions contains an unknown action")
    return result


def validate_policy(raw: Any) -> dict[str, Any]:
    value = require_object(raw, "policy")
    fields = (
        "policy_version",
        "normal_ceiling",
        "freshness_policy_id",
        "explicit_owner_approved_setup_paths",
        "policy_sha256",
    )
    exact_keys(value, fields, (), "policy")
    policy = copy.deepcopy(value)
    if policy["policy_version"] != POLICY_VERSION or policy["freshness_policy_id"] != FRESHNESS_POLICY:
        raise ContractError("UNSUPPORTED_POLICY", "policy version or freshness policy is not supported")
    require_int(policy["normal_ceiling"], "policy.normal_ceiling", 8, 12)
    setup_raw = require_list(policy["explicit_owner_approved_setup_paths"], "policy.explicit_owner_approved_setup_paths")
    policy["explicit_owner_approved_setup_paths"] = [validate_setup_path(item, index) for index, item in enumerate(setup_raw)]
    route_ids = [item["route_id"] for item in policy["explicit_owner_approved_setup_paths"]]
    if len(set(route_ids)) != len(route_ids):
        raise ContractError("DUPLICATE_ID", "policy setup paths contain duplicate route IDs")
    require_string(policy["policy_sha256"], "policy.policy_sha256", SHA256_RE)
    hash_input = {key: item for key, item in policy.items() if key != "policy_sha256"}
    expected = canonical_sha256(hash_input)
    if policy["policy_sha256"] != expected:
        raise ContractError("POLICY_HASH_MISMATCH", "policy_sha256 does not match canonical policy", [expected])
    return policy


def validate_inventory_envelope(raw: Any) -> dict[str, Any]:
    value = require_object(raw, "inventory")
    fields = (
        "schema_version",
        "accepted_registry_commit",
        "state_model_id",
        "manifest_algorithm",
        "manifest_fingerprint",
        "components",
    )
    exact_keys(value, fields, (), "inventory")
    inventory = copy.deepcopy(value)
    if inventory["schema_version"] != 1:
        raise ContractError("UNSUPPORTED_INVENTORY_SCHEMA", "inventory.schema_version must be 1")
    require_string(inventory["accepted_registry_commit"], "inventory.accepted_registry_commit", GIT_COMMIT_RE)
    if inventory["accepted_registry_commit"] != ACCEPTED_REGISTRY_COMMIT:
        raise ContractError("INVENTORY_COMMIT_MISMATCH", "inventory commit is not the accepted registry commit")
    if inventory["state_model_id"] != STATE_MODEL_ID:
        raise ContractError("STATE_MODEL_MISMATCH", "inventory state model is not accepted")
    if inventory["manifest_algorithm"] != MANIFEST_ALGORITHM:
        raise ContractError("MANIFEST_ALGORITHM_MISMATCH", "inventory manifest algorithm is not supported")
    require_string(inventory["manifest_fingerprint"], "inventory.manifest_fingerprint", SHA256_RE)
    components = require_list(inventory["components"], "inventory.components")
    if len(components) != len(COMPONENT_PATHS):
        raise ContractError("INVENTORY_COMPONENT_SET_MISMATCH", "inventory requires exactly 16 components")
    parsed: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for index, raw_component in enumerate(components):
        label = f"inventory.components[{index}]"
        component = require_object(raw_component, label)
        exact_keys(component, ("path", "sha256", "content_utf8"), (), label)
        path = require_string(component["path"], f"{label}.path")
        digest = require_string(component["sha256"], f"{label}.sha256", SHA256_RE)
        content = require_string(component["content_utf8"], f"{label}.content_utf8")
        if path in parsed:
            raise ContractError("DUPLICATE_ID", f"duplicate inventory component: {path}")
        actual = sha256_bytes(content.encode("utf-8"))
        if actual != digest:
            raise ContractError("COMPONENT_HASH_MISMATCH", f"component hash mismatch: {path}", [actual])
        parsed[path] = strict_json_loads(content, path)
        hashes[path] = digest
    if tuple(sorted(parsed)) != COMPONENT_PATHS:
        missing = sorted(set(COMPONENT_PATHS) - set(parsed))
        extra = sorted(set(parsed) - set(COMPONENT_PATHS))
        raise ContractError(
            "INVENTORY_COMPONENT_SET_MISMATCH",
            "inventory component paths differ from the accepted manifest",
            [*(f"missing:{item}" for item in missing), *(f"extra:{item}" for item in extra)],
        )
    manifest = "".join(f"{path}\t{hashes[path]}\n" for path in sorted(hashes)).encode("utf-8")
    fingerprint = sha256_bytes(manifest)
    if fingerprint != inventory["manifest_fingerprint"] or fingerprint != ACCEPTED_INVENTORY_FINGERPRINT:
        raise ContractError("INVENTORY_FINGERPRINT_MISMATCH", "inventory fingerprint is not the accepted registry fingerprint", [fingerprint])
    inventory["parsed_components"] = parsed
    inventory["component_hashes"] = hashes
    return inventory


def validate_evidence_references(candidates: list[dict[str, Any]], inventory: dict[str, Any]) -> None:
    declared_paths = set(inventory["component_hashes"])

    def identifiers(value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"id", "name"} and isinstance(item, (str, int)):
                    found.add(str(item))
                found.update(identifiers(item))
        elif isinstance(value, list):
            for item in value:
                found.update(identifiers(item))
        return found

    for index, candidate in enumerate(candidates):
        required_base = "registry/bundles.json" if candidate["route_type"] == "bundle" else "registry/capabilities.json"
        required_reference = f"{required_base}#{candidate['canonical_route_id']}"
        if required_reference not in candidate["evidence_refs"]:
            raise ContractError(
                "UNDECLARED_EVIDENCE_REFERENCE",
                f"candidate_evidence[{index}] lacks its canonical registry evidence reference",
                [required_reference],
            )
        for ref_index, reference in enumerate(candidate["evidence_refs"]):
            base, marker, fragment = reference.partition("#")
            fragment_valid = not marker or (
                bool(fragment)
                and fragment in identifiers(inventory["parsed_components"][base])
            ) if base in declared_paths else False
            if base not in declared_paths or not fragment_valid:
                raise ContractError(
                    "UNDECLARED_EVIDENCE_REFERENCE",
                    f"candidate_evidence[{index}].evidence_refs[{ref_index}] is not bound to an inventory component",
                    [reference],
                )


def validate_request(raw: Any) -> dict[str, Any]:
    value = require_object(raw, "request")
    required = (
        "contract_version",
        "request_id",
        "evaluation_time_utc",
        "task",
        "candidate_evidence",
        "inventory",
        "policy",
    )
    exact_keys(value, required, ("prior_receipt",), "request")
    if value["contract_version"] != REQUEST_VERSION:
        raise ContractError("UNSUPPORTED_REQUEST_VERSION", "contract_version is not supported")
    require_string(value["request_id"], "request.request_id", STABLE_ID)
    evaluation_time = require_string(value["evaluation_time_utc"], "request.evaluation_time_utc", UTC_RE)
    try:
        datetime.fromisoformat(evaluation_time[:-1] + "+00:00")
    except ValueError as error:
        raise ContractError("INVALID_TIMESTAMP", "request.evaluation_time_utc is not a real UTC calendar time") from error
    candidates_raw = require_list(value["candidate_evidence"], "request.candidate_evidence")
    if len(candidates_raw) > 12:
        raise ContractError("CONTEXT_BUDGET_EXCEEDED", "candidate_evidence exceeds the normal ceiling")
    candidates = [validate_candidate(item, index) for index, item in enumerate(candidates_raw)]
    route_ids = [item["route_id"] for item in candidates]
    if len(set(route_ids)) != len(route_ids):
        raise ContractError("DUPLICATE_ID", "candidate_evidence contains duplicate route IDs")
    request = copy.deepcopy(value)
    request["task"] = validate_task(value["task"])
    request["candidate_evidence"] = candidates
    request["inventory"] = validate_inventory_envelope(value["inventory"])
    validate_evidence_references(candidates, request["inventory"])
    request["policy"] = validate_policy(value["policy"])
    if "prior_receipt" in request:
        validate_prior_receipt_envelope(require_object(request["prior_receipt"], "request.prior_receipt"))
    return request


def collection(component: Any, key: str, label: str) -> list[dict[str, Any]]:
    value = require_object(component, label)
    items = require_list(value.get(key), f"{label}.{key}")
    if any(not isinstance(item, dict) for item in items):
        raise ContractError("INVALID_REGISTRY", f"{label}.{key} must contain objects")
    return copy.deepcopy(items)


def unique_map(items: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        item_id = require_string(item.get(key), f"{label}[{index}].{key}", STABLE_ID)
        if item_id in result:
            raise ContractError("DUPLICATE_ID", f"duplicate {label} {key}: {item_id}")
        result[item_id] = item
    return result


def validate_state_record(record: dict[str, Any], axes: dict[str, list[str]], label: str) -> None:
    for axis in STATE_AXES:
        state = require_string(record.get(axis), f"{label}.{axis}")
        if state not in axes[axis]:
            raise ContractError("INVALID_STATE_VALUE", f"{label}.{axis} is not in the accepted state model: {state}")


def validate_dependency_cycles(dependencies: dict[str, dict[str, Any]], nodes: set[tuple[str, str]]) -> None:
    graph: dict[tuple[str, str], set[tuple[str, str]]] = {node: set() for node in nodes}
    for edge in dependencies.values():
        if edge.get("requirement") != "hard":
            continue
        source = (str(edge.get("from_type")), str(edge.get("from_id")))
        target = (str(edge.get("to_type")), str(edge.get("to_id")))
        graph[source].add(target)
    visiting: set[tuple[str, str]] = set()
    visited: set[tuple[str, str]] = set()

    def visit(node: tuple[str, str]) -> None:
        if node in visiting:
            raise ContractError("DEPENDENCY_CYCLE", f"hard dependency cycle at {node[0]}:{node[1]}")
        if node in visited:
            return
        visiting.add(node)
        for target in sorted(graph[node]):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node)


def lifecycle_is_ready(lifecycle: dict[str, Any]) -> bool:
    return (
        lifecycle.get("install_state") in {"installed", "not-applicable"}
        and lifecycle.get("enablement_state") in {"enabled", "not-applicable"}
        and lifecycle.get("exposure_state") in {
            "project-exposed",
            "surface-exposed",
            "session-exposed",
            "not-applicable",
        }
        and lifecycle.get("authorization_state") in {"authorized", "not-required"}
        and lifecycle.get("activity_state") in {"available", "active", "invoked-this-task"}
        and lifecycle.get("promotion_state") in READY_PROMOTIONS
    )


def validate_family_authority_record(name: str, record: dict[str, Any]) -> None:
    domain_owners = record.get("domain_owners")
    if domain_owners is not None:
        if not isinstance(domain_owners, list):
            raise ContractError("INVALID_FAMILY_AUTHORITY", f"capabilities.{name}.domain_owners must be an array")
        mapped = {
            str(item.get("domain")): str(item.get("owner"))
            for item in domain_owners
            if isinstance(item, dict)
        }
        if len(mapped) != len(domain_owners):
            raise ContractError("INVALID_FAMILY_AUTHORITY", f"capabilities.{name}.domain_owners are not unique objects")
        if name == "capability-selection-gate" and mapped != {
            "api-mcp-sdk-plugin-connector": "choicegate-integrations",
            "local-cli-executable-script": "choicegate-tools",
        }:
            raise ContractError("INVALID_FAMILY_AUTHORITY", "Choicegate domain ownership differs from the accepted split")

    aliases = record.get("compatibility_aliases")
    if aliases is not None:
        if not isinstance(aliases, list):
            raise ContractError("INVALID_COMPATIBILITY_ALIAS", f"capabilities.{name}.compatibility_aliases must be an array")
        alias_names: set[str] = set()
        for index, item in enumerate(aliases):
            if not isinstance(item, dict):
                raise ContractError("INVALID_COMPATIBILITY_ALIAS", f"capabilities.{name}.compatibility_aliases[{index}] is invalid")
            alias_name = require_string(item.get("name"), f"capabilities.{name}.compatibility_aliases[{index}].name", STABLE_ID)
            if alias_name in alias_names:
                raise ContractError("INVALID_COMPATIBILITY_ALIAS", f"duplicate compatibility alias: {alias_name}")
            alias_names.add(alias_name)
            if item.get("authority_role") != "compatibility-alias" or item.get("transition_state") != "pending-separate-promotion":
                raise ContractError("INVALID_COMPATIBILITY_ALIAS", f"compatibility alias is not fail-closed: {alias_name}")
        if name == "capability-selection-gate" and alias_names != {"discover-better-tools"}:
            raise ContractError("INVALID_COMPATIBILITY_ALIAS", "Choicegate legacy alias binding differs from the accepted authority")

    editions = record.get("editions")
    if editions is None:
        return
    if not isinstance(editions, list) or len(editions) < 2:
        raise ContractError("INVALID_EDITION_POLICY", f"capabilities.{name}.editions must contain at least two editions")
    edition_map: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(editions):
        if not isinstance(item, dict):
            raise ContractError("INVALID_EDITION_POLICY", f"capabilities.{name}.editions[{index}] is invalid")
        edition_id = require_string(item.get("id"), f"capabilities.{name}.editions[{index}].id", STABLE_ID)
        if edition_id in edition_map:
            raise ContractError("INVALID_EDITION_POLICY", f"duplicate edition: {edition_id}")
        lifecycle = require_object(item.get("lifecycle"), f"capabilities.{name}.editions[{index}].lifecycle")
        edition_map[edition_id] = lifecycle
    policy = require_object(record.get("edition_policy"), f"capabilities.{name}.edition_policy")
    if (
        policy.get("maximum_active_per_surface") != 1
        or policy.get("simultaneous_eligibility") != "forbidden"
        or policy.get("selection_authority") != record.get("owner")
        or policy.get("default_edition") not in edition_map
    ):
        raise ContractError("INVALID_EDITION_POLICY", f"capabilities.{name} edition authority is not fail-closed")
    active_editions = [edition_id for edition_id, lifecycle in edition_map.items() if lifecycle_is_ready(lifecycle)]
    if len(active_editions) > 1:
        raise ContractError("EDITION_EXCLUSIVITY_VIOLATION", f"capabilities.{name} has multiple eligible editions")

    adapters = record.get("surface_adapters", [])
    adapter_surfaces = {
        str(item.get("surface"))
        for item in adapters
        if isinstance(item, dict)
    }
    surface_policies = record.get("surface_policies")
    if not isinstance(surface_policies, list):
        raise ContractError("INVALID_SURFACE_POLICY", f"capabilities.{name}.surface_policies must be an array")
    policy_map: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(surface_policies):
        if not isinstance(item, dict):
            raise ContractError("INVALID_SURFACE_POLICY", f"capabilities.{name}.surface_policies[{index}] is invalid")
        surface = str(item.get("surface"))
        if surface in policy_map:
            raise ContractError("INVALID_SURFACE_POLICY", f"duplicate surface policy: {surface}")
        policy_map[surface] = item
    if set(policy_map) != {"claude-code", "codex"}:
        raise ContractError("INVALID_SURFACE_POLICY", f"capabilities.{name} must declare both supported local surfaces")
    for surface, item in policy_map.items():
        route_policy = item.get("route_policy")
        qualification = item.get("qualification_state")
        if route_policy == "edition-adapter":
            if surface not in adapter_surfaces or qualification != "qualified-current":
                raise ContractError("INVALID_SURFACE_POLICY", f"capabilities.{name}.{surface} adapter is not qualified")
        elif route_policy == "no-safe-route":
            if surface in adapter_surfaces or qualification != "unqualified":
                raise ContractError("INVALID_SURFACE_POLICY", f"capabilities.{name}.{surface} no-safe-route policy leaks an adapter")
        else:
            raise ContractError("INVALID_SURFACE_POLICY", f"capabilities.{name}.{surface} route policy is invalid")


def build_registry(request: dict[str, Any]) -> dict[str, Any]:
    parsed = request["inventory"]["parsed_components"]
    axes_doc = require_object(parsed["registry/state-axes.json"], "registry/state-axes.json")
    if axes_doc.get("model_id") != STATE_MODEL_ID:
        raise ContractError("STATE_MODEL_MISMATCH", "state-axes.json does not declare the accepted model")
    axes_raw = require_object(axes_doc.get("axes"), "registry/state-axes.json.axes")
    if set(axes_raw) != set(STATE_AXES):
        raise ContractError("INVALID_REGISTRY", "state-axes.json must contain exactly seven axes")
    axes: dict[str, list[str]] = {}
    for axis in STATE_AXES:
        values = require_list(axes_raw[axis], f"state-axes.{axis}")
        if any(not isinstance(item, str) or not item for item in values) or len(set(values)) != len(values):
            raise ContractError("INVALID_REGISTRY", f"state-axes.{axis} must be a unique string list")
        axes[axis] = list(values)

    capabilities = unique_map(
        collection(parsed["registry/capabilities.json"], "capabilities", "registry/capabilities.json"),
        "name",
        "capabilities",
    )
    numeric_ids: set[int] = set()
    for name, record in capabilities.items():
        numeric_id = require_int(record.get("id"), f"capabilities.{name}.id", 1)
        if numeric_id in numeric_ids:
            raise ContractError("DUPLICATE_ID", f"duplicate numeric capability ID: {numeric_id}")
        numeric_ids.add(numeric_id)
        require_string(record.get("owner"), f"capabilities.{name}.owner")
        require_string(record.get("kind"), f"capabilities.{name}.kind")
        require_enum(record.get("risk"), set(RISK_PENALTY), f"capabilities.{name}.risk")
        validate_state_record(record, axes, f"capabilities.{name}")
        validate_family_authority_record(name, record)

    bundles = unique_map(
        collection(parsed["registry/bundles.json"], "bundles", "registry/bundles.json"),
        "id",
        "bundles",
    )
    dependencies = unique_map(
        collection(parsed["registry/dependencies.json"], "dependencies", "registry/dependencies.json"),
        "id",
        "dependencies",
    )
    conflicts = unique_map(
        collection(parsed["registry/conflicts.json"], "conflicts", "registry/conflicts.json"),
        "id",
        "conflicts",
    )
    preconditions = unique_map(
        collection(parsed["registry/preconditions.json"], "preconditions", "registry/preconditions.json"),
        "id",
        "preconditions",
    )
    supersessions = unique_map(
        collection(parsed["registry/supersessions.json"], "supersessions", "registry/supersessions.json"),
        "id",
        "supersessions",
    )

    def endpoint_exists(kind: Any, identifier: Any, label: str) -> None:
        kind_value = require_enum(kind, {"capability", "bundle"}, f"{label}.type")
        identifier_value = require_string(identifier, f"{label}.id", STABLE_ID)
        target = capabilities if kind_value == "capability" else bundles
        if identifier_value not in target:
            raise ContractError("MISSING_REFERENCE", f"{label} references missing {kind_value}: {identifier_value}")

    for edge_id, edge in dependencies.items():
        endpoint_exists(edge.get("from_type"), edge.get("from_id"), f"dependencies.{edge_id}.from")
        endpoint_exists(edge.get("to_type"), edge.get("to_id"), f"dependencies.{edge_id}.to")
        require_enum(edge.get("requirement"), {"hard", "optional"}, f"dependencies.{edge_id}.requirement")
    for edge_id, edge in conflicts.items():
        endpoint_exists(edge.get("left_type"), edge.get("left_id"), f"conflicts.{edge_id}.left")
        endpoint_exists(edge.get("right_type"), edge.get("right_id"), f"conflicts.{edge_id}.right")
        canonical_id = edge.get("canonical_id")
        if canonical_id is not None:
            if (
                canonical_id not in capabilities
                or canonical_id not in {edge.get("left_id"), edge.get("right_id")}
                or edge.get("authority_policy") != "explicit-owner-selection-required"
            ):
                raise ContractError("INVALID_OWNER_COLLISION_POLICY", f"conflicts.{edge_id} does not fail closed")
            other_id = edge.get("right_id") if edge.get("left_id") == canonical_id else edge.get("left_id")
            other = capabilities.get(str(other_id))
            if other is None or other.get("authority_role") != "noncanonical-conflict":
                raise ContractError("INVALID_OWNER_COLLISION_POLICY", f"conflicts.{edge_id} does not bind a noncanonical collision")
    for edge_id, edge in preconditions.items():
        endpoint_exists(edge.get("applies_to_type"), edge.get("applies_to_id"), f"preconditions.{edge_id}.target")
        require_object(edge.get("required"), f"preconditions.{edge_id}.required")
    for edge_id, edge in supersessions.items():
        endpoint_exists(edge.get("predecessor_type"), edge.get("predecessor_id"), f"supersessions.{edge_id}.predecessor")
        endpoint_exists(edge.get("successor_type"), edge.get("successor_id"), f"supersessions.{edge_id}.successor")
        effective = require_bool(edge.get("effective"), f"supersessions.{edge_id}.effective")
        state = require_enum(edge.get("state"), {"proposed", "approved", "rejected", "rolled-back"}, f"supersessions.{edge_id}.state")
        if effective and state != "approved":
            raise ContractError("INVALID_SUPERSESSION", f"effective supersession is not approved: {edge_id}")

    nodes = {*(('capability', item) for item in capabilities), *(('bundle', item) for item in bundles)}
    validate_dependency_cycles(dependencies, nodes)

    for bundle_id, bundle in bundles.items():
        require_string(bundle.get("version"), f"bundles.{bundle_id}.version")
        validate_state_record(bundle, axes, f"bundles.{bundle_id}")
        members = require_list(bundle.get("members"), f"bundles.{bundle_id}.members")
        orders: list[int] = []
        member_ids: list[str] = []
        for index, member_raw in enumerate(members):
            member = require_object(member_raw, f"bundles.{bundle_id}.members[{index}]")
            orders.append(require_int(member.get("order"), f"bundles.{bundle_id}.members[{index}].order", 1))
            member_id = require_string(member.get("capability_id"), f"bundles.{bundle_id}.members[{index}].capability_id", STABLE_ID)
            if member_id not in capabilities:
                raise ContractError("MISSING_REFERENCE", f"bundle {bundle_id} has missing member: {member_id}")
            member_ids.append(member_id)
            require_enum(member.get("requirement"), {"required", "optional"}, f"bundles.{bundle_id}.members[{index}].requirement")
            require_string(member.get("role"), f"bundles.{bundle_id}.members[{index}].role", STABLE_ID)
        if orders != list(range(1, len(orders) + 1)) or len(set(member_ids)) != len(member_ids):
            raise ContractError("INVALID_BUNDLE_ORDER", f"bundle {bundle_id} member order or identity is invalid")
        for field, known in (
            ("dependency_ids", dependencies),
            ("conflict_ids", conflicts),
            ("precondition_ids", preconditions),
        ):
            for reference in require_string_set(bundle.get(field), f"bundles.{bundle_id}.{field}"):
                if reference not in known:
                    raise ContractError("MISSING_REFERENCE", f"bundle {bundle_id} references missing {field}: {reference}")
        require_int(bundle.get("max_discoverable_capabilities"), f"bundles.{bundle_id}.max_discoverable_capabilities", 1, 12)
        fallback = require_object(bundle.get("fallback"), f"bundles.{bundle_id}.fallback")
        exact_keys(fallback, ("route_type", "route_id"), (), f"bundles.{bundle_id}.fallback")
        fallback_type = require_enum(
            fallback["route_type"],
            {"atomic", "bundle", "browser-manual", "no-safe-route"},
            f"bundles.{bundle_id}.fallback.route_type",
        )
        fallback_id = require_string(fallback["route_id"], f"bundles.{bundle_id}.fallback.route_id", STABLE_ID)
        if fallback_type == "atomic" and fallback_id not in capabilities:
            raise ContractError("MISSING_REFERENCE", f"bundle {bundle_id} fallback capability is missing: {fallback_id}")
        if fallback_type == "bundle" and fallback_id not in bundles:
            raise ContractError("MISSING_REFERENCE", f"bundle {bundle_id} fallback bundle is missing: {fallback_id}")
        if fallback_type == "browser-manual" and fallback_id != "browser-manual":
            raise ContractError("INVALID_FALLBACK", f"bundle {bundle_id} browser fallback ID is invalid")
        if fallback_type == "no-safe-route" and fallback_id != "NO_SAFE_ROUTE":
            raise ContractError("INVALID_FALLBACK", f"bundle {bundle_id} no-safe-route fallback ID is invalid")

    fixture: dict[str, Any] | None = None
    discoverable_ids = sorted({item["canonical_route_id"] for item in request["candidate_evidence"]})
    if request["task"]["fixture_scope"]:
        fixtures = collection(
            parsed["evals/choicegate/inventory-fixtures.json"],
            "fixtures",
            "evals/choicegate/inventory-fixtures.json",
        )
        fixture_map = unique_map(fixtures, "id", "inventory-fixtures")
        fixture_id = request["task"]["fixture_id"]
        if fixture_id not in fixture_map:
            raise ContractError("MISSING_REFERENCE", f"fixture does not exist: {fixture_id}")
        fixture = fixture_map[fixture_id]
        discoverable_ids = require_string_set(fixture.get("discoverable_ids"), f"fixture.{fixture_id}.discoverable_ids")
        for capability_id, overrides_raw in require_object(fixture.get("state_overrides", {}), f"fixture.{fixture_id}.state_overrides").items():
            if capability_id not in capabilities:
                raise ContractError("MISSING_REFERENCE", f"fixture override references missing capability: {capability_id}")
            overrides = require_object(overrides_raw, f"fixture.{fixture_id}.state_overrides.{capability_id}")
            if set(overrides) - set(STATE_AXES):
                raise ContractError("STRICT_SCHEMA_VIOLATION", f"fixture capability override widens its allowed fields: {capability_id}")
            aliases = capabilities[capability_id].get("compatibility_aliases")
            if isinstance(aliases, list) and len(aliases) == 1 and isinstance(aliases[0], dict):
                alias_lifecycle = aliases[0].get("lifecycle")
                if isinstance(alias_lifecycle, dict):
                    for axis in STATE_AXES:
                        if axis != "source_state" and axis in alias_lifecycle:
                            capabilities[capability_id][axis] = copy.deepcopy(alias_lifecycle[axis])
            capabilities[capability_id].update(copy.deepcopy(overrides))
            validate_state_record(capabilities[capability_id], axes, f"fixture.capabilities.{capability_id}")
        for bundle_id, overrides_raw in require_object(fixture.get("bundle_overrides", {}), f"fixture.{fixture_id}.bundle_overrides").items():
            if bundle_id not in bundles:
                raise ContractError("MISSING_REFERENCE", f"fixture override references missing bundle: {bundle_id}")
            overrides = require_object(overrides_raw, f"fixture.{fixture_id}.bundle_overrides.{bundle_id}")
            allowed = set(STATE_AXES) | {"fixture_only", "local_files_only", "remote_actions", "outward_messages"}
            if set(overrides) - allowed:
                raise ContractError("STRICT_SCHEMA_VIOLATION", f"fixture bundle override widens its allowed fields: {bundle_id}")
            for field in set(overrides) & (set(STATE_AXES) | {"fixture_only"}):
                bundles[bundle_id][field] = copy.deepcopy(overrides[field])
            validate_state_record(bundles[bundle_id], axes, f"fixture.bundles.{bundle_id}")
        for override_raw in require_list(fixture.get("supersession_overrides", []), f"fixture.{fixture_id}.supersession_overrides"):
            override = require_object(override_raw, f"fixture.{fixture_id}.supersession_overrides[]")
            matches = [
                edge for edge in supersessions.values()
                if edge.get("predecessor_id") == override.get("predecessor_id")
                and edge.get("successor_id") == override.get("successor_id")
            ]
            if len(matches) != 1:
                raise ContractError("MISSING_REFERENCE", "fixture supersession override did not match exactly one edge")
            matches[0]["state"] = require_enum(override.get("state"), {"proposed", "approved", "rejected", "rolled-back"}, "fixture supersession state")
            matches[0]["effective"] = require_bool(override.get("effective"), "fixture supersession effective")
        fixture_task = require_object(fixture.get("task_contract", {}), f"fixture.{fixture_id}.task_contract")
        for key, expected in fixture_task.items():
            actual = request["task"]["allowed_scope"].get(key, request["task"]["preconditions"].get(key))
            same_json_scalar = (
                actual is expected
                if isinstance(expected, bool)
                else (
                    not isinstance(actual, bool)
                    and isinstance(actual, type(expected))
                    and actual == expected
                )
            )
            if not same_json_scalar:
                raise ContractError("FIXTURE_TASK_MISMATCH", f"task does not preserve fixture contract: {key}")

    known_discoverable = set(capabilities) | set(bundles)
    synthetic: set[str] = set()
    synthetic_map: dict[str, str] = {}
    if fixture is not None:
        for item in require_list(fixture.get("synthetic_candidates", []), f"fixture.{fixture['id']}.synthetic_candidates"):
            synthetic_item = require_object(item, f"fixture.{fixture['id']}.synthetic_candidates[]")
            synthetic_id = require_string(synthetic_item.get("id"), "synthetic candidate id", STABLE_ID)
            canonical_id = require_string(
                synthetic_item.get("canonical_capability_id"),
                "synthetic candidate canonical_capability_id",
                STABLE_ID,
            )
            if canonical_id not in capabilities:
                raise ContractError("MISSING_REFERENCE", f"synthetic candidate canonical capability is missing: {canonical_id}")
            if synthetic_item.get("owner") != capabilities[canonical_id].get("owner"):
                raise ContractError("DUPLICATE_OWNER_MISMATCH", f"synthetic candidate owner differs from canonical capability: {synthetic_id}")
            synthetic.add(synthetic_id)
            synthetic_map[synthetic_id] = canonical_id
            # Synthetic wrappers exist only in accepted eval fixtures. Make the
            # canonical owner executable in that in-memory fixture so the case
            # tests deduplication rather than unrelated inactive baseline state.
            canonical = capabilities[canonical_id]
            canonical.update({
                "install_state": "installed",
                "enablement_state": "enabled",
                "exposure_state": "surface-exposed",
                "authorization_state": "not-required",
                "activity_state": "available",
                "promotion_state": "candidate-validated",
            })
            validate_state_record(canonical, axes, f"fixture.synthetic.{canonical_id}")
    for item in discoverable_ids:
        if item not in known_discoverable and item not in synthetic:
            raise ContractError("MISSING_REFERENCE", f"discoverable ID is not registered or fixture-declared: {item}")

    return {
        "axes": axes,
        "capabilities": capabilities,
        "bundles": bundles,
        "dependencies": dependencies,
        "conflicts": conflicts,
        "preconditions": preconditions,
        "supersessions": supersessions,
        "fixture": fixture,
        "discoverable_ids": discoverable_ids,
        "synthetic_ids": synthetic,
        "synthetic_map": synthetic_map,
        "fixture_bundle_ids": set() if fixture is None else set(require_object(fixture.get("bundle_overrides", {}), f"fixture.{fixture['id']}.bundle_overrides")),
    }


def validate_route_references(request: dict[str, Any], registry: dict[str, Any]) -> None:
    known = set(registry["capabilities"]) | set(registry["bundles"])
    synthetic_map = registry["synthetic_map"]
    allowed_fixture_routes = set(registry["discoverable_ids"]) | set(registry["fixture_bundle_ids"])
    for index, candidate in enumerate(request["candidate_evidence"]):
        route_id = candidate["route_id"]
        canonical_id = candidate["canonical_route_id"]
        if canonical_id not in known:
            raise ContractError("MISSING_REFERENCE", f"candidate_evidence[{index}] canonical route is not registered: {canonical_id}")
        if route_id != canonical_id and synthetic_map.get(route_id) != canonical_id:
            raise ContractError("UNDECLARED_ROUTE_ALIAS", f"candidate_evidence[{index}] route alias is not fixture-declared: {route_id}")
        if request["task"]["fixture_scope"] and canonical_id not in allowed_fixture_routes:
            raise ContractError("UNDISCOVERABLE_ROUTE", f"candidate_evidence[{index}] is outside the accepted fixture inventory: {canonical_id}")
    valid_requested = known | set(synthetic_map)
    for route_id in request["task"]["requested_route_ids"]:
        if route_id not in valid_requested:
            raise ContractError("MISSING_REFERENCE", f"task.requested_route_ids contains an unregistered route: {route_id}")
        canonical_id = synthetic_map.get(route_id, route_id)
        if request["task"]["fixture_scope"] and canonical_id not in allowed_fixture_routes:
            raise ContractError("UNDISCOVERABLE_ROUTE", f"task requested route is outside the accepted fixture inventory: {route_id}")


def state_binding(record: dict[str, Any]) -> dict[str, str]:
    return {axis: str(record[axis]) for axis in STATE_AXES}


def state_is_ready(record: dict[str, Any]) -> bool:
    return (
        record.get("install_state") in {"installed", "not-applicable"}
        and record.get("enablement_state") in {"enabled", "not-applicable"}
        and record.get("exposure_state") in {"project-exposed", "surface-exposed", "session-exposed", "not-applicable"}
        and record.get("authorization_state") in {"authorized", "not-required"}
        and record.get("activity_state") in {"available", "active", "invoked-this-task"}
    )


def surface_is_supported(record: dict[str, Any], surface: str, fixture_scope: bool) -> bool:
    if surface in {"browser", "manual"}:
        return False
    if fixture_scope and surface == "local":
        return True
    surface_policies = record.get("surface_policies")
    if isinstance(surface_policies, list):
        matches = [
            item for item in surface_policies
            if isinstance(item, dict) and item.get("surface") == surface
        ]
        if len(matches) != 1:
            return False
        if (
            matches[0].get("route_policy") == "no-safe-route"
            or matches[0].get("qualification_state") != "qualified-current"
        ):
            return False
    adapters = record.get("surface_adapters", [])
    if isinstance(adapters, list) and any(
        isinstance(adapter, dict) and adapter.get("surface") == surface
        for adapter in adapters
    ):
        return True
    owner = str(record.get("owner", "")).lower()
    canonical_path = str(record.get("canonical_path", "")).lower().replace("/", "\\")
    if surface == "codex":
        return owner.startswith("codex-") or "\\.codex\\" in canonical_path
    if surface == "claude-code":
        return owner.startswith("claude-code-")
    if surface == "local":
        return record.get("source_state") in {
            "canonical-local",
            "local-project",
            "native",
        }
    return False


def missing_setup_actions(record: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    if record.get("install_state") not in {"installed", "not-applicable"}:
        actions.add("install")
    if record.get("enablement_state") not in {"enabled", "not-applicable"}:
        actions.add("enable")
    if record.get("exposure_state") not in {"project-exposed", "surface-exposed", "session-exposed", "not-applicable"}:
        actions.add("expose")
    if record.get("authorization_state") not in {"authorized", "not-required"}:
        actions.add("authorize")
    return actions


def effective_supersession(registry: dict[str, Any], kind: str, identifier: str) -> dict[str, Any] | None:
    for edge in registry["supersessions"].values():
        if (
            edge.get("predecessor_type") == kind
            and edge.get("predecessor_id") == identifier
            and edge.get("state") == "approved"
            and edge.get("effective") is True
        ):
            return edge
    return None


def precondition_value(task: dict[str, Any], key: str) -> Any:
    if key in task["preconditions"]:
        return task["preconditions"][key]
    if key in task["allowed_scope"]:
        return task["allowed_scope"][key]
    return None


def preconditions_satisfied(registry: dict[str, Any], kind: str, identifier: str, task: dict[str, Any]) -> bool:
    for edge in registry["preconditions"].values():
        if edge.get("applies_to_type") != kind or edge.get("applies_to_id") != identifier:
            continue
        if edge.get("kind") == "state-axis":
            continue
        for key, expected in require_object(edge.get("required"), f"precondition.{edge['id']}.required").items():
            actual = precondition_value(task, key)
            if key == "max_attempts" and expected is True:
                if isinstance(actual, bool) or not isinstance(actual, int) or not 1 <= actual <= 3:
                    return False
            elif isinstance(expected, bool):
                if actual is not expected:
                    return False
            elif isinstance(actual, bool) or not isinstance(actual, type(expected)) or actual != expected:
                return False
    return True


def hard_dependency_ready(
    registry: dict[str, Any],
    kind: str,
    identifier: str,
    accepted_promotions: set[str],
) -> bool:
    for edge in registry["dependencies"].values():
        if edge.get("from_type") != kind or edge.get("from_id") != identifier or edge.get("requirement") != "hard":
            continue
        target_kind = edge["to_type"]
        target = registry["capabilities"].get(edge["to_id"]) if target_kind == "capability" else registry["bundles"].get(edge["to_id"])
        if (
            target is None
            or not state_is_ready(target)
            or target.get("promotion_state") not in accepted_promotions
            or target.get("source_state") == "quarantined-external"
            or effective_supersession(registry, target_kind, str(edge["to_id"])) is not None
        ):
            return False
    return True


def provider_conflict_ids(registry: dict[str, Any], route_ids: set[str]) -> set[str]:
    rejected: set[str] = set()
    for edge in registry["conflicts"].values():
        left = str(edge.get("left_id"))
        right = str(edge.get("right_id"))
        if left in route_ids and right in route_ids:
            rejected.update({left, right})
    families: dict[str, list[str]] = {}
    for route_id in route_ids:
        record = registry["capabilities"].get(route_id)
        family = None if record is None else record.get("provider_family")
        if family:
            families.setdefault(str(family), []).append(route_id)
    for members in families.values():
        if len(members) > 1:
            rejected.update(members)
    return rejected


def add_code(candidate: dict[str, Any], code: str) -> None:
    if code not in EXCLUSION_ORDER:
        raise RuntimeError(f"unknown exclusion code: {code}")
    if code not in candidate["hard_exclusion_codes"]:
        candidate["hard_exclusion_codes"].append(code)
        candidate["hard_exclusion_codes"].sort(key=EXCLUSION_ORDER.index)


def setup_path_for(policy: dict[str, Any], route_id: str) -> dict[str, Any] | None:
    for item in policy["explicit_owner_approved_setup_paths"]:
        if item["route_id"] == route_id:
            return item
    return None


def make_score(candidate_input: dict[str, Any], risk_class: str, member_count: int) -> dict[str, Any]:
    scope_penalty = sum(1 for value in candidate_input["required_scope"].values() if value)
    task_exact = 1 if candidate_input["task_class_match"] else 0
    covered = len(candidate_input["covers_required_outcomes"])
    risk = RISK_PENALTY[risk_class]
    selection_tuple = [
        task_exact,
        covered,
        candidate_input["task_fit"],
        -scope_penalty,
        -risk,
        -candidate_input["context_cost"],
        -candidate_input["expected_cost"],
        -member_count,
    ]
    return {
        "task_class_exact": task_exact,
        "required_outcomes_covered": covered,
        "task_fit": candidate_input["task_fit"],
        "scope_penalty": scope_penalty,
        "risk_penalty": risk,
        "context_cost": candidate_input["context_cost"],
        "expected_cost": candidate_input["expected_cost"],
        "member_count": member_count,
        "selection_tuple": selection_tuple,
        "lexical_tiebreak": candidate_input["canonical_route_id"],
    }


def evaluate_candidates(request: dict[str, Any], registry: dict[str, Any]) -> list[dict[str, Any]]:
    task = request["task"]
    policy = request["policy"]
    accepted_promotions = FIXTURE_PROMOTIONS if task["fixture_scope"] else READY_PROMOTIONS
    results: list[dict[str, Any]] = []
    duplicate_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in sorted(request["candidate_evidence"], key=lambda entry: entry["route_id"]):
        canonical_id = item["canonical_route_id"]
        record = registry["capabilities"].get(canonical_id) if item["route_type"] == "atomic" else registry["bundles"].get(canonical_id)
        if record is None:
            raise ContractError("MISSING_REFERENCE", f"candidate canonical route is not registered: {canonical_id}")
        if item["route_type"] == "bundle" and item["version"] != record.get("version"):
            raise ContractError("VERSION_MISMATCH", f"candidate bundle version mismatch: {canonical_id}")
        if item["route_type"] == "atomic" and item["version"] is not None:
            raise ContractError("VERSION_MISMATCH", f"atomic candidate version must be null: {canonical_id}")
        candidate = {
            "route_type": item["route_type"],
            "route_id": item["route_id"],
            "canonical_route_id": canonical_id,
            "candidate_evidence_sha256": canonical_sha256(item),
            "version": item["version"],
            "owner": str(record.get("owner", "registry")),
            "pool": "executable",
            "hard_exclusion_codes": [],
            "evidence_refs": sorted(item["evidence_refs"]),
            "score_breakdown": None,
            "duplicate_of": None,
            "final_disposition": "eligible",
            "_canonical_route_id": canonical_id,
            "_input": item,
            "_record": record,
            "_bundle_members": [],
            "_approvals": [],
        }
        duplicate_groups.setdefault((item["route_type"], canonical_id), []).append(candidate)
        results.append(candidate)

    for group in duplicate_groups.values():
        if len(group) < 2 and group[0]["route_id"] == group[0]["_canonical_route_id"]:
            continue
        kept = sorted(group, key=lambda item: (item["route_id"] != item["_canonical_route_id"], item["route_id"]))[0]
        for candidate in group:
            if candidate is kept:
                continue
            candidate["duplicate_of"] = kept["route_id"]
            add_code(candidate, "DUPLICATE_CANONICAL_OWNER")

    discoverable_count = len(registry["discoverable_ids"])
    ceiling = min(task["max_discoverable_capabilities"], policy["normal_ceiling"])
    over_budget = discoverable_count > ceiling
    composite_conflicts = provider_conflict_ids(registry, set(task["requested_route_ids"]))

    for candidate in results:
        item = candidate["_input"]
        record = candidate["_record"]
        canonical_id = candidate["_canonical_route_id"]
        kind = "capability" if item["route_type"] == "atomic" else "bundle"
        if item["risk_flags"] or record.get("source_state") == "quarantined-external":
            add_code(candidate, "UNSAFE_OR_UNVERIFIED")
        if not item["evidence_fresh"] or record.get("activity_state") == "stale":
            add_code(candidate, "STALE_EVIDENCE")
        if effective_supersession(registry, kind, canonical_id) is not None:
            add_code(candidate, "NOT_PROMOTED_FOR_ROUTE")
            add_code(candidate, "STALE_EVIDENCE")
        if record.get("promotion_state") not in accepted_promotions:
            add_code(candidate, "NOT_PROMOTED_FOR_ROUTE")
        if over_budget:
            add_code(candidate, "CONTEXT_BUDGET_EXCEEDED")
        if canonical_id in composite_conflicts:
            add_code(candidate, "PROVIDER_FAMILY_CONFLICT")
        if not surface_is_supported(record, task["surface"], task["fixture_scope"]):
            add_code(candidate, "SURFACE_MISMATCH")
        if not item["task_class_match"] or not set(task["required_outcomes"]).issubset(item["covers_required_outcomes"]):
            add_code(candidate, "SCOPE_OR_RISK_MISMATCH")
        for field, required in item["required_scope"].items():
            if required and not task["allowed_scope"][field]:
                add_code(candidate, "SCOPE_OR_RISK_MISMATCH")
        if DATA_CLASS_LEVEL[item["required_private_data_class"]] > DATA_CLASS_LEVEL[task["private_data_class"]]:
            add_code(candidate, "SCOPE_OR_RISK_MISMATCH")
        if not preconditions_satisfied(registry, kind, canonical_id, task):
            add_code(candidate, "PRECONDITION_UNSATISFIED")
        if not hard_dependency_ready(registry, kind, canonical_id, accepted_promotions):
            add_code(candidate, "DEPENDENCY_UNSATISFIED")

        member_count = 1
        route_risk = str(record.get("risk", "medium"))
        if item["route_type"] == "bundle":
            members = sorted(record["members"], key=lambda member: member["order"])
            member_count = 0
            known_roles = {str(member["role"]) for member in members}
            required_roles = {
                str(member["role"])
                for member in members
                if member["requirement"] == "required"
            }
            declared_roles = set(item["necessary_member_roles"])
            if declared_roles - known_roles:
                add_code(candidate, "BUNDLE_NOT_APPROVED")
            if len(required_roles) < 2 or not required_roles.issubset(declared_roles):
                add_code(candidate, "BUNDLE_UNNECESSARY")
            if record.get("fixture_only") is True and not task["fixture_scope"]:
                add_code(candidate, "BUNDLE_NOT_APPROVED")
            if task["task_class"] not in record.get("eligible_task_classes", []):
                add_code(candidate, "BUNDLE_NOT_APPROVED")
            if discoverable_count > min(ceiling, int(record["max_discoverable_capabilities"])):
                add_code(candidate, "CONTEXT_BUDGET_EXCEEDED")
            member_ids = {
                str(member["capability_id"])
                for member in members
                if member["role"] in declared_roles
            }
            if provider_conflict_ids(registry, member_ids):
                add_code(candidate, "PROVIDER_FAMILY_CONFLICT")
            for member in members:
                member_record = registry["capabilities"][member["capability_id"]]
                selected = member["role"] in declared_roles
                if selected:
                    member_count += 1
                if selected and RISK_LEVEL[str(member_record["risk"])] > RISK_LEVEL[route_risk]:
                    route_risk = str(member_record["risk"])
                if selected:
                    member_ready = (
                        state_is_ready(member_record)
                        and member_record.get("promotion_state") in accepted_promotions
                        and member_record.get("source_state") != "quarantined-external"
                        and effective_supersession(registry, "capability", str(member["capability_id"])) is None
                        and surface_is_supported(member_record, task["surface"], task["fixture_scope"])
                    )
                    if not member_ready:
                        add_code(candidate, "BUNDLE_MEMBER_UNAVAILABLE")
                    if not preconditions_satisfied(registry, "capability", str(member["capability_id"]), task):
                        add_code(candidate, "PRECONDITION_UNSATISFIED")
                    if not hard_dependency_ready(
                        registry,
                        "capability",
                        str(member["capability_id"]),
                        accepted_promotions,
                    ):
                        add_code(candidate, "DEPENDENCY_UNSATISFIED")
                candidate["_bundle_members"].append({
                    "order": member["order"],
                    "capability_id": member["capability_id"],
                    "requirement": member["requirement"],
                    "role": member["role"],
                    "selection": "selected" if selected and state_is_ready(member_record) else "omitted",
                    "state_binding": state_binding(member_record),
                })
        elif item["necessary_member_roles"]:
            add_code(candidate, "SCOPE_OR_RISK_MISMATCH")

        if RISK_LEVEL[route_risk] > RISK_LEVEL[task["risk_class"]]:
            add_code(candidate, "SCOPE_OR_RISK_MISMATCH")

        missing_actions = missing_setup_actions(record)
        setup_path = setup_path_for(policy, canonical_id)
        if missing_actions:
            allowed_actions = set() if setup_path is None else set(setup_path["allowed_actions"])
            setup_allowed = (
                task["allow_setup_choice"]
                and setup_path is not None
                and all(
                    action in allowed_actions
                    or (action == "authorize" and "configure" in allowed_actions)
                    for action in missing_actions
                )
            )
            if setup_allowed:
                add_code(candidate, "SETUP_APPROVAL_REQUIRED")
                candidate["_approvals"] = sorted(setup_path["approval_ids"])
            else:
                if "authorize" in missing_actions:
                    add_code(candidate, "AUTHORIZATION_MISMATCH")
                if "expose" in missing_actions:
                    add_code(candidate, "SURFACE_MISMATCH")
                if missing_actions - {"authorize", "expose"}:
                    add_code(candidate, "UNAVAILABLE_NO_APPROVED_SETUP")
        elif record.get("activity_state") not in {"available", "active", "invoked-this-task"}:
            add_code(candidate, "UNAVAILABLE_NO_APPROVED_SETUP")
        candidate["_score"] = make_score(item, route_risk, member_count)

    executable_atomics = [
        item for item in results
        if item["route_type"] == "atomic"
        and not item["hard_exclusion_codes"]
        and set(request["task"]["required_outcomes"]).issubset(item["_input"]["covers_required_outcomes"])
    ]
    if executable_atomics:
        for candidate in results:
            if candidate["route_type"] == "bundle" and not candidate["hard_exclusion_codes"]:
                add_code(candidate, "BUNDLE_UNNECESSARY")

    for candidate in results:
        codes = candidate["hard_exclusion_codes"]
        non_setup_codes = [code for code in codes if code != "SETUP_APPROVAL_REQUIRED"]
        if not codes:
            candidate["pool"] = "executable"
            candidate["final_disposition"] = "eligible"
            candidate["score_breakdown"] = candidate["_score"]
        elif codes == ["SETUP_APPROVAL_REQUIRED"]:
            candidate["pool"] = "setup-required"
            candidate["final_disposition"] = "requires-owner-setup-approval"
            candidate["score_breakdown"] = candidate["_score"]
        else:
            candidate["pool"] = "rejected"
            candidate["final_disposition"] = "rejected-hard-exclusion"
            candidate["score_breakdown"] = None
            if not non_setup_codes:
                raise RuntimeError("invalid setup classification")
    return results


def selection_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    score = candidate["score_breakdown"]
    return (
        -score["task_class_exact"],
        -score["required_outcomes_covered"],
        -score["task_fit"],
        score["scope_penalty"],
        score["risk_penalty"],
        score["context_cost"],
        score["expected_cost"],
        score["member_count"],
        candidate["_canonical_route_id"],
        candidate["route_id"],
    )


def normalized_task(task: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(task)
    result["fixture_id"] = result.get("fixture_id")
    result["owner_selected_route_id"] = result.get("owner_selected_route_id")
    return result


def inventory_binding(request: dict[str, Any]) -> dict[str, Any]:
    inventory = request["inventory"]
    return {
        "accepted_registry_commit": inventory["accepted_registry_commit"],
        "state_model_id": inventory["state_model_id"],
        "manifest_algorithm": inventory["manifest_algorithm"],
        "manifest_fingerprint": inventory["manifest_fingerprint"],
        "component_hashes": [
            {"path": path, "sha256": inventory["component_hashes"][path]}
            for path in sorted(inventory["component_hashes"])
        ],
    }


def strict_utf8_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(
            "ROUTER_BINDING_ENCODING",
            f"router binding file is not strict UTF-8: {path.name}",
        ) from exc


def canonical_text_sha256(path: Path) -> str:
    text = strict_utf8_text(path)
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return sha256_bytes(canonical)


def router_binding(choicegate_commit: str, policy: dict[str, Any]) -> dict[str, Any]:
    if GIT_COMMIT_RE.fullmatch(choicegate_commit) is None:
        raise ContractError("INVALID_ROUTER_BINDING", "--choicegate-commit must be a 40-character lowercase Git commit")
    skill_root = Path(__file__).resolve().parent.parent
    request_schema = skill_root / "schemas" / "route-request.schema.json"
    receipt_schema = skill_root / "schemas" / "decision-receipt.schema.json"
    helper = skill_root / "scripts" / "rank_candidates.py"
    for path in (request_schema, receipt_schema, helper):
        if not path.is_file():
            raise ContractError("ROUTER_BINDING_MISSING", f"router binding file is missing: {path.name}")
        strict_json_loads(strict_utf8_text(path), path.name) if path.suffix == ".json" else None
    return {
        "choicegate_commit": choicegate_commit,
        "router_version": ROUTER_VERSION,
        "router_policy_version": policy["policy_version"],
        "router_policy_sha256": policy["policy_sha256"],
        "request_schema_sha256": canonical_text_sha256(request_schema),
        "receipt_schema_sha256": canonical_text_sha256(receipt_schema),
        "router_source_sha256": canonical_text_sha256(Path(__file__).resolve()),
        "deterministic_helper_sha256": canonical_text_sha256(helper),
        "router_text_hash_algorithm": ROUTER_TEXT_HASH_ALGORITHM,
    }


def public_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "route_type",
        "route_id",
        "canonical_route_id",
        "candidate_evidence_sha256",
        "version",
        "owner",
        "pool",
        "hard_exclusion_codes",
        "evidence_refs",
        "score_breakdown",
        "duplicate_of",
        "final_disposition",
    )
    return [{field: copy.deepcopy(candidate[field]) for field in fields} for candidate in sorted(candidates, key=lambda item: item["route_id"])]


def make_receipt(
    request: dict[str, Any],
    binding: dict[str, Any],
    candidates: list[dict[str, Any]],
    decision: dict[str, Any],
    bundle_members: list[dict[str, Any]],
    approvals: list[str],
    fallback: dict[str, Any],
    discovery: dict[str, str],
) -> dict[str, Any]:
    request_for_hash = copy.deepcopy(request)
    request_for_hash["inventory"].pop("parsed_components", None)
    request_for_hash["inventory"].pop("component_hashes", None)
    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "request_id": request["request_id"],
        "request_sha256": canonical_sha256(request_for_hash),
        "inventory_binding": inventory_binding(request),
        "router_binding": binding,
        "task": normalized_task(request["task"]),
        "decision": decision,
        "bundle_members": copy.deepcopy(bundle_members),
        "candidates": public_candidates(candidates),
        "approvals_required": sorted(set(approvals)),
        "fallback": fallback,
        "discovery": discovery,
        "reselection_triggers": list(RESELECTION_TRIGGERS),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def require_nullable_stable_id(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return require_string(value, label, STABLE_ID)


def require_nullable_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError("INVALID_TYPE", f"{label} must be a string or null")
    return value


def require_finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("INVALID_TYPE", f"{label} must be numeric")
    result = float(value)
    if result != result or result in {float("inf"), float("-inf")}:
        raise ContractError("INVALID_VALUE", f"{label} must be finite")
    return result


def validate_prior_normalized_task(raw: Any) -> dict[str, Any]:
    task = require_object(raw, "prior_receipt.task")
    fields = (
        "task_class",
        "required_outcomes",
        "allowed_scope",
        "surface",
        "private_data_class",
        "authorization_required",
        "explicit_browser_choice",
        "intrinsic_visual_testing",
        "risk_class",
        "max_discoverable_capabilities",
        "allow_setup_choice",
        "fixture_scope",
        "fixture_id",
        "requested_route_ids",
        "preconditions",
        "owner_selected_route_id",
        "selected_path_failed",
    )
    exact_keys(task, fields, (), "prior_receipt.task")
    require_string(task["task_class"], "prior_receipt.task.task_class", STABLE_ID)
    require_string_set(task["required_outcomes"], "prior_receipt.task.required_outcomes")
    validate_allowed_scope(task["allowed_scope"], "prior_receipt.task.allowed_scope")
    require_enum(task["surface"], {"codex", "claude-code", "local", "browser", "manual"}, "prior_receipt.task.surface")
    require_enum(task["private_data_class"], set(DATA_CLASS_LEVEL), "prior_receipt.task.private_data_class")
    require_bool(task["authorization_required"], "prior_receipt.task.authorization_required")
    require_bool(task["explicit_browser_choice"], "prior_receipt.task.explicit_browser_choice")
    require_bool(task["intrinsic_visual_testing"], "prior_receipt.task.intrinsic_visual_testing")
    require_enum(task["risk_class"], set(RISK_LEVEL), "prior_receipt.task.risk_class")
    require_int(task["max_discoverable_capabilities"], "prior_receipt.task.max_discoverable_capabilities", 1, 12)
    require_bool(task["allow_setup_choice"], "prior_receipt.task.allow_setup_choice")
    require_bool(task["fixture_scope"], "prior_receipt.task.fixture_scope")
    require_nullable_stable_id(task["fixture_id"], "prior_receipt.task.fixture_id")
    require_string_set(task["requested_route_ids"], "prior_receipt.task.requested_route_ids")
    preconditions = require_object(task["preconditions"], "prior_receipt.task.preconditions")
    for key, item in preconditions.items():
        require_string(key, "prior_receipt.task.preconditions key", STABLE_ID)
        if item is None or isinstance(item, (dict, list)) or not isinstance(item, (str, int, float, bool)):
            raise ContractError("INVALID_TYPE", f"prior_receipt.task.preconditions.{key} must be scalar")
        if isinstance(item, float):
            require_finite_number(item, f"prior_receipt.task.preconditions.{key}")
    require_nullable_stable_id(task["owner_selected_route_id"], "prior_receipt.task.owner_selected_route_id")
    require_bool(task["selected_path_failed"], "prior_receipt.task.selected_path_failed")
    return task


def validate_prior_score_breakdown(raw: Any, label: str) -> None:
    score = require_object(raw, label)
    fields = (
        "task_class_exact",
        "required_outcomes_covered",
        "task_fit",
        "scope_penalty",
        "risk_penalty",
        "context_cost",
        "expected_cost",
        "member_count",
        "selection_tuple",
        "lexical_tiebreak",
    )
    exact_keys(score, fields, (), label)
    require_int(score["task_class_exact"], f"{label}.task_class_exact", 0, 1)
    require_int(score["required_outcomes_covered"], f"{label}.required_outcomes_covered", 0)
    require_number(score["task_fit"], f"{label}.task_fit", 0, 5)
    require_int(score["scope_penalty"], f"{label}.scope_penalty", 0)
    require_int(score["risk_penalty"], f"{label}.risk_penalty", 0, 4)
    require_number(score["context_cost"], f"{label}.context_cost", 0, 5)
    require_number(score["expected_cost"], f"{label}.expected_cost", 0, 5)
    require_int(score["member_count"], f"{label}.member_count", 1)
    selection = require_list(score["selection_tuple"], f"{label}.selection_tuple")
    if len(selection) != 8:
        raise ContractError("INVALID_VALUE", f"{label}.selection_tuple must contain exactly 8 numbers")
    for index, item in enumerate(selection):
        require_finite_number(item, f"{label}.selection_tuple[{index}]")
    require_string(score["lexical_tiebreak"], f"{label}.lexical_tiebreak", STABLE_ID)


def validate_prior_receipt_envelope(prior: dict[str, Any]) -> None:
    receipt_fields = (
        "receipt_version",
        "request_id",
        "request_sha256",
        "inventory_binding",
        "router_binding",
        "task",
        "decision",
        "bundle_members",
        "candidates",
        "approvals_required",
        "fallback",
        "discovery",
        "reselection_triggers",
        "prohibited_actions",
        "receipt_sha256",
    )
    exact_keys(prior, receipt_fields, (), "prior_receipt")
    if prior.get("receipt_version") != RECEIPT_VERSION:
        raise ContractError("HANDOFF_INVALID", "prior receipt version is not supported")
    require_string(prior.get("request_id"), "prior_receipt.request_id", STABLE_ID)
    require_string(prior.get("request_sha256"), "prior_receipt.request_sha256", SHA256_RE)
    inventory = require_object(prior.get("inventory_binding"), "prior_receipt.inventory_binding")
    exact_keys(
        inventory,
        ("accepted_registry_commit", "state_model_id", "manifest_algorithm", "manifest_fingerprint", "component_hashes"),
        (),
        "prior_receipt.inventory_binding",
    )
    require_string(inventory["accepted_registry_commit"], "prior_receipt.inventory_binding.accepted_registry_commit", GIT_COMMIT_RE)
    require_string(inventory["manifest_fingerprint"], "prior_receipt.inventory_binding.manifest_fingerprint", SHA256_RE)
    if inventory["state_model_id"] != STATE_MODEL_ID or inventory["manifest_algorithm"] != MANIFEST_ALGORITHM:
        raise ContractError("HANDOFF_INVALID", "prior receipt inventory model or algorithm changed")
    component_hashes = require_list(inventory["component_hashes"], "prior_receipt.inventory_binding.component_hashes")
    if len(component_hashes) != len(COMPONENT_PATHS):
        raise ContractError("HANDOFF_INVALID", "prior receipt inventory component count changed")
    component_paths: list[str] = []
    for index, raw_component in enumerate(component_hashes):
        component = require_object(raw_component, f"prior_receipt.inventory_binding.component_hashes[{index}]")
        exact_keys(component, ("path", "sha256"), (), f"prior_receipt.inventory_binding.component_hashes[{index}]")
        component_paths.append(require_string(component["path"], f"prior_receipt.inventory_binding.component_hashes[{index}].path"))
        require_string(component["sha256"], f"prior_receipt.inventory_binding.component_hashes[{index}].sha256", SHA256_RE)
    if tuple(sorted(component_paths)) != COMPONENT_PATHS:
        raise ContractError("HANDOFF_INVALID", "prior receipt inventory component paths changed")

    router = require_object(prior.get("router_binding"), "prior_receipt.router_binding")
    router_fields = (
        "choicegate_commit",
        "router_version",
        "router_policy_version",
        "router_policy_sha256",
        "request_schema_sha256",
        "receipt_schema_sha256",
        "router_source_sha256",
        "deterministic_helper_sha256",
        "router_text_hash_algorithm",
    )
    exact_keys(router, router_fields, (), "prior_receipt.router_binding")
    require_string(router["choicegate_commit"], "prior_receipt.router_binding.choicegate_commit", GIT_COMMIT_RE)
    if router["router_version"] != ROUTER_VERSION or router["router_policy_version"] != POLICY_VERSION:
        raise ContractError("HANDOFF_INVALID", "prior receipt router version changed")
    if router["router_text_hash_algorithm"] != ROUTER_TEXT_HASH_ALGORITHM:
        raise ContractError("HANDOFF_INVALID", "prior receipt router text hash algorithm changed")
    for field in (
        "router_policy_sha256",
        "request_schema_sha256",
        "receipt_schema_sha256",
        "router_source_sha256",
        "deterministic_helper_sha256",
    ):
        require_string(router[field], f"prior_receipt.router_binding.{field}", SHA256_RE)

    validate_prior_normalized_task(prior.get("task"))
    decision = require_object(prior.get("decision"), "prior_receipt.decision")
    exact_keys(decision, ("route_type", "route_id", "version", "owner", "executable", "reason"), (), "prior_receipt.decision")
    require_enum(
        decision["route_type"],
        {"atomic", "bundle", "requires-setup-approval", "browser-manual", "no-safe-route", "handoff"},
        "prior_receipt.decision.route_type",
    )
    require_string(decision["route_id"], "prior_receipt.decision.route_id", STABLE_ID)
    require_nullable_string(decision["version"], "prior_receipt.decision.version")
    require_nullable_stable_id(decision["owner"], "prior_receipt.decision.owner")
    require_bool(decision["executable"], "prior_receipt.decision.executable")
    require_string(decision["reason"], "prior_receipt.decision.reason", STABLE_ID)
    bundle_members = require_list(prior.get("bundle_members"), "prior_receipt.bundle_members")
    for index, raw_member in enumerate(bundle_members):
        label = f"prior_receipt.bundle_members[{index}]"
        member = require_object(raw_member, label)
        exact_keys(member, ("order", "capability_id", "requirement", "role", "selection", "state_binding"), (), label)
        require_int(member["order"], f"{label}.order", 1)
        require_string(member["capability_id"], f"{label}.capability_id", STABLE_ID)
        require_enum(member["requirement"], {"required", "optional"}, f"{label}.requirement")
        require_string(member["role"], f"{label}.role", STABLE_ID)
        require_enum(member["selection"], {"selected", "omitted"}, f"{label}.selection")
        state_binding_value = require_object(member["state_binding"], f"{label}.state_binding")
        exact_keys(state_binding_value, STATE_AXES, (), f"{label}.state_binding")
        for axis in STATE_AXES:
            if not isinstance(state_binding_value[axis], str):
                raise ContractError("INVALID_TYPE", f"{label}.state_binding.{axis} must be a string")
    prior_candidates = require_list(prior.get("candidates"), "prior_receipt.candidates")
    candidate_fields = (
        "route_type",
        "route_id",
        "canonical_route_id",
        "candidate_evidence_sha256",
        "version",
        "owner",
        "pool",
        "hard_exclusion_codes",
        "evidence_refs",
        "score_breakdown",
        "duplicate_of",
        "final_disposition",
    )
    for index, raw_candidate in enumerate(prior_candidates):
        label = f"prior_receipt.candidates[{index}]"
        candidate = require_object(raw_candidate, label)
        exact_keys(candidate, candidate_fields, (), label)
        require_enum(candidate["route_type"], {"atomic", "bundle"}, f"{label}.route_type")
        require_string(candidate["route_id"], f"{label}.route_id", STABLE_ID)
        require_string(candidate["canonical_route_id"], f"{label}.canonical_route_id", STABLE_ID)
        require_string(candidate["candidate_evidence_sha256"], f"{label}.candidate_evidence_sha256", SHA256_RE)
        require_nullable_string(candidate["version"], f"{label}.version")
        require_nullable_stable_id(candidate["owner"], f"{label}.owner")
        require_enum(candidate["pool"], {"executable", "setup-required", "rejected"}, f"{label}.pool")
        require_string_set(candidate["hard_exclusion_codes"], f"{label}.hard_exclusion_codes")
        evidence_refs = require_list(candidate["evidence_refs"], f"{label}.evidence_refs")
        if any(not isinstance(item, str) for item in evidence_refs):
            raise ContractError("INVALID_TYPE", f"{label}.evidence_refs must contain only strings")
        if len(set(evidence_refs)) != len(evidence_refs):
            raise ContractError("DUPLICATE_ID", f"{label}.evidence_refs contains duplicates")
        if candidate["score_breakdown"] is not None:
            validate_prior_score_breakdown(candidate["score_breakdown"], f"{label}.score_breakdown")
        require_nullable_stable_id(candidate["duplicate_of"], f"{label}.duplicate_of")
        require_string(candidate["final_disposition"], f"{label}.final_disposition", STABLE_ID)
    require_string_set(prior.get("approvals_required"), "prior_receipt.approvals_required")
    fallback = require_object(prior.get("fallback"), "prior_receipt.fallback")
    exact_keys(fallback, ("route_type", "route_id", "eligible", "reason"), (), "prior_receipt.fallback")
    require_enum(fallback["route_type"], {"atomic", "bundle", "browser-manual", "no-safe-route"}, "prior_receipt.fallback.route_type")
    require_string(fallback["route_id"], "prior_receipt.fallback.route_id", STABLE_ID)
    require_bool(fallback["eligible"], "prior_receipt.fallback.eligible")
    require_string(fallback["reason"], "prior_receipt.fallback.reason", STABLE_ID)
    discovery = require_object(prior.get("discovery"), "prior_receipt.discovery")
    exact_keys(discovery, ("status", "reason"), (), "prior_receipt.discovery")
    require_enum(
        discovery["status"],
        {
            "required",
            "skipped-explicit-browser",
            "skipped-intrinsic-visual",
            "suppressed-valid-handoff",
            "blocked-selected-path-failure",
        },
        "prior_receipt.discovery.status",
    )
    require_string(discovery["reason"], "prior_receipt.discovery.reason", STABLE_ID)
    if prior.get("reselection_triggers") != list(RESELECTION_TRIGGERS):
        raise ContractError("HANDOFF_INVALID", "prior receipt reselection triggers changed")
    if prior.get("prohibited_actions") != list(PROHIBITED_ACTIONS):
        raise ContractError("HANDOFF_INVALID", "prior receipt prohibited actions changed")
    provided = prior.get("receipt_sha256")
    require_string(provided, "prior_receipt.receipt_sha256", SHA256_RE)
    hash_input = {key: value for key, value in prior.items() if key != "receipt_sha256"}
    if canonical_sha256(hash_input) != provided:
        raise ContractError("HANDOFF_HASH_MISMATCH", "prior receipt hash is invalid")


def validate_prior_receipt(
    prior: dict[str, Any],
    request: dict[str, Any],
    binding: dict[str, Any],
    candidates: list[dict[str, Any]],
    resolved_fallback: dict[str, Any],
) -> dict[str, Any]:
    validate_prior_receipt_envelope(prior)
    if prior["request_id"] != request["request_id"]:
        raise ContractError("HANDOFF_REQUEST_ID_MISMATCH", "prior receipt request ID differs from the current request")
    if prior.get("inventory_binding") != inventory_binding(request):
        raise ContractError("HANDOFF_INVENTORY_DRIFT", "prior receipt inventory binding changed")
    if prior.get("router_binding") != binding:
        raise ContractError("HANDOFF_ROUTER_DRIFT", "prior receipt router binding changed")
    prior_task = require_object(prior.get("task"), "prior_receipt.task")
    current_task = normalized_task(request["task"])
    for field in ("owner_selected_route_id", "selected_path_failed"):
        prior_task = {key: value for key, value in prior_task.items() if key != field}
        current_task = {key: value for key, value in current_task.items() if key != field}
    if prior_task != current_task:
        raise ContractError("HANDOFF_SCOPE_DRIFT", "prior receipt task scope changed")
    decision = require_object(prior.get("decision"), "prior_receipt.decision")
    exact_keys(decision, ("route_type", "route_id", "version", "owner", "executable", "reason"), (), "prior_receipt.decision")
    route_id = require_string(decision.get("route_id"), "prior_receipt.decision.route_id", STABLE_ID)
    selected = request["task"].get("owner_selected_route_id")
    if selected != route_id:
        raise ContractError("HANDOFF_ROUTE_MISMATCH", "owner-selected route differs from prior receipt")
    if decision.get("route_type") not in {"atomic", "bundle"} or decision.get("executable") is not True:
        raise ContractError(
            "HANDOFF_ROUTE_INVALID",
            "prior authority must be the original executable atomic or bundle selection receipt",
        )
    matches = [item for item in candidates if item["_canonical_route_id"] == route_id and item["pool"] == "executable"]
    if len(matches) != 1:
        raise ContractError("HANDOFF_ROUTE_INVALID", "prior route is no longer uniquely executable")
    selected_candidate = matches[0]
    prior_selected = [
        item
        for item in prior["candidates"]
        if (
            isinstance(item, dict)
            and item.get("canonical_route_id") == route_id
            and item.get("route_id") == selected_candidate["route_id"]
        )
    ]
    if len(prior_selected) != 1:
        raise ContractError("HANDOFF_CANDIDATE_DRIFT", "prior receipt does not bind exactly one selected candidate")
    if prior_selected[0].get("candidate_evidence_sha256") != selected_candidate["candidate_evidence_sha256"]:
        raise ContractError("HANDOFF_CANDIDATE_DRIFT", "selected candidate evidence changed")
    if decision.get("route_type") != selected_candidate["route_type"]:
        raise ContractError("HANDOFF_ROUTE_MISMATCH", "prior receipt route type changed")
    if decision.get("version") != selected_candidate["version"]:
        raise ContractError("HANDOFF_VERSION_MISMATCH", "prior receipt selected version changed")
    if decision.get("owner") != selected_candidate["owner"]:
        raise ContractError("HANDOFF_OWNER_MISMATCH", "prior receipt selected owner changed")
    if prior.get("bundle_members") != selected_candidate["_bundle_members"]:
        raise ContractError("HANDOFF_BUNDLE_DRIFT", "prior receipt bundle membership changed")

    expected_reason = "highest-ranked-eligible-route"
    expected_discovery = {
        "status": "required",
        "reason": "no-valid-prior-receipt",
    }
    executable = sorted(
        (item for item in candidates if item["pool"] == "executable"),
        key=selection_key,
    )
    if not executable or executable[0] is not selected_candidate:
        raise ContractError("HANDOFF_CANDIDATE_DRIFT", "prior receipt did not select the deterministic winning candidate")
    if decision.get("reason") != expected_reason:
        raise ContractError("HANDOFF_ROUTE_INVALID", "prior receipt decision reason is inconsistent")
    if prior["task"].get("owner_selected_route_id") is not None:
        raise ContractError("HANDOFF_ROUTE_INVALID", "prior receipt owner-selection state is inconsistent")
    if prior["task"].get("selected_path_failed") is not False:
        raise ContractError("HANDOFF_ROUTE_INVALID", "prior receipt selected-path state is inconsistent")
    if prior.get("approvals_required") != []:
        raise ContractError("HANDOFF_ROUTE_INVALID", "an executable prior receipt cannot require setup approval")
    if prior.get("fallback") != resolved_fallback:
        raise ContractError("HANDOFF_FALLBACK_DRIFT", "prior receipt fallback accounting changed")
    if prior.get("discovery") != expected_discovery:
        raise ContractError("HANDOFF_DISCOVERY_DRIFT", "prior receipt discovery accounting is inconsistent")

    expected_candidates = copy.deepcopy(candidates)
    expected_selected = next(
        item
        for item in expected_candidates
        if item["route_id"] == selected_candidate["route_id"]
        and item["_canonical_route_id"] == selected_candidate["_canonical_route_id"]
    )
    expected_selected["final_disposition"] = "selected"
    if prior.get("candidates") != public_candidates(expected_candidates):
        raise ContractError("HANDOFF_CANDIDATE_DRIFT", "prior receipt candidate accounting changed")

    original_request = copy.deepcopy(request)
    original_request.pop("prior_receipt", None)
    original_request["task"].pop("owner_selected_route_id", None)
    original_request["task"]["selected_path_failed"] = False
    original_request["inventory"].pop("parsed_components", None)
    original_request["inventory"].pop("component_hashes", None)
    if prior.get("request_sha256") != canonical_sha256(original_request):
        raise ContractError("HANDOFF_REQUEST_HASH_MISMATCH", "prior receipt request hash changed")
    return selected_candidate


def resolve_registered_fallback(
    request: dict[str, Any],
    registry: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    specs = {
        (
            str(candidate["_record"]["fallback"]["route_type"]),
            str(candidate["_record"]["fallback"]["route_id"]),
        )
        for candidate in candidates
        if candidate["route_type"] == "bundle"
    }
    no_safe = {
        "route_type": "no-safe-route",
        "route_id": "NO_SAFE_ROUTE",
        "eligible": True,
        "reason": "no-eligible-registered-fallback",
    }
    if not specs:
        return no_safe
    if len(specs) != 1:
        raise ContractError("AMBIGUOUS_REGISTERED_FALLBACK", "candidate bundles declare different fallbacks")
    route_type, route_id = next(iter(specs))
    if route_type == "no-safe-route":
        return {
            "route_type": route_type,
            "route_id": route_id,
            "eligible": True,
            "reason": "registered-no-safe-route",
        }
    if route_type == "browser-manual":
        eligible = request["task"]["explicit_browser_choice"] or request["task"]["intrinsic_visual_testing"]
        return {
            "route_type": route_type,
            "route_id": route_id,
            "eligible": eligible,
            "reason": "registered-browser-fallback-eligible" if eligible else "registered-browser-fallback-ineligible",
        }

    matches = [
        candidate
        for candidate in candidates
        if candidate["route_type"] == route_type
        and candidate["_canonical_route_id"] == route_id
    ]
    eligible = len(matches) == 1 and matches[0]["pool"] == "executable"
    if not matches:
        reason = "registered-fallback-missing-candidate-evidence"
    elif len(matches) != 1:
        reason = "registered-fallback-ambiguous-candidate-evidence"
    elif eligible:
        reason = "registered-bundle-fallback-eligible"
    else:
        reason = "registered-bundle-fallback-ineligible"
    return {
        "route_type": route_type,
        "route_id": route_id,
        "eligible": eligible,
        "reason": reason,
    }


def route_request(raw_request: Any, choicegate_commit: str) -> dict[str, Any]:
    request = validate_request(raw_request)
    registry = build_registry(request)
    validate_route_references(request, registry)
    binding = router_binding(choicegate_commit, request["policy"])
    candidates = evaluate_candidates(request, registry)
    resolved_fallback = resolve_registered_fallback(request, registry, candidates)
    task = request["task"]

    browser_exception = task["explicit_browser_choice"] or task["intrinsic_visual_testing"]
    if (
        task.get("owner_selected_route_id")
        and not task["selected_path_failed"]
        and not browser_exception
        and "prior_receipt" not in request
    ):
        raise ContractError("PRIOR_RECEIPT_REQUIRED", "an owner-selected route requires its complete prior receipt")
    if task["selected_path_failed"]:
        for candidate in candidates:
            add_code(candidate, "EXPLICIT_CHOICE_MISMATCH")
            candidate["pool"] = "rejected"
            candidate["score_breakdown"] = None
            candidate["final_disposition"] = "selected-path-failed-stop"
        final_fallback = resolve_registered_fallback(request, registry, candidates)
        return make_receipt(
            request,
            binding,
            candidates,
            {"route_type": "no-safe-route", "route_id": "NO_SAFE_ROUTE", "version": None, "owner": None, "executable": False, "reason": "selected-path-failed-reselection-required"},
            [],
            [],
            final_fallback,
            {"status": "blocked-selected-path-failure", "reason": "selected-path-failed"},
        )
    if "prior_receipt" in request and not browser_exception:
        selected = validate_prior_receipt(
            request["prior_receipt"],
            request,
            binding,
            candidates,
            resolved_fallback,
        )
        for candidate in candidates:
            if candidate is selected:
                candidate["final_disposition"] = "selected-handoff"
                continue
            add_code(candidate, "EXPLICIT_CHOICE_MISMATCH")
            candidate["pool"] = "rejected"
            candidate["score_breakdown"] = None
            candidate["final_disposition"] = "rejected-valid-prior-choice"
        final_fallback = resolve_registered_fallback(request, registry, candidates)
        return make_receipt(
            request,
            binding,
            candidates,
            {"route_type": "handoff", "route_id": selected["_canonical_route_id"], "version": selected["version"], "owner": selected["owner"], "executable": True, "reason": "valid-prior-receipt"},
            selected["_bundle_members"],
            [],
            final_fallback,
            {"status": "suppressed-valid-handoff", "reason": "complete-prior-receipt-validated"},
        )
    if browser_exception:
        status = "skipped-explicit-browser" if task["explicit_browser_choice"] else "skipped-intrinsic-visual"
        reason = "explicit-browser-choice" if task["explicit_browser_choice"] else "intrinsic-visual-testing"
        for candidate in candidates:
            add_code(candidate, "EXPLICIT_CHOICE_MISMATCH")
            candidate["pool"] = "rejected"
            candidate["score_breakdown"] = None
            candidate["final_disposition"] = "rejected-browser-exception"
        final_fallback = resolve_registered_fallback(request, registry, candidates)
        return make_receipt(
            request,
            binding,
            candidates,
            {"route_type": "browser-manual", "route_id": "browser-manual", "version": None, "owner": None, "executable": False, "reason": reason},
            [],
            [],
            final_fallback,
            {"status": status, "reason": reason},
        )

    executable = sorted((item for item in candidates if item["pool"] == "executable"), key=selection_key)
    setup_required = sorted((item for item in candidates if item["pool"] == "setup-required"), key=selection_key)
    if executable:
        selected = executable[0]
        selected["final_disposition"] = "selected"
        return make_receipt(
            request,
            binding,
            candidates,
            {"route_type": selected["route_type"], "route_id": selected["_canonical_route_id"], "version": selected["version"], "owner": selected["owner"], "executable": True, "reason": "highest-ranked-eligible-route"},
            selected["_bundle_members"],
            [],
            resolved_fallback,
            {"status": "required", "reason": "no-valid-prior-receipt"},
        )
    if setup_required:
        selected = setup_required[0]
        selected["final_disposition"] = "selected-setup-required"
        return make_receipt(
            request,
            binding,
            candidates,
            {"route_type": "requires-setup-approval", "route_id": selected["_canonical_route_id"], "version": selected["version"], "owner": selected["owner"], "executable": False, "reason": "verified-route-requires-owner-setup"},
            selected["_bundle_members"],
            selected["_approvals"],
            resolved_fallback,
            {"status": "required", "reason": "no-valid-prior-receipt"},
        )
    return make_receipt(
        request,
        binding,
        candidates,
        {"route_type": "no-safe-route", "route_id": "NO_SAFE_ROUTE", "version": None, "owner": None, "executable": False, "reason": "no-candidate-survived-hard-exclusions"},
        [],
        [],
        resolved_fallback,
        {"status": "required", "reason": "no-valid-prior-receipt"},
    )


def canonical_url(value: str) -> str:
    """Normalize a discovery source URL for legacy candidate deduplication."""
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    path = re.sub(r"(?:\.git)?/$", "", parts.path.lower())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def legacy_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandidateError(f"{label} must be a number from 0 to 5")
    result = float(value)
    if not 0 <= result <= 5:
        raise CandidateError(f"{label} must be between 0 and 5")
    return result


def legacy_prepare(raw: dict[str, Any], index: int) -> dict[str, Any]:
    label = f"candidates[{index}]"
    name = str(raw.get("name", "")).strip()
    kind = str(raw.get("kind", "")).strip().lower()
    status = str(raw.get("status", "")).strip().lower()
    provenance = str(raw.get("provenance", "")).strip().lower()
    source_url = canonical_url(str(raw.get("source_url", "")))
    evidence = raw.get("evidence", [])
    ratings = raw.get("ratings", {})
    flags = raw.get("flags", {})
    if not name or not kind:
        raise CandidateError(f"{label} requires non-empty name and kind")
    if status not in LEGACY_STATUSES:
        raise CandidateError(f"{label}.status is not allowed")
    if provenance not in LEGACY_PROVENANCE:
        raise CandidateError(f"{label}.provenance is not allowed")
    if not isinstance(evidence, list) or any(not str(item).strip() for item in evidence):
        raise CandidateError(f"{label}.evidence must be a list of non-empty strings")
    if not isinstance(ratings, dict):
        raise CandidateError(f"{label}.ratings must be an object")
    if not isinstance(flags, dict):
        raise CandidateError(f"{label}.flags must be an object")
    scored_ratings = {
        key: legacy_number(ratings.get(key), f"{label}.ratings.{key}")
        for key in LEGACY_RATING_WEIGHTS
    }
    for key in LEGACY_HARD_FLAGS:
        if key in flags and not isinstance(flags[key], bool):
            raise CandidateError(f"{label}.flags.{key} must be true or false")
    normalized_flags = {key: flags.get(key, False) for key in LEGACY_HARD_FLAGS}
    notes = raw.get("notes", [])
    if not isinstance(notes, list):
        raise CandidateError(f"{label}.notes must be a list")
    canonical_id = slug(str(raw.get("canonical_id", "")))
    dedupe_key = canonical_id or source_url or f"{slug(name)}::{slug(kind)}"
    weighted = sum(scored_ratings[key] * weight for key, weight in LEGACY_RATING_WEIGHTS.items())
    weighted += LEGACY_PROVENANCE[provenance] * 4
    weighted += LEGACY_STATUSES[status] * 2
    max_weighted = 5 * (sum(LEGACY_RATING_WEIGHTS.values()) + 6)
    score = round(100 * weighted / max_weighted, 1)
    reasons: list[str] = []
    active_flags = sorted(key for key, active in normalized_flags.items() if active)
    if active_flags:
        reasons.append("hard safety flag: " + ", ".join(active_flags))
    for key in ("least_privilege", "privacy", "security"):
        if scored_ratings[key] < 3:
            reasons.append(f"{key.replace('_', ' ')} is below safety threshold")
    fallback_status = status == "browser_or_manual_fallback"
    if not fallback_status:
        if status == "unverified_or_risky":
            reasons.append("status is unverified or risky")
        if provenance in {"community", "unknown"}:
            reasons.append("publisher provenance is not independently verified")
        if not source_url:
            reasons.append("missing direct HTTP(S) source link")
        if len(evidence) < 2:
            reasons.append("fewer than two evidence points")
        if scored_ratings["task_fit"] < 4:
            reasons.append("task fit is below material threshold")
        if scored_ratings["improvement_over_fallback"] < 3:
            reasons.append("not materially better than fallback")
    fallback = fallback_status and not reasons
    accepted = not reasons and not fallback and score >= 65
    if not accepted and not reasons and not fallback_status:
        reasons.append("weighted score is below 65")
    return {
        "name": name,
        "kind": kind,
        "canonical_id": canonical_id or None,
        "dedupe_key": dedupe_key,
        "status": status,
        "provenance": provenance,
        "source_url": source_url or None,
        "score": score,
        "accepted": accepted,
        "fallback": fallback,
        "rejection_reasons": reasons,
        "notes": [str(item) for item in notes],
    }


def legacy_deduplicate(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for candidate in candidates:
        key = candidate["dedupe_key"]
        prior = kept.get(key)
        quality = (2 if candidate["accepted"] else 1 if candidate["fallback"] else 0, candidate["score"])
        prior_quality = (-1, -1.0) if prior is None else (
            2 if prior["accepted"] else 1 if prior["fallback"] else 0,
            prior["score"],
        )
        if prior is None or quality > prior_quality:
            if prior is not None:
                duplicates.append({"removed": prior["name"], "kept": candidate["name"], "key": key})
            kept[key] = candidate
        else:
            duplicates.append({"removed": candidate["name"], "kept": prior["name"], "key": key})
    return list(kept.values()), duplicates


def legacy_rank(payload: dict[str, Any], max_results: int) -> dict[str, Any]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise CandidateError("input requires a non-empty candidates array")
    prepared = [legacy_prepare(raw, index) for index, raw in enumerate(raw_candidates) if isinstance(raw, dict)]
    if len(prepared) != len(raw_candidates):
        raise CandidateError("every candidate must be an object")
    unique, duplicates = legacy_deduplicate(prepared)
    accepted = sorted((item for item in unique if item["accepted"]), key=lambda item: (-item["score"], item["name"].lower()))
    rejected = sorted((item for item in unique if not item["accepted"] and not item["fallback"]), key=lambda item: (-item["score"], item["name"].lower()))
    fallbacks = sorted((item for item in unique if item["fallback"]), key=lambda item: (-item["score"], item["name"].lower()))
    fallback_choice = fallbacks[0] if fallbacks else None
    candidate_limit = max_results - (1 if fallback_choice else 0)
    ranked = accepted[:candidate_limit]
    not_selected = [{**candidate, "selection_reason": "ranked below the total option limit"} for candidate in accepted[candidate_limit:]]
    return {
        "ranked": ranked,
        "not_selected": not_selected,
        "rejected": rejected,
        "fallback": fallback_choice,
        "duplicates": duplicates,
        "owner_choice_required": bool(accepted or fallbacks),
        "summary": {
            "input_count": len(raw_candidates),
            "unique_count": len(unique),
            "recommended_count": len(ranked),
            "not_selected_count": len(not_selected),
            "option_count": len(ranked) + (1 if fallback_choice else 0),
        },
    }


def read_json_source(source: str, label: str) -> Any:
    try:
        raw_bytes = sys.stdin.buffer.read() if source == "-" else Path(source).read_bytes()
    except OSError as error:
        raise ContractError("INPUT_READ_FAILED", f"{label}: {error}") from error
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("INVALID_UTF8", f"{label}: input is not valid UTF-8") from error
    return strict_json_loads(raw, label)


def failure_envelope(error: ContractError, choicegate_commit: str | None) -> dict[str, Any]:
    envelope = {
        "failure_version": FAILURE_VERSION,
        "error_code": error.code,
        "message": error.message,
        "details": list(error.details),
        "choicegate_commit": choicegate_commit,
    }
    envelope["failure_sha256"] = canonical_sha256(envelope)
    return envelope


def internal_failure_envelope(choicegate_commit: str | None) -> dict[str, Any]:
    envelope = {
        "failure_version": FAILURE_VERSION,
        "error_code": "UNEXPECTED_INTERNAL_FAILURE",
        "message": "unexpected internal router failure",
        "details": [],
        "choicegate_commit": choicegate_commit,
    }
    envelope["failure_sha256"] = canonical_sha256(envelope)
    return envelope


def canonical_print(value: Any) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="strict route-request JSON file, or - for stdin")
    parser.add_argument(
        "--choicegate-commit",
        required=True,
        help="40-character lowercase commit binding for the executing Choicegate tree",
    )
    args = parser.parse_args()
    try:
        payload = read_json_source(args.input, "route request")
        canonical_print(route_request(payload, args.choicegate_commit))
        return 0
    except ContractError as error:
        canonical_print(failure_envelope(error, args.choicegate_commit))
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    except Exception:
        canonical_print(internal_failure_envelope(args.choicegate_commit))
        print("UNEXPECTED_INTERNAL_FAILURE: unexpected internal router failure", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
