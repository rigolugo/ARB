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

## A14. R1-D07 N1 local ARB state creation/bootstrap Correction 01 (Marco-approved specification)

A separately dispatched R1-D07 N1 local ARB state creation/bootstrap
specification was reviewed. The initial `SPEC_01` was Marco-`BLOCK`ed; the
corrected `SPEC_01_CORRECTION_01` was Marco-`APPROVE`d. This section records
the approved specification content only; it does not record or authorize
canonical installation, local-state creation, or bootstrap execution.

### A14.1 Specification lineage

Blocked predecessor (historical lineage only):

```text
KALSHI_DEMO_N1_LOCAL_ARB_STATE_CREATION_AND_BOOTSTRAP_SPEC_01.md
review ZIP:
  bytes  = 29889
  sha256 = 911f1e7e45a3cc5b8e9be146fe1c7e15b780737e2fe3acc668a077ec21cc9c60

Marco BLOCK:
  bytes  = 8058
  sha256 = 2da1787e191a322a50195fe9b0da9ec965a8809b13b091dedd1ec51e98a743d4

blocker =
  EXECUTION_TIME_CANONICAL_IDENTITY_CONFLICT_AFTER_REQUIRED_SPEC_INSTALLATION

classification = BLOCKED_HISTORICAL_LINEAGE_ONLY
```

Approved successor:

```text
KALSHI_DEMO_N1_LOCAL_ARB_STATE_CREATION_AND_BOOTSTRAP_SPEC_01_CORRECTION_01.md
  bytes  = 52930
  sha256 = 24822a18f74a5944bcd9d19a9e4eb3ca7abeb5402ced8779044825e3082a4f8d

HANDOFF_KALSHI_DEMO_N1_LOCAL_ARB_STATE_CREATION_AND_BOOTSTRAP_SPEC_01_CORRECTION_01.md
  bytes  = 8539
  sha256 = e3873c72b71c4702ed2921628a6ea22e4eb57e1e808c8c8ebc6c706c100d475a

DERIVATION_EVIDENCE.json
  bytes  = 25945
  sha256 = 9cb72249e65be9be7ee72d00b16aa6e53d2e85ffab948f0a9b810184e1f01013

SOURCE_TRACEABILITY.md
  bytes  = 8567
  sha256 = 7ea9a5d7beff14f4cce77410e517efb37f487ce128952ef1a522e1f259d8c8c0

REVIEW_MANIFEST.json
  bytes  = 6035
  sha256 = 29686e18a25e675174eec5a785263b5035bc3bd19ec95df769f4b93a2931aa5c

MARCO_REVIEW.zip
  bytes  = 33370
  sha256 = 9b6901477c088066f47947bde4f4ee00471589dd80becab09db7cfb590f23695

MARCO_APPROVAL_HANDOFF_01.md
  bytes    = 8365
  sha256   = 52286b03882e2d946cead25787a09785ed894bc43bab302cbfa2a51e13c30350
  decision = APPROVE
```

All raw artifacts above remain external/local, matching the established R1-D07
controlling-spec canonicalization pattern; they are not repository-resident.

### A14.2 Corrected provenance theorem

```text
SPEC_AUTHORING_BASE
  commit = e7480d24464e7a122993f58e6b3554a629e9aeb4
  tree   = 14c2ad6553d9392b60cbd1ddc9279bdb1901e0c8
  parent = 9fa603642588dd0c0e32ec25f45cb3bcf0f6e133

SOURCE_IMPLEMENTATION_BASE
  commit = e7480d24464e7a122993f58e6b3554a629e9aeb4
  tree   = 14c2ad6553d9392b60cbd1ddc9279bdb1901e0c8
  parent = 9fa603642588dd0c0e32ec25f45cb3bcf0f6e133

frozen source blobs:
  src/arb/execution_ledger.py
    = e39f7f400714510a6a6b32a3dfd5f84125571d5c
  src/arb/venues/kalshi/ledger_binding.py
    = 43b36965466d42c611daa64fec71f86363a3e0f7

INSTALLED_SPEC_CANONICAL_IDENTITY
  status = TO_BE_BOUND_BY_SEPARATE_CANONICAL_INSTALLATION_RESULT
  commit = UNBOUND_AT_CANDIDATE_AUTHOR_TIME
  tree   = UNBOUND_AT_CANDIDATE_AUTHOR_TIME
  parent = UNBOUND_AT_CANDIDATE_AUTHOR_TIME
```

This candidate's own local documentation commit SHA must never be substituted
for the unbound `INSTALLED_SPEC_CANONICAL_IDENTITY` values above; that identity
is an output of a later, separate canonical-installation result only.

Future mutation rule:

```text
current main commit/tree/parent must equal the exact later reviewed
INSTALLED_SPEC_CANONICAL identity

AND

the two load-bearing source blobs at that identity must remain the exact frozen
blobs above.

newer descendant != automatically acceptable
post-install main drift -> fail closed / reviewed refresh required
source blob drift -> reviewed technical successor required
```

### A14.3 Approved local bootstrap contract (specification-level; not yet created)

A13's local state remains physically absent/not-created. A14 supersedes only
the earlier statement that the **specification values themselves** are
unresolved; it does not supersede A13's mutation-proof or absence findings.

Approved planned topology:

```text
authority_topology_gate = AUTHORITY_TOPOLOGY_RESOLVED

authority_namespace_id =
  ARB_KALSHI_DEMO_PRIMARY_AUTHORITY_V1

authority_namespace_root =
  C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority

authority_store =
  C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority\arb_execution_authority_v1.sqlite3

N1_active_ledger =
  C:\b1\kals\arb_state\kalshi_demo_primary_v1\ledger\subaccount1_execution_v2.sqlite3

active_deployment_root =
  C:\b1\kals\arb_state

canonical_repository_root =
  C:\b1\kals\ARB
```

Approved exact path/hash identities:

```text
authority_store_path_identity_sha256
= dbf0afa85aa59c82879cc78e24340d7035074b43879df39eca98a1e3ac83f899

active_ledger_path_identity_sha256
= ab36fd934f013f16795f161f20f1d63daecf8a385bfe260fc3a7bb8945e4d3b3

domain_binding_sha256
= f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02

bootstrap_contract_sha256
= c387e47c2862e6082e75bc8eb8dfa47ed085ec7be98e8426970a278a953e7360

bootstrap_class = KNOWN_NONEMPTY_PRESTACK
bootstrap_cutoff_at_utc = 2026-09-01T23:34:46.398722Z

active_contract_sha256
= f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53

active_incident_id
= adi_2c5c16c8e7299d0e6fccb23caec7c4d4

active_writer_proof_id
= adwp_0b247ef6546e88308017a3168b9ad2b8

bootstrap_event_id
= evt_c078e5802ee65566285f654acfa3bb67
```

Approved preservation set:

```text
retained_position_ticker = KXAAAGASD-26SEP02-4.1200
retained_position_floor_contracts = Decimal("1.00")
automatic_flatten_authorized = false

genesis:
  1 LEDGER_INITIALIZED
  2 EXECUTION_DOMAIN_BOOTSTRAP_RECORDED
  3 WRITER_PROOF_HELD

initial writer proof = HELD
release_eligible = false
venue transport during bootstrap = 0
automatic retry = 0
```

None of these values are yet instantiated as local persistent state; A13's
`NOT_FOUND` / `UNRESOLVED_NOT_FOUND` findings stand unchanged until a separate,
explicitly authorized local N1 bootstrap task creates them.

### A14.4 Archive / N1 distinction (unchanged)

```text
Kalshi Demo N1 already exists and is qualified historical remote/Demo evidence.
This local specification does not create/fund/modify Kalshi N1.

The archived SUBACCOUNT=0 authority/ledger pair remains historical/non-target
and must not be copied, rebound, migrated, renamed, or selected as N1 state.
```

### A14.5 Current route

```text
Correction-01 spec review = APPROVED.

This documentation candidate, if not yet installed on canonical main:
  NEXT = separate canonical installation of the reviewed candidate.

Once this exact canonicalization content is installed on main:
  require reviewed canonical-installation evidence that freezes exact
  INSTALLED_SPEC_CANONICAL_COMMIT/TREE/PARENT.

Only after that installation evidence is accepted:
  NEXT = prepare the one-shot local N1 bootstrap mutation package binding both
  the installed-spec identity and SOURCE_IMPLEMENTATION_BASE/frozen blobs.

Actual local-state mutation still requires a separate explicit user
authorization.

Risk-config work remains after successful local bootstrap + review +
canonicalization.
```

This section grants no local-state creation/bootstrap, no ledger or authority
mutation, no risk-config selection, no credential use, no Kalshi/venue access,
no execution envelope, no live run, no production, no Stage 3G+, and no
R1-D08. Approval/canonicalization of this specification does not itself
authorize local state creation, Kalshi access, credentials, venue writes,
risk-config, D07 live preflight, production, Stage 3G+, or R1-D08.

## A15. R1-D07 N1 local ARB state bootstrap execution (Marco-approved, completed)

A separately dispatched and Marco-approved one-shot local ARB N1 bootstrap
execution has been performed against the approved offline execution package and
an accepted external mutation-authorization artifact. This section canonicalizes
the accepted execution milestone into current state. It records documentation
only; it performs and authorizes no runtime, persistent-state, venue,
credential, release, restricted-session, risk-config, production, Stage 3G+, or
R1-D08 action.

### A15.1 Accepted terminal theorem

```text
terminal_classification            = LOCAL_N1_BOOTSTRAP_COMPLETE
created_at_utc                      = 2026-09-10T18:09:28.812345Z
intent_create_calls                = 1
authority_initialize_calls         = 1
active_ledger_initialize_calls     = 1
automatic_retries                  = 0
venue_requests                     = 0
venue_writes                       = 0
credential_value_reads             = 0
risk_config_ops                    = 0
repo_writes_by_execution           = 0
release_ops                        = 0
restricted_session_appends         = 0
archived_historical_N0_identities  = UNCHANGED
```

### A15.2 Exact three-event genesis (PERSISTED)

```text
1  LEDGER_INITIALIZED
     event_id   = evt_d8022c5bbfd546eaa83811a29bc7fade
     event_hash = 15e04bb6771847a4709a4bfb0951a6dbe694ae31179152aad8ca8624baa7cadd
2  EXECUTION_DOMAIN_BOOTSTRAP_RECORDED
     event_id   = evt_c078e5802ee65566285f654acfa3bb67
     event_hash = e8774fe356d43d573077419b34db818584f56b273ff210b7a87aa5ec4a540629
3  WRITER_PROOF_HELD
     event_id   = evt_1fbb81279f554c88b4b7257950086219
     event_hash = be0d2aa61ee507b5103bfe3d9c0a1387e97ec9d8b2eb97a7d74b4c7f134bc1c7
     incident_id = adi_2c5c16c8e7299d0e6fccb23caec7c4d4
```

### A15.3 Runtime identities (INDEPENDENTLY_VERIFIED local runtime facts)

```text
authority_namespace_id             = ARB_KALSHI_DEMO_PRIMARY_AUTHORITY_V1
authority_runtime_instance_id      = 772b53a9-7915-4133-957b-3d6c24dfdfc7
authority_schema_revision          = 1
authority_trusted_sequence         = 3
authority_trusted_event_hash       = be0d2aa61ee507b5103bfe3d9c0a1387e97ec9d8b2eb97a7d74b4c7f134bc1c7
authority_conflict_domain_row_count_total = 1
authority_store_path_identity_sha256 = dbf0afa85aa59c82879cc78e24340d7035074b43879df39eca98a1e3ac83f899

ledger_runtime_instance_id         = 485b37e9-738d-49f8-99cf-5f2e69589de6
ledger_schema_revision             = 2
ledger_event_count                 = 3
preledger_history_mode             = KNOWN_NONEMPTY_PRESTACK
ledger_path_identity_sha256        = ab36fd934f013f16795f161f20f1d63daecf8a385bfe260fc3a7bb8945e4d3b3

domain_binding_id                  = KEDB1_f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02
domain_binding_sha256              = f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02
bootstrap_contract_sha256          = c387e47c2862e6082e75bc8eb8dfa47ed085ec7be98e8426970a278a953e7360
active_contract_id                 = AEDC1_f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53
active_contract_sha256             = f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53
active_incident_id                 = adi_2c5c16c8e7299d0e6fccb23caec7c4d4
active_writer_proof_id             = adwp_0b247ef6546e88308017a3168b9ad2b8
writer_proof_state                 = HELD
```

### A15.4 Exact accepted external/local evidence identities

Raw files remain external/local and are NOT repository-resident; canonical
reference is by exact bytes / SHA-256 only.

```text
RESULT
  R1-D07_N1_LOCAL_ARB_STATE_CREATION_BOOTSTRAP_EXECUTION_01_RESULT.json
  raw_bytes = 8081
  sha256    = 07728e3f5d48f786e6a7a3a5af8be3847cce41c5a8d2419a8198db61210a12cf

REPORT
  R1-D07_N1_LOCAL_ARB_STATE_CREATION_BOOTSTRAP_EXECUTION_01_REPORT.md
  raw_bytes = 1095
  sha256    = af90167c47cc39b0328dd0a33e7d46883932de77479645ede78c9d41b4452474

DURABLE INTENT
  R1-D07_N1_LOCAL_ARB_STATE_CREATION_BOOTSTRAP_EXECUTION_01_INTENT_V1.json
  raw_bytes = 3122
  sha256    = 1bba4f7c9c4908d7b44ec8238708828c0b293aa09f0a5dc46eb79ed60297c1b6

EXTERNAL MUTATION AUTHORIZATION
  R1-D07_N1_LOCAL_ARB_STATE_CREATION_BOOTSTRAP_EXECUTION_01_MUTATION_AUTHORIZATION_01.json
  raw_bytes = 2625
  sha256    = 48e43aff23d860c3ff4e511d3d8251d721a5aebf14d18523cf59d9e4c981d2cc
  mutation_authorization_ref = R1-D07_N1_LOCAL_ARB_STATE_CREATION_BOOTSTRAP_EXECUTION_01_MUTATION_AUTHORIZATION_01

APPROVED EXECUTION PACKAGE (Correction 01)
  runner sha256               = 6aa6ca2f468f3161660034648322d5f9bbc565be839c3f1427a45aa83eb7b8e9  (87499 bytes)
  execution manifest sha256   = 634a19101c1ee33bdcd1b72e0a4d6fe54cee1655771159365d1bfea0c3f7b550  (4741 bytes)
  execution package zip sha256 = 964f2de82418e5c0b8e826e8e75849bd14b832566f64b8a090b606e3c66e0ef9  (29539 bytes)
  package Marco approval handoff sha256 = b06cc1c9b73d3f5447ecb43ecce294ec71decaf4da414cd6f30541294c05d523  (5526 bytes, decision APPROVE)
  package-preparation outer submission sha256 = 831079aaa0d95849909524c4e02708708a754b6db84005a154a4e45a206f816a  (83984 bytes)

MARCO EXECUTION APPROVAL
  R1-D07_N1_LOCAL_ARB_STATE_CREATION_BOOTSTRAP_EXECUTION_01_MARCO_EXECUTION_APPROVAL_HANDOFF_01.md
  raw_bytes = 3943
  sha256    = ac4c73aedd7efd5d8a81954eec9250b115dcff7a2015efd734dc3eea9538e8ad
  decision  = APPROVE
```

