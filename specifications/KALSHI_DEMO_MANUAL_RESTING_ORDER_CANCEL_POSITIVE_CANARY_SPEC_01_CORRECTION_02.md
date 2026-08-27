# KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02

```yaml
artifact_class: TECHNICAL_SPECIFICATION
task_class: SPEC_ONLY
correction_class: BOUNDED_SAME_SCOPE_CORRECTION_02
technical_scope: KALSHI_DEMO_MANUAL_BROWSER_RESTING_ORDER_CANCEL_POSITIVE_CANARY_OBSERVATION_ONLY
risk_tier: HIGH
repository: rigolugo/ARB
branch: main

canonical_main_verified: 997954197ebb8cbfb13baa3231b490abfbe20f64
canonical_tree_verified: d3f392832132106f38fa1ba6d4fc715b9df18417
canonical_parent_verified: d8b6f5f5db5fa76605dcd4ca1bd77fb0e16a5559

blocked_predecessor_spec_bytes: 92102
blocked_predecessor_spec_sha256: 24624214e43e788a174dfdecc56f14dbb324db7f7db427ea4251adc3512a642f
blocked_predecessor_handoff_bytes: 18423
blocked_predecessor_handoff_sha256: 7dd278687758260c6f1b1ba5d74de4a32cc1265a0bb0aa497b47a801196fd64f

canary_execution_domain_readiness: NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
canary_real_execution_eligible: false
historical_primary_domain_state: HELD
future_canary_lifecycle_contract: CONDITIONALLY_SPECIFIED

implementation_performed_by_this_artifact: false
tests_executed_by_this_artifact: false
credentials_used_by_this_artifact: false
venue_requests_by_this_artifact: 0
venue_writes_by_this_artifact: 0
persistent_state_mutated_by_this_artifact: false
repository_modified_by_this_artifact: false
git_write_activity_by_this_artifact: NONE

future_manual_demo_create_authorized_by_this_spec: false
future_manual_demo_cancel_authorized_by_this_spec: false
future_programmatic_demo_gets_authorized_by_this_spec: false
future_programmatic_demo_writes_authorized_by_this_spec: false
```

## 1. Purpose

This Correction 02 is a bounded same-scope source-binding identity correction to the exact blocked Correction 01. It changes no technical contract beyond the two Appendix-A repairs identified in `CANARY-TRACE-003`.

This Correction 01 preserves the blocked predecessor's narrow positive empirical canary lifecycle while correcting one material execution-domain defect: the future canary MUST NOT assume that primary subaccount `0`, a different ticker, manual browser transport, or any local namespace constitutes a currently valid domain for new risk.

Current disposition is exactly:

```text
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

Therefore the lifecycle below is **conditionally specified future behavior only**. It may be entered only after a later accepted domain-readiness artifact, bound by exact identity under Section 9A, proves one of the two allowed readiness routes for the exact venue/economic domain and a separate execution task authorizes the corresponding capabilities.

Once that future readiness gate is validly open, the intended lifecycle remains exactly:

```text
accepted exact canary_domain_identity
    ->
one preselected Demo market inside that exact domain
    ->
GET-only baseline with explicit bound subaccount on every portfolio query
    ->
one user-performed browser CREATE of one 1.00-contract BUY YES LIMIT
    ->
GET-only exact order binding
    ->
authoritative exact-order resting proof
    ->
one user-performed browser CANCEL of that same visible order, if still open
    ->
GET-only exact terminal order + fills + position observation
    ->
deterministic terminal classification + evidence package
```

The specification defines a future observation contract. It does not authorize or perform any venue request, credential use, browser order action, account/subaccount inspection, domain creation, funding/transfer, clean-domain bootstrap, persistent-state mutation, implementation, test, repository change, or Gate-D release.

The canary's purpose remains empirical venue-lifecycle evidence. It is not an execution-substrate authorization path, a writer-proof bypass, a market-making experiment, or proof that any currently safe canary domain exists.

## 2. Exact canonical repository and provenance gate

### CANARY-BASE-001 — canonical repository identity

The repository state independently observed for this Correction 02 is:

```text
repository = rigolugo/ARB
branch = main
main = 997954197ebb8cbfb13baa3231b490abfbe20f64
tree = d3f392832132106f38fa1ba6d4fc715b9df18417
parent = d8b6f5f5db5fa76605dcd4ca1bd77fb0e16a5559
```

A later implementation or execution MUST independently reverify the exact base required by its own task and MUST stop on unexplained drift. This specification does not silently retarget any older base-bound artifact.

### CANARY-BASE-002 — controlling predecessor

The controlling current execution-substrate/writer-eligibility input is:

```text
KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md
bytes = 68568
sha256 = 512000eea8db5562768682ae1659c03c20a2b5093fba68ef37eae784039a8336
```

Subordinate handoff:

```text
HANDOFF_KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md
bytes = 15390
sha256 = 57a37e444afcf0706adcc5f4f09bb280dc04c46a2fff8b4e678f6aead2dbaac8
```

The controlling dispositions remain:

```text
current_domain_readiness = NOT_GATE_D_EXECUTION_READY
overall_disposition = NO_CURRENTLY_VALID_EXECUTION_SUBSTRATE_PATH
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
```

No later accepted repository state inspected for this task superseded those dispositions in a way that makes the held primary conflict domain ready for new risk.

### CANARY-BASE-003 — current historical incident remains held

The current accepted incident state remains exactly:

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

This canary MUST NOT alter, release, retry, cancel, rewrite, reconcile, clone, or reinterpret that incident.

The canary MUST NOT infer any of:

```text
CREATE_NEVER_EXISTED
CREATE_DEFINITELY_FAILED
SAFE_TO_RETRY_CREATE
SAFE_TO_CANCEL
ZERO_EXPOSURE
WRITER_PROOF_RELEASED
INCIDENT_CLOSED
```

### CANARY-BASE-004 — exact blocked predecessor lineage

Correction 02 is a bounded same-scope correction of exactly:

```text
KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_01.md
bytes = 92102
sha256 = 24624214e43e788a174dfdecc56f14dbb324db7f7db427ea4251adc3512a642f

HANDOFF_KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_01.md
bytes = 18423
sha256 = 7dd278687758260c6f1b1ba5d74de4a32cc1265a0bb0aa497b47a801196fd64f
```

Those artifacts are the exact immediate blocked predecessor lineage. Correction 02 preserves every technical requirement from Correction 01 and repairs only the two stale Appendix-A source-binding identity values identified in `CANARY-TRACE-003`.

### CANARY-BASE-005 — exact current canary readiness disposition

At authoring time:

```text
historical_primary_conflict_domain =
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0

historical_primary_domain_state = HELD

CANARY_EXECUTION_DOMAIN_READINESS =
NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN

CANARY_REAL_EXECUTION_ELIGIBLE =
false

