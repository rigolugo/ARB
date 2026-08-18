# DECISION_LOG

Append-oriented record of project decisions. Historical entries are not rewritten; corrections and supersessions use new entries. This log is audit history, not a universal authorization prerequisite.

A bounded exact Gustavo current-chat dispatch may itself authorize the exact task it states within `project_context/GUARDRAILS.md`. A decision or authorization log entry need not pre-exist that already-authorized task, cannot retroactively authorize out-of-scope activity, and cannot fill an omitted capability. Marco review direction does not grant capability.

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

### DEC-0023
- Candidate ID: `CANDIDATE_02` (Kalshi Demo environment separation)
- Date: 2026-08-06
- Decision: Records the completed Candidate 02 canonical documentation installation lifecycle, distinguishing: (1) Candidate 02 specification acceptance was the earlier exact-artifact acceptance (see DEC-0021); (2) the canonical-installation authorization was a separate bounded documentation authorization (see DEC-0022); (3) Marco's remote-commit approval was a separate independent review event; (4) Gustavo's final installed-implementation acceptance applies to exact commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`; (5) Gustavo separately authorized this exact documentation-only acceptance-closure package to record that completed lifecycle.
- Status: `ACCEPTED_AND_CLOSURE_AUTHORIZED`
- Rationale: Independent review gate followed by explicit Gustavo acceptance closes the Candidate 02 canonical documentation installation lifecycle.
- Evidence: Marco's approval of remote installation commit `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`; Gustavo's exact installed-implementation acceptance statement; Gustavo-posted acceptance-closure dispatch in Neo's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0017`.
- Scope affected: Candidate 02 canonical documentation installation lifecycle and this exact record-only closure package.
- Superseded decisions: none.
- User approval reference: `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_INSTALLATION_ACCEPTANCE_CLOSURE_PACKAGE_01`.
- Authorizes further work: `YES` only for the exact documentation-only acceptance-closure package identified by `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_INSTALLATION_ACCEPTANCE_CLOSURE_PACKAGE_01`.
- Note: No technical implementation is authorized. No tests are authorized. No venue or credential access is authorized. No funding, order, cancellation, paper-trading, or live-trading capability is authorized. No later phase is authorized.

### DEC-0024
- Accepted implementation commit: `049ce4bdfebd39eee7e366431acea36ca3d55e18`
- Date: 2026-08-07
- Decision: Records the accepted and canonically installed Kalshi Demo offline environment-separation and capability-envelope validator implementation (`KALSHI_DEMO_ENVIRONMENT_SEPARATION_OFFLINE_VALIDATOR_IMPLEMENTATION_05`) and this separately bounded canonical-state closure authorization. Distinguishes exactly:
  1. the Implementation 05 implementation authorization and correction lineage — a bounded technical implementation authorization covering Implementations 01 through 05, of which Implementations 01 through 04 were each independently blocked by Marco's review and Implementation 05 was independently approved;
  2. Marco's independent implementation review — Marco's review of the submitted Implementation 05 package;
  3. Marco's independent remote browser-commit review — Marco's separate review of the browser-created remote commit `049ce4bdfebd39eee7e366431acea36ca3d55e18`, resulting in formal decision `APPROVE`;
  4. the non-force fast-forward installation at exact commit `049ce4bdfebd39eee7e366431acea36ca3d55e18`, a direct child of the exact prior canonical base `9e3643d5667f47fdfd4e7e89dcad046bcc0edbd6`;
  5. this closure authorization, `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01`, which only permits recording the completed technical implementation state in exactly six governance/documentation paths, and does not itself authorize any new technical implementation, execution, connectivity, credential use, venue access, or trading.
