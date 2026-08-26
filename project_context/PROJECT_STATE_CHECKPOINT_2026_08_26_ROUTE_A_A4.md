# PROJECT STATE CHECKPOINT — 2026-08-26 — ROUTE A THROUGH A4

Authority level: canonical current-state overlay.

This checkpoint records accepted state facts that post-date portions of `project_context/PROJECT_STATE.md` at the time this file was installed. For the exact facts listed here, this checkpoint controls over older state text until a later consolidation folds these facts back into `PROJECT_STATE.md` and `ARTIFACT_INDEX.md`.

This file grants no capability. It is a state/provenance record only.

## 1. Repository baseline for the accepted A3/A4 work

The accepted Revision-05/A3/A4 work was reviewed against:

```text
repository = rigolugo/ARB
branch = main
base_HEAD = 8917baf5effe046ce3bf6618d21d60103c929693
base_tree = 78011f39b8faafdee31ebdecd5147d35aa0bf1fa
base_parent = 8787dd4b4ec5a8ba1fbb5b0e8c81ad2d8706cd39
```

The containing checkpoint commit is a documentation/provenance advance only. It does not alter the accepted runtime semantics established at the baseline above.

## 2. Accepted Revision-05 source/negative-theorem contract

Controlling specification:

```text
KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_05.md
raw_bytes = 591027
sha256 = 5e51550edf3a644b07a640631564be4e53d248e7fa73c86f29e8fa15316457d6
```

Subordinate handoff:

```text
HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_READ_ONLY_SPEC_05.md
raw_bytes = 12304
sha256 = 694d7a0bdb4af541b422a9ff617e7f2a2897987035a83c14b1e347a85450a497
```

Accepted current source-contract identity:

```text
schema_id = KALSHI_PRIMARY_DOMAIN_HISTORICAL_RESOLUTION_EXECUTION_MATERIAL_SOURCE_CONTRACT_REV5
normalization_revision = 4
canonical_json_bytes = 143864
canonical_json_sha256 = dc30bf877ce9ce7d8f65c97357fafe6891ce1af359bc7d2b4c9747278ad9a762
market_result = NOT_CONFIRMED__NOT_EXECUTION_MATERIAL
market_result_contract.rendered_observation = POSITIVELY_EXPOSED_AS_CHILD_IN_CURRENT_RENDERED_RESEARCH_INTERFACE
```

The accepted theorem remained conservative: zero exact order/fill matches are not authoritative proof that the historical CREATE never existed or definitely failed.

## 3. Accepted A3 one-shot execution

Accepted evidence package:

```text
KALSHI_DEMO_A3_REV05_PROVIDER_02K_PHASE_B_EXECUTION_01_RETRY_01_EVIDENCE.zip
raw_bytes = 22410
sha256 = 460276e7f5d57502c2dc0e539f9a52ac73ada8fa63e83128a72f30b4d0cd7b42
```

Contained exact execution evidence:

```text
A3_EXECUTION_EVIDENCE.json
raw_bytes = 20024
sha256 = 1d4839b5879bc6d3d1ad47aa80b67fe4765244379a495940b9c6ce2d0f9378d4
```

Accepted execution components:

```text
Provider-02K sha256 = 1cc79a588d42a34b52692c225bf3554c777c32cc875cda56adbcc3981e046368
Revision-05 runner sha256 = f155d98b5edf1d273ac1c536b814de730b7d1832a5f5375841467a601c9f6c97
Launcher-11 sha256 = 69815647d6ed423ca810202ba36115605b0a43bb9606cafedb26cdfc980168a0
```

Accepted A3 terminal facts:

```text
status = A3_ONE_SHOT_EXECUTION_COMPLETE__RETURN_TO_MARCO
A3_consumed = true
result_class = READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN
bound_order_id = null
binding_source_class = NONE
planned_branch = ZERO_MATCH
authoritative_nonexistence_proven = false
overall_evidence_complete = false
retention_lower_bound_proven = false
writer_proof_state_after = HELD
writer_proof_release_eligible_after = false
source_docs_get_count = 19
Kalshi_Demo_GET_request_count = 8
retry_count = 0
redirect_count = 0
venue_write_activity = NONE
production_activity = NONE
persistent_ARB_state_accessed = false
persistent_ARB_state_mutated = false
```

A3 did not query positions or settlements on the ZERO_MATCH branch:

```text
position_evidence.required = false
settlement_evidence.required = false
```

