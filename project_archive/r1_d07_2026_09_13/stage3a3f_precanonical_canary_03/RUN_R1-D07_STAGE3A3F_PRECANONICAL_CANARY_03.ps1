# R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03
# One-shot operator launcher.
# Scope: unchanged reviewed local candidate; temporary diagnostic risk config differs
# semantically from the accepted N1 config at exactly one leaf:
#   state_integrity.reconciliation_read_deadline_ms: 1000 -> 30000
# Then exactly one fresh D07 selector invocation and, only on selector success,
# exactly one Stage 3A-3F read-only invocation.
# No retries. No Demo writes. No production. No Stage 3G+ / RELEASE_ONLY /
# NORMAL_WRITER / Gate D. No remote Git writes.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$TaskId = "R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03"
$AuthorizationId = "R1-D07_STAGE3A3F_PRECANONICAL_CANARY_03_AUTHORIZATION_01"

$Worktree = "C:\b1\kals\claude_worktrees\ARB\market-grid-schema-dispatch-c15c4a"
$CanonicalRoot = "C:\b1\kals\ARB"
$Python = "C:\Users\RigobertoLugo\miniconda3\envs\pmresearch\python.exe"

$Candidate = "a52949b37fe87c6f7595a7137d001e383b12ab55"
$CandidateTree = "0c9382bd73c8cbd9e07876408cb145d0fb2a2440"
$Base = "f5ed9bb3f55807e347f43285f57b057f3048168f"

$RunnerRel = "src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py"
$RunnerBlob = "cd8082586ca19bedb2fa806a33c3f173df580347"
$RunnerBytes = 572353
$RunnerSha256 = "9a2a699d7eb049274f1c4fe9023ea440632f659cc84ecdeb88b858ec52f0cd41"

$TestRel = "tests/test_kalshi_minimal_market_maker_experiment_runner.py"
$TestBlob = "260dcfebe3649253e2ede6b2dc77637ff0072018"
$TestBytes = 586490
$TestSha256 = "aea636af0846f8b4764fda396243e7bdb7242bfc5f123c864dba5635b4cc7ed4"

$SelectorRel = "src/arb/venues/kalshi/d07_market_selector.py"
$SelectorBlob = "47028082032b285b86c8ece51b864345ad707f34"
$SelectorBytes = 51169
$SelectorSha256 = "e5600cece8e292761fd9793739825090ab299575ef8f3aa966ef4f2db965de14"

$AuthorityNamespaceId = "ARB_KALSHI_DEMO_PRIMARY_AUTHORITY_V1"
$AuthorityNamespaceRoot = "C:\b1\kals\arb_state\kalshi_demo_primary_v1\authority"
$LedgerPath = "C:\b1\kals\arb_state\kalshi_demo_primary_v1\ledger\subaccount1_execution_v2.sqlite3"
$BootstrapContractSha256 = "c387e47c2862e6082e75bc8eb8dfa47ed085ec7be98e8426970a278a953e7360"
$AccountScopeRef = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
$Subaccount = 1
$ExchangeIndex = 0

$ExpectedN1TrustedSequence = 14
$ExpectedN1TrustedHash = "d3f88597cc22692c32a21fadaa2caed1057d77e786ca887597a3e1b80e4917a2"
$ExpectedN1FillId = "07212270-bae1-9bda-8e24-cd2221a09d60"
$ExpectedN1FillEventId = "evt_64a34f581264426d9695c117aebbab7c"
$ExpectedN1FillOrderId = "01a05f53-3238-7b6d-8cf2-eb152d909826"
$ExpectedN1FillTicker = "KXAAAGASD-26SEP02-4.1200"
$ExpectedN1FillCreatedAtUtc = "2026-09-01T23:34:43.231843Z"

$AcceptedRiskConfigName = "R1-D07_N1_PRE_RELEASE_RISK_CONFIG_CANDIDATE_01.json"
$AcceptedRiskConfigBytes = 1721
$AcceptedRiskConfigSha256 = "7266ca2a60d58b21547dca66e7016b37a4cbe9c5289e741f9b746b8296bc649c"
$AcceptedReconciliationReadDeadlineMs = 1000
$DiagnosticReconciliationReadDeadlineMs = 30000