current_canary_domain_identity =
NONE_PROVEN
```

No ticker, browser transport, process, database, ledger path, authority file, namespace, strategy instance, or restart changes this disposition.

## 3. Authority taxonomy for premises

Every material premise in this specification falls into one of four classes:

```text
CONTROLLING_ARB_REQUIREMENT
NON_CONTROLLING_EMPIRICAL_EVIDENCE
NON_CONTROLLING_EXTERNAL_RESEARCH
ARB_SPEC_INFERENCE
```

`CONTROLLING_ARB_REQUIREMENT` controls directly.

`NON_CONTROLLING_EMPIRICAL_EVIDENCE` and `NON_CONTROLLING_EXTERNAL_RESEARCH` are not requirements by themselves. A requirement derived from them becomes normative only where this specification explicitly adopts it.

`ARB_SPEC_INFERENCE` is an implementation-portable safety or reconciliation rule deliberately introduced by this specification and must be tested as such.

Unsupported venue semantics remain unresolved rather than being silently invented.

---

## 4. Current-task capability matrix

This SPEC_ONLY task has exactly the following capability envelope:

| Capability | Current task |
|---|---|
| Canonical repository read/sync | PERMITTED_AS_NEEDED |
| Repository modification | PROHIBITED |
| Local Git writes | PROHIBITED |
| Remote Git writes | PROHIBITED |
| Implementation-source authoring | PROHIBITED |
| Test-source authoring | PROHIBITED |
| Test execution | PROHIBITED |
| Package installation | PROHIBITED |
| Persistent ARB state mutation | PROHIBITED |
| Kalshi network | PROHIBITED |
| Kalshi Demo GET | PROHIBITED |
| Kalshi Demo write | PROHIBITED |
| Kalshi production | PROHIBITED |
| Credential read | PROHIBITED |
| Credential signing | PROHIBITED |
| WebSocket | PROHIBITED |
| Funding/transfer | PROHIBITED |
| Specification/handoff artifact generation | PERMITTED |

Anything omitted is prohibited for this task.

The future execution envelope described later is a technical contract only. It is not activated by this document.

---

## 5. Exact task-current OpenAPI source identity

### CANARY-SRC-001 — source snapshot

The supplied task-current source snapshot is:

```text
file = 04_TASK_CURRENT_SOURCE/openapi.yaml
bytes = 333315
sha256 = cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b
OpenAPI = 3.0.0
API info version = 3.28.0
```

This source was consumed statically. No current Kalshi network research was performed by this specification task.

The source exposes Demo REST servers including:

```text
https://external-api.demo.kalshi.co/trade-api/v2
https://demo-api.kalshi.co/trade-api/v2
```

The future observer defined here MUST pin exactly:

```text
scheme = https
host = external-api.demo.kalshi.co
port = 443
base_path = /trade-api/v2
```

It MUST NOT fall back to another Demo host or any production host.

### CANARY-SRC-002 — exact operation binding record

Correction 01 preserves the same six GET operations and source schemas while revising the planned portfolio-query contract so subaccount is supplied explicitly from the accepted `canary_domain_identity` instead of being fixed/defaulted to primary.

The canary operation binding therefore has schema revision `2`.

Canonical binding serialization is UTF-8 JSON with:

```text
object keys sorted lexicographically
no insignificant whitespace
separators exactly ',' and ':'
Unicode emitted as UTF-8, not ASCII escape expansion when not otherwise required
```

The canonical binding record has:

```text
canonical_json_bytes = 2672
canonical_json_sha256 = bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8
```

The exact record is Appendix A.

The six operation-specific bindings remain:

| Method | Path | operationId | Auth class | 200 schema |
|---|---|---|---|---|
| GET | `/markets/{ticker}` | `GetMarket` | PUBLIC | `GetMarketResponse` |
| GET | `/markets/{ticker}/orderbook` | `GetMarketOrderbook` | AUTHENTICATED_READ_ONLY | `GetMarketOrderbookResponse` |
| GET | `/portfolio/orders` | `GetOrders` | AUTHENTICATED_READ_ONLY | `GetOrdersResponse` |
| GET | `/portfolio/orders/{order_id}` | `GetOrder` | AUTHENTICATED_READ_ONLY | `GetOrderResponse` |
| GET | `/portfolio/fills` | `GetFills` | AUTHENTICATED_READ_ONLY | `GetFillsResponse` |
| GET | `/portfolio/positions` | `GetPositions` | AUTHENTICATED_READ_ONLY | `GetPositionsResponse` |

For `GetOrders`, `GetFills`, and `GetPositions`, the binding's exact planned policy is:

```text
portfolio_subaccount_policy =
EXPLICIT_FROM_CANARY_DOMAIN_IDENTITY__NO_DEFAULT
```

The supplied OpenAPI describes `subaccount` as an integer query parameter whose omission defaults to primary `0`. This specification deliberately prohibits relying on that default. Every portfolio request in the future canary MUST serialize the exact accepted `venue_subaccount` explicitly.

No source binding is generalized across another endpoint.

### CANARY-SRC-003 — authentication surface

For the five authenticated operations, the supplied source requires operation security through:

```text
KALSHI-ACCESS-KEY
KALSHI-ACCESS-SIGNATURE
KALSHI-ACCESS-TIMESTAMP
```

The future observer's credential-source convention remains exactly:

```text
KALSHI_DEMO_API_KEY_ID
KALSHI_DEMO_PRIVATE_KEY_PATH
```

`KALSHI_DEMO_PRIVATE_KEY_PATH` contains only a local filesystem path to a private-key file. It MUST NOT contain private-key bytes.

This convention deliberately differs from older repository-local implementations that may use a PEM-content environment variable. The later observer MUST implement the exact convention in this specification and MUST NOT silently substitute another secret source.

### CANARY-SRC-004 — source freshness at future execution

The snapshot above proves this specification's reviewed source identity. It does not prove future freshness.

Before any later real canary execution, the execution package MUST bind a task-current official OpenAPI snapshot for the six operations above. The later task may obtain that source through separately permitted official-documentation access or may consume an externally supplied exact current source artifact. If the relevant operation contract materially differs from Appendix A, the future execution MUST halt with:

```text
CANARY_SOURCE_DRIFT
```

A later source-verification requirement does not authorize network access by this specification.

## 6. Exact source schemas and lexical rules

### CANARY-SCHEMA-001 — Order status vocabulary

`Order.status` is exactly one of:

```text
resting
canceled
executed
```

Any other value is malformed for this canary source binding.

### CANARY-SCHEMA-002 — Order required fields

For every `Order` consumed by this canary, the source requires:

```text
order_id: string
user_id: string
client_order_id: string
ticker: string
outcome_side: string enum {yes,no}
book_side: BookSide enum {bid,ask}
type: string enum {limit,market}
status: OrderStatus
yes_price_dollars: FixedPointDollars
no_price_dollars: FixedPointDollars
fill_count_fp: FixedPointCount
remaining_count_fp: FixedPointCount
initial_count_fp: FixedPointCount
taker_fees_dollars: FixedPointDollars
maker_fees_dollars: FixedPointDollars
taker_fill_cost_dollars: FixedPointDollars
maker_fill_cost_dollars: FixedPointDollars
```

Optional source fields include `created_time`, `last_update_time`, `subaccount_number`, `exchange_index`, and others. The observer MUST validate any optional field it consumes but MUST NOT treat an optional field as source-required.

`client_order_id` is source-required as a string but a manually submitted browser order may expose an empty string. This canary MUST NOT require a nonempty `client_order_id` for binding.

### CANARY-SCHEMA-003 — Fill required fields

Every `Fill` consumed by the canary requires:

```text
fill_id: string
exchange_index: integer
trade_id: string
order_id: string
ticker: string
market_ticker: string
outcome_side: string enum {yes,no}
book_side: BookSide enum {bid,ask}
count_fp: FixedPointCount
yes_price_dollars: FixedPointDollars
no_price_dollars: FixedPointDollars
is_taker: boolean
fee_cost: FixedPointDollars
```

`created_time`, `subaccount_number`, and `ts` are optional under the supplied schema and are supporting evidence when present.

### CANARY-SCHEMA-004 — Position required fields

Every `MarketPosition` consumed by the canary requires:

```text
ticker: string
exchange_index: integer
total_traded_dollars: FixedPointDollars
position_fp: FixedPointCount
market_exposure_dollars: FixedPointDollars
realized_pnl_dollars: FixedPointDollars
fees_paid_dollars: FixedPointDollars
last_updated_ts: date-time string
```

`GetPositionsResponse` requires both:

```text
market_positions: array
event_positions: array
```

Its `cursor` is optional.

A missing exact ticker row after complete pagination MUST be represented as:

```text
ABSENT_FROM_COMPLETE_RESPONSE
```

It MUST NOT be normalized to numeric zero.

### CANARY-SCHEMA-005 — fixed-point precision

The supplied source defines:

```text
FixedPointCount = string
responses always emit 2 decimal places
minimum granularity = 0.01 contract

FixedPointDollars = string
responses emit up to 6 decimal places
```

All economic/count parsing and arithmetic MUST use exact decimal/fixed-point semantics. Binary floating point is prohibited for:

```text
price
quantity
fees
fill cost
position
exposure
PnL
```

A JSON number where a bound fixed-point field requires a string is malformed.

### CANARY-SCHEMA-006 — market price grid

`Market` exposes:

```text
market_type enum {binary,scalar}
status enum {initialized,inactive,active,closed,determined,disputed,amended,finalized}
price_level_structure: string
price_ranges: array<PriceRange>
```

Each `PriceRange` requires string fields:

```text
start
end
step
```

The future observer MUST derive valid canary prices only from the exact returned `price_ranges`. It MUST NOT assume a universal one-cent tick.

---

## 7. Non-controlling empirical inputs and their permitted use

The following empirical files were verified by exact bytes and SHA-256 and are non-controlling:

```text
order-response.json
bytes = 723
sha256 = d0c09a2fabbef633750925eac5689b4889b2bc08524eb6c42178e8ed87ab30d2

fills-response.json
bytes = 535
sha256 = 8aecdfd8b7f5330631cf0d5783be09c64378558953fa963267168e3fa5b5e38f

position-response.json
bytes = 519
sha256 = 3976454ab8e478033a1f6e82836dd981918db0f757580d4129f972147d8ff809

market-research-summary.json
bytes = 13325
sha256 = b7cceccffbda5cd8d03b6f2e0de1691a338f1848a9e393e66d46096b30740290

shadow-mm-summary.json
bytes = 19908
sha256 = fee369ffa79ad1d74a39774daa4f0ab856964e0dce3d72f81342a56c55fdc8c2

shadow-trades.jsonl
bytes = 56727
sha256 = f91774eafe4d5c13ba3ee3cfe3a50a4126974d9a1c55213b9568552c7348b8a0
```

The prior positive manual full-fill evidence showed one exact Demo order/fill/position representation with:

```text
order_id present
status = executed
order.type = market
fill.order_id exactly matching order.order_id
position ticker matching the order ticker
fixed-point strings in the current representation
```

Those observations support the decision to require exact venue-native order identity and cross-surface reconciliation. They do not establish resting-order or cancellation semantics.

The market/shadow research supports only the feasibility of selecting an active two-sided Demo binary market. It does not establish profitability, queue priority, future liquidity, actual maker fills, or production behavior.

The previously observed ticker `KXRAINSHARD2-26AUG28-TTN` is not a fixed dependency of this specification.

---

## 8. Deliberately adopted non-controlling research findings

The non-controlling research ledger is incorporated only for the following safety principles:

### CANARY-RES-001 — exact identity before cancellation

A cancellation target MUST be based on exact bound venue `order_id` evidence, not ticker-only, price-only, time-only, or fuzzy matching.

### CANARY-RES-002 — ambiguity does not authorize another create

Unknown/ambiguous CREATE or cancellation evidence MUST NOT trigger a second canary CREATE. The one-create budget is consumed once the user performs the browser CREATE action.

### CANARY-RES-003 — missing position is not zero

A failed position read or absent position row MUST NOT be normalized to zero exposure.

### CANARY-RES-004 — no timer/reconnect recovery

No timer, reconnect, process restart, or observation timeout may automatically create a replacement order or infer that a browser cancellation succeeded.

These principles are normative here because this section explicitly adopts them.

---

## 9. Future canary capability envelope

The following is a **maximum conditional envelope**, not a currently active capability set.

A later separately authorized execution conforming to this specification MAY contain the capabilities below only after Section 9A's exact domain-readiness gate has succeeded before any venue request or browser action:

| Capability | Future canary maximum |
|---|---|
| Environment | `KALSHI_DEMO` only |
| Exact canary domain | one exact accepted `canary_domain_identity` |
| Selected ticker | exactly one per execution; ticker is not a conflict-domain separator |
| Manual browser CREATE | exactly one, only inside the accepted exact canary domain |
| CREATE quantity | exactly `1.00` contract |
| CREATE direction | `BUY YES` |
| CREATE type | `LIMIT` |
| Manual browser CANCEL | at most one total; same exact canary domain and same exact canary order only |
| Programmatic HTTP methods | `GET` only |
| Programmatic venue writes | `0` |
| Programmatic POST | PROHIBITED |
| Programmatic DELETE | PROHIBITED |
| Programmatic PATCH/PUT | PROHIBITED |
| Programmatic amend/decrease/replace | PROHIBITED |
| Batch order operations | PROHIBITED |
| Cancel-all | PROHIBITED |
| WebSocket | PROHIBITED |
| Production | PROHIBITED |
| Funding/transfer during canary | PROHIBITED |
| Account/subaccount/domain creation during canary | PROHIBITED |
| Canonical persistent-state mutation during canary | PROHIBITED |
| Historical-incident action | PROHIBITED |
| Second CREATE after any outcome | PROHIBITED |
| Primary-domain fallback after alternate-domain failure | PROHIBITED |

The future browser CREATE and CANCEL are manual user actions. The future observer is programmatic GET-only.

No implementation, readiness artifact, or this specification activates execution capability by itself. A separate execution task is always required.

## 9A. Closed execution-domain readiness gate

### CANARY-DOMAIN-001 — gate executes before all venue activity

Before any future observer GET, credential load/signing, browser CREATE prompt, or browser CANCEL capability can be entered, the implementation MUST validate an exact accepted domain-readiness record and construct one exact `canary_domain_identity`.

If the record is absent, stale relative to the execution task's required base, malformed, identity-mismatched, route-incomplete, or not positive for the exact domain:

```text
terminal_class = CANARY_EXECUTION_DOMAIN_NOT_READY
request_count = 0
manual_create_count = 0
manual_cancel_count = 0
```

No venue request or manual order action may be used to discover a fallback domain after this failure.

Current task disposition remains:

```text
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

### CANARY-DOMAIN-002 — exact future `canary_domain_identity`

A future positive readiness artifact MUST bind one immutable domain identity containing at minimum:

```text
environment
account_scope_ref
venue_subaccount
conflict_domain_ref
domain_readiness_evidence_ref
domain_readiness_review_identity
readiness_route
```

Requirements:

```text
environment = exactly KALSHI_DEMO
account_scope_ref = exact nonempty stable account-scope reference
venue_subaccount = exact built-in integer, bool excluded, in the task-current OpenAPI domain 0..63 (0 primary, 1..63 subaccounts), reverified before future execution
conflict_domain_ref = exact venue/economic conflict-domain reference
domain_readiness_evidence_ref = exact artifact identity, including raw bytes and sha256
domain_readiness_review_identity = exact accepted current readiness-review record identity
readiness_route = exactly one of:
    ROUTE_CANARY_PRIMARY_READY
    ROUTE_CANARY_SEPARATE_DOMAIN_READY
```

No concrete future `account_scope_ref`, `venue_subaccount`, alternate conflict domain, or readiness artifact identity is invented by this specification.

Every portfolio GET supporting the canary MUST serialize the `subaccount` query parameter explicitly from `canary_domain_identity.venue_subaccount`. Omission, implicit defaulting, or caller substitution is prohibited even if the accepted subaccount happens to be `0`.

### CANARY-DOMAIN-003 — Route `ROUTE_CANARY_PRIMARY_READY`

This route is unavailable now.

A later accepted readiness artifact may select:

```text
ROUTE_CANARY_PRIMARY_READY
```

only if it proves for the exact primary conflict domain that:

1. the historical safety hold no longer makes the domain risk-write-ineligible;
2. the exact primary conflict domain satisfies every then-controlling predicate required before introducing new risk;
3. the accepted readiness evidence does not rely on ticker switching, browser/manual transport, local namespace changes, or restart as separation;
4. no unresolved controlling order/fill/position/inventory/exposure condition remains that would prohibit the canary's new risk;
5. the readiness conclusion is current for the future execution task and bound to an exact artifact identity.

This specification does not define how the historical hold is resolved and does not perform or authorize that work.

### CANARY-DOMAIN-004 — Route `ROUTE_CANARY_SEPARATE_DOMAIN_READY`

This route is unavailable now.

A later accepted readiness artifact may select:

```text
ROUTE_CANARY_SEPARATE_DOMAIN_READY
```

only for a genuinely separate venue/economic domain and only if it binds and positively proves, at minimum:

```text
environment
account_scope_ref
exact venue_subaccount/domain identity
exact conflict_domain_ref
actual venue/economic isolation from the held primary domain
domain inception class
exact domain inception evidence identity
complete-history theorem from actual domain inception
ambiguous domain-creation result = NONE
unresolved order state = NONE
unresolved fill state = NONE
unresolved position state = NONE
unresolved inventory state = NONE
unresolved exposure state = NONE
required durable clean-domain persistence compatibility = SATISFIED
exact durable clean-domain authority/ledger binding = COMPLETE
accepted current readiness-review identity
```

The inception class MUST be one of the controlling Route-B classes when applicable:

```text
NEWLY_CREATED_DOMAIN
PREEXISTING_BUT_APPARENTLY_UNUSED_DOMAIN
```

For `NEWLY_CREATED_DOMAIN`, the readiness artifact MUST bind authoritative creation identity/result evidence and the actual venue inception boundary. An ambiguous creation result is disqualifying.

For `PREEXISTING_BUT_APPARENTLY_UNUSED_DOMAIN`, zero current orders/fills/positions/balance is not a completeness theorem. Complete prior economic history from actual venue inception through the readiness snapshot MUST be proven under task-current source and retention semantics.

### CANARY-DOMAIN-005 — pseudo-separation is prohibited

None of the following establishes a separate venue/economic domain:

```text
different ticker on the same account/subaccount
manual browser transport
new process
new local database
new ledger path
new authority file
new namespace
new strategy instance
process restart
```

Therefore all are prohibited as substitutes for accepted domain-readiness evidence.

The following are also prohibited:

```text
fallback_to_primary_subaccount_0 = PROHIBITED
omitting subaccount so the API defaults to primary = PROHIBITED
switching ticker on primary to escape a readiness failure = PROHIBITED
creating another local namespace/database/ledger to escape a readiness failure = PROHIBITED
```

A failure of any separate-domain predicate closes the canary gate; it never selects the primary domain automatically.

### CANARY-DOMAIN-006 — controlling Route-B work is referenced, not imported

The controlling minimum Route-B sequence remains, as sequencing only:

```text
B1. READ_ONLY account/subaccount capability-and-facts task
B2. persistent clean-domain bootstrap specification revision
B3. implementation + offline tests of the persistent revision
B4a. bounded complete-history READ_ONLY reconciliation for a preexisting domain

OR

B4b. separate domain-creation write specification
     + durable creation-result reconciliation
     + separate execution capability

B5. separate funding/transfer contract if required
B6. clean-domain bootstrap binding using exact inception evidence
B7. canonical installation/readiness review
B8. only then later Gate-D market-maker execution specification
```

This canary specification authorizes none of B1-B8.

For the manual canary specifically, its future execution gate may open only after either:

```text
A. an accepted current primary-domain readiness artifact satisfying
   CANARY-DOMAIN-003;

or

B. completion through Route-B B7 for the exact separate domain plus an accepted
   current canary-domain readiness artifact satisfying CANARY-DOMAIN-004.
```

B8 remains a separate Gate-D market-maker stage and is not imported into this manual canary.

### CANARY-DOMAIN-007 — exact readiness artifact class required by the canary

The future canary MUST consume a readiness artifact whose normative payload is sufficient to reconstruct and validate the entire `canary_domain_identity` without inference.

At minimum its exact identity binding MUST include:

```text
artifact_name
raw_bytes
sha256
repository/base or canonical installation identity when applicable
readiness_route
environment
account_scope_ref
venue_subaccount
conflict_domain_ref
all route-specific proof/evidence references
result = CANARY_DOMAIN_READY_FOR_BOUNDED_NEW_RISK
```

The future execution task MUST name that exact artifact identity. A filename without byte/SHA binding, a user assertion, a current empty-order snapshot, or an implementation default is insufficient.

---

## 10. Future implementation path envelope

If a later implementation task is authorized from this specification, its default exact writable paths SHOULD be limited to:

```text
src/arb/venues/kalshi/manual_resting_cancel_canary.py
tests/test_kalshi_manual_resting_cancel_canary.py
```

Any implementation task that chooses different or additional writable paths must state them explicitly rather than inheriting broader repository write access.

Readable protected dependencies may include the exact canonical versions of:

```text
src/arb/venues/kalshi/models.py
src/arb/venues/kalshi/validation.py
src/arb/venues/kalshi/orderbook.py
src/arb/venues/kalshi/order_lifecycle.py
src/arb/venues/kalshi/quote_lifecycle.py
pyproject.toml
```

Those paths are readable dependencies, not writable by inference.

A later execution wrapper may be task-local and external to the repository unless a separate implementation decision makes it canonical supported behavior.

---

## 11. Future observer input contract

The future observer MUST receive exactly these non-secret execution inputs before any request:

```text
execution_id: exact nonempty string
canary_domain_identity: exact immutable identity validated under Section 9A
domain_readiness_evidence_ref: exact bytes/SHA-bound identity matching canary_domain_identity
domain_readiness_review_identity: exact accepted current review-record identity
environment: exactly KALSHI_DEMO and equal canary_domain_identity.environment
account_scope_ref: exact match to canary_domain_identity.account_scope_ref
subaccount: exact match to canary_domain_identity.venue_subaccount
conflict_domain_ref: exact match to canary_domain_identity.conflict_domain_ref
ticker: exact nonempty market ticker
demo_origin: exactly https://external-api.demo.kalshi.co
quantity_fp: exactly "1.00"
outcome_side: exactly "yes"
book_side: exactly "bid"
order_type: exactly "limit"
```

The future observer MUST reject before credential use or network:

```text
missing/unaccepted/stale domain-readiness evidence
domain-readiness result other than CANARY_DOMAIN_READY_FOR_BOUNDED_NEW_RISK
production environment
another host
omitted subaccount
implicit/default subaccount
subaccount differing from canary_domain_identity
account_scope_ref mismatch
conflict_domain_ref mismatch
ticker used as a domain-separation substitute
quantity other than "1.00"
market order
SELL or NO direction
a pre-populated order_id
write-capable programmatic transport capability
```

The observer MUST not accept a caller-provided canary price. It computes the proposed price from a fresh validated market/book snapshot under Section 13.

The observer MUST never rewrite `canary_domain_identity` in response to a market/read failure.

## 12. Deterministic market eligibility

### CANARY-MKT-001 — exactly one ticker per execution

A future execution starts with one ticker selected outside the observer's write logic. The observer validates that one ticker **inside the already accepted exact canary domain**.

If it is ineligible, the execution terminates `CANARY_MARKET_INELIGIBLE`. The same execution MUST NOT automatically rotate to another ticker.

A later execution task may choose a current equivalent ticker, but ticker selection cannot change or establish conflict-domain identity. The historical research ticker is merely a candidate while it remains eligible.

### CANARY-MKT-002 — market snapshot

Before the manual CREATE, the observer MUST obtain:

```text
GET /markets/{ticker}
GET /markets/{ticker}/orderbook?depth=0
```

`GetMarket` may be sent without credentials because the bound operation is public. The observer MUST NOT attach authentication headers to that public request.

`GetMarketOrderbook` MUST use the authenticated-read credential contract.

These market-level reads do not prove account/subaccount domain readiness.

### CANARY-MKT-003 — exact eligibility predicates

The market is eligible only if all are true at the final pre-CREATE eligibility snapshot:

```text
market.ticker == requested ticker
market.market_type == "binary"
market.status == "active"
market.close_time is valid timezone-aware RFC3339/date-time
market.close_time - current_utc >= 2 hours
market.yes_bid_dollars parses exactly
market.yes_ask_dollars parses exactly
market.yes_bid_size_fp > 0.00
market.yes_ask_size_fp > 0.00
best_yes_bid < best_yes_ask
orderbook_fp.yes_dollars is nonempty
orderbook_fp.no_dollars is nonempty
price_ranges is nonempty and structurally valid
```

The market snapshot and orderbook snapshot MUST be obtained within `10` seconds of one another by the observer's monotonic clock. If not, the market gate is stale and MUST be reacquired within the request budget before CREATE.

### CANARY-MKT-004 — no preexisting resting order in selected market

After Section 9A has already proven the exact canary domain and before manual CREATE, complete baseline order enumeration for:

```text
ticker = selected ticker
subaccount = canary_domain_identity.venue_subaccount
subaccount query parameter = EXPLICITLY_SERIALIZED
limit = 1000
```

MUST find zero orders with `status == "resting"` in that exact selected ticker/domain.

This is an **order-identification cleanliness predicate only**. It reduces the chance that the browser action will be confused with a preexisting visible order in the selected market.

It MUST NOT be used to prove any of:

```text
economic-domain separation
clean-domain inception
complete domain history
zero prior exposure
writer eligibility
readiness for new risk
```

The observer MUST NOT cancel or alter any preexisting order. If one exists, stop before CREATE.

### CANARY-MKT-005 — no concurrent user activity assumption

