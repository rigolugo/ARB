# Documentation-Only Repository Bootstrap Specification

**Artifact:** `SPEC_repository_bootstrap_CANDIDATE_10.md`  
Candidate: CANDIDATE_10  
**Predecessor candidate:** `CANDIDATE_09` — blocked  
**Revision status:** `SUBMITTED_FOR_MARCO_REVIEW`  
**Date:** 2026-08-05  
**Authoring agent:** Bruno  
**Review authority:** Marco  
**Approval authority:** User  
**Canonical installation target if accepted:** `specifications/SPEC_repository_bootstrap.md`  
**Lifecycle status:** `SUBMITTED_FOR_MARCO_REVIEW`; not accepted; not canonical; not implementation authorization

---


## 1. Title, candidate identity, revision, and lifecycle

Candidate: CANDIDATE_10

**Title:** Documentation-Only Repository Bootstrap Specification  
**Candidate artifact:** `SPEC_repository_bootstrap_CANDIDATE_10.md`  
**Paired Bruno handoff:** `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`  
**Predecessor candidate:** `CANDIDATE_09` — blocked  
**Revision:** Candidate 10 bounded authorization-lineage completion correction  
**Date:** 2026-08-05  
**Scope class:** `REPOSITORY_BOOTSTRAP_SPECIFICATION_CANDIDATE_10_BOUNDED_CORRECTION_ONLY`  
**Target repository:** `rigolugo/ARB`  
**Required canonical `main`:** `da629e93ce9255c28ecb485ee2b67bfc0c0ccb86`  
**Lifecycle status at delivery:** `SUBMITTED_FOR_MARCO_REVIEW`  
**Canonical status:** Proposed, noncanonical, and non-authorizing

Candidate 10 is one bounded SPECIFICATION-ONLY correction to blocked Candidate 09. It corrects only Candidate 09’s three reviewed omissions: Section 28 acceptance criterion 31, the Section 12 authorization-inheritance halt condition, and Section 31.2 fixed decision 18.

Candidate 09 is Candidate 10’s immediate blocked predecessor. Candidate 08 is Candidate 09’s blocked predecessor. Candidate 07 is Candidate 08’s blocked predecessor. Candidate 06 is Candidate 07’s blocked predecessor. Candidate 05 is Candidate 06’s blocked predecessor.

Candidate 10 does not redesign or broaden any other Candidate 09 requirement.

### 1.1 Immediate blocked predecessor identity inspected

Candidate 10 was derived from these exact frozen Candidate 09 artifacts:

| Immediate predecessor artifact | Candidate | Lifecycle/disposition | Bytes | SHA-256 |
|---|---|---|---:|---|
| `SPEC_repository_bootstrap_CANDIDATE_09.md` | `CANDIDATE_09` | `SUBMITTED_FOR_MARCO_REVIEW`; blocked | `118801` | `641b6b01a0594aa5ea030252cb365364451b728928e8352d1be3d1223a35c3a9` |
| `HANDOFF_repository_bootstrap_spec_CANDIDATE_09.md` | `CANDIDATE_09` | `SUBMITTED_FOR_MARCO_REVIEW`; blocked | `16262` | `af57c69040976f62f0fb52a76e2c731cdae99b8a0e4c7a9433585de5265086db` |

Candidate 09 is Candidate 10’s immediate blocked predecessor. Candidate 08 is Candidate 09’s blocked predecessor. Candidate 07 is Candidate 08’s blocked predecessor. Candidate 06 is Candidate 07’s blocked predecessor. Candidate 05 is Candidate 06’s blocked predecessor.

Candidate 05 remains blocked and was submitted without a separately recorded explicit user authorization. Candidate 06 was prepared under valid explicit user authorization and remains blocked. Candidate 07 was submitted without a separately recorded explicit user authorization and remains blocked. Candidate 08 was prepared under valid explicit user authorization and remains blocked. Candidate 09 was prepared under valid explicit user authorization and remains blocked.

These identities establish the Candidate 10 correction input only. They do not authorize, validate, accept, canonicalize, broaden, unblock, or make Candidate 09 installable.

Any mismatch in either immediate-predecessor filename, raw byte length, or SHA-256 is a halt condition.

### 1.2 Candidate-number allocation rules

1. Marco is the sole allocator of candidate identifiers for this repository-bootstrap specification workstream.
2. Bruno shall not invent, select, reserve, reuse, or retrospectively alter a candidate identifier.
3. Each new or corrected submission receives the next unused sequential candidate number allocated by Marco.
4. Candidate identifiers are never reused, retrospectively renumbered, or overwritten in place.
5. A candidate number may be skipped only through an explicit Marco record that states the skipped number and the reason.
6. The candidate-specific specification and Bruno handoff always share the same candidate number.
7. A correction to a frozen, submitted, reviewed, blocked, deferred, accepted, or otherwise dispositioned candidate requires a newly allocated candidate number.
8. Candidate-specific artifact filenames and metadata shall contain the allocated identifier exactly.
9. Marco allocated `CANDIDATE_10` as the next sequential candidate for this workstream.
10. Candidate 10 does not renumber or overwrite Candidate 09.
11. Candidate 09 is Candidate 10’s immediate blocked predecessor.
12. Candidate 08 is Candidate 09’s blocked predecessor.
13. Candidate 07 is Candidate 08’s blocked predecessor.
14. Candidate 06 is Candidate 07’s blocked predecessor.
15. Candidate 05 is Candidate 06’s blocked predecessor.

### 1.3 Candidate lifecycle status

A candidate under authoring may be `DRAFT_CANDIDATE`. Once its bytes are frozen and the specification and paired Bruno handoff are delivered to Marco, its status is `SUBMITTED_FOR_MARCO_REVIEW`.

Candidate 10 is delivered as `SUBMITTED_FOR_MARCO_REVIEW`.

- Delivery does not constitute Marco review.
- Delivery does not constitute user acceptance.
- Delivery does not make Candidate 10 canonical or authorizing.
- Marco’s `APPROVE` review, if issued, means only that the exact reviewed candidate is suitable to present to the user.
- Only the user may designate an exact identity-bound candidate as accepted.
- Candidate acceptance remains separate from implementation authorization.
- Acceptance must bind the exact candidate artifact identities defined in Section 8.
- Any byte change after submission requires a new Marco-allocated candidate number; Candidate 10 shall not be edited in place.
- A blocked, deferred, superseded, unverified, unaccepted, or identity-mismatched candidate shall not be installed at the canonical repository paths.

---

## 2. Authorization

### 2.1 Candidate 10 authorizing instruction

The user explicitly authorized Bruno in the current conversation to prepare `REPOSITORY_BOOTSTRAP_SPECIFICATION_CANDIDATE_10` under Marco’s exact bounded Candidate 10 correction scope and predecessor identities.

This Candidate 10 authorization is a new and distinct authorization event. It permits only:

- reading the canonical GitHub repository;
- reading the exact frozen Candidate 09 artifacts identified in Section 1.1;
- reading Marco’s Candidate 09 blocking review supplied as the controlling correction instruction;
- reading the user’s explicit Candidate 10 authorization; and
- producing exactly:
  - `SPEC_repository_bootstrap_CANDIDATE_10.md`;
  - `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`.

### 2.2 Authorization lineage and non-retroactivity

Candidate 05 was submitted without a separately recorded explicit user authorization and remains blocked.

Candidate 06 was prepared under a valid explicit user authorization and remains blocked.

Candidate 07 was submitted without a separately recorded explicit user authorization and remains blocked.

Candidate 08 was prepared under a valid explicit user authorization and remains blocked. Candidate 09 was prepared under a valid explicit user authorization and remains blocked. Candidate 09 is Candidate 10’s immediate blocked predecessor. Candidate 08 is Candidate 09’s blocked predecessor. Candidate 07 is Candidate 08’s blocked predecessor. Candidate 06 is Candidate 07’s blocked predecessor. Candidate 05 is Candidate 06’s blocked predecessor.

Candidate 10 authorization is distinct from:

- the original Candidate 01 specification authorization;
- Candidate 04 submission;
- Candidate 05 submission;
- Candidate 06 authorization and blocked submission;
- Candidate 07 submission;
- Candidate 08 authorization and blocked submission;
- Candidate 09 authorization and blocked submission;
- candidate acceptance; and
- any future bootstrap implementation authorization.

Candidate 10 authorization:

1. does not retroactively authorize Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
2. does not validate Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
3. does not accept Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
4. does not broaden Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
5. does not unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
6. does not alter Candidate 06’s, Candidate 08’s, or Candidate 09’s valid explicit authorization provenance;
7. does not amend, replace, broaden, or inherit from Candidate 01;
8. does not constitute candidate acceptance;
9. does not authorize repository implementation; and
10. does not authorize Neo.

The authorization history shall distinguish at least:

| Event | Correct treatment | Repository effect |
|---|---|---|
| Original Candidate 01 specification authorization | First historical specification authorization; limited to Candidate 01 | None |
| Candidate 04 submission | Submission/provenance event; no separately recorded explicit user authorization | None |
| Candidate 05 submission and block | Blocked submission; no separately recorded explicit user authorization | None |
| Candidate 06 correction authorization and block | Valid explicit bounded authorization for the two Candidate 06 external artifacts; Candidate 06 remains blocked | None |
| Candidate 07 submission and block | Blocked submission; no separately recorded explicit user authorization | None |
| Candidate 08 correction authorization and block | Valid explicit bounded authorization for the two Candidate 08 external artifacts; Candidate 08 remains blocked | None |
| Candidate 09 correction authorization and block | Valid explicit bounded authorization for the two Candidate 09 external artifacts; Candidate 09 remains blocked | None |
| Candidate 10 correction authorization | Explicit bounded authorization for the two Candidate 10 external artifacts only | None |
| Candidate acceptance | Separate future user decision binding exact candidate identities | None by itself |
| Future bootstrap implementation authorization | Separate future permission required before repository modification | None until explicitly granted and acted upon |

Authorization does not inherit across candidate identifiers. Candidate numbering, submission, Marco review, user candidate acceptance, implementation authorization, implementation, and implementation review are separate events.

### 2.3 Capability matrix for Candidate 10

| Capability | Status |
|---|---|
| Read canonical GitHub repository | `PERMITTED` |
| Read exact Candidate 09 artifacts | `PERMITTED` |
| Read Marco’s Candidate 09 blocking review | `PERMITTED` |
| Read the user’s Candidate 10 authorization | `PERMITTED` |
| Produce the two Candidate 10 external artifacts | `PERMITTED` |
| Other network access | `PROHIBITED` |
| Repository modifications | `PROHIBITED` |
| Branch creation | `PROHIBITED` |
| Repository commits or pushes | `PROHIBITED` |
| Pull requests, issues, or releases | `PROHIBITED` |
| Code changes | `PROHIBITED` |
| Test creation or execution | `PROHIBITED` |
| Project imports | `PROHIBITED` |
| Package installation | `PROHIBITED` |
| Subprocess or shell execution | `PROHIBITED` |
| Kalshi Demo reads or writes | `PROHIBITED` |
| Production reads or writes | `PROHIBITED` |
| Polymarket interaction | `PROHIBITED` |
| Credential use | `PROHIBITED` |
| Account funding | `PROHIBITED` |
| Order submission, amendment, or cancellation | `PROHIBITED` |
| Trading | `PROHIBITED` |
| Authorization of Neo | `PROHIBITED` |

Anything not explicitly marked `PERMITTED` is `PROHIBITED`.

### 2.4 Effect of Candidate 10

Candidate 10 is a frozen submission for Marco’s independent review. It is proposed, noncanonical, and non-authorizing. Repository implementation remains prohibited. It does not authorize:

- repository modification;
- branches, commits, pushes, pull requests, issues, or releases;
- implementation;
- code, tests, imports, package installation, subprocesses, or shell execution;
- network activity beyond reading the canonical GitHub repository;
- Demo or production access;
- Polymarket interaction;
- credentials;
- account funding;
- order submission, amendment, or cancellation;
- trading;
- Neo activity; or
- any later project phase.

The future implementation handoff described in this specification remains descriptive only. Marco may separately issue a candidate-specific implementation handoff only after:

1. Marco reviews the exact frozen Candidate 10 identities;
2. the user explicitly accepts the exact identity-bound Candidate 10;
3. the user separately and explicitly authorizes a bounded bootstrap implementation task; and
4. Marco issues the bounded implementation handoff with exact accepted-candidate bindings.

The later canonical installation target remains `handoffs/HANDOFF_repository_bootstrap_implementation.md`; Candidate 10 does not write that handoff.

---

## 3. Objective

Define the smallest complete, implementation-ready requirements for a documentation-only bootstrap of the canonical public repository.

The bootstrap shall establish:

- canonical project entry points;
- enforceable safety and authorization documents;
- explicit agent roles;
- current-state, decision, authorization, and artifact records;
- minimal trackable directories;
- public-repository secret protections;
- Demo/production separation requirements;
- monetary precision policy;
- a phase-gated development sequence; and
- reviewable, fail-closed approval rules.

The bootstrap shall leave `src/` and `tests/` empty except for the selected Git tracking placeholders.

---

## 4. Non-goals

This specification does not design, authorize, or implement:

