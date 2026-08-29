# PROJECT STATE CHECKPOINT — 2026-08-28 — ROUTE B B1 CURRENT OPENAPI SOURCE RESOLUTION

Authority level: canonical current-state overlay.

This checkpoint records the accepted credential-free task-current official-source resolution performed after the Route-B B1 Local Operator 02 execution. It supplements, and does not rewrite, `PROJECT_STATE_CHECKPOINT_2026_08_28_ROUTE_B_B1_AUTHENTICATED_EXECUTION.md`.

This checkpoint grants no credential use, authenticated Kalshi request, venue write, production access, persistent-state mutation, writer-proof release, or later-stage capability.

## 1. Canonical base before this source milestone

```text
repository = rigolugo/ARB
canonical_main_before_source_install = 311899ec0769b2b30e0ac53598092ed0c260f62c
canonical_tree_before_source_install = e485663e4aac862e949c9fa0c4badb0b00f3d729
canonical_parent_before_source_install = 60e4af9123f0e3d791ec8095911ed00760960d61
```

## 2. Public official-source probe

Task:

```text
KALSHI_DEMO_ROUTE_B_B1_CURRENT_OPENAPI_SOURCE_RESOLUTION_01
```

Only this public official source was retrieved:

```text
https://docs.kalshi.com/openapi.yaml
```

Observed activity classification:

```text
network_activity = PUBLIC_OFFICIAL_DOCUMENTATION_ONLY
credential_activity = NONE
kalshi_demo_api_activity = NONE
production_api_activity = NONE
venue_write_activity = NONE
http_status = 200
content_type = text/yaml
```

The exact lossless source snapshot is installed at:

```text
project_archive/kalshi_sources/KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml
raw_bytes = 325930
sha256 = 99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed
OpenAPI = 3.0.0
info.version = 3.29.0
```

Authority of the external source itself:

```text
OFFICIAL_KALSHI_SOURCE_NONCONTROLLING
```

Its conclusions become current ARB state here only to the extent explicitly accepted by this canonical checkpoint or a later controlling artifact.

## 3. Exact ApiKey.subaccount semantic resolved

The task-current official `ApiKey` schema establishes:

```text
ApiKey.required = [api_key_id, name, scopes]
subaccount_property_found = true
subaccount_required = false
subaccount_nullable = true
subaccount_minimum = 0
subaccount_maximum = 63
```

The exact material schema description is:

```text
If set, the API key is restricted to this single sub-account and may only read
and trade on it. Absent/null means the key is unrestricted.
```

Therefore the previously unresolved B1 source question is now resolved as:

```text
GET_API_KEYS_RESPONSE_SUBACCOUNT_ABSENCE_SEMANTICS = UNRESTRICTED
CURRENT_OFFICIAL_SOURCE_EXPLICITLY_PROVES_ABSENT_NULL_UNRESTRICTED = true
```

This satisfies the source-semantic condition anticipated by B1-SRC-004 for a future task-current source binding. It does not retroactively alter the exact source binding used by Local Operator 02.

## 4. B1-relevant source drift check

Marco compared the exact current OpenAPI 3.29.0 snapshot above against the exact supplied historical OpenAPI 3.28.0 snapshot:

```text
historical_raw_bytes = 333315
historical_sha256 = cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b
```

For these exact B1 GET operation objects:

```text
GET /account/limits
GET /api_keys
GET /portfolio/subaccounts/balances
GET /portfolio/subaccounts/netting
```

and these exact schemas:

```text
ApiKey
GetApiKeysResponse
GetAccountApiLimitsResponse
GetSubaccountBalancesResponse
SubaccountBalance
GetSubaccountNettingResponse
SubaccountNettingConfig
FixedPointDollars
```

the parsed OpenAPI objects were byte-independent structurally equal after YAML parsing.

A deterministic canonical JSON projection of exactly those selected current objects had:

```text
projection_raw_bytes = 6020
projection_sha256 = d1f5a2a42e8073424923f70a6306038724e838d3b69f5772202ad5e2c3e2725b
```

