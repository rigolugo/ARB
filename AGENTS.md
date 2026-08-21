# ARB Codex Implementer Instructions

## Purpose

This repository is the canonical implementation repository for `rigolugo/ARB`.

Codex is a bounded implementation and testing agent. Implementation does not imply acceptance.
A candidate becomes canonical only after separate project review and an explicit integration step.

Workflow labels such as Marco, Bruno, Codex, reviewer, implementer, or specification author
describe project functions only. They are not identity credentials and do not grant capability.

This file contains stable repository-wide instructions. The active task dispatch supplies the
variable task scope: exact base, writable paths, network/credential/Git permissions, controlling
artifacts, and required tests.

## 1. Required startup

Before modifying any repository file:

1. Verify the repository is `rigolugo/ARB`.
2. Identify the current branch/worktree and current `HEAD`.
3. Read root `START_HERE.md`.
4. Read `project_context/START_HERE.md`.
5. Follow the canonical read order it specifies for the active task.
6. Read the active task dispatch.
7. Identify the exact task-required base commit and verify the task worktree is based on it.
8. Identify every controlling specification, handoff, review, evidence item, or source binding
   named by the task.
9. Verify any task-supplied byte length, SHA-256, Git blob, tree, or commit identities.
10. Identify the exact writable paths and all protected paths.
11. Identify the exact allowed capabilities for network, credentials, venue access, execution,
    package installation, local Git, remote Git, and artifact generation.

Stop on an unexplained mismatch. Do not silently rebase or advance a task onto a newer base.

## 2. Capability separation

Treat each capability independently. One does not imply another.

Examples:

- repository read does not imply repository write;
- source editing does not imply test execution;
- test execution does not imply package installation;
- local Git does not imply remote Git;
- remote review-branch push does not imply `main` update;
- Demo access does not imply production access;
- public read does not imply authenticated read;
- authenticated read does not imply write;
- credential presence does not imply credential use;
- installed write-capable code does not imply permission to execute venue writes.

Anything not explicitly permitted by the active task is prohibited.

## 3. Public repository and secrets

This repository is public.

Never commit, print, log, serialize into artifacts, or otherwise expose:

- API keys;
- private keys;
- tokens;
- account secrets;
- private URLs;
- sensitive account data;
- local secret files;
- real credential values.

Credential presence never grants permission to read or use credentials.

Unless the active task explicitly permits credential use:

- do not read credential files;
- do not read secret environment variables;
- do not load real private keys;
- do not sign real venue requests;
- do not access authenticated accounts.

Tests must use mocks, fakes, synthetic credentials, or synthetic key material when the task permits
such fixtures.

## 4. Venue and environment separation

Kalshi Demo and Kalshi production are separate environments.

Never infer:

`Demo authorization -> production authorization`

Never substitute a Demo endpoint for production or a production endpoint for Demo.

If the observed environment contradicts the active task, halt closed before any venue request.

A task that does not explicitly permit venue network access must perform no Kalshi, Polymarket,
RPC, WebSocket, or other venue/network activity.

## 5. Network behavior

Repository synchronization is separate from venue/network capability.

Unless the active task explicitly permits the specific network activity:

- no Kalshi network access;
- no Polymarket network access;
- no RPC access;
- no arbitrary web requests;
- no package-registry access;
- no unrelated external-repository access.

For an offline implementation task, remain offline after any explicitly permitted canonical
repository synchronization.

## 6. Codex worktree and branch model

Implementation work must occur in an isolated Codex worktree or task branch.

Do not implement directly on canonical local `main`.

If the Codex app has already created an isolated worktree for the thread, use that worktree.
Do not create a nested worktree inside it.

The task worktree/branch must start from the exact task-required base.

Do not:

- amend accepted canonical commits;
- rebase onto a different base without instruction;
- merge unrelated branches;
- force-push;
- force-update any ref;
- update remote `main` during implementation;
- create or delete remote branches unless explicitly permitted by the task.

Local branch/commit creation is permitted only when the active task permits it.

## 7. Candidate-review boundary

Normal ARB implementation flow:

1. Codex works in an isolated worktree/task branch.
2. Codex implements only the authorized scope.
3. Codex runs the required tests and static self-review.
4. Codex creates a candidate commit only when the task permits local commits.
5. Codex builds and verifies the exact Marco review package defined by `MARCO_IMPLEMENTATION_REVIEW_PACKAGE_WORKFLOW.md`.
6. Codex reports exact candidate evidence and the review-package byte length/SHA-256.
7. Only then may Codex return `READY_FOR_MARCO_REVIEW`.
8. Independent project review evaluates that exact packaged candidate.
9. Only after review returns `APPROVE` may a separately permitted integration step update `main`.
10. `main` must be advanced by a non-force fast-forward only.