### A15.5 Installed-spec canonical identity actually bound and used

The bootstrap execution bound and used, as its `INSTALLED_SPEC_CANONICAL_IDENTITY`,
the exact identity established by the Correction-01 specification canonical
installation:

```text
commit = 71486d6c447b5334c869123050f079ff059b7229
tree   = 40be3d3418e460d9aa6313a7a28236b583477ff3
parent = e7480d24464e7a122993f58e6b3554a629e9aeb4
```

with the two load-bearing source blobs unchanged at that identity
(`src/arb/execution_ledger.py` = `e39f7f400714510a6a6b32a3dfd5f84125571d5c`;
`src/arb/venues/kalshi/ledger_binding.py` = `43b36965466d42c611daa64fec71f86363a3e0f7`).

For current state this supersedes A14.2's
`INSTALLED_SPEC_CANONICAL_IDENTITY = UNBOUND_AT_CANDIDATE_AUTHOR_TIME`. It does
NOT rewrite A14.2's historical author-time statement, and this checkpoint's own
documentation commit SHA is still never substituted for the identity above.

### A15.6 Supersession for current state (history preserved verbatim)

```text
A13    remains a CORRECT historical read-only absence finding AT ITS PROBE TIME.
       Superseded FOR CURRENT STATE only: the local ARB N1 authority store,
       active ledger, and three-event bootstrap genesis now EXIST. A13's
       mutation-proof (zero mutations by that probe) is unchanged.

A14    approved bootstrap specification theorem is PRESERVED. A14 remains the
       controlling specification-level record.

A14.2  UNBOUND installed-spec identity -> superseded for current state by A15.5.

A14.3  "Approved local bootstrap contract (specification-level; not yet
       created)" and "None of these values are yet instantiated as local
       persistent state" -> superseded for current state: the approved topology
       (authority namespace/root/store path, N1 active-ledger path, path-identity
       hashes, domain binding, bootstrap contract, active contract / incident /
       writer-proof identities, deterministic bootstrap event id, three-event
       HELD genesis) is now instantiated exactly as A14.3 specified.

A14.5  "Current route" state machine (canonicalize/install spec -> prepare the
       one-shot local N1 bootstrap mutation package -> execute/reconcile/review/
       canonicalize the local bootstrap) -> superseded: package preparation,
       Marco approval, one-shot execution, Marco execution approval, and this
       canonicalization are DONE.
```

### A15.7 What remains unresolved (no inference from bootstrap success)

```text
writer_proof_state                          = HELD
release_operations                          = 0  (no release performed; no release
                                                  or writer eligibility is inferred)
normal_writer_permit                        = NOT_GRANTED
restricted_session_lifecycle_permission     = UNRESOLVED / REQUIRES_SEPARATE_AUTHORIZATION
risk_config                                 = UNRESOLVED / NOT_STARTED
external_D07_live_execution_authorization    = UNRESOLVED / NOT_ISSUED
task_current_source/freshness/live_input     = UNRESOLVED / REQUIRES_FRESH_REVALIDATION
R1-D07 live execution                        = NOT_AUTHORIZED
```

The historical `P03_C2` ticker `KXNCAAFGAME-26SEP05CLEMLSU-CLEM` remains
historical only and requires task-current revalidation before any future real
preflight.

### A15.8 Next bounded action

```text
NEXT_BOUNDED_ACTION =
  separately prepare / specify / review the exact D07 N1 risk-config
  artifact/approval required by the installed controlling stack.

This task performs none of that work. Risk-config selection, thresholds,
approval, credential use, Kalshi/venue access, execution-authorization
envelope issuance, writer-proof release, restricted-session appends, D07 live
preflight, production, Stage 3G+, and R1-D08 all remain separately
unauthorized.
```

### A15.9 Boundary

This section is documentation/current-state overlay only. It authorizes no
local-state creation/bootstrap/re-execution, no ledger or authority mutation,
no writer-proof release, no restricted-session append, no risk-config work, no
credential use, no Kalshi/venue access, no execution envelope, no live run, no
production, no Stage 3G+, no remote Git write, no `main` installation of itself,
and no R1-D08. Recording an accepted execution milestone is provenance, not an
execution authorization, and is not evidence of live venue behavior,
profitability, or arbitrage.

## A16. R1-D07 N1 pre-release risk-config specification (Marco-approved, Stage 3A-3F read-phase only)

A separately dispatched R1-D07 N1 pre-release risk-config specification and its
external/local candidate artifact were reviewed and Marco-`APPROVE`d for the
exact bounded scope `R1-D07 Stage 3A-3F PRE-RELEASE READ PHASE ONLY`. This
section canonicalizes that accepted milestone. A15 remains correct historical
state before this acceptance and is not rewritten. This section records
documentation only; it does not consume the risk config, perform a live read,
release writer proof, or create runtime capability.

### A16.1 Accepted milestone

```text
task_id            = R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_01
Marco_decision     = APPROVE
approved_scope     = R1-D07 Stage 3A-3F PRE-RELEASE READ PHASE ONLY

specification
  KALSHI_DEMO_R1_D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_01.md
  raw_bytes = 16569
  sha256    = d69d8c73cf2db203603461f7521fab4a16a11cc64b2825fd9c93fd5aaefcda5e

handoff
  HANDOFF_KALSHI_DEMO_R1_D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_01.md
  raw_bytes = 3790
  sha256    = 504a5fe0644b97e1798ec2ccbfa34e0f2c4520009ec2d6800963567463d0bc8d

external/local candidate
  R1-D07_N1_PRE_RELEASE_RISK_CONFIG_CANDIDATE_01.json
  raw_bytes = 1721
  raw_sha256 = 7266ca2a60d58b21547dca66e7016b37a4cbe9c5289e741f9b746b8296bc649c
  semantic_RiskLimitConfigV1_sha256 = 7ca6730117af4e1398e061e8184bb31af113683e34475fb66185931724a435c1

value traceability
  R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_01_VALUE_TRACEABILITY.md
  raw_bytes = 13836
  sha256    = 6899d1d4a447e658af3f66f917d13854bdd53f445ee1cf207655dabbe7060aff

corrected inner Marco review
  raw_bytes = 16189
  sha256    = 9d79b2e730aeacc8bb386159fd109dcf0717a729f242190b5046452182965377

corrected outer Marco submission
  raw_bytes = 24324
  sha256    = fd6330cd754e76c46ed0c85189ec97bc13c13e259da1b1101e3423192f492643

Marco approval handoff
  R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_01_MARCO_APPROVAL_HANDOFF_01.md
  raw_bytes = 5869
  sha256    = 29b567984f0ae853eef9173524e86556b40e0f77922b360cf01121e409283e08
  decision  = APPROVE

controlling emergency/risk specification (unchanged; no policy redesign performed here)
  KALSHI_DEMO_EMERGENCY_CANCELLATION_AND_RISK_LIMITS_SPEC_03.md
  raw_bytes = 183042
  sha256    = bb8f078185eb766ed1589441712d9cc6fcd77f574a1a2100a1901cfb75e9c8cb
```

### A16.2 Risk-config identity theorem

The risk-config artifact has two distinct, non-interchangeable identity layers:

```text
raw external-file SHA-256 (exact bytes of the candidate JSON file)
  = 7266ca2a60d58b21547dca66e7016b37a4cbe9c5289e741f9b746b8296bc649c

semantic RiskLimitConfigV1.sha256 (canonical Decimal-tagged serialization of
the parsed configuration object, independent of incidental file formatting)
  = 7ca6730117af4e1398e061e8184bb31af113683e34475fb66185931724a435c1
```

These are separate identity layers over the same accepted configuration. Neither
substitutes for the other; a future consumer MUST verify both against the exact
values above.

### A16.3 Policy acceptance theorem

```text
total_leaves                                      = 45
CONTROLLING_FIXED                                  = 4
DERIVED_FROM_CONTROLLING_BOUND                     = 5
CONSERVATIVE_POLICY_PROPOSAL_REQUIRES_ACCEPTANCE   = 36
EMPIRICAL_INPUT_REQUIRED                           = 0
USER_RISK_CHOICE_REQUIRED                          = 0
```

The 36 class-3 conservative proposal values are accepted ONLY for
`R1-D07 Stage 3A-3F PRE-RELEASE READ PHASE`. This acceptance does NOT extend to
`RELEASE_ONLY`, `SAFE_HELD -> WRITER_ELIGIBLE`, `NormalWriterPermit`, Gate D or
any venue write, emergency cancellation, later market-making execution,
production, or R1-D08. Any reuse for a write-capable or later execution scope
requires a separate review/acceptance even if the risk-config hashes are
unchanged.

### A16.4 Safety/current-state supersession

This supersedes A15.7/A15.8 **for current state only** where they say
`risk_config = UNRESOLVED / NOT_STARTED` and that risk-config
preparation/review is the next bounded action. A15's own text is not rewritten;
it remains correct historical state as of the bootstrap-execution
canonicalization.

Current theorem:

```text
risk_config                 = RESOLVED_AND_MARCO_APPROVED_FOR_STAGE_3A_TO_3F_PRE_RELEASE_READ_PHASE_ONLY
risk_config_raw_sha256      = 7266ca2a60d58b21547dca66e7016b37a4cbe9c5289e741f9b746b8296bc649c
risk_config_semantic_sha256 = 7ca6730117af4e1398e061e8184bb31af113683e34475fb66185931724a435c1
risk_config_consumed        = false
```

### A16.5 Preserve unresolved later prerequisites

```text
writer_proof_state                          = HELD
writer_release                              = NOT_AUTHORIZED
normal_writer_permit                        = NOT_GRANTED
external_D07_live_execution_authorization    = UNRESOLVED / NOT_ISSUED
task_current_source/freshness/live_input     = UNRESOLVED / REQUIRES_FRESH_REVALIDATION
restricted_session_lifecycle_permission     = UNRESOLVED / REQUIRES_SEPARATE_AUTHORIZATION
R1-D07 live execution                       = NOT_AUTHORIZED
Stage 3G+                                   = NOT_AUTHORIZED
R1-D08                                      = NOT_AUTHORIZED
```

Risk-config approval grants no runtime capability.

### A16.6 Next bounded action

```text
NEXT_BOUNDED_ACTION =
  separately prepare / specify / review the bounded R1-D07 Stage 3A-3F
  live-read execution package that binds:
    - the exact accepted bootstrap contract;
    - this exact accepted risk config (raw + semantic identity);
    - the exact external execution-authorization envelope;
    - task-current source/freshness/live-input revalidation;
    - explicit permission for the bounded restricted-session lifecycle appends.

This task performs none of that work and does not itself authorize the live
run. It does not route directly to writer release or Stage 3G+.
```

### A16.7 Boundary

This section is documentation/current-state overlay only. It authorizes no
risk-config consumption, no deployed N1 state read or write, no Kalshi/API
access, no credential use, no restricted-session append, no writer-proof
release, no D07 live execution, no production, and no R1-D08. Recording an
accepted risk-config milestone is provenance, not an execution authorization,
and is not evidence of live venue behavior, profitability, or arbitrage.

## A17. Permanent D07 selector installed and precanonical live-canary accepted

A separately dispatched R1-D07 Correction-01 implementation candidate was
Marco-`APPROVE`d and canonically installed by one non-force fast-forward, and
the exact installed candidate subsequently passed one accepted bounded
precanonical live Demo read-only canary. This section canonicalizes both
milestones. A16 remains correct historical state before this installation and
is not rewritten. This section records documentation only; it authorizes no
Kalshi access, no credential use, no selector execution, no Stage 3, no venue
write, and no production.

### A17.1 Permanent selector implementation installed

```text
task               = R1-D07_PERMANENT_DYNAMIC_TICKER_SELECTOR_IMPLEMENTATION_01_CORRECTION_01
installation_task  = R1-D07_PERMANENT_DYNAMIC_TICKER_SELECTOR_IMPLEMENTATION_01_CORRECTION_01_CANONICAL_INSTALLATION_01_REV02
installation_state = APPROVED_AND_CANONICALLY_INSTALLED

installed_commit = b3792083b92687700037f23bd00ec67b9377902c
installed_tree   = 0e88586bf3ed1fab2ea7ac979b8b42bd1529d3ca
installed_parent = f62c3da5d358e8f760d57021ad82c96fa7e80fea
```

Exact installed paths:
- `src/arb/venues/kalshi/d07_market_selector.py` — 51169 bytes / SHA-256 `e5600cece8e292761fd9793739825090ab299575ef8f3aa966ef4f2db965de14` / blob `47028082032b285b86c8ece51b864345ad707f34`
- `tests/test_kalshi_d07_market_selector.py` — 45688 bytes / SHA-256 `81c45b884184ccacae120c7f6feb2db5e94e1261d8bc2a2225f857b08ca7f697` / blob `e9da2d374639c3d659c7d27f1f22ca857107bd8a`

Correction loop:
- predecessor candidate `44b56b5b18498f75f52ad5ac41a5ecfb043ec33c` = Marco-BLOCKED / NONCANONICAL / not ancestry;
- Correction-01 candidate `b3792083b92687700037f23bd00ec67b9377902c` = Marco-APPROVED and installed.

### A17.2 Selector contract now controlling as installed code

- reusable dynamic A4 -> C1 -> B1 -> C2 selector;
- no caller ticker/candidate/market override;
- no embedded historical ticker/candidate arrays;
- no stale historical fallback;
- Demo only;
- GET only;
- zero automatic retries / zero redirect following;
- credentials deferred until authenticated C1/C2 requirement;
- selector remains outside Stage-3 risk/release/writer authority.

### A17.3 Accepted precanonical live canary

```text
result identity
  R1-D07_PERMANENT_DYNAMIC_TICKER_SELECTOR_PRECANONICAL_LIVE_CANARY_01_RESULT.json
  raw_bytes = 1097
  sha256    = 700654d96e33d9527a7aa1f6b406cc93afd5c6a2fc8753733213ca1add553fb4

acceptance handoff
  sha256   = a260e94ce97e01285d0107f7d3d1c2da262bfc25083fec96e09a2a872c877ab1
  decision = ACCEPT FINDING

discovery_anchor_utc = 2026-09-12T21:31:00.719367Z
A4_eligible_count    = 100
C1_shortlist_count   = 20
B1_finalist_count    = 5
selected_ticker_at_observation_time = KXNCAAFGAME-26SEP12MSSTMINN-MSST
final_observed_spread               = 0.0100

capability_activity: zero venue writes / production / Stage 3 / N1 / risk-config activity
```

