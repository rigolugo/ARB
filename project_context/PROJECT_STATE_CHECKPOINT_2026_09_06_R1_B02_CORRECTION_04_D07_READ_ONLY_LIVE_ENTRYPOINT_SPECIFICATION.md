# PROJECT_STATE_CHECKPOINT_2026_09_06_R1_B02_CORRECTION_04_D07_READ_ONLY_LIVE_ENTRYPOINT_SPECIFICATION

Authority level: canonical current-state overlay when installed on canonical main.

This checkpoint captures the Marco-approved R1-B02/11 **Correction 04** milestone
for the R1-D07 read-only Stage-3 live-entrypoint specification, so that a fresh
ARB chat does not need prior chat history to know that Correction 03 was
blocked and why, that Correction 04 was approved, the exact D07 read-only
combined execution capability theorem, the corrected orderbook deadline
architecture, the credential compatibility convention, the remaining
live-execution prerequisites, and the next bounded action.

It does **not** implement the D07 live entrypoint and does **not** authorize
live execution, credential use, venue access, production, Stage 3G+, remote Git
writes, or `main` installation. It is documentation/current-state overlay only.

The raw Correction-03/04 specification, handoff, and Marco review/approval
artifacts are **not repository-resident**; they are referenced here by exact
byte length and SHA-256. They must be supplied by exact bytes/SHA in the next
implementation dispatch.

---

## A1. Canonical substrate

```text
precanonicalization_main   = d65af8c343df05df0a6810a0778a125e834ccd12
precanonicalization_tree   = e1c8225d4b588e5926d60636319a811729caf94c
precanonicalization_parent = 66de67d45d40f0edab77353f567270eea79211c5
repository                 = rigolugo/ARB
```

This checkpoint's own canonicalization candidate is prepared as one
documentation-only commit whose parent is exactly
`d65af8c343df05df0a6810a0778a125e834ccd12`.

## A2. Specification lineage

### Correction 02 — incorporated predecessor lineage

```text
KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL_SPEC_01_CORRECTION_02.md
  bytes  = 103964
  sha256 = 6e642fa488d171715a8b12794cbc0c7d896583aa03b968011b0c316a749efd74
HANDOFF_KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL_SPEC_01_CORRECTION_02.md
  bytes  = 17671
  sha256 = 7b1c1bb818acfd179f21f0b3643fd473d0c8f225ad51033529fa73c91731a50a
R1-B02_CORRECTION_02_MARCO_APPROVAL_HANDOFF.md
  bytes  = 3327
  sha256 = 71480b62577e93754d12a1f3d1bc4e6c1ef5586ad67d85f3a96805239bba0f62
```

### Correction 03 — BLOCKED historical lineage

```text
KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL_SPEC_01_CORRECTION_03.md
  bytes  = 67570
  sha256 = 83c03371a0483b8b61d7da54e89807a13b6ea765a8078522c80b17b0c04be621
HANDOFF_KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL_SPEC_01_CORRECTION_03.md
  bytes  = 15212
  sha256 = 96c39e271f80698815fb44625796864ef31ead46216b64e76d9a8bb60c774d11
R1-B02_CORRECTION_03_MARCO_REVIEW_HANDOFF_01.md   (Marco BLOCK handoff)
  bytes  = 4999
  sha256 = 30cff0cdbfa3d46980bac8cae48cfc8e9cf1a1f64b4cacf8da6e3f529e7bee35
BLOCK = BLOCK-C03-01 -- the D07 external execution capability envelope omitted the required
        demo_public_reads = PERMITTED capability while the frozen D07 read set performs
        GET_EXCHANGE_STATUS, GET_USER_DATA_TIMESTAMP, and GET_MARKET (unsigned Demo public reads).
```

### Correction 04 — APPROVED

```text
KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL_SPEC_01_CORRECTION_04.md
  bytes  = 33622
  sha256 = e50b751e4e6449ef86e49319d9d044c9c2ca2c37d749bf5ae96cf49ab9e062ea
HANDOFF_KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL_SPEC_01_CORRECTION_04.md
  bytes  = 17142
  sha256 = 48d726b1aa7c874324869dde6d2135b4618325f6f298b2e1ef24c3d4ce82a582
R1-B02_CORRECTION_04_DELIVERY_MANIFEST.txt
  bytes  = 2532
  sha256 = 3acbec845db58d1a9ccf31f9aa5582f0102d4aac0296800d34b99dd2b5218322
R1-B02_CORRECTION_04_KALSHI_DEMO_DYNAMIC_SUBACCOUNT_SPEC_MARCO_REVIEW.zip
  bytes  = 20065
  sha256 = 073b1642c554877490fc23f2cd9b012bf4a0a008afcca9b840721af3911b6146
R1-B02_CORRECTION_04_MARCO_APPROVAL_HANDOFF.md
  bytes  = 4622
  sha256 = 6bf41765c2c7fd8cdc7ece758056f54067bd72c666af4728d93c91f8dc346877
  decision = APPROVE
```

