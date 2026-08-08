"""Kalshi Demo authenticated REST order-book reconstruction (Revision 01,
Implementation 06 -- a same-scope correction of Marco-blocked
Implementation 05, for task
`KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION_IMPLEMENTATION_06`).

Implements the exact accepted contract of
`KALSHI_DEMO_ONE_MARKET_AUTHENTICATED_REST_ORDER_BOOK_RECONSTRUCTION_SPEC_01.md`
(bytes 61146, SHA-256 `ae8a57069a261c35c5a204d3358091c7ae3f0f9ddbe1cdbe6c8fb20f9250ead8`).

Public module interface (Spec Section 9.1) -- exact names, no substitutes:

    plan_demo_authenticated_orderbook(input) -> AuthenticatedOrderBookPlan | OrderBookHalt
    build_orderbook_signing_message(plan, timestamp_ms_text) -> OrderBookSigningMessage
    execute_demo_authenticated_orderbook(plan) -> KalshiNativeOrderBookSnapshot | OrderBookHalt
    parse_orderbook_response(plan, response_body, response_content_type) -> ParsedNativeOrderBook | OrderBookHalt

Not implemented, and never added: a generic Kalshi client, generic
authenticated HTTP client, generic signer, SDK wrapper, async framework,
strategy abstraction, market-discovery layer, WebSocket support, order
support, account support, or production support.

Implementation history (changelog; this file is the current
Implementation-06 candidate, not a prior implementation)
--------------------------------------------------------------------

Implementation 03 established: the exact operation-local
`OrderBookRestCapability` enum; the exact six-field
`AuthenticatedOrderBookInput` and five-field
`OrderBookExecutionDispatchExpectation`; the exact accepted 1556-byte
Section-9.2 canonical operation-binding record validated field-for-field
by strict type-aware equality; the exact public interface names; the
plan-bound `OrderBookSigningMessage` with private-signer binding
rejection; the five current-value gate locations; the exact
signature-lifecycle vocabulary; opaque, unmutated API-key handling; the
complete Revision-01 `KalshiNativeOrderBookSnapshot` success-field set;
the exact Content-Type policy; body-cap enforcement during reception; and
DNS member validation including sockaddr/port/family/address agreement.

Implementation 04 corrected: partial secret-lifecycle evidence
(`SECRET_LOADED_NO_SIGNATURE` when the API key loaded but the private key
did not); body-only receive-cap accounting (headers never counted against
the `65536` cap); fail-closed current-value gates (no raw
`AttributeError`/`TypeError`/canonical-validator exception may escape);
ASCII/header-safety proof for the API-key value; correct
`TRANSPORT_FAILURE` vs `DNS_VERIFICATION_FAILED` classification; complete
canonical snapshot identity (binding request timing and specification
identity into the hash); structured `expected`/`observed` halt evidence;
and `build_orderbook_signing_message` current-value validation at the
public boundary.

Implementation 05 corrected: incomplete-response uncertainty (any
termination after send may have begun but before a complete terminal
response is established -- EOF, timeout, or transport exception during
headers -- is uniformly `REQUEST_RESULT_UNKNOWN`); oversized-response
lifecycle no longer claims `response_definitively_received=True`;
bounded body reception (`recv()` requests at most
`min(4096, remaining_body_capacity + 1)`); `parse_orderbook_response`
current-value revalidation at entry; complete `ValidatedDemoProfile`
revalidation including the unused WebSocket `EndpointComponents` and both
revision fields; exact-collection credential-reference-state validation
(no dict-collapse before structural checks); and direct tests proving
`expected`/`observed` halt evidence is safe and closed.

Implementation 06 (this file) corrects:

1. Provenance: this file and its paired test module now consistently
   identify as Implementation 06; the shared test authorization fixture
   no longer claims task ID Implementation 03.
2. Retained body bytes never exceed exactly `65536`: the one-byte
   overflow probe used to prove `RESPONSE_TOO_LARGE` is never appended to
   the retained body buffer -- if a received chunk contains
   `remaining_capacity + 1` bytes, only the permitted prefix is retained
   and the excess byte is discarded immediately as overflow evidence
   only.
3. Exact `EndpointComponents` field types (`scheme`/`host`/`path` exact
   `str`; `port` exact `int` excluding `bool`; the three `has_*` flags
   exact `bool`) are required at every profile/current-value gate,
   for both REST and WebSocket endpoints, before any value comparison --
   a subclass with overridden equality can no longer impersonate an
   accepted endpoint value.
4. JSON `NaN`/`Infinity`/`-Infinity` now classify as
   `RESPONSE_JSON_INVALID`, distinct from `RESPONSE_DUPLICATE_JSON_KEY`,
   via a dedicated internal exception path.
5. The public parser converts every bounded-size JSON parsing failure --
   including Python's integer-string-conversion limit and JSON
   recursion-depth limit -- into a deterministic `OrderBookHalt`; no raw
   `ValueError`/`OverflowError`/`RecursionError` escapes
   `parse_orderbook_response()` for a response within the `65536`-byte
   cap.
6. Canonical price/quantity text is produced with a value-sized local
   `decimal.Context`, never the ambient global/thread-local context --
   an accepted quantity far larger than the default 28-digit precision
   canonicalizes exactly, without rounding, without an invented magnitude
   cap, and without `decimal.InvalidOperation`.
"""

from __future__ import annotations

import base64
import decimal
import enum
import hashlib
import ipaddress
import json
import os
import queue
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from .models import (
    CredentialReferenceKind,
    CredentialReferenceState,
    EndpointComponents,
    Environment,
    RequestedCapability,
    TaskAuthorizationCapabilityEnvelope,
    ValidatedDemoProfile,
    require_usable_capability_envelope,
)

# Deliberately NOT exported from the package top level
# (`arb.venues.kalshi`). `src/arb/venues/kalshi/__init__.py` is not
# modified by this task. Callers must
# `import arb.venues.kalshi.orderbook` explicitly.
__all__ = [
    "OrderBookRestCapability",
    "OrderBookExecutionDispatchExpectation",
    "AuthenticatedOrderBookInput",
    "OrderBookOperationSourceBinding",
    "AuthenticatedOrderBookPlan",
    "OrderBookSigningMessage",
    "KalshiNativeOrderBookLevel",
    "ParsedNativeOrderBook",
    "KalshiNativeOrderBookSnapshot",
    "OrderBookHalt",
    "OrderBookHaltCode",
    "OrderBookStage",
    "SignatureLifecycleState",
    "OrderBookError",
    "OrderBookTypeError",
    "validate_ticker_grammar",
    "plan_demo_authenticated_orderbook",
    "build_orderbook_signing_message",
    "execute_demo_authenticated_orderbook",
    "parse_orderbook_response",
]

# ---------------------------------------------------------------------------
# Exact Demo origin and operation identities (Spec 5.2, 5.4, 9.2, 9.3, 11).
# ---------------------------------------------------------------------------

DEMO_HOST = "external-api.demo.kalshi.co"
DEMO_PORT = 443
DEMO_ORIGIN = "https://external-api.demo.kalshi.co"
DEMO_BASE_PATH = "/trade-api/v2"

_API_KEY_ID_ENV_VAR = "KALSHI_DEMO_API_KEY_ID"
_PRIVATE_KEY_PEM_ENV_VAR = "KALSHI_DEMO_PRIVATE_KEY_PEM"

_OVERALL_TIMEOUT_MS = 10000
_SOCKET_STAGE_TIMEOUT_MS = 5000
_MAX_RESPONSE_BYTES = 65536
_REQUEST_BUDGET = 1

_SIGNING_PROFILE = "KALSHI_RSA_PSS_SHA256_V1"
_QUERY_POLICY = "OMIT_DEPTH_AND_QUERY_STRING"
_BODY_POLICY = "ABSENT"
_ROUTE_TEMPLATE = "/markets/{ticker}/orderbook"
_FULL_PATH_TEMPLATE = "/trade-api/v2/markets/{ticker}/orderbook"

_TICKER_PATTERN = re.compile(r"[A-Za-z0-9._~-]{1,200}")
_PRICE_STRING_PATTERN = re.compile(r"[0-9]+(\.[0-9]{1,4})?")
_QUANTITY_STRING_PATTERN = re.compile(r"[0-9]+(\.[0-9]{1,2})?")
_SHA256_HEX_PATTERN = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP_MS_TEXT_PATTERN = re.compile(r"[0-9]+")
_GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{7,64}")

_PRICE_MIN = decimal.Decimal("0")
_PRICE_MAX = decimal.Decimal("1")

# ---------------------------------------------------------------------------
# Spec 5.4 / 9.2 -- exact accepted identities.
# ---------------------------------------------------------------------------

_ACCEPTED_SPEC_SHA256 = "ae8a57069a261c35c5a204d3358091c7ae3f0f9ddbe1cdbe6c8fb20f9250ead8"
_ACCEPTED_RAW_OPENAPI_SHA256 = "6e6402bf667da7596b5074ba1c687cdcb6e67f73903f49fd6b94f4b83a6a22de"
_ACCEPTED_SOURCE_BINDING_RECORD_SHA256 = (
    "295224b34fcd6adde7f54605388286e515b961eb512f631269fc2cbdd0544d0d"
)
_ACCEPTED_SOURCE_BINDING_RECORD_BYTE_LENGTH = 1556

# The exact accepted Revision-01 canonical operation-binding record (Spec
# 9.2), parsed once as the literal ground truth every caller-supplied
# record is checked against by strict, type-aware equality.
_ACCEPTED_BINDING_FIELDS = {
    "binding_schema_revision": 1,
    "effective_auth_classification": "AUTHENTICATED_READ_ONLY",
    "effective_security": [
        {
            "kalshiAccessKey": [],
            "kalshiAccessSignature": [],
            "kalshiAccessTimestamp": [],
        }
    ],
    "effective_security_source": "OPERATION_OVERRIDE",
    "http_status": 200,
    "normalized_source_media_type": "text/yaml",
    "openapi_version": "3.0.0",
    "operation_method": "GET",
    "operation_path_template": "/markets/{ticker}/orderbook",
    "operation_security_key_present": True,
    "planned_query_policy": "OMIT_DEPTH_AND_QUERY_STRING",
    "query_parameters": {
        "depth": {
            "default": 0,
            "maximum": 100,
            "minimum": 0,
            "required": False,
            "type": "integer",
        }
    },
    "raw_openapi_byte_length": 323631,
    "raw_openapi_sha256": _ACCEPTED_RAW_OPENAPI_SHA256,
    "required_auth_header_names": [
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-SIGNATURE",
        "KALSHI-ACCESS-TIMESTAMP",
    ],
    "response_200": {
        "level_shape": ["price_dollars_string", "count_fp_string"],
        "media_type": "application/json",
        "orderbook_fp_required_fields": ["no_dollars", "yes_dollars"],
        "required_top_level_fields": ["orderbook_fp"],
    },
    "retrieved_at_utc": "2026-08-08T12:41:45Z",
    "reviewed_demo_rest_origin": DEMO_ORIGIN,
    "reviewed_full_request_path_template": _FULL_PATH_TEMPLATE,
    "schema_version": 1,
    "security_scheme_names": [
        "kalshiAccessKey",
        "kalshiAccessSignature",
        "kalshiAccessTimestamp",
    ],
    "source_info_version": "3.27.0",
    "source_url": "https://docs.kalshi.com/openapi.yaml",
    "ticker_parameter": {
        "in": "path",
        "maximum_length": None,
        "minimum_length": None,
        "name": "ticker",
        "pattern": None,
        "required": True,
        "type": "string",
    },
}

_REQUIRED_AUTH_HEADER_NAMES = (
    "KALSHI-ACCESS-KEY",
    "KALSHI-ACCESS-SIGNATURE",
    "KALSHI-ACCESS-TIMESTAMP",
)

_ORDERBOOK_FP_FIELDS = frozenset({"yes_dollars", "no_dollars"})
_RESPONSE_TOP_LEVEL_FIELDS = frozenset({"orderbook_fp"})

_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Closed enums (Spec 6, 8.1, 10, 10.1, 12).
# ---------------------------------------------------------------------------


class OrderBookRestCapability(enum.StrEnum):
    """Exact operation-local capability (Spec 8.1). Never means WebSocket
    or write access; never a new broad project capability."""

    KALSHI_DEMO_AUTHENTICATED_REST_READ = "KALSHI_DEMO_AUTHENTICATED_REST_READ"


