# R1-D07 N1 Fresh Read-Only State Revalidation — V2

## What this is

`RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1` is the canonical
successor to the accepted V1 launcher and its `CORRECTION_02` missing-field
closure wrapper (Marco `ACCEPT FINDING`, 2026-09-14). It is a **self-contained**
PowerShell launcher: the entire read-only Python probe is embedded in the
file itself (materialized to a private temp `.py` file at invocation time and
deleted afterward), so this single `.ps1` is the whole deliverable.

## Why V2 exists

The accepted V1 launcher correctly established safe/current local N1 state,
but its result omitted four handoff-required observations (`observation_
timestamp_utc`, `authority_schema_revision`, `bootstrap_contract_sha256`,
literal `ledger_path`). A bounded `CORRECTION_02` wrapper closed that gap for
one run. V2 is the durable fix: **one invocation now produces one complete,
review-ready result**, and it cannot terminal-`PASS` while any required
observation is missing. There is no more need for a post-run closure/
correction pass.

## Correction history

Three earlier V2 candidates were Marco-**BLOCK**ed. All are noncanonical and
none is ancestry of this candidate:

- `1ae681f6648c6f2197b1991e75b8b2c11abb07ef` — production PASS was not bound
  to the frozen accepted N1 identity set; a failing state-read path could emit
  a reduced envelope; the negative regression proof was incomplete.
- `1c4d44c7b9af67da57f19f0e4423803a26bbdbc4` — production PASS was bound only
  to identity strings stored *inside* the databases; the default result sink
  wrote into the repository and was alias-unsafe; mutation proof was skipped
  on early readable failures; the mandatory-field removal theorem was not
  directly proven; and several already-frozen contract facts were ordinary
  runtime parameters.
- `b30a8870ad033bc71698fc6c621c29be66f9d59a` — the result sink was validated
  by *path* but written with truncating replacement semantics, so a pathname
  outside every protected root that was an NTFS hard link to a protected store
  (or any other pre-existing object) could be truncated and replaced.

This archived file carries the exact `CORRECTION_04` technical bytes forward
through `CORRECTION_05` into `CORRECTION_06`. `CORRECTION_04` first
corrected the validator defect found by the accepted 2026-09-16 one-shot
empirical run (section G below) while preserving everything `CORRECTION_01`,
`CORRECTION_02`, and `CORRECTION_03` established (sections A-F below); its
implementation theorem was accepted on substance, but its archive/context
documentation was Marco-**BLOCK**ed for a provenance defect (see Provenance
below). `CORRECTION_05` correctly fixed that provenance defect, but was
itself Marco-**BLOCK**ed because its repository-resident archive
`MANIFEST.json` retained a stale byte/SHA-256 identity for this README file
(`ARCHIVE_MEMBER_IDENTITY_STALE_README`; see Provenance below).
`CORRECTION_06` is the proposed successor: same launcher bytes, same
corrected two-commit provenance, corrected archive member identity.

### F. The result file is created atomically and exclusively

A result artifact is a **new file only**. The final write is a single
create-if-absent open — `open(path, "x")`, i.e. `O_CREAT|O_EXCL`,
`CREATE_NEW` on Windows — in `create_result_file_exclusive()`. The existence
test and the creation are one kernel operation, so there is no window between
them.

Any object already occupying the destination pathname makes creation fail
**before a single byte is written**:

- an ordinary pre-existing file;
- an NTFS hard link — whichever file object it shares. Path normalization and
  link resolution cannot reveal that a directory entry aliases the authority
  store, ledger store, or Candidate-02 artifact, but it is still an existing
  entry, so creation fails;
- an object a racing process created after the path checks accepted the
  destination.

That object is never truncated, replaced, renamed, unlinked, chmod-ed, or
re-created. The run fails closed with `OUTPUT_PATH_ALREADY_EXISTS`
(`OUTPUT_EXCLUSIVE_CREATE_FAILED:<error>` for any other creation failure),
`output_sink.output_written = false`, one complete V2 failure JSON on stdout,
a non-zero exit, no production PASS marker, and **no retry**. The default
OS-temp destination goes through the same primitive — a random filename is not
a substitute for exclusive creation. The `CORRECTION_02` protected-root,
junction/symlink, and alias checks all remain as defense in depth.