During the future canary interval, no other user process/device SHOULD intentionally place, cancel, amend, decrease, or replace an order in the selected ticker and exact accepted canary domain.

If observed order/fill evidence indicates concurrent user activity that cannot be uniquely separated from the canary, classify `CANARY_IDENTITY_AMBIGUOUS` or `CANARY_RECONCILIATION_UNRESOLVED` as applicable.

Concurrent activity MUST NOT trigger a different ticker, different subaccount, or primary-domain fallback.

## 13. Deterministic non-marketable price construction

### CANARY-PRICE-001 — exact arithmetic

All price-grid work uses exact decimal arithmetic.

Let:

```text
B = exact market.yes_bid_dollars
A = exact market.yes_ask_dollars
```

The observer MUST locate `B` within one exact returned `PriceRange` and derive grid points only from that range's exact decimal `start`, `end`, and `step`.

The canary price `P` is the fifth valid grid point strictly below `B` within the same price range.

Equivalently, when `B`, `start`, and `step` are all grid-aligned and no range boundary is crossed:

```text
P = B - 5 * step
```

The market is ineligible if five strictly lower valid grid points within that same range do not exist.

### CANARY-PRICE-002 — non-marketable and interior predicates

`P` is eligible only if:

```text
P > start
P < end
P < B
P < A
P > 0
P < 1
```

The strict interior tests intentionally avoid depending on unresolved endpoint-inclusivity semantics at exact price-range boundaries.

The observer MUST reject any binary floating-point round trip or lexical normalization that changes the exact decimal value.

### CANARY-PRICE-003 — final freshness before browser submission

Immediately before displaying the manual CREATE prompt, the observer MUST reacquire `GetMarket` and `GetMarketOrderbook` and recompute `P` from the fresh data.

If the recomputed price differs from the previously displayed plan, the observer MUST display the new exact price and require the user to use only the newly computed value.

The final market/book snapshot used for `P` MUST be no older than `10` seconds when the manual CREATE prompt opens.

---

## 14. Baseline evidence contract

### CANARY-BASELINE-001 — baseline sequence

Only after Section 9A succeeds, and before manual CREATE, the observer MUST capture, in this order:

```text
1. exact market snapshot
2. exact orderbook snapshot
3. complete selected-ticker order enumeration in the accepted canary domain
4. bounded recent selected-ticker fill enumeration in the accepted canary domain
5. selected-ticker position response in the accepted canary domain
6. final fresh market snapshot + orderbook snapshot used to calculate P
```

Every portfolio request MUST serialize the exact accepted subaccount explicitly.

### CANARY-BASELINE-002 — recent fill window

Baseline fills MUST be queried with:

```text
ticker = selected ticker
subaccount = canary_domain_identity.venue_subaccount
subaccount query parameter = EXPLICITLY_SERIALIZED
min_ts = floor(T_baseline_utc_seconds) - 900
max_ts = ceil(T_baseline_utc_seconds) + 1
limit = 1000
```

This 15-minute lookback is supporting canary-attribution evidence only. It is not the domain history-completeness proof required by Section 9A. Exact post-create fill attribution uses `order_id` once the canary order is bound.

### CANARY-BASELINE-003 — position state

The observer MUST retain the complete raw `GetPositionsResponse` for:

```text
ticker = selected ticker
subaccount = canary_domain_identity.venue_subaccount
subaccount query parameter = EXPLICITLY_SERIALIZED
limit = 1000
```

The normalized baseline market-position state is exactly one of:

```text
PRESENT_EXACTLY_ONCE
ABSENT_FROM_COMPLETE_RESPONSE
DUPLICATE_TICKER_ROWS
PAGINATION_INCOMPLETE
MALFORMED
READ_FAILED
```

A successful fill-reconciliation branch later requires an exact usable baseline/post position comparison. `ABSENT_FROM_COMPLETE_RESPONSE` MUST NOT be assigned numeric zero.

The baseline position response is canary reconciliation evidence, not proof of clean-domain inception.

## 15. Time model and manual action windows

### CANARY-TIME-001 — clock pair

Every observer phase boundary MUST record both:

```text
utc_rfc3339: timezone-aware UTC string
monotonic_ms_from_execution_start: nonnegative integer
```

UTC time is used for evidence and API timestamp-window construction. Monotonic time controls deadlines.

A local UTC clock regression does not reset deadlines. If wall-clock regression makes an API time window ambiguous, classify `CANARY_LOCAL_CLOCK_UNSAFE` before any new manual CREATE.

### CANARY-TIME-002 — named boundaries

The evidence summary MUST preserve at minimum:

```text
T0_baseline_started
T1_baseline_completed
T2_create_prompt_opened
T3_create_user_confirmed
T4_order_bound
T5_resting_confirmed
T6_cancel_prompt_opened
T7_cancel_user_confirmed_or_not_required
T8_terminal_observed
T9_evidence_finalized
```

Unused boundaries MUST be explicit `NOT_REACHED`, never fabricated timestamps.

### CANARY-TIME-003 — user action windows

The user manual CREATE window is at most `120000 ms` from `T2`.

The user manual CANCEL prompt window is at most `120000 ms` from `T6`.

The overall canary observation deadline is `900000 ms` from `T0` through terminal evidence finalization, excluding no time for process restart. A process restart terminates the run; it does not resume the one-create lifecycle automatically.

If the observer's evidence deadline expires after the manual order is created and that order is still visibly resting, the user may perform the one permitted manual cleanup cancellation of that exact canary order, but the expired observer run MUST NOT claim successful terminal API reconciliation.

---

## 16. Manual CREATE contract

### CANARY-CREATE-001 — exact browser order and exact domain

The browser order MUST be displayed and manually verified as exactly:

```text
Demo environment
exact account/subaccount corresponding to canary_domain_identity
selected ticker
direction = BUY YES
order type = LIMIT
quantity = 1.00 contracts
limit price = exact P from current observer prompt
```

The user MUST be able to distinguish the browser's target account/subaccount from the held primary domain whenever the accepted route is `ROUTE_CANARY_SEPARATE_DOMAIN_READY`.

If the browser cannot establish that the CREATE will be submitted in the exact accepted canary domain, stop before CREATE.

If the browser cannot represent exactly `1.00` contracts and the exact price `P`, stop. Do not round, approximate, scale, substitute, change ticker, or fall back to primary.

### CANARY-CREATE-002 — one-create budget

The manual CREATE budget exists only after the domain-readiness gate has succeeded.

It is charged when the user confirms that the browser submission action for the exact accepted canary domain was performed, regardless of whether the API observer later sees the order.

After that point:

```text
second CREATE = PROHIBITED
```

This remains true after:

```text
zero order observation
multiple candidate orders
read failure
process interruption
full fill
partial fill
cancel ambiguity
manual cleanup
```

No failure creates a right to retry in primary subaccount `0` or another domain.

### CANARY-CREATE-003 — observer behavior at create boundary

The observer MUST display an explicit state equivalent to:

```text
WAITING_FOR_USER_MANUAL_CREATE
```

only after Section 9A and all baseline/market gates succeed.

It MUST NOT construct, sign, or send POST/DELETE/PATCH/PUT traffic.

The observer records only that the user reports the browser CREATE action occurred in the prompted exact canary domain and the local action-window timing. It MUST NOT treat user confirmation as venue acceptance proof.

## 17. Candidate discovery and exact order binding

### CANARY-BIND-001 — post-create discovery query

After the user confirms manual CREATE, the observer MUST discover candidate orders only through:

```text
GET /portfolio/orders
```

with:

```text
ticker = selected ticker
subaccount = canary_domain_identity.venue_subaccount
subaccount query parameter = EXPLICITLY_SERIALIZED
min_ts = floor(T2_utc_seconds) - 2
max_ts = ceil(T3_utc_seconds) + 30
limit = 1000
```

The exact interval is deliberately buffered to tolerate integer-second query precision without relying on undocumented inclusive/exclusive endpoint semantics.

### CANARY-BIND-002 — scheduled observation polls, not retries

Candidate discovery may perform at most `6` scheduled poll rounds, separated by at least `2000 ms`, under a `20000 ms` phase deadline.

Each HTTP request itself has retry count `0`.

A scheduled poll is a new observation request with its own `poll_ordinal`; it is not a transport retry. A failed GET MUST NOT be retried under the same poll ordinal.

### CANARY-BIND-003 — candidate hard-match fields

A candidate order survives only if all source-required fields are valid and:

```text
order_id is a nonempty string
order_id was not present in the baseline order set
ticker == selected ticker
type == "limit"
outcome_side == "yes"
book_side == "bid"
initial_count_fp == "1.00"
yes_price_dollars == canonical exact P
status in {resting,canceled,executed}
```

If `subaccount_number` is present, it MUST equal `canary_domain_identity.venue_subaccount` exactly. Absence of this optional response field does not erase the domain provenance established by the explicitly scoped candidate-discovery request.

If `created_time` is present, it MUST parse as timezone-aware and fall within:

```text
[T2_utc - 2 seconds, T3_utc + 30 seconds]
```

If `exchange_index` is present, it MUST be a nonnegative integer and is frozen into the bound identity.

If `client_order_id` is nonempty, it is frozen as supporting identity evidence. An empty string is permitted because the source requires a string but the manual browser representation is not source-bound to a nonempty client ID.

### CANARY-BIND-004 — exact uniqueness theorem

Exactly one candidate MUST survive the hard-match set.

```text
0 candidates -> CANARY_ORDER_NOT_OBSERVED
>1 candidate -> CANARY_IDENTITY_AMBIGUOUS
1 candidate -> candidate order_id becomes bound_order_id
```

Once bound, `bound_order_id` is immutable for the remainder of the run.

No later fuzzy match may replace it.

### CANARY-BIND-005 — exact-order readback is mandatory

Candidate-list observation is not sufficient to prove resting.

The observer MUST call:

```text
GET /portfolio/orders/{bound_order_id}
```

and require the returned `order.order_id` to equal the exact bound ID and all immutable canary identity fields to remain consistent.

A `404`, malformed response, changed identity field, or mismatched order ID does not authorize rebinding.

---

## 18. Authoritative resting proof

### CANARY-REST-001 — success predicate

Authoritative resting proof exists only if an exact-order read returns:

```text
order_id == bound_order_id
status == "resting"
ticker == selected ticker
type == "limit"
outcome_side == "yes"
book_side == "bid"
initial_count_fp == "1.00"
yes_price_dollars == exact P
remaining_count_fp > "0.00"
fill_count_fp >= "0.00"
fill_count_fp < "1.00"
```

All count comparisons are exact decimal comparisons.

### CANARY-REST-002 — arithmetic invariant while resting

This specification deliberately adopts the following reconciliation invariant while the exact order is `resting`:

```text
fill_count_fp + remaining_count_fp == initial_count_fp
```

Failure class:

```text
CANARY_AUTHORITATIVE_RESPONSE_MALFORMED
```

This is an ARB specification invariant derived from the source field meanings; it is not a quoted source guarantee.

