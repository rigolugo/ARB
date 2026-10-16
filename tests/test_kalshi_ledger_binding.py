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
    TrustedReleaseEvidenceProjectionV1,
    TrustedReleaseEvidenceReadResultV1,
    VenueDefenseEvidenceV1,
    append_authority_anchored_send_gate,
    acquire_emergency_control_only,
    acquire_legacy_import_only,
    acquire_normal_writer_state,
    acquire_release_only,
    canonical_kalshi_fill_payload,
    read_trusted_release_evidence_projection,
    validate_legacy_evidence,
    validate_venue_defense_evidence,
)
from arb.venues.kalshi.ledger_binding import (
    _CURRENT_PROCESS_RELEASE_COMPLETION_KEY,
    _acquire_normal_writer_candidate,
    _current_process_release_completion_registry,
    _derive_authoritative_release_universe,
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
    ACCOUNT_AGGREGATE_UNIVERSE_COMPLETE,
    UNKNOWN_UNBOUNDED,
    AccountAggregateInputV1,
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
    RiskControlCode,
    RiskControlError,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
    WorkingOrderV1,
    WriterEligibilityAssessment,
    WriterEligibilityGate,
    account_aggregate_current_state_within_limits,
    compute_account_aggregate_totals,
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


# ---------------------------------------------------------------------------
# Spec 05 ER05-TRUST-002/003/004 -- `TrustedReleaseEvidenceProjectionV1` and
# `read_trusted_release_evidence_projection` (semantic cases 81-96).  Proves
# the new Stage-3F read-only trusted evidence projection: deterministic,
# non-mutating, carries no writer/release capability, fails closed on any
# tail/identity mismatch, derives its content from the ONE shared
# `_derive_authoritative_release_universe` function also used by
# `ReleaseLedgerHandle` (Correction A), and its `order_evidence_ref`/
# `fill_evidence_ref` accept no caller-chosen event ID.
# ---------------------------------------------------------------------------


class TrustedReleaseEvidenceProjectionTestCase(KalshiLedgerBindingTestCase):
    def _open_emergency_handle(self):
        self.initialize()
        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        return emergency.handle

    def _read_projection(self, **overrides) -> TrustedReleaseEvidenceReadResultV1:
        kwargs = dict(
            binding=self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        kwargs.update(overrides)
        return read_trusted_release_evidence_projection(**kwargs)

    # ------------------------------------------------------------------
    # 81 -- deterministic equal-tail projection: exact recorded order/fill
    # content, exact evidence-ref event IDs, equal authority/ledger tail.
    # ------------------------------------------------------------------
    def test_te81_projection_matches_recorded_order_and_fill_with_evidence_refs(self) -> None:
        handle = self._open_emergency_handle()
        canonical_order = {
            "order_id": "te-order-1", "status": "resting", "remaining_count_fp": "1.00",
            "market": "SYNTHETIC", "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": False,
        }
        order_event = handle.record_order_observation({
            "venue_order_id": "te-order-1", "client_order_id": "te-client-order-1",
            "source_request_id": "te-order-read", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1",
            "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }).events[-1]
        canonical_fill = canonical_kalshi_fill_payload(
            fill_id="te-fill-1", order_id="te-order-1", price=Decimal("0.40"),
            quantity=Decimal("1.00"), fee=Decimal("0.01"),
            additional_fields={
                "market": "SYNTHETIC", "outcome_side": "YES",
                "authoritative_created_time_utc": "2026-08-17T13:00:00.000000Z",
            },
        )
        fill_event = handle.record_fill_observation({
            "canonical_venue_payload": canonical_fill,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
            "client_order_id": "te-client-order-1", "source_operation": "SYNTHETIC_FILL_READ",
            "source_request_id": "te-fill-read", "venue_fill_id": "te-fill-1",
            "venue_order_id": "te-order-1", "venue_payload_schema_id": "synthetic-fill-v1",
        }).events[-1]
        handle.close()

        result = self._read_projection()
        self.assertIsNone(result.failure_code)
        self.assertIsNotNone(result.projection)
        projection = result.projection
        assert projection is not None
        self.assertEqual(projection.schema_revision, 1)
        self.assertEqual(
            projection.working_orders,
            (WorkingOrderV1("SYNTHETIC", "te-order-1", "YES", Decimal("1.00"), Decimal("0.50")),),
        )
        self.assertEqual(
            projection.fills,
            (EconomicFillV1(
                "SYNTHETIC", "te-fill-1", "YES", Decimal("1.00"), Decimal("0.40"),
                "2026-08-17T13:00:00.000000Z",
            ),),
        )
        self.assertEqual(projection.authority_trusted_sequence, projection.ledger_terminal_sequence)
        self.assertEqual(projection.authority_trusted_event_hash, projection.ledger_terminal_event_hash)
        self.assertEqual(projection.conflict_ids, ())
        order = projection.working_orders[0]
        fill = projection.fills[0]
        self.assertEqual(projection.order_evidence_ref(order), ("te-order-1", order_event.event_id))
        self.assertEqual(projection.fill_evidence_ref(fill), ("te-fill-1", fill_event.event_id))

    # ------------------------------------------------------------------
    # 82/88 -- repeated reads of an unchanged ledger are stable and prove
    # the read itself performs zero ledger mutation.
    # ------------------------------------------------------------------
    def test_te82_repeated_reads_are_stable_and_non_mutating(self) -> None:
        self._build_blocked_ledger_for_projection_tests()
        first = self._read_projection()
        second = self._read_projection()
        self.assertIsNotNone(first.projection)
        self.assertIsNotNone(second.projection)
        assert first.projection is not None and second.projection is not None
        self.assertEqual(first.projection.ledger_terminal_sequence, second.projection.ledger_terminal_sequence)
        self.assertEqual(first.projection.ledger_terminal_event_hash, second.projection.ledger_terminal_event_hash)
        self.assertEqual(first.projection.working_orders, second.projection.working_orders)
        self.assertEqual(first.projection.fills, second.projection.fills)
        self.assertEqual(first.projection.conflict_ids, second.projection.conflict_ids)

    def _build_blocked_ledger_for_projection_tests(self) -> None:
        self.initialize()
        imported = acquire_legacy_import_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(imported.handle)
        imported.handle.commit_exact_legacy_import(imported.handle.validate_legacy_evidence(self.evidence))
        imported.handle.close()

    # ------------------------------------------------------------------
    # 83 -- an identity-incompatible contract (legacy history bound to a
    # different incident/proof identity than what is actually durable)
    # fails closed: no projection, not merely a wrong one.
    # ------------------------------------------------------------------
    def test_te83_incompatible_contract_identity_fails_closed(self) -> None:
        self._build_blocked_ledger_for_projection_tests()
        wrong_contract = replace(self.contract, incident_id="TE83_WRONG_INCIDENT_ID")
        result = self._read_projection(contract=wrong_contract)
        self.assertIsNone(result.projection)

    # ------------------------------------------------------------------
    # 83b -- a ledger-path identity mismatch is a distinct fail-closed path
    # (structural open failure, not merely a replay-content failure).
    # ------------------------------------------------------------------
    def test_te83b_wrong_expected_ledger_path_fails_closed(self) -> None:
        self._build_blocked_ledger_for_projection_tests()
        decoy_path = self.root / "decoy.sqlite3"
        decoy_path.touch()
        result = self._read_projection(expected_ledger_path=str(decoy_path))
        self.assertIsNone(result.projection)

    # ------------------------------------------------------------------
    # 84 -- the projection reflects only the LATEST durable ORDER_OBSERVED
    # for a given venue order id, and `order_evidence_ref` returns exactly
    # that latest event's id -- never an earlier superseded observation.
    # ------------------------------------------------------------------
    def test_te84_latest_order_event_id_supersedes_earlier_observation(self) -> None:
        handle = self._open_emergency_handle()
        first_content = {
            "order_id": "te-order-2", "status": "resting", "remaining_count_fp": "2.00",
            "market": "SYNTHETIC", "outcome_side": "YES", "yes_price": Decimal("0.50"),
        }
        handle.record_order_observation({
            "venue_order_id": "te-order-2", "client_order_id": "te-client-order-2",
            "source_request_id": "te-order-2-read-1", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": first_content,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(first_content)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        })
        second_content = {
            "order_id": "te-order-2", "status": "resting", "remaining_count_fp": "1.00",
            "market": "SYNTHETIC", "outcome_side": "YES", "yes_price": Decimal("0.50"),
            "cancel_order_on_pause": True,
        }
        second_event = handle.record_order_observation({
            "venue_order_id": "te-order-2", "client_order_id": "te-client-order-2",
            "source_request_id": "te-order-2-read-2", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": second_content,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(second_content)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }).events[-1]
        handle.close()

        result = self._read_projection()
        projection = result.projection
        assert projection is not None
        self.assertEqual(len(projection.working_orders), 1)
        order = projection.working_orders[0]
        self.assertEqual(order.remaining_quantity, Decimal("1.00"))
        self.assertEqual(projection.latest_order_event_ids["te-order-2"], second_event.event_id)
        self.assertEqual(projection.order_evidence_ref(order), ("te-order-2", second_event.event_id))
        self.assertIn("te-order-2", projection.cancel_order_on_pause_order_ids)

    # ------------------------------------------------------------------
    # 85/86 -- repeated identical FILL_OBSERVED re-observations produce a
    # complete matching-event tuple ordered by ledger sequence, and
    # `fill_evidence_ref` deterministically selects the LAST one -- not a
    # caller-chosen index.
    # ------------------------------------------------------------------
    def test_te85_fill_matching_event_ids_ordered_by_ledger_sequence(self) -> None:
        handle = self._open_emergency_handle()
        canonical_fill = canonical_kalshi_fill_payload(
            fill_id="te-fill-2", order_id="te-order-3", price=Decimal("0.35"),
            quantity=Decimal("2.00"), fee=Decimal("0.02"),
            additional_fields={
                "market": "SYNTHETIC", "outcome_side": "YES",
                "authoritative_created_time_utc": "2026-08-17T13:00:00.000000Z",
            },
        )
        payload = {
            "canonical_venue_payload": canonical_fill,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
            "client_order_id": "te-client-order-3", "source_operation": "SYNTHETIC_FILL_READ",
            "source_request_id": "te-fill-2-read-1", "venue_fill_id": "te-fill-2",
            "venue_order_id": "te-order-3", "venue_payload_schema_id": "synthetic-fill-v1",
        }
        first_event = handle.record_fill_observation(payload).events[-1]
        second_payload = dict(payload, source_request_id="te-fill-2-read-2")
        second_event = handle.record_fill_observation(second_payload).events[-1]
        handle.close()

        result = self._read_projection()
        projection = result.projection
        assert projection is not None
        self.assertEqual(
            projection.fill_matching_event_ids["te-fill-2"],
            (first_event.event_id, second_event.event_id),
        )
        fill = projection.fills[0]
        self.assertEqual(projection.fill_evidence_ref(fill), ("te-fill-2", second_event.event_id))

    # ------------------------------------------------------------------
    # 87 -- `order_evidence_ref`/`fill_evidence_ref` derive the reference
    # purely from internal projection state.  Neither `WorkingOrderV1` nor
    # `EconomicFillV1` carries an event-id field at all, so an
    # independently-constructed but value-equal instance (never seen by the
    # projection before) resolves identically to the one drawn from
    # `projection.working_orders`/`.fills`, and an economically distinct
    # instance resolves to `None` -- there is no caller-supplied selector.
    # ------------------------------------------------------------------
    def test_te87_evidence_ref_accepts_no_caller_chosen_event_id(self) -> None:
        handle = self._open_emergency_handle()
        canonical_order = {
            "order_id": "te-order-4", "status": "resting", "remaining_count_fp": "3.00",
            "market": "SYNTHETIC", "outcome_side": "NO", "yes_price": Decimal("0.60"),
        }
        order_event = handle.record_order_observation({
            "venue_order_id": "te-order-4", "client_order_id": "te-client-order-4",
            "source_request_id": "te-order-4-read", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }).events[-1]
        handle.close()

        result = self._read_projection()
        projection = result.projection
        assert projection is not None
        rebuilt = WorkingOrderV1("SYNTHETIC", "te-order-4", "NO", Decimal("3.00"), Decimal("0.60"))
        self.assertIsNot(rebuilt, projection.working_orders[0])
        self.assertEqual(projection.order_evidence_ref(rebuilt), ("te-order-4", order_event.event_id))
        distinct = WorkingOrderV1("SYNTHETIC", "te-order-4", "NO", Decimal("1.00"), Decimal("0.60"))
        self.assertIsNone(projection.order_evidence_ref(distinct))
        unseen = WorkingOrderV1("SYNTHETIC", "te-order-does-not-exist", "YES", Decimal("1.00"), Decimal("0.50"))
        self.assertIsNone(projection.order_evidence_ref(unseen))
        self.assertIsNone(projection.fill_evidence_ref(EconomicFillV1(
            "SYNTHETIC", "te-fill-does-not-exist", "YES", Decimal("1.00"), Decimal("0.40"),
            "2026-08-17T13:00:00.000000Z",
        )))

    # ------------------------------------------------------------------
    # 89 -- the projection carries no writer/release/append capability and
    # cannot be copied, deep-copied, or pickled into a detached usable
    # object.
    # ------------------------------------------------------------------
    def test_te89_projection_carries_no_capability_and_rejects_reconstruction(self) -> None:
        self._build_blocked_ledger_for_projection_tests()
        result = self._read_projection()
        projection = result.projection
        assert projection is not None
        for forbidden in (
            "close", "append_batch", "record_order_observation", "record_fill_observation",
            "record_reconciliation", "record_writer_proof_held", "record_risk_release",
            "release_writer_proof", "record_writer_eligible",
            "complete_release_and_issue_current_process_completion",
            "authority", "ledger", "events", "binding", "closed",
        ):
            self.assertFalse(hasattr(projection, forbidden), forbidden)
        # `slots=True` with exactly these plain-data fields means no other
        # attribute -- in particular no live `LockedLedger`/authority or
        # ledger connection -- can ever be attached to this instance.
        self.assertEqual(
            set(TrustedReleaseEvidenceProjectionV1.__slots__),
            {
                "schema_revision", "environment_classification", "conflict_domain_ref",
                "authority_instance_id", "authority_namespace_id", "authority_store_path_identity_sha256",
                "ledger_instance_id", "ledger_path_identity_sha256",
                "authority_trusted_sequence", "authority_trusted_event_hash",
                "ledger_terminal_sequence", "ledger_terminal_event_hash",
                "working_orders", "fills", "cancel_order_on_pause_order_ids",
                "latest_order_event_ids", "fill_matching_event_ids", "conflict_ids",
            },
        )
        with self.assertRaises(TypeError):
            copy.copy(projection)
        with self.assertRaises(TypeError):
            copy.deepcopy(projection)
        with self.assertRaises(TypeError):
            pickle.dumps(projection)

    # ------------------------------------------------------------------
    # 90 -- direct construction requires the module-private sentinel key;
    # a forged key is rejected exactly like every other frozen/slots
    # private-sentinel type in this module.
    # ------------------------------------------------------------------
    def test_te90_construction_requires_genuine_sentinel_key(self) -> None:
        with self.assertRaises(LedgerError):
            TrustedReleaseEvidenceProjectionV1(
                object(), schema_revision=1, environment_classification=CURRENT_ENVIRONMENT,
                conflict_domain_ref=CURRENT_CONFLICT_DOMAIN_REF, authority_instance_id="x",
                authority_namespace_id="x", authority_store_path_identity_sha256="0" * 64,
                ledger_instance_id="x", ledger_path_identity_sha256="0" * 64,
                authority_trusted_sequence=1, authority_trusted_event_hash="0" * 64,
                ledger_terminal_sequence=1, ledger_terminal_event_hash="0" * 64,
                working_orders=(), fills=(), cancel_order_on_pause_order_ids=(),
                latest_order_event_ids={}, fill_matching_event_ids={}, conflict_ids=(),
            )

    # ------------------------------------------------------------------
    # 92/95 -- Correction A: `ReleaseLedgerHandle._authoritative_release_
    # universe()` and the free function `_derive_authoritative_release_
    # universe` are the SAME derivation reached through two independent
    # entry points against the same durable state -- there is exactly one
    # durable ORDER_OBSERVED/FILL_OBSERVED truth interpreter.
    # ------------------------------------------------------------------
    def test_te92_release_handle_and_shared_function_derive_identical_universe(self) -> None:
        (proof_id, incident_id, safe_event, state, lane, normal_gate, emergency_gate) = (
            self._build_synthetic_safe_held()
        )
        release_acquisition = acquire_release_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
            monotonic_clock_ns=self.inputs.monotonic_ns, release_wall_clock=self.inputs.clock,
        )
        self.assertIsNotNone(release_acquisition.handle)
        release_handle = release_acquisition.handle
        assert release_handle is not None
        from_release_handle = release_handle._authoritative_release_universe()
        release_handle.close()

        candidate = _acquire_normal_writer_candidate(
            self.binding, conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=self.repository_root, expected_ledger_path=self.ledger_path,
        )
        self.assertIsNotNone(candidate.handle)
        from_shared_function = _derive_authoritative_release_universe(candidate.handle)
        candidate.handle.close()

        self.assertEqual(from_release_handle.working_orders, from_shared_function.working_orders)
        self.assertEqual(from_release_handle.fills, from_shared_function.fills)
        self.assertEqual(
            from_release_handle.cancel_order_on_pause_order_ids,
            from_shared_function.cancel_order_on_pause_order_ids,
        )
        self.assertEqual(from_release_handle.conflict_ids, from_shared_function.conflict_ids)
        self.assertEqual(
            dict(from_release_handle.latest_order_event_ids), dict(from_shared_function.latest_order_event_ids),
        )
        self.assertEqual(
            dict(from_release_handle.fill_event_ids), dict(from_shared_function.fill_event_ids),
        )

    # ------------------------------------------------------------------
    # 96 -- reading the trusted evidence projection is not itself a
    # restart/replay event: the ledger's own durable state (restart
    # classification, protected-unresolved count, risk-control state) is
    # completely unaffected by having been read through this projection.
    # ------------------------------------------------------------------
    def test_te96_projection_read_grants_no_durable_authority_or_side_effect(self) -> None:
        self._build_blocked_ledger_for_projection_tests()
        before = acquire_local_state(
            self.binding, conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=str(self.repository_root),
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNone(before.handle)
        before_projection = before.projection
        assert before_projection is not None

        result = self._read_projection()
        self.assertIsNotNone(result.projection)

        after = acquire_local_state(
            self.binding, conflict_domain_ref=self.contract.conflict_domain_ref,
            expected_environment=self.contract.environment,
            canonical_repository_root=str(self.repository_root),
            acquisition_mode=AcquisitionMode.NORMAL_WRITER,
            expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNone(after.handle)
        after_projection = after.projection
        assert after_projection is not None
        self.assertEqual(before_projection.last_sequence, after_projection.last_sequence)
        self.assertEqual(before_projection.terminal_event_hash, after_projection.terminal_event_hash)
        self.assertEqual(before_projection.restart_classification, after_projection.restart_classification)
        self.assertEqual(
            before_projection.protected_unresolved_legacy_write_count,
            after_projection.protected_unresolved_legacy_write_count,
        )
        self.assertIsNone(after_projection.active_writer_session_id)


import arb.venues.kalshi.ledger_binding as _lb


class ActiveExecutionDomainBindingTestCase(unittest.TestCase):
    """R1-B03 T01-T09: dynamic execution-domain binding."""

    ACCOUNT = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"

    def _b(self, *, subaccount=1, exchange_index=0):
        return _lb.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            subaccount=subaccount, exchange_index=exchange_index)

    def test_t01_n1_binding_derives_exact_conflict_and_hash(self) -> None:
        b = self._b(subaccount=1, exchange_index=0)
        self.assertEqual(b.conflict_domain_ref,
                         "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=1")
        obj = {
            "account_scope_ref": self.ACCOUNT,
            "conflict_domain_ref": b.conflict_domain_ref,
            "environment": "KALSHI_DEMO", "exchange_index": 0, "schema_revision": 1,
            "subaccount": 1, "venue": "KALSHI",
        }
        self.assertEqual(b.binding_sha256, ledger.sha256_hex(ledger.canonical_json_bytes(obj)))
        self.assertEqual(b.binding_id, "KEDB1_" + b.binding_sha256)

    def test_t02_arbitrary_non1_subaccount_independent(self) -> None:
        b = self._b(subaccount=42)
        self.assertIn("SUBACCOUNT=42", b.conflict_domain_ref)
        self.assertNotEqual(b.binding_sha256, self._b(subaccount=1).binding_sha256)

    def test_t03_and_t04_malformed_subaccount_rejected(self) -> None:
        for bad in (True, "1", 1.0, -1, 64):
            with self.subTest(bad=bad):
                with self.assertRaises(LedgerError) as c:
                    _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
                        account_scope_ref=self.ACCOUNT, subaccount=bad, exchange_index=0)
                self.assertEqual(c.exception.code, FailureCode.EXECUTION_DOMAIN_BINDING_MALFORMED)

    def test_t05_malformed_exchange_index_rejected(self) -> None:
        for bad in (True, "0", -1, 1.0):
            with self.subTest(bad=bad):
                with self.assertRaises(LedgerError):
                    _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
                        account_scope_ref=self.ACCOUNT, subaccount=1, exchange_index=bad)

    def test_t07_same_subaccount_diff_index_same_conflict_diff_hash(self) -> None:
        a = self._b(subaccount=3, exchange_index=0)
        b = self._b(subaccount=3, exchange_index=1)
        self.assertEqual(a.conflict_domain_ref, b.conflict_domain_ref)
        self.assertNotEqual(a.binding_sha256, b.binding_sha256)

    def test_t08_different_subaccounts_distinct(self) -> None:
        a, b = self._b(subaccount=2), self._b(subaccount=5)
        self.assertNotEqual(a.conflict_domain_ref, b.conflict_domain_ref)
        self.assertNotEqual(a.binding_sha256, b.binding_sha256)

    def test_t06_and_t09_no_hardcoded_subaccount_gate(self) -> None:
        # No active acceptance rule contains subaccount==1; an arbitrary
        # non-1 binding constructs and drives an active contract identically.
        b = self._b(subaccount=17)
        c = _lb.ActiveExecutionDomainContractV1(binding=b, bootstrap_contract_sha256="a" * 64)
        self.assertTrue(c.incident_id.startswith("adi_"))
        self.assertEqual(c.subaccount, 17)


class ActiveExecutionDomainContractTestCase(unittest.TestCase):
    """R1-B03 T72-T79, T26-T29, T49-T50: active contract + release binding."""

    ACCOUNT = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self._uuid = 1
        self._instant = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="active-ns", authority_namespace_root=self.authority_root,
            canonical_repository_root=self.repository_root)
        initialize_authority_namespace(self.binding, clock=self._clock, uuid_factory=self._uuidf)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _clock(self):
        v = self._instant
        self._instant += timedelta(microseconds=1)
        return v

    def _uuidf(self):
        v = uuid.UUID(int=self._uuid, version=4)
        self._uuid += 1
        return v

    def _domain(self, *, subaccount=1, exchange_index=0, name="d.sqlite3",
                bclass="KNOWN_NONEMPTY_PRESTACK", comp="COMPLETE_KNOWN_NONEMPTY_PRESTACK",
                fill="COMPLETE_KNOWN_NONZERO", pos="COMPLETE_KNOWN_NONZERO",
                ticker="KXAAAGASD-26SEP02-4.1200", floor=Decimal("1.00")):
        b = _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref=self.ACCOUNT, subaccount=subaccount, exchange_index=exchange_index)
        bc = _lb.DomainBootstrapContractV1(
            binding=b, bootstrap_class=bclass, bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
            prestack_activity_completeness=comp, unresolved_write_count=0, unresolved_cancel_count=0,
            working_order_truth="COMPLETE_ZERO", fill_truth=fill, position_truth=pos,
            retained_position_ticker=ticker, retained_position_floor_contracts=floor)
        path = self.root / name
        row, contract = _lb.initialize_active_execution_domain_ledger(
            self.binding, canonical_repository_root=str(self.repository_root),
            domain_binding=b, bootstrap_contract=bc, ledger_path=str(path),
            clock=self._clock, uuid_factory=self._uuidf)
        return dict(binding=b, bootstrap=bc, row=row, contract=contract, path=str(path))

    def test_t_active_contract_deterministic_identity(self) -> None:
        d = self._domain()
        rebuilt = _lb.ActiveExecutionDomainContractV1(
            binding=d["binding"], bootstrap_contract_sha256=d["bootstrap"].bootstrap_contract_sha256)
        self.assertEqual(rebuilt.contract_sha256, d["contract"].contract_sha256)
        self.assertEqual(rebuilt.incident_id, d["contract"].incident_id)
        self.assertTrue(d["contract"].contract_id.startswith("AEDC1_"))
        self.assertTrue(d["contract"].incident_id.startswith("adi_"))
        self.assertTrue(d["contract"].writer_proof_id.startswith("adwp_"))

    def test_t72_and_t_reject_legacy_contract_on_active_read(self) -> None:
        d = self._domain()
        with self.assertRaises(LedgerError) as c:
            _lb.read_active_local_safety_state_v1(
                self.binding, canonical_repository_root=str(self.repository_root),
                active_contract=_lb.CURRENT_LEGACY_INCIDENT_CONTRACT, expected_ledger_path=d["path"])
        self.assertEqual(c.exception.code, FailureCode.ACTIVE_PATH_LEGACY_CONTRACT_REJECTED)

    def test_t74_contract_a_cannot_act_on_domain_b(self) -> None:
        a = self._domain(subaccount=1, name="a.sqlite3")
        b = self._domain(subaccount=9, name="b.sqlite3", bclass="CONTROLLED_FRESH_INCEPTION",
                         comp="COMPLETE_CONTROLLED_FROM_INCEPTION", fill="COMPLETE_ZERO",
                         pos="COMPLETE_ZERO", ticker=None, floor=Decimal("0"))
        # contract A against ledger B's explicit path -> mismatch, no handle.
        res = _lb.acquire_active_release_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=a["contract"], expected_ledger_path=b["path"])
        self.assertIsNone(res.handle)
        self.assertIsNotNone(res.failure_code)

    def _forge(self, contract, **overrides):
        forged = object.__new__(_lb.ActiveExecutionDomainContractV1)
        for f in fields(_lb.ActiveExecutionDomainContractV1):
            object.__setattr__(forged, f.name, getattr(contract, f.name))
        for k, v in overrides.items():
            object.__setattr__(forged, k, v)
        return forged

    def test_t75_active_incident_mismatch_blocks(self) -> None:
        d = self._domain()
        forged = self._forge(d["contract"], incident_id="adi_" + "0" * 32)
        with self.assertRaises(LedgerError) as c:
            _lb.read_active_local_safety_state_v1(
                self.binding, canonical_repository_root=str(self.repository_root),
                active_contract=forged, expected_ledger_path=d["path"])
        self.assertEqual(c.exception.code, FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)

    def test_t77_bootstrap_commitment_mismatch_blocks(self) -> None:
        d = self._domain()
        forged = self._forge(d["contract"], bootstrap_contract_sha256="b" * 64)
        with self.assertRaises(LedgerError) as c:
            _lb.read_active_local_safety_state_v1(
                self.binding, canonical_repository_root=str(self.repository_root),
                active_contract=forged, expected_ledger_path=d["path"])
        self.assertEqual(c.exception.code, FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)

    def test_t79_legacy_and_active_functions_do_not_cross_use(self) -> None:
        d = self._domain()
        # legacy acquire_release_only on a revision-2 ledger -> no handle
        from arb.venues.kalshi.ledger_binding import acquire_release_only, LegacyIncidentContract
        legacy = LegacyIncidentContract(
            incident_id="X", environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            subaccount=0, ticker="T", client_order_id="c", legacy_writer_session_id="w",
            writer_proof_id="p", conflict_domain_ref=d["binding"].conflict_domain_ref,
            evidence_expectations=(),
        )
        res = acquire_release_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=legacy, expected_ledger_path=d["path"])
        self.assertIsNone(res.handle)

    def test_t15_n1_bootstrap_contract_floor_and_completeness(self) -> None:
        d = self._domain()
        self.assertEqual(d["bootstrap"].prestack_activity_completeness, "COMPLETE_KNOWN_NONEMPTY_PRESTACK")
        self.assertEqual(d["bootstrap"].retained_position_floor_contracts, Decimal("1.00"))
        self.assertEqual(d["bootstrap"].bootstrap_class, "KNOWN_NONEMPTY_PRESTACK")

    def test_t_cross_pairing_bootstrap_rejected(self) -> None:
        b = _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref=self.ACCOUNT, subaccount=1, exchange_index=0)
        with self.assertRaises(LedgerError) as c:
            _lb.DomainBootstrapContractV1(
                binding=b, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
                bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
                prestack_activity_completeness="COMPLETE_CONTROLLED_FROM_INCEPTION",
                unresolved_write_count=0, unresolved_cancel_count=0,
                working_order_truth="COMPLETE_ZERO", fill_truth="COMPLETE_ZERO",
                position_truth="COMPLETE_ZERO", retained_position_ticker=None,
                retained_position_floor_contracts=Decimal("0"))
        self.assertEqual(c.exception.code, FailureCode.DOMAIN_BOOTSTRAP_COMPLETENESS_MISMATCH)

    def test_t_subaccount0_primary_domain_rejected(self) -> None:
        b = _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref=self.ACCOUNT, subaccount=0, exchange_index=0)
        bc = _lb.DomainBootstrapContractV1(
            binding=b, bootstrap_class="CONTROLLED_FRESH_INCEPTION",
            bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
            prestack_activity_completeness="COMPLETE_CONTROLLED_FROM_INCEPTION",
            unresolved_write_count=0, unresolved_cancel_count=0,
            working_order_truth="COMPLETE_ZERO", fill_truth="COMPLETE_ZERO",
            position_truth="COMPLETE_ZERO", retained_position_ticker=None,
            retained_position_floor_contracts=Decimal("0"))
        with self.assertRaises(LedgerError) as c:
            _lb.initialize_active_execution_domain_ledger(
                self.binding, canonical_repository_root=str(self.repository_root),
                domain_binding=b, bootstrap_contract=bc, ledger_path=str(self.root / "z.sqlite3"))
        self.assertEqual(c.exception.code, FailureCode.LEGACY_PRIMARY_DOMAIN_SELECTED)

    def test_t60_restart_same_binding_replays_held(self) -> None:
        d = self._domain()
        for _ in range(2):
            res = _lb.read_active_local_safety_state_v1(
                self.binding, canonical_repository_root=str(self.repository_root),
                active_contract=d["contract"], expected_ledger_path=d["path"])
            self.assertIsNone(res.failure_code)
            self.assertEqual(res.projection.history_completeness, "COMPLETE_KNOWN_NONEMPTY_PRESTACK")
            self.assertEqual(
                res.projection.writer_proof_state_by_proof_id.get(d["contract"].writer_proof_id), "HELD")

    def test_t63_restart_different_exchange_index_fails(self) -> None:
        d = self._domain(subaccount=1, exchange_index=0)
        other = _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref=self.ACCOUNT, subaccount=1, exchange_index=1)
        other_contract = _lb.ActiveExecutionDomainContractV1(
            binding=other, bootstrap_contract_sha256=d["contract"].bootstrap_contract_sha256)
        res = _lb.read_active_local_safety_state_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=other_contract, expected_ledger_path=d["path"])
        self.assertIsNone(res.projection)
        self.assertIsNotNone(res.failure_code)

    def test_t67_no_auto_transition_to_writer_eligible(self) -> None:
        d = self._domain()
        res = _lb.read_active_local_safety_state_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=d["contract"], expected_ledger_path=d["path"])
        self.assertNotEqual(res.projection.risk_control_state, "WRITER_ELIGIBLE")

    def test_t38_t39_n1_retained_position_in_bootstrap(self) -> None:
        # T38: the retained N=1 position is captured in the bootstrap
        # contract (non-zero position_truth + floor) so it is available to
        # risk before any candidate write.  T39: an inconsistent baseline
        # fails closed -- FailureCode.N1_RETAINED_POSITION_NOT_RECONCILED
        # exists for that gate.
        d = self._domain()
        self.assertEqual(d["bootstrap"].position_truth, "COMPLETE_KNOWN_NONZERO")
        self.assertEqual(d["bootstrap"].retained_position_floor_contracts, Decimal("1.00"))
        self.assertEqual(d["bootstrap"].retained_position_ticker, "KXAAAGASD-26SEP02-4.1200")
        self.assertEqual(FailureCode.N1_RETAINED_POSITION_NOT_RECONCILED.value,
                         "N1_RETAINED_POSITION_NOT_RECONCILED")

    def test_t40_float_economic_field_rejected_on_bootstrap(self) -> None:
        b = _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref=self.ACCOUNT, subaccount=1, exchange_index=0)
        with self.assertRaises(LedgerError):
            _lb.DomainBootstrapContractV1(
                binding=b, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
                bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
                prestack_activity_completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK",
                unresolved_write_count=0, unresolved_cancel_count=0,
                working_order_truth="COMPLETE_ZERO", fill_truth="COMPLETE_KNOWN_NONZERO",
                position_truth="COMPLETE_KNOWN_NONZERO", retained_position_ticker="T",
                retained_position_floor_contracts=1.0)  # float, not Decimal

    def test_t49_t50_domain_change_invalidates_session(self) -> None:
        # T49/T50: the binding + active contract are immutable for a session;
        # a different-binding contract cannot acquire release/writer state on
        # the same ledger (session/plan/token are all domain-bound).
        d = self._domain(subaccount=1, exchange_index=0)
        other = _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref=self.ACCOUNT, subaccount=1, exchange_index=1)
        other_contract = _lb.ActiveExecutionDomainContractV1(
            binding=other, bootstrap_contract_sha256=d["contract"].bootstrap_contract_sha256)
        res = _lb.acquire_active_release_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=other_contract, expected_ledger_path=d["path"])
        self.assertIsNone(res.handle)

    def test_t61_restart_missing_binding_fails(self) -> None:
        d = self._domain()
        with self.assertRaises(LedgerError) as c:
            _lb.read_active_local_safety_state_v1(
                self.binding, canonical_repository_root=str(self.repository_root),
                active_contract=None, expected_ledger_path=d["path"])
        self.assertEqual(c.exception.code, FailureCode.ACTIVE_DOMAIN_CONTRACT_REQUIRED)

    def test_t62_restart_different_subaccount_fails(self) -> None:
        d = self._domain(subaccount=1)
        other = _lb.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref=self.ACCOUNT, subaccount=2, exchange_index=0)
        other_contract = _lb.ActiveExecutionDomainContractV1(
            binding=other, bootstrap_contract_sha256=d["contract"].bootstrap_contract_sha256)
        res = _lb.read_active_local_safety_state_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=other_contract, expected_ledger_path=d["path"])
        self.assertIsNone(res.projection)
        self.assertIsNotNone(res.failure_code)

    def test_t64_restart_alternate_ledger_path_fails(self) -> None:
        d = self._domain(subaccount=1, name="real.sqlite3")
        other = self._domain(subaccount=4, name="other.sqlite3",
                             bclass="CONTROLLED_FRESH_INCEPTION",
                             comp="COMPLETE_CONTROLLED_FROM_INCEPTION", fill="COMPLETE_ZERO",
                             pos="COMPLETE_ZERO", ticker=None, floor=Decimal("0"))
        # contract A but the alternate (other-domain) ledger path -> fail closed
        # (no projection, a failure code, no live handle).
        res = _lb.read_active_local_safety_state_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=d["contract"], expected_ledger_path=other["path"])
        self.assertIsNone(res.projection)
        self.assertIsNotNone(res.failure_code)
        self.assertIsNone(res.handle)

    def test_t65_t66_restart_unresolved_or_stale_remains_held(self) -> None:
        # A freshly bootstrapped active ledger reopened without any release
        # sequence stays HELD / not WRITER_ELIGIBLE (T66: unknown inventory /
        # T65: stale release evidence never auto-advances).
        d = self._domain()
        res = _lb.read_active_local_safety_state_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=d["contract"], expected_ledger_path=d["path"])
        self.assertEqual(
            res.projection.writer_proof_state_by_proof_id.get(d["contract"].writer_proof_id), "HELD")
        self.assertNotEqual(res.projection.risk_control_state, "WRITER_ELIGIBLE")

    def test_t76_active_writer_proof_mismatch_blocks(self) -> None:
        d = self._domain()
        forged = self._forge(d["contract"], writer_proof_id="adwp_" + "0" * 32)
        with self.assertRaises(LedgerError) as c:
            _lb.read_active_local_safety_state_v1(
                self.binding, canonical_repository_root=str(self.repository_root),
                active_contract=forged, expected_ledger_path=d["path"])
        self.assertEqual(c.exception.code, FailureCode.ACTIVE_DOMAIN_CONTRACT_MALFORMED)


