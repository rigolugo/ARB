# Marco Implementation Handoff — Kalshi Demo Environment Separation Specification Candidate 02 Canonical Installation

**Artifact:** `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation_CANDIDATE_02.md`  
**Candidate:** `CANDIDATE_02`  
**Author:** Marco  
**Date:** 2026-08-06  
**Classification:** `DOCUMENTATION_ONLY_CANONICAL_INSTALLATION_PACKAGE`  
**Implementation agent:** Neo  
**Canonical installation target:** `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation.md`  
**Authorization source:** the bounded Gustavo-posted Neo dispatch carrying authorization ID `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`  
**Repository-transfer mode:** `MANUAL_BROWSER_TEMPORARY_BRANCH`  
**Marco fast-forward after approval:** `PERMITTED`

## 1. Purpose

Prepare and verify one bounded documentation-only canonical installation package for the exact accepted Kalshi Demo Environment Separation and Capability Envelope Specification Candidate 02.

This handoff is a controlling implementation record and exact-copy source. It does not independently authorize execution. The exact Gustavo-posted Neo dispatch supplies operative task authorization.

The task installs governance and specification records only. It does not implement the validator, configuration parser, transport, authentication, connectivity, venue adapter, market data, orders, fills, ledger, strategy, or trading.

## 2. Canonical repository and immutable base

- repository: `rigolugo/ARB`
- visibility: `public`
- default branch: `main`
- exact required base: `e35d56dda77819f0066447e18a0a2dc5bac2bb88`
- accepted bootstrap implementation commit: `e136be0b80f0370572e889d1075a11fc1b445348`
- current canonical phase at dispatch: `DOCUMENTATION_BOOTSTRAP_COMPLETE`

Stop before editing on any unexplained repository, visibility, default-branch, HEAD, ancestry, tree, or controlling-record mismatch.

Do not silently rebase this task onto a later commit.

## 3. Controlling exact identities

### Accepted Candidate 02 specification

- filename: `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`
- raw bytes: `78876`
- SHA-256: `4a676c4698411db6743d591595918e4ba7af221b7a7b67d86e807925d8b47bf2`

### Accepted Bruno handoff

- filename: `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`
- raw bytes: `14114`
- SHA-256: `a47d623c4a80048909e4e9df8e4c11904ff0e763ab4e242028bd0c81dcedee6d`

### Marco approval review

- filename: `REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`
- final raw bytes and SHA-256 are supplied externally in Gustavo's Neo dispatch after this file is frozen.

### This implementation handoff

- filename: `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation_CANDIDATE_02.md`
- final raw bytes and SHA-256 are supplied externally in Gustavo's Neo dispatch after this file is frozen.

Any filename, byte-length, or SHA-256 mismatch is a halt condition.

## 4. Accepted user decision

Gustavo accepted the exact Candidate 02 specification and Bruno handoff identities listed in Section 3.

That acceptance:

- accepts those exact external candidate artifacts;
- does not accept Candidate 01;
- does not itself modify the repository;
- does not authorize implementation source or tests;
- does not authorize venue access or credentials;
- does not authorize a later technical phase.

The canonical installation task records the accepted Candidate 02 artifacts and their review without expanding their scope.

## 5. Repository-transfer workflow

```text
repository_transfer_mode: MANUAL_BROWSER_TEMPORARY_BRANCH
marco_fast_forward_main_after_approval: PERMITTED
```

Neo must:

1. work locally from the exact required base;
2. create one clean local implementation commit only if every requirement passes;
3. not push;
4. not request GitHub credentials;
5. produce one browser-upload ZIP containing exactly one top-level `repository_payload/` directory;
6. produce one detached ZIP SHA-256 file;
7. produce one external manifest with per-file raw byte lengths and SHA-256 values;
8. verify the package before delivery.

Gustavo will later create the exact temporary browser branch from the authorized base, upload only the authorized payload, commit through GitHub's browser, leave `main` unchanged, and return the branch and browser-created commit SHA to Marco.

Neo's local commit SHA is evidence only and is not required to equal the browser-created commit SHA.

