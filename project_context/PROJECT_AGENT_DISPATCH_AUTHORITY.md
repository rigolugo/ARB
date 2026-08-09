# Project Agent Dispatch Authority

## Status and hierarchy

This file defines how Bruno and Neo evaluate bounded task dispatches, same-scope corrections, risk-tier evidence, and return-to-Gustavo conditions. It is subordinate to `project_context/GUARDRAILS.md` and to platform/system safety requirements.

A bounded exact task prompt posted by Gustavo in Bruno's or Neo's current project chat is the operative task authorization for the capabilities and paths it explicitly permits. Canonical `AUTHORIZATION_LOG.md` and `DECISION_LOG.md` entries are audit history; they need not pre-exist an already-authorized task and cannot retroactively authorize activity outside the original dispatch.

Missing capability remains prohibited. A named artifact is a required input only when the active dispatch identifies it as a controlling source, predecessor, exact-copy input, required evidence, or required deliverable.

## Core dispatch rules

1. Gustavo remains the sole project approval authority.
2. Marco remains the independent orchestrator/reviewer. Marco review direction is not a new authorization.
3. Bruno remains the standing specification author.
4. Neo remains the standing implementation/test agent.
5. A task-specific Gustavo dispatch may temporarily authorize a narrower different activity without changing standing roles.
6. Technical capability, repository access, prior work, credentials, tools, or a risk-tier label never grant authority.
7. Omitted, malformed, unknown, stale, conflicting, or ambiguous permission is `PROHIBITED`.
8. No task may silently broaden objective, phase, artifact class, paths, venue/environment, network, credentials, writes, funding, execution, economic behavior, or risk.

## Required dispatch content

A bounded dispatch should state, directly or by exact incorporated reference, the task identifier, authorized agent, objective/phase, repository/base when relevant, controlling artifact identities when relevant, permitted artifact class, exact paths or path envelope, capability ceiling, venue/environment authority, network/credential/write/funding/trading permissions, risk tier, halt conditions, evidence/output, and completion/termination condition.

For correction-enabled work the dispatch additionally uses exactly:

```text
same_scope_corrections_after_marco_block: PERMITTED | PROHIBITED
```

Omitted, malformed, unknown, or ambiguous values are `PROHIBITED`.

## Source-binding scope and freshness

Source identities are operation- and observation-specific. A raw OpenAPI/AsyncAPI/documentation byte identity accepted for one operation or one prior task is historical provenance; it is not a standing declaration that those bytes remain the venue's current specification and it does not automatically control a different operation.

If an active dispatch requires a `current`, `fresh`, `then-current`, or equivalent source binding, all of the following apply unless the dispatch states a stricter rule:

1. the authorized agent must obtain or directly observe the official source during the active task;
2. the task must record the retrieval/observation timestamp and every exact byte/hash/version identity required by the dispatch;
3. operation-specific bindings must be derived from that task-current source rather than inherited from an unrelated earlier operation;
4. a historical or cached source snapshot may substitute only when the exact active dispatch explicitly permits that substitution;
5. inability to obtain or identity-bind the required current source is a stop condition, not permission to reuse the newest repository-stored hash;
6. a renderer, narrative guide, example, cached page, or prior implementation does not override an exact authoritative source precedence stated by the task;
7. a material conflict among official sources fails closed until the conflict is resolved within authorized scope or returned to Gustavo.

The same rule applies to source-derived schema claims. Required fields, enums, security declarations, request/response semantics, and idempotency behavior needed for a safety invariant must be supported by the exact controlling source for that task. Neo must not be left to choose among documentation versions or infer a missing safety field during implementation.

## Same-scope corrections after Marco BLOCK

`same_scope_corrections_after_marco_block` is an explicit capability of the original Gustavo task authorization. Marco `BLOCK` is review direction, not a new authorization. Continuation exists only inside the still-active original Gustavo authorization. Marco may narrow corrective work but cannot broaden capability.

### Bruno predicates

All must be true:

```text
original_authorization_still_active = true
same_scope_corrections_after_marco_block = PERMITTED
objective_unchanged = true
phase_unchanged = true
capability_ceiling_unchanged = true
venue_environment_authority_unchanged = true
permitted_artifact_class_unchanged = true
new_material_risk = false
```

The correction must remain inside the original artifact/capability envelope and address concrete blocking defects. If any predicate is false, unprovable, malformed, unknown, or ambiguous, continuation is prohibited and Bruno returns to Gustavo.

### Neo predicates

All must be true:

```text
original_authorization_still_active = true
same_scope_corrections_after_marco_block = PERMITTED
accepted_specification_unchanged = true
capability_ceiling_unchanged = true
authorized_path_envelope_not_materially_expanded = true
new_venue_environment_access = false
new_credential_capability = false
new_write_trading_funding_capability = false
material_economic_behavior_change = false
new_material_risk = false
```

The correction must be exact conformance/bug-fix work whose correct behavior is already uniquely determined by the accepted specification. If any predicate is false, unprovable, malformed, unknown, or ambiguous, continuation is prohibited and Neo returns to Gustavo.

## Correction lifecycle and termination

Same-scope correction continuation terminates on any of:

- Marco `APPROVE`;
- Marco `DEFER`;
- explicit Gustavo revocation; or
- a material-expansion trigger.

Marco `BLOCK` does not terminate a correction-enabled original authorization when every same-scope predicate passes. `ACCEPT FINDING` and `NEEDS VERIFICATION` do not grant new capability. Verification may occur only if the original authorization already permits the required capability.

## Exact Gustavo-return triggers

Return to Gustavo before further work when any of the following changes, is newly requested, or is ambiguous:

- objective;
- phase;
- accepted specification or its controlling identity;
- capability ceiling;
- authorized paths or material path envelope;
- venue;
- environment, including Demo-to-production transition;
- network capability;
- credential, authentication, signing, private-session, wallet, or account capability;
- production capability, including authenticated production reads;
- write, order, amendment, cancellation, or funding capability;
- trading or execution capability, including paper/live venue execution and shadow-to-write;
- economic behavior, including price, quantity, fee, P&L, hedge, settlement, incentive, exposure, or execution-timing semantics;
- risk-limit or material risk-control semantics;
- new dependency/executable or architectural surface that materially expands capability; or
- ambiguity about whether any of these triggers applies.

Ambiguity fails closed; affected work halts pending Gustavo.

## Risk tiers and proportional minimum evidence

Every task is classified `LOW`, `CONTROLLED`, or `HIGH`. Mixed work takes the highest applicable tier. Risk tier never grants capability. The tier describes evidence and control intensity only. Any required capability must still be explicitly authorized.

### LOW

`LOW` covers offline specification, documentation/governance, offline deterministic code, offline tests, provenance, packaging, and canonical-state work with no venue or credential capability unless separately authorized.

Minimum `LOW` evidence:

1. authorization anchor/task ID;
2. exact canonical repository/base when repository state matters;
3. declared risk tier;
4. exact changed artifact/path list;
5. test result summary if tests were authorized/applicable, otherwise `NOT_APPLICABLE`;
6. `network_activity = NONE` except separately authorized canonical repository synchronization;
7. `credential_activity = NONE`;
8. `venue_activity = NONE`;
9. artifact byte length plus SHA-256, package identity, or Git commit identity as applicable;
10. blockers/deviations; and
11. confirmation that no capability outside the dispatch occurred.

### CONTROLLED

`CONTROLLED` requires explicit Gustavo authorization for the named bounded read-only network capability and may include:

- Kalshi Demo public reads;
- Kalshi Demo authenticated reads;
- bounded read-only network/shadow observation; and
- public unauthenticated production read-only observation.

Production public read-only may be `CONTROLLED` only when no production credential, authenticated session, signature, private account surface, or write surface is required or used. Intending not to write is insufficient if authenticated production or write capability exists.

Minimum `CONTROLLED` evidence is all applicable `LOW` evidence plus:

