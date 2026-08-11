"""Offline-safe Kalshi Demo post-halt exact write-result reconciliation.

This module implements the bounded, read-only reconciliation contract for the
single unresolved Execution-01 CREATE result.  It performs no network I/O of
its own.  Every venue observation crosses a caller-supplied ``GET``-only
transport boundary, and every request path/query is generated internally from
a closed six-operation set.

The central safety invariant is intentionally conservative: complete live and
historical enumeration with zero exact ``client_order_id`` matches does *not*
prove that the earlier CREATE never existed.  Zero-match therefore remains an
unresolved write result and never releases the writer proof.

No function in this module loads environment variables, credentials, private
keys, account data, or auth headers.  The only signing helper builds the
secret-free Kalshi signing message for an internally validated prepared GET;
actual key handling belongs to a separately authorized caller/transport.

All quantity, price, fee, and risk arithmetic uses :class:`decimal.Decimal`.
Binary floating point is not used for monetary or quantity logic.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Protocol, Sequence, Tuple


# ---------------------------------------------------------------------------
# Frozen task / incident / source identities
# ---------------------------------------------------------------------------

REPOSITORY = "rigolugo/ARB"
REQUIRED_BASE = "c2fc896ace102edc0f59450160f90000fc9be7f1"
REQUIRED_TREE = "a69fb6f0cbf07c1e77bce81edd48a5ba9467d8ff"

SPECIFICATION_FILENAME = "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_SPEC_01.md"
SPECIFICATION_BYTES = 69923
SPECIFICATION_SHA256 = "61fd39b87d8b837e1a16b2b21cd133614f2607a3c21130682b53ace6ac4715e7"
HANDOFF_FILENAME = "HANDOFF_KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_SPEC_01.md"
HANDOFF_BYTES = 17704
HANDOFF_SHA256 = "ce6d3ef37339d118a0a390c69432833b50cedb3820017dbc66ef443934724a5e"
EXECUTION_EVIDENCE_FILENAME = "execution_evidence.json"
EXECUTION_EVIDENCE_BYTES = 10746
EXECUTION_EVIDENCE_SHA256 = "2cb1677d06d3c88a3dd6f5b41190fa6de237bae24f02457fee37b2e0d04eefac"

ACCEPTED_LIFECYCLE_SPEC_BYTES = 101724
ACCEPTED_LIFECYCLE_SPEC_SHA256 = "bb8355ad0022cda0d5ce936ed84993a381028187f207ae4b402f8017c9fbd101"
ACCEPTED_LIFECYCLE_IMPLEMENTATION_PATH = "src/arb/venues/kalshi/order_lifecycle.py"
ACCEPTED_LIFECYCLE_IMPLEMENTATION_BYTES = 181815
ACCEPTED_LIFECYCLE_IMPLEMENTATION_SHA256 = "7ea14d6c4e90f1447eb33ee0df1b04cdb598723f06928eb6077d8449bbf1d133"
ACCEPTED_LIFECYCLE_IMPLEMENTATION_BLOB = "0d36a116458469d1436ceed55018c90c9e876a02"

ENVIRONMENT = "KALSHI_DEMO"
DEMO_REST_ORIGIN = "https://external-api.demo.kalshi.co"
DEMO_REST_PORT = 443
TRADE_API_BASE_PATH = "/trade-api/v2"
ACCOUNT_SCOPE_REF = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
SUBACCOUNT = 0
EXCHANGE_INDEX = 0
TICKER = "KXFEDDECISION-26SEP-H0"
CLIENT_ORDER_ID = "2e64d452-2cc2-43fa-a976-e8f996192252"
WRITER_PROOF_ID = "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_WRITER_PROOF"

ECONOMIC_MEANING = "buy YES"
OUTCOME_SIDE = "yes"
BOOK_SIDE = "bid"
INITIAL_QUANTITY = Decimal("1.00")
LIMIT_PRICE = Decimal("0.0100")
TIME_IN_FORCE = "good_till_canceled"
POST_ONLY = True
CANCEL_ORDER_ON_PAUSE = True
REDUCE_ONLY = False
SELF_TRADE_PREVENTION_TYPE = "taker_at_cross"
MAX_FILLED_PRINCIPAL = Decimal("0.010000")
MAX_FEE_COST = Decimal("0.040000")
MAX_TOTAL_RISK = Decimal("0.050000")

PAGE_LIMIT = 1000
MAX_LIVE_ORDER_PAGES = 8
MAX_HISTORICAL_ORDER_PAGES = 8
MAX_LIVE_FILL_PAGES = 8
MAX_HISTORICAL_FILL_PAGES = 8
GLOBAL_GET_SEND_MAXIMUM = 34
HTTP_RETRIES = 0
REDIRECTS_FOLLOWED = 0
MASTER_DEADLINE_MS = 180_000
PER_REQUEST_CEILING_MS = 10_000

SOURCE_BINDING_MANIFEST_BYTES = b'{"authentication":{"authenticated_headers":["KALSHI-ACCESS-KEY","KALSHI-ACCESS-TIMESTAMP","KALSHI-ACCESS-SIGNATURE"],"signature":"RSA-PSS with SHA-256 over timestamp + HTTP_METHOD + path_without_query","url":"https://docs.kalshi.com/getting_started/quick_start_authenticated_requests"},"binding_manifest_id":"KALSHI_POST_HALT_RECONCILIATION_CURRENT_OFFICIAL_SOURCE_BINDING_2026-08-11","demo_environment":{"credentials_shared_between_demo_and_production":false,"demo_rest_root":"https://external-api.demo.kalshi.co/trade-api/v2","production_rest_root":"https://external-api.kalshi.com/trade-api/v2","signing_path_excludes_hostname_and_query":true,"url":"https://docs.kalshi.com/getting_started/api_environments"},"direction":{"canonical_fields":["outcome_side","book_side"],"equivalence":{"ask":"no","bid":"yes"},"legacy_fields":["action","side"],"legacy_status":"deprecated; not required by this specification","url":"https://docs.kalshi.com/getting_started/order_direction"},"fixed_point":{"count_fp":"string; responses emit 2 decimal places; 0.01 contract granularity","dollars":"fixed-point decimal strings; documented generally up to 4 decimal places","intermediate_calculation_precision":"may reach 6 decimal places","portfolio_dollars_note":"API changelog 2026-03-07 states selected portfolio _dollars response fields may emit up to 6 decimal places","url":"https://docs.kalshi.com/getting_started/fixed_point_migration"},"historical_partition":{"combine_live_and_historical_when_complete_history_needed":true,"fills_cutoff_field":"trades_created_ts","orders_cutoff_field":"orders_updated_ts","url":"https://docs.kalshi.com/getting_started/historical_data"},"negative_closure":{"reviewed_source_set_proves_read_after_write_negative_closure":false,"rule":"zero exact client_order_id matches must remain unresolved"},"observed_at_utc":"2026-08-11T10:40:38Z","official_source_scope":"docs.kalshi.com only","openapi_locator_observation":{"content_type":"text/yaml","future_implementation_acceptance":"must freshly materialize and hash the raw OpenAPI before implementation acceptance if exact raw-source binding is required","http_status":200,"raw_bytes_materialized":false,"raw_sha256":null,"reason":"available retrieval tool rejected text/yaml materialization; no raw hash is asserted","reported_content_length_bytes":323714,"url":"https://docs.kalshi.com/openapi.yaml"},"operations":{"EXACT_ORDER":{"authentication_required":true,"direction_fields":["outcome_side","book_side"],"method":"GET","order_economic_fields":["yes_price_dollars","no_price_dollars","cancel_order_on_pause"],"order_identity_fields":["order_id","client_order_id","ticker","subaccount_number"],"order_state_fields":["status","initial_count_fp","fill_count_fp","remaining_count_fp"],"path":"/trade-api/v2/portfolio/orders/{order_id}","path_parameters":["order_id"],"query_parameters":[],"response_required":["order"],"url":"https://docs.kalshi.com/api-reference/orders/get-order"},"HISTORICAL_CUTOFF":{"authentication_required":false,"method":"GET","pagination":false,"path":"/trade-api/v2/historical/cutoff","query_parameters":[],"response_required":["market_settled_ts","trades_created_ts","orders_updated_ts"],"url":"https://docs.kalshi.com/api-reference/historical/get-historical-cutoff-timestamps"},"HISTORICAL_FILLS":{"authentication_required":true,"direction_fields":["outcome_side","book_side"],"fill_fields":["fill_id","trade_id","order_id","ticker","market_ticker","count_fp","yes_price_dollars","no_price_dollars","is_taker","fee_cost","created_time","subaccount_number","ts"],"limit_range":[1,1000],"method":"GET","pagination":true,"path":"/trade-api/v2/historical/fills","query_parameters":["ticker","max_ts","limit","cursor"],"response_required":["fills","cursor"],"server_side_order_id_filter":false,"server_side_subaccount_filter":false,"task_query":{"limit":1000,"max_ts":"OMITTED","ticker":"KXFEDDECISION-26SEP-H0"},"url":"https://docs.kalshi.com/api-reference/historical/get-historical-fills"},"HISTORICAL_ORDERS":{"authentication_required":true,"direction_fields":["outcome_side","book_side"],"limit_range":[1,1000],"method":"GET","order_economic_fields":["yes_price_dollars","no_price_dollars","cancel_order_on_pause"],"order_identity_fields":["order_id","client_order_id","ticker","subaccount_number"],"order_state_fields":["status","initial_count_fp","fill_count_fp","remaining_count_fp"],"pagination":true,"path":"/trade-api/v2/historical/orders","query_parameters":["ticker","max_ts","limit","cursor"],"response_required":["orders","cursor"],"server_side_subaccount_filter":false,"task_query":{"limit":1000,"max_ts":"OMITTED","ticker":"KXFEDDECISION-26SEP-H0"},"url":"https://docs.kalshi.com/api-reference/historical/get-historical-orders"},"LIVE_FILLS":{"authentication_required":true,"direction_fields":["outcome_side","book_side"],"fill_fields":["fill_id","trade_id","order_id","ticker","market_ticker","count_fp","yes_price_dollars","no_price_dollars","is_taker","fee_cost","created_time","subaccount_number","ts"],"limit_range":[1,1000],"method":"GET","pagination":true,"partition_rule":"fills before trades_created_ts only historical","path":"/trade-api/v2/portfolio/fills","query_parameters":["ticker","order_id","min_ts","max_ts","limit","cursor","subaccount"],"response_required":["fills","cursor"],"task_query":{"limit":1000,"max_ts":"OMITTED","min_ts":"OMITTED","order_id":"<bound_order_id>","subaccount":0,"ticker":"KXFEDDECISION-26SEP-H0"},"url":"https://docs.kalshi.com/api-reference/portfolio/get-fills"},"LIVE_ORDERS":{"authentication_required":true,"direction_fields":["outcome_side","book_side"],"limit_range":[1,1000],"method":"GET","order_economic_fields":["yes_price_dollars","no_price_dollars","cancel_order_on_pause"],"order_identity_fields":["order_id","client_order_id","ticker","subaccount_number"],"order_state_fields":["status","initial_count_fp","fill_count_fp","remaining_count_fp"],"pagination":true,"partition_rule":"resting orders always live; canceled/fully executed before orders_updated_ts only historical","path":"/trade-api/v2/portfolio/orders","query_parameters":["ticker","event_ticker","min_ts","max_ts","status","limit","cursor","subaccount"],"response_required":["orders","cursor"],"task_query":{"event_ticker":"OMITTED","limit":1000,"max_ts":"OMITTED","min_ts":"OMITTED","status":"OMITTED","subaccount":0,"ticker":"KXFEDDECISION-26SEP-H0"},"url":"https://docs.kalshi.com/api-reference/orders/get-orders"}}}'
SOURCE_BINDING_MANIFEST_LENGTH = 6451
SOURCE_BINDING_MANIFEST_SHA256 = "499c10e0ab743b6e532df62e88e7d2a6ee6c7d5f13798575ff5e816b0ae3df78"

OPERATION_BINDING_IDENTITIES: Mapping[str, Tuple[int, str]] = MappingProxyType({
    "HISTORICAL_CUTOFF": (302, "2cf1380ef5728d02f2034524b9b9afac9ad0aaf39f25715f569d0814c46a738e"),
    "LIVE_ORDERS": (914, "32b9c640f6062db9c1f9543952c8700cc15aecd01b587235cca02179109e8780"),
    "HISTORICAL_ORDERS": (732, "71edfa60c609b7b0157add61be2be9f0ae80aeb7e557fca45aca4587193d0b40"),
    "EXACT_ORDER": (553, "e135f411f0fab6e59755b2852995a597b206ec482d33a0f9c7d28e6af9b7ef0c"),
    "LIVE_FILLS": (765, "890ba8d6e0e7b03a2983b3bb7eb0836ce48c45e641bf8c39d14f5df9d0ca893c"),
    "HISTORICAL_FILLS": (689, "b5d13819cf1b8f0f0467df3c3d9893020301d8eb551d4060459d710db71d9188"),
})

_REQUIRED_CREDENTIAL_REFERENCES = (
    "KALSHI_DEMO_API_KEY_ID",
    "KALSHI_DEMO_PRIVATE_KEY_PEM",
)
_SUPPORTED_ORDER_STATUSES = frozenset({"resting", "canceled", "executed"})


# ---------------------------------------------------------------------------
# Closed public types
# ---------------------------------------------------------------------------

class CapabilityState(enum.StrEnum):
    PERMITTED = "PERMITTED"
    PROHIBITED = "PROHIBITED"


class AuthenticationClass(enum.StrEnum):
    PUBLIC = "PUBLIC"
    AUTHENTICATED = "AUTHENTICATED"


class ReconciliationCapabilityName(enum.StrEnum):
    """Exact future-execution capabilities from RECON-CAP-003.

    These are independent operation capabilities.  Possessing any one of
    them, including credential use, never implies another.
    """

    HISTORICAL_CUTOFF_READ = "KALSHI_DEMO_PUBLIC_HISTORICAL_CUTOFF_READ"
    LIVE_ORDER_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_LIVE_ORDER_LIST_READ"
    HISTORICAL_ORDER_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_HISTORICAL_ORDER_LIST_READ"
    EXACT_ORDER_READ = "KALSHI_DEMO_AUTHENTICATED_EXACT_ORDER_READ"
    LIVE_FILL_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_LIVE_FILL_LIST_READ"
    HISTORICAL_FILL_LIST_READ = "KALSHI_DEMO_AUTHENTICATED_HISTORICAL_FILL_LIST_READ"
    CREDENTIAL_USE = "KALSHI_DEMO_CREDENTIAL_USE_FOR_THE_FIVE_AUTHENTICATED_GET_FAMILIES"


REQUIRED_RECONCILIATION_CAPABILITIES: FrozenSet[ReconciliationCapabilityName] = (
    frozenset(ReconciliationCapabilityName)
)


class ReconciliationOperation(enum.StrEnum):
    HISTORICAL_CUTOFF = "HISTORICAL_CUTOFF"
    LIVE_ORDERS = "LIVE_ORDERS"
    HISTORICAL_ORDERS = "HISTORICAL_ORDERS"
    EXACT_ORDER = "EXACT_ORDER"
    LIVE_FILLS = "LIVE_FILLS"
    HISTORICAL_FILLS = "HISTORICAL_FILLS"


class ResultClass(enum.StrEnum):
    WRITE_RECONCILED_ORDER_EXISTS_ACTIVE = "WRITE_RECONCILED_ORDER_EXISTS_ACTIVE"
    WRITE_RECONCILED_ORDER_EXISTS_TERMINAL = "WRITE_RECONCILED_ORDER_EXISTS_TERMINAL"
    WRITE_UNRESOLVED_ZERO_MATCH = "WRITE_UNRESOLVED_ZERO_MATCH"
    WRITE_UNRESOLVED_IDENTITY_VIOLATION = "WRITE_UNRESOLVED_IDENTITY_VIOLATION"
    WRITE_UNRESOLVED_READ_FAILURE = "WRITE_UNRESOLVED_READ_FAILURE"


class HaltCode(enum.StrEnum):
    CANONICAL_BASE_MISMATCH = "CANONICAL_BASE_MISMATCH"
    CONTROLLING_ARTIFACT_IDENTITY_MISMATCH = "CONTROLLING_ARTIFACT_IDENTITY_MISMATCH"
    TASK_CURRENT_SOURCE_UNAVAILABLE = "TASK_CURRENT_SOURCE_UNAVAILABLE"
    AUTHORITATIVE_SCHEMA_DRIFT = "AUTHORITATIVE_SCHEMA_DRIFT"
    DEMO_ENVIRONMENT_REQUIRED = "DEMO_ENVIRONMENT_REQUIRED"
    PRODUCTION_ENDPOINT_PROHIBITED = "PRODUCTION_ENDPOINT_PROHIBITED"
    GET_ONLY_CONTRACT_VIOLATION = "GET_ONLY_CONTRACT_VIOLATION"
    CAPABILITY_MISSING = "CAPABILITY_MISSING"
    SECRET_BOUNDARY_VIOLATION = "SECRET_BOUNDARY_VIOLATION"

    CUTOFF_RESPONSE_INVALID = "CUTOFF_RESPONSE_INVALID"
    PAGINATION_CURSOR_MALFORMED = "PAGINATION_CURSOR_MALFORMED"
    PAGINATION_CURSOR_CYCLE = "PAGINATION_CURSOR_CYCLE"
    PAGE_BUDGET_EXHAUSTED = "PAGE_BUDGET_EXHAUSTED"
    GLOBAL_REQUEST_BUDGET_EXHAUSTED = "GLOBAL_REQUEST_BUDGET_EXHAUSTED"
    MASTER_DEADLINE_EXHAUSTED = "MASTER_DEADLINE_EXHAUSTED"
    TRANSPORT_READ_FAILURE = "TRANSPORT_READ_FAILURE"
    UNEXPECTED_HTTP_STATUS = "UNEXPECTED_HTTP_STATUS"
    REDIRECT_PROHIBITED = "REDIRECT_PROHIBITED"

    ORDER_REQUIRED_FIELD_MISSING = "ORDER_REQUIRED_FIELD_MISSING"
    ORDER_ID_DUPLICATE_CONFLICT = "ORDER_ID_DUPLICATE_CONFLICT"
    MULTIPLE_ORDER_IDS_FOR_CLIENT_ORDER_ID = "MULTIPLE_ORDER_IDS_FOR_CLIENT_ORDER_ID"
    ORDER_IDENTITY_OR_ECONOMIC_MISMATCH = "ORDER_IDENTITY_OR_ECONOMIC_MISMATCH"
    ORDER_STATE_CHANGED_DURING_RECONCILIATION = "ORDER_STATE_CHANGED_DURING_RECONCILIATION"
    SOURCE_PARTITION_CONFLICT = "SOURCE_PARTITION_CONFLICT"
    UNSUPPORTED_ORDER_STATUS = "UNSUPPORTED_ORDER_STATUS"

    FILL_REQUIRED_FIELD_MISSING = "FILL_REQUIRED_FIELD_MISSING"
    FILL_WRONG_ORDER = "FILL_WRONG_ORDER"
    FILL_SCOPE_MISMATCH = "FILL_SCOPE_MISMATCH"
    FILL_ID_DUPLICATE_CONFLICT = "FILL_ID_DUPLICATE_CONFLICT"
    FILL_PRICE_WORSE_THAN_LIMIT = "FILL_PRICE_WORSE_THAN_LIMIT"
    POST_ONLY_TAKER_FILL_CONFLICT = "POST_ONLY_TAKER_FILL_CONFLICT"
    FILLED_PRINCIPAL_EXCEEDS_LIMIT = "FILLED_PRINCIPAL_EXCEEDS_LIMIT"
    FEE_RISK_EXCEEDS_LIMIT = "FEE_RISK_EXCEEDS_LIMIT"
    TOTAL_RISK_EXCEEDS_LIMIT = "TOTAL_RISK_EXCEEDS_LIMIT"
    OVERFILL = "OVERFILL"
    FILL_ORDER_RECONCILIATION_MISMATCH = "FILL_ORDER_RECONCILIATION_MISMATCH"
    ORDER_FILL_ARITHMETIC_NOT_PROVEN = "ORDER_FILL_ARITHMETIC_NOT_PROVEN"


_IDENTITY_VIOLATION_CODES: FrozenSet[HaltCode] = frozenset({
    HaltCode.ORDER_ID_DUPLICATE_CONFLICT,
    HaltCode.MULTIPLE_ORDER_IDS_FOR_CLIENT_ORDER_ID,
    HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH,
    HaltCode.FILL_WRONG_ORDER,
    HaltCode.FILL_SCOPE_MISMATCH,
    HaltCode.FILL_ID_DUPLICATE_CONFLICT,
    HaltCode.FILL_PRICE_WORSE_THAN_LIMIT,
    HaltCode.POST_ONLY_TAKER_FILL_CONFLICT,
    HaltCode.FILLED_PRINCIPAL_EXCEEDS_LIMIT,
    HaltCode.FEE_RISK_EXCEEDS_LIMIT,
    HaltCode.TOTAL_RISK_EXCEEDS_LIMIT,
    HaltCode.OVERFILL,
})


@dataclass(frozen=True, slots=True)
class ReconciliationCapabilityEnvelope:
    """Non-secret, closed future-execution capability declaration.

    Credential *reference names* are metadata only.  Their presence never
    grants a read; the explicit capability states below remain load-bearing.
    """

    environment: str
    rest_origin: str
    credential_reference_names: Tuple[str, ...]
    granted_capabilities: FrozenSet[ReconciliationCapabilityName]
    network_access: CapabilityState
    demo_public_reads: CapabilityState
    demo_authenticated_reads: CapabilityState
    credential_use: CapabilityState
    demo_writes: CapabilityState
    production_public_reads: CapabilityState
    production_authenticated_reads: CapabilityState
    production_writes: CapabilityState
    account_funding: CapabilityState
    websocket: CapabilityState


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    path: str
    bytes: int
    sha256: str
    git_blob: str


@dataclass(frozen=True, slots=True)
class ReconciliationProvenance:
    implementation: ArtifactIdentity
    tests: ArtifactIdentity
    source_raw_openapi_bytes: Optional[int] = None
    source_raw_openapi_sha256: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ReconciliationInput:
    capability_envelope: ReconciliationCapabilityEnvelope
    source_binding_manifest_bytes: bytes
    provenance: ReconciliationProvenance


@dataclass(frozen=True, slots=True)
class ReconciliationPlan:
    """Secret-free closed plan.  The executor replans internally under its
    master deadline rather than trusting a precomputed public plan."""

    environment: str
    origin: str
    base_path: str
    operations: Tuple[ReconciliationOperation, ...]
    source_binding_sha256: str
    ticker: str
    client_order_id: str


class ReconciliationPlanningError(ValueError):
    def __init__(self, halt_code: HaltCode):
        super().__init__(halt_code.value)
        self.halt_code = halt_code


@dataclass(frozen=True, slots=True)
class PreparedGetRequest:
    """Internally generated request.  No method/body/header/url parameter
    exists on the public executor; method is a read-only literal property."""

    operation: ReconciliationOperation
    origin: str
    path: str
    query: Mapping[str, object]
    authentication_class: AuthenticationClass
    page_ordinal: int
    effective_deadline_monotonic: float

    @property
    def method(self) -> str:
        return "GET"


@dataclass(frozen=True, slots=True)
class RawHttpResponse:
    status: int
    media_type: str
    body_bytes: bytes
    retry_count: int
    redirect_count: int


class ReconciliationTransport(Protocol):
    def send(self, request: PreparedGetRequest) -> RawHttpResponse: ...


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    result_class: ResultClass
    halt_code: Optional[HaltCode]
    bound_order_id: Optional[str]
    created_order_upper_bound: int
    active_order_upper_bound: int
    unknown_result: bool
    writer_proof_release_eligible: bool
    exact_client_order_id_match_count: int
    canonical_fill_count: int
    canonical_fill_quantity: Optional[Decimal]
    canonical_filled_principal: Optional[Decimal]
    canonical_fee_cost: Optional[Decimal]
    request_count: int
    retry_count: int
    redirect_count: int
    production_activity: int
    write_activity: int
    funding_activity: int
    websocket_activity: int
    evidence_json: bytes
    evidence_sha256: str


# ---------------------------------------------------------------------------
# Internal closed operation contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _OperationSpec:
    operation: ReconciliationOperation
    path_template: str
    authentication_class: AuthenticationClass
    paginated: bool
    page_budget: int


_OPERATION_SPECS: Mapping[ReconciliationOperation, _OperationSpec] = MappingProxyType({
    ReconciliationOperation.HISTORICAL_CUTOFF: _OperationSpec(
        ReconciliationOperation.HISTORICAL_CUTOFF,
        "/trade-api/v2/historical/cutoff",
        AuthenticationClass.PUBLIC,
        False,
        1,
    ),
    ReconciliationOperation.LIVE_ORDERS: _OperationSpec(
        ReconciliationOperation.LIVE_ORDERS,
        "/trade-api/v2/portfolio/orders",
        AuthenticationClass.AUTHENTICATED,
        True,
        MAX_LIVE_ORDER_PAGES,
    ),
    ReconciliationOperation.HISTORICAL_ORDERS: _OperationSpec(
        ReconciliationOperation.HISTORICAL_ORDERS,
        "/trade-api/v2/historical/orders",
        AuthenticationClass.AUTHENTICATED,
        True,
        MAX_HISTORICAL_ORDER_PAGES,
    ),
    ReconciliationOperation.EXACT_ORDER: _OperationSpec(
        ReconciliationOperation.EXACT_ORDER,
        "/trade-api/v2/portfolio/orders/{order_id}",
        AuthenticationClass.AUTHENTICATED,
        False,
        1,
    ),
    ReconciliationOperation.LIVE_FILLS: _OperationSpec(
        ReconciliationOperation.LIVE_FILLS,
        "/trade-api/v2/portfolio/fills",
        AuthenticationClass.AUTHENTICATED,
        True,
        MAX_LIVE_FILL_PAGES,
    ),
    ReconciliationOperation.HISTORICAL_FILLS: _OperationSpec(
        ReconciliationOperation.HISTORICAL_FILLS,
        "/trade-api/v2/historical/fills",
        AuthenticationClass.AUTHENTICATED,
        True,
        MAX_HISTORICAL_FILL_PAGES,
    ),
})

_OPERATION_ORDER = (
    ReconciliationOperation.HISTORICAL_CUTOFF,
    ReconciliationOperation.LIVE_ORDERS,
    ReconciliationOperation.HISTORICAL_ORDERS,
    ReconciliationOperation.EXACT_ORDER,
    ReconciliationOperation.LIVE_FILLS,
    ReconciliationOperation.HISTORICAL_FILLS,
)


# ---------------------------------------------------------------------------
# Strict parsing / canonicalization
# ---------------------------------------------------------------------------

_COUNT_PATTERN = re.compile(r"[0-9]+\.[0-9]{2}")
_MONEY_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]{1,6})?")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_BLOB_PATTERN = re.compile(r"[0-9a-f]{40}")
_RFC3339_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)


class _DuplicateJsonKey(ValueError):
    pass


class _NonFiniteJson(ValueError):
    pass


def _pairs_no_duplicates(pairs: Sequence[Tuple[str, object]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> object:
    raise _NonFiniteJson(token)


def _strict_json_loads(raw: bytes) -> object:
    if type(raw) is not bytes:
        raise ValueError("response body must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("response is not UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, _DuplicateJsonKey, _NonFiniteJson) as exc:
        raise ValueError("invalid strict JSON") from exc


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_count(value: object) -> Decimal:
    if type(value) is not str or _COUNT_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid fixed-point count")
    return Decimal(value)


def _parse_money(value: object) -> Decimal:
    if type(value) is not str or _MONEY_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid fixed-point monetary value")
    return Decimal(value)


def _opaque_identifier(value: object) -> str:
    if type(value) is not str or value == "":
        raise ValueError("invalid opaque identifier")
    return value


def _exact_int(value: object) -> int:
    if type(value) is not int:
        raise ValueError("integer required")
    return value


def _exact_bool(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("boolean required")
    return value


def _valid_rfc3339(value: object) -> bool:
    if type(value) is not str or _RFC3339_PATTERN.fullmatch(value) is None:
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def _json_safe(value: object) -> object:
    if isinstance(value, enum.Enum):
        return value.value
    if type(value) is Decimal:
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [_json_safe(v) for v in sorted(value, key=lambda item: repr(item))]
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError("unsupported evidence value")


# ---------------------------------------------------------------------------
# Source/capability/provenance validation
# ---------------------------------------------------------------------------

def validate_source_binding_manifest(raw: object) -> Optional[HaltCode]:
    if type(raw) is not bytes or len(raw) == 0:
        return HaltCode.TASK_CURRENT_SOURCE_UNAVAILABLE
    if len(raw) != SOURCE_BINDING_MANIFEST_LENGTH or _sha256(raw) != SOURCE_BINDING_MANIFEST_SHA256:
        return HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    if raw != SOURCE_BINDING_MANIFEST_BYTES:
        return HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    try:
        parsed = _strict_json_loads(raw)
    except ValueError:
        return HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    if type(parsed) is not dict:
        return HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    operations = parsed.get("operations")
    if type(operations) is not dict or set(operations) != set(OPERATION_BINDING_IDENTITIES):
        return HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    for name, (expected_bytes, expected_sha) in OPERATION_BINDING_IDENTITIES.items():
        operation_bytes = _canonical_json_bytes(operations[name])
        if len(operation_bytes) != expected_bytes or _sha256(operation_bytes) != expected_sha:
            return HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
        operation = operations[name]
        if type(operation) is not dict or operation.get("method") != "GET":
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    return None


def _validate_artifact_identity(identity: object) -> bool:
    return (
        type(identity) is ArtifactIdentity
        and type(identity.path) is str
        and identity.path != ""
        and type(identity.bytes) is int
        and identity.bytes >= 0
        and type(identity.sha256) is str
        and _SHA256_PATTERN.fullmatch(identity.sha256) is not None
        and type(identity.git_blob) is str
        and _BLOB_PATTERN.fullmatch(identity.git_blob) is not None
    )


def _validate_capability(envelope: object) -> Optional[HaltCode]:
    if type(envelope) is not ReconciliationCapabilityEnvelope:
        return HaltCode.CAPABILITY_MISSING
    if envelope.environment != ENVIRONMENT:
        return HaltCode.DEMO_ENVIRONMENT_REQUIRED
    if type(envelope.rest_origin) is not str:
        return HaltCode.DEMO_ENVIRONMENT_REQUIRED
    if envelope.rest_origin == "https://external-api.kalshi.com":
        return HaltCode.PRODUCTION_ENDPOINT_PROHIBITED
    if envelope.rest_origin != DEMO_REST_ORIGIN:
        return HaltCode.DEMO_ENVIRONMENT_REQUIRED
    if type(envelope.credential_reference_names) is not tuple:
        return HaltCode.SECRET_BOUNDARY_VIOLATION
    if envelope.credential_reference_names != _REQUIRED_CREDENTIAL_REFERENCES:
        return HaltCode.SECRET_BOUNDARY_VIOLATION
    if type(envelope.granted_capabilities) is not frozenset:
        return HaltCode.CAPABILITY_MISSING
    if any(type(capability) is not ReconciliationCapabilityName for capability in envelope.granted_capabilities):
        return HaltCode.CAPABILITY_MISSING
    # Every RECON-CAP-003 capability is independently required.  There is
    # no inheritance from authenticated-read, public-read, network access,
    # or credential presence.
    if envelope.granted_capabilities != REQUIRED_RECONCILIATION_CAPABILITIES:
        return HaltCode.CAPABILITY_MISSING

    required_permitted = (
        envelope.network_access,
        envelope.demo_public_reads,
        envelope.demo_authenticated_reads,
        envelope.credential_use,
    )
    if any(type(v) is not CapabilityState or v is not CapabilityState.PERMITTED for v in required_permitted):
        return HaltCode.CAPABILITY_MISSING

    required_prohibited = (
        envelope.demo_writes,
        envelope.production_public_reads,
        envelope.production_authenticated_reads,
        envelope.production_writes,
        envelope.account_funding,
        envelope.websocket,
    )
    if any(type(v) is not CapabilityState or v is not CapabilityState.PROHIBITED for v in required_prohibited):
        return HaltCode.CAPABILITY_MISSING
    return None


def _validate_input(reconciliation_input: object) -> Optional[HaltCode]:
    if type(reconciliation_input) is not ReconciliationInput:
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    cap_halt = _validate_capability(reconciliation_input.capability_envelope)
    if cap_halt is not None:
        return cap_halt
    source_halt = validate_source_binding_manifest(reconciliation_input.source_binding_manifest_bytes)
    if source_halt is not None:
        return source_halt
    provenance = reconciliation_input.provenance
    if type(provenance) is not ReconciliationProvenance:
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    if not _validate_artifact_identity(provenance.implementation):
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    if not _validate_artifact_identity(provenance.tests):
        return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    if provenance.source_raw_openapi_bytes is None:
        if provenance.source_raw_openapi_sha256 is not None:
            return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    else:
        if type(provenance.source_raw_openapi_bytes) is not int or provenance.source_raw_openapi_bytes <= 0:
            return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
        if (
            type(provenance.source_raw_openapi_sha256) is not str
            or _SHA256_PATTERN.fullmatch(provenance.source_raw_openapi_sha256) is None
        ):
            return HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH
    return None


def plan_post_halt_reconciliation(reconciliation_input: ReconciliationInput) -> ReconciliationPlan:
    halt = _validate_input(reconciliation_input)
    if halt is not None:
        raise ReconciliationPlanningError(halt)
    return ReconciliationPlan(
        environment=ENVIRONMENT,
        origin=DEMO_REST_ORIGIN,
        base_path=TRADE_API_BASE_PATH,
        operations=_OPERATION_ORDER,
        source_binding_sha256=SOURCE_BINDING_MANIFEST_SHA256,
        ticker=TICKER,
        client_order_id=CLIENT_ORDER_ID,
    )


# ---------------------------------------------------------------------------
# Secret-free GET signing message
# ---------------------------------------------------------------------------

_TIMESTAMP_MS_PATTERN = re.compile(r"[0-9]+")


def build_prepared_get_signing_message(
    request: PreparedGetRequest,
    *,
    timestamp_ms_text: str,
) -> bytes:
    """Return ``timestamp + GET + path_without_query`` for a validated
    internally shaped request.  No key/signature/header value is accepted or
    returned by this helper.
    """

    if type(request) is not PreparedGetRequest or _validate_prepared_request(request) is not None:
        raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
    if type(timestamp_ms_text) is not str or _TIMESTAMP_MS_PATTERN.fullmatch(timestamp_ms_text) is None:
        raise ValueError("timestamp_ms_text must be canonical ASCII digits")
    return (timestamp_ms_text + "GET" + request.path).encode("utf-8")


# ---------------------------------------------------------------------------
# Parsed order/fill records and provenance
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _Observation:
    source_stream: str
    page_ordinal: int
    record_ordinal: int
    response_sha256: str


@dataclass(frozen=True, slots=True)
class _OrderRecord:
    order_id: str
    client_order_id: str
    ticker: str
    subaccount_number: int
    outcome_side: str
    book_side: str
    yes_price_dollars: Decimal
    no_price_dollars: Decimal
    cancel_order_on_pause: bool
    status: str
    initial_count_fp: Decimal
    fill_count_fp: Decimal
    remaining_count_fp: Decimal
    self_trade_prevention_type: Optional[str]
    post_only: Optional[bool]
    time_in_force: Optional[str]
    reduce_only: Optional[bool]
    exchange_index: Optional[int]
    legacy_action: Optional[str]
    legacy_side: Optional[str]
    observations: Tuple[_Observation, ...]
    raw_authoritative: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _FillRecord:
    fill_id: str
    trade_id: str
    order_id: str
    ticker: str
    market_ticker: Optional[str]
    subaccount_number: int
    outcome_side: str
    book_side: str
    count_fp: Decimal
    yes_price_dollars: Decimal
    no_price_dollars: Decimal
    is_taker: bool
    fee_cost: Decimal
    created_time: Optional[object]
    ts: Optional[object]
    observations: Tuple[_Observation, ...]
    raw_authoritative: Mapping[str, object]


_ORDER_REQUIRED = (
    "order_id",
    "client_order_id",
    "ticker",
    "subaccount_number",
    "outcome_side",
    "book_side",
    "yes_price_dollars",
    "no_price_dollars",
    "cancel_order_on_pause",
    "status",
    "initial_count_fp",
    "fill_count_fp",
    "remaining_count_fp",
)

_FILL_REQUIRED = (
    "fill_id",
    "trade_id",
    "order_id",
    "ticker",
    "subaccount_number",
    "outcome_side",
    "book_side",
    "count_fp",
    "yes_price_dollars",
    "no_price_dollars",
    "is_taker",
    "fee_cost",
)

_ORDER_AUTHORITATIVE_FIELDS = frozenset(_ORDER_REQUIRED + (
    "self_trade_prevention_type",
    "post_only",
    "time_in_force",
    "reduce_only",
    "exchange_index",
    "action",
    "side",
))

_FILL_AUTHORITATIVE_FIELDS = frozenset(_FILL_REQUIRED + (
    "market_ticker",
    "created_time",
    "ts",
))


def _parse_order(
    raw: object,
    *,
    observation: _Observation,
) -> Tuple[Optional[_OrderRecord], Optional[HaltCode]]:
    if type(raw) is not dict:
        return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    for field_name in _ORDER_REQUIRED:
        if field_name not in raw:
            return None, HaltCode.ORDER_REQUIRED_FIELD_MISSING
    try:
        order_id = _opaque_identifier(raw["order_id"])
        client_order_id = _opaque_identifier(raw["client_order_id"])
        ticker = _opaque_identifier(raw["ticker"])
        subaccount = _exact_int(raw["subaccount_number"])
        outcome_side = _opaque_identifier(raw["outcome_side"])
        book_side = _opaque_identifier(raw["book_side"])
        yes_price = _parse_money(raw["yes_price_dollars"])
        no_price = _parse_money(raw["no_price_dollars"])
        cancel_on_pause = _exact_bool(raw["cancel_order_on_pause"])
        status = _opaque_identifier(raw["status"])
        initial_count = _parse_count(raw["initial_count_fp"])
        fill_count = _parse_count(raw["fill_count_fp"])
        remaining_count = _parse_count(raw["remaining_count_fp"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    if status not in _SUPPORTED_ORDER_STATUSES:
        return None, HaltCode.UNSUPPORTED_ORDER_STATUS

    stp: Optional[str] = None
    post_only: Optional[bool] = None
    tif: Optional[str] = None
    reduce_only: Optional[bool] = None
    exchange_index: Optional[int] = None
    legacy_action: Optional[str] = None
    legacy_side: Optional[str] = None
    try:
        if "self_trade_prevention_type" in raw:
            stp = _opaque_identifier(raw["self_trade_prevention_type"])
        if "post_only" in raw:
            post_only = _exact_bool(raw["post_only"])
        if "time_in_force" in raw:
            tif = _opaque_identifier(raw["time_in_force"])
        if "reduce_only" in raw:
            reduce_only = _exact_bool(raw["reduce_only"])
        if "exchange_index" in raw:
            exchange_index = _exact_int(raw["exchange_index"])
        if "action" in raw:
            legacy_action = _opaque_identifier(raw["action"])
        if "side" in raw:
            legacy_side = _opaque_identifier(raw["side"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT

    authoritative: Dict[str, object] = {}
    for name in _ORDER_AUTHORITATIVE_FIELDS:
        if name not in raw:
            continue
        value = raw[name]
        if name in ("yes_price_dollars", "no_price_dollars"):
            value = _parse_money(value)
        elif name in ("initial_count_fp", "fill_count_fp", "remaining_count_fp"):
            value = _parse_count(value)
        authoritative[name] = value

    return _OrderRecord(
        order_id=order_id,
        client_order_id=client_order_id,
        ticker=ticker,
        subaccount_number=subaccount,
        outcome_side=outcome_side,
        book_side=book_side,
        yes_price_dollars=yes_price,
        no_price_dollars=no_price,
        cancel_order_on_pause=cancel_on_pause,
        status=status,
        initial_count_fp=initial_count,
        fill_count_fp=fill_count,
        remaining_count_fp=remaining_count,
        self_trade_prevention_type=stp,
        post_only=post_only,
        time_in_force=tif,
        reduce_only=reduce_only,
        exchange_index=exchange_index,
        legacy_action=legacy_action,
        legacy_side=legacy_side,
        observations=(observation,),
        raw_authoritative=MappingProxyType(authoritative),
    ), None


def _parse_fill(
    raw: object,
    *,
    observation: _Observation,
) -> Tuple[Optional[_FillRecord], Optional[HaltCode]]:
    if type(raw) is not dict:
        return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    for field_name in _FILL_REQUIRED:
        if field_name not in raw:
            return None, HaltCode.FILL_REQUIRED_FIELD_MISSING
    try:
        fill_id = _opaque_identifier(raw["fill_id"])
        trade_id = _opaque_identifier(raw["trade_id"])
        order_id = _opaque_identifier(raw["order_id"])
        ticker = _opaque_identifier(raw["ticker"])
        subaccount = _exact_int(raw["subaccount_number"])
        outcome_side = _opaque_identifier(raw["outcome_side"])
        book_side = _opaque_identifier(raw["book_side"])
        count = _parse_count(raw["count_fp"])
        yes_price = _parse_money(raw["yes_price_dollars"])
        no_price = _parse_money(raw["no_price_dollars"])
        is_taker = _exact_bool(raw["is_taker"])
        fee_cost = _parse_money(raw["fee_cost"])
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT

    market_ticker: Optional[str] = None
    created_time: Optional[object] = None
    ts: Optional[object] = None
    try:
        if "market_ticker" in raw:
            market_ticker = _opaque_identifier(raw["market_ticker"])
        if "created_time" in raw:
            created_time = raw["created_time"]
            if not _valid_rfc3339(created_time):
                return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
        if "ts" in raw:
            ts = raw["ts"]
            if type(ts) is bool:
                return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
            if type(ts) not in (int, str):
                return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
            if type(ts) is str and not _valid_rfc3339(ts):
                return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    except ValueError:
        return None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT

    authoritative: Dict[str, object] = {}
    for name in _FILL_AUTHORITATIVE_FIELDS:
        if name not in raw:
            continue
        value = raw[name]
        if name == "count_fp":
            value = _parse_count(value)
        elif name in ("yes_price_dollars", "no_price_dollars", "fee_cost"):
            value = _parse_money(value)
        authoritative[name] = value

    return _FillRecord(
        fill_id=fill_id,
        trade_id=trade_id,
        order_id=order_id,
        ticker=ticker,
        market_ticker=market_ticker,
        subaccount_number=subaccount,
        outcome_side=outcome_side,
        book_side=book_side,
        count_fp=count,
        yes_price_dollars=yes_price,
        no_price_dollars=no_price,
        is_taker=is_taker,
        fee_cost=fee_cost,
        created_time=created_time,
        ts=ts,
        observations=(observation,),
        raw_authoritative=MappingProxyType(authoritative),
    ), None


def _common_fields_compatible(a: Mapping[str, object], b: Mapping[str, object]) -> bool:
    for key in set(a).intersection(b):
        if type(a[key]) is not type(b[key]) or a[key] != b[key]:
            return False
    return True


def _merge_order_observations(a: _OrderRecord, b: _OrderRecord) -> _OrderRecord:
    # Field values are compatible on every common authoritative field.
    # The first canonical value remains; provenance is unioned.
    return _OrderRecord(
        order_id=a.order_id,
        client_order_id=a.client_order_id,
        ticker=a.ticker,
        subaccount_number=a.subaccount_number,
        outcome_side=a.outcome_side,
        book_side=a.book_side,
        yes_price_dollars=a.yes_price_dollars,
        no_price_dollars=a.no_price_dollars,
        cancel_order_on_pause=a.cancel_order_on_pause,
        status=a.status,
        initial_count_fp=a.initial_count_fp,
        fill_count_fp=a.fill_count_fp,
        remaining_count_fp=a.remaining_count_fp,
        self_trade_prevention_type=a.self_trade_prevention_type if a.self_trade_prevention_type is not None else b.self_trade_prevention_type,
        post_only=a.post_only if a.post_only is not None else b.post_only,
        time_in_force=a.time_in_force if a.time_in_force is not None else b.time_in_force,
        reduce_only=a.reduce_only if a.reduce_only is not None else b.reduce_only,
        exchange_index=a.exchange_index if a.exchange_index is not None else b.exchange_index,
        legacy_action=a.legacy_action if a.legacy_action is not None else b.legacy_action,
        legacy_side=a.legacy_side if a.legacy_side is not None else b.legacy_side,
        observations=a.observations + b.observations,
        raw_authoritative=MappingProxyType({**dict(b.raw_authoritative), **dict(a.raw_authoritative)}),
    )


def _merge_fill_observations(a: _FillRecord, b: _FillRecord) -> _FillRecord:
    return _FillRecord(
        fill_id=a.fill_id,
        trade_id=a.trade_id,
        order_id=a.order_id,
        ticker=a.ticker,
        market_ticker=a.market_ticker if a.market_ticker is not None else b.market_ticker,
        subaccount_number=a.subaccount_number,
        outcome_side=a.outcome_side,
        book_side=a.book_side,
        count_fp=a.count_fp,
        yes_price_dollars=a.yes_price_dollars,
        no_price_dollars=a.no_price_dollars,
        is_taker=a.is_taker,
        fee_cost=a.fee_cost,
        created_time=a.created_time if a.created_time is not None else b.created_time,
        ts=a.ts if a.ts is not None else b.ts,
        observations=a.observations + b.observations,
        raw_authoritative=MappingProxyType({**dict(b.raw_authoritative), **dict(a.raw_authoritative)}),
    )


# ---------------------------------------------------------------------------
# Deadline / request / evidence execution state
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _Deadline:
    clock: Callable[[], float]
    entry: float

    @property
    def absolute(self) -> float:
        return self.entry + MASTER_DEADLINE_MS / 1000.0

    def expired(self) -> bool:
        return self.clock() >= self.absolute

    def remaining_ms(self) -> int:
        remaining = max(0.0, self.absolute - self.clock())
        return int(remaining * 1000.0)


@dataclass(slots=True)
class _ExecutionState:
    request_counts: Dict[ReconciliationOperation, int] = field(
        default_factory=lambda: {op: 0 for op in ReconciliationOperation}
    )
    request_ledger: List[Dict[str, object]] = field(default_factory=list)
    cutoff: Optional[Dict[str, str]] = None
    order_pages: Dict[str, List[Dict[str, object]]] = field(
        default_factory=lambda: {"LIVE_ORDERS": [], "HISTORICAL_ORDERS": []}
    )
    fill_pages: Dict[str, List[Dict[str, object]]] = field(
        default_factory=lambda: {"LIVE_FILLS": [], "HISTORICAL_FILLS": []}
    )
    order_duplicate_details: List[Dict[str, object]] = field(default_factory=list)
    fill_duplicate_details: List[Dict[str, object]] = field(default_factory=list)
    matched_order_ids: List[str] = field(default_factory=list)
    identity_matrix: Dict[str, str] = field(default_factory=dict)
    exact_order_evidence: Optional[Dict[str, object]] = None
    canonical_orders: List[_OrderRecord] = field(default_factory=list)
    canonical_fills: List[_FillRecord] = field(default_factory=list)
    bound_order_id: Optional[str] = None
    match_count: int = 0
    canonical_fill_quantity: Optional[Decimal] = None
    canonical_filled_principal: Optional[Decimal] = None
    canonical_fee_cost: Optional[Decimal] = None
    retry_count_observed: int = 0
    redirect_count_observed: int = 0

    def total_requests(self) -> int:
        return sum(self.request_counts.values())


def _check_deadline(deadline: _Deadline) -> Optional[HaltCode]:
    return HaltCode.MASTER_DEADLINE_EXHAUSTED if deadline.expired() else None


def _query_for(
    operation: ReconciliationOperation,
    *,
    cursor: Optional[str] = None,
    order_id: Optional[str] = None,
) -> Mapping[str, object]:
    if operation is ReconciliationOperation.HISTORICAL_CUTOFF:
        query: Dict[str, object] = {}
    elif operation is ReconciliationOperation.LIVE_ORDERS:
        query = {"ticker": TICKER, "subaccount": SUBACCOUNT, "limit": PAGE_LIMIT}
    elif operation is ReconciliationOperation.HISTORICAL_ORDERS:
        query = {"ticker": TICKER, "limit": PAGE_LIMIT}
    elif operation is ReconciliationOperation.EXACT_ORDER:
        query = {}
    elif operation is ReconciliationOperation.LIVE_FILLS:
        if type(order_id) is not str or order_id == "":
            raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
        query = {
            "ticker": TICKER,
            "order_id": order_id,
            "subaccount": SUBACCOUNT,
            "limit": PAGE_LIMIT,
        }
    elif operation is ReconciliationOperation.HISTORICAL_FILLS:
        query = {"ticker": TICKER, "limit": PAGE_LIMIT}
    else:
        raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
    if cursor is not None:
        if not _OPERATION_SPECS[operation].paginated or type(cursor) is not str or cursor == "":
            raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
        query["cursor"] = cursor
    return MappingProxyType(query)


def _path_for(operation: ReconciliationOperation, *, order_id: Optional[str] = None) -> str:
    spec = _OPERATION_SPECS[operation]
    if operation is ReconciliationOperation.EXACT_ORDER:
        if type(order_id) is not str or order_id == "" or "/" in order_id or "?" in order_id or "#" in order_id:
            raise ValueError(HaltCode.GET_ONLY_CONTRACT_VIOLATION.value)
        return spec.path_template.replace("{order_id}", order_id)
    return spec.path_template


def _validate_prepared_request(request: object) -> Optional[HaltCode]:
    if type(request) is not PreparedGetRequest:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if type(request.operation) is not ReconciliationOperation:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if request.origin != DEMO_REST_ORIGIN:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if request.method != "GET":
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    spec = _OPERATION_SPECS[request.operation]
    if request.authentication_class is not spec.authentication_class:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if type(request.path) is not str or not request.path.startswith(TRADE_API_BASE_PATH):
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if request.operation is ReconciliationOperation.EXACT_ORDER:
        prefix = "/trade-api/v2/portfolio/orders/"
        if not request.path.startswith(prefix):
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
        tail = request.path[len(prefix):]
        if tail == "" or "/" in tail or "?" in tail or "#" in tail:
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    elif request.path != spec.path_template:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if not isinstance(request.query, Mapping):
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION

    keys = set(request.query)
    if request.operation is ReconciliationOperation.HISTORICAL_CUTOFF:
        if keys:
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    elif request.operation is ReconciliationOperation.LIVE_ORDERS:
        allowed = {"ticker", "subaccount", "limit", "cursor"}
        if not keys.issubset(allowed) or not {"ticker", "subaccount", "limit"}.issubset(keys):
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
        if request.query["ticker"] != TICKER or request.query["subaccount"] != 0 or request.query["limit"] != 1000:
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    elif request.operation is ReconciliationOperation.HISTORICAL_ORDERS:
        allowed = {"ticker", "limit", "cursor"}
        if not keys.issubset(allowed) or not {"ticker", "limit"}.issubset(keys):
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
        if request.query["ticker"] != TICKER or request.query["limit"] != 1000:
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    elif request.operation is ReconciliationOperation.EXACT_ORDER:
        if keys:
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    elif request.operation is ReconciliationOperation.LIVE_FILLS:
        allowed = {"ticker", "order_id", "subaccount", "limit", "cursor"}
        if not keys.issubset(allowed) or not {"ticker", "order_id", "subaccount", "limit"}.issubset(keys):
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
        if (
            request.query["ticker"] != TICKER
            or request.query["subaccount"] != 0
            or request.query["limit"] != 1000
            or request.path != "/trade-api/v2/portfolio/fills"
        ):
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    elif request.operation is ReconciliationOperation.HISTORICAL_FILLS:
        allowed = {"ticker", "limit", "cursor"}
        if not keys.issubset(allowed) or not {"ticker", "limit"}.issubset(keys):
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
        if request.query["ticker"] != TICKER or request.query["limit"] != 1000:
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION

    if "cursor" in request.query:
        cursor = request.query["cursor"]
        if type(cursor) is not str or cursor == "":
            return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    if type(request.page_ordinal) is not int or request.page_ordinal < 1:
        return HaltCode.GET_ONLY_CONTRACT_VIOLATION
    return None


def _cursor_evidence(cursor: Optional[str]) -> Dict[str, object]:
    if cursor is None:
        return {"classification": "OMITTED", "sha256": None}
    if cursor == "":
        return {"classification": "TERMINAL_EMPTY", "sha256": None}
    return {"classification": "NONEMPTY_OPAQUE", "sha256": _sha256(cursor.encode("utf-8"))}


def _send_json(
    *,
    operation: ReconciliationOperation,
    transport: ReconciliationTransport,
    deadline: _Deadline,
    state: _ExecutionState,
    page_ordinal: int,
    cursor_input: Optional[str] = None,
    order_id: Optional[str] = None,
) -> Tuple[Optional[object], Optional[RawHttpResponse], Optional[HaltCode]]:
    if _check_deadline(deadline) is not None:
        return None, None, HaltCode.MASTER_DEADLINE_EXHAUSTED
    spec = _OPERATION_SPECS[operation]
    if state.request_counts[operation] >= spec.page_budget:
        return None, None, HaltCode.PAGE_BUDGET_EXHAUSTED
    if state.total_requests() >= GLOBAL_GET_SEND_MAXIMUM:
        return None, None, HaltCode.GLOBAL_REQUEST_BUDGET_EXHAUSTED

    try:
        path = _path_for(operation, order_id=order_id)
        query = _query_for(operation, cursor=cursor_input, order_id=order_id)
    except ValueError:
        return None, None, HaltCode.GET_ONLY_CONTRACT_VIOLATION

    request_start = deadline.clock()
    if request_start >= deadline.absolute:
        return None, None, HaltCode.MASTER_DEADLINE_EXHAUSTED
    effective = min(request_start + PER_REQUEST_CEILING_MS / 1000.0, deadline.absolute)
    request = PreparedGetRequest(
        operation=operation,
        origin=DEMO_REST_ORIGIN,
        path=path,
        query=query,
        authentication_class=spec.authentication_class,
        page_ordinal=page_ordinal,
        effective_deadline_monotonic=effective,
    )
    contract_halt = _validate_prepared_request(request)
    if contract_halt is not None:
        return None, None, contract_halt

    state.request_counts[operation] += 1
    ledger: Dict[str, object] = {
        "ordinal": state.total_requests(),
        "operation": operation.value,
        "method": "GET",
        "path": path,
        "sanitized_query": dict(query),
        "authentication_class": spec.authentication_class.value,
        "cursor_input": _cursor_evidence(cursor_input),
        "cursor_output": None,
        "page_ordinal": page_ordinal,
        "http_status": None,
        "media_type": None,
        "response_bytes": None,
        "response_sha256": None,
        "json_schema_classification": "TRANSPORT_PENDING",
        "elapsed_ms": None,
        "remaining_master_budget_after_parse_ms": None,
        "retry_count": 0,
        "redirect_count": 0,
    }
    state.request_ledger.append(ledger)

    try:
        response = transport.send(request)
    except Exception:
        ledger["json_schema_classification"] = "TRANSPORT_READ_FAILURE"
        ledger["elapsed_ms"] = max(0, int((deadline.clock() - request_start) * 1000))
        return None, None, HaltCode.TRANSPORT_READ_FAILURE

    after_receive = deadline.clock()
    if type(response) is not RawHttpResponse:
        ledger["json_schema_classification"] = "TRANSPORT_EVIDENCE_INVALID"
        return None, None, HaltCode.TRANSPORT_READ_FAILURE

    ledger["http_status"] = response.status
    ledger["media_type"] = response.media_type
    ledger["retry_count"] = response.retry_count
    ledger["redirect_count"] = response.redirect_count
    state.retry_count_observed += response.retry_count if type(response.retry_count) is int and type(response.retry_count) is not bool else 0
    state.redirect_count_observed += response.redirect_count if type(response.redirect_count) is int and type(response.redirect_count) is not bool else 0

    if after_receive >= deadline.absolute:
        ledger["json_schema_classification"] = "MASTER_DEADLINE_EXHAUSTED"
        return None, response, HaltCode.MASTER_DEADLINE_EXHAUSTED
    if after_receive >= effective:
        ledger["json_schema_classification"] = "PER_REQUEST_CEILING_EXHAUSTED"
        return None, response, HaltCode.TRANSPORT_READ_FAILURE
    if type(response.retry_count) is not int or type(response.retry_count) is bool or response.retry_count != 0:
        ledger["json_schema_classification"] = "RETRY_CONTRACT_VIOLATION"
        return None, response, HaltCode.TRANSPORT_READ_FAILURE
    if type(response.redirect_count) is not int or type(response.redirect_count) is bool:
        ledger["json_schema_classification"] = "REDIRECT_EVIDENCE_INVALID"
        return None, response, HaltCode.TRANSPORT_READ_FAILURE
    if response.redirect_count != 0:
        ledger["json_schema_classification"] = "REDIRECT_PROHIBITED"
        return None, response, HaltCode.REDIRECT_PROHIBITED
    if type(response.status) is not int or type(response.status) is bool:
        ledger["json_schema_classification"] = "STATUS_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    if 300 <= response.status <= 399:
        ledger["json_schema_classification"] = "REDIRECT_PROHIBITED"
        return None, response, HaltCode.REDIRECT_PROHIBITED
    if response.status != 200:
        ledger["json_schema_classification"] = "UNEXPECTED_HTTP_STATUS"
        return None, response, HaltCode.UNEXPECTED_HTTP_STATUS
    if type(response.media_type) is not str or response.media_type.split(";", 1)[0].strip().lower() != "application/json":
        ledger["json_schema_classification"] = "MEDIA_TYPE_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    if type(response.body_bytes) is not bytes:
        ledger["json_schema_classification"] = "BODY_BYTES_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT

    ledger["response_bytes"] = len(response.body_bytes)
    ledger["response_sha256"] = _sha256(response.body_bytes)
    try:
        parsed = _strict_json_loads(response.body_bytes)
    except ValueError:
        ledger["json_schema_classification"] = "STRICT_JSON_INVALID"
        return None, response, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT

    if _check_deadline(deadline) is not None:
        ledger["json_schema_classification"] = "MASTER_DEADLINE_EXHAUSTED_AFTER_PARSE"
        return None, response, HaltCode.MASTER_DEADLINE_EXHAUSTED

    ledger["json_schema_classification"] = "STRICT_JSON_VALID"
    ledger["elapsed_ms"] = max(0, int((deadline.clock() - request_start) * 1000))
    ledger["remaining_master_budget_after_parse_ms"] = deadline.remaining_ms()
    return parsed, response, None


def _extract_page(
    parsed: object,
    *,
    record_key: str,
) -> Tuple[Optional[List[object]], Optional[str], Optional[HaltCode]]:
    if type(parsed) is not dict or record_key not in parsed:
        return None, None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    if "cursor" not in parsed:
        return None, None, HaltCode.PAGINATION_CURSOR_MALFORMED
    records = parsed[record_key]
    cursor = parsed["cursor"]
    if type(records) is not list:
        return None, None, HaltCode.AUTHORITATIVE_SCHEMA_DRIFT
    if type(cursor) is not str:
        return None, None, HaltCode.PAGINATION_CURSOR_MALFORMED
    return records, cursor, None


def _dedupe_orders(
    records: Sequence[_OrderRecord],
    *,
    state: _ExecutionState,
) -> Tuple[Optional[List[_OrderRecord]], Optional[HaltCode]]:
    by_id: Dict[str, _OrderRecord] = {}
    for record in records:
        existing = by_id.get(record.order_id)
        if existing is None:
            by_id[record.order_id] = record
            continue
        compatible = _common_fields_compatible(existing.raw_authoritative, record.raw_authoritative)
        state.order_duplicate_details.append({
            "order_id": record.order_id,
            "classification": "COMPATIBLE" if compatible else "CONFLICT",
        })
        if not compatible:
            return None, HaltCode.ORDER_ID_DUPLICATE_CONFLICT
        by_id[record.order_id] = _merge_order_observations(existing, record)
    return list(by_id.values()), None


def _validate_target_order(order: _OrderRecord, *, state: _ExecutionState) -> Optional[HaltCode]:
    checks = {
        "client_order_id": order.client_order_id == CLIENT_ORDER_ID,
        "ticker": order.ticker == TICKER,
        "subaccount_number": order.subaccount_number == SUBACCOUNT,
        "outcome_side": order.outcome_side == OUTCOME_SIDE,
        "book_side": order.book_side == BOOK_SIDE,
        "initial_count_fp": order.initial_count_fp == INITIAL_QUANTITY,
        "yes_price_dollars": order.yes_price_dollars == LIMIT_PRICE,
        "cancel_order_on_pause": order.cancel_order_on_pause is CANCEL_ORDER_ON_PAUSE,
    }
    for name, passed in checks.items():
        state.identity_matrix[name] = "PASS" if passed else "FAIL"
    optional = {
        "self_trade_prevention_type": (order.self_trade_prevention_type, SELF_TRADE_PREVENTION_TYPE),
        "post_only": (order.post_only, POST_ONLY),
        "time_in_force": (order.time_in_force, TIME_IN_FORCE),
        "reduce_only": (order.reduce_only, REDUCE_ONLY),
        "exchange_index": (order.exchange_index, EXCHANGE_INDEX),
    }
    for name, (observed, expected) in optional.items():
        if observed is None:
            state.identity_matrix[name] = "FIELD_NOT_EXPOSED_BY_BOUND_SOURCE"
        elif type(observed) is type(expected) and observed == expected:
            state.identity_matrix[name] = "PASS"
        else:
            state.identity_matrix[name] = "FAIL"
            return HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH

    if order.legacy_action is not None and order.legacy_action != "buy":
        state.identity_matrix["legacy_action"] = "FAIL"
        return HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH
    if order.legacy_side is not None and order.legacy_side != "yes":
        state.identity_matrix["legacy_side"] = "FAIL"
        return HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH
    if not all(checks.values()):
        return HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH
    return None


def _state_fields_equal(a: _OrderRecord, b: _OrderRecord) -> bool:
    return (
        a.status == b.status
        and a.fill_count_fp == b.fill_count_fp
        and a.remaining_count_fp == b.remaining_count_fp
    )


def _dedupe_fills(
    records: Sequence[_FillRecord],
    *,
    state: _ExecutionState,
) -> Tuple[Optional[List[_FillRecord]], Optional[HaltCode]]:
    by_id: Dict[str, _FillRecord] = {}
    for record in records:
        existing = by_id.get(record.fill_id)
        if existing is None:
            by_id[record.fill_id] = record
            continue
        compatible = _common_fields_compatible(existing.raw_authoritative, record.raw_authoritative)
        state.fill_duplicate_details.append({
            "fill_id": record.fill_id,
            "classification": "COMPATIBLE" if compatible else "CONFLICT",
        })
        if not compatible:
            return None, HaltCode.FILL_ID_DUPLICATE_CONFLICT
        by_id[record.fill_id] = _merge_fill_observations(existing, record)
    return list(by_id.values()), None


# ---------------------------------------------------------------------------
# Deterministic evidence/result construction
# ---------------------------------------------------------------------------

def _observation_evidence(observation: _Observation) -> Dict[str, object]:
    return {
        "source_stream": observation.source_stream,
        "page_ordinal": observation.page_ordinal,
        "record_ordinal": observation.record_ordinal,
        "response_sha256": observation.response_sha256,
    }


def _order_evidence(order: _OrderRecord) -> Dict[str, object]:
    return {
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "ticker": order.ticker,
        "subaccount_number": order.subaccount_number,
        "outcome_side": order.outcome_side,
        "book_side": order.book_side,
        "yes_price_dollars": str(order.yes_price_dollars),
        "no_price_dollars": str(order.no_price_dollars),
        "cancel_order_on_pause": order.cancel_order_on_pause,
        "status": order.status,
        "initial_count_fp": str(order.initial_count_fp),
        "fill_count_fp": str(order.fill_count_fp),
        "remaining_count_fp": str(order.remaining_count_fp),
        "source_provenance": [_observation_evidence(o) for o in order.observations],
    }


def _fill_evidence(fill: _FillRecord) -> Dict[str, object]:
    return {
        "fill_id": fill.fill_id,
        "trade_id": fill.trade_id,
        "order_id": fill.order_id,
        "ticker": fill.ticker,
        "market_ticker": fill.market_ticker,
        "subaccount_number": fill.subaccount_number,
        "outcome_side": fill.outcome_side,
        "book_side": fill.book_side,
        "count_fp": str(fill.count_fp),
        "yes_price_dollars": str(fill.yes_price_dollars),
        "no_price_dollars": str(fill.no_price_dollars),
        "is_taker": fill.is_taker,
        "fee_cost": str(fill.fee_cost),
        "created_time": fill.created_time,
        "ts": fill.ts,
        "source_provenance": [_observation_evidence(o) for o in fill.observations],
    }


def _artifact_evidence(identity: ArtifactIdentity) -> Dict[str, object]:
    return {
        "path": identity.path,
        "bytes": identity.bytes,
        "sha256": identity.sha256,
        "git_blob": identity.git_blob,
    }


def _make_evidence_payload(
    *,
    reconciliation_input: ReconciliationInput,
    state: _ExecutionState,
    result_class: ResultClass,
    halt_code: Optional[HaltCode],
    bound_order_id: Optional[str],
    created_order_upper_bound: int,
    active_order_upper_bound: int,
    unknown_result: bool,
    writer_proof_release_eligible: bool,
    canonical_fill_count: int,
    canonical_fill_quantity: Optional[Decimal],
    canonical_filled_principal: Optional[Decimal],
    canonical_fee_cost: Optional[Decimal],
) -> Dict[str, object]:
    principal_plus_fee = (
        canonical_filled_principal + canonical_fee_cost
        if canonical_filled_principal is not None and canonical_fee_cost is not None
        else None
    )
    return {
        "task_id": "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_IMPLEMENTATION_01",
        "repository": REPOSITORY,
        "canonical_main": REQUIRED_BASE,
        "canonical_tree": REQUIRED_TREE,
        "identities": {
            "specification": {
                "filename": SPECIFICATION_FILENAME,
                "bytes": SPECIFICATION_BYTES,
                "sha256": SPECIFICATION_SHA256,
            },
            "handoff": {
                "filename": HANDOFF_FILENAME,
                "bytes": HANDOFF_BYTES,
                "sha256": HANDOFF_SHA256,
            },
            "execution_01_evidence": {
                "filename": EXECUTION_EVIDENCE_FILENAME,
                "bytes": EXECUTION_EVIDENCE_BYTES,
                "sha256": EXECUTION_EVIDENCE_SHA256,
            },
            "accepted_lifecycle_specification": {
                "bytes": ACCEPTED_LIFECYCLE_SPEC_BYTES,
                "sha256": ACCEPTED_LIFECYCLE_SPEC_SHA256,
            },
            "accepted_lifecycle_implementation": {
                "path": ACCEPTED_LIFECYCLE_IMPLEMENTATION_PATH,
                "bytes": ACCEPTED_LIFECYCLE_IMPLEMENTATION_BYTES,
                "sha256": ACCEPTED_LIFECYCLE_IMPLEMENTATION_SHA256,
                "git_blob": ACCEPTED_LIFECYCLE_IMPLEMENTATION_BLOB,
            },
            "implementation": _artifact_evidence(reconciliation_input.provenance.implementation),
            "tests": _artifact_evidence(reconciliation_input.provenance.tests),
            "source_binding_manifest": {
                "bytes": SOURCE_BINDING_MANIFEST_LENGTH,
                "sha256": SOURCE_BINDING_MANIFEST_SHA256,
            },
            "operation_bindings": {
                name: {"bytes": values[0], "sha256": values[1]}
                for name, values in OPERATION_BINDING_IDENTITIES.items()
            },
            "raw_openapi_if_materialized": (
                None
                if reconciliation_input.provenance.source_raw_openapi_bytes is None
                else {
                    "bytes": reconciliation_input.provenance.source_raw_openapi_bytes,
                    "sha256": reconciliation_input.provenance.source_raw_openapi_sha256,
                }
            ),
        },
        "frozen_scope": {
            "environment": ENVIRONMENT,
            "demo_origin": DEMO_REST_ORIGIN,
            "account_scope_ref": ACCOUNT_SCOPE_REF,
            "subaccount": SUBACCOUNT,
            "ticker": TICKER,
            "client_order_id": CLIENT_ORDER_ID,
            "writer_proof_id": WRITER_PROOF_ID,
            "economic_meaning": ECONOMIC_MEANING,
            "outcome_side": OUTCOME_SIDE,
            "book_side": BOOK_SIDE,
            "initial_quantity": str(INITIAL_QUANTITY),
            "limit_price": str(LIMIT_PRICE),
            "time_in_force": TIME_IN_FORCE,
            "post_only": POST_ONLY,
            "cancel_order_on_pause": CANCEL_ORDER_ON_PAUSE,
            "reduce_only": REDUCE_ONLY,
            "self_trade_prevention_type": SELF_TRADE_PREVENTION_TYPE,
            "exchange_index": EXCHANGE_INDEX,
        },
        "historical_cutoff": state.cutoff,
        "request_ledger": state.request_ledger,
        "enumeration": {
            "live_order_pages": state.order_pages["LIVE_ORDERS"],
            "historical_order_pages": state.order_pages["HISTORICAL_ORDERS"],
            "live_fill_pages": state.fill_pages["LIVE_FILLS"],
            "historical_fill_pages": state.fill_pages["HISTORICAL_FILLS"],
            "termination_cursor_state": {
                "LIVE_ORDERS": (state.order_pages["LIVE_ORDERS"][-1]["cursor_output"] if state.order_pages["LIVE_ORDERS"] else None),
                "HISTORICAL_ORDERS": (state.order_pages["HISTORICAL_ORDERS"][-1]["cursor_output"] if state.order_pages["HISTORICAL_ORDERS"] else None),
                "LIVE_FILLS": (state.fill_pages["LIVE_FILLS"][-1]["cursor_output"] if state.fill_pages["LIVE_FILLS"] else None),
                "HISTORICAL_FILLS": (state.fill_pages["HISTORICAL_FILLS"][-1]["cursor_output"] if state.fill_pages["HISTORICAL_FILLS"] else None),
            },
            "records_retained": {
                "orders": len(state.canonical_orders),
                "fills": len(state.canonical_fills),
            },
            "order_duplicate_details": state.order_duplicate_details,
            "fill_duplicate_details": state.fill_duplicate_details,
        },
        "order_match": {
            "exact_client_order_id_match_count": state.match_count,
            "matched_order_ids": state.matched_order_ids,
            "bound_order_id": bound_order_id,
            "identity_invariant_matrix": state.identity_matrix,
            "canonical_orders": [_order_evidence(o) for o in state.canonical_orders],
            "exact_order_result": state.exact_order_evidence,
        },
        "fills": {
            "canonical_fill_identities": [_fill_evidence(f) for f in state.canonical_fills],
            "canonical_fill_count": canonical_fill_count,
            "canonical_fill_quantity": None if canonical_fill_quantity is None else str(canonical_fill_quantity),
            "canonical_filled_principal": None if canonical_filled_principal is None else str(canonical_filled_principal),
            "canonical_fee_cost": None if canonical_fee_cost is None else str(canonical_fee_cost),
            "principal_plus_fee": None if principal_plus_fee is None else str(principal_plus_fee),
            "order_fill_reconciliation_result": (
                "PASS"
                if result_class in (
                    ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE,
                    ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL,
                )
                else "UNRESOLVED_OR_NOT_REACHED"
            ),
        },
        "terminal": {
            "result_class": result_class.value,
            "halt_code": None if halt_code is None else halt_code.value,
            "created_order_upper_bound": created_order_upper_bound,
            "active_order_upper_bound": active_order_upper_bound,
            "unknown_result": unknown_result,
            "writer_proof_release_eligible": writer_proof_release_eligible,
            "request_count": state.total_requests(),
            "retry_count": state.retry_count_observed,
            "redirect_count": state.redirect_count_observed,
            "production_activity": 0,
            "write_activity": 0,
            "funding_activity": 0,
            "websocket_activity": 0,
            "secret_values_printed": False,
            "secret_values_persisted": False,
        },
    }


def _finalize(
    *,
    reconciliation_input: ReconciliationInput,
    state: _ExecutionState,
    deadline: _Deadline,
    result_class: ResultClass,
    halt_code: Optional[HaltCode],
    bound_order_id: Optional[str],
    created_order_upper_bound: int,
    active_order_upper_bound: int,
    unknown_result: bool,
    writer_proof_release_eligible: bool,
    match_count: int,
    canonical_fill_count: int,
    canonical_fill_quantity: Optional[Decimal],
    canonical_filled_principal: Optional[Decimal],
    canonical_fee_cost: Optional[Decimal],
    enforce_deadline: bool = True,
) -> ReconciliationResult:
    state.match_count = match_count
    payload = _make_evidence_payload(
        reconciliation_input=reconciliation_input,
        state=state,
        result_class=result_class,
        halt_code=halt_code,
        bound_order_id=bound_order_id,
        created_order_upper_bound=created_order_upper_bound,
        active_order_upper_bound=active_order_upper_bound,
        unknown_result=unknown_result,
        writer_proof_release_eligible=writer_proof_release_eligible,
        canonical_fill_count=canonical_fill_count,
        canonical_fill_quantity=canonical_fill_quantity,
        canonical_filled_principal=canonical_filled_principal,
        canonical_fee_cost=canonical_fee_cost,
    )
    evidence = _canonical_json_bytes(_json_safe(payload))
    if enforce_deadline and deadline.expired():
        # Evidence/result construction itself consumed the master budget.
        # Build a minimal fail-closed terminal artifact without re-checking the
        # already-exhausted budget.
        return _finalize(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            result_class=ResultClass.WRITE_UNRESOLVED_READ_FAILURE,
            halt_code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
            bound_order_id=state.bound_order_id,
            created_order_upper_bound=1,
            active_order_upper_bound=1,
            unknown_result=True,
            writer_proof_release_eligible=False,
            match_count=state.match_count,
            canonical_fill_count=canonical_fill_count,
            canonical_fill_quantity=canonical_fill_quantity,
            canonical_filled_principal=canonical_filled_principal,
            canonical_fee_cost=canonical_fee_cost,
            enforce_deadline=False,
        )
    return ReconciliationResult(
        result_class=result_class,
        halt_code=halt_code,
        bound_order_id=bound_order_id,
        created_order_upper_bound=created_order_upper_bound,
        active_order_upper_bound=active_order_upper_bound,
        unknown_result=unknown_result,
        writer_proof_release_eligible=writer_proof_release_eligible,
        exact_client_order_id_match_count=match_count,
        canonical_fill_count=canonical_fill_count,
        canonical_fill_quantity=canonical_fill_quantity,
        canonical_filled_principal=canonical_filled_principal,
        canonical_fee_cost=canonical_fee_cost,
        request_count=state.total_requests(),
        retry_count=state.retry_count_observed,
        redirect_count=state.redirect_count_observed,
        production_activity=0,
        write_activity=0,
        funding_activity=0,
        websocket_activity=0,
        evidence_json=evidence,
        evidence_sha256=_sha256(evidence),
    )


def _failure_result(
    *,
    reconciliation_input: ReconciliationInput,
    state: _ExecutionState,
    deadline: _Deadline,
    code: HaltCode,
    match_count: Optional[int] = None,
    identity_width: Optional[int] = None,
) -> ReconciliationResult:
    if code in _IDENTITY_VIOLATION_CODES:
        result_class = ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION
        width = identity_width if identity_width is not None else max(1, match_count or state.match_count or 1)
        bound = None
        created = width
        active = width
    else:
        result_class = ResultClass.WRITE_UNRESOLVED_READ_FAILURE
        bound = state.bound_order_id
        created = 1
        active = 1
    return _finalize(
        reconciliation_input=reconciliation_input,
        state=state,
        deadline=deadline,
        result_class=result_class,
        halt_code=code,
        bound_order_id=bound,
        created_order_upper_bound=created,
        active_order_upper_bound=active,
        unknown_result=True,
        writer_proof_release_eligible=False,
        match_count=state.match_count if match_count is None else match_count,
        canonical_fill_count=len(state.canonical_fills),
        canonical_fill_quantity=state.canonical_fill_quantity,
        canonical_filled_principal=state.canonical_filled_principal,
        canonical_fee_cost=state.canonical_fee_cost,
    )


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

def execute_post_halt_reconciliation(
    reconciliation_input: ReconciliationInput,
    transport: ReconciliationTransport,
    *,
    monotonic_clock: Optional[Callable[[], float]] = None,
) -> ReconciliationResult:
    """Execute the closed read-only reconciliation through ``transport``.

    The master deadline starts at this function's entry and therefore covers
    capability/source validation, internal planning, request construction,
    transport, strict parsing, pagination, deduplication, matching, Decimal
    arithmetic, evidence construction, and terminal result construction.
    """

    clock = monotonic_clock if monotonic_clock is not None else time.monotonic
    entry = clock()
    deadline = _Deadline(clock=clock, entry=entry)
    state = _ExecutionState()

    validation_halt = _validate_input(reconciliation_input)
    if validation_halt is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input
            if type(reconciliation_input) is ReconciliationInput
            else _minimal_invalid_input(),
            state=state,
            deadline=deadline,
            code=validation_halt,
        )
    if _check_deadline(deadline) is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )

    # Internal replanning under the deadline. Public preplanning is never
    # trusted as runtime authorization or used as the execution clock origin.
    try:
        plan = plan_post_halt_reconciliation(reconciliation_input)
    except ReconciliationPlanningError as exc:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=exc.halt_code,
        )
    if plan.operations != _OPERATION_ORDER or plan.origin != DEMO_REST_ORIGIN:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.GET_ONLY_CONTRACT_VIOLATION,
        )
    if _check_deadline(deadline) is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )

    # 1. Historical cutoff.
    parsed, response, halt = _send_json(
        operation=ReconciliationOperation.HISTORICAL_CUTOFF,
        transport=transport,
        deadline=deadline,
        state=state,
        page_ordinal=1,
    )
    if halt is not None:
        if halt is HaltCode.AUTHORITATIVE_SCHEMA_DRIFT:
            halt = HaltCode.CUTOFF_RESPONSE_INVALID
        return _failure_result(reconciliation_input=reconciliation_input, state=state, deadline=deadline, code=halt)
    assert type(parsed) is dict and response is not None
    cutoff_fields = ("market_settled_ts", "trades_created_ts", "orders_updated_ts")
    if any(name not in parsed for name in cutoff_fields):
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.CUTOFF_RESPONSE_INVALID,
        )
    if any(not _valid_rfc3339(parsed[name]) for name in cutoff_fields):
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.CUTOFF_RESPONSE_INVALID,
        )
    state.cutoff = {name: parsed[name] for name in cutoff_fields}

    # 2-3. Complete live then historical order streams.
    all_orders: List[_OrderRecord] = []
    for operation, source_name in (
        (ReconciliationOperation.LIVE_ORDERS, "LIVE_ORDERS"),
        (ReconciliationOperation.HISTORICAL_ORDERS, "HISTORICAL_ORDERS"),
    ):
        cursor: Optional[str] = None
        seen_nonempty: set[str] = set()
        page = 1
        while True:
            parsed, response, halt = _send_json(
                operation=operation,
                transport=transport,
                deadline=deadline,
                state=state,
                page_ordinal=page,
                cursor_input=cursor,
            )
            if halt is not None:
                return _failure_result(reconciliation_input=reconciliation_input, state=state, deadline=deadline, code=halt)
            assert response is not None
            records, next_cursor, page_halt = _extract_page(parsed, record_key="orders")
            if page_halt is not None:
                return _failure_result(reconciliation_input=reconciliation_input, state=state, deadline=deadline, code=page_halt)
            assert records is not None and next_cursor is not None
            state.request_ledger[-1]["cursor_output"] = _cursor_evidence(next_cursor)
            page_detail = {
                "page_ordinal": page,
                "records_observed": len(records),
                "cursor_input": _cursor_evidence(cursor),
                "cursor_output": _cursor_evidence(next_cursor),
                "response_sha256": _sha256(response.body_bytes),
            }
            state.order_pages[source_name].append(page_detail)
            for index, raw_order in enumerate(records, 1):
                observation = _Observation(source_name, page, index, _sha256(response.body_bytes))
                order, order_halt = _parse_order(raw_order, observation=observation)
                if order_halt is not None:
                    return _failure_result(
                        reconciliation_input=reconciliation_input,
                        state=state,
                        deadline=deadline,
                        code=order_halt,
                    )
                assert order is not None
                if operation is ReconciliationOperation.LIVE_ORDERS and order.subaccount_number != SUBACCOUNT:
                    return _failure_result(
                        reconciliation_input=reconciliation_input,
                        state=state,
                        deadline=deadline,
                        code=HaltCode.AUTHORITATIVE_SCHEMA_DRIFT,
                    )
                all_orders.append(order)
            if _check_deadline(deadline) is not None:
                return _failure_result(
                    reconciliation_input=reconciliation_input,
                    state=state,
                    deadline=deadline,
                    code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
                )
            if next_cursor == "":
                break
            if next_cursor in seen_nonempty:
                return _failure_result(
                    reconciliation_input=reconciliation_input,
                    state=state,
                    deadline=deadline,
                    code=HaltCode.PAGINATION_CURSOR_CYCLE,
                )
            seen_nonempty.add(next_cursor)
            if page >= _OPERATION_SPECS[operation].page_budget:
                return _failure_result(
                    reconciliation_input=reconciliation_input,
                    state=state,
                    deadline=deadline,
                    code=HaltCode.PAGE_BUDGET_EXHAUSTED,
                )
            cursor = next_cursor
            page += 1

    # 4. Order dedupe and exact client-ID cardinality.
    deduped, dedupe_halt = _dedupe_orders(all_orders, state=state)
    if dedupe_halt is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=dedupe_halt,
        )
    assert deduped is not None
    state.canonical_orders = deduped
    if _check_deadline(deadline) is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )

    candidates = [order for order in deduped if order.client_order_id == CLIENT_ORDER_ID]
    state.match_count = len(candidates)
    state.matched_order_ids = [order.order_id for order in candidates]
    if len(candidates) == 0:
        return _finalize(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            result_class=ResultClass.WRITE_UNRESOLVED_ZERO_MATCH,
            halt_code=None,
            bound_order_id=None,
            created_order_upper_bound=1,
            active_order_upper_bound=1,
            unknown_result=True,
            writer_proof_release_eligible=False,
            match_count=0,
            canonical_fill_count=0,
            canonical_fill_quantity=None,
            canonical_filled_principal=None,
            canonical_fee_cost=None,
        )
    if len(candidates) > 1:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MULTIPLE_ORDER_IDS_FOR_CLIENT_ORDER_ID,
            match_count=len(candidates),
            identity_width=len(candidates),
        )

    candidate = candidates[0]
    identity_halt = _validate_target_order(candidate, state=state)
    if identity_halt is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=identity_halt,
            match_count=1,
        )

    state.bound_order_id = candidate.order_id
    live_observed = any(o.source_stream == "LIVE_ORDERS" for o in candidate.observations)
    historical_observed = any(o.source_stream == "HISTORICAL_ORDERS" for o in candidate.observations)
    if not live_observed and not historical_observed:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.AUTHORITATIVE_SCHEMA_DRIFT,
        )

    final_order = candidate
    if not live_observed:
        if candidate.status == "resting":
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.SOURCE_PARTITION_CONFLICT,
            )
    else:
        # 5. Exactly one live exact-order GET.
        parsed, response, halt = _send_json(
            operation=ReconciliationOperation.EXACT_ORDER,
            transport=transport,
            deadline=deadline,
            state=state,
            page_ordinal=1,
            order_id=state.bound_order_id,
        )
        if halt is not None:
            return _failure_result(reconciliation_input=reconciliation_input, state=state, deadline=deadline, code=halt)
        if type(parsed) is not dict or "order" not in parsed or response is None:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.AUTHORITATIVE_SCHEMA_DRIFT,
            )
        exact_observation = _Observation("EXACT_ORDER", 1, 1, _sha256(response.body_bytes))
        exact_order, exact_halt = _parse_order(parsed["order"], observation=exact_observation)
        if exact_halt is not None:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=exact_halt,
            )
        assert exact_order is not None
        state.exact_order_evidence = _order_evidence(exact_order)
        exact_identity_halt = _validate_target_order(exact_order, state=state)
        if exact_identity_halt is not None or exact_order.order_id != state.bound_order_id:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH,
                match_count=1,
            )
        if not _common_fields_compatible(
            {k: v for k, v in candidate.raw_authoritative.items() if k not in {"status", "fill_count_fp", "remaining_count_fp"}},
            {k: v for k, v in exact_order.raw_authoritative.items() if k not in {"status", "fill_count_fp", "remaining_count_fp"}},
        ):
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH,
                match_count=1,
            )
        if not _state_fields_equal(candidate, exact_order):
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.ORDER_STATE_CHANGED_DURING_RECONCILIATION,
            )
        final_order = exact_order

    if _check_deadline(deadline) is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )

    # 6-7. Complete live then historical fill streams.
    retained_fills: List[_FillRecord] = []
    for operation, source_name in (
        (ReconciliationOperation.LIVE_FILLS, "LIVE_FILLS"),
        (ReconciliationOperation.HISTORICAL_FILLS, "HISTORICAL_FILLS"),
    ):
        cursor: Optional[str] = None
        seen_nonempty: set[str] = set()
        page = 1
        while True:
            parsed, response, halt = _send_json(
                operation=operation,
                transport=transport,
                deadline=deadline,
                state=state,
                page_ordinal=page,
                cursor_input=cursor,
                order_id=state.bound_order_id if operation is ReconciliationOperation.LIVE_FILLS else None,
            )
            if halt is not None:
                return _failure_result(reconciliation_input=reconciliation_input, state=state, deadline=deadline, code=halt)
            assert response is not None
            records, next_cursor, page_halt = _extract_page(parsed, record_key="fills")
            if page_halt is not None:
                return _failure_result(reconciliation_input=reconciliation_input, state=state, deadline=deadline, code=page_halt)
            assert records is not None and next_cursor is not None
            state.request_ledger[-1]["cursor_output"] = _cursor_evidence(next_cursor)
            page_detail = {
                "page_ordinal": page,
                "records_observed": len(records),
                "cursor_input": _cursor_evidence(cursor),
                "cursor_output": _cursor_evidence(next_cursor),
                "response_sha256": _sha256(response.body_bytes),
            }
            state.fill_pages[source_name].append(page_detail)

            for index, raw_fill in enumerate(records, 1):
                observation = _Observation(source_name, page, index, _sha256(response.body_bytes))
                fill, fill_halt = _parse_fill(raw_fill, observation=observation)
                if fill_halt is not None:
                    return _failure_result(
                        reconciliation_input=reconciliation_input,
                        state=state,
                        deadline=deadline,
                        code=fill_halt,
                    )
                assert fill is not None
                if operation is ReconciliationOperation.HISTORICAL_FILLS and fill.order_id != state.bound_order_id:
                    # The historical endpoint cannot server-filter by order ID;
                    # unrelated, well-formed records are expected and ignored.
                    continue
                if fill.order_id != state.bound_order_id:
                    return _failure_result(
                        reconciliation_input=reconciliation_input,
                        state=state,
                        deadline=deadline,
                        code=HaltCode.FILL_WRONG_ORDER,
                    )
                if (
                    fill.ticker != TICKER
                    or fill.subaccount_number != SUBACCOUNT
                    or fill.outcome_side != OUTCOME_SIDE
                    or fill.book_side != BOOK_SIDE
                    or (fill.market_ticker is not None and fill.market_ticker != TICKER)
                ):
                    return _failure_result(
                        reconciliation_input=reconciliation_input,
                        state=state,
                        deadline=deadline,
                        code=HaltCode.FILL_SCOPE_MISMATCH,
                    )
                retained_fills.append(fill)

            if _check_deadline(deadline) is not None:
                return _failure_result(
                    reconciliation_input=reconciliation_input,
                    state=state,
                    deadline=deadline,
                    code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
                )
            if next_cursor == "":
                break
            if next_cursor in seen_nonempty:
                return _failure_result(
                    reconciliation_input=reconciliation_input,
                    state=state,
                    deadline=deadline,
                    code=HaltCode.PAGINATION_CURSOR_CYCLE,
                )
            seen_nonempty.add(next_cursor)
            if page >= _OPERATION_SPECS[operation].page_budget:
                return _failure_result(
                    reconciliation_input=reconciliation_input,
                    state=state,
                    deadline=deadline,
                    code=HaltCode.PAGE_BUDGET_EXHAUSTED,
                )
            cursor = next_cursor
            page += 1

    unique_fills, fill_dedupe_halt = _dedupe_fills(retained_fills, state=state)
    if fill_dedupe_halt is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=fill_dedupe_halt,
        )
    assert unique_fills is not None
    state.canonical_fills = unique_fills
    if _check_deadline(deadline) is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )

    # 8. Exact Decimal economics and order/fill reconciliation.
    fill_quantity = Decimal("0.00")
    filled_principal = Decimal("0")
    fee_cost = Decimal("0")
    for fill in unique_fills:
        if fill.is_taker:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.POST_ONLY_TAKER_FILL_CONFLICT,
            )
        if fill.yes_price_dollars > LIMIT_PRICE:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.FILL_PRICE_WORSE_THAN_LIMIT,
            )
        fill_quantity += fill.count_fp
        filled_principal += fill.count_fp * fill.yes_price_dollars
        fee_cost += fill.fee_cost
        if fill_quantity > INITIAL_QUANTITY:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.OVERFILL,
            )
    state.canonical_fill_quantity = fill_quantity
    state.canonical_filled_principal = filled_principal
    state.canonical_fee_cost = fee_cost

    if filled_principal > MAX_FILLED_PRINCIPAL:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.FILLED_PRINCIPAL_EXCEEDS_LIMIT,
        )
    if fee_cost > MAX_FEE_COST:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.FEE_RISK_EXCEEDS_LIMIT,
        )
    if filled_principal + fee_cost > MAX_TOTAL_RISK:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.TOTAL_RISK_EXCEEDS_LIMIT,
        )

    if _check_deadline(deadline) is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )
    if final_order.fill_count_fp != fill_quantity:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.FILL_ORDER_RECONCILIATION_MISMATCH,
        )
    if final_order.initial_count_fp != INITIAL_QUANTITY:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH,
        )

    status = final_order.status
    if status == "executed":
        if fill_quantity != INITIAL_QUANTITY or final_order.fill_count_fp != INITIAL_QUANTITY:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.FILL_ORDER_RECONCILIATION_MISMATCH,
            )
        if final_order.remaining_count_fp != Decimal("0.00"):
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.ORDER_FILL_ARITHMETIC_NOT_PROVEN,
            )
    elif status == "canceled":
        if fill_quantity < Decimal("0.00") or fill_quantity > INITIAL_QUANTITY:
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.ORDER_FILL_ARITHMETIC_NOT_PROVEN,
            )
    elif status == "resting":
        if fill_quantity >= INITIAL_QUANTITY or final_order.remaining_count_fp <= Decimal("0.00"):
            return _failure_result(
                reconciliation_input=reconciliation_input,
                state=state,
                deadline=deadline,
                code=HaltCode.ORDER_FILL_ARITHMETIC_NOT_PROVEN,
            )
    else:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.UNSUPPORTED_ORDER_STATUS,
        )

    if _check_deadline(deadline) is not None:
        return _failure_result(
            reconciliation_input=reconciliation_input,
            state=state,
            deadline=deadline,
            code=HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )

    if status == "resting":
        result_class = ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE
        active_upper = 1
        release = False
    else:
        result_class = ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL
        active_upper = 0
        release = True

    return _finalize(
        reconciliation_input=reconciliation_input,
        state=state,
        deadline=deadline,
        result_class=result_class,
        halt_code=None,
        bound_order_id=state.bound_order_id,
        created_order_upper_bound=1,
        active_order_upper_bound=active_upper,
        unknown_result=False,
        writer_proof_release_eligible=release,
        match_count=1,
        canonical_fill_count=len(unique_fills),
        canonical_fill_quantity=fill_quantity,
        canonical_filled_principal=filled_principal,
        canonical_fee_cost=fee_cost,
    )


def _minimal_invalid_input() -> ReconciliationInput:
    """Internal evidence-only placeholder used if a caller passes the wrong
    top-level type.  It contains no secret material and can never pass
    ``_validate_input`` or reach transport."""

    cap = ReconciliationCapabilityEnvelope(
        environment=ENVIRONMENT,
        rest_origin=DEMO_REST_ORIGIN,
        credential_reference_names=_REQUIRED_CREDENTIAL_REFERENCES,
        granted_capabilities=frozenset(),
        network_access=CapabilityState.PROHIBITED,
        demo_public_reads=CapabilityState.PROHIBITED,
        demo_authenticated_reads=CapabilityState.PROHIBITED,
        credential_use=CapabilityState.PROHIBITED,
        demo_writes=CapabilityState.PROHIBITED,
        production_public_reads=CapabilityState.PROHIBITED,
        production_authenticated_reads=CapabilityState.PROHIBITED,
        production_writes=CapabilityState.PROHIBITED,
        account_funding=CapabilityState.PROHIBITED,
        websocket=CapabilityState.PROHIBITED,
    )
    placeholder = ArtifactIdentity(
        path="UNAVAILABLE",
        bytes=0,
        sha256="0" * 64,
        git_blob="0" * 40,
    )
    return ReconciliationInput(
        capability_envelope=cap,
        source_binding_manifest_bytes=b"",
        provenance=ReconciliationProvenance(implementation=placeholder, tests=placeholder),
    )


__all__ = [
    "ACCOUNT_SCOPE_REF",
    "ArtifactIdentity",
    "AuthenticationClass",
    "BOOK_SIDE",
    "CANCEL_ORDER_ON_PAUSE",
    "CLIENT_ORDER_ID",
    "CapabilityState",
    "DEMO_REST_ORIGIN",
    "ENVIRONMENT",
    "GLOBAL_GET_SEND_MAXIMUM",
    "HaltCode",
    "INITIAL_QUANTITY",
    "LIMIT_PRICE",
    "MASTER_DEADLINE_MS",
    "MAX_FEE_COST",
    "MAX_FILLED_PRINCIPAL",
    "MAX_TOTAL_RISK",
    "OPERATION_BINDING_IDENTITIES",
    "OUTCOME_SIDE",
    "PAGE_LIMIT",
    "PER_REQUEST_CEILING_MS",
    "PreparedGetRequest",
    "RawHttpResponse",
    "ReconciliationCapabilityEnvelope",
    "ReconciliationInput",
    "ReconciliationOperation",
    "ReconciliationPlan",
    "ReconciliationPlanningError",
    "ReconciliationProvenance",
    "ReconciliationResult",
    "ReconciliationTransport",
    "ResultClass",
    "SOURCE_BINDING_MANIFEST_BYTES",
    "SOURCE_BINDING_MANIFEST_LENGTH",
    "SOURCE_BINDING_MANIFEST_SHA256",
    "SUBACCOUNT",
    "TICKER",
    "WRITER_PROOF_ID",
    "build_prepared_get_signing_message",
    "execute_post_halt_reconciliation",
    "plan_post_halt_reconciliation",
    "validate_source_binding_manifest",
]
