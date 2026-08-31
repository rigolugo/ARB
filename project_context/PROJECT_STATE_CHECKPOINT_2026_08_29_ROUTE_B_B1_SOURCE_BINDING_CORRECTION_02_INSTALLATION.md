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

## 10. Execution 02 accepted empirical result — current-state override

This section records the later accepted direct empirical result from the
separately authorized fresh B1 read-only execution and supersedes Sections 8 and
9 only where those sections describe the then-current pre-Execution-02 state or
next action. Historical Local Operator 02 facts remain unchanged.

Marco accepted the Execution-02 finding after exact sanitized-evidence review:

```text
execution_id =
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_EXECUTION_02

evidence_class = DIRECT_EMPIRICAL_OBSERVATION
storage = LOCAL_ONLY_EXTERNAL_ACCEPTED_EVIDENCE

sanitized_evidence =
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_EXECUTION_02_SANITIZED_MARCO_REVIEW.zip

raw_bytes = 50249
sha256 = e8ae4ddf30bb91c19a2167d31be284474440e75919a724262f67a64d47a3889c
zip_crc = PASS

sidecar_raw_bytes = 170
sidecar_sha256 = c8b56882152411680b4fca1bf0d9557c28c33cc2eee9209c9b00bbfa71299112
```

Exact execution substrate:

```text
canonical_commit = 2fed77a33e3a4be7cbded90a1f8f0d015fcc8a16
canonical_tree = 81b91ca4c45b7f68a41850a1b492468049a35475
canonical_parent = 8fe1d3cd1f9e05d5c32c58d896b6aef818a3e22a

execution_package =
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_EXECUTION_02_LOCAL_OPERATOR_06

execution_package_sha256 =
cc1844835af536e923674858a202d3a829b45df63a4753ed40b3db495f50d84f

execution_package_review_sha256 =
6d9d6c6a6b2aa181bb09a088574d24a3e5704d005d3e7029d2f17561f80a16c7

execution_02_live_invocation = CONSUMED
automatic_rerun = PROHIBITED
```

Task-current official source observed by that execution:

```text
source_url = https://docs.kalshi.com/openapi.yaml
retrieval_started_at_utc = 2026-08-31T03:05:56.784037Z
observed_at_utc = 2026-08-31T03:05:58.839441Z
body_complete_proof = CHUNKED_FRAMING_COMPLETE

raw_bytes = 325930
raw_sha256 = 99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed
OpenAPI = 3.0.0
info.version = 3.29.0

ApiKey.subaccount_structure = integer / min 0 / max 63 / nullable true / not required
ApiKey.subaccount_absent_null_semantic = UNRESTRICTED

binding_name =
KALSHI_DEMO_ROUTE_B_B1_EXECUTION_02_TASK_CURRENT_OPENAPI_BINDING

binding_record_sha256 =
7782f8ded7c09f115c2380a83928572841882185db990496a417f1a670119bfa

source_record_evaluation_status = OK
```

The exact authenticated Demo read-only execution performed four requests:

```text
request_count = 4
retry_count = 0
redirect_count = 0
production_activity = NONE
venue_write_activity = NONE

1. GET /trade-api/v2/account/limits
   HTTP 200
   raw_response_bytes = 133
   raw_response_sha256 = da2c1adab14b7b7253e6c1925c118553b28a1f6829ded584523199cd8abee05d

2. GET /trade-api/v2/api_keys
   HTTP 200
   raw_response_bytes = 110
   raw_response_sha256 = 13a68703876355181e59e2d162e5a34118dab999d8d9b86ed364036ddd5abb07

3. GET /trade-api/v2/portfolio/subaccounts/balances
   HTTP 200
   raw_response_bytes = 199
   raw_response_sha256 = 37c6195ccd8ee6f5861d5c718e62c138ab467608c0797879dd4907c99c6a668a

4. GET /trade-api/v2/portfolio/subaccounts/netting
   HTTP 200
   raw_response_bytes = 139
   raw_response_sha256 = 3880855785bcf407eb26c0c8c72e9ac454bad1320a21d8f0b7db2ae62cb36394
```

Raw authenticated response bodies remain local-only and are not repository
artifacts.

Accepted B1 account/key theorem:

```text
usage_tier = basic
relevant_grants = []

current_key_match_state = UNIQUE
current_key_restriction_state = UNRESTRICTED
current_key_restricted_subaccount_number = null
current_key_scopes = ["read", "write"]

balance_subaccount_numbers = [0]
netting_subaccount_numbers = [0]
surfaces_agree = true
account_wide_enumeration_proven = true
numbered_subaccounts = []

create_subaccount_capability = NOT_PROVEN_BY_B1_READ_ONLY_FACTS
documented_create_subaccount_tier_rule = ADVANCED_OR_ABOVE
documented_tier_rule_match = NO
```

