# PROJECT STATE CHECKPOINT — 2026-09-05 — R1-D07 MARKET SELECTION AND READ-ONLY PREFLIGHT PREPARATION

Authority level: canonical current-state overlay when installed on canonical `main`.

This checkpoint records accepted local/external empirical evidence for the R1-D07
Kalshi Demo market-selection preparation sequence and the subsequent network-free
live-entrypoint availability finding. It is an evidence/state carrier, not a new
trading-capability grant and not a permanent market-selection implementation
specification.

It supersedes older next-action text only where older text says R1-D07 market
selection has not been performed or that no task-current D07 read-only input ticker
has been qualified.

## 1. Canonical substrate for this checkpoint task

```text
repository = rigolugo/ARB
required_base_commit = 66de67d45d40f0edab77353f567270eea79211c5
required_base_tree   = fa8d3942a10e5d388bd2d12accbcb2ce36381842
required_base_parent = 63b881b7c6c81d30608ba61dca0aaf840028e4ee
```

The canonicalization task must stop on any unexplained base/tree/provenance mismatch.

## 2. R1-D07 preparation state

```text
R1-D07_S00_market_selection_empirical_process = COMPLETE_FOR_THIS_PREFLIGHT
P03_A4_complete_72h_market_discovery           = COMPLETE
P03_C1_batch_orderbook_validation              = COMPLETE
P03_B1_exact_6h_trade_recency                  = COMPLETE
P03_C2_final_fresh_revalidation                = COMPLETE

selected_ticker_for_D07_read_only_preflight =
    KXNCAAFGAME-26SEP05CLEMLSU-CLEM

selected_subaccount_context = 1
selected_exchange_index_context = 0

D07_read_only_Stage3_preflight =
    BLOCKED_PENDING_REVIEWED_LIVE_ENTRYPOINT

live_entrypoint_availability =
    PREFLIGHT_LIVE_ENTRYPOINT_UNAVAILABLE

D07_venue_write = NOT_AUTHORIZED
production = NOT_AUTHORIZED
R1-D08 = NOT_AUTHORIZED
```

The selected ticker is an input for the already-defined D07 **read-only** Stage-3
preflight only. It is not a permanent strategy constant, not a writer permit, not a
profitability result, and not an arbitrage claim.

## 3. Exact external/local evidence identities

Raw result JSON remains external/local. The repository records the identities and
accepted projections below rather than committing raw probe output.

| Evidence | Bytes | SHA-256 | Classification |
|---|---:|---|---|
| `KALSHI_DEMO_SUBACCOUNT1_EXCHANGE0_MARKET_SELECTION_PREFLIGHT_03_RESULT.json` | 16082 | `f902c1add483042be3cbdc9a49d30d7a5e94d9f65662244e04e9cbb76837af8e` | DIRECT_EMPIRICAL_OBSERVATION / bounded-partial precursor |
| `KALSHI_DEMO_MARKET_SELECTION_P03_A2_OPEN_EVENTS_DIAGNOSTIC_01_RESULT.json` | 33142 | `3c7fbbf0ba297a1212d3cf57f7a2e3969e4441d9812506603e2ab0d5b54a0a5a` | DIRECT_EMPIRICAL_OBSERVATION |
| `KALSHI_DEMO_MARKET_SELECTION_P03_A3_NESTED_EXACT_PARITY_DIAGNOSTIC_01_RESULT.json` | 24879 | `2a41be20592a2eeea10ca451f470aadeb41b14afc103a0b31551f649f1d6e17f` | DIRECT_EMPIRICAL_OBSERVATION |
| `KALSHI_DEMO_MARKET_SELECTION_P03_A4_COMPLETE_72H_MARKETS_DIAGNOSTIC_01_RESULT.json` | 160992 | `5b810665c5b836c23849161ae65c8fa28ab408b4a44e82b6dc38312dd51a24b6` | DIRECT_EMPIRICAL_OBSERVATION |
| `KALSHI_DEMO_MARKET_SELECTION_P03_C1_BATCH_ORDERBOOK_DIAGNOSTIC_01_RESULT.json` | 140851 | `2199972712bb4b360380300f5abf3fc847c8c35eed7d99c5d26d153f339dcdda` | DIRECT_EMPIRICAL_OBSERVATION |
| `KALSHI_DEMO_MARKET_SELECTION_P03_B1_EXACT_TRADE_RECENCY_DIAGNOSTIC_01_RESULT.json` | 48040 | `0d91b55ca79462c16be21c386535245304f0dd8646d9794d447f0d869d87cd5a` | DIRECT_EMPIRICAL_OBSERVATION |
| `KALSHI_DEMO_MARKET_SELECTION_P03_C2_FINAL_FRESH_REVALIDATION_DIAGNOSTIC_01_RESULT.json` | 12757 | `38ee108cabfc3efe0882f3e9b9929dc0148396cae2846fa3126db544eb09d3c6` | DIRECT_EMPIRICAL_OBSERVATION |
| `R1_D07_LIVE_ENTRYPOINT_AVAILABILITY_DIAGNOSTIC_01_RESULT.json` | 5139 | `7c4d5c081a970a22ce1068488c9f3c5da5029b26518d3db2ffca7aa3eadd6086` | DIRECT_EMPIRICAL_OBSERVATION / local-network-free |