function Stop-Preflight([string] $Reason) {
    throw "PRECANONICAL_PREFLIGHT_HALT: $Reason`nNo selector or Stage3 invocation has been started; execution authorization remains unconsumed."
}

function Assert-Equal([string] $Name, [string] $Observed, [string] $Expected) {
    if ($Observed -ne $Expected) {
        Stop-Preflight "$Name mismatch. expected=$Expected observed=$Observed"
    }
}

function Get-LowerSha256([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $Worktree -PathType Container)) {
    Stop-Preflight "candidate worktree missing"
}
if (-not (Test-Path -LiteralPath $CanonicalRoot -PathType Container)) {
    Stop-Preflight "canonical repository root missing"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Stop-Preflight "pmresearch Python interpreter missing"
}
if (-not (Test-Path -LiteralPath $AuthorityNamespaceRoot -PathType Container)) {
    Stop-Preflight "authority namespace root missing"
}
if (-not (Test-Path -LiteralPath $LedgerPath -PathType Leaf)) {
    Stop-Preflight "N1 ledger missing"
}

# Exact candidate / canonical-state provenance gate.
$ObservedHead = (& git -C $Worktree rev-parse HEAD).Trim()
$ObservedTree = (& git -C $Worktree rev-parse 'HEAD^{tree}').Trim()
$ObservedParent = (& git -C $Worktree rev-parse 'HEAD^').Trim()
Assert-Equal "candidate HEAD" $ObservedHead $Candidate
Assert-Equal "candidate tree" $ObservedTree $CandidateTree
Assert-Equal "candidate parent" $ObservedParent $Base

$WorktreeStatus = @(& git -C $Worktree status --porcelain=v1 --untracked-files=all)
if ($WorktreeStatus.Count -ne 0) {
    Stop-Preflight "candidate worktree is not clean"
}

$CanonicalHead = (& git -C $CanonicalRoot rev-parse HEAD).Trim()
Assert-Equal "local canonical HEAD" $CanonicalHead $Base
$CanonicalStatus = @(& git -C $CanonicalRoot status --porcelain=v1 --untracked-files=all)
if ($CanonicalStatus.Count -ne 0) {
    Stop-Preflight "local canonical repository is not clean"
}

$Changed = @(& git -C $Worktree diff --name-only "$Base..$Candidate")
$ExpectedChanged = @($RunnerRel, $TestRel)
if ($Changed.Count -ne 2 -or
    $Changed[0] -ne $ExpectedChanged[0] -or
    $Changed[1] -ne $ExpectedChanged[1]) {
    Stop-Preflight ("candidate changed-path set mismatch: " + ($Changed -join ","))
}

$RunnerPath = Join-Path $Worktree $RunnerRel
$TestPath = Join-Path $Worktree $TestRel
$SelectorPath = Join-Path $Worktree $SelectorRel

Assert-Equal "runner committed blob" ((& git -C $Worktree rev-parse "HEAD:$RunnerRel").Trim()) $RunnerBlob
Assert-Equal "test committed blob" ((& git -C $Worktree rev-parse "HEAD:$TestRel").Trim()) $TestBlob
Assert-Equal "selector committed blob" ((& git -C $Worktree rev-parse "HEAD:$SelectorRel").Trim()) $SelectorBlob

if ((Get-Item -LiteralPath $RunnerPath).Length -ne $RunnerBytes) { Stop-Preflight "runner byte length mismatch" }
if ((Get-Item -LiteralPath $TestPath).Length -ne $TestBytes) { Stop-Preflight "test byte length mismatch" }
if ((Get-Item -LiteralPath $SelectorPath).Length -ne $SelectorBytes) { Stop-Preflight "selector byte length mismatch" }

Assert-Equal "runner SHA-256" (Get-LowerSha256 $RunnerPath) $RunnerSha256
Assert-Equal "test SHA-256" (Get-LowerSha256 $TestPath) $TestSha256
Assert-Equal "selector SHA-256" (Get-LowerSha256 $SelectorPath) $SelectorSha256

