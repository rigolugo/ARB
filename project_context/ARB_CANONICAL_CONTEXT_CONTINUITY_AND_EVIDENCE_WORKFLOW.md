# ARB Canonical Context Continuity and Evidence Workflow

## Purpose

This workflow prevents material ARB knowledge from existing only in a chat and
prevents a fresh Marco, Bruno, Claude, Codex, reviewer, or implementer chat from
having to reconstruct project state from prior conversations.

It applies to `rigolugo/ARB`.

It has two equally important goals:

1. **Do not lose important work.**
2. **Do not create unnecessary file sprawl.**

This file defines continuity, milestone capture, evidence preservation,
bootstrap, canonicalization, and handoff procedure. It does not grant
repository writes, Git writes, network access, credential use, venue access,
production access, or any other capability.

Platform/system safety requirements, active task capability limits, canonical
guardrails, and controlling technical artifacts still control.

---

## 1. Core continuity theorem

A fresh ARB chat MUST be able to recover the material accepted project state
from canonical project artifacts plus a small task-specific handoff.

Prior chat history is not a required project dependency.

The intended model is:

```text
fresh chat
  -> exact canonical repository/base
  -> canonical START_HERE router
  -> current routed checkpoint/state
  -> artifact/evidence index
  -> task-specific controlling artifacts and accepted evidence
  -> small current-task handoff
  -> continue work
```

A prior conversation may contain useful historical context, but it MUST NOT be
the only durable source for a material fact needed by future ARB work.

---

## 2. What counts as an important milestone

An **important milestone** is any event that materially changes what a future
ARB chat must know to continue correctly.

At minimum, the following are milestones when they occur:

- a specification is accepted, blocked, superseded, or installed;
- an implementation is approved, blocked, corrected, or canonically installed;
- canonical `main` advances for an accepted project change;
- an empirical execution produces a terminal result;
- a live/read-only probe establishes or falsifies a material external
  assumption;
- a route/stage decision changes;
- a risk hold, release, writer-eligibility theorem, or execution-domain theorem
  changes;
- an unresolved write/exposure/reconciliation theorem changes;
- an external source conflict is discovered or resolved;
- a current-source binding is established;
- a material credential/environment/runtime issue changes the interpretation
  of an execution result;
- a material correction is accepted after a blocked predecessor;
- a new fact changes the narrowest next action;
- a substantial body of work would take significant time to reconstruct if the
  current chat disappeared.

Minor formatting edits, exploratory dead ends with no retained conclusion, and
reproducible scratch work need not become milestones.

---

## 3. Mandatory milestone canonicalization gate

Every important milestone MUST be captured canonically before it is treated as
fully closed, unless the active task lacks authority to perform the canonical
write.

For each milestone, ensure that a fresh chat can recover:

```text
WHAT happened
WHY it matters
EXACT result/theorem
AUTHORITY of the result
EVIDENCE supporting it
EXACT artifact identities
WHAT remains unresolved
WHAT is the next bounded action
```

### 3.1 Preferred canonical carriers — minimize file count

Do **not** create a new file for every observation.

Prefer updating existing canonical carriers in this order:

1. **Current routed checkpoint/state**
   - preserve the latest accepted project theorem and current route.
2. **`project_context/ARTIFACT_INDEX.md`**
   - preserve exact artifact/evidence identities and locators.
3. **Existing task-specific spec/handoff/review/evidence record**
   - preserve detail in the artifact that already owns the subject.
4. **Decision/authorization logs**
   - when the milestone is primarily an audit decision/authorization event.
5. **A new dedicated artifact**
   - only when the material has independent controlling, audit, provenance, or
     reproducibility value and does not fit cleanly in an existing carrier.

The goal is **few durable canonical files with high information density**, not
one file per chat or one file per command.

### 3.2 When a new checkpoint is justified

A new routed checkpoint is justified when:

- the project route/stage materially changes;
- the accepted safety/capability theorem changes;
- an execution result changes what future work may do;
- a canonical implementation/install milestone changes the current state;
- the prior checkpoint would become misleading if left as the last routed
  current state.

Do not create a new checkpoint for trivial activity.

### 3.3 If canonical writes are not authorized

If the current task cannot write the repository, the task MUST NOT silently end
with chat-only milestone state.

Instead produce one bounded **canonicalization/install handoff package**
containing:

