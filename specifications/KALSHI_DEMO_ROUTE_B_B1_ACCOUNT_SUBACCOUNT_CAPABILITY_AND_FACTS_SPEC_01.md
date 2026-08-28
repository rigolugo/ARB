# KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01

## 0. Artifact metadata

```yaml
artifact_class: TECHNICAL_SPECIFICATION
task_id: KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01
classification: SPEC_ONLY
route: ROUTE_B
stage: B1
scope: KALSHI_DEMO_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_READ_ONLY_SPECIFICATION
risk_tier: MEDIUM
implementation_not_performed_by_this_artifact: true
venue_execution_not_performed_by_this_artifact: true
```

This document specifies the smallest authenticated Kalshi Demo read-only account/subaccount capability-and-facts probe needed to choose the next Route-B branch. It is a technical contract for a later separately bounded implementation and execution. It does not itself grant implementation, credential use, venue access, or any write capability.

Normative keywords `MUST`, `MUST NOT`, `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are used in their ordinary requirements sense.

---

## 1. Canonical repository and exact authoring base

### B1-BASE-001 — repository identity

The canonical repository is exactly:

```text
rigolugo/ARB
```

Default branch:

```text
main
```

The exact canonical state independently observed for this specification authoring task is:

```text
canonical_main   = a0d7f324b7c49b6f2bfc7b586843ab77172cbe17
canonical_tree   = 9f5b5c413ffb6f7cb901a3a68654143617461155
canonical_parent = 997954197ebb8cbfb13baa3231b490abfbe20f64
```

Implementation against another base is prohibited unless a later technical task explicitly retargets this specification and revalidates all protected dependencies and source assumptions. No silent advance, rebase, or later-main substitution is permitted.

### B1-BASE-002 — repository activity performed by this artifact

This specification task performs no repository write and no Git write. Repository inspection is read-only.

---

## 2. Controlling technical inputs and provenance

The following exact supplied artifacts are controlling technical inputs for this specification:

| Artifact | Raw bytes | SHA-256 |
|---|---:|---|
| `02_CURRENT_ACCEPTED_STATE/PROJECT_STATE_CHECKPOINT_2026_08_27_MANUAL_RESTING_CANCEL_CANARY.md` | 6709 | `1cc4ab2d90f9190fe90020197adf5220a049d47370230f0801efe41fb1493a80` |
| `03_CONTROLLING_INPUTS/KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02.md` | 93365 | `b081feeee22d051d0f3f89b271e8029ab077d819512272df19b2151f5a254395` |
| `03_CONTROLLING_INPUTS/HANDOFF_KALSHI_DEMO_MANUAL_RESTING_ORDER_CANCEL_POSITIVE_CANARY_SPEC_01_CORRECTION_02.md` | 19475 | `ab31ad493b16be42d35c0dd912726506b347e5cc111987a29dc3d1c5314b0d81` |
| `03_CONTROLLING_INPUTS/KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md` | 68568 | `512000eea8db5562768682ae1659c03c20a2b5093fba68ef37eae784039a8336` |
| `03_CONTROLLING_INPUTS/HANDOFF_KALSHI_DEMO_GATE_D_REAL_EXECUTION_SUBSTRATE_AND_WRITER_ELIGIBILITY_SPEC_01.md` | 15390 | `57a37e444afcf0706adcc5f4f09bb280dc04c46a2fff8b4e678f6aead2dbaac8` |

The following supplied artifact is historical source context only, not proof of current official-source freshness:

```text
04_HISTORICAL_SOURCE_CONTEXT/openapi_3_28_0_predecessor_snapshot.yaml
raw_bytes = 333315
sha256    = cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b
OpenAPI   = 3.0.0
info.version = 3.28.0
```

The supplied external-interface research memo and external-research ledger are non-controlling research/evidence context unless a finding is explicitly adopted by a numbered requirement in this specification.

---

## 3. Current accepted state that B1 cannot change

### B1-STATE-001 — held primary domain remains held

B1 MUST preserve the current accepted theorem exactly:

```text
historical primary domain =
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0

writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

No B1 observation, including discovery of another subaccount, changes or weakens this theorem.

### B1-STATE-002 — conflict-domain theorem remains controlling

B1 MUST preserve:

```text
same account/subaccount + different ticker != separate domain
different process != separate domain
different local database != separate domain
different ledger/authority namespace != separate domain
manual browser mechanism != separate domain
restart != separate domain
```

Subaccount `0` MUST NOT be classified as a clean separate domain.

---

## 4. B1 purpose and exact questions

B1 answers only the following questions:

```text
Q1. What current Demo account Predictions API usage tier and relevant grant
    metadata are exposed by the authoritative authenticated read surface?

Q2. Is the exact API key used for B1 unrestricted across subaccounts,
    restricted to one exact subaccount, or not exposed/provable?

Q3. Which exact subaccount numbers are exposed by the selected authoritative
    read-only subaccount surfaces?

Q4. Do the independently selected account-wide subaccount surfaces agree on
    the enumerated subaccount identities?

Q5. Is at least one numbered subaccount (>0) exposed?

Q6. If a numbered subaccount exists, what facts are proven and what facts
    remain unproven about clean inception, history, exposure, and readiness?

Q7. If only primary subaccount 0 is exposed, can B1 conclude only
    NO_CURRENT_NUMBERED_SUBACCOUNT_OBSERVED without inferring creation
    capability or permission?

Q8. Does the current source and read-only evidence prove usable
    CreateSubaccount capability for this account/key? If not, creation
    capability remains NOT_PROVEN_BY_B1_READ_ONLY_FACTS.
```

### B1-SCOPE-001 — no history expansion

Orders, fills, positions, settlements, transfers, and broad account history are outside B1. Complete history for a preexisting candidate domain belongs to later Route-B work.

### B1-SCOPE-002 — transfer listing excluded

`GET /portfolio/subaccounts/transfers` is explicitly `OUT_OF_SCOPE_FOR_MINIMAL_B1`.

---

## 5. Fresh official-source binding used for this specification

### B1-SRC-001 — source class and observation

Fresh official source was observed from `docs.kalshi.com` on:

```text
source_observation_completed_at_utc = 2026-08-27T20:02:16Z
fresh_source_class = OFFICIAL_RENDERED_DOCUMENTATION
```

The browser representation could render the relevant official HTML/text pages. A direct attempt to retrieve `https://docs.kalshi.com/openapi.yaml` did not yield usable raw YAML bytes in the available authoring environment; therefore this specification MUST NOT claim a current raw OpenAPI byte identity, OpenAPI version, API `info.version`, or current operation IDs.

