# PROJECT STATE CHECKPOINT — 2026-08-28 — ROUTE B B1 ACCOUNT/SUBACCOUNT CAPABILITY-AND-FACTS IMPLEMENTATION

Authority level: canonical current-state overlay.

This checkpoint records the accepted Route-B B1 specification and approved offline implementation installation. For the exact facts listed here, this checkpoint controls over older state text until a later consolidation updates the long-form project state/index.

This file grants no venue, credential, persistent-state, or later-stage capability.

## 1. Installation base

The canonical installation task is bound to:

```text
repository = rigolugo/ARB
branch = main
base_HEAD = a0d7f324b7c49b6f2bfc7b586843ab77172cbe17
base_tree = 9f5b5c413ffb6f7cb901a3a68654143617461155
base_parent = 997954197ebb8cbfb13baa3231b490abfbe20f64
```

The containing canonical installation commit must be a direct child of that base. If remote `main` differs before push, installation must stop rather than rebase or silently retarget.

## 2. Installed controlling B1 documentation

Canonical specification:

```text
specifications/KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md
raw_bytes = 54469
sha256 = 0265953846cd48105a1d20d79453d6dfdb92310c38f9a8a06295fa32dceae500
```

Canonical subordinate handoff:

```text
handoffs/HANDOFF_KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md
raw_bytes = 10518
sha256 = 31d8ed23b7b4eb2e2cd6a834b5dbcd2374ce4abc06a6ad633be6dff85604b53f
```

Canonical implementation review record:

```text
reviews/REVIEW_KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_IMPLEMENTATION_01.md
review_disposition = APPROVE
```

The specification controls on any conflict with its handoff or review metadata.

## 3. Installed approved implementation

The accepted implementation paths are:

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

Approved local candidate provenance:

```text
candidate_commit = 3a2ede63e7e0c0ef86a248080c90a7b50c2370cf
candidate_tree = 824ed493affaa1ea4277f846bba6f6344966a72c
candidate_parent = a0d7f324b7c49b6f2bfc7b586843ab77172cbe17
review_zip_sha256 = 4dc7567cb3a1363eda026ce3a79d5a76b0915e68ea71e2c32f1b4c781725a296
```

The local candidate commit itself need not become canonical. Canonical installation is by exact reviewed bytes onto the exact canonical base.

## 4. B1 capability and implementation theorem

B1 is a read-only account/subaccount capability-and-facts probe.

Its future separately authorized venue surface remains exactly:

```text
GET /trade-api/v2/account/limits
GET /trade-api/v2/api_keys
GET /trade-api/v2/portfolio/subaccounts/balances
GET /trade-api/v2/portfolio/subaccounts/netting
```

under:

```text
https://external-api.demo.kalshi.co
```

with:

```text
PER_REQUEST_DEADLINE_MS = 10000
GLOBAL_EXECUTION_DEADLINE_MS = 40000
MAX_RESPONSE_BYTES_PER_REQUEST = 262144
MAX_TOTAL_RESPONSE_BYTES = 1048576
automatic_retry_count = 0
maximum_redirect_count = 0
```

The implementation is installed and offline-tested. Installation does not constitute execution authorization.

## 5. Historical primary state remains held

The accepted historical primary conflict domain remains:

```text
KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0
```

and remains:

```text
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
historical_primary_safe_to_reuse_proven = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

B1 installation does not reconcile, release, or make reusable the historical primary domain.

## 6. Current B1 readiness state

After canonical installation:

```text
B1_SPECIFICATION = INSTALLED_ACCEPTED
B1_IMPLEMENTATION = INSTALLED_APPROVED_OFFLINE
B1_AUTHENTICATED_DEMO_EXECUTION_AUTHORIZED = false
B1_EXECUTION_RESULT = NOT_RUN
B1_ROUTE_RESULT = NOT_AVAILABLE
```

No subaccount identity, account-wide enumeration theorem, current-key restriction theorem, or creation-capability fact is asserted merely because the implementation exists.

## 7. Next bounded stage

The next enabling task is a separately authorized:

```text
B1_AUTHENTICATED_DEMO_READ_ONLY_EXECUTION
```

Before any venue-capable call, that task must bind task-current official source evidence required by the controlling B1 specification and must explicitly permit the exact four authenticated Demo GETs.

This checkpoint does not authorize that task merely by naming it.

No B2, B3, B4a, B4b, B5, B6, B7, or B8 stage is authorized by this checkpoint.

## 8. Restart routing

For fresh-chat restart:

1. read root `START_HERE.md`;
2. read `project_context/START_HERE.md`;
3. read `project_context/PROJECT_STATE.md`;
4. apply `project_context/PROJECT_STATE_CHECKPOINT_2026_08_26_ROUTE_A_A4.md`;
5. apply `project_context/PROJECT_STATE_CHECKPOINT_2026_08_27_MANUAL_RESTING_CANCEL_CANARY.md`;
6. apply this B1 implementation checkpoint;
7. when working on B1, read the exact installed B1 specification, handoff, implementation review, source, and tests.

This checkpoint grants no credentials, venue access, venue writes, production access, persistent-state mutation, writer-proof release, or later Route-B capability.
