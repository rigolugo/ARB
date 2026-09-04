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
    ACTIVE_LEDGER_SCHEMA_REVISION,
    BOOTSTRAP_CLASS_TO_COMPLETENESS,
    AcquisitionMode,
    ActiveLedgerMeta,
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
    _acquire_normal_writer_candidate,
    _acquire_restricted_state,
    acquire_local_state,
    canonical_json_bytes,
    canonical_json_text,
    canonical_timestamp,
    end_restricted_session,
    initialize_execution_domain_ledger_v2,
    parse_canonical_json,
    sha256_hex,
    start_writer_session,
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
    state_changed_event_id: str | None = None
    state_changed_event_hash: str | None = None
    last_monotonic_ns: int = 0


@dataclass(frozen=True, slots=True)
class _AuthoritativeReleaseUniverse:
    working_orders: tuple[WorkingOrderV1, ...]
    fills: tuple[EconomicFillV1, ...]
    cancel_order_on_pause_order_ids: tuple[str, ...]
    latest_order_event_ids: Mapping[str, str]
    fill_event_ids: Mapping[str, tuple[str, ...]]
    conflict_ids: tuple[str, ...]


def _derive_authoritative_release_universe(locked: "LockedLedger") -> _AuthoritativeReleaseUniverse:
    """Derive the complete current economic universe from trusted replay.

    The one canonical shared durable ``ORDER_OBSERVED``/``FILL_OBSERVED``
    truth interpreter (Spec 05 ER05-TRUST-001).  ``ReleaseLedgerHandle``
    (Stage 3G) and ``read_trusted_release_evidence_projection`` (Stage 3F)
    both call this exact function against their own independently opened
    ``LockedLedger`` -- there is never a second parser or a second
    selection rule for durable order/fill truth.  Preserves the pre-Spec-05
    semantics of the method this was extracted from byte-for-byte; this
    refactor changes no release predicate or economic-release semantics.
    """

    projection = locked.projection()
    latest_orders: dict[str, object] = {}
    fill_events: dict[str, list[object]] = {}
    conflicts: set[str] = set(projection.fill_conflicts)
    for event in locked.events:
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
        remaining = ReleaseLedgerHandle._positive_qty2(content.get("remaining_count_fp"))
        yes_price = ReleaseLedgerHandle._stored_decimal_value(content.get("yes_price"))
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
        quantity = ReleaseLedgerHandle._stored_decimal_value(canonical.get("quantity"))
        yes_price = ReleaseLedgerHandle._stored_decimal_value(canonical.get("price"))
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


_CURRENT_PROCESS_RELEASE_COMPLETION_KEY = object()
_current_process_release_completion_registry_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class _CurrentProcessReleaseCompletionIssuanceRecord:
    """Independent issuance evidence, stored apart from the live token.

    ``frozen=True`` on ``CurrentProcessReleaseCompletionV1`` only overrides
    ordinary attribute assignment; ``object.__setattr__`` can still mutate a
    field on the live object in the same process.  Object-identity
    membership in the registry alone cannot detect that: the mutated object
    is still the exact registered object.  This record captures an
    immutable snapshot of every frozen field at the moment of issuance, kept
    independently of the live token, so admission can prove each field still
    equals its issuance-time value rather than merely comparing the token to
    itself.
    """

    token: "CurrentProcessReleaseCompletionV1"
    snapshot: Mapping[str, object]


# Module-private issuance registry.  Keyed by object id for O(1) lookup, but
# validity is never decided by key presence alone: every lookup re-compares
# the registered VALUE to the candidate with ``is`` so a later object that
# happens to be allocated at a freed/reused id can never be mistaken for a
# still-registered token.  The dict holds a genuine strong reference to each
# issued token for as long as it remains valid, which is what makes the
# identity check meaningful (the original object cannot be garbage collected
# and its id reused while it is still registered).  It also holds the
# independent issuance snapshot used for exact-field validation.
_current_process_release_completion_registry: dict[int, _CurrentProcessReleaseCompletionIssuanceRecord] = {}


def _register_current_process_release_completion(token: "CurrentProcessReleaseCompletionV1") -> None:
    snapshot = MappingProxyType({
        field.name: getattr(token, field.name) for field in fields(type(token))
    })
    with _current_process_release_completion_registry_lock:
        _current_process_release_completion_registry[id(token)] = (
            _CurrentProcessReleaseCompletionIssuanceRecord(token, snapshot)
        )


def _is_registered_current_process_release_completion(token: object) -> bool:
    with _current_process_release_completion_registry_lock:
        record = _current_process_release_completion_registry.get(id(token))
        return record is not None and record.token is token


def _consume_current_process_release_completion(token: "CurrentProcessReleaseCompletionV1") -> None:
    with _current_process_release_completion_registry_lock:
        record = _current_process_release_completion_registry.get(id(token))
        if record is not None and record.token is token:
            del _current_process_release_completion_registry[id(token)]


def _exact_field_equal(current: object, expected: object) -> bool:
    """Type-aware equality: ``True == 1`` must not pass a ``schema_revision``
    check bound to exact built-in ``int``, so plain ``==`` is insufficient.
    """
    return type(current) is type(expected) and current == expected


def _is_exact_sha256_hex(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _is_exact_event_id(value: object) -> bool:
    return type(value) is str and value.startswith("evt_") and len(value) == 36


def _validate_current_process_release_completion_frozen_fields(
    token: "CurrentProcessReleaseCompletionV1",
) -> bool:
    """Prove every frozen Spec-04 token field is still exact before admission.

    Two independent checks, both required:

    1. every field's current live value equals its independent
       issuance-time snapshot value, compared with exact-type-aware
       equality (catches any post-issuance ``object.__setattr__`` mutation,
       including a same-value-but-wrong-type substitution such as
       ``schema_revision = True``);
    2. every field independently satisfies the frozen Spec-04 schema's exact
       type/shape contract (authoritative source for what "exact" means,
       not merely incidental to snapshot equality).

    This is deliberately independent of -- and additional to -- the caller's
    live-continuity ("stale") checks in ``acquire_normal_writer_state``,
    which validate the token's bindings against *current* authoritative
    ledger/process state.  This function validates the token's own frozen
    fields against *itself at issuance*, which no amount of current-state
    comparison can substitute for.
    """
    with _current_process_release_completion_registry_lock:
        record = _current_process_release_completion_registry.get(id(token))
    if record is None or record.token is not token:
        return False
    for field in fields(type(token)):
        current = getattr(token, field.name)
        expected = record.snapshot.get(field.name)
        if not _exact_field_equal(current, expected):
            return False
    if (
        type(token.schema_revision) is not int or token.schema_revision != 1
        or type(token.process_instance_id) is not str or not token.process_instance_id
        or type(token.release_id) is not str or not token.release_id.startswith("rel_")
        or type(token.writer_proof_id) is not str or not token.writer_proof_id
        or not _is_exact_sha256_hex(token.risk_config_sha256)
        or type(token.resulting_risk_state_epoch) is not int or token.resulting_risk_state_epoch < 0
        or not _is_exact_event_id(token.writer_eligible_state_event_id)
        or not _is_exact_sha256_hex(token.writer_eligible_state_event_hash)
        or type(token.authority_trusted_sequence) is not int or token.authority_trusted_sequence <= 0
        or not _is_exact_sha256_hex(token.authority_trusted_event_hash)
        or type(token.ledger_terminal_sequence) is not int or token.ledger_terminal_sequence <= 0
        or not _is_exact_sha256_hex(token.ledger_terminal_event_hash)
        or not _is_exact_event_id(token.release_session_ended_event_id)
        or not _is_exact_sha256_hex(token.release_session_ended_event_hash)
        or type(token.private_release_handle_identity) is not object
        or type(token.private_release_source_identity) is not object
    ):
        return False
    return True


@dataclass(frozen=True, slots=True, init=False)
class CurrentProcessReleaseCompletionV1:
    """One-shot, process-local, non-forgeable normal-writer admission token.

    Only ``ReleaseLedgerHandle.complete_release_and_issue_current_process_completion``
    may construct and register an instance.  It is immutable, rejects
    ``copy``/``deepcopy``/``pickle``/``reduce`` reconstruction, and a value
    equal to a genuine instance in every public field is still invalid unless
    it is the exact same registered object (validated by ``is``, never by
    equality or by ``id()`` membership alone -- see the registry helpers
    above).  Historical replay, ledger evidence, or a different Python
    process can never reconstruct it: the registry is process-local memory
    only and is destroyed by process termination.
    """

    schema_revision: int
    process_instance_id: str
    release_id: str
    writer_proof_id: str
    risk_config_sha256: str
    resulting_risk_state_epoch: int
    writer_eligible_state_event_id: str
    writer_eligible_state_event_hash: str
    authority_trusted_sequence: int
    authority_trusted_event_hash: str
    ledger_terminal_sequence: int
    ledger_terminal_event_hash: str
    release_session_ended_event_id: str
    release_session_ended_event_hash: str
    private_release_handle_identity: object
    private_release_source_identity: object

    def __init__(self, key: object, **values: object) -> None:
        if key is not _CURRENT_PROCESS_RELEASE_COMPLETION_KEY:
            raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def __copy__(self):
        raise TypeError("CurrentProcessReleaseCompletionV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("CurrentProcessReleaseCompletionV1 cannot be serialized")


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
        """Derive the complete current economic universe from trusted replay.

        Delegates to the one shared canonical derivation (Spec 05
        ER05-TRUST-001) also used by `read_trusted_release_evidence_projection`
        -- there is exactly one durable ORDER_OBSERVED/FILL_OBSERVED truth
        interpreter in this module.
        """

        return _derive_authoritative_release_universe(self.__locked)

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
        result = self.__locked.append_batch((EventInput(
            EventType.RISK_CONTROL_STATE_CHANGED, payload, self.__session_id,
        ),))
        event = result.events[-1]
        progress.state_changed_event_id = event.event_id
        progress.state_changed_event_hash = event.event_hash
        return result

    def complete_release_and_issue_current_process_completion(
        self, assessment: ReleaseAssessmentV1,
    ) -> "CurrentProcessReleaseCompletionV1":
        """Issue the exact one-shot process-local normal-writer admission token.

        Only reachable after ``record_risk_release``, ``release_writer_proof``,
        and ``record_writer_eligible`` have already positively completed on
        this exact assessment context (ER04-REL-CAP-004).  This method never
        re-appends those three durable events; it only verifies they already
        landed as the exact unmoved ledger tail, then anchors the closing
        ``RESTRICTED_SESSION_ENDED`` readback before issuing the capability.
        Any failure below -- including a tail that moved between steps --
        leaves the capability ``NOT_ISSUED`` and never fabricates a
        best-effort token.
        """
        if self.__closed:
            raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)
        progress = self._context(assessment)
        if (
            progress.release_event_id is None
            or progress.proof_event_id is None
            or progress.state_changed_event_id is None
        ):
            raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)
        tail = self.__locked.events[-1]
        projection = self.__locked.projection()
        authority = self.__locked.authority_row
        observed_tail = (tail.sequence, tail.event_hash)
        process_instance_id = progress.source._snapshot()[2]
        if (
            tail.event_id != progress.state_changed_event_id
            or tail.event_hash != progress.state_changed_event_hash
            or tail.event_type is not EventType.RISK_CONTROL_STATE_CHANGED
            or tail.payload.get("previous_state") != "SAFE_HELD"
            or tail.payload.get("new_state") != "WRITER_ELIGIBLE"
            or tail.payload.get("cause") != "DURABLE_RELEASE_COMPLETED"
            or tail.payload.get("related_release_id") != assessment.release_id
            or projection.risk_control_state != "WRITER_ELIGIBLE"
            or projection.risk_state_epoch != assessment.risk_state_epoch + 1
            or projection.active_risk_config_sha256 != assessment.risk_config_sha256
            or projection.writer_proof_state_by_proof_id.get(assessment.writer_proof_id) != "RELEASED"
            or projection.writer_proof_release_eligible_by_proof_id.get(assessment.writer_proof_id) is not True
            or (authority.trusted_sequence, authority.trusted_event_hash) != observed_tail
            or (projection.trusted_sequence, projection.trusted_event_hash) != observed_tail
            or (projection.last_sequence, projection.terminal_event_hash) != observed_tail
            or process_instance_id != assessment.process_instance_id
        ):
            raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)

        session_id = self.__session_id
        private_release_handle_identity = self.__identity
        private_release_source_identity = assessment.private_source_identity
        try:
            end_restricted_session(
                self.__locked, restricted_session_id=session_id,
                acquisition_mode=AcquisitionMode.RELEASE_ONLY,
            )
        except LedgerError as exc:
            raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED) from exc
        finally:
            self.__closed = True

        ended_tail = self.__locked.events[-1]
        ended_authority = self.__locked.authority_row
        ended_projection = self.__locked.projection()
        ended_observed = (ended_tail.sequence, ended_tail.event_hash)
        if (
            ended_tail.event_type is not EventType.RESTRICTED_SESSION_ENDED
            or ended_tail.payload.get("restricted_session_id") != session_id
            or ended_tail.payload.get("acquisition_mode") != AcquisitionMode.RELEASE_ONLY.value
            or (ended_authority.trusted_sequence, ended_authority.trusted_event_hash) != ended_observed
            or (ended_projection.trusted_sequence, ended_projection.trusted_event_hash) != ended_observed
            or (ended_projection.last_sequence, ended_projection.terminal_event_hash) != ended_observed
            or ended_projection.active_restricted_session_id is not None
        ):
            raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)

        token = CurrentProcessReleaseCompletionV1(
            _CURRENT_PROCESS_RELEASE_COMPLETION_KEY,
            schema_revision=1,
            process_instance_id=assessment.process_instance_id,
            release_id=assessment.release_id,
            writer_proof_id=assessment.writer_proof_id,
            risk_config_sha256=assessment.risk_config_sha256,
            resulting_risk_state_epoch=assessment.risk_state_epoch + 1,
            writer_eligible_state_event_id=tail.event_id,
            writer_eligible_state_event_hash=tail.event_hash,
            authority_trusted_sequence=ended_authority.trusted_sequence,
            authority_trusted_event_hash=ended_authority.trusted_event_hash,
            ledger_terminal_sequence=ended_tail.sequence,
            ledger_terminal_event_hash=ended_tail.event_hash,
            release_session_ended_event_id=ended_tail.event_id,
            release_session_ended_event_hash=ended_tail.event_hash,
            private_release_handle_identity=private_release_handle_identity,
            private_release_source_identity=private_release_source_identity,
        )
        _register_current_process_release_completion(token)
        return token

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


