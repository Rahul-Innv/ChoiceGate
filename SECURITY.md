# Security Policy

## Supported versions

ChoiceGate is pre-1.0. Security fixes apply only to the current 0.1.0 pre-release line; no stable
release line is supported yet.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private repository names, owner
paths, or other sensitive data. Contact the maintainer privately through GitLab. When the canonical
project supports confidential issues, use a confidential issue and include only the minimum redacted
reproduction needed.

Include the affected contract or skill, the boundary that can be bypassed, a minimal reproduction,
the expected fail-closed behavior, and any known mitigation. Never test against a repository,
account, provider, or marketplace you do not own or have explicit permission to assess.

## Security boundaries

ChoiceGate must continue to reject duplicate JSON keys, stale or unbound evidence, unauthorized or
ineligible candidates, incompatible surfaces, ambiguous owners, and attempts to turn selection into
execution. It must never print secrets, request pasted credentials, silently authenticate, call a
provider, install a capability, or treat local evidence as proof of remote state.
