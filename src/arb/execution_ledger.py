"""Crash-safe, restart-safe local execution safety ledger.

This module implements the generic, venue-independent portion of
KALSHI_DEMO_PERSISTENT_LEDGER_AND_RESTART_RECOVERY_SPEC_03.  It owns two
separate SQLite durability domains: a deployment-bound authority database and
an append-only execution ledger.  It deliberately owns no network, credential,
signing, or venue capability.

The public API is intentionally explicit.  Normal opens never create files;
initialization is separate, authority is locked before its bound ledger, and a
ledger append is usable by its caller only after the authority tail has been
advanced and read back.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import re
import sqlite3
import unicodedata
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


AUTHORITY_STORE_FILENAME = "arb_execution_authority_v1.sqlite3"
AUTHORITY_SCHEMA_REVISION = 1
LEDGER_SCHEMA_REVISION = 1
EVENT_SCHEMA_REVISION = 1
ZERO_HASH = "0" * 64
PATH_IDENTITY_DOMAIN = b"ARB_PATH_IDENTITY_V1\x00"
EVENT_HASH_DOMAIN = b"ARB_LEDGER_EVENT_V1\x00"
PRELEDGER_HISTORY_MODE = "LEGACY_IMPORT_REQUIRED"
LOCK_MODEL = "AUTHORITY_THEN_LEDGER_SQLITE_EXCLUSIVE_V1"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ID_RE = re.compile(r"^evt_[0-9a-f]{32}$")
_LEGACY_EVENT_ID_RE = re.compile(r"^legacy_[0-9a-f]{64}$")
_WRITER_SESSION_ID_RE = re.compile(r"^ws_[0-9a-f]{32}$")
_RESTRICTED_SESSION_ID_RE = re.compile(r"^rs_[0-9a-f]{32}$")
_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"\.(?P<micro>\d{6})Z$"
)


class FailureCode(enum.StrEnum):
    AUTHORITY_STORE_MISSING = "AUTHORITY_STORE_MISSING"
    AUTHORITY_PATH_INSIDE_CANONICAL_REPOSITORY = "AUTHORITY_PATH_INSIDE_CANONICAL_REPOSITORY"
    AUTHORITY_STORAGE_OPEN_FAILURE = "AUTHORITY_STORAGE_OPEN_FAILURE"
    AUTHORITY_DURABILITY_CONFIGURATION_FAILURE = "AUTHORITY_DURABILITY_CONFIGURATION_FAILURE"
    AUTHORITY_SCHEMA_IDENTITY_MISMATCH = "AUTHORITY_SCHEMA_IDENTITY_MISMATCH"
    AUTHORITY_SCHEMA_UNSUPPORTED_NEWER = "AUTHORITY_SCHEMA_UNSUPPORTED_NEWER"
    AUTHORITY_SCHEMA_UNSUPPORTED_OLDER = "AUTHORITY_SCHEMA_UNSUPPORTED_OLDER"
    AUTHORITY_INTEGRITY_CHECK_FAILURE = "AUTHORITY_INTEGRITY_CHECK_FAILURE"
    AUTHORITY_IDENTITY_MISMATCH = "AUTHORITY_IDENTITY_MISMATCH"
    AUTHORITY_CONFLICT_DOMAIN_BINDING_MISSING = "AUTHORITY_CONFLICT_DOMAIN_BINDING_MISSING"
    AUTHORITY_CONFLICT_DOMAIN_ALREADY_BOUND = "AUTHORITY_CONFLICT_DOMAIN_ALREADY_BOUND"
    AUTHORITY_LEDGER_INITIALIZATION_PARTIAL_FAILURE = "AUTHORITY_LEDGER_INITIALIZATION_PARTIAL_FAILURE"
    AUTHORITY_ANCHOR_COMMIT_FAILURE = "AUTHORITY_ANCHOR_COMMIT_FAILURE"
    AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN = "AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN"
    AUTHORITY_ANCHOR_CATCHUP_FAILURE = "AUTHORITY_ANCHOR_CATCHUP_FAILURE"
    AUTHORITY_AHEAD_OF_LEDGER_ROLLBACK_OR_REPLACEMENT = "AUTHORITY_AHEAD_OF_LEDGER_ROLLBACK_OR_REPLACEMENT"
    AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH = "AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH"
    AUTHORITY_ALTERNATE_NAMESPACE_REJECTED = "AUTHORITY_ALTERNATE_NAMESPACE_REJECTED"
    LEDGER_FILE_MISSING = "LEDGER_FILE_MISSING"
    LEDGER_ALREADY_EXISTS = "LEDGER_ALREADY_EXISTS"
    LEDGER_PATH_INSIDE_CANONICAL_REPOSITORY = "LEDGER_PATH_INSIDE_CANONICAL_REPOSITORY"
    LEDGER_STORAGE_OPEN_FAILURE = "LEDGER_STORAGE_OPEN_FAILURE"
    LEDGER_DURABILITY_CONFIGURATION_FAILURE = "LEDGER_DURABILITY_CONFIGURATION_FAILURE"
    LEDGER_SCHEMA_IDENTITY_MISMATCH = "LEDGER_SCHEMA_IDENTITY_MISMATCH"
    LEDGER_SCHEMA_UNSUPPORTED_NEWER = "LEDGER_SCHEMA_UNSUPPORTED_NEWER"
    LEDGER_SCHEMA_UNSUPPORTED_OLDER = "LEDGER_SCHEMA_UNSUPPORTED_OLDER"
    LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE = "LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE"
    LEDGER_INTEGRITY_CHECK_FAILURE = "LEDGER_INTEGRITY_CHECK_FAILURE"
    LEDGER_SEQUENCE_INTEGRITY_FAILURE = "LEDGER_SEQUENCE_INTEGRITY_FAILURE"
    LEDGER_HASH_CHAIN_FAILURE = "LEDGER_HASH_CHAIN_FAILURE"
    LEDGER_CANONICAL_ENCODING_FAILURE = "LEDGER_CANONICAL_ENCODING_FAILURE"
    LEDGER_DECIMAL_CANONICALIZATION_FAILURE = "LEDGER_DECIMAL_CANONICALIZATION_FAILURE"
    NONCANONICAL_UNICODE = "NONCANONICAL_UNICODE"
    LEDGER_INSTANCE_ID_MISMATCH = "LEDGER_INSTANCE_ID_MISMATCH"
    LEDGER_ENVIRONMENT_MISMATCH = "LEDGER_ENVIRONMENT_MISMATCH"
    LEDGER_CONFLICT_DOMAIN_MISMATCH = "LEDGER_CONFLICT_DOMAIN_MISMATCH"
    LEDGER_AUTHORITY_BINDING_MISMATCH = "LEDGER_AUTHORITY_BINDING_MISMATCH"
    LEDGER_CONCURRENT_WRITER = "LEDGER_CONCURRENT_WRITER"
    LEDGER_COMMIT_FAILURE = "LEDGER_COMMIT_FAILURE"
    LEDGER_COMMIT_RESULT_UNKNOWN = "LEDGER_COMMIT_RESULT_UNKNOWN"
    PRELEDGER_EMPTY_ASSERTION_UNSUPPORTED = "PRELEDGER_EMPTY_ASSERTION_UNSUPPORTED"
    EVENT_ID_CONTENT_CONFLICT = "EVENT_ID_CONTENT_CONFLICT"
    EVENT_REQUIRED_PARENT_MISSING = "EVENT_REQUIRED_PARENT_MISSING"
    WRITER_SESSION_REFERENCE_INVALID = "WRITER_SESSION_REFERENCE_INVALID"
    REQUEST_PARENT_INVALID = "REQUEST_PARENT_INVALID"
    ORDER_IDENTITY_BINDING_CONFLICT = "ORDER_IDENTITY_BINDING_CONFLICT"
    DUPLICATE_FILL_CONFLICT = "DUPLICATE_FILL_CONFLICT"
    LEGACY_INCIDENT_EVIDENCE_IDENTITY_MISMATCH = "LEGACY_INCIDENT_EVIDENCE_IDENTITY_MISMATCH"
    LEGACY_INCIDENT_CONTENT_MISMATCH = "LEGACY_INCIDENT_CONTENT_MISMATCH"
    LEGACY_INCIDENT_IMPORT_CONFLICT = "LEGACY_INCIDENT_IMPORT_CONFLICT"
    LEGACY_INCIDENT_IMPORT_INCOMPLETE = "LEGACY_INCIDENT_IMPORT_INCOMPLETE"
    LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED = "LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED"
    SECRET_FIELD_PROHIBITED = "SECRET_FIELD_PROHIBITED"
    SECRET_PATTERN_PROHIBITED = "SECRET_PATTERN_PROHIBITED"
    EVENT_SCHEMA_CONTRACT_VIOLATION = "EVENT_SCHEMA_CONTRACT_VIOLATION"
    EVENT_REQUIRED_REFERENCE_INVALID = "EVENT_REQUIRED_REFERENCE_INVALID"
    RESTRICTED_SESSION_EVENT_NOT_PERMITTED = "RESTRICTED_SESSION_EVENT_NOT_PERMITTED"
    RESTRICTED_SESSION_STATE_CONFLICT = "RESTRICTED_SESSION_STATE_CONFLICT"
    RISK_STATE_TRANSITION_INVALID = "RISK_STATE_TRANSITION_INVALID"
    EMERGENCY_ACTION_DUPLICATE_CONFLICT = "EMERGENCY_ACTION_DUPLICATE_CONFLICT"
    CANCEL_ATTEMPT_PREDECESSOR_INVALID = "CANCEL_ATTEMPT_PREDECESSOR_INVALID"
    CANCEL_RESULT_EVIDENCE_CONFLICT = "CANCEL_RESULT_EVIDENCE_CONFLICT"
    CANCEL_RESULT_REVISION_CONFLICT = "CANCEL_RESULT_REVISION_CONFLICT"
    RELEASE_PREDICATE_FAILED = "RELEASE_PREDICATE_FAILED"
    RELEASE_PREDICATE_CHANGED = "RELEASE_PREDICATE_CHANGED"
    NORMAL_WRITER_ACQUISITION_REJECTED = "NORMAL_WRITER_ACQUISITION_REJECTED"
    CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED = "CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED"
    CURRENT_PROCESS_RELEASE_COMPLETION_INVALID = "CURRENT_PROCESS_RELEASE_COMPLETION_INVALID"
    CURRENT_PROCESS_RELEASE_COMPLETION_PROCESS_MISMATCH = "CURRENT_PROCESS_RELEASE_COMPLETION_PROCESS_MISMATCH"
    CURRENT_PROCESS_RELEASE_COMPLETION_STALE = "CURRENT_PROCESS_RELEASE_COMPLETION_STALE"
    CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED = "CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED"


class RestartClassification(enum.StrEnum):
    SAFE_NO_WRITE_CAPABILITY = "RESTART_SAFE_NO_WRITE_CAPABILITY"
    UNRESOLVED_WRITE_HELD = "RESTART_UNRESOLVED_WRITE_HELD"
    AUTHORITY_INTEGRITY_FAILURE = "RESTART_AUTHORITY_INTEGRITY_FAILURE"
    AUTHORITY_LEDGER_ROLLBACK_FAILURE = "RESTART_AUTHORITY_LEDGER_ROLLBACK_FAILURE"
    LEDGER_INTEGRITY_FAILURE = "RESTART_LEDGER_INTEGRITY_FAILURE"
    SCHEMA_UNSUPPORTED = "RESTART_SCHEMA_UNSUPPORTED"
    CONCURRENT_WRITER_BLOCKED = "RESTART_CONCURRENT_WRITER_BLOCKED"
    LEGACY_HISTORY_INCOMPLETE = "RESTART_LEGACY_HISTORY_INCOMPLETE"
    LEDGER_IDENTITY_FAILURE = "RESTART_LEDGER_IDENTITY_FAILURE"
    STORAGE_UNAVAILABLE = "RESTART_STORAGE_UNAVAILABLE"


class AcquisitionMode(enum.StrEnum):
    NORMAL_WRITER = "NORMAL_WRITER"
    LEGACY_IMPORT_ONLY = "LEGACY_IMPORT_ONLY"
    EMERGENCY_CONTROL_ONLY = "EMERGENCY_CONTROL_ONLY"
    RELEASE_ONLY = "RELEASE_ONLY"


class EventType(enum.StrEnum):
    LEDGER_INITIALIZED = "LEDGER_INITIALIZED"
    WRITER_SESSION_STARTED = "WRITER_SESSION_STARTED"
    WRITER_SESSION_ABANDONED = "WRITER_SESSION_ABANDONED"
    EXECUTION_INTENT_RECORDED = "EXECUTION_INTENT_RECORDED"
    REQUEST_PREPARED = "REQUEST_PREPARED"
    WRITE_SEND_BOUNDARY_ENTERED = "WRITE_SEND_BOUNDARY_ENTERED"
    READ_SEND_BOUNDARY_ENTERED = "READ_SEND_BOUNDARY_ENTERED"
    HTTP_RESPONSE_CLASSIFIED = "HTTP_RESPONSE_CLASSIFIED"
    TRANSPORT_UNKNOWN_AFTER_SEND = "TRANSPORT_UNKNOWN_AFTER_SEND"
    ORDER_IDENTITY_BOUND = "ORDER_IDENTITY_BOUND"
    ORDER_OBSERVED = "ORDER_OBSERVED"
    FILL_OBSERVED = "FILL_OBSERVED"
    RECONCILIATION_RECORDED = "RECONCILIATION_RECORDED"
    EXECUTION_HALTED = "EXECUTION_HALTED"
    EXECUTION_TERMINAL = "EXECUTION_TERMINAL"
    WRITER_PROOF_HELD = "WRITER_PROOF_HELD"
    WRITER_PROOF_RELEASED = "WRITER_PROOF_RELEASED"
    WRITER_SESSION_ENDED = "WRITER_SESSION_ENDED"
    LEGACY_INCIDENT_IMPORTED = "LEGACY_INCIDENT_IMPORTED"
    RISK_CONTROL_STATE_CHANGED = "RISK_CONTROL_STATE_CHANGED"
    EMERGENCY_ACTION_OPENED = "EMERGENCY_ACTION_OPENED"
    CANCEL_INTENT_RECORDED = "CANCEL_INTENT_RECORDED"
    CANCEL_SEND_BOUNDARY_ENTERED = "CANCEL_SEND_BOUNDARY_ENTERED"
    CANCEL_RESULT_RECORDED = "CANCEL_RESULT_RECORDED"
    RISK_RELEASE_RECORDED = "RISK_RELEASE_RECORDED"
    RESTRICTED_SESSION_STARTED = "RESTRICTED_SESSION_STARTED"
    RESTRICTED_SESSION_ENDED = "RESTRICTED_SESSION_ENDED"
    RESTRICTED_SESSION_ABANDONED = "RESTRICTED_SESSION_ABANDONED"


class AuthorityLedgerRelation(enum.StrEnum):
    EQUAL = "AUTHORITY_EQUAL_TO_LEDGER"
    LEDGER_AHEAD = "LEDGER_AHEAD_OF_AUTHORITY"


class AppendStatus(enum.StrEnum):
    APPENDED_AND_ANCHORED = "APPENDED_AND_ANCHORED"
    IDEMPOTENT_DUPLICATE = "IDEMPOTENT_DUPLICATE"


RISK_CONTROL_STATES = frozenset({
    "BOOT_HOLD", "HALTED", "EMERGENCY_CANCELING", "RECONCILING",
    "QUIESCENT_HELD", "SAFE_HELD", "WRITER_ELIGIBLE",
})
RISK_CONTROL_TRANSITIONS = MappingProxyType({
    ("BOOT_HOLD", "HALTED"): "REPLAY_OR_CURRENT_HARD_VIOLATION",
    ("BOOT_HOLD", "QUIESCENT_HELD"): "REPLAY_UNCERTAINTY_NO_CANCEL_TARGET",
    ("BOOT_HOLD", "SAFE_HELD"): "REPLAY_ALL_SAFETY_PREDICATES_PASS",
    ("HALTED", "EMERGENCY_CANCELING"): "EXACT_CANCEL_TARGET_SET_OPENED",
    ("HALTED", "RECONCILING"): "AUTHORITATIVE_TRUTH_REQUIRED",
    ("HALTED", "QUIESCENT_HELD"): "NO_CANCEL_TARGET_UNCERTAINTY_REMAINS",
    ("EMERGENCY_CANCELING", "RECONCILING"): "CANCEL_WAVE_ENDED_OR_AMBIGUOUS",
    ("RECONCILING", "EMERGENCY_CANCELING"): "RECONCILIATION_REVEALED_EXACT_ACTIVE_TARGET",
    ("RECONCILING", "QUIESCENT_HELD"): "NO_CANCEL_TARGET_RELEASE_PREDICATE_FALSE_OR_UNKNOWN",
    ("RECONCILING", "SAFE_HELD"): "ALL_RELEASE_PREDICATES_EXCEPT_EXPLICIT_RELEASE_PASS",
    ("QUIESCENT_HELD", "RECONCILING"): "NEW_RECONCILIATION_REQUIRED",
    ("QUIESCENT_HELD", "SAFE_HELD"): "UNCERTAINTY_RESOLVED_ALL_RELEASE_PREDICATES_PASS",
    ("SAFE_HELD", "WRITER_ELIGIBLE"): "DURABLE_RELEASE_COMPLETED",
    ("WRITER_ELIGIBLE", "HALTED"): "HARD_SAFETY_VIOLATION",
})

_NEW_EVENT_DOMAINS = MappingProxyType({
    EventType.RISK_CONTROL_STATE_CHANGED: b"ARB_RISK_CONTROL_STATE_CHANGED_V1\x00",
    EventType.EMERGENCY_ACTION_OPENED: b"ARB_EMERGENCY_ACTION_OPENED_V1\x00",
    EventType.CANCEL_INTENT_RECORDED: b"ARB_CANCEL_INTENT_RECORDED_V1\x00",
    EventType.CANCEL_SEND_BOUNDARY_ENTERED: b"ARB_CANCEL_SEND_BOUNDARY_ENTERED_V1\x00",
    EventType.CANCEL_RESULT_RECORDED: b"ARB_CANCEL_RESULT_RECORDED_V1\x00",
    EventType.RISK_RELEASE_RECORDED: b"ARB_RISK_RELEASE_RECORDED_V1\x00",
    EventType.RESTRICTED_SESSION_STARTED: b"ARB_RESTRICTED_SESSION_STARTED_V1\x00",
    EventType.RESTRICTED_SESSION_ENDED: b"ARB_RESTRICTED_SESSION_ENDED_V1\x00",
    EventType.RESTRICTED_SESSION_ABANDONED: b"ARB_RESTRICTED_SESSION_ABANDONED_V1\x00",
})


def _new_event_logical_identity(event_type: EventType, payload: Mapping[str, object]) -> Mapping[str, object]:
    if event_type is EventType.RISK_CONTROL_STATE_CHANGED:
        return {"risk_state_epoch_after": payload.get("risk_state_epoch_after")}
    if event_type is EventType.EMERGENCY_ACTION_OPENED:
        return {"emergency_action_id": payload.get("emergency_action_id")}
    if event_type is EventType.CANCEL_INTENT_RECORDED:
        return {"cancel_attempt_id": payload.get("cancel_attempt_id"), "stage": "INTENT"}
    if event_type is EventType.CANCEL_SEND_BOUNDARY_ENTERED:
        return {"cancel_attempt_id": payload.get("cancel_attempt_id"), "stage": "SEND_BOUNDARY"}
    if event_type is EventType.CANCEL_RESULT_RECORDED:
        return {"cancel_attempt_id": payload.get("cancel_attempt_id"), "result_revision": payload.get("result_revision")}
    if event_type is EventType.RISK_RELEASE_RECORDED:
        return {"release_id": payload.get("release_id")}
    if event_type is EventType.RESTRICTED_SESSION_STARTED:
        return {"restricted_session_id": payload.get("restricted_session_id"), "stage": "START"}
    if event_type is EventType.RESTRICTED_SESSION_ENDED:
        return {"restricted_session_id": payload.get("restricted_session_id"), "stage": "END"}
    if event_type is EventType.RESTRICTED_SESSION_ABANDONED:
        return {"abandoned_restricted_session_id": payload.get("abandoned_restricted_session_id"), "stage": "ABANDON"}
    raise LedgerError(FailureCode.LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE)


def deterministic_event_id(event_type: EventType, payload: Mapping[str, object]) -> str:
    """Return the Spec-03 deterministic ID for one new logical event."""
    if event_type not in _NEW_EVENT_DOMAINS:
        raise LedgerError(FailureCode.LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE)
    identity = _new_event_logical_identity(event_type, payload)
    return "evt_" + sha256_hex(_NEW_EVENT_DOMAINS[event_type] + canonical_json_bytes(identity))[:32]


@dataclass(frozen=True, slots=True)
class CrashFaultExpectation:
    ledger_commit_outcome: str
    authority_commit_outcome: str
    transport_invocation_count: int | None
    restart_interpretation: str
    unknown_write: bool | None
    writer_proof_state: str
    automatic_resend: bool = False


CRASH_FAULT_MATRIX = MappingProxyType({
    "A": CrashFaultExpectation("NONE", "UNCHANGED", 0, "PRIOR_STATE_CONTROLS", False, "PRIOR"),
    "B": CrashFaultExpectation("PRE_BOUNDARY_SUCCESS", "PRE_BOUNDARY_SUCCESS", 0, "PREPARED_NO_BOUNDARY", False, "PRIOR_OR_HELD"),
    "C": CrashFaultExpectation("BOUNDARY_SUCCESS", "BOUNDARY_SUCCESS", 0, "WRITE_MAY_HAVE_BEEN_SENT", True, "HELD"),
    "D": CrashFaultExpectation("BOUNDARY_SUCCESS", "BOUNDARY_SUCCESS", 1, "WRITE_RESULT_UNKNOWN", True, "HELD"),
    "E": CrashFaultExpectation("RESULT_ABSENT_OR_LEDGER_ONLY", "BOUNDARY_TRUSTED", 1, "UNRESOLVED_UNTIL_VALIDATED_CLOSURE", True, "HELD"),
    "F": CrashFaultExpectation("RESULT_SUCCESS", "RESULT_SUCCESS", 1, "EXACT_CLOSURE_CLASS_CONTROLS", None, "REPLAY_CONTROLS"),
    "G": CrashFaultExpectation("PRIOR_OR_COMPLETE_BATCH", "PRIOR_OR_NEW_TAIL", None, "REPLAY_COMPLETE_LEDGER_AND_TWO_STORE_RELATION", None, "HELD_WHILE_UNRESOLVED"),
    "H": CrashFaultExpectation("END_ABSENT_LEDGER_ONLY_OR_ANCHORED", "PRIOR_OR_END_TAIL", None, "SESSION_END_DOES_NOT_CHANGE_WRITE_TRUTH", None, "REPLAY_CONTROLS"),
    "I": CrashFaultExpectation("BOUNDARY_FAILURE", "UNCHANGED", 0, "NO_COMMITTED_BOUNDARY", False, "PRIOR"),
    "J": CrashFaultExpectation("BOUNDARY_SUCCESS", "OLD_TRUSTED_TAIL", 0, "LEDGER_AHEAD_CATCH_FORWARD_ONLY", True, "HELD"),
    "K": CrashFaultExpectation("BOUNDARY_SUCCESS", "DEFINITE_FAILURE", 0, "LEDGER_AHEAD_REOPEN_REQUIRED", True, "HELD"),
    "L": CrashFaultExpectation("BOUNDARY_SUCCESS", "UNKNOWN", 0, "CLOSE_REOPEN_EQUAL_OR_LEDGER_AHEAD", True, "HELD"),
    "M": CrashFaultExpectation("BOUNDARY_SUCCESS", "BOUNDARY_SUCCESS", 0, "WRITE_MAY_HAVE_BEEN_SENT", True, "HELD"),
    "N": CrashFaultExpectation("BOUNDARY_SUCCESS", "BOUNDARY_SUCCESS", 1, "WRITE_RESULT_UNKNOWN", True, "HELD"),
    "O": CrashFaultExpectation("LEDGER_BEHIND", "AUTHORITY_AHEAD", 0, "RESTART_AUTHORITY_LEDGER_ROLLBACK_FAILURE", None, "UNAVAILABLE_OR_HELD"),
    "P": CrashFaultExpectation("UNTRUSTED", "TRUSTED_PAIR_PRESENT", 0, "RESTART_LEDGER_INTEGRITY_FAILURE", None, "UNAVAILABLE_OR_HELD"),
    "Q": CrashFaultExpectation("UNAVAILABLE", "MISSING_OR_CORRUPT", 0, "RESTART_AUTHORITY_INTEGRITY_FAILURE", None, "UNAVAILABLE_OR_HELD"),
    "R": CrashFaultExpectation("NON_AUTHORITATIVE_LEDGER", "BINDS_LEDGER_A", 0, "LEDGER_B_WRITER_AUTHORITY_REJECTED", False, "UNAVAILABLE"),
})


class LedgerError(RuntimeError):
    """Secret-safe deterministic ledger failure."""

    def __init__(self, code: FailureCode, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code.value if detail is None else f"{code.value}:{detail}")


class CommitResultUnknown(LedgerError):
    """Fault-injection/adapter signal that a commit result is indeterminate."""


Clock = Callable[[], datetime]
UuidFactory = Callable[[], uuid.UUID]
FaultHook = Callable[[str], None]
HistoryValidator = Callable[[tuple["LedgerEvent", ...]], None]


def _noop_fault_hook(stage: str) -> None:
    del stage


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_timestamp(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def validate_canonical_timestamp(value: object) -> str:
    if type(value) is not str or _TIMESTAMP_RE.fullmatch(value) is None:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE) from exc
    if canonical_timestamp(parsed) != value:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
    return value


def _canonical_decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise LedgerError(FailureCode.LEDGER_DECIMAL_CANONICALIZATION_FAILURE)
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("-0") and Decimal(text).is_zero():
        return "0"
    return text


_SECRET_KEYS = frozenset(
    {
        "authorization", "authorization_header", "auth_header", "headers",
        "raw_headers", "signature", "signature_hash", "signature_fingerprint",
        "private_key", "private_key_pem", "api_secret", "secret", "password",
        "session_token", "bearer_token", "access_token", "wallet_secret",
    }
)
_SECRET_PATTERNS = (
    "-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----", "Authorization:", "Bearer ",
    "KALSHI-ACCESS-SIGNATURE:",
)
_ALLOWED_SUFFIX_KEYS = frozenset({"credential_reference_name", "credential_reference_class"})


def assert_secret_safe(value: object) -> None:
    """Recursively enforce the specification's key and content denylist."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            if type(key) is not str:
                raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
            lowered = unicodedata.normalize("NFC", key).lower()
            if lowered in _SECRET_KEYS or (
                (lowered.endswith("_secret") or lowered.endswith("_token"))
                and lowered not in _ALLOWED_SUFFIX_KEYS
            ):
                raise LedgerError(FailureCode.SECRET_FIELD_PROHIBITED)
            assert_secret_safe(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            assert_secret_safe(child)
    elif type(value) is str:
        if any(pattern in value for pattern in _SECRET_PATTERNS):
            raise LedgerError(FailureCode.SECRET_PATTERN_PROHIBITED)


def _canonical_value(value: object, *, allow_decimal_tag: bool = False) -> object:
    if value is None or type(value) in (bool, str):
        if type(value) is str and unicodedata.normalize("NFC", value) != value:
            raise LedgerError(FailureCode.NONCANONICAL_UNICODE)
        return value
    if type(value) is int:
        if value < -(2**63) or value > 2**63 - 1:
            raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
        return value
    if type(value) is Decimal:
        return {"$decimal": _canonical_decimal_text(value)}
    if type(value) is list:
        return [_canonical_value(item, allow_decimal_tag=allow_decimal_tag) for item in value]
    if type(value) is dict or isinstance(value, Mapping) and allow_decimal_tag:
        result: dict[str, object] = {}
        for key, child in value.items():
            if type(key) is not str:
                raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
            if unicodedata.normalize("NFC", key) != key:
                raise LedgerError(FailureCode.NONCANONICAL_UNICODE)
            if key.startswith("$"):
                if not (allow_decimal_tag and key == "$decimal" and len(value) == 1):
                    raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
            result[key] = _canonical_value(child, allow_decimal_tag=allow_decimal_tag)
        return result
    raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)