### CANARY-REST-003 — pre-rest fill/execute race

If the exact bound order is already `executed` before any exact-order `resting` read occurs, classify:

```text
CANARY_FILLED_BEFORE_RESTING_PROOF
```

This is positive execution evidence but it does not prove a resting-order state and therefore is not a successful resting/cancel canary.

No second order may be created.

### CANARY-REST-004 — partial fill while still resting

An exact `resting` order with:

```text
0.00 < fill_count_fp < 1.00
remaining_count_fp > 0.00
```

still proves a resting state. The same order may proceed to manual cancellation of only its remainder.

---

## 19. Manual cancellation target and cleanup safety

### CANARY-CANCEL-001 — exact API target before normal cancel step

The normal experiment cancel step may open only after all are true:

```text
Section 9A domain-readiness gate succeeded for this execution
bound_order_id exists
exact-order resting proof exists
the bound order remains in the exact accepted canary domain
```

The API identity remains the exact `bound_order_id`.

No cancellation capability exists merely because the held primary domain contains a visible order.

### CANARY-CANCEL-002 — browser target correspondence

The user may cancel only the single visible browser order corresponding to the bound canary in the exact accepted canary domain.

The browser row/order details MUST exactly match all browser-visible canary attributes available at that time, including at minimum:

```text
exact account/subaccount/domain selection where exposed
selected ticker
BUY YES direction
LIMIT type
exact limit price P
remaining quantity consistent with the bound exact-order observation
```

If the browser exposes the venue `order_id`, it MUST equal `bound_order_id`.

If the browser does not expose venue `order_id`, manual cancellation may proceed only if there is exactly one visible order matching all available exact canary attributes **inside the already accepted exact canary domain** and the baseline contained no preexisting resting order in that market/domain. Any competing visible match or domain ambiguity makes the target ambiguous and the canary MUST NOT claim exact manual-cancel attribution.

No ticker-only, price-only, approximate-time, or default-primary target selection is permitted.

### CANARY-CANCEL-003 — no cancel-all and no programmatic cancel

The future canary MUST NOT use:

```text
cancel-all
batch cancel
DELETE /portfolio/events/orders/{order_id}
any other programmatic write endpoint
```

The user's browser cancellation does not empirically validate `CancelOrderV2` transport or response semantics.

### CANARY-CANCEL-004 — manual cleanup after observation halt

Cleanup is a continuation of the one already-entered, domain-ready canary lifecycle. It is not an independent permission to write.

After the one manual CREATE has occurred in the exact accepted canary domain, if the observer later halts before authoritative cancellation proof and the user can still identify the exact visible canary order and exact domain without ambiguity, the same one manual browser CANCEL may be used as cleanup.

Such cleanup does not convert the terminal class to a canary success unless the required GET-only terminal reconciliation is completed inside its allowed observation envelope.

If the order is already executed, no cancel is required and none should be attempted.

If domain identity becomes ambiguous, the observer MUST NOT redirect cleanup to primary subaccount `0`, another ticker, or another local namespace. The terminal state remains unresolved and the evidence must preserve that uncertainty.

## 20. Fill-race semantics

### CANARY-FILL-001 — no second order after a fill

Any fill associated with `bound_order_id`, partial or complete, consumes the canary economically. No second CREATE is allowed.

### CANARY-FILL-002 — exact fill binding

Once `bound_order_id` exists, canary fills MUST be queried using:

```text
GET /portfolio/fills
order_id = bound_order_id
ticker = selected ticker
subaccount = canary_domain_identity.venue_subaccount
subaccount query parameter = EXPLICITLY_SERIALIZED
limit = 1000
```

Only fills whose exact `fill.order_id == bound_order_id` are canary fills.

### CANARY-FILL-003 — duplicate/conflicting fill identity

`fill_id` is the external fill identity for this canary.

Exact duplicate `fill_id` records with identical authoritative fields contribute once.

The same `fill_id` with any conflicting authoritative field is:

```text
CANARY_RECONCILIATION_UNRESOLVED
```

### CANARY-FILL-004 — fill quantity and fee reconciliation

For complete exact-order fill pagination, the observer MUST require:

```text
sum(fill.count_fp for unique bound fills) == final_order.fill_count_fp

sum(fill.fee_cost for unique bound fills)
    == final_order.maker_fees_dollars + final_order.taker_fees_dollars
```

All arithmetic is exact Decimal/fixed-point arithmetic.

If authoritative resting proof existed before a later fill, a canary fill with `is_taker == true` is inconsistent with the intended post-rest passive lifecycle and yields:

```text
CANARY_RECONCILIATION_UNRESOLVED
```

The raw evidence is still retained.

### CANARY-FILL-005 — post-cancel remaining quantity is intentionally not pre-assumed

The supplied OpenAPI defines `remaining_count_fp` as the remaining contracts for an order but does not specify the exact representation of canceled remainder after cancellation.

Therefore this specification MUST NOT require a particular post-cancel value such as `0.00` or the unfilled canceled quantity.

For `status == "canceled"` the observer MUST record:

```text
initial_count_fp
fill_count_fp
remaining_count_fp
```

exactly as returned and MUST identify the observed relation in evidence.

This canary is partly intended to establish that real representation empirically.

No successful classification may depend on an unsupported preselected post-cancel remainder convention.

---

## 21. Post-cancel / terminal authoritative reads

### CANARY-TERM-001 — terminal exact-order polling

After the user confirms browser CANCEL, the observer performs exact-order GET observations only:

```text
GET /portfolio/orders/{bound_order_id}
```

with at most `6` scheduled poll rounds, at least `2000 ms` apart, under a `20000 ms` terminal-order phase deadline.

Each request retry count is `0`.

Terminal exact-order status is:

```text
canceled
or
executed
```

`resting` after the terminal-order phase deadline is unresolved, not cancellation proof.

### CANARY-TERM-002 — terminal fill enumeration

After terminal order observation, enumerate complete bound-order fills under Section 20.

### CANARY-TERM-003 — terminal position observation

After terminal fill enumeration, obtain complete position observation for:

```text
ticker = selected ticker
subaccount = canary_domain_identity.venue_subaccount
subaccount query parameter = EXPLICITLY_SERIALIZED
limit = 1000
```

The raw response is always retained when obtained.

### CANARY-TERM-004 — position reconciliation

For a branch with one or more bound fills, successful full reconciliation requires exactly one usable baseline market-position state and exactly one usable terminal market-position state that permit an exact delta comparison.

For the fixed `BUY YES` canary:

```text
terminal.position_fp - baseline.position_fp
    == sum(unique bound fill.count_fp)

terminal.fees_paid_dollars - baseline.fees_paid_dollars
    == sum(unique bound fill.fee_cost)
```

If either required position row is `ABSENT_FROM_COMPLETE_RESPONSE`, the observer MUST NOT assume zero and the fill branch becomes:

```text
CANARY_RECONCILIATION_UNRESOLVED
```

The positive order/fill evidence remains preserved inside that unresolved terminal package.

For a zero-fill cancellation branch, position reconciliation succeeds only in one of two forms:

```text
A. baseline and terminal each contain exactly one market row and these economic fields are unchanged:
   position_fp
   total_traded_dollars
   market_exposure_dollars
   realized_pnl_dollars
   fees_paid_dollars

B. baseline and terminal both completely omit the market row, recorded as:
   NO_POSITION_ROW_OBSERVED_BOTH_SNAPSHOTS
```

Case B is absence corroboration only and MUST NOT be relabeled as numeric zero exposure. If exactly one snapshot contains a row, if duplicate rows exist, or if any economic field changes despite zero bound fills, classify `CANARY_RECONCILIATION_UNRESOLVED`.

---

## 22. Pagination contract

### CANARY-PAGE-001 — complete pagination required

For `GetOrders`, `GetFills`, and `GetPositions`, every collection used for a proof MUST be paginated until the response cursor is empty or the operation-specific page cap is reached.

Page size is exactly:

```text
limit = 1000
```

### CANARY-PAGE-002 — page caps

Maximum pages per logical collection are:

```text
baseline orders = 4
baseline recent fills = 4
baseline positions = 4
one candidate-discovery poll round = 2
bound-order fills = 4
terminal positions = 4
```

A nonempty cursor after the cap means:

```text
CANARY_PAGINATION_INCOMPLETE
```

No proof depending on that collection may be claimed.

### CANARY-PAGE-003 — cursor integrity

A repeated nonempty cursor value, cursor cycle, malformed cursor type, or page whose identity cannot be associated with the exact request series is malformed/unresolved and terminates that logical collection.

---

## 23. Network, deadline, retry, and redirect contract for the future observer

### CANARY-NET-001 — HTTP method allowlist

The observer transport MUST have an exact allowlist containing only:

```text
GET
```

No generic caller may supply an arbitrary method string.

### CANARY-NET-002 — redirects

Redirect following is prohibited.

```text
redirect_count = 0
```

Any `3xx` response is terminal `CANARY_READ_FAILURE` for that request series.

### CANARY-NET-003 — transport retry

Automatic transport retries are prohibited.

```text
retry_count_per_request = 0
```

Scheduled state polls defined by this specification are not retries and MUST be separately identified by phase and poll ordinal.

### CANARY-NET-004 — per-request deadline

Each GET has one monotonic caller-visible deadline of:

```text
10000 ms
```

The deadline begins before DNS/socket/TLS/request work for that GET and ends only when the response is completely received, schema-validated, and converted to the request's terminal result.

No parse-stage deadline reset is permitted.

### CANARY-NET-005 — response cap

The observer MUST cap each retained HTTP response body at:

```text
2,000,000 bytes
```

A body exceeding the cap is not partially accepted as authoritative JSON.

### CANARY-NET-006 — global request budget

The entire real canary may issue at most:

```text
48 programmatic GET requests
```

The request budget includes public market reads, authenticated reads, pagination, and scheduled polls.

The browser CREATE/CANCEL actions are not HTTP requests issued by the observer and are counted separately as manual actions.

Budget exhaustion is terminal:

```text
CANARY_READ_BUDGET_EXHAUSTED
```

No additional programmatic GET is sent after exhaustion.

---

## 24. HTTP response validation

### CANARY-HTTP-001 — success requirements

A GET response is authoritative only when all are true:

```text
HTTP status == 200
Content-Type normalizes to application/json
body <= 2,000,000 bytes
JSON parses without duplicate-key ambiguity
all required top-level fields exist with exact source types
all consumed nested required fields exist with exact source types
no disallowed NaN/Infinity numeric tokens
```

### CANARY-HTTP-002 — error status handling

Any non-200 response is a read failure for that request. It MUST NOT be parsed as a successful operation payload.

A `404` from exact `GetOrder` after binding does not prove the canary order never existed and does not authorize another CREATE.

### CANARY-HTTP-003 — source-required cursor fields

`GetOrdersResponse` and `GetFillsResponse` require `cursor` as a string.

`GetPositionsResponse.cursor` is optional. Missing `cursor` is treated as terminal pagination only if the response otherwise conforms and there is no conflicting page evidence; it MUST NOT be fabricated as an empty string in raw evidence.

