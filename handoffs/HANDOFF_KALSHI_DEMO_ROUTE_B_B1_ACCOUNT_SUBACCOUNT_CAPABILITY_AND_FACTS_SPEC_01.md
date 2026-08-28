# HANDOFF_KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01

## 1. Purpose

This handoff is concise implementation context for:

```text
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md
```

The specification controls if this handoff conflicts with it.

This handoff does not itself authorize implementation, tests, credentials, venue access, or any write.

---

## 2. Canonical repository/base

```text
repository = rigolugo/ARB
branch = main
canonical_main = a0d7f324b7c49b6f2bfc7b586843ab77172cbe17
canonical_tree = 9f5b5c413ffb6f7cb901a3a68654143617461155
canonical_parent = 997954197ebb8cbfb13baa3231b490abfbe20f64
```

Do not silently retarget to a later base.

---

## 3. Current accepted state that must not change

```text
historical primary domain =
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0

writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

B1 cannot release, reconcile, or reuse primary subaccount `0`.

---

## 4. Controlling specification/source identities

Primary specification:

```text
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md
```

Historical OpenAPI source context only:

```text
openapi_3_28_0_predecessor_snapshot.yaml
bytes = 333315
sha256 = cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b
OpenAPI = 3.0.0
info.version = 3.28.0
```

Fresh rendered-source binding used by the specification:

```text
binding_name = KALSHI_DEMO_ROUTE_B_B1_OFFICIAL_RENDERED_SOURCE_BINDING_01
observed_at_utc = 2026-08-27T20:02:16Z
canonical_record_bytes = 3307
canonical_record_sha256 = 964056df0d633fa27d53363aa58ee3c59c2fc6281c0b1cc68f25bbad5b104dc2
fresh_raw_openapi_status = NOT_OBTAINED
fresh_openapi_version = NOT_EXPOSED_BY_RENDERED_SOURCE
fresh_api_info_version = NOT_EXPOSED_BY_RENDERED_SOURCE
fresh_operation_ids = NOT_EXPOSED_BY_RENDERED_SOURCE
```

Fresh source URLs:

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

Fresh rendered Create Subaccount documentation observed `Advanced API tier and above` and numbered subaccounts `1..63`, so the earlier supplied `1..32` rendered-source conflict was not reproduced. Current raw OpenAPI was not obtained, so the representation remains lower-confidence than an exact raw OpenAPI binding.

Regardless, B1 freezes:

```text
CREATE_SUBACCOUNT_CAPABILITY = NOT_PROVEN_BY_B1_READ_ONLY_FACTS
```

---

## 5. Intended later implementation surface

When a later implementation task explicitly permits it, intended writable paths are only:

```text
src/arb/venues/kalshi/account_subaccount_probe.py
tests/test_kalshi_account_subaccount_probe.py
```

Readable protected dependencies:

```text
src/arb/venues/kalshi/models.py
src/arb/venues/kalshi/errors.py
src/arb/venues/kalshi/validation.py
src/arb/venues/kalshi/connectivity.py
```

Important hazard: canonical `validation.py` at this base recognizes an older PEM-content credential source. B1 requires:

```text
KALSHI_DEMO_API_KEY_ID
KALSHI_DEMO_PRIVATE_KEY_PATH
```

The private-key variable contains a filesystem path, not PEM bytes. Do not silently reuse `KALSHI_DEMO_PRIVATE_KEY_PEM`; do not modify protected `validation.py` under this intended path envelope.

No new dependency is required.

---

## 6. Exact future B1 venue surface

Only after a separate execution task permits authenticated Demo reads:

```text
origin = https://external-api.demo.kalshi.co/trade-api/v2

1. GET /account/limits
2. GET /api_keys
3. GET /portfolio/subaccounts/balances
4. GET /portfolio/subaccounts/netting
```

No query, no body, no pagination, no additional discovery.

Bounds:

```text
max requests = 4
attempts per path = 1
retries = 0
redirects = 0
per-request deadline = 10000 ms
global execution deadline = 40000 ms
max response bytes/request = 262144
max total response bytes = 1048576
```

No compatibility-host fallback, production fallback, WebSocket, transfer listing, order/fill/position/history reads, or any write.

---

## 7. Core response logic

### `/account/limits`

Consume only the relied-on projection:

```text
usage_tier
read
write
grants
```

Recognized usage tiers:

```text
basic advanced expert premier paragon prime prestige
```

Persist usage tier and relevant `event_contract` grant metadata; do not treat write-rate metadata or tier level as write authorization.

### `/api_keys`

Match `KALSHI_DEMO_API_KEY_ID` in memory and require exactly one match. Never put other key IDs/names in sanitized output.

Restriction rule:

```text
integer 0..63 -> RESTRICTED_TO_EXACT_SUBACCOUNT
absent/null -> UNRESTRICTED only if the task-current official source binding
               explicitly defines GET /api_keys response omission/null as
               unrestricted; otherwise NOT_EXPOSED