## 6. Exact branch and package names

Neo local branch:

`neo-c02-kalshi-demo-spec-installation`

Authorized browser temporary branch:

`candidate-02-kalshi-demo-spec-installation`

Required package:

`KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_PACKAGE_01.zip`

Detached checksum:

`KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_PACKAGE_01.zip.sha256`

Manifest:

`KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_PACKAGE_01_MANIFEST.md`

Recommended local commit message:

`Install accepted Kalshi Demo environment-separation specification Candidate 02`

## 7. Writable-path matrix

Neo may create or modify only:

```text
START_HERE.md
project_context/START_HERE.md
project_context/PROJECT_STATE.md
project_context/AUTHORIZATION_LOG.md
project_context/DECISION_LOG.md
project_context/ARTIFACT_INDEX.md
specifications/SPEC_kalshi_demo_environment_separation_and_capability_envelope.md
handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec.md
reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md
handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation.md
```

Every unlisted path is protected and prohibited.

Explicitly protected paths include:

```text
README.md
.gitignore
project_context/GUARDRAILS.md
project_context/AGENT_ROLES.md
specifications/SPEC_repository_bootstrap.md
reviews/REVIEW_repository_bootstrap_spec.md
handoffs/HANDOFF_repository_bootstrap_spec.md
handoffs/HANDOFF_repository_bootstrap_implementation.md
src/.gitkeep
tests/.gitkeep
artifacts/.gitkeep
```

No source, test, credential, environment, artifact-data, cache, log, database, or package file may be added.

## 8. Exact-copy mappings

Neo must copy these external sources byte-for-byte:

| External source | Canonical target |
|---|---|
| `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md` | `specifications/SPEC_kalshi_demo_environment_separation_and_capability_envelope.md` |
| `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` | `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec.md` |
| `REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md` | `reviews/REVIEW_kalshi_demo_environment_separation_and_capability_envelope_spec.md` |
| `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation_CANDIDATE_02.md` | `handoffs/HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_implementation.md` |

For every mapping:

1. verify the external filename, raw byte length, and SHA-256;
2. copy without normalization, reformatting, or substitution;
3. verify the target raw byte length and SHA-256;
4. halt on any mismatch.

Do not alter line endings, Unicode normalization, BOM state, whitespace, headings, URLs, tables, or formatting.

## 9. Required governance updates

Neo must update only the six listed governance files. Historical entries must remain append-only where the existing document requires append-only treatment.

### 9.1 Root `START_HERE.md`

Update the current-phase statement and canonical read order so that they record:

- Candidate 02 specification and Bruno handoff are accepted by Gustavo;
- this task canonically installs their exact identities and Marco's review;
- no validator implementation or technical phase is authorized;
- all venue access, credential use, funding, orders, cancellations, and trading remain prohibited;
- the canonical read order includes the four newly installed task records after the repository-bootstrap records.

Do not weaken any safety statement.

### 9.2 `project_context/START_HERE.md`

Update:

- current phase;
- canonical read order;
- record locations.

The resulting current phase must distinguish:

1. accepted and canonically installed specification/governance records; from
2. unstarted and unauthorized technical implementation.

Add exact pointers to the new canonical specification, Bruno handoff, Marco review, and implementation handoff.

### 9.3 `project_context/PROJECT_STATE.md`

Record:

- current phase:
  `KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ACCEPTED_AND_INSTALLED`;
- Candidate 02 exact accepted identities;
- Candidate 01 remains blocked and noncanonical;
- the documentation-only canonical installation consumes no venue or credential capability;
- active technical implementation authorization: none;
- no source code or tests exist for this specification;
- no Kalshi Demo or production request occurred;
- no Polymarket request occurred;
- no credentials were used;
- no orders, cancellations, funding, paper trading, or live trading occurred;
- unresolved implementation decisions remain those listed in accepted Candidate 02 Section 29;
- next user decision is whether to authorize a separately bounded technical implementation dispatch after Marco resolves the required implementation-handoff details;
- no next phase begins automatically.