- a complete trading platform;
- a strategy engine;
- market-making logic;
- arbitrage scanning;
- venue adapters;
- Kalshi or Polymarket API clients;
- authentication;
- credential loaders;
- endpoint configuration;
- order types;
- order submission;
- market-data schemas;
- event or ledger schemas;
- persistence code;
- tests or fixtures;
- CI/CD;
- package management;
- deployment;
- production read access;
- production write access;
- account funding;
- trading;
- profitability claims; or
- automatic progression to any later phase.

No later phase is authorized merely because it appears in the sequence in Section 26.

---

## 5. Current accepted state

### 5.1 Observed repository baseline

Bruno re-inspected the canonical GitHub repository on 2026-08-05 and observed:

| Attribute | Observed value |
|---|---|
| Repository | `rigolugo/ARB` |
| Visibility | Public |
| Default branch | `main` |
| HEAD commit | `da629e93ce9255c28ecb485ee2b67bfc0c0ccb86` |
| Commit message | `Initial commit` |
| Tracked tree | `README.md` only |
| `README.md` line 1 | `# ARB` |
| `README.md` line 2 | `Arbitrage research Project` |

The observed baseline matches the exact canonical state required by the Candidate 10 authorization. No baseline halt was triggered.

### 5.2 Preserved project direction

The bootstrap shall document the following project direction without implementing it:

- a venue-independent economic core only for genuinely shared economic concepts;
- a separate Kalshi adapter;
- a separate Polymarket adapter;
- Kalshi-first sequencing because Kalshi offers a Demo environment suitable for controlled, mock-funded execution work;
- incremental, evidence-gated development;
- no-live-trading by default; and
- no production writes without separate, explicit user authorization.

### 5.3 Current candidate and authorization state

At Candidate 10 delivery:

- Candidate 05 remains blocked and lacks a separately recorded explicit user authorization;
- Candidate 06 was validly authorized and remains blocked;
- Candidate 07 remains blocked and lacks a separately recorded explicit user authorization;
- Candidate 08 was validly authorized and remains blocked;
- Candidate 09 was validly authorized and remains blocked;
- Candidate 10 is `SUBMITTED_FOR_MARCO_REVIEW`, not accepted, not canonical, and not implementation authorization;
- only Bruno’s Candidate 10 SPECIFICATION-ONLY correction work is authorized;
- Candidate 10 authorization is distinct from Candidate 01, Candidate 04 submission, Candidate 05 submission, Candidate 06 authorization and blocked submission, Candidate 07 submission, Candidate 08 authorization and blocked submission, Candidate 09 authorization and blocked submission, candidate acceptance, and future implementation authorization;
- repository modification is prohibited;
- repository commit or push is prohibited;
- Neo is not authorized;
- no code, tests, imports, package installation, subprocess, or shell execution is authorized;
- no network access is authorized beyond reading the canonical GitHub repository;
- no Kalshi Demo or production access is authorized;
- no Polymarket interaction is authorized;
- no credentials, funding, orders, cancellations, or trading are authorized; and
- no blocked, superseded, or unaccepted candidate is automatically canonical.

### 5.4 Commit-time state decisions

The first documentation-bootstrap implementation shall apply all of these decisions:

1. `project_context/PROJECT_STATE.md` shall reflect the actual active bootstrap implementation authorization at commit time.
2. `project_context/AUTHORIZATION_LOG.md` shall preserve the original Candidate 01 authorization as the first historical specification authorization.
3. Candidate 04 shall remain a submission/provenance event without a separately recorded explicit user authorization.
4. Candidate 05 shall remain a blocked submission without a separately recorded explicit user authorization.
5. Candidate 06 shall remain a separately and validly authorized correction candidate that was later blocked.
6. Candidate 07 shall remain a blocked submission without a separately recorded explicit user authorization.
7. Candidate 08 shall remain a separately and validly authorized correction candidate that was later blocked.
8. Candidate 09 shall remain a separately and validly authorized correction candidate that was later blocked.
9. Candidate 10 authorization shall remain a new and distinct authorization event if Candidate 10 is accepted and installed.
10. Candidate acceptance shall remain separate from Candidate 10 authorization.
11. Any future bootstrap implementation authorization shall remain a further separate authorization event.
12. The existing root `README.md` shall remain unchanged.
13. The first bootstrap implementation shall include the four final task records listed in Section 7.2.
14. Only exact accepted-candidate bytes may be installed.
15. No blocked, superseded, unverified, or unaccepted candidate is automatically canonical.
16. No runtime, strategy, venue, credential, funding, order, cancellation, or trading phase is authorized by the bootstrap.

## 6. Terminology

| Term | Definition |
|---|---|
| **Canonical repository** | The public GitHub repository `rigolugo/ARB`. |
| **Candidate** | A numbered, external, reviewable artifact set that is not accepted or canonical merely because it exists. |
| **Accepted candidate** | The exact candidate explicitly accepted by the user after Marco review, bound by candidate ID, filename, byte length, and SHA-256. |
| **Candidate artifact identity** | The tuple `(candidate_id, source_filename, byte_length, sha256)` computed over exact raw file bytes. |
| **Canonical installation target** | The fixed generic repository path that receives an exact byte-for-byte copy of an accepted external artifact. |
| **Canonical document** | A tracked document designated as an authoritative source of project rules, state, decisions, roles, authorizations, or artifact references. |
| **Generated artifact** | Evidence or output produced by an execution, test, connectivity check, recorder, analysis, or other run. It is not authoritative merely because it exists. |
| **Accepted specification** | A specification reviewed by Marco and explicitly approved by the user for a bounded next action. |
| **Authorization** | Explicit user permission recorded with a bounded agent, task, path, capability, environment, and completion condition. |
| **Absent authorization** | Any capability not explicitly permitted. It resolves to `PROHIBITED`. |
| **Demo** | Kalshi’s non-production environment. Demo evidence does not establish production correctness, safety, liquidity, or profitability. |
| **Production read** | Authenticated or unauthenticated observation of production systems without state-changing operations. |
| **Production write** | Any production operation that can alter orders, positions, funds, account state, configuration, or venue state. |
| **Shadow execution** | Strategy evaluation using observed production data without sending orders. |
| **Economic core** | Venue-independent representations and calculations only where the economic meaning is genuinely shared. |
| **Venue adapter** | Venue-specific behavior, API shape, order semantics, fees, settlement, and market representation. |
| **Locked arbitrage** | A position whose required quantities are filled or contractually guaranteed and whose payout relationship has been verified at rule level, after relevant fees and costs. |
| **Fail closed** | Halt and prohibit the action when authorization, configuration, environment, state, or evidence is missing, ambiguous, malformed, stale, or contradictory. |
| **Material phase** | A project step that adds new technical capability, environment access, credentials, money movement, trading behavior, or strategy claims. |
| **Formal review** | Marco’s review beginning with exactly one approved review term defined in Section 22. |

---

## 7. Inputs and outputs

### 7.1 Candidate-stage inputs

Candidate 10 uses only:

1. the exact frozen Candidate 09 specification and handoff identified in Section 1.1;
2. Marco’s Candidate 09 blocking review supplied as the controlling correction instruction;
3. the user’s explicit Candidate 10 authorization;
4. the verified canonical repository baseline; and
5. every other Candidate 09 requirement preserved without redesign.

Candidate 05, Candidate 06, Candidate 07, and Candidate 08 artifacts and their reviews are not Candidate 10’s direct drafting inputs. Historical references to those candidates are retained only where needed to preserve accurate authorization and candidate lineage.

### 7.2 Required future bootstrap records and canonical targets

If Candidate 10 becomes the accepted candidate, the first documentation-bootstrap implementation shall install these exact source-to-target records:

| External source artifact | Role | Canonical repository target |
|---|---|---|
| `SPEC_repository_bootstrap_CANDIDATE_10.md` | Final user-accepted bootstrap specification | `specifications/SPEC_repository_bootstrap.md` |
| `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md` | Bruno’s corresponding final specification handoff | `handoffs/HANDOFF_repository_bootstrap_spec.md` |
| `REVIEW_repository_bootstrap_spec_CANDIDATE_10.md` | Marco’s corresponding approval review of the exact accepted candidate | `reviews/REVIEW_repository_bootstrap_spec.md` |
| `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md` | Marco’s later bounded implementation handoff | `handoffs/HANDOFF_repository_bootstrap_implementation.md` |

Candidate 10 produces only the first two external source artifacts. It does not write Marco’s review or implementation handoff.

If Candidate 10 is not accepted, none of its candidate-specific artifacts shall be installed. A later accepted candidate shall use its own candidate-specific source filenames and the same fixed canonical targets.

### 7.3 Permitted future bootstrap outputs

The first documentation-bootstrap implementation shall create exactly the authorized paths from this set:

```text
/
├── START_HERE.md
├── .gitignore
├── project_context/
│   ├── START_HERE.md
│   ├── GUARDRAILS.md
│   ├── PROJECT_STATE.md
│   ├── DECISION_LOG.md
│   ├── ARTIFACT_INDEX.md
│   ├── AGENT_ROLES.md
│   └── AUTHORIZATION_LOG.md
├── specifications/
│   └── SPEC_repository_bootstrap.md
├── handoffs/
│   ├── HANDOFF_repository_bootstrap_spec.md
│   └── HANDOFF_repository_bootstrap_implementation.md
├── reviews/
│   └── REVIEW_repository_bootstrap_spec.md
├── src/
│   └── .gitkeep
├── tests/
│   └── .gitkeep
└── artifacts/
    └── .gitkeep
```

The four canonical task records shall be exact byte-for-byte copies of the final accepted external source artifacts available before implementation.

The implementation shall not create `specifications/.gitkeep`, `handoffs/.gitkeep`, or `reviews/.gitkeep`.

`README.md` remains present and unchanged.

### 7.4 Output exclusions

The implementation shall not output:

- source code;
- test code;
- schemas;
- API clients;
- active configuration;
- credentials;
- environment files;
- logs;
- databases;
- downloaded data;
- account information;
- venue responses;
- trading evidence;
- generated strategy artifacts;
- blocked, superseded, unverified, or unaccepted candidates presented as canonical;
- placeholder files in `specifications/`, `handoffs/`, or `reviews/`; or
- any unlisted file.

---

## 8. Data types and precision rules

### 8.1 Authorization values

Every capability field in authorization records shall use one of:

- `PERMITTED`
- `PROHIBITED`

Where timing or lifecycle status is needed, it shall be a separate field and shall not replace the capability value.

Blank, missing, inherited, implied, or ambiguous capability values resolve to `PROHIBITED`.

### 8.2 Dates and identifiers

- Dates shall use ISO 8601 calendar format: `YYYY-MM-DD`.
- Datetimes, when needed later, shall include timezone offsets.
- Decision identifiers shall be stable and unique, for example `DEC-0001`.
- Authorization identifiers shall be stable and unique, for example `AUTH-0001`.
- Artifact identifiers shall be stable and unique, for example `ART-0001`.
- Specifications, reviews, and handoffs shall identify their revision and related authorization.

The implementation may choose a different stable prefix format only if Marco and the user approve it before bootstrap implementation.

### 8.3 Candidate artifact identity and byte binding

Every candidate artifact that may be accepted or installed shall have an external identity record containing:

- `candidate_id`: exact candidate identifier such as `CANDIDATE_10`;
- `source_filename`: exact candidate-specific filename;
- `byte_length`: exact number of raw file bytes;
- `sha256`: lowercase 64-hex SHA-256 of the exact raw file bytes.

Binding rules:

1. Byte length and SHA-256 are computed over the exact delivered bytes, without line-ending conversion, Unicode normalization, BOM insertion/removal, reformatting, or metadata rewriting.
2. An artifact shall not be required to contain its own final hash; self-hashing would create a circular identity. The exact identity is recorded externally in Marco’s review and later implementation records.
3. The **candidate acceptance identity table** shall bind the exact Candidate 10 specification and Bruno handoff identities.
4. Marco’s review shall contain that candidate acceptance identity table.
5. User acceptance shall identify `CANDIDATE_10` and explicitly accept the exact identity table in Marco’s review, or reproduce the same identities.
6. Any byte change to the specification or Bruno handoff after identity binding invalidates the candidate acceptance and requires a new candidate number.
7. A filename match without matching byte length and SHA-256 is insufficient.
8. A hash match under a different candidate ID or source filename is insufficient.
9. Before implementation, an **installation identity table** shall bind all four external source records: the accepted specification, Bruno handoff, Marco approval review, and Marco implementation handoff.
10. Marco’s implementation handoff may bind the first three finalized source records. Because it cannot safely self-hash, its own final byte length and SHA-256 shall be bound externally by the later implementation authorization or dispatch record after the handoff bytes are frozen.
11. The later implementation handoff shall restate the accepted candidate identity table and the source-to-canonical-target mapping.
12. The implementation shall verify each source artifact before copying and verify each canonical target after copying.
13. Each canonical target’s byte length and SHA-256 shall exactly equal its bound source artifact.
14. Any missing identity, mismatch, normalization, circular self-identity claim, or ambiguity halts the affected work.

### 8.4 Monetary precision policy

Future economic logic shall use decimal or fixed-point representations.

Binary floating-point arithmetic is prohibited for:

- prices;
- cash;
- fees;
- P&L;
- balances;
- order values;
- settlement amounts;
- quantities where venue units require exact precision;
- inventory cost basis; and
- incentive accounting.

Future specifications shall require:

1. explicit venue-native units;
2. explicit conversion boundaries;
3. documented rounding mode for each conversion;
4. no implicit rounding;
5. exact serialization and deserialization rules;
6. reconciliation against venue-reported values;
7. separate treatment of displayed, executable, maker, and taker prices;
8. separate accounting for gross edge, fees, slippage, adverse selection, forced-hedge cost, realized P&L, unrealized P&L, and confirmed incentives; and
9. no incentive recognition until confirmed.

This bootstrap selects no programming language or numeric library.

---

## 9. Repository interfaces

The repository bootstrap defines documentation interfaces, not software APIs.

### 9.1 Entry-point interface

A new reader or agent shall be able to start at root `START_HERE.md` and reach the current authorized state through the canonical read order.

### 9.2 Authorization interface

Before any task begins, the acting agent shall be able to identify:

- the controlling `GUARDRAILS.md`;
- the exact candidate and accepted artifact identity table;
- the exact task authorization entry;
- permitted paths;
- permitted network access;
- environment permissions;
- credential permissions;
- test permissions;
- artifact permissions;
- commit permissions;
- expiration or completion conditions; and
- revocation status.

Task-specific authorization is valid only within the current guardrails. Candidate authorizations do not inherit. If any required field is unavailable, contradictory, stale, mismatched, or inconsistent with `GUARDRAILS.md`, the task halts under the more restrictive interpretation.

### 9.3 Candidate-to-canonical specification interface

For Candidate 10:

- external candidate source: `SPEC_repository_bootstrap_CANDIDATE_10.md`;
- canonical installation target if accepted: `specifications/SPEC_repository_bootstrap.md`.

The canonical target shall be an exact byte-for-byte copy of the accepted source and shall retain Candidate 10 metadata. It shall be linked from:

- `project_context/PROJECT_STATE.md`;
- the active bootstrap authorization entry;
- `reviews/REVIEW_repository_bootstrap_spec.md`;
- `handoffs/HANDOFF_repository_bootstrap_spec.md`; and
- `handoffs/HANDOFF_repository_bootstrap_implementation.md`.

### 9.4 Review interface

Marco’s external review source for Candidate 10 shall be:

`REVIEW_repository_bootstrap_spec_CANDIDATE_10.md`

Its canonical installation target, if Candidate 10 is accepted, shall be:

`reviews/REVIEW_repository_bootstrap_spec.md`

The review shall:

- use exactly one formal decision term as its first non-whitespace text;
- place no title, heading, metadata, identity table, or explanation before that opening decision line;
- state `Candidate: CANDIDATE_10` after the opening decision line;
- bind the exact Candidate 10 specification and Bruno handoff identities after the opening decision line;
- identify the exact candidate reviewed;
- state whether the candidate is suitable to present to the user; and
- avoid implying that Marco’s review itself authorizes implementation.

Candidate 10 does not write that review.

### 9.5 Handoff interfaces

Candidate 10 defines:

- Bruno source: `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`;
- Bruno canonical target if accepted: `handoffs/HANDOFF_repository_bootstrap_spec.md`;
- Marco future source: `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md`;
- Marco canonical target if issued for the accepted candidate: `handoffs/HANDOFF_repository_bootstrap_implementation.md`.

The later Marco implementation handoff shall state `Candidate: CANDIDATE_10`, bind the accepted specification and Bruno handoff identities, identify the approval review, identify exact paths and permissions, and define evidence and stop conditions.

No handoff creates authorization. Candidate 10 does not write Marco’s review or implementation handoff.

### 9.6 Artifact index interface

Generated evidence is discoverable through `project_context/ARTIFACT_INDEX.md`; the index does not make evidence canonical, accepted, safe, or authorized.

---

## 10. State machine

### 10.1 Candidate lifecycle

```text
DRAFT_CANDIDATE
    -> SUBMITTED_FOR_MARCO_REVIEW
        -> BLOCKED
        -> DEFERRED
        -> NEEDS_VERIFICATION
        -> APPROVED_FOR_USER_DECISION
            -> USER_REJECTED
            -> USER_DEFERRED
            -> USER_ACCEPTED_EXACT_CANDIDATE
```

Allocation and transition rules:

- Marco is the sole allocator of candidate identifiers.
- A new or corrected submission receives the next unused sequential Marco-allocated candidate number.
- Candidate identifiers are never reused, retrospectively renumbered, or overwritten in place.
- A skipped number requires an explicit Marco record naming the number and reason.
- The specification and paired Bruno handoff share the same candidate identifier.
- Freezing and delivering both artifacts to Marco transitions the candidate to `SUBMITTED_FOR_MARCO_REVIEW`.
- `APPROVED_FOR_USER_DECISION` is not acceptance or implementation authorization.
- `USER_ACCEPTED_EXACT_CANDIDATE` requires exact candidate ID, filenames, byte lengths, and SHA-256 bindings.
- A byte change after submission requires a new candidate number and returns the corrected work to `DRAFT_CANDIDATE`.
- A blocked or superseded candidate never transitions to canonical installation.
- Candidate 10 is currently `SUBMITTED_FOR_MARCO_REVIEW`.

### 10.2 Project work-item states

```text
PROPOSED_SPEC
    -> MARCO_REVIEWED
        -> USER_REJECTED
        -> USER_DEFERRED
        -> USER_APPROVED_FOR_IMPLEMENTATION
            -> IMPLEMENTATION_IN_PROGRESS
                -> IMPLEMENTATION_HALTED
                -> IMPLEMENTATION_COMPLETE
                    -> MARCO_IMPLEMENTATION_REVIEWED
                        -> USER_REJECTED
                        -> USER_ACCEPTED
                        -> USER_AUTHORIZED_NEXT_PHASE
```

### 10.3 Transition requirements

| Transition | Required evidence |
|---|---|
| Candidate draft to Marco-reviewed | Marco review binding exact candidate identities |
| Marco-approved candidate to user-accepted candidate | Explicit user acceptance of the exact identity-bound candidate |
| `PROPOSED_SPEC -> MARCO_REVIEWED` | Marco review whose first non-whitespace text is exactly one formal decision term, followed by candidate identity and hash information |
| `MARCO_REVIEWED -> USER_APPROVED_FOR_IMPLEMENTATION` | Explicit user approval of a bounded implementation task, separate from candidate acceptance |
| `USER_APPROVED_FOR_IMPLEMENTATION -> IMPLEMENTATION_IN_PROGRESS` | Active implementation authorization plus Marco’s issued bounded implementation handoff |
| `IMPLEMENTATION_IN_PROGRESS -> IMPLEMENTATION_COMPLETE` | Authorized path diff, identity verification, and required evidence |
| `IMPLEMENTATION_COMPLETE -> MARCO_IMPLEMENTATION_REVIEWED` | Independent Marco review |
| `MARCO_IMPLEMENTATION_REVIEWED -> USER_ACCEPTED` | Explicit user acceptance |
| Any active state `-> IMPLEMENTATION_HALTED` | A halt condition or authorization revocation |

No transition may be inferred from silence, prior candidate authorization, prior candidate acceptance, repository access, technical feasibility, or a previous phase’s authorization.

---

## 11. Invariants

1. The user is the sole approval authority.
2. `project_context/GUARDRAILS.md` is the highest standing operational authority.
3. Exact user authorization determines task-specific permission only within the current guardrails.
4. Ordinary task authorization cannot override a permanent guardrail.
5. A guardrail remains controlling until the complete amendment process in Section 21.2 has been completed.
6. Marco’s review does not itself authorize implementation.
7. Bruno does not authorize himself or Neo.
8. Neo acts only against a Marco-reviewed, user-approved specification and separately issued bounded implementation handoff.
9. Anything not explicitly permitted is prohibited.
10. Technical capability, repository permission, credentials, or network access do not constitute authorization.
11. Demo and production are structurally and operationally distinct.
12. No environment silently falls back to another environment.
13. Production writes remain prohibited unless separately and explicitly authorized by the user within the guardrails.
14. No live trading is permitted by default.
15. Demo results are not production evidence.
16. Similarly named markets are not assumed economically equivalent without rule-level payout verification.
17. A two-leg position is not locked arbitrage until required quantities are filled or contractually guaranteed and payout equivalence is verified.
18. Economic values do not use binary floating point.
19. Incentives are not counted until confirmed.
20. Generated artifacts are not canonical decisions.
21. `PROJECT_STATE.md` cannot authorize work.
22. `DECISION_LOG.md` records decisions but does not replace a capability-specific authorization entry.
23. An expired, revoked, stale, ambiguous, contradictory, or guardrail-conflicting authorization fails closed.
24. Scope cannot expand silently.
25. No bootstrap file may imply that later sequence items are authorized.
26. No bootstrap document may authorize Neo under this task.
27. The public repository shall contain no secrets, credentials, private URLs, account data, or sensitive operational evidence.
28. The implementation diff shall be reviewable path by path.
29. The first bootstrap implementation shall adopt the exact four final task records required by Section 7.2.
30. The blocked draft shall not be treated as canonical merely because it preceded the final revision.

---

## 12. Failure and halt conditions

The later bootstrap implementation shall halt before modifying or committing anything if:

- the repository cannot be read;
- repository identity is ambiguous;
- visibility is not public as expected;
- default branch is not `main`;
- HEAD differs from the user-approved implementation baseline;
- the tree differs materially from the approved baseline;
- the candidate identifier was not allocated by Marco;
- the candidate is not the next unused sequential number and no explicit Marco skip record names the skipped number and reason;
- the specification and Bruno handoff do not share the same candidate number;
- a candidate identifier was reused, retrospectively renumbered, or overwritten in place;
- the accepted candidate is not identified by candidate ID, exact source filenames, byte lengths, and SHA-256 values;
- the first non-whitespace text of Marco’s review is not exactly one formal decision term;
- any title, heading, metadata, identity table, hash, or explanation appears before the opening decision line;
- Marco’s review does not bind the exact specification and Bruno handoff identities;
- user acceptance does not identify or incorporate the exact accepted-candidate identity table;
- any candidate source filename, candidate metadata, byte length, or SHA-256 mismatches;
- any source-to-canonical copy changes bytes, line endings, Unicode form, BOM state, or formatting;
- Candidate 05 is represented as having a separately recorded explicit user authorization;
- Candidate 05 is represented as separately authorized, validated, accepted, broadened, or made canonical;
- Candidate 06 is represented as accepted, canonical, or unblocked by Candidate 10;
- Candidate 08 is represented as accepted, canonical, or unblocked by Candidate 10;
- Candidate 09 is not represented as Candidate 10’s immediate blocked predecessor;
- Candidate 09 is represented as accepted, canonical, or unblocked by Candidate 10;
- Candidate 10 authorization is being treated as retroactively authorizing, validating, accepting, broadening, unblocking, canonicalizing, or making installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
- the original Candidate 01 authorization, Candidate 04 submission, Candidate 05 submission, Candidate 06 authorization, Candidate 07 submission, Candidate 08 authorization, or Candidate 09 authorization or submission is being treated as authorization for Candidate 10;
- the Candidate 10 correction authorization is being treated as candidate acceptance or repository implementation authorization;
- the user has not explicitly approved implementation;
- the implementation agent lacks an active authorization entry;
- Marco’s final approval review is absent from `reviews/REVIEW_repository_bootstrap_spec.md`;
- Marco’s bounded implementation handoff is absent from `handoffs/HANDOFF_repository_bootstrap_implementation.md`;
- the final user-approved specification or Bruno handoff is unavailable at the required canonical source material;
- any of the four required task records is blocked, superseded, incomplete, mismatched by candidate, or mismatched by bound identity;
- the implementation would place `.gitkeep` in `specifications/`, `handoffs/`, or `reviews/`;
- instructions conflict;
- a required path is outside the authorization;
- an existing file would be overwritten without explicit approval;
- `README.md` would be modified;
- repository modification would require code or tests;
- a secret, credential-like value, private endpoint, account identifier, wallet, log, database, or generated trading artifact is detected;
- Demo and production cannot be distinguished safely;
- an environment field is missing or contradictory;
- a requirement would silently authorize later work;
- an ordinary task authorization conflicts with `GUARDRAILS.md`;
- a purported guardrail amendment has not completed every step in Section 21.2;
- source-of-truth conflicts cannot be resolved under the guardrail-first rule;
- any canonical record is stale or ambiguous;
- `PROJECT_STATE.md` would not reflect the actual active bootstrap implementation authorization at commit time; or
- the agent cannot distinguish a specification requirement from implementation design.

On halt, the agent shall:

1. apply the more restrictive interpretation;
2. make no additional modifications;
3. not broaden the task;
4. preserve available evidence;
5. report exact observed versus expected state;
6. identify the exact conflicting or missing records;
7. identify any already-created uncommitted files;
8. state whether cleanup is required; and
9. return control to Marco and the user.

---

## 13. Logging and audit requirements

### 13.1 Bootstrap implementation evidence

A future implementation shall return, without creating runtime logs:

- pre-change repository identity, visibility, branch, and HEAD;
- pre-change file tree;
- Marco’s candidate-allocation record or sequence evidence showing that the accepted candidate used the next unused sequential number;
- any explicit Marco skip record applicable to an omitted candidate number;
- confirmation that the specification and Bruno handoff share the same candidate number;
- confirmation that the formal review’s first non-whitespace text is exactly one formal decision term and that identity/hash information follows it;
- accepted candidate identity table;
- candidate-specific source-to-canonical-target mapping;
- pre-copy and post-copy byte-length and SHA-256 comparison;
- exact changed-path list;
- post-change file tree;
- confirmation that the exact four final task records were adopted at their required paths;
- exact revision/identity mapping among the final specification, Bruno handoff, Marco approval review, user authorization, and Marco implementation handoff;
- confirmation that no blocked or superseded draft was adopted as canonical;
- content checklist results for every canonical document;
- guardrail-first precedence consistency results;
- secret-pattern inspection result;
- confirmation that `specifications/`, `handoffs/`, and `reviews/` contain the required real files and no `.gitkeep`;
- confirmation that `src/`, `tests/`, and `artifacts/` contain only `.gitkeep`;
- confirmation that no tests were created or executed;
- confirmation that no venue, credential, funding, order, cancellation, or trading access occurred;
- final diff;
- final commit SHA only if commit permission was explicitly granted; and
- `git status` or equivalent evidence showing the final workspace state.

### 13.2 Canonical audit records

The bootstrap shall establish three distinct governance record types:

- `project_context/DECISION_LOG.md`: append-only decisions;
- `project_context/AUTHORIZATION_LOG.md`: append-only capability permissions and revocations;
- `project_context/ARTIFACT_INDEX.md`: references to generated or external evidence.

The bootstrap shall also adopt the four task records in Section 7.2 as immutable revisioned canonical records. These records shall not be merged with the governance logs because specifications, reviews, handoffs, decisions, authorizations, and artifacts have different authority and lifecycle semantics.

### 13.3 Public-repository audit boundary

No audit evidence containing secrets, credentials, private URLs, account data, wallet identifiers, sensitive balances, raw venue responses, or personal data may be committed.

Sanitized evidence may be committed only case by case under a later explicit authorization.

---

## 14. Persistence and restart behavior

This bootstrap defines documentation persistence only.

### 14.1 Canonical persistence

- Canonical governance documents are tracked in Git.
- Candidate-specific external artifacts are not canonical merely because they exist.
- The first bootstrap commit shall contain the fixed canonical targets:
  - `specifications/SPEC_repository_bootstrap.md`;
  - `handoffs/HANDOFF_repository_bootstrap_spec.md`;
  - `reviews/REVIEW_repository_bootstrap_spec.md`; and
  - `handoffs/HANDOFF_repository_bootstrap_implementation.md`.
- Each canonical target shall be an exact byte-for-byte copy of the corresponding final accepted external candidate artifact.
- Candidate ID, source filename, byte length, and SHA-256 shall be preserved in review, authorization, state, and implementation evidence.
- A blocked, superseded, unverified, or unaccepted candidate is not canonical.
- Append-only records are changed through additive entries; historical entries are not silently rewritten.
- Marco allocates the next unused sequential candidate number for every correction; candidate identifiers are never reused, retrospectively renumbered, or overwritten in place. A skipped number requires an explicit Marco record naming the number and reason.
- `PROJECT_STATE.md` is a current snapshot and shall reflect the actual active bootstrap implementation authorization and exact accepted candidate at commit time.
- The original Candidate 01 SPECIFICATION-ONLY authorization remains the first historical specification authorization entry.
- Candidate 04 remains a submission/provenance event without a separately recorded explicit user authorization.
- Candidate 05 remains Candidate 06’s blocked predecessor submission without a separately recorded explicit user authorization and is not converted into an authorization entry.
- Candidate 06 correction authorization remains a distinct valid historical authorization entry despite Candidate 06 being blocked. Candidate 07 remains a blocked submission without separately recorded explicit authorization. Candidate 08 correction authorization remains a distinct valid historical authorization entry despite Candidate 08 being blocked. Candidate 09 correction authorization remains a distinct valid historical authorization entry despite Candidate 09 being blocked. Candidate 10 correction authorization is a separate later historical authorization entry if Candidate 10 is accepted and installed; it does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09.
- Candidate acceptance and active bootstrap implementation authorization are further separate events.
- Accepted specifications, reviews, and handoffs are retained as immutable identity-bound records unless the user explicitly approves removal.
- `.gitkeep` is absent from `specifications/`, `handoffs/`, and `reviews/` once their required real files are present.
- `.gitkeep` remains in `src/`, `tests/`, and `artifacts/` during this bootstrap.

### 14.2 Restart protocol for agents

An agent resuming work shall:

1. read the canonical sequence in Section 20;
2. treat `project_context/GUARDRAILS.md` as the highest standing operational authority;
3. verify repository identity and HEAD;
4. identify the exact accepted candidate;
5. retrieve the bound candidate ID, source filenames, byte lengths, and SHA-256 values;
6. verify all four canonical task records against their bound source identities and target mapping;
7. identify the exact active user authorization;
8. distinguish the original Candidate 01 authorization, Candidate 04 submission, Candidate 05 blocked submission without separately recorded explicit user authorization, Candidate 06 valid correction authorization and blocked submission, Candidate 07 blocked submission without separately recorded explicit user authorization, Candidate 08 valid correction authorization and blocked submission, Candidate 09 valid correction authorization and blocked submission, Candidate 10 correction authorization, candidate acceptance, and active implementation authorization;
9. verify that Candidate 05 and Candidate 07 remain blocked and are not represented as separately authorized, validated, accepted, broadened, unblocked, canonicalized, made installable, or retroactively authorized by Candidate 10; verify separately that Candidate 06’s, Candidate 08’s, and Candidate 09’s explicit authorization provenance is preserved while all three remain blocked;
10. verify Marco’s candidate-number allocation, same-number specification/handoff pairing, and any explicit skip record;
11. verify that no prior candidate authorization is being inherited;
12. verify that the active authorization operates only within current guardrails;
13. verify that the active authorization is not expired or revoked;
14. verify that `PROJECT_STATE.md` matches the active authorization and accepted candidate;
15. verify that the formal review begins with exactly one decision term as its first non-whitespace text and places identity information afterward;
16. compare guardrails, state, authorization, decisions, roles, specification, review, handoffs, and identity records for contradiction or staleness;
17. apply the more restrictive interpretation and halt on any conflict, ambiguity, stale record, or identity mismatch; and
18. resume only the bounded authorized task.

Conversation memory, prior chat summaries, blocked drafts, filenames without identity bindings, or agent statements cannot replace this restart protocol.

### 14.3 Future runtime persistence

No runtime ledger, state database, recovery snapshot, or reconciliation store is designed or authorized here. Later specifications must define those separately.

---

## 15. Security boundaries

### 15.1 Public repository warning

Both entry points shall prominently state that the repository is public.

### 15.2 Prohibited repository content

The repository shall not contain:

- `.env` files other than deliberately tracked examples;
- real credentials;
- private keys;
- certificates containing private material;
- account identifiers;
- funding details;
- wallet secrets;
- copied environment values;
- private or signed URLs;
- venue tokens;
- raw sensitive logs;
- local databases;
- recovery snapshots;
- downloaded account or trading data;
- generated trading/account artifacts; or
- personal data.

### 15.3 Access is not authorization

Repository admin or write capability, environment reachability, possession of credentials, and technical ability to submit orders do not authorize use.

### 15.4 Credential boundary

The bootstrap creates no credential file, loader, namespace, or active configuration. Future credentials shall be:

- environment-specific;
- stored outside the public repository;
- least-privileged;
- explicitly authorized;
- never shared between Demo and production;
- never logged;
- never included in artifacts; and
- revocable without code changes.

### 15.5 Funding and trading boundary

Account funding, money movement, order submission, cancellation, and production writes remain prohibited until separately authorized by the user with explicit capability fields.

---

## 16. Test requirements

No test code may be created or executed under the current task or the documentation-only bootstrap unless a later user authorization explicitly permits documentation validation commands.

A later bootstrap implementation shall satisfy requirements using deterministic inspection, not application tests.

Permitted validation categories, only when included in the bounded implementation authorization, are:

- path existence checks;
- Markdown heading and required-section checks;
- exact phrase/policy checks;
- link/path consistency checks;
- authorization-value completeness checks;
- tree-scope checks;
- secret-pattern checks; and
- Git status/diff inspection.

These checks shall not import or execute project source code, contact networks, access venues, or use credentials.

---

## 17. Proposed repository tree

```text
/
├── README.md
├── START_HERE.md
├── .gitignore
├── project_context/
│   ├── START_HERE.md
│   ├── GUARDRAILS.md
│   ├── PROJECT_STATE.md
│   ├── DECISION_LOG.md
│   ├── ARTIFACT_INDEX.md
│   ├── AGENT_ROLES.md
│   └── AUTHORIZATION_LOG.md
├── specifications/
│   └── SPEC_repository_bootstrap.md
├── handoffs/
│   ├── HANDOFF_repository_bootstrap_spec.md
│   └── HANDOFF_repository_bootstrap_implementation.md
├── reviews/
│   └── REVIEW_repository_bootstrap_spec.md
├── src/
│   └── .gitkeep
├── tests/
│   └── .gitkeep
└── artifacts/
    └── .gitkeep
```

### 17.1 Canonical task-record adoption

The first bootstrap implementation shall place the final versions available before implementation at the exact paths shown above:

- final user-approved bootstrap specification;
- Bruno’s corresponding final handoff;
- Marco’s corresponding approval review;
- Marco’s later bounded implementation handoff.

The blocked draft is not automatically canonical.

### 17.2 Tracking mechanism

`.gitkeep` is selected only for structural directories that remain empty in the first bootstrap implementation:

- `src/`;
- `tests/`; and
- `artifacts/`.

Rules:

- `.gitkeep` has no authority or semantic content.
- `specifications/`, `handoffs/`, and `reviews/` shall not contain `.gitkeep` because each contains real files in the first bootstrap commit.
- When any future placeholder directory receives its first real tracked file, `.gitkeep` shall be removed in the same approved change unless a documented tool constraint requires otherwise.
- No additional directory README files are added in this bootstrap.
- Existing root `README.md` remains unchanged.

---

## 18. Per-directory requirements

| Directory | Authoritative purpose | Allowed content in first bootstrap | Prohibited content | Proposer/modifier | Approval | Git tracking | Generated-content policy |
|---|---|---|---|---|---|---|---|
| `/` | Repository navigation and global safety entry | Existing unchanged `README.md`, root `START_HERE.md`, `.gitignore` | Secrets, runtime data, duplicated detailed state, active configs, README changes | Bruno may specify; implementation agent may modify only under bounded authorization | Explicit user approval for each material change | Normal tracked files | Generated content prohibited |
| `project_context/` | Canonical governance and current-state documents | The seven required canonical Markdown documents | Code, tests, raw artifacts, credentials, chat transcripts, informal notes | Bruno proposes structures; Marco reviews; authorized implementation agent writes | User approval required | All canonical files committed | Generated content prohibited |
| `specifications/` | Canonical accepted specifications | Exactly `SPEC_repository_bootstrap.md`, containing the exact byte-for-byte copy of the accepted candidate source | `.gitkeep`, blocked drafts presented as canonical, code, implementation artifacts | Bruno authors; authorized implementation agent adopts the approved record | User approval of specification and path-specific implementation authorization | Real file committed in first bootstrap | Specification is canonical only after user approval and adoption |
| `handoffs/` | Canonical bounded task handoffs | Exactly `HANDOFF_repository_bootstrap_spec.md` and `HANDOFF_repository_bootstrap_implementation.md`, each mapped from its exact candidate-specific source | `.gitkeep`, general brainstorming, credentials, unbounded requests | Bruno authors the spec handoff; Marco authors the implementation handoff; authorized implementation agent adopts both | User authorization required before implementation handoff can be acted upon | Real files committed in first bootstrap | Sensitive evidence excluded |
| `reviews/` | Independent formal review records | Exactly `REVIEW_repository_bootstrap_spec.md`, containing Marco’s final approval review | `.gitkeep`, implementation, authorization by implication, unstructured chat dumps | Marco authors; authorized implementation agent adopts | User decides downstream authorization | Real file committed in first bootstrap | Review committed; raw tool logs excluded |
| `src/` | Future production or research source code | `.gitkeep` only | All code, adapters, clients, schemas, loaders, engines, trading logic | Neo or another implementation agent only under later authorization | Separate user approval | `.gitkeep` committed | Generated code prohibited |
| `tests/` | Future automated tests and approved fixtures | `.gitkeep` only | Test code, live tests, credential-bearing fixtures, downloaded venue data | Neo or authorized test agent only under later authorization | Separate user approval | `.gitkeep` committed | Test outputs ignored; sanitized fixtures case by case |
| `artifacts/` | Future local generated-evidence location indexed by `ARTIFACT_INDEX.md` | `.gitkeep` only | Credentials, private URLs, account data, raw sensitive logs, local DBs, unapproved trading data | Producing agent only within task authorization | Case-by-case user approval to commit any artifact | `.gitkeep` committed | Generated contents ignored by default |

### 18.1 Directory ownership rules

