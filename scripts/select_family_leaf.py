#!/usr/bin/env python3
"""Select one atomic Choicegate family leaf without performing leaf work."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUEST_VERSION = "choicegate.family-request/v1"
RECEIPT_VERSION = "choicegate.family-dispatch-receipt/v1"
FAILURE_VERSION = "choicegate.family-dispatch-failure/v1"
DOMAIN_TO_LEAF = {
    "context": "choicegate-context",
    "generators": "choicegate-generators",
    "integrations": "choicegate-integrations",
    "refresh": "choicegate-refresh",
    "skills": "choicegate-skills",
    "tools": "choicegate-tools",
}
PROHIBITED_ACTIONS = (
    "activate",
    "authorize",
    "configure",
    "enable",
    "execute-selected-capability",
    "expose",
    "install",
    "promote",
)
STABLE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ContractError(ValueError):
    """A deterministic, caller-correctable family request failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object while rejecting every duplicate key."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(
            "STRICT_SCHEMA_VIOLATION",
            f"{label} fields differ: missing={sorted(expected - actual)} extra={sorted(actual - expected)}",
        )


def require_stable_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or STABLE_ID.fullmatch(value) is None:
        raise ContractError("INVALID_VALUE", f"{label} must be a stable lowercase identifier")
    return value


def validate_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractError("INVALID_TYPE", "family request must be an object")
    exact_keys(raw, {"contract_version", "request_id", "claims", "legacy_invocation"}, "request")
    if raw["contract_version"] != REQUEST_VERSION:
        raise ContractError("UNSUPPORTED_REQUEST_VERSION", "unsupported family request version")
    request_id = require_stable_id(raw["request_id"], "request_id")
    legacy_invocation = raw["legacy_invocation"]
    if type(legacy_invocation) is not bool:
        raise ContractError("INVALID_TYPE", "legacy_invocation must be Boolean")
    claims_raw = raw["claims"]
    if not isinstance(claims_raw, list) or len(claims_raw) > len(DOMAIN_TO_LEAF):
        raise ContractError("INVALID_TYPE", "claims must be an array with at most six entries")
    claims: list[dict[str, str]] = []
    domains: set[str] = set()
    evidence_ids: set[str] = set()
    for index, item in enumerate(claims_raw):
        if not isinstance(item, dict):
            raise ContractError("INVALID_TYPE", f"claims[{index}] must be an object")
        exact_keys(item, {"domain", "specificity", "evidence_id"}, f"claims[{index}]")
        domain = item["domain"]
        if domain not in DOMAIN_TO_LEAF:
            raise ContractError("UNKNOWN_DOMAIN", f"claims[{index}].domain is not owned by Choicegate")
        if domain in domains:
            raise ContractError("DUPLICATE_DOMAIN_CLAIM", f"duplicate domain claim: {domain}")
        specificity = item["specificity"]
        if specificity not in {"explicit", "inferred"}:
            raise ContractError("INVALID_VALUE", f"claims[{index}].specificity is invalid")
        evidence_id = require_stable_id(item["evidence_id"], f"claims[{index}].evidence_id")
        if evidence_id in evidence_ids:
            raise ContractError("DUPLICATE_EVIDENCE_ID", f"duplicate claim evidence: {evidence_id}")
        domains.add(domain)
        evidence_ids.add(evidence_id)
        claims.append({"domain": domain, "specificity": specificity, "evidence_id": evidence_id})
    if legacy_invocation and claims:
        raise ContractError("LEGACY_ALIAS_COLLISION", "legacy alias invocation cannot carry domain claims")
    return {
        "contract_version": REQUEST_VERSION,
        "request_id": request_id,
        "claims": sorted(claims, key=lambda item: (item["domain"], item["evidence_id"])),
        "legacy_invocation": legacy_invocation,
    }


def select_leaf(validated: dict[str, Any]) -> dict[str, Any]:
    claims = validated["claims"]
    if validated["legacy_invocation"]:
        return {"route_type": "dispatcher", "leaf_id": "choicegate", "reason": "explicit-legacy-alias"}
    if not claims:
        return {"route_type": "no-safe-route", "leaf_id": None, "reason": "no-supported-domain-claim"}
    if len(claims) == 1:
        return {
            "route_type": "atomic-leaf",
            "leaf_id": DOMAIN_TO_LEAF[claims[0]["domain"]],
            "reason": "single-domain-claim",
        }
    explicit = [claim for claim in claims if claim["specificity"] == "explicit"]
    if len(explicit) == 1:
        return {
            "route_type": "atomic-leaf",
            "leaf_id": DOMAIN_TO_LEAF[explicit[0]["domain"]],
            "reason": "one-explicit-domain-precedes-inferred",
        }
    return {"route_type": "no-safe-route", "leaf_id": None, "reason": "ambiguous-domain-claims"}


def dispatch(raw: Any) -> dict[str, Any]:
    request = validate_request(raw)
    receipt: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "request_id": request["request_id"],
        "request_sha256": canonical_sha256(request),
        "claims": sorted(request["claims"], key=lambda item: (item["domain"], item["evidence_id"])),
        "decision": select_leaf(request),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def failure(code: str, message: str) -> dict[str, Any]:
    result = {"failure_version": FAILURE_VERSION, "error_code": code, "message": message}
    result["failure_sha256"] = canonical_sha256(result)
    return result


def read_request(path: str) -> Any:
    raw = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("INVALID_UTF8", "family request is not strict UTF-8") from error
    try:
        return json.loads(text, object_pairs_hook=unique_object)
    except ContractError:
        raise
    except json.JSONDecodeError as error:
        raise ContractError("INVALID_JSON", "family request is not valid JSON") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="strict JSON request path, or - for stdin")
    args = parser.parse_args()
    try:
        result = dispatch(read_request(args.request))
    except ContractError as error:
        sys.stdout.buffer.write(canonical_bytes(failure(error.code, str(error))) + b"\n")
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    except Exception:
        result = failure("UNEXPECTED_INTERNAL_FAILURE", "unexpected internal failure")
        sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
        print("UNEXPECTED_INTERNAL_FAILURE: unexpected internal failure", file=sys.stderr)
        return 3
    sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
