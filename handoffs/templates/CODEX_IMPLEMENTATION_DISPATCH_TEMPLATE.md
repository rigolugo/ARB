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

1. `<command>`
2. `<command>`
3. `<full regression command>`

Report exact pass/fail counts.

## Static review

Return:

`SPEC REQUIREMENT -> CODE LOCATION -> TEST/EVIDENCE -> STATUS`

## Mandatory Marco review package

Before returning `READY_FOR_MARCO_REVIEW`, create and verify the exact candidate review package defined by:

`MARCO_IMPLEMENTATION_REVIEW_PACKAGE_WORKFLOW.md`

Default filename:

`<TASK_ID>_MARCO_REVIEW.zip`

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
- report ZIP bytes/SHA-256;
- reopen the ZIP after creation;
- compare every payload member byte-for-byte with the final candidate file;
- verify the exact member set;
- preserve the candidate unchanged until Marco reviews it.

A completion report, hashes, Git blobs, test counts, or static conformance matrix do not substitute for the package.

If the package cannot be created or verified, do not return `READY_FOR_MARCO_REVIEW`. Return:

`EXACT_CANDIDATE_REVIEW_PACKAGE_REQUIRED`

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
18. Marco review-package bytes/SHA-256
19. candidate patch bytes/SHA-256
20. confirmation that the package was reopened and every payload member verified byte-for-byte

Stop after candidate and review-package preparation. Do not update `main`.
