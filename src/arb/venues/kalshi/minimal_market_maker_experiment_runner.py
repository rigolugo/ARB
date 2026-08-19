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
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Sequence, Tuple

from arb.execution_ledger import (
    AuthorityLedgerRelation,
    AuthorityNamespaceBinding,
    EventInput,
    EventType,
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
    CURRENT_LEGACY_INCIDENT_CONTRACT,
    CurrentProcessReleaseCompletionV1,
    LegacyIncidentContract,
    NormalWriterAcquisition,
    ReleaseEvaluationStateV1,
    ReleaseReconciliationSnapshotV1,
    ReleaseRiskSnapshotV1,
    ReleaseLedgerHandle,
    TrustedReleaseEvidenceProjectionV1,
    TrustedReleaseEvidenceReadResultV1,
    acquire_normal_writer_state,
    acquire_release_only,
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
    "ExperimentRunnerInvocationV1",
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
    CREATE_ORDER_V2 = "CREATE_ORDER_V2"
    CANCEL_ORDER_V2 = "CANCEL_ORDER_V2"


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
) -> list[Tuple[str, str]]:
    if operation is RunnerOperation.GET_ORDERS:
        return [
            ("ticker", ticker or ""),
            ("status", "resting"),
            ("limit", str(_GET_ORDERS_LIMIT)),
            ("subaccount", str(_SUBACCOUNT)),
            ("exchange_index", str(_EXCHANGE_INDEX)),
        ]
    if operation is RunnerOperation.GET_FILLS:
        return [
            ("order_id", order_id or ""),
            ("limit", str(_GET_FILLS_LIMIT)),
            ("subaccount", str(_SUBACCOUNT)),
            ("exchange_index", str(_EXCHANGE_INDEX)),
        ]
    if operation is RunnerOperation.GET_POSITIONS:
        return [
            ("ticker", ticker or ""),
            ("limit", str(_GET_POSITIONS_LIMIT)),
            ("subaccount", str(_SUBACCOUNT)),
            ("exchange_index", str(_EXCHANGE_INDEX)),
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

    query_pairs = _first_page_query(operation, ticker=ticker, order_id=order_id)
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


def _parse_market(raw: object, *, expected_ticker: str) -> Mapping[str, object]:
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
    if exchange_index != _EXCHANGE_INDEX:
        raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="exchange_index mismatch")

    price_ranges = _parse_price_ranges(_require_field(market, "price_ranges", code=RunnerFailureCode.MARKET_GRID_INVALID))
    reference_raw = _require_field(market, "yes_bid_dollars", code=RunnerFailureCode.MARKET_GRID_INVALID)
    reference_price = _decimal_from_price_string(reference_raw)
    try:
        validate_price_ranges(reference_price, price_ranges)
    except RiskControlError as exc:
        raise RunnerError(RunnerFailureCode.MARKET_GRID_INVALID, detail="reference price off-grid") from exc

    return market


def _working_order_from_raw(raw: object, *, expected_ticker: str) -> WorkingOrderV1 | None:
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
    if ticker != expected_ticker or subaccount != _SUBACCOUNT or exchange_index != _EXCHANGE_INDEX:
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


