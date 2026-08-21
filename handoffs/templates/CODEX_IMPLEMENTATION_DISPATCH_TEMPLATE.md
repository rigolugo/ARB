# Codex Implementation Dispatch Template

> TEMPLATE ONLY. This file does not authorize work.

## Task identity

`task_id: <EXACT_TASK_ID>`

`classification: <OFFLINE_IMPLEMENTATION_AND_TEST_ONLY | OTHER_EXACT_CLASS>`

`risk_posture: <FAIL_CLOSED | OTHER>`

## Canonical repository

Repository:

`rigolugo/ARB`

Required exact base:

`<40-char commit SHA>`

Required tree, if controlled:

`<tree SHA or NOT_CONTROLLED>`

Before editing, verify repository/base and stop on unexplained mismatch.

## Controlling artifacts

For each controlling artifact provide:

- canonical/external path or filename;
- role;
- raw bytes if controlled;
- SHA-256 if controlled;
- Git blob/commit if controlled.

## Objective

<One bounded implementation objective.>

## Writable paths

Exactly:

- `<path 1>`
- `<path 2>`

All other repository paths are protected.

If another path is materially required, stop with:

`SCOPE_EXPANSION_REQUIRED`

## Required technical behavior

1. <requirement>
2. <requirement>
3. <requirement>

The controlling specification remains authoritative.

## Codex Python / Windows sandbox preflight

For an ordinary offline ARB Python implementation task, use these defaults unless the task states
a stricter value:

```text
Python test execution = YES
Python interpreter = %ARB_CODEX_PYTHON_EXE%
network during Python tests = NO
known WinError-5 sandbox fallback = PERMITTED
```

The task author must explicitly state each of those four fields as `YES` / `NO` or `PERMITTED` /
`PROHIBITED`, as applicable. A permitted fallback does not itself authorize tests; the specific
Python test command must already be authorized by the task.

Before material Python execution, run these `cmd.exe` checks:

```cmd
echo %ARB_CODEX_PYTHON_EXE%
"%ARB_CODEX_PYTHON_EXE%" --version
"%ARB_CODEX_PYTHON_EXE%" -c "import sys; print(sys.executable)"
"%ARB_CODEX_PYTHON_EXE%" -c "import tempfile; print(tempfile.gettempdir())"
```

Do not replace `%ARB_CODEX_PYTHON_EXE%` with bare `python` merely because `where python` returns
an executable. An unset, missing, non-executable, or wrong-environment variable is a stop condition.
Preserve the Codex-local `TEMP`, `TMP`, and `ARB_CODEX_TEMP_ROOT` values and verify
`TEMP == TMP == ARB_CODEX_TEMP_ROOT` unless the task explicitly provides another Codex task-local
root.

Mandatory probe/fallback algorithm:

```text
A. Validate ARB_CODEX_PYTHON_EXE, TEMP, TMP, and ARB_CODEX_TEMP_ROOT.
B. With %ARB_CODEX_PYTHON_EXE%, run a nested-temp probe that creates/writes/renames/deletes a
   child file, creates/removes a nested directory, and shutil.rmtree()s the tempfile.mkdtemp() root.
C. PASS -> run the authorized Python tests normally inside the filesystem sandbox.
D. Exact known unelevated-sandbox descendant failure only — correct temp root, mkdtemp succeeds,
   then PermissionError and/or errno 13 and/or WinError 5 on descendant mutation/cleanup -> run
   only the authorized offline Python test process outside the filesystem sandbox as the same
   unelevated user, and only when this task marks the fallback PERMITTED.
E. Any other probe or environment failure -> STOP.
F. Clean only exact task-created temp material; use the same narrowly bounded outside-sandbox
   cleanup only if the exact known WinError-5 condition blocks cleanup.
G. Verify git status --porcelain and the task's final cleanliness requirement.
```

The fallback is process-bounded to the authorized Python test command and necessary cleanup. It
does not grant a shell-wide unrestricted session, administrator rights, global sandbox disable,
ACL changes, network, credentials, venue access, or additional writable repository paths. Every
capability remains exactly as stated by the active task.

## Capability matrix

### Permitted

- canonical repository read/synchronization: `<YES/NO>`
- offline source editing: `<YES/NO>`
- offline test editing: `<YES/NO>`
- test execution: `<YES/NO>`
- artifact generation: `YES` for the mandatory Marco review package unless the task explicitly selects an equivalent exact-byte review mechanism
- local task branch/worktree: `<YES/NO>`
- local commit: `<YES/NO>`
- temporary remote review branch: `<YES/NO>`

### Prohibited unless explicitly changed above