Passing tests do not equal approval.

Codex must not update `main` merely because implementation is complete.

A local candidate commit SHA, hashes, Git blobs, test counts, or Codex's own conformance matrix do not substitute for the exact candidate bytes in the review package.

If Codex cannot build or verify the required review package, it MUST NOT claim `READY_FOR_MARCO_REVIEW`; report `EXACT_CANDIDATE_REVIEW_PACKAGE_REQUIRED`.

Once a candidate is ready for review, preserve it unchanged until Marco has received and reviewed the exact package. If a correction is later required, produce a new candidate and a new package.

## 8. Remote review branches

Remote Git is prohibited unless the active task explicitly permits it.

When a task permits a temporary remote review branch:

- push only the exact candidate commit/branch named by the task;
- do not push to `main`;
- do not force-push;
- do not create unrelated remote refs;
- report the remote branch name and commit SHA.

A remote review branch exists for independent review only. Its existence does not authorize
integration to `main`.

A remote review branch does not remove the standing Marco review-package requirement unless the active task explicitly selects an equivalent exact-byte review mechanism and Marco can independently retrieve every changed byte and the exact base-to-candidate diff.

## 9. Writable-path discipline

Modify only paths explicitly writable in the active task.

Do not modify adjacent files for convenience.

Examples of scope expansion:

- editing `__init__.py` when it is not writable;
- editing `pyproject.toml` when it is not writable;
- adding dependencies;
- changing unrelated tests;
- editing project governance/state documentation;
- adding runners, helpers, or utilities outside the allowed path set.

If a materially required change needs an additional path, stop and report:

`SCOPE_EXPANSION_REQUIRED`

## 10. Local environment

Target runtime: CPython 3.12.

Default local Conda environment: `pmresearch`.

Typical Windows repository path: `C:\b1\kals\ARB`.

Do not install or upgrade packages unless explicitly authorized.

Preserve exact repository bytes when the task is byte/hash sensitive. On Windows, repository-local
LF behavior is preferred:

`git config core.autocrlf false`
`git config core.eol lf`

Do not change global Git line-ending configuration for ARB tasks.

When shell syntax matters, state whether commands are for PowerShell or `cmd.exe`.
Do not mix PowerShell backticks with `cmd.exe` caret continuations.

### 10.1 Codex Python interpreter contract

For Codex ARB Python execution, use `%ARB_CODEX_PYTHON_EXE%`. Do not rely on bare `python`.
`where python` is informational only and does not select the Codex interpreter.

Before material Codex Python execution, run these `cmd.exe` checks:

```cmd
echo %ARB_CODEX_PYTHON_EXE%
"%ARB_CODEX_PYTHON_EXE%" --version
"%ARB_CODEX_PYTHON_EXE%" -c "import sys; print(sys.executable)"
"%ARB_CODEX_PYTHON_EXE%" -c "import tempfile; print(tempfile.gettempdir())"
```

The expected project environment is CPython 3.12 in `pmresearch`; no particular 3.12 patch
version is a permanent requirement. An unset, missing, non-executable, or wrong-environment
`%ARB_CODEX_PYTHON_EXE%` is an environment stop condition. Do not automatically fall back to
bare `python`, `py`, a Microsoft Store alias, Codex-bundled Python, or another Conda environment.

### 10.2 Codex TEMP/TMP and mandatory nested-temp probe

Codex ARB test processes must preserve the configured Codex-local `TEMP`, `TMP`, and
`ARB_CODEX_TEMP_ROOT` values. Verify `TEMP == TMP == ARB_CODEX_TEMP_ROOT` unless the active task
explicitly supplies another Codex task-local root. Do not redefine a machine-specific absolute
Codex temp path as a shared or Claude requirement.

Before any authorized Python test suite, use `%ARB_CODEX_PYTHON_EXE%` to run a synthetic
nested-temp probe. In one new `tempfile.mkdtemp()` root, the probe must:

1. create and write a child file;
2. rename and delete the child file;
3. create and remove a nested directory; and
4. remove the probe root with `shutil.rmtree()`.

Record whether every operation passed. This probe validates the environment; it is not an ARB
test.

The known Codex Windows sandbox condition is narrowly limited to all of these facts:

- the Windows sandbox is `unelevated`;
- the temp root resolves correctly;
- `tempfile.mkdtemp()` succeeds; and
- a descendant file/directory mutation or recursive cleanup then fails with `PermissionError`,
  errno 13, and/or WinError 5.