def canonical_json_bytes(value: object) -> bytes:
    assert_secret_safe(value)
    canonical = _canonical_value(value)
    try:
        return json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE) from exc


def canonical_json_text(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _canonical_stored_json_bytes(value: object) -> bytes:
    """Serialize an already-parsed authoritative value containing tags."""
    assert_secret_safe(value)
    canonical = _canonical_value(value, allow_decimal_tag=True)
    _validate_decimal_tags(canonical)
    return json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _duplicate_rejecting_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
        result[key] = value
    return result


def parse_canonical_json(raw: str | bytes) -> object:
    try:
        text = raw.decode("utf-8") if type(raw) is bytes else raw
        if type(text) is not str:
            raise TypeError
        value = json.loads(
            text, object_pairs_hook=_duplicate_rejecting_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(
                LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
            ),
            parse_constant=lambda _: (_ for _ in ()).throw(
                LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
            ),
        )
    except LedgerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE) from exc
    canonical = _canonical_value(value, allow_decimal_tag=True)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    if encoded != text:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
    _validate_decimal_tags(canonical)
    assert_secret_safe(canonical)
    return canonical


def _validate_decimal_tags(value: object) -> None:
    if type(value) is dict:
        if "$decimal" in value:
            if set(value) != {"$decimal"} or type(value["$decimal"]) is not str:
                raise LedgerError(FailureCode.LEDGER_DECIMAL_CANONICALIZATION_FAILURE)
            text = value["$decimal"]
            try:
                decimal_value = Decimal(text)
            except Exception as exc:
                raise LedgerError(FailureCode.LEDGER_DECIMAL_CANONICALIZATION_FAILURE) from exc
            if _canonical_decimal_text(decimal_value) != text:
                raise LedgerError(FailureCode.LEDGER_DECIMAL_CANONICALIZATION_FAILURE)
        for child in value.values():
            _validate_decimal_tags(child)
    elif type(value) is list:
        for child in value:
            _validate_decimal_tags(child)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_canonical_text(value: object, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and value == ""):
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
    if unicodedata.normalize("NFC", value) != value:
        raise LedgerError(FailureCode.NONCANONICAL_UNICODE)
    return value


def _uuid4_text(value: object) -> str:
    return _uuid4_text_for(value, FailureCode.LEDGER_INSTANCE_ID_MISMATCH)


def _uuid4_text_for(value: object, code: FailureCode) -> str:
    if type(value) is not str:
        raise LedgerError(code)
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise LedgerError(code) from exc
    if parsed.version != 4 or str(parsed) != value or value.lower() != value:
        raise LedgerError(code)
    return value


def _resolved_candidate(path: str | os.PathLike[str], *, must_exist: bool) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise LedgerError(FailureCode.LEDGER_STORAGE_OPEN_FAILURE)
    if must_exist:
        return candidate.resolve(strict=True)
    parent = candidate.parent.resolve(strict=True)
    return parent / candidate.name


def path_identity(path: str | os.PathLike[str], *, must_exist: bool = True) -> tuple[Path, str, str]:
    resolved = _resolved_candidate(path, must_exist=must_exist)
    normalized = os.path.normcase(os.path.normpath(str(resolved)))
    return resolved, normalized, sha256_hex(PATH_IDENTITY_DOMAIN + normalized.encode("utf-8"))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_link_or_junction(path: Path, code: FailureCode) -> None:
    try:
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise LedgerError(code)
    except OSError as exc:
        raise LedgerError(code) from exc


@dataclass(frozen=True, slots=True)
class AuthorityNamespaceBinding:
    authority_namespace_id: str
    authority_namespace_root: Path
    authority_store_resolved_path: Path
    authority_store_path_identity_sha256: str
    authority_schema_revision: int = AUTHORITY_SCHEMA_REVISION

    @classmethod
    def bind(
        cls,
        *,
        authority_namespace_id: str,
        authority_namespace_root: str | os.PathLike[str],
        canonical_repository_root: str | os.PathLike[str],
    ) -> "AuthorityNamespaceBinding":
        namespace_id = _require_canonical_text(authority_namespace_id)
        if not isinstance(authority_namespace_root, (str, os.PathLike)) or not Path(authority_namespace_root).is_absolute():
            raise LedgerError(FailureCode.AUTHORITY_STORAGE_OPEN_FAILURE)
        root = Path(authority_namespace_root)
        _reject_link_or_junction(root, FailureCode.AUTHORITY_IDENTITY_MISMATCH)
        resolved_root = root.resolve(strict=True)
        repository_root = Path(canonical_repository_root).resolve(strict=True)
        if _is_within(resolved_root, repository_root):
            raise LedgerError(FailureCode.AUTHORITY_PATH_INSIDE_CANONICAL_REPOSITORY)
        store = resolved_root / AUTHORITY_STORE_FILENAME
        _, _, identity = path_identity(store, must_exist=store.exists())
        return cls(namespace_id, resolved_root, store, identity)


@dataclass(frozen=True, slots=True)
class AuthorityMeta:
    authority_instance_id: str
    authority_schema_revision: int
    authority_namespace_id: str
    authority_store_resolved_path: str
    authority_store_path_identity_sha256: str
    created_at_utc: str


@dataclass(frozen=True, slots=True)
class AuthorityRow:
    conflict_domain_ref: str
    environment_classification: str
    ledger_instance_id: str
    ledger_resolved_path: str
    ledger_path_identity_sha256: str
    trusted_sequence: int
    trusted_event_hash: str
    updated_at_utc: str


@dataclass(frozen=True, slots=True)
class LedgerMeta:
    ledger_instance_id: str
    ledger_schema_revision: int
    created_at_utc: str
    environment_classification: str
    conflict_domain_ref: str
    preledger_history_mode: str
    authority_instance_id: str
    authority_namespace_id: str
    authority_store_path_identity_sha256: str
    ledger_path_identity_sha256: str


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    sequence: int
    event_id: str
    ledger_instance_id: str
    event_type: EventType
    event_schema_revision: int
    writer_session_id: str | None
    incident_id: str | None
    execution_attempt_id: str | None
    recorded_at_utc: str
    payload: Mapping[str, object]
    payload_json: str
    payload_sha256: str
    previous_event_hash: str
    event_hash: str


@dataclass(frozen=True, slots=True)
class EventInput:
    event_type: EventType
    payload: Mapping[str, object]
    writer_session_id: str | None = None
    incident_id: str | None = None
    execution_attempt_id: str | None = None
    event_id: str | None = None
    recorded_at_utc: str | None = None


@dataclass(frozen=True, slots=True)
class AppendResult:
    status: AppendStatus
    first_sequence: int
    last_sequence: int
    terminal_event_hash: str
    events: tuple[LedgerEvent, ...]


@dataclass(frozen=True, slots=True)
class SafetyProjection:
    authority_schema_revision: int
    authority_instance_id: str
    authority_namespace_id: str
    authority_store_path_identity_sha256: str
    trusted_sequence: int
    trusted_event_hash: str
    ledger_instance_id: str
    ledger_schema_revision: int
    ledger_path_identity_sha256: str
    environment_classification: str
    conflict_domain_ref: str
    history_completeness: str
    last_sequence: int
    terminal_event_hash: str
    writer_sessions: tuple[str, ...]
    active_writer_session_id: str | None
    abnormal_prior_session_ids: tuple[str, ...]
    incident_ids: tuple[str, ...]
    execution_attempt_ids: tuple[str, ...]
    prepared_requests: Mapping[str, Mapping[str, object]]
    write_send_boundaries: Mapping[str, Mapping[str, object]]
    write_closure_by_request_id: Mapping[str, str]
    unresolved_write_request_ids: tuple[str, ...]
    client_order_to_venue_order: Mapping[str, str]
    order_observation_history: Mapping[str, tuple[Mapping[str, object], ...]]
    canonical_fills_by_fill_id: Mapping[str, Mapping[str, object]]
    fill_conflicts: tuple[str, ...]
    reconciliation_disposition_by_incident: Mapping[str, str]
    legacy_incident_state_by_incident: Mapping[str, Mapping[str, object]]
    writer_proof_state_by_proof_id: Mapping[str, str]
    writer_proof_release_eligible_by_proof_id: Mapping[str, bool]
    protected_unresolved_legacy_write_count: int
    restart_classification: RestartClassification
    last_writer_session_id: str | None
    restricted_sessions: tuple[str, ...]
    restricted_session_modes: Mapping[str, AcquisitionMode]
    active_restricted_session_id: str | None
    abnormal_restricted_session_ids: tuple[str, ...]
    risk_control_state: str
    risk_state_epoch: int
    active_risk_config_sha256: str | None
    emergency_actions_by_id: Mapping[str, Mapping[str, object]]
    cancel_attempts_by_id: Mapping[str, Mapping[str, object]]
    cancel_send_may_have_been_sent_by_attempt: Mapping[str, bool]
    cancel_result_revision_by_attempt: Mapping[str, int]
    release_records_by_id: Mapping[str, Mapping[str, object]]


def _sqlite_uri(path: Path, mode: str) -> str:
    encoded = urllib.parse.quote(str(path).replace("\\", "/"), safe="/:")
    return f"file:{encoded}?mode={mode}"


def _connect_existing(path: Path, *, authority: bool) -> sqlite3.Connection:
    if not path.exists():
        raise LedgerError(FailureCode.AUTHORITY_STORE_MISSING if authority else FailureCode.LEDGER_FILE_MISSING)
    _reject_link_or_junction(path, FailureCode.AUTHORITY_IDENTITY_MISMATCH if authority else FailureCode.LEDGER_INSTANCE_ID_MISMATCH)
    try:
        connection = sqlite3.connect(_sqlite_uri(path, "rw"), uri=True, timeout=0.0, isolation_level=None)
    except sqlite3.Error as exc:
        raise LedgerError(FailureCode.AUTHORITY_STORAGE_OPEN_FAILURE if authority else FailureCode.LEDGER_STORAGE_OPEN_FAILURE) from exc
    _configure_connection(connection, initialize=False, authority=authority)
    return connection


def _connect_new(path: Path, *, authority: bool) -> sqlite3.Connection:
    if path.exists():
        raise LedgerError(FailureCode.AUTHORITY_IDENTITY_MISMATCH if authority else FailureCode.LEDGER_ALREADY_EXISTS)
    try:
        connection = sqlite3.connect(_sqlite_uri(path, "rwc"), uri=True, timeout=0.0, isolation_level=None)
    except sqlite3.Error as exc:
        raise LedgerError(FailureCode.AUTHORITY_STORAGE_OPEN_FAILURE if authority else FailureCode.LEDGER_STORAGE_OPEN_FAILURE) from exc
    _configure_connection(connection, initialize=True, authority=authority)
    return connection


def _pragma_scalar(connection: sqlite3.Connection, statement: str) -> object:
    row = connection.execute(statement).fetchone()
    return None if row is None else row[0]


