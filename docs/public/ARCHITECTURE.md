# ChoiceGate architecture

ChoiceGate separates capability selection from capability execution.

## Authority boundaries

- **The accepted capability registry** owns lifecycle eligibility and routing priority. ChoiceGate
  binds to one owner-accepted registry snapshot by content hash and never mutates it.
- **Rigwright** owns authoring and evaluation workflows, not selection.
- **ChoiceGate** owns deterministic selection and receipt generation.
- Product families own their implementations and thin consumers.
- Surface adapters translate one neutral contract; they do not become a second policy authority.

## Components

`scripts/select_family_leaf.py` dispatches a broad request to exactly one of six domain leaves or
returns no safe route. `scripts/route_capabilities.py` ranks frozen candidate evidence against the
accepted registry binding and emits a hash-bound receipt. Schemas define typed requests and receipts.
The seven `skills/choicegate*` directories provide narrow trigger surfaces over that shared core.

The root `SKILL.md` is a compatibility-only `discover-better-tools` alias. It is explicit-invocation
only, noncanonical, and never coeligible with the canonical family.

## Failure model

The system fails closed on malformed or duplicate-key JSON, unknown contract versions, stale or
unbound inventories, ambiguous owners, ineligible lifecycle states, missing required bundle members,
surface mismatch, authorization uncertainty, and selected-path failure. A receipt cannot grant
permission to execute, install, authenticate, configure, or call the selected capability.
