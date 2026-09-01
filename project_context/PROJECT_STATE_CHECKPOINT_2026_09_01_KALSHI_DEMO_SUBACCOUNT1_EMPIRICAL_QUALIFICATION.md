# PROJECT STATE CHECKPOINT — 2026-09-01 — KALSHI DEMO SUBACCOUNT 1 EMPIRICAL QUALIFICATION

Authority level: canonical current-state overlay **once installed on canonical `main`**.

This checkpoint preserves the material direct empirical findings obtained after
`PROJECT_STATE_CHECKPOINT_2026_08_29_ROUTE_B_B1_SOURCE_BINDING_CORRECTION_02_INSTALLATION.md`
and routes the next bounded Route-1 action.

It supersedes older checkpoint statements only where those statements say that no numbered
subaccount is observed, that Route 1 remains merely speculative, that explicit N=1 cancellation is
unproven, or that the next action is only Route-1/Route-2 comparison. Historical primary-domain
safety facts remain unchanged.

This checkpoint grants no production capability, no primary-domain reuse, no writer-proof release,
no additional funding, no additional CreateOrder, no executable fill canary, no market-making
execution, and no profitability or arbitrage claim by itself.

## 1. Canonical base for this pending installation

```text
repository = rigolugo/ARB
branch = main
required_base_commit = 029117361f08316a87fee808074ced1257dc0d66
required_base_tree = 94d1d0479e4f2907d27bccf4e2ce0ac70c224565
required_base_parent = 2fed77a33e3a4be7cbded90a1f8f0d015fcc8a16
required_base_message = Canonicalize B1 Execution 02 and route evaluation
```

Install only if those exact identities still control or after a separately reviewed rebase of this
canonicalization package. Do not silently transplant this checkpoint onto unexplained canonical drift.

## 2. Historical primary domain remains held

The historical primary economic domain remains:

```text
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0
```

Preserved theorem:

```text
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
historical_primary_safe_to_reuse_proven = false
historical_primary_incident_resolved = false
historical_primary_writer_proof_released = false
PRIMARY_DOMAIN_REUSE = NOT_AUTHORIZED
```

Nothing in the Route-1 subaccount work reconciles, releases, or economically clears the historical
primary-domain incident.

## 3. Direct empirical CreateSubaccount finding

One separately authorized Demo `CreateSubaccount` probe was executed while:

```text
usage_tier = basic
grants = []
pre-create numbered subaccounts = []
```

The exact one-shot request returned:

```text
POST /trade-api/v2/portfolio/subaccounts
body = {"exchange_index":0}
HTTP = 201
response = {"subaccount_number":1}
create_post_count = 1
automatic_retry_count = 0
```

Two post-create account-wide surfaces then agreed on `[0,1]`.

Accepted direct empirical theorem for this exact Demo account/environment/time:

```text
SUBACCOUNT=1 EXISTS = PROVEN
controlled inception of SUBACCOUNT=1 = PROVEN
Basic-tier CreateSubaccount acceptance = OBSERVED
documented Advanced+ rule enforcement on this exact Demo account = FALSIFIED FOR THIS OBSERVATION
production behavior = NOT INFERRED
```

Documentation remains useful as intended semantics; it does not override directly observed behavior
for this exact Demo environment/account/time.

## 4. N=1 clean-inception/read evidence

The bounded read-only suite established:

```text
account-wide balances subaccounts = [0,1]
account-wide netting subaccounts = [0,1]
surfaces_agree = true

N=1 live orders = 0
N=1 live fills = 0
N=1 live positions = 0
N=1 settlements = 0
N=1 historical orders = 0
N=1 historical fills = 0
N=1 historical positions = 0
```

All listed N=1 traversals reached cursor exhaustion within their configured bounds. Account-wide
retained-history cross-checks found no N=1 historical orders or fills.

Preserved limitation from the first read suite:

```text
candidate_clean_read_state_supported = false
```

Several empty invalid-value/control responses did not independently prove every read filter's
behavior. Later direct write/exact-read evidence is stronger evidence for N=1 economic routing.

## 5. Transfer/funding and transfer-history evidence

