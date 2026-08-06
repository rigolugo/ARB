# Marco Handoff — Repository Bootstrap Specification Candidate 10

**Artifact:** `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`  
Candidate: CANDIDATE_10  
**Predecessor candidate:** `CANDIDATE_09` — blocked  
**Date:** 2026-08-05  
**From:** Bruno  
**To:** Marco  
**Classification:** `REPOSITORY_BOOTSTRAP_SPECIFICATION_CANDIDATE_10_BOUNDED_CORRECTION_ONLY`  
**Purpose:** Independent review of three bounded authorization-lineage omissions in Candidate 09  
**Lifecycle status:** `SUBMITTED_FOR_MARCO_REVIEW`; proposed; noncanonical; non-authorizing  
**Implementation authorization:** None  
**Neo authorization:** None  
**Canonical installation target if later accepted:** `handoffs/HANDOFF_repository_bootstrap_spec.md`

---

## 1. Deliverables produced

Bruno produced exactly:

1. `SPEC_repository_bootstrap_CANDIDATE_10.md`
2. `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`

Both artifacts state exactly:

`Candidate: CANDIDATE_10`

Both frozen artifacts are delivered with lifecycle status:

`SUBMITTED_FOR_MARCO_REVIEW`

No Marco review, candidate-acceptance record, implementation authorization, implementation handoff, repository file, branch, commit, pull request, issue, release, archive, checksum sidecar, code, test, or additional artifact was produced.

---

## 2. Canonical baseline verification

Bruno verified the canonical GitHub repository before drafting:

| Attribute | Required and observed value |
|---|---|
| Repository | `rigolugo/ARB` |
| Visibility | Public |
| Default branch | `main` |
| HEAD | `da629e93ce9255c28ecb485ee2b67bfc0c0ccb86` |
| Tracked tree | `README.md` only |
| `README.md` | `# ARB` followed by `Arbitrage research Project` |

The observed baseline matched exactly. No baseline halt condition was triggered.

---

## 3. Exact immediate blocked predecessor inputs

Candidate 10 was derived from the exact frozen Candidate 09 artifacts:

| Artifact | Candidate | Disposition | Raw bytes | SHA-256 |
|---|---|---|---:|---|
| `SPEC_repository_bootstrap_CANDIDATE_09.md` | `CANDIDATE_09` | Immediate blocked predecessor | `118801` | `641b6b01a0594aa5ea030252cb365364451b728928e8352d1be3d1223a35c3a9` |
| `HANDOFF_repository_bootstrap_spec_CANDIDATE_09.md` | `CANDIDATE_09` | Immediate blocked predecessor | `16262` | `af57c69040976f62f0fb52a76e2c731cdae99b8a0e4c7a9433585de5265086db` |

Bruno independently recomputed both raw byte lengths and SHA-256 values before drafting. Both matched the required identities exactly.

Candidate 09 is Candidate 10’s immediate blocked predecessor.

The preserved lineage is:

- Candidate 04 was submitted without separately recorded explicit authorization.
- Candidate 05 was submitted without separately recorded explicit authorization and remains blocked.
- Candidate 06 was prepared under valid explicit authorization and remains blocked.
- Candidate 07 was submitted without separately recorded explicit authorization and remains blocked.
- Candidate 08 was prepared under valid explicit authorization and remains blocked.
- Candidate 09 was prepared under valid explicit authorization and remains blocked.
- Candidate 10 was prepared under the new explicit user authorization.

These identities establish correction provenance only. They do not authorize, validate, accept, broaden, unblock, canonicalize, or make Candidate 09 installable.

---

## 4. Candidate 10 authorization and non-retroactivity

The user explicitly authorized Bruno to prepare Candidate 10 under Marco’s exact bounded Candidate 10 correction scope and predecessor identities.

This is a new and distinct authorization event permitting only:

- reading `rigolugo/ARB`;
- reading the exact frozen Candidate 09 artifacts;
- reading Marco’s Candidate 09 blocking review supplied as the controlling correction instruction;
- reading the user’s Candidate 10 authorization; and
- producing the two Candidate 10 external documentation artifacts.

Candidate 10 authorization is distinct from:

- the original Candidate 01 specification authorization;
- Candidate 04 submission;
- Candidate 05 submission;
- Candidate 06 authorization and blocked submission;
- Candidate 07 submission;
- Candidate 08 authorization and blocked submission;
- Candidate 09 authorization and blocked submission;
- candidate acceptance; and
- any future implementation authorization.

Candidate 10 authorization does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09.

It does not constitute Candidate 10 acceptance, repository implementation authorization, canonical installation, Neo authorization, or authorization of a later phase.

---

## 5. Three bounded corrections

Candidate 10 corrects only three defects in Candidate 09.

### 5.1 Section 28 acceptance criterion 31

Candidate 10 Section 28 criterion 31 now requires the complete ordered lineage:

1. the original Candidate 01 authorization;
2. Candidate 04 submission;
3. Candidate 05 blocked submission without separately recorded explicit authorization;
4. Candidate 06 valid correction authorization and blocked submission;
5. Candidate 07 blocked submission without separately recorded explicit authorization;
6. Candidate 08 valid correction authorization and blocked submission;
7. Candidate 09 valid correction authorization and blocked submission;
8. Candidate 10 correction authorization;
9. candidate acceptance as a separate event; and
10. later implementation authorization as a separate event.

Candidate 08 is no longer omitted. Candidate 09 is included as Candidate 10’s validly authorized but blocked immediate predecessor.

### 5.2 Section 12 authorization-inheritance halt condition

Candidate 10 Section 12 now requires the future implementation to halt if any of these prior events is treated as authorization for Candidate 10:

- Candidate 01 authorization;
- Candidate 04 submission;
- Candidate 05 submission;
- Candidate 06 authorization;
- Candidate 07 submission;
- Candidate 08 authorization; or
- Candidate 09 authorization or submission.

Authorization does not inherit across candidate identifiers. Candidate 09’s valid bounded authorization remains limited to Candidate 09 and does not authorize Candidate 10.

### 5.3 Section 31.2 fixed decision 18

Candidate 10 Section 31.2 fixed decision 18 now states that:

- Candidate 06’s valid explicit authorization provenance remains unchanged;
- Candidate 08’s valid explicit authorization provenance remains unchanged; and
- Candidate 09’s valid explicit authorization provenance remains unchanged while Candidate 09 remains blocked.

The blocked disposition of Candidate 06, Candidate 08, and Candidate 09 is unchanged.

No other substantive Candidate 09 requirement was redesigned.

---

## 6. Candidate 09 requirements preserved

Candidate 10 preserves every other Candidate 09 requirement without redesign, except unavoidable Candidate 09-to-Candidate 10 updates to candidate identity, filenames, classification, lifecycle references, immediate-predecessor references, authorization references, external review and implementation-handoff filenames, candidate-specific canonical-source mappings, and frozen artifact identities.

Preserved requirements include:

- Candidate 09’s corrected Sections 5.4 and 19.5;
- Candidate 09’s Section 7.1 direct-input model;
- Marco as sole allocator of candidate identifiers;
- next-unused sequential candidate numbering;
- same-number specification and Bruno handoff pairing;
- no candidate-number reuse;
- no retrospective renumbering;
- no in-place overwrite;
- explicit Marco records for skipped candidate numbers;
- lifecycle status `SUBMITTED_FOR_MARCO_REVIEW` at frozen delivery;
- the formal-review first-non-whitespace decision rule;
- exact decision vocabulary:
  - `APPROVE`
  - `BLOCK`
  - `DEFER`
  - `ACCEPT FINDING`
  - `NEEDS VERIFICATION`;