@dataclass(frozen=True, slots=True)
class NormalWriterAcquisition:
    """Exact ER-NW-003 acquisition result carrier."""

    projection: SafetyProjection | None
    restart_classification: RestartClassification
    handle: LockedLedger | None
    normal_writer_session_id: str | None
    failure_code: FailureCode | None = None
    authority_ledger_relation: AuthorityLedgerRelation | None = None


def acquire_normal_writer_state(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    risk_config: RiskLimitConfigV1,
    process_instance_id: str,
    current_process_release_completion: CurrentProcessReleaseCompletionV1 | None = None,
    contract: LegacyIncidentContract = CURRENT_LEGACY_INCIDENT_CONTRACT,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> NormalWriterAcquisition:
    """Sole supported Kalshi normal-writer acquisition function (ER-NW-003).

    A non-``None`` handle/session may be returned only if, while the
    authority and ledger exclusive locks remain held, every durable
    ER-NW-003 predicate holds (exact authority/ledger identity and tail
    equality, ``history_completeness == COMPLETE``,
    ``protected_unresolved_legacy_write_count == 0``, no unresolved write,
    controlling writer proof ``RELEASED``/eligible, ``WRITER_ELIGIBLE``,
    active risk config bound to ``risk_config``, no active restricted
    session, no unresolved emergency cancel) AND the full current-process
    release-completion continuity block (ER04-NW-003/004/005) holds:
    ``current_process_release_completion`` is an exact, live-registered
    ``CurrentProcessReleaseCompletionV1`` bound to this process, this
    ``risk_config``, this replay epoch, its own bound writer-eligible and
    restricted-session-end event identities, and the current unmoved
    authority/ledger tail.

    Storage/integrity/identity failures from the private candidate bridge
    preserve their existing exact failure codes.  A pure durable
    eligibility/config failure (reached only once the candidate bridge
    itself opened cleanly) uses ``NORMAL_WRITER_ACQUISITION_REJECTED`` and
    never mutates eligibility.  Token-specific failures retain their own
    exact ``CURRENT_PROCESS_RELEASE_COMPLETION_*`` classifications.

    For the exact current historical state (Section 6), this always returns
    ``handle=None`` and ``normal_writer_session_id=None``: its protected
    unresolved legacy write is never cleared by any supported event, so
    ``history_completeness`` never reaches ``COMPLETE`` for that incident.
    """
    kwargs: dict[str, object] = {}
    if clock is not None:
        kwargs["clock"] = clock
    if uuid_factory is not None:
        kwargs["uuid_factory"] = uuid_factory
    if fault_hook is not None:
        kwargs["fault_hook"] = fault_hook
    opened = _acquire_normal_writer_candidate(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_bound_legacy_history(events, contract),
        **kwargs,
    )
    locked = opened.handle
    if locked is None:
        return NormalWriterAcquisition(
            opened.projection, opened.restart_classification, None, None,
            opened.failure_code, opened.authority_ledger_relation,
        )

    projection = locked.projection()
    tail = locked.events[-1]
    authority = locked.authority_row
    observed_tail = (tail.sequence, tail.event_hash)
    proof_state = projection.writer_proof_state_by_proof_id.get(contract.writer_proof_id)
    proof_eligible = projection.writer_proof_release_eligible_by_proof_id.get(contract.writer_proof_id)
    durable_eligible = (
        projection.history_completeness == "COMPLETE"
        and projection.protected_unresolved_legacy_write_count == 0
        and not projection.unresolved_write_request_ids
        and proof_state == "RELEASED"
        and proof_eligible is True
        and projection.risk_control_state == "WRITER_ELIGIBLE"
        and projection.active_risk_config_sha256 is not None
        and type(risk_config) is RiskLimitConfigV1
        and risk_config.conflict_domain == contract.conflict_domain_ref
        and risk_config.sha256 == projection.active_risk_config_sha256
        and projection.active_restricted_session_id is None
        and not any(projection.cancel_send_may_have_been_sent_by_attempt.values())
        and (authority.trusted_sequence, authority.trusted_event_hash) == observed_tail
        and (projection.trusted_sequence, projection.trusted_event_hash) == observed_tail
        and (projection.last_sequence, projection.terminal_event_hash) == observed_tail
    )
    if not durable_eligible:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED, locked.relation,
        )

    if current_process_release_completion is None:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED, locked.relation,
        )
    token = current_process_release_completion
    if (
        type(token) is not CurrentProcessReleaseCompletionV1
        or not _is_registered_current_process_release_completion(token)
    ):
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID, locked.relation,
        )
    # Object-identity registry membership alone does not prove every frozen
    # field is still exact: ``object.__setattr__`` can mutate a field on the
    # live (still-registered) object without changing its identity.  Every
    # frozen field must independently equal its issuance-time snapshot value
    # (exact-type-aware) and satisfy the frozen Spec-04 schema's exact
    # type/shape contract before the token may be trusted further.
    if not _validate_current_process_release_completion_frozen_fields(token):
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID, locked.relation,
        )
    if token.process_instance_id != process_instance_id:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_PROCESS_MISMATCH, locked.relation,
        )

    events_by_id = {event.event_id: event for event in locked.events}
    writer_eligible_event = events_by_id.get(token.writer_eligible_state_event_id)
    session_ended_event = events_by_id.get(token.release_session_ended_event_id)
    stale = (
        token.writer_proof_id != contract.writer_proof_id
        or token.risk_config_sha256 != risk_config.sha256
        or projection.risk_state_epoch != token.resulting_risk_state_epoch
        or writer_eligible_event is None
        or writer_eligible_event.event_type is not EventType.RISK_CONTROL_STATE_CHANGED
        or writer_eligible_event.event_hash != token.writer_eligible_state_event_hash
        or writer_eligible_event.payload.get("previous_state") != "SAFE_HELD"
        or writer_eligible_event.payload.get("new_state") != "WRITER_ELIGIBLE"
        or writer_eligible_event.payload.get("cause") != "DURABLE_RELEASE_COMPLETED"
        or writer_eligible_event.payload.get("related_release_id") != token.release_id
        or session_ended_event is None
        or session_ended_event.event_type is not EventType.RESTRICTED_SESSION_ENDED
        or session_ended_event.event_hash != token.release_session_ended_event_hash
        or (token.authority_trusted_sequence, token.authority_trusted_event_hash) != observed_tail
        or (token.ledger_terminal_sequence, token.ledger_terminal_event_hash) != observed_tail
    )
    if stale:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_STALE, locked.relation,
        )

    # Every durable and continuity predicate has now been validated while the
    # authority/ledger locks are still held.  Consume the single-admission
    # token immediately before the one permitted successor mutation.
    _consume_current_process_release_completion(token)
    relation = locked.relation
    try:
        session_id = start_writer_session(locked, prior_session_state="NONE")
    except LedgerError as exc:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None, exc.code, relation,
        )
    final_projection = locked.projection()
    if final_projection.active_writer_session_id != session_id:
        locked.close()
        return NormalWriterAcquisition(
            final_projection, final_projection.restart_classification, None, None,
            FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED, relation,
        )
    return NormalWriterAcquisition(
        final_projection, final_projection.restart_classification, locked, session_id,
        None, relation,
    )


