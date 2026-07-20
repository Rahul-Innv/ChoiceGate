# ChoiceGate routing contract

ChoiceGate selects one evidence-backed atomic capability, one registry-approved bundle, an owner-gated setup path, the explicit browser/manual exception, or `NO_SAFE_ROUTE`. It is a pure local decision boundary. It does not install, enable, expose, authorize, configure, invoke, message, spend, mutate a remote, or write evidence.

## Accepted authority binding

Version 1 accepts one owner-accepted snapshot of an external capability registry as its lifecycle and routing-priority authority:

- commit: `354046f9627c4a83a2a912e09a656d1871ed6cc4`
- tree: `786171bc52fe6efeefb860f01bb71d4c09ed3504`
- 16-component inventory fingerprint: `6ef1493691332e372106b652c991a4e9477c869d1a22e10af319845ae533198b`
- 17-component authority fingerprint including `registry/system.json`: `ed0bcb140ef9456eca22fbbaf9f0de3a662d642cf57a4314abe0ac0b3ff28f15`
- `registry/system.json` SHA-256: `1f89dd859977fa3616914d82e74280be49c927865f1bb96cf8bfe4a18800bc87`
- state model: `orthogonal-seven-axis-v1`
- manifest algorithm: `sha256-path-hash-manifest-v1`

For public reproducibility, the same request version also accepts one separately pinned
`public-demo-v1` profile with fingerprint
`80963c6f548e4830a98e98c555a14546fb3e05c017765efda1a30680fc9f836f`. The demo is accepted only
with fixture ID `public-demo`; its `accepted_registry_commit` must be `null` so synthetic data cannot
claim Git provenance. It exercises the full router but grants no owner lifecycle authority. The
owner profile still requires the exact commit and fingerprint above, and a null commit without the
demo profile fails closed.

The request must embed the exact bytes and SHA-256 digest of every declared component. The router accepts exactly these sixteen paths:

1. `evals/choicegate/inventory-fixtures.json`
2. `evals/choicegate/manifest.json`
3. `evals/choicegate/routing-cases.json`
4. `registry/bundles.json`
5. `registry/capabilities.json`
6. `registry/conflicts.json`
7. `registry/dependencies.json`
8. `registry/preconditions.json`
9. `registry/schemas/bundle.schema.json`
10. `registry/schemas/capability.schema.json`
11. `registry/schemas/conflict.schema.json`
12. `registry/schemas/dependency.schema.json`
13. `registry/schemas/precondition.schema.json`
14. `registry/schemas/supersession.schema.json`
15. `registry/state-axes.json`
16. `registry/supersessions.json`

For each path, hash the exact UTF-8 bytes. Sort paths ordinally, serialize each row as `path<TAB>sha256<LF>`, concatenate without a header, then SHA-256 the manifest bytes. A missing, extra, duplicate, byte-mismatched, wrong-commit, wrong-model, wrong-algorithm, or wrong-fingerprint input fails closed.

Fixture scope is test-only. Accepted fixture overrides are applied to an in-memory copy and never change the authority fingerprint. A fixture-declared synthetic wrapper must name an existing canonical capability and the same owner; the canonical route is made executable only inside that fixture so duplicate-owner behavior is isolated from unrelated baseline inactivity.

## Request contract

The strict Draft 2020-12 schema is [route-request.schema.json](../schemas/route-request.schema.json), schema ID `choicegate.route-request/v1`. Unknown fields, unsupported versions, duplicate IDs, non-finite numbers, duplicate JSON keys, invalid references, invalid bundle order, dependency cycles, and inconsistent supersessions fail closed.

The caller supplies:

- a stable request ID and explicit UTC evaluation time;
- task class, required outcomes, allowed scope, surface, data class, risk, preconditions, context ceiling, requested route IDs, and browser/visual intent;
- bounded candidate evidence with canonical route identity, version, outcome coverage, task fit, cost, freshness, risk flags, required scope, required private-data class, and evidence references bound to an embedded inventory component and, when present, one of that component's declared IDs;
- the complete accepted inventory envelope;
- a canonical policy hash and any exact, reversible, reviewed, owner-approved setup paths;
- the complete prior receipt when handing off an already selected path.

The router canonicalizes JSON with recursively sorted object keys, UTF-8 without a BOM, JSON-native scalars, no insignificant whitespace, and arrays in their declared order. Transport formatting, object-key order, LF/CRLF, Windows path strings, and non-ASCII text do not change a decision. Ordered bundle-member changes do.

Candidate route IDs must equal their canonical registry ID unless the accepted fixture declares the route as a synthetic wrapper for that same canonical owner. Every requested route ID must resolve to a registered route or such a fixture wrapper. Fixture-scoped candidates must also be present in the fixture's discoverable set or bundle overrides. Non-browser routes must be explicitly supported on the requested local, Codex, or Claude Code surface by accepted source or adapter metadata; unknown support fails closed.

## Hard exclusions and deterministic selection

Candidates are filtered before scoring. Stable exclusion codes are evaluated in this order:

1. `UNSAFE_OR_UNVERIFIED`
2. `NOT_PROMOTED_FOR_ROUTE`
3. `STALE_EVIDENCE`
4. `UNAVAILABLE_NO_APPROVED_SETUP`
5. `SETUP_APPROVAL_REQUIRED`
6. `AUTHORIZATION_MISMATCH`
7. `SURFACE_MISMATCH`
8. `DUPLICATE_CANONICAL_OWNER`
9. `DEPENDENCY_UNSATISFIED`
10. `PROVIDER_FAMILY_CONFLICT`
11. `PRECONDITION_UNSATISFIED`
12. `CONTEXT_BUDGET_EXCEEDED`
13. `BUNDLE_NOT_APPROVED`
14. `BUNDLE_MEMBER_UNAVAILABLE`
15. `BUNDLE_UNNECESSARY`
16. `SCOPE_OR_RISK_MISMATCH`
17. `EXPLICIT_CHOICE_MISMATCH`

An approved setup path is a choice, not execution. It must enumerate reversible reviewed actions and approval IDs. `configure` may satisfy an unknown authorization prerequisite only when configuration was explicitly approved. Setup-required candidates are never marked executable.

A bundle request must declare every registered required member role as necessary, must require at least two such roles, and may name only registered member roles. Unknown, unused-required, or zero-role bundles are rejected before scoring. Optional members are selected only when their role is explicitly necessary; every omission remains visible in the receipt. Boolean preconditions require the exact Boolean value; the bounded `max_attempts` precondition requires an integer from one through three. Arbitrary truthy values are never accepted.

After exclusions, deterministic selection prefers exact task-class match, more required outcomes, higher task fit, narrower scope, lower risk, lower context and expected cost, fewer members, then lexical canonical route ID. A bundle is rejected as unnecessary when one executable atomic candidate completely covers the task. Atomic routes and every selected bundle member must be installed or not applicable, enabled or not applicable, exposed on a supported surface, authorized or not required, active or available, and promoted. Required bundle members must be ready, dependencies and preconditions must hold, and provider-family conflicts reject the composite route. A bundle-declared fallback is eligible only when the fallback has its own unique candidate evidence and remains executable after the complete pipeline, including route-level selected-path, handoff, and browser-exception filtering; its receipt accounting is recomputed after any such filter. Missing fallback evidence never synthesizes an executable route. Otherwise the router returns `NO_SAFE_ROUTE`.

## Receipt and handoff

The strict receipt schema is [decision-receipt.schema.json](../schemas/decision-receipt.schema.json), schema ID `choicegate.decision-receipt/v1`. A receipt binds:

- canonical request SHA-256;
- registry profile, accepted inventory commit (null only for the synthetic public demo), fingerprint,
  and all component hashes;
- ChoiceGate commit, router and policy versions, policy hash, both schema hashes, router source hash, legacy helper hash, and the router-text hash algorithm;
- normalized task, decision, candidate accounting with a canonical candidate-evidence hash, bundle membership, approvals, fallback, discovery status, reselection triggers, and prohibited actions;
- canonical receipt SHA-256.

The caller passes the exact executing ChoiceGate commit through `--choicegate-commit`; the router does not inspect or alter Git. Router artifact hashes use `sha256-utf8-lf-v1`: decode each schema, router source, and deterministic helper as strict UTF-8; replace CRLF and bare CR with LF; preserve every other code point and the final-newline state; encode as UTF-8; then SHA-256 the canonical bytes. This prevents Git's platform line-ending materialization from changing the binding while keeping every non-line-ending byte significant. It does not alter the accepted registry inventory rule above, which continues to require the exact embedded UTF-8 bytes and accepted component digests. Before freezing or handing off a route, validate `receipt_sha256` over every receipt field except `receipt_sha256` itself.

A chosen-path handoff requires the complete original atomic or bundle selection receipt and the same stable request ID. The request schema contains a self-contained strict top-level receipt envelope; the complete receipt also remains independently valid against the receipt schema. ChoiceGate validates its hash, reconstructible request hash, inventory and router bindings, unchanged task scope, complete candidate accounting, deterministic original winner, fallback and discovery accounting, selected candidate-evidence hash, route type, version, owner, ordered bundle membership, identity, and current candidate eligibility. A bare route ID, different request ID, truncated receipt, changed scope, changed candidate permissions or risk evidence, changed authority, changed selected version, or failed selected path stops and requires reselection.

A handoff receipt is continuity evidence, not a chainable authority token. Reuse the original atomic or bundle selection receipt for each later unchanged continuation. This keeps repeated handoffs deterministic without treating an unkeyed, rehashed handoff output as proof of an earlier owner choice.

Reselect when availability, authorization, evidence freshness, inventory, router binding, bundle contract, owner gate, permission/risk, scope, or owner intent changes, or when the selected path fails. Do not rediscover for an unchanged valid handoff.

## CLI and evidence capture

Run from any working directory:

```text
python <skill-dir>/scripts/route_capabilities.py <request.json-or-dash> --choicegate-commit <40-lowercase-hex>
```

Use `-` for stdin when possible. The process writes exactly one canonical JSON envelope to stdout:

| Result | Exit | Meaning |
| --- | ---: | --- |
| Receipt, including valid `NO_SAFE_ROUTE` | `0` | Complete deterministic decision |
| Contract, schema, hash, or invariant failure | `2` | No route; deterministic failure envelope and concise stderr diagnostic |
| Unexpected internal failure | `3` | No route or fallback; generic failure envelope and concise stderr diagnostic |

The router does not write files. The caller preserves request, stdout, stderr, exit status, component manifest, and router binding under a new evidence attempt path. Partial output is never a receipt.

`scripts/rank_candidates.py` remains a backward-compatible discovery helper. Its import API, scoring, output shape, exit codes, and formatted stdout/stderr remain compatible, but its normalization and scoring implementation lives in the ChoiceGate router module to prevent a second ranking authority.