## 4. Historical precursor and why it was insufficient

The earlier bounded `PREFLIGHT_03` run observed:

```text
market_pages_fetched = 20
market_rows_observed = 20000
market_pagination_complete = false
market_cursor_remaining_after_cap = true

trade_pages_fetched = 20
trade_rows_observed = 20000
trade_pagination_complete = false

recommended_subset_candidate =
    KXHIGHLAX-26SEP05-B79.5
```

That result never proved complete discovery or a global-best market. The later A3
exact observation showed that old subset candidate had become effectively
non-executable at the top of book, demonstrating that market-selection quality can
decay materially over hours. Therefore an old selector result cannot be reused as a
current D07 input without fresh revalidation.

## 5. A2/A3 topology and schema findings

P03-A2 completed the exact public open-event query in
`74` pages and observed:

```text
open_event_count = 14792
nested_market_count = 123270
duplicate_event_tickers = 0
duplicate_market_tickers = 0
event_vs_market_exchange_index_mismatch_count =
    0
```

Nested market statuses were not uniformly active. Market-level status therefore
must be screened locally.

P03-A2 observed `is_provisional` absent from all
`123270` nested Market objects.
P03-A3 then checked five exact `GET /markets/{ticker}` targets and observed
`is_provisional` absent in exact responses for all five as well:

```text
A3 exact target count = 5
A3 exact exchange_index=0 count = 5
A3 exact is_provisional present count =
    0
A3 nested is_provisional present count =
    0
```

For this exact Demo environment/time, missing `is_provisional` is preserved as
`NOT_EXPOSED` / unknown. It MUST NOT be synthesized as `false`.

Official Kalshi documentation observed during the diagnostics displayed the field.
That documentation fact remains `OFFICIAL_KALSHI_SOURCE_NONCONTROLLING`; the
direct exact-target empirical observation controls actual target-runtime behavior
for the observed environment/time. A future task requiring task-current source
binding must revalidate the official source as required by its own dispatch.

Event-level and market-level `exchange_index` matched throughout A2, but this is
not promoted into a general routing theorem. Market-level returned
`exchange_index` remains the authoritative market-selection field.

## 6. Accepted market-selection process for this D07 read-only preflight

### 6.1 A4 — complete bounded discovery

P03-A4 used public `GET /markets` with a frozen 30-minute-to-72-hour close
window, `limit=1000`, cursor continuation, `mve_filter=exclude`, and **no**
status query parameter.

The exact result established:

```text
pagination_complete = true
pages_fetched = 85
market_count = 84750
duplicate_ticker_count = 0
scope_contradiction_count =
    0

exchange_index_0_count =
    18609
active_market_count =
    24482
preliminary_exchange_index_0_eligible_count =
    1573
retained_discovery_pool = 100
```

A4 local screening for the D07 discovery pool required:

- `status == active`;
- `market_type == binary`;
- returned market `exchange_index == 0`;
- valid `price_ranges`;
- direct summary YES book two-sided/non-crossed;
- direct YES ask `<= 0.8000`;
- direct YES ask quantity `>= 1.00`.

`is_provisional` remained observation-only because it was not exposed.
MVE exclusion came from the explicit request parameter `mve_filter=exclude`,
not from interpreting absent MVE response fields.

A4 generated a **discovery pool**, not a final D07 market.

### 6.2 C1 — current full-orderbook validation and event diversity

P03-C1 requested the exact A4 top 100 in one authenticated Demo batch-orderbook
read. It established:

```text
requested_returned_set_equal =
    true
shape_valid_books = 100 / 100
two_sided_books = 100 / 100
crossed_or_locked = 0
current_eligible = 100 / 100
event_diverse_shortlist = 20
```

Native orderbooks expose YES bids and NO bids. For selector analysis only, YES
asks were derived from native NO bids. That analytical complement does not grant
or broaden Stage-3 risk/release authority.

The expensive trade-validation stage retained at most one market per event.
Event diversity is a validation-budget rule, not a claim that same-event markets
are invalid.

### 6.3 B1 — exact recent-trade validation

P03-B1 used exact-ticker public trade reads for the 20 event-diverse C1
candidates over one frozen six-hour non-block window. Every ticker exhausted
pagination in this observation:

```text
candidate_count = 20
complete_with_activity = 17
complete_zero_trades = 3
incomplete = 0
finalist_count = 5
public_demo_get_count = 20
```

An incomplete trade window is `TRADE_WINDOW_INCOMPLETE` and is excluded from
ranking without making a market-quality inference.

