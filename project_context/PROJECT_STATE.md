# PROJECT_STATE

Authority level: canonical current-state snapshot.

This document records accepted state facts only. It does not authorize work and does not create authorization on its own. Historical authorization and decision details remain audit history; accepted task-specific specifications and evidence remain controlling only within their exact scope.

## 1. Repository identity

- Repository: `rigolugo/ARB`
- Visibility: public
- Default branch: `main`
- Exact canonical base used to prepare this state update: `5dca2d25df9c01fe1a1c1acfcfff5912bfdf5ec9`
- Exact canonical tree observed for that base: `783df783a832d5da745fa95d0aa62f35d0797bd2`
- Canonical `main` must always be reverified directly before a task relies on it.
- This file does not predeclare the commit SHA of any later documentation-transfer commit that may install this update.

## 2. Current accepted technical state

Current accepted state label:

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_IMPLEMENTATION_ACCEPTED_AND_INSTALLED__REAL_LIFECYCLE_EXECUTION_NOT_YET_PERFORMED`

Accepted milestones now include:

1. canonical documentation/bootstrap controls;
2. Kalshi Demo environment separation and capability envelope;
3. Kalshi Demo offline environment/capability validator;
4. manual browser temporary-branch repository-transfer workflow;
5. Kalshi Demo public unauthenticated connectivity preflight and one accepted bounded execution;
6. Kalshi Demo authenticated REST order-book specification;
7. accepted authenticated REST order-book Implementation 06 installed at canonical commit `36d7d45bc68aa2e56bac74889d2ec9ffaa4eb6d6`;
8. one accepted real authenticated Kalshi Demo REST order-book observation for one exact ticker;
9. Kalshi Demo one-order lifecycle specification Revision 01 reviewed and blocked;
10. Kalshi Demo one-order lifecycle specification Revision 02 reviewed and blocked;
11. later blocked one-order lifecycle predecessor lineage, including Revision 05, retained as historical blocked lineage;
12. Kalshi Demo one-order lifecycle specification Revision 06 accepted as the controlling lifecycle specification;
13. accepted one-order lifecycle implementation installed at canonical commit `5dca2d25df9c01fe1a1c1acfcfff5912bfdf5ec9` with exactly the two lifecycle paths recorded in Section 7.

The one-order lifecycle is technically accepted and installed. **No real one-order lifecycle execution has yet occurred.** Installation of write-capable code is not execution authorization and does not authorize a Demo order, cancellation, credential use, or any further venue request.

## 3. Accepted public connectivity predecessor

Installed connectivity implementation:

`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_IMPLEMENTATION_10`

Accepted implementation commit:

`a7fd2cc9668673cc11d1f3670d048ad87e3b4445`

Accepted implementation identities:

- `src/arb/venues/kalshi/connectivity.py`
  - raw bytes: `99628`
  - SHA-256: `b3235b33d14619ff34adb8f0de9b599d1b8aabdde1eee227b4906bac9695d544`
- `tests/test_kalshi_connectivity_preflight.py`
  - raw bytes: `143929`
  - SHA-256: `9e2a71e9bb801b790be40b8a96be46cf7ce5223218aeeb172ce48d66e7d37e15`

Controlling accepted specification:

`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_SPEC_03.md`

- raw bytes: `52179`
- SHA-256: `404f57009d1af2a4ff4cf345d482b4ab5c4be51f65cbd05c3a40af8a1d9b2235`

Accepted one-shot connectivity execution:

`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_EXECUTION_01`

- terminal result: `DEMO_REST_CONNECTIVITY_CONFIRMED`
- exact execution-evidence SHA-256: `9d1645a75ab507aecb8212ca8c144259e3208b7159b70889d85ac5757d68d417`
- environment: `KALSHI_DEMO`
- method/path: `GET /trade-api/v2/exchange/status`
- HTTP status: `200`
- request count: `1`
- retry count: `0`
- redirect count: `0`
- credentials/auth headers: `0`
- venue writes/orders/cancellations/funding: `0`

That execution authorization is consumed.

## 4. Accepted authenticated REST order-book specification and implementation

Accepted specification:

`KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION_SPEC_01.md`

- raw bytes: `61146`
- SHA-256: `ae8a57069a261c35c5a204d3358091c7ae3f0f9ddbe1cdbe6c8fb20f9250ead8`

Accepted handoff:

`HANDOFF_KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION_SPEC_01.md`

- raw bytes: `17316`
- SHA-256: `4ebbc45dba94a7074783abd44df760647bef5927431efa6f79ef8adbfcb96a63`

Accepted operation source-binding record:

- raw bytes: `1556`
- SHA-256: `295224b34fcd6adde7f54605388286e515b961eb512f631269fc2cbdd0544d0d`

Accepted reviewed raw OpenAPI snapshot for that predecessor review:

- source: `https://docs.kalshi.com/openapi.yaml`
- retrieved at: `2026-08-08T12:41:45Z`
- raw bytes: `323631`
- SHA-256: `6e6402bf667da7596b5074ba1c687cdcb6e67f73903f49fd6b94f4b83a6a22de`
- OpenAPI: `3.0.0`
- API info version: `3.27.0`

