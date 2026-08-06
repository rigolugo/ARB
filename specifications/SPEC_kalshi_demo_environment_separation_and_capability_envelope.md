# Kalshi Demo Environment Separation and Capability Envelope Specification

**Artifact:** `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`  
**Candidate identity:** `KALSHI_DEMO_ENVIRONMENT_SEPARATION_AND_CAPABILITY_ENVELOPE_SPEC_CANDIDATE_02`  
**Candidate:** `CANDIDATE_02`  
**Revision:** 02  
**Authorization ID:** `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01`  
**Task classification:** `DOCUMENTATION_GOVERNANCE_AND_SPEC_ONLY_BOUNDED_CORRECTION`  
**Authorization date:** 2026-08-06  
**Authoring agent:** Bruno  
**Review authority:** Marco  
**Approval authority:** Gustavo  
**Lifecycle at delivery:** `SUBMITTED_FOR_MARCO_REVIEW`  
**Canonical effect:** none  
**Implementation authorization:** none  
**Neo authorization:** none

---

## 1. Title, candidate identity, revision, and lifecycle

This document is Candidate 02 of the Kalshi Demo environment-separation and capability-envelope specification.

It is an external review candidate. It is not accepted, canonical, installed, installable, implementation-authorizing, or evidence of any venue access. It does not prove that any endpoint, credential, request, order, configuration, safety control, or trading behavior works.

The candidate is frozen at delivery with lifecycle:

`SUBMITTED_FOR_MARCO_REVIEW`

Delivery does not constitute Marco review or Gustavo acceptance. Any byte change after identity binding requires a new candidate identifier allocated through the project’s accepted governance process.

### 1.1 Blocked predecessor and bounded correction

Candidate 02 is one bounded correction to blocked Candidate 01. Candidate 02 was derived from these exact frozen predecessor artifacts:

| Blocked predecessor artifact | Raw byte length | SHA-256 |
|---|---:|---|
| `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md` | `75847` | `b8147c989852350bcd02cbc3cf5f18374f50a12a3a3ca140373dab9885431735` |
| `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_01.md` | `11277` | `948a6986bbb9ea72cf30dfa767957b5ab4b203f153a7cf01fedf0892bfca906d` |

Both predecessor identities matched exactly before drafting. Any mismatch would have halted Candidate 02 with no candidate artifacts created.

Candidate 02 corrects only:

1. candidate identity, filenames, authorization identity, revision, lifecycle references, and predecessor/correction descriptions mechanically required for Candidate 02;
2. the official Fixed-Point Representation source location in Section 7.6;
3. traceability entry `T-009`; and
4. explicit treatment of the displayed `Last Updated: August 20, 2026` value relative to the 2026-08-06 review baseline.

All other normative decisions are semantically preserved from blocked Candidate 01. No unrequested redesign is introduced.

---

## 2. Status and authority

### 2.1 Operative authorization

The operative authorization is:

`GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01`

This is a new, distinct, bounded correction authorization for Candidate 02. It does not retroactively authorize, validate, accept, canonicalize, install, or make installable blocked Candidate 01.

It authorizes Bruno to prepare exactly two external Markdown review candidates:

1. `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_02.md`
2. `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_02.md`

It does not amend historical authorization records retroactively and does not reopen the accepted repository bootstrap.

### 2.2 Candidate-authoring capability matrix

| Capability | Status | Exact boundary |
|---|---|---|
| Network access | `PERMITTED` | Read-only canonical `rigolugo/ARB`; exact blocked Candidate 01 artifacts; current official Fixed-Point Representation page; bounded official-source verification needed only to confirm the corrected URL and displayed metadata |
| Kalshi Demo public market-data reads | `PROHIBITED` | No venue request |
| Kalshi Demo authenticated reads | `PROHIBITED` | No venue request |
| Kalshi Demo writes | `PROHIBITED` | No mutation |
| Kalshi production public reads | `PROHIBITED` | No venue request |
| Kalshi production authenticated reads | `PROHIBITED` | No venue request |
| Kalshi production writes | `PROHIBITED` | No mutation |
| Polymarket reads | `PROHIBITED` | No venue request |
| Polymarket writes | `PROHIBITED` | No mutation |
| Credential use | `PROHIBITED` | No API key or signing operation |
| Private-key loading or parsing | `PROHIBITED` | No credential-file access |
| Credential-file reads | `PROHIBITED` | No credential-file access |
| Credential creation or derivation | `PROHIBITED` | No key generation or derivation |
| Account creation | `PROHIBITED` | No venue account activity |
| Account funding | `PROHIBITED` | No funds activity |
| Balance or portfolio access | `PROHIBITED` | No authenticated venue read |
| Order submission | `PROHIBITED` | No order activity |
| Order amendment | `PROHIBITED` | No order activity |
| Order cancellation | `PROHIBITED` | No order activity |
| Paper trading | `PROHIBITED` | No simulated venue interaction |
| Live trading | `PROHIBITED` | No trading |
| Code changes | `PROHIBITED` | Specification only |
| Implementation-source authoring | `PROHIBITED` | Specification only |
| Test-source authoring | `PROHIBITED` | Specification only |
| Test execution | `PROHIBITED` | No tests run |
| Project imports | `PROHIBITED` | No project execution |
| Package installation | `PROHIBITED` | No package changes |
| Shell or subprocess execution | `PROHIBITED` | No shell or subprocess work |
| Local research-data access | `PROHIBITED` | No research dataset read |
| Empirical execution | `PROHIBITED` | No empirical run |
| Repository path changes | `PROHIBITED` | No repository modification |
| Branches | `PROHIBITED` | No branch creation or update |
| Repository commits | `PROHIBITED` | No commit |
| Pull requests | `PROHIBITED` | No pull request |
| Canonical installation | `PROHIBITED` | Candidate remains external |
| Artifact generation | `PERMITTED` | Only the two named Markdown candidates and their raw-byte/SHA-256 reporting |

Anything not explicitly `PERMITTED` is `PROHIBITED`.

---

## 3. Canonical baseline and current accepted state

### 3.1 Repository baseline verified before drafting

| Attribute | Required value | Observed value | Result |
|---|---|---|---|
| Repository | `rigolugo/ARB` | `rigolugo/ARB` | match |
| Visibility | public | public | match |
| Default branch | `main` | `main` | match |
| Canonical `main` | `e35d56dda77819f0066447e18a0a2dc5bac2bb88` | `e35d56dda77819f0066447e18a0a2dc5bac2bb88` | match |
| Accepted bootstrap implementation commit | `e136be0b80f0370572e889d1075a11fc1b445348` | parent and accepted implementation recorded canonically | match |
| Current phase | `DOCUMENTATION_BOOTSTRAP_COMPLETE` | `DOCUMENTATION_BOOTSTRAP_COMPLETE` | match |

No canonical-baseline halt was triggered.

### 3.2 Required canonical read order completed

The following canonical records were read at exact canonical commit `e35d56dda77819f0066447e18a0a2dc5bac2bb88`, in order:

1. `START_HERE.md`
2. `project_context/START_HERE.md`
3. `project_context/GUARDRAILS.md`
4. `project_context/PROJECT_STATE.md`
5. `project_context/AUTHORIZATION_LOG.md`
6. `project_context/DECISION_LOG.md`
7. `project_context/AGENT_ROLES.md`
8. the accepted-candidate identity table in the canonical authorization chain
9. `specifications/SPEC_repository_bootstrap.md`
10. `reviews/REVIEW_repository_bootstrap_spec.md`
11. `handoffs/HANDOFF_repository_bootstrap_spec.md`
12. `handoffs/HANDOFF_repository_bootstrap_implementation.md`
13. relevant `project_context/ARTIFACT_INDEX.md` entries
14. exact blocked `SPEC_kalshi_demo_environment_separation_and_capability_envelope_CANDIDATE_01.md`
15. exact blocked `HANDOFF_kalshi_demo_environment_separation_and_capability_envelope_spec_CANDIDATE_01.md`
16. authorization `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01` and Marco’s Candidate 01 blocking decision
17. current official `Fixed-Point Representation` page at `https://docs.kalshi.com/getting_started/fixed_point_migration`

Acceptance-closure facts referenced by the canonical state, authorization, decision, and artifact records were also followed without modification.

### 3.3 Bound current-state facts

The specification binds these facts without modifying them:

- Candidate 10 repository-bootstrap specification: accepted.
- Candidate 10 repository-bootstrap implementation: accepted.
- Accepted implementation commit: `e136be0b80f0370572e889d1075a11fc1b445348`.
- Acceptance-closure canonical `main`: `e35d56dda77819f0066447e18a0a2dc5bac2bb88`.
- Current phase: `DOCUMENTATION_BOOTSTRAP_COMPLETE`.
- Active technical implementation authorization: none.
- Kalshi Demo reads and writes: prohibited unless separately authorized.
- Kalshi production reads and writes: prohibited.
- Polymarket reads and writes: prohibited.
- No prior Kalshi Demo environment-separation specification authorization existed when the bootstrap closure was installed.
- The current Gustavo dispatch is the separate bounded Candidate 02 drafting authorization.

