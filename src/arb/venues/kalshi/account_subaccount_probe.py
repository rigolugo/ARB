"""Kalshi Demo Route-B B1 account/subaccount capability-and-facts probe.

This module implements the exact accepted contract:

    KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01.md
    bytes  = 54469
    sha256 = 0265953846cd48105a1d20d79453d6dfdb92310c38f9a8a06295fa32dceae500

It is a narrow, isolated module. It is deliberately *not* exported from the
package ``__init__`` and adds no new dependency: only the Python standard
library plus ``cryptography`` (already required by ``pyproject.toml``) is used,
and ``cryptography`` is imported solely for the future request-signing boundary.

Nothing here performs real network I/O, opens a socket, resolves DNS, performs
TLS, reads a real credential value, or contacts Kalshi. The venue-capable
execution path (``execute_b1_account_subaccount_probe``) is fully driven by
injected boundaries -- a :class:`Transport`, a :class:`MessageSigner`, and a
:class:`Clock` -- so it is exercised entirely offline with fakes. There is no
transport implementation in this module that could reach a network; a caller
that forgets to inject one gets :class:`UnavailableTransport`, which always
raises.

Requirement identifiers in docstrings and comments (``B1-REQ-004`` and so on)
refer to sections of the controlling specification.

Scope boundary
--------------
This module provides implementation + offline-test logic only. It does not
authorize B1 authenticated Demo execution, credential reads, subaccount
creation, funding/transfer, netting changes, order activity, persistent-state
access, or any later Route-B stage. A separate explicit task is required before
any B1 venue execution.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

__all__ = [
    # Identity / source binding
    "TASK_ID",
    "DEMO_REST_BASE_URL",
    "SOURCE_BINDING_NAME",
    "SOURCE_BINDING_RECORD_BYTES",
    "SOURCE_BINDING_RECORD_SHA256",
    "SOURCE_BINDING_RECORD_JSON",
    "HISTORICAL_OPENAPI_SNAPSHOT_SHA256",
    "HISTORICAL_CORROBORATING_OPERATION_IDS",
    "SIGNING_PROFILE",
    "SourceEvidenceBinding",
    "AUTHORING_SOURCE_EVIDENCE_BINDING",
    # Enums
    "B1TerminalOutcome",
    "B1NextRouteClass",
    "CurrentKeyMatchState",
    "CurrentKeyRestrictionState",
    "BalanceClass",
    "RequestStatusClass",
    # Errors
    "B1ProbeError",
    "CapabilityScopeViolation",
    "CredentialSourceContractError",
    "SigningContractError",
    "SourceContractError",
    "EvidenceOutputRootError",
    # Source contract
    "SourceOperation",
    "RestrictedKeyErrorSignature",
    "TaskCurrentSourceRecord",
    "SourceEvaluation",
    "authoring_task_current_source_record",
    "verify_source_binding_record",
    # Request plan / signing
    "RequestPlan",
    "SigningMessage",
    "AuthenticatedHttpRequest",
    "build_request_plan_sequence",
    "build_signing_message",
    "build_authenticated_request",
    "evaluate_request_target",
    "is_permitted_b1_target",
    # Boundaries
    "Clock",
    "SystemClock",
    "MessageSigner",
    "RsaPssSha256FileSigner",
    "Transport",
    "TransportResponse",
    "ResponseBodyReader",
    "UnavailableTransport",
    "load_b1_credentials",
    # Parsers / projections
    "AccountLimitsProjection",
    "GrantProjection",
    "ApiKeyRecord",
    "BalanceRow",
    "NettingRow",
    "parse_account_limits",
    "parse_api_keys",
    "parse_subaccount_balances",
    "parse_subaccount_netting",
    "parse_balance_decimal",
    # Execution + evidence
    "B1EvidenceManifest",
    "B1SanitizedSummary",
    "B1Result",
    "execute_b1_account_subaccount_probe",
]

# ---------------------------------------------------------------------------
# Fixed identity, environment, and bounds (B1-SRC-006, B1-REQ-003..005).
# ---------------------------------------------------------------------------

TASK_ID = "KALSHI_DEMO_ROUTE_B_B1_ACCOUNT_SUBACCOUNT_CAPABILITY_AND_FACTS_SPEC_01"
ENVIRONMENT = "KALSHI_DEMO"

DEMO_SCHEME = "https"
DEMO_HOST = "external-api.demo.kalshi.co"
DEMO_PORT = 443
DEMO_BASE_PATH = "/trade-api/v2"
DEMO_REST_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"

# Hosts B1 must never use, even as a fallback (B1-SRC-006, B1-FAIL-006).
COMPATIBILITY_DEMO_HOST = "demo-api.kalshi.co"
PROHIBITED_HOSTS = frozenset(
    {
        COMPATIBILITY_DEMO_HOST,
        "api.elections.kalshi.com",
        "trading-api.kalshi.com",
        "api.kalshi.com",
        "kalshi.com",
    }
)

PER_REQUEST_DEADLINE_MS = 10_000
GLOBAL_EXECUTION_DEADLINE_MS = 40_000
MAX_RESPONSE_BYTES_PER_REQUEST = 262_144
MAX_TOTAL_RESPONSE_BYTES = 1_048_576
# C02-02: the B1 runner performs its own bounded blocking response-body reads.
# Every read requests a finite, positive maximum -- never "read all", never an
# unbounded iterator/materialisation. This is the largest number of bytes B1
# will ask for in a single :meth:`ResponseBodyReader.read` call; the actual
# request is further clamped to the remaining per-response and cumulative room.
RESPONSE_READ_CHUNK_BYTES = 65_536
MAX_REQUEST_COUNT = 4
MAX_ATTEMPTS_PER_PATH = 1
AUTOMATIC_RETRY_COUNT = 0
MAX_REDIRECT_COUNT = 0

_MS_TO_NS = 1_000_000

# Credential source names (B1-CRED-001). The private-key variable holds a
# filesystem *path*, never key bytes.
API_KEY_ID_ENV = "KALSHI_DEMO_API_KEY_ID"
PRIVATE_KEY_PATH_ENV = "KALSHI_DEMO_PRIVATE_KEY_PATH"
# The older canonical `validation.py` PEM-content convention. Its mere presence
# is a B1 credential-source contract violation (B1-IMPL-003, B1-TEST-002).
FORBIDDEN_PRIVATE_KEY_PEM_ENV = "KALSHI_DEMO_PRIVATE_KEY_PEM"

# Cryptographic request-signing profile. This is not a new Kalshi auth profile:
# it is the already-canonical ARB authenticated-GET signing semantics, statically
# established from `src/arb/venues/kalshi/orderbook.py` (`_SIGNING_PROFILE`,
# `build_orderbook_signing_message`, `_sign_orderbook_message`) and
# `order_lifecycle.py` (`SIGNING_PROFILE`):
#
#   message  = timestamp_ms_text + uppercase_method + full_request_path  (UTF-8)
#   query    = excluded from the signed path
#   scheme   = RSA-PSS, SHA-256, MGF1(SHA-256)
#   saltlen  = SHA-256 digest length (32)
#   header   = standard Base64 of the raw signature
SIGNING_PROFILE = "KALSHI_RSA_PSS_SHA256_MGF1_SALT_DIGESTLEN_V1"

# ---------------------------------------------------------------------------
# Fresh rendered-source binding identity (B1-SRC-008).
# ---------------------------------------------------------------------------

SOURCE_BINDING_NAME = "KALSHI_DEMO_ROUTE_B_B1_OFFICIAL_RENDERED_SOURCE_BINDING_01"
SOURCE_BINDING_RECORD_BYTES = 3307
SOURCE_BINDING_RECORD_SHA256 = (
    "964056df0d633fa27d53363aa58ee3c59c2fc6281c0b1cc68f25bbad5b104dc2"
)

FRESH_RAW_OPENAPI_STATUS = (
    "NOT_OBTAINED_UNSUPPORTED_TEXT_YAML_IN_BROWSER_AND_DIRECT_DOWNLOAD_FAILED"
)
SOURCE_OBSERVED_AT_UTC = "2026-08-27T20:02:16Z"

# Historical OpenAPI 3.28.0 snapshot -- corroboration only (B1-SRC-007). These
# operation IDs MUST NOT be presented as freshly verified current IDs.
HISTORICAL_OPENAPI_SNAPSHOT_SHA256 = (
    "cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b"
)
HISTORICAL_OPENAPI_SNAPSHOT_BYTES = 333_315
HISTORICAL_CORROBORATING_OPERATION_IDS = {
    "GET /account/limits": "GetAccountApiLimits",
    "GET /api_keys": "GetApiKeys",
    "GET /portfolio/subaccounts/balances": "GetSubaccountBalances",
    "GET /portfolio/subaccounts/netting": "GetSubaccountNetting",
    "POST /portfolio/subaccounts": "CreateSubaccount",
}

# The deterministic derived source-binding record (B1-SRC-008): UTF-8, no BOM,
# sorted keys, tight separators, ASCII escapes only. Held as a Python object and
# re-serialized deterministically so a byte can never drift in transcription;
# `_verify_embedded_source_binding()` fails import if the derived identity does
# not match the reviewed bytes/hash.
_SOURCE_BINDING_RECORD_OBJ = {
    "binding_name": SOURCE_BINDING_NAME,
    "fresh_api_info_version": "NOT_EXPOSED_BY_RENDERED_SOURCE",
    "fresh_openapi_version": "NOT_EXPOSED_BY_RENDERED_SOURCE",
    "fresh_operation_ids": "NOT_EXPOSED_BY_RENDERED_SOURCE",
    "fresh_raw_openapi_status": FRESH_RAW_OPENAPI_STATUS,
    "fresh_source_class": "OFFICIAL_RENDERED_DOCUMENTATION",
    "historical_corroboration": {
        "get_api_keys_subaccount_semantics": "absent/null described as unrestricted",
        "info_version": "3.28.0",
        "openapi": "3.0.0",
        "operation_ids": {
            "GET /account/limits": "GetAccountApiLimits",
            "GET /api_keys": "GetApiKeys",
            "GET /portfolio/subaccounts/balances": "GetSubaccountBalances",
            "GET /portfolio/subaccounts/netting": "GetSubaccountNetting",
            "POST /portfolio/subaccounts": "CreateSubaccount",
        },
        "path": "04_HISTORICAL_SOURCE_CONTEXT/openapi_3_28_0_predecessor_snapshot.yaml",
        "raw_bytes": 333315,
        "sha256": "cb853ffc47262646b96bba7b1a8925c9c344128fd498cdaa8dbcf9a0b3b8211b",
    },
    "observed_at_utc": SOURCE_OBSERVED_AT_UTC,
    "pages": [
        {
            "method": "GET",
            "path": "/account/limits",
            "response_200_top_level_required": [
                "usage_tier",
                "read",
                "write",
                "grants",
            ],
            "url": "https://docs.kalshi.com/api-reference/account/get-account-api-limits",
        },
        {
            "current_key_subaccount_response_absence_semantics": (
                "NOT_EXPOSED_BY_FRESH_RENDERED_SOURCE"
            ),
            "method": "GET",
            "path": "/api_keys",
            "response_200_top_level_required": ["api_keys"],
            "url": "https://docs.kalshi.com/api-reference/api-keys/get-api-keys",
        },
        {
            "account_wide_statement": "all subaccounts including primary",
            "method": "GET",
            "path": "/portfolio/subaccounts/balances",
            "response_200_top_level_required": ["subaccount_balances"],
            "url": "https://docs.kalshi.com/api-reference/portfolio/get-all-subaccount-balances",
        },
        {
            "account_wide_statement": "all subaccounts",
            "method": "GET",
            "path": "/portfolio/subaccounts/netting",
            "response_200_top_level_required": ["netting_configs"],
            "url": "https://docs.kalshi.com/api-reference/portfolio/get-subaccount-netting",
        },
        {
            "partition_statement": (
                "balances and positions are independent buckets within one Direct account"
            ),
            "restricted_key_statement": (
                "single-subaccount restricted keys cannot manage subaccounts or API keys "
                "and out-of-scope endpoints return 403"
            ),
            "subaccount_numbering": "0 primary; 1-63 numbered",
            "url": "https://docs.kalshi.com/getting_started/subaccounts",
        },
        {
            "create_request_omission_semantics": (
                "omit request subaccount to leave newly created key unrestricted"
            ),
            "note": (
                "does not by itself prove GET /api_keys response omission/null semantics"
            ),
            "subaccount_constraint": "integer 0-63",
            "url": "https://docs.kalshi.com/api-reference/api-keys/create-api-key",
        },
        {
            "documented_numbering": "sequential from 1; max 63 numbered",
            "documented_tier_rule": "Advanced API tier and above",
            "method": "POST_SOURCE_CONTEXT_ONLY_NOT_B1_RUNTIME",
            "path": "/portfolio/subaccounts",
            "url": "https://docs.kalshi.com/api-reference/portfolio/create-subaccount",
        },
        {
            "recommended_demo_rest_base_url": (
                "https://external-api.demo.kalshi.co/trade-api/v2"
            ),
            "signature_path_rule": (
                "full request path from API root without query parameters"
            ),
            "supported_demo_compatibility_url": (
                "https://demo-api.kalshi.co/trade-api/v2"
            ),
            "url": "https://docs.kalshi.com/getting_started/api_environments",
        },
        {
            "purpose": "official documentation index corroboration",
            "url": "https://docs.kalshi.com/llms.txt",
        },
    ],
    "schema_revision": 1,
}


def _canonical_json_bytes(obj: object) -> bytes:
    """Deterministic canonical JSON: UTF-8, sorted keys, tight separators,
    ASCII-only escapes (B1-SRC-008, B1-EVID-003/004)."""

    return json.dumps(
        obj, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


SOURCE_BINDING_RECORD_JSON = _canonical_json_bytes(_SOURCE_BINDING_RECORD_OBJ).decode(
    "ascii"
)


def _verify_embedded_source_binding() -> None:
    raw = SOURCE_BINDING_RECORD_JSON.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != SOURCE_BINDING_RECORD_BYTES:
        raise RuntimeError(
            "embedded B1 source-binding record byte length "
            f"{len(raw)} != reviewed {SOURCE_BINDING_RECORD_BYTES}"
        )
    if digest != SOURCE_BINDING_RECORD_SHA256:
        raise RuntimeError(
            "embedded B1 source-binding record sha256 mismatch: "
            f"{digest} != reviewed {SOURCE_BINDING_RECORD_SHA256}"
        )


_verify_embedded_source_binding()


def verify_source_binding_record(record_bytes: bytes) -> bool:
    """Return ``True`` iff *record_bytes* is exactly the reviewed B1
    source-binding record (B1-SRC-008, B1-TEST-011)."""

    if not isinstance(record_bytes, (bytes, bytearray)):
        raise TypeError("record_bytes must be bytes")
    raw = bytes(record_bytes)
    return (
        len(raw) == SOURCE_BINDING_RECORD_BYTES
        and hashlib.sha256(raw).hexdigest() == SOURCE_BINDING_RECORD_SHA256
    )


# ---------------------------------------------------------------------------
# Reviewed B1 request projection (B1-SRC-003, B1-REQ-001).
# ---------------------------------------------------------------------------

OP_ACCOUNT_LIMITS = "B1_GET_ACCOUNT_LIMITS"
OP_API_KEYS = "B1_GET_API_KEYS"
OP_SUBACCOUNT_BALANCES = "B1_GET_SUBACCOUNT_BALANCES"
OP_SUBACCOUNT_NETTING = "B1_GET_SUBACCOUNT_NETTING"

OPERATION_LABELS: Tuple[str, ...] = (
    OP_ACCOUNT_LIMITS,
    OP_API_KEYS,
    OP_SUBACCOUNT_BALANCES,
    OP_SUBACCOUNT_NETTING,
)

# Base-relative paths (used in the source projection and evidence records).
OP_BASE_PATHS: Mapping[str, str] = {
    OP_ACCOUNT_LIMITS: "/account/limits",
    OP_API_KEYS: "/api_keys",
    OP_SUBACCOUNT_BALANCES: "/portfolio/subaccounts/balances",
    OP_SUBACCOUNT_NETTING: "/portfolio/subaccounts/netting",
}

# Full request/signature paths (begin with the base path; query excluded).
OP_FULL_PATHS: Mapping[str, str] = {
    label: DEMO_BASE_PATH + OP_BASE_PATHS[label] for label in OPERATION_LABELS
}

ALLOWED_FULL_PATHS = frozenset(OP_FULL_PATHS.values())
ALLOWED_METHODS = frozenset({"GET"})

# Relied-on top-level response fields per operation (B1-SRC-003, B1-SCHEMA-*).
REVIEWED_REQUIRED_TOP_LEVEL: Mapping[str, Tuple[str, ...]] = {
    OP_ACCOUNT_LIMITS: ("usage_tier", "read", "write", "grants"),
    OP_API_KEYS: ("api_keys",),
    OP_SUBACCOUNT_BALANCES: ("subaccount_balances",),
    OP_SUBACCOUNT_NETTING: ("netting_configs",),
}

REVIEWED_SUBACCOUNT_MIN = 0
REVIEWED_SUBACCOUNT_MAX = 63

RECOGNIZED_USAGE_TIERS: Tuple[str, ...] = (
    "basic",
    "advanced",
    "expert",
    "premier",
    "paragon",
    "prime",
    "prestige",
)
# "Advanced API tier and above" per current Create Subaccount documentation
# (B1-FACT-004): every recognized tier except `basic`.
CREATE_TIER_RULE_TIERS = frozenset(RECOGNIZED_USAGE_TIERS) - {"basic"}

RECOGNIZED_SCOPES = frozenset(
    {
        "read",
        "write",
        "read::block_trade_accept",
        "read::portfolio_balance",
        "write::trade",
        "write::transfer",
        "write::block_trade_accept",
    }
)

PREDICTIONS_GRANT_EXCHANGE_INSTANCE = "event_contract"

# Fixed local raw-evidence basenames (B1-EVID-002).
LOCAL_RAW_BODY_FILENAMES: Mapping[str, str] = {
    OP_ACCOUNT_LIMITS: "01_account_limits.response.bin",
    OP_API_KEYS: "02_api_keys.response.bin",
    OP_SUBACCOUNT_BALANCES: "03_subaccount_balances.response.bin",
    OP_SUBACCOUNT_NETTING: "04_subaccount_netting.response.bin",
}

EVIDENCE_MANIFEST_FILENAME = "B1_ACCOUNT_SUBACCOUNT_FACTS_EVIDENCE_MANIFEST.json"
SANITIZED_SUMMARY_FILENAME = "B1_ACCOUNT_SUBACCOUNT_FACTS_SUMMARY.json"

# Accepted fixed-point balance grammar (B1-SCHEMA-003). `[0-9]` deliberately,
# never `\d`; `re.fullmatch` deliberately, never `match()` + `$`.
_BALANCE_PATTERN = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]{1,6})?")

# Canonical millisecond-timestamp text (matches orderbook.py's rule): ASCII
# digits, no leading zero, strictly positive.
_TIMESTAMP_MS_PATTERN = re.compile(r"[1-9][0-9]*")

# Lowercase 64-hex SHA-256 and a minimal RFC3339 UTC instant. Used to validate
# the non-secret evidence-binding identity carried by a task-current source
# record before any network request (C04).
_SHA256_HEX_PATTERN = re.compile(r"[0-9a-f]{64}")
_RFC3339_UTC_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z"
)


# ---------------------------------------------------------------------------
# Closed enums.
# ---------------------------------------------------------------------------


class B1TerminalOutcome(enum.StrEnum):
    """Closed terminal-outcome set (B1-TERM-001)."""

    B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED = (
        "B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED"
    )
    B1_PRIMARY_ONLY_OBSERVED = "B1_PRIMARY_ONLY_OBSERVED"
    B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY = (
        "B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY"
    )
    B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED = "B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED"
    B1_READ_CAPABILITY_INSUFFICIENT = "B1_READ_CAPABILITY_INSUFFICIENT"
    B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT = "B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT"
    B1_OFFICIAL_SOURCE_CONFLICT = "B1_OFFICIAL_SOURCE_CONFLICT"
    B1_AUTHORITATIVE_RESPONSE_MALFORMED = "B1_AUTHORITATIVE_RESPONSE_MALFORMED"
    B1_READ_FAILURE = "B1_READ_FAILURE"
    B1_SOURCE_DRIFT = "B1_SOURCE_DRIFT"
    B1_CAPABILITY_OR_SCOPE_VIOLATION = "B1_CAPABILITY_OR_SCOPE_VIOLATION"


# Deterministic precedence (B1-TERM-002): the first applicable class controls.
TERMINAL_PRECEDENCE: Tuple[B1TerminalOutcome, ...] = (
    B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION,
    B1TerminalOutcome.B1_OFFICIAL_SOURCE_CONFLICT,
    B1TerminalOutcome.B1_SOURCE_DRIFT,
    B1TerminalOutcome.B1_READ_FAILURE,
    B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED,
    B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED,
    B1TerminalOutcome.B1_READ_CAPABILITY_INSUFFICIENT,
    B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY,
    B1TerminalOutcome.B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT,
    B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED,
    B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED,
)


class B1NextRouteClass(enum.StrEnum):
    """Next-route classification (B1-ROUTE-001..004)."""

    EXISTING_NUMBERED_CANDIDATES_REQUIRE_LATER_PROOF = (
        "EXISTING_NUMBERED_CANDIDATES_REQUIRE_LATER_PROOF"
    )
    NO_NUMBERED_DOMAIN_CURRENTLY_OBSERVED = "NO_NUMBERED_DOMAIN_CURRENTLY_OBSERVED"
    RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION = (
        "RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION"
    )
    RESOLVE_SOURCE_OR_RESPONSE_CONTRACT = "RESOLVE_SOURCE_OR_RESPONSE_CONTRACT"


_NEXT_ROUTE_BY_OUTCOME: Mapping[B1TerminalOutcome, B1NextRouteClass] = {
    B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED: (
        B1NextRouteClass.EXISTING_NUMBERED_CANDIDATES_REQUIRE_LATER_PROOF
    ),
    B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED: (
        B1NextRouteClass.NO_NUMBERED_DOMAIN_CURRENTLY_OBSERVED
    ),
    B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY: (
        B1NextRouteClass.RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
    ),
    B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED: (
        B1NextRouteClass.RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
    ),
    B1TerminalOutcome.B1_READ_CAPABILITY_INSUFFICIENT: (
        B1NextRouteClass.RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
    ),
    B1TerminalOutcome.B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT: (
        B1NextRouteClass.RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
    ),
    B1TerminalOutcome.B1_READ_FAILURE: (
        B1NextRouteClass.RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
    ),
    B1TerminalOutcome.B1_OFFICIAL_SOURCE_CONFLICT: (
        B1NextRouteClass.RESOLVE_SOURCE_OR_RESPONSE_CONTRACT
    ),
    B1TerminalOutcome.B1_SOURCE_DRIFT: (
        B1NextRouteClass.RESOLVE_SOURCE_OR_RESPONSE_CONTRACT
    ),
    B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED: (
        B1NextRouteClass.RESOLVE_SOURCE_OR_RESPONSE_CONTRACT
    ),
    # A precedence-1 capability/scope violation means B1 never ran within its
    # envelope; the closest of the four defined next-route classes (Section 14,
    # handoff Section 9) is the read-scope/credential-limitation class.
    B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION: (
        B1NextRouteClass.RESOLVE_READ_SCOPE_OR_CREDENTIAL_LIMITATION
    ),
}


class CurrentKeyMatchState(enum.StrEnum):
    UNIQUE = "UNIQUE"
    ZERO_MATCH = "ZERO_MATCH"
    MULTIPLE_MATCHES = "MULTIPLE_MATCHES"
    NOT_OBSERVED = "NOT_OBSERVED"


class CurrentKeyRestrictionState(enum.StrEnum):
    UNRESTRICTED = "UNRESTRICTED"
    RESTRICTED_TO_EXACT_SUBACCOUNT = "RESTRICTED_TO_EXACT_SUBACCOUNT"
    RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN = "RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN"
    NOT_EXPOSED = "NOT_EXPOSED"
    NOT_OBSERVED = "NOT_OBSERVED"


class BalanceClass(enum.StrEnum):
    ZERO = "ZERO"
    NONZERO = "NONZERO"


class RequestStatusClass(enum.StrEnum):
    """Non-secret per-request classification recorded in the evidence
    manifest (B1-EVID-003)."""

    OK_200 = "OK_200"
    REDIRECT_3XX = "REDIRECT_3XX"
    UNAUTHORIZED_401 = "UNAUTHORIZED_401"
    FORBIDDEN_403_RESTRICTED_KEY = "FORBIDDEN_403_RESTRICTED_KEY"
    FORBIDDEN_403_GENERIC = "FORBIDDEN_403_GENERIC"
    RATE_LIMITED_429 = "RATE_LIMITED_429"
    CLIENT_ERROR_4XX = "CLIENT_ERROR_4XX"
    SERVER_ERROR_5XX = "SERVER_ERROR_5XX"
    UNEXPECTED_STATUS = "UNEXPECTED_STATUS"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    SIGNING_FAILURE = "SIGNING_FAILURE"
    TIMEOUT = "TIMEOUT"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    MEDIA_TYPE_INVALID = "MEDIA_TYPE_INVALID"
    MALFORMED_JSON = "MALFORMED_JSON"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    SOURCE_DRIFT = "SOURCE_DRIFT"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


# ---------------------------------------------------------------------------
# Errors. No error message here ever contains a secret value, a private-key
# path value, key bytes, a signature, an auth header, or a raw account
# identifier (B1-CRED-002).
# ---------------------------------------------------------------------------


class B1ProbeError(Exception):
    """Base class for B1 probe errors."""


class CapabilityScopeViolation(B1ProbeError):
    """A request target or method outside the exact B1 envelope was
    constructed or requested (B1-TERM precedence 1)."""


class CredentialSourceContractError(B1ProbeError):
    """The credential source contract (B1-CRED-001, B1-IMPL-003) was
    violated: wrong variable names, PEM content in the path variable, the
    older PEM-content variable present, or a required reference missing."""


class SigningContractError(B1ProbeError):
    """The private key could not be loaded as an RSA key, or signing failed.
    Carries no key bytes, path value, or signature."""


class SourceContractError(B1ProbeError):
    """A supplied task-current source record is structurally unusable."""


class EvidenceOutputRootError(B1ProbeError, ValueError):
    """The requested B1 evidence output root is empty/absent, or resolves to
    the canonical repository root or a descendant of it (B1-EVID-001,
    B1-CAP-002 ``local_evidence_artifact_write``, C01-03).

    Raised before any filesystem mutation. Subclasses :class:`ValueError` so
    an empty root keeps its historical exception type.
    """


# ---------------------------------------------------------------------------
# Evidence output-root containment (B1-EVID-001/002, B1-CAP-002, C01-03).
# The future evidence writer may only write to an explicit *external* output
# root: never the canonical repository root and never a descendant of it.
# ---------------------------------------------------------------------------


def _canonical_repository_root() -> Path:
    """Resolved path of the canonical repository root that contains this
    module (``<repo>/src/arb/venues/kalshi/account_subaccount_probe.py``)."""

    return Path(__file__).resolve().parents[4]


def _resolve_external_evidence_root(output_root: object) -> Path:
    """Resolve *output_root* and reject it -- before any filesystem mutation --
    when it is empty/absent, or when it resolves to the canonical repository
    root or any descendant of it (B1-EVID-001, C01-03).

    Uses resolved/canonical path comparison. On the supported Windows
    environment :meth:`pathlib.Path.resolve` plus case-insensitive
    :class:`~pathlib.PurePath` comparison is sufficient (``WindowsPath``
    equality and ``.parents`` membership already apply ``os.path.normcase``).
    """

    if not isinstance(output_root, (str, Path)) or not str(output_root).strip():
        raise EvidenceOutputRootError(
            "B1 evidence output_root must be an explicit external path"
        )
    resolved = Path(output_root).resolve()
    repo_root = _canonical_repository_root()
    if resolved == repo_root or repo_root in resolved.parents:
        raise EvidenceOutputRootError(
            "B1 evidence output_root must be outside the canonical repository; "
            "the repository root and its descendants are rejected"
        )
    return resolved


# ---------------------------------------------------------------------------
# Task-current source contract (B1-SRC-009).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceOperation:
    """One operation as described by a task-current official source record."""

    label: str
    method: str
    path: str
    required_top_level: Tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RestrictedKeyErrorSignature:
    """How a task-current source says an out-of-scope restricted-key request
    is shaped: the JSON body field name and its exact expected value
    (B1-SRC-004, B1-KEY-003)."""

    field_name: str
    expected_value: str

    def matches(self, parsed_body: object) -> bool:
        if not isinstance(parsed_body, dict):
            return False
        return parsed_body.get(self.field_name) == self.expected_value


class SourceEvaluationStatus(enum.StrEnum):
    OK = "OK"
    DRIFT = "DRIFT"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class SourceEvaluation:
    status: SourceEvaluationStatus
    findings: Tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceEvidenceBinding:
    """Immutable, non-secret provenance that deterministically identifies the
    task-current source binding an execution actually evaluated (C01).

    It is owned by :class:`TaskCurrentSourceRecord` and is the single source of
    the frozen B1-EVID-003/004 identity fields:

    * evidence manifest -- ``source_binding_name`` / ``source_binding_record_sha256``;
    * sanitized summary -- ``source_binding.name`` / ``.record_sha256`` /
      ``.observed_at_utc`` / ``.fresh_raw_openapi_status`` /
      ``.historical_openapi_context_sha256``.

    There is deliberately no module-global mutable "current source" singleton:
    the binding travels with the record passed to
    :func:`execute_b1_account_subaccount_probe`, and every terminal projection
    for that execution is built from this exact object (C02).

    ``record_sha256`` identifies whatever the task-current binding treats as its
    canonical source record (for the authoring rendered binding, the derived
    B1-SRC-008 record hash; for a task-current OpenAPI binding, the exact raw
    source SHA-256). No Git blob identity is asserted for raw external source
    bytes.
    """

    name: str
    record_sha256: str
    observed_at_utc: str
    fresh_raw_openapi_status: str
    historical_openapi_context_sha256: str

    def validate(self) -> Tuple[str, ...]:
        """Return findings describing why this evidence-binding identity is
        unusable (empty tuple == usable). Missing, malformed, or internally
        contradictory identity is rejected before any network request (C04);
        no new terminal enum is introduced -- the caller folds a non-empty
        result into the existing ``B1_SOURCE_DRIFT`` model.
        """

        findings: list[str] = []
        if not isinstance(self.name, str) or not self.name.strip():
            findings.append("source-binding name is missing")
        if (
            not isinstance(self.record_sha256, str)
            or _SHA256_HEX_PATTERN.fullmatch(self.record_sha256) is None
        ):
            findings.append(
                "source-binding record_sha256 is not a lowercase 64-hex digest"
            )
        if (
            not isinstance(self.observed_at_utc, str)
            or _RFC3339_UTC_PATTERN.fullmatch(self.observed_at_utc) is None
        ):
            findings.append("source-binding observed_at_utc is not an RFC3339 UTC instant")
        if (
            not isinstance(self.fresh_raw_openapi_status, str)
            or not self.fresh_raw_openapi_status.strip()
        ):
            findings.append("source-binding fresh_raw_openapi_status is missing")
        if (
            not isinstance(self.historical_openapi_context_sha256, str)
            or _SHA256_HEX_PATTERN.fullmatch(self.historical_openapi_context_sha256)
            is None
        ):
            findings.append(
                "source-binding historical_openapi_context_sha256 is not a "
                "lowercase 64-hex digest"
            )
        # Contradiction: a record that claims the accepted authoring binding
        # name but carries a different record hash (or vice versa) is unusable.
        claims_authoring_name = self.name == SOURCE_BINDING_NAME
        claims_authoring_hash = self.record_sha256 == SOURCE_BINDING_RECORD_SHA256
        if claims_authoring_name != claims_authoring_hash:
            findings.append(
                "source-binding name and record_sha256 disagree about whether this "
                "is the accepted authoring binding"
            )
        return tuple(findings)


# The evidence-binding identity for the accepted authoring rendered-source
# binding (B1-SRC-003/004/008). Preserved verbatim so a real execution that
# actually supplies ``authoring_task_current_source_record()`` still emits this
# exact identity (C03).
AUTHORING_SOURCE_EVIDENCE_BINDING = SourceEvidenceBinding(
    name=SOURCE_BINDING_NAME,
    record_sha256=SOURCE_BINDING_RECORD_SHA256,
    observed_at_utc=SOURCE_OBSERVED_AT_UTC,
    fresh_raw_openapi_status=FRESH_RAW_OPENAPI_STATUS,
    historical_openapi_context_sha256=HISTORICAL_OPENAPI_SNAPSHOT_SHA256,
)

# Explicit placeholder emitted -- only inside a ``B1_SOURCE_DRIFT`` terminal
# with ``request_count == 0`` -- when a task-current record carries a missing,
# malformed, or internally contradictory evidence-binding identity. It is
# deliberately not a real identity, so an unusable identity is never echoed
# into evidence as though it were trusted (C04).
_UNUSABLE_SOURCE_EVIDENCE_BINDING = SourceEvidenceBinding(
    name="UNUSABLE_SOURCE_EVIDENCE_BINDING",
    record_sha256="0" * 64,
    observed_at_utc="1970-01-01T00:00:00Z",
    fresh_raw_openapi_status="UNUSABLE_SOURCE_EVIDENCE_BINDING",
    historical_openapi_context_sha256="0" * 64,
)


def _emitted_source_binding(source_record: "TaskCurrentSourceRecord") -> SourceEvidenceBinding:
    """The evidence-binding identity every terminal projection for an
    execution is bound to (C02).

    It is the record's own ``evidence_binding`` when that identity is usable;
    otherwise the explicit unusable-identity placeholder, so a rejected
    (``B1_SOURCE_DRIFT``, pre-network) record never emits its malformed or
    contradictory identity as trusted evidence (C04)."""

    binding = getattr(source_record, "evidence_binding", None)
    if isinstance(binding, SourceEvidenceBinding) and not binding.validate():
        return binding
    return _UNUSABLE_SOURCE_EVIDENCE_BINDING


@dataclass(frozen=True, slots=True)
class TaskCurrentSourceRecord:
    """A task-current official source record for the four B1 GET operations
    (B1-SRC-009). Offline tests supply matching and materially drifted
    fixtures; a real execution must bind a genuine task-current record.

    ``api_keys_absent_subaccount_semantics`` is the only route by which an
    absent/null ``subaccount`` field in a ``GET /api_keys`` response element
    may be treated as ``UNRESTRICTED`` (B1-SRC-004, B1-KEY-001). The
    authoring rendered-source binding leaves it ``NOT_EXPOSED``.

    ``evidence_binding`` is the immutable, non-secret provenance identity that
    every terminal projection for an execution is bound to (C01/C02). It
    defaults to nothing: a genuine task-current record must supply it, and
    :meth:`evaluate_against_reviewed_contract` rejects a missing/unusable one
    before any network request (C04).
    """

    demo_rest_base_url: str
    operations: Tuple[SourceOperation, ...]
    api_keys_absent_subaccount_semantics: str  # "UNRESTRICTED" | "NOT_EXPOSED"
    subaccount_number_min: int
    subaccount_number_max: int
    restricted_key_error_signature: RestrictedKeyErrorSignature
    signature_path_excludes_query: bool
    evidence_binding: SourceEvidenceBinding
    declares_unresolved_conflict: bool = False
    record_label: str = ""
    observed_at_utc: str = ""

    def operation(self, label: str) -> Optional[SourceOperation]:
        for op in self.operations:
            if op.label == label:
                return op
        return None

    def evaluate_against_reviewed_contract(self) -> SourceEvaluation:
        """Classify this record against the reviewed B1 contract
        (B1-SRC-009, B1-FAIL-001/002, B1-TEST-011).

        C04: a missing, malformed, or internally contradictory
        ``evidence_binding`` identity is folded into ``DRIFT`` here -- i.e.
        rejected before any network request -- using the existing
        source-contract failure model rather than a new terminal enum.
        """

        findings: list[str] = []

        if self.declares_unresolved_conflict:
            return SourceEvaluation(
                status=SourceEvaluationStatus.CONFLICT,
                findings=("record declares an unresolved official-source conflict",),
            )

        if not isinstance(self.evidence_binding, SourceEvidenceBinding):
            findings.append("record carries no usable source evidence-binding identity")
        else:
            findings.extend(self.evidence_binding.validate())

        if self.api_keys_absent_subaccount_semantics not in (
            "UNRESTRICTED",
            "NOT_EXPOSED",
        ):
            findings.append(
                "api_keys_absent_subaccount_semantics is not a recognized value"
            )

        if self.demo_rest_base_url != DEMO_REST_BASE_URL:
            findings.append("demo_rest_base_url differs from the reviewed Demo base URL")

        if not self.signature_path_excludes_query:
            findings.append("signature path no longer excludes query parameters")

        if self.subaccount_number_min != REVIEWED_SUBACCOUNT_MIN:
            findings.append("subaccount minimum differs from reviewed 0")
        if self.subaccount_number_max != REVIEWED_SUBACCOUNT_MAX:
            findings.append("subaccount maximum differs from reviewed 63")

        seen_labels = {op.label for op in self.operations}
        if seen_labels != set(OPERATION_LABELS):
            findings.append("operation label set differs from the reviewed four")

        for label in OPERATION_LABELS:
            op = self.operation(label)
            if op is None:
                continue
            if op.method != "GET":
                findings.append(f"{label}: method is not GET")
            if op.path != OP_BASE_PATHS[label]:
                findings.append(f"{label}: path differs from reviewed {OP_BASE_PATHS[label]}")
            missing = [
                fld
                for fld in REVIEWED_REQUIRED_TOP_LEVEL[label]
                if fld not in op.required_top_level
            ]
            if missing:
                findings.append(
                    f"{label}: no longer requires relied-on field(s) {','.join(missing)}"
                )

        if findings:
            return SourceEvaluation(
                status=SourceEvaluationStatus.DRIFT, findings=tuple(findings)
            )
        return SourceEvaluation(status=SourceEvaluationStatus.OK, findings=())


def authoring_task_current_source_record() -> TaskCurrentSourceRecord:
    """The task-current source record equivalent to the authoring
    rendered-source binding (B1-SRC-003/004). ``NOT_EXPOSED`` absent/null
    semantics, exactly as recorded during authoring."""

    return TaskCurrentSourceRecord(
        demo_rest_base_url=DEMO_REST_BASE_URL,
        operations=tuple(
            SourceOperation(
                label=label,
                method="GET",
                path=OP_BASE_PATHS[label],
                required_top_level=REVIEWED_REQUIRED_TOP_LEVEL[label],
            )
            for label in OPERATION_LABELS
        ),
        api_keys_absent_subaccount_semantics="NOT_EXPOSED",
        subaccount_number_min=REVIEWED_SUBACCOUNT_MIN,
        subaccount_number_max=REVIEWED_SUBACCOUNT_MAX,
        restricted_key_error_signature=RestrictedKeyErrorSignature(
            field_name="code", expected_value="subaccount_restricted"
        ),
        signature_path_excludes_query=True,
        evidence_binding=AUTHORING_SOURCE_EVIDENCE_BINDING,
        record_label="AUTHORING_RENDERED_SOURCE_BINDING_EQUIVALENT",
        observed_at_utc=SOURCE_OBSERVED_AT_UTC,
    )


# ---------------------------------------------------------------------------
# Request-target containment (B1-REQ-001, B1-REQ-006, B1-TEST-001).
# ---------------------------------------------------------------------------


def evaluate_request_target(
    *, scheme: str, host: str, port: int, path: str, method: str
) -> None:
    """Raise :class:`CapabilityScopeViolation` unless the tuple is exactly
    one of the four permitted B1 GET targets on the exact Demo origin.

    Rejects: non-HTTPS, non-443, any host other than
    ``external-api.demo.kalshi.co`` (including the compatibility Demo host and
    every production host), any path outside the four full B1 paths, and any
    method other than ``GET``.
    """

    if method not in ALLOWED_METHODS:
        raise CapabilityScopeViolation(f"method {method!r} is not permitted; only GET")
    if scheme != DEMO_SCHEME:
        raise CapabilityScopeViolation(f"scheme {scheme!r} is not https")
    if host in PROHIBITED_HOSTS:
        raise CapabilityScopeViolation(f"host {host!r} is a prohibited fallback host")
    if host != DEMO_HOST:
        raise CapabilityScopeViolation(f"host {host!r} is not the exact Demo host")
    if port != DEMO_PORT:
        raise CapabilityScopeViolation(f"port {port!r} is not 443")
    if path not in ALLOWED_FULL_PATHS:
        raise CapabilityScopeViolation(f"path {path!r} is not an allowlisted B1 path")


def is_permitted_b1_target(url: str, method: str = "GET") -> bool:
    """Return ``True`` iff *url* + *method* is exactly a permitted B1 target.

    Any query string, fragment, or userinfo component makes the URL
    impermissible (B1-TEST-001).
    """

    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.query or parts.fragment:
        return False
    if parts.username is not None or parts.password is not None:
        return False
    try:
        port = parts.port if parts.port is not None else (
            443 if parts.scheme == "https" else -1
        )
    except ValueError:
        return False
    try:
        evaluate_request_target(
            scheme=parts.scheme,
            host=parts.hostname or "",
            port=port if port is not None else -1,
            path=parts.path,
            method=method,
        )
    except CapabilityScopeViolation:
        return False
    return True


# ---------------------------------------------------------------------------
# Pure request-plan construction (B1-REQ-001).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestPlan:
    """One immutable, fully bound B1 request. Empty query, empty body."""

    sequence: int
    operation_label: str
    method: str
    scheme: str
    host: str
    port: int
    full_path: str
    base_path: str

    def __post_init__(self) -> None:
        if self.method != "GET":
            raise CapabilityScopeViolation("RequestPlan.method must be GET")
        evaluate_request_target(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            path=self.full_path,
            method=self.method,
        )
        if not (1 <= self.sequence <= MAX_REQUEST_COUNT):
            raise CapabilityScopeViolation("RequestPlan.sequence out of 1..4")
        if self.operation_label not in OPERATION_LABELS:
            raise CapabilityScopeViolation("RequestPlan.operation_label unknown")
        if OP_FULL_PATHS[self.operation_label] != self.full_path:
            raise CapabilityScopeViolation("RequestPlan path/label mismatch")


def build_request_plan_sequence() -> Tuple[RequestPlan, ...]:
    """The fixed four-request sequence, in order (B1-REQ-001). No discovery,
    no additional requests are representable."""

    return tuple(
        RequestPlan(
            sequence=index + 1,
            operation_label=label,
            method="GET",
            scheme=DEMO_SCHEME,
            host=DEMO_HOST,
            port=DEMO_PORT,
            full_path=OP_FULL_PATHS[label],
            base_path=OP_BASE_PATHS[label],
        )
        for index, label in enumerate(OPERATION_LABELS)
    )


# ---------------------------------------------------------------------------
# Pure signing-message construction (B1-CRED, B1-SRC-006, Section 7).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SigningMessage:
    """The exact bytes to be signed: ``timestamp_ms_text + "GET" + full_path``
    (UTF-8), with no separator and no query. Query is excluded (B1-SRC-006)."""

    timestamp_ms_text: str
    method: str
    full_path: str
    message_bytes: bytes


def _timestamp_ms_text_is_canonical(value: object) -> bool:
    return (
        type(value) is str
        and _TIMESTAMP_MS_PATTERN.fullmatch(value) is not None
        and len(value) <= 20
    )


def build_signing_message(plan: RequestPlan, timestamp_ms_text: str) -> SigningMessage:
    """Construct the canonical signing message for *plan* (Section 7).

    Reuses the already-canonical ARB authenticated-GET signing-message
    construction (see ``orderbook.build_orderbook_signing_message``):
    ``timestamp_ms_text + method + full_path`` with no separator, UTF-8.
    """

    if type(plan) is not RequestPlan:
        raise CapabilityScopeViolation("build_signing_message requires a RequestPlan")
    if not _timestamp_ms_text_is_canonical(timestamp_ms_text):
        raise SigningContractError("timestamp_ms_text is not canonical millisecond text")
    # Defence in depth: re-verify the plan target before it is signed.
    evaluate_request_target(
        scheme=plan.scheme,
        host=plan.host,
        port=plan.port,
        path=plan.full_path,
        method=plan.method,
    )
    message_text = timestamp_ms_text + plan.method + plan.full_path
    return SigningMessage(
        timestamp_ms_text=timestamp_ms_text,
        method=plan.method,
        full_path=plan.full_path,
        message_bytes=message_text.encode("utf-8"),
    )


# ---------------------------------------------------------------------------
# Credential-source boundary (B1-CRED-001, B1-IMPL-003). No real value is
# read here; only environment-variable *names* are consulted, and the
# private-key variable is required to hold a path, never PEM bytes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class B1CredentialRefs:
    """Resolved, non-logged credential references. ``api_key_id`` is the
    in-memory current key ID for ``/api_keys`` matching; ``private_key_path``
    is a filesystem path. Neither is exposed by ``repr``/``str`` (B1-CRED-002,
    B1-EVID-004)."""

    api_key_id: str
    private_key_path: str

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "B1CredentialRefs(<redacted>)"

    __str__ = __repr__


_HEADER_SAFE_KEY_ID = re.compile(r"[A-Za-z0-9._~:-]{1,256}")


def _looks_like_pem(value: str) -> bool:
    return (
        "-----BEGIN" in value
        or "\n" in value
        or "\r" in value
        or "PRIVATE KEY" in value
    )


def load_b1_credentials(env: Mapping[str, str]) -> B1CredentialRefs:
    """Resolve the two -- and only two -- permitted credential references
    from *env* (a mapping of variable names to values; ``os.environ`` for a
    real execution, a synthetic dict for tests).

    Raises :class:`CredentialSourceContractError` if the older
    ``KALSHI_DEMO_PRIVATE_KEY_PEM`` name is present, if a required name is
    missing, if the path variable contains PEM content, or if the key ID is
    not header-safe. No value is placed in the exception message.
    """

    if FORBIDDEN_PRIVATE_KEY_PEM_ENV in env:
        raise CredentialSourceContractError(
            "the older PEM-content credential variable is present; B1 uses only "
            "KALSHI_DEMO_API_KEY_ID and KALSHI_DEMO_PRIVATE_KEY_PATH"
        )
    api_key_id = env.get(API_KEY_ID_ENV)
    private_key_path = env.get(PRIVATE_KEY_PATH_ENV)
    if not api_key_id:
        raise CredentialSourceContractError(f"{API_KEY_ID_ENV} is not set")
    if not private_key_path:
        raise CredentialSourceContractError(f"{PRIVATE_KEY_PATH_ENV} is not set")
    if _looks_like_pem(private_key_path):
        raise CredentialSourceContractError(
            f"{PRIVATE_KEY_PATH_ENV} must contain a filesystem path, not PEM content"
        )
    if _HEADER_SAFE_KEY_ID.fullmatch(api_key_id) is None:
        raise CredentialSourceContractError(
            f"{API_KEY_ID_ENV} contains characters not permitted in a request header"
        )
    return B1CredentialRefs(api_key_id=api_key_id, private_key_path=private_key_path)


# ---------------------------------------------------------------------------
# Signing boundary (Section 7). Injected for tests; the default loads an RSA
# private key from the filesystem path and signs with the canonical ARB
# authenticated-GET RSA-PSS profile. No passphrase surface exists.
# ---------------------------------------------------------------------------


class MessageSigner(Protocol):
    def sign(self, message_bytes: bytes) -> bytes:
        """Return the raw signature bytes for *message_bytes*."""


class RsaPssSha256FileSigner:
    """Loads an RSA private key from a filesystem path and signs with
    RSA-PSS / SHA-256 / MGF1(SHA-256), salt length = SHA-256 digest length.

    This is the already-canonical ARB authenticated-GET signing profile,
    statically established from ``orderbook._sign_orderbook_message`` and
    ``order_lifecycle`` (``SIGNING_PROFILE``). The only B1 difference is the
    key *source*: a filesystem path (``KALSHI_DEMO_PRIVATE_KEY_PATH``) rather
    than the older PEM-content environment variable.
    """

    __slots__ = ("_private_key_path",)

    def __init__(self, private_key_path: str) -> None:
        self._private_key_path = private_key_path

    def sign(self, message_bytes: bytes) -> bytes:
        if not isinstance(message_bytes, (bytes, bytearray)):
            raise SigningContractError("message_bytes must be bytes")
        try:
            key_bytes = Path(self._private_key_path).read_bytes()
        except OSError as exc:
            raise SigningContractError(
                "unable to read the configured private-key file"
            ) from exc
        try:
            private_key = load_pem_private_key(key_bytes, password=None)
        except Exception as exc:  # noqa: BLE001 - normalized, no detail leaked
            raise SigningContractError("configured private key is not loadable PEM") from exc
        finally:
            key_bytes = b""
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise SigningContractError("configured private key is not an RSA key")
        try:
            return private_key.sign(
                bytes(message_bytes),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=hashes.SHA256().digest_size,
                ),
                hashes.SHA256(),
            )
        except Exception as exc:  # noqa: BLE001
            raise SigningContractError("signing failed") from exc


def _resolve_signer(
    signer: Optional[MessageSigner], creds: B1CredentialRefs
) -> MessageSigner:
    if signer is not None:
        return signer
    return RsaPssSha256FileSigner(creds.private_key_path)


# ---------------------------------------------------------------------------
# Authenticated request assembly. The three KALSHI-ACCESS-* header values are
# secret-adjacent and are never rendered by repr/str (B1-CRED-002).
# ---------------------------------------------------------------------------

_ACCESS_KEY_HEADER = "KALSHI-ACCESS-KEY"
_ACCESS_SIGNATURE_HEADER = "KALSHI-ACCESS-SIGNATURE"
_ACCESS_TIMESTAMP_HEADER = "KALSHI-ACCESS-TIMESTAMP"


@dataclass(frozen=True, slots=True)
class AuthenticatedHttpRequest:
    """Everything a transport needs to send exactly one B1 GET. The header
    tuple carries the KALSHI-ACCESS-* values; ``repr``/``str`` redact them."""

    sequence: int
    operation_label: str
    method: str
    scheme: str
    host: str
    port: int
    full_path: str
    _headers: Tuple[Tuple[str, str], ...]

    def headers(self) -> Tuple[Tuple[str, str], ...]:
        return self._headers

    def __repr__(self) -> str:
        return (
            "AuthenticatedHttpRequest("
            f"sequence={self.sequence}, operation_label={self.operation_label!r}, "
            f"method={self.method!r}, scheme={self.scheme!r}, host={self.host!r}, "
            f"port={self.port}, full_path={self.full_path!r}, "
            f"headers=<redacted:{len(self._headers)}>)"
        )

    __str__ = __repr__


def build_authenticated_request(
    plan: RequestPlan,
    signing_message: SigningMessage,
    signature_b64: str,
    api_key_id: str,
) -> AuthenticatedHttpRequest:
    """Assemble the signed request for *plan* (Section 7, B1-REQ-007)."""

    if signing_message.full_path != plan.full_path or signing_message.method != plan.method:
        raise SigningContractError("signing message is not bound to this plan")
    evaluate_request_target(
        scheme=plan.scheme,
        host=plan.host,
        port=plan.port,
        path=plan.full_path,
        method=plan.method,
    )
    headers = (
        ("Host", plan.host),
        (_ACCESS_KEY_HEADER, api_key_id),
        (_ACCESS_SIGNATURE_HEADER, signature_b64),
        (_ACCESS_TIMESTAMP_HEADER, signing_message.timestamp_ms_text),
        ("Accept", "application/json"),
        ("Accept-Encoding", "identity"),
        ("Connection", "close"),
    )
    return AuthenticatedHttpRequest(
        sequence=plan.sequence,
        operation_label=plan.operation_label,
        method=plan.method,
        scheme=plan.scheme,
        host=plan.host,
        port=plan.port,
        full_path=plan.full_path,
        _headers=headers,
    )


# ---------------------------------------------------------------------------
# Clock boundary (B1-REQ-004). Monotonic for deadlines; wall clock only for
# non-authoritative evidence timestamps and the signing timestamp.
# ---------------------------------------------------------------------------


class Clock(Protocol):
    def monotonic_ns(self) -> int:
        ...

    def unix_millis(self) -> int:
        ...

    def now_utc_rfc3339(self) -> str:
        ...


class SystemClock:
    """Real clock. Uses only :mod:`time`/:mod:`datetime`; no I/O."""

    __slots__ = ()

    def monotonic_ns(self) -> int:
        import time

        return time.monotonic_ns()

    def unix_millis(self) -> int:
        import time

        return int(time.time() * 1000)

    def now_utc_rfc3339(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Transport boundary (C02-02, C03-01).
#
# The transport establishes response *metadata only* (status + headers) and
# hands back a bounded :class:`ResponseBodyReader`. It never reads,
# materialises, accumulates, or returns response-body bytes. The B1 runner
# itself owns the only blocking response-body read loop (see
# :func:`_read_response_body`): every read requests a finite, positive maximum
# and is preceded by the effective ``min(per-request, global)`` deadline
# check. This module ships NO implementation that can reach a network; a real
# execution task must inject its own bounded transport.
#
# C03-01: the *initial* blocking request/status operation is bounded too.
# :meth:`Transport.perform` receives a mandatory ``timeout_ms`` -- the
# B1-computed finite, positive remainder of the same immutable
# ``min(per-request, global)`` budget -- and every potentially blocking
# reader cleanup step (:meth:`ResponseBodyReader.close`) receives the same
# recomputed remainder. B1 never starts a second per-request timer and never
# resets the deadline; if no positive budget remains B1 does not begin the
# operation at all.
# ---------------------------------------------------------------------------


class ResponseBodyReader(Protocol):
    """A bounded, B1-driven reader over one response body (C02-02, C03-01-C).

    The B1 runner calls :meth:`read` repeatedly. Each call performs at most
    one bounded blocking read of no more than *max_bytes* bytes, honouring
    *timeout_ms* as the remaining effective budget, and returns the bytes
    actually read. An empty ``bytes`` return means end-of-body. A conforming
    reader MUST NOT return more than *max_bytes* bytes.

    :meth:`close` also receives a ``timeout_ms``: any cleanup that could block
    on the network MUST be bounded by it, and the reader MUST NOT start a new
    unbounded network step. The B1 runner checks the effective
    ``min(per-request, global)`` deadline before calling :meth:`close`, passes
    the finite positive remainder, and skips the call entirely when no
    positive budget remains (C03-01-C).
    """

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        ...

    def close(self, timeout_ms: int) -> None:
        ...


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """The result of one transport send. ``kind`` is one of ``"RESPONSE"``,
    ``"TIMEOUT"``, ``"TRANSPORT_ERROR"``.

    For ``"RESPONSE"`` the transport has established ``status`` and
    ``headers`` and provides ``reader`` -- a :class:`ResponseBodyReader` the
    B1 runner drives itself. The body is never carried here: there is no
    full-body field, no pre-materialised chunk tuple, and no ``read_all``.
    ``error_detail`` is a short non-secret token only.
    """

    kind: str
    status: Optional[int] = None
    headers: Tuple[Tuple[str, str], ...] = ()
    reader: Optional[ResponseBodyReader] = None
    error_detail: Optional[str] = None


class Transport(Protocol):
    def perform(
        self, request: AuthenticatedHttpRequest, timeout_ms: int
    ) -> TransportResponse:
        """Send *request*, establish the response status and headers, and
        return a :class:`TransportResponse`.

        *timeout_ms* (C03-01-A) is the B1-computed finite, positive remainder
        of the immutable ``min(per-request, global)`` budget, measured
        immediately before this call. A conforming implementation MUST bound
        the whole blocking initial operation -- connection setup, TLS
        handshake, request transmission, and response status/header
        acquisition -- by *timeout_ms*. It MUST NOT start its own per-request
        timer, ignore *timeout_ms*, or treat it as a fresh 10 000 ms when the
        global remainder is smaller. Exceeding it MUST surface as a
        ``"TIMEOUT"`` outcome (or simply by returning after the deadline,
        which the B1 runner re-checks); it MUST NOT retry.

        A conforming implementation MUST NOT:

        * read, materialise, or accumulate the response body before
          returning;
        * return full body bytes or a pre-materialised chunk tuple;
        * expose or use a ``read_all``-style whole-body convenience;
        * accept a sink and privately own the body-read loop;
        * follow redirects, retry, or fall back to any other host.

        For a ``"RESPONSE"`` outcome it MUST provide ``reader``; the B1 runner
        performs every blocking body read itself.
        """


class UnavailableTransport:
    """Default transport. Always raises: B1 real venue execution requires a
    separately authorized task that injects its own bounded transport."""

    __slots__ = ()

    def perform(
        self, request: AuthenticatedHttpRequest, timeout_ms: int
    ) -> TransportResponse:
        raise CapabilityScopeViolation(
            "no transport injected; B1 authenticated Demo execution is not "
            "authorized by this task"
        )


# ---------------------------------------------------------------------------
# Strict JSON / media-type helpers (B1-REQ-007, B1-SCHEMA-*).
# ---------------------------------------------------------------------------


class _MalformedResponse(B1ProbeError):
    def __init__(self, status_class: RequestStatusClass, detail: str) -> None:
        super().__init__(detail)
        self.status_class = status_class
        self.detail = detail


class _SourceDrift(B1ProbeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _reject_duplicate_keys(pairs: Sequence[Tuple[str, object]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise _MalformedResponse(
                RequestStatusClass.MALFORMED_JSON, f"duplicate JSON key {key!r}"
            )
        seen[key] = value
    return seen


def _parse_json_object(raw: bytes) -> dict:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _MalformedResponse(
            RequestStatusClass.MALFORMED_JSON, "response body is not valid UTF-8"
        ) from exc
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise _MalformedResponse(
            RequestStatusClass.MALFORMED_JSON, "response body is not valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "response body is not a JSON object"
        )
    return parsed


def _require_json_media_type(headers: Sequence[Tuple[str, str]]) -> None:
    value: Optional[str] = None
    for name, raw in headers:
        if name.lower() == "content-type":
            value = raw
            break
    if value is None or value.strip() == "":
        raise _MalformedResponse(
            RequestStatusClass.MEDIA_TYPE_INVALID, "missing Content-Type"
        )
    parts = [segment.strip() for segment in value.split(";")]
    if parts[0].lower() != "application/json":
        raise _MalformedResponse(
            RequestStatusClass.MEDIA_TYPE_INVALID, "Content-Type is not application/json"
        )
    for param in parts[1:]:
        if param == "":
            continue
        if not param.lower().startswith("charset="):
            raise _MalformedResponse(
                RequestStatusClass.MEDIA_TYPE_INVALID,
                "Content-Type carries a non-charset parameter",
            )


def _require_exact_int(value: object, what: str) -> int:
    # `type(value) is int` excludes bool (a subclass of int) and every int
    # subclass (B1-SCHEMA: "JSON booleans MUST NOT satisfy integer
    # requirements").
    if type(value) is not int:
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, f"{what} is not a JSON integer"
        )
    return value


def _require_exact_bool(value: object, what: str) -> bool:
    if type(value) is not bool:
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, f"{what} is not a JSON boolean"
        )
    return value


def _require_exact_str(value: object, what: str) -> str:
    if type(value) is not str:
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, f"{what} is not a JSON string"
        )
    return value


def _require_subaccount_number(value: object) -> int:
    number = _require_exact_int(value, "subaccount_number")
    if not (REVIEWED_SUBACCOUNT_MIN <= number <= REVIEWED_SUBACCOUNT_MAX):
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID,
            "subaccount_number outside 0..63",
        )
    return number


# ---------------------------------------------------------------------------
# Balance fixed-point parsing (B1-SCHEMA-003, B1-TEST-007).
# ---------------------------------------------------------------------------


def parse_balance_decimal(value: object) -> Tuple[Decimal, BalanceClass]:
    """Parse a balance from its original JSON string using exact
    :class:`~decimal.Decimal` arithmetic. Binary float is never used.

    Returns ``(decimal_value, BalanceClass)``. Raises
    :class:`_MalformedResponse` for any value outside the accepted grammar
    ``^-?(0|[1-9][0-9]*)(\\.[0-9]{1,6})?$`` (no exponent, NaN, infinity,
    leading ``+``, whitespace, comma, or more than six fractional digits).
    """

    if type(value) is not str:
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "balance is not a JSON string"
        )
    if _BALANCE_PATTERN.fullmatch(value) is None:
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "balance fails the fixed-point grammar"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - grammar precludes this
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "balance is not a valid decimal"
        ) from exc
    return parsed, (BalanceClass.ZERO if parsed == 0 else BalanceClass.NONZERO)


# ---------------------------------------------------------------------------
# Response projections (B1-SCHEMA-001..004).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GrantProjection:
    exchange_instance: str
    level: str
    source: str
    expires_ts: Optional[int]


@dataclass(frozen=True, slots=True)
class AccountLimitsProjection:
    usage_tier: str
    relevant_grants: Tuple[GrantProjection, ...]


def _require_top_level_fields(body: dict, label: str) -> None:
    for fld in REVIEWED_REQUIRED_TOP_LEVEL[label]:
        if fld not in body:
            raise _MalformedResponse(
                RequestStatusClass.SCHEMA_INVALID,
                f"{label}: missing required top-level field {fld!r}",
            )


def parse_account_limits(body: dict) -> AccountLimitsProjection:
    """B1-SCHEMA-001. An unrecognized ``usage_tier`` *value* is source drift;
    a wrong relied-on *type* or missing relied-on field is malformed."""

    _require_top_level_fields(body, OP_ACCOUNT_LIMITS)

    usage_tier = _require_exact_str(body["usage_tier"], "usage_tier")
    if usage_tier not in RECOGNIZED_USAGE_TIERS:
        raise _SourceDrift(f"unrecognized usage_tier value {usage_tier!r}")

    for bucket_name in ("read", "write"):
        bucket = body[bucket_name]
        if not isinstance(bucket, dict):
            raise _MalformedResponse(
                RequestStatusClass.SCHEMA_INVALID, f"{bucket_name} is not an object"
            )
        for rate_field in ("refill_rate", "bucket_capacity"):
            if rate_field not in bucket:
                raise _MalformedResponse(
                    RequestStatusClass.SCHEMA_INVALID,
                    f"{bucket_name}.{rate_field} is missing",
                )
            _require_exact_int(bucket[rate_field], f"{bucket_name}.{rate_field}")

    grants_raw = body["grants"]
    if not isinstance(grants_raw, list):
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "grants is not an array"
        )
    relevant: list[GrantProjection] = []
    for grant in grants_raw:
        if not isinstance(grant, dict):
            raise _MalformedResponse(
                RequestStatusClass.SCHEMA_INVALID, "grant element is not an object"
            )
        exchange_instance = _require_exact_str(
            grant.get("exchange_instance"), "grant.exchange_instance"
        )
        level = _require_exact_str(grant.get("level"), "grant.level")
        source = _require_exact_str(grant.get("source"), "grant.source")
        expires_raw = grant.get("expires_ts", None)
        if expires_raw is None:
            expires_ts: Optional[int] = None
        else:
            expires_ts = _require_exact_int(expires_raw, "grant.expires_ts")
        if exchange_instance == PREDICTIONS_GRANT_EXCHANGE_INSTANCE:
            relevant.append(
                GrantProjection(
                    exchange_instance=exchange_instance,
                    level=level,
                    source=source,
                    expires_ts=expires_ts,
                )
            )
    return AccountLimitsProjection(
        usage_tier=usage_tier, relevant_grants=tuple(relevant)
    )


# `subaccount` field presence sentinel for /api_keys elements.
_ABSENT = object()


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    api_key_id: str
    name: str
    scopes: Tuple[str, ...]
    subaccount: object  # int | None | _ABSENT

    def __repr__(self) -> str:
        # Never render the key id or name (B1-CRED-003): this transient must
        # not leak identifiers if it is ever logged.
        restriction = (
            self.subaccount if type(self.subaccount) is int else "absent/null"
        )
        return (
            "ApiKeyRecord(<id redacted>, <name redacted>, "
            f"scopes={list(self.scopes)}, subaccount={restriction})"
        )

    __str__ = __repr__


def parse_api_keys(body: dict) -> Tuple[ApiKeyRecord, ...]:
    """B1-SCHEMA-002. ``name`` is validated but never persisted downstream."""

    _require_top_level_fields(body, OP_API_KEYS)
    raw = body["api_keys"]
    if not isinstance(raw, list):
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "api_keys is not an array"
        )
    records: list[ApiKeyRecord] = []
    for element in raw:
        if not isinstance(element, dict):
            raise _MalformedResponse(
                RequestStatusClass.SCHEMA_INVALID, "api_keys element is not an object"
            )
        api_key_id = _require_exact_str(element.get("api_key_id"), "api_key_id")
        name = _require_exact_str(element.get("name"), "name")
        scopes_raw = element.get("scopes")
        if not isinstance(scopes_raw, list):
            raise _MalformedResponse(
                RequestStatusClass.SCHEMA_INVALID, "scopes is not an array"
            )
        scopes = tuple(_require_exact_str(s, "scope") for s in scopes_raw)
        if "subaccount" not in element:
            subaccount: object = _ABSENT
        else:
            sub_raw = element["subaccount"]
            if sub_raw is None:
                subaccount = None
            elif type(sub_raw) is int:
                if not (REVIEWED_SUBACCOUNT_MIN <= sub_raw <= REVIEWED_SUBACCOUNT_MAX):
                    raise _MalformedResponse(
                        RequestStatusClass.SCHEMA_INVALID,
                        "api_keys subaccount outside 0..63",
                    )
                subaccount = sub_raw
            else:
                raise _MalformedResponse(
                    RequestStatusClass.SCHEMA_INVALID,
                    "api_keys subaccount is neither integer nor null",
                )
        records.append(
            ApiKeyRecord(
                api_key_id=api_key_id,
                name=name,
                scopes=scopes,
                subaccount=subaccount,
            )
        )
    return tuple(records)


@dataclass(frozen=True, slots=True)
class BalanceRow:
    subaccount_number: int
    exchange_index: int
    balance: Decimal
    balance_class: BalanceClass
    updated_ts: int
    # C01-04: the original *validated lexical* balance string, retained
    # separately from the parsed ``Decimal`` so that exact-duplicate identity
    # is lexical rather than Decimal-equivalent. ``"1.0"`` and ``"1.00"`` (and
    # ``"0"`` vs ``"-0"``) therefore conflict as duplicates even though they
    # are numerically equal. Never serialized into the sanitized summary
    # (B1-EVID-005).
    balance_text: str = ""


def parse_subaccount_balances(body: dict) -> Tuple[BalanceRow, ...]:
    """B1-SCHEMA-003 + B1-SCHEMA-005 duplicate handling."""

    _require_top_level_fields(body, OP_SUBACCOUNT_BALANCES)
    raw = body["subaccount_balances"]
    if not isinstance(raw, list):
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "subaccount_balances is not an array"
        )
    by_key: dict[Tuple[int, int], BalanceRow] = {}
    order: list[Tuple[int, int]] = []
    for element in raw:
        if not isinstance(element, dict):
            raise _MalformedResponse(
                RequestStatusClass.SCHEMA_INVALID,
                "subaccount_balances element is not an object",
            )
        subaccount_number = _require_subaccount_number(element.get("subaccount_number"))
        exchange_index = _require_exact_int(
            element.get("exchange_index"), "exchange_index"
        )
        balance_raw = element.get("balance")
        balance_value, balance_class = parse_balance_decimal(balance_raw)
        updated_ts = _require_exact_int(element.get("updated_ts"), "updated_ts")
        # ``parse_balance_decimal`` has proven ``balance_raw`` is a ``str`` in
        # the accepted fixed-point grammar; keep that exact lexical text for
        # duplicate identity (C01-04).
        row = BalanceRow(
            subaccount_number=subaccount_number,
            exchange_index=exchange_index,
            balance=balance_value,
            balance_class=balance_class,
            updated_ts=updated_ts,
            balance_text=balance_raw,
        )
        key = (subaccount_number, exchange_index)
        if key in by_key:
            existing = by_key[key]
            # C01-04: exact-duplicate acceptance requires every consumed
            # authoritative field to be identical, and the balance comparison
            # is on the original *lexical* string, not the Decimal value.
            # ``"1.0"`` vs ``"1.00"`` and ``"0"`` vs ``"-0"`` therefore
            # conflict. Economic ZERO/NONZERO classification still uses exact
            # Decimal arithmetic (B1-SCHEMA-003).
            if (
                existing.balance_text != row.balance_text
                or existing.updated_ts != row.updated_ts
            ):
                raise _MalformedResponse(
                    RequestStatusClass.SCHEMA_INVALID,
                    "conflicting duplicate balance row",
                )
            # Exact lexical duplicate: canonicalize once (B1-SCHEMA-005).
            continue
        by_key[key] = row
        order.append(key)
    return tuple(by_key[key] for key in order)


@dataclass(frozen=True, slots=True)
class NettingRow:
    subaccount_number: int
    enabled: bool
    exchange_index: int


def parse_subaccount_netting(body: dict) -> Tuple[NettingRow, ...]:
    """B1-SCHEMA-004 + B1-SCHEMA-005 duplicate handling."""

    _require_top_level_fields(body, OP_SUBACCOUNT_NETTING)
    raw = body["netting_configs"]
    if not isinstance(raw, list):
        raise _MalformedResponse(
            RequestStatusClass.SCHEMA_INVALID, "netting_configs is not an array"
        )
    by_key: dict[Tuple[int, int], NettingRow] = {}
    order: list[Tuple[int, int]] = []
    for element in raw:
        if not isinstance(element, dict):
            raise _MalformedResponse(
                RequestStatusClass.SCHEMA_INVALID,
                "netting_configs element is not an object",
            )
        subaccount_number = _require_subaccount_number(element.get("subaccount_number"))
        enabled = _require_exact_bool(element.get("enabled"), "enabled")
        exchange_index = _require_exact_int(
            element.get("exchange_index"), "exchange_index"
        )
        row = NettingRow(
            subaccount_number=subaccount_number,
            enabled=enabled,
            exchange_index=exchange_index,
        )
        key = (subaccount_number, exchange_index)
        if key in by_key:
            if by_key[key] != row:
                raise _MalformedResponse(
                    RequestStatusClass.SCHEMA_INVALID,
                    "conflicting duplicate netting row",
                )
            continue
        by_key[key] = row
        order.append(key)
    return tuple(by_key[key] for key in order)


# ---------------------------------------------------------------------------
# B1-owned bounded response-body read loop (B1-REQ-004/005, C02-02).
#
# The B1 runner -- not the transport -- performs every blocking
# response-body read. Before each read the effective min(per-request, global)
# deadline is checked; each read requests a finite, positive maximum (never
# "read all"); the returned length and the per-response / cumulative ceilings
# are enforced immediately. Because these limits live in this B1-owned loop,
# no concrete transport can hand B1 an over-limit or deadline-violating body.
# ---------------------------------------------------------------------------


class _ResponseTooLarge(B1ProbeError):
    """A response reached ``MAX_RESPONSE_BYTES_PER_REQUEST`` or, cumulatively,
    ``MAX_TOTAL_RESPONSE_BYTES`` and still had at least one more body byte
    available at the B1-owned read boundary (B1-REQ-005, C02-02)."""


class _DeadlineExceeded(B1ProbeError):
    """The effective ``min(per-request, global)`` budget was exhausted at a
    B1-owned blocking response-read boundary (B1-REQ-004, C02-01/C02-02)."""


class _ReadContractError(B1ProbeError):
    """The injected :class:`ResponseBodyReader` violated its contract -- it
    returned a non-``bytes`` object or more bytes than the requested
    ``max_bytes``. B1 fails closed rather than trust it (C02-02)."""


def _read_response_body(
    reader: ResponseBodyReader,
    *,
    clock: Clock,
    effective_deadline_ns: int,
    total_prior: int,
) -> bytes:
    """Own the blocking response-body read loop for exactly one response
    (C02-02).

    ``effective_deadline_ns`` is ``min(per_request_deadline_ns,
    global_deadline_ns)``; both endpoints are immutable, so a single
    comparison against it enforces *both* the per-request and the global
    budget before every read (B1-REQ-004).

    Raises :class:`_DeadlineExceeded`, :class:`_ResponseTooLarge`, or
    :class:`_ReadContractError`. Returns the bounded body bytes on clean EOF.
    """

    body = bytearray()
    while True:
        # Deadline check / recompute immediately before every blocking read
        # (B1-REQ-004): one comparison covers per-request and global at once.
        now_ns = clock.monotonic_ns()
        if now_ns >= effective_deadline_ns:
            raise _DeadlineExceeded("effective response-read deadline exhausted")
        remaining_ms = max(1, (effective_deadline_ns - now_ns) // _MS_TO_NS)

        per_response_room = MAX_RESPONSE_BYTES_PER_REQUEST - len(body)
        cumulative_room = MAX_TOTAL_RESPONSE_BYTES - total_prior - len(body)

        if per_response_room <= 0 or cumulative_room <= 0:
            # Exactly at a ceiling: one bounded sentinel read distinguishes a
            # clean EOF from an over-limit body. Any returned byte is the
            # 262145th (or cumulative 1048577th) byte -> RESPONSE_TOO_LARGE.
            sentinel = reader.read(1, remaining_ms)
            if not isinstance(sentinel, (bytes, bytearray)):
                raise _ReadContractError("reader returned a non-bytes object")
            if len(sentinel) > 1:
                raise _ReadContractError(
                    "reader returned more bytes than requested"
                )
            if sentinel:
                raise _ResponseTooLarge(
                    "response body exceeds the byte ceiling enforced during read"
                )
            return bytes(body)

        # Finite, positive maximum for this single read (never "read all").
        want = min(per_response_room, cumulative_room, RESPONSE_READ_CHUNK_BYTES)
        chunk = reader.read(want, remaining_ms)
        if not isinstance(chunk, (bytes, bytearray)):
            raise _ReadContractError("reader returned a non-bytes object")
        if len(chunk) > want:
            raise _ReadContractError("reader returned more bytes than requested")
        if not chunk:
            return bytes(body)
        body.extend(chunk)


def _safe_close_reader(
    reader: ResponseBodyReader,
    *,
    clock: Clock,
    effective_deadline_ns: int,
) -> None:
    """Best-effort, deadline-bounded close of a B1-driven response reader
    (C03-01-C).

    The same immutable effective ``min(per-request, global)`` deadline that
    bounds :meth:`Transport.perform` and every body read also bounds cleanup.
    The monotonic clock is read once: if the effective deadline has already
    passed, B1 does NOT begin a potentially blocking close; otherwise a
    finite, positive remaining ``timeout_ms`` is derived from that single
    reading and passed to :meth:`ResponseBodyReader.close`. The deadline is
    never reset. A close failure is never itself a B1 terminal condition."""

    now_ns = clock.monotonic_ns()
    if now_ns >= effective_deadline_ns:
        return
    remaining_ms = max(1, (effective_deadline_ns - now_ns) // _MS_TO_NS)
    try:
        reader.close(remaining_ms)
    except Exception:  # noqa: BLE001 - close must not mask the real outcome
        pass


# ---------------------------------------------------------------------------
# Evidence projections (B1-EVID-003, B1-EVID-004).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestEvidence:
    sequence: int
    method: str
    path: str  # base-relative B1 path
    http_status: Optional[int]
    status_class: RequestStatusClass
    raw_response_byte_length: Optional[int]
    raw_response_sha256: Optional[str]
    observed_at_utc: Optional[str]
    local_raw_body_filename: Optional[str]

    def to_json_obj(self) -> dict:
        return {
            "sequence": self.sequence,
            "method": self.method,
            "path": self.path,
            "http_status": self.http_status,
            "status_class": self.status_class.value,
            "raw_response_byte_length": self.raw_response_byte_length,
            "raw_response_sha256": self.raw_response_sha256,
            "observed_at_utc": self.observed_at_utc,
            "local_raw_body_filename": self.local_raw_body_filename,
        }


@dataclass(frozen=True, slots=True)
class B1EvidenceManifest:
    """B1-EVID-003 local evidence manifest. No secret/header fields.

    ``source_binding`` is the exact evidence-binding identity of the source
    record the execution evaluated; the two ``source_binding_*`` manifest
    fields are projected from it, never from a fixed authoring constant (C02).
    The frozen ``schema_revision = 1`` field set is unchanged (C08).
    """

    started_at_utc: str
    completed_at_utc: str
    request_count: int
    requests: Tuple[RequestEvidence, ...]
    source_binding: SourceEvidenceBinding

    def to_json_obj(self) -> dict:
        return {
            "schema_revision": 1,
            "task_id": TASK_ID,
            "environment": ENVIRONMENT,
            "demo_rest_base_url": DEMO_REST_BASE_URL,
            "source_binding_name": self.source_binding.name,
            "source_binding_record_sha256": self.source_binding.record_sha256,
            "started_at_utc": self.started_at_utc,
            "completed_at_utc": self.completed_at_utc,
            "request_count": self.request_count,
            "retry_count": AUTOMATIC_RETRY_COUNT,
            "redirect_count": MAX_REDIRECT_COUNT,
            "requests": [item.to_json_obj() for item in self.requests],
        }

    def to_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json_obj())

    def write(self, output_root: str) -> str:
        """Write the manifest under an explicit external *output_root*
        (never the canonical repository root or a descendant -- B1-EVID-001,
        C01-03). Rejects before any filesystem mutation. Returns the path."""

        root = _resolve_external_evidence_root(output_root)
        target = root / EVIDENCE_MANIFEST_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_json_bytes())
        return str(target)


# Negative theorems that MUST remain explicitly false in every B1 summary
# (B1-EVID-004, Section 17). Frozen and copied verbatim into each result.
_NEGATIVE_THEOREMS: Mapping[str, bool] = {
    "historical_primary_incident_resolved": False,
    "historical_primary_writer_proof_released": False,
    "historical_primary_safe_to_reuse": False,
    "existing_numbered_subaccount_clean_inception_proven": False,
    "existing_numbered_subaccount_complete_history_proven": False,
    "existing_numbered_subaccount_zero_exposure_proven": False,
    "subaccount_creation_authorized": False,
    "funding_or_transfer_authorized": False,
    "canary_execution_ready": False,
    "market_maker_execution_ready": False,
    "production_behavior_known": False,
    "profitability_known": False,
    "arbitrage_proven": False,
}


@dataclass(frozen=True, slots=True)
class B1SanitizedSummary:
    """B1-EVID-004 closed sanitized projection. Contains no exact dollar
    balances, no real API key IDs, no unrelated key IDs/names, no private-key
    path value, no key bytes, no signature, no auth headers, no raw
    environment.

    ``source_binding`` is the exact evidence-binding identity of the source
    record the execution evaluated; the frozen ``source_binding`` sub-object is
    projected from it, never from a fixed authoring constant (C02). The frozen
    ``schema_revision = 1`` key set is unchanged (C08)."""

    terminal_outcome: B1TerminalOutcome
    next_route_class: B1NextRouteClass
    source_binding: SourceEvidenceBinding
    request_count: int
    usage_tier: Optional[str]
    relevant_grants: Tuple[GrantProjection, ...]
    current_key_match_state: CurrentKeyMatchState
    current_key_scopes: Tuple[str, ...]
    current_key_restriction_state: CurrentKeyRestrictionState
    current_key_restricted_subaccount_number: Optional[int]
    account_wide_enumeration_proven: bool
    balance_subaccount_numbers: Tuple[int, ...]
    netting_subaccount_numbers: Tuple[int, ...]
    surfaces_agree: Optional[bool]
    numbered_subaccounts: Tuple[int, ...]
    balance_classes: Tuple[Tuple[int, BalanceClass], ...]
    netting_states: Tuple[Tuple[int, int, bool], ...]
    documented_create_tier_rule_match: str
    evidence_manifest_bytes: Optional[int]
    evidence_manifest_sha256: Optional[str]

    def to_json_obj(self) -> dict:
        return {
            "schema_revision": 1,
            "task_id": TASK_ID,
            "environment": ENVIRONMENT,
            "demo_rest_base_url": DEMO_REST_BASE_URL,
            "source_binding": {
                "name": self.source_binding.name,
                "record_sha256": self.source_binding.record_sha256,
                "observed_at_utc": self.source_binding.observed_at_utc,
                "fresh_raw_openapi_status": self.source_binding.fresh_raw_openapi_status,
                "historical_openapi_context_sha256": (
                    self.source_binding.historical_openapi_context_sha256
                ),
            },
            "terminal_outcome": self.terminal_outcome.value,
            "next_route_class": self.next_route_class.value,
            "request_count": self.request_count,
            "retry_count": AUTOMATIC_RETRY_COUNT,
            "redirect_count": MAX_REDIRECT_COUNT,
            "api_usage": {
                "usage_tier": self.usage_tier,
                "relevant_grants": [
                    {
                        "exchange_instance": g.exchange_instance,
                        "level": g.level,
                        "source": g.source,
                        "expires_ts": g.expires_ts,
                    }
                    for g in self.relevant_grants
                ],
            },
            "current_key": {
                "match_state": self.current_key_match_state.value,
                "scopes": list(self.current_key_scopes),
                "restriction_state": self.current_key_restriction_state.value,
                "restricted_subaccount_number": (
                    self.current_key_restricted_subaccount_number
                ),
            },
            "enumeration": {
                "account_wide_enumeration_proven": self.account_wide_enumeration_proven,
                "balance_subaccount_numbers": list(self.balance_subaccount_numbers),
                "netting_subaccount_numbers": list(self.netting_subaccount_numbers),
                "surfaces_agree": self.surfaces_agree,
                "numbered_subaccounts": list(self.numbered_subaccounts),
                "balance_classes": [
                    {"subaccount_number": n, "class": c.value}
                    for n, c in self.balance_classes
                ],
                "netting_states": [
                    {
                        "subaccount_number": n,
                        "exchange_index": x,
                        "enabled": e,
                    }
                    for n, x, e in self.netting_states
                ],
            },
            "create_subaccount": {
                "documented_tier_rule": "ADVANCED_OR_ABOVE",
                "documented_tier_rule_match": self.documented_create_tier_rule_match,
                "capability": "NOT_PROVEN_BY_B1_READ_ONLY_FACTS",
            },
            "historical_primary": {
                "writer_proof_state": "HELD",
                "unresolved_exposure": "UNKNOWN_UNBOUNDED",
                "normal_writer_eligible": False,
            },
            "negative_theorems": dict(_NEGATIVE_THEOREMS),
            "evidence_manifest": {
                "raw_bytes": self.evidence_manifest_bytes,
                "sha256": self.evidence_manifest_sha256,
            },
        }

    def to_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json_obj())

    def write(self, output_root: str) -> str:
        """Write the sanitized summary under an explicit external
        *output_root* (never the canonical repository root or a descendant --
        B1-EVID-001, C01-03). Rejects before any filesystem mutation."""

        root = _resolve_external_evidence_root(output_root)
        target = root / SANITIZED_SUMMARY_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_json_bytes())
        return str(target)


@dataclass(frozen=True, slots=True)
class B1Result:
    """The terminal B1 result. ``raw_responses`` is LOCAL_ONLY raw
    authenticated evidence -- kept in memory and written to disk only when an
    explicit external ``output_root`` is supplied (B1-EVID-001/002)."""

    terminal_outcome: B1TerminalOutcome
    next_route_class: B1NextRouteClass
    summary: B1SanitizedSummary
    manifest: B1EvidenceManifest
    raw_responses: Tuple[Tuple[str, bytes], ...]  # (local_basename, body_bytes)
    detail: str = ""

    def __repr__(self) -> str:
        return (
            "B1Result("
            f"terminal_outcome={self.terminal_outcome.value}, "
            f"next_route_class={self.next_route_class.value}, "
            f"request_count={self.manifest.request_count}, "
            f"raw_responses=<{len(self.raw_responses)} local-only body/ies>)"
        )

    __str__ = __repr__

    def write_evidence(self, output_root: str) -> Tuple[str, str, Tuple[str, ...]]:
        """Write the sanitized summary, evidence manifest, and any raw
        response bodies under an explicit external *output_root*.

        Rejects -- before any filesystem mutation -- an empty/absent root and
        any root that resolves to the canonical repository root or a
        descendant of it (B1-EVID-001, C01-03). Raises
        :class:`EvidenceOutputRootError` (a :class:`ValueError`)."""

        root = _resolve_external_evidence_root(output_root)
        root.mkdir(parents=True, exist_ok=True)
        summary_path = self.summary.write(str(root))
        manifest_path = self.manifest.write(str(root))
        raw_paths: list[str] = []
        for basename, body in self.raw_responses:
            target = root / basename
            target.write_bytes(body)
            raw_paths.append(str(target))
        return summary_path, manifest_path, tuple(raw_paths)


# ---------------------------------------------------------------------------
# Internal run state.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _RunState:
    started_at_utc: str
    request_evidence: list[RequestEvidence] = field(default_factory=list)
    raw_bodies: list[Tuple[str, bytes]] = field(default_factory=list)
    consumed_total_bytes: int = 0
    request_count: int = 0

    usage_tier: Optional[str] = None
    relevant_grants: Tuple[GrantProjection, ...] = ()

    current_key_match_state: CurrentKeyMatchState = CurrentKeyMatchState.NOT_OBSERVED
    current_key_scopes: Tuple[str, ...] = ()
    current_key_restriction_state: CurrentKeyRestrictionState = (
        CurrentKeyRestrictionState.NOT_OBSERVED
    )
    current_key_restricted_subaccount_number: Optional[int] = None

    balance_rows: Tuple[BalanceRow, ...] = ()
    netting_rows: Tuple[NettingRow, ...] = ()
    balance_set: Tuple[int, ...] = ()
    netting_set: Tuple[int, ...] = ()
    surfaces_agree: Optional[bool] = None
    account_wide_enumeration_proven: bool = False
    numbered_subaccounts: Tuple[int, ...] = ()


def _documented_tier_rule_match(usage_tier: Optional[str]) -> str:
    if usage_tier is None:
        return "NOT_EVALUABLE"
    if usage_tier not in RECOGNIZED_USAGE_TIERS:
        return "NOT_EVALUABLE"
    return "YES" if usage_tier in CREATE_TIER_RULE_TIERS else "NO"


def _enforce_global_deadline(
    clock: Clock,
    global_deadline_ns: int,
    outcome: B1TerminalOutcome,
    detail: str,
) -> Tuple[B1TerminalOutcome, str]:
    """C01-01: an exhausted global deadline yields
    ``B1_READ_FAILURE``/``TIMEOUT`` unless a strictly higher-precedence
    terminal (``B1_CAPABILITY_OR_SCOPE_VIOLATION``,
    ``B1_OFFICIAL_SOURCE_CONFLICT``, ``B1_SOURCE_DRIFT``) was already
    determined (B1-REQ-004, B1-TERM-002).

    This is the one deviation from strict terminal precedence the correction
    dispatch permits, and only to enforce deadline failure: a lower-precedence
    success/malformed/disagreement terminal never masks an exhausted global
    deadline."""

    if clock.monotonic_ns() < global_deadline_ns:
        return outcome, detail
    read_failure = B1TerminalOutcome.B1_READ_FAILURE
    if TERMINAL_PRECEDENCE.index(outcome) <= TERMINAL_PRECEDENCE.index(read_failure):
        return outcome, detail
    return read_failure, "TIMEOUT"


def _project_terminal(
    state: _RunState,
    outcome: B1TerminalOutcome,
    completed_at: str,
    detail: str,
    source_binding: SourceEvidenceBinding,
) -> B1Result:
    """Pure terminal projection for *outcome*: build the evidence manifest,
    the sanitized summary, and the :class:`B1Result`.

    No deadline logic and no filesystem persistence happen here. Every field
    is derived from the already-observed *state*, so the projection stays
    internally consistent with whatever *outcome* is passed (C02-01
    requirement 7).

    *source_binding* is the exact evidence-binding identity of the source
    record supplied to this execution; both evidence projections are bound to
    it, never to a fixed authoring constant (C02)."""

    manifest = B1EvidenceManifest(
        started_at_utc=state.started_at_utc,
        completed_at_utc=completed_at,
        request_count=state.request_count,
        requests=tuple(state.request_evidence),
        source_binding=source_binding,
    )
    manifest_bytes = manifest.to_json_bytes()
    next_route = _NEXT_ROUTE_BY_OUTCOME[outcome]
    summary = B1SanitizedSummary(
        terminal_outcome=outcome,
        next_route_class=next_route,
        source_binding=source_binding,
        request_count=state.request_count,
        usage_tier=state.usage_tier,
        relevant_grants=state.relevant_grants,
        current_key_match_state=state.current_key_match_state,
        current_key_scopes=state.current_key_scopes,
        current_key_restriction_state=state.current_key_restriction_state,
        current_key_restricted_subaccount_number=(
            state.current_key_restricted_subaccount_number
        ),
        account_wide_enumeration_proven=state.account_wide_enumeration_proven,
        balance_subaccount_numbers=state.balance_set,
        netting_subaccount_numbers=state.netting_set,
        surfaces_agree=state.surfaces_agree,
        numbered_subaccounts=state.numbered_subaccounts,
        balance_classes=_summarize_balance_classes(state.balance_rows),
        netting_states=tuple(
            (r.subaccount_number, r.exchange_index, r.enabled)
            for r in sorted(
                state.netting_rows,
                key=lambda r: (r.subaccount_number, r.exchange_index),
            )
        ),
        documented_create_tier_rule_match=_documented_tier_rule_match(state.usage_tier),
        evidence_manifest_bytes=len(manifest_bytes),
        evidence_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
    return B1Result(
        terminal_outcome=outcome,
        next_route_class=next_route,
        summary=summary,
        manifest=manifest,
        raw_responses=tuple(state.raw_bodies),
        detail=detail,
    )


def _finish(
    state: _RunState,
    outcome: B1TerminalOutcome,
    clock: Clock,
    global_deadline_ns: int,
    source_binding: SourceEvidenceBinding,
    detail: str = "",
) -> B1Result:
    """Build and return exactly one terminal :class:`B1Result`.

    C02-01: the immutable global deadline dominates through the terminal
    return. It is enforced once before the terminal projection and once more
    *after* all nontrivial manifest/summary/result construction, immediately
    before the result is returned. If the deadline lapsed while the terminal
    was being projected, a lower-precedence success/failure terminal is not
    returned: the result is deterministically re-projected as
    ``B1_READ_FAILURE`` / ``TIMEOUT``.

    No evidence is persisted here. Callers that need local raw persistence
    invoke :meth:`B1Result.write_evidence` explicitly after the execute
    boundary returns (C02-01 evidence-write boundary, preferred option)."""

    completed_at = clock.now_utc_rfc3339()
    # First gate: an already-exhausted deadline downgrades a success terminal
    # before the (bounded) projection work runs.
    outcome, detail = _enforce_global_deadline(
        clock, global_deadline_ns, outcome, detail
    )
    result = _project_terminal(state, outcome, completed_at, detail, source_binding)

    # Final gate: re-check the immutable global deadline AFTER all nontrivial
    # terminal projection and immediately before returning. A crossing during
    # manifest/summary/result construction forces READ_FAILURE / TIMEOUT.
    final_outcome, final_detail = _enforce_global_deadline(
        clock, global_deadline_ns, result.terminal_outcome, result.detail
    )
    if (final_outcome, final_detail) == (result.terminal_outcome, result.detail):
        return result

    # One deterministic re-projection as the resolved timeout terminal. This
    # pass is bounded and is NOT re-gated on the deadline -- TIMEOUT is
    # already the worst applicable (non-higher-precedence) outcome, so there
    # is no reclassification loop (C02-01 requirement 5). The re-projection
    # reuses the same observed state, so request/retry/redirect counts and
    # raw-body references stay consistent with the returned timeout
    # (requirement 7); nothing success-labelled is left behind because no
    # evidence is serialized here (requirement 8).
    completed_at = clock.now_utc_rfc3339()
    return _project_terminal(
        state, final_outcome, completed_at, final_detail, source_binding
    )


def _summarize_balance_classes(
    rows: Tuple[BalanceRow, ...]
) -> Tuple[Tuple[int, BalanceClass], ...]:
    """Per-subaccount class: NONZERO if any valid row is NONZERO, ZERO only
    if every row for that subaccount is ZERO (B1-SCHEMA-003)."""

    by_sub: dict[int, BalanceClass] = {}
    for row in rows:
        if by_sub.get(row.subaccount_number) == BalanceClass.NONZERO:
            continue
        if row.balance_class == BalanceClass.NONZERO:
            by_sub[row.subaccount_number] = BalanceClass.NONZERO
        else:
            by_sub.setdefault(row.subaccount_number, BalanceClass.ZERO)
    return tuple((n, by_sub[n]) for n in sorted(by_sub))


# ---------------------------------------------------------------------------
# Status classification (B1-REQ-006/007, B1-FAIL-004, B1-KEY-003).
# ---------------------------------------------------------------------------


def _classify_http_status(
    status: int, operation_label: str, body_bytes: bytes, source: TaskCurrentSourceRecord
) -> Tuple[RequestStatusClass, B1TerminalOutcome, Optional[str]]:
    """Return ``(status_class, terminal_outcome, restriction_state_token)``
    for a non-200 status. ``restriction_state_token`` is set only for the
    exact restricted-key 403 on ``/api_keys``."""

    if 300 <= status <= 399:
        return (
            RequestStatusClass.REDIRECT_3XX,
            B1TerminalOutcome.B1_SOURCE_DRIFT,
            None,
        )
    if status == 401:
        return (
            RequestStatusClass.UNAUTHORIZED_401,
            B1TerminalOutcome.B1_READ_CAPABILITY_INSUFFICIENT,
            None,
        )
    if status == 403:
        if operation_label == OP_API_KEYS:
            parsed: object
            try:
                parsed = json.loads(body_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
            if source.restricted_key_error_signature.matches(parsed):
                return (
                    RequestStatusClass.FORBIDDEN_403_RESTRICTED_KEY,
                    B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY,
                    CurrentKeyRestrictionState.RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN.value,
                )
        return (
            RequestStatusClass.FORBIDDEN_403_GENERIC,
            B1TerminalOutcome.B1_READ_CAPABILITY_INSUFFICIENT,
            None,
        )
    if status == 429:
        return (
            RequestStatusClass.RATE_LIMITED_429,
            B1TerminalOutcome.B1_READ_FAILURE,
            None,
        )
    if 500 <= status <= 599:
        return (
            RequestStatusClass.SERVER_ERROR_5XX,
            B1TerminalOutcome.B1_READ_FAILURE,
            None,
        )
    if 400 <= status <= 499:
        return (
            RequestStatusClass.CLIENT_ERROR_4XX,
            B1TerminalOutcome.B1_READ_FAILURE,
            None,
        )
    return (
        RequestStatusClass.UNEXPECTED_STATUS,
        B1TerminalOutcome.B1_READ_FAILURE,
        None,
    )


# ---------------------------------------------------------------------------
# The venue-capable execute boundary (B1-REQ-*, Sections 9-16).
# ---------------------------------------------------------------------------


def execute_b1_account_subaccount_probe(
    *,
    credentials_env: Mapping[str, str],
    source_record: TaskCurrentSourceRecord,
    transport: Optional[Transport] = None,
    signer: Optional[MessageSigner] = None,
    clock: Optional[Clock] = None,
) -> B1Result:
    """Run the bounded B1 probe and return exactly one :class:`B1Result`.

    All venue-facing behaviour goes through the injected *transport*,
    *signer*, and *clock*. With the defaults (no transport) the call cannot
    reach a network: :class:`UnavailableTransport` raises before any request.
    Offline tests inject fakes.

    C02-01 evidence-write boundary: this execute boundary constructs and
    returns the terminal :class:`B1Result` and performs **no** evidence
    filesystem writes. Local raw persistence is a separate, explicit step --
    :meth:`B1Result.write_evidence` -- invoked by the caller after this
    function returns. The external-output-root containment check
    (B1-EVID-001, C01-03) lives in that persistence API.

    Never raises for a venue/source/credential condition -- every such
    condition is folded into a terminal :class:`B1Result`. Only genuine
    programming errors propagate.
    """

    clock = clock or SystemClock()
    transport = transport or UnavailableTransport()

    # C01-01: the immutable 40 000 ms global start/deadline pair is anchored
    # at entry to the venue-capable execute boundary -- before any other work
    # of that boundary (run-state construction, wall-clock reads,
    # credential/source evaluation) -- and is never reset (B1-REQ-004).
    global_start_ns = clock.monotonic_ns()
    global_deadline_ns = global_start_ns + GLOBAL_EXECUTION_DEADLINE_MS * _MS_TO_NS

    state = _RunState(started_at_utc=clock.now_utc_rfc3339())

    # C02: the evidence-binding identity every terminal projection for THIS
    # execution is bound to -- the supplied record's own identity when usable,
    # otherwise the explicit unusable-identity placeholder (C04). Never a fixed
    # module authoring constant.
    source_binding = _emitted_source_binding(source_record)

    # --- Credential-source contract (B1-CRED-001, B1-IMPL-003). -------------
    try:
        creds = load_b1_credentials(credentials_env)
    except CredentialSourceContractError as exc:
        return _finish(
            state,
            B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION,
            clock,
            global_deadline_ns,
            source_binding=source_binding,
            detail=str(exc),
        )

    active_signer = _resolve_signer(signer, creds)

    # --- Source contract evaluation (B1-SRC-009, B1-FAIL-001/002). ---------
    evaluation = source_record.evaluate_against_reviewed_contract()
    if evaluation.status is SourceEvaluationStatus.CONFLICT:
        return _finish(
            state,
            B1TerminalOutcome.B1_OFFICIAL_SOURCE_CONFLICT,
            clock,
            global_deadline_ns,
            source_binding=source_binding,
            detail="; ".join(evaluation.findings),
        )
    if evaluation.status is SourceEvaluationStatus.DRIFT:
        return _finish(
            state,
            B1TerminalOutcome.B1_SOURCE_DRIFT,
            clock,
            global_deadline_ns,
            source_binding=source_binding,
            detail="; ".join(evaluation.findings),
        )

    plans = build_request_plan_sequence()

    for plan in plans:
        # B1-REQ-002: a terminal failure on an earlier request prevents all
        # later requests -- the loop only continues on explicit success.
        if state.request_count >= MAX_REQUEST_COUNT:  # pragma: no cover - invariant
            return _finish(
                state,
                B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION,
                clock,
                global_deadline_ns,
                source_binding=source_binding,
                detail="request budget exceeded",
            )

        outcome = _perform_one_request(
            plan=plan,
            creds=creds,
            signer=active_signer,
            transport=transport,
            clock=clock,
            source_record=source_record,
            state=state,
            global_deadline_ns=global_deadline_ns,
        )
        if outcome is not None:
            terminal, detail = outcome
            return _finish(
                state,
                terminal,
                clock,
                global_deadline_ns,
                source_binding=source_binding,
                detail=detail,
            )

        # Post-request interpretation for /api_keys may end the run early.
        if plan.operation_label == OP_API_KEYS:
            early = _interpret_api_keys(state, source_record)
            if early is not None:
                terminal, detail = early
                return _finish(
                    state,
                    terminal,
                    clock,
                    global_deadline_ns,
                    source_binding=source_binding,
                    detail=detail,
                )

    # --- Reconciliation and terminal theorem (Sections 11-14). ------------
    return _reconcile_and_finish(state, clock, global_deadline_ns, source_binding)


def _perform_one_request(
    *,
    plan: RequestPlan,
    creds: B1CredentialRefs,
    signer: MessageSigner,
    transport: Transport,
    clock: Clock,
    source_record: TaskCurrentSourceRecord,
    state: _RunState,
    global_deadline_ns: int,
) -> Optional[Tuple[B1TerminalOutcome, str]]:
    """Perform one B1 request. Returns ``None`` on success (state updated),
    or ``(terminal_outcome, detail)`` on any terminal condition."""

    base_path = plan.base_path
    local_basename = LOCAL_RAW_BODY_FILENAMES[plan.operation_label]

    def evidence(
        status_class: RequestStatusClass,
        http_status: Optional[int],
        raw_len: Optional[int],
        raw_sha: Optional[str],
        observed: Optional[str],
        raw_saved: bool,
    ) -> None:
        state.request_evidence.append(
            RequestEvidence(
                sequence=plan.sequence,
                method=plan.method,
                path=base_path,
                http_status=http_status,
                status_class=status_class,
                raw_response_byte_length=raw_len,
                raw_response_sha256=raw_sha,
                observed_at_utc=observed,
                local_raw_body_filename=local_basename if raw_saved else None,
            )
        )

    # C01-01: signing / private-key preparation is pre-network work. It is
    # covered by the *global* deadline only and MUST NOT be charged to the
    # per-request network budget. Check the global deadline before doing it.
    if clock.monotonic_ns() >= global_deadline_ns:
        state.request_count += 1
        evidence(RequestStatusClass.TIMEOUT, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"

    # Sign and assemble (secret-adjacent values never leave this scope in
    # logs or evidence).
    timestamp_ms_text = str(clock.unix_millis())
    try:
        signing_message = build_signing_message(plan, timestamp_ms_text)
        signature = signer.sign(signing_message.message_bytes)
    except SigningContractError as exc:
        # A runtime signing failure (unreadable/non-RSA key file) is not a
        # scope violation -- it means the authenticated read cannot be
        # performed (B1-FAIL-004).
        state.request_count += 1
        evidence(RequestStatusClass.SIGNING_FAILURE, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_CAPABILITY_INSUFFICIENT, str(exc)
    signature_b64 = base64.b64encode(signature).decode("ascii")
    signature = b""
    request = build_authenticated_request(
        plan, signing_message, signature_b64, creds.api_key_id
    )
    signature_b64 = ""

    # The global deadline may have lapsed during signing / key file IO.
    if clock.monotonic_ns() >= global_deadline_ns:
        state.request_count += 1
        evidence(RequestStatusClass.TIMEOUT, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"

    # C01-01: the per-request timer starts *here*, immediately before the
    # first network-attributable operation, and covers the transport request,
    # the bounded response read, parse, and request-evidence construction
    # (B1-REQ-004). The effective budget is min(per-request, global).
    request_start_ns = clock.monotonic_ns()
    per_request_deadline_ns = request_start_ns + PER_REQUEST_DEADLINE_MS * _MS_TO_NS
    effective_deadline_ns = min(per_request_deadline_ns, global_deadline_ns)

    def _timed_out() -> bool:
        return clock.monotonic_ns() >= effective_deadline_ns

    # C02-02: the B1 runner owns the blocking response-body read loop. The
    # transport only establishes status + headers and returns a bounded
    # reader; it never reads, materialises, or returns body bytes.
    #
    # C03-01-A: the initial blocking request/status operation is bounded by
    # the SAME immutable effective min(per-request, global) budget. Read the
    # monotonic clock once, immediately before perform: if the effective
    # deadline has already passed, do not call the transport at all;
    # otherwise derive a finite, positive remaining timeout from that single
    # reading (never a fresh 10 000 ms when the global remainder is smaller)
    # and hand it to perform. No second per-request timer is started and the
    # deadline is never reset.
    state.request_count += 1
    now_ns = clock.monotonic_ns()
    if now_ns >= effective_deadline_ns:
        evidence(RequestStatusClass.TIMEOUT, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"
    perform_timeout_ms = max(1, (effective_deadline_ns - now_ns) // _MS_TO_NS)

    try:
        transport_response = transport.perform(request, perform_timeout_ms)
    except CapabilityScopeViolation as exc:
        # Precedence 1 (B1-TERM-002): a genuine capability/scope violation is
        # returned as-is and is never rewritten by the lower-precedence
        # post-perform deadline gate below (C03-01-B).
        evidence(RequestStatusClass.TRANSPORT_FAILURE, None, None, None, None, False)
        return B1TerminalOutcome.B1_CAPABILITY_OR_SCOPE_VIOLATION, str(exc)

    # C03-01-B: re-read the monotonic clock immediately after perform returns
    # and apply the controlling deadline BEFORE ordinary transport-result
    # classification. A RESPONSE, TRANSPORT_ERROR, or otherwise malformed
    # transport outcome produced after the effective deadline is
    # B1_READ_FAILURE / TIMEOUT -- not an ordinary TRANSPORT_FAILURE, and not
    # a body read. Nothing here retries or resends.
    if clock.monotonic_ns() >= effective_deadline_ns:
        if (
            transport_response.kind == "RESPONSE"
            and transport_response.reader is not None
        ):
            _safe_close_reader(
                transport_response.reader,
                clock=clock,
                effective_deadline_ns=effective_deadline_ns,
            )
        evidence(RequestStatusClass.TIMEOUT, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"

    if transport_response.kind == "TIMEOUT":
        evidence(RequestStatusClass.TIMEOUT, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"
    if transport_response.kind == "TRANSPORT_ERROR":
        evidence(RequestStatusClass.TRANSPORT_FAILURE, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TRANSPORT_FAILURE"
    if (
        transport_response.kind != "RESPONSE"
        or transport_response.status is None
        or transport_response.reader is None
    ):
        evidence(RequestStatusClass.TRANSPORT_FAILURE, None, None, None, None, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TRANSPORT_FAILURE"

    status = transport_response.status
    reader = transport_response.reader
    observed_at = clock.now_utc_rfc3339()

    # Redirects: never read the body, never read Location, never follow
    # (B1-REQ-006).
    if 300 <= status <= 399:
        _safe_close_reader(
            reader, clock=clock, effective_deadline_ns=effective_deadline_ns
        )
        evidence(RequestStatusClass.REDIRECT_3XX, status, None, None, observed_at, False)
        return B1TerminalOutcome.B1_SOURCE_DRIFT, "3xx redirect not followed"

    # B1-owned bounded blocking read loop: every read is deadline-gated and
    # size-bounded *here*, in B1, not in the transport (B1-REQ-004/005,
    # C02-02).
    #
    # C04-01: CAPTURE the body-read result instead of returning from inside an
    # ``except`` block. Python selects a ``return`` value *before* ``finally``
    # runs, so the previous shape chose the terminal while the reader was still
    # open: a ``_ResponseTooLarge`` detected inside the budget selected
    # B1_AUTHORITATIVE_RESPONSE_MALFORMED (precedence 5), and the bounded close
    # in ``finally`` could then consume the remaining budget and cross the
    # effective per-request deadline, yet the already-selected lower-precedence
    # terminal still returned -- violating B1-REQ-004 and the B1-TERM-002
    # ordering, in which B1_READ_FAILURE / TIMEOUT (precedence 4) outranks it.
    # The same applied to the READ_CONTRACT_VIOLATION subordinate reason.
    #
    # There is no ``return`` anywhere inside this statement: the read result is
    # captured, exactly one bounded cleanup runs in ``finally`` (including when
    # an unexpected exception propagates), and terminal precedence is evaluated
    # only afterwards.
    body_bytes: Optional[bytes] = None
    read_error: Optional[B1ProbeError] = None
    try:
        body_bytes = _read_response_body(
            reader,
            clock=clock,
            effective_deadline_ns=effective_deadline_ns,
            total_prior=state.consumed_total_bytes,
        )
    except (_DeadlineExceeded, _ResponseTooLarge, _ReadContractError) as exc:
        read_error = exc
    finally:
        # C03-01-C preserved: exactly one best-effort cleanup, bounded by the
        # SAME immutable effective min(per-request, global) deadline. No new
        # timer is started and the deadline is never reset.
        _safe_close_reader(
            reader, clock=clock, effective_deadline_ns=effective_deadline_ns
        )

    if read_error is not None:
        # C04-01: post-close effective-deadline precedence gate, evaluated
        # AFTER the bounded cleanup and BEFORE the captured read result is
        # projected.
        #
        # No higher-precedence terminal can be outstanding here.
        # B1_CAPABILITY_OR_SCOPE_VIOLATION (precedence 1) returns at the
        # ``transport.perform`` boundary above, and B1_SOURCE_DRIFT
        # (precedence 3) returns on the 3xx path above -- each *before* the
        # body read begins. Those paths run their own bounded close and are
        # deliberately NOT gated on the deadline, so an established
        # SOURCE_DRIFT (or capability/scope violation, or the later
        # B1_OFFICIAL_SOURCE_CONFLICT) remains controlling even when its
        # bounded cleanup crosses the deadline. This gate therefore only
        # promotes READ_FAILURE / TIMEOUT (precedence 4) over the strictly
        # lower-precedence captured results.
        if _timed_out():
            # Deadline exhausted at or before cleanup completion: TIMEOUT
            # outranks a captured _ResponseTooLarge projection
            # (B1_AUTHORITATIVE_RESPONSE_MALFORMED, precedence 5) and replaces
            # the READ_CONTRACT_VIOLATION subordinate reason. The bounded body
            # was not completed, so no length/hash is fabricated and no raw
            # body is persisted (Section 7).
            evidence(RequestStatusClass.TIMEOUT, status, None, None, observed_at, False)
            return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"

        # Still inside the effective deadline: project the captured result
        # normally.
        if isinstance(read_error, _ResponseTooLarge):
            evidence(
                RequestStatusClass.RESPONSE_TOO_LARGE, status, None, None, observed_at, False
            )
            return (
                B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED,
                str(read_error),
            )
        if isinstance(read_error, _ReadContractError):
            evidence(
                RequestStatusClass.TRANSPORT_FAILURE, status, None, None, observed_at, False
            )
            return B1TerminalOutcome.B1_READ_FAILURE, "READ_CONTRACT_VIOLATION"
        # _DeadlineExceeded: the read loop refused to start a blocking read
        # because the effective deadline was already exhausted, so the gate
        # above normally covers it; project it explicitly and fail closed.
        evidence(RequestStatusClass.TIMEOUT, status, None, None, observed_at, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"

    # Captured success: continue normal response handling. The existing
    # post-acquisition deadline gate below (C01-01/C02-01) is unchanged and
    # still runs after the bounded close, exactly as before.
    assert body_bytes is not None
    state.consumed_total_bytes += len(body_bytes)
    raw_sha = hashlib.sha256(body_bytes).hexdigest()

    # C01-01: a deadline crossing during / just after bounded body acquisition.
    if _timed_out():
        evidence(RequestStatusClass.TIMEOUT, status, len(body_bytes), raw_sha, observed_at, False)
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"

    if status != 200:
        status_class, terminal, restriction_token = _classify_http_status(
            status, plan.operation_label, body_bytes, source_record
        )
        evidence(status_class, status, len(body_bytes), raw_sha, observed_at, False)
        if (
            restriction_token is not None
            and plan.operation_label == OP_API_KEYS
        ):
            state.current_key_match_state = CurrentKeyMatchState.NOT_OBSERVED
            state.current_key_restriction_state = (
                CurrentKeyRestrictionState.RESTRICTED_EXACT_SUBACCOUNT_NOT_PROVEN
            )
        return terminal, f"HTTP {status}"

    # 200: media type + strict JSON + schema.
    try:
        _require_json_media_type(transport_response.headers)
        body = _parse_json_object(body_bytes)
        _apply_schema(plan.operation_label, body, state, creds)
    except _SourceDrift as exc:
        evidence(RequestStatusClass.SOURCE_DRIFT, status, len(body_bytes), raw_sha, observed_at, True)
        state.raw_bodies.append((local_basename, body_bytes))
        return B1TerminalOutcome.B1_SOURCE_DRIFT, exc.detail
    except _MalformedResponse as exc:
        evidence(exc.status_class, status, len(body_bytes), raw_sha, observed_at, True)
        state.raw_bodies.append((local_basename, body_bytes))
        # C01-01: a per-request/global deadline crossed while parsing outranks
        # a malformed-response terminal (B1-TERM-002: READ_FAILURE precedes
        # AUTHORITATIVE_RESPONSE_MALFORMED). SOURCE_DRIFT, which outranks
        # READ_FAILURE, is intentionally not yielded here.
        if _timed_out():
            return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"
        return B1TerminalOutcome.B1_AUTHORITATIVE_RESPONSE_MALFORMED, exc.detail

    evidence(RequestStatusClass.OK_200, status, len(body_bytes), raw_sha, observed_at, True)
    state.raw_bodies.append((local_basename, body_bytes))

    # C01-01: the per-request + global budget also covers parse and
    # request-evidence construction; the per-request timer "ends" only here,
    # after the request-level evidence record is built (B1-REQ-004).
    if _timed_out():
        return B1TerminalOutcome.B1_READ_FAILURE, "TIMEOUT"
    return None


def _apply_schema(
    operation_label: str, body: dict, state: _RunState, creds: B1CredentialRefs
) -> None:
    """Apply the operation-specific projection to the run state. Raises
    :class:`_SourceDrift` / :class:`_MalformedResponse` on contract failure."""

    if operation_label == OP_ACCOUNT_LIMITS:
        projection = parse_account_limits(body)
        state.usage_tier = projection.usage_tier
        state.relevant_grants = projection.relevant_grants
        return

    if operation_label == OP_API_KEYS:
        records = parse_api_keys(body)
        matches = [r for r in records if r.api_key_id == creds.api_key_id]
        if len(matches) == 0:
            state.current_key_match_state = CurrentKeyMatchState.ZERO_MATCH
            return
        if len(matches) > 1:
            state.current_key_match_state = CurrentKeyMatchState.MULTIPLE_MATCHES
            return
        matched = matches[0]
        unknown = sorted(s for s in matched.scopes if s not in RECOGNIZED_SCOPES)
        if unknown:
            raise _SourceDrift(
                f"matched current key carries unknown scope token(s) {','.join(unknown)}"
            )
        state.current_key_match_state = CurrentKeyMatchState.UNIQUE
        state.current_key_scopes = tuple(sorted(matched.scopes))
        state.current_key_restricted_subaccount_number = None
        if type(matched.subaccount) is int:
            state.current_key_restriction_state = (
                CurrentKeyRestrictionState.RESTRICTED_TO_EXACT_SUBACCOUNT
            )
            state.current_key_restricted_subaccount_number = matched.subaccount
        else:
            # absent or explicit null
            state.current_key_restriction_state = CurrentKeyRestrictionState.NOT_EXPOSED
        return

    if operation_label == OP_SUBACCOUNT_BALANCES:
        rows = parse_subaccount_balances(body)
        state.balance_rows = rows
        numbers = sorted({r.subaccount_number for r in rows})
        if REVIEWED_SUBACCOUNT_MIN not in numbers:
            raise _SourceDrift(
                "account-wide balances response omits mandatory primary subaccount 0"
            )
        state.balance_set = tuple(numbers)
        return

    if operation_label == OP_SUBACCOUNT_NETTING:
        rows = parse_subaccount_netting(body)
        state.netting_rows = rows
        numbers = sorted({r.subaccount_number for r in rows})
        if REVIEWED_SUBACCOUNT_MIN not in numbers:
            raise _SourceDrift(
                "account-wide netting response omits mandatory primary subaccount 0"
            )
        state.netting_set = tuple(numbers)
        return

    raise AssertionError(f"unknown operation label {operation_label!r}")  # pragma: no cover


def _interpret_api_keys(
    state: _RunState,
    source_record: TaskCurrentSourceRecord,
) -> Optional[Tuple[B1TerminalOutcome, str]]:
    """Decide, after ``/api_keys``, whether the run ends before the two
    account-wide surfaces (B1-KEY-001..004, B1-REQ-002)."""

    match_state = state.current_key_match_state
    if match_state in (
        CurrentKeyMatchState.ZERO_MATCH,
        CurrentKeyMatchState.MULTIPLE_MATCHES,
    ):
        return (
            B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED,
            "current key did not uniquely match exactly one returned api_key_id",
        )

    if match_state is not CurrentKeyMatchState.UNIQUE:  # pragma: no cover - guard
        return (
            B1TerminalOutcome.B1_CURRENT_KEY_NOT_UNIQUELY_MATCHED,
            "current key match state not resolved",
        )

    restriction = state.current_key_restriction_state
    if restriction is CurrentKeyRestrictionState.RESTRICTED_TO_EXACT_SUBACCOUNT:
        return (
            B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY,
            "current key is restricted to an exact subaccount",
        )

    if restriction is CurrentKeyRestrictionState.NOT_EXPOSED:
        semantics = source_record.api_keys_absent_subaccount_semantics
        if semantics == "UNRESTRICTED":
            state.current_key_restriction_state = CurrentKeyRestrictionState.UNRESTRICTED
            return None
        return (
            B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY,
            "current key restriction is NOT_EXPOSED by the task-current source",
        )

    if restriction is CurrentKeyRestrictionState.UNRESTRICTED:
        return None

    return (
        B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY,
        "current key restriction not proven unrestricted",
    )


def _reconcile_and_finish(
    state: _RunState,
    clock: Clock,
    global_deadline_ns: int,
    source_binding: SourceEvidenceBinding,
) -> B1Result:
    """Sections 11-14: identity-set reconciliation, account-wide proof, and
    the deterministic terminal theorem."""

    balance_set = set(state.balance_set)
    netting_set = set(state.netting_set)
    state.surfaces_agree = balance_set == netting_set

    if not state.surfaces_agree:
        # Preserve both sorted sets; never union/intersect (B1-ENUM-002).
        return _finish(
            state,
            B1TerminalOutcome.B1_SUBACCOUNT_ENUMERATION_DISAGREEMENT,
            clock,
            global_deadline_ns,
            source_binding=source_binding,
            detail="balances and netting subaccount identity sets differ",
        )

    account_wide = (
        state.current_key_match_state is CurrentKeyMatchState.UNIQUE
        and state.current_key_restriction_state
        is CurrentKeyRestrictionState.UNRESTRICTED
        and REVIEWED_SUBACCOUNT_MIN in balance_set
        and REVIEWED_SUBACCOUNT_MIN in netting_set
        and balance_set == netting_set
    )
    state.account_wide_enumeration_proven = account_wide

    if not account_wide:  # pragma: no cover - earlier guards make this unreachable
        return _finish(
            state,
            B1TerminalOutcome.B1_ACCOUNT_WIDE_ENUMERATION_NOT_PROVEN_WITH_CURRENT_KEY,
            clock,
            global_deadline_ns,
            source_binding=source_binding,
            detail="account-wide enumeration predicate not satisfied",
        )

    numbered = tuple(sorted(n for n in balance_set if n > 0))
    state.numbered_subaccounts = numbered
    if numbered:
        return _finish(
            state,
            B1TerminalOutcome.B1_EXISTING_NUMBERED_SUBACCOUNT_DISCOVERED,
            clock,
            global_deadline_ns,
            source_binding=source_binding,
            detail="one or more numbered subaccount identities exposed",
        )
    return _finish(
        state,
        B1TerminalOutcome.B1_PRIMARY_ONLY_OBSERVED,
        clock,
        global_deadline_ns,
        source_binding=source_binding,
        detail="only primary subaccount 0 exposed",
    )
