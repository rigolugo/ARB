# AUTHORIZATION_LOG

Append-only capability ledger, separate from `DECISION_LOG.md`, constrained by `project_context/GUARDRAILS.md`. Every capability field contains `PERMITTED` or `PROHIBITED`; no blank, inherited, or candidate-carried-forward fields are allowed. History is preserved; revocation is a new entry, not a rewrite.

---

### AUTH-0001 — Original Candidate 01 authorization
- Authorizing user: Gustavo
- Authorized agent: Bruno
- Task/phase: original repository-bootstrap specification (Candidate 01)
- Permitted artifact filenames: Candidate 01 specification and handoff (historical)
- Permitted repository paths: none (specification-only, external artifacts)
- Network access: `PROHIBITED` beyond canonical repository read
- Demo reads/writes: `PROHIBITED`
- Production reads/writes: `PROHIBITED`
- Credential use: `PROHIBITED`
- Account funding: `PROHIBITED`
- Code changes: `PROHIBITED`
- Tests: `PROHIBITED`
- Artifact generation: `PROHIBITED`
- Repository commits: `PROHIBITED`
- Expiration/completion condition: completed upon Candidate 01 delivery
- Revocation status: not revoked; superseded in effect by later candidates
- Note: remains the first historical specification authorization. Does not authorize Candidate 04 through Candidate 10, repository modification, code, tests, venue access, credentials, funding, orders, cancellations, trading, or Neo.

### AUTH-0002 — Candidate 04 submission
- Authorizing user: none separately recorded
- Authorized agent: Bruno
- Task/phase: Candidate 04 submission
- Status: submission/provenance event, not an authorization grant
- Note: shall not be represented as a Gustavo authorization entry; does not inherit from AUTH-0001; not retroactively authorized by Candidate 10.

### AUTH-0003 — Candidate 05 blocked submission
- Authorizing user: none separately recorded
- Authorized agent: Bruno
- Task/phase: Candidate 05 submission
- Status: blocked lifecycle/provenance fact, not an authorization grant
- Note: shall not be represented as an explicit Gustavo authorization entry; not retroactively authorized, validated, accepted, broadened, unblocked, canonicalized, or made installable by Candidate 10.

### AUTH-0004 — Candidate 06 correction authorization
- Candidate ID: `CANDIDATE_06`
- Authorizing user: Gustavo
- Authorized agent: Bruno
- Permitted: reading Candidate 05 artifacts, Marco's Candidate 05 blocking review, and this Candidate 06 authorization; producing `SPEC_repository_bootstrap_CANDIDATE_06.md` and `HANDOFF_repository_bootstrap_spec_CANDIDATE_06.md` only
- Lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`
- Disposition: blocked
- Repository effect: none
- Note: valid explicit authorization provenance preserved despite blocked disposition.

### AUTH-0005 — Candidate 07 blocked submission
- Authorizing user: none separately recorded
- Authorized agent: Bruno
- Task/phase: Candidate 07 submission
- Status: blocked lifecycle/provenance fact, not an authorization grant
- Lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`
- Disposition: blocked
- Repository effect: none

### AUTH-0006 — Candidate 08 correction authorization
- Candidate ID: `CANDIDATE_08`
- Authorizing user: Gustavo
- Authorized agent: Bruno
- Permitted: reading Candidate 07 artifacts, Marco's Candidate 07 blocking review, and this Candidate 08 authorization; producing `SPEC_repository_bootstrap_CANDIDATE_08.md` and `HANDOFF_repository_bootstrap_spec_CANDIDATE_08.md` only
- Lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`
- Disposition: blocked
- Repository effect: none
- Note: valid explicit authorization provenance preserved despite blocked disposition.

### AUTH-0007 — Candidate 09 correction authorization
- Candidate ID: `CANDIDATE_09`
- Authorizing user: Gustavo
- Authorized agent: Bruno
- Permitted: reading Candidate 08 artifacts, Marco's Candidate 08 blocking review, and this Candidate 09 authorization; producing `SPEC_repository_bootstrap_CANDIDATE_09.md` and `HANDOFF_repository_bootstrap_spec_CANDIDATE_09.md` only
- Lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`
- Disposition: blocked
- Repository effect: none
- Note: valid explicit authorization provenance preserved despite blocked disposition. Candidate 09 is Candidate 10's immediate blocked predecessor.