- “Proposer” means the agent may draft a change for review; it does not imply write authorization.
- No agent has standing modification authority.
- Every material update requires an active authorization entry operating within `GUARDRAILS.md`.
- The more restrictive rule controls if a directory rule conflicts with another record, and the affected work halts.
- `project_context/` remains canonical and must not become a generated-evidence store.
- The exact task-record paths in this section are implementation-critical and not open to substitution without a separately approved revision.

---

## 19. Required document specifications

### 19.1 Root `START_HERE.md`

**Purpose:** Concise repository entry point and routing document.

**Authority level:** Canonical entry point, subordinate to permanent guardrails and explicit authorization records.

**Required sections:**

1. Repository identity
2. Public repository warning
3. Safety defaults
4. Current authorized phase
5. Canonical read order
6. Prohibited sensitive content
7. Authorization statement
8. Demo evidence limitation
9. Approval authority

**Required initial content:**

- Identify `rigolugo/ARB` as the canonical repository.
- State prominently: **This repository is public.**
- State the no-live-trading default.
- State that technical capability does not constitute authorization.
- Prohibit credentials, keys, tokens, private URLs, account data, and sensitive artifacts.
- Direct readers to `project_context/START_HERE.md`.
- Provide the canonical read order by exact path, including the four canonical bootstrap task records.
- Summarize the current phase as documentation bootstrap only.
- State that Demo evidence is not production evidence.
- Identify the user as sole approval authority.
- State that absent authorization means prohibited.

**Update process:** Proposed by Bruno or Marco, independently reviewed by Marco, explicitly approved by the user, then changed by an authorized implementation agent.

**Relationship:** Routes to detailed canonical documents and shall not duplicate their full content.

**Conflict rule:** `GUARDRAILS.md` controls as the highest standing operational authority. Exact user authorization supplies task-specific permission only within those guardrails. Any conflict, ambiguity, or stale record uses the more restrictive interpretation and halts.

---

### 19.2 `project_context/START_HERE.md`

**Purpose:** Detailed orchestration and restart entry point.

**Authority level:** Canonical navigation and workflow authority; it does not grant capabilities.

**Required sections:**

1. Purpose
2. Canonical read order
3. Source-of-truth hierarchy
4. Agent workflow
5. Phase-gated process
6. Current phase
7. Record locations
8. Pre-task checks
9. Absent-authorization rule
10. Stale/conflicting document procedure
11. Formal review vocabulary pointer

**Required initial content:**

- List the exact canonical read order in Section 20, including all four canonical bootstrap task records.
- Define the precedence and halt rules in Section 21.
- Describe the ten-step gated agent workflow from `AGENT_ROLES.md`.
- State current project phase and active authorization.
- Identify the exact bootstrap records at `specifications/SPEC_repository_bootstrap.md`, `reviews/REVIEW_repository_bootstrap_spec.md`, `handoffs/HANDOFF_repository_bootstrap_spec.md`, and `handoffs/HANDOFF_repository_bootstrap_implementation.md`, and explain where later specifications, reviews, handoffs, decisions, authorizations, and artifact references live.
- Require repository identity, HEAD, active authorization, scope, path, environment, and revocation checks before work.
- State that absent authorization means prohibited.
- Require halt and Marco/user escalation on stale or conflicting documents.
- Clarify that conversation context is non-canonical.

**Update process:** Same approval workflow as root `START_HERE.md`.

**Relationship:** Detailed router to all canonical governance records.

**Conflict rule:** It cannot weaken `GUARDRAILS.md` or create authority absent from the exact active user authorization. Ordinary authorization cannot override a permanent guardrail.

---

### 19.3 `project_context/GUARDRAILS.md`

**Purpose:** Enforceable permanent safety, economic correctness, authorization, and scope rules.

**Authority level:** Highest standing repository safety authority. It can be changed only by an explicit user-approved guardrail change.

**Required sections:**

1. Permanent versus phase-specific rules
2. Authorization and approval
3. No-live-trading default
4. Demo/production separation
5. Venue separation
6. Credentials and secrets
7. Public repository boundary
8. Funding and production write prohibitions
9. Economic correctness
10. Monetary precision
11. Reconciliation and idempotency expectations
12. Risk and halt controls
13. Scope control
14. Conflict and fail-closed rules

**Required permanent guardrails:**

- No-live-trading default.
- Fail-closed authorization.
- User approval gates.
- Structural Demo/production separation.
- Venue-specific behavior remains in adapters.
- Credentials and secrets never committed.
- Public-repository warning.
- Access and technical capability do not imply authorization.
- Account funding prohibited without explicit authorization.
- Production writes prohibited without separate explicit authorization.
- Demo results are not proof of production safety or profitability.
- No strategy is “arbitrage” until required legs are filled or contractually locked and relevant payout rules are verified.
- Rule-level payout verification is required before treating similarly named markets as economically equivalent.
- Decimal or fixed-point economic arithmetic.
- Future execution requires idempotency keys where supported, exact fill/order reconciliation, and explicit venue truth sources.
- Risk limits, emergency cancellation, and halt controls fail closed.
- No silent scope expansion.
- Confirmed incentives only.
- Fees, slippage, adverse selection, and forced-hedge cost are separated from gross edge.

**Phase-specific status:** Must not be embedded as permanent truth. Current permissions and phase status belong in `PROJECT_STATE.md` and `AUTHORIZATION_LOG.md`.

**Update process:** Bruno or Marco may propose. Marco reviews. User must explicitly approve a guardrail revision. Implementation requires separate path authorization.

**Conflict rule:** A state document, specification, handoff, implementation, artifact, or agent statement cannot silently weaken a permanent guardrail. Conflict halts.

---

### 19.4 `project_context/PROJECT_STATE.md`

**Purpose:** Structured, current snapshot of accepted project status.

**Authority level:** Canonical current-state record; not an authorization source.

**Required sections:**

1. Repository identity and baseline commit
2. Current phase
3. Current authorization state
4. Completed and accepted work
5. Open work
6. Blocked work
7. Deferred work
8. Unresolved assumptions
9. Active accepted specification
10. Latest accepted implementation
11. Latest verified test evidence
12. Environment authorization matrix
13. Explicit next user decision
14. Last updated and approving authority
15. Staleness check

**Required initial content at specification stage:**

- Repository `rigolugo/ARB`.
- Baseline commit `da629e93ce9255c28ecb485ee2b67bfc0c0ccb86`.
- Current phase: documentation-bootstrap specification.
- Current authorization: Bruno Candidate 10 SPECIFICATION-ONLY correction authorization, distinct from Candidate 09’s valid authorization and blocked submission.
- Repository modifications: not approved.
- Completed accepted implementation: none.
- Active accepted specification candidate ID and exact artifact identity: none during the Candidate 10 correction task; Candidate 10 is `SUBMITTED_FOR_MARCO_REVIEW` and not canonical. At bootstrap commit time, identify the exact accepted candidate ID, source filename, byte length, SHA-256, and `specifications/SPEC_repository_bootstrap.md` as the canonical target.
- Latest test evidence: none.
- All venue, credential, funding, and trading capabilities prohibited.
- Next user decision after Marco review: accept, reject, narrow, or defer the exact identity-bound Candidate 10. Any implementation authorization is a later, separate decision.
- Last-updated date and approving authority; pending content shall not claim user approval.

**Required commit-time update:**

If the user later approves bootstrap implementation, the implementation shall update the state to the exact active bootstrap authorization, accepted candidate ID and bound identities, and the exact canonical specification, review, Bruno handoff, and Marco implementation handoff paths. It shall still state that no code, tests, venue access, production writes, or trading phases are authorized.

**Update process:** Marco proposes the state transition; authorized agent updates; user approval is required for material phase or authorization changes.

**Conflict rule:** `PROJECT_STATE.md` cannot override `GUARDRAILS.md` or create authorization. If it disagrees with guardrails or the authorization ledger, use the more restrictive interpretation and halt until corrected.

---

### 19.5 `project_context/DECISION_LOG.md`

**Purpose:** Append-only record of project decisions.

**Authority level:** Canonical decision history; decisions do not grant capabilities unless separately authorized.

**Required entry schema:**

- Decision ID
- Candidate ID, if candidate-specific
- Bound artifact identities, if acceptance-related
- Date
- Decision
- Status
- Rationale
- Evidence or reviewed artifact
- Scope affected
- Superseded decisions
- User approval reference
- Authorizes further work: `YES` or `NO`

**Required initial decisions:**

- User is sole approval authority.
- Marco is orchestrator and independent reviewer.
- Bruno is specification author.
- Neo is implementation/test agent only when separately authorized.
- Development is incremental and phase gated.
- Kalshi-first direction.
- Venue-independent economic core plus separate venue adapters.
- No-live-trading default.
- Demo evidence is not production evidence.
- Absent authorization means prohibited.
- Marco is the sole allocator of candidate identifiers for this workstream.
- Candidate numbers are sequential, immutable, non-reusable, and skippable only by an explicit Marco record naming the number and reason.
- The specification and Bruno handoff share the same candidate number.
- Candidate 04 remains a submission/provenance event without a separately recorded explicit user authorization.
- Candidate 05 was submitted without a separately recorded explicit user authorization and remains blocked.
- Candidate 06 was separately and validly authorized but remains blocked.
- Candidate 07 was submitted without a separately recorded explicit user authorization and remains blocked.
- Candidate 08 was separately and validly authorized but remains blocked.
- Candidate 09 was separately and validly authorized but remains blocked.
- Candidate 10 authorization is distinct from prior candidate events.
- Candidate 10 does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09.
- A delivered frozen candidate has status `SUBMITTED_FOR_MARCO_REVIEW`.
- Formal Marco reviews place exactly one decision term as the first non-whitespace text, with candidate identity and hashes afterward.

No entry may invent an approval reference. Unapproved proposals shall be labeled `PROPOSED` or omitted from accepted decision history, according to the user-approved implementation plan.

**Update process:** Append-only. Corrections and supersessions use new entries.

**Conflict rule:** A decision cannot override `GUARDRAILS.md`, expand exact task authorization, or replace a detailed authorization entry.

### 19.6 `project_context/ARTIFACT_INDEX.md`

**Purpose:** Canonical index of artifacts; not an artifact store.

**Authority level:** Canonical locator and classification record only.

**Required columns or fields:**

- Artifact ID
- Path or external location
- Producing task
- Producing agent
- Creation date
- Source commit or run ID
- Environment classification
- Generated versus canonical status
- Sensitivity classification
- Review state
- Retention or ignore policy
- Related specification
- Related test run or evidence

**Required initial content:**

- State that no trading, connectivity, environment, or test artifacts exist.
- State that `.gitkeep` is not an artifact.
- State that unindexed local artifacts have no accepted status.
- State that indexing does not authorize creation, retention, or commit.

**Update process:** Producing agent proposes an entry only if artifact generation was authorized; Marco reviews material evidence; user approval governs commitment of sensitive or generated evidence.

**Conflict rule:** Artifact evidence cannot override decisions, guardrails, state, or authorizations.

---

### 19.7 `project_context/AGENT_ROLES.md`

**Purpose:** Define agent authority boundaries and gated workflow.

**Authority level:** Canonical role definition; subordinate to user authorization and guardrails.

**Required sections:**

1. User
2. Marco
3. Bruno
4. Neo
5. Gated workflow
6. Reassignment rule
7. Conflict and no-inference rule

**Required role content:**

**User**

- Sole approval authority.
- Authorizes specifications, implementation, environment access, credentials, funding, trading, and material phase transitions.
- May accept, reject, narrow, defer, or revoke authorization.

**Marco**

- Orchestrator and independent reviewer.
- Maintains scope and sequencing.
- Reviews Bruno and Neo independently.
- Defines acceptance criteria and bounded handoffs.
- May inspect the repository.
- May not infer user approval.
- May not implement production code unless separately reassigned and authorized.
- May not trade or use production credentials.

**Bruno**

- Specification-authoring agent.
- Identifies assumptions, interfaces, failure states, halt conditions, and measurable acceptance criteria.
- Does not implement under SPEC-ONLY tasks.
- Does not modify the repository unless separately authorized.
- Does not authorize Neo or himself.

**Neo**

- Implementation and test agent.
- Acts only against a Marco-reviewed, user-approved specification and bounded implementation prompt.
- Changes only authorized paths.
- Adds no features outside the accepted specification.
- May not use credentials, access environments, commit, push, fund, or trade unless each capability is explicitly permitted.

**Required workflow:**

1. Marco identifies the next narrow question.
2. User approves specification work.
3. Marco issues a bounded SPEC-ONLY task.
4. Bruno returns a specification and handoff.
5. Marco reviews the specification.
6. User approves or rejects implementation.
7. Marco issues a bounded CODE/TEST-ONLY task.
8. Neo implements only the accepted specification.
9. Marco reviews implementation and evidence.
10. User accepts, rejects, or authorizes the next step.

**Update process:** Role changes require explicit user approval and an authorization/decision record.

**Conflict rule:** A task prompt cannot grant broader authority than `GUARDRAILS.md` and the exact active user authorization.

---

### 19.8 `project_context/AUTHORIZATION_LOG.md`

**Purpose:** Append-only capability ledger separate from decisions.

