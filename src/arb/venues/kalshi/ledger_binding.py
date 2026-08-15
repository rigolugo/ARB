"""Kalshi-specific binding for the local execution safety ledger.

The module contains no transport, credential, private-key, signing, or venue
I/O implementation.  It validates secret-free Kalshi ledger payloads and owns
the structurally restricted one-time legacy-import capability required by the
accepted Revision-03 specification.
"""

from __future__ import annotations

import enum
import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from arb.execution_ledger import (
    AcquisitionMode,
    AppendStatus,
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
    _acquire_legacy_import_state,
    _acquire_restricted_state,
    acquire_local_state,
    canonical_json_bytes,
    canonical_timestamp,
    end_restricted_session,
    parse_canonical_json,
    sha256_hex,
)
from arb.venues.kalshi.risk_control import (
    EconomicFillV1,
    FreshnessStampV1,
    RiskControlCode,
    RiskControlError,
    RiskLimitConfigV1,
    UNKNOWN_UNBOUNDED,
    WorkingOrderV1,
    WriterEligibilityGate,
    compute_market_economic_state,
    freshness_age_ms,
)


CURRENT_INCIDENT_ID = "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01"
CURRENT_ENVIRONMENT = "KALSHI_DEMO"
CURRENT_ACCOUNT_SCOPE_REF = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
CURRENT_SUBACCOUNT = 0
CURRENT_TICKER = "KXFEDDECISION-26SEP-H0"
CURRENT_CLIENT_ORDER_ID = "2e64d452-2cc2-43fa-a976-e8f996192252"
CURRENT_LEGACY_WRITER_SESSION_ID = "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_LOCAL_RUNNER"
CURRENT_WRITER_PROOF_ID = "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_WRITER_PROOF"
CURRENT_CONFLICT_DOMAIN_REF = "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0"
CURRENT_DISPOSITION = "WRITE_UNRESOLVED_ZERO_MATCH"


@dataclass(frozen=True, slots=True)
class EvidenceExpectation:
    name: str
    raw_bytes: int
    sha256: str


PRODUCTION_EVIDENCE_EXPECTATIONS = (
    EvidenceExpectation("execution_evidence.json", 10746, "2cb1677d06d3c88a3dd6f5b41190fa6de237bae24f02457fee37b2e0d04eefac"),
    EvidenceExpectation("KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json", 10541, "a10eb4a6d7490755bbe055056cbe4960d075fd73048967d7e3d1c846c7be34fe"),
    EvidenceExpectation("KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_EVIDENCE_01.json", 10882, "5e9cb2690854309f5684fa1b31cc4d837e301152a8466732382acb913dd73aa2"),
)


@dataclass(frozen=True, slots=True)
class LegacyIncidentContract:
    incident_id: str = CURRENT_INCIDENT_ID
    environment: str = CURRENT_ENVIRONMENT
    account_scope_ref: str = CURRENT_ACCOUNT_SCOPE_REF
    subaccount: int = CURRENT_SUBACCOUNT
    ticker: str = CURRENT_TICKER
    client_order_id: str = CURRENT_CLIENT_ORDER_ID
    legacy_writer_session_id: str = CURRENT_LEGACY_WRITER_SESSION_ID
    writer_proof_id: str = CURRENT_WRITER_PROOF_ID
    conflict_domain_ref: str = CURRENT_CONFLICT_DOMAIN_REF
    evidence_expectations: tuple[EvidenceExpectation, ...] = PRODUCTION_EVIDENCE_EXPECTATIONS


CURRENT_LEGACY_INCIDENT_CONTRACT = LegacyIncidentContract()


class LegacyImportStatus(enum.StrEnum):
    VALIDATED = "VALIDATED"
    NOT_COMMITTED = "NOT_COMMITTED"
    FULLY_AUTHORITY_ANCHORED = "FULLY_AUTHORITY_ANCHORED"
    ALREADY_COMPLETED_AND_ANCHORED = "ALREADY_COMPLETED_AND_ANCHORED"
    ALREADY_COMMITTED_CATCHUP_COMPLETED = "ALREADY_COMMITTED_CATCHUP_COMPLETED"


@dataclass(frozen=True, slots=True)
class ValidatedLegacyEvidence:
    contract: LegacyIncidentContract
    payload: Mapping[str, object]
    deterministic_event_id: str


@dataclass(frozen=True, slots=True)
class LegacyImportResult:
    status: LegacyImportStatus
    events_appended: int
    projection: SafetyProjection
    first_sequence: int | None = None
    last_sequence: int | None = None
    terminal_event_hash: str | None = None


@dataclass(frozen=True, slots=True)
class LegacyImportAcquisition:
    restart_classification: RestartClassification
    projection: SafetyProjection | None
    handle: "LegacyImportOnlyHandle | None"
    completed_result: LegacyImportResult | None
    failure_code: FailureCode | None


@dataclass(frozen=True, slots=True)
class RestrictedAcquisition:
    restart_classification: RestartClassification
    projection: SafetyProjection | None
    handle: "EmergencyControlLedgerHandle | ReleaseLedgerHandle | None"
    failure_code: FailureCode | None
    authority_ledger_relation: AuthorityLedgerRelation | None


@dataclass(frozen=True, slots=True)
class AuthorityAnchoredSendGate:
    request_id: str
    boundary_sequence: int
    boundary_event_hash: str
    authority_trusted_sequence: int
    authority_trusted_event_hash: str
    state: str = "AUTHORITY_ANCHORED_SEND_BOUNDARY"


def _duplicate_rejecting_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)
        output[key] = value
    return output


def _parse_evidence(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_rejecting_pairs)
    except LedgerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH) from exc


_LIFECYCLE_EVIDENCE_NAME = "execution_evidence.json"
_RECONCILIATION_EVIDENCE_NAME = (
    "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json"
)
_FILL_DISCOVERY_EVIDENCE_NAME = (
    "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_EVIDENCE_01.json"
)
_RECONCILIATION_EXECUTION_TASK_ID = (
    "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EXECUTION_01"
)
_RECONCILIATION_IMPLEMENTATION_TASK_ID = (
    "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_IMPLEMENTATION_01"
)
_FILL_DISCOVERY_EXECUTION_TASK_ID = (
    "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_01"
)
_FILL_DISCOVERY_IMPLEMENTATION_TASK_ID = (
    "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_IMPLEMENTATION_01"
)


@dataclass(frozen=True, slots=True)
class _LegacyArtifactFacts:
    """Schema-local projection of material facts explicitly proven by one artifact."""

    artifact_name: str
    authorization_consumed: bool
    lifecycle_incident_id: str | None
    environment: str
    account_scope_ref: str
    subaccount: int
    ticker: str
    client_order_id: str
    writer_proof_id: str
    legacy_writer_session_id: str | None
    final_disposition: str | None
    bound_order_id: str | None
    created_order_upper_bound: int
    active_order_upper_bound: int
    unknown_result: bool
    writer_proof_state: str | None
    writer_proof_release_eligible: bool


def _value_at(document: object, path: tuple[str, ...]) -> object:
    value = document
    for component in path:
        if type(value) is not dict or component not in value:
            raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)
        value = value[component]
    return value


def _require_at(document: object, path: tuple[str, ...], expected: object) -> object:
    value = _value_at(document, path)
    if type(value) is not type(expected) or value != expected:
        raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)
    return value


def _extract_lifecycle_evidence_facts(
    document: object,
    contract: LegacyIncidentContract,
) -> _LegacyArtifactFacts:
    """Validate only the accepted lifecycle artifact's exact material paths."""
    _require_at(document, ("task_id",), contract.incident_id)
    _require_at(document, ("authorization_consumed",), True)
    _require_at(document, ("environment",), contract.environment)
    _require_at(document, ("ticker",), contract.ticker)
    _require_at(document, ("client_order_id",), contract.client_order_id)
    _require_at(document, ("phase",), "FAIL_CLOSED_HALT")
    _require_at(document, ("halt_code",), "RECOVERY_ZERO_MATCH")
    _require_at(document, ("terminal_result",), None)

    canonical = ("canonical_lifecycle_evidence",)
    _require_at(document, canonical + ("environment",), contract.environment)
    _require_at(document, canonical + ("account_scope_ref",), contract.account_scope_ref)
    _require_at(document, canonical + ("subaccount",), contract.subaccount)
    _require_at(document, canonical + ("ticker",), contract.ticker)
    _require_at(document, canonical + ("client_order_id",), contract.client_order_id)
    _require_at(document, canonical + ("writer_session_id",), contract.legacy_writer_session_id)
    _require_at(document, canonical + ("proof_id",), contract.writer_proof_id)
    _require_at(document, canonical + ("proof_state",), "HELD")
    _require_at(document, canonical + ("proof_release_eligible",), False)
    _require_at(document, canonical + ("bound_order_id",), None)
    _require_at(document, canonical + ("created_order_upper_bound",), 1)
    _require_at(document, canonical + ("active_order_upper_bound",), 1)
    _require_at(document, canonical + ("unknown_result",), True)
    _require_at(document, canonical + ("create_send_may_have_begun",), True)
    _require_at(document, canonical + ("cancel_send_may_have_begun",), False)
    _require_at(document, canonical + ("halt_code",), "RECOVERY_ZERO_MATCH")

    proof = ("writer_proof",)
    _require_at(document, proof + ("id",), contract.writer_proof_id)
    _require_at(document, proof + ("account_scope_ref",), contract.account_scope_ref)
    _require_at(document, proof + ("writer_session_id",), contract.legacy_writer_session_id)
    _require_at(document, proof + ("continuity_state",), "HELD")

    reconciliation = ("reconciliation",)
    _require_at(document, reconciliation + ("created_order_upper_bound",), 1)
    _require_at(document, reconciliation + ("active_order_upper_bound",), 1)
    _require_at(document, reconciliation + ("unknown_result",), True)
    _require_at(document, reconciliation + ("proof_release_eligible",), False)
    _require_at(document, ("authoritative_order_snapshots",), [])
    _require_at(document, ("canonical_fill_summary",), None)

    return _LegacyArtifactFacts(
        artifact_name=_LIFECYCLE_EVIDENCE_NAME,
        authorization_consumed=True,
        lifecycle_incident_id=contract.incident_id,
        environment=contract.environment,
        account_scope_ref=contract.account_scope_ref,
        subaccount=contract.subaccount,
        ticker=contract.ticker,
        client_order_id=contract.client_order_id,
        writer_proof_id=contract.writer_proof_id,
        legacy_writer_session_id=contract.legacy_writer_session_id,
        final_disposition=None,
        bound_order_id=None,
        created_order_upper_bound=1,
        active_order_upper_bound=1,
        unknown_result=True,
        writer_proof_state="HELD",
        writer_proof_release_eligible=False,
    )