A separately authorized Demo numbered-subaccount funding transfer was executed and reconciled:

```text
probe = KALSHI_DEMO_SUBACCOUNT1_FUNDING_TRANSFER_EMPIRICAL_PROBE_01
from_subaccount = 0
to_subaccount = 1
exchange_index = 0
amount = $1.00
POST count = 1
HTTP = 200
automatic POST retry count = 0
terminal = TRANSFER_SUCCEEDED_AND_READBACK_CONFIRMED
```

Post-transfer evidence proved N=1 funding on exchange index 0. Later shard diagnostics established:

```text
N=1 aggregate >= $1 = true
N=1 exchange_index=0 >= $1 = true
N=1 exchange_index=2 = zero

primary exchange_index=0 >= $1 = true
primary exchange_index=2 > $0.00 and < $0.02
primary exchange_index=2 >= $0.01 = true
```

No direct shard-2 numbered-subaccount funding transfer was executed after that diagnostic.

A read-only transfer-history delta probe also established that the intra-account-transfer history
surface succeeded with `limit=500`, exhausted its cursor, and exposed one completed historical
cross-shard transfer row from shard 0 to shard 2. The preceding `limit=1000` request had returned
HTTP 400. This establishes actual observed interface behavior only; it grants no transfer capability.

## 6. Exchange-index routing diagnostics

A market on exchange index 2 was directly observed while N=1 funding was on exchange index 0.

Observed one-shot write diagnostics:

```text
CreateOrder with request exchange_index=0 against an exchange-index-2 market
    -> HTTP 404
    -> no N=1 order/fill/position residue observed

CreateOrder with request exchange_index=2
    -> HTTP 403
    -> no N=1 client-id match
    -> no primary-0 client-id match

CreateOrder against a matching exchange-index-0 market during a later run
    -> HTTP 503 service_unavailable
    -> no effect observed
```

The HTTP 503 is availability evidence, not proof of semantic rejection.

## 7. Ticker auto-routing and actual CreateOrderV2 response shape

A later health-gated request supplied a current exchange-index-0 ticker, set `subaccount=1`, and
**omitted `exchange_index`**.

Preflight directly observed:

```text
exchange_active = true
trading_active = true
exchange_index 0 exchange_active = true
exchange_index 0 trading_active = true
N=1 exchange-index-0 balance >= $1 = true
```

CreateOrder returned HTTP 201.

Accepted direct empirical theorem:

```text
CreateOrderV2 ticker auto-routing with exchange_index omitted = ACCEPTED
HTTP 201 order identity = VENUE-BOUND
exact resulting economic domain = SUBACCOUNT=1 / exchange_index=0
```

The actual Demo HTTP 201 response shape observed repeatedly is a **top-level order summary** containing
at least `order_id`, `client_order_id`, `fill_count`, `remaining_count`, and `ts_ms`. Probe code that
assumed `{"order": ...}` misparsed a valid 201 and required recovery. Future ARB specification and
implementation work must preserve the actual observed response behavior for this exact Demo target
rather than silently assuming a wrapper shape.

## 8. Exact-order reconciliation and read-after-write visibility

Multiple HTTP-201-created orders were subsequently reconciled by exact order ID and proved:

```text
subaccount_number = 1
exchange_index = 0
fill_count = 0.00
```

Earlier canaries were canceled by their configured expiration before an explicit cleanup DELETE was
issued. They reconciled to zero N=1 fill rows and zero N=1 position rows; one recovery also observed
zero corresponding primary-0 fill rows for the exact order.

A later durably bound 201 order established live read-after-create visibility and queue position:

```text
GET /trade-api/v2/portfolio/orders/{exact_order_id}
HTTP = 200
status = resting

GET /trade-api/v2/portfolio/orders/{exact_order_id}/queue_position
HTTP = 200
queue_position_fp = 100.00
```

The operator process then failed locally with a Python `NameError` before cancel-intent persistence
and before DELETE; the later recovery found that order canceled by expiration with no fill.

This local bug is preserved as provenance and did not consume a cancel write.

## 9. Final explicit live N=1 cancellation canary — accepted finding

A final separately authorized same-process canary closed the remaining cancellation question.

Probe:

```text
KALSHI_DEMO_SUBACCOUNT1_FINAL_EXPLICIT_CANCEL_CANARY_10
completed_at_utc = 2026-08-31T17:30:16.761628Z
environment = KALSHI_DEMO
```

Preflight and market binding:

```text
exchange_active = true
trading_active = true
exchange_index 0 active/trading = true
N=1 exchange_index 0 balance >= $1 = true
selected ticker = KXGOLDH-26AUG3115-T4425.99
selected market exchange_index = 0
create request exchange_index field = OMITTED
```

Create/result binding:

```text
CreateOrder POST count = 1
CreateOrder HTTP = 201
CreateOrder response bytes = 175
CreateOrder response SHA-256 = 7410647368f52813fa6860041c2ba472acc557856ddd1aca810b908e74c430ba
HTTP-201 order identity durably bound = true
```

Observed exact-read visibility lag for this exact order:

```text
immediate exact GET = HTTP 404
+0.25s exact GET = HTTP 200 / status=resting
subaccount_number = 1
exchange_index = 0
fill_count = 0.00
remaining_count = 1.00
```

Queue-position observation:

```text
HTTP = 200
queue_position_fp = 100.00
response SHA-256 = 88cc87d86132b3888fe51e401653625a90a0422fd066a9449353a1a3b16afb1b
```

Explicit exact cancel:

```text
DELETE count = 1
automatic write retry count = 0
DELETE HTTP = 200
DELETE response bytes = 93
DELETE response SHA-256 = 40abde44ef311b5e97e60427d9c559dc35390bf647b859af2ffef945c9041016
cancel response reduced_by = 1.00
```

Post-cancel exact-read sequence:

```text
t+0.00s = resting
t+0.25s = resting
t+0.50s = canceled
```

Final authoritative reconciliation:

```text
exact final status = canceled
N=1 fill count for order = 0
primary-0 fill count for order = 0
N=1 position row count = 0
confirmed = true
terminal = FINAL_EXPLICIT_CANCEL_TARGETED_N1_CONFIRMED_NO_FILL
production activity = NONE
```

Accepted direct empirical theorem for the exact observed Demo target:

```text
live queue-position read on a resting N=1 order = PROVEN
explicit exact DELETE targeting the bound N=1 order = PROVEN
explicit-cancel transition to canceled = PROVEN
no-fill cancellation reconciliation = PROVEN
corresponding primary-0 fill spillover = NONE OBSERVED
```

This does not prove executable-fill isolation because the canary was intentionally post-only and
unfilled.

## 10. Current Route-1 economic-domain theorem

Current accepted theorem after the final cancellation canary:

```text
Kalshi Demo SUBACCOUNT=0
    historical incident = PRESERVED
    writer_proof_state = HELD
    historical unresolved exposure = UNKNOWN_UNBOUNDED
    safe to reuse = NOT PROVEN
    DO NOT REUSE

Kalshi Demo SUBACCOUNT=1
    exists = PROVEN
    controlled inception = PROVEN
    account-wide identity = PROVEN
    initial live/historical emptiness = OBSERVED
    funding on exchange_index=0 = PROVEN
    CreateOrder ticker auto-routing = PROVEN
    exact CreateOrder domain binding to N=1 = PROVEN
    exact resulting exchange_index=0 = PROVEN
    top-level HTTP-201 CreateOrder response shape = OBSERVED
    exact order-id readback = PROVEN
    bounded read-after-create visibility lag = OBSERVED
    live queue-position read = PROVEN
    explicit exact DELETE cancel = PROVEN
    no-fill cancel reconciliation = PROVEN
    primary-fill spillover in cancel canary = NONE OBSERVED
    executable fill/readback/position isolation = NOT YET PROVEN
```

Route decision:

```text
PREFERRED_ROUTE = ROUTE_1_SUBACCOUNT_1
ROUTE_2_PRIMARY_RECLAMATION = DEFERRED_FALLBACK
```

Advanced account tier is not a practical Route-1 `CreateSubaccount` blocker for the exact observed
Demo account/time. This statement must not be extrapolated to production.