Explicit state:

```text
Correction 04 is the approved controlling D07 specification successor.
Correction 03 remains blocked historical lineage (not approved implementation authority).
Correction 02 remains incorporated predecessor lineage (Marco-approved).
```

The Correction-03/04 raw specification/handoff/review artifacts are **not
repository-resident**. Only their exact identities above are canonical. They
must be re-supplied by exact bytes/SHA-256 in the next implementation dispatch.

## A3. Exact D07 combined execution capability theorem (Correction 04)

The one external D07 task capability envelope has all thirteen canonical
`models.py CAPABILITY_ENVELOPE_FIELDS` fixed to exactly these values (an exact
set, not a minimum):

```text
PERMITTED (exactly these four):
  network_access
  demo_public_reads
  demo_authenticated_reads
  credential_use

PROHIBITED (exactly these nine):
  demo_writes
  production_public_reads
  production_authenticated_reads
  production_writes
  account_funding
  code_changes
  tests
  artifact_generation
  repository_commits
```

`demo_public_reads = PERMITTED` is required because the frozen D07 closed
active-V2 read set performs unsigned Demo public network reads
(`GET_EXCHANGE_STATUS`, `GET_USER_DATA_TIMESTAMP`, `GET_MARKET` --
`PUBLIC_NO_AUTH`) as well as signed Demo authenticated reads
(`GET_MARKET_ORDERBOOK`, `GET_ORDERS`, `GET_ORDER`, `GET_FILLS`,
`GET_POSITIONS` -- `DEMO_SIGNED_PRIVATE_READ`).

`artifact_generation = PROHIBITED`: the D07 read-only live entrypoint emits
only deterministic classification-only data to stdout / the returned result
mapping and writes no artifact file. Correction 04 adds no artifact-generation
exception; any later bounded file-artifact-output capability is granted
explicitly by a later, separately authorized execution package.

Deviation handling: an envelope whose thirteen fields are not exactly this
pattern (a required PERMITTED capability not `PERMITTED`, or a required
PROHIBITED capability `PERMITTED`) fails closed under the existing
Correction-03 `LIVE_EXECUTION_AUTHORIZATION_TOO_BROAD` classification. Correction
04 introduces no new failure classification. `LIVE_EXECUTION_AUTHORIZATION_UNVERIFIED`
(hash/parse/invariant) and `LIVE_EXECUTION_AUTHORIZATION_ID_MISMATCH`
(authorization-id binding) are preserved.

The external capability-envelope JSON is verified by SHA-256, parsed via the
canonical `serialization.parse_capability_envelope_json`, checked with
`models.require_usable_capability_envelope`, and then checked against this exact
thirteen-field pattern -- all before risk-config file I/O, authority binding,
restricted-session lifecycle, runtime construction, credential loading, and any
venue/network activity.

The combined task-level D07 envelope is not, and must not be substituted for,
an operation-local pure public `ValidatedDemoProfile` (whose operation-local
canonical rule requires `credential_use is PROHIBITED`). The D07 entrypoint
builds a `DEMO_AUTHENTICATED_READ` profile for the canonical orderbook path and
its own runner-local transport for the seven non-orderbook operations; it never
builds a pure-public `ValidatedDemoProfile` against the combined envelope.

`--confirm-live-read` is only a technical interlock and never an authorization
grant. The later live read-only Stage-3A-3F run proceeds only when BOTH a
verified external SHA-bound capability envelope satisfying the exact
thirteen-field pattern AND `--confirm-live-read` are present; neither
substitutes for the other.

## A4. Preserved Correction-03 architecture (specification level)