def _fill_from_raw(raw: object, *, expected_ticker: str, expected_order_id: str) -> EconomicFillV1:
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
        or subaccount != _SUBACCOUNT or exchange_index != _EXCHANGE_INDEX
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
    )

    def __init__(
        self, issuance_key: object, *, process_instance_id: str, ticker: str,
        runtime: ExperimentRunnerRuntimeV1,
        budget_max: int = PRE_RELEASE_READ_REQUEST_MAX,
        exhausted_code: "RunnerFailureCode | None" = None,
    ) -> None:
        if issuance_key is not _CAPABILITY_ISSUANCE_KEY:
            raise RunnerError(RunnerFailureCode.CAPABILITY_ISSUANCE_UNAUTHORIZED)
        if type(process_instance_id) is not str or process_instance_id == "":
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="process_instance_id")
        if type(ticker) is not str or _TICKER_PATTERN.fullmatch(ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="capability ticker")
        if type(runtime) is not ExperimentRunnerRuntimeV1:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="runtime type")
        if type(budget_max) is not int or budget_max <= 0:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="budget_max")
        self.__process_instance_id = process_instance_id
        self.__ticker = ticker
        self.__runtime = runtime
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
        result = _parse_market(parsed, expected_ticker=self.__ticker)
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
            order = _working_order_from_raw(row, expected_ticker=self.__ticker)
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
        confirmed = _working_order_from_raw(order_row, expected_ticker=self.__ticker)
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
            _fill_from_raw(row, expected_ticker=self.__ticker, expected_order_id=order_id)
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
            if row_ticker != self.__ticker or row_subaccount != _SUBACCOUNT or row_exchange_index != _EXCHANGE_INDEX:
                raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="position scope mismatch")
            validated.append(row)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_SCHEMA_VALIDATION)
        check_deadline(deadline, self.__runtime.monotonic_clock_ns(), checkpoint=DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return {"market_positions": tuple(validated), "cursor": response_cursor}


def _issue_pre_release_read_capability(
    *, process_instance_id: str, ticker: str, runtime: ExperimentRunnerRuntimeV1,
) -> PreReleaseReadCapabilityV1:
    """Module-private factory (Marco Blocker 01): the sole route by which a
    usable `PreReleaseReadCapabilityV1` is ever constructed. Called only by
    `run_pre_release_read_phase`, and only after Stage 3C's local
    release-impossibility gate has already returned no blocking reasons --
    i.e. the successful Stage-3C -> Stage-3D transition IS the issuance
    event. A caller cannot reach this factory by importing the module; it
    is not exported and is not part of `__all__`."""

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


def _local_impossibility_reasons(opened: OpenResult, *, writer_proof_id: str) -> Tuple[str, ...]:
    """Evaluate the full local release-impossibility predicate set (Spec 04
    ER04-PRE-004; dispatch Implementation-02 Section 8) against a
    `SafetyProjection` obtained from the read-only local-state open.
    Returns an empty tuple only when release has NOT already been
    disproven by durable facts (i.e. the pre-release read phase may
    proceed); any nonempty tuple means Stage 3C must stop before Stage 3D
    -- before capability issuance, credential resolution, signing, or any
    venue transport/budget consumption.
    """

    if opened.projection is None:
        return (f"LOCAL_STATE_UNAVAILABLE:{opened.failure_code.value if opened.failure_code else 'UNKNOWN'}",)
    projection = opened.projection
    reasons: list[str] = []
    if projection.history_completeness != "COMPLETE":
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
        incident_id=invocation.incident_id,
        writer_proof_id=invocation.writer_proof_id,
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


def _issue_gate_d_read_capability(
    *, process_instance_id: str, ticker: str, runtime: ExperimentRunnerRuntimeV1,
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

    return PreReleaseReadCapabilityV1(
        _CAPABILITY_ISSUANCE_KEY, process_instance_id=process_instance_id, ticker=ticker, runtime=runtime,
        budget_max=GATE_D_READ_REQUEST_MAX, exhausted_code=RunnerFailureCode.GATE_D_READ_BUDGET_EXHAUSTED,
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
    if subaccount != _SUBACCOUNT:
        return "SUBACCOUNT_MISMATCH"
    exchange_index = order_row.get("exchange_index")
    if type(exchange_index) is not int:
        return "EXCHANGE_INDEX_MISSING_OR_MALFORMED"
    if exchange_index != _EXCHANGE_INDEX:
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
    runtime: ExperimentRunnerRuntimeV1,
    invocation: ExperimentRunnerInvocationV1,
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
    runtime: ExperimentRunnerRuntimeV1,
    invocation: ExperimentRunnerInvocationV1,
    projection: "SafetyProjection",
    truth: AuthoritativeReadTruthV1,
    reconstruction: ReconstructedSlotOwnershipV1,
    selected: SelectedWriteV1,
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

    prepared = build_cancel_prepared_payload(
        request_id=request_id, environment="KALSHI_DEMO", venue_order_id=target_venue_order_id,
        client_order_id=working_order.client_order_id, adapter_payload_schema_id=_GATE_D_CANCEL_ADAPTER_PAYLOAD_SCHEMA_ID,
    )
    unresolved_exposure_usd = _gate_d_unresolved_exposure_usd(projection, truth)
    assessment = build_cancel_writer_eligibility_assessment(
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
        identity_violation = _gate_d_validate_terminal_order_identity(
            order_row, expected_order_id=target_venue_order_id, expected_client_order_id=working_order.client_order_id,
            expected_ticker=invocation.market_ticker, expected_outcome_side=working_order.outcome_side,
            expected_yes_price=working_order.yes_price,
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
    runtime: ExperimentRunnerRuntimeV1,
    invocation: ExperimentRunnerInvocationV1,
    projection: "SafetyProjection",
    truth: AuthoritativeReadTruthV1,
    reconstruction: ReconstructedSlotOwnershipV1,
    selected: SelectedWriteV1,
    desired: DesiredQuoteV1 | None,
    quote_plan_sha256: str,
    plan_input_sha256: str,
    source_book_snapshot_sha256: str,
) -> GateDWriteOutcomeV1:
    """Exact ordinary CREATE send sequence, structurally parallel to
    `_gate_d_execute_cancel`, reusing the unmodified canonical
    `build_writer_eligibility_assessment` candidate-risk projection
    (MM-RISK-002..006, not reopened by Spec 06/07)."""

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
    stage3: "_Stage3ReleaseAndNormalWriterResultV1",
    runtime: ExperimentRunnerRuntimeV1,
    invocation: ExperimentRunnerInvocationV1,
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

    if type(stage3) is not _Stage3ReleaseAndNormalWriterResultV1:
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="stage3 type")
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
        type(runtime) is not ExperimentRunnerRuntimeV1
        or type(runtime.strategy_instance_id) is not str or not runtime.strategy_instance_id
        or type(runtime.minimum_spread_usd) is not Decimal
        or type(runtime.gate_d_incident_id) is not str or not runtime.gate_d_incident_id
        or type(runtime.gate_d_capability_reference_id) is not str or not runtime.gate_d_capability_reference_id
        or not callable(runtime.normal_write_transport)
        or type(runtime.risk_config) is not RiskLimitConfigV1
    ):
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="runtime gate-d bindings")
    if type(invocation) is not ExperimentRunnerInvocationV1:
        raise RunnerError(RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED, detail="invocation type")
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
