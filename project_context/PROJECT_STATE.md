# PROJECT_STATE

Authority level: canonical current-state snapshot.

This document records accepted state facts only. It does not authorize work and does not create authorization on its own. Historical authorization and decision details remain in `AUTHORIZATION_LOG.md` and `DECISION_LOG.md`; accepted task-specific specifications and evidence remain controlling only within their exact scope.

## 1. Repository identity

- Repository: `rigolugo/ARB`
- Visibility: public
- Default branch: `main`
- Exact canonical base used to prepare this state/environment update: `a7fd2cc9668673cc11d1f3670d048ad87e3b4445`
- Canonical `main` must always be reverified directly before a task relies on it.
- This file does not predeclare the commit SHA of the update that installs this file.

## 2. Current accepted phase

`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_ACCEPTED`

The following predecessor milestones remain accepted:

- documentation/bootstrap controls;
- Kalshi Demo environment separation and capability-envelope specification;
- Kalshi Demo offline environment/capability validator;
- browser-branch repository-transfer workflow;
- Kalshi Demo read-only connectivity specification Revision 03;
- Kalshi Demo read-only connectivity Implementation 10;
- one separately authorized Kalshi Demo public unauthenticated connectivity execution with reconciled evidence.

This phase proves only the bounded Demo public read-only connectivity contract described below. It does not establish authenticated access, WebSocket correctness, order-book correctness, order/fill behavior, production safety, trading authorization, profitability, or arbitrage.

## 3. Accepted connectivity implementation

Installed implementation:

`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_IMPLEMENTATION_10`

Exact installed commit:

`a7fd2cc9668673cc11d1f3670d048ad87e3b4445`

Accepted implementation path identities:

- `src/arb/venues/kalshi/connectivity.py`
  - raw bytes: `99628`
  - SHA-256: `b3235b33d14619ff34adb8f0de9b599d1b8aabdde1eee227b4906bac9695d544`
- `tests/test_kalshi_connectivity_preflight.py`
  - raw bytes: `143929`
  - SHA-256: `9e2a71e9bb801b790be40b8a96be46cf7ce5223218aeeb172ce48d66e7d37e15`

Controlling accepted specification:

`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_PREFLIGHT_SPEC_03.md`

Exact accepted specification identity:

- raw bytes: `52179`
- SHA-256: `404f57009d1af2a4ff4cf345d482b4ab5c4be51f65cbd05c3a40af8a1d9b2235`

## 4. Accepted official source binding

Official REST source reviewed for the connectivity execution:

`https://docs.kalshi.com/openapi.yaml`

Reviewed raw OpenAPI identity:

- raw bytes: `323631`
- SHA-256: `6e6402bf667da7596b5074ba1c687cdcb6e67f73903f49fd6b94f4b83a6a22de`

Connectivity operation source-binding record:

- operation: `GET /exchange/status`
- effective security source: `NONE_DECLARED`
- classification: `PUBLIC_UNAUTHENTICATED_READ_ONLY`
- record raw bytes: `758`
- record SHA-256: `fe4baba81344d46ac3c548e86ce0db854d050357ed2012afdd5a7fa1692a9e97`

The `/exchange/status` source binding is operation-specific and must not be reused as authentication authority for another REST operation.

## 5. Accepted connectivity execution evidence

Execution task:

`KALSHI_DEMO_READ_ONLY_CONNECTIVITY_EXECUTION_01`

Terminal result:

`DEMO_REST_CONNECTIVITY_CONFIRMED`

Exact execution-evidence SHA-256:

`9d1645a75ab507aecb8212ca8c144259e3208b7159b70889d85ac5757d68d417`

Accepted execution facts:

- environment: `KALSHI_DEMO`
- method: `GET`
- full path: `/trade-api/v2/exchange/status`
- HTTP status: `200`
- DNS verification: `VERIFIED`
- resolver returned addresses: `2`
- verified DNS addresses: `2`
- selected address family: IPv4
- selected numeric address: `44.228.125.77`
- no prohibited address: confirmed
- no hostname re-resolution: confirmed
- TLS verification: `VERIFIED`
- negotiated TLS: `TLSv1.3`
- caller-visible elapsed time: `844 ms`
- overall execution deadline: `10000 ms`
- request count: `1`
- retry count: `0`
- redirects followed: `0`
- credentials read: `0`
- auth headers sent: `0`
- production requests: `0`
- Polymarket requests: `0`
- WebSocket connections: `0`
- writes: `0`
- orders: `0`
- cancellations: `0`
- funding actions: `0`
- authorization provenance mode: `EXTERNAL_GUSTAVO_ORCHESTRATION`
- runtime authorization provenance proof: `NOT_PERFORMED_BY_DESIGN`