The observed `write` key scope is account metadata only. It is not ARB venue-write
authorization.

Accepted terminal theorem:

```text
B1_EXECUTION_02 = ACCEPTED_DIRECT_EMPIRICAL_OBSERVATION
B1_EXECUTION_02_TERMINAL = B1_PRIMARY_ONLY_OBSERVED
B1_NEXT_ROUTE_CLASS = NO_NUMBERED_DOMAIN_CURRENTLY_OBSERVED
B1_ACCOUNT_WIDE_ENUMERATION_PROVEN = true
B1_NUMBERED_SUBACCOUNT_EXISTENCE = NONE_CURRENTLY_OBSERVED
B1_PRIMARY_ONLY_OBSERVED = true
B1_EXECUTION_02_LIVE_INVOCATION = CONSUMED
```

The existing-numbered-subaccount Route-B branch is therefore closed for the
Execution-02 observation. No existing numbered subaccount `N > 0` is currently
observed by the two agreeing account-wide enumeration surfaces.

Historical primary remains unchanged and unusable for the clean Route-B path:

```text
historical primary domain =
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0

writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
historical_primary_safe_to_reuse_proven = false
historical_primary_incident_resolved = false
historical_primary_writer_proof_released = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

No B1 fact reconciles the historical unresolved primary-domain write or releases
writer proof.

## 11. Canonical routing recommendation after Execution 02

The current project bottleneck is now the lack of a proven clean Kalshi Demo
economic execution domain, not the absence of the basic execution spine.

Canonical routing decision:

```text
FIRST:
  preserve/canonicalize B1 Execution 02 and its accepted route theorem

THEN:
  evaluate Route 1 versus Route 2 at the specification level

BEFORE:
  any further Kalshi venue activity
```

No further Kalshi request is authorized by this checkpoint.

### Route 1 — clean numbered-subaccount path

At specification level, evaluate a bounded account-tier / clean-numbered-domain
route whose eventual objective would be a genuine venue-side subaccount
`N > 0`, followed by exact clean-domain proof.

Current controlling facts before that evaluation are:

```text
existing numbered subaccount = NONE_CURRENTLY_OBSERVED
current account usage tier = basic
documented CreateSubaccount tier rule = ADVANCED_OR_ABOVE
documented tier match = NO
CreateSubaccount capability = NOT_PROVEN_BY_B1_READ_ONLY_FACTS
```

A future Route-1 specification MUST NOT infer write capability from the observed
key metadata or documentation. Any later account-tier change, subaccount create,
or other venue write requires its own controlling specification and separately
explicit execution capability.

Before a future CreateSubaccount request could be authorized, the controlling
design must include durable creation-result reconciliation. An ambiguous create
result MUST NOT be interpreted as a failed create or as permission to resend
automatically.

A newly created numbered subaccount, if ever separately authorized and proven,
would still be only a candidate clean domain until identity, inception/history,
access, inventory/exposure, ledger/risk binding, and absence of unresolved writes
are established.

Funding/transfer is not part of this route decision and remains a separate later
write problem.

### Route 2 — historical primary-domain resolution/reclamation path

At specification level, separately evaluate whether the existing durable
reconciliation, persistent-ledger, restart-recovery, and risk-control
architecture can support a bounded path to resolve the historical primary-domain
incident strongly enough to change the current hold theorem.

Route 2 MUST begin from the current state:

```text
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
historical_primary_safe_to_reuse_proven = false
```

The purpose of Route-2 evaluation is to determine whether a controlling proof
path exists. The existence of reconciliation machinery does not itself release
the hold, prove zero exposure, or authorize venue activity.

### Decision boundary

Current next-action class:

```text
ROUTE_B_SPEC_LEVEL_ALTERNATIVE_EVALUATION_REQUIRED
```

The next project action is therefore to compare Route 1 and Route 2 using
canonical evidence and non-controlling research, then choose the narrower
controlling specification path.

Until that comparison is completed and the user separately selects/authorizes a
next task:

```text
FURTHER_KALSHI_VENUE_ACTIVITY = NOT_AUTHORIZED
SUBACCOUNT_CREATE = NOT_AUTHORIZED
ACCOUNT_TIER_WRITE = NOT_AUTHORIZED
PRIMARY_DOMAIN_REUSE = NOT_AUTHORIZED
REAL_DEMO_MARKET_MAKING_EXPERIMENT = NOT_READY
```