N=1 is now a **qualified candidate execution domain**, not yet a fully proven execution domain,
because deliberately executable fill/position isolation remains untested.

## 11. Remaining material empirical gap

Do not repeat prior CreateSubaccount, funding, resting-create, queue-position, or cancel probes merely
because a later chat lacks this history. The only major pre-stack-binding empirical write behavior
still unresolved is:

```text
1. one deliberately executable one-contract N=1 order/fill
2. exact N=1 fill readback for that exact order
3. exact resulting N=1 position readback
4. prove no corresponding primary-0 fill spillover
5. prove no corresponding primary-0 position spillover
```

That fill canary requires a separate explicit task authorization after this checkpoint is canonically
installed. It is not authorized by this checkpoint.

## 12. External evidence identities and retention

The following sanitized/local operator artifacts remain **external/local-only evidence**. Their raw
bytes are not required to be committed. Canonical continuity is provided by exact identities where
available plus the sanitized facts recorded in this checkpoint.

```text
CREATE_SUBACCOUNT_INTENT.json
  bytes = 719
  sha256 = 4cd351f387d53e5af80ebc21975201183e550df05031d5e07b3f22840663831e

CREATE_SUBACCOUNT_ONE_SHOT_CONSUMED.marker
  bytes = 255
  sha256 = 0f8e515074928e72f8bd621ab4c30ffbc474673ea6ed2c99b3b157842a9d2293

CREATE_SUBACCOUNT_PROBE_RESULT.json
  bytes = 1268
  sha256 = 29dfc0d15f8c8716682aeea0d674ab9f376452bf5208d5b3c2230dd23eac8124

KALSHI_DEMO_SUBACCOUNT1_PRECANONICAL_EMPIRICAL_PROBE_SUITE_01_RESULT.json
  bytes = 27363
  sha256 = 1a00e26e5c4a8f98f2258e60a606b3c4bbb5be81fc9fedc96527bc881ae84f03

KALSHI_DEMO_SUBACCOUNT1_PRECANONICAL_EMPIRICAL_DELTA_PROBE_02_RESULT.json
  bytes = 3653
  sha256 = bfad91965915ebfbb7256398698df34d5b3434bba9886fb0776eed65540d8f60

KALSHI_DEMO_SUBACCOUNT1_PRECANONICAL_EMPIRICAL_DELTA_PROBE_03_RESULT.json
  bytes = 2025
  sha256 = b71c20a4aab642c07e3d5321b565f718e452dddded9f0b95fee408ba0c95aa28

FUNDING_TRANSFER_RESULT.json
  bytes = 3233
  sha256 = d145345ce190f0c5fd9e6d9d5ebab7f764756fe6fb110718c2151ac4a62f3cbe

KALSHI_DEMO_SUBACCOUNT1_CREATE_404_EXCHANGE_INDEX_DIAGNOSTIC_01_RESULT.json
  bytes = 2801
  sha256 = e41a75e441efb14b076eab213c2383fa8680602e8f1572fa9e2dbf945af4e14a

CREATE_EXCHANGE_INDEX2_RESULT.json
  bytes = 1560
  sha256 = 02feb231939d0f81f7f425a68254f38dd461f84977a66495e202be111be75876

KALSHI_DEMO_SUBACCOUNT1_SHARD_BALANCE_DIAGNOSTIC_01_RESULT.json
  bytes = 3987
  sha256 = 9af768304693e118d3f6175709eac1c52506e78c9b4affc714a2b387aba52bb7

KALSHI_DEMO_SUBACCOUNT1_SHARD2_DIRECT_FUNDING_THRESHOLD_DIAGNOSTIC_02_RESULT.json
  bytes = 1830
  sha256 = d466fea675bf358507eff25c32ace561e45b3487a902f5d8e75db6fb6e471af4

KALSHI_DEMO_SUBACCOUNT1_EXCHANGE0_MARKET_SELECTION_PREFLIGHT_01_RESULT.json
  bytes = 15708
  sha256 = e6a2e4d19dda99f63528ecafb0d163a1b1869f70e7fc6a60d79bbb71bbece387

DYNAMIC_EXCHANGE0_RESTING_CREATE_CANCEL_RESULT.json
  bytes = 3541
  sha256 = 48162ff87784ca577cfd78d775a39338e6517b0d73a3c90a15669191f9edff1c

HEALTH_GATED_AUTOROUTE_CREATE_CANCEL_RESULT.json
  bytes = 2380
  sha256 = 8b1d556030b2c8b00467e5264168e4030647ec19b45df639297ea60941e43662

EXACT_201_ORDER_RECONCILE_CANCEL_RESULT.json
  bytes = 3695
  sha256 = 8ab9eb2bde4f3a9f7c2a565dbab4391ad9688bd4d2b90f727156af0f5d9982b1

LIVE_QUEUE_EXPLICIT_CANCEL_RESULT.json
  bytes = 889
  sha256 = 8c534147a4a920062ccb7cab66edb11636faab094b8d9763ce17b716aea2cadd

PROBE06_201_RECOVERY_QUEUE_CANCEL_RESULT.json
  bytes = 4229
  sha256 = b6d6d3f8fb3a1544a94a0e329c3da744f91dd6557ae4967505591d39c21913fb

PROBE08_CANCEL_RECOVERY_RESULT.json
  bytes = 1051
  sha256 = 6b5aa16a3c494d6020dd5d3b63583a4529d5647ed486b45231de19c8e3811784

FINAL_EXPLICIT_CANCEL_RESULT.json
  original File Library/local operator item = RETAINED
  original raw bytes = NOT_REESTABLISHED_IN_CURRENT_HANDOFF
  original raw sha256 = NOT_REESTABLISHED_IN_CURRENT_HANDOFF
  material content = captured in Section 9
```

