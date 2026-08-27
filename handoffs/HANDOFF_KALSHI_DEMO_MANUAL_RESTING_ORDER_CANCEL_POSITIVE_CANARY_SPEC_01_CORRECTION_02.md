# HANDOFF_KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02

```yaml
artifact_class: TECHNICAL_HANDOFF
subordinate_to: KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02.md
implementation_performed_by_this_artifact: false
venue_execution_performed_by_this_artifact: false
current_canary_execution_domain_readiness: NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
current_canary_real_execution_eligible: false
```

## 1. Controlling corrected specification

Implement only from the exact corrected specification:

```text
KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02.md
bytes = 93365
sha256 = b081feeee22d051d0f3f89b271e8029ab077d819512272df19b2151f5a254395
```

If this handoff conflicts with the specification, the specification controls.

This handoff is implementation context only. It is not execution authorization.

The exact immediate blocked predecessor remains lineage only:

```text
KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_01.md
bytes = 92102
sha256 = 24624214e43e788a174dfdecc56f14dbb324db7f7db427ea4251adc3512a642f

HANDOFF_KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_01.md
bytes = 18423
sha256 = 7dd278687758260c6f1b1ba5d74de4a32cc1265a0bb0aa497b47a801196fd64f
```

---

## 2. Canonical repository/base observed during specification authoring

```text
repository = rigolugo/ARB
branch = main
main = 997954197ebb8cbfb13baa3231b490abfbe20f64
tree = d3f392832132106f38fa1ba6d4fc715b9df18417
parent = d8b6f5f5db5fa76605dcd4ca1bd77fb0e16a5559
```

A later implementation or execution task must reverify the exact base it is assigned and stop on unexplained mismatch.

---

## 3. Controlling substrate boundary

Preserve exactly:

```text
KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md
bytes = 68568
sha256 = 512000eea8db5562768682ae1659c03c20a2b5093fba68ef37eae784039a8336

current_domain_readiness = NOT_GATE_D_EXECUTION_READY
overall_disposition = NO_CURRENTLY_VALID_EXECUTION_SUBSTRATE_PATH
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
```

The historical primary conflict domain remains:

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

Correction 01 does not resolve or bypass any of that state.

Current canary conclusion is exactly:

```text
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

---

## 4. Exact correction that closes the block

The blocked candidate fixed the future manual canary to primary `subaccount=0`.

Correction 01 replaces that assumption with an exact pre-network execution-domain gate.

A future canary domain is represented by one immutable `canary_domain_identity` binding at minimum:

```text
environment
account_scope_ref
venue_subaccount
conflict_domain_ref
domain_readiness_evidence_ref
domain_readiness_review_identity
readiness_route
```

Exactly two future routes exist:

```text
ROUTE_CANARY_PRIMARY_READY
ROUTE_CANARY_SEPARATE_DOMAIN_READY
```

Neither route is available now.

`ROUTE_CANARY_PRIMARY_READY` requires later controlling proof that the exact primary conflict domain is no longer held/risk-write-ineligible and satisfies all then-controlling predicates for introducing new risk.

`ROUTE_CANARY_SEPARATE_DOMAIN_READY` requires a genuinely separate venue/economic domain with proven exact identity, actual isolation, clean inception/history theorem, no ambiguous creation result, no unresolved order/fill/position/inventory/exposure, required persistence compatibility/binding, and an exact current readiness-review identity.

The following are never domain separation:

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

And:

```text
fallback_to_primary_subaccount_0 = PROHIBITED
implicit/default primary subaccount = PROHIBITED
```

---

## 5. Route-B sequencing reference only

Correction 01 does not import or authorize Route-B capabilities.

The controlling minimum sequence remains:

```text
B1. READ_ONLY account/subaccount capability-and-facts task
B2. persistent clean-domain bootstrap specification revision
B3. implementation + offline tests
B4a. complete-history READ_ONLY reconciliation for a preexisting domain

OR

B4b. domain-creation write specification
     + durable creation-result reconciliation
     + separate execution capability