---

## 4. Objective

Define the smallest complete, implementation-neutral contract for structural separation of:

- Kalshi Demo and Kalshi production;
- unauthenticated public REST reads and authenticated reads;
- Kalshi Demo writes and production writes;
- task authorization and technical capability;
- non-secret configuration validation, secret loading, transport construction, and venue requests.

The first later implementation derived from this specification shall be able to validate a complete Kalshi Demo configuration without:

- opening a credential file;
- loading or parsing a private key;
- constructing an HTTP client;
- constructing a WebSocket client;
- signing a request;
- opening a socket;
- following a redirect;
- sending a REST request;
- opening a WebSocket;
- or making any venue call.

The specification is successful only if production access cannot arise from omission, defaults, fallback behavior, generic credentials, custom endpoints, compatibility-host fallback, reused namespaces, reused transport objects, universal clients, or authorization inferred from capability.

---

## 5. Non-goals and out-of-scope activities

Candidate 02 does not specify, authorize, implement, test, or execute:

- authentication implementation;
- request signing implementation;
- credential loading;
- connectivity;
- market discovery;
- REST requests;
- WebSocket connections;
- market-data acquisition;
- order-book reconstruction;
- orders, amendments, or cancellations;
- fills, positions, settlements, or balances;
- persistence ledgers;
- strategies;
- market making;
- arbitrage detection;
- cross-venue matching;
- Polymarket integration;
- paper trading;
- live trading;
- funding;
- profitability analysis;
- package or framework selection;
- source code;
- test code;
- repository changes;
- branches, commits, pull requests, or installation.

No deferred requirement in this document grants permission to begin that work.

---

## 6. Source hierarchy and conflict rule

Material conclusions use this precedence:

1. canonical `rigolugo/ARB` guardrails and accepted records;
2. authorization `GUSTAVO_KALSHI_DEMO_ENVIRONMENT_SEPARATION_SPEC_ONLY_CANDIDATE_02_01`;
3. current official Kalshi REST OpenAPI specification location;
4. current official Kalshi WebSocket AsyncAPI specification location;
5. current official Kalshi API documentation;
6. current official Kalshi API changelog;
7. official Kalshi SDKs as non-controlling examples only;
8. the five reviewed external repositories as non-normative architecture references and failure examples only.

No SDK, README, blog, code comment, external repository, search result, or prior conversation overrides official Kalshi specifications, official documentation, canonical guardrails, or the exact authorization.

Where official sources conflict, appear future-dated, are ambiguous, or cannot be version-bound:

- the conflict is recorded rather than silently resolved;
- the more restrictive interpretation controls;
- a typed `OFFICIAL_SOURCE_CONFLICT` halt applies if the conflict is material to the requested implementation capability;
- no endpoint, field, authentication rule, price behavior, or lifecycle behavior is invented.

---

## 7. Verified official-source baseline

Retrieval date for every item in this section: **2026-08-06**.

### 7.1 Environment separation and recommended endpoint profiles

Official source: **API Environments and Endpoints**, `https://docs.kalshi.com/getting_started/api_environments`.

Officially documented facts:

- Demo and production are separate environments.
- Credentials are not shared between them.
- Recommended production REST base: `https://external-api.kalshi.com/trade-api/v2`.
- Recommended Demo REST base: `https://external-api.demo.kalshi.co/trade-api/v2`.
- Recommended production WebSocket URL: `wss://external-api-ws.kalshi.com/trade-api/ws/v2`.
- Recommended Demo WebSocket URL: `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2`.
- Shared compatibility hosts are documented as also supported, but they are not allowlisted by Candidate 02.

Candidate 02’s normative conclusion is narrower than Kalshi’s general compatibility support: only the two recommended Demo endpoints are allowlisted for the first implementation. All production, shared, legacy, compatibility, and custom hosts are rejected.

### 7.2 Demo behavior

Official source: **Test In The Demo Environment**, `https://docs.kalshi.com/getting_started/demo_env`.

The official documentation describes Demo as using mock funds and states that Demo credentials are separate from production credentials. Candidate 02 treats Demo as a separate safety environment but does not treat Demo evidence as production evidence.

### 7.3 Authentication facts preserved but not implemented

Official sources:

- **Quick Start: Authenticated Requests**, `https://docs.kalshi.com/getting_started/quick_start_authenticated_requests`.
- **API Keys**, `https://docs.kalshi.com/getting_started/api_keys`.

The official documentation identifies the API-key ID, timestamp, and RSA-PSS signature headers and describes signing `timestamp + HTTP method + request path`, excluding query parameters. Candidate 02 records this only to classify authenticated capability and credential namespaces. Authentication and signing remain deferred and unauthorized.

### 7.4 WebSocket authentication

Official sources:

- **WebSocket Connection**, `https://docs.kalshi.com/websockets/websocket-connection`.
- **Quick Start: WebSockets**, `https://docs.kalshi.com/getting_started/quick_start_websockets`.

The official documentation states that the WebSocket connection itself requires authentication, including when a subscribed channel carries public market data. Therefore Candidate 02 classifies every WebSocket transport as an authenticated-read capability at minimum. A `DEMO_PUBLIC_REST_READ` capability can never construct a WebSocket transport.

### 7.5 REST OpenAPI and WebSocket AsyncAPI

Official locations:

- REST OpenAPI: `https://docs.kalshi.com/openapi.yaml`.
- WebSocket AsyncAPI: `https://docs.kalshi.com/asyncapi.yaml`.

The official documentation index and SDK guidance identify these machine-readable specifications as controlling sources for client maintenance. The research interface exposed the official locations but did not expose a stable specification version or source commit in a directly inspectable response. Consequently:

- the locations are bound;
- no version or commit is invented;
- a future implementation handoff must retrieve and hash the then-current official documents before relying on schema details;
- inability to retrieve and bind them is `OFFICIAL_SOURCE_CONFLICT` for any schema-dependent implementation, but not for this non-network configuration-validation candidate.

### 7.6 Fixed-point price and quantity representation

Official source: **Fixed-Point Representation**, `https://docs.kalshi.com/getting_started/fixed_point_migration`.

The documentation describes fixed-point dollar strings for prices and `_fp` strings for quantities, and identifies per-market `price_ranges` as the valid price-grid source of truth. Candidate 02 therefore prohibits binary floating-point for monetary and exact quantity values and forbids hardcoded one-cent tick assumptions. It does not define the complete market-data economic type system.

At Candidate 02’s relevant review baseline date of 2026-08-06, the page displayed `Last Updated: August 20, 2026`. Because August 20, 2026 is later than the 2026-08-06 baseline, Candidate 02 treats the displayed date as a future-dated metadata anomaly or announced/future material, not proof that the described future behavior was already effective. A later implementation must revalidate the current official source before adoption.

### 7.7 Order direction and order-book behavior

Official sources:

- **Order direction (outcome_side and book_side)**, `https://docs.kalshi.com/getting_started/order_direction`.
- **Orderbook Responses**, `https://docs.kalshi.com/getting_started/orderbook_responses`.
- **Orderbook Updates**, `https://docs.kalshi.com/websockets/orderbook-updates`.

The documentation distinguishes outcome side from book side, describes fixed-point order-book levels, and shows WebSocket snapshot/delta messages carrying `sid` and `seq`. It also announces a future default change for `use_yes_price`. Candidate 02 does not implement order books; it preserves explicit direction, fixed-point, sequence, duplicate, gap, and pricing-convention requirements as deferred constraints.

### 7.8 Market hierarchy and lifecycle

Official sources:

- official API documentation index and market/event/series references;
- **Market Lifecycle**, `https://docs.kalshi.com/getting_started/market_lifecycle`.

The official model distinguishes series, events, and markets, and documents lifecycle states, pauses, reopening, determination, disputes, amendments, finalization, and lifecycle events. Candidate 02 does not normalize or implement these schemas. It requires future adapters to preserve venue-native identifiers and lifecycle meaning.

### 7.9 Orders, fills, positions, settlement, and reconciliation

Official sources include current API reference pages for order creation, order lookup, fills, positions, settlement, and historical records. The documented records include `client_order_id`, order status, fixed-point quantities, price-dollar fields, fee fields, and identifiers needed for later reconciliation.

Candidate 02 does not implement these endpoints. It preserves future mandatory controls for persistent idempotency, unknown-result handling, REST/WebSocket reconciliation, exactly-once fill processing, historical/live partition handling, and restart recovery.

### 7.10 Exchange status, pauses, order groups, and rate limits

Official sources:

- **Maintenance and Pauses**, `https://docs.kalshi.com/getting_started/maintenance_and_pauses`.
- **Rate Limits and Tiers**, `https://docs.kalshi.com/getting_started/rate_limits`.
- official exchange-status, schedule, and order-group references.

The documentation distinguishes trading pauses from exchange pauses, documents maintenance behavior, and describes separate authenticated read/write rate-limit budgets. Candidate 02 does not implement these controls, but it preserves them as future adapter requirements.

