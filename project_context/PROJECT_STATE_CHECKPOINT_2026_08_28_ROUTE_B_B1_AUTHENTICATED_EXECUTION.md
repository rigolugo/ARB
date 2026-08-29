# PROJECT STATE CHECKPOINT — 2026-08-28 — ROUTE B B1 AUTHENTICATED EXECUTION

Authority level: canonical current-state overlay.

This checkpoint records the accepted Route-B B1 authenticated Demo read-only execution history through Local Operator 02. For the exact execution facts listed here, this checkpoint controls over `PROJECT_STATE_CHECKPOINT_2026_08_28_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_IMPLEMENTATION.md`, which remains the controlling installation/provenance checkpoint for the accepted B1 specification and implementation.

This file grants no new venue, credential, write, production, persistent-state, writer-proof-release, or later-stage capability.

## 1. Canonical execution base

Both local execution attempts were bound to:

```text
repository = rigolugo/ARB
canonical_commit = 60e4af9123f0e3d791ec8095911ed00760960d61
canonical_tree = b0a1a3726d8f17a44c003137f1919adb5deb68d2
canonical_parent = a0d7f324b7c49b6f2bfc7b586843ab77172cbe17
```

The installed B1 implementation identities remain:

```text
src/arb/venues/kalshi/account_subaccount_probe.py
raw_bytes = 119974
sha256 = 3339af5e47c22a008c5b2e8a6d5b5f56fd4d4022bef0048eac84e883cdf304d5
git_blob = b625a54a1b5769186f76734dbe23ce6521ca4707

tests/test_kalshi_account_subaccount_probe.py
raw_bytes = 114148
sha256 = 02a38c45ce744ab062f830b6fe9dc6d93044903845269cf9cd419c4284db4c4d
git_blob = fe207019e20fd968d7f55c344dbf9d41fbe6d7f4
```

The B1 source-binding record used by both executions remains:

```text
binding_name = KALSHI_DEMO_ROUTE_B_B1_OFFICIAL_RENDERED_SOURCE_BINDING_01
record_sha256 = 964056df0d633fa27d53363aa58ee3c59c2fc6281c0b1cc68f25bbad5b104dc2
observed_at_utc = 2026-08-27T20:02:16Z
```

The retained OpenAPI 3.28.0 snapshot remains historical corroboration only:

```text
raw_bytes = 333315
sha256 = cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b
historical ApiKey.subaccount semantic = absent/null described as unrestricted
fresh rendered GET /api_keys absence/null semantic = NOT_EXPOSED_BY_FRESH_RENDERED_SOURCE
```

## 2. Local Operator 01 — accepted diagnostic finding

Execution evidence package:

```text
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_EXECUTION_01_SANITIZED_MARCO_REVIEW.zip
raw_bytes = 2860
sha256 = 8282d8f4a71594584ca41c59a260c93f468e4e100f34b38d79e17926c7685064
storage = LOCAL_ONLY_EXTERNAL_ACCEPTED_EVIDENCE
```

Observed result:

```text
terminal_outcome = B1_CAPABILITY_OR_SCOPE_VIOLATION
next_route_class = RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
request_count = 0
retry_count = 0
redirect_count = 0
raw_response_file_count = 0
```

No authenticated Kalshi HTTP request was sent by Operator 01.

The later local diagnostic established the cause:

```text
KALSHI_DEMO_PRIVATE_KEY_PEM was present in the shell
```

The canonical B1 credential contract intentionally rejects the presence of that legacy PEM-content source because B1 permits only:

```text
KALSHI_DEMO_API_KEY_ID
KALSHI_DEMO_PRIVATE_KEY_PATH
```

After the legacy environment variable was removed from the current shell, the exact canonical `load_b1_credentials(os.environ)` check returned:

```text
B1_CREDENTIAL_CONTRACT=PASS
```

This resolved the Operator-01 credential-source limitation. It did not itself establish any account/subaccount fact.

## 3. Independent credential/connectivity diagnostic

Before Operator 02, the user locally ran the previously prepared `kalshi_demo_check.py` against:

```text
GET https://external-api.demo.kalshi.co/trade-api/v2/portfolio/balance
```

using the path-based Demo credential convention and Kalshi RSA-PSS/SHA-256 signing pattern.

Observed result:

```text
HTTP 200
```

Authority:

```text
DIRECT_EMPIRICAL_OBSERVATION
```

This established that the intended Demo key/private-key pair, signing method, host, and local network path could successfully perform an authenticated Demo GET.

It was not a B1 endpoint, did not consume a B1 request attempt, and does not prove B1 account/subaccount enumeration semantics.

No credential value, private-key value, signature, populated authentication header, or exact account balance is canonicalized here.

## 4. Local Operator 02 — accepted B1 execution result

Sanitized review package:

```text
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_EXECUTION_01_LOCAL_OPERATOR_02_SANITIZED_MARCO_REVIEW.zip
raw_bytes = 3373
sha256 = 0bfd94452c6752fad056a4e34e35c0c69b75e17ec90142a68784b99c20d8400c
storage = LOCAL_ONLY_EXTERNAL_ACCEPTED_EVIDENCE
zip_crc = PASS
member_count = 3
```

The package contains:

```text
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_EXECUTION_01_LOCAL_OPERATOR_02_EXECUTION_REPORT.txt
raw_bytes = 1952

B1_ACCOUNT_SUBACCOUNT_FACTS_SUMMARY.json
raw_bytes = 2170
sha256 = c35675fbb53ce382574eebe2554b6f3d88b234af5647de7ef757d84ef0316e12

B1_ACCOUNT_SUBACCOUNT_FACTS_EVIDENCE_MANIFEST.json
raw_bytes = 1155
sha256 = ac99c7addb213991413ec219ba2572c0687b801628bbf3fd2a0f4b7c5a4426a7
```

