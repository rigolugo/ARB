# PROJECT STATE CHECKPOINT — 2026-08-28 — ROUTE B B1 CURRENT OPENAPI SOURCE RESOLUTION

Authority level: canonical current-state overlay.

This checkpoint records the accepted credential-free task-current official-source
resolution performed after Route-B B1 Local Operator 02 and also records the
provenance correction required after the first repository installation of this
milestone.

It supplements, and does not rewrite,
`PROJECT_STATE_CHECKPOINT_2026_08_28_ROUTE_B_B1_AUTHENTICATED_EXECUTION.md`.

This checkpoint grants no credential use, authenticated Kalshi request, venue
write, production access, persistent-state mutation, writer-proof release, or
later-stage capability.

## 1. Canonical provenance correction

The first source-milestone commit:

```text
e1179f7c527e5a1a3b0b5b0620861ed1655e3071
```

correctly recorded the externally observed raw OpenAPI identity in prose, but
incorrectly claimed that exact raw bytes had been installed at:

```text
project_archive/kalshi_sources/KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml
```

The repository object actually installed at that path was:

```text
raw_bytes = 65640
sha256 = a2bb972f75518baacaa6cdff9dfcc13dd376c744c007552acf30ddede0f1aae1
git_blob = b8d0e168da84f2a483ae9bcc30d68a5b329e7324
```

That object is not the exact retrieved OpenAPI and is not authoritative source
evidence. It is removed by the provenance-correction commit that installs this
revised checkpoint.

No technical conclusion in this checkpoint relies on the removed object.

The exact retrieved raw OpenAPI remains noncanonical/local evidence identified
below. Its deterministic sanitized source-resolution report is installed
canonically.

## 2. Public official-source probe

Task:

```text
KALSHI_DEMO_ROUTE_B_B1_CURRENT_OPENAPI_SOURCE_RESOLUTION_01
```

Only this public official source was retrieved:

```text
https://docs.kalshi.com/openapi.yaml
```

Observed activity:

```text
network_activity = PUBLIC_OFFICIAL_DOCUMENTATION_ONLY
credential_activity = NONE
kalshi_demo_api_activity = NONE
production_api_activity = NONE
venue_write_activity = NONE
http_status = 200
content_type = text/yaml
```

Exact retrieved raw source identity:

```text
filename = KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml
storage = LOCAL_ONLY_EXTERNAL_SOURCE_EVIDENCE
raw_bytes = 325930
sha256 = 99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed
OpenAPI = 3.0.0
info.version = 3.29.0
```

The exact raw bytes are NOT represented as a repository-resident Git blob by
this checkpoint. Future byte-level reinspection therefore requires the exact
local/noncanonical artifact with the identity above.

Canonical sanitized source-resolution report:

```text
project_archive/kalshi_sources/KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01_REPORT.json
raw_bytes = 1151
sha256 = 85a6f371dbbe026198cff39366978b133a67c41b15f4abfd180b2077a268577a
git_blob = 3d1d45b0a53dedba1e054456fb498040d8c7deac
```

Detached local sidecar identity:

```text
KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml.sha256
storage = LOCAL_ONLY_DERIVED_EVIDENCE
raw_bytes = 115
sha256 = 75ba80de1a512b685d9396eebf6af7b6d76bcf2081740eda2e29dbeff70abb5b
```

Authority of the external source:

```text
OFFICIAL_KALSHI_SOURCE_NONCONTROLLING
```

The report is an accepted canonical projection of the direct public-source
observation; it does not itself become an external controlling requirement.

## 3. Exact ApiKey.subaccount semantic resolved

The exact retrieved 3.29.0 source and the canonical report establish:

```text
ApiKey.required = [api_key_id, name, scopes]
subaccount_property_found = true
subaccount_required = false
subaccount_nullable = true
subaccount_minimum = 0
subaccount_maximum = 63
```

Material source description:

```text
If set, the API key is restricted to this single sub-account and may only read
and trade on it. Absent/null means the key is unrestricted.
```

Accepted B1 source theorem:

```text
GET_API_KEYS_RESPONSE_SUBACCOUNT_ABSENCE_SEMANTICS = UNRESTRICTED
CURRENT_OFFICIAL_SOURCE_EXPLICITLY_PROVES_ABSENT_NULL_UNRESTRICTED = true
```

