# Marco Implementation Review Package Workflow

## Purpose

This file defines the standing exact-candidate transfer and verification contract for independent Marco review of Claude Code or Codex implementation candidates for `rigolugo/ARB`.

It applies to implementation candidates whether or not:

- the candidate is local-only;
- remote Git is permitted;
- a temporary review branch exists;
- manual browser transfer is selected;
- the implementer is Claude Code or Codex.

This workflow is a review-evidence requirement. It does not grant implementation, test execution, package installation, network, credential, venue, persistent-state, local-Git, remote-Git, push, PR, merge, or canonical-integration capability.

The active task still controls those capabilities.

## 1. Hard review gate

Every implementation candidate submitted for Marco review MUST make the exact candidate bytes independently available to Marco.

Default required artifacts:

```text
<TASK_ID>_MARCO_REVIEW.zip
<TASK_ID>_MARCO_REVIEW.zip.sha256
```

`READY_FOR_MARCO_REVIEW` is incomplete until the package and detached sidecar have been built, verified, and delivered or otherwise made available to Marco in the current review context.

The following are evidence but are not substitutes for candidate bytes:

- local candidate commit SHA;
- candidate tree SHA;
- changed-file byte counts;
- SHA-256 values;
- Git blob IDs;
- test counts;
- implementer-authored line numbers;
- implementer-authored static conformance matrices;
- prose completion reports.

If Marco does not have the exact candidate bytes, Marco MUST NOT issue `APPROVE` or `BLOCK` for implementation conformance.

Required disposition:

`NEEDS VERIFICATION`

Required reason:

`EXACT_CANDIDATE_REVIEW_PACKAGE_REQUIRED`

Marco may record a possible issue from the completion report, but until checked against the exact candidate bytes it remains a finding requiring verification rather than a confirmed implementation defect.

## 2. Preserve the candidate before correction

When a candidate reaches `READY_FOR_MARCO_REVIEW`, freeze it for review.

Do not modify the candidate merely because Marco or the implementer suspects a defect before Marco has received and reviewed the exact candidate package.

The purpose is to answer two separate questions in order:

1. What exact code did the implementer submit?
2. Does that exact code conform to the controlling contract?

If a correction is required after review, create a new candidate identity and a new review package. Do not overwrite the reviewed candidate evidence.

## 3. Default package contents

Unless the active task requires a stricter layout, create exactly one ZIP:

`<TASK_ID>_MARCO_REVIEW.zip`

with these top-level members:

```text
repository_payload/
candidate.patch
MANIFEST.txt
TEST_RESULTS.txt
```

The detached `<TASK_ID>_MARCO_REVIEW.zip.sha256` sidecar is NOT a ZIP member.

### 3.1 repository_payload/

`repository_payload/` MUST contain every changed repository path and no unlisted repository path.

Preserve exact repository-relative paths.

Example:

```text
repository_payload/src/arb/venues/kalshi/write_result_reconciliation.py
repository_payload/tests/test_kalshi_write_result_reconciliation.py
```

Do not flatten paths.

Do not add convenience copies.

Zero-byte changed files MUST be included.

### 3.2 candidate.patch

`candidate.patch` MUST represent the exact diff from the task-required base to the exact candidate commit/state.

Preferred generation when a candidate commit exists:

```text
git diff --binary <REQUIRED_BASE>..<CANDIDATE_COMMIT> -- <AUTHORIZED_CHANGED_PATHS...>
```

The patch MUST cover every changed path and MUST not include protected or unrelated paths.

If the task requires a single candidate whose parent is the required base, the patch base must still be the explicitly required base rather than an inferred branch point.

### 3.3 MANIFEST.txt

The manifest MUST report at least:

```text
task_id:
repository:
required_base:
required_tree_if_controlled:
required_parent_if_controlled:

worktree:
task_branch:

candidate_commit:
candidate_tree:
candidate_parent:

changed_path_count:
changed_paths:

for each changed path:
  path:
  raw_bytes:
  sha256:
  git_blob:

controlling_artifacts:
  filename/path:
  role:
  raw_bytes_if_controlled:
  sha256_if_controlled:
  git_blob_or_commit_if_controlled:

candidate_patch_bytes:
candidate_patch_sha256:

zip_filename:
container_identity_mode: DETACHED_AFTER_FINALIZATION
final_zip_bytes: POST_PACKAGE_EXTERNAL
final_zip_sha256: POST_PACKAGE_EXTERNAL
zip_sidecar_filename:

worktree_clean:
final_git_status_porcelain:
unexpected_paths:

network_used:
credential_activity:
venue_activity:
write_activity:
persistent_state_access:
persistent_state_mutation:
package_installation:
remote_git_writes:
```

