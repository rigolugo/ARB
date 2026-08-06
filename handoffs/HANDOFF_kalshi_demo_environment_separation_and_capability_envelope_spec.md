# Bruno Handoff — Kalshi Demo Environment Separation and Capability Envelope Specification Candidate 02

**Artifact:** `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`  
**Candidate identity:** `HANDOFF_KALSHI_DEMO_ENVIRONMENT_SEPARATION_AND_CAPABILITY_ENVELOPE_SPEC_CANDIDATE_02`  
**Candidate:** `CANDIDATE_02`  
**From:** Bruno  
**To:** Marco  
**Authorization ID:** `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01`  
**Task classification:** `DOCUMENTATION_GOVERNANCE_AND_SPEC_ONLY_BOUNDED_CORRECTION`  
**Date:** 2026-08-06  
**Lifecycle:** `SUBMITTED_FOR_MARCO_REVIEW`  
**Canonical effect:** none  
**Neo authorization:** none  
**Installation authorization:** none

---

## 1. Deliverables

Bruno produced exactly these two external Markdown candidates:

1. `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`
2. `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`

No ZIP, sidecar, repository file, branch, commit, pull request, code, test, venue artifact, or additional deliverable was created.

---

## 2. Exact specification identity

| Artifact | Raw byte length | SHA-256 |
|---|---:|---|
| `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md` | `78876` | `4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2` |

Marco must independently recompute the identity before review. Any byte mismatch requires a new candidate; the candidate shall not be edited in place after identity binding.

This handoff does not embed its own final hash, avoiding circular self-identity. Its exact external identity is reported with delivery.

### 2.1 Exact blocked Candidate 01 predecessor identities

| Blocked predecessor artifact | Raw byte length | SHA-256 |
|---|---:|---|
| `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md` | `75847` | `b8147c989852350bcd02cbc3cf5f18374f50a12a3a3ca140373dab9885431735` |
| `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_01.md` | `11277` | `948a6986bbb9ea72cf30dfa767957b5ab4b203f153a7cf01fedf0892bfca906d` |

Both identities matched exactly before Candidate 02 drafting. Candidate 01 remains blocked, noncanonical, non-authorizing, and uninstalled.

### 2.2 Bounded correction audit

Candidate 02 changes only:

1. candidate identity, artifact identifiers, filenames, revision, authorization ID, lifecycle references, and predecessor/correction descriptions mechanically required for Candidate 02;
2. specification Section 7.6 official source URL, from `https://docs.kalshi.com/getting_started/fixed_point` to `https://docs.kalshi.com/getting_started/fixed_point_migration`;
3. traceability entry `T-009`, which now binds the exact corrected source location;
4. the fixed-point metadata statement, which now records `Last Updated: August 20, 2026`, compares it with Candidate 02’s 2026-08-06 review baseline, and preserves the restrictive future-material treatment;
5. the corresponding unresolved-question and handoff traceability language needed to report that correction accurately; and
6. Candidate 02’s exact authorization and read-order boundaries.

All unrelated normative decisions are semantically preserved from blocked Candidate 01. No environment, endpoint, credential, capability, validation, halt, acceptance-test, deferred-control, blocker, or Neo-handoff design was redesigned.

---

## 3. Canonical repository verification

| Attribute | Verified value |
|---|---|
| Repository | `rigolugo/ARB` |
| Visibility | public |
| Default branch | `main` |
| Exact canonical `main` read | `e35d56dda77819f0066447e18a0a2dc5bac2bb88` |
| Accepted bootstrap implementation commit | `e136be0b80f0370572e889d1075a11fc1b445348` |
| Current canonical phase | `DOCUMENTATION_BOOTSTRAP_COMPLETE` |

The required baseline matched. No `LOCKED — CANONICAL BASELINE MISMATCH` condition occurred.

---

## 4. Canonical read-order completion

Bruno completed the required read order at exact commit `e35d56dda77819f0066447e18a0a2dc5bac2bb88`:

1. root `START_HERE.md`;
2. `project_context/START_HERE.md`;
3. `project_context/GUARDRAILS.md`;
4. `project_context/PROJECT_STATE.md`;
5. `project_context/AUTHORIZATION_LOG.md`;
6. `project_context/DECISION_LOG.md`;
7. `project_context/AGENT_ROLES.md`;
8. the accepted-candidate identity table in the canonical authorization chain;
9. `specifications/SPEC_repository_bootstrap.md`;
10. `reviews/REVIEW_repository_bootstrap_spec.md`;
11. `handoffs/HANDOFF_repository_bootstrap_spec.md`;
12. `handoffs/HANDOFF_repository_bootstrap_implementation.md`;
13. relevant `project_context/ARTIFACT_INDEX.md` entries;
14. exact blocked `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md`;
15. exact blocked `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_01.md`;
16. authorization `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01` and Marco’s Candidate 01 blocking decision;
17. current official `Fixed-Point Representation` page at `https://docs.kalshi.com/getting_started/fixed_point_migration`.

Acceptance-closure facts referenced by the canonical records were also followed without modification.

The canonical records confirm that Candidate 10 bootstrap work is complete, no technical implementation authorization is active, and the current Gustavo dispatch is a separate bounded specification authorization.

---

## 5. Official fixed-point source correction verified

Candidate 02 performed only the authorized official-source verification needed for the bounded correction:

- official title: `Fixed-Point Representation`;
- corrected official location: `https://docs.kalshi.com/getting_started/fixed_point_migration`;
- displayed metadata: `Last Updated: August 20, 2026`;
- Candidate 02 review baseline: `2026-08-06`.

Because August 20, 2026 is later than the 2026-08-06 baseline, Candidate 02 treats the displayed date as a metadata anomaly or announced/future material. It is not proof that future behavior was already effective. A later implementation must revalidate the current official source before adoption.

All other official-source conclusions, including the public-orderbook authentication conflict and OpenAPI/AsyncAPI version-binding limitation, are preserved semantically from the exact blocked Candidate 01 bytes and were not resolved or redesigned.

No venue API was called.

---

## 6. Normative decisions summarized

1. Environment is a closed explicit enum; there is no Boolean model and no default.
2. Only `KALSHI_DEMO` may validate in the first implementation; production is modeled only for deterministic rejection.
3. Only the recommended Demo REST and WebSocket endpoint tuples are allowlisted.
4. Compatibility, shared, legacy, production, custom, deceptive, and redirected endpoints fail closed.
5. Endpoint comparison uses parsed canonical components, never substring matching or DNS inference.
6. Public REST read, authenticated read, Demo write, and production capability are structurally separate.
7. Every WebSocket connection is classified as authenticated-read or stronger.
8. Production readers and writers are unconstructible in the first implementation.
9. Demo writers are unconstructible when the exact task prohibits Demo writes.
10. The task capability envelope is complete and explicit; omitted or inherited fields halt.
11. Effective capability is the intersection of requested capability, constructed surface, and exact task authorization; the more restrictive value controls.
12. Demo and production credential namespaces are distinct; generic variables are rejected.
13. Non-secret validation completes before credential-file access, private-key parsing, signing, transport construction, redirects, sockets, or requests.
14. Successful validation yields one immutable non-secret Demo profile, not a client or request authorization.
15. Failure yields one typed halt and no partial profile, client, transport, credential object, signer, or cache.
16. Secret values never enter logs, errors, representations, serialization, snapshots, manifests, or artifacts.
17. Decimal or fixed-point arithmetic is mandatory for economic values.
18. Venue-native data, lifecycle, directions, and provenance remain in a Kalshi adapter.
19. Cross-venue equivalence, atomic execution, reconciliation, ledgers, and profitability are deferred and unauthorized.
20. No phase begins automatically.

---

## 7. Unresolved questions

The specification records these Marco decisions as unresolved:

1. implementation language, package/runtime selection, and exact repository paths;
2. whether the first implementation contains only the pure validator/profile types or also inaccessible future factory interfaces;
3. resolution of the public order-book authentication presentation against a retrieved and hashed current OpenAPI security declaration before connectivity work;
4. whether safe errors may reveal credential basenames or only field-name/presence state;
5. exact retrieval, hashing, and retention procedure for current OpenAPI and AsyncAPI files in later schema work;
6. revalidation before adoption of the current fixed-point source at `https://docs.kalshi.com/getting_started/fixed_point_migration`, whose page displayed `Last Updated: August 20, 2026` after Candidate 02’s 2026-08-06 review baseline, together with the preserved future-dated changelog treatment;
7. final public names for Demo credential references;
8. deterministic capability-envelope serialization and identity method.

