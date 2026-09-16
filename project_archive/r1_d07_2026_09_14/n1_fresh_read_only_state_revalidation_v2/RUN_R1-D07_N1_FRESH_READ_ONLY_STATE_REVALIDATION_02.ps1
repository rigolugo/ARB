param(
    [Parameter(Mandatory = $true)][string]$Candidate02Path,
    [string]$Python = "C:\Users\RigobertoLugo\miniconda3\envs\pmresearch\python.exe",
    [string]$OutputPath,
    [switch]$NonProductionFixtureMode,
    [string]$FixtureRepo,
    [string]$FixtureAuthorityPath,
    [string]$FixtureLedgerPath,
    [string]$FixtureConflictDomain,
    [string]$FixtureFillId,
    [string]$FixtureExpectedCandidateRawSha256,
    [string]$FixtureExpectedCandidateSemanticSha256,
    [string]$FixtureExpectedIdentityPath,
    [string[]]$FixtureDropObservation = @(),
    [switch]$FixtureRaceOccupyOutputBeforeCreate
)

# R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_02 (V2, CORRECTION_03)
#
# Self-contained canonical successor to the accepted V1 launcher plus its
# CORRECTION_02 missing-field closure wrapper (Marco ACCEPT FINDING,
# 2026-09-14). One invocation produces one complete, review-ready
# ARB_R1_D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_RESULT_V2 JSON result and
# cannot terminal-PASS while a required observation is absent -- the exact
# V1 defect (result completeness, not state-reader safety) this successor
# closes.
#
# CORRECTION_03 (this candidate) closes the single remaining Marco-BLOCKED
# defect in the immediately preceding candidate
# (`b30a8870ad033bc71698fc6c621c29be66f9d59a`, noncanonical, never ancestry of
# this candidate):
#   F. the result artifact is created ATOMICALLY AND EXCLUSIVELY. The
#      predecessor validated the destination by path and then wrote it with
#      truncating replacement semantics, so a pathname OUTSIDE every protected
#      root that is an NTFS hard link to the authority store, ledger store,
#      Candidate-02 artifact, or any other object could still be truncated and
#      replaced -- path normalization and link resolution cannot reveal that a
#      directory entry shares its file object with a protected file. The final
#      write is now a single create-if-absent open (`open(path, "x")`, i.e.
#      O_CREAT|O_EXCL / CREATE_NEW). Any object already occupying the pathname
#      -- an ordinary file, a hard link, or one a racing process created after
#      validation -- makes creation fail before a single byte is written. That
#      object is never truncated, replaced, renamed, unlinked, or re-created;
#      the run fails closed with `OUTPUT_PATH_ALREADY_EXISTS`,
#      `output_written = false`, one complete V2 failure JSON on stdout, a
#      non-zero exit, no production PASS marker, and no retry. The
#      CORRECTION_02 path checks below all remain as defense in depth.
#
# CORRECTION_02 (retained) fixed the Marco-BLOCKED defects of
# `1c4d44c7b9af67da57f19f0e4423803a26bbdbc4`, which itself succeeded the first
# blocked candidate `1ae681f6648c6f2197b1991e75b8b2c11abb07ef` (all three
# predecessors noncanonical and never ancestry):
#   A. production PASS is now bound to the ACTUAL RESOLVED filesystem sources
#      (canonical repository root, authority SQLite file, ledger SQLite file),
#      not merely to path strings stored inside the databases. A stale
#      byte-copy of the accepted stores at another location keeps its embedded
#      metadata identities but can no longer reach production PASS. There is
#      no production `-Repo`/`-AuthorityPath`/`-LedgerPath` parameter at all:
#      the production sources are frozen constants, and the only way to point
#      the reader elsewhere is the explicitly nonproduction fixture seam below,
#      which is structurally incapable of emitting the production PASS marker;
#   B. the result sink is safe by construction. The default output destination
#      is a unique OS-temp file (NEVER `$PSScriptRoot`, which is inside the
#      canonical repository), and every requested destination is normalized,
#      resolved, and rejected if it lands under the canonical repository root,
#      under the deployed-state root, or on an alias of a protected input file.
#      An unsafe sink receives zero bytes, still yields one complete V2 failure
#      JSON on stdout, exits non-zero, and emits no production PASS marker;
#   C. the before/after mutation proof is now attempted in a finally-equivalent
#      path, after SQLite connections are closed, for EVERY store whose
#      pre-proof succeeded -- including readable stores whose schema/integrity/
#      domain/replay/candidate checks fail. A post-proof that cannot itself be
#      obtained is explicitly classified and fails closed;
#   D. a final machine-checkable mandatory-observation validator
#      (`validate_mandatory_observations`) runs over the fully assembled result,
#      so individually removing or nulling any mandatory observation --
#      including `observation_timestamp_utc`, `identity.authority_schema_revision`,
#      `domain.bootstrap_contract_sha256`, `identity.ledger_path`, and the new
#      actual-source-path observations -- provably blocks PASS;
#   E. the already-controlling frozen production facts (expected durable fill
#      ID, Candidate-02 expected raw/semantic identities) are contract
#      constants rather than ordinary runtime parameters.
#
# Safety invariants preserved from the predecessors (unchanged by this
# correction):
#   - authority/ledger SQLite access is opened with URI `mode=ro` ONLY. This
#     is enforced by SQLite itself, not merely by this script's call
#     discipline: any attempted write against a mode=ro connection fails at
#     the driver level rather than silently succeeding. The canonical
#     `arb.execution_ledger` "open + catch up" helper (`_open_locked`, and
#     everything built on it such as the normal-writer-candidate/read-active-
#     local-safety-state family in `ledger_binding.py`) is DELIBERATELY NOT
#     used here, because it opens read-write and can perform a legitimate
#     "authority anchor catch-up" UPDATE+COMMIT when the ledger is ahead of
#     the authority row. This read-only tool instead calls the same
#     underlying pure validation/replay primitives
#     (`_validate_schema`/`_validate_integrity`/`_authority_meta`/
#     `_authority_row`/`_active_ledger_meta`/`load_and_validate_events`/
#     `replay_projection`) directly against its own mode=ro connections, and
#     independently proves both stores' bytes/hash/mtime are unchanged
#     before and after the read.
#   - the frozen 17-field internal N1 metadata/domain identity gate from
#     CORRECTION_01 remains required, IN ADDITION to the new actual-source
#     binding. Both layers must pass for production PASS.
#   - the complete V2 envelope is constructed before any fallible operation.
#   - no Kalshi/network access, no credential use, no restricted-session
#     append, no risk-config consumption, no writer release.
#   - no automatic retry.
#   - historical tail sequence/hash are never hard-coded as current truth;
#     the authority/ledger tail is read fresh every invocation.
#   - `canonical_main_commit`/`canonical_main_tree` are captured fresh from
#     the live repository every invocation and are informational provenance
#     only, never gated against a frozen historical commit -- this successor
#     is meant to keep working as `main` advances.
#
# Exit codes:
#   0 -> production observation, every completeness precondition satisfied.
#        This is the ONLY case that prints READ_ONLY_REVALIDATION_TERMINAL=PASS.
#   1 -> incomplete/failed result (production or fixture).
#   3 -> nonproduction fixture observation that satisfied every gate it is
#        capable of satisfying. Deliberately non-zero so that no fixture run,
#        however green, can ever emit the production terminal PASS marker.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$TaskId = "R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2"

# Frozen production topology (03_REVIEW_DECISION/MARCO_BLOCK_CORRECTION_02_
# HANDOFF.md, 04_IMPLEMENTATION_GUIDANCE/ACTUAL_SOURCE_PATH_BINDING.md).
# These are contract constants. There is intentionally no production
# parameter that can replace any of them.
$FrozenRepo = "C:\b1\kals\ARB"
$FrozenAuthorityPath = "C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority\arb_execution_authority_v1.sqlite3"
$FrozenLedgerPath = "C:\b1\kals\arb_state\kalshi_demo_primary_v1\ledger\subaccount1_execution_v2.sqlite3"

function Halt([string]$Reason) {
    throw "READ_ONLY_REVALIDATION_V2_PREFLIGHT_HALT: $Reason"
}

# --------------------------------------------------------------------------
# Nonproduction fixture seam (IDENTITY_BINDING_AND_TEST_SEAM.md Design B).
#
# Offline synthetic fixtures cannot reproduce the accepted Windows deployment
# topology or the accepted N1 identities, so the end-to-end regression suite
# needs a way to point this launcher at temporary synthetic stores. That seam
# is explicit, is visibly marked in the result, and CANNOT emit the production
# terminal PASS marker (the probe reserves exit code 0 exclusively for a
# production observation). Supplying any -Fixture* value WITHOUT
# -NonProductionFixtureMode is rejected rather than silently honoured.
# --------------------------------------------------------------------------
$FixtureValues = @{
    "FixtureRepo"                              = $FixtureRepo
    "FixtureAuthorityPath"                     = $FixtureAuthorityPath
    "FixtureLedgerPath"                        = $FixtureLedgerPath
    "FixtureConflictDomain"                    = $FixtureConflictDomain
    "FixtureFillId"                            = $FixtureFillId
    "FixtureExpectedCandidateRawSha256"        = $FixtureExpectedCandidateRawSha256
    "FixtureExpectedCandidateSemanticSha256"   = $FixtureExpectedCandidateSemanticSha256
    "FixtureExpectedIdentityPath"              = $FixtureExpectedIdentityPath
}
$SuppliedFixtureParameters = @(
    $FixtureValues.Keys | Where-Object { -not [string]::IsNullOrEmpty($FixtureValues[$_]) } | Sort-Object
)
if ($FixtureDropObservation.Count -gt 0) {
    $SuppliedFixtureParameters = @($SuppliedFixtureParameters + "FixtureDropObservation" | Sort-Object)
}
if ($FixtureRaceOccupyOutputBeforeCreate.IsPresent) {
    $SuppliedFixtureParameters = @($SuppliedFixtureParameters + "FixtureRaceOccupyOutputBeforeCreate" | Sort-Object)
}
$FixtureModeRequested = $NonProductionFixtureMode.IsPresent
$FixtureOverrideWithoutMode = ((-not $FixtureModeRequested) -and ($SuppliedFixtureParameters.Count -gt 0))

if ($FixtureModeRequested) {
    $EffectiveRepo = if ([string]::IsNullOrEmpty($FixtureRepo)) { $FrozenRepo } else { $FixtureRepo }
} else {
    $EffectiveRepo = $FrozenRepo
}