- exact milestone summary;
- exact canonical base;
- exact files to add/update;
- exact bytes/SHA-256;
- required state/index/checkpoint changes;
- supporting evidence;
- stop boundary.

That package becomes a required predecessor for the next authorized
canonicalization task.

---

## 4. Canonical-context-first rule

Before any of the following:

- new external research;
- prior-chat recovery;
- a correction specification caused by an allegedly missing fact;
- a new empirical probe intended to answer an allegedly unresolved assumption;
- asking the user to reconstruct prior project context;
- declaring that evidence is unavailable;

the active agent MUST first inspect the canonical repository for the exact fact,
assumption, source identity, result, or unresolved question.

At minimum, when relevant to the active task, inspect:

1. root `START_HERE.md`;
2. `project_context/START_HERE.md`;
3. the latest routed canonical checkpoint(s);
4. `project_context/ARTIFACT_INDEX.md`;
5. the exact controlling specification/handoff/review;
6. task-specific source-binding/evidence records;
7. exact implementation constants or embedded source records when the
   implementation itself preserves reviewed provenance;
8. archived canonical artifacts explicitly referenced by those files.

Do not infer that a fact is absent merely because its standalone source file is
not present at an expected path.

Search for:

- exact SHA-256;
- exact byte length;
- source-binding name;
- operation/path name;
- key semantic phrase;
- artifact filename;
- task ID;
- accepted theorem/result.

A fact preserved in a controlling spec, accepted evidence record, canonical
checkpoint, or reviewed embedded source-binding record counts as canonical
project knowledge within that artifact's authority and scope.

---

## 5. No chat-only material facts

A material fact MUST NOT remain available only in conversation history after it
becomes necessary for future ARB work.

Material facts include, when relevant:

- accepted technical decisions;
- exact execution outcomes;
- external-interface assumptions relied upon by a spec or implementation;
- empirical observations;
- source URLs and source identities;
- source freshness status;
- unresolved risks/holds;
- capability conclusions;
- canonical artifact identities;
- important negative findings;
- route-selection facts;
- contradictions between sources;
- reasons a task failed closed;
- facts needed to reproduce or interpret a future review.

Before context disposal, handoff, or project-stage advancement, each material
fact MUST be either:

### A. Canonically installed

Stored or represented in an accepted canonical repository artifact with enough
provenance to recover its meaning and authority.

or:

### B. Canonically referenced as local/noncanonical evidence

When the raw evidence must not be committed, canonical project state MUST still
record enough information to preserve the theorem:

- evidence class;
- exact filename or logical identity;
- raw byte length when known;
- SHA-256 when known;
- observation/execution timestamp when known;
- source/interface;
- sanitized structural facts;
- authority classification;
- storage classification such as `LOCAL_ONLY`;
- whether raw bytes are required for future verification;
- what conclusion the evidence supports;
- what conclusion it explicitly does not support.

Secret-bearing or sensitive raw evidence MUST NOT be committed merely to satisfy
continuity.

---

## 6. Evidence authority classification

Every material transferred or canonicalized evidence item SHOULD be classified
as one of:

```text
CONTROLLING_ARB_REQUIREMENT
ACCEPTED_CANONICAL_ARB_ARTIFACT
DIRECT_EMPIRICAL_OBSERVATION
OFFICIAL_EXTERNAL_SOURCE_NONCONTROLLING
OTHER_NONCONTROLLING_RESEARCH
ARB_INFERENCE
UNRESOLVED
```

For Kalshi-specific material,
`OFFICIAL_EXTERNAL_SOURCE_NONCONTROLLING` may be rendered as
`OFFICIAL_KALSHI_SOURCE_NONCONTROLLING`.

Do not silently promote:

- prior-chat conclusions;
- documentation examples;
- historical source snapshots;
- Demo observations;
- implementer assertions;

into controlling requirements.

A finding becomes binding on implementation only through the applicable active
task or an accepted controlling ARB artifact.

---

## 7. Source evidence and freshness

Canonical preservation and current-source freshness are separate properties.

A historical OpenAPI/AsyncAPI/documentation snapshot may remain valuable
canonical evidence even when it is not task-current.

For every relied-on external source preserve, when available:

- source URL;
- source class;
- observation/retrieval timestamp;
- exact raw byte length;
- SHA-256;
- schema/API version;
- material operation/path/schema semantics;
- freshness classification;
- supersession/conflict notes.

Use explicit status such as:

```text
TASK_CURRENT
HISTORICAL_CORROBORATION
SUPERSEDED
CURRENTNESS_NOT_PROVEN
```