### 7.11 Historical-data partitioning

Official source: **Historical Data**, `https://docs.kalshi.com/getting_started/historical_data`.

The documentation states that live and historical records are partitioned by moving cutoff timestamps and that clients must route older data to historical endpoints. Candidate 02 preserves this as a future reconciliation constraint and forbids assuming a single live endpoint is complete history.

### 7.12 Changelog, deprecations, and announced future changes

Official source: **API Changelog**, `https://docs.kalshi.com/changelog`.

The changelog is required input for later implementation because fields, endpoints, pricing structures, and defaults change. On retrieval date 2026-08-06, the page also exposed entries dated 2026-08-13 and 2026-08-17. Candidate 02 treats those entries as announced future material, not current behavior. A later implementation must compare event date, publication date, current date, and the current OpenAPI/AsyncAPI before adoption.

### 7.13 Official-source conflict: public order-book authentication presentation

The conceptual **Orderbook Responses** page states that the REST market-orderbook endpoint requires no authentication. The generated API-reference presentation displayed authentication headers. Candidate 02 does not silently choose between these presentations.

Normative effect:

- `DEMO_PUBLIC_REST_READ` remains a structural capability category;
- Candidate 02 performs no request;
- a later connectivity or market-data specification must resolve the conflict against the current OpenAPI security declaration and a current official source snapshot;
- until resolved, constructing an actual public order-book transport is blocked with `OFFICIAL_SOURCE_CONFLICT`.

---

## 8. Terminology

| Term | Definition |
|---|---|
| Environment | Explicit venue deployment identity. Candidate 02 permits the model values `UNSET`, `KALSHI_DEMO`, and `KALSHI_PRODUCTION`; only `KALSHI_DEMO` can validate successfully in the first implementation. |
| Endpoint profile | Immutable pair of parsed REST and WebSocket base endpoints associated with one explicit environment. |
| Allowlist | Exact canonical component tuples accepted for a given environment and surface. It is not substring matching or DNS inference. |
| Requested capability | The narrow capability surface a caller asks the validator to authorize for later construction. |
| Task capability envelope | Complete, explicit task authorization record whose fields are only `PERMITTED` or `PROHIBITED`. |
| Constructed capability surface | The methods and transports that a future implementation can physically construct. |
| Active runtime capability | Intersection of requested capability, constructed surface, and exact task authorization. The most restrictive value controls. |
| Public REST read | A REST read defined by current official sources as unauthenticated. It excludes every WebSocket connection. |
| Authenticated read | A read requiring credential use, including every WebSocket connection under the current official documentation. |
| Demo write | A mutation capability against Kalshi Demo. It remains unauthorized by Candidate 02. |
| Production capability | Any public read, authenticated read, or write targeting Kalshi production. It exists in the model only for deterministic rejection in the first implementation. |
| Credential reference | A non-secret reference naming an environment-specific API-key identifier source or private-key path source. It never contains secret contents. |
| Validated Demo profile | Immutable, non-secret output proving only that configuration and task authorization passed this specification’s static checks. It is not a client, credential object, transport, request permission, or venue evidence. |
| Typed halt | Stable machine-readable failure code plus secret-safe metadata. |
| Placeholder | An obviously fake, blank, example, sentinel, or unresolved credential reference that must not pass validation. |
| Compatibility host | An officially documented shared or legacy host that is supported generally but intentionally not allowlisted by Candidate 02. |

---

## 9. Inputs and outputs

### 9.1 Required non-secret input

A validation attempt consumes exactly one `NonSecretConfigurationInput` containing:

- explicit environment value;
- explicit REST base endpoint;
- explicit WebSocket base endpoint;
- explicit requested capability;
- complete task capability envelope;
- environment-qualified credential references when and only when the requested capability requires credentials;
- explicit configuration schema revision;
- explicit source-baseline revision identifier for the endpoint allowlist;
- no secret values.

Missing, duplicate, contradictory, or aliased fields are invalid. Unknown fields that could affect environment, endpoint, credentials, or capability are invalid rather than ignored.

### 9.2 Successful output

Exactly one immutable `ValidatedDemoProfile` containing only:

- environment: `KALSHI_DEMO`;
- canonical Demo REST endpoint components;
- canonical Demo WebSocket endpoint components;
- requested capability;
- effective capability after intersection with authorization;
- non-secret credential-reference presence state where required;
- endpoint allowlist revision;
- capability-envelope identity or non-secret digest, if later authorized;
- validation schema revision;
- explicit statement that no secret was loaded and no transport was constructed.

Success does not create a client, credential object, signer, session, socket, redirect policy object, request, or cache entry with broader authority.

### 9.3 Failure output

Exactly one `TypedHalt` containing:

- primary halt code;
- stage at which validation stopped;
- safe configuration field name;
- safe expected classification;
- safe observed classification;
- contributing halt codes, if any;
- no secret value;
- no partial profile;
- no client, transport, signer, credential object, or cached capability.

A result cannot contain both a successful profile and a halt.

---

## 10. Data types and precision rules

### 10.1 Enumerated values

Environment values are closed:

- `UNSET`
- `KALSHI_DEMO`
- `KALSHI_PRODUCTION`

Requested capability values are closed:

- `DEMO_PUBLIC_REST_READ`
- `DEMO_AUTHENTICATED_READ`
- `DEMO_WRITE`
- `PRODUCTION_PUBLIC_REST_READ`
- `PRODUCTION_AUTHENTICATED_READ`
- `PRODUCTION_WRITE`

Authorization values are closed:

- `PERMITTED`
- `PROHIBITED`

Blank, null, inherited, omitted, implied, or unknown values are invalid. Boolean environment selection such as `demo=true` or `production=false` is prohibited.

### 10.2 URL representation

Endpoints are parsed as structured URL components. Validation never uses substring matching. The normalized comparison tuple is:

`(scheme, ASCII host, effective port, exact path, user-info-present, query-present, fragment-present)`

Host comparison is case-insensitive after parsing. Path comparison is case-sensitive and exact. DNS resolution is not part of validation.

### 10.3 Monetary and exact quantity representation

Binary floating-point is prohibited for:

- prices;
- quantities requiring exact venue precision;
- fees;
- balances;
- order values;
- fill values;
- settlement values;
- profit and loss;
- complementary-price derivations;
- incentives.

Future venue values use validated decimal strings or fixed-point integers with explicit scales. Candidate 02 does not define the complete economic type system.

### 10.4 Identifiers and hashes

- Git commits are exactly 40 lowercase hexadecimal characters when represented canonically.
- SHA-256 values are exactly 64 lowercase hexadecimal characters.
- Dates use `YYYY-MM-DD`.
- Datetimes, when later needed, include a timezone offset or `Z`.
- Capability-envelope identities must be non-secret and deterministic; their concrete serialization is deferred.

---

## 11. Assumptions

Candidate 02 assumes only:

1. The canonical repository facts in Section 3 remain true for this frozen candidate.
2. The official endpoint documentation retrieved on 2026-08-06 correctly identifies the recommended Demo and production endpoint profiles listed in Section 7.1.
3. A later implementation can use a standards-conforming URL parser without network access.
4. A later task authorization can supply a complete capability envelope independently of technical configuration.
5. Environment-qualified credential references can be identified without opening or parsing credential contents.
6. A future implementation can expose distinct capability construction paths rather than one universal client.
7. The current candidate’s output is a non-secret validation profile, not a venue client.

Any assumption that ceases to hold triggers revalidation or a typed halt; it does not justify fallback.

---

## 12. Explicit non-assumptions

Candidate 02 does not assume:

- production is the default;
- Demo is the default;
- `false` means production or `true` means Demo;
- endpoint hostname determines authorization;
- credentials determine environment;
- credential presence grants credential-use permission;
- credential-use permission grants network permission;
- network permission grants write permission;
- a public REST endpoint implies a public WebSocket connection;
- an SDK’s defaults are current or controlling;
- compatibility hosts are safe for a new integration;
- redirects preserve environment identity;
- similar market titles establish payout equivalence;
- successful response means an order filled;
- parallel requests are atomic;
- one-cent ticks are universal;
- fee formulas are static;
- live endpoints contain complete history;
- Demo evidence establishes production correctness, liquidity, or profitability;
- a validated configuration proves connectivity;
- Candidate 02 authorizes implementation or Neo.

---

## 13. Environment model

### 13.1 Explicit selection

Every running adapter configuration must contain one explicit environment value. There is no operational default.

- `UNSET` always halts with `ENVIRONMENT_UNSET`.
- Any unrecognized value halts with `ENVIRONMENT_UNKNOWN`.
- `KALSHI_PRODUCTION` halts with `PRODUCTION_ACCESS_PROHIBITED` in the first implementation stage.
- Only `KALSHI_DEMO` may progress.

### 13.2 Prohibited inference

Environment shall not be inferred from:

- hostname;
- credential variable name;
- account identity;
- branch name;
- command-line mode;
- dry-run flag;
- source-code build mode;
- default SDK configuration;
- previous successful validation;
- cached state;
- task history.

### 13.3 No fallback

After any environment validation failure:

- do not substitute Demo for production;
- do not substitute production for Demo;
- do not retry with another environment;
- do not fall back to a compatibility host;
- do not construct a reduced capability automatically;
- do not reinterpret write as read or authenticated read as public read.

Recovery requires corrected input and a new explicit validation attempt.

---

## 14. Endpoint-profile contract

### 14.1 First-stage Demo allowlist

#### REST

| Component | Allowed value |
|---|---|
| Scheme | `https` |
| Host | `external-api.demo.kalshi.co` |
| Effective port | `443` only; absent explicit port canonicalizes to 443 |
| Path | `/trade-api/v2` exactly |
| User information | absent |
| Query | absent |
| Fragment | absent |

#### WebSocket

| Component | Allowed value |
|---|---|
| Scheme | `wss` |
| Host | `external-api-ws.demo.kalshi.co` |
| Effective port | `443` only; absent explicit port canonicalizes to 443 |
| Path | `/trade-api/ws/v2` exactly |
| User information | absent |
| Query | absent |
| Fragment | absent |

### 14.2 Production profiles retained only for rejection

The following official recommended profiles are recognized solely so that a mismatch can be diagnosed deterministically:

- REST: `https://external-api.kalshi.com/trade-api/v2`
- WebSocket: `wss://external-api-ws.kalshi.com/trade-api/ws/v2`

Recognition does not authorize construction or network use.

### 14.3 Rejected hosts

The first implementation rejects:

- `https://api.elections.kalshi.com/trade-api/v2`;
- `https://demo-api.kalshi.co/trade-api/v2`;
- `wss://api.elections.kalshi.com/trade-api/ws/v2`;
- `wss://demo-api.kalshi.co/trade-api/ws/v2`;
- any custom URL;
- any IP literal;
- any deceptive subdomain;
- any host accepted only because it contains an allowed hostname as a substring;
- any host with a trailing dot;
- any Unicode or punycode host that is not exactly the allowlisted ASCII hostname after parsing.

### 14.4 URL safety rules

Validation shall reject:

- non-TLS schemes;
- user-info components;
- unexpected ports;
- empty hosts;
- path dot-segments;
- percent-encoded path separators or dot-segments;
- duplicate slashes in the path;
- trailing slashes not present in the exact allowlist;
- query strings;
- fragments;
- opaque URLs;
- scheme-relative URLs;
- relative URLs;
- whitespace or control characters;
- embedded credentials;
- multiple conflicting endpoint fields.

### 14.5 Endpoint/environment agreement

A syntactically valid endpoint known to belong to the other environment yields `ENVIRONMENT_ENDPOINT_MISMATCH`. It is never treated as a generic host error and never triggers environment inference.

Both REST and WebSocket endpoints must validate as one complete Demo endpoint profile even when the requested capability will initially use REST only. This prevents a dormant production or custom WebSocket endpoint from being carried into a validated profile.

### 14.6 Redirect policy

Configuration validation constructs no transport and follows no redirect.

In a later transport stage:

- automatic redirects must be disabled for base-endpoint requests;
- any redirect is a halt with `ENDPOINT_REDIRECT_PROHIBITED` in the first connectivity implementation;
- no redirected host, scheme, port, or path may be accepted implicitly;
- a later accepted amendment is required to permit a specific redirect policy.

---

## 15. Credential-namespace contract

### 15.1 Environment-qualified identifiers

The public configuration namespace shall use Demo-qualified identifiers, such as:

- `KALSHI_DEMO_API_KEY_ID`
- `KALSHI_DEMO_PRIVATE_KEY_PATH`

Exact public names may be refined by Marco before implementation, but the environment qualification is mandatory.

### 15.2 Prohibited identifiers and reuse

The validator rejects:

- `KALSHI_API_KEY`;
- `KALSHI_API_KEY_ID` when shared across environments;
- `KALSHI_PRIVATE_KEY`;
- `KALSHI_PRIVATE_KEY_PATH` when shared across environments;
- production-qualified references during Demo validation;
- aliases that resolve to generic or cross-environment namespaces;
- one credential object reused for Demo and production;
- credential content embedded directly in configuration.

### 15.3 Public-read rule

For `DEMO_PUBLIC_REST_READ`:

- credential use must be `PROHIBITED` in the task envelope;
- no credential reference is required;
- credential contents are never read;
- no authenticated reader or WebSocket surface can be constructed;
- supplying credential references to a public-only configuration is `CONFIGURATION_AMBIGUOUS` rather than an invitation to broaden capability.

### 15.4 Authenticated-read and Demo-write validation rule

For `DEMO_AUTHENTICATED_READ` or `DEMO_WRITE`, a later implementation may validate only the presence and environment qualification of credential references. It shall not open or parse the referenced file during configuration validation.

Required references must be:

- present;
- nonblank;
- Demo-qualified;
- non-placeholder;
- non-generic;
- non-production;
- represented outside displayable configuration objects as opaque references.

### 15.5 Placeholder policy

A reference is a placeholder if it is blank or uses an obvious unresolved marker, including angle-bracket examples, `CHANGEME`, `REPLACE_ME`, `EXAMPLE`, `PLACEHOLDER`, a tracked `.example` file, or an equivalent sentinel defined by the accepted implementation handoff.

Placeholder classification uses only the reference string and metadata; it does not open the file.

### 15.6 Secret-loading boundary

Private-key contents may be loaded only in a later separately authorized stage after all of these have succeeded:

1. canonical preflight;
2. official-source preflight;
3. non-secret configuration parse;
4. environment validation;
5. endpoint allowlist validation;
6. complete task capability-envelope validation;
7. requested-capability validation;
8. credential-namespace and reference validation;
9. secret-redaction policy establishment.

Candidate 02 does not authorize that later stage.

---

## 16. Capability-envelope contract

### 16.1 Required fields

Every task capability envelope contains every field below with exactly `PERMITTED` or `PROHIBITED`:

| Field |
|---|
| `network_access` |
| `demo_public_reads` |
| `demo_authenticated_reads` |
| `demo_writes` |
| `production_public_reads` |
| `production_authenticated_reads` |
| `production_writes` |
| `credential_use` |
| `account_funding` |
| `code_changes` |
| `tests` |
| `artifact_generation` |
| `repository_commits` |

No field may be blank, inherited, implied, omitted, carried forward, or computed from another task.

### 16.2 Intersection rule

For each capability:

`effective capability = requested capability ∩ constructed capability surface ∩ exact task authorization`

The most restrictive value controls. Technical capability never expands authorization.

### 16.3 Minimum authorization implications

These are necessary but not sufficient conditions:

| Requested capability | Required task fields |
|---|---|
| `DEMO_PUBLIC_REST_READ` | `network_access=PERMITTED`, `demo_public_reads=PERMITTED`, `credential_use=PROHIBITED` for actual request construction; static validation itself may run with `network_access=PROHIBITED` |
| `DEMO_AUTHENTICATED_READ` | `network_access=PERMITTED`, `demo_authenticated_reads=PERMITTED`, `credential_use=PERMITTED` for actual request construction |
| `DEMO_WRITE` | `network_access=PERMITTED`, `demo_writes=PERMITTED`, `credential_use=PERMITTED`; order-specific authorization remains separately required |
| Any production capability | Cannot be satisfied in the first implementation; `PRODUCTION_ACCESS_PROHIBITED` |

Configuration validation does not need network permission because it must not create or use transport. A future request constructor must re-evaluate the then-current task envelope rather than treating a validated profile as standing authorization.

### 16.4 Structural construction rule

The first implementation shall provide no constructible production reader or writer. Production capability types may exist only as rejected input values or inaccessible markers.

A Demo public-read surface shall not contain authenticated methods, WebSocket methods, or write methods.

A Demo authenticated-read surface shall not contain write methods.

A Demo-write surface shall be constructible only under an exact later task envelope with `demo_writes=PERMITTED`, and its construction remains outside Candidate 02 authorization.

A single universal write-capable client with caller promises is noncompliant.

---

## 17. Conceptual interfaces

These are behavioral records, not programming-language classes.

### 17.1 `EnvironmentSelection`

- one closed environment value;
- explicit source field name;
- no inferred or defaulted state.

### 17.2 `EndpointProfile`

- environment;
- REST parsed tuple;
- WebSocket parsed tuple;
- official-source retrieval date;
- allowlist revision;
- no transport object.

### 17.3 `EndpointAllowlist`

- exact accepted component tuples;
- exact recognized-but-prohibited production tuples;
- exact rejected compatibility hosts;
- source traceability;
- no DNS or network lookup.

### 17.4 `RequestedCapability`

- one closed capability value;
- explicit environment qualification;
- public/authenticated/write classification.

### 17.5 `TaskAuthorizationCapabilityEnvelope`