```text
fresh_raw_openapi_status = NOT_OBTAINED
fresh_openapi_version = NOT_EXPOSED_BY_RENDERED_SOURCE
fresh_api_info_version = NOT_EXPOSED_BY_RENDERED_SOURCE
fresh_operation_ids = NOT_EXPOSED_BY_RENDERED_SOURCE
representation_confidence = LOWER_THAN_RAW_OPENAPI
```

This limitation is a provenance limitation, not by itself an official-source conflict.

### B1-SRC-002 — exact fresh source URLs

The fresh source set is exactly:

```text
https://docs.kalshi.com/api-reference/account/get-account-api-limits
https://docs.kalshi.com/api-reference/api-keys/get-api-keys
https://docs.kalshi.com/api-reference/portfolio/get-all-subaccount-balances
https://docs.kalshi.com/api-reference/portfolio/get-subaccount-netting
https://docs.kalshi.com/getting_started/subaccounts
https://docs.kalshi.com/api-reference/api-keys/create-api-key
https://docs.kalshi.com/api-reference/portfolio/create-subaccount
https://docs.kalshi.com/getting_started/api_environments
https://docs.kalshi.com/llms.txt
```

No non-Kalshi site controls the B1 endpoint contract.

### B1-SRC-003 — fresh rendered operation projection

Fresh rendered source establishes the following B1 projection:

| B1 operation label | Method | Exact path | 200 body relied-on top-level field(s) | Pagination |
|---|---|---|---|---|
| `B1_GET_ACCOUNT_LIMITS` | `GET` | `/account/limits` | `usage_tier`, `read`, `write`, `grants` | none exposed |
| `B1_GET_API_KEYS` | `GET` | `/api_keys` | `api_keys` | none exposed |
| `B1_GET_SUBACCOUNT_BALANCES` | `GET` | `/portfolio/subaccounts/balances` | `subaccount_balances` | none exposed |
| `B1_GET_SUBACCOUNT_NETTING` | `GET` | `/portfolio/subaccounts/netting` | `netting_configs` | none exposed |

The rendered source describes balances as applying to all subaccounts including primary, and netting as applying to all subaccounts. The rendered subaccounts guide describes subaccount `0` as primary and numbered subaccounts as `1` through `63`.

No query parameters and no request bodies are permitted for these four B1 requests.

### B1-SRC-004 — current subaccount and restricted-key semantics

The fresh subaccounts guide establishes, for the B1 source projection:

```text
primary subaccount = 0
numbered subaccounts = 1..63
balances and positions are partitioned into independent buckets within one
Direct account
```

It also states that an API key can be restricted to one subaccount, that restricted keys cannot manage subaccounts or API keys, and that endpoints outside the restricted key's allowed set return a specific 403 restriction error.

Fresh Create API Key documentation establishes for the **create request**:

```text
subaccount field range = 0..63
request field omitted => newly created key unrestricted
request field set to integer N => newly created key restricted to N
```

That request-body rule does not by itself prove the omission/null semantics of the `subaccount` field returned later by `GET /api_keys`. The fresh rendered Get API Keys page available to this authoring task did not expose that child-field semantic. Therefore this authoring source binding records:

```text
GET_API_KEYS_RESPONSE_SUBACCOUNT_ABSENCE_SEMANTICS = NOT_EXPOSED_BY_FRESH_RENDERED_SOURCE
```

The historical OpenAPI 3.28.0 described absent/null in the `ApiKey` response object as unrestricted, but that historical statement is corroborating context rather than task-current proof. A future B1 execution MUST NOT convert an absent or null response field to `UNRESTRICTED` unless its task-current official source binding explicitly establishes that response semantic.

### B1-SRC-005 — Create Subaccount source conflict disposition

The supplied research memo recorded an earlier rendered-documentation observation of `1–32` / institution-market-maker framing. Fresh rendered official documentation observed for this specification now states:

```text
Create Subaccount documented tier rule = Advanced API tier and above
numbering = sequential from 1
maximum numbered subaccounts = 63
```

That fresh rendered representation aligns on these points with the retained OpenAPI 3.28.0 snapshot. Therefore:

```text
unresolved_official_source_conflict_for_tier_and_numbering = NONE_OBSERVED
historical_representation_conflict = NOT_REPRODUCED_ON_2026-08-27
```

However, because B1 is read-only and does not exercise `POST /portfolio/subaccounts`, the B1 capability theorem remains:

```text
CREATE_SUBACCOUNT_CAPABILITY = NOT_PROVEN_BY_B1_READ_ONLY_FACTS
```

Even when a returned usage tier is `advanced` or above, documentation-level tier eligibility is not proof that the exact account/key can or may successfully perform the write.

### B1-SRC-006 — Demo environment binding

The only permitted future B1 venue origin is:

```text
scheme = https
host   = external-api.demo.kalshi.co
port   = 443
base_path = /trade-api/v2
origin_base_url = https://external-api.demo.kalshi.co/trade-api/v2
```

The official environments page also lists `https://demo-api.kalshi.co/trade-api/v2` as a compatibility host, but B1 deliberately does not permit fallback to it. Production hosts are prohibited.

The signature path, when later execution is separately authorized, is the full request path beginning `/trade-api/v2/...` and excludes query parameters. B1 has no query parameters.

### B1-SRC-007 — historical source corroboration only

The retained OpenAPI 3.28.0 snapshot corroborates these historical operation IDs:

```text
GET  /account/limits                    -> GetAccountApiLimits
GET  /api_keys                          -> GetApiKeys
GET  /portfolio/subaccounts/balances    -> GetSubaccountBalances
GET  /portfolio/subaccounts/netting     -> GetSubaccountNetting
POST /portfolio/subaccounts             -> CreateSubaccount
```

These names MUST be labeled `HISTORICAL_CORROBORATING_OPERATION_ID` if recorded. They MUST NOT be represented as freshly verified operation IDs.

### B1-SRC-008 — deterministic derived source-binding identity

For reproducibility, the source facts above are represented by the following canonical JSON record: UTF-8, no BOM, sorted keys, no insignificant whitespace, ASCII escapes only.