### 7.1 Public source snapshots

When a public, non-sensitive external source materially controls reproducibility
and exact raw bytes are safely available, prefer retaining a canonical
repository-resident copy or lossless archive **only if the bytes add material
future value**.

Do not retain duplicate copies merely because they exist.

If the exact semantics, bytes, SHA-256, source URL, and necessary projection are
already losslessly preserved in an accepted canonical artifact, a duplicate
standalone source file is optional unless later byte-level reinspection is
likely to be necessary.

### 7.2 Freshness-required tasks

If an active controlling task requires a `current`, `fresh`, `then-current`, or
equivalent source binding, historical canonical evidence does not automatically
satisfy that freshness requirement.

However, before obtaining new evidence, the agent MUST inspect and report the
historical canonical evidence already available so the new task answers only
the actual freshness gap rather than rediscovering the entire interface.

---

## 8. Canonical empirical-evidence pattern

For authenticated, secret-bearing, account-specific, or otherwise sensitive
execution evidence, use:

```text
raw evidence
  -> LOCAL_ONLY / protected location
  -> exact bytes + SHA-256
  -> sanitized deterministic projection
  -> canonical evidence/result record
```

The canonical record should preserve enough information to establish:

- exact task;
- exact canonical base;
- authorized capability;
- request/attempt counts;
- endpoint/method identities when permitted;
- terminal outcome;
- relevant returned structural facts;
- retry/redirect counts;
- mutation/write counts;
- raw evidence identities;
- sanitized evidence identities;
- unresolved implications;
- next route.

Never commit:

- private keys;
- credential values;
- signatures;
- populated authentication headers;
- unnecessary raw account data.

---

## 9. Mandatory handoff completeness audit

When the user asks for a handoff to a new chat, the active Marco MUST perform a
**handoff completeness audit before packaging the handoff**.

The handoff is not complete until this audit is done.

### 9.1 Audit scope

Review all material work available to the current task, including:

- current-chat generated artifacts;
- user-returned execution/review packages;
- accepted local-only evidence;
- current task scratch artifacts that produced retained conclusions;
- predecessor packages explicitly relied upon;
- current canonical repository;
- current routed checkpoint/state;
- artifact index;
- controlling spec/handoff/review;
- source-binding/evidence records;
- any prior-chat recovery artifacts already imported into the current task.

### 9.2 Required classification

Every material noncanonical item MUST be classified as exactly one of:

```text
CANONICAL_ALREADY
MUST_CANONICALIZE_BEFORE_HANDOFF
LOCAL_ONLY_BUT_CANONICAL_REFERENCE_REQUIRED
REQUIRED_NONCANONICAL_INPUT_FOR_NEXT_CHAT
TRANSIENT_DISPOSABLE
```

### 9.3 Handoff blocking rule

A handoff MUST NOT be represented as continuity-complete while any item remains:

```text
MUST_CANONICALIZE_BEFORE_HANDOFF
```

unless repository write/install capability is not authorized.

If installation is not authorized, the handoff MUST include a complete
canonicalization package and explicitly state:

```text
CANONICALIZATION_PENDING
```

with the exact files, paths, bytes, hashes, and required updates.

### 9.4 Local-only evidence rule

For every:

```text
LOCAL_ONLY_BUT_CANONICAL_REFERENCE_REQUIRED
```

verify that the canonical repository already preserves, or the pending
canonicalization package will preserve:

- sanitized material facts;
- bytes/SHA identities;
- evidence class;
- storage classification;
- what it proves;
- what it does not prove.

### 9.5 New-chat package rule

The handoff package MUST contain all artifacts the new chat actually requires
that are not already reliably available from canonical repository paths.

Do not make the user reconstruct required inputs.

Do not duplicate large canonical artifacts in the handoff when an exact
canonical path + commit/tree + identity is sufficient and the receiving chat
has repository access.

When repository access is unavailable to the receiving agent, include the
required canonical artifacts in the handoff bundle.

---

## 10. Handoff audit report

For substantial handoffs, include a compact audit table:

```text
ITEM
-> CURRENT LOCATION
-> CANONICAL STATUS
-> REQUIRED ACTION
-> NEXT-CHAT NEED
```

Example:

```text
B1 sanitized execution result
-> local review ZIP
-> LOCAL_ONLY_BUT_CANONICAL_REFERENCE_REQUIRED
-> install sanitized theorem + raw ZIP SHA in checkpoint/evidence record
-> raw ZIP not needed by next chat after canonicalization
```