This is direct Demo empirical evidence for the exact installed selector bytes
above. The selected ticker is freshness-bound historical/current-at-observation
evidence only; it MUST NOT become a permanent strategy constant or be
automatically reused later.

### A17.4 Installation review evidence

```text
installation review ZIP
  raw_bytes = 10078
  sha256    = 533c51b093a9e4e704577bfb692c2a29be5c1846a0b6b87b6288d54f56b2e015

installation approval handoff
  sha256   = 950b5dd5b5b427fbe39b945c1c7172c067638899cae4e81bcf76540160152942
  decision = APPROVE

remote_git_write = one non-force fast-forward, refs/heads/main:
  f62c3da5d358e8f760d57021ad82c96fa7e80fea -> b3792083b92687700037f23bd00ec67b9377902c
```

No other repository path changed in the installation commit.

### A17.5 Current capability / next route

Preserved unchanged from A16:

```text
writer_proof_state    = HELD
writer_release        = NOT_AUTHORIZED
normal_writer_permit  = NOT_GRANTED
Stage_3G_plus         = NOT_AUTHORIZED
production            = NOT_AUTHORIZED
R1-D08                = NOT_AUTHORIZED
```

Accepted N1 local bootstrap state (A14/A15) and accepted risk config (A16)
remain unchanged; the risk config remains approved only for Stage 3A-3F
pre-release/read phase and remains unconsumed.

Current theorem:

```text
permanent_D07_dynamic_selector = INSTALLED_AND_LIVE_CANARY_VALIDATED
selector_current_ticker        = REQUIRES_FRESH_SELECTION_WHEN_USED
```

The next bounded route after this continuity update is preparation/
revalidation for a fresh Stage 3A-3F read-only execution using the installed
selector, subject to all still-required separate execution authorization,
credential/network capability, restricted-session permission, source/
freshness, and N1/risk/reconciliation preconditions. This section does not
authorize or perform that route.

### A17.6 Boundary

This section is documentation/current-state overlay only. It authorizes no
Kalshi/API access, no credential use, no selector execution, no deployed N1
state read or write, no risk-config consumption, no restricted-session
append, no writer-proof release, no Stage 3 execution, no venue write, no
production, and no R1-D08. The installation recorded here is Git provenance
for exactly that ref transition, and the canary recorded here is empirical
Demo read-only evidence at the recorded observation time; neither is an
execution authorization, and neither proves profitability or a permanent
selected ticker.

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


## A18. R1-D07 Stage 3A-3F CANARY_03 proven harness, successful read phase, and market-grid correction installation

This section supersedes A17 only for the current D07 route/state facts described
here. Earlier historical facts remain preserved. This section records accepted
provenance and empirical evidence; it grants no execution capability.

### A18.1 Market-grid correction exact canonical installation

```text
task = R1-D07_STAGE3_MARKET_GRID_SCHEMA_CORRECTION_01_CANONICAL_INSTALLATION_01
status = CANONICAL_INSTALLATION_VERIFIED
repository = rigolugo/ARB
branch = main

installed_commit = a52949b37fe87c6f7595a7137d001e383b12ab55
installed_tree   = 0c9382bd73c8cbd9e07876408cb145d0fb2a2440
installed_parent = f5ed9bb3f55807e347f43285f57b057f3048168f

runner_blob = cd8082586ca19bedb2fa806a33c3f173df580347
test_blob   = 260dcfebe3649253e2ede6b2dc77637ff0072018

installation = non-force fast-forward
new_commit_created_by_installation = false
Kalshi_access = NONE
credential_activity = NONE
N1_state_changes_by_installation = NONE
```

The exact commit above is the same immutable candidate exercised by CANARY_03.

### A18.2 Prestack fill durable materialization predecessor

Immediately before CANARY_03, the previously known N1 fill was durably
materialized through one separately authorized `EMERGENCY_CONTROL_ONLY` local
restricted session.

```text
task = R1-D07_N1_PRESTACK_FILL_DURABLE_MATERIALIZATION_01
status = VERIFIED_LOCAL_STATE_RESULT
authorization = CONSUMED

fill_id = 07212270-bae1-9bda-8e24-cd2221a09d60
order_id = 01a05f53-3238-7b6d-8cf2-eb152d909826
client_order_id = 930d77bb-9ae9-47d6-8576-07cfc0ebf706
ticker = KXAAAGASD-26SEP02-4.1200
outcome_side = YES
quantity = 1.00
yes_price = 0.5000
fee = 0.017500
authoritative_created_time_utc = 2026-09-01T23:34:43.231843Z
canonical_fill_sha256 = d9fc20024b341840add831eba8b6e479c95e32ab16c74fa4e8d76bd459e6bafd

fill_event_id = evt_64a34f581264426d9695c117aebbab7c
fill_event_sequence = 13
fill_event_hash = e1c1fad0080fdd45b141c26324f169f4dc4f4950ce000854b37d02ba82bb4eb6

verified_post_materialization_trusted_sequence = 14
verified_post_materialization_trusted_hash =
  d3f88597cc22692c32a21fadaa2caed1057d77e786ca887597a3e1b80e4917a2

risk_control_state = BOOT_HOLD
risk_state_epoch = 0
writer_proof_state/eligibility = unchanged
network = NONE
Kalshi_access = NONE
Demo_venue_writes = NONE
production = NONE
```

### A18.3 CANARY_03 accepted empirical theorem

```text
task = R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03
authorization_id = R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03_AUTHORIZATION_01
authorization_sha256 = ac03f04f01c4817e56753dc03674bb0dea7cc486085bdfa93d8a1e35e49ef49f
authorization_disposition = CONSUMED
automatic_retries = 0

tested_commit = a52949b37fe87c6f7595a7137d001e383b12ab55
tested_tree   = 0c9382bd73c8cbd9e07876408cb145d0fb2a2440
tested_parent = f5ed9bb3f55807e347f43285f57b057f3048168f

starting_N1_trusted_sequence = 14
starting_N1_trusted_hash =
  d3f88597cc22692c32a21fadaa2caed1057d77e786ca887597a3e1b80e4917a2
starting_durable_fill_id = 07212270-bae1-9bda-8e24-cd2221a09d60

selector_status = SUCCEEDED
A4_eligible_count = 100
C1_shortlist_count = 10
B1_finalist_count = 5
selected_ticker_at_observation_time = KXTRUMPSAY-26SEP14-MOON
final_spread_dollars = 0.0001

stage3_exit_code = 0
stage3_elapsed_ms = 18539
stage3_status = READ_PHASE_COMPLETE
pre_release_requests_consumed = 18
trusted_dynamic_read_set_id =
  ADRS2_8798c1f54ecd11695c39728a29931fc95fef6203ca2c588db714164c9e2c768c

Gate_D = NOT_ENTERED
Stage_3G_plus = NOT_ENTERED
NORMAL_WRITER = NOT_ACQUIRED
RELEASE_ONLY = NOT_ACQUIRED
write_authorization = NO_WRITE_AUTHORIZATION
Demo_venue_writes = PROHIBITED
production = PROHIBITED
```

The selected ticker is freshness-bound empirical evidence only and is not a
permanent strategy constant.

### A18.4 Proven execution harness preserved losslessly

Canonical repository archive:

`project_archive/r1_d07_2026_09_13/stage3a3f_precanonical_canary_03/`

```text
RUN_R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03.ps1
  bytes  = 27623
  sha256 = 28eda8da7386233603f3afbb18fbc5005cfd71d384d9cc9e7f878143b9bed530
  classification = PROVEN_EXECUTION_HARNESS
  authorization = CONSUMED
  replay = PROHIBITED
  allowed reuse = REFERENCE_TEMPLATE_ONLY

RUN_R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03.ps1.sha256
  bytes  = 115
  sha256 = cb1d814b423f13113639c59215dc734ac3cef7c6d2ed72fac08a0c5cc9c37d3e

R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03_TERMINAL_RESULT_CAPTURE.json
  bytes  = 3186
  sha256 = e46da7b0971ee05cde1acf9ae6cf07b64f04888cb56acddfad2111a958b408f0
  source = NORMALIZED_FROM_OPERATOR_STDOUT_IN_MARCO_CHAT
  original_raw_result_file = NOT_PROVIDED

README.md
  bytes  = 3332
  sha256 = 9f8ac4575f08e052c83ced9c6e15f7a2b62037afde8290026867996f428e8c4a

MANIFEST.json
  bytes  = 1220
  sha256 = 23f99c0cad8cf7c373c6250a9c488485cf62b94958cffbcda5901e2e39ad39bb
```

The launcher is preserved byte-for-byte because it is the first accepted harness
that produced the complete Stage 3A-3F read path. Its embedded authorization is
consumed; canonical preservation is NOT authorization to replay it.

### A18.5 Diagnostic risk-config finding

```text
accepted_candidate_raw_sha256 =
  7266ca2a60d58b21547dca66e7016b37a4cbe9c5289e741f9b746b8296bc649c

CANARY_01 empirical result:
  reconciliation_read_deadline_ms = 1000
  -> DYNAMIC_READ_FRESHNESS_STALE
  -> operationally falsified for that exact live topology/time

CANARY_03 diagnostic config sha256 =
  ce29cc69997b36a8721b1c60c02c7e2b83176fbd0fcd2ceb4a4e63115f3e7074

only diagnostic semantic delta =
  state_integrity.reconciliation_read_deadline_ms: 1000 -> 30000

CANARY_03 with 30000:
  READ_PHASE_COMPLETE
```

This evidence supports a separate bounded permanent risk-config correction.
It does not itself rewrite the controlling A16 risk-config artifact and does not
make `30000` binding policy until that successor is separately reviewed and
canonically accepted.

### A18.6 Current route and unresolved state

```text
market_grid_correction = INSTALLED_AND_LIVE_VALIDATED
CANARY_03_read_phase = COMPLETE
proven_CANARY_03_harness = CANONICALLY_PRESERVED_REPLAY_PROHIBITED

NEXT_BOUNDED_ACTION =
  prepare/review/install the narrow N1 pre-release risk-config successor that
  replaces reconciliation_read_deadline_ms = 1000 with the empirically supported
  30000 value while preserving all other accepted risk-config semantics.

Before any later live execution or state-changing action:
  re-read current N1 authority/ledger state;
  do not infer the post-CANARY_03 trusted tail from the starting tail recorded here.
```

Still prohibited / not inferred:

```text
writer release
NORMAL_WRITER
Gate D
Stage 3G+
Demo venue writes absent separate authorization
production
profitability or arbitrage theorem
```

### A18.7 Boundary

This section and its repository archive preserve accepted provenance only.
They grant no permission to replay CANARY_03, use its consumed authorization,
access Kalshi, use credentials, mutate N1, release writer proof, enter Gate D or
Stage 3G+, write Demo orders, access production, or claim profitability/arbitrage.

## A19. R1-D07 N1 pre-release risk-config SPEC_02 accepted successor

A separately dispatched `SPEC_ONLY` risk-config successor was reviewed and
Marco-`APPROVE`d after the A18 CANARY_03 evidence established that the accepted
SPEC_01 `1000 ms` reconciliation-read deadline was inadequate for the observed
Stage 3A-3F Demo read topology and that a diagnostic `30000 ms` deadline
completed the same bounded read phase. This section canonicalizes the approved
successor identities and decision only. It does not consume the configuration,
execute D07, access Kalshi, use credentials, read or mutate deployed N1 state,
release writer proof, or grant any later-stage capability.

### A19.1 Review and package identities

```text
task_id = R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02
Marco_decision = APPROVE
approved_scope = R1-D07 Stage 3A-3F PRE-RELEASE READ PHASE ONLY

canonical_review_base:
  commit = 45a5229c6281b4d396d9263013275fd69668506a
  tree   = 04e8ed3fd209b7414472be33f5fc35772dbb0fca
  parent = a52949b37fe87c6f7595a7137d001e383b12ab55

KALSHI_DEMO_R1_D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02.md
  bytes  = 16836
  sha256 = 9ae570ef1b2cf87925b5e655b5cf846bf99596f7ff28320b8bc30cdc56c368c2

HANDOFF_KALSHI_DEMO_R1_D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02.md
  bytes  = 4796
  sha256 = 640ebcc8362da61c66cdc25c0188511f99056bed3f4e865dce60991d8a161ae2

R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02_VALUE_TRACEABILITY.md
  bytes  = 14120
  sha256 = 281f666f4fd8db7096ee425f355a6a64ec2bebd425670905e60d5fa7139b1c76

R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02_STATIC_CONFORMANCE_MATRIX.md
  bytes  = 5907
  sha256 = 9b4cb9a634e754fc74f9b47e5b40a73669223ac2ad2595276c7f57afae2bb492

R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02_REVIEW_MANIFEST.json
  bytes  = 4616
  sha256 = 707733bbc0ad625bc2c5204c3efb016447e5d179f07c0196bf80be87c858b9e0

R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02_DELIVERY_MANIFEST.json
  bytes  = 4313
  sha256 = 6fe16a598fa6c83a63fd3aada364b7cc8fc7209bbc746ea07c432957b26d8251

R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02_MARCO_REVIEW.zip
  bytes  = 36894
  sha256 = c7c6ea43c713209ae6b6f9f00a41b90fd4ef54344514b50071fd73d121e5d65e

R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02_MARCO_SUBMISSION_BUNDLE.zip
  bytes  = 95959
  sha256 = 8b91bc911cad7e10bb7c2468a139dbfce397c5430fdc38836641ae159105e992

source Bruno dispatch bundle
  bytes  = 40321
  sha256 = bcf723d5e12110a8a73ff9cf78a66055d5fde2823bb2bc09471339d6bb20f4b5

R1-D07_N1_PRE_RELEASE_RISK_CONFIG_SPEC_02_MARCO_APPROVAL_HANDOFF_01.md
  bytes    = 7165
  sha256   = 549dc149650068f5542117232d28ddf04327cf894a1eedc62d76c97fcaf95584
  decision = APPROVE
```

The raw SPEC_02/review/submission artifacts remain external/local, following the
existing D07 risk-config continuity pattern. This checkpoint is the canonical
reference to their exact identities; it is not an artifact-byte store.

### A19.2 Accepted successor configuration identity

```text
R1-D07_N1_PRE_RELEASE_RISK_CONFIG_CANDIDATE_02.json

raw_bytes = 1722

raw_sha256 =
  4495ade7fed522bf17a202d6f5422f608765b65a4463121175695c862b3f904c

semantic_RiskLimitConfigV1_sha256 =
  e16c9219b495062647b82b9e8a4d5e9c1b98f3e54ce43f0044c1a85fea162bbb
```

The raw-file SHA-256 and semantic `RiskLimitConfigV1.sha256` remain distinct,
non-interchangeable identity layers. A later consumer must verify both against
the exact values above.

