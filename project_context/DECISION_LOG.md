# DECISION_LOG

Append-only record of project decisions. Decisions do not grant capabilities unless separately authorized in `AUTHORIZATION_LOG.md`. Historical entries are not rewritten; corrections and supersessions use new entries.

Entry schema: Decision ID, Candidate ID (if applicable), Bound artifact identities (if acceptance-related), Date, Decision, Status, Rationale, Evidence/reviewed artifact, Scope affected, Superseded decisions, User approval reference, Authorizes further work (`YES`/`NO`).

---

### DEC-0001
- Candidate ID: n/a
- Date: 2026-08-05
- Decision: Gustavo is the sole approval authority for this project.
- Status: `ACCEPTED`
- Rationale: Foundational governance decision.
- Evidence: Project operating contract.
- Scope affected: entire project.
- Superseded decisions: none.
- User approval reference: project operating contract.
- Authorizes further work: `NO`

### DEC-0002
- Date: 2026-08-05
- Decision: Marco is orchestrator and independent reviewer; Bruno is specification author; Neo is implementation/test agent only when separately authorized.
- Status: `ACCEPTED`
- Rationale: Role separation for safety and auditability.
- Evidence: Project operating contract; `AGENT_ROLES.md`.
- Scope affected: entire project.
- Superseded decisions: none.
- User approval reference: project operating contract.
- Authorizes further work: `NO`

### DEC-0003
- Date: 2026-08-05
- Decision: Development is incremental and phase gated; no phase begins automatically when the previous one completes.
- Status: `ACCEPTED`
- Rationale: Fail-closed, evidence-gated progression.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 26.
- Scope affected: entire project.
- Superseded decisions: none.
- User approval reference: project operating contract.
- Authorizes further work: `NO`

### DEC-0004
- Date: 2026-08-05
- Decision: Kalshi-first sequencing; venue-independent economic core plus separate venue adapters.
- Status: `ACCEPTED`
- Rationale: Kalshi offers a Demo environment suitable for controlled, mock-funded execution work.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 5.2.
- Scope affected: future venue-adapter work.
- Superseded decisions: none.
- User approval reference: project operating contract.
- Authorizes further work: `NO`

### DEC-0005
- Date: 2026-08-05
- Decision: No-live-trading default; Demo evidence is not production evidence.
- Status: `ACCEPTED`
- Rationale: Safety default pending explicit future authorization.
- Evidence: `project_context/GUARDRAILS.md` Sections 3-4.
- Scope affected: entire project.
- Superseded decisions: none.
- User approval reference: project operating contract.
- Authorizes further work: `NO`

### DEC-0006
- Date: 2026-08-05
- Decision: Absent authorization means prohibited.
- Status: `ACCEPTED`
- Rationale: Fail-closed authorization model.
- Evidence: `project_context/GUARDRAILS.md` Section 2.
- Scope affected: entire project.
- Superseded decisions: none.
- User approval reference: project operating contract.
- Authorizes further work: `NO`

### DEC-0007
- Date: 2026-08-05
- Decision: Marco is the sole allocator of candidate identifiers for the repository-bootstrap specification workstream. Candidate numbers are sequential, immutable, non-reusable, and skippable only by an explicit Marco record naming the number and reason. The specification and Bruno handoff share the same candidate number.
- Status: `ACCEPTED`
- Rationale: Deterministic candidate lifecycle and auditability.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 1.2.
- Scope affected: repository-bootstrap specification workstream.
- Superseded decisions: none.
- User approval reference: project operating contract.
- Authorizes further work: `NO`

### DEC-0008
- Candidate ID: `CANDIDATE_04`
- Date: 2026-08-05
- Decision: Candidate 04 is recorded as a submission/provenance event without a separately recorded explicit Gustavo authorization.
- Status: `RECORDED`
- Rationale: Preserve accurate historical lineage.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 2.2.
- Scope affected: candidate lineage record.
- Superseded decisions: none.
- User approval reference: none (provenance fact, not an authorization).
- Authorizes further work: `NO`

### DEC-0009
- Candidate ID: `CANDIDATE_05`
- Date: 2026-08-05
- Decision: Candidate 05 was submitted without a separately recorded explicit Gustavo authorization and remains blocked.
- Status: `BLOCKED`
- Rationale: Preserve accurate historical lineage; Candidate 05 is not represented as authorized.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 2.2.
- Scope affected: candidate lineage record.
- Superseded decisions: none.
- User approval reference: none.
- Authorizes further work: `NO`

### DEC-0010
- Candidate ID: `CANDIDATE_06`
- Date: 2026-08-05
- Decision: Candidate 06 was separately and validly authorized but remains blocked.
- Status: `BLOCKED`
- Rationale: Preserve accurate historical lineage.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 19.8 item 4.
- Scope affected: candidate lineage record.
- Superseded decisions: none.
- User approval reference: Candidate 06 correction authorization (historical).
- Authorizes further work: `NO`

