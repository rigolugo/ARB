APPROVE

# REVIEW — KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_IMPLEMENTATION_01

## Reviewed controlling artifacts

Specification:

```text
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md
raw_bytes = 54469
sha256 = 0265953846cd48105a1d20d79453d6dfdb92310c38f9a8a06295fa32dceae500
```

Subordinate handoff:

```text
HANDOFF_KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md
raw_bytes = 10518
sha256 = 31d8ed23b7b4eb2e2cd6a834b5dbcd2374ce4abc06a6ad633be6dff85604b53f
```

Exact approved implementation review package:

```text
KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_IMPLEMENTATION_01_CORRECTION_04_MARCO_REVIEW.zip
raw_bytes = 113295
sha256 = 4dc7567cb3a1363eda026ce3a79d5a76b0915e68ea71e2c32f1b4c781725a296
```

Approved local candidate provenance:

```text
candidate_commit = 3a2ede63e7e0c0ef86a248080c90a7b50c2370cf
candidate_tree = 824ed493affaa1ea4277f846bba6f6344966a72c
candidate_parent = a0d7f324b7c49b6f2bfc7b586843ab77172cbe17
```

Approved implementation payload:

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

Reviewed against canonical repository base:

```text
repository = rigolugo/ARB
branch = main
review_base = a0d7f324b7c49b6f2bfc7b586843ab77172cbe17
review_base_tree = 9f5b5c413ffb6f7cb901a3a68654143617461155
review_base_parent = 997954197ebb8cbfb13baa3231b490abfbe20f64
```

## Review result

Correction 04 closes the final material implementation defect under the controlling B1 specification.

The accepted implementation preserves:

```text
Demo-only HTTPS/443
exact host external-api.demo.kalshi.co
GET only
exact four B1 paths
empty query and body
maximum 4 requests
one attempt per path
automatic retries = 0
redirects = 0
no compatibility-host fallback
no production
no WebSocket
no endpoint discovery
```

The complete request lifecycle is deadline bounded:

```text
PER_REQUEST_DEADLINE_MS = 10000
GLOBAL_EXECUTION_DEADLINE_MS = 40000
```

The B1 runner structurally bounds:

```text
Transport.perform(request, timeout_ms)
ResponseBodyReader.read(max_bytes, timeout_ms)
ResponseBodyReader.close(timeout_ms)
```

and preserves the controlling terminal precedence through post-close result projection.

Response-body limits remain:

```text
MAX_RESPONSE_BYTES_PER_REQUEST = 262144
MAX_TOTAL_RESPONSE_BYTES = 1048576
```

The historical primary domain remains unchanged:

```text
writer_proof_state = HELD
historical_unresolved_exposure = UNKNOWN_UNBOUNDED
normal_writer_eligible = false
CANARY_EXECUTION_DOMAIN_READINESS = NO_VALID_CANARY_EXECUTION_DOMAIN_PROVEN
CANARY_REAL_EXECUTION_ELIGIBLE = false
```

The B1 implementation cannot release or reconcile that historical primary domain.

## Test evidence

Exact approved candidate evidence included:

```text
focused = 175 passed
protected regressions = 327 passed, 70 subtests
full offline = 2901 passed, 555 subtests
```

Marco independently reran the exact packaged focused suite:

```text
175 passed
```

and independently verified the new Correction-04 negative-control tests distinguish the blocked Correction-03 behavior.

## Acceptance boundary

This review approves the exact implementation candidate for canonical installation.

It does not authorize:

```text
authenticated B1 Demo GET execution
credential or private-key use
real signing
Kalshi network access
subaccount creation
funding or transfer
netting modification
order activity
persistent-state mutation
historical primary-domain release
production activity
B2-B8
```

A separately bounded execution task with task-current official-source evidence is required before authenticated B1 Demo reads.

## Current accepted state

```text
B1 specification = ACCEPTED
B1 implementation = APPROVED_FOR_CANONICAL_INSTALLATION
B1 authenticated Demo execution = NOT AUTHORIZED BY THIS REVIEW
historical primary writer proof = HELD
historical primary exposure = UNKNOWN_UNBOUNDED
normal writer eligible = false
```