The PowerShell wrapper now reports a result file's byte length and SHA-256
only when the probe itself reports `output_written: true`. It no longer calls
`Test-Path` on the requested pathname, which after a refused sink could stat a
path under the deployed-state root, or hash a pre-existing object — such as a
hard link to a protected store — and print that as if it were the result.

A refused invocation (a fixture override supplied without fixture mode) no
longer resolves the frozen production source paths. On Windows,
`Path.resolve()` opens a zero-access handle to an existing path, and a refusal
has no reason to touch the deployed stores; the source-binding observations
stay null and the mandatory validator still fails the run closed.

### A. Production PASS is bound to the actual resolved sources

`CORRECTION_01` froze the expected N1 identities, but those comparisons were
populated from path/domain/instance strings stored *inside* the SQLite
databases, and the launcher still accepted caller-selected `-Repo`,
`-AuthorityPath`, and `-LedgerPath`. A stale byte-copy of the accepted stores
at another filesystem location therefore kept the original embedded
identities and satisfied the gate.

`CORRECTION_02` adds a second, independent layer. `production_expectations()`
takes no arguments and returns the frozen production topology:

```text
repo      = C:\b1\kals\ARB
authority = C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority\arb_execution_authority_v1.sqlite3
ledger    = C:\b1\kals\arb_state\kalshi_demo_primary_v1\ledger\subaccount1_execution_v2.sqlite3
```

`check_production_source_binding()` compares the **actual resolved**
filesystem path of each source against its frozen expectation (link-resolved,
and case-insensitive after normalization as Windows requires), and the result
reports `source_binding.resolved_*_source_path`,
`source_binding.expected_*_path`, and explicit `*_source_bound` booleans.
Production terminal `PASS` requires **both** layers.

There is no production `-Repo`/`-AuthorityPath`/`-LedgerPath`/
`-ConflictDomain` parameter any more. The only way to read from another
location is the explicitly nonproduction fixture seam described below.

### B. The result sink is safe by construction

The predecessor defaulted `-OutputPath` to `$PSScriptRoot\...`, which is
inside canonical `project_archive/...` — so an ordinary installed invocation
created a repository file while the result declared `repository_writes =
NONE`. The sink was also caller-selectable with no alias or protected-root
guard.

`CORRECTION_02`:

- defaults the result destination to a unique OS-temp file, never
  `$PSScriptRoot`;
- validates every requested destination through `classify_output_sink()`
  before a single byte is written;
- rejects any destination under the canonical repository root, under
  `C:\b1\kals\arb_state`, or aliasing the authority store, ledger store,
  Candidate-02 artifact, or the launcher itself;
- rejects a destination that resolves through a junction/symlink parent
  **into** a protected root;
- on an unsafe sink writes zero bytes, still emits one complete V2 failure
  JSON on stdout, exits non-zero, and emits no production PASS marker.

The guard's first layer is purely lexical and performs no filesystem access
at all, so a request aimed at deployed state is refused without the tool
touching deployed state.

### C. Mutation proof on every readable path

The predecessor captured pre-read file proof but could return from a
schema/integrity/open failure before the post-read proof ran.
`_read_local_state()` now runs its whole read phase inside a `try` whose
`finally` closes every opened connection and then calls
`_finalize_mutation_proof()` for **every store whose pre-proof succeeded**,
regardless of how the phase ended. A post-proof that cannot itself be
obtained is classified `POST_READ_PROOF_UNOBTAINABLE:<store>` and fails
closed. A store that was never readable keeps explicit nulls — a missing file
cannot have a before/after proof, and that gap stays classified rather than
fabricated.

### D. A final mandatory-observation validator

`validate_mandatory_observations()` walks the fully assembled result against
declared `MANDATORY_NON_NULL_OBSERVATIONS` /
`MANDATORY_PRESENT_OBSERVATIONS` path sets and emits
`MISSING_REQUIRED_FIELD:<dotted.path>` for anything absent or nulled. It runs
last, immediately before the completeness decision, so individually removing
or nulling any mandatory observation — including `observation_timestamp_utc`,
`identity.authority_schema_revision`, `domain.bootstrap_contract_sha256`,
`identity.ledger_path`, and the new actual-source-path observations —
provably blocks `PASS`. The regression suite proves this by nulling each one
in an otherwise complete real launcher result, both purely and end to end.

### E. Frozen contract facts are constants, not parameters

