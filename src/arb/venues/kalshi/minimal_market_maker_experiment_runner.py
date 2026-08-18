"""Kalshi Demo minimal two-sided market-maker experiment runner -- Gate B.

Implements ONLY the authoritative-truth / read-only reconciliation spine
required by
`KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_EXPERIMENT_RUNNER_SPEC_04.md`
(bytes 45629, sha256
32d45abd79dafae7ffa960cfa3c15a9f536fc75d593a4c61e6ab2d3653f0e1f0), which
incorporates by exact predecessor identity every non-superseded requirement
of
`KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_EXPERIMENT_RUNNER_SPEC_03.md`
(bytes 117449, sha256
09bdca72ea83c4b701ee8c743b06f384c7fe682f7fb5bf14459ab484dad81771).

Gate B scope (refined Stage 3 of the preserved 20-stage runner sequence):

    3A  process starts BOOT_HOLD
    3B  open exact authority/ledger read/local-gate path and replay
    3C  reject locally if any non-freshness release predicate is already false
    3D  if structurally release-capable, expose only PreReleaseReadCapabilityV1
    3E  collect bounded current-process read/reconciliation truth
    3F  close venue-read phase; assemble exact ReleaseEvaluationStateV1

Gate B stops before Stage 3G (acquiring `RELEASE_ONLY` and completing the
durable release/session-end sequence).  It never constructs a
`CurrentProcessReleaseCompletionV1`, never acquires a normal writer, and
never exposes the write-capable experiment surface.  Those stages, the
20-stage decision loop, and CREATE/CANCEL dispatch belong to a later gate.

Six-path writable envelope (Spec 04 Section 11) -- this file and its test
module are two of the six; the remaining four
(`src/arb/execution_ledger.py`, `tests/test_execution_ledger.py`,
`src/arb/venues/kalshi/ledger_binding.py`,
`tests/test_kalshi_ledger_binding.py`) are protected and unmodified by this
task.  Every type imported from those files is used exactly as canonically
defined; none is re-implemented here.
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
    OpenResult,
    RestartClassification,
    SafetyProjection,
    acquire_local_state,
    canonical_json_bytes,
    canonical_timestamp,
    sha256_hex,
    validate_canonical_timestamp,
)
from arb.venues.kalshi.ledger_binding import (
    CURRENT_LEGACY_INCIDENT_CONTRACT,
    ReleaseEvaluationStateV1,
    ReleaseReconciliationSnapshotV1,
    ReleaseRiskSnapshotV1,
    TrustedReleaseEvidenceProjectionV1,
    TrustedReleaseEvidenceReadResultV1,
)
from arb.venues.kalshi.risk_control import (
    EconomicFillV1,
    FreshnessStampV1,
    PriceRangeV1,
    RiskControlError,
    RiskLimitConfigV1,
    UNKNOWN_UNBOUNDED,
    WorkingOrderV1,
    WriterEligibilityGate,
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
        "__lock", "__ordinal", "__authoritative_order_ids",
    )

    def __init__(
        self, issuance_key: object, *, process_instance_id: str, ticker: str,
        runtime: ExperimentRunnerRuntimeV1,
    ) -> None:
        if issuance_key is not _CAPABILITY_ISSUANCE_KEY:
            raise RunnerError(RunnerFailureCode.CAPABILITY_ISSUANCE_UNAUTHORIZED)
        if type(process_instance_id) is not str or process_instance_id == "":
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="process_instance_id")
        if type(ticker) is not str or _TICKER_PATTERN.fullmatch(ticker) is None:
            raise RunnerError(RunnerFailureCode.MARKET_IDENTITY_INVALID, detail="capability ticker")
        if type(runtime) is not ExperimentRunnerRuntimeV1:
            raise RunnerError(RunnerFailureCode.PRE_RELEASE_CAPABILITY_NOT_AUTHORIZED, detail="runtime type")
        self.__process_instance_id = process_instance_id
        self.__ticker = ticker
        self.__runtime = runtime
        self.__consumed = 0
        self.__ordinal = 0
        self.__lock = threading.Lock()
        self.__authoritative_order_ids: set[str] = set()

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
            if self.__consumed >= PRE_RELEASE_READ_REQUEST_MAX:
                raise RunnerError(RunnerFailureCode.PRE_RELEASE_READ_BUDGET_EXHAUSTED)
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
