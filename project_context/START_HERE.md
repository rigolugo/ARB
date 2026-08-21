# project_context/START_HERE

## Purpose

Canonical governance and restart router. This file does not grant capability and does not duplicate the full current project phase.

## Canonical read order

1. root `START_HERE.md`
2. `project_context/START_HERE.md` (this file)
3. `project_context/GUARDRAILS.md`
4. `project_context/PROJECT_AGENT_DISPATCH_AUTHORITY.md`
5. `project_context/PROJECT_STATE.md`
6. `project_context/AGENT_ROLES.md`
7. `project_context/LOCAL_EXECUTION_ENVIRONMENT.md`
8. `project_context/AUTHORIZATION_LOG.md`
9. `project_context/DECISION_LOG.md`
10. `BROWSER_BRANCH_REPOSITORY_TRANSFER_WORKFLOW.md`
11. `project_context/MARCO_IMPLEMENTATION_REVIEW_PACKAGE_WORKFLOW.md`
12. task-specific accepted specifications, handoffs, reviews, artifacts, or evidence only when relevant to the active task

`project_context/ARTIFACT_INDEX.md` remains the canonical artifact-reference ledger and is consulted when task-specific artifact provenance is relevant.

## Authority hierarchy

1. Platform/system safety requirements.
2. `project_context/GUARDRAILS.md` as the highest standing project operational authority.
3. Exact active Gustavo task authorization within those guardrails.
4. `project_context/PROJECT_AGENT_DISPATCH_AUTHORITY.md` and `project_context/AGENT_ROLES.md` for current dispatch/correction and role procedure.
5. `project_context/PROJECT_STATE.md` for current accepted state facts.
6. `AUTHORIZATION_LOG.md` and `DECISION_LOG.md` as audit history.
7. Task-specific accepted specifications and evidence within their exact scope.

`LOCAL_EXECUTION_ENVIRONMENT.md` is operational context only. It does not grant capability and does not outrank the authorities above.

Gustavo remains the sole approval authority. Marco remains the independent orchestrator/reviewer. Bruno remains the standing specification author. Neo remains the standing implementation/test agent. A task-specific Gustavo authorization may temporarily permit a narrower different activity without changing a standing role.

## Current-chat authorization and logs

A bounded exact Gustavo prompt posted in the named agent's current project chat may itself be the operative task authorization. Canonical authorization and decision logs are audit history and need not pre-exist the task whose authorization or decision they later record. Logs cannot retroactively authorize out-of-scope activity, and missing task capability remains prohibited.

A named artifact is required when the active task identifies it as a controlling source, predecessor, exact-copy input, required evidence, or required deliverable.

## Current-state and source-binding freshness

`PROJECT_STATE.md` is the current accepted-state snapshot. Audit logs are historical records and may lag a later accepted technical state until a bounded governance update records it. Absence of a later event from an audit log is not evidence that the event did not occur; agents must use the authority hierarchy above, exact active Gustavo authorization, current canonical `main`, and task-specific accepted identities.

A repository-stored API/OpenAPI/AsyncAPI identity is immutable provenance for the exact source snapshot and operations for which it was reviewed. Its presence in canonical history does **not** make that snapshot a standing "current" venue specification, does not bind a different operation automatically, and does not authorize reuse for a later write surface.

When an active dispatch requires a `current`, `fresh`, `then-current`, or equivalent official source binding, the authorized agent must obtain or otherwise directly observe the official source during that task and record the task-current retrieval/observation identity required by the dispatch. A retained or historical source snapshot may substitute only when the exact active dispatch explicitly permits that substitution. If the required current source cannot be obtained or its identity cannot be established, halt rather than silently reusing an older canonical hash.

## Routing

- Permanent safety and capability floors: `GUARDRAILS.md`
- Dispatch, same-scope correction, risk-tier evidence, Gustavo-return triggers, and source-binding freshness semantics: `PROJECT_AGENT_DISPATCH_AUTHORITY.md`
- Current project state: `PROJECT_STATE.md`
- Standing roles: `AGENT_ROLES.md`
- Local Windows/Miniconda execution and shell conventions: `LOCAL_EXECUTION_ENVIRONMENT.md`
- Authorization audit: `AUTHORIZATION_LOG.md`
- Decision audit: `DECISION_LOG.md`
- Manual-browser repository transfer and remote verification: `../BROWSER_BRANCH_REPOSITORY_TRANSFER_WORKFLOW.md`
- Exact implementation-candidate review package and detached container identity: `MARCO_IMPLEMENTATION_REVIEW_PACKAGE_WORKFLOW.md`

## Fail-closed rule

If any governance record is stale, conflicting, ambiguous, identity-mismatched, or insufficient for a capability the task requires, use the more restrictive interpretation and halt the affected activity. Do not infer authority from technical capability, prior tasks, old candidates, repository state, historical source hashes, or missing log entries.
