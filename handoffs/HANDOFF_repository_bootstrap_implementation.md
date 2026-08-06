# Marco Implementation Handoff — Repository Bootstrap Candidate 10

**Artifact:** `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md`  
**Candidate:** `CANDIDATE_10`  
**Author:** Marco  
**Date:** 2026-08-06  
**Classification:** `DOCUMENTATION_ONLY_REPOSITORY_BOOTSTRAP_IMPLEMENTATION`  
**Implementation agent:** Neo  
**Canonical installation target:** `handoffs/HANDOFF_repository_bootstrap_implementation.md`  
**Authorization source:** the bounded prompt Gustavo posts in Neo's current project chat  
**Merge authorization:** None

## 1. Purpose

Implement the accepted Candidate 10 documentation-only repository bootstrap on one temporary branch.

This handoff is a controlling implementation record and future exact-copy source. It does not independently authorize execution. Gustavo's current-chat Neo dispatch supplies the operative authorization and exact capability matrix.

## 2. Canonical repository and immutable base

- repository: `rigolugo/ARB`
- required visibility: `public`
- required default branch: `main`
- exact required base: `da629e93ce9255c28ecb485ee2b67bfc0c0ccb86`
- expected tracked tree before implementation: `README.md` only
- expected `README.md` bytes decode to:

```text
# ARB
Arbitrage research Project
```

Stop before editing on any unexplained repository, visibility, branch, HEAD, tree, or README mismatch.

## 3. Controlling exact identities

### Accepted Candidate 10 specification

- filename: `SPEC_repository_bootstrap_CANDIDATE_10.md`
- raw bytes: `122041`
- SHA-256: `6cff9ca01e0d3779d95ecea241ed83e1b47126117b1660e2066862b823f02b71`

### Accepted Bruno handoff

- filename: `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md`
- raw bytes: `17497`
- SHA-256: `be3dccbb16b270edb67297baf40bcf3944edeaa4877a30e13e1eecdbca823c7e`

### Marco approval review

- filename: `REVIEW_repository_bootstrap_spec_CANDIDATE_10.md`
- raw bytes: `2997`
- SHA-256: `78ff8e6252f0a45421ed479b4bdb87628138e1c4e4d5e919bc81816863d3d0b6`

### This implementation handoff

- filename: `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md`
- final raw bytes and SHA-256 are supplied externally in Gustavo's Neo dispatch after this file is frozen.

Any filename, byte-length, or SHA-256 mismatch is a halt condition.

## 4. Authorized branch model

The permitted temporary branch is:

`candidate-10-repository-bootstrap`

Neo may:

- create this exact branch from the exact required base;
- create the authorized files;
- create one implementation commit;
- push this exact branch.

Neo may not:

- modify `main`;
- rebase;
- amend another commit;
- force-push;
- create another branch;
- create a pull request;
- merge;
- delete the branch;
- create an issue, release, or tag.

## 5. Writable-path matrix

Neo may create or modify only:

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

Protected paths include:

```text
README.md
```

Every unlisted path is prohibited.

## 6. Exact-copy mappings

Neo must copy these sources byte-for-byte:

| External source | Canonical target |
|---|---|
| `SPEC_repository_bootstrap_CANDIDATE_10.md` | `specifications/SPEC_repository_bootstrap.md` |
| `HANDOFF_repository_bootstrap_spec_CANDIDATE_10.md` | `handoffs/HANDOFF_repository_bootstrap_spec.md` |
| `REVIEW_repository_bootstrap_spec_CANDIDATE_10.md` | `reviews/REVIEW_repository_bootstrap_spec.md` |
| `HANDOFF_repository_bootstrap_implementation_CANDIDATE_10.md` | `handoffs/HANDOFF_repository_bootstrap_implementation.md` |

For every mapping:

1. verify source filename, raw bytes, and SHA-256;
2. copy without normalization or reformatting;
3. verify target raw bytes and SHA-256;
4. halt on any mismatch.

Do not alter line endings, Unicode normalization, BOM state, whitespace, or formatting.

## 7. Authored bootstrap documents

Neo must author the non-copy bootstrap files exactly within Candidate 10 requirements:

- `START_HERE.md`
- `.gitignore`
- `project_context/START_HERE.md`
- `project_context/GUARDRAILS.md`
- `project_context/PROJECT_STATE.md`
- `project_context/DECISION_LOG.md`
- `project_context/ARTIFACT_INDEX.md`
- `project_context/AGENT_ROLES.md`
- `project_context/AUTHORIZATION_LOG.md`
- `src/.gitkeep`
- `tests/.gitkeep`
- `artifacts/.gitkeep`