The A3 authorization is consumed and is not rerunnable by inference.

## 4. Accepted A4 durable-ingest decision

Accepted external controlling specification:

```text
KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_DURABLE_RECONCILIATION_INGEST_STATE_UPDATE_SPEC_01.md
raw_bytes = 35105
sha256 = cbe6313f1e2bc4ab007e3d30214aa2f95a80296eb9f352d36eb4936694d48e75
```

Accepted external subordinate handoff:

```text
HANDOFF_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_DURABLE_RECONCILIATION_INGEST_STATE_UPDATE_SPEC_01.md
raw_bytes = 11085
sha256 = 67f2ac539f4a6cc4d9b8aa3c2401499c376bf44a0bebbafdcacf51c1b52038df
```

Canonical review record installed with this checkpoint:

```text
reviews/REVIEW_KALSHI_DEMO_PRIMARY_DOMAIN_HISTORICAL_INCIDENT_RESOLUTION_DURABLE_RECONCILIATION_INGEST_STATE_UPDATE_SPEC_01.md
review_disposition = APPROVE
```

Accepted A4 result:

```text
A4_DISPOSITION =
NO_DURABLE_RECONCILIATION_INGEST__A3_EVIDENCE_NONQUALIFYING__HELD_STATE_PRESERVED

durable_reconciliation_append_specified = false
A5_IMPLEMENTATION_REQUIRED_FOR_THIS_A3_RESULT = false
```

The load-bearing reason is that the accepted A3 evidence does not satisfy the Gate-D Route-A positive closure theorem. The existence of an emergency reconciliation capability does not create an obligation to append a nonqualifying reconciliation.

## 5. Durable incident state after A4

The accepted durable state remains unchanged:

```text
incident_id = KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01
disposition = WRITE_UNRESOLVED_ZERO_MATCH
bound_order_id = null
created_order_upper_bound = 1
active_order_upper_bound = 1
unknown_result = true
writer_proof_state = HELD
writer_proof_release_eligible = false
protected_unresolved_legacy_write_count = 1
history_completeness = COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE
restart_classification = RESTART_UNRESOLVED_WRITE_HELD
normal_writer_handle = NONE
historical_incident_cancel_target = NONE
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
release_eligible = false
normal_writer_eligible = false
```

Never infer from the accepted A3/A4 result:

```text
CREATE_NEVER_EXISTED
CREATE_DEFINITELY_FAILED
SAFE_TO_RETRY_CREATE
SAFE_TO_CANCEL
ZERO_EXPOSURE
WRITER_PROOF_RELEASED
INCIDENT_CLOSED
```

## 6. Route-A state and sequencing

Current Route-A classification:

```text
ROUTE_A_NOT_CURRENTLY_EXECUTION_READY__NEW_BOUNDED_HISTORICAL_RECONCILIATION_EVIDENCE_REQUIRED
```

Stage state:

```text
A1 = COMPLETE/ACCEPTED PREDECESSOR CONTRACT
A2 = COMPLETE/ACCEPTED SUBSTRATE
A3 = CONSUMED
A4 = COMPLETE/APPROVED__NO_DURABLE_INGEST
A5 = NOT_REQUIRED_FOR_THIS_A3_RESULT
A6 = NOT_APPLICABLE_FOR_THIS_A3_RESULT
A7 / writer-proof release = NOT_REACHED
Gate_D real experiment = NOT_AUTHORIZED_BY_THIS_CHECKPOINT
```

No new venue-evidence path is defined by A4. A later attempt to obtain new historical reconciliation evidence requires a new bounded task with its own source/operation/capability contract.

## 7. External artifact retention and restart rule

Raw execution ZIPs and accepted external specification/handoff bytes are not automatically committed merely to make the repository self-contained. Their exact identities above are canonical provenance references. Credentials, private keys, account secrets, auth headers, local databases, and other sensitive operational material must never be committed.

For fresh-chat restart:

1. read root `START_HERE.md`;
2. read `project_context/START_HERE.md`;
3. read `project_context/PROJECT_STATE.md`;
4. read this checkpoint for the accepted state that post-dates older portions of `PROJECT_STATE.md`;
5. use the exact external A4 specification/handoff identities above when the full controlling text is required;
6. use external A3 evidence only by the exact byte/SHA identities recorded here when raw evidence is actually required.

This checkpoint does not grant network, credentials, venue activity, persistent-state mutation, writer release, Gate-D execution, or production capability.