- all thirteen required capability fields;
- authorization ID;
- authorizing authority;
- task identifier;
- issue date;
- completion or expiration rule;
- no inherited fields.

### 17.6 `CredentialReference`

- environment classification;
- reference kind: API-key-ID source or private-key-path source;
- safe configured/missing/placeholder state;
- opaque source reference;
- no credential content;
- no displayable secret value.

### 17.7 `NonSecretConfigurationInput`

- environment;
- endpoints;
- requested capability;
- complete authorization envelope;
- optional environment-qualified credential references;
- schema and allowlist revisions;
- no secrets.

### 17.8 `ValidationResult`

A disjoint result:

- success with exactly one `ValidatedDemoProfile`; or
- failure with exactly one `TypedHalt`.

Never both.

### 17.9 `TypedHalt`

- stable halt code;
- validation stage;
- safe field name;
- safe classification metadata;
- contributing codes;
- redacted cause chain;
- no secret values.

### 17.10 `ValidatedDemoProfile`

- immutable;
- environment exactly `KALSHI_DEMO`;
- exact allowlisted endpoint tuples;
- requested and effective capability;
- non-secret credential-reference state;
- validation and allowlist revisions;
- explicit `secret_loaded=false`;
- explicit `transport_constructed=false`;
- explicit `network_request_sent=false`.

It is not serializable with credential contents because it never contains them.

---

## 18. Validation ordering and state machine

### 18.1 Deterministic validation sequence

1. Verify canonical repository and accepted-source prerequisites for the authorized implementation task.
2. Verify the official endpoint/source baseline required by that implementation task.
3. Parse non-secret configuration only.
4. Reject duplicate, contradictory, aliased, or unknown safety-relevant fields.
5. Require an explicit environment.
6. Validate the environment identifier.
7. Reject production selection for the Demo-only stage.
8. Parse REST and WebSocket endpoint values as URLs.
9. Canonicalize scheme, host, effective port, and path without DNS or network access.
10. Reject user information, queries, fragments, unsafe encodings, and malformed components.
11. Verify exact endpoint allowlisting.
12. Verify endpoint/environment agreement.
13. Parse every field in the task capability envelope.
14. Reject any missing or non-enumerated capability field.
15. Validate the requested capability value.
16. Reject every production capability.
17. Reject write capability unless the exact task permits Demo writes.
18. Compute the effective capability by intersection.
19. Identify the required credential namespace without reading secret contents.
20. Reject generic, production, cross-environment, or contradictory credential references.
21. Reject missing or placeholder references when credentials would be required.
22. Reject credential references for public-only capability as ambiguous broadening input.
23. Establish secret-redaction, safe-path, rendering, and nested-error policy.
24. Produce exactly one immutable non-secret `ValidatedDemoProfile`.
25. Stop. Secret loading, signing, transport construction, redirect handling, sockets, and requests remain inaccessible and unauthorized.

### 18.2 State machine

```text
RAW_NON_SECRET_INPUT
  -> NON_SECRET_PARSED
  -> ENVIRONMENT_VALIDATED
  -> ENDPOINT_PROFILE_VALIDATED
  -> CAPABILITY_ENVELOPE_VALIDATED
  -> REQUESTED_CAPABILITY_VALIDATED
  -> CREDENTIAL_REFERENCES_VALIDATED
  -> REDACTION_POLICY_ESTABLISHED
  -> VALIDATED_DEMO_PROFILE
```

Any failure transitions immediately to:

`HALTED_NO_PROFILE`

There is no transition from `HALTED_NO_PROFILE` to success within the same attempt. Recovery starts from `RAW_NON_SECRET_INPUT` with corrected input and a new explicit attempt.

### 18.3 Inaccessible deferred states

The following states shall not exist in Candidate 02’s implementation path:

- `SECRET_LOADED`
- `PRIVATE_KEY_PARSED`
- `SIGNER_CONSTRUCTED`
- `HTTP_CLIENT_CONSTRUCTED`
- `WEBSOCKET_CLIENT_CONSTRUCTED`
- `SOCKET_OPEN`
- `REQUEST_SENT`
- `REDIRECT_FOLLOWED`
- `VENUE_RESPONSE_RECEIVED`

---

## 19. Invariants

1. No environment default exists.
2. `UNSET` never runs an adapter.
3. Production selection cannot validate successfully in the first implementation.
4. Endpoint identity never grants authorization.
5. Credential presence never grants authorization.
6. A validated profile never grants standing network or write authority.
7. The effective capability never exceeds the constructed surface or exact task envelope.
8. Compatibility hosts are rejected even though official documentation lists them as supported.
9. Custom endpoints are rejected.
10. Endpoint matching uses parsed exact components, never substrings.
11. Both REST and WebSocket endpoint identities are validated before profile creation.
12. Every WebSocket capability is authenticated-read or stronger.
13. Public REST capability contains no credential, WebSocket, or write construction path.
14. Authenticated-read capability contains no write construction path.
15. Production readers and writers are unconstructible in the first implementation.
16. Demo writers are unconstructible when `demo_writes=PROHIBITED`.
17. No credential file is opened before all non-secret validation succeeds.
18. No transport object is created during configuration validation.
19. No network request occurs during configuration validation.
20. No failure returns a partial profile, client, transport, signer, credential object, or cached capability.
21. Secret values never enter logs, exceptions, representations, serialized output, snapshots, manifests, or artifacts.
22. Binary floating-point is never used for economic values.
23. Future persistent records carry explicit environment identity.
24. Future venue-native records retain original fields and provenance before normalization.
25. Similar names never establish cross-venue payout equivalence.
26. Parallel submission never establishes atomic execution.
27. Incentives are not counted until confirmed.
28. A two-leg trade is not locked arbitrage until required quantities are filled and payout relations are guaranteed.

---

## 20. Typed halts and precedence

### 20.1 Required halt codes

| Code | Exact semantics |
|---|---|
| `ENVIRONMENT_UNSET` | Environment missing, blank, null, or explicitly `UNSET`. |
| `ENVIRONMENT_UNKNOWN` | Environment token is not one of the closed values. |
| `ENVIRONMENT_NOT_AUTHORIZED` | Recognized nonproduction environment is outside the exact task authorization. |
| `ENDPOINT_MISSING` | Required REST or WebSocket endpoint field is absent or blank. |
| `ENDPOINT_MALFORMED` | URL cannot be safely parsed or contains user info, query, fragment, unsafe encoding, whitespace, control characters, relative/opaque form, or other malformed structure. |
| `ENDPOINT_SCHEME_PROHIBITED` | Scheme is not exact TLS scheme required for the endpoint surface. |
| `ENDPOINT_HOST_PROHIBITED` | Host is not allowlisted and is not a recognized other-environment endpoint used for a more specific mismatch halt. |
| `ENDPOINT_PORT_PROHIBITED` | Effective port is not 443. |
| `ENDPOINT_PATH_PROHIBITED` | Path is not the exact allowlisted path. |
| `ENDPOINT_NOT_ALLOWLISTED` | Parsed tuple is syntactically valid but absent from the exact allowlist after specific component checks. |
| `ENDPOINT_REDIRECT_PROHIBITED` | A later transport observes any redirect under the first connectivity policy. |
| `ENVIRONMENT_ENDPOINT_MISMATCH` | Endpoint is recognized as belonging to a different environment than the explicit selection. |
| `CREDENTIAL_NAMESPACE_MISMATCH` | Credential reference is generic, production-qualified, cross-environment, aliased, or otherwise inconsistent with Demo. |
| `CREDENTIAL_REFERENCE_MISSING` | Requested authenticated capability lacks a required non-secret credential reference. |
| `CREDENTIAL_PLACEHOLDER` | Required reference is blank, fake, example, sentinel, or unresolved. |
| `CAPABILITY_FIELD_MISSING` | Any required capability-envelope field is absent, blank, inherited, or invalid. |
| `CAPABILITY_NOT_AUTHORIZED` | Requested capability is not permitted by the exact task envelope after more specific production/write checks. |
| `PRODUCTION_ACCESS_PROHIBITED` | Environment or requested capability targets Kalshi production in the Demo-only stage. |
| `WRITE_CAPABILITY_PROHIBITED` | Requested Demo write capability is not explicitly permitted. |
| `SECRET_RENDERING_PROHIBITED` | Secret or credential content entered a log, error, representation, serialization, snapshot, manifest, or artifact path. |
| `CONFIGURATION_AMBIGUOUS` | Duplicate, contradictory, aliased, unknown safety-relevant fields, or credentials supplied to a public-only capability prevent one deterministic interpretation. |
| `OFFICIAL_SOURCE_CONFLICT` | Current official sources are materially conflicting, future-dated, stale, unavailable, or unversioned for the capability being implemented. |
| `CANONICAL_STATE_CONFLICT` | Canonical repository, guardrail, accepted-record, authorization, or exact-base state conflicts with the task. |

### 20.2 Primary precedence

The first applicable halt in this order is primary:

1. `CANONICAL_STATE_CONFLICT`
2. `OFFICIAL_SOURCE_CONFLICT`
3. `CONFIGURATION_AMBIGUOUS`
4. `ENVIRONMENT_UNSET`
5. `ENVIRONMENT_UNKNOWN`
6. `PRODUCTION_ACCESS_PROHIBITED` for explicit production environment selection
7. `ENVIRONMENT_NOT_AUTHORIZED`
8. `ENDPOINT_MISSING`
9. `ENDPOINT_MALFORMED`
10. `ENDPOINT_SCHEME_PROHIBITED`
11. `ENDPOINT_PORT_PROHIBITED`
12. `ENDPOINT_PATH_PROHIBITED`
13. `ENVIRONMENT_ENDPOINT_MISMATCH` for a recognized other-environment tuple
14. `ENDPOINT_HOST_PROHIBITED`
15. `ENDPOINT_NOT_ALLOWLISTED`
16. `CAPABILITY_FIELD_MISSING`
17. `PRODUCTION_ACCESS_PROHIBITED` for a production requested capability
18. `WRITE_CAPABILITY_PROHIBITED`
19. `CAPABILITY_NOT_AUTHORIZED`
20. `CREDENTIAL_NAMESPACE_MISMATCH`
21. `CREDENTIAL_REFERENCE_MISSING`
22. `CREDENTIAL_PLACEHOLDER`
23. `ENDPOINT_REDIRECT_PROHIBITED` in a later transport stage

A later generic error shall not hide an earlier specific safety condition. Additional applicable codes may be recorded as non-secret contributing codes.

### 20.3 Secret-exposure emergency override

If secret exposure is detected at any point, `SECRET_RENDERING_PROHIBITED` becomes the primary halt immediately. The prior primary code may be retained only as a safe `cause_code`. All exposed buffers, renderings, and nested exception text must be discarded or scrubbed; the secret itself must not be repeated in the halt.

### 20.4 No substitution

No halt may silently substitute:

- Demo for production;
- production for Demo;
- public reads for authenticated reads;
- authenticated reads for public reads;
- reads for writes;
- dry-run behavior for structural separation;
- compatibility hosts for recommended hosts;
- a reduced capability for the requested capability.

---

## 21. Failure and halt behavior

On any halt:

1. stop validation immediately after collecting only safe contributing metadata;
2. create no validated profile;
3. create no partial client, transport, signer, key object, credential object, or cached capability;
4. perform no fallback, retry, endpoint substitution, or environment substitution;
5. open no credential file;
6. make no network request;
7. emit one typed halt with the precedence rules in Section 20;
8. preserve no secret-bearing nested exception;
9. require corrected input and a new explicit attempt.

A canonical or official-source blocker stops before runtime configuration processing. A runtime configuration blocker stops before any secret or transport construction.

---

## 22. Secret-safe rendering, logging, and audit policy

### 22.1 Prohibited content

Secret or credential content shall never appear in:

- logs;
- exceptions;
- nested exceptions;
- `repr` or string conversion;
- debug output;
- serialized configuration;
- test snapshots;
- manifests;
- generated artifacts;
- telemetry;
- cache keys;
- process titles;
- filenames;
- environment dumps.

No candidate or placeholder may contain material resembling a usable private key.

### 22.2 Safe configuration states

Rendering may report only:

- `configured`;
- `missing`;
- `placeholder`;
- `not_required`.

It reports the safe field name and state, never the value.

### 22.3 Safe-path policy

Until Marco selects a later policy, credential paths may be reported only as:

- field name;
- presence state;
- optionally basename-only after explicit authorization.

Absolute paths, home directories, usernames, mount points, and directory structures are not logged by default.

### 22.4 API-key identifier policy

API-key identifiers are treated as sensitive configuration metadata. They are redacted. A non-secret fingerprint may be introduced only by a later accepted specification defining exact canonicalization, hashing, truncation, collision handling, and authorization.

### 22.5 Nested third-party errors

A future library error is untrusted. Before propagation or rendering, it must pass a secret scrubber and safe-field mapper. Raw library exceptions are never serialized directly.

### 22.6 Audit event fields

A non-secret validation audit event may include:

- validation schema revision;
- allowlist revision;
- task authorization ID;
- attempt timestamp;
- explicit environment classification;
- requested capability;
- effective capability;
- endpoint profile identifier, not arbitrary URL text;
- credential-reference states;
- success or halt code;
- assertions `secret_loaded=false`, `transport_constructed=false`, and `network_request_sent=false`.

Candidate 02 does not authorize creation or persistence of such logs.

---

## 23. Persistence and restart behavior

1. A validated profile is not persisted by default.
2. If a later task permits persistence, the stored record must contain explicit environment identity and no secret content.
3. A restart re-runs validation from non-secret input and the current exact task envelope.
4. A previous success is not standing authorization and cannot bypass current validation.
5. Cached profiles are invalid across authorization ID, source-baseline revision, endpoint-allowlist revision, or configuration revision changes.
6. Halted attempts persist no partial profile or capability.
7. Secret, signer, transport, and session objects are never serialized by this layer.
8. Recovery requires corrected input and a new explicit validation attempt.

---

## 24. Security boundaries

### 24.1 Repository boundary

The repository is public. Real credentials, key material, account identifiers, balances, private endpoints, signed URLs, venue responses, or sensitive runtime artifacts shall not be committed.

### 24.2 Configuration boundary

Tracked examples, if later authorized, must:

- have an unmistakable `.example` form;
- contain only obviously fake sentinel values;
- identify environment explicitly;
- never default to production;
- never enable writes;
- be rejected when placeholders remain.

Candidate 02 does not authorize creation of a tracked example file.

### 24.3 Secret boundary

Non-secret validation and secret loading are separate components and separate authorization gates. The validator receives references, never secret contents.

### 24.4 Transport boundary

Endpoint validation and transport construction are separate components and separate authorization gates. No reusable transport object is shared across Demo and production.

### 24.5 Adapter boundary

Kalshi-specific endpoints, signing, identifiers, direction fields, fixed-point parsing, lifecycle states, order/fill schemas, rate limits, and venue errors remain inside the Kalshi adapter. Shared economic types are used only for genuinely shared meaning.

### 24.6 Authorization boundary

Neither configuration nor technical capability creates permission. A request constructor must re-check the exact current task envelope immediately before any later authorized request.

---

## 25. Accepted external-repository findings

The following external repositories were supplied as reviewed non-normative sources:

| Repository | Reviewed commit |
|---|---|
| `Jonmaa/btc-polymarket-bot` | `35184491122c9d7720067db8cf0fec0f7189e3ef` |
| `ImMike/polymarket-arbitrage` | `7e4acc19aec11c770e9ce41c6c04634e24bfed39` |
| `tswaim/polymarket-kalshi-arbitrage-bot` | `6c4e9a1d562657b321f832a0d45ccda93389dfd3` |
| `TopTrenDev/polymarket-kalshi-arbitrage-bot` | `9fdf92d3ca6876312f6943af3414daf89ed65cdc` |
| `haoo99/Polymarket-Kalshi-Arbitrage-Bot` | `11a36ec4690044023c0869ea29111272ccc24e68` |

Only these surviving design findings inform Candidate 02:

1. Separate venue adapters from the economic core.
2. Preserve venue-native data and provenance before normalization.
3. Use exact decimal or fixed-point arithmetic.
4. Fail closed on environment selection.
5. Separate public-read, authenticated-read, Demo-write, and production capabilities structurally.
6. Validate environment, endpoint, authorization, capability, and reference safety before secrets or transports.
7. Carry explicit environment identity in future persistent records.
8. Do not infer market equivalence from names or labels.
9. Do not call parallel submission atomic.
10. Require future idempotency and reconciliation controls.

No source code is copied. No repository is imported as a dependency. No README claim is treated as evidence. No external repository is evidence of profitability, fills, atomic execution, contract equivalence, current fees, current endpoints, or production safety.

Source-code reuse from all five repositories is prohibited under Candidate 02. Missing, inconsistent, or non-file license status cannot be cured by inference.

---

## 26. Explicitly rejected patterns

The following are noncompliant:

- production selected when environment is absent;
- dry-run disabled when configuration is absent;
- Boolean environment models;
- one generic API-key namespace shared by Demo and production;
- one generic private-key namespace shared by Demo and production;
- endpoint overrides contradicting environment;
- endpoint selection by substring;
- custom URL overrides;
- compatibility-host fallback;
- validation after client construction;
- private-key loading before non-secret validation;
- one universal write-capable client;
- one transport reused between Demo and production;
- one ledger namespace reused between Demo and production;
- optional execution of only one required arbitrage leg;
- binary floating-point monetary arithmetic;
- title similarity as contract equivalence;
- successful API response as proof of fill;
- hardcoded fees as authoritative;
- hardcoded one-cent tick assumptions;
- cancellation or status stubs presented as completed controls;
- simulation or README output as profitability evidence;
- credentials in logs, errors, configuration rendering, artifacts, or snapshots;
- a public REST capability constructing an authenticated or WebSocket client;
- a read-only capability constructing a writer;
- a validated profile treated as authorization to send a request.