The accepted specification controls their required sections and content.

No `.gitkeep` may exist in:

- `specifications/`
- `handoffs/`
- `reviews/`

`src/`, `tests/`, and `artifacts/` contain only `.gitkeep` in this implementation.

## 8. Capability matrix

| Capability | Status |
|---|---|
| Read canonical GitHub repository | `PERMITTED` |
| Read supplied exact external artifacts | `PERMITTED` |
| Read Git history needed to verify the base | `PERMITTED` |
| Create exact temporary branch | `PERMITTED` |
| Create or modify listed paths | `PERMITTED` |
| Deterministic documentation and path validation | `PERMITTED` |
| Raw byte and SHA-256 validation | `PERMITTED` |
| Secret-pattern inspection | `PERMITTED` |
| Local shell/subprocess use strictly for authorized file and Git operations | `PERMITTED` |
| Create one implementation commit | `PERMITTED` |
| Push exact temporary branch | `PERMITTED` |
| Modify or merge `main` | `PROHIBITED` |
| Rebase, amend, or force-push | `PROHIBITED` |
| Pull request, issue, release, or tag | `PROHIBITED` |
| Source-code creation | `PROHIBITED` |
| Test-source creation | `PROHIBITED` |
| Application or project test execution | `PROHIBITED` |
| Project imports | `PROHIBITED` |
| Package installation | `PROHIBITED` |
| Network access other than required GitHub clone/fetch/push | `PROHIBITED` |
| Local research-data access | `PROHIBITED` |
| Artifact generation outside required implementation evidence | `PROHIBITED` |
| Credential use other than existing GitHub connector/session needed for the authorized push | `PROHIBITED` |
| Kalshi Demo access | `PROHIBITED` |
| Production reads or writes | `PROHIBITED` |
| Polymarket interaction | `PROHIBITED` |
| Account funding | `PROHIBITED` |
| Orders, cancellations, or trading | `PROHIBITED` |

Anything not explicitly `PERMITTED` is prohibited.

## 9. Required deterministic validation

Neo must verify:

1. exact repository, visibility, default branch, and base;
2. initial tree and unchanged README;
3. exact four source identities;
4. exact four source-to-target byte copies;
5. exact changed-path set;
6. no unlisted files;
7. required headings and statements in authored documents;
8. canonical read-order consistency;
9. `GUARDRAILS.md` precedence language;
10. dispatch and authorization history without invented approval artifacts;
11. Demo/production separation;
12. no-live-trading default;
13. fixed-point or decimal monetary policy;
14. no secret-like content;
15. placeholder placement;
16. no code or tests;
17. no venue or trading activity;
18. final branch and workspace state.

Do not run application tests or import project code.

## 10. Halt conditions

Stop without further changes on:

- baseline mismatch;
- artifact identity mismatch;
- unavailable controlling source;
- unlisted path need;
- protected-path modification;
- exact-copy mismatch;
- contradictory accepted requirement;
- secret or credential-like content;
- need for code, tests, packages, venue access, data access, or unauthorized network activity;
- need to alter `README.md`;
- inability to satisfy Candidate 10 without redesign;
- branch, commit, or push requirement beyond the permitted model.

Report exact expected and observed facts.

## 11. Commit

If all checks pass:

- create one commit on `candidate-10-repository-bootstrap`;
- recommended commit message:

`Bootstrap canonical project documentation from accepted Candidate 10`

- push that exact branch;
- do not merge.

## 12. Required Neo handoff

Return the compact YAML required by `NEO_PROJECT_OPERATING_CONTRACT_V2.md`, including:

- dispatch source and task ID;
- required and observed base;
- controlling artifact identities;
- writable, new, and protected paths;
- changed and created files;
- exact-copy results;
- requirements addressed;
- validation performed;
- self-check findings;
- all negative capability evidence;
- branch name and base;
- final commit SHA;
- push status;
- unchanged README result;
- unlisted-path result;
- secret-pattern result;
- final workspace status.

Use:

`status: READY_FOR_MARCO_REVIEW`

only if the complete bounded implementation, validation, commit, and authorized push succeed.

Otherwise use:

`status: BLOCKED`

and name the exact blocker.

## 13. Completion condition

Stop after pushing the temporary branch and returning the required evidence.

Do not:

- merge;
- request or infer acceptance;
- begin another phase;
- access a venue;
- use credentials beyond the authorized GitHub operation;
- fund an account;
- submit or cancel an order;
- trade.
