# PROJECT STATE CHECKPOINT — 2026-08-29 — ROUTE B B1 SOURCE-BINDING CORRECTION 02 INSTALLATION

Authority level: canonical current-state overlay.

This checkpoint records Marco's approval and the exact canonical installation of
`KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_02`.

It supplements the earlier Route-B B1 implementation, authenticated-execution,
and current-OpenAPI-source-resolution checkpoints. It supersedes only their
statements that the source/evidence-binding correction remained pending or was
the next B1 task.

This checkpoint grants no credential use, authenticated Kalshi request,
production access, venue write, persistent-state mutation, writer-proof release,
canary execution, or later-stage capability.

## 1. Exact canonical lineage

Pre-correction canonical base:

```text
commit = 735b9a8635131ccf7a708e708ff1dff671f32c03
tree = 24c3b1dd37544685e1927b77d5ea7794918a7c5c
parent = 6204702749b95d66714ec6045646043e04b28d4e
```

Blocked predecessor preserved in canonical history:

```text
task = KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_01
commit = d6bb5dd2871dc744709cd234d441eff7276b7fe5
tree = c627a4aeaeadec8f52284bc2367471f0b9935545
parent = 735b9a8635131ccf7a708e708ff1dff671f32c03
disposition = BLOCKED / PRESERVED
```

Approved final candidate and installed canonical object:

```text
task = KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_02
commit = 8fe1d3cd1f9e05d5c32c58d896b6aef818a3e22a
tree = 4eb953f399bb9a7f46c4f848f8c592de7f0434d4
parent = d6bb5dd2871dc744709cd234d441eff7276b7fe5
commit_count_above_735b9a8 = 2
```

Canonical lineage is therefore exactly:

```text
735b9a8635131ccf7a708e708ff1dff671f32c03
    ->
d6bb5dd2871dc744709cd234d441eff7276b7fe5
    ->
8fe1d3cd1f9e05d5c32c58d896b6aef818a3e22a
```

The blocked predecessor was not amended, squashed, dropped, or rewritten.

## 2. Exact approved installed paths

Only these two paths differ from the pre-correction canonical base:

```text
src/arb/venues/kalshi/account_subaccount_probe.py
raw_bytes = 140801
sha256 = 0f4cf19c7033e40bd6044f62616ead35060d852812ef428f7dd1716afb76e7de
git_blob = 1dc0e82c61b7dbd6b5a5e2ca2e9ed37ed3f75fe0

tests/test_kalshi_account_subaccount_probe.py
raw_bytes = 147073
sha256 = 24b9afcd79a5b6518736d85f6c0378a4010ac711df7093ee985d91f0e3a62f8e
git_blob = f1928b524863472d3b07d68b2662dd02f263cd81
```

Independent post-install GitHub verification established that current `main`
resolves to the exact candidate commit/tree above and that the installed remote
blob identities are exactly the two reviewed blob IDs.

## 3. Marco review evidence

Exact reviewed package:

```text
KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_02_MARCO_REVIEW.zip
raw_bytes = 85340
sha256 = feca1a24a2a7163e4417c425ae19bfc97ee3085a72b884c0bd2cd4aa12fff254
CRC = PASS
```

Detached sidecar:

```text
raw_bytes = 166
sha256 = 55bdb1f1f328db4a518fd3d806e2991c32a408833dd4d2debcb99a930253c269
```

`candidate.patch` inside that package:

```text
raw_bytes = 69392
sha256 = 056fbdfca1fce698dad0c8ebf596e071d98ea227d4ae779c572a4b75526e3ccb
range = 735b9a8635131ccf7a708e708ff1dff671f32c03..8fe1d3cd1f9e05d5c32c58d896b6aef818a3e22a
```

Marco disposition:

```text
APPROVE
```

Static conformance result:

```text
BIND-01 PASS
BIND-02 PASS
BIND-03 PASS
BIND-04 PASS
BIND-05 PASS
BIND-06 PASS
BIND-07 PASS
BIND-08 PASS
```

Validation evidence retained from the exact candidate review:

```text
focused = 210 passed
full repository = 2936 passed, 555 subtests passed
```

Passing tests remain supporting evidence, not independent proof of conformance.

## 4. Accepted source/evidence-binding theorem

For a valid non-authoring task-current B1 source record, active execution
evidence identity is no longer an opaque caller-supplied digest.

Accepted theorem:

```text
material TaskCurrentSourceRecord semantics
+
non-secret task-current source provenance
    ->
deterministic canonical binding record
    ->
canonical UTF-8 JSON bytes
    ->
SHA-256
    ->
active source_binding_record_sha256 emitted by B1 manifest/summary
```

Changing a material source semantic or provenance field changes the deterministic
binding-record bytes/hash or makes the source record fail closed before request
1.