---

## 27. Future implementation test requirements and acceptance criteria

These requirements describe a later, separately authorized Neo implementation. Candidate 02 authors no tests and executes no tests.

### 27.1 Authorized test environments for the first implementation

Only these environments are appropriate for the configuration-validation implementation:

- local unit tests;
- mocked integration tests with instrumented fake filesystem, fake secret loader, fake HTTP factory, fake WebSocket factory, and network-deny guard.

Kalshi Demo, Kalshi production read-only, Polymarket read-only, shadow execution, and production trading are not required and are prohibited unless separately authorized.

### 27.2 Measurable acceptance criteria

1. Missing environment halts with `ENVIRONMENT_UNSET`.
2. Unknown environment halts with `ENVIRONMENT_UNKNOWN`.
3. Production selection halts with `PRODUCTION_ACCESS_PROHIBITED`.
4. Demo with the production REST endpoint halts with `ENVIRONMENT_ENDPOINT_MISMATCH`.
5. Demo with the production WebSocket endpoint halts with `ENVIRONMENT_ENDPOINT_MISMATCH`.
6. Demo with a compatibility, legacy, or arbitrary custom endpoint halts unless a later accepted amendment explicitly allowlists it.
7. Malformed URLs halt with `ENDPOINT_MALFORMED`.
8. Non-TLS URLs halt with `ENDPOINT_SCHEME_PROHIBITED`.
9. Unexpected ports halt with `ENDPOINT_PORT_PROHIBITED`.
10. Unexpected path prefixes halt with `ENDPOINT_PATH_PROHIBITED`.
11. Deceptive subdomains and substring matches are rejected.
12. URLs containing user information are rejected without rendering that information.
13. Redirects to non-allowlisted hosts cannot proceed; the first transport policy rejects every redirect.
14. Missing capability fields halt with `CAPABILITY_FIELD_MISSING`.
15. Demo public-read capability cannot construct an authenticated reader or WebSocket transport.
16. Demo read-only capability cannot construct a writer.
17. Production public reads cannot be constructed.
18. Production authenticated reads cannot be constructed.
19. Production writes cannot be constructed.
20. Generic credential variables are rejected with `CREDENTIAL_NAMESPACE_MISMATCH`.
21. Production credential variables are not consumed during Demo validation.
22. Missing credential references halt when the requested capability requires credentials.
23. Placeholder credential references halt.
24. No private-key file is opened before non-secret validation succeeds.
25. No private-key material is parsed before non-secret validation succeeds.
26. No HTTP client is created before validation succeeds, and configuration validation creates none even on success.
27. No WebSocket client is created before validation succeeds, and configuration validation creates none even on success.
28. No network request occurs during configuration-validation tests.
29. Secret contents do not appear in logs, errors, serialized output, snapshots, manifests, or artifacts, including nested exception paths.
30. Valid Demo configuration produces exactly one immutable validated Demo profile.
31. Validated output carries explicit `KALSHI_DEMO` identity.
32. Repeated validation of identical complete non-secret input and envelope is deterministic.
33. Duplicate equivalent non-secret input produces the same result; duplicate conflicting fields halt as ambiguous.
34. Failure is closed and produces no fallback profile.
35. Failure produces no partial client, transport, credential object, signer, profile, or cached capability.
36. Recovery requires corrected input and a new explicit validation attempt.
37. A public-only request containing credential references halts as `CONFIGURATION_AMBIGUOUS`.
38. Explicit port 443 canonicalizes consistently; every other explicit port halts.
39. Trailing-dot hosts, IP literals, percent-encoded path separators, path dot-segments, queries, and fragments halt.
40. A recognized production capability fails before credential-reference evaluation.
41. An unauthorized Demo write fails before credential-reference evaluation.
42. A secret-rendering incident yields `SECRET_RENDERING_PROHIBITED` as primary while retaining only a safe cause code.
43. No test imports or invokes a venue SDK.
44. Network-deny instrumentation reports zero DNS lookups, sockets, HTTP requests, and WebSocket handshakes.
45. The success profile states `secret_loaded=false`, `transport_constructed=false`, and `network_request_sent=false`.

### 27.3 Duplicate, malformed, and recovery expectations

- Identical repeated input: identical semantic result.
- Duplicate identical fields: rejected unless the concrete configuration parser guarantees they cannot exist; silent last-value wins is prohibited.
- Duplicate conflicting fields: `CONFIGURATION_AMBIGUOUS`.
- Malformed input: no partial parse is promoted to a profile.
- Recovery: new attempt only; no mutation of a halted result.

---

## 28. Deferred constraints — preserved, non-authorizing

Later specifications must address, but Candidate 02 neither specifies nor authorizes:

- venue-native fixed-point market-data parsing;
- market-specific `price_ranges` validation;
- explicit order direction and pricing convention;
- snapshot and delta sequence integrity;
- duplicate and gap handling;
- stale-book handling;
- depth-aware executable pricing;
- authoritative fee accounting and fee changes;
- persistent `client_order_id`;
- ambiguous mutation-result handling;
- exactly-once fill processing;
- REST and WebSocket reconciliation;
- live/historical partition reconciliation;
- restart recovery;
- complete market lifecycle preservation;
- exchange-pause and maintenance handling;
- emergency cancellation;
- risk caps;
- rule-level cross-venue payout audit;
- leg risk and non-atomic execution handling;
- authoritative profitability accounting;
- confirmed-incentive accounting;
- environment-qualified logs, ledgers, order intents, events, fills, and artifacts.

---

## 29. Unresolved questions requiring Marco’s decision

1. **Implementation language and exact paths.** The canonical repository does not yet select a language, framework, package manager, or source/test file paths. Marco must define exact repository-relative paths in a later implementation handoff; directory wildcards are insufficient.
2. **First constructed surface.** Marco must decide whether the first implementation exposes only the pure validator and validated-profile types, or also inaccessible factory interfaces for later public/authenticated/write clients. No transport factory may become operational under Candidate 02.
3. **Public order-book authentication conflict.** Before any public order-book connectivity work, Marco must require resolution against a retrieved, hashed current OpenAPI security declaration because the conceptual and generated-reference presentations conflict.
4. **Safe path rendering.** Marco must decide whether future errors may reveal credential basenames or only field-name/presence state. The default in Candidate 02 is field-name/presence only.
5. **Official specification binding.** A later schema-dependent handoff must specify how the current OpenAPI and AsyncAPI files are retrieved, hashed, retained, and compared without making them canonical project authority above official sources.
6. **Future-dated official material.** The fixed-point page at `https://docs.kalshi.com/getting_started/fixed_point_migration` displayed `Last Updated: August 20, 2026`, later than Candidate 02’s 2026-08-06 review baseline. This is treated as a metadata anomaly or announced/future material, not proof that future behavior was already effective. Marco must require revalidation of the current official source before adoption. The changelog’s future-dated entries retain the same restrictive treatment.
7. **Credential public names.** The examples `KALSHI_DEMO_API_KEY_ID` and `KALSHI_DEMO_PRIVATE_KEY_PATH` satisfy the namespace invariant, but Marco may select exact names before implementation.
8. **Capability-envelope serialization.** The exact deterministic serialization and identity method for a task envelope is deferred; the semantic fields and fail-closed completeness rule are fixed here.

None of these questions blocks Candidate 02 review. Items 1, 3, 4, and 5 block the affected later implementation handoff until Marco resolves them.

---

## 30. Blocking conditions

### 30.1 Candidate 02 drafting blockers

None observed. The canonical repository baseline matched exactly, the required read order was completed, and the recommended Demo endpoint sources were consistent.

### 30.2 Future implementation blockers

A later implementation must halt before source changes if any of the following applies:

- Candidate 02 is not identity-bound, reviewed by Marco, and explicitly accepted by Gustavo.
- No separate Gustavo implementation authorization exists.
- Marco has not issued a bounded implementation handoff with exact paths.
- Canonical `main` differs from the exact implementation base without an authorized new dispatch.
- A permanent guardrail would need amendment.
- The then-current official recommended Demo endpoint differs from Section 14.
- The current OpenAPI or AsyncAPI cannot be retrieved and bound when schema-dependent work is requested.
- A material official-source conflict remains unresolved.
- A requested language, framework, package, or path is not explicitly authorized.
- Production access, credential use, network access, or Demo write would be required without exact permission.
- The implementation cannot separate public read, authenticated read, Demo write, and production surfaces structurally.
- Secret-safe behavior cannot be guaranteed before third-party error rendering.
- Any source or test work would exceed the exact handoff.

---

## 31. Traceability matrix