These do not block Candidate 02 review. Items 1, 3, 4, and 5 block the affected later implementation handoff until Marco resolves them.

---

## 8. Blocking conditions

### Candidate completion

No blocker prevented Candidate 02 completion.

### Later implementation

Implementation is blocked until all applicable conditions are satisfied, including:

- exact Candidate 02 identity is independently reviewed and accepted;
- a separate Gustavo implementation authorization exists;
- Marco allocates exact repository paths and commands;
- canonical base is reverified;
- then-current recommended Demo endpoints remain consistent;
- schema-dependent work binds current OpenAPI/AsyncAPI identities;
- material official-source conflicts are resolved;
- no guardrail amendment, production access, credential use, network access, or Demo write is inferred;
- public/authenticated/write/production surfaces can be separated structurally;
- secret-safe third-party error handling can be guaranteed.

---

## 9. Complete Candidate-authoring capability matrix

| Capability | Status |
|---|---|
| Network access for read-only canonical repository access, exact Candidate 01 artifacts, and bounded verification of the current official fixed-point page | `PERMITTED` |
| Kalshi Demo public market-data reads | `PROHIBITED` |
| Kalshi Demo authenticated reads | `PROHIBITED` |
| Kalshi Demo writes | `PROHIBITED` |
| Kalshi production public reads | `PROHIBITED` |
| Kalshi production authenticated reads | `PROHIBITED` |
| Kalshi production writes | `PROHIBITED` |
| Polymarket reads | `PROHIBITED` |
| Polymarket writes | `PROHIBITED` |
| Credential use | `PROHIBITED` |
| Private-key loading or parsing | `PROHIBITED` |
| Credential-file reads | `PROHIBITED` |
| Credential creation or derivation | `PROHIBITED` |
| Account creation | `PROHIBITED` |
| Account funding | `PROHIBITED` |
| Balance or portfolio access | `PROHIBITED` |
| Order submission | `PROHIBITED` |
| Order amendment | `PROHIBITED` |
| Order cancellation | `PROHIBITED` |
| Paper trading | `PROHIBITED` |
| Live trading | `PROHIBITED` |
| Code changes | `PROHIBITED` |
| Implementation-source authoring | `PROHIBITED` |
| Test-source authoring | `PROHIBITED` |
| Test execution | `PROHIBITED` |
| Project imports | `PROHIBITED` |
| Package installation | `PROHIBITED` |
| Shell or subprocess execution | `PROHIBITED` |
| Local research-data access | `PROHIBITED` |
| Empirical execution | `PROHIBITED` |
| Repository path changes | `PROHIBITED` |
| Branches | `PROHIBITED` |
| Repository commits | `PROHIBITED` |
| Pull requests | `PROHIBITED` |
| Canonical installation | `PROHIBITED` |
| Artifact generation | `PERMITTED` only for the two named Markdown candidates and identity reporting |

Anything not explicitly permitted is prohibited.

---

## 10. Negative evidence and confirmations

Bruno confirms:

- no code was authored;
- no tests were authored;
- no tests were executed;
- no project import occurred;
- no package was installed;
- no shell or subprocess was executed;
- no repository file was created, modified, deleted, staged, or committed;
- no branch, commit, pull request, issue, release, or tag was created;
- no canonical installation occurred;
- no venue API was called;
- no Kalshi Demo market-data or authenticated request occurred;
- no Kalshi production request occurred;
- no Polymarket request occurred;
- no credentials, private keys, credential files, balances, portfolios, or positions were read or used;
- no account was created or funded;
- no order was submitted, amended, or cancelled;
- no paper trading or live trading occurred;
- no profitability claim was made;
- no external repository source was copied, executed, installed, or imported;
- no next phase was authorized.

---

## 11. Review request and effect

Requested Marco decision: `APPROVE`

This is a request for independent review, not Bruno approval.

Candidate 02 preserves all unrelated Candidate 01 normative content semantically and introduces no unrequested redesign.

The candidate has no canonical effect. Marco review does not itself authorize implementation. Gustavo remains the sole approval authority. Neo is not authorized. Installation is not authorized. No later phase begins automatically.

---

## 12. Completion

The exact specification identified in Section 2 and this paired handoff are delivered with lifecycle:

`SUBMITTED_FOR_MARCO_REVIEW`

Stop after delivery and external identity reporting.