class OrderBookStage(enum.StrEnum):
    """Exact closed execution stages (Spec Section 10)."""

    PLAN_INPUT = "PLAN_INPUT"
    CAPABILITY_ENVELOPE_VALIDATED = "CAPABILITY_ENVELOPE_VALIDATED"
    PROFILE_VERIFIED = "PROFILE_VERIFIED"
    OPERATION_CAPABILITY_VERIFIED = "OPERATION_CAPABILITY_VERIFIED"
    SOURCE_RECORD_IDENTITY_VERIFIED = "SOURCE_RECORD_IDENTITY_VERIFIED"
    SOURCE_BOUND = "SOURCE_BOUND"
    TICKER_VERIFIED = "TICKER_VERIFIED"
    REQUEST_DESCRIPTION_FROZEN = "REQUEST_DESCRIPTION_FROZEN"
    PRE_DNS_CURRENT_VALUES_REVERIFIED = "PRE_DNS_CURRENT_VALUES_REVERIFIED"
    DNS_RESOLUTION_WAIT = "DNS_RESOLUTION_WAIT"
    DNS_SET_VERIFIED = "DNS_SET_VERIFIED"
    PRE_SOCKET_CURRENT_VALUES_REVERIFIED = "PRE_SOCKET_CURRENT_VALUES_REVERIFIED"
    TCP_CONNECTED_TO_PINNED_ADDRESS = "TCP_CONNECTED_TO_PINNED_ADDRESS"
    TLS_VERIFIED_FOR_DEMO_HOSTNAME = "TLS_VERIFIED_FOR_DEMO_HOSTNAME"
    PRE_SECRET_LOAD_CURRENT_VALUES_REVERIFIED = "PRE_SECRET_LOAD_CURRENT_VALUES_REVERIFIED"
    SECRETS_LOADED = "SECRETS_LOADED"
    PRE_SIGN_CURRENT_VALUES_REVERIFIED = "PRE_SIGN_CURRENT_VALUES_REVERIFIED"
    TIMESTAMP_GENERATED = "TIMESTAMP_GENERATED"
    SIGNING_MESSAGE_BUILT = "SIGNING_MESSAGE_BUILT"
    SIGNATURE_GENERATED_NOT_SENT = "SIGNATURE_GENERATED_NOT_SENT"
    PRE_SEND_CURRENT_VALUES_REVERIFIED = "PRE_SEND_CURRENT_VALUES_REVERIFIED"
    REQUEST_SEND_MAY_HAVE_BEGUN = "REQUEST_SEND_MAY_HAVE_BEGUN"
    RESPONSE_HEADERS_RECEIVED = "RESPONSE_HEADERS_RECEIVED"
    RESPONSE_BODY_RECEIVED = "RESPONSE_BODY_RECEIVED"
    RESPONSE_VALIDATED = "RESPONSE_VALIDATED"
    ORDER_BOOK_RECONSTRUCTED = "ORDER_BOOK_RECONSTRUCTED"
    SUCCEEDED = "SUCCEEDED"
    HALTED = "HALTED"


class SignatureLifecycleState(enum.StrEnum):
    """Exact signature-lifecycle vocabulary (Spec 10.1). A generated
    signature is never evidence of transmission."""

    NO_SECRET_LOADED = "NO_SECRET_LOADED"
    SECRET_LOADED_NO_SIGNATURE = "SECRET_LOADED_NO_SIGNATURE"
    SIGNATURE_GENERATED_NOT_SENT = "SIGNATURE_GENERATED_NOT_SENT"
    SEND_MAY_HAVE_BEGUN = "SEND_MAY_HAVE_BEGUN"
    RESPONSE_DEFINITIVELY_RECEIVED = "RESPONSE_DEFINITIVELY_RECEIVED"


class OrderBookHaltCode(enum.StrEnum):
    """Exact closed halt-code taxonomy (Spec Section 12)."""

    # 12.1 Planning/source/capability halts
    CANONICAL_BASE_MISMATCH = "CANONICAL_BASE_MISMATCH"
    CANONICAL_PREDECESSOR_CONFLICT = "CANONICAL_PREDECESSOR_CONFLICT"
    ORDER_BOOK_AUTHENTICATION_CONTRACT_CHANGED_OR_CONFLICTING = (
        "ORDER_BOOK_AUTHENTICATION_CONTRACT_CHANGED_OR_CONFLICTING"
    )
    SIGNING_CONTRACT_AMBIGUOUS = "SIGNING_CONTRACT_AMBIGUOUS"
    SOURCE_BINDING_INVALID = "SOURCE_BINDING_INVALID"
    SOURCE_BINDING_MISMATCH = "SOURCE_BINDING_MISMATCH"
    EXECUTION_CAPABILITY_NOT_AUTHORIZED = "EXECUTION_CAPABILITY_NOT_AUTHORIZED"
    ENVIRONMENT_NOT_AUTHORIZED = "ENVIRONMENT_NOT_AUTHORIZED"
    ENVIRONMENT_ENDPOINT_MISMATCH = "ENVIRONMENT_ENDPOINT_MISMATCH"
    PRODUCTION_ACCESS_PROHIBITED = "PRODUCTION_ACCESS_PROHIBITED"
    REST_AUTHENTICATED_READ_REQUIRED = "REST_AUTHENTICATED_READ_REQUIRED"
    MARKET_TICKER_INVALID = "MARKET_TICKER_INVALID"
    CURRENT_VALUE_MISMATCH = "CURRENT_VALUE_MISMATCH"
    REQUEST_BUDGET_EXHAUSTED = "REQUEST_BUDGET_EXHAUSTED"

    # 12.2 Credential/signing halts
    CREDENTIAL_REFERENCE_MISSING = "CREDENTIAL_REFERENCE_MISSING"
    CREDENTIAL_PLACEHOLDER = "CREDENTIAL_PLACEHOLDER"
    CREDENTIAL_NAMESPACE_MISMATCH = "CREDENTIAL_NAMESPACE_MISMATCH"
    CREDENTIAL_REFERENCE_MALFORMED = "CREDENTIAL_REFERENCE_MALFORMED"
    CREDENTIAL_NOT_REQUIRED_INVALID = "CREDENTIAL_NOT_REQUIRED_INVALID"
    SECRET_LOADING_FAILED = "SECRET_LOADING_FAILED"
    API_KEY_ID_MALFORMED = "API_KEY_ID_MALFORMED"
    PRIVATE_KEY_FORMAT_UNSUPPORTED = "PRIVATE_KEY_FORMAT_UNSUPPORTED"
    PRIVATE_KEY_TYPE_UNSUPPORTED = "PRIVATE_KEY_TYPE_UNSUPPORTED"
    TIMESTAMP_INVALID = "TIMESTAMP_INVALID"
    SIGNING_PROFILE_MISMATCH = "SIGNING_PROFILE_MISMATCH"
    SIGNING_FAILED = "SIGNING_FAILED"
    SECRET_RENDERING_PROHIBITED = "SECRET_RENDERING_PROHIBITED"

    # 12.3 Transport/HTTP halts
    DNS_VERIFICATION_FAILED = "DNS_VERIFICATION_FAILED"
    TLS_VERIFICATION_FAILED = "TLS_VERIFICATION_FAILED"
    CONNECTIVITY_TIMEOUT = "CONNECTIVITY_TIMEOUT"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    REQUEST_RESULT_UNKNOWN = "REQUEST_RESULT_UNKNOWN"
    ENDPOINT_REDIRECT_PROHIBITED = "ENDPOINT_REDIRECT_PROHIBITED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_OR_PERMISSION_FAILED = "AUTHORIZATION_OR_PERMISSION_FAILED"
    MARKET_NOT_FOUND = "MARKET_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    UNEXPECTED_HTTP_STATUS = "UNEXPECTED_HTTP_STATUS"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    RESPONSE_CONTENT_TYPE_INVALID = "RESPONSE_CONTENT_TYPE_INVALID"
    RESPONSE_ENCODING_UNSUPPORTED = "RESPONSE_ENCODING_UNSUPPORTED"

    # 12.4 Parsing halts
    RESPONSE_JSON_INVALID = "RESPONSE_JSON_INVALID"
    RESPONSE_DUPLICATE_JSON_KEY = "RESPONSE_DUPLICATE_JSON_KEY"
    ORDER_BOOK_SCHEMA_MALFORMED = "ORDER_BOOK_SCHEMA_MALFORMED"
    ORDER_BOOK_SCHEMA_SHAPE_CHANGED = "ORDER_BOOK_SCHEMA_SHAPE_CHANGED"
    ORDER_BOOK_LEVEL_MALFORMED = "ORDER_BOOK_LEVEL_MALFORMED"
    ORDER_BOOK_PRICE_INVALID = "ORDER_BOOK_PRICE_INVALID"
    ORDER_BOOK_QUANTITY_INVALID = "ORDER_BOOK_QUANTITY_INVALID"
    ORDER_BOOK_DUPLICATE_PRICE = "ORDER_BOOK_DUPLICATE_PRICE"
    ORDER_BOOK_TICKER_MISMATCH = "ORDER_BOOK_TICKER_MISMATCH"


# ---------------------------------------------------------------------------
# Exceptions.
# ---------------------------------------------------------------------------


class OrderBookError(ValueError):
    """Base class for this module's own typed validation failures. Never
    carries a secret value."""


class OrderBookTypeError(OrderBookError):
    """Raised when an object at a public boundary is not of the exact
    expected runtime type."""


class _DuplicateJsonKeyError(OrderBookError):
    """Implementation-06 correction 4: distinct from
    `_InvalidJsonConstantError` so a duplicate key can be classified as
    `RESPONSE_DUPLICATE_JSON_KEY` while a non-finite constant is
    classified as `RESPONSE_JSON_INVALID` -- the two are never
    conflated under one generic catch."""


class _InvalidJsonConstantError(OrderBookError):
    """Raised for a JSON `NaN`/`Infinity`/`-Infinity` token. Kept
    distinct from `_DuplicateJsonKeyError` (Implementation-06
    correction 4)."""


class _HaltingError(OrderBookError):
    """Internal control-flow exception carrying the exact halt code and a
    secret-safe detail string. Caught only inside this module's own
    execution boundary and converted into an `OrderBookHalt` with the
    correct stage/lifecycle/count evidence supplied at the catch site."""

    def __init__(
        self,
        code: "OrderBookHaltCode",
        detail: Optional[str] = None,
        *,
        expected: Optional[str] = None,
        observed: Optional[str] = None,
    ):
        super().__init__(detail or code.value)
        self.code = code
        self.detail = detail
        self.expected = expected
        self.observed = observed


# ---------------------------------------------------------------------------
# Small exact-type / strict-equality helpers.
# ---------------------------------------------------------------------------


def _is_exact_int(value: object) -> bool:
    return type(value) is int


def _is_exact_bool(value: object) -> bool:
    return type(value) is bool


def _is_exact_str(value: object) -> bool:
    return type(value) is str


def _is_blank(value: str) -> bool:
    return value.strip() == ""


def _capability_permitted(envelope: TaskAuthorizationCapabilityEnvelope, name: str) -> bool:
    return getattr(envelope, name).value == "PERMITTED"


def _capability_prohibited(envelope: TaskAuthorizationCapabilityEnvelope, name: str) -> bool:
    return getattr(envelope, name).value == "PROHIBITED"


def _is_sha256_hex(value: object) -> bool:
    if type(value) is not str:
        return False
    if _SHA256_HEX_PATTERN.fullmatch(value) is None:
        return False
    if value == "0" * 64:
        return False
    return True


def _strict_json_equal(a: object, b: object) -> bool:
    """Type-aware structural equality for parsed JSON values. Guards
    against Python's `bool`/`int` numeric-equality gotcha (`True == 1`)
    and against a `str` subclass presenting different real content while
    overriding equality."""

    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_strict_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_strict_json_equal(x, y) for x, y in zip(a, b))
    return a == b


def validate_ticker_grammar(ticker: object) -> bool:
    """Exact ticker grammar (Spec 8.2): built-in `str`, ASCII length
    `1..200`, characters only `[A-Za-z0-9._~-]`, case preserved, no
    normalization or percent-encoding of any kind."""

    if type(ticker) is not str:
        return False
    return _TICKER_PATTERN.fullmatch(ticker) is not None


def _api_key_id_is_header_safe(value: object) -> bool:
    """Spec 9.4/9.9, Implementation-04 correction 4: non-empty, printable
    ASCII, no CR/LF/HTTP control characters, no DEL, and no non-ASCII
    codepoint that could raise `UnicodeEncodeError` at the exact ASCII
    request serialization this implementation uses. Never stripped,
    cased, parsed, or otherwise transformed -- this function only
    checks; it never mutates the value."""

    if type(value) is not str:
        return False
    if value == "":
        return False
    if not value.isascii():
        return False
    if _CONTROL_CHAR_PATTERN.search(value) is not None:
        return False
    # Defense in depth: prove the value round-trips through the exact
    # ASCII encoding used at request-construction time before it is ever
    # accepted, so no UnicodeEncodeError can later escape from deep
    # inside header construction.
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _timestamp_ms_text_is_canonical(value: object) -> bool:
    """Spec 9.6: canonical ASCII decimal, no sign, no decimal point, no
    whitespace, no leading `+`, and (defensively) no leading zero unless
    the value is exactly `0`."""

    if type(value) is not str:
        return False
    if _TIMESTAMP_MS_TEXT_PATTERN.fullmatch(value) is None:
        return False
    if len(value) > 1 and value[0] == "0":
        return False
    return True