# Locate the exact accepted N1 risk config by filename + byte length + SHA-256.
$RiskCandidates = @(
    Get-ChildItem -LiteralPath "C:\b1\kals" -Filter $AcceptedRiskConfigName -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Length -eq $AcceptedRiskConfigBytes -and
            (Get-LowerSha256 $_.FullName) -eq $AcceptedRiskConfigSha256
        } |
        Sort-Object FullName
)
if ($RiskCandidates.Count -lt 1) {
    Stop-Preflight "exact accepted risk-config file not found under C:\b1\kals"
}
$AcceptedRiskConfigPath = $RiskCandidates[0].FullName

# Credential-presence gate only; values are never printed.
if ([string]::IsNullOrWhiteSpace($env:KALSHI_DEMO_API_KEY_ID)) {
    Stop-Preflight "KALSHI_DEMO_API_KEY_ID is absent"
}
if ([string]::IsNullOrWhiteSpace($env:KALSHI_DEMO_PRIVATE_KEY_PATH)) {
    Stop-Preflight "KALSHI_DEMO_PRIVATE_KEY_PATH is absent"
}
if (-not (Test-Path -LiteralPath $env:KALSHI_DEMO_PRIVATE_KEY_PATH -PathType Leaf)) {
    Stop-Preflight "KALSHI_DEMO_PRIVATE_KEY_PATH does not name a file"
}
if (-not [string]::IsNullOrEmpty($env:KALSHI_DEMO_PRIVATE_KEY_PEM)) {
    Stop-Preflight "KALSHI_DEMO_PRIVATE_KEY_PEM is already populated; credential source is ambiguous"
}

$PreviousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = (Join-Path $Worktree "src")

# Import-location proof before any live invocation.
$RunnerImportedFrom = (& $Python -c 'import pathlib, arb.venues.kalshi.minimal_market_maker_experiment_runner as m; print(pathlib.Path(m.__file__).resolve())').Trim()
$SelectorImportedFrom = (& $Python -c 'import pathlib, arb.venues.kalshi.d07_market_selector as m; print(pathlib.Path(m.__file__).resolve())').Trim()
Assert-Equal "runner import location" $RunnerImportedFrom ([IO.Path]::GetFullPath($RunnerPath))
Assert-Equal "selector import location" $SelectorImportedFrom ([IO.Path]::GetFullPath($SelectorPath))

# Exact N1 local-state preflight after accepted prestack-fill materialization.
# Read-only and before the live execution-authorization consumption boundary.
$env:ARB_PREFLIGHT_CANONICAL_ROOT = $CanonicalRoot
$env:ARB_PREFLIGHT_AUTHORITY_NAMESPACE_ID = $AuthorityNamespaceId
$env:ARB_PREFLIGHT_AUTHORITY_NAMESPACE_ROOT = $AuthorityNamespaceRoot
$env:ARB_PREFLIGHT_LEDGER_PATH = $LedgerPath
$env:ARB_PREFLIGHT_BOOTSTRAP_SHA256 = $BootstrapContractSha256
$env:ARB_PREFLIGHT_EXPECTED_SEQUENCE = [string]$ExpectedN1TrustedSequence
$env:ARB_PREFLIGHT_EXPECTED_HASH = $ExpectedN1TrustedHash
$env:ARB_PREFLIGHT_FILL_ID = $ExpectedN1FillId
$env:ARB_PREFLIGHT_FILL_EVENT_ID = $ExpectedN1FillEventId
$env:ARB_PREFLIGHT_FILL_ORDER_ID = $ExpectedN1FillOrderId
$env:ARB_PREFLIGHT_FILL_TICKER = $ExpectedN1FillTicker
$env:ARB_PREFLIGHT_FILL_CREATED_AT = $ExpectedN1FillCreatedAtUtc

$StatePreflightPy = @'
from decimal import Decimal
import os

from arb.execution_ledger import AuthorityLedgerRelation, AuthorityNamespaceBinding
from arb.venues.kalshi.ledger_binding import (
    ActiveExecutionDomainContractV1,
    ExecutionDomainBindingV1,
    read_active_local_safety_state_v1,
    read_active_trusted_release_evidence_projection_v1,
)