---

## 25. Closed terminal classification set

Every future execution MUST end with exactly one `terminal_class` from this closed set:

```text
CANARY_EXECUTION_DOMAIN_NOT_READY
CANARY_PASS_RESTING_THEN_CANCELED_NO_FILL
CANARY_PASS_RESTING_PARTIAL_FILL_THEN_CANCELED
CANARY_POSITIVE_RESTING_THEN_FILLED_BEFORE_CANCEL_TERMINALIZATION
CANARY_FILLED_BEFORE_RESTING_PROOF
CANARY_ORDER_NOT_OBSERVED
CANARY_IDENTITY_AMBIGUOUS
CANARY_CANCEL_TERMINAL_STATE_UNRESOLVED
CANARY_RECONCILIATION_UNRESOLVED
CANARY_MARKET_INELIGIBLE
CANARY_PAGINATION_INCOMPLETE
CANARY_AUTHORITATIVE_RESPONSE_MALFORMED
CANARY_READ_FAILURE
CANARY_READ_BUDGET_EXHAUSTED
CANARY_SOURCE_DRIFT
CANARY_LOCAL_CLOCK_UNSAFE
CANARY_MANUAL_ACTION_WINDOW_EXPIRED
CANARY_CAPABILITY_OR_SCOPE_VIOLATION
```

`CANARY_EXECUTION_DOMAIN_NOT_READY` is required whenever Section 9A cannot positively validate the exact accepted readiness artifact and canary domain before all venue activity. It requires:

```text
request_count = 0
manual_create_count = 0
manual_cancel_count = 0
```

### CANARY-CLASS-001 — no-fill pass

`CANARY_PASS_RESTING_THEN_CANCELED_NO_FILL` requires:

```text
one accepted exact canary_domain_identity
one bound exact order_id
at least one exact-order status == resting observation
manual browser CANCEL reported for the corresponding exact visible order in that domain
terminal exact-order status == canceled
complete bound-order fill enumeration
zero unique bound fills
final_order.fill_count_fp == "0.00"
fee sum == "0" exactly
position reconciliation satisfies zero-fill Section-21 rules
no source/domain/capability/read/pagination violation
```

It does not assume any specific post-cancel `remaining_count_fp` value.

### CANARY-CLASS-002 — partial-fill then canceled pass

`CANARY_PASS_RESTING_PARTIAL_FILL_THEN_CANCELED` requires:

```text
one accepted exact canary_domain_identity
one bound exact order_id
exact resting proof occurred
0.00 < final_order.fill_count_fp < 1.00
manual browser CANCEL reported in that exact domain
terminal exact-order status == canceled
complete exact bound-order fills
fill quantity == final order fill_count_fp
fill fees == final order maker_fees + taker_fees
successful exact baseline-to-terminal position reconciliation
all post-rest fills are is_taker == false
no source/domain/capability/read/pagination violation
```

It does not assume a particular canceled remainder representation.

### CANARY-CLASS-003 — resting then filled before cancel terminalization

If exact resting proof occurred but the order reaches `executed` before a `canceled` terminal state is observed, classify:

```text
CANARY_POSITIVE_RESTING_THEN_FILLED_BEFORE_CANCEL_TERMINALIZATION
```

This class requires complete fill/fee/position reconciliation to be considered fully reconciled positive evidence.

It is not evidence of browser cancellation behavior because the terminal order state is executed rather than canceled.

### CANARY-CLASS-004 — filled before resting proof

If the order reaches `executed` without any authoritative exact-order `resting` observation, classify:

```text
CANARY_FILLED_BEFORE_RESTING_PROOF
```

Preserve exact order/fill/position evidence if available. Do not create another order.

### CANARY-CLASS-005 — precedence

Failure/uncertainty precedence is:

```text
EXECUTION_DOMAIN_NOT_READY
    > CAPABILITY_OR_SCOPE_VIOLATION
    > SOURCE_DRIFT
    > LOCAL_CLOCK_UNSAFE
    > AUTHORITATIVE_RESPONSE_MALFORMED
    > PAGINATION_INCOMPLETE / READ_BUDGET_EXHAUSTED / READ_FAILURE
    > IDENTITY_AMBIGUOUS
    > ORDER_NOT_OBSERVED
    > CANCEL_TERMINAL_STATE_UNRESOLVED
    > RECONCILIATION_UNRESOLVED
    > positive terminal classes
```

When more than one symptom occurs, the highest-precedence material class controls `terminal_class`; all secondary findings remain in `secondary_findings[]`.

## 26. Exact evidence package contract

### CANARY-EVID-001 — evidence directory

A later execution MUST produce one local evidence directory containing at least:

```text
CANARY_EVIDENCE_MANIFEST.json
CANARY_SUMMARY.json
MANUAL_ACTION_JOURNAL.json
```

and one raw-response file for every GET that returned bytes.

Raw response filenames MUST begin with a monotonically increasing request ordinal, for example:

```text
0001_get_market.json
0002_get_market_orderbook.json
0003_get_orders_page_01.json
...
```

If the terminal class is `CANARY_EXECUTION_DOMAIN_NOT_READY`, no venue raw-response file may exist because `request_count` is exactly zero.

### CANARY-EVID-002 — raw response immutability and identity

For each present raw response, the manifest records:

```text
request_ordinal: integer >= 1
phase: closed enum string
method: exactly GET
path_and_sanitized_query: string with no auth material
started_utc: RFC3339 UTC
completed_utc: RFC3339 UTC
monotonic_start_ms: integer
monotonic_end_ms: integer
http_status: integer or null
content_type: string or null
raw_body_bytes: integer or null
raw_body_sha256: lowercase 64-hex or null
response_file: relative filename or null
poll_ordinal: integer or null
retry_count: exactly 0
redirect_count: exactly 0
result: closed request-result enum
```

Every portfolio request record MUST show the explicitly serialized bound `subaccount` value in sanitized query evidence.

Authentication headers, signatures, private-key bytes, and API key values MUST NOT be persisted.

### CANARY-EVID-003 — absent/not-required evidence

The manifest state for a logical evidence item is exactly one of:

```text
PRESENT
NOT_REQUIRED_BY_TERMINAL_BRANCH
NOT_OBTAINED_DUE_TO_HALT
```

`NOT_REQUIRED_BY_TERMINAL_BRANCH` MUST NOT be represented by an invented empty raw response file.

`NOT_OBTAINED_DUE_TO_HALT` MUST retain the halt reason.

### CANARY-EVID-004 — normalized summary schema

Because Correction 01 changes the execution-domain identity contract, the future normalized summary schema is explicitly revised:

```text
schema_id = KALSHI_DEMO_MANUAL_RESTING_CANCEL_CANARY_SUMMARY_V2
schema_revision = 2
```

`CANARY_SUMMARY.json` MUST contain at least:

```text
execution_id: string
environment = KALSHI_DEMO
account_scope_ref: string
subaccount: integer
conflict_domain_ref: string
readiness_route: ROUTE_CANARY_PRIMARY_READY|ROUTE_CANARY_SEPARATE_DOMAIN_READY
domain_readiness_evidence_artifact: string
domain_readiness_evidence_bytes: integer
domain_readiness_evidence_sha256: lowercase 64-hex
domain_readiness_review_identity: string
ticker: string
source_binding_sha256 = bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8
quantity_fp = "1.00"
planned_price_dollars: string or null
bound_order_id: string or null
bound_client_order_id: string or null
bound_exchange_index: integer or null
resting_proof_observed: boolean
manual_create_performed: boolean
manual_cancel_performed: boolean
manual_cancel_not_required_reason: string or null
terminal_order_status: resting|canceled|executed|null
post_cancel_remaining_count_fp_observed: string|null
bound_fill_count: integer
bound_fill_quantity_fp: string|null
bound_fill_fee_dollars: string|null
baseline_position_state: closed enum
terminal_position_state: closed enum
position_delta_fp: string|null
position_fee_delta_dollars: string|null
terminal_class: closed Section-25 enum
secondary_findings: array<string>
request_count: integer
retry_count: exactly 0
redirect_count: exactly 0
programmatic_write_count: exactly 0
manual_create_count: 0 or 1
manual_cancel_count: 0 or 1
production_request_count: exactly 0
websocket_count: exactly 0
persistent_arb_state_mutation: false
secrets_persisted: false
```

The `subaccount` field MUST equal `canary_domain_identity.venue_subaccount`; it is not fixed to `0`.

A `null` value is used only where the schema explicitly permits null. Unknown economic state MUST NOT be replaced with numeric zero.

### CANARY-EVID-005 — manual action journal

`MANUAL_ACTION_JOURNAL.json` records user-reported manual boundaries only:

```text
create_prompt_opened
create_user_confirmed
cancel_prompt_opened or NOT_REACHED
cancel_user_confirmed or NOT_REQUIRED/NOT_REACHED
```

Each reached manual-action journal entry MUST also bind the exact `conflict_domain_ref` and `subaccount` displayed/promoted by the observer for that action.

It MUST NOT claim that the venue accepted a manual action merely because the user clicked a browser control.

Optional screenshots may be retained separately for human corroboration only if they contain no secret material. Screenshot evidence is not required for the API proof.

## 27. Secret handling contract for a future observer

### CANARY-SEC-001 — credential sources

The only credential sources are:

```text
KALSHI_DEMO_API_KEY_ID
KALSHI_DEMO_PRIVATE_KEY_PATH
```

The private key path MUST be resolved as a local file and the key bytes MUST remain process-local.

### CANARY-SEC-002 — no secret persistence

The observer MUST NOT persist:

```text
API key ID value
private-key path unless redacted to a non-sensitive source label
private-key bytes
PEM contents
signature bytes/text
KALSHI-ACCESS-KEY header value
KALSHI-ACCESS-SIGNATURE header value
KALSHI-ACCESS-TIMESTAMP if captured as part of a signed-header dump
raw environment dump
```

Request evidence may record only a fixed boolean or enum that authenticated signing occurred, never the auth material.

### CANARY-SEC-003 — credential lifetime

Credential use begins only after all non-secret execution inputs, environment, exact host, capability envelope, and task-current source binding are validated.

A public `GetMarket` request MUST NOT require credential loading.

---

## 28. Gate-D, historical-state, and domain separation

### CANARY-SEP-001 — no Gate-D readiness inference

A successful canary MUST NOT establish:

```text
Gate-D execution readiness
NORMAL_WRITER acquisition
CurrentProcessReleaseCompletionV1
writer-proof release
risk state WRITER_ELIGIBLE
zero durable unresolved writes
clean-domain inception
persistent clean-domain bootstrap
```

Domain readiness is a prerequisite to the canary, not an output inferred from canary success.

### CANARY-SEP-002 — no historical-incident action

The canary MUST NOT search for or manufacture a cancellation target for the historical unresolved CREATE.

Any future manual canary order is a new canary observation object in an already accepted domain only. It MUST NOT be persisted as a surrogate resolution of the historical incident.