# ---------------------------------------------------------------------------
# OrderBookExecutionDispatchExpectation (Spec 7.2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderBookExecutionDispatchExpectation:
    gustavo_execution_authorization_id: str
    expected_raw_openapi_sha256: str
    expected_source_binding_record_sha256: str
    expected_specification_sha256: str
    expected_implementation_commit: str


def require_usable_execution_dispatch_expectation(expectation: object) -> None:
    if type(expectation) is not OrderBookExecutionDispatchExpectation:
        raise OrderBookTypeError(
            "execution dispatch expectation must have exact type "
            "OrderBookExecutionDispatchExpectation"
        )
    if not _is_exact_str(expectation.gustavo_execution_authorization_id) or _is_blank(
        expectation.gustavo_execution_authorization_id
    ):
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "gustavo_execution_authorization_id must be a non-blank str",
        )
    if not _is_exact_str(expectation.expected_implementation_commit) or (
        _GIT_COMMIT_PATTERN.fullmatch(expectation.expected_implementation_commit) is None
    ):
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "expected_implementation_commit must be a plausible git commit hex string",
        )
    if not _is_sha256_hex(expectation.expected_raw_openapi_sha256):
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "expected_raw_openapi_sha256 is malformed, blank, or placeholder",
        )
    if not _is_sha256_hex(expectation.expected_source_binding_record_sha256):
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "expected_source_binding_record_sha256 is malformed, blank, or placeholder",
        )
    if not _is_sha256_hex(expectation.expected_specification_sha256):
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "expected_specification_sha256 is malformed, blank, or placeholder",
        )
    # Current-value pin against the one accepted Revision-01 identities.
    if expectation.expected_specification_sha256 != _ACCEPTED_SPEC_SHA256:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_MISMATCH,
            "expected_specification_sha256 does not equal the accepted spec identity",
        )
    if expectation.expected_raw_openapi_sha256 != _ACCEPTED_RAW_OPENAPI_SHA256:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_MISMATCH,
            "expected_raw_openapi_sha256 does not equal the accepted raw OpenAPI identity",
        )
    if expectation.expected_source_binding_record_sha256 != _ACCEPTED_SOURCE_BINDING_RECORD_SHA256:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_MISMATCH,
            "expected_source_binding_record_sha256 does not equal the accepted record identity",
        )


# ---------------------------------------------------------------------------
# Operation-specific source binding (Spec 9.2) -- exact accepted record
# only, validated by strict type-aware equality against the literal
# accepted field set. No connectivity-style substitute fields.
# ---------------------------------------------------------------------------


def _reject_duplicate_keys(pairs):
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        seen.add(key)
        result[key] = value
    return result


def _reject_json_constant(token: str):
    raise _InvalidJsonConstantError(f"non-finite JSON constant is prohibited: {token}")


def _canonical_record_bytes(record: dict) -> bytes:
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class OrderBookOperationSourceBinding:
    """Internal derived result: the exact accepted Section-9.2 record
    fields, revalidated at every use-time consumption gate by rehashing/
    re-parsing the retained canonical record bytes."""

    binding_schema_revision: int
    effective_auth_classification: str
    effective_security: tuple
    effective_security_source: str
    http_status: int
    normalized_source_media_type: str
    openapi_version: str
    operation_method: str
    operation_path_template: str
    operation_security_key_present: bool
    planned_query_policy: str
    query_parameters: tuple
    raw_openapi_byte_length: int
    raw_openapi_sha256: str
    required_auth_header_names: tuple
    response_200: tuple
    retrieved_at_utc: str
    reviewed_demo_rest_origin: str
    reviewed_full_request_path_template: str
    schema_version: int
    security_scheme_names: tuple
    source_info_version: str
    source_url: str
    ticker_parameter: tuple
    source_binding_record_sha256: str
    source_binding_record_byte_length: int


def _freeze(value):
    """Recursively converts parsed-JSON dict/list structures into
    hashable tuples-of-pairs so the derived binding fields can live on a
    frozen dataclass while strict equality checks are still performed on
    the original parsed dict/list forms before freezing."""

    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _parse_source_binding_record_bytes(record_bytes: bytes) -> dict:
    if type(record_bytes) is not bytes:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "source_binding_record_bytes must be bytes",
        )
    try:
        text = record_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID, "record is not valid UTF-8"
        ) from exc
    try:
        record = json.loads(
            text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_json_constant
        )
    except (json.JSONDecodeError, OrderBookError) as exc:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID, "record is not valid JSON"
        ) from exc
    if not isinstance(record, dict):
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID, "record top level must be an object"
        )
    observed_fields = set(record.keys())
    accepted_fields = set(_ACCEPTED_BINDING_FIELDS.keys())
    unknown = observed_fields - accepted_fields
    if unknown:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            f"record contains unknown fields: {sorted(unknown)}",
        )
    missing = accepted_fields - observed_fields
    if missing:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            f"record is missing fields: {sorted(missing)}",
        )
    return record


def _derive_order_book_source_binding_fields(
    record_bytes: bytes, expectation: OrderBookExecutionDispatchExpectation
) -> dict:
    require_usable_execution_dispatch_expectation(expectation)

    if type(record_bytes) is not bytes or len(record_bytes) == 0:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID, "source_binding_record_bytes missing or empty"
        )
    if len(record_bytes) != _ACCEPTED_SOURCE_BINDING_RECORD_BYTE_LENGTH:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_MISMATCH,
            f"record byte length must be exactly {_ACCEPTED_SOURCE_BINDING_RECORD_BYTE_LENGTH}",
        )

    observed_record_sha256 = hashlib.sha256(record_bytes).hexdigest()
    if observed_record_sha256 != _ACCEPTED_SOURCE_BINDING_RECORD_SHA256:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_MISMATCH,
            "record hash does not equal the accepted record identity",
        )
    if observed_record_sha256 != expectation.expected_source_binding_record_sha256:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_MISMATCH,
            "record hash does not equal expectation.expected_source_binding_record_sha256",
        )

    record = _parse_source_binding_record_bytes(record_bytes)

    if _canonical_record_bytes(record) != record_bytes:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "record bytes are not the exact canonical serialization",
        )

    if not _strict_json_equal(record, _ACCEPTED_BINDING_FIELDS):
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_MISMATCH,
            "record does not exactly equal the accepted Section 9.2 record",
        )

    fields = {key: _freeze(value) if isinstance(value, (dict, list)) else value for key, value in record.items()}
    fields["source_binding_record_sha256"] = observed_record_sha256
    fields["source_binding_record_byte_length"] = len(record_bytes)
    return fields


def require_usable_order_book_source_binding(
    binding: object,
    expectation: OrderBookExecutionDispatchExpectation,
    record_bytes: object,
) -> None:
    if type(binding) is not OrderBookOperationSourceBinding:
        raise OrderBookTypeError(
            "source binding must have exact type OrderBookOperationSourceBinding"
        )
    if type(record_bytes) is not bytes:
        raise _HaltingError(
            OrderBookHaltCode.SOURCE_BINDING_INVALID,
            "retained source_binding_record_bytes must have exact type bytes",
        )
    authoritative = _derive_order_book_source_binding_fields(record_bytes, expectation)
    for field_name, authoritative_value in authoritative.items():
        current_value = getattr(binding, field_name)
        if type(current_value) is not type(authoritative_value):
            raise _HaltingError(
                OrderBookHaltCode.CURRENT_VALUE_MISMATCH,
                f"source binding field {field_name!r} no longer has its derived exact type",
            )
        if current_value != authoritative_value:
            raise _HaltingError(
                OrderBookHaltCode.CURRENT_VALUE_MISMATCH,
                f"source binding field {field_name!r} no longer matches the canonical record",
            )


# ---------------------------------------------------------------------------
# Planning input / plan (Spec 7.1, 7.3).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthenticatedOrderBookInput:
    """Exact accepted input (Spec 7.1). No URL, host, port, method,
    query, headers, timeout, retry/redirect policy, resolver, socket,
    TLS context, transport, session, signer, private key, API-key value,
    body, callback, or market list is caller-supplied."""

    validated_demo_profile: ValidatedDemoProfile
    authorization_envelope: TaskAuthorizationCapabilityEnvelope
    operation_capability: OrderBookRestCapability
    market_ticker: str
    source_binding_record_bytes: bytes
    execution_dispatch_expectation: OrderBookExecutionDispatchExpectation


@dataclass(frozen=True, slots=True)
class AuthenticatedOrderBookPlan:
    """Exact accepted plan (Spec 7.3). Contains no credential secret
    value, signature, or live transport."""

    validated_demo_profile: ValidatedDemoProfile
    authorization_envelope: TaskAuthorizationCapabilityEnvelope
    operation_capability: OrderBookRestCapability
    market_ticker: str
    source_binding_record_bytes: bytes
    source_binding: OrderBookOperationSourceBinding
    execution_dispatch_expectation: OrderBookExecutionDispatchExpectation
    host: str
    port: int
    base_path: str
    method: str
    route_template: str
    full_path: str
    query_policy: str
    body_policy: str
    request_budget: int
    retry_count: int
    redirects_enabled: bool
    proxy_enabled: bool
    cookies_enabled: bool
    ambient_auth_enabled: bool
    response_body_cap: int
    overall_deadline_ms: int
    socket_stage_cap_ms: int
    signing_profile: str


_PROHIBITED_ENVELOPE_FIELDS = (
    "demo_writes",
    "production_public_reads",
    "production_authenticated_reads",
    "production_writes",
    "account_funding",
)


_ACCEPTED_ALLOWLIST_REVISION = "candidate-02"
_ACCEPTED_VALIDATION_SCHEMA_REVISION = 1
DEMO_WEBSOCKET_HOST = "external-api-ws.demo.kalshi.co"
DEMO_WEBSOCKET_PATH = "/trade-api/ws/v2"

_ACCEPTED_CREDENTIAL_KINDS = (
    CredentialReferenceKind.API_KEY_ID_ENV_SOURCE,
    CredentialReferenceKind.PRIVATE_KEY_PEM_ENV_SOURCE,
)


def _require_exact_endpoint_component_field_types(ep: object, label: str) -> None:
    """Implementation-06 correction 3: require exact built-in field
    types on an `EndpointComponents` object *before* any value
    comparison, so a subclass with overridden `__eq__`/protocol methods
    can never impersonate an accepted endpoint value. `port` excludes
    `bool` and any other `int` subclass -- `type(x) is int`, not
    `isinstance`, since `isinstance(True, int)` is `True` in Python."""

    if type(ep.scheme) is not str:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, f"{label}.scheme type")
    if type(ep.host) is not str:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, f"{label}.host type")
    if type(ep.port) is not int:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, f"{label}.port type")
    if type(ep.path) is not str:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, f"{label}.path type")
    if type(ep.has_user_info) is not bool:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, f"{label}.has_user_info type")
    if type(ep.has_query) is not bool:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, f"{label}.has_query type")
    if type(ep.has_fragment) is not bool:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, f"{label}.has_fragment type")