Only complete windows with at least one non-block trade were eligible for B1
finalist ranking. The observed B1 ranking ordered by:

1. latest trade age ascending;
2. six-hour traded quantity descending;
3. six-hour trade count descending;
4. C1 current spread ascending;
5. C1 minimum two-sided 2-cent depth descending;
6. C1 rank;
7. ticker.

This exact ordering records the empirical process used for this D07 selection.
It does not prove optimal profitability.

### 6.4 C2 — task-current final revalidation and one explicit input ticker

P03-C2 performed five public exact-market reads plus one authenticated exact
five-ticker batch-orderbook read.

It established:

```text
market_metadata_eligible = 5 / 5
orderbook_eligible = 5 / 5
final_candidate_eligible = 5 / 5
selected_ticker =
    KXNCAAFGAME-26SEP05CLEMLSU-CLEM
```

Final C2 selection used:

1. fresh C2 orderbook spread ascending;
2. B1 rank ascending;
3. ticker ascending.

For the selected ticker C2 observed at that time:

```text
ticker = KXNCAAFGAME-26SEP05CLEMLSU-CLEM
event_ticker = KXNCAAFGAME-26SEP05CLEMLSU
status = active
exchange_index = 0
YES bid = 0.2200
YES ask = 0.2300
YES bid qty = 3787.85
YES ask qty = 3619.74
spread = 0.0100
```

Those quote/depth values are historical observations, not standing current truth.
The D07 read-only Stage-3 preflight must independently revalidate task-current
market/orderbook and subaccount-wide risk/reconciliation state.

## 7. Reusable selector architecture boundary

The accepted empirical sequence to preserve for later permanent selector
specification is:

```text
complete bounded Get Markets discovery
-> deterministic local eligibility screen
-> retained discovery pool
-> authenticated exact batch full-orderbook validation
-> event-diverse expensive-validation shortlist
-> exact-ticker complete recent-trade windows
-> small finalist set
-> immediate exact-market + full-orderbook fresh revalidation
-> one explicit operator-reviewable D07 read-only input ticker
```

The selector remains **outside** the trusted Stage-3 release/writer surface.

Future permanent code should distinguish at least conceptually:

```text
DISCOVERY_CANDIDATE
AUTHORITATIVELY_VALIDATED_CANDIDATE
D07_SELECTED_TICKER
```

No selector result can substitute for Stage-3 risk/release truth, dynamic
subaccount-wide completeness, writer eligibility, or write authorization.

## 8. Current live-entrypoint finding

After C2, the network-free availability diagnostic ran against exact canonical:

```text
HEAD = 66de67d45d40f0edab77353f567270eea79211c5
tree = fa8d3942a10e5d388bd2d12accbcb2ce36381842
tracked modifications = 0
untracked paths = 0
runner blob identity = PASS
required active-V2 interface = PASS
live non-test entrypoint candidates =
    0
partial non-test candidates =
    0
test-only examples =
    1
disposition =
    PREFLIGHT_LIVE_ENTRYPOINT_UNAVAILABLE
```

This means the canonical repository contains the required active-V2 runner
interfaces but no reviewed tracked non-test executable composition that both
constructs the active runtime and invokes only `run_pre_release_read_phase_v2`.

The test suite is evidence of composition patterns only and is not a live
execution authority. Do not copy/adapt a test into an ad-hoc live launcher.

## 9. Next bounded action

The next source-code task is a narrowly reviewed implementation:

`R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01`

Its purpose is only to create the missing reviewed live composition for the
already-defined Stage 3A-3F read-only path.

It must call `run_pre_release_read_phase_v2`, not
`run_active_experiment_stage3_and_gate_d`, and terminate at
`LOCALLY_BLOCKED` or `READ_PHASE_COMPLETE`.

The implementation task must separately freeze exact writable paths,
protected paths, runtime callback composition, test seams, evidence packaging,
and capability limits.

After that implementation is reviewed and canonically installed, the D07
read-only Stage-3 preflight may use an operator-bound task-current ticker. The
historical C2 ticker above is not automatically reusable if freshness has
expired; selector final revalidation must be repeated when required.

## 10. Explicit non-claims / capability boundary

This checkpoint does not:

- authorize CREATE, CANCEL, TRANSFER, RELEASE_ONLY, NORMAL_WRITER, Gate D, or
  any other venue write;
- authorize production;
- authorize R1-D08;
- prove production market behavior;
- prove profitability;
- prove arbitrage;
- make Demo displayed liquidity production evidence;
- make any historical selected ticker a permanent strategy constant;
- make `is_provisional` false when the exact Demo target omitted it;
- make event-level `exchange_index` a market routing authority;
- turn external diagnostic scripts into canonical executable code.

Raw result JSON and diagnostic scripts remain external/local evidence identified
by exact bytes/SHA-256. This repository checkpoint is the sanitized continuity
carrier.