# ===========================================================================
# R1-D07 N1 CORRECTION_05 -- durable authorization-set consumption, typed
# expectation / live receipt, no-repair reads, under-lock entry guard, dormant
# emergency handle and the exact emergency-close readback theorem (offline,
# synthetic stores/clocks only).
# ===========================================================================

import multiprocessing as _mp
from unittest import mock as _mock

_ORCH_BOOT = "PRE_RELEASE_BRIDGE_RELEASE_ORCHESTRATION_V1"
_ORCH_CLEAN = "CLEAN_SAFE_HELD_RELEASE_CONTINUATION_V1"
_AUTH_ACCOUNT = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
_AUTH_PROC = "proc_" + "7" * 32
_AUTH_START = 5_000_000_000
_AUTH_END = _AUTH_START + 300_000_000_000


def _auth_binding_object(contract, *, cls=_ORCH_BOOT, config_sha="c" * 64, **overrides):
    value = {
        "authorization_set_id": "set_1", "task_id": "task_1", "execution_attempt_id": "attempt_1",
        "invocation_id": "inv_1", "orchestration_authorization_id": "orch_1",
        "orchestration_authorization_class": cls, "repository": "rigolugo/ARB",
        "required_implementation_commit": "1" * 40, "required_implementation_tree": "2" * 40,
        "required_implementation_parent": "3" * 40,
        "active_contract_id": contract.contract_id, "active_contract_sha256": contract.contract_sha256,
        "domain_binding_id": contract.domain_binding_id, "domain_binding_sha256": contract.domain_binding_sha256,
        "environment": "KALSHI_DEMO", "account_scope_ref": _AUTH_ACCOUNT, "subaccount": 1,
        "exchange_index": 0, "conflict_domain_ref": contract.conflict_domain_ref,
        "market_scope": {"scope_kind": "SINGLE_MARKET_TICKER", "ticker": "KXTEST-26SEP12-A"},
        "risk_config_raw_sha256": "a" * 64, "risk_config_semantic_sha256": config_sha,
        "process_continuity_mode": "ONE_PROCESS_ONE_INVOCATION_NO_RESTART",
        "absolute_deadline_seconds": 300,
        "deadline_policy": "ONE_INVOCATION_START_ABSOLUTE_DEADLINE_NO_RESET",
    }
    value.update(overrides)
    return value


def _auth_expectation(binding_obj, checkpoint, *, o_sha="4" * 64, g_sha="6" * 64, d07_sha="5" * 64,
                      gate_id="gate_1", d07_id="d07_1"):
    return _lb._issue_active_authorization_expectation(
        _lb._AUTHORIZATION_EXPECTATION_ISSUER_KEY,
        execution_package_id="pkg_1", expectation_carrier_sha256="e" * 64,
        authorization_set_id=binding_obj["authorization_set_id"], binding=binding_obj,
        authorization_binding_sha256=_lb.compute_authorization_binding_sha256(binding_obj),
        orchestration_authorization_id=binding_obj["orchestration_authorization_id"],
        orchestration_authorization_class=binding_obj["orchestration_authorization_class"],
        orchestration_authorization_sha256=o_sha, d07_read_authorization_id=d07_id,
        d07_read_authorization_sha256=d07_sha, gate_d_authorization_id=gate_id,
        gate_d_authorization_sha256=g_sha, entry_checkpoint=checkpoint,
    )


def _auth_live_checkpoint(projection, contract, *, state_event_id=None):
    return {
        "authority_instance_id": projection.authority_instance_id,
        "authority_namespace_id": projection.authority_namespace_id,
        "authority_store_path_identity_sha256": projection.authority_store_path_identity_sha256,
        "ledger_instance_id": projection.ledger_instance_id,
        "ledger_path_identity_sha256": projection.ledger_path_identity_sha256,
        "trusted_sequence": projection.trusted_sequence, "trusted_event_hash": projection.trusted_event_hash,
        "risk_control_state": projection.risk_control_state, "risk_state_epoch": projection.risk_state_epoch,
        "risk_state_event_id": state_event_id, "writer_proof_id": contract.writer_proof_id,
        "writer_proof_state": projection.writer_proof_state_by_proof_id.get(contract.writer_proof_id),
        "writer_proof_release_eligible": projection.writer_proof_release_eligible_by_proof_id.get(contract.writer_proof_id),
        "active_risk_config_sha256": projection.active_risk_config_sha256,
    }


def _authorization_race_worker(params, queue, barrier):
    """Separate-process consumption attempt (T17/T18)."""
    binding = AuthorityNamespaceBinding.bind(
        authority_namespace_id=params["namespace_id"], authority_namespace_root=params["authority_root"],
        canonical_repository_root=params["repository_root"])
    domain = _lb.ExecutionDomainBindingV1(
        venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=_AUTH_ACCOUNT, subaccount=1, exchange_index=0)
    contract = _lb.ActiveExecutionDomainContractV1(binding=domain, bootstrap_contract_sha256=params["bootstrap_sha"])
    expectation = _auth_expectation(params["binding"], params["checkpoint"])
    if barrier is not None:
        barrier.wait(timeout=60)
    result = _lb.consume_active_execution_authorization_set_v1(
        binding, canonical_repository_root=params["repository_root"], active_contract=contract,
        expectation=expectation, process_instance_id=params["process_id"],
        invocation_started_monotonic_ns=_AUTH_START, absolute_deadline_monotonic_ns=_AUTH_END,
        monotonic_clock_ns=lambda: _AUTH_START + 1, expected_ledger_path=params["ledger_path"])
    queue.put((result.outcome, result.receipt is not None, result.reason))