def _require_usable_authenticated_profile(profile: object) -> None:
    """Local, operation-specific current-value gate for
    `ValidatedDemoProfile` (Spec 5.2/9.8): unlike the public
    `/exchange/status` connectivity binding, this operation requires
    `effective_capability == DEMO_AUTHENTICATED_READ` and both credential
    references present as exact Demo `CONFIGURED` -- never empty or
    `NOT_REQUIRED`.

    Implementation-05 correction 5: validates the *complete* accepted
    profile -- including the WebSocket `EndpointComponents` (unused by
    this REST-only operation; validating its current values authorizes
    no WebSocket activity) and the exact accepted
    `allowlist_revision`/`validation_schema_revision` -- not merely the
    REST endpoint and capability fields."""

    if type(profile) is not ValidatedDemoProfile:
        raise OrderBookTypeError("profile must have exact type ValidatedDemoProfile")
    if profile.environment is not Environment.KALSHI_DEMO:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_NOT_AUTHORIZED)
    if profile.requested_capability is not RequestedCapability.DEMO_AUTHENTICATED_READ:
        raise _HaltingError(OrderBookHaltCode.REST_AUTHENTICATED_READ_REQUIRED)
    if profile.effective_capability is not RequestedCapability.DEMO_AUTHENTICATED_READ:
        raise _HaltingError(OrderBookHaltCode.REST_AUTHENTICATED_READ_REQUIRED)
    if profile.secret_loaded is not False:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "profile.secret_loaded")
    if profile.transport_constructed is not False:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "profile.transport_constructed")
    if profile.network_request_sent is not False:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "profile.network_request_sent")

    if type(profile.rest) is not EndpointComponents:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.rest")
    _require_exact_endpoint_component_field_types(profile.rest, "profile.rest")
    if profile.rest.scheme != "https" or profile.rest.host != DEMO_HOST or profile.rest.port != DEMO_PORT:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH)
    if profile.rest.path != DEMO_BASE_PATH:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH)
    if profile.rest.has_user_info is not False or profile.rest.has_query is not False or profile.rest.has_fragment is not False:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.rest flags")

    # Not used for any network activity by this REST-only operation --
    # validated only so a mutated/production/malformed WebSocket endpoint
    # is grounds for rejection, exactly like the REST endpoint is.
    if type(profile.websocket) is not EndpointComponents:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.websocket")
    _require_exact_endpoint_component_field_types(profile.websocket, "profile.websocket")
    if profile.websocket.scheme != "wss":
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.websocket.scheme")
    if profile.websocket.host != DEMO_WEBSOCKET_HOST:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.websocket.host")
    if profile.websocket.port != DEMO_PORT:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.websocket.port")
    if profile.websocket.path != DEMO_WEBSOCKET_PATH:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.websocket.path")
    if (
        profile.websocket.has_user_info is not False
        or profile.websocket.has_query is not False
        or profile.websocket.has_fragment is not False
    ):
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "profile.websocket flags")

    if not _is_exact_str(profile.allowlist_revision) or profile.allowlist_revision != _ACCEPTED_ALLOWLIST_REVISION:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "profile.allowlist_revision")
    if (
        not _is_exact_int(profile.validation_schema_revision)
        or profile.validation_schema_revision != _ACCEPTED_VALIDATION_SCHEMA_REVISION
    ):
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "profile.validation_schema_revision")

    # Implementation-05 correction 6: exact-collection validation --
    # per-entry shape/type and absence of duplicate kinds are checked
    # structurally *before* any dict is built, so a duplicate kind entry
    # can never be silently collapsed away. Missing vs. extra/malformed
    # kinds are then distinguished by set difference against the exact
    # accepted two-kind collection, rather than a single coarse length
    # check that could not tell "too few" from "too many".
    states = profile.credential_reference_states
    if type(states) is not tuple:
        raise OrderBookTypeError("profile.credential_reference_states must be tuple")

    seen_kinds = []
    parsed_states = {}
    for entry in states:
        if type(entry) is not tuple or len(entry) != 2:
            raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED, "malformed entry shape")
        kind, state = entry
        if type(kind) is not CredentialReferenceKind or type(state) is not CredentialReferenceState:
            raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED, "malformed entry type")
        if kind in seen_kinds:
            raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED, "duplicate credential kind")
        seen_kinds.append(kind)
        parsed_states[kind] = state

    accepted_set = set(_ACCEPTED_CREDENTIAL_KINDS)
    seen_set = set(seen_kinds)

    extra_kinds = seen_set - accepted_set
    if extra_kinds:
        raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED, "unexpected credential kind present")

    missing_kinds = accepted_set - seen_set
    if missing_kinds:
        raise _HaltingError(
            OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING,
            "credential_reference_states is missing a required kind",
        )

    for kind in _ACCEPTED_CREDENTIAL_KINDS:
        state = parsed_states[kind]
        if state is CredentialReferenceState.MISSING:
            raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING)
        if state is CredentialReferenceState.PLACEHOLDER:
            raise _HaltingError(OrderBookHaltCode.CREDENTIAL_PLACEHOLDER)
        if state is CredentialReferenceState.NOT_REQUIRED:
            raise _HaltingError(OrderBookHaltCode.CREDENTIAL_NOT_REQUIRED_INVALID)
        if state is not CredentialReferenceState.CONFIGURED:
            raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MALFORMED)


def require_usable_authenticated_order_book_plan(plan: object) -> None:
    if type(plan) is not AuthenticatedOrderBookPlan:
        raise OrderBookTypeError("plan must have exact type AuthenticatedOrderBookPlan")

    _require_usable_authenticated_profile(plan.validated_demo_profile)

    try:
        require_usable_capability_envelope(plan.authorization_envelope)
    except Exception as exc:
        # The canonical validator raises its own exception types (e.g.
        # CapabilityEnvelopeTypeError), not this module's _HaltingError.
        # Convert deterministically here so every caller of this gate
        # function can rely on catching only _HaltingError/OrderBookTypeError.
        raise _HaltingError(
            OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED, "authorization_envelope"
        ) from exc
    envelope = plan.authorization_envelope
    if not _capability_permitted(envelope, "network_access"):
        raise _HaltingError(OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED, "network_access")
    if not _capability_permitted(envelope, "demo_authenticated_reads"):
        raise _HaltingError(
            OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED, "demo_authenticated_reads"
        )
    if not _capability_permitted(envelope, "credential_use"):
        raise _HaltingError(OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED, "credential_use")
    for prohibited_field in _PROHIBITED_ENVELOPE_FIELDS:
        if not _capability_prohibited(envelope, prohibited_field):
            raise _HaltingError(OrderBookHaltCode.PRODUCTION_ACCESS_PROHIBITED, prohibited_field)

    if type(plan.operation_capability) is not OrderBookRestCapability:
        raise OrderBookTypeError("plan.operation_capability must have exact type OrderBookRestCapability")
    if plan.operation_capability is not OrderBookRestCapability.KALSHI_DEMO_AUTHENTICATED_REST_READ:
        raise _HaltingError(OrderBookHaltCode.REST_AUTHENTICATED_READ_REQUIRED)

    require_usable_order_book_source_binding(
        plan.source_binding, plan.execution_dispatch_expectation, plan.source_binding_record_bytes
    )

    if not validate_ticker_grammar(plan.market_ticker):
        raise _HaltingError(OrderBookHaltCode.MARKET_TICKER_INVALID)
    if not _is_exact_str(plan.host) or plan.host != DEMO_HOST:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "host")
    if not _is_exact_int(plan.port) or plan.port != DEMO_PORT:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "port")
    if not _is_exact_str(plan.base_path) or plan.base_path != DEMO_BASE_PATH:
        raise _HaltingError(OrderBookHaltCode.ENVIRONMENT_ENDPOINT_MISMATCH, "base_path")
    if not _is_exact_str(plan.method) or plan.method != "GET":
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "method")
    if not _is_exact_str(plan.route_template) or plan.route_template != _ROUTE_TEMPLATE:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "route_template")

    expected_full_path = f"/trade-api/v2/markets/{plan.market_ticker}/orderbook"
    if not _is_exact_str(plan.full_path) or plan.full_path != expected_full_path:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "full_path")
    if not _is_exact_str(plan.query_policy) or plan.query_policy != _QUERY_POLICY:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "query_policy")
    if not _is_exact_str(plan.body_policy) or plan.body_policy != _BODY_POLICY:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "body_policy")
    if not _is_exact_int(plan.request_budget) or plan.request_budget != _REQUEST_BUDGET:
        raise _HaltingError(OrderBookHaltCode.REQUEST_BUDGET_EXHAUSTED)
    if not _is_exact_int(plan.retry_count) or plan.retry_count != 0:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "retry_count")
    if plan.redirects_enabled is not False:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "redirects_enabled")
    if plan.proxy_enabled is not False:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "proxy_enabled")
    if plan.cookies_enabled is not False:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "cookies_enabled")
    if plan.ambient_auth_enabled is not False:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "ambient_auth_enabled")
    if not _is_exact_int(plan.response_body_cap) or plan.response_body_cap != _MAX_RESPONSE_BYTES:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "response_body_cap")
    if not _is_exact_int(plan.overall_deadline_ms) or plan.overall_deadline_ms != _OVERALL_TIMEOUT_MS:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "overall_deadline_ms")
    if not _is_exact_int(plan.socket_stage_cap_ms) or plan.socket_stage_cap_ms != _SOCKET_STAGE_TIMEOUT_MS:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "socket_stage_cap_ms")
    if not _is_exact_str(plan.signing_profile) or plan.signing_profile != _SIGNING_PROFILE:
        raise _HaltingError(OrderBookHaltCode.SIGNING_PROFILE_MISMATCH)

    for forbidden in (
        "transport", "session", "resolver", "socket", "ssl_context", "client", "callback",
        "connection_factory", "signer", "private_key", "api_key", "api_key_id",
    ):
        if hasattr(plan, forbidden):
            raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, f"forbidden field: {forbidden}")


def plan_demo_authenticated_orderbook(
    input_data: object,
) -> Union[AuthenticatedOrderBookPlan, "OrderBookHalt"]:
    """Pure and offline (Spec 9.1): performs no DNS, socket, TLS, HTTP,
    or environment-variable activity of any kind."""

    if type(input_data) is not AuthenticatedOrderBookInput:
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.PLAN_INPUT)

    try:
        _require_usable_authenticated_profile(input_data.validated_demo_profile)
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.PROFILE_VERIFIED, detail=exc.detail,
                     expected=exc.expected, observed=exc.observed)
    except OrderBookTypeError:
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.PROFILE_VERIFIED)
    except Exception:
        # Fail-closed backstop: any unexpected exception (AttributeError,
        # TypeError, etc.) from a mutated/malformed profile must never
        # escape as a raw exception.
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.PROFILE_VERIFIED)

    try:
        require_usable_capability_envelope(input_data.authorization_envelope)
    except Exception:
        return _halt(
            OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED,
            OrderBookStage.CAPABILITY_ENVELOPE_VALIDATED,
        )
    envelope = input_data.authorization_envelope
    if not _capability_permitted(envelope, "network_access"):
        return _halt(
            OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED,
            OrderBookStage.CAPABILITY_ENVELOPE_VALIDATED,
            detail="network_access", expected="PERMITTED", observed=envelope.network_access.value,
        )
    if not _capability_permitted(envelope, "demo_authenticated_reads"):
        return _halt(
            OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED,
            OrderBookStage.CAPABILITY_ENVELOPE_VALIDATED,
            detail="demo_authenticated_reads", expected="PERMITTED",
            observed=envelope.demo_authenticated_reads.value,
        )
    if not _capability_permitted(envelope, "credential_use"):
        return _halt(
            OrderBookHaltCode.EXECUTION_CAPABILITY_NOT_AUTHORIZED,
            OrderBookStage.CAPABILITY_ENVELOPE_VALIDATED,
            detail="credential_use", expected="PERMITTED", observed=envelope.credential_use.value,
        )
    for prohibited_field in _PROHIBITED_ENVELOPE_FIELDS:
        if not _capability_prohibited(envelope, prohibited_field):
            return _halt(
                OrderBookHaltCode.PRODUCTION_ACCESS_PROHIBITED,
                OrderBookStage.CAPABILITY_ENVELOPE_VALIDATED,
                detail=prohibited_field, expected="PROHIBITED",
                observed=getattr(envelope, prohibited_field).value,
            )

    if type(input_data.operation_capability) is not OrderBookRestCapability:
        return _halt(
            OrderBookHaltCode.REST_AUTHENTICATED_READ_REQUIRED,
            OrderBookStage.OPERATION_CAPABILITY_VERIFIED,
        )
    if input_data.operation_capability is not OrderBookRestCapability.KALSHI_DEMO_AUTHENTICATED_REST_READ:
        return _halt(
            OrderBookHaltCode.REST_AUTHENTICATED_READ_REQUIRED,
            OrderBookStage.OPERATION_CAPABILITY_VERIFIED,
        )

    try:
        binding_fields = _derive_order_book_source_binding_fields(
            input_data.source_binding_record_bytes, input_data.execution_dispatch_expectation
        )
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.SOURCE_RECORD_IDENTITY_VERIFIED, detail=exc.detail,
                     expected=exc.expected, observed=exc.observed)
    except OrderBookTypeError:
        return _halt(OrderBookHaltCode.SOURCE_BINDING_INVALID, OrderBookStage.SOURCE_RECORD_IDENTITY_VERIFIED)
    except Exception:
        return _halt(OrderBookHaltCode.SOURCE_BINDING_INVALID, OrderBookStage.SOURCE_RECORD_IDENTITY_VERIFIED)

    binding = OrderBookOperationSourceBinding(**binding_fields)

    if not validate_ticker_grammar(input_data.market_ticker):
        return _halt(OrderBookHaltCode.MARKET_TICKER_INVALID, OrderBookStage.TICKER_VERIFIED)

    full_path = f"/trade-api/v2/markets/{input_data.market_ticker}/orderbook"

    plan = AuthenticatedOrderBookPlan(
        validated_demo_profile=input_data.validated_demo_profile,
        authorization_envelope=envelope,
        operation_capability=input_data.operation_capability,
        market_ticker=input_data.market_ticker,
        source_binding_record_bytes=input_data.source_binding_record_bytes,
        source_binding=binding,
        execution_dispatch_expectation=input_data.execution_dispatch_expectation,
        host=DEMO_HOST,
        port=DEMO_PORT,
        base_path=DEMO_BASE_PATH,
        method="GET",
        route_template=_ROUTE_TEMPLATE,
        full_path=full_path,
        query_policy=_QUERY_POLICY,
        body_policy=_BODY_POLICY,
        request_budget=_REQUEST_BUDGET,
        retry_count=0,
        redirects_enabled=False,
        proxy_enabled=False,
        cookies_enabled=False,
        ambient_auth_enabled=False,
        response_body_cap=_MAX_RESPONSE_BYTES,
        overall_deadline_ms=_OVERALL_TIMEOUT_MS,
        socket_stage_cap_ms=_SOCKET_STAGE_TIMEOUT_MS,
        signing_profile=_SIGNING_PROFILE,
    )

    try:
        require_usable_authenticated_order_book_plan(plan)
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.REQUEST_DESCRIPTION_FROZEN, detail=exc.detail,
                     expected=exc.expected, observed=exc.observed)
    except OrderBookTypeError:
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.REQUEST_DESCRIPTION_FROZEN)
    except Exception:
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.REQUEST_DESCRIPTION_FROZEN)

    return plan