canonical_root = os.environ["ARB_PREFLIGHT_CANONICAL_ROOT"]
binding = AuthorityNamespaceBinding.bind(
    authority_namespace_id=os.environ["ARB_PREFLIGHT_AUTHORITY_NAMESPACE_ID"],
    authority_namespace_root=os.environ["ARB_PREFLIGHT_AUTHORITY_NAMESPACE_ROOT"],
    canonical_repository_root=canonical_root,
)
domain_binding = ExecutionDomainBindingV1(
    venue="KALSHI",
    environment="KALSHI_DEMO",
    account_scope_ref="ARB_KALSHI_DEMO_PRIMARY_ACCOUNT",
    subaccount=1,
    exchange_index=0,
)
active_contract = ActiveExecutionDomainContractV1(
    binding=domain_binding,
    bootstrap_contract_sha256=os.environ["ARB_PREFLIGHT_BOOTSTRAP_SHA256"],
)

expected_seq = int(os.environ["ARB_PREFLIGHT_EXPECTED_SEQUENCE"])
expected_hash = os.environ["ARB_PREFLIGHT_EXPECTED_HASH"]
fill_id = os.environ["ARB_PREFLIGHT_FILL_ID"]
fill_event_id = os.environ["ARB_PREFLIGHT_FILL_EVENT_ID"]
fill_order_id = os.environ["ARB_PREFLIGHT_FILL_ORDER_ID"]
fill_ticker = os.environ["ARB_PREFLIGHT_FILL_TICKER"]
fill_created = os.environ["ARB_PREFLIGHT_FILL_CREATED_AT"]

local = read_active_local_safety_state_v1(
    binding,
    canonical_repository_root=canonical_root,
    active_contract=active_contract,
    expected_ledger_path=os.environ["ARB_PREFLIGHT_LEDGER_PATH"],
)
if local.failure_code is not None or local.projection is None:
    raise SystemExit(f"LOCAL_STATE_READ_FAILED:{local.failure_code}")
if local.authority_ledger_relation is not AuthorityLedgerRelation.EQUAL:
    raise SystemExit(f"LOCAL_STATE_RELATION_NOT_EQUAL:{local.authority_ledger_relation}")

safety = local.projection
if safety.active_restricted_session_id is not None:
    raise SystemExit(f"ACTIVE_RESTRICTED_SESSION:{safety.active_restricted_session_id}")
if tuple(safety.abnormal_restricted_session_ids) != ():
    raise SystemExit(f"ABNORMAL_RESTRICTED_SESSIONS:{tuple(safety.abnormal_restricted_session_ids)}")
if safety.risk_control_state != "BOOT_HOLD" or safety.risk_state_epoch != 0:
    raise SystemExit(
        f"RISK_STATE_MISMATCH:{safety.risk_control_state}:{safety.risk_state_epoch}"
    )

stored = safety.canonical_fills_by_fill_id.get(fill_id)
if stored is None:
    raise SystemExit("EXPECTED_DURABLE_FILL_MISSING")
# Replay stores Decimal values in canonical tagged representation; economic
# Decimal equality is verified below through the trusted projection.
if (
    stored.get("fill_id") != fill_id
    or stored.get("order_id") != fill_order_id
    or stored.get("market") != fill_ticker
    or stored.get("outcome_side") != "YES"
    or stored.get("authoritative_created_time_utc") != fill_created
):
    raise SystemExit("EXPECTED_DURABLE_FILL_CONTENT_MISMATCH")

trusted = read_active_trusted_release_evidence_projection_v1(
    binding,
    canonical_repository_root=canonical_root,
    active_contract=active_contract,
    expected_ledger_path=os.environ["ARB_PREFLIGHT_LEDGER_PATH"],
)
if trusted.failure_code is not None or trusted.projection is None:
    raise SystemExit(f"TRUSTED_STATE_READ_FAILED:{trusted.failure_code}")
if trusted.authority_ledger_relation is not AuthorityLedgerRelation.EQUAL:
    raise SystemExit(f"TRUSTED_STATE_RELATION_NOT_EQUAL:{trusted.authority_ledger_relation}")

projection = trusted.projection
if (
    projection.authority_trusted_sequence != expected_seq
    or projection.ledger_terminal_sequence != expected_seq
    or projection.authority_trusted_event_hash != expected_hash
    or projection.ledger_terminal_event_hash != expected_hash
):
    raise SystemExit(
        "TRUSTED_TAIL_MISMATCH:"
        f"{projection.authority_trusted_sequence}:"
        f"{projection.authority_trusted_event_hash}:"
        f"{projection.ledger_terminal_sequence}:"
        f"{projection.ledger_terminal_event_hash}"
    )