The state record must not predeclare the SHA of its own installation commit. It must require direct verification of current `main`.

### 9.4 `project_context/AUTHORIZATION_LOG.md`

Preserve existing entries exactly and append distinct entries recording:

1. Candidate 01 specification-drafting authorization:
   `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_01`;
2. Candidate 01 blocked disposition, with no repository effect;
3. Candidate 02 bounded-correction authorization:
   `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01`;
4. Gustavo's exact Candidate 02 acceptance, bound to both exact identities;
5. this canonical-installation authorization:
   `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_CANDIDATE_02_CANONICAL_INSTALLATION_01`;
6. canonical-installation completion semantics: the authorization is consumed by the exact reviewed installation commit and grants no technical implementation, tests, venue, credential, funding, order, cancellation, or trading capability.

Every capability field must be explicit. No field may be inherited or implied.

### 9.5 `project_context/DECISION_LOG.md`

Preserve existing entries exactly and append distinct decisions recording:

1. Marco's Candidate 01 decision `BLOCK`;
2. Marco's Candidate 02 decision `APPROVE`;
3. Gustavo's acceptance of the exact Candidate 02 specification and Bruno handoff;
4. Gustavo's separate authorization of this bounded documentation-only canonical installation package;
5. the fact that the installation does not authorize technical implementation or any venue activity.

Use the next sequential decision identifiers. Do not rewrite prior decisions.

### 9.6 `project_context/ARTIFACT_INDEX.md`

Preserve existing entries and append new canonical public documentation entries for:

- the installed Candidate 02 specification;
- the installed Bruno specification handoff;
- the installed Marco review;
- the installed Marco implementation handoff.

Each entry must include:

- canonical path;
- producing task and agent;
- creation or installation date;
- source identity;
- environment classification `n/a (documentation)`;
- status `Canonical`;
- sensitivity `Public`;
- review/acceptance state;
- retention `retained`;
- related specification and evidence links.

Do not index package ZIPs, detached checksums, manifests, local commits, or temporary branches as canonical repository artifacts.

## 10. Required capability matrix

| Capability | Status |
|---|---|
| Read canonical repository and Git history needed to verify the exact base | `PERMITTED` |
| Read the four exact external source artifacts | `PERMITTED` |
| Local documentation-only implementation on the exact local branch | `PERMITTED` |
| Create or modify the ten listed repository paths | `PERMITTED` |
| Raw-byte, SHA-256, path-set, content, and secret-pattern verification | `PERMITTED` |
| Local shell/subprocess use limited to Git, file, hashing, archive, and deterministic text-verification operations | `PERMITTED` |
| Create one local implementation commit | `PERMITTED` |
| Generate the required browser-upload ZIP, detached SHA-256, and manifest | `PERMITTED` |
| Neo push | `PROHIBITED` |
| Neo request or use GitHub credentials | `PROHIBITED` |
| Modify `main` | `PROHIBITED` |
| Create the browser temporary branch | `PROHIBITED` for Neo; performed manually by Gustavo |
| Pull request, merge commit, issue, release, or tag | `PROHIBITED` |
| Force update | `PROHIBITED` |
| Source-code creation or modification | `PROHIBITED` |
| Test-source creation or modification | `PROHIBITED` |
| Application or project test execution | `PROHIBITED` |
| Project imports | `PROHIBITED` |
| Package installation | `PROHIBITED` |
| Network access other than read-only GitHub clone/fetch needed for the exact repository | `PROHIBITED` |
| Credential creation, loading, parsing, or use | `PROHIBITED` |
| Kalshi Demo reads or writes | `PROHIBITED` |
| Kalshi production reads or writes | `PROHIBITED` |
| Polymarket reads or writes | `PROHIBITED` |
| Account creation or funding | `PROHIBITED` |
| Balance, portfolio, order, fill, position, or settlement access | `PROHIBITED` |
| Orders, amendments, cancellations, paper trading, or live trading | `PROHIBITED` |
| Artifact generation outside the required installation package and evidence | `PROHIBITED` |
| Later-phase work | `PROHIBITED` |
| Marco remote branch review | `PERMITTED` |
| Marco non-force fast-forward of `main` after `APPROVE` and all workflow conditions pass | `PERMITTED` |