1. exact Gustavo capability-transition anchor;
2. exact venue/environment classification, including production designation where applicable;
3. endpoint scheme/host/port classification and verification result;
4. exact public/authenticated and read/write classification;
5. for public production reads, proof no production credential/authenticated session/signature is required or used;
6. credential boundary metadata when relevant, never secret values;
7. redaction policy and confirmation no secret/private material is present;
8. exact allowed methods/routes/topics or equivalent observation surfaces;
9. maximum request/message count and data/time envelope;
10. timeout values;
11. retry cap and retryable/non-retryable classification;
12. rate-limit/backoff behavior where applicable;
13. actual request/message counts and response/status summary;
14. explicit zero venue writes, zero orders, zero cancellations, zero funding, and zero venue execution;
15. fail-closed halt events, if any; and
16. evidence identity sufficient to map authorization to observation.

### HIGH

`HIGH` includes at minimum:

- production authenticated reads using production credentials;
- production credential/signing capability;
- any production write/order capability;
- Demo writes/orders;
- funding;
- authenticated write canaries;
- shadow-to-write transitions;
- paper or live venue execution; and
- material risk-limit changes.

A production capability whose public/read-only status cannot be proven is `HIGH`. `HIGH` activity requires explicit Gustavo approval of the material capability and activity-specific authorization.

Minimum `HIGH` evidence is all applicable `CONTROLLED` evidence plus, as applicable:

1. exact activity-specific Gustavo approval anchor;
2. exact account/environment boundary without secret values;
3. exact production credential class/reference and environment-match proof;
4. exact authorized authenticated/read/write surface;
5. maximum action count, quantity, notional/funding amount, inventory/exposure, and time window;
6. pre-action risk-limit verification;
7. idempotency key or equivalent duplicate-prevention evidence where supported;
8. pre-action venue/account truth snapshot;
9. submitted action/request IDs and timestamps as applicable;
10. explicit venue-truth order/fill/cancellation/funding/reconciliation evidence for write/execution work;
11. deterministic accounting of displayed price, executable price, maker/taker status, gross edge, fees, slippage, adverse selection, forced-hedge cost, realized P&L, unrealized P&L, and confirmed incentives where relevant;
12. decimal/fixed-point precision evidence for all economic values;
13. emergency-cancellation/halt behavior and result where execution is possible;
14. post-action account/inventory/exposure truth where applicable;
15. unresolved reconciliation exceptions, each blocking or explicitly accepted by the authorized decision-maker;
16. proof Demo and production state/configuration/credentials remained structurally separated; and
17. immutable evidence identities sufficient for independent Marco review.

Nothing in this evidence schema authorizes `CONTROLLED` or `HIGH` activity.

## No closure recursion

No dedicated closure-of-closure task is required merely to prove that an already-reviewed governance installation occurred. Canonical Git history, the exact Gustavo authorization anchor, Marco review, and the authorized current-state/audit updates are sufficient layers. A later audit correction may be authorized when materially useful, but it is not a prerequisite to the preceding completed action.

## Neo standing read-only repository synchronization

Neo's standing read-only synchronization semantics for canonical `rigolugo/ARB` are preserved without expansion. They permit repository availability operations only: clone, fetch, required ref/commit/tag retrieval, checkout, `pull --ff-only`, and equivalent verified fast-forward-only local update for a separately authorized task.

They do not authorize source/document/test changes, implementation, test execution, project imports, artifact authoring, dependency/package downloads, push, remote branch creation/deletion, pull requests, merges, releases, workflow/settings changes, venue access, credentials, funding, orders, cancellations, or trading.

## Missing-input behavior

When a task cannot proceed, report the exact missing operational input or mismatch, such as `CANONICAL_BASE_MISMATCH`, `CONTROLLING_ARTIFACT_IDENTITY_MISMATCH`, `WRITABLE_PATH_MATRIX_NOT_SPECIFIED`, `REQUIRED_CAPABILITY_NOT_AUTHORIZED`, or `TASK_SCOPE_AMBIGUOUS`. Do not substitute a generic demand for approval paperwork that the active task did not require.

## Scope preservation

This dispatch rule simplifies authorization proof and correction loops. It does not broaden project scope, weaken `GUARDRAILS.md`, or authorize any venue/network/credential/write/funding/trading capability by itself.