matches = tuple(item for item in projection.fills if item.fill_id == fill_id)
if len(matches) != 1:
    raise SystemExit(f"TRUSTED_FILL_MATCH_COUNT:{len(matches)}")
fill = matches[0]
if (
    fill.market != fill_ticker
    or fill.outcome_side != "YES"
    or fill.quantity != Decimal("1.00")
    or fill.yes_price != Decimal("0.5000")
    or fill.authoritative_created_time_utc != fill_created
):
    raise SystemExit("TRUSTED_FILL_CONTENT_MISMATCH")

if tuple(projection.fill_matching_event_ids.get(fill_id, ())) != (fill_event_id,):
    raise SystemExit(
        "TRUSTED_FILL_EVENT_ID_MISMATCH:"
        f"{tuple(projection.fill_matching_event_ids.get(fill_id, ()))}"
    )
if tuple(projection.conflict_ids) != ():
    raise SystemExit(f"TRUSTED_PROJECTION_CONFLICTS:{tuple(projection.conflict_ids)}")

print("N1_STATE_PREFLIGHT=PASS")
'@

$StatePreflightOutput = @($StatePreflightPy | & $Python -)
$StatePreflightExit = $LASTEXITCODE
if ($StatePreflightExit -ne 0) {
    Stop-Preflight ("N1 exact local-state preflight failed: " + ($StatePreflightOutput -join " | "))
}
if (($StatePreflightOutput -join "`n").Trim() -ne "N1_STATE_PREFLIGHT=PASS") {
    Stop-Preflight ("unexpected N1 state-preflight output: " + ($StatePreflightOutput -join " | "))
}

$InvocationId = "r1d07_precanonical_canary03_" + [Guid]::NewGuid().ToString("N")
$TempRoot = [IO.Path]::GetTempPath()
$AuthPath = Join-Path $TempRoot ($InvocationId + "_AUTH.json")
$DiagnosticRiskPath = Join-Path $TempRoot ($InvocationId + "_RISK.json")

# Construct the temporary diagnostic risk config OFFLINE.
# The helper proves that the accepted source has the expected exact leaf value,
# deep-copies it, changes only that one semantic leaf, and writes a fresh temp file.
$env:ARB_ACCEPTED_RISK_CONFIG_PATH = $AcceptedRiskConfigPath
$env:ARB_DIAGNOSTIC_RISK_CONFIG_PATH = $DiagnosticRiskPath
$env:ARB_ACCEPTED_DEADLINE_MS = [string]$AcceptedReconciliationReadDeadlineMs
$env:ARB_DIAGNOSTIC_DEADLINE_MS = [string]$DiagnosticReconciliationReadDeadlineMs
$RiskMutationPy = @'
import copy
import json
import os
from pathlib import Path

src = Path(os.environ["ARB_ACCEPTED_RISK_CONFIG_PATH"])
dst = Path(os.environ["ARB_DIAGNOSTIC_RISK_CONFIG_PATH"])
old_ms = int(os.environ["ARB_ACCEPTED_DEADLINE_MS"])
new_ms = int(os.environ["ARB_DIAGNOSTIC_DEADLINE_MS"])

raw = src.read_text(encoding="utf-8")
obj = json.loads(raw)

if type(obj) is not dict:
    raise SystemExit("risk config top level is not an object")
si = obj.get("state_integrity")
if type(si) is not dict:
    raise SystemExit("state_integrity missing/not object")
observed = si.get("reconciliation_read_deadline_ms")
if type(observed) is not int or type(observed) is bool or observed != old_ms:
    raise SystemExit(
        f"unexpected accepted reconciliation_read_deadline_ms: {observed!r}"
    )

candidate = copy.deepcopy(obj)
candidate["state_integrity"]["reconciliation_read_deadline_ms"] = new_ms