This satisfies the source-semantic condition anticipated by B1-SRC-004 for a
future task-current source binding.

It does not retroactively alter Local Operator 02.

## 4. B1-relevant source drift check

Marco compared the exact current OpenAPI 3.29.0 raw artifact above against the
exact supplied historical OpenAPI 3.28.0 snapshot:

```text
historical_raw_bytes = 333315
historical_sha256 = cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b
```

The compared B1 GET operation objects were:

```text
GET /account/limits
GET /api_keys
GET /portfolio/subaccounts/balances
GET /portfolio/subaccounts/netting
```

The compared schemas were:

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

Those selected parsed objects were structurally equal after YAML parsing.

A deterministic canonical JSON projection of the selected current objects had:

```text
projection_raw_bytes = 6020
projection_sha256 = d1f5a2a42e8073424923f70a6306038724e838d3b69f5772202ad5e2c3e2725b
```

Disposition:

```text
MATERIAL_B1_OPENAPI_DRIFT_ON_SELECTED_SURFACE = NONE_OBSERVED
```

This is a `DIRECT_EMPIRICAL_OBSERVATION` over the two exact source artifacts.
It does not claim whole-document equality.

## 5. Relationship to Local Operator 02

Local Operator 02 remains historically correct under its exact execution-time
source binding:

```text
current_key_match_state = UNIQUE
current_key_restriction_state = NOT_EXPOSED
terminal_outcome = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
request_count = 2
```

This checkpoint MUST NOT rewrite that result to `UNRESTRICTED`.

The new source theorem is prospective:

```text
A later B1 execution may classify an absent/null ApiKey.subaccount response
state as UNRESTRICTED only when it explicitly binds to this task-current
official-source evidence (or a later valid task-current source).
```

## 6. Evidence-binding implementation gap

The accepted B1 core implementation can evaluate a `TaskCurrentSourceRecord`
whose:

```text
api_keys_absent_subaccount_semantics = UNRESTRICTED
```

and can continue to balances/netting when all other controlling predicates pass.

However, its sanitized manifest/summary currently serialize the fixed authoring
source-binding identity instead of the exact task-current source record supplied
to execution.

A future execution must not infer from OpenAPI 3.29.0 while emitting evidence
that identifies only the older rendered-source binding.

Therefore the next bounded implementation task remains:

```text
KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_01
```

Required purpose only:

```text
1. bind the exact task-current source identity used for execution;
2. permit the already-supported UNRESTRICTED source semantic to be supplied;
3. make sanitized execution evidence identify the actual task-current source;
4. preserve the historical authoring source binding separately;
5. add offline tests that fail if evaluated source and emitted source diverge.
```

The correction must not broaden B1 endpoints, request count, retries, redirects,
credentials, parsers, account-wide proof predicates, Demo/production
separation, or venue-write capability.

## 7. Current state

```text
B1_CURRENT_SOURCE_GAP = RESOLVED
B1_CURRENT_OPENAPI_VERSION = 3.29.0
B1_CURRENT_OPENAPI_RAW_STORAGE = LOCAL_ONLY_EXTERNAL_SOURCE_EVIDENCE
B1_CURRENT_OPENAPI_RAW_BYTES = 325930
B1_CURRENT_OPENAPI_SHA256 = 99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed
B1_CURRENT_SOURCE_REPORT = CANONICAL
B1_CURRENT_APIKEY_ABSENT_NULL_SEMANTIC = UNRESTRICTED
B1_SELECTED_SURFACE_SOURCE_DRIFT = NONE_OBSERVED
B1_OPERATOR_02_HISTORICAL_TERMINAL = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
B1_ACCOUNT_WIDE_ENUMERATION_PROVEN = false
B1_NUMBERED_SUBACCOUNT_EXISTENCE = UNKNOWN
B1_PRIMARY_ONLY = UNKNOWN
B1_NEXT_TASK = KALSHI_DEMO_ROUTE_B_B1_CURRENT_SOURCE_BINDING_AND_EXECUTION_EVIDENCE_CORRECTION_01
```

Historical primary remains:

```text
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

## 8. Execution boundary

No further authenticated B1 execution is authorized by this checkpoint.

After the evidence-binding correction is implemented, independently reviewed,
and canonically installed, a separate explicit task may authorize a fresh
bounded B1 read-only execution.

That future execution must not be described as an automatic retry of Local
Operator 02.