The expected durable fill ID and the Candidate-02 expected raw/semantic
identities are fixed by the V2 observation contract. Their production CLI
parameters (`-FillId`, `-ExpectedCandidateRawSha256`,
`-ExpectedCandidateSemanticSha256`) are removed. The contract's Candidate-02
values (`reconciliation_read_deadline_ms = 30000`, and all four normal send
maxima `= 0`) are additionally gated for a production observation.

## Safety model

- Every SQLite connection is opened with the URI `mode=ro` query parameter.
  This is enforced by SQLite itself: an attempted write against such a
  connection fails at the driver level regardless of which code path is
  reached.
- The canonical `arb.execution_ledger`/`arb.venues.kalshi.ledger_binding`
  "open + catch up" writer-candidate machinery
  (`_open_locked`, `read_active_local_safety_state_v1`, and everything built
  on the same acquisition path) is **deliberately not used**, because it can
  perform a legitimate authority-anchor "catch-up" `UPDATE`+`COMMIT` when the
  ledger is ahead of the authority row. That is a real persistent-state write
  this tool must never perform, even implicitly. Instead, V2 calls the
  underlying pure validation/replay primitives directly
  (`_validate_schema`, `_validate_integrity`, `_authority_meta`,
  `_authority_row`, `_active_ledger_meta`, `load_and_validate_events`,
  `replay_projection`) against its own `mode=ro` connections.
- Both SQLite files' bytes, SHA-256, and mtime are captured before and after
  the read and proven identical (`mutation_proof` in the result), on
  successful runs and on readable failing runs alike.
- No Kalshi access, no credentials, no network, no restricted-session
  append, no risk-config consumption, no writer release, no automatic retry.
- `canonical_main_commit`/`canonical_main_tree` are captured fresh from the
  live repository every invocation. They are informational provenance only —
  never gated against a frozen historical commit — because this launcher is
  meant to keep working as canonical `main` advances.
- The historical trusted tail (sequence/hash) is never hard-coded; it is read
  fresh every invocation.
- The post-probe local convenience report (result byte length and SHA-256) is
  wrapped so that no failure there can change the terminal classification or
  the process exit code.

## Usage

```powershell
.\RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02.ps1 `
    -Candidate02Path "C:\path\to\accepted_risk_config_candidate.json"