# Prove exactly one semantic leaf differs.
def walk(a, b, path=()):
    diffs = []
    if type(a) is not type(b):
        return [(path, a, b)]
    if isinstance(a, dict):
        if set(a) != set(b):
            return [(path + ("<keys>",), sorted(a), sorted(b))]
        for k in sorted(a):
            diffs.extend(walk(a[k], b[k], path + (k,)))
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            return [(path + ("<len>",), len(a), len(b))]
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(walk(x, y, path + (i,)))
        return diffs
    if a != b:
        return [(path, a, b)]
    return []

diffs = walk(obj, candidate)
expected = [
    (
        ("state_integrity", "reconciliation_read_deadline_ms"),
        old_ms,
        new_ms,
    )
]
if diffs != expected:
    raise SystemExit(f"unexpected semantic diff: {diffs!r}")

dst.write_text(
    json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
    encoding="utf-8",
    newline="\n",
)
'@

$RiskMutationPy | & $Python -
if ($LASTEXITCODE -ne 0) {
    Stop-Preflight "diagnostic risk-config construction/semantic-diff proof failed"
}
if (-not (Test-Path -LiteralPath $DiagnosticRiskPath -PathType Leaf)) {
    Stop-Preflight "diagnostic risk-config file was not created"
}
$DiagnosticRiskSha256 = Get-LowerSha256 $DiagnosticRiskPath

# Exact external D07 capability envelope: four PERMITTED, nine PROHIBITED.
$AuthObject = [ordered]@{
    schema_version = 1
    authorization_id = $AuthorizationId
    authorizing_authority = "Gustavo"
    task_id = $TaskId
    issue_date = "2026-09-13"
    completion_rule = "single-attempt"
    network_access = "PERMITTED"
    demo_public_reads = "PERMITTED"
    demo_authenticated_reads = "PERMITTED"
    demo_writes = "PROHIBITED"
    production_public_reads = "PROHIBITED"
    production_authenticated_reads = "PROHIBITED"
    production_writes = "PROHIBITED"
    credential_use = "PERMITTED"
    account_funding = "PROHIBITED"
    code_changes = "PROHIBITED"
    tests = "PROHIBITED"
    artifact_generation = "PROHIBITED"
    repository_commits = "PROHIBITED"
}
$AuthJson = $AuthObject | ConvertTo-Json -Compress
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($AuthPath, $AuthJson, $Utf8NoBom)
$AuthSha256 = Get-LowerSha256 $AuthPath

Write-Host "PRECANONICAL_CANARY_PREFLIGHT=PASS"
Write-Host "TASK_ID=$TaskId"
Write-Host "CANDIDATE_COMMIT=$Candidate"
Write-Host "EXPECTED_N1_TRUSTED_SEQUENCE=$ExpectedN1TrustedSequence"
Write-Host "EXPECTED_N1_TRUSTED_HASH=$ExpectedN1TrustedHash"
Write-Host "EXPECTED_N1_DURABLE_FILL_ID=$ExpectedN1FillId"
Write-Host "ACCEPTED_RISK_CONFIG_SHA256=$AcceptedRiskConfigSha256"
Write-Host "DIAGNOSTIC_RISK_DELTA=state_integrity.reconciliation_read_deadline_ms:$AcceptedReconciliationReadDeadlineMs->$DiagnosticReconciliationReadDeadlineMs"
Write-Host "DIAGNOSTIC_RISK_CONFIG_SHA256=$DiagnosticRiskSha256"
Write-Host "EXECUTION_AUTHORIZATION_ID=$AuthorizationId"
Write-Host "EXECUTION_AUTHORIZATION_SHA256=$AuthSha256"
Write-Host "AUTOMATIC_RETRIES=0"
Write-Host "DEMO_WRITES=PROHIBITED"
Write-Host "PRODUCTION=PROHIBITED"
Write-Host ""
Write-Host "=== AUTHORIZATION CONSUMPTION BOUNDARY: SELECTOR INVOCATION 1/1 ==="