### A19.3 Exact policy delta and preservation theorem

Accepted predecessor:

```text
R1-D07_N1_PRE_RELEASE_RISK_CONFIG_CANDIDATE_01.json
raw_bytes = 1721
raw_sha256 =
  7266ca2a60d58b21547dca66e7016b37a4cbe9c5289e741f9b746b8296bc649c
semantic_RiskLimitConfigV1_sha256 =
  7ca6730117af4e1398e061e8184bb31af113683e34475fb66185931724a435c1
```

Accepted SPEC_02 changes exactly one of the 45 semantic leaves:

```text
state_integrity.reconciliation_read_deadline_ms
1000 -> 30000
```

All other 44 leaves are unchanged exactly, including the four normal
risk-increasing send maxima:

```text
flow.create_max_sends              = 0
flow.modify_replace_max_sends      = 0
flow.ordinary_cancel_max_sends     = 0
flow.automated_execution_max_sends = 0
```

No other timeout, reconciliation-lag, market-data-age, backoff, emergency
request-deadline, economic limit, venue-defense policy, Decimal lexical value,
boolean, or nullability changed.

### A19.4 Evidence basis and bounded interpretation

Canonical A18 remains the accepted direct empirical basis:

```text
CANARY_01:
  reconciliation_read_deadline_ms = 1000
  -> DYNAMIC_READ_FRESHNESS_STALE

CANARY_03:
  only diagnostic risk-config semantic delta = 1000 -> 30000
  stage3_exit_code = 0
  stage3_elapsed_ms = 18539
  stage3_status = READ_PHASE_COMPLETE
  pre_release_requests_consumed = 18
  Gate D = NOT_ENTERED
  Stage 3G+ = NOT_ENTERED
  NORMAL_WRITER = NOT_ACQUIRED
  RELEASE_ONLY = NOT_ACQUIRED
  write_authorization = NO_WRITE_AUTHORIZATION
```

The accepted inference is limited to the exact D07 Stage 3A-3F pre-release
Demo read-phase configuration. It is not a production result, a universal venue
timeout, a writer-release theorem, a write-capable risk policy, a profitability
result, or an arbitrage result.

### A19.5 Preserved controlling risk architecture

SPEC_02 changes no controlling SPEC_03 safety contract. Preserved unchanged:

```text
UNKNOWN / unproven exposure -> UNKNOWN_UNBOUNDED / fail closed
HALT before emergency cancel boundary
cancel only exact proven authoritative order_id
ambiguous cancellation/write result -> reconcile and remain held
restart/reconnect/timer -> no automatic release or resend
Decimal economic semantics
explicit durable release only after the controlling release predicates
separate EMERGENCY_CONTROL_ONLY / RELEASE_ONLY / NORMAL_WRITER capabilities
```

### A19.6 Current-state supersession

A16 remains correct historical state for the original SPEC_01 acceptance.
A18 remains correct historical/direct empirical evidence for CANARY_01,
CANARY_03, the durable prestack fill, and the market-grid correction.

For current D07 risk-config state, A19 supersedes A16/A18 only where they say
the permanent `30000` successor is not yet reviewed/accepted.

```text
risk_config =
  RESOLVED_AND_MARCO_APPROVED_FOR_STAGE_3A_TO_3F_PRE_RELEASE_READ_PHASE_ONLY

active_approved_risk_config_artifact =
  R1-D07_N1_PRE_RELEASE_RISK_CONFIG_CANDIDATE_02.json

risk_config_raw_sha256 =
  4495ade7fed522bf17a202d6f5422f608765b65a4463121175695c862b3f904c

risk_config_semantic_sha256 =
  e16c9219b495062647b82b9e8a4d5e9c1b98f3e54ce43f0044c1a85fea162bbb

risk_config_consumed_by_this_canonicalization = false

writer_proof_state = HELD
writer_release = NOT_AUTHORIZED
normal_writer_permit = NOT_GRANTED
Gate_D = NOT_AUTHORIZED
Stage_3G_plus = NOT_AUTHORIZED
production = NOT_AUTHORIZED
R1_D08 = NOT_AUTHORIZED
```

### A19.7 Next bounded route

This continuity update does not decide or authorize the next live/promotion
operation. Before any later live execution or state-changing step:

```text
- re-read current N1 authority/ledger state;
- use a fresh task/authorization identity;
- verify candidate 02 raw + semantic identities;
- obtain explicit permission for every required capability and any persistent
  local control-plane appends;
- do not replay the consumed CANARY_03 authorization or archived launcher.
```

A later D07 live-read, release-boundary, Gate-D, or write-capable task requires
its own separately reviewed scope and explicit authorization. This canonical
continuity task stops after recording the approved SPEC_02 milestone.

### A19.8 Boundary

This section is documentation/current-state continuity only. It authorizes no
risk-config consumption, no deployed N1 read/write, no Kalshi/API access, no
credential use, no restricted-session append, no writer-proof release, no
NormalWriterPermit, no Gate D, no Stage 3G+, no Demo venue write, no production,
and no R1-D08.

## A20. R1-D07 N1 fresh read-only state revalidation V2 canonical successor

This section canonicalizes the accepted 2026-09-14 local-only empirical
milestone (the corrected V1 revalidation result) and records the exact
identity of its durable V2 successor tooling. It grants no capability beyond
what A14-A19 already establish; it is documentation/continuity only.

```text
current_state:
  V2 successor (CORRECTION_03)  = APPROVED_AND_CANONICALLY_INSTALLED
  installed main commit (CORRECTION_03 implementation installation) =
    a16f1286edf72215b372bca1146d248eac55f0c4
  installed tree                = 8b8bd8c715600e6c936ece2167004b9ffab58a4b
  later continuity documentation commit (the CORRECTION_06 Git base) =
    5cfe81e48da44741b3d229c92da0f64bbf34e9fc
  These are two distinct canonical events; the continuity commit did NOT
  install the CORRECTION_03 implementation (A20.7).
  V2 implementation correction loop (CORRECTION_03) = CLOSED
  one-shot authorized execution against CORRECTION_03 (2026-09-16) =
    HALTED_RETURN_TO_MARCO / RESULT_SCHEMA_INCOMPLETE; consumed (A20.7)
  V2 successor (CORRECTION_04)  = MARCO_BLOCK / PROVENANCE_CONFLATION_
    IMPLEMENTATION_INSTALL_COMMIT_VS_CONTINUITY_COMMIT; noncanonical,
    non-ancestry, never installed (A20.7.1)
  V2 successor (CORRECTION_05)  = MARCO_BLOCK / ARCHIVE_MEMBER_IDENTITY_
    STALE_README; noncanonical, non-ancestry, never installed; its
    provenance-theorem fix was substantively correct (A20.7.2)
  V2 successor (CORRECTION_06)  = APPROVED_AND_CANONICALLY_INSTALLED
    (A20.7.3, A20.7.4)
  installed main commit (CORRECTION_06; the exact Marco-reviewed commit
    object, no replacement installation commit) =
    01bc330ce5f94c72576150127b071398519282a5
  installed tree                = 4ec88ac79887fe1757ef2f5989410f229c02038a
  installed parent              = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
  V2 correction loop            = CLOSED
  current installed V2 launcher/sidecar/archive/test identities =
    the CORRECTION_06 identities in A20.7.4.2 (the A20.4.4 identities are the
    historical CORRECTION_03 record)
  terminal V2 revalidation PASS = NOT_ESTABLISHED (the one-shot execution
    above remains HALTED / RESULT_SCHEMA_INCOMPLETE and consumed; nothing
    here claims a terminal V2 PASS)
  continuity_update_pending     = true  # until the commit carrying this A20
                                        # update is itself installed (A20.7.4.4)
  next bounded action           = RETURN_TO_MARCO_FOR_REVIEW_OF_THIS_CONTINUITY_
    CANDIDATE; after its separately authorized canonical installation:
    RETURN_TO_MARCO_FOR_POST_INSTALL_D07_PLANNING (A20.7.4.4)
```

Installation is provenance, not execution authorization (A20.5).

### A20.1 Accepted local-only empirical result

```text
task = R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_01
Marco_decision = ACCEPT FINDING

result_filename = R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_01_CORRECTED_RESULT.json
result_bytes    = 7899
result_sha256   =
  a0568f5617c313b51edaf1e8787e0e75855b6ed6be650aea8caa2241d0feb0b0

observation_timestamp_utc = 2026-09-14T20:12:09.309612Z
evidence_class  = DIRECT_EMPIRICAL_LOCAL_STATE_READ_ONLY
storage_class   = LOCAL_ONLY_CANONICAL_REFERENCE_REQUIRED
```

The raw 7899-byte result remains `LOCAL_ONLY`; this checkpoint is the
canonical reference to its exact identity and accepted theorem, not an
artifact-byte store.

### A20.2 Accepted local-state theorem at observation time

```text
canonical commit/tree matched = b30236e974b708dfa5e7ab7dac8b848d2ca88d8d /
  d5efb61c2278eb2a40f40444ed327262f2ce8239
authority/ledger relation = AUTHORITY_EQUAL_TO_LEDGER
authority and ledger terminal sequence = 16
authority and ledger terminal hash =
  76f48d88fd869df9c79ffe17d318006071e80f2048e5cde351962e2aa2d73a4e
authority schema revision = 1
ledger schema revision = 2
bootstrap contract sha256 =
  c387e47c2862e6082e75bc8eb8dfa47ed085ec7be98e8426970a278a953e7360
writer proof = HELD, release eligibility = false
risk control state = BOOT_HOLD, epoch = 0
no active/abnormal writer or restricted session
no unresolved write request; no unresolved cancel attempt; no fill conflict
exact known durable prestack fill present once
no local trusted working order observed
Candidate-02 raw + semantic identities matched
authority and ledger bytes remained unchanged across the observation
Kalshi/network/credentials/repository-write/risk-config-consumption/
  writer-release/production activity all NONE
live venue exposure was NOT checked
```

This is a **local-only** observation. It does not prove current live Kalshi
Demo venue freshness, and the trusted terminal sequence/hash above is the
observed value at this one observation time only -- it is not installed as a
standing "current" fact for any later run.

### A20.3 V1 reporting defect and V2 correction rationale

```text
V1 defect = RESULT_COMPLETENESS_GAP, not a state-reader safety failure
missing fields at V1 = observation_timestamp_utc, authority_schema_revision,
  bootstrap_contract_sha256, literal ledger_path
correction  = durable V2 launcher with a machine-checkable completeness gate,
  not another post-run correction probe
```

V1's own safety/read-only-state logic was correct; the defect was that its
result omitted handoff-required observations. `CORRECTION_02` (2026-09-14,
Marco `ACCEPT FINDING`) closed that gap for one run only, and is retained as
historical/reference logic. The durable fix is V2, canonicalized below.

### A20.3a Blocked V2 candidates: noncanonical, non-ancestry

Three V2 candidates were reviewed and Marco-**BLOCK**ed before the approved
and canonically installed successor recorded in A20.4. None is installed,
accepted, canonical, or Git ancestry of that successor or of installed
`main`. They are recorded here only so a future reader does not mistake a
historical BLOCK for acceptance.

First blocked candidate:

```text
task_id          = R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01
candidate_commit = 1ae681f6648c6f2197b1991e75b8b2c11abb07ef
candidate_tree   = 706817a1f32583cbdacaa2744eeba54f3b2785ef
candidate_parent = b30236e974b708dfa5e7ab7dac8b848d2ca88d8d
review_state     = MARCO_BLOCK
allowed_use      = NONCANONICAL_CONTENT_SEED_ONLY
ancestry_use     = PROHIBITED

blocked_defects:
  1. production terminal PASS was not bound to the frozen accepted N1
     identity set -- an internally consistent, caller-selected synthetic
     ledger with a different authority/ledger/domain identity could reach
     PASS;
  2. a failing state-read path could emit a reduced 3-field result object
     rather than the complete mandatory V2 envelope;
  3. the negative regression proof envelope was incomplete.
```

Second blocked candidate:

```text
task_id          = R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_01
candidate_commit = 1c4d44c7b9af67da57f19f0e4423803a26bbdbc4
candidate_tree   = 0e3ca2ad699d7c59caf19646b54cb56868f39795
candidate_parent = b30236e974b708dfa5e7ab7dac8b848d2ca88d8d
review_state     = MARCO_BLOCK
allowed_use      = NONCANONICAL_CONTENT_SEED_ONLY
ancestry_use     = PROHIBITED

blocked_defects:
  1. production PASS was bound only to identity strings stored INSIDE the
     SQLite databases, so a stale byte-copy of the accepted stores at
     another filesystem location retained those identities and satisfied
     the gate;
  2. the default result sink was `$PSScriptRoot\...` -- inside canonical
     `project_archive/...` -- so an ordinary installed invocation created a
     repository file while declaring `repository_writes = NONE`, and the
     sink was caller-selectable with no protected-root/alias guard;
  3. the post-read mutation proof could be skipped when a readable store
     failed a schema/integrity/open check;
  4. the mandatory-field removal theorem was not directly proven;
  5. the expected durable fill ID and the Candidate-02 expected raw and
     semantic identities remained ordinary runtime parameters although the
     V2 observation contract already fixes them.
```

Third blocked candidate:

```text
task_id          = R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_02
candidate_commit = b30a8870ad033bc71698fc6c621c29be66f9d59a
candidate_tree   = 58c9c2410c2a22a0a2ef54bf7b9bdd08fba3f531
candidate_parent = b30236e974b708dfa5e7ab7dac8b848d2ca88d8d
review_state     = MARCO_BLOCK
allowed_use      = NONCANONICAL_CONTENT_SEED_ONLY
ancestry_use     = PROHIBITED

blocked_defect:
  RESULT_OUTPUT_EXISTING_OBJECT_HARDLINK_AND_TOCTOU_OVERWRITE -- the result
  sink was validated by PATH but written with truncating replacement
  semantics, so a pathname outside every protected root that was an NTFS
  hard link to a protected store (or any other pre-existing object, or one
  created by a racing process after validation) could be truncated and
  replaced after the mutation proof had already passed.
```

The corrected successor is `R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_
IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_03`, approved and canonically
installed as recorded below.

### A20.4 Approved and canonically installed V2 successor (CORRECTION_03)

```text
state = APPROVED_AND_CANONICALLY_INSTALLED
V2 implementation correction loop = CLOSED
```

### A20.4.1 Marco implementation approval