- Status: `ACCEPTED_AND_CLOSURE_AUTHORIZED`
- Rationale: Independent implementation review, independent remote-commit review, and non-force fast-forward installation together close the Implementation 05 technical implementation lifecycle; this closure authorization separately and narrowly permits recording that completed state.
- Evidence: Marco's independent review of the Implementation 05 package; Marco's independent review and `APPROVE` decision on remote commit `049ce4bdfebd39eee7e366431acea36ca3d55e18`; Neo's acceptance test run (CPython 3.12.3, `PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v`, 186/186 passed); Gustavo-posted canonical-state-closure dispatch in Neo's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0018`.
- Scope affected: Kalshi Demo offline environment-separation and capability-envelope validator implementation lifecycle, and this exact record-only closure package.
- Superseded decisions: none. Does not supersede or reopen `DEC-0023` (the separate Candidate 02 documentation-only canonical-installation acceptance and closure).
- User approval reference: `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01`.
- Network access under the original `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01` authorization: `PROHIBITED`. That original authorization did not itself permit Neo to fetch or clone the canonical repository; see `AUTH-0019` and `DEC-0025` for the separate, later authorization that made the exact canonical base available.
- Authorizes further work: `YES` only for this exact documentation closure task identified by `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01`; `NO` for connectivity, credentials, venue access, trading, and any later phase.
- Note: No connectivity, network execution, credential use, venue access (Kalshi Demo, Kalshi production, or Polymarket), funding, order, cancellation, paper-trading, or live-trading capability is authorized by this decision or by the underlying accepted implementation. Demo results are not, and this decision does not represent them as, production evidence. The offline validator is not represented as a connectivity implementation, venue adapter, market-data implementation, order implementation, or trading implementation.

### DEC-0025
- Date: 2026-08-07
- Decision: Records Gustavo's later, separate instruction, issued directly in chat: "update your local repo or clone again main." This instruction followed Neo's valid canonical-base-unavailable halt of `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01` (`status: BLOCKED`, blocker `LOCKED — CANONICAL BASELINE UNAVAILABLE_OFFLINE`), which occurred because exact canonical commit `049ce4bdfebd39eee7e366431acea36ca3d55e18` was not available in Neo's local repository and that task's own authorization did not itself permit repository synchronization. This decision authorized only the bounded read-only repository synchronization needed to obtain the exact canonical commit. The actual synchronization operation performed was `git fetch origin main`, followed by local fast-forward/update to the exact required base `049ce4bdfebd39eee7e366431acea36ca3d55e18`.
- Status: `ACCEPTED`
- Rationale: A narrowly bounded, explicit, one-time repository-read instruction resolving a correctly-identified offline blocker, distinct from and not expanding the substantive capability grant of the underlying documentation-closure task.
- Evidence: Gustavo's exact chat instruction; Neo's prior `status: BLOCKED` return with blocker `LOCKED — CANONICAL BASELINE UNAVAILABLE_OFFLINE`; `git fetch origin main` and subsequent fast-forward to `049ce4bdfebd39eee7e366431acea36ca3d55e18`; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0019`.
- Scope affected: local repository availability only, for the purpose of continuing the already-authorized `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01` documentation task. This decision's scope is limited solely to unblocking that task; it is not represented as authorizing repository synchronization for any later closure task. The later standing authorization (`AUTH-0020` / `DEC-0026`) separately covers repository synchronization for future separately authorized tasks, including Closure 02 or Closure 03 if actually needed.
- Superseded decisions: none.
- User approval reference: `GUSTAVO_NEO_CANONICAL_REPOSITORY_BASE_SYNC_01`.
- Authorizes further work: `NO` — this decision authorized no technical implementation, no tests, no venue access, no credentials, no trading, and no remote repository write. It authorized only the described one-time read-only synchronization.

### DEC-0026
- Date: 2026-08-07
- Decision: Records Gustavo's standing authorization permitting Neo to maintain a read-only local filesystem clone of `rigolugo/ARB` for future separately authorized tasks, so that a missing, stale, or behind-canonical local clone does not by itself require a new user authorization merely to become current. Bound to authorization ID `GUSTAVO_NEO_STANDING_CANONICAL_REPOSITORY_READ_ONLY_SYNC_01`.
- Status: `ACCEPTED`
- Rationale: Reduces repeated narrow one-time synchronization requests (as in `DEC-0025`) for a routine, read-only, fail-safe repository operation, while preserving the requirement that every material task still carry its own separate bounded authorization.
- Evidence: Gustavo-posted standing-authorization terms in Neo's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0020`.
- Scope affected: local repository availability for `rigolugo/ARB` only, across future separately authorized Neo tasks.
- Superseded decisions: none.
- User approval reference: `GUSTAVO_NEO_STANDING_CANONICAL_REPOSITORY_READ_ONLY_SYNC_01`.
- Permits only: canonical repository clone; fetch; fast-forward-only pull/update; checkout; ref retrieval; read-only verification.
- Grants no: source changes; documentation changes; test changes; test execution; implementation; repository commits; remote writes; venue access; credentials; trading — by itself.
- Authorizes further work: `NO`, except that read-only canonical repository synchronization may accompany an otherwise separately authorized Neo task.

