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

## All non-bootstrap capabilities

All capabilities not explicitly listed as `PERMITTED` in an active, non-revoked entry above are `PROHIBITED`, including Kalshi Demo access, Kalshi production access, Polymarket interaction, credentials beyond the authorized GitHub push, account funding, order submission, cancellation, and trading.