```text
implementation_task =
  R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_03
Marco_implementation_decision = APPROVE

reviewed_candidate_commit = 5e97e09600afab60392628679757b5015b731623
reviewed_candidate_tree   = 8b8bd8c715600e6c936ece2167004b9ffab58a4b
reviewed_candidate_parent = b30236e974b708dfa5e7ab7dac8b848d2ca88d8d

reviewed_package:
  MARCO_REVIEW.zip            bytes = 212418
    sha256 = 386efd992ce17bf5a979720bba44211fda8065af60403150b530f1b85ff68d57
  MARCO_SUBMISSION_BUNDLE.zip bytes = 223082
    sha256 = 7facc89aff00398dbb5d8e949ad0fcf0fdc3ebe9e020f00d99eace4f162018ef
  candidate.patch             bytes = 252668
    sha256 = 6ddd2fda1397d6a9c2eae666ec5e8088dc5cbb018ec921deef65a106804ef045

reviewed test evidence:
  targeted = 58 passed / 117 subtests / 0 skipped / 0 failed
  full     = 3681 passed / 2 pre-existing skips / 687 subtests / 0 failed
```

Packaging note: the CORRECTION_03 outer `DELIVERY_MANIFEST.json` carried a
package-builder field `network = NONE`. That field was inaccurate: the
implementation task performed one read-only GitHub `git ls-remote` of
`refs/heads/main` to verify its base, as its `TEST_RESULTS.txt` and the
archive `MANIFEST.json` disclose. Marco accepted this as a nonmaterial
packaging inconsistency; it is not a claim of zero repository-network reads.

### A20.4.2 Canonical installation

```text
installation_task =
  R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICAL_INSTALLATION_01
Marco_installation_decision = APPROVE
installation_terminal       = CANONICAL_INSTALLATION_COMPLETE_RETURN_TO_MARCO

installed_commit = a16f1286edf72215b372bca1146d248eac55f0c4
installed_tree   = 8b8bd8c715600e6c936ece2167004b9ffab58a4b
installed_parent = b30236e974b708dfa5e7ab7dac8b848d2ca88d8d
parent_count     = 1
installed_tree_equals_reviewed_tree = true
changed_paths    = exact approved seven
installed_blob_mismatches = 0
canonical local main == origin/main == installed commit

installation_mode = ONE_NON_FORCE_FAST_FORWARD
push              = <installed commit>:refs/heads/main, b30236e..a16f128
push_attempts     = 1
push_retries      = 0
force / force_with_lease / merge / rebase / cherry_pick = 0
installation_network_activity = GITHUB_REPOSITORY_SYNC_AND_EXACT_MAIN_PUSH_ONLY
```

The installed commit SHA differs from the reviewed candidate SHA because the
installation created a fresh commit; its tree is byte-identical to the
reviewed tree and its only parent is the reviewed candidate's parent.

### A20.4.3 External installation evidence (external/local, by identity only)

```text
R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICAL_INSTALLATION_01_RESULT.json
  bytes  = 10492
  sha256 = 1977d5ae756fe262812b790c9de73d8a041faa34404b79c4d77854b9bab258fc

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICAL_INSTALLATION_01_REPORT.md
  bytes  = 7292
  sha256 = b3be00d2008e0fb6d85bdf4ab0324a743b81ebe01164df0a9e2590c9386b8cc5

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICAL_INSTALLATION_01_EVIDENCE_BUNDLE.zip
  bytes  = 77770
  sha256 = 00475be7376d5bd26b2d08920487c6081018b3b438500769e8b72c1f511f481e
```

These artifacts are not repository-resident; this checkpoint is the canonical
reference to their exact identities.

### A20.4.4 Installed repository-resident identities

```text
archive path =
  project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/

RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1
  bytes    = 92690
  sha256   = cb42c4fc72822d71634bc82074c073c654bad876307641a64249b7bc56256bcb
  git_blob = 8f842d9de01712b3d033cf003863475a89903979
  result_schema = ARB_R1_D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_RESULT_V2

RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1.sha256
  bytes    = 121
  sha256   = c9fbf08e8a6e813a41d42654d7bf2b43d0ef177b1daec2984c162a2b0688af42
  git_blob = 83977797424b1ff1c1ff9829a415f05011e18bc5
  (detached checksum sidecar)

README.md
  bytes    = 15713
  sha256   = 8f33f265b3371d31f815f8d1e9ac8e83f6c217fac7ddfde234c671dcad73652b
  git_blob = ccf70a0cc7c8e94a8d2a947cc20d4547ce1787cc

MANIFEST.json
  bytes    = 12076
  sha256   = d9d1ac111cf8fe8122695832a63c341646dd144e3ed65175257f34d270a4e31a
  git_blob = 02214574db6f4255fbb84be0df0bec084e54753c

tests/test_r1_d07_n1_fresh_read_only_state_revalidation_v2.py
  bytes    = 96566
  sha256   = 41d84fbd6084f6e79e6bed6ad68f186efd12635926bad919cf2123938e057fdb
  git_blob = c54c6452dbc9180f82688bdc13c925a61626f02a
```

The installed checkpoint and `project_context/ARTIFACT_INDEX.md` blobs at
`a16f1286edf72215b372bca1146d248eac55f0c4` were the reviewed bytes, which still
described this successor as proposed. This A20 revision is the separately
authorized continuity update that records the installed state; it changes no
installed runtime, test, or archive byte.

### A20.4.5 Implementation summary

V2 is self-contained: the entire read-only probe is embedded in the single
`.ps1` file (materialized to a private temp file at invocation time and
removed afterward), so this one archived file is the whole deliverable.
Every SQLite connection it opens uses URI `mode=ro`; the canonical
"open + catch up" writer-candidate machinery
(`_open_locked` and everything built on it, including
`ledger_binding.read_active_local_safety_state_v1`) is deliberately not
used, because that path can perform a legitimate authority-anchor
catch-up write. `canonical_main_commit`/`canonical_main_tree` are captured
fresh each invocation and are informational only, never gated against a
frozen historical commit, and the trusted tail is read fresh every
invocation -- historical sequence 16 above is not hard-coded as current
truth for any future run.

`CORRECTION_01` (retained in this successor) binds production terminal
`PASS` to a frozen 17-field accepted N1 identity set (authority
namespace/instance/path/schema-revision/identity-hash, ledger
instance/schema-revision/path/identity-hash, conflict domain,
execution-domain binding id/hash, bootstrap contract hash, active contract
id/hash, incident id, writer-proof id) with no CLI override, and guarantees
the complete V2 envelope on every failure path (missing/unreadable/corrupt
store, schema/integrity failure, candidate rejection, or any unanticipated
exception).

`CORRECTION_02` (retained in this successor) adds five bounded closures on
top of that:

```text
A. production PASS is additionally bound to the ACTUAL RESOLVED filesystem
   sources, independently of the identity strings stored inside the
   databases:
     repo      = C:\b1\kals\ARB
     authority = C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority\
                 arb_execution_authority_v1.sqlite3
     ledger    = C:\b1\kals\arb_state\kalshi_demo_primary_v1\ledger\
                 subaccount1_execution_v2.sqlite3
   There is no production -Repo/-AuthorityPath/-LedgerPath/-ConflictDomain
   parameter, so a stale internally valid byte-copy at another location can
   no longer reach production PASS.

B. the result sink is safe by construction: the default destination is a
   unique OS-temp file (never $PSScriptRoot, which is repository-resident),
   and every requested destination is normalized, link-resolved through its
   nearest existing parent, and rejected if it lands under the canonical
   repository root, under C:\b1\kals\arb_state, or on an alias of the
   authority store, ledger store, Candidate-02 artifact, or the launcher.
   An unsafe sink receives zero bytes, still yields one complete V2 failure
   JSON on stdout, exits non-zero, and emits no production PASS marker, so
   `repository_writes = NONE` and `persistent_state_writes = NONE` remain
   truthful declarations.

C. the before/after mutation proof is attempted in a finally-equivalent
   path, after the SQLite connections are closed, for every store whose
   pre-proof succeeded -- including readable stores that then failed a
   schema/integrity/domain/replay/candidate check. An unobtainable
   post-proof is classified POST_READ_PROOF_UNOBTAINABLE:<store> and fails
   closed; a store that was never readable keeps explicit nulls rather than
   a fabricated proof.

D. a final machine-checkable mandatory-observation validator runs last over
   the fully assembled result, so individually removing or nulling any
   mandatory observation -- including observation_timestamp_utc,
   identity.authority_schema_revision, domain.bootstrap_contract_sha256,
   identity.ledger_path, and the new actual-source-path observations --
   provably blocks PASS.

E. the expected durable fill ID and the Candidate-02 expected raw and
   semantic identities are closed contract constants rather than runtime
   parameters, and the contract's Candidate-02 values
   (reconciliation_read_deadline_ms = 30000, all four normal send maxima
   = 0) are additionally gated for a production observation.
```

`CORRECTION_03` closes the one defect that remained:

```text
F. the result file is created ATOMICALLY AND EXCLUSIVELY with a single
   create-if-absent open (open(path, "x") = O_CREAT|O_EXCL / CREATE_NEW).
   Any object already at the destination pathname -- an ordinary file, an
   NTFS hard link to any file object (including the authority store, ledger
   store, or Candidate-02 artifact), or an object a racing process created
   after the B path checks accepted the destination -- makes creation fail
   before a single byte is written. That object is never truncated,
   replaced, renamed, unlinked, or re-created. The run fails closed with
   OUTPUT_PATH_ALREADY_EXISTS, output_sink.output_written = false, one
   complete V2 failure JSON on stdout, a non-zero exit, no production PASS
   marker, and no retry. The default OS-temp destination uses the same
   primitive. The B path checks all remain as defense in depth.

   The PowerShell wrapper reports a result file's size and hash only when
   the probe reports output_written = true, so it never stats or reads a
   refused or pre-existing pathname. A refused invocation (fixture override
   without fixture mode) no longer resolves the frozen production source
   paths, because on Windows Path.resolve() opens a zero-access handle to an
   existing path.
```

The launcher exposes an explicitly nonproduction fixture seam
(`-NonProductionFixtureMode`) so the offline suite can exercise it against
synthetic SQLite fixtures. It is not an operator path: a fixture result
carries `mode.observation_mode = NONPRODUCTION_TEST_FIXTURE` and an
unmistakable test-only marker, a complete fixture observation returns status
`NONPRODUCTION_FIXTURE_COMPLETE` and exit code `3` rather than `0`, the
launcher prints `READ_ONLY_REVALIDATION_TERMINAL=PASS` only for exit `0`,
and a fixture override supplied without the mode flag is rejected as
`FIXTURE_OVERRIDE_WITHOUT_FIXTURE_MODE` with no state read and no
source-path resolution. A further fixture-only hook,
`-FixtureRaceOccupyOutputBeforeCreate`, exists solely to prove the
validation-to-create race is closed.

The offline test module proves the CORRECTION_03 targeted requirements
C03-T01..C03-T08 -- including a real NTFS hard-link attack against
synthetic authority and ledger stores, an ordinary pre-existing output
file, and a deterministic validation-to-create race -- and preserves every
CORRECTION_01 and CORRECTION_02 test: 58 tests / 117 subtests. The test
module itself is offline and performs no deployed-N1, Kalshi, credential, or
network activity.

### A20.5 No capability advancement

```text
risk_config_consumption = NONE / NOT_AUTHORIZED
deployed_n1_activity_by_this_continuity_task = NONE
kalshi_access = NONE
credential_use = NONE
restricted_session_append = NONE
writer_proof_release = NONE / NOT_AUTHORIZED
NormalWriterPermit = NOT_GRANTED
Gate_D = NOT_AUTHORIZED
Stage_3G_plus = NOT_AUTHORIZED
Demo_venue_write = NOT_AUTHORIZED
production = NOT_AUTHORIZED
R1_D08 = NOT_AUTHORIZED

next bounded action = RETURN_TO_MARCO_FOR_POST_INSTALL_D07_PLANNING
```

This section records an accepted local-only empirical milestone and the
identity of the durable, offline-tested tooling that is now approved and
canonically installed for producing a complete result on a future authorized
run. None of the three blocked predecessors is installed, accepted, or
ancestry of installed `main`.

Installation is provenance, not execution authorization. Installing the V2
launcher does not authorize running it: a deployed-N1 read, any Kalshi read,
risk-config consumption, restricted-session append, writer-proof release, or
any later-stage step each requires a separate task with explicit capability
authorization. A16/A18/A19 risk-config and writer-proof state remain
unchanged and controlling.

### A20.6 Boundary

This section is documentation/current-state continuity only. It authorizes
no risk-config consumption, no deployed N1 read/write, no Kalshi/API access,
no credential use, no restricted-session append, no writer-proof release, no
NormalWriterPermit, no Gate D, no Stage 3G+, no Demo venue write, no
production, and no R1-D08.

### A20.7 Halted-execution validator defect and its lineage of corrections
(CORRECTION_04 BLOCKED, CORRECTION_05 BLOCKED, CORRECTION_06 APPROVED AND
CANONICALLY INSTALLED)

This subsection records the triggering one-shot authorized execution against
the installed `CORRECTION_03` successor, the accepted material finding, the
BLOCKED `CORRECTION_04` correction candidate, the BLOCKED `CORRECTION_05`
correction candidate, the approved `CORRECTION_06` successor candidate, and
(A20.7.4) its canonical installation. It does not modify A20.1 through A20.6
above, which remain the exact record of the installed `CORRECTION_03` state
as of that installation; the later `CORRECTION_06` installation replaces the
`CORRECTION_03` launcher/sidecar/archive/test bytes on `main`, and the current
installed identities are those recorded in A20.7.4.2.

Two-commit distinction, controlling for every provenance sentence in this
subsection and in `ARTIFACT_INDEX.md`:

```text
CORRECTION_03 implementation-installation commit = a16f1286edf72215b372bca1146d248eac55f0c4
  (reviewed candidate 5e97e09600afab60392628679757b5015b731623, installed
  tree 8b8bd8c715600e6c936ece2167004b9ffab58a4b, 7 changed paths)

later continuity documentation commit = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
  (tree fd02a506c7f3bd8f6308db6d85017342899a7f41, parent a16f1286edf72215b372bca1146d248eac55f0c4,
  2 changed documentation paths, role = records the already-completed
  CORRECTION_03 installation in this A20 section and in ARTIFACT_INDEX.md;
  was the CORRECTION_06 Git base; the CORRECTION_06 installation commit
  01bc330ce5f94c72576150127b071398519282a5 (A20.7.4) is its direct child)

These are two distinct canonical events and must never be collapsed into
one. 5cfe81e48da44741b3d229c92da0f64bbf34e9fc did NOT install CORRECTION_03.
```