`exchange_active=true` and `trading_active=true` were status observations only. They grant no trading or write capability.

The one-shot execution authorization is consumed and no additional request may be inferred from it.

## 6. Order-book authentication classification

A subsequent Bruno SPEC_ONLY attempt targeted a public unauthenticated one-market REST order-book reconstruction.

Bruno correctly halted with:

`OFFICIAL_SOURCE_CONFLICT`

for:

`GET /trade-api/v2/markets/{ticker}/orderbook`

Current official narrative material conflicted:

- the Get Market Orderbook operation reference marks Kalshi authentication headers required;
- the Orderbook Responses guide states that no authentication is required.

Marco accepted the halt and resolved the project classification by binding the exact reviewed OpenAPI operation-level security declaration.

Project classification:

`GET /trade-api/v2/markets/{ticker}/orderbook = AUTHENTICATED_READ_ONLY`

This resolves the classification question only. It does not authorize authenticated access, credential use, signing, or an order-book request.

The prior public-unauthenticated REST order-book specification authorization produced no specification or handoff artifact and cannot be reused.

## 7. Local execution environment

Canonical local-execution conventions are recorded separately in:

`project_context/LOCAL_EXECUTION_ENVIRONMENT.md`

That file is operational context only and grants no capability.

Current default local context includes:

- Microsoft Windows;
- Miniconda / Conda;
- default project Conda environment: `pmresearch`;
- CPython 3.12 target;
- Python execution commands formatted for `cmd.exe`;
- PowerShell available for verification, hashing, Git diagnostics, filesystem work, and separately authorized installations;
- explicit Windows LF/CRLF controls and exact Git/blob/byte/SHA-256 verification for byte-sensitive tasks.

## 8. Current authorization state

- Active technical implementation authorization: `NONE`.
- Active venue execution authorization: `NONE`.
- Active credential/signing authorization: `NONE`.
- Production access: `PROHIBITED` unless separately and explicitly authorized.
- Polymarket access in the current Kalshi workstream: `PROHIBITED` unless separately and explicitly authorized.
- Demo writes/orders/cancellations/funding/trading: `PROHIBITED` unless separately and explicitly authorized.
- The accepted connectivity execution authorization has been consumed.
- No later phase is authorized merely by the accepted connectivity result or by this state record.

## 9. Next gated technical work

The next intended material technical unit is a new Bruno SPEC_ONLY task for:

`ONE_MARKET_KALSHI_DEMO_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION`

The specification may describe the authentication/signing boundary required for a later Demo authenticated read, but the specification-drafting task itself must not:

- read credentials;
- construct a live signer;
- call the Kalshi Demo API;
- call Kalshi production;
- connect WebSockets;
- submit/amend/cancel orders;
- access funding;
- trade;
- implement source code;
- execute tests.

Any later implementation requires a separate Gustavo authorization after Marco accepts the specification.

Any later authenticated Demo execution requires a separate activity-specific Gustavo authorization after the implementation is accepted and installed.

## 10. Explicitly deferred

Unless separately authorized, the following remain deferred:

- authenticated Demo execution;
- WebSocket connectivity;
- WebSocket subscriptions and order-book deltas;
- sequence-gap handling and reconnect recovery;
- continuously maintained order books;
- multiple-market processing;
- market discovery for strategy selection;
- order lifecycle;
- fills;
- persistent ledger;
- restart recovery;
- emergency cancellation;
- risk limits;
- market making;
- profitability accounting;
- logical arbitrage;
- Kalshi production observation;
- Polymarket adapter work;
- shadow execution;
- authenticated production canaries;
- live trading.

## 11. Standing safety interpretation

- Demo does not imply production.
- Public read does not imply authenticated read.
- Read does not imply write.
- Credential presence does not grant capability.
- Risk tier does not grant capability.
- Environment ambiguity halts closed.
- Technical capability never substitutes for Gustavo authorization.
- No strategy is called arbitrage until required legs are filled or otherwise contractually locked and the payout relationship has been verified at rule level.
