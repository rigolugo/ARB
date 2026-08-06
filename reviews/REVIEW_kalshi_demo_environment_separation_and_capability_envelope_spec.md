APPROVE

Candidate: CANDIDATE_02

# Marco Review — Kalshi Demo Environment Separation and Capability Envelope Specification Candidate 02

**Artifact:** `REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`  
**Reviewer:** Marco  
**Decision:** `APPROVE`  
**Review date:** 2026-08-06  
**Disposition:** Suitable for Gustavo's exact-candidate acceptance decision  
**Implementation authorization created:** No  
**Canonical installation target if implemented:** `reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md`

## 1. Exact reviewed identities

| Artifact | Raw bytes | SHA-256 |
|---|---:|---|
| `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md` | `78876` | `4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2` |
| `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` | `14114` | `a47d623c4a80048909e4e9df8e4c11904ff0e763ab4e242028bd0c81dcedee6d` |

The canonical repository baseline reviewed was:

- repository: `rigolugo/ARB`;
- visibility: public;
- default branch: `main`;
- HEAD: `e35d56dda77819f0066447e18a0a2dc5bac2bb88`;
- current canonical phase: `DOCUMENTATION_BOOTSTRAP_COMPLETE`.

## 2. Predecessor disposition

Candidate 01 remains blocked, noncanonical, uninstalled, and non-authorizing.

Its exact identities were:

| Artifact | Raw bytes | SHA-256 |
|---|---:|---|
| `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md` | `75847` | `b8147c989852350bcd02cbc3cf5f18374f50a12a3a3ca140373dab9885431735` |
| `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_01.md` | `11277` | `948a6986bbb9ea72cf30dfa767957b5ab4b203f153a7cf01fedf0892bfca906d` |

Candidate 02 is a bounded correction and does not retroactively accept, canonicalize, install, or authorize Candidate 01.

## 3. Review result

Candidate 02 resolves the sole Candidate 01 blocker:

1. Section 7.6 now identifies the official Fixed-Point Representation source as:
   `https://docs.kalshi.com/getting_started/fixed_point_migration`.
2. Traceability entry `T-009` binds the same exact source location.
3. The displayed metadata value `Last Updated: August 20, 2026` is recorded explicitly.
4. Because that displayed date is later than the 2026-08-06 review baseline, Candidate 02 treats it as a metadata anomaly or announced/future material rather than proof that future behavior was already effective.
5. Later implementation is required to revalidate the then-current official source before adoption.

No unrequested redesign was found.

## 4. Accepted normative direction

The exact Candidate 02 specification adequately defines:

- explicit non-Boolean environment selection;
- no Demo or production default;
- deterministic production rejection;
- exact recommended Demo REST and WebSocket endpoint allowlists;
- rejection of production, compatibility, legacy, custom, deceptive, and redirected endpoints;
- parsed URL-component comparison rather than substring matching;
- structural separation of public REST read, authenticated read, Demo write, and production capabilities;
- classification of every WebSocket surface as authenticated-read or stronger;
- complete task capability envelopes with no omitted or inherited fields;
- intersection of requested capability, constructible capability, and exact task authorization;
- separate Demo and production credential namespaces;
- non-secret validation before credential-file access, private-key parsing, signing, transport construction, sockets, redirects, or requests;
- one immutable non-secret validated Demo profile;
- typed halts with deterministic precedence;
- secret-exposure emergency override;
- secret-safe logging, rendering, serialization, and error handling;
- zero-network configuration validation;
- exact decimal or fixed-point arithmetic for economic values;
- preservation of Kalshi-native semantics within the venue adapter;
- explicit future environment identity in persistent records;
- no title-based cross-venue equivalence;
- no claim that concurrent submissions are atomic;
- deferred idempotency, reconciliation, restart recovery, execution, and profitability controls.

## 5. Deferred decisions

These matters remain unresolved but do not block acceptance of this static specification:

1. implementation language, runtime, package manager, and exact repository paths;
2. whether the first implementation exposes only the pure validator/profile types or also inaccessible future factory interfaces;
3. resolution of the public order-book authentication presentation against a retrieved and hashed current OpenAPI security declaration before connectivity work;
4. safe credential-path rendering policy;
5. exact OpenAPI and AsyncAPI retrieval, hashing, retention, and comparison procedure;
6. final public names for Demo credential references;
7. deterministic capability-envelope serialization and identity.

The affected items must be resolved in a later, separately authorized implementation handoff before source changes.

## 6. Meaning of this decision

`APPROVE` means the exact Candidate 02 artifacts identified in Section 1 were suitable for Gustavo's acceptance decision.

This review does not itself authorize:

- canonical installation;
- repository modification;
- branch creation;
- commits or pushes;
- implementation source;
- test source or test execution;
- package installation;
- credential creation, loading, parsing, or use;
- Kalshi Demo access;
- Kalshi production access;
- Polymarket access;
- funding;
- orders, amendments, cancellations, paper trading, or live trading;
- Neo activity;
- any later project phase.

Gustavo subsequently accepted the exact Candidate 02 specification and Bruno handoff identities. A separate bounded canonical-installation authorization and implementation dispatch remain required.

## 7. Canonical-record purpose

If canonical installation is separately authorized, this exact file is copied byte-for-byte to:

`reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md`

Any byte change requires a newly frozen external review identity before installation.
