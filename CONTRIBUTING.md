# Contributing to ChoiceGate

Contributions should improve capability selection without weakening lifecycle, authorization,
evidence, surface, or fail-closed boundaries.

## Before proposing a change

1. Keep the family router dispatch-only and each leaf limited to one measurable outcome.
2. Do not duplicate ranking, hashing, schema, or receipt logic across surface adapters.
3. Preserve the accepted external capability registry as lifecycle and routing-priority authority.
4. Never include credentials, owner home paths, private repositories, browser state, or private
   product data in fixtures, screenshots, logs, or documentation.
5. Add or update a positive, near-miss, collision, malformed-input, or regression case whenever
   routing behavior changes.

## Validation

Run the portable repository suite on every change:

```powershell
python -B -m unittest discover -s tests -p "test_*.py"
```

Maintainers also run the authority-bound suite against the exact owner-accepted capability-registry
snapshot. A passing portable suite is not a substitute for that authority-bound replay.

## Merge requests

Describe the intent owner, changed paths, exact tests run, compatibility effects, privacy/security
impact, and every owner-only or outward action that remains. Do not combine publication, tagging,
marketplace, installation, lifecycle promotion, or remote changes with a product change.