Installed implementation:

`KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION_IMPLEMENTATION_06`

Exact installed canonical commit:

`36d7d45bc68aa2e56bac74889d2ec9ffaa4eb6d6`

Accepted path identities:

- `pyproject.toml`
  - raw bytes: `210`
  - SHA-256: `993a3b8b2e20d56b31663757dbf8d79b47901f8cc79d89ad08af1e1ea56f783e`
- `src/arb/venues/kalshi/orderbook.py`
  - raw bytes: `109759`
  - SHA-256: `a692cb9858ee132eee9555fdd320ff59c3db7648e33e5696b89e221217c4230b`
- `tests/test_kalshi_authenticated_orderbook.py`
  - raw bytes: `136753`
  - SHA-256: `f7a78c5b342927eb5035cf0824ed316787d024a5b578ac6f81630d0137681591`

Canonical dependency added for this implementation:

`cryptography==49.0.0`

Accepted test evidence supplied during review:

- authenticated order-book tests: `288` passed;
- connectivity regression: `241` passed;
- combined targeted battery: `529` passed;
- full repository battery: `715` passed, `0` failed;
- no real network, real secret reads, Demo/production requests, WebSockets, orders, amendments, cancellations, funding, or trades during implementation testing;
- secret scan clean.

The predecessor authenticated order-book implementation remains accepted and authenticated **read-only**. Its prior accepted state is not displaced by the later lifecycle implementation.

## 5. Accepted real authenticated Demo order-book observation

Accepted execution task:

`KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_EXECUTION_01`

Observed and accepted facts:

- environment: `KALSHI_DEMO`;
- host: `external-api.demo.kalshi.co`;
- ticker: `KXFEDDECISION-26SEP-H0`;
- method: `GET`;
- path: `/trade-api/v2/markets/KXFEDDECISION-26SEP-H0/orderbook`;
- terminal result: `SUCCESS`;
- HTTP status classification: `200`;
- request count: `1`;
- retry count: `0`;
- redirect count: `0`;
- response byte length: `419`;
- response SHA-256: `2bc5099eff51a3f7f8b7c292a3114df177d6fb97b4604dfd7d67d4e8a14f1ceb`;
- canonical snapshot SHA-256: `a2989b451ecebddbc99441ba2ecd7f76eba4c6f818f0ae8c3ddcb496e8fa2bdc`;
- native YES bid levels reconstructed: `14`;
- native NO bid levels reconstructed: `3`.

This proves one bounded authenticated Demo REST observation only. It does not prove production connectivity, production credentials, WebSocket behavior, order placement, fills, cancellation, ledger correctness, profitability, market-making performance, or arbitrage.

The one-request execution authorization is consumed. No additional request may be inferred from it.

## 6. Source-binding scope and freshness state

The predecessor raw OpenAPI identity:

`6e6402bf667da7596b5074ba1c687cdcb6e67f73903f49fd6b94f4b83a6a22de`

is an **exact historical source snapshot retrieved on 2026-08-08** and accepted only as provenance for the operations/reviews that explicitly bound it. Its presence in canonical state, source, or tests does not mean those bytes are the current Kalshi OpenAPI at a later time and does not automatically bind a new operation or write surface.

Revision 06 separately binds the task-current official source snapshot retrieved `2026-08-09T13:00:42Z`:

- source: `https://docs.kalshi.com/openapi.yaml`;
- raw bytes: `333283`;
- SHA-256: `80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d`;
- OpenAPI: `3.0.0`;
- API info version: `3.27.0`;
- source identity record: `843` bytes / SHA-256 `10c88fbbbbcc017cd9ac8891cd89dc00c5df6c7ca49c5f8671c1121de695d22a`.

That source snapshot, source identity record, and the six Revision-06 operation bindings are immutable provenance for the accepted lifecycle contract. They are not standing authorization for future venue activity and do not by themselves establish freshness for a later task.