```text
triggering_execution_task = R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_EXECUTION_01
observation_timestamp_utc = 2026-09-16
launcher_invocation_count = 1
automatic_retries         = 0
exit_code                 = 1
terminal =
  READ_ONLY_REVALIDATION_V2_EXECUTION_HALTED_RETURN_TO_MARCO
launcher_terminal =
  READ_ONLY_REVALIDATION_TERMINAL=RESULT_SCHEMA_INCOMPLETE

transient_result_bytes  = 6016
transient_result_sha256 =
  d18b71468e880e9146ba3629625c7d98a9c1c54e9ba6061224b19baa92e3d397
transient_result_availability =
  DELETED_BY_AUTHORIZED_EXECUTION_CONTRACT_AFTER_CAPTURE;
  exact bytes are NOT available as a review input and are not reconstructed
  here -- the accepted material finding is the user-reported observation
  record in the CORRECTION_04 correction dispatch bundle's
  MARCO_ACCEPT_FINDING_CORRECTION_04_HANDOFF.md

Marco_decision = ACCEPT FINDING
```

Exact material failure:

```text
status = RESULT_SCHEMA_INCOMPLETE
observation_completeness.complete = false

failures =
  PRODUCTION_IDENTITY_MISMATCH:authority_path
  PRODUCTION_IDENTITY_MISMATCH:ledger_path
```

The same run reported every other frozen identity field matching, the
independent actual-source-binding gate passing for all three real sources,
both path-identity SHA-256 fields matching, authority/ledger before/after
bytes/hash/mtime unchanged, authority trusted sequence `16`, ledger terminal
sequence `16`, `authority_ledger_relation = AUTHORITY_EQUAL_TO_LEDGER`, the
expected durable prestack fill present and exact, Candidate-02 raw and
semantic hashes matched, zero unresolved writes/cancels/fill conflicts,
writer proof `HELD`, risk control state `BOOT_HOLD`, and every prohibited
activity field `NONE`. The observed durable metadata path strings had
lowercase Windows drive-letter spelling (`c:\...`); the frozen production
identity constants used uppercase (`C:\...`). This is a validator
implementation defect, not evidence that a different source file was read.

Accepted correction theorem:

```text
In check_frozen_production_identity(), exactly these two frozen fields:
  authority_path
  ledger_path
gain Windows drive-letter/component case-insensitive lexical equality:
  str(observed).casefold() == str(expected).casefold()

Every other of the 17 frozen identity fields remains exact case-sensitive
equality. No generic path normalization (os.path.normpath/normcase,
separator conversion, dot-segment collapse, alias/symlink acceptance, or
path relocation) was added. The independent actual-source-binding gate
(check_production_source_binding / A20.4.5 item A) is unchanged and remains
load-bearing.
```

### A20.7.1 CORRECTION_04 candidate — Marco BLOCK (provenance conflation)

CORRECTION_04 candidate identity (offline implementation; reviewed and
BLOCKED; never installed):

```text
task_id =
  R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_04
required_base_commit  = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
required_base_tree    = fd02a506c7f3bd8f6308db6d85017342899a7f41
required_base_parent  = a16f1286edf72215b372bca1146d248eac55f0c4
candidate_commit       = e6e5b913e1da8ae2960e328ce3f70c122179a4a1
candidate_tree         = 3ef6629ef27b2811e9d332c65b6b5e8ff24b0db1
candidate_parent       = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
Marco_decision = BLOCK
blocked_reason = PROVENANCE_CONFLATION_IMPLEMENTATION_INSTALL_COMMIT_VS_CONTINUITY_COMMIT
status = NONCANONICAL_CONTENT_SEED_ONLY; not Git ancestry of installed main
  or of the CORRECTION_05 candidate below
```

The candidate's archive/context documentation incorrectly described
`5cfe81e48da44741b3d229c92da0f64bbf34e9fc` as the commit that installed the
CORRECTION_03 implementation. The narrow `authority_path`/`ledger_path`
casefold implementation theorem itself was accepted on substance; only the
provenance documentation was defective. Its launcher, launcher sidecar, and
V2 test bytes (identities below) are carried forward byte-identical into
CORRECTION_05.

CORRECTION_04's exact seven-path cumulative diff (relative to canonical base
`5cfe81e48da44741b3d229c92da0f64bbf34e9fc`; blocked, never installed):

```text
project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/MANIFEST.json
project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/README.md
project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1
project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1.sha256
tests/test_r1_d07_n1_fresh_read_only_state_revalidation_v2.py
project_context/PROJECT_STATE_CHECKPOINT_2026_09_06_R1_B02_CORRECTION_04_D07_READ_ONLY_LIVE_ENTRYPOINT_SPECIFICATION.md
project_context/ARTIFACT_INDEX.md
```

Confirmed-good technical bytes from the BLOCKED CORRECTION_04 candidate,
carried forward byte-identical into CORRECTION_05 (not re-edited there):

```text
RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1
  bytes  = 93733
  sha256 = f51d73d3efe807585daafbebf84577f99a3978c2d40674c5fc2eb4380d956f6b

RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1.sha256
  bytes  = 121
  sha256 = eaa8dfb77f47ba571f91ebaeee9232493ecf57e713976a362855fdfa2921b180

tests/test_r1_d07_n1_fresh_read_only_state_revalidation_v2.py
  bytes  = 104371
  sha256 = abe840c3e00d3428d48773a78ab94a1250e8c644e36d1d7a84c52436a135550d
```

Predecessor test evidence (executed for CORRECTION_04 only; NOT re-executed
for CORRECTION_05 -- see A20.7.2): the CORRECTION_04 targeted module (`67`
tests / `126` subtests, including new theorems `C04-T01`..`C04-T09`) and the
full repository suite (`3690` passed / `2` pre-existing unrelated skips)
both passed under `PYTHONPATH=src` with the required `pmresearch` CPython
3.12.13 interpreter; no real N1, Kalshi, credential, or network activity
occurred in any test.

Rerun authorization: the one-shot authorized N1 execution above is
consumed. Neither CORRECTION_04 nor CORRECTION_05 authorizes a second
deployed-N1 read; a later rerun requires a new explicit user authorization
after correction review and canonical installation.

### A20.7.2 CORRECTION_05 candidate — Marco BLOCK (stale archive member
identity)

CORRECTION_05 was a fresh candidate descending directly from canonical base
`5cfe81e48da44741b3d229c92da0f64bbf34e9fc` (tree
`fd02a506c7f3bd8f6308db6d85017342899a7f41`, parent
`a16f1286edf72215b372bca1146d248eac55f0c4`). It was NOT built on, merged
with, rebased onto, or cherry-picked from the blocked CORRECTION_04
candidate `e6e5b913e1da8ae2960e328ce3f70c122179a4a1`; that candidate was used
only as a noncanonical technical-byte content seed for the three files
listed above.

```text
task_id =
  R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_05
required_base_commit  = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
required_base_tree    = fd02a506c7f3bd8f6308db6d85017342899a7f41
required_base_parent  = a16f1286edf72215b372bca1146d248eac55f0c4
candidate_commit       = e7f0bf536d6bcf4a7e0025f35ca43cc706b8cb60
candidate_tree         = 73f5f1be419a6f59ac12a69acf9d59a42589437b
candidate_parent       = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
Marco_decision = BLOCK
blocked_reason = ARCHIVE_MEMBER_IDENTITY_STALE_README
status = NONCANONICAL_CONTENT_SEED_ONLY; not Git ancestry of installed main
  or of the CORRECTION_06 candidate below
```

Exact defect: the candidate's repository-resident archive `MANIFEST.json`
recorded a stale `members[].README.md` tuple --

```text
recorded (stale):  bytes = 18514,  sha256 = 84cc87742883ce407f387ad9dc4c4d3060b4a1a2bf72a25aae5cfe524d9a172d
actual (final C05): bytes = 20453, sha256 = be31473f3c3e8c2afd809d47591c9f109d115c54ce62f82fa64dc7a2d6a24984
  git_blob = 0e6c21ec272f023d8f5a99ba03dc9f2c9d6ee379
```

The review-package `MANIFEST.txt`/`DELIVERY_MANIFEST.json` recorded the
correct final README identity; the defect was isolated to the
repository-resident archive manifest itself. The correction scope attempted
was exactly four direct provenance/current-state edits (this file's A20.7,
plus the archive MANIFEST.json, archive README.md, and
`ARTIFACT_INDEX.md`) restating that `a16f1286edf72215b372bca1146d248eac55f0c4`
-- not `5cfe81e48da44741b3d229c92da0f64bbf34e9fc` -- installed the
CORRECTION_03 implementation; that provenance theorem was substantively
correct and is carried forward unchanged into CORRECTION_06. No
implementation logic, launcher behavior, or test behavior was changed.

Test evidence for CORRECTION_05 itself: no pytest rerun was performed.
Because the launcher, launcher sidecar, and V2 test file were required to
remain byte-identical to the CORRECTION_04 seed, and were independently
verified byte/SHA-256/Git-blob identical to it, the CORRECTION_04 test
evidence above was carried forward as predecessor evidence rather than
re-executed, per `TEST_EVIDENCE_REUSE_RULE.md` in the CORRECTION_05 dispatch
bundle.

### A20.7.3 CORRECTION_06 candidate — approved archive-identity/provenance
successor (canonically installed; see A20.7.4)

CORRECTION_06 is a fresh candidate descending directly from canonical base
`5cfe81e48da44741b3d229c92da0f64bbf34e9fc` (tree
`fd02a506c7f3bd8f6308db6d85017342899a7f41`, parent
`a16f1286edf72215b372bca1146d248eac55f0c4`). It is NOT built on, merged
with, rebased onto, or cherry-picked from the blocked CORRECTION_05
candidate `e7f0bf536d6bcf4a7e0025f35ca43cc706b8cb60`; that candidate is used
only as a noncanonical technical-byte content seed.

```text
task_id =
  R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06
required_base_commit  = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
required_base_tree    = fd02a506c7f3bd8f6308db6d85017342899a7f41
required_base_parent  = a16f1286edf72215b372bca1146d248eac55f0c4
candidate_parent       = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc (exactly
  one fresh local commit; while under review, the exact candidate
  commit/tree identities were recorded only in the CORRECTION_06 Marco review
  package, since this checkpoint file was itself one of the seven cumulative
  changed paths and could not state its own final identity; they are now
  recorded in A20.7.4 because the exact reviewed commit object was installed)
Marco_decision = APPROVE
status = APPROVED_AND_CANONICALLY_INSTALLED (A20.7.4)
```

Correction scope: exactly four direct provenance/current-state edits
(this file's A20.7, plus the archive MANIFEST.json, archive README.md, and
`ARTIFACT_INDEX.md`). The archive `MANIFEST.json`'s `README.md` member
tuple was derived from the FINAL CORRECTION_06 `README.md` bytes (22025
bytes, SHA-256 `b165d18346b1c169ae2025652773cc7164fdc9228d39729e14c9aa512722df39`),
computed only after all CORRECTION_06 `README.md` edits were complete --
never copied from a predecessor's recorded value. After that edit, the
manifest was parsed and every non-self `members[]` entry was independently
recomputed against its actual sibling file:

```text
ARCHIVE_MEMBER_IDENTITY_SELF_CHECK = PASS
mismatches = 0
```

The `a16f1286edf72215b372bca1146d248eac55f0c4` (implementation install) vs
`5cfe81e48da44741b3d229c92da0f64bbf34e9fc` (continuity commit) provenance
distinction from CORRECTION_05 is preserved unchanged. No implementation
logic, launcher behavior, or test behavior is changed.

Test evidence for CORRECTION_06 itself: no pytest rerun performed. Because
the launcher, launcher sidecar, and V2 test file are required to remain
byte-identical to the CORRECTION_05 seed, and were independently verified
byte/SHA-256/Git-blob identical to it, the CORRECTION_04 test evidence above
is carried forward as predecessor evidence rather than re-executed, per
`VALIDATION_RULES.md` in the CORRECTION_06 dispatch bundle.

This subsection does not itself claim a terminal V2 `PASS`, does not
authorize another deployed-N1 read, V2 rerun, risk-config consumption,
restricted-session append, writer release, Gate D, Stage 3G+, or production
access. It records two BLOCKED predecessor candidates (CORRECTION_04 and
CORRECTION_05) and the approved, offline-implemented successor candidate
(CORRECTION_06), whose exact reviewed commit object is now canonically
installed on `main` (A20.7.4). The two blocked candidates remain
noncanonical, non-ancestry, never-installed history.

### A20.7.4 CORRECTION_06 canonical installation

```text
state = APPROVED_AND_CANONICALLY_INSTALLED
V2 correction loop = CLOSED
```

Marco approved the CORRECTION_06 candidate and the exact reviewed commit object
was then installed on `rigolugo/ARB` `main`. Unlike the CORRECTION_03
installation (A20.4.2), which created a fresh installation commit, the reviewed
candidate commit and the installed commit here are the same Git object; no
second installation-commit identity exists and none may be inferred.

```text
implementation_task =
  R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06
Marco_implementation_decision = APPROVE

installation_task =
  R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_CANONICAL_INSTALLATION_01
Marco_installation_decision = APPROVE
installation_terminal       = CANONICAL_INSTALLATION_COMPLETE_RETURN_TO_MARCO
installation_mode           = EXACT_APPROVED_COMMIT_ONE_NON_FORCE_FAST_FORWARD

reviewed_candidate_commit = installed_commit =
  01bc330ce5f94c72576150127b071398519282a5
installed_tree   = 4ec88ac79887fe1757ef2f5989410f229c02038a
installed_parent = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
parent_count     = 1
commit_count_above_base = 1
changed_path_count      = 7 (the exact approved seven paths listed under
  A20.7.1; all modifications, no renames)
installed_blob_mismatches = 0
canonical local main == origin/main == installed commit
canonical local checkout clean after installation = true

pre-installation main = 5cfe81e48da44741b3d229c92da0f64bbf34e9fc
  (tree fd02a506c7f3bd8f6308db6d85017342899a7f41, parent
  a16f1286edf72215b372bca1146d248eac55f0c4)
push          = 01bc330ce5f94c72576150127b071398519282a5:refs/heads/main,
                5cfe81e..01bc330 (fast-forward)
push_attempts = 1
push_retries  = 0
push_exit_code = 0
force / force_with_lease / merge / rebase / cherry_pick / new commit = 0
push observed UTC = 2026-09-18T17:51:39Z .. 2026-09-18T17:51:43Z
installation_network_activity = GITHUB_REPOSITORY_SYNC_AND_EXACT_MAIN_PUSH_ONLY
```

Exact reviewed CORRECTION_06 package identities (external/local, by identity
only; `candidate.patch` is the diff from `5cfe81e48da44741b3d229c92da0f64bbf34e9fc`
to the installed commit over the exact seven paths):