# ---------------------------------------------------------------------------
# Signing message (Spec 9.5, 9.7).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderBookSigningMessage:
    """Bound exactly to the plan it was built for (Spec 9.7). The private
    signer rejects any message whose bound fields differ from the
    current plan."""

    operation_capability: OrderBookRestCapability
    method: str
    host: str
    route_template: str
    full_path: str
    ticker: str
    query_policy: str
    source_binding_record_sha256: str
    signing_profile: str
    timestamp_ms_text: str
    message_bytes: bytes


def build_orderbook_signing_message(
    plan: "AuthenticatedOrderBookPlan", timestamp_ms_text: str
) -> OrderBookSigningMessage:
    """Pure and secret-free (Spec 9.7): exact
    `timestamp_ms_text + method + full_path` bytes, with no separator, no
    hostname, no query, and no body.

    Implementation-04 correction 8: validates the complete current plan
    (method, route, base/full path, ticker, operation capability, source
    binding, query policy, signing profile) before constructing any
    bytes. A plan whose accepted contract has been mutated away is
    rejected here, at the public builder boundary, independently of the
    private signer's own binding check performed later at sign time."""

    if type(plan) is not AuthenticatedOrderBookPlan:
        raise OrderBookTypeError("plan must have exact type AuthenticatedOrderBookPlan")
    try:
        require_usable_authenticated_order_book_plan(plan)
    except _HaltingError:
        raise
    except OrderBookTypeError:
        raise
    except Exception as exc:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "plan failed current-value validation") from exc
    if not _timestamp_ms_text_is_canonical(timestamp_ms_text):
        raise _HaltingError(OrderBookHaltCode.TIMESTAMP_INVALID)

    message_text = timestamp_ms_text + plan.method + plan.full_path
    message_bytes = message_text.encode("utf-8")

    return OrderBookSigningMessage(
        operation_capability=plan.operation_capability,
        method=plan.method,
        host=plan.host,
        route_template=plan.route_template,
        full_path=plan.full_path,
        ticker=plan.market_ticker,
        query_policy=plan.query_policy,
        source_binding_record_sha256=plan.source_binding.source_binding_record_sha256,
        signing_profile=plan.signing_profile,
        timestamp_ms_text=timestamp_ms_text,
        message_bytes=message_bytes,
    )


def _require_signing_message_bound_to_plan(
    signing_message: OrderBookSigningMessage, plan: AuthenticatedOrderBookPlan
) -> None:
    if type(signing_message) is not OrderBookSigningMessage:
        raise OrderBookTypeError("signing message must have exact type OrderBookSigningMessage")
    if signing_message.operation_capability is not plan.operation_capability:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing capability mismatch")
    if signing_message.method != plan.method:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing method mismatch")
    if signing_message.host != plan.host:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing host mismatch")
    if signing_message.route_template != plan.route_template:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing route mismatch")
    if signing_message.full_path != plan.full_path:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing full_path mismatch")
    if signing_message.ticker != plan.market_ticker:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing ticker mismatch")
    if signing_message.query_policy != plan.query_policy:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing query_policy mismatch")
    if signing_message.source_binding_record_sha256 != plan.source_binding.source_binding_record_sha256:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing source binding mismatch")
    if signing_message.signing_profile != plan.signing_profile:
        raise _HaltingError(OrderBookHaltCode.SIGNING_PROFILE_MISMATCH)
    expected_bytes = (
        signing_message.timestamp_ms_text + plan.method + plan.full_path
    ).encode("utf-8")
    if signing_message.message_bytes != expected_bytes:
        raise _HaltingError(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, "signing message bytes mismatch")


# ---------------------------------------------------------------------------
# Ephemeral secrets and private signer (Spec 9.9, 15.2). Only this
# execution path ever receives a secret value.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class _EphemeralOrderBookSecrets:
    api_key_id: str
    private_key_pem: bytes

    def __repr__(self) -> str:  # never render secret content
        return "_EphemeralOrderBookSecrets(REDACTED)"

    def __str__(self) -> str:
        return self.__repr__()


def _load_api_key_id() -> str:
    """Private and narrow (Spec 9.9). Reads exactly the one named
    environment value, once, with no fallback name. Split out from
    `_load_demo_orderbook_secrets` (Implementation-04 correction 1) so
    the executor can distinguish "neither secret loaded" from "the
    API-key value loaded but the private key did not" and report the
    factually correct signature-lifecycle state."""

    api_key_id = os.environ.get(_API_KEY_ID_ENV_VAR)
    if api_key_id is None:
        raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING, "api_key_id")
    if not _api_key_id_is_header_safe(api_key_id):
        raise _HaltingError(OrderBookHaltCode.API_KEY_ID_MALFORMED)
    return api_key_id


def _load_private_key_pem() -> bytes:
    """Private and narrow (Spec 9.9). Reads exactly the one named
    environment value, once, with no fallback name."""

    private_key_pem_text = os.environ.get(_PRIVATE_KEY_PEM_ENV_VAR)
    if private_key_pem_text is None:
        raise _HaltingError(OrderBookHaltCode.CREDENTIAL_REFERENCE_MISSING, "private_key_pem")
    return private_key_pem_text.encode("utf-8")


def _load_demo_orderbook_secrets(plan: AuthenticatedOrderBookPlan) -> _EphemeralOrderBookSecrets:
    """Private and narrow (Spec 9.9). Convenience wrapper reading both
    named environment values, once each, and does not enumerate
    environment variables or use fallback names. Callable only after the
    complete non-secret gate, DNS verification, and Demo-host TLS
    verification have succeeded. The executor itself calls
    `_load_api_key_id`/`_load_private_key_pem` directly (not this
    wrapper) so it can track partial-load lifecycle state; this wrapper
    exists for callers that only need the all-or-nothing pair."""

    api_key_id = _load_api_key_id()
    private_key_pem = _load_private_key_pem()
    return _EphemeralOrderBookSecrets(api_key_id=api_key_id, private_key_pem=private_key_pem)


def _sign_orderbook_message(
    signing_message: OrderBookSigningMessage,
    plan: AuthenticatedOrderBookPlan,
    secrets: _EphemeralOrderBookSecrets,
) -> bytes:
    """Private and narrow (Spec 9.7, 15.2). Accepts only an
    `OrderBookSigningMessage` bound exactly to `plan`; never a generic
    `sign(bytes)` surface. Returns the raw RSA-PSS signature bytes."""

    _require_signing_message_bound_to_plan(signing_message, plan)

    try:
        private_key = load_pem_private_key(secrets.private_key_pem, password=None)
    except Exception as exc:
        raise _HaltingError(OrderBookHaltCode.PRIVATE_KEY_FORMAT_UNSUPPORTED) from exc

    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise _HaltingError(OrderBookHaltCode.PRIVATE_KEY_TYPE_UNSUPPORTED)

    try:
        signature = private_key.sign(
            signing_message.message_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
    except Exception as exc:
        raise _HaltingError(OrderBookHaltCode.SIGNING_FAILED) from exc
    finally:
        private_key = None

    return signature


# ---------------------------------------------------------------------------
# Immutable native order-book types (Spec 7.4, 8.3-8.6).
# ---------------------------------------------------------------------------


def _safe_quantize(value: decimal.Decimal, exponent: decimal.Decimal) -> decimal.Decimal:
    """Implementation-06 correction 6: quantizes using a local
    `decimal.Context` sized deterministically from the value's own
    digit count -- never the ambient global/thread-local context. Since
    `value` already has at most as many fractional digits as
    `exponent`'s scale (enforced by the accepted price/quantity lexical
    grammar before this is ever called), quantizing only pads trailing
    zero digits and never rounds; the only way this can fail is if the
    context's `prec` is smaller than the resulting coefficient length,
    which a fixed/ambient default (28) cannot guarantee for an
    arbitrarily large accepted quantity. The local context is sized with
    a generous safety margin and never mutates any global/thread-local
    Decimal state."""

    _, digits, _ = value.as_tuple()
    local_prec = max(len(digits) + 16, 32)
    local_context = decimal.Context(prec=local_prec)
    return value.quantize(exponent, context=local_context)


@dataclass(frozen=True, slots=True)
class KalshiNativeOrderBookLevel:
    price: decimal.Decimal
    quantity: decimal.Decimal

    def __post_init__(self) -> None:
        if type(self.price) is not decimal.Decimal or type(self.quantity) is not decimal.Decimal:
            raise OrderBookTypeError("price and quantity must have exact type Decimal")
        if self.price < _PRICE_MIN or self.price > _PRICE_MAX:
            raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID, "price out of [0,1]")
        if self.quantity <= 0:
            raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_QUANTITY_INVALID, "quantity must be positive")

    def canonical_price_str(self) -> str:
        return str(_safe_quantize(self.price, decimal.Decimal("0.0001")))

    def canonical_quantity_str(self) -> str:
        return str(_safe_quantize(self.quantity, decimal.Decimal("0.01")))


@dataclass(frozen=True, slots=True)
class ParsedNativeOrderBook:
    """Return type of `parse_orderbook_response` (Spec 9.1)."""

    yes_levels: Tuple[KalshiNativeOrderBookLevel, ...] = ()
    no_levels: Tuple[KalshiNativeOrderBookLevel, ...] = ()

    def __post_init__(self) -> None:
        for levels in (self.yes_levels, self.no_levels):
            if type(levels) is not tuple:
                raise OrderBookTypeError("levels must have exact type tuple")
            for level in levels:
                if type(level) is not KalshiNativeOrderBookLevel:
                    raise OrderBookTypeError("each level must have exact type KalshiNativeOrderBookLevel")
            prices = [level.price for level in levels]
            if len(set(prices)) != len(prices):
                raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_DUPLICATE_PRICE)
            if list(prices) != sorted(prices):
                raise OrderBookError("levels are not in canonical ascending-price order")