```

The authoring rendered-source binding does not expose the GET-response absence/null semantic. Historical OpenAPI 3.28.0 says absent/null is unrestricted, but that historical statement alone is not task-current proof.

If exact restricted-key 403 occurs before the current key can be enumerated, classify restriction as `RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN` and account-wide enumeration as unproven.

### balances

Rows require:

```text
subaccount_number: int 0..63
exchange_index: int
balance: fixed-point decimal string
updated_ts: int
```

Never parse balance through binary float. Sanitized output records only `ZERO` / `NONZERO`.

### netting

Rows require:

```text
subaccount_number: int 0..63
enabled: bool
exchange_index: int
```

### account-wide proof

Account-wide enumeration is proven only when current key is uniquely matched and `UNRESTRICTED`, both balances/netting are valid 200 responses, both include `0`, and the identity sets are equal.

Never union/intersect disagreeing sets to manufacture a result.

---

## 8. Terminal outcomes

Closed outcome set:

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

Two successful facts are deliberately narrow:

```text
numbered candidate(s) observed
OR
no current numbered subaccount observed under proven account-wide enumeration
```

Neither is writer/domain readiness.

---

## 9. Next-route theorem

```text
Existing numbered candidate(s)
-> no writes
-> later B2/B3/B4a planning may consume exact candidate identities
-> clean inception/history/readiness remain unproven

Primary only
-> primary remains prohibited clean-domain candidate
-> no current numbered subaccount observed
-> any creation path requires separate write specification + durable
   creation-result reconciliation + separate execution capability

Account-wide enumeration not proven
-> stop domain selection
-> later bounded task must resolve read credential/scope/source limitation

Source/response contract unresolved
-> stop affected path
-> no create/domain inference
```

No branch auto-starts B2-B8.

---

## 10. Evidence outputs for later execution

Raw authenticated responses:

```text
LOCAL_ONLY / DO_NOT_CANONICALLY_COMMIT_BY_DEFAULT
```

Required local evidence manifest:

```text
B1_ACCOUNT_SUBACCOUNT_FACTS_EVIDENCE_MANIFEST.json
```

Required sanitized summary:

```text
B1_ACCOUNT_SUBACCOUNT_FACTS_SUMMARY.json
```

Manifest binds each actually attempted request by method/path, HTTP status, raw bytes, SHA-256, timestamp, and source-binding identity. It contains no secrets/auth headers.

Sanitized summary contains only B1-relevant account tier/grant facts, current-key scope/restriction class, enumerated subaccount numbers, surface agreement, ZERO/NONZERO balance classes, netting state, source identities, request counts, terminal outcome, next-route class, and explicit negative theorems.

Never include exact dollar balances or unrelated API-key identifiers/names in the sanitized summary.

---

## 11. Negative theorems that must remain explicit

B1 alone never proves:

```text
historical primary incident resolved
primary writer proof released
primary safe to reuse
numbered candidate clean inception
numbered candidate complete history
numbered candidate zero exposure
subaccount creation authorized
funding/transfer authorized
canary execution ready
market-maker execution ready
production behavior known
profitability known
arbitrage proven
```

---

## 12. Required later offline evidence

Implementation review must map:

```text
SPEC REQUIREMENT -> CODE LOCATION -> TEST/EVIDENCE -> STATUS
```

At minimum tests must cover:

- exact host/path/method allowlist and production/compatibility rejection;
- path-based credential source and secret non-disclosure;
- current-key zero/one/multiple match cases;
- absent/integer/null subaccount restriction semantics;
- exact restricted-key 403 vs generic 403;
- per-request/global deadline crossings with fake clock;
- zero retries and zero redirects;
- 262144/262145 byte boundary;
- fixed-point Decimal lexical boundaries and float prohibition;
- subaccount 0/63 boundaries and bool/out-of-range rejection;
- mandatory primary 0;
- balances/netting agreement/disagreement;
- exact/conflicting duplicates;
- numbered vs primary-only route result;
- complete negative-theorem serialization;
- source-binding hash/drift behavior;
- sensitive raw evidence vs sanitized output separation.

No venue access is part of offline implementation tests.

---

## 13. Stop boundary

This handoff carries only B1 specification context. It does not authorize implementation, tests, credentials, authenticated venue calls, writes, subaccount creation, funding/transfers, netting changes, orders, persistence mutation, repository/Git writes, a correction revision, or B2-B8.