```text
- canonical legacy execute_demo_authenticated_orderbook(plan) remains valid for
  every existing caller with unchanged signature and observable 10-second-from-entry
  deadline behavior;
- the later implementation adds exactly one narrow operation-local primitive:
    execute_demo_authenticated_orderbook_within_deadline(
        plan, *, caller_deadline_monotonic_ns,
        caller_monotonic_clock_ns=_current_monotonic_ns)
  whose effective deadline is min(caller_deadline_monotonic_ns, entry + 10000 ms),
  never reset or extended, reusing all inherited signing/TLS/DNS/body-cap/parser/
  current-value/source-binding logic, introducing no generic HTTP client/signer;
- active-V2 GET_MARKET_ORDERBOOK integration: all local AuthenticatedOrderBookInput
  construction + plan_demo_authenticated_orderbook + local request-identity
  construction occur BEFORE the pre-release budget charge (zero budget); exactly
  one charge immediately before the deadline-aware primitive; the primitive is
  the first transport-side action; post-charge inherited current-value gates are
  transport-bound anti-TOCTOU checks and any halt after the charge consumes the
  charged unit (no refund, no retry, no redirect followed);
- the exact caller active OperationDeadlineV1 (its absolute_deadline_monotonic_ns
  field, = min(absolute invocation deadline, op start + 10000 ms)) remains
  load-bearing through final accepted result construction and cannot be
  reset/extended;
- one 300-second absolute Stage-3 invocation deadline is sampled once at the top
  of the live execution boundary -- before external-authorization file I/O,
  risk-config file I/O, authority binding, restricted-session lifecycle,
  gate/runtime construction, or venue reads -- threaded through
  build_active_experiment_runner_runtime_v2 and never reset;
- generic non-orderbook private signed-GET transport is deterministic and
  secret-safe: closed credential-header safety validation before send; bounded
  TLS/socket/http/header exception set mapped to fixed RunnerError
  classifications; no raw exception text / no secret / no header value in
  stdout / stderr / result / exception detail; zero automatic retry; zero
  followed redirect; MAX_RESPONSE_BODY_BYTES body cap; redacted repr;
- the later implementation direct edit set is exactly four paths:

    src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py
    tests/test_kalshi_minimal_market_maker_experiment_runner.py
    src/arb/venues/kalshi/orderbook.py
    tests/test_kalshi_authenticated_orderbook.py

- src/arb/venues/kalshi/models.py, src/arb/venues/kalshi/validation.py, and
  src/arb/venues/kalshi/serialization.py remain readable-PROTECTED (imported,
  never modified); no new module;
- construction only through build_active_experiment_runner_runtime_v2; execution
  only of run_pre_release_read_phase_v2; no Stage 3G+ / RELEASE_ONLY /
  NORMAL_WRITER / Gate D / CREATE / CANCEL / TRANSFER / production reachability
  from the D07 entrypoint; READ_PHASE_COMPLETE remains NO_WRITE_AUTHORIZATION.
```

## A5. Credential compatibility fact

Operator-local persistent convention (unchanged):

```text
KALSHI_DEMO_API_KEY_ID
KALSHI_DEMO_PRIVATE_KEY_PATH
```

`KALSHI_DEMO_PRIVATE_KEY_PATH` contains the filesystem path to the PEM-format
private-key file. The operator does **not** permanently configure a
PEM-content variable.

The approved design uses a narrow launcher compatibility bridge:

```text
read KALSHI_DEMO_PRIVATE_KEY_PATH
  -> read the referenced PEM file bytes (strict UTF-8)
  -> set a temporary process-local KALSHI_DEMO_PRIVATE_KEY_PEM
  -> invoke the existing canonical PEM-based authenticated-read / orderbook boundary
  -> remove KALSHI_DEMO_PRIVATE_KEY_PEM in a finally-equivalent path on success and failure
```

A pre-existing `KALSHI_DEMO_PRIVATE_KEY_PEM` before the bridge is
credential-source ambiguity and fails closed (`CREDENTIAL_SOURCE_AMBIGUOUS`).
The bridge performs no key generation or conversion, no API-key mutation, no
secret serialization/logging, no fallback to another name/path, and spawns no
child process while the temporary value exists.

## A6. Restricted-session lifecycle

Constructing the mandated active runtime requires a real `EmergencyCancelGate`,
and the accepted active emergency-control acquisition uses the active
restricted-session mechanism. The resulting

```text
RESTRICTED_SESSION_STARTED / RESTRICTED_SESSION_ENDED
```

events are accepted local control-plane lifecycle bookkeeping inherent in the
existing reviewed runtime topology. They are not venue requests, cancel sends,
release events, writer sessions, writer-proof release, or Stage-3G+
continuation. A later real D07 run must **separately authorize** those bounded
persistent local appends in addition to the Demo read-only network/credential
activity. The offline implementation task uses only synthetic/temp ledger
state and must not touch the real N1 deployed authority/ledger.

## A7. Blocked predecessor implementation

```text
candidate_commit = f0e5b19bb4635393fdcaf45ece56dca250b06537
candidate_tree   = ff3ae9c249f79c08344d821ca187f9bed1116af0
candidate_parent = d65af8c343df05df0a6810a0778a125e834ccd12
status           = BLOCKED_NONCANONICAL_CONTENT_SEED_ONLY
```