`POST_PACKAGE_EXTERNAL` is a literal sentinel. The embedded manifest MUST NOT claim the final container byte length or final container SHA-256 as a computed value.

The manifest MUST be complete before the ZIP is finalized. After ZIP finalization, the ZIP MUST NOT be rewritten merely to insert its own final bytes or hash.

This sequence is invalid:

```text
compute ZIP hash
-> edit embedded MANIFEST
-> rebuild ZIP
-> claim old hash
```

Use blocker:

`REVIEW_PACKAGE_CONTAINER_SELF_REFERENCE_INVALID`

All candidate and internal-member identity values MUST be derived from the final candidate/package state. Do not manually reuse stale values from an earlier completion report.

### 3.4 TEST_RESULTS.txt

Record exact executed commands and exact outcomes required by the active task, including where applicable:

- targeted test command and result;
- related regression command and result;
- full regression command and result;
- subtest counts;
- exit codes;
- elapsed time when available;
- confirmation of mocked/offline network behavior when required;
- any test not run and the exact reason.

Do not substitute a summary count for the exact commands when the task requires command provenance.

## 4. Package exclusions

The package MUST NOT contain:

- `.git/` internals;
- unrelated repository files;
- virtual environments;
- caches;
- build output;
- logs unrelated to required test evidence;
- downloaded dependencies;
- credentials;
- private keys;
- tokens;
- secret environment values;
- authentication headers;
- venue account data not explicitly authorized as review evidence;
- editor or OS metadata;
- unrelated evidence artifacts.

The review package is for code/test candidate review, not a repository backup.

## 5. Exact-byte preservation

Packaging MUST preserve changed-file bytes exactly.

Do not normalize:

- line endings;
- Unicode;
- BOM state;
- trailing whitespace;
- final newline state;
- Python formatting;
- JSON formatting;
- Markdown formatting.

Read the final changed file bytes and write those exact bytes to the corresponding `repository_payload/` member.

## 6. Deterministic finalization and verification order

The standing order is:

```text
T0  freeze exact candidate/state
T1  generate exact candidate.patch
T2  generate TEST_RESULTS.txt
T3  generate MANIFEST.txt with all candidate/internal identities and
    POST_PACKAGE_EXTERNAL final-container sentinels
T4  build ZIP exactly once from final internal members
T5  close/finalize ZIP
T6  reopen ZIP read-only
T7  verify exact member set and every internal member
T8  compare repository_payload members byte-for-byte to frozen candidate
T9  verify per-file bytes/SHA-256/Git blob
T10 verify candidate.patch bytes/SHA-256 and base-to-candidate coverage
T11 verify MANIFEST internal identities and literal external-container sentinels
T12 compute final ZIP raw bytes/SHA-256
T13 create detached .sha256 sidecar
T14 verify sidecar exact bytes/content
T15 recompute ZIP raw bytes/SHA-256 and require unchanged identity
T16 report package + sidecar identities externally
T17 READY_FOR_MARCO_REVIEW
```

Any write to the ZIP after T5 invalidates the package and requires rebuilding from T3/T4 under a new deterministic finalization attempt.

This workflow does not require bit-for-bit reproducibility of ZIP metadata across different packaging programs unless an active task separately requires it. It requires exact verification of the one finalized package delivered to Marco.

## 7. Detached final-container identity

The standing container identity mode is:

```text
container_identity_mode =
DETACHED_AFTER_FINALIZATION
```

After the ZIP is finalized and internal verification passes:

1. compute the immutable ZIP raw byte length;
2. compute lowercase SHA-256 of the immutable ZIP;
3. create the detached sidecar;
4. verify the sidecar;
5. recompute/recheck the ZIP identity without modifying the ZIP;
6. report ZIP and sidecar identities externally.

The sidecar MUST be UTF-8/ASCII-compatible text with exactly:

```text
<64-lowercase-hex-sha256><two ASCII spaces><exact ZIP basename><LF>
```