- candidate identity and hash information after the opening decision line;
- exact raw-byte length and lowercase SHA-256 binding;
- the non-circular artifact-identity model;
- candidate-specific external filenames;
- stable generic canonical installation paths;
- exact source-to-canonical byte-copy requirements;
- canonical adoption of the four task records;
- `GUARDRAILS.md` as highest standing operational authority;
- task-specific user authorization only within current guardrails;
- prohibition on ordinary authorization overriding permanent guardrails;
- the exact six-step guardrail-amendment process;
- the existing guardrail remaining controlling until amendment completion;
- more-restrictive interpretation and halt on conflict, ambiguity, stale records, or identity mismatch;
- separate specification, Marco review, user acceptance, implementation authorization, implementation, implementation review, and next-phase gates;
- `PROJECT_STATE.md` reflecting the actual active implementation authorization at commit time;
- the original Candidate 01 authorization as the first historical specification authorization;
- Candidate 04’s submission/provenance status;
- Candidate 05’s blocked and unauthorized-submission status;
- Candidate 06’s valid authorization provenance and blocked disposition;
- Candidate 07’s blocked and unauthorized-submission status;
- Candidate 08’s valid authorization provenance and blocked disposition;
- Candidate 09’s valid authorization provenance and blocked disposition;
- unchanged root `README.md`;
- no `.gitkeep` in `specifications/`, `handoffs/`, or `reviews/`;
- retained `src/.gitkeep`, `tests/.gitkeep`, and `artifacts/.gitkeep`;
- public-repository warnings and secret protections;
- Demo and production separation;
- no silent environment fallback;
- venue-specific adapter boundaries;
- decimal or fixed-point monetary arithmetic;
- no binary floating-point economic values;
- no profitability claim without reconciled evidence;
- no arbitrage characterization until all required legs are filled or contractually locked and payout rules are verified;
- no code;
- no tests;
- no credentials;
- no venue access;
- no funding;
- no orders or cancellations;
- no trading; and
- no Neo authorization.

No new architecture, implementation design, governance mechanism, path, phase, capability, acceptance gate, venue behavior, or future authorization was added.

---

## 7. Candidate 10 specification identity at delivery

The frozen Candidate 10 specification delivered with this handoff has:

| Artifact | Candidate | Raw bytes | SHA-256 |
|---|---|---:|---|
| `SPEC_repository_bootstrap_CANDIDATE_10.md` | `CANDIDATE_10` | `122041` | `6cff9ca01e0d3779d95ecea241ed83e1b47126117b1660e2066862b823f02b71` |

Marco must independently recompute this identity before review.

This handoff intentionally does not state its own final raw byte length or SHA-256. Its identity must be computed independently by Marco after delivery, avoiding a circular self-identity claim.

---

## 8. Fixed canonical installation targets preserved

If Candidate 10 is later reviewed, identity-bound, explicitly accepted by the user, and separately authorized for implementation, the fixed canonical installation targets remain:

```text
specifications/SPEC_repository_bootstrap.md
handoffs/HANDOFF_repository_bootstrap_spec.md
reviews/REVIEW_repository_bootstrap_spec.md
handoffs/HANDOFF_repository_bootstrap_implementation.md
```

Candidate 10 does not authorize or perform installation.

The candidate-specific external records remain distinct from these stable generic canonical paths.

---

## 9. Final proposed canonical tree preserved

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

`README.md` remains unchanged.

This tree is descriptive only. Candidate 10 does not authorize its creation.

---

## 10. Remaining unresolved questions

None.

Marco must independently review the exact Candidate 10 bytes. Candidate 10 remains proposed, noncanonical, and non-authorizing. The user must separately accept the exact identity-bound candidate before any implementation authorization can be considered.

---

## 11. Recommended Marco review focus

Marco should verify:

1. Both artifacts state `Candidate: CANDIDATE_10`.
2. Candidate 09 immediate-predecessor identities match exactly.
3. Candidate 09 is described consistently as Candidate 10’s immediate blocked predecessor.
4. Candidate 09 retains valid explicit authorization provenance and remains blocked.
5. Candidate 10 is described as prepared under the user’s explicit authorization.
6. Section 28 criterion 31 includes Candidate 08 and the complete lineage through Candidate 10.
7. Section 12 prohibits authorization inheritance from Candidate 08 and Candidate 09 as well as every earlier listed event.
8. Section 31.2 fixed decision 18 preserves Candidate 06, Candidate 08, and Candidate 09 valid authorization provenance without changing their blocked dispositions.
9. Candidate 09’s corrected Sections 5.4 and 19.5 remain preserved.
10. Candidate 09’s Section 7.1 direct-input model remains preserved apart from unavoidable Candidate 10 identity and predecessor updates.
11. Candidate 10 changes only the three authorized defects.
12. Every other Candidate 09 requirement is preserved.
13. Candidate 10 is `SUBMITTED_FOR_MARCO_REVIEW`, proposed, noncanonical, and non-authorizing.
14. Candidate acceptance remains separate from implementation authorization.
15. Repository implementation and Neo remain prohibited.
16. The specification identity in Section 7 matches Marco’s independent computation.
17. The handoff contains no self-declared final handoff identity.

A formal Marco review must use exactly one of these terms as its first non-whitespace text:

- `APPROVE`
- `BLOCK`
- `DEFER`
- `ACCEPT FINDING`
- `NEEDS VERIFICATION`

Candidate identity and hash information must follow that opening decision line.

---

## 12. Explicit confirmations

Candidate: CANDIDATE_10

Lifecycle status: `SUBMITTED_FOR_MARCO_REVIEW`

Bruno confirms:

- Candidate 09 is Candidate 10’s immediate blocked predecessor;
- Candidate 05 remains blocked and is not represented as having separately recorded explicit user authorization;
- Candidate 06 remains blocked and its valid explicit authorization provenance is preserved;
- Candidate 07 remains blocked and is not represented as having separately recorded explicit user authorization;
- Candidate 08 remains blocked and its valid explicit authorization provenance is preserved;
- Candidate 09 remains blocked and its valid explicit authorization provenance is preserved;
- Candidate 10 was prepared under the user’s explicit authorization;
- Candidate 10 authorization is distinct from Candidate 01 authorization, Candidate 04 submission, Candidate 05 submission, Candidate 06 authorization and blocked submission, Candidate 07 submission, Candidate 08 authorization and blocked submission, Candidate 09 authorization and blocked submission, candidate acceptance, and future implementation authorization;
- Candidate 10 does not retroactively authorize, validate, accept, broaden, unblock, canonicalize, or make installable Candidate 05, Candidate 06, Candidate 07, Candidate 08, or Candidate 09;
- Section 28 criterion 31 now includes Candidate 08 and the complete lineage through Candidate 10;
- Section 12 now prohibits inheritance from Candidate 08 and Candidate 09 as well as every earlier listed event;
- Section 31.2 preserves Candidate 06, Candidate 08, and Candidate 09 valid authorization provenance;
- every other Candidate 09 requirement was preserved without redesign;
- no canonical repository file was created, modified, deleted, staged, committed, or pushed;
- no branch, issue, pull request, release, or repository installation was created;
- no code was created or modified;
- no tests were created or executed;
- no project import occurred;
- no package was installed;
- no subprocess or shell command was executed;
- no network access occurred beyond reading the canonical GitHub repository;
- no credentials, secrets, account data, private URLs, or wallet data were accessed;
- no Kalshi Demo environment was accessed;
- no production environment was accessed;
- no Polymarket interaction occurred;
- no account was funded;
- no order was placed, amended, or canceled;
- no trading occurred;
- Marco’s review was not written;
- no candidate-acceptance record was written;
- no implementation authorization or implementation handoff was written;
- repository implementation remains prohibited; and
- Neo remains unauthorized.

---

## 13. Completion condition

The two frozen Candidate 10 artifacts are delivered for Marco’s independent review.

No candidate acceptance, implementation authorization, implementation handoff, Neo authorization, or later-phase authorization is requested or inferred.