# CORRECTION_02 defect B: the default result destination must never be inside
# the canonical repository. `$PSScriptRoot` is under `project_archive/...`, so
# the predecessor's default silently created a repository file on every
# ordinary invocation while declaring `repository_writes = NONE`. The default
# is now a unique OS-temp file, and the embedded probe independently validates
# whatever destination it is given before writing a single byte.
$DefaultOutputSinkUsed = $false
if (-not $OutputPath) {
    $DefaultOutputSinkUsed = $true
    $OutputPath = Join-Path ([System.IO.Path]::GetTempPath()) `
        ("R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_RESULT_" + [Guid]::NewGuid().ToString("N") + ".json")
}

# Preflight halts here are reserved for environment prerequisites without
# which the read cannot even be attempted (no interpreter, no repository to
# resolve `src` from). A missing authority store, ledger store, or
# Candidate-02 file is instead an *observation* the embedded probe itself
# reports as a specific, gated completeness failure in the JSON result (see
# module docstring) -- this wrapper must not short-circuit that path with an
# uncaught exception, or the two failure-reporting mechanisms would diverge
# for what is substantively the same condition.
if (-not (Test-Path -LiteralPath $EffectiveRepo -PathType Container)) { Halt "canonical repo path not found: $EffectiveRepo" }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { Halt "python interpreter not found: $Python" }

# Fresh provenance capture -- informational only (see header). A git failure
# here is not a preflight halt: it becomes a reported, gated, missing
# `canonical_main_commit`/`canonical_main_tree` field in the JSON result, so
# the completeness gate -- not this wrapper -- is the single place PASS/FAIL
# is decided.
$GitCommit = ""
$GitTree = ""
try {
    $GitCommit = (& git -C $EffectiveRepo rev-parse HEAD 2>$null | Select-Object -First 1)
    $GitTree = (& git -C $EffectiveRepo rev-parse 'HEAD^{tree}' 2>$null | Select-Object -First 1)
} catch {
    $GitCommit = ""
    $GitTree = ""
}
if ($null -eq $GitCommit) { $GitCommit = "" }
if ($null -eq $GitTree) { $GitTree = "" }

Write-Output "READ_ONLY_REVALIDATION_V2_PREFLIGHT=PASS"
Write-Output "TASK_ID=$TaskId"
Write-Output "N1_MODE=LOCAL_SQLITE_READ_ONLY_URI_MODE_RO"
if ($FixtureModeRequested) {
    Write-Output "OBSERVATION_MODE=NONPRODUCTION_TEST_FIXTURE"
} else {
    Write-Output "OBSERVATION_MODE=PRODUCTION"
}
Write-Output "KALSHI_ACCESS=NONE"
Write-Output "CREDENTIAL_ACTIVITY=NONE"
Write-Output "NETWORK_ACTIVITY=NONE"
Write-Output "N1_MUTATION=PROHIBITED"
Write-Output "REPOSITORY_WRITE=NONE"
Write-Output "AUTOMATIC_RETRIES=0"
Write-Output "DEFAULT_RESULT_SINK_USED=$DefaultOutputSinkUsed"
Write-Output "CANONICAL_MAIN_COMMIT=$GitCommit"
Write-Output "CANONICAL_MAIN_TREE=$GitTree"
Write-Output ""
Write-Output "=== N1 LOCAL READ-ONLY REVALIDATION V2 BOUNDARY ==="

# --------------------------------------------------------------------------
# Embedded read-only probe (single canonical invocation; see module
# docstring below for the full safety/derivation rationale). Kept in a
# single-quoted here-string (no PowerShell interpolation of `$`/backticks)
# and materialized to a private temp .py file the interpreter loads by path
# -- never passed as inline command-line source -- so native argument
# parsing can never strip or reinterpret a quote character inside it (the
# CORRECTION_01-era native-argument-quoting defect this design avoids by
# construction).
# --------------------------------------------------------------------------
$Py = @'
"""R1-D07 N1 fresh read-only state revalidation -- V2 canonical successor
probe (CORRECTION_03).

Produces one complete ARB_R1_D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_RESULT_V2
JSON result per invocation. Every observation required by
02_CONTROLLING/OBSERVATION_CONTRACT_V2.md is either present with a real
value or, for the specific fields the contract marks conditional, an
explicit NOT_EXPOSED_BY_TRUSTED_PROJECTION sentinel. A missing required
field is recorded in observation_completeness.failures and blocks terminal
PASS; it is never silently omitted or defaulted.

CORRECTION_02 closed the Marco-BLOCKED defects A-E below, and CORRECTION_03
closes defect F, the only one remaining after them:

  F. THE RESULT FILE IS CREATED ATOMICALLY AND EXCLUSIVELY.
     B (below) validates the destination by PATH. A pathname outside every
     protected root can still be an NTFS hard link to a protected file, and no
     amount of path normalization or link resolution reveals that. The
     predecessor then wrote with truncating replacement semantics, so such a
     link could truncate the authority/ledger store after the mutation proof
     had already passed. `create_result_file_exclusive()` replaces that write
     with one create-if-absent open (`open(path, "x")`): any object already
     at the pathname -- ordinary file, hard link, or one a racing process
     created after validation -- makes creation fail before any byte is
     written, and the run fails closed with OUTPUT_PATH_ALREADY_EXISTS,
     output_written=false, a complete V2 failure JSON on stdout, a non-zero
     exit, no production PASS, and no retry. The default OS-temp destination
     goes through the same primitive; a random name is not a substitute for
     exclusive creation.

  A. PRODUCTION PASS IS BOUND TO THE ACTUAL RESOLVED SOURCES.
     `production_expectations()` takes no arguments and returns the frozen
     production repo/authority/ledger filesystem sources, conflict domain,
     expected fill ID, Candidate-02 identities, and the frozen 17-field N1
     identity set. `check_production_source_binding()` compares the ACTUAL
     resolved filesystem path of each source against its frozen expectation
     (case-insensitively after normalization, as required on Windows), and
     `check_frozen_production_identity()` separately compares the identities
     stored INSIDE the databases. Both layers are required: an internally
     valid byte-copy of the accepted stores at another filesystem location
     retains its embedded identities but fails the source-binding layer.

  B. THE RESULT SINK IS SAFE BY CONSTRUCTION.
     `classify_output_sink()` validates the requested destination before any
     byte is written. Layer 1 is purely lexical (zero filesystem access) and
     rejects anything under a protected root or aliasing a protected file --
     so a request aimed at deployed state is refused without touching
     deployed state at all. Layer 2 then resolves the request through its
     nearest existing parent, defeating a junction/symlink parent that
     traverses INTO a protected root, and re-checks. An unsafe sink is
     written zero bytes, is classified, blocks PASS, and still yields one
     complete V2 failure JSON on stdout.

  C. MUTATION PROOF ON EVERY READABLE PATH.
     `_read_local_state()` runs its whole read phase inside a `try` whose
     `finally` closes every opened connection and then calls
     `_finalize_mutation_proof()` for every store whose pre-proof succeeded --
     regardless of whether the phase returned early on a schema, integrity,
     domain, replay, or candidate failure. A post-proof that cannot itself be
     obtained is classified `POST_READ_PROOF_UNOBTAINABLE:<store>` and fails
     closed. A store with no successful pre-proof keeps explicit nulls rather
     than a fabricated proof, and is separately classified as unreadable.

  D. A FINAL MANDATORY-OBSERVATION VALIDATOR.
     `validate_mandatory_observations()` walks the fully assembled result
     against the declared MANDATORY_NON_NULL_OBSERVATIONS /
     MANDATORY_PRESENT_OBSERVATIONS path sets and emits
     `MISSING_REQUIRED_FIELD:<dotted.path>` for anything absent or nulled.
     It is the last gate before the completeness decision, so removing or
     nulling any mandatory observation from an otherwise complete result
     provably blocks PASS.

  E. FROZEN PRODUCTION FACTS ARE CONSTANTS, NOT PARAMETERS.
     There is no `--repo`, `--authority`, `--ledger`, `--conflict-domain`,
     `--fill-id`, `--expected-candidate-raw-sha256`, or
     `--expected-candidate-semantic-sha256` argument. Every alternate value
     lives behind the explicitly nonproduction `--fixture-*` seam, which is
     only honoured together with `--nonproduction-fixture-mode` and which can
     never produce the production terminal PASS marker, because exit code 0
     and status READ_ONLY_REVALIDATION_PASS are reserved for a production
     observation.

Read-only by construction: every SQLite connection is opened with the URI
`mode=ro` query parameter, which SQLite itself enforces at the driver level
-- an attempted write against such a connection fails rather than silently
succeeding, regardless of what higher-level code path is reached. This
module deliberately calls the canonical `arb.execution_ledger` pure
validation/replay primitives directly (`_validate_schema`,
`_validate_integrity`, `_authority_meta`, `_authority_row`,
`_active_ledger_meta`, `load_and_validate_events`, `replay_projection`)
rather than the higher-level "open + catch up" helpers
(`_open_locked` and everything built on it, including
`ledger_binding.read_active_local_safety_state_v1` and the normal-writer-
candidate acquisition family), because those helpers open read-write and can
perform a legitimate authority-anchor "catch-up" UPDATE+COMMIT when the
ledger is ahead of the authority row -- a persistent-state write this
read-only tool must never perform, even implicitly. Before and after the
read, this module independently proves both SQLite files' bytes, SHA-256,
and mtime are byte-for-byte unchanged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path

RESULT_SCHEMA = "ARB_R1_D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_RESULT_V2"
SENTINEL_NOT_EXPOSED = "NOT_EXPOSED_BY_TRUSTED_PROJECTION"

# Status / exit-code contract. Exit 0 and STATUS_PRODUCTION_PASS are reserved
# exclusively for a complete PRODUCTION observation; the launcher prints
# READ_ONLY_REVALIDATION_TERMINAL=PASS only for exit 0, so no fixture run can
# ever emit the production terminal marker (CORRECTION_02 defect E / C02-T12).
STATUS_PRODUCTION_PASS = "READ_ONLY_REVALIDATION_PASS"
STATUS_FIXTURE_COMPLETE = "NONPRODUCTION_FIXTURE_COMPLETE"
STATUS_INCOMPLETE = "RESULT_SCHEMA_INCOMPLETE"
EXIT_PRODUCTION_PASS = 0
EXIT_INCOMPLETE = 1
EXIT_FIXTURE_COMPLETE = 3

OBSERVATION_MODE_PRODUCTION = "PRODUCTION"
OBSERVATION_MODE_FIXTURE = "NONPRODUCTION_TEST_FIXTURE"
NONPRODUCTION_FIXTURE_MARKER = "NONPRODUCTION_TEST_FIXTURE_RESULT_NOT_A_PRODUCTION_OBSERVATION"

EXPECTED_FILL_ID = "07212270-bae1-9bda-8e24-cd2221a09d60"

# Economic fields proving the exact known fill theorem (checkpoint A18.2).
# The separately recorded `canonical_fill_sha256` from that checkpoint is a
# provenance identity for the original acceptance evidence, not a value this
# read-only tool independently recomputes; it is reported informationally
# only from the durable canonical payload when present, and is not itself a
# completeness gate.
EXPECTED_FILL_STR_FIELDS = {
    "ticker": "KXAAAGASD-26SEP02-4.1200",
    "outcome_side": "YES",
    "authoritative_created_time_utc": "2026-09-01T23:34:43.231843Z",
}
EXPECTED_FILL_DECIMAL_FIELDS = {
    "quantity": Decimal("1.00"),
    "yes_price": Decimal("0.5000"),
    "fee": Decimal("0.017500"),
}

# --- CORRECTION_02 defect E: frozen Candidate-02 contract identities -------
# The V2 observation contract already fixes these. They are implementation
# constants, NOT runtime arguments: the predecessor's
# `--expected-candidate-raw-sha256`/`--expected-candidate-semantic-sha256`
# production flags are removed, and the only way to bind a different expected
# value is the explicitly nonproduction fixture seam (C02-T11).
CANDIDATE02_RAW_SHA256 = "4495ade7fed522bf17a202d6f5422f608765b65a4463121175695c862b3f904c"
CANDIDATE02_SEMANTIC_SHA256 = "e16c9219b495062647b82b9e8a4d5e9c1b98f3e54ce43f0044c1a85fea162bbb"
CANDIDATE02_CONTRACT_VALUES = {
    "reconciliation_read_deadline_ms": 30000,
    "create_max_sends": 0,
    "modify_replace_max_sends": 0,
    "ordinary_cancel_max_sends": 0,
    "automated_execution_max_sends": 0,
}

# --- CORRECTION_02 defect A: frozen production filesystem topology --------
# Per 03_REVIEW_DECISION/MARCO_BLOCK_CORRECTION_02_HANDOFF.md and
# 04_IMPLEMENTATION_GUIDANCE/ACTUAL_SOURCE_PATH_BINDING.md, the production
# reader source root and both deployed store paths are frozen. The internal
# database metadata identity gate (FROZEN_PRODUCTION_IDENTITY, below) remains
# separately required: metadata alone is forgeable by copying the accepted
# files elsewhere, so the ACTUAL resolved source must match too.
FROZEN_PRODUCTION_SOURCES = {
    "repo": r"C:\b1\kals\ARB",
    "authority": r"C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority\arb_execution_authority_v1.sqlite3",
    "ledger": r"C:\b1\kals\arb_state\kalshi_demo_primary_v1\ledger\subaccount1_execution_v2.sqlite3",
}
FROZEN_DEPLOYMENT_ROOT = r"C:\b1\kals\arb_state"
FROZEN_CONFLICT_DOMAIN = "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=1"

# --- CORRECTION_01 defect 1 (preserved): frozen production N1 identity gate
# Exact accepted N1 identities per 03_REVIEW_DECISION/MARCO_BLOCK_
# CORRECTION_01_HANDOFF.md. These are implementation constants, not runtime
# arguments. Internal structural/replay consistency is necessary but NOT
# sufficient for the production terminal PASS marker -- every one of these
# frozen fields must ALSO equal its exact expected value, and (CORRECTION_02)
# the actual resolved source files must ALSO be the frozen ones.
FROZEN_PRODUCTION_IDENTITY = {
    "authority_namespace_id": "ARB_KALSHI_DEMO_PRIMARY_AUTHORITY_V1",
    "authority_instance_id": "772b53a9-7915-4133-957b-3d6c24dfdfc7",
    "authority_schema_revision": 1,
    "authority_path": r"C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority\arb_execution_authority_v1.sqlite3",
    "authority_store_path_identity_sha256": "dbf0afa85aa59c82879cc78e24340d7035074b43879df39eca98a1e3ac83f899",
    "ledger_instance_id": "485b37e9-738d-49f8-99cf-5f2e69589de6",
    "ledger_schema_revision": 2,
    "ledger_path": r"C:\b1\kals\arb_state\kalshi_demo_primary_v1\ledger\subaccount1_execution_v2.sqlite3",
    "ledger_path_identity_sha256": "ab36fd934f013f16795f161f20f1d63daecf8a385bfe260fc3a7bb8945e4d3b3",
    "conflict_domain_ref": FROZEN_CONFLICT_DOMAIN,
    "execution_domain_binding_id": "KEDB1_f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02",
    "execution_domain_binding_sha256": "f6aa344c8b573f2d436f76e5dc58601f8583af71a2555922d35f250ded123a02",
    "bootstrap_contract_sha256": "c387e47c2862e6082e75bc8eb8dfa47ed085ec7be98e8426970a278a953e7360",
    "active_contract_id": "AEDC1_f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53",
    "active_contract_sha256": "f2d62188997b28d2d36f4686c271cb9be43f10d1cbdf217960dda0ecf8e61c53",
    "incident_id": "adi_2c5c16c8e7299d0e6fccb23caec7c4d4",
    "writer_proof_id": "adwp_0b247ef6546e88308017a3168b9ad2b8",
}


def production_expectations() -> dict:
    """The complete frozen production expectation set.

    Deliberately takes NO arguments: there is no code path by which a runtime
    argument, environment variable, or CLI flag can reach it (C02-T01,
    C02-T10, C02-T11). `run()` uses exactly this for a production
    observation; the nonproduction fixture seam substitutes its own copy and
    is separately incapable of emitting the production terminal PASS marker.
    """
    return {
        "repo": FROZEN_PRODUCTION_SOURCES["repo"],
        "authority": FROZEN_PRODUCTION_SOURCES["authority"],
        "ledger": FROZEN_PRODUCTION_SOURCES["ledger"],
        "conflict_domain": FROZEN_CONFLICT_DOMAIN,
        "fill_id": EXPECTED_FILL_ID,
        "candidate_raw_sha256": CANDIDATE02_RAW_SHA256,
        "candidate_semantic_sha256": CANDIDATE02_SEMANTIC_SHA256,
        "identity": dict(FROZEN_PRODUCTION_IDENTITY),
    }


# --- path normalization / containment primitives --------------------------

def normalize_for_compare(path_text: str) -> str:
    """Case- and separator-normalized absolute form used for every path
    comparison. Windows path comparison must be case-insensitive after
    normalization (ACTUAL_SOURCE_PATH_BINDING.md); `os.path.normcase` is the
    platform-correct way to express that without hard-coding a lowercase
    assumption. Performs no filesystem access."""
    return os.path.normcase(os.path.normpath(os.path.abspath(path_text)))


def is_within_root(candidate_norm: str, root_norm: str) -> bool:
    """True when `candidate_norm` is the root itself or lies beneath it.
    Both arguments must already be `normalize_for_compare`d. Compares whole
    path components (via the trailing separator) so that a sibling directory
    whose name merely starts with the root's name is not treated as
    contained. Performs no filesystem access."""
    if candidate_norm == root_norm:
        return True
    return candidate_norm.startswith(root_norm.rstrip("\\/") + os.sep)


def resolve_actual_path(path_text: str) -> str:
    """Link-resolved absolute path. `Path.resolve()` is non-strict, so this
    works for a path that does not (yet) exist; it falls back to a purely
    lexical absolute form if the OS refuses to resolve at all."""
    try:
        return str(Path(path_text).resolve())
    except OSError:
        return os.path.abspath(path_text)


def resolve_through_existing_parent(path_text: str) -> str | None:
    """Resolve a not-yet-existing destination by link-resolving its nearest
    EXISTING ancestor and re-appending the remaining components
    (OUTPUT_SINK_SAFETY.md). Returns None when no ancestor can be resolved,
    which the caller treats as fail-closed."""
    target = Path(os.path.abspath(path_text))
    suffix: list[str] = []
    probe = target
    while True:
        try:
            if probe.exists():
                break
        except OSError:
            return None
        if probe.parent == probe:
            return None
        if not probe.name:
            return None
        suffix.append(probe.name)
        probe = probe.parent
    try:
        base = probe.resolve()
    except OSError:
        return None
    for name in reversed(suffix):
        base = base / name
    return str(base)


# --- CORRECTION_02 defect A: actual-source binding gate -------------------

def check_production_source_binding(*, resolved_repo, resolved_authority, resolved_ledger,
                                     expected_repo, expected_authority, expected_ledger) -> list[str]:
    """Pure gate proving the ACTUAL resolved filesystem sources are the
    expected ones. This is deliberately independent of the metadata identity
    gate: a byte-copy of the accepted stores at another location keeps its
    embedded `authority_store_resolved_path`/`ledger_resolved_path` strings
    and would satisfy the metadata layer alone (Marco BLOCK defect 1). Both
    sides are link-resolved and case-normalized before comparison, so a
    junction/symlink route to the same real file still binds correctly.
    Performs no SQLite access and reads no file content."""
    failures: list[str] = []
    for label, actual, expected in (
        ("repo", resolved_repo, expected_repo),
        ("authority", resolved_authority, expected_authority),
        ("ledger", resolved_ledger, expected_ledger),
    ):
        if actual is None or expected is None:
            failures.append(f"MISSING_REQUIRED_FIELD:source_binding.resolved_{label}_source_path")
            continue
        if normalize_for_compare(resolve_actual_path(actual)) != normalize_for_compare(resolve_actual_path(expected)):
            failures.append(f"PRODUCTION_SOURCE_PATH_MISMATCH:{label}")
    return failures


# --- CORRECTION_02 defect B: output sink safety ---------------------------

def classify_output_sink(requested, *, protected_roots, protected_files) -> tuple:
    """Validate a requested result destination BEFORE any byte is written.

    Returns `(resolved_path_or_None, failure_or_None)`.

    Layer 1 is purely lexical and performs ZERO filesystem access, so a
    request aimed at the deployed-state root is refused without the probe
    ever touching deployed state. Layer 2 link-resolves the request through
    its nearest existing parent and re-checks containment/alias, which is
    what defeats a junction or symlink parent that traverses INTO a protected
    root. Protected roots/files are compared in their frozen lexical form
    plus whatever already-resolved forms the caller supplies, so this
    function never has to resolve a protected path of its own accord --
    deliberately, because resolving `C:\\b1\\kals\\arb_state` would itself be
    a deployed-state filesystem touch this tool must be able to avoid.

    Precondition: protected roots/files are supplied in canonical resolved
    form. The frozen production constants satisfy this by construction, and
    `run()` additionally supplies the already-resolved repo/authority/ledger
    paths it computed for the source-binding gate. A caller that supplies a
    non-canonical root spelling (for example a Windows 8.3 short path) gets
    lexical protection for that root but not link-resolved protection.
    """
    if requested is None or requested == "":
        return None, "MISSING_REQUIRED_FIELD:output_sink.requested_output_path"

    roots = [normalize_for_compare(r) for r in protected_roots if r]
    files = [normalize_for_compare(f) for f in protected_files if f]

    try:
        lexical = normalize_for_compare(requested)
    except (OSError, ValueError) as exc:
        return None, f"UNSAFE_OUTPUT_SINK:UNRESOLVABLE:{type(exc).__name__}"

    for root, original in zip(roots, [r for r in protected_roots if r]):
        if is_within_root(lexical, root):
            return None, f"UNSAFE_OUTPUT_SINK:PROTECTED_ROOT:{original}"
    for target, original in zip(files, [f for f in protected_files if f]):
        if lexical == target:
            return None, f"UNSAFE_OUTPUT_SINK:PROTECTED_FILE_ALIAS:{original}"

    resolved = resolve_through_existing_parent(requested)
    if resolved is None:
        return None, "UNSAFE_OUTPUT_SINK:PARENT_UNRESOLVABLE"
    resolved_norm = normalize_for_compare(resolved)
    for root, original in zip(roots, [r for r in protected_roots if r]):
        if is_within_root(resolved_norm, root):
            return None, f"UNSAFE_OUTPUT_SINK:PROTECTED_ROOT_VIA_LINK:{original}"
    for target, original in zip(files, [f for f in protected_files if f]):
        if resolved_norm == target:
            return None, f"UNSAFE_OUTPUT_SINK:PROTECTED_FILE_ALIAS_VIA_LINK:{original}"
    return resolved, None


# --- CORRECTION_03 defect F: atomic exclusive result creation --------------
# Stable classifications for a result file that could not be created safely.
OUTPUT_PATH_ALREADY_EXISTS = "OUTPUT_PATH_ALREADY_EXISTS"
OUTPUT_EXCLUSIVE_CREATE_FAILED = "OUTPUT_EXCLUSIVE_CREATE_FAILED"
OUTPUT_WRITE_FAILED = "OUTPUT_WRITE_FAILED"

# Bytes the nonproduction race hook places at the destination. Fixed and
# distinctive so a test can prove the racing object survived byte-for-byte.
FIXTURE_RACE_OBJECT_BYTES = b"NONPRODUCTION_FIXTURE_RACE_OBJECT_CREATED_AFTER_SINK_VALIDATION\n"


def create_result_file_exclusive(path: str, payload: str) -> str | None:
    """Create the result file at `path` if and only if NO object occupies
    that pathname, then write `payload` into the file just created.

    Returns None on success, or a stable failure classification.

    This is a single atomic create-if-absent operation: mode "x" maps to
    O_CREAT|O_EXCL (CreateFile CREATE_NEW on Windows), so the existence test
    and the creation are one kernel operation with no window between them.
    It deliberately does NOT ask "does the path exist?" and then open for
    writing: that sequence is exactly the validation-to-write race this
    correction closes.

    Consequences, all without any object ever being opened for writing:
      - an ordinary pre-existing file is refused;
      - an NTFS hard link is refused, whichever file object it shares -- path
        normalization and link resolution cannot reveal that a directory
        entry aliases the authority store, ledger store, or Candidate-02
        artifact, but it is still an existing entry, so creation fails;
      - an object a racing process created after `classify_output_sink`
        accepted the path is refused.
    An existing object is never truncated, replaced, renamed, unlinked, or
    re-created, and there is no retry.

    The text-mode newline convention is unchanged from the predecessors'
    `Path.write_text(payload, encoding="utf-8")`, so a successful result file
    carries the same bytes it did before this correction.
    """
    try:
        handle = open(path, "x", encoding="utf-8")
    except FileExistsError:
        return OUTPUT_PATH_ALREADY_EXISTS
    except OSError as exc:
        return f"{OUTPUT_EXCLUSIVE_CREATE_FAILED}:{type(exc).__name__}"
    # From here on the file is one this run has just created, never a
    # pre-existing object, so a write failure cannot damage anything else.
    try:
        with handle:
            handle.write(payload)
    except OSError as exc:
        return f"{OUTPUT_WRITE_FAILED}:{type(exc).__name__}"
    return None


def _fixture_occupy_output_after_validation(path: str) -> str | None:
    """Nonproduction fixture seam for the C03-T03 race regression.

    Runs strictly AFTER `classify_output_sink` has accepted `path` and
    immediately BEFORE `create_result_file_exclusive`, and places an object at
    the destination exactly as a racing process would. It is unreachable
    outside `--nonproduction-fixture-mode`, touches only the already-validated
    safe destination, and cannot affect production PASS (a fixture run can
    never return EXIT_PRODUCTION_PASS). The hook itself uses exclusive
    creation too, so it can never overwrite anything either."""
    try:
        with open(path, "xb") as handle:
            handle.write(FIXTURE_RACE_OBJECT_BYTES)
    except OSError as exc:
        return f"FIXTURE_RACE_HOOK_FAILED:{type(exc).__name__}"
    return None


# --- CORRECTION_02 defect D: final mandatory observation validator --------
# Every observation OBSERVATION_CONTRACT_V2.md marks mandatory, expressed as
# dotted result paths so the validator is a single machine-checkable list
# rather than scattered ad hoc checks. NON_NULL entries must exist AND carry
# a non-null value (an explicit contract sentinel counts as a value). PRESENT
# entries must exist but may legitimately be null/empty as an observed value
# (an absent active session ID is a real observation, not a gap).
MANDATORY_NON_NULL_OBSERVATIONS = (
    "observation_timestamp_utc",
    "canonical_main_commit",
    "canonical_main_tree",
    "identity.authority_namespace_id",
    "identity.authority_instance_id",
    "identity.authority_schema_revision",
    "identity.authority_path",
    "identity.authority_store_path_identity_sha256",
    "identity.ledger_instance_id",
    "identity.ledger_schema_revision",
    "identity.ledger_path",
    "identity.ledger_path_identity_sha256",
    "identity.conflict_domain_ref",
    "tail.authority_ledger_relation",
    "tail.authority_trusted_sequence",
    "tail.authority_trusted_event_hash",
    "tail.ledger_terminal_sequence",
    "tail.ledger_terminal_event_hash",
    "domain.execution_domain_binding_id",
    "domain.execution_domain_binding_sha256",
    "domain.bootstrap_contract_sha256",
    "domain.active_contract_id",
    "domain.active_contract_sha256",
    "domain.incident_id",
    "domain.writer_proof_id",
    "domain.conflict_domain_ref",
    "risk_writer.risk_control_state",
    "risk_writer.risk_state_epoch",
    "risk_writer.writer_proof_state",
    "risk_writer.writer_proof_release_eligible",
    "risk_writer.normal_writer_eligible",
    "unresolved.unresolved_write_count",
    "unresolved.unresolved_cancel_count",
    "unresolved.fill_conflict_count",
    "local_projection.local_trusted_working_order_count",
    "local_projection.trusted_filled_exposure",
    "local_projection.retained_position_evidence",
    "durable_fill.expected_fill_id",
    "durable_fill.expected_fill_present_count",
    "durable_fill.expected_fill_present_and_exact",
    "candidate02.raw_bytes",
    "candidate02.raw_sha256",
    "candidate02.semantic_sha256",
    "candidate02.reconciliation_read_deadline_ms",
    "candidate02.create_max_sends",
    "candidate02.modify_replace_max_sends",
    "candidate02.ordinary_cancel_max_sends",
    "candidate02.automated_execution_max_sends",
    "activity.network_activity",
    "activity.credential_activity",
    "activity.kalshi_access",
    "activity.venue_writes",
    "activity.repository_writes",
    "activity.persistent_state_writes",
    "activity.restricted_session_append",
    "activity.risk_config_consumption",
    "activity.writer_release",
    "activity.production",
    "mutation_proof.authority_before",
    "mutation_proof.authority_after",
    "mutation_proof.ledger_before",
    "mutation_proof.ledger_after",
    "mutation_proof.authority_unchanged",
    "mutation_proof.ledger_unchanged",
    "source_binding.expected_repo_path",
    "source_binding.expected_authority_source_path",
    "source_binding.expected_ledger_source_path",
    "source_binding.resolved_repo_path",
    "source_binding.resolved_authority_source_path",
    "source_binding.resolved_ledger_source_path",
    "source_binding.repo_source_bound",
    "source_binding.authority_source_bound",
    "source_binding.ledger_source_bound",
    "output_sink.requested_output_path",
    "output_sink.resolved_output_path",
    "output_sink.output_sink_safe",
    "output_sink.output_written",
    "mode.observation_mode",
    "mode.production_pass_eligible",
)
MANDATORY_PRESENT_OBSERVATIONS = (
    "schema",
    "task_id",
    "sessions.active_writer_session_id",
    "sessions.active_restricted_session_id",
    "sessions.abnormal_writer_session_ids",
    "sessions.abnormal_restricted_session_ids",
    "unresolved.unresolved_write_request_ids",
    "unresolved.unresolved_cancel_attempt_ids",
    "unresolved.fill_conflicts",
    "local_projection.local_trusted_working_order_ids",
    "local_projection.release_universe_conflict_ids",
    "durable_fill.durable_fill_ids",
    "durable_fill.matching_event_ids",
    "durable_fill.matched_fields",
    "mode.nonproduction_fixture_marker",
    "mode.fixture_overrides",
)


def lookup_observation(result: dict, dotted: str) -> tuple:
    """Return `(present, value)` for a dotted result path."""
    node = result
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return (False, None)
        node = node[part]
    return (True, node)


def validate_mandatory_observations(result: dict) -> list[str]:
    """Final machine-checkable completeness validator (CORRECTION_02 defect
    D / C02-T09). Individually removing or nulling ANY mandatory observation
    from an otherwise complete result yields a stable
    `MISSING_REQUIRED_FIELD:<dotted.path>` here, which blocks terminal PASS.
    Presence in a happy-path result is not, by itself, proof of this
    theorem -- the regression suite removes/nulls each field and asserts this
    function reports it."""
    failures: list[str] = []
    for dotted in MANDATORY_PRESENT_OBSERVATIONS:
        present, _ = lookup_observation(result, dotted)
        if not present:
            failures.append(f"MISSING_REQUIRED_FIELD:{dotted}")
    for dotted in MANDATORY_NON_NULL_OBSERVATIONS:
        present, value = lookup_observation(result, dotted)
        if not present or value is None:
            failures.append(f"MISSING_REQUIRED_FIELD:{dotted}")
    return failures


def check_frozen_production_identity(observed: dict, expected: dict | None = None) -> list[str]:
    """Pure identity gate: compares each observed value against the frozen
    accepted N1 identity. A field the caller could not observe at all (None)
    is skipped here -- that gap is already recorded by
    `validate_mandatory_observations` as a MISSING_REQUIRED_FIELD, and
    re-flagging it here would only produce a confusing duplicate. A field
    that WAS observed but does not equal the frozen expected value is always
    reported, distinctly, as a production identity mismatch."""
    expected_identity = FROZEN_PRODUCTION_IDENTITY if expected is None else expected
    failures = []
    for key, expected_value in expected_identity.items():
        value = observed.get(key)
        if value is None:
            continue
        if value != expected_value:
            failures.append(f"PRODUCTION_IDENTITY_MISMATCH:{key}")
    return failures


def check_candidate02_contract_values(observed) -> list[str]:
    """Pure gate for the Candidate-02 values the V2 observation contract
    fixes (`reconciliation_read_deadline_ms = 30000`, and all four normal
    send maxima = 0). Applied for a production observation only: under the
    nonproduction fixture seam the candidate is synthetic by definition, so
    these are reported but not gated there."""
    if not isinstance(observed, dict):
        return []
    failures = []
    for key, expected in CANDIDATE02_CONTRACT_VALUES.items():
        value = observed.get(key)
        if value is None:
            continue
        if value != expected:
            failures.append(f"CANDIDATE02_CONTRACT_VALUE_MISMATCH:{key}")
    return failures


def check_unresolved_gate(*, unresolved_write_ids, unresolved_cancel_ids, fill_conflicts) -> list[str]:
    """Pure completeness gate for unresolved-write/cancel/fill-conflict
    presence (T11/T12/T13), isolated so it is directly unit-testable with
    synthetic tuples independent of constructing a full write/emergency-
    cancel event stream (see STATIC_CONFORMANCE_MATRIX.md for why a fully
    legitimate unresolved-write/cancel ledger fixture is out of this bounded
    read-only correction's scope)."""
    failures = []
    if unresolved_write_ids:
        failures.append("UNRESOLVED_WRITE_PRESENT")
    if unresolved_cancel_ids:
        failures.append("UNRESOLVED_CANCEL_PRESENT")
    if fill_conflicts:
        failures.append("FILL_CONFLICT_PRESENT")
    return failures


def file_proof(path: Path) -> dict:
    item = path.stat()
    return {
        "bytes": item.st_size,
        "mtime_utc": dt.datetime.fromtimestamp(item.st_mtime, dt.timezone.utc).isoformat(timespec="microseconds"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def ro_connect(path: Path) -> sqlite3.Connection:
    """True SQLite mode=ro connection. Deliberately leaves row_factory at the
    default (plain tuples): the reused canonical arb.execution_ledger
    validation helpers compare PRAGMA results against tuple literals, and a
    sqlite3.Row never compares equal to a plain tuple even with identical
    values."""
    uri = path.resolve(strict=True).as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


# --- CORRECTION_01 defect 2 (preserved): complete envelope before any
# --- fallible op ----------------------------------------------------------

def _empty_result_skeleton(*, fill_id: str, canonical_main_commit, canonical_main_tree,
                            observation_timestamp_utc: str, observation_mode: str,
                            fixture_overrides: list, expectations: dict,
                            requested_output_path) -> dict:
    """Every mandatory OBSERVATION_CONTRACT_V2 top-level group/key, populated
    with an explicit non-observed representation. Built BEFORE any fallible
    file/SQLite operation so every failure path returns this same complete
    shape with whatever was actually learned filled in, rather than a
    reduced ad hoc object."""
    production = observation_mode == OBSERVATION_MODE_PRODUCTION
    return {
        "schema": RESULT_SCHEMA,
        "task_id": "R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2",
        "observation_timestamp_utc": observation_timestamp_utc,
        "canonical_main_commit": canonical_main_commit,
        "canonical_main_tree": canonical_main_tree,
        "mode": {
            "observation_mode": observation_mode,
            "production_pass_eligible": production,
            "nonproduction_fixture_marker": None if production else NONPRODUCTION_FIXTURE_MARKER,
            "fixture_overrides": list(fixture_overrides),
        },
        "identity": {
            "authority_namespace_id": None, "authority_instance_id": None,
            "authority_schema_revision": None, "authority_path": None,
            "authority_store_path_identity_sha256": None,
            "ledger_instance_id": None, "ledger_schema_revision": None,
            "ledger_path": None, "ledger_path_identity_sha256": None,
            "conflict_domain_ref": None,
        },
        "source_binding": {
            "expected_repo_path": expectations["repo"],
            "expected_authority_source_path": expectations["authority"],
            "expected_ledger_source_path": expectations["ledger"],
            "resolved_repo_path": None,
            "resolved_authority_source_path": None,
            "resolved_ledger_source_path": None,
            "repo_source_bound": None,
            "authority_source_bound": None,
            "ledger_source_bound": None,
        },
        "output_sink": {
            "requested_output_path": requested_output_path,
            "resolved_output_path": None,
            "output_sink_safe": None,
            "output_written": False,
        },
        "tail": {
            "authority_ledger_relation": None,
            "authority_trusted_sequence": None, "authority_trusted_event_hash": None,
            "ledger_terminal_sequence": None, "ledger_terminal_event_hash": None,
        },
        "domain": {
            "execution_domain_binding_id": None, "execution_domain_binding_sha256": None,
            "bootstrap_contract_sha256": None, "active_contract_id": None,
            "active_contract_sha256": None, "incident_id": None, "writer_proof_id": None,
            "conflict_domain_ref": None,
        },
        "risk_writer": {
            "risk_control_state": None, "risk_state_epoch": None,
            "writer_proof_state": None, "writer_proof_release_eligible": None,
            "normal_writer_eligible": SENTINEL_NOT_EXPOSED,
        },
        "sessions": {
            "active_writer_session_id": None, "active_restricted_session_id": None,
            "abnormal_writer_session_ids": [], "abnormal_restricted_session_ids": [],
        },
        "unresolved": {
            "unresolved_write_request_ids": [], "unresolved_write_count": None,
            "unresolved_cancel_attempt_ids": [], "unresolved_cancel_count": None,
            "fill_conflicts": [], "fill_conflict_count": None,
        },
        "local_projection": {
            "local_trusted_working_order_count": None, "local_trusted_working_order_ids": [],
            "trusted_filled_exposure": SENTINEL_NOT_EXPOSED,
            "retained_position_evidence": SENTINEL_NOT_EXPOSED,
            "release_universe_conflict_ids": [],
        },
        "durable_fill": {
            "durable_fill_ids": [], "expected_fill_id": fill_id,
            "expected_fill_present_count": 0, "expected_fill_present_and_exact": False,
            "matching_event_ids": [], "matched_fields": {},
        },
        "candidate02": None,
        "activity": {
            "network_activity": "NONE", "credential_activity": "NONE", "kalshi_access": "NONE",
            "venue_writes": "NONE", "repository_writes": "NONE", "persistent_state_writes": "NONE",
            "restricted_session_append": "NONE", "risk_config_consumption": "NONE",
            "writer_release": "NONE", "production": "NONE",
        },
        "mutation_proof": {
            "authority_before": None, "authority_after": None,
            "ledger_before": None, "ledger_after": None,
            "authority_unchanged": None, "ledger_unchanged": None,
        },
    }


def _el_derive_release_universe(projection, events) -> dict:
    """Pure re-derivation mirroring ledger_binding._derive_authoritative_
    release_universe's working-order/fill-event selection, expressed over
    plain event/projection data so it does not require a live LockedLedger
    with real DB connections. Read-only: only iterates already-loaded,
    already hash-chain-validated events; issues no queries of its own."""
    latest_orders: dict[str, object] = {}
    fill_events: dict[str, list] = {}
    conflicts: set[str] = set(projection.fill_conflicts)
    for event in events:
        if event.event_type.value == "ORDER_OBSERVED":
            order_id = event.payload.get("venue_order_id")
            content = event.payload.get("canonical_venue_payload")
            if not isinstance(order_id, str) or not order_id or not isinstance(content, dict):
                conflicts.add(f"order-event:{event.event_id}")
                continue
            latest_orders[order_id] = event
        elif event.event_type.value == "FILL_OBSERVED":
            fill_id = event.payload.get("venue_fill_id")
            content = event.payload.get("canonical_venue_payload")
            if not isinstance(fill_id, str) or not fill_id or not isinstance(content, dict):
                conflicts.add(f"fill-event:{event.event_id}")
                continue
            fill_events.setdefault(fill_id, []).append(event)
    if set(latest_orders) != set(projection.order_observation_history):
        conflicts.add("order-replay-universe")
    if set(fill_events) != set(projection.canonical_fills_by_fill_id):
        conflicts.add("fill-replay-universe")

    working_orders = []
    for order_id, event in sorted(latest_orders.items()):
        content = event.payload.get("canonical_venue_payload")
        if not isinstance(content, dict):
            conflicts.add(f"order-content:{order_id}")
            continue
        if content.get("status") == "resting":
            working_orders.append({
                "order_id": order_id,
                "market": content.get("market"),
                "outcome_side": content.get("outcome_side"),
            })

    fill_event_ids: dict[str, tuple] = {}
    for fill_id, canonical in sorted(projection.canonical_fills_by_fill_id.items()):
        candidates = fill_events.get(fill_id, [])
        matching = tuple(
            event for event in candidates
            if event.payload.get("canonical_venue_payload") == canonical
        )
        fill_event_ids[fill_id] = tuple(event.event_id for event in matching)
        if not matching:
            conflicts.add(f"fill-content:{fill_id}")

    return {
        "working_orders": working_orders,
        "conflict_ids": sorted(conflicts),
        "fill_event_ids": fill_event_ids,
    }


def _finalize_mutation_proof(*, stores: dict, proof_before: dict, result: dict,
                              completeness_failures: list) -> None:
    """CORRECTION_02 defect C. For every store whose pre-proof succeeded,
    attempt the post-proof and compare. Invoked from a `finally` after the
    SQLite connections are closed, so it runs on successful runs AND on
    readable runs that failed a schema/integrity/domain/replay/candidate
    check. A store with no successful pre-proof keeps explicit nulls -- a
    missing file cannot have a before/after proof and must stay classified
    rather than fabricated. A post-proof that cannot itself be obtained is
    classified and fails closed."""
    proof = result["mutation_proof"]
    for label, path in stores.items():
        before = proof_before.get(label)
        proof[f"{label}_before"] = before
        if before is None:
            proof[f"{label}_after"] = None
            proof[f"{label}_unchanged"] = None
            continue
        try:
            after = file_proof(path)
        except OSError as exc:
            proof[f"{label}_after"] = None
            proof[f"{label}_unchanged"] = False
            completeness_failures.append(f"POST_READ_PROOF_UNOBTAINABLE:{label}:{type(exc).__name__}")
            continue
        proof[f"{label}_after"] = after
        unchanged = before == after
        proof[f"{label}_unchanged"] = unchanged
        if not unchanged:
            completeness_failures.append(f"{label.upper()}_MUTATED_DURING_READ")


def _read_local_state(*, repo: str, authority_path: str, ledger_path: str, conflict_domain: str,
                       fill_id: str, result: dict, completeness_failures: list) -> None:
    """Populate `result`'s identity/tail/domain/risk_writer/sessions/
    unresolved/local_projection/durable_fill/mutation_proof groups from the
    live SQLite stores. Every fallible step is individually classified; a
    failure at any point leaves the remaining groups at their skeleton
    defaults (still present, still None/empty) rather than raising past this
    function uncaught.

    The whole read phase runs inside `_phase()` so that every early return it
    makes still passes through this function's `finally`, which closes the
    connections and then finalizes the before/after mutation proof
    (CORRECTION_02 defect C). No branch can bypass that step."""
    import arb.execution_ledger as _el
    from arb.venues.kalshi import ledger_binding as _lb

    authority_file = Path(authority_path)
    ledger_file = Path(ledger_path)
    proof_before: dict = {}
    connections: dict = {}

    def _phase() -> None:
        try:
            proof_before["authority"] = file_proof(authority_file)
        except OSError as exc:
            completeness_failures.append(f"AUTHORITY_STORE_UNREADABLE:{type(exc).__name__}")
        try:
            proof_before["ledger"] = file_proof(ledger_file)
        except OSError as exc:
            completeness_failures.append(f"LEDGER_STORE_UNREADABLE:{type(exc).__name__}")
        if "authority" not in proof_before or "ledger" not in proof_before:
            return

        try:
            connections["authority"] = ro_connect(authority_file)
        except (OSError, sqlite3.Error) as exc:
            completeness_failures.append(f"AUTHORITY_STORE_OPEN_FAILED:{type(exc).__name__}")
            return
        try:
            connections["ledger"] = ro_connect(ledger_file)
        except (OSError, sqlite3.Error) as exc:
            completeness_failures.append(f"LEDGER_STORE_OPEN_FAILED:{type(exc).__name__}")
            return
        authority_con = connections["authority"]
        ledger_con = connections["ledger"]

        try:
            _el._validate_schema(authority_con, authority=True)
            _el._validate_integrity(authority_con, authority=True)
            authority_meta = _el._authority_meta(authority_con)
            authority_row = _el._authority_row(authority_con, conflict_domain)
        except (_el.LedgerError, sqlite3.Error) as exc:
            code = exc.code.value if isinstance(exc, _el.LedgerError) else type(exc).__name__
            completeness_failures.append(f"AUTHORITY_SCHEMA_OR_INTEGRITY_FAILED:{code}")
            return

        try:
            _el._validate_schema(ledger_con, authority=False, ledger_revision=_el.ACTIVE_LEDGER_SCHEMA_REVISION)
            _el._validate_integrity(ledger_con, authority=False)
            ledger_meta = _el._active_ledger_meta(ledger_con)
            events = _el.load_and_validate_events(ledger_con, ledger_meta)
        except (_el.LedgerError, sqlite3.Error) as exc:
            code = exc.code.value if isinstance(exc, _el.LedgerError) else type(exc).__name__
            completeness_failures.append(f"LEDGER_SCHEMA_OR_INTEGRITY_FAILED:{code}")
            return

        tail = events[-1]
        locked = _el.LockedLedger(
            binding=None, conflict_domain_ref=conflict_domain,
            authority=None, ledger=None,
            authority_meta=authority_meta, authority_row=authority_row, ledger_meta=ledger_meta,
            events=events, relation=_el.AuthorityLedgerRelation.EQUAL,
            clock=None, uuid_factory=None, fault_hook=None,
        )
        projection = locked.projection()

        if (authority_row.trusted_sequence, authority_row.trusted_event_hash) == (tail.sequence, tail.event_hash):
            relation = "AUTHORITY_EQUAL_TO_LEDGER"
        elif authority_row.trusted_sequence < tail.sequence:
            relation = "LEDGER_AHEAD_OF_AUTHORITY"
            completeness_failures.append("AUTHORITY_LEDGER_RELATION_NOT_EQUAL")
        else:
            relation = "AUTHORITY_AHEAD_OF_LEDGER_ANOMALY"
            completeness_failures.append("AUTHORITY_LEDGER_RELATION_NOT_EQUAL")

        result["identity"] = {
            "authority_namespace_id": projection.authority_namespace_id,
            "authority_instance_id": projection.authority_instance_id,
            "authority_schema_revision": projection.authority_schema_revision,
            "authority_path": authority_meta.authority_store_resolved_path,
            "authority_store_path_identity_sha256": projection.authority_store_path_identity_sha256,
            "ledger_instance_id": projection.ledger_instance_id,
            "ledger_schema_revision": projection.ledger_schema_revision,
            "ledger_path": authority_row.ledger_resolved_path,
            "ledger_path_identity_sha256": projection.ledger_path_identity_sha256,
            "conflict_domain_ref": projection.conflict_domain_ref,
        }
        result["tail"] = {
            "authority_ledger_relation": relation,
            "authority_trusted_sequence": authority_row.trusted_sequence,
            "authority_trusted_event_hash": authority_row.trusted_event_hash,
            "ledger_terminal_sequence": tail.sequence,
            "ledger_terminal_event_hash": tail.event_hash,
        }

        # -- domain identities ----------------------------------------------
        bootstrap_events = [e for e in events if e.event_type is _el.EventType.EXECUTION_DOMAIN_BOOTSTRAP_RECORDED]
        if len(bootstrap_events) != 1:
            completeness_failures.append("BOOTSTRAP_EVENT_COUNT_NOT_ONE")
            bootstrap_contract_sha256 = None
        else:
            bootstrap_contract_sha256 = bootstrap_events[0].payload.get("bootstrap_contract_sha256")
            if not isinstance(bootstrap_contract_sha256, str):
                completeness_failures.append("BOOTSTRAP_CONTRACT_SHA256_NOT_EXPOSED")
                bootstrap_contract_sha256 = None

        active_contract_id = active_contract_sha256 = incident_id = writer_proof_id = None
        try:
            binding_json = json.loads(ledger_meta.execution_domain_binding_json)
            rebuilt_binding = _lb.ExecutionDomainBindingV1(
                venue=binding_json["venue"], environment=binding_json["environment"],
                account_scope_ref=binding_json["account_scope_ref"],
                subaccount=binding_json["subaccount"], exchange_index=binding_json["exchange_index"],
            )
            if bootstrap_contract_sha256 is not None:
                active_contract = _lb.ActiveExecutionDomainContractV1(
                    binding=rebuilt_binding, bootstrap_contract_sha256=bootstrap_contract_sha256,
                )
                active_contract_id = active_contract.contract_id
                active_contract_sha256 = active_contract.contract_sha256
                incident_id = active_contract.incident_id
                writer_proof_id = active_contract.writer_proof_id
        except (_el.LedgerError, KeyError, TypeError, ValueError) as exc:
            completeness_failures.append(f"ACTIVE_CONTRACT_DERIVATION_FAILED:{type(exc).__name__}")

        result["domain"] = {
            "execution_domain_binding_id": ledger_meta.execution_domain_binding_id,
            "execution_domain_binding_sha256": ledger_meta.execution_domain_binding_sha256,
            "bootstrap_contract_sha256": bootstrap_contract_sha256,
            "active_contract_id": active_contract_id,
            "active_contract_sha256": active_contract_sha256,
            "incident_id": incident_id,
            "writer_proof_id": writer_proof_id,
            "conflict_domain_ref": projection.conflict_domain_ref,
        }

        # -- risk / writer state -------------------------------------------------
        writer_proof_states = dict(projection.writer_proof_state_by_proof_id)
        writer_proof_release = dict(projection.writer_proof_release_eligible_by_proof_id)
        this_proof_state = writer_proof_states.get(writer_proof_id) if writer_proof_id else None
        this_proof_release = writer_proof_release.get(writer_proof_id) if writer_proof_id else None
        result["risk_writer"] = {
            "risk_control_state": projection.risk_control_state,
            "risk_state_epoch": projection.risk_state_epoch,
            "writer_proof_state": this_proof_state,
            "writer_proof_release_eligible": this_proof_release,
            "normal_writer_eligible": SENTINEL_NOT_EXPOSED,
        }
        if projection.risk_control_state not in _el.RISK_CONTROL_STATES:
            completeness_failures.append("INVALID_OBSERVATION:risk_writer.risk_control_state")

        # -- sessions ---------------------------------------------------------------
        result["sessions"] = {
            "active_writer_session_id": projection.active_writer_session_id,
            "active_restricted_session_id": projection.active_restricted_session_id,
            "abnormal_writer_session_ids": list(projection.abnormal_prior_session_ids),
            "abnormal_restricted_session_ids": list(projection.abnormal_restricted_session_ids),
        }

        # -- unresolved / conflicts ------------------------------------------------
        unresolved_write_ids = list(projection.unresolved_write_request_ids)
        unresolved_cancel_ids = sorted(
            attempt_id for attempt_id, may_have_sent in projection.cancel_send_may_have_been_sent_by_attempt.items()
            if may_have_sent
        )
        fill_conflicts = list(projection.fill_conflicts)
        result["unresolved"] = {
            "unresolved_write_request_ids": unresolved_write_ids,
            "unresolved_write_count": len(unresolved_write_ids),
            "unresolved_cancel_attempt_ids": unresolved_cancel_ids,
            "unresolved_cancel_count": len(unresolved_cancel_ids),
            "fill_conflicts": fill_conflicts,
            "fill_conflict_count": len(fill_conflicts),
        }
        completeness_failures.extend(check_unresolved_gate(
            unresolved_write_ids=unresolved_write_ids,
            unresolved_cancel_ids=unresolved_cancel_ids,
            fill_conflicts=fill_conflicts,
        ))

        # -- local order / exposure projection (also yields fill event ids) --------
        universe = _el_derive_release_universe(projection, events)
        result["local_projection"] = {
            "local_trusted_working_order_count": len(universe["working_orders"]),
            "local_trusted_working_order_ids": [o["order_id"] for o in universe["working_orders"]],
            "trusted_filled_exposure": SENTINEL_NOT_EXPOSED,
            "retained_position_evidence": SENTINEL_NOT_EXPOSED,
            "release_universe_conflict_ids": universe["conflict_ids"],
        }
        if universe["conflict_ids"]:
            completeness_failures.append("RELEASE_UNIVERSE_CONFLICT_PRESENT")

        # -- durable prestack fill ----------------------------------------------------
        durable_fills = dict(projection.canonical_fills_by_fill_id)
        durable_fill_ids = list(durable_fills.keys())
        expected_present = fill_id in durable_fills
        expected_exact = False
        matched_fields: dict = {}
        if expected_present:
            canonical = durable_fills[fill_id]
            raw_fields = {
                "ticker": canonical.get("market"),
                "outcome_side": canonical.get("outcome_side"),
                "quantity": canonical.get("quantity"),
                "yes_price": canonical.get("price"),
                "fee": canonical.get("fee"),
                "authoritative_created_time_utc": canonical.get("authoritative_created_time_utc"),
            }
            matched_fields = dict(raw_fields)
            for field in ("quantity", "yes_price", "fee"):
                unwrapped = _lb.ReleaseLedgerHandle._stored_decimal_value(raw_fields[field])
                matched_fields[field] = str(unwrapped) if unwrapped is not None else None
            str_exact = all(raw_fields.get(k) == v for k, v in EXPECTED_FILL_STR_FIELDS.items())
            decimal_exact = all(
                _lb.ReleaseLedgerHandle._stored_decimal_matches(raw_fields.get(field), expected)
                for field, expected in EXPECTED_FILL_DECIMAL_FIELDS.items()
            )
            expected_exact = str_exact and decimal_exact
        result["durable_fill"] = {
            "durable_fill_ids": durable_fill_ids,
            "expected_fill_id": fill_id,
            "expected_fill_present_count": 1 if expected_present else 0,
            "expected_fill_present_and_exact": bool(expected_present and expected_exact),
            "matching_event_ids": list(universe["fill_event_ids"].get(fill_id, ())),
            "matched_fields": matched_fields,
        }
        if not (expected_present and expected_exact):
            completeness_failures.append("EXPECTED_DURABLE_FILL_THEOREM_FAILED")

    try:
        _phase()
    finally:
        for con in connections.values():
            try:
                con.close()
            except sqlite3.Error:
                pass
        _finalize_mutation_proof(
            stores={"authority": authority_file, "ledger": ledger_file},
            proof_before=proof_before, result=result,
            completeness_failures=completeness_failures,
        )


def _dedupe(items: list) -> list:
    """Stable de-duplication so a condition classified by two independent
    gates is reported once."""
    seen = set()
    ordered = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _null_observation(result: dict, dotted: str) -> bool:
    """Nonproduction fixture seam used by the C02-T09 regression to prove the
    mandatory-observation validator is genuinely load-bearing end to end:
    null one observation in an otherwise complete result and confirm the
    launcher itself fails closed. Unreachable outside fixture mode."""
    parts = dotted.split(".")
    node = result
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    if not isinstance(node, dict) or parts[-1] not in node:
        return False
    node[parts[-1]] = None
    return True


def run(*, candidate02_path: str, output_path: str | None,
        canonical_main_commit: str | None = None, canonical_main_tree: str | None = None,
        fixture: dict | None = None, refusal: str | None = None) -> tuple:
    """Single canonical observation. Returns `(result, exit_code)`.

    `fixture` is None for a production observation. When supplied it is the
    explicitly nonproduction seam: it may substitute sources, conflict
    domain, expected fill ID, expected Candidate-02 identities, and the
    expected N1 identity set, but the result is marked
    NONPRODUCTION_TEST_FIXTURE and can never return EXIT_PRODUCTION_PASS.
    """
    production = fixture is None
    expectations = production_expectations()
    fixture_overrides: list[str] = []
    if not production:
        for key in ("repo", "authority", "ledger", "conflict_domain", "fill_id",
                    "candidate_raw_sha256", "candidate_semantic_sha256", "identity"):
            value = fixture.get(key)
            if value:
                expectations[key] = value
                fixture_overrides.append(key)
        if fixture.get("null_observations"):
            fixture_overrides.append("null_observations")
        if fixture.get("race_occupy_output_before_create"):
            fixture_overrides.append("race_occupy_output_before_create")
        fixture_overrides.sort()

    observation_timestamp_utc = (
        dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
    if output_path is None:
        output_path = str(
            Path(tempfile.gettempdir())
            / f"R1-D07_N1_FRESH_READ_ONLY_STATE_REVALIDATION_V2_RESULT_{uuid.uuid4().hex}.json"
        )

    result = _empty_result_skeleton(
        fill_id=expectations["fill_id"], canonical_main_commit=canonical_main_commit,
        canonical_main_tree=canonical_main_tree, observation_timestamp_utc=observation_timestamp_utc,
        observation_mode=OBSERVATION_MODE_PRODUCTION if production else OBSERVATION_MODE_FIXTURE,
        fixture_overrides=fixture_overrides, expectations=expectations,
        requested_output_path=output_path,
    )
    completeness_failures: list[str] = []
    if refusal:
        completeness_failures.append(refusal)
    if not canonical_main_commit:
        completeness_failures.append("MISSING_REQUIRED_FIELD:canonical_main_commit")
    if not canonical_main_tree:
        completeness_failures.append("MISSING_REQUIRED_FIELD:canonical_main_tree")

    # -- CORRECTION_02 defect A: bind to the ACTUAL resolved sources --------
    # Resolved before the state read so the binding theorem is reported even
    # when the read itself fails, and so the sink guard can treat the actual
    # store files as protected aliases.
    #
    # CORRECTION_03: a refused invocation performs no state read, so it must
    # not resolve the sources either. On Windows `Path.resolve()` opens a
    # (zero-access) handle to an existing path, and for a production-mode
    # refusal those paths are the frozen deployed N1 stores. Skipping resolution
    # leaves the source-binding observations null, which the mandatory
    # validator already reports -- the refusal still fails closed.
    resolved_repo = resolved_authority = resolved_ledger = None
    if not refusal:
        resolved_repo = resolve_actual_path(expectations["repo"])
        resolved_authority = resolve_actual_path(expectations["authority"])
        resolved_ledger = resolve_actual_path(expectations["ledger"])
        source_failures = check_production_source_binding(
            resolved_repo=resolved_repo, resolved_authority=resolved_authority,
            resolved_ledger=resolved_ledger, expected_repo=expectations["repo"],
            expected_authority=expectations["authority"], expected_ledger=expectations["ledger"],
        )
        result["source_binding"].update({
            "resolved_repo_path": resolved_repo,
            "resolved_authority_source_path": resolved_authority,
            "resolved_ledger_source_path": resolved_ledger,
            "repo_source_bound": "PRODUCTION_SOURCE_PATH_MISMATCH:repo" not in source_failures,
            "authority_source_bound": "PRODUCTION_SOURCE_PATH_MISMATCH:authority" not in source_failures,
            "ledger_source_bound": "PRODUCTION_SOURCE_PATH_MISMATCH:ledger" not in source_failures,
        })
        completeness_failures.extend(source_failures)

    # -- CORRECTION_02 defect B: validate the sink before any write ---------
    # Protected roots/files are supplied in their frozen lexical form plus
    # the already-resolved forms this run computed above, so the guard never
    # has to resolve a deployed-state path of its own accord.
    sink_resolved, sink_failure = classify_output_sink(
        output_path,
        protected_roots=[
            FROZEN_PRODUCTION_SOURCES["repo"], resolved_repo,
            FROZEN_DEPLOYMENT_ROOT,
        ],
        protected_files=[
            FROZEN_PRODUCTION_SOURCES["authority"], FROZEN_PRODUCTION_SOURCES["ledger"],
            resolved_authority, resolved_ledger,
            candidate02_path, resolve_actual_path(candidate02_path),
            os.environ.get("ARB_R1D07_V2_LAUNCHER_PATH", ""),
        ],
    )
    result["output_sink"]["resolved_output_path"] = sink_resolved
    result["output_sink"]["output_sink_safe"] = sink_failure is None
    if sink_failure is not None:
        completeness_failures.append(sink_failure)

    if not refusal:
        # CORRECTION_01 defect 2: this outer catch is a last-resort safety
        # net. Every phase inside already classifies its own fallible
        # operations individually; the catch exists only so a truly
        # unanticipated exception still returns the complete envelope (with
        # whatever was learned before the exception) instead of an uncaught
        # traceback as the result contract.
        try:
            sys.path.insert(0, str(Path(expectations["repo"]) / "src"))
            _read_local_state(
                repo=expectations["repo"], authority_path=expectations["authority"],
                ledger_path=expectations["ledger"], conflict_domain=expectations["conflict_domain"],
                fill_id=expectations["fill_id"],
                result=result, completeness_failures=completeness_failures,
            )
        except Exception as exc:  # noqa: BLE001 - last-resort envelope guarantee
            completeness_failures.append(f"UNEXPECTED_ERROR:{type(exc).__name__}")

        # -- Candidate-02 ---------------------------------------------------
        # Attempted independently of local-state read success/failure: a
        # Candidate-02 identity result should never depend on whether the N1
        # stores themselves were readable.
        try:
            candidate_file = Path(candidate02_path)
            if not candidate_file.exists():
                completeness_failures.append("CANDIDATE02_FILE_MISSING")
                result["candidate02"] = None
            else:
                raw = candidate_file.read_bytes()
                raw_sha256 = hashlib.sha256(raw).hexdigest()
                if raw_sha256 != expectations["candidate_raw_sha256"]:
                    completeness_failures.append("CANDIDATE02_RAW_SHA256_MISMATCH")
                    result["candidate02"] = {"raw_bytes": len(raw), "raw_sha256": raw_sha256, "semantic_sha256": None}
                else:
                    from arb.venues.kalshi.minimal_market_maker_experiment_runner import _load_sha_bound_risk_config
                    try:
                        config = _load_sha_bound_risk_config(path=str(candidate_file), expected_sha256=raw_sha256)
                        semantic_ok = config.sha256 == expectations["candidate_semantic_sha256"]
                        result["candidate02"] = {
                            "raw_bytes": len(raw),
                            "raw_sha256": raw_sha256,
                            "semantic_sha256": config.sha256,
                            "reconciliation_read_deadline_ms": config.state_integrity.reconciliation_read_deadline_ms,
                            "create_max_sends": config.flow.create_max_sends,
                            "modify_replace_max_sends": config.flow.modify_replace_max_sends,
                            "ordinary_cancel_max_sends": config.flow.ordinary_cancel_max_sends,
                            "automated_execution_max_sends": config.flow.automated_execution_max_sends,
                        }
                        if not semantic_ok:
                            completeness_failures.append("CANDIDATE02_SEMANTIC_SHA256_MISMATCH")
                    except Exception as exc:  # noqa: BLE001 - fail closed on any config rejection
                        completeness_failures.append(f"CANDIDATE02_REJECTED:{type(exc).__name__}")
                        result["candidate02"] = None
        except Exception as exc:  # noqa: BLE001 - last-resort envelope guarantee
            completeness_failures.append(f"UNEXPECTED_ERROR:{type(exc).__name__}")

    # -- CORRECTION_01 defect 1 (preserved): frozen N1 identity gate --------
    observed_identity = dict(result["identity"])
    observed_identity.update(result["domain"])
    completeness_failures.extend(
        check_frozen_production_identity(observed_identity, expectations["identity"])
    )
    if production:
        completeness_failures.extend(check_candidate02_contract_values(result["candidate02"]))

    # -- nonproduction fixture null-observation seam (C02-T09) --------------
    if not production:
        for dotted in (fixture.get("null_observations") or []):
            if not _null_observation(result, dotted):
                completeness_failures.append(f"FIXTURE_NULL_OBSERVATION_PATH_UNKNOWN:{dotted}")

    # -- CORRECTION_02 defect D: final mandatory observation validator ------
    completeness_failures.extend(validate_mandatory_observations(result))

    # -- completeness gate --------------------------------------------------
    failures = _dedupe(completeness_failures)
    complete = not failures
    result["observation_completeness"] = {"complete": complete, "failures": failures}
    if complete and production:
        result["status"] = STATUS_PRODUCTION_PASS
        exit_code = EXIT_PRODUCTION_PASS
    elif complete:
        result["status"] = STATUS_FIXTURE_COMPLETE
        exit_code = EXIT_FIXTURE_COMPLETE
    else:
        result["status"] = STATUS_INCOMPLETE
        exit_code = EXIT_INCOMPLETE

    # The local report is permitted; a repository or deployed-state write is
    # not. Only a sink that passed `classify_output_sink` is ever created, and
    # (CORRECTION_03) it is created exclusively: a pathname that is already
    # occupied by ANY object -- including a hard link to a protected file that
    # the path checks above cannot see -- is never opened for writing.
    if sink_failure is None and sink_resolved is not None:
        if not production and fixture.get("race_occupy_output_before_create"):
            race_failure = _fixture_occupy_output_after_validation(sink_resolved)
            if race_failure is not None:
                failures = _dedupe(failures + [race_failure])
        # Serialized with output_written=true because the payload is only ever
        # placed into a file this run has just exclusively created; if creation
        # fails, the flag is reset below and the file never receives the bytes.
        result["output_sink"]["output_written"] = True
        payload = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
        create_failure = create_result_file_exclusive(sink_resolved, payload)
        if create_failure is not None:
            result["output_sink"]["output_written"] = False
            failures = _dedupe(failures + [create_failure])
            result["observation_completeness"] = {"complete": False, "failures": failures}
            result["status"] = STATUS_INCOMPLETE
            exit_code = EXIT_INCOMPLETE
    return result, exit_code


def _build_fixture(args) -> dict | None:
    if not args.nonproduction_fixture_mode:
        return None
    identity = None
    if args.fixture_expected_identity_path:
        identity = json.loads(Path(args.fixture_expected_identity_path).read_text(encoding="utf-8"))
    return {
        "repo": args.fixture_repo,
        "authority": args.fixture_authority,
        "ledger": args.fixture_ledger,
        "conflict_domain": args.fixture_conflict_domain,
        "fill_id": args.fixture_fill_id,
        "candidate_raw_sha256": args.fixture_expected_candidate_raw_sha256,
        "candidate_semantic_sha256": args.fixture_expected_candidate_semantic_sha256,
        "identity": identity,
        "null_observations": list(args.fixture_null_observation or ()),
        "race_occupy_output_before_create": bool(args.fixture_race_occupy_output_before_create),
    }


FIXTURE_ARGUMENT_DESTINATIONS = (
    "fixture_repo", "fixture_authority", "fixture_ledger", "fixture_conflict_domain",
    "fixture_fill_id", "fixture_expected_candidate_raw_sha256",
    "fixture_expected_candidate_semantic_sha256", "fixture_expected_identity_path",
    "fixture_null_observation", "fixture_race_occupy_output_before_create",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    # Production surface. Deliberately minimal: the repository root, both
    # store paths, the conflict domain, the expected fill ID, and both
    # Candidate-02 expected identities are frozen contract constants with no
    # production argument (CORRECTION_02 defects A and E).
    parser.add_argument("--candidate02", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--canonical-commit", default=None)
    parser.add_argument("--canonical-tree", default=None)
    # Explicitly nonproduction fixture surface. Every one of these is ignored
    # -- and its use rejected -- unless --nonproduction-fixture-mode is also
    # given, and none of them can yield EXIT_PRODUCTION_PASS.
    parser.add_argument("--nonproduction-fixture-mode", action="store_true")
    parser.add_argument("--fixture-repo", default=None)
    parser.add_argument("--fixture-authority", default=None)
    parser.add_argument("--fixture-ledger", default=None)
    parser.add_argument("--fixture-conflict-domain", default=None)
    parser.add_argument("--fixture-fill-id", default=None)
    parser.add_argument("--fixture-expected-candidate-raw-sha256", default=None)
    parser.add_argument("--fixture-expected-candidate-semantic-sha256", default=None)
    parser.add_argument("--fixture-expected-identity-path", default=None)
    parser.add_argument("--fixture-null-observation", action="append", default=None)
    parser.add_argument("--fixture-race-occupy-output-before-create", action="store_true")
    args = parser.parse_args()

    refusal = None
    if not args.nonproduction_fixture_mode:
        supplied = [dest for dest in FIXTURE_ARGUMENT_DESTINATIONS if getattr(args, dest)]
        if supplied:
            refusal = "FIXTURE_OVERRIDE_WITHOUT_FIXTURE_MODE:" + ",".join(sorted(supplied))

    result, exit_code = run(
        candidate02_path=args.candidate02, output_path=args.output,
        canonical_main_commit=args.canonical_commit, canonical_main_tree=args.canonical_tree,
        fixture=_build_fixture(args), refusal=refusal,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
'@

$PyBytes = [System.Text.Encoding]::UTF8.GetBytes($Py)

# Materialized to a private temp file rather than passed inline (e.g. via
# `python -c <base64 blob>`): the embedded source is large enough that
# inlining its encoded form on the command line can exceed the Windows
# CreateProcess command-line length budget ("the filename or extension is
# too long"). Writing it to a file the interpreter loads by path carries no
# such limit and involves no argument-quoting boundary at all for the
# source text itself. The file is private to this invocation (a fresh
# GUID-named path under the OS temp directory) and is always removed in
# `finally`; it is disposable execution material, not a repository artifact
# or persistent state.
$ProbeScriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("arb_r1d07_n1_v2_probe_" + [Guid]::NewGuid().ToString("N") + ".py")
[System.IO.File]::WriteAllBytes($ProbeScriptPath, $PyBytes)

$PreviousPythonPath = $env:PYTHONPATH
$PreviousDontWrite = $env:PYTHONDONTWRITEBYTECODE
$PreviousLauncherPath = $env:ARB_R1D07_V2_LAUNCHER_PATH
try {
    $env:PYTHONPATH = (Join-Path $EffectiveRepo "src")
    $env:PYTHONDONTWRITEBYTECODE = "1"
    # Lets the probe's output-sink guard reject an alias of this launcher
    # itself without hard-coding an installed repository path into the
    # embedded source.
    $env:ARB_R1D07_V2_LAUNCHER_PATH = $PSCommandPath

    $ProbeArgs = @(
        "--candidate02", $Candidate02Path,
        "--output", $OutputPath,
        "--canonical-commit", $GitCommit,
        "--canonical-tree", $GitTree
    )
    if ($FixtureModeRequested) {
        $ProbeArgs += "--nonproduction-fixture-mode"
        if (-not [string]::IsNullOrEmpty($FixtureRepo)) { $ProbeArgs += @("--fixture-repo", $FixtureRepo) }
        if (-not [string]::IsNullOrEmpty($FixtureAuthorityPath)) { $ProbeArgs += @("--fixture-authority", $FixtureAuthorityPath) }
        if (-not [string]::IsNullOrEmpty($FixtureLedgerPath)) { $ProbeArgs += @("--fixture-ledger", $FixtureLedgerPath) }
        if (-not [string]::IsNullOrEmpty($FixtureConflictDomain)) { $ProbeArgs += @("--fixture-conflict-domain", $FixtureConflictDomain) }
        if (-not [string]::IsNullOrEmpty($FixtureFillId)) { $ProbeArgs += @("--fixture-fill-id", $FixtureFillId) }
        if (-not [string]::IsNullOrEmpty($FixtureExpectedCandidateRawSha256)) { $ProbeArgs += @("--fixture-expected-candidate-raw-sha256", $FixtureExpectedCandidateRawSha256) }
        if (-not [string]::IsNullOrEmpty($FixtureExpectedCandidateSemanticSha256)) { $ProbeArgs += @("--fixture-expected-candidate-semantic-sha256", $FixtureExpectedCandidateSemanticSha256) }
        if (-not [string]::IsNullOrEmpty($FixtureExpectedIdentityPath)) { $ProbeArgs += @("--fixture-expected-identity-path", $FixtureExpectedIdentityPath) }
        foreach ($dotted in $FixtureDropObservation) {
            if (-not [string]::IsNullOrEmpty($dotted)) { $ProbeArgs += @("--fixture-null-observation", $dotted) }
        }
        if ($FixtureRaceOccupyOutputBeforeCreate.IsPresent) { $ProbeArgs += "--fixture-race-occupy-output-before-create" }
    } elseif ($FixtureOverrideWithoutMode) {
        # Reaching the probe with a deliberately invalid fixture argument is
        # how the "default invocation must reject test-only overrides" rule
        # is proven end to end: the probe emits the complete V2 failure
        # envelope with FIXTURE_OVERRIDE_WITHOUT_FIXTURE_MODE, performs no
        # state read, and exits non-zero.
        $ProbeArgs += @("--fixture-repo", $EffectiveRepo)
    }

    # Explicit stream redirect + ForEach-Object materialization: capturing a
    # native process's output directly into a variable ($x = & exe args) can
    # trip "StandardOutputEncoding is only supported when standard output is
    # redirected" in headless/non-console PowerShell hosts. Piping through
    # *>&1 forces a real redirection so this native invocation behaves the
    # same in an interactive console and in an unattended host.
    $ProbeStdout = @(& $Python -B $ProbeScriptPath @ProbeArgs *>&1 | ForEach-Object { $_.ToString() })
    $ProbeExit = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $PreviousDontWrite
    $env:ARB_R1D07_V2_LAUNCHER_PATH = $PreviousLauncherPath
    Remove-Item -LiteralPath $ProbeScriptPath -Force -ErrorAction SilentlyContinue
}

$ProbeStdout | ForEach-Object { Write-Output $_ }

Write-Output ""
Write-Output "RESULT_PATH=$OutputPath"
# Convenience reporting only -- the authoritative result is the JSON the probe
# already emitted on stdout, and the authoritative classification is the probe
# exit code below. This block is therefore wrapped so that no failure here can
# change the terminal classification or the process exit code: with
# `$ErrorActionPreference = "Stop"`, an unavailable cmdlet in the local host
# would otherwise abort the script before `exit $ProbeExit` and silently
# rewrite a complete observation as a generic failure.
#
# SHA-256 is computed through the .NET API rather than `Get-FileHash` on
# purpose: `Get-FileHash` lives in a module that is not resolvable in every
# Windows PowerShell host this launcher may be invoked from (an inherited
# `PSModulePath` that front-loads PowerShell 7 module roots is enough to hide
# it), whereas `System.Security.Cryptography` is always present.
#
# CORRECTION_03: this block reports on the result file ONLY when the probe
# itself reports `"output_written":true`, i.e. only for a file the probe just
# exclusively created. The predecessor called `Test-Path` on whatever pathname
# was requested, so after a refused sink it could stat a path under the
# deployed-state root, or open and hash a pre-existing object -- including a
# hard link to a protected store -- and print that object's size and hash as
# if they described a result. The probe emits compact JSON
# (`separators=(",", ":")`), so the literal below appears if and only if the
# probe created the file; plain string matching avoids any module dependency.
$ProbeCreatedResultFile = $false
foreach ($ProbeLine in $ProbeStdout) {
    if ($ProbeLine.Contains('"output_written":true')) { $ProbeCreatedResultFile = $true }
}
try {
    if ($ProbeCreatedResultFile) {
        $ResultBytes = [System.IO.File]::ReadAllBytes($OutputPath)
        Write-Output "RESULT_BYTES=$($ResultBytes.Length)"
        $Sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $ResultHash = [System.BitConverter]::ToString($Sha256.ComputeHash($ResultBytes)).Replace("-", "").ToLowerInvariant()
        } finally {
            $Sha256.Dispose()
        }
        Write-Output "RESULT_SHA256=$ResultHash"
    } else {
        Write-Output "RESULT_WRITTEN=NONE"
    }
} catch {
    Write-Output "RESULT_LOCAL_REPORT_UNAVAILABLE=$($_.Exception.GetType().Name)"
}

# Exit code 0 is reserved by the probe for a complete PRODUCTION observation,
# so this is the single place the production terminal PASS marker can be
# emitted -- and a nonproduction fixture run (exit 3) structurally cannot
# reach it, however green that fixture is.
if ($ProbeExit -eq 0) {
    Write-Output "READ_ONLY_REVALIDATION_TERMINAL=PASS"
} elseif ($ProbeExit -eq 3) {
    Write-Output "READ_ONLY_REVALIDATION_TERMINAL=NONPRODUCTION_FIXTURE_NO_PRODUCTION_PASS"
} else {
    Write-Output "READ_ONLY_REVALIDATION_TERMINAL=RESULT_SCHEMA_INCOMPLETE"
}

exit $ProbeExit