| ID | Material fact or requirement | Official/canonical source and location | Retrieved | Version/identity | Normative conclusion | Ambiguity/limitation |
|---|---|---|---|---|---|---|
| T-001 | Canonical guardrails and phase | `project_context/GUARDRAILS.md`; `PROJECT_STATE.md` at `e35d56d...bb88` | 2026-08-06 | Git commit `e35d56dda77819f0066447e18a0a2dc5bac2bb88` | Demo/production separated; no active technical authorization | None for Candidate 02 |
| T-002 | Separate Demo/prod credentials and endpoints | API Environments and Endpoints | 2026-08-06 | Page version not published | Separate environments and namespaces | Page version unavailable |
| T-003 | Recommended Demo REST endpoint | API Environments and Endpoints; Demo Environment | 2026-08-06 | Page version not published | Allowlist `external-api.demo.kalshi.co/trade-api/v2` only | Compatibility host intentionally rejected |
| T-004 | Recommended Demo WS endpoint | API Environments and Endpoints; WebSocket API | 2026-08-06 | Page version not published | Allowlist `external-api-ws.demo.kalshi.co/trade-api/ws/v2` only | Compatibility host intentionally rejected |
| T-005 | RSA-PSS authenticated requests | Quick Start: Authenticated Requests; API Keys | 2026-08-06 | Page version not published | Authenticated capability requires key ID/private key reference; implementation deferred | Example code non-controlling |
| T-006 | WebSocket handshake authentication | WebSocket Connection; Quick Start: WebSockets | 2026-08-06 | AsyncAPI version not exposed | Every WS surface is authenticated-read or stronger | Channel-level “public” does not remove handshake auth |
| T-007 | REST schema source | `https://docs.kalshi.com/openapi.yaml` | 2026-08-06 | Version/commit not observable | Later schema work must retrieve and hash current file | Research interface did not expose stable version |
| T-008 | WS schema source | `https://docs.kalshi.com/asyncapi.yaml` | 2026-08-06 | Version/commit not observable | Later schema work must retrieve and hash current file | Research interface did not expose stable version |
| T-009 | Fixed-point prices/quantities and dynamic grids | **Fixed-Point Representation**, `https://docs.kalshi.com/getting_started/fixed_point_migration`; changelog | 2026-08-06 | Page displayed `Last Updated: August 20, 2026` | Decimal/fixed-point only; per-market grid later | Displayed date is later than the review baseline and is treated as a metadata anomaly or announced/future material; it does not make future behavior effective, and later implementation must revalidate the current official source before adoption |
| T-010 | Order direction | Order direction page | 2026-08-06 | Page version not published | Preserve outcome side/book side and explicit WS pricing flag later | Future default flip announced without current date |
| T-011 | Order-book snapshot/delta sequence | Orderbook Updates / AsyncAPI-rendered reference | 2026-08-06 | AsyncAPI version not exposed | Future sequence/gap/duplicate controls mandatory | Deferred in Candidate 02 |
| T-012 | Public order-book auth | Orderbook Responses vs generated API reference | 2026-08-06 | OpenAPI security declaration not directly bound | Connectivity blocked pending source resolution | Official presentation conflict |
| T-013 | Series/event/market hierarchy | Official API documentation index and references | 2026-08-06 | Page version not published | Preserve venue-native hierarchy and IDs | No complete model in Candidate 02 |
| T-014 | Market lifecycle | Market Lifecycle | 2026-08-06 | Page version not published | Preserve native lifecycle; no generic erasure | Lifecycle can change; changelog required |
| T-015 | `client_order_id`, order/fill fields | Current order and fill API references | 2026-08-06 | OpenAPI version not exposed | Future idempotency and reconciliation mandatory | Deferred |
| T-016 | Historical partition | Historical Data | 2026-08-06 | Cutoffs are runtime-moving | Never assume live endpoints are complete history | Runtime values not retrieved or authorized |
| T-017 | Maintenance and pauses | Maintenance and Pauses | 2026-08-06 | Page version not published | Future pause handling and emergency controls mandatory | No runtime status queried |
| T-018 | Read/write rate budgets | Rate Limits and Tiers | 2026-08-06 | Account tier is runtime-specific | Future adapter must model venue-specific limits | No account queried |
| T-019 | Fees and changes | API references and changelog | 2026-08-06 | Dynamic | Fees must be authoritative and version-aware | Candidate 02 does not define formulas |
| T-020 | Changelog/deprecations | API Changelog | 2026-08-06 | Current page contains future entries | Compare dates and specs; do not adopt future entries silently | Future-dated entries observed |
| T-021 | SDK precedence | Kalshi SDKs overview | 2026-08-06 | SDK releases vary | OpenAPI/AsyncAPI/docs control over SDK examples | SDKs non-controlling |
| T-022 | External repository findings | Five supplied reviewed commits | 2026-08-06 | Exact commits in Section 25 | Architecture lessons only; no code reuse | Non-normative; no profitability evidence |

---

## 32. Explicitly unauthorized follow-up work

After Candidate 02 delivery, the following remain unauthorized:

- repository installation;
- repository modification;
- branches, commits, pushes, pull requests, or issues;
- implementation-source authoring;
- test-source authoring;
- test execution;
- imports or package installation;
- shell or subprocess execution;
- credential creation, reading, loading, parsing, or use;
- HTTP or WebSocket client construction;
- DNS, sockets, REST, WebSocket, or venue calls;
- Kalshi Demo public or authenticated reads;
- Kalshi Demo writes;
- all Kalshi production activity;
- all Polymarket activity;
- account creation or funding;
- balance, portfolio, position, fill, or settlement access;
- orders, amendments, cancellations, paper trading, or live trading;
- market discovery or order-book work;
- ledger, strategy, arbitrage, or profitability work;
- automatic progression to any next phase;
- authorization of Neo.

---

## 33. Required boundaries for a later Neo implementation handoff

### 33.1 Current status

**DESCRIPTIVE ONLY — NEO NOT AUTHORIZED.**

Candidate 02 does not issue an implementation handoff. A later Marco handoff must be independently reviewed and posted under a separate Gustavo authorization.

### 33.2 Exact paths

Candidate 02 authorizes no repository paths.

A later handoff must enumerate every exact file to add or modify. It may not use broad directory permissions or say only “implement the specification.” Until Marco resolves Section 29 question 1, all repository paths remain prohibited.

### 33.3 Minimum components to identify

The later handoff must name the exact files and components implementing:

- closed environment selection;
- exact endpoint profile and allowlist;
- complete task capability envelope;
- requested capability and intersection logic;
- non-secret credential references;
- pure validation state machine;
- typed halts and precedence;
- secret-safe rendering policy;
- immutable validated Demo profile;
- local unit tests and mocked integration tests.

### 33.4 Prohibited paths and content

The later handoff must prohibit:

- canonical governance-document changes unless separately authorized;
- credential files;
- active `.env` files;
- private keys;
- real API-key identifiers;
- venue responses;
- runtime databases or ledgers;
- production endpoint enablement;
- Polymarket code;
- order, fill, strategy, or arbitrage code;
- any unlisted path.

### 33.5 Allowed commands and network activity

The later handoff must state exact allowed commands. For the pure validation implementation, expected network activity is `PROHIBITED`; dependency installation is also `PROHIBITED` unless separately justified and authorized.

### 33.6 Required tests

The handoff must map exact test files to Section 27 criteria and require a network-deny harness plus fake secret/transport factories. It must prohibit venue calls and real credential reads.

### 33.7 Expected outputs

At minimum:

- exact changed-path list;
- implementation commit or package identity only if separately authorized;
- test inventory;
- deterministic test results;
- proof of zero secret-file opens before validation;
- proof of zero transport construction and network activity in validation tests;
- proof that production and writes are unconstructible under prohibited envelopes;
- secret-pattern scan over authorized outputs;
- final workspace status.

### 33.8 Stop conditions

Neo must stop on any Section 30 blocker, path need outside the handoff, source conflict, guardrail conflict, baseline mismatch, dependency need outside authorization, secret exposure, or requirement for network/credential/venue activity.

### 33.9 Evidence returned to Marco

The evidence must identify:

- exact dispatch and authorization ID;
- exact base and observed HEAD;
- exact accepted specification identity;
- exact changed paths;
- commands used;
- tests run and results;
- all negative-capability evidence;
- zero-network result;
- zero-secret-read result;
- no production construction result;
- no Demo-write construction result unless explicitly authorized;
- final artifact identities;
- blockers or readiness for Marco review.

No next phase begins automatically.

---

## 34. Completion conditions

Candidate 02 is complete when:

1. the canonical baseline is verified;
2. the canonical read order is completed;
3. official endpoint sources are traced;
4. environment, endpoint, credential, and capability contracts are explicit;
5. validation ordering and state transitions are deterministic;
6. halt codes and precedence are exact;
7. secret-safe behavior is specified;
8. measurable future acceptance criteria are defined;
9. unresolved questions and blockers are explicit;
10. deferred constraints remain non-authorizing;
11. the paired Bruno handoff reports this specification’s exact raw byte length and SHA-256;
12. both frozen candidates are delivered to Marco with lifecycle `SUBMITTED_FOR_MARCO_REVIEW`.

Requested Marco decision: `APPROVE`

This request is not Bruno approval. Marco’s review does not by itself authorize implementation, installation, venue access, credentials, or Neo.