- package installation;
- dependency changes;
- arbitrary internet access;
- venue network access;
- real credentials/private keys;
- secret environment reads;
- account access;
- WebSockets;
- funding;
- CREATE/CANCEL/amend/decrease/batch writes;
- production activity;
- force-push;
- direct `main` update.

## Worktree/Git rules

- Use an isolated Codex worktree/task branch.
- Base it on the exact required commit.
- Do not implement directly on local `main`.
- Do not rebase onto a different base.
- Do not amend accepted canonical commits.
- If remote review-branch push is permitted, push only the task candidate branch.
- Never push directly to `main`.
- `main` integration occurs only after separate Marco review returns `APPROVE`.

## Required tests

Run exactly:

1. `<command; when Python is used, express it as "%ARB_CODEX_PYTHON_EXE%" ...>`
2. `<command; when Python is used, express it as "%ARB_CODEX_PYTHON_EXE%" ...>`
3. `<full regression command; when Python is used, express it as "%ARB_CODEX_PYTHON_EXE%" ...>`

Report exact pass/fail counts.

## Static review

Return:

`SPEC REQUIREMENT -> CODE LOCATION -> TEST/EVIDENCE -> STATUS`

## Mandatory Marco review package

Before returning `READY_FOR_MARCO_REVIEW`, create and verify the exact candidate review package defined by:

`project_context/MARCO_IMPLEMENTATION_REVIEW_PACKAGE_WORKFLOW.md`

Resolve the final-artifact root before package creation. The ordinary Codex default is:

```text
IMPLEMENTER_FINAL_ARTIFACT_ROOT =
%ARB_CODEX_ARTIFACT_ROOT%
```

An active task may specify a different exact Codex root. An unset, unavailable, ambiguous, or
non-writable root prohibits `READY_FOR_MARCO_REVIEW`.

Default final artifacts:

```text
<IMPLEMENTER_FINAL_ARTIFACT_ROOT>\<TASK_ID>_MARCO_REVIEW.zip
<IMPLEMENTER_FINAL_ARTIFACT_ROOT>\<TASK_ID>_MARCO_REVIEW.zip.sha256
```

The package MUST contain:

```text
repository_payload/
  <every changed repository path with exact final bytes>
candidate.patch
MANIFEST.txt
TEST_RESULTS.txt
```

Requirements:

- include every changed path and no unlisted repository path;
- generate `candidate.patch` from the exact required base to the exact candidate;
- report bytes/SHA-256/Git blob for each changed file;
- report candidate commit/tree/parent;
- report patch bytes/SHA-256;
- complete `MANIFEST.txt` before ZIP finalization with:

  ```text
  container_identity_mode = DETACHED_AFTER_FINALIZATION
  final_zip_bytes = POST_PACKAGE_EXTERNAL
  final_zip_sha256 = POST_PACKAGE_EXTERNAL
  ```

- do not embed computed final ZIP bytes/SHA-256 in `MANIFEST.txt`;
- finalize the ZIP, reopen it read-only, and verify every internal member;
- compute and externally report final ZIP bytes/SHA-256;
- create and verify the required detached `.zip.sha256` sidecar;
- recompute final ZIP bytes/SHA-256 after sidecar creation and require the identity to be unchanged;
- compare every payload member byte-for-byte with the final candidate file;
- verify the exact member set;
- preserve the candidate unchanged until Marco reviews it.

A completion report, hashes, Git blobs, test counts, or static conformance matrix do not substitute for the package.

If the final-artifact root, package, or sidecar cannot be created or verified, do not return
`READY_FOR_MARCO_REVIEW`. Return the applicable blocker, including:

```text
IMPLEMENTER_FINAL_ARTIFACT_ROOT_UNRESOLVED
REVIEW_PACKAGE_SIDECAR_MISSING
REVIEW_PACKAGE_SIDECAR_FORMAT_MISMATCH
EXACT_CANDIDATE_REVIEW_PACKAGE_REQUIRED
```

## Completion return

Return:

1. `status: READY_FOR_MARCO_REVIEW`
2. exact starting `HEAD`
3. starting tree if controlled
4. worktree/task branch
5. changed paths
6. bytes/SHA-256/Git blob for each changed file
7. exact test commands/results
8. full regression result
9. static conformance matrix
10. network activity
11. credential activity
12. venue/write activity
13. local candidate commit
14. local commit parent
15. remote review branch if permitted
16. final `git status --porcelain`
17. Marco review-package filename
18. Marco review ZIP bytes/SHA-256
19. Marco review sidecar filename and bytes/SHA-256
20. candidate patch bytes/SHA-256
21. confirmation that the ZIP was reopened and all internal members were verified, including every payload member byte-for-byte
22. confirmation that final ZIP identity was recomputed after sidecar creation and remained unchanged

Stop after candidate and review-package preparation. Do not update `main`.