Requirements:

```text
BOM =
NONE

line_count =
1

final_newline =
LF

path_in_sidecar =
BASENAME_ONLY
```

The sidecar itself is NOT a ZIP member.

The completion report MUST report:

```text
review_zip_filename
review_zip_raw_bytes
review_zip_sha256

review_zip_sidecar_filename
review_zip_sidecar_raw_bytes
review_zip_sidecar_sha256
```

Useful blockers:

```text
REVIEW_PACKAGE_SIDECAR_MISSING
REVIEW_PACKAGE_SIDECAR_FORMAT_MISMATCH
REVIEW_PACKAGE_SIDECAR_ZIP_SHA256_MISMATCH
REVIEW_PACKAGE_FINAL_CONTAINER_IDENTITY_MISMATCH
```

## 8. Mandatory post-creation verification

After ZIP creation, reopen the ZIP read-only and independently verify:

1. the exact member set;
2. every `repository_payload/` path;
3. every payload member byte-for-byte against the final candidate file;
4. per-file byte length;
5. per-file SHA-256;
6. per-file Git blob ID when applicable;
7. `candidate.patch` byte length and SHA-256 plus exact base-to-candidate coverage;
8. every internal member named by the manifest;
9. the manifest's internal identities and literal final-container sentinels;
10. no unexpected member exists;
11. final ZIP byte length and SHA-256 outside the ZIP;
12. the detached sidecar's exact bytes and content;
13. unchanged final ZIP identity after sidecar creation.

Any mismatch invalidates the package.

Useful blocker labels:

```text
REVIEW_PACKAGE_MEMBER_SET_MISMATCH
REVIEW_PACKAGE_BYTE_MISMATCH
REVIEW_PACKAGE_SHA256_MISMATCH
REVIEW_PACKAGE_GIT_BLOB_MISMATCH
REVIEW_PACKAGE_PATCH_MISMATCH
REVIEW_PACKAGE_MANIFEST_MISMATCH
REVIEW_PACKAGE_UNEXPECTED_PATH
REVIEW_PACKAGE_CONTAINER_SELF_REFERENCE_INVALID
REVIEW_PACKAGE_SIDECAR_MISSING
REVIEW_PACKAGE_SIDECAR_FORMAT_MISMATCH
REVIEW_PACKAGE_SIDECAR_ZIP_SHA256_MISMATCH
REVIEW_PACKAGE_FINAL_CONTAINER_IDENTITY_MISMATCH
EXACT_CANDIDATE_REVIEW_PACKAGE_REQUIRED
```

## 9. Candidate identity rules

When a candidate commit exists, verify and report:

- candidate commit SHA;
- candidate tree SHA;
- candidate parent SHA;
- exact changed-path set against the required base;
- exact Git blob for every changed path.

If the candidate is local-only, the inability of GitHub to resolve the commit is expected and is not itself a defect.

The review package is the transfer mechanism that gives Marco the exact local candidate bytes.

If a remotely accessible candidate also exists, Marco SHOULD independently compare remote identities with the package, but the remote copy does not authorize integration and does not excuse a package mismatch.

## 10. Implementer final-artifact root

The shared logical destination is:

`IMPLEMENTER_FINAL_ARTIFACT_ROOT`

The active implementation task MUST resolve it before package creation. Codex and Claude may resolve independent local destinations through their respective task/environment contracts; this shared workflow does not prescribe either implementer's machine-specific absolute path.

Final locations:

```text
<IMPLEMENTER_FINAL_ARTIFACT_ROOT>\<TASK_ID>_MARCO_REVIEW.zip
<IMPLEMENTER_FINAL_ARTIFACT_ROOT>\<TASK_ID>_MARCO_REVIEW.zip.sha256
```

The resolved root MUST be outside the repository unless an active task explicitly authorizes a repository artifact path. Do not use a visualization/rendering directory as the final delivery location unless the active task explicitly binds that directory.

Temporary package construction may use task-authorized temporary storage, but the final immutable ZIP and sidecar MUST be placed in the resolved final artifact root.

An unset, unavailable, ambiguous, or non-writable root blocks `READY_FOR_MARCO_REVIEW`:

`IMPLEMENTER_FINAL_ARTIFACT_ROOT_UNRESOLVED`

## 11. Implementer completion rule