```text
R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_MARCO_REVIEW.zip
  bytes  = 177498
  sha256 = c9fac26f848ab60d8f9e086c5b25d748a9918b1f7a15bb5dd5e280ecc8984e19

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_MARCO_SUBMISSION_BUNDLE.zip
  bytes  = 186510
  sha256 = 5189243dae5b932aca46aae194697b0c30bd5b89dde702deff6949789520542b

candidate.patch
  bytes  = 70140
  sha256 = 9bdacf465b1b55d82a7519c90a2999ddc4d7e1b4928ddfa8c3b0e3a28cf7f70b

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_CANONICAL_INSTALLATION_01_CLAUDE_DISPATCH_BUNDLE.zip
  bytes  = 589843
  sha256 = 0e55734e4c4ca16f1a96257eaa6597357fce8b414b8a19113323432bcba498a7

MARCO_INSTALLATION_ACCEPTANCE_HANDOFF.md
  bytes  = 3672
  sha256 = ce0aadbab56bc02ca93338dab0771fe451f7a08d2563481decb920e7b3e2c58b
  (Marco installation-acceptance record; decision APPROVE)
```

### A20.7.4.1 External installation evidence (external/local, by identity only)

The installer generated these files locally. They are not repository-resident;
this checkpoint is the canonical reference to their exact identities.

```text
evidence_root   = C:\b1\kals\claude-zips
evidence_class  = LOCAL_ONLY_INSTALLATION_EVIDENCE (installer-generated;
                  accepted by Marco through the installation-acceptance record)
storage_class   = LOCAL_ONLY_CANONICAL_REFERENCE_REQUIRED

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_CANONICAL_INSTALLATION_01_RESULT.json
  bytes  = 11641
  sha256 = 7aae20fd1d0b37140e0ecdf49e29c9bc838b1d5e0a7e544dc88103a388348f1e

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_CANONICAL_INSTALLATION_01_REPORT.md
  bytes  = 9777
  sha256 = fac6a4659729252eeaa22ace85c6532065b902bacc0156cc8887df4b4c0156e5

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_CANONICAL_INSTALLATION_01_EVIDENCE_BUNDLE.zip
  bytes  = 23140
  sha256 = 991e192a6679da3f00322c700fd0ebbbbcb400cbed2a308141cc67d9a79368d6

R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06_CANONICAL_INSTALLATION_01_EVIDENCE_BUNDLE.zip.sha256
  bytes  = 209
  sha256 = cae88996d29333e2cf6b5749142f8605c57d83ca54b39e8cdf2dbb34851a777c
  (detached sidecar for the evidence ZIP)
```

These identities were computed from the files as they exist under the evidence
root by the continuity task, before any edit; none was copied from chat or
from a predecessor record. The sidecar SHA-256 equals the recomputed
evidence-ZIP SHA-256; the ZIP reopens with eleven members (`RESULT.json`,
`REPORT.md`, seven phase transcripts, `installed_file_identity_table.tsv`,
`approved_package_verification_record.json`); its embedded `RESULT.json` and
`REPORT.md` are byte-identical to the standalone files; and the RESULT/REPORT
content agrees with Git truth (installed commit/tree/parent, exact seven paths
and blob IDs, one push, zero retries, no force, local `main` fast-forwarded and
clean, `continuity_update_pending = true`).

```text
proves     = the exact installation facts recorded in A20.7.4 and the
             per-phase observation transcripts behind them
does_not_prove = any deployed-N1 state, any Kalshi/venue state, any V2
             execution result, or any capability
```

### A20.7.4.2 Installed repository-resident identities (as installed at 01bc330ce5f94c72576150127b071398519282a5)

```text
archive path =
  project_archive/r1_d07_2026_09_14/n1_fresh_read_only_state_revalidation_v2/

RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1
  bytes    = 93733
  sha256   = f51d73d3efe807585daafbebf84577f99a3978c2d40674c5fc2eb4380d956f6b
  git_blob = dededbb1719e21bdc3a456818fa1f4a0d740557b

RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1.sha256
  bytes    = 121
  sha256   = eaa8dfb77f47ba571f91ebaeee9232493ecf57e713976a362855fdfa2921b180
  git_blob = fb349f3e5201d70536a84f7c8caf1ec1fba2ffcf

README.md
  bytes    = 22025
  sha256   = b165d18346b1c169ae2025652773cc7164fdc9228d39729e14c9aa512722df39
  git_blob = 796c0946ffbb56e15447dc643ee92ab1e37a6a40

MANIFEST.json
  bytes    = 21373
  sha256   = 5733b2db357d049f1c9b3f2f28bd17d296149c8fdbaadff3cb1a73a107ba39bb
  git_blob = 556490c06a32b5afe6594965349ba02587181b62

tests/test_r1_d07_n1_fresh_read_only_state_revalidation_v2.py
  bytes    = 104371
  sha256   = abe840c3e00d3428d48773a78ab94a1250e8c644e36d1d7a84c52436a135550d
  git_blob = 3833945b4b0d9d4ad24392912957511d9405a489

project_context/PROJECT_STATE_CHECKPOINT_2026_09_06_R1_B02_CORRECTION_04_D07_READ_ONLY_LIVE_ENTRYPOINT_SPECIFICATION.md
  (this file, as reviewed and installed at 01bc330; superseded by this update)
  bytes    = 113399
  sha256   = cdf0d37c53cef48da0e7f26172b0c266fe796f257c7d8870040d471f091e2031
  git_blob = 082976a0fba30fcdddcc4eabb370e1f6c8e80c51

project_context/ARTIFACT_INDEX.md
  (as reviewed and installed at 01bc330; superseded by the paired update)
  bytes    = 187168
  sha256   = 4f92d97df5d43cabd750c6d3a72b48d3d48f1039e915cc2f7b3e7213d0f47d17
  git_blob = 216ceb66e91736de814c1b652d2a2dc06316a410
```

For current-state purposes these launcher, launcher-sidecar, archive
README/MANIFEST, and V2 test identities supersede the corresponding
CORRECTION_03 identities in A20.4.4, which remain the historical
CORRECTION_03 installation record. The launcher, sidecar, and test bytes are
byte-identical to the CORRECTION_04/CORRECTION_05 confirmed-good seed
(A20.7.1, A20.7.2) and are unchanged by this continuity update.

The archive `README.md` and `MANIFEST.json` are immutable installed provenance
at the identities above and are not edited by this continuity update. Both were
authored and reviewed before installation: the `README.md` describes
`CORRECTION_06` as a proposed candidate and the `MANIFEST.json` records
`candidate_status = PROPOSED_CANDIDATE_NOT_YET_CANONICALLY_INSTALLED`.
Those are pre-installation self-descriptions, not current state; the
CORRECTION_06 archive-member identities they carry
(`ARCHIVE_MEMBER_IDENTITY_SELF_CHECK = PASS`, zero mismatches) are retained
unchanged, and this A20.7.4 together with the paired `ARTIFACT_INDEX.md` entry
controls current state.

### A20.7.4.3 INSTALLATION_ENVIRONMENT_OBSERVATIONS

Two installation-time Git maintenance observations were reported by the
installer and accepted by Marco as non-invalidating environment facts. They are
preserved here as installation evidence/provenance only.

```text
observation 1 = WORKTREE_PRUNE_PERMISSION_DENIED
  Git auto-maintenance / `git worktree prune`, run as a side effect of the
  authorized fetch and pull, printed "failed to delete .git/worktrees/<name>:
  Permission denied" for approximately 44 pre-existing stale
  `.git/worktrees/...` administrative entries. The total stale-entry count was
  77 before and after; every command still exited 0; live worktrees were
  unaffected.

observation 2 = STALLED_GIT_MAINTENANCE_CHILDREN
  `git pull --ff-only origin main` completed the fast-forward and then did not
  return for approximately five minutes because idle `git worktree prune` and
  `git maintenance` child processes persisted. The installer terminated only
  those two idle child processes; the pull then returned exit 0. There was no
  pull retry and no manual repository-file edit.

tracked repository-byte effect = NONE
installed Git object identity effect = NONE
second push = NONE
retries = NONE
manual repository-file edit = NONE
repair performed by the continuity task = NONE
```

The continuity task did not repair, prune, or otherwise modify stale worktree
administrative metadata or Git maintenance behavior; any such repair requires
its own separate authorization.

### A20.7.4.4 Current state, unresolved items, and next action

```text
CORRECTION_06 = APPROVED_AND_CANONICALLY_INSTALLED
V2 correction loop = CLOSED
implementation_candidate_installed = true
continuity_update_pending = true   # until the commit carrying this A20 update is
                                   # itself canonically installed
C04 = MARCO_BLOCK (PROVENANCE_CONFLATION_IMPLEMENTATION_INSTALL_COMMIT_VS_CONTINUITY_COMMIT);
      noncanonical, non-ancestry, never installed (A20.7.1)
C05 = MARCO_BLOCK (ARCHIVE_MEMBER_IDENTITY_STALE_README);
      noncanonical, non-ancestry, never installed (A20.7.2)
accepted halted execution finding = 6016-byte transient result,
  RESULT_SCHEMA_INCOMPLETE, HALTED_RETURN_TO_MARCO (A20.7); preserved
one-shot execution authorization = CONSUMED
terminal V2 revalidation PASS = NOT_ESTABLISHED
```

`CORRECTION_06` closes the offline V2 correction loop. It does not establish a
terminal V2 revalidation `PASS`: the one-shot authorized execution recorded in
A20.7 remains `HALTED` / `RESULT_SCHEMA_INCOMPLETE` and consumed, and no
terminal V2 `PASS` has been established. A new deployed-N1 V2
revalidation requires separate explicit user authorization after this
continuity update is canonically installed. Installation is provenance, not
execution authorization.

```text
deployed_n1_activity_by_this_continuity_task = NONE
v2_rerun = NOT_AUTHORIZED
kalshi_access = NONE
credential_use = NONE
risk_config_consumption = NONE / NOT_AUTHORIZED
restricted_session_append = NONE
writer_proof_release = NONE / NOT_AUTHORIZED
NormalWriterPermit = NOT_GRANTED
Gate_D = NOT_AUTHORIZED
Stage_3G_plus = NOT_AUTHORIZED
Demo_venue_write = NOT_AUTHORIZED
production = NOT_AUTHORIZED
R1_D08 = NOT_AUTHORIZED
```

A16/A18/A19 risk-config and writer-proof state remain unchanged and
controlling.

After the commit carrying this update is itself canonically installed (a
separately authorized step that is not performed here, and whose commit
identity this file cannot state about itself):

```text
continuity_candidate_installed = true
continuity_update_pending = false
next_bounded_action = RETURN_TO_MARCO_FOR_POST_INSTALL_D07_PLANNING
```

This subsection authorizes and performs no D07 operational step.

### A21 R1-D07 release-only and writer-eligibility specification CORRECTION_02

This is a documentation-only continuity candidate prepared directly from
canonical `rigolugo/ARB/main` commit
`0d48e3251f37d41e6e4c89203670fbb6b2367d1c` (tree
`8f48554e8be7a196b16aefc7d3c77ba9ac4a19b1`, parent
`01bc330ce5f94c72576150127b071398519282a5`). The original SPEC_01 candidate
and CORRECTION_01 candidate are Marco-BLOCKED, noncanonical, never installed,
and are not this candidate's parent or source. In particular, blocked
CORRECTION_01 candidate `06d05ac6051cc2ea24ffe124051fc217ccc063f0` is not
ancestry of this candidate.

CORRECTION_02 is proposed and pending Marco review. It preserves the accepted
`EXECUTION_02` V2 PASS without rerunning it, the active V2 process-local token
theorem, the proof-only Candidate-02 risk object, the
`USER_RISK_CHOICE_REQUIRED` decision, and the implementation gates
`PRE_RELEASE_BRIDGE_IMPLEMENTATION_REQUIRED` and
`SAME_PROCESS_RELEASE_TO_GATE_D_IMPLEMENTATION_REQUIRED`.

The corrected future topology is: pre-bridge fresh read/reconciliation;
canonical `EMERGENCY_CONTROL_ONLY` acquisition; qualifying incident-bound
`RECONCILIATION_RECORDED`; HELD plus release-eligible readback;
`BOOT_HOLD -> SAFE_HELD`; live-handle SAFE_HELD readback; then
`EmergencyControlLedgerHandle.close()`. The close call is the durable
`RESTRICTED_SESSION_ENDED` boundary. Only after it returns may a fresh
read-only reopen verify the end event, no active restricted session, equal
authority/ledger tails, SAFE_HELD, and HELD-plus-eligible proof. No end-event
readback is performed before close.

The post-close bridge must then obtain a new Stage-3A–3F result with a new
private trusted dynamic capability, a new `ADRS2_<64hex>` identity, and fresh
market/reconciliation timestamps. The pre-bridge `ActiveReleaseEvaluationStateV1`
is not RELEASE_ONLY authority. The later state alone may feed
`acquire_active_release_only_v1`, the full 19-predicate evaluation, durable
release, `CurrentProcessReleaseCompletionV2`,
`acquire_active_normal_writer_state_v1`, Stage 3K, and any future separately
authorized same-process bounded Gate-D action.

Static analysis finds the installed live boundary supports only one
`run_pre_release_read_phase_v2` call per invocation. Although each call would
mint a fresh single-use capability with a separate 72-request counter, the
installed public boundary has one externally verified read-only authorization,
one runtime, one non-refreshable 300-second absolute deadline, and exactly one
read-phase call. It does not define aggregate two-pass accounting or bridge
composition. The result is
`POST_BRIDGE_STAGE3_REFRESH_IMPLEMENTATION_REQUIRED`; no read limit or
deadline is increased here. The minimal future correction is one explicit
same-process bridge orchestrator/authorization envelope that counts both
distinct passes, keeps the one absolute deadline, creates the fresh capability
and ADRS2 lineage after close/readback, and rejects any second pass that lacks
remaining authorized budget or deadline.

The proof-only risk config remains unchanged: all four normal send maxima are
zero. No user risk leaf is selected. Current state remains
`BOOT_HOLD / HELD / writer_proof_release_eligible=false` until separately
authorized execution proves otherwise. No deployed-N1 activity, credential
use, restricted-session append, release, writer admission, Gate-D, venue
write, production activity, source/test edit, package installation, or remote
Git write is authorized by this continuity record.

`continuity_update_pending = true` until this candidate is separately reviewed
and canonically installed. Until then the next bounded action is
`RETURN_TO_MARCO_FOR_REVIEW_OF_CORRECTION_02_CANDIDATE`.

### A22 R1-D07 N1 release-only and writer-eligibility specification CORRECTION_05

This is a documentation-only continuity candidate prepared directly from the
required canonical `rigolugo/ARB/main` base:

```text
commit = 1536a13ba415371a0d8569f5e41671735c78e5e1
tree   = 073d1661c8acc8439d209cbc3c8c46883612f098
parent = 0d48e3251f37d41e6e4c89203670fbb6b2367d1c
```

CORRECTION_04 candidate `1803cc674152754b3addb5f477eaa46b93515e48` is
Marco-BLOCKED, noncanonical, never installed, and is not this candidate's
parent or ancestry. Its exact specification and review/submission package are
content seed only.

CORRECTION_05 is a one-defect successor. The canonical current N1 binding is:

```text
subaccount     = 1
exchange_index = 0
active_contract_id = AEDC1_f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53
domain_binding_id  = KEDB1_f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02
```