### AUTH-0008 — Candidate 10 correction authorization
- Candidate ID: `CANDIDATE_10`
- Authorizing user: Gustavo
- Authorized agent: Bruno
- Permitted: reading Candidate 09 artifacts, Marco's Candidate 09 blocking review, and this Candidate 10 authorization; producing `SPEC_repository_bootstrap_CANDIDATE_10.md` and `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md` only
- Lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`
- Repository effect: none
- Note: distinct event; does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, 06, 07, 08, or 09. Not candidate acceptance. Not implementation authorization.

### AUTH-0009 — Candidate 10 acceptance
- Candidate ID: `CANDIDATE_10`
- Authorizing user: Gustavo
- Action: explicit acceptance of the exact identity-bound Candidate 10 specification (`SPEC_repository_bootstrap_CANDIDATE_10.md`, 122041 bytes, sha256 `6cff9ca01e0d3779d95ecea241ed83e1b47126117b1660e2066862b823f02b71`) and Bruno handoff (`HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`, 17497 bytes, sha256 `be3dccbb16b270edb67297baf40bcf3944edeaa4877a30e13e1eecdbca823c7e`)
- Repository effect: none by itself
- Note: separate from Candidate 10 correction authorization (AUTH-0008) and from implementation authorization (AUTH-0010).

### AUTH-0010 — Bootstrap implementation authorization
- Authorization ID: `GUSTAVO_CANDIDATE_10_REPOSITORY_BOOTSTRAP_IMPLEMENTATION_01`
- Authorizing user: Gustavo
- Date: 2026-08-06
- Authorized agent: Neo
- Candidate ID: `CANDIDATE_10`
- Task/phase: `CANDIDATE_10_REPOSITORY_BOOTSTRAP_IMPLEMENTATION_01`
- Exact permitted artifact filenames: `SPEC_repository_bootstrap_CANDIDATE_10.md`; `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`; `REVIEW_repository_bootstrap_spec_CANDIDATE_10.md`; `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md`
- Permitted repository paths: exactly the paths listed in `handoffs/HANDOFF_repository_bootstrap_implementation.md` Section 5
- Network access: `PERMITTED` (read canonical repository and required GitHub clone/fetch/push only)
- Demo reads: `PROHIBITED`
- Demo writes: `PROHIBITED`
- Production reads: `PROHIBITED`
- Production writes: `PROHIBITED`
- Credential use: `PROHIBITED` beyond the authorized GitHub push operation
- Account funding: `PROHIBITED`
- Code changes: `PROHIBITED`
- Tests: `PROHIBITED`
- Artifact generation: `PROHIBITED` beyond required implementation evidence
- Repository commits: `PERMITTED` (one commit on branch `candidate-10-repository-bootstrap`)
- Expiration/completion condition: completion of this bounded implementation task and return of required evidence
- Revocation status: not revoked
- Related specification identity: `SPEC_repository_bootstrap_CANDIDATE_10.md` (see AUTH-0009)
- Related Marco review: `REVIEW_repository_bootstrap_spec_CANDIDATE_10.md`, 2997 bytes, sha256 `78ff8e6252f0a45421ed479b4bdb87628138e1c4e4d5e919bc81816863d3d0b6`, decision `APPROVE`
- Related Bruno handoff identity: `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md` (see AUTH-0009)
- Related implementation handoff: `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md`, 9226 bytes, sha256 `a7be9eea76e17cf8729bb256d864bb60fd7a92bb1347db32bea16977a7d4cd71`

### AUTH-0011 — Bootstrap implementation authorization completion
- Related authorization: `GUSTAVO_CANDIDATE_10_REPOSITORY_BOOTSTRAP_IMPLEMENTATION_01` (see AUTH-0010)
- Date: 2026-08-06
- Completion condition satisfied: yes — implementation accepted at commit `e136be0b80f0370572e889d1075a11fc1b445348`
- Status: `COMPLETED`
- Grants new capabilities: `NO`
- Demo reads: `PROHIBITED`
- Demo writes: `PROHIBITED`
- Production reads: `PROHIBITED`
- Production writes: `PROHIBITED`
- Credential use: `PROHIBITED`
- Account funding: `PROHIBITED`
- Orders: `PROHIBITED`
- Cancellations: `PROHIBITED`
- Trading: `PROHIBITED`
- Later-phase work: `PROHIBITED`
- Note: this completion entry closes AUTH-0010. It does not authorize any subsequent technical phase. Any further work requires its own separate bounded specification, review, and authorization.

## Required historical authorization distinction (preserved verbatim in effect)

1. **Original Candidate 01 authorization** — see AUTH-0001.
2. **Candidate 04 submission without separately recorded explicit authorization** — see AUTH-0002.
3. **Candidate 05 blocked submission without separately recorded explicit authorization** — see AUTH-0003.
4. **Candidate 06 correction authorization and blocked submission** — see AUTH-0004.
5. **Candidate 07 blocked submission without separately recorded explicit authorization** — see AUTH-0005.
6. **Candidate 08 correction authorization and blocked submission** — see AUTH-0006.
7. **Candidate 09 correction authorization and blocked submission** — see AUTH-0007.
8. **Candidate 10 correction authorization** — see AUTH-0008.

Candidate 10 correction authorization (AUTH-0008) shall not be represented as an amendment to Candidate 01, as authorization of Candidate 04 or Candidate 05, as acceptance or unblocking of Candidate 06, Candidate 07, Candidate 08, or Candidate 09, as candidate acceptance, or as implementation authorization. AUTH-0001, AUTH-0002, AUTH-0003, AUTH-0004, AUTH-0005, AUTH-0006, AUTH-0007, AUTH-0008, AUTH-0009, and AUTH-0010 remain separate.

### AUTH-0012 — Candidate 01 specification-drafting authorization (Kalshi Demo environment separation)
- Authorization ID: `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_01`
- Authorizing user: Gustavo
- Authorized agent: Bruno
- Task/phase: original Kalshi Demo environment-separation and capability-envelope specification (Candidate 01)
- Permitted artifact filenames: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md`; `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_01.md` (external, specification-only)
- Permitted repository paths: none
- Network access: `PERMITTED` only for read-only access to the canonical `rigolugo/ARB` repository; official Kalshi documentation; the official REST OpenAPI specification; the official WebSocket AsyncAPI specification; the official Kalshi changelog; and, only if needed, bounded read-only inspection of these five named external repositories:
  - `Jonmaa/btc-polymarket-bot`
  - `ImMike/polymarket-arbitrage`
  - `tswaim/polymarket-kalshi-arbitrage-bot`
  - `TopTrenDev/polymarket-kalshi-arbitrage-bot`
  - `haoo99/Polymarket-Kalshi-Arbitrage-Bot`
