# PROJECT_STATE_CHECKPOINT_2026_09_06_R1_B02_CORRECTION_04_D07_READ_ONLY_LIVE_ENTRYPOINT_SPECIFICATION

Authority level: canonical current-state overlay when installed on canonical main.

This checkpoint captures the Marco-approved R1-B02/11 **Correction 04** milestone
for the R1-D07 read-only Stage-3 live-entrypoint specification **and** the
Marco-approved, canonically installed R1-D07 Correction-04 live-entrypoint
**implementation**, so that a fresh ARB chat does not need prior chat history to
know that Correction 03 was blocked and why, that Correction 04 was approved,
the exact D07 read-only combined execution capability theorem, the corrected
orderbook deadline architecture, the credential compatibility convention, the
complete implementation correction lineage (the blocked non-canonical seed
candidate, the Correction-01/02/03 blocked candidates, and the approved
Correction-04 successor), the exact installed implementation identity, the
remaining live-execution prerequisites, and the next bounded action.

It does **not** itself implement the D07 live entrypoint and does **not**
authorize live execution, credential use, venue access, production, Stage 3G+,
R1-D08, or any remote Git write of its own. It is documentation/current-state
overlay only. The implementation installation recorded in A12 was performed by a
separate, separately authorized canonical installation task; recording that
installation is historical Git provenance and grants no execution capability.

The raw Correction-03/04 specification, handoff, and Marco review/approval
artifacts are **not repository-resident**; they are referenced here by exact
byte length and SHA-256. The implementation Marco review/approval handoffs, the
reviewed Correction-04 submission bundle, and the canonical-installation
result/report are likewise **not repository-resident** and are referenced here
by exact byte length and SHA-256.

---

## A1. Canonical substrate

```text
precanonicalization_main   = d65af8c343df05df0a6810a0778a125e834ccd12
precanonicalization_tree   = e1c8225d4b588e5926d60636319a811729caf94c
precanonicalization_parent = 66de67d45d40f0edab77353f567270eea79211c5
repository                 = rigolugo/ARB
```

This checkpoint's own original canonicalization candidate was prepared as one
documentation-only commit whose parent is exactly
`d65af8c343df05df0a6810a0778a125e834ccd12`.

The later R1-D07 Correction-04 **canonical continuity** update to this same
checkpoint path is prepared as one further documentation-only commit whose
parent is exactly the installed implementation commit:

```text
continuity_base_main   = 4c95fa72cdb7fd420950a2937629c253206f2e5f
continuity_base_tree   = 71c3a37f3f7f521a3e83ced1ab45623a366dce5e
continuity_base_parent = 6e3c2348fc784d295e9406ec110d929a4b000c89
```

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

That future implementation correction has since occurred and the correction loop
is now closed. See A10 for the complete implementation correction lineage, A11
for the accepted Correction-04 implementation candidate evidence and installed
payload identities, and A12 for the canonical installation evidence. This A7
blocked-predecessor record is preserved unchanged, and
`f0e5b19bb4635393fdcaf45ece56dca250b06537` is confirmed absent from the
installed implementation's ancestry.

## A8. Current R1-D07 state and next action

```text
R1-D07 market-selection empirical preparation   = ACCEPTED HISTORICAL INPUT EVIDENCE
R1-D07 live-entrypoint availability diagnostic  = PREFLIGHT_LIVE_ENTRYPOINT_UNAVAILABLE
R1-D07 live-entrypoint specification            = CORRECTION_04 APPROVED_AND_CANONICALLY_REFERENCED
R1-D07 live-entrypoint implementation           = CORRECTION_04 APPROVED_AND_CANONICALLY_INSTALLED
R1-D07 implementation correction loop           = CLOSED
installed implementation commit                 = 4c95fa72cdb7fd420950a2937629c253206f2e5f
installed implementation tree                   = 71c3a37f3f7f521a3e83ced1ab45623a366dce5e

D07 live execution      = NOT_AUTHORIZED
Kalshi/credential use   = NOT_AUTHORIZED
venue writes            = NOT_AUTHORIZED
production              = NOT_AUTHORIZED
Stage 3G+               = NOT_AUTHORIZED
R1-D08                  = NOT_AUTHORIZED
```

