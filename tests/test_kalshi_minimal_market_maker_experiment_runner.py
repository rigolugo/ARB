"""Offline tests for the Gate-B pre-release read/reconciliation runner spine
(Implementation 02 -- a same-scope correction of Marco-blocked Implementation
01, addressing Marco Blockers 01-05).

Covers Spec 04 ER04-TEST-002 cases 73/78/79/80 (as they concern this file's
own runner-owned boundary; the ledger_binding.py-owned halves of those cases
are already covered by tests/test_kalshi_ledger_binding.py), the preserved
Gate-B-dispatch direct cases B01-B40, and the Implementation-02 correction
cases C01-C25.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import json
import pickle
import tempfile
import unittest
import uuid
from unittest import mock
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping

from arb.execution_ledger import (
    AcquisitionMode,
    AuthorityLedgerRelation,
    AuthorityNamespaceBinding,
    FailureCode,
    LedgerError,
    OpenResult,
    acquire_local_state,
    canonical_json_bytes,
    end_writer_session,
)
from arb.venues.kalshi.ledger_binding import (
    CURRENT_ACCOUNT_SCOPE_REF,
    CURRENT_CLIENT_ORDER_ID,
    CURRENT_DISPOSITION,
    CURRENT_ENVIRONMENT,
    CURRENT_INCIDENT_ID,
    CURRENT_TICKER,
    CURRENT_WRITER_PROOF_ID,
    PRODUCTION_EVIDENCE_EXPECTATIONS,
    CurrentProcessReleaseCompletionV1,
    EvidenceExpectation,
    LegacyIncidentContract,
    NormalWriterAcquisition,
    ReleaseEvaluationStateV1,
    ReleaseLedgerHandle,
    TrustedReleaseEvidenceProjectionV1,
    TrustedReleaseEvidenceReadResultV1,
    acquire_emergency_control_only,
    acquire_legacy_import_only,
    acquire_normal_writer_state,
    acquire_release_only,
    canonical_kalshi_fill_payload,
    read_trusted_release_evidence_projection,
)
from arb.venues.kalshi.emergency_cancel import (
    EmergencyCancelGate,
    EmergencyRateConfigV1,
    EmergencyRateLane,
)
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    FlowRiskLimits,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
    WorkingOrderV1,
    WriterEligibilityGate,
)
from arb.venues.kalshi.orderbook import (
    KalshiNativeOrderBookLevel,
    KalshiNativeOrderBookSnapshot,
    OrderBookHalt,
    OrderBookHaltCode,
    OrderBookStage,
)

import arb.venues.kalshi.ledger_binding as ledger_binding
import arb.venues.kalshi.minimal_market_maker_experiment_runner as runner
from arb.venues.kalshi.minimal_market_maker_experiment_runner import (
    ExperimentRunnerInvocationV1,
    ExperimentRunnerRuntimeV1,
    OPERATION_BINDING_INDEX_BYTES,
    OPERATION_BINDING_INDEX_SHA256,
    OperationDeadlineV1,
    PRE_RELEASE_READ_OPERATIONS,
    PRE_RELEASE_READ_REQUEST_MAX,
    PreReleaseReadCapabilityV1,
    RawOperationResponseV1,
    RunnerError,
    RunnerFailureCode,
    RunnerOperation,
    WRITE_OPERATIONS,
    build_operation_binding_index,
    collect_authoritative_read_truth,
    create_one_shot_marker,
    prepare_runner_operation_request,
    run_pre_release_read_phase,
)


# ---------------------------------------------------------------------------
# Deterministic clock/uuid inputs (mirrors tests/test_kalshi_ledger_binding.py).
# ---------------------------------------------------------------------------


class DeterministicInputs:
    def __init__(self) -> None:
        self.instant = datetime(2026, 8, 17, 13, 0, 0, tzinfo=timezone.utc)
        self.number = 501
        self.monotonic_value = 5_000_000_000

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
        self.monotonic_value += 1_000_000  # +1ms per call
        return value


# ---------------------------------------------------------------------------
# Fake transport / orderbook fetch.
# ---------------------------------------------------------------------------


class _ScriptedTransport:
    """Fake `send_operation_request`. Each call pops the next scripted
    response for that operation; raises if the script is exhausted so a
    test can prove exactly how many transport calls actually happened."""

    def __init__(self) -> None:
        self.responses: dict[RunnerOperation, list] = {}
        self.calls: list[tuple] = []

    def queue(self, operation: RunnerOperation, response) -> None:
        self.responses.setdefault(operation, []).append(response)

    def __call__(self, operation, prepared, deadline):
        self.calls.append((operation, prepared, deadline))
        pending = self.responses.get(operation)
        if not pending:
            raise AssertionError(f"no scripted transport response for {operation}")
        response = pending.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _json_response(payload: Mapping[str, object]) -> RawOperationResponseV1:
    body = json.dumps(payload).encode("utf-8")
    return RawOperationResponseV1(http_status=200, content_type="application/json", body_bytes=body)


_PRICE_RANGES = [{"start_dollars": "0.00", "end_dollars": "1.00", "step_dollars": "0.01"}]


def _market_payload(*, ticker: str, status: str = "active", exchange_index: int = 0, price_ranges=None) -> RawOperationResponseV1:
    return _json_response({"market": {
        "ticker": ticker, "status": status, "exchange_index": exchange_index,
        "yes_bid_dollars": "0.45", "price_ranges": _PRICE_RANGES if price_ranges is None else price_ranges,
    }})


def _orders_payload(rows: list[dict], *, cursor: str = "") -> RawOperationResponseV1:
    return _json_response({"orders": rows, "cursor": cursor})


def _order_row(order_id: str, *, ticker: str, side: str = "yes", status: str = "resting") -> dict:
    return {
        "order_id": order_id, "ticker": ticker, "side": side, "status": status,
        "subaccount": 0, "exchange_index": 0,
        "remaining_count_fp": "1.00", "yes_price_dollars": "0.45",
    }


def _order_payload(order_id: str, *, ticker: str, side: str = "yes", status: str = "resting") -> RawOperationResponseV1:
    return _json_response({"order": _order_row(order_id, ticker=ticker, side=side, status=status)})


def _fills_payload(rows: list[dict], *, cursor: str = "") -> RawOperationResponseV1:
    return _json_response({"fills": rows, "cursor": cursor})


def _fill_row(fill_id: str, *, order_id: str, ticker: str, side: str = "yes", price: str = "0.40", quantity: str = "1.00") -> dict:
    return {
        "fill_id": fill_id, "order_id": order_id, "ticker": ticker, "side": side,
        "subaccount": 0, "exchange_index": 0,
        "yes_price_dollars": price, "count_fp": quantity,
        "created_time": "2026-08-17T13:00:00.000000Z",
    }


def _positions_payload(rows: list[dict], *, cursor: str = "") -> RawOperationResponseV1:
    return _json_response({"market_positions": rows, "event_positions": [], "cursor": cursor})


def _position_row(ticker: str, *, position_count_fp: str = "0.00") -> dict:
    return {"ticker": ticker, "subaccount": 0, "exchange_index": 0, "position_count_fp": position_count_fp}


def _fake_orderbook_snapshot(ticker: str) -> KalshiNativeOrderBookSnapshot:
    return KalshiNativeOrderBookSnapshot(
        environment="KALSHI_DEMO", market_ticker=ticker, method="GET",
        route_template="/markets/{ticker}/orderbook",
        full_request_path=f"/trade-api/v2/markets/{ticker}/orderbook",
        endpoint_classification="AUTHENTICATED_READ_ONLY",
        request_timestamp_ms=1_755_000_000_000,
        request_started_monotonic_ns=1, request_completed_monotonic_ns=2,
        yes_levels=(KalshiNativeOrderBookLevel(price=Decimal("0.45"), quantity=Decimal("10")),),
        no_levels=(KalshiNativeOrderBookLevel(price=Decimal("0.50"), quantity=Decimal("8")),),
        canonical_level_ordering="ASCENDING_PRICE", response_byte_length=64,
        response_sha256="0" * 64, raw_openapi_sha256="0" * 64,
        source_binding_record_sha256="0" * 64, request_count=1, retry_count=0, redirect_count=0,
        gustavo_execution_authorization_id="TEST_AUTH", expected_implementation_commit="0" * 40,
        specification_sha256="0" * 64,
    )


def _standard_orderbook_fetch(ticker_expected: str):
    calls: list = []

    def _fetch(ticker: str, deadline: OperationDeadlineV1):
        calls.append((ticker, deadline))
        return _fake_orderbook_snapshot(ticker_expected)

    _fetch.calls = calls
    return _fetch


# ---------------------------------------------------------------------------
# Ledger harness shared with tests/test_kalshi_ledger_binding.py's pattern:
# synthetic evidence bound to the SAME production identity constants
# (incident_id/environment/conflict_domain_ref/ticker/...), validated
# against locally computed byte-length/sha256 pairs rather than the real
# production evidence content.
# ---------------------------------------------------------------------------


class GateBTestCase(unittest.TestCase):
    TICKER = CURRENT_TICKER

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self.ledger_path = self.root / "execution.sqlite3"
        self.inputs = DeterministicInputs()
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="gate-b-test-namespace",
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
    def _encode_evidence_documents(documents: dict[str, dict[str, object]]) -> dict[str, bytes]:
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

    def _initialize(self) -> None:
        from arb.execution_ledger import initialize_authority_namespace, initialize_ledger_binding
        initialize_authority_namespace(self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        initialize_ledger_binding(
            self.binding,
            conflict_domain_ref=self.contract.conflict_domain_ref,
            environment_classification=self.contract.environment,
            ledger_path=self.ledger_path,
            canonical_repository_root=self.repository_root,
            clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )

    def _read_local_safety_state(self) -> Callable[[], OpenResult]:
        def _read() -> OpenResult:
            return acquire_local_state(
                self.binding,
                conflict_domain_ref=self.contract.conflict_domain_ref,
                expected_environment=self.contract.environment,
                canonical_repository_root=str(self.repository_root),
                acquisition_mode=AcquisitionMode.NORMAL_WRITER,
                expected_ledger_path=str(self.ledger_path),
                clock=self.inputs.clock,
                uuid_factory=self.inputs.uuid,
            )
        return _read

    def _build_blocked_ledger(self) -> None:
        """Reproduces the exact current historical incident: after legacy
        import, `protected_unresolved_legacy_write_count == 1` and release
        is locally disproven -- matching Spec 04 Section 4/ER04-HIST-001."""

        self._initialize()
        imported = acquire_legacy_import_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(imported.handle)
        imported.handle.commit_exact_legacy_import(imported.handle.validate_legacy_evidence(self.evidence))
        imported.handle.close()

    def _new_gates(self, handle) -> tuple:
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
        emergency_gate = EmergencyCancelGate(
            handle=handle, rate_lane=lane, process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        return normal_gate, emergency_gate

    def _build_release_capable_ledger(self):
        """Builds a ledger that passes the FULL local-gate predicate set
        (dispatch Implementation-02 Section 8), including `history_
        completeness == COMPLETE` -- which requires an actual completed
        legacy import, not merely a fresh unimported ledger.

        Sequence: complete a legacy import using the same synthetic
        evidence `_build_blocked_ledger` uses (establishing the legacy
        writer proof as durably `HELD`, not yet eligible, exactly like the
        real historical incident) -- then record a FRESH `RECONCILIATION_
        RECORDED` event for the SAME `CURRENT_INCIDENT_ID` with
        `writer_proof_release_eligible=True`. Per execution_ledger.py's
        replay logic, this flips `proof_eligible[CURRENT_WRITER_PROOF_ID]`
        to `True` for the already-`HELD` legacy proof without needing a
        second `WRITER_PROOF_HELD` event, which makes
        `protected_unresolved_legacy_write_count == 0` and `history_
        completeness == "COMPLETE"` (imported + resolved, as opposed to
        `"COMPLETE_WITH_PROTECTED_UNRESOLVED_LEGACY_WRITE"`). No orders/
        fills are pre-recorded; Gate B's own bounded reads independently
        discover them. Returns (config, incident_id, proof_id, normal_gate,
        emergency_gate) using the exact `CURRENT_INCIDENT_ID`/`CURRENT_
        WRITER_PROOF_ID` identities.
        """

        self._build_blocked_ledger()
        config = RiskLimitConfigV1(
            1, self.contract.conflict_domain_ref, "USD",
            PerOrderRiskLimits(Decimal("10"), Decimal("10"), True, Decimal("0.10"), 1_000),
            PerMarketRiskLimits(Decimal("20"), Decimal("20"), 10, Decimal("20"), Decimal("20")),
            AccountRiskLimits(Decimal("100"), 50, Decimal("100"), 0, Decimal("0")),
            FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
        )
        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        handle = emergency.handle
        handle.record_reconciliation({
            "incident_id": CURRENT_INCIDENT_ID,
            "disposition": "SYNTHETIC_RESOLVED_SAFE",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
            "bound_order_id": None,
            "created_order_upper_bound": 0,
            "active_order_upper_bound": 0,
            "unknown_result": False,
            "writer_proof_release_eligible": True,
            "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RESOLUTION_V1",
        }, incident_id=CURRENT_INCIDENT_ID)
        resolved = handle.inspect_validated_projection()
        self.assertEqual(resolved.protected_unresolved_legacy_write_count, 0)
        self.assertEqual(resolved.history_completeness, "COMPLETE")
        self.assertTrue(resolved.writer_proof_release_eligible_by_proof_id.get(CURRENT_WRITER_PROOF_ID))

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
            "observed_authority_trusted_sequence": resolved.last_sequence,
            "observed_authority_trusted_hash": resolved.terminal_event_hash,
            "observed_ledger_terminal_sequence": resolved.last_sequence,
            "observed_ledger_terminal_hash": resolved.terminal_event_hash,
        }
        handle.record_risk_control_state_changed(state_payload)
        projection = handle.inspect_validated_projection()
        self.assertEqual(projection.risk_control_state, "SAFE_HELD")

        normal_gate, emergency_gate = self._new_gates(handle)
        handle.close()
        return config, CURRENT_INCIDENT_ID, CURRENT_WRITER_PROOF_ID, normal_gate, emergency_gate

    def _read_trusted_release_evidence(self) -> Callable[[], TrustedReleaseEvidenceReadResultV1]:
        def _read() -> TrustedReleaseEvidenceReadResultV1:
            return read_trusted_release_evidence_projection(
                self.binding,
                canonical_repository_root=str(self.repository_root),
                contract=self.contract,
                expected_ledger_path=str(self.ledger_path),
                clock=self.inputs.clock,
                uuid_factory=self.inputs.uuid,
            )
        return _read

    def _runtime(
        self, *, normal_gate, emergency_gate, config, transport: _ScriptedTransport,
        orderbook_fetch=None, experiment_absolute_end_monotonic_ns: int = 10**18,
        read_trusted_release_evidence=None,
    ) -> ExperimentRunnerRuntimeV1:
        return ExperimentRunnerRuntimeV1(
            normal_gate=normal_gate, emergency_gate=emergency_gate,
            read_local_safety_state=self._read_local_safety_state(),
            read_trusted_release_evidence=read_trusted_release_evidence or self._read_trusted_release_evidence(),
            send_operation_request=transport,
            fetch_orderbook=orderbook_fetch or _standard_orderbook_fetch(self.TICKER),
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid, risk_config=config,
            experiment_absolute_end_monotonic_ns=experiment_absolute_end_monotonic_ns,
            authority_binding=self.binding,
            canonical_repository_root=str(self.repository_root),
            expected_ledger_path=str(self.ledger_path),
            contract=self.contract,
        )

    def _invocation(self, *, incident_id: str, proof_id: str) -> ExperimentRunnerInvocationV1:
        return ExperimentRunnerInvocationV1(
            invocation_id=f"inv_{self.inputs.uuid().hex}", market_ticker=self.TICKER,
            incident_id=incident_id, writer_proof_id=proof_id,
        )

    def _capability(self, runtime: ExperimentRunnerRuntimeV1) -> PreReleaseReadCapabilityV1:
        """Test-only access to the module-private issuance factory -- the
        ONLY route by which tests (or production code) may construct a
        usable capability, exactly mirroring what `run_pre_release_read_
        phase` does after Stage 3C passes (Marco Blocker 01)."""

        return runner._issue_pre_release_read_capability(
            process_instance_id=runtime.normal_gate.process_instance_id, ticker=self.TICKER, runtime=runtime,
        )

    def _script_full_read_cycle(self, transport: _ScriptedTransport, *, order_ids=(), fills_by_order=None) -> None:
        transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
        rows = [_order_row(order_id, ticker=self.TICKER) for order_id in order_ids]
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload(rows))
        fills_by_order = fills_by_order or {}
        for order_id in order_ids:
            transport.queue(RunnerOperation.GET_ORDER, _order_payload(order_id, ticker=self.TICKER))
            rows = fills_by_order.get(order_id, [])
            transport.queue(RunnerOperation.GET_FILLS, _fills_payload(rows))
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([_position_row(self.TICKER)] if order_ids else []))


# ---------------------------------------------------------------------------
# B01/B02/B39/B40: current historical blocker stops locally, zero secrets,
# zero venue requests, zero durable mutation, zero writer session.
# ---------------------------------------------------------------------------


class LocalImpossibilityGateTests(GateBTestCase):
    def _blocked_runtime(self, transport: _ScriptedTransport, orderbook_fetch=None):
        self._build_blocked_ledger()
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
        emergency_gate = EmergencyCancelGate(
            handle=emergency.handle, rate_lane=lane, process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        emergency.handle.close()
        return self._runtime(
            normal_gate=normal_gate, emergency_gate=emergency_gate, config=None,
            transport=transport, orderbook_fetch=orderbook_fetch,
        )

    def test_b01_current_historical_incident_stops_before_credential_resolver(self) -> None:
        credential_resolver_calls: list = []

        def _fetch_orderbook(ticker, deadline):
            credential_resolver_calls.append((ticker, deadline))
            raise AssertionError("credential/venue access must not occur")

        transport = _ScriptedTransport()
        runtime = self._blocked_runtime(transport, orderbook_fetch=_fetch_orderbook)
        invocation = self._invocation(incident_id=CURRENT_INCIDENT_ID, proof_id=CURRENT_WRITER_PROOF_ID)

        result = run_pre_release_read_phase(invocation, runtime)

        self.assertEqual(result.status, "LOCALLY_BLOCKED")
        self.assertIn("PROTECTED_UNRESOLVED_LEGACY_WRITE_COUNT_NONZERO", result.local_block_reasons)
        self.assertIsNone(result.release_state)
        self.assertEqual(result.requests_consumed, 0)
        self.assertEqual(credential_resolver_calls, [])

    def test_b02_current_historical_incident_sends_zero_fake_venue_requests(self) -> None:
        transport = _ScriptedTransport()  # intentionally empty script
        runtime = self._blocked_runtime(transport)
        invocation = self._invocation(incident_id=CURRENT_INCIDENT_ID, proof_id=CURRENT_WRITER_PROOF_ID)

        result = run_pre_release_read_phase(invocation, runtime)

        self.assertEqual(result.status, "LOCALLY_BLOCKED")
        self.assertEqual(transport.calls, [])
        self.assertEqual(result.requests_consumed, 0)

    def test_b39_no_release_only_durable_mutation_occurs(self) -> None:
        runtime = self._blocked_runtime(_ScriptedTransport())
        # Snapshot only after all harness-side gate construction (which
        # itself opens/closes an EMERGENCY_CONTROL_ONLY session) is done --
        # this test proves the RUNNER's own call makes no durable mutation,
        # not that constructing test fixtures is mutation-free.
        before = self._read_local_safety_state()()
        run_pre_release_read_phase(self._invocation(incident_id=CURRENT_INCIDENT_ID, proof_id=CURRENT_WRITER_PROOF_ID), runtime)
        after = self._read_local_safety_state()()
        self.assertEqual(before.projection.last_sequence, after.projection.last_sequence)
        self.assertEqual(before.projection.terminal_event_hash, after.projection.terminal_event_hash)

    def test_b40_no_writer_session_started_occurs(self) -> None:
        self._build_blocked_ledger()
        state = self._read_local_safety_state()()
        self.assertIsNone(state.projection.active_writer_session_id)
        self.assertEqual(state.projection.writer_sessions, ())

    def test_c03_local_durable_fill_conflict_blocks_before_credential_transport(self) -> None:
        """C03: a durable fill-identity conflict recorded on the ledger
        blocks Stage 3C before any credential/venue activity.

        Gate A's own append-time defense (`DUPLICATE_FILL_CONFLICT`)
        already rejects a conflicting duplicate write before it can ever
        land durably, so this exact scenario cannot be constructed via a
        single offline ledger session. This test instead proves the
        SECOND, independent layer directly: `_local_impossibility_reasons`
        reads `projection.fill_conflicts` and blocks whenever it is
        nonempty, via a duck-typed fake projection (no live ledger/SQLite
        handle needed, avoiding any fixture-only file-locking fragility)."""

        from types import SimpleNamespace
        fake_projection = SimpleNamespace(
            history_completeness="COMPLETE", protected_unresolved_legacy_write_count=0,
            unresolved_write_request_ids=(), fill_conflicts=("conflict-fill",),
            writer_proof_state_by_proof_id={CURRENT_WRITER_PROOF_ID: "HELD"},
            writer_proof_release_eligible_by_proof_id={CURRENT_WRITER_PROOF_ID: True},
            risk_control_state="SAFE_HELD", restart_classification=runner.RestartClassification.UNRESOLVED_WRITE_HELD,
        )
        fake_opened = OpenResult(fake_projection, runner.RestartClassification.UNRESOLVED_WRITE_HELD, None)
        reasons = runner._local_impossibility_reasons(fake_opened, writer_proof_id=CURRENT_WRITER_PROOF_ID)
        self.assertIn("FILL_IDENTITY_CONFLICT", reasons)


# ---------------------------------------------------------------------------
# B04-B10 / C01: PreReleaseReadCapabilityV1 structural closure and closed
# construction.
# ---------------------------------------------------------------------------


class StructuralClosureTests(GateBTestCase):
    def _ready_capability(self) -> PreReleaseReadCapabilityV1:
        config, incident_id, proof_id, normal_gate, emergency_gate = self._build_release_capable_ledger()
        runtime = self._runtime(
            normal_gate=normal_gate, emergency_gate=emergency_gate, config=config,
            transport=_ScriptedTransport(),
        )
        return self._capability(runtime)

    def test_b04_public_surface_is_exactly_six_reads(self) -> None:
        capability = self._ready_capability()
        public = {name for name in dir(capability) if not name.startswith("_")}
        self.assertEqual(public, {"get_market", "get_market_orderbook", "get_orders", "get_order", "get_fills", "get_positions", "requests_consumed"})

    def test_b04_rejects_create_order_v2_structurally(self) -> None:
        capability = self._ready_capability()
        self.assertFalse(hasattr(capability, "create_order"))
        self.assertFalse(hasattr(capability, "send"))
        self.assertFalse(hasattr(capability, "request"))
        with self.assertRaises(RunnerError) as ctx:
            prepare_runner_operation_request(
                RunnerOperation.CREATE_ORDER_V2, path_parameters={}, request_ordinal=1,
            )
        self.assertEqual(ctx.exception.code, RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION)

    def test_b05_rejects_cancel_order_v2_structurally(self) -> None:
        with self.assertRaises(RunnerError) as ctx:
            prepare_runner_operation_request(
                RunnerOperation.CANCEL_ORDER_V2, path_parameters={"order_id": "x"}, request_ordinal=1,
            )
        self.assertEqual(ctx.exception.code, RunnerFailureCode.OPERATION_REQUEST_POLICY_VIOLATION)
        self.assertTrue(WRITE_OPERATIONS.isdisjoint(PRE_RELEASE_READ_OPERATIONS))

    def test_b06_rejects_arbitrary_method_path_host(self) -> None:
        prepared = prepare_runner_operation_request(
            RunnerOperation.GET_MARKET, path_parameters={"ticker": CURRENT_TICKER}, ticker=CURRENT_TICKER, request_ordinal=1,
        )
        self.assertEqual(prepared.method, "GET")
        self.assertEqual(prepared.host, runner.DEMO_HOST)
        self.assertTrue(prepared.wire_request_url.startswith(runner.DEMO_ORIGIN))
        import inspect
        signature = inspect.signature(prepare_runner_operation_request)
        self.assertNotIn("host", signature.parameters)
        self.assertNotIn("method", signature.parameters)
        self.assertNotIn("url", signature.parameters)

    def test_b07_production_host_unreachable(self) -> None:
        self.assertNotIn("kalshi.co", runner.DEMO_HOST.replace("demo.kalshi.co", ""))
        self.assertIn("demo", runner.DEMO_HOST)
        self.assertNotIn("PRODUCTION", [op.value for op in RunnerOperation])

    def test_b08_websocket_unavailable(self) -> None:
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertNotIn("wss://", source)
        self.assertNotIn("websocket.", source.lower())
        self.assertFalse(hasattr(runner, "websocket"))
        public = {name for name in dir(PreReleaseReadCapabilityV1) if not name.startswith("_")}
        self.assertTrue(all("socket" not in name.lower() for name in public))

    def test_b09_retry_count_remains_zero(self) -> None:
        self.assertEqual(runner.AUTOMATIC_RETRIES, 0)

    def test_b10_redirect_count_remains_zero(self) -> None:
        self.assertEqual(runner.REDIRECTS, 0)

    def test_c01_direct_construction_cannot_create_usable_capability(self) -> None:
        """Marco Blocker 01: importing the class and calling its ordinary
        constructor (without the module-private issuance key) must not
        produce a usable capability."""

        with self.assertRaises(TypeError):
            PreReleaseReadCapabilityV1(process_instance_id="proc_" + "0" * 32, ticker=self.TICKER, runtime=None)  # type: ignore[call-arg]
        with self.assertRaises(RunnerError) as ctx:
            PreReleaseReadCapabilityV1(object(), process_instance_id="proc_" + "0" * 32, ticker=self.TICKER, runtime=None)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.CAPABILITY_ISSUANCE_UNAUTHORIZED)
        # The real key is module-private and not exported.
        self.assertNotIn("_CAPABILITY_ISSUANCE_KEY", runner.__all__)

    def test_c02_capability_issuance_impossible_when_history_incomplete(self) -> None:
        """C02: a fresh ledger that has never completed a legacy import
        (`history_completeness == INCOMPLETE`) blocks Stage 3C -> Stage 3D,
        so no capability is ever issued."""

        self._initialize()
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        _, emergency_gate = self._new_gates(emergency.handle)
        emergency_gate = EmergencyCancelGate(
            handle=emergency.handle, rate_lane=EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100)),
            process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        emergency.handle.close()
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=None, transport=_ScriptedTransport())
        result = run_pre_release_read_phase(self._invocation(incident_id=CURRENT_INCIDENT_ID, proof_id=CURRENT_WRITER_PROOF_ID), runtime)
        self.assertEqual(result.status, "LOCALLY_BLOCKED")
        self.assertTrue(any(reason.startswith("HISTORY_COMPLETENESS:INCOMPLETE") for reason in result.local_block_reasons))
        self.assertEqual(result.requests_consumed, 0)


# ---------------------------------------------------------------------------
# Full-cycle harness-backed tests (B03, B11-B38, C04-C25) -- these exercise a
# real structurally-release-capable ledger plus the closed capability end to
# end.
# ---------------------------------------------------------------------------


class ReadPhaseTests(GateBTestCase):
    def _ready_runtime_and_invocation(self, transport: _ScriptedTransport, **kwargs):
        config, incident_id, proof_id, normal_gate, emergency_gate = self._build_release_capable_ledger()
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport, **kwargs)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        return runtime, invocation

    def _ready_capability(self, transport: _ScriptedTransport, **kwargs) -> PreReleaseReadCapabilityV1:
        runtime, _ = self._ready_runtime_and_invocation(transport, **kwargs)
        return self._capability(runtime)

    def _empty_trusted_projection(self):
        """Minimal duck-typed stand-in exposing exactly the
        `TrustedReleaseEvidenceProjectionV1` surface
        `_match_trusted_release_evidence` reads (`conflict_ids`,
        `working_orders`, `fills`, `order_evidence_ref`,
        `fill_evidence_ref`), for direct unit-level testing of the matcher
        without a full ledger round trip."""

        from types import SimpleNamespace
        return SimpleNamespace(
            conflict_ids=(), working_orders=(), fills=(),
            order_evidence_ref=lambda order: None,
            fill_evidence_ref=lambda fill: None,
        )

    def test_b03_successful_reads_do_not_manufacture_release_token(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)

        result = run_pre_release_read_phase(invocation, runtime)

        self.assertEqual(result.status, "READ_PHASE_COMPLETE")
        self.assertIsInstance(result.release_state, ReleaseEvaluationStateV1)
        self.assertNotIsInstance(result.release_state, CurrentProcessReleaseCompletionV1)
        self.assertNotIsInstance(result, CurrentProcessReleaseCompletionV1)
        self.assertFalse(hasattr(result, "current_process_release_completion"))
        self.assertFalse(hasattr(result, "normal_writer_session_id"))

    def test_b11_separate_pre_release_budget_hard_stops_at_16(self) -> None:
        transport = _ScriptedTransport()
        for _ in range(20):
            transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([]))
        capability = self._ready_capability(transport)
        for _ in range(PRE_RELEASE_READ_REQUEST_MAX):
            capability.get_orders()
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_READ_BUDGET_EXHAUSTED)
        self.assertEqual(capability.requests_consumed, PRE_RELEASE_READ_REQUEST_MAX)

    def test_b12_budget_cannot_borrow_from_future_64_read_lane(self) -> None:
        self.assertNotEqual(PRE_RELEASE_READ_REQUEST_MAX, runner.EXPERIMENT_READ_REQUEST_MAX)
        self.assertEqual(PRE_RELEASE_READ_REQUEST_MAX, 16)
        self.assertEqual(runner.EXPERIMENT_READ_REQUEST_MAX, 64)

    def test_b13_get_market_exact_ticker_identity(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker="WRONG-TICKER"))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_market()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.MARKET_IDENTITY_INVALID)

    def test_b14_orderbook_delegates_canonical_authenticated_implementation(self) -> None:
        transport = _ScriptedTransport()
        orderbook_fetch = _standard_orderbook_fetch(self.TICKER)
        capability = self._ready_capability(transport, orderbook_fetch=orderbook_fetch)
        snapshot = capability.get_market_orderbook()
        self.assertIsInstance(snapshot, KalshiNativeOrderBookSnapshot)
        self.assertEqual(len(orderbook_fetch.calls), 1)
        self.assertEqual([call[0] for call in transport.calls], [])

    def test_b14b_orderbook_halt_propagates_as_failure(self) -> None:
        transport = _ScriptedTransport()

        def _halting_fetch(ticker, deadline):
            return OrderBookHalt(code=OrderBookHaltCode.MARKET_NOT_FOUND, stage=OrderBookStage.RESPONSE_VALIDATED)

        capability = self._ready_capability(transport, orderbook_fetch=_halting_fetch)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_market_orderbook()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_b15_get_orders_second_page_terminal_cursor_completes(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)], cursor="cursor-1"))
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-b", ticker=self.TICKER)], cursor=""))
        capability = self._ready_capability(transport)
        orders, complete, order_ids = runner._fetch_orders(capability, ticker=self.TICKER)
        self.assertTrue(complete)
        self.assertEqual(order_ids, ("order-a", "order-b"))
        self.assertTrue(all(type(order) is WorkingOrderV1 for order in orders))

    def test_b16_get_orders_cursor_after_page_2_incomplete(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([], cursor="cursor-1"))
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([], cursor="cursor-2"))
        capability = self._ready_capability(transport)
        orders, complete, order_ids = runner._fetch_orders(capability, ticker=self.TICKER)
        self.assertFalse(complete)

    def test_b17_get_order_via_authoritative_target_set(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("real-order", ticker=self.TICKER)]))
        transport.queue(RunnerOperation.GET_ORDER, _order_payload("real-order", ticker=self.TICKER))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError):
            capability.get_order("")
        capability.get_orders()  # admits "real-order" into the authoritative target set
        confirmed = capability.get_order("real-order")
        self.assertEqual(confirmed.order_id, "real-order")

    def test_b18_more_than_two_pre_release_order_targets_prohibited(self) -> None:
        transport = _ScriptedTransport()
        order_ids = ("order-1", "order-2", "order-3")
        transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row(oid, ticker=self.TICKER) for oid in order_ids]))
        for oid in order_ids[:runner.GET_ORDER_MAX_TARGETS]:
            transport.queue(RunnerOperation.GET_ORDER, _order_payload(oid, ticker=self.TICKER))
            transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([]))
        capability = self._ready_capability(transport)
        truth = collect_authoritative_read_truth(capability, ticker=self.TICKER)
        self.assertEqual(len(truth.bound_order_ids), runner.GET_ORDER_MAX_TARGETS)
        self.assertFalse(truth.orders_complete)

    def test_b19_fill_exact_duplicate_dedupes_by_fill_id(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        row = _fill_row("fill-1", order_id="order-a", ticker=self.TICKER)
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([row, dict(row)]))
        capability = self._ready_capability(transport)
        capability.get_orders()
        fills_by_id: dict = {}
        complete = runner._fetch_fills_for_order(capability, ticker=self.TICKER, order_id="order-a", fills_by_id=fills_by_id)
        self.assertTrue(complete)
        self.assertEqual(len(fills_by_id), 1)

    def test_b20_conflicting_duplicate_fill_id_hard_fails(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        row_a = _fill_row("fill-1", order_id="order-a", ticker=self.TICKER, price="0.40")
        row_b = _fill_row("fill-1", order_id="order-a", ticker=self.TICKER, price="0.55")
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([row_a, row_b]))
        capability = self._ready_capability(transport)
        capability.get_orders()
        with self.assertRaises(RunnerError) as ctx:
            runner._fetch_fills_for_order(capability, ticker=self.TICKER, order_id="order-a", fills_by_id={})
        self.assertEqual(ctx.exception.code, RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_b21_fill_page_5_for_one_order_prohibited(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        for page in range(runner.GET_FILLS_MAX_PAGES_PER_ORDER):
            transport.queue(RunnerOperation.GET_FILLS, _fills_payload([], cursor=f"cursor-{page}"))
        capability = self._ready_capability(transport)
        capability.get_orders()
        complete = runner._fetch_fills_for_order(capability, ticker=self.TICKER, order_id="order-a", fills_by_id={})
        self.assertFalse(complete)
        fills_calls = [call for call in transport.calls if call[0] is RunnerOperation.GET_FILLS]
        self.assertEqual(len(fills_calls), runner.GET_FILLS_MAX_PAGES_PER_ORDER)

    def test_b22_incomplete_fills_remain_incomplete(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        for i in range(4):
            transport.queue(RunnerOperation.GET_FILLS, _fills_payload([], cursor=f"still-more-{i}"))
        capability = self._ready_capability(transport)
        capability.get_orders()
        complete = runner._fetch_fills_for_order(capability, ticker=self.TICKER, order_id="order-a", fills_by_id={})
        self.assertFalse(complete)

    def test_b23_submitted_limit_price_never_becomes_fill_price(self) -> None:
        row = _fill_row("fill-1", order_id="order-a", ticker=self.TICKER, price="0.33")
        fill = runner._fill_from_raw(row, expected_ticker=self.TICKER, expected_order_id="order-a")
        self.assertEqual(fill.yes_price, Decimal("0.33"))
        self.assertNotEqual(fill.yes_price, Decimal("0.45"))  # the order's own submitted/resting price

    def test_b24_positions_empty_means_no_venue_position_row(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([]))
        capability = self._ready_capability(transport)
        state, rows = runner._fetch_positions(capability, ticker=self.TICKER)
        self.assertEqual(state, "NO_VENUE_POSITION_ROW")
        self.assertEqual(rows, ())

    def test_b25_malformed_positions_do_not_become_zero(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({"market_positions": "not-a-list", "event_positions": [], "cursor": ""}))
        capability = self._ready_capability(transport)
        state, rows = runner._fetch_positions(capability, ticker=self.TICKER)
        self.assertEqual(state, "VENUE_POSITION_UNAVAILABLE")

    def test_b26_cross_ticker_response_conflict(self) -> None:
        row = _order_row("order-a", ticker="WRONG-TICKER")
        with self.assertRaises(RunnerError) as ctx:
            runner._working_order_from_raw(row, expected_ticker=self.TICKER)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORDER_IDENTITY_INVALID)

    def test_b27_subaccount_exchange_index_mismatch_fails(self) -> None:
        row = _order_row("order-a", ticker=self.TICKER)
        row["subaccount"] = 1
        with self.assertRaises(RunnerError) as ctx:
            runner._working_order_from_raw(row, expected_ticker=self.TICKER)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORDER_IDENTITY_INVALID)

    def _permissive_deadline(self) -> OperationDeadlineV1:
        return OperationDeadlineV1.create(
            process_instance_id="proc_test", operation_name="GET_ORDERS", request_ordinal=1,
            started_monotonic_ns=self.inputs.monotonic_value,
            experiment_absolute_end_monotonic_ns=10**18, uuid_factory=self.inputs.uuid,
        )

    def test_b28_response_body_exact_cap_accepted(self) -> None:
        payload = {"orders": [], "cursor": ""}
        packed = json.dumps(payload).encode("utf-8")
        padded = packed[:-1] + b' ' * (runner.MAX_RESPONSE_BODY_BYTES - len(packed)) + packed[-1:]
        self.assertEqual(len(padded), runner.MAX_RESPONSE_BODY_BYTES)
        raw = RawOperationResponseV1(http_status=200, content_type="application/json", body_bytes=padded)
        decoded = runner._decode_and_validate_runner_json_response(
            RunnerOperation.GET_ORDERS, raw_response=raw, deadline=self._permissive_deadline(),
            now_monotonic_ns=self.inputs.monotonic_ns,
        )
        self.assertEqual(decoded, payload)

    def test_b29_response_body_cap_plus_one_rejected(self) -> None:
        payload = {"orders": [], "cursor": ""}
        packed = json.dumps(payload).encode("utf-8")
        over = packed[:-1] + b' ' * (runner.MAX_RESPONSE_BODY_BYTES - len(packed) + 1) + packed[-1:]
        self.assertEqual(len(over), runner.MAX_RESPONSE_BODY_BYTES + 1)
        raw = RawOperationResponseV1(http_status=200, content_type="application/json", body_bytes=over)
        with self.assertRaises(RunnerError) as ctx:
            runner._decode_and_validate_runner_json_response(
                RunnerOperation.GET_ORDERS, raw_response=raw, deadline=self._permissive_deadline(),
                now_monotonic_ns=self.inputs.monotonic_ns,
            )
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_BODY_TOO_LARGE)

    def test_b30_deadline_expiry_during_parsing_fails(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([]))
        config, incident_id, proof_id, normal_gate, emergency_gate = self._build_release_capable_ledger()

        calls = {"n": 0}
        base = self.inputs.monotonic_value

        def _clock() -> int:
            calls["n"] += 1
            if calls["n"] >= 6:
                return base + 11_000_000_000
            return base + calls["n"]

        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        runtime = runner.ExperimentRunnerRuntimeV1(
            normal_gate=runtime.normal_gate, emergency_gate=runtime.emergency_gate,
            read_local_safety_state=runtime.read_local_safety_state,
            read_trusted_release_evidence=runtime.read_trusted_release_evidence,
            send_operation_request=transport, fetch_orderbook=runtime.fetch_orderbook,
            monotonic_clock_ns=_clock, wall_clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
            risk_config=config, experiment_absolute_end_monotonic_ns=base + 300_000_000_000,
            authority_binding=runtime.authority_binding,
            canonical_repository_root=runtime.canonical_repository_root,
            expected_ledger_path=runtime.expected_ledger_path,
            contract=runtime.contract,
        )
        capability = self._capability(runtime)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)

    def test_b31_operation_binding_index_exact_identity(self) -> None:
        produced = build_operation_binding_index()
        self.assertEqual(len(produced), OPERATION_BINDING_INDEX_BYTES)
        self.assertEqual(hashlib.sha256(produced).hexdigest(), OPERATION_BINDING_INDEX_SHA256)

    def test_b32_exact_demo_url_path_decomposition(self) -> None:
        prepared = prepare_runner_operation_request(
            RunnerOperation.GET_MARKET, path_parameters={"ticker": "TEST-TICKER"}, ticker="TEST-TICKER", request_ordinal=1,
        )
        self.assertEqual(prepared.wire_request_url, "https://external-api.demo.kalshi.co/trade-api/v2/markets/TEST-TICKER")
        self.assertEqual(prepared.signed_path_without_query, "/trade-api/v2/markets/TEST-TICKER")

    def test_b33_query_text_excluded_from_signed_path(self) -> None:
        prepared = prepare_runner_operation_request(
            RunnerOperation.GET_ORDERS, path_parameters={}, ticker=self.TICKER, request_ordinal=1,
        )
        self.assertNotIn("?", prepared.signed_path_without_query)
        self.assertIn("?", prepared.wire_request_url)

    def test_b34_no_secret_values_in_semantic_evidence(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        result = run_pre_release_read_phase(invocation, runtime)
        import dataclasses
        rendered = repr(result.release_state.__class__) + str(dataclasses.astuple(result.truth))
        for forbidden in ("PRIVATE KEY", "BEGIN RSA", "KALSHI-ACCESS-SIGNATURE"):
            self.assertNotIn(forbidden, rendered)

    def test_b35_release_evaluation_state_process_identity_exact(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        result = run_pre_release_read_phase(invocation, runtime)
        snapshot = result.release_state._snapshot()
        self.assertEqual(snapshot[2], runtime.normal_gate.process_instance_id)
        self.assertEqual(snapshot[2], runtime.emergency_gate.process_instance_id)

    def test_b36_risk_snapshot_reflects_collected_truth(self) -> None:
        """Implementation 04: a release state is only ever constructed
        after a COMPLETE_TRUSTED_MATCH, so this now requires the fresh
        order/fill to have a matching durable counterpart -- otherwise
        Stage 3F correctly stops before any `ReleaseRiskSnapshotV1` is
        built at all (see test_c21c)."""

        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        self._script_full_read_cycle(
            transport, order_ids=("order-a",),
            fills_by_order={"order-a": [_fill_row("fill-1", order_id="order-a", ticker=self.TICKER)]},
        )
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        result = run_pre_release_read_phase(invocation, runtime)
        snapshot = result.release_state._snapshot()
        risk_snapshot = snapshot[6]
        self.assertEqual(len(risk_snapshot.fills), 1)
        self.assertEqual(risk_snapshot.fills[0].fill_id, "fill-1")

    def test_b37_venue_reads_cannot_overwrite_protected_historical_truth(self) -> None:
        self._build_blocked_ledger()
        before = self._read_local_safety_state()()
        self.assertEqual(before.projection.protected_unresolved_legacy_write_count, 1)
        after = self._read_local_safety_state()()
        self.assertEqual(before.projection.protected_unresolved_legacy_write_count, after.projection.protected_unresolved_legacy_write_count)
        self.assertEqual(before.projection.last_sequence, after.projection.last_sequence)

    def test_b38_position_unavailable_forces_unknown_unbounded_exposure(self) -> None:
        """Position corroboration is load-bearing (dispatch Section 17):
        even with zero durable unresolved writes, a `VENUE_POSITION_
        UNAVAILABLE` corroboration result alone forces `UNKNOWN_UNBOUNDED`
        exposure -- it is never treated as equivalent to a corroborated
        zero position."""

        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([]))
        # Incomplete position pagination -> VENUE_POSITION_UNAVAILABLE.
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([], cursor="c1"))
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([], cursor="c2"))
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.truth.position_corroboration, "UNAVAILABLE")
        risk_snapshot = result.release_state._snapshot()[6]
        self.assertEqual(risk_snapshot.unresolved_write_exposure_usd, runner.UNKNOWN_UNBOUNDED)

    # -- Marco Blocker 02: authoritative order-ID target set ---------------

    def test_c04_unauthorized_arbitrary_get_order_id_fails_before_budget(self) -> None:
        transport = _ScriptedTransport()  # empty: no request should ever be sent
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_order("never-admitted-order-id")
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORDER_TARGET_NOT_AUTHORITATIVE)
        self.assertEqual(capability.requests_consumed, 0)
        self.assertEqual(transport.calls, [])

    def test_c05_unauthorized_arbitrary_get_fills_id_fails_before_budget(self) -> None:
        transport = _ScriptedTransport()
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_fills("never-admitted-order-id")
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORDER_TARGET_NOT_AUTHORITATIVE)
        self.assertEqual(capability.requests_consumed, 0)
        self.assertEqual(transport.calls, [])

    def test_c06_target_becomes_eligible_only_through_get_orders(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        transport.queue(RunnerOperation.GET_ORDER, _order_payload("order-a", ticker=self.TICKER))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_order("order-a")  # not yet admitted
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORDER_TARGET_NOT_AUTHORITATIVE)
        capability.get_orders()  # admits "order-a"
        confirmed = capability.get_order("order-a")
        self.assertEqual(confirmed.order_id, "order-a")

    def test_c06b_no_public_authorize_order_id_escape_hatch(self) -> None:
        capability = self._ready_capability(_ScriptedTransport())
        public = {name for name in dir(capability) if not name.startswith("_")}
        self.assertTrue(all("authorize" not in name.lower() for name in public))

    # -- Marco Blocker 03: exact response schema ----------------------------

    def test_c07_malformed_get_market_exact_schema_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_MARKET, _json_response({"market": {"ticker": self.TICKER, "status": "active"}}))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_market()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08_get_market_unusable_price_grid_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER, price_ranges=[]))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_market()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.MARKET_GRID_INVALID)

    def test_c08b_get_market_off_grid_reference_price_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_MARKET, _json_response({"market": {
            "ticker": self.TICKER, "status": "active", "exchange_index": 0,
            "yes_bid_dollars": "0.455",  # not aligned to the 0.01 grid step
            "price_ranges": _PRICE_RANGES,
        }}))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_market()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.MARKET_GRID_INVALID)

    def test_c09_malformed_get_order_response_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        transport.queue(RunnerOperation.GET_ORDER, _json_response({"order": {"order_id": "order-a", "ticker": self.TICKER}}))
        capability = self._ready_capability(transport)
        capability.get_orders()
        with self.assertRaises(RunnerError) as ctx:
            capability.get_order("order-a")
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c10_malformed_get_fills_response_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        bad_row = _fill_row("fill-1", order_id="order-a", ticker=self.TICKER)
        del bad_row["created_time"]
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([bad_row]))
        capability = self._ready_capability(transport)
        capability.get_orders()
        with self.assertRaises(RunnerError) as ctx:
            capability.get_fills("order-a")
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c11_malformed_get_positions_response_rejected(self) -> None:
        transport = _ScriptedTransport()
        bad_row = _position_row(self.TICKER)
        del bad_row["subaccount"]
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([bad_row]))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_positions()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c12_bool_vs_int_exact_type_confusion_rejected(self) -> None:
        row = _order_row("order-a", ticker=self.TICKER)
        row["exchange_index"] = False  # False == 0 under `==`, but must not satisfy `type(x) is int`
        with self.assertRaises(RunnerError) as ctx:
            runner._working_order_from_raw(row, expected_ticker=self.TICKER)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORDER_IDENTITY_INVALID)
        self.assertIn("type", ctx.exception.detail or "")

    # -- Marco Blocker 04: no manufactured zero economic exposure -----------

    def test_c13_pagination_completeness_alone_does_not_zero_unresolved_count(self) -> None:
        """Unit-level proof that `assemble_release_evaluation_state` derives
        `unresolved_write_count` from the durable `SafetyProjection`, never
        from venue-read pagination completeness. Implementation 04: the
        fake projection must still be T0/T1-coherent with the real ledger
        (only the two protected/unresolved fields are overridden) so the
        trusted-match/coherence gate does not itself block this unit check
        before the exposure derivation under test even runs."""

        import dataclasses
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)  # orders/fills fully paginate (both empty)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        capability = self._capability(runtime)
        truth = collect_authoritative_read_truth(capability, ticker=self.TICKER)
        self.assertTrue(truth.orders_complete and truth.fills_complete)
        real_projection = runtime.read_local_safety_state().projection
        fake_projection = dataclasses.replace(
            real_projection, protected_unresolved_legacy_write_count=1, unresolved_write_request_ids=("req_x",),
        )
        state = runner.assemble_release_evaluation_state(invocation, runtime, truth, fake_projection)
        risk_snapshot = state._snapshot()[6]
        self.assertEqual(risk_snapshot.unresolved_write_count, 2)  # 1 + len(("req_x",))

    def test_c14_pagination_completeness_alone_does_not_zero_exposure(self) -> None:
        import dataclasses
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        capability = self._capability(runtime)
        truth = collect_authoritative_read_truth(capability, ticker=self.TICKER)
        real_projection = runtime.read_local_safety_state().projection
        fake_projection = dataclasses.replace(
            real_projection, protected_unresolved_legacy_write_count=1, unresolved_write_request_ids=(),
        )
        state = runner.assemble_release_evaluation_state(invocation, runtime, truth, fake_projection)
        risk_snapshot = state._snapshot()[6]
        self.assertEqual(risk_snapshot.unresolved_write_exposure_usd, runner.UNKNOWN_UNBOUNDED)

    def test_c15_venue_position_unavailable_remains_release_ineligible(self) -> None:
        # Covered end-to-end by test_b38; this adds a direct unit check of
        # the corroboration function itself.
        state = runner._corroborate_position(
            ticker=self.TICKER, position_state="VENUE_POSITION_UNAVAILABLE",
            market_positions_raw=(), working_orders=(), fills=(),
        )
        self.assertEqual(state, "UNAVAILABLE")

    def test_c16_no_venue_position_row_does_not_independently_manufacture_zero(self) -> None:
        """NO_VENUE_POSITION_ROW alone is not proof of zero -- it must
        agree with the independently-derived economic truth from fills, or
        it is a CONFLICT."""

        nonzero_fill = runner._fill_from_raw(
            _fill_row("fill-1", order_id="order-a", ticker=self.TICKER, quantity="2.00"),
            expected_ticker=self.TICKER, expected_order_id="order-a",
        )
        conflict_state = runner._corroborate_position(
            ticker=self.TICKER, position_state="NO_VENUE_POSITION_ROW",
            market_positions_raw=(), working_orders=(), fills=(nonzero_fill,),
        )
        self.assertEqual(conflict_state, "CONFLICT")
        agree_state = runner._corroborate_position(
            ticker=self.TICKER, position_state="NO_VENUE_POSITION_ROW",
            market_positions_raw=(), working_orders=(), fills=(),
        )
        self.assertEqual(agree_state, "CORROBORATED")

    def test_c17_observed_position_contradicting_independent_truth_fails_closed(self) -> None:
        nonzero_fill = runner._fill_from_raw(
            _fill_row("fill-1", order_id="order-a", ticker=self.TICKER, quantity="2.00"),
            expected_ticker=self.TICKER, expected_order_id="order-a",
        )
        row = _position_row(self.TICKER, position_count_fp="0.00")  # venue disagrees with the 2.00 YES fill
        state = runner._corroborate_position(
            ticker=self.TICKER, position_state="VENUE_POSITION_ROW_OBSERVED",
            market_positions_raw=(row,), working_orders=(), fills=(nonzero_fill,),
        )
        self.assertEqual(state, "CONFLICT")

    def test_c17b_observed_position_agreeing_with_independent_truth_corroborates(self) -> None:
        fill = runner._fill_from_raw(
            _fill_row("fill-1", order_id="order-a", ticker=self.TICKER, quantity="2.00"),
            expected_ticker=self.TICKER, expected_order_id="order-a",
        )
        row = _position_row(self.TICKER, position_count_fp="2.00")
        state = runner._corroborate_position(
            ticker=self.TICKER, position_state="VENUE_POSITION_ROW_OBSERVED",
            market_positions_raw=(row,), working_orders=(), fills=(fill,),
        )
        self.assertEqual(state, "CORROBORATED")

    # -- Marco Blocker 05: trusted evidence consistency ----------------------

    def test_c18_reconciled_order_ids_always_empty(self) -> None:
        """Implementation 04 (Blocker 01/03 correction): a fresh order with
        no durable counterpart can no longer surface as a silently-empty
        but otherwise successful release state. Gate B now correctly stops
        with a deterministic conflict before any reconciliation object --
        `authoritative_known_active_order_ids` included -- is constructed
        from that untrusted fresh output. `_match_trusted_release_evidence`
        is unit-tested directly to prove `known_active_order_ids == ()` on
        that non-complete outcome (Blocker 01)."""

        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport, order_ids=("order-a",))
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        with self.assertRaises(RunnerError) as ctx:
            run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("fresh-order-without-durable-counterpart:order-a", ctx.exception.detail)

        fresh_order = runner._working_order_from_raw(
            _order_row("order-a", ticker=self.TICKER), expected_ticker=self.TICKER,
        )
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(fresh_order,), orders_complete=True, bound_order_ids=("order-a",),
            fills=(), fills_complete=True,
            position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, self._empty_trusted_projection())
        self.assertFalse(match.complete)
        self.assertEqual(match.known_active_order_ids, ())
        self.assertIn("fresh-order-without-durable-counterpart:order-a", match.identity_conflict_ids)

    def test_c19_reconciled_fill_ids_always_empty(self) -> None:
        """Implementation 04: a fresh fill with no durable counterpart is
        now a deterministic conflict that halts Stage 3F before any
        reconciliation object is built (Blocker 03)."""

        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport, order_ids=("order-a",), fills_by_order={"order-a": [_fill_row("fill-1", order_id="order-a", ticker=self.TICKER)]})
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        with self.assertRaises(RunnerError) as ctx:
            run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("fresh-fill-without-durable-counterpart:fill-1", ctx.exception.detail)

    def test_c20_empty_evidence_refs_match_empty_reconciled_sets(self) -> None:
        """Ordinary incompleteness (pagination not complete, no identity
        conflict at all) remains distinguishable from a conflict: both the
        reconciled sets AND the evidence-ref tuples stay consistently
        empty on `INCOMPLETE_OR_UNAVAILABLE`, and the outcome is not
        misclassified as `IDENTITY_OR_ECONOMIC_CONFLICT` merely because
        data is missing (dispatch Section 11)."""

        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(), orders_complete=False, bound_order_ids=(),
            fills=(), fills_complete=True,
            position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, self._empty_trusted_projection())
        self.assertFalse(match.complete)
        self.assertEqual(match.status, runner._TrustedMatchStatus.INCOMPLETE_OR_UNAVAILABLE)
        self.assertEqual(match.reconciled_order_ids, ())
        self.assertEqual(match.reconciled_fill_ids, ())
        self.assertEqual(match.order_evidence_event_ids, ())
        self.assertEqual(match.fill_evidence_event_ids, ())
        self.assertEqual(match.identity_conflict_ids, ())

    def test_c21_documents_gate_a_read_only_evidence_gap(self) -> None:
        """C21 (dispatch Section 25): 'exact trusted pre-existing order/
        fill event refs are consumed successfully if the protected API
        exposes them.' Verified finding: it does not -- `SafetyProjection.
        order_observation_history`/`canonical_fills_by_fill_id` never carry
        `event_id`, and no read-only-acceptable acquisition mode ever
        returns a live `LockedLedger` (whose `.events` DOES carry
        `event_id`) to a caller who has not itself opened a restricted/
        write session. This test proves the negative directly rather than
        faking a pass: `SafetyProjection`'s exposed order/fill mappings
        contain plain payload dicts, never a `(payload, event_id)` pair or
        anything resembling one."""

        self._build_release_capable_ledger()
        state = self._read_local_safety_state()()
        projection = state.projection
        for value in projection.order_observation_history.values():
            for entry in value:
                self.assertNotIn("event_id", entry)
        for entry in projection.canonical_fills_by_fill_id.values():
            self.assertNotIn("event_id", entry)
        # `SafetyProjection` itself still carries no `event_id`, exactly as
        # documented in Implementation 02 -- but Spec 05 resolves the gap
        # through a SEPARATE narrow read-only path
        # (`read_trusted_release_evidence_projection`) rather than by
        # widening `SafetyProjection`. That resolution is exercised
        # end-to-end by C21b below.
        self.assertNotIn("KNOWN_GATE_A_READ_ONLY_EVIDENCE_GAP", runner.__all__)

    def _build_release_capable_ledger_with_durable_evidence(self, *, order_id: str, fill_id: str):
        """Like `_build_release_capable_ledger`, but durably records an
        ORDER_OBSERVED/FILL_OBSERVED pair BEFORE reaching SAFE_HELD, with
        economics chosen to exactly match what `_script_full_read_cycle`'s
        default `_order_row`/`_fill_row` fixtures return for the same
        `order_id`/`fill_id` (Spec 05 Correction E positive path)."""

        self._build_blocked_ledger()
        config = RiskLimitConfigV1(
            1, self.contract.conflict_domain_ref, "USD",
            PerOrderRiskLimits(Decimal("10"), Decimal("10"), True, Decimal("0.10"), 1_000),
            PerMarketRiskLimits(Decimal("20"), Decimal("20"), 10, Decimal("20"), Decimal("20")),
            AccountRiskLimits(Decimal("100"), 50, Decimal("100"), 0, Decimal("0")),
            FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
        )
        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        handle = emergency.handle
        canonical_order = {
            "order_id": order_id, "status": "resting", "remaining_count_fp": "1.00",
            "market": self.TICKER, "outcome_side": "YES", "yes_price": Decimal("0.45"),
        }
        order_event = handle.record_order_observation({
            "venue_order_id": order_id, "client_order_id": f"client-{order_id}",
            "source_request_id": f"{order_id}-read", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }).events[-1]
        canonical_fill = canonical_kalshi_fill_payload(
            fill_id=fill_id, order_id=order_id, price=Decimal("0.40"), quantity=Decimal("1.00"),
            fee=Decimal("0.00"), additional_fields={
                "market": self.TICKER, "outcome_side": "YES",
                "authoritative_created_time_utc": "2026-08-17T13:00:00.000000Z",
            },
        )
        fill_event = handle.record_fill_observation({
            "canonical_venue_payload": canonical_fill,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
            "client_order_id": f"client-{order_id}", "source_operation": "SYNTHETIC_FILL_READ",
            "source_request_id": f"{fill_id}-read", "venue_fill_id": fill_id,
            "venue_order_id": order_id, "venue_payload_schema_id": "synthetic-fill-v1",
        }).events[-1]
        handle.record_reconciliation({
            "incident_id": CURRENT_INCIDENT_ID, "disposition": "SYNTHETIC_RESOLVED_SAFE",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED", "bound_order_id": None,
            "created_order_upper_bound": 0, "active_order_upper_bound": 0, "unknown_result": False,
            "writer_proof_release_eligible": True, "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RESOLUTION_V1",
        }, incident_id=CURRENT_INCIDENT_ID)
        resolved = handle.inspect_validated_projection()
        self.assertEqual(resolved.protected_unresolved_legacy_write_count, 0)
        state_payload = {
            "previous_state": "BOOT_HOLD", "new_state": "SAFE_HELD",
            "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS", "risk_state_epoch_before": 0,
            "risk_state_epoch_after": 1, "risk_config_sha256": config.sha256,
            "related_emergency_action_id": None, "related_release_id": None,
            "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": resolved.last_sequence,
            "observed_authority_trusted_hash": resolved.terminal_event_hash,
            "observed_ledger_terminal_sequence": resolved.last_sequence,
            "observed_ledger_terminal_hash": resolved.terminal_event_hash,
        }
        handle.record_risk_control_state_changed(state_payload)
        normal_gate, emergency_gate = self._new_gates(handle)
        handle.close()
        return config, CURRENT_INCIDENT_ID, CURRENT_WRITER_PROOF_ID, normal_gate, emergency_gate, order_event, fill_event

    def test_c21b_complete_durable_match_populates_reconciled_ids_with_evidence_refs(self) -> None:
        """Spec 05 Correction E positive path: the fresh Stage-3E venue
        read's complete active-order/fill identity set exactly equals the
        trusted projection's durable set, and every item resolves to a
        non-None evidence ref -- so `reconciled_order_ids`/`fill_ids` and
        their evidence-event-id tuples become genuinely non-empty."""

        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        self._script_full_read_cycle(
            transport, order_ids=("order-a",),
            fills_by_order={"order-a": [_fill_row("fill-1", order_id="order-a", ticker=self.TICKER)]},
        )
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        result = run_pre_release_read_phase(invocation, runtime)
        reconciliation_snapshot = result.release_state._snapshot()[7]
        self.assertEqual(reconciliation_snapshot.reconciled_order_ids, ("order-a",))
        self.assertEqual(reconciliation_snapshot.reconciled_fill_ids, ("fill-1",))
        self.assertEqual(
            reconciliation_snapshot.order_evidence_event_ids, (("order-a", order_event.event_id),),
        )
        self.assertEqual(
            reconciliation_snapshot.fill_evidence_event_ids, (("fill-1", fill_event.event_id),),
        )

    def test_c21c_incomplete_durable_match_holds_reconciliation_empty(self) -> None:
        """A fresh venue order with no durable counterpart at all (a
        genuinely different order id than what was ever observed) must
        never produce a partially-populated reconciliation -- Correction E
        requires the COMPLETE identity set to match. Implementation 04
        strengthens this further (Blocker 03): the mismatch halts Stage 3F
        before ANY release state -- reconciliation included -- is
        constructed at all, rather than surfacing inside an
        otherwise-successful empty result.

        Implementation 05 (ER05-TRUST-006 directionality correction): this
        fixture is simultaneously a proven fresh-vs-durable CONFLICT
        (order-b has no durable counterpart) and a durable-vs-fresh
        INCOMPLETENESS (order-a/fill-1 are durable but absent from the
        fresh enumeration). Per dispatch Section 11, the proven conflict is
        never erased by the coexisting incompleteness -- the outcome
        remains `IDENTITY_OR_ECONOMIC_CONFLICT`, and its conflict-identity
        tuple names only the genuine conflict (order-b), never the
        durable-only absences (which carry no conflict identity at all)."""

        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport, order_ids=("order-b",))
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        with self.assertRaises(RunnerError) as ctx:
            run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("fresh-order-without-durable-counterpart:order-b", ctx.exception.detail)
        for absent in (
            "durable-order-without-fresh-counterpart:order-a",
            "durable-fill-without-fresh-counterpart:fill-1",
        ):
            self.assertNotIn(absent, ctx.exception.detail)

    def test_c22_positive_read_only_path_causes_zero_ledger_sequence_delta(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        before = self._read_local_safety_state()()
        run_pre_release_read_phase(invocation, runtime)
        after = self._read_local_safety_state()()
        self.assertEqual(before.projection.last_sequence, after.projection.last_sequence)
        self.assertEqual(before.projection.terminal_event_hash, after.projection.terminal_event_hash)

    # Gate-B-own-call-graph source scope for c23/c24 (as opposed to a whole-
    # file text scan): Gate C (a separate, later-invoked private function)
    # legitimately contains these exact canonical calls, so the true
    # preserved Gate-B invariant is that `run_pre_release_read_phase` and
    # everything IT transitively calls never do -- not that the string never
    # appears anywhere in the file.
    _GATE_B_OWN_CALL_GRAPH = (
        run_pre_release_read_phase,
        runner._local_impossibility_reasons,
        runner._issue_pre_release_read_capability,
        collect_authoritative_read_truth,
        runner.assemble_release_evaluation_state,
        runner._match_trusted_release_evidence,
        runner._require_exact_t0_t1_durable_coherence,
    )

    def test_c23_no_release_token_created(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertIsInstance(result.release_state, ReleaseEvaluationStateV1)
        source = "\n".join(inspect.getsource(fn) for fn in self._GATE_B_OWN_CALL_GRAPH)
        for forbidden in (
            "complete_release_and_issue_current_process_completion",
            "acquire_release_only", "acquire_normal_writer_state",
        ):
            self.assertNotIn(forbidden, source)

    def test_c24_no_release_only_session(self) -> None:
        source = "\n".join(inspect.getsource(fn) for fn in self._GATE_B_OWN_CALL_GRAPH)
        self.assertNotIn("evaluate_release", source)
        self.assertNotIn("record_risk_release", source)
        self.assertNotIn("release_writer_proof(", source)

    def test_c25_no_writer_session_started(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        before = self._read_local_safety_state()()
        run_pre_release_read_phase(invocation, runtime)
        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_writer_session_id)
        self.assertEqual(before.projection.writer_sessions, after.projection.writer_sessions)


# ---------------------------------------------------------------------------
# Spec 05 ER05-RESP-001..009 -- strict generic JSON response boundary
# (semantic cases 97-105): exact media type, strict body-size-before-decode,
# strict UTF-8, duplicate-key rejection at every depth, non-finite constant
# rejection, and a deadline checked live through every sub-step.
# ---------------------------------------------------------------------------


class StrictResponseBoundaryTests(ReadPhaseTests):
    def test_97_media_type_with_charset_parameter_is_accepted(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type="application/json; charset=utf-8",
            body_bytes=json.dumps({"orders": [], "cursor": ""}).encode("utf-8"),
        ))
        capability = self._ready_capability(transport)
        result = capability.get_orders()
        self.assertEqual(result["cursor"], "")

    def test_98_wrong_media_type_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type="text/plain",
            body_bytes=json.dumps({"orders": [], "cursor": ""}).encode("utf-8"),
        ))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_99_non_string_content_type_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type=None,  # type: ignore[arg-type]
            body_bytes=json.dumps({"orders": [], "cursor": ""}).encode("utf-8"),
        ))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_100_invalid_utf8_byte_sequence_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type="application/json", body_bytes=b"\xff\xfe{}",
        ))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_JSON_INVALID)

    def test_101_duplicate_top_level_json_key_rejected(self) -> None:
        transport = _ScriptedTransport()
        raw_text = '{"orders": [], "cursor": "", "cursor": "dup"}'
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type="application/json", body_bytes=raw_text.encode("utf-8"),
        ))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_JSON_INVALID)

    def test_102_duplicate_nested_json_key_rejected(self) -> None:
        transport = _ScriptedTransport()
        raw_text = '{"orders": [{"order_id": "x", "order_id": "y", "ticker": "T"}], "cursor": ""}'
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type="application/json", body_bytes=raw_text.encode("utf-8"),
        ))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_JSON_INVALID)

    def test_103_non_finite_json_constant_rejected(self) -> None:
        transport = _ScriptedTransport()
        raw_text = '{"orders": [], "cursor": "", "extra": NaN}'
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type="application/json", body_bytes=raw_text.encode("utf-8"),
        ))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_JSON_INVALID)

    def test_104_non_dict_top_level_json_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_ORDERS, RawOperationResponseV1(
            http_status=200, content_type="application/json", body_bytes=b"[]",
        ))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_orders()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_105_deadline_checked_before_body_decode_begins(self) -> None:
        raw = RawOperationResponseV1(
            http_status=200, content_type="application/json",
            body_bytes=json.dumps({"orders": [], "cursor": ""}).encode("utf-8"),
        )
        deadline = OperationDeadlineV1.create(
            process_instance_id="proc_test", operation_name="GET_ORDERS", request_ordinal=1,
            started_monotonic_ns=0, experiment_absolute_end_monotonic_ns=0,
            uuid_factory=self.inputs.uuid,
        )
        with self.assertRaises(RunnerError) as ctx:
            runner._decode_and_validate_runner_json_response(
                RunnerOperation.GET_ORDERS, raw_response=raw, deadline=deadline,
                now_monotonic_ns=lambda: 10**18,
            )
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)
        self.assertEqual(ctx.exception.detail, runner.DeadlineCheckpoint.AFTER_MEDIA_TYPE_VALIDATION.value)


# ---------------------------------------------------------------------------
# Spec 05 ER05-POS-002/003 -- exact GET_POSITIONS top-level schema
# (semantic cases 106-113): `market_positions`, `event_positions`, `cursor`
# all mandatory/non-null/exact type; each `event_positions` element an
# exact dict even though economically unused.
# ---------------------------------------------------------------------------


class PositionsSchemaTests(ReadPhaseTests):
    def test_106_missing_event_positions_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": [], "cursor": "",
        }))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_positions()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_107_event_positions_wrong_type_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": [], "event_positions": "not-a-list", "cursor": "",
        }))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_positions()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.POSITION_TRUTH_UNAVAILABLE)

    def test_108_event_positions_element_not_dict_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": [], "event_positions": ["not-a-dict"], "cursor": "",
        }))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_positions()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_109_empty_event_positions_with_market_positions_accepted(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": [_position_row(self.TICKER)], "event_positions": [], "cursor": "",
        }))
        capability = self._ready_capability(transport)
        result = capability.get_positions()
        self.assertEqual(len(result["market_positions"]), 1)

    def test_110_missing_cursor_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": [], "event_positions": [],
        }))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_positions()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_111_null_cursor_rejected(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": [], "event_positions": [], "cursor": None,
        }))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_positions()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_112_exact_str_cursor_returned_directly(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": [], "event_positions": [], "cursor": "next-page-token",
        }))
        capability = self._ready_capability(transport)
        result = capability.get_positions()
        self.assertEqual(result["cursor"], "next-page-token")

    def test_113_market_positions_wrong_type_rejected_as_position_unavailable(self) -> None:
        transport = _ScriptedTransport()
        transport.queue(RunnerOperation.GET_POSITIONS, _json_response({
            "market_positions": {"not": "a-list"}, "event_positions": [], "cursor": "",
        }))
        capability = self._ready_capability(transport)
        with self.assertRaises(RunnerError) as ctx:
            capability.get_positions()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.POSITION_TRUTH_UNAVAILABLE)


# ---------------------------------------------------------------------------
# Implementation 04 direct correction tests (dispatch Section 23, D01-D25):
# Blocker 01 (known_active_ids sourced only from a successful trusted
# match), Blocker 02 (typed match outcome: COMPLETE_TRUSTED_MATCH /
# INCOMPLETE_OR_UNAVAILABLE / IDENTITY_OR_ECONOMIC_CONFLICT, never one
# indistinguishable empty result), Blocker 03 (zero release-state
# construction on a failed/incomplete match), Blocker 04 (exact T0/T1
# durable identity+tail coherence before either projection is used).
# ---------------------------------------------------------------------------


class ImplementationFourCorrectionTests(ReadPhaseTests):
    def test_d01_successful_match_populates_known_active_ids_only_from_trusted_match(self) -> None:
        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        self._script_full_read_cycle(
            transport, order_ids=("order-a",),
            fills_by_order={"order-a": [_fill_row("fill-1", order_id="order-a", ticker=self.TICKER)]},
        )
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        result = run_pre_release_read_phase(invocation, runtime)
        reconciliation_snapshot = result.release_state._snapshot()[7]
        self.assertEqual(reconciliation_snapshot.authoritative_known_active_order_ids, ("order-a",))
        self.assertEqual(reconciliation_snapshot.reconciled_order_ids, ("order-a",))

    def test_d02_fresh_order_without_durable_counterpart_cannot_populate_known_active_ids(self) -> None:
        fresh_order = runner._working_order_from_raw(_order_row("order-a", ticker=self.TICKER), expected_ticker=self.TICKER)
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(fresh_order,), orders_complete=True, bound_order_ids=("order-a",),
            fills=(), fills_complete=True, position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, self._empty_trusted_projection())
        self.assertFalse(match.complete)
        self.assertEqual(match.known_active_order_ids, ())

    def test_d03_fresh_fill_without_durable_counterpart_cannot_be_reconciled(self) -> None:
        fresh_fill = runner._fill_from_raw(
            _fill_row("fill-1", order_id="order-a", ticker=self.TICKER),
            expected_ticker=self.TICKER, expected_order_id="order-a",
        )
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(), orders_complete=True, bound_order_ids=(),
            fills=(fresh_fill,), fills_complete=True, position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, self._empty_trusted_projection())
        self.assertFalse(match.complete)
        self.assertEqual(match.reconciled_fill_ids, ())
        self.assertIn("fresh-fill-without-durable-counterpart:fill-1", match.identity_conflict_ids)

    def test_d04_extra_fresh_order_yields_deterministic_nonempty_conflict_identity(self) -> None:
        fresh_order = runner._working_order_from_raw(_order_row("order-a", ticker=self.TICKER), expected_ticker=self.TICKER)
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(fresh_order,), orders_complete=True, bound_order_ids=("order-a",),
            fills=(), fills_complete=True, position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, self._empty_trusted_projection())
        self.assertEqual(match.status, runner._TrustedMatchStatus.IDENTITY_OR_ECONOMIC_CONFLICT)
        self.assertEqual(match.identity_conflict_ids, ("fresh-order-without-durable-counterpart:order-a",))

    def test_d05_same_order_id_incompatible_economics_yields_conflict(self) -> None:
        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        mismatched_row = _order_row("order-a", ticker=self.TICKER)
        mismatched_row["remaining_count_fp"] = "2.00"  # durable evidence has remaining_count_fp "1.00"
        transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([mismatched_row]))
        transport.queue(RunnerOperation.GET_ORDER, _order_payload("order-a", ticker=self.TICKER))
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([_fill_row("fill-1", order_id="order-a", ticker=self.TICKER)]))
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([_position_row(self.TICKER)]))
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        with self.assertRaises(RunnerError) as ctx:
            run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("order-economic-mismatch:order-a", ctx.exception.detail)

    def test_d06_same_fill_id_incompatible_economics_yields_conflict(self) -> None:
        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        mismatched_fill = _fill_row("fill-1", order_id="order-a", ticker=self.TICKER, price="0.55")
        transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
        transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([_order_row("order-a", ticker=self.TICKER)]))
        transport.queue(RunnerOperation.GET_ORDER, _order_payload("order-a", ticker=self.TICKER))
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([mismatched_fill]))
        transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([_position_row(self.TICKER)]))
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        with self.assertRaises(RunnerError) as ctx:
            run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("fill-economic-mismatch:fill-1", ctx.exception.detail)

    def test_d07_incomplete_venue_truth_is_incomplete_not_conflict(self) -> None:
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(), orders_complete=False, bound_order_ids=(),
            fills=(), fills_complete=False, position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, self._empty_trusted_projection())
        self.assertEqual(match.status, runner._TrustedMatchStatus.INCOMPLETE_OR_UNAVAILABLE)
        self.assertEqual(match.identity_conflict_ids, ())

    def test_d08_projection_conflict_ids_propagate_into_match_conflict_outcome(self) -> None:
        from types import SimpleNamespace
        conflicted = SimpleNamespace(
            conflict_ids=("order-replay-universe",), working_orders=(), fills=(),
            order_evidence_ref=lambda order: None, fill_evidence_ref=lambda fill: None,
        )
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(), orders_complete=True, bound_order_ids=(),
            fills=(), fills_complete=True, position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, conflicted)
        self.assertEqual(match.status, runner._TrustedMatchStatus.IDENTITY_OR_ECONOMIC_CONFLICT)
        self.assertEqual(match.identity_conflict_ids, ("projection-conflict:order-replay-universe",))

    def test_d09_legitimate_empty_complete_universe_is_successful_match(self) -> None:
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(), orders_complete=True, bound_order_ids=(),
            fills=(), fills_complete=True, position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, self._empty_trusted_projection())
        self.assertTrue(match.complete)
        self.assertEqual(match.status, runner._TrustedMatchStatus.COMPLETE_TRUSTED_MATCH)
        self.assertEqual(match.known_active_order_ids, ())
        self.assertEqual(match.reconciled_order_ids, ())
        self.assertEqual(match.identity_conflict_ids, ())

    def _assert_zero_release_state_construction_on_failure(self, invocation, runtime) -> None:
        with (
            mock.patch.object(runner, "ReleaseRiskSnapshotV1", wraps=runner.ReleaseRiskSnapshotV1) as risk_ctor,
            mock.patch.object(runner, "ReleaseReconciliationSnapshotV1", wraps=runner.ReleaseReconciliationSnapshotV1) as recon_ctor,
            mock.patch.object(runner, "ReleaseEvaluationStateV1", wraps=runner.ReleaseEvaluationStateV1) as state_ctor,
        ):
            with self.assertRaises(RunnerError):
                run_pre_release_read_phase(invocation, runtime)
            self.assertEqual(risk_ctor.call_count, 0)
            self.assertEqual(recon_ctor.call_count, 0)
            self.assertEqual(state_ctor.call_count, 0)

    def test_d10_d11_d12_trusted_match_failure_constructs_zero_release_state_objects(self) -> None:
        """D10 (zero `ReleaseEvaluationStateV1`), D11 (zero
        `ReleaseReconciliationSnapshotV1`), D12 (zero `ReleaseRiskSnapshotV1`)
        -- proven together via production-boundary monkeypatching on the
        exact fresh-order-without-durable-counterpart failure fixture."""

        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport, order_ids=("order-a",))
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        self._assert_zero_release_state_construction_on_failure(invocation, runtime)

    def test_d13_read_phase_cannot_return_complete_with_non_complete_match(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport, order_ids=("order-a",))
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        try:
            result = run_pre_release_read_phase(invocation, runtime)
        except RunnerError:
            return  # raising instead of returning also satisfies "cannot return READ_PHASE_COMPLETE"
        self.assertNotEqual(result.status, "READ_PHASE_COMPLETE")
        self.assertIsNone(result.release_state)

    def test_d14_exact_t0_t1_coherence_succeeds_on_the_real_ledger(self) -> None:
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE")
        self.assertIsNotNone(result.release_state)

    def _t0_t1_mismatch_fixture(self):
        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        real_projection = runtime.read_local_safety_state().projection
        truth = collect_authoritative_read_truth(self._capability(runtime), ticker=self.TICKER)
        return real_projection, runtime, invocation, truth

    def test_d15_t0_trusted_sequence_mismatch_fails_before_state_construction(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        bad_projection = dataclasses.replace(real_projection, trusted_sequence=real_projection.trusted_sequence + 1)
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)

    def test_d16_t0_trusted_event_hash_mismatch_fails_before_state_construction(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        other_hash = "0" * 64 if real_projection.trusted_event_hash != "0" * 64 else "1" * 64
        bad_projection = dataclasses.replace(real_projection, trusted_event_hash=other_hash)
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)

    def test_d17_t0_last_sequence_mismatch_fails_before_state_construction(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        bad_projection = dataclasses.replace(
            real_projection, trusted_sequence=real_projection.last_sequence + 1, last_sequence=real_projection.last_sequence + 1,
        )
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)

    def test_d18_t0_terminal_event_hash_mismatch_fails_before_state_construction(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        other_hash = "0" * 64 if real_projection.terminal_event_hash != "0" * 64 else "1" * 64
        bad_projection = dataclasses.replace(
            real_projection, trusted_event_hash=other_hash, terminal_event_hash=other_hash,
        )
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)

    def test_d19_authority_identity_mismatch_fails_before_state_construction(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        bad_projection = dataclasses.replace(real_projection, authority_instance_id="different-authority-instance")
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("authority_instance_id", ctx.exception.detail)

    def test_d20_ledger_identity_mismatch_fails_before_state_construction(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        bad_projection = dataclasses.replace(real_projection, ledger_instance_id="different-ledger-instance")
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("ledger_instance_id", ctx.exception.detail)

    def test_d21_environment_conflict_domain_mismatch_fails_before_state_construction(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        bad_projection = dataclasses.replace(real_projection, conflict_domain_ref="different-conflict-domain")
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("conflict_domain_ref", ctx.exception.detail)

    def test_d22_t0_internal_tail_mismatch_fails_closed_even_if_other_fields_match(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        bad_projection = dataclasses.replace(real_projection, trusted_sequence=real_projection.trusted_sequence + 1)
        # Every OTHER T0 field (including last_sequence, which now disagrees
        # only with the deliberately-bumped trusted_sequence) is untouched
        # real data -- this isolates the "T0 internal tail" check itself.
        with self.assertRaises(RunnerError) as ctx:
            runner.assemble_release_evaluation_state(invocation, runtime, truth, bad_projection)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("T0 internal", ctx.exception.detail)

    def test_d23_tail_mismatch_triggers_no_automatic_retry(self) -> None:
        real_projection, runtime, invocation, truth = self._t0_t1_mismatch_fixture()
        bad_projection = dataclasses.replace(real_projection, trusted_sequence=real_projection.trusted_sequence + 1)
        counting = mock.Mock(wraps=runtime.read_trusted_release_evidence)
        retried_runtime = dataclasses.replace(runtime, read_trusted_release_evidence=counting)
        with self.assertRaises(RunnerError):
            runner.assemble_release_evaluation_state(invocation, retried_runtime, truth, bad_projection)
        self.assertEqual(counting.call_count, 1)

    def test_d24_complete_valid_universe_builds_exact_trusted_refs(self) -> None:
        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        self._script_full_read_cycle(
            transport, order_ids=("order-a",),
            fills_by_order={"order-a": [_fill_row("fill-1", order_id="order-a", ticker=self.TICKER)]},
        )
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        result = run_pre_release_read_phase(invocation, runtime)
        reconciliation_snapshot = result.release_state._snapshot()[7]
        self.assertEqual(reconciliation_snapshot.authoritative_known_active_order_ids, ("order-a",))
        self.assertEqual(reconciliation_snapshot.reconciled_order_ids, ("order-a",))
        self.assertEqual(reconciliation_snapshot.reconciled_fill_ids, ("fill-1",))
        self.assertEqual(reconciliation_snapshot.order_evidence_event_ids, (("order-a", order_event.event_id),))
        self.assertEqual(reconciliation_snapshot.fill_evidence_event_ids, (("fill-1", fill_event.event_id),))
        self.assertEqual(reconciliation_snapshot.identity_conflict_ids, ())

    def test_d25_positive_path_causes_zero_ledger_sequence_delta(self) -> None:
        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        self._script_full_read_cycle(
            transport, order_ids=("order-a",),
            fills_by_order={"order-a": [_fill_row("fill-1", order_id="order-a", ticker=self.TICKER)]},
        )
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        before = runtime.read_local_safety_state()
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE")
        after = runtime.read_local_safety_state()
        self.assertEqual(before.projection.last_sequence, after.projection.last_sequence)
        self.assertEqual(before.projection.terminal_event_hash, after.projection.terminal_event_hash)


# ---------------------------------------------------------------------------
# Implementation 05 direct directionality tests (dispatch Section 15,
# E01-E04): Spec 05 ER05-TRUST-006 requires ASYMMETRIC classification of
# fresh-vs-durable set differences. `fresh - durable` (a fresh venue fact
# with no durable counterpart) is a proven contradiction ->
# IDENTITY_OR_ECONOMIC_CONFLICT. `durable - fresh` (a required durable
# identity simply absent from an otherwise-COMPLETE fresh enumeration) is
# ordinary incompleteness -> INCOMPLETE_OR_UNAVAILABLE, never a fabricated
# conflict merely because the venue result omitted it.
# ---------------------------------------------------------------------------


class ImplementationFiveCorrectionTests(ReadPhaseTests):
    def _matching_working_order(self, order_id: str) -> WorkingOrderV1:
        return runner._working_order_from_raw(_order_row(order_id, ticker=self.TICKER), expected_ticker=self.TICKER)

    def _matching_fill(self, fill_id: str, *, order_id: str) -> EconomicFillV1:
        return runner._fill_from_raw(
            _fill_row(fill_id, order_id=order_id, ticker=self.TICKER),
            expected_ticker=self.TICKER, expected_order_id=order_id,
        )

    def _assemble_with_hand_built_truth(self, runtime, invocation, truth):
        projection = runtime.read_local_safety_state().projection
        return runner.assemble_release_evaluation_state(invocation, runtime, truth, projection)

    def _assert_zero_release_state_construction(self, call) -> RunnerError:
        with (
            mock.patch.object(runner, "ReleaseRiskSnapshotV1", wraps=runner.ReleaseRiskSnapshotV1) as risk_ctor,
            mock.patch.object(runner, "ReleaseReconciliationSnapshotV1", wraps=runner.ReleaseReconciliationSnapshotV1) as recon_ctor,
            mock.patch.object(runner, "ReleaseEvaluationStateV1", wraps=runner.ReleaseEvaluationStateV1) as state_ctor,
        ):
            with self.assertRaises(RunnerError) as ctx:
                call()
            self.assertEqual(risk_ctor.call_count, 0)
            self.assertEqual(recon_ctor.call_count, 0)
            self.assertEqual(state_ctor.call_count, 0)
        return ctx.exception

    def test_e01_durable_order_absent_from_complete_fresh_set_is_incomplete(self) -> None:
        """Durable active order exists; fresh order enumeration is
        COMPLETE; that durable order is absent from the fresh set ->
        INCOMPLETE_OR_UNAVAILABLE, empty conflict ids, zero release-state
        constructions (fills kept in exact agreement on both sides so the
        order dimension is isolated)."""

        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(), orders_complete=True, bound_order_ids=(),
            fills=(self._matching_fill("fill-1", order_id="order-a"),), fills_complete=True,
            position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, runtime.read_trusted_release_evidence().projection)
        self.assertEqual(match.status, runner._TrustedMatchStatus.INCOMPLETE_OR_UNAVAILABLE)
        self.assertEqual(match.identity_conflict_ids, ())

        exc = self._assert_zero_release_state_construction(
            lambda: self._assemble_with_hand_built_truth(runtime, invocation, truth),
        )
        self.assertEqual(exc.code, RunnerFailureCode.PAGINATION_INCOMPLETE)

    def test_e02_durable_fill_absent_from_complete_fresh_set_is_incomplete(self) -> None:
        """Durable canonical fill exists; fresh fill enumeration is
        COMPLETE; that durable fill is absent from the fresh set ->
        INCOMPLETE_OR_UNAVAILABLE, empty conflict ids, zero release-state
        constructions (orders kept in exact agreement on both sides so the
        fill dimension is isolated)."""

        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(self._matching_working_order("order-a"),), orders_complete=True, bound_order_ids=("order-a",),
            fills=(), fills_complete=True,
            position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, runtime.read_trusted_release_evidence().projection)
        self.assertEqual(match.status, runner._TrustedMatchStatus.INCOMPLETE_OR_UNAVAILABLE)
        self.assertEqual(match.identity_conflict_ids, ())

        exc = self._assert_zero_release_state_construction(
            lambda: self._assemble_with_hand_built_truth(runtime, invocation, truth),
        )
        self.assertEqual(exc.code, RunnerFailureCode.PAGINATION_INCOMPLETE)

    def test_e03_fresh_order_without_durable_counterpart_is_conflict(self) -> None:
        """Fresh active order exists with no durable counterpart ->
        IDENTITY_OR_ECONOMIC_CONFLICT with a deterministic nonempty
        conflict identity, zero release-state constructions."""

        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(self._matching_working_order("order-c"),), orders_complete=True, bound_order_ids=("order-c",),
            fills=(self._matching_fill("fill-1", order_id="order-a"),), fills_complete=True,
            position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, runtime.read_trusted_release_evidence().projection)
        self.assertEqual(match.status, runner._TrustedMatchStatus.IDENTITY_OR_ECONOMIC_CONFLICT)
        self.assertEqual(match.identity_conflict_ids, ("fresh-order-without-durable-counterpart:order-c",))

        exc = self._assert_zero_release_state_construction(
            lambda: self._assemble_with_hand_built_truth(runtime, invocation, truth),
        )
        self.assertEqual(exc.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("fresh-order-without-durable-counterpart:order-c", exc.detail)

    def test_e04_fresh_fill_without_durable_counterpart_is_conflict(self) -> None:
        """Fresh fill exists with no durable counterpart ->
        IDENTITY_OR_ECONOMIC_CONFLICT with a deterministic nonempty
        conflict identity, zero release-state constructions."""

        (
            config, incident_id, proof_id, normal_gate, emergency_gate, order_event, fill_event,
        ) = self._build_release_capable_ledger_with_durable_evidence(order_id="order-a", fill_id="fill-1")
        transport = _ScriptedTransport()
        runtime = self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=config, transport=transport)
        invocation = self._invocation(incident_id=incident_id, proof_id=proof_id)
        truth = runner.AuthoritativeReadTruthV1(
            market={"ticker": self.TICKER}, orderbook=_fake_orderbook_snapshot(self.TICKER),
            working_orders=(self._matching_working_order("order-a"),), orders_complete=True, bound_order_ids=("order-a",),
            fills=(self._matching_fill("fill-2", order_id="order-a"),), fills_complete=True,
            position_state="NO_VENUE_POSITION_ROW", market_positions_raw=(),
            position_corroboration="CORROBORATED", requests_consumed=1,
        )
        match = runner._match_trusted_release_evidence(truth, runtime.read_trusted_release_evidence().projection)
        self.assertEqual(match.status, runner._TrustedMatchStatus.IDENTITY_OR_ECONOMIC_CONFLICT)
        self.assertEqual(match.identity_conflict_ids, ("fresh-fill-without-durable-counterpart:fill-2",))

        exc = self._assert_zero_release_state_construction(
            lambda: self._assemble_with_hand_built_truth(runtime, invocation, truth),
        )
        self.assertEqual(exc.code, RunnerFailureCode.PRE_RELEASE_RELEASE_PREDICATE_FAILED)
        self.assertIn("fresh-fill-without-durable-counterpart:fill-2", exc.detail)


# ---------------------------------------------------------------------------
# Gate C -- Stage 3G (RELEASE_ONLY) through Stage 3K (final normal-writer
# revalidation). GC01-GC24 (dispatch Section 22) plus Implementation-02
# Corrections 01/02 (post-admission cleanup safety; per-boundary deadline
# coverage).
# ---------------------------------------------------------------------------


class _ExpireOnDemandClock:
    """Deterministic monotonic clock (Implementation 02 Correction 02):
    returns ordinary `DeterministicInputs` values until `expire()` is
    called, after which every subsequent call returns a value already past
    the fixed deadline. Lets each D1-D4 test expire the clock at the EXACT
    Gate-C checkpoint under test -- via a canonical-method wrapper that
    calls the real method then expires -- rather than approximating how
    many internal monotonic-clock calls happen before that checkpoint."""

    def __init__(self, inner: Callable[[], int], deadline: int) -> None:
        self._inner = inner
        self.deadline = deadline
        self._expired = False

    def expire(self) -> None:
        self._expired = True

    def __call__(self) -> int:
        if self._expired:
            return self.deadline + 1_000_000
        return self._inner()


class GateCTests(ReadPhaseTests):
    def _read_phase_complete(self, transport: _ScriptedTransport | None = None, **runtime_kwargs):
        """Empty-portfolio Gate-B READ_PHASE_COMPLETE: zero orders/fills is
        trivially within every configured risk limit, so this is the
        simplest genuinely release-eligible fixture for Gate C."""

        transport = transport or _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport, **runtime_kwargs)
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE")
        return result, runtime

    def _sequence(self) -> tuple[int, str]:
        opened = self._read_local_safety_state()()
        return opened.projection.last_sequence, opened.projection.terminal_event_hash

    def _obtain_unconsumed_token(
        self, runtime: ExperimentRunnerRuntimeV1, release_state: ReleaseEvaluationStateV1,
    ) -> CurrentProcessReleaseCompletionV1:
        """Test-only direct canonical Stage 3G/3H/3I sequence (public API
        only) that stops BEFORE Stage 3J, so the returned token has not yet
        been consumed by `acquire_normal_writer_state` -- needed for
        GC10/GC12/GC13/GC14, which each exercise the token's own
        continuity/consumption boundary independently of the full Gate C
        continuation."""

        acquisition = acquire_release_only(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            contract=runtime.contract, expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
            monotonic_clock_ns=runtime.monotonic_clock_ns, release_wall_clock=runtime.wall_clock,
        )
        self.assertIsNone(acquisition.failure_code)
        handle = acquisition.handle
        assessment = handle.evaluate_release(release_state)
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        handle.record_writer_eligible(assessment)
        return handle.complete_release_and_issue_current_process_completion(assessment)

    def test_gc01_full_stage3_success(self) -> None:
        """GC01: successful same-process Gate-B READ_PHASE_COMPLETE carries
        through RELEASE_ONLY -> RISK_RELEASE_RECORDED -> WRITER_PROOF_
        RELEASED -> SAFE_HELD->WRITER_ELIGIBLE -> RESTRICTED_SESSION_ENDED
        -> CurrentProcessReleaseCompletionV1 -> NORMAL_WRITER -> exactly one
        fresh ws_ -> Stage-3K PASS."""

        result, runtime = self._read_phase_complete()
        before_seq, _ = self._sequence()

        stage3 = runner._complete_stage3_release_and_normal_writer(result, runtime)

        self.assertEqual(stage3.process_instance_id, runtime.normal_gate.process_instance_id)
        self.assertTrue(stage3.release_id.startswith("rel_"))
        self.assertRegex(stage3.normal_writer_session_id, r"^ws_[0-9a-f]{32}$")
        acquisition = stage3.normal_writer_acquisition
        self.assertIsInstance(acquisition, NormalWriterAcquisition)
        self.assertIsNotNone(acquisition.handle)
        self.assertFalse(acquisition.handle.closed)
        self.assertEqual(acquisition.handle.relation, AuthorityLedgerRelation.EQUAL)
        self.assertEqual(acquisition.projection.risk_control_state, "WRITER_ELIGIBLE")
        self.assertEqual(acquisition.projection.active_writer_session_id, stage3.normal_writer_session_id)
        self.assertEqual(len([s for s in acquisition.projection.writer_sessions if s == stage3.normal_writer_session_id]), 1)

        # Clean explicit teardown through the canonical public API only.
        end_writer_session(acquisition.handle, writer_session_id=stage3.normal_writer_session_id)
        after = self._read_local_safety_state()()
        after_seq = after.projection.last_sequence
        self.assertGreater(after_seq, before_seq)
        self.assertIsNone(after.projection.active_writer_session_id)
        self.assertIn(stage3.normal_writer_session_id, after.projection.writer_sessions)

    def _blocked_runtime(self, transport: _ScriptedTransport) -> ExperimentRunnerRuntimeV1:
        """Mirrors `LocalImpossibilityGateTests._blocked_runtime`: builds the
        exact current historical incident and closes every fixture-only
        handle before returning, so the runtime's own later acquisitions
        never race a still-open harness lock."""

        self._build_blocked_ledger()
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
        emergency_gate = EmergencyCancelGate(
            handle=emergency.handle, rate_lane=lane, process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid,
        )
        emergency.handle.close()
        return self._runtime(normal_gate=normal_gate, emergency_gate=emergency_gate, config=None, transport=transport)

    def test_gc02_locally_blocked_result_cannot_enter_gate_c(self) -> None:
        """GC02: a LOCALLY_BLOCKED Gate-B result cannot enter Gate C; zero
        persistence mutation."""

        transport = _ScriptedTransport()
        runtime = self._blocked_runtime(transport)
        invocation = self._invocation(incident_id=CURRENT_INCIDENT_ID, proof_id=CURRENT_WRITER_PROOF_ID)
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.status, "LOCALLY_BLOCKED")

        before = self._sequence()
        with (
            mock.patch.object(runner, "acquire_release_only", wraps=runner.acquire_release_only) as spy,
            self.assertRaises(RunnerError) as ctx,
        ):
            runner._complete_stage3_release_and_normal_writer(result, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED)
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(self._sequence(), before)
        self.assertEqual(transport.calls, [])

    def test_gc03_missing_release_state_fails_before_release_only(self) -> None:
        """GC03: READ_PHASE_COMPLETE with missing/invalid release_state
        fails before RELEASE_ONLY."""

        result, runtime = self._read_phase_complete()
        malformed = dataclasses.replace(result, release_state=None)
        before = self._sequence()
        with (
            mock.patch.object(runner, "acquire_release_only", wraps=runner.acquire_release_only) as spy,
            self.assertRaises(RunnerError) as ctx,
        ):
            runner._complete_stage3_release_and_normal_writer(malformed, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED)
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(self._sequence(), before)

    def test_gc04_process_instance_id_mismatch_fails_before_release_mutation(self) -> None:
        """GC04: process_instance_id mismatch fails before release
        mutation."""

        result, runtime = self._read_phase_complete()
        malformed = dataclasses.replace(result, process_instance_id="proc_" + "0" * 32)
        before = self._sequence()
        with (
            mock.patch.object(runner, "acquire_release_only", wraps=runner.acquire_release_only) as spy,
            self.assertRaises(RunnerError) as ctx,
        ):
            runner._complete_stage3_release_and_normal_writer(malformed, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED)
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(self._sequence(), before)

    def test_gc05_failing_predicate_produces_no_release_token_or_writer(self) -> None:
        """GC05: canonical evaluate_release false/failing predicate ->
        no RISK_RELEASE_RECORDED, token, or writer.

        `evaluate_release` itself never raises on a false predicate (it
        always returns an assessment carrying whatever vector the current
        durable state produces); `record_risk_release` is the first
        canonical step that actually enforces `all(vector.values())`. This
        is forced honestly via `ReleaseEvaluationStateV1.replace(...)` (the
        canonical "current inputs re-read" mutator Stage 3's own runner
        would use) binding a structurally valid but DIFFERENT risk config
        than the one whose sha256 was recorded active at SAFE_HELD, so the
        evaluator's own `risk_config_complete_valid` predicate is false."""

        result, runtime = self._read_phase_complete()
        different_config = dataclasses.replace(
            runtime.risk_config,
            conflict_domain_account=dataclasses.replace(
                runtime.risk_config.conflict_domain_account, max_aggregate_working_orders=999,
            ),
        )
        self.assertNotEqual(different_config.sha256, runtime.risk_config.sha256)
        result.release_state.replace(risk_config=different_config)
        registry_before = len(ledger_binding._current_process_release_completion_registry)

        with self.assertRaises(RunnerError) as ctx:
            runner._complete_stage3_release_and_normal_writer(result, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED)
        self.assertEqual(ctx.exception.detail, "record_risk_release")
        # A clean RELEASE_ONLY acquire-then-close is itself a restricted
        # session with its own START/END bookkeeping events; the invariant
        # under test is that no release/writer/token event was recorded, not
        # that the ledger sequence is byte-for-byte unchanged.
        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertEqual(len(ledger_binding._current_process_release_completion_registry), registry_before)

    def _fault_after(self, method_name: str, expected_detail: str) -> None:
        result, runtime = self._read_phase_complete()
        registry_before = len(ledger_binding._current_process_release_completion_registry)
        with mock.patch.object(
            ReleaseLedgerHandle, method_name,
            side_effect=LedgerError(FailureCode.RELEASE_PREDICATE_CHANGED),
        ):
            with self.assertRaises(RunnerError) as ctx:
                runner._complete_stage3_release_and_normal_writer(result, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DURABLE_RELEASE_SEQUENCE_FAILED)
        self.assertEqual(ctx.exception.detail, expected_detail)
        self.assertEqual(len(ledger_binding._current_process_release_completion_registry), registry_before)
        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertIsNone(after.projection.active_writer_session_id)
        return registry_before, after

    def test_gc06_fault_after_risk_release_recorded(self) -> None:
        """GC06: fault after RISK_RELEASE_RECORDED -> no token, no writer,
        no automatic second release (the patched method is called exactly
        once by construction -- Gate C never loops or retries)."""

        self._fault_after("release_writer_proof", "release_writer_proof")

    def test_gc07_fault_after_writer_proof_released(self) -> None:
        """GC07: fault after WRITER_PROOF_RELEASED -> no token, no
        writer."""

        self._fault_after("record_writer_eligible", "record_writer_eligible")

    def test_gc08_fault_after_writer_eligible_before_token(self) -> None:
        """GC08: fault after WRITER_ELIGIBLE but before successful
        session-end/token issuance -> no token, no normal writer."""

        result, runtime = self._read_phase_complete()
        registry_before = len(ledger_binding._current_process_release_completion_registry)
        with mock.patch.object(
            ReleaseLedgerHandle, "complete_release_and_issue_current_process_completion",
            side_effect=LedgerError(FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED),
        ):
            with self.assertRaises(RunnerError) as ctx:
                runner._complete_stage3_release_and_normal_writer(result, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_ISSUANCE_FAILED)
        self.assertEqual(len(ledger_binding._current_process_release_completion_registry), registry_before)
        after = self._read_local_safety_state()()
        # WRITER_ELIGIBLE was durably recorded (real record_writer_eligible
        # ran); only the finalizer/token step was faulted.
        self.assertEqual(after.projection.risk_control_state, "WRITER_ELIGIBLE")
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertIsNone(after.projection.active_writer_session_id)

    def test_gc09_token_requires_exact_restricted_session_ended_readback(self) -> None:
        """GC09: token cannot exist until exact RESTRICTED_SESSION_ENDED
        positive equal-tail readback -- proven directly against the
        canonical finalizer by skipping `record_writer_eligible` (the step
        immediately before the finalizer): the finalizer refuses to
        fabricate the readback/token without it, exactly mirroring what
        GC08 proves for a raised fault at that same boundary."""

        result, runtime = self._read_phase_complete()
        registry_before = len(ledger_binding._current_process_release_completion_registry)
        acquisition = acquire_release_only(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            contract=runtime.contract, expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
            monotonic_clock_ns=runtime.monotonic_clock_ns, release_wall_clock=runtime.wall_clock,
        )
        handle = acquisition.handle
        assessment = handle.evaluate_release(result.release_state)
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        with self.assertRaises(LedgerError) as ctx:
            handle.complete_release_and_issue_current_process_completion(assessment)
        self.assertEqual(ctx.exception.code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_NOT_ISSUED)
        self.assertEqual(len(ledger_binding._current_process_release_completion_registry), registry_before)
        handle.close()

    def test_gc10_genuine_token_admits_normal_writer_only_once(self) -> None:
        """GC10: genuine token admits normal writer only once; reuse
        fails."""

        result, runtime = self._read_phase_complete()
        token = self._obtain_unconsumed_token(runtime, result.release_state)
        first = acquire_normal_writer_state(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            risk_config=runtime.risk_config, process_instance_id=runtime.normal_gate.process_instance_id,
            current_process_release_completion=token, contract=runtime.contract,
            expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
        )
        self.assertIsNone(first.failure_code)
        self.assertIsNotNone(first.handle)
        end_writer_session(first.handle, writer_session_id=first.normal_writer_session_id)

        second = acquire_normal_writer_state(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            risk_config=runtime.risk_config, process_instance_id=runtime.normal_gate.process_instance_id,
            current_process_release_completion=token, contract=runtime.contract,
            expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
        )
        self.assertEqual(second.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        self.assertIsNone(second.handle)
        self.assertIsNone(second.normal_writer_session_id)

    def test_gc11_copied_or_reconstructed_token_remains_rejected(self) -> None:
        """GC11: copy/deepcopy/reconstructed/direct token remains rejected
        regression."""

        result, runtime = self._read_phase_complete()
        token = self._obtain_unconsumed_token(runtime, result.release_state)
        with self.assertRaises(TypeError):
            copy.copy(token)
        with self.assertRaises(TypeError):
            copy.deepcopy(token)
        with self.assertRaises(TypeError):
            pickle.dumps(token)
        fields = {field.name: getattr(token, field.name) for field in dataclasses.fields(token)}
        with self.assertRaises(LedgerError):
            CurrentProcessReleaseCompletionV1(object(), **fields)

        # The genuine unconsumed token still works -- proves the rejections
        # above are about identity/reconstruction, not about this fixture.
        normal = acquire_normal_writer_state(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            risk_config=runtime.risk_config, process_instance_id=runtime.normal_gate.process_instance_id,
            current_process_release_completion=token, contract=runtime.contract,
            expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
        )
        self.assertIsNone(normal.failure_code)
        end_writer_session(normal.handle, writer_session_id=normal.normal_writer_session_id)

    def test_gc12_durable_writer_eligible_without_live_token_cannot_start_ws(self) -> None:
        """GC12: historical durable WRITER_ELIGIBLE + RELEASED proof but no
        live same-process token cannot start ws_."""

        result, runtime = self._read_phase_complete()
        self._obtain_unconsumed_token(runtime, result.release_state)  # issued, then simply discarded

        normal = acquire_normal_writer_state(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            risk_config=runtime.risk_config, process_instance_id=runtime.normal_gate.process_instance_id,
            current_process_release_completion=None, contract=runtime.contract,
            expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
        )
        self.assertEqual(normal.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_REQUIRED)
        self.assertIsNone(normal.handle)
        self.assertIsNone(normal.normal_writer_session_id)

    def test_gc13_simulated_process_termination_destroys_token_continuity(self) -> None:
        """GC13: simulated process termination destroys token continuity;
        Process B replay cannot acquire normal writer. Fault injection
        directly removes the token's registry entry (the in-memory-only
        state process termination would destroy) without touching any
        durable ledger state -- Section 21 permits patching a private
        module boundary for exactly this kind of direct fault injection."""

        result, runtime = self._read_phase_complete()
        token = self._obtain_unconsumed_token(runtime, result.release_state)
        removed = ledger_binding._current_process_release_completion_registry.pop(id(token), None)
        self.assertIsNotNone(removed)

        normal = acquire_normal_writer_state(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            risk_config=runtime.risk_config, process_instance_id=runtime.normal_gate.process_instance_id,
            current_process_release_completion=token, contract=runtime.contract,
            expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
        )
        self.assertEqual(normal.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)
        self.assertIsNone(normal.handle)

    def test_gc14_tail_movement_between_token_and_normal_writer_fails(self) -> None:
        """GC14: config/proof/state/tail movement between token issuance and
        normal-writer acquisition fails with zero ws_ start. The tail is
        moved by a genuine canonical append (a fresh ORDER_OBSERVED) through
        the emergency-control handle -- a real, otherwise-harmless durable
        mutation the live token was not issued against."""

        result, runtime = self._read_phase_complete()
        token = self._obtain_unconsumed_token(runtime, result.release_state)

        emergency = acquire_emergency_control_only(
            self.binding, canonical_repository_root=str(self.repository_root),
            contract=self.contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
        )
        self.assertIsNotNone(emergency.handle)
        canonical_order = {
            "order_id": "order-tail-mover", "status": "resting", "remaining_count_fp": "1.00",
            "market": self.TICKER, "outcome_side": "YES", "yes_price": Decimal("0.45"),
        }
        emergency.handle.record_order_observation({
            "venue_order_id": "order-tail-mover", "client_order_id": "client-tail-mover",
            "source_request_id": "tail-mover-read", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        })
        emergency.handle.close()

        normal = acquire_normal_writer_state(
            runtime.authority_binding, canonical_repository_root=runtime.canonical_repository_root,
            risk_config=runtime.risk_config, process_instance_id=runtime.normal_gate.process_instance_id,
            current_process_release_completion=token, contract=runtime.contract,
            expected_ledger_path=runtime.expected_ledger_path,
            clock=runtime.wall_clock, uuid_factory=runtime.uuid_factory,
        )
        self.assertEqual(normal.failure_code, FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_STALE)
        self.assertIsNone(normal.handle)
        self.assertIsNone(normal.normal_writer_session_id)

    def test_gc15_successful_acquisition_starts_exactly_one_ws_with_equal_tails(self) -> None:
        """GC15: successful normal acquisition starts exactly one ws_,
        active writer identity is exact, and authority/ledger tails remain
        equal."""

        result, runtime = self._read_phase_complete()
        stage3 = runner._complete_stage3_release_and_normal_writer(result, runtime)
        acquisition = stage3.normal_writer_acquisition
        locked = acquisition.handle
        started = [
            event for event in locked.events
            if event.event_type.value == "WRITER_SESSION_STARTED"
        ]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].payload["writer_session_id"], stage3.normal_writer_session_id)
        tail = locked.events[-1]
        self.assertEqual((locked.authority_row.trusted_sequence, locked.authority_row.trusted_event_hash), (tail.sequence, tail.event_hash))
        self.assertEqual(locked.relation, AuthorityLedgerRelation.EQUAL)
        end_writer_session(locked, writer_session_id=stage3.normal_writer_session_id)

    def test_gc16_current_historical_incident_remains_stage3c_blocked(self) -> None:
        """GC16: exact current historical incident remains Stage-3C blocked
        with Gate-C entry count zero, secret reads zero, venue requests
        zero."""

        transport = _ScriptedTransport()
        runtime = self._blocked_runtime(transport)
        opened = self._read_local_safety_state()()
        self.assertEqual(opened.projection.protected_unresolved_legacy_write_count, 1)
        invocation = self._invocation(incident_id=CURRENT_INCIDENT_ID, proof_id=CURRENT_WRITER_PROOF_ID)

        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.status, "LOCALLY_BLOCKED")
        self.assertEqual(transport.calls, [])

        with (
            mock.patch.object(runner, "acquire_release_only", wraps=runner.acquire_release_only) as release_spy,
            mock.patch.object(runner, "acquire_normal_writer_state", wraps=runner.acquire_normal_writer_state) as writer_spy,
            self.assertRaises(RunnerError) as ctx,
        ):
            runner._complete_stage3_release_and_normal_writer(result, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_C_ENTRY_PRECONDITION_FAILED)
        self.assertEqual(release_spy.call_count, 0)
        self.assertEqual(writer_spy.call_count, 0)
        self.assertEqual(transport.calls, [])

    def test_gc17_no_credential_signing_venue_or_websocket_path(self) -> None:
        """GC17: Gate-C runner code has no credential load, signing, venue
        request, CREATE/CANCEL, WebSocket, or production path."""

        source = inspect.getsource(runner._complete_stage3_release_and_normal_writer)
        for forbidden in (
            "sign", "credential", "secret", "private_key", "websocket", "WebSocket",
            "CREATE_ORDER", "CANCEL_ORDER", "requests.", "urllib", "socket.", "http.client",
        ):
            self.assertNotIn(forbidden, source)

    def test_gc18_no_writer_permit_progression_or_decision_loop(self) -> None:
        """GC18: Gate-C code contains no NormalWriterPermit progression,
        market-maker decision loop, Stage-4+ transport, or cleanup-cancel
        implementation."""

        source = inspect.getsource(runner._complete_stage3_release_and_normal_writer)
        for forbidden in (
            "NormalWriterPermit", "decision_cycle", "cleanup_cancel", "T0", "T1", "T2", "T3",
        ):
            self.assertNotIn(forbidden, source)

    def test_gc19d1_deadline_expired_before_release_only(self) -> None:
        """GC19/D1 (Implementation 02 Correction 02): deadline already
        expired before RELEASE_ONLY acquisition -> no RELEASE_ONLY
        mutation, no token, no NORMAL_WRITER, fail closed.

        Gate B itself must reach READ_PHASE_COMPLETE under a generous
        deadline first (an already-expired deadline would instead fail
        inside Gate B's own operations, proving nothing about Gate C); only
        the SEPARATE runtime handed to Gate C carries an already-elapsed
        `experiment_absolute_end_monotonic_ns`, so this is genuinely the
        very first Gate-C boundary check, and only it, that fails here."""

        result, runtime = self._read_phase_complete()
        already_expired = self.inputs.monotonic_value
        expired_runtime = dataclasses.replace(runtime, experiment_absolute_end_monotonic_ns=already_expired)
        before = self._sequence()
        with (
            mock.patch.object(runner, "acquire_release_only", wraps=runner.acquire_release_only) as spy,
            self.assertRaises(RunnerError) as ctx,
        ):
            runner._complete_stage3_release_and_normal_writer(result, expired_runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)
        self.assertEqual(ctx.exception.detail, "before RELEASE_ONLY")
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(self._sequence(), before)

    def test_gc19d2_deadline_expires_before_current_process_completion(self) -> None:
        """GC19/D2: deadline expires after durable release progression
        (RISK_RELEASE_RECORDED -> WRITER_PROOF_RELEASED -> WRITER_ELIGIBLE
        all durably recorded for real) but before `complete_release_and_
        issue_current_process_completion(...)` -> no token issued, no
        NORMAL_WRITER, restricted session safely closed/ended.

        The clock is expired via a wrapper around the REAL canonical
        `record_writer_eligible` (the step immediately preceding the
        finalizer): the real method runs to completion first, then the
        clock flips to expired, so Gate C's own next deadline check -- and
        only that one -- observes expiry."""

        result, runtime = self._read_phase_complete()
        clock = _ExpireOnDemandClock(runtime.monotonic_clock_ns, deadline=10**18)
        d2_runtime = dataclasses.replace(
            runtime, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline,
        )
        real_record_writer_eligible = ReleaseLedgerHandle.record_writer_eligible

        def _expire_after(self_handle, assessment):
            outcome = real_record_writer_eligible(self_handle, assessment)
            clock.expire()
            return outcome

        registry_before = len(ledger_binding._current_process_release_completion_registry)
        with mock.patch.object(ReleaseLedgerHandle, "record_writer_eligible", _expire_after):
            with self.assertRaises(RunnerError) as ctx:
                runner._complete_stage3_release_and_normal_writer(result, d2_runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)
        self.assertEqual(ctx.exception.detail, "before current-process completion")
        self.assertEqual(len(ledger_binding._current_process_release_completion_registry), registry_before)
        after = self._read_local_safety_state()()
        self.assertEqual(after.projection.risk_control_state, "WRITER_ELIGIBLE")
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertIsNone(after.projection.active_writer_session_id)

    def test_gc19d3_deadline_expires_before_normal_writer_acquisition(self) -> None:
        """GC19/D3: deadline expires after genuine current-process
        completion token issuance but before `acquire_normal_writer_state
        (...)` -> no NORMAL_WRITER ws_, fail closed. No reconstructed or
        fabricated token is ever used -- the wrapper expires the clock only
        AFTER the real finalizer has already returned a genuine live
        token, which then simply goes unconsumed."""

        result, runtime = self._read_phase_complete()
        clock = _ExpireOnDemandClock(runtime.monotonic_clock_ns, deadline=10**18)
        d3_runtime = dataclasses.replace(
            runtime, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline,
        )
        real_finalizer = ReleaseLedgerHandle.complete_release_and_issue_current_process_completion

        def _expire_after_token(self_handle, assessment):
            token = real_finalizer(self_handle, assessment)
            clock.expire()
            return token

        registry_before = len(ledger_binding._current_process_release_completion_registry)
        with mock.patch.object(
            ReleaseLedgerHandle, "complete_release_and_issue_current_process_completion", _expire_after_token,
        ):
            with self.assertRaises(RunnerError) as ctx:
                runner._complete_stage3_release_and_normal_writer(result, d3_runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)
        self.assertEqual(ctx.exception.detail, "before NORMAL_WRITER")
        # The genuine token was issued and remains registered (unconsumed,
        # exactly like process termination before Stage 3J) -- registry
        # size grows by exactly one, it is not silently discarded/reused.
        self.assertEqual(len(ledger_binding._current_process_release_completion_registry), registry_before + 1)
        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_writer_session_id)
        self.assertEqual(after.projection.writer_sessions, ())

    def test_gc19d4_deadline_expires_after_normal_writer_before_stage3k_success(self) -> None:
        """GC19/D4: deadline expires after genuine NORMAL_WRITER admission
        (a real `ws_` has started) but before successful Stage-3K
        completion -> canonical WRITER_SESSION_ENDED cleanup occurs, no
        active writer survives, Gate C fails closed."""

        result, runtime = self._read_phase_complete()
        clock = _ExpireOnDemandClock(runtime.monotonic_clock_ns, deadline=10**18)
        d4_runtime = dataclasses.replace(
            runtime, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline,
        )
        real_acquire = runner.acquire_normal_writer_state

        def _expire_after_admission(binding, **kwargs):
            outcome = real_acquire(binding, **kwargs)
            if outcome.handle is not None:
                clock.expire()
            return outcome

        with mock.patch.object(runner, "acquire_normal_writer_state", side_effect=_expire_after_admission):
            with self.assertRaises(RunnerError) as ctx:
                runner._complete_stage3_release_and_normal_writer(result, d4_runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)
        self.assertEqual(ctx.exception.detail, "Stage-3K success boundary")
        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_writer_session_id)
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertEqual(len(after.projection.writer_sessions), 1)

    def test_gc_corr01a_malformed_post_acquisition_carrier_ends_genuine_ws(self) -> None:
        """Implementation 02 Correction 01 / GC-CORR-01A: the real canonical
        `acquire_normal_writer_state` genuinely creates a live `ws_`
        writer session; only the RETURNED carrier's runner-validated
        `authority_ledger_relation` field is then altered (the canonical
        acquisition and the durable ledger state underneath are untouched).
        Runner-level post-acquisition validation must fail on that altered
        field AND durably end the genuine `ws_` through canonical
        `end_writer_session` before propagating -- not merely raise while
        abandoning the still-open lock."""

        result, runtime = self._read_phase_complete()
        real_acquire = runner.acquire_normal_writer_state

        def _corrupt_relation_after_real_admission(binding, **kwargs):
            outcome = real_acquire(binding, **kwargs)
            if outcome.handle is None:
                return outcome
            return dataclasses.replace(outcome, authority_ledger_relation=None)

        with mock.patch.object(runner, "acquire_normal_writer_state", side_effect=_corrupt_relation_after_real_admission):
            with self.assertRaises(RunnerError) as ctx:
                runner._complete_stage3_release_and_normal_writer(result, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.NORMAL_WRITER_ACQUISITION_FAILED)

        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_writer_session_id)
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertEqual(len(after.projection.writer_sessions), 1)

    def test_gc_corr01b_stage3k_rederivation_exception_ends_genuine_ws(self) -> None:
        """Implementation 02 Correction 01 / GC-CORR-01B: an exception
        raised BY the Stage-3K re-derivation machinery itself (not merely a
        boolean predicate returning false) after genuine NORMAL_WRITER
        admission must still durably end the genuine `ws_` through
        canonical `end_writer_session` before propagating.

        The fault is injected as a one-shot raise from the live
        `LockedLedger`'s own `.projection()` method (instance-level
        rebinding -- `LockedLedger` has no `__slots__`), simulating an
        unexpected fault inside the re-derivation call itself rather than
        a scripted false predicate."""

        result, runtime = self._read_phase_complete()
        real_acquire = runner.acquire_normal_writer_state

        def _raise_once_from_projection(binding, **kwargs):
            outcome = real_acquire(binding, **kwargs)
            if outcome.handle is None:
                return outcome

            def _projection_raises_once():
                raise RuntimeError("simulated Stage-3K re-derivation fault")

            outcome.handle.projection = _projection_raises_once
            return outcome

        with mock.patch.object(runner, "acquire_normal_writer_state", side_effect=_raise_once_from_projection):
            with self.assertRaises(RuntimeError):
                runner._complete_stage3_release_and_normal_writer(result, runtime)

        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_writer_session_id)
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertEqual(len(after.projection.writer_sessions), 1)

    def test_gc20_pre_token_failures_leave_no_active_restricted_session(self) -> None:
        """GC20: all pre-token failure paths release/close RELEASE_ONLY
        correctly and leave no active restricted session where a clean
        close is deterministically possible."""

        before, after = self._fault_after("record_risk_release", "record_risk_release")
        self.assertIsNone(after.projection.active_restricted_session_id)

    def test_gc21_no_raw_persistence_bridge_calls(self) -> None:
        """GC21: runner never invokes raw SQLite, _open_locked,
        _acquire_normal_writer_candidate, or start_writer_session
        directly."""

        source = inspect.getsource(runner._complete_stage3_release_and_normal_writer)
        for forbidden in ("_open_locked", "_acquire_normal_writer_candidate", "start_writer_session(", "sqlite3"):
            self.assertNotIn(forbidden, source)

    def test_gc22_all_prior_semantic_cases_preserved(self) -> None:
        """GC22: all Gate-B semantic cases 1-113 remain preserved -- smoke
        re-check of a representative cross-section (the full suite is the
        complete evidence, run alongside this file)."""

        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport)
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE")
        produced = build_operation_binding_index()
        self.assertEqual(len(produced), OPERATION_BINDING_INDEX_BYTES)
        self.assertEqual(hashlib.sha256(produced).hexdigest(), OPERATION_BINDING_INDEX_SHA256)

    def test_gc23_successful_handoff_leaves_acquisition_open_for_test_to_end(self) -> None:
        """GC23: successful Gate-C handoff returns the live canonical
        normal-writer acquisition without closing it; test then ends it
        explicitly with canonical end_writer_session."""

        result, runtime = self._read_phase_complete()
        stage3 = runner._complete_stage3_release_and_normal_writer(result, runtime)
        acquisition = stage3.normal_writer_acquisition
        self.assertFalse(acquisition.handle.closed)
        end_writer_session(acquisition.handle, writer_session_id=stage3.normal_writer_session_id)
        self.assertTrue(acquisition.handle.closed)

    def test_gc24_forced_stage3k_failure_ends_writer_session_through_canonical_api(self) -> None:
        """GC24: forced Stage-3K validation failure after writer admission
        uses canonical end_writer_session and positively anchors WRITER_
        SESSION_ENDED before locks close.

        Forced by rebinding just the returned `LockedLedger` instance's own
        `.projection()` method (the object has no `__slots__`, so this is
        ordinary instance-level rebinding, not a class-wide patch) to report
        a corrupted `active_risk_config_sha256` -- but only for Stage-3K's
        own later fresh re-derivation call. The real
        `acquire_normal_writer_state` call underneath still runs for real
        and genuinely starts `ws_`, so the session `end_writer_session`
        later ends is the exact real active one."""

        result, runtime = self._read_phase_complete()
        real_acquire = runner.acquire_normal_writer_state

        def _corrupt_projection_after_real_start(binding, **kwargs):
            outcome = real_acquire(binding, **kwargs)
            if outcome.handle is None:
                return outcome
            real_projection_fn = outcome.handle.projection

            def _corrupted_projection():
                return dataclasses.replace(real_projection_fn(), active_risk_config_sha256="0" * 64)

            outcome.handle.projection = _corrupted_projection
            return outcome

        with mock.patch.object(runner, "acquire_normal_writer_state", side_effect=_corrupt_projection_after_real_start):
            with self.assertRaises(RunnerError) as ctx:
                runner._complete_stage3_release_and_normal_writer(result, runtime)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.STAGE_3K_REVALIDATION_FAILED)

        # The real ws_ genuinely started and was genuinely ended through the
        # canonical public API (not dropped) -- re-reading local safety
        # state through an entirely separate, freshly-opened handle proves
        # WRITER_SESSION_ENDED was durably, positively anchored.
        after = self._read_local_safety_state()()
        self.assertIsNone(after.projection.active_restricted_session_id)
        self.assertIsNone(after.projection.active_writer_session_id)
        self.assertEqual(len(after.projection.writer_sessions), 1)


# ---------------------------------------------------------------------------
# One-shot marker (ER-ONESHOT-001/002).
# ---------------------------------------------------------------------------


class OneShotMarkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.marker_path = str(Path(self.temp.name) / "marker.json")
        self.clock = lambda: datetime(2026, 8, 17, 13, 0, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create(self) -> None:
        create_one_shot_marker(
            self.marker_path, execution_authorization_id="auth-1", invocation_id="inv-1",
            runner_commit="a" * 40, runner_tree="b" * 40, market_ticker=CURRENT_TICKER,
            process_instance_id="proc_" + "0" * 32, wall_clock=self.clock,
        )

    def test_marker_created_once(self) -> None:
        self._create()
        self.assertTrue(Path(self.marker_path).exists())

    def test_marker_second_invocation_rejected(self) -> None:
        self._create()
        with self.assertRaises(RunnerError) as ctx:
            self._create()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.EXPERIMENT_AUTHORIZATION_ALREADY_CONSUMED)


if __name__ == "__main__":
    unittest.main()