```json
{"binding_name":"KALSHI_DEMO_ROUTE_B_B1_OFFICIAL_RENDERED_SOURCE_BINDING_01","fresh_api_info_version":"NOT_EXPOSED_BY_RENDERED_SOURCE","fresh_openapi_version":"NOT_EXPOSED_BY_RENDERED_SOURCE","fresh_operation_ids":"NOT_EXPOSED_BY_RENDERED_SOURCE","fresh_raw_openapi_status":"NOT_OBTAINED_UNSUPPORTED_TEXT_YAML_IN_BROWSER_AND_DIRECT_DOWNLOAD_FAILED","fresh_source_class":"OFFICIAL_RENDERED_DOCUMENTATION","historical_corroboration":{"get_api_keys_subaccount_semantics":"absent/null described as unrestricted","info_version":"3.28.0","openapi":"3.0.0","operation_ids":{"GET /account/limits":"GetAccountApiLimits","GET /api_keys":"GetApiKeys","GET /portfolio/subaccounts/balances":"GetSubaccountBalances","GET /portfolio/subaccounts/netting":"GetSubaccountNetting","POST /portfolio/subaccounts":"CreateSubaccount"},"path":"04_HISTORICAL_SOURCE_CONTEXT/openapi_3_28_0_predecessor_snapshot.yaml","raw_bytes":333315,"sha256":"cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b"},"observed_at_utc":"2026-08-27T20:02:16Z","pages":[{"method":"GET","path":"/account/limits","response_200_top_level_required":["usage_tier","read","write","grants"],"url":"https://docs.kalshi.com/api-reference/account/get-account-api-limits"},{"current_key_subaccount_response_absence_semantics":"NOT_EXPOSED_BY_FRESH_RENDERED_SOURCE","method":"GET","path":"/api_keys","response_200_top_level_required":["api_keys"],"url":"https://docs.kalshi.com/api-reference/api-keys/get-api-keys"},{"account_wide_statement":"all subaccounts including primary","method":"GET","path":"/portfolio/subaccounts/balances","response_200_top_level_required":["subaccount_balances"],"url":"https://docs.kalshi.com/api-reference/portfolio/get-all-subaccount-balances"},{"account_wide_statement":"all subaccounts","method":"GET","path":"/portfolio/subaccounts/netting","response_200_top_level_required":["netting_configs"],"url":"https://docs.kalshi.com/api-reference/portfolio/get-subaccount-netting"},{"partition_statement":"balances and positions are independent buckets within one Direct account","restricted_key_statement":"single-subaccount restricted keys cannot manage subaccounts or API keys and out-of-scope endpoints return 403","subaccount_numbering":"0 primary; 1-63 numbered","url":"https://docs.kalshi.com/getting_started/subaccounts"},{"create_request_omission_semantics":"omit request subaccount to leave newly created key unrestricted","note":"does not by itself prove GET /api_keys response omission/null semantics","subaccount_constraint":"integer 0-63","url":"https://docs.kalshi.com/api-reference/api-keys/create-api-key"},{"documented_numbering":"sequential from 1; max 63 numbered","documented_tier_rule":"Advanced API tier and above","method":"POST_SOURCE_CONTEXT_ONLY_NOT_B1_RUNTIME","path":"/portfolio/subaccounts","url":"https://docs.kalshi.com/api-reference/portfolio/create-subaccount"},{"recommended_demo_rest_base_url":"https://external-api.demo.kalshi.co/trade-api/v2","signature_path_rule":"full request path from API root without query parameters","supported_demo_compatibility_url":"https://demo-api.kalshi.co/trade-api/v2","url":"https://docs.kalshi.com/getting_started/api_environments"},{"purpose":"official documentation index corroboration","url":"https://docs.kalshi.com/llms.txt"}],"schema_revision":1}
```

Identity:

```text
canonical_source_binding_record_bytes = 3307
canonical_source_binding_record_sha256 = 964056df0d633fa27d53363aa58ee3c59c2fc6281c0b1cc68f25bbad5b104dc2
```

This hash identifies the **derived source-binding record**, not raw bytes of Kalshi's documentation.

### B1-SRC-009 — freshness at future real execution

The authoring source snapshot does not prove future freshness. Before any future authenticated B1 execution, the execution package MUST bind a task-current official source record for all four GET operations. That record may be obtained under separately permitted official-documentation access or supplied as an exact external artifact. If a relied-on method, path, authorization rule, response field, key-restriction semantic, subaccount numeric constraint, or Demo environment rule materially differs, execution MUST halt as `B1_SOURCE_DRIFT` or `B1_OFFICIAL_SOURCE_CONFLICT` before the affected inference.

This requirement does not itself authorize documentation network access at execution time.

---

## 6. Capability boundaries

### B1-CAP-001 — current SPEC_ONLY authoring capability

For this artifact-producing task:

```yaml
canonical_repository_sync: PERMITTED_READ_ONLY_AS_NEEDED
repository_write: PROHIBITED
git_write: PROHIBITED
public_official_documentation_access:
  host: docs.kalshi.com
  method: GET_ONLY
  credentials: PROHIBITED
general_internet: PROHIBITED
kalshi_demo_authenticated_api: PROHIBITED
kalshi_demo_write: PROHIBITED
kalshi_production: PROHIBITED
credential_read: PROHIBITED
credential_signing: PROHIBITED
websocket: PROHIBITED
funding_transfer: PROHIBITED
subaccount_creation: PROHIBITED
netting_update: PROHIBITED
implementation: PROHIBITED
tests: PROHIBITED
persistent_state_mutation: PROHIBITED
```

### B1-CAP-002 — future B1 execution envelope described by this specification

A later execution, only when separately enabled by its own task, MUST be constrained to:

```yaml
environment: KALSHI_DEMO
venue_network:
  protocol: HTTPS_ONLY
  host: external-api.demo.kalshi.co
  port: 443
  base_path: /trade-api/v2
  methods: [GET]
  paths:
    - /account/limits
    - /api_keys
    - /portfolio/subaccounts/balances
    - /portfolio/subaccounts/netting
  redirects: PROHIBITED
  retries: 0
credentials:
  use_for_exact_authenticated_reads: PERMITTED_ONLY_WHEN_SEPARATELY_DISPATCHED
  print_or_log_secret_values: PROHIBITED
venue_writes: PROHIBITED
orders: PROHIBITED
cancellations: PROHIBITED
amendments: PROHIBITED
subaccount_creation: PROHIBITED
funding_transfer: PROHIBITED
netting_update: PROHIBITED
websocket: PROHIBITED
production_access: PROHIBITED
host_fallback: PROHIBITED
package_install: PROHIBITED
general_internet: PROHIBITED
official_documentation_access: PROHIBITED_AT_VENUE_EXECUTION_UNLESS_SEPARATELY_PERMITTED
subprocess_spawn: PROHIBITED_BY_DEFAULT
repository_write: PROHIBITED_DURING_EXECUTION
git_write: PROHIBITED_DURING_EXECUTION
local_evidence_artifact_write: PERMITTED_ONLY_TO_EXPLICIT_EXTERNAL_OUTPUT_ROOT
```

Permission for authenticated GETs does not imply any write permission.

---

## 7. Future implementation surface