def _configure_connection(connection: sqlite3.Connection, *, initialize: bool, authority: bool) -> None:
    failure = FailureCode.AUTHORITY_DURABILITY_CONFIGURATION_FAILURE if authority else FailureCode.LEDGER_DURABILITY_CONFIGURATION_FAILURE
    try:
        if initialize:
            mode = str(_pragma_scalar(connection, "PRAGMA journal_mode=DELETE")).lower()
        else:
            mode = str(_pragma_scalar(connection, "PRAGMA journal_mode")).lower()
        connection.execute("PRAGMA synchronous=EXTRA")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=0")
        locking = str(_pragma_scalar(connection, "PRAGMA locking_mode=EXCLUSIVE")).lower()
        observed = (
            mode,
            _pragma_scalar(connection, "PRAGMA synchronous"),
            _pragma_scalar(connection, "PRAGMA foreign_keys"),
            _pragma_scalar(connection, "PRAGMA busy_timeout"),
            locking,
        )
        if observed != ("delete", 3, 1, 0, "exclusive"):
            raise LedgerError(failure)
    except LedgerError:
        connection.close()
        raise
    except sqlite3.Error as exc:
        connection.close()
        if getattr(exc, "sqlite_errorcode", None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise LedgerError(FailureCode.LEDGER_CONCURRENT_WRITER) from exc
        if getattr(exc, "sqlite_errorcode", None) in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
            raise LedgerError(
                FailureCode.AUTHORITY_INTEGRITY_CHECK_FAILURE
                if authority else FailureCode.LEDGER_INTEGRITY_CHECK_FAILURE
            ) from exc
        raise LedgerError(failure) from exc


_AUTHORITY_SCHEMA = """
CREATE TABLE authority_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    authority_instance_id TEXT NOT NULL UNIQUE,
    authority_schema_revision INTEGER NOT NULL CHECK (authority_schema_revision = 1),
    authority_namespace_id TEXT NOT NULL,
    authority_store_resolved_path TEXT NOT NULL,
    authority_store_path_identity_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE conflict_domain_authority (
    conflict_domain_ref TEXT PRIMARY KEY,
    environment_classification TEXT NOT NULL,
    ledger_instance_id TEXT NOT NULL UNIQUE,
    ledger_resolved_path TEXT NOT NULL UNIQUE,
    ledger_path_identity_sha256 TEXT NOT NULL UNIQUE,
    trusted_sequence INTEGER NOT NULL CHECK (trusted_sequence >= 1),
    trusted_event_hash TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
CREATE TRIGGER trg_authority_meta_no_update BEFORE UPDATE ON authority_meta
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_AUTHORITY_META'); END;
CREATE TRIGGER trg_authority_meta_no_delete BEFORE DELETE ON authority_meta
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_AUTHORITY_META'); END;
CREATE TRIGGER trg_conflict_authority_no_delete BEFORE DELETE ON conflict_domain_authority
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CONFLICT_DOMAIN_BINDING'); END;
CREATE TRIGGER trg_conflict_authority_immutable_fields BEFORE UPDATE ON conflict_domain_authority
WHEN NEW.conflict_domain_ref != OLD.conflict_domain_ref OR
     NEW.environment_classification != OLD.environment_classification OR
     NEW.ledger_instance_id != OLD.ledger_instance_id OR
     NEW.ledger_resolved_path != OLD.ledger_resolved_path OR
     NEW.ledger_path_identity_sha256 != OLD.ledger_path_identity_sha256
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CONFLICT_DOMAIN_BINDING'); END;
CREATE TRIGGER trg_conflict_authority_monotonic_tail BEFORE UPDATE ON conflict_domain_authority
WHEN NEW.trusted_sequence <= OLD.trusted_sequence
BEGIN SELECT RAISE(ABORT, 'NON_MONOTONIC_AUTHORITY_TAIL'); END;
PRAGMA user_version=1;
"""


_LEDGER_SCHEMA = """
CREATE TABLE ledger_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    ledger_instance_id TEXT NOT NULL UNIQUE,
    ledger_schema_revision INTEGER NOT NULL CHECK (ledger_schema_revision = 1),
    created_at_utc TEXT NOT NULL,
    environment_classification TEXT NOT NULL,
    conflict_domain_ref TEXT NOT NULL,
    preledger_history_mode TEXT NOT NULL CHECK (preledger_history_mode = 'LEGACY_IMPORT_REQUIRED'),
    authority_instance_id TEXT NOT NULL,
    authority_namespace_id TEXT NOT NULL,
    authority_store_path_identity_sha256 TEXT NOT NULL,
    ledger_path_identity_sha256 TEXT NOT NULL
);
CREATE TABLE ledger_events (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    event_id TEXT NOT NULL UNIQUE,
    ledger_instance_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_schema_revision INTEGER NOT NULL CHECK (event_schema_revision = 1),
    writer_session_id TEXT,
    incident_id TEXT,
    execution_attempt_id TEXT,
    recorded_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    previous_event_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    FOREIGN KEY (ledger_instance_id) REFERENCES ledger_meta(ledger_instance_id)
);
CREATE TRIGGER trg_ledger_events_no_update BEFORE UPDATE ON ledger_events
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_EVENTS'); END;
CREATE TRIGGER trg_ledger_events_no_delete BEFORE DELETE ON ledger_events
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_EVENTS'); END;
CREATE TRIGGER trg_ledger_meta_no_update BEFORE UPDATE ON ledger_meta
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_META'); END;
CREATE TRIGGER trg_ledger_meta_no_delete BEFORE DELETE ON ledger_meta
BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_META'); END;
PRAGMA user_version=1;
"""


_AUTHORITY_TABLE_COLUMNS = {
    "authority_meta": ("singleton", "authority_instance_id", "authority_schema_revision", "authority_namespace_id", "authority_store_resolved_path", "authority_store_path_identity_sha256", "created_at_utc"),
    "conflict_domain_authority": ("conflict_domain_ref", "environment_classification", "ledger_instance_id", "ledger_resolved_path", "ledger_path_identity_sha256", "trusted_sequence", "trusted_event_hash", "updated_at_utc"),
}
_LEDGER_TABLE_COLUMNS = {
    "ledger_meta": ("singleton", "ledger_instance_id", "ledger_schema_revision", "created_at_utc", "environment_classification", "conflict_domain_ref", "preledger_history_mode", "authority_instance_id", "authority_namespace_id", "authority_store_path_identity_sha256", "ledger_path_identity_sha256"),
    "ledger_events": ("sequence", "event_id", "ledger_instance_id", "event_type", "event_schema_revision", "writer_session_id", "incident_id", "execution_attempt_id", "recorded_at_utc", "payload_json", "payload_sha256", "previous_event_hash", "event_hash"),
}
_AUTHORITY_TRIGGERS = frozenset({"trg_authority_meta_no_update", "trg_authority_meta_no_delete", "trg_conflict_authority_no_delete", "trg_conflict_authority_immutable_fields", "trg_conflict_authority_monotonic_tail"})
_LEDGER_TRIGGERS = frozenset({"trg_ledger_events_no_update", "trg_ledger_events_no_delete", "trg_ledger_meta_no_update", "trg_ledger_meta_no_delete"})

_AUTHORITY_TRIGGER_SQL = {
    "trg_authority_meta_no_update": "CREATE TRIGGER trg_authority_meta_no_update BEFORE UPDATE ON authority_meta BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_AUTHORITY_META'); END",
    "trg_authority_meta_no_delete": "CREATE TRIGGER trg_authority_meta_no_delete BEFORE DELETE ON authority_meta BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_AUTHORITY_META'); END",
    "trg_conflict_authority_no_delete": "CREATE TRIGGER trg_conflict_authority_no_delete BEFORE DELETE ON conflict_domain_authority BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CONFLICT_DOMAIN_BINDING'); END",
    "trg_conflict_authority_immutable_fields": "CREATE TRIGGER trg_conflict_authority_immutable_fields BEFORE UPDATE ON conflict_domain_authority WHEN NEW.conflict_domain_ref != OLD.conflict_domain_ref OR NEW.environment_classification != OLD.environment_classification OR NEW.ledger_instance_id != OLD.ledger_instance_id OR NEW.ledger_resolved_path != OLD.ledger_resolved_path OR NEW.ledger_path_identity_sha256 != OLD.ledger_path_identity_sha256 BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CONFLICT_DOMAIN_BINDING'); END",
    "trg_conflict_authority_monotonic_tail": "CREATE TRIGGER trg_conflict_authority_monotonic_tail BEFORE UPDATE ON conflict_domain_authority WHEN NEW.trusted_sequence <= OLD.trusted_sequence BEGIN SELECT RAISE(ABORT, 'NON_MONOTONIC_AUTHORITY_TAIL'); END",
}
_LEDGER_TRIGGER_SQL = {
    "trg_ledger_events_no_update": "CREATE TRIGGER trg_ledger_events_no_update BEFORE UPDATE ON ledger_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_EVENTS'); END",
    "trg_ledger_events_no_delete": "CREATE TRIGGER trg_ledger_events_no_delete BEFORE DELETE ON ledger_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_EVENTS'); END",
    "trg_ledger_meta_no_update": "CREATE TRIGGER trg_ledger_meta_no_update BEFORE UPDATE ON ledger_meta BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_META'); END",
    "trg_ledger_meta_no_delete": "CREATE TRIGGER trg_ledger_meta_no_delete BEFORE DELETE ON ledger_meta BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_LEDGER_META'); END",
}
_AUTHORITY_TABLE_SQL = {
    "authority_meta": "CREATE TABLE authority_meta (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), authority_instance_id TEXT NOT NULL UNIQUE, authority_schema_revision INTEGER NOT NULL CHECK (authority_schema_revision = 1), authority_namespace_id TEXT NOT NULL, authority_store_resolved_path TEXT NOT NULL, authority_store_path_identity_sha256 TEXT NOT NULL, created_at_utc TEXT NOT NULL)",
    "conflict_domain_authority": "CREATE TABLE conflict_domain_authority (conflict_domain_ref TEXT PRIMARY KEY, environment_classification TEXT NOT NULL, ledger_instance_id TEXT NOT NULL UNIQUE, ledger_resolved_path TEXT NOT NULL UNIQUE, ledger_path_identity_sha256 TEXT NOT NULL UNIQUE, trusted_sequence INTEGER NOT NULL CHECK (trusted_sequence >= 1), trusted_event_hash TEXT NOT NULL, updated_at_utc TEXT NOT NULL)",
}
_LEDGER_TABLE_SQL = {
    "ledger_meta": "CREATE TABLE ledger_meta (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), ledger_instance_id TEXT NOT NULL UNIQUE, ledger_schema_revision INTEGER NOT NULL CHECK (ledger_schema_revision = 1), created_at_utc TEXT NOT NULL, environment_classification TEXT NOT NULL, conflict_domain_ref TEXT NOT NULL, preledger_history_mode TEXT NOT NULL CHECK (preledger_history_mode = 'LEGACY_IMPORT_REQUIRED'), authority_instance_id TEXT NOT NULL, authority_namespace_id TEXT NOT NULL, authority_store_path_identity_sha256 TEXT NOT NULL, ledger_path_identity_sha256 TEXT NOT NULL)",
    "ledger_events": "CREATE TABLE ledger_events (sequence INTEGER PRIMARY KEY CHECK (sequence >= 1), event_id TEXT NOT NULL UNIQUE, ledger_instance_id TEXT NOT NULL, event_type TEXT NOT NULL, event_schema_revision INTEGER NOT NULL CHECK (event_schema_revision = 1), writer_session_id TEXT, incident_id TEXT, execution_attempt_id TEXT, recorded_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, previous_event_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE, FOREIGN KEY (ledger_instance_id) REFERENCES ledger_meta(ledger_instance_id))",
}


def _normalize_schema_sql(value: str) -> str:
    return "".join(value.split()).rstrip(";").lower()


def _validate_integrity(connection: sqlite3.Connection, *, authority: bool) -> None:
    failure = FailureCode.AUTHORITY_INTEGRITY_CHECK_FAILURE if authority else FailureCode.LEDGER_INTEGRITY_CHECK_FAILURE
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.Error as exc:
        raise LedgerError(failure) from exc
    if rows != [("ok",)] or foreign != []:
        raise LedgerError(failure)


def _validate_schema(connection: sqlite3.Connection, *, authority: bool) -> None:
    expected_revision = AUTHORITY_SCHEMA_REVISION if authority else LEDGER_SCHEMA_REVISION
    observed = _pragma_scalar(connection, "PRAGMA user_version")
    if observed != expected_revision:
        if type(observed) is int and observed > expected_revision:
            code = FailureCode.AUTHORITY_SCHEMA_UNSUPPORTED_NEWER if authority else FailureCode.LEDGER_SCHEMA_UNSUPPORTED_NEWER
        elif type(observed) is int and observed < expected_revision:
            code = FailureCode.AUTHORITY_SCHEMA_UNSUPPORTED_OLDER if authority else FailureCode.LEDGER_SCHEMA_UNSUPPORTED_OLDER
        else:
            code = FailureCode.AUTHORITY_SCHEMA_IDENTITY_MISMATCH if authority else FailureCode.LEDGER_SCHEMA_IDENTITY_MISMATCH
        raise LedgerError(code)
    tables = _AUTHORITY_TABLE_COLUMNS if authority else _LEDGER_TABLE_COLUMNS
    expected_table_sql = _AUTHORITY_TABLE_SQL if authority else _LEDGER_TABLE_SQL
    triggers = _AUTHORITY_TRIGGERS if authority else _LEDGER_TRIGGERS
    expected_trigger_sql = _AUTHORITY_TRIGGER_SQL if authority else _LEDGER_TRIGGER_SQL
    schema_code = FailureCode.AUTHORITY_SCHEMA_IDENTITY_MISMATCH if authority else FailureCode.LEDGER_SCHEMA_IDENTITY_MISMATCH
    for table, columns in tables.items():
        actual = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
        if actual != columns:
            raise LedgerError(schema_code)
        table_row = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if (
            table_row is None
            or type(table_row[0]) is not str
            or _normalize_schema_sql(table_row[0]) != _normalize_schema_sql(expected_table_sql[table])
        ):
            raise LedgerError(schema_code)
    actual_triggers = {row[0]: row[1] for row in connection.execute("SELECT name, sql FROM sqlite_schema WHERE type='trigger'")}
    if set(actual_triggers) != set(triggers) or any(
        not actual_triggers[name]
        or _normalize_schema_sql(actual_triggers[name]) != _normalize_schema_sql(expected_trigger_sql[name])
        for name in triggers
    ):
        raise LedgerError(schema_code)
    if not authority:
        foreign = connection.execute("PRAGMA foreign_key_list(ledger_events)").fetchall()
        if len(foreign) != 1 or foreign[0][2:5] != ("ledger_meta", "ledger_instance_id", "ledger_instance_id"):
            raise LedgerError(schema_code)


def _authority_meta(connection: sqlite3.Connection) -> AuthorityMeta:
    rows = connection.execute("SELECT authority_instance_id,authority_schema_revision,authority_namespace_id,authority_store_resolved_path,authority_store_path_identity_sha256,created_at_utc FROM authority_meta").fetchall()
    if len(rows) != 1:
        raise LedgerError(FailureCode.AUTHORITY_SCHEMA_IDENTITY_MISMATCH)
    meta = AuthorityMeta(*rows[0])
    _uuid4_text_for(meta.authority_instance_id, FailureCode.AUTHORITY_IDENTITY_MISMATCH)
    validate_canonical_timestamp(meta.created_at_utc)
    if meta.authority_schema_revision != 1 or not _HEX64_RE.fullmatch(meta.authority_store_path_identity_sha256):
        raise LedgerError(FailureCode.AUTHORITY_SCHEMA_IDENTITY_MISMATCH)
    return meta


def _authority_row(connection: sqlite3.Connection, conflict_domain_ref: str) -> AuthorityRow:
    rows = connection.execute("SELECT conflict_domain_ref,environment_classification,ledger_instance_id,ledger_resolved_path,ledger_path_identity_sha256,trusted_sequence,trusted_event_hash,updated_at_utc FROM conflict_domain_authority WHERE conflict_domain_ref=?", (conflict_domain_ref,)).fetchall()
    if len(rows) != 1:
        raise LedgerError(FailureCode.AUTHORITY_CONFLICT_DOMAIN_BINDING_MISSING)
    row = AuthorityRow(*rows[0])
    _uuid4_text(row.ledger_instance_id)
    if type(row.trusted_sequence) is not int or row.trusted_sequence < 1 or not _HEX64_RE.fullmatch(row.trusted_event_hash):
        raise LedgerError(FailureCode.AUTHORITY_INTEGRITY_CHECK_FAILURE)
    validate_canonical_timestamp(row.updated_at_utc)
    return row


def _ledger_meta(connection: sqlite3.Connection) -> LedgerMeta:
    rows = connection.execute("SELECT ledger_instance_id,ledger_schema_revision,created_at_utc,environment_classification,conflict_domain_ref,preledger_history_mode,authority_instance_id,authority_namespace_id,authority_store_path_identity_sha256,ledger_path_identity_sha256 FROM ledger_meta").fetchall()
    if len(rows) != 1:
        raise LedgerError(FailureCode.LEDGER_SCHEMA_IDENTITY_MISMATCH)
    meta = LedgerMeta(*rows[0])
    _uuid4_text(meta.ledger_instance_id)
    _uuid4_text(meta.authority_instance_id)
    validate_canonical_timestamp(meta.created_at_utc)
    if meta.ledger_schema_revision != 1 or meta.preledger_history_mode != PRELEDGER_HISTORY_MODE:
        raise LedgerError(FailureCode.LEDGER_SCHEMA_IDENTITY_MISMATCH)
    if not _HEX64_RE.fullmatch(meta.authority_store_path_identity_sha256) or not _HEX64_RE.fullmatch(meta.ledger_path_identity_sha256):
        raise LedgerError(FailureCode.LEDGER_SCHEMA_IDENTITY_MISMATCH)
    return meta


def initialize_authority_namespace(
    binding: AuthorityNamespaceBinding,
    *,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
) -> AuthorityMeta:
    if binding.authority_schema_revision != 1:
        raise LedgerError(FailureCode.AUTHORITY_SCHEMA_IDENTITY_MISMATCH)
    connection = _connect_new(binding.authority_store_resolved_path, authority=True)
    created = canonical_timestamp(clock())
    instance = str(uuid_factory())
    _uuid4_text(instance)
    try:
        connection.executescript("BEGIN EXCLUSIVE;\n" + _AUTHORITY_SCHEMA)
        connection.execute(
            "INSERT INTO authority_meta VALUES (1,?,?,?,?,?,?)",
            (instance, 1, binding.authority_namespace_id, os.path.normcase(os.path.normpath(str(binding.authority_store_resolved_path))), binding.authority_store_path_identity_sha256, created),
        )
        connection.commit()
        _validate_schema(connection, authority=True)
        _validate_integrity(connection, authority=True)
        return _authority_meta(connection)
    except LedgerError:
        if connection.in_transaction:
            connection.rollback()
        raise
    except sqlite3.Error as exc:
        if connection.in_transaction:
            connection.rollback()
        raise LedgerError(FailureCode.AUTHORITY_STORAGE_OPEN_FAILURE) from exc
    finally:
        connection.close()


def _validate_authority_open(connection: sqlite3.Connection, binding: AuthorityNamespaceBinding) -> AuthorityMeta:
    _validate_schema(connection, authority=True)
    _validate_integrity(connection, authority=True)
    meta = _authority_meta(connection)
    normalized = os.path.normcase(os.path.normpath(str(binding.authority_store_resolved_path)))
    if (
        meta.authority_namespace_id != binding.authority_namespace_id
        or meta.authority_store_resolved_path != normalized
        or meta.authority_store_path_identity_sha256 != binding.authority_store_path_identity_sha256
    ):
        raise LedgerError(FailureCode.AUTHORITY_IDENTITY_MISMATCH)
    return meta


def _event_core(event: LedgerEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_schema_revision": event.event_schema_revision,
        "event_type": event.event_type.value,
        "execution_attempt_id": event.execution_attempt_id,
        "incident_id": event.incident_id,
        "ledger_instance_id": event.ledger_instance_id,
        "payload": dict(event.payload),
        "payload_sha256": event.payload_sha256,
        "previous_event_hash": event.previous_event_hash,
        "recorded_at_utc": event.recorded_at_utc,
        "sequence": event.sequence,
        "writer_session_id": event.writer_session_id,
    }


def _construct_event(
    *, meta: LedgerMeta, sequence: int, previous_hash: str, event_input: EventInput,
    clock: Clock, uuid_factory: UuidFactory,
) -> LedgerEvent:
    if type(event_input.event_type) is not EventType:
        raise LedgerError(FailureCode.LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE)
    payload_bytes = canonical_json_bytes(dict(event_input.payload))
    payload_text = payload_bytes.decode("utf-8")
    payload_hash = sha256_hex(payload_bytes)
    if event_input.event_type in _NEW_EVENT_DOMAINS:
        expected_new_event_id = deterministic_event_id(event_input.event_type, event_input.payload)
        event_id = event_input.event_id or expected_new_event_id
        if event_id != expected_new_event_id:
            raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
    else:
        event_id = event_input.event_id or f"evt_{uuid_factory().hex}"
    if event_input.event_type is EventType.LEGACY_INCIDENT_IMPORTED:
        expected = f"legacy_{payload_hash}"
        if event_id != expected:
            raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
    elif _EVENT_ID_RE.fullmatch(event_id) is None:
        raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
    recorded = event_input.recorded_at_utc or canonical_timestamp(clock())
    validate_canonical_timestamp(recorded)
    for optional in (event_input.writer_session_id, event_input.incident_id, event_input.execution_attempt_id):
        if optional is not None:
            _require_canonical_text(optional)
    if (
        event_input.writer_session_id is not None
        and _WRITER_SESSION_ID_RE.fullmatch(event_input.writer_session_id) is None
        and _RESTRICTED_SESSION_ID_RE.fullmatch(event_input.writer_session_id) is None
    ):
        raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
    placeholder = LedgerEvent(sequence, event_id, meta.ledger_instance_id, event_input.event_type, 1, event_input.writer_session_id, event_input.incident_id, event_input.execution_attempt_id, recorded, MappingProxyType(dict(parse_canonical_json(payload_text))), payload_text, payload_hash, previous_hash, "")
    event_hash = sha256_hex(EVENT_HASH_DOMAIN + _canonical_stored_json_bytes(_event_core(placeholder)))
    return LedgerEvent(
        sequence, event_id, meta.ledger_instance_id, event_input.event_type, 1,
        event_input.writer_session_id, event_input.incident_id,
        event_input.execution_attempt_id, recorded, placeholder.payload,
        payload_text, payload_hash, previous_hash, event_hash,
    )


def _row_to_event(row: Sequence[object]) -> LedgerEvent:
    try:
        event_type = EventType(row[3])
    except ValueError as exc:
        raise LedgerError(FailureCode.LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE) from exc
    payload = parse_canonical_json(row[9])
    if type(payload) is not dict:
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
    return LedgerEvent(
        sequence=row[0], event_id=row[1], ledger_instance_id=row[2], event_type=event_type,
        event_schema_revision=row[4], writer_session_id=row[5], incident_id=row[6],
        execution_attempt_id=row[7], recorded_at_utc=row[8],
        payload=MappingProxyType(payload), payload_json=row[9], payload_sha256=row[10],
        previous_event_hash=row[11], event_hash=row[12],
    )


def load_and_validate_events(connection: sqlite3.Connection, meta: LedgerMeta) -> tuple[LedgerEvent, ...]:
    rows = connection.execute("SELECT sequence,event_id,ledger_instance_id,event_type,event_schema_revision,writer_session_id,incident_id,execution_attempt_id,recorded_at_utc,payload_json,payload_sha256,previous_event_hash,event_hash FROM ledger_events ORDER BY sequence").fetchall()
    events: list[LedgerEvent] = []
    seen_ids: dict[str, LedgerEvent] = {}
    previous = ZERO_HASH
    for index, row in enumerate(rows, start=1):
        event = _row_to_event(row)
        if type(event.sequence) is not int or event.sequence != index:
            raise LedgerError(FailureCode.LEDGER_SEQUENCE_INTEGRITY_FAILURE)
        if event.ledger_instance_id != meta.ledger_instance_id:
            raise LedgerError(FailureCode.LEDGER_INSTANCE_ID_MISMATCH)
        if event.event_schema_revision != 1:
            raise LedgerError(FailureCode.LEDGER_SCHEMA_UNSUPPORTED_NEWER if event.event_schema_revision > 1 else FailureCode.LEDGER_SCHEMA_UNSUPPORTED_OLDER)
        validate_canonical_timestamp(event.recorded_at_utc)
        if sha256_hex(event.payload_json.encode("utf-8")) != event.payload_sha256:
            raise LedgerError(FailureCode.LEDGER_HASH_CHAIN_FAILURE)
        if event.previous_event_hash != previous:
            raise LedgerError(FailureCode.LEDGER_HASH_CHAIN_FAILURE)
        if sha256_hex(EVENT_HASH_DOMAIN + _canonical_stored_json_bytes(_event_core(event))) != event.event_hash:
            raise LedgerError(FailureCode.LEDGER_HASH_CHAIN_FAILURE)
        if event.event_id in seen_ids:
            raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
        if event.event_type in _NEW_EVENT_DOMAINS:
            if event.event_id != deterministic_event_id(event.event_type, event.payload):
                raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
        elif event.event_type is EventType.LEGACY_INCIDENT_IMPORTED:
            if event.event_id != f"legacy_{event.payload_sha256}":
                raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
        elif _EVENT_ID_RE.fullmatch(event.event_id) is None:
            raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
        seen_ids[event.event_id] = event
        events.append(event)
        previous = event.event_hash
    if not events or events[0].event_type is not EventType.LEDGER_INITIALIZED:
        raise LedgerError(FailureCode.LEDGER_SEQUENCE_INTEGRITY_FAILURE)
    _validate_initialization_event(meta, events[0])
    _validate_event_semantics(events)
    return tuple(events)


def _validate_initialization_event(meta: LedgerMeta, event: LedgerEvent) -> None:
    expected = {
        "authority_instance_id": meta.authority_instance_id,
        "authority_namespace_id": meta.authority_namespace_id,
        "authority_store_path_identity_sha256": meta.authority_store_path_identity_sha256,
        "conflict_domain_ref": meta.conflict_domain_ref,
        "created_at_utc": meta.created_at_utc,
        "environment_classification": meta.environment_classification,
        "ledger_instance_id": meta.ledger_instance_id,
        "ledger_path_identity_sha256": meta.ledger_path_identity_sha256,
        "ledger_schema_revision": 1,
        "preledger_history_mode": PRELEDGER_HISTORY_MODE,
    }
    if (
        dict(event.payload) != expected
        or type(event.payload.get("ledger_schema_revision")) is not int
        or event.sequence != 1
        or event.writer_session_id is not None
        or event.incident_id is not None
        or event.execution_attempt_id is not None
    ):
        raise LedgerError(FailureCode.LEDGER_SCHEMA_IDENTITY_MISMATCH)


def _require_payload_keys(event: LedgerEvent, required: set[str]) -> None:
    if not required.issubset(event.payload):
        raise LedgerError(FailureCode.EVENT_REQUIRED_PARENT_MISSING)


def _require_exact_payload_keys(event: LedgerEvent, required: set[str]) -> None:
    if set(event.payload) != required:
        raise LedgerError(FailureCode.EVENT_REQUIRED_PARENT_MISSING)


_RELEASE_PREDICATE_KEYS = frozenset({
    "ledger_integrity_pass", "authority_anchor_consistency_pass", "binding_identity_pass",
    "supported_event_set_pass", "trusted_replay_complete", "no_unresolved_emergency_cancel",
    "known_active_orders_reconciled", "fills_reconciled", "zero_identity_conflicts",
    "conservative_exposure_finite_and_within_limits", "risk_config_complete_valid",
    "market_data_fresh", "reconciliation_fresh", "venue_defense_pass",
    "protected_unresolved_legacy_write_count_zero", "no_controlling_unresolved_write",
    "writer_proof_release_eligible", "state_safe_held", "no_outstanding_permits",
})

_NEW_EVENT_PAYLOAD_KEYS = MappingProxyType({
    EventType.RISK_CONTROL_STATE_CHANGED: frozenset({
        "previous_state", "new_state", "cause", "risk_state_epoch_before",
        "risk_state_epoch_after", "risk_config_sha256", "related_emergency_action_id",
        "related_release_id", "predecessor_state_event_id",
        "observed_authority_trusted_sequence", "observed_authority_trusted_hash",
        "observed_ledger_terminal_sequence", "observed_ledger_terminal_hash",
    }),
    EventType.EMERGENCY_ACTION_OPENED: frozenset({
        "emergency_action_id", "conflict_domain_ref", "cause", "starting_control_state",
        "target_set_kind", "target_order_ids", "target_set_sha256", "risk_config_sha256",
        "risk_state_epoch", "authority_trusted_sequence", "authority_trusted_hash",
        "ledger_terminal_sequence", "ledger_terminal_hash", "opened_at_utc",
        "deduplication_key_sha256",
    }),
    EventType.CANCEL_INTENT_RECORDED: frozenset({
        "emergency_action_id", "cancel_attempt_id", "target_order_id", "conflict_domain_ref",
        "subaccount", "exchange_index", "source_binding_id", "risk_state_epoch",
        "risk_config_sha256", "authoritative_order_observation_event_id",
        "authoritative_order_observation_event_hash", "prior_order_status",
        "prior_remaining_count_fp", "attempt_ordinal", "request_id", "intent_recorded_at_utc",
    }),
    EventType.CANCEL_SEND_BOUNDARY_ENTERED: frozenset({
        "emergency_action_id", "cancel_attempt_id", "target_order_id", "request_id",
        "canonical_request_sha256", "operation_name", "method", "path_without_query",
        "attempt_ordinal", "deadline_id", "deadline_budget_ms", "deadline_process_instance_id",
        "deadline_started_monotonic_ns", "deadline_absolute_monotonic_ns",
        "predecessor_intent_event_id", "predecessor_intent_event_hash",
        "predecessor_authority_trusted_sequence", "predecessor_authority_trusted_hash",
        "predecessor_ledger_terminal_sequence", "predecessor_ledger_terminal_hash",
        "write_ambiguity_rule", "boundary_recorded_at_utc",
    }),
    EventType.CANCEL_RESULT_RECORDED: frozenset({
        "emergency_action_id", "cancel_attempt_id", "target_order_id", "result_revision",
        "prior_result_event_id", "result_class", "response_present", "response_http_status",
        "response_media_type_class", "response_body_sha256", "response_byte_length",
        "response_order_id", "response_reduced_by_fp", "reconciliation_basis_event_ids",
        "fill_basis_event_ids", "order_state_basis_event_ids", "canceled_quantity_fp",
        "filled_quantity_fp", "remaining_quantity_fp", "write_closure_class", "unresolved",
        "result_at_utc",
    }),
    EventType.RISK_RELEASE_RECORDED: frozenset({
        "release_id", "risk_config_sha256", "risk_state_epoch", "authority_trusted_sequence",
        "authority_trusted_hash", "ledger_terminal_sequence", "ledger_terminal_hash",
        "reconciliation_snapshot_sha256", "risk_snapshot_sha256", "predicate_vector",
        "predicate_vector_sha256", "writer_proof_id", "safe_held_state_event_id",
        "safe_held_state_event_hash", "release_recorded_at_utc",
    }),
    EventType.RESTRICTED_SESSION_STARTED: frozenset({
        "restricted_session_id", "acquisition_mode", "session_schema_revision", "lock_model",
        "prior_restricted_session_state", "opening_trusted_sequence", "opening_trusted_event_hash",
        "opening_ledger_sequence", "opening_ledger_event_hash",
    }),
    EventType.RESTRICTED_SESSION_ENDED: frozenset({
        "restricted_session_id", "acquisition_mode", "pre_end_trusted_sequence",
        "pre_end_trusted_event_hash", "pre_end_ledger_sequence", "pre_end_ledger_event_hash",
        "end_reason",
    }),
    EventType.RESTRICTED_SESSION_ABANDONED: frozenset({
        "abandoned_restricted_session_id", "acquisition_mode", "reason",
        "observed_trusted_sequence", "observed_trusted_event_hash",
        "observed_ledger_sequence", "observed_ledger_event_hash",
    }),
})

_ID_PATTERNS = MappingProxyType({
    "emergency_action_id": re.compile(r"^ea_[0-9a-f]{32}$"),
    "cancel_attempt_id": re.compile(r"^ca_[0-9a-f]{32}$"),
    "request_id": re.compile(r"^req_[0-9a-f]{32}$"),
    "deadline_id": re.compile(r"^dl_[0-9a-f]{32}$"),
    "release_id": re.compile(r"^rel_[0-9a-f]{32}$"),
    "process_instance_id": re.compile(r"^proc_[0-9a-f]{32}$"),
})
_QTY2_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]{2}$")