# ---------------------------------------------------------------------------
# Spec 05 Correction 01 -- TrustedReleaseEvidenceProjectionV1: a narrow,
# immutable, READ-ONLY Stage-3F projection of the same shared canonical
# durable release universe `ReleaseLedgerHandle` uses at Stage 3G.  It is
# never a LockedLedger, writer/release/emergency capability, venue/
# credential capability, append API, or generic event-history API; its
# existence is not evidence that a venue fact is durably persisted.
# ---------------------------------------------------------------------------

_TRUSTED_RELEASE_EVIDENCE_PROJECTION_KEY = object()


def _is_exact_sorted_unique_str_tuple(value: object) -> bool:
    return (
        type(value) is tuple
        and all(type(item) is str and item for item in value)
        and tuple(sorted(set(value))) == value
    )


def _is_exact_unique_event_id_sequence(value: object) -> bool:
    """Unordered-uniqueness only: `fill_matching_event_ids[fill_id]` is
    ordered by ledger sequence (Spec 05 ER05-TRUST-004), not alphabetically
    sorted, so this deliberately does not require sortedness."""

    return (
        type(value) is tuple
        and all(_is_exact_event_id(item) for item in value)
        and len(set(value)) == len(value)
    )


@dataclass(frozen=True, slots=True, init=False)
class TrustedReleaseEvidenceProjectionV1:
    """One-shot, process-local, read-only trusted durable evidence
    projection (Spec 05 ER05-TRUST-002).  Immutable; rejects
    copy/deepcopy/pickle/reduce reconstruction.  Replaying its logged data
    elsewhere can never create a writer or release capability -- it carries
    no capability, only validated durable facts and their exact event-ID
    references, bound to one specific equal authority/ledger tail.
    """

    schema_revision: int
    environment_classification: str
    conflict_domain_ref: str

    authority_instance_id: str
    authority_namespace_id: str
    authority_store_path_identity_sha256: str

    ledger_instance_id: str
    ledger_path_identity_sha256: str

    authority_trusted_sequence: int
    authority_trusted_event_hash: str
    ledger_terminal_sequence: int
    ledger_terminal_event_hash: str

    working_orders: tuple[WorkingOrderV1, ...]
    fills: tuple[EconomicFillV1, ...]
    cancel_order_on_pause_order_ids: tuple[str, ...]

    latest_order_event_ids: Mapping[str, str]
    fill_matching_event_ids: Mapping[str, tuple[str, ...]]

    conflict_ids: tuple[str, ...]

    def __init__(self, key: object, **values: object) -> None:
        if key is not _TRUSTED_RELEASE_EVIDENCE_PROJECTION_KEY:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])
        self.__validate()

    def __validate(self) -> None:
        if type(self.schema_revision) is not int or self.schema_revision != 1:
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        for value in (
            self.environment_classification, self.conflict_domain_ref,
            self.authority_instance_id, self.authority_namespace_id,
            self.ledger_instance_id,
        ):
            if type(value) is not str or not value:
                raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        for value in (
            self.authority_store_path_identity_sha256, self.ledger_path_identity_sha256,
            self.authority_trusted_event_hash, self.ledger_terminal_event_hash,
        ):
            if not _is_exact_sha256_hex(value):
                raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        for value in (self.authority_trusted_sequence, self.ledger_terminal_sequence):
            if type(value) is not int or value <= 0:
                raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if (
            self.authority_trusted_sequence != self.ledger_terminal_sequence
            or self.authority_trusted_event_hash != self.ledger_terminal_event_hash
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if type(self.working_orders) is not tuple or any(
            type(item) is not WorkingOrderV1 for item in self.working_orders
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if type(self.fills) is not tuple or any(
            type(item) is not EconomicFillV1 for item in self.fills
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if not _is_exact_sorted_unique_str_tuple(self.cancel_order_on_pause_order_ids):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if not _is_exact_sorted_unique_str_tuple(self.conflict_ids):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if not isinstance(self.latest_order_event_ids, Mapping) or any(
            type(k) is not str or not k or not _is_exact_event_id(v)
            for k, v in self.latest_order_event_ids.items()
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)
        if not isinstance(self.fill_matching_event_ids, Mapping) or any(
            type(k) is not str or not k or not _is_exact_unique_event_id_sequence(v)
            for k, v in self.fill_matching_event_ids.items()
        ):
            raise LedgerError(FailureCode.RELEASE_PREDICATE_FAILED)

    def __copy__(self):
        raise TypeError("TrustedReleaseEvidenceProjectionV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("TrustedReleaseEvidenceProjectionV1 cannot be serialized")

    def order_evidence_ref(self, order: "WorkingOrderV1") -> tuple[str, str] | None:
        """Deterministic evidence lookup only -- accepts no caller-chosen
        event ID (Spec 05 ER05-TRUST-004)."""

        if type(order) is not WorkingOrderV1:
            return None
        for candidate in self.working_orders:
            if candidate == order:
                event_id = self.latest_order_event_ids.get(candidate.order_id)
                if event_id is None:
                    return None
                return (candidate.order_id, event_id)
        return None

    def fill_evidence_ref(self, fill: "EconomicFillV1") -> tuple[str, str] | None:
        """Deterministic evidence lookup only -- selects the latest element
        of the canonical matching-event tuple; accepts no caller-chosen
        event ID (Spec 05 ER05-TRUST-004)."""

        if type(fill) is not EconomicFillV1:
            return None
        for candidate in self.fills:
            if candidate == fill:
                matching = self.fill_matching_event_ids.get(candidate.fill_id)
                if not matching:
                    return None
                return (candidate.fill_id, matching[-1])
        return None


@dataclass(frozen=True, slots=True)
class TrustedReleaseEvidenceReadResultV1:
    projection: TrustedReleaseEvidenceProjectionV1 | None
    restart_classification: RestartClassification
    failure_code: FailureCode | None = None
    authority_ledger_relation: AuthorityLedgerRelation | None = None


def read_trusted_release_evidence_projection(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    contract: LegacyIncidentContract = CURRENT_LEGACY_INCIDENT_CONTRACT,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> TrustedReleaseEvidenceReadResultV1:
    """Read-only Stage-3F trusted evidence projection factory (Spec 05
    ER05-TRUST-003).  Reuses the already-canonical, private, authority-
    first/ledger-second, equal-tail-validated `_acquire_normal_writer_
    candidate(...)` bridge solely as a validated open/replay/close round
    trip.  Never calls `start_writer_session`, never appends an event, and
    never exposes the `LockedLedger` to the caller.  `execution_ledger.py`
    is unchanged by this function -- the needed validated candidate bridge
    already exists at the required canonical base.
    """

    kwargs: dict[str, object] = {}
    if clock is not None:
        kwargs["clock"] = clock
    if uuid_factory is not None:
        kwargs["uuid_factory"] = uuid_factory
    if fault_hook is not None:
        kwargs["fault_hook"] = fault_hook
    opened = _acquire_normal_writer_candidate(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_bound_legacy_history(events, contract),
        **kwargs,
    )
    locked = opened.handle
    if locked is None:
        # `_acquire_normal_writer_candidate` already requires
        # `AuthorityLedgerRelation.EQUAL` for a live candidate; a `None`
        # handle here means no equal-tail candidate was available.
        return TrustedReleaseEvidenceReadResultV1(
            None, opened.restart_classification, opened.failure_code, opened.authority_ledger_relation,
        )
    try:
        universe = _derive_authoritative_release_universe(locked)
        tail = locked.events[-1]
        authority = locked.authority_row
        observed_tail = (tail.sequence, tail.event_hash)
        if (
            (authority.trusted_sequence, authority.trusted_event_hash) != observed_tail
            or (opened.projection.trusted_sequence, opened.projection.trusted_event_hash) != observed_tail
        ):
            return TrustedReleaseEvidenceReadResultV1(
                None, opened.projection.restart_classification,
                FailureCode.AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH, locked.relation,
            )
        projection = TrustedReleaseEvidenceProjectionV1(
            _TRUSTED_RELEASE_EVIDENCE_PROJECTION_KEY,
            schema_revision=1,
            environment_classification=locked.ledger_meta.environment_classification,
            conflict_domain_ref=locked.conflict_domain_ref,
            authority_instance_id=locked.authority_meta.authority_instance_id,
            authority_namespace_id=locked.authority_meta.authority_namespace_id,
            authority_store_path_identity_sha256=locked.authority_meta.authority_store_path_identity_sha256,
            ledger_instance_id=locked.ledger_meta.ledger_instance_id,
            ledger_path_identity_sha256=locked.ledger_meta.ledger_path_identity_sha256,
            authority_trusted_sequence=authority.trusted_sequence,
            authority_trusted_event_hash=authority.trusted_event_hash,
            ledger_terminal_sequence=tail.sequence,
            ledger_terminal_event_hash=tail.event_hash,
            working_orders=universe.working_orders,
            fills=universe.fills,
            cancel_order_on_pause_order_ids=universe.cancel_order_on_pause_order_ids,
            latest_order_event_ids=MappingProxyType(dict(universe.latest_order_event_ids)),
            fill_matching_event_ids=MappingProxyType(dict(universe.fill_event_ids)),
            conflict_ids=universe.conflict_ids,
        )
        return TrustedReleaseEvidenceReadResultV1(
            projection, opened.projection.restart_classification, None, locked.relation,
        )
    finally:
        locked.close()


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


# ===========================================================================
# Active execution-domain (dynamic numbered-subaccount) binding, bootstrap
# contract, active safety/release contract, and the revision-2 active Gate
# B/C/D read/acquisition boundary.  Nothing below repoints, subclasses, or
# widens ``LegacyIncidentContract``; the legacy SUBACCOUNT=0 path above is
# untouched.  (KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND
# _RISK_CONTROL_SPEC_01_CORRECTION_02, sections 5-8 and 14 -- Correction 02
# is a complete standalone same-scope successor to Correction 01 and
# preserves all its non-conflicting active-domain architecture.)
# ===========================================================================

_ACTIVE_ENVIRONMENT = "KALSHI_DEMO"
_ACTIVE_HISTORY_ANCHOR_DOMAIN = b"ARB_ACTIVE_EXECUTION_DOMAIN_INCIDENT_V1\x00"
_ACTIVE_WRITER_PROOF_DOMAIN = b"ARB_ACTIVE_DOMAIN_WRITER_PROOF_V1\x00"
_BOOTSTRAP_TRUTH_VALUES = frozenset({"COMPLETE_ZERO", "COMPLETE_KNOWN_NONZERO"})
_EVIDENCE_PROVENANCE_VALUES = frozenset({"PROJECT_EVIDENCE_RECORDED", "INDEPENDENTLY_VERIFIED"})

# Correction 02 composite trusted dynamic pre-release read-set identity
# (DSB-READSET-003): ``ADRS2_`` + the full 64-hex read-set SHA-256.  No
# truncated read-set hash is normative.
def _is_adrs2_read_set_id(value: object) -> bool:
    return (
        type(value) is str
        and value[:6] == "ADRS2_"
        and _is_exact_sha256_hex(value[6:])
    )


def _first_32_lower_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _require_nfc_nonempty(value: object) -> str:
    import unicodedata
    if type(value) is not str or not value or unicodedata.normalize("NFC", value) != value:
        raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
    return value


@dataclass(frozen=True, slots=True, init=False)
class ExecutionDomainBindingV1:
    """Immutable dynamically selected numbered-subaccount execution domain
    (DSB-BIND-001..004).  ``exchange_index`` is excluded from
    ``conflict_domain_ref`` (subaccount-wide writer conflict scope) but
    included in the binding hash."""

    schema_revision: int
    venue: str
    environment: str
    account_scope_ref: str
    subaccount: int
    exchange_index: int
    conflict_domain_ref: str
    binding_id: str
    binding_sha256: str

    def __init__(
        self,
        *,
        venue: str,
        environment: str,
        account_scope_ref: str,
        subaccount: int,
        exchange_index: int,
    ) -> None:
        if venue != "KALSHI" or environment != "KALSHI_DEMO":
            raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
        scope = _require_nfc_nonempty(account_scope_ref)
        if any(ch in scope for ch in ("|", "\x00", "\r", "\n")) or scope.strip() != scope:
            raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
        if any(ord(ch) < 0x20 for ch in scope):
            raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
        if type(subaccount) is not int or type(subaccount) is bool or not 0 <= subaccount <= 63:
            raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
        if type(exchange_index) is not int or type(exchange_index) is bool or exchange_index < 0:
            raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
        conflict = f"KALSHI|KALSHI_DEMO|{scope}|SUBACCOUNT={subaccount}"
        canonical = {
            "account_scope_ref": scope,
            "conflict_domain_ref": conflict,
            "environment": "KALSHI_DEMO",
            "exchange_index": exchange_index,
            "schema_revision": 1,
            "subaccount": subaccount,
            "venue": "KALSHI",
        }
        binding_sha256 = sha256_hex(canonical_json_bytes(canonical))
        object.__setattr__(self, "schema_revision", 1)
        object.__setattr__(self, "venue", "KALSHI")
        object.__setattr__(self, "environment", "KALSHI_DEMO")
        object.__setattr__(self, "account_scope_ref", scope)
        object.__setattr__(self, "subaccount", subaccount)
        object.__setattr__(self, "exchange_index", exchange_index)
        object.__setattr__(self, "conflict_domain_ref", conflict)
        object.__setattr__(self, "binding_sha256", binding_sha256)
        object.__setattr__(self, "binding_id", "KEDB1_" + binding_sha256)

    def canonical_object(self) -> dict[str, object]:
        return {
            "account_scope_ref": self.account_scope_ref,
            "conflict_domain_ref": self.conflict_domain_ref,
            "environment": self.environment,
            "exchange_index": self.exchange_index,
            "schema_revision": 1,
            "subaccount": self.subaccount,
            "venue": self.venue,
        }

    def canonical_json(self) -> str:
        return canonical_json_text(self.canonical_object())

    def __copy__(self):
        raise TypeError("ExecutionDomainBindingV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("ExecutionDomainBindingV1 cannot be serialized")


@dataclass(frozen=True, slots=True)
class EvidenceReferenceV1:
    name: str
    raw_bytes: int
    sha256: str
    provenance_class: str

    def __post_init__(self) -> None:
        _require_nfc_nonempty(self.name)
        if (
            type(self.raw_bytes) is not int or type(self.raw_bytes) is bool or self.raw_bytes < 0
            or type(self.sha256) is not str or not _is_exact_sha256_hex(self.sha256)
            or self.provenance_class not in _EVIDENCE_PROVENANCE_VALUES
        ):
            raise LedgerError(FailureCode.DOMAIN_BOOTSTRAP_EVIDENCE_MISMATCH)

    def canonical_object(self) -> dict[str, object]:
        return {
            "name": self.name,
            "provenance_class": self.provenance_class,
            "raw_bytes": self.raw_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True, init=False)
class DomainBootstrapContractV1:
    """Immutable, canonical-hashed domain onboarding contract (DSB-BOOT-003).

    The persisted completeness enum string is hash-significant: the two
    accepted classes never collapse to one generic ``COMPLETE`` value.
    """

    schema_revision: int
    domain_binding_id: str
    domain_binding_sha256: str
    conflict_domain_ref: str
    bootstrap_class: str
    bootstrap_cutoff_at_utc: str
    inception_evidence: tuple
    prestack_evidence: tuple
    prestack_activity_completeness: str
    unresolved_write_count: int
    unresolved_cancel_count: int
    working_order_truth: str
    fill_truth: str
    position_truth: str
    retained_position_ticker: str | None
    retained_position_floor_contracts: Decimal
    automatic_flatten_authorized: bool
    bootstrap_contract_sha256: str

    def __init__(
        self,
        *,
        binding: ExecutionDomainBindingV1,
        bootstrap_class: str,
        bootstrap_cutoff_at_utc: str,
        inception_evidence: Sequence[EvidenceReferenceV1] = (),
        prestack_evidence: Sequence[EvidenceReferenceV1] = (),
        prestack_activity_completeness: str,
        unresolved_write_count: int,
        unresolved_cancel_count: int,
        working_order_truth: str,
        fill_truth: str,
        position_truth: str,
        retained_position_ticker: str | None,
        retained_position_floor_contracts: Decimal,
        automatic_flatten_authorized: bool = False,
    ) -> None:
        if type(binding) is not ExecutionDomainBindingV1:
            raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
        if (
            bootstrap_class not in BOOTSTRAP_CLASS_TO_COMPLETENESS
            or BOOTSTRAP_CLASS_TO_COMPLETENESS[bootstrap_class] != prestack_activity_completeness
        ):
            raise LedgerError(FailureCode.DOMAIN_BOOTSTRAP_COMPLETENESS_MISMATCH)
        for value in (working_order_truth, fill_truth, position_truth):
            if value not in _BOOTSTRAP_TRUTH_VALUES:
                raise LedgerError(FailureCode.DOMAIN_BOOTSTRAP_EVIDENCE_MISMATCH)
        if (
            type(unresolved_write_count) is not int or type(unresolved_write_count) is bool or unresolved_write_count < 0
            or type(unresolved_cancel_count) is not int or type(unresolved_cancel_count) is bool or unresolved_cancel_count < 0
            or automatic_flatten_authorized is not False
            or (retained_position_ticker is not None and type(retained_position_ticker) is not str)
            or type(retained_position_floor_contracts) is not Decimal
            or not retained_position_floor_contracts.is_finite()
            or retained_position_floor_contracts < 0
        ):
            raise LedgerError(FailureCode.DOMAIN_BOOTSTRAP_EVIDENCE_MISMATCH)
        canonical_timestamp_check = str(bootstrap_cutoff_at_utc)
        inception = tuple(inception_evidence)
        prestack = tuple(prestack_evidence)
        if any(type(e) is not EvidenceReferenceV1 for e in inception + prestack):
            raise LedgerError(FailureCode.DOMAIN_BOOTSTRAP_EVIDENCE_MISMATCH)
        object.__setattr__(self, "schema_revision", 1)
        object.__setattr__(self, "domain_binding_id", binding.binding_id)
        object.__setattr__(self, "domain_binding_sha256", binding.binding_sha256)
        object.__setattr__(self, "conflict_domain_ref", binding.conflict_domain_ref)
        object.__setattr__(self, "bootstrap_class", bootstrap_class)
        object.__setattr__(self, "bootstrap_cutoff_at_utc", canonical_timestamp_check)
        object.__setattr__(self, "inception_evidence", inception)
        object.__setattr__(self, "prestack_evidence", prestack)
        object.__setattr__(self, "prestack_activity_completeness", prestack_activity_completeness)
        object.__setattr__(self, "unresolved_write_count", unresolved_write_count)
        object.__setattr__(self, "unresolved_cancel_count", unresolved_cancel_count)
        object.__setattr__(self, "working_order_truth", working_order_truth)
        object.__setattr__(self, "fill_truth", fill_truth)
        object.__setattr__(self, "position_truth", position_truth)
        object.__setattr__(self, "retained_position_ticker", retained_position_ticker)
        object.__setattr__(self, "retained_position_floor_contracts", retained_position_floor_contracts)
        object.__setattr__(self, "automatic_flatten_authorized", False)
        object.__setattr__(
            self, "bootstrap_contract_sha256",
            sha256_hex(canonical_json_bytes(self._canonical_object())),
        )

    def _canonical_object(self) -> dict[str, object]:
        return {
            "automatic_flatten_authorized": False,
            "bootstrap_class": self.bootstrap_class,
            "bootstrap_cutoff_at_utc": self.bootstrap_cutoff_at_utc,
            "conflict_domain_ref": self.conflict_domain_ref,
            "domain_binding_id": self.domain_binding_id,
            "domain_binding_sha256": self.domain_binding_sha256,
            "fill_truth": self.fill_truth,
            "inception_evidence": [e.canonical_object() for e in self.inception_evidence],
            "position_truth": self.position_truth,
            "prestack_activity_completeness": self.prestack_activity_completeness,
            "prestack_evidence": [e.canonical_object() for e in self.prestack_evidence],
            "retained_position_floor_contracts": self.retained_position_floor_contracts,
            "retained_position_ticker": self.retained_position_ticker,
            "schema_revision": 1,
            "unresolved_cancel_count": self.unresolved_cancel_count,
            "unresolved_write_count": self.unresolved_write_count,
            "working_order_truth": self.working_order_truth,
        }

    def event_payload(self) -> dict[str, object]:
        """The exact ``EXECUTION_DOMAIN_BOOTSTRAP_RECORDED`` payload (DSB-BOOT-007)."""
        obj = self._canonical_object()
        del obj["schema_revision"]
        obj["bootstrap_schema_revision"] = 1
        obj["bootstrap_contract_sha256"] = self.bootstrap_contract_sha256
        return obj


@dataclass(frozen=True, slots=True, init=False)
class ActiveExecutionDomainContractV1:
    """Immutable active-domain safety/release contract (DSB-WRITER-001).

    Separate from ``LegacyIncidentContract`` -- never a subclass, wrapper, or
    repointed instance.  Its incident identity is domain-persistent and
    bootstrap-scoped, never session/request/invocation scoped.
    """

    schema_revision: int
    domain_binding_id: str
    domain_binding_sha256: str
    venue: str
    environment: str
    account_scope_ref: str
    subaccount: int
    exchange_index: int
    conflict_domain_ref: str
    bootstrap_contract_sha256: str
    incident_id: str
    writer_proof_id: str
    contract_id: str
    contract_sha256: str

    def __init__(
        self,
        *,
        binding: ExecutionDomainBindingV1,
        bootstrap_contract_sha256: str,
    ) -> None:
        if type(binding) is not ExecutionDomainBindingV1:
            raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
        if type(bootstrap_contract_sha256) is not str or not _is_exact_sha256_hex(bootstrap_contract_sha256):
            raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
        writer_proof_id = "adwp_" + _first_32_lower_hex(
            _ACTIVE_WRITER_PROOF_DOMAIN + binding.binding_sha256.encode("ascii")
        )
        incident_id = "adi_" + _first_32_lower_hex(
            _ACTIVE_HISTORY_ANCHOR_DOMAIN
            + binding.binding_sha256.encode("ascii")
            + b"\x00"
            + bootstrap_contract_sha256.encode("ascii")
        )
        canonical = {
            "account_scope_ref": binding.account_scope_ref,
            "bootstrap_contract_sha256": bootstrap_contract_sha256,
            "conflict_domain_ref": binding.conflict_domain_ref,
            "domain_binding_id": binding.binding_id,
            "domain_binding_sha256": binding.binding_sha256,
            "environment": binding.environment,
            "exchange_index": binding.exchange_index,
            "incident_id": incident_id,
            "schema_revision": 1,
            "subaccount": binding.subaccount,
            "venue": binding.venue,
            "writer_proof_id": writer_proof_id,
        }
        contract_sha256 = sha256_hex(canonical_json_bytes(canonical))
        for name, value in (
            ("schema_revision", 1),
            ("domain_binding_id", binding.binding_id),
            ("domain_binding_sha256", binding.binding_sha256),
            ("venue", binding.venue),
            ("environment", binding.environment),
            ("account_scope_ref", binding.account_scope_ref),
            ("subaccount", binding.subaccount),
            ("exchange_index", binding.exchange_index),
            ("conflict_domain_ref", binding.conflict_domain_ref),
            ("bootstrap_contract_sha256", bootstrap_contract_sha256),
            ("incident_id", incident_id),
            ("writer_proof_id", writer_proof_id),
            ("contract_sha256", contract_sha256),
            ("contract_id", "AEDC1_" + contract_sha256),
        ):
            object.__setattr__(self, name, value)

    def __copy__(self):
        raise TypeError("ActiveExecutionDomainContractV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("ActiveExecutionDomainContractV1 cannot be serialized")


def _reject_legacy_contract(value: object) -> None:
    if type(value) is LegacyIncidentContract:
        raise LedgerError(FailureCode.ACTIVE_PATH_LEGACY_CONTRACT_REJECTED)


def _require_active_contract(active_contract: object) -> ActiveExecutionDomainContractV1:
    _reject_legacy_contract(active_contract)
    if active_contract is None:
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_REQUIRED)
    if type(active_contract) is not ActiveExecutionDomainContractV1:
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
    # Recompute the contract identity; a mutated/forged instance fails closed.
    rebuilt = ActiveExecutionDomainContractV1(
        binding=ExecutionDomainBindingV1(
            venue=active_contract.venue,
            environment=active_contract.environment,
            account_scope_ref=active_contract.account_scope_ref,
            subaccount=active_contract.subaccount,
            exchange_index=active_contract.exchange_index,
        ),
        bootstrap_contract_sha256=active_contract.bootstrap_contract_sha256,
    )
    if (
        rebuilt.contract_sha256 != active_contract.contract_sha256
        or rebuilt.contract_id != active_contract.contract_id
        or rebuilt.incident_id != active_contract.incident_id
        or rebuilt.writer_proof_id != active_contract.writer_proof_id
        or rebuilt.domain_binding_id != active_contract.domain_binding_id
        or rebuilt.domain_binding_sha256 != active_contract.domain_binding_sha256
        or rebuilt.conflict_domain_ref != active_contract.conflict_domain_ref
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
    return active_contract


_ACTIVE_DOMAIN_COMMITMENT_KEYS = (
    "domain_binding_id", "domain_binding_sha256", "active_contract_id",
    "active_contract_sha256", "bootstrap_contract_sha256", "conflict_domain_ref",
    "account_scope_ref", "subaccount", "exchange_index", "environment",
    "incident_id", "writer_proof_id",
)


def active_domain_commitment(
    active_contract: ActiveExecutionDomainContractV1,
    domain_binding: ExecutionDomainBindingV1,
) -> dict:
    """The exact 12-field active execution-domain commitment carried by every
    active ordinary CREATE/CANCEL assessment/permit/prepared-request
    (DSB-WRITER-007/008).  For an active runtime NO field may be ``None``.
    Fails closed on a contract/binding mismatch."""
    contract = _require_active_contract(active_contract)
    if type(domain_binding) is not ExecutionDomainBindingV1:
        raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
    if (
        contract.domain_binding_id != domain_binding.binding_id
        or contract.domain_binding_sha256 != domain_binding.binding_sha256
        or contract.conflict_domain_ref != domain_binding.conflict_domain_ref
        or contract.account_scope_ref != domain_binding.account_scope_ref
        or contract.subaccount != domain_binding.subaccount
        or contract.exchange_index != domain_binding.exchange_index
        or contract.environment != domain_binding.environment
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH)
    return {
        "domain_binding_id": contract.domain_binding_id,
        "domain_binding_sha256": contract.domain_binding_sha256,
        "active_contract_id": contract.contract_id,
        "active_contract_sha256": contract.contract_sha256,
        "bootstrap_contract_sha256": contract.bootstrap_contract_sha256,
        "conflict_domain_ref": contract.conflict_domain_ref,
        "account_scope_ref": contract.account_scope_ref,
        "subaccount": contract.subaccount,
        "exchange_index": contract.exchange_index,
        "environment": contract.environment,
        "incident_id": contract.incident_id,
        "writer_proof_id": contract.writer_proof_id,
    }


def validate_active_domain_commitment(value: object) -> dict:
    """Reject a partial/None-bearing active commitment (DSB-WRITER-007:
    for an active runtime no active field may be ``None``)."""
    if not isinstance(value, Mapping) or set(value) != set(_ACTIVE_DOMAIN_COMMITMENT_KEYS):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
    for key in _ACTIVE_DOMAIN_COMMITMENT_KEYS:
        if value[key] is None:
            raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
    if not _is_exact_sha256_hex(value["domain_binding_sha256"]) or not _is_exact_sha256_hex(value["active_contract_sha256"]) or not _is_exact_sha256_hex(value["bootstrap_contract_sha256"]):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
    if type(value["subaccount"]) is not int or type(value["subaccount"]) is bool or type(value["exchange_index"]) is not int or type(value["exchange_index"]) is bool:
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
    return dict(value)


def _validate_active_contract_against_events(
    events: tuple, active_contract: ActiveExecutionDomainContractV1
) -> None:
    """History validator run inside the locked open (DSB-WRITER-008: active
    contract vs revision-2 ledger metadata/bootstrap and vs writer proof)."""
    if len(events) < 3:
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_BOOTSTRAP_COMMITMENT_MISMATCH)
    initial, bootstrap, hold = events[0], events[1], events[2]
    if (
        initial.event_type is not EventType.LEDGER_INITIALIZED
        or bootstrap.event_type is not EventType.EXECUTION_DOMAIN_BOOTSTRAP_RECORDED
        or hold.event_type is not EventType.WRITER_PROOF_HELD
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_BOOTSTRAP_COMMITMENT_MISMATCH)
    ip = initial.payload
    bp = bootstrap.payload
    hp = hold.payload
    if (
        ip.get("ledger_schema_revision") != ACTIVE_LEDGER_SCHEMA_REVISION
        or ip.get("execution_domain_binding_id") != active_contract.domain_binding_id
        or ip.get("execution_domain_binding_sha256") != active_contract.domain_binding_sha256
        or ip.get("conflict_domain_ref") != active_contract.conflict_domain_ref
        or ip.get("environment_classification") != active_contract.environment
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH)
    if (
        bp.get("domain_binding_id") != active_contract.domain_binding_id
        or bp.get("domain_binding_sha256") != active_contract.domain_binding_sha256
        or bp.get("bootstrap_contract_sha256") != active_contract.bootstrap_contract_sha256
        or bp.get("conflict_domain_ref") != active_contract.conflict_domain_ref
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_BOOTSTRAP_COMMITMENT_MISMATCH)
    if (
        hp.get("writer_proof_id") != active_contract.writer_proof_id
        or hp.get("conflict_domain_ref") != active_contract.conflict_domain_ref
        or hold.incident_id != active_contract.incident_id
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_WRITER_PROOF_MISMATCH)


def _validate_active_locked(locked: LockedLedger, active_contract: ActiveExecutionDomainContractV1) -> None:
    """DSB-WRITER-008: active contract vs revision-2 ledger_meta and authority row."""
    meta = locked.ledger_meta
    if type(meta) is not ActiveLedgerMeta:
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_LEDGER_SCHEMA_REQUIRED)
    row = locked.authority_row
    if (
        meta.ledger_schema_revision != ACTIVE_LEDGER_SCHEMA_REVISION
        or meta.environment_classification != active_contract.environment
        or meta.conflict_domain_ref != active_contract.conflict_domain_ref
        or meta.execution_domain_binding_id != active_contract.domain_binding_id
        or meta.execution_domain_binding_sha256 != active_contract.domain_binding_sha256
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH)
    parsed = parse_canonical_json(meta.execution_domain_binding_json)
    rebuilt_binding = ExecutionDomainBindingV1(
        venue=active_contract.venue,
        environment=active_contract.environment,
        account_scope_ref=active_contract.account_scope_ref,
        subaccount=active_contract.subaccount,
        exchange_index=active_contract.exchange_index,
    )
    if parsed != rebuilt_binding.canonical_object():
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH)
    if (
        row.conflict_domain_ref != active_contract.conflict_domain_ref
        or row.environment_classification != active_contract.environment
        or row.ledger_instance_id != meta.ledger_instance_id
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH)


def initialize_active_execution_domain_ledger(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    domain_binding: ExecutionDomainBindingV1,
    bootstrap_contract: DomainBootstrapContractV1,
    ledger_path: str,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
):
    """Venue wrapper for the revision-2 active-domain ledger initializer
    (DSB-PERSIST-005).  Deterministically reconstructs the active contract
    and never touches the historical revision-1 ledger."""
    if type(domain_binding) is not ExecutionDomainBindingV1 or type(bootstrap_contract) is not DomainBootstrapContractV1:
        raise LedgerError(FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)
    if (
        bootstrap_contract.domain_binding_id != domain_binding.binding_id
        or bootstrap_contract.domain_binding_sha256 != domain_binding.binding_sha256
    ):
        raise LedgerError(FailureCode.DOMAIN_LEDGER_BINDING_MISMATCH)
    if (
        domain_binding.account_scope_ref == CURRENT_ACCOUNT_SCOPE_REF
        and domain_binding.subaccount == 0
    ):
        raise LedgerError(FailureCode.LEGACY_PRIMARY_DOMAIN_SELECTED)
    active_contract = ActiveExecutionDomainContractV1(
        binding=domain_binding,
        bootstrap_contract_sha256=bootstrap_contract.bootstrap_contract_sha256,
    )
    kwargs: dict[str, object] = {}
    if clock is not None:
        kwargs["clock"] = clock
    if uuid_factory is not None:
        kwargs["uuid_factory"] = uuid_factory
    if fault_hook is not None:
        kwargs["fault_hook"] = fault_hook
    row = initialize_execution_domain_ledger_v2(
        binding,
        conflict_domain_ref=domain_binding.conflict_domain_ref,
        ledger_path=ledger_path,
        canonical_repository_root=canonical_repository_root,
        preledger_history_mode=bootstrap_contract.bootstrap_class,
        execution_domain_binding_id=domain_binding.binding_id,
        execution_domain_binding_sha256=domain_binding.binding_sha256,
        execution_domain_binding_json=domain_binding.canonical_json(),
        bootstrap_event_payload=bootstrap_contract.event_payload(),
        active_incident_id=active_contract.incident_id,
        active_writer_proof_id=active_contract.writer_proof_id,
        **kwargs,
    )
    return row, active_contract


def _active_open_kwargs(clock, uuid_factory, fault_hook) -> dict[str, object]:
    kwargs: dict[str, object] = {"ledger_revision": ACTIVE_LEDGER_SCHEMA_REVISION}
    if clock is not None:
        kwargs["clock"] = clock
    if uuid_factory is not None:
        kwargs["uuid_factory"] = uuid_factory
    if fault_hook is not None:
        kwargs["fault_hook"] = fault_hook
    return kwargs


def read_active_local_safety_state_v1(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    active_contract: ActiveExecutionDomainContractV1,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> OpenResult:
    """Gate-B local active-domain safety-state read (DSB-WRITER-005).  Opens,
    replays, and validates the active contract against the revision-2 ledger;
    exposes no LockedLedger and never appends."""
    contract = _require_active_contract(active_contract)
    opened = _acquire_normal_writer_candidate(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_active_contract_against_events(events, contract),
        **_active_open_kwargs(clock, uuid_factory, fault_hook),
    )
    locked = opened.handle
    if locked is None:
        return OpenResult(
            opened.projection, opened.restart_classification, None,
            opened.failure_code, opened.authority_ledger_relation,
        )
    try:
        _validate_active_locked(locked, contract)
        projection = locked.projection()
        return OpenResult(projection, projection.restart_classification, None, None, locked.relation)
    except LedgerError as exc:
        return OpenResult(None, RestartClassification.LEDGER_INTEGRITY_FAILURE, None, exc.code, locked.relation)
    finally:
        locked.close()


def read_active_trusted_release_evidence_projection_v1(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    active_contract: ActiveExecutionDomainContractV1,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> TrustedReleaseEvidenceReadResultV1:
    """Gate-B active trusted release-evidence projection (DSB-WRITER-005)."""
    contract = _require_active_contract(active_contract)
    opened = _acquire_normal_writer_candidate(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_active_contract_against_events(events, contract),
        **_active_open_kwargs(clock, uuid_factory, fault_hook),
    )
    locked = opened.handle
    if locked is None:
        return TrustedReleaseEvidenceReadResultV1(
            None, opened.restart_classification, opened.failure_code, opened.authority_ledger_relation,
        )
    try:
        _validate_active_locked(locked, contract)
        universe = _derive_authoritative_release_universe(locked)
        tail = locked.events[-1]
        authority = locked.authority_row
        observed_tail = (tail.sequence, tail.event_hash)
        if (
            (authority.trusted_sequence, authority.trusted_event_hash) != observed_tail
            or (opened.projection.trusted_sequence, opened.projection.trusted_event_hash) != observed_tail
        ):
            return TrustedReleaseEvidenceReadResultV1(
                None, opened.projection.restart_classification,
                FailureCode.AUTHORITY_LEDGER_ANCHOR_HASH_MISMATCH, locked.relation,
            )
        projection = TrustedReleaseEvidenceProjectionV1(
            _TRUSTED_RELEASE_EVIDENCE_PROJECTION_KEY,
            schema_revision=1,
            environment_classification=locked.ledger_meta.environment_classification,
            conflict_domain_ref=locked.conflict_domain_ref,
            authority_instance_id=locked.authority_meta.authority_instance_id,
            authority_namespace_id=locked.authority_meta.authority_namespace_id,
            authority_store_path_identity_sha256=locked.authority_meta.authority_store_path_identity_sha256,
            ledger_instance_id=locked.ledger_meta.ledger_instance_id,
            ledger_path_identity_sha256=locked.ledger_meta.ledger_path_identity_sha256,
            authority_trusted_sequence=authority.trusted_sequence,
            authority_trusted_event_hash=authority.trusted_event_hash,
            ledger_terminal_sequence=tail.sequence,
            ledger_terminal_event_hash=tail.event_hash,
            working_orders=universe.working_orders,
            fills=universe.fills,
            cancel_order_on_pause_order_ids=universe.cancel_order_on_pause_order_ids,
            latest_order_event_ids=MappingProxyType(dict(universe.latest_order_event_ids)),
            fill_matching_event_ids=MappingProxyType(dict(universe.fill_event_ids)),
            conflict_ids=universe.conflict_ids,
        )
        return TrustedReleaseEvidenceReadResultV1(
            projection, opened.projection.restart_classification, None, locked.relation,
        )
    except LedgerError as exc:
        return TrustedReleaseEvidenceReadResultV1(
            None, RestartClassification.LEDGER_INTEGRITY_FAILURE, exc.code, locked.relation,
        )
    finally:
        locked.close()


def _acquire_active_narrow_restricted(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    acquisition_mode: AcquisitionMode,
    active_contract: ActiveExecutionDomainContractV1,
    expected_ledger_path: str | None,
    clock,
    uuid_factory,
    fault_hook,
    monotonic_clock_ns=None,
    release_wall_clock=None,
) -> RestrictedAcquisition:
    contract = _require_active_contract(active_contract)
    opened = _acquire_restricted_state(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        acquisition_mode=acquisition_mode,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_active_contract_against_events(events, contract),
        **_active_open_kwargs(clock, uuid_factory, fault_hook),
    )
    if opened.locked is None:
        return RestrictedAcquisition(
            opened.restart_classification, opened.projection, None,
            opened.failure_code, opened.authority_ledger_relation,
        )
    try:
        _validate_active_locked(opened.locked, contract)
    except LedgerError as exc:
        opened.locked.close()
        return RestrictedAcquisition(
            RestartClassification.LEDGER_INTEGRITY_FAILURE, None, None, exc.code,
            opened.authority_ledger_relation,
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


def acquire_active_emergency_control_only_v1(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    active_contract: ActiveExecutionDomainContractV1,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> RestrictedAcquisition:
    return _acquire_active_narrow_restricted(
        binding, canonical_repository_root=canonical_repository_root,
        acquisition_mode=AcquisitionMode.EMERGENCY_CONTROL_ONLY, active_contract=active_contract,
        expected_ledger_path=expected_ledger_path, clock=clock, uuid_factory=uuid_factory,
        fault_hook=fault_hook,
    )


def acquire_active_release_only_v1(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    active_contract: ActiveExecutionDomainContractV1,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
    monotonic_clock_ns=None,
    release_wall_clock=None,
) -> RestrictedAcquisition:
    return _acquire_active_narrow_restricted(
        binding, canonical_repository_root=canonical_repository_root,
        acquisition_mode=AcquisitionMode.RELEASE_ONLY, active_contract=active_contract,
        expected_ledger_path=expected_ledger_path, clock=clock, uuid_factory=uuid_factory,
        fault_hook=fault_hook, monotonic_clock_ns=monotonic_clock_ns,
        release_wall_clock=release_wall_clock,
    )


class ActiveReleaseEvaluationStateV1:
    """DSB-WRITER-004.  Same current-release inputs as
    ``ReleaseEvaluationStateV1`` except it carries the active contract and
    forbids separately caller-supplied active incident/proof IDs; those are
    derived only from ``active_contract``.

    Correction 02 adds one mandatory input commitment: the exact private
    trusted dynamic read-set identity (``ADRS2_<64hex>``) that supported
    this release.  No public constructor accepts a caller-created
    ``DynamicIndexDomainAccountWideReadV1`` as equivalent release truth --
    only the composite identity string flows here, and Stage 3F is what
    verifies the private read-set type + live issuer lineage that produced
    it."""

    __slots__ = ("__active_contract", "__inner", "__trusted_dynamic_read_set_id")

    def __init__(
        self,
        *,
        process_instance_id: str,
        active_contract: ActiveExecutionDomainContractV1,
        trusted_dynamic_read_set_id: str,
        risk_config,
        risk_snapshot,
        reconciliation_snapshot,
        market_freshness,
        reconciliation_freshness,
        venue_defense_evidence,
        normal_gate,
        emergency_gate,
    ) -> None:
        contract = _require_active_contract(active_contract)
        if not _is_adrs2_read_set_id(trusted_dynamic_read_set_id):
            raise LedgerError(FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)
        self.__active_contract = contract
        self.__trusted_dynamic_read_set_id = trusted_dynamic_read_set_id
        self.__inner = ReleaseEvaluationStateV1(
            process_instance_id=process_instance_id,
            incident_id=contract.incident_id,
            writer_proof_id=contract.writer_proof_id,
            risk_config=risk_config,
            risk_snapshot=risk_snapshot,
            reconciliation_snapshot=reconciliation_snapshot,
            market_freshness=market_freshness,
            reconciliation_freshness=reconciliation_freshness,
            venue_defense_evidence=venue_defense_evidence,
            normal_gate=normal_gate,
            emergency_gate=emergency_gate,
        )

    @property
    def active_contract(self) -> ActiveExecutionDomainContractV1:
        return self.__active_contract

    @property
    def trusted_dynamic_read_set_id(self) -> str:
        return self.__trusted_dynamic_read_set_id

    @property
    def inner(self) -> ReleaseEvaluationStateV1:
        return self.__inner

    def replace(self, **kwargs) -> None:
        self.__inner.replace(**kwargs)

    def __copy__(self):
        raise TypeError("ActiveReleaseEvaluationStateV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("ActiveReleaseEvaluationStateV1 cannot be serialized")


_ACTIVE_COMPLETION_KEY = object()
_active_completion_registry_lock = threading.Lock()
_active_completion_registry: dict[int, "CurrentProcessReleaseCompletionV2"] = {}


def _register_active_completion(token: "CurrentProcessReleaseCompletionV2") -> None:
    with _active_completion_registry_lock:
        _active_completion_registry[id(token)] = token


def _is_registered_active_completion(token: object) -> bool:
    with _active_completion_registry_lock:
        return _active_completion_registry.get(id(token)) is token


def _consume_active_completion(token: "CurrentProcessReleaseCompletionV2") -> None:
    with _active_completion_registry_lock:
        if _active_completion_registry.get(id(token)) is token:
            del _active_completion_registry[id(token)]


@dataclass(frozen=True, slots=True, init=False)
class CurrentProcessReleaseCompletionV2:
    """DSB-WRITER-006.  Preserves every V1 one-shot / process-local /
    non-copyable / non-serializable property and adds exact active-domain
    commitments.  A V1 token cannot acquire an active revision-2 normal
    writer; a V2 token cannot acquire the legacy N=0 writer path.

    Correction 02 additionally requires the completion lineage to commit to
    the exact accepted private dynamic read-set identity
    (``trusted_dynamic_read_set_id`` = ``ADRS2_<64hex>``) that supported the
    release."""

    v1: CurrentProcessReleaseCompletionV1
    active_contract_id: str
    active_contract_sha256: str
    domain_binding_id: str
    domain_binding_sha256: str
    bootstrap_contract_sha256: str
    incident_id: str
    writer_proof_id: str
    trusted_dynamic_read_set_id: str

    def __init__(self, key: object, **values: object) -> None:
        if key is not _ACTIVE_COMPLETION_KEY:
            raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def __copy__(self):
        raise TypeError("CurrentProcessReleaseCompletionV2 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("CurrentProcessReleaseCompletionV2 cannot be serialized")


def issue_active_current_process_release_completion_v2(
    release_handle: ReleaseLedgerHandle,
    assessment: "ReleaseAssessmentV1",
    *,
    active_contract: ActiveExecutionDomainContractV1,
    trusted_dynamic_read_set_id: str,
) -> CurrentProcessReleaseCompletionV2:
    """Issue the V2 completion token from an active RELEASE_ONLY handle after
    the durable release sequence and restricted-session-end readback
    (DSB-WRITER-006).  Consumes the intermediate V1 token so only the V2
    admission remains valid.

    Correction 02 requires ``trusted_dynamic_read_set_id`` -- the exact
    ``ADRS2_<64hex>`` identity of the private
    ``_ReleaseEligibleDynamicIndexDomainReadSetV2`` that fed Stage 3F -- to
    be committed into the completion lineage."""
    contract = _require_active_contract(active_contract)
    if type(release_handle) is not ReleaseLedgerHandle:
        raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)
    if not _is_adrs2_read_set_id(trusted_dynamic_read_set_id):
        raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)
    if (
        assessment.writer_proof_id != contract.writer_proof_id
        or assessment.private_source_identity is None
    ):
        raise LedgerError(FailureCode.ACTIVE_DOMAIN_WRITER_PROOF_MISMATCH)
    v1 = release_handle.complete_release_and_issue_current_process_completion(assessment)
    if (
        type(v1) is not CurrentProcessReleaseCompletionV1
        or not _is_registered_current_process_release_completion(v1)
        or v1.writer_proof_id != contract.writer_proof_id
    ):
        raise LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)
    _consume_current_process_release_completion(v1)
    token = CurrentProcessReleaseCompletionV2(
        _ACTIVE_COMPLETION_KEY,
        v1=v1,
        active_contract_id=contract.contract_id,
        active_contract_sha256=contract.contract_sha256,
        domain_binding_id=contract.domain_binding_id,
        domain_binding_sha256=contract.domain_binding_sha256,
        bootstrap_contract_sha256=contract.bootstrap_contract_sha256,
        incident_id=contract.incident_id,
        writer_proof_id=contract.writer_proof_id,
        trusted_dynamic_read_set_id=trusted_dynamic_read_set_id,
    )
    _register_active_completion(token)
    return token


def acquire_active_normal_writer_state_v1(
    binding: AuthorityNamespaceBinding,
    *,
    canonical_repository_root: str,
    risk_config,
    process_instance_id: str,
    current_process_release_completion: CurrentProcessReleaseCompletionV2,
    active_contract: ActiveExecutionDomainContractV1,
    expected_ledger_path: str | None = None,
    clock=None,
    uuid_factory=None,
    fault_hook=None,
) -> NormalWriterAcquisition:
    """Sole supported revision-2 active-domain normal-writer acquisition
    (DSB-WRITER-005/006, DSB-WRITER-008 Stage 3J/3K).  Rejects a legacy
    contract, a V1 completion token, and any active-contract/domain/
    bootstrap/incident/proof mismatch before returning a handle."""
    contract = _require_active_contract(active_contract)
    opened = _acquire_normal_writer_candidate(
        binding,
        conflict_domain_ref=contract.conflict_domain_ref,
        expected_environment=contract.environment,
        canonical_repository_root=canonical_repository_root,
        expected_ledger_path=expected_ledger_path,
        history_validator=lambda events: _validate_active_contract_against_events(events, contract),
        **_active_open_kwargs(clock, uuid_factory, fault_hook),
    )
    locked = opened.handle
    if locked is None:
        return NormalWriterAcquisition(
            opened.projection, opened.restart_classification, None, None,
            opened.failure_code, opened.authority_ledger_relation,
        )
    try:
        _validate_active_locked(locked, contract)
    except LedgerError as exc:
        locked.close()
        return NormalWriterAcquisition(
            None, RestartClassification.LEDGER_INTEGRITY_FAILURE, None, None, exc.code, locked.relation,
        )
    projection = locked.projection()
    tail = locked.events[-1]
    authority = locked.authority_row
    observed_tail = (tail.sequence, tail.event_hash)
    proof_state = projection.writer_proof_state_by_proof_id.get(contract.writer_proof_id)
    proof_eligible = projection.writer_proof_release_eligible_by_proof_id.get(contract.writer_proof_id)
    from arb.venues.kalshi.risk_control import RiskLimitConfigV1 as _RiskLimitConfigV1
    durable_eligible = (
        projection.history_completeness in BOOTSTRAP_CLASS_TO_COMPLETENESS.values()
        and projection.protected_unresolved_legacy_write_count == 0
        and not projection.unresolved_write_request_ids
        and proof_state == "RELEASED"
        and proof_eligible is True
        and projection.risk_control_state == "WRITER_ELIGIBLE"
        and projection.active_risk_config_sha256 is not None
        and type(risk_config) is _RiskLimitConfigV1
        and risk_config.conflict_domain == contract.conflict_domain_ref
        and risk_config.sha256 == projection.active_risk_config_sha256
        and projection.active_restricted_session_id is None
        and not any(projection.cancel_send_may_have_been_sent_by_attempt.values())
        and (authority.trusted_sequence, authority.trusted_event_hash) == observed_tail
        and (projection.trusted_sequence, projection.trusted_event_hash) == observed_tail
        and (projection.last_sequence, projection.terminal_event_hash) == observed_tail
    )
    if not durable_eligible:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED, locked.relation,
        )
    token = current_process_release_completion
    if token is None:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED, locked.relation,
        )
    if type(token) is CurrentProcessReleaseCompletionV1:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID, locked.relation,
        )
    if type(token) is not CurrentProcessReleaseCompletionV2 or not _is_registered_active_completion(token):
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID, locked.relation,
        )
    # The embedded V1 token has been deliberately consumed from the V1
    # registry by ``issue_active_current_process_release_completion_v2`` (only
    # the V2 admission remains valid), so its structural contract is verified
    # directly here rather than via the V1 live-registry helper.
    _v1 = token.v1
    if (
        type(_v1) is not CurrentProcessReleaseCompletionV1
        or type(_v1.schema_revision) is not int or _v1.schema_revision != 1
        or type(_v1.process_instance_id) is not str or not _v1.process_instance_id
        or type(_v1.release_id) is not str or not _v1.release_id.startswith("rel_")
        or type(_v1.writer_proof_id) is not str or not _v1.writer_proof_id
        or not _is_exact_sha256_hex(_v1.risk_config_sha256)
        or type(_v1.resulting_risk_state_epoch) is not int or _v1.resulting_risk_state_epoch < 0
        or not _is_exact_event_id(_v1.writer_eligible_state_event_id)
        or not _is_exact_sha256_hex(_v1.writer_eligible_state_event_hash)
        or type(_v1.authority_trusted_sequence) is not int or _v1.authority_trusted_sequence <= 0
        or not _is_exact_sha256_hex(_v1.authority_trusted_event_hash)
        or type(_v1.ledger_terminal_sequence) is not int or _v1.ledger_terminal_sequence <= 0
        or not _is_exact_sha256_hex(_v1.ledger_terminal_event_hash)
        or not _is_exact_event_id(_v1.release_session_ended_event_id)
        or not _is_exact_sha256_hex(_v1.release_session_ended_event_hash)
    ):
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID, locked.relation,
        )
    if (
        token.active_contract_id != contract.contract_id
        or token.active_contract_sha256 != contract.contract_sha256
        or token.domain_binding_id != contract.domain_binding_id
        or token.domain_binding_sha256 != contract.domain_binding_sha256
        or token.bootstrap_contract_sha256 != contract.bootstrap_contract_sha256
        or token.incident_id != contract.incident_id
        or token.writer_proof_id != contract.writer_proof_id
    ):
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH, locked.relation,
        )
    # DSB-WRITER-006: the completion lineage must carry the exact accepted
    # private dynamic read-set identity that supported the release.
    if not _is_adrs2_read_set_id(token.trusted_dynamic_read_set_id):
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID, locked.relation,
        )
    if token.v1.process_instance_id != process_instance_id:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_PROCESS_MISMATCH, locked.relation,
        )
    events_by_id = {event.event_id: event for event in locked.events}
    v1 = token.v1
    writer_eligible_event = events_by_id.get(v1.writer_eligible_state_event_id)
    session_ended_event = events_by_id.get(v1.release_session_ended_event_id)
    stale = (
        v1.writer_proof_id != contract.writer_proof_id
        or v1.risk_config_sha256 != risk_config.sha256
        or projection.risk_state_epoch != v1.resulting_risk_state_epoch
        or writer_eligible_event is None
        or writer_eligible_event.event_type is not EventType.RISK_CONTROL_STATE_CHANGED
        or writer_eligible_event.event_hash != v1.writer_eligible_state_event_hash
        or writer_eligible_event.payload.get("previous_state") != "SAFE_HELD"
        or writer_eligible_event.payload.get("new_state") != "WRITER_ELIGIBLE"
        or writer_eligible_event.payload.get("cause") != "DURABLE_RELEASE_COMPLETED"
        or writer_eligible_event.payload.get("related_release_id") != v1.release_id
        or session_ended_event is None
        or session_ended_event.event_type is not EventType.RESTRICTED_SESSION_ENDED
        or session_ended_event.event_hash != v1.release_session_ended_event_hash
        or (v1.authority_trusted_sequence, v1.authority_trusted_event_hash) != observed_tail
        or (v1.ledger_terminal_sequence, v1.ledger_terminal_event_hash) != observed_tail
    )
    if stale:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None,
            FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_STALE, locked.relation,
        )
    _consume_active_completion(token)
    relation = locked.relation
    try:
        session_id = start_writer_session(locked, prior_session_state="NONE")
    except LedgerError as exc:
        locked.close()
        return NormalWriterAcquisition(
            projection, projection.restart_classification, None, None, exc.code, relation,
        )
    final_projection = locked.projection()
    if final_projection.active_writer_session_id != session_id:
        locked.close()
        return NormalWriterAcquisition(
            final_projection, final_projection.restart_classification, None, None,
            FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED, relation,
        )
    return NormalWriterAcquisition(
        final_projection, final_projection.restart_classification, locked, session_id, None, relation,
    )