### CANARY-SEP-003 — no alternate-domain bypass

This specification does not define a concrete alternate domain.

The canary MUST NOT define or infer an alternate domain merely to make an execution possible. In particular, none of these is separation:

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

A concrete alternate `account_scope_ref`, `venue_subaccount`, or `conflict_domain_ref` may enter the canary only through an exact accepted readiness artifact satisfying Section 9A.

The following fallback is always prohibited:

```text
fallback_to_primary_subaccount_0 = PROHIBITED
```

### CANARY-SEP-004 — no programmatic write validation claim

A successful browser CREATE/cancel lifecycle MUST NOT be cited as empirical proof of:

```text
CreateOrderV2 POST transport
CancelOrderV2 DELETE transport
programmatic signing correctness for writes
write idempotency semantics
write retry semantics
ordinary writer permit lifecycle
```

### CANARY-SEP-005 — canary baseline is not substrate proof

Zero selected-ticker resting orders, zero recent selected-ticker fills, or absent selected-ticker positions observed by the canary MUST NOT be promoted to:

```text
clean domain
complete history
zero prior exposure
safe primary domain
writer eligible
```

Those are canary-local attribution/reconciliation observations only.

## 29. What this canary may prove

If a future execution first enters through a valid Section-9A readiness artifact and terminal evidence satisfies a positive class, the canary may establish only the exact facts actually observed, such as:

```text
the execution used one exact pre-accepted canary domain identity
one manual Demo limit order was observable through GET as exact order_id X
that exact order was authoritatively observed with status resting
that exact order later had status canceled after the browser cancel action
or that the exact order executed during the race
exact bound-order fills were observable
exact order/fill fee fields reconciled under the specified invariants
position consequences were or were not reconcilable under the explicit position rules
the current GET representations matched the bound source contract
```

The canary does not independently prove the substrate theorem that opened its gate. In particular, canary success does not transform its baseline observations into clean-domain inception, complete history, writer release, or Gate-D readiness.

It does not prove:

```text
production behavior
production liquidity
profitability
queue priority
market-maker realized PnL
arbitrage
programmatic write behavior
historical incident closure
Gate-D execution-substrate validity
clean-domain inception beyond the separately accepted readiness artifact
```

## 30. Future implementation test/evidence requirements

A later implementation MUST be reviewable as:

```text
SPEC REQUIREMENT -> CODE LOCATION -> TEST/EVIDENCE -> STATUS
```

At minimum, offline tests MUST cover the following without real venue access or real secrets.

### CANARY-TEST-000 — execution-domain readiness gate

Prove:

- absent readiness artifact -> `CANARY_EXECUTION_DOMAIN_NOT_READY`, request count `0`, manual actions `0`;
- malformed or bytes/SHA-mismatched readiness artifact -> same fail-closed result;
- readiness route outside the exact two-value set is rejected;
- `account_scope_ref`, `venue_subaccount`, or `conflict_domain_ref` mismatch is rejected before credential use/network;
- same account/subaccount + different ticker remains the same conflict domain;
- new process/database/ledger/authority/namespace/strategy/restart cannot satisfy domain separation;
- manual browser transport cannot satisfy domain separation;
- explicit subaccount query serialization is required for every portfolio request;
- omitted subaccount is rejected even though the current source defines a primary-account default;
- failed separate-domain readiness cannot fall back to primary subaccount `0`;
- a synthetic fully valid primary-ready record and a synthetic fully valid separate-domain-ready record can each open only their exact bound domain.

### CANARY-TEST-001 — source and operation binding

Prove:

- exact OpenAPI source identity accepted;
- changed bytes/hash rejected;
- each of six GET operation bindings matches Appendix A;
- exact canonical operation-binding bytes `2672` and SHA-256 `bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8`;
- write operation substitution rejected;
- production host rejected;
- alternate Demo host fallback rejected;
- source drift classification deterministic.

### CANARY-TEST-002 — fixed-point and schema validation

Prove:

- `FixedPointCount` exact string parsing;
- `FixedPointDollars` exact string parsing;
- binary float rejection;
- malformed required Order/Fill/Position fields rejected;
- unknown order status rejected;
- empty `client_order_id` accepted as a source-valid string;
- optional `created_time` absent does not falsely become malformed;
- malformed optional field is rejected if consumed.

### CANARY-TEST-003 — price-grid selection

Prove:

- normal one-cent range selects fifth lower grid point exactly;
- piecewise/range-boundary case fails closed rather than crossing a range;
- fewer than five lower interior points fails market eligibility;
- crossed/one-sided/zero-size book fails;
- stale market/book pair fails;
- price calculation does not use float.

### CANARY-TEST-004 — baseline canary-attribution cleanliness

Prove:

- zero preexisting resting orders in the selected ticker/domain passes this local attribution predicate;
- one preexisting resting order blocks before CREATE;
- zero orders does not imply clean-domain inception, complete history, or domain readiness;
- pagination completes deterministically;
- cursor cycle and page-cap exhaustion halt;
- absent position row stays `ABSENT_FROM_COMPLETE_RESPONSE`, not zero;
- all portfolio baseline queries carry the exact bound subaccount explicitly.

### CANARY-TEST-005 — one-create state machine

Prove:

- CREATE state is unreachable before domain readiness succeeds;
- exactly one manual CREATE transition is representable after readiness;
- browser domain ambiguity blocks before CREATE;
- zero candidate after CREATE does not reopen create capability;
- multiple candidates do not reopen create capability;
- read failure does not reopen create capability;
- process restart cannot resume a preexisting run and create again;
- no failure can redirect a second CREATE to primary or another domain.

### CANARY-TEST-006 — exact identity binding

Prove:

- baseline order cannot bind;
- one exact new match binds once;
- zero matches -> `CANARY_ORDER_NOT_OBSERVED`;
- multiple matches -> `CANARY_IDENTITY_AMBIGUOUS`;
- order ID mismatch on exact readback rejects;
- later fields cannot rebind to another order ID;
- nonempty `client_order_id` is corroborating only, not mandatory;
- candidate order evidence outside the accepted canary domain cannot bind.

### CANARY-TEST-007 — resting proof

Prove:

- exact `resting`, 0 fill, 1.00 remaining passes resting proof;
- partial fill + positive remaining can pass resting proof if arithmetic invariant holds;
- executed before exact resting observation -> `CANARY_FILLED_BEFORE_RESTING_PROOF`;
- invalid fill+remaining arithmetic -> malformed.

### CANARY-TEST-008 — browser cancellation boundary

Prove:

- observer cannot emit DELETE/POST/PATCH/PUT;
- no cancel-all path exists;
- cancel prompt cannot open before accepted domain + bound exact order + resting proof;
- ambiguous browser domain or order correspondence cannot be claimed as exact cancel proof;
- cleanup cancel is impossible if CREATE never occurred under a valid domain gate;
- cleanup cancel does not turn failed observation into pass without GET reconciliation;
- cleanup never falls back to primary or another domain.

### CANARY-TEST-009 — terminal cancellation representation

Prove at least two valid canceled fixtures with different `remaining_count_fp` representations can be preserved without an invented fixed post-cancel remainder rule, provided all other bound evidence is valid.

This test is mandatory because the supplied OpenAPI does not define canceled-remainder representation.

### CANARY-TEST-010 — fill and fee reconciliation

Prove:

- duplicate identical fill contributes once;
- conflicting duplicate fill ID becomes unresolved;
- sum fill quantity equals final order fill count;
- sum fill fee equals maker+taker order fees;
- post-rest `is_taker=true` becomes reconciliation unresolved;
- full fill and partial fill branches are distinguished;
- fill requests carry the exact bound subaccount explicitly.

### CANARY-TEST-011 — position reconciliation

Prove:

- exact YES position delta equals fill quantity;
- fee delta equals fill fee;
- missing baseline or terminal row on a filled branch remains unresolved, never zero;
- zero-fill branch records absent/absent as `NO_POSITION_ROW_OBSERVED_BOTH_SNAPSHOTS`, not zero exposure;
- position requests carry the exact bound subaccount explicitly.

### CANARY-TEST-012 — deadlines/retries/redirects/budgets

Prove:

- per-request deadline includes parsing and terminal construction;
- no automatic request retry;
- scheduled poll ordinals remain distinct from retries;
- redirect rejected;
- global request budget enforced at 48;
- manual action window expiry deterministic;
- clock regression does not reset deadlines;
- readiness failure consumes no venue request budget because it occurs before network.

### CANARY-TEST-013 — evidence and secret safety

Prove:

- every raw response manifest entry gets exact byte length and SHA-256;
- `NOT_REQUIRED_BY_TERMINAL_BRANCH` creates no fabricated raw file;
- auth headers/signatures/private key/API key value absent from evidence;
- summary V2 binds exact account scope, subaccount, conflict domain, readiness evidence and readiness review identity;
- summary null/unknown handling follows schema;
- production requests, WebSocket, programmatic writes, and persistent-state mutation all remain zero/false in offline fixtures.

## 31. Requirement traceability matrix and Correction-01 block closure

### CANARY-TRACE-001 — requirement-to-implementation evidence map

| Requirement group | Implementation surface | Required evidence |
|---|---|---|
| CANARY-BASE-* | startup/provenance gate | exact repository/source/predecessor identity tests |
| CANARY-DOMAIN-* | pre-network domain-readiness gate | exact readiness identity, two-route, no-fallback, pseudo-separation tests |
| CANARY-SRC-* | source-binding validator | canonical binding hash + drift tests |
| CANARY-SCHEMA-* | response parser/canonicalizer | schema/Decimal tests |
| CANARY-MKT-* | market gate | market/book eligibility + attribution-cleanliness fixtures |
| CANARY-PRICE-* | price-grid calculator | exact grid tests |
| CANARY-BASELINE-* | baseline collector | explicit-subaccount pagination/isolation/position tests |
| CANARY-TIME-* | run state/deadline model | fake-clock tests |
| CANARY-CREATE-* | manual action state machine | domain-gated one-create transition tests |
| CANARY-BIND-* | candidate binder | zero/one/many exact identity tests |
| CANARY-REST-* | exact-order proof | resting/race fixtures |
| CANARY-CANCEL-* | manual cancel gate | exact-domain/no-write/correspondence tests |
| CANARY-FILL-* | fill reconciliation | dedupe/quantity/fee tests |
| CANARY-TERM-* | terminal collector/reconciler | cancel/fill/position tests |
| CANARY-PAGE-* | paginator | cursor/page-cap tests |
| CANARY-NET-* | transport envelope | method/deadline/retry/redirect/budget tests |
| CANARY-HTTP-* | response validator | status/media/schema tests |
| CANARY-CLASS-* | terminal classifier | domain-not-ready + one-class/precedence tests |
| CANARY-EVID-* | evidence writer | V2 domain binding + byte/hash/absence/secret tests |
| CANARY-SEC-* | credential loader/signing boundary | secret lifecycle tests |
| CANARY-SEP-* | integration boundary | no persistence/Gate-D/historical/pseudo-domain mutation tests |