### DEC-0011
- Candidate ID: `CANDIDATE_07`
- Date: 2026-08-05
- Decision: Candidate 07 was submitted without a separately recorded explicit Gustavo authorization and remains blocked.
- Status: `BLOCKED`
- Rationale: Preserve accurate historical lineage.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 19.8 item 5.
- Scope affected: candidate lineage record.
- Superseded decisions: none.
- User approval reference: none.
- Authorizes further work: `NO`

### DEC-0012
- Candidate ID: `CANDIDATE_08`
- Date: 2026-08-05
- Decision: Candidate 08 was separately and validly authorized but remains blocked.
- Status: `BLOCKED`
- Rationale: Preserve accurate historical lineage.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 19.8 item 6.
- Scope affected: candidate lineage record.
- Superseded decisions: none.
- User approval reference: Candidate 08 correction authorization (historical).
- Authorizes further work: `NO`

### DEC-0013
- Candidate ID: `CANDIDATE_09`
- Date: 2026-08-05
- Decision: Candidate 09 was separately and validly authorized but remains blocked. Candidate 09 is Candidate 10's immediate blocked predecessor.
- Status: `BLOCKED`
- Rationale: Preserve accurate historical lineage.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 19.8 item 7.
- Scope affected: candidate lineage record.
- Superseded decisions: none.
- User approval reference: Candidate 09 correction authorization (historical).
- Authorizes further work: `NO`

### DEC-0014
- Candidate ID: `CANDIDATE_10`
- Date: 2026-08-05
- Decision: Candidate 10 correction authorization is a distinct event and does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09.
- Status: `ACCEPTED`
- Rationale: Prevent authorization inheritance across candidate identifiers.
- Evidence: `specifications/SPEC_repository_bootstrap.md` Section 2.2, Section 12.
- Scope affected: candidate lineage record.
- Superseded decisions: none.
- User approval reference: Candidate 10 correction authorization.
- Authorizes further work: `NO`

### DEC-0015
- Candidate ID: `CANDIDATE_10`
- Bound artifact identities: `SPEC_repository_bootstrap_CANDIDATE_10.md` (122041 bytes, sha256 6cff9ca01e0d3779d95ecea241ed83e1b47126117b1660e2066862b823f02b71); `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md` (17497 bytes, sha256 be3dccbb16b270edb67297baf40bcf3944edeaa4877a30e13e1eecdbca823c7e)
- Date: 2026-08-06
- Decision: Marco reviewed Candidate 10 and issued decision `APPROVE`, meaning the exact candidate is suitable for Gustavo's acceptance decision. This review does not itself authorize implementation.
- Status: `ACCEPTED`
- Rationale: Independent review gate.
- Evidence: `reviews/REVIEW_repository_bootstrap_spec.md`.
- Scope affected: Candidate 10 lifecycle.
- Superseded decisions: none.
- User approval reference: n/a (Marco review, not Gustavo decision).
- Authorizes further work: `NO`

### DEC-0016
- Candidate ID: `CANDIDATE_10`
- Date: 2026-08-06
- Decision: Gustavo authorized bounded documentation-bootstrap implementation under authorization ID `GUSTAVO_CANDIDATE_10_REPOSITORY_BOOTSTRAP_IMPLEMENTATION_01`, naming Neo as the authorized implementation agent.
- Status: `ACCEPTED`
- Rationale: Separate implementation authorization event, distinct from candidate acceptance.
- Evidence: Gustavo-posted implementation-dispatch prompt in Neo's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0010`.
- Scope affected: this documentation bootstrap implementation.
- Superseded decisions: none.
- User approval reference: `GUSTAVO_CANDIDATE_10_REPOSITORY_BOOTSTRAP_IMPLEMENTATION_01`.
- Authorizes further work: `YES` (bounded to this exact implementation task only).

### DEC-0017
- Date: 2026-08-06
- Decision: This documentation bootstrap was implemented on temporary branch `candidate-10-repository-bootstrap` from base `da629e93ce9255c28ecb485ee2b67bfc0c0ccb86`, installing the four canonical task records and supporting governance/entry documents. `main` was not modified.
- Status: `IMPLEMENTED_PENDING_MARCO_REVIEW`
- Rationale: Bounded implementation execution record.
- Evidence: this commit; `project_context/PROJECT_STATE.md`.
- Scope affected: this documentation bootstrap.
- Superseded decisions: none.
- User approval reference: `GUSTAVO_CANDIDATE_10_REPOSITORY_BOOTSTRAP_IMPLEMENTATION_01`.
- Authorizes further work: `NO` (Marco review and Gustavo acceptance remain separate, later events).