# ===========================================================================
# Correction 02 Section 14 -- exact retained-position terminal-settlement
# binding (DSB-SETTLE-001..005).  The current N1 terminal settlement is a
# historical accepted-evidence fact; runtime issues NO fresh settlements GET
# and adds no settlement operation to the trusted pre-release capability.
# ===========================================================================

# The exact frozen canonical object (DSB-SETTLE-001).  Its canonical JSON is
# 580 bytes and hashes to the frozen identity below; there is no
# caller-supplied settlement time / result / count / response-identity
# override.
_ATSE1_CANONICAL_OBJECT: Mapping[str, object] = MappingProxyType({
    "evidence_bytes": 26321,
    "evidence_name": "KALSHI_DEMO_SUBACCOUNT1_EXCHANGE_INDEX_DOMAIN_COMPLETENESS_DIAGNOSTIC_02_RESULT.json",
    "evidence_sha256": "2fc189b2a807a6c22ab3e71e41a6cfa66415e3bda87e6c8e66c3eb6e8029c69b",
    "exchange_index": 0,
    "market_result": "yes",
    "schema_revision": 1,
    "settled_time": "2026-09-02T14:41:43.665741Z",
    "settlement_economic_rows_digest_sha256": "3b73590a086e12538e8da7f0dc21c9b3717c85676e84fd5effb3a63f654e3965",
    "settlement_response_sha256": "562f47b835201d3445805102a25b3550582263367570847f4cf48b92a0dab119",
    "ticker": "KXAAAGASD-26SEP02-4.1200",
    "yes_count_fp": "1.00",
})
_ATSE1_CANONICAL_JSON = canonical_json_text(dict(_ATSE1_CANONICAL_OBJECT))
_ATSE1_CANONICAL_BYTES = len(canonical_json_bytes(dict(_ATSE1_CANONICAL_OBJECT)))
ACCEPTED_TERMINAL_SETTLEMENT_SHA256 = sha256_hex(canonical_json_bytes(dict(_ATSE1_CANONICAL_OBJECT)))
ACCEPTED_TERMINAL_SETTLEMENT_ID = "ATSE1_" + ACCEPTED_TERMINAL_SETTLEMENT_SHA256
_ATSE1_CONSTRUCTION_KEY = object()
_RETAINED_FLOOR_RECONCILED = "RETAINED_POSITION_TERMINALLY_SETTLED"