**Authority level:** Canonical task-specific permission record, constrained by permanent guardrails.

**Required entry fields:**

- Authorization ID
- Authorizing user
- Date
- Authorized agent
- Candidate ID, if applicable
- Task or phase
- Exact permitted artifact filenames
- Permitted repository paths
- Network access
- Demo reads
- Demo writes
- Production reads
- Production writes
- Credential use
- Account funding
- Code changes
- Tests
- Artifact generation
- Repository commits
- Expiration or completion condition
- Revocation status
- Related specification identity
- Related Marco review
- Related Bruno handoff identity
- Related implementation handoff

Every capability field shall contain `PERMITTED` or `PROHIBITED`. No blank, inherited, or candidate-carried-forward fields are allowed.

**Required historical authorization distinction:**

1. **Original Candidate 01 authorization**
   - remains the first historical specification authorization;
   - applies only to the original Candidate 01 specification work and artifacts;
   - does not authorize Candidate 04, Candidate 05, Candidate 06, Candidate 07, Candidate 08, Candidate 09, or Candidate 10;
   - does not authorize repository modification, code, tests, venue access, credentials, funding, orders, cancellations, trading, or Neo.

2. **Candidate 04 submission without separately recorded explicit authorization**
   - is a lifecycle and provenance fact, not an authorization grant;
   - shall not be represented as a user authorization entry;
   - shall not inherit from Candidate 01;
   - shall not be retroactively authorized by Candidate 10.

3. **Candidate 05 blocked submission without separately recorded explicit authorization**
   - is a blocked lifecycle and provenance fact, not an authorization grant;
   - shall not be represented as an explicit user authorization entry;
   - shall not inherit from Candidate 01 or Candidate 04;
   - shall not be retroactively authorized, validated, accepted, broadened, unblocked, canonicalized, or made installable by Candidate 10.

4. **Candidate 06 correction authorization and blocked submission**
   - Candidate ID: `CANDIDATE_06`;
   - valid explicit user authorization;
   - permitted reading the exact Candidate 05 artifacts, Marco’s Candidate 05 blocking review, and the user’s Candidate 06 authorization;
   - permitted only:
     - `SPEC_repository_bootstrap_CANDIDATE_06.md`;
     - `HANDOFF_repository_bootstrap_spec_CANDIDATE_06.md`;
   - lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`;
   - disposition: blocked;
   - no repository effect.

5. **Candidate 07 blocked submission without separately recorded explicit authorization**
   - Candidate ID: `CANDIDATE_07`;
   - blocked lifecycle and provenance fact, not an authorization grant;
   - shall not be represented as an explicit user authorization entry;
   - lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`;
   - disposition: blocked;
   - no repository effect.

6. **Candidate 08 correction authorization and blocked submission**
   - Candidate ID: `CANDIDATE_08`;
   - valid explicit user authorization;
   - permitted reading the exact Candidate 07 artifacts, Marco’s Candidate 07 blocking review, and the user’s Candidate 08 authorization;
   - permitted only:
     - `SPEC_repository_bootstrap_CANDIDATE_08.md`;
     - `HANDOFF_repository_bootstrap_spec_CANDIDATE_08.md`;
   - lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`;
   - disposition: blocked;
   - no repository effect.

7. **Candidate 09 correction authorization and blocked submission**
   - Candidate ID: `CANDIDATE_09`;
   - valid explicit user authorization;
   - permitted reading the exact Candidate 08 artifacts, Marco’s Candidate 08 blocking review, and the user’s Candidate 09 authorization;
   - permitted only:
     - `SPEC_repository_bootstrap_CANDIDATE_09.md`;
     - `HANDOFF_repository_bootstrap_spec_CANDIDATE_09.md`;
   - lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`;
   - disposition: blocked;
   - no repository effect.

8. **Candidate 10 correction authorization**
   - Candidate ID: `CANDIDATE_10`;
   - valid explicit user authorization in the current conversation;
   - permits reading the exact Candidate 09 artifacts, Marco’s Candidate 09 blocking review, and the user’s Candidate 10 authorization;
   - permits only:
     - `SPEC_repository_bootstrap_CANDIDATE_10.md`;
     - `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`;
   - lifecycle at delivery: `SUBMITTED_FOR_MARCO_REVIEW`;
   - no repository effect.

Candidate 10 authorization shall not be represented as an amendment to Candidate 01, as authorization of Candidate 04 or Candidate 05, as acceptance or unblocking of Candidate 06, Candidate 07, Candidate 08, or Candidate 09, as candidate acceptance, or as implementation authorization. Candidate 01 authorization, Candidate 04 submission, Candidate 05 submission, Candidate 06 authorization and blocked submission, Candidate 07 submission, Candidate 08 authorization and blocked submission, Candidate 09 authorization and blocked submission, Candidate 10 authorization, candidate acceptance, and implementation authorization remain separate.

**Required future bootstrap implementation entry:**

Before repository modification, a further separate entry must identify:

- the exact accepted candidate;
- the bound specification and Bruno handoff identities;
- Marco’s approval review;
- Marco’s candidate-specific implementation handoff;
- the exact acting implementation agent;
- all authorized repository targets in Section 30.2;
- commands, validation, artifact permissions, and commit/push permissions.

All non-bootstrap capabilities remain `PROHIBITED`.

**Update process:** Append-only. Revocation is a new entry or explicit revocation field update under user authority; history is preserved.

**Conflict rule:** If an authorization conflicts with `GUARDRAILS.md`, inherits from another candidate, or two active entries overlap or contradict, the more restrictive capability applies and the task halts. Ordinary authorization cannot override a permanent guardrail.

---

### 19.9 Root `.gitignore`

**Purpose:** Protect the public repository from local, generated, sensitive, and runtime files.

**Authority level:** Canonical repository ignore policy; it supplements but does not replace security procedures.

**Required categories:**

- `.env`
- `.env.*` local variants
- private keys and certificates
- credential files
- local configuration overrides
- caches
- virtual environments
- build output
- test caches and coverage output
- editor files
- operating-system files
- runtime logs
- local databases
- downloaded raw data
- generated trading or account artifacts
- temporary files
- local state and recovery snapshots
- future runtime secrets and token caches

**Required safe exceptions:**

- `!.env.example`
- equivalent explicitly approved `*.example` placeholders
- sanitized fixtures only when explicitly approved
- `.gitkeep` placeholders

Ignore rules are defense in depth. They do not authorize storing secrets locally or committing files by force.

**Required policy statement:** Before any commit, inspect staged content. Do not rely on `.gitignore` to detect already tracked or force-added secrets.

**Prohibited content:** Actual secret values or credential-like examples.

---

### 19.10 Safe placeholder configuration policy

**Purpose:** Define rules for future tracked configuration examples without creating active configuration now.

**Authority level:** Permanent security and environment-separation requirement.

**Requirements:**

Tracked examples shall:

- use an unmistakable suffix such as `.example`;
- contain only obviously fake sentinel values;
- never include real endpoint tokens, account IDs, private URLs, wallets, keys, signatures, or copied environment values;
- identify environment classification explicitly;
- default to disabled or read-only behavior;
- never default to production;
- never enable order submission;
- be visually and structurally distinguishable from active configuration;
- be rejected by future runtime validation if placeholder values remain;
- document required variable names without exposing values; and
- use separate namespaces for Demo and production.

The bootstrap shall not create `.env.example`, active Kalshi configuration, active Polymarket configuration, endpoint definitions, or credential namespaces. Those belong to a later bounded environment-separation specification.

---

## 20. Canonical read order

Every agent shall read in this order:

1. root `START_HERE.md`
2. `project_context/START_HERE.md`
3. `project_context/GUARDRAILS.md`
4. `project_context/PROJECT_STATE.md`
5. `project_context/AUTHORIZATION_LOG.md`
6. `project_context/DECISION_LOG.md`
7. `project_context/AGENT_ROLES.md`
8. the accepted-candidate identity table recorded in the approval/authorization chain
9. `specifications/SPEC_repository_bootstrap.md`
10. `reviews/REVIEW_repository_bootstrap_spec.md`
11. `handoffs/HANDOFF_repository_bootstrap_spec.md`
12. `handoffs/HANDOFF_repository_bootstrap_implementation.md`
13. relevant `project_context/ARTIFACT_INDEX.md` entries

### 20.1 Justification

- Entry points establish identity and routing.
- `GUARDRAILS.md` establishes the highest standing operational authority before task permission is interpreted.
- Project state identifies the current phase and active authorization.
- The authorization log identifies task-specific permission within the guardrails.
- Decision history and roles provide context and authority boundaries.
- The accepted-candidate identity table establishes which exact external bytes may control.
- The exact final specification, approval review, Bruno handoff, and Marco implementation handoff establish the bounded task record.
- Artifact references are interpreted last because evidence cannot authorize action.

No reader may skip directly to a specification, review, handoff, or artifact and infer authority.

---

## 21. Source-of-truth precedence and conflict handling

### 21.1 Deterministic operational authority rule

1. `project_context/GUARDRAILS.md` is the highest standing operational authority.
2. Exact user authorization determines task-specific permission only within the current guardrails.
3. Ordinary task authorization cannot override a permanent guardrail.
4. `PROJECT_STATE.md`, `DECISION_LOG.md`, `AGENT_ROLES.md`, specifications, reviews, handoffs, artifacts, implementations, agent statements, conversation memory, and technical capability cannot weaken a current guardrail or expand task permission.
5. The user remains the sole approval authority, including for guardrail amendments and task-specific work.
6. Any conflict, ambiguity, or stale record uses the more restrictive interpretation and halts the affected work.

### 21.2 Guardrail amendment process

A permanent guardrail changes only after all of these steps are complete:

1. an explicit proposed amendment;
2. Marco review;
3. explicit user approval of the guardrail amendment;
4. path-specific authorization to modify `project_context/GUARDRAILS.md`;
5. an auditable decision record; and
6. completion of the authorized repository change.

Until all six steps are completed, the existing guardrail remains controlling.

An ordinary task authorization, including one signed or stated by the user for a non-guardrail task, shall not be interpreted as silently amending `GUARDRAILS.md`.

### 21.3 Task-specific permission resolution

After confirming compliance with `GUARDRAILS.md`, the acting agent shall resolve task permission from:

1. the exact active user authorization recorded in `project_context/AUTHORIZATION_LOG.md`;
2. the current state in `project_context/PROJECT_STATE.md`;
3. the accepted specification and Marco approval review;
4. the applicable bounded handoff; and
5. relevant decisions and artifact references.

Lower-order records may narrow permission. They may not expand permission beyond the guardrails or exact active authorization.

### 21.4 Conflict and stale-record handling

When records conflict, are ambiguous, or appear stale:

1. apply the more restrictive interpretation immediately;
2. halt the affected work;
3. identify exact paths, revisions, authorization IDs, and conflicting fields;
4. determine whether a record is superseded, expired, revoked, incomplete, or mismatched;
5. do not rewrite history silently;
6. request Marco review and user decision where required; and
7. resume only after the canonical repository records are corrected through an authorized change.

A record is stale if it references:

- a superseded baseline commit;
- an expired or revoked authorization;
- a superseded or blocked specification presented as active;
- a completed phase as current;
- a missing or mismatched review;
- a missing or mismatched implementation handoff;
- a non-current environment matrix;
- a `PROJECT_STATE.md` that does not match the active authorization; or
- an accepted-candidate or installation identity mismatch; or
- an artifact or implementation that no longer matches the repository tree.

---

## 22. Formal review vocabulary

The first non-whitespace text of every formal Marco review shall be exactly one of these formal decision terms:

- `APPROVE`
- `BLOCK`
- `DEFER`
- `ACCEPT FINDING`
- `NEEDS VERIFICATION`

The opening decision term shall appear before any title, heading, candidate metadata, identity table, explanation, or other text.

After the opening decision line, the review shall identify:

- the exact candidate identifier;
- the exact candidate-specific specification filename;
- the exact candidate-specific Bruno handoff filename;
- each bound artifact byte length;
- each bound artifact SHA-256; and
- the review rationale and disposition.

Candidate identity and hash information therefore follows the opening decision line. It never precedes the formal decision term.

No synonymous approval terms shall replace these labels.

### 22.1 Meaning

| Term | Intended use |
|---|---|
| `APPROVE` | The reviewed artifact is suitable to present to the user for the next authorization decision. It does not authorize implementation, access, or trading. |
| `BLOCK` | A defect, conflict, safety issue, missing requirement, or unmet gate prevents progression. |
| `DEFER` | The artifact or decision is intentionally postponed without treating it as accepted or defective. |
| `ACCEPT FINDING` | Marco accepts a factual or analytical finding; this does not authorize implementation. |
| `NEEDS VERIFICATION` | Material evidence is missing or uncertain; no affected progression is allowed until verified. |

Only the user may authorize material work after Marco’s review.

---

## 23. Demo and production separation requirements

Future technical work shall separate:

- offline/local testing;
- Kalshi Demo;
- Kalshi production;
- Polymarket production;
- shadow execution; and
- authenticated production activity.

### 23.1 Mandatory separation dimensions

Each environment shall have separate:

- configuration namespaces;
- endpoint definitions;
- credential namespaces;
- runtime modes;
- state and ledger namespaces;
- log classifications;
- artifact classifications;
- authorization records; and
- halt conditions.