Local Operator 02 pre-latch checks established:

```text
legacy_pem_env_absent_at_live_gate = yes
canonical_credential_contract_pre_latch = PASS
private_key_parse_pre_latch = PASS
dns_preflight_pre_latch = PASS
live_invocation_count = 1
runner_returncode = 0
```

Exact B1 terminal result:

```text
terminal_outcome = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
next_route_class = RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
request_count = 2
retry_count = 0
redirect_count = 0
production_requests = 0
venue_writes = 0
persistent_state_access = 0
persistent_state_mutations = 0
```

The two authenticated Demo requests were:

```text
1. GET /trade-api/v2/account/limits -> HTTP 200
2. GET /trade-api/v2/api_keys       -> HTTP 200
```

Local-only raw response identities:

```text
01_account_limits.response.bin
raw_bytes = 133
sha256 = da2c1adab14b7b7253e6c1925c118553b28a1f6829ded584523199cd8abee05d

02_api_keys.response.bin
raw_bytes = 110
sha256 = 13a68703876355181e59e2d162e5a34118dab999d8d9b86ed364036ddd5abb07
```

These raw authenticated response bodies remain local-only and are not committed.

## 5. Account/key facts proven by Operator 02

The accepted sanitized projection establishes:

```text
usage_tier = basic
relevant_grants = []

current_key_match_state = UNIQUE
current_key_scopes = ["read", "write"]
current_key_restriction_state = NOT_EXPOSED
current_key_restricted_subaccount_number = null

account_wide_enumeration_proven = false

create_subaccount_capability = NOT_PROVEN_BY_B1_READ_ONLY_FACTS
documented_create_subaccount_tier_rule = ADVANCED_OR_ABOVE
documented_tier_rule_match = NO
```

The execution intentionally stopped after `/api_keys`.

Therefore these two B1 reads were **not** performed:

```text
GET /trade-api/v2/portfolio/subaccounts/balances
GET /trade-api/v2/portfolio/subaccounts/netting
```

Accordingly, B1 has not established:

```text
whether any numbered subaccount >0 currently exists
whether only primary subaccount 0 exists
the account-wide balance-subaccount set
the account-wide netting-subaccount set
agreement between those two account-wide enumeration surfaces
```

An empty `numbered_subaccounts` array in the sanitized summary is not a theorem that no numbered subaccount exists; account-wide enumeration did not occur.

## 6. Why the execution stopped

The task-current rendered source binding did not expose the GET-response semantic needed to convert an absent/null `subaccount` representation in `GET /api_keys` into:

```text
UNRESTRICTED
```

The B1 controlling contract deliberately requires:

```text
absent/null response subaccount
+
task-current official response semantic not exposed
=
NOT_EXPOSED
```

The historical OpenAPI 3.28.0 statement that absent/null means unrestricted remains canonical historical corroboration, but B1 explicitly prohibits using it as task-current proof for this execution.

This is a source-freshness/scope-proof limitation, not a credential failure.

## 7. Historical primary remains held

Nothing in Operator 01, the independent balance diagnostic, or Operator 02 changes the historical primary theorem:

```text
historical primary domain =
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0

writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
historical_primary_safe_to_reuse_proven = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

No writer proof was released. No historical incident was reconciled by B1. No order, cancel, transfer, funding, or production action was performed.

## 8. Current B1 state

The current accepted state is:

```text
B1_SPECIFICATION = INSTALLED_ACCEPTED
B1_IMPLEMENTATION = INSTALLED_APPROVED_OFFLINE
B1_AUTHENTICATED_DEMO_EXECUTION = PERFORMED
B1_OPERATOR_01 = ACCEPTED_DIAGNOSTIC_FINDING_ZERO_REQUESTS
B1_OPERATOR_02 = ACCEPTED_EXECUTION_RESULT
B1_EXECUTION_RESULT = B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY
B1_NEXT_ROUTE_CLASS = RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
B1_ACCOUNT_WIDE_ENUMERATION_PROVEN = false
B1_NUMBERED_SUBACCOUNT_EXISTENCE = UNKNOWN
B1_PRIMARY_ONLY = UNKNOWN
```

The prior implementation checkpoint's `NOT_RUN` / `NOT_AVAILABLE` runtime fields are historical and are superseded by this checkpoint.

## 9. Next bounded question

The narrow unresolved question is:

```text
Can task-current official Kalshi evidence establish that the observed
GET /api_keys current-key subaccount absence/null representation means
the exact current key is unrestricted across subaccounts?
```

Canonical historical evidence MUST be inspected before any new research or probe.

If task-current official evidence establishes the semantic, any later continuation must be separately bounded and must not silently repeat already-consumed B1 requests.

This checkpoint does not itself authorize another venue request.

## 10. Restart routing

For fresh-chat restart:

1. read root `START_HERE.md`;
2. read `project_context/START_HERE.md`;
3. apply `project_context/ARB_CANONICAL_CONTEXT_CONTINUITY_AND_EVIDENCE_WORKFLOW.md`;
4. read `project_context/PROJECT_STATE.md`;
5. apply the routed historical checkpoints;
6. apply `project_context/PROJECT_STATE_CHECKPOINT_2026_08_28_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_IMPLEMENTATION.md` for B1 installation provenance;
7. apply this checkpoint for the current B1 execution theorem;
8. inspect the exact B1 specification/source binding before declaring a fact missing or initiating new external work.

This checkpoint grants no new credentials, venue access, venue writes, production access, persistent-state mutation, writer-proof release, or later Route-B capability.
