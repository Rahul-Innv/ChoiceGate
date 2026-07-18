#!/usr/bin/env python3
"""Backward-compatible discovery ranking entry point backed by Choicegate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .route_capabilities import (
        CandidateError,
        LEGACY_HARD_FLAGS,
        LEGACY_PROVENANCE,
        LEGACY_RATING_WEIGHTS,
        LEGACY_STATUSES,
        canonical_url,
        legacy_deduplicate,
        legacy_number,
        legacy_prepare,
        legacy_rank,
        slug,
    )
except ImportError:
    from route_capabilities import (
        CandidateError,
        LEGACY_HARD_FLAGS,
        LEGACY_PROVENANCE,
        LEGACY_RATING_WEIGHTS,
        LEGACY_STATUSES,
        canonical_url,
        legacy_deduplicate,
        legacy_number,
        legacy_prepare,
        legacy_rank,
        slug,
    )


# Preserve the original import-level API while keeping one scoring implementation.
STATUSES = LEGACY_STATUSES
PROVENANCE = LEGACY_PROVENANCE
RATING_WEIGHTS = LEGACY_RATING_WEIGHTS
HARD_FLAGS = LEGACY_HARD_FLAGS
number = legacy_number
prepare = legacy_prepare
deduplicate = legacy_deduplicate
rank = legacy_rank


def read_payload(source: str) -> dict[str, Any]:
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise CandidateError("input root must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON candidate file, or - to read stdin")
    parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        choices=range(1, 4),
        help="maximum total owner-facing options, including fallback",
    )
    args = parser.parse_args()
    try:
        payload = read_payload(args.input)
        result = rank(payload, args.max_results)
    except (OSError, json.JSONDecodeError, CandidateError) as error:
        print(json.dumps({"error": str(error)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