### DEC-0027
- Date: 2026-08-07
- Decision: Records Gustavo's explicit authorization of `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_02`, bounded to the six documentation/governance paths (`START_HERE.md`; `project_context/START_HERE.md`; `project_context/PROJECT_STATE.md`; `project_context/AUTHORIZATION_LOG.md`; `project_context/DECISION_LOG.md`; `project_context/ARTIFACT_INDEX.md`). This authorization did not authorize technical implementation, tests, venue access, credentials, remote writes, or trading.
- Status: `BLOCKED`
- Marco's disposition: `BLOCK`
- Reason: Closure 02 omitted its own authorization event from `AUTHORIZATION_LOG.md` and `DECISION_LOG.md`; contained incorrect/incomplete dates for the new August 7 authorization events (recorded as August 6); retrospectively broadened `DEC-0025`'s scope from Closure 01 alone to "Closure 01/02"; and left `PROJECT_STATE.md` referring to Closure 01 as the exact current closure task.
- Canonical effect of Closure 02: `NONE`
- Blocked local commit: `38bafc11024764b608894ffd3877a9097969a26d`
- Rationale: Independent Marco review is required before any closure package's documentation corrections take canonical effect; Closure 02 failed that review for the reasons stated above and was not installed.
- Evidence: Marco's independent review and `BLOCK` disposition of the Closure 02 package; Gustavo-posted Closure 03 correction dispatch in Neo's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0021`.
- Scope affected: `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_02` lifecycle only. Does not affect the separately accepted and installed Implementation 05 technical implementation (see `DEC-0024`).
- Superseded decisions: none.
- User approval reference: none separately assigned in the original Closure 02 authorization instruction (see `AUTH-0021`).
- Authorizes further work: `NO`.

### DEC-0028
- Date: 2026-08-07
- Decision: Records Gustavo's explicit authorization `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_03_01`, authorizing Neo to prepare `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_03` as one bounded documentation/governance correction to blocked Closure 02, bounded to the same six documentation/governance paths as Closure 01 and Closure 02.
- Status: `SUBMITTED_FOR_MARCO_REVIEW`
- Rationale: Corrects the specific defects that caused Marco to block Closure 02 (missing own-authorization-event record, incorrect dates, over-broadened `DEC-0025` scope, and a stale `PROJECT_STATE.md` reference to Closure 01 as current), while preserving all otherwise-accurate Closure 01/02 content.
- Evidence: Gustavo-posted Closure 03 correction dispatch in Neo's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0022`.
- Scope affected: this exact bounded documentation-closure correction task only.
- Superseded decisions: none.
- User approval reference: `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_03_01`.
- Authorizes further work: `NO` beyond this exact documentation closure task.
- Note: This decision does not claim that Closure 03 is already installed or accepted. Canonical effect, if any, occurs only after Marco's independent review, browser transfer, and any permitted non-force fast-forward.

### DEC-0029
- Date: 2026-08-07
- Decision: Records Gustavo's explicit current-chat authorization `ARB_WORKFLOW_SIMPLIFICATION_AMENDMENT_01_CANONICAL_INSTALLATION_02`, authorizing Bruno to prepare one fresh bounded documentation/governance correction to blocked `ARB_WORKFLOW_SIMPLIFICATION_AMENDMENT_01_CANONICAL_INSTALLATION_01` directly from exact canonical base `6252833f5e315d171c5c4a7002e79ec278ddc888`, across exactly eight named governance paths, with no blocked-predecessor ancestry.
- Status: `AUTHORIZED_PREPARED_FOR_MARCO_REVIEW`
- Rationale: Correct only the blocked Installation 01 defects: complete dispatch/correction/risk governance; add the accepted streamlined byte-identical remote-review rule; remove log-as-prerequisite contradictions; record Closure 03 as already canonical at `6252833f5e315d171c5c4a7002e79ec278ddc888`; simplify both START_HERE routers; and preserve protected bytes and historical AUTH/DEC entries.
- Evidence: Gustavo's exact current-chat dispatch; controlling `ARB_WORKFLOW_SIMPLIFICATION_AMENDMENT_01_CANDIDATE_02.md` identity `69863` bytes / sha256 `5931cf008435e03883098c4aca5020be01e696e6c99d356c6780ab6a03067b8c`; canonical `main` observed at `6252833f5e315d171c5c4a7002e79ec278ddc888`; blocked Installation 01 package supplied as correction reference only.
- Scope affected: exactly `START_HERE.md`; `project_context/START_HERE.md`; `project_context/AGENT_ROLES.md`; `project_context/PROJECT_STATE.md`; `project_context/AUTHORIZATION_LOG.md`; `project_context/DECISION_LOG.md`; `project_context/PROJECT_AGENT_DISPATCH_AUTHORITY.md`; and `BROWSER_BRANCH_REPOSITORY_TRANSFER_WORKFLOW.md`. Every other path is protected.
- Superseded decisions: none. Blocked Installation 01 had no canonical audit entry or canonical effect at this base.
- User approval reference: `ARB_WORKFLOW_SIMPLIFICATION_AMENDMENT_01_CANONICAL_INSTALLATION_02`.
- Authorizes further work: `NO` beyond this exact preparation; no subsequent phase begins automatically.
- Canonical effect: `NONE` at package preparation. Marco review is pending.

