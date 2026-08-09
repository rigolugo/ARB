# PROJECT_STATE

Authority level: canonical current-state snapshot.

This document records accepted state facts only. It does not authorize work and does not create authorization on its own. Historical authorization and decision details remain audit history; accepted task-specific specifications and evidence remain controlling only within their exact scope.

## 1. Repository identity

- Repository: `rigolugo/ARB`
- Visibility: public
- Default branch: `main`
- Exact canonical base used to prepare this state-hygiene update: `36d7d45bc68aa2e56bac74889d2ec9ffaa4eb6d6`
- Canonical `main` must always be reverified directly before a task relies on it.
- This file does not predeclare the commit SHA of the browser commit that may install this update.

## 2. Current accepted technical state

Current accepted state label:

`KALSHI_DEMO_AUTHENTICATED_REST_ORDER_BOOK_ACCEPTED__ONE_ORDER_LIFECYCLE_SPEC_REWORK_REQUIRED`

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
10. Kalshi Demo one-order lifecycle specification Revision 02 reviewed and blocked.

The project has **not** accepted or implemented the one-order lifecycle. No Demo order/write capability follows from the accepted authenticated read stage.

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

The implementation remains authenticated **read-only**. It contains no accepted order-create, cancel, fill-lifecycle, WebSocket, market-making, arbitrage, or production execution capability.

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

The raw OpenAPI identity:

`6e6402bf667da7596b5074ba1c687cdcb6e67f73903f49fd6b94f4b83a6a22de`

is an **exact historical source snapshot retrieved on 2026-08-08** and accepted only as provenance for the operations/reviews that explicitly bound it. Its presence in canonical state, source, or tests does not mean those bytes are the current Kalshi OpenAPI at a later time and does not automatically bind a new operation or write surface.

For a task that explicitly requires a current/fresh official source, the source must be obtained or directly observed during that task and identity-bound as required by the dispatch. A cached/retained repository snapshot may substitute only when the active Gustavo dispatch explicitly permits it. If required current bytes or identity cannot be established, the affected task halts.

Operation-specific source bindings do not generalize across endpoints. In particular, the accepted authenticated order-book binding does not establish Create Order V2, Get Orders, Get Order, Get Fills, or Cancel Order V2 semantics.

## 7. One-order lifecycle specification status

### Revision 01 — BLOCKED

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_01.md`

- raw bytes: `74426`
- SHA-256: `f19fa936044a513fc47b19a2a20b08ad116c5f7fef2d2fda8dc47dea97d0dbcf`

`HANDOFF_KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_01.md`

- raw bytes: `29007`
- SHA-256: `30c15019b7607fde4381eb9eba3d22dc6c85a2f98e90aff4d0090f41191f1341`

Marco blocking findings included:

- the claimed pre-create/no-active-order invariant was not proven by a pre-action venue-truth observation;
- the lifecycle write/read/fill/cancel source schema was not frozen tightly enough for Neo.

Revision 01 is not accepted and authorizes nothing downstream.

### Revision 02 — BLOCKED

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_02.md`

- raw bytes: `79944`
- SHA-256: `b318f444382851e15cfe2ddab70e77f36703aab9a4f55ca99b5da3050f53180f`

`HANDOFF_KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_02.md`

- raw bytes: `18095`
- SHA-256: `f10192b6c32f190ce88c7a2fbe676018a04bbefdc1ee68349754688b7f842f24`

Revision 02 corrected the pre-create venue-truth design and operation-binding structure but remained blocked because:

1. it reused the retained 2026-08-08 raw OpenAPI snapshot rather than establishing the task-current raw OpenAPI identity required by its exact dispatch; and
2. its `exclusive_writer_condition` remained insufficiently closed/implementable and did not fully exclude an unresolved prior same-scope write already in flight before the pre-create snapshot.

Revision 02 is not accepted and authorizes nothing downstream.

## 8. Current authorization state

This state document grants no capability.

Current technical/venue state after the completed authenticated read and the blocked lifecycle specifications:

- active technical implementation authorization: `NONE`;
- active venue execution authorization: `NONE`;
- active credential/signing authorization: `NONE`;
- Demo public/authenticated reads: `PROHIBITED` unless a new exact authorization permits them;
- Demo writes/orders/cancellations: `PROHIBITED`;
- production reads/writes: `PROHIBITED` unless separately and explicitly authorized;
- WebSockets: `PROHIBITED` unless separately and explicitly authorized;
- funding/trading: `PROHIBITED`;
- Polymarket activity in the current Kalshi workstream: `PROHIBITED` unless separately authorized.

Technical capability, installed cryptography support, prior successful authentication, or credential presence does not alter these permissions.

## 9. Next gated work

The next intended material design unit remains the same one-order lifecycle, but a new Revision 03 specification is **not automatically authorized** by this state update.

A future Gustavo authorization for Revision 03 should remain `SPEC_ONLY` and should correct the two remaining Revision-02 blockers without redesigning accepted direction:

1. bind a task-current official raw OpenAPI snapshot and regenerate/reconfirm all lifecycle operation bindings from that source; and
2. define a closed, implementation-independent no-competing-writer/no-unresolved-prior-write precondition that begins before the pre-create truth snapshot, identifies the proof/evidence owner, remains true through lifecycle termination, and fails closed when it cannot be established.

Only after Marco accepts an exact lifecycle specification may Gustavo separately consider a bounded offline Neo implementation task. No Demo write follows automatically from specification acceptance or implementation acceptance.

## 10. Local execution environment

Canonical local command and Windows/Miniconda conventions remain in:

`project_context/LOCAL_EXECUTION_ENVIRONMENT.md`

That document is operational context only and grants no capability.

## 11. Explicitly deferred / prohibited absent new authorization

- one-order implementation;
- any Demo order submission;
- any Demo cancellation;
- persistent ledger/restart recovery;
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
- Technical capability never substitutes for Gustavo authorization.
- No strategy is called arbitrage until all required legs are filled or otherwise contractually locked and the payout relationship has been verified at rule level.