def _extract_reconciliation_evidence_facts(
    document: object,
    contract: LegacyIncidentContract,
) -> _LegacyArtifactFacts:
    """Validate reconciliation provenance separately from shared incident facts."""
    _require_at(document, ("task_id",), _RECONCILIATION_EXECUTION_TASK_ID)
    _require_at(document, ("authorization", "authorization_consumed"), True)
    _require_at(document, ("authorization", "overall_execution_attempts_authorized"), 1)
    _require_at(
        document,
        ("canonical_result", "evidence", "task_id"),
        _RECONCILIATION_IMPLEMENTATION_TASK_ID,
    )

    scope = ("canonical_result", "evidence", "frozen_scope")
    _require_at(document, scope + ("environment",), contract.environment)
    _require_at(document, scope + ("account_scope_ref",), contract.account_scope_ref)
    _require_at(document, scope + ("subaccount",), contract.subaccount)
    _require_at(document, scope + ("ticker",), contract.ticker)
    _require_at(document, scope + ("client_order_id",), contract.client_order_id)
    _require_at(document, scope + ("writer_proof_id",), contract.writer_proof_id)

    result = ("canonical_result",)
    for prefix in (result, result + ("evidence", "terminal")):
        _require_at(document, prefix + ("result_class",), CURRENT_DISPOSITION)
        _require_at(document, prefix + ("created_order_upper_bound",), 1)
        _require_at(document, prefix + ("active_order_upper_bound",), 1)
        _require_at(document, prefix + ("unknown_result",), True)
        _require_at(document, prefix + ("writer_proof_release_eligible",), False)
    _require_at(document, result + ("bound_order_id",), None)
    _require_at(document, result + ("exact_client_order_id_match_count",), 0)
    _require_at(document, result + ("canonical_fill_count",), 0)

    order_match = result + ("evidence", "order_match")
    _require_at(document, order_match + ("bound_order_id",), None)
    _require_at(document, order_match + ("exact_client_order_id_match_count",), 0)
    _require_at(document, order_match + ("canonical_orders",), [])
    _require_at(document, order_match + ("matched_order_ids",), [])
    fills = result + ("evidence", "fills")
    _require_at(document, fills + ("canonical_fill_count",), 0)
    _require_at(document, fills + ("canonical_fill_identities",), [])
    _require_at(document, fills + ("order_fill_reconciliation_result",), "UNRESOLVED_OR_NOT_REACHED")
    records_retained = result + ("evidence", "enumeration", "records_retained")
    _require_at(document, records_retained + ("orders",), 0)
    _require_at(document, records_retained + ("fills",), 0)

    return _LegacyArtifactFacts(
        artifact_name=_RECONCILIATION_EVIDENCE_NAME,
        authorization_consumed=True,
        lifecycle_incident_id=None,
        environment=contract.environment,
        account_scope_ref=contract.account_scope_ref,
        subaccount=contract.subaccount,
        ticker=contract.ticker,
        client_order_id=contract.client_order_id,
        writer_proof_id=contract.writer_proof_id,
        legacy_writer_session_id=None,
        final_disposition=CURRENT_DISPOSITION,
        bound_order_id=None,
        created_order_upper_bound=1,
        active_order_upper_bound=1,
        unknown_result=True,
        writer_proof_state=None,
        writer_proof_release_eligible=False,
    )


def _extract_fill_discovery_evidence_facts(
    document: object,
    contract: LegacyIncidentContract,
) -> _LegacyArtifactFacts:
    """Validate fill-discovery provenance separately from shared incident facts."""
    _require_at(document, ("task_id",), _FILL_DISCOVERY_EXECUTION_TASK_ID)
    _require_at(document, ("authorization", "authorization_consumed"), True)
    _require_at(document, ("authorization", "overall_execution_authorized"), 1)
    _require_at(document, ("authorization", "rerun_permitted_under_this_authorization"), False)
    _require_at(
        document,
        ("canonical_result", "evidence", "task_id"),
        _FILL_DISCOVERY_IMPLEMENTATION_TASK_ID,
    )

    scope = ("canonical_result", "evidence", "frozen_scope")
    _require_at(document, scope + ("environment",), contract.environment)
    _require_at(document, scope + ("account_scope_ref",), contract.account_scope_ref)
    _require_at(document, scope + ("subaccount",), contract.subaccount)
    _require_at(document, scope + ("ticker",), contract.ticker)
    _require_at(document, scope + ("client_order_id",), contract.client_order_id)
    _require_at(document, scope + ("writer_proof_id",), contract.writer_proof_id)

    result = ("canonical_result",)
    for prefix in (
        result,
        result + ("evidence", "predecessor_result"),
        result + ("evidence", "terminal"),
    ):
        _require_at(document, prefix + ("result_class",), CURRENT_DISPOSITION)
        _require_at(document, prefix + ("bound_order_id",), None)
        _require_at(document, prefix + ("created_order_upper_bound",), 1)
        _require_at(document, prefix + ("active_order_upper_bound",), 1)
        _require_at(document, prefix + ("unknown_result",), True)
        _require_at(document, prefix + ("writer_proof_release_eligible",), False)
    for path in (
        result + ("candidate_order_id_count",),
        result + ("canonical_fill_count",),
        result + ("validated_binding_count",),
        result + ("prior_exact_client_order_id_match_count",),
        result + ("evidence", "terminal", "candidate_order_id_count"),
        result + ("evidence", "terminal", "canonical_fill_count"),
        result + ("evidence", "terminal", "validated_binding_count"),
        result + ("evidence", "terminal", "prior_exact_client_order_id_match_count"),
        result + ("evidence", "predecessor_result", "exact_client_order_id_match_count"),
        result + ("evidence", "bound_fill_reconciliation", "canonical_fill_count"),
        result + ("evidence", "candidate_validation", "validated_binding_count"),
        result + ("evidence", "discovery", "candidate_order_id_count"),
        result + ("evidence", "discovery", "unique_fill_id_count"),
    ):
        _require_at(document, path, 0)
    _require_at(document, result + ("candidate_order_ids",), [])
    _require_at(document, result + ("validated_binding_order_ids",), [])
    _require_at(document, result + ("evidence", "terminal", "candidate_order_ids"), [])
    _require_at(document, result + ("evidence", "terminal", "validated_binding_order_ids"), [])
    _require_at(document, result + ("evidence", "bound_fill_reconciliation", "bound_order_id"), None)
    _require_at(document, result + ("evidence", "bound_fill_reconciliation", "bound_fills"), [])
    _require_at(document, result + ("evidence", "candidate_validation", "results"), [])
    _require_at(document, result + ("evidence", "candidate_validation", "validated_binding_order_ids"), [])
    _require_at(document, result + ("evidence", "discovery", "candidate_order_id_set"), [])
    _require_at(document, result + ("evidence", "discovery", "canonical_discovery_fills"), [])

    return _LegacyArtifactFacts(
        artifact_name=_FILL_DISCOVERY_EVIDENCE_NAME,
        authorization_consumed=True,
        lifecycle_incident_id=None,
        environment=contract.environment,
        account_scope_ref=contract.account_scope_ref,
        subaccount=contract.subaccount,
        ticker=contract.ticker,
        client_order_id=contract.client_order_id,
        writer_proof_id=contract.writer_proof_id,
        legacy_writer_session_id=None,
        final_disposition=CURRENT_DISPOSITION,
        bound_order_id=None,
        created_order_upper_bound=1,
        active_order_upper_bound=1,
        unknown_result=True,
        writer_proof_state=None,
        writer_proof_release_eligible=False,
    )


def _require_shared_incident_consistency(
    facts: tuple[_LegacyArtifactFacts, ...],
    contract: LegacyIncidentContract,
) -> None:
    """Cross-check only explicit semantic projections, never arbitrary JSON keys."""
    expected = {
        "environment": contract.environment,
        "account_scope_ref": contract.account_scope_ref,
        "subaccount": contract.subaccount,
        "ticker": contract.ticker,
        "client_order_id": contract.client_order_id,
        "writer_proof_id": contract.writer_proof_id,
        "bound_order_id": None,
        "created_order_upper_bound": 1,
        "active_order_upper_bound": 1,
        "unknown_result": True,
        "writer_proof_release_eligible": False,
    }
    if len(facts) != 3 or any(item.authorization_consumed is not True for item in facts):
        raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)
    for attribute, expected_value in expected.items():
        if any(
            type(getattr(item, attribute)) is not type(expected_value)
            or getattr(item, attribute) != expected_value
            for item in facts
        ):
            raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)
    incident_ids = [item.lifecycle_incident_id for item in facts if item.lifecycle_incident_id is not None]
    dispositions = [item.final_disposition for item in facts if item.final_disposition is not None]
    writer_states = [item.writer_proof_state for item in facts if item.writer_proof_state is not None]
    legacy_sessions = [item.legacy_writer_session_id for item in facts if item.legacy_writer_session_id is not None]
    if (
        incident_ids != [contract.incident_id]
        or dispositions != [CURRENT_DISPOSITION, CURRENT_DISPOSITION]
        or writer_states != ["HELD"]
        or legacy_sessions != [contract.legacy_writer_session_id]
    ):
        raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)


def validate_legacy_evidence(
    evidence_files: Mapping[str, bytes],
    *,
    contract: LegacyIncidentContract = CURRENT_LEGACY_INCIDENT_CONTRACT,
) -> ValidatedLegacyEvidence:
    """Validate synthetic or exact identity-bound legacy evidence.

    Production identities are fixed in ``CURRENT_LEGACY_INCIDENT_CONTRACT``.
    Tests may supply an explicit contract whose expectations bind synthetic
    bytes; this avoids copying or importing the real accepted evidence.
    """
    if set(evidence_files) != {item.name for item in contract.evidence_expectations}:
        raise LedgerError(FailureCode.LEGACY_INCIDENT_EVIDENCE_IDENTITY_MISMATCH)
    documents_by_name: dict[str, object] = {}
    for expectation in contract.evidence_expectations:
        raw = evidence_files[expectation.name]
        if type(raw) is not bytes or len(raw) != expectation.raw_bytes or hashlib.sha256(raw).hexdigest() != expectation.sha256:
            raise LedgerError(FailureCode.LEGACY_INCIDENT_EVIDENCE_IDENTITY_MISMATCH)
        document = _parse_evidence(raw)
        documents_by_name[expectation.name] = document

    try:
        facts = (
            _extract_lifecycle_evidence_facts(
                documents_by_name[_LIFECYCLE_EVIDENCE_NAME], contract
            ),
            _extract_reconciliation_evidence_facts(
                documents_by_name[_RECONCILIATION_EVIDENCE_NAME], contract
            ),
            _extract_fill_discovery_evidence_facts(
                documents_by_name[_FILL_DISCOVERY_EVIDENCE_NAME], contract
            ),
        )
    except KeyError as exc:
        raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH) from exc
    _require_shared_incident_consistency(facts, contract)

    payload = _expected_legacy_payload(contract)
    payload_bytes = canonical_json_bytes(payload)
    event_id = f"legacy_{sha256_hex(payload_bytes)}"
    return ValidatedLegacyEvidence(contract, MappingProxyType(payload), event_id)