The prior blocked divergence is therefore closed:

```text
same active binding identity
+
UNRESTRICTED vs NOT_EXPOSED ApiKey.subaccount absence semantic
=
PROHIBITED
```

The accepted authoring legacy source binding remains separately preserved and
may emit its historical fixed identity only for an authoring-congruent record.

Evidence schema revision/key sets remain unchanged.

## 5. Current official-source context

The canonical source-resolution checkpoint remains controlling for the exact
public-source observation it records.

Exact externally retained raw OpenAPI identity:

```text
filename = KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml
storage = LOCAL_ONLY_EXTERNAL_SOURCE_EVIDENCE
raw_bytes = 325930
sha256 = 99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed
OpenAPI = 3.0.0
info.version = 3.29.0
source_url = https://docs.kalshi.com/openapi.yaml
```

Canonical sanitized source-resolution report:

```text
project_archive/kalshi_sources/KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01_REPORT.json
raw_bytes = 1151
sha256 = 85a6f371dbbe026198cff39366978b133a67c41b15f4abfd180b2077a268577a
git_blob = 3d1d45b0a53dedba1e054456fb498040d8c7deac
```

Accepted source theorem for that observation:

```text
ApiKey.subaccount absent/null = UNRESTRICTED
```

The exact empirical observation timestamp for the 325930-byte raw source was
not established by that evidence. The fabricated value
`2026-08-28T00:00:00Z` is not accepted empirical provenance and is not present as
a runtime default in the installed Correction 02 implementation.

A future task-current source binding must carry an explicitly observed
`observed_at_utc`; no hard-coded empirical default is permitted.

## 6. Historical B1 execution remains unchanged

Local Operator 02 remains a historical accepted result under its exact older
source binding:

```text
current_key_match_state = UNIQUE
current_key_restriction_state = NOT_EXPOSED
terminal_outcome = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
request_count = 2
```

Correction 02 and the later public source theorem do not rewrite that historical
execution.

Numbered-subaccount existence remains unknown because the historical execution
stopped before balances/netting enumeration.

## 7. Exact canonical installation result

Installation task:

```text
KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_02_CANONICAL_INSTALLATION_01
```

Accepted installation facts:

```text
pre_install_main = 735b9a8635131ccf7a708e708ff1dff671f32c03
post_install_main = 8fe1d3cd1f9e05d5c32c58d896b6aef818a3e22a
main_update_mode = NON_FORCE_FAST_FORWARD
candidate_identity_preserved = true
force_push = false
merge_commit = false
temporary_transfer_branch_deleted = true
remote_changed_path_count = 2
```

Activity boundary:

```text
network_activity = GITHUB_REPOSITORY_ONLY
credential_activity = NONE_EXCEPT_EXISTING_GIT_REMOTE_AUTH_MECHANISM
kalshi_activity = NONE
venue_activity = NONE
persistent_state_activity = NONE
package_installation = NONE
```

Marco independently reverified after installation that GitHub `main` equals the
exact approved candidate commit/tree/parent, that base-to-main is two commits
with merge base `735b9a8...`, and that the two remote installed blob identities
match the approved review package.

## 8. Current B1 state

```text
B1_CURRENT_SOURCE_GAP = RESOLVED
B1_CURRENT_APIKEY_ABSENT_NULL_SEMANTIC = UNRESTRICTED
B1_SOURCE_EVIDENCE_BINDING_CORRECTION_02 = APPROVED_AND_CANONICALLY_INSTALLED
B1_CANONICAL_IMPLEMENTATION_COMMIT = 8fe1d3cd1f9e05d5c32c58d896b6aef818a3e22a
B1_CANONICAL_IMPLEMENTATION_TREE = 4eb953f399bb9a7f46c4f848f8c592de7f0434d4
B1_OPERATOR_02_HISTORICAL_TERMINAL = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
B1_ACCOUNT_WIDE_ENUMERATION_PROVEN = false
B1_NUMBERED_SUBACCOUNT_EXISTENCE = UNKNOWN
B1_AUTHENTICATED_EXECUTION_AUTHORIZED = false
```

Historical primary remains unchanged:

```text
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

## 9. Next bounded action

The evidence-binding implementation gap is closed.

No fresh authenticated B1 execution is authorized by this checkpoint.

Before any future separately authorized B1 authenticated read-only execution,
the task must establish a valid task-current official-source binding for that
execution, including a truthful explicit `observed_at_utc`, and then pass that
exact source record to the installed deterministic evidence-binding path.

Current next-action class:

```text
PREPARE_SEPARATELY_AUTHORIZED_FRESH_B1_READ_ONLY_EXECUTION_WITH_TASK_CURRENT_SOURCE_BINDING
```

A future execution is a new bounded execution, not an automatic retry of Local
Operator 02.