### DEC-0018
- Candidate ID: `CANDIDATE_10`
- Accepted implementation commit: `e136be0b80f0370572e889d1075a11fc1b445348`
- Date: 2026-08-06
- Decision: Gustavo accepted the installed Candidate 10 repository-bootstrap implementation at canonical `main` commit `e136be0b80f0370572e889d1075a11fc1b445348`.
- Status: `ACCEPTED`
- Rationale: Explicit Gustavo acceptance closes the Candidate 10 documentation-bootstrap implementation lifecycle.
- Evidence: Gustavo's exact acceptance statement issued in Marco's current project chat; canonical `main` accepted implementation commit `e136be0b80f0370572e889d1075a11fc1b445348`.
- Scope affected: repository-bootstrap implementation lifecycle.
- Superseded decisions: none.
- User approval reference: Gustavo's exact acceptance statement: "I accept the installed Candidate 10 repository-bootstrap implementation at canonical main commit e136be0b80f0370572e889d1075a11fc1b445348."
- Authorizes further work: `NO`

### DEC-0019
- Candidate ID: `CANDIDATE_01` (Kalshi Demo environment separation)
- Date: 2026-08-06
- Decision: Marco reviewed the Kalshi Demo environment-separation and capability-envelope specification Candidate 01 and issued decision `BLOCK`.
- Status: `BLOCKED`
- Rationale: Independent review gate; the official Fixed-Point Representation source citation was unresolved.
- Evidence: Candidate 02 Marco review, Section 2 (predecessor disposition).
- Scope affected: Kalshi Demo environment-separation specification candidate lineage.
- Superseded decisions: none.
- User approval reference: n/a (Marco review, not Gustavo decision).
- Authorizes further work: `NO`

### DEC-0020
- Candidate ID: `CANDIDATE_02` (Kalshi Demo environment separation)
- Bound artifact identities: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md` (78876 bytes, sha256 4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2); `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` (14114 bytes, sha256 a47d623c4a80048909e4e9df8e4c11904ff0e763ab4e242028bd0c81dcedee6d)
- Date: 2026-08-06
- Decision: Marco reviewed Candidate 02 and issued decision `APPROVE`, meaning the exact candidate is suitable for Gustavo's acceptance decision. This review does not itself authorize implementation.
- Status: `ACCEPTED`
- Rationale: Independent review gate; Candidate 02 resolves the sole Candidate 01 blocker.
- Evidence: `reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md`.
- Scope affected: Kalshi Demo environment-separation specification candidate lineage.
- Superseded decisions: none.
- User approval reference: n/a (Marco review, not Gustavo decision).
- Authorizes further work: `NO`

### DEC-0021
- Candidate ID: `CANDIDATE_02` (Kalshi Demo environment separation)
- Bound artifact identities: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md` (78876 bytes, sha256 4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2); `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` (14114 bytes, sha256 a47d623c4a80048909e4e9df8e4c11904ff0e763ab4e242028bd0c81dcedee6d)
- Date: 2026-08-06
- Decision: Gustavo accepted the exact Candidate 02 specification and Bruno handoff identities. Candidate 01 remains blocked and non-authorizing.
- Status: `ACCEPTED`
- Rationale: Explicit Gustavo acceptance of the reviewed correction candidate.
- Evidence: Gustavo-posted Neo canonical-installation dispatch, "Gustavo acceptance binding" section.
- Scope affected: Kalshi Demo environment-separation specification lifecycle.
- Superseded decisions: none.
- User approval reference: Gustavo's exact Candidate 02 acceptance statement referenced in the canonical-installation dispatch.
- Authorizes further work: `NO` (acceptance alone does not authorize installation or implementation).

### DEC-0022
- Candidate ID: `CANDIDATE_02` (Kalshi Demo environment separation)
- Date: 2026-08-06
- Decision: Gustavo separately authorized a bounded documentation-only canonical-installation package under authorization ID `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`, naming Neo as the authorized implementation agent, under repository-transfer mode `MANUAL_BROWSER_TEMPORARY_BRANCH`. This is a bounded documentation-only canonical-installation authorization; it is not Candidate acceptance and it is not technical implementation authorization.
- Status: `ACCEPTED`
- Rationale: Separate installation authorization event, distinct from candidate acceptance; does not authorize technical implementation, tests, venue access, credentials, funding, orders, cancellations, or trading.
- Evidence: Gustavo-posted implementation-dispatch prompt in Neo's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0016`.
- Scope affected: this canonical-installation task only.
- Superseded decisions: none.
- User approval reference: `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`.
- Authorizes further work: `YES` — bounded exclusively to the exact documentation-only canonical-installation package identified by `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`.
- Note: This is an installation authorization, not an acceptance event. It authorizes no technical implementation, tests, venue access, credential use, funding, order activity, trading, or later phase.