### 23.2 Fail-closed environment selection

- No environment may silently fall back to another.
- Missing environment selection halts.
- Unknown environment names halt.
- Malformed environment configuration halts.
- Contradictory endpoint/credential/environment combinations halt.
- Demo credentials may not authenticate production.
- Production credentials may not be loaded in Demo or local modes.
- Shadow execution may not send orders.
- A Demo-authorized task shall fail if configured with a production endpoint.
- Production writes remain prohibited unless separately and explicitly authorized.

### 23.3 Venue separation

Shared economic concepts may use venue-independent types only where meaning is genuinely shared.

Kalshi and Polymarket shall not be forced into identical:

- order representations;
- settlement models;
- fee models;
- market identifiers;
- outcome semantics;
- tick or quantity units;
- lifecycle events; or
- authentication behavior.

Venue-specific behavior belongs in the corresponding adapter.

---

## 24. Update and approval workflow

### 24.1 Candidate specification lifecycle

1. Marco allocates the next unused sequential candidate identifier.
2. Bruno produces a candidate-specific specification and paired handoff using that same identifier, under an exact SPECIFICATION-ONLY authorization when such authorization is recorded.
3. The candidate number is not reused, retrospectively renumbered, or overwritten in place.
4. A skipped candidate number requires an explicit Marco record naming the skipped number and reason.
5. Bruno freezes both artifacts and delivers them to Marco.
6. Delivery establishes `SUBMITTED_FOR_MARCO_REVIEW`.
7. Marco independently recomputes and records each exact candidate identity tuple.
8. Marco’s formal review begins with exactly one formal decision term as its first non-whitespace text.
9. Candidate identity and hash information follows the opening decision line.
10. Marco’s `APPROVE`, if issued, means suitable for user decision only.
11. The user accepts, rejects, narrows, or defers the exact identity-bound candidate.
12. Any byte change after submission requires the next unused sequential Marco-allocated candidate number and a new review.
13. Only an accepted candidate may be referenced by a later implementation authorization.
14. Candidate acceptance does not itself authorize repository implementation.

### 24.2 Ordinary canonical document changes

For every material canonical document change other than a guardrail amendment:

1. A permitted agent proposes the change.
2. The proposal identifies exact paths and rationale.
3. Marco independently reviews it.
4. The user explicitly approves, rejects, narrows, or defers it.
5. An authorization entry permits the exact agent, paths, and capabilities within the current guardrails.
6. The authorized agent modifies only those paths.
7. Evidence is returned.
8. Marco reviews the implementation.
9. The user accepts or rejects the result.

### 24.3 Guardrail changes

A change to `project_context/GUARDRAILS.md` shall follow every step in Section 21.2. Until the repository change is completed, the prior guardrail remains controlling.

### 24.4 Append-only records

- `DECISION_LOG.md` and `AUTHORIZATION_LOG.md` preserve history.
- Supersessions and revocations are explicit.
- Prior entries are not rewritten to make the historical record appear cleaner.
- The original Candidate 01 authorization remains the first historical specification authorization entry.
- Candidate 04 remains recorded as a submission/provenance event without a separately recorded explicit user authorization.
- Candidate 05 remains recorded as Candidate 06’s blocked predecessor submission without a separately recorded explicit user authorization and is not rewritten as authorized.
- Candidate 06 correction authorization remains a distinct valid historical authorization entry even though Candidate 06 is blocked. Candidate 07 remains a blocked submission without separately recorded explicit authorization. Candidate 08 correction authorization remains a distinct valid historical authorization entry even though Candidate 08 is blocked. Candidate 09 correction authorization remains a distinct valid historical authorization entry even though Candidate 09 is blocked. Candidate 10 correction authorization, if Candidate 10 is accepted, remains a separate later historical authorization entry and does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09.
- Candidate 01 authorization, Candidate 04 submission, Candidate 05 submission, Candidate 06 authorization and blocked submission, Candidate 07 submission, Candidate 08 authorization and blocked submission, Candidate 09 authorization and blocked submission, Candidate 10 authorization, candidate acceptance, and future implementation authorization remain distinct events.
- No specification authorization authorizes repository implementation.
- Sensitive values are never recorded.

### 24.5 Current-state updates

`PROJECT_STATE.md` shall reflect the actual active bootstrap implementation authorization at commit time and shall be updated whenever an accepted material transition occurs. It shall not authorize work or claim a future authorization before that authorization exists.

### 24.6 First bootstrap task-record adoption

The first bootstrap implementation shall adopt, in the same authorized repository change, the exact final versions of:

- `specifications/SPEC_repository_bootstrap.md`;
- `handoffs/HANDOFF_repository_bootstrap_spec.md`;
- `reviews/REVIEW_repository_bootstrap_spec.md`; and
- `handoffs/HANDOFF_repository_bootstrap_implementation.md`.

---

## 25. Repository safety and scope rules

1. Repository visibility is public and must be treated as such.
2. Only authorized paths may change.
3. Pre-existing files are not modified unless expressly named.
4. No force-add of ignored sensitive files.
5. No credentials or copied environment values.
6. No active configs in bootstrap.
7. No code or tests.
8. No generated runtime artifacts.
9. No unreviewed “helpful” extras.
10. No branch, commit, or push unless explicitly permitted.
11. No automatic issue, PR, or release creation.
12. No network calls beyond those expressly permitted.
13. No inference that a directory, placeholder, specification, review, or handoff authorizes future contents or actions.
14. No inference that a documented phase sequence authorizes progression.
15. Any scope ambiguity halts rather than expands.

---

## 26. Initial project sequence

The canonical documents shall record this sequence:

1. canonical documentation and guardrails;
2. Kalshi Demo environment separation;
3. read-only connectivity preflight;
4. one-market order-book reconstruction;
5. one-order lifecycle;
6. fill and REST reconciliation;
7. persistent ledger and restart recovery;
8. emergency cancellation and risk limits;
9. minimal two-sided market-maker engine;
10. authoritative profitability accounting;
11. one narrow logical-arbitrage relationship;
12. Kalshi production read-only observation;
13. Polymarket production read-only adapter;
14. shadow execution;
15. authenticated production activity only after separate explicit user authorization.

### 26.1 Sequence is not authorization

The sequence is planning guidance only.

Every phase requires:

1. bounded specification;
2. Marco review;
3. explicit user approval;
4. bounded implementation authorization;
5. implementation and evidence;
6. Marco review; and
7. user acceptance or next-step authorization.

No phase begins automatically when the previous one completes.

---

## 27. Test and review matrix for the later bootstrap

| Review area | Required check | Pass condition |
|---|---|---|
| Baseline | Repository identity, visibility, branch, HEAD, tree | Matches user-approved baseline |
| Scope | Changed paths | Exact subset of authorized bootstrap paths |
| Structure | Required directories and files | All exist; no extras |
| Candidate identity | Candidate ID, source filenames, bytes, SHA-256 | Exact and bound by Marco review/user acceptance |
| Candidate authorization lineage | Candidate 01, Candidate 04 submission, Candidate 05 blocked submission, Candidate 06 valid authorization and blocked submission, Candidate 07 blocked submission, Candidate 08 valid authorization and blocked submission, Candidate 09 valid authorization and blocked submission, Candidate 10 authorization, acceptance, implementation | Separate events; no inheritance or retroactive authorization |
| Canonical task records | Four required exact paths | Exact byte-for-byte copies of bound accepted sources |
| Record candidate alignment | Specification, Bruno handoff, Marco review, user authorization, implementation handoff | Same accepted candidate; no blocked or superseded candidate adopted |
| Placeholder placement | `.gitkeep` locations | Present only in `src/`, `tests/`, and `artifacts/` |
| Source code | `src/` contents | `.gitkeep` only |
| Tests | `tests/` contents | `.gitkeep` only |
| Root entry | Mandatory statements | All present and concise |
| Orchestration entry | Exact read order and workflow | Complete and consistent |
| Guardrails | Highest standing authority | Explicit and consistent |
| Guardrail amendment | Required six-step process | Exact process present; old guardrail controls until completion |
| Task authorization | Permission within guardrails | No ordinary authorization can override guardrails |
| State | Current authorization and phase | Accurate at commit time |
| Authorization ledger | Historical and active entries | Candidate 01 first historical specification authorization; Candidate 05 blocked without separately recorded authorization; Candidate 06 validly authorized but blocked; Candidate 07 blocked without separately recorded authorization; Candidate 08 validly authorized but blocked; Candidate 09 validly authorized but blocked; Candidate 10 distinct; acceptance and implementation separate |
| Decision log | Required decisions | Present without invented approvals |
| Artifact index | Initial empty state | No runtime/test artifacts claimed |
| Roles | Agent boundaries | Consistent across files |
| Formal vocabulary | Review terms | Exact five terms only |
| Environment separation | Modes and fail-closed rules | Explicit and consistent |
| Precision | Economic arithmetic | Binary floating point prohibited |
| Secret policy | `.gitignore` and placeholders | Consistent; no secrets |
| Sensitive content | Repository inspection | None present |
| Future phases | Sequence wording | Guidance only; no authorization |
| Public warning | Both entry points | Prominent warning present |
| README | Existing root file | Unchanged |
| Halt behavior | Conflict, ambiguity, stale records | More restrictive interpretation and halt |
| Diff reviewability | Path-by-path diff | Reviewer can inspect each change |

---

## 28. Acceptance criteria

The later bootstrap implementation is acceptable only if all criteria pass:

1. Only explicitly authorized documentation and structural paths are changed.
2. No source code, test code, API client, trading engine, credential loader, schema, or runtime configuration is added.
3. All required canonical governance documents exist.
4. Every required canonical governance document contains all mandatory sections.
5. The first bootstrap implementation includes exactly:
   - `specifications/SPEC_repository_bootstrap.md`;
   - `handoffs/HANDOFF_repository_bootstrap_spec.md`;
   - `reviews/REVIEW_repository_bootstrap_spec.md`; and
   - `handoffs/HANDOFF_repository_bootstrap_implementation.md`.
6. Those four records are exact byte-for-byte copies of the final accepted external candidate artifacts.
7. The accepted candidate is bound by candidate ID, exact source filenames, raw byte lengths, and lowercase SHA-256 values.
8. Both Candidate 10 deliverables state `Candidate: CANDIDATE_10`, use the exact Candidate 10 filenames, and share the same candidate number.
9. Marco is identified as the sole allocator of candidate identifiers.
10. Candidate 10 is the next Marco-allocated sequential candidate after blocked Candidate 09.
11. Candidate identifiers are never reused, retrospectively renumbered, or overwritten in place.
12. Any skipped candidate number is supported by an explicit Marco record naming the number and reason.
13. Candidate 10 delivery status is `SUBMITTED_FOR_MARCO_REVIEW`.
14. The installation identity table binds all four source records before repository modification.
15. Marco’s review binds the exact specification and Bruno handoff identities.
16. The first non-whitespace text of Marco’s formal review is exactly one formal decision term.
17. No title, heading, metadata, identity table, hash, or explanation precedes the opening review decision line.
18. Candidate identity and hash information follows the opening decision line.
19. User acceptance explicitly accepts the exact identity-bound candidate.
20. Any post-submission or post-binding byte change requires a new Marco-allocated candidate number.
21. No blocked, superseded, unverified, or unaccepted candidate is adopted as canonical.
22. `specifications/`, `handoffs/`, and `reviews/` contain no `.gitkeep`.
23. `src/`, `tests/`, and `artifacts/` contain only `.gitkeep`.
24. Canonical read order lists the exact four task-record paths and is consistent across entry documents.
25. `GUARDRAILS.md` is consistently identified as the highest standing operational authority.
26. Exact user authorization is consistently limited to task-specific permission within current guardrails.
27. No ordinary authorization can override a permanent guardrail.
28. The guardrail-amendment process contains all six required steps, and the existing guardrail controls until repository completion.
29. Any conflict, ambiguity, or stale record applies the more restrictive interpretation and halts affected work.
30. Agent boundaries are consistent across all files.
31. Authorization lineage records, in order, the original Candidate 01 authorization; Candidate 04 submission; Candidate 05 blocked submission without separately recorded explicit authorization; Candidate 06 valid correction authorization and blocked submission; Candidate 07 blocked submission without separately recorded explicit authorization; Candidate 08 valid correction authorization and blocked submission; Candidate 09 valid correction authorization and blocked submission; Candidate 10 correction authorization; candidate acceptance as a separate event; and later implementation authorization as a separate event.
32. No record represents Candidate 05 as having a separately recorded explicit user authorization.
33. No record treats Candidate 10 authorization as retroactive authorization, validation, acceptance, broadening, unblocking, canonicalization, or installability of Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09.
34. Candidate 05 remains blocked and noncanonical.
35. No authorization inherits across candidate identifiers.
36. `PROJECT_STATE.md` reflects the actual active bootstrap implementation authorization at commit time.
37. Existing root `README.md` is unchanged.
38. Demo and production environments are explicitly separated.
39. Production writes and live trading are explicitly prohibited.
40. Repository-publicity warnings are visible at both entry points.
41. Secret and placeholder policies are consistent with `.gitignore`.
42. Monetary precision rules prohibit binary floating point for economic values.
43. The phase sequence is recorded but does not authorize future phases.
44. No credentials, account information, wallets, private URLs, logs, databases, downloaded raw data, or generated trading data are present.
45. A reviewer can determine the current authorized state solely through the canonical read order.
46. All ambiguous, missing, inherited, or omitted authorization fields fail closed.
47. No statement implies that Demo results establish production safety or profitability.
48. No statement authorizes Neo under the Candidate 10 correction task.
49. The future implementation handoff remains descriptive until separately issued by Marco after explicit user approval.
50. `DECISION_LOG.md` and `AUTHORIZATION_LOG.md` do not invent user approvals.
51. Every formal review term is defined exactly once and no equivalent approval vocabulary is introduced.
52. Generated artifact content is ignored by default; only `artifacts/.gitkeep` is initially committed under `artifacts/`.
53. All halt conditions are documented consistently.
54. The implementation evidence includes baseline, Marco candidate allocation/skip records, exact changed paths, accepted-candidate identity and source-to-target mapping, formal-review first-line verification, post-change tree, content checks, guardrail-precedence checks, secret check, final diff, and final workspace state.
55. No venue, credential, funding, account, order, cancellation, or trading access occurs.
56. Marco can review the bootstrap path by path without relying on chat history.
57. The repository remains at documentation-bootstrap scope only.