Additional operator-transcript evidence from the failed Probe-08 process is retained as accepted
provenance for the exact observations before the local exception:

```text
exact order visibility HTTP = 200
exact order status = resting
queue-position HTTP = 200
queue_position_fp = 100.00
local failure = NameError: PATH_CANCEL_PREFIX not defined
failure occurred before cancel-intent persistence and before DELETE
```

The canonicalization handoff package contains a deterministic JSON reconstruction of the File
Library-visible `FINAL_EXPLICIT_CANCEL_RESULT.json` content for transfer convenience. That reconstruction
is **not** asserted to be byte-identical to the user's original local file and must not replace the
original evidence identity.

## 13. Evidence authority and discrepancy handling

For actual external runtime behavior, preserve this precedence:

```text
1. controlling ARB safety/capability requirements
2. direct empirical observation of exact target environment/account/interface
3. accepted/canonicalized empirical ARB evidence
4. official documentation/schemas
5. third-party research
6. ARB inference
```

Observed documentation/runtime discrepancies are preserved rather than erased:

```text
documented CreateSubaccount Advanced+ rule
vs
Basic Demo account CreateSubaccount HTTP 201

documented/assumed CreateOrder response wrapper
vs
observed top-level Demo HTTP 201 order summary
```

These observations apply only to the exact environment/account/interface/time observed and do not
establish production behavior.

## 14. Current next action after canonical installation

Current next-action class:

```text
KALSHI_DEMO_SUBACCOUNT1_EXECUTABLE_FILL_AND_ISOLATION_EMPIRICAL_CANARY
```

Required ordering:

```text
FIRST:
    canonically install this checkpoint/router/index update

THEN, only under separate explicit authorization:
    one deliberately executable one-contract N=1 fill canary
    exact fill + position reconciliation
    prove no corresponding primary-0 economic spillover

THEN:
    canonicalize the completed N=1 execution-domain theorem

THEN:
    bind existing ARB ledger/risk/restart/execution machinery explicitly to SUBACCOUNT=1

THEN:
    one tiny bounded order-lifecycle canary under that bound stack

THEN:
    minimal Demo market-making experiment
```

No market-making profitability or logical-arbitrage claim is established by this checkpoint.

## 15. Canonicalization status of this file

Until a verified repository commit installs this file and updates the canonical router/index:

```text
CANONICALIZATION_STATUS = PENDING
```

The canonicalization task itself performs **repository documentation writes only**. It must perform
no Kalshi request, no credential use, no venue write, no persistent trading-state mutation, and no
production activity.