This specification performs no implementation. If a later implementation task adopts this exact specification without changing its path envelope, the smallest intended repository surface is:

### B1-IMPL-001 — writable paths for later implementation

```text
src/arb/venues/kalshi/account_subaccount_probe.py
tests/test_kalshi_account_subaccount_probe.py
```

No other repository path is writable by implication from this specification.

### B1-IMPL-002 — readable protected dependencies

The later implementation MAY read/import the exact canonical versions from the required base as appropriate, but MUST NOT modify them under this specification's intended path envelope:

```text
src/arb/venues/kalshi/models.py
src/arb/venues/kalshi/errors.py
src/arb/venues/kalshi/validation.py
src/arb/venues/kalshi/connectivity.py
```

### B1-IMPL-003 — credential-source incompatibility warning

At the observed canonical base, `validation.py` contains an older credential-source convention using a PEM-content environment source. B1's controlling credential convention is path-based and therefore incompatible with blindly reusing that rule.

The later B1 implementation MUST NOT:

```text
replace KALSHI_DEMO_PRIVATE_KEY_PATH with KALSHI_DEMO_PRIVATE_KEY_PEM
read private-key bytes from an environment variable
modify validation.py merely to force compatibility
silently accept multiple secret-source conventions
```

It MAY reuse non-secret Demo endpoint/profile concepts from canonical code only where their exact current semantics remain compatible.

### B1-IMPL-004 — no new dependency

The intended implementation MUST use the existing project environment and standard/canonical dependencies. No new package dependency or package installation is required by this specification.

---

## 8. Credential and secret contract for a later execution

### B1-CRED-001 — only two credential references

The only permitted credential source names are:

```text
KALSHI_DEMO_API_KEY_ID
KALSHI_DEMO_PRIVATE_KEY_PATH
```

`KALSHI_DEMO_PRIVATE_KEY_PATH` contains a filesystem path, not key bytes.

### B1-CRED-002 — process-local secret handling

When later execution is separately allowed, the private-key file may be read solely to sign the four exact B1 requests. Key bytes and generated signatures remain process-local.

The runner MUST NOT print, log, return, serialize, hash into a public artifact, or otherwise persist:

```text
private-key bytes
private-key PEM text
signature bytes/base64
KALSHI-ACCESS-SIGNATURE values
authentication headers
raw environment variables
```

### B1-CRED-003 — exact current-key matching

For the `/api_keys` response, the runner MUST compare each returned `api_key_id` to the in-memory value of `KALSHI_DEMO_API_KEY_ID` and require exactly one match.

It MUST NOT persist or expose the identifiers or names of unrelated keys. The sanitized result stores only:

```text
current_key_match_state
current_key_scopes
current_key_subaccount_restriction_state
current_key_restricted_subaccount_number when proven
```

If there are zero or multiple matches, terminal result is `B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED` and no restriction inference is permitted.

---

## 9. Exact request plan and bounds

### B1-REQ-001 — fixed sequence

The later runner MUST use this fixed sequence and MUST NOT perform discovery beyond it:

```text
1. GET /trade-api/v2/account/limits
2. GET /trade-api/v2/api_keys
3. GET /trade-api/v2/portfolio/subaccounts/balances
4. GET /trade-api/v2/portfolio/subaccounts/netting
```

Each request has an empty query and empty body.

### B1-REQ-002 — conditional early halt

A terminal failure on an earlier request MUST prevent all later requests. The runner MUST NOT continue merely to collect additional facts after source, capability, authentication, transport, status, size, or schema failure.

A specific `403` from `/api_keys` whose body exactly matches the current source's restricted-key classification MAY terminate as `B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY`; the runner MUST NOT then attempt the two account-wide subaccount surfaces with that key.

### B1-REQ-003 — request budget

```text
maximum_request_count = 4
maximum_attempts_per_path = 1
automatic_retry_count = 0
maximum_redirect_count = 0
```

No retry is permitted for timeout, 401, 403, 429, 5xx, connection reset, TLS failure, malformed JSON, oversized response, or any other result.

### B1-REQ-004 — deadlines

The later runner MUST use monotonic time and one immutable execution start/deadline pair.

```text
PER_REQUEST_DEADLINE_MS = 10000
GLOBAL_EXECUTION_DEADLINE_MS = 40000
```

For request `i`, the effective remaining budget before every blocking network step and response-read step is:

```text
min(remaining_per_request_budget, remaining_global_budget)
```

The per-request timer begins immediately before the first network activity attributable to that request and ends only after the full response bytes have been bounded, parsed, and the request-level evidence record constructed. The global timer begins at entry to the venue-capable execute boundary and ends only at return of the terminal B1 result. Neither deadline may be reset.

Exhaustion yields `B1_READ_FAILURE` with subordinate reason `TIMEOUT`; no resend follows.

### B1-REQ-005 — response size

```text
MAX_RESPONSE_BYTES_PER_REQUEST = 262144
MAX_TOTAL_RESPONSE_BYTES = 1048576
```

The runner MUST enforce the per-response cap while reading, not after unbounded accumulation. Any response exceeding the cap is terminal `B1_AUTHORITATIVE_RESPONSE_MALFORMED` with subordinate reason `RESPONSE_TOO_LARGE`.

### B1-REQ-006 — redirects and host containment

Automatic redirect handling MUST be disabled. Any `3xx` is terminal `B1_SOURCE_DRIFT`. No `Location` target is followed.

Only the exact Demo host is permitted. Production hosts and the supported compatibility Demo host are prohibited fallbacks for B1.

### B1-REQ-007 — accepted media type/status

A successful operation requires:

```text
HTTP status = 200
response media type = application/json, permitting only an optional charset
```

A missing/blank/incompatible media type is malformed. Unknown status codes are never treated as success.

---

## 10. Response projection and exact typing

Because a current raw OpenAPI snapshot was not obtainable during authoring, the B1 parser MUST implement a closed **relied-on projection** rather than claiming a complete current full-response schema. Unknown additive fields may be retained only in local raw evidence and ignored by the sanitized parser; they MUST NOT alter B1 conclusions.

JSON booleans MUST NOT satisfy integer requirements. Binary floating point MUST NOT be used for money.

### B1-SCHEMA-001 — `/account/limits`

Required top-level fields:

```text
usage_tier: string
read: object
write: object
grants: array<object>
```

`usage_tier` MUST be exactly one of:

```text
basic
advanced
expert
premier
paragon
prime
prestige
```

For `read` and `write`, historical 3.28.0 corroborates required integer fields `refill_rate` and `bucket_capacity`. B1 MUST require both fields to be JSON integers and MUST NOT persist their exact values in the sanitized summary unless a later technical revision requires them.