```

The complete production parameter surface is:

| Parameter | Role |
|---|---|
| `-Candidate02Path` | **Required.** Path to the accepted risk-config candidate artifact. Its expected raw and semantic identities are frozen, so substituting another file fails closed rather than binding a different expectation. |
| `-Python` | Interpreter path. Defaults to the accepted local `pmresearch` CPython 3.12. |
| `-OutputPath` | Optional local result destination. Defaults to a unique OS-temp file; validated before any write. |

Everything else — repository root, authority store, ledger store, conflict
domain, expected fill ID, and both expected Candidate-02 identities — is a
frozen contract constant with no production parameter.

Exit code `0` and `READ_ONLY_REVALIDATION_TERMINAL=PASS` are emitted only for
a complete **production** observation. Otherwise the script still emits the
complete JSON result (for human review) but exits non-zero.

### G. `authority_path` / `ledger_path` frozen metadata comparison is
Windows drive-letter/component case-insensitive

The one-shot authorized production execution on 2026-09-16 halted with
`RESULT_SCHEMA_INCOMPLETE` and exactly two failures,
`PRODUCTION_IDENTITY_MISMATCH:authority_path` and
`PRODUCTION_IDENTITY_MISMATCH:ledger_path`, even though every other frozen
identity field matched, the independent actual-source-binding gate passed
for all three real sources, both path-identity SHA-256 fields matched, and
mutation proof passed. The observed durable metadata path strings used
lowercase Windows drive-letter spelling (`c:\...`); the frozen constants use
uppercase (`C:\...`). This was a validator implementation defect, not
evidence that a different source file was read.

`check_frozen_production_identity()` now compares exactly these two keys
with `str(observed).casefold() == str(expected).casefold()`. Every other
frozen identity field, including `authority_store_path_identity_sha256` and
`ledger_path_identity_sha256`, remains exact case-sensitive equality. No
`os.path.normpath`/`normcase`, separator conversion, dot-segment collapse,
alias/symlink acceptance, or path relocation was added to this comparison,
and the independent actual-source-binding gate
(`check_production_source_binding`, section A) is unchanged and remains
load-bearing: a byte-identical copy of the accepted stores at another
filesystem location is still refused even when its embedded metadata path
strings are case-equivalent to the frozen ones.

## Result contract

Implements `02_CONTROLLING/OBSERVATION_CONTRACT_V2.md` from the accepting
dispatch bundle in full: result schema identity
`ARB_R1_D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_RESULT_V2`, an explicit
machine-checkable `observation_completeness` section, and terminal `PASS`
gated on all nine completeness preconditions in that contract, plus the
`CORRECTION_01` frozen-identity gate (`CORRECTION_04`-corrected per section G
above), the `CORRECTION_02` actual-source binding and output-sink gates, and
the `CORRECTION_03` exclusive result-creation rule. A missing required
observation is classified `RESULT_SCHEMA_INCOMPLETE`, never silently
omitted, and never yields a false `PASS`.

## Nonproduction fixture mode — not an operator path

`-NonProductionFixtureMode` and the `-Fixture*` parameters exist solely so
the offline regression suite can exercise this launcher against synthetic
SQLite fixtures in a temporary directory. **This is not a production operator
option and must never be used for a real observation.**

Structurally it cannot forge a production result:

- the result carries `mode.observation_mode =
  NONPRODUCTION_TEST_FIXTURE` and
  `mode.nonproduction_fixture_marker =
  NONPRODUCTION_TEST_FIXTURE_RESULT_NOT_A_PRODUCTION_OBSERVATION`;
- a complete fixture observation returns status
  `NONPRODUCTION_FIXTURE_COMPLETE` and **exit code 3**, never `0`;
- the launcher prints `READ_ONLY_REVALIDATION_TERMINAL=PASS` only for exit
  `0`, so no fixture run can emit the production terminal marker;
- supplying any `-Fixture*` value **without** `-NonProductionFixtureMode` is
  rejected: the probe emits the complete V2 failure envelope with
  `FIXTURE_OVERRIDE_WITHOUT_FIXTURE_MODE`, performs no state read, and exits
  non-zero.

`-FixtureRaceOccupyOutputBeforeCreate` exists only to prove the
validation-to-create race is closed: after the path checks accept the
destination and immediately before the exclusive create, it places a fixed
marker object at that pathname exactly as a racing process would. The hook
itself also uses exclusive creation, runs only in fixture mode, and cannot
affect production PASS.

## What this launcher does NOT authorize

Preparing or running this launcher against deployed N1 state is a separately
authorized activity. This archived file and its offline test coverage do not
themselves authorize a real run, Kalshi access, credential use, restricted-
session lifecycle append, risk-config consumption, writer-proof release,
Gate D, Stage 3G+, Demo venue write, production access, or R1-D08.

## Provenance

- Predecessor V1 launcher: `C:\b1\kals\arb_local\d8\RUN_R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_01.ps1`
  (external/local; not repository-resident).
- Accepted `CORRECTION_02` closure evidence: Marco `ACCEPT FINDING`,
  2026-09-14 (`R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_01_CORRECTED_RESULT.json`,
  7899 bytes, SHA-256 `a0568f5617c313b51edaf1e8787e0e75855b6ed6be650aea8caa2241d0feb0b0`).
- All three blocked V2 candidates (`1ae681f6648c6f2197b1991e75b8b2c11abb07ef`,
  `1c4d44c7b9af67da57f19f0e4423803a26bbdbc4`, and
  `b30a8870ad033bc71698fc6c621c29be66f9d59a`) were used only as noncanonical
  content seeds and are never this candidate's Git ancestors.
- `CORRECTION_03` was installed canonically through installation commit
  `a16f1286edf72215b372bca1146d248eac55f0c4` (tree `8b8bd8c715600e6c936ece2167004b9ffab58a4b`,
  parent `b30236e974b708dfa5e7ab7dac8b848d2ca88d8d`, exactly the reviewed
  candidate `5e97e09600afab60392628679757b5015b731623`, 7 changed paths). A
  later, separate documentation-continuity task installed commit
  `5cfe81e48da44741b3d229c92da0f64bbf34e9fc` (tree
  `fd02a506c7f3bd8f6308db6d85017342899a7f41`, parent `a16f1286edf72215b372bca1146d248eac55f0c4`,
  2 changed documentation paths) solely to record the already-completed
  CORRECTION_03 installation in A20/`ARTIFACT_INDEX.md`. These are two
  distinct canonical events: `5cfe81e48da44741b3d229c92da0f64bbf34e9fc` is the
  later continuity documentation commit and the current base for this
  candidate, not the commit that installed the CORRECTION_03 implementation.
- The accepted one-shot authorized production execution against `CORRECTION_03`
  (task `R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_EXECUTION_01`,
  2026-09-16) halted `READ_ONLY_REVALIDATION_V2_EXECUTION_HALTED_RETURN_TO_MARCO`
  with terminal `READ_ONLY_REVALIDATION_TERMINAL=RESULT_SCHEMA_INCOMPLETE` and
  exactly the two `authority_path`/`ledger_path` failures corrected in section
  G. The transient 6016-byte result JSON
  (SHA-256 `d18b71468e880e9146ba3629625c7d98a9c1c54e9ba6061224b19baa92e3d397`)
  was deleted by the authorized execution contract after capture, per its
  design, and its exact bytes are not available as a review input; the
  accepted material finding is the user-reported observation record in
  `03_REVIEW_DECISION/MARCO_ACCEPT_FINDING_CORRECTION_04_HANDOFF.md` of the
  CORRECTION_04 correction dispatch bundle. That one-shot execution
  authorization is consumed; no correction since has authorized another
  deployed-N1 read.
- The `CORRECTION_04` candidate (commit `e6e5b913e1da8ae2960e328ce3f70c122179a4a1`,
  tree `3ef6629ef27b2811e9d332c65b6b5e8ff24b0db1`, parent
  `5cfe81e48da44741b3d229c92da0f64bbf34e9fc`) implemented the section-G
  correction correctly and its implementation theorem was accepted on
  substance, but Marco **BLOCK**ed it for `PROVENANCE_CONFLATION_
  IMPLEMENTATION_INSTALL_COMMIT_VS_CONTINUITY_COMMIT`: its archive/context
  documentation described `5cfe81e48da44741b3d229c92da0f64bbf34e9fc` as the
  commit that installed CORRECTION_03. It is noncanonical content-seed only
  and is never Git ancestry of this candidate; its launcher, launcher
  sidecar, and V2 test bytes are carried forward byte-identical here.
- The `CORRECTION_05` candidate (commit `e7f0bf536d6bcf4a7e0025f35ca43cc706b8cb60`,
  tree `73f5f1be419a6f59ac12a69acf9d59a42589437b`, parent
  `5cfe81e48da44741b3d229c92da0f64bbf34e9fc`) correctly fixed the
  `CORRECTION_04` provenance-conflation defect above, but Marco
  **BLOCK**ed it for `ARCHIVE_MEMBER_IDENTITY_STALE_README`: its
  repository-resident archive `MANIFEST.json` retained the pre-edit
  README tuple (18514 bytes, SHA-256
  `84cc87742883ce407f387ad9dc4c4d3060b4a1a2bf72a25aae5cfe524d9a172d`)
  instead of the actual final `CORRECTION_05` README bytes (20453 bytes,
  SHA-256 `be31473f3c3e8c2afd809d47591c9f109d115c54ce62f82fa64dc7a2d6a24984`).
  The review-package `MANIFEST.txt`/`DELIVERY_MANIFEST.json` recorded the
  correct final identity; the defect was isolated to the repository-resident
  archive manifest. It is noncanonical content-seed only and is never Git
  ancestry of this candidate; its launcher, launcher sidecar, and V2 test
  bytes are carried forward byte-identical here.
- This corrected V2 successor is implemented under task
  `R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_IMPLEMENTATION_CANONICALIZATION_01_CORRECTION_06`,
  descends directly from canonical base `5cfe81e48da44741b3d229c92da0f64bbf34e9fc`,
  and is a proposed candidate only, not yet canonically installed. This
  archive `MANIFEST.json`'s `README.md` member identity is derived from
  this file's own final `CORRECTION_06` bytes (see `MANIFEST.json` in this
  directory), not copied from any predecessor's recorded value.

See `MANIFEST.json` in this directory for exact file identities, and
`project_context/PROJECT_STATE_CHECKPOINT_2026_09_06_R1_B02_CORRECTION_04_D07_READ_ONLY_LIVE_ENTRYPOINT_SPECIFICATION.md`
section `A20` for the canonical continuity record.
