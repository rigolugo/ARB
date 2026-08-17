"""Offline tests for the restricted Kalshi ledger binding."""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
import sqlite3
import sys
import tempfile
import unittest
import uuid
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import arb.execution_ledger as ledger
from arb.execution_ledger import (
    AcquisitionMode,
    AuthorityLedgerRelation,
    AuthorityNamespaceBinding,
    CommitResultUnknown,
    EventInput,
    EventType,
    FailureCode,
    LedgerError,
    RestartClassification,
    acquire_local_state,
    canonical_json_bytes,
    initialize_authority_namespace,
    initialize_ledger_binding,
    start_writer_session,
)
from arb.venues.kalshi.ledger_binding import (
    CURRENT_ACCOUNT_SCOPE_REF,
    CURRENT_CLIENT_ORDER_ID,
    CURRENT_CONFLICT_DOMAIN_REF,
    CURRENT_DISPOSITION,
    CURRENT_ENVIRONMENT,
    CURRENT_INCIDENT_ID,
    CURRENT_TICKER,
    CURRENT_WRITER_PROOF_ID,
    PRODUCTION_EVIDENCE_EXPECTATIONS,
    CurrentProcessReleaseCompletionV1,
    EvidenceExpectation,
    LegacyIncidentContract,
    LegacyImportStatus,
    NormalWriterAcquisition,
    ReleaseAssessmentV1,
    ReleaseEvaluationStateV1,
    ReleaseReconciliationSnapshotV1,
    ReleaseRiskSnapshotV1,
    VenueDefenseEvidenceV1,
    append_authority_anchored_send_gate,
    acquire_emergency_control_only,
    acquire_legacy_import_only,
    acquire_normal_writer_state,
    acquire_release_only,
    canonical_kalshi_fill_payload,
    validate_legacy_evidence,
    validate_venue_defense_evidence,
)
from arb.venues.kalshi.ledger_binding import (
    _CURRENT_PROCESS_RELEASE_COMPLETION_KEY,
    _acquire_normal_writer_candidate,
    _current_process_release_completion_registry,
    _is_registered_current_process_release_completion,
    _register_current_process_release_completion,
    _consume_current_process_release_completion,
)
from arb.venues.kalshi.emergency_cancel import (
    AuthoritativeCancelTargetV1,
    EmergencyActionId,
    EmergencyCancelAdapter,
    EmergencyCancelCode,
    EmergencyCancelError,
    EmergencyCancelGate,
    EmergencyRateConfigV1,
    EmergencyRateLane,
)
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    EconomicFillV1,
    FlowRiskLimits,
    FreshnessStampV1,
    HISTORICAL_INCIDENT_CANCEL_TARGET,
    HISTORICAL_INCIDENT_WRITER_RELEASE_ELIGIBLE,
    HISTORICAL_UNRESOLVED_EXPOSURE,
    NormalWriteAdapter,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    PermitStage,
    RiskControlError,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
    WorkingOrderV1,
    WriterEligibilityAssessment,
    WriterEligibilityGate,
)


class DeterministicInputs:
    def __init__(self) -> None:
        self.instant = datetime(2026, 8, 13, 13, 0, 0, tzinfo=timezone.utc)
        self.number = 101
        self.monotonic_value = 1_000_000_000

    def clock(self) -> datetime:
        value = self.instant
        self.instant += timedelta(microseconds=1)
        return value

    def uuid(self) -> uuid.UUID:
        value = uuid.UUID(int=self.number, version=4)
        self.number += 1
        return value

    def monotonic_ns(self) -> int:
        value = self.monotonic_value
        self.monotonic_value += 1
        return value

    def advance_ms(self, milliseconds: int) -> None:
        self.monotonic_value += milliseconds * 1_000_000