B5. funding/transfer contract if required
B6. clean-domain bootstrap binding using exact inception evidence
B7. canonical installation/readiness review
B8. only then later Gate-D market-maker execution specification
```

For this manual canary, a separate-domain execution gate may open only after B7 for the exact domain plus an exact canary-domain readiness artifact satisfying the corrected specification.

B8 remains a separate Gate-D stage.

---

## 6. Exact source binding

Task-current source used to author Correction 01:

```text
04_TASK_CURRENT_SOURCE/openapi.yaml
bytes = 333315
sha256 = cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b
OpenAPI = 3.0.0
API info version = 3.28.0
```

Exact corrected canary operation-binding record:

```text
binding_schema_revision = 2
canonical_json_bytes = 2672
canonical_json_sha256 = bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8
portfolio_subaccount_policy =
EXPLICIT_FROM_CANARY_DOMAIN_IDENTITY__NO_DEFAULT
```

Operations remain exactly:

```text
GET /markets/{ticker}
GET /markets/{ticker}/orderbook
GET /portfolio/orders
GET /portfolio/orders/{order_id}
GET /portfolio/fills
GET /portfolio/positions
```

No POST/DELETE/PATCH/PUT belongs in the observer.

For every portfolio collection request:

```text
subaccount = canary_domain_identity.venue_subaccount
query parameter must be explicitly serialized
```

Do not rely on the source's default-to-primary behavior.

Pinned future Demo origin remains:

```text
https://external-api.demo.kalshi.co/trade-api/v2
```

No host fallback.

---

## 7. Future credential convention

If a later implementation/execution is separately authorized, observer credential sources remain exactly:

```text
KALSHI_DEMO_API_KEY_ID
KALSHI_DEMO_PRIVATE_KEY_PATH
```

The second variable contains a filesystem path only.

Never persist:

```text
API key value
private-key bytes
signature
signed auth headers
raw environment dump
```

No credential activity occurred during this correction.

---

## 8. Suggested exact later implementation paths

Default implementation writable paths should be only:

```text
src/arb/venues/kalshi/manual_resting_cancel_canary.py
tests/test_kalshi_manual_resting_cancel_canary.py
```

Readable protected dependencies may include:

```text
src/arb/venues/kalshi/models.py
src/arb/venues/kalshi/validation.py
src/arb/venues/kalshi/orderbook.py
src/arb/venues/kalshi/order_lifecycle.py
src/arb/venues/kalshi/quote_lifecycle.py
pyproject.toml
```

Do not modify protected dependencies by inference.

A one-shot real-execution wrapper should remain task-local unless a separate task makes it canonical supported behavior.

---

## 9. Core implementation state machine

Implement a closed state machine equivalent to:

```text
START
  -> VALIDATE_NONSECRET_INPUTS
  -> VALIDATE_DOMAIN_READINESS_ARTIFACT
  -> BIND_EXACT_CANARY_DOMAIN
  -> VALIDATE_SOURCE_BINDING
  -> MARKET_ELIGIBILITY
  -> BASELINE
  -> FINAL_PRICE_SNAPSHOT
  -> WAITING_FOR_USER_MANUAL_CREATE
  -> CREATE_BUDGET_CONSUMED
  -> DISCOVER_EXACT_ORDER
  -> BOUND_ORDER
  -> EXACT_RESTING_PROOF
  -> WAITING_FOR_USER_MANUAL_CANCEL   [only if still open]
  -> TERMINAL_EXACT_ORDER
  -> EXACT_FILLS
  -> POSITION
  -> RECONCILE
  -> EVIDENCE_FINALIZED
  -> STOP
