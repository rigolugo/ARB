# PROJECT_STATE

Authority level: canonical current-state snapshot. This document does not authorize work and does not create authorization on its own.

## 1. Repository identity and baseline commit

- Repository: `rigolugo/ARB`
- Visibility: public
- Default branch: `main`
- Accepted bootstrap implementation commit: `e136be0b80f0370572e889d1075a11fc1b445348`
- Accepted Kalshi Demo environment-separation (Candidate 02) canonical documentation implementation commit: `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`
- Current canonical `main`: must be reverified directly from the repository before reliance or further work; this record does not predeclare the SHA of its own installation commit.

## 2. Current phase

`KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ACCEPTED_AND_INSTALLED`

The prior phase, `DOCUMENTATION_BOOTSTRAP_COMPLETE`, remains true of the repository-bootstrap workstream. The Kalshi Demo environment-separation and capability-envelope specification (Candidate 02) documentation-only canonical installation was reviewed by Marco, approved for the remote installation commit, and explicitly accepted by Gustavo at exact commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`. That installation lifecycle is `ACCEPTED_AND_CLOSURE_AUTHORIZED`; see `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0017` and `project_context/DECISION_LOG.md` entry `DEC-0023`.

## 3. Current authorization state

- Candidate 10 implementation: `ACCEPTED`
- Gustavo acceptance is complete.
- Implementation authorization `GUSTAVO_CANDIDATE_10_REPOSITORY_BOOTSTRAP_IMPLEMENTATION_01` is completed and no longer active. See `project_context/AUTHORIZATION_LOG.md`.
- Active technical implementation authorization: none.

The completed bootstrap implementation authorization is distinct from the Candidate 10 specification-drafting authorization and from Candidate 10 specification acceptance.

## 4. Completed and accepted work

- Candidate 10 documentation-only repository bootstrap specification and Bruno handoff: accepted.
- Marco's Candidate 10 approval review: `APPROVE`.
- Marco's Candidate 10 implementation handoff: issued.
- This documentation bootstrap implementation: performed under the above authorization.
- Gustavo accepted the installed Candidate 10 repository-bootstrap implementation at the accepted implementation commit `e136be0b80f0370572e889d1075a11fc1b445348`.
- Kalshi Demo environment-separation and capability-envelope specification Candidate 01: blocked, noncanonical, uninstalled, non-authorizing.
- Kalshi Demo environment-separation and capability-envelope specification Candidate 02 and Bruno handoff: accepted by Gustavo.
  - `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`, 78876 bytes, sha256 `4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2`
  - `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`, 14114 bytes, sha256 `a47d623c4a80048909e4e9df8e4c11904ff0e763ab4e242028bd0c81dcedee6d`
- Marco's Candidate 02 approval review: `APPROVE`.
  - `REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`, 6213 bytes, sha256 `6d665601c5eb0b35943e0a782a34141f45b13b9f3440c3052c85171d54fe3c9b`
- Marco's Candidate 02 canonical-installation implementation handoff: issued.
  - `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation_CANDIDATE_02.md`, 18572 bytes, sha256 `19ec68c938d2d72dfa769dfc4c40e638d1e5f97f2590abf4928a73b2ba720982`
- This documentation-only canonical installation was performed under authorization `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`; it consumes no venue or credential capability.
- Marco approved the remote installation commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`.
- Gustavo explicitly accepted the installed Candidate 02 canonical documentation implementation at exact commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`. The Candidate 02 documentation-installation lifecycle is accepted and closed.
- Active technical implementation authorization for the Kalshi Demo environment-separation specification: none.
- No source code or tests exist for this specification.
- No Kalshi Demo or production request occurred.
- No Polymarket request occurred.
- No credentials were used.
- No orders, cancellations, funding, paper trading, or live trading occurred.

## 5. Open work

None recorded by this bootstrap implementation. Later phases require their own bounded specification, review, and authorization.

## 6. Blocked work

None recorded by this bootstrap implementation.

## 7. Deferred work

None recorded by this bootstrap implementation.

## 8. Unresolved assumptions

### Repository bootstrap

None unresolved. See `specifications/SPEC_repository_bootstrap.md` Section 31.1 for the specification's stated assumptions; the documentation-only bootstrap implementation recorded no unresolved assumptions of its own.

### Kalshi Demo environment separation (Candidate 02) — unresolved implementation decisions

These do not invalidate the accepted static Candidate 02 specification. They block only the affected technical implementation work until resolved in a separate, later Marco implementation handoff. See accepted Candidate 02 specification, Section 29 (`Unresolved questions requiring Marco's decision`) for the complete list, including at minimum:

- implementation language, runtime, package manager, and exact repository paths;
- whether the first constructed capability surface exposes only the pure validator/profile types or also inaccessible future factory interfaces;
- resolution of the public order-book authentication-source conflict against a retrieved and hashed current OpenAPI security declaration;
- safe credential-path rendering policy;
- exact OpenAPI and AsyncAPI retrieval, hashing, retention, and comparison procedure;
- revalidation of future-dated official material (e.g., the fixed-point source's displayed `Last Updated: August 20, 2026` metadata) before adoption;
- final public names for Demo credential references;
- deterministic capability-envelope serialization and identity method.

No technical implementation is authorized until these are resolved and a separate bounded implementation dispatch is issued.

## 9. Active accepted specifications

### Repository bootstrap

- Candidate ID: `CANDIDATE_10`
- Source filename: `SPEC_repository_bootstrap_CANDIDATE_10.md`
- Raw bytes: `122041`
- SHA-256: `6cff9ca01e0d3779d95ecea241ed83e1b47126117b1660e2066862b823f02b71`
- Canonical target: `specifications/SPEC_repository_bootstrap.md`
- Status: accepted by Gustavo; documentation-only bootstrap implementation accepted at commit `e136be0b80f0370572e889d1075a11fc1b445348`.

### Kalshi Demo environment separation

- Candidate ID: `CANDIDATE_02`
- Source filename: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`
- Raw bytes: `78876`
- SHA-256: `4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2`
- Canonical target: `specifications/SPEC_kalshi_demo_environment_separation_and_capability_envelope.md`
- Status: accepted by Gustavo and canonically installed at commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`, following Marco's approval of that remote installation commit and Gustavo's explicit acceptance of the installed implementation. The Candidate 02 documentation-installation lifecycle is accepted and closed. Candidate 02 was not superseded by, and does not supersede, Candidate 10; the two are independent accepted specifications. This acceptance and installation do not authorize technical implementation.

## 10. Latest accepted implementation

Two independent accepted implementations exist in this repository:

1. The repository-bootstrap documentation implementation, installed on branch `candidate-10-repository-bootstrap` from base `da629e93ce9255c28ecb485ee2b67bfc0c0ccb86`. Gustavo accepted this implementation at accepted implementation commit `e136be0b80f0370572e889d1075a11fc1b445348`.
2. The Kalshi Demo environment-separation and capability-envelope specification (Candidate 02) canonical documentation installation, prepared across bounded correction packages from base `e35d56dda77819f0066447e18a0a2dc5bac2bb88`, transferred to `main` via the manual browser temporary-branch workflow, reviewed and approved by Marco, and explicitly accepted by Gustavo at accepted implementation commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`.

Current canonical `main` must be reverified directly from the repository before reliance or further work.

## 11. Latest verified test evidence

None. No tests are authorized or performed by this documentation-only bootstrap.

## 12. Environment authorization matrix

| Environment | Reads | Writes |
|---|---|---|
| Kalshi Demo | `PROHIBITED` | `PROHIBITED` |
| Kalshi production | `PROHIBITED` | `PROHIBITED` |
| Polymarket | `PROHIBITED` | `PROHIBITED` |

No venue, credential, funding, order, cancellation, or trading capability is authorized at this phase.

## 13. Explicit next user decision

The Kalshi Demo environment-separation and capability-envelope specification Candidate 02 and Bruno's handoff are accepted and canonically installed as governance/specification records only. Unresolved implementation decisions remain those listed in the accepted Candidate 02 specification, Section 29 (`Unresolved questions requiring Marco's decision`). The next user decision is whether Gustavo authorizes a separately bounded technical implementation dispatch after Marco resolves the required implementation-handoff details recorded there. No such technical implementation authorization currently exists. This canonical installation does not itself authorize that or any other next phase; any further phase requires its own separate bounded specification, review, and authorization. No next phase begins automatically.

## 14. Last updated and approving authority

Updated by Neo under authorization `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_INSTALLATION_ACCEPTANCE_CLOSURE_PACKAGE_01`, recording the completed lifecycle of the Kalshi Demo environment-separation and capability-envelope specification Candidate 02 canonical documentation installation: Bruno's accepted specification and handoff, Marco's approval review, Marco's canonical-installation implementation handoff, Marco's approval of the remote installation commit, and Gustavo's explicit acceptance of the installed implementation at commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`. This closure record does not itself authorize technical implementation, tests, venue access, credentials, funding, orders, cancellations, or trading.

## 15. Staleness check

This snapshot reflects repository state as of commit-time on branch `neo-c02-installation-acceptance-closure-01` from accepted canonical base `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`. Current canonical `main` must be reverified directly from the repository before reliance or further work. This record does not predeclare the SHA of its own closure-package installation commit.
