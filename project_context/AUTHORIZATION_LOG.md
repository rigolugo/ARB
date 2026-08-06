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

## All non-bootstrap capabilities

All capabilities not explicitly listed as `PERMITTED` in an active, non-revoked entry above are `PROHIBITED`, including Kalshi Demo access, Kalshi production access, Polymarket interaction, credentials beyond the authorized GitHub push, account funding, order submission, cancellation, and trading.