@dataclass(frozen=True, slots=True)
class KalshiNativeOrderBookSnapshot:
    """Exact accepted Revision-01 success object (Spec 7.4)."""

    environment: str
    market_ticker: str
    method: str
    route_template: str
    full_request_path: str
    endpoint_classification: str
    request_timestamp_ms: int
    request_started_monotonic_ns: int
    request_completed_monotonic_ns: int
    yes_levels: Tuple[KalshiNativeOrderBookLevel, ...]
    no_levels: Tuple[KalshiNativeOrderBookLevel, ...]
    canonical_level_ordering: str
    response_byte_length: int
    response_sha256: str
    raw_openapi_sha256: str
    source_binding_record_sha256: str
    request_count: int
    retry_count: int
    redirect_count: int
    gustavo_execution_authorization_id: str
    expected_implementation_commit: str
    specification_sha256: str
    canonical_snapshot_sha256: str = ""

    def _canonical_dict(self) -> dict:
        def levels_to_list(levels):
            return [[lvl.canonical_price_str(), lvl.canonical_quantity_str()] for lvl in levels]

        return {
            "environment": self.environment,
            "market_ticker": self.market_ticker,
            "method": self.method,
            "route_template": self.route_template,
            "full_request_path": self.full_request_path,
            "endpoint_classification": self.endpoint_classification,
            "request_timestamp_ms": self.request_timestamp_ms,
            "request_started_monotonic_ns": self.request_started_monotonic_ns,
            "request_completed_monotonic_ns": self.request_completed_monotonic_ns,
            "yes_levels": levels_to_list(self.yes_levels),
            "no_levels": levels_to_list(self.no_levels),
            "canonical_level_ordering": self.canonical_level_ordering,
            "response_byte_length": self.response_byte_length,
            "response_sha256": self.response_sha256,
            "raw_openapi_sha256": self.raw_openapi_sha256,
            "source_binding_record_sha256": self.source_binding_record_sha256,
            "request_count": self.request_count,
            "retry_count": self.retry_count,
            "redirect_count": self.redirect_count,
            "gustavo_execution_authorization_id": self.gustavo_execution_authorization_id,
            "expected_implementation_commit": self.expected_implementation_commit,
            "specification_sha256": self.specification_sha256,
        }

    def serialize_canonical(self) -> bytes:
        return json.dumps(
            self._canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")

    def compute_identity_sha256(self) -> str:
        return hashlib.sha256(self.serialize_canonical()).hexdigest()

    def with_canonical_identity(self) -> "KalshiNativeOrderBookSnapshot":
        digest = self.compute_identity_sha256()
        fields = self._canonical_dict()
        return KalshiNativeOrderBookSnapshot(
            environment=self.environment,
            market_ticker=self.market_ticker,
            method=self.method,
            route_template=self.route_template,
            full_request_path=self.full_request_path,
            endpoint_classification=self.endpoint_classification,
            request_timestamp_ms=self.request_timestamp_ms,
            request_started_monotonic_ns=self.request_started_monotonic_ns,
            request_completed_monotonic_ns=self.request_completed_monotonic_ns,
            yes_levels=self.yes_levels,
            no_levels=self.no_levels,
            canonical_level_ordering=self.canonical_level_ordering,
            response_byte_length=self.response_byte_length,
            response_sha256=self.response_sha256,
            raw_openapi_sha256=self.raw_openapi_sha256,
            source_binding_record_sha256=self.source_binding_record_sha256,
            request_count=self.request_count,
            retry_count=self.retry_count,
            redirect_count=self.redirect_count,
            gustavo_execution_authorization_id=self.gustavo_execution_authorization_id,
            expected_implementation_commit=self.expected_implementation_commit,
            specification_sha256=self.specification_sha256,
            canonical_snapshot_sha256=digest,
        )


# ---------------------------------------------------------------------------
# Wire-schema parsing (Spec 8.3-8.5, 12.4-12.6) -- exact public interface
# `parse_orderbook_response(plan, response_body, response_content_type)`.
# ---------------------------------------------------------------------------


def _parse_content_type(content_type: object) -> None:
    """Spec 12.6: accept `application/json`, optionally exactly one
    case-insensitive `charset=utf-8` parameter; reject all other
    parameters, duplicates, or conflicts. No content sniffing."""

    if type(content_type) is not str:
        raise _HaltingError(OrderBookHaltCode.RESPONSE_CONTENT_TYPE_INVALID)
    parts = [p.strip() for p in content_type.split(";")]
    if not parts or parts[0].lower() != "application/json":
        raise _HaltingError(OrderBookHaltCode.RESPONSE_CONTENT_TYPE_INVALID)
    seen_charset = False
    for param in parts[1:]:
        if param == "":
            raise _HaltingError(OrderBookHaltCode.RESPONSE_CONTENT_TYPE_INVALID)
        if "=" not in param:
            raise _HaltingError(OrderBookHaltCode.RESPONSE_CONTENT_TYPE_INVALID)
        name, _, value = param.partition("=")
        if name.strip().lower() != "charset" or value.strip().lower() != "utf-8":
            raise _HaltingError(OrderBookHaltCode.RESPONSE_CONTENT_TYPE_INVALID)
        if seen_charset:
            raise _HaltingError(OrderBookHaltCode.RESPONSE_CONTENT_TYPE_INVALID)
        seen_charset = True


def _parse_price_string(value: object) -> decimal.Decimal:
    if type(value) is not str:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID, "price must be a JSON string")
    if _PRICE_STRING_PATTERN.fullmatch(value) is None:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID, "malformed price string")
    price = decimal.Decimal(value)
    if price < _PRICE_MIN or price > _PRICE_MAX:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_PRICE_INVALID, "price out of [0,1]")
    return price


def _parse_quantity_string(value: object) -> decimal.Decimal:
    if type(value) is not str:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_QUANTITY_INVALID, "quantity must be a JSON string")
    if _QUANTITY_STRING_PATTERN.fullmatch(value) is None:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_QUANTITY_INVALID, "malformed quantity string")
    quantity = decimal.Decimal(value)
    if quantity <= 0:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_QUANTITY_INVALID, "quantity must be positive")
    return quantity


def _parse_side(value: object) -> Tuple[KalshiNativeOrderBookLevel, ...]:
    if value is None:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED, "side must not be null")
    if type(value) is not list:
        raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED, "side must be a JSON array")

    levels = []
    seen_prices = set()
    for entry in value:
        if type(entry) is not list or len(entry) != 2:
            raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_LEVEL_MALFORMED)
        price_raw, quantity_raw = entry
        price = _parse_price_string(price_raw)
        quantity = _parse_quantity_string(quantity_raw)
        if price in seen_prices:
            raise _HaltingError(OrderBookHaltCode.ORDER_BOOK_DUPLICATE_PRICE)
        seen_prices.add(price)
        levels.append(KalshiNativeOrderBookLevel(price=price, quantity=quantity))

    levels.sort(key=lambda level: level.price)
    return tuple(levels)


def parse_orderbook_response(
    plan: object, response_body: bytes, response_content_type: str
) -> Union[ParsedNativeOrderBook, "OrderBookHalt"]:
    """Exact public parser (Spec 9.1, 12.4-12.6).

    Implementation-05 correction 4: revalidates the complete current
    `AuthenticatedOrderBookPlan` at entry -- a mutated plan cannot widen
    the response body cap, host/environment, operation capability,
    source binding, ticker/path binding, query/body policy, signing
    profile, or request/retry/redirect policy. Any malformed current
    value returns a deterministic `OrderBookHalt`; no raw validation
    exception escapes."""

    if type(plan) is not AuthenticatedOrderBookPlan:
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.RESPONSE_VALIDATED)

    try:
        require_usable_authenticated_order_book_plan(plan)
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.RESPONSE_VALIDATED, detail=exc.detail,
                     expected=exc.expected, observed=exc.observed)
    except OrderBookTypeError:
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.RESPONSE_VALIDATED)
    except Exception:
        # Fail-closed backstop: no raw validation exception may escape
        # this public boundary, ever.
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.RESPONSE_VALIDATED)

    try:
        _parse_content_type(response_content_type)
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.RESPONSE_VALIDATED, detail=exc.detail)

    if type(response_body) is not bytes:
        return _halt(OrderBookHaltCode.RESPONSE_JSON_INVALID, OrderBookStage.RESPONSE_VALIDATED)
    if len(response_body) > plan.response_body_cap:
        return _halt(OrderBookHaltCode.RESPONSE_TOO_LARGE, OrderBookStage.RESPONSE_VALIDATED)

    try:
        text = response_body.decode("utf-8")
    except UnicodeDecodeError:
        return _halt(OrderBookHaltCode.RESPONSE_JSON_INVALID, OrderBookStage.ORDER_BOOK_RECONSTRUCTED)

    try:
        payload = json.loads(
            text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_json_constant
        )
    except _DuplicateJsonKeyError:
        return _halt(OrderBookHaltCode.RESPONSE_DUPLICATE_JSON_KEY, OrderBookStage.ORDER_BOOK_RECONSTRUCTED)
    except (ValueError, OverflowError, RecursionError):
        # Implementation-06 correction 5: covers json.JSONDecodeError
        # (malformed JSON), _InvalidJsonConstantError (NaN/Infinity/
        # -Infinity -- correction 4), Python's integer-string-conversion
        # limit, and JSON recursion-depth limit for deeply nested
        # structures. Every one of these classifies as
        # RESPONSE_JSON_INVALID; only a duplicate key gets its own code.
        # No raw exception of any of these kinds escapes this boundary.
        return _halt(OrderBookHaltCode.RESPONSE_JSON_INVALID, OrderBookStage.ORDER_BOOK_RECONSTRUCTED)

    if not isinstance(payload, dict):
        return _halt(OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED, OrderBookStage.ORDER_BOOK_RECONSTRUCTED)

    observed = set(payload.keys())
    unknown = observed - _RESPONSE_TOP_LEVEL_FIELDS
    if unknown:
        return _halt(
            OrderBookHaltCode.ORDER_BOOK_SCHEMA_SHAPE_CHANGED,
            OrderBookStage.ORDER_BOOK_RECONSTRUCTED,
            detail=f"unknown top-level fields: {sorted(unknown)}",
        )
    missing = _RESPONSE_TOP_LEVEL_FIELDS - observed
    if missing:
        return _halt(OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED, OrderBookStage.ORDER_BOOK_RECONSTRUCTED)

    order_book_fp = payload["orderbook_fp"]
    if not isinstance(order_book_fp, dict):
        return _halt(OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED, OrderBookStage.ORDER_BOOK_RECONSTRUCTED)

    observed_ob = set(order_book_fp.keys())
    unknown_ob = observed_ob - _ORDERBOOK_FP_FIELDS
    if unknown_ob:
        return _halt(
            OrderBookHaltCode.ORDER_BOOK_SCHEMA_SHAPE_CHANGED,
            OrderBookStage.ORDER_BOOK_RECONSTRUCTED,
            detail=f"unknown orderbook_fp fields: {sorted(unknown_ob)}",
        )
    missing_ob = _ORDERBOOK_FP_FIELDS - observed_ob
    if missing_ob:
        return _halt(OrderBookHaltCode.ORDER_BOOK_SCHEMA_MALFORMED, OrderBookStage.ORDER_BOOK_RECONSTRUCTED)

    try:
        yes_levels = _parse_side(order_book_fp["yes_dollars"])
        no_levels = _parse_side(order_book_fp["no_dollars"])
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.ORDER_BOOK_RECONSTRUCTED, detail=exc.detail)

    try:
        return ParsedNativeOrderBook(yes_levels=yes_levels, no_levels=no_levels)
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.ORDER_BOOK_RECONSTRUCTED, detail=exc.detail)


# ---------------------------------------------------------------------------
# Secret-safe halt (Spec 7.5).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderBookHalt:
    code: OrderBookHaltCode
    stage: OrderBookStage
    detail: Optional[str] = None
    expected: Optional[str] = None
    observed: Optional[str] = None
    request_count: int = 0
    retry_count: int = 0
    response_definitively_received: bool = False
    signature_lifecycle_state: SignatureLifecycleState = SignatureLifecycleState.NO_SECRET_LOADED
    caller_visible_elapsed_ms: int = 0

    def __repr__(self) -> str:
        parts = [f"code={self.code.value}", f"stage={self.stage.value}"]
        if self.detail is not None:
            parts.append(f"detail={self.detail}")
        if self.expected is not None:
            parts.append(f"expected={self.expected}")
        if self.observed is not None:
            parts.append(f"observed={self.observed}")
        parts.append(f"request_count={self.request_count}")
        parts.append(f"retry_count={self.retry_count}")
        parts.append(f"response_definitively_received={self.response_definitively_received}")
        parts.append(f"signature_lifecycle_state={self.signature_lifecycle_state.value}")
        parts.append(f"caller_visible_elapsed_ms={self.caller_visible_elapsed_ms}")
        return "OrderBookHalt(" + ", ".join(parts) + ")"

    def __str__(self) -> str:
        return self.__repr__()


def _halt(
    code: OrderBookHaltCode,
    stage: OrderBookStage,
    *,
    detail: Optional[str] = None,
    expected: Optional[str] = None,
    observed: Optional[str] = None,
    request_count: int = 0,
    retry_count: int = 0,
    response_definitively_received: bool = False,
    signature_lifecycle_state: SignatureLifecycleState = SignatureLifecycleState.NO_SECRET_LOADED,
    caller_visible_elapsed_ms: int = 0,
) -> OrderBookHalt:
    return OrderBookHalt(
        code=code,
        stage=stage,
        detail=detail,
        expected=expected,
        observed=observed,
        request_count=request_count,
        retry_count=retry_count,
        response_definitively_received=response_definitively_received,
        signature_lifecycle_state=signature_lifecycle_state,
        caller_visible_elapsed_ms=caller_visible_elapsed_ms,
    )