Only that characterized descendant-write/cleanup failure qualifies for the fallback below.
Wrong or missing `%ARB_CODEX_PYTHON_EXE%`, wrong `TEMP`/`TMP`, syntax or import failure, a test
assertion failure, dependency failure, repository permission failure, an unknown filesystem error,
or a network or credential requirement remains a hard stop and must not be classified as sandbox
noise.

### 10.3 Process-bounded test fallback

If and only if the active task already authorizes the specific offline Python test command and the
pre-test probe fails with the exact known condition above, Codex may run only that already-authorized
offline Python test process outside the filesystem sandbox as the same unelevated Windows user.

The fallback preserves all active-task limits: no elevation or administrator rights, no global
sandbox disable, no repository or host ACL changes, and no expansion of network, venue, credential,
repository-path, or other capability. When the task prohibits network access, the outside-sandbox
Python process remains offline. This is not a shell-wide unrestricted session; it is bounded to the
authorized Python test command plus necessary cleanup of exact task-created temp material.

After test execution, remove task-created temp files/directories, verify that probe artifacts and
owned test temp material are gone, and run `git status --porcelain`. If cleanup is blocked by the
same known WinError-5 condition, it may occur outside the filesystem sandbox as the same unelevated
user, limited to the exact task-created temp paths. Never delete unrelated temp material.

For normal ARB test execution, do not request or use administrator rights, switch to an elevated
sandbox when the host cannot install it, disable sandboxing globally, loosen repository or host
ACLs, or take ownership of repository/system directories.

## 11. Numerical and identity correctness

Follow the controlling technical specification.

Where exact monetary/quantity arithmetic is required:

- use `Decimal`;
- do not substitute binary floating point;
- preserve accepted lexical/fixed-point constraints.

Preserve opaque venue identifiers exactly.

Do not:

- synthesize complement prices unless explicitly permitted;
- fabricate missing venue fields;
- infer fills from order limits;
- infer an order did not reach the venue merely because a read returned zero matches;
- call something arbitrage unless required economic/contractual legs are actually lockable.

## 12. Testing

Tests are evidence, not proof of conformance.

For every implementation, as required by the task:

1. run task-specific tests;
2. run required targeted regressions;
3. run full repository regression;
4. perform static review against the controlling specification.

Offline tasks must use mocks, fakes, and synthetic material only.

Do not weaken assertions merely to make tests pass.
Do not delete required tests.

When deterministic evidence is required, control nondeterministic inputs such as clocks, UUIDs,
ordering, random values, and synthetic transport behavior.

## 13. Static self-review

Before completion, produce a traceability matrix:

`SPEC REQUIREMENT -> CODE LOCATION -> TEST/EVIDENCE -> STATUS`

Use:

- `PASS`
- `FAIL`
- `NOT_APPLICABLE`
- `UNRESOLVED`

A known static-contract failure remains a failure even if tests pass.

## 14. Completion report

Every implementation candidate should report, when applicable:

- task ID;
- exact starting base commit;
- starting tree when required;
- worktree/task branch;
- changed paths;
- raw byte size of every changed file;
- SHA-256 of every changed file;
- Git blob ID of every changed file;
- exact test commands;
- exact pass/fail counts;
- full-regression result;
- static conformance summary;
- network activity;
- credential activity;
- venue activity;
- write activity;
- local commit SHA;
- local commit parent;
- remote review branch if explicitly permitted;
- final `git status --porcelain`;
- Marco review-package filename;
- Marco review-package raw byte length;
- Marco review-package SHA-256;
- candidate patch raw byte length and SHA-256.

Do not claim zero activity unless the task environment and evidence actually support that claim.

Preferred completion status:

`READY_FOR_MARCO_REVIEW`

That status is valid only after the exact review package has been created, reopened, byte-verified, and made available for Marco review.

## 15. Stop conditions

Stop rather than guessing on:

- canonical repository mismatch;
- required-base mismatch;
- controlled tree mismatch;
- controlling-artifact identity mismatch;
- missing required controlling artifact;
- unexplained protected-path change;
- required dependency not authorized;
- required additional writable path;
- environment ambiguity;
- unexpected credential requirement;
- unexpected venue/network requirement;
- material contradiction in the controlling specification;
- inability to create or verify the required Marco review package.

Report the exact expected condition and the exact observed condition.

## 16. Project progression

Do not infer authorization for later stages.

ARB progresses incrementally through Demo execution and exact reconciliation before later
production observation or execution stages.

Demo results are not production profitability evidence.

A later stage requires its own explicit task and capabilities.