The audit exists to prevent silent loss, not to create another permanent file.
It may live inside the handoff itself unless a controlling task requires a
separate artifact.

---

## 11. Task-closure canonicalization checklist

Before declaring a milestone fully closed or disposable, verify:

```text
[ ] important milestone identified
[ ] accepted theorem/result recorded
[ ] controlling artifact installed or exact accepted identity recorded
[ ] current routed checkpoint reflects the accepted state
[ ] artifact index updated when applicable
[ ] material source/evidence provenance preserved
[ ] local-only evidence has canonical identity/projection when needed
[ ] superseded artifacts clearly marked
[ ] unresolved risks explicit
[ ] next bounded route explicit
[ ] START_HERE still routes a fresh chat to the correct current state
[ ] no material current-chat fact remains chat-only
```

If all items are satisfied, the chat may be safely disposable for project
continuity.

---

## 12. Fresh-chat bootstrap procedure

At the beginning of a new ARB work chat whose task depends on existing project
state:

1. verify the canonical repository is `rigolugo/ARB`;
2. resolve the exact canonical `main`/required base when repository state is
   relevant;
3. read the shared project instructions;
4. read canonical `START_HERE`;
5. read the currently routed checkpoint(s);
6. read the relevant artifact index entries;
7. read only the task-specific controlling artifacts/evidence required for the
   active task;
8. identify:
   - confirmed current facts;
   - historical-but-preserved facts;
   - genuinely unresolved facts;
   - freshness gaps;
   - capability boundaries;
9. only then decide whether prior-chat recovery, new research, or a new probe is
   required.

Do not make prior chat history the first recovery mechanism when canonical
project state can answer the question.

---

## 13. Prior-chat recovery is an exception path

Prior-chat recovery is appropriate only when:

- a material fact is not represented sufficiently in canonical artifacts;
- a referenced noncanonical artifact is unavailable;
- provenance needed for a current decision was never canonicalized;
- an exact predecessor package exists only in the prior chat;
- the user explicitly asks to recover prior conversation information.

When used, recover the smallest necessary context.

Require the prior chat to provide:

- exact fact;
- authority class;
- provenance;
- artifact filenames;
- bytes/SHA-256 when known;
- freshness;
- conflicts;
- unresolved items;
- complete supporting artifacts needed by the receiving chat.

After recovery, material newly recovered facts MUST be evaluated by the
milestone canonicalization gate.

Repeated dependence on the same old chat is evidence of a continuity defect.

---

## 14. Handoff minimization rule

A handoff to a fresh chat SHOULD contain only:

```text
repository
exact canonical main/base/tree when relevant
current task ID
current task capability envelope
current routed checkpoint
controlling artifact identities
pending canonicalization status, if any
noncanonical inputs required for this task
exact deliverables / stop boundary
```

Do not paste the entire project history when canonical routing exists.

Do not require the receiving chat to determine which artifacts are needed from
a large undifferentiated bundle.

When additional task artifacts are required, provide them together with the
dispatch in accordance with the standing ARB new-chat packaging rule.

---

## 15. Artifact-index requirements

`project_context/ARTIFACT_INDEX.md` remains the canonical artifact-reference
ledger for entries indexed there.

For new material entries, record when applicable:

- task/artifact ID;
- canonical repository path;
- artifact role;
- authority;
- status;
- bytes;
- SHA-256;
- Git blob/commit;
- predecessor/successor or supersession relation;
- source/evidence class;
- freshness classification;
- local-only raw evidence identity if applicable;
- routed checkpoint containing the accepted theorem.

An index entry is a locator/provenance record. It does not replace the
controlling content of the indexed artifact.

Avoid indexing temporary scratch files that carry no durable theorem or
provenance value.

---

## 16. START_HERE routing requirement

`project_context/START_HERE.md` must remain a restart router, not a long-form
project-history dump.

When a newly accepted checkpoint becomes necessary to understand the current
project state, START_HERE SHOULD route to it.

When a specialized workflow becomes standing procedure, START_HERE or the
shared project instructions SHOULD point to that workflow rather than copying
the workflow in full.

---

## 17. Static context review before new work

Before deciding that a missing fact requires code/spec correction or another
external probe, perform a static context review:

```text
QUESTION / ASSUMPTION
-> CANONICAL LOCATIONS SEARCHED
-> EXISTING EVIDENCE
-> AUTHORITY
-> FRESHNESS
-> ACTUAL GAP
-> NARROWEST NEXT ACTION
```

For substantial work, record this matrix in the task notes or handoff.

A new probe SHOULD test only the actual unresolved assumption.

Passing tests or a successful empirical probe do not erase contradictory
canonical evidence; contradictions must be recorded and resolved deliberately.

---

## 18. Supersession and correction

Never overwrite the identity of an accepted predecessor.

When a correction supersedes an earlier artifact:

- preserve predecessor identity;
- identify the successor explicitly;
- state whether the predecessor is historical, blocked, superseded, or still
  controlling in some scope;
- update the routed checkpoint/index;
- do not make a fresh chat infer supersession from timestamps alone.

---

## 19. Canonical repository evidence is the default continuity source

For project continuity, prefer this lookup order:

1. platform/system requirements;
2. current project instructions and guardrails;
3. exact active user task;
4. current canonical repository state;
5. currently routed checkpoint(s);
6. controlling task-specific artifacts;
7. accepted canonical evidence/source records;
8. task-local noncanonical inputs;
9. prior-chat recovery;
10. new external research.

This order is about continuity and evidence lookup, not authority expansion.
A lower item cannot grant a capability omitted by a higher controlling source.

---

## 20. File-sprawl control

The continuity system MUST NOT respond to every milestone by creating a new
permanent file.

Prefer:

```text
update current checkpoint
+ update artifact index
+ update existing owner artifact
```

over:

```text
create another standalone summary
create another standalone evidence recap
create another standalone context memo
```

Create a new permanent artifact only when one of these is true:

- it is itself a controlling specification/review/handoff;
- it is a required independently verifiable evidence record;
- it is a route/stage checkpoint;
- it is a lossless archive/manifest necessary for provenance;
- combining it with an existing carrier would make authority or provenance
  ambiguous.

Where many small accepted records accumulate, consolidate them in a later
bounded governance task rather than continuing indefinite file growth.

Do not delete accepted provenance merely for neatness.

---

## 21. Failure mode this workflow prevents

The following sequence is prohibited when canonical evidence already answers
the historical portion of the question:

```text
fresh chat
-> assume fact is missing
-> ask old chat
-> redo research
-> redo probe
-> discover canonical spec already contained the evidence
```

Required sequence:

```text
fresh chat
-> inspect canonical routing/evidence
-> identify historical fact already preserved
-> identify only the remaining freshness/currentness gap
-> perform the smallest permitted action needed for that gap
```

A second prohibited sequence is:

```text
hours of useful work
-> result exists only in chat/local folder
-> start new chat
-> previous theorem/evidence disappears
-> repeat work
```

Required sequence:

```text
important milestone
-> milestone canonicalization gate
-> canonical theorem/evidence identity installed or queued for install
-> handoff completeness audit
-> safe new-chat transition
```

---

## 22. Relationship to other ARB workflows

Use this workflow together with, when relevant:

- `ARB_SHARED_CONTEXT_MEMO.md`
- `REPOSITORY_ACCESS_RULES.md`
- `BROWSER_UPLOAD_TRANSFER_WORKFLOW.md`
- `LOCAL_EXECUTION_ENVIRONMENT.md`
- `MARCO_IMPLEMENTATION_REVIEW_PACKAGE_WORKFLOW.md`
- `MARCO_ARB_EXTERNAL_RESEARCH_FINDINGS_MASTER_01.md`

This workflow does not replace their capability, repository, transfer, review,
or research-authority rules.

---

## 23. Default continuity test

A milestone has adequate continuity when a competent fresh ARB chat, given:

- access to the canonical repository;
- current project instructions;
- the small current-task handoff;
- any explicitly identified noncanonical task inputs;

can determine without prior conversation history:

```text
WHAT is currently accepted?
WHY is it accepted?
WHICH exact evidence supports it?
WHAT is historical versus current?
WHAT remains unresolved?
WHAT is the next bounded task?
WHAT capabilities are and are not permitted?
```

A handoff has adequate continuity only when the sending Marco has also answered:

```text
WHAT material work from this chat is not yet in the repository?
WHICH of it must be canonicalized?
WHICH must remain local but be canonically referenced?
WHICH exact noncanonical inputs does the next chat still need?
IS anything important being left behind only in this chat?
```

If either test fails, continuity is incomplete.
