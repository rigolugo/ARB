"""Offline tests for the restricted Kalshi ledger binding."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import arb.execution_ledger as ledger
from arb.execution_ledger import (
    AcquisitionMode,
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
    EvidenceExpectation,
    LegacyIncidentContract,
    LegacyImportStatus,
    append_authority_anchored_send_gate,
    acquire_legacy_import_only,
    acquire_normal_writer_state,
    canonical_kalshi_fill_payload,
    validate_legacy_evidence,
)


class DeterministicInputs:
    def __init__(self) -> None:
        self.instant = datetime(2026, 8, 13, 13, 0, 0, tzinfo=timezone.utc)
        self.number = 101

    def clock(self) -> datetime:
        value = self.instant
        self.instant += timedelta(microseconds=1)
        return value

    def uuid(self) -> uuid.UUID:
        value = uuid.UUID(int=self.number, version=4)
        self.number += 1
        return value


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


if __name__ == "__main__":
    unittest.main()