This candidate implemented `R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01`
against the (now-superseded) Correction-02-only D07 dispatch and was Marco-BLOCKED
(BLOCK-01 external live authorization, BLOCK-02 300 s deadline anchor, BLOCK-03
orderbook active-deadline integration, BLOCK-04 secret-safe generic transport).
Corrections 03 and 04 resolve those findings at the specification level.

The blocked candidate MUST NOT become Git ancestry through merge, cherry-pick,
or rebase. A future implementation correction must be exactly one fresh commit
from the exact then-current canonical base. Blocked-candidate bytes may be used
only as explicitly packaged non-canonical reference content seed.

## A8. Current R1-D07 state and next action

```text
R1-D07 market-selection empirical preparation   = ACCEPTED HISTORICAL INPUT EVIDENCE
R1-D07 live-entrypoint availability diagnostic  = PREFLIGHT_LIVE_ENTRYPOINT_UNAVAILABLE
R1-D07 live-entrypoint specification            = CORRECTION_04 APPROVED_PENDING_CANONICALIZATION (at this checkpoint's preparation)

After this checkpoint is installed on canonical main:
R1-D07 live-entrypoint specification            = CORRECTION_04 APPROVED_AND_CANONICALLY_REFERENCED
R1-D07 offline implementation correction        = NEXT_BOUNDED_ACTION

D07 live execution   = NOT_AUTHORIZED
venue writes         = NOT_AUTHORIZED
production            = NOT_AUTHORIZED
R1-D08               = NOT_AUTHORIZED
```

The historical `P03_C2` selected ticker
`KXNCAAFGAME-26SEP05CLEMLSU-CLEM` is a historical D07 read-only preflight input
only. It is **not** a standing or fresh live-run input. Any future real
preflight requires task-current freshness / revalidation.

Known later live-run inputs that remain separately required before any real D07
run:

```text
exact accepted bootstrap_contract_sha256
exact accepted risk-config artifact + sha256
exact external execution-authorization capability-envelope JSON + sha256
    (with the exact Correction-04 thirteen-field pattern, incl. demo_public_reads = PERMITTED)
exact installed implementation identity (Git commit)
task-current source / freshness binding
explicit permission for the bounded restricted-session STARTED/ENDED local lifecycle appends
exact fresh ticker / input state for that preflight
```

## A9. Tests

Correction-04 test theorem (specification level; no implementation test was
executed in the SPEC_ONLY correction):

```text
T01-T178 preserved exactly, never renumbered or mutated
T179 = demo_public_reads PROHIBITED negative authorization case:
       a canonically valid envelope with the twelve other exact D07 fields correct
       but demo_public_reads = PROHIBITED -> LIVE_EXECUTION_AUTHORIZATION_TOO_BROAD;
       runtime construction NOT entered; network activity = 0; credential reads = 0;
       restricted-session lifecycle appends = 0; no secret in any output
T180 = exact 4-PERMITTED / 9-PROHIBITED positive authorization case:
       an envelope whose thirteen fields are exactly the D07 pattern -> accepted;
       proceeds to the read-only Stage-3A-3F run (run_pre_release_read_phase_v2 only)
```

The earlier blocked R1-D07 implementation candidate reported focused
`1239 passed` and full `3456 passed + 568 subtests` at the offline
implementation task; that evidence belongs to the blocked candidate lineage
and is not accepted implementation. The next bounded implementation correction
re-establishes its own test evidence from the exact then-current canonical
base.

## Supersession relation

This checkpoint supersedes the prior D07 checkpoint
(`PROJECT_STATE_CHECKPOINT_2026_09_05_R1_D07_MARKET_SELECTION_AND_READ_ONLY_PREFLIGHT_PREPARATION.md`)
**only** where that checkpoint states that the R1-D07 live-entrypoint
specification / implementation path is unresolved, pending design, or that the
next bounded source-code task is
`R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01` under a
Correction-02-only dispatch. The prior checkpoint's accepted empirical
market-selection evidence, selector sequence, `is_provisional NOT_EXPOSED`
rule, MVE-exclusion provenance, market-level `exchange_index` selection
authority, incomplete-pagination fail-closed rule, and
`PREFLIGHT_LIVE_ENTRYPOINT_UNAVAILABLE` availability finding are preserved
unchanged.

This checkpoint grants no production capability, no venue write, no credential
use, no Kalshi access, no Stage 3G+, no remote Git write, no `main`
installation, and no R1-D08 authorization.