# ---------------------------------------------------------------------------
# DNS resolution with deadline (accepted quarantined daemon-worker model).
# ---------------------------------------------------------------------------


def _address_is_acceptable(ip) -> bool:
    if (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_unspecified or ip.is_reserved
    ):
        return False
    return ip.is_global


def _deterministic_sorted(pairs):
    return tuple(sorted(pairs, key=lambda pair: (pair[0], ipaddress.ip_address(pair[1]).packed)))


def _classify_dns_answer(raw_candidates, expected_port: int) -> Tuple[Tuple[int, str], ...]:
    if not raw_candidates:
        raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "empty answer")

    parsed: set = set()
    for candidate in raw_candidates:
        if type(candidate) is not tuple or len(candidate) != 2:
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "malformed candidate")
        family_value, sockaddr = candidate
        if type(family_value) not in (socket.AddressFamily, int):
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "malformed family")

        if family_value == socket.AF_INET:
            expected_len, expected_version = 2, 4
        elif family_value == socket.AF_INET6:
            expected_len, expected_version = 4, 6
        else:
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "unsupported family")

        if type(sockaddr) is not tuple or len(sockaddr) != expected_len:
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "malformed sockaddr")

        addr_text = sockaddr[0]
        sockaddr_port = sockaddr[1]
        if type(addr_text) is not str:
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "malformed address text")
        if type(sockaddr_port) is not int or sockaddr_port != expected_port:
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "port mismatch")
        try:
            ip = ipaddress.ip_address(addr_text)
        except ValueError as exc:
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "unclassifiable address") from exc

        if ip.version != expected_version:
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "family/version mismatch")
        if not _address_is_acceptable(ip):
            raise _HaltingError(OrderBookHaltCode.DNS_VERIFICATION_FAILED, "prohibited address")

        parsed.add((expected_version, str(ip)))

    return _deterministic_sorted(parsed)


def _dns_resolver_worker(host: str, port: int, result_channel: "queue.Queue") -> None:
    try:
        answer = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        candidates = tuple((family, sockaddr) for family, _st, _pr, _cn, sockaddr in answer)
        result_channel.put(("ok", candidates))
    except OSError as exc:
        result_channel.put(("error", exc))


def _resolve_addresses_with_deadline(host: str, port: int, timeout_s: float):
    if timeout_s <= 0:
        raise TimeoutError("no time remained for DNS resolution")
    result_channel: "queue.Queue" = queue.Queue(maxsize=1)
    worker = threading.Thread(
        target=_dns_resolver_worker, args=(host, port, result_channel),
        daemon=True, name="kalshi-orderbook-dns-resolver",
    )
    worker.start()
    try:
        kind, payload = result_channel.get(timeout=timeout_s)
    except queue.Empty:
        raise TimeoutError("DNS resolution exceeded the caller-visible deadline") from None
    if kind == "error":
        raise payload
    return payload


# ---------------------------------------------------------------------------
# HTTP response header/status validation.
# ---------------------------------------------------------------------------


def _validate_http_response_headers(header_bytes: bytes, body: bytes, max_body_bytes: int):
    """Implementation-04 correction 2: accepts the header block and body
    as already-separated byte strings -- the receive loop performs the
    `\\r\\n\\r\\n` split itself, as soon as it is seen, so the `65536`
    cap can be enforced against body bytes only, while they are being
    received, never against header bytes and never only after an
    oversized body has already been fully buffered."""

    try:
        header_text = header_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise _HaltingError(OrderBookHaltCode.RESPONSE_JSON_INVALID, "malformed headers") from exc

    lines = header_text.split("\r\n")
    status_line = lines[0]
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise _HaltingError(OrderBookHaltCode.RESPONSE_JSON_INVALID, "malformed status line")
    status = int(parts[1])

    headers: dict = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()

    if 300 <= status <= 399:
        raise _HaltingError(OrderBookHaltCode.ENDPOINT_REDIRECT_PROHIBITED, str(status), expected="200", observed=str(status))
    if status == 401:
        raise _HaltingError(OrderBookHaltCode.AUTHENTICATION_FAILED, str(status), expected="200", observed=str(status))
    if status == 403:
        raise _HaltingError(OrderBookHaltCode.AUTHORIZATION_OR_PERMISSION_FAILED, str(status), expected="200", observed=str(status))
    if status == 404:
        raise _HaltingError(OrderBookHaltCode.MARKET_NOT_FOUND, str(status), expected="200", observed=str(status))
    if status == 429:
        raise _HaltingError(OrderBookHaltCode.RATE_LIMITED, str(status), expected="200", observed=str(status))
    if status != 200:
        raise _HaltingError(OrderBookHaltCode.UNEXPECTED_HTTP_STATUS, str(status), expected="200", observed=str(status))

    content_encoding = headers.get("content-encoding", "identity")
    if content_encoding.lower() not in ("identity", ""):
        raise _HaltingError(OrderBookHaltCode.RESPONSE_ENCODING_UNSUPPORTED, content_encoding)

    content_type = headers.get("content-type", "")

    if len(body) > max_body_bytes:
        raise _HaltingError(OrderBookHaltCode.RESPONSE_TOO_LARGE)

    return content_type, body


def _compute_body_retention(body_total: int, cap: int, candidate: bytes):
    """Implementation-06 correction 2: pure retention-accounting helper.
    Returns `(bytes_to_retain, new_body_total, cap_exceeded)`.

    Retains at most the permitted prefix of `candidate` so retained body
    bytes never exceed `cap`. If no capacity remains at all, the entire
    candidate is discarded -- it exists only as overflow evidence that
    the cap was exceeded, never as retained/buffered content."""

    remaining = cap - body_total
    if remaining <= 0:
        return b"", body_total, True
    if len(candidate) > remaining:
        return candidate[:remaining], body_total + remaining, True
    return candidate, body_total + len(candidate), False


# ---------------------------------------------------------------------------
# Execution boundary (Spec 9.1, 9.9, 10, 15.4) -- exact public interface
# `execute_demo_authenticated_orderbook(plan)`.
# ---------------------------------------------------------------------------


def _current_monotonic_ns() -> int:
    return time.monotonic_ns()


def _remaining_ns(deadline_ns: int) -> int:
    return deadline_ns - _current_monotonic_ns()


