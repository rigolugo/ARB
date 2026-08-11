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
- artifact generation: `<YES/NO>`
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

Stop after candidate preparation. Do not update `main`.