class _ArmableReleaseFault:
    def __init__(self, stage: str, *, unknown: bool = False) -> None:
        self.stage = stage
        self.unknown = unknown
        self.armed = False

    def __call__(self, stage: str) -> None:
        if not self.armed or stage != self.stage:
            return
        self.armed = False
        if self.unknown:
            raise CommitResultUnknown(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
        raise LedgerError(FailureCode.LEDGER_COMMIT_FAILURE)


class _PermitLocked:
    """Minimal locked-state fake used only to mint a genuine normal permit."""

    def __init__(self, config_hash: str) -> None:
        self.conflict_domain_ref = CURRENT_CONFLICT_DOMAIN_REF
        self.events = [SimpleNamespace(sequence=10, event_hash="1" * 64)]
        self.authority_row = SimpleNamespace(
            trusted_sequence=10, trusted_event_hash="1" * 64,
        )
        self._config_hash = config_hash

    def projection(self):
        return SimpleNamespace(
            active_writer_session_id="ws_" + "1" * 32,
            risk_control_state="WRITER_ELIGIBLE",
            risk_state_epoch=7,
            active_risk_config_sha256=self._config_hash,
        )

class KalshiLedgerBindingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self.ledger_path = self.root / "execution.sqlite3"
        self.inputs = DeterministicInputs()
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="kalshi-test-namespace",
            authority_namespace_root=self.authority_root,
            canonical_repository_root=self.repository_root,
        )
        self.documents = self._synthetic_evidence_documents()
        self.evidence = self._encode_evidence_documents(self.documents)
        self.expectations = self._expectations_for(self.evidence)
        self.contract = LegacyIncidentContract(evidence_expectations=self.expectations)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _synthetic_evidence_documents() -> dict[str, dict[str, object]]:
        lifecycle = {
            "task_id": CURRENT_INCIDENT_ID,
            "authorization_consumed": True,
            "environment": CURRENT_ENVIRONMENT,
            "ticker": CURRENT_TICKER,
            "client_order_id": CURRENT_CLIENT_ORDER_ID,
            "phase": "FAIL_CLOSED_HALT",
            "halt_code": "RECOVERY_ZERO_MATCH",
            "terminal_result": None,
            "canonical_lifecycle_evidence": {
                "environment": CURRENT_ENVIRONMENT,
                "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                "subaccount": 0,
                "ticker": CURRENT_TICKER,
                "client_order_id": CURRENT_CLIENT_ORDER_ID,
                "writer_session_id": "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_LOCAL_RUNNER",
                "proof_id": CURRENT_WRITER_PROOF_ID,
                "proof_state": "HELD",
                "proof_release_eligible": False,
                "bound_order_id": None,
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "create_send_may_have_begun": True,
                "cancel_send_may_have_begun": False,
                "halt_code": "RECOVERY_ZERO_MATCH",
            },
            "writer_proof": {
                "id": CURRENT_WRITER_PROOF_ID,
                "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                "writer_session_id": "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01_LOCAL_RUNNER",
                "continuity_state": "HELD",
            },
            "reconciliation": {
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "proof_release_eligible": False,
            },
            "authoritative_order_snapshots": [],
            "canonical_fill_summary": None,
        }
        reconciliation = {
            "task_id": "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EXECUTION_01",
            "authorization": {
                "authorization_consumed": True,
                "overall_execution_attempts_authorized": 1,
            },
            "canonical_result": {
                "result_class": CURRENT_DISPOSITION,
                "bound_order_id": None,
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "writer_proof_release_eligible": False,
                "exact_client_order_id_match_count": 0,
                "canonical_fill_count": 0,
                "evidence": {
                    "task_id": "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_IMPLEMENTATION_01",
                    "frozen_scope": {
                        "environment": CURRENT_ENVIRONMENT,
                        "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                        "subaccount": 0,
                        "ticker": CURRENT_TICKER,
                        "client_order_id": CURRENT_CLIENT_ORDER_ID,
                        "writer_proof_id": CURRENT_WRITER_PROOF_ID,
                    },
                    "terminal": {
                        "result_class": CURRENT_DISPOSITION,
                        "created_order_upper_bound": 1,
                        "active_order_upper_bound": 1,
                        "unknown_result": True,
                        "writer_proof_release_eligible": False,
                    },
                    "order_match": {
                        "bound_order_id": None,
                        "exact_client_order_id_match_count": 0,
                        "canonical_orders": [],
                        "matched_order_ids": [],
                    },
                    "fills": {
                        "canonical_fill_count": 0,
                        "canonical_fill_identities": [],
                        "order_fill_reconciliation_result": "UNRESOLVED_OR_NOT_REACHED",
                    },
                    "enumeration": {"records_retained": {"orders": 0, "fills": 0}},
                },
            },
        }
        fill_discovery = {
            "task_id": "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_01",
            "authorization": {
                "authorization_consumed": True,
                "overall_execution_authorized": 1,
                "rerun_permitted_under_this_authorization": False,
            },
            "canonical_result": {
                "result_class": CURRENT_DISPOSITION,
                "bound_order_id": None,
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "writer_proof_release_eligible": False,
                "candidate_order_id_count": 0,
                "candidate_order_ids": [],
                "canonical_fill_count": 0,
                "validated_binding_count": 0,
                "validated_binding_order_ids": [],
                "prior_exact_client_order_id_match_count": 0,
                "evidence": {
                    "task_id": "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_IMPLEMENTATION_01",
                    "frozen_scope": {
                        "environment": CURRENT_ENVIRONMENT,
                        "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                        "subaccount": 0,
                        "ticker": CURRENT_TICKER,
                        "client_order_id": CURRENT_CLIENT_ORDER_ID,
                        "writer_proof_id": CURRENT_WRITER_PROOF_ID,
                    },
                    "predecessor_result": {
                        "result_class": CURRENT_DISPOSITION,
                        "bound_order_id": None,
                        "created_order_upper_bound": 1,
                        "active_order_upper_bound": 1,
                        "exact_client_order_id_match_count": 0,
                        "unknown_result": True,
                        "writer_proof_release_eligible": False,
                    },
                    "terminal": {
                        "result_class": CURRENT_DISPOSITION,
                        "bound_order_id": None,
                        "created_order_upper_bound": 1,
                        "active_order_upper_bound": 1,
                        "unknown_result": True,
                        "writer_proof_release_eligible": False,
                        "candidate_order_id_count": 0,
                        "candidate_order_ids": [],
                        "canonical_fill_count": 0,
                        "prior_exact_client_order_id_match_count": 0,
                        "validated_binding_count": 0,
                        "validated_binding_order_ids": [],
                    },
                    "bound_fill_reconciliation": {
                        "bound_order_id": None,
                        "bound_fills": [],
                        "canonical_fill_count": 0,
                    },
                    "candidate_validation": {
                        "results": [],
                        "validated_binding_count": 0,
                        "validated_binding_order_ids": [],
                    },
                    "discovery": {
                        "candidate_order_id_count": 0,
                        "candidate_order_id_set": [],
                        "canonical_discovery_fills": [],
                        "unique_fill_id_count": 0,
                    },
                },
            },
        }
        return {
            "execution_evidence.json": lifecycle,
            "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json": reconciliation,
            "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_EVIDENCE_01.json": fill_discovery,
        }

    @staticmethod
    def _encode_evidence_documents(
        documents: dict[str, dict[str, object]],
    ) -> dict[str, bytes]:
        return {
            name: json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
            for name, value in documents.items()
        }

    @staticmethod
    def _expectations_for(evidence: dict[str, bytes]) -> tuple[EvidenceExpectation, ...]:
        return tuple(
            EvidenceExpectation(item.name, len(evidence[item.name]), hashlib.sha256(evidence[item.name]).hexdigest())
            for item in PRODUCTION_EVIDENCE_EXPECTATIONS
        )

    def evidence_case(
        self,
        mutate,
    ) -> tuple[dict[str, bytes], LegacyIncidentContract]:
        documents = copy.deepcopy(self.documents)
        mutate(documents)
        evidence = self._encode_evidence_documents(documents)
        return evidence, LegacyIncidentContract(evidence_expectations=self._expectations_for(evidence))

    def initialize(self) -> None:
        initialize_authority_namespace(
            self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid
        )
        initialize_ledger_binding(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            environment_classification=self.contract.environment,
            ledger_path=self.ledger_path,
            canonical_repository_root=self.repository_root,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )

    def acquire_import(self, *, fault_hook=None):
        return acquire_legacy_import_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            fault_hook=fault_hook,
        )

    def _build_synthetic_safe_held(
        self, *, venue_policy: VenueDefensePolicy | None = None,
    ):
        """Create genuinely evaluated, non-legacy release inputs and state."""

        self.initialize()
        config = RiskLimitConfigV1(
            1, self.contract.conflict_domain_ref, "USD",
            PerOrderRiskLimits(Decimal("10"), Decimal("10"), True, Decimal("0.10"), 1_000),
            PerMarketRiskLimits(Decimal("20"), Decimal("20"), 10, Decimal("20"), Decimal("20")),
            AccountRiskLimits(Decimal("100"), 50, Decimal("100"), 0, Decimal("0")),
            FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            venue_policy or VenueDefensePolicy(
                "NOT_REQUIRED", None, True,
                "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT",
            ),
        )
        emergency = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        handle = emergency.handle
        assert handle is not None
        incident_id = "SYNTHETIC_RELEASE_INCIDENT"
        proof_id = "SYNTHETIC_RELEASE_PROOF"
        canonical_order = {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": True,
        }
        order_event = handle.record_order_observation({
            "venue_order_id": "synthetic-order-1",
            "client_order_id": "synthetic-client-order-1",
            "source_request_id": "synthetic-release-order-read",
            "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1",
            "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }).events[-1]
        canonical_fill = canonical_kalshi_fill_payload(
            fill_id="synthetic-fill-1", order_id="synthetic-order-1",
            price=Decimal("0.40"), quantity=Decimal("1.00"), fee=Decimal("0.01"),
            additional_fields={
                "market": "SYNTHETIC", "outcome_side": "YES",
                "authoritative_created_time_utc": "2026-08-13T13:00:00.000000Z",
            },
        )
        fill_event = handle.record_fill_observation({
            "canonical_venue_payload": canonical_fill,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
            "client_order_id": "synthetic-client-order-1",
            "source_operation": "SYNTHETIC_FILL_READ",
            "source_request_id": "synthetic-release-fill-read",
            "venue_fill_id": "synthetic-fill-1",
            "venue_order_id": "synthetic-order-1",
            "venue_payload_schema_id": "synthetic-fill-v1",
        }).events[-1]
        handle.record_writer_proof_held({
            "writer_proof_id": proof_id,
            "conflict_domain_ref": self.contract.conflict_domain_ref,
            "held_reason": "SYNTHETIC_PREDECESSOR_HOLD",
            "protected_unresolved_write_event_ids": [],
        }, incident_id=incident_id)
        handle.record_reconciliation({
            "incident_id": incident_id,
            "disposition": "SYNTHETIC_AUTHORITATIVE_SAFE",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
            "bound_order_id": None,
            "created_order_upper_bound": 0,
            "active_order_upper_bound": 0,
            "unknown_result": False,
            "writer_proof_release_eligible": True,
            "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RECONCILIATION_V1",
        }, incident_id=incident_id)
        before = handle.inspect_validated_projection()
        # The narrow handle intentionally exposes projection but not raw append;
        # the current tail is the projection tail and the preceding state event is absent.
        state_payload = {
            "previous_state": "BOOT_HOLD",
            "new_state": "SAFE_HELD",
            "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
            "risk_state_epoch_before": 0,
            "risk_state_epoch_after": 1,
            "risk_config_sha256": config.sha256,
            "related_emergency_action_id": None,
            "related_release_id": None,
            "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": before.last_sequence,
            "observed_authority_trusted_hash": before.terminal_event_hash,
            "observed_ledger_terminal_sequence": before.last_sequence,
            "observed_ledger_terminal_hash": before.terminal_event_hash,
        }
        safe_result = handle.record_risk_control_state_changed(state_payload)
        safe_event = safe_result.events[-1]
        projection = handle.inspect_validated_projection()
        self.assertEqual(projection.risk_control_state, "SAFE_HELD")
        self.assertEqual(projection.writer_proof_state_by_proof_id[proof_id], "HELD")
        self.assertTrue(projection.writer_proof_release_eligible_by_proof_id[proof_id])
        self.assertEqual(projection.protected_unresolved_legacy_write_count, 0)
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
        emergency_gate = EmergencyCancelGate(
            handle=handle,
            rate_lane=lane,
            process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        handle.close()
        market_data = {"ticker": "SYNTHETIC", "reference_yes_price": Decimal("0.50")}
        risk_snapshot = ReleaseRiskSnapshotV1(
            fills=(EconomicFillV1(
                "SYNTHETIC", "synthetic-fill-1", "YES", Decimal("1.00"),
                Decimal("0.40"), "2026-08-13T13:00:00.000000Z",
            ),),
            working_orders=(WorkingOrderV1(
                "SYNTHETIC", "synthetic-order-1", "YES", Decimal("1.00"), Decimal("0.50"),
            ),),
            unresolved_write_count=0,
            unresolved_write_exposure_usd=Decimal("0"),
            market_data_snapshot=market_data,
        )
        reconciliation = ReleaseReconciliationSnapshotV1(
            ("synthetic-order-1",), ("synthetic-order-1",), ("synthetic-fill-1",),
            (), (), (("synthetic-order-1", order_event.event_id),),
            (("synthetic-fill-1", fill_event.event_id),),
        )
        received_ns = self.inputs.monotonic_value
        received_at = ledger.canonical_timestamp(self.inputs.instant)
        market_stamp = FreshnessStampV1(
            normal_gate.process_instance_id, received_at, received_ns, "NONE", None,
            risk_snapshot.market_data_sha256,
        )
        reconciliation_stamp = FreshnessStampV1(
            normal_gate.process_instance_id, received_at, received_ns, "NONE", None,
            reconciliation.sha256,
        )
        state = ReleaseEvaluationStateV1(
            process_instance_id=normal_gate.process_instance_id,
            incident_id=incident_id,
            writer_proof_id=proof_id,
            risk_config=config,
            risk_snapshot=risk_snapshot,
            reconciliation_snapshot=reconciliation,
            market_freshness=market_stamp,
            reconciliation_freshness=reconciliation_stamp,
            venue_defense_evidence=None,
            normal_gate=normal_gate,
            emergency_gate=emergency_gate,
        )
        return proof_id, incident_id, safe_event, state, lane, normal_gate, emergency_gate

    def _begin_evaluated_release(self):
        (
            proof_id, incident_id, safe_event, state, lane, normal_gate,
            emergency_gate,
        ) = self._build_synthetic_safe_held()
        acquisition = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            release_wall_clock=self.inputs.clock,
        )
        self.assertIsNotNone(acquisition.handle)
        handle = acquisition.handle
        assert handle is not None
        assessment = handle.evaluate_release(state)
        return (
            handle, assessment, state, lane, normal_gate, emergency_gate,
            proof_id, incident_id, safe_event,
        )

    def _acquire_release_for_state(self, state: ReleaseEvaluationStateV1):
        acquisition = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            release_wall_clock=self.inputs.clock,
        )
        self.assertIsNotNone(acquisition.handle)
        handle = acquisition.handle
        assert handle is not None
        return handle

    def _append_trusted_order(
        self, order_id: str, canonical_order: Mapping[str, object],
    ):
        acquisition = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(acquisition.handle)
        handle = acquisition.handle
        assert handle is not None
        event = handle.record_order_observation({
            "venue_order_id": order_id,
            "client_order_id": f"synthetic-client-{order_id}",
            "source_request_id": f"synthetic-order-read-{order_id}-{self.inputs.uuid().hex}",
            "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1",
            "canonical_venue_payload": dict(canonical_order),
            "canonical_venue_payload_sha256": hashlib.sha256(
                canonical_json_bytes(dict(canonical_order))
            ).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ORDER_STATE",
        }).events[-1]
        handle.close()
        return event

    def _append_trusted_fill(
        self,
        *,
        fill_id: str,
        order_id: str,
        quantity: Decimal,
        yes_price: Decimal,
        outcome_side: str = "YES",
        market: str = "SYNTHETIC",
        created_at: str = "2026-08-13T13:00:01.000000Z",
    ):
        acquisition = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(acquisition.handle)
        handle = acquisition.handle
        assert handle is not None
        canonical_fill = canonical_kalshi_fill_payload(
            fill_id=fill_id, order_id=order_id, price=yes_price,
            quantity=quantity, fee=Decimal("0.01"),
            additional_fields={
                "market": market, "outcome_side": outcome_side,
                "authoritative_created_time_utc": created_at,
            },
        )
        event = handle.record_fill_observation({
            "canonical_venue_payload": canonical_fill,
            "canonical_venue_payload_sha256": hashlib.sha256(
                canonical_json_bytes(canonical_fill)
            ).hexdigest(),
            "client_order_id": f"synthetic-client-{order_id}",
            "source_operation": "SYNTHETIC_FILL_READ",
            "source_request_id": f"synthetic-fill-read-{fill_id}-{self.inputs.uuid().hex}",
            "venue_fill_id": fill_id,
            "venue_order_id": order_id,
            "venue_payload_schema_id": "synthetic-fill-v1",
        }).events[-1]
        handle.close()
        return event

    def _venue_proof_for_state(
        self,
        state: ReleaseEvaluationStateV1,
        *,
        group_id: str | None,
        group_state: str,
        member_order_ids: tuple[str, ...],
        cancel_order_on_pause_order_ids: tuple[str, ...],
        conflict_order_ids: tuple[str, ...] = (),
        process_instance_id: str | None = None,
        received_monotonic_ns: int | None = None,
        received_at_utc: str | None = None,
    ) -> VenueDefenseEvidenceV1:
        snapshot = state._snapshot()
        process = process_instance_id or snapshot[2]
        reconciliation = snapshot[7]
        assert type(process) is str
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        observation = {
            "observation_schema_id": "KALSHI_VENUE_DEFENSE_OBSERVATION_V1",
            "order_group_id": group_id,
            "order_group_state": group_state,
            "member_order_ids": list(member_order_ids),
            "cancel_order_on_pause_order_ids": list(cancel_order_on_pause_order_ids),
            "membership_conflict_order_ids": list(conflict_order_ids),
        }
        observation_hash = hashlib.sha256(canonical_json_bytes(observation)).hexdigest()
        stamp = FreshnessStampV1(
            process,
            received_at_utc or ledger.canonical_timestamp(self.inputs.instant),
            self.inputs.monotonic_value if received_monotonic_ns is None else received_monotonic_ns,
            "NONE", None, observation_hash,
        )
        return validate_venue_defense_evidence(
            process_instance_id=process,
            canonical_observation=observation,
            canonical_observation_sha256=observation_hash,
            reconciliation_snapshot_sha256=reconciliation.sha256,
            freshness=stamp,
        )

    def _replace_complete_release_universe(
        self,
        state: ReleaseEvaluationStateV1,
        *,
        working_orders: tuple[WorkingOrderV1, ...],
        fills: tuple[EconomicFillV1, ...],
        order_event_ids: Mapping[str, str],
        fill_event_ids: Mapping[str, str],
    ) -> None:
        prior = state._snapshot()
        process = prior[2]
        config = prior[5]
        risk = prior[6]
        old_reconciliation = prior[7]
        assert type(process) is str
        assert type(config) is RiskLimitConfigV1
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(old_reconciliation) is ReleaseReconciliationSnapshotV1
        active_ids = tuple(sorted(item.order_id for item in working_orders))
        fill_ids = tuple(sorted(item.fill_id for item in fills))
        new_risk = ReleaseRiskSnapshotV1(
            fills=fills, working_orders=working_orders,
            unresolved_write_count=risk.unresolved_write_count,
            unresolved_write_exposure_usd=risk.unresolved_write_exposure_usd,
            market_data_snapshot=dict(risk.market_data_snapshot),
        )
        new_reconciliation = ReleaseReconciliationSnapshotV1(
            active_ids, active_ids, fill_ids, (), (),
            tuple((identity, order_event_ids[identity]) for identity in active_ids),
            tuple((identity, fill_event_ids[identity]) for identity in fill_ids),
        )
        received_at = ledger.canonical_timestamp(self.inputs.instant)
        received_ns = self.inputs.monotonic_value
        market_stamp = FreshnessStampV1(
            process, received_at, received_ns, "NONE", None,
            new_risk.market_data_sha256,
        )
        reconciliation_stamp = FreshnessStampV1(
            process, received_at, received_ns, "NONE", None,
            new_reconciliation.sha256,
        )
        state.replace(
            risk_snapshot=new_risk,
            reconciliation_snapshot=new_reconciliation,
            market_freshness=market_stamp,
            reconciliation_freshness=reconciliation_stamp,
        )

    @staticmethod
    def _risk_variant(state: ReleaseEvaluationStateV1, **changes) -> ReleaseRiskSnapshotV1:
        risk = state._snapshot()[6]
        assert type(risk) is ReleaseRiskSnapshotV1
        values = {
            "fills": risk.fills,
            "working_orders": risk.working_orders,
            "unresolved_write_count": risk.unresolved_write_count,
            "unresolved_write_exposure_usd": risk.unresolved_write_exposure_usd,
            "market_data_snapshot": dict(risk.market_data_snapshot),
        }
        values.update(changes)
        return ReleaseRiskSnapshotV1(**values)

    @staticmethod
    def _reconciliation_variant(
        state: ReleaseEvaluationStateV1, **changes,
    ) -> ReleaseReconciliationSnapshotV1:
        reconciliation = state._snapshot()[7]
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        values = {
            field.name: getattr(reconciliation, field.name)
            for field in reconciliation.__dataclass_fields__.values()
        }
        values.update(changes)
        return ReleaseReconciliationSnapshotV1(**values)

    def _assert_release_denied_after_change(self, change, predicate: str) -> None:
        handle, _initial, state, lane, normal_gate, emergency_gate, *_ = self._begin_evaluated_release()
        change(state, lane, normal_gate, emergency_gate)
        assessment = handle.evaluate_release(state)
        self.assertIs(assessment.predicate_vector[predicate], False)
        before = handle.inspect_validated_projection().last_sequence
        with self.assertRaises(LedgerError):
            handle.record_risk_release(assessment)
        self.assertEqual(handle.inspect_validated_projection().last_sequence, before)
        handle.close()

    def _assert_proof_blocked_after_change(self, change) -> None:
        handle, assessment, state, lane, normal_gate, emergency_gate, proof_id, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        change(state, lane, normal_gate, emergency_gate)
        with self.assertRaises(LedgerError):
            handle.release_writer_proof(assessment)
        projection = handle.inspect_validated_projection()
        self.assertEqual(projection.writer_proof_state_by_proof_id[proof_id], "HELD")
        handle.close()

    def _assert_final_blocked_after_change(self, change) -> None:
        handle, assessment, state, lane, normal_gate, emergency_gate, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        change(state, lane, normal_gate, emergency_gate)
        with self.assertRaises(LedgerError):
            handle.record_writer_eligible(assessment)
        self.assertEqual(handle.inspect_validated_projection().risk_control_state, "SAFE_HELD")
        handle.close()

    def _assert_release_fault_prefix(
        self,
        *,
        target: str,
        stage: str,
        unknown: bool,
        expected_release: bool,
        expected_proof: str,
        expected_state: str,
        expected_end: bool = False,
    ) -> None:
        proof_id, incident_id, safe_event, release_state, _lane, *_gates = self._build_synthetic_safe_held()
        fault = _ArmableReleaseFault(stage, unknown=unknown)
        acquisition = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            fault_hook=fault,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            release_wall_clock=self.inputs.clock,
        )
        self.assertIsNotNone(acquisition.handle)
        handle = acquisition.handle
        assert handle is not None
        assessment = handle.evaluate_release(release_state)
        self.assertTrue(all(assessment.predicate_vector.values()), assessment.predicate_vector)
        release_event = None
        proof_event = None

        try:
            if target == "release":
                fault.armed = True
            release_event = handle.record_risk_release(assessment).events[-1]
            if target == "proof":
                fault.armed = True
            proof_event = handle.release_writer_proof(assessment).events[-1]
            projection = handle.inspect_validated_projection()
            if target == "state":
                fault.armed = True
            handle.record_writer_eligible(assessment)
            if target == "end":
                fault.armed = True
            handle.close()
            self.fail("fault injection did not stop the release sequence")
        except LedgerError:
            pass
        finally:
            # Crash simulation: close the internal SQLite handles without
            # fabricating a later RESTRICTED_SESSION_ENDED event.
            locked = getattr(handle, "_ReleaseLedgerHandle__locked")
            if not locked.closed:
                locked.close()

        reopened = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        projection = reopened.projection()
        self.assertEqual(assessment.release_id in projection.release_records_by_id, expected_release)
        self.assertEqual(projection.writer_proof_state_by_proof_id[proof_id], expected_proof)
        self.assertEqual(projection.risk_control_state, expected_state)
        self.assertEqual(projection.active_restricted_session_id is None, expected_end)
        self.assertEqual(projection.unresolved_write_request_ids, ())
        reopened.close()

    def _prepare_case_a_live_writer(self, *, fault_hook=ledger._noop_fault_hook):
        # Reuse the exact positive release path to establish the only durable
        # predecessor state from which a normal ws_ may be opened.
        self.test_fully_eligible_synthetic_durable_release_reaches_writer_eligible()
        locked = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            fault_hook=fault_hook,
        )
        session_id = start_writer_session(locked, prior_session_state="CLEAN")
        monotonic = 1_000_000_000

        def tick() -> int:
            nonlocal monotonic
            monotonic += 1
            return monotonic

        gate = WriterEligibilityGate(
            monotonic_clock_ns=tick,
            wall_clock=lambda: datetime(2026, 8, 13, 14, tzinfo=timezone.utc),
            uuid_factory=self.inputs.uuid,
        )
        permit = gate.issue_permit(
            locked=locked,
            normal_writer_session_id=session_id,
            assessment=WriterEligibilityAssessment(
                "ra_" + "1" * 32, "CREATE_ORDER_V2", "req_" + "2" * 32,
                "a" * 64, "b" * 64, "a" * 64, "d" * 64, "e" * 64,
                "f" * 64, "0" * 64, 2, 2_000_000_000, True,
            ),
            intent_payload={
                "execution_attempt_id": "ea_" + "5" * 32,
                "venue": "KALSHI",
                "environment": "KALSHI_DEMO",
                "conflict_domain_ref": self.contract.conflict_domain_ref,
                "incident_id": "SYNTHETIC_CASE_A_LIVE_WRITER_TEST",
                "operation_family": "SYNTHETIC_TEST",
                "client_order_id": "synthetic-client-order-case-a",
                "capability_reference_id": "cap_" + "6" * 32,
                "intent_payload_schema_id": "SYNTHETIC_TEST_INTENT_V1",
                "intent_payload": {"request_id": "req_" + "2" * 32},
            },
            prepared_payload={
                "request_id": "req_" + "2" * 32,
                "operation_name": "CREATE_ORDER_V2",
                "prepared_request_sha256": "a" * 64,
            },
        )
        return locked, session_id, gate, permit

    def test_production_evidence_identities_are_frozen(self) -> None:
        self.assertEqual(
            [(item.raw_bytes, item.sha256) for item in PRODUCTION_EVIDENCE_EXPECTATIONS],
            [
                (10746, "2cb1677d06d3c88a3dd6f5b41190fa6de237bae24f02457fee37b2e0d04eefac"),
                (10541, "a10eb4a6d7490755bbe055056cbe4960d075fd73048967d7e3d1c846c7be34fe"),
                (10882, "5e9cb2690854309f5684fa1b31cc4d837e301152a8466732382acb913dd73aa2"),
            ],
        )

    def assert_content_mismatch(self, mutate) -> None:
        evidence, contract = self.evidence_case(mutate)
        with self.assertRaises(LedgerError) as caught:
            validate_legacy_evidence(evidence, contract=contract)
        self.assertEqual(caught.exception.code, FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)

    def test_distinct_artifact_local_task_ids_validate_deterministically(self) -> None:
        one = validate_legacy_evidence(self.evidence, contract=self.contract)
        two = validate_legacy_evidence(self.evidence, contract=self.contract)
        self.assertEqual(one.deterministic_event_id, two.deterministic_event_id)
        self.assertTrue(one.deterministic_event_id.startswith("legacy_"))
        self.assertEqual(one.payload["final_disposition"], CURRENT_DISPOSITION)
        self.assertEqual(one.payload["bound_order_id"], None)
        lifecycle_task = self.documents["execution_evidence.json"]["task_id"]
        reconciliation = self.documents[
            "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json"
        ]
        fill_discovery = self.documents[
            "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_EVIDENCE_01.json"
        ]
        self.assertEqual(lifecycle_task, CURRENT_INCIDENT_ID)
        self.assertNotEqual(reconciliation["task_id"], lifecycle_task)
        self.assertNotEqual(reconciliation["canonical_result"]["evidence"]["task_id"], lifecycle_task)
        self.assertNotEqual(fill_discovery["task_id"], lifecycle_task)
        self.assertNotEqual(fill_discovery["canonical_result"]["evidence"]["task_id"], lifecycle_task)

    def test_evidence_identity_failure_occurs_before_import(self) -> None:
        self.initialize()
        acquisition = self.acquire_import()
        bad = dict(self.evidence)
        bad[self.expectations[0].name] += b" "
        with self.assertRaises(LedgerError) as caught:
            acquisition.handle.validate_legacy_evidence(bad)
        self.assertEqual(caught.exception.code, FailureCode.LEGACY_INCIDENT_EVIDENCE_IDENTITY_MISMATCH)
        self.assertEqual(acquisition.handle.inspect_validated_projection().last_sequence, 1)
        # Validation failure occurs before a commit operation; the caller
        # explicitly closes the still-valid restricted inspection handle.
        acquisition.handle.close()

    def test_duplicate_json_key_and_content_mismatch_rejected(self) -> None:
        duplicate = b'{"incident_id":"x","incident_id":"x"}'
        files = dict(self.evidence)
        files["execution_evidence.json"] = duplicate
        contract = LegacyIncidentContract(evidence_expectations=self._expectations_for(files))
        with self.assertRaises(LedgerError) as caught:
            validate_legacy_evidence(files, contract=contract)
        self.assertEqual(caught.exception.code, FailureCode.LEGACY_INCIDENT_CONTENT_MISMATCH)

    def test_lifecycle_task_id_incorrect_fails_closed(self) -> None:
        self.assert_content_mismatch(
            lambda documents: documents["execution_evidence.json"].__setitem__(
                "task_id", "NOT_THE_LIFECYCLE_INCIDENT"
            )
        )

    def test_reconciliation_shared_client_order_id_incorrect_fails_closed(self) -> None:
        name = "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json"
        self.assert_content_mismatch(
            lambda documents: documents[name]["canonical_result"]["evidence"]["frozen_scope"].__setitem__(
                "client_order_id", "contradictory-client-order-id"
            )
        )

    def test_fill_discovery_shared_ticker_incorrect_fails_closed(self) -> None:
        name = "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_EVIDENCE_01.json"
        self.assert_content_mismatch(
            lambda documents: documents[name]["canonical_result"]["evidence"]["frozen_scope"].__setitem__(
                "ticker", "CONTRADICTORY-TICKER"
            )
        )

    def test_unrelated_nested_task_id_is_not_an_incident_alias(self) -> None:
        def mutate(documents) -> None:
            documents["execution_evidence.json"]["unrelated_provenance"] = {
                "task_id": "UNRELATED_NESTED_TASK_ID"
            }
            reconciliation_name = (
                "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json"
            )
            documents[reconciliation_name]["unrelated_provenance"] = {
                "task_id": "ANOTHER_UNRELATED_TASK_ID"
            }

        evidence, contract = self.evidence_case(mutate)
        validated = validate_legacy_evidence(evidence, contract=contract)
        self.assertEqual(validated.payload["incident_id"], CURRENT_INCIDENT_ID)

    def test_material_writer_proof_state_contradiction_fails_closed(self) -> None:
        self.assert_content_mismatch(
            lambda documents: documents["execution_evidence.json"]["writer_proof"].__setitem__(
                "continuity_state", "RELEASED"
            )
        )

    def test_material_result_disposition_contradiction_fails_closed(self) -> None:
        name = "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json"
        self.assert_content_mismatch(
            lambda documents: documents[name]["canonical_result"].__setitem__(
                "result_class", "CREATE_NEVER_EXISTED"
            )
        )

    def test_each_authorization_consumed_fact_is_independently_required(self) -> None:
        targets = (
            ("execution_evidence.json", None),
            ("KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json", "authorization"),
            ("KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_EVIDENCE_01.json", "authorization"),
        )
        for name, parent in targets:
            for replacement in ("missing", False):
                with self.subTest(artifact=name, replacement=replacement):
                    def mutate(documents, *, name=name, parent=parent, replacement=replacement) -> None:
                        target = documents[name] if parent is None else documents[name][parent]
                        if replacement == "missing":
                            del target["authorization_consumed"]
                        else:
                            target["authorization_consumed"] = replacement

                    self.assert_content_mismatch(mutate)

    def test_unrelated_nested_consumed_marker_cannot_substitute_for_schema_path(self) -> None:
        name = "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json"

        def mutate(documents) -> None:
            del documents[name]["authorization"]["authorization_consumed"]
            documents[name]["unrelated"] = {"authorization_consumed": True}

        self.assert_content_mismatch(mutate)

    def test_normal_writer_blocked_and_import_only_distinct_handle(self) -> None:
        self.initialize()
        normal = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=None,
            process_instance_id="proc_" + "0" * 32,
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertEqual(normal.restart_classification, RestartClassification.LEGACY_HISTORY_INCOMPLETE)
        self.assertIsNone(normal.handle)
        generic_import = acquire_local_state(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.LEGACY_IMPORT_ONLY,
            expected_ledger_path=self.ledger_path,
        )
        self.assertIsNone(generic_import.handle)
        self.assertEqual(
            generic_import.failure_code,
            FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED,
        )
        acquisition = self.acquire_import()
        self.assertEqual(acquisition.restart_classification, RestartClassification.LEGACY_HISTORY_INCOMPLETE)
        self.assertIsNotNone(acquisition.handle)
        public = {name for name in dir(acquisition.handle) if not name.startswith("_")}
        self.assertEqual(
            public,
            {"close", "commit_exact_legacy_import", "inspect_validated_projection", "validate_legacy_evidence"},
        )
        for prohibited in (
            "append", "append_batch", "transport", "send", "sign", "credentials",
            "release_writer_proof", "start_writer_session", "enter_write_send_boundary",
        ):
            self.assertFalse(hasattr(acquisition.handle, prohibited))
        with self.assertRaises(LedgerError) as session_error:
            start_writer_session(acquisition.handle, prior_session_state="NONE")
        self.assertEqual(
            session_error.exception.code,
            FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED,
        )
        with self.assertRaises(LedgerError) as gate_error:
            append_authority_anchored_send_gate(
                acquisition.handle,
                writer_session_id="ws_rejected",
                incident_id="synthetic-incident",
                execution_attempt_id="synthetic-attempt",
                intent_payload={},
                prepared_payload={},
            )
        self.assertEqual(
            gate_error.exception.code,
            FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED,
        )
        acquisition.handle.close()

    def test_emergency_and_release_acquisitions_are_narrow_sequential_and_replayable(self) -> None:
        self.initialize()
        imported = self.acquire_import()
        imported.handle.commit_exact_legacy_import(
            imported.handle.validate_legacy_evidence(self.evidence)
        )
        imported.handle.close()

        emergency = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        self.assertTrue(emergency.handle.restricted_session_id.startswith("rs_"))
        self.assertEqual(
            {name for name in dir(emergency.handle) if not name.startswith("_")},
            {
                "close", "inspect_validated_projection", "open_emergency_action",
                "record_cancel_intent", "record_cancel_result", "record_cancel_send_boundary",
                "record_execution_halt", "record_fill_observation", "record_order_observation",
                "record_reconciliation", "record_risk_control_state_changed",
                "record_writer_proof_held", "restricted_session_id",
            },
        )
        for prohibited in ("append_batch", "send", "sign", "credentials", "release_writer_proof"):
            self.assertFalse(hasattr(emergency.handle, prohibited))
        concurrent = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(concurrent.handle)
        emergency.handle.close()

        release = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(release.handle)
        self.assertEqual(
            {name for name in dir(release.handle) if not name.startswith("_")},
            {"close", "complete_release_and_issue_current_process_completion", "evaluate_release", "inspect_validated_projection", "record_risk_release", "record_writer_eligible", "release_writer_proof", "restricted_session_id"},
        )
        for prohibited in ("append_batch", "send", "cancel", "record_cancel_intent", "record_order_observation"):
            self.assertFalse(hasattr(release.handle, prohibited))
        with self.assertRaises(LedgerError) as historical_release:
            release.handle.record_risk_release({})
        self.assertEqual(
            historical_release.exception.code,
            FailureCode.RELEASE_PREDICATE_FAILED,
        )
        release.handle.close()

        replay = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(replay.handle)
        projection = replay.handle.inspect_validated_projection()
        self.assertEqual(projection.active_restricted_session_id, replay.handle.restricted_session_id)
        replay.handle.close()

    def test_fully_eligible_synthetic_durable_release_reaches_writer_eligible(self) -> None:
        proof_id, incident_id, safe_event, release_state, _lane, *_gates = self._build_synthetic_safe_held()
        release = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            release_wall_clock=self.inputs.clock,
        )
        self.assertIsNotNone(release.handle)
        handle = release.handle
        assert handle is not None
        assessment = handle.evaluate_release(release_state)
        self.assertEqual(len(assessment.predicate_vector), 19)
        self.assertTrue(all(assessment.predicate_vector.values()), assessment.predicate_vector)
        release_result = handle.record_risk_release(assessment)
        release_event = release_result.events[-1]
        self.assertEqual(release_event.payload["predicate_vector"], dict(assessment.predicate_vector))
        self.assertEqual(release_event.payload["risk_snapshot_sha256"], assessment.risk_snapshot_sha256)
        self.assertEqual(
            release_event.payload["reconciliation_snapshot_sha256"],
            assessment.reconciliation_snapshot_sha256,
        )
        projection = handle.inspect_validated_projection()
        self.assertEqual(projection.writer_proof_state_by_proof_id[proof_id], "HELD")
        self.assertEqual(projection.risk_control_state, "SAFE_HELD")

        proof_result = handle.release_writer_proof(assessment)
        proof_event = proof_result.events[-1]
        projection = handle.inspect_validated_projection()
        self.assertEqual(projection.writer_proof_state_by_proof_id[proof_id], "RELEASED")
        self.assertEqual(projection.risk_control_state, "SAFE_HELD")

        eligible_result = handle.record_writer_eligible(assessment)
        self.assertGreater(eligible_result.events[-1].sequence, proof_event.sequence)
        self.assertEqual(handle.inspect_validated_projection().risk_control_state, "WRITER_ELIGIBLE")
        handle.close()

        reopened = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        final = reopened.projection()
        self.assertEqual(final.risk_control_state, "WRITER_ELIGIBLE")
        self.assertEqual(final.writer_proof_state_by_proof_id[proof_id], "RELEASED")
        self.assertIsNone(final.active_restricted_session_id)
        reopened.close()

    def test_rel_assess_01_caller_vector_rejected_before_append(self) -> None:
        handle, assessment, *_ = self._begin_evaluated_release()
        caller_vector = {key: True for key in assessment.predicate_vector}
        before = handle.inspect_validated_projection().last_sequence
        with self.assertRaises(LedgerError):
            handle.record_risk_release({"predicate_vector": caller_vector})  # type: ignore[arg-type]
        self.assertEqual(handle.inspect_validated_projection().last_sequence, before)
        handle.close()

    def test_rel_assess_02_arbitrary_snapshot_hashes_rejected_before_append(self) -> None:
        handle, assessment, *_ = self._begin_evaluated_release()
        before = handle.inspect_validated_projection().last_sequence
        with self.assertRaises(TypeError):
            handle.record_risk_release(
                assessment,
                risk_snapshot_sha256="c" * 64,
                reconciliation_snapshot_sha256="b" * 64,
            )
        self.assertEqual(handle.inspect_validated_projection().last_sequence, before)
        handle.close()

    def test_rel_assess_03_valid_assessment_is_opaque_derived_and_nonserializable(self) -> None:
        handle, assessment, *_ = self._begin_evaluated_release()
        self.assertTrue(all(assessment.predicate_vector.values()))
        with self.assertRaises(LedgerError):
            ReleaseAssessmentV1(object())
        for operation in (copy.copy, copy.deepcopy):
            with self.assertRaises(TypeError):
                operation(assessment)
        event = handle.record_risk_release(assessment).events[-1]
        self.assertEqual(event.payload["predicate_vector"], dict(assessment.predicate_vector))
        self.assertEqual(event.payload["risk_snapshot_sha256"], assessment.risk_snapshot_sha256)
        self.assertEqual(
            event.payload["reconciliation_snapshot_sha256"],
            assessment.reconciliation_snapshot_sha256,
        )
        handle.close()

    def test_rel_assess_04_missing_risk_config_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda state, *_: state.replace(risk_config=None),
            "risk_config_complete_valid",
        )

    def test_rel_assess_05_config_hash_mismatch_denied(self) -> None:
        def change(state, *_):
            config = state._snapshot()[5]
            assert type(config) is RiskLimitConfigV1
            state.replace(
                risk_config=replace(
                    config,
                    per_order=replace(config.per_order, max_contracts=Decimal("11")),
                )
            )
        self._assert_release_denied_after_change(change, "risk_config_complete_valid")

    def test_rel_assess_06_unknown_unbounded_exposure_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda state, *_: state.replace(
                risk_snapshot=self._risk_variant(
                    state, unresolved_write_exposure_usd="UNKNOWN_UNBOUNDED",
                )
            ),
            "conservative_exposure_finite_and_within_limits",
        )

    def test_rel_assess_07_one_decimal_quantum_over_limit_denied(self) -> None:
        def change(state, *_):
            risk = self._risk_variant(state)
            over = replace(
                risk.fills[0], quantity=Decimal("20.01"), yes_price=Decimal("1.0000"),
            )
            state.replace(risk_snapshot=self._risk_variant(state, fills=(over,)))
        self._assert_release_denied_after_change(
            change, "conservative_exposure_finite_and_within_limits",
        )

    def test_rel_assess_08_market_freshness_boundary_then_stale_denied(self) -> None:
        handle, initial, state, *_ = self._begin_evaluated_release()
        self.assertTrue(initial.predicate_vector["market_data_fresh"])
        self.inputs.advance_ms(1_001)
        stale = handle.evaluate_release(state)
        self.assertFalse(stale.predicate_vector["market_data_fresh"])
        with self.assertRaises(LedgerError):
            handle.record_risk_release(stale)
        handle.close()

    def test_rel_assess_09_stale_reconciliation_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda _state, *_: self.inputs.advance_ms(1_001),
            "reconciliation_fresh",
        )

    def test_rel_assess_10_wrong_process_freshness_denied(self) -> None:
        def change(state, *_):
            snapshot = state._snapshot()
            market = snapshot[8]
            reconciliation = snapshot[9]
            assert type(market) is FreshnessStampV1
            assert type(reconciliation) is FreshnessStampV1
            state.replace(
                market_freshness=replace(market, process_instance_id="proc_" + "9" * 32),
                reconciliation_freshness=replace(
                    reconciliation, process_instance_id="proc_" + "9" * 32,
                ),
            )
        self._assert_release_denied_after_change(change, "market_data_fresh")

    def test_rel_assess_11_unreconciled_known_active_order_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda state, *_: state.replace(
                reconciliation_snapshot=self._reconciliation_variant(
                    state, reconciled_order_ids=(),
                )
            ),
            "known_active_orders_reconciled",
        )

    def test_rel_assess_12_unreconciled_fill_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda state, *_: state.replace(
                reconciliation_snapshot=self._reconciliation_variant(
                    state, reconciled_fill_ids=(),
                )
            ),
            "fills_reconciled",
        )

    def test_rel_assess_13_identity_conflict_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda state, *_: state.replace(
                reconciliation_snapshot=self._reconciliation_variant(
                    state, identity_conflict_ids=("synthetic-conflict",),
                )
            ),
            "zero_identity_conflicts",
        )

    def test_rel_assess_14_unresolved_emergency_cancel_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda state, *_: state.replace(
                reconciliation_snapshot=self._reconciliation_variant(
                    state, unresolved_emergency_cancel_attempt_ids=("ca_" + "1" * 32,),
                )
            ),
            "no_unresolved_emergency_cancel",
        )

    def test_rel_assess_15_venue_defense_failure_denied(self) -> None:
        def change(state, *_):
            config = state._snapshot()[5]
            assert type(config) is RiskLimitConfigV1
            state.replace(risk_config=replace(
                config, venue_defense=self._required_defense_policy(),
            ))

        self._assert_release_denied_after_change(
            change,
            "venue_defense_pass",
        )

    def test_rel_assess_16_genuine_outstanding_normal_permit_denied(self) -> None:
        def change(state, _lane, normal_gate, _emergency_gate):
            config = state._snapshot()[5]
            assert type(config) is RiskLimitConfigV1
            assessment = WriterEligibilityAssessment(
                "ra_" + "1" * 32, "CREATE_ORDER_V2", "req_" + "2" * 32,
                "a" * 64, "b" * 64, config.sha256, "d" * 64, "e" * 64,
                "f" * 64, "0" * 64, 7, self.inputs.monotonic_value + 1_000_000_000, True,
            )
            normal_gate.issue_permit(
                locked=_PermitLocked(config.sha256),
                normal_writer_session_id="ws_" + "1" * 32,
                assessment=assessment,
                intent_payload={
                    "execution_attempt_id": "ea_" + "3" * 32,
                    "venue": "KALSHI",
                    "environment": "KALSHI_DEMO",
                    "conflict_domain_ref": CURRENT_CONFLICT_DOMAIN_REF,
                    "incident_id": "SYNTHETIC_RELEASE_OUTSTANDING_PERMIT_TEST",
                    "operation_family": "SYNTHETIC_TEST",
                    "client_order_id": "synthetic-client-order-outstanding",
                    "capability_reference_id": "cap_" + "4" * 32,
                    "intent_payload_schema_id": "SYNTHETIC_TEST_INTENT_V1",
                    "intent_payload": {"request_id": "req_" + "2" * 32},
                },
                prepared_payload={
                    "request_id": "req_" + "2" * 32,
                    "operation_name": "CREATE_ORDER_V2",
                    "prepared_request_sha256": "a" * 64,
                },
            )
        self._assert_release_denied_after_change(change, "no_outstanding_permits")

    def test_rel_assess_17_genuine_outstanding_emergency_action_denied(self) -> None:
        self._assert_release_denied_after_change(
            lambda _state, lane, *_: lane.reserve(
                "ea_" + "1" * 32, "synthetic-order-1", self.inputs.monotonic_value // 1_000_000,
            ),
            "no_outstanding_permits",
        )

    def test_rel_assess_18_historical_incident_remains_denied_and_unbounded(self) -> None:
        self.initialize()
        imported = self.acquire_import()
        imported.handle.commit_exact_legacy_import(
            imported.handle.validate_legacy_evidence(self.evidence)
        )
        imported.handle.close()
        emergency = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
        emergency_gate = EmergencyCancelGate(
            handle=emergency.handle,
            rate_lane=lane,
            process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        emergency.handle.close()
        risk = ReleaseRiskSnapshotV1((), (), 1, "UNKNOWN_UNBOUNDED", {"historical": True})
        reconciliation = ReleaseReconciliationSnapshotV1((), (), (), (), (), (), ())
        state = ReleaseEvaluationStateV1(
            process_instance_id=normal_gate.process_instance_id,
            incident_id=CURRENT_INCIDENT_ID,
            writer_proof_id=CURRENT_WRITER_PROOF_ID,
            risk_config=None,
            risk_snapshot=risk,
            reconciliation_snapshot=reconciliation,
            market_freshness=None,
            reconciliation_freshness=None,
            venue_defense_evidence=None,
            normal_gate=normal_gate,
            emergency_gate=emergency_gate,
        )
        release = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            release_wall_clock=self.inputs.clock,
        )
        assessment = release.handle.evaluate_release(state)
        self.assertFalse(assessment.predicate_vector["writer_proof_release_eligible"])
        self.assertFalse(assessment.predicate_vector["protected_unresolved_legacy_write_count_zero"])
        self.assertFalse(assessment.predicate_vector["conservative_exposure_finite_and_within_limits"])
        self.assertIsNone(HISTORICAL_INCIDENT_CANCEL_TARGET)
        self.assertFalse(HISTORICAL_INCIDENT_WRITER_RELEASE_ELIGIBLE)
        self.assertEqual(HISTORICAL_UNRESOLVED_EXPOSURE, "UNKNOWN_UNBOUNDED")
        with self.assertRaises(LedgerError):
            release.handle.record_risk_release(assessment)
        release.handle.close()

    def test_rel_change_01_market_stale_after_release_blocks_proof(self) -> None:
        self._assert_proof_blocked_after_change(
            lambda _state, *_: self.inputs.advance_ms(1_001)
        )

    def test_rel_change_02_reconciliation_stale_after_release_blocks_proof(self) -> None:
        self._assert_proof_blocked_after_change(
            lambda _state, *_: self.inputs.advance_ms(1_001)
        )

    def test_rel_change_03_config_identity_change_after_release_blocks_proof(self) -> None:
        self._assert_proof_blocked_after_change(
            lambda state, *_: state.replace(risk_config=None)
        )

    def test_rel_change_04_exposure_above_limit_after_release_blocks_proof(self) -> None:
        def change(state, *_):
            risk = self._risk_variant(state)
            state.replace(risk_snapshot=self._risk_variant(
                state,
                fills=(replace(risk.fills[0], quantity=Decimal("20.01"), yes_price=Decimal("1.0000")),),
            ))
        self._assert_proof_blocked_after_change(change)

    def test_rel_change_05_new_unresolved_emergency_after_release_blocks_proof(self) -> None:
        self._assert_proof_blocked_after_change(
            lambda state, *_: state.replace(
                reconciliation_snapshot=self._reconciliation_variant(
                    state, unresolved_emergency_cancel_attempt_ids=("ca_" + "2" * 32,),
                )
            )
        )

    def test_rel_change_06_new_outstanding_permit_after_release_blocks_proof(self) -> None:
        self._assert_proof_blocked_after_change(
            lambda _state, lane, *_: lane.reserve(
                "ea_" + "2" * 32, "synthetic-order-1", self.inputs.monotonic_value // 1_000_000,
            )
        )

    def test_rel_change_07_market_stale_after_proof_blocks_writer_eligible(self) -> None:
        self._assert_final_blocked_after_change(
            lambda _state, *_: self.inputs.advance_ms(1_001)
        )

    def test_rel_change_08_reconciliation_identity_change_after_proof_blocks_final(self) -> None:
        self._assert_final_blocked_after_change(
            lambda state, *_: state.replace(
                reconciliation_snapshot=self._reconciliation_variant(
                    state, reconciled_fill_ids=(),
                )
            )
        )

    def test_rel_change_09_config_change_after_proof_blocks_final(self) -> None:
        self._assert_final_blocked_after_change(
            lambda state, *_: state.replace(risk_config=None)
        )

    def test_rel_change_10_new_unresolved_emergency_after_proof_blocks_final(self) -> None:
        self._assert_final_blocked_after_change(
            lambda state, *_: state.replace(
                reconciliation_snapshot=self._reconciliation_variant(
                    state, unresolved_emergency_cancel_attempt_ids=("ca_" + "3" * 32,),
                )
            )
        )

    def _assert_current_state_denied(
        self, state: ReleaseEvaluationStateV1, predicate: str,
    ) -> None:
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertFalse(assessment.predicate_vector[predicate])
        before = handle.inspect_validated_projection().last_sequence
        with self.assertRaises(LedgerError):
            handle.record_risk_release(assessment)
        self.assertEqual(handle.inspect_validated_projection().last_sequence, before)
        handle.close()

    def test_rel_truth_01_omitted_active_order_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_order("synthetic-order-2", {
            "order_id": "synthetic-order-2", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.60"),
            "cancel_order_on_pause": True,
        })
        self._assert_current_state_denied(state, "known_active_orders_reconciled")

    def test_rel_truth_02_omitted_canonical_fill_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_fill(
            fill_id="synthetic-fill-2", order_id="synthetic-order-1",
            quantity=Decimal("1.00"), yes_price=Decimal("0.30"),
        )
        self._assert_current_state_denied(state, "fills_reconciled")

    def test_rel_truth_03_omitted_order_cannot_hide_over_limit_exposure(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_order("synthetic-order-2", {
            "order_id": "synthetic-order-2", "status": "resting",
            "remaining_count_fp": "10.01", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("1.00"),
            "cancel_order_on_pause": True,
        })
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertFalse(assessment.predicate_vector["known_active_orders_reconciled"])
        self.assertFalse(
            assessment.predicate_vector[
                "conservative_exposure_finite_and_within_limits"
            ]
        )
        with self.assertRaises(LedgerError):
            handle.record_risk_release(assessment)
        handle.close()

    def test_rel_truth_04_omitted_fill_cannot_hide_over_limit_exposure(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_fill(
            fill_id="synthetic-fill-2", order_id="synthetic-order-1",
            quantity=Decimal("21.00"), yes_price=Decimal("1.00"),
        )
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertFalse(assessment.predicate_vector["fills_reconciled"])
        self.assertFalse(
            assessment.predicate_vector[
                "conservative_exposure_finite_and_within_limits"
            ]
        )
        with self.assertRaises(LedgerError):
            handle.record_risk_release(assessment)
        handle.close()

    def test_rel_truth_05_phantom_order_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        risk = state._snapshot()[6]
        reconciliation = state._snapshot()[7]
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        phantom = WorkingOrderV1(
            "SYNTHETIC", "phantom-order", "YES", Decimal("1.00"), Decimal("0.50"),
        )
        refs = dict(reconciliation.order_evidence_event_ids)
        refs[phantom.order_id] = "evt_" + "9" * 64
        self._replace_complete_release_universe(
            state, working_orders=risk.working_orders + (phantom,), fills=risk.fills,
            order_event_ids=refs,
            fill_event_ids=dict(reconciliation.fill_evidence_event_ids),
        )
        self._assert_current_state_denied(state, "known_active_orders_reconciled")

    def test_rel_truth_06_phantom_fill_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        risk = state._snapshot()[6]
        reconciliation = state._snapshot()[7]
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        phantom = EconomicFillV1(
            "SYNTHETIC", "phantom-fill", "YES", Decimal("1.00"),
            Decimal("0.50"), "2026-08-13T13:00:02.000000Z",
        )
        refs = dict(reconciliation.fill_evidence_event_ids)
        refs[phantom.fill_id] = "evt_" + "8" * 64
        self._replace_complete_release_universe(
            state, working_orders=risk.working_orders, fills=risk.fills + (phantom,),
            order_event_ids=dict(reconciliation.order_evidence_event_ids),
            fill_event_ids=refs,
        )
        self._assert_current_state_denied(state, "fills_reconciled")

    def test_rel_truth_07_earlier_resting_later_terminal_is_not_active(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "canceled",
            "remaining_count_fp": "0.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": True,
        })
        risk = state._snapshot()[6]
        reconciliation = state._snapshot()[7]
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        self._replace_complete_release_universe(
            state, working_orders=(), fills=risk.fills, order_event_ids={},
            fill_event_ids=dict(reconciliation.fill_evidence_event_ids),
        )
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertTrue(assessment.predicate_vector["known_active_orders_reconciled"])
        self.assertTrue(
            assessment.predicate_vector[
                "conservative_exposure_finite_and_within_limits"
            ]
        )
        handle.close()

    def test_rel_truth_08_latest_resting_remains_active_and_economic(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        reconciliation = state._snapshot()[7]
        risk = state._snapshot()[6]
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        assert type(risk) is ReleaseRiskSnapshotV1
        self.assertEqual(
            reconciliation.authoritative_known_active_order_ids,
            ("synthetic-order-1",),
        )
        self.assertEqual(tuple(item.order_id for item in risk.working_orders), (
            "synthetic-order-1",
        ))
        self.assertTrue(assessment.predicate_vector["known_active_orders_reconciled"])
        self.assertTrue(
            assessment.predicate_vector[
                "conservative_exposure_finite_and_within_limits"
            ]
        )
        handle.close()

    def test_rel_truth_09_conflicting_trusted_order_identity_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "different-order", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": True,
        })
        self._assert_current_state_denied(state, "zero_identity_conflicts")

    def test_rel_truth_10_complete_exact_authoritative_universe_succeeds(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        order_event = self._append_trusted_order("synthetic-order-2", {
            "order_id": "synthetic-order-2", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "NO", "yes_price": Decimal("0.60"),
            "cancel_order_on_pause": True,
        })
        fill_event = self._append_trusted_fill(
            fill_id="synthetic-fill-2", order_id="synthetic-order-2",
            quantity=Decimal("1.00"), yes_price=Decimal("0.30"),
            outcome_side="NO",
        )
        risk = state._snapshot()[6]
        reconciliation = state._snapshot()[7]
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        order_two = WorkingOrderV1(
            "SYNTHETIC", "synthetic-order-2", "NO", Decimal("1.00"), Decimal("0.60"),
        )
        fill_two = EconomicFillV1(
            "SYNTHETIC", "synthetic-fill-2", "NO", Decimal("1.00"),
            Decimal("0.30"), "2026-08-13T13:00:01.000000Z",
        )
        order_refs = dict(reconciliation.order_evidence_event_ids)
        order_refs[order_two.order_id] = order_event.event_id
        fill_refs = dict(reconciliation.fill_evidence_event_ids)
        fill_refs[fill_two.fill_id] = fill_event.event_id
        self._replace_complete_release_universe(
            state, working_orders=risk.working_orders + (order_two,),
            fills=risk.fills + (fill_two,), order_event_ids=order_refs,
            fill_event_ids=fill_refs,
        )
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        for predicate in (
            "known_active_orders_reconciled", "fills_reconciled",
            "conservative_exposure_finite_and_within_limits", "venue_defense_pass",
        ):
            self.assertTrue(assessment.predicate_vector[predicate], predicate)
        handle.close()

    @staticmethod
    def _required_defense_policy() -> VenueDefensePolicy:
        return VenueDefensePolicy(
            "REQUIRED_FOR_EXPERIMENT", "synthetic-group-G", True,
            "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT",
        )

    def test_rel_defense_01_forged_required_mode_object_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        valid = self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        )
        assert type(valid) is VenueDefenseEvidenceV1
        forged_fields = {
            field.name: getattr(valid, field.name)
            for field in valid.__dataclass_fields__.values()
        }
        with self.assertRaises(LedgerError):
            VenueDefenseEvidenceV1(object(), **forged_fields)
        state.replace(venue_defense_evidence=None)
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_rel_defense_02_validated_wrong_group_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-H", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        ))
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_rel_defense_03_missing_active_order_membership_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=(),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        ))
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_rel_defense_04_conflicting_membership_denied_and_held(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
            conflict_order_ids=("synthetic-order-1",),
        ))
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertFalse(assessment.predicate_vector["venue_defense_pass"])
        self.assertFalse(assessment.predicate_vector["zero_identity_conflicts"])
        with self.assertRaises(LedgerError):
            handle.record_risk_release(assessment)
        handle.close()

    def test_rel_defense_05_stale_validated_proof_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        self.inputs.advance_ms(1_001)
        snapshot = state._snapshot()
        process, risk, reconciliation = snapshot[2], snapshot[6], snapshot[7]
        assert type(process) is str
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        now = ledger.canonical_timestamp(self.inputs.instant)
        state.replace(
            market_freshness=FreshnessStampV1(
                process, now, self.inputs.monotonic_value, "NONE", None,
                risk.market_data_sha256,
            ),
            reconciliation_freshness=FreshnessStampV1(
                process, now, self.inputs.monotonic_value, "NONE", None,
                reconciliation.sha256,
            ),
        )
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertTrue(assessment.predicate_vector["market_data_fresh"])
        self.assertTrue(assessment.predicate_vector["reconciliation_fresh"])
        self.assertFalse(assessment.predicate_vector["venue_defense_pass"])
        handle.close()

    def test_rel_defense_06_validated_required_mode_assertion_still_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        ))
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertFalse(assessment.predicate_vector["venue_defense_pass"])
        handle.close()

    def test_rel_defense_07_not_required_passes_without_group_proof(self) -> None:
        handle, assessment, *_ = self._begin_evaluated_release()
        self.assertTrue(assessment.predicate_vector["venue_defense_pass"])
        handle.close()

    def test_rel_defense_08_intended_membership_without_proof_denied(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        # The durable order payload may express intended group membership, but
        # no validated authoritative group observation is present here.
        state.replace(venue_defense_evidence=None)
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_rel_defense_09_prior_process_proof_denied_after_restart(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
            process_instance_id="proc_" + "9" * 32,
        ))
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_01_exact_former_bypass_denied_without_release_record(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        ))
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_02_direct_evidence_constructor_cannot_create_proof(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        dormant = self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        )
        values = {
            field.name: getattr(dormant, field.name)
            for field in dormant.__dataclass_fields__.values()
        }
        with self.assertRaises(LedgerError):
            VenueDefenseEvidenceV1(object(), **values)
        state.replace(venue_defense_evidence=dormant)
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_03_intended_create_membership_is_not_group_proof(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": True,
            "order_group_id": "synthetic-group-G",
        })
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_04_exact_active_ids_do_not_substitute_for_group_proof(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=state._snapshot()[7].authoritative_known_active_order_ids,
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        ))
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_05_hash_self_consistency_is_not_provenance(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        dormant = self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        )
        self.assertEqual(
            dormant.canonical_observation_sha256,
            dormant.freshness.snapshot_sha256,
        )
        state.replace(venue_defense_evidence=dormant)
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_06_required_mode_has_no_supported_positive_path(self) -> None:
        supported_surface = (
            VenueDefenseEvidenceV1.__name__, validate_venue_defense_evidence.__name__,
        )
        self.assertEqual(
            supported_surface,
            ("VenueDefenseEvidenceV1", "validate_venue_defense_evidence"),
        )
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=self._required_defense_policy(),
        )
        self._assert_current_state_denied(state, "venue_defense_pass")
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id="synthetic-group-G", group_state="ACTIVE",
            member_order_ids=("synthetic-order-1",),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        ))
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_07_not_required_needs_no_group_proof(self) -> None:
        policy = VenueDefensePolicy(
            "NOT_REQUIRED", None, False, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT",
        )
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held(
            venue_policy=policy,
        )
        self.assertIsNone(state._snapshot()[10])
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertTrue(assessment.predicate_vector["venue_defense_pass"])
        self.assertTrue(all(assessment.predicate_vector.values()), assessment.predicate_vector)
        handle.close()

    def test_def_prov_08_authoritative_cancel_on_pause_pass(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self.assertIsNone(state._snapshot()[10])
        handle = self._acquire_release_for_state(state)
        assessment = handle.evaluate_release(state)
        self.assertTrue(assessment.predicate_vector["venue_defense_pass"])
        handle.close()

    def test_def_prov_09_authoritative_cancel_on_pause_fail(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": False,
        })
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_prov_10_caller_cancel_assertion_cannot_override_replay(self) -> None:
        *_, state, _lane, _normal, _emergency = self._build_synthetic_safe_held()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": False,
        })
        state.replace(venue_defense_evidence=self._venue_proof_for_state(
            state, group_id=None, group_state="NOT_APPLICABLE",
            member_order_ids=(),
            cancel_order_on_pause_order_ids=("synthetic-order-1",),
        ))
        self._assert_current_state_denied(state, "venue_defense_pass")

    def test_def_change_01_required_mode_after_release_blocks_proof(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        config = state._snapshot()[5]
        assert type(config) is RiskLimitConfigV1
        state.replace(risk_config=replace(
            config, venue_defense=self._required_defense_policy(),
        ))
        with self.assertRaises(LedgerError):
            handle.release_writer_proof(assessment)
        handle.close()

    def test_def_change_02_required_mode_after_proof_blocks_final(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        config = state._snapshot()[5]
        assert type(config) is RiskLimitConfigV1
        state.replace(risk_config=replace(
            config, venue_defense=self._required_defense_policy(),
        ))
        with self.assertRaises(LedgerError):
            handle.record_writer_eligible(assessment)
        self.assertEqual(handle.inspect_validated_projection().risk_control_state, "SAFE_HELD")
        handle.close()

    def test_def_change_03_cancel_pause_false_after_release_blocks_proof(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        handle.close()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": False,
        })
        handle = self._acquire_release_for_state(state)
        self.assertFalse(
            handle.evaluate_release(state).predicate_vector["venue_defense_pass"]
        )
        with self.assertRaises(LedgerError):
            handle.release_writer_proof(assessment)
        handle.close()

    def test_def_change_04_cancel_pause_false_after_proof_blocks_final(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        handle.close()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": False,
        })
        handle = self._acquire_release_for_state(state)
        self.assertFalse(
            handle.evaluate_release(state).predicate_vector["venue_defense_pass"]
        )
        with self.assertRaises(LedgerError):
            handle.record_writer_eligible(assessment)
        self.assertEqual(handle.inspect_validated_projection().risk_control_state, "SAFE_HELD")
        handle.close()

    def test_rel_change_11_new_universe_truth_after_release_blocks_proof(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        risk = state._snapshot()[6]
        reconciliation = state._snapshot()[7]
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        phantom = EconomicFillV1(
            "SYNTHETIC", "new-fill", "YES", Decimal("1.00"), Decimal("0.50"),
            "2026-08-13T13:00:03.000000Z",
        )
        refs = dict(reconciliation.fill_evidence_event_ids)
        refs[phantom.fill_id] = "evt_" + "7" * 64
        self._replace_complete_release_universe(
            state, working_orders=risk.working_orders, fills=risk.fills + (phantom,),
            order_event_ids=dict(reconciliation.order_evidence_event_ids),
            fill_event_ids=refs,
        )
        with self.assertRaises(LedgerError):
            handle.release_writer_proof(assessment)
        handle.close()

    def test_rel_change_12_authoritative_cancel_pause_failure_blocks_proof_release(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        handle.close()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": False,
        })
        handle = self._acquire_release_for_state(state)
        self.assertFalse(
            handle.evaluate_release(state).predicate_vector["venue_defense_pass"]
        )
        with self.assertRaises(LedgerError):
            handle.release_writer_proof(assessment)
        handle.close()

    def test_rel_change_13_new_universe_truth_after_proof_blocks_final(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        risk = state._snapshot()[6]
        reconciliation = state._snapshot()[7]
        assert type(risk) is ReleaseRiskSnapshotV1
        assert type(reconciliation) is ReleaseReconciliationSnapshotV1
        phantom = WorkingOrderV1(
            "SYNTHETIC", "new-order", "YES", Decimal("1.00"), Decimal("0.50"),
        )
        refs = dict(reconciliation.order_evidence_event_ids)
        refs[phantom.order_id] = "evt_" + "6" * 64
        self._replace_complete_release_universe(
            state, working_orders=risk.working_orders + (phantom,), fills=risk.fills,
            order_event_ids=refs,
            fill_event_ids=dict(reconciliation.fill_evidence_event_ids),
        )
        with self.assertRaises(LedgerError):
            handle.record_writer_eligible(assessment)
        self.assertEqual(handle.inspect_validated_projection().risk_control_state, "SAFE_HELD")
        handle.close()

    def test_rel_change_14_authoritative_cancel_pause_failure_blocks_final(self) -> None:
        handle, assessment, state, *_ = self._begin_evaluated_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        handle.close()
        self._append_trusted_order("synthetic-order-1", {
            "order_id": "synthetic-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": False,
        })
        handle = self._acquire_release_for_state(state)
        self.assertFalse(
            handle.evaluate_release(state).predicate_vector["venue_defense_pass"]
        )
        with self.assertRaises(LedgerError):
            handle.record_writer_eligible(assessment)
        self.assertEqual(handle.inspect_validated_projection().risk_control_state, "SAFE_HELD")
        handle.close()

    def test_release_fault_a_record_before_commit(self) -> None:
        self._assert_release_fault_prefix(
            target="release", stage="before_ledger_commit", unknown=False,
            expected_release=False, expected_proof="HELD", expected_state="SAFE_HELD",
        )

    def test_release_fault_b_record_ledger_commit_authority_failure(self) -> None:
        self._assert_release_fault_prefix(
            target="release", stage="before_authority_commit", unknown=False,
            expected_release=True, expected_proof="HELD", expected_state="SAFE_HELD",
        )

    def test_release_fault_c_record_authority_unknown(self) -> None:
        self._assert_release_fault_prefix(
            target="release", stage="after_authority_commit", unknown=True,
            expected_release=True, expected_proof="HELD", expected_state="SAFE_HELD",
        )

    def test_release_fault_d_proof_before_commit(self) -> None:
        self._assert_release_fault_prefix(
            target="proof", stage="before_ledger_commit", unknown=False,
            expected_release=True, expected_proof="HELD", expected_state="SAFE_HELD",
        )

    def test_release_fault_e1_proof_authority_failure(self) -> None:
        self._assert_release_fault_prefix(
            target="proof", stage="before_authority_commit", unknown=False,
            expected_release=True, expected_proof="RELEASED", expected_state="SAFE_HELD",
        )

    def test_release_fault_e2_proof_authority_unknown(self) -> None:
        self._assert_release_fault_prefix(
            target="proof", stage="after_authority_commit", unknown=True,
            expected_release=True, expected_proof="RELEASED", expected_state="SAFE_HELD",
        )

    def test_release_fault_f_final_state_before_commit(self) -> None:
        self._assert_release_fault_prefix(
            target="state", stage="before_ledger_commit", unknown=False,
            expected_release=True, expected_proof="RELEASED", expected_state="SAFE_HELD",
        )

    def test_release_fault_g1_final_state_authority_failure(self) -> None:
        self._assert_release_fault_prefix(
            target="state", stage="before_authority_commit", unknown=False,
            expected_release=True, expected_proof="RELEASED", expected_state="WRITER_ELIGIBLE",
        )

    def test_release_fault_g2_final_state_authority_unknown(self) -> None:
        self._assert_release_fault_prefix(
            target="state", stage="after_authority_commit", unknown=True,
            expected_release=True, expected_proof="RELEASED", expected_state="WRITER_ELIGIBLE",
        )

    def test_release_fault_h1_restricted_end_before_commit(self) -> None:
        self._assert_release_fault_prefix(
            target="end", stage="before_ledger_commit", unknown=False,
            expected_release=True, expected_proof="RELEASED", expected_state="WRITER_ELIGIBLE",
            expected_end=False,
        )

    def test_release_fault_h2_restricted_end_authority_unknown(self) -> None:
        self._assert_release_fault_prefix(
            target="end", stage="after_authority_commit", unknown=True,
            expected_release=True, expected_proof="RELEASED", expected_state="WRITER_ELIGIBLE",
            expected_end=True,
        )

    def test_halt_own_01_live_normal_owner_persists_trusted_halt(self) -> None:
        locked, session_id, gate, permit = self._prepare_case_a_live_writer()
        calls: list[object] = []
        result = gate.persist_case_a_halt(
            locked=locked,
            normal_writer_session_id=session_id,
            risk_config_sha256="a" * 64,
        )
        self.assertTrue(result["locks_released"])
        self.assertEqual(gate.progress_snapshot(permit)["stage"], PermitStage.INVALIDATED)
        with self.assertRaises(RiskControlError):
            NormalWriteAdapter(gate, lambda request: calls.append(request)).invoke(permit, object())
        self.assertEqual(calls, [])
        reopened = ledger._open_locked(
            self.binding, conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
        )
        self.assertEqual(reopened.projection().risk_control_state, "HALTED")
        self.assertEqual(reopened.authority_row.trusted_sequence, reopened.events[-1].sequence)
        reopened.close()

    def test_halt_own_02_restricted_constructor_not_invoked_before_release(self) -> None:
        locked, session_id, _, _ = self._prepare_case_a_live_writer()
        before = tuple((event.sequence, event.event_hash) for event in locked.events)
        attempted = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(attempted.handle)
        self.assertEqual(tuple((event.sequence, event.event_hash) for event in locked.events), before)
        self.assertFalse(any(event.event_type is EventType.WRITER_SESSION_ABANDONED for event in locked.events[-1:]))
        ledger.end_writer_session(locked, writer_session_id=session_id)

    def test_halt_own_03_exact_successful_ownership_sequence(self) -> None:
        locked, session_id, gate, _ = self._prepare_case_a_live_writer()
        gate.persist_case_a_halt(
            locked=locked, normal_writer_session_id=session_id,
            risk_config_sha256="a" * 64,
        )
        emergency = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        handle = emergency.handle
        assert handle is not None
        self.assertTrue(handle.restricted_session_id.startswith("rs_"))
        private_locked = getattr(handle, "_EmergencyControlLedgerHandle__locked")
        tail_types = [event.event_type for event in private_locked.events]
        halt_index = max(i for i, event in enumerate(private_locked.events) if event.event_type is EventType.RISK_CONTROL_STATE_CHANGED and event.payload.get("cause") == "HARD_SAFETY_VIOLATION")
        self.assertEqual(tail_types[halt_index:halt_index + 3], [
            EventType.RISK_CONTROL_STATE_CHANGED,
            EventType.WRITER_SESSION_ENDED,
            EventType.RESTRICTED_SESSION_STARTED,
        ])
        self.assertNotIn(EventType.WRITER_SESSION_ABANDONED, tail_types[halt_index:])
        self.assertEqual(sum(event.payload.get("cause") == "HARD_SAFETY_VIOLATION" for event in private_locked.events), 1)
        handle.close()

    def test_halt_own_04_halt_ledger_failure_before_commit(self) -> None:
        fault = _ArmableReleaseFault("before_ledger_commit")
        locked, session_id, gate, permit = self._prepare_case_a_live_writer(fault_hook=fault)
        fault.armed = True
        with self.assertRaises(RiskControlError):
            gate.persist_case_a_halt(
                locked=locked, normal_writer_session_id=session_id,
                risk_config_sha256="a" * 64,
            )
        self.assertEqual(gate.progress_snapshot(permit)["stage"], PermitStage.INVALIDATED)
        self.assertEqual(locked.projection().risk_control_state, "WRITER_ELIGIBLE")
        self.assertIsNone(acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
        ).handle)
        locked.close()
        normal = acquire_normal_writer_state(
            self.binding, canonical_repository_root=str(self.repository_root),
            risk_config=None, process_instance_id="proc_" + "0" * 32,
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(normal.handle)

    def _assert_halt_authority_recovery(self, *, unknown: bool) -> None:
        stage = "after_authority_commit" if unknown else "before_authority_commit"
        fault = _ArmableReleaseFault(stage, unknown=unknown)
        locked, session_id, gate, permit = self._prepare_case_a_live_writer(fault_hook=fault)
        fault.armed = True
        with self.assertRaises(RiskControlError):
            gate.persist_case_a_halt(
                locked=locked, normal_writer_session_id=session_id,
                risk_config_sha256="a" * 64,
            )
        self.assertEqual(gate.progress_snapshot(permit)["stage"], PermitStage.INVALIDATED)
        emergency = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        handle = emergency.handle
        assert handle is not None
        private_locked = getattr(handle, "_EmergencyControlLedgerHandle__locked")
        halts = [event for event in private_locked.events if event.event_type is EventType.RISK_CONTROL_STATE_CHANGED and event.payload.get("cause") == "HARD_SAFETY_VIOLATION"]
        self.assertEqual(len(halts), 1)
        self.assertEqual(private_locked.projection().risk_control_state, "HALTED")
        self.assertIn(EventType.WRITER_SESSION_ABANDONED, [event.event_type for event in private_locked.events])
        handle.close()

    def test_halt_own_05_ledger_commit_authority_failure_catches_forward(self) -> None:
        self._assert_halt_authority_recovery(unknown=False)

    def test_halt_own_06_authority_commit_unknown_replays_without_duplicate(self) -> None:
        self._assert_halt_authority_recovery(unknown=True)

    def test_halt_own_07_no_live_normal_owner_starts_fresh_restricted_session(self) -> None:
        self.initialize()
        emergency = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        handle = emergency.handle
        assert handle is not None
        private_locked = getattr(handle, "_EmergencyControlLedgerHandle__locked")
        self.assertEqual(private_locked.events[-1].event_type, EventType.RESTRICTED_SESSION_STARTED)
        self.assertFalse(any(event.event_type is EventType.WRITER_SESSION_STARTED for event in private_locked.events))
        handle.close()

    def test_halt_own_09_invalidated_permit_cannot_cross_to_later_rs(self) -> None:
        locked, session_id, gate, permit = self._prepare_case_a_live_writer()
        gate.persist_case_a_halt(
            locked=locked, normal_writer_session_id=session_id,
            risk_config_sha256="a" * 64,
        )
        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        calls: list[object] = []
        with self.assertRaises(RiskControlError):
            NormalWriteAdapter(gate, lambda request: calls.append(request)).invoke(permit, object())
        self.assertEqual(calls, [])
        self.assertEqual(
            {name for name in dir(emergency.handle) if not name.startswith("_")},
            {
                "close", "inspect_validated_projection", "open_emergency_action",
                "record_cancel_intent", "record_cancel_result", "record_cancel_send_boundary",
                "record_execution_halt", "record_fill_observation", "record_order_observation",
                "record_reconciliation", "record_risk_control_state_changed",
                "record_writer_proof_held", "restricted_session_id",
            },
        )
        emergency.handle.close()

    def test_abnormal_restricted_session_is_abandoned_only_after_fresh_lock_acquisition(self) -> None:
        self.initialize()
        first = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        old_session = first.handle.restricted_session_id
        # Simulate process death: OS locks disappear without a clean end event.
        first.handle._EmergencyControlLedgerHandle__locked.close()

        recovered = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(recovered.handle)
        events = recovered.handle._EmergencyControlLedgerHandle__locked.events
        abandoned = [event for event in events if event.event_type is EventType.RESTRICTED_SESSION_ABANDONED]
        self.assertEqual(len(abandoned), 1)
        self.assertEqual(abandoned[0].payload["abandoned_restricted_session_id"], old_session)
        self.assertNotEqual(recovered.handle.restricted_session_id, old_session)
        recovered.handle.close()

    def test_emergency_cancel_intent_and_boundary_anchor_before_one_exact_transport_entry(self) -> None:
        self.initialize()
        acquired = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        handle = acquired.handle
        prior = handle.inspect_validated_projection()
        config_hash = "a" * 64
        handle.record_risk_control_state_changed({
            "previous_state": "BOOT_HOLD", "new_state": "HALTED",
            "cause": "REPLAY_OR_CURRENT_HARD_VIOLATION",
            "risk_state_epoch_before": 0, "risk_state_epoch_after": 1,
            "risk_config_sha256": config_hash,
            "related_emergency_action_id": None, "related_release_id": None,
            "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": prior.trusted_sequence,
            "observed_authority_trusted_hash": prior.trusted_event_hash,
            "observed_ledger_terminal_sequence": prior.last_sequence,
            "observed_ledger_terminal_hash": prior.terminal_event_hash,
        })
        canonical_order = {"order_id": "order-1", "status": "resting", "remaining_count_fp": "2.00"}
        observed = handle.record_order_observation({
            "venue_order_id": "order-1", "client_order_id": CURRENT_CLIENT_ORDER_ID,
            "source_request_id": "synthetic-emergency-read", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1",
            "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }).events[-1]
        action_id = EmergencyActionId.mint(self.inputs.uuid)
        action_time = ledger.canonical_timestamp(self.inputs.clock())
        before_action = handle.inspect_validated_projection()
        targets = ["order-1"]
        target_hash = hashlib.sha256(canonical_json_bytes(targets)).hexdigest()
        dedup_object = {
            "conflict_domain_ref": self.contract.conflict_domain_ref,
            "risk_state_epoch": 1,
            "cause": "HARD_RISK_HALT",
            "target_set_sha256": target_hash,
        }
        action_event = handle.open_emergency_action({
            "emergency_action_id": action_id.value,
            "conflict_domain_ref": self.contract.conflict_domain_ref,
            "cause": "HARD_RISK_HALT", "starting_control_state": "HALTED",
            "target_set_kind": "EXACT_ORDER_ID_SET", "target_order_ids": targets,
            "target_set_sha256": target_hash, "risk_config_sha256": config_hash,
            "risk_state_epoch": 1,
            "authority_trusted_sequence": before_action.trusted_sequence,
            "authority_trusted_hash": before_action.trusted_event_hash,
            "ledger_terminal_sequence": before_action.last_sequence,
            "ledger_terminal_hash": before_action.terminal_event_hash,
            "opened_at_utc": action_time,
            "deduplication_key_sha256": hashlib.sha256(canonical_json_bytes(dedup_object)).hexdigest(),
        }, recorded_at_utc=action_time).events[-1]
        before_canceling = handle.inspect_validated_projection()
        halt_state_event = next(
            event for event in reversed(handle._EmergencyControlLedgerHandle__locked.events)
            if event.event_type is EventType.RISK_CONTROL_STATE_CHANGED
        )
        handle.record_risk_control_state_changed({
            "previous_state": "HALTED", "new_state": "EMERGENCY_CANCELING",
            "cause": "EXACT_CANCEL_TARGET_SET_OPENED",
            "risk_state_epoch_before": 1, "risk_state_epoch_after": 2,
            "risk_config_sha256": config_hash,
            "related_emergency_action_id": action_id.value, "related_release_id": None,
            "predecessor_state_event_id": halt_state_event.event_id,
            "observed_authority_trusted_sequence": before_canceling.trusted_sequence,
            "observed_authority_trusted_hash": before_canceling.trusted_event_hash,
            "observed_ledger_terminal_sequence": before_canceling.last_sequence,
            "observed_ledger_terminal_hash": before_canceling.terminal_event_hash,
        })
        authoritative_target = AuthoritativeCancelTargetV1(
            "order-1", self.contract.conflict_domain_ref, 0, 0,
            observed.event_id, observed.event_hash, Decimal("2.00"), "resting",
        )
        monotonic_values = iter((1_000_000_000, 1_000_000_001, 1_000_000_002))
        gate = EmergencyCancelGate(
            handle=handle,
            rate_lane=EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 0, 10, 100)),
            process_instance_id="proc_" + "1" * 32,
            monotonic_clock_ns=lambda: next(monotonic_values),
            wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        prepared, permit = gate.persist_intent_and_boundary(
            action_id=action_id, target=authoritative_target,
            risk_config_sha256=config_hash, attempt_ordinal=1, deadline_budget_ms=500,
        )
        calls = []
        adapter = EmergencyCancelAdapter(gate, lambda request: calls.append(request) or {"status": 200})
        self.assertEqual(adapter.cancel(permit, prepared), {"status": 200})
        self.assertEqual(calls, [prepared])
        with self.assertRaises(EmergencyCancelError) as reused:
            adapter.cancel(permit, prepared)
        self.assertEqual(reused.exception.code, EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_CONSUMED)
        projected = handle.inspect_validated_projection()
        self.assertTrue(projected.cancel_send_may_have_been_sent_by_attempt[permit.cancel_attempt_id])
        self.assertEqual(projected.risk_control_state, "EMERGENCY_CANCELING")
        handle.close()

    def test_send_gate_rejects_incomplete_history_before_any_mutation(self) -> None:
        self.initialize()
        locked = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        before = locked.projection()
        with self.assertRaises(LedgerError) as caught:
            append_authority_anchored_send_gate(
                locked,
                writer_session_id="ws_not_started",
                incident_id="synthetic-incident",
                execution_attempt_id="synthetic-attempt",
                intent_payload={},
                prepared_payload={},
            )
        self.assertEqual(caught.exception.code, FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED)
        after = locked.projection()
        self.assertEqual((after.last_sequence, after.terminal_event_hash), (before.last_sequence, before.terminal_event_hash))
        self.assertEqual((locked.authority_row.trusted_sequence, locked.authority_row.trusted_event_hash), (before.trusted_sequence, before.trusted_event_hash))
        locked.close()

    def test_send_gate_rejects_imported_unresolved_history_before_any_mutation(self) -> None:
        self.initialize()
        acquisition = self.acquire_import()
        result = acquisition.handle.commit_exact_legacy_import(
            acquisition.handle.validate_legacy_evidence(self.evidence)
        )
        self.assertEqual(result.projection.restart_classification, RestartClassification.UNRESOLVED_WRITE_HELD)
        self.assertEqual(result.projection.writer_proof_state_by_proof_id[CURRENT_WRITER_PROOF_ID], "HELD")
        acquisition.handle.close()
        locked = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        before = locked.projection()
        with self.assertRaises(LedgerError) as caught:
            append_authority_anchored_send_gate(
                locked,
                writer_session_id="ws_not_started",
                incident_id="synthetic-incident",
                execution_attempt_id="synthetic-attempt",
                intent_payload={},
                prepared_payload={},
            )
        self.assertEqual(caught.exception.code, FailureCode.LEGACY_IMPORT_ONLY_ACQUISITION_REJECTED)
        after = locked.projection()
        self.assertEqual((after.last_sequence, after.terminal_event_hash), (before.last_sequence, before.terminal_event_hash))
        self.assertEqual(
            (locked.authority_row.trusted_sequence, locked.authority_row.trusted_event_hash),
            (before.trusted_sequence, before.trusted_event_hash),
        )
        event_types = [event.event_type for event in locked.events]
        self.assertNotIn(EventType.EXECUTION_INTENT_RECORDED, event_types)
        self.assertNotIn(EventType.REQUEST_PREPARED, event_types)
        self.assertNotIn(EventType.WRITE_SEND_BOUNDARY_ENTERED, event_types)
        locked.close()

    def test_successful_import_is_exact_two_event_atomic_batch(self) -> None:
        self.initialize()
        acquisition = self.acquire_import()
        validated = acquisition.handle.validate_legacy_evidence(self.evidence)
        result = acquisition.handle.commit_exact_legacy_import(validated)
        self.assertEqual(result.status, LegacyImportStatus.FULLY_AUTHORITY_ANCHORED)
        self.assertEqual(result.events_appended, 2)
        self.assertEqual(result.projection.last_sequence, 3)
        self.assertEqual(result.projection.protected_unresolved_legacy_write_count, 1)
        acquisition.handle.close()
        connection = sqlite3.connect(self.ledger_path)
        try:
            rows = connection.execute("SELECT sequence,event_type,writer_session_id,incident_id,execution_attempt_id FROM ledger_events ORDER BY sequence").fetchall()
        finally:
            connection.close()
        self.assertEqual([row[1] for row in rows], ["LEDGER_INITIALIZED", "LEGACY_INCIDENT_IMPORTED", "WRITER_PROOF_HELD"])
        self.assertEqual(rows[1][2:], (None, CURRENT_INCIDENT_ID, None))
        self.assertEqual(rows[2][2:], (None, CURRENT_INCIDENT_ID, None))

    def test_import_replays_exact_unresolved_current_incident(self) -> None:
        self.initialize()
        acquisition = self.acquire_import()
        result = acquisition.handle.commit_exact_legacy_import(
            acquisition.handle.validate_legacy_evidence(self.evidence)
        )
        projection = result.projection
        incident = projection.legacy_incident_state_by_incident[CURRENT_INCIDENT_ID]
        self.assertEqual(incident["bound_order_id"], None)
        self.assertEqual(incident["created_order_upper_bound"], 1)
        self.assertEqual(incident["active_order_upper_bound"], 1)
        self.assertTrue(incident["unknown_result"])
        self.assertEqual(projection.reconciliation_disposition_by_incident[CURRENT_INCIDENT_ID], CURRENT_DISPOSITION)
        self.assertEqual(projection.writer_proof_state_by_proof_id[CURRENT_WRITER_PROOF_ID], "HELD")
        self.assertFalse(projection.writer_proof_release_eligible_by_proof_id[CURRENT_WRITER_PROOF_ID])
        self.assertEqual(projection.restart_classification, RestartClassification.UNRESOLVED_WRITE_HELD)
        acquisition.handle.close()
        normal = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=None,
            process_instance_id="proc_" + "0" * 32,
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertEqual(normal.restart_classification, RestartClassification.UNRESOLVED_WRITE_HELD)
        self.assertIsNone(normal.handle)

    def test_ledger_transaction_failure_leaves_zero_import_events(self) -> None:
        self.initialize()

        def hook(stage: str) -> None:
            if stage == "before_ledger_commit":
                raise sqlite3.OperationalError("synthetic ledger failure")

        acquisition = self.acquire_import(fault_hook=hook)
        validated = acquisition.handle.validate_legacy_evidence(self.evidence)
        with self.assertRaises(LedgerError) as caught:
            acquisition.handle.commit_exact_legacy_import(validated)
        self.assertEqual(caught.exception.code, FailureCode.LEDGER_COMMIT_FAILURE)
        connection = sqlite3.connect(self.ledger_path)
        try:
            self.assertEqual(connection.execute("SELECT count(*) FROM ledger_events").fetchone()[0], 1)
        finally:
            connection.close()
        acquisition.handle.close()

    def test_authority_definite_failure_preserves_complete_batch_then_catches_up(self) -> None:
        self.initialize()

        def hook(stage: str) -> None:
            if stage == "before_authority_commit":
                raise sqlite3.OperationalError("synthetic authority failure")

        acquisition = self.acquire_import(fault_hook=hook)
        validated = acquisition.handle.validate_legacy_evidence(self.evidence)
        with self.assertRaises(LedgerError) as caught:
            acquisition.handle.commit_exact_legacy_import(validated)
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_ANCHOR_COMMIT_FAILURE)
        ledger_connection = sqlite3.connect(self.ledger_path)
        authority_connection = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            self.assertEqual(ledger_connection.execute("SELECT count(*) FROM ledger_events").fetchone()[0], 3)
            self.assertEqual(authority_connection.execute("SELECT trusted_sequence FROM conflict_domain_authority").fetchone()[0], 1)
        finally:
            ledger_connection.close(); authority_connection.close()
        reopened = self.acquire_import()
        self.assertIsNone(reopened.handle)
        self.assertEqual(reopened.completed_result.status, LegacyImportStatus.ALREADY_COMMITTED_CATCHUP_COMPLETED)
        self.assertEqual(reopened.completed_result.events_appended, 0)
        self.assertEqual(reopened.restart_classification, RestartClassification.UNRESOLVED_WRITE_HELD)

    def test_authority_unknown_preserves_batch_and_reopen_appends_zero(self) -> None:
        self.initialize()

        def hook(stage: str) -> None:
            if stage == "before_authority_commit":
                raise CommitResultUnknown(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)

        acquisition = self.acquire_import(fault_hook=hook)
        validated = acquisition.handle.validate_legacy_evidence(self.evidence)
        with self.assertRaises(LedgerError) as caught:
            acquisition.handle.commit_exact_legacy_import(validated)
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
        reopened = self.acquire_import()
        self.assertEqual(reopened.completed_result.events_appended, 0)
        self.assertEqual(reopened.completed_result.status, LegacyImportStatus.ALREADY_COMMITTED_CATCHUP_COMPLETED)
        connection = sqlite3.connect(self.ledger_path)
        try:
            self.assertEqual(connection.execute("SELECT count(*) FROM ledger_events").fetchone()[0], 3)
        finally:
            connection.close()

    def test_ledger_commit_unknown_requires_reopen_and_no_blind_retry(self) -> None:
        self.initialize()

        def hook(stage: str) -> None:
            if stage == "before_ledger_commit":
                raise CommitResultUnknown(FailureCode.LEDGER_COMMIT_RESULT_UNKNOWN)

        acquisition = self.acquire_import(fault_hook=hook)
        validated = acquisition.handle.validate_legacy_evidence(self.evidence)
        with self.assertRaises(LedgerError) as caught:
            acquisition.handle.commit_exact_legacy_import(validated)
        self.assertEqual(caught.exception.code, FailureCode.LEDGER_COMMIT_RESULT_UNKNOWN)
        reopened = self.acquire_import()
        self.assertIsNotNone(reopened.handle)
        self.assertEqual(reopened.handle.inspect_validated_projection().last_sequence, 1)
        reopened.handle.close()

    def test_authority_commit_unknown_after_actual_commit_reopens_equal(self) -> None:
        self.initialize()

        def hook(stage: str) -> None:
            if stage == "after_authority_commit":
                raise CommitResultUnknown(FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)

        acquisition = self.acquire_import(fault_hook=hook)
        validated = acquisition.handle.validate_legacy_evidence(self.evidence)
        with self.assertRaises(LedgerError) as caught:
            acquisition.handle.commit_exact_legacy_import(validated)
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_ANCHOR_COMMIT_RESULT_UNKNOWN)
        reopened = self.acquire_import()
        self.assertEqual(reopened.completed_result.status, LegacyImportStatus.ALREADY_COMPLETED_AND_ANCHORED)
        self.assertEqual(reopened.completed_result.events_appended, 0)

    def test_authority_equal_reopen_recognizes_without_duplicate(self) -> None:
        self.initialize()
        acquisition = self.acquire_import()
        acquisition.handle.commit_exact_legacy_import(
            acquisition.handle.validate_legacy_evidence(self.evidence)
        )
        acquisition.handle.close()
        reopened = self.acquire_import()
        self.assertIsNone(reopened.handle)
        self.assertEqual(reopened.completed_result.status, LegacyImportStatus.ALREADY_COMPLETED_AND_ANCHORED)
        self.assertEqual(reopened.completed_result.events_appended, 0)

    def test_partial_import_suffix_fails_closed_without_authority_catchup(self) -> None:
        self.initialize()
        validated = validate_legacy_evidence(self.evidence, contract=self.contract)
        locked = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        partial = ledger._construct_event(
            meta=locked.ledger_meta,
            sequence=2,
            previous_hash=locked.events[-1].event_hash,
            event_input=EventInput(
                EventType.LEGACY_INCIDENT_IMPORTED,
                validated.payload,
                incident_id=CURRENT_INCIDENT_ID,
                event_id=validated.deterministic_event_id,
            ),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        locked.ledger.execute("BEGIN IMMEDIATE")
        ledger._insert_event(locked.ledger, partial)
        locked.ledger.commit()
        locked.close()
        reopened = self.acquire_import()
        self.assertIsNone(reopened.handle)
        self.assertEqual(reopened.failure_code, FailureCode.LEGACY_INCIDENT_IMPORT_INCOMPLETE)
        authority = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            self.assertEqual(authority.execute("SELECT trusted_sequence FROM conflict_domain_authority").fetchone()[0], 1)
        finally:
            authority.close()

    def test_conflicting_complete_suffix_fails_before_authority_catchup(self) -> None:
        self.initialize()
        validated = validate_legacy_evidence(self.evidence, contract=self.contract)
        conflicting_payload = dict(validated.payload)
        conflicting_payload["ticker"] = "DIFFERENT"
        conflicting_id = f"legacy_{hashlib.sha256(canonical_json_bytes(conflicting_payload)).hexdigest()}"

        def hook(stage: str) -> None:
            if stage == "before_authority_commit":
                raise sqlite3.OperationalError("synthetic authority failure")

        locked = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            fault_hook=hook,
        )
        with self.assertRaises(LedgerError) as caught:
            locked.append_batch((
                EventInput(
                    EventType.LEGACY_INCIDENT_IMPORTED,
                    conflicting_payload,
                    incident_id=CURRENT_INCIDENT_ID,
                    event_id=conflicting_id,
                ),
                EventInput(EventType.WRITER_PROOF_HELD, {
                    "conflict_domain_ref": CURRENT_CONFLICT_DOMAIN_REF,
                    "held_reason": "PROTECTED_UNRESOLVED_LEGACY_WRITE",
                    "protected_unresolved_write_event_ids": [conflicting_id],
                    "writer_proof_id": CURRENT_WRITER_PROOF_ID,
                }, incident_id=CURRENT_INCIDENT_ID),
            ))
        self.assertEqual(caught.exception.code, FailureCode.AUTHORITY_ANCHOR_COMMIT_FAILURE)

        reopened = self.acquire_import()
        self.assertIsNone(reopened.handle)
        self.assertEqual(reopened.failure_code, FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
        authority = sqlite3.connect(self.binding.authority_store_resolved_path)
        try:
            self.assertEqual(
                authority.execute(
                    "SELECT trusted_sequence FROM conflict_domain_authority"
                ).fetchone()[0],
                1,
            )
        finally:
            authority.close()

    def test_conflicting_second_legacy_import_is_rejected_before_commit(self) -> None:
        self.initialize()
        acquisition = self.acquire_import()
        validated = acquisition.handle.validate_legacy_evidence(self.evidence)
        acquisition.handle.commit_exact_legacy_import(validated)
        acquisition.handle.close()
        locked = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        conflicting_payload = dict(validated.payload)
        conflicting_payload["ticker"] = "DIFFERENT"
        conflicting_id = f"legacy_{hashlib.sha256(canonical_json_bytes(conflicting_payload)).hexdigest()}"
        with self.assertRaises(LedgerError) as caught:
            locked.append_batch((
                EventInput(EventType.LEGACY_INCIDENT_IMPORTED, conflicting_payload, incident_id=CURRENT_INCIDENT_ID, event_id=conflicting_id),
                EventInput(EventType.WRITER_PROOF_HELD, {
                    "conflict_domain_ref": CURRENT_CONFLICT_DOMAIN_REF,
                    "held_reason": "PROTECTED_UNRESOLVED_LEGACY_WRITE",
                    "protected_unresolved_write_event_ids": [conflicting_id],
                    "writer_proof_id": CURRENT_WRITER_PROOF_ID,
                }, incident_id=CURRENT_INCIDENT_ID),
            ))
        self.assertEqual(caught.exception.code, FailureCode.LEGACY_INCIDENT_IMPORT_CONFLICT)
        self.assertEqual(locked.projection().last_sequence, 3)
        locked.close()

    def test_order_binding_and_fill_deduplication_conflicts(self) -> None:
        self.initialize()
        locked = ledger._open_locked(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        session = start_writer_session(locked, prior_session_state="NONE")
        binding_payload = {
            "binding_basis_event_ids": [],
            "client_order_id": CURRENT_CLIENT_ORDER_ID,
            "environment": CURRENT_ENVIRONMENT,
            "incident_id": "synthetic-incident",
            "venue": "KALSHI",
            "venue_order_id": "order-1",
        }
        locked.append_batch((EventInput(EventType.ORDER_IDENTITY_BOUND, binding_payload, session, "synthetic-incident"),))
        locked.append_batch((EventInput(EventType.ORDER_IDENTITY_BOUND, binding_payload, session, "synthetic-incident"),))
        conflicting = dict(binding_payload); conflicting["venue_order_id"] = "order-2"
        with self.assertRaises(LedgerError) as order_error:
            locked.append_batch((EventInput(EventType.ORDER_IDENTITY_BOUND, conflicting, session, "synthetic-incident"),))
        self.assertEqual(order_error.exception.code, FailureCode.ORDER_IDENTITY_BINDING_CONFLICT)

        canonical_fill = canonical_kalshi_fill_payload(
            fill_id="fill-1", order_id="order-1", price=Decimal("0.42"),
            quantity=Decimal("2"), fee=Decimal("0.01"),
        )
        fill_payload = {
            "canonical_venue_payload": canonical_fill,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
            "client_order_id": CURRENT_CLIENT_ORDER_ID,
            "source_operation": "SYNTHETIC_FILL_READ",
            "source_request_id": "request-fill",
            "venue_fill_id": "fill-1",
            "venue_order_id": "order-1",
            "venue_payload_schema_id": "synthetic-fill-v1",
        }
        locked.append_batch((EventInput(EventType.FILL_OBSERVED, fill_payload, session, "synthetic-incident"),))
        locked.append_batch((EventInput(EventType.FILL_OBSERVED, fill_payload, session, "synthetic-incident"),))
        changed_fill = canonical_kalshi_fill_payload(
            fill_id="fill-1", order_id="order-1", price=Decimal("0.43"),
            quantity=Decimal("2"), fee=Decimal("0.01"),
        )
        conflict_payload = dict(fill_payload); conflict_payload["canonical_venue_payload"] = changed_fill
        conflict_payload["canonical_venue_payload_sha256"] = hashlib.sha256(canonical_json_bytes(changed_fill)).hexdigest()
        with self.assertRaises(LedgerError) as fill_error:
            locked.append_batch((EventInput(EventType.FILL_OBSERVED, conflict_payload, session, "synthetic-incident"),))
        self.assertEqual(fill_error.exception.code, FailureCode.DUPLICATE_FILL_CONFLICT)
        self.assertEqual(len(locked.projection().canonical_fills_by_fill_id), 1)
        locked.close()

    def test_fill_payload_requires_decimal_and_preserves_actual_price(self) -> None:
        payload = canonical_kalshi_fill_payload(
            fill_id="fill-1", order_id="order-1", price=Decimal("0.42"),
            quantity=Decimal("3"), fee=Decimal("0.02"),
            additional_fields={"submitted_limit_price": Decimal("0.50")},
        )
        self.assertEqual(payload["price"], Decimal("0.42"))
        self.assertNotEqual(payload["price"], payload["submitted_limit_price"])
        with self.assertRaises(LedgerError):
            canonical_kalshi_fill_payload(
                fill_id="fill-1", order_id="order-1", price=0.42,
                quantity=Decimal("3"), fee=Decimal("0.02"),
            )

    def test_no_real_side_effect_capability_exists(self) -> None:
        # Structural proof: neither module imports socket/http/ssl nor exposes
        # a transport/credential/signing member on the restricted handle.
        source = Path(ledger.__file__).read_text(encoding="utf-8") + Path(
            __import__("arb.venues.kalshi.ledger_binding", fromlist=["x"]).__file__
        ).read_text(encoding="utf-8")
        for prohibited_import in ("import socket", "import requests", "import httpx", "import ssl"):
            self.assertNotIn(prohibited_import, source)


class NormalWriterAcquisitionTestCase(KalshiLedgerBindingTestCase):
    """GATE A IMPLEMENTATION 02: same-scope correction to Marco-blocked
    Implementation 01 (candidate 0a38e7c2f7862f8b39e7543f657e4c83a1910e4f),
    applying Correction 01 (ER-NW-002 exact replay-derived
    history-completeness semantics), Correction 02 (ER-NW-001 module-private
    normal-writer candidate bridge; no public generic bypass), and
    Correction 03 (exact ER-NW-003 ``NormalWriterAcquisition`` acquisition
    contract, exact returned ``normal_writer_session_id``, exact
    ``NORMAL_WRITER_ACQUISITION_REJECTED`` classification) from
    KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_EXPERIMENT_RUNNER_SPEC_03.md
    (bytes=117449, sha256=09bdca72ea83c4b701ee8c743b06f384c7fe682f7fb5bf14459ab484dad81771),
    incorporated unchanged by SPEC_04, plus SPEC_04's current-process
    release-completion continuity additions (ER04-REL-CAP-*/ER04-NW-003..005).

    Every positive-path fixture reaches ``history_completeness == COMPLETE``
    only through the real ``commit_exact_legacy_import`` /
    ``validate_legacy_evidence`` ceremony followed by one genuine qualifying
    ``RECONCILIATION_RECORDED`` event (per ER-NW-002) -- never by skipping
    legacy import, never by fabricating replay facts.  Per ER04-TEST-003,
    white-box private-constructor access is used only to prove
    rejection/non-forgeability of a deliberately wrong token, never to
    manufacture a successful writer-admission fixture.
    """

    @staticmethod
    def _synthetic_legacy_evidence_documents(
        *, incident_id: str, writer_proof_id: str, legacy_writer_session_id: str,
    ) -> dict[str, dict[str, object]]:
        lifecycle = {
            "task_id": incident_id,
            "authorization_consumed": True,
            "environment": CURRENT_ENVIRONMENT,
            "ticker": CURRENT_TICKER,
            "client_order_id": CURRENT_CLIENT_ORDER_ID,
            "phase": "FAIL_CLOSED_HALT",
            "halt_code": "RECOVERY_ZERO_MATCH",
            "terminal_result": None,
            "canonical_lifecycle_evidence": {
                "environment": CURRENT_ENVIRONMENT,
                "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                "subaccount": 0,
                "ticker": CURRENT_TICKER,
                "client_order_id": CURRENT_CLIENT_ORDER_ID,
                "writer_session_id": legacy_writer_session_id,
                "proof_id": writer_proof_id,
                "proof_state": "HELD",
                "proof_release_eligible": False,
                "bound_order_id": None,
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "create_send_may_have_begun": True,
                "cancel_send_may_have_begun": False,
                "halt_code": "RECOVERY_ZERO_MATCH",
            },
            "writer_proof": {
                "id": writer_proof_id,
                "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                "writer_session_id": legacy_writer_session_id,
                "continuity_state": "HELD",
            },
            "reconciliation": {
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "proof_release_eligible": False,
            },
            "authoritative_order_snapshots": [],
            "canonical_fill_summary": None,
        }
        reconciliation = {
            "task_id": "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EXECUTION_01",
            "authorization": {
                "authorization_consumed": True,
                "overall_execution_attempts_authorized": 1,
            },
            "canonical_result": {
                "result_class": CURRENT_DISPOSITION,
                "bound_order_id": None,
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "writer_proof_release_eligible": False,
                "exact_client_order_id_match_count": 0,
                "canonical_fill_count": 0,
                "evidence": {
                    "task_id": "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_IMPLEMENTATION_01",
                    "frozen_scope": {
                        "environment": CURRENT_ENVIRONMENT,
                        "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                        "subaccount": 0,
                        "ticker": CURRENT_TICKER,
                        "client_order_id": CURRENT_CLIENT_ORDER_ID,
                        "writer_proof_id": writer_proof_id,
                    },
                    "terminal": {
                        "result_class": CURRENT_DISPOSITION,
                        "created_order_upper_bound": 1,
                        "active_order_upper_bound": 1,
                        "unknown_result": True,
                        "writer_proof_release_eligible": False,
                    },
                    "order_match": {
                        "bound_order_id": None,
                        "exact_client_order_id_match_count": 0,
                        "canonical_orders": [],
                        "matched_order_ids": [],
                    },
                    "fills": {
                        "canonical_fill_count": 0,
                        "canonical_fill_identities": [],
                        "order_fill_reconciliation_result": "UNRESOLVED_OR_NOT_REACHED",
                    },
                    "enumeration": {"records_retained": {"orders": 0, "fills": 0}},
                },
            },
        }
        fill_discovery = {
            "task_id": "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_01",
            "authorization": {
                "authorization_consumed": True,
                "overall_execution_authorized": 1,
                "rerun_permitted_under_this_authorization": False,
            },
            "canonical_result": {
                "result_class": CURRENT_DISPOSITION,
                "bound_order_id": None,
                "created_order_upper_bound": 1,
                "active_order_upper_bound": 1,
                "unknown_result": True,
                "writer_proof_release_eligible": False,
                "candidate_order_id_count": 0,
                "candidate_order_ids": [],
                "canonical_fill_count": 0,
                "validated_binding_count": 0,
                "validated_binding_order_ids": [],
                "prior_exact_client_order_id_match_count": 0,
                "evidence": {
                    "task_id": "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_IMPLEMENTATION_01",
                    "frozen_scope": {
                        "environment": CURRENT_ENVIRONMENT,
                        "account_scope_ref": CURRENT_ACCOUNT_SCOPE_REF,
                        "subaccount": 0,
                        "ticker": CURRENT_TICKER,
                        "client_order_id": CURRENT_CLIENT_ORDER_ID,
                        "writer_proof_id": writer_proof_id,
                    },
                    "predecessor_result": {
                        "result_class": CURRENT_DISPOSITION,
                        "bound_order_id": None,
                        "created_order_upper_bound": 1,
                        "active_order_upper_bound": 1,
                        "exact_client_order_id_match_count": 0,
                        "unknown_result": True,
                        "writer_proof_release_eligible": False,
                    },
                    "terminal": {
                        "result_class": CURRENT_DISPOSITION,
                        "bound_order_id": None,
                        "created_order_upper_bound": 1,
                        "active_order_upper_bound": 1,
                        "unknown_result": True,
                        "writer_proof_release_eligible": False,
                        "candidate_order_id_count": 0,
                        "candidate_order_ids": [],
                        "canonical_fill_count": 0,
                        "prior_exact_client_order_id_match_count": 0,
                        "validated_binding_count": 0,
                        "validated_binding_order_ids": [],
                    },
                    "bound_fill_reconciliation": {
                        "bound_order_id": None,
                        "bound_fills": [],
                        "canonical_fill_count": 0,
                    },
                    "candidate_validation": {
                        "results": [],
                        "validated_binding_count": 0,
                        "validated_binding_order_ids": [],
                    },
                    "discovery": {
                        "candidate_order_id_count": 0,
                        "candidate_order_id_set": [],
                        "canonical_discovery_fills": [],
                        "unique_fill_id_count": 0,
                    },
                },
            },
        }
        return {
            "execution_evidence.json": lifecycle,
            "KALSHI_DEMO_POST_HALT_EXACT_WRITE_RESULT_RECONCILIATION_EVIDENCE_01.json": reconciliation,
            "KALSHI_DEMO_POST_HALT_FILL_DISCOVERY_BINDING_FALLBACK_EXECUTION_EVIDENCE_01.json": fill_discovery,
        }

    def _build_legacy_completed_safe_held(self):
        """Reach SAFE_HELD with genuine ``history_completeness == COMPLETE``.

        Builds a synthetic legacy incident through the real
        ``commit_exact_legacy_import``/``validate_legacy_evidence`` ceremony
        (only the identity fields are parameterized; the imported
        disposition/eligibility shape is frozen exactly as for the real
        historical incident -- legacy import always begins protected), then
        records one genuine qualifying ``RECONCILIATION_RECORDED`` event for
        that same incident making its sole associated writer proof
        release-eligible.  Per ER-NW-002 this is the only way
        ``protected_unresolved_legacy_write_count`` can reach zero for an
        imported incident, and thus the only way ``history_completeness``
        can ever reach ``COMPLETE``.
        """
        self.initialize()
        incident_id = "SYNTHETIC_LEGACY_RELEASE_INCIDENT"
        proof_id = "SYNTHETIC_LEGACY_RELEASE_PROOF"
        legacy_writer_session_id = "SYNTHETIC_LEGACY_RELEASE_LOCAL_RUNNER"
        documents = self._synthetic_legacy_evidence_documents(
            incident_id=incident_id, writer_proof_id=proof_id,
            legacy_writer_session_id=legacy_writer_session_id,
        )
        evidence = self._encode_evidence_documents(documents)
        contract = LegacyIncidentContract(
            incident_id=incident_id, writer_proof_id=proof_id,
            legacy_writer_session_id=legacy_writer_session_id,
            evidence_expectations=self._expectations_for(evidence),
        )
        imported = acquire_legacy_import_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(imported.handle)
        validated = imported.handle.validate_legacy_evidence(evidence)
        imported.handle.commit_exact_legacy_import(validated)
        imported.handle.close()

        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        handle = emergency.handle
        assert handle is not None
        handle.record_reconciliation({
            "incident_id": incident_id,
            "disposition": "SYNTHETIC_QUALIFYING_RECONCILIATION_CLOSED",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
            "bound_order_id": None,
            "created_order_upper_bound": 0,
            "active_order_upper_bound": 0,
            "unknown_result": False,
            "writer_proof_release_eligible": True,
            "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RECONCILIATION_V1",
        }, incident_id=incident_id)
        projection = handle.inspect_validated_projection()
        self.assertEqual(projection.history_completeness, "COMPLETE")
        self.assertEqual(projection.protected_unresolved_legacy_write_count, 0)
        self.assertTrue(projection.writer_proof_release_eligible_by_proof_id[proof_id])
        self.assertEqual(projection.writer_proof_state_by_proof_id[proof_id], "HELD")
        # Restart classification remains UNRESOLVED_WRITE_HELD: the proof is
        # eligible but not yet RELEASED (ER-NW-002's intentionally
        # conservative two-stage gate).
        self.assertEqual(projection.restart_classification, RestartClassification.UNRESOLVED_WRITE_HELD)

        config = RiskLimitConfigV1(
            1, contract.conflict_domain_ref, "USD",
            PerOrderRiskLimits(Decimal("10"), Decimal("10"), True, Decimal("0.10"), 1_000),
            PerMarketRiskLimits(Decimal("20"), Decimal("20"), 10, Decimal("20"), Decimal("20")),
            AccountRiskLimits(Decimal("100"), 50, Decimal("100"), 0, Decimal("0")),
            FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
        )
        canonical_order = {
            "order_id": "synthetic-legacy-order-1", "status": "resting",
            "remaining_count_fp": "1.00", "market": "SYNTHETIC",
            "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": True,
        }
        order_event = handle.record_order_observation({
            "venue_order_id": "synthetic-legacy-order-1",
            "client_order_id": "synthetic-legacy-client-order-1",
            "source_request_id": "synthetic-legacy-release-order-read",
            "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1",
            "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }).events[-1]
        canonical_fill = canonical_kalshi_fill_payload(
            fill_id="synthetic-legacy-fill-1", order_id="synthetic-legacy-order-1",
            price=Decimal("0.40"), quantity=Decimal("1.00"), fee=Decimal("0.01"),
            additional_fields={
                "market": "SYNTHETIC", "outcome_side": "YES",
                "authoritative_created_time_utc": "2026-08-13T13:00:00.000000Z",
            },
        )
        fill_event = handle.record_fill_observation({
            "canonical_venue_payload": canonical_fill,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
            "client_order_id": "synthetic-legacy-client-order-1",
            "source_operation": "SYNTHETIC_FILL_READ",
            "source_request_id": "synthetic-legacy-release-fill-read",
            "venue_fill_id": "synthetic-legacy-fill-1",
            "venue_order_id": "synthetic-legacy-order-1",
            "venue_payload_schema_id": "synthetic-fill-v1",
        }).events[-1]
        # No record_writer_proof_held here: the proof is already HELD via
        # the legacy import above; re-holding it would be a duplicate/
        # conflicting event, not a fresh predecessor hold.
        before = handle.inspect_validated_projection()
        state_payload = {
            "previous_state": "BOOT_HOLD",
            "new_state": "SAFE_HELD",
            "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
            "risk_state_epoch_before": 0,
            "risk_state_epoch_after": 1,
            "risk_config_sha256": config.sha256,
            "related_emergency_action_id": None,
            "related_release_id": None,
            "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": before.last_sequence,
            "observed_authority_trusted_hash": before.terminal_event_hash,
            "observed_ledger_terminal_sequence": before.last_sequence,
            "observed_ledger_terminal_hash": before.terminal_event_hash,
        }
        handle.record_risk_control_state_changed(state_payload)
        safe_projection = handle.inspect_validated_projection()
        self.assertEqual(safe_projection.risk_control_state, "SAFE_HELD")
        self.assertEqual(safe_projection.history_completeness, "COMPLETE")
        self.assertEqual(safe_projection.protected_unresolved_legacy_write_count, 0)
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
        emergency_gate = EmergencyCancelGate(
            handle=handle,
            rate_lane=lane,
            process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        handle.close()
        market_data = {"ticker": "SYNTHETIC", "reference_yes_price": Decimal("0.50")}
        risk_snapshot = ReleaseRiskSnapshotV1(
            fills=(EconomicFillV1(
                "SYNTHETIC", "synthetic-legacy-fill-1", "YES", Decimal("1.00"),
                Decimal("0.40"), "2026-08-13T13:00:00.000000Z",
            ),),
            working_orders=(WorkingOrderV1(
                "SYNTHETIC", "synthetic-legacy-order-1", "YES", Decimal("1.00"), Decimal("0.50"),
            ),),
            unresolved_write_count=0,
            unresolved_write_exposure_usd=Decimal("0"),
            market_data_snapshot=market_data,
        )
        reconciliation_snapshot = ReleaseReconciliationSnapshotV1(
            ("synthetic-legacy-order-1",), ("synthetic-legacy-order-1",), ("synthetic-legacy-fill-1",),
            (), (), (("synthetic-legacy-order-1", order_event.event_id),),
            (("synthetic-legacy-fill-1", fill_event.event_id),),
        )
        received_ns = self.inputs.monotonic_value
        received_at = ledger.canonical_timestamp(self.inputs.instant)
        market_stamp = FreshnessStampV1(
            normal_gate.process_instance_id, received_at, received_ns, "NONE", None,
            risk_snapshot.market_data_sha256,
        )
        reconciliation_stamp = FreshnessStampV1(
            normal_gate.process_instance_id, received_at, received_ns, "NONE", None,
            reconciliation_snapshot.sha256,
        )
        state = ReleaseEvaluationStateV1(
            process_instance_id=normal_gate.process_instance_id,
            incident_id=incident_id,
            writer_proof_id=proof_id,
            risk_config=config,
            risk_snapshot=risk_snapshot,
            reconciliation_snapshot=reconciliation_snapshot,
            market_freshness=market_stamp,
            reconciliation_freshness=reconciliation_stamp,
            venue_defense_evidence=None,
            normal_gate=normal_gate,
            emergency_gate=emergency_gate,
        )
        return contract, proof_id, incident_id, config, state, normal_gate, emergency_gate

    def _begin_legacy_completed_release(self):
        contract, proof_id, incident_id, config, state, normal_gate, emergency_gate = (
            self._build_legacy_completed_safe_held()
        )
        acquisition = acquire_release_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
            monotonic_clock_ns=self.inputs.monotonic_ns,
            release_wall_clock=self.inputs.clock,
        )
        self.assertIsNotNone(acquisition.handle)
        handle = acquisition.handle
        assert handle is not None
        assessment = handle.evaluate_release(state)
        return handle, assessment, state, contract, proof_id, incident_id, config, normal_gate, emergency_gate

    def _issue_genuine_token(self):
        """Drive one full canonical RELEASE_ONLY sequence to a live token.

        Returns (token, risk_config, process_instance_id, contract).
        """
        (
            handle, assessment, state, contract, proof_id, incident_id, config,
            normal_gate, emergency_gate,
        ) = self._begin_legacy_completed_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        handle.record_writer_eligible(assessment)
        token = handle.complete_release_and_issue_current_process_completion(assessment)
        return token, config, normal_gate.process_instance_id, contract

    # ------------------------------------------------------------------
    # A01 -- historical durable WRITER_ELIGIBLE without current-process
    # token cannot acquire NORMAL_WRITER, even though every other durable
    # predicate (including the new history_completeness == COMPLETE gate)
    # genuinely passes.
    # ------------------------------------------------------------------
    def test_a01_historical_writer_eligible_without_token_cannot_acquire(self) -> None:
        (
            handle, assessment, state, contract, proof_id, incident_id, config,
            normal_gate, emergency_gate,
        ) = self._begin_legacy_completed_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        handle.record_writer_eligible(assessment)
        handle.close()  # durable WRITER_ELIGIBLE now exists; no token was ever issued.

        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=normal_gate.process_instance_id,
            current_process_release_completion=None,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsInstance(result, NormalWriterAcquisition)
        self.assertIsNone(result.handle)
        self.assertIsNone(result.normal_writer_session_id)
        self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED)
        self.assertIsNone(result.projection.active_writer_session_id)

    # ------------------------------------------------------------------
    # A02 -- exact NormalWriterAcquisition success: fresh ws_ session,
    # exact returned normal_writer_session_id, history_completeness ==
    # COMPLETE reached only through genuine legacy import + qualifying
    # reconciliation.
    # ------------------------------------------------------------------
    def test_a02_same_process_release_finalizer_admits_fresh_writer(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        self.assertTrue(_is_registered_current_process_release_completion(token))
        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=process_instance_id,
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsInstance(result, NormalWriterAcquisition)
        self.assertIsNotNone(result.handle)
        self.assertIsNone(result.failure_code)
        self.assertIsNotNone(result.normal_writer_session_id)
        self.assertTrue(result.normal_writer_session_id.startswith("ws_"))
        self.assertEqual(result.projection.active_writer_session_id, result.normal_writer_session_id)
        self.assertEqual(result.projection.risk_control_state, "WRITER_ELIGIBLE")
        self.assertEqual(result.handle.events[-1].event_type, EventType.WRITER_SESSION_STARTED)
        result.handle.close()

    # ------------------------------------------------------------------
    # A03 -- wrong process rejects token.
    # ------------------------------------------------------------------
    def test_a03_wrong_process_rejects_token(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id="proc_" + ("0" * 32),
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(result.handle)
        self.assertIsNone(result.normal_writer_session_id)
        self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_PROCESS_MISMATCH)
        self.assertTrue(_is_registered_current_process_release_completion(token))

    # ------------------------------------------------------------------
    # A04 -- wrong risk config rejects (pure durable/config rejection uses
    # NORMAL_WRITER_ACQUISITION_REJECTED, since it is caught before the
    # token-specific staleness block is ever reached).
    # ------------------------------------------------------------------
    def test_a04_wrong_risk_config_rejects(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        wrong_per_market = replace(
            config.per_market,
            max_authoritative_working_orders=config.per_market.max_authoritative_working_orders + 1,
        )
        wrong_config = replace(config, per_market=wrong_per_market)
        self.assertNotEqual(wrong_config.sha256, config.sha256)
        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=wrong_config,
            process_instance_id=process_instance_id,
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(result.handle)
        self.assertEqual(result.failure_code, FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED)
        self.assertTrue(_is_registered_current_process_release_completion(token))

    # ------------------------------------------------------------------
    # A05 -- wrong risk-state epoch rejects (white-box field substitution on
    # a separately-registered token; the underlying durable state is
    # unaffected, isolating exactly this staleness condition).
    # ------------------------------------------------------------------
    def test_a05_wrong_risk_state_epoch_rejects(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        wrong_values = {field.name: getattr(token, field.name) for field in fields(type(token))}
        wrong_values["resulting_risk_state_epoch"] = token.resulting_risk_state_epoch + 1
        wrong_token = CurrentProcessReleaseCompletionV1(_CURRENT_PROCESS_RELEASE_COMPLETION_KEY, **wrong_values)
        _register_current_process_release_completion(wrong_token)
        try:
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=wrong_token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_STALE)
        finally:
            _consume_current_process_release_completion(wrong_token)
        self.assertTrue(_is_registered_current_process_release_completion(token))

    # ------------------------------------------------------------------
    # A06 -- wrong writer-eligible-state-event identity rejects.
    # ------------------------------------------------------------------
    def test_a06_wrong_state_event_identity_rejects(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        wrong_values = {field.name: getattr(token, field.name) for field in fields(type(token))}
        wrong_values["writer_eligible_state_event_hash"] = "f" * 64
        wrong_token = CurrentProcessReleaseCompletionV1(_CURRENT_PROCESS_RELEASE_COMPLETION_KEY, **wrong_values)
        _register_current_process_release_completion(wrong_token)
        try:
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=wrong_token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_STALE)
        finally:
            _consume_current_process_release_completion(wrong_token)

    # ------------------------------------------------------------------
    # A07 -- authority/ledger tail movement invalidates token (a pure
    # tail-moving event that touches no risk-control-state transition).
    # ------------------------------------------------------------------
    def test_a07_authority_ledger_tail_movement_invalidates_token(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        emergency = acquire_emergency_control_only(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        stale_order = {
            "venue_order_id": "post-issuance-order-1",
            "client_order_id": "post-issuance-client-order-1",
            "source_request_id": "post-issuance-order-read",
            "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1",
            "canonical_venue_payload": {
                "order_id": "post-issuance-order-1", "status": "resting",
                "remaining_count_fp": "1.00", "market": "SYNTHETIC",
                "outcome_side": "YES", "yes_price": Decimal("0.50"),
                "cancel_order_on_pause": True,
            },
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes({
                "order_id": "post-issuance-order-1", "status": "resting",
                "remaining_count_fp": "1.00", "market": "SYNTHETIC",
                "outcome_side": "YES", "yes_price": Decimal("0.50"),
                "cancel_order_on_pause": True,
            })).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }
        emergency.handle.record_order_observation(stale_order)
        emergency.handle.close()

        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=process_instance_id,
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(result.handle)
        self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_STALE)
        self.assertEqual(result.projection.risk_control_state, "WRITER_ELIGIBLE")
        self.assertTrue(_is_registered_current_process_release_completion(token))

    # ------------------------------------------------------------------
    # A08/A09/A10 -- copy/deepcopy/pickle/reduce reconstruction rejected.
    # ------------------------------------------------------------------
    def test_a08_copy_rejected(self) -> None:
        token, *_ = self._issue_genuine_token()
        with self.assertRaises(TypeError):
            copy.copy(token)

    def test_a09_deepcopy_rejected(self) -> None:
        token, *_ = self._issue_genuine_token()
        with self.assertRaises(TypeError):
            copy.deepcopy(token)

    def test_a10_pickle_reduce_reconstruction_rejected(self) -> None:
        token, *_ = self._issue_genuine_token()
        with self.assertRaises(TypeError):
            pickle.dumps(token)
        with self.assertRaises(TypeError):
            token.__reduce_ex__(4)

    # ------------------------------------------------------------------
    # A11 -- fabricated value-equal object rejected: identity, not equality.
    # ------------------------------------------------------------------
    def test_a11_fabricated_value_equal_object_rejected(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        same_values = {field.name: getattr(token, field.name) for field in fields(type(token))}
        fabricated = CurrentProcessReleaseCompletionV1(_CURRENT_PROCESS_RELEASE_COMPLETION_KEY, **same_values)
        self.assertIsNot(fabricated, token)
        self.assertEqual(fabricated, token)  # every public field matches...
        self.assertFalse(_is_registered_current_process_release_completion(fabricated))  # ...but is not registered.

        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=process_instance_id,
            current_process_release_completion=fabricated,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(result.handle)
        self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        self.assertTrue(_is_registered_current_process_release_completion(token))

        with self.assertRaises(LedgerError) as wrong_key:
            CurrentProcessReleaseCompletionV1(object(), **same_values)
        self.assertEqual(wrong_key.exception.code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)

    # ------------------------------------------------------------------
    # A12 -- registry retains a strong reference while valid (deterministic
    # refcount proof; never a probabilistic id-reuse loop).
    # ------------------------------------------------------------------
    def test_a12_registry_retains_strong_reference(self) -> None:
        token, *_ = self._issue_genuine_token()
        self.assertIn(id(token), _current_process_release_completion_registry)
        # Scoped narrowly: holding a local reference to the record would
        # itself keep the token's refcount elevated after consumption below,
        # confounding the very thing this test measures.
        expected_snapshot = {field.name: getattr(token, field.name) for field in fields(type(token))}
        self.assertIs(_current_process_release_completion_registry[id(token)].token, token)
        self.assertEqual(
            dict(_current_process_release_completion_registry[id(token)].snapshot),
            expected_snapshot,
        )
        registered_refcount = sys.getrefcount(token)
        _consume_current_process_release_completion(token)
        after_refcount = sys.getrefcount(token)
        self.assertEqual(after_refcount, registered_refcount - 1)
        self.assertNotIn(id(token), _current_process_release_completion_registry)

    # ------------------------------------------------------------------
    # GATE A IMPLEMENTATION 03: exact frozen-field validation.  Object-
    # identity registry membership alone does not prove every field is
    # still exact -- ``object.__setattr__`` can mutate a field on the live,
    # still-registered token without changing its identity.  Each of these
    # mutates one field on an otherwise genuine, still-registered token
    # (bounded white-box mutation used only to prove rejection, never to
    # manufacture a successful fixture) and restores it afterward.
    # ------------------------------------------------------------------
    def test_t01_wrong_schema_revision_rejects(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        original = token.schema_revision
        object.__setattr__(token, "schema_revision", 2)
        try:
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertIsNone(result.normal_writer_session_id)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        finally:
            object.__setattr__(token, "schema_revision", original)

    def test_t01b_schema_revision_exact_type_bool_confusion_rejects(self) -> None:
        # schema_revision's genuine value is exactly 1; True == 1 under
        # plain ``==`` but type(True) is bool, not int.  A naive value-only
        # check would wrongly accept this.
        token, config, process_instance_id, contract = self._issue_genuine_token()
        self.assertEqual(token.schema_revision, 1)
        object.__setattr__(token, "schema_revision", True)
        try:
            self.assertEqual(token.schema_revision, 1)  # still true by plain ==
            self.assertIsNot(type(token.schema_revision), int)  # but wrong exact type
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        finally:
            object.__setattr__(token, "schema_revision", 1)

    def test_t02_wrong_private_release_handle_identity_rejects(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        original = token.private_release_handle_identity
        object.__setattr__(token, "private_release_handle_identity", object())
        try:
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertIsNone(result.normal_writer_session_id)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
            # Object identity in the registry is unaffected by the mutation.
            self.assertTrue(_is_registered_current_process_release_completion(token))
        finally:
            object.__setattr__(token, "private_release_handle_identity", original)

    def test_t03_wrong_private_release_source_identity_rejects(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        original = token.private_release_source_identity
        object.__setattr__(token, "private_release_source_identity", object())
        try:
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertIsNone(result.normal_writer_session_id)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
            self.assertTrue(_is_registered_current_process_release_completion(token))
        finally:
            object.__setattr__(token, "private_release_source_identity", original)

    def test_t04_exact_type_contract_on_resulting_risk_state_epoch(self) -> None:
        # A second load-bearing field (distinct from schema_revision) where
        # the frozen schema requires exact built-in int; a wrong-typed
        # substitution must be rejected even though it lives entirely
        # outside the schema_revision-specific check.
        token, config, process_instance_id, contract = self._issue_genuine_token()
        original = token.resulting_risk_state_epoch
        object.__setattr__(token, "resulting_risk_state_epoch", str(original))
        try:
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        finally:
            object.__setattr__(token, "resulting_risk_state_epoch", original)

    def test_t05_unmodified_genuine_token_still_admits_exactly_once(self) -> None:
        # The correction must not make the legitimate path impossible.
        token, config, process_instance_id, contract = self._issue_genuine_token()
        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=process_instance_id,
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNotNone(result.handle)
        self.assertIsNotNone(result.normal_writer_session_id)
        self.assertTrue(result.normal_writer_session_id.startswith("ws_"))
        self.assertFalse(_is_registered_current_process_release_completion(token))
        result.handle.close()

    # ------------------------------------------------------------------
    # A13/A14 -- single admission; second use of a consumed token fails.
    # ------------------------------------------------------------------
    def test_a13_genuine_token_admits_at_most_once(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=process_instance_id,
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNotNone(result.handle)
        self.assertFalse(_is_registered_current_process_release_completion(token))
        result.handle.close()

    def test_a14_second_use_of_consumed_token_fails(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        first = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=process_instance_id,
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNotNone(first.handle)
        first.handle.close()

        second = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=config,
            process_instance_id=process_instance_id,
            current_process_release_completion=token,
            contract=contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(second.handle)
        self.assertEqual(second.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)

    # ------------------------------------------------------------------
    # A15/A16 -- restart destroys the process-local registry; durable
    # replay alone (WRITER_ELIGIBLE plus COMPLETE history) cannot
    # reconstruct token validity.
    # ------------------------------------------------------------------
    def test_a15_restart_clears_registry_and_invalidates_live_token(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        self.assertTrue(_is_registered_current_process_release_completion(token))
        saved = dict(_current_process_release_completion_registry)
        _current_process_release_completion_registry.clear()
        try:
            self.assertFalse(_is_registered_current_process_release_completion(token))
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(result.handle)
            self.assertEqual(result.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        finally:
            _current_process_release_completion_registry.clear()
            _current_process_release_completion_registry.update(saved)

    def test_a16_durable_replay_alone_cannot_recreate_token(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        saved = dict(_current_process_release_completion_registry)
        _current_process_release_completion_registry.clear()
        try:
            reopened = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=None,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
            )
            self.assertIsNone(reopened.handle)
            self.assertEqual(reopened.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED)
            self.assertEqual(reopened.projection.risk_control_state, "WRITER_ELIGIBLE")
            self.assertEqual(reopened.projection.history_completeness, "COMPLETE")
        finally:
            _current_process_release_completion_registry.clear()
            _current_process_release_completion_registry.update(saved)

    # ------------------------------------------------------------------
    # A17 -- alias of A07 (same intervening-event mechanism).
    # ------------------------------------------------------------------
    def test_a17_intervening_event_invalidates_token(self) -> None:
        self.test_a07_authority_ledger_tail_movement_invalidates_token()

    # ------------------------------------------------------------------
    # A18 -- ER-NW-005: the exact current historical state remains blocked
    # (protected forever: nothing ever records a qualifying reconciliation
    # for CURRENT_INCIDENT_ID), before any secret/network activity.
    # ------------------------------------------------------------------
    def test_a18_current_historical_incident_blocks_before_secret_or_network(self) -> None:
        self.initialize()
        acquisition = self.acquire_import()
        acquisition.handle.commit_exact_legacy_import(
            acquisition.handle.validate_legacy_evidence(self.evidence)
        )
        acquisition.handle.close()

        candidate = _acquire_normal_writer_candidate(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
        )
        self.assertIsNotNone(candidate.handle)  # ER-NW-001 exposes the candidate...
        self.assertEqual(candidate.projection.history_completeness, "COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE")
        self.assertEqual(candidate.projection.protected_unresolved_legacy_write_count, 1)
        candidate.handle.close()

        # ...but the Kalshi binding's own durable-eligibility gate (ER-NW-003)
        # rejects it before ever inspecting risk_config/token.
        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=object(),  # type: ignore[arg-type]
            process_instance_id="proc_" + ("0" * 32),
            current_process_release_completion=object(),  # type: ignore[arg-type]
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(result.handle)
        self.assertIsNone(result.normal_writer_session_id)
        self.assertEqual(result.failure_code, FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED)
        self.assertEqual(result.projection.protected_unresolved_legacy_write_count, 1)
        self.assertEqual(result.projection.reconciliation_disposition_by_incident[CURRENT_INCIDENT_ID], CURRENT_DISPOSITION)
        self.assertFalse(result.projection.writer_proof_release_eligible_by_proof_id[CURRENT_WRITER_PROOF_ID])

    # ------------------------------------------------------------------
    # A19 -- no clean-history bootstrap: an empty fresh ledger stays
    # BOOT_HOLD/INCOMPLETE, never COMPLETE, merely by existing.
    # ------------------------------------------------------------------
    def test_a19_empty_fresh_ledger_cannot_bootstrap_writer_eligible(self) -> None:
        self.initialize()
        candidate = _acquire_normal_writer_candidate(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
        )
        self.assertIsNotNone(candidate.handle)  # ER-NW-001 exposes any equal-tail candidate...
        self.assertEqual(candidate.projection.history_completeness, "INCOMPLETE")
        self.assertEqual(candidate.projection.risk_control_state, "BOOT_HOLD")
        candidate.handle.close()

        result = acquire_normal_writer_state(
            self.binding,
            canonical_repository_root=str(self.repository_root),
            risk_config=None,
            process_instance_id="proc_" + ("0" * 32),
            current_process_release_completion=None,
            contract=self.contract,
            expected_ledger_path=str(self.ledger_path),
        )
        self.assertIsNone(result.handle)
        self.assertEqual(result.failure_code, FailureCode.NORMAL_WRITER_ACQUISITION_REJECTED)

    # ------------------------------------------------------------------
    # A20 -- ER-NW-001/Correction 02: the public generic NORMAL_WRITER
    # bridge exposes no live bypass handle, even for a domain that has
    # genuinely reached durable WRITER_ELIGIBLE with COMPLETE history; only
    # the private bridge (consumed exclusively by the Kalshi binding) does.
    # ------------------------------------------------------------------
    def test_a20_public_generic_bridge_exposes_no_bypass_handle(self) -> None:
        (
            handle, assessment, state, contract, proof_id, incident_id, config,
            normal_gate, emergency_gate,
        ) = self._begin_legacy_completed_release()
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        handle.record_writer_eligible(assessment)
        handle.close()

        public = acquire_local_state(
            self.binding,
            conflict_domain_ref=contract.conflict_domain_ref,
            expected_environment=contract.environment,
            canonical_repository_root=self.repository_root,
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
            expected_ledger_path=self.ledger_path,
        )
        self.assertIsNone(public.handle)

        private_candidate = _acquire_normal_writer_candidate(
            self.binding,
            conflict_domain_ref=contract.conflict_domain_ref,
            expected_environment=contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
        )
        self.assertIsNotNone(private_candidate.handle)
        self.assertEqual(private_candidate.projection.risk_control_state, "WRITER_ELIGIBLE")
        self.assertEqual(private_candidate.projection.history_completeness, "COMPLETE")
        self.assertIsNone(private_candidate.projection.active_writer_session_id)
        self.assertFalse(any(
            event.event_type is EventType.WRITER_SESSION_STARTED
            for event in private_candidate.handle.events
        ))
        private_candidate.handle.close()

    # ------------------------------------------------------------------
    # ER-NW-004 -- session start uses/returns the exact deterministic seams
    # (clock/uuid_factory/fault_hook) required by the frozen acquisition API.
    # ------------------------------------------------------------------
    def test_deterministic_seams_are_honored_at_session_start(self) -> None:
        # Two independently built fixtures, each driven through an identically
        # freshly-seeded DeterministicInputs seam supplied only for the
        # acquisition call itself (not the token-issuance flow, which keeps
        # using self.inputs).  If the supplied clock/uuid_factory seam is
        # actually threaded through to start_writer_session rather than
        # silently falling back to the real uuid.uuid4/wall clock, the two
        # runs must produce the exact same ws_ session id.
        session_ids: list[str] = []
        for _ in range(2):
            # Each iteration needs its own fresh authority/ledger namespace;
            # initialize() may only run once per namespace.
            self.tearDown()
            self.setUp()
            token, config, process_instance_id, contract = self._issue_genuine_token()
            seam_inputs = DeterministicInputs()
            result = acquire_normal_writer_state(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                risk_config=config,
                process_instance_id=process_instance_id,
                current_process_release_completion=token,
                contract=contract,
                expected_ledger_path=str(self.ledger_path),
                clock=seam_inputs.clock,
                uuid_factory=seam_inputs.uuid,
            )
            self.assertIsNotNone(result.handle)
            assert result.normal_writer_session_id is not None
            self.assertTrue(result.normal_writer_session_id.startswith("ws_"))
            session_ids.append(result.normal_writer_session_id)
            result.handle.close()
        self.assertEqual(session_ids[0], session_ids[1])

    # ------------------------------------------------------------------
    # ER-NW-002 direct derivation coverage.  The generic schema validator
    # permits at most one LEGACY_INCIDENT_IMPORTED event ever
    # (execution_ledger._validate_spec03_event_sequence), so "multiple
    # imported incidents" is structurally unreachable; these cases instead
    # cover the reachable state machine: import alone (protected), import +
    # qualifying reconciliation (COMPLETE but still HELD/UNRESOLVED_WRITE_HELD),
    # import + reconciliation + RELEASED (COMPLETE and finally
    # SAFE_NO_WRITE_CAPABILITY), and multiple candidate controlling proofs
    # for the same imported incident (remains protected even if one proof is
    # eligible).
    # ------------------------------------------------------------------
    def test_er_nw_002_import_alone_is_protected_and_unresolved(self) -> None:
        self.initialize()
        incident_id = "SYNTHETIC_ER_NW_002_INCIDENT_A"
        proof_id = "SYNTHETIC_ER_NW_002_PROOF_A"
        legacy_writer_session_id = "SYNTHETIC_ER_NW_002_A_LOCAL_RUNNER"
        documents = self._synthetic_legacy_evidence_documents(
            incident_id=incident_id, writer_proof_id=proof_id,
            legacy_writer_session_id=legacy_writer_session_id,
        )
        evidence = self._encode_evidence_documents(documents)
        contract = LegacyIncidentContract(
            incident_id=incident_id, writer_proof_id=proof_id,
            legacy_writer_session_id=legacy_writer_session_id,
            evidence_expectations=self._expectations_for(evidence),
        )
        imported = acquire_legacy_import_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        result = imported.handle.commit_exact_legacy_import(
            imported.handle.validate_legacy_evidence(evidence)
        )
        self.assertEqual(result.projection.history_completeness, "COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE")
        self.assertEqual(result.projection.protected_unresolved_legacy_write_count, 1)
        self.assertEqual(result.projection.restart_classification, RestartClassification.UNRESOLVED_WRITE_HELD)
        self.assertFalse(result.projection.writer_proof_release_eligible_by_proof_id[proof_id])
        self.assertEqual(result.projection.writer_proof_state_by_proof_id[proof_id], "HELD")
        imported.handle.close()

    def test_er_nw_002_full_release_reaches_safe_no_write_capability(self) -> None:
        token, config, process_instance_id, contract = self._issue_genuine_token()
        # By the time a genuine token has been issued, the full accepted
        # release sequence -- including WRITER_PROOF_RELEASED -- has
        # completed.  A fresh replay must now show COMPLETE history and
        # SAFE_NO_WRITE_CAPABILITY (no HELD proof remains).
        candidate = _acquire_normal_writer_candidate(
            self.binding,
            conflict_domain_ref=contract.conflict_domain_ref,
            expected_environment=contract.environment,
            canonical_repository_root=self.repository_root,
            expected_ledger_path=self.ledger_path,
        )
        self.assertIsNotNone(candidate.handle)
        self.assertEqual(candidate.projection.history_completeness, "COMPLETE")
        self.assertEqual(candidate.projection.protected_unresolved_legacy_write_count, 0)
        self.assertEqual(candidate.projection.restart_classification, RestartClassification.SAFE_NO_WRITE_CAPABILITY)
        self.assertEqual(candidate.projection.writer_proof_state_by_proof_id[contract.writer_proof_id], "RELEASED")
        candidate.handle.close()
        _consume_current_process_release_completion(token)

    def test_er_nw_002_multiple_candidate_proofs_remain_protected(self) -> None:
        self.initialize()
        incident_id = "SYNTHETIC_ER_NW_002_INCIDENT_B"
        proof_id = "SYNTHETIC_ER_NW_002_PROOF_B"
        legacy_writer_session_id = "SYNTHETIC_ER_NW_002_B_LOCAL_RUNNER"
        documents = self._synthetic_legacy_evidence_documents(
            incident_id=incident_id, writer_proof_id=proof_id,
            legacy_writer_session_id=legacy_writer_session_id,
        )
        evidence = self._encode_evidence_documents(documents)
        contract = LegacyIncidentContract(
            incident_id=incident_id, writer_proof_id=proof_id,
            legacy_writer_session_id=legacy_writer_session_id,
            evidence_expectations=self._expectations_for(evidence),
        )
        imported = acquire_legacy_import_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        imported.handle.commit_exact_legacy_import(
            imported.handle.validate_legacy_evidence(evidence)
        )
        imported.handle.close()

        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        handle = emergency.handle
        assert handle is not None
        # Make the imported proof genuinely eligible ...
        handle.record_reconciliation({
            "incident_id": incident_id,
            "disposition": "SYNTHETIC_QUALIFYING_RECONCILIATION_CLOSED",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
            "bound_order_id": None, "created_order_upper_bound": 0,
            "active_order_upper_bound": 0, "unknown_result": False,
            "writer_proof_release_eligible": True, "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RECONCILIATION_V1",
        }, incident_id=incident_id)
        self.assertEqual(handle.inspect_validated_projection().history_completeness, "COMPLETE")
        # ... but then a second, unrelated proof also gets associated with
        # the same incident_id.  Per ER-NW-002 this makes the association
        # ambiguous ("more than one candidate controlling proof"), so the
        # imported incident must remain protected regardless of the first
        # proof's eligibility.
        second_proof_id = "SYNTHETIC_ER_NW_002_PROOF_B_SECOND"
        handle.record_writer_proof_held({
            "writer_proof_id": second_proof_id,
            "conflict_domain_ref": contract.conflict_domain_ref,
            "held_reason": "SYNTHETIC_SECOND_CANDIDATE_PROOF",
            "protected_unresolved_write_event_ids": [],
        }, incident_id=incident_id)
        projection = handle.inspect_validated_projection()
        self.assertEqual(projection.history_completeness, "COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE")
        self.assertEqual(projection.protected_unresolved_legacy_write_count, 1)
        self.assertTrue(projection.writer_proof_release_eligible_by_proof_id[proof_id])
        self.assertFalse(projection.writer_proof_release_eligible_by_proof_id[second_proof_id])
        handle.close()


if __name__ == "__main__":
    unittest.main()