Exchange index is one exact field, not a uniqueness theorem. The active domain
continues to require the complete exact contract/domain/account/subaccount/
exchange/market/implementation/risk/attempt/invocation binding. The corrected
value propagates through the O/G/E.binding/B schemas, BOOT_HOLD and clean
SAFE_HELD variants, Gate-D cross-binding, and directly dependent comparisons.
The banned exchange-index-one route wording is absent from the normative
successor.

All CORRECTION_04 authorization theorems remain preserved: clean SAFE_HELD
one-phase continuation; durable cross-restart authorization consumption and
replay rejection; same-invocation Gate-D anti-substitution; trusted external
expected-hash provenance; 2x72/144/300 accounting; narrow mutation authority;
the pre-mutation theorem; crash/restart semantics; the six-path future
implementation edit set; and `USER_RISK_CHOICE_REQUIRED = OPEN`. Candidate-02
remains proof-only with all four normal send maxima zero. Accepted
`EXECUTION_02` V2 PASS is unchanged and was not rerun.

This continuity candidate authorizes no deployed-N1 or Kalshi/API access,
credentials, state mutation, RELEASE_ONLY, writer-proof release, NORMAL_WRITER,
Gate D, venue write, production activity, source/test/archive edit, package
installation, or remote Git write. `continuity_update_pending = true` until
this two-path candidate is independently reviewed and canonically installed.
The next bounded action is `RETURN_TO_MARCO_FOR_REVIEW_OF_CORRECTION_05`.

### A23 R1-D07 N1 pre-release bridge / same-process Gate-D orchestrator implementation CORRECTION_03 — APPROVED_AND_CANONICALLY_INSTALLED

This is a documentation-only continuity overlay. This continuity candidate is
prepared directly from canonical `rigolugo/ARB/main` base:

```text
commit = 60ca9f61cab2ed81310d89a422bd7af4f2b532ad
tree   = 95821332715eaffb7e33f25e15d2e28806f0d1d4
parent = 8655fff50ffffd5e82bd32fb1cb6c23b26a0bd38
```

This section controls current continuity when present on canonical main. It
alters no implementation bytes and grants no runtime capability.

**WHY this section exists.** A22 (and the artifact-index tail) still describe the
CORRECTION_05 release-only / writer-eligibility specification as a candidate
awaiting Marco review, and describe the same-process bridge / Gate-D orchestrator
as future implementation work that remains required. Both milestones have since
been independently approved and canonically installed. The continuity workflow
requires an important implementation/install milestone to preserve what happened,
why it matters, the exact theorem, its authority/evidence, its exact identities,
the unresolved state, and the next bounded action. This section records them in
the existing routed D07 checkpoint; no new checkpoint is created.

**Supersession scope (A22 only, and only where stated).** A23 supersedes A22
only on: (a) the review/installation status of CORRECTION_05 (A22's wording that
it is a candidate pending Marco review); (b) the implementation-required /
uninstalled status of the pre-release bridge and same-process release-to-Gate-D
substrate; and (c) A22's continuity-pending flag and its next bounded action.
All historical A22 technical content — the exact N1 binding, the preserved
CORRECTION_04 authorization theorems, the six-path future implementation edit
set, and the blocked-predecessor lineage — remains preserved unchanged. A21 and
earlier sections are not rewritten.

**Current theorem.**

```text
controlling_spec = CORRECTION_05 / APPROVED_AND_CANONICALLY_INSTALLED
implementation = CORRECTION_03 / APPROVED_AND_CANONICALLY_INSTALLED
canonical_main = 60ca9f61cab2ed81310d89a422bd7af4f2b532ad
canonical_tree = 95821332715eaffb7e33f25e15d2e28806f0d1d4
live_orchestrator_execution = NOT_RUN
USER_RISK_CHOICE_REQUIRED = OPEN
next_bounded_action = RETURN_TO_MARCO_FOR_USER_RISK_CHOICE_AND_SEPARATELY_APPROVED_EXECUTION_PACKAGE_PLANNING
```

**A23.1 Controlling specification milestone.** The CORRECTION_05 release-only /
writer-eligibility specification is approved and canonically installed:

```text
canonical commit    = 8655fff50ffffd5e82bd32fb1cb6c23b26a0bd38
tree                = 7cf520b41b678494e15010af4c2167222432b35d
parent              = 1536a13ba415371a0d8569f5e41671735c78e5e1
spec bytes          = 53002
spec sha256         = d3bb8add3ab2a3a168bd3ee0da6131c967b0649837d6160fb5c4c98742767d79
handoff bytes       = 5311
handoff sha256      = ab6061dea5fb105977f84b5b04829560d3ad0ce2082030156b0fba2db09de4a4
installation RESULT = 14603 bytes / a07e8e57f1e1adf462337da439f147fdc5725fe73ae82be8f0c105df8f20b374
installation REPORT = 9453 bytes / d7cfbfae0724a982eeb0e85bd6deb0fcd3fb6ecfa6fba8f91d744efd1ad6b415
installation review ZIP = 153215 bytes / 2b7386a4f4e5aa08dbb5fc1f9145b3eda4dba4131061957518140eae3568b25f
```

Preserved unchanged: the exact current N1 binding is `subaccount = 1`,
`exchange_index = 0`; the exchange index is one exact field and not a standalone
uniqueness theorem (the complete active-contract / domain / account / subaccount
/ exchange / market / implementation / risk / attempt / invocation binding
remains required); `USER_RISK_CHOICE_REQUIRED = OPEN`; Candidate-02 remains
proof-only (raw SHA-256
`4495ade7fed522bf17a202d6f5422f608765b65a4463121175695c862b3f904c`, semantic
SHA-256
`e16c9219b495062647b82b9e8a4d5e9c1b98f3e54ce43f0044c1a85fea162bbb`) and all four
normal send maxima remain zero; no write-capable risk values have been selected.

**A23.2 Implementation milestone.** The approved implementation candidate is:

```text
task   = R1-D07_N1_PRE_RELEASE_BRIDGE_REFRESH_AND_SAME_PROCESS_GATE_D_ORCHESTRATOR_IMPLEMENTATION_01_CORRECTION_03
commit = 60ca9f61cab2ed81310d89a422bd7af4f2b532ad
tree   = 95821332715eaffb7e33f25e15d2e28806f0d1d4
parent = 8655fff50ffffd5e82bd32fb1cb6c23b26a0bd38
commits above base = 1
```

Exact approved review provenance (Marco decision `APPROVE`, technical review
only):

```text
review ZIP      = 541015 bytes / c8b739e4d7b2952daffaacba38bc9acd52d999fde2cfa785f045cca354126552
submission ZIP  = 561979 bytes / a4e2fc591c49a45e690b0789d5137265f33252b450d3bb6a56c4a711d2429187
candidate.patch = 428658 bytes / 1464ce7036deca6aec8809d37f6305910034a790040792d7e5c821770f1fd572
Marco approval  = 7034 bytes / e6b5910b2307485b1ed81ebd08b14a2927af5ea08ee0bf616e80a456f0dff742
```

Blocked predecessor candidates `a65db56e227cb098d85f25a1947db8e3bbdda352`
(CORRECTION_01) and `9e4caade5e1c22cb36e93fc93e3a25f881ae1957`
(CORRECTION_02) remain Marco-BLOCKED, noncanonical, never installed, and not
ancestry. Marco-reported approval test evidence (accepted review evidence, not
re-run by this continuity task): `test_execution_ledger.py` 78 passed / 82
subtests; `test_kalshi_ledger_binding.py` 453 passed / 59 subtests; the runner
module 1375 passed / 2 skipped / 156 subtests; combined three modules 1906 passed
/ 2 skipped / 297 subtests; full repository 3789 passed / 2 skipped / 911
subtests.

Exactly six installed paths and identities (as installed at
`60ca9f61cab2ed81310d89a422bd7af4f2b532ad`):

| Path | Bytes | SHA-256 | Git blob |
|---|---|---|---|
| `src/arb/execution_ledger.py` | 215456 | `a21813677b7344968dc2df2860fe4d3d91ad194c8bb6b003c2a159f561573b9b` | `608f4cd281525a8bf53fafa2b19eb23cc5b669ac` |
| `src/arb/venues/kalshi/ledger_binding.py` | 241761 | `a09b8a3867b110ab5253f68ae140684e2161bdcf542ca41b64460c57f40a8c6c` | `f7ca4949954606d85006ccca4006a529ce5431b2` |
| `src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py` | 676456 | `80d9a95bd53dfc1b592270d3a3a6c1571aaf0a1975b4c4408ba7ce41992d9d91` | `1c11d5208aac05d88a4b7c3c0a1a3dd47d1b1046` |
| `tests/test_execution_ledger.py` | 118705 | `9075256e11f27b40d6f88d3870d9c37b14a74d9d596e73269611715e26a8adb1` | `242566dd3146e1a8461e59f71c9e2c2f8b6dd701` |
| `tests/test_kalshi_ledger_binding.py` | 308541 | `a90a98d90e7756c814e22aaac8ef40cf37a9af65337f918b8c4e0905e7bab6e2` | `c7f93e0510bf704d2e87c7e218d3688ef12b27b6` |
| `tests/test_kalshi_minimal_market_maker_experiment_runner.py` | 715961 | `21c6b8afb978010a7b48a187b031ce21193b837d5252f3037c319bc887f31288` | `60ed6c2aa6152ed4c41ac32d8ed760ee9eb6020f` |

Implementation theorem (installed substrate; not executed):

- active-ledger-only durable `EXECUTION_AUTHORIZATION_SET_CONSUMED`;
- cross-restart consumed-authorization replay rejection;
- no-repair authorization freshness/admission;
- `BOOT_HOLD` two-pass bridge and clean `SAFE_HELD` one-pass route;
- one absolute 300-second deadline and bounded read budgets;
- exact close + post-close readback + new post-bridge `ADRS2` identity;
- 19-predicate release evaluation;
- same-process release -> `CurrentProcessReleaseCompletionV2` -> `NormalWriter`
  -> Stage 3K -> separately authorized Gate D;
- private launcher-only trusted-expectations boundary;
- trusted E semantic snapshot recursively immutable and alias-independent
  (the CORRECTION_03 delta over the blocked CORRECTION_02 seed: exactly the
  runner and its test module);
- exact current N1 binding uses `subaccount = 1`, `exchange_index = 0`;
- the D07 read-only path remains read-only.

This is installed substrate only. It is not a live release or Gate-D execution.

**A23.3 Canonical implementation installation.** Installation task
`R1-D07_N1_PRE_RELEASE_BRIDGE_REFRESH_AND_SAME_PROCESS_GATE_D_ORCHESTRATOR_IMPLEMENTATION_01_CORRECTION_03_CANONICAL_INSTALLATION_01`
(Marco decision `APPROVE`):

```text
previous main    = 8655fff50ffffd5e82bd32fb1cb6c23b26a0bd38
installed main   = 60ca9f61cab2ed81310d89a422bd7af4f2b532ad
installed tree   = 95821332715eaffb7e33f25e15d2e28806f0d1d4
installed parent = 8655fff50ffffd5e82bd32fb1cb6c23b26a0bd38
candidate source = EXACT_APPROVED_COMMIT_OBJECT
post-push classification = REMOTE_INSTALLATION_CONFIRMED
push commands = 1
push retries = 0
force / force-with-lease = 0
```

Accepted installation evidence (external/local, by identity only):

```text
RESULT              = 8916 bytes / 24d06403b65796d7e2681e7a890bb0be82369c84c52a2e5a38dc9f974f19bcba
REPORT              = 11632 bytes / 60ca372d795591ad72f1748d4b2dacb7d7d41ffe971920b3d6eae1b05efee52a
GIT_TRANSCRIPT      = 18165 bytes / 088c1c23d0ed1660b98f265680e70629b72d3729dbc0a7d35b4358e35505f0da
PUSH_ATTEMPT_MARKER = 1541 bytes / 6ad559e42431d41ccbff4af3d655e3ace352380315a37623837d7949796409d9
DELIVERY_MANIFEST   = 2697 bytes / bc17fad5532939341b95cef6ffa6e2af118d4fd3f03f611c16dcb85322559e50
final MARCO_REVIEW.zip = 21314 bytes / b1604ab0593d3a1a66085c4fccb4beac88b6fbf1ce6bd612b9d5dcdb7da62cf9
Marco installation acceptance = 3174 bytes / 44689b7f762eb32e7ed76fa9d3a70f4b52dd8d47bd6ee754d089ad5d53f1f4fa
```

Accepted nonblocking local-sync deviation: after authoritative remote
confirmation, local synchronization used `git fetch origin` followed by
`git merge --ff-only origin/main`, with zero additional remote write.

**A23.4 Corrected provenance fact.** The earlier CORRECTION_03 "dispatch bundle
contamination" disclosure was false and is retracted. The exact ZIP
`a31ab07da14423421956bb062860927219f819bd362eb012300541b55fc0e503` (6794430
bytes) had 84 entries, one intended root, and zero foreign members; the false
report came from reuse of a dirty extraction directory and must not be
canonicalized as a property of that ZIP.

**A23.5 Current operational state.**

```text
implementation_substrate = APPROVED_AND_CANONICALLY_INSTALLED
live_orchestrator_execution = NOT_RUN
deployed_n1_activity_from_implementation_or_install = NONE
Kalshi/API/venue activity from implementation/install = NONE
credential use = NONE
RELEASE_ONLY real acquisition = NONE
writer-proof release = NONE
NormalWriter real acquisition = NONE
Gate-D real execution = NONE
production = NONE
USER_RISK_CHOICE_REQUIRED = OPEN
```

The prior accepted deployed-state theorem `BOOT_HOLD / HELD /
writer_proof_release_eligible=false` is preserved only as historical /
current-until-refreshed knowledge. This continuity task did not read deployed N1
state and makes no fresh deployed-state claim. No launcher / O / G / E execution
package has been issued by this milestone, and no user risk choice has been made.

**A23.6 Next bounded action.**

```text
next_bounded_action = RETURN_TO_MARCO_FOR_USER_RISK_CHOICE_AND_SEPARATELY_APPROVED_EXECUTION_PACKAGE_PLANNING
```

The user must separately choose the write-capable risk values. After that, a
separately reviewed exact launcher + E/O/G package may be prepared. Actual Demo
release / writer / Gate-D execution still requires separate explicit user
authorization. This continuity canonicalization grants none of those
capabilities and is not profitability or arbitrage evidence.

**A23.7 Boundary.** This continuity record authorizes no credential use,
N1/deployed-state access, Kalshi/API/venue activity, risk selection, risk-config
consumption, restricted-session append, RELEASE_ONLY, writer-proof release,
NormalWriter, Gate D, venue write, production, R1-D08, or remote Git write.
Recording an approved specification or an installed implementation is
Git/review provenance and never an execution authorization.