def execute_demo_authenticated_orderbook(
    plan: object,
) -> Union[KalshiNativeOrderBookSnapshot, OrderBookHalt]:
    """The one network-capable boundary (Spec 9.1, 10.2). Accepts only an
    already-validated plan; accepts no transport or secret injection.
    `10000 ms` caller-visible deadline from the first instruction through
    final return, including through secret loading, signing, response
    parsing, and canonical snapshot construction."""

    start_ns = _current_monotonic_ns()
    deadline_ns = start_ns + _OVERALL_TIMEOUT_MS * 1_000_000

    def _elapsed_ms() -> int:
        return int((_current_monotonic_ns() - start_ns) / 1_000_000)

    if type(plan) is not AuthenticatedOrderBookPlan:
        return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, OrderBookStage.PLAN_INPUT,
                     caller_visible_elapsed_ms=_elapsed_ms())

    def gate(stage: OrderBookStage, lifecycle: SignatureLifecycleState):
        try:
            require_usable_authenticated_order_book_plan(plan)
        except _HaltingError as exc:
            return _halt(exc.code, stage, detail=exc.detail, expected=exc.expected, observed=exc.observed,
                         signature_lifecycle_state=lifecycle, caller_visible_elapsed_ms=_elapsed_ms())
        except OrderBookTypeError:
            return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, stage,
                         signature_lifecycle_state=lifecycle, caller_visible_elapsed_ms=_elapsed_ms())
        except Exception:
            # Fail-closed backstop (Implementation-04 correction 3): any
            # unexpected exception from a mutated/malformed plan at any
            # of the five current-value gates must never escape as a raw
            # exception -- it always becomes a deterministic halt.
            return _halt(OrderBookHaltCode.CURRENT_VALUE_MISMATCH, stage,
                         signature_lifecycle_state=lifecycle, caller_visible_elapsed_ms=_elapsed_ms())
        return None

    # Gate 1: pre-DNS.
    failure = gate(OrderBookStage.PRE_DNS_CURRENT_VALUES_REVERIFIED, SignatureLifecycleState.NO_SECRET_LOADED)
    if failure is not None:
        return failure

    remaining_s = _remaining_ns(deadline_ns) / 1_000_000_000.0
    if remaining_s <= 0:
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.DNS_RESOLUTION_WAIT,
                     caller_visible_elapsed_ms=_elapsed_ms())

    try:
        raw_addresses = _resolve_addresses_with_deadline(plan.host, plan.port, remaining_s)
    except TimeoutError:
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.DNS_RESOLUTION_WAIT,
                     caller_visible_elapsed_ms=_elapsed_ms())
    except OSError:
        return _halt(OrderBookHaltCode.DNS_VERIFICATION_FAILED, OrderBookStage.DNS_SET_VERIFIED,
                     caller_visible_elapsed_ms=_elapsed_ms())

    try:
        verified_pairs = _classify_dns_answer(raw_addresses, plan.port)
    except _HaltingError as exc:
        return _halt(exc.code, OrderBookStage.DNS_SET_VERIFIED, detail=exc.detail,
                     caller_visible_elapsed_ms=_elapsed_ms())

    selected_version, selected_address = verified_pairs[0]

    # Gate 2: pre-socket.
    failure = gate(OrderBookStage.PRE_SOCKET_CURRENT_VALUES_REVERIFIED, SignatureLifecycleState.NO_SECRET_LOADED)
    if failure is not None:
        return failure

    remaining_s = min(_remaining_ns(deadline_ns) / 1e9, plan.socket_stage_cap_ms / 1000.0)
    if remaining_s <= 0:
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.PRE_SOCKET_CURRENT_VALUES_REVERIFIED,
                     caller_visible_elapsed_ms=_elapsed_ms())

    family = socket.AF_INET if selected_version == 4 else socket.AF_INET6
    try:
        raw_sock = socket.socket(family, socket.SOCK_STREAM)
        raw_sock.settimeout(remaining_s)
        raw_sock.connect((selected_address, plan.port))
    except (socket.timeout, TimeoutError):
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.TCP_CONNECTED_TO_PINNED_ADDRESS,
                     caller_visible_elapsed_ms=_elapsed_ms())
    except OSError:
        # DNS verification already succeeded above; a socket/connect
        # failure to the pinned, already-verified address is a distinct
        # transport failure, never misreported as a DNS failure.
        return _halt(OrderBookHaltCode.TRANSPORT_FAILURE, OrderBookStage.TCP_CONNECTED_TO_PINNED_ADDRESS,
                     caller_visible_elapsed_ms=_elapsed_ms())

    remaining_s = min(_remaining_ns(deadline_ns) / 1e9, plan.socket_stage_cap_ms / 1000.0)
    if remaining_s <= 0:
        raw_sock.close()
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
                     caller_visible_elapsed_ms=_elapsed_ms())

    try:
        raw_sock.settimeout(remaining_s)
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        tls_sock = context.wrap_socket(raw_sock, server_hostname=plan.host)
    except (socket.timeout, TimeoutError):
        raw_sock.close()
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
                     caller_visible_elapsed_ms=_elapsed_ms())
    except (ssl.SSLError, OSError):
        raw_sock.close()
        return _halt(OrderBookHaltCode.TLS_VERIFICATION_FAILED, OrderBookStage.TLS_VERIFIED_FOR_DEMO_HOSTNAME,
                     caller_visible_elapsed_ms=_elapsed_ms())

    # Gate 3: pre-secret load.
    failure = gate(OrderBookStage.PRE_SECRET_LOAD_CURRENT_VALUES_REVERIFIED, SignatureLifecycleState.NO_SECRET_LOADED)
    if failure is not None:
        tls_sock.close()
        return failure
    if _remaining_ns(deadline_ns) <= 0:
        tls_sock.close()
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.PRE_SECRET_LOAD_CURRENT_VALUES_REVERIFIED,
                     caller_visible_elapsed_ms=_elapsed_ms())

    # Implementation-04 correction 1: load the two secrets sequentially
    # (not via the combined all-or-nothing wrapper) so the lifecycle
    # evidence reported on halt is factually accurate -- NO_SECRET_LOADED
    # only when the API-key read itself failed; SECRET_LOADED_NO_SIGNATURE
    # once the API-key value was successfully read, even if the
    # subsequent private-key read then fails.
    try:
        api_key_id_loaded = _load_api_key_id()
    except _HaltingError as exc:
        tls_sock.close()
        return _halt(exc.code, OrderBookStage.SECRETS_LOADED, detail=exc.detail,
                     signature_lifecycle_state=SignatureLifecycleState.NO_SECRET_LOADED,
                     caller_visible_elapsed_ms=_elapsed_ms())

    try:
        private_key_pem_loaded = _load_private_key_pem()
    except _HaltingError as exc:
        tls_sock.close()
        api_key_id_loaded = None
        return _halt(exc.code, OrderBookStage.SECRETS_LOADED, detail=exc.detail,
                     signature_lifecycle_state=SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE,
                     caller_visible_elapsed_ms=_elapsed_ms())

    secrets = _EphemeralOrderBookSecrets(
        api_key_id=api_key_id_loaded, private_key_pem=private_key_pem_loaded
    )
    api_key_id_loaded = None
    private_key_pem_loaded = None

    if _remaining_ns(deadline_ns) <= 0:
        tls_sock.close()
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.SECRETS_LOADED,
                     signature_lifecycle_state=SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE,
                     caller_visible_elapsed_ms=_elapsed_ms())

    # Gate 4: pre-sign.
    failure = gate(OrderBookStage.PRE_SIGN_CURRENT_VALUES_REVERIFIED, SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE)
    if failure is not None:
        tls_sock.close()
        secrets = None
        return failure

    timestamp_ms_text = str(int(time.time() * 1000))
    try:
        signing_message = build_orderbook_signing_message(plan, timestamp_ms_text)
    except _HaltingError as exc:
        tls_sock.close()
        secrets = None
        return _halt(exc.code, OrderBookStage.SIGNING_MESSAGE_BUILT, detail=exc.detail,
                     signature_lifecycle_state=SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE,
                     caller_visible_elapsed_ms=_elapsed_ms())

    try:
        signature = _sign_orderbook_message(signing_message, plan, secrets)
    except _HaltingError as exc:
        tls_sock.close()
        secrets = None
        return _halt(exc.code, OrderBookStage.SIGNATURE_GENERATED_NOT_SENT, detail=exc.detail,
                     signature_lifecycle_state=SignatureLifecycleState.SECRET_LOADED_NO_SIGNATURE,
                     caller_visible_elapsed_ms=_elapsed_ms())

    signature_b64 = base64.b64encode(signature).decode("ascii")
    signature = None
    api_key_id = secrets.api_key_id
    secrets = None

    if _remaining_ns(deadline_ns) <= 0:
        tls_sock.close()
        api_key_id = None
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.SIGNATURE_GENERATED_NOT_SENT,
                     signature_lifecycle_state=SignatureLifecycleState.SIGNATURE_GENERATED_NOT_SENT,
                     caller_visible_elapsed_ms=_elapsed_ms())

    # Gate 5: pre-send.
    failure = gate(OrderBookStage.PRE_SEND_CURRENT_VALUES_REVERIFIED, SignatureLifecycleState.SIGNATURE_GENERATED_NOT_SENT)
    if failure is not None:
        tls_sock.close()
        api_key_id = None
        return failure

    if not _api_key_id_is_header_safe(api_key_id):
        # Defense in depth: re-verified immediately before header
        # construction, even though the loader already checked this.
        tls_sock.close()
        api_key_id = None
        signature_b64 = None
        return _halt(OrderBookHaltCode.API_KEY_ID_MALFORMED, OrderBookStage.REQUEST_SEND_MAY_HAVE_BEGUN,
                     signature_lifecycle_state=SignatureLifecycleState.SIGNATURE_GENERATED_NOT_SENT,
                     caller_visible_elapsed_ms=_elapsed_ms())

    try:
        request_bytes = (
            f"{plan.method} {plan.full_path} HTTP/1.1\r\n"
            f"Host: {plan.host}\r\n"
            f"KALSHI-ACCESS-KEY: {api_key_id}\r\n"
            f"KALSHI-ACCESS-SIGNATURE: {signature_b64}\r\n"
            f"KALSHI-ACCESS-TIMESTAMP: {timestamp_ms_text}\r\n"
            "Accept: application/json\r\n"
            "Accept-Encoding: identity\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
    except UnicodeEncodeError:
        # No accepted value should ever reach this point, but this
        # boundary must never let a raw UnicodeEncodeError escape.
        tls_sock.close()
        api_key_id = None
        signature_b64 = None
        return _halt(OrderBookHaltCode.API_KEY_ID_MALFORMED, OrderBookStage.REQUEST_SEND_MAY_HAVE_BEGUN,
                     signature_lifecycle_state=SignatureLifecycleState.SIGNATURE_GENERATED_NOT_SENT,
                     caller_visible_elapsed_ms=_elapsed_ms())
    api_key_id = None
    signature_b64 = None

    remaining_s = min(_remaining_ns(deadline_ns) / 1e9, plan.socket_stage_cap_ms / 1000.0)
    if remaining_s <= 0:
        tls_sock.close()
        return _halt(OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.REQUEST_SEND_MAY_HAVE_BEGUN,
                     signature_lifecycle_state=SignatureLifecycleState.SIGNATURE_GENERATED_NOT_SENT,
                     caller_visible_elapsed_ms=_elapsed_ms())

    request_timestamp_ms = int(timestamp_ms_text)
    request_started_ns = _current_monotonic_ns()

    try:
        tls_sock.settimeout(remaining_s)
        tls_sock.sendall(request_bytes)
    except (socket.timeout, TimeoutError, OSError):
        try:
            tls_sock.close()
        except OSError:
            pass
        return _halt(
            OrderBookHaltCode.REQUEST_RESULT_UNKNOWN, OrderBookStage.REQUEST_SEND_MAY_HAVE_BEGUN,
            request_count=1, retry_count=0, response_definitively_received=False,
            signature_lifecycle_state=SignatureLifecycleState.SEND_MAY_HAVE_BEGUN,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    request_bytes = None

    header_buffer = bytearray()
    header_bytes = None
    body_chunks = []
    body_total = 0
    headers_complete = False
    receive_failed = False
    cap_exceeded = False
    _separator = b"\r\n\r\n"
    _HEADER_READ_CHUNK = 4096

    def _retain_body_bytes(candidate: bytes) -> bool:
        """Delegates to the pure `_compute_body_retention` helper
        (Implementation-06 correction 2) and applies its result to this
        call's local state. Returns True if the cap was (or already had
        been) exceeded."""

        nonlocal body_total, cap_exceeded
        to_retain, body_total, exceeded = _compute_body_retention(body_total, plan.response_body_cap, candidate)
        if to_retain:
            body_chunks.append(to_retain)
        if exceeded:
            cap_exceeded = True
        return exceeded

    try:
        while True:
            remaining_overall_s = _remaining_ns(deadline_ns) / 1e9
            if remaining_overall_s <= 0:
                receive_failed = True
                break
            stage_s = min(plan.socket_stage_cap_ms / 1000.0, remaining_overall_s)
            tls_sock.settimeout(stage_s)

            if not headers_complete:
                # Headers are never counted against the body cap; read up
                # to the ordinary chunk size while searching for the
                # header/body separator.
                read_size = _HEADER_READ_CHUNK
            else:
                # Implementation-05 correction 3: bounded body reception.
                # Request at most the minimum excess necessary to prove
                # the cap would be exceeded -- never an unconditional
                # full 4096-byte over-read once less than 4096 bytes of
                # permitted body capacity remain.
                remaining_capacity = plan.response_body_cap - body_total
                if remaining_capacity < 0:
                    cap_exceeded = True
                    break
                read_size = min(_HEADER_READ_CHUNK, remaining_capacity + 1)

            chunk = tls_sock.recv(read_size)
            if not chunk:
                break

            if not headers_complete:
                header_buffer.extend(chunk)
                idx = header_buffer.find(_separator)
                if idx == -1:
                    continue
                header_bytes = bytes(header_buffer[:idx])
                leftover = bytes(header_buffer[idx + len(_separator):])
                headers_complete = True
                del header_buffer
                if leftover and _retain_body_bytes(leftover):
                    break
            else:
                if _retain_body_bytes(chunk):
                    break
    except (socket.timeout, TimeoutError, OSError):
        receive_failed = True
    finally:
        try:
            tls_sock.close()
        except OSError:
            pass

    request_completed_ns = _current_monotonic_ns()

    # Implementation-05 correction 1: any termination after send may
    # have begun but before a complete terminal HTTP response has been
    # established -- clean EOF before/during the header block, a
    # deadline expiry mid-reception, a socket timeout, or any transport
    # exception -- is uniformly REQUEST_RESULT_UNKNOWN. A
    # header-incomplete EOF is never RESPONSE_JSON_INVALID and never
    # claims RESPONSE_DEFINITIVELY_RECEIVED, because no usable response
    # was ever definitively established.
    if receive_failed or not headers_complete:
        return _halt(
            OrderBookHaltCode.REQUEST_RESULT_UNKNOWN, OrderBookStage.RESPONSE_HEADERS_RECEIVED,
            request_count=1, retry_count=0, response_definitively_received=False,
            signature_lifecycle_state=SignatureLifecycleState.SEND_MAY_HAVE_BEGUN,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    if cap_exceeded:
        # Implementation-05 correction 2: the cap-exceeded determination
        # is itself definite and deterministic (RESPONSE_TOO_LARGE), but
        # reception was deliberately stopped before the complete response
        # was established -- the evidence must not claim
        # response_definitively_received=True or
        # RESPONSE_DEFINITIVELY_RECEIVED, since only "more than the cap"
        # was proven, not "the complete response".
        return _halt(
            OrderBookHaltCode.RESPONSE_TOO_LARGE, OrderBookStage.RESPONSE_BODY_RECEIVED,
            request_count=1, retry_count=0, response_definitively_received=False,
            signature_lifecycle_state=SignatureLifecycleState.SEND_MAY_HAVE_BEGUN,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    if _remaining_ns(deadline_ns) <= 0:
        return _halt(
            OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.RESPONSE_VALIDATED,
            request_count=1, retry_count=0, response_definitively_received=True,
            signature_lifecycle_state=SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    body = b"".join(body_chunks)

    try:
        content_type, body = _validate_http_response_headers(header_bytes, body, plan.response_body_cap)
    except _HaltingError as exc:
        return _halt(
            exc.code, OrderBookStage.RESPONSE_VALIDATED, detail=exc.detail,
            expected=exc.expected, observed=exc.observed,
            request_count=1, retry_count=0, response_definitively_received=True,
            signature_lifecycle_state=SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    parsed = parse_orderbook_response(plan, body, content_type)
    if isinstance(parsed, OrderBookHalt):
        return _halt(
            parsed.code, parsed.stage, detail=parsed.detail,
            request_count=1, retry_count=0, response_definitively_received=True,
            signature_lifecycle_state=SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    if _remaining_ns(deadline_ns) <= 0:
        return _halt(
            OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.ORDER_BOOK_RECONSTRUCTED,
            request_count=1, retry_count=0, response_definitively_received=True,
            signature_lifecycle_state=SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    snapshot = KalshiNativeOrderBookSnapshot(
        environment="KALSHI_DEMO",
        market_ticker=plan.market_ticker,
        method=plan.method,
        route_template=plan.route_template,
        full_request_path=plan.full_path,
        endpoint_classification="AUTHENTICATED_READ_ONLY",
        request_timestamp_ms=request_timestamp_ms,
        request_started_monotonic_ns=request_started_ns,
        request_completed_monotonic_ns=request_completed_ns,
        yes_levels=parsed.yes_levels,
        no_levels=parsed.no_levels,
        canonical_level_ordering="PRICE_ASCENDING",
        response_byte_length=len(body),
        response_sha256=hashlib.sha256(body).hexdigest(),
        raw_openapi_sha256=plan.source_binding.raw_openapi_sha256,
        source_binding_record_sha256=plan.source_binding.source_binding_record_sha256,
        request_count=1,
        retry_count=0,
        redirect_count=0,
        gustavo_execution_authorization_id=plan.execution_dispatch_expectation.gustavo_execution_authorization_id,
        expected_implementation_commit=plan.execution_dispatch_expectation.expected_implementation_commit,
        specification_sha256=plan.execution_dispatch_expectation.expected_specification_sha256,
    ).with_canonical_identity()

    if _remaining_ns(deadline_ns) <= 0:
        return _halt(
            OrderBookHaltCode.CONNECTIVITY_TIMEOUT, OrderBookStage.SUCCEEDED,
            request_count=1, retry_count=0, response_definitively_received=True,
            signature_lifecycle_state=SignatureLifecycleState.RESPONSE_DEFINITIVELY_RECEIVED,
            caller_visible_elapsed_ms=_elapsed_ms(),
        )

    return snapshot