Any failed criterion yields `BLOCK` unless the specification is formally revised under a newly allocated candidate number and the user approves the revision.

---

## 29. Explicitly unauthorized follow-up work

The following are explicitly unauthorized after this specification is delivered:

- issuing a task to Neo;
- adding these corrected artifacts or any future review/handoff to the repository under the Candidate 10 correction task;
- creating the repository bootstrap files or canonical task-record paths;
- modifying `README.md`;
- creating branches, commits, pull requests, or issues;
- adding CI;
- adding package metadata;
- adding code or tests;
- choosing language or libraries;
- defining active endpoints;
- creating `.env.example`;
- creating credential loaders;
- accessing Kalshi Demo;
- accessing Kalshi production;
- accessing Polymarket;
- funding accounts;
- placing or canceling orders;
- collecting production data;
- shadow execution;
- strategy evaluation; and
- any phase beyond documentation specification review.

---

## 30. Future implementation handoff template

### 30.1 Status

**DESCRIPTIVE ONLY — NOT ISSUED — NEO NOT AUTHORIZED.**

This section defines the required bounds of Marco’s later implementation handoff. It is not itself the handoff and shall not be treated as authorization.

Marco may prepare external `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md` for canonical target `handoffs/HANDOFF_repository_bootstrap_implementation.md` only after:

1. Marco reviews and approves the exact frozen Candidate 10 artifacts for user decision;
2. the user explicitly accepts the exact Candidate 10 identity table;
3. the user explicitly approves a bounded bootstrap implementation task; and
4. the exact implementation agent and capabilities are recorded.

This correction task does not write Marco’s review or implementation handoff.

### 30.2 Future authorized-path template

The later Marco handoff may authorize only these exact repository paths:

```text
START_HERE.md
.gitignore
project_context/START_HERE.md
project_context/GUARDRAILS.md
project_context/PROJECT_STATE.md
project_context/DECISION_LOG.md
project_context/ARTIFACT_INDEX.md
project_context/AGENT_ROLES.md
project_context/AUTHORIZATION_LOG.md
specifications/SPEC_repository_bootstrap.md
handoffs/HANDOFF_repository_bootstrap_spec.md
handoffs/HANDOFF_repository_bootstrap_implementation.md
reviews/REVIEW_repository_bootstrap_spec.md
src/.gitkeep
tests/.gitkeep
artifacts/.gitkeep
```

`README.md` shall remain unchanged and is not an authorized modification path.

### 30.3 Required accepted-candidate source records

If Candidate 10 is accepted, before implementation begins the acting agent must have:

- `SPEC_repository_bootstrap_CANDIDATE_10.md`;
- `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`;
- `REVIEW_repository_bootstrap_spec_CANDIDATE_10.md`;
- `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md`;
- Marco’s candidate acceptance identity table binding the exact Candidate 10 specification and Bruno handoff bytes;
- explicit user acceptance of that exact identity-bound candidate;
- an installation identity table binding all four source records, with the final implementation-handoff identity bound externally after its bytes are frozen; and
- a separate active implementation authorization.

The implementation shall map those sources to the fixed canonical targets in Section 7.2 without altering bytes. It does not author or revise Marco’s review or handoff.

### 30.4 Future files/components to implement

- Documentation files and directory placeholders only.
- No functions, components, code, schemas, loaders, clients, or tests.

### 30.5 Prohibited paths and activities

- Every unlisted path.
- Modification of `README.md`.
- `specifications/.gitkeep`, `handoffs/.gitkeep`, or `reviews/.gitkeep`.
- Any active configuration file.
- Any credential, data, log, database, or runtime-state path.
- Any work that conflicts with `GUARDRAILS.md`.
- Any guardrail modification unless separately authorized through the complete amendment process.

### 30.6 Future allowed command categories

Only after explicit user approval and Marco’s issued handoff:

- read-only repository inspection;
- directory creation;
- creation of the listed Markdown and `.gitkeep` files;
- verifying the accepted candidate ID, filenames, byte lengths, and SHA-256 values;
- copying the four final canonical task records without altering any bytes;
- deterministic text/path validation;
- candidate and identity-consistency validation;
- secret-pattern inspection;
- Git diff/status inspection; and
- commit or push only if the exact authorization explicitly marks each capability `PERMITTED`.

No other network commands, package installation, test execution, API access, venue access, credentials, funding, orders, cancellations, or trading.

### 30.7 Required evidence

The implementation agent would have to return:

- baseline identity and HEAD;
- pre-change tree;
- exact changed paths;
- post-change tree;
- exact accepted-candidate identity table;
- exact candidate-source-to-canonical-target mapping;
- pre-copy and post-copy byte-length and SHA-256 equality;
- evidence that no blocked, superseded, unverified, or unaccepted candidate was adopted;
- per-file requirement checklist;
- guardrail-first precedence checklist;
- secret scan result;
- confirmation `src/`, `tests/`, and `artifacts/` contain only `.gitkeep`;
- confirmation no `.gitkeep` exists in `specifications/`, `handoffs/`, or `reviews/`;
- confirmation no code or tests were created or run;
- confirmation no venue, credentials, funding, orders, cancellations, or trading were accessed;
- final diff;
- final workspace status; and
- commit SHA only if committing was authorized.

### 30.8 Stop conditions

The implementation agent must stop on every condition in Section 12, any unlisted path need, baseline drift, candidate mismatch, byte-length or SHA-256 mismatch, record-identity mismatch, guardrail conflict, or ambiguity in current authorization.

---

## 31. Assumptions and fixed bootstrap decisions

### 31.1 Assumptions

1. `rigolugo/ARB` is the intended canonical repository.
2. The repository will remain public during bootstrap.
3. Markdown is the canonical format for governance documents.
4. Git history is the persistence mechanism for canonical documentation.
5. The user will provide explicit approval references or wording when implementation is authorized.
6. No legal, regulatory, tax, or venue-compliance conclusion is made by this bootstrap.
7. No active configuration example is needed until the environment-separation phase.
8. The initial document set is sufficient for the first governance layer and shall not expand without a separate approved need.

### 31.2 Fixed decisions

1. Marco is the sole allocator of candidate identifiers for this workstream.
2. Every new or corrected submission receives the next unused sequential candidate number.
3. Candidate identifiers are never reused, retrospectively renumbered, or overwritten in place.
4. A candidate number may be skipped only through an explicit Marco record naming the number and reason.
5. The specification and Bruno handoff always share the same candidate number.
6. Candidate 10 external artifacts are:
   - `SPEC_repository_bootstrap_CANDIDATE_10.md`;
   - `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`.
7. Candidate 10 is `SUBMITTED_FOR_MARCO_REVIEW` upon frozen delivery to Marco.
8. Candidate 10 does not write Marco’s future review or implementation handoff.
9. Candidate 10 is not accepted or canonical merely because it is submitted.
10. Every formal Marco review begins with exactly one formal decision term as its first non-whitespace text.
11. Candidate identity and hash information follows the opening decision line.
12. Exact acceptance requires candidate ID, source filename, byte length, and SHA-256 binding.
13. Any byte change after submission or identity binding requires a new Marco-allocated candidate number.
14. Candidate 04 remains a submission/provenance event without a separately recorded explicit user authorization.
15. Candidate 05 was submitted without a separately recorded explicit user authorization, remains blocked, and shall not be represented otherwise.
16. Candidate 09 is Candidate 10’s immediate blocked predecessor; Candidate 08 is Candidate 09’s blocked predecessor; Candidate 07 is Candidate 08’s blocked predecessor; Candidate 06 is Candidate 07’s blocked predecessor; Candidate 05 is Candidate 06’s blocked predecessor.
17. Candidate 10 authorization is a distinct event and does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09.
18. Candidate 06’s valid explicit authorization provenance remains unchanged; Candidate 08’s valid explicit authorization provenance remains unchanged; and Candidate 09’s valid explicit authorization provenance remains unchanged while Candidate 09 remains blocked.
19. Candidate acceptance remains separate from Candidate 10 authorization and implementation authorization.
20. Canonical repository task-record paths remain:
   - `specifications/SPEC_repository_bootstrap.md`;
   - `handoffs/HANDOFF_repository_bootstrap_spec.md`;
   - `reviews/REVIEW_repository_bootstrap_spec.md`;
   - `handoffs/HANDOFF_repository_bootstrap_implementation.md`.
21. `PROJECT_STATE.md` shall reflect the actual active bootstrap implementation authorization and accepted candidate at commit time.
22. The original Candidate 01 authorization remains the first historical specification authorization entry.
23. A future implementation authorization is a further separate authorization.
24. Existing root `README.md` shall remain unchanged.
25. `.gitkeep` shall be removed when a placeholder directory receives its first real tracked file.
26. The first bootstrap implementation shall include all four canonical task records in the same authorized repository change.
27. `specifications/`, `handoffs/`, and `reviews/` shall contain real records and no `.gitkeep` in the first bootstrap.
28. `src/.gitkeep`, `tests/.gitkeep`, and `artifacts/.gitkeep` shall be retained.

## 32. Open questions requiring Marco’s decision

None.

Candidate-number allocation, immutable lifecycle identifiers, same-number specification/handoff pairing, the formal-review first-line rule, Candidate 10 submitted status, identity binding, authorization lineage, canonical paths, placeholder treatment, current-state behavior, and authority precedence are resolved. Candidate 09 is Candidate 10’s immediate blocked predecessor. Candidate 08 is Candidate 09’s blocked predecessor. Candidate 07 is Candidate 08’s blocked predecessor. Candidate 06 is Candidate 07’s blocked predecessor. Candidate 05 is Candidate 06’s blocked predecessor. Candidate 05 and Candidate 07 lack separately recorded explicit user authorization; Candidate 06, Candidate 08, and Candidate 09 retain their valid explicit authorization provenance and blocked dispositions. Marco must still independently review the exact Candidate 10 bytes. The user must still explicitly accept the exact candidate and separately authorize any future implementation.

---

## 33. Specification completion statement

Candidate: CANDIDATE_10

Lifecycle status: `SUBMITTED_FOR_MARCO_REVIEW`

Candidate 10 makes only the three authorized corrections to Candidate 09: Section 28 acceptance criterion 31, the Section 12 authorization-inheritance halt condition, and Section 31.2 fixed decision 18. It preserves every other Candidate 09 requirement without redesign.

Bruno confirms for Candidate 10:

- Candidate 05 remains blocked and is not represented as having a separately recorded explicit user authorization;
- Candidate 06 remains blocked and its valid explicit user authorization provenance is preserved;
- Candidate 07 remains blocked and is not represented as having a separately recorded explicit user authorization;
- Candidate 08 remains blocked and its valid explicit authorization provenance is preserved;
- Candidate 09 remains blocked and its valid explicit authorization provenance is preserved;
- Candidate 09 is Candidate 10’s immediate blocked predecessor;
- Candidate 08 is Candidate 09’s blocked predecessor;
- Candidate 07 is Candidate 08’s blocked predecessor;
- Candidate 06 is Candidate 07’s blocked predecessor;
- Candidate 05 is Candidate 06’s blocked predecessor;
- Candidate 10 was prepared under the user’s explicit authorization in the current conversation;
- Candidate 10 authorization is distinct from Candidate 01, Candidate 04 submission, Candidate 05 submission, Candidate 06 authorization and blocked submission, Candidate 07 submission, Candidate 08 authorization and blocked submission, Candidate 09 authorization and blocked submission, candidate acceptance, and future implementation authorization;
- Candidate 10 does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
- no repository files were modified;
- no branch was created;
- no repository commit or push was performed;
- no code or tests were created;
- no tests were executed;
- no network access occurred beyond reading the canonical GitHub repository;
- no credentials were accessed;
- no Kalshi Demo or production environment was accessed;
- no Polymarket environment was accessed;
- no account was funded;
- no order was placed or canceled;
- no trading occurred;
- Marco’s future review and implementation handoff were not written; and
- Neo remains unauthorized.