def _expected_legacy_payload(contract: LegacyIncidentContract) -> dict[str, object]:
    artifacts = [
        {"name": item.name, "bytes": item.raw_bytes, "sha256": item.sha256}
        for item in contract.evidence_expectations
    ]
    return {
        "account_scope_ref": contract.account_scope_ref,
        "active_order_upper_bound": 1,
        "authorization_states": {
            "exact_reconciliation": "CONSUMED",
            "fill_discovery_fallback": "CONSUMED",
            "one_order_lifecycle": "CONSUMED",
        },
        "bound_order_id": None,
        "client_order_id": contract.client_order_id,
        "created_order_upper_bound": 1,
        "environment": contract.environment,
        "evidence_artifacts": artifacts,
        "final_disposition": CURRENT_DISPOSITION,
        "incident_id": contract.incident_id,
        "legacy_import_schema_revision": 1,
        "legacy_write_may_have_been_sent": True,
        "legacy_writer_session_id": contract.legacy_writer_session_id,
        "provenance_status": "PROJECT_EVIDENCE_RECORDED",
        "subaccount": contract.subaccount,
        "ticker": contract.ticker,
        "unknown_result": True,
        "writer_proof_id": contract.writer_proof_id,
        "writer_proof_release_eligible": False,
        "writer_proof_state": "HELD",
    }


def _validate_bound_legacy_history(
    events: tuple,
    contract: LegacyIncidentContract,
) -> None:
    legacy_events = [event for event in events if event.event_type is EventType.LEGACY_INCIDENT_IMPORTED]
    protected_holds = [
        event for event in events
        if event.event_type is EventType.WRITER_PROOF_HELD
        and event.payload.get("held_reason") == "PROTECTED_UNRESOLVED_LEGACY_WRITE"
    ]
    if not legacy_events:
        if protected_holds:
            raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
        return
    if len(legacy_events) != 1 or len(protected_holds) != 1:
        raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
    legacy_event = legacy_events[0]
    expected_payload = _expected_legacy_payload(contract)
    expected_id = f"legacy_{sha256_hex(canonical_json_bytes(expected_payload))}"
    if (
        legacy_event.event_id != expected_id
        or legacy_event.incident_id != contract.incident_id
        or dict(legacy_event.payload) != expected_payload
        or protected_holds[0].incident_id != contract.incident_id
        or dict(protected_holds[0].payload) != {
            "conflict_domain_ref": contract.conflict_domain_ref,
            "held_reason": "PROTECTED_UNRESOLVED_LEGACY_WRITE",
            "protected_unresolved_write_event_ids": [expected_id],
            "writer_proof_id": contract.writer_proof_id,
        }
    ):
        raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)


class LegacyImportOnlyHandle:
    """Structurally restricted local bootstrap capability.

    Its public surface contains only inspection, evidence validation, exact
    import commit, and close.  In particular it provides no generic append,
    writer session, send gate, transport, signing, or proof-release method.
    """

    __slots__ = ("__locked", "__contract", "__validated")

    def __init__(self, locked: LockedLedger, contract: LegacyIncidentContract) -> None:
        self.__locked = locked
        self.__contract = contract
        self.__validated: ValidatedLegacyEvidence | None = None

    def inspect_validated_projection(self) -> SafetyProjection:
        return self.__locked.projection()

    def validate_legacy_evidence(self, evidence_files: Mapping[str, bytes]) -> ValidatedLegacyEvidence:
        validated = validate_legacy_evidence(evidence_files, contract=self.__contract)
        self.__validated = validated
        return validated

    def commit_exact_legacy_import(
        self,
        validated: ValidatedLegacyEvidence | None = None,
    ) -> LegacyImportResult:
        evidence = validated or self.__validated
        if evidence is None or evidence.contract != self.__contract:
            raise LedgerError(FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)
        before = self.__locked.projection()
        if before.history_completeness != "INCOMPLETE":
            raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
        legacy = EventInput(
            EventType.LEGACY_INCIDENT_IMPORTED,
            evidence.payload,
            writer_session_id=None,
            incident_id=self.__contract.incident_id,
            execution_attempt_id=None,
            event_id=evidence.deterministic_event_id,
        )
        hold = EventInput(
            EventType.WRITER_PROOF_HELD,
            {
                "conflict_domain_ref": self.__contract.conflict_domain_ref,
                "held_reason": "PROTECTED_UNRESOLVED_LEGACY_WRITE",
                "protected_unresolved_write_event_ids": [evidence.deterministic_event_id],
                "writer_proof_id": self.__contract.writer_proof_id,
            },
            writer_session_id=None,
            incident_id=self.__contract.incident_id,
            execution_attempt_id=None,
        )
        try:
            result = self.__locked.append_batch((legacy, hold))
        except LedgerError:
            # Every failed/unknown import commit path is a local halt.  Release
            # both exclusive locks and require explicit reopen; never retry the
            # batch through the same handle.
            self.__locked.close()
            raise
        projection = self.__locked.projection()
        _validate_current_import_projection(projection, self.__contract)
        return LegacyImportResult(
            LegacyImportStatus.FULLY_AUTHORITY_ANCHORED,
            0 if result.status is AppendStatus.IDEMPOTENT_DUPLICATE else 2,
            projection,
            result.first_sequence,
            result.last_sequence,
            result.terminal_event_hash,
        )

    def close(self) -> None:
        self.__locked.close()


def _validate_current_import_projection(projection: SafetyProjection, contract: LegacyIncidentContract) -> None:
    incident = projection.legacy_incident_state_by_incident.get(contract.incident_id)
    if (
        projection.history_completeness != "COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE"
        or projection.restart_classification is not RestartClassification.UNRESOLVED_WRITE_HELD
        or projection.protected_unresolved_legacy_write_count != 1
        or projection.reconciliation_disposition_by_incident.get(contract.incident_id) != CURRENT_DISPOSITION
        or projection.writer_proof_state_by_proof_id.get(contract.writer_proof_id) != "HELD"
        or projection.writer_proof_release_eligible_by_proof_id.get(contract.writer_proof_id) is not False
        or incident is None
        or dict(incident) != {
            "active_order_upper_bound": 1,
            "bound_order_id": None,
            "created_order_upper_bound": 1,
            "disposition": CURRENT_DISPOSITION,
            "unknown_result": True,
            "writer_proof_release_eligible": False,
            "writer_proof_state": "HELD",
        }
    ):
        raise LedgerError(FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)


