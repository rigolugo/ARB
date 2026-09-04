"""Kalshi Demo minimal two-sided market-maker experiment runner -- Gate B + C.

Gate B implements the authoritative-truth / read-only reconciliation spine
required by
`KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_EXPERIMENT_RUNNER_SPEC_04.md`
(bytes 45629, sha256
32d45abd79dafae7ffa960cfa3c15a9f536fc75d593a4c61e6ab2d3653f0e1f0), which
incorporates by exact predecessor identity every non-superseded requirement
of
`KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_EXPERIMENT_RUNNER_SPEC_03.md`
(bytes 117449, sha256
09bdca72ea83c4b701ee8c743b06f384c7fe682f7fb5bf14459ab484dad81771), as
corrected without reopening architecture by
`KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_EXPERIMENT_RUNNER_SPEC_05.md`
(bytes 44642, sha256
8b49b6437d0024ada65e43c3586a72d857063263ee4f46ca0b18e3a292ceb878).

Gate B scope (Stage 3 of the preserved 20-stage runner sequence):

    3A  process starts BOOT_HOLD
    3B  open exact authority/ledger read/local-gate path and replay
    3C  reject locally if any non-freshness release predicate is already false
    3D  if structurally release-capable, expose only PreReleaseReadCapabilityV1
    3E  collect bounded current-process read/reconciliation truth
    3F  close venue-read phase; assemble exact ReleaseEvaluationStateV1

Gate C (this implementation) begins only from a successfully completed Gate-B
`PreReleaseReadPhaseResultV1` (`status == "READ_PHASE_COMPLETE"`) and
implements exactly:

    3G  acquire canonical RELEASE_ONLY
    3H  exact durable release sequence (RISK_RELEASE_RECORDED ->
        WRITER_PROOF_RELEASED -> SAFE_HELD -> WRITER_ELIGIBLE)
    3I  CurrentProcessReleaseCompletionV1 (RESTRICTED_SESSION_ENDED readback)
    3J  NORMAL_WRITER acquisition consuming that exact same-process token
    3K  final revalidation of the live normal-writer acquisition

Gate C never constructs `CurrentProcessReleaseCompletionV1` by any means
other than the canonical `ReleaseLedgerHandle.complete_release_and_issue_
current_process_completion(...)` return value, never acquires a normal
writer other than through `acquire_normal_writer_state(...)`, and never
exposes CREATE/CANCEL, a decision loop, or any write-capable experiment
surface -- those remain a later gate's scope.

Two-path writable envelope (Gate-C dispatch Section 5) -- this file and its
test module are the only two writable paths; `src/arb/execution_ledger.py`,
`tests/test_execution_ledger.py`, `src/arb/venues/kalshi/ledger_binding.py`,
and `tests/test_kalshi_ledger_binding.py` are protected and unmodified by
this task.  Every type imported from those files is used exactly as
canonically defined; none is re-implemented here.
"""

from __future__ import annotations

import enum
import os
import re
import threading
import uuid
from dataclasses import dataclass, field, fields, replace as _dataclass_replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Callable, Mapping, Sequence, Tuple

from arb.execution_ledger import (
    ActiveLedgerMeta,
    AuthorityLedgerRelation,
    AuthorityNamespaceBinding,
    EventInput,
    EventType,
    FailureCode,
    LedgerError,
    LockedLedger,
    OpenResult,
    RestartClassification,
    SafetyProjection,
    acquire_local_state,
    canonical_json_bytes,
    canonical_timestamp,
    end_writer_session,
    sha256_hex,
    validate_canonical_timestamp,
)
from arb.venues.kalshi.ledger_binding import (
    ACCEPTED_TERMINAL_SETTLEMENT_ID,
    CURRENT_ACCOUNT_SCOPE_REF,
    CURRENT_LEGACY_INCIDENT_CONTRACT,
    AcceptedTerminalSettlementEvidenceV1,
    ActiveExecutionDomainContractV1,
    ActiveReleaseEvaluationStateV1,
    CurrentProcessReleaseCompletionV1,
    CurrentProcessReleaseCompletionV2,
    ExecutionDomainBindingV1,
    active_domain_commitment,
    LegacyIncidentContract,
    NormalWriterAcquisition,
    ReleaseEvaluationStateV1,
    ReleaseReconciliationSnapshotV1,
    ReleaseRiskSnapshotV1,
    ReleaseLedgerHandle,
    TrustedReleaseEvidenceProjectionV1,
    TrustedReleaseEvidenceReadResultV1,
    acquire_active_normal_writer_state_v1,
    acquire_active_release_only_v1,
    acquire_normal_writer_state,
    acquire_release_only,
    issue_active_current_process_release_completion_v2,
    n1_accepted_terminal_settlement_evidence,
    read_active_local_safety_state_v1,
    read_active_trusted_release_evidence_projection_v1,
    reconcile_retained_bootstrap_floor_v1,
)
from arb.venues.kalshi.risk_control import (
    EconomicFillV1,
    FreshnessStampV1,
    NormalWriteAdapter,
    PriceRangeV1,
    RiskControlError,
    RiskLimitConfigV1,
    UNKNOWN_UNBOUNDED,
    WorkingOrderV1,
    WriterEligibilityGate,
    build_orderbook_reference,
    compute_market_economic_state,
    compute_permit_domain_commitment_sha256,
    validate_price_ranges,
)
from arb.venues.kalshi.emergency_cancel import EmergencyCancelGate
from arb.venues.kalshi.orderbook import (
    DEMO_BASE_PATH,
    DEMO_HOST,
    DEMO_ORIGIN,
    DEMO_PORT,
    KalshiNativeOrderBookSnapshot,
    OrderBookHalt,
)
from arb.venues.kalshi.order_lifecycle import (
    SUPPORTED_ORDER_STATUSES,
    SendOutcome,
    check_cancel_conservation,
    classify_cancel_response,
)
from arb.venues.kalshi.order_lifecycle import RawHttpResponse as LifecycleRawHttpResponse
from arb.venues.kalshi.minimal_market_maker import (
    QUOTE_QUANTITY,
    DesiredQuoteV1,
    MarketMakerEconomicTruthV1,
    MarketMakerInputV1,
    QuoteSlot as MMQuoteSlot,
    SlotClassification,
    build_economic_truth,
    build_market_maker_config,
    compute_mm_freshness_identity_sha256,
    compute_price_grid_sha256,
    evaluate_market_maker_input,
)
from arb.venues.kalshi.quote_lifecycle import (
    QuoteAction,
    QuoteLifecycleError,
    ReconstructedSlotOwnershipV1,
    SelectedWriteV1,
    VenueBindingV1,
    VenueBindingV2,
    active_prepared_request_domain_metadata,
    allocate_client_order_id,
    build_cancel_prepared_payload,
    build_cancel_writer_eligibility_assessment,
    build_create_prepared_payload,
    build_mm_cancel_intent_payload,
    build_mm_create_intent_payload,
    build_mm_create_order_body,
    build_writer_eligibility_assessment,
    candidate_for_desired_quote,
    compare_slot,
    issue_and_persist_write_permit,
    reconstruct_slot_ownership,
    select_write_action,
    validate_cancel_request_binding,
)

__all__ = [
    "RunnerOperation",
    "PRE_RELEASE_READ_OPERATIONS",
    "WRITE_OPERATIONS",
    "RunnerFailureCode",
    "RunnerError",
    "PRE_RELEASE_READ_REQUEST_MAX",
    "OPERATION_DEADLINE_MS",
    "MAX_RESPONSE_BODY_BYTES",
    "AUTOMATIC_RETRIES",
    "REDIRECTS",
    "GET_ORDERS_MAX_PAGES",
    "GET_FILLS_MAX_PAGES_PER_ORDER",
    "GET_POSITIONS_MAX_PAGES",
    "GET_ORDER_MAX_TARGETS",
    "OPERATION_BINDING_INDEX_BYTES",
    "OPERATION_BINDING_INDEX_SHA256",
    "build_operation_binding_index",
    "DeadlineCheckpoint",
    "OperationDeadlineV1",
    "check_deadline",
    "PreparedRunnerOperationRequestV1",
    "prepare_runner_operation_request",
    "RawOperationResponseV1",
    "PreReleaseReadCapabilityV1",
    "ExperimentRunnerRuntimeV1",
    "ExperimentRunnerRuntimeV2",
    "build_active_experiment_runner_runtime_v2",
    "ExperimentRunnerInvocationV1",
    "ExperimentRunnerInvocationV2",
    "ActiveRouteQualificationV1",
    "ActiveDomainAcceptedEvidenceContractV1",
    "n1_accepted_evidence_contract",
    "SubaccountWideCompletenessTheoremV1",
    "ProvenAccountWideReadV1",
    "ActiveAccountWidePartitionV1",
    "ExchangeIndexStatusObservationV1",
    "UserDataFreshnessWatermarkV1",
    "PerIndexSurfaceTraversalV1",
    "PerIndexTraversalV1",
    "RetainedPositionSettlementReconciliationV1",
    "DynamicIndexDomainAccountWideReadV1",
    "compute_dynamic_index_domain_read_set_identity",
    "require_dynamic_index_domain_completeness",
    "active_scope_classify_row",
    "partition_active_account_wide_rows",
    "require_subaccount_wide_completeness",
    "require_complete_active_pagination",
    "collect_active_authoritative_read_truth",
    "assemble_active_release_evaluation_state_v1",
    "ActivePreReleaseReadOperationV2",
    "ActivePreReleaseReadAuthClassV2",
    "PRE_RELEASE_READ_REQUEST_MAX_V2",
    "PreReleaseReadPhaseResultV2",
    "run_pre_release_read_phase_v2",
    "run_active_experiment_stage3_and_gate_d",
    "AuthoritativeReadTruthV1",
    "PreReleaseReadPhaseResultV1",
    "LOCAL_GATE_HISTORICAL_INCIDENT_CONTEXT",
    "create_one_shot_marker",
    "run_pre_release_read_phase",
    "assemble_release_evaluation_state",
]


# ---------------------------------------------------------------------------
# Section 1 -- exact closed eight-operation set (Spec 03 Section 15/31; Spec
# 04 Section 8/15).  Only the six read members are ever exposed by
# `PreReleaseReadCapabilityV1`; CREATE_ORDER_V2/CANCEL_ORDER_V2 exist only so
# the enum/frozensets can express the closed universe this correction is
# carved out of -- no code path in this file can construct a request for
# either of them.
# ---------------------------------------------------------------------------


class RunnerOperation(enum.StrEnum):
    GET_MARKET = "GET_MARKET"
    GET_MARKET_ORDERBOOK = "GET_MARKET_ORDERBOOK"
    GET_ORDERS = "GET_ORDERS"
    GET_ORDER = "GET_ORDER"
    GET_FILLS = "GET_FILLS"
    GET_POSITIONS = "GET_POSITIONS"
    # Correction 06 (BLOCK-05-01 / CL-4 as corrected): CLOSED INTERNAL
    # active-V2 transport identifiers ONLY.  They exist so the two active-V2
    # pre-release bookend GETs flow through the SAME ``send_operation_request``
    # boundary and the SAME strict generic JSON response decoder as every
    # other read, WITHOUT a new runtime callback and WITHOUT passing arbitrary
    # strings.  They are UNREACHABLE through the legacy V1 surface: they are
    # NOT in ``PRE_RELEASE_READ_OPERATIONS``, NOT in
    # ``_GENERIC_REQUEST_OPERATIONS``, NOT in ``_ROUTE_TEMPLATES``, and
    # ``prepare_runner_operation_request`` / ``PreReleaseReadCapabilityV1``
    # reject them.  They are consumed ONLY by the active-V2 closed transport
    # mapping (``_ACTIVE_V2_TRANSPORT_OPERATIONS`` / ``_ACTIVE_V2_OP_TO_RUNNER_
    # OP`` / ``_prepare_active_v2_request``).  The controlling SEMANTIC read
    # surface remains ``ActivePreReleaseReadOperationV2`` (exactly 8 members).
    # Static check (Correction 06): no inherited contract fixes the
    # ``RunnerOperation`` enum universe -- ``OPERATION_BINDING_INDEX_SHA256``
    # derives from the string literal ``_OPERATION_BINDING_ORDER`` +
    # ``_OPERATION_BINDING_RECORDS`` (verified at import), never from
    # ``list(RunnerOperation)``; the only test over the enum universe is a
    # negative ``"PRODUCTION" not in [op.value ...]`` assertion.
    GET_EXCHANGE_STATUS = "GET_EXCHANGE_STATUS"
    GET_USER_DATA_TIMESTAMP = "GET_USER_DATA_TIMESTAMP"
    CREATE_ORDER_V2 = "CREATE_ORDER_V2"
    CANCEL_ORDER_V2 = "CANCEL_ORDER_V2"


# Preserved legacy V1 six-read allowlist -- byte/semantically UNCHANGED.
# ``GET_EXCHANGE_STATUS`` / ``GET_USER_DATA_TIMESTAMP`` are deliberately NOT
# here: they are active-V2-only closed transport identifiers.
PRE_RELEASE_READ_OPERATIONS = frozenset({
    RunnerOperation.GET_MARKET,
    RunnerOperation.GET_MARKET_ORDERBOOK,
    RunnerOperation.GET_ORDERS,
    RunnerOperation.GET_ORDER,
    RunnerOperation.GET_FILLS,
    RunnerOperation.GET_POSITIONS,
})

WRITE_OPERATIONS = frozenset({
    RunnerOperation.CREATE_ORDER_V2,
    RunnerOperation.CANCEL_ORDER_V2,
})

# The five operations that flow through the generic `prepare_runner_operation_request`
# closed-request-policy boundary.  GET_MARKET_ORDERBOOK is deliberately excluded --
# it must reuse the accepted authenticated `orderbook.py` implementation exactly
# (ER-OP-002 / ER-OB-AUTH-002) and never gets a second implementation here.
_GENERIC_REQUEST_OPERATIONS = frozenset({
    RunnerOperation.GET_MARKET,
    RunnerOperation.GET_ORDERS,
    RunnerOperation.GET_ORDER,
    RunnerOperation.GET_FILLS,
    RunnerOperation.GET_POSITIONS,
})


class RunnerFailureCode(enum.StrEnum):
    # ER04-* umbrella codes (Spec 04 Section 18).
    PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED = "PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED"
    PRE_RELEASE_OPERATION_PROHIBITED = "PRE_RELEASE_OPERATION_PROHIBITED"
    PRE_RELEASE_READ_BUDGET_EXHAUSTED = "PRE_RELEASE_READ_BUDGET_EXHAUSTED"
    PRE_RELEASE_RELEASE_PREDICATE_FAILED = "PRE_RELEASE_RELEASE_PREDICATE_FAILED"

    # More specific request/schema/deadline/reconciliation classifications
    # (Spec 04 Section 18: "existing more specific ... classifications remain
    # controlling and must not be collapsed into these new umbrella codes").
    OPERATION_REQUEST_POLICY_VIOLATION = "OPERATION_REQUEST_POLICY_VIOLATION"
    OPERATION_BINDING_INDEX_MISMATCH = "OPERATION_BINDING_INDEX_MISMATCH"
    RESPONSE_BODY_TOO_LARGE = "RESPONSE_BODY_TOO_LARGE"
    RESPONSE_SCHEMA_INVALID = "RESPONSE_SCHEMA_INVALID"
    RESPONSE_JSON_INVALID = "RESPONSE_JSON_INVALID"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    PAGINATION_INCOMPLETE = "PAGINATION_INCOMPLETE"
    CURSOR_CYCLE_DETECTED = "CURSOR_CYCLE_DETECTED"
    FILL_DUPLICATE_CONFLICT = "FILL_DUPLICATE_CONFLICT"
    ORDER_IDENTITY_INVALID = "ORDER_IDENTITY_INVALID"
    MARKET_IDENTITY_INVALID = "MARKET_IDENTITY_INVALID"
    POSITION_TRUTH_UNAVAILABLE = "POSITION_TRUTH_UNAVAILABLE"
    GET_ORDER_TARGET_LIMIT_EXCEEDED = "GET_ORDER_TARGET_LIMIT_EXCEEDED"
    LOCAL_RELEASE_IMPOSSIBILITY = "LOCAL_RELEASE_IMPOSSIBILITY"
    EXPERIMENT_AUTHORIZATION_ALREADY_CONSUMED = "EXPERIMENT_AUTHORIZATION_ALREADY_CONSUMED"
    EXPERIMENT_AUTHORIZATION_CONSUMPTION_STATE_INVALID = (
        "EXPERIMENT_AUTHORIZATION_CONSUMPTION_STATE_INVALID"
    )
    PROCESS_INSTANCE_ID_INCONSISTENT = "PROCESS_INSTANCE_ID_INCONSISTENT"

    # Implementation-02 corrections (Marco blockers 01-05).
    CAPABILITY_ISSUANCE_UNAUTHORIZED = "CAPABILITY_ISSUANCE_UNAUTHORIZED"
    ORDER_TARGET_NOT_AUTHORITATIVE = "ORDER_TARGET_NOT_AUTHORITATIVE"
    MARKET_GRID_INVALID = "MARKET_GRID_INVALID"
    POSITION_CORROBORATION_CONFLICT = "POSITION_CORROBORATION_CONFLICT"

    # Gate C -- Stage 3G-3K release / normal-writer continuation (dispatch
    # Sections 6-20). Reused where an existing classification already fits
    # (e.g. DEADLINE_EXCEEDED); these are new only where Gate C introduces a
    # genuinely new failure surface no earlier gate had.
    GATE_C_ENTRY_PRECONDITION_FAILED = "GATE_C_ENTRY_PRECONDITION_FAILED"
    RELEASE_ONLY_ACQUISITION_FAILED = "RELEASE_ONLY_ACQUISITION_FAILED"
    DURABLE_RELEASE_SEQUENCE_FAILED = "DURABLE_RELEASE_SEQUENCE_FAILED"
    CURRENT_PROCESS_RELEASE_COMPLETION_ISSUANCE_FAILED = (
        "CURRENT_PROCESS_RELEASE_COMPLETION_ISSUANCE_FAILED"
    )
    NORMAL_WRITER_ACQUISITION_FAILED = "NORMAL_WRITER_ACQUISITION_FAILED"
    STAGE_3K_REVALIDATION_FAILED = "STAGE_3K_REVALIDATION_FAILED"

    # Gate D -- Stage 4+ ordinary strategy write decision loop (dispatch
    # KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_RUNNER_GATE_D_ORDINARY_STRATEGY_WRITE_LOOP_IMPLEMENTATION_CORRECTION_02,
    # Spec 07).
    GATE_D_ENTRY_PRECONDITION_FAILED = "GATE_D_ENTRY_PRECONDITION_FAILED"
    GATE_D_READ_BUDGET_EXHAUSTED = "GATE_D_READ_BUDGET_EXHAUSTED"
    GATE_D_ORDINARY_WRITE_BUDGET_EXHAUSTED = "GATE_D_ORDINARY_WRITE_BUDGET_EXHAUSTED"
    GATE_D_STRATEGY_CUTOFF_EXCEEDED = "GATE_D_STRATEGY_CUTOFF_EXCEEDED"
    GATE_D_ABSOLUTE_DEADLINE_EXCEEDED = "GATE_D_ABSOLUTE_DEADLINE_EXCEEDED"
    GATE_D_HALTED = "GATE_D_HALTED"
    GATE_D_CANCEL_TARGET_BINDING_INVALID = "GATE_D_CANCEL_TARGET_BINDING_INVALID"
    GATE_D_FRESHNESS_EXPIRED_BEFORE_ADAPTER = "GATE_D_FRESHNESS_EXPIRED_BEFORE_ADAPTER"
    GATE_D_STRATEGY_INPUT_CONSTRUCTION_FAILED = "GATE_D_STRATEGY_INPUT_CONSTRUCTION_FAILED"

    # Revision-2 active execution-domain path (KALSHI_DEMO_DYNAMIC_SUBACCOUNT
    # _EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL_SPEC_01_CORRECTION_02,
    # DSB-WRITER-003..010 / DSB-DYN-001..006 / DSB-OPS-001..012 /
    # DSB-BUDGET-001..007 / DSB-DOMAIN/FRESH/PAGE / DSB-READSET-001..005 /
    # DSB-RISK-003..008 / DSB-READ-001..006 / DSB-RUN-001..006 /
    # DSB-FAIL-001..003).
    ACTIVE_GATE_ENTRY_PRECONDITION_FAILED = "ACTIVE_GATE_ENTRY_PRECONDITION_FAILED"
    DOMAIN_SCOPE_RESPONSE_MISMATCH = "DOMAIN_SCOPE_RESPONSE_MISMATCH"
    DOMAIN_SCOPE_RESPONSE_AMBIGUOUS = "DOMAIN_SCOPE_RESPONSE_AMBIGUOUS"
    DOMAIN_ROUTE_EXCHANGE_INDEX_MISMATCH = "DOMAIN_ROUTE_EXCHANGE_INDEX_MISMATCH"
    DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED = "DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED"
    SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN = "SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN"
    N1_RETAINED_POSITION_NOT_RECONCILED = "N1_RETAINED_POSITION_NOT_RECONCILED"
    ACTIVE_DOMAIN_CONTRACT_MISMATCH = "ACTIVE_DOMAIN_CONTRACT_MISMATCH"
    ACTIVE_DOMAIN_PERMIT_MISMATCH = "ACTIVE_DOMAIN_PERMIT_MISMATCH"
    NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH = "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH"
    ACTIVE_PATH_LEGACY_CONTRACT_REJECTED = "ACTIVE_PATH_LEGACY_CONTRACT_REJECTED"
    ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID = "ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID"

    # Correction 02 DSB-FAIL-001 -- stable trusted dynamic pre-release read
    # failure taxonomy.  A generic dynamic-read failure never masks a more
    # precise existing predecessor classification (DSB-FAIL-001 final para).
    TRUSTED_DYNAMIC_READ_CAPABILITY_REQUIRED = "TRUSTED_DYNAMIC_READ_CAPABILITY_REQUIRED"
    TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID = "TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID"
    CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED = "CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED"
    DYNAMIC_READ_SOURCE_MISMATCH = "DYNAMIC_READ_SOURCE_MISMATCH"
    DYNAMIC_READ_BUDGET_EXHAUSTED = "DYNAMIC_READ_BUDGET_EXHAUSTED"
    DYNAMIC_READ_DEADLINE_EXHAUSTED = "DYNAMIC_READ_DEADLINE_EXHAUSTED"
    DYNAMIC_READ_STATUS_DOMAIN_MALFORMED = "DYNAMIC_READ_STATUS_DOMAIN_MALFORMED"
    DYNAMIC_READ_STATUS_DOMAIN_DUPLICATE = "DYNAMIC_READ_STATUS_DOMAIN_DUPLICATE"
    DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED = "DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED"
    DYNAMIC_READ_STATUS_DOMAIN_CHANGED = "DYNAMIC_READ_STATUS_DOMAIN_CHANGED"
    DYNAMIC_READ_SELECTED_INDEX_NOT_IN_DOMAIN = "DYNAMIC_READ_SELECTED_INDEX_NOT_IN_DOMAIN"
    DYNAMIC_READ_FRESHNESS_MALFORMED = "DYNAMIC_READ_FRESHNESS_MALFORMED"
    DYNAMIC_READ_FRESHNESS_REGRESSION = "DYNAMIC_READ_FRESHNESS_REGRESSION"
    DYNAMIC_READ_FRESHNESS_STALE = "DYNAMIC_READ_FRESHNESS_STALE"
    DYNAMIC_READ_FRESHNESS_FUTURE_SKEW = "DYNAMIC_READ_FRESHNESS_FUTURE_SKEW"
    DYNAMIC_READ_CLOCK_REGRESSION = "DYNAMIC_READ_CLOCK_REGRESSION"
    DYNAMIC_READ_PAGINATION_INCOMPLETE = "DYNAMIC_READ_PAGINATION_INCOMPLETE"
    DYNAMIC_READ_CURSOR_CYCLE = "DYNAMIC_READ_CURSOR_CYCLE"
    DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH = "DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH"
    DYNAMIC_READ_POSITION_EVENT_SCOPE_UNPROVEN = "DYNAMIC_READ_POSITION_EVENT_SCOPE_UNPROVEN"
    DYNAMIC_READ_COMPOSITE_IDENTITY_MISMATCH = "DYNAMIC_READ_COMPOSITE_IDENTITY_MISMATCH"
    STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED = "STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED"
    P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH = "P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH"


class RunnerError(RuntimeError):
    """Secret-safe deterministic runner failure. Never carries a secret value."""

    def __init__(self, code: RunnerFailureCode, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code.value if detail is None else f"{code.value}:{detail}")


# ---------------------------------------------------------------------------
# Section 2 -- fixed bounds (Spec 04 Sections 11/17; Spec 03 Section 18/31).
# ---------------------------------------------------------------------------

PRE_RELEASE_READ_REQUEST_MAX = 16
EXPERIMENT_READ_REQUEST_MAX = 64  # preserved identity; not consumable here.
OPERATION_DEADLINE_MS = 10_000
MAX_RESPONSE_BODY_BYTES = 65536
AUTOMATIC_RETRIES = 0
REDIRECTS = 0

GET_ORDERS_MAX_PAGES = 2
GET_FILLS_MAX_PAGES_PER_ORDER = 4
GET_POSITIONS_MAX_PAGES = 2
GET_ORDER_MAX_TARGETS = 2

_GET_ORDERS_LIMIT = 20
_GET_FILLS_LIMIT = 50
_GET_POSITIONS_LIMIT = 20
_SUBACCOUNT = 0
_EXCHANGE_INDEX = 0


# ---------------------------------------------------------------------------
# Section 3 -- exact operation-binding index (Spec 03 ER-SOURCE-003, verbatim
# preimage/identity preserved unchanged by Spec 04 Section 16).
# ---------------------------------------------------------------------------

OPERATION_BINDING_INDEX_BYTES = 1338
OPERATION_BINDING_INDEX_SHA256 = (
    "f4e80e66cfb082318b26c1f622623f35489a5ff090613452a068740d4baf39e1"
)

_OPERATION_BINDING_ORDER: Tuple[str, ...] = (
    "GET_MARKET",
    "GET_MARKET_ORDERBOOK",
    "GET_ORDERS",
    "GET_ORDER",
    "GET_FILLS",
    "GET_POSITIONS",
    "CREATE_ORDER_V2",
    "CANCEL_ORDER_V2",
)

_OPERATION_BINDING_RECORDS: Mapping[str, Tuple[int, str]] = {
    "GET_MARKET": (1074, "52ac9b524d37c6154c9816baced03393a186ca1425b4c405636a129d7e0fa355"),
    "GET_MARKET_ORDERBOOK": (1444, "47961310515c6e0e2fe2337b5659bbb7b06bfe2b8e06c70c4e742a3ccf893998"),
    "GET_ORDERS": (1184, "43e184dca78a7c4da479f6d23f1fefbb21b08133c494f0b415516251d28453b5"),
    "GET_ORDER": (1067, "12f2ea634e656a6a3ac249af9782e917c3575bc251e5fe9aa0c41a9784f5099c"),
    "GET_FILLS": (1254, "f45d681293dae649b69ee15a9e2d4199c3a4796a11c7e3b4c11486474d20404d"),
    "GET_POSITIONS": (1365, "a45d288c1ed428a7feaf9080d2fb38ca12a2f4e74f4d4d3b6fe706e12c681767"),
    "CREATE_ORDER_V2": (1177, "eee9d61a0a6f791fc4e5dc79378be30d9f6e0e31d39260ed747bb0a703fbbb9e"),
    "CANCEL_ORDER_V2": (1083, "5855189feda82ba327d9cf971359cad0e425cce21a158036a586d36227a20e71"),
}

_OPERATION_BINDING_RETRIEVED_AT_UTC = "2026-08-16T02:10:01Z"

# The exact literal reference preimage (Spec 03 ER-SOURCE-003D), reproduced
# verbatim as the ground truth every mechanically rebuilt index is checked
# against by exact byte equality.
_OPERATION_BINDING_REFERENCE_PREIMAGE = (
    '{"binding_index_schema_revision":1,"operation_order":["GET_MARKET",'
    '"GET_MARKET_ORDERBOOK","GET_ORDERS","GET_ORDER","GET_FILLS",'
    '"GET_POSITIONS","CREATE_ORDER_V2","CANCEL_ORDER_V2"],"operations":'
    '[{"operation_name":"GET_MARKET","record_bytes":1074,"record_sha256":'
    '"52ac9b524d37c6154c9816baced03393a186ca1425b4c405636a129d7e0fa355"},'
    '{"operation_name":"GET_MARKET_ORDERBOOK","record_bytes":1444,'
    '"record_sha256":'
    '"47961310515c6e0e2fe2337b5659bbb7b06bfe2b8e06c70c4e742a3ccf893998"},'
    '{"operation_name":"GET_ORDERS","record_bytes":1184,"record_sha256":'
    '"43e184dca78a7c4da479f6d23f1fefbb21b08133c494f0b415516251d28453b5"},'
    '{"operation_name":"GET_ORDER","record_bytes":1067,"record_sha256":'
    '"12f2ea634e656a6a3ac249af9782e917c3575bc251e5fe9aa0c41a9784f5099c"},'
    '{"operation_name":"GET_FILLS","record_bytes":1254,"record_sha256":'
    '"f45d681293dae649b69ee15a9e2d4199c3a4796a11c7e3b4c11486474d20404d"},'
    '{"operation_name":"GET_POSITIONS","record_bytes":1365,"record_sha256":'
    '"a45d288c1ed428a7feaf9080d2fb38ca12a2f4e74f4d4d3b6fe706e12c681767"},'
    '{"operation_name":"CREATE_ORDER_V2","record_bytes":1177,'
    '"record_sha256":'
    '"eee9d61a0a6f791fc4e5dc79378be30d9f6e0e31d39260ed747bb0a703fbbb9e"},'
    '{"operation_name":"CANCEL_ORDER_V2","record_bytes":1083,'
    '"record_sha256":'
    '"5855189feda82ba327d9cf971359cad0e425cce21a158036a586d36227a20e71"}],'
    '"retrieved_at_utc":"2026-08-16T02:10:01Z"}'
)


def build_operation_binding_index() -> bytes:
    """Mechanically rebuild the exact Spec-03 ER-SOURCE-003 operation-binding
    index and verify it equals the accepted 1338-byte / sha256
    `f4e80e66...` identity by exact byte equality before returning it.
    """

    index_object = {
        "binding_index_schema_revision": 1,
        "operation_order": list(_OPERATION_BINDING_ORDER),
        "operations": [
            {
                "operation_name": name,
                "record_bytes": _OPERATION_BINDING_RECORDS[name][0],
                "record_sha256": _OPERATION_BINDING_RECORDS[name][1],
            }
            for name in _OPERATION_BINDING_ORDER
        ],
        "retrieved_at_utc": _OPERATION_BINDING_RETRIEVED_AT_UTC,
    }
    produced = canonical_json_bytes(index_object)
    reference = _OPERATION_BINDING_REFERENCE_PREIMAGE.encode("utf-8")
    if produced != reference:
        raise RunnerError(RunnerFailureCode.OPERATION_BINDING_INDEX_MISMATCH, detail="preimage")
    if len(produced) != OPERATION_BINDING_INDEX_BYTES:
        raise RunnerError(RunnerFailureCode.OPERATION_BINDING_INDEX_MISMATCH, detail="bytes")
    if sha256_hex(produced) != OPERATION_BINDING_INDEX_SHA256:
        raise RunnerError(RunnerFailureCode.OPERATION_BINDING_INDEX_MISMATCH, detail="sha256")
    return produced


# Verified once at import time: a corrupted literal here is a defect in this
# file, not a runtime condition to tolerate.
build_operation_binding_index()


# ---------------------------------------------------------------------------
# Section 4 -- exact Demo URL/path construction (Spec 03 ER-SOURCE-004).
# Reused, not redefined: `DEMO_HOST`/`DEMO_PORT`/`DEMO_ORIGIN`/`DEMO_BASE_PATH`
# come directly from the accepted authenticated `orderbook.py` module so the
# two implementations can never drift apart.
# ---------------------------------------------------------------------------

DEMO_API_BASE_URL = DEMO_ORIGIN + DEMO_BASE_PATH

_ROUTE_TEMPLATES: Mapping[RunnerOperation, str] = {
    RunnerOperation.GET_MARKET: "/markets/{ticker}",
    RunnerOperation.GET_ORDERS: "/portfolio/orders",
    RunnerOperation.GET_ORDER: "/portfolio/orders/{order_id}",
    RunnerOperation.GET_FILLS: "/portfolio/fills",
    RunnerOperation.GET_POSITIONS: "/portfolio/positions",
}
# NOTE (Correction 06): the active-V2 status / user_data_timestamp paths are
# NOT added to this legacy V1 route table.  Active V2 renders its exact
# DSB-OPS-003 paths from ``_ACTIVE_V2_OP_BINDING`` inside
# ``_prepare_active_v2_request`` only.

_TICKER_PATTERN = re.compile(r"[A-Za-z0-9._~-]{1,200}")
_ORDER_ID_PATTERN = re.compile(r"[A-Za-z0-9._~-]{1,200}")
_UNRESERVED = re.compile(r"[A-Za-z0-9._~-]")


def _percent_encode(value: str) -> str:
    """RFC3986 percent-encoding: unreserved characters pass through, space
    becomes `%20` (never `+`), every other byte is escaped with uppercase
    hex."""

    out: list[str] = []
    for byte in value.encode("utf-8"):
        char = chr(byte)
        if _UNRESERVED.fullmatch(char):
            out.append(char)
        else:
            out.append(f"%{byte:02X}")
    return "".join(out)


def _canonical_query_string(pairs: Sequence[Tuple[str, str]]) -> str:
    if not pairs:
        return ""
    seen: set[str] = set()
    parts: list[str] = []
    for key, value in pairs:
        if type(key) is not str or type(value) is not str or key == "":
            raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="query shape")
        if key in seen:
            raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="duplicate query key")
        seen.add(key)
        parts.append(f"{_percent_encode(key)}={_percent_encode(value)}")
    return "&".join(parts)


def _render_route(operation: RunnerOperation, path_parameters: Mapping[str, str]) -> str:
    template = _ROUTE_TEMPLATES[operation]
    if operation is RunnerOperation.GET_MARKET:
        if set(path_parameters) != {"ticker"}:
            raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="path_parameters")
        ticker = path_parameters["ticker"]
        if type(ticker) is not str or _TICKER_PATTERN.fullmatch(ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="ticker grammar")
        return template.format(ticker=ticker)
    if operation is RunnerOperation.GET_ORDER:
        if set(path_parameters) != {"order_id"}:
            raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="path_parameters")
        order_id = path_parameters["order_id"]
        if type(order_id) is not str or _ORDER_ID_PATTERN.fullmatch(order_id) is None:
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="order_id grammar")
        return template.format(order_id=order_id)
    if path_parameters:
        raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="path_parameters")
    return template


# ---------------------------------------------------------------------------
# Section 5 -- OperationDeadlineV1 (Spec 03 ER-TIME-002..004; Spec 04
# Section 12/15.1).
# ---------------------------------------------------------------------------


class DeadlineCheckpoint(enum.StrEnum):
    BEFORE_PREPARATION = "BEFORE_PREPARATION"
    AFTER_PREPARATION = "AFTER_PREPARATION"
    AFTER_SIGNING = "AFTER_SIGNING"
    AFTER_TRANSPORT = "AFTER_TRANSPORT"
    # Spec 05 ER05-RESP-008: the strict generic response boundary keeps the
    # exact same OperationDeadlineV1 identity live through each of these
    # finer-grained sub-steps, not merely "before" and "after" the whole
    # decode/parse/validate pipeline. No new failure taxonomy is added --
    # every checkpoint below still raises only RunnerFailureCode.
    # DEADLINE_EXCEEDED via the same `check_deadline` helper.
    AFTER_MEDIA_TYPE_VALIDATION = "AFTER_MEDIA_TYPE_VALIDATION"
    AFTER_BODY_SIZE_VALIDATION = "AFTER_BODY_SIZE_VALIDATION"
    AFTER_UTF8_DECODE = "AFTER_UTF8_DECODE"
    AFTER_PARSING = "AFTER_PARSING"
    AFTER_SCHEMA_VALIDATION = "AFTER_SCHEMA_VALIDATION"
    AFTER_RESULT_CONSTRUCTION = "AFTER_RESULT_CONSTRUCTION"


@dataclass(frozen=True, slots=True)
class OperationDeadlineV1:
    schema_revision: int
    deadline_id: str
    process_instance_id: str
    operation_name: str
    request_ordinal: int
    started_monotonic_ns: int
    absolute_deadline_monotonic_ns: int
    experiment_absolute_end_monotonic_ns: int

    @classmethod
    def create(
        cls,
        *,
        process_instance_id: str,
        operation_name: str,
        request_ordinal: int,
        started_monotonic_ns: int,
        experiment_absolute_end_monotonic_ns: int,
        uuid_factory: Callable[[], "uuid.UUID"] = uuid.uuid4,
    ) -> "OperationDeadlineV1":
        ceiling_ns = started_monotonic_ns + OPERATION_DEADLINE_MS * 1_000_000
        absolute = min(ceiling_ns, experiment_absolute_end_monotonic_ns)
        return cls(
            schema_revision=1,
            deadline_id=f"odl_{uuid_factory().hex}",
            process_instance_id=process_instance_id,
            operation_name=operation_name,
            request_ordinal=request_ordinal,
            started_monotonic_ns=started_monotonic_ns,
            absolute_deadline_monotonic_ns=absolute,
            experiment_absolute_end_monotonic_ns=experiment_absolute_end_monotonic_ns,
        )

    def expired(self, now_monotonic_ns: int) -> bool:
        return now_monotonic_ns >= self.absolute_deadline_monotonic_ns


def check_deadline(
    deadline: OperationDeadlineV1, now_monotonic_ns: int, *, checkpoint: DeadlineCheckpoint,
) -> None:
    if deadline.expired(now_monotonic_ns):
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail=checkpoint.value)


# ---------------------------------------------------------------------------
# Section 6 -- closed request preparation for the five generic read
# operations (Spec 03 ER-REQ-001/002, ER-OP-001/003/004/005/006).
# GET_MARKET_ORDERBOOK never reaches this function (ER-OP-002).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreparedRunnerOperationRequestV1:
    operation: RunnerOperation
    method: str
    host: str
    full_path: str
    wire_request_url: str
    signed_path_without_query: str
    query: Tuple[Tuple[str, str], ...]
    body: None
    auth_mode: str
    request_id: str


def _first_page_query(
    operation: RunnerOperation, *, ticker: str | None, order_id: str | None,
    subaccount: int = _SUBACCOUNT, exchange_index: int = _EXCHANGE_INDEX,
) -> list[Tuple[str, str]]:
    # `subaccount`/`exchange_index` default to the legacy source-bound
    # SUBACCOUNT=0 route (V1 wire behaviour byte-identical).  The active
    # revision-2 path passes runtime.domain_binding.subaccount /
    # .exchange_index instead -- no literal 0/1 in the active call site.
    if operation is RunnerOperation.GET_ORDERS:
        return [
            ("ticker", ticker or ""),
            ("status", "resting"),
            ("limit", str(_GET_ORDERS_LIMIT)),
            ("subaccount", str(subaccount)),
            ("exchange_index", str(exchange_index)),
        ]
    if operation is RunnerOperation.GET_FILLS:
        return [
            ("order_id", order_id or ""),
            ("limit", str(_GET_FILLS_LIMIT)),
            ("subaccount", str(subaccount)),
            ("exchange_index", str(exchange_index)),
        ]
    if operation is RunnerOperation.GET_POSITIONS:
        return [
            ("ticker", ticker or ""),
            ("limit", str(_GET_POSITIONS_LIMIT)),
            ("subaccount", str(subaccount)),
            ("exchange_index", str(exchange_index)),
        ]
    return []


def prepare_runner_operation_request(
    operation: RunnerOperation,
    *,
    path_parameters: Mapping[str, str],
    ticker: str | None = None,
    order_id: str | None = None,
    cursor: str | None = None,
    request_ordinal: int,
    uuid_factory: Callable[[], "uuid.UUID"] = uuid.uuid4,
    subaccount: int = _SUBACCOUNT,
    exchange_index: int = _EXCHANGE_INDEX,
) -> PreparedRunnerOperationRequestV1:
    """Pure and offline: derives method/route/full path/wire URL/signed path
    from the closed operation contract. Caller-supplied values are limited
    to exact path parameters and the exact bound cursor; nothing here can
    construct an arbitrary method/path/host/query/body.
    """

    if operation not in _GENERIC_REQUEST_OPERATIONS:
        raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="operation")

    relative_route = _render_route(operation, path_parameters)
    full_path = DEMO_BASE_PATH + relative_route

    query_pairs = _first_page_query(
        operation, ticker=ticker, order_id=order_id,
        subaccount=subaccount, exchange_index=exchange_index,
    )
    if cursor is not None:
        if operation not in (
            RunnerOperation.GET_ORDERS, RunnerOperation.GET_FILLS, RunnerOperation.GET_POSITIONS,
        ):
            raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="cursor not permitted")
        if type(cursor) is not str or cursor == "":
            raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="cursor empty")
        query_pairs = query_pairs + [("cursor", cursor)]

    canonical_query = _canonical_query_string(query_pairs)
    query_suffix = "" if canonical_query == "" else "?" + canonical_query
    wire_request_url = DEMO_ORIGIN + full_path + query_suffix

    auth_mode = "PUBLIC_UNSIGNED_FOR_THIS_OPERATION" if operation is RunnerOperation.GET_MARKET else "AUTHENTICATED"

    return PreparedRunnerOperationRequestV1(
        operation=operation,
        method="GET",
        host=DEMO_HOST,
        full_path=full_path,
        wire_request_url=wire_request_url,
        signed_path_without_query=full_path,
        query=tuple(query_pairs),
        body=None,
        auth_mode=auth_mode,
        request_id=f"req_{uuid_factory().hex}",
    )


@dataclass(frozen=True, slots=True)
class RawOperationResponseV1:
    """Transport-agnostic raw response carrier returned by the runtime's
    injected `send_operation_request` callable. Never carries a secret."""

    http_status: int
    content_type: str
    body_bytes: bytes
    transport_unknown: bool = False


# ---------------------------------------------------------------------------
# Section 7 -- response parsing/validation for the five generic reads.
# ---------------------------------------------------------------------------


_OWS_CHARS = " \t"


def _normalize_media_type(content_type: object) -> str | None:
    """Spec 05 ER05-RESP-003 exact normalization: strip ASCII SP/HTAB
    around the complete header value, take the substring before the first
    `;`, strip ASCII SP/HTAB around that token, ASCII-lowercase it. Returns
    `None` (never raises) if `content_type` is not an exact built-in `str`,
    so the caller can classify that uniformly with every other response
    failure."""

    if type(content_type) is not str:
        return None
    stripped = content_type.strip(_OWS_CHARS)
    token = stripped.split(";", 1)[0]
    return token.strip(_OWS_CHARS).lower()


class _DuplicateJsonKeyError(ValueError):
    """Internal control-flow only; converted to RunnerFailureCode.
    RESPONSE_JSON_INVALID at the strict-parser boundary (no new failure
    taxonomy, Spec 05 ER05-RESP-009)."""


class _NonFiniteJsonConstantError(ValueError):
    """Internal control-flow only; same conversion as above."""


def _reject_duplicate_json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """`object_pairs_hook` fires once per JSON object at every nesting
    depth, so this rejects duplicate member names at every depth, not only
    the top level (Spec 05 ER05-RESP-005)."""

    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_non_finite_json_constant(token: str) -> None:
    """`parse_constant` fires for `NaN`/`Infinity`/`-Infinity` (and no
    other token); raising here means no operation-specific validator ever
    sees a successfully parsed non-finite numeric constant (Spec 05
    ER05-RESP-006)."""

    raise _NonFiniteJsonConstantError(f"non-finite JSON constant is prohibited: {token}")


def _strict_json_loads(text: str) -> object:
    import json

    try:
        return json.loads(
            text, object_pairs_hook=_reject_duplicate_json_pairs,
            parse_constant=_reject_non_finite_json_constant,
        )
    except (ValueError, RecursionError) as exc:
        raise RunnerError(RunnerFailureCode.RESPONSE_JSON_INVALID, detail="json") from exc


def _decode_and_validate_runner_json_response(
    operation: "RunnerOperation",
    *,
    raw_response: "RawOperationResponseV1",
    deadline: "OperationDeadlineV1",
    now_monotonic_ns: Callable[[], int],
) -> Mapping[str, object]:
    """The one shared strict production response boundary (Spec 05
    ER05-RESP-001) for every generic Stage-3E read except the protected
    accepted orderbook path. Enforces exact media type, strict body-size
    bound before decode (never truncate-and-accept), strict UTF-8, and a
    duplicate-key-rejecting / non-finite-constant-rejecting JSON parse,
    with the same `OperationDeadlineV1` identity checked live at every
    sub-step. No caller can reach an operation-specific parser by a looser
    direct `json.loads` bypass -- this function is the only route from raw
    transport bytes to a returned top-level `dict`.
    """

    if type(raw_response) is not RawOperationResponseV1:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="transport return type")
    if raw_response.transport_unknown:
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="transport result unknown")
    if raw_response.http_status != 200:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail=f"http_status={raw_response.http_status}")

    normalized_media_type = _normalize_media_type(raw_response.content_type)
    if normalized_media_type != "application/json":
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="media type")
    check_deadline(deadline, now_monotonic_ns(), checkpoint=DeadlineCheckpoint.AFTER_MEDIA_TYPE_VALIDATION)

    body = raw_response.body_bytes
    if type(body) is not bytes:
        raise RunnerError(RunnerFailureCode.RESPONSE_JSON_INVALID, detail="body type")
    if len(body) > MAX_RESPONSE_BODY_BYTES:
        raise RunnerError(RunnerFailureCode.RESPONSE_BODY_TOO_LARGE)
    check_deadline(deadline, now_monotonic_ns(), checkpoint=DeadlineCheckpoint.AFTER_BODY_SIZE_VALIDATION)

    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RunnerError(RunnerFailureCode.RESPONSE_JSON_INVALID, detail="utf-8") from exc
    check_deadline(deadline, now_monotonic_ns(), checkpoint=DeadlineCheckpoint.AFTER_UTF8_DECODE)

    parsed = _strict_json_loads(text)
    check_deadline(deadline, now_monotonic_ns(), checkpoint=DeadlineCheckpoint.AFTER_PARSING)

    if type(parsed) is not dict:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail=f"{operation.value} top level")
    return parsed


def _require_dict(value: object, *, code: RunnerFailureCode, detail: str) -> Mapping[str, object]:
    if type(value) is not dict:
        raise RunnerError(code, detail=detail)
    return value


def _require_str(value: object, *, code: RunnerFailureCode, detail: str) -> str:
    if type(value) is not str or value == "":
        raise RunnerError(code, detail=detail)
    return value


def _require_field(obj: Mapping[str, object], name: str, *, code: RunnerFailureCode) -> object:
    """Require a key to be PRESENT (not merely falsy/absent-defaulted) --
    a missing required field is a schema violation, never silently
    defaulted (Marco Blocker 03)."""

    if name not in obj:
        raise RunnerError(code, detail=f"missing field: {name}")
    return obj[name]


def _require_exact_int(value: object, *, code: RunnerFailureCode, detail: str) -> int:
    """`type(x) is int`, never `isinstance` -- excludes `bool` (a subclass
    of `int` in Python, so `False == 0`/`True == 1` would otherwise let a
    boolean silently satisfy an exact-integer field). Marco Blocker 03 /
    C12."""

    if type(value) is not int:
        raise RunnerError(code, detail=detail)
    return value


def _require_exact_str(value: object, *, code: RunnerFailureCode, detail: str) -> str:
    if type(value) is not str:
        raise RunnerError(code, detail=detail)
    return value


def _decimal_from_price_string(value: object) -> Decimal:
    if type(value) is not str:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="price type")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="price value") from exc
    if not parsed.is_finite() or parsed < Decimal("0") or parsed > Decimal("1"):
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="price range")
    return parsed


def _decimal_from_quantity_string(value: object) -> Decimal:
    if type(value) is not str:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="quantity type")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="quantity value") from exc
    if not parsed.is_finite() or parsed <= Decimal("0"):
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="quantity range")
    return parsed


def _parse_price_ranges(raw: object) -> Tuple[PriceRangeV1, ...]:
    """Exact usable price-range/grid metadata (Spec 03 ER-OP-001; Marco
    Blocker 12). Reuses the canonical `PriceRangeV1`/`validate_price_ranges`
    grid machinery (risk_control.py) rather than a weaker parallel
    interpretation -- malformed/absent grid data fails closed here, not
    later at quote time."""

    if type(raw) is not list or not raw:
        raise RunnerError(RunnerFailureCode.MARKET_GRID_INVALID, detail="price_ranges missing/empty")
    ranges: list[PriceRangeV1] = []
    for entry in raw:
        row = _require_dict(entry, code=RunnerFailureCode.MARKET_GRID_INVALID, detail="price_range row")
        start = _decimal_from_price_string(_require_field(row, "start_dollars", code=RunnerFailureCode.MARKET_GRID_INVALID))
        end = _decimal_from_price_string(_require_field(row, "end_dollars", code=RunnerFailureCode.MARKET_GRID_INVALID))
        step_raw = _require_field(row, "step_dollars", code=RunnerFailureCode.MARKET_GRID_INVALID)
        if type(step_raw) is not str:
            raise RunnerError(RunnerFailureCode.MARKET_GRID_INVALID, detail="step type")
        try:
            step = Decimal(step_raw)
        except InvalidOperation as exc:
            raise RunnerError(RunnerFailureCode.MARKET_GRID_INVALID, detail="step value") from exc
        try:
            ranges.append(PriceRangeV1(start, end, step))
        except RiskControlError as exc:
            raise RunnerError(RunnerFailureCode.MARKET_GRID_INVALID, detail="range shape") from exc
    return tuple(ranges)


def _parse_market(
    raw: object, *, expected_ticker: str, expected_exchange_index: int = _EXCHANGE_INDEX,
) -> Mapping[str, object]:
    obj = _require_dict(raw, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="top level")
    market = _require_dict(
        _require_field(obj, "market", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="market shape",
    )
    ticker = _require_exact_str(
        _require_field(market, "ticker", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="ticker type",
    )
    status = _require_exact_str(
        _require_field(market, "status", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="status type",
    )
    exchange_index = _require_exact_int(
        _require_field(market, "exchange_index", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="exchange_index type",
    )
    if ticker != expected_ticker:
        raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="ticker mismatch")
    if status != "active":
        raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="not active")
    if exchange_index != expected_exchange_index:
        raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="exchange_index mismatch")

    price_ranges = _parse_price_ranges(_require_field(market, "price_ranges", code=RunnerFailureCode.MARKET_GRID_INVALID))
    reference_raw = _require_field(market, "yes_bid_dollars", code=RunnerFailureCode.MARKET_GRID_INVALID)
    reference_price = _decimal_from_price_string(reference_raw)
    try:
        validate_price_ranges(reference_price, price_ranges)
    except RiskControlError as exc:
        raise RunnerError(RunnerFailureCode.MARKET_GRID_INVALID, detail="reference price off-grid") from exc

    return market


def _working_order_from_raw(
    raw: object, *, expected_ticker: str,
    expected_subaccount: int = _SUBACCOUNT, expected_exchange_index: "int | None" = _EXCHANGE_INDEX,
) -> WorkingOrderV1 | None:
    # ``expected_exchange_index=None`` means "any exchange_index for the
    # expected subaccount" -- used ONLY by the proven subaccount-wide
    # aggregate pass (DSB-RISK-004 path A) so same-subaccount other-index
    # working orders can feed aggregate risk.  The scoped selected-route
    # reads always pass an exact integer.
    order = _require_dict(raw, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="order row")
    order_id = _require_exact_str(
        _require_field(order, "order_id", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="order_id type",
    )
    if order_id == "":
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="order_id blank")
    ticker = _require_exact_str(
        _require_field(order, "ticker", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="ticker type",
    )
    subaccount = _require_exact_int(
        _require_field(order, "subaccount", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="subaccount type",
    )
    exchange_index = _require_exact_int(
        _require_field(order, "exchange_index", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="exchange_index type",
    )
    if (
        ticker != expected_ticker or subaccount != expected_subaccount
        or (expected_exchange_index is not None and exchange_index != expected_exchange_index)
    ):
        raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="cross-ticker or scope conflict")
    status = _require_exact_str(
        _require_field(order, "status", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="status type",
    )
    if status != "resting":
        return None
    side = _require_field(order, "side", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    outcome_side = {"yes": "YES", "no": "NO"}.get(side) if type(side) is str else None
    if outcome_side is None:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="side")
    remaining = _require_field(order, "remaining_count_fp", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    price = _require_field(order, "yes_price_dollars", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    return WorkingOrderV1(
        expected_ticker, order_id, outcome_side,
        _decimal_from_quantity_string(remaining), _decimal_from_price_string(price),
    )


def _fill_from_raw(
    raw: object, *, expected_ticker: str, expected_order_id: str,
    expected_subaccount: int = _SUBACCOUNT, expected_exchange_index: "int | None" = _EXCHANGE_INDEX,
) -> EconomicFillV1:
    fill = _require_dict(raw, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="fill row")
    fill_id = _require_exact_str(
        _require_field(fill, "fill_id", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="fill_id type",
    )
    if fill_id == "":
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="fill_id blank")
    order_id = _require_exact_str(
        _require_field(fill, "order_id", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="order_id type",
    )
    ticker = _require_exact_str(
        _require_field(fill, "ticker", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="ticker type",
    )
    subaccount = _require_exact_int(
        _require_field(fill, "subaccount", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="subaccount type",
    )
    exchange_index = _require_exact_int(
        _require_field(fill, "exchange_index", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="exchange_index type",
    )
    if (
        order_id != expected_order_id or ticker != expected_ticker
        or subaccount != expected_subaccount
        or (expected_exchange_index is not None and exchange_index != expected_exchange_index)
    ):
        raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="fill scope mismatch")
    side = _require_field(fill, "side", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    outcome_side = {"yes": "YES", "no": "NO"}.get(side) if type(side) is str else None
    if outcome_side is None:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="fill side")
    price = _require_field(fill, "yes_price_dollars", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    quantity = _require_field(fill, "count_fp", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    created = _require_field(fill, "created_time", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    timestamp = _require_str(created, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="fill timestamp")
    validate_canonical_timestamp(timestamp)
    return EconomicFillV1(
        expected_ticker, fill_id, outcome_side,
        _decimal_from_quantity_string(quantity), _decimal_from_price_string(price), timestamp,
    )


# ---------------------------------------------------------------------------
# Section 8 -- PreReleaseReadCapabilityV1 (Spec 04 ER04-PRE-002/003).
# A closed, budget-tracked, six-method read-only capability. There is no
# generic `.send(...)`/`.request(...)` public method: the object's entire
# public surface IS the closed six-operation set, so CREATE/CANCEL/amend/
# decrease/replace/batch-write/Order-Group/WebSocket/production/arbitrary
# method-path-query-body are structurally unreachable, not merely rejected
# by convention.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExperimentRunnerRuntimeV1:
    """Closed dependency carrier (Spec 03 ER-ARCH-002). Production
    construction binds the real canonical authority binding, clocks, the
    accepted authenticated orderbook entrypoint, and the closed operation
    transport. Test fakes implement the same exact closed interfaces.
    Never accepts an arbitrary URL, method, generic authenticated client, or
    unvalidated callback."""

    normal_gate: WriterEligibilityGate
    emergency_gate: EmergencyCancelGate
    read_local_safety_state: Callable[[], OpenResult]
    read_trusted_release_evidence: Callable[[], "TrustedReleaseEvidenceReadResultV1"]
    send_operation_request: Callable[
        [RunnerOperation, PreparedRunnerOperationRequestV1, OperationDeadlineV1], RawOperationResponseV1
    ]
    fetch_orderbook: Callable[[str, OperationDeadlineV1], object]
    monotonic_clock_ns: Callable[[], int]
    wall_clock: Callable[[], datetime]
    uuid_factory: Callable[[], "uuid.UUID"]
    risk_config: RiskLimitConfigV1 | None
    experiment_absolute_end_monotonic_ns: int
    # Gate C closed data bindings (dispatch Section 9): narrow values, not
    # callbacks, needed to invoke the canonical `acquire_release_only` /
    # `acquire_normal_writer_state` persistence entrypoints directly. There
    # is deliberately no `release_callback`/`normal_writer_callback`/
    # `ledger_callback`/`writer_session_callback` -- a caller-selectable
    # authority path is exactly what Gate C must not expose.
    authority_binding: AuthorityNamespaceBinding
    canonical_repository_root: str
    expected_ledger_path: str | None
    # `contract` binds the exact `LegacyIncidentContract` (conflict domain /
    # environment / bound legacy-history identity) already used to open
    # `read_local_safety_state`/`read_trusted_release_evidence`. Every
    # replay-time history validation inside `acquire_release_only`/
    # `acquire_normal_writer_state` depends on this exact same contract;
    # defaulting silently to the production `CURRENT_LEGACY_INCIDENT_
    # CONTRACT` would make Gate C's own acquisitions diverge from Gate B's
    # already-open contract in any non-production (synthetic-evidence) run.
    contract: LegacyIncidentContract
    # Gate D closed bindings (all optional, defaulted to `None`, so every
    # existing Gate A/B/C construction of this dataclass remains valid
    # unchanged). None of these grants capability by itself -- Gate D's own
    # entry preconditions (a genuine Stage-3K NORMAL_WRITER result) must
    # still pass before any of them is used. There is deliberately no
    # generic `compute_quote_decision`/quote-decision callback field here
    # (MM07-CLAR-003): production Gate D always builds a real
    # `MarketMakerInputV1` and calls the protected, unmodified
    # `evaluate_market_maker_input` directly -- there is no substitutable
    # strategy seam on this runtime at all.
    strategy_instance_id: str | None = None
    minimum_spread_usd: Decimal | None = None
    gate_d_incident_id: str | None = None
    gate_d_capability_reference_id: str | None = None
    # The one narrow write-transport callable Gate D's `NormalWriteAdapter`
    # is ever constructed with. Never a generic HTTP client, never
    # caller-selectable per request -- exactly the same one-adapter-per-gate
    # shape `risk_control.NormalWriteAdapter` already enforces.
    normal_write_transport: Callable[[object], object] | None = None

    def __post_init__(self) -> None:
        if type(self.normal_gate) is not WriterEligibilityGate:
            raise RunnerError(RunnerFailureCode.PROCESS_INSTANCE_ID_INCONSISTENT, detail="normal_gate type")
        if type(self.emergency_gate) is not EmergencyCancelGate:
            raise RunnerError(RunnerFailureCode.PROCESS_INSTANCE_ID_INCONSISTENT, detail="emergency_gate type")
        if self.normal_gate.process_instance_id != self.emergency_gate.process_instance_id:
            raise RunnerError(RunnerFailureCode.PROCESS_INSTANCE_ID_INCONSISTENT, detail="gate mismatch")
        if (
            not callable(self.read_local_safety_state) or not callable(self.send_operation_request)
            or not callable(self.fetch_orderbook) or not callable(self.read_trusted_release_evidence)
        ):
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="runtime callables")
        if type(self.authority_binding) is not AuthorityNamespaceBinding:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="authority_binding type")
        if type(self.canonical_repository_root) is not str or not self.canonical_repository_root:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="canonical_repository_root")
        if self.expected_ledger_path is not None and type(self.expected_ledger_path) is not str:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="expected_ledger_path type")
        if type(self.contract) is not LegacyIncidentContract:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="contract type")


_ROUTE_WIRE_POLICIES = frozenset({"EXPLICIT_EXCHANGE_INDEX", "EMPIRICALLY_BOUND_AUTOROUTE"})
# One immutable route-contract shape covering the active Gate-D CREATE/CANCEL
# routing semantics for a single (subaccount, exchange_index) route.
_ACTIVE_ROUTE_REQUEST_SHAPE_ID = "KALSHI_MM_ACTIVE_GATE_D_ROUTE_V1"

# The exact accepted account-wide authoritative-read source classification.
_ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1 = "KALSHI_DEMO_ACCOUNT_WIDE_AUTHORITATIVE_READ_V1"
_ACCOUNT_WIDE_REQUEST_CLASSIFICATION = "ACCOUNT_WIDE"

# Task-controlled accepted-evidence registry (Correction 03 / DSB-N1-002 /
# DSB-STOP-001).  An evidence identity is "accepted" ONLY when it is a value
# in this frozenset.  This set is changed only by an authorized, reviewed
# code change -- NEVER by a caller-provided argument at run time.  It
# currently holds exactly the two spec-fixed accepted N=1 evidence
# identities named by DSB-N1-002 of the controlling specification:
#   PROJECT_STATE_CHECKPOINT_2026_09_01_KALSHI_DEMO_SUBACCOUNT1_EMPIRICAL_QUALIFICATION.md
#     sha256 = 879d311420d2f6a4e2c20b8f96e8107f3753a30923f0e2afdfb7f5668bcb9068
#   EXECUTABLE_FILL_ISOLATION_RESULT.json
#     sha256 = da301946c745b6ccac321a71e97683375bca9e103b649906c95999bc5587e360
# A future subaccount's route/completeness evidence gets its own identity
# added here by the task that separately accepts it.
_N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256 = (
    "879d311420d2f6a4e2c20b8f96e8107f3753a30923f0e2afdfb7f5668bcb9068"
)
_N1_EXECUTABLE_FILL_ISOLATION_RESULT_SHA256 = (
    "da301946c745b6ccac321a71e97683375bca9e103b649906c95999bc5587e360"
)
# Correction 04 accepted empirical inputs (R1-B03-P01 / R1-B03-P02).
#   P01  KALSHI_DEMO_SUBACCOUNT1_SUBACCOUNT_WIDE_COMPLETENESS_DIAGNOSTIC_01_RESULT.json
#        bytes = 36076 ; sha256 = aeb07275f62ce295a131a07c5d2c9604728be58b416a9ff1d3d7517c8d0d6138
#        -- NEGATIVE completeness evidence: proves that OMITTING exchange_index
#        does NOT prove all-index enumeration.  It may NEVER satisfy a positive
#        completeness / index-domain / settlement predicate.
#   P02  KALSHI_DEMO_SUBACCOUNT1_EXCHANGE_INDEX_DOMAIN_COMPLETENESS_DIAGNOSTIC_02_RESULT.json
#        bytes = 26321 ; sha256 = 2fc189b2a807a6c22ab3e71e41a6cfa66415e3bda87e6c8e66c3eb6e8029c69b
#        -- POSITIVE interface-capability evidence: qualifies the exact dynamic
#        /exchange/status index-domain + explicit per-index orders/fills/
#        positions read capability AND the exact accepted N1 controlled
#        retained-position settlement-reconciliation.  Its HISTORICAL economic
#        rows may NEVER mint current writer eligibility -- current release
#        always requires a fresh dynamically enumerated read set.
_P01_NEGATIVE_COMPLETENESS_EVIDENCE_SHA256 = (
    "aeb07275f62ce295a131a07c5d2c9604728be58b416a9ff1d3d7517c8d0d6138"
)
_P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256 = (
    "2fc189b2a807a6c22ab3e71e41a6cfa66415e3bda87e6c8e66c3eb6e8029c69b"
)
_TASK_CONTROLLED_ACCEPTED_EVIDENCE_SHA256 = frozenset({
    _N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256,
    _N1_EXECUTABLE_FILL_ISOLATION_RESULT_SHA256,
    _P01_NEGATIVE_COMPLETENESS_EVIDENCE_SHA256,
    _P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,
})
# Identities that are NEGATIVE evidence -- present in the outer registry only
# so they can be explicitly RECOGNISED and REFUSED by every positive role.
_NEGATIVE_COMPLETENESS_EVIDENCE_SHA256 = frozenset({
    _P01_NEGATIVE_COMPLETENESS_EVIDENCE_SHA256,
})
# Role-specific accepted-evidence sets.  Registry membership alone is NOT
# sufficient -- every positive predicate consults ONLY its own role set.
#
# Correction 02 (DSB-N1-002 / DSB-STOP-001) narrows these decisively for the
# current N1 domain:
#   * the N1 canonical empirical checkpoint is ROUTE / PRE-STACK evidence only;
#   * the N1 executable-fill-isolation result is ROUTE / PRE-STACK evidence
#     only and is NOT bound into ANY positive completeness role;
#   * ``static_positive_completeness_theorem_evidence`` is EMPTY -- current
#     N1 Path B is UNAVAILABLE.  An empty static positive set is valid and
#     MUST NOT cause a legacy-hash substitution.
_ACCEPTED_ROUTE_EVIDENCE_SHA256 = frozenset({
    _N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256,
})
# DSB-RISK-004 Path B / DSB-N1-002: no accepted static positive completeness
# theorem instance exists for current N1.  The Path-B *structure* remains
# supported (future domains), but nothing is accepted into it now.
_ACCEPTED_STATIC_POSITIVE_COMPLETENESS_EVIDENCE_SHA256: frozenset = frozenset()
_ACCEPTED_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256 = frozenset({
    _P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,
})
_ACCEPTED_SETTLEMENT_RECONCILIATION_EVIDENCE_SHA256 = frozenset({
    _P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,
})
# DSB-DOMAIN-002 / DSB-BUDGET-001.
#
# ``_ACTIVE_EXCHANGE_INDEX_VALUE_MAX`` is a per-VALUE ceiling only: an
# individual validated ``exchange_index`` is a bounded exact non-negative int
# ``0 <= value <= 2147483647``.  It is NOT a P02-derived "highest allowed
# index"; a domain member value of 17 or 2147483647 is perfectly valid.
#
# The number of UNIQUE indices in one current domain is a separate COUNT
# bound: 1..8 inclusive.  A ninth unique index fails closed BEFORE the first
# per-index portfolio traversal (DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED).
# P02 empirically observed [0,1,2,3]; that is a fixture, never a compiled
# domain / allowlist, and no category / ticker determines a shard or index.
_ACTIVE_EXCHANGE_INDEX_VALUE_MAX = 2147483647
_ACTIVE_EXCHANGE_INDEX_ENTRY_MIN = 1
_ACTIVE_EXCHANGE_INDEX_ENTRY_MAX = 8
_ACTIVE_INDEX_DOMAIN_ENUMERATION_SOURCE_V1 = "KALSHI_DEMO_DYNAMIC_EXCHANGE_STATUS_INDEX_DOMAIN_V1"
_ACCEPTED_PROVENANCE_CLASSES = ("PROJECT_EVIDENCE_RECORDED", "INDEPENDENTLY_VERIFIED")

# Private construction key: an ``ActiveDomainAcceptedEvidenceContractV1`` can
# be built ONLY by an in-module onboarding constructor (currently
# ``n1_accepted_evidence_contract``).  A caller cannot construct one directly
# for any domain -- so a future subaccount cannot "self-accept" its own
# evidence by instantiating a dataclass.
_ACCEPTED_EVIDENCE_CONTRACT_KEY = object()


def _canonical_evidence_tuple(
    values: object, *, role_allowed: "frozenset", role: str, allow_empty: bool = False,
) -> "Tuple[str, ...]":
    """Sorted, de-duplicated tuple of 64-hex identities that are ALL present
    in the task-controlled accepted-evidence registry AND in the exact
    ROLE-SPECIFIC accepted set ``role_allowed`` (registry membership alone is
    not sufficient).  A NEGATIVE-evidence identity (e.g. P01) can never
    appear in a positive role.  Anything else -> the contract is invalid
    (fails closed); a caller cannot introduce a new 'accepted' identity here.

    Correction 02: ``allow_empty=True`` permits an EMPTY tuple, which is the
    valid current-N1 state for the static positive completeness role
    (DSB-N1-002).  An empty set never triggers a legacy-hash fallback."""
    if type(values) not in (tuple, list, frozenset, set):
        raise RunnerError(
            RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail=role + " accepted-evidence set type")
    out = sorted({v for v in values})
    if not out:
        if allow_empty:
            return ()
        raise RunnerError(
            RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail=role + " accepted-evidence identity format")
    if any(not _is_hex64(v) for v in out):
        raise RunnerError(
            RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail=role + " accepted-evidence identity format")
    if any(v in _NEGATIVE_COMPLETENESS_EVIDENCE_SHA256 for v in out):
        raise RunnerError(
            RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID,
            detail=role + " accepted-evidence set contains a negative-evidence identity")
    if any(v not in _TASK_CONTROLLED_ACCEPTED_EVIDENCE_SHA256 for v in out):
        raise RunnerError(
            RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID,
            detail=role + " evidence identity not in the task-controlled accepted registry")
    if any(v not in role_allowed for v in out):
        raise RunnerError(
            RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID,
            detail=role + " evidence identity not accepted for this role")
    return tuple(out)


def _validate_retained_bootstrap_position(
    value: object, *, conflict_domain_ref: str,
) -> "Mapping[str, object] | None":
    """Correction 04 R06: an accepted-evidence contract may declare exactly
    one immutable retained-bootstrap-position fact for its domain (ticker,
    exchange_index, floor_contracts, conflict_domain_ref).  ``None`` means the
    domain has no retained bootstrap position.  The historical bootstrap
    inception is NOT rewritten -- this only names the fact that must be
    settlement-reconciled by a fresh current read set before it stops
    contributing to current risk."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise RunnerError(RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail="retained bootstrap position type")
    ticker = value.get("ticker")
    idx = value.get("exchange_index")
    floor_raw = value.get("floor_contracts_fp")
    ref = value.get("conflict_domain_ref")
    if (
        set(value) != {"ticker", "exchange_index", "floor_contracts_fp", "conflict_domain_ref"}
        or type(ticker) is not str or _TICKER_PATTERN.fullmatch(ticker) is None
        or type(idx) is not int or type(idx) is bool or idx < 0
        or type(floor_raw) is not str
        or ref != conflict_domain_ref
    ):
        raise RunnerError(RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail="retained bootstrap position fields")
    try:
        floor = Decimal(floor_raw)
    except InvalidOperation as exc:
        raise RunnerError(RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail="retained bootstrap floor value") from exc
    if not floor.is_finite() or floor <= 0:
        raise RunnerError(RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail="retained bootstrap floor range")
    return {"ticker": ticker, "exchange_index": idx, "floor_contracts_fp": floor_raw, "conflict_domain_ref": ref}


@dataclass(frozen=True, slots=True)
class ActiveDomainAcceptedEvidenceContractV1:
    """DSB-N1-002 / DSB-STOP-001 / DSB-RISK-004: a trusted immutable
    onboarding/config contract that binds -- BEFORE any active Gate-B/C/D run
    -- the exact accepted route-evidence and completeness-evidence identities
    for ONE active execution domain.

    It is not caller-forgeable for an arbitrary domain: it can be built ONLY
    via an in-module onboarding constructor (``n1_accepted_evidence_contract``)
    holding ``_ACCEPTED_EVIDENCE_CONTRACT_KEY``, and every bound identity MUST
    already be in ``_TASK_CONTROLLED_ACCEPTED_EVIDENCE_SHA256`` (changed only
    by a reviewed code change).  A future subaccount has no such onboarding
    constructor / anchor, so its runtime cannot be built and the active path
    fails closed (DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED /
    SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)."""

    environment: str
    account_scope_ref: str
    conflict_domain_ref: str
    subaccount: int
    selected_exchange_index: int
    account_wide_source_classification: str
    accepted_route_evidence_sha256: "Tuple[str, ...]"
    accepted_completeness_evidence_sha256: "Tuple[str, ...]"
    accepted_index_domain_enumeration_evidence_sha256: "Tuple[str, ...]"
    accepted_settlement_reconciliation_evidence_sha256: "Tuple[str, ...]"
    index_domain_enumeration_source: str
    # Correction 06 (BLOCK-05-02): a COUNT bound only -- the maximum number of
    # UNIQUE current exchange indices.  There is NO maximum-index-VALUE field.
    dynamic_exchange_index_entry_max: int
    retained_bootstrap_position: "Mapping[str, object] | None"
    accepted_provenance_class: str
    contract_identity_sha256: str = field(init=False, default="")

    def __init__(
        self, key: object, *, environment: str, account_scope_ref: str, conflict_domain_ref: str,
        subaccount: int, selected_exchange_index: int, account_wide_source_classification: str,
        accepted_route_evidence_sha256: "Tuple[str, ...]",
        accepted_completeness_evidence_sha256: "Tuple[str, ...]",
        accepted_index_domain_enumeration_evidence_sha256: "Tuple[str, ...]",
        accepted_settlement_reconciliation_evidence_sha256: "Tuple[str, ...]",
        index_domain_enumeration_source: str,
        dynamic_exchange_index_entry_max: int,
        retained_bootstrap_position: "Mapping[str, object] | None",
        accepted_provenance_class: str,
    ) -> None:
        if key is not _ACCEPTED_EVIDENCE_CONTRACT_KEY:
            raise RunnerError(
                RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID,
                detail="accepted-evidence contract has no in-module onboarding constructor for this domain")
        if (
            environment != "KALSHI_DEMO"
            or type(account_scope_ref) is not str or not account_scope_ref
            or type(conflict_domain_ref) is not str or not conflict_domain_ref
            or type(subaccount) is not int or type(subaccount) is bool or not 0 <= subaccount <= 63
            or type(selected_exchange_index) is not int or type(selected_exchange_index) is bool
            or not 0 <= selected_exchange_index <= _ACTIVE_EXCHANGE_INDEX_VALUE_MAX
            or account_wide_source_classification != _ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1
            or index_domain_enumeration_source != _ACTIVE_INDEX_DOMAIN_ENUMERATION_SOURCE_V1
            # Correction 06: exact built-in int, bool prohibited, count bound in
            # [1, 8].  The selected index is validated later as a MEMBER of the
            # observed domain -- never as ``<= dynamic_exchange_index_entry_max``.
            or type(dynamic_exchange_index_entry_max) is not int
            or type(dynamic_exchange_index_entry_max) is bool
            or not _ACTIVE_EXCHANGE_INDEX_ENTRY_MIN <= dynamic_exchange_index_entry_max <= _ACTIVE_EXCHANGE_INDEX_ENTRY_MAX
            or accepted_provenance_class not in _ACCEPTED_PROVENANCE_CLASSES
        ):
            raise RunnerError(
                RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID, detail="contract fields")
        route = _canonical_evidence_tuple(
            accepted_route_evidence_sha256, role_allowed=_ACCEPTED_ROUTE_EVIDENCE_SHA256, role="route")
        # Correction 02 DSB-N1-002 / DSB-RISK-004: the static positive
        # completeness role is a SEPARATE, currently EMPTY accepted set.  An
        # empty tuple is valid and is the current N1 state (Path B UNAVAILABLE).
        completeness = _canonical_evidence_tuple(
            accepted_completeness_evidence_sha256,
            role_allowed=_ACCEPTED_STATIC_POSITIVE_COMPLETENESS_EVIDENCE_SHA256,
            role="static-positive-completeness-theorem", allow_empty=True)
        index_domain = _canonical_evidence_tuple(
            accepted_index_domain_enumeration_evidence_sha256,
            role_allowed=_ACCEPTED_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256, role="index-domain-enumeration")
        settlement = _canonical_evidence_tuple(
            accepted_settlement_reconciliation_evidence_sha256,
            role_allowed=_ACCEPTED_SETTLEMENT_RECONCILIATION_EVIDENCE_SHA256, role="settlement-reconciliation")
        retained = _validate_retained_bootstrap_position(retained_bootstrap_position, conflict_domain_ref=conflict_domain_ref)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "account_scope_ref", account_scope_ref)
        object.__setattr__(self, "conflict_domain_ref", conflict_domain_ref)
        object.__setattr__(self, "subaccount", subaccount)
        object.__setattr__(self, "selected_exchange_index", selected_exchange_index)
        object.__setattr__(self, "account_wide_source_classification", account_wide_source_classification)
        object.__setattr__(self, "accepted_route_evidence_sha256", route)
        object.__setattr__(self, "accepted_completeness_evidence_sha256", completeness)
        object.__setattr__(self, "accepted_index_domain_enumeration_evidence_sha256", index_domain)
        object.__setattr__(self, "accepted_settlement_reconciliation_evidence_sha256", settlement)
        object.__setattr__(self, "index_domain_enumeration_source", index_domain_enumeration_source)
        object.__setattr__(self, "dynamic_exchange_index_entry_max", dynamic_exchange_index_entry_max)
        object.__setattr__(self, "retained_bootstrap_position", retained)
        object.__setattr__(self, "accepted_provenance_class", accepted_provenance_class)
        object.__setattr__(self, "contract_identity_sha256", sha256_hex(canonical_json_bytes({
            # Correction 06: bumped schema tag + the count-bound key so the
            # contract identity commits to the NEW field name/value.
            "schema": "ARB_ACTIVE_DOMAIN_ACCEPTED_EVIDENCE_CONTRACT_V3",
            "environment": environment,
            "account_scope_ref": account_scope_ref,
            "conflict_domain_ref": conflict_domain_ref,
            "subaccount": subaccount,
            "selected_exchange_index": selected_exchange_index,
            "account_wide_source_classification": account_wide_source_classification,
            "accepted_route_evidence_sha256": list(route),
            "accepted_completeness_evidence_sha256": list(completeness),
            "accepted_index_domain_enumeration_evidence_sha256": list(index_domain),
            "accepted_settlement_reconciliation_evidence_sha256": list(settlement),
            "index_domain_enumeration_source": index_domain_enumeration_source,
            "dynamic_exchange_index_entry_max": dynamic_exchange_index_entry_max,
            "retained_bootstrap_position": retained,
            "accepted_provenance_class": accepted_provenance_class,
        })))

    def applies_to(self, domain_binding: "ExecutionDomainBindingV1") -> bool:
        return (
            self.environment == domain_binding.environment
            and self.account_scope_ref == domain_binding.account_scope_ref
            and self.conflict_domain_ref == domain_binding.conflict_domain_ref
            and self.subaccount == domain_binding.subaccount
            and self.selected_exchange_index == domain_binding.exchange_index
        )


def n1_accepted_evidence_contract(
    domain_binding: "ExecutionDomainBindingV1",
) -> ActiveDomainAcceptedEvidenceContractV1:
    """Explicit N=1 onboarding object (NOT generic active code).

    Correction 02 (DSB-N1-002 / DSB-STOP-001): binds ONLY the N1 canonical
    empirical checkpoint into the ROUTE / pre-stack role.  The
    executable-fill-isolation result is route/pre-stack evidence and is NOT
    bound into any positive completeness role.  The static positive
    completeness set is EMPTY -- current N1 Path B is UNAVAILABLE and current
    writer-release completeness is a fresh trusted Path A read-set only.
    Raises DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED for any non-N=1 domain."""
    if (
        type(domain_binding) is not ExecutionDomainBindingV1
        or domain_binding.environment != "KALSHI_DEMO"
        or domain_binding.account_scope_ref != CURRENT_ACCOUNT_SCOPE_REF
        or domain_binding.subaccount != 1
        or domain_binding.exchange_index != 0
    ):
        raise RunnerError(
            RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED,
            detail="N=1 accepted-evidence contract requested for a non-N=1 domain")
    return ActiveDomainAcceptedEvidenceContractV1(
        _ACCEPTED_EVIDENCE_CONTRACT_KEY,
        environment=domain_binding.environment,
        account_scope_ref=domain_binding.account_scope_ref,
        conflict_domain_ref=domain_binding.conflict_domain_ref,
        subaccount=1,
        selected_exchange_index=0,
        account_wide_source_classification=_ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
        accepted_route_evidence_sha256=(_N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256,),
        # DSB-N1-002: static_positive_completeness_theorem_evidence = EMPTY.
        accepted_completeness_evidence_sha256=(),
        accepted_index_domain_enumeration_evidence_sha256=(
            _P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,
        ),
        accepted_settlement_reconciliation_evidence_sha256=(
            _P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,
        ),
        index_domain_enumeration_source=_ACTIVE_INDEX_DOMAIN_ENUMERATION_SOURCE_V1,
        # Correction 06 (BLOCK-05-02): a COUNT bound of exactly 8 unique
        # current exchange indices.  There is no maximum-index-value concept
        # for current N1; P02's observed [0,1,2,3] is a fixture only, and the
        # fifth through eighth stable index is traversed automatically.
        dynamic_exchange_index_entry_max=_ACTIVE_EXCHANGE_INDEX_ENTRY_MAX,
        # DSB-N1-003 / P02: the historical controlled N=1 retained position.
        retained_bootstrap_position={
            "ticker": "KXAAAGASD-26SEP02-4.1200",
            "exchange_index": 0,
            "floor_contracts_fp": "1.00",
            "conflict_domain_ref": domain_binding.conflict_domain_ref,
        },
        accepted_provenance_class="PROJECT_EVIDENCE_RECORDED",
    )


@dataclass(frozen=True, slots=True)
class ActiveRouteQualificationV1:
    """DSB-QUOTE-004 / DSB-N1-001 / DSB-FUTURE-003 / DSB-STOP-002: an
    explicit, immutable, qualified route-policy contract bound BEFORE Gate D.

    The active execution code never infers a route policy from
    ``subaccount == 1`` (or any literal).  A route policy is valid only when
    this contract's provenance/qualification identity proves the selected
    ``exchange_index_wire_policy`` applies to the exact
    environment/account-scope/subaccount/exchange_index/operation-request
    shape.  A future subaccount without its own qualification is
    ``DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED``."""

    environment: str
    account_scope_ref: str
    subaccount: int
    exchange_index: int
    operation_request_shape_id: str
    exchange_index_wire_policy: str  # one of _ROUTE_WIRE_POLICIES
    qualification_evidence_identity_sha256: str  # identity of an accepted evidence artifact (64 hex)
    provenance_class: str  # PROJECT_EVIDENCE_RECORDED | INDEPENDENTLY_VERIFIED

    def __post_init__(self) -> None:
        if (
            self.environment != "KALSHI_DEMO"
            or type(self.account_scope_ref) is not str or not self.account_scope_ref
            or type(self.subaccount) is not int or type(self.subaccount) is bool or not 0 <= self.subaccount <= 63
            or type(self.exchange_index) is not int or type(self.exchange_index) is bool or self.exchange_index < 0
            or self.operation_request_shape_id != _ACTIVE_ROUTE_REQUEST_SHAPE_ID
            or self.exchange_index_wire_policy not in _ROUTE_WIRE_POLICIES
            or type(self.qualification_evidence_identity_sha256) is not str
            or len(self.qualification_evidence_identity_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.qualification_evidence_identity_sha256)
            or self.provenance_class not in ("PROJECT_EVIDENCE_RECORDED", "INDEPENDENTLY_VERIFIED")
        ):
            raise RunnerError(RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED, detail="route qualification malformed")

    def applies_to(self, *, domain_binding: ExecutionDomainBindingV1, operation_request_shape_id: str) -> bool:
        return (
            self.operation_request_shape_id == operation_request_shape_id
            and self.environment == domain_binding.environment
            and self.account_scope_ref == domain_binding.account_scope_ref
            and self.subaccount == domain_binding.subaccount
            and self.exchange_index == domain_binding.exchange_index
        )


def _require_active_route_qualified(runtime: "ExperimentRunnerRuntimeV2") -> None:
    """DSB-STOP-002: an active route must be explicitly qualified for its
    exact domain before permit issuance / transport."""
    rq = runtime.route_qualification
    if type(rq) is not ActiveRouteQualificationV1 or not rq.applies_to(
        domain_binding=runtime.domain_binding, operation_request_shape_id=_ACTIVE_ROUTE_REQUEST_SHAPE_ID,
    ):
        raise RunnerError(RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED, detail="active route not qualified for this domain")
    _require_active_accepted_evidence_contract(
        runtime.accepted_evidence_contract, domain_binding=runtime.domain_binding, route_qualification=rq,
    )


def _require_active_accepted_evidence_contract(
    contract: "ActiveDomainAcceptedEvidenceContractV1 | None",
    *,
    domain_binding: "ExecutionDomainBindingV1",
    route_qualification: "ActiveRouteQualificationV1",
) -> None:
    """Correction 03 F4: the route qualification's evidence identity +
    provenance class must be members of a separately bound, trusted,
    domain-scoped ``ActiveDomainAcceptedEvidenceContractV1`` -- not merely a
    syntactically valid 64-hex string.  A future subaccount without an
    accepted route-evidence contract is ``DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED``
    before permit issuance / transport."""
    if type(contract) is not ActiveDomainAcceptedEvidenceContractV1 or not contract.applies_to(domain_binding):
        raise RunnerError(
            RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED,
            detail="accepted-evidence contract missing or does not apply to this active domain")
    if (
        route_qualification.qualification_evidence_identity_sha256 not in contract.accepted_route_evidence_sha256
        or route_qualification.provenance_class != contract.accepted_provenance_class
    ):
        raise RunnerError(
            RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED,
            detail="route qualification evidence identity/provenance not separately accepted for this domain")


@dataclass(frozen=True, slots=True)
class ExperimentRunnerRuntimeV2:
    """Active revision-2 execution-domain runtime (DSB-WRITER-003 / DSB-RUN-001).

    Preserves every non-legacy ``ExperimentRunnerRuntimeV1`` dependency field
    with the same names/types/semantics, but replaces the V1 legacy contract
    field with an immutable ``ExecutionDomainBindingV1`` + matching
    ``ActiveExecutionDomainContractV1``.  It cannot define, store, default,
    embed, or indirectly carry ``LegacyIncidentContract``, and it does not
    accept an independently caller-selected Gate-D incident id or active
    writer-proof id -- both derive only from ``active_contract``.
    """

    normal_gate: WriterEligibilityGate
    emergency_gate: EmergencyCancelGate
    read_local_safety_state: Callable[[], OpenResult]
    read_trusted_release_evidence: Callable[[], "TrustedReleaseEvidenceReadResultV1"]
    send_operation_request: Callable[
        [RunnerOperation, PreparedRunnerOperationRequestV1, OperationDeadlineV1], RawOperationResponseV1
    ]
    fetch_orderbook: Callable[[str, OperationDeadlineV1], object]
    monotonic_clock_ns: Callable[[], int]
    wall_clock: Callable[[], datetime]
    uuid_factory: Callable[[], "uuid.UUID"]
    risk_config: RiskLimitConfigV1 | None
    experiment_absolute_end_monotonic_ns: int
    authority_binding: AuthorityNamespaceBinding
    canonical_repository_root: str
    expected_ledger_path: str | None
    domain_binding: ExecutionDomainBindingV1
    active_contract: ActiveExecutionDomainContractV1
    route_qualification: "ActiveRouteQualificationV1 | None" = None
    accepted_evidence_contract: "ActiveDomainAcceptedEvidenceContractV1 | None" = None
    strategy_instance_id: str | None = None
    minimum_spread_usd: Decimal | None = None
    gate_d_capability_reference_id: str | None = None
    normal_write_transport: Callable[[object], object] | None = None
    # Correction 02 DSB-DYN-004: the ONLY synthetic-current-read seam.  It is
    # ``None`` for every production runtime -- ``build_active_experiment_
    # runner_runtime_v2`` (the production factory) has NO parameter for it, so
    # production Stage 3E always binds ``_LiveTrustedDynamicReadAcquirerV2``.
    # A dedicated module-private test factory
    # (``_build_active_experiment_runner_runtime_v2_for_test``) is the only
    # thing that may set it, and only to a ``_FakeTrustedDynamicReadAcquirerV2``.
    # It is not an arbitrary acquirer/callback slot.
    trusted_dynamic_read_acquirer_test_seam: object | None = None

    def __post_init__(self) -> None:
        if type(self.normal_gate) is not WriterEligibilityGate:
            raise RunnerError(RunnerFailureCode.PROCESS_INSTANCE_ID_INCONSISTENT, detail="normal_gate type")
        if type(self.emergency_gate) is not EmergencyCancelGate:
            raise RunnerError(RunnerFailureCode.PROCESS_INSTANCE_ID_INCONSISTENT, detail="emergency_gate type")
        if self.normal_gate.process_instance_id != self.emergency_gate.process_instance_id:
            raise RunnerError(RunnerFailureCode.PROCESS_INSTANCE_ID_INCONSISTENT, detail="gate mismatch")
        if (
            not callable(self.read_local_safety_state) or not callable(self.send_operation_request)
            or not callable(self.fetch_orderbook) or not callable(self.read_trusted_release_evidence)
        ):
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="runtime callables")
        if type(self.authority_binding) is not AuthorityNamespaceBinding:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="authority_binding type")
        if type(self.canonical_repository_root) is not str or not self.canonical_repository_root:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="canonical_repository_root")
        if self.expected_ledger_path is not None and type(self.expected_ledger_path) is not str:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="expected_ledger_path type")
        # An ``ExperimentRunnerRuntimeV2`` may never carry a legacy contract in
        # any field: a ``LegacyIncidentContract`` presented anywhere fails
        # during local construction, before repository-state release
        # evaluation and before venue access (DSB-WRITER-003).
        for value in (self.domain_binding, self.active_contract, self.risk_config,
                      self.accepted_evidence_contract,
                      self.strategy_instance_id, self.minimum_spread_usd,
                      self.gate_d_capability_reference_id, self.normal_write_transport):
            if type(value) is LegacyIncidentContract:
                raise RunnerError(
                    RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED,
                    detail=FailureCode.ACTIVE_PATH_LEGACY_CONTRACT_REJECTED.value,
                )
        if type(self.domain_binding) is not ExecutionDomainBindingV1:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="domain_binding type")
        if type(self.active_contract) is not ActiveExecutionDomainContractV1:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="active_contract type")
        b, c = self.domain_binding, self.active_contract
        if (
            b.binding_id != c.domain_binding_id
            or b.binding_sha256 != c.domain_binding_sha256
            or b.venue != c.venue
            or b.environment != c.environment
            or b.account_scope_ref != c.account_scope_ref
            or b.subaccount != c.subaccount
            or b.exchange_index != c.exchange_index
            or b.conflict_domain_ref != c.conflict_domain_ref
        ):
            raise RunnerError(
                RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED,
                detail=FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH.value,
            )
        # DSB-QUOTE-004 / DSB-STOP-002: an active runtime is unusable without
        # an explicit route qualification that applies to its exact domain.
        # There is NO N=1 (or any) literal route-selection rule in this code.
        if type(self.route_qualification) is not ActiveRouteQualificationV1 or not self.route_qualification.applies_to(
            domain_binding=self.domain_binding, operation_request_shape_id=_ACTIVE_ROUTE_REQUEST_SHAPE_ID,
        ):
            raise RunnerError(
                RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED,
                detail="route_qualification missing or does not apply to this domain",
            )
        # Correction 03 / DSB-N1-002 / DSB-STOP-001: the accepted route- and
        # completeness-evidence identities MUST be bound BEFORE this run by a
        # trusted immutable acceptance contract for this exact active domain.
        # The route qualification's evidence identity + provenance class are
        # only valid when they are in that separately bound accepted set --
        # a syntactically valid 64-hex string is not enough.
        _require_active_accepted_evidence_contract(
            self.accepted_evidence_contract, domain_binding=self.domain_binding,
            route_qualification=self.route_qualification,
        )
        # DSB-DYN-004: the production constructor MUST NOT accept an arbitrary
        # acquirer/callback.  The only accepted non-``None`` value is a
        # ``_FakeTrustedDynamicReadAcquirerV2`` supplied by the module-private
        # test factory.
        seam = self.trusted_dynamic_read_acquirer_test_seam
        if seam is not None and not isinstance(seam, _FakeTrustedDynamicReadAcquirerV2):
            raise RunnerError(
                RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID,
                detail="ExperimentRunnerRuntimeV2 does not accept an arbitrary trusted-read acquirer/callback",
            )

    @property
    def gate_d_incident_id(self) -> str:
        """Derived only from the active contract; never caller-selectable."""
        return self.active_contract.incident_id

    @property
    def gate_d_writer_proof_id(self) -> str:
        return self.active_contract.writer_proof_id

    @property
    def contract(self):  # pragma: no cover - explicit non-legacy guard
        raise RunnerError(
            RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED,
            detail=FailureCode.ACTIVE_PATH_LEGACY_CONTRACT_REJECTED.value,
        )

    def active_venue_binding_v2(
        self, *, exchange_index_wire_policy: str, adapter_payload_schema_id: str,
    ) -> VenueBindingV2:
        return VenueBindingV2(
            domain_binding=self.domain_binding,
            exchange_index_wire_policy=exchange_index_wire_policy,
            adapter_payload_schema_id=adapter_payload_schema_id,
        )


def build_active_experiment_runner_runtime_v2(
    *,
    normal_gate: WriterEligibilityGate,
    emergency_gate: EmergencyCancelGate,
    send_operation_request,
    fetch_orderbook,
    monotonic_clock_ns,
    wall_clock,
    uuid_factory,
    risk_config: RiskLimitConfigV1 | None,
    experiment_absolute_end_monotonic_ns: int,
    authority_binding: AuthorityNamespaceBinding,
    canonical_repository_root: str,
    expected_ledger_path: str | None,
    domain_binding: ExecutionDomainBindingV1,
    active_contract: ActiveExecutionDomainContractV1,
    route_qualification: ActiveRouteQualificationV1,
    accepted_evidence_contract: ActiveDomainAcceptedEvidenceContractV1,
    strategy_instance_id: str | None = None,
    minimum_spread_usd: Decimal | None = None,
    gate_d_capability_reference_id: str | None = None,
    normal_write_transport=None,
) -> ExperimentRunnerRuntimeV2:
    """Build an active runtime whose Gate-B local/trusted reads are bound to
    the active revision-2 helpers with the exact same ``active_contract``
    (DSB-WRITER-005: ``read_local_safety_state`` / ``read_trusted_release_
    evidence`` MUST be the active helpers, not the legacy projection path)."""
    if type(active_contract) is LegacyIncidentContract:
        raise RunnerError(
            RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED,
            detail=FailureCode.ACTIVE_PATH_LEGACY_CONTRACT_REJECTED.value,
        )

    def _read_local_safety_state() -> OpenResult:
        return read_active_local_safety_state_v1(
            authority_binding,
            canonical_repository_root=canonical_repository_root,
            active_contract=active_contract,
            expected_ledger_path=expected_ledger_path,
        )

    def _read_trusted_release_evidence() -> "TrustedReleaseEvidenceReadResultV1":
        return read_active_trusted_release_evidence_projection_v1(
            authority_binding,
            canonical_repository_root=canonical_repository_root,
            active_contract=active_contract,
            expected_ledger_path=expected_ledger_path,
        )

    return ExperimentRunnerRuntimeV2(
        normal_gate=normal_gate,
        emergency_gate=emergency_gate,
        read_local_safety_state=_read_local_safety_state,
        read_trusted_release_evidence=_read_trusted_release_evidence,
        send_operation_request=send_operation_request,
        fetch_orderbook=fetch_orderbook,
        monotonic_clock_ns=monotonic_clock_ns,
        wall_clock=wall_clock,
        uuid_factory=uuid_factory,
        risk_config=risk_config,
        experiment_absolute_end_monotonic_ns=experiment_absolute_end_monotonic_ns,
        authority_binding=authority_binding,
        canonical_repository_root=canonical_repository_root,
        expected_ledger_path=expected_ledger_path,
        domain_binding=domain_binding,
        active_contract=active_contract,
        route_qualification=route_qualification,
        accepted_evidence_contract=accepted_evidence_contract,
        strategy_instance_id=strategy_instance_id,
        minimum_spread_usd=minimum_spread_usd,
        gate_d_capability_reference_id=gate_d_capability_reference_id,
        normal_write_transport=normal_write_transport,
    )


@dataclass(frozen=True, slots=True)
class ExperimentRunnerInvocationV1:
    """Exact bound invocation identity (Spec 03 ER-ARCH-001, narrowed to the
    fields Gate B's read-only phase actually needs)."""

    invocation_id: str
    market_ticker: str
    incident_id: str
    writer_proof_id: str

    def __post_init__(self) -> None:
        for name in ("invocation_id", "market_ticker", "incident_id", "writer_proof_id"):
            value = getattr(self, name)
            if type(value) is not str or value == "":
                raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail=name)
        if _TICKER_PATTERN.fullmatch(self.market_ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="invocation ticker grammar")


# Module-private issuance sentinel (Marco Blocker 01). Never exported, never
# persisted -- a plain in-memory object identity that only
# `_issue_pre_release_read_capability` ever passes to the constructor.
_CAPABILITY_ISSUANCE_KEY = object()


class PreReleaseReadCapabilityV1:
    """Closed Demo-only, REST-only, read-only capability (ER04-PRE-002).

    Public surface is exactly six methods plus `requests_consumed`. No
    method here can be bent into a write request: `get_market_orderbook`
    exclusively calls the injected `fetch_orderbook` (bound in production to
    the accepted authenticated `orderbook.py` entrypoint); the other five
    exclusively call `prepare_runner_operation_request`, which only knows
    about the five closed GET operations and raises
    `OPERATION_REQUEST_POLICY_VIOLATION` for anything else -- there is no
    code path from any public method of this class to CREATE_ORDER_V2 or
    CANCEL_ORDER_V2.

    Construction is closed (Marco Blocker 01): the ordinary constructor
    requires a module-private issuance key that only `_issue_pre_release_
    read_capability` -- called exclusively by `run_pre_release_read_phase`
    after Stage 3C's local release-impossibility gate has already passed
    -- ever supplies. A caller that imports this class and calls
    `PreReleaseReadCapabilityV1(process_instance_id=..., ticker=..., runtime=...)`
    directly (without the key) cannot construct a usable instance; it fails
    closed with `CAPABILITY_ISSUANCE_UNAUTHORIZED` before any budget/
    transport/credential activity is possible. This is process-local
    admission control, not persistence or replayable authority -- nothing
    is written anywhere, and the key is a plain in-memory sentinel object
    discarded with the module.

    GET_ORDER/GET_FILLS target authorization (Marco Blocker 02): this
    object also owns a private, closed authoritative order-ID set, which
    only successful `get_orders()` row validation may extend. `get_order`/
    `get_fills` check membership in that set -- before reserving budget,
    before signing, before transport -- and reject any ID that is not an
    exact, already-admitted authoritative identity. There is no public
    method that inserts into the set directly.
    """

    __slots__ = (
        "__process_instance_id", "__ticker", "__runtime", "__consumed",
        "__lock", "__ordinal", "__authoritative_order_ids", "__budget_max", "__exhausted_code",
        "__domain_subaccount", "__domain_exchange_index",
    )

    def __init__(
        self, issuance_key: object, *, process_instance_id: str, ticker: str,
        runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
        budget_max: int = PRE_RELEASE_READ_REQUEST_MAX,
        exhausted_code: "RunnerFailureCode | None" = None,
        domain_subaccount: int = _SUBACCOUNT,
        domain_exchange_index: int = _EXCHANGE_INDEX,
    ) -> None:
        if issuance_key is not _CAPABILITY_ISSUANCE_KEY:
            raise RunnerError(RunnerFailureCode.CAPABILITY_ISSUANCE_UNAUTHORIZED)
        if type(process_instance_id) is not str or process_instance_id == "":
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="process_instance_id")
        if type(ticker) is not str or _TICKER_PATTERN.fullmatch(ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="capability ticker")
        if type(runtime) not in (ExperimentRunnerRuntimeV1, ExperimentRunnerRuntimeV2):
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="runtime type")
        if type(budget_max) is not int or budget_max <= 0:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="budget_max")
        if type(domain_subaccount) is not int or type(domain_subaccount) is bool or not 0 <= domain_subaccount <= 63:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="domain_subaccount")
        if type(domain_exchange_index) is not int or type(domain_exchange_index) is bool or domain_exchange_index < 0:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="domain_exchange_index")
        self.__process_instance_id = process_instance_id
        self.__ticker = ticker
        self.__runtime = runtime
        self.__domain_subaccount = domain_subaccount
        self.__domain_exchange_index = domain_exchange_index
        self.__consumed = 0
        self.__ordinal = 0
        self.__lock = threading.Lock()
        self.__authoritative_order_ids: set[str] = set()
        self.__budget_max = budget_max
        self.__exhausted_code = exhausted_code or RunnerFailureCode.PRE_RELEASE_READ_BUDGET_EXHAUSTED

    @property
    def requests_consumed(self) -> int:
        with self.__lock:
            return self.__consumed

    def __admit_order_id(self, order_id: str) -> None:
        """Private: the only route by which an order ID becomes an
        authorized GET_ORDER/GET_FILLS target -- called only from within
        `get_orders()` after a row has passed exact schema validation."""

        with self.__lock:
            self.__authoritative_order_ids.add(order_id)

    def __is_authoritative_target(self, order_id: str) -> bool:
        with self.__lock:
            return order_id in self.__authoritative_order_ids

    def _reserve(self) -> int:
        with self.__lock:
            if self.__consumed >= self.__budget_max:
                raise RunnerError(self.__exhausted_code)
            self.__consumed += 1
            self.__ordinal += 1
            return self.__ordinal

    def _deadline(self, operation: RunnerOperation, ordinal: int) -> OperationDeadlineV1:
        return OperationDeadlineV1.create(
            process_instance_id=self.__process_instance_id,
            operation_name=operation.value,
            request_ordinal=ordinal,
            started_monotonic_ns=self.__runtime.monotonic_clock_ns(),
            experiment_absolute_end_monotonic_ns=self.__runtime.experiment_absolute_end_monotonic_ns,
            uuid_factory=self.__runtime.uuid_factory,
        )

    def _send_generic(
        self, operation: RunnerOperation, *, path_parameters: Mapping[str, str],
        ticker: str | None = None, order_id: str | None = None, cursor: str | None = None,
    ) -> Tuple[object, OperationDeadlineV1]:
        if operation not in PRE_RELEASE_READ_OPERATIONS or operation not in _GENERIC_REQUEST_OPERATIONS:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_OPERATION_PROHIBITED, detail=str(operation))
        ordinal = self._reserve()
        deadline = self._deadline(operation, ordinal)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.BEFORE_PREPARATION)
        prepared = prepare_runner_operation_request(
            operation, path_parameters=path_parameters, ticker=ticker, order_id=order_id,
            cursor=cursor, request_ordinal=ordinal, uuid_factory=self.__runtime.uuid_factory,
            subaccount=self.__domain_subaccount, exchange_index=self.__domain_exchange_index,
        )
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_PREPARATION)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SIGNING)
        raw = self.__runtime.send_operation_request(operation, prepared, deadline)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_TRANSPORT)
        parsed = _decode_and_validate_runner_json_response(
            operation, raw_response=raw, deadline=deadline,
            now_monotonic_ns=self.__runtime.monotonic_clock_ns,
        )
        return parsed, deadline

    # -- the exact six closed read operations -----------------------------

    def get_market(self) -> Mapping[str, object]:
        parsed, deadline = self._send_generic(
            RunnerOperation.GET_MARKET, path_parameters={"ticker": self.__ticker}, ticker=self.__ticker,
        )
        result = _parse_market(
            parsed, expected_ticker=self.__ticker,
            expected_exchange_index=self.__domain_exchange_index,
        )
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SCHEMA_VALIDATION)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return result

    def get_market_orderbook(self) -> object:
        if RunnerOperation.GET_MARKET_ORDERBOOK not in PRE_RELEASE_READ_OPERATIONS:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_OPERATION_PROHIBITED)
        ordinal = self._reserve()
        deadline = self._deadline(RunnerOperation.GET_MARKET_ORDERBOOK, ordinal)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.BEFORE_PREPARATION)
        result = self.__runtime.fetch_orderbook(self.__ticker, deadline)
        if isinstance(result, OrderBookHalt):
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail=f"orderbook halt {result.code.value}")
        if type(result) is not KalshiNativeOrderBookSnapshot:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="orderbook return type")
        if result.market_ticker != self.__ticker:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="orderbook ticker mismatch")
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return result

    def get_orders(self, *, cursor: str | None = None) -> Mapping[str, object]:
        """Validates every row (Marco Blocker 03) and admits each
        successfully-validated order's exact ID into the private
        authoritative target set (Marco Blocker 02) -- the only place in
        this class that mutates that set."""

        parsed, deadline = self._send_generic(
            RunnerOperation.GET_ORDERS, path_parameters={}, ticker=self.__ticker, cursor=cursor,
        )
        obj = _require_dict(parsed, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="get_orders top level")
        orders_raw = _require_field(obj, "orders", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        if type(orders_raw) is not list:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="orders type")
        response_cursor = _require_field(obj, "cursor", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        if response_cursor is not None and type(response_cursor) is not str:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="cursor type")
        validated: list[WorkingOrderV1] = []
        for row in orders_raw:
            order = _working_order_from_raw(
                row, expected_ticker=self.__ticker,
                expected_subaccount=self.__domain_subaccount,
                expected_exchange_index=self.__domain_exchange_index,
            )
            if order is not None:
                validated.append(order)
                self.__admit_order_id(order.order_id)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SCHEMA_VALIDATION)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return {"orders": tuple(validated), "cursor": response_cursor or ""}

    def get_order(self, order_id: str) -> WorkingOrderV1:
        if type(order_id) is not str or order_id == "":
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="order_id")
        # Authoritative-target-set membership is checked BEFORE budget
        # reservation, signing, or transport (Marco Blocker 02).
        if not self.__is_authoritative_target(order_id):
            raise RunnerError(RunnerFailureCode.ORDER_TARGET_NOT_AUTHORITATIVE, detail=order_id)
        parsed, deadline = self._send_generic(
            RunnerOperation.GET_ORDER, path_parameters={"order_id": order_id}, ticker=self.__ticker,
        )
        obj = _require_dict(parsed, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="get_order top level")
        order_row = _require_dict(
            _require_field(obj, "order", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
            code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="order shape",
        )
        confirmed = _working_order_from_raw(
            order_row, expected_ticker=self.__ticker,
            expected_subaccount=self.__domain_subaccount,
            expected_exchange_index=self.__domain_exchange_index,
        )
        if confirmed is None or confirmed.order_id != order_id:
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="order_id mismatch")
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SCHEMA_VALIDATION)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return confirmed

    def get_fills(self, order_id: str, *, cursor: str | None = None) -> Mapping[str, object]:
        if type(order_id) is not str or order_id == "":
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="order_id")
        # Authoritative-target-set membership is checked BEFORE budget
        # reservation, signing, or transport (Marco Blocker 02).
        if not self.__is_authoritative_target(order_id):
            raise RunnerError(RunnerFailureCode.ORDER_TARGET_NOT_AUTHORITATIVE, detail=order_id)
        parsed, deadline = self._send_generic(
            RunnerOperation.GET_FILLS, path_parameters={}, order_id=order_id, cursor=cursor,
        )
        obj = _require_dict(parsed, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="get_fills top level")
        fills_raw = _require_field(obj, "fills", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        if type(fills_raw) is not list:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="fills type")
        response_cursor = _require_field(obj, "cursor", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        if response_cursor is not None and type(response_cursor) is not str:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="cursor type")
        validated = tuple(
            _fill_from_raw(
                row, expected_ticker=self.__ticker, expected_order_id=order_id,
                expected_subaccount=self.__domain_subaccount,
                expected_exchange_index=self.__domain_exchange_index,
            )
            for row in fills_raw
        )
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SCHEMA_VALIDATION)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return {"fills": validated, "cursor": response_cursor or ""}

    def get_positions(self, *, cursor: str | None = None) -> Mapping[str, object]:
        """Exact GET_POSITIONS top-level schema (Spec 05 ER05-POS-002/003):
        `market_positions`, `event_positions`, and `cursor` are all
        mandatory, non-null, and exact built-in type. `event_positions` is
        validated structurally (each element an exact `dict`) even though
        this one-market strategy does not consume its economics -- the
        field's presence/type is part of the bound schema and is never
        silently ignored as absent."""

        parsed, deadline = self._send_generic(
            RunnerOperation.GET_POSITIONS, path_parameters={}, ticker=self.__ticker, cursor=cursor,
        )
        obj = _require_dict(parsed, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="get_positions top level")

        market_positions_raw = _require_field(obj, "market_positions", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        if type(market_positions_raw) is not list:
            raise RunnerError(RunnerFailureCode.POSITION_TRUTH_UNAVAILABLE, detail="market_positions type")

        event_positions_raw = _require_field(obj, "event_positions", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        if type(event_positions_raw) is not list:
            raise RunnerError(RunnerFailureCode.POSITION_TRUTH_UNAVAILABLE, detail="event_positions type")
        for entry in event_positions_raw:
            _require_dict(entry, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="event_positions row")

        response_cursor = _require_field(obj, "cursor", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        if type(response_cursor) is not str:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="cursor type")

        validated: list[Mapping[str, object]] = []
        for raw in market_positions_raw:
            row = _require_dict(raw, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="position row")
            row_ticker = _require_exact_str(
                _require_field(row, "ticker", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
                code=RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="position ticker type",
            )
            row_subaccount = _require_exact_int(
                _require_field(row, "subaccount", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
                code=RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="position subaccount type",
            )
            row_exchange_index = _require_exact_int(
                _require_field(row, "exchange_index", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
                code=RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="position exchange_index type",
            )
            if row_ticker != self.__ticker or row_subaccount != self.__domain_subaccount or row_exchange_index != self.__domain_exchange_index:
                raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="position scope mismatch")
            validated.append(row)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SCHEMA_VALIDATION)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return {"market_positions": tuple(validated), "cursor": response_cursor}


def _issue_pre_release_read_capability(
    *, process_instance_id: str, ticker: str,
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
) -> PreReleaseReadCapabilityV1:
    """Module-private factory (Marco Blocker 01): the sole route by which a
    usable `PreReleaseReadCapabilityV1` is ever constructed. Called only by
    `run_pre_release_read_phase` / `run_pre_release_read_phase_v2`, and only
    after Stage 3C's local release-impossibility gate has already returned no
    blocking reasons -- i.e. the successful Stage-3C -> Stage-3D transition
    IS the issuance event. A caller cannot reach this factory by importing
    the module; it is not exported and is not part of `__all__`.

    For a revision-2 active runtime the capability's private reads are scoped
    to ``runtime.domain_binding`` (DSB-RUN-002): no literal 0/1 in the active
    request/validation path."""

    if type(runtime) is ExperimentRunnerRuntimeV2:
        return PreReleaseReadCapabilityV1(
            _CAPABILITY_ISSUANCE_KEY, process_instance_id=process_instance_id, ticker=ticker,
            runtime=runtime,
            domain_subaccount=runtime.domain_binding.subaccount,
            domain_exchange_index=runtime.domain_binding.exchange_index,
        )
    return PreReleaseReadCapabilityV1(
        _CAPABILITY_ISSUANCE_KEY, process_instance_id=process_instance_id, ticker=ticker, runtime=runtime,
    )


# ---------------------------------------------------------------------------
# Section 9 -- bounded authoritative-truth collection (Stage 3E) using only
# the closed capability above.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthoritativeReadTruthV1:
    market: Mapping[str, object]
    orderbook: object
    working_orders: Tuple[WorkingOrderV1, ...]
    orders_complete: bool
    bound_order_ids: Tuple[str, ...]
    fills: Tuple[EconomicFillV1, ...]
    fills_complete: bool
    position_state: str  # NO_VENUE_POSITION_ROW | VENUE_POSITION_ROW_OBSERVED | VENUE_POSITION_UNAVAILABLE
    market_positions_raw: Tuple[Mapping[str, object], ...]
    position_corroboration: str  # CORROBORATED | CONFLICT | UNAVAILABLE
    requests_consumed: int


def _position_count_from_row(row: Mapping[str, object]) -> Decimal:
    value = _require_field(row, "position_count_fp", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    if type(value) is not str:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="position_count_fp type")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="position_count_fp value") from exc
    if not parsed.is_finite():
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="position_count_fp finite")
    return parsed


def _corroborate_position(
    *, ticker: str, position_state: str, market_positions_raw: Tuple[Mapping[str, object], ...],
    working_orders: Tuple[WorkingOrderV1, ...], fills: Tuple[EconomicFillV1, ...],
) -> str:
    """Position corroboration is load-bearing (Spec 04/dispatch Section 17):
    venue position truth must actually be cross-checked against an
    independently-derived economic truth (the accepted canonical
    `compute_market_economic_state`, reused rather than a parallel
    interpretation), not merely collected and ignored.

    Returns exactly one of: CORROBORATED, CONFLICT, UNAVAILABLE. A caller
    may only treat exposure as provably bounded when this is CORROBORATED.
    """

    if position_state == "VENUE_POSITION_UNAVAILABLE":
        return "UNAVAILABLE"
    try:
        derived = compute_market_economic_state(ticker, fills, working_orders)
    except RiskControlError:
        return "UNAVAILABLE"
    independent_net = derived.signed_net_position
    if position_state == "NO_VENUE_POSITION_ROW":
        return "CORROBORATED" if independent_net == 0 else "CONFLICT"
    if position_state == "VENUE_POSITION_ROW_OBSERVED":
        if len(market_positions_raw) != 1:
            return "CONFLICT"
        try:
            venue_net = _position_count_from_row(market_positions_raw[0])
        except RunnerError:
            return "UNAVAILABLE"
        return "CORROBORATED" if venue_net == independent_net else "CONFLICT"
    return "UNAVAILABLE"


def _fetch_orders(capability: PreReleaseReadCapabilityV1, *, ticker: str) -> Tuple[Tuple[WorkingOrderV1, ...], bool, Tuple[str, ...]]:
    orders: list[WorkingOrderV1] = []
    order_ids: list[str] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None
    complete = False
    for _page in range(GET_ORDERS_MAX_PAGES):
        page = capability.get_orders(cursor=cursor)
        for working_order in page["orders"]:
            orders.append(working_order)
            order_ids.append(working_order.order_id)
        next_cursor = page["cursor"]
        if not next_cursor:
            complete = True
            break
        if next_cursor in seen_cursors:
            raise RunnerError(RunnerFailureCode.CURSOR_CYCLE_DETECTED, detail="get_orders")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return tuple(orders), complete, tuple(order_ids)


def _fetch_fills_for_order(
    capability: PreReleaseReadCapabilityV1, *, ticker: str, order_id: str,
    fills_by_id: dict[str, EconomicFillV1],
) -> bool:
    seen_cursors: set[str] = set()
    cursor: str | None = None
    complete = False
    for _page in range(GET_FILLS_MAX_PAGES_PER_ORDER):
        page = capability.get_fills(order_id, cursor=cursor)
        for fill in page["fills"]:
            existing = fills_by_id.get(fill.fill_id)
            if existing is None:
                fills_by_id[fill.fill_id] = fill
            elif existing != fill:
                raise RunnerError(RunnerFailureCode.FILL_DUPLICATE_CONFLICT, detail=fill.fill_id)
        next_cursor = page["cursor"]
        if not next_cursor:
            complete = True
            break
        if next_cursor in seen_cursors:
            raise RunnerError(RunnerFailureCode.CURSOR_CYCLE_DETECTED, detail="get_fills")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return complete


def _fetch_positions(capability: PreReleaseReadCapabilityV1, *, ticker: str) -> Tuple[str, Tuple[Mapping[str, object], ...]]:
    rows: list[Mapping[str, object]] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None
    complete = False
    for _page in range(GET_POSITIONS_MAX_PAGES):
        try:
            page = capability.get_positions(cursor=cursor)
        except RunnerError as exc:
            if exc.code is RunnerFailureCode.POSITION_TRUTH_UNAVAILABLE:
                return "VENUE_POSITION_UNAVAILABLE", ()
            raise
        rows.extend(page["market_positions"])  # already validated inside get_positions()
        next_cursor = page["cursor"]
        if not next_cursor:
            complete = True
            break
        if next_cursor in seen_cursors:
            raise RunnerError(RunnerFailureCode.CURSOR_CYCLE_DETECTED, detail="get_positions")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    if not complete:
        return "VENUE_POSITION_UNAVAILABLE", tuple(rows)
    if not rows:
        return "NO_VENUE_POSITION_ROW", ()
    return "VENUE_POSITION_ROW_OBSERVED", tuple(rows)


def collect_authoritative_read_truth(
    capability: PreReleaseReadCapabilityV1, *, ticker: str,
) -> AuthoritativeReadTruthV1:
    """Stage 3E: exercise the closed six-operation capability up to its
    16-request budget and assemble authoritative economic/reconciliation
    truth. Never rewrites protected historical truth -- it only produces
    new, independently-scoped venue evidence for Stage 3F to fold in."""

    market = capability.get_market()
    orderbook = capability.get_market_orderbook()
    working_orders, orders_complete, order_ids = _fetch_orders(capability, ticker=ticker)

    bound_ids = order_ids[:GET_ORDER_MAX_TARGETS]
    if len(order_ids) > GET_ORDER_MAX_TARGETS:
        orders_complete = False

    fills_by_id: dict[str, EconomicFillV1] = {}
    fills_complete = True
    for order_id in bound_ids:
        confirmed = capability.get_order(order_id)  # RunnerOperation.GET_ORDER, exact-target-set only
        if confirmed.order_id != order_id:
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="get_order confirmation")
        page_complete = _fetch_fills_for_order(capability, ticker=ticker, order_id=order_id, fills_by_id=fills_by_id)
        fills_complete = fills_complete and page_complete

    position_state, market_positions_raw = _fetch_positions(capability, ticker=ticker)
    fills = tuple(sorted(fills_by_id.values(), key=lambda item: (item.authoritative_created_time_utc, item.fill_id)))
    position_corroboration = _corroborate_position(
        ticker=ticker, position_state=position_state, market_positions_raw=market_positions_raw,
        working_orders=working_orders, fills=fills,
    )

    return AuthoritativeReadTruthV1(
        market=market,
        orderbook=orderbook,
        working_orders=working_orders,
        orders_complete=orders_complete,
        bound_order_ids=bound_ids,
        fills=fills,
        fills_complete=fills_complete,
        position_state=position_state,
        market_positions_raw=market_positions_raw,
        position_corroboration=position_corroboration,
        requests_consumed=capability.requests_consumed,
    )


# ---------------------------------------------------------------------------
# Section 10 -- Stage 3B/3C local impossibility gate, using the genuinely
# read-only `acquire_local_state(..., acquisition_mode=NORMAL_WRITER)` path
# (execution_ledger.py): it opens authority+ledger under the same exclusive
# lock pair as every other acquisition, computes the SafetyProjection, and
# immediately closes -- `OpenResult.handle` is always `None` for this mode,
# so no restricted session, writer session, or other durable capability is
# ever retained or created by this read.
# ---------------------------------------------------------------------------

LOCAL_GATE_HISTORICAL_INCIDENT_CONTEXT = CURRENT_LEGACY_INCIDENT_CONTRACT


# Restart classifications that are definitively bad (integrity/schema/
# storage failure or an incomplete legacy history) and therefore always
# locally block release. `UNRESOLVED_WRITE_HELD` and `SAFE_NO_WRITE_
# CAPABILITY` are deliberately excluded: a writer proof that is durably
# `HELD` (not yet `RELEASED`, since release itself only happens later, at
# Gate C) is the ordinary, expected pre-release state -- `UNRESOLVED_
# WRITE_HELD` is what every genuinely release-capable ledger reports here,
# not a failure. Treating it as blocking would make Stage 3D unreachable
# in every realistic scenario.
_BLOCKING_RESTART_CLASSIFICATIONS = frozenset({
    RestartClassification.AUTHORITY_INTEGRITY_FAILURE,
    RestartClassification.AUTHORITY_LEDGER_ROLLBACK_FAILURE,
    RestartClassification.LEDGER_INTEGRITY_FAILURE,
    RestartClassification.SCHEMA_UNSUPPORTED,
    RestartClassification.CONCURRENT_WRITER_BLOCKED,
    RestartClassification.LEGACY_HISTORY_INCOMPLETE,
    RestartClassification.LEDGER_IDENTITY_FAILURE,
    RestartClassification.STORAGE_UNAVAILABLE,
})


_ACTIVE_LOCAL_COMPLETENESS_VALUES = frozenset({
    "COMPLETE_CONTROLLED_FROM_INCEPTION", "COMPLETE_KNOWN_NONEMPTY_PRESTACK",
})


def _local_impossibility_reasons(
    opened: OpenResult, *, writer_proof_id: str,
    allowed_completeness: frozenset = frozenset({"COMPLETE"}),
) -> Tuple[str, ...]:
    """Evaluate the full local release-impossibility predicate set (Spec 04
    ER04-PRE-004; dispatch Implementation-02 Section 8) against a
    `SafetyProjection` obtained from the read-only local-state open.
    Returns an empty tuple only when release has NOT already been
    disproven by durable facts (i.e. the pre-release read phase may
    proceed); any nonempty tuple means Stage 3C must stop before Stage 3D
    -- before capability issuance, credential resolution, signing, or any
    venue transport/budget consumption.

    ``allowed_completeness`` defaults to the legacy single ``{"COMPLETE"}``
    set (V1 behaviour byte-identical).  The revision-2 active path passes
    the two accepted bootstrap-completeness values instead.
    """

    if opened.projection is None:
        return (f"LOCAL_STATE_UNAVAILABLE:{opened.failure_code.value if opened.failure_code else 'UNKNOWN'}",)
    projection = opened.projection
    reasons: list[str] = []
    if projection.history_completeness not in allowed_completeness:
        reasons.append(f"HISTORY_COMPLETENESS:{projection.history_completeness}")
    if projection.protected_unresolved_legacy_write_count != 0:
        reasons.append("PROTECTED_UNRESOLVED_LEGACY_WRITE_COUNT_NONZERO")
    if projection.unresolved_write_request_ids:
        reasons.append("UNRESOLVED_WRITE_EXISTS")
    if projection.fill_conflicts:
        reasons.append("FILL_IDENTITY_CONFLICT")
    proof_state = projection.writer_proof_state_by_proof_id.get(writer_proof_id)
    if proof_state is None:
        reasons.append("WRITER_PROOF_ABSENT")
    elif proof_state not in ("HELD", "RELEASED"):
        reasons.append(f"WRITER_PROOF_STRUCTURALLY_INCOMPATIBLE:{proof_state}")
    else:
        eligible = projection.writer_proof_release_eligible_by_proof_id.get(writer_proof_id)
        if eligible is not True:
            reasons.append("WRITER_PROOF_NOT_RELEASE_ELIGIBLE")
    if projection.risk_control_state != "SAFE_HELD":
        reasons.append(f"RISK_CONTROL_STATE_NOT_SAFE_HELD:{projection.risk_control_state}")
    if projection.restart_classification in _BLOCKING_RESTART_CLASSIFICATIONS:
        reasons.append(f"RESTART_CLASSIFICATION:{projection.restart_classification.value}")
    return tuple(reasons)


# ---------------------------------------------------------------------------
# Section 11 -- Stage 3F: assemble the exact canonical ReleaseEvaluationStateV1
# input chain from Stage 3E's authoritative read truth. This function never
# acquires RELEASE_ONLY, never evaluates a release, and never issues a
# CurrentProcessReleaseCompletionV1 -- Gate B stops here.
#
# RESOLVED_GATE_A_READ_ONLY_EVIDENCE_GAP (Spec 05 Correction 01; formerly
# documented as an open gap by Implementation 02's
# KNOWN_GATE_A_READ_ONLY_EVIDENCE_GAP finding):
#
# Implementation 02 found that no protected, read-only Gate-A interface
# exposed the exact durable ORDER_OBSERVED/FILL_OBSERVED `event_id` needed
# to populate `order_evidence_event_ids`/`fill_evidence_event_ids`, and so
# always left `reconciled_order_ids`/`reconciled_fill_ids` empty. Spec 05
# resolves this by adding exactly that read-only interface:
# `ledger_binding.read_trusted_release_evidence_projection(...)` returns a
# `TrustedReleaseEvidenceProjectionV1` -- built from the SAME shared
# `_derive_authoritative_release_universe(...)` derivation
# `ReleaseLedgerHandle` uses at Stage 3G, acquired via the existing
# protected `_acquire_normal_writer_candidate(...)` bridge (open/replay/
# close, zero writer sessions, zero appends, zero LockedLedger exposure).
# `_match_trusted_release_evidence` below implements the exact Spec 05
# Section 10 algorithm: a fresh Stage-3E venue fact may only populate
# `reconciled_order_ids`/`reconciled_fill_ids`/the evidence-event-id tuples
# when the COMPLETE fresh active-order/fill identity set exactly equals the
# projection's durable identity set AND every single fresh item produces a
# non-`None` `order_evidence_ref`/`fill_evidence_ref`. Any missing durable
# fact, extra/missing fresh fact, mismatch, or ambiguity leaves those
# fields empty (HOLD/incomplete) exactly as Implementation 02 did -- the
# difference is that a COMPLETE, exact match can now be honestly reconciled
# with real trusted evidence references instead of never at all.
# ---------------------------------------------------------------------------


def _market_data_snapshot(market: Mapping[str, object], orderbook: object) -> Mapping[str, object]:
    snapshot: dict[str, object] = {"ticker": market.get("ticker")}
    reference = market.get("yes_bid_dollars") or market.get("last_price_dollars")
    if type(reference) is str:
        try:
            snapshot["reference_yes_price"] = Decimal(reference)
        except InvalidOperation:
            pass
    return snapshot


class _TrustedMatchStatus(enum.StrEnum):
    """Spec 05 Section 10 Stage-3F match outcome (Implementation 04 Blocker
    02 correction). Mutually exclusive and explicit -- a legitimate
    empty-universe complete match (`COMPLETE_TRUSTED_MATCH` with every
    tuple empty) is structurally distinguishable from "matching never
    proved" (either other member), which Implementation 03's single
    all-empty `_EMPTY_MATCH` object could not express."""

    COMPLETE_TRUSTED_MATCH = "COMPLETE_TRUSTED_MATCH"
    INCOMPLETE_OR_UNAVAILABLE = "INCOMPLETE_OR_UNAVAILABLE"
    IDENTITY_OR_ECONOMIC_CONFLICT = "IDENTITY_OR_ECONOMIC_CONFLICT"


@dataclass(frozen=True, slots=True)
class _TrustedReconciliationMatchV1:
    """Private typed Stage-3F match result. `known_active_order_ids` is
    populated ONLY on `status is COMPLETE_TRUSTED_MATCH` (Implementation 04
    Blocker 01 correction) -- it is never derived from raw, untrusted
    Stage-3E venue output."""

    status: "_TrustedMatchStatus"
    known_active_order_ids: Tuple[str, ...]
    reconciled_order_ids: Tuple[str, ...]
    reconciled_fill_ids: Tuple[str, ...]
    order_evidence_event_ids: Tuple[Tuple[str, str], ...]
    fill_evidence_event_ids: Tuple[Tuple[str, str], ...]
    identity_conflict_ids: Tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.status is _TrustedMatchStatus.COMPLETE_TRUSTED_MATCH


def _incomplete_match() -> _TrustedReconciliationMatchV1:
    return _TrustedReconciliationMatchV1(_TrustedMatchStatus.INCOMPLETE_OR_UNAVAILABLE, (), (), (), (), (), ())


def _conflict_match(identity_conflict_ids: Tuple[str, ...]) -> _TrustedReconciliationMatchV1:
    return _TrustedReconciliationMatchV1(
        _TrustedMatchStatus.IDENTITY_OR_ECONOMIC_CONFLICT, (), (), (), (), (), identity_conflict_ids,
    )


def _match_trusted_release_evidence(
    truth: "AuthoritativeReadTruthV1",
    trusted: TrustedReleaseEvidenceProjectionV1,
) -> _TrustedReconciliationMatchV1:
    """Spec 05 Section 10 deterministic Stage-3F reconciliation algorithm
    (Implementation 04 Blockers 01/02 correction; Implementation 05
    ER05-TRUST-006 directionality correction).

    A successful Stage-3E venue read never itself becomes durable truth
    (ER05-TRUST-005). Only a COMPLETE exact match between the fresh venue
    universe and the projection's durable universe -- every identity
    present on both sides, every single item individually resolving to a
    real projection evidence reference -- returns `COMPLETE_TRUSTED_MATCH`.

    Every other outcome is explicitly classified rather than collapsed into
    one indistinguishable empty result:
      - incomplete venue pagination, OR a required durable identity that is
        simply absent from an otherwise-COMPLETE fresh enumeration ->
        `INCOMPLETE_OR_UNAVAILABLE` (missing data, never treated as a
        fabricated identity conflict merely because the venue result
        omitted it -- ER05-TRUST-006's asymmetric rule: `durable - fresh`
        is incompleteness, not contradiction);
      - the projection's own durable `conflict_ids`, a FRESH identity with
        no durable counterpart at all (a proven fresh-vs-durable
        contradiction: `fresh - durable`), or an identical id whose
        economics disagree (the per-item evidence-ref lookup fails despite
        the id sets matching) -> `IDENTITY_OR_ECONOMIC_CONFLICT` with
        deterministic, secret-safe, sorted, unique conflict identifiers
        derived only from the conflict category and the exact public
        order/fill id. A proven conflict is never erased merely because a
        durable identity is also missing on the same side (dispatch
        Section 11) -- conflict takes priority over incompleteness.

    The caller (`assemble_release_evaluation_state`) must already have
    confirmed `trusted` is non-`None` and T0/T1 durable coherence before
    calling this function; this function never receives a `None` projection.
    """

    if trusted.conflict_ids:
        return _conflict_match(tuple(sorted(f"projection-conflict:{cid}" for cid in trusted.conflict_ids)))
    if not truth.orders_complete or not truth.fills_complete:
        return _incomplete_match()

    fresh_order_ids = frozenset(order.order_id for order in truth.working_orders)
    projection_order_ids = frozenset(order.order_id for order in trusted.working_orders)
    fresh_fill_ids = frozenset(fill.fill_id for fill in truth.fills)
    projection_fill_ids = frozenset(fill.fill_id for fill in trusted.fills)

    conflicts: set[str] = set()
    for order_id in fresh_order_ids - projection_order_ids:
        conflicts.add(f"fresh-order-without-durable-counterpart:{order_id}")
    for fill_id in fresh_fill_ids - projection_fill_ids:
        conflicts.add(f"fresh-fill-without-durable-counterpart:{fill_id}")
    if conflicts:
        return _conflict_match(tuple(sorted(conflicts)))

    if (projection_order_ids - fresh_order_ids) or (projection_fill_ids - fresh_fill_ids):
        # A required durable order/fill is absent from an otherwise-COMPLETE
        # fresh enumeration -- incompleteness, not a fabricated conflict
        # (ER05-TRUST-006). Carries no conflict identity.
        return _incomplete_match()

    order_refs: list[Tuple[str, str]] = []
    for order in truth.working_orders:
        ref = trusted.order_evidence_ref(order)
        if ref is None:
            conflicts.add(f"order-economic-mismatch:{order.order_id}")
            continue
        order_refs.append(ref)

    fill_refs: list[Tuple[str, str]] = []
    for fill in truth.fills:
        ref = trusted.fill_evidence_ref(fill)
        if ref is None:
            conflicts.add(f"fill-economic-mismatch:{fill.fill_id}")
            continue
        fill_refs.append(ref)

    if conflicts:
        return _conflict_match(tuple(sorted(conflicts)))

    return _TrustedReconciliationMatchV1(
        status=_TrustedMatchStatus.COMPLETE_TRUSTED_MATCH,
        known_active_order_ids=tuple(sorted(fresh_order_ids)),
        reconciled_order_ids=tuple(sorted(fresh_order_ids)),
        reconciled_fill_ids=tuple(sorted(fresh_fill_ids)),
        order_evidence_event_ids=tuple(sorted(order_refs)),
        fill_evidence_event_ids=tuple(sorted(fill_refs)),
        identity_conflict_ids=(),
    )


def _require_exact_t0_t1_durable_coherence(
    t0: "SafetyProjection", t1: TrustedReleaseEvidenceProjectionV1,
) -> None:
    """Implementation 04 Blocker 04 correction (Spec 05 dispatch Sections
    15-19): prove Stage-3B's `SafetyProjection` (T0) and Stage-3F's
    `TrustedReleaseEvidenceProjectionV1` (T1) describe the exact same
    durable authority/ledger identity and tail before both are used in one
    `ReleaseEvaluationStateV1`. No inference -- every comparison below uses
    only fields already exposed by the two canonical projection types;
    `execution_ledger.py` is not touched and no new persistence structure or
    authority is introduced."""

    if t0.trusted_sequence != t0.last_sequence or t0.trusted_event_hash != t0.terminal_event_hash:
        raise RunnerError(
            RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED,
            detail="T0 internal authority/ledger tail mismatch",
        )
    if (
        t1.authority_trusted_sequence != t1.ledger_terminal_sequence
        or t1.authority_trusted_event_hash != t1.ledger_terminal_event_hash
    ):
        raise RunnerError(
            RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED,
            detail="T1 internal authority/ledger tail mismatch",
        )
    mismatches: list[str] = []
    if t0.authority_instance_id != t1.authority_instance_id:
        mismatches.append("authority_instance_id")
    if t0.authority_namespace_id != t1.authority_namespace_id:
        mismatches.append("authority_namespace_id")
    if t0.authority_store_path_identity_sha256 != t1.authority_store_path_identity_sha256:
        mismatches.append("authority_store_path_identity_sha256")
    if t0.trusted_sequence != t1.authority_trusted_sequence:
        mismatches.append("trusted_sequence")
    if t0.trusted_event_hash != t1.authority_trusted_event_hash:
        mismatches.append("trusted_event_hash")
    if t0.ledger_instance_id != t1.ledger_instance_id:
        mismatches.append("ledger_instance_id")
    if t0.ledger_path_identity_sha256 != t1.ledger_path_identity_sha256:
        mismatches.append("ledger_path_identity_sha256")
    if t0.environment_classification != t1.environment_classification:
        mismatches.append("environment_classification")
    if t0.conflict_domain_ref != t1.conflict_domain_ref:
        mismatches.append("conflict_domain_ref")
    if t0.last_sequence != t1.ledger_terminal_sequence:
        mismatches.append("last_sequence")
    if t0.terminal_event_hash != t1.ledger_terminal_event_hash:
        mismatches.append("terminal_event_hash")
    if mismatches:
        raise RunnerError(
            RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED,
            detail="T0/T1 durable coherence mismatch: " + ",".join(mismatches),
        )


def assemble_release_evaluation_state(
    invocation: ExperimentRunnerInvocationV1,
    runtime: ExperimentRunnerRuntimeV1,
    truth: AuthoritativeReadTruthV1,
    projection: SafetyProjection,
) -> ReleaseEvaluationStateV1:
    """Stage 3F assembly (Marco Blockers 04/05 from Implementation 02;
    Spec 05 Correction 01/E; Implementation 04 Blockers 01-04 correction).

    Mandatory ordering (dispatch Section 20): obtain the trusted read-only
    projection (T1); prove T0 (`projection`, captured at Stage 3B)/T1 exact
    durable identity+tail coherence; perform complete trusted fresh-vs-
    durable matching; and ONLY on `COMPLETE_TRUSTED_MATCH` construct
    `ReleaseRiskSnapshotV1`/`ReleaseReconciliationSnapshotV1`/
    `ReleaseEvaluationStateV1`. Any earlier failure raises the already
    controlling `RunnerError(RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED
    | PAGINATION_INCOMPLETE, ...)` before any of those three objects is
    constructed -- there is no "empty but safe" release state for Stage 3G
    to reject; Gate B itself stops first.

    `unresolved_write_count`/`unresolved_write_exposure_usd` are derived
    ONLY from the authoritative durable `SafetyProjection` captured at
    Stage 3B -- exactly the same
    `protected_unresolved_legacy_write_count + len(unresolved_write_request_ids)`
    computation the real canonical evaluator uses as `durable_unresolved_count`
    (ledger_binding.py `_derive`). Venue-read pagination completeness never
    participates in this derivation. Exposure is `Decimal("0")` only when
    the durable count is provably zero; otherwise `UNKNOWN_UNBOUNDED`. This
    is release/risk economics (Spec 05's own non-reopened list) and is
    unchanged by this correction.

    Position corroboration (dispatch Section 17) is load-bearing: unless
    `truth.position_corroboration == "CORROBORATED"`, exposure cannot be
    treated as provably bounded even when the durable unresolved-write
    count is zero.

    `authoritative_known_active_order_ids`/`reconciled_order_ids`/
    `reconciled_fill_ids`/the evidence-event-id tuples are ALL now sourced
    exclusively from the trusted match's own successful result (Blocker
    01) -- never from raw, untrusted Stage-3E venue output.
    """

    return _assemble_release_state_core(
        incident_id=invocation.incident_id,
        writer_proof_id=invocation.writer_proof_id,
        runtime=runtime, truth=truth, projection=projection,
    )


def _assemble_release_state_core(
    *, incident_id: str, writer_proof_id: str,
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
    truth: AuthoritativeReadTruthV1, projection: SafetyProjection,
) -> ReleaseEvaluationStateV1:
    """Shared Stage-3F assembly body.  ``incident_id`` / ``writer_proof_id``
    are the only contract-derived inputs; for the legacy path they come from
    the ``ExperimentRunnerInvocationV1``, for the active path they come only
    from ``runtime.active_contract`` (DSB-WRITER-003).  Everything else is
    identical, so a single implementation serves both without ambiguity."""

    process_instance_id = runtime.normal_gate.process_instance_id

    # Stage 3F step 1: trusted read-only projection (T1). The projection
    # read is itself a zero-append, zero-writer-session, equal-tail-
    # validated read-only round trip (ER05-TRUST-003).
    read_result = runtime.read_trusted_release_evidence()
    if type(read_result) is not TrustedReleaseEvidenceReadResultV1:
        raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="trusted evidence read result type")
    if read_result.projection is None:
        raise RunnerError(RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED, detail="trusted evidence projection unavailable")

    # Stage 3F step 2: exact T0/T1 durable identity/tail coherence
    # (Blocker 04) -- no release-state object exists yet.
    _require_exact_t0_t1_durable_coherence(projection, read_result.projection)

    # Stage 3F step 3: complete trusted fresh-vs-durable matching
    # (Blockers 01/02) -- still no release-state object exists yet.
    match = _match_trusted_release_evidence(truth, read_result.projection)
    if not match.complete:
        code = (
            RunnerFailureCode.PAGINATION_INCOMPLETE
            if match.status is _TrustedMatchStatus.INCOMPLETE_OR_UNAVAILABLE
            else RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED
        )
        raise RunnerError(code, detail=",".join(match.identity_conflict_ids) or match.status.value)

    # Stage 3F step 4 onward (Blocker 03): only a COMPLETE_TRUSTED_MATCH
    # reaches this point -- every release-state object below is
    # constructed exactly once, after and only after that success.
    market_data = _market_data_snapshot(truth.market, truth.orderbook)
    durable_unresolved_count = (
        projection.protected_unresolved_legacy_write_count + len(projection.unresolved_write_request_ids)
    )
    if durable_unresolved_count == 0 and truth.position_corroboration == "CORROBORATED":
        exposure: Decimal | str = Decimal("0")
    else:
        exposure = UNKNOWN_UNBOUNDED
    risk_snapshot = ReleaseRiskSnapshotV1(
        fills=truth.fills,
        working_orders=truth.working_orders,
        unresolved_write_count=durable_unresolved_count,
        unresolved_write_exposure_usd=exposure,
        market_data_snapshot=market_data,
    )

    reconciliation = ReleaseReconciliationSnapshotV1(
        match.known_active_order_ids,
        match.reconciled_order_ids,
        match.reconciled_fill_ids,
        match.identity_conflict_ids,
        (),
        match.order_evidence_event_ids,
        match.fill_evidence_event_ids,
    )

    now_ns = runtime.monotonic_clock_ns()
    now_utc = canonical_timestamp(runtime.wall_clock())
    market_stamp = FreshnessStampV1(
        process_instance_id, now_utc, now_ns, "NONE", None, risk_snapshot.market_data_sha256,
    )
    reconciliation_stamp = FreshnessStampV1(
        process_instance_id, now_utc, now_ns, "NONE", None, reconciliation.sha256,
    )

    return ReleaseEvaluationStateV1(
        process_instance_id=process_instance_id,
        incident_id=incident_id,
        writer_proof_id=writer_proof_id,
        risk_config=runtime.risk_config,
        risk_snapshot=risk_snapshot,
        reconciliation_snapshot=reconciliation,
        market_freshness=market_stamp,
        reconciliation_freshness=reconciliation_stamp,
        venue_defense_evidence=None,
        normal_gate=runtime.normal_gate,
        emergency_gate=runtime.emergency_gate,
    )


# ---------------------------------------------------------------------------
# Section 12 -- Stage 3 orchestration result and entrypoint.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreReleaseReadPhaseResultV1:
    status: str  # "LOCALLY_BLOCKED" | "READ_PHASE_COMPLETE"
    process_instance_id: str
    local_block_reasons: Tuple[str, ...]
    release_state: ReleaseEvaluationStateV1 | None
    truth: AuthoritativeReadTruthV1 | None
    requests_consumed: int


def run_pre_release_read_phase(
    invocation: ExperimentRunnerInvocationV1, runtime: ExperimentRunnerRuntimeV1,
) -> PreReleaseReadPhaseResultV1:
    """Execute Stages 3A-3F and stop. Never acquires `RELEASE_ONLY`, never
    issues a `CurrentProcessReleaseCompletionV1`, never acquires
    `NORMAL_WRITER`, and never exposes the write-capable experiment
    surface -- those are Stage 3G onward, owned by a later gate."""

    if type(invocation) is not ExperimentRunnerInvocationV1:
        raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="invocation type")
    if type(runtime) is not ExperimentRunnerRuntimeV1:
        raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="runtime type")

    process_instance_id = runtime.normal_gate.process_instance_id

    # Stage 3B: local read-only authority/ledger replay (no credential
    # resolver, no venue transport has been touched at this point).
    opened = runtime.read_local_safety_state()
    if type(opened) is not OpenResult:
        raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="local state type")

    # Stage 3C: local release-impossibility gate.
    reasons = _local_impossibility_reasons(opened, writer_proof_id=invocation.writer_proof_id)
    if reasons:
        return PreReleaseReadPhaseResultV1(
            status="LOCALLY_BLOCKED",
            process_instance_id=process_instance_id,
            local_block_reasons=reasons,
            release_state=None,
            truth=None,
            requests_consumed=0,
        )

    # Stage 3D: the successful Stage-3C -> Stage-3D transition IS the
    # issuance event -- only here, only via the module-private factory, is
    # a usable PreReleaseReadCapabilityV1 ever constructed (Marco Blocker 01).
    capability = _issue_pre_release_read_capability(
        process_instance_id=process_instance_id, ticker=invocation.market_ticker, runtime=runtime,
    )

    # Stage 3E: bounded read/reconciliation refresh.
    truth = collect_authoritative_read_truth(capability, ticker=invocation.market_ticker)

    # Stage 3F: close the venue-read phase; assemble the exact
    # ReleaseEvaluationStateV1 input chain. No RELEASE_ONLY acquisition, no
    # release evaluation, and no CurrentProcessReleaseCompletionV1 occurs
    # anywhere in this function.
    release_state = assemble_release_evaluation_state(invocation, runtime, truth, opened.projection)

    return PreReleaseReadPhaseResultV1(
        status="READ_PHASE_COMPLETE",
        process_instance_id=process_instance_id,
        local_block_reasons=(),
        release_state=release_state,
        truth=truth,
        requests_consumed=capability.requests_consumed,
    )


# ---------------------------------------------------------------------------
# Section 12b -- Gate C: Stage 3G (RELEASE_ONLY) through Stage 3K (final
# normal-writer revalidation). Module-private continuation only -- no second
# public experiment entrypoint. Every durable mutation below is performed
# exclusively through the canonical `ledger_binding.py`/`execution_ledger.py`
# public surface (`acquire_release_only`, `ReleaseLedgerHandle.evaluate_
# release`/`record_risk_release`/`release_writer_proof`/`record_writer_
# eligible`/`complete_release_and_issue_current_process_completion`,
# `acquire_normal_writer_state`, `end_writer_session`); this file never
# touches raw SQLite, `_open_locked`, `_acquire_normal_writer_candidate`, or
# `start_writer_session` directly, and never constructs, copies, or
# reconstructs a `CurrentProcessReleaseCompletionV1`.
# ---------------------------------------------------------------------------


_WRITER_SESSION_ID_PATTERN = re.compile(r"^ws_[0-9a-f]{32}$")


def _fail_closed_end_writer_session(locked: "LockedLedger", writer_session_id: str | None) -> None:
    """Post-admission cleanup obligation (Implementation 02 Correction 01).

    Once `acquire_normal_writer_state` has returned a genuine non-`None`
    handle, a real `ws_` writer session already exists durably. This helper
    is the single place that ends it through the canonical public
    `end_writer_session` -- never raw SQLite, never a dropped/abandoned
    lock, never a second append bridge. It prefers the session ID the
    canonical acquisition itself returned; it falls back to reading the
    ledger's own live active-session identity only if that field is
    somehow unusable, so a corrupted return carrier can never leave a
    genuine writer session un-terminated. A no-op if the locks are already
    closed (the canonical finalizer/acquisition functions already close on
    their own internal failure branches)."""

    if locked.closed:
        return
    session_id = writer_session_id
    if type(session_id) is not str or _WRITER_SESSION_ID_PATTERN.fullmatch(session_id) is None:
        session_id = locked.projection().active_writer_session_id
    if session_id is None:
        locked.close()
        return
    end_writer_session(locked, writer_session_id=session_id)


@dataclass(frozen=True, slots=True)
class _Stage3ReleaseAndNormalWriterResultV1:
    """Gate C (Stage 3G-3K) success carrier (dispatch Section 18).

    Module-private: no public export, no serialization, no credential/
    secret/transport field. Carries the live canonical
    `NormalWriterAcquisition` -- its still-open `LockedLedger` and started
    `ws_` session -- forward for a later gate's continuation; this function
    never closes it on success."""

    process_instance_id: str
    release_id: str
    normal_writer_session_id: str
    normal_writer_acquisition: NormalWriterAcquisition


def _complete_stage3_release_and_normal_writer(
    read_phase_result: PreReleaseReadPhaseResultV1,
    runtime: ExperimentRunnerRuntimeV1,
) -> _Stage3ReleaseAndNormalWriterResultV1:
    """Gate C: Stage 3G (RELEASE_ONLY) through Stage 3K (final normal-writer
    revalidation) (dispatch Sections 6-20).

    Only a genuine same-process Gate-B `READ_PHASE_COMPLETE` result may
    enter (Section 8); every failure below exposes no token and no normal
    writer, performs no retry, and never fabricates, copies, or
    reconstructs a `CurrentProcessReleaseCompletionV1`. The durable release
    sequence (`record_risk_release` -> `release_writer_proof` ->
    `record_writer_eligible` -> `complete_release_and_issue_current_
    process_completion`) is invoked exactly once, in exactly that order, on
    exactly one `ReleaseAssessmentV1` obtained from the canonical
    evaluator -- no subset of its predicate vector is inspected locally to
    declare success; every gate is enforced by the canonical handle methods
    themselves, which raise `LedgerError` on any predicate failure or
    drift."""

    if type(runtime) is not ExperimentRunnerRuntimeV1:
        raise RunnerError(RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED, detail="runtime type")

    # Stage 3G entry preconditions (dispatch Section 8). No RELEASE_ONLY
    # acquisition may occur until every one of these holds. This is the only
    # gate: there is no "resume Gate C" entrypoint and no reconstruction of
    # a `ReleaseEvaluationStateV1` from serialized fields -- the exact
    # same-process object produced by Gate B's own Stage 3F is required.
    if (
        type(read_phase_result) is not PreReleaseReadPhaseResultV1
        or read_phase_result.status != "READ_PHASE_COMPLETE"
        or type(read_phase_result.release_state) is not ReleaseEvaluationStateV1
        or read_phase_result.process_instance_id != runtime.normal_gate.process_instance_id
        or type(runtime.risk_config) is not RiskLimitConfigV1
    ):
        raise RunnerError(RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED)
    if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="before RELEASE_ONLY")

    # Stage 3G -- the sole supported RELEASE_ONLY acquisition path.
    acquisition = acquire_release_only(
        runtime.authority_binding,
        canonical_repository_root=runtime.canonical_repository_root,
        contract=runtime.contract,
        expected_ledger_path=runtime.expected_ledger_path,
        clock=runtime.wall_clock,
        uuid_factory=runtime.uuid_factory,
        monotonic_clock_ns=runtime.monotonic_clock_ns,
        release_wall_clock=runtime.wall_clock,
    )
    if (
        acquisition.failure_code is not None
        or type(acquisition.handle) is not ReleaseLedgerHandle
        or acquisition.authority_ledger_relation is not AuthorityLedgerRelation.EQUAL
    ):
        if acquisition.handle is not None:
            acquisition.handle.close()
        raise RunnerError(RunnerFailureCode.RELEASE_ONLY_ACQUISITION_FAILED)

    handle = acquisition.handle

    # Stage 3H -- exact durable release sequence (dispatch Section 12). Each
    # canonical mutation is invoked exactly once; a failure at any step
    # closes the still-open `ReleaseLedgerHandle` (a no-op if the canonical
    # method already closed it) and exposes no token, no writer, and
    # attempts no automatic second release.
    try:
        assessment = handle.evaluate_release(read_phase_result.release_state)
    except LedgerError as exc:
        handle.close()
        raise RunnerError(RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED, detail="evaluate_release") from exc

    try:
        handle.record_risk_release(assessment)
    except LedgerError as exc:
        handle.close()
        raise RunnerError(RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED, detail="record_risk_release") from exc

    try:
        handle.release_writer_proof(assessment)
    except LedgerError as exc:
        handle.close()
        raise RunnerError(RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED, detail="release_writer_proof") from exc

    try:
        handle.record_writer_eligible(assessment)
    except LedgerError as exc:
        handle.close()
        raise RunnerError(RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED, detail="record_writer_eligible") from exc

    if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
        handle.close()
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="before current-process completion")

    # Stage 3I -- the exact live token returned by the canonical finalizer,
    # which itself positively anchors RESTRICTED_SESSION_ENDED and proves
    # authority/ledger tail equality before returning (dispatch Section 14).
    try:
        token = handle.complete_release_and_issue_current_process_completion(assessment)
    except LedgerError as exc:
        handle.close()
        raise RunnerError(RunnerFailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_ISSUANCE_FAILED) from exc
    if type(token) is not CurrentProcessReleaseCompletionV1:
        raise RunnerError(RunnerFailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_ISSUANCE_FAILED)

    if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
        # The token now exists and is registered, but Section 19 forbids any
        # retry or reconstruction on expiry -- it is simply never consumed
        # and Stage 3J is never reached.
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="before NORMAL_WRITER")

    # Stage 3J -- the sole supported normal-writer acquisition path. The
    # one-shot token is consumed exactly once, only inside this canonical
    # call, only after every durable/continuity predicate re-validates.
    normal = acquire_normal_writer_state(
        runtime.authority_binding,
        canonical_repository_root=runtime.canonical_repository_root,
        risk_config=runtime.risk_config,
        process_instance_id=runtime.normal_gate.process_instance_id,
        current_process_release_completion=token,
        contract=runtime.contract,
        expected_ledger_path=runtime.expected_ledger_path,
        clock=runtime.wall_clock,
        uuid_factory=runtime.uuid_factory,
    )
    if normal.handle is None:
        # The canonical function itself already closed everything on every
        # one of its own failure branches (ER-NW-003) -- there is no
        # genuine `ws_` to clean up here.
        raise RunnerError(RunnerFailureCode.NORMAL_WRITER_ACQUISITION_FAILED)

    # From this point on a genuine `LockedLedger` + started `ws_` writer
    # session exists (Implementation 02 Correction 01): `acquire_normal_
    # writer_state` never returns a non-`None` handle except on a full
    # successful admission that already durably appended WRITER_SESSION_
    # STARTED. Every subsequent runner-side check -- post-acquisition
    # carrier validation, Stage-3K fresh re-derivation, the final deadline
    # check, and any exception any of that machinery raises -- is wrapped
    # in exactly this one cleanup-protected region, so no future edit can
    # add a new post-admission failure path that bypasses canonical
    # `end_writer_session` cleanup. On success, execution falls through to
    # the `return` below the `try` and no cleanup runs.
    locked = normal.handle
    session_id = normal.normal_writer_session_id
    try:
        if (
            normal.failure_code is not None
            or session_id is None
            or _WRITER_SESSION_ID_PATTERN.fullmatch(session_id) is None
            or normal.authority_ledger_relation is not AuthorityLedgerRelation.EQUAL
        ):
            raise RunnerError(RunnerFailureCode.NORMAL_WRITER_ACQUISITION_FAILED)

        # Stage 3K -- final revalidation while the normal-writer locks
        # remain live (dispatch Section 16). Re-derives the projection
        # fresh from the still-open `LockedLedger` rather than trusting
        # the acquisition's own snapshot, so this is a genuine independent
        # readback under live locks.
        tail = locked.events[-1]
        authority = locked.authority_row
        observed_tail = (tail.sequence, tail.event_hash)
        projection = locked.projection()
        revalidated = (
            not locked.closed
            and type(projection) is SafetyProjection
            and locked.relation is AuthorityLedgerRelation.EQUAL
            and projection.active_writer_session_id == session_id
            and session_id in projection.writer_sessions
            and projection.active_restricted_session_id is None
            and projection.risk_control_state == "WRITER_ELIGIBLE"
            and projection.active_risk_config_sha256 == runtime.risk_config.sha256
            and projection.writer_proof_state_by_proof_id.get(token.writer_proof_id) == "RELEASED"
            and projection.writer_proof_release_eligible_by_proof_id.get(token.writer_proof_id) is True
            and projection.protected_unresolved_legacy_write_count == 0
            and not projection.unresolved_write_request_ids
            and (authority.trusted_sequence, authority.trusted_event_hash) == observed_tail
            and (projection.trusted_sequence, projection.trusted_event_hash) == observed_tail
            and (projection.last_sequence, projection.terminal_event_hash) == observed_tail
            and runtime.normal_gate.process_instance_id == token.process_instance_id
        )
        if not revalidated:
            raise RunnerError(RunnerFailureCode.STAGE_3K_REVALIDATION_FAILED)

        if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
            raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="Stage-3K success boundary")
    except Exception:
        # Fail-closed cleanup-protected region (dispatch Correction 01): a
        # real `ws_` exists, so any failure/exception reaching here -- a
        # predicate, a corrupted carrier field, or an exception raised by
        # the re-derivation machinery itself -- ends it canonically before
        # propagating. The original exception is never suppressed; if the
        # cleanup call itself also fails, that failure chains onto it as
        # additional safety-relevant evidence rather than replacing it.
        _fail_closed_end_writer_session(locked, session_id)
        raise

    return _Stage3ReleaseAndNormalWriterResultV1(
        process_instance_id=runtime.normal_gate.process_instance_id,
        release_id=token.release_id,
        normal_writer_session_id=session_id,
        normal_writer_acquisition=normal,
    )


# ---------------------------------------------------------------------------
# Section 13 -- one-shot marker (Spec 03 ER-ONESHOT-001/002). No canonical
# primitive for this exists anywhere in the protected files, so it is
# implemented here, scoped narrowly to this file's own writable envelope.
# ---------------------------------------------------------------------------


def create_one_shot_marker(
    marker_path: str,
    *,
    execution_authorization_id: str,
    invocation_id: str,
    runner_commit: str,
    runner_tree: str,
    market_ticker: str,
    process_instance_id: str,
    wall_clock: Callable[[], datetime],
) -> None:
    """Atomically create the exact consumption marker binding one execution
    authorization to exactly one runner invocation. Create-if-absent
    (`O_CREAT|O_EXCL`), flush+fsync, close, then re-open and byte-verify
    before returning. Never claims durability beyond what the local
    filesystem provides; never economic truth, a writer permit, a risk-state
    transition, or an authority replacement."""

    for name, value in (
        ("execution_authorization_id", execution_authorization_id),
        ("invocation_id", invocation_id),
        ("market_ticker", market_ticker),
        ("process_instance_id", process_instance_id),
    ):
        if type(value) is not str or value == "":
            raise RunnerError(RunnerFailureCode.EXPERIMENT_AUTHORIZATION_CONSUMPTION_STATE_INVALID, detail=name)
    if type(runner_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", runner_commit) is None:
        raise RunnerError(RunnerFailureCode.EXPERIMENT_AUTHORIZATION_CONSUMPTION_STATE_INVALID, detail="runner_commit")
    if type(runner_tree) is not str or re.fullmatch(r"[0-9a-f]{40}", runner_tree) is None:
        raise RunnerError(RunnerFailureCode.EXPERIMENT_AUTHORIZATION_CONSUMPTION_STATE_INVALID, detail="runner_tree")

    payload = {
        "schema_revision": 1,
        "execution_authorization_id": execution_authorization_id,
        "invocation_id": invocation_id,
        "runner_commit": runner_commit,
        "runner_tree": runner_tree,
        "market_ticker": market_ticker,
        "process_instance_id": process_instance_id,
        "created_at_utc": canonical_timestamp(wall_clock()),
    }
    data = canonical_json_bytes(payload)

    try:
        fd = os.open(marker_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RunnerError(RunnerFailureCode.EXPERIMENT_AUTHORIZATION_ALREADY_CONSUMED) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise RunnerError(RunnerFailureCode.EXPERIMENT_AUTHORIZATION_CONSUMPTION_STATE_INVALID) from exc

    with open(marker_path, "rb") as handle:
        readback = handle.read()
    if readback != data:
        raise RunnerError(RunnerFailureCode.EXPERIMENT_AUTHORIZATION_CONSUMPTION_STATE_INVALID, detail="readback")


# ---------------------------------------------------------------------------
# Section 14 -- Gate D: Stage 4+ ordinary strategy write decision loop
# (dispatch KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_RUNNER_GATE_D_
# ORDINARY_STRATEGY_WRITE_LOOP_IMPLEMENTATION_CORRECTION_06, Spec 07 --
# one narrow same-scope correction to the Marco-blocked Implementation
# Correction 05 candidate 8afa3c63bf83b7597a0323fe86dbf160a52711de (itself a
# correction to the Marco-blocked Correction 04 candidate
# 8532486c23cdc9e0fd0336cafc38540cb284b071, which corrected the Marco-blocked
# Correction 03 candidate 6311dea74b0c80787cf53efbdf8152592ad5d6ce, which
# corrected the Marco-blocked Correction 02 candidate
# cedfb6e0f3098b46d787660d276d5dd0b8847517, which corrected the Marco-blocked
# Implementation 01 candidate 34136bcfec4f92f8a35ec9c12cb9dd9819836ac8),
# freshly reconstructed on clean canonical base
# 969bc79c312e45161371d6637e5c54326f349ddb; none of the five blocked
# candidates is this file's ancestor).
#
# Four corrections relative to the Implementation 01 candidate (Spec 07
# MM07-CLAR-001..004, all preserved unchanged), one correction relative to
# the Correction 02 candidate (Correction 03 Defect 01, quote_lifecycle.py),
# three corrections relative to the Correction 03 candidate (Correction 04
# Defects 01-03), one further tightening relative to the Correction 04
# candidate (Correction 05), and one further tightening relative to the
# Correction 05 candidate (Correction 06), applied deliberately below:
#
#   1. CANCEL_THEN_RECONCILE_BEFORE_NEW is an ORDINARY STRATEGY write. It
#      consumes ordinary_strategy_write_send_max, never cleanup_exact_
#      cancel_send_max. This loop never selects a "cleanup" lane at all --
#      that capacity is reserved for the separate termination/cleanup
#      architecture this Gate-D loop does not implement or touch.
#   2. A CANCEL/CREATE target is cleared only when the fresh authoritative
#      post-send read reports an exact accepted terminal status
#      (`"canceled"`/`"executed"`, taken from the protected canonical
#      `order_lifecycle.SUPPORTED_ORDER_STATUSES`) -- never `status !=
#      "resting"`.
#   3. Production construction always builds a real `MarketMakerInputV1`
#      and calls the protected, unmodified `evaluate_market_maker_input`
#      directly (`_gate_d_build_quote_plan` below). There is no generic
#      `compute_quote_decision` field or any other quote-logic-substitution
#      seam anywhere on `ExperimentRunnerRuntimeV1` or in this loop.
#   4. One ordinary send-budget unit is consumed the instant trusted T3
#      (`WRITE_SEND_BOUNDARY_ENTERED`) durably commits -- before the final
#      pre-adapter freshness recheck, before `adapter.invoke`, and
#      regardless of adapter exceptions, HTTP outcome, or reconciliation
#      result. Charging never depends on anything after T3.
#   5. (Correction 03 Defect 01, quote_lifecycle.py) Every applicable
#      MM07-ECON-005..009 transformation invariant between the exact
#      reconstructed pre/post economic states is explicitly, load-bearingly
#      validated before an ordinary CANCEL assessment may be eligible --
#      never merely `post <= pre` and never satisfied by both states
#      independently passing the configured maximum limits alone.
#   6. (Correction 04 Defect 01) The returned CANCEL transport result is
#      always routed through the protected canonical
#      `order_lifecycle.classify_cancel_response` (`_gate_d_classify_
#      cancel_result` below) -- an adapter call returning normally is never
#      itself treated as a validated definitive success, and a malformed
#      successful-looking response is never durably labeled
#      `DEFINITIVE_SUCCESS`.
#   7. (Correction 04 Defect 03) An authoritative terminal row is never
#      accepted for closure purposes based only on `order_id`/`status`
#      (`_gate_d_validate_terminal_order_identity` below) -- exact
#      `order_id`, `client_order_id`, `ticker`, outcome side, account/
#      exchange scope, and well-formed `status`/`fill_count_fp`/
#      `remaining_count_fp`/`initial_count_fp` are all validated first, and
#      the full validated row (not merely `order_id`/`status`/
#      `remaining_count_fp`) is what gets durably retained as closure
#      evidence.
#   8. (Correction 04 Defect 02) `canceled` closure requires the protected
#      canonical `order_lifecycle.check_cancel_conservation`, using ONLY
#      the exact `reduced_by` value that itself already passed
#      `classify_cancel_response` -- never
#      `fill_count_fp + remaining_count_fp == 1.00` (no controlling
#      artifact establishes that identity for Gate D), and never a
#      GET_ORDER `remaining_count_fp` substituted for `reduced_by`.
#      `executed` closure instead requires complete fresh fills proving
#      full execution of the exact original quantity, independent of any
#      CANCEL `reduced_by`. A fresh, independently re-fetched fill read for
#      the exact target order (via the same closed GET_FILLS pagination
#      machinery every ordinary decision cycle already uses) remains
#      mandatory either way, incorporating any fill that raced the CANCEL
#      send. HTTP success alone, or an exact terminal order-status read
#      alone, never closes the slot (MM07-CLOSE-001).
#   9. (Correction 05) The terminal-order identity validator
#      (`_gate_d_validate_terminal_order_identity`) is fully fail-closed:
#      `client_order_id` binding is now mandatory (never conditional on the
#      field merely being present); `fill_count_fp`/`remaining_count_fp`/
#      `initial_count_fp` are parsed only under the exact accepted
#      FixedPointCount lexical grammar (unsigned, exactly two fractional
#      digits -- never a bare JSON number, never `"1"`/`"1.0"`/`"1.000"`/
#      exponent notation) and bounded (`0.00 <= fill_count_fp <= 1.00`,
#      `0.00 <= remaining_count_fp <= 1.00`,
#      `fill_count_fp + remaining_count_fp <= 1.00` -- a pure order-record
#      self-consistency check, never a substitute for the protected
#      `check_cancel_conservation` identity used separately for CANCEL
#      closure); and the authoritative row's exact quote price is now
#      bound against the strategy-owned target's `yes_price`. Works
#      identically for both the LOWER_YES_BID and UPPER_YES_ASK slots.
#   10. (Correction 06) The `subaccount`/`exchange_index` scope checks in
#      `_gate_d_validate_terminal_order_identity` are now mandatory and
#      exact-`int`-typed: `type(order_row["subaccount"]) is int` (never
#      `isinstance`, since `bool` is a subclass of `int` in Python) and
#      `order_row["subaccount"] == 0` are both required, and likewise for
#      `exchange_index` -- a missing field, `False`, `True`, `0.0`, `"0"`,
#      or any wrong int all leave the slot unresolved rather than being
#      silently accepted or defaulted to `0`.
# ---------------------------------------------------------------------------

GATE_D_ORDINARY_WRITE_SEND_MAX = 4
GATE_D_CLEANUP_CANCEL_SEND_MAX = 2  # reserved capacity; never consumed by this ordinary loop (MM07-CLAR-001)
GATE_D_DECISION_CYCLE_MAX = 12
GATE_D_READ_REQUEST_MAX = EXPERIMENT_READ_REQUEST_MAX  # 64 -- Section 2's preserved identity
GATE_D_ORDINARY_WRITE_IN_FLIGHT_MAX = 1
GATE_D_CLEANUP_CANCEL_IN_FLIGHT_MAX = 1
GATE_D_STRATEGY_ACTIVITY_CUTOFF_SECONDS = 240
GATE_D_ABSOLUTE_EXPERIMENT_DEADLINE_SECONDS = 300

_GATE_D_QUOTE_SLOTS: Tuple[str, ...] = (MMQuoteSlot.LOWER_YES_BID.value, MMQuoteSlot.UPPER_YES_ASK.value)
_GATE_D_KEEP_REPRICE_DISTANCE_GRID_STEPS = 2  # minimal_market_maker.py's own fixed constant, Spec 03/05 unreopened.
_GATE_D_CANCEL_ADAPTER_PAYLOAD_SCHEMA_ID = "gate-d-cancel-v1"
_GATE_D_CREATE_ADAPTER_PAYLOAD_SCHEMA_ID = "gate-d-create-v1"
_GATE_D_CREATE_EXPIRATION_WINDOW_SECONDS = 21600
# MM07-CLAR-002: the exact accepted authoritative terminal-status vocabulary,
# derived from the protected canonical order_lifecycle.SUPPORTED_ORDER_
# STATUSES rather than a locally-invented set -- never `status != "resting"`.
_GATE_D_TERMINAL_ORDER_STATUSES: frozenset[str] = frozenset(SUPPORTED_ORDER_STATUSES) - {"resting"}


@dataclass(frozen=True, slots=True)
class GateDWriteOutcomeV1:
    quote_slot: str
    action: str  # "CANCEL" | "CREATE"
    lane: str  # always "ORDINARY" -- MM07-CLAR-001, no cleanup lane in this loop
    request_id: str
    client_order_id: str
    target_venue_order_id: str | None
    assessment_eligible: bool
    budget_charged: bool  # MM07-CLAR-004: true iff trusted T3 durably committed
    transport_invoked: bool
    result_classification: str
    # ELIGIBLE_NOT_SENT | TARGET_BINDING_INVALID | PERMIT_ISSUANCE_FAILED |
    # FRESHNESS_EXPIRED_BEFORE_ADAPTER | ADAPTER_EXCEPTION | TERMINAL |
    # TERMINAL_UNRECONCILED | STILL_ACTIVE | BOUND_ACTIVE | AMBIGUOUS


@dataclass(frozen=True, slots=True)
class GateDCycleResultV1:
    cycle_index: int
    reads_consumed_after: int
    actions_by_slot: Mapping[str, str]
    selected_slot: str | None
    selected_action: str | None
    write_outcome: GateDWriteOutcomeV1 | None


@dataclass(frozen=True, slots=True)
class GateDLoopResultV1:
    stop_reason: str
    cycles_executed: int
    reads_consumed: int
    ordinary_writes_sent: int
    cleanup_cancels_sent: int  # always 0 -- this loop never selects the cleanup lane
    cycle_results: Tuple[GateDCycleResultV1, ...]


def _runtime_domain_scope(
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
) -> Tuple[int, int]:
    """Resolve the private-read domain scope: the legacy source-bound
    SUBACCOUNT=0 route for a V1 runtime, or the immutable
    ``runtime.domain_binding`` for a V2 runtime (DSB-RUN-002).  Exact static
    branch on runtime type -- no ambiguous dual-contract acceptance."""
    if type(runtime) is ExperimentRunnerRuntimeV2:
        return runtime.domain_binding.subaccount, runtime.domain_binding.exchange_index
    return _SUBACCOUNT, _EXCHANGE_INDEX


def _require_active_gate_d_pre_adapter_equality(
    *, runtime: "ExperimentRunnerRuntimeV2", locked: "LockedLedger",
    assessment, permit, prepared_domain_metadata: Mapping[str, object],
    prepared_request_sha256: str,
    active_trusted_read_set_id: str | None = None,
) -> "str | None":
    """DSB-WRITER-008 final pre-adapter gate for an active ordinary
    CREATE/CANCEL.  Requires exact equality among runtime.active_contract /
    domain_binding, the locked revision-2 ledger domain, the assessment, the
    NormalWriterPermit (including a recomputed permit_domain_commitment
    digest), the prepared-request logical domain metadata, and -- Correction
    02 -- the trusted dynamic read-set identity carried by both the
    assessment and the permit.  Returns the most-specific mismatch
    classification string, or ``None`` when every identity is exact.  A
    non-``None`` return MUST short-circuit BEFORE transport."""
    c = runtime.active_contract
    b = runtime.domain_binding
    meta = locked.ledger_meta

    # 1. locked revision-2 ledger domain.
    if (
        type(meta) is not ActiveLedgerMeta
        or meta.execution_domain_binding_id != c.domain_binding_id
        or meta.execution_domain_binding_sha256 != c.domain_binding_sha256
        or meta.conflict_domain_ref != c.conflict_domain_ref
        or meta.environment_classification != c.environment
        or locked.conflict_domain_ref != c.conflict_domain_ref
    ):
        return "ACTIVE_DOMAIN_CONTRACT_MISMATCH"

    expected = {
        "domain_binding_id": c.domain_binding_id, "domain_binding_sha256": c.domain_binding_sha256,
        "active_contract_id": c.contract_id, "active_contract_sha256": c.contract_sha256,
        "bootstrap_contract_sha256": c.bootstrap_contract_sha256,
        "conflict_domain_ref": c.conflict_domain_ref, "account_scope_ref": c.account_scope_ref,
        "subaccount": c.subaccount, "exchange_index": c.exchange_index,
        "environment": c.environment, "incident_id": c.incident_id, "writer_proof_id": c.writer_proof_id,
    }
    if (
        type(active_trusted_read_set_id) is not str
        or active_trusted_read_set_id[:6] != "ADRS2_"
        or len(active_trusted_read_set_id) != 70
    ):
        return "ACTIVE_DOMAIN_PERMIT_MISMATCH"
    expected["trusted_dynamic_read_set_id"] = active_trusted_read_set_id
    if (b.subaccount != c.subaccount or b.exchange_index != c.exchange_index
            or b.binding_sha256 != c.domain_binding_sha256 or b.conflict_domain_ref != c.conflict_domain_ref):
        return "ACTIVE_DOMAIN_CONTRACT_MISMATCH"

    # 2. assessment active commitments.
    for key, value in expected.items():
        if getattr(assessment, key, None) != value:
            return "ACTIVE_DOMAIN_PERMIT_MISMATCH"

    # 3. NormalWriterPermit active commitments + recomputed digest.
    for key, value in expected.items():
        if getattr(permit, key, None) != value:
            return "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH"
    if (
        permit.permit_domain_commitment_sha256 is None
        or permit.permit_domain_commitment_sha256 != compute_permit_domain_commitment_sha256(permit)
    ):
        return "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH"

    # 4. prepared-request logical domain metadata.
    if (
        prepared_domain_metadata.get("subaccount") != c.subaccount
        or prepared_domain_metadata.get("exchange_index") != c.exchange_index
        or prepared_domain_metadata.get("conflict_domain_ref") != c.conflict_domain_ref
        or prepared_domain_metadata.get("domain_binding_sha256") != c.domain_binding_sha256
        or prepared_domain_metadata.get("domain_binding_id") != c.domain_binding_id
        or prepared_domain_metadata.get("canonical_request_sha256") != prepared_request_sha256
        or prepared_domain_metadata.get("exchange_index_wire_policy") != runtime.route_qualification.exchange_index_wire_policy
    ):
        return "ACTIVE_DOMAIN_PERMIT_MISMATCH"

    return None


def _issue_gate_d_read_capability(
    *, process_instance_id: str, ticker: str,
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
) -> PreReleaseReadCapabilityV1:
    """Module-private factory for Gate D's Stage-4+ read capability: the
    exact same closed six-operation, REST-only, read-only surface as
    Stage 3E's `PreReleaseReadCapabilityV1` -- no new venue operation, no
    write method -- but budgeted against the Gate-D-scoped
    `GATE_D_READ_REQUEST_MAX` (dispatch's preserved `read_request_max = 64`
    identity) rather than Stage 3E's 16, and exhausted with
    `GATE_D_READ_BUDGET_EXHAUSTED`. Called only by
    `run_gate_d_ordinary_decision_loop`, and only after its own entry
    preconditions (a genuine Stage-3K `NORMAL_WRITER` result) have already
    passed."""

    scope_subaccount, scope_exchange_index = _runtime_domain_scope(runtime)
    return PreReleaseReadCapabilityV1(
        _CAPABILITY_ISSUANCE_KEY, process_instance_id=process_instance_id, ticker=ticker, runtime=runtime,
        budget_max=GATE_D_READ_REQUEST_MAX, exhausted_code=RunnerFailureCode.GATE_D_READ_BUDGET_EXHAUSTED,
        domain_subaccount=scope_subaccount, domain_exchange_index=scope_exchange_index,
    )


def _gate_d_unresolved_exposure_usd(projection: "SafetyProjection", truth: AuthoritativeReadTruthV1) -> Decimal | str:
    """Exactly the same conservative rule Stage 3F's `assemble_release_
    evaluation_state` already uses (Section 11): provably zero only when
    the durable unresolved-write count is zero AND fresh venue position
    truth corroborates the independently-derived economic state;
    `UNKNOWN_UNBOUNDED` otherwise. UNKNOWN is never treated as zero."""

    durable_unresolved_count = projection.protected_unresolved_legacy_write_count + len(projection.unresolved_write_request_ids)
    if durable_unresolved_count == 0 and truth.position_corroboration == "CORROBORATED":
        return Decimal("0")
    return UNKNOWN_UNBOUNDED


def _gate_d_reconciliation_snapshot_object(truth: AuthoritativeReadTruthV1) -> Mapping[str, object]:
    return {
        "bound_order_ids": sorted(truth.bound_order_ids),
        "fill_ids": sorted(fill.fill_id for fill in truth.fills),
        "position_state": truth.position_state,
    }


def _gate_d_working_orders_map(
    reconstructions: Mapping[str, ReconstructedSlotOwnershipV1],
) -> Mapping[str, object]:
    return {slot: reconstructions[slot].working_order for slot in _GATE_D_QUOTE_SLOTS}


def _gate_d_read_order_status(
    capability: PreReleaseReadCapabilityV1, *, order_id: str,
) -> Tuple[str, Mapping[str, object]]:
    """Exact authoritative post-send order read (MM07-CLAR-002): the raw
    GET_ORDER status, never collapsed into "identity invalid" for a
    genuinely terminal order the way the Stage-3E `get_order()` wrapper does
    for its own (resting-only) purpose. Reuses the same closed request/
    deadline/budget pipeline via the capability's own `_send_generic` -- no
    new venue operation."""

    parsed, _deadline = capability._send_generic(
        RunnerOperation.GET_ORDER, path_parameters={"order_id": order_id},
    )
    obj = _require_dict(parsed, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="get_order top level")
    order_row = _require_dict(
        _require_field(obj, "order", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="order shape",
    )
    confirmed_id = _require_exact_str(
        _require_field(order_row, "order_id", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="order_id type",
    )
    if confirmed_id != order_id:
        raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="order_id mismatch")
    status = _require_field(order_row, "status", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
    if type(status) is not str or not status:
        # Missing/malformed status remains unresolved (MM07-CLAR-002 /
        # MM07-TEST-CLOSURE 8) -- never promoted to a supported value.
        return "", order_row
    return status, order_row


def _gate_d_record_closing_reconciliation(
    locked: "LockedLedger", *, session_id: str, incident_id: str, bound_order_id: str,
) -> None:
    payload = {
        "incident_id": incident_id, "disposition": "GATE_D_AUTHORITATIVE_TERMINAL",
        "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED", "bound_order_id": bound_order_id,
        "created_order_upper_bound": 0, "active_order_upper_bound": 0, "unknown_result": False,
        "writer_proof_release_eligible": True, "basis_event_ids": [],
        "adapter_reconciliation_schema_id": "GATE_D_RECONCILIATION_V1",
    }
    locked.append_batch((EventInput(EventType.RECONCILIATION_RECORDED, payload, session_id, incident_id, None),))


_GATE_D_TERMINAL_ORDER_EVIDENCE_FIELDS: Tuple[str, ...] = (
    "order_id", "client_order_id", "ticker", "side", "status",
    "fill_count_fp", "remaining_count_fp", "initial_count_fp",
    "subaccount", "exchange_index", "yes_price_dollars",
)


def _gate_d_record_terminal_order_observation(
    locked: "LockedLedger", *, session_id: str, venue_order_id: str, client_order_id: str, order_row: Mapping[str, object],
) -> None:
    """Record the fresh authoritative terminal observation
    `reconstruct_slot_ownership` requires before a closing reconciliation
    can classify a slot `TERMINAL_RECONCILED` rather than continuing to
    read the order's last (pre-send) `resting` observation.

    Correction 04 dispatch Sections 15/21: retains every closure-relevant
    field actually present on the exact validated authoritative
    ``order_row`` (identity, status, and all three fixed-point-count
    fields) -- never reduced to only ``order_id``/``status``/
    ``remaining_count_fp``, and never a synthesized ``"0.00"``/invented
    value for any field. Only called after
    `_gate_d_validate_terminal_order_identity` has already proven every one
    of these fields present and well-formed."""

    canonical_order = {
        name: order_row[name] for name in _GATE_D_TERMINAL_ORDER_EVIDENCE_FIELDS if name in order_row
    }
    locked.append_batch((EventInput(EventType.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": f"gate-d-post-send-{venue_order_id}", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "gate-d-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex(canonical_json_bytes(canonical_order)),
        "observation_semantic_class": "AUTHORITATIVE_TERMINAL_ORDER",
    }, session_id, None, None),))


def _gate_d_record_fill_observation(
    locked: "LockedLedger", *, session_id: str, venue_order_id: str, client_order_id: str, fill: EconomicFillV1,
) -> None:
    """Persist one fresh authoritative post-CANCEL fill as evidence
    (Correction 03 Defect 02 / MM07-CLOSE-001): binds the exact fill this
    closure's reconciliation relied on into the same durable evidence chain
    `_authoritative_terminal_reconciliation_exists` (quote_lifecycle.py)
    already checks every `FILL_OBSERVED` sequence number against, so a
    still-later race is always detectable on restart."""

    canonical_fill = {
        "fill_id": fill.fill_id, "order_id": venue_order_id, "outcome_side": fill.outcome_side,
        "quantity": str(fill.quantity), "yes_price": str(fill.yes_price),
        "created_time_utc": fill.authoritative_created_time_utc,
    }
    locked.append_batch((EventInput(EventType.FILL_OBSERVED, {
        "venue_fill_id": fill.fill_id, "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": f"gate-d-post-cancel-fill-{fill.fill_id}", "source_operation": "GET_FILLS_V2",
        "venue_payload_schema_id": "gate-d-fill-v1", "canonical_venue_payload": canonical_fill,
        "canonical_venue_payload_sha256": sha256_hex(canonical_json_bytes(canonical_fill)),
    }, session_id, None, None),))


def _gate_d_fetch_fresh_fills_for_order(
    capability: PreReleaseReadCapabilityV1, *, ticker: str, order_id: str,
) -> Tuple[Tuple[EconomicFillV1, ...], bool]:
    """Fresh authoritative post-CANCEL fill evidence for the exact target
    order (Correction 03 Defect 02 / MM07-CLOSE-001..002). Reuses the exact
    same closed GET_FILLS pagination machinery `collect_authoritative_read_
    truth` already uses for every ordinary decision cycle
    (`_fetch_fills_for_order`) -- this is not a new or second reconciliation
    engine. A full fresh fetch inherently incorporates any fill that raced
    the CANCEL send, since it is never computed as a diff against a stale
    pre-cancel snapshot."""

    fills_by_id: dict[str, EconomicFillV1] = {}
    complete = _fetch_fills_for_order(capability, ticker=ticker, order_id=order_id, fills_by_id=fills_by_id)
    fills = tuple(sorted(fills_by_id.values(), key=lambda item: (item.authoritative_created_time_utc, item.fill_id)))
    return fills, complete


def _gate_d_nonnegative_decimal(value: object) -> Decimal | None:
    """Correction 05 Section 17: the exact accepted FixedPointCount lexical
    contract -- JSON string, unsigned ASCII decimal, exactly two fractional
    digits, no sign, no exponent, no whitespace, never coerced from a JSON
    number. Rejects `0`, `1`, `"1"`, `"1.0"`, `"1.000"`, `"1e0"`,
    `"+1.00"`, `" 1.00"`; accepts only `"0.00"`-shaped strings. Uses the
    same exact grammar `_gate_d_parse_cancel_fixed_point_count` already
    applies to a validated Cancel V2 `reduced_by` -- one shared lexical
    definition, never two independently interpreted representations."""

    if type(value) is not str or _GATE_D_FIXED_POINT_COUNT_RE.fullmatch(value) is None:
        return None
    return Decimal(value)


def _gate_d_price_decimal(value: object) -> Decimal | None:
    """The same lax `FixedPointDollars`-shaped price representation
    already accepted elsewhere in Gate D for `yes_price_dollars`
    (`_decimal_from_price_string`), made non-raising for validator use."""

    if type(value) is not str:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < Decimal("0") or parsed > Decimal("1"):
        return None
    return parsed


def _gate_d_validate_terminal_order_identity(
    order_row: Mapping[str, object], *, expected_order_id: str, expected_client_order_id: str,
    expected_ticker: str, expected_outcome_side: str, expected_yes_price: Decimal,
    expected_subaccount: int = _SUBACCOUNT, expected_exchange_index: int = _EXCHANGE_INDEX,
) -> str | None:
    """Correction 04 Defect 03 / Correction 05 (dispatch Sections 14-23) /
    Correction 06 (dispatch Sections 13-16): an authoritative terminal row
    must never be accepted for closure purposes based on a partial
    identity/scope check. Validates, in order: exact ``order_id``; exact
    ``client_order_id`` -- MANDATORY, never conditional on the field merely
    being present (Correction 05 Section 16); exact ``ticker``; exact
    outcome side (the accepted Gate-D venue row has no separate bid/ask
    field -- outcome side and venue side are bijectively coupled by the
    fixed two-slot strategy, so this one check covers both); exact
    account/exchange scope -- MANDATORY and exact-``int``-typed
    (Correction 06 Section 14): ``type(order_row["subaccount"]) is int``
    is required rather than ``isinstance`` because ``bool`` is a subclass
    of ``int`` in Python, so an ``isinstance`` or bare ``!=`` check would
    incorrectly accept ``False`` as equal to ``0``; a missing field, any
    bool, any float, any string, and any wrong int are all rejected, and no
    default is ever substituted for a missing field; exact supported
    ``status``; the exact FixedPointCount lexical contract plus quantity
    bounds and internal conservation for
    ``fill_count_fp``/``remaining_count_fp``/``initial_count_fp``
    (Correction 05 Sections 17/18 -- a pure order-record self-consistency
    check, never a substitute for the protected `check_cancel_conservation`
    identity used separately for CANCEL closure); and the exact strategy
    quote price (Correction 05 Sections 19/20). Returns ``None`` only when
    every check passes; any violation leaves the slot unresolved (never
    fail-open)."""

    if order_row.get("order_id") != expected_order_id:
        return "ORDER_ID_MISMATCH"
    client_order_id = order_row.get("client_order_id")
    if client_order_id is None:
        return "CLIENT_ORDER_ID_MISSING"
    if client_order_id != expected_client_order_id:
        return "CLIENT_ORDER_ID_MISMATCH"
    if order_row.get("ticker") != expected_ticker:
        return "TICKER_MISMATCH"
    side = order_row.get("side")
    outcome_side = {"yes": "YES", "no": "NO"}.get(side) if type(side) is str else None
    if outcome_side != expected_outcome_side:
        return "OUTCOME_SIDE_MISMATCH"
    subaccount = order_row.get("subaccount")
    if type(subaccount) is not int:
        return "SUBACCOUNT_MISSING_OR_MALFORMED"
    if subaccount != expected_subaccount:
        return "SUBACCOUNT_MISMATCH"
    exchange_index = order_row.get("exchange_index")
    if type(exchange_index) is not int:
        return "EXCHANGE_INDEX_MISSING_OR_MALFORMED"
    if exchange_index != expected_exchange_index:
        return "EXCHANGE_INDEX_MISMATCH"
    status = order_row.get("status")
    if status not in SUPPORTED_ORDER_STATUSES:
        return "STATUS_UNSUPPORTED_OR_MALFORMED"

    fill_count = _gate_d_nonnegative_decimal(order_row.get("fill_count_fp"))
    if fill_count is None:
        return "FILL_COUNT_FP_MISSING_OR_MALFORMED"
    remaining_count = _gate_d_nonnegative_decimal(order_row.get("remaining_count_fp"))
    if remaining_count is None:
        return "REMAINING_COUNT_FP_MISSING_OR_MALFORMED"
    initial_count = _gate_d_nonnegative_decimal(order_row.get("initial_count_fp"))
    if initial_count is None:
        return "INITIAL_COUNT_FP_MISSING_OR_MALFORMED"

    if fill_count > QUOTE_QUANTITY:
        return "FILL_COUNT_FP_OUT_OF_BOUNDS"
    if remaining_count > QUOTE_QUANTITY:
        return "REMAINING_COUNT_FP_OUT_OF_BOUNDS"
    if fill_count + remaining_count > QUOTE_QUANTITY:
        return "FILL_PLUS_REMAINING_EXCEEDS_QUANTITY"
    if initial_count != QUOTE_QUANTITY:
        return "INITIAL_COUNT_FP_NOT_FIXED_QUANTITY"

    price = _gate_d_price_decimal(order_row.get("yes_price_dollars"))
    if price is None:
        return "PRICE_EVIDENCE_MISSING_OR_MALFORMED"
    if price != expected_yes_price:
        return "PRICE_MISMATCH"

    return None


def _gate_d_fresh_fill_reconciliation_violation(
    *, order_row: Mapping[str, object], fresh_fills: Tuple[EconomicFillV1, ...],
) -> str | None:
    """MM07-CLOSE-001 (Correction 03/04): the independently re-fetched
    fresh fill set must reconcile exactly to the order's own authoritative
    ``fill_count_fp`` -- the same accounting identity
    ``order_lifecycle.FillLedger.reconcile_against_order`` establishes as
    canonical, applied here to Gate D's own two-sided, variable-price
    working orders (that fixed-side/fixed-price protected helper cannot
    validate directly). This is deliberately independent of any CANCEL-
    response ``reduced_by`` value and independent of the withdrawn
    ``fill_count_fp + remaining_count_fp == 1.00`` identity (Correction 04
    Section 16) -- it only proves the fresh fill set is internally
    consistent with the order's own bookkeeping."""

    fill_count = _gate_d_nonnegative_decimal(order_row.get("fill_count_fp"))
    if fill_count is None:
        return "FILL_COUNT_FP_MISSING_OR_MALFORMED"
    fresh_total = sum((fill.quantity for fill in fresh_fills), Decimal("0"))
    if fresh_total != fill_count:
        return "FRESH_FILL_TOTAL_DOES_NOT_RECONCILE_TO_ORDER"
    return None


_GATE_D_FIXED_POINT_COUNT_RE = re.compile(r"^[0-9]+\.[0-9]{2}$")


def _gate_d_parse_cancel_fixed_point_count(value: object) -> Decimal | None:
    """The exact same FixedPointCount representation the protected
    `order_lifecycle.classify_cancel_response` already accepts/rejects for
    `reduced_by` (Correction 04 Section 17) -- never a second,
    independently interpreted representation. By the time this is called,
    `classify_cancel_response` has already proven this exact string parses
    under this exact grammar (it returns SEND_MAY_HAVE_BEGUN_UNKNOWN
    otherwise), so this re-parses rather than re-validates it."""

    if type(value) is not str or _GATE_D_FIXED_POINT_COUNT_RE.fullmatch(value) is None:
        return None
    return Decimal(value)


def _gate_d_classify_cancel_result(
    raw_response: object, *, expected_order_id: str, expected_client_order_id: str,
) -> Tuple["SendOutcome", Mapping[str, object]]:
    """Correction 04 Defect 01 (dispatch Sections 12-14): route the
    returned CANCEL transport result through the protected canonical
    `classify_cancel_response` -- an adapter call returning normally is
    never itself treated as a validated definitive success. Builds the
    exact `order_lifecycle.RawHttpResponse` evidence carrier that
    classifier requires; never duplicates or rewrites its validation logic
    locally."""

    body: Mapping[str, object] = {}
    http_status = 0
    if type(raw_response) is RawOperationResponseV1 and not raw_response.transport_unknown:
        http_status = raw_response.http_status
        try:
            parsed = _strict_json_loads(raw_response.body_bytes.decode("utf-8"))
        except (RunnerError, UnicodeDecodeError):
            parsed = None
        if type(parsed) is dict:
            body = parsed
        disposition = (
            SendOutcome.DEFINITIVE_SUCCESS if http_status == 200 and type(parsed) is dict
            else SendOutcome.DEFINITIVE_RESPONSE_AFTER_SEND
        )
    else:
        disposition = SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN

    lifecycle_raw = LifecycleRawHttpResponse(
        status=http_status, body=body, media_type="application/json", retry_count=0, redirect_count=0,
        send_result_classification=disposition,
    )
    outcome = classify_cancel_response(
        lifecycle_raw, expected_order_id=expected_order_id, expected_client_order_id=expected_client_order_id,
    )
    return outcome, body


def _gate_d_record_order_identity_and_observation(
    locked: "LockedLedger", *, session_id: str, incident_id: str, client_order_id: str,
    venue_order_id: str, market_ticker: str, outcome_side: str, remaining_count_fp: str, yes_price_dollars: str,
) -> None:
    locked.append_batch((EventInput(EventType.ORDER_IDENTITY_BOUND, {
        "client_order_id": client_order_id, "venue_order_id": venue_order_id, "venue": "KALSHI",
        "environment": "KALSHI_DEMO", "incident_id": incident_id, "binding_basis_event_ids": [],
    }, session_id, incident_id, None),))
    canonical_order = {
        "order_id": venue_order_id, "status": "resting", "remaining_count_fp": remaining_count_fp,
        "market": market_ticker, "outcome_side": outcome_side, "yes_price": yes_price_dollars,
    }
    locked.append_batch((EventInput(EventType.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": f"gate-d-{venue_order_id}", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "gate-d-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex(canonical_json_bytes(canonical_order)),
        "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
    }, session_id, None, None),))


def _gate_d_record_http_response_classified(
    locked: "LockedLedger", *, session_id: str, request_id: str, raw_response: object, write_closure_class: str,
    adapter_result_class: str = "DEFINITIVE_RESPONSE_AFTER_SEND", validated_identity_fields: Mapping[str, object] | None = None,
) -> None:
    """Close the ledger's own WRITE_SEND_BOUNDARY_ENTERED bookkeeping
    (`SafetyProjection.unresolved_write_request_ids`) for this exact
    request. This is independent of, and always chronologically after,
    Gate D's own ordinary-send-budget charge (MM07-CLAR-004): the budget is
    already consumed by the time this runs. Only `write_closure_class in
    {"NO_SEND_PROVEN", "AUTHORITATIVE_RESULT_CLOSED"}` clears the durable
    unresolved-write set; every other value (in particular "UNRESOLVED")
    leaves the request durably unresolved, blocking a future fresh Gate-D/
    Gate-C re-entry until genuinely reconciled.

    `adapter_result_class` carries the actual protected classifier outcome
    (e.g. the exact `SendOutcome` value) when the caller has one, rather
    than always the generic default. `validated_identity_fields` retains
    the exact validated result-evidence fields (Correction 04 Section 15) --
    for a validated definitive CANCEL success this is `order_id`,
    `reduced_by`, `ts_ms`, and `client_order_id` when present -- using this
    existing allowed evidence structure rather than a new persistent event
    field or schema."""

    if type(raw_response) is RawOperationResponseV1:
        http_status = raw_response.http_status
        body = raw_response.body_bytes
    else:
        http_status = 0
        body = b""
    payload = {
        "request_id": request_id, "http_status": http_status, "response_media_type": "application/json",
        "response_byte_length": len(body), "response_sha256": sha256_hex(body),
        "adapter_result_class": adapter_result_class, "write_closure_class": write_closure_class,
        "validated_identity_fields": dict(validated_identity_fields) if validated_identity_fields else {},
    }
    locked.append_batch((EventInput(EventType.HTTP_RESPONSE_CLASSIFIED, payload, session_id, None, None),))


def _gate_d_extract_created_order_id(raw_response: object, *, expected_client_order_id: str) -> str | None:
    """Parse Gate D's own internal CREATE transport-response contract for
    the venue-assigned order id. This identity is ordinary send-result
    evidence (receiving it back is how the strategy learns a new order's
    identity at all); it is never treated as authoritative *state* --
    `_gate_d_execute_create` still requires a fresh authoritative GET_ORDER
    read reporting `"resting"` before binding it."""

    if (
        type(raw_response) is not RawOperationResponseV1
        or raw_response.transport_unknown
        or raw_response.http_status != 200
    ):
        return None
    try:
        parsed = _strict_json_loads(raw_response.body_bytes.decode("utf-8"))
    except (RunnerError, UnicodeDecodeError):
        return None
    if type(parsed) is not dict:
        return None
    order = parsed.get("order")
    if type(order) is not dict:
        return None
    order_id = order.get("order_id")
    if type(order_id) is not str or not order_id:
        return None
    client_order_id = order.get("client_order_id")
    if client_order_id is not None and client_order_id != expected_client_order_id:
        return None
    return order_id


# ---------------------------------------------------------------------------
# MM07-CLAR-003 -- production strategy binding. This is the ONLY place Gate D
# ever calls the protected, unmodified `evaluate_market_maker_input`. There is
# no other route into strategy planning and no caller-substitutable seam.
# ---------------------------------------------------------------------------


def _gate_d_build_quote_plan(
    *,
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
    invocation: "ExperimentRunnerInvocationV1 | ExperimentRunnerInvocationV2",
    truth: AuthoritativeReadTruthV1,
    reconstructions: Mapping[str, ReconstructedSlotOwnershipV1],
    projection: "SafetyProjection",
) -> "QuotePlanV1":
    """Build a genuine `MarketMakerInputV1` from this cycle's fresh
    authoritative truth and durable ledger state, and evaluate it through
    the protected canonical `evaluate_market_maker_input`. This is
    production Gate D's only strategy-planning path (MM07-CLAR-003) -- no
    generic quote-decision callback exists anywhere in this module."""

    process_instance_id = runtime.normal_gate.process_instance_id
    now_ns = runtime.monotonic_clock_ns()
    now_utc = canonical_timestamp(runtime.wall_clock())

    try:
        strategy_config = build_market_maker_config(
            strategy_instance_id=runtime.strategy_instance_id, market_ticker=invocation.market_ticker,
            minimum_spread_usd=runtime.minimum_spread_usd,
        )
        price_ranges = _parse_price_ranges(truth.market.get("price_ranges"))
        price_grid_sha256 = compute_price_grid_sha256(price_ranges)

        book_snapshot = truth.orderbook
        if type(book_snapshot) is not KalshiNativeOrderBookSnapshot:
            raise RunnerError(RunnerFailureCode.GATE_D_STRATEGY_INPUT_CONSTRUCTION_FAILED, detail="book_snapshot type")
        book_snapshot_sha256 = book_snapshot.canonical_snapshot_sha256
        book_freshness = FreshnessStampV1(process_instance_id, now_utc, now_ns, "NONE", None, book_snapshot_sha256)

        reconciliation_snapshot_sha256 = sha256_hex(canonical_json_bytes(_gate_d_reconciliation_snapshot_object(truth)))
        reconciliation_freshness = FreshnessStampV1(process_instance_id, now_utc, now_ns, "NONE", None, reconciliation_snapshot_sha256)

        market_economic_state = compute_market_economic_state(invocation.market_ticker, truth.fills, truth.working_orders)
        unresolved_write_exposure_usd = _gate_d_unresolved_exposure_usd(projection, truth)
        signed_inventory_known = unresolved_write_exposure_usd != UNKNOWN_UNBOUNDED
        fill_history_completeness = "COMPLETE" if truth.fills_complete else "INCOMPLETE"
        reconciliation_completeness = (
            "COMPLETE" if truth.orders_complete and truth.position_corroboration == "CORROBORATED" else "INCOMPLETE"
        )
        economic_truth = build_economic_truth(
            signed_inventory_state="KNOWN" if signed_inventory_known else "UNKNOWN",
            unresolved_write_exposure_usd=unresolved_write_exposure_usd,
            fill_history_completeness=fill_history_completeness,
            reconciliation_completeness=reconciliation_completeness,
            signed_net_position_contracts=market_economic_state.signed_net_position if signed_inventory_known else None,
            market_economic_state=market_economic_state,
            unresolved_write_request_ids=tuple(projection.unresolved_write_request_ids),
            protected_unresolved_legacy_write_count=projection.protected_unresolved_legacy_write_count,
            fill_identity_conflict_ids=tuple(projection.fill_conflicts),
        )

        strategy_working_orders = tuple(
            reconstructions[slot].working_order for slot in _GATE_D_QUOTE_SLOTS if reconstructions[slot].working_order is not None
        )
        slot_classifications = {slot: reconstructions[slot].classification for slot in _GATE_D_QUOTE_SLOTS}

        market_maker_input = MarketMakerInputV1(
            strategy_config=strategy_config, book_snapshot=book_snapshot, book_snapshot_sha256=book_snapshot_sha256,
            book_freshness=book_freshness, price_ranges=price_ranges, price_grid_sha256=price_grid_sha256,
            risk_control_state=projection.risk_control_state, risk_state_epoch=projection.risk_state_epoch,
            risk_config=runtime.risk_config, risk_config_sha256=runtime.risk_config.sha256,
            reconciliation_snapshot_sha256=reconciliation_snapshot_sha256, reconciliation_freshness=reconciliation_freshness,
            economic_truth=economic_truth, strategy_working_orders=strategy_working_orders,
            slot_classifications=slot_classifications, process_instance_id=process_instance_id,
            now_monotonic_ns=now_ns, now_utc=now_utc,
        )
    except (RiskControlError, ValueError) as exc:
        raise RunnerError(RunnerFailureCode.GATE_D_STRATEGY_INPUT_CONSTRUCTION_FAILED) from exc

    return evaluate_market_maker_input(market_maker_input)


# ---------------------------------------------------------------------------
# MM07-CANCEL-001..003 / MM07-PERMIT-001..003 / MM07-CLAR-002/004 -- the
# ordinary CANCEL send sequence, corrected for exact terminal classification
# and trusted-T3 budget charging.
# ---------------------------------------------------------------------------


def _gate_d_execute_cancel(
    *,
    locked: "LockedLedger",
    session_id: str,
    capability: PreReleaseReadCapabilityV1,
    adapter: NormalWriteAdapter,
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
    invocation: "ExperimentRunnerInvocationV1 | ExperimentRunnerInvocationV2",
    projection: "SafetyProjection",
    truth: AuthoritativeReadTruthV1,
    reconstruction: ReconstructedSlotOwnershipV1,
    selected: SelectedWriteV1,
    active_trusted_read_set_id: str | None = None,
) -> GateDWriteOutcomeV1:
    """Exact Spec-06/07 ordinary CANCEL send sequence: fresh economic proof
    (with load-bearing transformation-invariant validation, Correction 03
    Defect 01), exact target/request binding, genuine one-shot permit
    T0->T1->T2->T3, ordinary send-budget charge the instant T3 durably
    commits, final pre-adapter freshness/target recheck, at most one
    transport invocation, then the protected canonical
    `classify_cancel_response` result classification (Correction 04 Defect
    01), exact terminal-order identity validation (Correction 04 Defect
    03), a fresh independently-refetched fill reconciliation (Correction 03
    Defect 02), and closure via the protected canonical
    `check_cancel_conservation` using only the exact validated `reduced_by`
    that itself passed the classifier for `canceled`, or complete fresh
    fill proof of full execution for `executed` (Correction 04 Defect 02) --
    an exact terminal status alone, HTTP success alone, or a
    fill_count_fp/remaining_count_fp identity no controlling artifact
    establishes, never closes the slot (MM07-CLOSE-001)."""

    working_order = reconstruction.working_order
    target_venue_order_id = selected.target_venue_order_id
    request_id = f"req_{runtime.uuid_factory().hex}"
    execution_attempt_id = f"ea_{runtime.uuid_factory().hex}"
    conflict_domain_ref = locked.conflict_domain_ref

    reconciliation_snapshot_sha256 = sha256_hex(canonical_json_bytes(_gate_d_reconciliation_snapshot_object(truth)))
    market_data_object = _market_data_snapshot(truth.market, truth.orderbook)
    market_data_snapshot_sha256 = sha256_hex(canonical_json_bytes(market_data_object))
    now_ns = runtime.monotonic_clock_ns()
    now_utc = canonical_timestamp(runtime.wall_clock())
    process_instance_id = runtime.normal_gate.process_instance_id
    market_data_freshness_identity_sha256 = compute_mm_freshness_identity_sha256(
        FreshnessStampV1(process_instance_id, now_utc, now_ns, "NONE", None, market_data_snapshot_sha256),
    )
    reconciliation_freshness_identity_sha256 = compute_mm_freshness_identity_sha256(
        FreshnessStampV1(process_instance_id, now_utc, now_ns, "NONE", None, reconciliation_snapshot_sha256),
    )
    freshness_deadline_monotonic_ns = now_ns + OPERATION_DEADLINE_MS * 1_000_000

    active_commitment: "dict | None" = None
    if type(runtime) is ExperimentRunnerRuntimeV2:
        _require_active_route_qualified(runtime)
        active_commitment = active_domain_commitment(runtime.active_contract, runtime.domain_binding)

    prepared = build_cancel_prepared_payload(
        request_id=request_id, environment="KALSHI_DEMO", venue_order_id=target_venue_order_id,
        client_order_id=working_order.client_order_id, adapter_payload_schema_id=_GATE_D_CANCEL_ADAPTER_PAYLOAD_SCHEMA_ID,
    )
    unresolved_exposure_usd = _gate_d_unresolved_exposure_usd(projection, truth)
    assessment = build_cancel_writer_eligibility_assessment(
        active_domain_commitment=active_commitment,
        trusted_dynamic_read_set_id=active_trusted_read_set_id,
        risk_assessment_id=f"ra_{runtime.uuid_factory().hex}", request_id=request_id,
        strategy_instance_id=runtime.strategy_instance_id, market_ticker=invocation.market_ticker,
        quote_slot=selected.quote_slot, quote_generation_id=working_order.quote_generation_id,
        target_venue_order_id=target_venue_order_id, client_order_id=working_order.client_order_id,
        authoritative_fills=truth.fills, authoritative_working_orders=truth.working_orders,
        unresolved_exposure_usd=unresolved_exposure_usd, prepared_request_sha256=prepared["prepared_request_sha256"],
        risk_config=runtime.risk_config, market_data_snapshot_sha256=market_data_snapshot_sha256,
        market_data_freshness_identity_sha256=market_data_freshness_identity_sha256,
        reconciliation_snapshot_sha256=reconciliation_snapshot_sha256,
        reconciliation_freshness_identity_sha256=reconciliation_freshness_identity_sha256,
        risk_state_epoch=projection.risk_state_epoch, freshness_deadline_monotonic_ns=freshness_deadline_monotonic_ns,
    )
    outer_intent = build_mm_cancel_intent_payload(
        execution_attempt_id=execution_attempt_id, conflict_domain_ref=conflict_domain_ref,
        incident_id=runtime.gate_d_incident_id, client_order_id=working_order.client_order_id,
        capability_reference_id=runtime.gate_d_capability_reference_id, request_id=request_id,
        strategy_instance_id=runtime.strategy_instance_id, market_ticker=invocation.market_ticker,
        quote_slot=selected.quote_slot, quote_generation_id=working_order.quote_generation_id,
        target_venue_order_id=target_venue_order_id, reconciliation_snapshot_sha256=reconciliation_snapshot_sha256,
    )

    def _outcome(*, budget_charged: bool, transport_invoked: bool, classification: str) -> GateDWriteOutcomeV1:
        return GateDWriteOutcomeV1(
            selected.quote_slot, "CANCEL", "ORDINARY", request_id, working_order.client_order_id,
            target_venue_order_id, assessment.eligible, budget_charged, transport_invoked, classification,
        )

    # Pre-T1: malformed intent or target mismatch never reaches the ledger.
    try:
        validate_cancel_request_binding(
            outer_intent_payload=outer_intent, prepared_payload=prepared, assessment=assessment,
            target_venue_order_id=target_venue_order_id,
        )
    except QuoteLifecycleError:
        return _outcome(budget_charged=False, transport_invoked=False, classification="TARGET_BINDING_INVALID")

    if not assessment.eligible:
        return _outcome(budget_charged=False, transport_invoked=False, classification="ELIGIBLE_NOT_SENT")

    # MM07-CLAR-004: budget is charged the instant trusted T3 durably
    # commits below -- never before (a failure here charges nothing) and
    # never contingent on anything that happens afterward.
    try:
        permit = issue_and_persist_write_permit(
            gate=runtime.normal_gate, locked=locked, normal_writer_session_id=session_id, assessment=assessment,
            outer_intent_payload=outer_intent, prepared_payload=prepared,
        )
    except (RiskControlError, LedgerError):
        return _outcome(budget_charged=False, transport_invoked=False, classification="PERMIT_ISSUANCE_FAILED")

    # Trusted T3 has now committed: the ordinary send-budget unit is spent
    # regardless of everything that follows.
    budget_charged = True

    # Final pre-adapter freshness and target-binding recheck (dispatch
    # Section 20 / MM07-PERMIT-002/003). If freshness expires after T3 but
    # before adapter entry, transport must not be called and no replacement
    # CREATE may follow -- but the budget unit charged above stands.
    try:
        validate_cancel_request_binding(
            outer_intent_payload=outer_intent, prepared_payload=prepared, assessment=assessment,
            target_venue_order_id=target_venue_order_id,
        )
    except QuoteLifecycleError:
        return _outcome(budget_charged=budget_charged, transport_invoked=False, classification="TARGET_BINDING_INVALID")
    if runtime.monotonic_clock_ns() > permit.freshness_deadline_monotonic_ns:
        return _outcome(budget_charged=budget_charged, transport_invoked=False, classification="FRESHNESS_EXPIRED_BEFORE_ADAPTER")

    # DSB-WRITER-008 final pre-adapter active-domain equality gate for the
    # ordinary CANCEL path -- fail BEFORE transport on any mismatch.
    if active_commitment is not None:
        prepared_domain_metadata = {
            "conflict_domain_ref": runtime.domain_binding.conflict_domain_ref,
            "domain_binding_id": runtime.domain_binding.binding_id,
            "domain_binding_sha256": runtime.domain_binding.binding_sha256,
            "exchange_index": runtime.domain_binding.exchange_index,
            "exchange_index_wire_policy": runtime.route_qualification.exchange_index_wire_policy,
            "canonical_request_sha256": prepared["prepared_request_sha256"],
            "subaccount": runtime.domain_binding.subaccount,
        }
        mismatch = _require_active_gate_d_pre_adapter_equality(
            runtime=runtime, locked=locked, assessment=assessment, permit=permit,
            prepared_domain_metadata=prepared_domain_metadata,
            prepared_request_sha256=prepared["prepared_request_sha256"],
            active_trusted_read_set_id=active_trusted_read_set_id,
        )
        if mismatch is not None:
            return _outcome(budget_charged=budget_charged, transport_invoked=False, classification=mismatch)

    try:
        raw_response = adapter.invoke(permit, prepared)
    except Exception:
        # trusted T3 + adapter exception => budget already consumed above;
        # the request may or may not have reached the venue (write-ambiguity
        # boundary), so the slot remains conservatively unresolved -- no
        # reconciliation write, no replacement, no blind retry.
        return _outcome(budget_charged=budget_charged, transport_invoked=True, classification="ADAPTER_EXCEPTION")

    # Correction 04 Defect 01 (dispatch Sections 12-14): route the returned
    # result through the protected canonical classify_cancel_response --
    # an adapter call returning normally is never itself treated as a
    # validated definitive success.
    cancel_send_outcome, cancel_result_body = _gate_d_classify_cancel_result(
        raw_response, expected_order_id=target_venue_order_id, expected_client_order_id=working_order.client_order_id,
    )
    trustworthy_reduced_by: Decimal | None = None
    validated_identity_fields: dict[str, object] = {}
    if cancel_send_outcome is SendOutcome.DEFINITIVE_SUCCESS:
        # Correction 04 Section 15: retain the exact validated result
        # evidence so restart/review can recover the exact reduced_by this
        # closure relied on, using the existing HTTP_RESPONSE_CLASSIFIED
        # validated_identity_fields structure -- no new schema.
        trustworthy_reduced_by = _gate_d_parse_cancel_fixed_point_count(cancel_result_body.get("reduced_by"))
        validated_identity_fields = {
            "order_id": cancel_result_body.get("order_id"), "reduced_by": cancel_result_body.get("reduced_by"),
            "ts_ms": cancel_result_body.get("ts_ms"),
        }
        if "client_order_id" in cancel_result_body:
            validated_identity_fields["client_order_id"] = cancel_result_body.get("client_order_id")

    # MM07-CLOSE-001/MM07-CLAR-002: an exact supported terminal order status
    # is necessary but never sufficient to close the slot. HTTP success
    # alone does not clear it, a terminal order-status read alone does not
    # clear it, and (Correction 04) neither does a fill_count_fp/
    # remaining_count_fp identity that no controlling artifact establishes,
    # nor a GET_ORDER remaining_count_fp substituted for reduced_by.
    classification = "AMBIGUOUS"
    try:
        status, order_row = _gate_d_read_order_status(capability, order_id=target_venue_order_id)
    except RunnerError as exc:
        if exc.code is RunnerFailureCode.GATE_D_READ_BUDGET_EXHAUSTED:
            raise
        status = ""
        order_row = {}

    if status in _GATE_D_TERMINAL_ORDER_STATUSES:
        fresh_fills: Tuple[EconomicFillV1, ...] = ()
        # Correction 04 Defect 03: exact terminal-order identity/scope
        # validation before the row may contribute to closure at all.
        _terminal_subaccount, _terminal_exchange_index = _runtime_domain_scope(runtime)
        identity_violation = _gate_d_validate_terminal_order_identity(
            order_row, expected_order_id=target_venue_order_id, expected_client_order_id=working_order.client_order_id,
            expected_ticker=invocation.market_ticker, expected_outcome_side=working_order.outcome_side,
            expected_yes_price=working_order.yes_price,
            expected_subaccount=_terminal_subaccount, expected_exchange_index=_terminal_exchange_index,
        )
        if identity_violation is not None:
            classification = "TERMINAL_UNRECONCILED"
        else:
            try:
                fresh_fills, fills_complete = _gate_d_fetch_fresh_fills_for_order(
                    capability, ticker=invocation.market_ticker, order_id=target_venue_order_id,
                )
            except RunnerError as exc:
                if exc.code is RunnerFailureCode.GATE_D_READ_BUDGET_EXHAUSTED:
                    raise
                fresh_fills, fills_complete = (), False

            if not fills_complete:
                classification = "TERMINAL_UNRECONCILED"
            elif _gate_d_fresh_fill_reconciliation_violation(order_row=order_row, fresh_fills=fresh_fills) is not None:
                classification = "TERMINAL_UNRECONCILED"
            else:
                fresh_total = sum((fill.quantity for fill in fresh_fills), Decimal("0"))
                if status == "canceled":
                    # Correction 04 Defect 02 (dispatch Section 16): the
                    # protected canonical check_cancel_conservation, using
                    # ONLY the exact reduced_by value that itself already
                    # passed the protected classifier -- never
                    # fill_count_fp + remaining_count_fp == 1.00, never a
                    # second independently interpreted reduced_by, never a
                    # GET_ORDER remaining_count_fp substitute.
                    if trustworthy_reduced_by is None:
                        classification = "TERMINAL_UNRECONCILED"
                    else:
                        conservation_halt = check_cancel_conservation(
                            final_fill_quantity=fresh_total, reduced_by=trustworthy_reduced_by,
                        )
                        classification = "TERMINAL_UNRECONCILED" if conservation_halt is not None else "TERMINAL"
                else:
                    # status == "executed" (dispatch Sections 19/25):
                    # closure requires complete fresh fills proving full
                    # execution of the exact original quantity --
                    # independent of any CANCEL reduced_by. The actual
                    # CANCEL result classification is preserved separately
                    # (validated_identity_fields/adapter_result_class)
                    # regardless of this outcome.
                    classification = "TERMINAL" if fresh_total == QUOTE_QUANTITY else "TERMINAL_UNRECONCILED"

        if classification == "TERMINAL":
            _gate_d_record_terminal_order_observation(
                locked, session_id=session_id, venue_order_id=target_venue_order_id,
                client_order_id=working_order.client_order_id, order_row=order_row,
            )
            for fill in fresh_fills:
                _gate_d_record_fill_observation(
                    locked, session_id=session_id, venue_order_id=target_venue_order_id,
                    client_order_id=working_order.client_order_id, fill=fill,
                )
            _gate_d_record_closing_reconciliation(
                locked, session_id=session_id, incident_id=runtime.gate_d_incident_id, bound_order_id=target_venue_order_id,
            )
    elif status == "resting":
        classification = "STILL_ACTIVE"
    # any other status (missing/malformed/unsupported) stays "AMBIGUOUS" --
    # unresolved/fail-closed (MM07-CLAR-002).

    _gate_d_record_http_response_classified(
        locked, session_id=session_id, request_id=request_id, raw_response=raw_response,
        write_closure_class="AUTHORITATIVE_RESULT_CLOSED" if classification == "TERMINAL" else "UNRESOLVED",
        adapter_result_class=cancel_send_outcome.value, validated_identity_fields=validated_identity_fields,
    )

    return _outcome(budget_charged=budget_charged, transport_invoked=True, classification=classification)


def _gate_d_execute_create(
    *,
    locked: "LockedLedger",
    session_id: str,
    capability: PreReleaseReadCapabilityV1,
    adapter: NormalWriteAdapter,
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
    invocation: "ExperimentRunnerInvocationV1 | ExperimentRunnerInvocationV2",
    projection: "SafetyProjection",
    truth: AuthoritativeReadTruthV1,
    reconstruction: ReconstructedSlotOwnershipV1,
    selected: SelectedWriteV1,
    desired: DesiredQuoteV1 | None,
    quote_plan_sha256: str,
    plan_input_sha256: str,
    source_book_snapshot_sha256: str,
    active_trusted_read_set_id: str | None = None,
) -> GateDWriteOutcomeV1:
    """Exact ordinary CREATE send sequence, structurally parallel to
    `_gate_d_execute_cancel`, reusing the unmodified canonical
    `build_writer_eligibility_assessment` candidate-risk projection
    (MM-RISK-002..006, not reopened by Spec 06/07).

    Correction 02 DSB-WRITER-007 / DSB-QUOTE-003: for an active runtime the
    assessment/permit lineage also commits to
    ``active_trusted_read_set_id`` -- the exact ``ADRS2_<64hex>`` identity of
    the fresh trusted dynamic read-set that supported the current release --
    so a permit cannot be carried across current-read acquisitions."""

    if desired is None or type(desired) is not DesiredQuoteV1:
        raise RunnerError(RunnerFailureCode.GATE_D_STRATEGY_INPUT_CONSTRUCTION_FAILED, detail="missing desired for CREATE_NEW")

    client_order_id = allocate_client_order_id(persisted_client_order_id=reconstruction.persisted_client_order_id)
    request_id = f"req_{runtime.uuid_factory().hex}"
    execution_attempt_id = f"ea_{runtime.uuid_factory().hex}"
    conflict_domain_ref = locked.conflict_domain_ref
    process_instance_id = runtime.normal_gate.process_instance_id

    reconciliation_snapshot_sha256 = sha256_hex(canonical_json_bytes(_gate_d_reconciliation_snapshot_object(truth)))
    market_data_object = _market_data_snapshot(truth.market, truth.orderbook)
    market_data_snapshot_sha256 = sha256_hex(canonical_json_bytes(market_data_object))
    now_ns = runtime.monotonic_clock_ns()
    now_utc = canonical_timestamp(runtime.wall_clock())
    market_data_freshness_identity_sha256 = compute_mm_freshness_identity_sha256(
        FreshnessStampV1(process_instance_id, now_utc, now_ns, "NONE", None, market_data_snapshot_sha256),
    )
    reconciliation_freshness_identity_sha256 = compute_mm_freshness_identity_sha256(
        FreshnessStampV1(process_instance_id, now_utc, now_ns, "NONE", None, reconciliation_snapshot_sha256),
    )
    unresolved_exposure_usd = _gate_d_unresolved_exposure_usd(projection, truth)

    # Active revision-2 path binds the venue create route to the immutable
    # domain binding (VenueBindingV2, DSB-QUOTE-001..003).  The
    # exchange-index wire policy comes ONLY from the explicit, pre-Gate-D
    # ``runtime.route_qualification`` -- there is no ``subaccount == 1`` (or
    # any) literal route-selection rule (DSB-QUOTE-004 / DSB-STOP-002); an
    # unqualified route fails closed before permit issuance.  The legacy
    # path keeps the source-bound SUBACCOUNT=0 VenueBindingV1 unchanged.
    active_commitment: "dict | None" = None
    if type(runtime) is ExperimentRunnerRuntimeV2:
        _require_active_route_qualified(runtime)
        active_commitment = active_domain_commitment(runtime.active_contract, runtime.domain_binding)
        venue_binding: "VenueBindingV1 | VenueBindingV2" = VenueBindingV2(
            domain_binding=runtime.domain_binding,
            exchange_index_wire_policy=runtime.route_qualification.exchange_index_wire_policy,
            adapter_payload_schema_id=_GATE_D_CREATE_ADAPTER_PAYLOAD_SCHEMA_ID,
        )
    else:
        venue_binding = VenueBindingV1(adapter_payload_schema_id=_GATE_D_CREATE_ADAPTER_PAYLOAD_SCHEMA_ID)
    expiration_time = int(runtime.wall_clock().timestamp()) + _GATE_D_CREATE_EXPIRATION_WINDOW_SECONDS
    body = build_mm_create_order_body(
        ticker=invocation.market_ticker, client_order_id=client_order_id, venue_side=desired.venue_side,
        yes_price=desired.yes_price, quantity=desired.quantity, expiration_time=expiration_time, venue_binding=venue_binding,
    )
    prepared = build_create_prepared_payload(
        request_id=request_id, environment="KALSHI_DEMO", client_order_id=client_order_id,
        canonical_body=body, venue_binding=venue_binding,
    )
    market_economic_state = compute_market_economic_state(invocation.market_ticker, truth.fills, truth.working_orders)
    candidate = candidate_for_desired_quote(market_ticker=invocation.market_ticker, desired=desired)
    assessment = build_writer_eligibility_assessment(
        risk_assessment_id=f"ra_{runtime.uuid_factory().hex}", request_id=request_id, candidate=candidate,
        market_economic_state=market_economic_state, unresolved_exposure=unresolved_exposure_usd,
        risk_config=runtime.risk_config, prepared_request_sha256=prepared["prepared_request_sha256"],
        market_data_snapshot_sha256=market_data_snapshot_sha256,
        market_data_freshness_identity_sha256=market_data_freshness_identity_sha256,
        reconciliation_snapshot_sha256=reconciliation_snapshot_sha256,
        reconciliation_freshness_identity_sha256=reconciliation_freshness_identity_sha256,
        risk_state_epoch=projection.risk_state_epoch,
        freshness_deadline_monotonic_ns=now_ns + OPERATION_DEADLINE_MS * 1_000_000,
        active_domain_commitment=active_commitment,
        trusted_dynamic_read_set_id=active_trusted_read_set_id,
    )
    outer_intent = build_mm_create_intent_payload(
        execution_attempt_id=execution_attempt_id, conflict_domain_ref=conflict_domain_ref,
        incident_id=runtime.gate_d_incident_id, client_order_id=client_order_id,
        capability_reference_id=runtime.gate_d_capability_reference_id, request_id=request_id,
        strategy_instance_id=runtime.strategy_instance_id, market_ticker=invocation.market_ticker,
        quote_slot=selected.quote_slot, quote_generation_id=desired.quote_generation_id,
        quote_plan_sha256=quote_plan_sha256, plan_input_sha256=plan_input_sha256,
        source_book_snapshot_sha256=source_book_snapshot_sha256, risk_config_sha256=runtime.risk_config.sha256,
        risk_state_epoch=projection.risk_state_epoch, reconciliation_snapshot_sha256=reconciliation_snapshot_sha256,
        venue_side=desired.venue_side, outcome_side=desired.outcome_side, yes_price=desired.yes_price,
        quantity=desired.quantity,
    )

    def _outcome(*, budget_charged: bool, transport_invoked: bool, classification: str, venue_order_id: str | None = None) -> GateDWriteOutcomeV1:
        return GateDWriteOutcomeV1(
            selected.quote_slot, "CREATE", "ORDINARY", request_id, client_order_id,
            venue_order_id, assessment.eligible, budget_charged, transport_invoked, classification,
        )

    if not assessment.eligible:
        return _outcome(budget_charged=False, transport_invoked=False, classification="ELIGIBLE_NOT_SENT")

    try:
        permit = issue_and_persist_write_permit(
            gate=runtime.normal_gate, locked=locked, normal_writer_session_id=session_id, assessment=assessment,
            outer_intent_payload=outer_intent, prepared_payload=prepared,
        )
    except (RiskControlError, LedgerError):
        return _outcome(budget_charged=False, transport_invoked=False, classification="PERMIT_ISSUANCE_FAILED")

    budget_charged = True

    if runtime.monotonic_clock_ns() > permit.freshness_deadline_monotonic_ns:
        return _outcome(budget_charged=budget_charged, transport_invoked=False, classification="FRESHNESS_EXPIRED_BEFORE_ADAPTER")

    # DSB-WRITER-008 final pre-adapter active-domain equality gate: exact
    # equality among runtime.active_contract/domain_binding, the locked
    # revision-2 ledger domain, the assessment, the NormalWriterPermit, and
    # the prepared-request logical domain metadata -- fail BEFORE transport
    # with the most specific active-domain/permit mismatch classification.
    if active_commitment is not None:
        prepared_domain_metadata = active_prepared_request_domain_metadata(
            venue_binding, canonical_request_sha256=prepared["prepared_request_sha256"],
        )
        mismatch = _require_active_gate_d_pre_adapter_equality(
            runtime=runtime, locked=locked, assessment=assessment, permit=permit,
            prepared_domain_metadata=prepared_domain_metadata,
            prepared_request_sha256=prepared["prepared_request_sha256"],
            active_trusted_read_set_id=active_trusted_read_set_id,
        )
        if mismatch is not None:
            return _outcome(budget_charged=budget_charged, transport_invoked=False, classification=mismatch)

    try:
        raw_response = adapter.invoke(permit, prepared)
    except Exception:
        return _outcome(budget_charged=budget_charged, transport_invoked=True, classification="ADAPTER_EXCEPTION")

    venue_order_id = _gate_d_extract_created_order_id(raw_response, expected_client_order_id=client_order_id)
    classification = "AMBIGUOUS"
    if venue_order_id is not None:
        try:
            status, order_row = _gate_d_read_order_status(capability, order_id=venue_order_id)
        except RunnerError as exc:
            if exc.code is RunnerFailureCode.GATE_D_READ_BUDGET_EXHAUSTED:
                raise
            status = ""
            order_row = {}
        if status == "resting":
            # Dispatch Section 16: use the real authoritative returned order
            # record, not an invented/desired value, when it is present and
            # well-formed.
            raw_remaining_count_fp = order_row.get("remaining_count_fp")
            _gate_d_record_order_identity_and_observation(
                locked, session_id=session_id, incident_id=runtime.gate_d_incident_id, client_order_id=client_order_id,
                venue_order_id=venue_order_id, market_ticker=invocation.market_ticker, outcome_side=desired.outcome_side,
                remaining_count_fp=raw_remaining_count_fp if type(raw_remaining_count_fp) is str else str(desired.quantity),
                yes_price_dollars=str(desired.yes_price),
            )
            classification = "BOUND_ACTIVE"

    _gate_d_record_http_response_classified(
        locked, session_id=session_id, request_id=request_id, raw_response=raw_response,
        write_closure_class="AUTHORITATIVE_RESULT_CLOSED" if classification == "BOUND_ACTIVE" else "UNRESOLVED",
    )

    return _outcome(budget_charged=budget_charged, transport_invoked=True, classification=classification, venue_order_id=venue_order_id)


def run_gate_d_ordinary_decision_loop(
    stage3: "_Stage3ReleaseAndNormalWriterResultV1 | _Stage3ActiveReleaseAndNormalWriterResultV1",
    runtime: "ExperimentRunnerRuntimeV1 | ExperimentRunnerRuntimeV2",
    invocation: "ExperimentRunnerInvocationV1 | ExperimentRunnerInvocationV2",
    *,
    decision_cycle_max: int = GATE_D_DECISION_CYCLE_MAX,
) -> GateDLoopResultV1:
    """Gate D entrypoint: the bounded Stage-4+ ordinary strategy write
    decision loop. Begins only from a genuine, still-open Stage-3K
    `_Stage3ReleaseAndNormalWriterResultV1` -- the real historical incident
    (`protected_unresolved_legacy_write_count` permanently 1) can never
    reach this function at all, because Gate C's own Stage-3C/3K predicates
    already reject it before RELEASE_ONLY, exactly as they did before Gate D
    existed (Spec 07 MM07-HIST-001). This function adds no new persistent
    event type, table, authority, or writer gate -- every durable mutation
    goes through the unmodified canonical `WriterEligibilityGate`/
    `LockedLedger.append_batch` surface. Production strategy planning is
    always the real `evaluate_market_maker_input` pipeline
    (`_gate_d_build_quote_plan`) -- there is no substitutable seam."""

    if type(stage3) not in (_Stage3ReleaseAndNormalWriterResultV1, _Stage3ActiveReleaseAndNormalWriterResultV1):
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="stage3 type")
    active_gate_d = type(stage3) is _Stage3ActiveReleaseAndNormalWriterResultV1
    acquisition = stage3.normal_writer_acquisition
    if (
        type(acquisition) is not NormalWriterAcquisition
        or acquisition.handle is None
        or acquisition.handle.closed
        or stage3.normal_writer_session_id != acquisition.normal_writer_session_id
    ):
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="normal_writer_acquisition")
    locked = acquisition.handle
    session_id = stage3.normal_writer_session_id
    projection = locked.projection()
    if (
        projection.risk_control_state != "WRITER_ELIGIBLE"
        or projection.active_writer_session_id != session_id
        or projection.protected_unresolved_legacy_write_count != 0
        or projection.unresolved_write_request_ids
    ):
        # Stage-4 never begins unless Stage 3K completed with a genuine
        # current NORMAL_WRITER session and zero durable unresolved writes
        # -- including the real historical incident, which this predicate
        # rejects unconditionally.
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="projection")
    if (
        type(runtime) not in (ExperimentRunnerRuntimeV1, ExperimentRunnerRuntimeV2)
        or (active_gate_d and type(runtime) is not ExperimentRunnerRuntimeV2)
        or (not active_gate_d and type(runtime) is not ExperimentRunnerRuntimeV1)
        or type(runtime.strategy_instance_id) is not str or not runtime.strategy_instance_id
        or type(runtime.minimum_spread_usd) is not Decimal
        or type(runtime.gate_d_incident_id) is not str or not runtime.gate_d_incident_id
        or type(runtime.gate_d_capability_reference_id) is not str or not runtime.gate_d_capability_reference_id
        or not callable(runtime.normal_write_transport)
        or type(runtime.risk_config) is not RiskLimitConfigV1
    ):
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="runtime gate-d bindings")
    if type(invocation) not in (ExperimentRunnerInvocationV1, ExperimentRunnerInvocationV2):
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="invocation type")
    # An active Stage-3 result MUST arrive with a V2 runtime whose active
    # contract matches, and vice-versa (no cross-path entry).
    if active_gate_d and runtime.active_contract.incident_id != stage3.active_contract.incident_id:
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="active contract mismatch")
    # Correction 02 DSB-WRITER-007 / DSB-QUOTE-003 / DSB-RUN-006: the fresh
    # trusted dynamic read-set identity that supported the active Stage-3K
    # release flows into every ordinary Gate-D assessment/permit lineage.
    active_trusted_read_set_id: str | None = None
    if active_gate_d:
        active_trusted_read_set_id = stage3.trusted_dynamic_read_set_id
        if (
            type(active_trusted_read_set_id) is not str
            or active_trusted_read_set_id[:6] != "ADRS2_"
            or len(active_trusted_read_set_id) != 70
        ):
            raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="active stage-3 trusted read-set identity")
    if type(decision_cycle_max) is not int or not (0 < decision_cycle_max <= GATE_D_DECISION_CYCLE_MAX):
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="decision_cycle_max")

    capability = _issue_gate_d_read_capability(
        process_instance_id=runtime.normal_gate.process_instance_id, ticker=invocation.market_ticker, runtime=runtime,
    )
    adapter = NormalWriteAdapter(runtime.normal_gate, runtime.normal_write_transport)

    loop_start_ns = runtime.monotonic_clock_ns()
    cutoff_ns = GATE_D_STRATEGY_ACTIVITY_CUTOFF_SECONDS * 1_000_000_000
    ordinary_writes_sent = 0
    cleanup_cancels_sent = 0  # never incremented -- MM07-CLAR-001, no cleanup lane in this loop
    cycle_results: list[GateDCycleResultV1] = []
    stop_reason = "DECISION_CYCLE_BUDGET_EXHAUSTED"

    for cycle_index in range(1, decision_cycle_max + 1):
        now_ns = runtime.monotonic_clock_ns()
        if now_ns - loop_start_ns >= cutoff_ns:
            stop_reason = "STRATEGY_CUTOFF_EXCEEDED"
            break
        if now_ns >= runtime.experiment_absolute_end_monotonic_ns:
            stop_reason = "ABSOLUTE_DEADLINE_EXCEEDED"
            break

        live_projection = locked.projection()
        if live_projection.risk_control_state != "WRITER_ELIGIBLE" or live_projection.active_writer_session_id != session_id:
            # MM07-HALT-001: ordinary strategy CANCEL/CREATE both stop at
            # HALT. Emergency exact-target cancellation remains owned
            # exclusively by the separate EMERGENCY_CONTROL_ONLY
            # architecture -- never routed through here.
            stop_reason = "HALTED"
            break

        try:
            truth = collect_authoritative_read_truth(capability, ticker=invocation.market_ticker)
        except RunnerError as exc:
            if exc.code is RunnerFailureCode.GATE_D_READ_BUDGET_EXHAUSTED:
                stop_reason = "READ_BUDGET_EXHAUSTED"
                break
            raise

        reconstructions = {
            slot: reconstruct_slot_ownership(
                locked.events, strategy_instance_id=runtime.strategy_instance_id,
                market_ticker=invocation.market_ticker, quote_slot=slot,
            )
            for slot in _GATE_D_QUOTE_SLOTS
        }

        # MM07-CLAR-003: the ONLY strategy-planning call in production Gate D.
        plan = _gate_d_build_quote_plan(
            runtime=runtime, invocation=invocation, truth=truth, reconstructions=reconstructions, projection=live_projection,
        )
        plan_valid = plan.plan_classification == "VALID_DESIRED_STATE"
        desired_by_slot = {
            MMQuoteSlot.LOWER_YES_BID.value: plan.lower_quote,
            MMQuoteSlot.UPPER_YES_ASK.value: plan.upper_quote,
        }
        reference = None
        try:
            reference = build_orderbook_reference(
                tuple((level.price, level.quantity) for level in truth.orderbook.yes_levels),
                tuple((level.price, level.quantity) for level in truth.orderbook.no_levels),
            )
        except RiskControlError:
            reference = None
        best_yes_bid = reference.best_yes_bid if reference is not None else None
        best_yes_ask = reference.best_yes_ask if reference is not None else None
        price_ranges = _parse_price_ranges(truth.market.get("price_ranges"))

        actions: dict[str, QuoteAction] = {
            slot: compare_slot(
                desired=desired_by_slot[slot], plan_valid=plan_valid,
                classification=reconstructions[slot].classification, working_order=reconstructions[slot].working_order,
                price_ranges=price_ranges, keep_reprice_distance_grid_steps=_GATE_D_KEEP_REPRICE_DISTANCE_GRID_STEPS,
                best_yes_bid=best_yes_bid, best_yes_ask=best_yes_ask,
                risk_control_state=live_projection.risk_control_state,
            )
            for slot in _GATE_D_QUOTE_SLOTS
        }

        working_orders_map = _gate_d_working_orders_map(reconstructions)
        try:
            selected = select_write_action(actions, working_orders_map)
        except QuoteLifecycleError:
            # MM06-TARGET-001: no exact proven target for a selected CANCEL
            # -> zero ordinary CANCEL sends this cycle, never a fallback
            # targeting mechanism.
            selected = None

        write_outcome: GateDWriteOutcomeV1 | None = None
        budget_stop = False
        if selected is not None:
            # MM07-CLAR-001: CANCEL_EXISTING, CANCEL_THEN_RECONCILE_BEFORE_
            # NEW, and CREATE_NEW are ALL ordinary strategy writes -- there
            # is no cleanup lane in this loop at all.
            if ordinary_writes_sent >= GATE_D_ORDINARY_WRITE_SEND_MAX:
                stop_reason = "ORDINARY_WRITE_BUDGET_EXHAUSTED"
                budget_stop = True
            elif selected.action == "CANCEL":
                write_outcome = _gate_d_execute_cancel(
                    locked=locked, session_id=session_id, capability=capability, adapter=adapter, runtime=runtime,
                    invocation=invocation, projection=live_projection, truth=truth,
                    reconstruction=reconstructions[selected.quote_slot], selected=selected,
                    active_trusted_read_set_id=active_trusted_read_set_id,
                )
                if write_outcome.budget_charged:
                    ordinary_writes_sent += 1
            else:
                write_outcome = _gate_d_execute_create(
                    locked=locked, session_id=session_id, capability=capability, adapter=adapter, runtime=runtime,
                    invocation=invocation, projection=live_projection, truth=truth,
                    reconstruction=reconstructions[selected.quote_slot], selected=selected,
                    desired=desired_by_slot[selected.quote_slot],
                    quote_plan_sha256=plan.plan_sha256, plan_input_sha256=plan.plan_input_sha256,
                    source_book_snapshot_sha256=plan.source_book_snapshot_sha256,
                    active_trusted_read_set_id=active_trusted_read_set_id,
                )
                if write_outcome.budget_charged:
                    ordinary_writes_sent += 1

        cycle_results.append(GateDCycleResultV1(
            cycle_index, capability.requests_consumed, dict(actions),
            selected.quote_slot if selected else None, selected.action if selected else None, write_outcome,
        ))
        if budget_stop:
            break
    else:
        stop_reason = "DECISION_CYCLE_BUDGET_EXHAUSTED"

    return GateDLoopResultV1(
        stop_reason=stop_reason, cycles_executed=len(cycle_results), reads_consumed=capability.requests_consumed,
        ordinary_writes_sent=ordinary_writes_sent, cleanup_cancels_sent=cleanup_cancels_sent,
        cycle_results=tuple(cycle_results),
    )


# ===========================================================================
# Section 15 -- Revision-2 ACTIVE execution-domain Stage 3A-3K path
# (KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL
# _SPEC_01_CORRECTION_02, DSB-WRITER-003..010 / DSB-DYN-001..006 /
# DSB-OPS-001..012 / DSB-BUDGET-001..007 / DSB-DOMAIN/FRESH/PAGE /
# DSB-READSET-001..005 / DSB-RISK-003..008 / DSB-READ-001..006 /
# DSB-RUN-001..006).
#
# These are EXPLICIT V2 entrypoints/types.  They never accept a
# LegacyIncidentContract or a V1 completion token; they derive incident/proof
# only from runtime.active_contract; and they carry that one active_contract
# object from Stage 3A through Stage 3K.  The legacy V1 path above is
# untouched and remains the only path a LegacyIncidentContract can enter.
# Correction 02: current Path-A truth is produced ONLY by the trusted dynamic
# pre-release acquisition boundary -- ``deterministic self-hash !=
# authoritative-source proof``.
# ===========================================================================


@dataclass(frozen=True, slots=True)
class ExperimentRunnerInvocationV2:
    """Active revision-2 bound invocation.  Unlike ExperimentRunnerInvocationV1
    it carries NO caller-supplied incident/proof: those come only from
    runtime.active_contract (DSB-WRITER-003)."""

    invocation_id: str
    market_ticker: str

    def __post_init__(self) -> None:
        for name in ("invocation_id", "market_ticker"):
            value = getattr(self, name)
            if type(value) is not str or value == "":
                raise RunnerError(RunnerFailureCode.ACTIVE_GATE_ENTRY_PRECONDITION_FAILED, detail=name)
        if _TICKER_PATTERN.fullmatch(self.market_ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="active invocation ticker grammar")


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


@dataclass(frozen=True, slots=True)
class SubaccountWideCompletenessTheoremV1:
    """DSB-RISK-004 path B: an accepted exact completeness theorem proving
    that every non-selected exchange_index for the selected subaccount has
    zero relevant economic state at the reconciliation cutoff.

    It is accepted ONLY when it is identity-bound to a separately accepted
    evidence artifact (``accepted_evidence_identity_sha256`` must be in the
    caller's accepted-evidence set) AND its
    ``reconciliation_cutoff_identity_sha256`` matches the current
    reconciliation cutoff.  A caller-created dataclass with arbitrary values
    is NOT sufficient acceptance evidence (DSB-STOP-001)."""

    conflict_domain_ref: str
    subaccount: int
    selected_exchange_index: int
    proven_zero_foreign_exchange_indices: Tuple[int, ...]
    reconciliation_cutoff_identity_sha256: str
    accepted_evidence_identity_sha256: str
    provenance_class: str  # PROJECT_EVIDENCE_RECORDED | INDEPENDENTLY_VERIFIED

    def __post_init__(self) -> None:
        if (
            type(self.conflict_domain_ref) is not str or not self.conflict_domain_ref
            or type(self.subaccount) is not int or type(self.subaccount) is bool
            or type(self.selected_exchange_index) is not int
            or type(self.proven_zero_foreign_exchange_indices) is not tuple
            or any(type(x) is not int or type(x) is bool or x < 0 for x in self.proven_zero_foreign_exchange_indices)
            or self.selected_exchange_index in self.proven_zero_foreign_exchange_indices
            or not _is_hex64(self.reconciliation_cutoff_identity_sha256)
            or not _is_hex64(self.accepted_evidence_identity_sha256)
            or self.provenance_class not in ("PROJECT_EVIDENCE_RECORDED", "INDEPENDENTLY_VERIFIED")
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="theorem malformed")


def _canonical_account_wide_row(row: object) -> list:
    """Deterministic canonical form of one account-wide row -- a sorted list
    of ``[key, str(value)]`` pairs -- so a content hash over it COMMITS to
    the full validated row content (Correction 03 F2 / F5), not just its
    scope coordinates.  A non-mapping row is unpartitionable."""
    if not isinstance(row, Mapping):
        raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="account-wide row not a mapping")
    return [[str(k), str(row[k])] for k in sorted(row.keys(), key=str)]


@dataclass(frozen=True, slots=True)
class ProvenAccountWideReadV1:
    """DSB-RISK-004 path A carrier: a PROVEN complete authoritative
    account-wide read (Correction 03 F2).

    It is completeness evidence ONLY when, at use time
    (``require_subaccount_wide_completeness``), it matches a separately bound
    ``ActiveDomainAcceptedEvidenceContractV1`` for the exact active domain:
      * ``request_classification`` is exactly ``"ACCOUNT_WIDE"`` -- an
        account-wide (not selected-route) request;
      * ``accepted_source_classification`` equals the contract's accepted
        account-wide source classification;
      * ``accepted_evidence_identity_sha256`` is one of the contract's
        accepted completeness-evidence identities (i.e. a value in the
        task-controlled accepted-evidence registry -- NOT a caller-labelled
        64-hex string);
      * ``pagination_exhausted`` is exactly ``True`` and it is bound to the
        CURRENT reconciliation cutoff;
      * ``account_scope_ref`` / ``subaccount`` equal the selected domain's.

    ``account_wide_result_hash`` is COMPUTED here from every field + every
    canonical row, so it changes when any row, pagination fact, scope fact,
    or source identity changes; ``require_subaccount_wide_completeness``
    recomputes and checks it.  A bare/empty caller object carrying only the
    right current cutoff does not satisfy Path A.  An empty result proves
    zero ONLY when it is itself the exact accepted, complete authoritative
    account-wide result (i.e. it also passes the contract-bound checks)."""

    request_classification: str
    accepted_source_classification: str
    accepted_evidence_identity_sha256: str
    account_scope_ref: str
    subaccount: int
    pagination_exhausted: bool
    reconciliation_cutoff_identity_sha256: str
    position_rows: Tuple[Mapping[str, object], ...] = ()
    working_order_rows: Tuple[Mapping[str, object], ...] = ()
    fill_rows: Tuple[Mapping[str, object], ...] = ()
    account_wide_result_hash: str = field(init=False, default="")

    def __post_init__(self) -> None:
        if (
            self.request_classification != _ACCOUNT_WIDE_REQUEST_CLASSIFICATION
            or type(self.accepted_source_classification) is not str or not self.accepted_source_classification
            or not _is_hex64(self.accepted_evidence_identity_sha256)
            or type(self.account_scope_ref) is not str or not self.account_scope_ref
            or type(self.subaccount) is not int or type(self.subaccount) is bool or not 0 <= self.subaccount <= 63
            or self.pagination_exhausted is not True
            or not _is_hex64(self.reconciliation_cutoff_identity_sha256)
            or type(self.position_rows) is not tuple
            or type(self.working_order_rows) is not tuple
            or type(self.fill_rows) is not tuple
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="proven account-wide read malformed")
        object.__setattr__(self, "account_wide_result_hash", self._compute_result_hash())

    def _compute_result_hash(self) -> str:
        return sha256_hex(canonical_json_bytes({
            "schema": "ARB_ACCOUNT_WIDE_AUTHORITATIVE_READ_RESULT_V1",
            "request_classification": self.request_classification,
            "accepted_source_classification": self.accepted_source_classification,
            "accepted_evidence_identity_sha256": self.accepted_evidence_identity_sha256,
            "account_scope_ref": self.account_scope_ref,
            "subaccount": self.subaccount,
            "pagination_exhausted": self.pagination_exhausted,
            "reconciliation_cutoff_identity_sha256": self.reconciliation_cutoff_identity_sha256,
            "position_rows": [_canonical_account_wide_row(r) for r in self.position_rows],
            "working_order_rows": [_canonical_account_wide_row(r) for r in self.working_order_rows],
            "fill_rows": [_canonical_account_wide_row(r) for r in self.fill_rows],
        }))


def _active_scope_row_int(row: Mapping[str, object], field: str) -> int | None:
    value = row.get(field)
    if type(value) is not int or type(value) is bool:
        return None
    return value


def active_scope_classify_row(
    row: Mapping[str, object], *, expected_subaccount: int, expected_exchange_index: int,
    exact_route: bool = True,
) -> str:
    """DSB-READ-001/002/003/004: classify one economic row by proven exact
    scope.  Returns "SELECTED" or "SAME_SUBACCOUNT_FOREIGN_INDEX"; raises on
    a missing/malformed scope field (DOMAIN_SCOPE_RESPONSE_AMBIGUOUS), a
    foreign subaccount (DOMAIN_SCOPE_RESPONSE_MISMATCH), or -- on an
    exact-route read -- a foreign exchange index
    (DOMAIN_ROUTE_EXCHANGE_INDEX_MISMATCH).  A missing/malformed field is
    NEVER treated as selected-domain evidence."""
    sub = _active_scope_row_int(row, "subaccount")
    idx = _active_scope_row_int(row, "exchange_index")
    if sub is None or idx is None:
        raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="row scope field missing/malformed")
    if sub != expected_subaccount:
        raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH, detail="subaccount " + str(sub))
    if idx == expected_exchange_index:
        return "SELECTED"
    if exact_route:
        raise RunnerError(RunnerFailureCode.DOMAIN_ROUTE_EXCHANGE_INDEX_MISMATCH, detail="exchange_index " + str(idx))
    return "SAME_SUBACCOUNT_FOREIGN_INDEX"


@dataclass(frozen=True, slots=True)
class ActiveAccountWidePartitionV1:
    # Same-subaccount / selected exchange_index.
    selected: Tuple[Mapping[str, object], ...]
    # Same-subaccount / other exchange_index -- retained and FOLDED INTO
    # subaccount-wide aggregate risk.
    same_subaccount_foreign_index: Tuple[Mapping[str, object], ...]
    # Other-subaccount rows -- digested/counted, NEVER folded into
    # selected-domain risk (DSB-READ-003).
    foreign_subaccount: Tuple[Mapping[str, object], ...]
    foreign_subaccount_count: int
    foreign_partition_digest_sha256: str


def partition_active_account_wide_rows(
    proven_read: "ProvenAccountWideReadV1", *, expected_subaccount: int, expected_exchange_index: int,
) -> ActiveAccountWidePartitionV1:
    """DSB-READ-003: partition the rows of a PROVEN account-wide read.

    A proven account-wide response MAY legitimately contain multiple
    subaccounts (unlike a scoped selected-subaccount response, where a
    foreign subaccount is ``DOMAIN_SCOPE_RESPONSE_MISMATCH`` --
    ``active_scope_classify_row``).  Here every row is partitioned exactly:
    selected subaccount + selected index -> ``selected``; selected subaccount
    + other index -> ``same_subaccount_foreign_index`` (folded into aggregate
    risk); another subaccount -> ``foreign_subaccount`` (digested/counted,
    NOT folded).  A row that cannot be partitioned exactly is
    ``DOMAIN_SCOPE_RESPONSE_AMBIGUOUS``.

    Correction 03 F5: ``foreign_partition_digest_sha256`` commits to the
    canonical VALIDATED CONTENT of every foreign-subaccount row (not just its
    ``(subaccount, exchange_index)`` scope), so changing a foreign row's
    order/fill/position identity or economics changes the digest.  Foreign
    rows are ordered canonically before hashing, so the digest/count are
    deterministic regardless of input row order."""
    if type(proven_read) is not ProvenAccountWideReadV1:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="proven account-wide read required")
    all_rows = tuple(proven_read.position_rows) + tuple(proven_read.working_order_rows) + tuple(proven_read.fill_rows)
    selected: list[Mapping[str, object]] = []
    foreign_index: list[Mapping[str, object]] = []
    foreign_subaccount: list[Mapping[str, object]] = []
    foreign_canonical: list[list] = []
    for row in all_rows:
        sub = _active_scope_row_int(row, "subaccount")
        idx = _active_scope_row_int(row, "exchange_index")
        if sub is None or idx is None:
            raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="unpartitionable row")
        if sub != expected_subaccount:
            foreign_subaccount.append(row)
            foreign_canonical.append([sub, idx, _canonical_account_wide_row(row)])
        elif idx == expected_exchange_index:
            selected.append(row)
        else:
            foreign_index.append(row)
    foreign_canonical.sort(key=lambda entry: canonical_json_bytes(entry))
    digest = sha256_hex(canonical_json_bytes(foreign_canonical))
    return ActiveAccountWidePartitionV1(
        tuple(selected), tuple(foreign_index), tuple(foreign_subaccount),
        len(foreign_subaccount), digest,
    )


def require_complete_active_pagination(complete: bool, *, detail: str) -> None:
    """DSB-READ-005: an incomplete/cyclic traversal is unknown, never zero."""
    if not complete:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="pagination incomplete: " + detail)


def require_subaccount_wide_completeness(
    *, domain_binding: ExecutionDomainBindingV1,
    current_reconciliation_cutoff_sha256: str,
    accepted_evidence_contract: "ActiveDomainAcceptedEvidenceContractV1",
    completeness_theorem,
    proven_account_wide_read,
) -> None:
    """DSB-RISK-003/004/005 / DSB-STOP-001 -- FAIL CLOSED.

    Correction 02: this is the STATIC positive-completeness path (Path B) and
    its structural cousin (a caller-supplied ``ProvenAccountWideReadV1``).
    For the current N1 domain the accepted static positive completeness set
    is EMPTY, so neither a ``ProvenAccountWideReadV1`` nor a
    ``SubaccountWideCompletenessTheoremV1`` can be accepted here -- current
    writer-release completeness comes ONLY from a fresh trusted Path A
    ``_ReleaseEligibleDynamicIndexDomainReadSetV2`` produced by the trusted
    dynamic pre-release acquisition boundary.  The Path-B *structure* remains
    for future domains that are separately accepted into it.

    ``accepted_evidence_contract`` is a trusted immutable
    ``ActiveDomainAcceptedEvidenceContractV1`` bound to this exact active
    domain BEFORE the run.  It is NOT a per-call caller-provided acceptance
    set.

    Until a proven read or accepted theorem passes ->
    ``STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED`` /
    ``SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN``."""
    if not _is_hex64(current_reconciliation_cutoff_sha256):
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="current cutoff identity invalid")
    if (
        type(accepted_evidence_contract) is not ActiveDomainAcceptedEvidenceContractV1
        or not accepted_evidence_contract.applies_to(domain_binding)
    ):
        raise RunnerError(
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            detail="accepted-evidence contract missing or does not apply to this active domain")

    if proven_account_wide_read is not None:
        p = proven_account_wide_read
        if type(p) is not ProvenAccountWideReadV1:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="proven read type")
        if p.request_classification != _ACCOUNT_WIDE_REQUEST_CLASSIFICATION:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="not an account-wide request classification")
        if p.accepted_source_classification != accepted_evidence_contract.account_wide_source_classification:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="account-wide source classification not accepted")
        if p.accepted_evidence_identity_sha256 not in accepted_evidence_contract.accepted_completeness_evidence_sha256:
            raise RunnerError(RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED, detail="account-wide evidence identity not in the (currently empty for N1) accepted static positive completeness set")
        if p.account_scope_ref != domain_binding.account_scope_ref or p.subaccount != domain_binding.subaccount:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="account-wide read scope mismatch")
        if p.pagination_exhausted is not True:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="account-wide pagination not exhausted")
        if p.reconciliation_cutoff_identity_sha256 != current_reconciliation_cutoff_sha256:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="account-wide read cutoff stale")
        if p.account_wide_result_hash != p._compute_result_hash():
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="account-wide result hash inconsistent")
        return

    if completeness_theorem is None:
        raise RunnerError(
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            detail="no proven account-wide read and no accepted completeness theorem",
        )
    if type(completeness_theorem) is not SubaccountWideCompletenessTheoremV1:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="theorem type")
    if (
        completeness_theorem.conflict_domain_ref != domain_binding.conflict_domain_ref
        or completeness_theorem.subaccount != domain_binding.subaccount
        or completeness_theorem.selected_exchange_index != domain_binding.exchange_index
    ):
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="theorem domain mismatch")
    if completeness_theorem.reconciliation_cutoff_identity_sha256 != current_reconciliation_cutoff_sha256:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="theorem cutoff stale")
    if completeness_theorem.accepted_evidence_identity_sha256 not in accepted_evidence_contract.accepted_completeness_evidence_sha256:
        raise RunnerError(RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED, detail="theorem evidence identity not in the (currently empty for N1) accepted static positive completeness set")
    if completeness_theorem.provenance_class != accepted_evidence_contract.accepted_provenance_class:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="theorem provenance class not accepted")


def _active_reconciliation_cutoff_sha256(truth: AuthoritativeReadTruthV1) -> str:
    """Deterministic current reconciliation-cutoff / freshness identity for
    the active read truth -- what a path-A read or a path-B theorem MUST be
    bound to."""
    return sha256_hex(canonical_json_bytes({
        "market_data_sha256": sha256_hex(canonical_json_bytes(_market_data_snapshot(truth.market, truth.orderbook))),
        "position_state": truth.position_state,
        "orders_complete": truth.orders_complete,
        "fills_complete": truth.fills_complete,
        "selected_working_order_ids": sorted(o.order_id for o in truth.working_orders),
        "selected_fill_ids": sorted(f.fill_id for f in truth.fills),
    }))


def _foreign_index_position_fill(
    row: Mapping[str, object], *, ticker: str, subaccount: int, exchange_index: int,
) -> "EconomicFillV1 | None":
    """Correction 03 F1: fold a same-subaccount foreign-index authoritative
    POSITION/inventory row into the subaccount-wide aggregate economic state
    by expressing its exact signed fixed-point inventory as one canonical
    ``EconomicFillV1`` -- the controlling ``compute_market_economic_state``
    net-position formula is derived from fills, so this is the faithful
    representation (not a synthetic working order).  A net-zero position
    contributes nothing.  A row missing an exact signed count, a mark price,
    or an authoritative as-of timestamp is malformed."""
    count = _position_count_from_row(row)  # signed fixed-point str -> Decimal, else RESPONSE_SCHEMA_INVALID
    price_raw = row.get("yes_price_dollars")
    as_of = row.get("position_as_of_utc")
    if type(price_raw) is not str or type(as_of) is not str:
        raise RunnerError(
            RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS,
            detail="foreign-index position row missing mark price / as-of timestamp")
    price = _decimal_from_price_string(price_raw)
    validate_canonical_timestamp(as_of)
    if count == 0:
        return None
    magnitude = -count if count < 0 else count
    fill_id = "posfill_" + sha256_hex(canonical_json_bytes([
        "ARB_FOREIGN_INDEX_POSITION_FILL_V1", ticker, subaccount, exchange_index,
        _canonical_account_wide_row(row),
    ]))[:24]
    return EconomicFillV1(
        ticker, fill_id, "YES" if count > 0 else "NO", magnitude, price, as_of,
    )


def _parse_same_subaccount_foreign_index_economics(
    partition: ActiveAccountWidePartitionV1, *, ticker: str, subaccount: int,
) -> "tuple[tuple, tuple]":
    """Parse the same-subaccount / other-exchange_index rows into typed
    WorkingOrderV1 / EconomicFillV1 objects so they FEED the subaccount-wide
    aggregate risk (DSB-RISK-003/004/006).  Foreign-index authoritative
    POSITION rows contribute their exact signed inventory (Correction 03 F1).
    Malformed rows fail closed; two position rows for the same foreign
    exchange_index with different content are contradictory."""
    working: list = []
    fills: list = []
    position_rows_by_index: dict[int, list] = {}
    for row in partition.same_subaccount_foreign_index:
        if "fill_id" in row:
            fills.append(_fill_from_raw(
                row, expected_ticker=ticker, expected_order_id=str(row.get("order_id", "")),
                expected_subaccount=subaccount, expected_exchange_index=None,
            ))
        elif "order_id" in row and "remaining_count_fp" in row:
            parsed = _working_order_from_raw(
                row, expected_ticker=ticker, expected_subaccount=subaccount, expected_exchange_index=None,
            )
            if parsed is not None:
                working.append(parsed)
        elif "position_count_fp" in row:
            idx = _active_scope_row_int(row, "exchange_index")
            if idx is None:
                raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="foreign-index position row scope")
            canonical = _canonical_account_wide_row(row)
            if idx in position_rows_by_index:
                if position_rows_by_index[idx] != canonical:
                    raise RunnerError(
                        RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS,
                        detail="contradictory duplicate foreign-index position rows")
                continue
            position_rows_by_index[idx] = canonical
            synthetic = _foreign_index_position_fill(
                row, ticker=ticker, subaccount=subaccount, exchange_index=idx,
            )
            if synthetic is not None:
                fills.append(synthetic)
        else:
            raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="foreign-index economic row shape")
    return tuple(working), tuple(fills)


# ===========================================================================
# Dynamic exchange-index-domain enumeration Path A -- offline test fixture
# value representation.
#
# Correction 02 (DSB-DYN-001..006): ``DynamicIndexDomainAccountWideReadV1``
# and its component observation types remain a DETERMINISTIC OFFLINE TEST
# FIXTURE representation ONLY.  They are never the authority-bearing
# production type: production release truth is the private
# ``_ReleaseEligibleDynamicIndexDomainReadSetV2`` minted only by the trusted
# dynamic pre-release acquisition boundary further below.  A test fixture is
# consumed ONLY behind ``_FakeTrustedDynamicReadAcquirerV2``.
# ===========================================================================

_CANONICAL_UTC_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _parse_canonical_utc(value: str) -> datetime:
    """Parse an already-canonical timestamp string to an aware UTC datetime."""
    return datetime.strptime(validate_canonical_timestamp(value), _CANONICAL_UTC_FMT).replace(tzinfo=timezone.utc)


def _sorted_bounded_index_domain(
    values: object, *, domain_max: int,
    count_min: int = _ACTIVE_EXCHANGE_INDEX_ENTRY_MIN,
    count_max: int = _ACTIVE_EXCHANGE_INDEX_ENTRY_MAX,
    bound_exceeded_code: "RunnerFailureCode | None" = None,
) -> "Tuple[int, ...]":
    """DSB-DOMAIN-001/002 / DSB-BUDGET-001: an exact finite integer
    exchange-index domain -- strictly increasing (hence sorted +
    de-duplicated), every member a bounded exact non-negative int
    (0 <= value <= 2147483647), and between ``count_min`` and ``count_max``
    UNIQUE entries inclusive.  A duplicate, a malformed / bool / negative /
    out-of-int32 member, or a count outside the bound fails closed.  When
    ``bound_exceeded_code`` is given it is used for the >count_max case
    (DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED); otherwise the generic
    fixture failure is used."""
    if type(values) not in (tuple, list) or not values:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="exchange-index domain empty/malformed")
    out: list[int] = list(values)
    for v in out:
        if type(v) is not int or type(v) is bool or v < 0 or v > domain_max:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="exchange-index domain member " + repr(v))
    if any(out[i] >= out[i + 1] for i in range(len(out) - 1)):
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="exchange-index domain not strictly increasing / duplicate")
    if len(out) < count_min or len(out) > count_max:
        raise RunnerError(
            bound_exceeded_code or RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            detail="exchange-index domain unique count " + str(len(out)) + " outside [" + str(count_min) + "," + str(count_max) + "]")
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ExchangeIndexStatusObservationV1:
    """One ``/exchange/status`` observation (DSB-DOMAIN-001/002).  Carries the
    exact status RESPONSE identity -- kept SEPARATE from the
    user_data_timestamp freshness identity -- and the exact finite bounded
    sorted integer exchange_index domain (1..8 unique entries) it exposed."""

    response_identity_sha256: str
    exchange_index_domain: "Tuple[int, ...]"

    def __post_init__(self) -> None:
        if not _is_hex64(self.response_identity_sha256):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="status response identity")
        object.__setattr__(
            self, "exchange_index_domain",
            _sorted_bounded_index_domain(self.exchange_index_domain, domain_max=_ACTIVE_EXCHANGE_INDEX_VALUE_MAX))


@dataclass(frozen=True, slots=True)
class UserDataFreshnessWatermarkV1:
    """One ``/exchange/user_data_timestamp`` observation (R04).  ``as_of_time``
    is approximate freshness ORDERING evidence, NOT an atomic snapshot token;
    its RESPONSE identity is kept SEPARATE from the ``/exchange/status``
    response identity."""

    response_identity_sha256: str
    as_of_time_utc: str

    def __post_init__(self) -> None:
        if not _is_hex64(self.response_identity_sha256):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="freshness watermark response identity")
        validate_canonical_timestamp(self.as_of_time_utc)


@dataclass(frozen=True, slots=True)
class PerIndexSurfaceTraversalV1:
    """Explicit per-(exchange_index, surface) private traversal: the request
    identity, the ordered per-page (response digest + economic digest +
    cursor-present) and the pagination-completion flag.  Pagination MUST be
    exhausted (R01)."""

    request_identity_sha256: str
    page_response_digests: "Tuple[str, ...]"
    page_economic_digests: "Tuple[str, ...]"
    final_cursor_absent: bool
    pagination_complete: bool

    def __post_init__(self) -> None:
        if (
            not _is_hex64(self.request_identity_sha256)
            or type(self.page_response_digests) is not tuple or not self.page_response_digests
            or type(self.page_economic_digests) is not tuple
            or len(self.page_economic_digests) != len(self.page_response_digests)
            or any(not _is_hex64(d) for d in self.page_response_digests)
            or any(not _is_hex64(d) for d in self.page_economic_digests)
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="per-index surface traversal malformed")
        if self.final_cursor_absent is not True or self.pagination_complete is not True:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="per-index surface pagination not exhausted")


@dataclass(frozen=True, slots=True)
class PerIndexTraversalV1:
    """Explicit orders/fills/positions traversal for ONE enumerated exchange
    index, with the validated same-subaccount economic rows observed there."""

    exchange_index: int
    orders: PerIndexSurfaceTraversalV1
    fills: PerIndexSurfaceTraversalV1
    positions: PerIndexSurfaceTraversalV1
    order_rows: "Tuple[Mapping[str, object], ...]" = ()
    fill_rows: "Tuple[Mapping[str, object], ...]" = ()
    position_rows: "Tuple[Mapping[str, object], ...]" = ()

    def __post_init__(self) -> None:
        if (
            type(self.exchange_index) is not int or type(self.exchange_index) is bool or self.exchange_index < 0
            or type(self.orders) is not PerIndexSurfaceTraversalV1
            or type(self.fills) is not PerIndexSurfaceTraversalV1
            or type(self.positions) is not PerIndexSurfaceTraversalV1
            or type(self.order_rows) is not tuple or type(self.fill_rows) is not tuple
            or type(self.position_rows) is not tuple
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="per-index traversal malformed")


@dataclass(frozen=True, slots=True)
class RetainedPositionSettlementReconciliationV1:
    """R06: an accepted exact settlement/reconciliation for the domain's
    retained bootstrap position, cross-checked against a fresh complete
    per-index positions enumeration that shows NO live controlled position."""

    settlement_evidence_identity_sha256: str
    ticker: str
    exchange_index: int
    conflict_domain_ref: str
    market_result: str
    settled_time_utc: str
    yes_count_fp: str
    settlement_response_identity_sha256: str

    def __post_init__(self) -> None:
        try:
            settled = Decimal(self.yes_count_fp) if type(self.yes_count_fp) is str else None
        except InvalidOperation:
            settled = None
        if (
            not _is_hex64(self.settlement_evidence_identity_sha256)
            or not _is_hex64(self.settlement_response_identity_sha256)
            or type(self.ticker) is not str or _TICKER_PATTERN.fullmatch(self.ticker) is None
            or type(self.exchange_index) is not int or type(self.exchange_index) is bool or self.exchange_index < 0
            or type(self.conflict_domain_ref) is not str or not self.conflict_domain_ref
            or self.market_result not in ("yes", "no")
            or settled is None or not settled.is_finite() or settled <= 0
        ):
            raise RunnerError(RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED, detail="settlement reconciliation malformed")
        validate_canonical_timestamp(self.settled_time_utc)


def _settlement_reconciliation_canonical(sr: "RetainedPositionSettlementReconciliationV1 | None") -> object:
    if sr is None:
        return None
    return {
        "settlement_evidence_identity_sha256": sr.settlement_evidence_identity_sha256,
        "ticker": sr.ticker, "exchange_index": sr.exchange_index,
        "conflict_domain_ref": sr.conflict_domain_ref, "market_result": sr.market_result,
        "settled_time_utc": sr.settled_time_utc, "yes_count_fp": sr.yes_count_fp,
        "settlement_response_identity_sha256": sr.settlement_response_identity_sha256,
    }


@dataclass(frozen=True, slots=True)
class DynamicIndexDomainAccountWideReadV1:
    """R1-B03 Correction 04 Path A: a fresh, dynamically enumerated
    subaccount-wide read set.  It represents the empirically established
    interface shape (P02): a current ``/exchange/status`` index domain, an
    explicit orders/fills/positions traversal for EVERY index in that domain
    with pagination exhausted, before/after status + freshness observations,
    and (when the domain has a retained bootstrap position) an accepted
    settlement reconciliation.

    ``read_set_identity_sha256`` is caller-supplied but MUST equal the value
    recomputed from the full object by
    ``compute_dynamic_index_domain_read_set_identity`` -- a caller-chosen
    hash that is not recomputed is rejected (R03)."""

    accepted_source_classification: str
    index_domain_enumeration_evidence_identity_sha256: str
    account_scope_ref: str
    subaccount: int
    selected_exchange_index: int
    status_before: ExchangeIndexStatusObservationV1
    status_after: ExchangeIndexStatusObservationV1
    freshness_before: UserDataFreshnessWatermarkV1
    freshness_after: UserDataFreshnessWatermarkV1
    per_index_traversals: "Tuple[PerIndexTraversalV1, ...]"
    selected_route_reconciliation_cutoff_sha256: str
    read_set_identity_sha256: str
    settlement_reconciliation: "RetainedPositionSettlementReconciliationV1 | None" = None

    def __post_init__(self) -> None:
        if (
            type(self.accepted_source_classification) is not str or not self.accepted_source_classification
            or not _is_hex64(self.index_domain_enumeration_evidence_identity_sha256)
            or type(self.account_scope_ref) is not str or not self.account_scope_ref
            or type(self.subaccount) is not int or type(self.subaccount) is bool or not 0 <= self.subaccount <= 63
            or type(self.selected_exchange_index) is not int or type(self.selected_exchange_index) is bool
            or self.selected_exchange_index < 0
            or type(self.status_before) is not ExchangeIndexStatusObservationV1
            or type(self.status_after) is not ExchangeIndexStatusObservationV1
            or type(self.freshness_before) is not UserDataFreshnessWatermarkV1
            or type(self.freshness_after) is not UserDataFreshnessWatermarkV1
            or type(self.per_index_traversals) is not tuple or not self.per_index_traversals
            or any(type(t) is not PerIndexTraversalV1 for t in self.per_index_traversals)
            or not _is_hex64(self.selected_route_reconciliation_cutoff_sha256)
            or not _is_hex64(self.read_set_identity_sha256)
            or (self.settlement_reconciliation is not None
                and type(self.settlement_reconciliation) is not RetainedPositionSettlementReconciliationV1)
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="dynamic index-domain read malformed")
        # R02: exact before/after domain stability.
        if self.status_before.exchange_index_domain != self.status_after.exchange_index_domain:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="exchange-index domain changed before/after")
        domain = self.status_before.exchange_index_domain
        if self.selected_exchange_index not in domain:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="selected exchange_index absent from enumerated domain")
        traversed = tuple(t.exchange_index for t in self.per_index_traversals)
        if traversed != domain:
            raise RunnerError(
                RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
                detail="per-index traversals do not exactly enumerate the status domain in canonical order")
        # R04: freshness ORDERING (monotonic nondecreasing), not T0 == T1.
        if _parse_canonical_utc(self.freshness_after.as_of_time_utc) < _parse_canonical_utc(self.freshness_before.as_of_time_utc):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="user_data_timestamp clock regression (T1 < T0)")


def compute_dynamic_index_domain_read_set_identity(
    read: DynamicIndexDomainAccountWideReadV1, *,
    active_domain_binding_id: str,
    active_domain_binding_sha256: str,
    active_contract_sha256: str,
    risk_config_sha256: str,
) -> str:
    """R03: the SINGLE composite current-read / reconciliation-cutoff identity
    bound to ALL pages.  Commits to the active domain binding + active
    contract + risk config, the account scope + selected sub/index, the
    ``/exchange/status`` before/after RESPONSE identities + domains (kept
    SEPARATE from the user_data_timestamp identities), the
    user_data_timestamp before/after RESPONSE identities + as_of values, and
    -- for every exchange index in the canonical sorted domain -- the
    orders/fills/positions request identities + every page response digest +
    every page economic digest + cursor-completion + pagination-completion +
    the validated rows.  Changing any of these MUST change the identity."""
    def _surface(s: PerIndexSurfaceTraversalV1) -> dict:
        return {
            "request_identity_sha256": s.request_identity_sha256,
            "page_response_digests": list(s.page_response_digests),
            "page_economic_digests": list(s.page_economic_digests),
            "final_cursor_absent": s.final_cursor_absent,
            "pagination_complete": s.pagination_complete,
        }

    per_index = [
        {
            "exchange_index": t.exchange_index,
            "orders": _surface(t.orders), "fills": _surface(t.fills), "positions": _surface(t.positions),
            "order_rows": [_canonical_account_wide_row(r) for r in t.order_rows],
            "fill_rows": [_canonical_account_wide_row(r) for r in t.fill_rows],
            "position_rows": [_canonical_account_wide_row(r) for r in t.position_rows],
        }
        for t in sorted(read.per_index_traversals, key=lambda x: x.exchange_index)
    ]
    return sha256_hex(canonical_json_bytes({
        "schema": "ARB_DYNAMIC_INDEX_DOMAIN_ACCOUNT_WIDE_READ_SET_V1",
        "active_domain_binding_id": active_domain_binding_id,
        "active_domain_binding_sha256": active_domain_binding_sha256,
        "active_contract_sha256": active_contract_sha256,
        "risk_config_sha256": risk_config_sha256,
        "account_scope_ref": read.account_scope_ref,
        "subaccount": read.subaccount,
        "selected_exchange_index": read.selected_exchange_index,
        "accepted_source_classification": read.accepted_source_classification,
        "index_domain_enumeration_evidence_identity_sha256": read.index_domain_enumeration_evidence_identity_sha256,
        "status_before_response_identity_sha256": read.status_before.response_identity_sha256,
        "status_before_exchange_index_domain": list(read.status_before.exchange_index_domain),
        "status_after_response_identity_sha256": read.status_after.response_identity_sha256,
        "status_after_exchange_index_domain": list(read.status_after.exchange_index_domain),
        "user_data_timestamp_before_response_identity_sha256": read.freshness_before.response_identity_sha256,
        "user_data_timestamp_before_as_of_time_utc": read.freshness_before.as_of_time_utc,
        "user_data_timestamp_after_response_identity_sha256": read.freshness_after.response_identity_sha256,
        "user_data_timestamp_after_as_of_time_utc": read.freshness_after.as_of_time_utc,
        "per_index": per_index,
        "selected_route_reconciliation_cutoff_sha256": read.selected_route_reconciliation_cutoff_sha256,
        "settlement_reconciliation": _settlement_reconciliation_canonical(read.settlement_reconciliation),
    }))


def _dynamic_read_controlled_live_position_contracts(
    read: DynamicIndexDomainAccountWideReadV1, *, ticker: str, subaccount: int,
) -> Decimal:
    """Sum of the signed live position contracts for ``ticker`` across EVERY
    enumerated exchange index (R06 -- a fresh complete per-index positions
    enumeration must contain no live controlled position)."""
    total = Decimal("0")
    for t in read.per_index_traversals:
        for row in t.position_rows:
            row_ticker = row.get("ticker")
            if row_ticker != ticker:
                continue
            sub = _active_scope_row_int(row, "subaccount")
            if sub is not None and sub != subaccount:
                raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH, detail="other-subaccount controlled position row")
            total += _position_count_from_row(row)
    return total


def _parse_dynamic_index_domain_foreign_economics(
    read: DynamicIndexDomainAccountWideReadV1, *, ticker: str, subaccount: int,
) -> "tuple[tuple, tuple]":
    """R05: fold EVERY enumerated FOREIGN (non-selected) exchange index's
    validated same-subaccount orders/fills/positions into typed
    WorkingOrderV1 / EconomicFillV1 objects for the subaccount-wide aggregate.
    Selected-index economics already enter via the scoped selected-route
    read.  An other-subaccount row -> DOMAIN_SCOPE_RESPONSE_MISMATCH; a
    row whose ``exchange_index`` disagrees with its traversal, or an
    unpartitionable row -> DOMAIN_SCOPE_RESPONSE_AMBIGUOUS; a contradictory
    duplicate foreign-index position -> fail closed."""
    working: list = []
    fills: list = []
    seen_position: dict[tuple, list] = {}
    for t in read.per_index_traversals:
        if t.exchange_index == read.selected_exchange_index:
            continue
        for row in tuple(t.order_rows) + tuple(t.fill_rows) + tuple(t.position_rows):
            sub = _active_scope_row_int(row, "subaccount")
            idx = _active_scope_row_int(row, "exchange_index")
            if sub is None:
                raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="foreign-index row scope")
            if sub != subaccount:
                raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH, detail="other-subaccount row on enumerated index")
            if idx != t.exchange_index:
                raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="row exchange_index disagrees with traversal")
            if "fill_id" in row:
                fills.append(_fill_from_raw(
                    row, expected_ticker=ticker, expected_order_id=str(row.get("order_id", "")),
                    expected_subaccount=subaccount, expected_exchange_index=None,
                ))
            elif "order_id" in row and "remaining_count_fp" in row:
                parsed = _working_order_from_raw(
                    row, expected_ticker=ticker, expected_subaccount=subaccount, expected_exchange_index=None,
                )
                if parsed is not None:
                    working.append(parsed)
            elif "position_count_fp" in row:
                canonical = _canonical_account_wide_row(row)
                if t.exchange_index in seen_position:
                    if seen_position[t.exchange_index] != canonical:
                        raise RunnerError(
                            RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS,
                            detail="contradictory duplicate foreign-index position row")
                    continue
                seen_position[t.exchange_index] = canonical
                synthetic = _foreign_index_position_fill(
                    row, ticker=ticker, subaccount=subaccount, exchange_index=t.exchange_index,
                )
                if synthetic is not None:
                    fills.append(synthetic)
            else:
                raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="foreign-index economic row shape")
    return tuple(working), tuple(fills)


def require_dynamic_index_domain_completeness(
    read: "DynamicIndexDomainAccountWideReadV1", *,
    domain_binding: ExecutionDomainBindingV1,
    active_contract: "ActiveExecutionDomainContractV1",
    risk_config: "RiskLimitConfigV1",
    accepted_evidence_contract: "ActiveDomainAcceptedEvidenceContractV1",
    current_selected_route_cutoff_sha256: str,
    now_monotonic_ns: int,
    now_utc: str,
    t0_wall_sample_utc: "str | None" = None,
    t1_wall_sample_utc: "str | None" = None,
) -> str:
    """Correction 04 Path A -- FAIL CLOSED (requirements 01-08).  Validates the
    fresh dynamically enumerated read set against the separately bound
    domain-scoped ``accepted_evidence_contract``, recomputes and checks the
    composite read-set identity, applies the EXISTING risk/reconciliation
    freshness/deadline configuration to the user_data_timestamp ordering, and
    -- when the domain has a retained bootstrap position -- requires an
    accepted settlement reconciliation with a fresh complete per-index
    positions enumeration and no live controlled position.

    Returns the retained-position classification:
    ``"NO_RETAINED_BOOTSTRAP_POSITION"`` or
    ``"RETAINED_POSITION_TERMINALLY_SETTLED"``.  Any mismatch raises before
    any economics are merged (hence before Stage 3F / Gate D / transport)."""
    if type(read) is not DynamicIndexDomainAccountWideReadV1:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="dynamic index-domain read type")
    if (
        type(accepted_evidence_contract) is not ActiveDomainAcceptedEvidenceContractV1
        or not accepted_evidence_contract.applies_to(domain_binding)
    ):
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="accepted-evidence contract does not apply")
    if not _is_hex64(current_selected_route_cutoff_sha256):
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="current selected-route cutoff invalid")

    # R07: role-specific accepted evidence.  P01 (negative) can never satisfy.
    evid = read.index_domain_enumeration_evidence_identity_sha256
    if evid in _NEGATIVE_COMPLETENESS_EVIDENCE_SHA256:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="negative completeness evidence cannot qualify index-domain enumeration")
    if evid not in accepted_evidence_contract.accepted_index_domain_enumeration_evidence_sha256:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="index-domain enumeration evidence not separately accepted")
    if read.accepted_source_classification != accepted_evidence_contract.account_wide_source_classification:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="account-wide source classification not accepted")
    if (
        read.account_scope_ref != domain_binding.account_scope_ref
        or read.subaccount != domain_binding.subaccount
        or read.selected_exchange_index != domain_binding.exchange_index
    ):
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="dynamic read scope mismatch")

    # R02 / Correction 06 (BLOCK-05-02): a COUNT bound only.  Each individual
    # index value is already validated as ``0 <= value <= 2147483647`` inside
    # ``ExchangeIndexStatusObservationV1.__post_init__`` (no P02-derived
    # maximum-index-value); here the number of UNIQUE current indices must not
    # exceed the contract's ``dynamic_exchange_index_entry_max``.  A ninth
    # unique index fails BEFORE the first per-index portfolio traversal.
    domain = read.status_before.exchange_index_domain
    if len(domain) > accepted_evidence_contract.dynamic_exchange_index_entry_max:
        raise RunnerError(
            RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED,
            detail="unique current exchange-index count " + str(len(domain))
            + " exceeds dynamic_exchange_index_entry_max=" + str(accepted_evidence_contract.dynamic_exchange_index_entry_max))
    if domain_binding.exchange_index not in domain:
        raise RunnerError(
            RunnerFailureCode.DYNAMIC_READ_SELECTED_INDEX_NOT_IN_DOMAIN,
            detail="selected execution-binding exchange_index is not a member of the observed status domain")

    if read.selected_route_reconciliation_cutoff_sha256 != current_selected_route_cutoff_sha256:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="dynamic read selected-route cutoff stale")

    # R04 / DSB-FRESH-002/003 / Correction 06 (BLOCK-05-04): freshness
    # ORDERING + the exact 30s/5s active-V2 caps + the EXISTING authoritative
    # RiskLimitConfigV1.state_integrity limits, all CONJUNCTIVE.  The 30s/5s
    # caps never REPLACE a stricter existing threshold; whichever applicable
    # predicate is stricter wins.  T1 >= T0 is required; T1 == T0 and T1 > T0
    # are both acceptable; T1 < T0 fails; the two trusted wall-clock samples
    # used for freshness must be nondecreasing.
    lim = risk_config.state_integrity
    t0 = _parse_canonical_utc(read.freshness_before.as_of_time_utc)
    t1 = _parse_canonical_utc(read.freshness_after.as_of_time_utc)
    t0_sample = _parse_canonical_utc(t0_wall_sample_utc if t0_wall_sample_utc is not None else now_utc)
    t1_sample = _parse_canonical_utc(t1_wall_sample_utc if t1_wall_sample_utc is not None else now_utc)
    if type(now_monotonic_ns) is not int or now_monotonic_ns < 0:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_CLOCK_REGRESSION, detail="freshness monotonic clock invalid")
    if t1 < t0:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_REGRESSION, detail="user_data_timestamp T1 < T0")
    if t1_sample < t0_sample:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_CLOCK_REGRESSION, detail="trusted wall-clock freshness sample regressed between T0 and T1")
    for bookend, as_of, sample in (("T0", t0, t0_sample), ("T1", t1, t1_sample)):
        age_ms = (sample - as_of).total_seconds() * 1000.0
        future_ms = (as_of - sample).total_seconds() * 1000.0
        # Active-V2 acquisition caps (DSB-FRESH-003).
        if age_ms > _PRE_RELEASE_FRESHNESS_MAX_AGE_MS:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_STALE, detail=bookend + " age exceeds pre_release_freshness_max_age_ms=30000")
        if future_ms > _PRE_RELEASE_FRESHNESS_FUTURE_SKEW_MAX_MS:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_FUTURE_SKEW, detail=bookend + " future skew exceeds pre_release_freshness_future_skew_max_ms=5000")
        # Existing authoritative state-integrity limits (stricter wins).
        if age_ms > lim.max_reconciliation_lag_ms:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_STALE, detail=bookend + " age exceeds state_integrity.max_reconciliation_lag_ms")
        if future_ms > lim.max_future_wall_clock_skew_ms:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_FUTURE_SKEW, detail=bookend + " future skew exceeds state_integrity.max_future_wall_clock_skew_ms")
    window_ms = (t1 - t0).total_seconds() * 1000.0
    if window_ms > lim.reconciliation_read_deadline_ms:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_STALE, detail="T0..T1 window exceeds state_integrity.reconciliation_read_deadline_ms")

    # R03: recompute the composite identity from the full object.
    expected = compute_dynamic_index_domain_read_set_identity(
        read,
        active_domain_binding_id=active_contract.domain_binding_id,
        active_domain_binding_sha256=active_contract.domain_binding_sha256,
        active_contract_sha256=active_contract.contract_sha256,
        risk_config_sha256=risk_config.sha256,
    )
    if read.read_set_identity_sha256 != expected:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="dynamic read-set composite identity mismatch")

    # R06: retained bootstrap-position settlement reconciliation.
    rbp = accepted_evidence_contract.retained_bootstrap_position
    if rbp is None:
        return "NO_RETAINED_BOOTSTRAP_POSITION"
    sr = read.settlement_reconciliation
    if type(sr) is not RetainedPositionSettlementReconciliationV1:
        raise RunnerError(RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED, detail="retained bootstrap position present; read set carries no settlement reconciliation")
    if sr.settlement_evidence_identity_sha256 in _NEGATIVE_COMPLETENESS_EVIDENCE_SHA256:
        raise RunnerError(RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED, detail="negative evidence cannot qualify settlement reconciliation")
    if sr.settlement_evidence_identity_sha256 not in accepted_evidence_contract.accepted_settlement_reconciliation_evidence_sha256:
        raise RunnerError(RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED, detail="settlement reconciliation evidence not separately accepted")
    if (
        sr.ticker != rbp["ticker"]
        or sr.exchange_index != rbp["exchange_index"]
        or sr.conflict_domain_ref != rbp["conflict_domain_ref"]
    ):
        raise RunnerError(RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED, detail="settlement reconciliation does not match the retained bootstrap position identity")
    live = _dynamic_read_controlled_live_position_contracts(read, ticker=rbp["ticker"], subaccount=domain_binding.subaccount)
    if live != 0:
        raise RunnerError(RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED, detail="a live controlled position is still present across the enumerated domain")
    return "RETAINED_POSITION_TERMINALLY_SETTLED"


def collect_active_authoritative_read_truth(
    capability: PreReleaseReadCapabilityV1, *, ticker: str,
    domain_binding: ExecutionDomainBindingV1,
    accepted_evidence_contract: "ActiveDomainAcceptedEvidenceContractV1",
    completeness_theorem=None,
    proven_account_wide_read=None,
    dynamic_index_domain_read=None,
    active_contract: "ActiveExecutionDomainContractV1 | None" = None,
    risk_config: "RiskLimitConfigV1 | None" = None,
    now_monotonic_ns: "int | None" = None,
    now_utc: "str | None" = None,
) -> AuthoritativeReadTruthV1:
    """Stage 3E for the active revision-2 path -- FAIL CLOSED scope /
    partition / completeness contract (DSB-READ-001..006 / DSB-RISK-003..006):

      * every selected-route row proves exact subaccount+exchange_index
        (handled inside the scoped capability);
      * pagination completeness is required -- incomplete => unknown;
      * subaccount-wide completeness is required and default CLOSED: it is
        proven ONLY by a ``ProvenAccountWideReadV1`` (path A) or a
        ``SubaccountWideCompletenessTheoremV1`` (path B) that BOTH bind to
        the CURRENT reconciliation cutoff AND to the separately bound,
        domain-scoped ``accepted_evidence_contract`` -- checked FIRST, before
        any economics are merged;
      * only after that check passes, the proven read's same-subaccount
        other-index working orders / fills / authoritative POSITION rows are
        PARSED and MERGED into the truth so they feed the subaccount-wide
        aggregate risk; other-subaccount rows are digested/counted, never
        merged;
      * a read failure never synthesizes empty truth."""
    truth = collect_authoritative_read_truth(capability, ticker=ticker)

    require_complete_active_pagination(truth.orders_complete, detail="orders")
    require_complete_active_pagination(truth.fills_complete, detail="fills")

    current_cutoff = _active_reconciliation_cutoff_sha256(truth)

    if dynamic_index_domain_read is not None:
        # Correction 04 Path A: explicit dynamic exchange-index-domain
        # enumeration.  Fresh read set required (P02 historical rows can never
        # mint current writer eligibility).
        if (
            type(active_contract) is not ActiveExecutionDomainContractV1
            or type(risk_config) is not RiskLimitConfigV1
            or type(now_monotonic_ns) is not int
            or type(now_utc) is not str
        ):
            raise RunnerError(
                RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
                detail="dynamic index-domain Path A requires active_contract / risk_config / now")
        require_dynamic_index_domain_completeness(
            dynamic_index_domain_read,
            domain_binding=domain_binding,
            active_contract=active_contract,
            risk_config=risk_config,
            accepted_evidence_contract=accepted_evidence_contract,
            current_selected_route_cutoff_sha256=current_cutoff,
            now_monotonic_ns=now_monotonic_ns,
            now_utc=now_utc,
        )
        extra_working, extra_fills = _parse_dynamic_index_domain_foreign_economics(
            dynamic_index_domain_read, ticker=ticker, subaccount=domain_binding.subaccount,
        )
        if extra_working or extra_fills:
            truth = _dataclass_replace(
                truth,
                working_orders=truth.working_orders + extra_working,
                fills=truth.fills + extra_fills,
            )
        return truth

    require_subaccount_wide_completeness(
        domain_binding=domain_binding,
        current_reconciliation_cutoff_sha256=current_cutoff,
        accepted_evidence_contract=accepted_evidence_contract,
        completeness_theorem=completeness_theorem,
        proven_account_wide_read=proven_account_wide_read,
    )

    if proven_account_wide_read is not None:
        partition = partition_active_account_wide_rows(
            proven_account_wide_read,
            expected_subaccount=domain_binding.subaccount,
            expected_exchange_index=domain_binding.exchange_index,
        )
        extra_working, extra_fills = _parse_same_subaccount_foreign_index_economics(
            partition, ticker=ticker, subaccount=domain_binding.subaccount,
        )
        if extra_working or extra_fills:
            truth = _dataclass_replace(
                truth,
                working_orders=truth.working_orders + extra_working,
                fills=truth.fills + extra_fills,
            )

    return truth


def assemble_active_release_evaluation_state_v1(
    runtime: ExperimentRunnerRuntimeV2,
    truth: AuthoritativeReadTruthV1,
    projection: SafetyProjection,
    *,
    trusted_dynamic_read_set_id: str,
) -> ActiveReleaseEvaluationStateV1:
    """Stage 3F (active): build the exact ActiveReleaseEvaluationStateV1
    whose incident/proof come ONLY from runtime.active_contract
    (DSB-WRITER-004) and which commits to the exact private trusted dynamic
    read-set identity (``ADRS2_<64hex>``) that supported the release.  Reuses
    the shared Stage-3F assembly body so the trusted-evidence / T0-T1
    coherence / fresh-vs-durable matching logic is identical to the legacy
    path."""
    if type(runtime) is not ExperimentRunnerRuntimeV2:
        raise RunnerError(RunnerFailureCode.ACTIVE_GATE_ENTRY_PRECONDITION_FAILED, detail="runtime type")
    if (
        type(trusted_dynamic_read_set_id) is not str
        or trusted_dynamic_read_set_id[:6] != "ADRS2_"
        or len(trusted_dynamic_read_set_id) != 70
    ):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_COMPOSITE_IDENTITY_MISMATCH, detail="trusted_dynamic_read_set_id shape")
    inner = _assemble_release_state_core(
        incident_id=runtime.active_contract.incident_id,
        writer_proof_id=runtime.active_contract.writer_proof_id,
        runtime=runtime, truth=truth, projection=projection,
    )
    snap = inner._snapshot()
    return ActiveReleaseEvaluationStateV1(
        process_instance_id=runtime.normal_gate.process_instance_id,
        active_contract=runtime.active_contract,
        trusted_dynamic_read_set_id=trusted_dynamic_read_set_id,
        risk_config=snap[5],
        risk_snapshot=snap[6],
        reconciliation_snapshot=snap[7],
        market_freshness=snap[8],
        reconciliation_freshness=snap[9],
        venue_defense_evidence=snap[10],
        normal_gate=runtime.normal_gate,
        emergency_gate=runtime.emergency_gate,
    )


# ===========================================================================
# Correction 02 Sections 9-13 -- the trusted dynamic pre-release acquisition
# boundary (DSB-DYN-001..006 / DSB-OPS-001..012 / DSB-BUDGET-001..007 /
# DSB-DOMAIN/FRESH/PAGE / DSB-READSET-001..005).
#
# Normative rule: ``deterministic self-hash != authoritative-source proof``.
# Only this closed, process-local, single-use boundary may create the private
# release-eligible current-read type.  A caller that knows every status/page/
# row/cursor/freshness identity and the composite hash still cannot
# manufacture release-eligible current truth.
# ===========================================================================


class ActivePreReleaseReadOperationV2(enum.StrEnum):
    """DSB-OPS-001 -- the exact closed active-V2 pre-release read surface.  No
    write / cancel / transfer / account-management / settlement / WebSocket /
    production / arbitrary-HTTP operation exists on this capability."""

    GET_EXCHANGE_STATUS = "GET_EXCHANGE_STATUS"
    GET_USER_DATA_TIMESTAMP = "GET_USER_DATA_TIMESTAMP"
    GET_MARKET = "GET_MARKET"
    GET_MARKET_ORDERBOOK = "GET_MARKET_ORDERBOOK"
    GET_ORDERS = "GET_ORDERS"
    GET_ORDER = "GET_ORDER"
    GET_FILLS = "GET_FILLS"
    GET_POSITIONS = "GET_POSITIONS"


class ActivePreReleaseReadAuthClassV2(enum.StrEnum):
    """DSB-OPS-002 -- the exact closed authentication classification.  There is
    no production-auth class and no write/signing class.  This SPEC/offline
    implementation task uses NO credentials."""

    PUBLIC_NO_AUTH = "PUBLIC_NO_AUTH"
    DEMO_SIGNED_PRIVATE_READ = "DEMO_SIGNED_PRIVATE_READ"


# DSB-OPS-003 -- exact method / path / auth binding.  All paths are under the
# selected Kalshi Demo REST origin and the ``/trade-api/v2`` API root;
# redirects are never followed.
_ACTIVE_V2_API_ROOT = "/trade-api/v2"
_ACTIVE_V2_OP_BINDING: Mapping[ActivePreReleaseReadOperationV2, Tuple[str, str, ActivePreReleaseReadAuthClassV2]] = MappingProxyType({
    ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS: ("GET", _ACTIVE_V2_API_ROOT + "/exchange/status", ActivePreReleaseReadAuthClassV2.PUBLIC_NO_AUTH),
    ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP: ("GET", _ACTIVE_V2_API_ROOT + "/exchange/user_data_timestamp", ActivePreReleaseReadAuthClassV2.PUBLIC_NO_AUTH),
    ActivePreReleaseReadOperationV2.GET_MARKET: ("GET", _ACTIVE_V2_API_ROOT + "/markets/{ticker}", ActivePreReleaseReadAuthClassV2.PUBLIC_NO_AUTH),
    ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK: ("GET", _ACTIVE_V2_API_ROOT + "/markets/{ticker}/orderbook", ActivePreReleaseReadAuthClassV2.DEMO_SIGNED_PRIVATE_READ),
    ActivePreReleaseReadOperationV2.GET_ORDERS: ("GET", _ACTIVE_V2_API_ROOT + "/portfolio/orders", ActivePreReleaseReadAuthClassV2.DEMO_SIGNED_PRIVATE_READ),
    ActivePreReleaseReadOperationV2.GET_ORDER: ("GET", _ACTIVE_V2_API_ROOT + "/portfolio/orders/{order_id}", ActivePreReleaseReadAuthClassV2.DEMO_SIGNED_PRIVATE_READ),
    ActivePreReleaseReadOperationV2.GET_FILLS: ("GET", _ACTIVE_V2_API_ROOT + "/portfolio/fills", ActivePreReleaseReadAuthClassV2.DEMO_SIGNED_PRIVATE_READ),
    ActivePreReleaseReadOperationV2.GET_POSITIONS: ("GET", _ACTIVE_V2_API_ROOT + "/portfolio/positions", ActivePreReleaseReadAuthClassV2.DEMO_SIGNED_PRIVATE_READ),
})

# DSB-BUDGET-002/003 -- exact per-surface maxima and the independently frozen
# total.  Derivation: 2 status + 2 freshness + 1 market + 1 orderbook + 2
# exact-order supplements + 8 indices * (2 orders + 4 fills + 2 positions) = 72.
_ACTIVE_V2_STATUS_REQUEST_MAX = 2
_ACTIVE_V2_FRESHNESS_REQUEST_MAX = 2
_ACTIVE_V2_MARKET_REQUEST_MAX = 1
_ACTIVE_V2_ORDERBOOK_REQUEST_MAX = 1
_ACTIVE_V2_ORDER_REQUEST_MAX = 2
_ACTIVE_V2_ORDERS_PAGE_MAX = 2
_ACTIVE_V2_FILLS_PAGE_MAX = 4
_ACTIVE_V2_POSITIONS_PAGE_MAX = 2
_ACTIVE_V2_PORTFOLIO_PAGE_LIMIT = 1000
PRE_RELEASE_READ_REQUEST_MAX_V2 = (
    _ACTIVE_V2_STATUS_REQUEST_MAX + _ACTIVE_V2_FRESHNESS_REQUEST_MAX
    + _ACTIVE_V2_MARKET_REQUEST_MAX + _ACTIVE_V2_ORDERBOOK_REQUEST_MAX
    + _ACTIVE_V2_ORDER_REQUEST_MAX
    + _ACTIVE_EXCHANGE_INDEX_ENTRY_MAX * (
        _ACTIVE_V2_ORDERS_PAGE_MAX + _ACTIVE_V2_FILLS_PAGE_MAX + _ACTIVE_V2_POSITIONS_PAGE_MAX
    )
)
assert PRE_RELEASE_READ_REQUEST_MAX_V2 == 72, PRE_RELEASE_READ_REQUEST_MAX_V2

# DSB-FRESH-003 -- ADDITIONAL active-V2 acquisition caps.  They are
# conjunctive with the existing authoritative ``RiskLimitConfigV1.state_
# integrity`` predicates and never relax them; the stricter applicable
# predicate wins (Marco approval binding interpretation).
_PRE_RELEASE_FRESHNESS_MAX_AGE_MS = 30000
_PRE_RELEASE_FRESHNESS_FUTURE_SKEW_MAX_MS = 5000

# DSB-READSET-005 -- the exact accepted dynamic source identity.
_ACTIVE_DYNAMIC_SOURCE_IDENTITY: Mapping[str, object] = MappingProxyType({
    "source_contract_id": "ARB_KALSHI_DEMO_ACTIVE_DYNAMIC_PRE_RELEASE_READ_V2",
    "inherited_binding_index_sha256": OPERATION_BINDING_INDEX_SHA256,
    "p02_evidence_sha256": _P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,
    "p01_negative_evidence_sha256": _P01_NEGATIVE_COMPLETENESS_EVIDENCE_SHA256,
    "operation_contract_revision": 2,
})
_ADRS2_READ_SET_SCHEMA = "ARB_KALSHI_DEMO_ACTIVE_DYNAMIC_PRE_RELEASE_READ_SET_V2"
_RELEASE_ELIGIBLE_READ_SET_KEY = object()
_TRUSTED_DYNAMIC_CAPABILITY_KEY = object()
# Process-local, unexported issuer sentinel (DSB-DYN-003).  It is NOT an
# authority substitute and is never serialized into the deterministic
# read-set hash; it is only an in-process anti-injection lineage check.
_ACTIVE_TRUSTED_ISSUER_SENTINEL = object()


def _trusted_local_release_projection_identity(opened: "OpenResult | None") -> str:
    """Deterministic identity of the trusted local release projection observed
    at Stage 3B, committed into the composite read-set (DSB-READSET-001)."""
    projection = getattr(opened, "projection", None)
    if projection is None:
        return sha256_hex(canonical_json_bytes({"trusted_local_release_projection": "UNAVAILABLE"}))
    return sha256_hex(canonical_json_bytes({
        "trusted_local_release_projection": "OBSERVED",
        "conflict_domain_ref": getattr(projection, "conflict_domain_ref", None),
        "risk_control_state": getattr(projection, "risk_control_state", None),
        "risk_state_epoch": getattr(projection, "risk_state_epoch", None),
        "active_risk_config_sha256": getattr(projection, "active_risk_config_sha256", None),
        "history_completeness": getattr(projection, "history_completeness", None),
        "trusted_sequence": getattr(projection, "trusted_sequence", None),
        "trusted_event_hash": getattr(projection, "trusted_event_hash", None),
        "terminal_event_hash": getattr(projection, "terminal_event_hash", None),
    }))


# ===========================================================================
# Correction 06 (BLOCK-05-01 / BLOCK-05-05) -- the closed active-V2 transport
# mapping, the private V2 request-preparation machinery, the ONE converged
# private acquisition-result representation, and the production live
# acquisition state machine.
#
# ``ActivePreReleaseReadOperationV2`` stays the controlling SEMANTIC 8-op
# surface.  The two active-V2 bookend GETs reach the existing
# ``send_operation_request`` transport boundary + the existing strict generic
# JSON decoder through the CLOSED INTERNAL ``RunnerOperation`` transport
# identifiers below -- never through the legacy V1
# ``PRE_RELEASE_READ_OPERATIONS`` / ``_GENERIC_REQUEST_OPERATIONS`` /
# ``prepare_runner_operation_request`` / ``PreReleaseReadCapabilityV1`` path,
# which is preserved byte/semantically unchanged.
# ===========================================================================

# Active-V2 -> internal transport identifier.  ``GET_MARKET_ORDERBOOK`` maps
# for identity/decoder symmetry only; it is dispatched through the inherited
# accepted ``fetch_orderbook`` path, never re-implemented (DSB-OPS-003/011).
_ACTIVE_V2_OP_TO_RUNNER_OP: Mapping[ActivePreReleaseReadOperationV2, RunnerOperation] = MappingProxyType({
    ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS: RunnerOperation.GET_EXCHANGE_STATUS,
    ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP: RunnerOperation.GET_USER_DATA_TIMESTAMP,
    ActivePreReleaseReadOperationV2.GET_MARKET: RunnerOperation.GET_MARKET,
    ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK: RunnerOperation.GET_MARKET_ORDERBOOK,
    ActivePreReleaseReadOperationV2.GET_ORDERS: RunnerOperation.GET_ORDERS,
    ActivePreReleaseReadOperationV2.GET_ORDER: RunnerOperation.GET_ORDER,
    ActivePreReleaseReadOperationV2.GET_FILLS: RunnerOperation.GET_FILLS,
    ActivePreReleaseReadOperationV2.GET_POSITIONS: RunnerOperation.GET_POSITIONS,
})
# The exact closed set of internal transport identifiers the active-V2
# acquirer may drive.  Disjoint from ``WRITE_OPERATIONS``.
_ACTIVE_V2_TRANSPORT_OPERATIONS: "frozenset[RunnerOperation]" = frozenset(_ACTIVE_V2_OP_TO_RUNNER_OP.values())
assert _ACTIVE_V2_TRANSPORT_OPERATIONS.isdisjoint(WRITE_OPERATIONS)
assert len(_ACTIVE_V2_OP_TO_RUNNER_OP) == 8

_ACTIVE_V2_PORTFOLIO_OPS = (
    ActivePreReleaseReadOperationV2.GET_ORDERS,
    ActivePreReleaseReadOperationV2.GET_FILLS,
    ActivePreReleaseReadOperationV2.GET_POSITIONS,
)


def _active_v2_canonical_query(
    operation: ActivePreReleaseReadOperationV2, *,
    subaccount: int, exchange_index: "int | None", cursor_in: str,
) -> "Tuple[Tuple[str, str], ...]":
    """DSB-OPS-004 -- the exact query key/value sequence.  Status / freshness /
    market / orderbook / exact-order carry NO ARB query.  The three paginated
    portfolio surfaces carry exactly ``subaccount, exchange_index, limit=1000``
    on the first page and additionally the exact nonempty ``cursor`` on a
    continuation page.  No other optional filter is ever added -- no ticker,
    order id, status, event ticker, or timestamp narrowing."""
    if operation not in _ACTIVE_V2_PORTFOLIO_OPS:
        return ()
    pairs = [
        ("subaccount", str(subaccount)),
        ("exchange_index", str(exchange_index)),
        ("limit", str(_ACTIVE_V2_PORTFOLIO_PAGE_LIMIT)),
    ]
    if cursor_in:
        pairs.append(("cursor", cursor_in))
    return tuple(pairs)


def _active_v2_request_identity_sha256(
    operation: ActivePreReleaseReadOperationV2, *,
    active_contract: "ActiveExecutionDomainContractV1",
    domain_binding: "ExecutionDomainBindingV1",
    exchange_index: "int | None",
    page_ordinal: int,
    cursor_in: str = "",
    ticker: "str | None" = None,
    order_id: "str | None" = None,
) -> str:
    """DSB-READSET-002 -- deterministic request identity.  Commits operation
    enum / method / exact path / auth class / canonical query sequence /
    active_contract_sha256 / domain_binding_sha256 / subaccount /
    exchange_index (when applicable) / page ordinal / cursor input (when
    applicable) / selected ticker or order id (when applicable).  NEVER a
    secret, signature, private key, auth header, or secret environment
    value."""
    method, path, auth = _ACTIVE_V2_OP_BINDING[operation]
    return sha256_hex(canonical_json_bytes({
        "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_READ_REQUEST_IDENTITY_V1",
        "operation": operation.value,
        "method": method,
        "path": path,
        "auth_class": auth.value,
        "canonical_query": [
            [k, v] for k, v in _active_v2_canonical_query(
                operation, subaccount=domain_binding.subaccount,
                exchange_index=exchange_index, cursor_in=cursor_in,
            )
        ],
        "active_contract_sha256": active_contract.contract_sha256,
        "domain_binding_sha256": active_contract.domain_binding_sha256,
        "subaccount": domain_binding.subaccount,
        "exchange_index": exchange_index,
        "page_ordinal": page_ordinal,
        "cursor_input": cursor_in,
        "selected_ticker": ticker,
        "selected_order_id": order_id,
    }))


def _prepare_active_v2_request(
    operation: ActivePreReleaseReadOperationV2, *,
    subaccount: int,
    exchange_index: "int | None" = None,
    ticker: "str | None" = None,
    order_id: "str | None" = None,
    cursor: "str | None" = None,
    request_ordinal: int,
    uuid_factory: "Callable[[], uuid.UUID]",
) -> PreparedRunnerOperationRequestV1:
    """Correction 06 (CL-4) -- the CLOSED private V2 request preparation for
    all eight ``ActivePreReleaseReadOperationV2`` members.  Pure / offline: it
    derives method / exact path / wire URL / canonical query from the frozen
    DSB-OPS-003 binding + the exact DSB-OPS-004 query contract ONLY.  Nothing
    here can construct an arbitrary method / path / host / body, add an
    unlisted query key, or follow a redirect.  ``GET_MARKET_ORDERBOOK`` is
    prepared here for request-identity purposes only -- transport goes through
    the inherited accepted ``fetch_orderbook`` path, never re-implemented."""
    method, api_path, auth = _ACTIVE_V2_OP_BINDING[operation]
    rendered = api_path
    if operation in (ActivePreReleaseReadOperationV2.GET_MARKET, ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK):
        if type(ticker) is not str or _TICKER_PATTERN.fullmatch(ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="active-V2 ticker grammar")
        rendered = rendered.replace("{ticker}", ticker)
    elif operation is ActivePreReleaseReadOperationV2.GET_ORDER:
        if type(order_id) is not str or _ORDER_ID_PATTERN.fullmatch(order_id) is None:
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="active-V2 order_id grammar")
        rendered = rendered.replace("{order_id}", order_id)
    if cursor is not None and operation not in _ACTIVE_V2_PORTFOLIO_OPS:
        raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="cursor not permitted for this V2 operation")
    if cursor is not None and (type(cursor) is not str or cursor == ""):
        raise RunnerError(RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION, detail="V2 cursor empty")
    query_pairs = list(_active_v2_canonical_query(
        operation, subaccount=subaccount, exchange_index=exchange_index,
        cursor_in=cursor if type(cursor) is str else "",
    ))
    canonical_query = _canonical_query_string(query_pairs)
    query_suffix = "" if canonical_query == "" else "?" + canonical_query
    auth_mode = (
        "PUBLIC_UNSIGNED_FOR_THIS_OPERATION"
        if auth is ActivePreReleaseReadAuthClassV2.PUBLIC_NO_AUTH else "AUTHENTICATED"
    )
    return PreparedRunnerOperationRequestV1(
        operation=_ACTIVE_V2_OP_TO_RUNNER_OP[operation],
        method=method,
        host=DEMO_HOST,
        full_path=rendered,
        wire_request_url=DEMO_ORIGIN + rendered + query_suffix,
        signed_path_without_query=rendered,
        query=tuple(query_pairs),
        body=None,
        auth_mode=auth_mode,
        request_id=f"req_{uuid_factory().hex}",
    )


# --- the ONE converged private acquisition-result / page-commitment shape ---


@dataclass(frozen=True, slots=True)
class _ActiveV2PageCommitmentV1:
    """DSB-READSET-001 / BLOCK-05-05 -- one ordered immutable commitment per
    ACTUAL portfolio request.  ``response_sha256`` is the digest of the exact
    raw response body bytes; ``canonical_content_digest_sha256`` is a
    SEPARATELY computed digest over the canonical validated
    page/economic content -- the two are distinct concepts computed
    separately."""

    operation: str
    exchange_index: int
    page_ordinal: int
    request_identity_sha256: str
    response_sha256: str
    canonical_content_digest_sha256: str
    cursor_in: str
    cursor_out: str
    row_count: int
    row_content_sha256: "Tuple[str, ...]"

    def __post_init__(self) -> None:
        if (
            type(self.operation) is not str or not self.operation
            or type(self.exchange_index) is not int or type(self.exchange_index) is bool or self.exchange_index < 0
            or type(self.page_ordinal) is not int or type(self.page_ordinal) is bool or self.page_ordinal < 1
            or not _is_hex64(self.request_identity_sha256)
            or not _is_hex64(self.response_sha256)
            or not _is_hex64(self.canonical_content_digest_sha256)
            or type(self.cursor_in) is not str or type(self.cursor_out) is not str
            or type(self.row_count) is not int or type(self.row_count) is bool or self.row_count < 0
            or type(self.row_content_sha256) is not tuple
            or len(self.row_content_sha256) != self.row_count
            or any(not _is_hex64(h) for h in self.row_content_sha256)
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active-V2 page commitment malformed")


@dataclass(frozen=True, slots=True)
class _ActiveV2SurfaceCommitmentV1:
    """One (exchange_index, surface) traversal: the ordered page commitments,
    the page count, and ``pagination_exhausted`` (always True for a
    release-eligible read).  Cursor thread: first page ``cursor_in == ""``;
    each page's ``cursor_in`` equals the previous page's nonempty
    ``cursor_out``; the final page's ``cursor_out == ""`` (terminal)."""

    operation: str
    exchange_index: int
    pages: "Tuple[_ActiveV2PageCommitmentV1, ...]"
    page_count: int
    pagination_exhausted: bool

    def __post_init__(self) -> None:
        if (
            type(self.pages) is not tuple or not self.pages
            or any(type(p) is not _ActiveV2PageCommitmentV1 for p in self.pages)
            or type(self.page_count) is not int or self.page_count != len(self.pages)
            or self.pagination_exhausted is not True
            or any(p.page_ordinal != i + 1 for i, p in enumerate(self.pages))
            or any(p.operation != self.operation for p in self.pages)
            or any(p.exchange_index != self.exchange_index for p in self.pages)
            or self.pages[0].cursor_in != ""
            or self.pages[-1].cursor_out != ""
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active-V2 surface commitment malformed")
        for prev, cur in zip(self.pages, self.pages[1:]):
            if not prev.cursor_out or cur.cursor_in != prev.cursor_out:
                raise RunnerError(RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE, detail="active-V2 page cursor thread break")


@dataclass(frozen=True, slots=True)
class _ActiveV2PerIndexCommitmentV1:
    exchange_index: int
    orders: _ActiveV2SurfaceCommitmentV1
    fills: _ActiveV2SurfaceCommitmentV1
    positions: _ActiveV2SurfaceCommitmentV1
    order_rows: "Tuple[Mapping[str, object], ...]" = ()
    fill_rows: "Tuple[Mapping[str, object], ...]" = ()
    position_rows: "Tuple[Mapping[str, object], ...]" = ()

    def __post_init__(self) -> None:
        for surf, op in (
            (self.orders, ActivePreReleaseReadOperationV2.GET_ORDERS),
            (self.fills, ActivePreReleaseReadOperationV2.GET_FILLS),
            (self.positions, ActivePreReleaseReadOperationV2.GET_POSITIONS),
        ):
            if type(surf) is not _ActiveV2SurfaceCommitmentV1 or surf.exchange_index != self.exchange_index or surf.operation != op.value:
                raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active-V2 per-index commitment malformed")


@dataclass(frozen=True, slots=True)
class _ActiveV2BookendCommitmentV1:
    """Status / freshness bookend commitment.  For status: exact request
    identity + raw response SHA + canonical validated status-content SHA +
    exact sorted derived domain.  For freshness: exact request identity + raw
    response SHA + exact parsed ``as_of_time`` + the trusted wall-clock sample
    taken immediately after successful parse."""

    operation: str
    bookend: str
    request_identity_sha256: str
    response_sha256: str
    canonical_content_sha256: str
    exact_sorted_domain: "Tuple[int, ...]" = ()
    as_of_time_utc: str = ""
    wall_sample_utc: str = ""

    def __post_init__(self) -> None:
        if (
            self.bookend not in ("BEFORE", "AFTER")
            or not _is_hex64(self.request_identity_sha256)
            or not _is_hex64(self.response_sha256)
            or not _is_hex64(self.canonical_content_sha256)
            or type(self.exact_sorted_domain) is not tuple
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active-V2 bookend commitment malformed")


@dataclass(frozen=True, slots=True)
class _ActiveV2ContentCommitmentV1:
    """Selected market / orderbook commitment: exact request identity, the
    exact accepted response/snapshot identity, and a SEPARATELY computed
    canonical consumed economic-content digest (DSB-OPS-011 / CL-3)."""

    operation: str
    request_identity_sha256: str
    response_identity_sha256: str
    canonical_consumed_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_hex64(self.request_identity_sha256)
            or not _is_hex64(self.response_identity_sha256)
            or not _is_hex64(self.canonical_consumed_digest_sha256)
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active-V2 content commitment malformed")


@dataclass(frozen=True, slots=True)
class _ActiveV2OrderSupplementCommitmentV1:
    order_id: str
    request_identity_sha256: str
    response_sha256: str
    canonical_content_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.order_id) is not str or _ORDER_ID_PATTERN.fullmatch(self.order_id) is None
            or not _is_hex64(self.request_identity_sha256)
            or not _is_hex64(self.response_sha256)
            or not _is_hex64(self.canonical_content_sha256)
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active-V2 exact-order supplement malformed")


@dataclass(frozen=True, slots=True)
class _ActiveV2AcquiredReadV1:
    """DSB-READSET-001 / BLOCK-05-05 / CL-1 -- the ONE private
    acquisition-result representation produced by BOTH the production live
    acquirer and the offline fake seam.  Carries every ordered page/bookend
    commitment plus the derived ``DynamicIndexDomainAccountWideReadV1``
    fixture (so the existing completeness / foreign-economics predicates run
    unchanged) and the scoped selected-route ``AuthoritativeReadTruthV1``.
    There is no weaker or alternate shape and one ADRS2 minting
    implementation consumes it."""

    status_before: _ActiveV2BookendCommitmentV1
    status_after: _ActiveV2BookendCommitmentV1
    freshness_before: _ActiveV2BookendCommitmentV1
    freshness_after: _ActiveV2BookendCommitmentV1
    selected_market: _ActiveV2ContentCommitmentV1
    selected_orderbook: _ActiveV2ContentCommitmentV1
    per_index: "Tuple[_ActiveV2PerIndexCommitmentV1, ...]"
    exact_order_supplements: "Tuple[_ActiveV2OrderSupplementCommitmentV1, ...]"
    d0: "Tuple[int, ...]"
    d1: "Tuple[int, ...]"
    fixture: "DynamicIndexDomainAccountWideReadV1"
    selected_route_truth: "AuthoritativeReadTruthV1"
    t0_wall_sample_utc: str
    t1_wall_sample_utc: str

    def __post_init__(self) -> None:
        if (
            type(self.fixture) is not DynamicIndexDomainAccountWideReadV1
            or type(self.selected_route_truth) is not AuthoritativeReadTruthV1
            or type(self.d0) is not tuple or type(self.d1) is not tuple
        ):
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active-V2 acquired read malformed")
        if self.d0 != self.d1:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_CHANGED, detail="D1 != D0")
        if tuple(p.exchange_index for p in self.per_index) != self.d0:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="per-index commitments do not enumerate D0 ascending")
        if self.status_before.exact_sorted_domain != self.d0 or self.status_after.exact_sorted_domain != self.d1:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_CHANGED, detail="status bookend domain != derived domain")
        if len(self.exact_order_supplements) > _ACTIVE_V2_ORDER_REQUEST_MAX:
            raise RunnerError(RunnerFailureCode.GET_ORDER_TARGET_LIMIT_EXCEEDED, detail="more than two exact-order supplements")
        validate_canonical_timestamp(self.t0_wall_sample_utc)
        validate_canonical_timestamp(self.t1_wall_sample_utc)


# --- the closed private V2 transport adapter ------------------------------


class _ActiveV2OperationAdapter:
    """DSB-DYN-001/006 / CL-4 -- the CLOSED module-private bridge from
    ``ActivePreReleaseReadOperationV2`` to the already-supplied
    ``ExperimentRunnerRuntimeV2`` transport dependencies
    (``send_operation_request`` + the accepted ``fetch_orderbook``).  It adds
    NO caller-supplied transport/acquirer seam, follows NO redirect, performs
    NO automatic retry, and never widens the operation surface beyond the
    exact eight-op contract.  Every JSON GET flows through the SAME strict
    generic response decoder as every other read."""

    __slots__ = ("_runtime", "_absolute_invocation_deadline_ns", "_process_instance_id")

    def __init__(self, runtime: "ExperimentRunnerRuntimeV2", *, absolute_invocation_deadline_ns: int) -> None:
        if type(runtime) is not ExperimentRunnerRuntimeV2:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="adapter runtime type")
        if type(absolute_invocation_deadline_ns) is not int or absolute_invocation_deadline_ns < 0:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="adapter deadline")
        self._runtime = runtime
        self._absolute_invocation_deadline_ns = absolute_invocation_deadline_ns
        self._process_instance_id = runtime.normal_gate.process_instance_id

    def _deadline(self, operation: ActivePreReleaseReadOperationV2, ordinal: int) -> OperationDeadlineV1:
        # DSB-BUDGET-006: request_deadline = min(absolute_invocation_deadline,
        # request_start_monotonic + 10000 ms).  ``OperationDeadlineV1.create``
        # applies exactly that min() against the passed experiment end.
        return OperationDeadlineV1.create(
            process_instance_id=self._process_instance_id,
            operation_name=operation.value,
            request_ordinal=ordinal,
            started_monotonic_ns=self._runtime.monotonic_clock_ns(),
            experiment_absolute_end_monotonic_ns=self._absolute_invocation_deadline_ns,
            uuid_factory=self._runtime.uuid_factory,
        )

    def issue_json(
        self,
        capability: "_TrustedDynamicPreReleaseReadCapabilityV2",
        operation: ActivePreReleaseReadOperationV2,
        *,
        ordinal: int,
        subaccount: int,
        exchange_index: "int | None" = None,
        ticker: "str | None" = None,
        order_id: "str | None" = None,
        cursor: "str | None" = None,
    ) -> "Tuple[Mapping[str, object], bytes, OperationDeadlineV1]":
        """Correction 07 C07-E / DSB-BUDGET-005 -- exact charge boundary:

        start monotonic sample + create request deadline -> check
        BEFORE_PREPARATION -> ``_prepare_active_v2_request`` (local
        construction) -> complete ALL local request validation -> check
        AFTER_PREPARATION / inherited local-signing boundary -> ``capability.
        charge(operation)`` exactly once -> IMMEDIATELY
        ``send_operation_request(...)``.

        A local request-construction/validation failure (anything before the
        ``charge`` call) consumes ZERO V2 budget.  Any request that reaches
        the charge boundary stays consumed on every later HTTP / timeout /
        parse / scope failure -- there is no refund and no retry.

        The one ``OperationDeadlineV1`` identity is returned to the caller so
        the SAME deadline covers operation-specific schema / scope / cursor /
        row-hash / page-digest / accepted-commitment construction, with one
        final check after the accepted result exists (C07-F)."""
        deadline = self._deadline(operation, ordinal)
        check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.BEFORE_PREPARATION)
        # Every fallible LOCAL step -- operation->transport identifier mapping,
        # method/path/query/auth/request-id construction and validation --
        # completes BEFORE the charge (C07-E / clarification 1).
        runner_op = _ACTIVE_V2_OP_TO_RUNNER_OP[operation]
        prepared = _prepare_active_v2_request(
            operation, subaccount=subaccount, exchange_index=exchange_index,
            ticker=ticker, order_id=order_id, cursor=cursor,
            request_ordinal=ordinal, uuid_factory=self._runtime.uuid_factory,
        )
        # All local request construction/validation is now complete.
        check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_PREPARATION)
        check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SIGNING)
        # Charge exactly once; the next fallible action is the transport call.
        capability.charge(operation)
        raw = self._runtime.send_operation_request(runner_op, prepared, deadline)
        check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_TRANSPORT)
        parsed = _decode_and_validate_runner_json_response(
            runner_op, raw_response=raw, deadline=deadline,
            now_monotonic_ns=self._runtime.monotonic_clock_ns,
        )
        raw_bytes = raw.body_bytes if type(raw.body_bytes) is bytes else b""
        return parsed, raw_bytes, deadline

    def issue_orderbook(
        self, capability: "_TrustedDynamicPreReleaseReadCapabilityV2", *, ordinal: int, ticker: str,
    ) -> "Tuple[object, OperationDeadlineV1]":
        """DSB-OPS-003/011 / CL-3 / C07-E -- the inherited accepted
        ``fetch_orderbook`` path.  Exact local ticker/request preparation and
        validation happen FIRST; then the capability is charged exactly once;
        then ``fetch_orderbook`` is invoked immediately.  A local preparation
        failure consumes ZERO budget.  The parsed snapshot identity is NEVER
        treated as a raw-body SHA.  The request ``OperationDeadlineV1`` is
        returned so the caller's snapshot validation / canonical identity /
        economic digest / selected-orderbook commitment construction all
        occur before one final check against the SAME deadline (C07-F)."""
        deadline = self._deadline(ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK, ordinal)
        check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.BEFORE_PREPARATION)
        # Exact local ticker/request preparation + validation BEFORE any charge.
        _prepare_active_v2_request(
            ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK,
            subaccount=capability.runtime.domain_binding.subaccount, ticker=ticker,
            request_ordinal=ordinal, uuid_factory=self._runtime.uuid_factory,
        )
        check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_PREPARATION)
        capability.charge(ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK)
        result = self._runtime.fetch_orderbook(ticker, deadline)
        check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_TRANSPORT)
        if isinstance(result, OrderBookHalt):
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="orderbook halt " + result.code.value)
        if type(result) is not KalshiNativeOrderBookSnapshot:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="orderbook return type")
        if result.market_ticker != ticker:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="orderbook ticker mismatch")
        return result, deadline


# --- exact response parsers for the active-V2 status / freshness / pages ---

_ACTIVE_V2_SURFACE_PAGE_MAX = MappingProxyType({
    ActivePreReleaseReadOperationV2.GET_ORDERS: _ACTIVE_V2_ORDERS_PAGE_MAX,
    ActivePreReleaseReadOperationV2.GET_FILLS: _ACTIVE_V2_FILLS_PAGE_MAX,
    ActivePreReleaseReadOperationV2.GET_POSITIONS: _ACTIVE_V2_POSITIONS_PAGE_MAX,
})
_ACTIVE_V2_SURFACE_ROW_KEY = MappingProxyType({
    ActivePreReleaseReadOperationV2.GET_ORDERS: "orders",
    ActivePreReleaseReadOperationV2.GET_FILLS: "fills",
    ActivePreReleaseReadOperationV2.GET_POSITIONS: "market_positions",
})


def _active_v2_status_domain_and_content(parsed: "Mapping[str, object]") -> "Tuple[Tuple[int, ...], str]":
    """DSB-OPS-006 / DSB-DOMAIN-001/002 -- derive the exact sorted unique
    integer exchange-index domain from a ``GET_EXCHANGE_STATUS`` body and a
    canonical status-content digest kept SEPARATE from the raw response SHA.
    Malformed / duplicate / out-of-range / >8-unique fail closed with the
    precise ``DYNAMIC_READ_STATUS_DOMAIN_*`` code before any traversal."""
    if type(parsed.get("exchange_active")) is not bool or type(parsed.get("trading_active")) is not bool:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_MALFORMED, detail="status required booleans")
    rows = parsed.get("exchange_index_statuses")
    if type(rows) is not list or not rows:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_MALFORMED, detail="exchange_index_statuses missing/non-array/empty")
    seen: set[int] = set()
    values: list[int] = []
    canonical_rows: list[dict] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_MALFORMED, detail="status row not an object")
        idx = row.get("exchange_index")
        if type(idx) is not int or type(idx) is bool or idx < 0 or idx > _ACTIVE_EXCHANGE_INDEX_VALUE_MAX:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_MALFORMED, detail="status row exchange_index " + repr(idx))
        if type(row.get("exchange_active")) is not bool or type(row.get("trading_active")) is not bool:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_MALFORMED, detail="status row required booleans")
        if "intra_exchange_transfers_active" in row and type(row.get("intra_exchange_transfers_active")) is not bool:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_MALFORMED, detail="status row intra_exchange_transfers_active type")
        if "description" in row and type(row.get("description")) is not str:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_MALFORMED, detail="status row description type")
        if idx in seen:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_DUPLICATE, detail="duplicate exchange_index " + str(idx))
        seen.add(idx)
        values.append(idx)
        canonical_rows.append({k: str(row[k]) for k in sorted(row.keys(), key=str)})
    domain = _sorted_bounded_index_domain(
        tuple(sorted(values)), domain_max=_ACTIVE_EXCHANGE_INDEX_VALUE_MAX,
        bound_exceeded_code=RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED,
    )
    content_sha = sha256_hex(canonical_json_bytes({
        "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_STATUS_CONTENT_V1",
        "exchange_active": parsed["exchange_active"],
        "trading_active": parsed["trading_active"],
        "exchange_index_statuses": sorted(canonical_rows, key=lambda r: int(r["exchange_index"])),
    }))
    return domain, content_sha


def _active_v2_as_of_time(parsed: "Mapping[str, object]") -> str:
    """DSB-OPS-007 -- the single ARB-consumed ``as_of_time`` field: a
    nonempty timezone-aware RFC3339 string producing a finite UTC instant.
    Naive/invalid/duplicate-key/non-string fails closed."""
    raw = parsed.get("as_of_time")
    if type(raw) is not str or raw == "":
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_MALFORMED, detail="as_of_time missing/non-string")
    try:
        # ARB canonical UTC form (``...%f Z``): a finite timezone-aware instant.
        # A naive / invalid / malformed-offset value fails closed here.
        canonical = validate_canonical_timestamp(raw)
        _parse_canonical_utc(canonical)
    except Exception as exc:  # noqa: BLE001 - any parse failure is fail-closed
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_MALFORMED, detail="as_of_time not a finite canonical UTC instant") from exc
    return canonical


_ACTIVE_V2_SUBACCOUNT_FIELD = "subaccount_number"


def _active_v2_row_ticker(row: "Mapping[str, object]", *, operation_detail: str) -> str:
    """The row's OWN exact market ticker (DSB-OPS-008/009/010 / Correction 07
    C07-C: each accepted economic row keeps its own ticker; it is never
    forced to the selected market).  Predecessor validation only: an exact
    non-empty built-in ``str``.  A missing / non-string / empty ticker is
    malformed current truth."""
    ticker = row.get("ticker")
    if type(ticker) is not str or ticker == "":
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail=operation_detail + " row ticker missing/non-string/empty")
    return ticker


def _active_v2_order_fill_scope(
    row: "Mapping[str, object]", *, subaccount: int, exchange_index: int, operation: "ActivePreReleaseReadOperationV2",
) -> str:
    """Correction 07 C07-B / DSB-OPS-008/009 -- exact active-V2 GET_ORDERS /
    GET_FILLS row scope.  EVERY consumed row REQUIRES:

    ``subaccount_number`` : exact built-in int, bool prohibited, non-null,
    == ``runtime.domain_binding.subaccount``;
    ``exchange_index``    : exact built-in int, bool prohibited, non-null,
    == the exact request index.

    A missing required field is malformed current truth -- the request scope
    is NEVER used as a default.  A legacy/synthetic ``subaccount`` key, if
    present, is a CONTRADICTION check only (must equal the runtime subaccount)
    and is NOT a substitute for the required ``subaccount_number``.  Returns
    the row's own exact ticker.  This function NEVER touches the legacy V1
    ``_working_order_from_raw`` / ``_fill_from_raw`` schema."""
    if _ACTIVE_V2_SUBACCOUNT_FIELD not in row:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail=operation.value + " row missing required subaccount_number")
    sn = row.get(_ACTIVE_V2_SUBACCOUNT_FIELD)
    if type(sn) is not int or type(sn) is bool or sn != subaccount:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail=operation.value + " subaccount_number not exact int == runtime subaccount")
    if "exchange_index" not in row:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail=operation.value + " row missing required exchange_index")
    ei = row.get("exchange_index")
    if type(ei) is not int or type(ei) is bool or ei != exchange_index:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail=operation.value + " exchange_index not exact int == request index")
    legacy = row.get("subaccount")
    if legacy is not None and (type(legacy) is not int or type(legacy) is bool or legacy != subaccount):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail=operation.value + " contradictory legacy subaccount field")
    return _active_v2_row_ticker(row, operation_detail=operation.value)


def _active_v2_position_scope(row: "Mapping[str, object]", *, subaccount: int, exchange_index: int) -> str:
    """Correction 07 C07-B / DSB-OPS-010 -- exact active-V2 GET_POSITIONS
    ``market_positions`` row scope.  REQUIRED exact ``exchange_index`` ==
    request index.  ``subaccount_number``, when exposed, must be an exact int
    == runtime subaccount.  A legacy/synthetic ``subaccount`` key, if present,
    is a CONTRADICTION check only (must equal the runtime subaccount) and does
    not substitute for a missing order/fill ``subaccount_number``.  Returns
    the row's own exact ticker."""
    if "exchange_index" not in row:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail="position row missing required exchange_index")
    ei = row.get("exchange_index")
    if type(ei) is not int or type(ei) is bool or ei != exchange_index:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail="position exchange_index not exact int == request index")
    sn = row.get(_ACTIVE_V2_SUBACCOUNT_FIELD)
    if sn is not None and (type(sn) is not int or type(sn) is bool or sn != subaccount):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail="position subaccount_number not exact int == runtime subaccount")
    legacy = row.get("subaccount")
    if legacy is not None and (type(legacy) is not int or type(legacy) is bool or legacy != subaccount):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail="position contradictory legacy subaccount field")
    return _active_v2_row_ticker(row, operation_detail="GET_POSITIONS")


def _active_v2_working_order_from_row(
    row: "Mapping[str, object]", *, subaccount: int, exchange_index: int,
) -> "WorkingOrderV1 | None":
    """Correction 07 -- active-V2-specific working-order conversion.  Uses the
    row's OWN ticker and the exact ``subaccount_number`` scope; a non-resting
    order returns ``None``.  The legacy V1 ``_working_order_from_raw`` schema
    is left untouched."""
    ticker = _active_v2_order_fill_scope(
        row, subaccount=subaccount, exchange_index=exchange_index,
        operation=ActivePreReleaseReadOperationV2.GET_ORDERS,
    )
    order_id = _require_exact_str(
        _require_field(row, "order_id", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 order_id type")
    if order_id == "":
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 order_id blank")
    status = _require_exact_str(
        _require_field(row, "status", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 order status type")
    if status != "resting":
        return None
    side = row.get("side")
    outcome_side = {"yes": "YES", "no": "NO"}.get(side) if type(side) is str else None
    if outcome_side is None:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 order side")
    remaining = _decimal_from_quantity_string(_require_field(row, "remaining_count_fp", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID))
    price = _decimal_from_price_string(_require_field(row, "yes_price_dollars", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID))
    return WorkingOrderV1(ticker, order_id, outcome_side, remaining, price)


@dataclass(frozen=True, slots=True)
class _ActiveV2ParsedFillV1:
    """Correction 09 C09-A / DSB-OPS-009 -- the ONE private parsed active-V2
    fill identity.  It carries the COMPLETE inherited exact fill identity,
    including the ``order_id`` that the public ``EconomicFillV1`` risk
    projection does not model, so DSB-READ-005 exactly-once/conflict
    comparison compares the full identity rather than only the economic
    projection.  Frozen: equality is exact field-by-field equality, preserving
    the predecessor's Decimal/temporal comparison semantics."""

    fill_id: str
    order_id: str
    subaccount: int
    exchange_index: int
    ticker: str
    outcome_side: str
    quantity: Decimal
    yes_price: Decimal
    created_time_utc: str

    def economic_fill(self) -> "EconomicFillV1":
        """The existing public risk projection -- the ``EconomicFillV1`` model
        is UNCHANGED by Correction 09; ``order_id`` stays private identity."""
        return EconomicFillV1(
            self.ticker, self.fill_id, self.outcome_side,
            self.quantity, self.yes_price, self.created_time_utc,
        )


def _active_v2_parsed_fill_from_row(
    row: "Mapping[str, object]", *, subaccount: int, exchange_index: int,
) -> "_ActiveV2ParsedFillV1":
    """Correction 09 C09-A -- the ONE shared active-V2 fill parser.  Every
    consumer (C08 page-acceptance economic validation, selected-route truth,
    account-wide aggregate extras, and the C09-C domain-wide fill-identity
    proof) parses through THIS function; there is no second/weaker fill
    parser.  Uses the row's OWN ticker and the exact ``subaccount_number``
    scope, and preserves the inherited exact identity / Decimal / temporal
    validation of the legacy V1 ``_fill_from_raw`` -- including its REQUIRED
    exact ``order_id`` (C09-B: omitted by Correction 08).  The legacy V1
    ``_fill_from_raw`` schema itself is left untouched."""
    ticker = _active_v2_order_fill_scope(
        row, subaccount=subaccount, exchange_index=exchange_index,
        operation=ActivePreReleaseReadOperationV2.GET_FILLS,
    )
    fill_id = _require_exact_str(
        _require_field(row, "fill_id", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 fill_id type")
    if fill_id == "":
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 fill_id blank")
    # C09-B / DSB-OPS-009: order_id is inherited exact fill IDENTITY (never a
    # current-working-order liveness claim -- see C09-G).  A missing / non-str
    # / blank order_id is malformed current truth.  The request scope is NEVER
    # used as a default.
    order_id = _require_exact_str(
        _require_field(row, "order_id", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="active-V2 fill order_id type")
    if order_id == "":
        raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="active-V2 fill order_id blank")
    side = row.get("side")
    outcome_side = {"yes": "YES", "no": "NO"}.get(side) if type(side) is str else None
    if outcome_side is None:
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 fill side")
    price = _decimal_from_price_string(_require_field(row, "yes_price_dollars", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID))
    quantity = _decimal_from_quantity_string(_require_field(row, "count_fp", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID))
    created = _require_str(
        _require_field(row, "created_time", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
        code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="active-V2 fill created_time")
    validate_canonical_timestamp(created)
    return _ActiveV2ParsedFillV1(
        fill_id=fill_id, order_id=order_id, subaccount=subaccount, exchange_index=exchange_index,
        ticker=ticker, outcome_side=outcome_side, quantity=quantity, yes_price=price,
        created_time_utc=created,
    )


def _active_v2_fill_from_row(
    row: "Mapping[str, object]", *, subaccount: int, exchange_index: int,
) -> "EconomicFillV1":
    """Correction 07 / Correction 09 -- active-V2-specific fill conversion.
    Delegates to the ONE shared ``_active_v2_parsed_fill_from_row`` and returns
    only its existing ``EconomicFillV1`` projection."""
    return _active_v2_parsed_fill_from_row(
        row, subaccount=subaccount, exchange_index=exchange_index,
    ).economic_fill()


def _active_v2_scope_guard(row: "Mapping[str, object]", *, subaccount: int, exchange_index: int) -> None:
    """DSB-PAGE-003 -- retained ONLY for the exact-order GET_ORDER supplement
    confirmation (a single trusted selected-route order id).  The paginated
    portfolio surfaces use the exact Correction-07 operation-specific
    validators above."""
    ei = row.get("exchange_index")
    if type(ei) is not int or type(ei) is bool or ei != exchange_index:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail="get_order row exchange_index != request index")
    sn = row.get(_ACTIVE_V2_SUBACCOUNT_FIELD)
    if sn is not None and (type(sn) is not int or type(sn) is bool or sn != subaccount):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail="get_order row subaccount_number mismatch")
    legacy = row.get("subaccount")
    if legacy is not None and (type(legacy) is not int or type(legacy) is bool or legacy != subaccount):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH, detail="get_order row contradictory legacy subaccount")


def _active_v2_extract_cursor_out(parsed: "Mapping[str, object]") -> str:
    """DSB-PAGE-001 -- ``cursor`` must be an exact string.  ``""`` is
    terminal; a nonempty string is the exact next-page cursor; an
    absent/null/non-string cursor is malformed/incomplete."""
    if "cursor" not in parsed:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE, detail="cursor field absent")
    cursor = parsed.get("cursor")
    if type(cursor) is not str:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE, detail="cursor not a string")
    return cursor


def _active_v2_validate_page_row_economics(
    row: "Mapping[str, object]",
    *,
    operation: ActivePreReleaseReadOperationV2,
    row_ticker: str,
    subaccount: int,
    exchange_index: int,
    selected_exchange_index: int,
    selected_ticker: str,
    retained_ticker: "str | None",
) -> None:
    """Correction 08 C08-A/B/C/D -- DSB-BUDGET-006: validate, BEFORE this
    page's own final same-request deadline check, exactly the economic
    fields a later ARB risk/reconciliation path will actually consume from
    this accepted row.  Reuses the SAME semantic parsers later used by
    selected-route truth / account-wide aggregate extras / position
    corroboration (``_active_v2_working_order_from_row`` /
    ``_active_v2_parsed_fill_from_row`` / ``_position_count_from_row`` /
    ``_foreign_index_position_fill``) -- never a parallel/weaker parser.
    Validation-only: any returned object is discarded here; the row itself
    is never mutated or filtered by this function."""
    if operation is ActivePreReleaseReadOperationV2.GET_ORDERS:
        _active_v2_working_order_from_row(row, subaccount=subaccount, exchange_index=exchange_index)
        return
    if operation is ActivePreReleaseReadOperationV2.GET_FILLS:
        # C09-B: the SHARED parsed-fill identity parser (which requires the
        # inherited exact ``order_id``) runs HERE, inside the C08 page
        # lifecycle -- before cursor/digest/page commitment and before this
        # page's own final same-request deadline check.  No second deadline
        # window is created and fill validation is never moved later.
        _active_v2_parsed_fill_from_row(row, subaccount=subaccount, exchange_index=exchange_index)
        return
    # GET_POSITIONS -- ``position_count_fp`` is always consumed (corroboration
    # / retained-live check / exact-zero classification / aggregate-risk
    # magnitude all read it), so it is validated for every accepted position
    # row.  Every other field is validated ONLY when this row's classification
    # actually consumes it, mirroring
    # ``_parse_dynamic_index_domain_account_wide_extra_economics`` exactly.
    count = _position_count_from_row(row)
    if exchange_index == selected_exchange_index and row_ticker == selected_ticker:
        return  # SELECTED_ROUTE_ACCOUNTED: selected-route corroboration consumes count only.
    if retained_ticker is not None and row_ticker == retained_ticker:
        return  # RETAINED_CURRENT_POSITION_CHECKED: the retained-live check consumes count only.
    if count == 0:
        return  # EXACT_ZERO_ACCOUNTED: count only.
    # AGGREGATE_RISK_ACCOUNTED: a nonzero unrelated position is folded into
    # aggregate risk as one synthetic EconomicFillV1 -- validate the exact
    # inherited synthetic-risk inputs (yes_price_dollars / position_as_of_utc
    # / conversion) before this page becomes accepted.
    _foreign_index_position_fill(row, ticker=row_ticker, subaccount=subaccount, exchange_index=exchange_index)


def _active_v2_paginate_surface(
    adapter: "_ActiveV2OperationAdapter",
    capability: "_TrustedDynamicPreReleaseReadCapabilityV2",
    operation: ActivePreReleaseReadOperationV2,
    *,
    ordinal_box: list,
    subaccount: int,
    exchange_index: int,
    selected_ticker: str,
    retained_ticker: "str | None" = None,
) -> "Tuple[_ActiveV2SurfaceCommitmentV1, Tuple[Mapping[str, object], ...]]":
    """DSB-DOMAIN-003 / DSB-PAGE-001..004 / Correction 07 C07-A + C07-E/F /
    Correction 08 C08-A..E -- one (surface, index) traversal.

    Every page: validate the top-level shape; validate EVERY row's exact
    active-V2 operation-specific scope (``subaccount_number`` +
    ``exchange_index`` for orders/fills; required ``exchange_index`` for
    positions; ``event_positions`` must be exactly empty); validate EVERY
    row's CONSUMED economic schema via
    ``_active_v2_validate_page_row_economics`` (DSB-BUDGET-006: the same
    per-request deadline must cover this, not only scope/cursor/digest);
    PRESERVE EVERY validated row (NO ticker filter, NO retained-ticker
    exception); compute the row hashes, the canonical page content digest,
    and ``row_count`` from EVERY validated row; append EVERY validated row to
    the surface result; only then handle the cursor.  The exact raw response
    SHA stays DISTINCT from the canonical page content digest.  The one
    per-operation ``OperationDeadlineV1`` returned by the adapter covers the
    scope / economic-schema / cursor / row-hash / page-digest /
    page-commitment work, with one final check after the accepted page
    commitment exists (C07-F / C08-E)."""
    runtime = adapter._runtime
    contract = runtime.active_contract
    binding = runtime.domain_binding
    row_key = _ACTIVE_V2_SURFACE_ROW_KEY[operation]
    page_max = _ACTIVE_V2_SURFACE_PAGE_MAX[operation]
    is_positions = operation is ActivePreReleaseReadOperationV2.GET_POSITIONS
    pages: list[_ActiveV2PageCommitmentV1] = []
    kept_rows: list[Mapping[str, object]] = []
    seen_cursors: set[str] = set()
    cursor_in = ""
    exhausted = False
    for page_ordinal in range(1, page_max + 1):
        ordinal_box[0] += 1
        parsed, raw_bytes, deadline = adapter.issue_json(
            capability, operation, ordinal=ordinal_box[0], subaccount=subaccount,
            exchange_index=exchange_index, cursor=(cursor_in or None),
        )
        rows_raw = parsed.get(row_key)
        if type(rows_raw) is not list:
            raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail=operation.value + " " + row_key + " non-array")
        if is_positions:
            events = parsed.get("event_positions")
            if type(events) is not list:
                raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="event_positions non-array")
            if events:
                raise RunnerError(RunnerFailureCode.DYNAMIC_READ_POSITION_EVENT_SCOPE_UNPROVEN, detail="nonempty unscoped event_positions")
        page_rows: list[Mapping[str, object]] = []
        for row in rows_raw:
            if not isinstance(row, Mapping):
                raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail=operation.value + " row not an object")
            if is_positions:
                row_ticker = _active_v2_position_scope(row, subaccount=subaccount, exchange_index=exchange_index)
            else:
                row_ticker = _active_v2_order_fill_scope(row, subaccount=subaccount, exchange_index=exchange_index, operation=operation)
            # C08-A..D: complete CONSUMED economic schema validation, reusing
            # the exact same parsers later object construction uses, BEFORE
            # this page's own final same-request deadline check below.
            _active_v2_validate_page_row_economics(
                row, operation=operation, row_ticker=row_ticker, subaccount=subaccount,
                exchange_index=exchange_index, selected_exchange_index=binding.exchange_index,
                selected_ticker=selected_ticker, retained_ticker=retained_ticker,
            )
            page_rows.append(row)  # C07-A: retain EVERY validated row, no ticker filter
        cursor_out = _active_v2_extract_cursor_out(parsed)
        row_hashes = tuple(
            sha256_hex(canonical_json_bytes(_canonical_account_wide_row(r))) for r in page_rows
        )
        content_digest = sha256_hex(canonical_json_bytes({
            "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_PAGE_CONTENT_V1",
            "operation": operation.value,
            "exchange_index": exchange_index,
            "page_ordinal": page_ordinal,
            "cursor_out": cursor_out,
            "rows": [_canonical_account_wide_row(r) for r in page_rows],
        }))
        commitment = _ActiveV2PageCommitmentV1(
            operation=operation.value,
            exchange_index=exchange_index,
            page_ordinal=page_ordinal,
            request_identity_sha256=_active_v2_request_identity_sha256(
                operation, active_contract=contract, domain_binding=binding,
                exchange_index=exchange_index, page_ordinal=page_ordinal, cursor_in=cursor_in,
            ),
            response_sha256=sha256_hex(raw_bytes),
            canonical_content_digest_sha256=content_digest,
            cursor_in=cursor_in,
            cursor_out=cursor_out,
            row_count=len(page_rows),
            row_content_sha256=row_hashes,
        )
        # C07-F: one final check of the SAME request deadline, after the
        # accepted page commitment (scope + cursor + hashes + digest) exists.
        check_deadline(deadline, runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        pages.append(commitment)
        kept_rows.extend(page_rows)
        if cursor_out == "":
            exhausted = True
            break
        if cursor_out == cursor_in or cursor_out in seen_cursors:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_CURSOR_CYCLE, detail=operation.value + " repeated/cyclic cursor")
        seen_cursors.add(cursor_out)
        cursor_in = cursor_out
    if not exhausted:
        # DSB-BUDGET-002 / DSB-PAGE-001: a nonempty cursor after the final
        # allowed page is incomplete -- NO extra request is attempted.
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE, detail=operation.value + " nonempty cursor at page cap")
    surface = _ActiveV2SurfaceCommitmentV1(
        operation=operation.value, exchange_index=exchange_index,
        pages=tuple(pages), page_count=len(pages), pagination_exhausted=True,
    )
    return surface, tuple(kept_rows)


def _active_v2_selected_route_truth(
    *,
    market: "Mapping[str, object]",
    orderbook: object,
    order_rows: "Tuple[Mapping[str, object], ...]",
    fill_rows: "Tuple[Mapping[str, object], ...]",
    position_rows: "Tuple[Mapping[str, object], ...]",
    bound_order_ids: "Tuple[str, ...]",
    orders_complete: bool,
    subaccount: int,
    exchange_index: int,
    ticker: str,
    requests_consumed: int,
) -> "AuthoritativeReadTruthV1":
    """Assemble the scoped selected-route ``AuthoritativeReadTruthV1`` from the
    selected exchange index's own validated V2 reads, filtered to the selected
    ticker (Correction 07 C07-C: selected-route truth = selected index +
    selected ticker only).  DSB-OPS-005: the selected index participates once
    in the all-index traversal; it is not re-read.  Uses the active-V2
    operation-specific converters (``subaccount_number`` schema); the legacy
    V1 ``_working_order_from_raw`` / ``_fill_from_raw`` schema is untouched."""
    working_orders: list[WorkingOrderV1] = []
    for row in order_rows:
        wo = _active_v2_working_order_from_row(row, subaccount=subaccount, exchange_index=exchange_index)
        if wo is not None:
            if wo.market != ticker:
                raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="selected-route order ticker mismatch")
            working_orders.append(wo)
    # Correction 09 C09-D / DSB-READ-005: ``fill_id`` remains the exactly-once
    # key, but equality/conflict is decided on the FULL parsed identity (which
    # includes ``order_id`` and the exact scope), not merely on the
    # ``EconomicFillV1`` projection.  An exact duplicate contributes exactly
    # one economic fill; any contradictory field fails closed.
    fills_by_id: dict[str, _ActiveV2ParsedFillV1] = {}
    for row in fill_rows:
        parsed = _active_v2_parsed_fill_from_row(row, subaccount=subaccount, exchange_index=exchange_index)
        if parsed.ticker != ticker:
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="selected-route fill ticker mismatch")
        existing = fills_by_id.get(parsed.fill_id)
        if existing is None:
            fills_by_id[parsed.fill_id] = parsed
        elif existing != parsed:
            raise RunnerError(RunnerFailureCode.FILL_DUPLICATE_CONFLICT, detail=parsed.fill_id)
    fills = tuple(sorted(
        (parsed.economic_fill() for parsed in fills_by_id.values()),
        key=lambda item: (item.authoritative_created_time_utc, item.fill_id),
    ))
    position_state = "VENUE_POSITION_ROW_OBSERVED" if position_rows else "NO_VENUE_POSITION_ROW"
    corroboration = _corroborate_position(
        ticker=ticker, position_state=position_state, market_positions_raw=tuple(position_rows),
        working_orders=tuple(working_orders), fills=fills,
    )
    return AuthoritativeReadTruthV1(
        market=market, orderbook=orderbook, working_orders=tuple(working_orders),
        orders_complete=orders_complete, bound_order_ids=tuple(bound_order_ids),
        fills=fills, fills_complete=True, position_state=position_state,
        market_positions_raw=tuple(position_rows), position_corroboration=corroboration,
        requests_consumed=requests_consumed,
    )


_POSITION_CLASS_SELECTED_ROUTE_ACCOUNTED = "SELECTED_ROUTE_ACCOUNTED"
_POSITION_CLASS_RETAINED_CURRENT_POSITION_CHECKED = "RETAINED_CURRENT_POSITION_CHECKED"
_POSITION_CLASS_EXACT_ZERO_ACCOUNTED = "EXACT_ZERO_ACCOUNTED"
_POSITION_CLASS_AGGREGATE_RISK_ACCOUNTED = "AGGREGATE_RISK_ACCOUNTED"
_POSITION_CLASSES = frozenset({
    _POSITION_CLASS_SELECTED_ROUTE_ACCOUNTED, _POSITION_CLASS_RETAINED_CURRENT_POSITION_CHECKED,
    _POSITION_CLASS_EXACT_ZERO_ACCOUNTED, _POSITION_CLASS_AGGREGATE_RISK_ACCOUNTED,
})


def _parse_dynamic_index_domain_account_wide_extra_economics(
    read: "DynamicIndexDomainAccountWideReadV1", *,
    selected_ticker: str,
    selected_exchange_index: int,
    subaccount: int,
    retained_ticker: "str | None" = None,
) -> "tuple[tuple, tuple, bool]":
    """Correction 07 C07-C / C07-D / DSB-RISK-004 -- consume EVERY accepted
    economic row across EVERY enumerated index and EVERY ticker that is NOT
    already represented by the selected-route truth (selected index + selected
    ticker), converting each to the existing ``WorkingOrderV1`` /
    ``EconomicFillV1`` using that ROW's OWN exact ticker as the market.

    Covers:
      * selected-index / other-ticker working orders, fills, positions;
      * foreign-index / selected-ticker rows;
      * foreign-index / other-ticker rows.

    Predecessor duplicate / conflict / fixed-point / fail-closed semantics are
    preserved (duplicate identity is ``(exchange_index, ticker)``, so multiple
    markets on one exchange index are never conflated).  A row already
    represented by the selected route is never double counted.

    Returns ``(extra_working_orders, extra_fills, other_positions_all_accounted)``.
    The boolean is the DERIVED result of EXPLICITLY classifying EVERY accepted
    current market-position row across every enumerated index into exactly one
    of:

      SELECTED_ROUTE_ACCOUNTED               -- the selected-index/selected-
                                                 ticker position, consumed by
                                                 selected-route corroboration;
      RETAINED_CURRENT_POSITION_CHECKED       -- a row for the retained
                                                 bootstrap ticker, verified by
                                                 the caller's retained-live-
                                                 contracts check;
      EXACT_ZERO_ACCOUNTED                    -- an exact zero-count position;
      AGGREGATE_RISK_ACCOUNTED                -- a nonzero position folded
                                                 into aggregate risk as one
                                                 synthetic ``EconomicFillV1``.

    A row that cannot be placed into exactly one of these four classes is
    UNCLASSIFIED and the boolean becomes ``False`` (fail closed at the
    caller's retained-floor reconciliation).  A genuinely malformed row (bad
    ``position_count_fp`` / scope) still fails hard before release."""
    working: list = []
    fills: list = []
    seen_position: dict[tuple, list] = {}
    # C09-E / DSB-READ-005: extra (non-selected-route) fills are exactly-once
    # by ``fill_id``, compared on the full parsed identity.
    seen_extra_fill: dict[str, _ActiveV2ParsedFillV1] = {}
    every_position_classified = True
    for t in read.per_index_traversals:
        for row in tuple(t.order_rows) + tuple(t.fill_rows) + tuple(t.position_rows):
            is_position = "position_count_fp" in row
            is_fill = "fill_id" in row
            is_order = ("order_id" in row and "remaining_count_fp" in row)
            if is_position:
                row_ticker = _active_v2_position_scope(row, subaccount=subaccount, exchange_index=t.exchange_index)
            elif is_fill:
                row_ticker = _active_v2_order_fill_scope(
                    row, subaccount=subaccount, exchange_index=t.exchange_index,
                    operation=ActivePreReleaseReadOperationV2.GET_FILLS)
            elif is_order:
                row_ticker = _active_v2_order_fill_scope(
                    row, subaccount=subaccount, exchange_index=t.exchange_index,
                    operation=ActivePreReleaseReadOperationV2.GET_ORDERS)
            else:
                raise RunnerError(RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS, detail="account-wide economic row shape")
            is_selected_route_row = t.exchange_index == selected_exchange_index and row_ticker == selected_ticker

            if is_position:
                key = (t.exchange_index, row_ticker)
                canonical = _canonical_account_wide_row(row)
                if key in seen_position:
                    if seen_position[key] != canonical:
                        raise RunnerError(
                            RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS,
                            detail="contradictory duplicate account-wide position row")
                    continue
                seen_position[key] = canonical
                if is_selected_route_row:
                    classification = _POSITION_CLASS_SELECTED_ROUTE_ACCOUNTED
                elif retained_ticker is not None and row_ticker == retained_ticker:
                    # Verified separately by the caller's fresh complete
                    # retained-ticker live-contracts check; not re-folded here.
                    classification = _POSITION_CLASS_RETAINED_CURRENT_POSITION_CHECKED
                else:
                    count = _position_count_from_row(row)  # bad Decimal -> RESPONSE_SCHEMA_INVALID (hard fail)
                    if count == 0:
                        classification = _POSITION_CLASS_EXACT_ZERO_ACCOUNTED
                    else:
                        price_raw = row.get("yes_price_dollars")
                        as_of = row.get("position_as_of_utc")
                        if type(price_raw) is str and type(as_of) is str:
                            synthetic = _foreign_index_position_fill(
                                row, ticker=row_ticker, subaccount=subaccount, exchange_index=t.exchange_index)
                            if synthetic is not None:
                                fills.append(synthetic)
                            classification = _POSITION_CLASS_AGGREGATE_RISK_ACCOUNTED
                        else:
                            # A nonzero, non-selected-route, non-retained
                            # position we cannot faithfully represent ->
                            # UNCLASSIFIED (fail closed at ATSE1 time).
                            classification = None
                if classification not in _POSITION_CLASSES:
                    every_position_classified = False
                continue

            # Orders / fills already represented by the selected route are not
            # re-consumed here (no double counting); they still enter the
            # page/ADRS2 commitment upstream regardless.
            if is_selected_route_row:
                continue
            if is_fill:
                # C09-E: one economic fill per exact fill event; an exact
                # duplicate (same fill_id AND identical parsed identity) is
                # NOT double counted into aggregate risk, and a contradictory
                # duplicate fails closed.  The raw row itself still stays in
                # the page/ADRS2 commitment upstream (C09-F).
                parsed_fill = _active_v2_parsed_fill_from_row(
                    row, subaccount=subaccount, exchange_index=t.exchange_index)
                existing_fill = seen_extra_fill.get(parsed_fill.fill_id)
                if existing_fill is None:
                    seen_extra_fill[parsed_fill.fill_id] = parsed_fill
                    fills.append(parsed_fill.economic_fill())
                elif existing_fill != parsed_fill:
                    raise RunnerError(RunnerFailureCode.FILL_DUPLICATE_CONFLICT, detail=parsed_fill.fill_id)
            else:
                parsed = _active_v2_working_order_from_row(row, subaccount=subaccount, exchange_index=t.exchange_index)
                if parsed is not None:
                    working.append(parsed)
    return tuple(working), tuple(fills), every_position_classified


def _validate_active_v2_domain_wide_fill_identity(
    read: "DynamicIndexDomainAccountWideReadV1", *, subaccount: int,
) -> None:
    """Correction 09 C09-C / DSB-OPS-009 + DSB-READ-005 -- the ONE domain-wide
    exactly-once fill-identity proof, run at the converged mint boundary that
    BOTH the live acquirer and the test-only fake seam reach, before any
    release-eligible read set or risk acceptance exists.

    Every accepted fill row across EVERY enumerated exchange index and EVERY
    fill page is parsed with the ONE shared ``_active_v2_parsed_fill_from_row``
    and keyed by ``fill_id``:

      * first occurrence            -> retain the exact parsed identity;
      * identical parsed identity   -> exact duplicate, allowed;
      * ANY differing field         -> ``FILL_DUPLICATE_CONFLICT``, fail closed.

    Because the exact scope (``subaccount`` / ``exchange_index``) and
    ``order_id`` are part of the compared identity, the same ``fill_id``
    observed under a different exchange index, ticker, order, side, quantity,
    price, or canonical time is a CONFLICT -- never a second economic fill.

    This validates ECONOMIC truth only: the raw page rows and their ADRS2
    commitments still retain every observed occurrence (C09-F).  No new
    per-request deadline window is created -- the still-running absolute
    invocation deadline remains controlling over this mint-time work."""
    seen: dict[str, _ActiveV2ParsedFillV1] = {}
    for t in read.per_index_traversals:
        for row in t.fill_rows:
            parsed = _active_v2_parsed_fill_from_row(
                row, subaccount=subaccount, exchange_index=t.exchange_index)
            existing = seen.get(parsed.fill_id)
            if existing is None:
                seen[parsed.fill_id] = parsed
            elif existing != parsed:
                raise RunnerError(RunnerFailureCode.FILL_DUPLICATE_CONFLICT, detail=parsed.fill_id)


def _run_active_v2_acquisition(
    runtime: "ExperimentRunnerRuntimeV2",
    capability: "_TrustedDynamicPreReleaseReadCapabilityV2",
    *,
    opened: "OpenResult | None",
    selected_ticker: str,
) -> "_ActiveV2AcquiredReadV1":
    """DSB-FRESH-001 / DSB-DOMAIN-001..004 / DSB-PAGE-001..004 -- the exact
    production live acquisition state machine.  Issues S0 -> T0 -> selected
    GET_MARKET -> selected GET_MARKET_ORDERBOOK -> per-index (ORDERS<=2,
    FILLS<=4, POSITIONS<=2) for every i in ascending D0 -> zero-to-two exact
    GET_ORDER supplements -> T1 -> S1, each request capability-owned and
    charged once immediately before transport, each inside the exact 10000-ms
    per-operation deadline, zero automatic retry, zero redirect, and the whole
    thing inside the already-running absolute invocation deadline.  Returns
    the ONE converged ``_ActiveV2AcquiredReadV1`` (no weaker shape)."""
    contract = runtime.active_contract
    binding = runtime.domain_binding
    if type(selected_ticker) is not str or _TICKER_PATTERN.fullmatch(selected_ticker) is None:
        raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="active-V2 selected ticker")
    adapter = _ActiveV2OperationAdapter(
        runtime, absolute_invocation_deadline_ns=capability.absolute_invocation_deadline_ns,
    )
    ordinal_box = [0]
    # Correction 08 C08-D: the retained-bootstrap ticker (if any) is known
    # up front and is threaded into EVERY per-index GET_POSITIONS page
    # acceptance so its consumed-economics validation boundary (DSB-BUDGET-
    # 006) can classify a retained-current-ticker row -- without filtering
    # any row -- at the exact same place C07-D later classifies it.
    rbp = runtime.accepted_evidence_contract.retained_bootstrap_position
    retained_ticker = rbp["ticker"] if rbp is not None else None

    def _bookend(operation, *, bookend, exchange_index=None, ticker=None):
        ordinal_box[0] += 1
        parsed, raw_bytes, deadline = adapter.issue_json(
            capability, operation, ordinal=ordinal_box[0], subaccount=binding.subaccount,
            exchange_index=exchange_index, ticker=ticker,
        )
        return parsed, raw_bytes, deadline

    def _final_check(deadline):
        # C07-F: one final check of the SAME per-operation deadline, after the
        # accepted operation/bookend/market/orderbook/supplement commitment
        # exists, immediately before it becomes part of acquired truth.
        check_deadline(deadline, runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)

    def _req_id(operation, *, exchange_index=None, ticker=None, order_id=None):
        return _active_v2_request_identity_sha256(
            operation, active_contract=contract, domain_binding=binding,
            exchange_index=exchange_index, page_ordinal=1, ticker=ticker, order_id=order_id,
        )

    # 1 -- S0 status-before -> D0
    s0_parsed, s0_raw, s0_deadline = _bookend(ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS, bookend="BEFORE")
    d0, s0_content = _active_v2_status_domain_and_content(s0_parsed)
    if binding.exchange_index not in d0:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_SELECTED_INDEX_NOT_IN_DOMAIN, detail="selected exchange_index absent from D0")
    status_before = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS.value, bookend="BEFORE",
        request_identity_sha256=_req_id(ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS),
        response_sha256=sha256_hex(s0_raw), canonical_content_sha256=s0_content,
        exact_sorted_domain=d0,
    )
    _final_check(s0_deadline)

    # 2 -- T0 freshness-before (wall sample taken immediately after parse)
    t0_parsed, t0_raw, t0_deadline = _bookend(ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP, bookend="BEFORE")
    t0_as_of = _active_v2_as_of_time(t0_parsed)
    t0_wall = canonical_timestamp(runtime.wall_clock())
    freshness_before = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP.value, bookend="BEFORE",
        request_identity_sha256=_req_id(ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP),
        response_sha256=sha256_hex(t0_raw),
        canonical_content_sha256=sha256_hex(canonical_json_bytes({
            "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_FRESHNESS_CONTENT_V1", "as_of_time": t0_as_of})),
        as_of_time_utc=t0_as_of, wall_sample_utc=t0_wall,
    )
    _final_check(t0_deadline)

    # 3 -- selected GET_MARKET
    ordinal_box[0] += 1
    m_parsed, m_raw, m_deadline = adapter.issue_json(
        capability, ActivePreReleaseReadOperationV2.GET_MARKET, ordinal=ordinal_box[0],
        subaccount=binding.subaccount, ticker=selected_ticker,
    )
    market = _parse_market(m_parsed, expected_ticker=selected_ticker, expected_exchange_index=binding.exchange_index)
    selected_market = _ActiveV2ContentCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_MARKET.value,
        request_identity_sha256=_req_id(ActivePreReleaseReadOperationV2.GET_MARKET, ticker=selected_ticker),
        response_identity_sha256=sha256_hex(m_raw),
        canonical_consumed_digest_sha256=sha256_hex(canonical_json_bytes({
            "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_MARKET_ECON_V1",
            "market": _canonical_account_wide_row(market),
        })),
    )
    _final_check(m_deadline)

    # 4 -- selected GET_MARKET_ORDERBOOK (inherited accepted fetch_orderbook)
    ordinal_box[0] += 1
    orderbook, ob_deadline = adapter.issue_orderbook(capability, ordinal=ordinal_box[0], ticker=selected_ticker)
    ob_identity = orderbook.with_canonical_identity().canonical_snapshot_sha256
    if not _is_hex64(ob_identity):
        raise RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="orderbook snapshot identity")
    selected_orderbook = _ActiveV2ContentCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK.value,
        request_identity_sha256=_req_id(ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK, ticker=selected_ticker),
        response_identity_sha256=ob_identity,
        canonical_consumed_digest_sha256=sha256_hex(canonical_json_bytes({
            "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_ORDERBOOK_ECON_V1",
            "market_data_snapshot": {k: str(v) for k, v in _market_data_snapshot(market, orderbook).items()},
            "canonical_snapshot_sha256": ob_identity,
        })),
    )
    _final_check(ob_deadline)

    # 5 -- per-index all-member traversal (ascending D0).  Every accepted row
    # (every ticker) is retained by ``_active_v2_paginate_surface`` and enters
    # the page commitments / ADRS2 (C07-A).  Selected-route filtering happens
    # only AFTER the complete accepted rows exist (C07-C).
    per_index: list[_ActiveV2PerIndexCommitmentV1] = []
    sel_order_rows: "Tuple[Mapping[str, object], ...]" = ()
    sel_fill_rows: "Tuple[Mapping[str, object], ...]" = ()
    sel_position_rows: "Tuple[Mapping[str, object], ...]" = ()
    fixture_traversals: list[PerIndexTraversalV1] = []
    for i in d0:
        orders_surface, orders_rows = _active_v2_paginate_surface(
            adapter, capability, ActivePreReleaseReadOperationV2.GET_ORDERS,
            ordinal_box=ordinal_box, subaccount=binding.subaccount, exchange_index=i,
            selected_ticker=selected_ticker, retained_ticker=retained_ticker,
        )
        fills_surface, fills_rows = _active_v2_paginate_surface(
            adapter, capability, ActivePreReleaseReadOperationV2.GET_FILLS,
            ordinal_box=ordinal_box, subaccount=binding.subaccount, exchange_index=i,
            selected_ticker=selected_ticker, retained_ticker=retained_ticker,
        )
        positions_surface, positions_rows = _active_v2_paginate_surface(
            adapter, capability, ActivePreReleaseReadOperationV2.GET_POSITIONS,
            ordinal_box=ordinal_box, subaccount=binding.subaccount, exchange_index=i,
            selected_ticker=selected_ticker, retained_ticker=retained_ticker,
        )
        per_index.append(_ActiveV2PerIndexCommitmentV1(
            exchange_index=i, orders=orders_surface, fills=fills_surface, positions=positions_surface,
            order_rows=orders_rows, fill_rows=fills_rows, position_rows=positions_rows,
        ))

        def _surface_fixture(surface: _ActiveV2SurfaceCommitmentV1) -> PerIndexSurfaceTraversalV1:
            return PerIndexSurfaceTraversalV1(
                request_identity_sha256=surface.pages[0].request_identity_sha256,
                page_response_digests=tuple(p.response_sha256 for p in surface.pages),
                page_economic_digests=tuple(p.canonical_content_digest_sha256 for p in surface.pages),
                final_cursor_absent=True, pagination_complete=True,
            )

        fixture_traversals.append(PerIndexTraversalV1(
            exchange_index=i,
            orders=_surface_fixture(orders_surface),
            fills=_surface_fixture(fills_surface),
            positions=_surface_fixture(positions_surface),
            order_rows=orders_rows, fill_rows=fills_rows, position_rows=positions_rows,
        ))
        if i == binding.exchange_index:
            # C07-C: selected-route truth = selected index + selected ticker
            # ONLY, derived AFTER the complete accepted rows exist.  Every
            # other accepted row (this index's other tickers, every foreign
            # index) stays in the fixture traversal and is folded into
            # account-wide aggregate risk by
            # ``_parse_dynamic_index_domain_account_wide_extra_economics``.
            sel_order_rows = tuple(r for r in orders_rows if r.get("ticker") == selected_ticker)
            sel_fill_rows = tuple(r for r in fills_rows if r.get("ticker") == selected_ticker)
            sel_position_rows = tuple(r for r in positions_rows if r.get("ticker") == selected_ticker)

    # 6 -- zero-to-two exact GET_ORDER supplements from the selected index's
    # own accepted GET_ORDERS traversal (DSB-OPS-004/005).
    selected_order_ids = [str(r.get("order_id", "")) for r in sel_order_rows if str(r.get("order_id", "")) != ""]
    bound_ids = tuple(selected_order_ids[:_ACTIVE_V2_ORDER_REQUEST_MAX])
    orders_complete = len(selected_order_ids) <= _ACTIVE_V2_ORDER_REQUEST_MAX
    supplements: list[_ActiveV2OrderSupplementCommitmentV1] = []
    for oid in bound_ids:
        ordinal_box[0] += 1
        o_parsed, o_raw, o_deadline = adapter.issue_json(
            capability, ActivePreReleaseReadOperationV2.GET_ORDER, ordinal=ordinal_box[0],
            subaccount=binding.subaccount, exchange_index=binding.exchange_index,
            ticker=selected_ticker, order_id=oid,
        )
        o_obj = _require_dict(o_parsed, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="get_order top level")
        o_row = _require_dict(
            _require_field(o_obj, "order", code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID),
            code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="order shape",
        )
        _active_v2_scope_guard(o_row, subaccount=binding.subaccount, exchange_index=binding.exchange_index)
        if o_row.get("order_id") != oid or o_row.get("ticker") != selected_ticker:
            raise RunnerError(RunnerFailureCode.ORDER_IDENTITY_INVALID, detail="get_order confirmation mismatch")
        supplements.append(_ActiveV2OrderSupplementCommitmentV1(
            order_id=oid,
            request_identity_sha256=_req_id(
                ActivePreReleaseReadOperationV2.GET_ORDER, exchange_index=binding.exchange_index,
                ticker=selected_ticker, order_id=oid,
            ),
            response_sha256=sha256_hex(o_raw),
            canonical_content_sha256=sha256_hex(canonical_json_bytes({
                "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_ORDER_SUPPLEMENT_V1",
                "order": _canonical_account_wide_row(o_row),
            })),
        ))
        _final_check(o_deadline)

    # 7 -- T1 freshness-after
    t1_parsed, t1_raw, t1_deadline = _bookend(ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP, bookend="AFTER")
    t1_as_of = _active_v2_as_of_time(t1_parsed)
    t1_wall = canonical_timestamp(runtime.wall_clock())
    if _parse_canonical_utc(t1_as_of) < _parse_canonical_utc(t0_as_of):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_FRESHNESS_REGRESSION, detail="T1 as_of < T0 as_of")
    if _parse_canonical_utc(t1_wall) < _parse_canonical_utc(t0_wall):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_CLOCK_REGRESSION, detail="trusted wall-clock sample regressed T0->T1")
    freshness_after = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP.value, bookend="AFTER",
        request_identity_sha256=_active_v2_request_identity_sha256(
            ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP, active_contract=contract,
            domain_binding=binding, exchange_index=None, page_ordinal=2,
        ),
        response_sha256=sha256_hex(t1_raw),
        canonical_content_sha256=sha256_hex(canonical_json_bytes({
            "schema": "ARB_KALSHI_DEMO_ACTIVE_V2_FRESHNESS_CONTENT_V1", "as_of_time": t1_as_of})),
        as_of_time_utc=t1_as_of, wall_sample_utc=t1_wall,
    )
    _final_check(t1_deadline)

    # 8 -- S1 status-after -> D1 == D0
    s1_parsed, s1_raw, s1_deadline = _bookend(ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS, bookend="AFTER")
    d1, s1_content = _active_v2_status_domain_and_content(s1_parsed)
    if d1 != d0:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_CHANGED, detail="D1 != D0")
    status_after = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS.value, bookend="AFTER",
        request_identity_sha256=_active_v2_request_identity_sha256(
            ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS, active_contract=contract,
            domain_binding=binding, exchange_index=None, page_ordinal=2,
        ),
        response_sha256=sha256_hex(s1_raw), canonical_content_sha256=s1_content, exact_sorted_domain=d1,
    )
    _final_check(s1_deadline)

    # 9 -- build the selected-route truth + the completeness fixture, then the
    # converged acquired-read (final composite validation happens in the mint,
    # inside the still-running absolute invocation deadline).
    selected_route_truth = _active_v2_selected_route_truth(
        market=market, orderbook=orderbook, order_rows=sel_order_rows, fill_rows=sel_fill_rows,
        position_rows=sel_position_rows, bound_order_ids=bound_ids, orders_complete=orders_complete,
        subaccount=binding.subaccount, exchange_index=binding.exchange_index, ticker=selected_ticker,
        requests_consumed=capability.requests_consumed,
    )
    cutoff = _active_reconciliation_cutoff_sha256(selected_route_truth)
    # The completeness fixture's ``settlement_reconciliation`` is derived by
    # THIS trusted boundary from the module-private
    # ``n1_accepted_terminal_settlement_evidence()`` -- never caller content.
    # It only satisfies the existing fixture-path completeness check; the
    # ACTUAL retained-position release authority is
    # ``reconcile_retained_bootstrap_floor_v1`` in ``_mint_release_eligible_
    # read_set`` (BLOCK-05-03).  ``rbp`` was already resolved at the top of
    # this function (Correction 08 C08-D) and is reused here unchanged.
    settlement_reconciliation = None
    if rbp is not None:
        _atse1 = n1_accepted_terminal_settlement_evidence()
        settlement_reconciliation = RetainedPositionSettlementReconciliationV1(
            settlement_evidence_identity_sha256=_atse1.evidence_sha256,
            ticker=rbp["ticker"],
            exchange_index=rbp["exchange_index"],
            conflict_domain_ref=rbp["conflict_domain_ref"],
            market_result=_atse1.market_result,
            settled_time_utc=_atse1.settled_time,
            yes_count_fp=_atse1.yes_count_fp,
            settlement_response_identity_sha256=_atse1.settlement_response_sha256,
        )
    fixture_no_ident = DynamicIndexDomainAccountWideReadV1(
        accepted_source_classification=_ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
        index_domain_enumeration_evidence_identity_sha256=_P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,
        account_scope_ref=binding.account_scope_ref,
        subaccount=binding.subaccount,
        selected_exchange_index=binding.exchange_index,
        status_before=ExchangeIndexStatusObservationV1(response_identity_sha256=sha256_hex(s0_raw), exchange_index_domain=d0),
        status_after=ExchangeIndexStatusObservationV1(response_identity_sha256=sha256_hex(s1_raw), exchange_index_domain=d1),
        freshness_before=UserDataFreshnessWatermarkV1(response_identity_sha256=sha256_hex(t0_raw), as_of_time_utc=t0_as_of),
        freshness_after=UserDataFreshnessWatermarkV1(response_identity_sha256=sha256_hex(t1_raw), as_of_time_utc=t1_as_of),
        per_index_traversals=tuple(fixture_traversals),
        selected_route_reconciliation_cutoff_sha256=cutoff,
        read_set_identity_sha256="0" * 64,
        settlement_reconciliation=settlement_reconciliation,
    )
    fixture_identity = compute_dynamic_index_domain_read_set_identity(
        fixture_no_ident,
        active_domain_binding_id=contract.domain_binding_id,
        active_domain_binding_sha256=contract.domain_binding_sha256,
        active_contract_sha256=contract.contract_sha256,
        risk_config_sha256=runtime.risk_config.sha256,
    )
    fixture = _dataclass_replace(fixture_no_ident, read_set_identity_sha256=fixture_identity)

    return _ActiveV2AcquiredReadV1(
        status_before=status_before, status_after=status_after,
        freshness_before=freshness_before, freshness_after=freshness_after,
        selected_market=selected_market, selected_orderbook=selected_orderbook,
        per_index=tuple(per_index), exact_order_supplements=tuple(supplements),
        d0=d0, d1=d1, fixture=fixture, selected_route_truth=selected_route_truth,
        t0_wall_sample_utc=t0_wall, t1_wall_sample_utc=t1_wall,
    )


def _active_v2_surface_canonical(surface: "_ActiveV2SurfaceCommitmentV1") -> dict:
    """DSB-READSET-001 -- per-surface commitment: one entry per ACTUAL page,
    each with its request identity, its RAW response SHA, its SEPARATELY
    computed canonical economic/content digest, the exact cursor-in/out, the
    row count, and the validated canonical row-content hashes; plus the page
    count and ``pagination_exhausted``."""
    return {
        "operation": surface.operation,
        "exchange_index": surface.exchange_index,
        "page_count": surface.page_count,
        "pagination_exhausted": surface.pagination_exhausted,
        "pages": [
            {
                "page_ordinal": p.page_ordinal,
                "request_identity_sha256": p.request_identity_sha256,
                "response_sha256": p.response_sha256,
                "canonical_economic_content_digest_sha256": p.canonical_content_digest_sha256,
                "cursor_in": p.cursor_in,
                "cursor_out": p.cursor_out,
                "row_count": p.row_count,
                "row_content_sha256": list(p.row_content_sha256),
            }
            for p in surface.pages
        ],
    }


def _compute_release_eligible_read_set_sha256(
    acquired: "_ActiveV2AcquiredReadV1",
    *,
    active_contract: "ActiveExecutionDomainContractV1",
    domain_binding: "ExecutionDomainBindingV1",
    risk_config_sha256: str,
    risk_state_epoch: int,
    reconciliation_cutoff_identity_sha256: str,
    trusted_local_release_projection_identity_sha256: str,
    acquisition_started_at_utc: str,
    acquisition_completed_at_utc: str,
    absolute_invocation_deadline_identity: str,
    pre_release_requests_consumed: int,
    retained_position_classification: str,
    accepted_terminal_settlement_id: str,
) -> Tuple[str, Mapping[str, object]]:
    """DSB-READSET-001/003/005 -- the exact ``ADRS2_`` composite identity.

    The canonical object commits every DSB-READSET-001 Section-13 field: the
    active contract/binding, the accepted source identity, the issuer lineage
    class, the acquisition window, the absolute invocation-deadline identity,
    the frozen budget max + consumed count, the ``/exchange/status``
    before/after request/RAW-response/canonical-status-content/domain
    identities (SEPARATE from the ``user_data_timestamp`` before/after request/
    RAW-response/as_of identities), the selected market/orderbook request/
    response/economic-content identities, EVERY per-index per-surface
    per-ACTUAL-page request/RAW-response/canonical-economic-digest/cursor/
    row-hash/page-count/pagination-exhausted commitment, the zero-to-two exact
    trusted GET_ORDER supplements, the current risk-config identity, risk-state
    epoch, reconciliation cutoff, trusted local release projection identity,
    and the retained-position settlement classification + accepted ATSE1
    identity where applicable.  Any mutation of any of these -- including a
    single page ordinal, request identity, raw response hash (which is a
    distinct value from the canonical content digest), row hash, cursor, or
    an exact-order supplement -- changes the composite hash.  A correct
    self-hash still does NOT establish source authority: the exact private
    type + the same live issuer lineage remain independently mandatory
    (DSB-READSET-004)."""
    fixture = acquired.fixture
    inner = compute_dynamic_index_domain_read_set_identity(
        fixture,
        active_domain_binding_id=active_contract.domain_binding_id,
        active_domain_binding_sha256=active_contract.domain_binding_sha256,
        active_contract_sha256=active_contract.contract_sha256,
        risk_config_sha256=risk_config_sha256,
    )

    def _bookend(b: "_ActiveV2BookendCommitmentV1", *, status: bool) -> dict:
        out = {
            "request_identity_sha256": b.request_identity_sha256,
            "response_sha256": b.response_sha256,
        }
        if status:
            out["canonical_status_content_sha256"] = b.canonical_content_sha256
            out["exact_sorted_domain"] = list(b.exact_sorted_domain)
        else:
            out["canonical_freshness_content_sha256"] = b.canonical_content_sha256
            out["as_of_time"] = b.as_of_time_utc
            out["trusted_wall_clock_sample_utc"] = b.wall_sample_utc
        return out

    def _content(c: "_ActiveV2ContentCommitmentV1") -> dict:
        return {
            "request_identity_sha256": c.request_identity_sha256,
            "response_identity_sha256": c.response_identity_sha256,
            "canonical_economic_content_digest_sha256": c.canonical_consumed_digest_sha256,
        }

    canonical: Mapping[str, object] = MappingProxyType({
        "schema": _ADRS2_READ_SET_SCHEMA,
        "schema_revision": 2,
        "active_contract_id": active_contract.contract_id,
        "active_contract_sha256": active_contract.contract_sha256,
        "domain_binding_id": active_contract.domain_binding_id,
        "domain_binding_sha256": active_contract.domain_binding_sha256,
        "conflict_domain_ref": active_contract.conflict_domain_ref,
        "subaccount": domain_binding.subaccount,
        "selected_exchange_index": domain_binding.exchange_index,
        "accepted_dynamic_source_identity": dict(_ACTIVE_DYNAMIC_SOURCE_IDENTITY),
        "issuer_lineage_class": "LIVE_TRUSTED_DYNAMIC_ACQUIRER_V2",
        "acquisition_started_at_utc": acquisition_started_at_utc,
        "acquisition_completed_at_utc": acquisition_completed_at_utc,
        "absolute_invocation_deadline_identity": absolute_invocation_deadline_identity,
        "pre_release_read_request_max_v2": PRE_RELEASE_READ_REQUEST_MAX_V2,
        "pre_release_requests_consumed": pre_release_requests_consumed,
        "derived_domain_d0": list(acquired.d0),
        "derived_domain_d1": list(acquired.d1),
        "status_before": _bookend(acquired.status_before, status=True),
        "status_after": _bookend(acquired.status_after, status=True),
        "freshness_before": _bookend(acquired.freshness_before, status=False),
        "freshness_after": _bookend(acquired.freshness_after, status=False),
        "selected_market": _content(acquired.selected_market),
        "selected_orderbook": _content(acquired.selected_orderbook),
        "per_index_traversals": [
            {
                "exchange_index": pc.exchange_index,
                "orders": _active_v2_surface_canonical(pc.orders),
                "fills": _active_v2_surface_canonical(pc.fills),
                "positions": _active_v2_surface_canonical(pc.positions),
                "order_rows": [_canonical_account_wide_row(r) for r in pc.order_rows],
                "fill_rows": [_canonical_account_wide_row(r) for r in pc.fill_rows],
                "position_rows": [_canonical_account_wide_row(r) for r in pc.position_rows],
            }
            for pc in acquired.per_index
        ],
        "exact_order_supplements": [
            {
                "order_id": s.order_id,
                "request_identity_sha256": s.request_identity_sha256,
                "response_sha256": s.response_sha256,
                "canonical_content_sha256": s.canonical_content_sha256,
            }
            for s in acquired.exact_order_supplements
        ],
        "dynamic_index_domain_read_inner_identity_sha256": inner,
        "selected_route_reconciliation_cutoff_sha256": fixture.selected_route_reconciliation_cutoff_sha256,
        "retained_position_classification": retained_position_classification,
        "accepted_terminal_settlement_id": accepted_terminal_settlement_id,
        "current_risk_config_identity": risk_config_sha256,
        "current_risk_state_epoch": risk_state_epoch,
        "reconciliation_cutoff_identity": reconciliation_cutoff_identity_sha256,
        "trusted_local_release_projection_identity": trusted_local_release_projection_identity_sha256,
    })
    return sha256_hex(canonical_json_bytes(dict(canonical))), canonical


@dataclass(frozen=True, init=False)
class _ReleaseEligibleDynamicIndexDomainReadSetV2:
    """DSB-READSET-001 -- the ONLY type that may represent current Path-A
    release truth in the production active-V2 path.  Process-local,
    non-serializable, non-copyable, non-deepcopyable, single-use, bound to
    exactly one active contract/domain and one Stage-3 invocation, invalid
    after restart.  Not constructible through a public constructor.  Recomputing
    ``read_set_id`` correctly does NOT prove source authority (DSB-READSET-004):
    Stage 3F additionally requires the exact private type + the live issuer
    lineage that produced it."""

    schema_revision: int
    read_set_sha256: str
    read_set_id: str
    read_set_canonical: Mapping[str, object]
    selected_route_truth: "AuthoritativeReadTruthV1"
    extra_working_orders: Tuple[object, ...]
    extra_fills: Tuple[object, ...]
    controlled_live_position_contracts: Decimal
    retained_position_classification: str
    accepted_terminal_settlement_id: str
    pre_release_requests_consumed: int
    absolute_invocation_deadline_ns: int

    def __init__(self, key: object, **values: object) -> None:
        if key is not _RELEASE_ELIGIBLE_READ_SET_KEY:
            raise RunnerError(
                RunnerFailureCode.CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED,
                detail="no public constructor for _ReleaseEligibleDynamicIndexDomainReadSetV2",
            )
        object.__setattr__(self, "_issuer_sentinel", values.pop("_issuer_sentinel"))
        object.__setattr__(self, "_nonce", values.pop("_nonce"))
        object.__setattr__(self, "_capability_obj_id", values.pop("_capability_obj_id"))
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def verify_self_hash(self) -> bool:
        return (
            self.read_set_id == "ADRS2_" + self.read_set_sha256
            and self.read_set_sha256 == sha256_hex(canonical_json_bytes(dict(self.read_set_canonical)))
        )

    def __copy__(self):
        raise TypeError("_ReleaseEligibleDynamicIndexDomainReadSetV2 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("_ReleaseEligibleDynamicIndexDomainReadSetV2 cannot be serialized")


class _TrustedDynamicPreReleaseReadCapabilityV2:
    """DSB-DYN-002/003 -- the one closed process-local trusted dynamic
    pre-release capability.  Single-use for one Stage-3 invocation; after a
    successful result or any terminal failure it is consumed.  Owns the
    independent 72-request budget and receives the already-running absolute
    invocation deadline (Stage 3D does NOT create a new 300-second window)."""

    __slots__ = (
        "_runtime", "_issuer_sentinel", "_nonce", "_absolute_invocation_deadline_ns",
        "_consumed", "_requests_consumed", "_lock",
    )

    def __init__(self, key: object, *, runtime: "ExperimentRunnerRuntimeV2", absolute_invocation_deadline_ns: int) -> None:
        if key is not _TRUSTED_DYNAMIC_CAPABILITY_KEY:
            raise RunnerError(
                RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID,
                detail="no public constructor for _TrustedDynamicPreReleaseReadCapabilityV2",
            )
        if type(runtime) is not ExperimentRunnerRuntimeV2:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="runtime type")
        if type(absolute_invocation_deadline_ns) is not int or absolute_invocation_deadline_ns < 0:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="deadline")
        self._runtime = runtime
        self._issuer_sentinel = _ACTIVE_TRUSTED_ISSUER_SENTINEL
        self._nonce = runtime.uuid_factory().hex
        self._absolute_invocation_deadline_ns = absolute_invocation_deadline_ns
        self._consumed = False
        self._requests_consumed = 0
        self._lock = threading.Lock()

    @property
    def runtime(self) -> "ExperimentRunnerRuntimeV2":
        return self._runtime

    @property
    def issuer_sentinel(self) -> object:
        return self._issuer_sentinel

    @property
    def nonce(self) -> str:
        return self._nonce

    @property
    def absolute_invocation_deadline_ns(self) -> int:
        return self._absolute_invocation_deadline_ns

    @property
    def requests_consumed(self) -> int:
        return self._requests_consumed

    @property
    def is_consumed(self) -> bool:
        return self._consumed

    def charge(self, operation: ActivePreReleaseReadOperationV2, *, count: int = 1) -> None:
        """DSB-BUDGET-005/006 -- charge ``count`` units at the pre-transport
        boundary.  A request that reaches this charged boundary stays consumed
        regardless of any later outcome; there is no refund and no retry.  The
        deadline is checked first (DSB-BUDGET-006); a request that would exceed
        72 fails ``DYNAMIC_READ_BUDGET_EXHAUSTED`` before transport."""
        with self._lock:
            if self._consumed:
                raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="capability already consumed")
            if operation not in _ACTIVE_V2_OP_BINDING:
                raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="operation not on the closed V2 surface")
            if self._runtime.monotonic_clock_ns() >= self._absolute_invocation_deadline_ns:
                raise RunnerError(RunnerFailureCode.DYNAMIC_READ_DEADLINE_EXHAUSTED, detail="absolute invocation deadline reached before request " + str(self._requests_consumed + 1))
            if self._requests_consumed + count > PRE_RELEASE_READ_REQUEST_MAX_V2:
                raise RunnerError(RunnerFailureCode.DYNAMIC_READ_BUDGET_EXHAUSTED, detail="request " + str(self._requests_consumed + count) + " exceeds pre_release_read_request_max_v2=72")
            self._requests_consumed += count

    def mark_consumed(self) -> None:
        with self._lock:
            self._consumed = True

    def __copy__(self):
        raise TypeError("_TrustedDynamicPreReleaseReadCapabilityV2 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("_TrustedDynamicPreReleaseReadCapabilityV2 cannot be serialized")


class _TrustedDynamicReadAcquirerV2:
    """DSB-DYN-002/004 -- the exact acquisition interface.  The production path
    always binds ``_LiveTrustedDynamicReadAcquirerV2``; the offline fake seam
    binds ``_FakeTrustedDynamicReadAcquirerV2`` only through a module-private
    test factory."""

    def acquire(self, capability: "_TrustedDynamicPreReleaseReadCapabilityV2") -> "_ReleaseEligibleDynamicIndexDomainReadSetV2":  # pragma: no cover - interface
        raise NotImplementedError


def _mint_release_eligible_read_set(
    capability: "_TrustedDynamicPreReleaseReadCapabilityV2",
    *,
    acquired: "_ActiveV2AcquiredReadV1",
    opened: "OpenResult | None",
) -> "_ReleaseEligibleDynamicIndexDomainReadSetV2":
    """The ONE ADRS2 minting implementation (CL-1).  Consumes the ONE
    converged ``_ActiveV2AcquiredReadV1`` (from either the live acquirer or
    the fake seam), validates the enumerated read set against the
    domain-scoped accepted-evidence contract, wires the exact retained
    bootstrap-floor reconciliation through
    ``reconcile_retained_bootstrap_floor_v1`` +
    ``n1_accepted_terminal_settlement_evidence()`` (BLOCK-05-03 -- the caller
    settlement fields / P02 SHA are NOT release authority), recomputes and
    binds the full per-page DSB-READSET-001 composite ADRS2 identity inside
    the still-running absolute invocation deadline, folds same-subaccount
    foreign-index economics into the selected-route truth, and mints the
    private release-eligible type with this capability's live issuer lineage.
    A correct self-hash does NOT by itself establish source authority."""
    if type(acquired) is not _ActiveV2AcquiredReadV1:
        raise RunnerError(RunnerFailureCode.CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED, detail="acquisition result is not the converged private type")
    runtime = capability.runtime
    contract = runtime.active_contract
    binding = runtime.domain_binding
    risk_config = runtime.risk_config
    fixture = acquired.fixture
    selected_route_truth = acquired.selected_route_truth
    if type(risk_config) is not RiskLimitConfigV1:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="active runtime risk_config required")
    if type(selected_route_truth) is not AuthoritativeReadTruthV1:
        raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="selected-route truth type")
    require_complete_active_pagination(selected_route_truth.orders_complete, detail="orders")
    require_complete_active_pagination(selected_route_truth.fills_complete, detail="fills")
    # C09-C: the domain-wide exactly-once fill-identity proof runs at this ONE
    # converged live/fake boundary, before any release-eligible mint or risk
    # acceptance consumes the accepted fill rows.
    _validate_active_v2_domain_wide_fill_identity(fixture, subaccount=binding.subaccount)

    now_monotonic_ns = runtime.monotonic_clock_ns()
    started_utc = canonical_timestamp(runtime.wall_clock())
    current_cutoff = _active_reconciliation_cutoff_sha256(selected_route_truth)

    retained_classification = require_dynamic_index_domain_completeness(
        fixture,
        domain_binding=binding,
        active_contract=contract,
        risk_config=risk_config,
        accepted_evidence_contract=runtime.accepted_evidence_contract,
        current_selected_route_cutoff_sha256=current_cutoff,
        now_monotonic_ns=now_monotonic_ns,
        now_utc=started_utc,
        t0_wall_sample_utc=acquired.t0_wall_sample_utc,
        t1_wall_sample_utc=acquired.t1_wall_sample_utc,
    )

    selected_ticker_value = (
        selected_route_truth.market.get("ticker") if isinstance(selected_route_truth.market, Mapping) else ""
    )
    rbp = runtime.accepted_evidence_contract.retained_bootstrap_position
    extra_working, extra_fills, every_position_classified = _parse_dynamic_index_domain_account_wide_extra_economics(
        fixture, selected_ticker=selected_ticker_value, selected_exchange_index=binding.exchange_index,
        subaccount=binding.subaccount, retained_ticker=(rbp["ticker"] if rbp is not None else None),
    )
    folded_truth = selected_route_truth
    if extra_working or extra_fills:
        folded_truth = _dataclass_replace(
            selected_route_truth,
            working_orders=selected_route_truth.working_orders + extra_working,
            fills=selected_route_truth.fills + extra_fills,
        )

    # BLOCK-05-03 -- the ACTUAL retained-position release authority.
    controlled_live = Decimal("0")
    accepted_atse1_id = ""
    if rbp is not None:
        controlled_live = _dynamic_read_controlled_live_position_contracts(
            fixture, ticker=rbp["ticker"], subaccount=binding.subaccount,
        )
        # ``fresh_all_index_positions_complete`` is True ONLY after EVERY
        # enumerated index's GET_POSITIONS traversal exhausts and D1 == D0.
        fresh_all_index_positions_complete = (
            bool(acquired.per_index)
            and acquired.d0 == acquired.d1
            and tuple(pc.exchange_index for pc in acquired.per_index) == acquired.d0
            and all(pc.positions.pagination_exhausted is True for pc in acquired.per_index)
        )
        # Correction 07 C07-D -- DERIVED, never a literal ``True``: EVERY
        # accepted current position row must have been explicitly classified
        # (selected-route accounted / retained-current-position checked /
        # exact-zero accounted / aggregate-risk accounted -- an unclassified
        # row fails closed), the domain must be stable and every index's
        # positions traversal exhausted, and -- when the selected route itself
        # carries a live position -- selected-route corroboration must
        # actually agree with the independently derived economic state.
        selected_route_position_ok = (
            selected_route_truth.position_state == "NO_VENUE_POSITION_ROW"
            or selected_route_truth.position_corroboration == "CORROBORATED"
        )
        other_positions_all_accounted = (
            every_position_classified
            and fresh_all_index_positions_complete
            and selected_route_position_ok
        )
        accepted_settlement = n1_accepted_terminal_settlement_evidence()
        try:
            retained_classification = reconcile_retained_bootstrap_floor_v1(
                accepted_settlement=accepted_settlement,
                retained_position_ticker=rbp["ticker"],
                retained_position_floor_contracts=Decimal(str(rbp["floor_contracts_fp"])),
                retained_route_exchange_index=rbp["exchange_index"],
                fresh_all_index_positions_complete=fresh_all_index_positions_complete,
                current_retained_ticker_live_contracts=controlled_live,
                ambiguous_event_positions_present=False,
                other_positions_all_accounted=other_positions_all_accounted,
            )
        except LedgerError as exc:
            raise RunnerError(
                RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED,
                detail="retained bootstrap floor not reconciled: " + exc.code.value,
            ) from exc
        accepted_atse1_id = ACCEPTED_TERMINAL_SETTLEMENT_ID

    completed_utc = canonical_timestamp(runtime.wall_clock())
    if runtime.monotonic_clock_ns() >= capability.absolute_invocation_deadline_ns:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_DEADLINE_EXHAUSTED, detail="absolute invocation deadline expired during final read-set construction")
    deadline_identity = sha256_hex(canonical_json_bytes({
        "absolute_invocation_deadline_ns": capability.absolute_invocation_deadline_ns,
        "active_contract_sha256": contract.contract_sha256,
    }))
    read_set_sha256, canonical = _compute_release_eligible_read_set_sha256(
        acquired,
        active_contract=contract,
        domain_binding=binding,
        risk_config_sha256=risk_config.sha256,
        risk_state_epoch=getattr(getattr(opened, "projection", None), "risk_state_epoch", 0) or 0,
        reconciliation_cutoff_identity_sha256=current_cutoff,
        trusted_local_release_projection_identity_sha256=_trusted_local_release_projection_identity(opened),
        acquisition_started_at_utc=started_utc,
        acquisition_completed_at_utc=completed_utc,
        absolute_invocation_deadline_identity=deadline_identity,
        pre_release_requests_consumed=capability.requests_consumed,
        retained_position_classification=retained_classification,
        accepted_terminal_settlement_id=accepted_atse1_id,
    )
    read_set = _ReleaseEligibleDynamicIndexDomainReadSetV2(
        _RELEASE_ELIGIBLE_READ_SET_KEY,
        _issuer_sentinel=capability.issuer_sentinel,
        _nonce=capability.nonce,
        _capability_obj_id=id(capability),
        schema_revision=2,
        read_set_sha256=read_set_sha256,
        read_set_id="ADRS2_" + read_set_sha256,
        read_set_canonical=canonical,
        selected_route_truth=folded_truth,
        extra_working_orders=tuple(extra_working),
        extra_fills=tuple(extra_fills),
        controlled_live_position_contracts=controlled_live,
        retained_position_classification=retained_classification,
        accepted_terminal_settlement_id=accepted_atse1_id,
        pre_release_requests_consumed=capability.requests_consumed,
        absolute_invocation_deadline_ns=capability.absolute_invocation_deadline_ns,
    )
    capability.mark_consumed()
    return read_set


class _LiveTrustedDynamicReadAcquirerV2(_TrustedDynamicReadAcquirerV2):
    """DSB-DYN-002/005/006 -- the production acquirer.  It owns every current
    venue GET, response byte acquisition, parse, scope validation, pagination,
    canonical page/row digests, status-domain derivation, freshness validation,
    and private result construction, all charged to the capability's
    independent 72-request budget.  No out-of-band read may be admitted as
    current Stage-3 truth."""

    __slots__ = ("_runtime", "_opened", "_selected_ticker")

    def __init__(
        self, runtime: "ExperimentRunnerRuntimeV2", *,
        selected_ticker: str, opened: "OpenResult | None" = None,
    ) -> None:
        if type(runtime) is not ExperimentRunnerRuntimeV2:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="runtime type")
        if type(selected_ticker) is not str or _TICKER_PATTERN.fullmatch(selected_ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="live acquirer selected ticker")
        self._runtime = runtime
        self._opened = opened
        self._selected_ticker = selected_ticker

    def acquire(self, capability: "_TrustedDynamicPreReleaseReadCapabilityV2") -> "_ReleaseEligibleDynamicIndexDomainReadSetV2":
        if type(capability) is not _TrustedDynamicPreReleaseReadCapabilityV2 or capability.runtime is not self._runtime:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="capability/runtime mismatch")
        if capability.is_consumed:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="capability already consumed")
        acquired = _run_active_v2_acquisition(
            self._runtime, capability, opened=self._opened, selected_ticker=self._selected_ticker,
        )
        return _mint_release_eligible_read_set(capability, acquired=acquired, opened=self._opened)


def _normalize_legacy_fixture_rows_for_active_v2(
    fixture: "DynamicIndexDomainAccountWideReadV1", *,
    active_contract: "ActiveExecutionDomainContractV1",
    risk_config_sha256: str,
) -> "DynamicIndexDomainAccountWideReadV1":
    """Correction 07 clarification -- module-private TEST-ONLY fixture
    normalizer, reachable ONLY from ``_synthesize_active_v2_acquired`` (the
    fake seam's synthesis path).  It is NEVER reachable from the production
    ``_LiveTrustedDynamicReadAcquirerV2``, and it does NOT relax the live
    active-V2 orders/fills schema -- live rows still require exact
    ``subaccount_number``.

    It converts a trusted legacy synthetic fixture's ``subaccount``-keyed
    economic rows into the same canonical active-V2 ``subaccount_number``
    shape the live acquirer's rows carry, so the fake seam mints through the
    exact same converged representation / economics helpers as the live
    acquirer -- never a weaker or alternate one.  A row that already carries
    ``subaccount_number`` is left exactly as-is; a row that states BOTH
    fields with disagreeing values is a contradiction and fails closed."""

    changed = False

    def _normalize_row(row: object) -> object:
        nonlocal changed
        if not isinstance(row, Mapping):
            return row
        legacy = row.get("subaccount")
        v2 = row.get(_ACTIVE_V2_SUBACCOUNT_FIELD)
        if v2 is not None and legacy is not None and v2 != legacy:
            raise RunnerError(
                RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH,
                detail="fixture row subaccount_number/subaccount contradiction")
        if v2 is not None or legacy is None:
            return row
        out = dict(row)
        out[_ACTIVE_V2_SUBACCOUNT_FIELD] = legacy
        changed = True
        return out

    def _normalize_traversal(t: "PerIndexTraversalV1") -> "PerIndexTraversalV1":
        return PerIndexTraversalV1(
            exchange_index=t.exchange_index, orders=t.orders, fills=t.fills, positions=t.positions,
            order_rows=tuple(_normalize_row(r) for r in t.order_rows),
            fill_rows=tuple(_normalize_row(r) for r in t.fill_rows),
            position_rows=tuple(_normalize_row(r) for r in t.position_rows),
        )

    normalized_traversals = tuple(_normalize_traversal(t) for t in fixture.per_index_traversals)
    if not changed:
        # Nothing needed normalizing (already V2-shaped, or no rows at all):
        # return the ORIGINAL fixture object unchanged, including its
        # existing ``read_set_identity_sha256`` -- a caller-supplied,
        # deliberately-inconsistent identity (e.g. an injection/mutation
        # test) must NOT be silently repaired by this test-only helper.
        return fixture
    normalized = _dataclass_replace(fixture, per_index_traversals=normalized_traversals)
    identity = compute_dynamic_index_domain_read_set_identity(
        normalized,
        active_domain_binding_id=active_contract.domain_binding_id,
        active_domain_binding_sha256=active_contract.domain_binding_sha256,
        active_contract_sha256=active_contract.contract_sha256,
        risk_config_sha256=risk_config_sha256,
    )
    return _dataclass_replace(normalized, read_set_identity_sha256=identity)


def _synthesize_active_v2_acquired(
    fixture: "DynamicIndexDomainAccountWideReadV1",
    selected_route_truth: "AuthoritativeReadTruthV1",
    *,
    runtime: "ExperimentRunnerRuntimeV2",
) -> "_ActiveV2AcquiredReadV1":
    """CL-1 -- convert an existing deterministic offline
    ``DynamicIndexDomainAccountWideReadV1`` fixture into the ONE converged
    ``_ActiveV2AcquiredReadV1`` shape for injection / lineage / hash tests.
    The fake seam does NOT execute the transport state machine; it may
    synthesize the per-page/bookend commitments from fixture material, but it
    MUST NOT retain a weaker or alternate read-set / ADRS2 shape -- the same
    ``_mint_release_eligible_read_set`` consumes the result and production
    authority still additionally requires live-acquirer issuer lineage.  The
    fixture's legacy ``subaccount``-keyed rows are normalized to the exact
    active-V2 ``subaccount_number`` shape (test-only; never reachable from the
    live acquirer) before being carried into the acquired read."""
    fixture = _normalize_legacy_fixture_rows_for_active_v2(
        fixture, active_contract=runtime.active_contract, risk_config_sha256=runtime.risk_config.sha256,
    )

    def _h(*parts: object) -> str:
        return sha256_hex(canonical_json_bytes(list(parts)))

    def _surface(op: ActivePreReleaseReadOperationV2, idx: int, src: "PerIndexSurfaceTraversalV1", rows: "Tuple[Mapping[str, object], ...]") -> _ActiveV2SurfaceCommitmentV1:
        n = len(src.page_response_digests)
        pages: list[_ActiveV2PageCommitmentV1] = []
        for k in range(1, n + 1):
            cursor_in = "" if k == 1 else "SYNTH-CUR-" + op.value + "-" + str(idx) + "-" + str(k - 1)
            cursor_out = "" if k == n else "SYNTH-CUR-" + op.value + "-" + str(idx) + "-" + str(k)
            page_rows = tuple(rows) if k == 1 else ()
            pages.append(_ActiveV2PageCommitmentV1(
                operation=op.value, exchange_index=idx, page_ordinal=k,
                request_identity_sha256=_h("synthetic_request", src.request_identity_sha256, op.value, idx, k, cursor_in),
                response_sha256=src.page_response_digests[k - 1],
                canonical_content_digest_sha256=src.page_economic_digests[k - 1],
                cursor_in=cursor_in, cursor_out=cursor_out,
                row_count=len(page_rows),
                row_content_sha256=tuple(sha256_hex(canonical_json_bytes(_canonical_account_wide_row(r))) for r in page_rows),
            ))
        return _ActiveV2SurfaceCommitmentV1(
            operation=op.value, exchange_index=idx, pages=tuple(pages),
            page_count=len(pages), pagination_exhausted=True,
        )

    d0 = fixture.status_before.exchange_index_domain
    d1 = fixture.status_after.exchange_index_domain
    per_index = tuple(
        _ActiveV2PerIndexCommitmentV1(
            exchange_index=t.exchange_index,
            orders=_surface(ActivePreReleaseReadOperationV2.GET_ORDERS, t.exchange_index, t.orders, t.order_rows),
            fills=_surface(ActivePreReleaseReadOperationV2.GET_FILLS, t.exchange_index, t.fills, t.fill_rows),
            positions=_surface(ActivePreReleaseReadOperationV2.GET_POSITIONS, t.exchange_index, t.positions, t.position_rows),
            order_rows=t.order_rows, fill_rows=t.fill_rows, position_rows=t.position_rows,
        )
        for t in fixture.per_index_traversals
    )
    market = selected_route_truth.market if isinstance(selected_route_truth.market, Mapping) else {}
    ob = selected_route_truth.orderbook
    ob_identity = ""
    _with_ident = getattr(ob, "with_canonical_identity", None)
    if callable(_with_ident):
        try:
            ob_identity = _with_ident().canonical_snapshot_sha256
        except Exception:  # noqa: BLE001 - synthetic fallback
            ob_identity = ""
    if not _is_hex64(ob_identity):
        ob_identity = _h("synthetic_orderbook_identity", str(type(ob)), market.get("ticker"))
    status_before = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS.value, bookend="BEFORE",
        request_identity_sha256=_h("synthetic_request", "S0", fixture.status_before.response_identity_sha256),
        response_sha256=fixture.status_before.response_identity_sha256,
        canonical_content_sha256=_h("synthetic_status_content", "BEFORE", list(d0)),
        exact_sorted_domain=d0,
    )
    status_after = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS.value, bookend="AFTER",
        request_identity_sha256=_h("synthetic_request", "S1", fixture.status_after.response_identity_sha256),
        response_sha256=fixture.status_after.response_identity_sha256,
        canonical_content_sha256=_h("synthetic_status_content", "AFTER", list(d1)),
        exact_sorted_domain=d1,
    )
    freshness_before = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP.value, bookend="BEFORE",
        request_identity_sha256=_h("synthetic_request", "T0", fixture.freshness_before.response_identity_sha256),
        response_sha256=fixture.freshness_before.response_identity_sha256,
        canonical_content_sha256=_h("synthetic_freshness_content", fixture.freshness_before.as_of_time_utc),
        as_of_time_utc=fixture.freshness_before.as_of_time_utc,
        wall_sample_utc=fixture.freshness_before.as_of_time_utc,
    )
    freshness_after = _ActiveV2BookendCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP.value, bookend="AFTER",
        request_identity_sha256=_h("synthetic_request", "T1", fixture.freshness_after.response_identity_sha256),
        response_sha256=fixture.freshness_after.response_identity_sha256,
        canonical_content_sha256=_h("synthetic_freshness_content", fixture.freshness_after.as_of_time_utc),
        as_of_time_utc=fixture.freshness_after.as_of_time_utc,
        wall_sample_utc=fixture.freshness_after.as_of_time_utc,
    )
    selected_market = _ActiveV2ContentCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_MARKET.value,
        request_identity_sha256=_h("synthetic_request", "GET_MARKET", market.get("ticker")),
        response_identity_sha256=_h("synthetic_market_response", _canonical_account_wide_row(market) if market else []),
        canonical_consumed_digest_sha256=_h("ARB_KALSHI_DEMO_ACTIVE_V2_MARKET_ECON_V1", _canonical_account_wide_row(market) if market else []),
    )
    selected_orderbook = _ActiveV2ContentCommitmentV1(
        operation=ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK.value,
        request_identity_sha256=_h("synthetic_request", "GET_MARKET_ORDERBOOK", market.get("ticker")),
        response_identity_sha256=ob_identity,
        canonical_consumed_digest_sha256=_h(
            "ARB_KALSHI_DEMO_ACTIVE_V2_ORDERBOOK_ECON_V1",
            {k: str(v) for k, v in _market_data_snapshot(market, ob).items()} if market else {},
        ),
    )
    return _ActiveV2AcquiredReadV1(
        status_before=status_before, status_after=status_after,
        freshness_before=freshness_before, freshness_after=freshness_after,
        selected_market=selected_market, selected_orderbook=selected_orderbook,
        per_index=per_index, exact_order_supplements=(),
        d0=d0, d1=d1, fixture=fixture, selected_route_truth=selected_route_truth,
        t0_wall_sample_utc=fixture.freshness_before.as_of_time_utc,
        t1_wall_sample_utc=fixture.freshness_after.as_of_time_utc,
    )


class _FakeTrustedDynamicReadAcquirerV2(_TrustedDynamicReadAcquirerV2):
    """DSB-DYN-004 -- the ONLY synthetic-current-read seam.  Module-private and
    used only by the runner test module.  It consumes synthetic
    ``DynamicIndexDomainAccountWideReadV1`` fixture material internally,
    converts it to the ONE converged ``_ActiveV2AcquiredReadV1`` shape, and
    mints a private ``_ReleaseEligibleDynamicIndexDomainReadSetV2`` ONLY
    through this same trusted acquisition boundary
    (``_mint_release_eligible_read_set``).  A cryptographic bearer token, a
    public dataclass constructor, a plugin source, or a separate source module
    are NOT permitted alternatives, and it must not retain a weaker
    read-set / ADRS2 shape."""

    __slots__ = ("_fixture", "_selected_route_truth", "_opened", "_implied_request_count")

    def __init__(
        self,
        *,
        fixture: "DynamicIndexDomainAccountWideReadV1",
        selected_route_truth: "AuthoritativeReadTruthV1",
        runtime: "ExperimentRunnerRuntimeV2 | None" = None,  # accepted for symmetry; not identity-pinned
        opened: "OpenResult | None" = None,
        implied_request_count: int = 72,
    ) -> None:
        del runtime
        if type(fixture) is not DynamicIndexDomainAccountWideReadV1:
            raise RunnerError(RunnerFailureCode.CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED, detail="fake seam requires a DynamicIndexDomainAccountWideReadV1 fixture")
        if type(selected_route_truth) is not AuthoritativeReadTruthV1:
            raise RunnerError(RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN, detail="selected-route truth type")
        if type(implied_request_count) is not int or not 0 <= implied_request_count <= PRE_RELEASE_READ_REQUEST_MAX_V2:
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_BUDGET_EXHAUSTED, detail="implied request count out of range")
        self._fixture = fixture
        self._selected_route_truth = selected_route_truth
        self._opened = opened
        self._implied_request_count = implied_request_count

    def acquire(self, capability: "_TrustedDynamicPreReleaseReadCapabilityV2") -> "_ReleaseEligibleDynamicIndexDomainReadSetV2":
        if type(capability) is not _TrustedDynamicPreReleaseReadCapabilityV2:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="capability type")
        if capability.is_consumed:
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="capability already consumed")
        # Charge the fixture's implied request count one unit at a time through
        # the same pre-transport charge boundary the live path uses, so budget
        # / deadline accounting is identical.
        for i in range(self._implied_request_count):
            op = (
                ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS if i < 2
                else ActivePreReleaseReadOperationV2.GET_USER_DATA_TIMESTAMP if i < 4
                else ActivePreReleaseReadOperationV2.GET_MARKET if i == 4
                else ActivePreReleaseReadOperationV2.GET_MARKET_ORDERBOOK if i == 5
                else ActivePreReleaseReadOperationV2.GET_ORDERS
            )
            capability.charge(op)
        acquired = _synthesize_active_v2_acquired(self._fixture, self._selected_route_truth, runtime=capability.runtime)
        return _mint_release_eligible_read_set(capability, acquired=acquired, opened=self._opened)


def _issue_trusted_dynamic_pre_release_read_capability_v2(
    runtime: "ExperimentRunnerRuntimeV2", existing_invocation_deadline_ns: int,
) -> "_TrustedDynamicPreReleaseReadCapabilityV2":
    """DSB-DYN-002 -- the SOLE production route by which a usable
    ``_TrustedDynamicPreReleaseReadCapabilityV2`` is created.  Called only by
    ``run_pre_release_read_phase_v2`` AFTER Stage 3C's local
    release-impossibility gate has returned no blocking reasons.  Stage 3D
    receives the already-running absolute invocation deadline; issuing the
    capability does NOT create a new 300-second window."""
    if type(runtime) is not ExperimentRunnerRuntimeV2:
        raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_REQUIRED, detail="runtime type")
    if type(existing_invocation_deadline_ns) is not int or existing_invocation_deadline_ns < 0:
        raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="existing invocation deadline")
    return _TrustedDynamicPreReleaseReadCapabilityV2(
        _TRUSTED_DYNAMIC_CAPABILITY_KEY, runtime=runtime,
        absolute_invocation_deadline_ns=existing_invocation_deadline_ns,
    )


def _acquire_release_eligible_dynamic_index_domain_read_set_v2(
    runtime: "ExperimentRunnerRuntimeV2",
    capability: "_TrustedDynamicPreReleaseReadCapabilityV2",
    *,
    selected_ticker: str,
    opened: "OpenResult | None" = None,
) -> "_ReleaseEligibleDynamicIndexDomainReadSetV2":
    """DSB-DYN-002 / DSB-READSET-004 -- Stage 3E.  Runs the trusted acquirer
    that owns every current venue GET and returns exactly one private
    ``_ReleaseEligibleDynamicIndexDomainReadSetV2``.  Stage 3F (the caller)
    accepts the result only if: the exact private type; the live issuer
    lineage belongs to THIS runtime/process/capability; the capability is
    consumed exactly once; the active contract/domain match the current
    runtime exactly; the read-set self-hash verifies; and the absolute
    invocation deadline has not expired.  A deserialized or caller-reconstructed
    value-equivalent object is rejected ``CALLER_SUPPLIED_DYNAMIC_READ_SET_
    REJECTED`` even if every hash is correct."""
    if type(runtime) is not ExperimentRunnerRuntimeV2:
        raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_REQUIRED, detail="runtime type")
    if type(capability) is not _TrustedDynamicPreReleaseReadCapabilityV2 or capability.runtime is not runtime:
        raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="capability/runtime mismatch")
    if capability.is_consumed:
        raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="capability already consumed before Stage 3E")

    seam = runtime.trusted_dynamic_read_acquirer_test_seam
    if seam is not None:
        if not isinstance(seam, _FakeTrustedDynamicReadAcquirerV2):
            raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="only a _FakeTrustedDynamicReadAcquirerV2 may occupy the test seam")
        acquirer: _TrustedDynamicReadAcquirerV2 = seam
    else:
        acquirer = _LiveTrustedDynamicReadAcquirerV2(runtime, selected_ticker=selected_ticker, opened=opened)

    result = acquirer.acquire(capability)

    if type(result) is not _ReleaseEligibleDynamicIndexDomainReadSetV2:
        raise RunnerError(RunnerFailureCode.CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED, detail="Stage 3E result is not the private release-eligible type")
    if (
        getattr(result, "_issuer_sentinel", None) is not capability.issuer_sentinel
        or getattr(result, "_nonce", None) != capability.nonce
        or getattr(result, "_capability_obj_id", None) != id(capability)
    ):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_SOURCE_MISMATCH, detail="read-set issuer lineage does not match this capability")
    if not capability.is_consumed:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_SOURCE_MISMATCH, detail="capability was not consumed by the acquirer")
    if not result.verify_self_hash():
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_COMPOSITE_IDENTITY_MISMATCH, detail="read-set self-hash does not verify")
    canonical = result.read_set_canonical
    if (
        canonical.get("active_contract_sha256") != runtime.active_contract.contract_sha256
        or canonical.get("domain_binding_sha256") != runtime.active_contract.domain_binding_sha256
        or canonical.get("conflict_domain_ref") != runtime.active_contract.conflict_domain_ref
        or canonical.get("subaccount") != runtime.domain_binding.subaccount
        or canonical.get("selected_exchange_index") != runtime.domain_binding.exchange_index
        or dict(canonical.get("accepted_dynamic_source_identity") or {}) != dict(_ACTIVE_DYNAMIC_SOURCE_IDENTITY)
    ):
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_SOURCE_MISMATCH, detail="read-set does not match the current runtime active contract/domain")
    if runtime.monotonic_clock_ns() >= capability.absolute_invocation_deadline_ns:
        raise RunnerError(RunnerFailureCode.DYNAMIC_READ_DEADLINE_EXHAUSTED, detail="absolute invocation deadline expired during Stage 3E result construction")
    return result


def _build_active_experiment_runner_runtime_v2_for_test(
    *, fake_acquirer_factory: Callable[["ExperimentRunnerRuntimeV2"], "_FakeTrustedDynamicReadAcquirerV2"] | None = None, **kwargs: object,
) -> "ExperimentRunnerRuntimeV2":
    """Module-private test-only factory (DSB-DYN-004).  It builds an active
    runtime via the production factory and then, if requested, attaches a
    ``_FakeTrustedDynamicReadAcquirerV2`` to the single synthetic-current-read
    seam.  Production code never calls this."""
    runtime = build_active_experiment_runner_runtime_v2(**kwargs)  # type: ignore[arg-type]
    if fake_acquirer_factory is None:
        return runtime
    fake = fake_acquirer_factory(runtime)
    if not isinstance(fake, _FakeTrustedDynamicReadAcquirerV2):
        raise RunnerError(RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID, detail="fake_acquirer_factory did not return a _FakeTrustedDynamicReadAcquirerV2")
    return _dataclass_replace(runtime, trusted_dynamic_read_acquirer_test_seam=fake)


@dataclass(frozen=True, slots=True)
class PreReleaseReadPhaseResultV2:
    status: str  # "LOCALLY_BLOCKED" | "READ_PHASE_COMPLETE"
    process_instance_id: str
    local_block_reasons: Tuple[str, ...]
    active_release_state: object
    truth: object
    requests_consumed: int
    trusted_dynamic_read_set_id: str = ""


def run_pre_release_read_phase_v2(
    invocation: ExperimentRunnerInvocationV2,
    runtime: ExperimentRunnerRuntimeV2,
) -> PreReleaseReadPhaseResultV2:
    """Active Stages 3A-3F (DSB-RUN-003).

    3A BOOT_HOLD -> 3B exact local authority/ledger replay through the active
    helper (``runtime.read_local_safety_state`` bound to
    ``read_active_local_safety_state_v1``) -> 3C local
    release-impossibility gate (NO venue current-read request occurs before
    3C succeeds; a 3C denial consumes NO pre-release capability/request
    budget) -> 3D issue exactly one ``_TrustedDynamicPreReleaseReadCapabilityV2``
    receiving the already-running absolute invocation deadline -> 3E the live
    trusted acquirer OWNS every current venue GET and returns exactly one
    private ``_ReleaseEligibleDynamicIndexDomainReadSetV2`` -> 3F assemble
    ``ActiveReleaseEvaluationStateV1`` using ONLY that private read-set's
    identity and folded truth.

    Correction 02: this entrypoint takes NO caller-supplied
    ``DynamicIndexDomainAccountWideReadV1`` / ``ProvenAccountWideReadV1`` /
    ``SubaccountWideCompletenessTheoremV1`` / ``dict`` / callback -- current
    Path-A truth can only come from the trusted acquisition boundary
    (``deterministic self-hash != authoritative-source proof``).  It never
    acquires RELEASE_ONLY / issues a completion token / acquires NORMAL_WRITER."""
    if type(invocation) is not ExperimentRunnerInvocationV2:
        raise RunnerError(RunnerFailureCode.ACTIVE_GATE_ENTRY_PRECONDITION_FAILED, detail="invocation type")
    if type(runtime) is not ExperimentRunnerRuntimeV2:
        raise RunnerError(RunnerFailureCode.ACTIVE_GATE_ENTRY_PRECONDITION_FAILED, detail="runtime type")

    process_instance_id = runtime.normal_gate.process_instance_id

    opened = runtime.read_local_safety_state()
    if type(opened) is not OpenResult:
        raise RunnerError(RunnerFailureCode.ACTIVE_GATE_ENTRY_PRECONDITION_FAILED, detail="local state type")

    reasons = _local_impossibility_reasons(
        opened, writer_proof_id=runtime.active_contract.writer_proof_id,
        allowed_completeness=_ACTIVE_LOCAL_COMPLETENESS_VALUES,
    )
    if reasons:
        return PreReleaseReadPhaseResultV2(
            status="LOCALLY_BLOCKED", process_instance_id=process_instance_id,
            local_block_reasons=reasons, active_release_state=None, truth=None,
            requests_consumed=0, trusted_dynamic_read_set_id="",
        )

    # Stage 3D -- one closed process-local trusted capability, receiving the
    # already-running absolute invocation deadline (no reset).
    capability = _issue_trusted_dynamic_pre_release_read_capability_v2(
        runtime, runtime.experiment_absolute_end_monotonic_ns,
    )

    # Stage 3E -- the live trusted acquirer owns every current venue GET and
    # returns exactly one private release-eligible read-set.
    read_set = _acquire_release_eligible_dynamic_index_domain_read_set_v2(
        runtime, capability, selected_ticker=invocation.market_ticker, opened=opened,
    )

    truth = read_set.selected_route_truth

    # Stage 3F -- assemble ActiveReleaseEvaluationStateV1 committing to the
    # exact private read-set identity.
    active_release_state = assemble_active_release_evaluation_state_v1(
        runtime, truth, opened.projection,
        trusted_dynamic_read_set_id=read_set.read_set_id,
    )

    return PreReleaseReadPhaseResultV2(
        status="READ_PHASE_COMPLETE", process_instance_id=process_instance_id,
        local_block_reasons=(), active_release_state=active_release_state, truth=truth,
        requests_consumed=read_set.pre_release_requests_consumed,
        trusted_dynamic_read_set_id=read_set.read_set_id,
    )


@dataclass(frozen=True, slots=True)
class _Stage3ActiveReleaseAndNormalWriterResultV1:
    """Gate-C active (Stage 3G-3K) success carrier.  Module-private, no
    export/serialization/secret field.  Carries the one active_contract and
    the live NormalWriterAcquisition forward for Gate D."""

    process_instance_id: str
    release_id: str
    normal_writer_session_id: str
    normal_writer_acquisition: NormalWriterAcquisition
    active_contract: ActiveExecutionDomainContractV1
    trusted_dynamic_read_set_id: str = ""


def _complete_stage3_active_release_and_normal_writer_v2(
    read_phase_result: PreReleaseReadPhaseResultV2,
    runtime: ExperimentRunnerRuntimeV2,
) -> _Stage3ActiveReleaseAndNormalWriterResultV1:
    """Active Stages 3G-3K.  3G acquire_active_release_only_v1 -> 3H durable
    release (evaluate_release / record_risk_release / release_writer_proof /
    record_writer_eligible) -> 3I issue_active_current_process_release_
    completion_v2 -> 3J acquire_active_normal_writer_state_v1 -> 3K
    active-contract/domain revalidation.  One runtime.active_contract object
    is carried through every stage; no LegacyIncidentContract and no V1
    token can enter."""

    if type(runtime) is not ExperimentRunnerRuntimeV2:
        raise RunnerError(RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED, detail="runtime type")
    if (
        type(read_phase_result) is not PreReleaseReadPhaseResultV2
        or read_phase_result.status != "READ_PHASE_COMPLETE"
        or type(read_phase_result.active_release_state) is not ActiveReleaseEvaluationStateV1
        or read_phase_result.process_instance_id != runtime.normal_gate.process_instance_id
        or type(runtime.risk_config) is not RiskLimitConfigV1
        or read_phase_result.active_release_state.active_contract.contract_sha256
        != runtime.active_contract.contract_sha256
        or read_phase_result.active_release_state.trusted_dynamic_read_set_id
        != read_phase_result.trusted_dynamic_read_set_id
        or read_phase_result.trusted_dynamic_read_set_id[:6] != "ADRS2_"
        or len(read_phase_result.trusted_dynamic_read_set_id) != 70
    ):
        raise RunnerError(RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED)
    if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="before active RELEASE_ONLY")

    active_contract = runtime.active_contract

    acquisition = acquire_active_release_only_v1(
        runtime.authority_binding,
        canonical_repository_root=runtime.canonical_repository_root,
        active_contract=active_contract,
        expected_ledger_path=runtime.expected_ledger_path,
        clock=runtime.wall_clock,
        uuid_factory=runtime.uuid_factory,
        monotonic_clock_ns=runtime.monotonic_clock_ns,
        release_wall_clock=runtime.wall_clock,
    )
    if (
        acquisition.failure_code is not None
        or type(acquisition.handle) is not ReleaseLedgerHandle
        or acquisition.authority_ledger_relation is not AuthorityLedgerRelation.EQUAL
    ):
        if acquisition.handle is not None:
            acquisition.handle.close()
        raise RunnerError(RunnerFailureCode.RELEASE_ONLY_ACQUISITION_FAILED)
    handle = acquisition.handle

    try:
        assessment = handle.evaluate_release(read_phase_result.active_release_state.inner)
    except LedgerError as exc:
        handle.close()
        raise RunnerError(RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED, detail="evaluate_release") from exc
    for step_name, step in (
        ("record_risk_release", handle.record_risk_release),
        ("release_writer_proof", handle.release_writer_proof),
        ("record_writer_eligible", handle.record_writer_eligible),
    ):
        try:
            step(assessment)
        except LedgerError as exc:
            handle.close()
            raise RunnerError(RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED, detail=step_name) from exc

    if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
        handle.close()
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="before active completion token")

    try:
        token = issue_active_current_process_release_completion_v2(
            handle, assessment, active_contract=active_contract,
            trusted_dynamic_read_set_id=read_phase_result.trusted_dynamic_read_set_id,
        )
    except LedgerError as exc:
        handle.close()
        raise RunnerError(RunnerFailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_ISSUANCE_FAILED) from exc
    if type(token) is not CurrentProcessReleaseCompletionV2:
        raise RunnerError(RunnerFailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_ISSUANCE_FAILED)

    if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
        raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="before active NORMAL_WRITER")

    normal = acquire_active_normal_writer_state_v1(
        runtime.authority_binding,
        canonical_repository_root=runtime.canonical_repository_root,
        risk_config=runtime.risk_config,
        process_instance_id=runtime.normal_gate.process_instance_id,
        current_process_release_completion=token,
        active_contract=active_contract,
        expected_ledger_path=runtime.expected_ledger_path,
        clock=runtime.wall_clock,
        uuid_factory=runtime.uuid_factory,
    )
    if normal.handle is None:
        raise RunnerError(RunnerFailureCode.NORMAL_WRITER_ACQUISITION_FAILED)

    locked = normal.handle
    session_id = normal.normal_writer_session_id
    try:
        if (
            normal.failure_code is not None
            or session_id is None
            or _WRITER_SESSION_ID_PATTERN.fullmatch(session_id) is None
            or normal.authority_ledger_relation is not AuthorityLedgerRelation.EQUAL
        ):
            raise RunnerError(RunnerFailureCode.NORMAL_WRITER_ACQUISITION_FAILED)

        tail = locked.events[-1]
        authority = locked.authority_row
        observed_tail = (tail.sequence, tail.event_hash)
        projection = locked.projection()
        revalidated = (
            not locked.closed
            and type(projection) is SafetyProjection
            and locked.relation is AuthorityLedgerRelation.EQUAL
            and projection.active_writer_session_id == session_id
            and session_id in projection.writer_sessions
            and projection.active_restricted_session_id is None
            and projection.risk_control_state == "WRITER_ELIGIBLE"
            and projection.active_risk_config_sha256 == runtime.risk_config.sha256
            and projection.writer_proof_state_by_proof_id.get(active_contract.writer_proof_id) == "RELEASED"
            and projection.writer_proof_release_eligible_by_proof_id.get(active_contract.writer_proof_id) is True
            and projection.protected_unresolved_legacy_write_count == 0
            and not projection.unresolved_write_request_ids
            and (authority.trusted_sequence, authority.trusted_event_hash) == observed_tail
            and (projection.trusted_sequence, projection.trusted_event_hash) == observed_tail
            and (projection.last_sequence, projection.terminal_event_hash) == observed_tail
            and token.incident_id == active_contract.incident_id
            and token.writer_proof_id == active_contract.writer_proof_id
            and token.active_contract_sha256 == active_contract.contract_sha256
            and token.v1.process_instance_id == runtime.normal_gate.process_instance_id
        )
        if not revalidated:
            raise RunnerError(RunnerFailureCode.STAGE_3K_REVALIDATION_FAILED)
        if runtime.monotonic_clock_ns() >= runtime.experiment_absolute_end_monotonic_ns:
            raise RunnerError(RunnerFailureCode.DEADLINE_EXCEEDED, detail="active Stage-3K success boundary")
    except Exception:
        _fail_closed_end_writer_session(locked, session_id)
        raise

    return _Stage3ActiveReleaseAndNormalWriterResultV1(
        process_instance_id=runtime.normal_gate.process_instance_id,
        release_id=token.v1.release_id,
        normal_writer_session_id=session_id,
        normal_writer_acquisition=normal,
        active_contract=active_contract,
        trusted_dynamic_read_set_id=read_phase_result.trusted_dynamic_read_set_id,
    )


def run_active_experiment_stage3_and_gate_d(
    invocation: ExperimentRunnerInvocationV2,
    runtime: ExperimentRunnerRuntimeV2,
    *,
    decision_cycle_max: int = GATE_D_DECISION_CYCLE_MAX,
) -> "GateDLoopResultV1":
    """One explicit active entrypoint: Stage 3A-3F -> Stage 3G-3K -> enter
    the ordinary Gate-D decision loop, and ONLY from that active Stage-3K
    result (DSB-RUN-003).  A LOCALLY_BLOCKED Stage-3C outcome raises rather
    than silently returning an empty loop result.

    Correction 02: current Path-A truth comes ONLY from the trusted dynamic
    pre-release acquisition boundary -- there is no caller-supplied
    completeness/read-set parameter."""
    read_phase = run_pre_release_read_phase_v2(invocation, runtime)
    if read_phase.status != "READ_PHASE_COMPLETE":
        raise RunnerError(
            RunnerFailureCode.ACTIVE_GATE_ENTRY_PRECONDITION_FAILED,
            detail="locally blocked: " + ",".join(read_phase.local_block_reasons),
        )
    stage3 = _complete_stage3_active_release_and_normal_writer_v2(read_phase, runtime)
    return run_gate_d_ordinary_decision_loop(
        stage3, runtime, invocation, decision_cycle_max=decision_cycle_max,
    )