The `R1-D07 offline implementation correction = NEXT_BOUNDED_ACTION` route
recorded at this checkpoint's original preparation is **superseded and no longer
current**. That correction loop ran to completion: its Correction-04 successor
was Marco-approved and canonically installed on `main` (A10, A11, A12).

Installation of an implementation is not an execution authorization. The
installed read-only live entrypoint exists in canonical source, and it must not
be run against any venue until a separate task explicitly authorizes that run.

### Next bounded action

```text
NEXT_BOUNDED_ACTION =
  R1-D07 read-only live-preflight readiness/input/freshness preparation
  for a later separately authorized execution task.

This does NOT itself create an execution capability envelope, authorize
credential use, perform task-current source retrieval, access Kalshi, mutate
the real N1 ledger, or run the live preflight.
```

The historical `P03_C2` selected ticker
`KXNCAAFGAME-26SEP05CLEMLSU-CLEM` is a historical D07 read-only preflight input
only. It is **not** a standing or fresh live-run input. Any future real
preflight requires task-current freshness / revalidation.

Known later live-run inputs that remain separately required before any real D07
run:

```text
exact accepted bootstrap_contract_sha256                     = UNRESOLVED
exact accepted risk-config artifact + sha256                 = UNRESOLVED
exact external execution-authorization capability-envelope JSON + sha256
    (with the exact Correction-04 thirteen-field pattern, incl. demo_public_reads = PERMITTED)
                                                             = UNRESOLVED
exact installed implementation identity (Git commit)
    = RESOLVED -> 4c95fa72cdb7fd420950a2937629c253206f2e5f
task-current source / freshness binding                      = UNRESOLVED
explicit permission for the bounded restricted-session STARTED/ENDED local
    lifecycle appends                                        = UNRESOLVED
exact fresh ticker / input state for that preflight          = UNRESOLVED
```

Only the installed implementation identity is resolved. Every input still marked
`UNRESOLVED` must be supplied or separately authorized by a later bounded task.
None of them may be synthesized, inferred, defaulted, or carried over from
historical evidence.

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

That re-establishment has since occurred. The accepted offline validation
carried by the approved and canonically installed Correction-04 implementation
candidate `4c95fa72cdb7fd420950a2937629c253206f2e5f` is:

```text
host-readiness = 1 passed
focused        = 1564 passed + 21 subtests, 0 failed
full           = 3493 passed + 570 subtests, 0 failed, exit 0
```

These are offline test results only. They are not live-venue evidence, do not
prove venue behavior, and do not authorize a D07 live run.

## A10. R1-D07 implementation correction lineage

The offline implementation of the Correction-04 D07 read-only Stage-3 live
entrypoint required four review cycles after the initial blocked seed candidate.
The complete lineage is:

```text
initial blocked implementation candidate
  commit = f0e5b19bb4635393fdcaf45ece56dca250b06537
  status = BLOCKED_NONCANONICAL_CONTENT_SEED_ONLY
  the existing A7 record of this candidate is preserved unchanged
  Marco review handoff
    R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_MARCO_REVIEW_HANDOFF_01.md
    bytes  = 8503
    sha256 = e3b473da7d7579ef378ee5fa9eaefe51ef91f92205b450d8876914d7965452ba

Correction-01 candidate
  commit   = cd538f8733729424c548a811a41585c16cf60d5e
  decision = BLOCK
  Marco handoff
    R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_01_MARCO_REVIEW_HANDOFF_01.md
    bytes  = 12332
    sha256 = 21ca91336a7057a9859555864e2d016596b0b74edde507d1be73e2c9c3cf6711
  material blockers
    production active-V2 arbitrary-callable seam;
    direct live-boundary confirm bypass;
    stale generic transport deadline;
    incomplete bounded-exception scope

Correction-02 candidate
  commit   = d1b57763cfac00bd0f765e3fba8af9154ca84307
  decision = BLOCK
  Marco handoff
    R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_02_MARCO_REVIEW_HANDOFF_01.md
    bytes  = 10505
    sha256 = 8622ba37247af2b5b2e29f613417bda2a1764510cab0037013a9ef64a7a3e7f6
  material blocker
    the same absolute request deadline was not load-bearing through the
    complete high-level generic transport

Correction-03 candidate
  commit   = c7833e8d63c84540951356931d4c3af80a1d02ec
  decision = BLOCK
  Marco handoff
    R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_03_MARCO_REVIEW_HANDOFF_01.md
    bytes  = 9057
    sha256 = 09ac1b1f71f1f4bdfb0613a159759847b4cad84dd9aeaeacebaf4043f3a0b037
  material blocker
    the DNS queue wait retained a stale pre-thread-start relative timeout

Correction-04 accepted candidate
  commit   = 4c95fa72cdb7fd420950a2937629c253206f2e5f
  tree     = 71c3a37f3f7f521a3e83ced1ab45623a366dce5e
  parent   = 6e3c2348fc784d295e9406ec110d929a4b000c89
  decision = APPROVE
  Marco approval handoff
    R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_04_MARCO_APPROVAL_HANDOFF_01.md
    bytes  = 5928
    sha256 = dd0702e160d62fc0092b29671193557d1b7e1dd190a3046ba08abdd21d972519
  status   = APPROVED_AND_CANONICALLY_INSTALLED
  closure  = the DNS helper receives the exact request deadline and the exact
             bound runtime clock, performs a pre-start deadline check, starts the
             single daemon resolver worker, then recomputes the queue wait budget
             from that same absolute deadline immediately before the queue read;
             an exhausted deadline never enters the queue wait
```

```text
R1-D07 implementation correction loop = CLOSED
```

Each blocked candidate above remains blocked historical lineage only. None of
them is approved implementation authority, and none of them is Git ancestry of
the installed implementation.

## A11. Accepted Correction-04 implementation candidate evidence

Exact reviewed Correction-04 candidate review evidence:

```text
outer submission bundle
  R1D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_04_MARCO_SUBMISSION_BUNDLE.zip
  bytes  = 371671
  sha256 = 58dd90554e2d3fea21b3c4dbdbd307e52a5eb970252ecf8061f8b48524453d74

inner review ZIP
  R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_04_MARCO_REVIEW.zip
  bytes  = 355353
  sha256 = 532503ce4875ef08dcaa13d93bbca27d9a09478050d52846dc5b222a843eede8

candidate.patch
  bytes  = 255941
  sha256 = 91ccb234e66635564bd38aa143d2e1a611ffa76a35d2e62441d51154005a5806
```

Exact installed payload, at the four-path direct edit set fixed by A4:

```text
src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py
  bytes  = 570530
  sha256 = 02dec750e2a51a0ee76db2fca5ff130b4ac3c65927c278e94fa52daea004cd19
  blob   = 061eae94efcecf694002b3dd9e07834951d6dc29

tests/test_kalshi_minimal_market_maker_experiment_runner.py
  bytes  = 574022
  sha256 = 0d338433fd996dc0152019799dfd5dbc99abba4c9273343c1bd8a98147f7514d
  blob   = 67b201d3a0cad5de9bef8c0f8eb2c86c5d730178

src/arb/venues/kalshi/orderbook.py
  bytes  = 115667
  sha256 = 0546f95f2560a480b45dda30fb14c939fd9721b74ab2ba0f720a55ff83fdfd08
  blob   = 4d0c8b8407ddb941decaa5cf6a493ac6ab3063c5

tests/test_kalshi_authenticated_orderbook.py
  bytes  = 148363
  sha256 = d788cbda777ccca85b1fda3008de479a054b56f3d26c0dbf98ec0e60bbbbea4e
  blob   = 40df77cc472aff9b93e84bf97e075e7d283c8c57
```

`models.py`, `validation.py`, and `serialization.py` remained readable-PROTECTED
as required by A4; no new module was added.

The accepted final offline validation carried by this reviewed candidate is
recorded in A9.

The raw review bundles and handoffs remain external/local. Only their exact byte
lengths and SHA-256 identities above are canonical.

## A12. Canonical installation evidence

The approved Correction-04 implementation candidate was installed on canonical
`main` by a separate, separately authorized installation task:

```text
task_id    = R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_04_CANONICAL_INSTALLATION_01
repository = rigolugo/ARB
remote_ref = refs/heads/main
installed_at_utc = 2026-09-08T17:02:10Z

transition = 6e3c2348fc784d295e9406ec110d929a4b000c89
          -> 4c95fa72cdb7fd420950a2937629c253206f2e5f
push_mode  = NON_FORCE_FAST_FORWARD
force_push = 0
only refs/heads/main intentionally changed

postinstall_remote_main   = 4c95fa72cdb7fd420950a2937629c253206f2e5f
postinstall_remote_tree   = 71c3a37f3f7f521a3e83ced1ab45623a366dce5e
postinstall_remote_parent = 6e3c2348fc784d295e9406ec110d929a4b000c89
changed_path_count        = 4
```

Installation evidence identities:

```text
R1D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_04_CANONICAL_INSTALLATION_01_INSTALLATION_RESULT.json
  bytes  = 7558
  sha256 = f941652e506f7570b186854f9d079c236391518a8e6ce7a8b4d0beefd448806d

R1D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_IMPLEMENTATION_01_CORRECTION_04_CANONICAL_INSTALLATION_01_INSTALLATION_COMPLETION_REPORT.md
  bytes  = 10535
  sha256 = e5305c11d25ad486936d5c32bedbf668c6755caa1b3542d5f3338ce7f5569909
```

The installation task confirmed that none of

```text
c7833e8d63c84540951356931d4c3af80a1d02ec
d1b57763cfac00bd0f765e3fba8af9154ca84307
cd538f8733729424c548a811a41585c16cf60d5e
f0e5b19bb4635393fdcaf45ece56dca250b06537
```

is ancestry of the installed commit.

The installation result and completion report are direct Git installation
evidence for exactly that repository, ref, and time. They prove the exact
canonical installation only. They do **not** prove live venue behavior, do not
constitute Demo or production execution evidence, and do not authorize
execution. The installation task itself performed no Kalshi request, no real
credential use beyond ambient Git remote authentication, no venue write, no
production activity, no project test or runtime execution, and no real N1
deployed-state access. Both raw files remain external/local and are canonical
here only by the exact identities above.

## A13. R1-D07 read-only local-state readiness result

A separately dispatched, Marco-approved bounded read-only task inspected the
local Windows execution root for the persistent ARB control-plane state that the
installed D07 architecture will require before any real live run. It made zero
Kalshi/API requests and performed zero persistent-state mutations.

```text
local_state_readiness_task
  = R1-D07_READ_ONLY_STAGE3_LIVE_PREFLIGHT_LOCAL_STATE_READINESS_READ_ONLY_01

terminal_classification
  = LOCAL_STATE_READINESS_COMPLETE__PARTIAL_UNRESOLVED

probe_scope
  = read-only local filesystem/SQLite inspection within C:\b1\kals

canonical_repository_root
  = C:\b1\kals\ARB
  status = RESOLVED_FROM_VERIFIED_LOCAL_STATE

target_conflict_domain
  = KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=1

matching local ARB authority store for target conflict domain
  = NOT_FOUND within authorized root at probe time

authority_namespace_id
  = UNRESOLVED_NOT_FOUND

authority_namespace_root
  = UNRESOLVED_NOT_FOUND

expected_ledger_path
  = UNRESOLVED_NOT_FOUND

bootstrap_contract_sha256
  = UNRESOLVED_BOOTSTRAP_NOT_PERSISTED
```

### A13.1 Required semantic distinction

This local negative finding does NOT mean Kalshi Demo subaccount N1 is absent.

The previously qualified Kalshi Demo N1 execution domain remains accepted
historical empirical evidence:

```text
account_scope_ref = ARB_KALSHI_DEMO_PRIMARY_ACCOUNT
subaccount        = 1
exchange_index    = 0
```

The new negative finding is only:

```text
no corresponding local ARB persisted authority / active-ledger / bootstrap
state for that N1 domain was found inside C:\b1\kals at probe time.
```

This canonicalization does not claim task-current remote existence was
reverified by the probe; the probe made zero Kalshi/API requests.

### A13.2 Archived non-target N0 finding