For a task that explicitly requires a current/fresh official source, the source must be obtained or directly observed during that task and identity-bound as required by that task. A cached/retained repository snapshot may substitute only when the active technical task explicitly permits it. If required current bytes or identity cannot be established, the affected task halts.

Operation-specific source bindings do not generalize across endpoints.

## 7. One-order lifecycle specification and implementation state

### Revision 01 — historical BLOCKED lineage

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_01.md`

- raw bytes: `74426`
- SHA-256: `f19fa936044a513fc47b19a2a20b08ad116c5f7fef2d2fda8dc47dea97d0dbcf`

`HANDOFF_KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_01.md`

- raw bytes: `29007`
- SHA-256: `30c15019b7607fde4381eb9eba3d22dc6c85a2f98e90aff4d0090f41191f1341`

The blocking findings included an unproven pre-create/no-active-order invariant and insufficiently frozen lifecycle write/read/fill/cancel source schema. Revision 01 remains historical blocked lineage and is not the controlling lifecycle specification.

### Revision 02 — historical BLOCKED lineage

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_02.md`

- raw bytes: `79944`
- SHA-256: `b318f444382851e15cfe2ddab70e77f36703aab9a4f55ca99b5da3050f53180f`

`HANDOFF_KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_02.md`

- raw bytes: `18095`
- SHA-256: `f10192b6c32f190ce88c7a2fbe676018a04bbefdc1ee68349754688b7f842f24`

Revision 02 corrected the pre-create venue-truth design and operation-binding structure but remained blocked because it did not establish the required task-current raw OpenAPI identity and its no-competing-writer/no-unresolved-prior-write precondition remained insufficiently closed. Revision 02 remains historical blocked lineage and is not the controlling lifecycle specification.

### Later blocked predecessors — historical lineage only

Revision 05 and other blocked predecessors remain historical blocked lineage. Their historical disposition is preserved; none is relabeled as accepted by this state update.

### Revision 06 — ACCEPTED controlling specification