### DEC-0030
- Candidate ID: `839d475b55a708ec6e2bf280a99b1c35992dd6b1` (Gate-C `IMPLEMENTATION_02`, a same-scope correction to Marco-blocked `IMPLEMENTATION_01` candidate `2fc7a281dbf091f53a859eec3f1a632bfdfe564a`, never installed)
- Date: 2026-08-18
- Decision: Marco approved Implementation 02's local candidate `839d475b55a708ec6e2bf280a99b1c35992dd6b1` (parent `12e69143fa94540f2a5f803a5677aa1718207478`, tree `c6dc085da5e399bf6be144866c2b63d179242921`), correcting Implementation 01's two blocking defects (post-admission cleanup safety; per-boundary deadline test coverage) and adding independently verified commit-object provenance.
- Status: `ACCEPTED`
- Rationale: Correction 01 (cleanup-protected Stage 3J/3K post-admission region ending any genuine live `ws_` session through canonical `end_writer_session` on every subsequent failure path) and Correction 02 (four independently targeted deadline-boundary tests replacing one mislabeled test) resolved the exact defects Marco identified in Implementation 01; the corrected candidate's regression evidence (focused 824 passed, protected regression 873 passed, broader regression 1772 passed, full discovery 2199 passed, 0 failed) and static traceability matrix were reviewed.
- Evidence: the exact task-implementer-produced candidate, review bundle (`KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_RUNNER_GATE_C_RELEASE_AND_NORMAL_WRITER_HANDOFF_IMPLEMENTATION_02_MARCO_REVIEW_BUNDLE_01.zip`), and its manifest; this decision's own evidentiary basis is the exact assertion of Marco's approval embedded in the subsequent `KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_RUNNER_GATE_C_IMPLEMENTATION_02_REMOTE_REVIEW_TRANSFER_01` dispatch, which states this candidate as already Marco-approved; no separate distinct Marco-review-output message was directly produced or observed within this implementer's own session prior to that dispatch.
- Scope affected: Gate-C release/normal-writer runner code (`src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py`, `tests/test_kalshi_minimal_market_maker_experiment_runner.py`) only.
- Superseded decisions: none recorded for Implementation 01 in this log (Implementation 01 was blocked before reaching this log; see `project_context/ARTIFACT_INDEX.md` non-indexed note).
- User approval reference: `KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_RUNNER_GATE_C_IMPLEMENTATION_02_REMOTE_REVIEW_TRANSFER_01` (assertion of prior approval).
- Authorizes further work: `NO` — local approval alone does not authorize a remote write, canonical installation, or Gate D.

### DEC-0031
- Candidate ID: `839d475b55a708ec6e2bf280a99b1c35992dd6b1`
- Date: 2026-08-18
- Decision: Marco independently reviewed the temporary remote review branch `review/gate-c-impl-02-839d475b` (pushed to `rigolugo/ARB` pointing directly at commit `839d475b55a708ec6e2bf280a99b1c35992dd6b1`, parent `12e69143fa94540f2a5f803a5677aa1718207478`, tree `c6dc085da5e399bf6be144866c2b63d179242921`, changed paths exactly the two Gate-C runner/test files) and approved it as byte-for-byte and commit-for-commit equivalent to the locally approved candidate in `DEC-0030`.
- Status: `ACCEPTED`
- Rationale: The remote-transfer task performed exhaustive pre-push and post-push verification (candidate SHA/parent/tree/commit-count/diff-name equality; protected-blob equality; branch-non-existence check before push; post-push remote re-derivation of parent/tree/diff/`origin/main`), so the remote-hosted object is provably the identical Git object as the local approval.
- Evidence: the remote-review-transfer completion report (`READY_FOR_MARCO_REMOTE_BRANCH_REVIEW`) recorded in this project's chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0025`; this decision's evidentiary basis for the remote review's own approval outcome is this documentation-sync dispatch's framing of Gate C as already canonically installed, which presupposes that step; no separate distinct "Marco reviewed the remote branch and approved" message was directly observed within this implementer's own session.
- Scope affected: remote-hosted equivalence confirmation for `839d475b55a708ec6e2bf280a99b1c35992dd6b1` only.
- Superseded decisions: none.
- User approval reference: `KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_RUNNER_GATE_C_IMPLEMENTATION_02_REMOTE_REVIEW_TRANSFER_01`.
- Authorizes further work: `NO` — remote-branch equivalence approval alone does not authorize canonical installation or Gate D.