```

If domain readiness validation fails:

```text
terminal_class = CANARY_EXECUTION_DOMAIN_NOT_READY
request_count = 0
manual_create_count = 0
manual_cancel_count = 0
STOP
```

Once `CREATE_BUDGET_CONSUMED` is entered, there is no transition back to a state that permits another CREATE.

Restart never restores the create budget and never creates a different domain.

---

## 10. Manual order contract

Only after the exact domain gate is valid, one future browser order may be prompted:

```text
Demo only
exact accepted account/subaccount/domain
BUY YES
LIMIT
quantity = "1.00"
price = exact deterministic P
```

`P` remains the fifth exact valid price-grid point below the fresh best YES bid, without crossing a `PriceRange` boundary.

Required pre-create market predicates still include:

```text
binary
active
>= 2 hours to close
two-sided non-crossed book
positive top sizes
valid price_ranges
zero preexisting resting user orders for selected ticker inside exact accepted canary domain
```

The zero-preexisting-order condition is only canary-attribution cleanliness. It is not clean-domain inception, complete history, or domain-readiness proof.

If the chosen ticker is ineligible, stop. Do not rotate ticker, domain, or subaccount in the same execution.

If the browser cannot prove the exact selected domain for the manual CREATE, stop before CREATE.

---

## 11. Exact identity and resting proof

After manual CREATE, discover only through explicitly scoped:

```text
GET /portfolio/orders
ticker = selected ticker
subaccount = canary_domain_identity.venue_subaccount
```

Candidate hard fields remain:

```text
new order_id not present in baseline
ticker exact
type = limit
outcome_side = yes
book_side = bid
initial_count_fp = "1.00"
yes_price_dollars = exact P
```

If optional `subaccount_number` is present, it must equal the bound venue subaccount.

Exactly one candidate binds:

```text
zero -> CANARY_ORDER_NOT_OBSERVED
multiple -> CANARY_IDENTITY_AMBIGUOUS
one -> immutable bound_order_id
```

Then `GET /portfolio/orders/{bound_order_id}` is mandatory.

Resting proof requires exact `status = resting`. List observation alone is insufficient.

Empty browser-generated `client_order_id` remains acceptable if source-valid.

---

## 12. Cancellation and fill races

Manual CANCEL remains browser-only and at most one total action for the exact visible canary order in the exact accepted canary domain.

Never implement:

```text
CancelOrderV2
cancel-all
batch cancel
fuzzy target selection
primary fallback
```

A full fill before cancel does not permit another order.

A partial fill while still resting may proceed to cancel the remainder of that same exact order.

Cleanup is not an independent write permission. It exists only after a valid domain-gated CREATE and only for that exact visible canary order.

If domain identity becomes ambiguous, do not redirect cleanup to primary or another domain.

Post-cancel `remaining_count_fp` remains intentionally not pre-assumed.

---

## 13. Reconciliation identities

Use exact Decimal/fixed-point arithmetic only.

While resting:

```text
fill_count_fp + remaining_count_fp == initial_count_fp
```

For complete exact bound-order fills:

```text
sum(unique fill.count_fp) == final_order.fill_count_fp
sum(unique fill.fee_cost)
    == final_order.maker_fees_dollars + final_order.taker_fees_dollars
```

For successful filled branches with usable exact baseline and terminal position rows:

```text
terminal.position_fp - baseline.position_fp
    == sum(unique bound fill.count_fp)

terminal.fees_paid_dollars - baseline.fees_paid_dollars
    == sum(unique bound fill.fee_cost)
```

Never treat an absent position row as zero.

All fills and positions collections must use the explicitly bound canary subaccount.

---

## 14. Bounds

Preserve exact observer bounds:

```text
per-request deadline = 10000 ms
request retry count = 0
redirect count = 0
response body cap = 2,000,000 bytes
global GET request budget = 48
candidate discovery polls = max 6, >= 2000 ms apart, phase <= 20000 ms
terminal exact-order polls = max 6, >= 2000 ms apart, phase <= 20000 ms
manual CREATE window = 120000 ms
manual CANCEL prompt window = 120000 ms
overall observation deadline = 900000 ms
collection page size = 1000
baseline orders pages = max 4
baseline recent-fill pages = max 4
baseline position pages = max 4
candidate-discovery pages per poll = max 2
bound-order fill pages = max 4
terminal position pages = max 4
```

Scheduled polls are new observations, not retries.

Domain-readiness failure occurs before network and therefore consumes zero GET requests.

---

## 15. Closed terminal classes

The corrected closed set adds the pre-network class:

```text
CANARY_EXECUTION_DOMAIN_NOT_READY
```

and preserves:

```text
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

`CANARY_EXECUTION_DOMAIN_NOT_READY` has highest precedence because it closes before venue activity.

---

## 16. Evidence package

Required minimum remains:

```text
CANARY_EVIDENCE_MANIFEST.json
CANARY_SUMMARY.json
MANUAL_ACTION_JOURNAL.json
one raw-response file for every GET that returned bytes
```

The corrected summary is:

```text
schema_id = KALSHI_DEMO_MANUAL_RESTING_CANCEL_CANARY_SUMMARY_V2
schema_revision = 2
```

It must bind at minimum:

```text
environment
account_scope_ref
subaccount
conflict_domain_ref
readiness_route
domain_readiness_evidence artifact/bytes/sha256
domain_readiness_review_identity
```

plus the preserved canary lifecycle/reconciliation fields.

For every raw response record exact byte length and SHA-256.

No secret material in evidence.

---

## 17. Review-critical tests

A later implementation review should focus first on:

1. readiness-artifact absence/mismatch yields `CANARY_EXECUTION_DOMAIN_NOT_READY` with `request_count=0`;
2. exact two-route validation and rejection of any third route;
3. same account/subaccount + different ticker remains the same conflict domain;
4. browser/process/database/ledger/authority/namespace/strategy/restart are rejected as pseudo-separation;
5. no fallback or implicit default to primary subaccount `0`;
6. explicit exact subaccount on every portfolio GET;
7. corrected source-binding identity and six exact GET operation bindings;
8. GET-only transport method allowlist and production-host rejection;
9. Decimal-only price/grid arithmetic including piecewise boundaries;
10. zero preexisting resting-order gate remains attribution-cleanliness only;
11. one-create state machine with no reopen after ambiguity/fill/read failure/restart;
12. zero/one/many exact order binding and immutable `bound_order_id`;
13. exact-order `resting` proof;
14. browser cancellation exact-domain boundary and cleanup no-fallback behavior;
15. partial/full fill races;
16. post-cancel canceled fixtures with different valid `remaining_count_fp` observations;
17. fill quantity/fee dedupe and reconciliation;
18. position absence remaining unknown rather than zero;
19. 10 s request deadlines through parsing, zero retries, zero redirects, 48-request cap;
20. Summary V2 and raw evidence SHA/byte/domain binding plus secret scan;
21. proof that no persistent ARB state, historical incident, writer proof, Gate-D permit, or programmatic venue write path is touched.

---

## 18. Block-closure locations

The corrected specification closes the formal block in these exact locations:

```text
Section 1
    current conditional lifecycle theorem

Section 2 / CANARY-BASE-005
    current readiness = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN

Section 5 / CANARY-SRC-002
    explicit bound-domain subaccount query policy

Section 9A / CANARY-DOMAIN-001..007
    two-route readiness gate, exact domain identity, Route-B theorem,
    pseudo-separation prohibition, no primary fallback

Section 11
    parameterized observer domain inputs

Sections 12, 14, 17, 20, 21
    explicit bound subaccount on portfolio observations

Section 16
    browser CREATE bound to exact accepted domain

Section 19
    cancel/cleanup bound to exact accepted domain

Section 25
    CANARY_EXECUTION_DOMAIN_NOT_READY terminal class

Section 26
    Summary V2 domain/readiness provenance

Section 28
    no pseudo-domain bypass

Section 31 / CANARY-TRACE-002
    BLOCK FINDING -> BLOCKED LOCATION -> CORRECTION-01 LOCATION -> STATUS
```

---

## 18A. Correction-02 exact source-binding closure

Correction 02 changes no technical contract beyond the two Appendix-A repairs below:

| MARCO BLOCK FINDING | CORRECTION-01 LOCATION | CORRECTION-02 LOCATION | STATUS |
|---|---|---|---|
| Appendix binding label `CANARY_OPENAPI_OPERATION_BINDING_REV1` is stale while `binding_schema_revision = 2` | Appendix A heading | Appendix A heading | `CLOSED_IN_CORRECTION_02` — exact label is `CANARY_OPENAPI_OPERATION_BINDING_REV2` |
| Appendix terminal canonical JSON `bytes = 2528` conflicts with the verified binding identity | Appendix A terminal Identity block | Appendix A terminal Identity block | `CLOSED_IN_CORRECTION_02` — exact bytes are `2672`; SHA-256 remains `bfae4c05e8c91b855cd222dc97fac62d8610353c1b10175439bd4860a987c9e8` |

Mechanical updates are limited to Correction-02 artifact identity/lineage and this handoff's exact controlling-specification identity.

---

## 19. Non-negotiable interpretation boundaries

The historical primary domain is still held.

No current canary execution domain is proven.

A successful future canary may establish only one current Demo manual order's observed lifecycle representation inside a domain that was already proven ready by separate controlling evidence.

It does not establish:

```text
programmatic CreateOrderV2 behavior
programmatic CancelOrderV2 behavior
Gate-D execution readiness
NORMAL_WRITER
writer-proof release
clean-domain inception by canary observation
persistent ledger compatibility
market-maker profitability
production behavior
arbitrage
historical incident closure
```

---

## 20. Current handoff stop

Current theorem:

```text
historical primary domain = still HELD
current canary execution domain = NONE PROVEN
manual canary execution now = NOT READY / NOT AUTHORIZED
future canary lifecycle contract = CONDITIONALLY SPECIFIED
next enabling work = substrate/domain-readiness work, not another manual order on primary subaccount 0
```

This handoff authorizes no implementation, tests, credentials, venue activity, account/subaccount facts execution, domain creation, funding/transfer, clean-domain bootstrap, persistent mutation, Git/repository write, Gate-D execution, SPEC_02, or Correction 03.

Stop after delivery of the Correction-02 specification and this handoff. If Correction 02 is blocked, stop; no Correction 03 or SPEC_02 is authorized.