Disposition:

```text
MATERIAL_B1_OPENAPI_DRIFT_ON_SELECTED_SURFACE = NONE_OBSERVED
```

This comparison is a `DIRECT_EMPIRICAL_OBSERVATION` over the two exact source snapshots. It does not claim that the entire OpenAPI 3.28.0 and 3.29.0 documents are identical.

## 5. Supplied derived artifacts

The local probe also produced:

```text
KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml.sha256
raw_bytes = 115
sha256 = 75ba80de1a512b685d9396eebf6af7b6d76bcf2081740eda2e29dbeff70abb5b

KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01_REPORT.json
raw_bytes = 1151
sha256 = 85a6f371dbbe026198cff39366978b133a67c41b15f4abfd180b2077a268577a
```

The detached sidecar correctly names the YAML SHA-256 above. The report is a derived projection of the canonical raw YAML and does not add independent source authority.

To minimize file proliferation, these two derived artifacts are not separately installed in the repository; their exact identities and material facts are preserved by this checkpoint.

## 6. Relationship to Local Operator 02

Local Operator 02 remains historically correct under its exact execution-time source binding:

```text
current_key_match_state = UNIQUE
current_key_restriction_state = NOT_EXPOSED
terminal_outcome = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
request_count = 2
```

This checkpoint MUST NOT rewrite that historical execution result to `UNRESTRICTED`.

Instead, the new theorem is:

```text
Local Operator 02 observed the uniquely matched current key with no bound
subaccount value in its sanitized projection.

A later task-current official source now explicitly establishes that an
ApiKey.subaccount value that is absent/null means that key is unrestricted.
```

Any future execution that relies on this semantic must bind its evidence to the exact current source used for that execution.

## 7. Evidence-binding implementation gap

The accepted B1 core implementation can evaluate a task-current source record whose:

```text
api_keys_absent_subaccount_semantics = UNRESTRICTED
```

and can continue to the account-wide balances/netting reads when all other controlling predicates pass.

However, the installed implementation's sanitized execution summary/manifest retains the earlier embedded authoring source-binding identity. A future execution must not make an inference from OpenAPI 3.29.0 while emitting evidence that identifies only the older rendered-source binding.

Therefore the next bounded implementation task is:

```text
KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_01
```

Required purpose only:

```text
1. bind the exact task-current OpenAPI source identity used for execution;
2. permit the already-supported UNRESTRICTED source semantic to be supplied;
3. make sanitized execution evidence identify the actual task-current source
   record used for the inference;
4. preserve the historical authoring source binding separately;
5. add offline tests that fail if evaluated source and emitted evidence source
   diverge.
```

The correction must not broaden B1 endpoints, request count, retries, redirects, credentials, parsers, account-wide proof predicates, Demo/production separation, or any venue-write capability.

## 8. Current state after source resolution

```text
B1_CURRENT_SOURCE_GAP = RESOLVED
B1_CURRENT_OPENAPI_VERSION = 3.29.0
B1_CURRENT_OPENAPI_SHA256 = 99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed
B1_CURRENT_APIKEY_ABSENT_NULL_SEMANTIC = UNRESTRICTED
B1_SELECTED_SURFACE_SOURCE_DRIFT = NONE_OBSERVED
B1_OPERATOR_02_HISTORICAL_TERMINAL = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
B1_ACCOUNT_WIDE_ENUMERATION_PROVEN = false
B1_NUMBERED_SUBACCOUNT_EXISTENCE = UNKNOWN
B1_PRIMARY_ONLY = UNKNOWN
B1_NEXT_TASK = KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_01
```

The historical primary remains unchanged:

```text
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

## 9. Execution boundary

No further authenticated B1 execution is authorized by this checkpoint.

After the evidence-binding correction is implemented, independently reviewed, and canonically installed, a separate explicit task may authorize a fresh bounded B1 read-only execution.

That future execution must not be described as an automatic retry of Local Operator 02.