try {
    Set-Location -LiteralPath $Worktree

    # EXACTLY ONE selector invocation. Do not retry.
    $SelectorStdout = @(& $Python -m arb.venues.kalshi.d07_market_selector --json)
    $SelectorExit = $LASTEXITCODE
    $SelectorText = ($SelectorStdout -join "`n").Trim()

    if ($SelectorExit -ne 0) {
        $Partial = [ordered]@{
            schema = "ARB_R1_D07_STAGE3A3F_PRECANONICAL_CANARY_RESULT_WRAPPER_V1"
            task_id = $TaskId
            invocation_id = $InvocationId
            candidate_commit = $Candidate
            selector_invocation_count = 1
            selector_exit_code = $SelectorExit
            selector_output = $SelectorText
            stage3_invocation_count = 0
            diagnostic_reconciliation_read_deadline_ms = $DiagnosticReconciliationReadDeadlineMs
            diagnostic_risk_config_sha256 = $DiagnosticRiskSha256
            authorization_disposition = "PARTIALLY_CONSUMED_SELECTOR_ONLY"
            automatic_retry = 0
            demo_writes = "PROHIBITED"
            production = "PROHIBITED"
            writer_release = "PROHIBITED"
            stage_3g_plus = "PROHIBITED"
        }
        Write-Output ($Partial | ConvertTo-Json -Compress -Depth 8)
        exit $SelectorExit
    }

    try {
        $SelectorResult = $SelectorText | ConvertFrom-Json
    }
    catch {
        $Partial = [ordered]@{
            schema = "ARB_R1_D07_STAGE3A3F_PRECANONICAL_CANARY_RESULT_WRAPPER_V1"
            task_id = $TaskId
            invocation_id = $InvocationId
            candidate_commit = $Candidate
            selector_invocation_count = 1
            selector_exit_code = $SelectorExit
            selector_output = $SelectorText
            stage3_invocation_count = 0
            diagnostic_reconciliation_read_deadline_ms = $DiagnosticReconciliationReadDeadlineMs
            diagnostic_risk_config_sha256 = $DiagnosticRiskSha256
            authorization_disposition = "PARTIALLY_CONSUMED_SELECTOR_ONLY"
            terminal_reason = "SELECTOR_JSON_PARSE_FAILED"
            automatic_retry = 0
            demo_writes = "PROHIBITED"
            production = "PROHIBITED"
            writer_release = "PROHIBITED"
            stage_3g_plus = "PROHIBITED"
        }
        Write-Output ($Partial | ConvertTo-Json -Compress -Depth 8)
        exit 91
    }

    if ($SelectorResult.status -ne "SUCCEEDED" -or [string]::IsNullOrWhiteSpace([string]$SelectorResult.selected_ticker)) {
        $Partial = [ordered]@{
            schema = "ARB_R1_D07_STAGE3A3F_PRECANONICAL_CANARY_RESULT_WRAPPER_V1"
            task_id = $TaskId
            invocation_id = $InvocationId
            candidate_commit = $Candidate
            selector_invocation_count = 1
            selector_exit_code = $SelectorExit
            selector_result = $SelectorResult
            stage3_invocation_count = 0
            diagnostic_reconciliation_read_deadline_ms = $DiagnosticReconciliationReadDeadlineMs
            diagnostic_risk_config_sha256 = $DiagnosticRiskSha256
            authorization_disposition = "PARTIALLY_CONSUMED_SELECTOR_ONLY"
            automatic_retry = 0
            demo_writes = "PROHIBITED"
            production = "PROHIBITED"
            writer_release = "PROHIBITED"
            stage_3g_plus = "PROHIBITED"
        }
        Write-Output ($Partial | ConvertTo-Json -Compress -Depth 8)
        exit 92
    }

    $Ticker = [string]$SelectorResult.selected_ticker
    Write-Host "SELECTED_TICKER=$Ticker"
    Write-Host ""
    Write-Host "=== AUTHORIZATION CONSUMPTION BOUNDARY: STAGE3 INVOCATION 1/1 ==="

    # EXACTLY ONE Stage 3A-3F invocation. Do not retry.
    $Stage3Timer = [Diagnostics.Stopwatch]::StartNew()
    $Stage3Stdout = @(
        & $Python -m arb.venues.kalshi.minimal_market_maker_experiment_runner `
            --ticker $Ticker `
            --authority-namespace-id $AuthorityNamespaceId `
            --authority-namespace-root $AuthorityNamespaceRoot `
            --canonical-repository-root $CanonicalRoot `
            --ledger-path $LedgerPath `
            --bootstrap-contract-sha256 $BootstrapContractSha256 `
            --risk-config-json $DiagnosticRiskPath `
            --risk-config-sha256 $DiagnosticRiskSha256 `
            --execution-authorization-json $AuthPath `
            --execution-authorization-sha256 $AuthSha256 `
            --installed-implementation-commit $Candidate `
            --account-scope-ref $AccountScopeRef `
            --subaccount $Subaccount `
            --exchange-index $ExchangeIndex `
            --invocation-id $InvocationId `
            --confirm-live-read
    )
    $Stage3Exit = $LASTEXITCODE
    $Stage3Timer.Stop()
    $Stage3ElapsedMs = [int64]$Stage3Timer.ElapsedMilliseconds
    $Stage3Lines = @($Stage3Stdout | ForEach-Object { [string]$_ })

    $Result = [ordered]@{
        schema = "ARB_R1_D07_STAGE3A3F_PRECANONICAL_CANARY_RESULT_WRAPPER_V1"
        task_id = $TaskId
        invocation_id = $InvocationId
        candidate_commit = $Candidate
        candidate_tree = $CandidateTree
        candidate_parent = $Base
        expected_n1_trusted_sequence = $ExpectedN1TrustedSequence
        expected_n1_trusted_hash = $ExpectedN1TrustedHash
        expected_n1_durable_fill_id = $ExpectedN1FillId
        selector_invocation_count = 1
        selector_result = $SelectorResult
        stage3_invocation_count = 1
        stage3_exit_code = $Stage3Exit
        stage3_elapsed_ms = $Stage3ElapsedMs
        stage3_output_lines = $Stage3Lines
        execution_authorization_id = $AuthorizationId
        execution_authorization_sha256 = $AuthSha256
        accepted_risk_config_raw_sha256 = $AcceptedRiskConfigSha256
        diagnostic_risk_config_sha256 = $DiagnosticRiskSha256
        diagnostic_risk_delta = "state_integrity.reconciliation_read_deadline_ms:$AcceptedReconciliationReadDeadlineMs->$DiagnosticReconciliationReadDeadlineMs"
        installed_implementation_commit = $Candidate
        authorization_disposition = "CONSUMED"
        automatic_retry = 0
        demo_writes = "PROHIBITED"
        production = "PROHIBITED"
        writer_release = "PROHIBITED"
        release_only = "PROHIBITED"
        normal_writer = "PROHIBITED"
        gate_d = "PROHIBITED"
        stage_3g_plus = "PROHIBITED"
    }

    Write-Host ""
    Write-Host "=== TERMINAL RESULT ==="
    Write-Output ($Result | ConvertTo-Json -Compress -Depth 12)

    exit $Stage3Exit
}
finally {
    foreach ($p in @($AuthPath, $DiagnosticRiskPath)) {
        if (Test-Path -LiteralPath $p) {
            Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item Env:ARB_ACCEPTED_RISK_CONFIG_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:ARB_DIAGNOSTIC_RISK_CONFIG_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:ARB_ACCEPTED_DEADLINE_MS -ErrorAction SilentlyContinue
    Remove-Item Env:ARB_DIAGNOSTIC_DEADLINE_MS -ErrorAction SilentlyContinue
    foreach ($name in @(
        "ARB_PREFLIGHT_CANONICAL_ROOT",
        "ARB_PREFLIGHT_AUTHORITY_NAMESPACE_ID",
        "ARB_PREFLIGHT_AUTHORITY_NAMESPACE_ROOT",
        "ARB_PREFLIGHT_LEDGER_PATH",
        "ARB_PREFLIGHT_BOOTSTRAP_SHA256",
        "ARB_PREFLIGHT_EXPECTED_SEQUENCE",
        "ARB_PREFLIGHT_EXPECTED_HASH",
        "ARB_PREFLIGHT_FILL_ID",
        "ARB_PREFLIGHT_FILL_EVENT_ID",
        "ARB_PREFLIGHT_FILL_ORDER_ID",
        "ARB_PREFLIGHT_FILL_TICKER",
        "ARB_PREFLIGHT_FILL_CREATED_AT"
    )) {
        Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
    }
    $env:PYTHONPATH = $PreviousPythonPath
}