```text
The only discovered ARB persistent state was an archived historical
SUBACCOUNT=0 legacy-import authority/ledger pair under
C:\b1\kals\Archive\arb_state\kalshi_demo_primary_v1\.

It is non-target historical evidence and MUST NOT be renamed, rebound, copied,
or treated as N1 persistent state.
```

The archived path contents are not current N0 runtime-state claims.

### A13.3 Evidence identity

```text
local-state review ZIP
  R1-D07_READ_ONLY_STAGE3_LIVE_PREFLIGHT_LOCAL_STATE_READINESS_READ_ONLY_01_MARCO_REVIEW.zip
  bytes  = 22072
  sha256 = b49256109746a1e772107aa5e36a57f84697fd2e740d52369d5a1fa43bddb097

Marco approval handoff
  R1-D07_READ_ONLY_STAGE3_LIVE_PREFLIGHT_LOCAL_STATE_READINESS_READ_ONLY_01_MARCO_APPROVAL_HANDOFF_01.md
  bytes    = 7205
  sha256   = 77bde598fd35909468bbb7c7ffec8324857478ceeee41c03b09a48a2e38b7886
  decision = APPROVE
```

Mutation-proof summary:

```text
persistent_state_mutations = 0
database_write_statements = 0
sqlite_companion_files_created = 0
restricted_session_lifecycle_appends = 0
credential_or_key_reads = 0
Kalshi/venue/API access = 0
repository edits/commits/remote writes = 0
```

The review ZIP is accepted direct empirical/local evidence for exactly the
authorized Windows root and probe time. It proves no local target N1 ARB store
was found inside that boundary; it does not prove global filesystem absence and
does not reverify remote Kalshi state.

### A13.4 Corrected current D07 route

This section supersedes the A8 "Next bounded action" text that names generic
R1-D07 read-only live-preflight readiness/input/freshness preparation as the
next bounded route. That generic-preparation route is no longer current.

```text
NEXT_BOUNDED_ACTION =
  separately specify/review the R1-D07 N1 LOCAL ARB STATE
  CREATION / BOOTSTRAP task for the already-qualified Kalshi Demo N1 domain.

That later state-changing task requires separate explicit local-state-mutation
authorization and an exact accepted bootstrap-contract artifact.

It must not create, fund, recreate, or modify the Kalshi Demo subaccount
itself, choose risk thresholds, access Kalshi, read credentials, issue an
execution-authorization envelope, or run D07.
```

Risk-config approval remains AFTER local N1 state creation/bootstrap. The A8
list of still-`UNRESOLVED` later live-run inputs (`bootstrap_contract_sha256`,
risk-config artifact + sha256, external execution-authorization envelope +
sha256, task-current source/freshness binding, restricted-session lifecycle
append permission, fresh ticker/input state) is unchanged; only the installed
implementation identity `4c95fa72cdb7fd420950a2937629c253206f2e5f` remains
resolved. `R1-D07 live execution = NOT_AUTHORIZED`.

This section is documentation/current-state overlay only. It authorizes no
local-state creation/bootstrap, no ledger or authority mutation, no risk-config
selection, no credential use, no Kalshi/venue access, no execution envelope, no
live run, no production, no Stage 3G+, and no R1-D08.

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

This checkpoint further supersedes its **own** earlier preparation-time text
only where that text states that the R1-D07 offline implementation correction is
the next bounded action, that the Correction-04 live-entrypoint implementation is
unresolved or pending, or that the Correction-04 implementation has not been
installed on canonical `main`. Its Correction-02/03/04 specification lineage and
exact identities, the D07 combined execution capability theorem, the preserved
orderbook deadline architecture, the credential compatibility convention, the
restricted-session lifecycle theorem, the A7 blocked-predecessor record, and the
Correction-04 `T179`/`T180` test theorem are preserved unchanged.

This checkpoint grants no production capability, no venue write, no credential
use, no Kalshi access, no D07 live execution, no Stage 3G+, no remote Git write,
no further `main` installation, and no R1-D08 authorization. The
already-completed canonical installation recorded in A12 is historical Git
provenance for exactly that transition; it is not an execution authorization and
does not prove live venue behavior.