Anything not explicitly `PERMITTED` is prohibited.

## 11. Required deterministic verification

Neo must verify:

1. exact repository, visibility, default branch, and required base;
2. the base is the checked-out commit and the starting worktree is clean;
3. exact four external artifact identities;
4. exact four source-to-target byte copies;
5. exact ten-path changed set;
6. no unlisted files or modifications;
7. every protected path is byte-identical to the base;
8. canonical read-order consistency;
9. Candidate 01 remains blocked and noncanonical;
10. Candidate 02 exact acceptance identities;
11. accepted-specification scope remains documentation-only;
12. no technical implementation authorization is introduced;
13. Demo/production and venue separation remain explicit;
14. no secret-like or credential-like content exists;
15. no source code or test source is added;
16. no application tests or project imports occur;
17. package contains exactly one `repository_payload/` top-level directory;
18. package payload contains exactly the ten authorized repository paths;
19. manifest matches every packaged file's raw bytes and SHA-256;
20. extracted package reproduces the local committed tree for the ten authorized paths;
21. final local branch has exactly one authorized implementation commit above the base;
22. final worktree is clean;
23. no push occurred.

## 12. Package format

The ZIP must contain exactly:

```text
repository_payload/
```

Under `repository_payload/`, preserve the ten authorized repository-relative paths exactly.

The ZIP must not contain:

- `.git/`;
- the manifest;
- the detached checksum;
- caches;
- logs;
- temporary files;
- credentials;
- absolute paths;
- drive letters;
- duplicate members;
- unlisted paths.

The detached checksum file must contain the ZIP SHA-256 and exact ZIP filename.

The external manifest must include:

- task and authorization IDs;
- required base;
- local branch and local commit;
- package filename, raw byte length, and SHA-256;
- exact payload member count;
- each repository-relative path;
- each file's raw byte length and SHA-256;
- exact-copy versus authored-update classification;
- protected-path verification result;
- no-secret result;
- no-network-beyond-GitHub result;
- no-push result;
- clean-worktree result.

## 13. Halt conditions

Stop without further work on:

- baseline or ancestry mismatch;
- unavailable or mismatched source artifact;
- required path outside the exact writable matrix;
- protected-path modification;
- exact-copy mismatch;
- need to change a guardrail;
- need to redesign the accepted specification;
- contradictory accepted requirement;
- secret or credential-like content;
- need for source code, tests, packages, project imports, venue access, credentials, data access, or unauthorized network activity;
- need to push;
- inability to produce the exact package structure;
- package or manifest mismatch;
- inability to create one clean local commit;
- any condition requiring force.

Report exact expected and observed facts.

## 14. Required Neo return

Return:

- status: `READY_FOR_MARCO_REVIEW` or `BLOCKED`;
- task ID and authorization ID;
- repository, required base, and observed base;
- accepted Candidate 02 identities;
- Marco review and implementation-handoff identities;
- local branch and local commit;
- exact changed-path set;
- exact-copy verification results;
- authored governance-update summary;
- protected-path result;
- commands used;
- verification performed;
- package filename, bytes, and SHA-256;
- detached-checksum filename and content;
- manifest filename;
- payload member count and per-file identities;
- secret-pattern result;
- project-import and application-test result;
- network-use result;
- push result;
- final clean-worktree result;
- blockers, if any.

Use `READY_FOR_MARCO_REVIEW` only when the complete local implementation, commit, package, detached checksum, manifest, and all deterministic verification pass.

## 15. Completion condition

Stop after returning the verified browser-upload package and evidence.

Do not:

- push;
- create the remote temporary branch;
- modify `main`;
- merge;
- request acceptance;
- begin technical implementation;
- access a venue;
- use credentials;
- fund an account;
- submit, amend, or cancel an order;
- paper trade or live trade.

No later phase begins automatically.
