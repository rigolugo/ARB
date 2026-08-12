# PROJECT_STATE

Authority level: canonical current-state snapshot.

This document records accepted state facts only. It does not authorize work and does not create authorization on its own. Historical authorization and decision details remain audit history; accepted task-specific specifications and evidence remain controlling only within their exact scope.

## 1. Repository identity

- Repository: `rigolugo/ARB`
- Visibility: public
- Default branch: `main`
- Exact canonical base used to prepare this state update: `55b4ecaf5bc93978ee23bfd218cfe5ddba35bc49`
- Exact canonical tree observed for that base: `69df0e38d6830639fc3103ea95c41ceec65a5b2d`
- Canonical `main` must always be reverified directly before a task relies on it.
- This file does not predeclare the commit SHA of any later documentation-transfer commit that may install this update.

## 2. Current accepted technical state

Current accepted state label:

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_CONSUMED__POST_HALT_RECONCILIATION_EXECUTION_01_CONSUMED__WRITE_UNRESOLVED_ZERO_MATCH__WRITER_PROOF_HELD`

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
13. accepted one-order lifecycle implementation installed at canonical commit `5dca2d25df9c01fe1a1c1acfcfff5912bfdf5ec9` with exactly the two lifecycle paths recorded in Section 7;
14. `KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01` recorded by accepted external execution evidence (ART-0040): one bounded Kalshi Demo lifecycle attempt, terminal `FAIL_CLOSED_HALT` / `RECOVERY_ZERO_MATCH`, prior CREATE write result unresolved;
15. `KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_SPEC_01.md` accepted as the controlling read-only reconciliation specification (ART-0041/ART-0042); no implementation or venue execution authorized by the specification itself;
16. `KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_IMPLEMENTATION_01` accepted and installed at canonical commit `bbec7f203140312169af7db2f5c2936b58fbd6dd` (ART-0043/ART-0044); its implementation and offline validation performed no venue reconciliation;
17. `KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EXECUTION_01` recorded by accepted external execution evidence (ART-0045): its one authorized execution attempt is consumed, the bounded GET-only evidence collection succeeded, and the prior CREATE remains unresolved with result `WRITE_UNRESOLVED_ZERO_MATCH` and writer proof `HELD`.

Canonical `main` later advanced through `ARB_CODEX_IMPLEMENTER_STRUCTURE_01` at commit `7e43435397a6ca26b119b783f165cb6b30406a76` (tree `99b4c3b840d3fbf9f99c4c39b962cc07fdb3295c`, parent `bbec7f203140312169af7db2f5c2936b58fbd6dd`). That advance is tooling/workflow infrastructure only, not a technical phase transition, reconciliation evidence, venue evidence, or execution authorization.

The one-order lifecycle is technically accepted and installed. Accepted execution evidence records that `KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01` occurred with terminal disposition `FAIL_CLOSED_HALT` / `RECOVERY_ZERO_MATCH`, and that the separate `KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EXECUTION_01` was consumed as a bounded GET-only evidence collection with result `WRITE_UNRESOLVED_ZERO_MATCH`. The prior CREATE's write result remains unresolved — zero live-order and historical-order matches do not establish that the CREATE never existed. Writer proof remains `HELD` and release-ineligible. See Section 7 for exact evidence-qualified detail. No accepted result authorizes a further Demo order, cancellation, retry, second lifecycle, credential use, exploratory venue request, or production activity.

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

The installed implementation is capable of the bounded Kalshi Demo one-order lifecycle only when a separate valid execution input/transport and every runtime predicate required by Revision 06 are supplied. A real execution attempt using this implementation has now occurred; see the Execution-01 subsection below. Implementation and offline-test presence are not themselves execution evidence.

There is still no accepted evidence of:

- a successful Demo Create (the CREATE result remains unresolved, not proven successful);
- an actual fill;
- an actual cancellation;
- live Create/Cancel ambiguity recovery;
- persistent ledger/restart recovery;
- market making;
- profitability;
- arbitrage;
- production behavior.

### Execution 01 — accepted execution evidence (write result unresolved)

Accepted external execution evidence (ART-0040) for:

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01`

- evidence file: `execution_evidence.json`
- raw bytes: `10746`
- SHA-256: `2cb1677d06d3c88a3dd6f5b41190fa6de237bae24f02457fee37b2e0d04eefac`

Accepted project execution evidence records the following observed execution result. This section describes what the accepted evidence artifact records, not an independently observed Kalshi transaction:

- environment: `KALSHI_DEMO`; account scope: `ARB_KALSHI_DEMO_PRIMARY_ACCOUNT`; subaccount `0`;
- ticker: `KXFEDDECISION-26SEP-H0`; client order id: `2e64d452-2cc2-43fa-a976-e8f996192252`;
- execution authorization consumed: `true`; network used: `true`;
- 3 requests with send boundary entered:
  1. `PRE_CREATE_TRUTH` — `GET /trade-api/v2/portfolio/orders` — HTTP `200` — `DEFINITIVE_SUCCESS`;
  2. `CREATE` — `POST /trade-api/v2/portfolio/events/orders` — HTTP `400` — `DEFINITIVE_RESPONSE_AFTER_SEND`;
  3. `RECOVERY` — `GET /trade-api/v2/portfolio/orders` — HTTP `200` — `DEFINITIVE_SUCCESS`;
- the 74-byte CREATE response body is not retained in the accepted evidence; the application-level rejection reason is not known and is not inferred;
- terminal phase: `FAIL_CLOSED_HALT`; halt code: `RECOVERY_ZERO_MATCH`;
- the bounded recovery read observed zero matching orders; this does **not** prove the prior CREATE definitely had no server-side effect;
- `created_order_upper_bound = 1`; `active_order_upper_bound = 1`; `bound_order_id = null`; `unknown_result = true`;
- writer proof `KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_WRITER_PROOF`: state `HELD`, release eligible `false`;
- `create_send_may_have_begun = true`; `cancel_send_may_have_begun = false`; no Cancel was sent; no fill was established;
- retry count `0`; redirect count `0`; production activity `0`; funding activity `0`; WebSocket activity `0`;
- local one-shot runner `run_one_order_lifecycle.py` used for this execution is classified `local_only = true`, `committed_to_repository = false`, and is not indexed as a canonical repository artifact.

The correct current project state is that the CREATE write result is **unresolved**: neither "the CREATE definitely succeeded" nor "the CREATE definitely failed/never happened" is an accepted conclusion. Another one-order lifecycle Create or Cancel is **not authorized** while this write result remains unresolved.

### Accepted post-halt reconciliation specification

Accepted controlling next-stage specification (ART-0041):

`KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_SPEC_01.md`

- raw bytes: `69923`
- SHA-256: `61fd39b87d8b837e1a16b2b21cd133614f2607a3c21130682b53ace6ac4715e7`
- technical scope: `KALSHI_DEMO_POST_HALT_READ_ONLY_EXACT_WRITE_RESULT_RECONCILIATION`
- implementation performed by this artifact: `false`; venue execution performed or authorized by this artifact: `false`

Accepted handoff (ART-0042):

`HANDOFF_KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_SPEC_01.md`

- raw bytes: `17704`
- SHA-256: `ce6d3ef37339d118a0a390c69432833b50cedb3820017dbc66ef443934724a5e`

The specification's central accepted rule: zero exact `client_order_id` matches in a bounded reconciliation read is not proof that the prior CREATE definitely never existed. Under its task-current source contract the disposition remains `WRITE_UNRESOLVED_ZERO_MATCH` unless a later controlling official source establishes a sufficient negative consistency guarantee. The specification authorizes no implementation or venue execution by itself.

Accepted and installed implementation:

`KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_IMPLEMENTATION_01`

- exact installed canonical commit: `bbec7f203140312169af7db2f5c2936b58fbd6dd`;
- parent: `c2fc896ace102edc0f59450160f90000fc9be7f1`;
- tree: `26162b2667670db4039a4d1fa65ff0a95a9d0422`;
- `src/arb/venues/kalshi/write_result_reconciliation.py`: `104965` bytes / SHA-256 `2e7a53d2a1fad4b2c9d50e07b9e4fd99e5c0a08573adee123f27839b5929f678` / Git blob `0419108fe72cc96d7a0b94fc5c05aa99d929333e`;
- `tests/test_kalshi_write_result_reconciliation.py`: `58739` bytes / SHA-256 `6e9632f878d711e185e3e99251c7b79b78c8226d1c9f320b175f083ed2e0c59a` / Git blob `585869bd59cb82939da3c0ac75feeefd509bdf5a`.

Accepted installation-review validation evidence records: deterministic evidence test `1 passed`; reconciliation suite `140 passed`; targeted four-module regression `1082 passed`; full repository regression `1268 passed`; failures `0`. The implementation/test activity recorded Kalshi Demo requests `0`, Kalshi production requests `0`, real secret reads `0`, credential activity `NONE`, venue activity `NONE`, and write activity `NONE`. These are accepted project/manifest results and were not rerun by this documentation task.

Implementation installation itself performed no authenticated Demo reconciliation and grants no venue or credential capability.

### Accepted post-halt reconciliation execution

Accepted external execution evidence (ART-0045) for:

`KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EXECUTION_01`