def _schema_error(code: FailureCode = FailureCode.EVENT_SCHEMA_CONTRACT_VIOLATION) -> None:
    raise LedgerError(code)


def _is_sha256(value: object) -> bool:
    return type(value) is str and _HEX64_RE.fullmatch(value) is not None


def _is_event_id(value: object) -> bool:
    return type(value) is str and _EVENT_ID_RE.fullmatch(value) is not None


def _is_named_id(name: str, value: object) -> bool:
    return type(value) is str and _ID_PATTERNS[name].fullmatch(value) is not None


def _is_qty2(value: object, *, positive: bool = False) -> bool:
    return (
        type(value) is str
        and _QTY2_RE.fullmatch(value) is not None
        and (not positive or Decimal(value) > 0)
    )


def _require_tail(payload: Mapping[str, object], seq_key: str, hash_key: str, previous: LedgerEvent) -> None:
    if type(payload.get(seq_key)) is not int or payload.get(seq_key) != previous.sequence or payload.get(hash_key) != previous.event_hash:
        _schema_error(FailureCode.EVENT_REQUIRED_REFERENCE_INVALID)


def _require_sorted_unique_ids(value: object, *, event_ids: bool = False) -> list[str]:
    if type(value) is not list or any(type(item) is not str for item in value):
        _schema_error()
    items = list(value)
    if items != sorted(set(items)):
        _schema_error()
    if event_ids and any(_EVENT_ID_RE.fullmatch(item) is None for item in items):
        _schema_error()
    return items