### CANARY-TRACE-002 — explicit block-finding closure map

| Block finding | Blocked spec location | Correction-01 location | Status |
|---|---|---|---|
| Fixed future execution input to primary `subaccount = 0` | Section 11; portfolio query snippets in Sections 12, 14, 17, 20, 21 | Sections 9A, 11, 12, 14, 17, 20, 21 | `CLOSED_IN_CORRECTION_01` — exact subaccount comes only from accepted `canary_domain_identity` and is explicitly serialized |
| Manual browser CREATE could introduce new risk in the held primary conflict domain | Sections 9 and 16 | Sections 1, 9, 9A, 16, 28 | `CLOSED_IN_CORRECTION_01` — no browser action exists until an exact readiness route is proven |
| Zero preexisting selected-market orders could be read as practical economic isolation | Section 12 `CANARY-MKT-004` | Sections 9A and 12 `CANARY-MKT-004` | `CLOSED_IN_CORRECTION_01` — baseline zero is attribution cleanliness only, never domain/history/readiness proof |
| Summary/evidence schema implied primary subaccount `0` | Section 26 `CANARY-EVID-004` | Section 26 `CANARY-EVID-004`, Summary V2 | `CLOSED_IN_CORRECTION_01` — account scope, exact subaccount, conflict domain and readiness identities are required fields |
| Cleanup/terminal language could be interpreted as permitting a write in held primary | Sections 19 and 25 | Sections 19, 25, 28 | `CLOSED_IN_CORRECTION_01` — cleanup exists only after a valid domain-gated CREATE and never falls back to primary |
| Candidate lacked an exact current canary readiness disposition | Sections 2/28 by implication only | YAML; Sections 1, 2 `CANARY-BASE-005`, 9A `CANARY-DOMAIN-001` | `CLOSED_IN_CORRECTION_01` — `NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN`, `CANARY_REAL_EXECUTION_ELIGIBLE=false` |

This map is correction traceability metadata. It does not itself authorize any implementation or venue capability.

### CANARY-TRACE-003 — Correction-02 source-binding identity closure map

| MARCO BLOCK FINDING | CORRECTION-01 LOCATION | CORRECTION-02 LOCATION | STATUS |
|---|---|---|---|
| Appendix binding label `CANARY_OPENAPI_OPERATION_BINDING_REV1` is stale while `binding_schema_revision = 2` | Appendix A heading | Appendix A heading | `CLOSED_IN_CORRECTION_02` — label is exactly `CANARY_OPENAPI_OPERATION_BINDING_REV2` |
| Appendix terminal canonical JSON `bytes = 2528` conflicts with the independently verified 2672-byte canonical record | Appendix A terminal Identity block | Appendix A terminal Identity block | `CLOSED_IN_CORRECTION_02` — bytes are exactly `2672`; SHA-256 remains `bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8` |

Mechanical artifact-identity updates only: document title/correction class, immediate-predecessor identity, Correction-02 self-reference/stop lineage, and subordinate handoff identity. No other technical-contract text is changed by Correction 02.

## 32. Explicit unresolved issues

The following facts are intentionally unresolved by the supplied materials and therefore are not invented:

### UNRESOLVED-001 — canceled remainder representation

The supplied OpenAPI does not define whether a canceled order's `remaining_count_fp` is zeroed, retained as canceled-unfilled quantity, or represented another valid way. The canary records this empirically and does not pre-assume it.

### UNRESOLVED-002 — browser UI venue-order-id visibility

The supplied API source does not establish which exact order fields the browser UI displays. The manual target rule therefore requires exact correspondence across all available browser-visible fields, and exact `order_id` equality if the browser exposes it.

### UNRESOLVED-003 — position-row absence semantics

The supplied OpenAPI does not establish that absence of a `MarketPosition` row means numeric zero. The specification preserves absence explicitly and refuses zero inference.

### UNRESOLVED-004 — future source freshness

The supplied OpenAPI is task-current for this specification only. A later real execution must separately establish current source compatibility.

### UNRESOLVED-005 — concrete future canary domain

No exact future canary `account_scope_ref`, alternate venue subaccount, conflict-domain reference, domain-inception evidence, clean-domain persistence binding, or accepted readiness-review identity is established by the current inputs.

This is not filled by assumption. The exact current disposition remains:

```text
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

These unresolved points do not authorize a broader correction or an execution attempt. They are handled conservatively by the current closed gates.

## 33. Completion criteria for this specification

This Correction 02 is complete only if all of the following remain true:

1. canonical `main`, tree, and parent are exact and verified;
2. exact blocked predecessor identities are preserved as blocked lineage;
3. Gate-D remains `NOT_GATE_D_EXECUTION_READY` with `NO_CURRENTLY_VALID_EXECUTION_SUBSTRATE_PATH`;
4. the historical primary incident remains `HELD`, `UNKNOWN_UNBOUNDED`, and writer-ineligible;
5. `CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN`;
6. `CANARY_REAL_EXECUTION_ELIGIBLE = false`;
7. no concrete safe canary account/subaccount/conflict domain is invented;
8. exactly two conditional future readiness routes exist: `ROUTE_CANARY_PRIMARY_READY` and `ROUTE_CANARY_SEPARATE_DOMAIN_READY`;
9. Route-B isolation/inception/history/persistence predicates are referenced without importing B1-B8 capabilities;
10. ticker/browser/process/database/ledger/authority/namespace/strategy/restart pseudo-separation is prohibited;
11. primary-subaccount fallback and implicit subaccount defaulting are prohibited;
12. a future observer cannot perform any venue request or manual action before exact readiness artifact validation;
13. every future portfolio GET takes its explicit subaccount from accepted `canary_domain_identity`;
14. the current task performs no venue or credential activity;
15. the future observer remains GET-only programmatically;
16. future browser CREATE remains exactly one `1.00`-contract BUY YES LIMIT in the exact accepted canary domain;
17. the canary price remains deterministic, exact, grid-valid, and deliberately below the current best YES bid;
18. exact venue-native `order_id` is required before normal cancellation proof;
19. exact-order GET is required to prove `resting`;
20. fill-before-cancel and partial-fill races remain first-class terminal branches;
21. no second CREATE is possible after ambiguity, fill, failure, cleanup, or domain failure;
22. cancellation terminal state is established by authoritative GET evidence, not browser-click confirmation;
23. post-cancel `remaining_count_fp` semantics are observed rather than invented;
24. fill/fee/position reconciliation remains exact and fail-closed;
25. missing position rows are not zeroed;
26. retries, redirects, request counts, polling, deadlines, and pagination remain bounded;
27. evidence is byte/hash bound, domain-bound, and secret-safe;
28. browser cancellation does not validate `CancelOrderV2`;
29. the canary cannot release or bypass the held historical conflict domain;
30. no production, profitability, market-making, or arbitrage conclusion is inferred.

Final theorem:

```text
historical primary domain = still HELD
current canary execution domain = NONE PROVEN
manual canary execution now = NOT READY / NOT AUTHORIZED
future canary lifecycle contract = CONDITIONALLY SPECIFIED
next enabling work = substrate/domain-readiness work, not another manual order on primary subaccount 0
```

## 34. Stop boundary

After this Correction 02 specification and its subordinate handoff are prepared:

```text
STOP
```

This artifact does not authorize:

```text
observer implementation
test execution
account/subaccount facts execution
credential loading/signing
Kalshi GET
browser CREATE
browser CANCEL
programmatic venue write
subaccount/domain creation
funding/transfer
clean-domain bootstrap
Gate-D release
Gate-D market-maker execution
persistent-state mutation
repository modification
branch creation
commit
push
SPEC_02
Correction 03
```

If this Correction 02 is blocked, the specification lineage stops under the current task. No Correction 03 or SPEC_02 is authorized.

## Appendix A — exact CANARY_OPENAPI_OPERATION_BINDING_REV2 canonical JSON

```json
{"auth_headers":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-SIGNATURE","KALSHI-ACCESS-TIMESTAMP"],"base_path":"/trade-api/v2","binding_schema_revision":2,"book_side_enum":["bid","ask"],"demo_origin":"https://external-api.demo.kalshi.co","fixed_point_count":{"minimum_granularity":"0.01","response_scale":2,"type":"string"},"fixed_point_dollars":{"response_max_decimal_places":6,"type":"string"},"market_status_enum":["initialized","inactive","active","closed","determined","disputed","amended","finalized"],"market_type_enum":["binary","scalar"],"operations":[{"auth":"PUBLIC","method":"GET","operation_id":"GetMarket","path":"/markets/{ticker}","required_top_level":["market"],"response_200":"#/components/schemas/GetMarketResponse","used_parameters":["ticker:path"]},{"auth":"AUTHENTICATED_READ_ONLY","method":"GET","operation_id":"GetMarketOrderbook","path":"/markets/{ticker}/orderbook","required_top_level":["orderbook_fp"],"response_200":"#/components/schemas/GetMarketOrderbookResponse","used_parameters":["ticker:path","depth:query=0"]},{"auth":"AUTHENTICATED_READ_ONLY","method":"GET","operation_id":"GetOrders","path":"/portfolio/orders","required_top_level":["orders","cursor"],"response_200":"#/components/schemas/GetOrdersResponse","used_parameters":["ticker:query","min_ts:query","max_ts:query","limit:query=1000","cursor:query","subaccount:query=EXPLICIT_CANARY_DOMAIN"]},{"auth":"AUTHENTICATED_READ_ONLY","method":"GET","operation_id":"GetOrder","path":"/portfolio/orders/{order_id}","required_top_level":["order"],"response_200":"#/components/schemas/GetOrderResponse","used_parameters":["order_id:path"]},{"auth":"AUTHENTICATED_READ_ONLY","method":"GET","operation_id":"GetFills","path":"/portfolio/fills","required_top_level":["fills","cursor"],"response_200":"#/components/schemas/GetFillsResponse","used_parameters":["ticker:query","order_id:query","min_ts:query","max_ts:query","limit:query=1000","cursor:query","subaccount:query=EXPLICIT_CANARY_DOMAIN"]},{"auth":"AUTHENTICATED_READ_ONLY","method":"GET","operation_id":"GetPositions","path":"/portfolio/positions","required_top_level":["market_positions","event_positions"],"response_200":"#/components/schemas/GetPositionsResponse","used_parameters":["ticker:query","limit:query=1000","cursor:query","subaccount:query=EXPLICIT_CANARY_DOMAIN"]}],"order_status_enum":["resting","canceled","executed"],"outcome_side_enum":["yes","no"],"portfolio_subaccount_policy":"EXPLICIT_FROM_CANARY_DOMAIN_IDENTITY__NO_DEFAULT","source":{"api_info_version":"3.28.0","bytes":333315,"file":"04_TASK_CURRENT_SOURCE/openapi.yaml","openapi":"3.0.0","sha256":"cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b"}}
```

Identity:

```text
bytes = 2672
sha256 = bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8
```