def acquire_legacy_import_only(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    contract: LegacyIncidentContract = CURRENT_LEGACY_INCIDENT_CONTRACT,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> LegacyImportAcquisition:
    kwargs: dict[str, object] = {}
    if clock is not None:
        kwargs["clock"] = clock
    if uuid_factory is not None:
        kwargs["uuid_factory"] = uuid_factory
    if fault_hook is not None:
        kwargs["fault_hook"] = fault_hook
    opened = _acquire_legacy_import_state(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_bound_legacy_history(events, contract),
        **kwargs,
    )
    if opened.locked is not None:
        return LegacyImportAcquisition(opened.restart_classification, opened.projection, LegacyImportOnlyHandle(opened.locked, contract), None, None)
    completed: LegacyImportResult | None = None
    if opened.projection is not None and opened.projection.history_completeness == "COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE":
        _validate_current_import_projection(opened.projection, contract)
        # The private restricted acquisition bridge performs any required
        # validated forward catch-up before returning.  Its projection is
        # therefore fully anchored.
        status = (
            LegacyImportStatus.ALREADY_COMMITTED_CATCHUP_COMPLETED
            if opened.authority_ledger_relation is AuthorityLedgerRelation.LEDGER_AHEAD
            else LegacyImportStatus.ALREADY_COMPLETED_AND_ANCHORED
        )
        completed = LegacyImportResult(status, 0, opened.projection)
    return LegacyImportAcquisition(opened.restart_classification, opened.projection, None, completed, opened.failure_code)


class EmergencyControlLedgerHandle:
    """Narrow persistent emergency-control capability; never a venue capability."""

    __slots__ = ("__locked", "__session_id", "__closed")

    def __init__(self, locked: LockedLedger, session_id: str) -> None:
        self.__locked = locked
        self.__session_id = session_id
        self.__closed = False

    @property
    def restricted_session_id(self) -> str:
        return self.__session_id

    def inspect_validated_projection(self) -> SafetyProjection:
        return self.__locked.projection()

    def _record(self, event_type: EventType, payload: Mapping[str, object], *, event_id: str | None = None, recorded_at_utc: str | None = None):
        if self.__closed:
            raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
        return self.__locked.append_batch((EventInput(
            event_type, payload, writer_session_id=self.__session_id,
            event_id=event_id, recorded_at_utc=recorded_at_utc,
        ),))

    def record_risk_control_state_changed(self, payload: Mapping[str, object], *, event_id: str | None = None, recorded_at_utc: str | None = None):
        if payload.get("new_state") == "SAFE_HELD":
            projection = self.__locked.projection()
            if (
                projection.protected_unresolved_legacy_write_count != 0
                or projection.unresolved_write_request_ids
                or any(projection.cancel_send_may_have_been_sent_by_attempt.values())
                or any(
                    state == "HELD"
                    and projection.writer_proof_release_eligible_by_proof_id.get(proof_id) is not True
                    for proof_id, state in projection.writer_proof_state_by_proof_id.items()
                )
            ):
                raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        return self._record(EventType.RISK_CONTROL_STATE_CHANGED, payload, event_id=event_id, recorded_at_utc=recorded_at_utc)

    def open_emergency_action(self, payload: Mapping[str, object], *, event_id: str | None = None, recorded_at_utc: str | None = None):
        return self._record(EventType.EMERGENCY_ACTION_OPENED, payload, event_id=event_id, recorded_at_utc=recorded_at_utc)

    def record_cancel_intent(self, payload: Mapping[str, object], *, event_id: str | None = None, recorded_at_utc: str | None = None):
        return self._record(EventType.CANCEL_INTENT_RECORDED, payload, event_id=event_id, recorded_at_utc=recorded_at_utc)

    def record_cancel_send_boundary(self, payload: Mapping[str, object], *, event_id: str | None = None, recorded_at_utc: str | None = None):
        return self._record(EventType.CANCEL_SEND_BOUNDARY_ENTERED, payload, event_id=event_id, recorded_at_utc=recorded_at_utc)

    def record_cancel_result(self, payload: Mapping[str, object], *, event_id: str | None = None, recorded_at_utc: str | None = None):
        return self._record(EventType.CANCEL_RESULT_RECORDED, payload, event_id=event_id, recorded_at_utc=recorded_at_utc)

    def record_order_observation(self, payload: Mapping[str, object], *, incident_id: str | None = None):
        return self.__locked.append_batch((EventInput(EventType.ORDER_OBSERVED, payload, self.__session_id, incident_id),))

    def record_fill_observation(self, payload: Mapping[str, object], *, incident_id: str | None = None):
        return self.__locked.append_batch((EventInput(EventType.FILL_OBSERVED, payload, self.__session_id, incident_id),))

    def record_reconciliation(self, payload: Mapping[str, object], *, incident_id: str):
        return self.__locked.append_batch((EventInput(EventType.RECONCILIATION_RECORDED, payload, self.__session_id, incident_id),))

    def record_execution_halt(self, payload: Mapping[str, object], *, incident_id: str | None = None):
        return self.__locked.append_batch((EventInput(EventType.EXECUTION_HALTED, payload, self.__session_id, incident_id),))

    def record_writer_proof_held(self, payload: Mapping[str, object], *, incident_id: str | None = None):
        return self.__locked.append_batch((EventInput(EventType.WRITER_PROOF_HELD, payload, self.__session_id, incident_id),))

    def close(self) -> None:
        if self.__closed:
            return
        self.__closed = True
        end_restricted_session(
            self.__locked, restricted_session_id=self.__session_id,
            acquisition_mode=AcquisitionMode.EMERGENCY_CONTROL_ONLY,
        )


_RELEASE_PREDICATE_KEYS = (
    "ledger_integrity_pass",
    "authority_anchor_consistency_pass",
    "binding_identity_pass",
    "supported_event_set_pass",
    "trusted_replay_complete",
    "no_unresolved_emergency_cancel",
    "known_active_orders_reconciled",
    "fills_reconciled",
    "zero_identity_conflicts",
    "conservative_exposure_finite_and_within_limits",
    "risk_config_complete_valid",
    "market_data_fresh",
    "reconciliation_fresh",
    "venue_defense_pass",
    "protected_unresolved_legacy_write_count_zero",
    "no_controlling_unresolved_write",
    "writer_proof_release_eligible",
    "state_safe_held",
    "no_outstanding_permits",
)


def _exact_tuple(value: object, item_type: type, failure: FailureCode) -> tuple:
    if type(value) is not tuple or any(type(item) is not item_type for item in value):
        raise LedgerError(failure)
    return value


def _canonical_economic_fill(fill: EconomicFillV1) -> Mapping[str, object]:
    return {
        "authoritative_created_time_utc": fill.authoritative_created_time_utc,
        "fill_id": fill.fill_id,
        "market": fill.market,
        "outcome_side": fill.outcome_side,
        "quantity": fill.quantity,
        "yes_price": fill.yes_price,
    }


def _canonical_working_order(order: WorkingOrderV1) -> Mapping[str, object]:
    return {
        "market": order.market,
        "order_id": order.order_id,
        "outcome_side": order.outcome_side,
        "remaining_quantity": order.remaining_quantity,
        "status": order.status,
        "yes_price": order.yes_price,
    }


@dataclass(frozen=True, slots=True)
class ReleaseRiskSnapshotV1:
    """Exact economic and market inputs used for one release evaluation."""

    fills: tuple[EconomicFillV1, ...]
    working_orders: tuple[WorkingOrderV1, ...]
    unresolved_write_count: int
    unresolved_write_exposure_usd: Decimal | str
    market_data_snapshot: Mapping[str, object]

    def __post_init__(self) -> None:
        _exact_tuple(self.fills, EconomicFillV1, FailureCode.RELEASE_PREDICATE_FAILED)
        _exact_tuple(self.working_orders, WorkingOrderV1, FailureCode.RELEASE_PREDICATE_FAILED)
        if type(self.unresolved_write_count) is not int or self.unresolved_write_count < 0:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        exposure = self.unresolved_write_exposure_usd
        if not (
            type(exposure) is str and exposure == UNKNOWN_UNBOUNDED
            or type(exposure) is Decimal and exposure.is_finite() and exposure >= 0
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if type(self.market_data_snapshot) is not dict:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        # Validate now and retain a private immutable copy.  No repr/object
        # address participates in the persisted identity.
        canonical_json_bytes(self.market_data_snapshot)
        object.__setattr__(self, "market_data_snapshot", MappingProxyType(dict(self.market_data_snapshot)))

    def canonical_object(self) -> Mapping[str, object]:
        return {
            "fills": [
                _canonical_economic_fill(item)
                for item in sorted(self.fills, key=lambda value: (value.authoritative_created_time_utc, value.fill_id))
            ],
            "market_data_snapshot": dict(self.market_data_snapshot),
            "unresolved_write_count": self.unresolved_write_count,
            "unresolved_write_exposure_usd": self.unresolved_write_exposure_usd,
            "working_orders": [
                _canonical_working_order(item)
                for item in sorted(self.working_orders, key=lambda value: (value.market, value.order_id))
            ],
        }

    @property
    def sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.canonical_object()))

    @property
    def market_data_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(dict(self.market_data_snapshot)))


@dataclass(frozen=True, slots=True)
class ReleaseReconciliationSnapshotV1:
    """Exact reconciled identities and their trusted-ledger evidence refs."""

    authoritative_known_active_order_ids: tuple[str, ...]
    reconciled_order_ids: tuple[str, ...]
    reconciled_fill_ids: tuple[str, ...]
    identity_conflict_ids: tuple[str, ...]
    unresolved_emergency_cancel_attempt_ids: tuple[str, ...]
    order_evidence_event_ids: tuple[tuple[str, str], ...]
    fill_evidence_event_ids: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        for value in (
            self.authoritative_known_active_order_ids,
            self.reconciled_order_ids,
            self.reconciled_fill_ids,
            self.identity_conflict_ids,
            self.unresolved_emergency_cancel_attempt_ids,
        ):
            if type(value) is not tuple or any(type(item) is not str or not item for item in value):
                raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
            if tuple(sorted(set(value))) != value:
                raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        for refs in (self.order_evidence_event_ids, self.fill_evidence_event_ids):
            if (
                type(refs) is not tuple
                or any(
                    type(item) is not tuple
                    or len(item) != 2
                    or any(type(part) is not str or not part for part in item)
                    for item in refs
                )
                or tuple(sorted(set(refs))) != refs
            ):
                raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)

    def canonical_object(self) -> Mapping[str, object]:
        return {
            "authoritative_known_active_order_ids": list(self.authoritative_known_active_order_ids),
            "fill_evidence_event_ids": [list(item) for item in self.fill_evidence_event_ids],
            "identity_conflict_ids": list(self.identity_conflict_ids),
            "order_evidence_event_ids": [list(item) for item in self.order_evidence_event_ids],
            "reconciled_fill_ids": list(self.reconciled_fill_ids),
            "reconciled_order_ids": list(self.reconciled_order_ids),
            "unresolved_emergency_cancel_attempt_ids": list(self.unresolved_emergency_cancel_attempt_ids),
        }

    @property
    def sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.canonical_object()))


_VENUE_DEFENSE_EVIDENCE_KEY = object()
_VENUE_DEFENSE_OBSERVATION_KEYS = frozenset({
    "observation_schema_id", "order_group_id", "order_group_state",
    "member_order_ids", "cancel_order_on_pause_order_ids",
    "membership_conflict_order_ids",
})


