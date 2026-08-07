# START_HERE

## 1. Repository identity

Canonical repository: `rigolugo/ARB`.

## 2. Public repository warning

**This repository is public.**

## 3. Safety defaults

- No live trading is permitted by default.
- Technical capability, repository access, or credentials do not constitute authorization.
- Credentials, keys, tokens, private URLs, account data, and sensitive artifacts are prohibited anywhere in this repository.

## 4. Current authorized phase

The Candidate 10 documentation bootstrap is complete and has been accepted by Gustavo. Gustavo separately accepted the exact Kalshi Demo environment-separation and capability-envelope specification Candidate 02 (Bruno's specification and handoff identities) and separately authorized a bounded documentation-only canonical installation, which records those accepted Candidate 02 artifacts and Marco's approval review in this repository.

In addition, Gustavo separately authorized a bounded technical implementation task, and the resulting Kalshi Demo offline environment-separation and capability-envelope validator (`KALSHI_DEMO_ENVIRONMENT_SEPARATION_OFFLINE_VALIDATOR_IMPLEMENTATION_05`) is accepted and canonically installed at exact commit `049ce4bdfebd39eee7e366431acea36ca3d55e18`, following Marco's independent review of the implementation package and of the browser-created remote commit, and Marco's non-force fast-forward of `main` after approval. This validator is a pure, offline, non-secret static validator only: it performs no DNS resolution, no socket, HTTP, or WebSocket activity, no credential reads, no private-key parsing, and no signing, and it constructs no transport, signer, or venue client of any kind. It is not a connectivity implementation, venue adapter, market-data implementation, order implementation, or trading implementation.

No connectivity, network execution, authentication, venue-adapter, market-data, order, fill, ledger, strategy, or trading implementation is authorized. No subsequent technical phase beyond the accepted offline validator is currently authorized. All Kalshi Demo, Kalshi production, and Polymarket venue access, all credential use, all account funding, and all order, cancellation, and trading activity remain prohibited. Kalshi Demo network access requires a separately accepted connectivity-preflight specification and a separately bounded implementation/execution authorization; no such authorization currently exists.

## 5. Canonical read order

1. `START_HERE.md` (this file)
2. `project_context/START_HERE.md`
3. `project_context/GUARDRAILS.md`
4. `project_context/PROJECT_STATE.md`
5. `project_context/AUTHORIZATION_LOG.md`
6. `project_context/DECISION_LOG.md`
7. `project_context/AGENT_ROLES.md`
8. the accepted-candidate identity table recorded in the authorization chain
9. `specifications/SPEC_repository_bootstrap.md`
10. `reviews/REVIEW_repository_bootstrap_spec.md`
11. `handoffs/HANDOFF_repository_bootstrap_spec.md`
12. `handoffs/HANDOFF_repository_bootstrap_implementation.md`
13. `specifications/SPEC_kalshi_demo_environment_separation_and_capability_envelope.md`
14. `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec.md`
15. `reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md`
16. `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation.md`
17. relevant `project_context/ARTIFACT_INDEX.md` entries

## 6. Prohibited sensitive content

No `.env` files (other than deliberately tracked `.example` placeholders), private keys, credentials, account identifiers, funding details, wallet secrets, private or signed URLs, venue tokens, raw sensitive logs, local databases, or personal data may be committed to this public repository.

## 7. Authorization statement

Absent authorization means prohibited. Anything not explicitly permitted by an active, exact authorization entry is prohibited.

## 8. Demo evidence limitation

Kalshi Demo results are not production evidence. Demo evidence does not establish production correctness, safety, liquidity, or profitability.

## 9. Approval authority

Gustavo is the sole project approval authority. See `project_context/START_HERE.md` and `project_context/AGENT_ROLES.md` for the full workflow and role boundaries.