- Execution evidence: this authorization entry records permitted scope only. It does not assert that optional access to any named external repository occurred. Source-code reuse from all five repositories is prohibited under Candidate 01; only non-normative design findings could be drawn from them.
- Demo reads/writes: `PROHIBITED`
- Production reads/writes: `PROHIBITED`
- Credential use: `PROHIBITED`
- Account funding: `PROHIBITED`
- Code changes: `PROHIBITED`
- Tests: `PROHIBITED`
- Artifact generation: `PERMITTED` only for:
  - `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md`
  - `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_01.md`
  - reporting their raw byte lengths and SHA-256 identities.
- Repository commits: `PROHIBITED`
- Expiration/completion condition: completed upon Candidate 01 delivery
- Revocation status: not revoked; superseded in effect by the Candidate 02 correction
- Note: this is historical authorization-scope recording only; it creates no current capability. Does not authorize Candidate 02, repository modification, implementation source, test source, test execution, project imports, package installation, venue access, credentials, funding, orders, cancellations, trading, or Neo.
- Source verification: independently confirmed against the supplied `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md` (75847 bytes, sha256 `b8147c989852350bcd02cbc3cf5f18374f50a12a3a3ca140373dab9885431735`), Section 2.2 (`Candidate-authoring capability matrix`) and Section 25 (`Accepted external-repository findings`).

