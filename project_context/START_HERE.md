# project_context/START_HERE

## 1. Purpose

Detailed orchestration and restart entry point for this project. This document routes readers and agents to the canonical governance and task records. It does not itself grant capabilities.

## 2. Canonical read order

1. root `START_HERE.md`
2. `project_context/START_HERE.md` (this file)
3. `project_context/GUARDRAILS.md`
4. `project_context/PROJECT_STATE.md`
5. `project_context/AUTHORIZATION_LOG.md`
6. `project_context/DECISION_LOG.md`
7. `project_context/AGENT_ROLES.md`
8. the accepted-candidate identity table recorded in the authorization chain
9. `specifications/SPEC_repository_bootstrap.md`
10. `reviews/REVIEW_repository_bootstrap_spec.md`
11. `handoffs/HANDOFF_repository_bootstrap_spec.md`
12. `handoffs/HANDOFF_repository_bootstrap_implementation.md`
13. relevant `project_context/ARTIFACT_INDEX.md` entries

## 3. Source-of-truth hierarchy

1. `project_context/GUARDRAILS.md` is the highest standing operational authority.
2. Exact user (Gustavo) authorization determines task-specific permission only within the current guardrails.
3. Ordinary task authorization cannot override a permanent guardrail.
4. `PROJECT_STATE.md`, `DECISION_LOG.md`, `AGENT_ROLES.md`, specifications, reviews, handoffs, artifacts, implementations, agent statements, conversation memory, and technical capability cannot weaken a current guardrail or expand task permission.
5. Gustavo remains the sole approval authority, including for guardrail amendments and task-specific work.
6. Any conflict, ambiguity, or stale record uses the more restrictive interpretation and halts the affected work.

## 4. Agent workflow

See `project_context/AGENT_ROLES.md` for the complete ten-step gated workflow among Gustavo, Marco, Bruno, and Neo.

## 5. Phase-gated process

Every material change follows: proposal, independent Marco review, explicit Gustavo approval, bounded authorization, implementation, Marco review of implementation, Gustavo acceptance or next-step authorization. No phase begins automatically when the previous one completes.

## 6. Current phase

The Candidate 10 documentation bootstrap is installed and accepted. The canonical accepted implementation commit is `e136be0b80f0370572e889d1075a11fc1b445348`. No later phase is active or authorized.

## 7. Record locations

- Accepted specification: `specifications/SPEC_repository_bootstrap.md`
- Marco's approval review: `reviews/REVIEW_repository_bootstrap_spec.md`
- Bruno's specification handoff: `handoffs/HANDOFF_repository_bootstrap_spec.md`
- Marco's implementation handoff: `handoffs/HANDOFF_repository_bootstrap_implementation.md`
- Current state: `project_context/PROJECT_STATE.md`
- Decisions: `project_context/DECISION_LOG.md`
- Authorizations: `project_context/AUTHORIZATION_LOG.md`
- Artifact references: `project_context/ARTIFACT_INDEX.md`
- Agent roles: `project_context/AGENT_ROLES.md`

Later specifications, reviews, handoffs, decisions, authorizations, and artifact references will be added at their corresponding canonical paths and indexed from the records above.

## 8. Pre-task checks

Before any task, an acting agent must verify: repository identity, HEAD, active authorization, task scope, permitted paths, environment permissions, and revocation status.

## 9. Absent-authorization rule

Absent authorization means prohibited. Nothing may be inferred from tools, access, prior work, or technical capability.

## 10. Stale/conflicting document procedure

On any stale or conflicting document, apply the more restrictive interpretation, halt the affected work, and escalate to Marco and Gustavo.

## 11. Formal review vocabulary pointer

See `project_context/AGENT_ROLES.md` and `specifications/SPEC_repository_bootstrap.md` Section 22 for the exact five formal Marco review decision terms: `APPROVE`, `BLOCK`, `DEFER`, `ACCEPT FINDING`, `NEEDS VERIFICATION`.

Conversation context is non-canonical. The canonical repository controls over chat memory, summaries, uploaded duplicates, mirrors, archives, old branches, and prior agent output.
