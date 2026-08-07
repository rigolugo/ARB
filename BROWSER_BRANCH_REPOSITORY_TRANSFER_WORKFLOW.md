# Browser-Branch Repository Transfer Workflow

## Status

This file defines the default repository-transfer workflow for bounded implementation tasks in `rigolugo/ARB`.

It is intended for Marco and Neo Project Knowledge.

It replaces any default assumption that Neo must push directly from its execution environment.

## Core workflow

For an implementation task that selects this workflow:

1. Gustavo posts Neo's bounded implementation dispatch.
2. Neo implements locally from the exact authorized base.
3. Neo creates a clean local implementation commit only when commit creation is authorized.
4. Neo does not push.
5. Neo creates a browser-upload package, detached SHA-256 file, and manifest.
6. Gustavo creates the exact authorized temporary branch from the exact required base through GitHub's browser interface.
7. Gustavo uploads only the authorized package payload and creates the temporary-branch commit.
8. Gustavo leaves `main` unchanged and sends Marco the remote branch name and browser-created commit SHA.
9. Marco independently reviews the remote branch commit against the authorized base, paths, artifact identities, and accepted contract.
10. If Marco issues `APPROVE`, all fast-forward conditions pass, and the original Gustavo dispatch explicitly permitted it, Marco performs a non-force fast-forward update of `main` to the reviewed commit.
11. Marco verifies the resulting `main` HEAD and tree.
12. No later phase begins automatically.

## Task-scoped merge authorization

The workflow itself does not grant standing authority to merge every future branch.

A Gustavo-posted Neo dispatch may include:

```text
repository_transfer_mode: MANUAL_BROWSER_TEMPORARY_BRANCH
marco_fast_forward_main_after_approval: PERMITTED
```

When those exact fields are present, Gustavo's posting of that dispatch provides task-scoped authority for:

- Neo to prepare the browser-upload package;
- Gustavo to create and populate the temporary branch manually;
- Marco to review the resulting remote commit; and
- Marco to perform a non-force fast-forward of `main` only after an `APPROVE` decision and all required checks pass.

No separate merge-approval artifact or later approval message is required for that task.

If `marco_fast_forward_main_after_approval` is missing, ambiguous, or `PROHIBITED`, Marco may review but may not update `main`.

## Neo responsibilities

Neo must:

- verify the exact repository, branch base, controlling artifact identities, writable paths, protected paths, and capabilities;
- implement only the bounded scope;
- preserve a clean worktree;
- create a local commit only when explicitly authorized;
- avoid requesting GitHub write credentials;
- avoid repeated push attempts when browser transfer is selected;
- package exactly the authorized repository payload;
- include zero-byte placeholder files correctly;
- produce:
  - one ZIP with a single `repository_payload/` top-level directory;
  - one detached `.sha256`;
  - one manifest with per-file raw byte lengths and SHA-256 values;
- exclude `.git/`, caches, logs, temporary files, credentials, and every unlisted path;
- verify the package before delivery;
- report the local branch, base, local commit, payload members, package identity, and clean-worktree status.

Neo's local commit SHA is evidence of the local implementation state. It is not required to equal the browser-created remote commit SHA.

Neo must not:

- push;
- ask for GitHub credentials;
- merge;
- modify `main`;
- create a pull request;
- treat packaging as a new implementation stage;
- modify repository bytes during packaging.

## Gustavo responsibilities

Gustavo must:

- create the exact temporary branch from the exact required base;
- upload only the contents under `repository_payload/`;
- preserve repository-relative paths;
- ensure zero-byte files are included;
- create the browser commit on the temporary branch;
- leave `main` unchanged;
- not merge;
- provide Marco:
  - repository;
  - temporary branch name;
  - browser-created commit SHA;
  - expected base;
  - package and manifest when requested.

The browser-created commit may have a different SHA from Neo's local commit because commit metadata differs. That is expected.

## Marco responsibilities

Before review, Marco must verify:

- canonical repository;
- current `main` HEAD;
- expected base;
- temporary branch existence;
- reviewed commit existence;
- reviewed commit ancestry;
- branch and commit relationship;
- changed-path set;
- protected paths;
- exact-copy target bytes;
- package-manifest consistency where applicable;
- absence of unlisted paths;
- absence of secrets or prohibited content;
- accepted specification conformance;
- task capability boundaries.

Marco must issue one formal decision:

- `APPROVE`
- `BLOCK`
- `DEFER`
- `ACCEPT FINDING`
- `NEEDS VERIFICATION`

## Streamlined remote review for byte-identical approved packages

When Marco has already substantively approved the exact package bytes and the browser-created remote bytes are proven byte-identical, the remote review may be limited to:

- canonical-main drift;
- exact base and ancestry;
- exact changed paths;
- protected paths;
- exact remote byte/blob identities against the approved bytes;
- temporary branch/ref resolution;
- unexpected commits/files;
- transfer-mode compliance; and
- the non-force fast-forward condition.

A second full semantic review is not required solely because identical approved bytes have been transferred remotely.

Any changed byte, changed path, material ancestry difference, protected-path difference, changed material evidence, or inability to prove byte identity reopens semantic review and prevents streamlined approval until resolved.

## Fast-forward conditions

Marco may update `main` only when all are true:

1. the task dispatch states:
   `marco_fast_forward_main_after_approval: PERMITTED`;
2. Marco's decision is `APPROVE`;
3. current `main` still equals the exact authorized base;
4. the reviewed commit is a descendant of that base;
5. the temporary branch resolves to the reviewed commit;
6. the reviewed tree contains exactly the authorized changes;
7. every protected path is unchanged;
8. all required exact-copy identities match;
9. no prohibited capability or content is observed;
10. a non-force update is possible.

The update must use non-force behavior.

Marco must stop without updating `main` if:

- `main` moved;
- the reviewed commit is not descended from the required base;
- the branch does not resolve to the reviewed commit;
- additional commits or paths are unexplained;
- exact bytes do not match;
- a protected path changed;
- a material requirement failed;
- force would be required.

## Post-update verification

After the non-force update, Marco must verify:

- `main` resolves to the reviewed commit;
- the resulting tree matches the approved tree;
- no unexpected commit or path was introduced;
- no temporary-branch deletion or later-phase action was performed unless separately authorized.

## Default capability treatment

When this workflow is selected:

| Capability | Default |
|---|---|
| Neo local implementation | As stated in task dispatch |
| Neo local commit | Only if explicitly permitted |
| Neo push | `PROHIBITED` |
| Neo credential request | `PROHIBITED` |
| Browser-upload package generation | `PERMITTED` when stated |
| Gustavo temporary-branch creation/upload | Per task dispatch |
| Marco remote branch review | `PERMITTED` |
| Marco non-force fast-forward of `main` | Only when task dispatch explicitly says `PERMITTED` |
| Force update | `PROHIBITED` |
| Pull request | `PROHIBITED` unless separately authorized |
| Merge commit | `PROHIBITED` |
| Later-phase work | `PROHIBITED` |

Anything not explicitly permitted remains prohibited.