- evidence file: `KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json`;
- raw bytes: `10541`; SHA-256: `a10eb4a6d7490755bbe055056cbe4960d075fd73048967d7e3d1c846c7be34fe`;
- frozen target: environment `KALSHI_DEMO`; account scope `ARB_KALSHI_DEMO_PRIMARY_ACCOUNT`; subaccount `0`; ticker `KXFEDDECISION-26SEP-H0`; client order id `2e64d452-2cc2-43fa-a976-e8f996192252`; writer proof `KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_WRITER_PROOF`;
- `authorization_consumed = true`; `overall_execution_attempts_authorized = 1`; `send_boundary_entered_count = 3`;
- request 1: public `GET /trade-api/v2/historical/cutoff`, HTTP `200`, retries `0`, redirects `0`;
- request 2: authenticated `GET /trade-api/v2/portfolio/orders` for the frozen ticker, subaccount `0`, limit `1000`, HTTP `200`, records observed `0`, cursor `TERMINAL_EMPTY`, retries `0`, redirects `0`;
- request 3: authenticated `GET /trade-api/v2/historical/orders` for the frozen ticker, limit `1000`, HTTP `200`, records observed `0`, cursor `TERMINAL_EMPTY`, retries `0`, redirects `0`;
- request count `3`; retry count `0`; redirect count `0`; no `EXACT_ORDER`, `LIVE_FILLS`, or `HISTORICAL_FILLS` request occurred because no order id was bound;
- result `WRITE_UNRESOLVED_ZERO_MATCH`; halt code `null`; exact client-order-id match count `0`; bound order id `null`;
- `created_order_upper_bound = 1`; `active_order_upper_bound = 1`; `unknown_result = true`;
- writer-proof continuity state `HELD`; writer-proof release eligible `false`;
- production activity `0`; write activity `0`; funding activity `0`; WebSocket activity `0`;
- secret values printed `false`; secret values persisted `false`.

The reconciliation execution succeeded as a bounded GET-only evidence collection, but it did **not** resolve the prior ambiguous CREATE. Zero live-order and historical-order matches do **not** prove that the CREATE never existed, so `WRITE_UNRESOLVED_ZERO_MATCH` remains unresolved. Execution 01 is consumed and must not be rerun. Writer proof remains `HELD` and release-ineligible. No CREATE, CANCEL, retry, second lifecycle, or exploratory venue request is authorized by this result, and no production capability or activity was established.

Execution-time public-source provenance recorded OpenAPI `3.0.0`, API info version `3.27.0`, `323714` bytes, SHA-256 `9b7708b12d33b3cb38bfe7b840b3e38399ecdc88a20a5791a674c39ac0304de8`. This is execution-time observation provenance only, not a standing freshness guarantee. The reviewed local runner SHA-256 was `e1e1d0a0665eb443336ec920546b415508bb8df721240e26a1360e1cdeee4c9f`; neither the runner nor the raw OpenAPI file is canonical repository source.

## 8. Current authorization / capability state

This state document grants no capability.

Current technical/venue state after installation of the accepted reconciliation implementation:

- active venue execution authorization: `NONE`;
- active credential/signing authorization: `NONE`;
- reconciliation implementation: `INSTALLED_ACCEPTED`;
- authenticated Demo reconciliation Execution 01: `CONSUMED`; accepted result `WRITE_UNRESOLVED_ZERO_MATCH`;
- writer proof: `HELD`; release eligible `false`;
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

The next technical design task is a separate SPEC-only fill-discovery binding fallback. Its planned existence does not mean that its specification is accepted, implemented, or executed, and does not authorize any venue request or other capability.

Another one-order lifecycle Create or Cancel is **not authorized** while Execution-01's write result remains unresolved (Section 7). Before any future lifecycle execution, the task must separately establish the exact Revision-06 runtime predicates, including the required environment/capability envelope, credential-reference and signing boundaries, writer-exclusivity/prior-write proof, exact source/binding identities, bounded ticker/economics, request budgets/deadlines, and caller-supplied transport behavior.

No Demo Create, Cancel, retry, second lifecycle, exploratory venue request, credential use, or further venue read/write may be inferred from the present accepted state.

## 10. Local execution environment

Canonical local command and Windows/Miniconda conventions remain in:

`project_context/LOCAL_EXECUTION_ENVIRONMENT.md`

That document is operational context only and grants no capability.

## 11. Explicitly deferred / prohibited absent a separate task

`KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01` has already occurred and its write result remains unresolved (Section 7). The items below remain prohibited absent a separate explicit task; for the lifecycle in particular this means no *additional* Create/Cancel attempt while the prior write is unresolved.

- another one-order lifecycle execution (Create/Cancel) while Execution-01's write result remains unresolved;
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