### DEC-0032
- Candidate ID: `839d475b55a708ec6e2bf280a99b1c35992dd6b1`
- Date: 2026-08-18
- Decision: Gustavo explicitly authorized canonical installation of exact candidate `839d475b55a708ec6e2bf280a99b1c35992dd6b1` onto canonical `main`.
- Status: `ACCEPTED`
- Rationale: Following `DEC-0030`/`DEC-0031`'s local and remote-branch approvals, canonical `main` was advanced to this exact commit.
- Evidence: this decision's evidentiary basis is (a) the independently Git-verified observation recorded in `DEC-0033` that `origin/main` now resolves to exactly `839d475b55a708ec6e2bf280a99b1c35992dd6b1` via a clean single-parent fast-forward from the prior canonical `main` (`12e69143fa94540f2a5f803a5677aa1718207478`), and (b) this exact documentation-sync dispatch's own framing of Gate C as "the already-installed Gate-C implementation." No separate distinct "I, Gustavo, authorize canonical installation" chat message was directly observed within this implementer's own session; this entry records the authorization as evidenced by its observed effect plus the current dispatch's assertion, not by a witnessed authorization utterance.
- Scope affected: canonical `main` for `rigolugo/ARB`.
- Superseded decisions: none.
- User approval reference: not separately captured as a discrete message in this implementer's session; see rationale.
- Authorizes further work: `NO` beyond the installation itself — installation grants no Gate-D capability (see `DEC-0034`/`PROJECT_STATE.md` Section 13.4).

### DEC-0033
- Candidate ID: `839d475b55a708ec6e2bf280a99b1c35992dd6b1`
- Date: 2026-08-18
- Decision: Records the independently Git-verified technical fact that canonical `main` was fast-forwarded to exact commit `839d475b55a708ec6e2bf280a99b1c35992dd6b1`, with no replacement commit and no merge commit.
- Status: `ACCEPTED`
- Rationale: `git cat-file -p 839d475b55a708ec6e2bf280a99b1c35992dd6b1` shows exactly one `parent` line (`12e69143fa94540f2a5f803a5677aa1718207478`, the immediately prior canonical `main`), which is structurally inconsistent with a merge commit (which would carry two or more `parent` lines) and consistent only with a linear, non-force fast-forward.
- Evidence: `git fetch origin main` plus `git rev-parse origin/main` (`839d475b55a708ec6e2bf280a99b1c35992dd6b1`) and `git cat-file -p` of that object, independently re-executed by this documentation-sync task.
- Scope affected: canonical `main` provenance record only.
- Superseded decisions: none.
- User approval reference: n/a (technical observation, not itself an authorization).
- Authorizes further work: `NO`.

### DEC-0034
- Candidate ID: n/a (documentation-only)
- Date: 2026-08-18
- Decision: Gustavo explicitly authorized `ARB_CANONICAL_DOCUMENTATION_STATE_SYNC_THROUGH_GATE_C_01`, a bounded documentation-only synchronization of `project_context/PROJECT_STATE.md`, `project_context/ARTIFACT_INDEX.md`, `project_context/DECISION_LOG.md`, and `project_context/AUTHORIZATION_LOG.md` through the installed Gate-C candidate, explicitly before any Gate-D specification or implementation work begins.
- Status: `ACCEPTED`
- Rationale: Carries canonical governance-state documentation forward through the persistent-ledger, emergency-cancellation, minimal-market-maker, and runner Gate A/B/C milestones while preserving the unresolved historical incident and explicitly withholding any Gate-D authorization.
- Evidence: Gustavo's exact current-chat dispatch `ARB_CANONICAL_DOCUMENTATION_STATE_SYNC_THROUGH_GATE_C_01`, posted directly in this implementer's current project chat; `project_context/AUTHORIZATION_LOG.md` entry `AUTH-0028`.
- Scope affected: exactly the four named governance paths.
- Superseded decisions: none.
- User approval reference: `ARB_CANONICAL_DOCUMENTATION_STATE_SYNC_THROUGH_GATE_C_01`.
- Authorizes further work: `NO` — this decision explicitly does not authorize Gate D, and grants no venue, credential, or execution capability.