Claude Code and Codex MUST include the review-package step before `READY_FOR_MARCO_REVIEW`:

```text
bounded implementation
-> required tests
-> static self-review
-> exact candidate commit/state
-> build Marco review package
-> finalize ZIP without self-referential container identity
-> reopen and verify every internal member
-> compute final ZIP identity externally
-> create and verify detached sidecar
-> recompute and confirm unchanged ZIP identity
-> report package and sidecar identities
-> READY_FOR_MARCO_REVIEW
```

If the active task prohibits artifact generation, then it cannot validly require Marco implementation review through this default workflow. The implementer must stop with:

`EXACT_CANDIDATE_REVIEW_PACKAGE_REQUIRED`

and report the capability conflict rather than claiming review readiness.

## 12. Marco intake procedure

On receiving an implementation completion report, Marco MUST first determine whether the exact candidate is independently inspectable.

### 12.1 Package present

Marco MUST:

1. independently compute ZIP raw bytes/SHA-256;
2. independently read and verify the detached sidecar;
3. require sidecar ZIP hash to equal the independently computed ZIP hash;
4. inspect the exact ZIP member set;
5. verify the manifest `container_identity_mode` and `POST_PACKAGE_EXTERNAL` sentinels;
6. inspect every repository payload;
7. independently compute changed-file bytes/SHA-256/Git blobs;
8. verify `candidate.patch` and candidate/base topology;
9. review test evidence;
10. perform static contract review;
11. only then issue a formal disposition.

For large implementations use:

`SPEC REQUIREMENT -> CODE LOCATION -> TEST/EVIDENCE -> STATUS`

The detached sidecar is integrity evidence, not authorization. A correct hash never grants remote Git, venue, credential, or integration capability.

### 12.2 Package absent

Marco MUST return:

`NEEDS VERIFICATION`

with:

`EXACT_CANDIDATE_REVIEW_PACKAGE_REQUIRED`

Marco MUST NOT convert completion-report prose into a formal `BLOCK` or `APPROVE` of code conformance.

### 12.3 Reported concern before package review

A completion report may reveal a possible defect. Marco may state it as:

`POSSIBLE FINDING — REQUIRES CANDIDATE-BYTE VERIFICATION`

Do not direct code correction until the exact candidate has been inspected, unless an independent safety requirement requires immediate halt of an action. For ordinary offline implementation review, preserve the candidate and inspect first.

## 13. Relationship to Browser-Branch Repository Transfer Workflow

`../BROWSER_BRANCH_REPOSITORY_TRANSFER_WORKFLOW.md` governs one optional transfer method:

`repository_transfer_mode: MANUAL_BROWSER_TEMPORARY_BRANCH`

This review-package workflow is broader and applies even when browser transfer is not selected.

A browser-transfer package may satisfy the Marco review-package requirement only if it contains every artifact and verification required here.

Review-package creation does not authorize:

- browser transfer;
- push;
- remote branch creation;
- PR creation;
- merge;
- remote `main` update.

## 14. Relationship to remote review branches

A temporary remote review branch is an optional additional review/transfer mechanism only when separately permitted.

The standing sequence is:

```text
exact candidate
-> exact candidate review package
-> Marco static/test review
-> APPROVE/BLOCK
-> separately authorized remote transfer/integration steps, if any
```

A remote branch must never be created merely to compensate for a missing review package when remote Git is prohibited.

## 15. Formal review dispositions

For implementation review:

- `APPROVE`: exact candidate bytes reviewed; no material controlling-contract defect remains.
- `BLOCK`: exact candidate bytes reviewed; at least one material controlling-contract defect is confirmed.
- `DEFER`: review intentionally postponed for a project reason other than missing exact candidate evidence.
- `ACCEPT FINDING`: a finding is accepted under the project review process where that disposition is appropriate.
- `NEEDS VERIFICATION`: exact evidence required to determine conformance is missing or unresolved.

Missing candidate bytes/package is always `NEEDS VERIFICATION`, not `BLOCK`.

## 16. Completion boundary

This workflow ends when Marco has independently reviewed the exact candidate and issued the formal technical disposition.

No approval automatically grants:

- canonical installation;
- remote Git write;
- venue access;
- credential use;
- account access;
- execution;
- another project stage.

Each later capability remains separately controlled by the active task.