Accepted specification:

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_06.md`

- raw bytes: `101724`
- SHA-256: `bb8355ad0022cda0d5ce936ed84993a381028187f207ae4b402f8017c9fbd101`

Accepted handoff:

`HANDOFF_KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_06.md`

- raw bytes: `13667`
- SHA-256: `a7cecc181001c0ef646da8a0c53bcbcb53e2cf4c8a2bb2a8b43386b4805e75d5`

Accepted review record provenance:

- raw bytes: `4166`
- SHA-256: `540dbbcb14fc66e39a268d405b331ed77dbcb3d6ccff3fc9b2a0f9ce9594c8b3`

Accepted Revision-06 operation-binding identities:

- `PRE_CREATE_ORDER_TRUTH`: `3844` bytes / SHA-256 `f51e23154d775b63a9a3de93bce4af97d368a2747de06fc020621e62496e1959`;
- `CREATE_ORDER_V2`: `3558` bytes / SHA-256 `03c319dfb9fcfd6c5a909c38f408ba27e48f83e0844ebed47fab7f306e9ff4f9`;
- `EXACT_ORDER_READ`: `3082` bytes / SHA-256 `ed5312101eddd9658f263d81aa7f41a28ca17e6d71dfd7b4c10b3610f5316792`;
- `ORDER_LIST_RECOVERY`: `3987` bytes / SHA-256 `e03e8bd348641521f84081bd350387c5eecd4e51b433eae2f99b949eef6a1989`;
- `FILL_READ`: `3260` bytes / SHA-256 `e421bc5ec7a8f65d97b335c7dd6b7e8c8475abb3f64b7f7f2ffba82f2c6b292d`;
- `CANCEL_ORDER_V2`: `2479` bytes / SHA-256 `4650e325f30a3cd177ad6b948f96dccb581c06585869a83a84e072a6066cde64`.

Accepted installed implementation commit:

`5dca2d25df9c01fe1a1c1acfcfff5912bfdf5ec9`

- parent: `a6a2bd1618011030eeadb410112a967bbbabcb07`;
- tree: `783df783a832d5da745fa95d0aa62f35d0797bd2`;
- browser commit message: `Python implementation Correction 06` (non-controlling metadata);
- accepted technical correction lineage for the installed bytes: Correction 05.

Installed path identities:

- `src/arb/venues/kalshi/order_lifecycle.py`
  - raw bytes: `181815`
  - SHA-256: `7ea14d6c4e90f1447eb33ee0df1b04cdb598723f06928eb6077d8449bbf1d133`
  - Git blob: `0d36a116458469d1436ceed55018c90c9e876a02`
- `tests/test_kalshi_one_order_lifecycle.py`
  - raw bytes: `250999`
  - SHA-256: `31be69106ec6aa4dc31493580d259dba608e011de6afb17fda1bc3e3ec031558`
  - Git blob: `f17ed92eef3460f023a9d5d4eccdf05c933f37dc`

Accepted offline validation evidence:

- observed dependency: `cryptography==49.0.0`;
- `python -m py_compile ...`: PASS;
- lifecycle suite: `413` passed;
- connectivity regression: `241` passed;
- authenticated order-book regression: `288` passed;
- combined lifecycle/connectivity/order-book battery: `942` passed;
- full repository discovery: `1128` passed;
- real Kalshi venue activity: `0`;
- real credential/private-key use: `0`;
- account access: `0`;
- real orders: `0`;
- real cancellations: `0`;
- WebSocket/production activity: `0`.

The installed implementation is capable of the bounded Kalshi Demo one-order lifecycle only when a separate valid execution input/transport and every runtime predicate required by Revision 06 are supplied. **No accepted real lifecycle execution has yet occurred.**

There is no accepted evidence yet of:

- successful Demo Create;
- an actual fill;
- an actual cancellation;
- live Create/Cancel ambiguity recovery;
- persistent ledger/restart recovery;
- market making;
- profitability;
- arbitrage;
- production behavior.

## 8. Current authorization / capability state

This state document grants no capability.

Current technical/venue state after installation of the accepted one-order lifecycle implementation:

- active venue execution authorization: `NONE`;
- active credential/signing authorization: `NONE`;
- Demo public/authenticated reads: `PROHIBITED` unless a new exact task permits them;
- Demo writes/orders/cancellations: `PROHIBITED`;
- production reads/writes: `PROHIBITED` unless separately and explicitly permitted;
- WebSockets: `PROHIBITED` unless separately and explicitly permitted;
- funding/trading: `PROHIBITED`;
- Polymarket activity in the current Kalshi workstream: `PROHIBITED` unless separately permitted.

Installation of write-capable code is not execution authorization. No capability is inherited merely because code exists on canonical `main`.

In particular:

- implementation presence does not authorize venue network access;
- credential presence does not authorize credential use;
- authenticated read does not authorize write;
- Create does not authorize Cancel;
- Demo does not imply production;
- no order or cancellation may be performed without a separate explicit execution decision and all runtime predicates required by Revision 06.

## 9. Next gated work

Any real Kalshi Demo one-order lifecycle execution is a separate gated task. The accepted specification and installed implementation do not themselves permit a venue request.

Before any such future execution, the task must separately establish the exact Revision-06 runtime predicates, including the required environment/capability envelope, credential-reference and signing boundaries, writer-exclusivity/prior-write proof, exact source/binding identities, bounded ticker/economics, request budgets/deadlines, and caller-supplied transport behavior.

No Demo Create, Cancel, credential use, or further venue read/write may be inferred from the present accepted installation state.

## 10. Local execution environment

Canonical local command and Windows/Miniconda conventions remain in:

`project_context/LOCAL_EXECUTION_ENVIRONMENT.md`

That document is operational context only and grants no capability.

## 11. Explicitly deferred / prohibited absent a separate task

- real one-order lifecycle execution;
- any Demo order submission;
- any Demo cancellation;
- any credential/private-key use;
- persistent ledger/restart recovery beyond the accepted in-memory implementation contract;
- emergency cancellation service;
- WebSocket connectivity/subscriptions;
- sequence-gap/reconnect handling;
- continuously maintained order books;
- multiple-market processing;
- strategy-driven discovery;
- market making;
- profitability accounting;
- logical arbitrage;
- Kalshi production observation;
- Polymarket adapter work;
- shadow execution;
- authenticated production canaries;
- live trading.

## 12. Standing safety interpretation

- Demo does not imply production.
- Public read does not imply authenticated read.
- Authenticated read does not imply write.
- Create does not imply cancel.
- Credential presence does not grant capability.
- Risk tier does not grant capability.
- A historical source hash does not imply current source freshness.
- An operation-specific source binding does not authorize or define a different operation.
- Environment or source ambiguity halts closed.
- Technical capability or installed code never substitutes for a separate explicit execution decision.
- No strategy is called arbitrage until all required legs are filled or otherwise contractually locked and the payout relationship has been verified at rule level.
