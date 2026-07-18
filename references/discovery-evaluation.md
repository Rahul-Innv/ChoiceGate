# Discovery and evaluation reference

Contents: [Inventory](#inventory-routes) | [Budget](#search-budget-and-coverage) | [Evidence](#evidence-standard) | [Statuses](#status-model) | [Rubric](#comparison-rubric) | [Ranking](#ranking-helper-input) | [Report](#compact-report)

## Inventory routes

Use only routes present and permitted in the current environment.

- **Current session:** Read callable tool and skill declarations first. Note plugin provenance in tool metadata and any available-but-uninstalled plugin list. Use tool search when exposed.
- **Codex/ChatGPT:** Prefer the Plugins directory, `/plugins`, configured marketplace metadata, or `codex plugin marketplace list` when available. Inspect installed/enabled state separately from connector authorization. Current official guidance: [Plugins](https://learn.chatgpt.com/docs/plugins) and [Build plugins](https://learn.chatgpt.com/docs/build-plugins).
- **Claude Code:** Prefer `claude plugin list --available --json`, `claude plugin marketplace list`, `claude plugin details <name>`, and `claude mcp list`. On Windows PowerShell, use `claude.cmd` if execution policy blocks `claude.ps1`. Current official guidance: [Discover plugins](https://code.claude.com/docs/en/discover-plugins) and [MCP](https://code.claude.com/docs/en/mcp).
- **MCP:** Search the [Official MCP Registry](https://registry.modelcontextprotocol.io/) and its [registry documentation](https://modelcontextprotocol.io/registry/about). A registry listing proves publication metadata, not safety or suitability.
- **Provider:** Prefer the provider's own product/API/CLI/SDK documentation, security and privacy pages, pricing, limits, release notes, and official source organization.
- **GitHub/public web:** Prefer an installed GitHub connector or `gh` CLI, then web search. Inspect the canonical repository, releases, recent commits, issue handling, security policy, license, package ownership, and archived/deprecated status. Never execute README install snippets during discovery.

Do not run a CLI just because it exists. Safe discovery commands are limited to metadata such as list, status, help, version, and public catalog search. Do not use a service search/query command to test authorization or inspect account data. Do not print environment variables, tokens, headers, cookies, credential stores, or full configuration files.

## Search budget and coverage

For a routine discovery, perform at most one focused pass per relevant tier: current session, client marketplace, official registry/provider, and narrow GitHub/public-web corroboration. Stop after verifying up to three distinct execution paths, including the fallback. Expand only when the owner asks for exhaustive research or the bounded passes cannot resolve a material decision.

Report relevant sources as `CHECKED`, `UNAVAILABLE`, `AUTH_REQUIRED`, or `NOT_RELEVANT`. Include the observed snapshot date when a local marketplace exposes one. Do not update a marketplace, install a search tool, or authenticate merely to improve coverage. An unavailable source is an evidence gap, not a negative result.

## Evidence standard

For an accepted candidate, record:

1. A direct primary link proving publisher identity and actual capability.
2. Independent evidence for maintenance, permissions/data flow, security/privacy, cost/limits, or platform support as relevant.
3. Current-session metadata for installed, enabled, and authorization state, when explicitly exposed. Treat unknown authorization as configuration-required; never prove it by reading service data.

Reject or quarantine a candidate when publisher identity is ambiguous, the package name is typosquatted, activity is abandoned without a stable reason, permissions are broader than the task, data handling is undisclosed, install steps fetch and execute unreviewed code, claims cannot be independently verified, or use depends on evading account controls or making a paid commitment.

## Status model

| Status | Meaning |
| --- | --- |
| `INSTALLED_USABLE` | Present, task-fit, and authorization explicitly confirmed by metadata or a non-data status route |
| `AVAILABLE_TO_INSTALL` | Verified candidate exists but is not installed or enabled |
| `REQUIRES_AUTH_OR_CONFIG` | Present or available, but authorization/configuration is missing or unknown |
| `UNVERIFIED_OR_RISKY` | Quarantined or rejected; never recommend or execute |
| `BROWSER_OR_MANUAL_FALLBACK` | No material trustworthy integration; requires owner choice unless the fast exception applies |

## Comparison rubric

Rate each dimension from 0 (unacceptable/unknown) to 5 (excellent/verified):

| Dimension | Prefer |
| --- | --- |
| Task fit | Direct structured coverage of the requested outcome |
| Provenance | First-party provider or independently verified maintainer |
| Maintenance | Recent releases/commits, responsive issues, clear support |
| Permissions | Least privilege and separable read/write scopes |
| Data access | Only necessary records/fields; clear data path and hosting |
| Privacy/security | Documented controls, no secret leakage, auditable behavior |
| Cost/limits | Known cost, no required paid action, usable rate limits |
| Install friction | Reversible, reviewable, minimal dependencies |
| Compatibility | Works on the owner's client, OS, runtime, and account tier |
| Non-overlap | Adds material capability instead of duplicating installed tools |
| Improvement | Credibly better than browser/manual execution |

Unknown is not neutral. Score unknown security, privacy, permissions, or provenance as 0 and reject the candidate from the recommended set.

## Ranking-helper input

Pass a JSON object with a `candidates` array. Prefer `python <skill-dir>/scripts/rank_candidates.py -` plus the tool runner's stdin so discovery does not write a file. Use a temporary file outside the project only when stdin control is unavailable. Each candidate needs:

```json
{
  "name": "Use the installed Example connector",
  "kind": "execution_path",
  "canonical_id": "provider/example",
  "status": "available_to_install",
  "provenance": "official_first_party",
  "source_url": "https://provider.example/docs/integration",
  "evidence": ["provider capability page", "current release page"],
  "ratings": {
    "task_fit": 5,
    "maintenance": 4,
    "least_privilege": 4,
    "data_access": 4,
    "privacy": 4,
    "security": 4,
    "cost": 3,
    "rate_limits": 3,
    "installation_friction": 3,
    "platform_compatibility": 5,
    "non_overlap": 5,
    "improvement_over_fallback": 5
  },
  "flags": {
    "unsafe": false,
    "account_evasion": false,
    "requires_paid_action": false,
    "would_expose_secrets": false,
    "unverified_claims": false
  },
  "notes": ["Requires OAuth approval"]
}
```

Allowed lowercase statuses are `installed_usable`, `available_to_install`, `requires_auth_or_config`, `unverified_or_risky`, and `browser_or_manual_fallback`. Allowed provenance values are `official_first_party`, `official_marketplace`, `verified_maintainer`, `community`, and `unknown`.

## Compact report

```markdown
Recommendation: <best option, no material alternative, or browser exception>

Options:
1. <outcome and next step> — <STATUS>
   Why: <material advantage over the other paths>
   Access: <permissions, data, auth/config>
   Tradeoffs: <privacy/security, cost/limits, friction, compatibility>
   Evidence: <direct links>

Coverage: <source — CHECKED/UNAVAILABLE/AUTH_REQUIRED/NOT_RELEVANT; ...>
Rejected: <candidate — concise reason and link>
Not selected: <verified contender — why it ranked below the three-option limit>
Owner choice: <choose option 1, 2, or 3>
```

Omit the owner-choice line only when the owner explicitly chose browser/Chrome or visual interactive testing is intrinsic and already requested.