Each grant used by B1 MUST contain:

```text
exchange_instance: string
level: string
source: string
expires_ts: integer | null | absent
```

Historical corroboration recognizes `exchange_instance` values `event_contract` and `margined`. For B1's Predictions route decision, only grants with `exchange_instance == "event_contract"` are `relevant_grants`; others may remain local evidence and MUST NOT be reinterpreted as Predictions grants.

An unrecognized `usage_tier` or relied-on field type is `B1_SOURCE_DRIFT` or `B1_AUTHORITATIVE_RESPONSE_MALFORMED` according to Section 15.

### B1-SCHEMA-002 — `/api_keys`

Required top-level projection:

```text
api_keys: array<object>
```

For each element, B1 consumes:

```text
api_key_id: string
name: string
scopes: array<string>
subaccount: integer 0..63 | null | absent
```

`name` is validated but never persisted to the sanitized summary.

Recognized current-source scope vocabulary is:

```text
read
write
read::block_trade_accept
read::portfolio_balance
write::trade
write::transfer
write::block_trade_accept
```

An unknown scope token affecting the uniquely matched current key is `B1_SOURCE_DRIFT`; it MUST NOT be guessed into a broader capability.

Current-key restriction classification is source-gated:

```text
subaccount integer N where 0 <= N <= 63
    => RESTRICTED_TO_EXACT_SUBACCOUNT
       restricted_subaccount_number = N

subaccount absent or explicit null
    => UNRESTRICTED only when the task-current official source binding
       explicitly defines that GET /api_keys response state as unrestricted
    => otherwise NOT_EXPOSED

wrong type / bool / out of range
    => B1_AUTHORITATIVE_RESPONSE_MALFORMED
```

Under the authoring rendered-source binding in Section 5, absent/null response semantics are `NOT_EXPOSED`; historical 3.28.0 semantics alone cannot upgrade them.

A `write` scope in the returned key metadata does not grant or authorize any write in B1 and is not proof of CreateSubaccount capability.

### B1-SCHEMA-003 — `/portfolio/subaccounts/balances`

Required top-level projection:

```text
subaccount_balances: array<object>
```

Each consumed row requires:

```text
subaccount_number: integer, 0..63
exchange_index: integer
balance: fixed-point decimal JSON string
updated_ts: integer
```

`balance` MUST be parsed from its original string with exact decimal arithmetic. Accepted B1 lexical grammar is:

```regex
^-?(0|[1-9][0-9]*)(\.[0-9]{1,6})?$
```

No exponent notation, NaN, infinity, leading plus sign, commas, whitespace, or binary float conversion is allowed.

For sanitized reporting:

```text
Decimal(balance) == 0 => ZERO
Decimal(balance) != 0 => NONZERO
```

Exact dollar values MUST NOT be copied into the sanitized summary.

If multiple exchange-index rows exist for one subaccount, that subaccount's summary balance class is:

```text
NONZERO if any valid row is NONZERO
ZERO only if every valid row for that subaccount is ZERO
```

### B1-SCHEMA-004 — `/portfolio/subaccounts/netting`

Required top-level projection:

```text
netting_configs: array<object>
```

Each consumed row requires:

```text
subaccount_number: integer, 0..63
enabled: boolean
exchange_index: integer
```

Netting configuration is descriptive B1 evidence only. B1 never updates it and never converts `enabled` or `disabled` into writer-readiness evidence.

### B1-SCHEMA-005 — duplicate row handling

Within balances, an exact duplicate row for the same `(subaccount_number, exchange_index)` may be canonicalized once only if every consumed field is identical. Conflicting duplicates are `B1_AUTHORITATIVE_RESPONSE_MALFORMED`.

The same rule applies to netting rows by `(subaccount_number, exchange_index)`.

### B1-SCHEMA-006 — mandatory primary identity

A valid complete account-wide enumeration MUST include subaccount `0` in both balances and netting identity sets. Absence of `0` from either otherwise syntactically valid account-wide response is `B1_SOURCE_DRIFT`, because it contradicts the relied-on official account-wide/primary semantics.

---

## 11. Current-key scope and account-wide proof

### B1-KEY-001 — successful unrestricted-key proof

The current key is classified `UNRESTRICTED` only if:

1. `/api_keys` returns 200 with a valid body;
2. the exact in-memory current key ID matches exactly one entry;
3. the matching entry has the response state defined by the task-current source as unrestricted; and
4. that task-current source explicitly defines the relevant absent/null response semantic rather than relying only on the historical 3.28.0 snapshot or the Create API Key request-body omission rule.

With only the authoring rendered-source binding in Section 5, an absent or explicit-null `subaccount` response field remains `NOT_EXPOSED`; a future execution must carry a stronger task-current official source binding before account-wide absence can be proven through this route.

### B1-KEY-002 — exact restricted key

If the unique current-key record contains integer subaccount `N`, B1 records:

```text
CURRENT_KEY_SUBACCOUNT_RESTRICTION = RESTRICTED_TO_EXACT_SUBACCOUNT
CURRENT_KEY_RESTRICTED_SUBACCOUNT_NUMBER = N
```

It MUST terminate `B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY`. It MUST NOT interpret any later/previous partial portfolio view as account-wide absence.

### B1-KEY-003 — 403 restricted-key proof without exact number

If `/api_keys` returns `403` and the returned error body exactly matches the current official restricted-key error classification, B1 may record:

```text
CURRENT_KEY_SUBACCOUNT_RESTRICTION = RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN
```

No exact number is inferred. Terminal result is `B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY`.

A generic or differently shaped 403 is `B1_READ_CAPABILITY_INSUFFICIENT`, not proof of restriction.

### B1-KEY-004 — account-wide proof predicate

`account_wide_enumeration_proven = true` if and only if all are true:

```text
current_key_match_state == UNIQUE
current_key_subaccount_restriction_state == UNRESTRICTED
balances response == valid 200
netting response == valid 200
balances identity set includes 0
netting identity set includes 0
balances identity set == netting identity set
```

Otherwise it is `false`.

---

## 12. Independent enumeration and reconciliation

### B1-ENUM-001 — identity sets

Define:

```text
BALANCE_SUBACCOUNT_SET = sorted unique subaccount_number values in balances
NETTING_SUBACCOUNT_SET = sorted unique subaccount_number values in netting
```

No identity may be synthesized from numeric gaps. For example, observing `0` and `2` does not imply `1` exists.

### B1-ENUM-002 — agreement

A successful account-wide B1 result requires:

```text
BALANCE_SUBACCOUNT_SET == NETTING_SUBACCOUNT_SET
```

If both responses are individually valid but the sets differ, terminal result is:

```text
B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT
```

The sanitized result MUST preserve both sorted sets. It MUST NOT take their union, intersection, or choose one source as silently authoritative.

### B1-ENUM-003 — numbered candidates

If account-wide enumeration is proven, define:

```text
NUMBERED_SUBACCOUNTS = sorted(N for N in BALANCE_SUBACCOUNT_SET if N > 0)
```

`NUMBERED_SUBACCOUNTS` is a candidate identity list only.

---

## 13. Exact B1 interpretation theorems

### B1-FACT-001 — numbered subaccount discovered

If `NUMBERED_SUBACCOUNTS` is non-empty under proven account-wide enumeration:

```text
terminal_outcome = B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED
```

B1 proves only that one or more numbered subaccount identities were authoritatively exposed by the two selected read surfaces at the observation time, plus the explicitly recorded B1 balance class/netting metadata.

It does **not** prove for any candidate:

```text
clean inception
newly created for ARB
complete history
no prior orders
no prior fills
no prior positions
zero historical exposure
zero current economic exposure beyond the narrow balance-class observation
funding suitability
empty suitability
writer eligibility
canary readiness
Gate-D readiness
```

### B1-FACT-002 — primary only

If account-wide enumeration is proven and both sets are exactly `{0}`:

```text
terminal_outcome = B1_PRIMARY_ONLY_OBSERVED
fact = NO_CURRENT_NUMBERED_SUBACCOUNT_OBSERVED
```

This does not prove that a numbered subaccount never existed and does not prove that creation is available, unavailable, authorized, safe, or necessary.

### B1-FACT-003 — independent bucket semantics are not clean-history semantics

Current official documentation describes subaccount balances and positions as independent buckets under one Direct account. B1 may preserve that as an interface/economic partition fact. It MUST NOT convert that fact into a clean-inception or complete-history theorem.

### B1-FACT-004 — creation capability

B1 MUST output:

```text
CREATE_SUBACCOUNT_CAPABILITY = NOT_PROVEN_BY_B1_READ_ONLY_FACTS
```

The sanitized summary MAY separately report whether the returned `usage_tier` satisfies the **documented tier rule** observed in current Create Subaccount documentation, using:

```text
DOCUMENTED_CREATE_TIER_RULE_MATCH = YES | NO | NOT_EVALUABLE
```

This is documentation-level metadata only. It is not a write capability, authorization, readiness result, or prediction of success.

### B1-FACT-005 — primary state remains unchanged

Every terminal B1 result MUST assert:

```text
historical_primary_writer_proof_state = HELD
historical_primary_unresolved_exposure = UNKNOWN_UNBOUNDED
historical_primary_normal_writer_eligible = false
historical_primary_safe_to_reuse_proven = false
```

B1 cannot release or reconcile the historical primary domain.

---

## 14. Terminal outcomes and next-route theorem

### B1-TERM-001 — closed terminal outcome set

The terminal `outcome` MUST be exactly one of:

```text
B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED
B1_PRIMARY_ONLY_OBSERVED
B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
B1_READ_CAPABILITY_INSUFFICIENT
B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT
B1_OFFICIAL_SOURCE_CONFLICT
B1_AUTHORITATIVE_RESPONSE_MALFORMED
B1_READ_FAILURE
B1_SOURCE_DRIFT
B1_CAPABILITY_OR_SCOPE_VIOLATION
```

A successful terminal result is not a domain-readiness result.

### B1-TERM-002 — deterministic precedence

The first applicable terminal class in this precedence controls:

```text
1. B1_CAPABILITY_OR_SCOPE_VIOLATION
2. B1_OFFICIAL_SOURCE_CONFLICT
3. B1_SOURCE_DRIFT
4. B1_READ_FAILURE
5. B1_AUTHORITATIVE_RESPONSE_MALFORMED
6. B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED
7. B1_READ_CAPABILITY_INSUFFICIENT
8. B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
9. B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT
10. B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED
11. B1_PRIMARY_ONLY_OBSERVED
```

A lower-precedence result MUST NOT mask an earlier material failure.

### B1-ROUTE-001 — branch A

If terminal outcome is `B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED`:

```text
next_route_class = EXISTING_NUMBERED_CANDIDATES_REQUIRE_LATER_PROOF
```

No write domain is selected. Candidate identities may be passed to later B2/B3/B4a planning. Clean/readiness state remains unproven.

### B1-ROUTE-002 — branch B

If terminal outcome is `B1_PRIMARY_ONLY_OBSERVED`:

```text
next_route_class = NO_NUMBERED_DOMAIN_CURRENTLY_OBSERVED
```

Subaccount `0` remains unusable for the clean Route-B path. Any future creation path requires a separate write specification, durable creation-result reconciliation, and separately explicit execution capability before a creation request could occur.

### B1-ROUTE-003 — branch C

If account-wide enumeration is not proven:

```text
next_route_class = RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
```

Route-B domain selection stops. No absence theorem is inferred from a restricted or insufficient view.

### B1-ROUTE-004 — branch D

If source or response contract is unresolved:

```text
next_route_class = RESOLVE_SOURCE_OR_RESPONSE_CONTRACT
```

No create or domain capability inference is permitted.

### B1-ROUTE-005 — no automatic advancement

No B1 terminal outcome automatically authorizes or starts B2, B3, B4a, B4b, B5, B6, B7, or B8.

---

## 15. Failure, halt, retry, and ambiguity handling

### B1-FAIL-001 — source conflict

If two task-current official source representations materially disagree on a relied-on method, path, required field, key-restriction semantic, numeric constraint, or environment rule and the conflict cannot be mechanically scoped away, terminal outcome is `B1_OFFICIAL_SOURCE_CONFLICT`. No affected request/inference proceeds.

### B1-FAIL-002 — source drift

If the task-current source binding materially differs from the reviewed B1 contract, or a semantically valid response contradicts a relied-on current-source theorem such as mandatory primary `0`, terminal outcome is `B1_SOURCE_DRIFT`.

### B1-FAIL-003 — malformed authoritative response

Invalid JSON, wrong relied-on field type, missing required relied-on field, invalid subaccount number, invalid fixed-point lexical value, conflicting duplicate row, or response-size excess yields `B1_AUTHORITATIVE_RESPONSE_MALFORMED`.

No partial fact from the malformed response may be promoted to a successful B1 theorem.

### B1-FAIL-004 — read failures

Transport failure, DNS failure, TLS failure, timeout, 429, 5xx, or unexpected non-success HTTP status not classified more specifically yields `B1_READ_FAILURE` or `B1_READ_CAPABILITY_INSUFFICIENT` for a credential/scope-specific 401/403 condition.