def _validate_spec03_event_sequence(events: Sequence[LedgerEvent], session_modes: Mapping[str, AcquisitionMode]) -> None:
    """Validate the closed Spec-03 vocabulary without altering historical schemas."""
    by_id: dict[str, LedgerEvent] = {}
    active_session: str | None = None
    active_mode: AcquisitionMode | None = None
    risk_state = "BOOT_HOLD"
    risk_epoch = 0
    last_state_event: LedgerEvent | None = None
    actions: dict[str, LedgerEvent] = {}
    action_dedup: dict[str, str] = {}
    intents: dict[str, LedgerEvent] = {}
    intent_ordinals: dict[tuple[str, str], int] = {}
    attempt_by_action_target: dict[tuple[str, str], str] = {}
    boundaries: set[str] = set()
    results: dict[str, LedgerEvent] = {}
    releases: dict[str, LedgerEvent] = {}
    proof_states: dict[str, str] = {}
    proof_eligible: dict[str, bool] = {}
    proof_incidents: dict[str, str | None] = {}
    emergency_old = {
        EventType.ORDER_OBSERVED, EventType.FILL_OBSERVED, EventType.RECONCILIATION_RECORDED,
        EventType.EXECUTION_HALTED, EventType.WRITER_PROOF_HELD,
    }
    for index, event in enumerate(events):
        previous = events[index - 1] if index else event
        payload = event.payload
        if event.event_type is EventType.WRITER_SESSION_STARTED:
            active_session = event.writer_session_id
            active_mode = AcquisitionMode.NORMAL_WRITER
        elif event.event_type in {EventType.WRITER_SESSION_ENDED, EventType.WRITER_SESSION_ABANDONED}:
            active_session = None
            active_mode = None

        if event.event_type is EventType.RESTRICTED_SESSION_STARTED:
            if set(payload) != _NEW_EVENT_PAYLOAD_KEYS[event.event_type]:
                _schema_error()
            sid = payload["restricted_session_id"]
            try:
                mode = AcquisitionMode(payload["acquisition_mode"])
            except (TypeError, ValueError):
                _schema_error(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            if (
                event.incident_id is not None or event.execution_attempt_id is not None
                or event.writer_session_id != sid or type(sid) is not str
                or _RESTRICTED_SESSION_ID_RE.fullmatch(sid) is None
                or mode not in {AcquisitionMode.EMERGENCY_CONTROL_ONLY, AcquisitionMode.RELEASE_ONLY}
                or active_session is not None or type(payload["session_schema_revision"]) is not int
                or payload["session_schema_revision"] != 1 or payload["lock_model"] != LOCK_MODEL
                or payload["prior_restricted_session_state"] not in {"NONE", "CLEAN", "ABNORMAL"}
            ):
                _schema_error(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            _require_tail(payload, "opening_trusted_sequence", "opening_trusted_event_hash", previous)
            _require_tail(payload, "opening_ledger_sequence", "opening_ledger_event_hash", previous)
            active_session, active_mode = sid, mode
        elif event.event_type is EventType.RESTRICTED_SESSION_ENDED:
            if set(payload) != _NEW_EVENT_PAYLOAD_KEYS[event.event_type]:
                _schema_error()
            sid = payload["restricted_session_id"]
            if (
                event.writer_session_id != sid or event.incident_id is not None or event.execution_attempt_id is not None
                or sid != active_session or payload["acquisition_mode"] != (active_mode.value if active_mode else None)
                or payload["end_reason"] != "CLEAN_RELEASE_OF_EXCLUSIVE_LOCKS"
            ):
                _schema_error(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            _require_tail(payload, "pre_end_trusted_sequence", "pre_end_trusted_event_hash", previous)
            _require_tail(payload, "pre_end_ledger_sequence", "pre_end_ledger_event_hash", previous)
            active_session = None
            active_mode = None
        elif event.event_type is EventType.RESTRICTED_SESSION_ABANDONED:
            if set(payload) != _NEW_EVENT_PAYLOAD_KEYS[event.event_type]:
                _schema_error()
            sid = payload["abandoned_restricted_session_id"]
            if (
                event.writer_session_id is not None or event.incident_id is not None or event.execution_attempt_id is not None
                or sid != active_session or payload["acquisition_mode"] != (active_mode.value if active_mode else None)
                or payload["reason"] != "PREVIOUS_RESTRICTED_SESSION_NO_LONGER_HOLDS_REQUIRED_AUTHORITY_AND_LEDGER_LOCKS"
            ):
                _schema_error(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            _require_tail(payload, "observed_trusted_sequence", "observed_trusted_event_hash", previous)
            _require_tail(payload, "observed_ledger_sequence", "observed_ledger_event_hash", previous)
            active_session = None
            active_mode = None
        elif event.writer_session_id is not None and _RESTRICTED_SESSION_ID_RE.fullmatch(event.writer_session_id):
            if event.writer_session_id != active_session:
                _schema_error(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            if active_mode is AcquisitionMode.EMERGENCY_CONTROL_ONLY:
                admitted = emergency_old | {
                    EventType.RISK_CONTROL_STATE_CHANGED, EventType.EMERGENCY_ACTION_OPENED,
                    EventType.CANCEL_INTENT_RECORDED, EventType.CANCEL_SEND_BOUNDARY_ENTERED,
                    EventType.CANCEL_RESULT_RECORDED,
                }
            else:
                admitted = {EventType.RISK_RELEASE_RECORDED, EventType.WRITER_PROOF_RELEASED, EventType.RISK_CONTROL_STATE_CHANGED}
            if event.event_type not in admitted:
                _schema_error(FailureCode.RESTRICTED_SESSION_EVENT_NOT_PERMITTED)

        if event.event_type in _NEW_EVENT_PAYLOAD_KEYS and event.event_type not in {
            EventType.RESTRICTED_SESSION_STARTED, EventType.RESTRICTED_SESSION_ENDED,
            EventType.RESTRICTED_SESSION_ABANDONED,
        }:
            if set(payload) != _NEW_EVENT_PAYLOAD_KEYS[event.event_type] or event.incident_id is not None or event.execution_attempt_id is not None:
                _schema_error()

        if event.event_type is EventType.WRITER_PROOF_HELD:
            proof_id = str(payload.get("writer_proof_id"))
            proof_states[proof_id] = "HELD"
            proof_eligible[proof_id] = False
            proof_incidents[proof_id] = event.incident_id
        elif event.event_type is EventType.RECONCILIATION_RECORDED:
            if payload.get("writer_proof_release_eligible") is True:
                for proof_id, incident_id in proof_incidents.items():
                    if incident_id == event.incident_id and proof_states.get(proof_id) == "HELD":
                        proof_eligible[proof_id] = True
        elif event.event_type is EventType.WRITER_PROOF_RELEASED:
            proof_id = payload.get("writer_proof_id")
            release_basis = payload.get("release_basis_event_ids")
            prior_release = previous if index else None
            if (
                active_mode is not AcquisitionMode.RELEASE_ONLY
                or risk_state != "SAFE_HELD"
                or type(proof_id) is not str
                or proof_states.get(proof_id) != "HELD"
                or proof_eligible.get(proof_id) is not True
                or prior_release is None
                or prior_release.event_type is not EventType.RISK_RELEASE_RECORDED
                or prior_release.payload.get("writer_proof_id") != proof_id
                or type(release_basis) is not list
                or prior_release.event_id not in release_basis
            ):
                _schema_error(FailureCode.RELEASE_PREDICATE_CHANGED)
            proof_states[proof_id] = "RELEASED"

        if event.event_type is EventType.RISK_CONTROL_STATE_CHANGED:
            before, after, cause = payload["previous_state"], payload["new_state"], payload["cause"]
            if (
                before not in RISK_CONTROL_STATES or after not in RISK_CONTROL_STATES
                or RISK_CONTROL_TRANSITIONS.get((before, after)) != cause
                or before != risk_state or type(payload["risk_state_epoch_before"]) is not int
                or type(payload["risk_state_epoch_after"]) is not int
                or payload["risk_state_epoch_before"] != risk_epoch
                or payload["risk_state_epoch_after"] != risk_epoch + 1
            ):
                _schema_error(FailureCode.RISK_STATE_TRANSITION_INVALID)
            if payload["risk_config_sha256"] is not None and not _is_sha256(payload["risk_config_sha256"]):
                _schema_error()
            if after in {"SAFE_HELD", "WRITER_ELIGIBLE"} and not _is_sha256(payload["risk_config_sha256"]):
                _schema_error(FailureCode.RISK_STATE_TRANSITION_INVALID)
            expected_predecessor = None if last_state_event is None else last_state_event.event_id
            if payload["predecessor_state_event_id"] != expected_predecessor:
                _schema_error(FailureCode.EVENT_REQUIRED_REFERENCE_INVALID)
            _require_tail(payload, "observed_authority_trusted_sequence", "observed_authority_trusted_hash", previous)
            _require_tail(payload, "observed_ledger_terminal_sequence", "observed_ledger_terminal_hash", previous)
            if active_mode is AcquisitionMode.NORMAL_WRITER and (before, after, cause) != ("WRITER_ELIGIBLE", "HALTED", "HARD_SAFETY_VIOLATION"):
                _schema_error(FailureCode.RESTRICTED_SESSION_EVENT_NOT_PERMITTED)
            if active_mode is AcquisitionMode.RELEASE_ONLY and (before, after, cause) != ("SAFE_HELD", "WRITER_ELIGIBLE", "DURABLE_RELEASE_COMPLETED"):
                _schema_error(FailureCode.RESTRICTED_SESSION_EVENT_NOT_PERMITTED)
            if active_mode is AcquisitionMode.EMERGENCY_CONTROL_ONLY and (after == "WRITER_ELIGIBLE" or before == "WRITER_ELIGIBLE"):
                _schema_error(FailureCode.RESTRICTED_SESSION_EVENT_NOT_PERMITTED)
            action_id = payload["related_emergency_action_id"]
            if (before, after) in {
                ("HALTED", "EMERGENCY_CANCELING"),
                ("RECONCILING", "EMERGENCY_CANCELING"),
                ("EMERGENCY_CANCELING", "RECONCILING"),
            }:
                if not _is_named_id("emergency_action_id", action_id) or action_id not in actions:
                    _schema_error(FailureCode.EVENT_REQUIRED_REFERENCE_INVALID)
            elif action_id is not None:
                _schema_error(FailureCode.EVENT_REQUIRED_REFERENCE_INVALID)
            if after == "WRITER_ELIGIBLE":
                release_id = payload["related_release_id"]
                if not _is_named_id("release_id", release_id) or release_id not in releases:
                    _schema_error(FailureCode.EVENT_REQUIRED_REFERENCE_INVALID)
                released_proof = releases[release_id].payload.get("writer_proof_id")
                if type(released_proof) is not str or proof_states.get(released_proof) != "RELEASED":
                    _schema_error(FailureCode.RELEASE_PREDICATE_CHANGED)
            elif payload["related_release_id"] is not None:
                _schema_error()
            risk_state, risk_epoch, last_state_event = after, risk_epoch + 1, event
        elif event.event_type is EventType.EMERGENCY_ACTION_OPENED:
            action_id = payload["emergency_action_id"]
            targets = _require_sorted_unique_ids(payload["target_order_ids"])
            authoritative_known_orders = set()
            for prior in by_id.values():
                if prior.event_type is not EventType.ORDER_OBSERVED:
                    continue
                canonical_order = prior.payload["canonical_venue_payload"]
                if (
                    type(canonical_order) is dict
                    and canonical_order.get("status") == "resting"
                    and _is_qty2(canonical_order.get("remaining_count_fp"), positive=True)
                ):
                    authoritative_known_orders.add(str(prior.payload["venue_order_id"]))
            if (
                active_mode is not AcquisitionMode.EMERGENCY_CONTROL_ONLY or risk_state != "HALTED"
                or not _is_named_id("emergency_action_id", action_id)
                or type(payload["conflict_domain_ref"]) is not str or not payload["conflict_domain_ref"]
                or payload["starting_control_state"] != "HALTED"
                or payload["cause"] not in {"HARD_RISK_HALT", "EXPLICIT_EMERGENCY_CONTROL", "RESTART_RECOVERY_OF_PERSISTED_HALT"}
                or payload["target_set_kind"] not in {"EXACT_ORDER_ID_SET", "EMPTY"}
                or (payload["target_set_kind"] == "EMPTY") != (targets == [])
                or payload["target_set_sha256"] != sha256_hex(canonical_json_bytes(targets))
                or any(target not in authoritative_known_orders for target in targets)
                or (payload["risk_config_sha256"] is not None and not _is_sha256(payload["risk_config_sha256"]))
                or (last_state_event is not None and payload["risk_config_sha256"] != last_state_event.payload["risk_config_sha256"])
                or type(payload["risk_state_epoch"]) is not int or payload["risk_state_epoch"] != risk_epoch
                or payload["opened_at_utc"] != event.recorded_at_utc
            ):
                _schema_error()
            _require_tail(payload, "authority_trusted_sequence", "authority_trusted_hash", previous)
            _require_tail(payload, "ledger_terminal_sequence", "ledger_terminal_hash", previous)
            dedup_obj = {key: payload[key] for key in ("conflict_domain_ref", "risk_state_epoch", "cause", "target_set_sha256")}
            if payload["deduplication_key_sha256"] != sha256_hex(canonical_json_bytes(dedup_obj)):
                _schema_error()
            dedup = payload["deduplication_key_sha256"]
            if dedup in action_dedup and action_dedup[dedup] != action_id:
                _schema_error(FailureCode.EMERGENCY_ACTION_DUPLICATE_CONFLICT)
            action_dedup[dedup], actions[action_id] = action_id, event
        elif event.event_type is EventType.CANCEL_INTENT_RECORDED:
            action_id, attempt_id, target = payload["emergency_action_id"], payload["cancel_attempt_id"], payload["target_order_id"]
            observation = by_id.get(str(payload["authoritative_order_observation_event_id"]))
            key = (str(action_id), str(target))
            ordinal = payload["attempt_ordinal"]
            previous_attempt = attempt_by_action_target.get(key)
            previous_result = results.get(previous_attempt) if previous_attempt is not None else None
            observed_order = observation.payload["canonical_venue_payload"] if observation is not None and observation.event_type is EventType.ORDER_OBSERVED else None
            if (
                active_mode is not AcquisitionMode.EMERGENCY_CONTROL_ONLY or action_id not in actions
                or not _is_named_id("cancel_attempt_id", attempt_id) or type(target) is not str or not target
                or target not in actions[action_id].payload["target_order_ids"]
                or type(payload["subaccount"]) is not int or not 0 <= payload["subaccount"] <= 63
                or type(payload["exchange_index"]) is not int or payload["exchange_index"] < 0
                or payload["source_binding_id"] != "KSR-02_CANCEL_ORDER_V2_2026-08-13T20:18:41Z"
                or type(payload["risk_state_epoch"]) is not int or payload["risk_state_epoch"] != risk_epoch
                or observation is None or observation.event_type is not EventType.ORDER_OBSERVED
                or observation.event_hash != payload["authoritative_order_observation_event_hash"]
                or observation.payload["venue_order_id"] != target
                or type(observed_order) is not dict
                or observed_order.get("status") != "resting"
                or observed_order.get("remaining_count_fp") != payload["prior_remaining_count_fp"]
                or payload["conflict_domain_ref"] != actions[action_id].payload["conflict_domain_ref"]
                or payload["prior_order_status"] != "resting"
                or not _is_qty2(payload["prior_remaining_count_fp"], positive=True)
                or type(ordinal) is not int or ordinal != intent_ordinals.get(key, 0) + 1
                or (ordinal > 1 and (previous_result is None or previous_result.payload["result_class"] != "CANCEL_REJECTED_CONFIRMED"))
                or not _is_named_id("request_id", payload["request_id"])
                or (payload["risk_config_sha256"] is not None and not _is_sha256(payload["risk_config_sha256"]))
                or payload["risk_config_sha256"] != actions[action_id].payload["risk_config_sha256"]
                or payload["intent_recorded_at_utc"] != event.recorded_at_utc
            ):
                _schema_error(FailureCode.CANCEL_ATTEMPT_PREDECESSOR_INVALID)
            intent_ordinals[key] = ordinal
            attempt_by_action_target[key] = str(attempt_id)
            intents[attempt_id] = event
        elif event.event_type is EventType.CANCEL_SEND_BOUNDARY_ENTERED:
            attempt_id = payload["cancel_attempt_id"]
            intent = intents.get(str(attempt_id))
            if (
                intent is None or attempt_id in boundaries
                or payload["predecessor_intent_event_id"] != intent.event_id
                or payload["predecessor_intent_event_hash"] != intent.event_hash
                or any(payload[key] != intent.payload[key] for key in ("emergency_action_id", "cancel_attempt_id", "target_order_id", "request_id", "attempt_ordinal"))
                or not _is_sha256(payload["canonical_request_sha256"])
                or payload["operation_name"] != "CANCEL_ORDER_V2" or payload["method"] != "DELETE"
                or payload["path_without_query"] != "/trade-api/v2/portfolio/events/orders/" + payload["target_order_id"]
                or not _is_named_id("deadline_id", payload["deadline_id"])
                or not _is_named_id("process_instance_id", payload["deadline_process_instance_id"])
                or type(payload["deadline_budget_ms"]) is not int or payload["deadline_budget_ms"] <= 0
                or type(payload["deadline_started_monotonic_ns"]) is not int or payload["deadline_started_monotonic_ns"] < 0
                or type(payload["deadline_absolute_monotonic_ns"]) is not int
                or payload["deadline_absolute_monotonic_ns"] != payload["deadline_started_monotonic_ns"] + payload["deadline_budget_ms"] * 1_000_000
                or payload["write_ambiguity_rule"] != "CANCEL_MAY_HAVE_BEEN_SENT_AFTER_THIS_ANCHORED_EVENT"
                or payload["boundary_recorded_at_utc"] != event.recorded_at_utc
            ):
                _schema_error(FailureCode.CANCEL_ATTEMPT_PREDECESSOR_INVALID)
            _require_tail(payload, "predecessor_authority_trusted_sequence", "predecessor_authority_trusted_hash", previous)
            _require_tail(payload, "predecessor_ledger_terminal_sequence", "predecessor_ledger_terminal_hash", previous)
            boundaries.add(str(attempt_id))
        elif event.event_type is EventType.CANCEL_RESULT_RECORDED:
            attempt_id = str(payload["cancel_attempt_id"])
            intent = intents.get(attempt_id)
            prior = results.get(attempt_id)
            revision = payload["result_revision"]
            result_class = payload["result_class"]
            if (
                intent is None or type(revision) is not int or revision < 1
                or (revision == 1 and payload["prior_result_event_id"] is not None)
                or (revision > 1 and (prior is None or prior.event_id != payload["prior_result_event_id"] or prior.payload["result_revision"] != revision - 1 or prior.payload["result_class"] != "CANCEL_UNRESOLVED"))
                or any(payload[key] != intent.payload[key] for key in ("emergency_action_id", "cancel_attempt_id", "target_order_id"))
                or result_class not in {"CANCELED_CONFIRMED", "FILLED_BEFORE_CANCEL", "PARTIAL_FILL_THEN_REMAINDER_CANCELED", "ALREADY_TERMINAL", "CANCEL_REJECTED_CONFIRMED", "CANCEL_UNRESOLVED"}
                or type(payload["response_present"]) is not bool or type(payload["unresolved"]) is not bool
                or payload["unresolved"] != (result_class == "CANCEL_UNRESOLVED")
                or payload["write_closure_class"] != ("UNRESOLVED" if payload["unresolved"] else "AUTHORITATIVE_RESULT_CLOSED")
                or payload["result_at_utc"] != event.recorded_at_utc
            ):
                _schema_error(FailureCode.CANCEL_RESULT_REVISION_CONFLICT)
            expected_basis_types = {
                "reconciliation_basis_event_ids": EventType.RECONCILIATION_RECORDED,
                "fill_basis_event_ids": EventType.FILL_OBSERVED,
                "order_state_basis_event_ids": EventType.ORDER_OBSERVED,
            }
            for key, expected_type in expected_basis_types.items():
                ids = _require_sorted_unique_ids(payload[key], event_ids=True)
                if any(item not in by_id or by_id[item].event_type is not expected_type for item in ids):
                    _schema_error(FailureCode.EVENT_REQUIRED_REFERENCE_INVALID)
                if expected_type in {EventType.FILL_OBSERVED, EventType.ORDER_OBSERVED} and any(
                    by_id[item].payload["venue_order_id"] != intent.payload["target_order_id"] for item in ids
                ):
                    _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            response_present = payload["response_present"]
            response_fields = ("response_http_status", "response_media_type_class", "response_body_sha256", "response_byte_length")
            if response_present:
                if (
                    type(payload["response_http_status"]) is not int
                    or not 100 <= payload["response_http_status"] <= 599
                    or payload["response_media_type_class"] not in {"APPLICATION_JSON", "OTHER", "MISSING"}
                    or not _is_sha256(payload["response_body_sha256"])
                    or type(payload["response_byte_length"]) is not int
                    or payload["response_byte_length"] < 0
                ):
                    _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            elif any(payload[key] is not None for key in response_fields + ("response_order_id", "response_reduced_by_fp")):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if payload["response_order_id"] is not None and payload["response_order_id"] != intent.payload["target_order_id"]:
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if payload["response_media_type_class"] != "APPLICATION_JSON" and (payload["response_order_id"] is not None or payload["response_reduced_by_fp"] is not None):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if payload["response_reduced_by_fp"] is not None and not _is_qty2(payload["response_reduced_by_fp"]):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            filled = payload["filled_quantity_fp"]
            canceled = payload["canceled_quantity_fp"]
            remaining = payload["remaining_quantity_fp"]
            if not _is_qty2(filled) or canceled is not None and not _is_qty2(canceled) or remaining is not None and not _is_qty2(remaining):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if result_class == "CANCEL_UNRESOLVED":
                pass
            elif canceled is None or remaining is None or Decimal(intent.payload["prior_remaining_count_fp"]) != Decimal(filled) + Decimal(canceled) + Decimal(remaining):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            elif not payload["order_state_basis_event_ids"] and not payload["fill_basis_event_ids"]:
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if result_class == "CANCELED_CONFIRMED" and not (Decimal(filled) == 0 and Decimal(remaining) == 0 and Decimal(canceled) == Decimal(intent.payload["prior_remaining_count_fp"])):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if result_class == "FILLED_BEFORE_CANCEL" and not (Decimal(filled) == Decimal(intent.payload["prior_remaining_count_fp"]) and Decimal(canceled) == 0 and Decimal(remaining) == 0):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if result_class == "PARTIAL_FILL_THEN_REMAINDER_CANCELED" and not (0 < Decimal(filled) < Decimal(intent.payload["prior_remaining_count_fp"]) and Decimal(remaining) == 0):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if result_class == "CANCEL_REJECTED_CONFIRMED" and not (Decimal(canceled) == 0 and Decimal(remaining) == Decimal(intent.payload["prior_remaining_count_fp"]) - Decimal(filled)):
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            if payload["response_reduced_by_fp"] is not None and result_class in {"CANCELED_CONFIRMED", "PARTIAL_FILL_THEN_REMAINDER_CANCELED"} and payload["response_reduced_by_fp"] != canceled:
                _schema_error(FailureCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
            results[attempt_id] = event
        elif event.event_type is EventType.RISK_RELEASE_RECORDED:
            vector = payload["predicate_vector"]
            state_event = by_id.get(str(payload["safe_held_state_event_id"]))
            if (
                active_mode is not AcquisitionMode.RELEASE_ONLY or risk_state != "SAFE_HELD"
                or not _is_named_id("release_id", payload["release_id"])
                or not _is_sha256(payload["risk_config_sha256"])
                or not _is_sha256(payload["reconciliation_snapshot_sha256"])
                or not _is_sha256(payload["risk_snapshot_sha256"])
                or type(payload["writer_proof_id"]) is not str or not payload["writer_proof_id"]
                or type(payload["risk_state_epoch"]) is not int or payload["risk_state_epoch"] != risk_epoch
                or type(vector) is not dict or set(vector) != _RELEASE_PREDICATE_KEYS
                or any(type(value) is not bool or not value for value in vector.values())
                or payload["predicate_vector_sha256"] != sha256_hex(canonical_json_bytes(vector))
                or state_event is None or state_event is not last_state_event or state_event.event_hash != payload["safe_held_state_event_hash"]
                or state_event.payload["risk_state_epoch_after"] != payload["risk_state_epoch"]
                or state_event.payload["risk_config_sha256"] != payload["risk_config_sha256"]
                or payload["release_recorded_at_utc"] != event.recorded_at_utc
            ):
                _schema_error(FailureCode.RELEASE_PREDICATE_FAILED)
            _require_tail(payload, "authority_trusted_sequence", "authority_trusted_hash", previous)
            _require_tail(payload, "ledger_terminal_sequence", "ledger_terminal_hash", previous)
            releases[str(payload["release_id"])] = event
        by_id[event.event_id] = event


def _validate_event_semantics(events: Sequence[LedgerEvent]) -> None:
    sessions: set[str] = set()
    active_sessions: set[str] = set()
    session_modes: dict[str, AcquisitionMode] = {}
    requests: dict[str, LedgerEvent] = {}
    boundaries: set[str] = set()
    imports: list[int] = []
    intents: set[str] = set()
    for i, event in enumerate(events):
        if event.event_type is EventType.WRITER_SESSION_STARTED:
            _require_exact_payload_keys(event, {"writer_session_id", "session_schema_revision", "lock_model", "prior_session_state"})
            session_id = event.payload["writer_session_id"]
            if (
                event.writer_session_id != session_id
                or type(session_id) is not str
                or _WRITER_SESSION_ID_RE.fullmatch(session_id) is None
                or session_id in sessions
                or active_sessions
                or type(event.payload["session_schema_revision"]) is not int
                or event.payload["session_schema_revision"] != 1
                or event.payload["lock_model"] != LOCK_MODEL
                or event.payload["prior_session_state"] not in {"NONE", "CLEAN", "ABNORMAL"}
            ):
                raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
            sessions.add(session_id)
            active_sessions.add(session_id)
            session_modes[session_id] = AcquisitionMode.NORMAL_WRITER
        elif event.event_type is EventType.RESTRICTED_SESSION_STARTED:
            session_id = event.payload.get("restricted_session_id")
            mode_value = event.payload.get("acquisition_mode")
            try:
                mode = AcquisitionMode(mode_value)
            except (TypeError, ValueError) as exc:
                raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT) from exc
            if (
                type(session_id) is not str
                or _RESTRICTED_SESSION_ID_RE.fullmatch(session_id) is None
                or event.writer_session_id != session_id
                or session_id in sessions
                or active_sessions
                or mode not in {AcquisitionMode.EMERGENCY_CONTROL_ONLY, AcquisitionMode.RELEASE_ONLY}
            ):
                raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            sessions.add(session_id)
            active_sessions.add(session_id)
            session_modes[session_id] = mode
        elif event.event_type in {EventType.WRITER_SESSION_ENDED, EventType.EXECUTION_INTENT_RECORDED, EventType.REQUEST_PREPARED, EventType.WRITE_SEND_BOUNDARY_ENTERED, EventType.READ_SEND_BOUNDARY_ENTERED, EventType.HTTP_RESPONSE_CLASSIFIED, EventType.TRANSPORT_UNKNOWN_AFTER_SEND, EventType.ORDER_IDENTITY_BOUND, EventType.ORDER_OBSERVED, EventType.FILL_OBSERVED, EventType.RECONCILIATION_RECORDED, EventType.EXECUTION_HALTED, EventType.EXECUTION_TERMINAL, EventType.WRITER_PROOF_RELEASED}:
            if event.writer_session_id is None or event.writer_session_id not in active_sessions:
                raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
        if event.event_type is EventType.WRITER_SESSION_ENDED:
            _require_exact_payload_keys(event, {"writer_session_id"})
            if event.payload["writer_session_id"] != event.writer_session_id:
                raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
            active_sessions.remove(event.writer_session_id)
        if event.event_type is EventType.RESTRICTED_SESSION_ENDED:
            session_id = event.payload.get("restricted_session_id")
            if type(session_id) is not str or session_id not in active_sessions or event.writer_session_id != session_id:
                raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            active_sessions.remove(session_id)
        if event.event_type is EventType.RESTRICTED_SESSION_ABANDONED:
            abandoned_restricted = event.payload.get("abandoned_restricted_session_id")
            if type(abandoned_restricted) is not str or abandoned_restricted not in active_sessions:
                raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
            active_sessions.remove(abandoned_restricted)
        if event.event_type is EventType.WRITER_SESSION_ABANDONED:
            _require_exact_payload_keys(event, {"abandoned_writer_session_id", "reason"})
            abandoned = event.payload["abandoned_writer_session_id"]
            if (
                type(abandoned) is not str
                or abandoned not in active_sessions
                or event.payload["reason"] != "PREVIOUS_SESSION_NO_LONGER_HOLDS_REQUIRED_AUTHORITY_AND_LEDGER_LOCKS"
            ):
                raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
            active_sessions.remove(abandoned)
        if event.event_type is EventType.EXECUTION_INTENT_RECORDED:
            _require_exact_payload_keys(event, {
                "execution_attempt_id", "venue", "environment", "conflict_domain_ref",
                "incident_id", "operation_family", "client_order_id",
                "capability_reference_id", "intent_payload_schema_id", "intent_payload",
            })
            if event.execution_attempt_id != event.payload["execution_attempt_id"] or event.incident_id != event.payload["incident_id"]:
                raise LedgerError(FailureCode.EVENT_REQUIRED_PARENT_MISSING)
            intents.add(str(event.execution_attempt_id))
        if event.event_type is EventType.REQUEST_PREPARED:
            _require_exact_payload_keys(event, {"request_id", "operation_class", "venue", "environment", "operation_name", "method", "path_without_query", "canonical_query", "canonical_query_sha256", "canonical_body", "canonical_body_sha256", "prepared_request_sha256", "client_order_id", "venue_order_id", "idempotency_key", "adapter_payload_schema_id"})
            if event.execution_attempt_id not in intents:
                raise LedgerError(FailureCode.EVENT_REQUIRED_PARENT_MISSING)
            request_id = event.payload["request_id"]
            if type(request_id) is not str or request_id in requests:
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            if sha256_hex(canonical_json_bytes(event.payload["canonical_query"])) != event.payload["canonical_query_sha256"]:
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            body = event.payload["canonical_body"]
            body_hash = None if body is None else sha256_hex(canonical_json_bytes(body))
            if body_hash != event.payload["canonical_body_sha256"]:
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            request_identity = dict(event.payload)
            supplied_prepared_hash = request_identity.pop("prepared_request_sha256")
            if sha256_hex(canonical_json_bytes(request_identity)) != supplied_prepared_hash:
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            if event.payload["operation_class"] not in {"READ", "WRITE"}:
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            requests[request_id] = event
        if event.event_type in {EventType.WRITE_SEND_BOUNDARY_ENTERED, EventType.READ_SEND_BOUNDARY_ENTERED}:
            expected_keys = {"request_id", "operation_name", "prepared_request_sha256"}
            if event.event_type is EventType.WRITE_SEND_BOUNDARY_ENTERED:
                expected_keys.add("write_ambiguity_rule")
            _require_exact_payload_keys(event, expected_keys)
            request_id = event.payload["request_id"]
            if request_id not in requests or request_id in boundaries or requests[request_id].payload["prepared_request_sha256"] != event.payload["prepared_request_sha256"]:
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            if event.event_type is EventType.WRITE_SEND_BOUNDARY_ENTERED and event.payload["write_ambiguity_rule"] != "WRITE_MAY_HAVE_BEEN_SENT_AFTER_THIS_COMMIT":
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            boundaries.add(request_id)
        if event.event_type in {EventType.HTTP_RESPONSE_CLASSIFIED, EventType.TRANSPORT_UNKNOWN_AFTER_SEND}:
            request_id = event.payload.get("request_id")
            if request_id not in boundaries:
                raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            if event.event_type is EventType.HTTP_RESPONSE_CLASSIFIED:
                _require_exact_payload_keys(event, {"request_id", "http_status", "response_media_type", "response_byte_length", "response_sha256", "adapter_result_class", "write_closure_class", "validated_identity_fields"})
                if (
                    type(event.payload["http_status"]) is not int
                    or type(event.payload["response_byte_length"]) is not int
                    or event.payload["http_status"] < 100
                    or event.payload["http_status"] > 599
                    or event.payload["response_byte_length"] < 0
                    or event.payload["write_closure_class"] not in {"NOT_APPLICABLE", "UNRESOLVED", "NO_SEND_PROVEN", "AUTHORITATIVE_RESULT_CLOSED"}
                ):
                    raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
            else:
                _require_exact_payload_keys(event, {"request_id", "unknown_class", "write_closure_class"})
                if event.payload["unknown_class"] != "TRANSPORT_RESULT_UNKNOWN_AFTER_SEND" or event.payload["write_closure_class"] != "UNRESOLVED":
                    raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
        if event.event_type is EventType.ORDER_IDENTITY_BOUND:
            _require_exact_payload_keys(event, {"client_order_id", "venue_order_id", "venue", "environment", "incident_id", "binding_basis_event_ids"})
            if event.incident_id != event.payload["incident_id"]:
                raise LedgerError(FailureCode.EVENT_REQUIRED_PARENT_MISSING)
        if event.event_type is EventType.ORDER_OBSERVED:
            _require_exact_payload_keys(event, {"venue_order_id", "client_order_id", "source_request_id", "source_operation", "venue_payload_schema_id", "canonical_venue_payload", "canonical_venue_payload_sha256", "observation_semantic_class"})
            if sha256_hex(_canonical_stored_json_bytes(event.payload["canonical_venue_payload"])) != event.payload["canonical_venue_payload_sha256"]:
                raise LedgerError(FailureCode.LEDGER_HASH_CHAIN_FAILURE)
        if event.event_type is EventType.FILL_OBSERVED:
            _require_exact_payload_keys(event, {"venue_fill_id", "venue_order_id", "client_order_id", "source_request_id", "source_operation", "venue_payload_schema_id", "canonical_venue_payload", "canonical_venue_payload_sha256"})
            if sha256_hex(_canonical_stored_json_bytes(event.payload["canonical_venue_payload"])) != event.payload["canonical_venue_payload_sha256"]:
                raise LedgerError(FailureCode.LEDGER_HASH_CHAIN_FAILURE)
        if event.event_type is EventType.RECONCILIATION_RECORDED:
            _require_exact_payload_keys(event, {"incident_id", "disposition", "write_closure_class", "bound_order_id", "created_order_upper_bound", "active_order_upper_bound", "unknown_result", "writer_proof_release_eligible", "basis_event_ids", "adapter_reconciliation_schema_id"})
            if (
                event.incident_id != event.payload["incident_id"]
                or type(event.payload["created_order_upper_bound"]) is not int
                or type(event.payload["active_order_upper_bound"]) is not int
                or type(event.payload["unknown_result"]) is not bool
                or type(event.payload["writer_proof_release_eligible"]) is not bool
                or event.payload["write_closure_class"] not in {"NOT_APPLICABLE", "UNRESOLVED", "NO_SEND_PROVEN", "AUTHORITATIVE_RESULT_CLOSED"}
            ):
                raise LedgerError(FailureCode.EVENT_REQUIRED_PARENT_MISSING)
        if event.event_type is EventType.WRITER_PROOF_HELD:
            _require_exact_payload_keys(event, {"writer_proof_id", "conflict_domain_ref", "held_reason", "protected_unresolved_write_event_ids"})
        if event.event_type is EventType.WRITER_PROOF_RELEASED:
            _require_exact_payload_keys(event, {"writer_proof_id", "conflict_domain_ref", "release_basis_event_ids", "release_contract_id"})
        if event.event_type is EventType.LEGACY_INCIDENT_IMPORTED:
            imports.append(i)
            if event.writer_session_id is not None or event.incident_id is None or event.execution_attempt_id is not None:
                raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
            if i + 1 >= len(events) or events[i + 1].event_type is not EventType.WRITER_PROOF_HELD:
                raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_INCOMPLETE)
            hold = events[i + 1]
            if hold.writer_session_id is not None or hold.incident_id != event.incident_id or hold.execution_attempt_id is not None or hold.payload.get("held_reason") != "PROTECTED_UNRESOLVED_LEGACY_WRITE" or hold.payload.get("protected_unresolved_write_event_ids") != [event.event_id]:
                raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
    if len(imports) > 1:
        raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
    _validate_spec03_event_sequence(events, session_modes)


def initialize_ledger_binding(
    binding: AuthorityNamespaceBinding,
    *,
    conflict_domain_ref: str,
    environment_classification: str,
    ledger_path: str | os.PathLike[str],
    canonical_repository_root: str | os.PathLike[str],
    preledger_history_mode: str = PRELEDGER_HISTORY_MODE,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
    fault_hook: FaultHook = _noop_fault_hook,
) -> AuthorityRow:
    conflict = _require_canonical_text(conflict_domain_ref)
    environment = _require_canonical_text(environment_classification)
    if preledger_history_mode != PRELEDGER_HISTORY_MODE:
        raise LedgerError(FailureCode.PRELEDGER_EMPTY_ASSERTION_UNSUPPORTED)
    repository_root = Path(canonical_repository_root).resolve(strict=True)
    ledger_resolved, ledger_normalized, ledger_identity = path_identity(ledger_path, must_exist=False)
    if _is_within(ledger_resolved, repository_root):
        raise LedgerError(FailureCode.LEDGER_PATH_INSIDE_CANONICAL_REPOSITORY)
    if ledger_resolved.exists():
        raise LedgerError(FailureCode.LEDGER_ALREADY_EXISTS)
    authority = _connect_existing(binding.authority_store_resolved_path, authority=True)
    ledger: sqlite3.Connection | None = None
    try:
        authority.execute("BEGIN EXCLUSIVE")
        authority_meta = _validate_authority_open(authority, binding)
        if authority.execute("SELECT 1 FROM conflict_domain_authority WHERE conflict_domain_ref=?", (conflict,)).fetchone() is not None:
            raise LedgerError(FailureCode.AUTHORITY_CONFLICT_DOMAIN_ALREADY_BOUND)
        ledger = _connect_new(ledger_resolved, authority=False)
        ledger.executescript("BEGIN EXCLUSIVE;\n" + _LEDGER_SCHEMA)
        ledger_instance = str(uuid_factory())
        _uuid4_text(ledger_instance)
        created = canonical_timestamp(clock())
        ledger.execute("INSERT INTO ledger_meta VALUES (1,?,?,?,?,?,?,?,?,?,?)", (ledger_instance, 1, created, environment, conflict, PRELEDGER_HISTORY_MODE, authority_meta.authority_instance_id, binding.authority_namespace_id, binding.authority_store_path_identity_sha256, ledger_identity))
        meta = _ledger_meta(ledger)
        initial = _construct_event(meta=meta, sequence=1, previous_hash=ZERO_HASH, event_input=EventInput(EventType.LEDGER_INITIALIZED, {
            "authority_instance_id": authority_meta.authority_instance_id,
            "authority_namespace_id": binding.authority_namespace_id,
            "authority_store_path_identity_sha256": binding.authority_store_path_identity_sha256,
            "conflict_domain_ref": conflict,
            "created_at_utc": created,
            "environment_classification": environment,
            "ledger_instance_id": ledger_instance,
            "ledger_path_identity_sha256": ledger_identity,
            "ledger_schema_revision": 1,
            "preledger_history_mode": PRELEDGER_HISTORY_MODE,
        }), clock=clock, uuid_factory=uuid_factory)
        _insert_event(ledger, initial)
        fault_hook("before_ledger_initialization_commit")
        ledger.commit()
        fault_hook("after_ledger_initialization_commit")
        _validate_schema(ledger, authority=False)
        _validate_integrity(ledger, authority=False)
        load_and_validate_events(ledger, meta)
        updated = canonical_timestamp(clock())
        authority.execute("INSERT INTO conflict_domain_authority VALUES (?,?,?,?,?,?,?,?)", (conflict, environment, ledger_instance, ledger_normalized, ledger_identity, 1, initial.event_hash, updated))
        fault_hook("before_authority_binding_commit")
        authority.commit()
        fault_hook("after_authority_binding_commit")
        row = _authority_row(authority, conflict)
        if row.trusted_sequence != 1 or row.trusted_event_hash != initial.event_hash:
            raise LedgerError(FailureCode.AUTHORITY_LEDGER_INITIALIZATION_PARTIAL_FAILURE)
        return row
    except CommitResultUnknown:
        raise
    except LedgerError:
        if ledger is not None and ledger.in_transaction:
            ledger.rollback()
        if authority.in_transaction:
            authority.rollback()
        raise
    except sqlite3.Error as exc:
        if ledger is not None and ledger.in_transaction:
            ledger.rollback()
        if authority.in_transaction:
            authority.rollback()
        if ledger_resolved.exists():
            raise LedgerError(FailureCode.AUTHORITY_LEDGER_INITIALIZATION_PARTIAL_FAILURE) from exc
        raise LedgerError(FailureCode.LEDGER_COMMIT_FAILURE) from exc
    finally:
        if ledger is not None:
            ledger.close()
        authority.close()


def _insert_event(connection: sqlite3.Connection, event: LedgerEvent) -> None:
    connection.execute(
        "INSERT INTO ledger_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event.sequence, event.event_id, event.ledger_instance_id, event.event_type.value,
         event.event_schema_revision, event.writer_session_id, event.incident_id,
         event.execution_attempt_id, event.recorded_at_utc, event.payload_json,
         event.payload_sha256, event.previous_event_hash, event.event_hash),
    )


def _classify_error(error: LedgerError) -> RestartClassification:
    if error.code in {
        FailureCode.AUTHORITY_STORE_MISSING, FailureCode.AUTHORITY_STORAGE_OPEN_FAILURE,
        FailureCode.AUTHORITY_DURABILITY_CONFIGURATION_FAILURE, FailureCode.AUTHORITY_SCHEMA_IDENTITY_MISMATCH,
        FailureCode.AUTHORITY_INTEGRITY_CHECK_FAILURE, FailureCode.AUTHORITY_IDENTITY_MISMATCH,
        FailureCode.AUTHORITY_CONFLICT_DOMAIN_BINDING_MISSING, FailureCode.AUTHORITY_ANCHOR_CATCHUP_FAILURE,
    }:
        return RestartClassification.AUTHORITY_INTEGRITY_FAILURE
    if error.code is FailureCode.AUTHORITY_AHEAD_OF_LEDGER_ROLLBACK_OR_REPLACEMENT:
        return RestartClassification.AUTHORITY_LEDGER_ROLLBACK_FAILURE
    if error.code in {FailureCode.LEDGER_CONCURRENT_WRITER}:
        return RestartClassification.CONCURRENT_WRITER_BLOCKED
    if error.code in {FailureCode.LEDGER_FILE_MISSING, FailureCode.LEDGER_INSTANCE_ID_MISMATCH, FailureCode.LEDGER_ENVIRONMENT_MISMATCH, FailureCode.LEDGER_CONFLICT_DOMAIN_MISMATCH, FailureCode.LEDGER_AUTHORITY_BINDING_MISMATCH}:
        return RestartClassification.LEDGER_IDENTITY_FAILURE
    if error.code in {FailureCode.AUTHORITY_SCHEMA_UNSUPPORTED_NEWER, FailureCode.AUTHORITY_SCHEMA_UNSUPPORTED_OLDER, FailureCode.LEDGER_SCHEMA_UNSUPPORTED_NEWER, FailureCode.LEDGER_SCHEMA_UNSUPPORTED_OLDER, FailureCode.LEDGER_SCHEMA_UNSUPPORTED_EVENT_TYPE}:
        return RestartClassification.SCHEMA_UNSUPPORTED
    return RestartClassification.LEDGER_INTEGRITY_FAILURE


class LockedLedger:
    """Internal authority-first, ledger-second locked local state."""

    def __init__(
        self, binding: AuthorityNamespaceBinding, conflict_domain_ref: str,
        authority: sqlite3.Connection, ledger: sqlite3.Connection,
        authority_meta: AuthorityMeta, authority_row: AuthorityRow, ledger_meta: LedgerMeta,
        events: tuple[LedgerEvent, ...], relation: AuthorityLedgerRelation,
        *, clock: Clock, uuid_factory: UuidFactory, fault_hook: FaultHook,
    ) -> None:
        self.binding = binding
        self.conflict_domain_ref = conflict_domain_ref
        self.authority = authority
        self.ledger = ledger
        self.authority_meta = authority_meta
        self.authority_row = authority_row
        self.ledger_meta = ledger_meta
        self.events = events
        self.relation = relation
        self.clock = clock
        self.uuid_factory = uuid_factory
        self.fault_hook = fault_hook
        self.closed = False

    def close(self) -> None:
        if self.closed:
            return
        self.ledger.close()
        self.authority.close()
        self.closed = True

    def projection(self) -> SafetyProjection:
        return replay_projection(self.authority_meta, self.authority_row, self.ledger_meta, self.events)

    def append_batch(self, inputs: Sequence[EventInput]) -> AppendResult:
        if self.closed or not inputs:
            raise LedgerError(FailureCode.LEDGER_COMMIT_FAILURE)
        if self.authority_row.trusted_sequence != self.events[-1].sequence or self.authority_row.trusted_event_hash != self.events[-1].event_hash:
            raise LedgerError(FailureCode.AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH)
        if any(item.event_type is EventType.WRITER_PROOF_RELEASED for item in inputs):
            projection = self.projection()
            if len(inputs) != 1:
                raise LedgerError(FailureCode.EVENT_REQUIRED_PARENT_MISSING)
            item = inputs[0]
            proof_id = item.payload.get("writer_proof_id")
            release_basis = item.payload.get("release_basis_event_ids")
            prior = self.events[-1]
            prior_payload = prior.payload
            active_restricted = projection.active_restricted_session_id
            if (
                type(proof_id) is not str
                or projection.writer_proof_state_by_proof_id.get(proof_id) != "HELD"
                or projection.writer_proof_release_eligible_by_proof_id.get(proof_id) is not True
                or projection.unresolved_write_request_ids
                or projection.protected_unresolved_legacy_write_count != 0
                or any(projection.cancel_send_may_have_been_sent_by_attempt.values())
                or active_restricted is None
                or projection.restricted_session_modes.get(active_restricted) is not AcquisitionMode.RELEASE_ONLY
                or item.writer_session_id != active_restricted
                or prior.event_type is not EventType.RISK_RELEASE_RECORDED
                or prior.writer_session_id != active_restricted
                or prior_payload.get("writer_proof_id") != proof_id
                or type(release_basis) is not list
                or prior.event_id not in release_basis
                or item.payload.get("conflict_domain_ref") != self.conflict_domain_ref
            ):
                raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        duplicates: list[LedgerEvent] = []
        existing_by_id = {event.event_id: event for event in self.events}
        if all(item.event_id is not None and item.event_id in existing_by_id for item in inputs):
            for item in inputs:
                existing = existing_by_id[item.event_id]
                candidate = _construct_event(meta=self.ledger_meta, sequence=existing.sequence, previous_hash=existing.previous_event_hash, event_input=item, clock=self.clock, uuid_factory=self.uuid_factory)
                if _event_core(candidate) != _event_core(existing) or candidate.event_hash != existing.event_hash:
                    raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
                duplicates.append(existing)
            return AppendResult(AppendStatus.IDEMPOTENT_DUPLICATE, duplicates[0].sequence, duplicates[-1].sequence, duplicates[-1].event_hash, tuple(duplicates))
        if any(item.event_id is not None and item.event_id in existing_by_id for item in inputs):
            raise LedgerError(FailureCode.EVENT_ID_CONTENT_CONFLICT)
        built: list[LedgerEvent] = []
        sequence = self.events[-1].sequence
        previous = self.events[-1].event_hash
        for item in inputs:
            sequence += 1
            event = _construct_event(
                meta=self.ledger_meta, sequence=sequence, previous_hash=previous,
                event_input=item, clock=self.clock, uuid_factory=self.uuid_factory,
            )
            built.append(event)
            previous = event.event_hash
        # All application/event/batch semantics are checked before the first
        # row is inserted so any such failure leaves zero batch rows.
        proposed_events = self.events + tuple(built)
        _validate_event_semantics(proposed_events)
        # Projection-level identity/deduplication conflicts are likewise
        # validated before the ledger transaction begins.
        replay_projection(
            self.authority_meta, self.authority_row, self.ledger_meta,
            proposed_events,
        )
        try:
            self.ledger.execute("BEGIN IMMEDIATE")
            for event in built:
                _insert_event(self.ledger, event)
            self.fault_hook("before_ledger_commit")
            self.ledger.commit()
            self.fault_hook("after_ledger_commit")
        except CommitResultUnknown:
            self.close()
            raise LedgerError(FailureCode.LEDGER_COMMIT_RESULT_UNKNOWN)
        except (sqlite3.Error, LedgerError) as exc:
            if self.ledger.in_transaction:
                self.ledger.rollback()
            if isinstance(exc, LedgerError):
                raise
            raise LedgerError(FailureCode.LEDGER_COMMIT_FAILURE) from exc
        new_events = self.events + tuple(built)
        old_row = self.authority_row
        try:
            self.authority.execute("BEGIN IMMEDIATE")
            current = _authority_row(self.authority, self.conflict_domain_ref)
            if current.trusted_sequence != old_row.trusted_sequence or current.trusted_event_hash != old_row.trusted_event_hash:
                raise LedgerError(FailureCode.AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH)
            self.authority.execute("UPDATE conflict_domain_authority SET trusted_sequence=?,trusted_event_hash=?,updated_at_utc=? WHERE conflict_domain_ref=?", (built[-1].sequence, built[-1].event_hash, canonical_timestamp(self.clock()), self.conflict_domain_ref))
            self.fault_hook("before_authority_commit")
            self.authority.commit()
            self.fault_hook("after_authority_commit")
        except CommitResultUnknown:
            self.close()
            raise LedgerError(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
        except (sqlite3.Error, LedgerError) as exc:
            if self.authority.in_transaction:
                self.authority.rollback()
            self.close()
            if isinstance(exc, LedgerError) and exc.code is FailureCode.AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH:
                raise
            raise LedgerError(FailureCode.AUTHORITY_ANCHOR_COMMIT_FAILURE) from exc
        row = _authority_row(self.authority, self.conflict_domain_ref)
        ledger_tail = self.ledger.execute("SELECT sequence,event_hash FROM ledger_events ORDER BY sequence DESC LIMIT 1").fetchone()
        if (row.trusted_sequence, row.trusted_event_hash) != (built[-1].sequence, built[-1].event_hash) or ledger_tail != (built[-1].sequence, built[-1].event_hash):
            self.close()
            raise LedgerError(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
        self.events = new_events
        self.authority_row = row
        return AppendResult(AppendStatus.APPENDED_AND_ANCHORED, built[0].sequence, built[-1].sequence, built[-1].event_hash, tuple(built))


def _open_locked(
    binding: AuthorityNamespaceBinding,
    *, conflict_domain_ref: str,
    expected_environment: str,
    canonical_repository_root: str | os.PathLike[str],
    expected_ledger_path: str | os.PathLike[str] | None = None,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
    fault_hook: FaultHook = _noop_fault_hook,
    history_validator: HistoryValidator | None = None,
) -> LockedLedger:
    conflict = _require_canonical_text(conflict_domain_ref)
    environment = _require_canonical_text(expected_environment)
    authority: sqlite3.Connection | None = None
    ledger: sqlite3.Connection | None = None
    try:
        authority = _connect_existing(binding.authority_store_resolved_path, authority=True)
        authority.execute("BEGIN EXCLUSIVE")
        meta = _validate_authority_open(authority, binding)
        row = _authority_row(authority, conflict)
        if row.environment_classification != environment:
            raise LedgerError(FailureCode.LEDGER_ENVIRONMENT_MISMATCH)
        ledger_path = Path(row.ledger_resolved_path)
        if not ledger_path.exists():
            raise LedgerError(FailureCode.LEDGER_FILE_MISSING)
        repository_root = Path(canonical_repository_root).resolve(strict=True)
        resolved, normalized, identity = path_identity(ledger_path, must_exist=True)
        if _is_within(resolved, repository_root):
            raise LedgerError(FailureCode.LEDGER_PATH_INSIDE_CANONICAL_REPOSITORY)
        if normalized != row.ledger_resolved_path or identity != row.ledger_path_identity_sha256:
            raise LedgerError(FailureCode.LEDGER_AUTHORITY_BINDING_MISMATCH)
        if expected_ledger_path is not None:
            _, expected_normalized, expected_identity = path_identity(expected_ledger_path, must_exist=True)
            if expected_normalized != normalized or expected_identity != identity:
                raise LedgerError(FailureCode.LEDGER_AUTHORITY_BINDING_MISMATCH)
        ledger = _connect_existing(resolved, authority=False)
        ledger.execute("BEGIN EXCLUSIVE")
        _validate_schema(ledger, authority=False)
        ledger_meta = _ledger_meta(ledger)
        if ledger_meta.ledger_instance_id != row.ledger_instance_id:
            raise LedgerError(FailureCode.LEDGER_INSTANCE_ID_MISMATCH)
        if ledger_meta.environment_classification != environment:
            raise LedgerError(FailureCode.LEDGER_ENVIRONMENT_MISMATCH)
        if ledger_meta.conflict_domain_ref != conflict:
            raise LedgerError(FailureCode.LEDGER_CONFLICT_DOMAIN_MISMATCH)
        if ledger_meta.authority_instance_id != meta.authority_instance_id or ledger_meta.authority_namespace_id != binding.authority_namespace_id or ledger_meta.authority_store_path_identity_sha256 != binding.authority_store_path_identity_sha256 or ledger_meta.ledger_path_identity_sha256 != identity:
            raise LedgerError(FailureCode.LEDGER_AUTHORITY_BINDING_MISMATCH)
        _validate_integrity(ledger, authority=False)
        events = load_and_validate_events(ledger, ledger_meta)
        tail = events[-1]
        if row.trusted_sequence > tail.sequence:
            raise LedgerError(FailureCode.AUTHORITY_AHEAD_OF_LEDGER_ROLLBACK_OR_REPLACEMENT)
        if events[row.trusted_sequence - 1].event_hash != row.trusted_event_hash:
            raise LedgerError(FailureCode.AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH)
        # Catch-up is a trust mutation.  Complete generic replay and any
        # venue-bound history validation must therefore succeed over the full
        # observed history before the authority row can move forward.
        replay_projection(meta, row, ledger_meta, events)
        if history_validator is not None:
            history_validator(events)
        relation = AuthorityLedgerRelation.EQUAL
        if row.trusted_sequence < tail.sequence:
            relation = AuthorityLedgerRelation.LEDGER_AHEAD
            try:
                authority.execute("UPDATE conflict_domain_authority SET trusted_sequence=?,trusted_event_hash=?,updated_at_utc=? WHERE conflict_domain_ref=?", (tail.sequence, tail.event_hash, canonical_timestamp(clock()), conflict))
                fault_hook("before_authority_catchup_commit")
                authority.commit()
                fault_hook("after_authority_catchup_commit")
                row = _authority_row(authority, conflict)
            except (sqlite3.Error, LedgerError) as exc:
                if authority.in_transaction:
                    authority.rollback()
                raise LedgerError(FailureCode.AUTHORITY_ANCHOR_CATCHUP_FAILURE) from exc
            if (row.trusted_sequence, row.trusted_event_hash) != (tail.sequence, tail.event_hash):
                raise LedgerError(FailureCode.AUTHORITY_ANCHOR_CATCHUP_FAILURE)
        else:
            authority.commit()
        ledger.commit()
        return LockedLedger(binding, conflict, authority, ledger, meta, row, ledger_meta, events, relation, clock=clock, uuid_factory=uuid_factory, fault_hook=fault_hook)
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
        if ledger is not None:
            ledger.close()
        if authority is not None:
            authority.close()
        if getattr(exc, "sqlite_errorcode", None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise LedgerError(FailureCode.LEDGER_CONCURRENT_WRITER) from exc
        if getattr(exc, "sqlite_errorcode", None) in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
            raise LedgerError(FailureCode.LEDGER_INTEGRITY_CHECK_FAILURE) from exc
        raise LedgerError(FailureCode.LEDGER_STORAGE_OPEN_FAILURE) from exc
    except Exception:
        if ledger is not None:
            ledger.close()
        if authority is not None:
            authority.close()
        raise


def replay_projection(authority_meta: AuthorityMeta, authority_row: AuthorityRow, ledger_meta: LedgerMeta, events: Sequence[LedgerEvent]) -> SafetyProjection:
    sessions: list[str] = []
    open_sessions: set[str] = set()
    abnormal: list[str] = []
    incidents: set[str] = set()
    attempts: set[str] = set()
    prepared: dict[str, Mapping[str, object]] = {}
    boundaries: dict[str, Mapping[str, object]] = {}
    closures: dict[str, str] = {}
    unresolved: set[str] = set()
    bindings: dict[str, str] = {}
    order_history: dict[str, list[Mapping[str, object]]] = {}
    fills: dict[str, Mapping[str, object]] = {}
    fill_conflicts: list[str] = []
    reconciliation: dict[str, str] = {}
    legacy_states: dict[str, Mapping[str, object]] = {}
    proofs: dict[str, str] = {}
    proof_eligible: dict[str, bool] = {}
    proof_incident: dict[str, str | None] = {}
    imported_incident_ids: set[str] = set()
    restricted_sessions: list[str] = []
    restricted_modes: dict[str, AcquisitionMode] = {}
    open_restricted: set[str] = set()
    abnormal_restricted: list[str] = []
    risk_state = "BOOT_HOLD"
    risk_epoch = 0
    active_risk_config: str | None = None
    emergency_actions: dict[str, Mapping[str, object]] = {}
    cancel_attempts: dict[str, Mapping[str, object]] = {}
    cancel_may_sent: dict[str, bool] = {}
    cancel_result_revision: dict[str, int] = {}
    release_records: dict[str, Mapping[str, object]] = {}
    for event in events:
        if event.incident_id is not None:
            incidents.add(event.incident_id)
        if event.execution_attempt_id is not None:
            attempts.add(event.execution_attempt_id)
        payload = event.payload
        if event.event_type is EventType.WRITER_SESSION_STARTED:
            sid = str(payload["writer_session_id"])
            sessions.append(sid); open_sessions.add(sid)
        elif event.event_type is EventType.WRITER_SESSION_ENDED and event.writer_session_id is not None:
            open_sessions.discard(event.writer_session_id)
        elif event.event_type is EventType.WRITER_SESSION_ABANDONED:
            sid = payload.get("abandoned_writer_session_id")
            if type(sid) is str:
                abnormal.append(sid); open_sessions.discard(sid)
        elif event.event_type is EventType.REQUEST_PREPARED:
            prepared[str(payload["request_id"])] = payload
        elif event.event_type is EventType.WRITE_SEND_BOUNDARY_ENTERED:
            request = str(payload["request_id"]); boundaries[request] = payload; unresolved.add(request)
        elif event.event_type is EventType.HTTP_RESPONSE_CLASSIFIED:
            request = str(payload["request_id"]); closure = str(payload["write_closure_class"]); closures[request] = closure
            if closure in {"NO_SEND_PROVEN", "AUTHORITATIVE_RESULT_CLOSED"}:
                unresolved.discard(request)
        elif event.event_type is EventType.TRANSPORT_UNKNOWN_AFTER_SEND:
            request = str(payload["request_id"]); closures[request] = "UNRESOLVED"; unresolved.add(request)
        elif event.event_type is EventType.ORDER_IDENTITY_BOUND:
            client = str(payload["client_order_id"]); venue = str(payload["venue_order_id"])
            if client in bindings and bindings[client] != venue:
                raise LedgerError(FailureCode.ORDER_IDENTITY_BINDING_CONFLICT)
            bindings[client] = venue
        elif event.event_type is EventType.ORDER_OBSERVED:
            venue = str(payload["venue_order_id"]); order_history.setdefault(venue, []).append(payload)
        elif event.event_type is EventType.FILL_OBSERVED:
            fill_id = str(payload["venue_fill_id"]); canonical_payload = payload["canonical_venue_payload"]
            if fill_id in fills and fills[fill_id] != canonical_payload:
                fill_conflicts.append(fill_id)
                raise LedgerError(FailureCode.DUPLICATE_FILL_CONFLICT)
            fills[fill_id] = canonical_payload
        elif event.event_type is EventType.RECONCILIATION_RECORDED:
            incident = str(payload["incident_id"])
            reconciliation[incident] = str(payload["disposition"])
            if payload["writer_proof_release_eligible"] is True:
                for proof, held_incident in proof_incident.items():
                    if held_incident == incident and proofs.get(proof) == "HELD":
                        proof_eligible[proof] = True
        elif event.event_type is EventType.WRITER_PROOF_HELD:
            proof = str(payload["writer_proof_id"])
            proofs[proof] = "HELD"
            proof_eligible[proof] = False
            proof_incident[proof] = event.incident_id
        elif event.event_type is EventType.WRITER_PROOF_RELEASED:
            proof = str(payload["writer_proof_id"]); proofs[proof] = "RELEASED"; proof_eligible[proof] = True
        elif event.event_type is EventType.LEGACY_INCIDENT_IMPORTED:
            imported_incident_ids.add(str(payload["incident_id"]))
            reconciliation[str(payload["incident_id"])] = str(payload["final_disposition"])
            legacy_states[str(payload["incident_id"])] = MappingProxyType({
                "active_order_upper_bound": payload["active_order_upper_bound"],
                "bound_order_id": payload["bound_order_id"],
                "created_order_upper_bound": payload["created_order_upper_bound"],
                "disposition": payload["final_disposition"],
                "unknown_result": payload["unknown_result"],
                "writer_proof_release_eligible": payload["writer_proof_release_eligible"],
                "writer_proof_state": payload["writer_proof_state"],
            })
        elif event.event_type is EventType.RESTRICTED_SESSION_STARTED:
            sid = str(payload["restricted_session_id"])
            restricted_sessions.append(sid)
            restricted_modes[sid] = AcquisitionMode(payload["acquisition_mode"])
            open_restricted.add(sid)
        elif event.event_type is EventType.RESTRICTED_SESSION_ENDED:
            open_restricted.discard(str(payload["restricted_session_id"]))
        elif event.event_type is EventType.RESTRICTED_SESSION_ABANDONED:
            sid = str(payload["abandoned_restricted_session_id"])
            abnormal_restricted.append(sid)
            open_restricted.discard(sid)
        elif event.event_type is EventType.RISK_CONTROL_STATE_CHANGED:
            risk_state = str(payload["new_state"])
            risk_epoch = int(payload["risk_state_epoch_after"])
            config = payload["risk_config_sha256"]
            active_risk_config = str(config) if config is not None else None
        elif event.event_type is EventType.EMERGENCY_ACTION_OPENED:
            emergency_actions[str(payload["emergency_action_id"])] = payload
        elif event.event_type is EventType.CANCEL_INTENT_RECORDED:
            attempt = str(payload["cancel_attempt_id"])
            cancel_attempts[attempt] = payload
            cancel_may_sent[attempt] = False
        elif event.event_type is EventType.CANCEL_SEND_BOUNDARY_ENTERED:
            cancel_may_sent[str(payload["cancel_attempt_id"])] = True
        elif event.event_type is EventType.CANCEL_RESULT_RECORDED:
            attempt = str(payload["cancel_attempt_id"])
            cancel_attempts[attempt] = payload
            cancel_result_revision[attempt] = int(payload["result_revision"])
            if not bool(payload["unresolved"]):
                cancel_may_sent[attempt] = False
        elif event.event_type is EventType.RISK_RELEASE_RECORDED:
            release_records[str(payload["release_id"])] = payload
    if open_sessions:
        abnormal.extend(sorted(open_sessions))
    # ER-NW-002: for each imported legacy incident, proof association is
    # derived only from the existing WRITER_PROOF_HELD event(s) whose
    # incident_id equals that imported incident.  The imported incident
    # contributes exactly one protected count unless there is exactly one
    # such controlling proof and replay has derived
    # writer_proof_release_eligible_by_proof_id[proof_id] == true from a
    # qualifying RECONCILIATION_RECORDED event for the same incident.  No
    # proof, more than one candidate controlling proof, an ineligible proof,
    # or an unknown association remains protected.  This is intentionally
    # conservative and does not rewrite historical events: it is a pure
    # function of already-replayed proof/incident/eligibility facts.
    protected_unresolved_legacy_write_count = 0
    for imported_incident_id in imported_incident_ids:
        candidate_proofs = {
            proof for proof, held_incident in proof_incident.items()
            if held_incident == imported_incident_id
        }
        if len(candidate_proofs) == 1:
            (only_proof,) = candidate_proofs
            if proof_eligible.get(only_proof) is True:
                continue
        protected_unresolved_legacy_write_count += 1
    if not imported_incident_ids:
        history = "INCOMPLETE"
    elif protected_unresolved_legacy_write_count > 0:
        history = "COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE"
    else:
        history = "COMPLETE"
    if history == "INCOMPLETE":
        restart = RestartClassification.LEGACY_HISTORY_INCOMPLETE
    elif unresolved or protected_unresolved_legacy_write_count or any(state == "HELD" for state in proofs.values()):
        restart = RestartClassification.UNRESOLVED_WRITE_HELD
    else:
        restart = RestartClassification.SAFE_NO_WRITE_CAPABILITY
    return SafetyProjection(
        authority_meta.authority_schema_revision, authority_meta.authority_instance_id,
        authority_meta.authority_namespace_id, authority_meta.authority_store_path_identity_sha256,
        authority_row.trusted_sequence, authority_row.trusted_event_hash,
        ledger_meta.ledger_instance_id, ledger_meta.ledger_schema_revision,
        ledger_meta.ledger_path_identity_sha256, ledger_meta.environment_classification,
        ledger_meta.conflict_domain_ref, history, events[-1].sequence, events[-1].event_hash,
        tuple(sessions), sorted(open_sessions)[-1] if open_sessions else None,
        tuple(sorted(set(abnormal))), tuple(sorted(incidents)), tuple(sorted(attempts)),
        MappingProxyType(dict(sorted(prepared.items()))), MappingProxyType(dict(sorted(boundaries.items()))),
        MappingProxyType(dict(sorted(closures.items()))), tuple(sorted(unresolved)),
        MappingProxyType(dict(sorted(bindings.items()))), MappingProxyType({k: tuple(v) for k, v in sorted(order_history.items())}),
        MappingProxyType(dict(sorted(fills.items()))), tuple(sorted(fill_conflicts)),
        MappingProxyType(dict(sorted(reconciliation.items()))), MappingProxyType(dict(sorted(legacy_states.items()))),
        MappingProxyType(dict(sorted(proofs.items()))),
        MappingProxyType(dict(sorted(proof_eligible.items()))), protected_unresolved_legacy_write_count, restart,
        sessions[-1] if sessions else None,
        tuple(restricted_sessions), MappingProxyType(dict(sorted(restricted_modes.items()))),
        sorted(open_restricted)[-1] if open_restricted else None,
        tuple(sorted(set(abnormal_restricted))), risk_state, risk_epoch, active_risk_config,
        MappingProxyType(dict(sorted(emergency_actions.items()))),
        MappingProxyType(dict(sorted(cancel_attempts.items()))),
        MappingProxyType(dict(sorted(cancel_may_sent.items()))),
        MappingProxyType(dict(sorted(cancel_result_revision.items()))),
        MappingProxyType(dict(sorted(release_records.items()))),
    )


def deterministic_review_export(projection: SafetyProjection, *, relation: AuthorityLedgerRelation = AuthorityLedgerRelation.EQUAL) -> bytes:
    value = {
        "abnormal_prior_session_count": len(projection.abnormal_prior_session_ids),
        "authority_instance_id": projection.authority_instance_id,
        "authority_ledger_relation": relation.value,
        "authority_namespace_id": projection.authority_namespace_id,
        "authority_schema_revision": projection.authority_schema_revision,
        "authority_store_path_identity_sha256": projection.authority_store_path_identity_sha256,
        "client_order_to_venue_order_relationships": dict(projection.client_order_to_venue_order),
        "conflict_domain_ref": projection.conflict_domain_ref,
        "deduplicated_fill_count": len(projection.canonical_fills_by_fill_id),
        "deduplicated_fill_ids": sorted(projection.canonical_fills_by_fill_id),
        "environment_classification": projection.environment_classification,
        "event_count": projection.last_sequence,
        "export_schema_revision": 1,
        "first_sequence": 1,
        "incident_ids": list(projection.incident_ids),
        "integrity_validation_result": "PASS",
        "last_sequence": projection.last_sequence,
        "last_writer_session_id": projection.last_writer_session_id,
        "ledger_instance_id": projection.ledger_instance_id,
        "ledger_path_identity_sha256": projection.ledger_path_identity_sha256,
        "ledger_schema_revision": projection.ledger_schema_revision,
        "legacy_incident_states": {
            key: dict(value)
            for key, value in sorted(projection.legacy_incident_state_by_incident.items())
        },
        "reconciliation_dispositions": dict(projection.reconciliation_disposition_by_incident),
        "restart_classification": projection.restart_classification.value,
        "risk_control_state": projection.risk_control_state,
        "risk_state_epoch": projection.risk_state_epoch,
        "active_risk_config_sha256": projection.active_risk_config_sha256,
        "restricted_session_ids": list(projection.restricted_sessions),
        "active_restricted_session_id": projection.active_restricted_session_id,
        "abnormal_restricted_session_ids": list(projection.abnormal_restricted_session_ids),
        "emergency_action_ids": sorted(projection.emergency_actions_by_id),
        "cancel_attempt_ids": sorted(projection.cancel_attempts_by_id),
        "release_ids": sorted(projection.release_records_by_id),
        "terminal_event_hash": projection.terminal_event_hash,
        "trusted_event_hash": projection.trusted_event_hash,
        "trusted_sequence": projection.trusted_sequence,
        "unresolved_write_count": len(projection.unresolved_write_request_ids) + projection.protected_unresolved_legacy_write_count,
        "unresolved_write_request_ids": list(projection.unresolved_write_request_ids),
        "writer_proof_states": dict(projection.writer_proof_state_by_proof_id),
        "writer_session_state": "ABNORMAL" if projection.active_writer_session_id else "CLEAN",
    }
    return canonical_json_bytes(value)


def start_writer_session(
    locked: LockedLedger,
    *,
    prior_session_state: str,
    writer_session_id: str | None = None,
) -> str:
    """Append and authority-anchor abandonment/start events.

    A caller may use this only after an accepted higher-level acquisition has
    established normal-writer eligibility.  It is intentionally absent from
    the restricted legacy-import handle.
    """
    if type(locked) is not LockedLedger:
        raise LedgerError(FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED)
    if prior_session_state not in {"NONE", "CLEAN", "ABNORMAL"}:
        raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
    projection = locked.projection()
    events: list[EventInput] = []
    if projection.active_writer_session_id is not None:
        events.append(EventInput(EventType.WRITER_SESSION_ABANDONED, {
            "abandoned_writer_session_id": projection.active_writer_session_id,
            "reason": "PREVIOUS_SESSION_NO_LONGER_HOLDS_REQUIRED_AUTHORITY_AND_LEDGER_LOCKS",
        }))
        prior_session_state = "ABNORMAL"
    session_id = writer_session_id or f"ws_{locked.uuid_factory().hex}"
    if _WRITER_SESSION_ID_RE.fullmatch(session_id) is None:
        raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
    events.append(EventInput(EventType.WRITER_SESSION_STARTED, {
        "lock_model": LOCK_MODEL,
        "prior_session_state": prior_session_state,
        "session_schema_revision": 1,
        "writer_session_id": session_id,
    }, writer_session_id=session_id))
    locked.append_batch(events)
    return session_id


def end_writer_session(locked: LockedLedger, *, writer_session_id: str) -> None:
    """Authority-anchor WRITER_SESSION_ENDED, verify equality, then close."""
    try:
        result = locked.append_batch((EventInput(
            EventType.WRITER_SESSION_ENDED,
            {"writer_session_id": writer_session_id},
            writer_session_id=writer_session_id,
        ),))
        if (
            locked.authority_row.trusted_sequence != result.last_sequence
            or locked.authority_row.trusted_event_hash != result.terminal_event_hash
        ):
            raise LedgerError(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
    finally:
        locked.close()


def end_restricted_session(
    locked: LockedLedger,
    *,
    restricted_session_id: str,
    acquisition_mode: AcquisitionMode,
) -> None:
    """Anchor a clean restricted end before releasing ledger then authority locks."""
    try:
        previous = locked.events[-1]
        locked.append_batch((EventInput(EventType.RESTRICTED_SESSION_ENDED, {
            "restricted_session_id": restricted_session_id,
            "acquisition_mode": acquisition_mode.value,
            "pre_end_trusted_sequence": previous.sequence,
            "pre_end_trusted_event_hash": previous.event_hash,
            "pre_end_ledger_sequence": previous.sequence,
            "pre_end_ledger_event_hash": previous.event_hash,
            "end_reason": "CLEAN_RELEASE_OF_EXCLUSIVE_LOCKS",
        }, writer_session_id=restricted_session_id),))
    finally:
        locked.close()


@dataclass(frozen=True, slots=True)
class OpenResult:
    projection: SafetyProjection | None
    restart_classification: RestartClassification
    handle: LockedLedger | None
    failure_code: FailureCode | None = None
    authority_ledger_relation: AuthorityLedgerRelation | None = None


@dataclass(frozen=True, slots=True)
class _LegacyImportInternalResult:
    """Module-private carrier; never part of the public acquisition API."""

    projection: SafetyProjection | None
    restart_classification: RestartClassification
    locked: LockedLedger | None
    failure_code: FailureCode | None = None
    authority_ledger_relation: AuthorityLedgerRelation | None = None


@dataclass(frozen=True, slots=True)
class _RestrictedInternalResult:
    """Fresh restricted acquisition plus its already-anchored ``rs_`` session.

    No caller can convert a pre-existing normal-writer lock into a restricted
    session: construction and session start both occur inside the single fresh
    acquisition operation below, before the locked ledger is returned.
    """

    projection: SafetyProjection | None
    restart_classification: RestartClassification
    locked: LockedLedger | None
    restricted_session_id: str | None = None
    failure_code: FailureCode | None = None
    authority_ledger_relation: AuthorityLedgerRelation | None = None


def _acquire_local_state_internal(
    binding: AuthorityNamespaceBinding,
    *,
    conflict_domain_ref: str,
    expected_environment: str,
    canonical_repository_root: str | os.PathLike[str],
    acquisition_mode: AcquisitionMode,
    expected_ledger_path: str | os.PathLike[str] | None = None,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
    fault_hook: FaultHook = _noop_fault_hook,
    history_validator: HistoryValidator | None = None,
) -> OpenResult:
    if type(acquisition_mode) is not AcquisitionMode:
        return OpenResult(None, RestartClassification.LEDGER_INTEGRITY_FAILURE, None, FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED)
    try:
        locked = _open_locked(binding, conflict_domain_ref=conflict_domain_ref, expected_environment=expected_environment, canonical_repository_root=canonical_repository_root, expected_ledger_path=expected_ledger_path, clock=clock, uuid_factory=uuid_factory, fault_hook=fault_hook, history_validator=history_validator)
        projection = locked.projection()
        if acquisition_mode is AcquisitionMode.NORMAL_WRITER:
            # Revision 03 has no supported empty-history proof; current imported
            # history is still protected and unresolved.  Therefore neither
            # valid state can expose an ordinary writer handle.
            locked.close()
            return OpenResult(projection, projection.restart_classification, None, None, locked.relation)
        if acquisition_mode in {AcquisitionMode.EMERGENCY_CONTROL_ONLY, AcquisitionMode.RELEASE_ONLY}:
            return OpenResult(projection, projection.restart_classification, locked, None, locked.relation)
        if projection.history_completeness != "INCOMPLETE":
            locked.close()
            return OpenResult(projection, projection.restart_classification, None, None, locked.relation)
        if projection.restart_classification is not RestartClassification.LEGACY_HISTORY_INCOMPLETE:
            locked.close()
            return OpenResult(projection, projection.restart_classification, None, FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED, locked.relation)
        return OpenResult(projection, projection.restart_classification, locked, None, locked.relation)
    except LedgerError as exc:
        return OpenResult(None, _classify_error(exc), None, exc.code)


def acquire_local_state(
    binding: AuthorityNamespaceBinding,
    *,
    conflict_domain_ref: str,
    expected_environment: str,
    canonical_repository_root: str | os.PathLike[str],
    acquisition_mode: AcquisitionMode,
    expected_ledger_path: str | os.PathLike[str] | None = None,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
    fault_hook: FaultHook = _noop_fault_hook,
    history_validator: HistoryValidator | None = None,
) -> OpenResult:
    """Acquire public local state without exposing bootstrap mutation power.

    ``LEGACY_IMPORT_ONLY`` is deliberately not serviced by this generic API.
    The Kalshi binding consumes the private mode-specific helper below and
    wraps its internal lock object in ``LegacyImportOnlyHandle`` before any
    result becomes caller-visible.
    """
    if acquisition_mode in {
        AcquisitionMode.LEGACY_IMPORT_ONLY,
        AcquisitionMode.EMERGENCY_CONTROL_ONLY,
        AcquisitionMode.RELEASE_ONLY,
    }:
        return OpenResult(
            None,
            RestartClassification.LEDGER_INTEGRITY_FAILURE,
            None,
            FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED,
        )
    return _acquire_local_state_internal(
        binding,
        conflict_domain_ref=conflict_domain_ref,
        expected_environment=expected_environment,
        canonical_repository_root=canonical_repository_root,
        acquisition_mode=acquisition_mode,
        expected_ledger_path=expected_ledger_path,
        clock=clock,
        uuid_factory=uuid_factory,
        fault_hook=fault_hook,
        history_validator=history_validator,
    )


def _acquire_normal_writer_candidate(
    binding: AuthorityNamespaceBinding,
    *,
    conflict_domain_ref: str,
    expected_environment: str,
    canonical_repository_root: str | os.PathLike[str],
    expected_ledger_path: str | os.PathLike[str] | None = None,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
    fault_hook: FaultHook = _noop_fault_hook,
    history_validator: HistoryValidator | None = None,
) -> OpenResult:
    """Private normal-writer candidate bridge (ER-NW-001).

    Not part of the public ``acquire_local_state`` surface: no generic
    caller can obtain a live normal-writer-capable candidate through the
    public API.  This bridge is consumed only by a venue binding (e.g.
    ``arb.venues.kalshi.ledger_binding.acquire_normal_writer_state``), which
    performs the full durable-eligibility and current-process continuity
    validation required by that venue's exact acquisition theorem while the
    same authority/ledger exclusive lock pair returned here remains held,
    before ever starting a writer session.

    This bridge itself evaluates only the venue-agnostic structural
    predicates: authority-first/ledger-second exclusive locking, full
    identity/schema/integrity validation, complete replay under the supplied
    history validator, and an exactly-equal authority/ledger trusted tail.
    A ledger-ahead relation exposes no candidate on this acquisition; the
    caller must close and perform a fresh equal-tail reopen.  It does not
    itself evaluate history completeness, risk/proof state, or any other
    durable eligibility predicate, and it never starts a writer session.
    """
    try:
        locked = _open_locked(
            binding, conflict_domain_ref=conflict_domain_ref,
            expected_environment=expected_environment,
            canonical_repository_root=canonical_repository_root,
            expected_ledger_path=expected_ledger_path, clock=clock,
            uuid_factory=uuid_factory, fault_hook=fault_hook,
            history_validator=history_validator,
        )
    except LedgerError as exc:
        return OpenResult(None, _classify_error(exc), None, exc.code)
    projection = locked.projection()
    if locked.relation is not AuthorityLedgerRelation.EQUAL:
        locked.close()
        return OpenResult(projection, projection.restart_classification, None, None, locked.relation)
    return OpenResult(projection, projection.restart_classification, locked, None, locked.relation)


def _acquire_legacy_import_state(
    binding: AuthorityNamespaceBinding,
    *,
    conflict_domain_ref: str,
    expected_environment: str,
    canonical_repository_root: str | os.PathLike[str],
    expected_ledger_path: str | os.PathLike[str] | None = None,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
    fault_hook: FaultHook = _noop_fault_hook,
    history_validator: HistoryValidator | None = None,
) -> _LegacyImportInternalResult:
    """Private bridge consumed only by the restricted venue importer."""
    opened = _acquire_local_state_internal(
        binding,
        conflict_domain_ref=conflict_domain_ref,
        expected_environment=expected_environment,
        canonical_repository_root=canonical_repository_root,
        acquisition_mode=AcquisitionMode.LEGACY_IMPORT_ONLY,
        expected_ledger_path=expected_ledger_path,
        clock=clock,
        uuid_factory=uuid_factory,
        fault_hook=fault_hook,
        history_validator=history_validator,
    )
    return _LegacyImportInternalResult(
        opened.projection,
        opened.restart_classification,
        opened.handle,
        opened.failure_code,
        opened.authority_ledger_relation,
    )


def _acquire_restricted_state(
    binding: AuthorityNamespaceBinding,
    *,
    conflict_domain_ref: str,
    expected_environment: str,
    canonical_repository_root: str | os.PathLike[str],
    acquisition_mode: AcquisitionMode,
    expected_ledger_path: str | os.PathLike[str] | None = None,
    clock: Clock = _utc_now,
    uuid_factory: UuidFactory = uuid.uuid4,
    fault_hook: FaultHook = _noop_fault_hook,
    history_validator: HistoryValidator | None = None,
) -> _RestrictedInternalResult:
    """Private bridge for narrow emergency/release binding handles."""
    if acquisition_mode not in {AcquisitionMode.EMERGENCY_CONTROL_ONLY, AcquisitionMode.RELEASE_ONLY}:
        return _RestrictedInternalResult(
            None, RestartClassification.LEDGER_INTEGRITY_FAILURE, None,
            failure_code=FailureCode.RESTRICTED_SESSION_STATE_CONFLICT,
        )
    opened = _acquire_local_state_internal(
        binding,
        conflict_domain_ref=conflict_domain_ref,
        expected_environment=expected_environment,
        canonical_repository_root=canonical_repository_root,
        acquisition_mode=acquisition_mode,
        expected_ledger_path=expected_ledger_path,
        clock=clock,
        uuid_factory=uuid_factory,
        fault_hook=fault_hook,
        history_validator=history_validator,
    )
    if opened.handle is None:
        return _RestrictedInternalResult(
            opened.projection, opened.restart_classification, None,
            failure_code=opened.failure_code,
            authority_ledger_relation=opened.authority_ledger_relation,
        )

    # This is deliberately the only restricted-session start site.  The lock
    # was acquired afresh immediately above; it has never been exposed to a
    # normal writer or to the caller.  Replayed open sessions therefore denote
    # owners that cannot still hold the newly acquired OS/SQLite locks.
    locked = opened.handle
    try:
        projection = locked.projection()
        prior_state = "NONE"
        if projection.active_writer_session_id is not None:
            locked.append_batch((EventInput(EventType.WRITER_SESSION_ABANDONED, {
                "abandoned_writer_session_id": projection.active_writer_session_id,
                "reason": "PREVIOUS_SESSION_NO_LONGER_HOLDS_REQUIRED_AUTHORITY_AND_LEDGER_LOCKS",
            }),))
            prior_state = "ABNORMAL"
            projection = locked.projection()
        if projection.active_restricted_session_id is not None:
            prior = projection.active_restricted_session_id
            prior_mode = projection.restricted_session_modes[prior]
            previous = locked.events[-1]
            locked.append_batch((EventInput(EventType.RESTRICTED_SESSION_ABANDONED, {
                "abandoned_restricted_session_id": prior,
                "acquisition_mode": prior_mode.value,
                "reason": "PREVIOUS_RESTRICTED_SESSION_NO_LONGER_HOLDS_REQUIRED_AUTHORITY_AND_LEDGER_LOCKS",
                "observed_trusted_sequence": previous.sequence,
                "observed_trusted_event_hash": previous.event_hash,
                "observed_ledger_sequence": previous.sequence,
                "observed_ledger_event_hash": previous.event_hash,
            }),))
            prior_state = "ABNORMAL"
        projection = locked.projection()
        if projection.active_writer_session_id is not None or projection.active_restricted_session_id is not None:
            raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
        session_id = f"rs_{locked.uuid_factory().hex}"
        if _RESTRICTED_SESSION_ID_RE.fullmatch(session_id) is None:
            raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
        previous = locked.events[-1]
        locked.append_batch((EventInput(EventType.RESTRICTED_SESSION_STARTED, {
            "restricted_session_id": session_id,
            "acquisition_mode": acquisition_mode.value,
            "session_schema_revision": 1,
            "lock_model": LOCK_MODEL,
            "prior_restricted_session_state": prior_state,
            "opening_trusted_sequence": previous.sequence,
            "opening_trusted_event_hash": previous.event_hash,
            "opening_ledger_sequence": previous.sequence,
            "opening_ledger_event_hash": previous.event_hash,
        }, writer_session_id=session_id),))
        return _RestrictedInternalResult(
            locked.projection(), opened.restart_classification, locked,
            restricted_session_id=session_id,
            authority_ledger_relation=opened.authority_ledger_relation,
        )
    except LedgerError as exc:
        locked.close()
        return _RestrictedInternalResult(
            None, _classify_error(exc), None, failure_code=exc.code,
            authority_ledger_relation=opened.authority_ledger_relation,
        )


def sqlite_posture(connection: sqlite3.Connection) -> Mapping[str, object]:
    """Return exact non-secret SQLite readback evidence for tests/review."""
    return MappingProxyType({
        "journal_mode": str(_pragma_scalar(connection, "PRAGMA journal_mode")).lower(),
        "synchronous": _pragma_scalar(connection, "PRAGMA synchronous"),
        "foreign_keys": _pragma_scalar(connection, "PRAGMA foreign_keys"),
        "busy_timeout": _pragma_scalar(connection, "PRAGMA busy_timeout"),
        "locking_mode": str(_pragma_scalar(connection, "PRAGMA locking_mode")).lower(),
        "user_version": _pragma_scalar(connection, "PRAGMA user_version"),
    })


__all__ = [
    "AUTHORITY_STORE_FILENAME", "AcquisitionMode", "AppendResult", "AppendStatus",
    "AuthorityLedgerRelation", "AuthorityMeta", "AuthorityNamespaceBinding", "AuthorityRow",
    "CRASH_FAULT_MATRIX", "CommitResultUnknown", "CrashFaultExpectation", "EventInput", "EventType", "FailureCode", "LedgerError",
    "LedgerEvent", "LedgerMeta", "LockedLedger", "OpenResult", "RestartClassification",
    "SafetyProjection", "acquire_local_state", "assert_secret_safe", "canonical_json_bytes",
    "canonical_json_text", "canonical_timestamp", "deterministic_review_export",
    "deterministic_event_id", "end_restricted_session", "end_writer_session",
    "initialize_authority_namespace", "initialize_ledger_binding", "load_and_validate_events",
    "parse_canonical_json", "path_identity", "replay_projection", "sha256_hex", "sqlite_posture",
    "start_writer_session", "RISK_CONTROL_STATES", "RISK_CONTROL_TRANSITIONS",
]