@dataclass(frozen=True, slots=True, init=False)
class AcceptedTerminalSettlementEvidenceV1:
    """DSB-SETTLE-001.  One immutable logical onboarding record for the
    current N1 retained-ticker terminal settlement.  Construction requires
    EXACT equality with the fixed canonical object -- any changed field
    (settled time, result, count, ticker, exchange index, evidence SHA,
    settlement-response SHA, economic-row digest) fails
    ``P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH``.  An exact P02 filename/SHA
    label on arbitrary settlement content is not sufficient (DSB-SETTLE-004)."""

    schema_revision: int
    evidence_bytes: int
    evidence_name: str
    evidence_sha256: str
    exchange_index: int
    market_result: str
    settled_time: str
    settlement_economic_rows_digest_sha256: str
    settlement_response_sha256: str
    ticker: str
    yes_count_fp: str
    canonical_bytes: int
    canonical_sha256: str
    id: str

    def __init__(self, key: object, *, candidate_object: Mapping[str, object]) -> None:
        if key is not _ATSE1_CONSTRUCTION_KEY:
            raise LedgerError(FailureCode.P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH)
        if not isinstance(candidate_object, Mapping):
            raise LedgerError(FailureCode.P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH)
        candidate = dict(candidate_object)
        try:
            candidate_json = canonical_json_text(candidate)
            candidate_sha = sha256_hex(canonical_json_bytes(candidate))
        except (TypeError, ValueError) as exc:
            raise LedgerError(FailureCode.P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH) from exc
        if (
            candidate_json != _ATSE1_CANONICAL_JSON
            or candidate_sha != ACCEPTED_TERMINAL_SETTLEMENT_SHA256
        ):
            raise LedgerError(FailureCode.P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH)
        frozen = dict(_ATSE1_CANONICAL_OBJECT)
        for name, value in frozen.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "canonical_bytes", _ATSE1_CANONICAL_BYTES)
        object.__setattr__(self, "canonical_sha256", ACCEPTED_TERMINAL_SETTLEMENT_SHA256)
        object.__setattr__(self, "id", ACCEPTED_TERMINAL_SETTLEMENT_ID)

    def __copy__(self):
        raise TypeError("AcceptedTerminalSettlementEvidenceV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("AcceptedTerminalSettlementEvidenceV1 cannot be serialized")


def n1_accepted_terminal_settlement_evidence(
    candidate_object: Mapping[str, object] | None = None,
) -> AcceptedTerminalSettlementEvidenceV1:
    """Explicit N1 onboarding constructor for the exact accepted terminal
    settlement (DSB-SETTLE-001).  With no argument it builds the frozen
    record; a supplied object must equal the frozen canonical object exactly
    or ``P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH`` is raised."""
    obj = dict(_ATSE1_CANONICAL_OBJECT) if candidate_object is None else candidate_object
    return AcceptedTerminalSettlementEvidenceV1(_ATSE1_CONSTRUCTION_KEY, candidate_object=obj)


def reconcile_retained_bootstrap_floor_v1(
    *,
    accepted_settlement: AcceptedTerminalSettlementEvidenceV1,
    retained_position_ticker: str,
    retained_position_floor_contracts: Decimal,
    retained_route_exchange_index: int,
    fresh_all_index_positions_complete: bool,
    current_retained_ticker_live_contracts: Decimal,
    ambiguous_event_positions_present: bool,
    other_positions_all_accounted: bool,
) -> str:
    """DSB-SETTLE-003/004.  Returns ``"RETAINED_POSITION_TERMINALLY_SETTLED"``
    only when ALL hold: exact accepted ``AcceptedTerminalSettlementEvidenceV1``
    identity; accepted ticker == bootstrap retained ticker; accepted
    exchange_index == bootstrap selected retained route/index; yes_count_fp
    Decimal == Decimal("1.00") and covers the retained floor exactly;
    market_result == "yes"; a fresh complete trusted all-index positions
    traversal; no current nonzero retained-ticker live position; no ambiguous
    nonempty ``event_positions``; and every other current position row
    accounted by the existing risk economics.  Empty current positions alone
    are insufficient.  Otherwise ``N1_RETAINED_POSITION_NOT_RECONCILED``."""
    if (
        type(accepted_settlement) is not AcceptedTerminalSettlementEvidenceV1
        or accepted_settlement.id != ACCEPTED_TERMINAL_SETTLEMENT_ID
        or accepted_settlement.canonical_sha256 != ACCEPTED_TERMINAL_SETTLEMENT_SHA256
    ):
        raise LedgerError(FailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)
    try:
        settled = Decimal(accepted_settlement.yes_count_fp)
        floor = retained_position_floor_contracts if type(retained_position_floor_contracts) is Decimal else None
        live = current_retained_ticker_live_contracts if type(current_retained_ticker_live_contracts) is Decimal else None
    except Exception as exc:  # noqa: BLE001 - fail closed on any Decimal error
        raise LedgerError(FailureCode.N1_RETAINED_POSITION_NOT_RECONCILED) from exc
    if (
        accepted_settlement.ticker != retained_position_ticker
        or type(retained_route_exchange_index) is not int
        or type(retained_route_exchange_index) is bool
        or accepted_settlement.exchange_index != retained_route_exchange_index
        or accepted_settlement.market_result != "yes"
        or floor is None or not floor.is_finite() or floor < 0
        or not settled.is_finite()
        or settled != Decimal("1.00")
        or settled < floor
        or fresh_all_index_positions_complete is not True
        or live is None or not live.is_finite() or live != 0
        or ambiguous_event_positions_present is not False
        or other_positions_all_accounted is not True
    ):
        raise LedgerError(FailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)
    return _RETAINED_FLOOR_RECONCILED


__all__ = [
    "AuthorityAnchoredSendGate", "CURRENT_ACCOUNT_SCOPE_REF", "CURRENT_CLIENT_ORDER_ID",
    "CURRENT_CONFLICT_DOMAIN_REF", "CURRENT_DISPOSITION", "CURRENT_ENVIRONMENT",
    "CURRENT_INCIDENT_ID", "CURRENT_LEGACY_INCIDENT_CONTRACT", "CURRENT_TICKER",
    "CURRENT_WRITER_PROOF_ID", "EvidenceExpectation", "LegacyIncidentContract",
    "EmergencyControlLedgerHandle", "LegacyImportAcquisition", "LegacyImportOnlyHandle", "LegacyImportResult",
    "LegacyImportStatus", "PRODUCTION_EVIDENCE_EXPECTATIONS", "ValidatedLegacyEvidence",
    "CurrentProcessReleaseCompletionV1", "NormalWriterAcquisition",
    "ReleaseAssessmentV1", "ReleaseEvaluationStateV1", "ReleaseLedgerHandle",
    "ReleaseReconciliationSnapshotV1", "ReleaseRiskSnapshotV1", "RestrictedAcquisition",
    "VenueDefenseEvidenceV1", "acquire_emergency_control_only",
    "acquire_legacy_import_only", "acquire_normal_writer_state", "acquire_release_only",
    "append_authority_anchored_send_gate", "canonical_kalshi_fill_payload",
    "prepared_request_identity", "validate_legacy_evidence",
    "validate_venue_defense_evidence",
    "TrustedReleaseEvidenceProjectionV1", "TrustedReleaseEvidenceReadResultV1",
    "read_trusted_release_evidence_projection",
    "ExecutionDomainBindingV1", "EvidenceReferenceV1", "DomainBootstrapContractV1",
    "ActiveExecutionDomainContractV1", "ActiveReleaseEvaluationStateV1",
    "CurrentProcessReleaseCompletionV2", "initialize_active_execution_domain_ledger",
    "read_active_local_safety_state_v1", "read_active_trusted_release_evidence_projection_v1",
    "acquire_active_emergency_control_only_v1", "acquire_active_release_only_v1",
    "acquire_active_normal_writer_state_v1",
    "issue_active_current_process_release_completion_v2",
    "active_domain_commitment", "validate_active_domain_commitment",
    "AcceptedTerminalSettlementEvidenceV1", "ACCEPTED_TERMINAL_SETTLEMENT_ID",
    "ACCEPTED_TERMINAL_SETTLEMENT_SHA256", "n1_accepted_terminal_settlement_evidence",
    "reconcile_retained_bootstrap_floor_v1",
]
