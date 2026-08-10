"""Kalshi Demo one-order REST lifecycle (Revision 06).

SAME_SCOPE_CORRECTION_01: corrects Implementation 01 to conform fully to
``KALSHI_DEMO_ONE_ORDER_LIFECYCLE_SPEC_06.md`` per Marco's BLOCK review,
in particular Sections 7.2, 7.3, 9.3, 9.4, 9.5, and Appendices A, C, D, E,
F, G. No policy, path, dependency, or capability was broadened; this
revision only makes existing accepted-spec requirements load-bearing where
Implementation 01 left them as unused helpers or reduced models.

This module performs **no network I/O of its own**. Every venue call is
issued through a caller-supplied ``LifecycleTransport`` implementation, so
this module can be exercised entirely offline with a fake/deterministic
transport. It never imports ``socket``, ``http.client``, ``urllib``,
``requests``, or any networking library, and it never reads a real
credential value or private key.

All monetary/quantity arithmetic uses ``decimal.Decimal``. Binary
floating-point is never used for a monetary or quantity comparison, and
authoritative fixed-point fields are only ever accepted as JSON strings
(a numeric JSON value where a ``FixedPointCount``/``FixedPointDollars``
string is required is rejected, not coerced).

The ``WriterExclusivityPriorWriteProof`` is never self-issued, fabricated,
broadened, or refreshed anywhere in this module. It is only ever *consumed*
and *validated* -- it must be supplied by the caller (in real use, by a
future execution authorization external to this package), per Appendix F.

Signing helpers implement exactly the accepted signing contract for later
separately authorized execution:

    message = UTF8(timestamp_ms_text + UPPERCASE_METHOD + full_path_without_query)
    algorithm = RSA-PSS, SHA-256, MGF1(SHA-256), salt length 32

``full_path`` always includes ``/trade-api/v2`` and always excludes host,
query, and body. This module never performs real signing against a real
private key; offline tests use synthetic, clearly-fake RSA test key
material only.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import datetime, timezone
from types import MappingProxyType
from decimal import Decimal
from typing import (
    Callable,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    Union,
)

from cryptography.hazmat.primitives import hashes as _hashes
from cryptography.hazmat.primitives.asymmetric import padding as _padding
from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

# Canonical, unmodified Kalshi Demo environment-separation / capability-
# envelope types (SAME_SCOPE_CORRECTION_02, Section 7.1). These are the
# same accepted types already consumed the same way by
# arb.venues.kalshi.orderbook and arb.venues.kalshi.connectivity; this
# module imports them read-only and never modifies models.py/validation.py.
from arb.venues.kalshi.models import (
    CredentialReferenceKind as _CredentialReferenceKind,
    CredentialReferenceState as _CredentialReferenceState,
    EndpointComponents as _EndpointComponents,
    Environment as _Environment,
    RequestedCapability as _RequestedCapability,
    TaskAuthorizationCapabilityEnvelope,
    ValidatedDemoProfile,
    CapabilityEnvelopeError as _CapabilityEnvelopeError,
    require_usable_capability_envelope as _require_usable_capability_envelope,
)

__all__ = [
    # Economics / configuration constants
    "VENUE",
    "ENVIRONMENT",
    "SUBACCOUNT",
    "EXCHANGE_INDEX",
    "QUANTITY",
    "LIMIT_PRICE",
    "TIME_IN_FORCE",
    "SIDE",
    "SELF_TRADE_PREVENTION_TYPE",
    "POST_ONLY",
    "CANCEL_ORDER_ON_PAUSE",
    "REDUCE_ONLY",
    "EXPIRATION_OFFSET_SECONDS",
    "MAX_FILLED_PRINCIPAL",
    "MAX_TOTAL_RISK",
    "DEMO_REST_ORIGIN",
    "SUPPORTED_ORDER_STATUSES",
    # Capabilities
    "CapabilityName",
    "REQUIRED_CAPABILITIES",
    "CapabilityEnvelope",
    # Request budget / deadline
    "LifecycleOperation",
    "OPERATION_BUDGET",
    "GLOBAL_REQUEST_MAXIMUM",
    "RequestBudgetExceededError",
    "RequestBudgetTracker",
    "MASTER_DEADLINE_MS",
    "PER_REQUEST_CEILING_MS",
    "LifecycleDeadline",
    # Identity gates
    "ACCEPTED_SPEC_SHA256",
    "ACCEPTED_SPEC_BYTES",
    "BLOCKED_PREDECESSOR_SPEC_SHA256",
    "SOURCE_OPENAPI_BYTES",
    "SOURCE_OPENAPI_SHA256",
    "SOURCE_RECORD_BYTES",
    "SOURCE_RECORD_SHA256",
    "OPERATION_BINDINGS",
    "sha256_hex",
    "verify_identity",
    "validate_controlling_spec_identity",
    "validate_operation_binding",
    "validate_operation_binding_semantics",
    "validate_source_record_identity",
    "validate_source_identity",
    "parse_and_validate_source_record",
    # Execution authorization / fee-risk binding
    "OneOrderFeeRiskBinding",
    "OneOrderLifecycleDispatchExpectation",
    "OneOrderLifecycleExecutionAuthorization",
    "validate_execution_authorization",
    "validate_lifecycle_input_fields",
    "validate_pre_send_gate",
    # Writer exclusivity / prior-write proof
    "PROOF_SCHEMA_REVISION",
    "PROOF_MODE_FIRST_ACCEPTED_DEMO_WRITE",
    "REQUIRED_PROTECTED_WRITE_OPERATIONS",
    "WriterExclusivityFailureCode",
    "WriterExclusivityPriorWriteProof",
    "validate_writer_proof",
    "is_rfc3339_utc_z",
    # Signing
    "SIGNING_PROFILE",
    "timestamp_ms_text_is_canonical",
    "build_signing_message",
    "sign_lifecycle_request",
    # Order construction / recovery / read validation
    "generate_client_order_id",
    "is_valid_lowercase_uuid4",
    "compute_expiration_time",
    "CREATE_ORDER_ALLOWED_FIELDS",
    "build_create_order_body",
    "validate_create_order_body",
    "GetOrdersResponse",
    "build_pre_create_query",
    "validate_pre_create_response",
    "build_recovery_query",
    "validate_recovery_response",
    "ORDER_REQUIRED_FIELDS",
    "ORDER_FIXED_POINT_STRING_FIELDS",
    "validate_order_record",
    # Fills
    "FILL_REQUIRED_FIELDS",
    "FILL_FIXED_POINT_STRING_FIELDS",
    "CanonicalFill",
    "FillLedger",
    "build_fills_query",
    # Create/cancel result classification
    "SendOutcome",
    "classify_create_response",
    "classify_cancel_response",
    # Cancel
    "build_cancel_query",
    "cancel_is_send_capable",
    "check_cancel_conservation",
    # Orchestration
    "LifecycleHaltCode",
    "LifecycleTerminal",
    "PreparedRequest",
    "RawHttpResponse",
    "LifecycleTransportPreSendError",
    "LifecycleTransportUnknownAfterSendError",
    "LifecycleTransport",
    "OneOrderLifecycleInput",
    "OneOrderLifecyclePlan",
    "OneOrderLifecycleResult",
    "OneOrderLifecycleHalt",
    "plan_demo_one_order_lifecycle",
    "execute_demo_one_order_lifecycle",
]


# ---------------------------------------------------------------------------
# Core closed economics (Spec Section 8.2, "CORE CLOSED ECONOMICS")
# ---------------------------------------------------------------------------

VENUE = "KALSHI"
ENVIRONMENT = "KALSHI_DEMO"
SUBACCOUNT = 0
EXCHANGE_INDEX = 0

QUANTITY = Decimal("1.00")
LIMIT_PRICE = Decimal("0.0100")
TIME_IN_FORCE = "good_till_canceled"
SIDE = "bid"
SELF_TRADE_PREVENTION_TYPE = "taker_at_cross"
POST_ONLY = True
CANCEL_ORDER_ON_PAUSE = True
REDUCE_ONLY = False
EXPIRATION_OFFSET_SECONDS = 45

MAX_FILLED_PRINCIPAL = Decimal("0.010000")
MAX_TOTAL_RISK = Decimal("0.050000")

DEMO_REST_ORIGIN = "https://external-api.demo.kalshi.co"
_TRADE_API_BASE_PATH = "/trade-api/v2"

# Canonical Demo endpoint/profile constants, matching exactly the same
# accepted values already used by arb.venues.kalshi.orderbook and
# arb.venues.kalshi.connectivity (each defines its own private copy of
# these same accepted values; this module follows that established
# per-module pattern rather than importing another module's private
# names).
_DEMO_HOST = "external-api.demo.kalshi.co"
_DEMO_PORT = 443
_DEMO_WEBSOCKET_HOST = "external-api-ws.demo.kalshi.co"
_DEMO_WEBSOCKET_PATH = "/trade-api/ws/v2"
_ACCEPTED_ALLOWLIST_REVISION = "candidate-02"
_ACCEPTED_VALIDATION_SCHEMA_REVISION = 1
_ACCEPTED_CREDENTIAL_REFERENCE_KINDS = (
    _CredentialReferenceKind.API_KEY_ID_ENV_SOURCE,
    _CredentialReferenceKind.PRIVATE_KEY_PEM_ENV_SOURCE,
)
# Envelope fields this write-capable lifecycle requires PERMITTED. Unlike
# the read-only arb.venues.kalshi.orderbook operation, `demo_writes` must
# be PERMITTED here (this lifecycle issues Create/Cancel), not prohibited.
_REQUIRED_PERMITTED_ENVELOPE_FIELDS = (
    "network_access",
    "demo_authenticated_reads",
    "demo_writes",
    "credential_use",
)
# Envelope fields this lifecycle requires PROHIBITED -- production and
# funding capability must never be present, matching Revision 06's
# no-production/no-funding closed negative-capability requirement.
_REQUIRED_PROHIBITED_ENVELOPE_FIELDS = (
    "production_public_reads",
    "production_authenticated_reads",
    "production_writes",
    "account_funding",
)

SUPPORTED_ORDER_STATUSES: FrozenSet[str] = frozenset({"resting", "canceled", "executed"})


# ---------------------------------------------------------------------------
# Capability separation (Spec Section 2.4)
# ---------------------------------------------------------------------------

class CapabilityName(enum.StrEnum):
    """The exact seven distinct capabilities from Section 2.4. No
    capability implies another: authenticated read does not imply write,
    credential presence does not imply any operation, create does not
    imply cancel."""

    PRE_CREATE_ORDER_TRUTH_READ = "KALSHI_DEMO_PRE_CREATE_ORDER_TRUTH_READ"
    ORDER_CREATE = "KALSHI_DEMO_ORDER_CREATE"
    EXACT_ORDER_READ = "KALSHI_DEMO_EXACT_ORDER_READ"
    ORDER_LIST_RECOVERY_READ = "KALSHI_DEMO_ORDER_LIST_RECOVERY_READ"
    FILL_READ = "KALSHI_DEMO_FILL_READ"
    ORDER_CANCEL = "KALSHI_DEMO_ORDER_CANCEL"
    CREDENTIAL_USE = "KALSHI_DEMO_CREDENTIAL_USE"


REQUIRED_CAPABILITIES: FrozenSet[CapabilityName] = frozenset(CapabilityName)

# Which capability each budgeted operation independently requires. Recovery
# uses the same underlying Get Orders OpenAPI operation as pre-create but
# remains a distinct capability, per Section 9.3.
_OPERATION_REQUIRED_CAPABILITY: Mapping["LifecycleOperation", CapabilityName] = {}  # populated below


@dataclass(frozen=True, slots=True)
class CapabilityEnvelope:
    """An explicit, closed set of granted capabilities. Missing capability
    halts before the operation it gates becomes send-capable; capability
    presence is checked independently for every operation and never
    inferred from another operation's capability or from credential
    presence."""

    granted: FrozenSet[CapabilityName]

    def has(self, capability: CapabilityName) -> bool:
        return capability in self.granted

    def missing(self, required: FrozenSet[CapabilityName]) -> FrozenSet[CapabilityName]:
        return required - self.granted


# ---------------------------------------------------------------------------
# Request budget (Spec Appendix A)
# ---------------------------------------------------------------------------

class LifecycleOperation(enum.StrEnum):
    """Closed set of the six budgeted lifecycle request operations."""

    PRE_CREATE_TRUTH = "PRE_CREATE_TRUTH"
    CREATE = "CREATE"
    RECOVERY = "RECOVERY"
    EXACT_ORDER = "EXACT_ORDER"
    FILLS = "FILLS"
    CANCEL = "CANCEL"


# SAME_SCOPE_CORRECTION_03, point 8: the exact fixed method + path
# template for each of the six authorized lifecycle operations, used only
# to validate a PreparedRequest before signing it (see
# sign_lifecycle_request). EXACT_ORDER/CANCEL paths end in a caller-bound
# order_id segment, so those two are matched by prefix plus a single
# non-empty trailing path segment rather than a fixed literal string.
_LIFECYCLE_SIGNING_CONTRACT: Mapping[LifecycleOperation, Tuple[str, str]] = {
    LifecycleOperation.PRE_CREATE_TRUTH: ("GET", "/trade-api/v2/portfolio/orders"),
    LifecycleOperation.CREATE: ("POST", "/trade-api/v2/portfolio/events/orders"),
    LifecycleOperation.RECOVERY: ("GET", "/trade-api/v2/portfolio/orders"),
    LifecycleOperation.EXACT_ORDER: ("GET", "/trade-api/v2/portfolio/orders/"),
    LifecycleOperation.FILLS: ("GET", "/trade-api/v2/portfolio/fills"),
    LifecycleOperation.CANCEL: ("DELETE", "/trade-api/v2/portfolio/events/orders/"),
}


OPERATION_BUDGET: Mapping[LifecycleOperation, int] = {
    LifecycleOperation.PRE_CREATE_TRUTH: 1,
    LifecycleOperation.CREATE: 1,
    LifecycleOperation.RECOVERY: 1,
    LifecycleOperation.EXACT_ORDER: 3,
    LifecycleOperation.FILLS: 4,
    LifecycleOperation.CANCEL: 1,
}

GLOBAL_REQUEST_MAXIMUM = 11

_OPERATION_REQUIRED_CAPABILITY = {
    LifecycleOperation.PRE_CREATE_TRUTH: CapabilityName.PRE_CREATE_ORDER_TRUTH_READ,
    LifecycleOperation.CREATE: CapabilityName.ORDER_CREATE,
    LifecycleOperation.RECOVERY: CapabilityName.ORDER_LIST_RECOVERY_READ,
    LifecycleOperation.EXACT_ORDER: CapabilityName.EXACT_ORDER_READ,
    LifecycleOperation.FILLS: CapabilityName.FILL_READ,
    LifecycleOperation.CANCEL: CapabilityName.ORDER_CANCEL,
}


class RequestBudgetExceededError(Exception):
    """Raised when a reservation would exceed either the per-operation
    branch maximum or the global 11-request maximum. No operation may
    borrow budget from another."""

    def __init__(self, operation: LifecycleOperation) -> None:
        super().__init__(f"request budget exceeded for operation: {operation.value}")
        self.operation = operation


class RequestBudgetTracker:
    """Independent per-operation counters plus one shared global counter.

    No automatic retries are ever issued by this tracker; each
    ``reserve()`` call corresponds to exactly one intended request.
    """

    __slots__ = ("_counts",)

    def __init__(self) -> None:
        self._counts: Dict[LifecycleOperation, int] = {op: 0 for op in LifecycleOperation}

    def used(self, operation: LifecycleOperation) -> int:
        return self._counts[operation]

    def remaining(self, operation: LifecycleOperation) -> int:
        return OPERATION_BUDGET[operation] - self._counts[operation]

    def total_used(self) -> int:
        return sum(self._counts.values())

    def reserve(self, operation: LifecycleOperation) -> None:
        if self._counts[operation] + 1 > OPERATION_BUDGET[operation]:
            raise RequestBudgetExceededError(operation)
        if self.total_used() + 1 > GLOBAL_REQUEST_MAXIMUM:
            raise RequestBudgetExceededError(operation)
        self._counts[operation] += 1

    def snapshot(self) -> Dict[str, int]:
        return {op.value: count for op, count in self._counts.items()}


# ---------------------------------------------------------------------------
# Deadlines (Spec Section "DEADLINE")
# ---------------------------------------------------------------------------

MASTER_DEADLINE_MS = 90_000
PER_REQUEST_CEILING_MS = 10_000


@dataclass(slots=True)
class LifecycleDeadline:
    """One master lifecycle deadline plus a per-request ceiling clipped by
    that same master deadline. There is no second post-network or parsing
    deadline: proof validation, request construction, response parsing,
    fill reconciliation, economic checks, cancel reconciliation, and
    terminal result construction all remain inside this one master
    deadline.
    """

    monotonic_clock: Callable[[], float]
    entry_monotonic: float
    master_deadline_ms: int = MASTER_DEADLINE_MS

    def absolute_deadline_monotonic(self) -> float:
        return self.entry_monotonic + (self.master_deadline_ms / 1000.0)

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = now if now is not None else self.monotonic_clock()
        return current >= self.absolute_deadline_monotonic()

    def effective_request_deadline_monotonic(
        self,
        request_start_monotonic: float,
        per_request_ceiling_ms: int = PER_REQUEST_CEILING_MS,
    ) -> float:
        return min(
            request_start_monotonic + (per_request_ceiling_ms / 1000.0),
            self.absolute_deadline_monotonic(),
        )


# ---------------------------------------------------------------------------
# Identity gates: controlling specification, source, six operation bindings
# ---------------------------------------------------------------------------

ACCEPTED_SPEC_SHA256 = "bb8355ad0022cda0d5ce936ed84993a381028187f207ae4b402f8017c9fbd101"
ACCEPTED_SPEC_BYTES = 101724

# Known blocked predecessor controlling-specification identities. This set
# is informational only -- the primary gate is exact equality against
# ACCEPTED_SPEC_SHA256, which alone rejects every identity below (and any
# other non-matching identity) regardless of enumeration here.
BLOCKED_PREDECESSOR_SPEC_SHA256: FrozenSet[str] = frozenset({
    "f19fa936044a513fc47b19a2a20b08ad116c5f7fef2d2fda8dc47dea97d0dbcf",  # Revision 01
    "b318f444382851e15cfe2ddab70e77f36703aab9a4f55ca99b5da3050f53180f",  # Revision 02
    "e1c5ffacad19a0b81c02a024d101096942f73473cfd97dd5cc0a1c89714241a1",  # Revision 05
})

SOURCE_OPENAPI_BYTES = 333283
SOURCE_OPENAPI_SHA256 = "80f4961e275dba2fed8e464c90c6ee77e3e8d521ec0c2e16b1c94dde8bf0160d"

SOURCE_RECORD_BYTES = 843
SOURCE_RECORD_SHA256 = "10c88fbbbbcc017cd9ac8891cd89dc00c5df6c7ca49c5f8671c1121de695d22a"

# The six exact accepted operation-binding identities (bytes, sha256),
# Appendix D.1-D.6.
OPERATION_BINDINGS: Mapping[str, Tuple[int, str]] = {
    "PRE_CREATE_ORDER_TRUTH": (3844, "f51e23154d775b63a9a3de93bce4af97d368a2747de06fc020621e62496e1959"),
    "CREATE_ORDER_V2": (3558, "03c319dfb9fcfd6c5a909c38f408ba27e48f83e0844ebed47fab7f306e9ff4f9"),
    "EXACT_ORDER_READ": (3082, "ed5312101eddd9658f263d81aa7f41a28ca17e6d71dfd7b4c10b3610f5316792"),
    "ORDER_LIST_RECOVERY": (3987, "e03e8bd348641521f84081bd350387c5eecd4e51b433eae2f99b949eef6a1989"),
    "FILL_READ": (3260, "e421bc5ec7a8f65d97b335c7dd6b7e8c8475abb3f64b7f7f2ffba82f2c6b292d"),
    "CANCEL_ORDER_V2": (2479, "4650e325f30a3cd177ad6b948f96dccb581c06585869a83a84e072a6066cde64"),
}


@dataclass(frozen=True, slots=True)
class _OperationContract:
    binding_name: str
    method: str
    path_template: str
    query_contract: Tuple[Tuple[str, object], ...]
    request_body_required: Optional[bool]
    request_body_absent: bool
    request_required_fields: Tuple[str, ...]
    request_prohibited_fields: Tuple[str, ...]
    request_schema: Optional[str]
    response_required_fields: Tuple[str, ...]
    response_media_type: str
    response_schema: str


def _contract_query(**kwargs: object) -> Tuple[Tuple[str, object], ...]:
    return tuple(sorted(kwargs.items()))


# This is the implementation's own immutable request/response template
# representation. Appendix-D records are parsed independently and must agree
# with these values before transport call 1; byte/hash identity alone is not
# treated as semantic proof.
_CURRENT_OPERATION_CONTRACTS: Mapping[str, _OperationContract] = MappingProxyType({
    "PRE_CREATE_ORDER_TRUTH": _OperationContract(
        "PRE_CREATE_ORDER_TRUTH", "GET", "/portfolio/orders",
        _contract_query(cursor="OMITTED_FIRST_REQUEST", event_ticker="PROHIBITED", limit=1000,
                        max_ts="PROHIBITED", min_ts="PROHIBITED", status="resting",
                        subaccount=0, ticker="EXACT_AUTHORIZED_TICKER"),
        None, True, (), (), None, ("orders", "cursor"), "application/json", "GetOrdersResponse",
    ),
    "CREATE_ORDER_V2": _OperationContract(
        "CREATE_ORDER_V2", "POST", "/portfolio/events/orders", (),
        True, False,
        ("ticker", "client_order_id", "side", "count", "price", "time_in_force",
         "self_trade_prevention_type", "expiration_time", "post_only",
         "cancel_order_on_pause", "reduce_only", "subaccount", "exchange_index"),
        ("order_group_id", "action", "yes_price", "no_price", "type"),
        "CreateOrderV2Request", ("order_id", "fill_count", "remaining_count", "ts_ms"),
        "application/json", "CreateOrderV2Response",
    ),
    "EXACT_ORDER_READ": _OperationContract(
        "EXACT_ORDER_READ", "GET", "/portfolio/orders/{order_id}", (),
        None, True, (), (), None, ("order",), "application/json", "GetOrderResponse",
    ),
    "ORDER_LIST_RECOVERY": _OperationContract(
        "ORDER_LIST_RECOVERY", "GET", "/portfolio/orders",
        _contract_query(cursor="OMITTED_FIRST_REQUEST", event_ticker="PROHIBITED", limit=1000,
                        max_ts="PROHIBITED", min_ts="PROHIBITED", status="OMITTED",
                        subaccount=0, ticker="EXACT_AUTHORIZED_TICKER"),
        None, True, (), (), None, ("orders", "cursor"), "application/json", "GetOrdersResponse",
    ),
    "FILL_READ": _OperationContract(
        "FILL_READ", "GET", "/portfolio/fills",
        _contract_query(cursor="OMITTED_FIRST_REQUEST_OR_EXACT_PRIOR_CURSOR", limit=1000,
                        max_ts="PROHIBITED", min_ts="PROHIBITED",
                        order_id="EXACT_BOUND_ORDER_ID", subaccount=0, ticker="PROHIBITED"),
        None, True, (), (), None, ("fills", "cursor"), "application/json", "GetFillsResponse",
    ),
    "CANCEL_ORDER_V2": _OperationContract(
        "CANCEL_ORDER_V2", "DELETE", "/portfolio/events/orders/{order_id}",
        _contract_query(exchange_index=0, market_ticker="OMITTED", subaccount=0),
        None, True, (), (), None, ("order_id", "reduced_by", "ts_ms"),
        "application/json", "CancelOrderV2Response",
    ),
})


def _parse_operation_binding_contract(name: str, raw_bytes: bytes) -> Optional[_OperationContract]:
    if validate_operation_binding(name, raw_bytes=raw_bytes) is not None:
        return None
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_no_duplicate_keys_object_pairs_hook)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateSourceRecordKeyError):
        return None
    if type(parsed) is not dict or parsed.get("binding_purpose") != name:
        return None
    method = parsed.get("operation_method")
    path_template = parsed.get("operation_path_template")
    response_media_type = parsed.get("response_media_type")
    response_schema = parsed.get("response_schema")
    if not all(type(v) is str for v in (method, path_template, response_media_type, response_schema)):
        return None

    query_obj = parsed.get("project_query_contract")
    if query_obj is None:
        query_contract: Tuple[Tuple[str, object], ...] = ()
    elif type(query_obj) is dict:
        query_contract = tuple(sorted(query_obj.items()))
    else:
        return None

    body_required_value = parsed.get("request_body_required")
    request_body_required: Optional[bool]
    if body_required_value is None:
        request_body_required = None
    elif type(body_required_value) is bool:
        request_body_required = body_required_value
    else:
        return None
    request_body_absent = parsed.get("request_body") == "ABSENT" or request_body_required is None

    required_request = parsed.get("project_required_closed_request_fields", ())
    prohibited_request = parsed.get("project_prohibited_request_fields", ())
    if type(required_request) not in (list, tuple) or not all(type(v) is str for v in required_request):
        return None
    if type(prohibited_request) not in (list, tuple) or not all(type(v) is str for v in prohibited_request):
        return None
    request_schema = parsed.get("request_schema")
    if request_schema is not None and type(request_schema) is not str:
        return None

    response_required = parsed.get("response_required_top_level_fields")
    if response_required is None:
        response_required = parsed.get("response_required_fields")
    if type(response_required) is not list or not all(type(v) is str for v in response_required):
        return None

    return _OperationContract(
        binding_name=name, method=method, path_template=path_template, query_contract=query_contract,
        request_body_required=request_body_required, request_body_absent=request_body_absent,
        request_required_fields=tuple(required_request), request_prohibited_fields=tuple(prohibited_request),
        request_schema=request_schema, response_required_fields=tuple(response_required),
        response_media_type=response_media_type, response_schema=response_schema,
    )


def validate_operation_binding_semantics(
    operation_binding_bytes: Mapping[str, bytes],
) -> Optional[LifecycleHaltCode]:
    if type(operation_binding_bytes) is not dict and not isinstance(operation_binding_bytes, Mapping):
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    if set(operation_binding_bytes.keys()) != set(_CURRENT_OPERATION_CONTRACTS.keys()):
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    for name, expected_current in _CURRENT_OPERATION_CONTRACTS.items():
        raw = operation_binding_bytes.get(name)
        if type(raw) is not bytes:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        parsed = _parse_operation_binding_contract(name, raw)
        if parsed is None or parsed != expected_current:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_identity(*, raw_bytes: bytes, expected_length: int, expected_sha256: str) -> bool:
    """Exact-copy identity check: byte length AND sha256 hex digest must
    both match. Neither check alone is sufficient."""

    if type(raw_bytes) is not bytes:
        return False
    if len(raw_bytes) != expected_length:
        return False
    return sha256_hex(raw_bytes) == expected_sha256


class LifecycleHaltCode(enum.StrEnum):
    """Closed set of deterministic halt reasons. Every halt this module
    can produce is one of these values; nothing here carries a secret
    value, credential, or raw exception text."""

    SPEC_IDENTITY_MISMATCH = "SPEC_IDENTITY_MISMATCH"
    SPEC_IDENTITY_BLOCKED_PREDECESSOR = "SPEC_IDENTITY_BLOCKED_PREDECESSOR"
    SOURCE_IDENTITY_MISMATCH = "TASK_CURRENT_OPENAPI_IDENTITY_MISMATCH"
    SOURCE_RECORD_IDENTITY_MISMATCH = "SOURCE_RECORD_IDENTITY_MISMATCH"
    OPERATION_BINDING_MISMATCH = "LIFECYCLE_OPERATION_BINDING_MISMATCH"
    EXECUTION_AUTHORIZATION_INVALID = "EXECUTION_AUTHORIZATION_INVALID"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    CANONICAL_DEMO_PROFILE_INVALID = "CANONICAL_DEMO_PROFILE_INVALID"
    CANONICAL_CAPABILITY_ENVELOPE_INVALID = "CANONICAL_CAPABILITY_ENVELOPE_INVALID"
    CANONICAL_CAPABILITY_NOT_AUTHORIZED = "CANONICAL_CAPABILITY_NOT_AUTHORIZED"
    CANONICAL_PRODUCTION_OR_FUNDING_CAPABILITY_PRESENT = "CANONICAL_PRODUCTION_OR_FUNDING_CAPABILITY_PRESENT"
    ENVIRONMENT_NOT_DEMO = "ENVIRONMENT_NOT_DEMO"

    # Appendix F.3 / Section 9.5.8 exact writer-exclusivity failure codes.
    WRITER_EXCLUSIVITY_NOT_ESTABLISHED = "WRITER_EXCLUSIVITY_NOT_ESTABLISHED"
    WRITER_EXCLUSIVITY_SCOPE_MISMATCH = "WRITER_EXCLUSIVITY_SCOPE_MISMATCH"
    WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT = "WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT"
    WRITER_EXCLUSIVITY_LOST = "WRITER_EXCLUSIVITY_LOST"
    PRIOR_WRITE_STATE_UNKNOWN = "PRIOR_WRITE_STATE_UNKNOWN"
    PRIOR_WRITE_UNRESOLVED = "PRIOR_WRITE_UNRESOLVED"
    PRIOR_WRITE_PROVENANCE_INSUFFICIENT = "PRIOR_WRITE_PROVENANCE_INSUFFICIENT"

    PRE_CREATE_HTTP_ERROR = "PRE_CREATE_HTTP_ERROR"
    PRE_CREATE_MALFORMED_RESPONSE = "PRE_CREATE_MALFORMED_RESPONSE"
    PRE_CREATE_NONEMPTY_CURSOR = "PRE_CREATE_NONEMPTY_CURSOR"
    PRE_CREATE_RESTING_ORDER_EXISTS = "PRE_CREATE_RESTING_ORDER_EXISTS"

    CREATE_DEFINITIVELY_FAILED = "CREATE_DEFINITIVELY_FAILED"
    CREATE_RESPONSE_MALFORMED = "CREATE_RESPONSE_MALFORMED"
    CREATE_AMBIGUOUS_UNRESOLVED = "CREATE_AMBIGUOUS_UNRESOLVED"

    RECOVERY_ZERO_MATCH = "RECOVERY_ZERO_MATCH"
    RECOVERY_MULTIPLE_MATCH = "RECOVERY_MULTIPLE_MATCH"
    RECOVERY_MALFORMED_RESPONSE = "RECOVERY_MALFORMED_RESPONSE"
    RECOVERY_NONEMPTY_CURSOR = "RECOVERY_NONEMPTY_CURSOR"

    ORDER_IDENTITY_MISMATCH = "ORDER_IDENTITY_MISMATCH"
    ORDER_UNSUPPORTED_STATUS = "ORDER_UNSUPPORTED_STATUS"
    ORDER_MALFORMED = "AUTHORITATIVE_SCHEMA_DRIFT"

    FILL_MALFORMED = "FILL_MALFORMED"
    DUPLICATE_FILL_CONFLICT = "DUPLICATE_FILL_CONFLICT"
    OVERFILL = "OVERFILL"
    FILL_PRICE_WORSE_THAN_LIMIT = "FILL_PRICE_WORSE_THAN_LIMIT"
    POST_ONLY_TAKER_FILL_CONFLICT = "POST_ONLY_TAKER_FILL_CONFLICT"
    FILLED_PRINCIPAL_EXCEEDS_LIMIT = "FILLED_PRINCIPAL_EXCEEDS_LIMIT"
    FILLS_INCOMPLETE_PAGE_BUDGET = "FILLS_INCOMPLETE_PAGE_BUDGET"
    FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH = "FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH"

    CANCEL_RESPONSE_MALFORMED = "CANCEL_RESPONSE_MALFORMED"
    CANCEL_SEND_DEFINITIVELY_FAILED = "CANCEL_SEND_DEFINITIVELY_FAILED"
    CANCEL_AMBIGUOUS_UNRESOLVED = "CANCEL_AMBIGUOUS_UNRESOLVED"
    CANCEL_QUANTITY_CONSERVATION_MISMATCH = "CANCEL_QUANTITY_CONSERVATION_MISMATCH"
    FINAL_FILL_RECONCILIATION_INCOMPLETE = "FINAL_FILL_RECONCILIATION_INCOMPLETE"

    REQUEST_BUDGET_EXCEEDED = "REQUEST_BUDGET_EXCEEDED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    UNRESOLVED_TERMINAL_STATE = "UNRESOLVED_TERMINAL_STATE"

    # SAME_SCOPE_CORRECTION_03 additions.
    CLIENT_ORDER_ID_MISSING = "CLIENT_ORDER_ID_MISSING"
    CLIENT_ORDER_ID_MALFORMED = "CLIENT_ORDER_ID_MALFORMED"
    RESPONSE_MEDIA_TYPE_INVALID = "RESPONSE_MEDIA_TYPE_INVALID"
    RESPONSE_RETRY_OR_REDIRECT_NONZERO = "RESPONSE_RETRY_OR_REDIRECT_NONZERO"
    RESPONSE_TRANSPORT_EVIDENCE_MISSING = "RESPONSE_TRANSPORT_EVIDENCE_MISSING"
    TRANSPORT_PRE_SEND_FAILURE = "TRANSPORT_PRE_SEND_FAILURE"
    TRANSPORT_RESULT_UNKNOWN = "TRANSPORT_RESULT_UNKNOWN"


def validate_controlling_spec_identity(supplied_sha256: str) -> Optional[LifecycleHaltCode]:
    """Section 9.4 item 1 / Section "CURRENT SPECIFICATION IDENTITY GATE".
    Must be validated before any venue request becomes send-capable."""

    if type(supplied_sha256) is not str:
        return LifecycleHaltCode.SPEC_IDENTITY_MISMATCH
    if supplied_sha256 == ACCEPTED_SPEC_SHA256:
        return None
    if supplied_sha256 in BLOCKED_PREDECESSOR_SPEC_SHA256:
        return LifecycleHaltCode.SPEC_IDENTITY_BLOCKED_PREDECESSOR
    return LifecycleHaltCode.SPEC_IDENTITY_MISMATCH


def validate_operation_binding(name: str, *, raw_bytes: bytes) -> Optional[LifecycleHaltCode]:
    if name not in OPERATION_BINDINGS:
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    expected_length, expected_sha256 = OPERATION_BINDINGS[name]
    if not verify_identity(raw_bytes=raw_bytes, expected_length=expected_length, expected_sha256=expected_sha256):
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    return None


def validate_source_identity(*, raw_bytes: bytes) -> Optional[LifecycleHaltCode]:
    """Direct identity check against the full ~333KB raw Kalshi OpenAPI
    document itself, as distinct from the 843-byte Appendix-C source
    *record* (validated by ``validate_source_record_identity``), which
    only describes that document's provenance and hash as metadata.

    This module never receives the raw OpenAPI document as lifecycle
    input (Revision 06 Section 7.1 does not supply it), so this function
    is not invoked by ``validate_pre_send_gate`` or
    ``execute_demo_one_order_lifecycle``. Section 9.4 item 3 is instead satisfied
    by ``parse_and_validate_source_record``, which validates the exact
    accepted Appendix-C record's own claim about the raw document's
    identity (``raw_openapi_byte_length``/``raw_openapi_sha256`` fields)
    without requiring the raw document itself as input. This function
    remains available for a future caller that does possess the raw
    document and wants to verify it directly against the same identity.
    """

    if not verify_identity(raw_bytes=raw_bytes, expected_length=SOURCE_OPENAPI_BYTES, expected_sha256=SOURCE_OPENAPI_SHA256):
        return LifecycleHaltCode.SOURCE_IDENTITY_MISMATCH
    return None


def validate_source_record_identity(*, raw_bytes: bytes) -> Optional[LifecycleHaltCode]:
    """Section 9.4 item 2: source identity record exact bytes/hash
    (Appendix C)."""

    if not verify_identity(raw_bytes=raw_bytes, expected_length=SOURCE_RECORD_BYTES, expected_sha256=SOURCE_RECORD_SHA256):
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH
    return None


# The exact accepted Appendix-C source identity record field values
# (SAME_SCOPE_CORRECTION_02, Section 9.4 item 3). Every field is required
# and must match exactly; this is intentionally the complete accepted
# record, not just the two raw_openapi_* fields, because the dispatch
# requires "wrong environment/base, wrong source URL/version, or any
# required source-record mismatch" to halt -- not only a raw-identity
# mismatch narrowly construed.
_ACCEPTED_SOURCE_RECORD_FIELDS: Mapping[str, object] = {
    "content_retrieval_classification": "SUCCESS__USER_BROWSER_DIRECT_OFFICIAL_DOWNLOAD_RECEIVED_DURING_ACTIVE_TASK",
    "http_status_observed_by_bruno": None,
    "normalized_source_media_type": "text/yaml",
    "openapi_version": "3.0.0",
    "raw_lf_count": 9563,
    "raw_line_ending_profile": "CRLF",
    "raw_openapi_byte_length": SOURCE_OPENAPI_BYTES,
    "raw_openapi_sha256": SOURCE_OPENAPI_SHA256,
    "retrieval_provenance": "GUSTAVO_DIRECT_DOWNLOAD_FROM_EXACT_OFFICIAL_URL_AND_UPLOAD_TO_ACTIVE_REVISION_03_TASK",
    "retrieved_at_utc": "2026-08-09T13:00:42Z",
    "reviewed_demo_base_path": _TRADE_API_BASE_PATH,
    "reviewed_demo_rest_origin": DEMO_REST_ORIGIN,
    "source_format": "YAML",
    "source_info_title": "Kalshi Trade API Manual Endpoints",
    "source_info_version": "3.27.0",
    "source_schema_revision": 2,
    "source_url": "https://docs.kalshi.com/openapi.yaml",
}


class _DuplicateSourceRecordKeyError(ValueError):
    """Raised internally when the raw source-record JSON contains a
    duplicate object key; never escapes ``parse_and_validate_source_record``
    as a raw exception."""


def _no_duplicate_keys_object_pairs_hook(pairs: list) -> Dict[str, object]:
    seen: Dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateSourceRecordKeyError(key)
        seen[key] = value
    return seen


def parse_and_validate_source_record(*, raw_bytes: bytes) -> Optional[LifecycleHaltCode]:
    """Section 9.4 item 3, made load-bearing without any new raw-file
    input (SAME_SCOPE_CORRECTION_02).

    Revision 06 Section 7.1 supplies ``official_source_identity_record_bytes``
    (Appendix C) -- not the raw ~333KB OpenAPI document itself. This
    function first re-confirms the exact accepted record identity (item 2,
    byte-length/hash), then parses that same record's JSON content and
    requires every field to equal the exact accepted Revision-06 value,
    including ``raw_openapi_byte_length == 333283`` and
    ``raw_openapi_sha256 == SOURCE_OPENAPI_SHA256`` -- the record's own
    *claim* about the raw OpenAPI document it was derived from. This closes
    item 3 using only data already present in an input this module already
    receives and byte-validates; it never fetches or fabricates the raw
    OpenAPI document.

    Malformed JSON, a duplicate object key, a wrong field type, or any
    field value that does not exactly equal the accepted Revision-06
    record content halts before transport call 1.
    """

    identity_halt = validate_source_record_identity(raw_bytes=raw_bytes)
    if identity_halt is not None:
        return identity_halt

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH

    try:
        parsed = json.loads(text, object_pairs_hook=_no_duplicate_keys_object_pairs_hook)
    except (json.JSONDecodeError, _DuplicateSourceRecordKeyError):
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH

    if type(parsed) is not dict:
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH

    if set(parsed.keys()) != set(_ACCEPTED_SOURCE_RECORD_FIELDS.keys()):
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH

    for field_name, expected_value in _ACCEPTED_SOURCE_RECORD_FIELDS.items():
        observed_value = parsed[field_name]
        # Exact type-aware equality: guards against the bool/int numeric
        # equality gotcha (True == 1) and requires the same JSON type,
        # not merely an equal-looking value.
        if type(observed_value) is not type(expected_value):
            return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH
        if observed_value != expected_value:
            return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH

    return None


# ---------------------------------------------------------------------------
# Execution authorization / fee-risk binding (Spec Section 7.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OneOrderFeeRiskBinding:
    """The exact fee-risk relationship: planned principal plus the bound
    maximum fee must never exceed the overall risk ceiling."""

    max_fee_dollars: Decimal

    def __post_init__(self) -> None:
        if type(self.max_fee_dollars) is not Decimal:
            raise TypeError("max_fee_dollars must be a Decimal")

    def is_within_ceiling(self) -> bool:
        return (MAX_FILLED_PRINCIPAL + self.max_fee_dollars) <= MAX_TOTAL_RISK


@dataclass(frozen=True, slots=True)
class OneOrderLifecycleDispatchExpectation:
    """Closed negative-capability declaration required by Section 7.2:
    no production, no WebSocket, no amend, no decrease, no replacement.
    Every field must be exactly ``True`` (the prohibition holds); a
    ``False`` value here means the dispatch is claiming a capability this
    module never implements, which is itself a scope violation."""

    no_production: bool
    no_websocket: bool
    no_amend: bool
    no_decrease: bool
    no_replacement: bool

    def is_closed(self) -> bool:
        return all((self.no_production, self.no_websocket, self.no_amend, self.no_decrease, self.no_replacement))


_FORTY_HEX_PATTERN = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class OneOrderLifecycleExecutionAuthorization:
    """The complete Section 7.2 ``OneOrderLifecycleExecutionAuthorization``
    non-secret metadata -- and *only* Section 7.2 metadata.
    Missing/broader/mismatching authority halts before any request -- this
    is validated in full by ``validate_execution_authorization`` before
    the first transport call.

    ``validated_demo_profile``, ``authorization_envelope`` and
    ``dispatch_expectation`` remain Section-7.1 sibling inputs.
    ``fee_risk_binding`` also remains a Section-7.1 input, while Revision 06
    Section 7.2 separately requires this authorization record to bind the
    exact same non-secret fee-risk value; both copies are validated for exact
    equality before transport call 1.
    """

    gustavo_execution_authorization_id: str
    environment: str
    ticker: str
    subaccount: int
    account_scope_ref: str
    writer_session_id: str
    capabilities: CapabilityEnvelope
    max_created_orders: int
    max_create_send_attempts: int
    max_cancel_send_attempts: int
    max_total_rest_requests: int
    max_lifecycle_duration_ms: int
    accepted_spec_sha256: str
    accepted_implementation_commit: str
    # Exact task-current *source identity record* SHA-256 (the 843-byte
    # Appendix-C record's own hash: SOURCE_RECORD_SHA256). This is
    # deliberately distinct from the raw ~333KB OpenAPI document hash
    # (SOURCE_OPENAPI_SHA256), which the source record references
    # internally as one of its own fields but never equals as a whole.
    source_identity_sha256: str
    operation_binding_sha256: Mapping[str, str]
    fee_risk_binding: OneOrderFeeRiskBinding
    writer_proof_id: str


def _require_usable_validated_demo_profile(profile: object) -> Optional[LifecycleHaltCode]:
    """Local, operation-specific current-value gate for the canonical
    ``ValidatedDemoProfile`` (Section 7.1), mirroring the exact same
    pattern already used by
    ``arb.venues.kalshi.orderbook._require_usable_authenticated_profile``.

    SAME_SCOPE_CORRECTION_03 fix: requires
    ``effective_capability == DEMO_AUTHENTICATED_READ``, not
    ``DEMO_WRITE``. The accepted canonical validator
    (``arb.venues.kalshi.validation.validate``) unconditionally rejects a
    ``DEMO_WRITE`` request with ``WRITE_CAPABILITY_PROHIBITED`` -- it can
    never actually issue a ``DEMO_WRITE`` profile, so requiring one here
    would demand evidence the canonical system can never produce.

    This authenticated-read profile proves only environment, endpoint, and
    credential-*reference* readiness -- it is NOT write authorization.
    Write authority for this lifecycle is established independently and
    exclusively through: (1) ``authorization_envelope.demo_writes ==
    PERMITTED``; (2) ``authorization_envelope.credential_use ==
    PERMITTED``; (3) the seven exact lifecycle-local operation
    capabilities; (4) a valid ``WriterExclusivityPriorWriteProof``; and
    (5) the later exact Gustavo execution authorization. None of those
    are inferred from this profile, and this profile is never treated as
    a substitute for any of them.
    """

    if type(profile) is not ValidatedDemoProfile:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    if profile.environment is not _Environment.KALSHI_DEMO:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    if profile.requested_capability is not _RequestedCapability.DEMO_AUTHENTICATED_READ:
        return LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED
    if profile.effective_capability is not _RequestedCapability.DEMO_AUTHENTICATED_READ:
        return LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED

    if profile.secret_loaded is not False:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    if profile.transport_constructed is not False:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    if profile.network_request_sent is not False:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID

    if type(profile.rest) is not _EndpointComponents:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    rest = profile.rest
    if (
        type(rest.scheme) is not str or rest.scheme != "https"
        or type(rest.host) is not str or rest.host != _DEMO_HOST
        or type(rest.port) is not int or rest.port != _DEMO_PORT
        or type(rest.path) is not str or rest.path != _TRADE_API_BASE_PATH
        or rest.has_user_info is not False or rest.has_query is not False or rest.has_fragment is not False
    ):
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID

    # Not used for any network activity by this REST-only lifecycle;
    # validated only so a mutated/production/malformed WebSocket endpoint
    # is grounds for rejection, exactly like the REST endpoint is (same
    # rationale as arb.venues.kalshi.orderbook).
    if type(profile.websocket) is not _EndpointComponents:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    websocket = profile.websocket
    if (
        type(websocket.scheme) is not str or websocket.scheme != "wss"
        or type(websocket.host) is not str or websocket.host != _DEMO_WEBSOCKET_HOST
        or type(websocket.port) is not int or websocket.port != _DEMO_PORT
        or type(websocket.path) is not str or websocket.path != _DEMO_WEBSOCKET_PATH
        or websocket.has_user_info is not False or websocket.has_query is not False or websocket.has_fragment is not False
    ):
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID

    if type(profile.allowlist_revision) is not str or profile.allowlist_revision != _ACCEPTED_ALLOWLIST_REVISION:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    if (
        type(profile.validation_schema_revision) is not int
        or profile.validation_schema_revision != _ACCEPTED_VALIDATION_SCHEMA_REVISION
    ):
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID

    states = profile.credential_reference_states
    if type(states) is not tuple:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID

    seen_kinds = []
    parsed_states: Dict[_CredentialReferenceKind, _CredentialReferenceState] = {}
    for entry in states:
        if type(entry) is not tuple or len(entry) != 2:
            return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
        kind, state = entry
        if type(kind) is not _CredentialReferenceKind or type(state) is not _CredentialReferenceState:
            return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
        if kind in seen_kinds:
            return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
        seen_kinds.append(kind)
        parsed_states[kind] = state

    accepted_set = set(_ACCEPTED_CREDENTIAL_REFERENCE_KINDS)
    seen_set = set(seen_kinds)
    if seen_set != accepted_set:
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID

    for kind in _ACCEPTED_CREDENTIAL_REFERENCE_KINDS:
        if parsed_states[kind] is not _CredentialReferenceState.CONFIGURED:
            return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID

    return None


def _require_usable_authorization_envelope(envelope: object) -> Optional[LifecycleHaltCode]:
    """Consumption-boundary gate for the canonical
    ``TaskAuthorizationCapabilityEnvelope`` (Section 7.1), mirroring the
    exact same pattern already used by
    ``arb.venues.kalshi.orderbook.require_usable_authenticated_order_book_plan``.
    This lifecycle requires ``demo_writes`` PERMITTED (unlike the
    read-only orderbook operation, which prohibits it), because it issues
    Create/Cancel writes.
    """

    try:
        _require_usable_capability_envelope(envelope)
    except _CapabilityEnvelopeError:
        return LifecycleHaltCode.CANONICAL_CAPABILITY_ENVELOPE_INVALID
    except Exception:
        return LifecycleHaltCode.CANONICAL_CAPABILITY_ENVELOPE_INVALID

    for required_field in _REQUIRED_PERMITTED_ENVELOPE_FIELDS:
        if getattr(envelope, required_field).value != "PERMITTED":
            return LifecycleHaltCode.CANONICAL_CAPABILITY_NOT_AUTHORIZED
    for prohibited_field in _REQUIRED_PROHIBITED_ENVELOPE_FIELDS:
        if getattr(envelope, prohibited_field).value != "PROHIBITED":
            return LifecycleHaltCode.CANONICAL_PRODUCTION_OR_FUNDING_CAPABILITY_PRESENT

    return None


def validate_execution_authorization(
    authorization: OneOrderLifecycleExecutionAuthorization,
    *,
    expected_ticker: str,
    expected_fee_risk_binding: Optional[OneOrderFeeRiskBinding] = None,
) -> Optional[LifecycleHaltCode]:
    if type(authorization) is not OneOrderLifecycleExecutionAuthorization:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    for text_field in (
        authorization.gustavo_execution_authorization_id,
        authorization.account_scope_ref,
        authorization.writer_session_id,
        authorization.accepted_implementation_commit,
        authorization.writer_proof_id,
    ):
        if type(text_field) is not str or text_field.strip() == "":
            return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    if authorization.environment != ENVIRONMENT:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if authorization.ticker != expected_ticker:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(authorization.subaccount) is not int or authorization.subaccount != SUBACCOUNT:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    if type(authorization.max_created_orders) is not int or authorization.max_created_orders != 1:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(authorization.max_create_send_attempts) is not int or authorization.max_create_send_attempts != 1:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(authorization.max_cancel_send_attempts) is not int or authorization.max_cancel_send_attempts != 1:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(authorization.max_total_rest_requests) is not int or authorization.max_total_rest_requests != GLOBAL_REQUEST_MAXIMUM:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(authorization.max_lifecycle_duration_ms) is not int or authorization.max_lifecycle_duration_ms != MASTER_DEADLINE_MS:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    if authorization.accepted_spec_sha256 != ACCEPTED_SPEC_SHA256:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(authorization.accepted_implementation_commit) is not str or not _FORTY_HEX_PATTERN.fullmatch(authorization.accepted_implementation_commit.lower()):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    # SAME_SCOPE_CORRECTION_02 fix: Section 7.2 requires the exact
    # *task-current source identity record* SHA-256 (the 843-byte
    # Appendix-C record's own hash) here -- NOT the raw ~333KB OpenAPI
    # document's hash it happens to reference internally. Correction 01
    # incorrectly compared against SOURCE_OPENAPI_SHA256; these are two
    # distinct identities and must never be interchangeable.
    if authorization.source_identity_sha256 != SOURCE_RECORD_SHA256:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    if set(authorization.operation_binding_sha256.keys()) != set(OPERATION_BINDINGS.keys()):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    for name, expected_sha in OPERATION_BINDINGS.items():
        if authorization.operation_binding_sha256.get(name) != expected_sha[1]:
            return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    if type(authorization.fee_risk_binding) is not OneOrderFeeRiskBinding:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(authorization.fee_risk_binding.max_fee_dollars) is not Decimal:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if not authorization.fee_risk_binding.is_within_ceiling():
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if expected_fee_risk_binding is not None:
        if type(expected_fee_risk_binding) is not OneOrderFeeRiskBinding:
            return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
        if authorization.fee_risk_binding.max_fee_dollars != expected_fee_risk_binding.max_fee_dollars:
            return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    if type(authorization.capabilities) is not CapabilityEnvelope:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    return None


def validate_lifecycle_input_fields(
    *,
    validated_demo_profile: object,
    authorization_envelope: object,
    fee_risk_binding: object,
    dispatch_expectation: object,
) -> Optional[LifecycleHaltCode]:
    """Validates the four Section 7.1 ``OneOrderLifecycleInput`` fields
    that are siblings of ``lifecycle_authorization``, not members of it
    (SAME_SCOPE_CORRECTION_03 fix -- see
    ``OneOrderLifecycleExecutionAuthorization``'s docstring). This is a
    second, broader gate independent of the seven local operation
    capabilities; neither replaces the other.
    """

    profile_halt = _require_usable_validated_demo_profile(validated_demo_profile)
    if profile_halt is not None:
        return profile_halt

    envelope_halt = _require_usable_authorization_envelope(authorization_envelope)
    if envelope_halt is not None:
        return envelope_halt

    if type(fee_risk_binding) is not OneOrderFeeRiskBinding:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if not fee_risk_binding.is_within_ceiling():
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    if type(dispatch_expectation) is not OneOrderLifecycleDispatchExpectation:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if not dispatch_expectation.is_closed():
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID

    return None


def validate_pre_send_gate(
    *,
    controlling_spec_sha256: str,
    source_record_bytes: bytes,
    operation_binding_bytes: Mapping[str, bytes],
    authorization: OneOrderLifecycleExecutionAuthorization,
    writer_proof: "WriterExclusivityPriorWriteProof",
    validated_demo_profile: object,
    authorization_envelope: object,
    fee_risk_binding: object,
    dispatch_expectation: object,
    client_order_id: object,
    expected_ticker: str,
    expected_writer_identity: str,
    executor_entry_utc: str,
) -> Optional[LifecycleHaltCode]:
    """Section 9.4's complete source/binding validation gate plus
    Section 7.2's execution-authorization gate plus the Section 7.1
    profile/envelope/fee-risk/dispatch-expectation fields plus the writer
    proof plus the frozen ``client_order_id``, all evaluated before
    transport call count 1. Returns the first failing check in the order
    Section 9.4 lists them, followed by the remaining Section 7.1 checks.

    Item 3 ("fresh raw OpenAPI hash identity expected by the accepted
    spec") is satisfied by ``parse_and_validate_source_record``, which
    validates the exact accepted Appendix-C record's *content* -- not by
    fetching or fabricating the raw ~333KB OpenAPI document, which
    Revision 06 Section 7.1 never supplies as lifecycle input in the
    first place. Items 1, 2, 3, 4, 5, and 6 are all fully wired below.
    """

    halt = validate_controlling_spec_identity(controlling_spec_sha256)
    if halt is not None:
        return halt

    halt = parse_and_validate_source_record(raw_bytes=source_record_bytes)
    if halt is not None:
        return halt

    if set(operation_binding_bytes.keys()) != set(OPERATION_BINDINGS.keys()):
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    for name, raw in operation_binding_bytes.items():
        halt = validate_operation_binding(name, raw_bytes=raw)
        if halt is not None:
            return halt
    halt = validate_operation_binding_semantics(operation_binding_bytes)
    if halt is not None:
        return halt

    halt = validate_execution_authorization(authorization, expected_ticker=expected_ticker, expected_fee_risk_binding=fee_risk_binding)
    if halt is not None:
        return halt

    # SAME_SCOPE_CORRECTION_03: these four Section 7.1 Input fields are
    # siblings of `authorization` (Section 7.2), not members of it.
    halt = validate_lifecycle_input_fields(
        validated_demo_profile=validated_demo_profile,
        authorization_envelope=authorization_envelope,
        fee_risk_binding=fee_risk_binding,
        dispatch_expectation=dispatch_expectation,
    )
    if halt is not None:
        return halt

    # SAME_SCOPE_CORRECTION_03, point 4: client_order_id is a required,
    # immutable Section 7.1 input, frozen before pre-create can become
    # send-capable.
    if client_order_id is None or client_order_id == "":
        return LifecycleHaltCode.CLIENT_ORDER_ID_MISSING
    if not is_valid_lowercase_uuid4(client_order_id):
        return LifecycleHaltCode.CLIENT_ORDER_ID_MALFORMED

    halt = validate_writer_proof(
        writer_proof,
        expected_ticker=expected_ticker,
        expected_writer_identity=expected_writer_identity,
        expected_lifecycle_execution_authorization_id=authorization.gustavo_execution_authorization_id,
        executor_entry_utc=executor_entry_utc,
    )
    if halt is not None:
        return halt

    if writer_proof.proof_id != authorization.writer_proof_id:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH

    return None


# ---------------------------------------------------------------------------
# WriterExclusivityPriorWriteProof (Spec Section 9.5, Appendix F)
# ---------------------------------------------------------------------------

PROOF_SCHEMA_REVISION = 1
PROOF_MODE_FIRST_ACCEPTED_DEMO_WRITE = "FIRST_ACCEPTED_DEMO_WRITE_V1"
REQUIRED_PROTECTED_WRITE_OPERATIONS: FrozenSet[str] = frozenset({"CREATE", "AMEND", "DECREASE", "CANCEL"})

_RFC3339_UTC_Z_PATTERN = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?Z"
)


@dataclass(frozen=True, order=True, slots=True)
class _Rfc3339Instant:
    second: datetime
    fractional_second: Decimal


def _parse_rfc3339_utc_z(value: object) -> Optional[_Rfc3339Instant]:
    """Parse exact RFC3339 UTC-Z text without truncating fractional digits.

    Chronological comparison remains exact even when two instants differ only
    after the sixth fractional digit.  The integral second is represented by a
    UTC ``datetime`` and the fractional second by an arbitrary-precision
    ``Decimal`` constructed only after ASCII lexical validation.
    """

    if type(value) is not str:
        return None
    match = _RFC3339_UTC_Z_PATTERN.fullmatch(value)
    if match is None:
        return None
    try:
        second = datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
            int(match.group(4)), int(match.group(5)), int(match.group(6)),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    fractional_group = match.group(7)
    fraction = Decimal(f"0{fractional_group}") if fractional_group is not None else Decimal("0")
    return _Rfc3339Instant(second=second, fractional_second=fraction)


def is_rfc3339_utc_z(value: object) -> bool:
    """A conservative RFC3339 UTC (``Z``-suffixed) timestamp check: exact
    ``str`` type, fully anchored pattern, and a real calendar date/time."""

    return _parse_rfc3339_utc_z(value) is not None


class WriterExclusivityFailureCode(enum.StrEnum):
    """Section 9.5.8 exact minimum failure code set, re-exported here for
    convenience; these are also members of ``LifecycleHaltCode``."""

    NOT_ESTABLISHED = LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED.value
    SCOPE_MISMATCH = LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH.value
    NOT_ACTIVE_BEFORE_PREFLIGHT = LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT.value
    LOST = LifecycleHaltCode.WRITER_EXCLUSIVITY_LOST.value
    PRIOR_WRITE_UNKNOWN = LifecycleHaltCode.PRIOR_WRITE_STATE_UNKNOWN.value
    PRIOR_WRITE_UNRESOLVED = LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED.value
    PRIOR_WRITE_PROVENANCE_INSUFFICIENT = LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT.value


@dataclass(frozen=True, slots=True)
class WriterExclusivityPriorWriteProof:
    """The complete Revision-06 Appendix F.1 writer-exclusivity /
    prior-write proof. This module never constructs a "default" or
    "self-issued" instance of this class anywhere in its own logic --
    every instance this module consumes must be supplied by the caller.
    ``validate_writer_proof`` is the single place this module decides
    whether a supplied proof is usable; it never mutates or "repairs" a
    proof.
    """

    proof_schema_revision: int
    proof_id: str
    proof_mode: str
    lifecycle_execution_authorization_id: str
    venue: str
    environment: str
    account_scope_ref: str
    credential_environment_ref: str
    # SAME_SCOPE_CORRECTION_03: Appendix F.1 shows this field as an exact
    # JSON list ["KALSHI_DEMO_API_KEY_ID","KALSHI_DEMO_PRIVATE_KEY_PEM"];
    # unlike permitted_writer_identities/protected_write_operations, the
    # spec gives no "tuple/list" or "set/list" alternative for this field,
    # so exact list is the only accepted container.
    credential_source_names: List[str]
    subaccount: int
    ticker: str
    writer_session_id: str
    permitted_writer_count: int
    # Appendix F.1: "exact one-element tuple/list [writer_session_id]" --
    # both forms are accepted.
    permitted_writer_identities: Union[Tuple[str, ...], List[str]]
    # Appendix F.1: "exact set/list [...]" -- both forms are accepted.
    protected_write_operations: Union[Set[str], List[str]]
    valid_from_utc: str
    valid_until_utc: Optional[str]
    release_state: str
    release_condition: str
    continuity_state: str
    prior_write_state: str
    prior_unresolved_write_count: int
    # Appendix F.1: "list[str], empty for actual first-write stage" --
    # exact list only.
    prior_write_execution_ids: List[str]
    # Appendix F.1: "exact empty list" -- exact list only.
    unclosed_prior_write_execution_ids: List[str]
    prior_write_provenance_mode: str
    prior_write_provenance_source: str
    canonical_state_commit: str
    canonical_state_label: str
    issuer_role: str
    issuer_validation_result: str


_REQUIRED_CREDENTIAL_SOURCE_NAMES: List[str] = ["KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"]


def validate_writer_proof(
    proof: WriterExclusivityPriorWriteProof,
    *,
    expected_ticker: str,
    expected_writer_identity: str,
    expected_lifecycle_execution_authorization_id: str,
    executor_entry_utc: str,
) -> Optional[LifecycleHaltCode]:
    """Validates every closed field of a supplied writer-exclusivity /
    prior-write proof against the exact Appendix F.1 contract. Credential
    possession alone (a non-empty ``credential_source_names``) is never
    sufficient by itself -- every other field below must independently
    pass. A zero-order venue snapshot is a *separate* precondition (see
    ``validate_pre_create_response``) and is never accepted here as a
    substitute for any of these checks.
    """

    if type(proof) is not WriterExclusivityPriorWriteProof:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    # Exact built-in types; bool cannot satisfy integer (bool is an int
    # subclass in Python, so `type(x) is int` correctly excludes it).
    if type(proof.proof_schema_revision) is not int or proof.proof_schema_revision != PROOF_SCHEMA_REVISION:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    if proof.proof_mode != PROOF_MODE_FIRST_ACCEPTED_DEMO_WRITE:
        return LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT

    for text_field in (
        proof.proof_id,
        proof.lifecycle_execution_authorization_id,
        proof.account_scope_ref,
        proof.writer_session_id,
        proof.prior_write_provenance_source,
        proof.canonical_state_label,
    ):
        if type(text_field) is not str or text_field.strip() == "":
            return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    if proof.lifecycle_execution_authorization_id != expected_lifecycle_execution_authorization_id:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH

    if proof.venue != VENUE:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH
    if proof.environment != ENVIRONMENT:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH
    if proof.credential_environment_ref != ENVIRONMENT:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH

    if type(proof.credential_source_names) is not list or proof.credential_source_names != _REQUIRED_CREDENTIAL_SOURCE_NAMES:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    if type(proof.subaccount) is not int or proof.subaccount != SUBACCOUNT:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH

    if proof.ticker != expected_ticker:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH

    if type(proof.permitted_writer_count) is not int or proof.permitted_writer_count != 1:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    # SAME_SCOPE_CORRECTION_03: Appendix F.1 accepts either a tuple or a
    # list here ("exact one-element tuple/list"); a set/frozenset is not
    # one of the accepted forms (order/exact single-element identity
    # matters), so it is deliberately excluded.
    if (
        type(proof.permitted_writer_identities) not in (tuple, list)
        or len(proof.permitted_writer_identities) != 1
        or proof.permitted_writer_identities[0] != proof.writer_session_id
    ):
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    if proof.writer_session_id != expected_writer_identity:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH

    # Appendix F.1 external input accepts exactly built-in set or list.
    # frozenset is reserved for the planner's internal immutable snapshot.
    protected_ops = proof.protected_write_operations
    if type(protected_ops) is set:
        protected_ops_set = protected_ops
    elif type(protected_ops) is list:
        if len(protected_ops) != len(set(protected_ops)):
            return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED
        protected_ops_set = set(protected_ops)
    else:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED
    if protected_ops_set != REQUIRED_PROTECTED_WRITE_OPERATIONS:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    parsed_valid_from = _parse_rfc3339_utc_z(proof.valid_from_utc)
    if parsed_valid_from is None:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED
    parsed_executor_entry = _parse_rfc3339_utc_z(executor_entry_utc)
    if parsed_executor_entry is None:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED
    if parsed_valid_from > parsed_executor_entry:
        # SAME_SCOPE_CORRECTION_02 fix: compared chronologically via
        # timezone-aware datetime objects, not as raw strings. A raw
        # string comparison gets this backwards whenever the two
        # timestamps have different fractional-second precision --
        # ASCII '.' (0x2E) sorts before 'Z' (0x5A), so
        # "12:00:00.1Z" < "12:00:00Z" lexically even though
        # 12:00:00.1Z is chronologically *later*.
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT

    if proof.valid_until_utc is not None:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    if proof.release_state != "UNRELEASED":
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_LOST

    if proof.release_condition != "NO_WRITE_SENT_TERMINAL_OR_TERMINAL_AUTHORITATIVE_RECONCILIATION":
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED

    if proof.continuity_state != "HELD":
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_LOST

    if proof.prior_write_state == "UNKNOWN":
        return LifecycleHaltCode.PRIOR_WRITE_STATE_UNKNOWN
    if proof.prior_write_state != "NO_UNRESOLVED_SAME_SCOPE_WRITE":
        return LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED

    if type(proof.prior_unresolved_write_count) is not int or proof.prior_unresolved_write_count != 0:
        return LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED

    # SAME_SCOPE_CORRECTION_03: Appendix F.1 specifies "exact empty
    # list" for this field -- list only, not tuple.
    if type(proof.unclosed_prior_write_execution_ids) is not list or len(proof.unclosed_prior_write_execution_ids) != 0:
        return LifecycleHaltCode.PRIOR_WRITE_UNRESOLVED

    # By this point proof_mode is guaranteed to be
    # FIRST_ACCEPTED_DEMO_WRITE_V1 (checked earlier in this function).
    # Section 9.5.4: "For the actual first write execution,
    # prior_write_execution_ids is expected to be empty." A non-empty
    # collection in first-write mode is a provenance defect, not merely
    # a type defect. SAME_SCOPE_CORRECTION_03: Appendix F.1 specifies
    # "list[str]" for this field -- list only, not tuple.
    if type(proof.prior_write_execution_ids) is not list or len(proof.prior_write_execution_ids) != 0:
        return LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT

    if proof.prior_write_provenance_mode != "PROJECT_AUTHORIZATION_AND_ACCEPTED_EXECUTION_EVIDENCE":
        return LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT

    if type(proof.canonical_state_commit) is not str or not _FORTY_HEX_PATTERN.fullmatch(proof.canonical_state_commit.lower()):
        return LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT

    if proof.issuer_role != "GUSTAVO_EXECUTION_DISPATCH":
        return LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT
    if proof.issuer_validation_result != "PASS":
        return LifecycleHaltCode.PRIOR_WRITE_PROVENANCE_INSUFFICIENT

    return None


# ---------------------------------------------------------------------------
# Signing contract (offline construction only; no real signing/network here)
# ---------------------------------------------------------------------------

SIGNING_PROFILE = "KALSHI_RSA_PSS_SHA256_MGF1_SALT32_V1"
_TIMESTAMP_MS_PATTERN = re.compile(r"[0-9]+")
_SIGNABLE_METHODS: FrozenSet[str] = frozenset({"GET", "POST", "DELETE"})

# SAME_SCOPE_CORRECTION_03, point 8: the exact fixed method + path
def timestamp_ms_text_is_canonical(value: object) -> bool:
    """Canonical ASCII decimal only: no sign, no decimal point, no
    leading/trailing whitespace, no non-ASCII digit forms."""

    return type(value) is str and _TIMESTAMP_MS_PATTERN.fullmatch(value) is not None


def build_signing_message(*, timestamp_ms_text: str, method: str, full_path: str) -> bytes:
    """message = UTF8(timestamp_ms_text + UPPERCASE_METHOD + full_path).

    ``full_path`` must include ``/trade-api/v2`` and must never contain a
    query string, host, or body content. This is an internal building
    block; the only public signing entry point is
    ``sign_lifecycle_request``, which additionally validates the request
    against the exact lifecycle contract before ever calling this.
    """

    if not timestamp_ms_text_is_canonical(timestamp_ms_text):
        raise ValueError("timestamp_ms_text must be canonical ASCII decimal digits")
    if type(method) is not str:
        raise ValueError("method must be a str")
    upper_method = method.upper()
    if upper_method not in _SIGNABLE_METHODS:
        raise ValueError(f"unsupported method for signing: {method!r}")
    if type(full_path) is not str or "?" in full_path:
        raise ValueError("full_path must be a str and must not contain a query string")
    if not full_path.startswith(_TRADE_API_BASE_PATH):
        raise ValueError(f"full_path must include {_TRADE_API_BASE_PATH}")
    return (timestamp_ms_text + upper_method + full_path).encode("utf-8")


def _validate_request_against_lifecycle_signing_contract(request: "PreparedRequest") -> None:
    """Rejects an unknown operation, a method/path mismatch against that
    operation's exact fixed contract, or a path containing a query
    string. Never inspects ``request.query``/``request.body`` for
    inclusion in the signed material -- those are never part of what is
    signed."""

    if type(request.operation) is not LifecycleOperation or request.operation not in _LIFECYCLE_SIGNING_CONTRACT:
        raise ValueError("not one of the six authorized lifecycle operations")

    expected_method, path_prefix = _LIFECYCLE_SIGNING_CONTRACT[request.operation]

    if type(request.method) is not str or request.method != expected_method:
        raise ValueError("method does not match this operation's exact fixed contract")

    if type(request.path) is not str or "?" in request.path:
        raise ValueError("path must not contain a query string")

    if request.operation in (LifecycleOperation.EXACT_ORDER, LifecycleOperation.CANCEL):
        if not request.path.startswith(path_prefix):
            raise ValueError("path does not match this operation's exact fixed prefix")
        remainder = request.path[len(path_prefix):]
        if remainder == "" or "/" in remainder:
            raise ValueError("path must end in exactly one non-empty order_id segment")
    else:
        if request.path != path_prefix:
            raise ValueError("path does not match this operation's exact fixed contract")


def sign_lifecycle_request(
    request: "PreparedRequest",
    private_key: _rsa.RSAPrivateKey,
    *,
    timestamp_ms_text: str,
) -> bytes:
    """The only public signing entry point (SAME_SCOPE_CORRECTION_03,
    point 8). Unlike a generic ``sign_message(private_key, arbitrary_bytes)``
    surface -- which Revision 06 Section 9.1 explicitly prohibits ("no ...
    arbitrary signer is permitted") -- this function only ever signs
    ``timestamp_ms_text + UPPERCASE_METHOD + full_path_without_query`` for
    one of the six authorized lifecycle operations, after validating
    ``request`` against that operation's exact fixed method/path
    contract. It never signs caller-supplied arbitrary bytes, a query
    string, a host, or a body.

    Callers are responsible for supplying the private key; this module
    never loads, generates for production use, or persists one. Offline
    tests use freshly generated, unmistakably synthetic RSA test keys
    only. No secret loading is added by this function.
    """

    if type(request) is not PreparedRequest:
        raise ValueError("request must have exact type PreparedRequest")

    _validate_request_against_lifecycle_signing_contract(request)

    message = build_signing_message(
        timestamp_ms_text=timestamp_ms_text,
        method=request.method,
        full_path=request.path,
    )
    return private_key.sign(
        message,
        _padding.PSS(mgf=_padding.MGF1(_hashes.SHA256()), salt_length=32),
        _hashes.SHA256(),
    )


# ---------------------------------------------------------------------------
# Create order
# ---------------------------------------------------------------------------

def generate_client_order_id() -> str:
    """A frozen lowercase UUID v4. ``uuid.uuid4()``'s default string form
    is already lowercase hexadecimal with hyphens.

    SAME_SCOPE_CORRECTION_03, point 4: this is a convenience helper for an
    *upstream* planner/input-construction step, before
    ``plan_demo_one_order_lifecycle`` is ever called. Once an
    ``OneOrderLifecycleInput`` exists, ``client_order_id`` is a required,
    immutable field -- this function is never called internally by
    ``plan_demo_one_order_lifecycle`` or ``execute_demo_one_order_lifecycle``,
    and no new client_order_id is ever generated after planning begins,
    including during ambiguous-create recovery (which reuses the exact
    frozen ID)."""

    return str(uuid.uuid4())


_LOWERCASE_UUID4_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


def is_valid_lowercase_uuid4(value: object) -> bool:
    """Exact ``str`` type, fully anchored lowercase RFC 4122 version-4
    UUID textual form (version nibble ``4``, variant nibble one of
    ``8``/``9``/``a``/``b``). Uppercase hex, mixed case, braces, and any
    other UUID version are all rejected."""

    return type(value) is str and _LOWERCASE_UUID4_PATTERN.fullmatch(value) is not None


def compute_expiration_time(body_freeze_epoch_seconds: float) -> int:
    """``expiration_time = floor(body_freeze_epoch_seconds) + 45``."""

    return math.floor(body_freeze_epoch_seconds) + EXPIRATION_OFFSET_SECONDS


CREATE_ORDER_ALLOWED_FIELDS: FrozenSet[str] = frozenset({
    "ticker",
    "client_order_id",
    "side",
    "count",
    "price",
    "time_in_force",
    "self_trade_prevention_type",
    "expiration_time",
    "post_only",
    "cancel_order_on_pause",
    "reduce_only",
    "subaccount",
    "exchange_index",
})


def build_create_order_body(*, ticker: str, client_order_id: str, expiration_time: int) -> Dict[str, object]:
    """The exact closed Create V2 request body. ``order_group_id`` is
    always omitted. No other field beyond ``CREATE_ORDER_ALLOWED_FIELDS``
    is ever included."""

    body: Dict[str, object] = {
        "ticker": ticker,
        "client_order_id": client_order_id,
        "side": SIDE,
        "count": "1.00",
        "price": "0.0100",
        "time_in_force": TIME_IN_FORCE,
        "self_trade_prevention_type": SELF_TRADE_PREVENTION_TYPE,
        "expiration_time": expiration_time,
        "post_only": POST_ONLY,
        "cancel_order_on_pause": CANCEL_ORDER_ON_PAUSE,
        "reduce_only": REDUCE_ONLY,
        "subaccount": SUBACCOUNT,
        "exchange_index": EXCHANGE_INDEX,
    }
    assert set(body.keys()) == CREATE_ORDER_ALLOWED_FIELDS
    assert "order_group_id" not in body
    return body


def validate_create_order_body(body: Mapping[str, object]) -> bool:
    """Returns True only if ``body`` has exactly the allowed key set with
    exactly the fixed closed values (ticker and client_order_id vary per
    lifecycle instance and are not otherwise constrained here)."""

    if set(body.keys()) != CREATE_ORDER_ALLOWED_FIELDS:
        return False
    if "order_group_id" in body:
        return False
    if body.get("side") != SIDE:
        return False
    if body.get("count") != "1.00":
        return False
    if body.get("price") != "0.0100":
        return False
    if body.get("time_in_force") != TIME_IN_FORCE:
        return False
    if body.get("self_trade_prevention_type") != SELF_TRADE_PREVENTION_TYPE:
        return False
    if body.get("post_only") is not True:
        return False
    if body.get("cancel_order_on_pause") is not True:
        return False
    if body.get("reduce_only") is not False:
        return False
    if body.get("subaccount") != SUBACCOUNT:
        return False
    if body.get("exchange_index") != EXCHANGE_INDEX:
        return False
    if type(body.get("ticker")) is not str or body.get("ticker") == "":
        return False
    if type(body.get("client_order_id")) is not str or body.get("client_order_id") == "":
        return False
    if type(body.get("expiration_time")) is not int:
        return False
    return True


# ---------------------------------------------------------------------------
# Pre-create venue truth / ambiguous-create recovery
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GetOrdersResponse:
    """A structurally complete parsed ``GetOrdersResponse``."""

    http_status: int
    cursor: str
    orders: Tuple[Mapping[str, object], ...]


def _parse_get_orders_response(
    raw: "RawHttpResponse", *, malformed_code: LifecycleHaltCode
) -> Tuple[Optional[GetOrdersResponse], Optional[LifecycleHaltCode]]:
    if not isinstance(raw.body, Mapping):
        return None, malformed_code
    if "orders" not in raw.body or "cursor" not in raw.body:
        return None, malformed_code
    orders = raw.body["orders"]
    cursor = raw.body["cursor"]
    if type(orders) is not list or type(cursor) is not str:
        return None, malformed_code
    if not all(isinstance(order, Mapping) for order in orders):
        return None, malformed_code
    return GetOrdersResponse(raw.status, cursor, tuple(orders)), None


def build_pre_create_query(*, ticker: str) -> Dict[str, object]:
    return {
        "ticker": ticker,
        "status": "resting",
        "limit": 1000,
        "subaccount": SUBACCOUNT,
    }


def validate_pre_create_response(response: GetOrdersResponse, *, ticker: str) -> Optional[LifecycleHaltCode]:
    """Requires HTTP 200, ``cursor == ""``, and zero matching resting
    orders. Only then may state become ``PRE_CREATE_ACTIVE_SCOPE_CLEAR``.
    This function never adopts, cancels, amends, decreases, or otherwise
    treats a discovered order as actionable -- any non-empty result is an
    unconditional halt.
    """

    if response.http_status != 200:
        return LifecycleHaltCode.PRE_CREATE_HTTP_ERROR
    if type(response.cursor) is not str:
        return LifecycleHaltCode.PRE_CREATE_MALFORMED_RESPONSE
    if response.cursor != "":
        return LifecycleHaltCode.PRE_CREATE_NONEMPTY_CURSOR
    if type(response.orders) is not tuple:
        return LifecycleHaltCode.PRE_CREATE_MALFORMED_RESPONSE
    if len(response.orders) != 0:
        return LifecycleHaltCode.PRE_CREATE_RESTING_ORDER_EXISTS
    return None


def build_recovery_query(*, ticker: str) -> Dict[str, object]:
    return {
        "ticker": ticker,
        "limit": 1000,
        "subaccount": SUBACCOUNT,
    }


def validate_recovery_response(
    response: GetOrdersResponse,
    *,
    client_order_id: str,
    ticker: str,
) -> Tuple[Optional[Mapping[str, object]], Optional[LifecycleHaltCode]]:
    """Exact ambiguous-create recovery contract: HTTP 200, ``cursor == ""``,
    and exactly one local match by the frozen ``client_order_id``, with
    exact ticker, direction, type ``limit``, initial quantity ``1.00``,
    price ``0.0100``, and a supported status."""

    if response.http_status != 200:
        return None, LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE
    if type(response.cursor) is not str:
        return None, LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE
    if response.cursor != "":
        return None, LifecycleHaltCode.RECOVERY_NONEMPTY_CURSOR
    if type(response.orders) is not tuple:
        return None, LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE

    matches = [o for o in response.orders if o.get("client_order_id") == client_order_id]
    if len(matches) == 0:
        return None, LifecycleHaltCode.RECOVERY_ZERO_MATCH
    if len(matches) > 1:
        return None, LifecycleHaltCode.RECOVERY_MULTIPLE_MATCH

    order = matches[0]
    order_halt = validate_order_record(
        order,
        bound_order_id=order.get("order_id") if type(order.get("order_id")) is str else "",
        client_order_id=client_order_id,
        ticker=ticker,
    )
    if order_halt is not None:
        return None, LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE

    return order, None


# ---------------------------------------------------------------------------
# Authoritative Order / Fill schema (Spec Appendix E)
# ---------------------------------------------------------------------------

ORDER_REQUIRED_FIELDS: Tuple[str, ...] = (
    "order_id",
    "user_id",
    "client_order_id",
    "ticker",
    "outcome_side",
    "book_side",
    "type",
    "status",
    "yes_price_dollars",
    "no_price_dollars",
    "fill_count_fp",
    "remaining_count_fp",
    "initial_count_fp",
    "taker_fees_dollars",
    "maker_fees_dollars",
    "taker_fill_cost_dollars",
    "maker_fill_cost_dollars",
)

ORDER_FIXED_POINT_COUNT_FIELDS: Tuple[str, ...] = (
    "fill_count_fp", "remaining_count_fp", "initial_count_fp",
)
ORDER_FIXED_POINT_DOLLAR_FIELDS: Tuple[str, ...] = (
    "yes_price_dollars", "no_price_dollars", "taker_fees_dollars",
    "maker_fees_dollars", "taker_fill_cost_dollars", "maker_fill_cost_dollars",
)
ORDER_FIXED_POINT_STRING_FIELDS: Tuple[str, ...] = (
    *ORDER_FIXED_POINT_DOLLAR_FIELDS, *ORDER_FIXED_POINT_COUNT_FIELDS,
)


_FIXED_POINT_COUNT_RESPONSE_PATTERN = re.compile(r"[0-9]+\.[0-9]{2}")
_FIXED_POINT_DOLLARS_RESPONSE_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]{1,6})?")


def _parse_fixed_point_count(value: object) -> Optional[Decimal]:
    """Parse authoritative FixedPointCount response text.

    Revision 06 binds response representation to an unsigned ASCII decimal
    string with exactly two fractional digits.  Lexical validation happens
    before Decimal construction, rejecting exponent notation, signs,
    whitespace, NaN/Infinity, separators, non-string JSON values and scale
    violations.
    """

    if type(value) is not str or _FIXED_POINT_COUNT_RESPONSE_PATTERN.fullmatch(value) is None:
        return None
    return Decimal(value)


def _parse_fixed_point_dollars(value: object) -> Optional[Decimal]:
    """Parse authoritative FixedPointDollars response text.

    Values are finite unsigned ASCII decimal strings with at most six
    fractional digits. No coercion from JSON numbers is permitted.
    """

    if type(value) is not str or _FIXED_POINT_DOLLARS_RESPONSE_PATTERN.fullmatch(value) is None:
        return None
    return Decimal(value)


def validate_order_record(
    order: Mapping[str, object],
    *,
    bound_order_id: str,
    client_order_id: str,
    ticker: str,
) -> Optional[LifecycleHaltCode]:
    """The complete Appendix E.1 authoritative Order validation: every
    required field present, every FixedPoint field an exact string
    (never a numeric JSON value), and the quantity-conservation
    invariants ``0 <= fill_count_fp``, ``0 <= remaining_count_fp``,
    ``fill_count_fp + remaining_count_fp <= 1.00``, and
    ``initial_count_fp == 1.00`` all enforced.
    """

    if not isinstance(order, Mapping):
        return LifecycleHaltCode.ORDER_MALFORMED

    for required_field in ORDER_REQUIRED_FIELDS:
        if required_field not in order:
            return LifecycleHaltCode.ORDER_MALFORMED

    if type(order.get("order_id")) is not str or order.get("order_id") == "":
        return LifecycleHaltCode.ORDER_MALFORMED
    if type(order.get("user_id")) is not str or order.get("user_id") == "":
        return LifecycleHaltCode.ORDER_MALFORMED
    if type(order.get("client_order_id")) is not str:
        return LifecycleHaltCode.ORDER_MALFORMED
    if type(order.get("ticker")) is not str:
        return LifecycleHaltCode.ORDER_MALFORMED
    if type(order.get("type")) is not str:
        return LifecycleHaltCode.ORDER_MALFORMED
    if type(order.get("status")) is not str:
        return LifecycleHaltCode.ORDER_MALFORMED

    parsed: Dict[str, Decimal] = {}
    for fp_field in ORDER_FIXED_POINT_COUNT_FIELDS:
        parsed_value = _parse_fixed_point_count(order.get(fp_field))
        if parsed_value is None:
            return LifecycleHaltCode.ORDER_MALFORMED
        parsed[fp_field] = parsed_value
    for fp_field in ORDER_FIXED_POINT_DOLLAR_FIELDS:
        parsed_value = _parse_fixed_point_dollars(order.get(fp_field))
        if parsed_value is None:
            return LifecycleHaltCode.ORDER_MALFORMED
        parsed[fp_field] = parsed_value

    for optional_field in ("subaccount_number", "exchange_index"):
        if optional_field in order and order.get(optional_field) is not None:
            value = order.get(optional_field)
            if type(value) is not int or value != 0:
                return LifecycleHaltCode.ORDER_MALFORMED

    if parsed["fill_count_fp"] < Decimal("0") or parsed["fill_count_fp"] > QUANTITY:
        return LifecycleHaltCode.ORDER_MALFORMED
    if parsed["remaining_count_fp"] < Decimal("0") or parsed["remaining_count_fp"] > QUANTITY:
        return LifecycleHaltCode.ORDER_MALFORMED
    if parsed["fill_count_fp"] + parsed["remaining_count_fp"] > QUANTITY:
        return LifecycleHaltCode.ORDER_MALFORMED
    if parsed["initial_count_fp"] != QUANTITY:
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH

    # Identity checks (never satisfied by legacy `side`/`action`, which
    # this function never reads for direction).
    if order.get("order_id") != bound_order_id:
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH
    if order.get("client_order_id") != client_order_id:
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH
    if order.get("ticker") != ticker:
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH
    if order.get("outcome_side") != "yes":
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH
    if order.get("book_side") != SIDE:
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH
    if order.get("type") != "limit":
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH
    if parsed["yes_price_dollars"] != LIMIT_PRICE:
        return LifecycleHaltCode.ORDER_IDENTITY_MISMATCH

    status = order.get("status")
    if status not in SUPPORTED_ORDER_STATUSES:
        return LifecycleHaltCode.ORDER_UNSUPPORTED_STATUS

    return None


FILL_REQUIRED_FIELDS: Tuple[str, ...] = (
    "fill_id",
    "trade_id",
    "order_id",
    "ticker",
    "market_ticker",
    "outcome_side",
    "book_side",
    "count_fp",
    "yes_price_dollars",
    "no_price_dollars",
    "is_taker",
    "fee_cost",
)

FILL_FIXED_POINT_STRING_FIELDS: Tuple[str, ...] = (
    "count_fp", "yes_price_dollars", "no_price_dollars", "fee_cost",
)


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CanonicalFill:
    fill_id: str
    trade_id: str
    order_id: str
    ticker: str
    market_ticker: str
    outcome_side: str
    book_side: str
    count_fp: Decimal
    yes_price_dollars: Decimal
    no_price_dollars: Decimal
    is_taker: bool
    fee_cost: Decimal
    optional_authoritative_fields: Tuple[Tuple[str, str], ...]


_FILL_OPTIONAL_AUTHORITATIVE_FIELDS: Tuple[str, ...] = (
    "side", "action", "created_time", "subaccount_number", "ts",
)


def _canonicalize_optional_fill_fields(raw_fill: Mapping[str, object]) -> Optional[Tuple[Tuple[str, str], ...]]:
    items: List[Tuple[str, str]] = []
    for name in _FILL_OPTIONAL_AUTHORITATIVE_FIELDS:
        if name not in raw_fill:
            continue
        value = raw_fill[name]
        if name == "subaccount_number" and value is not None:
            if type(value) is not int or type(value) is bool or value != 0:
                return None
        try:
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError):
            return None
        items.append((name, encoded))
    return tuple(items)


def build_fills_query(*, order_id: str, cursor: str) -> Dict[str, object]:
    query: Dict[str, object] = {
        "order_id": order_id,
        "limit": 1000,
        "subaccount": SUBACCOUNT,
    }
    if cursor != "":
        query["cursor"] = cursor
    return query


def _parse_fills_page(raw: "RawHttpResponse") -> Tuple[Optional[List[Mapping[str, object]]], Optional[str], Optional[LifecycleHaltCode]]:
    if raw.status != 200 or not isinstance(raw.body, Mapping):
        return None, None, LifecycleHaltCode.FILL_MALFORMED
    if "fills" not in raw.body or "cursor" not in raw.body:
        return None, None, LifecycleHaltCode.FILL_MALFORMED
    fills = raw.body["fills"]
    cursor = raw.body["cursor"]
    if type(fills) is not list or type(cursor) is not str:
        return None, None, LifecycleHaltCode.FILL_MALFORMED
    if not all(isinstance(fill, Mapping) for fill in fills):
        return None, None, LifecycleHaltCode.FILL_MALFORMED
    return fills, cursor, None


def _parse_exact_order_response(raw: "RawHttpResponse") -> Tuple[Optional[Mapping[str, object]], Optional[LifecycleHaltCode]]:
    if raw.status != 200 or not isinstance(raw.body, Mapping):
        return None, LifecycleHaltCode.ORDER_MALFORMED
    if "order" not in raw.body or not isinstance(raw.body["order"], Mapping):
        return None, LifecycleHaltCode.ORDER_MALFORMED
    return raw.body["order"], None


class FillLedger:
    """Accumulates canonical fills by ``fill_id``, in memory only,
    performing no I/O. Enforces the complete Appendix E.2 authoritative
    Fill schema, idempotent exact-duplicate handling, conflicting-duplicate
    rejection, per-fill price-limit and post-only-taker checks, overfill
    prevention, and the aggregate filled-principal bound -- all with
    ``Decimal`` arithmetic only, and every FixedPoint field accepted only
    as an exact string (never coerced from a numeric JSON value).
    """

    __slots__ = ("_by_id",)

    def __init__(self) -> None:
        self._by_id: Dict[str, CanonicalFill] = {}

    def fills(self) -> Tuple[CanonicalFill, ...]:
        return tuple(self._by_id.values())

    def total_quantity(self) -> Decimal:
        total = Decimal("0")
        for canonical_fill in self._by_id.values():
            total += canonical_fill.count_fp
        return total

    def actual_filled_principal(self) -> Decimal:
        total = Decimal("0")
        for canonical_fill in self._by_id.values():
            total += canonical_fill.count_fp * canonical_fill.yes_price_dollars
        return total

    def ingest(
        self,
        raw_fill: Mapping[str, object],
        *,
        bound_order_id: str,
        ticker: str,
    ) -> Optional[LifecycleHaltCode]:
        if not isinstance(raw_fill, Mapping):
            return LifecycleHaltCode.FILL_MALFORMED

        for required_field in FILL_REQUIRED_FIELDS:
            if required_field not in raw_fill:
                return LifecycleHaltCode.FILL_MALFORMED

        # Parse the complete authoritative identity before comparing a replay.
        # This ensures a same-fill_id replay with *any* changed authoritative
        # content is classified as DUPLICATE_FILL_CONFLICT rather than having
        # the changed field discarded or hidden by a narrower model.
        text_fields = (
            "fill_id", "trade_id", "order_id", "ticker", "market_ticker",
            "outcome_side", "book_side",
        )
        for name in text_fields:
            value = raw_fill[name]
            if type(value) is not str or value == "":
                return LifecycleHaltCode.FILL_MALFORMED
        fill_id = raw_fill["fill_id"]

        count = _parse_fixed_point_count(raw_fill["count_fp"])
        yes_price = _parse_fixed_point_dollars(raw_fill["yes_price_dollars"])
        no_price = _parse_fixed_point_dollars(raw_fill["no_price_dollars"])
        fee_cost = _parse_fixed_point_dollars(raw_fill["fee_cost"])
        if count is None or yes_price is None or no_price is None or fee_cost is None:
            return LifecycleHaltCode.FILL_MALFORMED
        if count <= Decimal("0"):
            return LifecycleHaltCode.FILL_MALFORMED

        is_taker = raw_fill["is_taker"]
        if type(is_taker) is not bool:
            return LifecycleHaltCode.FILL_MALFORMED

        if "subaccount_number" in raw_fill and raw_fill["subaccount_number"] is not None:
            value = raw_fill["subaccount_number"]
            if type(value) is not int or type(value) is bool or value != 0:
                return LifecycleHaltCode.FILL_MALFORMED
        optional_fields = _canonicalize_optional_fill_fields(raw_fill)
        if optional_fields is None:
            return LifecycleHaltCode.FILL_MALFORMED

        candidate = CanonicalFill(
            fill_id=fill_id,
            trade_id=raw_fill["trade_id"],
            order_id=raw_fill["order_id"],
            ticker=raw_fill["ticker"],
            market_ticker=raw_fill["market_ticker"],
            outcome_side=raw_fill["outcome_side"],
            book_side=raw_fill["book_side"],
            count_fp=count,
            yes_price_dollars=yes_price,
            no_price_dollars=no_price,
            is_taker=is_taker,
            fee_cost=fee_cost,
            optional_authoritative_fields=optional_fields,
        )

        existing = self._by_id.get(fill_id)
        if existing is not None:
            if existing == candidate:
                return None
            return LifecycleHaltCode.DUPLICATE_FILL_CONFLICT

        # First occurrence must satisfy every normal lifecycle identity and
        # economic invariant before it becomes canonical.
        if candidate.order_id != bound_order_id:
            return LifecycleHaltCode.FILL_MALFORMED
        if candidate.ticker != ticker or candidate.market_ticker != ticker:
            return LifecycleHaltCode.FILL_MALFORMED
        if candidate.outcome_side != "yes" or candidate.book_side != SIDE:
            return LifecycleHaltCode.FILL_MALFORMED
        if yes_price > LIMIT_PRICE:
            return LifecycleHaltCode.FILL_PRICE_WORSE_THAN_LIMIT
        if is_taker:
            return LifecycleHaltCode.POST_ONLY_TAKER_FILL_CONFLICT
        if self.total_quantity() + count > QUANTITY:
            return LifecycleHaltCode.OVERFILL

        self._by_id[fill_id] = candidate
        if self.actual_filled_principal() > MAX_FILLED_PRINCIPAL:
            return LifecycleHaltCode.FILLED_PRINCIPAL_EXCEEDS_LIMIT
        return None

    def reconcile_against_order(self, order: Mapping[str, object]) -> Optional[LifecycleHaltCode]:
        """After every authoritative reconciliation point, the canonical
        deduplicated fill quantity must reconcile exactly to authoritative
        ``Order.fill_count_fp``."""

        order_fill_count = _parse_fixed_point_count(order.get("fill_count_fp"))
        if order_fill_count is None:
            return LifecycleHaltCode.ORDER_MALFORMED
        if self.total_quantity() != order_fill_count:
            return LifecycleHaltCode.FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH
        return None


# ---------------------------------------------------------------------------
# Create/cancel unknown-result classification (Spec Appendix G)
# ---------------------------------------------------------------------------

class SendOutcome(enum.StrEnum):
    """Closed write-send/result classification required by Correction 04."""

    DEFINITELY_NOT_SENT_PRE_SEND = "DEFINITELY_NOT_SENT_PRE_SEND"
    SEND_MAY_HAVE_BEGUN_UNKNOWN = "SEND_MAY_HAVE_BEGUN_UNKNOWN"
    DEFINITIVE_RESPONSE_AFTER_SEND = "DEFINITIVE_RESPONSE_AFTER_SEND"
    DEFINITIVE_SUCCESS = "DEFINITIVE_SUCCESS"


def classify_create_response(
    raw: "RawHttpResponse", *, expected_client_order_id: Optional[str] = None
) -> Tuple[SendOutcome, Optional[str]]:
    """Validate Create V2's send/result class and complete 201 schema.

    A received rejection is never described as a pre-send failure. A malformed
    or conflicting success response is fail-closed as an unknown-after-send
    result because the request was transmitted but its exact created-order
    identity cannot be trusted.
    """

    disposition = getattr(raw, "send_result_classification", None)
    if disposition is SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
        return disposition, None
    if disposition is SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN:
        return disposition, None
    if disposition is SendOutcome.DEFINITIVE_RESPONSE_AFTER_SEND:
        # Appendix D binds only the successful Create status/schema.  A received
        # non-success response proves transmission, but it does not prove that
        # the write had no side effect.  No HTTP status is promoted to a
        # source-proven no-create result.
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None
    if disposition is not SendOutcome.DEFINITIVE_SUCCESS or raw.status != 201:
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None

    if not isinstance(raw.body, Mapping):
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None
    for required_field in ("order_id", "fill_count", "remaining_count", "ts_ms"):
        if required_field not in raw.body:
            return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None

    order_id = raw.body["order_id"]
    if type(order_id) is not str or order_id == "":
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None
    fill_count = _parse_fixed_point_count(raw.body["fill_count"])
    remaining_count = _parse_fixed_point_count(raw.body["remaining_count"])
    if fill_count is None or remaining_count is None or fill_count + remaining_count != QUANTITY:
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None

    ts_ms = raw.body["ts_ms"]
    if type(ts_ms) is not int or type(ts_ms) is bool:
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None

    if "client_order_id" in raw.body:
        client_order_id = raw.body["client_order_id"]
        if type(client_order_id) is not str:
            return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None
        if expected_client_order_id is not None and client_order_id != expected_client_order_id:
            return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None

    for optional_money in ("average_fill_price", "average_fee_paid"):
        if optional_money in raw.body and _parse_fixed_point_dollars(raw.body[optional_money]) is None:
            return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN, None

    return SendOutcome.DEFINITIVE_SUCCESS, order_id


def classify_cancel_response(
    raw: "RawHttpResponse",
    *,
    expected_order_id: Optional[str] = None,
    expected_client_order_id: Optional[str] = None,
) -> SendOutcome:
    """Validate Cancel V2's send/result class and complete 200 schema."""

    disposition = getattr(raw, "send_result_classification", None)
    if disposition is SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
        return disposition
    if disposition is SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN:
        return disposition
    if disposition is SendOutcome.DEFINITIVE_RESPONSE_AFTER_SEND:
        # Appendix D binds only the successful Cancel status/schema.  A received
        # non-success response proves transmission, but it does not prove that
        # cancellation had no side effect.  No HTTP status is promoted to a
        # source-proven no-cancel result.
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    if disposition is not SendOutcome.DEFINITIVE_SUCCESS or raw.status != 200:
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN

    if not isinstance(raw.body, Mapping):
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    for required_field in ("order_id", "reduced_by", "ts_ms"):
        if required_field not in raw.body:
            return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN

    order_id = raw.body["order_id"]
    if type(order_id) is not str or order_id == "":
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    if expected_order_id is not None and order_id != expected_order_id:
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    if _parse_fixed_point_count(raw.body["reduced_by"]) is None:
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    ts_ms = raw.body["ts_ms"]
    if type(ts_ms) is not int or type(ts_ms) is bool:
        return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    if "client_order_id" in raw.body:
        client_order_id = raw.body["client_order_id"]
        if type(client_order_id) is not str:
            return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
        if expected_client_order_id is not None and client_order_id != expected_client_order_id:
            return SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    return SendOutcome.DEFINITIVE_SUCCESS


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def build_cancel_query() -> Dict[str, object]:
    return {
        "subaccount": SUBACCOUNT,
        "exchange_index": EXCHANGE_INDEX,
    }


def cancel_is_send_capable(
    *,
    bound_order_id: Optional[str],
    latest_status: Optional[str],
    canonical_fill_quantity: Decimal,
    cancel_send_attempt_count: int,
    writer_proof_state_held: bool,
    has_cancel_capability: bool = True,
    deadline_capacity_remaining: bool = True,
) -> bool:
    if bound_order_id is None:
        return False
    if latest_status != "resting":
        return False
    if canonical_fill_quantity >= QUANTITY:
        return False
    if cancel_send_attempt_count != 0:
        return False
    if not writer_proof_state_held:
        return False
    if not has_cancel_capability:
        return False
    if not deadline_capacity_remaining:
        return False
    return True


def check_cancel_conservation(*, final_fill_quantity: Decimal, reduced_by: Decimal) -> Optional[LifecycleHaltCode]:
    """``canonical_final_fill_quantity + cancel_response.reduced_by ==
    Decimal("1.00")`` for a definitive successful cancel ending in
    authoritative status ``canceled``."""

    if final_fill_quantity + reduced_by != QUANTITY:
        return LifecycleHaltCode.CANCEL_QUANTITY_CONSERVATION_MISMATCH
    return None


# ---------------------------------------------------------------------------
# Transport interface and orchestration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """Everything the transport boundary needs to prove the exact
    method/path/query/body contract used for one request, plus the exact
    clipped effective deadline the transport must honor. This is not a
    generic HTTP request abstraction -- ``method``/``path`` are always one
    of the six exact Section 9.2 surfaces; nothing else is constructible
    through this orchestrator."""

    operation: LifecycleOperation
    method: str
    path: str
    query: Mapping[str, object]
    body: Optional[Mapping[str, object]]
    effective_deadline_monotonic: float


@dataclass(frozen=True, slots=True)
class RawHttpResponse:
    """Explicit transport result/evidence. No safety-relevant field defaults.

    ``media_type``, retry/redirect counts, and the send/result classification
    must be supplied by the transport.  Omission is therefore impossible via
    ordinary construction and is independently rejected at consumption in
    case an object is forged/tampered.
    """

    status: int
    body: Mapping[str, object]
    media_type: str
    retry_count: int
    redirect_count: int
    send_result_classification: SendOutcome


class LifecycleTransportPreSendError(Exception):
    """Transport proved failure before the request send boundary."""


class LifecycleTransportUnknownAfterSendError(Exception):
    """Transport cannot prove whether/with what result transmission occurred."""


class LifecycleTransport(Protocol):
    """A single narrow send surface. No network implementation lives here."""

    def send(self, request: PreparedRequest) -> RawHttpResponse: ...


class LifecycleTerminal(enum.StrEnum):
    """SAME_SCOPE_CORRECTION_03: only the three genuine success terminal
    states remain here. A halt is never represented as a
    ``LifecycleTerminal`` value -- see ``OneOrderLifecycleHalt``, a wholly
    separate return type, so a halt can never masquerade as a success
    result."""

    CANCELED = "CANCELED"
    FILLED = "FILLED"
    ALREADY_CANCELED = "ALREADY_CANCELED"


def _build_request(
    operation: LifecycleOperation,
    *,
    method: str,
    path: str,
    query: Mapping[str, object],
    body: Optional[Mapping[str, object]],
    deadline: LifecycleDeadline,
    monotonic_clock: Callable[[], float],
) -> PreparedRequest:
    request_start = monotonic_clock()
    effective_deadline = deadline.effective_request_deadline_monotonic(request_start)
    return PreparedRequest(
        operation=operation,
        method=method,
        path=path,
        query=MappingProxyType(dict(query)),
        body=MappingProxyType(dict(body)) if body is not None else None,
        effective_deadline_monotonic=effective_deadline,
    )


def _validate_response_transport_evidence(raw: object) -> Optional[LifecycleHaltCode]:
    if type(raw) is not RawHttpResponse:
        return LifecycleHaltCode.RESPONSE_TRANSPORT_EVIDENCE_MISSING
    sentinel = object()
    media_type = getattr(raw, "media_type", sentinel)
    retry_count = getattr(raw, "retry_count", sentinel)
    redirect_count = getattr(raw, "redirect_count", sentinel)
    classification = getattr(raw, "send_result_classification", sentinel)
    status = getattr(raw, "status", sentinel)
    body = getattr(raw, "body", sentinel)
    if sentinel in (media_type, retry_count, redirect_count, classification, status, body):
        return LifecycleHaltCode.RESPONSE_TRANSPORT_EVIDENCE_MISSING
    if type(media_type) is not str or media_type != "application/json":
        return LifecycleHaltCode.RESPONSE_MEDIA_TYPE_INVALID
    if type(retry_count) is not int or type(retry_count) is bool or retry_count != 0:
        return LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO
    if type(redirect_count) is not int or type(redirect_count) is bool or redirect_count != 0:
        return LifecycleHaltCode.RESPONSE_RETRY_OR_REDIRECT_NONZERO
    if type(classification) is not SendOutcome:
        return LifecycleHaltCode.RESPONSE_TRANSPORT_EVIDENCE_MISSING
    if type(status) is not int or type(status) is bool:
        return LifecycleHaltCode.RESPONSE_TRANSPORT_EVIDENCE_MISSING
    if not isinstance(body, Mapping):
        return LifecycleHaltCode.RESPONSE_TRANSPORT_EVIDENCE_MISSING
    return None


def _send_and_validate(
    transport: LifecycleTransport,
    request: PreparedRequest,
    *,
    monotonic_clock: Callable[[], float],
) -> Tuple[Optional[RawHttpResponse], Optional[LifecycleHaltCode], SendOutcome]:
    """Send once, classify transport exceptions, and fail closed on evidence
    or deadline violations. No transport exception escapes this boundary."""

    try:
        raw = transport.send(request)
    except LifecycleTransportPreSendError:
        return None, LifecycleHaltCode.TRANSPORT_PRE_SEND_FAILURE, SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND
    except LifecycleTransportUnknownAfterSendError:
        return None, LifecycleHaltCode.TRANSPORT_RESULT_UNKNOWN, SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    except Exception:
        return None, LifecycleHaltCode.TRANSPORT_RESULT_UNKNOWN, SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN

    disposition = getattr(raw, "send_result_classification", SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)
    if type(disposition) is not SendOutcome:
        disposition = SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN
    evidence_halt = _validate_response_transport_evidence(raw)
    if evidence_halt is not None:
        return None, evidence_halt, disposition
    if monotonic_clock() >= request.effective_deadline_monotonic:
        return None, LifecycleHaltCode.DEADLINE_EXCEEDED, disposition
    return raw, None, disposition


def _canonical_secret_safe_value(value: object) -> object:
    if isinstance(value, enum.Enum):
        return value.value
    if type(value) is Decimal:
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _canonical_secret_safe_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if type(value) in (tuple, list, set, frozenset):
        values = list(value)
        if type(value) in (set, frozenset):
            values = sorted(values, key=lambda item: repr(item))
        return [_canonical_secret_safe_value(v) for v in values]
    if hasattr(value, "__dataclass_fields__"):
        return {
            f.name: _canonical_secret_safe_value(getattr(value, f.name))
            for f in dataclass_fields(value)
            if f.name != "secret_safe_evidence_sha256"
        }
    if value is None or type(value) in (str, int, bool, float):
        return value
    raise TypeError("unsupported secret-safe evidence value")


def _secret_safe_evidence_sha256_from_record(record: Mapping[str, object]) -> str:
    canonical = json.dumps(
        _canonical_secret_safe_value(record),
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _recompute_secret_safe_evidence_sha256(evidence: object) -> str:
    if not hasattr(evidence, "__dataclass_fields__"):
        raise TypeError("evidence must be a lifecycle dataclass")
    record = {
        f.name: getattr(evidence, f.name)
        for f in dataclass_fields(evidence)
        if f.name != "secret_safe_evidence_sha256"
    }
    return _secret_safe_evidence_sha256_from_record(record)


# ---------------------------------------------------------------------------
# Section 7.1: OneOrderLifecycleInput
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OneOrderLifecycleInput:
    """The exact, complete Section 7.1 immutable future input. Arbitrary
    caller URLs, methods, query/body changes, side/quantity/price
    changes, retries, proxies, sessions, second tickers, replacement IDs,
    or caller-selected proof semantics are never accepted anywhere in
    this module -- every one of those is fixed by the accepted
    specification, not by this input.

    SAME_SCOPE_CORRECTION_03 fix: ``validated_demo_profile``,
    ``authorization_envelope``, ``fee_risk_binding``, and
    ``dispatch_expectation`` are fields of *this* type, siblings of
    ``lifecycle_authorization``. The fee-risk value is additionally mirrored
    in the execution-authorization data and must match exactly.
    """

    validated_demo_profile: ValidatedDemoProfile
    authorization_envelope: TaskAuthorizationCapabilityEnvelope
    lifecycle_authorization: OneOrderLifecycleExecutionAuthorization
    writer_exclusivity_prior_write_proof: WriterExclusivityPriorWriteProof
    market_ticker: str
    # SAME_SCOPE_CORRECTION_03, point 4: required, immutable, frozen
    # before pre-create can become send-capable. Never generated inside
    # this module -- see generate_client_order_id()'s docstring for the
    # upstream-only convenience helper.
    client_order_id: str
    official_source_identity_record_bytes: bytes
    operation_binding_record_bytes: Mapping[str, bytes]
    fee_risk_binding: OneOrderFeeRiskBinding
    dispatch_expectation: OneOrderLifecycleDispatchExpectation


# ---------------------------------------------------------------------------
# Section 7.4: immutable internal plan snapshots
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _AuthorizationSnapshot:
    gustavo_execution_authorization_id: str
    environment: str
    ticker: str
    subaccount: int
    account_scope_ref: str
    writer_session_id: str
    capabilities: FrozenSet[CapabilityName]
    max_created_orders: int
    max_create_send_attempts: int
    max_cancel_send_attempts: int
    max_total_rest_requests: int
    max_lifecycle_duration_ms: int
    accepted_spec_sha256: str
    accepted_implementation_commit: str
    source_identity_sha256: str
    operation_binding_sha256: Tuple[Tuple[str, str], ...]
    fee_risk_max_fee_dollars: Decimal
    writer_proof_id: str


@dataclass(frozen=True, slots=True)
class _ProofSnapshot:
    proof_schema_revision: int
    proof_id: str
    proof_mode: str
    lifecycle_execution_authorization_id: str
    venue: str
    environment: str
    account_scope_ref: str
    credential_environment_ref: str
    credential_source_names: Tuple[str, ...]
    subaccount: int
    ticker: str
    writer_session_id: str
    permitted_writer_count: int
    permitted_writer_identities: Tuple[str, ...]
    protected_write_operations: FrozenSet[str]
    valid_from_utc: str
    valid_until_utc: Optional[str]
    release_state: str
    release_condition: str
    continuity_state: str
    prior_write_state: str
    prior_unresolved_write_count: int
    prior_write_execution_ids: Tuple[str, ...]
    unclosed_prior_write_execution_ids: Tuple[str, ...]
    prior_write_provenance_mode: str
    prior_write_provenance_source: str
    canonical_state_commit: str
    canonical_state_label: str
    issuer_role: str
    issuer_validation_result: str


def _snapshot_authorization(authorization: OneOrderLifecycleExecutionAuthorization) -> _AuthorizationSnapshot:
    return _AuthorizationSnapshot(
        gustavo_execution_authorization_id=authorization.gustavo_execution_authorization_id,
        environment=authorization.environment,
        ticker=authorization.ticker,
        subaccount=authorization.subaccount,
        account_scope_ref=authorization.account_scope_ref,
        writer_session_id=authorization.writer_session_id,
        capabilities=frozenset(authorization.capabilities.granted),
        max_created_orders=authorization.max_created_orders,
        max_create_send_attempts=authorization.max_create_send_attempts,
        max_cancel_send_attempts=authorization.max_cancel_send_attempts,
        max_total_rest_requests=authorization.max_total_rest_requests,
        max_lifecycle_duration_ms=authorization.max_lifecycle_duration_ms,
        accepted_spec_sha256=authorization.accepted_spec_sha256,
        accepted_implementation_commit=authorization.accepted_implementation_commit,
        source_identity_sha256=authorization.source_identity_sha256,
        operation_binding_sha256=tuple(sorted((str(k), str(v)) for k, v in authorization.operation_binding_sha256.items())),
        fee_risk_max_fee_dollars=authorization.fee_risk_binding.max_fee_dollars,
        writer_proof_id=authorization.writer_proof_id,
    )


def _snapshot_proof(proof: WriterExclusivityPriorWriteProof) -> _ProofSnapshot:
    protected = frozenset(proof.protected_write_operations)
    return _ProofSnapshot(
        proof_schema_revision=proof.proof_schema_revision, proof_id=proof.proof_id, proof_mode=proof.proof_mode,
        lifecycle_execution_authorization_id=proof.lifecycle_execution_authorization_id,
        venue=proof.venue, environment=proof.environment, account_scope_ref=proof.account_scope_ref,
        credential_environment_ref=proof.credential_environment_ref,
        credential_source_names=tuple(proof.credential_source_names), subaccount=proof.subaccount,
        ticker=proof.ticker, writer_session_id=proof.writer_session_id,
        permitted_writer_count=proof.permitted_writer_count,
        permitted_writer_identities=tuple(proof.permitted_writer_identities),
        protected_write_operations=protected, valid_from_utc=proof.valid_from_utc,
        valid_until_utc=proof.valid_until_utc, release_state=proof.release_state,
        release_condition=proof.release_condition, continuity_state=proof.continuity_state,
        prior_write_state=proof.prior_write_state, prior_unresolved_write_count=proof.prior_unresolved_write_count,
        prior_write_execution_ids=tuple(proof.prior_write_execution_ids),
        unclosed_prior_write_execution_ids=tuple(proof.unclosed_prior_write_execution_ids),
        prior_write_provenance_mode=proof.prior_write_provenance_mode,
        prior_write_provenance_source=proof.prior_write_provenance_source,
        canonical_state_commit=proof.canonical_state_commit, canonical_state_label=proof.canonical_state_label,
        issuer_role=proof.issuer_role, issuer_validation_result=proof.issuer_validation_result,
    )


@dataclass(frozen=True, slots=True)
class OneOrderLifecyclePlan:
    """Immutable secret-free plan containing only copied/canonicalized state."""

    demo_rest_origin: str
    demo_host: str
    demo_port: int
    demo_base_path: str
    ticker: str
    client_order_id: str
    gustavo_execution_authorization_id: str
    writer_session_id: str
    proof_id: str
    account_scope_ref: str
    source_record_bytes: bytes
    source_record_sha256: str
    operation_binding_bytes: Mapping[str, bytes]
    operation_binding_sha256: Mapping[str, str]
    operation_contracts: Mapping[str, _OperationContract]
    max_created_orders: int
    max_create_send_attempts: int
    max_cancel_send_attempts: int
    max_total_rest_requests: int
    retry_count: int
    redirect_count: int
    master_deadline_ms: int
    per_request_ceiling_ms: int
    fee_risk_max_fee_dollars: Decimal
    authorization_snapshot: _AuthorizationSnapshot
    proof_snapshot: _ProofSnapshot
    entry_monotonic: float
    proof_validated_monotonic: float
    executor_entry_utc: str


def _validate_plan_consumption(plan: object) -> Optional[LifecycleHaltCode]:
    if type(plan) is not OneOrderLifecyclePlan:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if (plan.demo_rest_origin != DEMO_REST_ORIGIN or plan.demo_host != _DEMO_HOST or
            type(plan.demo_port) is not int or plan.demo_port != _DEMO_PORT or
            plan.demo_base_path != _TRADE_API_BASE_PATH):
        return LifecycleHaltCode.CANONICAL_DEMO_PROFILE_INVALID
    if type(plan.ticker) is not str or plan.ticker == "" or not is_valid_lowercase_uuid4(plan.client_order_id):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(plan.authorization_snapshot) is not _AuthorizationSnapshot or type(plan.proof_snapshot) is not _ProofSnapshot:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    auth = plan.authorization_snapshot
    proof = plan.proof_snapshot
    if (auth.environment != ENVIRONMENT or auth.ticker != plan.ticker or auth.subaccount != SUBACCOUNT or
            auth.gustavo_execution_authorization_id != plan.gustavo_execution_authorization_id or
            auth.writer_session_id != plan.writer_session_id or auth.account_scope_ref != plan.account_scope_ref or
            auth.writer_proof_id != plan.proof_id):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(auth.capabilities) is not frozenset or any(type(c) is not CapabilityName for c in auth.capabilities):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if (plan.max_created_orders != 1 or plan.max_create_send_attempts != 1 or plan.max_cancel_send_attempts != 1 or
            plan.max_total_rest_requests != GLOBAL_REQUEST_MAXIMUM or plan.retry_count != 0 or plan.redirect_count != 0 or
            plan.master_deadline_ms != MASTER_DEADLINE_MS or plan.per_request_ceiling_ms != PER_REQUEST_CEILING_MS):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if (auth.max_created_orders != plan.max_created_orders or auth.max_create_send_attempts != plan.max_create_send_attempts or
            auth.max_cancel_send_attempts != plan.max_cancel_send_attempts or auth.max_total_rest_requests != plan.max_total_rest_requests or
            auth.max_lifecycle_duration_ms != plan.master_deadline_ms or auth.accepted_spec_sha256 != ACCEPTED_SPEC_SHA256 or
            type(auth.accepted_implementation_commit) is not str or _FORTY_HEX_PATTERN.fullmatch(auth.accepted_implementation_commit.lower()) is None or
            auth.source_identity_sha256 != SOURCE_RECORD_SHA256 or auth.fee_risk_max_fee_dollars != plan.fee_risk_max_fee_dollars):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if type(plan.fee_risk_max_fee_dollars) is not Decimal or plan.fee_risk_max_fee_dollars != auth.fee_risk_max_fee_dollars:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if MAX_FILLED_PRINCIPAL + plan.fee_risk_max_fee_dollars > MAX_TOTAL_RISK:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if (proof.proof_schema_revision != PROOF_SCHEMA_REVISION or
            proof.proof_id != plan.proof_id or
            proof.proof_mode != PROOF_MODE_FIRST_ACCEPTED_DEMO_WRITE or
            proof.lifecycle_execution_authorization_id != plan.gustavo_execution_authorization_id or
            proof.venue != VENUE or proof.environment != ENVIRONMENT or proof.account_scope_ref != plan.account_scope_ref or
            proof.credential_environment_ref != ENVIRONMENT or
            proof.credential_source_names != tuple(_REQUIRED_CREDENTIAL_SOURCE_NAMES) or
            proof.subaccount != SUBACCOUNT or proof.ticker != plan.ticker or proof.writer_session_id != plan.writer_session_id or
            proof.permitted_writer_count != 1 or proof.permitted_writer_identities != (plan.writer_session_id,) or
            proof.protected_write_operations != REQUIRED_PROTECTED_WRITE_OPERATIONS or
            proof.valid_until_utc is not None or proof.release_state != "UNRELEASED" or
            proof.release_condition != "NO_WRITE_SENT_TERMINAL_OR_TERMINAL_AUTHORITATIVE_RECONCILIATION" or
            proof.continuity_state != "HELD" or proof.prior_write_state != "NO_UNRESOLVED_SAME_SCOPE_WRITE" or
            proof.prior_unresolved_write_count != 0 or proof.prior_write_execution_ids != () or
            proof.unclosed_prior_write_execution_ids != () or
            proof.prior_write_provenance_mode != "PROJECT_AUTHORIZATION_AND_ACCEPTED_EXECUTION_EVIDENCE" or
            type(proof.prior_write_provenance_source) is not str or proof.prior_write_provenance_source.strip() == "" or
            type(proof.canonical_state_commit) is not str or _FORTY_HEX_PATTERN.fullmatch(proof.canonical_state_commit.lower()) is None or
            type(proof.canonical_state_label) is not str or proof.canonical_state_label.strip() == "" or
            proof.issuer_role != "GUSTAVO_EXECUTION_DISPATCH" or proof.issuer_validation_result != "PASS"):
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH
    if _parse_rfc3339_utc_z(plan.executor_entry_utc) is None or _parse_rfc3339_utc_z(proof.valid_from_utc) is None:
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ESTABLISHED
    if _parse_rfc3339_utc_z(proof.valid_from_utc) > _parse_rfc3339_utc_z(plan.executor_entry_utc):
        return LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT
    if type(plan.source_record_bytes) is not bytes or sha256_hex(plan.source_record_bytes) != plan.source_record_sha256:
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH
    if parse_and_validate_source_record(raw_bytes=plan.source_record_bytes) is not None:
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH
    if plan.source_record_sha256 != SOURCE_RECORD_SHA256:
        return LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH
    if set(plan.operation_binding_bytes.keys()) != set(OPERATION_BINDINGS.keys()):
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    if set(plan.operation_binding_sha256.keys()) != set(OPERATION_BINDINGS.keys()):
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    for name, raw in plan.operation_binding_bytes.items():
        if validate_operation_binding(name, raw_bytes=raw) is not None:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if plan.operation_binding_sha256[name] != OPERATION_BINDINGS[name][1]:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    if validate_operation_binding_semantics(plan.operation_binding_bytes) is not None:
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    if dict(plan.operation_contracts) != dict(_CURRENT_OPERATION_CONTRACTS):
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    if tuple(sorted(plan.operation_binding_sha256.items())) != auth.operation_binding_sha256:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if not (type(plan.entry_monotonic) in (int, float) and type(plan.proof_validated_monotonic) in (int, float)):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if not math.isfinite(float(plan.entry_monotonic)) or not math.isfinite(float(plan.proof_validated_monotonic)):
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    if plan.proof_validated_monotonic < plan.entry_monotonic:
        return LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID
    return None


# ---------------------------------------------------------------------------
# Section 7.5 / 7.6: immutable public evidence
# ---------------------------------------------------------------------------

def _immutable_mapping(mapping: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True, slots=True)
class OneOrderLifecycleResult:
    terminal: LifecycleTerminal
    gustavo_execution_authorization_id: str
    proof_id: str
    writer_session_id: str
    environment: str
    ticker: str
    subaccount: int
    account_scope_ref: str
    pre_create_truth_confirmed: bool
    pre_create_matching_resting_order_count: int
    pre_create_cursor: str
    client_order_id: str
    bound_order_id: str
    final_status: str
    fills: Tuple[CanonicalFill, ...]
    canonical_fill_quantity: Decimal
    fill_price_validations: Tuple[Tuple[str, bool], ...]
    actual_filled_principal: Decimal
    principal_within_bound: bool
    cancel_classification: Optional[SendOutcome]
    cancel_reduced_by: Optional[Decimal]
    cancel_conservation_result: Optional[bool]
    create_send_may_have_begun: bool
    cancel_send_may_have_begun: bool
    created_order_upper_bound: int
    active_order_upper_bound: int
    unknown_result: bool
    request_counts: Mapping[str, int]
    retry_count: int
    redirect_count: int
    source_record_sha256: str
    operation_binding_sha256: Mapping[str, str]
    proof_continuity_state: str
    proof_release_eligible: bool
    elapsed_ms: float
    secret_safe_evidence_sha256: str

    @property
    def created_order_count_upper_bound(self) -> int:
        return self.created_order_upper_bound

    @property
    def active_order_count_upper_bound(self) -> int:
        return self.active_order_upper_bound


@dataclass(frozen=True, slots=True)
class OneOrderLifecycleHalt:
    halt_code: LifecycleHaltCode
    stage: str
    gustavo_execution_authorization_id: Optional[str]
    proof_id: Optional[str]
    writer_session_id: Optional[str]
    environment: Optional[str]
    ticker: Optional[str]
    subaccount: Optional[int]
    account_scope_ref: Optional[str]
    proof_state: Optional[str]
    prior_write_state: Optional[str]
    proof_release_eligible: bool
    create_send_may_have_begun: bool
    cancel_send_may_have_begun: bool
    request_counts: Mapping[str, int]
    retry_count: int
    redirect_count: int
    bound_order_id: Optional[str]
    client_order_id: Optional[str]
    created_order_upper_bound: int
    active_order_upper_bound: int
    unknown_result: bool
    source_record_sha256: Optional[str]
    operation_binding_sha256: Mapping[str, str]
    elapsed_ms: float
    expected_classification: Optional[str]
    observed_classification: Optional[str]
    secret_safe_evidence_sha256: str

    @property
    def created_order_count_upper_bound(self) -> int:
        return self.created_order_upper_bound

    @property
    def active_order_count_upper_bound(self) -> int:
        return self.active_order_upper_bound


def _with_evidence_hash(evidence: Union[OneOrderLifecycleResult, OneOrderLifecycleHalt]):
    values = {f.name: getattr(evidence, f.name) for f in dataclass_fields(evidence)}
    values["secret_safe_evidence_sha256"] = _recompute_secret_safe_evidence_sha256(evidence)
    return type(evidence)(**values)


def _make_plan_halt(
    code: LifecycleHaltCode,
    *,
    lifecycle_input: Optional[OneOrderLifecycleInput] = None,
    client_order_id: Optional[str] = None,
    source_record_sha256: Optional[str] = None,
    operation_binding_sha256: Optional[Mapping[str, str]] = None,
    expected_classification: Optional[str] = None,
    observed_classification: Optional[str] = None,
) -> OneOrderLifecycleHalt:
    authorization = lifecycle_input.lifecycle_authorization if (lifecycle_input is not None and type(lifecycle_input.lifecycle_authorization) is OneOrderLifecycleExecutionAuthorization) else None
    proof = lifecycle_input.writer_exclusivity_prior_write_proof if (lifecycle_input is not None and type(lifecycle_input.writer_exclusivity_prior_write_proof) is WriterExclusivityPriorWriteProof) else None
    halt = OneOrderLifecycleHalt(
        halt_code=code, stage="PLAN",
        gustavo_execution_authorization_id=authorization.gustavo_execution_authorization_id if authorization else None,
        proof_id=proof.proof_id if proof and type(proof.proof_id) is str else None,
        writer_session_id=authorization.writer_session_id if authorization and type(authorization.writer_session_id) is str else None,
        environment=authorization.environment if authorization and type(authorization.environment) is str else None,
        ticker=lifecycle_input.market_ticker if lifecycle_input is not None and type(lifecycle_input.market_ticker) is str else None,
        subaccount=authorization.subaccount if authorization and type(authorization.subaccount) is int else None,
        account_scope_ref=authorization.account_scope_ref if authorization and type(authorization.account_scope_ref) is str else None,
        proof_state=proof.continuity_state if proof and type(proof.continuity_state) is str else None,
        prior_write_state=proof.prior_write_state if proof and type(proof.prior_write_state) is str else None,
        proof_release_eligible=False, create_send_may_have_begun=False, cancel_send_may_have_begun=False,
        request_counts=MappingProxyType({}), retry_count=0, redirect_count=0, bound_order_id=None,
        client_order_id=client_order_id, created_order_upper_bound=0, active_order_upper_bound=0, unknown_result=False,
        source_record_sha256=source_record_sha256,
        operation_binding_sha256=MappingProxyType(dict(operation_binding_sha256 or {})),
        elapsed_ms=0.0, expected_classification=expected_classification, observed_classification=observed_classification,
        secret_safe_evidence_sha256="",
    )
    return _with_evidence_hash(halt)


# ---------------------------------------------------------------------------
# plan_demo_one_order_lifecycle
# ---------------------------------------------------------------------------

def plan_demo_one_order_lifecycle(
    lifecycle_input: OneOrderLifecycleInput,
    *,
    monotonic_clock: Optional[Callable[[], float]] = None,
    _utc_clock: Optional[Callable[[], str]] = None,
) -> Union[OneOrderLifecyclePlan, OneOrderLifecycleHalt]:
    """Validate every local prerequisite and return an immutable snapshot.

    The authoritative executor-entry UTC value is captured here.  ``_utc_clock``
    is a private deterministic seam for offline tests; ordinary callers do not
    supply an authoritative timestamp.
    """

    import time as _time
    if monotonic_clock is None:
        monotonic_clock = _time.monotonic
    if _utc_clock is None:
        _utc_clock = lambda: datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    if type(lifecycle_input) is not OneOrderLifecycleInput:
        return _make_plan_halt(LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)

    entry_monotonic = monotonic_clock()
    executor_entry_utc = _utc_clock()
    authorization = lifecycle_input.lifecycle_authorization
    writer_proof = lifecycle_input.writer_exclusivity_prior_write_proof
    ticker = lifecycle_input.market_ticker
    client_order_id = lifecycle_input.client_order_id

    if type(authorization) is not OneOrderLifecycleExecutionAuthorization:
        return _make_plan_halt(LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID, lifecycle_input=lifecycle_input)

    halt = validate_controlling_spec_identity(authorization.accepted_spec_sha256)
    if halt is not None:
        return _make_plan_halt(halt, lifecycle_input=lifecycle_input, client_order_id=client_order_id if type(client_order_id) is str else None,
                               expected_classification=ACCEPTED_SPEC_SHA256, observed_classification=str(authorization.accepted_spec_sha256))

    source_bytes = lifecycle_input.official_source_identity_record_bytes
    halt = parse_and_validate_source_record(raw_bytes=source_bytes) if type(source_bytes) is bytes else LifecycleHaltCode.SOURCE_RECORD_IDENTITY_MISMATCH
    if halt is not None:
        observed = sha256_hex(source_bytes) if type(source_bytes) is bytes else type(source_bytes).__name__
        return _make_plan_halt(halt, lifecycle_input=lifecycle_input, client_order_id=client_order_id if type(client_order_id) is str else None,
                               expected_classification=SOURCE_RECORD_SHA256, observed_classification=observed)
    established_source_sha = SOURCE_RECORD_SHA256

    raw_bindings = lifecycle_input.operation_binding_record_bytes
    if not isinstance(raw_bindings, Mapping) or set(raw_bindings.keys()) != set(OPERATION_BINDINGS.keys()):
        return _make_plan_halt(LifecycleHaltCode.OPERATION_BINDING_MISMATCH, lifecycle_input=lifecycle_input,
                               client_order_id=client_order_id if type(client_order_id) is str else None,
                               source_record_sha256=established_source_sha, expected_classification="EXACT_SIX_BINDINGS",
                               observed_classification="BINDING_KEY_SET_MISMATCH")
    binding_bytes_snapshot: Dict[str, bytes] = {}
    binding_sha_snapshot: Dict[str, str] = {}
    for name in OPERATION_BINDINGS:
        raw = raw_bindings[name]
        if type(raw) is not bytes or validate_operation_binding(name, raw_bytes=raw) is not None:
            observed = sha256_hex(raw) if type(raw) is bytes else type(raw).__name__
            return _make_plan_halt(LifecycleHaltCode.OPERATION_BINDING_MISMATCH, lifecycle_input=lifecycle_input,
                                   client_order_id=client_order_id if type(client_order_id) is str else None,
                                   source_record_sha256=established_source_sha, operation_binding_sha256=binding_sha_snapshot,
                                   expected_classification=OPERATION_BINDINGS[name][1], observed_classification=observed)
        binding_bytes_snapshot[name] = bytes(raw)
        binding_sha_snapshot[name] = OPERATION_BINDINGS[name][1]
    halt = validate_operation_binding_semantics(binding_bytes_snapshot)
    if halt is not None:
        return _make_plan_halt(halt, lifecycle_input=lifecycle_input, client_order_id=client_order_id if type(client_order_id) is str else None,
                               source_record_sha256=established_source_sha, operation_binding_sha256=binding_sha_snapshot,
                               expected_classification="APPENDIX_D_SEMANTIC_CONTRACTS", observed_classification="CURRENT_TEMPLATE_MISMATCH")

    halt = validate_execution_authorization(authorization, expected_ticker=ticker, expected_fee_risk_binding=lifecycle_input.fee_risk_binding)
    if halt is not None:
        return _make_plan_halt(halt, lifecycle_input=lifecycle_input, client_order_id=client_order_id if type(client_order_id) is str else None,
                               source_record_sha256=established_source_sha, operation_binding_sha256=binding_sha_snapshot)
    halt = validate_lifecycle_input_fields(
        validated_demo_profile=lifecycle_input.validated_demo_profile,
        authorization_envelope=lifecycle_input.authorization_envelope,
        fee_risk_binding=lifecycle_input.fee_risk_binding,
        dispatch_expectation=lifecycle_input.dispatch_expectation,
    )
    if halt is not None:
        return _make_plan_halt(halt, lifecycle_input=lifecycle_input, client_order_id=client_order_id if type(client_order_id) is str else None,
                               source_record_sha256=established_source_sha, operation_binding_sha256=binding_sha_snapshot)
    if client_order_id is None or client_order_id == "":
        return _make_plan_halt(LifecycleHaltCode.CLIENT_ORDER_ID_MISSING, lifecycle_input=lifecycle_input, source_record_sha256=established_source_sha,
                               operation_binding_sha256=binding_sha_snapshot)
    if not is_valid_lowercase_uuid4(client_order_id):
        return _make_plan_halt(LifecycleHaltCode.CLIENT_ORDER_ID_MALFORMED, lifecycle_input=lifecycle_input, client_order_id=client_order_id if type(client_order_id) is str else None,
                               source_record_sha256=established_source_sha, operation_binding_sha256=binding_sha_snapshot)
    halt = validate_writer_proof(
        writer_proof, expected_ticker=ticker, expected_writer_identity=authorization.writer_session_id,
        expected_lifecycle_execution_authorization_id=authorization.gustavo_execution_authorization_id,
        executor_entry_utc=executor_entry_utc,
    )
    if halt is not None:
        return _make_plan_halt(halt, lifecycle_input=lifecycle_input, client_order_id=client_order_id, source_record_sha256=established_source_sha,
                               operation_binding_sha256=binding_sha_snapshot)
    if writer_proof.proof_id != authorization.writer_proof_id:
        return _make_plan_halt(LifecycleHaltCode.WRITER_EXCLUSIVITY_SCOPE_MISMATCH, lifecycle_input=lifecycle_input, client_order_id=client_order_id,
                               source_record_sha256=established_source_sha, operation_binding_sha256=binding_sha_snapshot)

    proof_validated_monotonic = monotonic_clock()
    return OneOrderLifecyclePlan(
        demo_rest_origin=DEMO_REST_ORIGIN, demo_host=_DEMO_HOST, demo_port=_DEMO_PORT, demo_base_path=_TRADE_API_BASE_PATH,
        ticker=str(ticker), client_order_id=str(client_order_id),
        gustavo_execution_authorization_id=authorization.gustavo_execution_authorization_id,
        writer_session_id=authorization.writer_session_id, proof_id=writer_proof.proof_id, account_scope_ref=authorization.account_scope_ref,
        source_record_bytes=bytes(source_bytes), source_record_sha256=established_source_sha,
        operation_binding_bytes=MappingProxyType(dict(binding_bytes_snapshot)),
        operation_binding_sha256=MappingProxyType(dict(binding_sha_snapshot)),
        operation_contracts=MappingProxyType(dict(_CURRENT_OPERATION_CONTRACTS)),
        max_created_orders=authorization.max_created_orders, max_create_send_attempts=authorization.max_create_send_attempts,
        max_cancel_send_attempts=authorization.max_cancel_send_attempts, max_total_rest_requests=authorization.max_total_rest_requests,
        retry_count=0, redirect_count=0, master_deadline_ms=MASTER_DEADLINE_MS, per_request_ceiling_ms=PER_REQUEST_CEILING_MS,
        fee_risk_max_fee_dollars=lifecycle_input.fee_risk_binding.max_fee_dollars,
        authorization_snapshot=_snapshot_authorization(authorization), proof_snapshot=_snapshot_proof(writer_proof),
        entry_monotonic=entry_monotonic, proof_validated_monotonic=proof_validated_monotonic, executor_entry_utc=executor_entry_utc,
    )


_BINDING_NAME_BY_OPERATION: Mapping[LifecycleOperation, str] = MappingProxyType({
    LifecycleOperation.PRE_CREATE_TRUTH: "PRE_CREATE_ORDER_TRUTH",
    LifecycleOperation.CREATE: "CREATE_ORDER_V2",
    LifecycleOperation.RECOVERY: "ORDER_LIST_RECOVERY",
    LifecycleOperation.EXACT_ORDER: "EXACT_ORDER_READ",
    LifecycleOperation.FILLS: "FILL_READ",
    LifecycleOperation.CANCEL: "CANCEL_ORDER_V2",
})


def _validate_prepared_request_contract(
    plan: OneOrderLifecyclePlan,
    request: PreparedRequest,
    *,
    expected_order_id: Optional[str] = None,
    expected_cursor: Optional[str] = None,
    expected_expiration_time: Optional[int] = None,
) -> Optional[LifecycleHaltCode]:
    """Validate the concrete request against the immutable Appendix-D plan.

    This check is intentionally independent of the public request-builder
    helpers so monkeypatching or otherwise tampering with a builder cannot make
    the validator agree with the same bad template. Dynamic order-id, fill
    cursor and create-expiration values are supplied from the already-frozen
    lifecycle state and must match exactly before the request may reach the
    transport.
    """

    if type(request) is not PreparedRequest:
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    name = _BINDING_NAME_BY_OPERATION.get(request.operation)
    if name is None or name not in plan.operation_contracts:
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    contract = plan.operation_contracts[name]
    if request.method != contract.method:
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH

    if "{order_id}" in contract.path_template:
        if type(expected_order_id) is not str or expected_order_id == "":
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        expected_path = (
            _TRADE_API_BASE_PATH
            + contract.path_template.replace("{order_id}", expected_order_id)
        )
        if request.path != expected_path:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    elif request.path != _TRADE_API_BASE_PATH + contract.path_template:
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH

    q = dict(request.query)
    if request.operation is LifecycleOperation.PRE_CREATE_TRUTH:
        if set(q) != {"ticker", "status", "limit", "subaccount"}:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["ticker"]) is not str or q["ticker"] != plan.ticker:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["status"]) is not str or q["status"] != "resting":
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["limit"]) is not int or q["limit"] != 1000:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["subaccount"]) is not int or q["subaccount"] != SUBACCOUNT:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    elif request.operation is LifecycleOperation.RECOVERY:
        if set(q) != {"ticker", "limit", "subaccount"}:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["ticker"]) is not str or q["ticker"] != plan.ticker:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["limit"]) is not int or q["limit"] != 1000:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["subaccount"]) is not int or q["subaccount"] != SUBACCOUNT:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    elif request.operation is LifecycleOperation.EXACT_ORDER:
        if q != {}:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    elif request.operation is LifecycleOperation.FILLS:
        if type(expected_order_id) is not str or expected_order_id == "":
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(expected_cursor) is not str:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        expected_keys = {"order_id", "limit", "subaccount"}
        if expected_cursor != "":
            expected_keys.add("cursor")
        if set(q) != expected_keys:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["order_id"]) is not str or q["order_id"] != expected_order_id:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["limit"]) is not int or q["limit"] != 1000:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["subaccount"]) is not int or q["subaccount"] != SUBACCOUNT:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if expected_cursor != "":
            if type(q["cursor"]) is not str or q["cursor"] != expected_cursor:
                return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    elif request.operation is LifecycleOperation.CANCEL:
        if set(q) != {"subaccount", "exchange_index"}:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["subaccount"]) is not int or q["subaccount"] != SUBACCOUNT:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(q["exchange_index"]) is not int or q["exchange_index"] != EXCHANGE_INDEX:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    elif request.operation is LifecycleOperation.CREATE:
        if q != {} or request.body is None or not isinstance(request.body, Mapping):
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        body = request.body
        if set(body) != CREATE_ORDER_ALLOWED_FIELDS:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["ticker"]) is not str or body["ticker"] != plan.ticker:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["client_order_id"]) is not str or body["client_order_id"] != plan.client_order_id:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["side"]) is not str or body["side"] != "bid":
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["count"]) is not str or body["count"] != "1.00":
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["price"]) is not str or body["price"] != "0.0100":
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["time_in_force"]) is not str or body["time_in_force"] != "good_till_canceled":
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if (type(body["self_trade_prevention_type"]) is not str or
                body["self_trade_prevention_type"] != "taker_at_cross"):
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(expected_expiration_time) is not int or type(expected_expiration_time) is bool:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["expiration_time"]) is not int or type(body["expiration_time"]) is bool or body["expiration_time"] != expected_expiration_time:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if body["post_only"] is not True or body["cancel_order_on_pause"] is not True or body["reduce_only"] is not False:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["subaccount"]) is not int or body["subaccount"] != SUBACCOUNT:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
        if type(body["exchange_index"]) is not int or body["exchange_index"] != EXCHANGE_INDEX:
            return LifecycleHaltCode.OPERATION_BINDING_MISMATCH

    if request.operation is not LifecycleOperation.CREATE and request.body is not None:
        return LifecycleHaltCode.OPERATION_BINDING_MISMATCH
    return None


# ---------------------------------------------------------------------------
# execute_demo_one_order_lifecycle
# ---------------------------------------------------------------------------

def execute_demo_one_order_lifecycle(
    plan: OneOrderLifecyclePlan,
    transport: LifecycleTransport,
    *,
    monotonic_clock: Optional[Callable[[], float]] = None,
    _wall_clock: Optional[Callable[[], float]] = None,
) -> Union[OneOrderLifecycleResult, OneOrderLifecycleHalt]:
    """Execute one closed Demo lifecycle through a caller-supplied transport.

    No venue implementation lives here. The wall clock is captured internally;
    ``_wall_clock`` exists only as a deterministic offline-test seam.
    """

    import time as _time
    if monotonic_clock is None:
        monotonic_clock = _time.monotonic
    if _wall_clock is None:
        _wall_clock = _time.time

    plan_halt = _validate_plan_consumption(plan)
    if plan_halt is not None:
        return _make_plan_halt(plan_halt)

    auth = plan.authorization_snapshot
    proof = plan.proof_snapshot
    ticker = plan.ticker
    frozen_client_order_id = plan.client_order_id
    budget = RequestBudgetTracker()
    ledger = FillLedger()
    deadline = LifecycleDeadline(monotonic_clock=monotonic_clock, entry_monotonic=plan.entry_monotonic, master_deadline_ms=plan.master_deadline_ms)

    create_send_may_have_begun = False
    cancel_send_may_have_begun = False
    created_order_upper_bound = 0
    active_order_upper_bound = 0
    unknown_result = False
    bound_order_id: Optional[str] = None

    def _halt(
        code: LifecycleHaltCode,
        *,
        expected_classification: Optional[str] = None,
        observed_classification: Optional[str] = None,
        proof_release_eligible_override: Optional[bool] = None,
    ) -> OneOrderLifecycleHalt:
        elapsed_ms = max(0.0, (monotonic_clock() - plan.entry_monotonic) * 1000.0)
        halt = OneOrderLifecycleHalt(
            halt_code=code, stage="EXECUTE",
            gustavo_execution_authorization_id=plan.gustavo_execution_authorization_id,
            proof_id=plan.proof_id, writer_session_id=plan.writer_session_id, environment=ENVIRONMENT,
            ticker=plan.ticker, subaccount=SUBACCOUNT, account_scope_ref=plan.account_scope_ref,
            proof_state=proof.continuity_state, prior_write_state=proof.prior_write_state,
            proof_release_eligible=(
                proof_release_eligible_override
                if proof_release_eligible_override is not None
                else (not create_send_may_have_begun and not cancel_send_may_have_begun)
            ),
            create_send_may_have_begun=create_send_may_have_begun,
            cancel_send_may_have_begun=cancel_send_may_have_begun,
            request_counts=MappingProxyType(budget.snapshot()), retry_count=plan.retry_count, redirect_count=plan.redirect_count,
            bound_order_id=bound_order_id, client_order_id=frozen_client_order_id,
            created_order_upper_bound=created_order_upper_bound, active_order_upper_bound=active_order_upper_bound,
            unknown_result=unknown_result, source_record_sha256=plan.source_record_sha256,
            operation_binding_sha256=MappingProxyType(dict(plan.operation_binding_sha256)), elapsed_ms=elapsed_ms,
            expected_classification=expected_classification, observed_classification=observed_classification,
            secret_safe_evidence_sha256="",
        )
        return _with_evidence_hash(halt)

    def _reserve(operation: LifecycleOperation) -> Optional[OneOrderLifecycleHalt]:
        capability = _OPERATION_REQUIRED_CAPABILITY[operation]
        if capability not in auth.capabilities:
            return _halt(LifecycleHaltCode.CAPABILITY_MISSING, expected_classification=capability.value, observed_classification="MISSING")
        try:
            budget.reserve(operation)
        except RequestBudgetExceededError:
            return _halt(LifecycleHaltCode.REQUEST_BUDGET_EXCEEDED)
        return None

    def _perform(
        request: PreparedRequest,
        *,
        expected_order_id: Optional[str] = None,
        expected_cursor: Optional[str] = None,
        expected_expiration_time: Optional[int] = None,
    ) -> Tuple[Optional[RawHttpResponse], Optional[LifecycleHaltCode], SendOutcome]:
        contract_halt = _validate_prepared_request_contract(
            plan, request, expected_order_id=expected_order_id,
            expected_cursor=expected_cursor, expected_expiration_time=expected_expiration_time,
        )
        if contract_halt is not None:
            return None, contract_halt, SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND
        return _send_and_validate(transport, request, monotonic_clock=monotonic_clock)

    if deadline.is_expired(monotonic_clock()):
        return _halt(LifecycleHaltCode.DEADLINE_EXCEEDED)

    # Pre-create authoritative truth.
    reservation = _reserve(LifecycleOperation.PRE_CREATE_TRUTH)
    if reservation is not None:
        return reservation
    pre_create_send_boundary_monotonic = monotonic_clock()
    if not (plan.proof_validated_monotonic < pre_create_send_boundary_monotonic):
        return _halt(LifecycleHaltCode.WRITER_EXCLUSIVITY_NOT_ACTIVE_BEFORE_PREFLIGHT)
    request = _build_request(
        LifecycleOperation.PRE_CREATE_TRUTH, method="GET", path=f"{_TRADE_API_BASE_PATH}/portfolio/orders",
        query=build_pre_create_query(ticker=ticker), body=None, deadline=deadline, monotonic_clock=monotonic_clock,
    )
    raw, evidence_halt, disposition = _perform(request)
    if evidence_halt is not None:
        return _halt(evidence_halt, observed_classification=disposition.value)
    assert raw is not None
    if disposition is not SendOutcome.DEFINITIVE_SUCCESS:
        return _halt(LifecycleHaltCode.PRE_CREATE_HTTP_ERROR, observed_classification=disposition.value)
    response, parse_halt = _parse_get_orders_response(raw, malformed_code=LifecycleHaltCode.PRE_CREATE_MALFORMED_RESPONSE)
    if parse_halt is not None:
        return _halt(parse_halt)
    assert response is not None
    pre_create_halt = validate_pre_create_response(response, ticker=ticker)
    if pre_create_halt is not None:
        return _halt(pre_create_halt)

    if deadline.is_expired(monotonic_clock()):
        return _halt(LifecycleHaltCode.DEADLINE_EXCEEDED)

    # Create.
    try:
        freeze_epoch = _wall_clock()
        if type(freeze_epoch) not in (int, float) or type(freeze_epoch) is bool or not math.isfinite(float(freeze_epoch)):
            return _halt(LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
        expiration_time = compute_expiration_time(freeze_epoch)
    except Exception:
        return _halt(LifecycleHaltCode.EXECUTION_AUTHORIZATION_INVALID)
    create_body = build_create_order_body(ticker=ticker, client_order_id=frozen_client_order_id, expiration_time=expiration_time)
    reservation = _reserve(LifecycleOperation.CREATE)
    if reservation is not None:
        return reservation
    request = _build_request(
        LifecycleOperation.CREATE, method="POST", path=f"{_TRADE_API_BASE_PATH}/portfolio/events/orders", query={}, body=create_body,
        deadline=deadline, monotonic_clock=monotonic_clock,
    )
    create_raw, evidence_halt, disposition = _perform(request, expected_expiration_time=expiration_time)
    if disposition is not SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
        create_send_may_have_begun = True
        created_order_upper_bound = 1
        active_order_upper_bound = 1
    if evidence_halt is not None:
        if disposition is SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
            created_order_upper_bound = 0
            active_order_upper_bound = 0
        else:
            unknown_result = True
        return _halt(evidence_halt, observed_classification=disposition.value)
    assert create_raw is not None
    create_outcome, definitive_order_id = classify_create_response(create_raw, expected_client_order_id=frozen_client_order_id)
    if (disposition is SendOutcome.DEFINITIVE_SUCCESS and create_raw.status == 201
            and create_outcome is SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN):
        unknown_result = True
        return _halt(LifecycleHaltCode.CREATE_RESPONSE_MALFORMED, observed_classification=create_outcome.value)
    if create_outcome is SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
        create_send_may_have_begun = False
        created_order_upper_bound = 0
        active_order_upper_bound = 0
        return _halt(LifecycleHaltCode.CREATE_DEFINITIVELY_FAILED, observed_classification=create_outcome.value)
    if create_outcome is SendOutcome.DEFINITIVE_SUCCESS:
        bound_order_id = definitive_order_id
        created_order_upper_bound = 1
        active_order_upper_bound = 1
    else:
        unknown_result = True
        # Ambiguous create: one recovery list read, never another POST.
        reservation = _reserve(LifecycleOperation.RECOVERY)
        if reservation is not None:
            return reservation
        request = _build_request(
            LifecycleOperation.RECOVERY, method="GET", path=f"{_TRADE_API_BASE_PATH}/portfolio/orders",
            query=build_recovery_query(ticker=ticker), body=None, deadline=deadline, monotonic_clock=monotonic_clock,
        )
        recovery_raw, recovery_transport_halt, recovery_disposition = _perform(request)
        if recovery_transport_halt is not None:
            return _halt(recovery_transport_halt, observed_classification=recovery_disposition.value)
        assert recovery_raw is not None
        if recovery_disposition is not SendOutcome.DEFINITIVE_SUCCESS:
            return _halt(LifecycleHaltCode.CREATE_AMBIGUOUS_UNRESOLVED, observed_classification=recovery_disposition.value)
        recovery_response, recovery_parse_halt = _parse_get_orders_response(
            recovery_raw, malformed_code=LifecycleHaltCode.RECOVERY_MALFORMED_RESPONSE
        )
        if recovery_parse_halt is not None:
            return _halt(recovery_parse_halt)
        assert recovery_response is not None
        recovered_order, recovery_halt = validate_recovery_response(
            recovery_response, client_order_id=frozen_client_order_id, ticker=ticker,
        )
        if recovery_halt is not None:
            return _halt(recovery_halt)
        assert recovered_order is not None
        bound_order_id = recovered_order["order_id"]  # validated str
        unknown_result = False

    if bound_order_id is None:
        unknown_result = True
        return _halt(LifecycleHaltCode.CREATE_AMBIGUOUS_UNRESOLVED)
    if deadline.is_expired(monotonic_clock()):
        return _halt(LifecycleHaltCode.DEADLINE_EXCEEDED)

    # Initial exact order.
    reservation = _reserve(LifecycleOperation.EXACT_ORDER)
    if reservation is not None:
        return reservation
    request = _build_request(
        LifecycleOperation.EXACT_ORDER, method="GET", path=f"{_TRADE_API_BASE_PATH}/portfolio/orders/{bound_order_id}",
        query={}, body=None, deadline=deadline, monotonic_clock=monotonic_clock,
    )
    order_raw, order_transport_halt, order_disposition = _perform(request, expected_order_id=bound_order_id)
    if order_transport_halt is not None:
        return _halt(order_transport_halt, observed_classification=order_disposition.value)
    assert order_raw is not None
    if order_disposition is not SendOutcome.DEFINITIVE_SUCCESS:
        return _halt(LifecycleHaltCode.ORDER_MALFORMED, observed_classification=order_disposition.value)
    latest_order, order_parse_halt = _parse_exact_order_response(order_raw)
    if order_parse_halt is not None:
        return _halt(order_parse_halt)
    assert latest_order is not None
    order_halt = validate_order_record(latest_order, bound_order_id=bound_order_id, client_order_id=frozen_client_order_id, ticker=ticker)
    if order_halt is not None:
        return _halt(order_halt)

    # Initial fills, with strict required fills/cursor on every page.
    fills_cursor = ""
    first_page = True
    while True:
        if deadline.is_expired(monotonic_clock()):
            return _halt(LifecycleHaltCode.DEADLINE_EXCEEDED)
        reservation = _reserve(LifecycleOperation.FILLS)
        if reservation is not None:
            return reservation
        request = _build_request(
            LifecycleOperation.FILLS, method="GET", path=f"{_TRADE_API_BASE_PATH}/portfolio/fills",
            query=build_fills_query(order_id=bound_order_id, cursor=(fills_cursor if not first_page else "")),
            body=None, deadline=deadline, monotonic_clock=monotonic_clock,
        )
        fills_raw, fills_transport_halt, fills_disposition = _perform(request, expected_order_id=bound_order_id, expected_cursor=(fills_cursor if not first_page else ""))
        if fills_transport_halt is not None:
            return _halt(fills_transport_halt, observed_classification=fills_disposition.value)
        assert fills_raw is not None
        if fills_disposition is not SendOutcome.DEFINITIVE_SUCCESS:
            return _halt(LifecycleHaltCode.FILL_MALFORMED, observed_classification=fills_disposition.value)
        page_fills, fills_cursor_value, fills_parse_halt = _parse_fills_page(fills_raw)
        if fills_parse_halt is not None:
            return _halt(fills_parse_halt)
        assert page_fills is not None and fills_cursor_value is not None
        for raw_fill in page_fills:
            fill_halt = ledger.ingest(raw_fill, bound_order_id=bound_order_id, ticker=ticker)
            if fill_halt is not None:
                return _halt(fill_halt)
        fills_cursor = fills_cursor_value
        first_page = False
        if fills_cursor == "":
            break
        if budget.remaining(LifecycleOperation.FILLS) <= 0:
            return _halt(LifecycleHaltCode.FILLS_INCOMPLETE_PAGE_BUDGET)

    reconciliation_halt = ledger.reconcile_against_order(latest_order)
    if reconciliation_halt is not None:
        return _halt(reconciliation_halt)

    latest_status = latest_order["status"]
    canonical_qty = ledger.total_quantity()
    pre_create_truth_confirmed = True

    send_capable = cancel_is_send_capable(
        bound_order_id=bound_order_id, latest_status=latest_status, canonical_fill_quantity=canonical_qty,
        cancel_send_attempt_count=0, writer_proof_state_held=(proof.continuity_state == "HELD"),
        has_cancel_capability=(CapabilityName.ORDER_CANCEL in auth.capabilities),
        deadline_capacity_remaining=not deadline.is_expired(monotonic_clock()),
    )

    if send_capable:
        reservation = _reserve(LifecycleOperation.CANCEL)
        if reservation is not None:
            return reservation
        request = _build_request(
            LifecycleOperation.CANCEL, method="DELETE", path=f"{_TRADE_API_BASE_PATH}/portfolio/events/orders/{bound_order_id}",
            query=build_cancel_query(), body=None, deadline=deadline, monotonic_clock=monotonic_clock,
        )
        cancel_raw, cancel_transport_halt, cancel_disposition = _perform(request, expected_order_id=bound_order_id)
        if cancel_disposition is not SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
            cancel_send_may_have_begun = True
        if cancel_transport_halt is not None:
            if cancel_disposition is not SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
                unknown_result = True
            return _halt(cancel_transport_halt, observed_classification=cancel_disposition.value)
        assert cancel_raw is not None
        cancel_outcome = classify_cancel_response(
            cancel_raw, expected_order_id=bound_order_id, expected_client_order_id=frozen_client_order_id
        )
        if (cancel_disposition is SendOutcome.DEFINITIVE_SUCCESS and cancel_raw.status == 200
                and cancel_outcome is SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN):
            unknown_result = True
            return _halt(LifecycleHaltCode.CANCEL_RESPONSE_MALFORMED, observed_classification=cancel_outcome.value)
        if cancel_outcome is SendOutcome.DEFINITELY_NOT_SENT_PRE_SEND:
            cancel_send_may_have_begun = False
            return _halt(LifecycleHaltCode.CANCEL_SEND_DEFINITIVELY_FAILED, observed_classification=cancel_outcome.value)
        if cancel_outcome is SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN:
            unknown_result = True
            _reconcile_after_ambiguous_cancel(
                plan=plan, transport=transport, budget=budget, deadline=deadline, monotonic_clock=monotonic_clock,
                bound_order_id=bound_order_id, frozen_client_order_id=frozen_client_order_id, ticker=ticker, ledger=ledger,
            )
            return _halt(LifecycleHaltCode.CANCEL_AMBIGUOUS_UNRESOLVED, observed_classification=cancel_outcome.value)

        # Definitive validated cancel success.
        unknown_result = False
        reduced_by = _parse_fixed_point_count(cancel_raw.body["reduced_by"])
        if reduced_by is None:
            unknown_result = True
            return _halt(LifecycleHaltCode.CANCEL_RESPONSE_MALFORMED)

        final_order, reread_halt = _reread_order_after_cancel(
            plan=plan, transport=transport, budget=budget, deadline=deadline, monotonic_clock=monotonic_clock,
            bound_order_id=bound_order_id, frozen_client_order_id=frozen_client_order_id, ticker=ticker,
        )
        if reread_halt is not None:
            return _halt(reread_halt)
        assert final_order is not None
        fills_complete, fills_halt = _drain_final_fills(
            plan=plan, transport=transport, budget=budget, deadline=deadline, monotonic_clock=monotonic_clock,
            bound_order_id=bound_order_id, ticker=ticker, ledger=ledger,
        )
        if fills_halt is not None:
            return _halt(fills_halt)
        if not fills_complete:
            return _halt(LifecycleHaltCode.FINAL_FILL_RECONCILIATION_INCOMPLETE)

        # Complete final Order/Fill reconciliation is mandatory before race resolution.
        reconciliation_halt = ledger.reconcile_against_order(final_order)
        if reconciliation_halt is not None:
            return _halt(reconciliation_halt)
        final_status = final_order["status"]
        final_fill_quantity = ledger.total_quantity()
        final_remaining = _parse_fixed_point_count(final_order["remaining_count_fp"])
        final_fill_count = _parse_fixed_point_count(final_order["fill_count_fp"])
        if final_remaining is None or final_fill_count is None:
            return _halt(LifecycleHaltCode.ORDER_MALFORMED)

        if final_status == "canceled":
            conservation_halt = check_cancel_conservation(final_fill_quantity=final_fill_quantity, reduced_by=reduced_by)
            if conservation_halt is not None:
                return _halt(conservation_halt)
            terminal = LifecycleTerminal.CANCELED
            conservation_result: Optional[bool] = True
        elif final_status == "executed":
            # A valid fill/cancel race may finish executed, but then all quantity
            # must be authoritative fills and the cancel response must have
            # reduced zero quantity.
            if final_fill_quantity != QUANTITY or final_fill_count != QUANTITY or final_remaining != Decimal("0.00"):
                return _halt(LifecycleHaltCode.FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH)
            if reduced_by != Decimal("0.00"):
                return _halt(LifecycleHaltCode.CANCEL_QUANTITY_CONSERVATION_MISMATCH)
            terminal = LifecycleTerminal.FILLED
            conservation_result = True
        else:
            return _halt(LifecycleHaltCode.UNRESOLVED_TERMINAL_STATE, observed_classification=str(final_status))

        candidate = _build_result(
            terminal=terminal, plan=plan, bound_order_id=bound_order_id, final_status=str(final_status), ledger=ledger,
            pre_create_truth_confirmed=pre_create_truth_confirmed, budget=budget, cancel_classification=cancel_outcome,
            cancel_reduced_by=reduced_by, cancel_conservation_result=conservation_result, monotonic_clock=monotonic_clock,
            create_send_may_have_begun=create_send_may_have_begun, cancel_send_may_have_begun=cancel_send_may_have_begun,
            created_order_upper_bound=created_order_upper_bound, active_order_upper_bound=0,
        )
        if deadline.is_expired(monotonic_clock()):
            return _halt(LifecycleHaltCode.DEADLINE_EXCEEDED)
        return candidate

    # No cancel attempted: only fully reconciled terminal observations succeed.
    if latest_status == "executed" and canonical_qty == QUANTITY:
        remaining = _parse_fixed_point_count(latest_order["remaining_count_fp"])
        if remaining != Decimal("0.00"):
            return _halt(LifecycleHaltCode.FILL_QUANTITY_ORDER_RECONCILIATION_MISMATCH)
        candidate = _build_result(
            terminal=LifecycleTerminal.FILLED, plan=plan, bound_order_id=bound_order_id, final_status="executed", ledger=ledger,
            pre_create_truth_confirmed=pre_create_truth_confirmed, budget=budget, cancel_classification=None, cancel_reduced_by=None,
            cancel_conservation_result=None, monotonic_clock=monotonic_clock,
            create_send_may_have_begun=create_send_may_have_begun, cancel_send_may_have_begun=False,
            created_order_upper_bound=created_order_upper_bound, active_order_upper_bound=0,
        )
        if deadline.is_expired(monotonic_clock()):
            return _halt(LifecycleHaltCode.DEADLINE_EXCEEDED)
        return candidate
    if latest_status == "canceled":
        remaining = _parse_fixed_point_count(latest_order["remaining_count_fp"])
        if remaining != Decimal("0.00"):
            return _halt(LifecycleHaltCode.UNRESOLVED_TERMINAL_STATE)
        candidate = _build_result(
            terminal=LifecycleTerminal.ALREADY_CANCELED, plan=plan, bound_order_id=bound_order_id, final_status="canceled", ledger=ledger,
            pre_create_truth_confirmed=pre_create_truth_confirmed, budget=budget, cancel_classification=None, cancel_reduced_by=None,
            cancel_conservation_result=None, monotonic_clock=monotonic_clock,
            create_send_may_have_begun=create_send_may_have_begun, cancel_send_may_have_begun=False,
            created_order_upper_bound=created_order_upper_bound, active_order_upper_bound=0,
        )
        if deadline.is_expired(monotonic_clock()):
            return _halt(LifecycleHaltCode.DEADLINE_EXCEEDED)
        return candidate
    return _halt(LifecycleHaltCode.UNRESOLVED_TERMINAL_STATE)


def _build_result(
    *,
    terminal: LifecycleTerminal,
    plan: OneOrderLifecyclePlan,
    bound_order_id: str,
    final_status: str,
    ledger: FillLedger,
    pre_create_truth_confirmed: bool,
    budget: RequestBudgetTracker,
    cancel_classification: Optional[SendOutcome],
    cancel_reduced_by: Optional[Decimal],
    cancel_conservation_result: Optional[bool],
    monotonic_clock: Callable[[], float],
    create_send_may_have_begun: bool,
    cancel_send_may_have_begun: bool,
    created_order_upper_bound: int,
    active_order_upper_bound: int,
) -> OneOrderLifecycleResult:
    fills = tuple(ledger.fills())
    fill_price_validations = tuple((f.fill_id, f.yes_price_dollars <= LIMIT_PRICE) for f in fills)
    actual_filled_principal = ledger.actual_filled_principal()
    principal_within_bound = actual_filled_principal <= MAX_FILLED_PRINCIPAL
    elapsed_ms = (monotonic_clock() - plan.entry_monotonic) * 1000.0
    proof_release_eligible = True
    result = OneOrderLifecycleResult(
        terminal=terminal,
        gustavo_execution_authorization_id=plan.gustavo_execution_authorization_id,
        proof_id=plan.proof_id,
        writer_session_id=plan.writer_session_id,
        environment=ENVIRONMENT,
        ticker=plan.ticker,
        subaccount=SUBACCOUNT,
        account_scope_ref=plan.account_scope_ref,
        pre_create_truth_confirmed=pre_create_truth_confirmed,
        pre_create_matching_resting_order_count=0,
        pre_create_cursor="",
        client_order_id=plan.client_order_id,
        bound_order_id=bound_order_id,
        final_status=final_status,
        fills=fills,
        canonical_fill_quantity=ledger.total_quantity(),
        fill_price_validations=fill_price_validations,
        actual_filled_principal=actual_filled_principal,
        principal_within_bound=principal_within_bound,
        cancel_classification=cancel_classification,
        cancel_reduced_by=cancel_reduced_by,
        cancel_conservation_result=cancel_conservation_result,
        create_send_may_have_begun=create_send_may_have_begun,
        cancel_send_may_have_begun=cancel_send_may_have_begun,
        created_order_upper_bound=created_order_upper_bound,
        active_order_upper_bound=active_order_upper_bound,
        unknown_result=False,
        request_counts=MappingProxyType(budget.snapshot()),
        retry_count=plan.retry_count,
        redirect_count=plan.redirect_count,
        source_record_sha256=plan.source_record_sha256,
        operation_binding_sha256=MappingProxyType(dict(plan.operation_binding_sha256)),
        proof_continuity_state=plan.proof_snapshot.continuity_state,
        proof_release_eligible=proof_release_eligible,
        elapsed_ms=elapsed_ms,
        secret_safe_evidence_sha256="",
    )
    return _with_evidence_hash(result)


def _reread_order_after_cancel(
    *,
    plan: OneOrderLifecyclePlan,
    transport: LifecycleTransport,
    budget: RequestBudgetTracker,
    deadline: LifecycleDeadline,
    monotonic_clock: Callable[[], float],
    bound_order_id: str,
    frozen_client_order_id: str,
    ticker: str,
) -> Tuple[Optional[Mapping[str, object]], Optional[LifecycleHaltCode]]:
    """Return the complete validated final authoritative Order."""

    if budget.remaining(LifecycleOperation.EXACT_ORDER) <= 0:
        return None, LifecycleHaltCode.FINAL_FILL_RECONCILIATION_INCOMPLETE
    if deadline.is_expired(monotonic_clock()):
        return None, LifecycleHaltCode.DEADLINE_EXCEEDED

    budget.reserve(LifecycleOperation.EXACT_ORDER)
    request = _build_request(
        LifecycleOperation.EXACT_ORDER,
        method="GET",
        path=f"{_TRADE_API_BASE_PATH}/portfolio/orders/{bound_order_id}",
        query={},
        body=None,
        deadline=deadline,
        monotonic_clock=monotonic_clock,
    )
    contract_halt = _validate_prepared_request_contract(plan, request, expected_order_id=bound_order_id)
    if contract_halt is not None:
        return None, contract_halt
    raw, evidence_halt, disposition = _send_and_validate(
        transport, request, monotonic_clock=monotonic_clock
    )
    if evidence_halt is not None:
        return None, evidence_halt
    if disposition is not SendOutcome.DEFINITIVE_SUCCESS or raw is None:
        return None, LifecycleHaltCode.ORDER_MALFORMED
    reread_order, parse_halt = _parse_exact_order_response(raw)
    if parse_halt is not None or reread_order is None:
        return None, parse_halt or LifecycleHaltCode.ORDER_MALFORMED
    halt = validate_order_record(
        reread_order,
        bound_order_id=bound_order_id,
        client_order_id=frozen_client_order_id,
        ticker=ticker,
    )
    if halt is not None:
        return None, halt
    return reread_order, None


def _drain_final_fills(
    *,
    plan: OneOrderLifecyclePlan,
    transport: LifecycleTransport,
    budget: RequestBudgetTracker,
    deadline: LifecycleDeadline,
    monotonic_clock: Callable[[], float],
    bound_order_id: str,
    ticker: str,
    ledger: FillLedger,
) -> Tuple[bool, Optional[LifecycleHaltCode]]:
    """Drain final post-cancel fills with strict page completeness."""

    cursor = ""
    first_page = True
    while True:
        if not first_page and cursor == "":
            return True, None
        if budget.remaining(LifecycleOperation.FILLS) <= 0:
            return False, None
        if deadline.is_expired(monotonic_clock()):
            return False, LifecycleHaltCode.DEADLINE_EXCEEDED

        budget.reserve(LifecycleOperation.FILLS)
        request = _build_request(
            LifecycleOperation.FILLS,
            method="GET",
            path=f"{_TRADE_API_BASE_PATH}/portfolio/fills",
            query=build_fills_query(order_id=bound_order_id, cursor=(cursor if not first_page else "")),
            body=None,
            deadline=deadline,
            monotonic_clock=monotonic_clock,
        )
        contract_halt = _validate_prepared_request_contract(
            plan, request, expected_order_id=bound_order_id,
            expected_cursor=(cursor if not first_page else ""),
        )
        if contract_halt is not None:
            return False, contract_halt
        raw, evidence_halt, disposition = _send_and_validate(
            transport, request, monotonic_clock=monotonic_clock
        )
        if evidence_halt is not None:
            return False, evidence_halt
        if disposition is not SendOutcome.DEFINITIVE_SUCCESS or raw is None:
            return False, LifecycleHaltCode.FILL_MALFORMED
        page_fills, next_cursor, parse_halt = _parse_fills_page(raw)
        if parse_halt is not None or page_fills is None or next_cursor is None:
            return False, parse_halt or LifecycleHaltCode.FILL_MALFORMED

        for raw_fill in page_fills:
            halt = ledger.ingest(raw_fill, bound_order_id=bound_order_id, ticker=ticker)
            if halt is not None:
                return False, halt

        cursor = next_cursor
        first_page = False
        if cursor == "":
            return True, None


def _reconcile_after_ambiguous_cancel(
    *,
    plan: OneOrderLifecyclePlan,
    transport: LifecycleTransport,
    budget: RequestBudgetTracker,
    deadline: LifecycleDeadline,
    monotonic_clock: Callable[[], float],
    bound_order_id: str,
    frozen_client_order_id: str,
    ticker: str,
    ledger: FillLedger,
) -> None:
    """Best-effort same-order reads after an unknown cancel; never resend."""

    if budget.remaining(LifecycleOperation.EXACT_ORDER) > 0 and not deadline.is_expired(monotonic_clock()):
        try:
            budget.reserve(LifecycleOperation.EXACT_ORDER)
            request = _build_request(
                LifecycleOperation.EXACT_ORDER,
                method="GET",
                path=f"{_TRADE_API_BASE_PATH}/portfolio/orders/{bound_order_id}",
                query={}, body=None, deadline=deadline, monotonic_clock=monotonic_clock,
            )
            if _validate_prepared_request_contract(
                plan, request, expected_order_id=bound_order_id
            ) is None:
                raw, evidence_halt, disposition = _send_and_validate(
                    transport, request, monotonic_clock=monotonic_clock
                )
                if evidence_halt is None and disposition is SendOutcome.DEFINITIVE_SUCCESS and raw is not None:
                    reread_order, parse_halt = _parse_exact_order_response(raw)
                    if parse_halt is None and reread_order is not None:
                        validate_order_record(
                            reread_order,
                            bound_order_id=bound_order_id,
                            client_order_id=frozen_client_order_id,
                            ticker=ticker,
                        )
        except Exception:
            pass

    if budget.remaining(LifecycleOperation.FILLS) > 0 and not deadline.is_expired(monotonic_clock()):
        try:
            budget.reserve(LifecycleOperation.FILLS)
            request = _build_request(
                LifecycleOperation.FILLS,
                method="GET",
                path=f"{_TRADE_API_BASE_PATH}/portfolio/fills",
                query=build_fills_query(order_id=bound_order_id, cursor=""),
                body=None, deadline=deadline, monotonic_clock=monotonic_clock,
            )
            if _validate_prepared_request_contract(
                plan, request, expected_order_id=bound_order_id, expected_cursor=""
            ) is None:
                raw, evidence_halt, disposition = _send_and_validate(
                    transport, request, monotonic_clock=monotonic_clock
                )
                if evidence_halt is None and disposition is SendOutcome.DEFINITIVE_SUCCESS and raw is not None:
                    page_fills, _cursor, parse_halt = _parse_fills_page(raw)
                    if parse_halt is None and page_fills is not None:
                        for raw_fill in page_fills:
                            ledger.ingest(raw_fill, bound_order_id=bound_order_id, ticker=ticker)
        except Exception:
            pass
