# PROJECT STATE CHECKPOINT — 2026-08-27 — MANUAL RESTING/CANCEL POSITIVE CANARY SPEC

Authority level: canonical current-state overlay.

This checkpoint records accepted state facts that post-date portions of `project_context/PROJECT_STATE.md` and the 2026-08-26 Route-A checkpoint. For the exact facts listed here, this checkpoint controls over older state text until a later consolidation folds these facts into `PROJECT_STATE.md` and `ARTIFACT_INDEX.md`.

This file grants no capability. It is a documentation/provenance record only.

## 1. Installation base

The accepted canary specification/handoff were reviewed against exact canonical base:

```text
repository = rigolugo/ARB
branch = main
base_HEAD = 997954197ebb8cbfb13baa3231b490abfbe20f64
base_tree = d3f392832132106f38fa1ba6d4fc715b9df18417
base_parent = d8b6f5f5db5fa76605dcd4ca1bd77fb0e16a5559
```

The containing commit is documentation/provenance only. It does not alter runtime code, persistent state, writer-proof state, venue state, or credentials.

## 2. Accepted controlling canary specification

Canonical specification installed by this checkpoint:

```text
specifications/KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02.md
raw_bytes = 93365
sha256 = b081feeee22d051d0f3f89b271e8029ab077d819512272df19b2151f5a254395
```

Canonical subordinate handoff installed by this checkpoint:

```text
handoffs/HANDOFF_KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02.md
raw_bytes = 19475
sha256 = ab31ad493b16be42d35c0dd912726506b347e5cc111987a29dc3d1c5314b0d81
```

Canonical review record installed with this checkpoint:

```text
reviews/REVIEW_KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02.md
review_disposition = APPROVE
```

The installed specification is the accepted controlling manual resting-order/cancel positive-canary contract in its exact scope. The blocked original SPEC_01 and blocked Correction 01 remain historical lineage only and are not installed here as competing controlling specifications.

## 3. Exact accepted source-binding identity

The accepted canary operation binding remains:

```text
binding_schema_revision = 2
binding_label = CANARY_OPENAPI_OPERATION_BINDING_REV2
canonical_json_bytes = 2672
canonical_json_sha256 = bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8
portfolio_subaccount_policy = EXPLICIT_FROM_CANARY_DOMAIN_IDENTITY__NO_DEFAULT
```

The future observer remains programmatic GET-only and binds these exact six operations under the specification's source-freshness rules:

```text
GET /markets/{ticker}
GET /markets/{ticker}/orderbook
GET /portfolio/orders
GET /portfolio/orders/{order_id}
GET /portfolio/fills
GET /portfolio/positions
```

This checkpoint does not establish future OpenAPI freshness by itself.

## 4. Historical primary-domain state remains held

The accepted historical primary conflict domain remains:

```text
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0
```

The historical incident remains:

```text
incident_id = KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01
disposition = WRITE_UNRESOLVED_ZERO_MATCH
bound_order_id = null
writer_proof_state = HELD
writer_proof_release_eligible = false
historical_incident_cancel_target = NONE
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
release_eligible = false
normal_writer_eligible = false
```

Do not infer from prior zero-match evidence:

```text
CREATE_NEVER_EXISTED
CREATE_DEFINITELY_FAILED
SAFE_TO_RETRY_CREATE
SAFE_TO_CANCEL
ZERO_EXPOSURE
WRITER_PROOF_RELEASED
INCIDENT_CLOSED
```

## 5. Current canary execution readiness

Current accepted canary theorem:

```text
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
current_canary_domain_identity = NONE_PROVEN
manual canary execution now = NOT READY / NOT AUTHORIZED
future canary lifecycle contract = CONDITIONALLY_SPECIFIED
```

The held primary subaccount-0 domain is not a valid target for new canary risk while its accepted state remains held/risk-write-ineligible.

None of the following creates economic-domain separation:

```text
different ticker on same account/subaccount
manual browser transport
new process
new local database
new ledger path
new authority file
new namespace
new strategy instance
restart
```

The following remains prohibited:

```text
fallback_to_primary_subaccount_0 = PROHIBITED
implicit/default primary subaccount = PROHIBITED
```

## 6. Conditional future canary routes

Exactly two future readiness routes are defined by the accepted specification:

```text
ROUTE_CANARY_PRIMARY_READY
ROUTE_CANARY_SEPARATE_DOMAIN_READY
```

Neither route is currently available.

`ROUTE_CANARY_PRIMARY_READY` requires later accepted proof that the exact primary conflict domain is no longer held/risk-write-ineligible and satisfies all then-controlling predicates for new risk.

`ROUTE_CANARY_SEPARATE_DOMAIN_READY` requires a genuinely separate venue/economic domain with accepted proof of exact identity, isolation, inception/history completeness, no unresolved order/fill/position/inventory/exposure, required persistence compatibility/binding, and exact readiness-review identity.

The canary itself cannot create or prove the substrate theorem that opens its own gate.

## 7. Next enabling stage

The next enabling work is substrate/domain-readiness work rather than another order attempt on primary subaccount `0`.

The accepted canary specification references the controlling Route-B sequence without authorizing it. The next bounded stage is:

```text
B1 = READ_ONLY account/subaccount capability-and-facts task
```

B1 must receive its own exact dispatch/capability envelope before execution. This checkpoint does not authorize B1 network access or credential use merely by naming it as the next stage.

No account/subaccount creation, funding/transfer, clean-domain bootstrap, or Gate-D execution is authorized by this checkpoint.

## 8. Restart routing

For fresh-chat restart:

1. read root `START_HERE.md`;
2. read `project_context/START_HERE.md`;
3. read `project_context/PROJECT_STATE.md`;
4. read `project_context/PROJECT_STATE_CHECKPOINT_2026_08_26_ROUTE_A_A4.md` for accepted Route-A/A3/A4 facts;
5. read this checkpoint for the accepted manual resting/cancel canary specification and current domain-readiness state;
6. read the exact installed specification/handoff/review above when working on the canary or its enabling substrate path.

This checkpoint does not grant implementation, tests, network, credentials, venue writes, browser order actions, persistent-state mutation, writer release, Gate-D execution, or production capability.
