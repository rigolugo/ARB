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
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Callable, Mapping

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
    acquire_local_state,
    canonical_json_bytes,
    parse_canonical_json,
    sha256_hex,
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
    "LegacyImportAcquisition", "LegacyImportOnlyHandle", "LegacyImportResult",
    "LegacyImportStatus", "PRODUCTION_EVIDENCE_EXPECTATIONS", "ValidatedLegacyEvidence",
    "acquire_legacy_import_only", "acquire_normal_writer_state",
    "append_authority_anchored_send_gate", "canonical_kalshi_fill_payload",
    "prepared_request_identity", "validate_legacy_evidence",
]