@dataclass(frozen=True, slots=True, init=False)
class VenueDefenseEvidenceV1:
    """Dormant process-local data; never authoritative Order Group proof."""

    process_instance_id: str
    observation_id: str
    canonical_observation_sha256: str
    order_group_id: str | None
    order_group_state: str
    member_order_ids: tuple[str, ...]
    cancel_order_on_pause_order_ids: tuple[str, ...]
    membership_conflict_order_ids: tuple[str, ...]
    reconciliation_snapshot_sha256: str
    freshness: FreshnessStampV1

    def __init__(self, key: object, **values: object) -> None:
        if key is not _VENUE_DEFENSE_EVIDENCE_KEY:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def __copy__(self):
        raise TypeError("VenueDefenseEvidenceV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("VenueDefenseEvidenceV1 cannot be serialized")


def validate_venue_defense_evidence(
    *,
    process_instance_id: str,
    canonical_observation: Mapping[str, object],
    canonical_observation_sha256: str,
    reconciliation_snapshot_sha256: str,
    freshness: FreshnessStampV1,
) -> VenueDefenseEvidenceV1:
    """Validate legacy assertion shape without granting release authority.

    This factory is retained only for compatibility with callers that need to
    validate the dormant data shape.  The repository has no accepted
    authoritative Order Group observation adapter, so objects returned here
    are deliberately incapable of satisfying ``REQUIRED_FOR_EXPERIMENT``.
    """

    if (
        type(process_instance_id) is not str or not process_instance_id
        or type(canonical_observation) is not dict
        or set(canonical_observation) != _VENUE_DEFENSE_OBSERVATION_KEYS
        or type(canonical_observation_sha256) is not str
        or type(reconciliation_snapshot_sha256) is not str
        or type(freshness) is not FreshnessStampV1
    ):
        raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
    expected_hash = sha256_hex(canonical_json_bytes(canonical_observation))
    if (
        canonical_observation_sha256 != expected_hash
        or freshness.snapshot_sha256 != expected_hash
        or freshness.process_instance_id != process_instance_id
        or len(reconciliation_snapshot_sha256) != 64
        or any(character not in "0123456789abcdef" for character in reconciliation_snapshot_sha256)
        or canonical_observation["observation_schema_id"]
        != "KALSHI_VENUE_DEFENSE_OBSERVATION_V1"
    ):
        raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
    group_id = canonical_observation["order_group_id"]
    group_state = canonical_observation["order_group_state"]
    if (
        group_id is not None and (type(group_id) is not str or not group_id)
        or group_state not in {"ACTIVE", "NOT_APPLICABLE"}
        or group_id is None and group_state != "NOT_APPLICABLE"
        or group_id is not None and group_state != "ACTIVE"
    ):
        raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)

    def validated_ids(name: str) -> tuple[str, ...]:
        value = canonical_observation[name]
        if (
            type(value) is not list
            or any(type(item) is not str or not item for item in value)
            or value != sorted(set(value))
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        return tuple(value)

    members = validated_ids("member_order_ids")
    cancel_on_pause = validated_ids("cancel_order_on_pause_order_ids")
    conflicts = validated_ids("membership_conflict_order_ids")
    return VenueDefenseEvidenceV1(
        _VENUE_DEFENSE_EVIDENCE_KEY,
        process_instance_id=process_instance_id,
        observation_id=f"vdo_{canonical_observation_sha256}",
        canonical_observation_sha256=canonical_observation_sha256,
        order_group_id=group_id,
        order_group_state=group_state,
        member_order_ids=members,
        cancel_order_on_pause_order_ids=cancel_on_pause,
        membership_conflict_order_ids=conflicts,
        reconciliation_snapshot_sha256=reconciliation_snapshot_sha256,
        freshness=freshness,
    )


_UNSET = object()


class ReleaseEvaluationStateV1:
    """Process-local current inputs re-read at every durable release stage."""

    __slots__ = (
        "__identity", "__lock", "__version", "__process_instance_id",
        "__incident_id", "__writer_proof_id", "__risk_config", "__risk_snapshot",
        "__reconciliation_snapshot", "__market_freshness", "__reconciliation_freshness",
        "__venue_defense_evidence", "__normal_gate", "__emergency_gate",
    )

    def __init__(
        self,
        *,
        process_instance_id: str,
        incident_id: str,
        writer_proof_id: str,
        risk_config: RiskLimitConfigV1 | None,
        risk_snapshot: ReleaseRiskSnapshotV1,
        reconciliation_snapshot: ReleaseReconciliationSnapshotV1,
        market_freshness: FreshnessStampV1 | None,
        reconciliation_freshness: FreshnessStampV1 | None,
        venue_defense_evidence: VenueDefenseEvidenceV1 | None,
        normal_gate: WriterEligibilityGate,
        emergency_gate: object,
    ) -> None:
        if (
            type(process_instance_id) is not str
            or type(incident_id) is not str or not incident_id
            or type(writer_proof_id) is not str or not writer_proof_id
            or risk_config is not None and type(risk_config) is not RiskLimitConfigV1
            or type(risk_snapshot) is not ReleaseRiskSnapshotV1
            or type(reconciliation_snapshot) is not ReleaseReconciliationSnapshotV1
            or market_freshness is not None and type(market_freshness) is not FreshnessStampV1
            or reconciliation_freshness is not None and type(reconciliation_freshness) is not FreshnessStampV1
            or venue_defense_evidence is not None
            and type(venue_defense_evidence) is not VenueDefenseEvidenceV1
            or type(normal_gate) is not WriterEligibilityGate
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        # Lazy import avoids a module cycle: emergency_cancel depends on this
        # module for its narrow ledger handle.
        from arb.venues.kalshi.emergency_cancel import EmergencyCancelGate
        if type(emergency_gate) is not EmergencyCancelGate:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        self.__identity = object()
        self.__lock = threading.RLock()
        self.__version = 0
        self.__process_instance_id = process_instance_id
        self.__incident_id = incident_id
        self.__writer_proof_id = writer_proof_id
        self.__risk_config = risk_config
        self.__risk_snapshot = risk_snapshot
        self.__reconciliation_snapshot = reconciliation_snapshot
        self.__market_freshness = market_freshness
        self.__reconciliation_freshness = reconciliation_freshness
        self.__venue_defense_evidence = venue_defense_evidence
        self.__normal_gate = normal_gate
        self.__emergency_gate = emergency_gate

    def replace(
        self,
        *,
        risk_config: object = _UNSET,
        risk_snapshot: object = _UNSET,
        reconciliation_snapshot: object = _UNSET,
        market_freshness: object = _UNSET,
        reconciliation_freshness: object = _UNSET,
        venue_defense_evidence: object = _UNSET,
    ) -> None:
        """Atomically replace typed current evidence and invalidate assessments."""
        with self.__lock:
            candidates = {
                "risk_config": (risk_config, (RiskLimitConfigV1, type(None))),
                "risk_snapshot": (risk_snapshot, (ReleaseRiskSnapshotV1,)),
                "reconciliation_snapshot": (reconciliation_snapshot, (ReleaseReconciliationSnapshotV1,)),
                "market_freshness": (market_freshness, (FreshnessStampV1, type(None))),
                "reconciliation_freshness": (reconciliation_freshness, (FreshnessStampV1, type(None))),
                "venue_defense_evidence": (
                    venue_defense_evidence, (VenueDefenseEvidenceV1, type(None)),
                ),
            }
            for name, (value, accepted) in candidates.items():
                if value is _UNSET:
                    continue
                if type(value) not in accepted:
                    raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
                setattr(self, f"_ReleaseEvaluationStateV1__{name}", value)
            self.__version += 1

    def _snapshot(self) -> tuple[object, ...]:
        with self.__lock:
            return (
                self.__identity, self.__version, self.__process_instance_id,
                self.__incident_id, self.__writer_proof_id, self.__risk_config,
                self.__risk_snapshot, self.__reconciliation_snapshot,
                self.__market_freshness, self.__reconciliation_freshness,
                self.__venue_defense_evidence, self.__normal_gate, self.__emergency_gate,
            )

    def __copy__(self):
        raise TypeError("ReleaseEvaluationStateV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("ReleaseEvaluationStateV1 cannot be serialized")


_RELEASE_ASSESSMENT_KEY = object()


@dataclass(frozen=True, slots=True, init=False)
class ReleaseAssessmentV1:
    release_id: str
    restricted_session_id: str
    process_instance_id: str
    risk_config_sha256: str
    risk_state_epoch: int
    safe_held_state_event_id: str
    safe_held_state_event_hash: str
    risk_snapshot_sha256: str
    reconciliation_snapshot_sha256: str
    predicate_vector: Mapping[str, bool]
    predicate_vector_sha256: str
    writer_proof_id: str
    evaluated_trusted_sequence: int
    evaluated_trusted_hash: str
    evaluated_monotonic_ns: int
    private_evaluator_identity: object
    private_source_identity: object
    source_version: int

    def __init__(self, key: object, **values: object) -> None:
        if key is not _RELEASE_ASSESSMENT_KEY:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def __copy__(self):
        raise TypeError("ReleaseAssessmentV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("ReleaseAssessmentV1 cannot be serialized")


@dataclass(slots=True)
class _ReleaseProgress:
    assessment: ReleaseAssessmentV1
    source: ReleaseEvaluationStateV1
    release_event_id: str | None = None
    release_event_hash: str | None = None
    proof_event_id: str | None = None
    proof_event_hash: str | None = None
    last_monotonic_ns: int = 0


@dataclass(frozen=True, slots=True)
class _AuthoritativeReleaseUniverse:
    working_orders: tuple[WorkingOrderV1, ...]
    fills: tuple[EconomicFillV1, ...]
    cancel_order_on_pause_order_ids: tuple[str, ...]
    latest_order_event_ids: Mapping[str, str]
    fill_event_ids: Mapping[str, tuple[str, ...]]
    conflict_ids: tuple[str, ...]


class ReleaseLedgerHandle:
    """Narrow evaluator-backed durable release capability.

    No supported method accepts an authoritative predicate vector or snapshot
    hash.  Those values exist only as outputs of ``evaluate_release`` and are
    copied into durable events after stage-local revalidation.
    """

    __slots__ = (
        "__locked", "__session_id", "__closed", "__identity", "__monotonic",
        "__wall", "__uuid", "__progress",
    )

    def __init__(
        self,
        locked: LockedLedger,
        session_id: str,
        *,
        monotonic_clock_ns: Callable[[], int] = time.monotonic_ns,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        self.__locked = locked
        self.__session_id = session_id
        self.__closed = False
        self.__identity = object()
        self.__monotonic = monotonic_clock_ns
        self.__wall = wall_clock
        self.__uuid = uuid_factory
        self.__progress: dict[int, _ReleaseProgress] = {}

    @property
    def restricted_session_id(self) -> str:
        return self.__session_id

    def inspect_validated_projection(self) -> SafetyProjection:
        return self.__locked.projection()

    @staticmethod
    def _evidence_event_matches(
        events_by_id: Mapping[str, object],
        refs: Sequence[tuple[str, str]],
        expected_type: EventType,
        payload_identity_key: str,
    ) -> bool:
        for identity, event_id in refs:
            event = events_by_id.get(event_id)
            if (
                event is None
                or event.event_type is not expected_type
                or event.payload.get(payload_identity_key) != identity
            ):
                return False
        return True

    @staticmethod
    def _stored_decimal_matches(value: object, expected: Decimal) -> bool:
        """Compare a parsed durable JSON Decimal tag with an economic Decimal."""
        expected_tag = json.loads(canonical_json_bytes(expected).decode("utf-8"))
        return value == expected_tag

    @staticmethod
    def _stored_decimal_value(value: object) -> Decimal | None:
        if not isinstance(value, Mapping) or set(value) != {"$decimal"}:
            return None
        text = value.get("$decimal")
        if type(text) is not str:
            return None
        try:
            parsed = Decimal(text)
        except Exception:
            return None
        if not parsed.is_finite():
            return None
        expected_tag = json.loads(canonical_json_bytes(parsed).decode("utf-8"))
        return parsed if value == expected_tag else None

    @staticmethod
    def _positive_qty2(value: object) -> Decimal | None:
        if type(value) is not str:
            return None
        try:
            parsed = Decimal(value)
        except Exception:
            return None
        if not parsed.is_finite() or parsed <= 0 or format(parsed, ".2f") != value:
            return None
        return parsed

    def _authoritative_release_universe(self) -> _AuthoritativeReleaseUniverse:
        """Derive the complete current economic universe from trusted replay."""

        projection = self.__locked.projection()
        latest_orders: dict[str, object] = {}
        fill_events: dict[str, list[object]] = {}
        conflicts: set[str] = set(projection.fill_conflicts)
        for event in self.__locked.events:
            if event.event_type is EventType.ORDER_OBSERVED:
                order_id = event.payload.get("venue_order_id")
                content = event.payload.get("canonical_venue_payload")
                if type(order_id) is not str or not order_id or not isinstance(content, Mapping):
                    conflicts.add(f"order-event:{event.event_id}")
                    continue
                if content.get("order_id") != order_id:
                    conflicts.add(f"order-identity:{order_id}")
                latest_orders[order_id] = event
            elif event.event_type is EventType.FILL_OBSERVED:
                fill_id = event.payload.get("venue_fill_id")
                content = event.payload.get("canonical_venue_payload")
                if type(fill_id) is not str or not fill_id or not isinstance(content, Mapping):
                    conflicts.add(f"fill-event:{event.event_id}")
                    continue
                if (
                    content.get("fill_id") != fill_id
                    or content.get("order_id") != event.payload.get("venue_order_id")
                ):
                    conflicts.add(f"fill-identity:{fill_id}")
                fill_events.setdefault(fill_id, []).append(event)

        if set(latest_orders) != set(projection.order_observation_history):
            conflicts.add("order-replay-universe")
        if set(fill_events) != set(projection.canonical_fills_by_fill_id):
            conflicts.add("fill-replay-universe")

        orders: list[WorkingOrderV1] = []
        cancel_order_on_pause_ids: list[str] = []
        latest_order_ids: dict[str, str] = {}
        for order_id, event in sorted(latest_orders.items()):
            content = event.payload.get("canonical_venue_payload")
            if not isinstance(content, Mapping):
                conflicts.add(f"order-content:{order_id}")
                continue
            latest_order_ids[order_id] = event.event_id
            status = content.get("status")
            if type(status) is not str or not status:
                conflicts.add(f"order-status:{order_id}")
                continue
            if status != "resting":
                continue
            remaining = self._positive_qty2(content.get("remaining_count_fp"))
            yes_price = self._stored_decimal_value(content.get("yes_price"))
            try:
                if remaining is None or yes_price is None:
                    raise ValueError
                orders.append(WorkingOrderV1(
                    content.get("market"), order_id, content.get("outcome_side"),
                    remaining, yes_price,
                ))
                if content.get("cancel_order_on_pause") is True:
                    cancel_order_on_pause_ids.append(order_id)
            except (RiskControlError, ValueError):
                conflicts.add(f"order-economic:{order_id}")

        fills: list[EconomicFillV1] = []
        fill_event_ids: dict[str, tuple[str, ...]] = {}
        for fill_id, canonical in sorted(projection.canonical_fills_by_fill_id.items()):
            candidates = fill_events.get(fill_id, [])
            matching = tuple(
                event for event in candidates
                if event.payload.get("canonical_venue_payload") == canonical
            )
            fill_event_ids[fill_id] = tuple(event.event_id for event in matching)
            if not matching or not isinstance(canonical, Mapping):
                conflicts.add(f"fill-content:{fill_id}")
                continue
            quantity = self._stored_decimal_value(canonical.get("quantity"))
            yes_price = self._stored_decimal_value(canonical.get("price"))
            try:
                if quantity is None or yes_price is None:
                    raise ValueError
                fills.append(EconomicFillV1(
                    canonical.get("market"), fill_id, canonical.get("outcome_side"),
                    quantity, yes_price, canonical.get("authoritative_created_time_utc"),
                ))
            except (RiskControlError, ValueError):
                conflicts.add(f"fill-economic:{fill_id}")

        return _AuthoritativeReleaseUniverse(
            tuple(orders), tuple(fills), tuple(sorted(cancel_order_on_pause_ids)),
            MappingProxyType(latest_order_ids), MappingProxyType(fill_event_ids),
            tuple(sorted(conflicts)),
        )

    @staticmethod
    def _economic_release_pass(
        risk: ReleaseRiskSnapshotV1,
        config: RiskLimitConfigV1 | None,
    ) -> bool:
        if config is None or risk.unresolved_write_exposure_usd == UNKNOWN_UNBOUNDED:
            return False
        unresolved = risk.unresolved_write_exposure_usd
        assert type(unresolved) is Decimal
        if (
            risk.unresolved_write_count > config.conflict_domain_account.max_unresolved_write_count
            or unresolved > config.conflict_domain_account.max_conservative_unresolved_write_exposure_usd
        ):
            return False
        markets = sorted({item.market for item in risk.fills} | {item.market for item in risk.working_orders})
        aggregate_exposure = unresolved
        aggregate_working_orders = 0
        aggregate_working_contracts = Decimal("0")
        for market in markets:
            state = compute_market_economic_state(market, risk.fills, risk.working_orders)
            market_orders = tuple(item for item in risk.working_orders if item.market == market)
            if any(
                order.remaining_quantity > config.per_order.max_contracts
                or order.remaining_quantity
                * (order.yes_price if order.outcome_side == "YES" else Decimal("1.0000") - order.yes_price)
                > config.per_order.max_worst_case_exposure_usd
                for order in market_orders
            ):
                return False
            worst_net = max(
                abs(state.signed_net_position + state.working_bid_quantity),
                abs(state.signed_net_position - state.working_ask_quantity),
            )
            gross = state.filled_exposure_usd + state.working_exposure_usd
            if (
                worst_net > config.per_market.max_abs_net_position_contracts
                or gross > config.per_market.max_gross_exposure_usd
                or state.working_order_count > config.per_market.max_authoritative_working_orders
                or state.working_contracts > config.per_market.max_working_contracts
                or state.working_exposure_usd > config.per_market.max_working_order_exposure_usd
            ):
                return False
            aggregate_exposure += gross
            aggregate_working_orders += state.working_order_count
            aggregate_working_contracts += state.working_contracts
        return (
            aggregate_exposure <= config.conflict_domain_account.max_aggregate_exposure_usd
            and aggregate_working_orders <= config.conflict_domain_account.max_aggregate_working_orders
            and aggregate_working_contracts <= config.conflict_domain_account.max_aggregate_working_contracts
        )

    def _derive(
        self,
        source: ReleaseEvaluationStateV1,
        *,
        prior_monotonic_ns: int | None,
        proof_released_expected: bool,
    ) -> tuple[Mapping[str, bool], Mapping[str, object]]:
        if self.__closed or type(source) is not ReleaseEvaluationStateV1:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        (
            source_identity, source_version, process_instance_id, incident_id,
            writer_proof_id, config, risk, reconciliation, market_freshness,
            reconciliation_freshness, venue_evidence, normal_gate, emergency_gate,
        ) = source._snapshot()
        projection = self.__locked.projection()
        tail = self.__locked.events[-1]
        authority = self.__locked.authority_row
        now_monotonic_ns = self.__monotonic()
        if type(now_monotonic_ns) is not int or now_monotonic_ns < 0:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        now_utc = canonical_timestamp(self.__wall())
        events_by_id = {event.event_id: event for event in self.__locked.events}

        universe = self._authoritative_release_universe()
        authoritative_risk = ReleaseRiskSnapshotV1(
            fills=universe.fills,
            working_orders=universe.working_orders,
            unresolved_write_count=risk.unresolved_write_count,
            unresolved_write_exposure_usd=risk.unresolved_write_exposure_usd,
            market_data_snapshot=dict(risk.market_data_snapshot),
        )
        risk_hash = authoritative_risk.sha256
        reconciliation_hash = reconciliation.sha256
        config_valid = (
            type(config) is RiskLimitConfigV1
            and config.conflict_domain == self.__locked.conflict_domain_ref
            and projection.active_risk_config_sha256 == config.sha256
        )
        known_order_ids = tuple(sorted(item.order_id for item in universe.working_orders))
        fill_ids = tuple(sorted(item.fill_id for item in universe.fills))
        supplied_order_ids = tuple(sorted(item.order_id for item in risk.working_orders))
        supplied_fill_ids = tuple(sorted(item.fill_id for item in risk.fills))
        supplied_orders = {item.order_id: item for item in risk.working_orders}
        supplied_fills = {item.fill_id: item for item in risk.fills}
        order_refs = tuple(reconciliation.order_evidence_event_ids)
        fill_refs = tuple(reconciliation.fill_evidence_event_ids)
        order_ref_by_id = dict(order_refs)
        fill_ref_by_id = dict(fill_refs)
        order_content_matches = True
        for order in universe.working_orders:
            event = events_by_id.get(order_ref_by_id.get(order.order_id, ""))
            content = None if event is None else event.payload.get("canonical_venue_payload")
            if (
                event is None
                or event.event_type is not EventType.ORDER_OBSERVED
                or event.event_id != universe.latest_order_event_ids.get(order.order_id)
                or not isinstance(content, Mapping)
                or content.get("order_id") != order.order_id
                or content.get("market") != order.market
                or content.get("outcome_side") != order.outcome_side
                or content.get("remaining_count_fp") != f"{order.remaining_quantity:.2f}"
                or not self._stored_decimal_matches(
                    content.get("yes_price"), order.yes_price,
                )
                or content.get("status") != "resting"
            ):
                order_content_matches = False
                break
        fill_content_matches = True
        for fill in universe.fills:
            event = events_by_id.get(fill_ref_by_id.get(fill.fill_id, ""))
            content = None if event is None else event.payload.get("canonical_venue_payload")
            if (
                event is None
                or event.event_type is not EventType.FILL_OBSERVED
                or event.event_id not in universe.fill_event_ids.get(fill.fill_id, ())
                or not isinstance(content, Mapping)
                or content.get("fill_id") != fill.fill_id
                or content.get("market") != fill.market
                or content.get("outcome_side") != fill.outcome_side
                or not self._stored_decimal_matches(
                    content.get("quantity"), fill.quantity,
                )
                or not self._stored_decimal_matches(
                    content.get("price"), fill.yes_price,
                )
                or content.get("authoritative_created_time_utc")
                != fill.authoritative_created_time_utc
            ):
                fill_content_matches = False
                break
        known_orders_reconciled = (
            len(set(known_order_ids)) == len(known_order_ids)
            and supplied_order_ids == known_order_ids
            and len(supplied_orders) == len(known_order_ids)
            and all(supplied_orders.get(item.order_id) == item for item in universe.working_orders)
            and reconciliation.authoritative_known_active_order_ids == known_order_ids
            and reconciliation.reconciled_order_ids == known_order_ids
            and tuple(identity for identity, _ in order_refs) == known_order_ids
            and self._evidence_event_matches(events_by_id, order_refs, EventType.ORDER_OBSERVED, "venue_order_id")
            and order_content_matches
        )
        fills_reconciled = (
            len(set(fill_ids)) == len(fill_ids)
            and supplied_fill_ids == fill_ids
            and len(supplied_fills) == len(fill_ids)
            and all(supplied_fills.get(item.fill_id) == item for item in universe.fills)
            and reconciliation.reconciled_fill_ids == fill_ids
            and tuple(identity for identity, _ in fill_refs) == fill_ids
            and self._evidence_event_matches(events_by_id, fill_refs, EventType.FILL_OBSERVED, "venue_fill_id")
            and fill_content_matches
        )

        market_fresh = False
        reconciliation_fresh = False
        if config_valid and type(market_freshness) is FreshnessStampV1:
            try:
                market_fresh = (
                    market_freshness.snapshot_sha256 == authoritative_risk.market_data_sha256
                    and freshness_age_ms(
                        market_freshness,
                        current_process_instance_id=process_instance_id,
                        now_monotonic_ns=now_monotonic_ns,
                        now_utc=now_utc,
                        max_age_ms=min(
                            config.per_order.max_market_data_age_ms,
                            config.state_integrity.max_required_market_data_age_ms,
                        ),
                        max_future_wall_clock_skew_ms=config.state_integrity.max_future_wall_clock_skew_ms,
                        prior_monotonic_ns=prior_monotonic_ns,
                    ) >= 0
                )
            except RiskControlError:
                market_fresh = False
        if config_valid and type(reconciliation_freshness) is FreshnessStampV1:
            try:
                reconciliation_fresh = (
                    reconciliation_freshness.snapshot_sha256 == reconciliation_hash
                    and freshness_age_ms(
                        reconciliation_freshness,
                        current_process_instance_id=process_instance_id,
                        now_monotonic_ns=now_monotonic_ns,
                        now_utc=now_utc,
                        max_age_ms=config.state_integrity.max_reconciliation_lag_ms,
                        max_future_wall_clock_skew_ms=config.state_integrity.max_future_wall_clock_skew_ms,
                        prior_monotonic_ns=prior_monotonic_ns,
                        stale_code=RiskControlCode.RECONCILIATION_STALE,
                    ) >= 0
                )
            except RiskControlError:
                reconciliation_fresh = False

        venue_defense = False
        if config_valid:
            policy = config.venue_defense
            cancel_proven = (
                not policy.cancel_order_on_pause_required
                or universe.cancel_order_on_pause_order_ids == known_order_ids
            )
            if policy.order_group_mode == "NOT_REQUIRED":
                venue_defense = cancel_proven
            elif policy.order_group_mode == "REQUIRED_FOR_EXPERIMENT":
                # No accepted authoritative Order Group reader exists in this
                # implementation stage.  Caller-authored mappings, hashes,
                # freshness stamps, intended CREATE membership, and active-id
                # lists cannot substitute for that missing authority.
                venue_defense = False

        proof_state = projection.writer_proof_state_by_proof_id.get(writer_proof_id)
        proof_pass = (
            proof_state == ("RELEASED" if proof_released_expected else "HELD")
            and projection.writer_proof_release_eligible_by_proof_id.get(writer_proof_id) is True
        )
        safe_event = next(
            (
                event for event in reversed(self.__locked.events)
                if event.event_type is EventType.RISK_CONTROL_STATE_CHANGED
                and event.payload.get("new_state") == "SAFE_HELD"
            ),
            None,
        )
        no_emergency = (
            not any(projection.cancel_send_may_have_been_sent_by_attempt.values())
            and not reconciliation.unresolved_emergency_cancel_attempt_ids
        )
        defense_conflicts = (
            venue_evidence.membership_conflict_order_ids
            if type(venue_evidence) is VenueDefenseEvidenceV1 else ()
        )
        zero_conflicts = (
            not universe.conflict_ids
            and not projection.fill_conflicts
            and not reconciliation.identity_conflict_ids
            and not defense_conflicts
        )
        durable_unresolved_count = (
            projection.protected_unresolved_legacy_write_count
            + len(projection.unresolved_write_request_ids)
        )
        no_outstanding = (
            normal_gate.process_instance_id == process_instance_id
            and getattr(emergency_gate, "process_instance_id", None) == process_instance_id
            and normal_gate.outstanding_permit_count == 0
            and getattr(emergency_gate, "outstanding_permit_count", -1) == 0
        )
        tail_equal = (
            (authority.trusted_sequence, authority.trusted_event_hash)
            == (tail.sequence, tail.event_hash)
            == (projection.trusted_sequence, projection.trusted_event_hash)
            == (projection.last_sequence, projection.terminal_event_hash)
        )
        vector = {
            "ledger_integrity_pass": not self.__locked.closed,
            "authority_anchor_consistency_pass": tail_equal,
            "binding_identity_pass": projection.conflict_domain_ref == self.__locked.conflict_domain_ref,
            "supported_event_set_pass": all(type(event.event_type) is EventType for event in self.__locked.events),
            "trusted_replay_complete": projection.last_sequence == len(self.__locked.events),
            "no_unresolved_emergency_cancel": no_emergency,
            "known_active_orders_reconciled": known_orders_reconciled,
            "fills_reconciled": fills_reconciled,
            "zero_identity_conflicts": zero_conflicts,
            "conservative_exposure_finite_and_within_limits": (
                risk.sha256 == risk_hash
                and self._economic_release_pass(
                    authoritative_risk, config if config_valid else None,
                )
            ),
            "risk_config_complete_valid": config_valid,
            "market_data_fresh": market_fresh,
            "reconciliation_fresh": reconciliation_fresh,
            "venue_defense_pass": venue_defense,
            "protected_unresolved_legacy_write_count_zero": projection.protected_unresolved_legacy_write_count == 0,
            "no_controlling_unresolved_write": not projection.unresolved_write_request_ids and risk.unresolved_write_count == durable_unresolved_count == 0,
            "writer_proof_release_eligible": proof_pass,
            "state_safe_held": projection.risk_control_state == "SAFE_HELD" and safe_event is not None,
            "no_outstanding_permits": no_outstanding,
        }
        if tuple(vector) != _RELEASE_PREDICATE_KEYS:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        metadata: Mapping[str, object] = MappingProxyType({
            "source_identity": source_identity,
            "source_version": source_version,
            "process_instance_id": process_instance_id,
            "incident_id": incident_id,
            "writer_proof_id": writer_proof_id,
            "risk_config_sha256": config.sha256 if type(config) is RiskLimitConfigV1 else "",
            "risk_state_epoch": projection.risk_state_epoch,
            "safe_held_state_event_id": "" if safe_event is None else safe_event.event_id,
            "safe_held_state_event_hash": "" if safe_event is None else safe_event.event_hash,
            "risk_snapshot_sha256": risk_hash,
            "reconciliation_snapshot_sha256": reconciliation_hash,
            "trusted_sequence": tail.sequence,
            "trusted_hash": tail.event_hash,
            "now_monotonic_ns": now_monotonic_ns,
        })
        return MappingProxyType(vector), metadata

    def evaluate_release(self, source: ReleaseEvaluationStateV1) -> ReleaseAssessmentV1:
        vector, metadata = self._derive(
            source, prior_monotonic_ns=None, proof_released_expected=False,
        )
        release_id = f"rel_{self.__uuid().hex}"
        vector_copy = MappingProxyType(dict(vector))
        assessment = ReleaseAssessmentV1(
            _RELEASE_ASSESSMENT_KEY,
            release_id=release_id,
            restricted_session_id=self.__session_id,
            process_instance_id=metadata["process_instance_id"],
            risk_config_sha256=metadata["risk_config_sha256"],
            risk_state_epoch=metadata["risk_state_epoch"],
            safe_held_state_event_id=metadata["safe_held_state_event_id"],
            safe_held_state_event_hash=metadata["safe_held_state_event_hash"],
            risk_snapshot_sha256=metadata["risk_snapshot_sha256"],
            reconciliation_snapshot_sha256=metadata["reconciliation_snapshot_sha256"],
            predicate_vector=vector_copy,
            predicate_vector_sha256=sha256_hex(canonical_json_bytes(dict(vector_copy))),
            writer_proof_id=metadata["writer_proof_id"],
            evaluated_trusted_sequence=metadata["trusted_sequence"],
            evaluated_trusted_hash=metadata["trusted_hash"],
            evaluated_monotonic_ns=metadata["now_monotonic_ns"],
            private_evaluator_identity=self.__identity,
            private_source_identity=metadata["source_identity"],
            source_version=metadata["source_version"],
        )
        self.__progress[id(assessment)] = _ReleaseProgress(
            assessment, source, last_monotonic_ns=assessment.evaluated_monotonic_ns,
        )
        return assessment

    def _context(self, assessment: ReleaseAssessmentV1) -> _ReleaseProgress:
        if (
            type(assessment) is not ReleaseAssessmentV1
            or assessment.private_evaluator_identity is not self.__identity
            or assessment.restricted_session_id != self.__session_id
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        progress = self.__progress.get(id(assessment))
        if progress is None or progress.assessment is not assessment:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        return progress

    def _revalidate(
        self,
        progress: _ReleaseProgress,
        *,
        proof_released_expected: bool,
    ) -> tuple[Mapping[str, bool], Mapping[str, object]]:
        assessment = progress.assessment
        vector, metadata = self._derive(
            progress.source,
            prior_monotonic_ns=progress.last_monotonic_ns,
            proof_released_expected=proof_released_expected,
        )
        stable = (
            metadata["source_identity"] is assessment.private_source_identity
            and metadata["source_version"] == assessment.source_version
            and metadata["process_instance_id"] == assessment.process_instance_id
            and metadata["writer_proof_id"] == assessment.writer_proof_id
            and metadata["risk_config_sha256"] == assessment.risk_config_sha256
            and metadata["risk_state_epoch"] == assessment.risk_state_epoch
            and metadata["safe_held_state_event_id"] == assessment.safe_held_state_event_id
            and metadata["safe_held_state_event_hash"] == assessment.safe_held_state_event_hash
            and metadata["risk_snapshot_sha256"] == assessment.risk_snapshot_sha256
            and metadata["reconciliation_snapshot_sha256"] == assessment.reconciliation_snapshot_sha256
            and all(vector.values())
        )
        if not stable:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        progress.last_monotonic_ns = metadata["now_monotonic_ns"]
        return vector, metadata

    def record_risk_release(self, assessment: ReleaseAssessmentV1):
        """R0: append only an evaluator-derived, freshly revalidated record."""
        progress = self._context(assessment)
        if progress.release_event_id is not None:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        vector, metadata = self._revalidate(progress, proof_released_expected=False)
        if (
            metadata["trusted_sequence"] != assessment.evaluated_trusted_sequence
            or metadata["trusted_hash"] != assessment.evaluated_trusted_hash
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        timestamp = canonical_timestamp(self.__wall())
        payload = {
            "release_id": assessment.release_id,
            "risk_config_sha256": assessment.risk_config_sha256,
            "risk_state_epoch": assessment.risk_state_epoch,
            "authority_trusted_sequence": metadata["trusted_sequence"],
            "authority_trusted_hash": metadata["trusted_hash"],
            "ledger_terminal_sequence": metadata["trusted_sequence"],
            "ledger_terminal_hash": metadata["trusted_hash"],
            "reconciliation_snapshot_sha256": assessment.reconciliation_snapshot_sha256,
            "risk_snapshot_sha256": assessment.risk_snapshot_sha256,
            "predicate_vector": dict(vector),
            "predicate_vector_sha256": assessment.predicate_vector_sha256,
            "writer_proof_id": assessment.writer_proof_id,
            "safe_held_state_event_id": assessment.safe_held_state_event_id,
            "safe_held_state_event_hash": assessment.safe_held_state_event_hash,
            "release_recorded_at_utc": timestamp,
        }
        result = self.__locked.append_batch((EventInput(
            EventType.RISK_RELEASE_RECORDED, payload, self.__session_id,
            recorded_at_utc=timestamp,
        ),))
        event = result.events[-1]
        progress.release_event_id = event.event_id
        progress.release_event_hash = event.event_hash
        return result

    def release_writer_proof(self, assessment: ReleaseAssessmentV1):
        """R1/R2: re-evaluate, match the release event, then release proof."""
        progress = self._context(assessment)
        if progress.release_event_id is None or progress.proof_event_id is not None:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        self._revalidate(progress, proof_released_expected=False)
        prior = self.__locked.events[-1]
        expected_vector = dict(assessment.predicate_vector)
        if (
            prior.event_id != progress.release_event_id
            or prior.event_hash != progress.release_event_hash
            or prior.event_type is not EventType.RISK_RELEASE_RECORDED
            or prior.writer_session_id != self.__session_id
            or prior.payload.get("release_id") != assessment.release_id
            or prior.payload.get("writer_proof_id") != assessment.writer_proof_id
            or prior.payload.get("risk_config_sha256") != assessment.risk_config_sha256
            or prior.payload.get("risk_state_epoch") != assessment.risk_state_epoch
            or prior.payload.get("safe_held_state_event_id") != assessment.safe_held_state_event_id
            or prior.payload.get("safe_held_state_event_hash") != assessment.safe_held_state_event_hash
            or prior.payload.get("risk_snapshot_sha256") != assessment.risk_snapshot_sha256
            or prior.payload.get("reconciliation_snapshot_sha256") != assessment.reconciliation_snapshot_sha256
            or prior.payload.get("predicate_vector") != expected_vector
            or prior.payload.get("predicate_vector_sha256") != assessment.predicate_vector_sha256
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        source_snapshot = progress.source._snapshot()
        incident_id = source_snapshot[3]
        payload = {
            "writer_proof_id": assessment.writer_proof_id,
            "conflict_domain_ref": self.__locked.conflict_domain_ref,
            "release_basis_event_ids": [prior.event_id],
            "release_contract_id": "SPEC_03_SECTION_22",
        }
        result = self.__locked.append_batch((EventInput(
            EventType.WRITER_PROOF_RELEASED, payload, self.__session_id, incident_id,
        ),))
        event = result.events[-1]
        progress.proof_event_id = event.event_id
        progress.proof_event_hash = event.event_hash
        return result

    def record_writer_eligible(self, assessment: ReleaseAssessmentV1):
        """R3/R4: revalidate the expected proof progression and final state."""
        progress = self._context(assessment)
        if progress.proof_event_id is None:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        self._revalidate(progress, proof_released_expected=True)
        projection = self.__locked.projection()
        prior = self.__locked.events[-1]
        if (
            prior.event_id != progress.proof_event_id
            or prior.event_hash != progress.proof_event_hash
            or projection.risk_control_state != "SAFE_HELD"
            or projection.risk_state_epoch != assessment.risk_state_epoch
            or projection.active_risk_config_sha256 != assessment.risk_config_sha256
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED)
        payload = {
            "previous_state": "SAFE_HELD",
            "new_state": "WRITER_ELIGIBLE",
            "cause": "DURABLE_RELEASE_COMPLETED",
            "risk_state_epoch_before": assessment.risk_state_epoch,
            "risk_state_epoch_after": assessment.risk_state_epoch + 1,
            "risk_config_sha256": assessment.risk_config_sha256,
            "related_emergency_action_id": None,
            "related_release_id": assessment.release_id,
            "predecessor_state_event_id": assessment.safe_held_state_event_id,
            "observed_authority_trusted_sequence": prior.sequence,
            "observed_authority_trusted_hash": prior.event_hash,
            "observed_ledger_terminal_sequence": prior.sequence,
            "observed_ledger_terminal_hash": prior.event_hash,
        }
        return self.__locked.append_batch((EventInput(
            EventType.RISK_CONTROL_STATE_CHANGED, payload, self.__session_id,
        ),))

    def close(self) -> None:
        if self.__closed:
            return
        self.__closed = True
        end_restricted_session(
            self.__locked, restricted_session_id=self.__session_id,
            acquisition_mode=AcquisitionMode.RELEASE_ONLY,
        )


def _acquire_narrow_restricted(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    acquisition_mode: AcquisitionMode,
    contract: LegacyIncidentContract,
    expected_ledger_path: str | None,
    clock,
    uuid_factory,
    fault_hook,
    monotonic_clock_ns=None,
    release_wall_clock=None,
) -> RestrictedAcquisition:
    kwargs: dict[str, object] = {}
    if clock is not None:
        kwargs["clock"] = clock
    if uuid_factory is not None:
        kwargs["uuid_factory"] = uuid_factory
    if fault_hook is not None:
        kwargs["fault_hook"] = fault_hook
    opened = _acquire_restricted_state(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        acquisition_mode=acquisition_mode,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_bound_legacy_history(events, contract),
        **kwargs,
    )
    if opened.locked is None:
        return RestrictedAcquisition(
            opened.restart_classification, opened.projection, None,
            opened.failure_code, opened.authority_ledger_relation,
        )
    session_id = opened.restricted_session_id
    if session_id is None:
        opened.locked.close()
        raise LedgerError(FailureCode.RESTRICTED_SESSION_STATE_CONFLICT)
    handle: EmergencyControlLedgerHandle | ReleaseLedgerHandle
    if acquisition_mode is AcquisitionMode.EMERGENCY_CONTROL_ONLY:
        handle = EmergencyControlLedgerHandle(opened.locked, session_id)
    else:
        handle = ReleaseLedgerHandle(
            opened.locked,
            session_id,
            monotonic_clock_ns=monotonic_clock_ns or time.monotonic_ns,
            wall_clock=release_wall_clock or clock or (lambda: datetime.now(timezone.utc)),
            uuid_factory=uuid_factory or uuid.uuid4,
        )
    return RestrictedAcquisition(
        opened.restart_classification, opened.locked.projection(), handle,
        None, opened.authority_ledger_relation,
    )


def acquire_emergency_control_only(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    contract: LegacyIncidentContract = CURRENT_LEGACY_INCIDENT_CONTRACT,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> RestrictedAcquisition:
    return _acquire_narrow_restricted(
        binding, canonical_repository_root=canonical_repository_root,
        acquisition_mode=AcquisitionMode.EMERGENCY_CONTROL_ONLY, contract=contract,
        expected_ledger_path=expected_ledger_path, clock=clock,
        uuid_factory=uuid_factory, fault_hook=fault_hook,
    )


def acquire_release_only(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    contract: LegacyIncidentContract = CURRENT_LEGACY_INCIDENT_CONTRACT,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
    monotonic_clock_ns=None,
    release_wall_clock=None,
) -> RestrictedAcquisition:
    return _acquire_narrow_restricted(
        binding, canonical_repository_root=canonical_repository_root,
        acquisition_mode=AcquisitionMode.RELEASE_ONLY, contract=contract,
        expected_ledger_path=expected_ledger_path, clock=clock,
        uuid_factory=uuid_factory, fault_hook=fault_hook,
        monotonic_clock_ns=monotonic_clock_ns,
        release_wall_clock=release_wall_clock,
    )


def acquire_normal_writer_state(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    contract: LegacyIncidentContract = CURRENT_LEGACY_INCIDENT_CONTRACT,
    expected_ledger_path: str | None = None,
) -> OpenResult:
    """Return local normal-writer eligibility; Revision 03 exposes no writer.

    Before import this returns LEGACY_HISTORY_INCOMPLETE; after the current
    import it returns UNRESOLVED_WRITE_HELD.  In both cases ``handle`` is None.
    """
    return acquire_local_state(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        acquisition_mode=AcquisitionMode.NORMAL_WRITER,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_bound_legacy_history(events, contract),
    )


def prepared_request_identity(payload: Mapping[str, object]) -> str:
    """Hash a validated, secret-free prepared request identity."""
    return sha256_hex(canonical_json_bytes(dict(payload)))


def append_authority_anchored_send_gate(
    locked: LockedLedger,
    *,
    writer_session_id: str,
    incident_id: str,
    execution_attempt_id: str,
    intent_payload: Mapping[str, object],
    prepared_payload: Mapping[str, object],
) -> AuthorityAnchoredSendGate:
    """Persist intent, request and write boundary, returning permission last.

    This local helper has no transport parameter.  If any ledger/authority
    step fails or is unknown it raises and can never construct the returned
    gate.  A later integration may permit transport only after receiving this
    exact object under a separately accepted execution contract.
    """
    if type(locked) is not LockedLedger:
        raise LedgerError(FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED)
    projection = locked.projection()
    if (
        projection.history_completeness != "COMPLETE"
        or projection.restart_classification is not RestartClassification.SAFE_NO_WRITE_CAPABILITY
        or projection.protected_unresolved_legacy_write_count != 0
        or projection.unresolved_write_request_ids
        or any(state == "HELD" for state in projection.writer_proof_state_by_proof_id.values())
    ):
        raise LedgerError(FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED)
    if (
        projection.active_writer_session_id != writer_session_id
        or writer_session_id not in projection.writer_sessions
    ):
        raise LedgerError(FailureCode.WRITER_SESSION_REFERENCE_INVALID)
    request_id = prepared_payload.get("request_id")
    if type(request_id) is not str:
        raise LedgerError(FailureCode.REQUEST_PARENT_INVALID)
    locked.append_batch((EventInput(EventType.EXECUTION_INTENT_RECORDED, intent_payload, writer_session_id, incident_id, execution_attempt_id),))
    locked.append_batch((EventInput(EventType.REQUEST_PREPARED, prepared_payload, writer_session_id, incident_id, execution_attempt_id),))
    boundary = locked.append_batch((EventInput(EventType.WRITE_SEND_BOUNDARY_ENTERED, {
        "operation_name": prepared_payload["operation_name"],
        "prepared_request_sha256": prepared_payload["prepared_request_sha256"],
        "request_id": request_id,
        "write_ambiguity_rule": "WRITE_MAY_HAVE_BEEN_SENT_AFTER_THIS_COMMIT",
    }, writer_session_id, incident_id, execution_attempt_id),))
    row = locked.authority_row
    event = boundary.events[-1]
    if (row.trusted_sequence, row.trusted_event_hash) != (event.sequence, event.event_hash):
        raise LedgerError(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
    return AuthorityAnchoredSendGate(request_id, event.sequence, event.event_hash, row.trusted_sequence, row.trusted_event_hash)


def canonical_kalshi_fill_payload(
    *,
    fill_id: str,
    order_id: str,
    price: Decimal,
    quantity: Decimal,
    fee: Decimal,
    additional_fields: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    """Build a Decimal-only canonical fill payload without price inference."""
    if any(type(value) is not Decimal for value in (price, quantity, fee)):
        raise LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
    payload: dict[str, object] = {
        "fee": fee,
        "fill_id": fill_id,
        "order_id": order_id,
        "price": price,
        "quantity": quantity,
    }
    if additional_fields:
        payload.update(additional_fields)
    # Round-trip construction validates canonical and secret-safe content.
    canonical_json_bytes(payload)
    return payload


__all__ = [
    "AuthorityAnchoredSendGate", "CURRENT_ACCOUNT_SCOPE_REF", "CURRENT_CLIENT_ORDER_ID",
    "CURRENT_CONFLICT_DOMAIN_REF", "CURRENT_DISPOSITION", "CURRENT_ENVIRONMENT",
    "CURRENT_INCIDENT_ID", "CURRENT_LEGACY_INCIDENT_CONTRACT", "CURRENT_TICKER",
    "CURRENT_WRITER_PROOF_ID", "EvidenceExpectation", "LegacyIncidentContract",
    "EmergencyControlLedgerHandle", "LegacyImportAcquisition", "LegacyImportOnlyHandle", "LegacyImportResult",
    "LegacyImportStatus", "PRODUCTION_EVIDENCE_EXPECTATIONS", "ValidatedLegacyEvidence",
    "ReleaseAssessmentV1", "ReleaseEvaluationStateV1", "ReleaseLedgerHandle",
    "ReleaseReconciliationSnapshotV1", "ReleaseRiskSnapshotV1", "RestrictedAcquisition",
    "VenueDefenseEvidenceV1", "acquire_emergency_control_only",
    "acquire_legacy_import_only", "acquire_normal_writer_state", "acquire_release_only",
    "append_authority_anchored_send_gate", "canonical_kalshi_fill_payload",
    "prepared_request_identity", "validate_legacy_evidence",
    "validate_venue_defense_evidence",
]