No automatic retry follows.

### B1-FAIL-005 — post-send ambiguity

B1 contains only idempotent GETs and no venue writes. A connection failure after a GET send may leave the observation result unknown, but it creates no B1 write-result reconciliation problem. The runner MUST still stop and MUST NOT resend automatically.

### B1-FAIL-006 — no fallback

Failure on the recommended Demo host MUST NOT trigger:

```text
compatibility-host fallback
production fallback
WebSocket fallback
browser/manual fallback
another account
another API key
a broader endpoint set
```

---

## 16. Evidence separation and persistence contract

### B1-EVID-001 — three evidence classes

The future execution MUST distinguish:

```text
raw authenticated local evidence
sanitized review summary
canonical repository documentation
```

Raw authenticated responses are:

```text
LOCAL_ONLY
DO_NOT_CANONICALLY_COMMIT_BY_DEFAULT
```

### B1-EVID-002 — local raw response files

A separately authorized B1 execution MAY persist raw response bodies only under an explicit task-local output root outside the canonical repository. Deterministic filenames SHOULD be:

```text
01_account_limits.response.bin
02_api_keys.response.bin
03_subaccount_balances.response.bin
04_subaccount_netting.response.bin
```

Absent requests due to early halt produce no fabricated response file.

### B1-EVID-003 — local evidence manifest schema

The local evidence manifest filename is:

```text
B1_ACCOUNT_SUBACCOUNT_FACTS_EVIDENCE_MANIFEST.json
```

It MUST be UTF-8 JSON without secrets and contain exactly the B1 projection below, permitting no secret/header fields:

```text
schema_revision: integer = 1
task_id: string = KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01
environment: string = KALSHI_DEMO
demo_rest_base_url: string = https://external-api.demo.kalshi.co/trade-api/v2
source_binding_name: string
source_binding_record_sha256: lowercase 64-hex
started_at_utc: RFC3339 UTC string
completed_at_utc: RFC3339 UTC string
request_count: integer 0..4
retry_count: integer = 0
redirect_count: integer = 0
requests: array in execution order, each item:
  sequence: integer 1..4
  method: string = GET
  path: one exact B1 path
  http_status: integer | null
  status_class: string
  raw_response_byte_length: integer >= 0 | null
  raw_response_sha256: lowercase 64-hex | null
  observed_at_utc: RFC3339 UTC string | null
  local_raw_body_filename: fixed non-secret basename | null
```

The manifest MUST NOT contain API key IDs, names, secret paths, signatures, auth headers, or exact dollar balances.

### B1-EVID-004 — sanitized summary artifact

The sanitized summary filename is exactly:

```text
B1_ACCOUNT_SUBACCOUNT_FACTS_SUMMARY.json
```

It MUST contain the following closed projection:

```text
schema_revision: 1
task_id: exact task ID
environment: KALSHI_DEMO
demo_rest_base_url: exact Demo base URL
source_binding:
  name: string
  record_sha256: lowercase 64-hex
  observed_at_utc: RFC3339 UTC
  fresh_raw_openapi_status: string
  historical_openapi_context_sha256: lowercase 64-hex
terminal_outcome: one B1 terminal enum
next_route_class: one B1 next-route enum
request_count: integer 0..4
retry_count: 0
redirect_count: 0
api_usage:
  usage_tier: recognized string | null
  relevant_grants: array of sanitized grant projections
current_key:
  match_state: UNIQUE | ZERO_MATCH | MULTIPLE_MATCHES | NOT_OBSERVED
  scopes: sorted array of recognized scope strings
  restriction_state:
    UNRESTRICTED |
    RESTRICTED_TO_EXACT_SUBACCOUNT |
    RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN |
    NOT_EXPOSED |
    NOT_OBSERVED
  restricted_subaccount_number: integer 0..63 | null
enumeration:
  account_wide_enumeration_proven: boolean
  balance_subaccount_numbers: sorted array<integer 0..63>
  netting_subaccount_numbers: sorted array<integer 0..63>
  surfaces_agree: boolean | null
  numbered_subaccounts: sorted array<integer 1..63>
  balance_classes: array of {subaccount_number, class: ZERO|NONZERO}
  netting_states: array of {subaccount_number, exchange_index, enabled}
create_subaccount:
  documented_tier_rule: ADVANCED_OR_ABOVE
  documented_tier_rule_match: YES | NO | NOT_EVALUABLE
  capability: NOT_PROVEN_BY_B1_READ_ONLY_FACTS
historical_primary:
  writer_proof_state: HELD
  unresolved_exposure: UNKNOWN_UNBOUNDED
  normal_writer_eligible: false
negative_theorems:
  historical_primary_incident_resolved: false
  historical_primary_writer_proof_released: false
  historical_primary_safe_to_reuse: false
  existing_numbered_subaccount_clean_inception_proven: false
  existing_numbered_subaccount_complete_history_proven: false
  existing_numbered_subaccount_zero_exposure_proven: false
  subaccount_creation_authorized: false
  funding_or_transfer_authorized: false
  canary_execution_ready: false
  market_maker_execution_ready: false
  production_behavior_known: false
  profitability_known: false
  arbitrage_proven: false
evidence_manifest:
  raw_bytes: integer >= 0 | null
  sha256: lowercase 64-hex | null
```

Fields unavailable because execution halted early MUST use the explicit `null`, empty-array, `NOT_OBSERVED`, or `false` states above; they MUST NOT be omitted if omission could be mistaken for success.

### B1-EVID-005 — no exact dollar balances in sanitized summary

Only `ZERO` / `NONZERO` balance classes may appear in the sanitized summary. Exact dollar strings remain raw local evidence.

### B1-EVID-006 — provenance language

A later review may state that the evidence manifest records a venue response only after verifying the exact evidence artifact identity. It MUST distinguish direct observation from project-evidence recording when appropriate. B1 does not require a later reviewer to pretend to have re-observed the network event.

---

## 17. Required negative theorems

Every successful or halted B1 summary MUST explicitly preserve all of the following as `false`/unproven:

```text
historical primary incident resolved
primary writer proof released
primary safe to reuse
existing numbered subaccount clean
existing numbered subaccount complete history
existing numbered subaccount zero exposure
subaccount creation authorized
subaccount transfer/funding authorized
canary execution ready
market-maker execution ready
production behavior known
profitability known
arbitrage proven
```

No absence of evidence may be serialized as evidence of absence beyond the exact `NO_CURRENT_NUMBERED_SUBACCOUNT_OBSERVED` theorem under proven account-wide enumeration.

---

## 18. Later implementation acceptance tests/evidence