class AuthorizationConsumptionBindingTests(unittest.TestCase):
    """C04-T01/T15-T21/T23/T24/T26/T27 at the binding layer."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self.ledger_path = self.root / "active.sqlite3"
        self.inputs = DeterministicInputs()
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="auth-ns", authority_namespace_root=self.authority_root,
            canonical_repository_root=self.repository_root)
        initialize_authority_namespace(self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        self.domain = _lb.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=_AUTH_ACCOUNT, subaccount=1, exchange_index=0)
        self.bootstrap = _lb.DomainBootstrapContractV1(
            binding=self.domain, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
            bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
            prestack_activity_completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK",
            unresolved_write_count=0, unresolved_cancel_count=0, working_order_truth="COMPLETE_ZERO",
            fill_truth="COMPLETE_KNOWN_NONZERO", position_truth="COMPLETE_KNOWN_NONZERO",
            retained_position_ticker="KXAAAGASD-26SEP02-4.1200",
            retained_position_floor_contracts=Decimal("1.00"))
        _, self.contract = _lb.initialize_active_execution_domain_ledger(
            self.binding, canonical_repository_root=str(self.repository_root),
            domain_binding=self.domain, bootstrap_contract=self.bootstrap,
            ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)

    def tearDown(self) -> None:
        self.temp.cleanup()

    # -- helpers ---------------------------------------------------------
    def _read(self, *, no_repair=False):
        return _lb.read_active_local_safety_state_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid, no_repair=no_repair)

    def _checkpoint(self):
        opened = self._read(no_repair=True)
        self.assertIsNone(opened.failure_code)
        return _auth_live_checkpoint(opened.projection, self.contract, state_event_id=self._state_event_id())

    def _state_event_id(self):
        connection = sqlite3.connect(str(self.ledger_path))
        try:
            row = connection.execute(
                "SELECT event_id FROM ledger_events WHERE event_type='RISK_CONTROL_STATE_CHANGED' ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else row[0]

    def _event_types(self):
        connection = sqlite3.connect(str(self.ledger_path))
        try:
            return [r[0] for r in connection.execute("SELECT event_type FROM ledger_events ORDER BY sequence")]
        finally:
            connection.close()

    def _authority_tail(self):
        connection = sqlite3.connect(str(self.authority_root / ledger.AUTHORITY_STORE_FILENAME))
        try:
            return connection.execute(
                "SELECT trusted_sequence,trusted_event_hash FROM conflict_domain_authority").fetchone()
        finally:
            connection.close()

    def _binding_obj(self, **overrides):
        return _auth_binding_object(self.contract, **overrides)

    def _expectation(self, *, cls=_ORCH_BOOT, checkpoint=None, **kwargs):
        binding_obj = self._binding_obj(cls=cls)
        return _auth_expectation(binding_obj, checkpoint or self._checkpoint(), **kwargs)

    def _consume(self, expectation, *, mono=None, fault_hook=None, start=_AUTH_START):
        return _lb.consume_active_execution_authorization_set_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expectation=expectation, process_instance_id=_AUTH_PROC, invocation_started_monotonic_ns=start,
            absolute_deadline_monotonic_ns=start + 300_000_000_000,
            monotonic_clock_ns=mono or (lambda: start + 1), expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid, fault_hook=fault_hook)

    def _freshness(self, expectation):
        return _lb.read_active_authorization_freshness_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expectation=expectation, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid)

    def _drive_to_safe_held(self, config_sha="c" * 64):
        emergency = _lb.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        handle = emergency.handle
        self.assertIsNotNone(handle, emergency.failure_code)
        handle.record_reconciliation({
            "incident_id": self.contract.incident_id, "disposition": "SYNTHETIC_SAFE",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED", "bound_order_id": None,
            "created_order_upper_bound": 0, "active_order_upper_bound": 0, "unknown_result": False,
            "writer_proof_release_eligible": True, "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RESOLUTION_V1"}, incident_id=self.contract.incident_id)
        live = handle.inspect_validated_projection()
        handle.record_risk_control_state_changed({
            "previous_state": "BOOT_HOLD", "new_state": "SAFE_HELD", "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
            "risk_state_epoch_before": 0, "risk_state_epoch_after": 1, "risk_config_sha256": config_sha,
            "related_emergency_action_id": None, "related_release_id": None, "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": live.last_sequence, "observed_authority_trusted_hash": live.terminal_event_hash,
            "observed_ledger_terminal_sequence": live.last_sequence, "observed_ledger_terminal_hash": live.terminal_event_hash})
        handle.close()

    # -- typed expectation ---------------------------------------------------
    def test_expectation_requires_private_issuer_and_is_immutable_and_unserializable(self) -> None:
        expectation = self._expectation()
        with self.assertRaises(LedgerError):
            _lb.ActiveAuthorizationExpectationV1(object(), **{})
        with self.assertRaises(AttributeError):
            expectation.authorization_set_id = "other"
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.assertRaises(TypeError):
                operation(expectation)
        self.assertNotIn("set_1", repr(expectation))

    def test_expectation_rejects_hash_class_and_distinctness_mismatches(self) -> None:
        binding_obj = self._binding_obj()
        checkpoint = self._checkpoint()
        good = dict(
            execution_package_id="pkg_1", expectation_carrier_sha256="e" * 64,
            authorization_set_id="set_1", binding=binding_obj,
            authorization_binding_sha256=_lb.compute_authorization_binding_sha256(binding_obj),
            orchestration_authorization_id="orch_1", orchestration_authorization_class=_ORCH_BOOT,
            orchestration_authorization_sha256="4" * 64, d07_read_authorization_id="d07_1",
            d07_read_authorization_sha256="5" * 64, gate_d_authorization_id="gate_1",
            gate_d_authorization_sha256="6" * 64, entry_checkpoint=checkpoint)
        key = _lb._AUTHORIZATION_EXPECTATION_ISSUER_KEY
        _lb._issue_active_authorization_expectation(key, **good)
        for change in (
            {"authorization_binding_sha256": "0" * 64},
            {"authorization_set_id": "set_other"},
            {"orchestration_authorization_class": _ORCH_CLEAN},
            {"gate_d_authorization_id": "orch_1"},
            {"binding": dict(binding_obj, exchange_index="0")},
            {"binding": dict(binding_obj, extra_key=1)},
        ):
            with self.subTest(change=list(change)):
                with self.assertRaises(LedgerError):
                    _lb._issue_active_authorization_expectation(key, **dict(good, **change))

    def test_entry_checkpoint_validation_is_exact_and_closed(self) -> None:
        checkpoint = self._checkpoint()
        self.assertEqual(_lb.validate_active_entry_checkpoint(checkpoint)["risk_control_state"], "BOOT_HOLD")
        for change in (
            {"risk_control_state": "WRITER_ELIGIBLE"},
            {"risk_state_epoch": 1},
            {"trusted_sequence": True},
            {"trusted_event_hash": "Z" * 64},
            {"writer_proof_release_eligible": 1},
            {"active_risk_config_sha256": "c" * 64},
        ):
            with self.subTest(change=list(change)):
                with self.assertRaises(LedgerError):
                    _lb.validate_active_entry_checkpoint(dict(checkpoint, **change))
        with self.assertRaises(LedgerError):
            _lb.validate_active_entry_checkpoint({k: v for k, v in checkpoint.items() if k != "writer_proof_id"})

    def test_binding_object_and_hash_are_exact_and_domain_separated(self) -> None:
        binding_obj = self._binding_obj()
        expected = ledger.sha256_hex(b"ARB_RELEASE_GATE_D_BINDING_V1\x00" + ledger.canonical_json_bytes(binding_obj))
        self.assertEqual(_lb.compute_authorization_binding_sha256(binding_obj), expected)
        for bad in (
            dict(binding_obj, subaccount=True), dict(binding_obj, market_scope={"scope_kind": "X", "ticker": "T"}),
            dict(binding_obj, absolute_deadline_seconds=301), dict(binding_obj, environment="KALSHI_PROD"),
            dict(binding_obj, required_implementation_commit="A" * 40),
        ):
            with self.assertRaises(LedgerError):
                _lb.compute_authorization_binding_sha256(bad)

    # -- freshness -----------------------------------------------------------------
    def test_freshness_unused_only_at_exact_checkpoint_and_state_conditions(self) -> None:
        expectation = self._expectation()
        result = self._freshness(expectation)
        self.assertIs(result.state, _lb.AuthorizationFreshnessState.UNUSED)
        before = (self._event_types(), self._authority_tail())
        self._freshness(expectation)
        self.assertEqual((self._event_types(), self._authority_tail()), before)  # zero append / no repair
        checkpoint = self._checkpoint()
        for change, reason in (
            ({"trusted_sequence": checkpoint["trusted_sequence"] + 1}, "ENTRY_CHECKPOINT_MISMATCH"),
            ({"ledger_instance_id": "some-other-ledger"}, "STORE_IDENTITY_MISMATCH"),
            ({"authority_namespace_id": "other-ns"}, "STORE_IDENTITY_MISMATCH"),
        ):
            with self.subTest(change=list(change)):
                stale = self._freshness(self._expectation(checkpoint=dict(checkpoint, **change)))
                self.assertIs(stale.state, _lb.AuthorizationFreshnessState.STALE_BINDING)
                self.assertEqual(stale.reason, reason)

    def test_freshness_binding_and_variant_mismatches_are_stale(self) -> None:
        other = self._binding_obj(active_contract_sha256="9" * 64)
        stale = self._freshness(_auth_expectation(other, self._checkpoint()))
        self.assertIs(stale.state, _lb.AuthorizationFreshnessState.STALE_BINDING)
        self.assertEqual(stale.reason, "BINDING_CONTRACT_MISMATCH")
        # A clean SAFE_HELD continuation cannot be admitted from genuine BOOT_HOLD.
        fake_safe_checkpoint = dict(
            self._checkpoint(), risk_control_state="SAFE_HELD", risk_state_epoch=1,
            risk_state_event_id="evt_" + "1" * 32, writer_proof_release_eligible=True,
            active_risk_config_sha256="c" * 64)
        expectation = _auth_expectation(self._binding_obj(cls=_ORCH_CLEAN), fake_safe_checkpoint)
        wrong = self._freshness(expectation)
        self.assertIs(wrong.state, _lb.AuthorizationFreshnessState.STALE_BINDING)
        self.assertEqual(wrong.reason, "ENTRY_STATE_MISMATCH")

    def test_clean_safe_held_entry_and_boot_hold_variant_mismatch(self) -> None:
        self._drive_to_safe_held()
        checkpoint = self._checkpoint()
        self.assertEqual(checkpoint["risk_control_state"], "SAFE_HELD")
        clean = self._freshness(_auth_expectation(self._binding_obj(cls=_ORCH_CLEAN), checkpoint))
        self.assertIs(clean.state, _lb.AuthorizationFreshnessState.UNUSED, clean.reason)
        boot_checkpoint = dict(checkpoint, risk_control_state="BOOT_HOLD", risk_state_epoch=0,
                               risk_state_event_id=None, active_risk_config_sha256=None,
                               writer_proof_release_eligible=False)
        boot = self._freshness(_auth_expectation(self._binding_obj(cls=_ORCH_BOOT), boot_checkpoint))
        self.assertIs(boot.state, _lb.AuthorizationFreshnessState.STALE_BINDING)
        self.assertEqual(boot.reason, "ENTRY_STATE_MISMATCH")

    # -- consumption ------------------------------------------------------------------
    def test_consumption_appends_exactly_one_anchored_event_and_mints_live_receipt(self) -> None:
        expectation = self._expectation()
        before = self._read(no_repair=True).projection
        before_types = self._event_types()
        result = self._consume(expectation)
        self.assertEqual(result.outcome, "CONSUMED", (result.reason, result.underlying_failure_code))
        receipt = result.receipt
        self.assertIsInstance(receipt, _lb.ActiveAuthorizationConsumptionV1)
        types = self._event_types()
        self.assertEqual(types[:-1], before_types)
        self.assertEqual(types[-1], "EXECUTION_AUTHORIZATION_SET_CONSUMED")
        self.assertEqual(receipt.consumption_sequence, before.last_sequence + 1)
        after = self._read(no_repair=True).projection
        self.assertEqual((after.trusted_sequence, after.trusted_event_hash), (after.last_sequence, after.terminal_event_hash))
        self.assertEqual(after.terminal_event_hash, receipt.consumption_event_hash)
        # The event changes no safety projection (risk / proof / config / sessions).
        for name in ("risk_control_state", "risk_state_epoch", "active_risk_config_sha256",
                     "writer_proof_state_by_proof_id", "writer_proof_release_eligible_by_proof_id",
                     "active_restricted_session_id", "active_writer_session_id", "restricted_sessions"):
            self.assertEqual(getattr(after, name), getattr(before, name), name)
        # Locks were released before the caller resumes: an independent read succeeds.
        self.assertIsNone(self._read(no_repair=True).failure_code)
        # Exactly the deterministic event id.
        expected_id = "evt_" + ledger.sha256_hex(
            b"ARB_EXECUTION_AUTHORIZATION_SET_CONSUMED_V1\x00" + ledger.canonical_json_bytes(
                {"conflict_domain_ref": self.contract.conflict_domain_ref, "orchestration_authorization_id": "orch_1"}))[:32]
        self.assertEqual(receipt.consumption_event_id, expected_id)

    def test_second_consumption_is_replayed_conflict_or_sha_replay_and_never_appends(self) -> None:
        first = self._consume(self._expectation())
        self.assertEqual(first.outcome, "CONSUMED")
        types = self._event_types()
        again = self._consume(self._expectation())
        self.assertEqual((again.outcome, again.receipt), ("REPLAYED", None))
        # Same IDs but changed G bytes -> conflict (AUTHORIZATION_SET_ID_CONFLICT).
        changed = self._consume(self._expectation(g_sha="8" * 64))
        self.assertEqual((changed.outcome, changed.receipt), ("CONFLICT", None))
        # New IDs but the identical raw O artifact -> still consumed (no relabel replay).
        relabeled = _auth_expectation(
            self._binding_obj(authorization_set_id="set_2", execution_attempt_id="attempt_2",
                              invocation_id="inv_2", orchestration_authorization_id="orch_2"),
            self._checkpoint(), gate_id="gate_2", d07_id="d07_2", g_sha="9" * 64)
        replay = self._consume(relabeled)
        self.assertEqual((replay.outcome, replay.receipt), ("REPLAYED", None))
        self.assertEqual(self._event_types(), types)
        self.assertIs(self._freshness(self._expectation()).state, _lb.AuthorizationFreshnessState.CONSUMED)
        self.assertIs(self._freshness(self._expectation(g_sha="8" * 64)).state, _lb.AuthorizationFreshnessState.CONFLICT)

    def test_idempotent_duplicate_append_can_never_mint_a_receipt(self) -> None:
        expectation = self._expectation()
        self.assertEqual(self._consume(expectation).outcome, "CONSUMED")
        opened = ledger._acquire_consumption_state(
            self.binding, conflict_domain_ref=self.contract.conflict_domain_ref, expected_environment="KALSHI_DEMO",
            canonical_repository_root=str(self.repository_root), expected_ledger_path=str(self.ledger_path))
        self.assertIsNotNone(opened.locked)
        try:
            record = opened.consumption.records[0]
            existing = opened.locked.events[-1]
            duplicate = opened.locked._append_batch_locked((EventInput(
                EventType.EXECUTION_AUTHORIZATION_SET_CONSUMED, dict(record.payload),
                event_id=existing.event_id, recorded_at_utc=existing.recorded_at_utc),))
            self.assertIs(duplicate.status, ledger.AppendStatus.IDEMPOTENT_DUPLICATE)
            with self.assertRaises(LedgerError):
                ledger._append_authorization_consumption(opened.locked, dict(record.payload))
            with self.assertRaises(LedgerError) as conflict:
                opened.locked._append_batch_locked((EventInput(
                    EventType.EXECUTION_AUTHORIZATION_SET_CONSUMED, dict(record.payload)),))
            self.assertIn(conflict.exception.code, {FailureCode.EVENT_ID_CONTENT_CONFLICT, FailureCode.EVENT_REQUIRED_REFERENCE_INVALID})
        finally:
            opened.locked.close()

    def test_deadline_expiry_before_consumption_appends_nothing(self) -> None:
        expectation = self._expectation()
        types = self._event_types()
        result = self._consume(expectation, mono=lambda: _AUTH_END)
        self.assertEqual((result.outcome, result.receipt), ("DEADLINE_EXPIRED", None))
        self.assertEqual(self._event_types(), types)
        bad_window = _lb.consume_active_execution_authorization_set_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expectation=expectation, process_instance_id=_AUTH_PROC, invocation_started_monotonic_ns=_AUTH_START,
            absolute_deadline_monotonic_ns=_AUTH_START + 299_000_000_000, monotonic_clock_ns=lambda: _AUTH_START,
            expected_ledger_path=str(self.ledger_path))
        self.assertEqual(bad_window.outcome, "FAILED")

    def test_untrusted_expectation_is_rejected_without_appending(self) -> None:
        types = self._event_types()
        fake = {"authorization_set_id": "set_1"}
        result = self._consume(fake)
        self.assertEqual((result.outcome, result.receipt), ("STALE_BINDING", None))
        self.assertEqual(self._event_types(), types)
        self.assertIs(self._freshness(fake).state, _lb.AuthorizationFreshnessState.INDETERMINATE)

    def test_binding_mismatch_is_stale_and_appends_nothing(self) -> None:
        types = self._event_types()
        stale = self._consume(_auth_expectation(self._binding_obj(exchange_index=3), self._checkpoint()))
        self.assertEqual((stale.outcome, stale.receipt), ("STALE_BINDING", None))
        self.assertEqual(self._event_types(), types)

    # -- receipt --------------------------------------------------------------------------
    def test_receipt_is_live_process_local_one_shot_and_not_reconstructable(self) -> None:
        receipt = self._consume(self._expectation()).receipt
        receipt.assert_live(process_instance_id=_AUTH_PROC)
        with self.assertRaises(LedgerError) as c:
            receipt.assert_live(process_instance_id="proc_" + "8" * 32)
        self.assertEqual(c.exception.code, FailureCode.AUTHORIZATION_RECEIPT_PROCESS_MISMATCH)
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.assertRaises(TypeError):
                operation(receipt)
        with self.assertRaises(AttributeError):
            receipt.consumption_sequence = 1
        # A forged instance (wrong issuer key) or a value-equal reconstruction fails.
        with self.assertRaises(LedgerError):
            _lb.ActiveAuthorizationConsumptionV1(object(), **{})
        forged = _lb.ActiveAuthorizationConsumptionV1(
            _lb._AUTHORIZATION_RECEIPT_ISSUER_KEY, **{name: getattr(receipt, name) for name in _lb._RECEIPT_FIELDS})
        self.assertIsNot(forged, receipt)
        forged.revoke()
        with self.assertRaises(LedgerError):
            forged.assert_live()
        receipt.assert_live()  # the genuine receipt is unaffected
        # OS process identity: a different pid (fork/other process) never validates.
        with _mock.patch.object(_lb.os, "getpid", return_value=receipt.os_process_id + 1):
            with self.assertRaises(LedgerError) as c:
                receipt.assert_live()
            self.assertEqual(c.exception.code, FailureCode.AUTHORIZATION_RECEIPT_PROCESS_MISMATCH)
        receipt.revoke()
        with self.assertRaises(LedgerError) as c:
            receipt.assert_live()
        self.assertEqual(c.exception.code, FailureCode.AUTHORIZATION_RECEIPT_INVALID)

    def test_receipt_stage_latches_are_monotonic_and_one_use(self) -> None:
        receipt = self._consume(self._expectation()).receipt
        receipt.claim_stage("PHASE_1_READ")
        receipt.claim_stage("PHASE_2_READ")
        for stage in ("PHASE_1_READ", "PHASE_2_READ", "BRIDGE_EMERGENCY_ACQUISITION"):
            with self.assertRaises(LedgerError) as c:
                receipt.claim_stage(stage)
            self.assertEqual(c.exception.code, FailureCode.AUTHORIZATION_RECEIPT_STAGE_LATCH_SPENT)
        receipt.claim_stage("RELEASE_ONLY_ACQUISITION")
        with self.assertRaises(LedgerError):
            receipt.claim_stage("NOT_A_STAGE")
        self.assertEqual(receipt.claimed_stages[-1], "RELEASE_ONLY_ACQUISITION")
        receipt.revoke()

    # -- crash / fault matrix (C04-T21) ------------------------------------------------------
    def _fault(self, stage, exception):
        def hook(name):
            if name == stage:
                raise exception
        return hook

    def test_fault_before_ledger_commit_is_definite_failure_and_leaves_no_row(self) -> None:
        expectation = self._expectation()
        types = self._event_types()
        result = self._consume(expectation, fault_hook=self._fault("before_ledger_commit", sqlite3.OperationalError("x")))
        self.assertEqual((result.outcome, result.receipt), ("FAILED", None))
        self.assertEqual(self._event_types(), types)
        # Historical UNUSED only: a later, separately authorized attempt is not this invocation.
        self.assertIs(self._freshness(expectation).state, _lb.AuthorizationFreshnessState.UNUSED)

    def test_fault_after_ledger_commit_before_anchor_is_indeterminate_and_ledger_ahead(self) -> None:
        expectation = self._expectation()
        anchored = self._authority_tail()
        result = self._consume(expectation, fault_hook=self._fault("after_ledger_commit", RuntimeError("crash")))
        self.assertEqual((result.outcome, result.receipt), ("INDETERMINATE", None))
        self.assertIn("EXECUTION_AUTHORIZATION_SET_CONSUMED", self._event_types())
        self.assertEqual(self._authority_tail(), anchored)  # authority NOT advanced by any repair
        # No-repair freshness cannot call this UNUSED, and does not catch up.
        fresh = self._freshness(expectation)
        self.assertIs(fresh.state, _lb.AuthorizationFreshnessState.INDETERMINATE)
        self.assertEqual(fresh.underlying_failure_code, FailureCode.NO_REPAIR_AUTHORITY_LEDGER_TAIL_MISMATCH)
        self.assertEqual(self._authority_tail(), anchored)
        again = self._consume(expectation)
        self.assertEqual((again.outcome, again.receipt), ("INDETERMINATE", None))
        no_repair = self._read(no_repair=True)
        self.assertEqual(no_repair.failure_code, FailureCode.NO_REPAIR_AUTHORITY_LEDGER_TAIL_MISMATCH)
        self.assertEqual(self._authority_tail(), anchored)
        # Default (unchanged) recovery catch-up preserves the durable event: never fresh authority.
        self.assertIsNone(self._read(no_repair=False).failure_code)
        self.assertIs(self._freshness(expectation).state, _lb.AuthorizationFreshnessState.CONSUMED)

    def test_faults_after_anchor_and_after_readback_never_yield_a_receipt_but_stay_consumed(self) -> None:
        for index, stage in enumerate(("after_authority_commit", "after_consumption_readback")):
            with self.subTest(stage=stage):
                self.tearDown()
                self.setUp()
                expectation = self._expectation()
                result = self._consume(expectation, fault_hook=self._fault(stage, RuntimeError("crash")))
                self.assertEqual((result.outcome, result.receipt), ("INDETERMINATE", None))
                self.assertIs(self._freshness(expectation).state, _lb.AuthorizationFreshnessState.CONSUMED)
                self.assertEqual(self._consume(expectation).outcome, "REPLAYED")

    def test_commit_result_unknown_paths_are_indeterminate(self) -> None:
        for stage in ("before_ledger_commit", "before_authority_commit"):
            with self.subTest(stage=stage):
                self.tearDown()
                self.setUp()
                expectation = self._expectation()
                result = self._consume(expectation, fault_hook=self._fault(stage, CommitResultUnknown(FailureCode.LEDGER_COMMIT_RESULT_UNKNOWN)))
                self.assertEqual((result.outcome, result.receipt), ("INDETERMINATE", None))
                self.assertIn(self._freshness(expectation).state, {
                    _lb.AuthorizationFreshnessState.INDETERMINATE, _lb.AuthorizationFreshnessState.UNUSED,
                    _lb.AuthorizationFreshnessState.CONSUMED})

    def test_definite_authority_failure_after_ledger_commit_is_failed_not_retried(self) -> None:
        expectation = self._expectation()
        result = self._consume(expectation, fault_hook=self._fault("before_authority_commit", sqlite3.OperationalError("x")))
        self.assertEqual((result.outcome, result.receipt), ("FAILED", None))
        self.assertIs(self._freshness(expectation).state, _lb.AuthorizationFreshnessState.INDETERMINATE)

    # -- store integrity (C04-T23) ---------------------------------------------------------------
    def test_corrupt_or_replaced_store_is_indeterminate_never_an_empty_map(self) -> None:
        expectation = self._expectation()
        connection = sqlite3.connect(str(self.ledger_path))
        try:
            connection.execute("DROP TRIGGER trg_ledger_events_no_update")
            connection.execute("UPDATE ledger_events SET payload_sha256='" + "0" * 64 + "' WHERE sequence=2")
            connection.commit()
        finally:
            connection.close()
        fresh = self._freshness(expectation)
        self.assertIs(fresh.state, _lb.AuthorizationFreshnessState.INDETERMINATE)
        self.assertIsNone(self._consume(expectation).receipt)

    def test_consumption_event_with_foreign_domain_binding_fails_history_validation(self) -> None:
        # Craft (bypassing the binding API) a syntactically valid consumption whose
        # domain identity is not this active contract: replay must fail closed.
        foreign = self._binding_obj(active_contract_sha256="9" * 64)
        opened = ledger._acquire_consumption_state(
            self.binding, conflict_domain_ref=self.contract.conflict_domain_ref, expected_environment="KALSHI_DEMO",
            canonical_repository_root=str(self.repository_root), expected_ledger_path=str(self.ledger_path))
        locked = opened.locked
        tail = locked.events[-1]
        payload = {
            "consumption_schema_revision": 1, "execution_package_id": "pkg_1", "expectation_carrier_sha256": "e" * 64,
            "authorization_set_id": "set_1", "authorization_binding_sha256": _lb.compute_authorization_binding_sha256(foreign),
            "orchestration_authorization_id": "orch_1", "orchestration_authorization_class": _ORCH_BOOT,
            "orchestration_authorization_sha256": "4" * 64, "d07_read_authorization_id": "d07_1",
            "d07_read_authorization_sha256": "5" * 64, "gate_d_authorization_id": "gate_1",
            "gate_d_authorization_sha256": "6" * 64, "task_id": "task_1", "execution_attempt_id": "attempt_1",
            "invocation_id": "inv_1", "process_instance_id": _AUTH_PROC, "binding": foreign,
            "authority_instance_id": locked.authority_meta.authority_instance_id,
            "authority_namespace_id": locked.authority_meta.authority_namespace_id,
            "authority_store_path_identity_sha256": locked.authority_meta.authority_store_path_identity_sha256,
            "ledger_instance_id": locked.ledger_meta.ledger_instance_id,
            "ledger_path_identity_sha256": locked.ledger_meta.ledger_path_identity_sha256,
            "pre_consumption_sequence": tail.sequence, "pre_consumption_event_hash": tail.event_hash,
            "invocation_started_monotonic_ns": _AUTH_START, "invocation_absolute_deadline_monotonic_ns": _AUTH_END,
            "consumption_policy": "DURABLE_ARB_AUTHORIZATION_SET_CONSUMED_V1"}
        try:
            ledger._append_authorization_consumption(locked, payload)
        finally:
            locked.close()
        rejected = self._read(no_repair=True)
        self.assertEqual(rejected.failure_code, FailureCode.ACTIVE_DOMAIN_CONTRACT_MISMATCH)
        self.assertIsNone(rejected.projection)

    # -- no-repair reads --------------------------------------------------------------------------------
    def test_existing_default_reads_keep_authority_catch_up_behaviour(self) -> None:
        expectation = self._expectation()
        anchored = self._authority_tail()
        self._consume(expectation, fault_hook=self._fault("after_ledger_commit", RuntimeError("crash")))
        self.assertEqual(self._authority_tail(), anchored)
        default = self._read()
        self.assertIsNone(default.failure_code)
        self.assertIs(default.authority_ledger_relation, AuthorityLedgerRelation.LEDGER_AHEAD)
        self.assertNotEqual(self._authority_tail(), anchored)
        evidence = _lb.read_active_trusted_release_evidence_projection_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), no_repair=True)
        self.assertIsNotNone(evidence.projection)

    def test_no_repair_trusted_evidence_read_refuses_ledger_ahead(self) -> None:
        self._consume(self._expectation(), fault_hook=self._fault("after_ledger_commit", RuntimeError("crash")))
        anchored = self._authority_tail()
        evidence = _lb.read_active_trusted_release_evidence_projection_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), no_repair=True)
        self.assertIsNone(evidence.projection)
        self.assertEqual(evidence.failure_code, FailureCode.NO_REPAIR_AUTHORITY_LEDGER_TAIL_MISMATCH)
        self.assertEqual(self._authority_tail(), anchored)

    # -- under-lock entry guard (C04-T14 / T27) -----------------------------------------------------------
    def _guard(self, receipt, *, tail=None, **overrides):
        projection = self._read(no_repair=True).projection
        sequence, digest = tail or (projection.last_sequence, projection.terminal_event_hash)
        proof = self.contract.writer_proof_id
        values = dict(
            receipt=receipt, expected_tail_sequence=sequence, expected_tail_event_hash=digest,
            expected_risk_control_state=projection.risk_control_state,
            expected_risk_state_epoch=projection.risk_state_epoch,
            expected_active_risk_config_sha256=projection.active_risk_config_sha256,
            expected_writer_proof_state=projection.writer_proof_state_by_proof_id[proof],
            expected_writer_proof_release_eligible=projection.writer_proof_release_eligible_by_proof_id[proof])
        values.update(overrides)
        return _lb.ActiveAcquisitionEntryGuardV1(**values)

    def test_guard_failure_leaves_stores_byte_identical_for_every_acquisition(self) -> None:
        receipt = self._consume(self._expectation()).receipt
        types, tail = self._event_types(), self._authority_tail()
        projection = self._read(no_repair=True).projection
        bad_guards = (
            self._guard(receipt, tail=(projection.last_sequence, "0" * 64)),
            self._guard(receipt, expected_risk_control_state="SAFE_HELD"),
            self._guard(receipt, expected_writer_proof_release_eligible=True),
        )
        for guard in bad_guards:
            for acquire in (_lb.acquire_active_emergency_control_only_v1, _lb.acquire_active_release_only_v1):
                with self.subTest(guard=guard.expected_risk_control_state, acquire=acquire.__name__):
                    result = acquire(
                        self.binding, canonical_repository_root=str(self.repository_root),
                        active_contract=self.contract, expected_ledger_path=str(self.ledger_path),
                        clock=self.inputs.clock, uuid_factory=self.inputs.uuid, entry_guard=guard)
                    self.assertIsNone(result.handle)
                    self.assertEqual(result.failure_code, FailureCode.ACQUISITION_ENTRY_GUARD_FAILED)
                    self.assertEqual((self._event_types(), self._authority_tail()), (types, tail))
        receipt.revoke()

    def test_guard_rejects_dead_receipt_and_missing_consumption_event(self) -> None:
        receipt = self._consume(self._expectation()).receipt
        guard = self._guard(receipt)
        receipt.revoke()
        types = self._event_types()
        result = _lb.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
            entry_guard=guard)
        self.assertIsNone(result.handle)
        self.assertEqual(result.failure_code, FailureCode.AUTHORIZATION_RECEIPT_INVALID)
        self.assertEqual(self._event_types(), types)
        with self.assertRaises(LedgerError):
            _lb.ActiveAcquisitionEntryGuardV1(
                receipt=object(), expected_tail_sequence=1, expected_tail_event_hash="a" * 64,
                expected_risk_control_state="BOOT_HOLD", expected_risk_state_epoch=0,
                expected_active_risk_config_sha256=None, expected_writer_proof_state="HELD",
                expected_writer_proof_release_eligible=False)

    def test_guarded_emergency_acquisition_succeeds_only_at_the_exact_tail(self) -> None:
        receipt = self._consume(self._expectation()).receipt
        guard = self._guard(receipt)
        emergency = _lb.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
            entry_guard=guard)
        self.assertIsNotNone(emergency.handle, emergency.failure_code)
        emergency.handle.close()
        receipt.revoke()
        self.assertEqual(self._event_types()[-2:], ["RESTRICTED_SESSION_STARTED", "RESTRICTED_SESSION_ENDED"])

    def test_stale_open_session_is_not_abandoned_by_a_guarded_acquisition(self) -> None:
        # An abandoned-crash emulation: a restricted session left open in the ledger.
        opened = _lb.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        opened.handle._EmergencyControlLedgerHandle__locked.close()  # drop the locks WITHOUT the clean end
        types = self._event_types()
        self.assertEqual(types[-1], "RESTRICTED_SESSION_STARTED")
        result = self._consume(_auth_expectation(self._binding_obj(), dict(self._checkpoint())))
        self.assertEqual(result.outcome, "STALE_BINDING")
        self.assertEqual(result.reason, "ENTRY_STATE_REQUIRES_RECOVERY")
        self.assertEqual(self._event_types(), types)  # no abandonment, no consumption
        # The ordinary (default) acquisition still abandons: unchanged legacy behaviour.
        default = _lb.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        default.handle.close()
        self.assertIn("RESTRICTED_SESSION_ABANDONED", self._event_types())

    # -- dormant handle ------------------------------------------------------------------------------------
    def test_dormant_emergency_handle_builds_a_gate_with_zero_appends(self) -> None:
        types, tail = self._event_types(), self._authority_tail()
        handle = _lb.build_dormant_emergency_control_handle_v1()
        gate = EmergencyCancelGate(
            handle=handle, rate_lane=EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100)),
            process_instance_id="proc_" + "a" * 32, monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock, uuid_factory=self.inputs.uuid, active_contract=self.contract)
        self.assertEqual(gate.outstanding_permit_count, 0)
        for call in (
            lambda: handle.inspect_validated_projection(),
            lambda: handle.record_reconciliation({}, incident_id="x"),
            lambda: handle.record_risk_control_state_changed({}),
            lambda: handle.open_emergency_action({}),
            lambda: handle.record_order_observation({}),
        ):
            with self.assertRaises(LedgerError):
                call()
        handle.close()
        self.assertEqual((self._event_types(), self._authority_tail()), (types, tail))
        self.assertNotIn("is_dormant", {name for name in dir(handle) if not name.startswith("_")})

    # -- exact clean-close readback theorem (C04-T06) -----------------------------------------------------------------
    def _close_emergency(self):
        emergency = _lb.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        handle = emergency.handle
        live = handle.inspect_validated_projection()
        pre = (live.last_sequence, live.terminal_event_hash, handle.restricted_session_id)
        handle.close()
        return pre

    def _readback(self, sequence, digest, session):
        return _lb.read_active_emergency_close_readback_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.contract,
            restricted_session_id=session, pre_close_sequence=sequence, pre_close_event_hash=digest,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)

    def test_close_readback_theorem_is_exact(self) -> None:
        sequence, digest, session = self._close_emergency()
        ok = self._readback(sequence, digest, session)
        self.assertTrue(ok.verified, (ok.reason, ok.failure_code))
        self.assertEqual(ok.projection.last_sequence, sequence + 1)
        for label, args in (
            ("wrong sequence", (sequence - 1, digest, session)),
            ("wrong parent hash", (sequence, "0" * 64, session)),
            ("wrong session", (sequence, digest, "rs_" + "0" * 32)),
        ):
            with self.subTest(label):
                self.assertFalse(self._readback(*args).verified)
        # Extra movement after the close (a later event) breaks the exact +1 tail.
        second = self._close_emergency()
        self.assertFalse(self._readback(sequence, digest, session).verified)
        self.assertTrue(self._readback(*second[:2], second[2]).verified)

    # -- cross-process replay and race (C04-T17 / T18) --------------------------------------------------------------------
    def _worker_params(self, checkpoint):
        return {
            "namespace_id": "auth-ns", "authority_root": str(self.authority_root),
            "repository_root": str(self.repository_root), "ledger_path": str(self.ledger_path),
            "bootstrap_sha": self.contract.bootstrap_contract_sha256, "binding": self._binding_obj(),
            "checkpoint": checkpoint, "process_id": _AUTH_PROC,
        }

    def test_new_independent_process_cannot_reuse_a_consumed_set(self) -> None:
        checkpoint = self._checkpoint()
        self.assertEqual(self._consume(self._expectation(checkpoint=checkpoint)).outcome, "CONSUMED")
        context = _mp.get_context("spawn")
        queue = context.Queue()
        process = context.Process(target=_authorization_race_worker, args=(self._worker_params(checkpoint), queue, None))
        process.start()
        outcome = queue.get(timeout=120)
        process.join(timeout=60)
        self.assertEqual(outcome[:2], ("REPLAYED", False))
        self.assertEqual(self._event_types().count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)

    def test_parallel_consumption_has_at_most_one_winner_and_never_retries(self) -> None:
        checkpoint = self._checkpoint()
        context = _mp.get_context("spawn")
        queue = context.Queue()
        barrier = context.Barrier(2)
        processes = [
            context.Process(target=_authorization_race_worker, args=(self._worker_params(checkpoint), queue, barrier))
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        outcomes = [queue.get(timeout=180) for _ in processes]
        for process in processes:
            process.join(timeout=60)
        winners = [o for o in outcomes if o[0] == "CONSUMED"]
        self.assertEqual(len(winners), 1, outcomes)
        self.assertTrue(winners[0][1])
        losers = [o for o in outcomes if o[0] != "CONSUMED"]
        self.assertEqual(len(losers), 1)
        self.assertIn(losers[0][0], {"REPLAYED", "UNAVAILABLE", "CONFLICT", "STALE_BINDING"})
        self.assertFalse(losers[0][1])
        self.assertEqual(self._event_types().count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)

    # -- CORRECTION_02 closure: C04-T15 authority/ledger divergence -----------
    def _snapshot_ledger(self):
        return {path.name: path.read_bytes()
                for path in sorted(self.root.glob(self.ledger_path.name + "*"))}

    def _restore_ledger(self, snapshot) -> None:
        for path in sorted(self.root.glob(self.ledger_path.name + "*")):
            if path.name not in snapshot:
                path.unlink()
        for name, payload in snapshot.items():
            (self.root / name).write_bytes(payload)

    def _acquisitions(self):
        return (
            ("emergency", _lb.acquire_active_emergency_control_only_v1),
            ("release", _lb.acquire_active_release_only_v1),
        )

    def _assert_every_acquisition_fails_closed(self, code) -> None:
        for label, acquire in self._acquisitions():
            with self.subTest(label):
                acquisition = acquire(
                    self.binding, canonical_repository_root=str(self.repository_root),
                    active_contract=self.contract, expected_ledger_path=str(self.ledger_path),
                    clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
                if acquisition.handle is not None:
                    acquisition.handle.close()
                self.assertIsNone(acquisition.handle)
                self.assertEqual(acquisition.failure_code, code)

    def test_c04_t15_authority_ahead_of_ledger_fails_closed_with_no_repair(self) -> None:
        """C04-T15 (authority ahead).  A restored older ledger under a newer
        approved authority anchor is a rollback/replacement: every read and
        every acquisition fails closed.  There is no catch-up, no anchor
        movement, no abandonment, no creation, no consumption and no session
        append -- under the no-repair open AND the default open."""
        older = self._snapshot_ledger()
        self.assertEqual(self._consume(self._expectation()).outcome, "CONSUMED")
        anchored = self._authority_tail()
        self._restore_ledger(older)  # authority is now AHEAD of the ledger
        durable = self._event_types()
        self.assertNotIn("EXECUTION_AUTHORIZATION_SET_CONSUMED", durable)

        rollback = FailureCode.AUTHORITY_AHEAD_OF_LEDGER_ROLLBACK_OR_REPLACEMENT
        for no_repair in (True, False):
            with self.subTest(no_repair=no_repair):
                opened = self._read(no_repair=no_repair)
                self.assertIsNone(opened.projection)  # never an empty/default state
                self.assertEqual(opened.failure_code, rollback)
                # No catch-up and no anchor movement in EITHER direction.
                self.assertEqual(self._authority_tail(), anchored)
                self.assertEqual(self._event_types(), durable)

        evidence = _lb.read_active_trusted_release_evidence_projection_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=self.contract, expected_ledger_path=str(self.ledger_path),
            no_repair=True)
        self.assertIsNone(evidence.projection)
        self.assertEqual(evidence.failure_code, rollback)

        self._assert_every_acquisition_fails_closed(rollback)
        # Nothing was created, consumed, abandoned or appended.
        self.assertEqual(self._event_types(), durable)
        self.assertEqual(self._authority_tail(), anchored)
        for forbidden in (
            "EXECUTION_AUTHORIZATION_SET_CONSUMED", "RESTRICTED_SESSION_STARTED",
            "RESTRICTED_SESSION_ENDED", "RESTRICTED_SESSION_ABANDONED", "WRITER_SESSION_STARTED",
        ):
            self.assertNotIn(forbidden, self._event_types())

    def test_c04_t15_ledger_ahead_of_authority_fails_closed_with_no_repair(self) -> None:
        """C04-T15 (ledger ahead).  The mirror case under the no-repair
        admission path: the durable event stands, the anchor is NOT advanced to
        catch up, and no acquisition, consumption or session append occurs."""
        anchored = self._authority_tail()
        expectation = self._expectation()
        result = self._consume(
            expectation, fault_hook=self._fault("after_ledger_commit", RuntimeError("crash")))
        self.assertEqual((result.outcome, result.receipt), ("INDETERMINATE", None))
        durable = self._event_types()
        self.assertIn("EXECUTION_AUTHORIZATION_SET_CONSUMED", durable)
        self.assertEqual(self._authority_tail(), anchored)  # no repair-driven catch-up

        mismatch = FailureCode.NO_REPAIR_AUTHORITY_LEDGER_TAIL_MISMATCH
        opened = self._read(no_repair=True)
        self.assertIsNone(opened.projection)  # never an empty/default state
        self.assertEqual(opened.failure_code, mismatch)
        self.assertEqual(self._authority_tail(), anchored)

        freshness = self._freshness(expectation)
        self.assertIs(freshness.state, _lb.AuthorizationFreshnessState.INDETERMINATE)
        self.assertEqual(freshness.underlying_failure_code, mismatch)
        self.assertEqual(self._authority_tail(), anchored)

        # Re-consumption is refused and appends nothing further.
        again = self._consume(expectation)
        self.assertEqual((again.outcome, again.receipt), ("INDETERMINATE", None))
        self.assertEqual(self._event_types(), durable)
        self.assertEqual(self._authority_tail(), anchored)
        for forbidden in (
            "RESTRICTED_SESSION_STARTED", "RESTRICTED_SESSION_ABANDONED", "WRITER_SESSION_STARTED",
        ):
            self.assertNotIn(forbidden, self._event_types())
        self.assertEqual(self._event_types().count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)


class AccountAggregateReleaseSemanticsTestCase(unittest.TestCase):
    """CORRECTION_07 C06-LB-01..10 / C07-06 / C07-AGG-001..005.

    Release / current-state evaluation and the CREATE candidate path share
    ONE aggregate numeric meaning, the three account leaves are compared
    inclusively, and an incomplete / conflicting / unequal-tail universe can
    never mint a usable aggregate snapshot.
    """

    MARKET_A = "MKT-A"
    MARKET_B = "MKT-B"
    T0 = "2026-08-13T20:00:00.000000Z"
    READ_SET_ID = "ADRS2_" + "b" * 64

    def _config(
        self,
        *,
        max_aggregate_exposure_usd=Decimal("100"),
        max_aggregate_working_orders=50,
        max_aggregate_working_contracts=Decimal("100"),
        max_conservative_unresolved_write_exposure_usd=Decimal("1"),
    ) -> RiskLimitConfigV1:
        """Only the three existing account leaves vary; no new leaf exists.

        The conservative unresolved-exposure leaf is left generous so these
        tests isolate the three AGGREGATE predicates rather than re-testing
        the separate predecessor unresolved-write predicate.
        """
        return RiskLimitConfigV1(
            1, "KALSHI|KALSHI_DEMO|SYNTHETIC|SUBACCOUNT=0", "USD",
            PerOrderRiskLimits(Decimal("10"), Decimal("10"), True, Decimal("0.10"), 1_000),
            PerMarketRiskLimits(Decimal("20"), Decimal("20"), 10, Decimal("20"), Decimal("20")),
            AccountRiskLimits(
                max_aggregate_exposure_usd, max_aggregate_working_orders,
                max_aggregate_working_contracts, 0,
                max_conservative_unresolved_write_exposure_usd,
            ),
            FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
        )

    def _fill(self, market, fill_id, side, quantity, yes_price):
        return EconomicFillV1(market, fill_id, side, quantity, yes_price, self.T0)

    def _order(self, market, order_id, side, remaining, yes_price):
        return WorkingOrderV1(market, order_id, side, remaining, yes_price)

    def _risk(self, *, fills=(), orders=(), unresolved=Decimal("0")):
        return ReleaseRiskSnapshotV1(tuple(fills), tuple(orders), 0, unresolved, {})

    def _release_pass(self, risk, config):
        return _lb.ReleaseLedgerHandle._economic_release_pass(risk, config)

    # -- C06-LB-01 ------------------------------------------------------

    def test_c06_lb_01_release_uses_the_same_shared_numeric_helper_as_the_candidate_path(self) -> None:
        """The release aggregate equals the shared helper's totals exactly,
        for a genuinely multi-market universe including unresolved exposure."""

        fills = (
            self._fill(self.MARKET_A, "f1", "YES", Decimal("1.00"), Decimal("0.40")),
            self._fill(self.MARKET_B, "f2", "NO", Decimal("1.00"), Decimal("0.25")),
        )
        orders = (
            self._order(self.MARKET_A, "o1", "YES", Decimal("1.00"), Decimal("0.30")),
            self._order(self.MARKET_B, "o2", "NO", Decimal("1.00"), Decimal("0.90")),
        )
        unresolved = Decimal("0.05")
        totals = compute_account_aggregate_totals(
            fills=fills, working_orders=orders, unresolved_exposure=unresolved,
        )
        expected = unresolved + Decimal("0.4000") + Decimal("0.3000") + Decimal("0.7500") + Decimal("0.1000")
        self.assertEqual(totals.aggregate_exposure_usd, expected)
        self.assertEqual(totals.aggregate_working_orders, 2)
        self.assertEqual(totals.aggregate_working_contracts, Decimal("2.00"))

        risk = self._risk(fills=fills, orders=orders, unresolved=unresolved)
        # Release passes at exactly the helper's totals and fails one
        # representable step below each of them -- i.e. it is deciding on the
        # same numbers, not a parallel derivation.
        exact = self._config(
            max_aggregate_exposure_usd=totals.aggregate_exposure_usd,
            max_aggregate_working_orders=totals.aggregate_working_orders,
            max_aggregate_working_contracts=totals.aggregate_working_contracts,
        )
        self.assertTrue(self._release_pass(risk, exact))
        self.assertTrue(account_aggregate_current_state_within_limits(totals, exact))

        for tighter in (
            self._config(max_aggregate_exposure_usd=totals.aggregate_exposure_usd - Decimal("0.000001")),
            self._config(max_aggregate_working_orders=totals.aggregate_working_orders - 1),
            self._config(max_aggregate_working_contracts=totals.aggregate_working_contracts - Decimal("0.01")),
        ):
            self.assertFalse(self._release_pass(risk, tighter))
            self.assertFalse(account_aggregate_current_state_within_limits(totals, tighter))

    # -- C06-LB-02..05 --------------------------------------------------

    def test_c06_lb_02_and_03_release_exposure_equality_passes_and_micro_excess_fails(self) -> None:
        orders = (self._order(self.MARKET_A, "o1", "YES", Decimal("1.00"), Decimal("0.30")),)
        risk = self._risk(orders=orders, unresolved=Decimal("0.20"))
        total = Decimal("0.20") + Decimal("0.3000")

        self.assertTrue(self._release_pass(risk, self._config(max_aggregate_exposure_usd=total)))
        self.assertFalse(self._release_pass(
            risk, self._config(max_aggregate_exposure_usd=total - Decimal("0.000001")),
        ))

    def test_c06_lb_04_release_working_orders_equality_passes_and_plus_one_fails(self) -> None:
        orders = (
            self._order(self.MARKET_A, "o1", "YES", Decimal("1.00"), Decimal("0.10")),
            self._order(self.MARKET_B, "o2", "YES", Decimal("1.00"), Decimal("0.10")),
        )
        risk = self._risk(orders=orders)

        self.assertTrue(self._release_pass(risk, self._config(max_aggregate_working_orders=2)))
        self.assertFalse(self._release_pass(risk, self._config(max_aggregate_working_orders=1)))

    def test_c06_lb_05_release_working_contracts_equality_passes_and_plus_hundredth_fails(self) -> None:
        orders = (
            self._order(self.MARKET_A, "o1", "YES", Decimal("1.00"), Decimal("0.10")),
            self._order(self.MARKET_B, "o2", "YES", Decimal("1.00"), Decimal("0.10")),
        )
        risk = self._risk(orders=orders)

        self.assertTrue(self._release_pass(risk, self._config(max_aggregate_working_contracts=Decimal("2.00"))))
        self.assertFalse(self._release_pass(
            risk, self._config(max_aggregate_working_contracts=Decimal("2.00") - Decimal("0.01")),
        ))

    # -- C06-LB-06 ------------------------------------------------------

    def test_c06_lb_06_universe_spans_markets_and_retains_fills_after_an_order_stops_resting(self) -> None:
        """A multi-market universe is aggregated across markets, and a fill's
        exposure survives its order leaving the working set."""

        fills = (
            self._fill(self.MARKET_A, "f1", "YES", Decimal("1.00"), Decimal("0.40")),
            self._fill(self.MARKET_B, "f2", "YES", Decimal("1.00"), Decimal("0.60")),
        )
        resting = (self._order(self.MARKET_A, "o1", "YES", Decimal("1.00"), Decimal("0.30")),)

        while_resting = compute_account_aggregate_totals(
            fills=fills, working_orders=resting, unresolved_exposure=Decimal("0"),
        )
        after_terminal = compute_account_aggregate_totals(
            fills=fills, working_orders=(), unresolved_exposure=Decimal("0"),
        )

        self.assertEqual(while_resting.markets, (self.MARKET_A, self.MARKET_B))
        self.assertEqual(while_resting.aggregate_exposure_usd, Decimal("1.0000") + Decimal("0.3000"))
        self.assertEqual(after_terminal.markets, (self.MARKET_A, self.MARKET_B))
        self.assertEqual(after_terminal.aggregate_exposure_usd, Decimal("1.0000"))
        self.assertEqual(after_terminal.aggregate_working_orders, 0)
        self.assertEqual(after_terminal.aggregate_working_contracts, Decimal("0"))

    # -- C06-LB-07 ------------------------------------------------------

    def test_c06_lb_07_order_or_fill_identity_conflict_prevents_a_usable_aggregate_universe(self) -> None:
        """Conflicting durable identities fail closed: the shared helper
        rejects contradictory fills, and any derived conflict id makes the
        aggregate input unconstructable."""

        contradictory = (
            EconomicFillV1(self.MARKET_A, "f1", "YES", Decimal("1.00"), Decimal("0.40"), self.T0),
            EconomicFillV1(self.MARKET_A, "f1", "YES", Decimal("2.00"), Decimal("0.40"), self.T0),
        )
        with self.assertRaises(RiskControlError) as caught:
            compute_account_aggregate_totals(
                fills=contradictory, working_orders=(), unresolved_exposure=Decimal("0"),
            )
        self.assertIs(caught.exception.code, RiskControlCode.RISK_INPUT_UNAVAILABLE)

        duplicate_orders = (
            self._order(self.MARKET_A, "o1", "YES", Decimal("1.00"), Decimal("0.30")),
            self._order(self.MARKET_A, "o1", "YES", Decimal("1.00"), Decimal("0.30")),
        )
        with self.assertRaises(RiskControlError):
            compute_account_aggregate_totals(
                fills=(), working_orders=duplicate_orders, unresolved_exposure=Decimal("0"),
            )

        with self.assertRaises(RiskControlError):
            self._aggregate_input(conflict_ids=("fill-identity:f1",))

    # -- C06-LB-08 ------------------------------------------------------

    def _aggregate_input(self, **overrides) -> AccountAggregateInputV1:
        config = self._config()
        values = dict(
            conflict_domain_ref=config.conflict_domain,
            authority_namespace_id="ns-1",
            authority_instance_id="auth-1",
            ledger_instance_id="ledger-1",
            authority_trusted_sequence=5,
            authority_trusted_hash="c" * 64,
            ledger_terminal_sequence=5,
            ledger_terminal_hash="c" * 64,
            risk_config_sha256=config.sha256,
            trusted_dynamic_read_set_id=self.READ_SET_ID,
            reconciliation_snapshot_sha256="d" * 64,
            universe_completeness=ACCOUNT_AGGREGATE_UNIVERSE_COMPLETE,
            conflict_ids=(),
            fills=(),
            working_orders=(),
            unresolved_exposure_usd=Decimal("0"),
        )
        values.update(overrides)
        return AccountAggregateInputV1(**values)

    def test_c06_lb_08_unequal_authority_and_ledger_tails_cannot_mint_a_snapshot(self) -> None:
        # Equal tails are usable ...
        usable = self._aggregate_input()
        self.assertEqual(usable.authority_trusted_sequence, usable.ledger_terminal_sequence)

        # ... any inequality is not.
        with self.assertRaises(RiskControlError):
            self._aggregate_input(ledger_terminal_sequence=6)
        with self.assertRaises(RiskControlError):
            self._aggregate_input(authority_trusted_hash="e" * 64)
        # An incomplete universe is likewise unusable.
        with self.assertRaises(RiskControlError):
            self._aggregate_input(universe_completeness="INCOMPLETE")
        # And UNKNOWN unresolved exposure is never treated as zero.
        with self.assertRaises(RiskControlError) as caught:
            self._aggregate_input(unresolved_exposure_usd=UNKNOWN_UNBOUNDED)
        self.assertIs(caught.exception.code, RiskControlCode.UNKNOWN_UNBOUNDED_EXPOSURE)

    # -- C06-LB-09 ------------------------------------------------------

    def test_c06_lb_09_no_event_vocabulary_or_schema_revision_change_is_required(self) -> None:
        """The correction adds no event type and no schema revision: the
        aggregate is derived from the EXISTING durable ORDER_OBSERVED /
        FILL_OBSERVED vocabulary and the existing risk-limit schema."""

        self.assertEqual(self._config().schema_version, 1)
        # The aggregate derivation consumes only the existing economic
        # element types -- it introduces no event of its own.
        self.assertIn("ORDER_OBSERVED", {event.name for event in EventType})
        self.assertIn("FILL_OBSERVED", {event.name for event in EventType})
        self.assertNotIn(
            "ACCOUNT_AGGREGATE_EVALUATED", {event.name for event in EventType},
        )
        # No new risk-limit leaf: the account limits object still has exactly
        # its five predecessor fields.
        self.assertEqual(
            tuple(field.name for field in fields(AccountRiskLimits)),
            (
                "max_aggregate_exposure_usd", "max_aggregate_working_orders",
                "max_aggregate_working_contracts", "max_unresolved_write_count",
                "max_conservative_unresolved_write_exposure_usd",
            ),
        )

    # -- C06-LB-10 ------------------------------------------------------

    def test_c06_lb_10_unknown_unbounded_release_exposure_still_fails_closed(self) -> None:
        """The predecessor fail-closed release theorem is preserved: UNKNOWN
        unresolved exposure can never pass the economic release predicate,
        however small the market universe is."""

        risk = ReleaseRiskSnapshotV1((), (), 1, UNKNOWN_UNBOUNDED, {})
        self.assertFalse(self._release_pass(risk, self._config()))
        # A missing configuration is equally fail-closed.
        self.assertFalse(self._release_pass(self._risk(), None))


# ===========================================================================
# R1-D07 F03 HELD retained-root guard primitive -- PS-014 M01..M07/M09
# recording-model coverage (PS-008..012 under WG-004..016/024).  The actual
# B mechanics run unchanged; only B's five fixed private native operations
# (and the observed-ABI fact) are replaced, per test, by the TEST-ONLY
# recording model below.  No DLL, native API, filesystem target, credential,
# network or store is touched.  Model success is MODEL_ONLY_OFFLINE evidence:
# it proves no real native behavior, actor exclusion, history/currentness,
# enrollment or timing calibration.  (M08 pin/protection evidence is the
# unchanged G1/TS/TF regressions plus independent raw-blob verification; TB
# deliberately pins nothing, so no reverse pin cycle is introduced.)
# ===========================================================================

import builtins as _builtins
import contextlib as _contextlib
import importlib.util as _importlib_util
import inspect as _inspect
import io as _io
import itertools as _itertools
import os as _os
import re as _re
import socket as _socket
import struct as _struct
import tokenize as _tokenize

_RRG_T0 = 7_000_000_000
_RRG_TA = _RRG_T0 + 300_000_000_000
_RRG_PROC = "proc_" + "9" * 32
_RRG_VOLUME_GUID = "0000aaaa-1111-2222-3333-444455556666"
_RRG_SERIAL = 0x0123456789ABCDEF
_RRG_BUDGET = _lb._F03RRGModelBudgetV1(open_ns=1_000, query_ns=1_000, close_ns=1_000, later_reserve_ns=1_000_000)
_RRG_HANDLE_BASES = _itertools.count(1)
_RRG_SECTION_HEADER = (
    "# ===========================================================================\n"
    "# R1-D07 F03 HELD retained-root guard primitive"
)
_RRG_BASE_B_SHA256 = "d3219a0dfbfc864b204de219420553861ae1ca2cb9162797697242f39d4dd63a"
_RRG_B_PATH = Path(__file__).resolve().parents[1] / "src" / "arb" / "venues" / "kalshi" / "ledger_binding.py"
_RRG_OPEN_FAILURE = ("status", 0xC0000022, 0, 1, True)  # ACCESS_DENIED with a returned handle


def _rrg_join(parent: str, name: str) -> str:
    return parent + name if parent.endswith("\\") else parent + "\\" + name


def _rrg_code_only(source: str) -> str:
    kept = []
    for token in _tokenize.generate_tokens(_io.StringIO(source).readline):
        if token.type in (_tokenize.STRING, _tokenize.COMMENT):
            continue
        kept.append(token.string)
    return " ".join(kept).replace(" (", "(").replace(" .", ".").replace(". ", ".")


def _rrg_section_source() -> str:
    text = _RRG_B_PATH.read_text(encoding="utf-8")
    section = text.split(_RRG_SECTION_HEADER, 1)[1]
    return _RRG_SECTION_HEADER + section.split("\n\n\n__all__ = [", 1)[0]


class _RecordingRootModel:
    """TEST-ONLY recording model of B's fixed private native boundaries
    (NtCreateFile, GetFileInformationByHandleEx, GetFinalPathNameByHandleW,
    CloseHandle, GetLastError).  It decodes the actual owned call storage B
    builds, keeps a synthetic directory tree and handle table, advances a
    deterministic integer clock by ``step_ns`` per call and injects faults by
    call ordinal.  It touches no filesystem, DLL or native API."""

    ANCHOR = "\\??\\C:\\"

    def __init__(self, components=("b1", "kals", "ARB_LOCAL"), root="F03_TESTS", *, reuse=False, step_ns=1_000):
        self.base = 0x5A000000 + next(_RRG_HANDLE_BASES) * 0x1000
        self.reuse = reuse
        self.step_ns = step_ns
        self.now = _RRG_T0 + 1
        self.objects: dict = {}
        self.handles: dict = {}
        self.calls: list = []
        self.opens: list = []
        self.close_log: list = []
        self.storages: list = []
        self.violations: list = []
        self.faults: dict = {}
        self.expire_after: set = set()
        self.last_error_mode = "value"
        self.last_error_calls = 0
        self._next = self.base
        self.names = tuple(components) + (root,)
        self.order = ["C:\\"]
        self._add("C:\\", 1)
        path = "C:\\"
        for index, name in enumerate(self.names, start=2):
            path = _rrg_join(path, name)
            self._add(path, index)
            self.order.append(path)

    def _add(self, path: str, number: int) -> None:
        self.objects[path] = {
            "serial": _RRG_SERIAL, "id": bytes((number * 37 + k * 11) % 256 for k in range(16)),
            "attributes": 0x10, "tag": 0, "dos": "\\\\?\\" + path,
            "guid": "\\\\?\\Volume{" + _RRG_VOLUME_GUID + "}\\" + path[3:],
        }

    def identity(self, path: str):
        obj = self.objects[path]
        return _lb._F03RRGIdentityV1(
            volume_serial_64=f"{obj['serial']:016x}", file_id_128=obj["id"].hex(), final_dos_path=obj["dos"],
            final_guid_path=obj["guid"], attributes=obj["attributes"], reparse_tag=obj["tag"])

    def enrollment(self):
        edges = [_lb._F03RRGModelEdgeV1(self.ANCHOR, self.identity(self.order[0]))]
        for name, path in zip(self.names, self.order[1:]):
            edges.append(_lb._F03RRGModelEdgeV1(name, self.identity(path)))
        return _lb._F03RRGModelEnrollmentV1(ancestors=tuple(edges[:-1]), root=edges[-1])

    def clock(self) -> int:
        return self.now

    def _record(self, kind, *details):
        ordinal = len(self.calls) + 1
        self.calls.append((ordinal, kind) + details)
        self.now += self.step_ns
        return ordinal, self.faults.get(ordinal)

    def _done(self, ordinal, result):
        if ordinal in self.expire_after:
            self.now = max(self.now, _RRG_TA)
        return result

    def _allocate(self) -> int:
        if self.reuse:
            raw = self.base + 4
            while raw in self.handles:
                raw += 4
            return raw
        self._next += 4
        return self._next

    def _observed(self, path, fault):
        obj = dict(self.objects[path])
        if fault == "reparse":
            obj["attributes"] |= 0x400
            obj["tag"] = 0xA0000003
        elif fault == "tag":
            obj["tag"] = 0x80000017
        elif fault == "not_directory":
            obj["attributes"] = 0x20
        elif fault == "wrong_id":
            obj["id"] = bytes(reversed(obj["id"]))
        elif fault == "wrong_serial":
            obj["serial"] ^= 1
        elif fault == "wrong_dos":
            obj["dos"] += "x"
        elif fault == "case":
            head, separator, last = obj["dos"].rpartition("\\")
            obj["dos"] = head + separator + last[:1].swapcase() + last[1:]
        elif fault == "wrong_guid":
            obj["guid"] += "x"
        elif fault == "wrong_volume_guid":
            obj["guid"] = obj["guid"].replace(_RRG_VOLUME_GUID, "ffffffff-1111-2222-3333-444455556666")
        elif fault == "overlong":
            obj["dos"] = obj["dos"] + "\\" + "\u00e9" * 2100
        return obj

    # -- the five patched boundaries ----------------------------------------
    def nt_create_file(self, storage, access, allocation, attributes, share, disposition, options, ea, ea_length):
        length, maximum, buffer_ref = _struct.unpack_from("<HH4xQ", storage.unicode_string)
        oa_length, root, name_ref, oa_attributes, descriptor, qos = _struct.unpack_from(
            "<I4xQQI4xQQ", storage.object_attributes)
        name = bytes(storage.name_buffer[:length]).decode("utf-16-le")
        ordinal, fault = self._record("NtCreateFile", root, name)
        self.opens.append({
            "ordinal": ordinal, "root": root, "name": name,
            "args": (access, allocation, attributes, share, disposition, options, ea, ea_length),
            "length": length, "maximum": maximum, "buffer_ref": buffer_ref,
            "oa": (oa_length, name_ref, oa_attributes, descriptor, qos), "buffer_len": len(storage.name_buffer),
            "terminator": bytes(storage.name_buffer[length:]), "slot": bytes(storage.handle_slot),
            "iosb": bytes(storage.io_status_block), "live": frozenset(self.handles),
        })
        self.storages.append(storage)
        if fault == "exception":
            raise OSError("synthetic open exception")
        if isinstance(fault, tuple) and fault[0] == "raise" and fault[2] == "before":
            raise fault[1]("synthetic open-boundary raise before output publication")
        if fault == "malformed":
            return self._done(ordinal, "malformed")
        if root == 0:
            path = "C:\\" if name == self.ANCHOR else None
        else:
            parent = self.handles.get(root)
            path = None if parent is None else _rrg_join(parent, name)
        if path is None or path not in self.objects or fault == "missing":
            _struct.pack_into("<I4xQ", storage.io_status_block, 0, 0xC0000034, 0)
            return self._done(ordinal, -0x3FFFFFCC)  # STATUS_OBJECT_NAME_NOT_FOUND as a signed NTSTATUS
        status, iosb, information, raw = 0, 0, 1, None
        if fault == "pending":
            status = 0x103
        elif fault == "iosb_pending":
            iosb = 0x103
        elif isinstance(fault, tuple) and fault[0] == "status":
            status, iosb, information = fault[1:4]
            if not fault[4]:
                raw = 0
        if fault == "null_handle":
            raw = 0
        elif fault == "invalid_handle":
            raw = 0xFFFFFFFFFFFFFFFF
        elif fault == "duplicate":
            raw = next(iter(self.handles))
        if raw is None:
            raw = self._allocate()
            self.handles[raw] = path
        _struct.pack_into("<Q", storage.handle_slot, 0, raw)
        if status != 0x103:
            _struct.pack_into("<I4xQ", storage.io_status_block, 0, iosb, information)
        if isinstance(fault, tuple) and fault[0] == "raise" and fault[2] == "after":
            raise fault[1]("synthetic open-boundary raise after output publication")
        return self._done(ordinal, status)

    def get_info(self, handle, info_class, buffer, size):
        ordinal, fault = self._record("GetFileInformationByHandleEx", handle, info_class, size, len(buffer),
                                      handle in self.handles)
        if fault == "exception":
            raise OSError("synthetic query exception")
        if isinstance(fault, tuple) and fault[0] == "raise":
            raise fault[1]("synthetic query-boundary raise")
        path = self.handles.get(handle)
        if fault == "fail" or path is None:
            return self._done(ordinal, 0)
        obj = self._observed(path, fault)
        if info_class == 18:
            _struct.pack_into("<Q", buffer, 0, obj["serial"])
            buffer[8:24] = obj["id"]
        elif info_class == 9:
            _struct.pack_into("<II", buffer, 0, obj["attributes"], obj["tag"])
        else:
            self.violations.append(("info_class", ordinal))
            return self._done(ordinal, 0)
        if fault == "resize":
            buffer.append(0)
        return self._done(ordinal, 1)

    def get_final(self, handle, buffer, capacity, flags):
        ordinal, fault = self._record("GetFinalPathNameByHandleW", handle, capacity, flags, len(buffer),
                                      handle in self.handles)
        if fault == "exception":
            raise OSError("synthetic final-path exception")
        if isinstance(fault, tuple) and fault[0] == "raise":
            raise fault[1]("synthetic final-path-boundary raise")
        path = self.handles.get(handle)
        if fault == "zero" or path is None:
            return self._done(ordinal, 0)
        if fault == "truncated":
            return self._done(ordinal, capacity)
        if fault == "over":
            return self._done(ordinal, capacity + 7)
        obj = self._observed(path, fault)
        encoded = (obj["dos"] if flags == 0 else obj["guid"]).encode("utf-16-le")
        if fault == "lone_surrogate":
            encoded += b"\x00\xd8"
        buffer[: len(encoded)] = encoded
        buffer[len(encoded): len(encoded) + 2] = b"\x01\x00" if fault == "unterminated" else b"\x00\x00"
        if fault == "resize":
            buffer.extend(b"\x00\x00")
        return self._done(ordinal, len(encoded) // 2)

    def close(self, handle):
        ordinal, fault = self._record("CloseHandle", handle)
        self.close_log.append(handle)
        if fault == "exception":
            raise OSError("synthetic close exception")
        if isinstance(fault, tuple) and fault[0] == "raise":
            if fault[2] == "after" and handle in self.handles:
                del self.handles[handle]  # the close took effect, then the boundary was interrupted
            raise fault[1]("synthetic close-boundary raise")
        if fault == "fail":
            return self._done(ordinal, 0)
        if handle not in self.handles:
            self.violations.append(("close_unknown", ordinal))
            return self._done(ordinal, 0)
        del self.handles[handle]
        return self._done(ordinal, 1)

    def last_error(self):
        self.last_error_calls += 1
        if self.last_error_mode == "exception":
            raise OSError("synthetic last-error exception")
        if self.last_error_mode == "bad":
            return "not-an-integer"
        if isinstance(self.last_error_mode, type):
            raise self.last_error_mode("synthetic last-error-boundary raise")
        return 0x57

    @_contextlib.contextmanager
    def installed(self):
        with _contextlib.ExitStack() as stack:
            for name, function in (
                ("_f03_rrg_native_nt_create_file", self.nt_create_file),
                ("_f03_rrg_native_get_file_information_by_handle_ex", self.get_info),
                ("_f03_rrg_native_get_final_path_name_by_handle_w", self.get_final),
                ("_f03_rrg_native_close_handle", self.close),
                ("_f03_rrg_native_get_last_error", self.last_error),
                ("_f03_rrg_observed_abi", lambda: ("nt", 8, True)),
            ):
                stack.enter_context(_mock.patch.object(_lb, name, function))
            yield self

    def ordinals(self, kind, **match):
        selected = []
        for call in self.calls:
            if call[1] != kind:
                continue
            if "info_class" in match and call[3] != match["info_class"]:
                continue
            if "flags" in match and call[4] != match["flags"]:
                continue
            selected.append(call[0])
        return selected


class F03HeldRetainedRootGuardPrimitiveTests(unittest.TestCase):
    """PS-014 M01..M07/M09 for the held retained-root guard primitive."""

    # -- helpers -------------------------------------------------------------
    _DEFAULT = object()

    def _acquire(self, model, enrollment=_DEFAULT, **overrides):
        kwargs = dict(process_instance_id=_RRG_PROC, t0_ns=_RRG_T0, ta_ns=_RRG_TA,
                      monotonic_clock_ns=model.clock, budget=_RRG_BUDGET)
        kwargs.update(overrides)
        with model.installed():
            return _lb._f03_rrg_acquire_model_chain_v1(
                model.enrollment() if enrollment is self._DEFAULT else enrollment, **kwargs)

    def _refused(self, model, enrollment=_DEFAULT, **overrides):
        with self.assertRaises(_lb._F03RootGuardRefusal) as context:
            self._acquire(model, enrollment, **overrides)
        return context.exception

    def _release(self, model, chain, pid=_RRG_PROC):
        with model.installed():
            return _lb._f03_rrg_release_model_chain_v1(chain, process_instance_id=pid)

    def _revalidate(self, model, chain, pid=_RRG_PROC):
        with model.installed():
            return _lb._f03_rrg_revalidate_model_chain_v1(chain, process_instance_id=pid)

    @staticmethod
    def _attempt(chain):
        return object.__getattribute__(chain, "_attempt")

    def _nominal(self, **model_kwargs):
        model = _RecordingRootModel(**model_kwargs)
        chain = self._acquire(model)
        acquisition = _RecordingRootModel(**model_kwargs)
        acquisition.calls = list(model.calls)
        self._release(model, chain)
        return acquisition

    def _assert_rollback(self, model, refusal, *, quarantined=False):
        report = refusal.report
        self.assertIsNotNone(report)
        self.assertEqual(report.evidence_class, "MODEL_ONLY_OFFLINE")
        self.assertEqual(report.primary, refusal.code)
        self.assertEqual(model.violations, [])
        self.assertEqual(report.close_attempts, report.close_successes + report.close_uncertain)
        self.assertLessEqual(report.max_live, 66)
        self.assertEqual(len(model.close_log), len(set(model.close_log)))  # close-once
        self.assertIs(report.quarantined, quarantined)
        if quarantined:
            self.assertEqual(report.cleanup_outcome, "PENDING_QUARANTINED_NO_CLEAN_CLAIM")
        elif report.close_uncertain == 0:
            self.assertEqual(model.handles, {})
            self.assertEqual(report.cleanup_outcome, "CLOSED_ALL_REGISTERED")
        else:
            self.assertEqual(report.cleanup_outcome, "CLOSE_UNCERTAIN")
        # Rollback order: transient R first, then G deepest-first.
        tail = []
        for event in reversed(report.lifecycle):
            if event[0] != "CLOSE":
                break
            tail.append(event)
        tail.reverse()
        roles = [event[2] for event in tail]
        r_count = roles.count("R")
        self.assertEqual(roles[:r_count], ["R"] * r_count)
        g_generations = [event[1] for event in tail if event[2] != "R"]
        self.assertEqual(g_generations, sorted(g_generations, reverse=True))
        return report

    # -- M01 names / ABI -----------------------------------------------------
    def test_m01_component_names_boundaries_and_every_rejected_spelling(self) -> None:
        valid = _lb._f03_rrg_valid_component
        for name in ("a" * 128, "\U0001F600" * 64, "F03_TESTS", "a.b", "\u00e9t\u00e9", "x" * 127 + "y"):
            self.assertTrue(valid(name), name[:12])
        for name in (
            "", ".", "..", "a/b", "a\\b", "a:", "x\x00", "x.", "x ", "a" * 129, "a" * 127 + "\U0001F600",
            "\ud800", "\udc00", "a\ud800b", "\ud83d\ude00", "CON", "nul.txt", "com1", "LPT9", "CONIN$", "aux ",
            "\\??\\C:", "\\\\server\\share", "C:", "\\\\.\\device", None, b"bytes", 5,
        ):
            self.assertFalse(valid(name), repr(name)[:24])

    def test_m01_prevalidation_failure_makes_zero_model_opens(self) -> None:
        base = _RecordingRootModel()
        enrollment = base.enrollment()
        bad_names = ("..", "a/b", "x.", "\ud800", "CON", "a" * 129)
        for bad in bad_names:
            model = _RecordingRootModel()
            root = _lb._F03RRGModelEdgeV1(bad, enrollment.root.expected)
            refusal = self._refused(model, _lb._F03RRGModelEnrollmentV1(ancestors=enrollment.ancestors, root=root))
            self.assertIn(refusal.code, {"COMPONENT_NAME_REFUSED", "ENROLLMENT_LEXICAL_MISMATCH"})
            self.assertIsNone(refusal.report)
            self.assertEqual(model.calls, [])
        for anchor_name in ("\\??\\c:\\", "\\??\\C:", "C:\\", "\\??\\D:\\", "\\\\?\\C:\\"):
            model = _RecordingRootModel()
            ancestors = (_lb._F03RRGModelEdgeV1(anchor_name, enrollment.ancestors[0].expected),) + enrollment.ancestors[1:]
            refusal = self._refused(model, _lb._F03RRGModelEnrollmentV1(ancestors=ancestors, root=enrollment.root))
            self.assertEqual(refusal.code, "ANCHOR_REFUSED")
            self.assertEqual(model.calls, [])
        for malformed in (None, {"ancestors": ()}, enrollment.root):
            model = _RecordingRootModel()
            self.assertEqual(self._refused(model, malformed).code, "ENROLLMENT_MALFORMED")
            self.assertEqual(model.calls, [])
        model = _RecordingRootModel()
        self.assertEqual(self._refused(model, process_instance_id="").code, "PROCESS_INSTANCE_INVALID")
        self.assertEqual(model.calls, [])

    def test_m01_x64_abi_layout_and_pre_entry_rejection(self) -> None:
        sizes = {name: (_struct.calcsize(layout), size) for name, layout, size, _ in _lb._F03_RRG_ABI_LAYOUTS}
        self.assertEqual(sizes, {"UNICODE_STRING": (16, 16), "OBJECT_ATTRIBUTES": (48, 48), "IO_STATUS_BLOCK": (16, 16)})
        offsets = {(name, field): _struct.calcsize(preceding)
                   for name, _, _, fields_ in _lb._F03_RRG_ABI_LAYOUTS for field, preceding, _ in fields_}
        self.assertEqual(offsets, {
            ("UNICODE_STRING", "Length"): 0, ("UNICODE_STRING", "MaximumLength"): 2, ("UNICODE_STRING", "Buffer"): 8,
            ("OBJECT_ATTRIBUTES", "Length"): 0, ("OBJECT_ATTRIBUTES", "RootDirectory"): 8,
            ("OBJECT_ATTRIBUTES", "ObjectName"): 16, ("OBJECT_ATTRIBUTES", "Attributes"): 24,
            ("OBJECT_ATTRIBUTES", "SecurityDescriptor"): 32, ("OBJECT_ATTRIBUTES", "SecurityQualityOfService"): 40,
            ("IO_STATUS_BLOCK", "Status"): 0, ("IO_STATUS_BLOCK", "Information"): 8,
        })
        for observed in (("posix", 8, True), ("nt", 4, False), ("nt", 8, False), ("nt", 4, True)):
            model = _RecordingRootModel()
            with model.installed(), _mock.patch.object(_lb, "_f03_rrg_observed_abi", lambda value=observed: value):
                with self.assertRaises(_lb._F03RootGuardRefusal) as context:
                    _lb._f03_rrg_acquire_model_chain_v1(
                        model.enrollment(), process_instance_id=_RRG_PROC, t0_ns=_RRG_T0, ta_ns=_RRG_TA,
                        monotonic_clock_ns=model.clock, budget=_RRG_BUDGET)
            self.assertEqual(context.exception.code, "ABI_UNSUPPORTED")
            self.assertEqual(model.calls, [])
        broken = (("UNICODE_STRING", "<HH4xQ", 16, (("Buffer", "<HH", 8),)),)
        model = _RecordingRootModel()
        with _mock.patch.object(_lb, "_F03_RRG_ABI_LAYOUTS", broken):
            self.assertEqual(self._refused(model).code, "ABI_LAYOUT_REFUSED")
        self.assertEqual(model.calls, [])

    def test_m01_owned_terminated_storage_and_ushort_bounds(self) -> None:
        storage = _lb._F03RRGCallStorageV1("b1", 0x5A5A0004)
        self.assertEqual(_struct.unpack("<HH4xQ", bytes(storage.unicode_string)), (4, 6, 0x1))
        self.assertEqual(bytes(storage.name_buffer), b"b\x001\x00\x00\x00")
        self.assertEqual(_struct.unpack("<I4xQQI4xQQ", bytes(storage.object_attributes)), (48, 0x5A5A0004, 0x2, 0, 0, 0))
        self.assertEqual(bytes(storage.io_status_block), bytes(16))
        self.assertEqual(bytes(storage.handle_slot), bytes(8))
        _lb._F03RRGCallStorageV1("a" * 32766, 0)  # Length 65532, MaximumLength 65534
        for name, code in (("a" * 32767, "UNICODE_STRING_BOUNDS_REFUSED"), ("", "UNICODE_STRING_BOUNDS_REFUSED"),
                           ("\ud800", "NAME_ENCODING_REFUSED")):
            with self.assertRaises(_lb._F03RootGuardRefusal) as context:
                _lb._F03RRGCallStorageV1(name, 0)
            self.assertEqual(context.exception.code, code)

    def test_m01_exact_g_and_r_argument_tuples_and_owned_call_storage(self) -> None:
        model = _RecordingRootModel()
        chain = self._acquire(model)
        attempt = self._attempt(chain)
        g_args = (0x001000A1, None, 0, 3, 1, 0x21, None, 0)
        r_args = (0x001000A1, None, 0, 7, 1, 0x00200020, None, 0)
        roles = [entry.role for entry in attempt.entries]
        self.assertEqual(len(model.opens), len(roles))
        self.assertEqual(model.opens[0]["root"], 0)
        self.assertEqual(model.opens[0]["name"], "\\??\\C:\\")
        for record, entry in zip(model.opens, attempt.entries):
            self.assertEqual(record["args"], r_args if entry.role == "R" else g_args)
            self.assertNotIn(record["args"][5], (0x00200021,))
            self.assertEqual(record["maximum"], record["length"] + 2)
            self.assertEqual(record["buffer_len"], record["maximum"])
            self.assertEqual(record["terminator"], b"\x00\x00")
            self.assertEqual(record["buffer_ref"], 0x1)
            self.assertEqual(record["oa"], (48, 0x2, 0, 0, 0))
            self.assertEqual(record["slot"], bytes(8))
            self.assertEqual(record["iosb"], bytes(16))
            if entry.role != "G_ANCHOR":
                self.assertIn(record["root"], record["live"])  # exact registered live parent
        for storage in model.storages:
            self.assertEqual(storage.state, "RELEASED")
        self._release(model, chain)

    # -- M02 status / pending -------------------------------------------------
    def test_m02_only_exact_zero_zero_one_success_is_accepted(self) -> None:
        nominal = self._nominal()
        open_points = nominal.ordinals("NtCreateFile")
        cases = (
            (("status", 0xC0000022, 0xC0000022, 0, False), "OPEN_REFUSED", False),
            (("status", 0xC0000022, 0, 1, True), "OPEN_REFUSED", True),
            (("status", -0x3FFFFFDE, 0, 1, True), "OPEN_REFUSED", True),  # signed NTSTATUS form
            (("status", 0x40000000, 0, 1, True), "OPEN_REFUSED", True),  # informational
            (("status", 0x80000005, 0, 1, True), "OPEN_REFUSED", True),  # warning
            (("status", 0x00000001, 0, 1, True), "OPEN_REFUSED", True),  # nonnegative is not enough
            (("status", 0, 0, 2, True), "OPEN_REFUSED", True),  # FILE_CREATED
            (("status", 0, 0, 0, True), "OPEN_REFUSED", True),
            (("status", 0, 0, 3, True), "OPEN_REFUSED", True),
            (("status", 0, 0xC0000001, 1, True), "OPEN_REFUSED", True),
            ("null_handle", "OPEN_REFUSED", False),
            ("invalid_handle", "OPEN_REFUSED", False),
            ("missing", "OPEN_OBJECT_MISSING", False),
        )
        for ordinal in (open_points[0], open_points[1], open_points[2], open_points[-1]):
            for fault, code, registered in cases:
                with self.subTest(ordinal=ordinal, fault=fault):
                    model = _RecordingRootModel()
                    model.faults[ordinal] = fault
                    refusal = self._refused(model)
                    self.assertEqual(refusal.code, code)
                    report = self._assert_rollback(model, refusal)
                    self.assertEqual(report.raw_statuses[-1][0], "OPEN")
                    self.assertTrue(all(0 <= value <= 0xFFFFFFFF for value in report.raw_statuses[-1][1:3]))
                    failed_raw = _struct.unpack("<Q", bytes(model.storages[-1].handle_slot))[0]
                    closes = model.close_log.count(failed_raw)
                    self.assertEqual(closes, 1 if registered else 0)
                    self.assertTrue(all(call[1] == "CloseHandle" for call in model.calls[ordinal:]))

    def test_m02_pending_quarantines_storage_and_ownership_without_clean_claim(self) -> None:
        nominal = self._nominal()
        for ordinal in nominal.ordinals("NtCreateFile")[:3] + nominal.ordinals("NtCreateFile")[-1:]:
            for fault, code in (("pending", "OPEN_PENDING_QUARANTINED"), ("iosb_pending", "OPEN_PENDING_QUARANTINED"),
                                ("exception", "OPEN_EXCEPTION_COMPLETION_UNKNOWN"),
                                ("malformed", "OPEN_STATUS_MALFORMED")):
                with self.subTest(ordinal=ordinal, fault=fault):
                    model = _RecordingRootModel()
                    model.faults[ordinal] = fault
                    refusal = self._refused(model)
                    self.assertEqual(refusal.code, code)
                    report = self._assert_rollback(model, refusal, quarantined=True)
                    self.assertEqual(model.calls[-1][0], ordinal)  # no wait/resume/retry/close afterwards
                    storage = model.storages[-1]
                    self.assertEqual(storage.state, "QUARANTINED")
                    self.assertTrue(any(kept is storage for kept, _ in _lb._F03_RRG_PENDING_QUARANTINE))
                    attempt = next(owner for kept, owner in _lb._F03_RRG_PENDING_QUARANTINE if kept is storage)
                    for entry in attempt.entries:
                        if entry.state in ("ACQUIRED_UNVALIDATED", "VALIDATED"):
                            self.assertTrue(entry.quarantined)
                            self.assertIs(_lb._F03_RRG_LIVE_HANDLES.get(entry.raw), entry)  # never freed
                    self.assertNotIn(report.cleanup_outcome, {"CLOSED_ALL_REGISTERED"})

    def test_m02_duplicate_live_handle_never_creates_a_second_owner(self) -> None:
        nominal = self._nominal()
        for ordinal in nominal.ordinals("NtCreateFile")[1:]:
            with self.subTest(ordinal=ordinal):
                model = _RecordingRootModel()
                model.faults[ordinal] = "duplicate"
                refusal = self._refused(model)
                self.assertEqual(refusal.code, "DUPLICATE_LIVE_HANDLE")
                report = self._assert_rollback(model, refusal)
                self.assertEqual(report.registrations, len({entry for entry in model.close_log}))

    # -- M03 queries ----------------------------------------------------------
    def test_m03_exact_same_handle_query_classes_buffers_flags_and_native_order(self) -> None:
        model = _RecordingRootModel()
        chain = self._acquire(model)
        attempt = self._attempt(chain)
        queries = [call for call in model.calls if call[1] != "NtCreateFile" and call[1] != "CloseHandle"]
        self.assertEqual(len(queries) % 4, 0)
        for index in range(0, len(queries), 4):
            group = queries[index:index + 4]
            self.assertEqual([call[1] for call in group], [
                "GetFileInformationByHandleEx", "GetFileInformationByHandleEx",
                "GetFinalPathNameByHandleW", "GetFinalPathNameByHandleW"])
            self.assertEqual(group[0][3:6], (18, 24, 24))
            self.assertEqual(group[1][3:6], (9, 8, 8))
            self.assertEqual(group[2][3:6], (32768, 0, 65536))
            self.assertEqual(group[3][3:6], (32768, 1, 65536))
            self.assertEqual(len({call[2] for call in group}), 1)  # one registered handle
            self.assertTrue(all(call[-1] is True for call in group))  # live at every query
        for entry, path in zip(attempt.chain, model.order):
            self.assertEqual(entry.identity, model.identity(path))
            self.assertEqual(entry.identity.file_id_128, model.objects[path]["id"].hex())  # native byte order
            self.assertEqual(entry.identity.volume_serial_64, "0123456789abcdef")
        self._release(model, chain)
        reordered = _RecordingRootModel()
        enrollment = reordered.enrollment()
        root = enrollment.root.expected
        swapped = _lb._F03RRGModelEdgeV1(enrollment.root.name, _lb._F03RRGIdentityV1(
            volume_serial_64=root.volume_serial_64, file_id_128=bytes(reversed(bytes.fromhex(root.file_id_128))).hex(),
            final_dos_path=root.final_dos_path, final_guid_path=root.final_guid_path, attributes=0x10, reparse_tag=0))
        refusal = self._refused(reordered, _lb._F03RRGModelEnrollmentV1(ancestors=enrollment.ancestors, root=swapped))
        self.assertEqual(refusal.code, "IDENTITY_MISMATCH")
        self._assert_rollback(reordered, refusal)

    def test_m03_every_query_refusal_is_terminal_without_retry_or_resize(self) -> None:
        nominal = self._nominal()
        file_id = nominal.ordinals("GetFileInformationByHandleEx", info_class=18)
        attribute = nominal.ordinals("GetFileInformationByHandleEx", info_class=9)
        dos = nominal.ordinals("GetFinalPathNameByHandleW", flags=0)
        guid = nominal.ordinals("GetFinalPathNameByHandleW", flags=1)
        # Index 1 = the first transient R query (edge 1); index 2 = its G; index -1 = final revalidation.
        cases = (
            (attribute, "not_directory", "NOT_DIRECTORY"), (attribute, "reparse", "REPARSE_REFUSED"),
            (attribute, "tag", "REPARSE_REFUSED"), (file_id, "wrong_id", "IDENTITY_MISMATCH"),
            (file_id, "wrong_serial", "VOLUME_CHANGED"), (dos, "wrong_dos", "IDENTITY_MISMATCH"),
            (dos, "case", "IDENTITY_MISMATCH"), (guid, "wrong_guid", "IDENTITY_MISMATCH"),
            (guid, "wrong_volume_guid", "VOLUME_CHANGED"), (dos, "overlong", "FINAL_PATH_MALFORMED"),
            (dos, "zero", "FINAL_PATH_FAILED"), (guid, "truncated", "FINAL_PATH_TRUNCATED"),
            (dos, "over", "FINAL_PATH_TRUNCATED"), (guid, "unterminated", "FINAL_PATH_MALFORMED"),
            (dos, "lone_surrogate", "FINAL_PATH_MALFORMED"), (dos, "resize", "FINAL_PATH_MALFORMED"),
            (file_id, "fail", "QUERY_FAILED"), (attribute, "exception", "QUERY_EXCEPTION"),
            (guid, "exception", "QUERY_EXCEPTION"), (file_id, "resize", "QUERY_BUFFER_INVALID"),
        )
        for points, fault, code in cases:
            for ordinal in (points[1], points[2], points[-1]):
                with self.subTest(fault=fault, ordinal=ordinal):
                    model = _RecordingRootModel()
                    model.faults[ordinal] = fault
                    refusal = self._refused(model)
                    self.assertEqual(refusal.code, code)
                    report = self._assert_rollback(model, refusal)
                    self.assertTrue(all(call[1] == "CloseHandle" for call in model.calls[ordinal:]))
                    if fault in {"zero", "fail"}:
                        self.assertEqual(report.last_errors[-1][1], 0x57)  # captured immediately
                    if fault == "exception":
                        self.assertEqual(report.last_errors[-1][1], "UNAVAILABLE")
        for mode in ("exception", "bad"):
            model = _RecordingRootModel()
            model.last_error_mode = mode
            model.faults[file_id[1]] = "fail"
            refusal = self._refused(model)
            self.assertEqual(refusal.report.last_errors[-1], ("FileIdInfo", "UNAVAILABLE"))

    # -- M04 descent / capacity -----------------------------------------------
    def test_m04_one_ancestor_retained_descent_and_handoff_order(self) -> None:
        model = _RecordingRootModel(components=())
        chain = self._acquire(model)
        attempt = self._attempt(chain)
        self.assertEqual([entry.role for entry in attempt.chain], ["G_ANCHOR", "G"])
        events = [(event[0], event[2]) for event in chain.report().lifecycle]
        self.assertEqual(events, [
            ("OPEN", "G_ANCHOR"), ("REGISTERED", "G_ANCHOR"), ("QUERIED", "G_ANCHOR"),
            ("OPEN", "R"), ("REGISTERED", "R"), ("QUERIED", "R"),
            ("OPEN", "G"), ("REGISTERED", "G"), ("QUERIED", "G"),
            ("QUERIED", "G_ANCHOR"), ("QUERIED", "G"), ("CLOSE", "R"),
            ("QUERIED", "G_ANCHOR"), ("QUERIED", "G"),
        ])
        report = self._release(model, chain)
        self.assertEqual([event[2] for event in report.lifecycle[-2:]], ["G", "G_ANCHOR"])
        self.assertEqual(model.handles, {})
        self.assertEqual((report.close_attempts, report.close_successes, report.close_uncertain), (3, 3, 0))

    def test_m04_sixty_four_ancestors_exact_65_persistent_66_native_bound(self) -> None:
        components = tuple(f"d{index:02d}" for index in range(63))
        model = _RecordingRootModel(components=components)
        chain = self._acquire(model)
        attempt = self._attempt(chain)
        self.assertEqual(len(attempt.chain), 65)
        self.assertEqual(chain.report().max_live, 66)
        self.assertTrue(all(entry.state == "CLOSED" for entry in attempt.entries if entry.role == "R"))
        chain_raws = [entry.raw for entry in attempt.chain]
        # Every relative open happens while EVERY previously accepted G is live.
        accepted = 1
        for record in model.opens[1:]:
            self.assertTrue(set(chain_raws[:accepted]) <= record["live"])
            self.assertEqual(record["root"], chain_raws[accepted - 1])
            if record["args"][3] == 3:
                accepted += 1
        report = self._release(model, chain)
        g_closes = [event[1] for event in report.lifecycle if event[0] == "CLOSE" and event[2] != "R"]
        self.assertEqual(g_closes, sorted(g_closes, reverse=True))
        self.assertEqual(model.handles, {})
        too_many = _RecordingRootModel(components=tuple(f"d{index:02d}" for index in range(64)))
        self.assertEqual(self._refused(too_many).code, "ANCESTOR_COUNT_REFUSED")  # 65 ancestors: no truncation
        self.assertEqual(too_many.calls, [])
        empty = _RecordingRootModel()
        self.assertEqual(self._refused(empty, _lb._F03RRGModelEnrollmentV1(
            ancestors=(), root=empty.enrollment().root)).code, "ANCESTOR_COUNT_REFUSED")
        self.assertEqual(empty.calls, [])
        self.assertEqual((_lb._F03_RRG_MAX_ANCESTORS, _lb._F03_RRG_MAX_PERSISTENT_G, _lb._F03_RRG_MAX_B_HANDLES),
                         (64, 65, 66))
        self.assertEqual(set(_lb._F03_RRG_ROLE_PROFILES), {"G_ANCHOR", "G", "R"})  # no D/W role implemented

    def test_m04_capacity_reserved_before_open_and_duplicate_objects_refused(self) -> None:
        # Anchor G, edge-1 R and G, then edge-2 R: the next open would exceed the patched bound.
        for limit_name, limit, expected_opens in (("_F03_RRG_MAX_B_HANDLES", 3, 4), ("_F03_RRG_MAX_PERSISTENT_G", 2, 4)):
            model = _RecordingRootModel()
            with _mock.patch.object(_lb, limit_name, limit):
                refusal = self._refused(model)
            self.assertEqual(refusal.code, "HANDLE_CAPACITY_REFUSED")
            self.assertEqual(len(model.opens), expected_opens)  # refused BEFORE the over-limit open
            self._assert_rollback(model, refusal)
        model = _RecordingRootModel()
        enrollment = model.enrollment()
        clone = _lb._F03RRGModelEdgeV1(enrollment.root.name, _lb._F03RRGIdentityV1(
            volume_serial_64=enrollment.root.expected.volume_serial_64,
            file_id_128=enrollment.ancestors[1].expected.file_id_128,
            final_dos_path=enrollment.root.expected.final_dos_path,
            final_guid_path=enrollment.root.expected.final_guid_path, attributes=0x10, reparse_tag=0))
        refusal = self._refused(model, _lb._F03RRGModelEnrollmentV1(ancestors=enrollment.ancestors, root=clone))
        self.assertEqual(refusal.code, "ENROLLMENT_DUPLICATE_OBJECT")
        self.assertEqual(model.calls, [])

    # -- M05 ownership ----------------------------------------------------------
    def test_m05_failure_at_every_recorded_boundary_rolls_back_once(self) -> None:
        nominal = self._nominal()
        modes = {
            "NtCreateFile": ((_RRG_OPEN_FAILURE, "OPEN_REFUSED"), ("exception", "OPEN_EXCEPTION_COMPLETION_UNKNOWN")),
            "GetFileInformationByHandleEx": (("fail", "QUERY_FAILED"), ("exception", "QUERY_EXCEPTION")),
            "GetFinalPathNameByHandleW": (("zero", "FINAL_PATH_FAILED"), ("exception", "QUERY_EXCEPTION")),
            "CloseHandle": (("fail", "CLOSE_FAILED"), ("exception", "CLOSE_EXCEPTION")),
        }
        self.assertEqual(len(nominal.calls), 101)
        for ordinal, kind, *_ in nominal.calls:
            for fault, code in modes[kind]:
                with self.subTest(ordinal=ordinal, fault=fault):
                    model = _RecordingRootModel()
                    model.faults[ordinal] = fault
                    refusal = self._refused(model)
                    self.assertEqual(refusal.code, code)
                    quarantined = kind == "NtCreateFile" and fault == "exception"
                    report = self._assert_rollback(model, refusal, quarantined=quarantined)
                    if kind == "CloseHandle":
                        failed = model.calls[ordinal - 1][2]
                        self.assertEqual(model.close_log.count(failed), 1)  # never retried
                        self.assertIn(failed, model.handles)
                        self.assertEqual(report.close_uncertain, 1)
                    generations = [event[1] for event in report.lifecycle if event[0] == "REGISTERED"]
                    self.assertEqual(len(generations), len(set(generations)))

    def test_m05_primary_and_ordered_secondary_cleanup_failures_are_distinct(self) -> None:
        nominal = self._nominal()
        last_query = nominal.ordinals("GetFileInformationByHandleEx", info_class=18)[-1]
        probe = _RecordingRootModel()
        probe.faults[last_query] = "fail"
        self._refused(probe)
        rollback_closes = probe.ordinals("CloseHandle")[-5:]
        self.assertEqual(len(rollback_closes), 5)
        for position, close_ordinal in enumerate(rollback_closes):
            with self.subTest(close=close_ordinal):
                model = _RecordingRootModel()
                model.faults[last_query] = "fail"
                model.faults[close_ordinal] = "fail" if position % 2 else "exception"
                refusal = self._refused(model)
                self.assertEqual(refusal.code, "QUERY_FAILED")
                report = self._assert_rollback(model, refusal)
                self.assertEqual(report.secondary, ("CLOSE_EXCEPTION" if position % 2 == 0 else "CLOSE_FAILED",))
                # Four earlier transient R closes plus five rollback G closes: every other owned G
                # is still closed exactly once and the ambiguous one is not retried.
                self.assertEqual(report.close_attempts, 9)
                self.assertEqual((report.close_successes, report.close_uncertain), (8, 1))

    def test_m05_release_close_failures_and_integer_reuse_generations(self) -> None:
        probe = _RecordingRootModel()
        self._release(probe, self._acquire(probe))
        release_closes = probe.ordinals("CloseHandle")[-5:]
        for close_ordinal in release_closes:
            with self.subTest(close=close_ordinal):
                model = _RecordingRootModel()
                model.faults[close_ordinal] = "fail"
                chain = self._acquire(model)
                with self.assertRaises(_lb._F03RootGuardRefusal) as context:
                    self._release(model, chain)
                report = context.exception.report
                self.assertEqual(context.exception.code, "RELEASE_CLOSE_UNCERTAIN")
                self.assertEqual((report.close_uncertain, report.cleanup_outcome), (1, "CLOSE_UNCERTAIN"))
                self.assertEqual(len(model.close_log), len(set(model.close_log)))
                self.assertEqual(len(model.handles), 1)
                calls = len(model.calls)
                with self.assertRaises(_lb._F03RootGuardRefusal) as again:
                    self._release(model, chain)
                self.assertEqual(again.exception.code, "CHAIN_CLOSED")
                self.assertEqual(len(model.calls), calls)
        model = _RecordingRootModel(reuse=True)
        first = self._acquire(model)
        first_entries = list(self._attempt(first).entries)
        raws = [entry.raw for entry in first_entries]
        generations = [entry.generation for entry in first_entries]
        self.assertLess(len(set(raws)), len(raws))  # closed R integers were reused by the model
        self.assertEqual(len(set(generations)), len(generations))
        self.assertEqual(generations, sorted(generations))
        self._release(model, first)
        second = self._acquire(model)
        second_entries = list(self._attempt(second).entries)
        self.assertGreater(min(entry.generation for entry in second_entries), max(generations))
        stale = first_entries[0]
        self.assertIs(_lb._F03_RRG_LIVE_HANDLES.get(stale.raw), second_entries[0])
        with self.assertRaises(_lb._F03RootGuardRefusal) as context:
            _lb._f03_rrg_require_live(self._attempt(first), stale)  # a reused integer never revives it
        self.assertEqual(context.exception.code, "HANDLE_NOT_LIVE")
        self._release(model, second)

    # -- M06 isolation / holds ----------------------------------------------
    def test_m06_production_entry_refuses_first_for_every_input_and_platform(self) -> None:
        touched: list = []

        def trap(*_args, **_kwargs):
            touched.append(1)
            raise AssertionError("held production entry touched a prohibited surface")

        model = _RecordingRootModel()
        surfaces = [
            (_lb, "_f03_rrg_native_nt_create_file"), (_lb, "_f03_rrg_native_get_file_information_by_handle_ex"),
            (_lb, "_f03_rrg_native_get_final_path_name_by_handle_w"), (_lb, "_f03_rrg_native_close_handle"),
            (_lb, "_f03_rrg_native_get_last_error"), (_lb, "_f03_rrg_acquire_model_chain_v1"),
            (_lb, "_f03_rrg_require_supported_abi"), (_lb, "_f03_rrg_observed_abi"),
            (_lb, "_f03_rrg_validate_enrollment"), (_lb, "_F03RRGCallStorageV1"), (_lb, "_f03_rrg_register"),
            (_builtins, "open"), (_os, "stat"), (_os, "lstat"), (_os, "listdir"), (_os, "scandir"), (_os, "mkdir"),
            (_os, "getpid"), (Path, "resolve"), (_socket, "socket"), (_socket, "getaddrinfo"),
        ]
        inputs = (
            ((), {}),
            ((model.enrollment(),), dict(process_instance_id=_RRG_PROC, t0_ns=_RRG_T0, ta_ns=_RRG_TA,
                                         monotonic_clock_ns=model.clock, budget=_RRG_BUDGET)),
            (("\\??\\C:\\",), {"root": "C:\\b1\\kals\\ARB_LOCAL\\F03_TESTS"}),
            ((None, 5, b"x"), {"native": True, "adapter": trap, "fault_hook": trap, "accepted": True}),
            ((), {"enrollment_ref": {"logical_id": "x", "bytes": 1, "sha256": "0" * 64}, "lease": object()}),
        )
        quarantine_before = len(_lb._F03_RRG_PENDING_QUARANTINE)
        registry_before = dict(_lb._F03_RRG_LIVE_HANDLES)
        receipts_before = dict(_lb._live_receipt_registry)
        for os_name in ("nt", "posix", "java"):
            with _contextlib.ExitStack() as stack:
                stack.enter_context(_mock.patch.object(_lb.os, "name", os_name))
                for owner, name in surfaces:
                    stack.enter_context(_mock.patch.object(owner, name, trap))
                for args, kwargs in inputs:
                    try:
                        _lb._acquire_f03_retained_root_guard_v1(*args, **kwargs)
                    except _lb._F03RootGuardRefusal as refusal:
                        outcome = (refusal.code, refusal.report)
                    else:
                        outcome = ("RETURNED", None)
                    self.assertEqual(outcome, ("F03_N1_ROOT_UNAVAILABLE", None))
        self.assertEqual(touched, [])
        self.assertEqual(model.calls, [])
        self.assertEqual(len(_lb._F03_RRG_PENDING_QUARANTINE), quarantine_before)
        self.assertEqual(dict(_lb._F03_RRG_LIVE_HANDLES), registry_before)
        self.assertEqual(dict(_lb._live_receipt_registry), receipts_before)
        entry_code = _rrg_code_only(_inspect.getsource(_lb._acquire_f03_retained_root_guard_v1))
        for banned in ("_f03_rrg_", "native", "os.", "open(", "clock", "struct", "_attempt", "Chain", "return"):
            self.assertNotIn(banned, entry_code, banned)

    def test_m06_held_native_operations_refuse_before_entry_and_b_loads_no_library(self) -> None:
        held = (
            (_lb._f03_rrg_native_nt_create_file, (None,) * 9), (_lb._f03_rrg_native_close_handle, (1,)),
            (_lb._f03_rrg_native_get_file_information_by_handle_ex, (1, 18, bytearray(24), 24)),
            (_lb._f03_rrg_native_get_final_path_name_by_handle_w, (1, bytearray(4), 2, 0)),
            (_lb._f03_rrg_native_get_last_error, ()),
        )
        for function, args in held:
            with self.assertRaises(_lb._F03RRGNativeUnavailable):
                function(*args)
        # Unpatched mechanics refuse at the first boundary: nothing entered, nothing registered or quarantined.
        model = _RecordingRootModel()
        quarantine_before = len(_lb._F03_RRG_PENDING_QUARANTINE)
        with _mock.patch.object(_lb, "_f03_rrg_observed_abi", lambda: ("nt", 8, True)):
            with self.assertRaises(_lb._F03RootGuardRefusal) as context:
                _lb._f03_rrg_acquire_model_chain_v1(
                    model.enrollment(), process_instance_id=_RRG_PROC, t0_ns=_RRG_T0, ta_ns=_RRG_TA,
                    monotonic_clock_ns=model.clock, budget=_RRG_BUDGET)
        report = context.exception.report
        self.assertEqual(context.exception.code, "NATIVE_BINDING_UNAVAILABLE")
        self.assertEqual((report.open_calls, report.registrations, report.quarantined), (0, 0, False))
        self.assertEqual(len(_lb._F03_RRG_PENDING_QUARANTINE), quarantine_before)
        code = _rrg_code_only(_rrg_section_source())
        for banned in ("ctypes", "WinDLL", "windll", "cdll", "CDLL", "LoadLibrary", "dlopen", "__import__",
                       "importlib", "subprocess", "socket", "environ", "getenv", "sqlite", "Decimal", "float(",
                       "CreateFileW", "FlushFileBuffers", "_append_authorization_consumption",
                       "_acquire_consumption_state", "_AUTHORIZATION_RECEIPT_ISSUER_KEY"):
            self.assertNotIn(banned, code, banned)
        self.assertIsNone(_re.search(r"(?<![\w.])open\(", code))
        whole = _rrg_code_only(_RRG_B_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("ctypes", whole)
        import ctypes as _ctypes_module
        import _ctypes as _ctypes_native
        loads: list = []

        def load_trap(*_args, **_kwargs):
            loads.append(1)
            raise AssertionError("B import attempted a native library load")

        name = "_arb_tb_rrg_isolated_ledger_binding_copy"
        with _contextlib.ExitStack() as stack:
            stack.enter_context(_mock.patch.object(_ctypes_module.CDLL, "__init__", load_trap))
            for loader in ("LoadLibrary", "dlopen"):
                if hasattr(_ctypes_native, loader):
                    stack.enter_context(_mock.patch.object(_ctypes_native, loader, load_trap))
            spec = _importlib_util.spec_from_file_location(name, _RRG_B_PATH)
            copy_module = _importlib_util.module_from_spec(spec)
            sys.modules[name] = copy_module
            try:
                spec.loader.exec_module(copy_module)
            finally:
                sys.modules.pop(name, None)
        self.assertEqual(loads, [])
        with self.assertRaises(copy_module._F03RootGuardRefusal):
            copy_module._acquire_f03_retained_root_guard_v1()

    def test_m06_no_if_publication_wiring_or_export(self) -> None:
        for absent in ("_F03PhysicalProjectionV1", "_F03RootLeaseV1", "_F03CustodyLeaseV1", "_F03N1AdmissionMaterialV1",
                       "_mint_f03_n1_admission_material_v1", "_consume_active_execution_authorization_set_f03_n1_v1",
                       "_validate_f03_n1_material_locked_v1", "_F03_MATERIAL_ISSUER_KEY"):
            self.assertFalse(hasattr(_lb, absent), absent)
        for name in _lb.__all__:
            self.assertFalse(name.startswith("_"), name)
            self.assertNotIn("rrg", name.lower())
            self.assertNotIn("root_guard", name.lower())
            self.assertNotIn("RetainedRoot", name)
        repository = Path(__file__).resolve().parents[1]
        for relative in ("src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py",
                         "src/arb/venues/kalshi/f03_fee_semantics_runner.py", "src/arb/execution_ledger.py"):
            source = (repository / relative).read_text(encoding="utf-8")
            for symbol in ("_f03_rrg", "_F03RRG", "_F03_RRG", "_acquire_f03_retained_root_guard",
                           "_F03RootGuardRefusal", "_F03RetainedRootModelChainV1"):
                self.assertNotIn(symbol, source, (relative, symbol))
        b_code = _rrg_code_only(_RRG_B_PATH.read_text(encoding="utf-8"))
        for definition in ("_f03_rrg_acquire_model_chain_v1(", "_f03_rrg_revalidate_model_chain_v1(",
                           "_f03_rrg_release_model_chain_v1(", "_acquire_f03_retained_root_guard_v1("):
            self.assertEqual(b_code.count(definition), 1, definition)  # definition only: no caller wiring
        model = _RecordingRootModel()
        receipts_before = dict(_lb._live_receipt_registry)
        chain = self._acquire(model)
        self.assertIs(type(chain), _lb._F03RetainedRootModelChainV1)
        self.assertEqual(chain.evidence_class, "MODEL_ONLY_OFFLINE")
        self.assertEqual(dict(_lb._live_receipt_registry), receipts_before)
        with self.assertRaises(TypeError):
            _lb._F03RetainedRootModelChainV1(object(), self._attempt(chain))
        with self.assertRaises(AttributeError):
            chain._attempt = None
        self._release(model, chain)

    def test_m06_process_copy_pickle_closed_and_identity_mismatches_refuse(self) -> None:
        model = _RecordingRootModel()
        chain = self._acquire(model)
        attempt = self._attempt(chain)
        for value in (chain, attempt, attempt.entries[0], model.storages[0]):
            for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                with self.assertRaises(TypeError):
                    operation(value)
        calls = len(model.calls)
        with self.assertRaises(_lb._F03RootGuardRefusal) as context:
            self._release(model, chain, pid="proc_" + "8" * 32)
        self.assertEqual(context.exception.code, "PROCESS_MISMATCH")
        self.assertEqual(len(model.calls), calls)  # no side effect; the owner can still release
        self._revalidate(model, chain)  # still live and unchanged
        with _mock.patch.object(_lb.os, "getpid", lambda: attempt.os_process_id + 1):
            with self.assertRaises(_lb._F03RootGuardRefusal) as context:
                self._revalidate(model, chain)
        self.assertEqual(context.exception.code, "PROCESS_MISMATCH")
        self.assertEqual(context.exception.report.cleanup_outcome, "PROCESS_MISMATCH_NOT_CLOSED")
        self.assertTrue(all(call[1] != "CloseHandle" for call in model.calls[calls:]))  # foreign process closes nothing
        for operation in (self._revalidate, self._release):
            with self.assertRaises(_lb._F03RootGuardRefusal) as context:
                operation(model, chain)
            self.assertEqual(context.exception.code, "CHAIN_CLOSED")
        # Changed live evidence invalidates and rolls back immediately.
        model = _RecordingRootModel()
        chain = self._acquire(model)
        model.faults[len(model.calls) + 1] = "wrong_id"
        with self.assertRaises(_lb._F03RootGuardRefusal) as context:
            self._revalidate(model, chain)
        self.assertEqual(context.exception.code, "IDENTITY_MISMATCH")
        self._assert_rollback(model, context.exception)
        with self.assertRaises(_lb._F03RootGuardRefusal):
            _lb._f03_rrg_revalidate_model_chain_v1(object(), process_instance_id=_RRG_PROC)

    # -- M07 timing -----------------------------------------------------------
    def test_m07_original_t0_ta_shape_start_deadline_and_clock_discipline(self) -> None:
        for overrides, code in (
            (dict(ta_ns=_RRG_TA + 1), "ORIGINAL_BUDGET_INVALID"), (dict(ta_ns=_RRG_TA - 1), "ORIGINAL_BUDGET_INVALID"),
            (dict(t0_ns=True), "ORIGINAL_BUDGET_INVALID"), (dict(t0_ns=float(_RRG_T0)), "ORIGINAL_BUDGET_INVALID"),
            (dict(monotonic_clock_ns=lambda: _RRG_TA), "DEADLINE_EXPIRED"),
            (dict(monotonic_clock_ns=lambda: _RRG_TA + 1), "DEADLINE_EXPIRED"),
            (dict(monotonic_clock_ns=lambda: _RRG_T0 - 1), "CLOCK_REGRESSED"),
            (dict(monotonic_clock_ns=lambda: float(_RRG_T0 + 1)), "CLOCK_INVALID"),
            (dict(monotonic_clock_ns=None), "CLOCK_INVALID"),
            (dict(budget=_lb._F03RRGModelBudgetV1(1, 1, 1, -1)), "BUDGET_INVALID"),
            (dict(budget=_lb._F03RRGModelBudgetV1(
                open_ns=0, query_ns=0, close_ns=0, later_reserve_ns=_RRG_TA - _RRG_T0)), "RESERVE_INSUFFICIENT"),
        ):
            with self.subTest(code=code, overrides=sorted(overrides)):
                model = _RecordingRootModel()
                refusal = self._refused(model, **overrides)
                self.assertEqual(refusal.code, code)
                self.assertEqual(model.calls, [])
        with self.assertRaises(TypeError):
            _lb._F03RRGModelBudgetV1()  # no default runnable policy exists
        model = _RecordingRootModel()
        values = iter([_RRG_T0 + 10, _RRG_T0 + 5])
        refusal = self._refused(model, monotonic_clock_ns=lambda: next(values, _RRG_T0 + 5))
        self.assertEqual(refusal.code, "CLOCK_REGRESSED")  # no reset or refund

    def test_m07_insufficient_reserve_mid_attempt_and_expiry_after_every_call(self) -> None:
        model = _RecordingRootModel()
        tight = _lb._F03RRGModelBudgetV1(open_ns=1_000, query_ns=1_000, close_ns=1_000,
                                         later_reserve_ns=_RRG_TA - _RRG_T0 - 60_000)
        refusal = self._refused(model, budget=tight)
        self.assertEqual(refusal.code, "RESERVE_INSUFFICIENT")
        report = self._assert_rollback(model, refusal)
        self.assertGreater(report.open_calls, 0)
        nominal = self._nominal()
        for ordinal, kind, *_ in nominal.calls:
            with self.subTest(ordinal=ordinal, kind=kind):
                model = _RecordingRootModel()
                model.expire_after.add(ordinal)
                refusal = self._refused(model)
                self.assertEqual(refusal.code, "DEADLINE_EXPIRED_AFTER_CALL")
                report = self._assert_rollback(model, refusal)
                self.assertTrue(report.overrun)
                self.assertTrue(all(call[1] == "CloseHandle" for call in model.calls[ordinal:]))
                self.assertGreaterEqual(model.now, _RRG_TA)  # cleanup still attempted after TA

    def test_m07_cleanup_and_release_overrun_recorded_never_renewed(self) -> None:
        nominal = self._nominal()
        failing = nominal.ordinals("GetFinalPathNameByHandleW", flags=0)[-1]
        model = _RecordingRootModel()
        model.faults[failing] = "zero"
        model.expire_after.add(failing)
        refusal = self._refused(model)
        self.assertEqual(refusal.code, "FINAL_PATH_FAILED")
        report = self._assert_rollback(model, refusal)
        self.assertTrue(report.overrun)
        self.assertEqual(report.close_attempts, report.close_successes)
        model = _RecordingRootModel()
        chain = self._acquire(model)
        model.now = _RRG_TA + 5
        with self.assertRaises(_lb._F03RootGuardRefusal) as context:
            self._release(model, chain)
        self.assertEqual(context.exception.code, "RELEASE_OVERRUN")
        self.assertTrue(context.exception.report.overrun)
        self.assertEqual(model.handles, {})  # every owned G still closed once after TA
        with self.assertRaises(_lb._F03RootGuardRefusal) as context:
            self._revalidate(model, chain)
        self.assertEqual(context.exception.code, "CHAIN_CLOSED")
        model = _RecordingRootModel()
        chain = self._acquire(model)
        model.now = _RRG_TA
        with self.assertRaises(_lb._F03RootGuardRefusal) as context:
            self._revalidate(model, chain)
        self.assertEqual(context.exception.code, "DEADLINE_EXPIRED")
        self.assertEqual(model.handles, {})

    # -- M09 legacy / privacy -------------------------------------------------
    def test_m09_generic_b_bytes_unchanged_outside_the_additive_held_section(self) -> None:
        text = _RRG_B_PATH.read_bytes().decode("utf-8")
        head, rest = text.split(_RRG_SECTION_HEADER, 1)
        tail = rest.split("\n\n\n__all__ = [", 1)[1]
        reconstructed = head + "__all__ = [" + tail
        self.assertEqual(reconstructed.count("import struct\nimport sys\n"), 1)
        reconstructed = reconstructed.replace("import struct\nimport sys\n", "", 1)
        self.assertEqual(hashlib.sha256(reconstructed.encode("utf-8")).hexdigest(), _RRG_BASE_B_SHA256)

    def test_m09_public_evidence_excludes_raw_handles_paths_and_identifiers(self) -> None:
        model = _RecordingRootModel()
        chain = self._acquire(model)
        attempt = self._attempt(chain)
        secrets = {str(entry.raw) for entry in attempt.entries} | {hex(entry.raw) for entry in attempt.entries}
        secrets |= {f"{entry.raw:x}" for entry in attempt.entries}
        secrets |= {obj["id"].hex() for obj in model.objects.values()} | {"0123456789abcdef", _RRG_VOLUME_GUID}
        secrets |= {"ARB_LOCAL", "F03_TESTS", "kals", "C:\\"}
        texts = [repr(chain), str(chain), repr(chain.report()), repr(attempt), repr(attempt.entries[0]),
                 repr(attempt.chain[0].identity), repr(model.enrollment()), repr(model.storages[0])]
        report = self._release(model, chain)
        texts.append(repr(report))
        failing = _RecordingRootModel()
        failing.faults[self._nominal().ordinals("GetFileInformationByHandleEx", info_class=18)[3]] = "fail"
        refusal = self._refused(failing)
        texts += [repr(refusal), str(refusal), repr(refusal.report)]
        for text in texts:
            for secret in secrets:
                self.assertNotIn(secret, text)


class F03HeldRetainedRootGuardInterruptionTests(unittest.TestCase):
    """Correction 01 / Marco B-01: a non-Exception interruption (KeyboardInterrupt,
    SystemExit) or an ordinary exception at a fixed operation boundary is
    finalized conservatively BEFORE it propagates.  Unknown open completion
    keeps strong storage/output ownership in process-lifetime quarantine; an
    interrupted close is terminal CLOSE_UNCERTAIN, never retried and never
    reported clean; every other safely closable registration is still closed
    once; acquisition/revalidation/release are invalidated; the original
    primary and ordered secondary failures are preserved; the interruption
    object itself is re-raised, never swallowed."""

    _P = F03HeldRetainedRootGuardPrimitiveTests
    _DEFAULT = F03HeldRetainedRootGuardPrimitiveTests._DEFAULT
    INTERRUPTIONS = (KeyboardInterrupt, SystemExit)

    def _acquire(self, model, **overrides):
        return self._P._acquire(self, model, **overrides)

    def _release(self, model, chain):
        return self._P._release(self, model, chain)

    def _revalidate(self, model, chain):
        return self._P._revalidate(self, model, chain)

    def _nominal(self):
        return self._P._nominal(self)

    def _raised(self, exc_type, operation):
        with self.assertRaises(exc_type) as context:
            operation()
        return context.exception

    @staticmethod
    def _report(exc):
        return getattr(exc, "_f03_rrg_report", None)

    @staticmethod
    def _in_quarantine(storage):
        return any(kept is storage for kept, _ in _lb._F03_RRG_PENDING_QUARANTINE)

    def test_b01_open_boundary_interruption_before_and_after_output_publication(self) -> None:
        nominal = self._nominal()
        opens = nominal.ordinals("NtCreateFile")
        for exc_type in self.INTERRUPTIONS:
            for when in ("before", "after"):
                for ordinal in (opens[0], opens[1], opens[2], opens[-1]):
                    with self.subTest(exc=exc_type.__name__, when=when, ordinal=ordinal):
                        model = _RecordingRootModel()
                        model.faults[ordinal] = ("raise", exc_type, when)
                        exc = self._raised(exc_type, lambda: self._acquire(model))
                        storage = model.storages[-1]
                        # Unknown completion: the call storage is retained in process-lifetime quarantine.
                        self.assertEqual(storage.state, "QUARANTINED")
                        self.assertTrue(self._in_quarantine(storage))
                        raw = _struct.unpack("<Q", bytes(storage.handle_slot))[0]
                        if when == "after":
                            entry = _lb._F03_RRG_LIVE_HANDLES.get(raw)
                            self.assertIsNotNone(entry)  # published output is owned, never orphaned
                            self.assertTrue(entry.quarantined)
                            self.assertIn(raw, model.handles)
                        self.assertNotIn(raw, model.close_log)
                        self.assertEqual(model.calls[-1][0], ordinal)  # no wait/retry/close afterwards
                        for kept_storage, attempt in _lb._F03_RRG_PENDING_QUARANTINE:
                            if kept_storage is storage:
                                for registered in attempt.entries:
                                    if registered.state in ("ACQUIRED_UNVALIDATED", "VALIDATED"):
                                        self.assertTrue(registered.quarantined)
                                        self.assertIs(_lb._F03_RRG_LIVE_HANDLES.get(registered.raw), registered)
                                self.assertTrue(attempt.invalidated and attempt.closed)
                        report = self._report(exc)
                        self.assertIsNotNone(report)
                        self.assertEqual(report.primary, "OPEN_INTERRUPTED_COMPLETION_UNKNOWN")
                        self.assertEqual(report.interruption, exc_type.__name__)
                        self.assertTrue(report.quarantined)
                        self.assertEqual(report.cleanup_outcome, "PENDING_QUARANTINED_NO_CLEAN_CLAIM")

    def test_b01_quarantined_ownership_survives_exception_and_traceback_disposal(self) -> None:
        import gc
        nominal = self._nominal()
        ordinal = nominal.ordinals("NtCreateFile")[2]
        for fault in (("raise", KeyboardInterrupt, "after"), ("raise", OSError, "after")):
            with self.subTest(fault=fault[1].__name__):
                model = _RecordingRootModel()
                model.faults[ordinal] = fault
                try:
                    self._acquire(model)
                except BaseException as caught:  # noqa: BLE001 - the injected boundary failure itself
                    self.assertIs(type(caught), fault[1] if fault[1] is KeyboardInterrupt else _lb._F03RootGuardRefusal)
                storage = model.storages[-1]
                raw = _struct.unpack("<Q", bytes(storage.handle_slot))[0]
                storage_id = id(storage)
                del storage
                model.storages.clear()
                gc.collect()
                self.assertTrue(any(id(kept) == storage_id for kept, _ in _lb._F03_RRG_PENDING_QUARANTINE))
                entry = _lb._F03_RRG_LIVE_HANDLES.get(raw)
                self.assertIsNotNone(entry)
                self.assertTrue(entry.quarantined)
                self.assertEqual(entry.state, "ACQUIRED_UNVALIDATED")
                self.assertNotIn(raw, model.close_log)

    def test_b01_transient_close_interruption_is_terminal_uncertain_and_never_clean(self) -> None:
        nominal = self._nominal()
        transient_closes = nominal.ordinals("CloseHandle")
        self.assertEqual(len(transient_closes), 4)
        for exc_type in self.INTERRUPTIONS:
            for when in ("before", "after"):
                for ordinal in transient_closes:
                    with self.subTest(exc=exc_type.__name__, when=when, ordinal=ordinal):
                        model = _RecordingRootModel()
                        model.faults[ordinal] = ("raise", exc_type, when)
                        exc = self._raised(exc_type, lambda: self._acquire(model))
                        raw = model.calls[ordinal - 1][2]
                        entry = _lb._F03_RRG_LIVE_HANDLES.get(raw)
                        self.assertIsNotNone(entry)
                        self.assertEqual(entry.state, "CLOSE_UNCERTAIN")
                        self.assertEqual(model.close_log.count(raw), 1)  # never retried
                        # Every other owned guard was still closed exactly once.
                        expected_left = {raw} if when == "before" else set()
                        self.assertEqual(set(model.handles), expected_left)
                        self.assertEqual(len(model.close_log), len(set(model.close_log)))
                        self.assertTrue(all(call[1] == "CloseHandle" for call in model.calls[ordinal:]))
                        report = self._report(exc)
                        self.assertIsNotNone(report)
                        self.assertEqual(report.primary, "CLOSE_INTERRUPTED")
                        self.assertEqual(report.interruption, exc_type.__name__)
                        self.assertEqual(report.close_uncertain, 1)
                        self.assertEqual(report.close_attempts, report.close_successes + 1)
                        self.assertEqual(report.cleanup_outcome, "CLOSE_UNCERTAIN")
                        self.assertNotEqual(report.cleanup_outcome, "CLOSED_ALL_REGISTERED")

    def test_b01_rollback_close_interruption_keeps_primary_and_finishes_cleanup(self) -> None:
        nominal = self._nominal()
        last_query = nominal.ordinals("GetFileInformationByHandleEx", info_class=18)[-1]
        probe = _RecordingRootModel()
        probe.faults[last_query] = "fail"
        with self.assertRaises(_lb._F03RootGuardRefusal):
            self._acquire(probe)
        rollback_closes = probe.ordinals("CloseHandle")[-5:]
        for exc_type in self.INTERRUPTIONS:
            for position, close_ordinal in enumerate(rollback_closes):
                with self.subTest(exc=exc_type.__name__, close=close_ordinal):
                    model = _RecordingRootModel()
                    model.faults[last_query] = "fail"
                    model.faults[close_ordinal] = ("raise", exc_type, "before")
                    exc = self._raised(exc_type, lambda: self._acquire(model))
                    raw = model.calls[close_ordinal - 1][2]
                    self.assertEqual(set(model.handles), {raw})  # the remaining guards were still closed
                    self.assertEqual(model.close_log.count(raw), 1)
                    self.assertEqual(_lb._F03_RRG_LIVE_HANDLES.get(raw).state, "CLOSE_UNCERTAIN")
                    report = self._report(exc)
                    self.assertIsNotNone(report)
                    self.assertEqual(report.primary, "QUERY_FAILED")  # original primary preserved
                    self.assertEqual(report.secondary, ("CLOSE_INTERRUPTED",))
                    self.assertEqual((report.close_attempts, report.close_successes, report.close_uncertain), (9, 8, 1))
                    self.assertEqual(report.cleanup_outcome, "CLOSE_UNCERTAIN")

    def test_b01_release_close_interruption_finalizes_every_other_guard(self) -> None:
        probe = _RecordingRootModel()
        self._release(probe, self._acquire(probe))
        release_closes = probe.ordinals("CloseHandle")[-5:]
        for exc_type in self.INTERRUPTIONS:
            for when in ("before", "after"):
                for close_ordinal in release_closes:
                    with self.subTest(exc=exc_type.__name__, when=when, close=close_ordinal):
                        model = _RecordingRootModel()
                        model.faults[close_ordinal] = ("raise", exc_type, when)
                        chain = self._acquire(model)
                        exc = self._raised(exc_type, lambda: self._release(model, chain))
                        raw = model.calls[close_ordinal - 1][2]
                        self.assertEqual(set(model.handles), {raw} if when == "before" else set())
                        self.assertEqual(len(model.close_log), len(set(model.close_log)))
                        self.assertEqual(_lb._F03_RRG_LIVE_HANDLES.get(raw).state, "CLOSE_UNCERTAIN")
                        calls = len(model.calls)
                        for operation in (self._release, self._revalidate):
                            with self.assertRaises(_lb._F03RootGuardRefusal) as again:
                                operation(model, chain)
                            self.assertEqual(again.exception.code, "CHAIN_CLOSED")
                        self.assertEqual(len(model.calls), calls)
                        report = self._report(exc)
                        self.assertIsNotNone(report)
                        self.assertEqual(report.primary, "RELEASE_INTERRUPTED")
                        self.assertEqual(report.secondary, ("CLOSE_INTERRUPTED",))
                        self.assertEqual(report.cleanup_outcome, "CLOSE_UNCERTAIN")

    def test_b01_revalidation_interruption_invalidates_and_rolls_back(self) -> None:
        for exc_type in self.INTERRUPTIONS:
            for offset in range(4):  # FileIdInfo, AttributeTag, DOS and GUID boundaries of the first requery
                with self.subTest(exc=exc_type.__name__, offset=offset):
                    model = _RecordingRootModel()
                    chain = self._acquire(model)
                    model.faults[len(model.calls) + 1 + offset] = ("raise", exc_type, "before")
                    exc = self._raised(exc_type, lambda: self._revalidate(model, chain))
                    self.assertEqual(model.handles, {})  # owned guards closed once, before propagation
                    self.assertEqual(len(model.close_log), len(set(model.close_log)))
                    with self.assertRaises(_lb._F03RootGuardRefusal) as again:
                        self._revalidate(model, chain)
                    self.assertEqual(again.exception.code, "CHAIN_CLOSED")
                    report = self._report(exc)
                    self.assertIsNotNone(report)
                    self.assertEqual(report.primary, "QUERY_INTERRUPTED")
                    self.assertEqual(report.cleanup_outcome, "CLOSED_ALL_REGISTERED")

    def test_b01_shared_last_error_and_clock_boundaries_never_swallow_interruption(self) -> None:
        nominal = self._nominal()
        failing_query = nominal.ordinals("GetFileInformationByHandleEx", info_class=18)[2]
        for exc_type in self.INTERRUPTIONS:
            with self.subTest(boundary="GetLastError", exc=exc_type.__name__):
                model = _RecordingRootModel()
                model.faults[failing_query] = "fail"
                model.last_error_mode = exc_type
                exc = self._raised(exc_type, lambda: self._acquire(model))
                self.assertEqual(model.handles, {})  # finalized before propagation
                report = self._report(exc)
                self.assertIsNotNone(report)
                self.assertEqual(report.primary, "QUERY_FAILED")
                self.assertEqual(report.last_errors[-1], ("FileIdInfo", "UNAVAILABLE"))
                self.assertEqual(report.interruption, exc_type.__name__)
                self.assertEqual(report.cleanup_outcome, "CLOSED_ALL_REGISTERED")
            with self.subTest(boundary="clock", exc=exc_type.__name__):
                model = _RecordingRootModel()
                samples = {"count": 0}

                def clock(model=model, samples=samples, exc_type=exc_type):
                    samples["count"] += 1
                    if samples["count"] == 12:  # one sample in the middle of the first edge
                        raise exc_type("synthetic clock-boundary raise")
                    return model.now

                exc = self._raised(exc_type, lambda: self._acquire(model, monotonic_clock_ns=clock))
                self.assertEqual(model.handles, {})
                self.assertEqual(len(model.close_log), len(set(model.close_log)))
                report = self._report(exc)
                self.assertIsNotNone(report)
                self.assertEqual(report.primary, "CLOCK_INTERRUPTED")
                self.assertEqual(report.interruption, exc_type.__name__)
                self.assertEqual(report.cleanup_outcome, "CLOSED_ALL_REGISTERED")

    def test_b01_ordinary_exception_after_output_publication_retains_ownership(self) -> None:
        nominal = self._nominal()
        for ordinal in nominal.ordinals("NtCreateFile")[:3]:
            with self.subTest(ordinal=ordinal):
                model = _RecordingRootModel()
                model.faults[ordinal] = ("raise", OSError, "after")
                with self.assertRaises(_lb._F03RootGuardRefusal) as context:
                    self._acquire(model)
                storage = model.storages[-1]
                raw = _struct.unpack("<Q", bytes(storage.handle_slot))[0]
                entry = _lb._F03_RRG_LIVE_HANDLES.get(raw)
                self.assertIsNotNone(entry)
                self.assertTrue(entry.quarantined)
                self.assertNotIn(raw, model.close_log)
                self.assertEqual(context.exception.code, "OPEN_EXCEPTION_COMPLETION_UNKNOWN")
                self.assertIsNone(context.exception.report.interruption)
                self.assertEqual(context.exception.report.cleanup_outcome, "PENDING_QUARANTINED_NO_CLEAN_CLAIM")


if __name__ == "__main__":
    unittest.main()