### AUTH-0013 — Candidate 01 blocked disposition (Kalshi Demo environment separation)
- Candidate ID: `CANDIDATE_01`
- Authorizing user: n/a (disposition record)
- Task/phase: Marco's Candidate 01 review
- Disposition: `BLOCK`
- Repository effect: none
- Note: Candidate 01 remains blocked, noncanonical, uninstalled, and non-authorizing. Preserved for historical lineage only.

### AUTH-0014 — Candidate 02 bounded-correction authorization (Kalshi Demo environment separation)
- Authorization ID: `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01`
- Authorizing user: Gustavo
- Authorized agent: Bruno
- Task/phase: bounded correction of blocked Candidate 01 (Candidate 02)
- Permitted artifact filenames: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`; `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` only
- Permitted repository paths: none
- Network access: `PERMITTED` for read-only canonical repository access, exact Candidate 01 artifacts, and bounded verification of the current official fixed-point source page only
- Demo reads/writes: `PROHIBITED`
- Production reads/writes: `PROHIBITED`
- Credential use: `PROHIBITED`
- Account funding: `PROHIBITED`
- Code changes: `PROHIBITED`
- Tests: `PROHIBITED`
- Artifact generation: `PERMITTED` only for the two named external Markdown candidates and identity reporting
- Repository commits: `PROHIBITED`
- Expiration/completion condition: completed upon Candidate 02 delivery with lifecycle `SUBMITTED_FOR_MARCO_REVIEW`
- Revocation status: not revoked
- Note: does not itself authorize canonical installation, implementation, tests, venue access, credentials, funding, orders, cancellations, or trading.

### AUTH-0015 — Candidate 02 acceptance (Kalshi Demo environment separation)
- Candidate ID: `CANDIDATE_02`
- Authorizing user: Gustavo
- Action: explicit acceptance of the exact identity-bound Candidate 02 specification (`SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`, 78876 bytes, sha256 `4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2`) and Bruno handoff (`HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`, 14114 bytes, sha256 `a47d623c4a80048909e4e9df8e4c11904ff0e763ab4e242028bd0c81dcedee6d`)
- Repository effect: none by itself
- Note: separate from the Candidate 02 correction authorization (AUTH-0014) and from the canonical-installation authorization (AUTH-0016). Does not accept Candidate 01. Does not authorize implementation source, tests, venue access, credentials, or a later technical phase.

### AUTH-0016 — Kalshi Demo environment-separation Candidate 02 canonical-installation authorization
- Authorization ID: `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`
- Authorizing user: Gustavo
- Date: 2026-08-06
- Authorized agent: Neo
- Candidate ID: `CANDIDATE_02`
- Task/phase: `KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_PACKAGE_01`, classification `DOCUMENTATION_ONLY_CANONICAL_INSTALLATION_PACKAGE`
- Exact permitted artifact filenames: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`; `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`; `REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`; `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation_CANDIDATE_02.md`
- Permitted repository paths: exactly the ten paths listed in `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation.md` Section 7
- Repository-transfer mode: `MANUAL_BROWSER_TEMPORARY_BRANCH`
- Network access: `PERMITTED` (read-only canonical repository clone/fetch only; no push)
- Demo reads: `PROHIBITED`
- Demo writes: `PROHIBITED`
- Production reads: `PROHIBITED`
- Production writes: `PROHIBITED`
- Credential use: `PROHIBITED`
- Account funding: `PROHIBITED`
- Code changes: `PROHIBITED`
- Tests: `PROHIBITED`
- Artifact generation: `PERMITTED` only for the required installation package, detached checksum, manifest, and implementation evidence
- Repository commits: `PERMITTED` (one local commit on branch `neo-c02-kalshi-demo-spec-installation`; Neo push `PROHIBITED`)
- Expiration/completion condition: completion of this bounded canonical-installation task and return of required evidence
- Revocation status: not revoked
- Related specification identity: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md` (see AUTH-0015)
- Related Marco review: `REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`, 6213 bytes, sha256 `6d665601c5eb0b35943e0a782a34141f45b13b9f3440c3052c85171d54fe3c9b`, decision `APPROVE`
- Related Bruno handoff identity: `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` (see AUTH-0015)
- Related implementation handoff: `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation_CANDIDATE_02.md`, 18572 bytes, sha256 `19ec68c938d2d72dfa769dfc4c40e638d1e5f97f2590abf4928a73b2ba720982`
- Completion semantics: this authorization is consumed by the exact reviewed installation commit and grants no technical implementation, tests, venue, credential, funding, order, cancellation, or trading capability.

### AUTH-0017 — Candidate 02 installed documentation acceptance and closure authorization
- Authorization ID: `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_INSTALLATION_ACCEPTANCE_CLOSURE_PACKAGE_01`
- Authorizing user: Gustavo
- Authorized agent: Neo
- Date: 2026-08-06
- Candidate ID: `CANDIDATE_02`
- Classification: `DOCUMENTATION_ONLY_CANONICAL_ACCEPTANCE_CLOSURE`
- Gustavo explicitly accepted the installed Candidate 02 canonical documentation implementation at: `3d19bd9f3d3610f4af0304bfd3ecf833cfd8420d`
- Related prior installation authorization: `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`
- The prior installation authorization is completed and consumed by the exact accepted installation commit.
- Exact permitted repository paths: `project_context/PROJECT_STATE.md`; `project_context/AUTHORIZATION_LOG.md`; `project_context/DECISION_LOG.md`; `project_context/ARTIFACT_INDEX.md` only
- Repository-transfer mode: `MANUAL_BROWSER_TEMPORARY_BRANCH`
- Network access: `PERMITTED` only for read-only canonical GitHub clone/fetch and exact-base verification
- Local documentation changes: `PERMITTED` only for this closure
- Local repository commit: `PERMITTED` exactly once on the authorized local branch
- Package, detached checksum, manifest, and deterministic review evidence: `PERMITTED`
- Neo push: `PROHIBITED`
- Remote branch creation: `PROHIBITED` for Neo
- Modification of `main`: `PROHIBITED` for Neo
- Technical implementation: `PROHIBITED`
- Source code: `PROHIBITED`
- Test source and test execution: `PROHIBITED`
- Project imports and package installation: `PROHIBITED`
- Kalshi Demo reads and writes: `PROHIBITED`
- Kalshi production reads and writes: `PROHIBITED`
- Polymarket reads and writes: `PROHIBITED`
- Credential, private-key, account, balance, portfolio, and position access: `PROHIBITED`
- Funding: `PROHIBITED`
- Orders, amendments, cancellations, paper trading, and live trading: `PROHIBITED`
- Later-phase work: `PROHIBITED`
- Completion condition: preparation and return of the exact closure package for Marco review; canonical effect occurs only after later reviewed browser transfer and non-force fast-forward.
- Grants new technical capability: `NO`
- Note: this entry records both the accepted installation closure and the bounded authorization to prepare the record-only closure package. It does not imply that the closure package itself is already installed or accepted.

### AUTH-0018 — Kalshi Demo offline validator Implementation 05 canonical state closure authorization
- Authorization ID: `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01`
- Authorizing user: Gustavo
- Authorized agent: Neo
- Date: 2026-08-07
- Task/phase: `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01`
- Classification: `DOCUMENTATION_GOVERNANCE_CANONICAL_STATE_CLOSURE_ONLY`
- Records the already accepted and installed Kalshi Demo offline environment-separation and capability-envelope validator implementation (`KALSHI_DEMO_ENVIRONMENT_SEPARATION_OFFLINE_VALIDATOR_IMPLEMENTATION_05`) at accepted canonical implementation commit `049ce4bdfebd39eee7e366431acea36ca3d55e18`. Does not itself authorize any new technical implementation or execution.
- Exact permitted repository paths: `START_HERE.md`; `project_context/START_HERE.md`; `project_context/PROJECT_STATE.md`; `project_context/AUTHORIZATION_LOG.md`; `project_context/DECISION_LOG.md`; `project_context/ARTIFACT_INDEX.md` only
- Capability matrix for this task:
  - `network_access`: `PROHIBITED`
  - `demo_public_reads`: `PROHIBITED`
  - `demo_authenticated_reads`: `PROHIBITED`
  - `demo_writes`: `PROHIBITED`
  - `production_public_reads`: `PROHIBITED`
  - `production_authenticated_reads`: `PROHIBITED`
  - `production_writes`: `PROHIBITED`
  - `credential_use`: `PROHIBITED`
  - `account_funding`: `PROHIBITED`
  - `code_changes`: `PROHIBITED`
  - `tests`: `PROHIBITED`
  - `artifact_generation`: `PERMITTED` only for this bounded documentation closure package, checksum, manifest, and review evidence
  - `repository_commits`: `PERMITTED` exactly once locally for this bounded six-path documentation closure
- `repository_transfer_mode`: `MANUAL_BROWSER_TEMPORARY_BRANCH`
- `marco_fast_forward_main_after_approval`: `PERMITTED`
- Neo push: `PROHIBITED`
- Neo remote branch creation: `PROHIBITED`
- Neo modification of `main`: `PROHIBITED`
- Later-phase work: `PROHIBITED`
- Expiration/completion condition: preparation and return of the exact closure package for Marco review; canonical effect occurs only after later reviewed browser transfer and non-force fast-forward.
- Revocation status: not revoked
- Related implementation-lineage authorizations: the bounded Kalshi Demo offline validator implementation dispatches for Implementations 01 through 05 (Implementations 01–04 blocked by Marco's independent review; Implementation 05 approved), together with their controlling Marco handoff and runtime amendment.
- Related Marco reviews: Marco's independent review of the submitted Implementation 05 package, and Marco's independent review of the browser-created remote commit `049ce4bdfebd39eee7e366431acea36ca3d55e18`; Marco's formal decision on the remote implementation was `APPROVE`.
- Grants new technical capability: `NO`
- Note: this entry authorizes only the preparation and recording of the already-completed and already-installed technical implementation state. It does not itself claim that this exact closure package is already installed; canonical effect of this closure package occurs only after the same manual-browser-temporary-branch review and non-force fast-forward process applies to it. It does not authorize connectivity implementation, credential use, Kalshi Demo access, Kalshi production access, Polymarket access, funding, orders, cancellations, paper trading, live trading, or any later phase.
- Base-verification note: the dispatch for this task prohibits network access and requires the exact base to already be available locally, halting otherwise. The exact base was not present in Neo's local repository clone when this task was first attempted; Neo returned `status: BLOCKED` accordingly. The user (Gustavo) then separately and explicitly instructed Neo, directly in chat, to update the local clone. Neo performed a single read-only `git fetch origin main` under that explicit instruction, confirmed the fetched commit matched the exact required base byte-for-byte, and only then resumed this closure task. This fetch is recorded here for accuracy; it is not represented as part of this task's own `network_access: PROHIBITED` capability grant, and no other network request occurred at any point in this closure task. See `AUTH-0019` for the formal record of that separate synchronization authorization, and `AUTH-0020` for the later standing synchronization authorization.

### AUTH-0019 — Canonical repository base-synchronization authorization
- Authorization ID: `GUSTAVO_NEO_CANONICAL_REPOSITORY_BASE_SYNC_01`
- Authorizing user: Gustavo
- Authorized agent: Neo
- Repository: `rigolugo/ARB`
- Date: 2026-08-07
- Context: this is the separate, later authorization for the one-time synchronization event referenced in `AUTH-0018`'s base-verification note. Neo correctly halted `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_01` with `status: BLOCKED` and blocker `LOCKED — CANONICAL BASELINE UNAVAILABLE_OFFLINE` because exact canonical commit `049ce4bdfebd39eee7e366431acea36ca3d55e18` was not available in Neo's local repository, and that task's own authorization did not itself permit Neo to fetch or clone the canonical repository. Neo's halt explained that the task could proceed only if either (1) the exact canonical commit was made available locally outside Neo's authorized capabilities, or (2) Gustavo authorized the exact read-only Git operation needed to update Neo's local repository. Gustavo then explicitly instructed Neo, directly in chat: "update your local repo or clone again main."
- Purpose: make the exact required canonical base available in Neo's local filesystem so the already-authorized Closure 01 documentation task could continue.
- Permitted for this one-time event: read-only `git fetch` of `rigolugo/ARB`; read-only `git clone` of `rigolugo/ARB` if necessary; local checkout or fast-forward-only update to the exact canonical commit required by the active task.
- Actual operation performed: `git fetch origin main`, followed by local fast-forward/update to exact canonical commit `049ce4bdfebd39eee7e366431acea36ca3d55e18`.
- Network scope: `PERMITTED` only for this bounded read-only canonical-repository synchronization.
- Explicitly prohibited: `git push`; remote branch creation/deletion; remote-`main` modification; force update; pull-request creation; merge; package downloads; unrelated repositories; Kalshi; Polymarket; credentials/private keys; account access; funding; orders; cancellations; paper trading; live trading.
- Grants new technical capability: `NO`
- Note: `AUTH-0019` granted repository availability only. It did not authorize implementation, tests, venue activity, or any other phase. See `project_context/DECISION_LOG.md` entry `DEC-0025`.

### AUTH-0020 — Standing read-only canonical-repository synchronization authorization
- Authorization ID: `GUSTAVO_NEO_STANDING_CANONICAL_REPOSITORY_READ_ONLY_SYNC_01`
- Authorizing user: Gustavo
- Authorized agent: Neo
- Repository: `rigolugo/ARB`
- Date: 2026-08-07
- Status: `STANDING_READ_ONLY_REPOSITORY_SYNCHRONIZATION_AUTHORIZATION`
- Purpose: allow Neo, when performing an otherwise separately authorized project task, to obtain and maintain a local filesystem clone of the canonical `rigolugo/ARB` repository without requiring a new user authorization merely because the local clone is missing, stale, or behind canonical state.
- Permitted: `git clone` of `rigolugo/ARB`; `git fetch` from `rigolugo/ARB`; retrieval of required branches, commits, tags, and refs; `git pull --ff-only`; equivalent fetch plus verified fast-forward; checkout of the exact canonical commit required by an active task; read-only inspection needed to verify repository identity, ancestry, canonical base, and task baseline.
- Any update must be fast-forward-only. No merge commit or rebase may be created merely to synchronize the local repository.
- Remote writes: `PROHIBITED` unless separately and explicitly authorized.
- Specifically prohibited: `git push`; remote branch creation; remote branch deletion; force push; remote-`main` modification; PR creation; PR merge; GitHub issue/release/workflow/settings modification; package/dependency downloads; unrelated repository access; Kalshi network access; Polymarket network access; credential/private-key use; account access; account funding; order submission; order amendment; cancellation; paper trading; live trading.
- Capability semantics: `AUTH-0020` provides canonical repository availability only. It does NOT by itself authorize: source-code changes; documentation changes; test-source changes; test execution; project imports; implementation; specification drafting; artifact generation; repository commits; venue connectivity; credential use; or any project phase. Every material task still requires its own separately bounded authorization.
- Expiration: none automatic; may be revoked or narrowed by a later explicit Gustavo authorization.
- Grants new technical capability: `NO`
- Note: this is a standing authorization, distinct from the one-time `AUTH-0019` event. It was consulted (though not exercised, since the exact base was already available locally) when preparing `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_02`. See `project_context/DECISION_LOG.md` entry `DEC-0026`.

### AUTH-0021 — Kalshi Demo offline validator Implementation 05 canonical-state Closure 02 bounded-correction authorization
- Authorization ID: `NOT_SEPARATELY_ASSIGNED_IN_ORIGINAL_USER_AUTHORIZATION`
- Authorizing user: Gustavo
- Authorized agent: Neo
- Date: 2026-08-07
- Task/phase: `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_02`
- Classification: `DOCUMENTATION_GOVERNANCE_CANONICAL_STATE_CLOSURE_BOUNDED_CORRECTION_ONLY`
- Note on authorization ID: Gustavo's original instruction for this task began "I authorize Neo to prepare: KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_02" and did not assign a separate authorization ID. No authorization ID is invented or retroactively attributed to Gustavo for this entry; the field above records that fact precisely.
- Exact canonical base: `049ce4bdfebd39eee7e366431acea36ca3d55e18`
- Exact writable repository paths: `START_HERE.md`; `project_context/START_HERE.md`; `project_context/PROJECT_STATE.md`; `project_context/AUTHORIZATION_LOG.md`; `project_context/DECISION_LOG.md`; `project_context/ARTIFACT_INDEX.md` only (the same six documentation/governance paths as Closure 01)
- What Closure 02 did: corrected Closure 01's authorization provenance; recorded `AUTH-0019` (the one-time base-synchronization event) and `AUTH-0020` (the standing synchronization authorization); corrected the stale present-tense statement in `project_context/ARTIFACT_INDEX.md`.
- What Closure 02 did not authorize: no source-code changes; no test-source changes; no tests; no project imports; no Kalshi access; no Polymarket access; no credentials; no trading.
- Repository-transfer mode: `MANUAL_BROWSER_TEMPORARY_BRANCH`; `marco_fast_forward_main_after_approval`: `PERMITTED`.
- Grants new technical capability: `NO`
- Later-phase work: `PROHIBITED` — Closure 02 did not itself authorize any later phase.
- Disposition: Closure 02 was subsequently reviewed by Marco and disposed `BLOCK`. It was never canonically installed; its local commit `38bafc11024764b608894ffd3877a9097969a26d` had no canonical effect on `main`. See `project_context/DECISION_LOG.md` entry `DEC-0027` for Marco's disposition and stated reasons.

### AUTH-0022 — Kalshi Demo offline validator Implementation 05 canonical-state Closure 03 bounded-correction authorization
- Authorization ID: `GUSTAVO_KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_03_01`
- Authorizing user: Gustavo
- Authorized agent: Neo
- Date: 2026-08-07
- Task/phase: `KALSHI_DEMO_OFFLINE_VALIDATOR_IMPLEMENTATION_05_CANONICAL_STATE_CLOSURE_03`
- Classification: `DOCUMENTATION_GOVERNANCE_CANONICAL_STATE_CLOSURE_BOUNDED_CORRECTION_ONLY`
- Exact canonical base: `049ce4bdfebd39eee7e366431acea36ca3d55e18`
- Exact writable repository paths: `START_HERE.md`; `project_context/START_HERE.md`; `project_context/PROJECT_STATE.md`; `project_context/AUTHORIZATION_LOG.md`; `project_context/DECISION_LOG.md`; `project_context/ARTIFACT_INDEX.md` only (the same six documentation/governance paths as Closure 01 and Closure 02)
- `repository_transfer_mode`: `MANUAL_BROWSER_TEMPORARY_BRANCH`
- `marco_fast_forward_main_after_approval`: `PERMITTED`
- Repository read-only synchronization under `AUTH-0020`: `PERMITTED` if required. All other network activity: `PROHIBITED`.
- Neo push: `PROHIBITED`
- Remote branch creation by Neo: `PROHIBITED`
- Technical implementation: `PROHIBITED`
- Source changes: `PROHIBITED`
- Test-source changes: `PROHIBITED`
- Test execution: `PROHIBITED`
- Project imports: `PROHIBITED`
- Credentials: `PROHIBITED`
- Kalshi: `PROHIBITED`
- Polymarket: `PROHIBITED`
- Funding, orders, cancellations, paper trading, live trading: `PROHIBITED`
- Later phase: `PROHIBITED`
- Purpose: correct the authorization provenance and one stale artifact-index statement remaining after Closure 02's block, while preserving all otherwise-accurate Closure 01/02 content, per this exact dispatch.
- Grants new technical capability: `NO`
- Note: this entry does not claim that Closure 03 is already installed or accepted. Canonical effect, if any, occurs only after Marco's independent review, browser transfer, and any permitted non-force fast-forward. See `project_context/DECISION_LOG.md` entry `DEC-0028`.

## All non-bootstrap capabilities

All capabilities not explicitly listed as `PERMITTED` in an active, non-revoked entry above are `PROHIBITED`, including Kalshi Demo access, Kalshi production access, Polymarket interaction, credentials beyond the authorized GitHub push, account funding, order submission, cancellation, and trading.