No tests are executed by this SPEC_ONLY task. A later implementation task conforming to this specification MUST provide deterministic offline tests at minimum for the following requirements.

### B1-TEST-001 — base/path/capability containment

Prove:

- exact Demo host accepted;
- compatibility Demo host rejected;
- both production hosts rejected;
- non-HTTPS rejected;
- non-443 rejected;
- query/fragment/userinfo rejected;
- only four GET paths accepted;
- POST/DELETE/PATCH/PUT rejected before send;
- redirect disabled and 3xx not followed;
- request count cannot exceed four;
- no WebSocket path exists in the runner.

### B1-TEST-002 — credential-source contract

Prove:

- only `KALSHI_DEMO_API_KEY_ID` and `KALSHI_DEMO_PRIVATE_KEY_PATH` are accepted;
- PEM content in the path variable is rejected as a path contract violation;
- older `KALSHI_DEMO_PRIVATE_KEY_PEM` is not silently substituted;
- secret values/signatures never appear in result/evidence objects or logs;
- `/api_keys` matching keeps unrelated key IDs/names out of sanitized output.

### B1-TEST-003 — request deadline/budget

Use deterministic fake clocks/transports to prove:

- 10,000 ms per-request deadline includes read, parse, and request-evidence construction;
- 40,000 ms global deadline is anchored once and never reset;
- a timeout after send causes halt without resend;
- retry count remains zero;
- a 5th request is impossible;
- a 3xx is not followed.

### B1-TEST-004 — size limits

Prove exactly 262,144 response bytes may be accepted if otherwise valid and byte 262,145 halts. Prove total accepted response bytes cannot exceed 1,048,576.

### B1-TEST-005 — account limits schema

Prove accepted tiers and exact-type requirements. Reject bool-as-int, missing required projection fields, malformed grants, and unrecognized usage tier without guessing.

### B1-TEST-006 — API-key matching/restriction

Prove:

- one exact ID match required;
- zero/multiple matches halt;
- absent/null `subaccount` => `NOT_EXPOSED` when the task-current source does not define response omission/null semantics;
- absent/null => `UNRESTRICTED` only under a task-current source fixture that explicitly defines that response semantic;
- integer 0 and 63 boundaries accepted as exact restriction values;
- -1/64/bool/string rejected;
- exact restricted-key 403 classifies account-wide enumeration as unproven;
- generic 403 does not reveal an exact restriction.

### B1-TEST-007 — balance fixed-point semantics

Prove:

- decimal strings use exact `Decimal`/fixed-point parsing;
- no binary float conversion;
- `0`, `0.0`, `-0.000000` classify ZERO;
- positive/negative nonzero values classify NONZERO;
- exponent, NaN, infinity, plus sign, whitespace, comma, >6 fractional digits reject;
- exact dollar strings do not appear in summary.

### B1-TEST-008 — subaccount identity reconciliation

Prove:

- subaccount number boundaries 0 and 63 accepted;
- bool/-1/64/string rejected;
- primary 0 is mandatory in a complete account-wide result;
- equal sets succeed;
- differing sets halt `B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT` without union/intersection inference;
- gaps are not synthesized;
- exact duplicate rows contribute once;
- conflicting duplicates halt.

### B1-TEST-009 — terminal and next-route theorem

Prove:

- numbered set non-empty => `B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED` and later-history/readiness remains unproven;
- exactly `{0}` => `B1_PRIMARY_ONLY_OBSERVED` and only `NO_CURRENT_NUMBERED_SUBACCOUNT_OBSERVED` is asserted;
- restricted/unknown key scope never produces account-wide absence;
- source conflict/drift precedes success;
- no terminal result authorizes later Route-B stages.

### B1-TEST-010 — negative-theorem serialization

For every successful terminal class and representative failure class, assert the full `negative_theorems` object remains explicitly false as required.

### B1-TEST-011 — source binding

Prove source-binding record hash validation, exact method/path projection, fresh-source drift classification, and that historical OpenAPI operation IDs cannot be presented as fresh current IDs.

### B1-TEST-012 — artifact sensitivity

Prove local raw evidence can contain exact authenticated response bytes only in the external output root, while sanitized summary/manifest exclude:

```text
private-key bytes
signature
auth headers
raw environment
unrelated API key IDs/names
exact dollar balances
```

---

## 19. Requirement traceability map

A later implementation/review MUST be able to produce a table with columns:

```text
SPEC REQUIREMENT -> CODE LOCATION -> TEST/EVIDENCE -> STATUS
```

At minimum, every requirement ID beginning with the following prefixes must be mapped:

```text
B1-BASE
B1-STATE
B1-SCOPE
B1-SRC
B1-CAP
B1-IMPL
B1-CRED
B1-REQ
B1-SCHEMA
B1-KEY
B1-ENUM
B1-FACT
B1-TERM
B1-ROUTE
B1-FAIL
B1-EVID
B1-TEST
```

Passing tests alone are insufficient if static conformance to path, source, capability, and evidence boundaries is not demonstrated.

---

## 20. Completion criteria for the future B1 implementation/execution chain

### B1-DONE-001 — specification implementation completeness

A later implementation is specification-complete only when:

1. only the intended writable implementation/test paths changed;
2. protected dependencies remained unchanged;
3. the exact canonical base or an explicitly retargeted base is verified;
4. all offline acceptance tests pass;
5. requirement traceability is complete;
6. no new dependency is introduced;
7. no venue access occurs during implementation/offline tests.

### B1-DONE-002 — execution completeness

A later B1 execution is complete only when:

1. a separately bounded execution capability permits the exact authenticated Demo GET surface;
2. a task-current official source binding is present and not materially drifted;
3. the exact current key/source references are validated without exposing secrets;
4. request and deadline budgets are enforced;
5. exactly one terminal outcome is produced;
6. the local evidence manifest and sanitized summary are generated according to this specification;
7. no write, retry, redirect, fallback, WebSocket, production access, or repository mutation occurred.

---

## 21. Route-B sequence preserved

This specification preserves the accepted sequencing boundary:

```text
B1. READ_ONLY account/subaccount capability-and-facts
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

B1 imports no capability from B2-B8.

---

## 22. Final normative boundary

This specification does not perform or authorize:

```text
implementation
test execution
credential use
authenticated Kalshi access
subaccount creation
funding/transfer
netting modification
order placement
order cancellation
order amendment
persistent ledger/authority mutation
writer-proof release
primary-domain reuse
production access
repository write
Git write
```

The smallest B1 theorem is deliberately narrow: determine the current read capability/scope facts, reconcile the two minimal account-wide subaccount identity surfaces when the key can authoritatively see them, and return a bounded next-route classification without promoting existence into cleanliness or absence into creation capability.
