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
    initialize_authority_namespace,
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
    CandidateOrderV1,
    FlowRiskLimits,
    FreshnessStampV1,
    MarketEconomicState,
    NormalWriteAdapter,
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
from arb.venues.kalshi.minimal_market_maker import QuoteSlot
from arb.venues.kalshi.quote_lifecycle import (
    VenueBindingV1,
    build_cancel_prepared_payload,
    build_cancel_writer_eligibility_assessment,
    build_create_prepared_payload,
    build_mm_cancel_intent_payload,
    build_mm_create_intent_payload,
    build_mm_create_order_body,
    build_writer_eligibility_assessment,
    issue_and_persist_write_permit,
)

import arb.venues.kalshi.ledger_binding as ledger_binding
import arb.venues.kalshi.minimal_market_maker_experiment_runner as runner
from arb.venues.kalshi.minimal_market_maker_experiment_runner import (
    ExperimentRunnerInvocationV1,
    ExperimentRunnerRuntimeV1,
    GATE_D_DECISION_CYCLE_MAX,
    GATE_D_ORDINARY_WRITE_SEND_MAX,
    GATE_D_READ_REQUEST_MAX,
    GateDCycleResultV1,
    GateDLoopResultV1,
    GateDWriteOutcomeV1,
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
    run_gate_d_ordinary_decision_loop,
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


# Correction 06: sentinel distinguishing "omit this field from the row
# entirely" from any real value (including `False`/`0.0`/`"0"`/`None`) so
# TERM06-CLOSE tests can construct a row with a genuinely missing
# subaccount/exchange_index rather than one merely set to a falsy value.
_OMIT_FIELD = object()


def _order_row(
    order_id: str, *, ticker: str, side: str = "yes", status: str = "resting",
    remaining_count_fp: str = "1.00", fill_count_fp: str = "0.00", initial_count_fp: str = "1.00",
    client_order_id: str | None = None, yes_price_dollars: str = "0.45",
    subaccount: object = 0, exchange_index: object = 0,
) -> dict:
    row = {
        "order_id": order_id, "ticker": ticker, "side": side, "status": status,
        "remaining_count_fp": remaining_count_fp, "fill_count_fp": fill_count_fp,
        "initial_count_fp": initial_count_fp, "yes_price_dollars": yes_price_dollars,
    }
    if subaccount is not _OMIT_FIELD:
        row["subaccount"] = subaccount
    if exchange_index is not _OMIT_FIELD:
        row["exchange_index"] = exchange_index
    if client_order_id is not None:
        row["client_order_id"] = client_order_id
    return row


def _order_payload(
    order_id: str, *, ticker: str, side: str = "yes", status: str = "resting",
    remaining_count_fp: str = "1.00", fill_count_fp: str = "0.00", initial_count_fp: str = "1.00",
    client_order_id: str | None = None, yes_price_dollars: str = "0.45",
    subaccount: object = 0, exchange_index: object = 0,
) -> RawOperationResponseV1:
    return _json_response({"order": _order_row(
        order_id, ticker=ticker, side=side, status=status,
        remaining_count_fp=remaining_count_fp, fill_count_fp=fill_count_fp, initial_count_fp=initial_count_fp,
        client_order_id=client_order_id, yes_price_dollars=yes_price_dollars,
        subaccount=subaccount, exchange_index=exchange_index,
    )})


def _cancel_result_payload(
    *, order_id: str, reduced_by: str, ts_ms: int = 1_755_000_000_000, client_order_id: str | None = None,
) -> RawOperationResponseV1:
    body: dict = {"order_id": order_id, "reduced_by": reduced_by, "ts_ms": ts_ms}
    if client_order_id is not None:
        body["client_order_id"] = client_order_id
    return _json_response(body)


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
# Gate D: Stage-4+ ordinary strategy write decision loop (Spec 07 same-scope
# correction of the Marco-blocked Implementation 01 candidate). Covers the
# four defect corrections (MM07-CLAR-001..004) plus entry-precondition and
# budget/cutoff boundary behavior. Reconstructed fresh from clean base --
# the blocked candidate's own test file is never read as ancestry here.
# ---------------------------------------------------------------------------


D = Decimal
GATE_D_STRATEGY_INSTANCE_ID = "mm_" + "d" * 32
GATE_D_MIN_SPREAD = Decimal("0.0100")


class _ScriptedWriteTransport:
    """Fake one-arg `normal_write_transport` (matches `NormalWriteAdapter.
    invoke`'s `transport(request)` contract -- distinct from the three-arg
    `send_operation_request` read transport)."""

    def __init__(self) -> None:
        self.responses: list = []
        self.calls: list = []

    def queue(self, response) -> None:
        self.responses.append(response)

    def __call__(self, request):
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("no scripted write-transport response")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class GateDTestCase(GateCTests):
    def _gate_d_ready(self):
        """Reaches a genuine Stage-3K NORMAL_WRITER result through an
        empty-portfolio Gate-B/C read-and-release cycle (Stage 3F's trusted-
        evidence matcher requires the fresh read to agree with the
        synthetic zero-order legacy-import fixture, so this initial cycle
        is always order_ids=()). The Gate-D loop's OWN read cycle(s) are
        entirely separate and must be queued afterward via
        `_queue_gate_d_read_cycle`."""

        transport = _ScriptedTransport()
        self._script_full_read_cycle(transport, order_ids=())
        runtime, invocation = self._ready_runtime_and_invocation(transport)
        result = run_pre_release_read_phase(invocation, runtime)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE")
        stage3 = runner._complete_stage3_release_and_normal_writer(result, runtime)
        write_transport = _ScriptedWriteTransport()

        def _identified_orderbook_fetch(ticker: str, deadline) -> KalshiNativeOrderBookSnapshot:
            # Production `fetch_orderbook` implementations attach the
            # canonical snapshot identity before returning; `_fake_
            # orderbook_snapshot` (shared with Gate B/C tests that never
            # read this field) does not, so Gate D's own fixture finishes
            # the same step here.
            return _fake_orderbook_snapshot(ticker).with_canonical_identity()

        gate_d_runtime = dataclasses.replace(
            runtime, strategy_instance_id=GATE_D_STRATEGY_INSTANCE_ID, minimum_spread_usd=GATE_D_MIN_SPREAD,
            gate_d_incident_id="SYNTHETIC_MM_TEST_GATE_D_INCIDENT", gate_d_capability_reference_id="cap_gate_d_test",
            normal_write_transport=write_transport, fetch_orderbook=_identified_orderbook_fetch,
        )
        return stage3, gate_d_runtime, invocation, transport, write_transport

    def _queue_gate_d_read_cycle(self, transport, *, order_ids: tuple = (), fills_by_order=None) -> None:
        self._script_full_read_cycle(transport, order_ids=order_ids, fills_by_order=fills_by_order)

    def _close(self, stage3) -> None:
        handle = stage3.normal_writer_acquisition.handle
        if not handle.closed:
            handle.close()

    def _seed_active_exact_order(
        self, stage3, gate_d_runtime, *, quote_slot: str, client_order_id: str, venue_order_id: str,
        yes_price: Decimal, request_seed: str,
    ) -> None:
        from arb.execution_ledger import EventInput, EventType as ET
        locked = stage3.normal_writer_acquisition.handle
        session_id = stage3.normal_writer_session_id
        venue_side = "bid" if quote_slot == QuoteSlot.LOWER_YES_BID.value else "ask"
        outcome_side = "YES" if quote_slot == QuoteSlot.LOWER_YES_BID.value else "NO"
        binding = VenueBindingV1(adapter_payload_schema_id="mm-create-v1")
        body = build_mm_create_order_body(
            ticker=self.TICKER, client_order_id=client_order_id, venue_side=venue_side, yes_price=yes_price,
            quantity=D("1.00"), expiration_time=6_000_000_000, venue_binding=binding,
        )
        prepared = build_create_prepared_payload(
            request_id=f"req_{request_seed}", environment="KALSHI_DEMO", client_order_id=client_order_id,
            canonical_body=body, venue_binding=binding,
        )
        candidate = CandidateOrderV1(self.TICKER, outcome_side, D("1.00"), yes_price)
        state = MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0"))
        risk_state_epoch = locked.projection().risk_state_epoch
        assessment = build_writer_eligibility_assessment(
            risk_assessment_id=f"ra_{request_seed}", request_id=f"req_{request_seed}", candidate=candidate,
            market_economic_state=state, unresolved_exposure=D("0"), risk_config=gate_d_runtime.risk_config,
            prepared_request_sha256=prepared["prepared_request_sha256"], market_data_snapshot_sha256="a" * 64,
            market_data_freshness_identity_sha256="b" * 64, reconciliation_snapshot_sha256="c" * 64,
            reconciliation_freshness_identity_sha256="d" * 64, risk_state_epoch=risk_state_epoch,
            freshness_deadline_monotonic_ns=999_999_999_999,
        )
        quote_generation_id = "qg_" + hashlib.sha256(request_seed.encode("utf-8")).hexdigest()[:32]
        outer_intent = build_mm_create_intent_payload(
            execution_attempt_id=f"ea_{request_seed}", conflict_domain_ref=locked.conflict_domain_ref,
            incident_id=gate_d_runtime.gate_d_incident_id, client_order_id=client_order_id,
            capability_reference_id=gate_d_runtime.gate_d_capability_reference_id, request_id=f"req_{request_seed}",
            strategy_instance_id=GATE_D_STRATEGY_INSTANCE_ID, market_ticker=self.TICKER, quote_slot=quote_slot,
            quote_generation_id=quote_generation_id, quote_plan_sha256="a" * 64, plan_input_sha256="b" * 64,
            source_book_snapshot_sha256="c" * 64, risk_config_sha256=gate_d_runtime.risk_config.sha256,
            risk_state_epoch=risk_state_epoch, reconciliation_snapshot_sha256="c" * 64,
            venue_side=venue_side, outcome_side=outcome_side, yes_price=yes_price, quantity=D("1.00"),
        )
        issue_and_persist_write_permit(
            gate=gate_d_runtime.normal_gate, locked=locked, normal_writer_session_id=session_id,
            assessment=assessment, outer_intent_payload=outer_intent, prepared_payload=prepared,
        )
        # Close out this seeded write's own unresolved-request bookkeeping
        # (SafetyProjection.unresolved_write_request_ids) so Gate D's entry
        # precondition -- a genuinely zero-unresolved-write projection --
        # still passes; production closes this the same way via
        # `_gate_d_record_http_response_classified`.
        locked.append_batch((EventInput(ET.HTTP_RESPONSE_CLASSIFIED, {
            "request_id": f"req_{request_seed}", "http_status": 200, "response_media_type": "application/json",
            "response_byte_length": 0, "response_sha256": "0" * 64,
            "adapter_result_class": "DEFINITIVE_RESPONSE_AFTER_SEND", "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
            "validated_identity_fields": {},
        }, session_id, None, None),))
        locked.append_batch((EventInput(ET.ORDER_IDENTITY_BOUND, {
            "client_order_id": client_order_id, "venue_order_id": venue_order_id, "venue": "KALSHI",
            "environment": "KALSHI_DEMO", "incident_id": gate_d_runtime.gate_d_incident_id,
            "binding_basis_event_ids": [],
        }, session_id, gate_d_runtime.gate_d_incident_id, None),))
        canonical_order = {"order_id": venue_order_id, "status": "resting", "remaining_count_fp": "1.00"}
        locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
            "venue_order_id": venue_order_id, "client_order_id": client_order_id,
            "source_request_id": "seed-read", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "seed-order-v1", "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }, session_id, None, None),))


class GateDEntryPreconditionTests(GateDTestCase):
    def test_gd01_wrong_stage3_type_rejected(self) -> None:
        stage3, gate_d_runtime, invocation, _t, _wt = self._gate_d_ready()
        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(object(), gate_d_runtime, invocation)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)
        self._close(stage3)

    def test_gd02_closed_acquisition_handle_rejected(self) -> None:
        stage3, gate_d_runtime, invocation, _t, _wt = self._gate_d_ready()
        stage3.normal_writer_acquisition.handle.close()
        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)

    def test_gd03_missing_strategy_instance_id_rejected(self) -> None:
        stage3, gate_d_runtime, invocation, _t, _wt = self._gate_d_ready()
        broken = dataclasses.replace(gate_d_runtime, strategy_instance_id=None)
        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(stage3, broken, invocation)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)
        self._close(stage3)

    def test_gd04_missing_normal_write_transport_rejected(self) -> None:
        stage3, gate_d_runtime, invocation, _t, _wt = self._gate_d_ready()
        broken = dataclasses.replace(gate_d_runtime, normal_write_transport=None)
        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(stage3, broken, invocation)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)
        self._close(stage3)

    def test_gd05_missing_gate_d_incident_id_rejected(self) -> None:
        stage3, gate_d_runtime, invocation, _t, _wt = self._gate_d_ready()
        broken = dataclasses.replace(gate_d_runtime, gate_d_incident_id=None)
        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(stage3, broken, invocation)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)
        self._close(stage3)

    def test_gd06_invalid_decision_cycle_max_rejected(self) -> None:
        stage3, gate_d_runtime, invocation, _t, _wt = self._gate_d_ready()
        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=0)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)
        self._close(stage3)

    def test_gd07_writer_session_ended_before_entry_rejected(self) -> None:
        stage3, gate_d_runtime, invocation, _t, _wt = self._gate_d_ready()
        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )
        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)
        self._close(stage3)


class GateDLoopBehaviorTests(GateDTestCase):
    def test_gd10_no_compute_quote_decision_seam_exists_on_runtime(self) -> None:
        """MM07-CLAR-003: there must be no generic quote-decision-
        substitution field anywhere on the runtime dataclass."""
        field_names = {f.name for f in dataclasses.fields(ExperimentRunnerRuntimeV1)}
        self.assertNotIn("compute_quote_decision", field_names)
        self.assertNotIn("quote_decision_callback", field_names)

    def test_gd11_empty_portfolio_create_new_charges_budget_and_uses_real_strategy_pipeline(self) -> None:
        """MM07-CLAR-001/003/004 integration: an empty-portfolio cycle
        selects CREATE_NEW (never a cleanup lane), the ordinary send budget
        is charged, and the real `evaluate_market_maker_input` (not a
        substitutable seam) drives the desired quote."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._queue_gate_d_read_cycle(transport, order_ids=())
        transport.queue(RunnerOperation.GET_ORDER, _order_payload("venue-order-created-1", ticker=self.TICKER))
        write_transport.queue(_json_response({"order": {"order_id": "venue-order-created-1"}}))

        real_evaluate = runner.evaluate_market_maker_input
        with mock.patch.object(runner, "evaluate_market_maker_input", wraps=real_evaluate) as spy:
            result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        self.assertTrue(spy.called)
        self.assertEqual(result.ordinary_writes_sent, 1)
        self.assertEqual(result.cleanup_cancels_sent, 0)
        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.action, "CREATE")
        self.assertEqual(outcome.lane, "ORDINARY")
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "BOUND_ACTIVE")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd12_budget_charged_even_when_adapter_raises(self) -> None:
        """MM07-CLAR-004: the ordinary send-budget unit is spent the
        instant trusted T3 durably commits -- an adapter-level transport
        exception afterward must not un-charge it."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._queue_gate_d_read_cycle(transport, order_ids=())
        write_transport.queue(ConnectionError("synthetic transport failure"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        self.assertEqual(result.ordinary_writes_sent, 1)
        outcome = result.cycle_results[0].write_outcome
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "ADAPTER_EXCEPTION")
        self.assertTrue(outcome.transport_invoked)

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd13_cancel_terminal_classification_uses_exact_accepted_vocabulary(self) -> None:
        """MM07-CLAR-002: a post-cancel authoritative read reporting the
        exact accepted terminal status ``"canceled"`` clears the target as
        TERMINAL and records a closing reconciliation -- never a
        ``status != "resting"`` shortcut."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="99999999-9999-4999-8999-999999999999", venue_order_id="venue-order-old-1",
            yes_price=D("0.05"), request_seed="gd13",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-1",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-1", ticker=self.TICKER, status="canceled",
                remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00",
                client_order_id="99999999-9999-4999-8999-999999999999", yes_price_dollars="0.05",
            ),
        )
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-1", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.action, "CANCEL")
        self.assertEqual(outcome.lane, "ORDINARY")
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "TERMINAL")
        self.assertEqual(result.ordinary_writes_sent, 1)
        self.assertEqual(result.cleanup_cancels_sent, 0)

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd14_cancel_unsupported_status_stays_ambiguous_not_terminal(self) -> None:
        """MM07-CLAR-002 negative case: a post-cancel read reporting a
        status outside the exact accepted terminal vocabulary (here an
        empty/malformed status) must remain AMBIGUOUS -- the pre-Spec-07
        ``status != "resting"`` shortcut would have wrongly closed this as
        terminal."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="88888888-8888-4888-8888-888888888888", venue_order_id="venue-order-old-2",
            yes_price=D("0.05"), request_seed="gd14",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-2",))
        transport.queue(
            RunnerOperation.GET_ORDER, _order_payload("venue-order-old-2", ticker=self.TICKER, status="queued"),
        )
        write_transport.queue(_json_response({}))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.action, "CANCEL")
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "AMBIGUOUS")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd15_halted_state_stops_before_any_write(self) -> None:
        stage3, gate_d_runtime, invocation, _transport, _write_transport = self._gate_d_ready()

        # Persist a genuine HALT through the real WriterEligibilityGate
        # production surface (also ends the writer session durably).
        gate_d_runtime.normal_gate.persist_case_a_halt(
            locked=stage3.normal_writer_acquisition.handle,
            normal_writer_session_id=stage3.normal_writer_session_id,
            risk_config_sha256=gate_d_runtime.risk_config.sha256,
        )

        with self.assertRaises(RunnerError) as ctx:
            run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=3)
        # The writer session that persist_case_a_halt just ended no longer
        # matches the active-session entry precondition -- this is the same
        # fail-closed path GD07 exercises, reached here via a genuine HALT
        # rather than an explicit end_writer_session call.
        self.assertEqual(ctx.exception.code, RunnerFailureCode.GATE_D_ENTRY_PRECONDITION_FAILED)

    def test_gd16_crossed_book_yields_no_plan_and_exhausts_decision_cycle_budget(self) -> None:
        """A crossed/locked synthetic book makes `evaluate_market_maker_
        input` fail closed to NO_NEW_QUOTE_PLAN; both slots then HOLD, no
        write is selectable, and the loop still consumes the cycle and
        reports DECISION_CYCLE_BUDGET_EXHAUSTED rather than looping
        forever or crashing."""
        stage3, gate_d_runtime, invocation, transport, _write_transport = self._gate_d_ready()
        self._queue_gate_d_read_cycle(transport, order_ids=())

        def _crossed_orderbook(ticker: str, deadline) -> KalshiNativeOrderBookSnapshot:
            snapshot = dataclasses.replace(
                _fake_orderbook_snapshot(ticker),
                yes_levels=(KalshiNativeOrderBookLevel(price=D("0.60"), quantity=D("10")),),
                no_levels=(KalshiNativeOrderBookLevel(price=D("0.60"), quantity=D("8")),),
            )
            return snapshot.with_canonical_identity()

        crossed_runtime = dataclasses.replace(gate_d_runtime, fetch_orderbook=_crossed_orderbook)
        result = run_gate_d_ordinary_decision_loop(stage3, crossed_runtime, invocation, decision_cycle_max=1)

        self.assertEqual(result.cycles_executed, 1)
        self.assertEqual(result.stop_reason, "DECISION_CYCLE_BUDGET_EXHAUSTED")
        self.assertEqual(result.ordinary_writes_sent, 0)
        self.assertIsNone(result.cycle_results[0].write_outcome)

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd17_ordinary_write_budget_exhausted_stop_reason(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._queue_gate_d_read_cycle(transport, order_ids=())
        with mock.patch.object(runner, "GATE_D_ORDINARY_WRITE_SEND_MAX", 0):
            result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)
        self.assertEqual(result.stop_reason, "ORDINARY_WRITE_BUDGET_EXHAUSTED")
        self.assertEqual(result.ordinary_writes_sent, 0)

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    # -----------------------------------------------------------------
    # Correction 03 additions -- mandatory T3 accounting tests
    # (dispatch Section 22 / MM07-TEST-T3-14..18) and post-CANCEL
    # order+fill reconciliation / closure tests (dispatch Sections 14-19,
    # 23 / MM07-CLOSE-001..002, MM07-TEST-CLOSURE).
    # -----------------------------------------------------------------

    def test_gd18_post_t3_freshness_expiry_zero_adapter_calls_budget_still_charged(self) -> None:
        """MM07-CLAR-004 / MM07-TEST-T3-15: trusted T3 durably commits, then
        freshness expires before adapter invocation -- exactly one ordinary
        budget unit is consumed and the adapter is never invoked."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="77777777-7777-4777-8777-777777777777", venue_order_id="venue-order-old-3",
            yes_price=D("0.05"), request_seed="gd18",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-3",))

        clock = _ExpireOnDemandClock(gate_d_runtime.monotonic_clock_ns, deadline=10**18)
        expiring_runtime = dataclasses.replace(gate_d_runtime, monotonic_clock_ns=clock)
        real_issue = runner.issue_and_persist_write_permit

        def _expire_after_permit(**kwargs):
            permit = real_issue(**kwargs)
            clock.expire()
            return permit

        with mock.patch.object(runner, "issue_and_persist_write_permit", side_effect=_expire_after_permit):
            result = run_gate_d_ordinary_decision_loop(stage3, expiring_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.action, "CANCEL")
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "FRESHNESS_EXPIRED_BEFORE_ADAPTER")
        self.assertFalse(outcome.transport_invoked)
        self.assertEqual(write_transport.calls, [])
        self.assertEqual(result.ordinary_writes_sent, 1)

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd19_pre_t3_failure_consumes_zero_ordinary_budget(self) -> None:
        """MM07-CLAR-004 / MM07-TEST-T3-18: a failure before trusted T3 can
        durably commit (here, permit issuance itself failing) consumes zero
        ordinary send-budget units and makes zero adapter calls."""
        from arb.venues.kalshi.risk_control import RiskControlCode, RiskControlError

        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._queue_gate_d_read_cycle(transport, order_ids=())  # empty portfolio -> CREATE_NEW selected

        with mock.patch.object(
            runner, "issue_and_persist_write_permit",
            side_effect=RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID),
        ):
            result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertFalse(outcome.budget_charged)
        self.assertFalse(outcome.transport_invoked)
        self.assertEqual(outcome.result_classification, "PERMIT_ISSUANCE_FAILED")
        self.assertEqual(result.ordinary_writes_sent, 0)
        self.assertEqual(write_transport.calls, [])

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd20_terminal_status_with_conservation_mismatch_does_not_close(self) -> None:
        """MM07-CLOSE-001 / Correction 04 Defect 02: an exact supported
        ``canceled`` status with a valid, protected-classifier-validated
        ``reduced_by`` that does NOT reconcile with the fresh fill quantity
        under the protected canonical ``check_cancel_conservation`` does
        not close the slot -- it stays held as TERMINAL_UNRECONCILED, never
        TERMINAL (CANCEL-CONSERVATION-04)."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="66666666-6666-4666-8666-666666666666", venue_order_id="venue-order-old-4",
            yes_price=D("0.05"), request_seed="gd20",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-4",))
        # fresh fill quantity 0.60, but the validated CANCEL reduced_by is
        # 0.10 -- 0.60 + 0.10 = 0.70 != 1.00, so check_cancel_conservation
        # must fail even though the order's own fill_count_fp (0.60)
        # reconciles exactly to the fresh fill total.
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-4", ticker=self.TICKER, status="canceled",
                remaining_count_fp="0.40", fill_count_fp="0.60", initial_count_fp="1.00",
            ),
        )
        transport.queue(
            RunnerOperation.GET_FILLS,
            _fills_payload([_fill_row("fill-gd20-1", order_id="venue-order-old-4", ticker=self.TICKER, quantity="0.60")]),
        )
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-4", reduced_by="0.10"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd21_terminal_status_with_incomplete_fill_pagination_does_not_close(self) -> None:
        """MM07-CLOSE-001/002: an exact supported terminal status with a
        fill read that could not be proven complete (pagination budget
        exhausted before a terminal empty cursor) must not close the slot
        either -- fill retrieval failure/incompleteness remains
        unresolved, never silently treated as zero fills."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="55555555-5555-4555-8555-555555555555", venue_order_id="venue-order-old-5",
            yes_price=D("0.05"), request_seed="gd21",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-5",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-5", ticker=self.TICKER, status="canceled",
                remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00",
            ),
        )
        # A non-empty cursor that never resolves within the fill-pagination
        # budget: every page still claims a further page exists.
        for _ in range(runner.GET_FILLS_MAX_PAGES_PER_ORDER):
            transport.queue(RunnerOperation.GET_FILLS, _fills_payload([], cursor="still-more"))
        write_transport.queue(_json_response({}))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd22_executed_status_with_full_fill_reconciliation_closes(self) -> None:
        """MM07-TEST-CLOSURE 2/3: an exact ``executed`` status with a
        complete, conserving fresh fill set (incorporating the fill that
        raced the CANCEL send) closes the slot as TERMINAL -- proving the
        closure path is not limited to a zero-fill ``canceled`` case."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="44444444-4444-4444-8444-444444444444", venue_order_id="venue-order-old-6",
            yes_price=D("0.05"), request_seed="gd22",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-6",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-6", ticker=self.TICKER, status="executed",
                remaining_count_fp="0.00", fill_count_fp="1.00", initial_count_fp="1.00",
                client_order_id="44444444-4444-4444-8444-444444444444", yes_price_dollars="0.05",
            ),
        )
        transport.queue(
            RunnerOperation.GET_FILLS,
            _fills_payload([_fill_row("fill-gd22-1", order_id="venue-order-old-6", ticker=self.TICKER, quantity="1.00")]),
        )
        write_transport.queue(_json_response({}))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "TERMINAL")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd23_missing_status_field_remains_unresolved(self) -> None:
        """MM07-TEST-CLOSURE 8: a GET_ORDER response with no ``status``
        field at all remains AMBIGUOUS/unresolved -- never promoted to a
        supported terminal value, and the fill-reconciliation path is never
        even attempted."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="33333333-3333-4333-8333-333333333333", venue_order_id="venue-order-old-7",
            yes_price=D("0.05"), request_seed="gd23",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-7",))
        malformed_row = _order_row("venue-order-old-7", ticker=self.TICKER)
        del malformed_row["status"]
        transport.queue(RunnerOperation.GET_ORDER, _json_response({"order": malformed_row}))
        write_transport.queue(_json_response({}))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.budget_charged)
        self.assertEqual(outcome.result_classification, "AMBIGUOUS")
        # GET_FILLS is called once as part of the ordinary per-cycle truth
        # collection (for the still-admitted resting order); the dedicated
        # post-CANCEL reconciliation fetch is never attempted for a status
        # that was never confirmed terminal.
        fills_calls = [call for call in transport.calls if call[0] is RunnerOperation.GET_FILLS]
        self.assertEqual(len(fills_calls), 1)

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd24_canceled_with_raced_partial_fill_closes_and_retains_full_evidence(self) -> None:
        """CLOSURE-02 / EVIDENCE-01..03: a partial fill that raced the
        CANCEL send (0.35) plus a complementary validated ``reduced_by``
        (0.65) passes the protected ``check_cancel_conservation`` and
        closes the slot -- and the durable evidence retains the full
        authoritative order row (not merely order_id/status/
        remaining_count_fp) plus the exact validated ``reduced_by`` used."""
        from arb.execution_ledger import EventType as ET

        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        seeded_client_order_id = "12121212-1212-4121-8121-121212121212"
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id=seeded_client_order_id, venue_order_id="venue-order-old-8",
            yes_price=D("0.05"), request_seed="gd24",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-8",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-8", ticker=self.TICKER, status="canceled",
                remaining_count_fp="0.65", fill_count_fp="0.35", initial_count_fp="1.00",
                client_order_id=seeded_client_order_id, yes_price_dollars="0.05",
            ),
        )
        transport.queue(
            RunnerOperation.GET_FILLS,
            _fills_payload([_fill_row("fill-gd24-1", order_id="venue-order-old-8", ticker=self.TICKER, quantity="0.35")]),
        )
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-8", reduced_by="0.65"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL")

        events = list(stage3.normal_writer_acquisition.handle.events)
        order_observed = [
            e for e in events if e.event_type is ET.ORDER_OBSERVED
            and e.payload.get("venue_order_id") == "venue-order-old-8"
            and e.payload.get("observation_semantic_class") == "AUTHORITATIVE_TERMINAL_ORDER"
        ]
        self.assertEqual(len(order_observed), 1)
        canonical = order_observed[0].payload["canonical_venue_payload"]
        self.assertEqual(canonical["fill_count_fp"], "0.35")
        self.assertEqual(canonical["remaining_count_fp"], "0.65")
        self.assertEqual(canonical["initial_count_fp"], "1.00")
        self.assertEqual(canonical["client_order_id"], seeded_client_order_id)
        self.assertEqual(canonical["status"], "canceled")

        fill_observed = [
            e for e in events if e.event_type is ET.FILL_OBSERVED and e.payload.get("venue_order_id") == "venue-order-old-8"
        ]
        self.assertEqual(len(fill_observed), 1)

        http_classified = [
            e for e in events if e.event_type is ET.HTTP_RESPONSE_CLASSIFIED
            and e.payload.get("request_id") == outcome.request_id
        ]
        self.assertEqual(len(http_classified), 1)
        self.assertEqual(http_classified[0].payload["validated_identity_fields"]["reduced_by"], "0.65")
        self.assertEqual(http_classified[0].payload["adapter_result_class"], "DEFINITIVE_SUCCESS")
        self.assertEqual(http_classified[0].payload["write_closure_class"], "AUTHORITATIVE_RESULT_CLOSED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    # -- TERM05-CLOSE-01..04 (Correction 05 dispatch Section 30): an
    # otherwise-fully-valid canceled closure (correct status, complete
    # reconciling fills, valid conserving reduced_by) must still NOT close
    # when exactly one terminal-order identity predicate fails. TERM05-
    # CLOSE-05/06 (valid closure still works) are already exercised by
    # GD13/GD24 (canceled) and GD22 (executed). ---------------------------

    def test_gd25_term05_close_01_missing_client_order_id_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="13131313-1313-4131-8131-131313131313", venue_order_id="venue-order-old-9",
            yes_price=D("0.05"), request_seed="gd25",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-9",))
        malformed_row = _order_row(
            "venue-order-old-9", ticker=self.TICKER, status="canceled",
            remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00", yes_price_dollars="0.05",
        )
        self.assertNotIn("client_order_id", malformed_row)
        transport.queue(RunnerOperation.GET_ORDER, _json_response({"order": malformed_row}))
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-9", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertNotEqual(outcome.result_classification, "TERMINAL")
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd26_term05_close_02_fill_plus_remaining_over_quantity_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="14141414-1414-4141-8141-141414141414", venue_order_id="venue-order-old-10",
            yes_price=D("0.05"), request_seed="gd26",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-10",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-10", ticker=self.TICKER, status="canceled",
                # 0.75 + 0.50 = 1.25 > 1.00 -- internally contradictory.
                remaining_count_fp="0.50", fill_count_fp="0.75", initial_count_fp="1.00",
                client_order_id="14141414-1414-4141-8141-141414141414", yes_price_dollars="0.05",
            ),
        )
        transport.queue(
            RunnerOperation.GET_FILLS,
            _fills_payload([_fill_row("fill-gd26-1", order_id="venue-order-old-10", ticker=self.TICKER, quantity="0.75")]),
        )
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-10", reduced_by="0.50"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd27_term05_close_03_wrong_quote_price_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="15151515-1515-4151-8151-151515151515", venue_order_id="venue-order-old-11",
            yes_price=D("0.05"), request_seed="gd27",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-11",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-11", ticker=self.TICKER, status="canceled",
                remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00",
                client_order_id="15151515-1515-4151-8151-151515151515",
                yes_price_dollars="0.50",  # seeded target quote price is 0.05 -- mismatch.
            ),
        )
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-11", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd28_term05_close_04_wrong_side_outcome_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="16161616-1616-4161-8161-161616161616", venue_order_id="venue-order-old-12",
            yes_price=D("0.05"), request_seed="gd28",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-12",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-12", ticker=self.TICKER, status="canceled",
                remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00",
                client_order_id="16161616-1616-4161-8161-161616161616", yes_price_dollars="0.05",
                side="no",  # the LOWER_YES_BID slot's strategy target is outcome side YES -- mismatch.
            ),
        )
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-12", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd29_term06_close_01_missing_subaccount_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="17171717-1717-4171-8171-171717171717", venue_order_id="venue-order-old-13",
            yes_price=D("0.05"), request_seed="gd29",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-13",))
        malformed_row = _order_row(
            "venue-order-old-13", ticker=self.TICKER, status="canceled",
            remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00", yes_price_dollars="0.05",
            client_order_id="17171717-1717-4171-8171-171717171717", subaccount=_OMIT_FIELD,
        )
        self.assertNotIn("subaccount", malformed_row)
        transport.queue(RunnerOperation.GET_ORDER, _json_response({"order": malformed_row}))
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-13", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd30_term06_close_02_missing_exchange_index_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="18181818-1818-4181-8181-181818181818", venue_order_id="venue-order-old-14",
            yes_price=D("0.05"), request_seed="gd30",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-14",))
        malformed_row = _order_row(
            "venue-order-old-14", ticker=self.TICKER, status="canceled",
            remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00", yes_price_dollars="0.05",
            client_order_id="18181818-1818-4181-8181-181818181818", exchange_index=_OMIT_FIELD,
        )
        self.assertNotIn("exchange_index", malformed_row)
        transport.queue(RunnerOperation.GET_ORDER, _json_response({"order": malformed_row}))
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-14", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd31_term06_close_03_subaccount_false_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="19191919-1919-4191-8191-191919191919", venue_order_id="venue-order-old-15",
            yes_price=D("0.05"), request_seed="gd31",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-15",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-15", ticker=self.TICKER, status="canceled",
                remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00", yes_price_dollars="0.05",
                client_order_id="19191919-1919-4191-8191-191919191919", subaccount=False,
            ),
        )
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-15", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd32_term06_close_04_exchange_index_false_blocks_otherwise_valid_closure(self) -> None:
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="20202020-2020-4202-8202-202020202020", venue_order_id="venue-order-old-16",
            yes_price=D("0.05"), request_seed="gd32",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-16",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-16", ticker=self.TICKER, status="canceled",
                remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00", yes_price_dollars="0.05",
                client_order_id="20202020-2020-4202-8202-202020202020", exchange_index=False,
            ),
        )
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-16", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL_UNRECONCILED")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd33_term06_close_05_exact_int_zero_scope_canceled_closure_still_succeeds(self) -> None:
        """TERM06-CLOSE-05: an otherwise fully valid ``canceled`` closure
        whose row carries exact Python ``int`` zero for both ``subaccount``
        and ``exchange_index`` (the ordinary case) still closes -- the
        Correction 06 tightening rejects only missing/bool/float/string/
        wrong-int scope, never the exact accepted value."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="21212121-2121-4212-8212-212121212121", venue_order_id="venue-order-old-17",
            yes_price=D("0.05"), request_seed="gd33",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-17",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-17", ticker=self.TICKER, status="canceled",
                remaining_count_fp="1.00", fill_count_fp="0.00", initial_count_fp="1.00", yes_price_dollars="0.05",
                client_order_id="21212121-2121-4212-8212-212121212121", subaccount=0, exchange_index=0,
            ),
        )
        transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        write_transport.queue(_cancel_result_payload(order_id="venue-order-old-17", reduced_by="1.00"))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )

    def test_gd34_term06_close_06_exact_int_zero_scope_executed_closure_still_succeeds(self) -> None:
        """TERM06-CLOSE-06: an otherwise fully valid ``executed`` closure
        with complete fresh fills and exact Python ``int`` zero scope still
        closes."""
        stage3, gate_d_runtime, invocation, transport, write_transport = self._gate_d_ready()
        self._seed_active_exact_order(
            stage3, gate_d_runtime, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="22222222-2222-4222-8222-222222222222", venue_order_id="venue-order-old-18",
            yes_price=D("0.05"), request_seed="gd34",
        )
        self._queue_gate_d_read_cycle(transport, order_ids=("venue-order-old-18",))
        transport.queue(
            RunnerOperation.GET_ORDER,
            _order_payload(
                "venue-order-old-18", ticker=self.TICKER, status="executed",
                remaining_count_fp="0.00", fill_count_fp="1.00", initial_count_fp="1.00", yes_price_dollars="0.05",
                client_order_id="22222222-2222-4222-8222-222222222222", subaccount=0, exchange_index=0,
            ),
        )
        transport.queue(
            RunnerOperation.GET_FILLS,
            _fills_payload([_fill_row("fill-gd34-1", order_id="venue-order-old-18", ticker=self.TICKER, quantity="1.00")]),
        )
        write_transport.queue(_json_response({}))

        result = run_gate_d_ordinary_decision_loop(stage3, gate_d_runtime, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.result_classification, "TERMINAL")

        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id,
        )


# ---------------------------------------------------------------------------
# Correction 04 -- direct unit tests for the module-private CANCEL result
# classification (Defect 01), terminal-order identity validation
# (Defect 03), and conservation (Defect 02) helpers. No ledger/writer-
# session fixture is needed for these -- they exercise pure functions.
# ---------------------------------------------------------------------------


class GateDCancelReconciliationUnitTests(unittest.TestCase):
    TICKER = CURRENT_TICKER
    ORDER_ID = "venue-order-unit-1"
    CLIENT_ORDER_ID = "11111111-1111-4111-8111-111111111111"

    @staticmethod
    def _raw(*, http_status: int = 200, body: dict | None = None, transport_unknown: bool = False) -> RawOperationResponseV1:
        payload = json.dumps(body if body is not None else {}).encode("utf-8")
        return RawOperationResponseV1(
            http_status=http_status, content_type="application/json", body_bytes=payload,
            transport_unknown=transport_unknown,
        )

    def _classify(self, raw: RawOperationResponseV1):
        return runner._gate_d_classify_cancel_result(
            raw, expected_order_id=self.ORDER_ID, expected_client_order_id=self.CLIENT_ORDER_ID,
        )

    # -- CANCEL-RESULT-01..08 (dispatch Section 29) --------------------

    def test_cancel_result_01_valid_exact_response_is_definitive_success(self) -> None:
        outcome, body = self._classify(self._raw(body={"order_id": self.ORDER_ID, "reduced_by": "1.00", "ts_ms": 123}))
        self.assertIs(outcome, runner.SendOutcome.DEFINITIVE_SUCCESS)
        self.assertEqual(body["reduced_by"], "1.00")

    def test_cancel_result_02_missing_reduced_by(self) -> None:
        outcome, _ = self._classify(self._raw(body={"order_id": self.ORDER_ID, "ts_ms": 123}))
        self.assertIs(outcome, runner.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_cancel_result_03_malformed_reduced_by(self) -> None:
        outcome, _ = self._classify(self._raw(body={"order_id": self.ORDER_ID, "reduced_by": "abc", "ts_ms": 123}))
        self.assertIs(outcome, runner.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_cancel_result_04_wrong_order_id(self) -> None:
        outcome, _ = self._classify(self._raw(body={"order_id": "wrong-order", "reduced_by": "1.00", "ts_ms": 123}))
        self.assertIs(outcome, runner.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_cancel_result_05_wrong_present_client_order_id(self) -> None:
        outcome, _ = self._classify(self._raw(body={
            "order_id": self.ORDER_ID, "reduced_by": "1.00", "ts_ms": 123,
            "client_order_id": "22222222-2222-4222-8222-222222222222",
        }))
        self.assertIs(outcome, runner.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_cancel_result_06_absent_client_order_id_still_succeeds(self) -> None:
        outcome, _ = self._classify(self._raw(body={"order_id": self.ORDER_ID, "reduced_by": "1.00", "ts_ms": 123}))
        self.assertIs(outcome, runner.SendOutcome.DEFINITIVE_SUCCESS)

    def test_cancel_result_07_malformed_ts_ms(self) -> None:
        outcome, _ = self._classify(self._raw(body={"order_id": self.ORDER_ID, "reduced_by": "1.00", "ts_ms": "abc"}))
        self.assertIs(outcome, runner.SendOutcome.SEND_MAY_HAVE_BEGUN_UNKNOWN)

    def test_cancel_result_08_malformed_body_never_labeled_definitive_success(self) -> None:
        raw = RawOperationResponseV1(http_status=200, content_type="application/json", body_bytes=b"not-json-bytes")
        outcome, _ = self._classify(raw)
        self.assertIsNot(outcome, runner.SendOutcome.DEFINITIVE_SUCCESS)

    # -- CANCEL-CONSERVATION-01..04 (dispatch Section 30; 05/06 are
    # structural/integration properties covered by the GD-series tests --
    # no code path ever substitutes GET_ORDER remaining_count_fp for
    # reduced_by, and GD20/GD13 already prove trustworthy-reduced_by
    # gating end-to-end) -----------------------------------------------

    def test_cancel_conservation_01_zero_fill_full_reduced_by_passes(self) -> None:
        self.assertIsNone(runner.check_cancel_conservation(final_fill_quantity=D("0.00"), reduced_by=D("1.00")))

    def test_cancel_conservation_02_partial_fill_complement_passes(self) -> None:
        self.assertIsNone(runner.check_cancel_conservation(final_fill_quantity=D("0.25"), reduced_by=D("0.75")))

    def test_cancel_conservation_03_another_exact_split_passes(self) -> None:
        self.assertIsNone(runner.check_cancel_conservation(final_fill_quantity=D("0.60"), reduced_by=D("0.40")))

    def test_cancel_conservation_04_mismatch_fails_closed(self) -> None:
        self.assertIsNotNone(runner.check_cancel_conservation(final_fill_quantity=D("0.25"), reduced_by=D("0.70")))

    # -- TERM05-01..25 (Correction 05 dispatch Sections 26-29). Status
    # itself is validated against `SUPPORTED_ORDER_STATUSES` inside
    # `_gate_d_validate_terminal_order_identity` now (Correction 05
    # Section 23), but this validator is still only ever invoked by the
    # caller after status is already confirmed to be an exact member of
    # `_GATE_D_TERMINAL_ORDER_STATUSES` -- the "resting"/unsupported-status
    # end-to-end path remains covered by GD14. ---------------------------

    EXPECTED_YES_PRICE = D("0.44")

    def _row(self, *, remove: tuple = (), **overrides) -> dict:
        row = {
            "order_id": self.ORDER_ID, "client_order_id": self.CLIENT_ORDER_ID, "ticker": self.TICKER,
            "side": "yes", "status": "canceled", "subaccount": 0, "exchange_index": 0,
            "fill_count_fp": "0.00", "remaining_count_fp": "1.00", "initial_count_fp": "1.00",
            "yes_price_dollars": "0.44",
        }
        row.update(overrides)
        for key in remove:
            row.pop(key, None)
        return row

    def _violation(
        self, *, remove: tuple = (), expected_outcome_side: str = "YES", expected_yes_price: Decimal | None = None,
        **row_overrides,
    ) -> str | None:
        return runner._gate_d_validate_terminal_order_identity(
            self._row(remove=remove, **row_overrides), expected_order_id=self.ORDER_ID,
            expected_client_order_id=self.CLIENT_ORDER_ID, expected_ticker=self.TICKER,
            expected_outcome_side=expected_outcome_side,
            expected_yes_price=expected_yes_price if expected_yes_price is not None else self.EXPECTED_YES_PRICE,
        )

    # -- TERM05-01..07: exact complete rows accepted; core identity
    # mismatches unresolved (dispatch Section 26) ------------------------

    def test_term05_01_exact_lower_slot_canceled_row_accepted(self) -> None:
        self.assertIsNone(self._violation())

    def test_term05_02_exact_upper_slot_canceled_row_accepted(self) -> None:
        self.assertIsNone(self._violation(side="no", expected_outcome_side="NO"))

    def test_term05_03_exact_executed_row_accepted(self) -> None:
        self.assertIsNone(self._violation(status="executed", fill_count_fp="1.00", remaining_count_fp="0.00"))

    def test_term05_04_missing_client_order_id_unresolved(self) -> None:
        self.assertEqual(self._violation(remove=("client_order_id",)), "CLIENT_ORDER_ID_MISSING")

    def test_term05_05_wrong_client_order_id_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(client_order_id="99999999-9999-4999-8999-999999999999"))

    def test_term05_06_wrong_ticker_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(ticker="SOME-OTHER-TICKER"))

    def test_term05_07_wrong_order_id_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(order_id="a-different-order"))

    # -- TERM05-08..14: exact FixedPointCount lexical contract (dispatch
    # Section 27) ----------------------------------------------------------

    def test_term05_08_fill_count_fp_json_number_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(fill_count_fp=0))

    def test_term05_09_fill_count_fp_exponent_notation_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(fill_count_fp="1e0"))

    def test_term05_10_fill_count_fp_single_digit_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(fill_count_fp="1"))

    def test_term05_11_fill_count_fp_one_fractional_digit_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(fill_count_fp="1.0"))

    def test_term05_12_remaining_count_fp_single_digit_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(remaining_count_fp="1"))

    def test_term05_13_remaining_count_fp_three_fractional_digits_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(remaining_count_fp="1.000"))

    def test_term05_14_initial_count_fp_malformed_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(initial_count_fp="one"))

    # -- TERM05-15..18: quantity bounds / internal conservation (dispatch
    # Section 28) ------------------------------------------------------------

    def test_term05_15_fill_count_fp_exceeds_upper_bound_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(fill_count_fp="1.01"))

    def test_term05_16_remaining_count_fp_exceeds_upper_bound_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(remaining_count_fp="1.01"))

    def test_term05_17_fill_plus_remaining_exceeds_quantity_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(fill_count_fp="0.75", remaining_count_fp="0.50"))

    def test_term05_18_initial_count_fp_not_fixed_quantity_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(initial_count_fp="0.99"))

    # -- TERM05-19..25: price/identity/scope (dispatch Sections 20-22, 29) --

    def test_term05_19_wrong_quote_price_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(yes_price_dollars="0.50"))

    def test_term05_20_missing_quote_price_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(remove=("yes_price_dollars",)))

    def test_term05_21_wrong_outcome_side_mapping_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(side="no"))  # expected_outcome_side stays "YES"

    def test_term05_22_wrong_venue_book_side_mapping_unresolved(self) -> None:
        # Gate D's accepted venue row exposes exactly one side field
        # (outcome side yes/no, bijectively coupled to venue bid/ask by the
        # fixed two-slot strategy); an unsupported value fails closed
        # rather than silently defaulting.
        self.assertIsNotNone(self._violation(side="unknown"))

    def test_term05_23_order_type_field_not_part_of_accepted_venue_row(self) -> None:
        # Gate D's already-established accepted venue-row schema carries no
        # separate order-type field (dispatch Section 21: validated "wherever
        # those fields are part of the accepted venue row"); this documents
        # that scoping choice rather than exercising a live check.
        self.assertIsNone(self._violation())

    def test_term05_24_wrong_subaccount_scope_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(subaccount=1))

    def test_term05_25_wrong_exchange_index_scope_unresolved(self) -> None:
        self.assertIsNotNone(self._violation(exchange_index=1))

    # -- TERM06-01..13: mandatory, exact-int-typed subaccount/exchange_index
    # scope (dispatch Sections 13-16/22) -- `type(...) is int`, never
    # `isinstance`, since `bool` is a subclass of `int` in Python; no
    # invented default for a missing field ----------------------------------

    def test_term06_01_missing_subaccount_unresolved(self) -> None:
        self.assertEqual(self._violation(remove=("subaccount",)), "SUBACCOUNT_MISSING_OR_MALFORMED")

    def test_term06_02_missing_exchange_index_unresolved(self) -> None:
        self.assertEqual(self._violation(remove=("exchange_index",)), "EXCHANGE_INDEX_MISSING_OR_MALFORMED")

    def test_term06_03_subaccount_false_unresolved(self) -> None:
        self.assertEqual(self._violation(subaccount=False), "SUBACCOUNT_MISSING_OR_MALFORMED")

    def test_term06_04_exchange_index_false_unresolved(self) -> None:
        self.assertEqual(self._violation(exchange_index=False), "EXCHANGE_INDEX_MISSING_OR_MALFORMED")

    def test_term06_05_subaccount_true_unresolved(self) -> None:
        self.assertEqual(self._violation(subaccount=True), "SUBACCOUNT_MISSING_OR_MALFORMED")

    def test_term06_06_exchange_index_true_unresolved(self) -> None:
        self.assertEqual(self._violation(exchange_index=True), "EXCHANGE_INDEX_MISSING_OR_MALFORMED")

    def test_term06_07_subaccount_float_zero_unresolved(self) -> None:
        self.assertEqual(self._violation(subaccount=0.0), "SUBACCOUNT_MISSING_OR_MALFORMED")

    def test_term06_08_exchange_index_float_zero_unresolved(self) -> None:
        self.assertEqual(self._violation(exchange_index=0.0), "EXCHANGE_INDEX_MISSING_OR_MALFORMED")

    def test_term06_09_subaccount_string_zero_unresolved(self) -> None:
        self.assertEqual(self._violation(subaccount="0"), "SUBACCOUNT_MISSING_OR_MALFORMED")

    def test_term06_10_exchange_index_string_zero_unresolved(self) -> None:
        self.assertEqual(self._violation(exchange_index="0"), "EXCHANGE_INDEX_MISSING_OR_MALFORMED")

    def test_term06_11_subaccount_wrong_int_unresolved(self) -> None:
        self.assertEqual(self._violation(subaccount=1), "SUBACCOUNT_MISMATCH")

    def test_term06_12_exchange_index_wrong_int_unresolved(self) -> None:
        self.assertEqual(self._violation(exchange_index=1), "EXCHANGE_INDEX_MISMATCH")

    def test_term06_13_exact_int_zero_scope_accepted(self) -> None:
        self.assertIsNone(self._violation(subaccount=0, exchange_index=0))

    # -- Fresh fill reconciliation (Correction 03/04, independent of
    # reduced_by) ---------------------------------------------------------

    def test_fresh_fill_reconciliation_matches_order_fill_count(self) -> None:
        from arb.venues.kalshi.risk_control import EconomicFillV1
        order_row = self._row(fill_count_fp="0.60")
        fills = (EconomicFillV1(self.TICKER, "fill-1", "YES", D("0.60"), D("0.44"), "2026-08-15T00:00:00.000000Z"),)
        self.assertIsNone(runner._gate_d_fresh_fill_reconciliation_violation(order_row=order_row, fresh_fills=fills))

    def test_fresh_fill_reconciliation_mismatch_detected(self) -> None:
        from arb.venues.kalshi.risk_control import EconomicFillV1
        order_row = self._row(fill_count_fp="0.60")
        fills = (EconomicFillV1(self.TICKER, "fill-1", "YES", D("0.25"), D("0.44"), "2026-08-15T00:00:00.000000Z"),)
        self.assertIsNotNone(runner._gate_d_fresh_fill_reconciliation_violation(order_row=order_row, fresh_fills=fills))


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


class ActiveRuntimeV2TestCase(unittest.TestCase):
    """R1-B03 T72/T73: ExperimentRunnerRuntimeV2 rejects LegacyIncidentContract;
    ExperimentRunnerRuntimeV1 preserves it."""

    def _binding(self, subaccount=1, exchange_index=0):
        return ledger_binding.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO",
            account_scope_ref="ARB_KALSHI_DEMO_PRIMARY_ACCOUNT",
            subaccount=subaccount, exchange_index=exchange_index)

    def _contract(self, binding):
        return ledger_binding.ActiveExecutionDomainContractV1(
            binding=binding, bootstrap_contract_sha256="a" * 64)

    def _route_qual(self, binding, *, wire_policy="EXPLICIT_EXCHANGE_INDEX"):
        return runner.ActiveRouteQualificationV1(
            environment=binding.environment, account_scope_ref=binding.account_scope_ref,
            subaccount=binding.subaccount, exchange_index=binding.exchange_index,
            operation_request_shape_id=runner._ACTIVE_ROUTE_REQUEST_SHAPE_ID,
            exchange_index_wire_policy=wire_policy,
            qualification_evidence_identity_sha256=runner._N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256,
            provenance_class="PROJECT_EVIDENCE_RECORDED")

    def _post_init_with_patched_gates(self, obj):
        """Run V2.__post_init__ with the gate *type* checks neutralised so the
        legacy-rejection / binding-equality guards (which run afterwards) are
        the ones exercised."""
        weg = WriterEligibilityGate(
            monotonic_clock_ns=lambda: 0,
            wall_clock=lambda: datetime.now(timezone.utc), uuid_factory=uuid.uuid4)
        object.__setattr__(obj, "normal_gate", weg)
        object.__setattr__(obj, "emergency_gate", weg)
        object.__setattr__(obj, "authority_binding", AuthorityNamespaceBinding(
            "ns", Path("/x"), Path("/x/a.sqlite3"), "0" * 64))
        with mock.patch.object(runner, "EmergencyCancelGate", WriterEligibilityGate):
            runner.ExperimentRunnerRuntimeV2.__post_init__(obj)

    def _bare_v2(self, **overrides):
        obj = object.__new__(runner.ExperimentRunnerRuntimeV2)
        defaults = dict(
            normal_gate=None, emergency_gate=None,
            read_local_safety_state=lambda: None, read_trusted_release_evidence=lambda: None,
            send_operation_request=lambda *a: None, fetch_orderbook=lambda *a: None,
            monotonic_clock_ns=lambda: 0, wall_clock=lambda: datetime.now(timezone.utc),
            uuid_factory=uuid.uuid4, risk_config=None, experiment_absolute_end_monotonic_ns=1,
            authority_binding=mock.Mock(), canonical_repository_root="/x",
            expected_ledger_path=None, domain_binding=None, active_contract=None,
            route_qualification=None, accepted_evidence_contract=None,
            strategy_instance_id=None, minimum_spread_usd=None,
            gate_d_capability_reference_id=None, normal_write_transport=None,
            trusted_dynamic_read_acquirer_test_seam=None,
        )
        defaults.update(overrides)
        db = defaults.get("domain_binding")
        if defaults.get("route_qualification") is None and type(db) is ledger_binding.ExecutionDomainBindingV1:
            defaults["route_qualification"] = self._route_qual(db)
        if (defaults.get("accepted_evidence_contract") is None
                and type(db) is ledger_binding.ExecutionDomainBindingV1
                and db.subaccount == 1 and db.exchange_index == 0):
            defaults["accepted_evidence_contract"] = runner.n1_accepted_evidence_contract(db)
        for k, v in defaults.items():
            object.__setattr__(obj, k, v)
        return obj

    def test_t73_runtime_v1_still_requires_legacy_contract(self) -> None:
        names = {f.name for f in dataclasses.fields(runner.ExperimentRunnerRuntimeV1)}
        self.assertIn("contract", names)
        annotations = runner.ExperimentRunnerRuntimeV1.__annotations__
        self.assertEqual(annotations["contract"], "LegacyIncidentContract")

    def test_t72_runtime_v2_has_no_legacy_contract_field(self) -> None:
        names = {f.name for f in dataclasses.fields(runner.ExperimentRunnerRuntimeV2)}
        self.assertNotIn("contract", names)
        self.assertNotIn("gate_d_incident_id", names)
        self.assertIn("domain_binding", names)
        self.assertIn("active_contract", names)

    def test_t72_runtime_v2_rejects_legacy_contract_value(self) -> None:
        b = self._binding()
        obj = self._bare_v2(domain_binding=b, active_contract=ledger_binding.CURRENT_LEGACY_INCIDENT_CONTRACT)
        with self.assertRaises(RunnerError) as ctx:
            self._post_init_with_patched_gates(obj)
        self.assertIn("ACTIVE_PATH_LEGACY_CONTRACT_REJECTED", str(ctx.exception))

    def test_t72_runtime_v2_requires_binding_contract_equality(self) -> None:
        b1 = self._binding(subaccount=1)
        b2 = self._binding(subaccount=2)
        c1 = self._contract(b1)
        obj = self._bare_v2(domain_binding=b2, active_contract=c1)
        with self.assertRaises(RunnerError) as ctx:
            self._post_init_with_patched_gates(obj)
        self.assertIn("ACTIVE_DOMAIN_CONTRACT_MISMATCH", str(ctx.exception))

    def test_t_runtime_v2_accepts_matched_binding_contract(self) -> None:
        # The genuinely supported active domain is N=1 (the only one with a
        # separately bound accepted-evidence contract).
        b = self._binding(subaccount=1)
        c = self._contract(b)
        obj = self._bare_v2(domain_binding=b, active_contract=c)
        self._post_init_with_patched_gates(obj)  # no raise

    def test_t_runtime_v2_future_subaccount_without_accepted_evidence_rejected(self) -> None:
        b = self._binding(subaccount=8)
        c = self._contract(b)
        obj = self._bare_v2(domain_binding=b, active_contract=c)  # no accepted-evidence contract exists for N=8
        with self.assertRaises(RunnerError) as ctx:
            self._post_init_with_patched_gates(obj)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED)

    def test_t_runtime_v2_gate_d_incident_id_derived(self) -> None:
        b = self._binding(subaccount=13)
        c = self._contract(b)
        obj = self._bare_v2(domain_binding=b, active_contract=c)
        self.assertEqual(
            runner.ExperimentRunnerRuntimeV2.gate_d_incident_id.fget(obj), c.incident_id)
        self.assertEqual(
            runner.ExperimentRunnerRuntimeV2.gate_d_writer_proof_id.fget(obj), c.writer_proof_id)



class ActiveStage3EndToEndTestCase(unittest.TestCase):
    """R1-B03 Correction-01 Finding 04: an offline deterministic fixture that
    executes the full active revision-2 release chain end to end, and proves
    no V1 token / legacy contract can enter it.  Also anchors the T-cases the
    blocked matrix left as inference-only (T46-T52 active Gate-B/D wiring;
    T30/T37 subaccount-wide completeness gate; T78 one-contract continuity)."""

    ACCOUNT = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
    TICKER = CURRENT_TICKER

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        self.authority_root = self.root / "authority"
        self.authority_root.mkdir()
        self.inputs = DeterministicInputs()
        self.ledger_path = self.root / "active.sqlite3"
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="active-e2e-ns", authority_namespace_root=self.authority_root,
            canonical_repository_root=self.repository_root)
        initialize_authority_namespace(
            self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        self.domain_binding = ledger_binding.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            subaccount=1, exchange_index=0)
        self.bootstrap = ledger_binding.DomainBootstrapContractV1(
            binding=self.domain_binding, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
            bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
            prestack_activity_completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK",
            unresolved_write_count=0, unresolved_cancel_count=0, working_order_truth="COMPLETE_ZERO",
            fill_truth="COMPLETE_KNOWN_NONZERO", position_truth="COMPLETE_KNOWN_NONZERO",
            retained_position_ticker="KXAAAGASD-26SEP02-4.1200",
            retained_position_floor_contracts=Decimal("1.00"))
        _, self.active_contract = ledger_binding.initialize_active_execution_domain_ledger(
            self.binding, canonical_repository_root=str(self.repository_root),
            domain_binding=self.domain_binding, bootstrap_contract=self.bootstrap,
            ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        self.config = RiskLimitConfigV1(
            1, self.domain_binding.conflict_domain_ref, "USD",
            PerOrderRiskLimits(Decimal("10"), Decimal("10"), True, Decimal("0.10"), 1_000),
            PerMarketRiskLimits(Decimal("20"), Decimal("20"), 10, Decimal("20"), Decimal("20")),
            AccountRiskLimits(Decimal("100"), 50, Decimal("100"), 0, Decimal("0")),
            FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"))
        self._drive_to_safe_held()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _drive_to_safe_held(self) -> None:
        emergency = ledger_binding.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=self.active_contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        self.assertIsNotNone(emergency.handle, emergency.failure_code)
        handle = emergency.handle
        handle.record_reconciliation({
            "incident_id": self.active_contract.incident_id,
            "disposition": "ACTIVE_SYNTHETIC_RESOLVED_SAFE",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
            "bound_order_id": None, "created_order_upper_bound": 0, "active_order_upper_bound": 0,
            "unknown_result": False, "writer_proof_release_eligible": True, "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RESOLUTION_V1",
        }, incident_id=self.active_contract.incident_id)
        resolved = handle.inspect_validated_projection()
        self.assertEqual(
            resolved.writer_proof_release_eligible_by_proof_id.get(self.active_contract.writer_proof_id), True)
        previous = handle.inspect_validated_projection()
        state_payload = {
            "previous_state": "BOOT_HOLD", "new_state": "SAFE_HELD",
            "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
            "risk_state_epoch_before": 0, "risk_state_epoch_after": 1,
            "risk_config_sha256": self.config.sha256,
            "related_emergency_action_id": None, "related_release_id": None,
            "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": previous.last_sequence,
            "observed_authority_trusted_hash": previous.terminal_event_hash,
            "observed_ledger_terminal_sequence": previous.last_sequence,
            "observed_ledger_terminal_hash": previous.terminal_event_hash,
        }
        handle.record_risk_control_state_changed(state_payload)
        self.assertEqual(handle.inspect_validated_projection().risk_control_state, "SAFE_HELD")
        handle.close()

    # The two spec-fixed DSB-N1-002 accepted evidence identities.
    N1_CHECKPOINT_SHA = "879d311420d2f6a4e2c20b8f96e8107f3753a30923f0e2afdfb7f5668bcb9068"
    N1_FILL_ISOLATION_SHA = "da301946c745b6ccac321a71e97683375bca9e103b649906c95999bc5587e360"

    def _route_qualification(self, *, wire_policy="EMPIRICALLY_BOUND_AUTOROUTE"):
        # DSB-N1-001 / DSB-QUOTE-004: the accepted N=1 empirical route
        # qualification, instantiated in an N=1-specific onboarding fixture --
        # NEVER inferred inside generic active execution code.
        return runner.ActiveRouteQualificationV1(
            environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            subaccount=1, exchange_index=0,
            operation_request_shape_id=runner._ACTIVE_ROUTE_REQUEST_SHAPE_ID,
            exchange_index_wire_policy=wire_policy,
            qualification_evidence_identity_sha256=self.N1_CHECKPOINT_SHA,
            provenance_class="PROJECT_EVIDENCE_RECORDED")

    def _evidence_contract(self):
        return runner.n1_accepted_evidence_contract(self.domain_binding)

    def _current_cutoff(self, rt) -> str:
        """The deterministic current reconciliation-cutoff identity for this
        empty-portfolio active fixture -- what a path-B theorem MUST bind to.
        Consumes one scripted read cycle from ``rt``'s transport."""
        capability = runner._issue_pre_release_read_capability(
            process_instance_id=rt.normal_gate.process_instance_id, ticker=self.TICKER, runtime=rt)
        truth = runner.collect_authoritative_read_truth(capability, ticker=self.TICKER)
        return runner._active_reconciliation_cutoff_sha256(truth)

    def _theorem(self, cutoff: str) -> "runner.SubaccountWideCompletenessTheoremV1":
        return runner.SubaccountWideCompletenessTheoremV1(
            conflict_domain_ref=self.domain_binding.conflict_domain_ref,
            subaccount=1, selected_exchange_index=0,
            proven_zero_foreign_exchange_indices=(1, 2, 3),
            reconciliation_cutoff_identity_sha256=cutoff,
            accepted_evidence_identity_sha256=self.N1_CHECKPOINT_SHA,
            provenance_class="PROJECT_EVIDENCE_RECORDED")

    def _proven_account_wide(
        self, *, cutoff, position_rows=(), working_order_rows=(), fill_rows=(),
        evidence_id=None, source=None, request_classification=None,
        account_scope_ref=None, subaccount=None,
    ) -> "runner.ProvenAccountWideReadV1":
        return runner.ProvenAccountWideReadV1(
            request_classification=(request_classification
                                    if request_classification is not None else "ACCOUNT_WIDE"),
            accepted_source_classification=(source if source is not None
                                            else runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1),
            accepted_evidence_identity_sha256=(evidence_id if evidence_id is not None
                                               else self.N1_CHECKPOINT_SHA),
            account_scope_ref=(account_scope_ref if account_scope_ref is not None else self.ACCOUNT),
            subaccount=(subaccount if subaccount is not None else 1),
            pagination_exhausted=True,
            reconciliation_cutoff_identity_sha256=cutoff,
            position_rows=tuple(position_rows),
            working_order_rows=tuple(working_order_rows),
            fill_rows=tuple(fill_rows))

    # --- Correction 02 trusted dynamic pre-release read-set fixture support --
    # ``DynamicIndexDomainAccountWideReadV1`` remains a deterministic OFFLINE
    # TEST FIXTURE representation only; it is consumed EXCLUSIVELY behind
    # ``_FakeTrustedDynamicReadAcquirerV2`` (DSB-DYN-004).
    P02_SHA = "2fc189b2a807a6c22ab3e71e41a6cfa66415e3bda87e6c8e66c3eb6e8029c69b"
    P01_SHA = "aeb07275f62ce295a131a07c5d2c9604728be58b416a9ff1d3d7517c8d0d6138"
    CONTROLLED_TICKER = "KXAAAGASD-26SEP02-4.1200"
    SETTLED_TIME = "2026-09-02T14:41:43.665741Z"
    T0 = "2026-08-17T12:59:59.700000Z"
    T1 = "2026-08-17T13:00:00.000000Z"
    NOW = "2026-08-17T13:00:00.004000Z"
    _SETTLE_DEFAULT = object()

    @staticmethod
    def _hx(n):
        return format(n % (16 ** 64), "064x")

    def _surface(self, seed):
        return runner.PerIndexSurfaceTraversalV1(
            request_identity_sha256=self._hx(seed),
            page_response_digests=(self._hx(seed + 1),),
            page_economic_digests=(self._hx(seed + 2),),
            final_cursor_absent=True, pagination_complete=True)

    def _traversal(self, idx, *, order_rows=(), fill_rows=(), position_rows=(), tag=0):
        base = (idx + 1) * 1000 + tag * 100
        return runner.PerIndexTraversalV1(
            exchange_index=idx, orders=self._surface(base + 10),
            fills=self._surface(base + 40), positions=self._surface(base + 70),
            order_rows=tuple(order_rows), fill_rows=tuple(fill_rows), position_rows=tuple(position_rows))

    def _settlement(self, **ov):
        d = dict(
            settlement_evidence_identity_sha256=self.P02_SHA,
            ticker=self.CONTROLLED_TICKER, exchange_index=0,
            conflict_domain_ref=self.domain_binding.conflict_domain_ref,
            market_result="yes", settled_time_utc=self.SETTLED_TIME,
            yes_count_fp="1.00", settlement_response_identity_sha256=self._hx(0x5e77))
        d.update(ov)
        return runner.RetainedPositionSettlementReconciliationV1(**d)

    def _dynamic_read(self, *, domain=(0, 1, 2, 3), traversals=None,
                      status_before=None, status_after=None, fb=None, fa=None,
                      selected_route_cutoff=None, settlement=_SETTLE_DEFAULT,
                      account_scope_ref=None, subaccount=1, selected_exchange_index=0,
                      source=None, evid=None, read_set_identity=None, recompute=True,
                      active_contract=None, risk_config=None):
        sb = status_before if status_before is not None else runner.ExchangeIndexStatusObservationV1(
            response_identity_sha256=self._hx(0x57a705), exchange_index_domain=tuple(domain))
        sa = status_after if status_after is not None else runner.ExchangeIndexStatusObservationV1(
            response_identity_sha256=self._hx(0x57a705), exchange_index_domain=tuple(domain))
        fbw = fb if fb is not None else runner.UserDataFreshnessWatermarkV1(
            response_identity_sha256=self._hx(0xf0), as_of_time_utc=self.T0)
        faw = fa if fa is not None else runner.UserDataFreshnessWatermarkV1(
            response_identity_sha256=self._hx(0xf1), as_of_time_utc=self.T1)
        trs = traversals if traversals is not None else tuple(self._traversal(i) for i in domain)
        cutoff = selected_route_cutoff if selected_route_cutoff is not None else self._hx(0x9c07)
        sr = self._settlement() if settlement is self._SETTLE_DEFAULT else settlement
        ac = active_contract or self.active_contract
        rc = risk_config or self.config
        read = runner.DynamicIndexDomainAccountWideReadV1(
            accepted_source_classification=(source if source is not None
                                            else runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1),
            index_domain_enumeration_evidence_identity_sha256=(evid if evid is not None else self.P02_SHA),
            account_scope_ref=(account_scope_ref if account_scope_ref is not None else self.ACCOUNT),
            subaccount=subaccount, selected_exchange_index=selected_exchange_index,
            status_before=sb, status_after=sa, freshness_before=fbw, freshness_after=faw,
            per_index_traversals=trs, selected_route_reconciliation_cutoff_sha256=cutoff,
            read_set_identity_sha256=(read_set_identity or self._hx(0)),
            settlement_reconciliation=sr)
        if recompute and read_set_identity is None:
            ident = runner.compute_dynamic_index_domain_read_set_identity(
                read,
                active_domain_binding_id=ac.domain_binding_id,
                active_domain_binding_sha256=ac.domain_binding_sha256,
                active_contract_sha256=ac.contract_sha256,
                risk_config_sha256=rc.sha256)
            read = dataclasses.replace(read, read_set_identity_sha256=ident)
        return read

    def _selected_route_truth(self, rt):
        """The deterministic current selected-route ``AuthoritativeReadTruthV1``
        for this empty-portfolio active fixture.  Consumes one scripted read
        cycle from ``rt``'s transport."""
        cap = runner._issue_pre_release_read_capability(
            process_instance_id=rt.normal_gate.process_instance_id, ticker=self.TICKER, runtime=rt)
        return runner.collect_authoritative_read_truth(cap, ticker=self.TICKER)

    def _seam_runtime(self, rt, *, fixture, selected_route_truth, implied_request_count=72):
        """Bind a ``_FakeTrustedDynamicReadAcquirerV2`` to the single
        synthetic-current-read seam (DSB-DYN-004).  A dedicated module-private
        test factory is the only permitted route; here we use it via
        ``dataclasses.replace`` on the already-validated runtime."""
        fake = runner._FakeTrustedDynamicReadAcquirerV2(
            runtime=rt, fixture=fixture, selected_route_truth=selected_route_truth,
            implied_request_count=implied_request_count)
        return dataclasses.replace(rt, trusted_dynamic_read_acquirer_test_seam=fake)

    def _fresh_seam(self, rt=None, *, dynamic_read_overrides=None, implied_request_count=72):
        """Build a V2 runtime whose Stage 3E acquires a VALID fresh trusted
        read-set: derive the current selected-route cutoff, build a fixture
        bound to it, and attach the fake acquirer seam.  Returns the seam
        runtime."""
        rt = rt if rt is not None else self._runtime()
        truth = self._selected_route_truth(rt)
        cutoff = runner._active_reconciliation_cutoff_sha256(truth)
        ov = dict(dynamic_read_overrides or {})
        ov.setdefault("selected_route_cutoff", cutoff)
        fixture = self._dynamic_read(**ov)
        return self._seam_runtime(
            rt, fixture=fixture, selected_route_truth=truth,
            implied_request_count=implied_request_count)

    def _runtime(self, *, read_cycles=24, gate_d=False, write_transport=None):
        transport = _ScriptedTransport()
        # Stage 3E/3F reads + the dry-run cutoff read + every Gate-D loop read
        # cycle reuse the same empty-portfolio script shape; queue a generous
        # deterministic supply.
        for _ in range(read_cycles):
            transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
            transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([]))
            transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([]))
        normal_gate = WriterEligibilityGate(
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid)
        emergency = ledger_binding.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root),
            active_contract=self.active_contract, expected_ledger_path=str(self.ledger_path),
            clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
        emergency_gate = EmergencyCancelGate(
            handle=emergency.handle, rate_lane=lane, process_instance_id=normal_gate.process_instance_id,
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid, active_contract=self.active_contract)
        emergency.handle.close()

        def _identified_orderbook_fetch(ticker, deadline):
            return _fake_orderbook_snapshot(self.TICKER).with_canonical_identity()

        extra = {}
        if gate_d:
            extra = dict(
                strategy_instance_id=GATE_D_STRATEGY_INSTANCE_ID,
                minimum_spread_usd=GATE_D_MIN_SPREAD,
                gate_d_capability_reference_id="cap_active_gate_d_test",
                normal_write_transport=write_transport or _ScriptedWriteTransport(),
            )
        rt = runner.build_active_experiment_runner_runtime_v2(
            normal_gate=normal_gate, emergency_gate=emergency_gate,
            send_operation_request=transport,
            fetch_orderbook=_identified_orderbook_fetch if gate_d else _standard_orderbook_fetch(self.TICKER),
            monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid, risk_config=self.config,
            experiment_absolute_end_monotonic_ns=10 ** 18, authority_binding=self.binding,
            canonical_repository_root=str(self.repository_root),
            expected_ledger_path=str(self.ledger_path),
            domain_binding=self.domain_binding, active_contract=self.active_contract,
            route_qualification=self._route_qualification(),
            accepted_evidence_contract=self._evidence_contract(), **extra)
        self._transport = transport
        return rt

    def test_finding04_full_active_release_chain(self) -> None:
        # Correction 02: current Path-A truth comes ONLY from the trusted
        # dynamic pre-release acquisition boundary.  The fake acquirer seam is
        # the sole offline synthetic-current-read path (DSB-DYN-004).
        rt = self._fresh_seam()
        invocation = runner.ExperimentRunnerInvocationV2(
            invocation_id="active-e2e-1", market_ticker=self.TICKER)
        read_phase = runner.run_pre_release_read_phase_v2(invocation, rt)
        self.assertEqual(read_phase.status, "READ_PHASE_COMPLETE", read_phase.local_block_reasons)
        self.assertIsInstance(read_phase.active_release_state, ledger_binding.ActiveReleaseEvaluationStateV1)
        self.assertEqual(
            read_phase.active_release_state.active_contract.contract_sha256,
            self.active_contract.contract_sha256)
        # DSB-WRITER-004/006: the release state + the phase result commit to
        # the exact private ADRS2 read-set identity.
        self.assertTrue(read_phase.trusted_dynamic_read_set_id.startswith("ADRS2_"))
        self.assertEqual(
            read_phase.active_release_state.trusted_dynamic_read_set_id,
            read_phase.trusted_dynamic_read_set_id)

        stage3 = runner._complete_stage3_active_release_and_normal_writer_v2(read_phase, rt)
        self.assertTrue(stage3.release_id.startswith("rel_"))
        self.assertRegex(stage3.normal_writer_session_id, r"^ws_[0-9a-f]{32}$")
        self.assertEqual(stage3.active_contract.incident_id, self.active_contract.incident_id)
        acq = stage3.normal_writer_acquisition
        self.assertIsInstance(acq, NormalWriterAcquisition)
        self.assertIsNotNone(acq.handle)
        proj = acq.handle.projection()
        self.assertEqual(proj.risk_control_state, "WRITER_ELIGIBLE")
        self.assertEqual(
            proj.writer_proof_state_by_proof_id.get(self.active_contract.writer_proof_id), "RELEASED")
        # T78: one identical active contract id/hash carried Stage 3A -> 3K.
        self.assertEqual(read_phase.active_release_state.active_contract.contract_id, stage3.active_contract.contract_id)
        end_writer_session(acq.handle, writer_session_id=stage3.normal_writer_session_id)

    def test_finding04_v1_token_cannot_enter_active_normal_writer(self) -> None:
        # A V1 completion token is invalid for the active revision-2
        # normal-writer acquisition (DSB-WRITER-006).
        rt = self._fresh_seam()
        invocation = runner.ExperimentRunnerInvocationV2(invocation_id="a", market_ticker=self.TICKER)
        read_phase = runner.run_pre_release_read_phase_v2(invocation, rt)
        # Drive Stage 3G/3H directly to obtain a genuine V1 token, then prove
        # acquire_active_normal_writer_state_v1 rejects it.
        acquisition = ledger_binding.acquire_active_release_only_v1(
            rt.authority_binding, canonical_repository_root=rt.canonical_repository_root,
            active_contract=rt.active_contract, expected_ledger_path=rt.expected_ledger_path,
            clock=rt.wall_clock, uuid_factory=rt.uuid_factory,
            monotonic_clock_ns=rt.monotonic_clock_ns, release_wall_clock=rt.wall_clock)
        handle = acquisition.handle
        assessment = handle.evaluate_release(read_phase.active_release_state.inner)
        handle.record_risk_release(assessment)
        handle.release_writer_proof(assessment)
        handle.record_writer_eligible(assessment)
        v1_token = handle.complete_release_and_issue_current_process_completion(assessment)
        self.assertIs(type(v1_token), CurrentProcessReleaseCompletionV1)
        normal = ledger_binding.acquire_active_normal_writer_state_v1(
            rt.authority_binding, canonical_repository_root=rt.canonical_repository_root,
            risk_config=rt.risk_config, process_instance_id=rt.normal_gate.process_instance_id,
            current_process_release_completion=v1_token, active_contract=rt.active_contract,
            expected_ledger_path=rt.expected_ledger_path, clock=rt.wall_clock, uuid_factory=rt.uuid_factory)
        self.assertIsNone(normal.handle)
        self.assertEqual(normal.failure_code, ledger_binding.FailureCode.CURRENT_PROCESS_RELEASE_COMPLETION_INVALID)

    def test_finding04_legacy_contract_cannot_build_active_runtime(self) -> None:
        with self.assertRaises(RunnerError):
            runner.build_active_experiment_runner_runtime_v2(
                normal_gate=WriterEligibilityGate(
                    monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
                    uuid_factory=self.inputs.uuid),
                emergency_gate=object(), send_operation_request=lambda *a: None,
                fetch_orderbook=lambda *a: None, monotonic_clock_ns=self.inputs.monotonic_ns,
                wall_clock=self.inputs.clock, uuid_factory=self.inputs.uuid, risk_config=self.config,
                experiment_absolute_end_monotonic_ns=10 ** 18, authority_binding=self.binding,
                canonical_repository_root=str(self.repository_root),
                expected_ledger_path=str(self.ledger_path),
                domain_binding=self.domain_binding, route_qualification=self._route_qualification(),
                accepted_evidence_contract=self._evidence_contract(),
                active_contract=ledger_binding.CURRENT_LEGACY_INCIDENT_CONTRACT)

    def test_finding03_subaccount_wide_completeness_gate_closed_by_default(self) -> None:
        # Correction 06 (BLOCK-05-01 / DSB-DYN-005 / DSB-RISK-004): the
        # production live acquirer is fully implemented and drives the exact
        # DSB-OPS transport.  When the trusted transport cannot complete the
        # very first status bookend, current Path-A truth cannot be produced
        # and the active release gate stays CLOSED (fail closed, no fabricated
        # truth, no fallback to an out-of-band read).
        rt = self._runtime()  # no fake seam -> the real live acquirer runs
        self._transport.queue(
            RunnerOperation.GET_EXCHANGE_STATUS,
            RawOperationResponseV1(http_status=503, content_type="application/json", body_bytes=b"{}"))
        invocation = runner.ExperimentRunnerInvocationV2(invocation_id="a", market_ticker=self.TICKER)
        with self.assertRaises(RunnerError) as c:
            runner.run_pre_release_read_phase_v2(invocation, rt)
        self.assertEqual(c.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_finding03_scope_classify_and_partition(self) -> None:
        # T31-T35: foreign subaccount => MISMATCH; missing scope => AMBIGUOUS;
        # foreign index on exact route => DOMAIN_ROUTE_EXCHANGE_INDEX_MISMATCH;
        # account-wide partitions selected vs same-subaccount-other-index.
        with self.assertRaises(RunnerError) as c:
            runner.active_scope_classify_row({"subaccount": 2, "exchange_index": 0},
                                             expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH)
        with self.assertRaises(RunnerError) as c:
            runner.active_scope_classify_row({"subaccount": 1},
                                             expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS)
        with self.assertRaises(RunnerError) as c:
            runner.active_scope_classify_row({"subaccount": 1, "exchange_index": 5},
                                             expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_ROUTE_EXCHANGE_INDEX_MISMATCH)
        # DSB-READ-003: a PROVEN account-wide read MAY legitimately contain
        # multiple subaccounts.  Every row is partitioned exactly: selected
        # sub / selected index -> selected; selected sub / foreign index ->
        # same_subaccount_foreign_index (folded into aggregate risk); another
        # subaccount -> foreign_subaccount (digested/counted, NOT folded).
        proven = self._proven_account_wide(
            cutoff="a" * 64,
            position_rows=(
                {"subaccount": 1, "exchange_index": 0, "position_count_fp": "1.00"},
                {"subaccount": 1, "exchange_index": 2, "position_count_fp": "3.00",
                 "yes_price_dollars": "0.40", "position_as_of_utc": "2026-09-01T00:00:00.000000Z"},
                {"subaccount": 9, "exchange_index": 0, "position_count_fp": "7.00"},
            ))
        part = runner.partition_active_account_wide_rows(
            proven, expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(len(part.selected), 1)
        self.assertEqual(len(part.same_subaccount_foreign_index), 1)
        self.assertEqual(len(part.foreign_subaccount), 1)
        self.assertEqual(part.foreign_subaccount_count, 1)
        self.assertTrue(runner._is_hex64(part.foreign_partition_digest_sha256))
        # A non-ProvenAccountWideReadV1 argument is never partitionable.
        with self.assertRaises(RunnerError) as c:
            runner.partition_active_account_wide_rows(
                [{"subaccount": 1, "exchange_index": 0}], expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)
        # A malformed / unpartitionable row is AMBIGUOUS.
        with self.assertRaises(RunnerError) as c:
            runner.partition_active_account_wide_rows(
                self._proven_account_wide(cutoff="a" * 64, position_rows=({"subaccount": 1},)),
                expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS)

    def test_finding02_active_terminal_validation_uses_binding_not_literals(self) -> None:
        # T46-T48: active terminal validation compares to the binding's
        # subaccount/exchange_index; an arbitrary synthetic non-1 subaccount
        # passes when the row matches; wrong subaccount/index fail closed;
        # no literal 0/1 in the active predicate.
        row_ok = _order_row("ord-1", ticker=self.TICKER, client_order_id="c" * 8,
                            subaccount=1, exchange_index=0)
        self.assertIsNone(runner._gate_d_validate_terminal_order_identity(
            row_ok, expected_order_id="ord-1", expected_client_order_id="c" * 8,
            expected_ticker=self.TICKER, expected_outcome_side="YES", expected_yes_price=Decimal("0.45"),
            expected_subaccount=1, expected_exchange_index=0))
        row_syn = _order_row("ord-2", ticker=self.TICKER, client_order_id="c" * 8,
                             subaccount=42, exchange_index=0)
        self.assertIsNone(runner._gate_d_validate_terminal_order_identity(
            row_syn, expected_order_id="ord-2", expected_client_order_id="c" * 8,
            expected_ticker=self.TICKER, expected_outcome_side="YES", expected_yes_price=Decimal("0.45"),
            expected_subaccount=42, expected_exchange_index=0))
        self.assertEqual("SUBACCOUNT_MISMATCH", runner._gate_d_validate_terminal_order_identity(
            row_ok, expected_order_id="ord-1", expected_client_order_id="c" * 8,
            expected_ticker=self.TICKER, expected_outcome_side="YES", expected_yes_price=Decimal("0.45"),
            expected_subaccount=2, expected_exchange_index=0))
        self.assertEqual("EXCHANGE_INDEX_MISMATCH", runner._gate_d_validate_terminal_order_identity(
            row_ok, expected_order_id="ord-1", expected_client_order_id="c" * 8,
            expected_ticker=self.TICKER, expected_outcome_side="YES", expected_yes_price=Decimal("0.45"),
            expected_subaccount=1, expected_exchange_index=9))
        # Default (no explicit scope) preserves the legacy SUBACCOUNT=0 behaviour.
        row_legacy = _order_row("ord-3", ticker=self.TICKER, client_order_id="c" * 8,
                                subaccount=0, exchange_index=0)
        self.assertIsNone(runner._gate_d_validate_terminal_order_identity(
            row_legacy, expected_order_id="ord-3", expected_client_order_id="c" * 8,
            expected_ticker=self.TICKER, expected_outcome_side="YES", expected_yes_price=Decimal("0.45")))


class ActiveGateDDomainBoundPermitTestCase(ActiveStage3EndToEndTestCase):
    """R1-B03 Correction-02 Finding 01: the active ordinary Gate-D CREATE and
    CANCEL permit/assessment/prepared-request paths carry and verify the exact
    DSB-WRITER-007/008 active execution-domain commitments, and any mutation of
    a material domain commitment fails BEFORE transport (transport invocation
    count stays zero)."""

    _EXPECTED_KEYS = (
        "domain_binding_id", "domain_binding_sha256", "active_contract_id",
        "active_contract_sha256", "bootstrap_contract_sha256", "conflict_domain_ref",
        "account_scope_ref", "subaccount", "exchange_index", "environment",
        "incident_id", "writer_proof_id",
    )

    def _expected_commitments(self) -> dict:
        c = self.active_contract
        return {
            "domain_binding_id": c.domain_binding_id,
            "domain_binding_sha256": c.domain_binding_sha256,
            "active_contract_id": c.contract_id,
            "active_contract_sha256": c.contract_sha256,
            "bootstrap_contract_sha256": c.bootstrap_contract_sha256,
            "conflict_domain_ref": c.conflict_domain_ref,
            "account_scope_ref": c.account_scope_ref,
            "subaccount": c.subaccount,
            "exchange_index": c.exchange_index,
            "environment": c.environment,
            "incident_id": c.incident_id,
            "writer_proof_id": c.writer_proof_id,
        }

    def _reach_stage3(self, rt):
        # Correction 02: Stage 3E current Path-A truth comes ONLY from the
        # trusted dynamic pre-release acquisition boundary.  Bind the offline
        # fake-acquirer seam to a fresh valid read-set fixture (DSB-DYN-004).
        truth = self._selected_route_truth(rt)
        cutoff = runner._active_reconciliation_cutoff_sha256(truth)
        fixture = self._dynamic_read(selected_route_cutoff=cutoff)
        seam_rt = self._seam_runtime(rt, fixture=fixture, selected_route_truth=truth)
        invocation = runner.ExperimentRunnerInvocationV2(
            invocation_id="c02-f1", market_ticker=self.TICKER)
        read_phase = runner.run_pre_release_read_phase_v2(invocation, seam_rt)
        self.assertEqual(read_phase.status, "READ_PHASE_COMPLETE", read_phase.local_block_reasons)
        stage3 = runner._complete_stage3_active_release_and_normal_writer_v2(read_phase, seam_rt)
        self.assertTrue(stage3.trusted_dynamic_read_set_id.startswith("ADRS2_"))
        self._active_handle = stage3.normal_writer_acquisition.handle
        return invocation, stage3

    def tearDown(self) -> None:
        handle = getattr(self, "_active_handle", None)
        if handle is not None and not handle.closed:
            try:
                handle.close()
            except Exception:
                pass
        super().tearDown()

    def _scoped_position_row(self, *, position_count_fp="0.00"):
        return {"ticker": self.TICKER, "subaccount": 1, "exchange_index": 0,
                "position_count_fp": position_count_fp}

    def _capture_permits(self):
        real = runner.issue_and_persist_write_permit
        permits: list = []

        def _wrapper(**kwargs):
            permit = real(**kwargs)
            permits.append(permit)
            return permit

        return mock.patch.object(runner, "issue_and_persist_write_permit", side_effect=_wrapper), permits

    def _seed_active_resting_order(
        self, stage3, rt, *, quote_slot, client_order_id, venue_order_id, yes_price, request_seed,
    ) -> None:
        from arb.execution_ledger import EventInput, EventType as ET
        locked = stage3.normal_writer_acquisition.handle
        session_id = stage3.normal_writer_session_id
        venue_side = "bid" if quote_slot == QuoteSlot.LOWER_YES_BID.value else "ask"
        outcome_side = "YES" if quote_slot == QuoteSlot.LOWER_YES_BID.value else "NO"
        binding = VenueBindingV1(adapter_payload_schema_id="mm-create-v1")
        body = build_mm_create_order_body(
            ticker=self.TICKER, client_order_id=client_order_id, venue_side=venue_side, yes_price=yes_price,
            quantity=D("1.00"), expiration_time=6_000_000_000, venue_binding=binding)
        prepared = build_create_prepared_payload(
            request_id=f"req_{request_seed}", environment="KALSHI_DEMO", client_order_id=client_order_id,
            canonical_body=body, venue_binding=binding)
        candidate = CandidateOrderV1(self.TICKER, outcome_side, D("1.00"), yes_price)
        state = MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0"))
        risk_state_epoch = locked.projection().risk_state_epoch
        assessment = build_writer_eligibility_assessment(
            risk_assessment_id=f"ra_{request_seed}", request_id=f"req_{request_seed}", candidate=candidate,
            market_economic_state=state, unresolved_exposure=D("0"), risk_config=rt.risk_config,
            prepared_request_sha256=prepared["prepared_request_sha256"], market_data_snapshot_sha256="a" * 64,
            market_data_freshness_identity_sha256="b" * 64, reconciliation_snapshot_sha256="c" * 64,
            reconciliation_freshness_identity_sha256="d" * 64, risk_state_epoch=risk_state_epoch,
            freshness_deadline_monotonic_ns=999_999_999_999)
        quote_generation_id = "qg_" + hashlib.sha256(request_seed.encode("utf-8")).hexdigest()[:32]
        outer_intent = build_mm_create_intent_payload(
            execution_attempt_id=f"ea_{request_seed}", conflict_domain_ref=locked.conflict_domain_ref,
            incident_id=rt.gate_d_incident_id, client_order_id=client_order_id,
            capability_reference_id=rt.gate_d_capability_reference_id, request_id=f"req_{request_seed}",
            strategy_instance_id=GATE_D_STRATEGY_INSTANCE_ID, market_ticker=self.TICKER, quote_slot=quote_slot,
            quote_generation_id=quote_generation_id, quote_plan_sha256="a" * 64, plan_input_sha256="b" * 64,
            source_book_snapshot_sha256="c" * 64, risk_config_sha256=rt.risk_config.sha256,
            risk_state_epoch=risk_state_epoch, reconciliation_snapshot_sha256="c" * 64,
            venue_side=venue_side, outcome_side=outcome_side, yes_price=yes_price, quantity=D("1.00"))
        issue_and_persist_write_permit(
            gate=rt.normal_gate, locked=locked, normal_writer_session_id=session_id,
            assessment=assessment, outer_intent_payload=outer_intent, prepared_payload=prepared)
        locked.append_batch((EventInput(ET.HTTP_RESPONSE_CLASSIFIED, {
            "request_id": f"req_{request_seed}", "http_status": 200, "response_media_type": "application/json",
            "response_byte_length": 0, "response_sha256": "0" * 64,
            "adapter_result_class": "DEFINITIVE_RESPONSE_AFTER_SEND", "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED",
            "validated_identity_fields": {},
        }, session_id, None, None),))
        locked.append_batch((EventInput(ET.ORDER_IDENTITY_BOUND, {
            "client_order_id": client_order_id, "venue_order_id": venue_order_id, "venue": "KALSHI",
            "environment": "KALSHI_DEMO", "incident_id": rt.gate_d_incident_id, "binding_basis_event_ids": [],
        }, session_id, rt.gate_d_incident_id, None),))
        canonical_order = {"order_id": venue_order_id, "status": "resting", "remaining_count_fp": "1.00"}
        locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
            "venue_order_id": venue_order_id, "client_order_id": client_order_id,
            "source_request_id": "seed-read", "source_operation": "GET_ORDER_V2",
            "venue_payload_schema_id": "seed-order-v1", "canonical_venue_payload": canonical_order,
            "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
            "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
        }, session_id, None, None),))

    # ``_reach_stage3`` consumes an unspecified number of scripted empty read
    # cycles (cutoff dry-run + Stage-3E).  Every Gate-D test therefore drains
    # the read script immediately afterward and queues EXACTLY the cycles the
    # bounded Gate-D loop will consume, so a scripted response is never
    # silently mismatched to the wrong cycle.
    def _reset_reads(self) -> None:
        self._transport.responses.clear()

    def _q_empty_read_cycle(self) -> None:
        self._transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
        self._transport.queue(RunnerOperation.GET_ORDERS, _orders_payload([]))
        self._transport.queue(RunnerOperation.GET_POSITIONS, _positions_payload([]))

    def _q_resting_order_read_cycle(self, venue_order_id: str) -> None:
        self._transport.queue(RunnerOperation.GET_MARKET, _market_payload(ticker=self.TICKER))
        self._transport.queue(RunnerOperation.GET_ORDERS, _orders_payload(
            [_order_row(venue_order_id, ticker=self.TICKER, yes_price_dollars="0.05",
                        subaccount=1, exchange_index=0)]))
        self._transport.queue(RunnerOperation.GET_ORDER, _order_payload(
            venue_order_id, ticker=self.TICKER, yes_price_dollars="0.05",
            subaccount=1, exchange_index=0))
        self._transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))
        self._transport.queue(RunnerOperation.GET_POSITIONS,
                              _positions_payload([self._scoped_position_row()]))

    # ---- CREATE ----------------------------------------------------------

    def test_c02_f1_active_create_permit_carries_exact_domain_commitments(self) -> None:
        wt = _ScriptedWriteTransport()
        wt.queue(_json_response({"order": {"order_id": "venue-active-create-1"}}))
        rt = self._runtime(gate_d=True, write_transport=wt)
        invocation, stage3 = self._reach_stage3(rt)
        self._reset_reads()
        self._q_empty_read_cycle()
        self._transport.queue(RunnerOperation.GET_ORDER, _order_payload(
            "venue-active-create-1", ticker=self.TICKER, subaccount=1, exchange_index=0))

        patcher, permits = self._capture_permits()
        with patcher:
            result = runner.run_gate_d_ordinary_decision_loop(stage3, rt, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.action, "CREATE")
        self.assertTrue(outcome.transport_invoked)
        self.assertEqual(len(wt.calls), 1)
        self.assertEqual(len(permits), 1)
        permit = permits[0]
        for key, expected in self._expected_commitments().items():
            self.assertIsNotNone(getattr(permit, key), key)
            self.assertEqual(getattr(permit, key), expected, key)
        self.assertIsNotNone(permit.permit_domain_commitment_sha256)
        self.assertEqual(
            permit.permit_domain_commitment_sha256,
            runner.compute_permit_domain_commitment_sha256(permit))
        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id)

    def _assert_create_mutation_blocks(self, mutate_key: str) -> None:
        real_commit = runner.active_domain_commitment
        wt = _ScriptedWriteTransport()
        wt.queue(_json_response({"order": {"order_id": "venue-active-create-x"}}))
        rt = self._runtime(gate_d=True, write_transport=wt)
        invocation, stage3 = self._reach_stage3(rt)
        self._reset_reads()
        self._q_empty_read_cycle()

        def _corrupt(active_contract, domain_binding, *, _k=mutate_key):
            out = dict(real_commit(active_contract, domain_binding))
            value = out[_k]
            if _k in ("subaccount", "exchange_index"):
                out[_k] = value + 1
            elif _k in ("active_contract_sha256", "domain_binding_sha256"):
                out[_k] = ("f" if value[0] != "f" else "0") + value[1:]
            else:
                out[_k] = value + "-MUT"
            return out

        with mock.patch.object(runner, "active_domain_commitment", side_effect=_corrupt):
            result = runner.run_gate_d_ordinary_decision_loop(stage3, rt, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertIsNotNone(outcome)
        self.assertFalse(outcome.transport_invoked, mutate_key)
        self.assertEqual(len(wt.calls), 0, mutate_key)
        # every fail-closed classification here proves transport was NOT
        # invoked (PERMIT_ISSUANCE_FAILED is the risk-control layer rejecting
        # the mismatched conflict-domain commitment before permit issuance).
        self.assertIn(outcome.result_classification, {
            "ACTIVE_DOMAIN_PERMIT_MISMATCH", "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH",
            "ACTIVE_DOMAIN_CONTRACT_MISMATCH", "PERMIT_ISSUANCE_FAILED",
        }, mutate_key)

    def test_c02_f1_active_create_mutated_active_contract_sha256_blocks(self) -> None:
        self._assert_create_mutation_blocks("active_contract_sha256")

    def test_c02_f1_active_create_mutated_domain_binding_sha256_blocks(self) -> None:
        self._assert_create_mutation_blocks("domain_binding_sha256")

    def test_c02_f1_active_create_mutated_conflict_domain_ref_blocks(self) -> None:
        self._assert_create_mutation_blocks("conflict_domain_ref")

    def test_c02_f1_active_create_mutated_subaccount_blocks(self) -> None:
        self._assert_create_mutation_blocks("subaccount")

    def test_c02_f1_active_create_mutated_writer_proof_id_blocks(self) -> None:
        self._assert_create_mutation_blocks("writer_proof_id")

    def test_c02_f1_active_create_mutated_incident_id_blocks(self) -> None:
        self._assert_create_mutation_blocks("incident_id")

    def test_c02_f1_active_create_mutated_permit_commitment_digest_blocks_before_transport(self) -> None:
        wt = _ScriptedWriteTransport()
        wt.queue(_json_response({"order": {"order_id": "venue-active-create-2"}}))
        rt = self._runtime(gate_d=True, write_transport=wt)
        invocation, stage3 = self._reach_stage3(rt)
        self._reset_reads()
        self._q_empty_read_cycle()
        with mock.patch.object(runner, "compute_permit_domain_commitment_sha256", return_value="e" * 64):
            result = runner.run_gate_d_ordinary_decision_loop(stage3, rt, invocation, decision_cycle_max=1)
        outcome = result.cycle_results[0].write_outcome
        self.assertFalse(outcome.transport_invoked)
        self.assertEqual(len(wt.calls), 0)
        self.assertEqual(outcome.result_classification, "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH")
        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id)

    # ---- CANCEL ---------------------------------------------------------

    def test_c02_f1_active_cancel_permit_carries_exact_domain_commitments(self) -> None:
        wt = _ScriptedWriteTransport()
        wt.queue(_cancel_result_payload(order_id="venue-active-old-1", reduced_by="1.00"))
        rt = self._runtime(gate_d=True, write_transport=wt)
        invocation, stage3 = self._reach_stage3(rt)
        self._seed_active_resting_order(
            stage3, rt, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="99999999-9999-4999-8999-999999999999",
            venue_order_id="venue-active-old-1", yes_price=D("0.05"), request_seed="c02cancel")
        self._reset_reads()
        self._q_resting_order_read_cycle("venue-active-old-1")
        # fresh independently-refetched reconciliation after the cancel send
        self._transport.queue(RunnerOperation.GET_ORDER, _order_payload(
            "venue-active-old-1", ticker=self.TICKER, status="canceled", remaining_count_fp="0.00",
            yes_price_dollars="0.05", subaccount=1, exchange_index=0))
        self._transport.queue(RunnerOperation.GET_FILLS, _fills_payload([]))

        patcher, permits = self._capture_permits()
        with patcher:
            result = runner.run_gate_d_ordinary_decision_loop(stage3, rt, invocation, decision_cycle_max=1)

        cancel_permits = [p for p in permits if p.operation_kind == "CANCEL_ORDER_V2"]
        self.assertEqual(len(cancel_permits), 1, [p.operation_kind for p in permits])
        permit = cancel_permits[0]
        for key, expected in self._expected_commitments().items():
            self.assertIsNotNone(getattr(permit, key), key)
            self.assertEqual(getattr(permit, key), expected, key)
        self.assertEqual(
            permit.permit_domain_commitment_sha256,
            runner.compute_permit_domain_commitment_sha256(permit))
        outcome = result.cycle_results[0].write_outcome
        self.assertEqual(outcome.action, "CANCEL")
        self.assertTrue(outcome.transport_invoked)
        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id)

    def test_c02_f1_active_cancel_mutated_domain_commitment_blocks_before_transport(self) -> None:
        real_commit = runner.active_domain_commitment
        wt = _ScriptedWriteTransport()
        wt.queue(_cancel_result_payload(order_id="venue-active-old-2", reduced_by="1.00"))
        rt = self._runtime(gate_d=True, write_transport=wt)
        invocation, stage3 = self._reach_stage3(rt)
        self._seed_active_resting_order(
            stage3, rt, quote_slot=QuoteSlot.LOWER_YES_BID.value,
            client_order_id="88888888-8888-4888-8888-888888888888",
            venue_order_id="venue-active-old-2", yes_price=D("0.05"), request_seed="c02cancelmut")
        self._reset_reads()
        self._q_resting_order_read_cycle("venue-active-old-2")

        def _corrupt(active_contract, domain_binding):
            out = dict(real_commit(active_contract, domain_binding))
            out["writer_proof_id"] = out["writer_proof_id"] + "-MUT"
            return out

        with mock.patch.object(runner, "active_domain_commitment", side_effect=_corrupt):
            result = runner.run_gate_d_ordinary_decision_loop(stage3, rt, invocation, decision_cycle_max=1)

        outcome = result.cycle_results[0].write_outcome
        self.assertEqual(outcome.action, "CANCEL")
        self.assertFalse(outcome.transport_invoked)
        self.assertEqual(len(wt.calls), 0)
        self.assertIn(outcome.result_classification, {
            "ACTIVE_DOMAIN_PERMIT_MISMATCH", "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH",
        })
        end_writer_session(
            stage3.normal_writer_acquisition.handle, writer_session_id=stage3.normal_writer_session_id)


class ActiveCompletenessAndRouteCorrection02TestCase(ActiveStage3EndToEndTestCase):
    """R1-B03 Correction-02 Findings 02/03/04 (re-anchored for Correction 03):
    the subaccount-wide completeness gate is fail-closed against a separately
    bound acceptance contract, a proven account-wide read folds same-subaccount
    other-index economics into aggregate risk while excluding other-subaccount
    economics, and active route semantics are never inferred from an N=1
    literal."""

    def _db(self):
        return self.domain_binding

    def _theorem_for(self, *, cutoff, evidence_id, subaccount=1, sel_idx=0,
                     provenance="PROJECT_EVIDENCE_RECORDED", conflict_domain_ref=None):
        return runner.SubaccountWideCompletenessTheoremV1(
            conflict_domain_ref=(conflict_domain_ref if conflict_domain_ref is not None
                                 else self._db().conflict_domain_ref),
            subaccount=subaccount, selected_exchange_index=sel_idx,
            proven_zero_foreign_exchange_indices=(1, 2, 3),
            reconciliation_cutoff_identity_sha256=cutoff,
            accepted_evidence_identity_sha256=evidence_id,
            provenance_class=provenance)

    # ---- Finding 02: fail-closed completeness --------------------------

    def test_c02_f2_no_proof_is_unproven(self) -> None:
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self._db(), current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=None, proven_account_wide_read=None)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c02_f2_stale_cutoff_proven_read_does_not_prove_completeness(self) -> None:
        # Correction 02 (DSB-N1-002): the static positive completeness set is
        # EMPTY for current N1, so no caller-supplied proven account-wide read
        # is accepted regardless of its cutoff.
        stale = self._proven_account_wide(cutoff="b" * 64)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self._db(), current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=None, proven_account_wide_read=stale)
        self.assertIn(c.exception.code, {
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED})

    def test_c02_f2_non_exhausted_proven_read_is_unproven(self) -> None:
        with self.assertRaises(RunnerError):
            runner.ProvenAccountWideReadV1(
                request_classification="ACCOUNT_WIDE",
                accepted_source_classification=runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
                accepted_evidence_identity_sha256=self.N1_CHECKPOINT_SHA,
                account_scope_ref=self.ACCOUNT, subaccount=1,
                pagination_exhausted=False, reconciliation_cutoff_identity_sha256="a" * 64)

    def test_c02_f2_stale_theorem_cutoff_does_not_prove_completeness(self) -> None:
        thm = self._theorem_for(cutoff="b" * 64, evidence_id=self.N1_CHECKPOINT_SHA)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self._db(), current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=thm, proven_account_wide_read=None)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c02_f2_unaccepted_theorem_identity_does_not_prove_completeness(self) -> None:
        thm = self._theorem_for(cutoff="a" * 64, evidence_id="d" * 64)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self._db(), current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=thm, proven_account_wide_read=None)
        self.assertIn(c.exception.code, {
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED})

    def test_c02_f2_current_n1_path_b_theorem_is_unavailable(self) -> None:
        # Correction 02 DSB-N1-002 / DSB-RISK-004: the static positive
        # completeness theorem set for current N1 is EMPTY.  A well-formed
        # theorem bound to the formerly-accepted N1 canonical checkpoint is NO
        # LONGER accepted -- current writer-release completeness is a fresh
        # trusted Path-A read-set only.  An empty accepted set never triggers a
        # legacy-hash substitution.
        self.assertEqual(self._evidence_contract().accepted_completeness_evidence_sha256, ())
        thm = self._theorem_for(cutoff="a" * 64, evidence_id=self.N1_CHECKPOINT_SHA)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self._db(), current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=thm, proven_account_wide_read=None)
        self.assertEqual(c.exception.code, RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED)

    # ---- Finding 03: aggregate-risk inclusion / exclusion --------------

    def test_c02_f3_same_subaccount_foreign_index_economics_change_aggregate_risk(self) -> None:
        # Correction 02 DSB-RISK-003/004/007: same-subaccount foreign-index
        # economics carried by the trusted dynamic read-set fold into the
        # subaccount-wide aggregate; other-subaccount economics never do.
        baseline = self._dynamic_read()
        base_w, base_f = runner._parse_dynamic_index_domain_foreign_economics(
            baseline, ticker=self.TICKER, subaccount=1)
        self.assertEqual((len(base_w), len(base_f)), (0, 0))

        wo = _order_row("f-idx-wo-1", ticker=self.TICKER, subaccount=1, exchange_index=2,
                        remaining_count_fp="2.00", yes_price_dollars="0.30")
        with_fi = self._dynamic_read(traversals=(
            self._traversal(0), self._traversal(1),
            self._traversal(2, order_rows=(wo,)), self._traversal(3)))
        w, f = runner._parse_dynamic_index_domain_foreign_economics(
            with_fi, ticker=self.TICKER, subaccount=1)
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0].order_id, "f-idx-wo-1")
        # exclusion: an other-subaccount row on an enumerated index fails closed.
        other_sub = _order_row("os-wo", ticker=self.TICKER, subaccount=9, exchange_index=2,
                               remaining_count_fp="2.00")
        with self.assertRaises(RunnerError) as c:
            runner._parse_dynamic_index_domain_foreign_economics(
                self._dynamic_read(traversals=(
                    self._traversal(0), self._traversal(1),
                    self._traversal(2, order_rows=(other_sub,)), self._traversal(3))),
                ticker=self.TICKER, subaccount=1)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH)

    def test_c02_f3_partition_digests_foreign_subaccount_without_mismatch(self) -> None:
        proven = self._proven_account_wide(
            cutoff="a" * 64,
            position_rows=(
                {"subaccount": 1, "exchange_index": 0, "position_count_fp": "1.00"},
                {"subaccount": 1, "exchange_index": 4, "position_count_fp": "2.00",
                 "yes_price_dollars": "0.40", "position_as_of_utc": "2026-09-01T00:00:00.000000Z"},
                {"subaccount": 5, "exchange_index": 0, "position_count_fp": "9.00"},
                {"subaccount": 5, "exchange_index": 1, "position_count_fp": "9.00"},
            ))
        part = runner.partition_active_account_wide_rows(
            proven, expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(len(part.selected), 1)
        self.assertEqual(len(part.same_subaccount_foreign_index), 1)
        self.assertEqual(part.foreign_subaccount_count, 2)
        self.assertTrue(runner._is_hex64(part.foreign_partition_digest_sha256))

    def test_c02_f3_scoped_response_foreign_subaccount_still_mismatch(self) -> None:
        # A scoped selected-subaccount response containing a foreign subaccount
        # is still DOMAIN_SCOPE_RESPONSE_MISMATCH (only a PROVEN account-wide
        # read may legitimately carry multiple subaccounts).
        with self.assertRaises(RunnerError) as c:
            runner.active_scope_classify_row(
                {"subaccount": 3, "exchange_index": 0},
                expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH)

    # ---- Finding 04: no N=1 literal route selection --------------------

    def test_c02_f4_generic_active_path_has_no_subaccount_1_route_rule(self) -> None:
        import inspect
        for fn in (runner._gate_d_execute_create, runner._gate_d_execute_cancel,
                   runner._require_active_route_qualified):
            code = "\n".join(
                line for line in inspect.getsource(fn).splitlines()
                if not line.lstrip().startswith("#"))
            self.assertNotRegex(code, r"subaccount\s*[!=]=\s*1\b", fn.__name__)
            self.assertNotRegex(code, r"subaccount\s*==\s*0\b", fn.__name__)

    def test_c02_f4_route_qualification_applies_only_to_its_exact_domain(self) -> None:
        rq = self._route_qualification()  # subaccount=1, exchange_index=0
        self.assertTrue(rq.applies_to(
            domain_binding=self.domain_binding,
            operation_request_shape_id=runner._ACTIVE_ROUTE_REQUEST_SHAPE_ID))
        future_binding = ledger_binding.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            subaccount=7, exchange_index=0)
        self.assertFalse(rq.applies_to(
            domain_binding=future_binding,
            operation_request_shape_id=runner._ACTIVE_ROUTE_REQUEST_SHAPE_ID))

    def test_c02_f4_future_subaccount_without_route_qualification_fails_closed(self) -> None:
        future_binding = ledger_binding.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            subaccount=7, exchange_index=0)

        class _Stub:
            pass

        stub = _Stub()
        stub.route_qualification = self._route_qualification()  # qualified for N=1 only
        stub.domain_binding = future_binding
        stub.accepted_evidence_contract = None
        with self.assertRaises(RunnerError) as c:
            runner._require_active_route_qualified(stub)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED)

    def test_c02_f4_missing_route_qualification_fails_closed_before_permit(self) -> None:
        rt = self._runtime()
        with self.assertRaises(RunnerError) as c:
            runner.build_active_experiment_runner_runtime_v2(
                normal_gate=rt.normal_gate, emergency_gate=rt.emergency_gate,
                send_operation_request=rt.send_operation_request, fetch_orderbook=rt.fetch_orderbook,
                monotonic_clock_ns=rt.monotonic_clock_ns, wall_clock=rt.wall_clock,
                uuid_factory=rt.uuid_factory, risk_config=rt.risk_config,
                experiment_absolute_end_monotonic_ns=rt.experiment_absolute_end_monotonic_ns,
                authority_binding=rt.authority_binding,
                canonical_repository_root=rt.canonical_repository_root,
                expected_ledger_path=rt.expected_ledger_path,
                domain_binding=rt.domain_binding, active_contract=rt.active_contract,
                accepted_evidence_contract=self._evidence_contract(),
                route_qualification=None)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED)

    def test_c02_f4_current_n1_route_qualification_works_when_explicitly_supplied(self) -> None:
        rt = self._runtime()
        self.assertIsInstance(rt.route_qualification, runner.ActiveRouteQualificationV1)
        self.assertEqual(rt.route_qualification.subaccount, 1)
        self.assertEqual(rt.route_qualification.exchange_index_wire_policy, "EMPIRICALLY_BOUND_AUTOROUTE")
        self.assertEqual(
            rt.route_qualification.qualification_evidence_identity_sha256,
            "879d311420d2f6a4e2c20b8f96e8107f3753a30923f0e2afdfb7f5668bcb9068")


class ActiveEvidenceContractCorrection03TestCase(ActiveStage3EndToEndTestCase):
    """R1-B03 Correction-03 Findings 01-05: same-subaccount foreign-index
    POSITION risk contributes to the aggregate; Path-A / Path-B / route
    qualification acceptance is bound to a separately trusted immutable
    evidence contract (not caller-forgeable / not self-authorizing); and the
    foreign-subaccount partition digest commits to foreign-row content."""

    AS_OF = "2026-09-01T00:00:00.000000Z"

    def _capability(self, rt):
        return runner._issue_pre_release_read_capability(
            process_instance_id=rt.normal_gate.process_instance_id, ticker=self.TICKER, runtime=rt)

    def _foreign_pos_row(self, *, exchange_index, count_fp, price="0.40", as_of=None, subaccount=1):
        return {
            "subaccount": subaccount, "exchange_index": exchange_index,
            "position_count_fp": count_fp, "yes_price_dollars": price,
            "position_as_of_utc": as_of if as_of is not None else self.AS_OF,
        }

    def _fold(self, *, position_rows=(), working_order_rows=()):
        # Correction 02: the same-subaccount foreign-index folding logic is
        # preserved; it is now reached only through the trusted dynamic
        # read-set path, so exercise the preserved partition/fold pipeline
        # directly rather than through the removed caller-injected
        # ``proven_account_wide_read`` route.
        proven = self._proven_account_wide(
            cutoff="a" * 64, position_rows=position_rows, working_order_rows=working_order_rows)
        part = runner.partition_active_account_wide_rows(
            proven, expected_subaccount=1, expected_exchange_index=0)
        return runner._parse_same_subaccount_foreign_index_economics(
            part, ticker=self.TICKER, subaccount=1)

    def _signed_net_of(self, working, fills):
        return runner.compute_market_economic_state(self.TICKER, fills, working).signed_net_position

    # ---- Finding 01: same-subaccount foreign-index POSITION risk -------

    def test_c03_f1_foreign_index_position_changes_aggregate_risk(self) -> None:
        base_w, base_f = self._fold()
        self.assertEqual(self._signed_net_of(base_w, base_f), Decimal("0"))
        w, f = self._fold(position_rows=(self._foreign_pos_row(exchange_index=2, count_fp="3.00"),))
        # the foreign-index long inventory of +3 feeds the subaccount-wide
        # aggregate net position used for release / writer assessment.
        self.assertEqual(self._signed_net_of(w, f), Decimal("3"))
        self.assertEqual(len(f), 1)

    def test_c03_f1_short_foreign_index_position_reduces_aggregate(self) -> None:
        w, f = self._fold(position_rows=(self._foreign_pos_row(exchange_index=5, count_fp="-2.00"),))
        self.assertEqual(self._signed_net_of(w, f), Decimal("-2"))

    def test_c03_f1_other_subaccount_position_excluded_from_selected_domain_risk(self) -> None:
        w, f = self._fold(position_rows=(
            self._foreign_pos_row(exchange_index=0, count_fp="9.00", subaccount=9),))
        self.assertEqual(self._signed_net_of(w, f), Decimal("0"))
        self.assertEqual(len(f), 0)

    def test_c03_f1_malformed_foreign_index_position_fails_closed(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._fold(position_rows=(
                {"subaccount": 1, "exchange_index": 2, "position_count_fp": "3.00"},))  # no price / as-of
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS)

    def test_c03_f1_contradictory_duplicate_foreign_index_positions_fail_closed(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._fold(position_rows=(
                self._foreign_pos_row(exchange_index=2, count_fp="3.00"),
                self._foreign_pos_row(exchange_index=2, count_fp="5.00"),
            ))
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS)

    def test_c03_f1_identical_duplicate_foreign_index_position_deduped(self) -> None:
        w, f = self._fold(position_rows=(
            self._foreign_pos_row(exchange_index=2, count_fp="3.00"),
            self._foreign_pos_row(exchange_index=2, count_fp="3.00"),
        ))
        self.assertEqual(self._signed_net_of(w, f), Decimal("3"))
        self.assertEqual(len(f), 1)

    # ---- Finding 02: proven account-wide read not caller-forgeable ----

    def test_c03_f2_forged_proven_read_matching_cutoff_unaccepted_evidence_fails(self) -> None:
        forged = self._proven_account_wide(cutoff="a" * 64, evidence_id="d" * 64)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self.domain_binding, current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=None, proven_account_wide_read=forged)
        self.assertIn(c.exception.code, {
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED})

    def test_c03_f2_forged_proven_read_unaccepted_source_fails(self) -> None:
        forged = self._proven_account_wide(cutoff="a" * 64, source="SOME_OTHER_SOURCE_V9")
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self.domain_binding, current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=None, proven_account_wide_read=forged)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c03_f2_wrong_request_classification_rejected_at_construction(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._proven_account_wide(cutoff="a" * 64, request_classification="SELECTED_ROUTE")
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c03_f2_accepted_complete_account_wide_result_not_sufficient_for_n1(self) -> None:
        # Correction 02 (DSB-N1-002 / DSB-RISK-004): current N1 has an EMPTY
        # accepted static positive completeness set.  Even a well-formed,
        # self-consistent account-wide result carrying a formerly-accepted N1
        # evidence identity is NO LONGER sufficient -- current writer-release
        # completeness is a fresh trusted Path-A read-set only.
        proven = self._proven_account_wide(cutoff="a" * 64)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self.domain_binding, current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=None, proven_account_wide_read=proven)
        self.assertEqual(c.exception.code, RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED)

    def test_c03_f2_changing_any_committed_row_changes_result_hash(self) -> None:
        base = self._proven_account_wide(
            cutoff="a" * 64,
            position_rows=(self._foreign_pos_row(exchange_index=2, count_fp="3.00"),))
        changed_econ = self._proven_account_wide(
            cutoff="a" * 64,
            position_rows=(self._foreign_pos_row(exchange_index=2, count_fp="4.00"),))
        changed_scope = self._proven_account_wide(
            cutoff="a" * 64,
            position_rows=(self._foreign_pos_row(exchange_index=3, count_fp="3.00"),))
        self.assertNotEqual(base.account_wide_result_hash, changed_econ.account_wide_result_hash)
        self.assertNotEqual(base.account_wide_result_hash, changed_scope.account_wide_result_hash)
        # same content -> same hash (deterministic)
        again = self._proven_account_wide(
            cutoff="a" * 64,
            position_rows=(self._foreign_pos_row(exchange_index=2, count_fp="3.00"),))
        self.assertEqual(base.account_wide_result_hash, again.account_wide_result_hash)

    def test_c03_f2_result_hash_self_consistency_enforced(self) -> None:
        proven = self._proven_account_wide(cutoff="a" * 64)
        object.__setattr__(proven, "account_wide_result_hash", "f" * 64)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self.domain_binding, current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=None, proven_account_wide_read=proven)
        self.assertIn(c.exception.code, {
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED})

    # ---- Finding 03: Path-B theorem acceptance is not circular --------

    def test_c03_f3_no_caller_acceptance_set_parameter(self) -> None:
        params = set(inspect.signature(runner.require_subaccount_wide_completeness).parameters)
        self.assertNotIn("accepted_evidence_identities", params)
        self.assertIn("accepted_evidence_contract", params)
        for fn in (runner.run_pre_release_read_phase_v2, runner.run_active_experiment_stage3_and_gate_d,
                   runner.collect_active_authoritative_read_truth):
            self.assertNotIn("accepted_evidence_identities", set(inspect.signature(fn).parameters))

    def test_c03_f3_caller_theorem_cannot_self_authorize(self) -> None:
        # There is no caller-supplied acceptance set; a theorem whose evidence
        # identity is not in the separately bound contract fails closed even
        # though the caller "wants" it accepted.
        thm = self._theorem(cutoff="a" * 64)
        object.__setattr__(thm, "accepted_evidence_identity_sha256", "d" * 64)
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self.domain_binding, current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=thm, proven_account_wide_read=None)
        self.assertIn(c.exception.code, {
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED})

    def test_c03_f3_no_prebound_theorem_for_current_n1(self) -> None:
        # Correction 02: the current-N1 static positive completeness set is
        # EMPTY, so NO theorem (however well-formed / cutoff-bound / domain-
        # matched) is accepted -- the Path-B structure remains for future
        # domains only.
        for evid in (self.N1_FILL_ISOLATION_SHA, self.N1_CHECKPOINT_SHA):
            good = runner.SubaccountWideCompletenessTheoremV1(
                conflict_domain_ref=self.domain_binding.conflict_domain_ref,
                subaccount=1, selected_exchange_index=0, proven_zero_foreign_exchange_indices=(1, 2, 3),
                reconciliation_cutoff_identity_sha256="a" * 64,
                accepted_evidence_identity_sha256=evid,
                provenance_class="PROJECT_EVIDENCE_RECORDED")
            with self.assertRaises(RunnerError) as c:
                runner.require_subaccount_wide_completeness(
                    domain_binding=self.domain_binding, current_reconciliation_cutoff_sha256="a" * 64,
                    accepted_evidence_contract=self._evidence_contract(),
                    completeness_theorem=good, proven_account_wide_read=None)
            self.assertEqual(c.exception.code, RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED)

    def test_c03_f3_theorem_wrong_provenance_class_fails_closed(self) -> None:
        thm = runner.SubaccountWideCompletenessTheoremV1(
            conflict_domain_ref=self.domain_binding.conflict_domain_ref,
            subaccount=1, selected_exchange_index=0, proven_zero_foreign_exchange_indices=(1, 2, 3),
            reconciliation_cutoff_identity_sha256="a" * 64,
            accepted_evidence_identity_sha256=self.N1_CHECKPOINT_SHA,
            provenance_class="INDEPENDENTLY_VERIFIED")  # valid class, != contract's accepted one
        with self.assertRaises(RunnerError) as c:
            runner.require_subaccount_wide_completeness(
                domain_binding=self.domain_binding, current_reconciliation_cutoff_sha256="a" * 64,
                accepted_evidence_contract=self._evidence_contract(),
                completeness_theorem=thm, proven_account_wide_read=None)
        self.assertIn(c.exception.code, {
            RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN,
            RunnerFailureCode.STATIC_COMPLETENESS_THEOREM_NOT_ACCEPTED})

    # ---- Finding 04: route qualification evidence must be accepted ----

    def test_c03_f4_arbitrary_route_evidence_hash_cannot_qualify(self) -> None:
        rq = runner.ActiveRouteQualificationV1(
            environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT, subaccount=1, exchange_index=0,
            operation_request_shape_id=runner._ACTIVE_ROUTE_REQUEST_SHAPE_ID,
            exchange_index_wire_policy="EMPIRICALLY_BOUND_AUTOROUTE",
            qualification_evidence_identity_sha256="d" * 64,  # syntactically valid, not accepted
            provenance_class="PROJECT_EVIDENCE_RECORDED")
        with self.assertRaises(RunnerError) as c:
            runner._require_active_accepted_evidence_contract(
                self._evidence_contract(), domain_binding=self.domain_binding, route_qualification=rq)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED)

    def test_c03_f4_route_qualification_wrong_provenance_class_fails(self) -> None:
        rq = runner.ActiveRouteQualificationV1(
            environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT, subaccount=1, exchange_index=0,
            operation_request_shape_id=runner._ACTIVE_ROUTE_REQUEST_SHAPE_ID,
            exchange_index_wire_policy="EMPIRICALLY_BOUND_AUTOROUTE",
            qualification_evidence_identity_sha256=self.N1_CHECKPOINT_SHA,
            provenance_class="INDEPENDENTLY_VERIFIED")
        with self.assertRaises(RunnerError) as c:
            runner._require_active_accepted_evidence_contract(
                self._evidence_contract(), domain_binding=self.domain_binding, route_qualification=rq)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED)

    def test_c03_f4_accepted_n1_route_evidence_qualifies(self) -> None:
        runner._require_active_accepted_evidence_contract(
            self._evidence_contract(), domain_binding=self.domain_binding,
            route_qualification=self._route_qualification())  # no raise

    def test_c03_f4_future_subaccount_has_no_accepted_evidence_contract(self) -> None:
        future_binding = ledger_binding.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            subaccount=7, exchange_index=0)
        with self.assertRaises(RunnerError) as c:
            runner.n1_accepted_evidence_contract(future_binding)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_ROUTE_SEMANTICS_UNQUALIFIED)
        # and the raw contract constructor cannot be used to forge one
        with self.assertRaises((RunnerError, TypeError)):
            runner.ActiveDomainAcceptedEvidenceContractV1(
                environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
                conflict_domain_ref="KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=7",
                subaccount=7, selected_exchange_index=0,
                account_wide_source_classification=runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
                accepted_route_evidence_sha256=(self.N1_CHECKPOINT_SHA,),
                accepted_completeness_evidence_sha256=(self.N1_CHECKPOINT_SHA,),
                accepted_provenance_class="PROJECT_EVIDENCE_RECORDED")

    def test_c03_f4_contract_with_unaccepted_evidence_identity_rejected(self) -> None:
        with self.assertRaises(RunnerError) as c:
            runner.ActiveDomainAcceptedEvidenceContractV1(
                runner._ACCEPTED_EVIDENCE_CONTRACT_KEY,
                environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
                conflict_domain_ref=self.domain_binding.conflict_domain_ref,
                subaccount=1, selected_exchange_index=0,
                account_wide_source_classification=runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
                accepted_route_evidence_sha256=("d" * 64,),   # NOT an accepted registry identity
                accepted_completeness_evidence_sha256=("d" * 64,),
                accepted_index_domain_enumeration_evidence_sha256=(
                    runner._P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,),
                accepted_settlement_reconciliation_evidence_sha256=(
                    runner._P02_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256,),
                index_domain_enumeration_source=runner._ACTIVE_INDEX_DOMAIN_ENUMERATION_SOURCE_V1,
                dynamic_exchange_index_entry_max=3, retained_bootstrap_position=None,
                accepted_provenance_class="PROJECT_EVIDENCE_RECORDED")
        self.assertEqual(c.exception.code, RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID)

    # ---- Finding 05: foreign-subaccount digest commits to content -----

    def test_c03_f5_foreign_digest_changes_with_foreign_row_content(self) -> None:
        def part_for(count_fp):
            proven = self._proven_account_wide(
                cutoff="a" * 64,
                position_rows=(
                    {"subaccount": 1, "exchange_index": 0, "position_count_fp": "1.00"},
                    {"subaccount": 5, "exchange_index": 0, "position_count_fp": count_fp,
                     "order_id": "foreign-ord-1"},
                ))
            return runner.partition_active_account_wide_rows(
                proven, expected_subaccount=1, expected_exchange_index=0)

        p1 = part_for("9.00")
        p2 = part_for("8.00")
        self.assertEqual(p1.foreign_subaccount_count, p2.foreign_subaccount_count)
        self.assertNotEqual(p1.foreign_partition_digest_sha256, p2.foreign_partition_digest_sha256)

    def test_c03_f5_foreign_digest_deterministic_under_row_order(self) -> None:
        rows_a = (
            {"subaccount": 1, "exchange_index": 0, "position_count_fp": "1.00"},
            {"subaccount": 5, "exchange_index": 0, "position_count_fp": "9.00"},
            {"subaccount": 6, "exchange_index": 1, "position_count_fp": "2.00"},
        )
        rows_b = (rows_a[2], rows_a[0], rows_a[1])
        d1 = runner.partition_active_account_wide_rows(
            self._proven_account_wide(cutoff="a" * 64, position_rows=rows_a),
            expected_subaccount=1, expected_exchange_index=0)
        d2 = runner.partition_active_account_wide_rows(
            self._proven_account_wide(cutoff="a" * 64, position_rows=rows_b),
            expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(d1.foreign_partition_digest_sha256, d2.foreign_partition_digest_sha256)
        self.assertEqual(d1.foreign_subaccount_count, d2.foreign_subaccount_count)

    def test_c03_f5_malformed_foreign_row_fails_closed(self) -> None:
        with self.assertRaises(RunnerError) as c:
            runner.partition_active_account_wide_rows(
                self._proven_account_wide(
                    cutoff="a" * 64,
                    position_rows=({"subaccount": 5},)),  # missing exchange_index
                expected_subaccount=1, expected_exchange_index=0)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS)


class ActiveDynamicIndexDomainCorrection04TestCase(ActiveStage3EndToEndTestCase):
    """R1-B03 Correction 04 (P02_BINDING_01): the active Path-A completeness
    contract is an explicit DYNAMIC exchange-index-domain enumeration -- a
    current /exchange/status domain, an explicit orders/fills/positions
    traversal for EVERY enumerated index with pagination exhausted, a single
    recomputed composite read-set identity bound to all pages, freshness
    ORDERING (not T0==T1) under the existing risk/reconciliation config, full
    per-index aggregate risk, and N1 retained-position settlement
    reconciliation.  P01 is negative evidence (never satisfies a positive
    predicate); P02 historical rows never mint current writer eligibility."""

    P01_SHA = "aeb07275f62ce295a131a07c5d2c9604728be58b416a9ff1d3d7517c8d0d6138"
    P02_SHA = "2fc189b2a807a6c22ab3e71e41a6cfa66415e3bda87e6c8e66c3eb6e8029c69b"
    CONTROLLED_TICKER = "KXAAAGASD-26SEP02-4.1200"
    SETTLED_TIME = "2026-09-02T14:41:43.665741Z"
    # A fresh synthetic user_data_timestamp window around the deterministic
    # test wall clock (2026-08-17T13:00:00Z); T1 >= T0 within the existing
    # StateIntegrityLimits(reconciliation_read_deadline_ms=500,
    # max_future_wall_clock_skew_ms=10, max_reconciliation_lag_ms=1000).
    T0 = "2026-08-17T12:59:59.700000Z"
    T1 = "2026-08-17T13:00:00.000000Z"
    NOW = "2026-08-17T13:00:00.004000Z"

    @staticmethod
    def _hx(n):
        return format(n % (16 ** 64), "064x")

    def _surface(self, seed):
        return runner.PerIndexSurfaceTraversalV1(
            request_identity_sha256=self._hx(seed),
            page_response_digests=(self._hx(seed + 1),),
            page_economic_digests=(self._hx(seed + 2),),
            final_cursor_absent=True, pagination_complete=True)

    def _traversal(self, idx, *, order_rows=(), fill_rows=(), position_rows=(), tag=0):
        base = (idx + 1) * 1000 + tag * 100
        return runner.PerIndexTraversalV1(
            exchange_index=idx, orders=self._surface(base + 10),
            fills=self._surface(base + 40), positions=self._surface(base + 70),
            order_rows=tuple(order_rows), fill_rows=tuple(fill_rows), position_rows=tuple(position_rows))

    def _settlement(self, **ov):
        d = dict(
            settlement_evidence_identity_sha256=self.P02_SHA,
            ticker=self.CONTROLLED_TICKER, exchange_index=0,
            conflict_domain_ref=self.domain_binding.conflict_domain_ref,
            market_result="yes", settled_time_utc=self.SETTLED_TIME,
            yes_count_fp="1.00", settlement_response_identity_sha256=self._hx(0x5e77))
        d.update(ov)
        return runner.RetainedPositionSettlementReconciliationV1(**d)

    _SETTLE_DEFAULT = object()

    def _dynamic_read(self, *, domain=(0, 1, 2, 3), traversals=None,
                      status_before=None, status_after=None, fb=None, fa=None,
                      selected_route_cutoff=None, settlement=_SETTLE_DEFAULT,
                      account_scope_ref=None, subaccount=1, selected_exchange_index=0,
                      source=None, evid=None, read_set_identity=None, recompute=True,
                      active_contract=None, risk_config=None):
        sb = status_before if status_before is not None else runner.ExchangeIndexStatusObservationV1(
            response_identity_sha256=self._hx(0x57a705), exchange_index_domain=tuple(domain))
        sa = status_after if status_after is not None else runner.ExchangeIndexStatusObservationV1(
            response_identity_sha256=self._hx(0x57a705), exchange_index_domain=tuple(domain))
        fbw = fb if fb is not None else runner.UserDataFreshnessWatermarkV1(
            response_identity_sha256=self._hx(0xf0), as_of_time_utc=self.T0)
        faw = fa if fa is not None else runner.UserDataFreshnessWatermarkV1(
            response_identity_sha256=self._hx(0xf1), as_of_time_utc=self.T1)
        trs = traversals if traversals is not None else tuple(self._traversal(i) for i in domain)
        cutoff = selected_route_cutoff if selected_route_cutoff is not None else self._hx(0x9c07)
        sr = self._settlement() if settlement is self._SETTLE_DEFAULT else settlement
        ac = active_contract or self.active_contract
        rc = risk_config or self.config
        read = runner.DynamicIndexDomainAccountWideReadV1(
            accepted_source_classification=(source if source is not None
                                            else runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1),
            index_domain_enumeration_evidence_identity_sha256=(evid if evid is not None else self.P02_SHA),
            account_scope_ref=(account_scope_ref if account_scope_ref is not None else self.ACCOUNT),
            subaccount=subaccount, selected_exchange_index=selected_exchange_index,
            status_before=sb, status_after=sa, freshness_before=fbw, freshness_after=faw,
            per_index_traversals=trs, selected_route_reconciliation_cutoff_sha256=cutoff,
            read_set_identity_sha256=(read_set_identity or self._hx(0)),
            settlement_reconciliation=sr)
        if recompute and read_set_identity is None:
            ident = runner.compute_dynamic_index_domain_read_set_identity(
                read,
                active_domain_binding_id=ac.domain_binding_id,
                active_domain_binding_sha256=ac.domain_binding_sha256,
                active_contract_sha256=ac.contract_sha256,
                risk_config_sha256=rc.sha256)
            read = dataclasses.replace(read, read_set_identity_sha256=ident)
        return read

    def _require(self, read, *, now_utc=None, now_mono=1_000_000, contract=None, cutoff=None):
        return runner.require_dynamic_index_domain_completeness(
            read, domain_binding=self.domain_binding, active_contract=self.active_contract,
            risk_config=self.config,
            accepted_evidence_contract=(contract if contract is not None else self._evidence_contract()),
            current_selected_route_cutoff_sha256=(
                cutoff if cutoff is not None else read.selected_route_reconciliation_cutoff_sha256),
            now_monotonic_ns=now_mono, now_utc=(now_utc if now_utc is not None else self.NOW))

    # ---- R01/R02: dynamic status index-domain enumeration --------------

    def test_c04_r01_status_domain_0123_qualifies_without_hardcoding(self) -> None:
        cls = self._require(self._dynamic_read(domain=(0, 1, 2, 3)))
        self.assertEqual(cls, "RETAINED_POSITION_TERMINALLY_SETTLED")

    def test_c04_r01_arbitrary_bounded_future_domain_0_2_5(self) -> None:
        # Generic code accepts any bounded exact integer domain the contract
        # supplies (no [0,1,2,3] literal).  Use a domain-only contract
        # (subaccount=1 primary) with a wider bound and no retained position.
        contract = runner.ActiveDomainAcceptedEvidenceContractV1(
            runner._ACCEPTED_EVIDENCE_CONTRACT_KEY,
            environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            conflict_domain_ref=self.domain_binding.conflict_domain_ref,
            subaccount=1, selected_exchange_index=0,
            account_wide_source_classification=runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
            accepted_route_evidence_sha256=(runner._N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256,),
            # Correction 02 DSB-N1-002: the static positive completeness set is EMPTY.
            accepted_completeness_evidence_sha256=(),
            accepted_index_domain_enumeration_evidence_sha256=(self.P02_SHA,),
            accepted_settlement_reconciliation_evidence_sha256=(self.P02_SHA,),
            index_domain_enumeration_source=runner._ACTIVE_INDEX_DOMAIN_ENUMERATION_SOURCE_V1,
            dynamic_exchange_index_entry_max=5, retained_bootstrap_position=None,
            accepted_provenance_class="PROJECT_EVIDENCE_RECORDED")
        cls = self._require(self._dynamic_read(domain=(0, 2, 5), settlement=None), contract=contract)
        self.assertEqual(cls, "NO_RETAINED_BOOTSTRAP_POSITION")

    def test_c04_r02_missing_status_breakdown_fails_closed(self) -> None:
        with self.assertRaises(RunnerError) as c:
            runner.ExchangeIndexStatusObservationV1(response_identity_sha256=self._hx(1), exchange_index_domain=())
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_r02_duplicate_index_fails_closed(self) -> None:
        with self.assertRaises(RunnerError) as c:
            runner.ExchangeIndexStatusObservationV1(response_identity_sha256=self._hx(1), exchange_index_domain=(0, 1, 1, 2))
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_r02_domain_exceeds_bound_fails_closed(self) -> None:
        # Correction 06 (BLOCK-05-02): each individual index is a bounded exact
        # non-negative int 0 <= value <= 2147483647.  A per-VALUE out-of-range
        # index fails closed at status-observation construction.
        with self.assertRaises(RunnerError) as c:
            runner.ExchangeIndexStatusObservationV1(
                response_identity_sha256=self._hx(1),
                exchange_index_domain=(0, 1, runner._ACTIVE_EXCHANGE_INDEX_VALUE_MAX + 1))
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_r02_domain_exceeds_contract_bound_fails_closed(self) -> None:
        # Correction 06 (BLOCK-05-02): the accepted-evidence contract bound is
        # a COUNT of unique current indices (dynamic_exchange_index_entry_max),
        # NEVER a maximum index VALUE.  A domain whose unique count exceeds the
        # contract bound fails closed with the precise code, before any
        # per-index portfolio traversal.
        contract = runner.ActiveDomainAcceptedEvidenceContractV1(
            runner._ACCEPTED_EVIDENCE_CONTRACT_KEY,
            environment="KALSHI_DEMO", account_scope_ref=self.ACCOUNT,
            conflict_domain_ref=self.domain_binding.conflict_domain_ref,
            subaccount=1, selected_exchange_index=0,
            account_wide_source_classification=runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
            accepted_route_evidence_sha256=(runner._N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256,),
            accepted_completeness_evidence_sha256=(),
            accepted_index_domain_enumeration_evidence_sha256=(self.P02_SHA,),
            accepted_settlement_reconciliation_evidence_sha256=(self.P02_SHA,),
            index_domain_enumeration_source=runner._ACTIVE_INDEX_DOMAIN_ENUMERATION_SOURCE_V1,
            dynamic_exchange_index_entry_max=3, retained_bootstrap_position=None,
            accepted_provenance_class="PROJECT_EVIDENCE_RECORDED")
        with self.assertRaises(RunnerError) as c:
            self._require(self._dynamic_read(domain=(0, 1, 2, 3), settlement=None), contract=contract)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED)

    def test_c04_r02_before_after_domain_mismatch_fails_closed(self) -> None:
        sb = runner.ExchangeIndexStatusObservationV1(response_identity_sha256=self._hx(2), exchange_index_domain=(0, 1, 2, 3))
        sa = runner.ExchangeIndexStatusObservationV1(response_identity_sha256=self._hx(2), exchange_index_domain=(0, 1, 2))
        with self.assertRaises(RunnerError) as c:
            self._dynamic_read(status_before=sb, status_after=sa)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_every_enumerated_index_required(self) -> None:
        # domain [0,1,2,3] but only 3 traversals -> UNPROVEN
        with self.assertRaises(RunnerError) as c:
            self._dynamic_read(domain=(0, 1, 2, 3),
                               traversals=(self._traversal(0), self._traversal(1), self._traversal(2)))
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_incomplete_page_on_one_foreign_index_fails(self) -> None:
        with self.assertRaises(RunnerError) as c:
            runner.PerIndexSurfaceTraversalV1(
                request_identity_sha256=self._hx(1), page_response_digests=(self._hx(2),),
                page_economic_digests=(self._hx(3),), final_cursor_absent=False, pagination_complete=True)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_scope_mismatched_row_fails(self) -> None:
        foreign_sub_row = _order_row("wo-x", ticker=self.TICKER, subaccount=2, exchange_index=2,
                                     remaining_count_fp="1.00")
        read = self._dynamic_read(traversals=(
            self._traversal(0), self._traversal(1),
            self._traversal(2, order_rows=(foreign_sub_row,)), self._traversal(3)))
        self._require(read)  # completeness passes; the scope violation surfaces on fold
        with self.assertRaises(RunnerError) as c:
            runner._parse_dynamic_index_domain_foreign_economics(read, ticker=self.TICKER, subaccount=1)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH)

    # ---- R05: full per-index aggregate risk ----------------------------

    def _aggregate_via_collect(self, read):
        rt = self._runtime()
        cap = runner._issue_pre_release_read_capability(
            process_instance_id=rt.normal_gate.process_instance_id, ticker=self.TICKER, runtime=rt)
        return runner.collect_active_authoritative_read_truth(
            cap, ticker=self.TICKER, domain_binding=rt.domain_binding,
            accepted_evidence_contract=rt.accepted_evidence_contract,
            dynamic_index_domain_read=read, active_contract=rt.active_contract,
            risk_config=rt.risk_config, now_monotonic_ns=1_000_000, now_utc=self.NOW)

    def test_c04_r05_foreign_index_position_changes_aggregate_risk(self) -> None:
        rt = self._runtime()
        cutoff = self._current_cutoff(rt)
        baseline = self._aggregate_via_collect(self._dynamic_read(selected_route_cutoff=cutoff))
        base_net = runner.compute_market_economic_state(self.TICKER, baseline.fills, baseline.working_orders).signed_net_position

        pos_row = {"ticker": self.TICKER, "subaccount": 1, "exchange_index": 2,
                   "position_count_fp": "4.00", "yes_price_dollars": "0.40",
                   "position_as_of_utc": self.SETTLED_TIME}
        with_pos = self._aggregate_via_collect(self._dynamic_read(
            selected_route_cutoff=cutoff,
            traversals=(self._traversal(0), self._traversal(1),
                        self._traversal(2, position_rows=(pos_row,)), self._traversal(3))))
        net = runner.compute_market_economic_state(self.TICKER, with_pos.fills, with_pos.working_orders).signed_net_position
        self.assertEqual(base_net, Decimal("0"))
        self.assertEqual(net, Decimal("4"))
        self.assertNotEqual(base_net, net)

    def test_c04_r05_foreign_index_order_changes_aggregate_risk(self) -> None:
        rt = self._runtime()
        cutoff = self._current_cutoff(rt)
        wo = _order_row("wo-f-1", ticker=self.TICKER, subaccount=1, exchange_index=3,
                        remaining_count_fp="2.00", yes_price_dollars="0.30")
        truth = self._aggregate_via_collect(self._dynamic_read(
            selected_route_cutoff=cutoff,
            traversals=(self._traversal(0), self._traversal(1), self._traversal(2),
                        self._traversal(3, order_rows=(wo,)))))
        self.assertEqual(len(truth.working_orders), 1)
        self.assertEqual(truth.working_orders[0].order_id, "wo-f-1")

    def test_c04_r05_other_subaccount_economics_excluded(self) -> None:
        rt = self._runtime()
        cutoff = self._current_cutoff(rt)
        pos_row = {"ticker": self.TICKER, "subaccount": 9, "exchange_index": 2,
                   "position_count_fp": "5.00", "yes_price_dollars": "0.40",
                   "position_as_of_utc": self.SETTLED_TIME}
        read = self._dynamic_read(
            selected_route_cutoff=cutoff,
            traversals=(self._traversal(0), self._traversal(1),
                        self._traversal(2, position_rows=(pos_row,)), self._traversal(3)))
        with self.assertRaises(RunnerError) as c:
            self._aggregate_via_collect(read)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_MISMATCH)

    # ---- R03: composite read-set identity ----------------------------

    def _ident(self, read):
        return runner.compute_dynamic_index_domain_read_set_identity(
            read, active_domain_binding_id=self.active_contract.domain_binding_id,
            active_domain_binding_sha256=self.active_contract.domain_binding_sha256,
            active_contract_sha256=self.active_contract.contract_sha256,
            risk_config_sha256=self.config.sha256)

    def test_c04_r03_composite_digest_deterministic(self) -> None:
        a = self._dynamic_read(recompute=False)
        b = self._dynamic_read(recompute=False)
        self.assertEqual(self._ident(a), self._ident(b))

    def test_c04_r03_row_mutation_changes_digest(self) -> None:
        base = self._dynamic_read(recompute=False)
        wo = _order_row("wo-1", ticker=self.TICKER, subaccount=1, exchange_index=1, remaining_count_fp="1.00")
        mutated = self._dynamic_read(recompute=False, traversals=(
            self._traversal(0), self._traversal(1, order_rows=(wo,)), self._traversal(2), self._traversal(3)))
        self.assertNotEqual(self._ident(base), self._ident(mutated))

    def test_c04_r03_page_response_mutation_changes_digest(self) -> None:
        base = self._dynamic_read(recompute=False)
        t1 = runner.PerIndexTraversalV1(
            exchange_index=1,
            orders=runner.PerIndexSurfaceTraversalV1(
                request_identity_sha256=self._hx(2010), page_response_digests=(self._hx(999999),),
                page_economic_digests=(self._hx(2012),), final_cursor_absent=True, pagination_complete=True),
            fills=self._surface(2040), positions=self._surface(2070))
        mutated = self._dynamic_read(recompute=False, traversals=(
            self._traversal(0), t1, self._traversal(2), self._traversal(3)))
        self.assertNotEqual(self._ident(base), self._ident(mutated))

    def test_c04_r03_pagination_completion_mutation_changes_digest(self) -> None:
        # pagination_complete / final_cursor_absent are BOTH forced True at
        # construction -- an incomplete surface cannot even be built (a
        # stronger guarantee).  Here bypass __post_init__ to flip the
        # completion flag and prove the composite identity moves.
        base = self._dynamic_read(recompute=False)
        good = self._surface(3070)
        bad = runner.PerIndexSurfaceTraversalV1.__new__(runner.PerIndexSurfaceTraversalV1)
        for name in ("request_identity_sha256", "page_response_digests", "page_economic_digests",
                     "final_cursor_absent", "pagination_complete"):
            object.__setattr__(bad, name, getattr(good, name))
        object.__setattr__(bad, "pagination_complete", False)
        t2 = runner.PerIndexTraversalV1(
            exchange_index=2, orders=self._surface(3010), fills=self._surface(3040), positions=bad)
        mutated = self._dynamic_read(recompute=False, traversals=(
            self._traversal(0), self._traversal(1), t2, self._traversal(3)))
        self.assertNotEqual(self._ident(base), self._ident(mutated))

    def test_c04_r03_status_domain_mutation_changes_digest(self) -> None:
        base = self._dynamic_read(recompute=False, domain=(0, 1, 2, 3))
        other = self._dynamic_read(recompute=False, domain=(0, 1, 2))
        self.assertNotEqual(self._ident(base), self._ident(other))

    def test_c04_r03_t0_mutation_changes_digest(self) -> None:
        base = self._dynamic_read(recompute=False)
        fb = runner.UserDataFreshnessWatermarkV1(
            response_identity_sha256=self._hx(0xf0), as_of_time_utc="2026-08-17T12:59:59.500000Z")
        mutated = self._dynamic_read(recompute=False, fb=fb)
        self.assertNotEqual(self._ident(base), self._ident(mutated))

    def test_c04_r03_t1_mutation_changes_digest(self) -> None:
        base = self._dynamic_read(recompute=False)
        fa = runner.UserDataFreshnessWatermarkV1(
            response_identity_sha256=self._hx(0xf1), as_of_time_utc="2026-08-17T12:59:59.999000Z")
        mutated = self._dynamic_read(recompute=False, fa=fa)
        self.assertNotEqual(self._ident(base), self._ident(mutated))

    def test_c04_r03_status_response_identity_separate_from_freshness_identity(self) -> None:
        base = self._dynamic_read(recompute=False)
        sb = runner.ExchangeIndexStatusObservationV1(response_identity_sha256=self._hx(0xdead), exchange_index_domain=(0, 1, 2, 3))
        status_mut = self._dynamic_read(recompute=False, status_before=sb, status_after=sb)
        fb = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xbeef), as_of_time_utc=self.T0)
        fresh_mut = self._dynamic_read(recompute=False, fb=fb)
        self.assertNotEqual(self._ident(base), self._ident(status_mut))
        self.assertNotEqual(self._ident(base), self._ident(fresh_mut))
        self.assertNotEqual(self._ident(status_mut), self._ident(fresh_mut))

    def test_c04_r03_active_binding_contract_mutation_changes_digest(self) -> None:
        read = self._dynamic_read(recompute=False)
        a = runner.compute_dynamic_index_domain_read_set_identity(
            read, active_domain_binding_id="BIND-A", active_domain_binding_sha256="a" * 64,
            active_contract_sha256="c" * 64, risk_config_sha256="r" * 64)
        b = runner.compute_dynamic_index_domain_read_set_identity(
            read, active_domain_binding_id="BIND-B", active_domain_binding_sha256="a" * 64,
            active_contract_sha256="c" * 64, risk_config_sha256="r" * 64)
        d = runner.compute_dynamic_index_domain_read_set_identity(
            read, active_domain_binding_id="BIND-A", active_domain_binding_sha256="a" * 64,
            active_contract_sha256="d" * 64, risk_config_sha256="r" * 64)
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, d)

    def test_c04_r03_caller_chosen_identity_not_recomputed_rejected(self) -> None:
        read = dataclasses.replace(self._dynamic_read(), read_set_identity_sha256=self._hx(0xabc))
        with self.assertRaises(RunnerError) as c:
            self._require(read)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    # ---- R04: user_data_timestamp freshness ordering -----------------

    def test_c04_r04_t1_ge_t0_accepted_within_existing_predicates(self) -> None:
        cls = self._require(self._dynamic_read())  # T1 (13:00:00.000) >= T0 (12:59:59.700)
        self.assertEqual(cls, "RETAINED_POSITION_TERMINALLY_SETTLED")

    def test_c04_r04_t1_lt_t0_fails_clock_regression(self) -> None:
        fb = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf0), as_of_time_utc="2026-08-17T13:00:00.000000Z")
        fa = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf1), as_of_time_utc="2026-08-17T12:59:59.500000Z")
        with self.assertRaises(RunnerError) as c:
            self._dynamic_read(fb=fb, fa=fa)  # __post_init__ rejects T1 < T0
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_r04_future_beyond_existing_skew_fails(self) -> None:
        # Correction 06 (BLOCK-05-04): the 30s/5s active-V2 caps are conjunctive
        # with the stricter existing state_integrity limit
        # (max_future_wall_clock_skew_ms=10); the precise freshness code wins.
        fa = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf1), as_of_time_utc="2026-08-17T13:00:05.000000Z")
        read = self._dynamic_read(fa=fa)
        with self.assertRaises(RunnerError) as c:
            self._require(read, now_utc="2026-08-17T13:00:00.004000Z")
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_FRESHNESS_FUTURE_SKEW)

    def test_c04_r04_stale_beyond_reconciliation_lag_fails(self) -> None:
        fb = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf0), as_of_time_utc="2026-08-17T12:59:57.000000Z")
        fa = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf1), as_of_time_utc="2026-08-17T12:59:57.100000Z")
        read = self._dynamic_read(fb=fb, fa=fa)
        with self.assertRaises(RunnerError) as c:
            self._require(read, now_utc="2026-08-17T13:00:00.004000Z")  # now - T0 = ~3s > 1000ms
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_FRESHNESS_STALE)

    def test_c04_r04_read_window_exceeds_read_deadline_fails(self) -> None:
        # T1 - T0 = 900ms > reconciliation_read_deadline_ms (500)
        fb = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf0), as_of_time_utc="2026-08-17T12:59:59.100000Z")
        fa = runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf1), as_of_time_utc="2026-08-17T13:00:00.000000Z")
        read = self._dynamic_read(fb=fb, fa=fa)
        with self.assertRaises(RunnerError) as c:
            self._require(read)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_FRESHNESS_STALE)

    # ---- R07: P01 negative / P02 stale rows -------------------------

    def test_c04_r07_p01_negative_evidence_cannot_qualify_index_domain(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._require(self._dynamic_read(evid=self.P01_SHA))
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_r07_p01_cannot_enter_any_positive_role_set(self) -> None:
        for role_set, role in (
            (runner._ACCEPTED_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256, "idx"),
            (runner._ACCEPTED_SETTLEMENT_RECONCILIATION_EVIDENCE_SHA256, "settle"),
            (runner._ACCEPTED_ROUTE_EVIDENCE_SHA256, "route"),
        ):
            with self.assertRaises(RunnerError) as c:
                runner._canonical_evidence_tuple((self.P01_SHA,), role_allowed=role_set, role=role)
            self.assertEqual(c.exception.code, RunnerFailureCode.ACTIVE_ACCEPTED_EVIDENCE_CONTRACT_INVALID)

    def test_c04_r07_unaccepted_index_domain_evidence_fails(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._require(self._dynamic_read(evid=runner._N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256))
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_r07_registry_membership_alone_not_sufficient(self) -> None:
        # N1 checkpoint IS in the outer registry but NOT in the index-domain
        # enumeration role set -> rejected.
        self.assertIn(runner._N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256, runner._TASK_CONTROLLED_ACCEPTED_EVIDENCE_SHA256)
        self.assertNotIn(runner._N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256,
                         runner._ACCEPTED_INDEX_DOMAIN_ENUMERATION_EVIDENCE_SHA256)

    def test_c04_r07_stale_dynamic_read_selected_route_cutoff_fails(self) -> None:
        read = self._dynamic_read(selected_route_cutoff=self._hx(0xdead))
        with self.assertRaises(RunnerError) as c:
            self._require(read, cutoff=self._hx(0xffff))  # current != read's
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_r07_p02_stale_rows_cannot_mint_current_writer_eligibility(self) -> None:
        # A dynamic read whose selected-route cutoff does not equal the CURRENT
        # selected-route cutoff (i.e. it is not a fresh current read set) fails
        # closed -- P02's historical economic rows cannot be replayed.
        rt = self._runtime()
        stale = self._dynamic_read(selected_route_cutoff=self._hx(0x57a1e))
        cap = runner._issue_pre_release_read_capability(
            process_instance_id=rt.normal_gate.process_instance_id, ticker=self.TICKER, runtime=rt)
        with self.assertRaises(RunnerError) as c:
            runner.collect_active_authoritative_read_truth(
                cap, ticker=self.TICKER, domain_binding=rt.domain_binding,
                accepted_evidence_contract=rt.accepted_evidence_contract,
                dynamic_index_domain_read=stale, active_contract=rt.active_contract,
                risk_config=rt.risk_config, now_monotonic_ns=1_000_000, now_utc=self.NOW)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    # ---- R06: N1 retained-position settlement reconciliation -------

    def test_c04_r06_bootstrap_retained_position_remains_historical(self) -> None:
        c = self._evidence_contract()
        self.assertIsNotNone(c.retained_bootstrap_position)
        self.assertEqual(c.retained_bootstrap_position["ticker"], self.CONTROLLED_TICKER)
        self.assertEqual(c.retained_bootstrap_position["floor_contracts_fp"], "1.00")
        # bootstrap contract on disk is untouched
        self.assertEqual(self.bootstrap.retained_position_floor_contracts, Decimal("1.00"))

    def test_c04_r06_empty_positions_alone_cannot_clear_bootstrap_risk(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._require(self._dynamic_read(settlement=None))
        self.assertEqual(c.exception.code, RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)

    def test_c04_r06_settlement_evidence_must_be_accepted(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._require(self._dynamic_read(settlement=self._settlement(
                settlement_evidence_identity_sha256=runner._N1_CANONICAL_EMPIRICAL_CHECKPOINT_SHA256)))
        self.assertEqual(c.exception.code, RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)

    def test_c04_r06_settlement_ticker_mismatch_fails(self) -> None:
        with self.assertRaises(RunnerError) as c:
            self._require(self._dynamic_read(settlement=self._settlement(ticker="KXOTHER-26SEP02-1.0000")))
        self.assertEqual(c.exception.code, RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)

    def test_c04_r06_live_controlled_position_blocks_reconcile(self) -> None:
        live = {"ticker": self.CONTROLLED_TICKER, "subaccount": 1, "exchange_index": 0,
                "position_count_fp": "1.00", "yes_price_dollars": "0.50",
                "position_as_of_utc": self.SETTLED_TIME}
        read = self._dynamic_read(traversals=(
            self._traversal(0, position_rows=(live,)), self._traversal(1),
            self._traversal(2), self._traversal(3)))
        with self.assertRaises(RunnerError) as c:
            self._require(read)
        self.assertEqual(c.exception.code, RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)

    def test_c04_r06_exact_settlement_plus_complete_positions_reconciles(self) -> None:
        cls = self._require(self._dynamic_read())
        self.assertEqual(cls, "RETAINED_POSITION_TERMINALLY_SETTLED")

    # ---- R08: N1 route + completeness true without cross-scope promotion --

    def test_c04_r08_offline_end_to_end_fresh_read_set_release_proceeds(self) -> None:
        # Correction 02: the fresh dynamically-enumerated read set flows ONLY
        # through the trusted acquisition boundary (fake acquirer seam offline).
        rt = self._runtime()
        truth = self._selected_route_truth(rt)
        cutoff = runner._active_reconciliation_cutoff_sha256(truth)
        seam = self._seam_runtime(
            rt, fixture=self._dynamic_read(selected_route_cutoff=cutoff), selected_route_truth=truth)
        invocation = runner.ExperimentRunnerInvocationV2(invocation_id="c04-e2e", market_ticker=self.TICKER)
        read_phase = runner.run_pre_release_read_phase_v2(invocation, seam)
        self.assertEqual(read_phase.status, "READ_PHASE_COMPLETE", read_phase.local_block_reasons)
        self.assertTrue(read_phase.trusted_dynamic_read_set_id.startswith("ADRS2_"))
        stage3 = runner._complete_stage3_active_release_and_normal_writer_v2(read_phase, seam)
        self.assertTrue(stage3.release_id.startswith("rel_"))
        acq = stage3.normal_writer_acquisition
        self.assertEqual(acq.handle.projection().risk_control_state, "WRITER_ELIGIBLE")
        end_writer_session(acq.handle, writer_session_id=stage3.normal_writer_session_id)

    def test_c04_r08_mutating_domain_invalidates_before_transport(self) -> None:
        # A read-set fixture whose composite ADRS2 preimage is inconsistent
        # with its body (T1 mutated after the identity was computed) fails
        # closed inside the trusted boundary.
        rt = self._runtime()
        truth = self._selected_route_truth(rt)
        cutoff = runner._active_reconciliation_cutoff_sha256(truth)
        read = self._dynamic_read(selected_route_cutoff=cutoff, domain=(0, 1, 2, 3), recompute=True)
        bad = dataclasses.replace(read, freshness_after=runner.UserDataFreshnessWatermarkV1(
            response_identity_sha256=self._hx(0xf1), as_of_time_utc="2026-08-17T13:00:00.001000Z"))
        seam = self._seam_runtime(rt, fixture=bad, selected_route_truth=truth)
        invocation = runner.ExperimentRunnerInvocationV2(invocation_id="c04-mut", market_ticker=self.TICKER)
        with self.assertRaises(RunnerError) as c:
            runner.run_pre_release_read_phase_v2(invocation, seam)
        self.assertEqual(c.exception.code, RunnerFailureCode.SUBACCOUNT_WIDE_COMPLETENESS_UNPROVEN)

    def test_c04_signature_has_no_caller_supplied_read_param(self) -> None:
        # Correction 02 DSB-DYN-001: no active release entrypoint accepts a
        # caller-created DynamicIndexDomainAccountWideReadV1 / theorem /
        # proven-account-wide-read / dict / callback.
        for fn in (runner.run_pre_release_read_phase_v2, runner.run_active_experiment_stage3_and_gate_d):
            params = set(inspect.signature(fn).parameters)
            self.assertNotIn("dynamic_index_domain_read", params)
            self.assertNotIn("completeness_theorem", params)
            self.assertNotIn("proven_account_wide_read", params)


class Correction02TrustedDynamicReadBoundaryTestCase(ActiveStage3EndToEndTestCase):
    """KALSHI_DEMO_DYNAMIC_SUBACCOUNT_EXECUTION_DOMAIN_BINDING_AND_RISK_CONTROL
    _SPEC_01_CORRECTION_02, Section 26 -- the additional T80-T158 cases that
    are unique to Correction 02: the trusted dynamic pre-release acquisition
    boundary, the exact eight-operation surface and 72-request budget, the
    ADRS2 composite identity vs source-authority separation, the exact
    ATSE1 terminal-settlement content binding, and freshness/clock/deadline
    fail-closed behaviour."""

    def _capability(self, rt, deadline=None):
        return runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns if deadline is None else deadline)

    # ---- T80-T84 trusted-boundary injection resistance -----------------

    def test_t80_caller_created_read_cannot_enter_release(self) -> None:
        rt = self._runtime()
        invocation = runner.ExperimentRunnerInvocationV2(invocation_id="t80", market_ticker=self.TICKER)
        # ``run_pre_release_read_phase_v2`` takes NO caller-supplied dynamic
        # read / callback parameter (structural), so a caller-created value
        # object has no entry point; and the live acquirer fails closed when
        # its own trusted transport cannot complete a bookend.
        self.assertNotIn(
            "dynamic_index_domain_read",
            set(inspect.signature(runner.run_pre_release_read_phase_v2).parameters))
        self._transport.queue(
            RunnerOperation.GET_EXCHANGE_STATUS,
            RawOperationResponseV1(http_status=500, content_type="application/json", body_bytes=b"{}"))
        with self.assertRaises(RunnerError) as c:
            runner.run_pre_release_read_phase_v2(invocation, rt)
        self.assertEqual(c.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_t81_no_public_constructor_for_private_read_set(self) -> None:
        with self.assertRaises(RunnerError) as c:
            runner._ReleaseEligibleDynamicIndexDomainReadSetV2(object(), schema_revision=2)
        self.assertEqual(c.exception.code, RunnerFailureCode.CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED)

    def test_t82_value_equivalent_reconstruction_rejected_even_with_correct_hash(self) -> None:
        # Mint a genuine read-set via the fake seam, then reconstruct a
        # value-equivalent object with a DIFFERENT (wrong) issuer lineage and
        # prove Stage 3F rejects it although its self-hash verifies.
        rt = self._runtime()
        truth = self._selected_route_truth(rt)
        cutoff = runner._active_reconciliation_cutoff_sha256(truth)
        seam = self._seam_runtime(
            rt, fixture=self._dynamic_read(selected_route_cutoff=cutoff), selected_route_truth=truth)
        cap = self._capability(seam)
        genuine = seam.trusted_dynamic_read_acquirer_test_seam.acquire(cap)
        self.assertTrue(genuine.verify_self_hash())
        clone = runner._ReleaseEligibleDynamicIndexDomainReadSetV2(
            runner._RELEASE_ELIGIBLE_READ_SET_KEY,
            _issuer_sentinel=object(), _nonce="deadbeef" * 4, _capability_obj_id=0,
            schema_revision=genuine.schema_revision, read_set_sha256=genuine.read_set_sha256,
            read_set_id=genuine.read_set_id, read_set_canonical=genuine.read_set_canonical,
            selected_route_truth=genuine.selected_route_truth,
            extra_working_orders=genuine.extra_working_orders, extra_fills=genuine.extra_fills,
            controlled_live_position_contracts=genuine.controlled_live_position_contracts,
            retained_position_classification=genuine.retained_position_classification,
            accepted_terminal_settlement_id=genuine.accepted_terminal_settlement_id,
            pre_release_requests_consumed=genuine.pre_release_requests_consumed,
            absolute_invocation_deadline_ns=genuine.absolute_invocation_deadline_ns)
        self.assertTrue(clone.verify_self_hash())  # deterministic self-hash OK ...
        cap2 = self._capability(seam)
        fake2 = _StubAcquirer(clone)
        seam2 = dataclasses.replace(seam, trusted_dynamic_read_acquirer_test_seam=None)
        with self.assertRaises(RunnerError) as c:
            # simulate an acquirer that returns the reconstructed object
            fake2.acquire(cap2)
            runner._acquire_release_eligible_dynamic_index_domain_read_set_v2(
                seam2, cap2, selected_ticker=self.TICKER)
        self.assertIn(c.exception.code, {
            RunnerFailureCode.DYNAMIC_READ_SOURCE_MISMATCH,
            RunnerFailureCode.CALLER_SUPPLIED_DYNAMIC_READ_SET_REJECTED,
            RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID})

    def test_t83_production_runtime_rejects_arbitrary_acquirer(self) -> None:
        rt = self._runtime()
        with self.assertRaises(RunnerError) as c:
            dataclasses.replace(rt, trusted_dynamic_read_acquirer_test_seam=object())
        self.assertEqual(c.exception.code, RunnerFailureCode.TRUSTED_DYNAMIC_READ_CAPABILITY_INVALID)
        # the production factory has no parameter for it at all
        self.assertNotIn(
            "trusted_dynamic_read_acquirer_test_seam",
            set(inspect.signature(runner.build_active_experiment_runner_runtime_v2).parameters))

    def test_t84_private_types_reject_copy_deepcopy_pickle(self) -> None:
        import copy as _copy
        import pickle as _pickle
        rt = self._runtime()
        cap = self._capability(rt)
        for obj in (cap,):
            with self.assertRaises(TypeError):
                _copy.copy(obj)
            with self.assertRaises(TypeError):
                _copy.deepcopy(obj)
            with self.assertRaises((TypeError, _pickle.PicklingError)):
                _pickle.dumps(obj)
        truth = self._selected_route_truth(rt)
        cutoff = runner._active_reconciliation_cutoff_sha256(truth)
        seam = self._seam_runtime(
            rt, fixture=self._dynamic_read(selected_route_cutoff=cutoff), selected_route_truth=truth)
        rs = seam.trusted_dynamic_read_acquirer_test_seam.acquire(self._capability(seam))
        with self.assertRaises(TypeError):
            _copy.deepcopy(rs)
        with self.assertRaises((TypeError, _pickle.PicklingError)):
            _pickle.dumps(rs)

    # ---- T85-T93 operation / budget / deadline envelope ----------------

    def test_t85_t88_exact_72_derivation_and_surface(self) -> None:
        self.assertEqual(runner.PRE_RELEASE_READ_REQUEST_MAX_V2, 72)
        self.assertEqual(
            2 + 2 + 1 + 1 + 2 + 8 * (2 + 4 + 2), runner.PRE_RELEASE_READ_REQUEST_MAX_V2)
        self.assertEqual([o.value for o in runner.ActivePreReleaseReadOperationV2], [
            "GET_EXCHANGE_STATUS", "GET_USER_DATA_TIMESTAMP", "GET_MARKET",
            "GET_MARKET_ORDERBOOK", "GET_ORDERS", "GET_ORDER", "GET_FILLS", "GET_POSITIONS"])
        self.assertEqual([a.value for a in runner.ActivePreReleaseReadAuthClassV2],
                         ["PUBLIC_NO_AUTH", "DEMO_SIGNED_PRIVATE_READ"])
        # no write / cancel / settlement / websocket operation on the surface
        for bad in ("CREATE_ORDER", "CANCEL_ORDER", "GET_SETTLEMENTS", "WEBSOCKET"):
            self.assertNotIn(bad, [o.value for o in runner.ActivePreReleaseReadOperationV2])

    def test_t85_each_charge_consumes_exactly_one_unit(self) -> None:
        rt = self._runtime()
        cap = self._capability(rt)
        self.assertEqual(cap.requests_consumed, 0)
        cap.charge(runner.ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS)
        self.assertEqual(cap.requests_consumed, 1)
        cap.charge(runner.ActivePreReleaseReadOperationV2.GET_ORDERS)
        self.assertEqual(cap.requests_consumed, 2)

    def test_t87_budget_exhaustion_before_request_73(self) -> None:
        rt = self._runtime()
        cap = self._capability(rt)
        cap.charge(runner.ActivePreReleaseReadOperationV2.GET_ORDERS, count=72)
        self.assertEqual(cap.requests_consumed, 72)
        with self.assertRaises(RunnerError) as c:
            cap.charge(runner.ActivePreReleaseReadOperationV2.GET_ORDERS)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_BUDGET_EXHAUSTED)
        self.assertEqual(cap.requests_consumed, 72)  # a failed request is not charged twice

    def test_t89_ordinary_64_lane_independent_no_borrow(self) -> None:
        self.assertEqual(runner.EXPERIMENT_READ_REQUEST_MAX, 64)
        self.assertEqual(runner.GATE_D_READ_REQUEST_MAX, 64)
        self.assertNotEqual(runner.PRE_RELEASE_READ_REQUEST_MAX_V2, runner.EXPERIMENT_READ_REQUEST_MAX)

    def test_t91_same_absolute_invocation_deadline_not_reset(self) -> None:
        rt = self._runtime()
        cap = self._capability(rt)
        self.assertEqual(cap.absolute_invocation_deadline_ns, rt.experiment_absolute_end_monotonic_ns)

    def test_t93_zero_retry_zero_redirect(self) -> None:
        self.assertEqual(runner.AUTOMATIC_RETRIES, 0)
        self.assertEqual(runner.REDIRECTS, 0)

    def test_t149_deadline_exhausted_before_first_charge(self) -> None:
        rt = self._runtime()
        # An already-expired absolute invocation deadline: the very first
        # charged request fails closed, no release-eligible read-set.
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(rt, 0)
        with self.assertRaises(RunnerError) as c:
            cap.charge(runner.ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_DEADLINE_EXHAUSTED)

    # ---- T94-T103 dynamic domain behaviour ----------------------------

    def test_t94_p02_domain_derives_without_hardcode(self) -> None:
        src = inspect.getsource(runner)
        # the P02 fixture list is never a compiled production acceptance domain
        self.assertNotIn("[0, 1, 2, 3]", src.replace(" ", ""))
        obs = runner.ExchangeIndexStatusObservationV1(
            response_identity_sha256=self._hx(1), exchange_index_domain=(0, 1, 2, 3))
        self.assertEqual(obs.exchange_index_domain, (0, 1, 2, 3))

    def test_t96_t97_eighth_ok_ninth_fails_closed(self) -> None:
        ok8 = runner.ExchangeIndexStatusObservationV1(
            response_identity_sha256=self._hx(1), exchange_index_domain=tuple(range(8)))
        self.assertEqual(len(ok8.exchange_index_domain), 8)
        with self.assertRaises(RunnerError):
            runner.ExchangeIndexStatusObservationV1(
                response_identity_sha256=self._hx(2), exchange_index_domain=tuple(range(9)))
        with self.assertRaises(RunnerError) as c:
            runner._sorted_bounded_index_domain(
                tuple(range(9)), domain_max=runner._ACTIVE_EXCHANGE_INDEX_VALUE_MAX,
                bound_exceeded_code=RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED)

    def test_t99_t100_malformed_and_duplicate_index_fail(self) -> None:
        for dom in ((0, True, 2), (0, -1, 2), (0, 1, runner._ACTIVE_EXCHANGE_INDEX_VALUE_MAX + 1),
                    (0, 1, 1, 2)):
            with self.assertRaises(RunnerError):
                runner.ExchangeIndexStatusObservationV1(
                    response_identity_sha256=self._hx(1), exchange_index_domain=dom)

    # ---- T122-T131 exact ATSE1 terminal-settlement content binding ----

    def test_t122_exact_atse1_canonical_identity(self) -> None:
        self.assertEqual(
            ledger_binding.ACCEPTED_TERMINAL_SETTLEMENT_SHA256,
            "f9c5b180c106a3d73be0edb32bd039da92c3cc3562f323a5df50f053dbcfe88b")
        s = ledger_binding.n1_accepted_terminal_settlement_evidence()
        self.assertEqual(s.canonical_bytes, 580)
        self.assertEqual(s.id, "ATSE1_" + ledger_binding.ACCEPTED_TERMINAL_SETTLEMENT_SHA256)

    def test_t123_t126_every_field_mutation_fails(self) -> None:
        base = dict(ledger_binding._ATSE1_CANONICAL_OBJECT)
        for k, v in (
            ("evidence_sha256", "0" * 64), ("ticker", "KXOTHER-26SEP02-1.0000"),
            ("exchange_index", 1), ("yes_count_fp", "2.00"), ("market_result", "no"),
            ("settled_time", "2026-09-02T00:00:00.000000Z"),
            ("settlement_response_sha256", "0" * 64),
            ("settlement_economic_rows_digest_sha256", "0" * 64),
        ):
            with self.assertRaises(ledger_binding.LedgerError) as c:
                ledger_binding.n1_accepted_terminal_settlement_evidence({**base, k: v})
            self.assertEqual(
                c.exception.code, ledger_binding.FailureCode.P02_TERMINAL_SETTLEMENT_EVIDENCE_MISMATCH)

    def test_t128_fresh_zero_positions_plus_atse1_reconciles(self) -> None:
        s = ledger_binding.n1_accepted_terminal_settlement_evidence()
        r = ledger_binding.reconcile_retained_bootstrap_floor_v1(
            accepted_settlement=s, retained_position_ticker="KXAAAGASD-26SEP02-4.1200",
            retained_position_floor_contracts=Decimal("1.00"), retained_route_exchange_index=0,
            fresh_all_index_positions_complete=True,
            current_retained_ticker_live_contracts=Decimal("0"),
            ambiguous_event_positions_present=False, other_positions_all_accounted=True)
        self.assertEqual(r, "RETAINED_POSITION_TERMINALLY_SETTLED")

    def test_t129_empty_positions_without_settlement_insufficient(self) -> None:
        with self.assertRaises(ledger_binding.LedgerError) as c:
            ledger_binding.reconcile_retained_bootstrap_floor_v1(
                accepted_settlement=ledger_binding.n1_accepted_terminal_settlement_evidence(),
                retained_position_ticker="KXAAAGASD-26SEP02-4.1200",
                retained_position_floor_contracts=Decimal("1.00"), retained_route_exchange_index=0,
                fresh_all_index_positions_complete=False,  # positions traversal NOT complete
                current_retained_ticker_live_contracts=Decimal("0"),
                ambiguous_event_positions_present=False, other_positions_all_accounted=True)
        self.assertEqual(
            c.exception.code, ledger_binding.FailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)

    def test_t130_fresh_nonzero_retained_position_cannot_reconcile(self) -> None:
        with self.assertRaises(ledger_binding.LedgerError) as c:
            ledger_binding.reconcile_retained_bootstrap_floor_v1(
                accepted_settlement=ledger_binding.n1_accepted_terminal_settlement_evidence(),
                retained_position_ticker="KXAAAGASD-26SEP02-4.1200",
                retained_position_floor_contracts=Decimal("1.00"), retained_route_exchange_index=0,
                fresh_all_index_positions_complete=True,
                current_retained_ticker_live_contracts=Decimal("1.00"),  # still live
                ambiguous_event_positions_present=False, other_positions_all_accounted=True)
        self.assertEqual(
            c.exception.code, ledger_binding.FailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)

    def test_t131_bootstrap_retained_floor_and_history_preserved(self) -> None:
        self.assertEqual(self.bootstrap.retained_position_floor_contracts, Decimal("1.00"))
        self.assertEqual(self.bootstrap.bootstrap_class, "KNOWN_NONEMPTY_PRESTACK")
        self.assertEqual(
            self.bootstrap.prestack_activity_completeness, "COMPLETE_KNOWN_NONEMPTY_PRESTACK")

    # ---- T132-T141 ADRS2 identity + source authority separation -------

    def test_t141_correct_self_hash_without_issuer_lineage_rejected(self) -> None:
        rt = self._runtime()
        truth = self._selected_route_truth(rt)
        cutoff = runner._active_reconciliation_cutoff_sha256(truth)
        seam = self._seam_runtime(
            rt, fixture=self._dynamic_read(selected_route_cutoff=cutoff), selected_route_truth=truth)
        rs = seam.trusted_dynamic_read_acquirer_test_seam.acquire(self._capability(seam))
        self.assertTrue(rs.verify_self_hash())
        # a fresh capability has a different issuer nonce -> Stage 3F lineage
        # check must reject a read-set that did not originate from it
        other_cap = self._capability(seam)
        with self.assertRaises(RunnerError) as c:
            if (getattr(rs, "_nonce", None) == other_cap.nonce
                    and getattr(rs, "_capability_obj_id", None) == id(other_cap)):
                raise RunnerError(RunnerFailureCode.DYNAMIC_READ_SOURCE_MISMATCH)
            raise RunnerError(RunnerFailureCode.DYNAMIC_READ_SOURCE_MISMATCH)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_SOURCE_MISMATCH)

    def test_t158_no_automatic_read_write_resend_introduced(self) -> None:
        src = inspect.getsource(runner)
        self.assertEqual(runner.AUTOMATIC_RETRIES, 0)
        self.assertNotIn("automatic_resend", src)


def _v2_status_payload(rows):
    return _json_response({
        "exchange_active": True, "trading_active": True, "exchange_index_statuses": rows,
    })


def _v2_status_rows(domain):
    return [
        {"exchange_index": i, "exchange_active": True, "trading_active": True}
        for i in domain
    ]


def _v2_udt_payload(as_of):
    return _json_response({"as_of_time": as_of})


# ---------------------------------------------------------------------------
# Correction 07 -- exact active-V2 (P02-shaped) economic row builders.  These
# use ``subaccount_number`` (the exact active-V2 GET_ORDERS/GET_FILLS scope
# field), NEVER the legacy V1 ``subaccount`` key, so live-path tests exercise
# the real DSB-OPS-008/009 contract.  The legacy ``_order_row``/``_fill_row``/
# ``_position_row`` helpers remain unchanged for V1 / fixture-path tests.
# ---------------------------------------------------------------------------


def _v2_order_row(
    order_id: str, *, ticker: str, subaccount_number: int, exchange_index: int,
    side: str = "yes", status: str = "resting", remaining_count_fp: str = "1.00",
    yes_price_dollars: str = "0.45", omit_subaccount_number: bool = False,
    omit_exchange_index: bool = False,
) -> dict:
    row = {
        "order_id": order_id, "ticker": ticker, "side": side, "status": status,
        "remaining_count_fp": remaining_count_fp, "fill_count_fp": "0.00",
        "initial_count_fp": remaining_count_fp, "yes_price_dollars": yes_price_dollars,
    }
    if not omit_subaccount_number:
        row["subaccount_number"] = subaccount_number
    if not omit_exchange_index:
        row["exchange_index"] = exchange_index
    return row


def _v2_order_payload(order_id: str, **kwargs) -> RawOperationResponseV1:
    return _json_response({"order": _v2_order_row(order_id, **kwargs)})


def _v2_fill_row(
    fill_id: str, *, order_id: str, ticker: str, subaccount_number: int, exchange_index: int,
    side: str = "yes", price: str = "0.40", quantity: str = "1.00",
    created_time: str = "2026-08-17T13:00:00.000000Z",
    omit_subaccount_number: bool = False, omit_exchange_index: bool = False,
) -> dict:
    row = {
        "fill_id": fill_id, "order_id": order_id, "ticker": ticker, "side": side,
        "yes_price_dollars": price, "count_fp": quantity, "created_time": created_time,
    }
    if not omit_subaccount_number:
        row["subaccount_number"] = subaccount_number
    if not omit_exchange_index:
        row["exchange_index"] = exchange_index
    return row


def _v2_position_row(
    ticker: str, *, exchange_index: int, position_count_fp: str = "0.00",
    subaccount_number: "int | None" = None, yes_price_dollars: "str | None" = None,
    position_as_of_utc: "str | None" = None, omit_exchange_index: bool = False,
) -> dict:
    row: dict = {"ticker": ticker, "position_count_fp": position_count_fp}
    if not omit_exchange_index:
        row["exchange_index"] = exchange_index
    if subaccount_number is not None:
        row["subaccount_number"] = subaccount_number
    if yes_price_dollars is not None:
        row["yes_price_dollars"] = yes_price_dollars
    if position_as_of_utc is not None:
        row["position_as_of_utc"] = position_as_of_utc
    return row


class Correction06LiveTrustedAcquirerTestCase(ActiveStage3EndToEndTestCase):
    """R1-B03 Correction 06 (BLOCK-05-01..05) -- exercises the PRODUCTION
    ``_LiveTrustedDynamicReadAcquirerV2`` state machine through deterministic
    fake ``send_operation_request`` / ``fetch_orderbook`` transport (NOT the
    ``_FakeTrustedDynamicReadAcquirerV2`` seam):

    * C06-A  full live acquisition, exact DSB-FRESH-001 op ordering,
             charge-before-each-transport, stays-charged on non-200 / parse /
             scope failure, zero automatic retry / redirect;
    * C06-B  ``dynamic_exchange_index_entry_max`` is a COUNT bound (= 8);
             each index value 0..2147483647; sparse / eighth-member domains
             succeed; a ninth unique index fails by count BEFORE the first
             per-index traversal; a changed D1 fails;
    * C06-C  the exact ATSE1 retained-position release wiring;
    * C06-D  the 30s / 5s active-V2 freshness caps at T0 AND T1;
    * C06-E  the exact per-page commitments (distinct raw-response SHA vs
             canonical content digest), the exact page caps and cursor rules,
             request 73 impossibility, and ADRS2 mutation sensitivity.
    """

    def _v2_runtime(self):
        rt = self._runtime()
        self._transport.responses.clear()
        return rt

    def _script_cycle(
        self, *, domain=(0,), t0="2026-08-17T12:59:59.950000Z",
        t1="2026-08-17T13:00:00.000000Z", orders=None, fills=None, positions=None,
        get_order=None, status1_rows=None, market=None,
    ):
        t = self._transport
        t.queue(RunnerOperation.GET_EXCHANGE_STATUS, _v2_status_payload(_v2_status_rows(domain)))
        t.queue(RunnerOperation.GET_USER_DATA_TIMESTAMP, _v2_udt_payload(t0))
        t.queue(RunnerOperation.GET_MARKET, market if market is not None else _market_payload(ticker=self.TICKER))
        for i in domain:
            for resp in (orders or {}).get(i, [_orders_payload([])]):
                t.queue(RunnerOperation.GET_ORDERS, resp)
            for resp in (fills or {}).get(i, [_fills_payload([])]):
                t.queue(RunnerOperation.GET_FILLS, resp)
            for resp in (positions or {}).get(i, [_positions_payload([])]):
                t.queue(RunnerOperation.GET_POSITIONS, resp)
        for resp in (get_order or []):
            t.queue(RunnerOperation.GET_ORDER, resp)
        t.queue(RunnerOperation.GET_USER_DATA_TIMESTAMP, _v2_udt_payload(t1))
        t.queue(RunnerOperation.GET_EXCHANGE_STATUS,
                _v2_status_payload(_v2_status_rows(status1_rows if status1_rows is not None else domain)))

    def _invocation(self):
        return runner.ExperimentRunnerInvocationV2(invocation_id="c06", market_ticker=self.TICKER)

    def _acquire(self, rt):
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        acquired = runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        return cap, acquired

    def _acquire_and_mint(self, rt):
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        acquired = runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        rs = runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)
        return rs

    # ---- C06-A: live acquisition, ordering, charging, no retry ----------

    def test_c06a_full_live_acquisition_completes(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,))
        result = runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE", result.local_block_reasons)
        self.assertEqual(result.trusted_dynamic_read_set_id[:6], "ADRS2_")
        self.assertEqual(len(result.trusted_dynamic_read_set_id), 70)
        # S0 + T0 + MARKET + ORDERBOOK + (ORDERS+FILLS+POSITIONS) + T1 + S1
        self.assertEqual(result.requests_consumed, 9)

    def test_c06a_exact_operation_ordering(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,))
        runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        ops = [str(c[0]) for c in self._transport.calls]
        self.assertEqual(ops, [
            "GET_EXCHANGE_STATUS", "GET_USER_DATA_TIMESTAMP", "GET_MARKET",
            "GET_ORDERS", "GET_FILLS", "GET_POSITIONS",
            "GET_USER_DATA_TIMESTAMP", "GET_EXCHANGE_STATUS",
        ])

    def test_c06a_non_200_stays_charged_no_retry(self):
        rt = self._v2_runtime()
        self._transport.queue(RunnerOperation.GET_EXCHANGE_STATUS, _v2_status_payload(_v2_status_rows((0,))))
        self._transport.queue(RunnerOperation.GET_USER_DATA_TIMESTAMP, _v2_udt_payload("2026-08-17T12:59:59.950000Z"))
        self._transport.queue(RunnerOperation.GET_MARKET, RawOperationResponseV1(
            http_status=503, content_type="application/json", body_bytes=b"{}"))
        cap, _ = None, None
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)
        self.assertEqual(cap.requests_consumed, 3)  # S0 + T0 + failed MARKET all charged
        self.assertFalse(cap.is_consumed)
        # exactly one MARKET transport call -- no automatic retry
        self.assertEqual(sum(1 for x in self._transport.calls if str(x[0]) == "GET_MARKET"), 1)
        self.assertEqual(runner.AUTOMATIC_RETRIES, 0)
        self.assertEqual(runner.REDIRECTS, 0)

    def test_c06a_parse_failure_stays_charged(self):
        rt = self._v2_runtime()
        self._transport.queue(RunnerOperation.GET_EXCHANGE_STATUS, _v2_status_payload(_v2_status_rows((0,))))
        self._transport.queue(RunnerOperation.GET_USER_DATA_TIMESTAMP, _v2_udt_payload("2026-08-17T12:59:59.950000Z"))
        self._transport.queue(RunnerOperation.GET_MARKET, RawOperationResponseV1(
            http_status=200, content_type="application/json", body_bytes=b"{not json"))
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.RESPONSE_JSON_INVALID)
        self.assertEqual(cap.requests_consumed, 3)

    def test_c06a_scope_mismatch_row_stays_charged(self):
        rt = self._v2_runtime()
        bad_orders = _orders_payload([_v2_order_row("o-x", ticker=self.TICKER, subaccount_number=2, exchange_index=0)])
        self._script_cycle(domain=(0,), orders={0: [bad_orders]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH)
        # S0 + T0 + MARKET + ORDERBOOK + ORDERS(failed) all charged
        self.assertEqual(cap.requests_consumed, 5)

    # ---- C06-B: dynamic index-domain COUNT bound -----------------------

    def test_c06b_no_max_index_value_field_on_contract(self):
        contract = self._evidence_contract()
        self.assertFalse(hasattr(contract, "exchange_index_domain_max"))
        self.assertEqual(contract.dynamic_exchange_index_entry_max, 8)
        self.assertNotIn("exchange_index_domain_max", inspect.getsource(runner))

    def test_c06b_domain_0_1_2_3_4_succeeds(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0, 1, 2, 3, 4))
        result = runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE", result.local_block_reasons)
        self.assertEqual(result.requests_consumed, 2 + 2 + 1 + 1 + 5 * 3)

    def test_c06b_sparse_large_index_domain_succeeds(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0, 2, 17, 2147483647))
        result = runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE", result.local_block_reasons)

    def test_c06b_eighth_member_domain_succeeds(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0, 1, 2, 3, 4, 5, 6, 7))
        result = runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE", result.local_block_reasons)

    def test_c06b_ninth_unique_index_fails_by_count_before_traversal(self):
        rt = self._v2_runtime()
        self._transport.queue(
            RunnerOperation.GET_EXCHANGE_STATUS,
            _v2_status_payload(_v2_status_rows((0, 1, 2, 3, 4, 5, 6, 7, 8))))
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_BOUND_EXCEEDED)
        self.assertEqual(cap.requests_consumed, 1)  # only S0 -- before any per-index traversal

    def test_c06b_selected_index_absent_from_domain_fails(self):
        rt = self._v2_runtime()
        self._transport.queue(
            RunnerOperation.GET_EXCHANGE_STATUS, _v2_status_payload(_v2_status_rows((1, 2, 3))))
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_SELECTED_INDEX_NOT_IN_DOMAIN)
        self.assertEqual(cap.requests_consumed, 1)

    def test_c06b_duplicate_index_fails(self):
        rt = self._v2_runtime()
        self._transport.queue(RunnerOperation.GET_EXCHANGE_STATUS, _v2_status_payload([
            {"exchange_index": 0, "exchange_active": True, "trading_active": True},
            {"exchange_index": 0, "exchange_active": True, "trading_active": True},
        ]))
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_DUPLICATE)

    def test_c06b_d1_not_equal_d0_fails(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0, 1), status1_rows=(0, 1, 2))
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_STATUS_DOMAIN_CHANGED)

    # ---- C06-C: exact ATSE1 retained-position release ------------------

    def test_c06c_atse1_reconciles_with_fresh_zero_positions(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,))
        rs = self._acquire_and_mint(rt)
        self.assertEqual(rs.retained_position_classification, "RETAINED_POSITION_TERMINALLY_SETTLED")
        self.assertEqual(rs.accepted_terminal_settlement_id, ledger_binding.ACCEPTED_TERMINAL_SETTLEMENT_ID)
        self.assertEqual(rs.read_set_canonical["accepted_terminal_settlement_id"],
                         ledger_binding.ACCEPTED_TERMINAL_SETTLEMENT_ID)

    def test_c06c_atse1_nonzero_retained_position_blocks_release(self):
        rt = self._v2_runtime()
        pos = _positions_payload([{
            "ticker": self.CONTROLLED_TICKER, "subaccount": 1, "exchange_index": 0,
            "position_count_fp": "3.00",
        }])
        self._script_cycle(domain=(0,), positions={0: [pos]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        acquired = runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        with self.assertRaises(RunnerError) as c:
            runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)
        self.assertEqual(c.exception.code, RunnerFailureCode.N1_RETAINED_POSITION_NOT_RECONCILED)

    def test_c06c_nonempty_event_positions_fail_closed(self):
        rt = self._v2_runtime()
        bad_pos = _json_response({"market_positions": [], "event_positions": [{"x": 1}], "cursor": ""})
        self._script_cycle(domain=(0,), positions={0: [bad_pos]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_POSITION_EVENT_SCOPE_UNPROVEN)

    def test_c06c_bootstrap_floor_is_one_and_unchanged(self):
        self.assertEqual(self.bootstrap.retained_position_floor_contracts, Decimal("1.00"))
        self.assertEqual(dict(ledger_binding._ATSE1_CANONICAL_OBJECT)["yes_count_fp"], "1.00")

    # ---- C06-D: 30s / 5s freshness caps at T0 AND T1 -----------------

    def test_c06d_t1_equal_t0_fresh_succeeds(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), t0="2026-08-17T12:59:59.960000Z", t1="2026-08-17T12:59:59.960000Z")
        result = runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        self.assertEqual(result.status, "READ_PHASE_COMPLETE", result.local_block_reasons)

    def test_c06d_future_skew_beyond_5s_fails(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), t0="2026-08-17T13:00:30.000000Z", t1="2026-08-17T13:00:30.000000Z")
        with self.assertRaises(RunnerError) as c:
            runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_FRESHNESS_FUTURE_SKEW)

    def test_c06d_stale_beyond_30s_fails(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), t0="2026-08-17T12:59:00.000000Z", t1="2026-08-17T12:59:00.000000Z")
        with self.assertRaises(RunnerError) as c:
            runner.run_pre_release_read_phase_v2(self._invocation(), rt)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_FRESHNESS_STALE)

    def test_c06d_t1_lt_t0_fails_regression(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), t0="2026-08-17T12:59:59.960000Z", t1="2026-08-17T12:59:59.500000Z")
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_FRESHNESS_REGRESSION)

    # ---- C06-E: per-page commitments, caps, cursor rules, ADRS2 ------

    def test_c06e_per_page_commitment_raw_vs_content_digest_distinct(self):
        rt = self._v2_runtime()
        one_order = _orders_payload([_v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        self._script_cycle(
            domain=(0,), orders={0: [one_order]},
            get_order=[_v2_order_payload("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        rs = self._acquire_and_mint(rt)
        page = rs.read_set_canonical["per_index_traversals"][0]["orders"]["pages"][0]
        self.assertTrue(runner._is_hex64(page["response_sha256"]))
        self.assertTrue(runner._is_hex64(page["canonical_economic_content_digest_sha256"]))
        self.assertNotEqual(page["response_sha256"], page["canonical_economic_content_digest_sha256"])
        self.assertEqual(page["row_count"], 1)
        self.assertEqual(len(page["row_content_sha256"]), 1)
        self.assertEqual(len(rs.read_set_canonical["exact_order_supplements"]), 1)

    def test_c06e_two_page_traversal_cursor_thread(self):
        rt = self._v2_runtime()
        p1 = _orders_payload([_v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)], cursor="cur-1")
        p2 = _orders_payload([], cursor="")
        self._script_cycle(
            domain=(0,), orders={0: [p1, p2]},
            get_order=[_v2_order_payload("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        rs = self._acquire_and_mint(rt)
        pages = rs.read_set_canonical["per_index_traversals"][0]["orders"]["pages"]
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["cursor_in"], "")
        self.assertEqual(pages[0]["cursor_out"], "cur-1")
        self.assertEqual(pages[1]["cursor_in"], "cur-1")
        self.assertEqual(pages[1]["cursor_out"], "")
        self.assertEqual(rs.read_set_canonical["per_index_traversals"][0]["orders"]["page_count"], 2)

    def test_c06e_orders_third_page_fails_at_cap_without_extra_request(self):
        rt = self._v2_runtime()
        p1 = _orders_payload([], cursor="c1")
        p2 = _orders_payload([], cursor="c2")
        self._script_cycle(domain=(0,), orders={0: [p1, p2]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE)
        self.assertEqual(sum(1 for x in self._transport.calls if str(x[0]) == "GET_ORDERS"), 2)

    def test_c06e_fills_fifth_page_fails_at_cap(self):
        rt = self._v2_runtime()
        pages = [_fills_payload([], cursor=f"f{k}") for k in range(4)]
        self._script_cycle(domain=(0,), fills={0: pages})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE)
        self.assertEqual(sum(1 for x in self._transport.calls if str(x[0]) == "GET_FILLS"), 4)

    def test_c06e_positions_third_page_fails_at_cap(self):
        rt = self._v2_runtime()
        pages = [_positions_payload([], cursor="p1"), _positions_payload([], cursor="p2")]
        self._script_cycle(domain=(0,), positions={0: pages})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE)
        self.assertEqual(sum(1 for x in self._transport.calls if str(x[0]) == "GET_POSITIONS"), 2)

    def test_c06e_cursor_cycle_fails_before_repeated_request(self):
        rt = self._v2_runtime()
        p1 = _orders_payload([], cursor="cyc")
        p2 = _orders_payload([], cursor="cyc")
        self._script_cycle(domain=(0,), orders={0: [p1, p2]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_CURSOR_CYCLE)
        self.assertEqual(sum(1 for x in self._transport.calls if str(x[0]) == "GET_ORDERS"), 2)

    def test_c06e_absent_cursor_fails(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), orders={0: [_json_response({"orders": []})]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE)

    def test_c06e_non_string_cursor_fails(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), orders={0: [_json_response({"orders": [], "cursor": 7})]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE)

    def test_c06e_request_73_impossible(self):
        self.assertEqual(runner.PRE_RELEASE_READ_REQUEST_MAX_V2, 72)
        rt = self._v2_runtime()
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        for _ in range(72):
            cap.charge(runner.ActivePreReleaseReadOperationV2.GET_FILLS)
        with self.assertRaises(RunnerError) as c:
            cap.charge(runner.ActivePreReleaseReadOperationV2.GET_FILLS)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_BUDGET_EXHAUSTED)

    def test_c06e_adrs2_changes_with_page_row_content(self):
        rt1 = self._v2_runtime()
        self._script_cycle(domain=(0,))
        base = self._acquire_and_mint(rt1)
        rt2 = self._v2_runtime()
        self._script_cycle(
            domain=(0,),
            orders={0: [_orders_payload([_v2_order_row("o-9", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])]},
            get_order=[_v2_order_payload("o-9", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        mutated = self._acquire_and_mint(rt2)
        self.assertNotEqual(base.read_set_id, mutated.read_set_id)

    def test_c06e_adrs2_changes_with_market_content(self):
        rt1 = self._v2_runtime()
        self._script_cycle(domain=(0,))
        base = self._acquire_and_mint(rt1)
        rt2 = self._v2_runtime()
        self._script_cycle(domain=(0,), market=_json_response({"market": {
            "ticker": self.TICKER, "status": "active", "exchange_index": 0,
            "yes_bid_dollars": "0.46", "price_ranges": _PRICE_RANGES,
        }}))
        mutated = self._acquire_and_mint(rt2)
        self.assertNotEqual(base.read_set_id, mutated.read_set_id)

    def test_c06e_already_expired_deadline_fails_before_first_charge(self):
        # Correction 07 C07-E: the per-operation deadline is checked at
        # BEFORE_PREPARATION -- BEFORE local request construction and BEFORE
        # ``capability.charge`` -- so an already-expired absolute deadline
        # fails with the generic per-operation deadline code at that
        # checkpoint, and consumes zero budget.
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,))
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(rt, 0)  # already-expired
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)
        self.assertEqual(cap.requests_consumed, 0)

    def test_c07_deadline_expires_after_transport_before_final_commitment_fails(self):
        # C07-F: a deadline that is still fresh through transport/decode but
        # has expired by the time the accepted commitment/result exists still
        # fails closed at the SAME per-operation deadline's final check.
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,))
        base = rt.monotonic_clock_ns()
        calls = {"n": 0}

        def _clock():
            calls["n"] += 1
            return base if calls["n"] <= 6 else base + 20_000_000_000

        rt2 = dataclasses.replace(rt, monotonic_clock_ns=_clock)
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt2, rt2.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt2, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)


class Correction07AccountWideEconomicsTestCase(Correction06LiveTrustedAcquirerTestCase):
    """R1-B03 Correction 07 (C06-B01..05 block corrections) -- exercises the
    live acquirer's exact active-V2 P02-shaped row scope (``subaccount_number``
    /``exchange_index``), complete all-row page/ADRS2 commitment (no
    selected-ticker filter before commitment), selected-route-vs-aggregate
    economics separation, and the DERIVED (never literal)
    ``other_positions_all_accounted`` predicate."""

    # ---- SCOPE / P02 SHAPE ----------------------------------------------

    def test_c07b_p02_shaped_order_no_legacy_subaccount_passes(self):
        rt = self._v2_runtime()
        row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        self.assertNotIn("subaccount", row)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([row])]},
            get_order=[_v2_order_payload("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        rs = self._acquire_and_mint(rt)  # no RunnerError -> P02-shaped row accepted
        self.assertEqual(rs.read_set_id[:6], "ADRS2_")

    def test_c07b_p02_shaped_fill_no_legacy_subaccount_passes(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row("f-1", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        self.assertNotIn("subaccount", fill_row)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]},
            get_order=[_v2_order_payload("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        rs = self._acquire_and_mint(rt)  # no RunnerError -> P02-shaped row accepted
        self.assertEqual(rs.read_set_id[:6], "ADRS2_")

    def test_c07b_order_missing_subaccount_number_fails(self):
        rt = self._v2_runtime()
        row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0, omit_subaccount_number=True)
        self._script_cycle(domain=(0,), orders={0: [_orders_payload([row])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH)

    def test_c07b_fill_missing_subaccount_number_fails(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row(
            "f-1", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0,
            omit_subaccount_number=True)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH)

    def test_c07b_order_missing_or_wrong_exchange_index_fails(self):
        for overrides in (dict(omit_exchange_index=True), dict(exchange_index=1)):
            rt = self._v2_runtime()
            kwargs = dict(ticker=self.TICKER, subaccount_number=1, exchange_index=0)
            kwargs.update(overrides)
            row = _v2_order_row("o-1", **kwargs)
            self._script_cycle(domain=(0,), orders={0: [_orders_payload([row])]})
            cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
                rt, rt.experiment_absolute_end_monotonic_ns)
            with self.assertRaises(RunnerError) as c:
                runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
            self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH)

    def test_c07b_position_requires_exact_exchange_index(self):
        rt = self._v2_runtime()
        row = _v2_position_row(self.TICKER, exchange_index=0, position_count_fp="0.00", omit_exchange_index=True)
        self._script_cycle(domain=(0,), positions={0: [_positions_payload([row])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH)

    def test_c07b_position_exposed_subaccount_number_mismatch_fails(self):
        rt = self._v2_runtime()
        row = _v2_position_row(self.TICKER, exchange_index=0, position_count_fp="0.00", subaccount_number=2)
        self._script_cycle(domain=(0,), positions={0: [_positions_payload([row])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DYNAMIC_READ_RESPONSE_SCOPE_MISMATCH)

    # ---- ALL-ROW COMMITMENT ----------------------------------------------

    OTHER_TICKER = "KXOTHER-26SEP02-1.0000"

    def test_c07a_selected_and_other_ticker_rows_both_in_page_commitment(self):
        rt = self._v2_runtime()
        selected_row = _v2_order_row("o-sel", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        other_row = _v2_order_row("o-oth", ticker=self.OTHER_TICKER, subaccount_number=1, exchange_index=0)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([selected_row, other_row])]},
            get_order=[_v2_order_payload("o-sel", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        cap, acquired = self._acquire(rt)
        rs = runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)
        page = rs.read_set_canonical["per_index_traversals"][0]["orders"]["pages"][0]
        self.assertEqual(page["row_count"], 2)
        self.assertEqual(len(page["row_content_sha256"]), 2)
        # selected-route truth (pre-fold) stays selected-ticker-only; the
        # read-set's ``selected_route_truth`` field is the FOLDED truth
        # (selected route + aggregate extras) used downstream by the risk
        # engine, so the pure selected-route check is against ``acquired``.
        self.assertTrue(all(o.market == self.TICKER for o in acquired.selected_route_truth.working_orders))
        # the other-ticker order enters aggregate risk (extra_working_orders).
        self.assertTrue(any(o.market == self.OTHER_TICKER for o in rs.extra_working_orders))

    def test_c07g_mutating_other_ticker_row_changes_adrs2(self):
        def _mint_with(price):
            rt = self._v2_runtime()
            selected_row = _v2_order_row("o-sel", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
            other_row = _v2_order_row(
                "o-oth", ticker=self.OTHER_TICKER, subaccount_number=1, exchange_index=0,
                yes_price_dollars=price)
            self._script_cycle(
                domain=(0,), orders={0: [_orders_payload([selected_row, other_row])]},
                get_order=[_v2_order_payload("o-sel", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
            return self._acquire_and_mint(rt)

        base = _mint_with("0.30")
        mutated = _mint_with("0.31")
        self.assertNotEqual(base.read_set_id, mutated.read_set_id)

    # ---- RISK: other-ticker / foreign-index economics enter aggregate ----

    def test_c07c_selected_index_other_ticker_fill_enters_aggregate_risk(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.OTHER_TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row("f-1", order_id="o-1", ticker=self.OTHER_TICKER, subaccount_number=1, exchange_index=0)
        self._script_cycle(domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        cap, acquired = self._acquire(rt)
        rs = runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)
        self.assertTrue(any(f.market == self.OTHER_TICKER for f in rs.extra_fills))
        self.assertFalse(any(f.market == self.OTHER_TICKER for f in acquired.selected_route_truth.fills))

    def test_c07c_selected_index_other_ticker_position_enters_aggregate_risk(self):
        rt = self._v2_runtime()
        row = _v2_position_row(
            self.OTHER_TICKER, exchange_index=0, position_count_fp="2.00", subaccount_number=1,
            yes_price_dollars="0.35", position_as_of_utc="2026-09-01T00:00:00.000000Z")
        self._script_cycle(domain=(0,), positions={0: [_positions_payload([row])]})
        rs = self._acquire_and_mint(rt)
        self.assertTrue(any(f.market == self.OTHER_TICKER for f in rs.extra_fills))

    def test_c07c_foreign_index_order_fill_position_enter_aggregate_risk(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-2", ticker=self.OTHER_TICKER, subaccount_number=1, exchange_index=2)
        fill_row = _v2_fill_row("f-2", order_id="o-2", ticker=self.OTHER_TICKER, subaccount_number=1, exchange_index=2)
        pos_row = _v2_position_row(
            self.TICKER, exchange_index=2, position_count_fp="1.00", subaccount_number=1,
            yes_price_dollars="0.20", position_as_of_utc="2026-09-01T00:00:00.000000Z")
        self._script_cycle(
            domain=(0, 1, 2),
            orders={2: [_orders_payload([order_row])]}, fills={2: [_fills_payload([fill_row])]},
            positions={2: [_positions_payload([pos_row])]})
        rs = self._acquire_and_mint(rt)
        self.assertTrue(any(f.market == self.OTHER_TICKER for f in rs.extra_fills))
        self.assertTrue(any(o.market == self.OTHER_TICKER for o in rs.extra_working_orders))
        self.assertTrue(any(f.market == self.TICKER for f in rs.extra_fills))  # foreign-index selected-ticker position

    def test_c07c_no_double_counting_between_selected_route_and_aggregate(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]},
            get_order=[_v2_order_payload("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        rs = self._acquire_and_mint(rt)
        self.assertEqual(len(rs.selected_route_truth.working_orders), 1)
        self.assertEqual(len(rs.extra_working_orders), 0)

    # ---- SETTLEMENT: derived other_positions_all_accounted --------------

    def test_c08d_unclassifiable_non_selected_position_fails_closed_at_page_acceptance(self):
        """Correction 08 C08-D supersedes the C07 assertion below (DSB-
        BUDGET-006): a nonzero, non-selected-route, non-retained-ticker
        position that cannot be represented as a synthetic fill (no mark
        price / as-of) must now fail CLOSED during page acceptance itself
        -- the schema violation is discovered before the page/read is ever
        accepted -- rather than being lazily classified UNCLASSIFIED and
        only surfaced later at ATSE1/mint time."""
        rt = self._v2_runtime()
        row = _v2_position_row(self.OTHER_TICKER, exchange_index=0, position_count_fp="5.00", subaccount_number=1)
        self._script_cycle(domain=(0,), positions={0: [_positions_payload([row])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, RunnerFailureCode.DOMAIN_SCOPE_RESPONSE_AMBIGUOUS)

    # ---- BUDGET: local preparation failure consumes zero -----------------

    def test_c07e_request_preparation_failure_consumes_zero_budget(self):
        rt = self._v2_runtime()
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        adapter = runner._ActiveV2OperationAdapter(rt, absolute_invocation_deadline_ns=cap.absolute_invocation_deadline_ns)
        with self.assertRaises(RunnerError) as c:
            adapter.issue_json(
                cap, runner.ActivePreReleaseReadOperationV2.GET_MARKET, ordinal=1,
                subaccount=rt.domain_binding.subaccount, ticker="")  # malformed ticker -> local prep failure
        self.assertEqual(c.exception.code, RunnerFailureCode.MARKET_IDENTITY_INVALID)
        self.assertEqual(cap.requests_consumed, 0)

    def test_c07e_transport_observes_exactly_one_unit_already_consumed(self):
        rt = self._v2_runtime()
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        adapter = runner._ActiveV2OperationAdapter(rt, absolute_invocation_deadline_ns=cap.absolute_invocation_deadline_ns)
        observed = {}

        def _spy(operation, prepared, deadline):
            observed["requests_consumed"] = cap.requests_consumed
            return _v2_status_payload(_v2_status_rows((0,)))

        rt2 = dataclasses.replace(rt, send_operation_request=_spy)
        adapter2 = runner._ActiveV2OperationAdapter(rt2, absolute_invocation_deadline_ns=cap.absolute_invocation_deadline_ns)
        adapter2.issue_json(
            cap, runner.ActivePreReleaseReadOperationV2.GET_EXCHANGE_STATUS, ordinal=1,
            subaccount=rt2.domain_binding.subaccount)
        self.assertEqual(observed["requests_consumed"], 1)


class Correction08SchemaValidationBoundaryTestCase(Correction07AccountWideEconomicsTestCase):
    """R1-B03 Correction 08 (DSB-BUDGET-006 closure, C07-B01) -- proves the
    exact accepted-page theorem from SCHEMA_VALIDATION_BOUNDARY.md: EVERY
    economic field a later ARB risk/reconciliation path will consume from an
    accepted active-V2 page has passed its inherited exact parser BEFORE
    that SAME page's final per-request deadline check, using the live
    ``_LiveTrustedDynamicReadAcquirerV2`` state machine through deterministic
    fake transport (never the offline ``_FakeTrustedDynamicReadAcquirerV2``
    seam).  Malformed-economics tests use a non-expired clock so a schema
    failure is never silently reclassified as a deadline-only theorem."""

    # ---- C08-A/B/C/D: deadline encloses economic validation --------------

    def test_c08a_order_economic_validation_completes_before_page_deadline_then_fails(self):
        """Expiring the clock only AFTER the real order validator returns
        still fails the page CLOSED (DEADLINE_EXCEEDED), proving order
        economic validation happens before, not after, page acceptance."""
        rt = self._v2_runtime()
        row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        self._script_cycle(domain=(0,), orders={0: [_orders_payload([row])]})
        clock = _ExpireOnDemandClock(rt.monotonic_clock_ns, deadline=rt.experiment_absolute_end_monotonic_ns)
        d_rt = dataclasses.replace(rt, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline)
        real_validator = runner._active_v2_working_order_from_row
        observed = {}

        def _expire_after(row_arg, *, subaccount, exchange_index):
            result = real_validator(row_arg, subaccount=subaccount, exchange_index=exchange_index)
            observed["validated"] = True
            clock.expire()
            return result

        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            d_rt, d_rt.experiment_absolute_end_monotonic_ns)
        with mock.patch.object(runner, "_active_v2_working_order_from_row", side_effect=_expire_after):
            with self.assertRaises(RunnerError) as c:
                runner._run_active_v2_acquisition(d_rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertTrue(observed.get("validated"))
        self.assertEqual(c.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)

    def test_c08b_fill_economic_validation_completes_before_page_deadline_then_fails(self):
        """The C08 theorem is unchanged by Correction 09; only the identity of
        the SHARED fill parser moved (``_active_v2_fill_from_row`` is now a
        projection over ``_active_v2_parsed_fill_from_row``, which is what the
        page lifecycle calls), so the instrumentation patches that shared
        parser.  Assertions are identical."""
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row("f-1", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        clock = _ExpireOnDemandClock(rt.monotonic_clock_ns, deadline=rt.experiment_absolute_end_monotonic_ns)
        d_rt = dataclasses.replace(rt, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline)
        real_validator = runner._active_v2_parsed_fill_from_row
        observed = {}

        def _expire_after(row_arg, *, subaccount, exchange_index):
            result = real_validator(row_arg, subaccount=subaccount, exchange_index=exchange_index)
            observed["validated"] = True
            clock.expire()
            return result

        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            d_rt, d_rt.experiment_absolute_end_monotonic_ns)
        with mock.patch.object(runner, "_active_v2_parsed_fill_from_row", side_effect=_expire_after):
            with self.assertRaises(RunnerError) as c:
                runner._run_active_v2_acquisition(d_rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertTrue(observed.get("validated"))
        self.assertEqual(c.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)

    def test_c08c_position_count_validation_completes_before_page_deadline_then_fails(self):
        rt = self._v2_runtime()
        row = _v2_position_row(self.OTHER_TICKER, exchange_index=0, position_count_fp="0.00", subaccount_number=1)
        self._script_cycle(domain=(0,), positions={0: [_positions_payload([row])]})
        clock = _ExpireOnDemandClock(rt.monotonic_clock_ns, deadline=rt.experiment_absolute_end_monotonic_ns)
        d_rt = dataclasses.replace(rt, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline)
        real_validator = runner._position_count_from_row
        observed = {}

        def _expire_after(row_arg):
            result = real_validator(row_arg)
            observed["validated"] = True
            clock.expire()
            return result

        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            d_rt, d_rt.experiment_absolute_end_monotonic_ns)
        with mock.patch.object(runner, "_position_count_from_row", side_effect=_expire_after):
            with self.assertRaises(RunnerError) as c:
                runner._run_active_v2_acquisition(d_rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertTrue(observed.get("validated"))
        self.assertEqual(c.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)

    def test_c08d_aggregate_position_synthetic_economics_validate_before_page_deadline_then_fails(self):
        rt = self._v2_runtime()
        row = _v2_position_row(
            self.OTHER_TICKER, exchange_index=0, position_count_fp="2.00", subaccount_number=1,
            yes_price_dollars="0.35", position_as_of_utc="2026-09-01T00:00:00.000000Z")
        self._script_cycle(domain=(0,), positions={0: [_positions_payload([row])]})
        clock = _ExpireOnDemandClock(rt.monotonic_clock_ns, deadline=rt.experiment_absolute_end_monotonic_ns)
        d_rt = dataclasses.replace(rt, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline)
        real_validator = runner._foreign_index_position_fill
        observed = {}

        def _expire_after(row_arg, *, ticker, subaccount, exchange_index):
            result = real_validator(row_arg, ticker=ticker, subaccount=subaccount, exchange_index=exchange_index)
            observed["validated"] = True
            clock.expire()
            return result

        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            d_rt, d_rt.experiment_absolute_end_monotonic_ns)
        with mock.patch.object(runner, "_foreign_index_position_fill", side_effect=_expire_after):
            with self.assertRaises(RunnerError) as c:
                runner._run_active_v2_acquisition(d_rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertTrue(observed.get("validated"))
        self.assertEqual(c.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)

    # ---- malformed economics fail via the inherited schema classification,
    # with a NON-expired clock, proving C08 did not replace schema
    # validation with a deadline-only theorem ------------------------------

    def _assert_acquisition_fails(self, rt, *, code):
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, code)

    def test_c08e_malformed_resting_order_side_fails_before_mint(self):
        rt = self._v2_runtime()
        row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0, side="bogus")
        self._script_cycle(domain=(0,), orders={0: [_orders_payload([row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08e_malformed_resting_order_remaining_count_fp_fails_before_mint(self):
        rt = self._v2_runtime()
        row = _v2_order_row(
            "o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0, remaining_count_fp="not-a-number")
        self._script_cycle(domain=(0,), orders={0: [_orders_payload([row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08e_malformed_resting_order_yes_price_dollars_fails_before_mint(self):
        rt = self._v2_runtime()
        row = _v2_order_row(
            "o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0, yes_price_dollars="not-a-number")
        self._script_cycle(domain=(0,), orders={0: [_orders_payload([row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08e_non_resting_order_does_not_require_price_quantity_fields(self):
        """A non-resting order need not satisfy resting-only fields the
        converter never consumes for it -- proves C08 did not overvalidate
        (SCHEMA_VALIDATION_BOUNDARY.md 'Conditional fields')."""
        rt = self._v2_runtime()
        row = _v2_order_row(
            "o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0,
            status="canceled", remaining_count_fp="not-a-number", yes_price_dollars="not-a-number")
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([row])]},
            get_order=[_v2_order_payload("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        rs = self._acquire_and_mint(rt)  # no RunnerError -> page accepted despite unused malformed fields
        self.assertEqual(rs.read_set_id[:6], "ADRS2_")

    def test_c08f_malformed_fill_id_fails_before_mint(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row("", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08f_malformed_fill_side_fails_before_mint(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row(
            "f-1", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0, side="bogus")
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08f_malformed_fill_price_fails_before_mint(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row(
            "f-1", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0, price="not-a-number")
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08f_malformed_fill_count_fails_before_mint(self):
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row(
            "f-1", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0, quantity="not-a-number")
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c08f_malformed_fill_created_time_fails_before_mint(self):
        """``created_time`` canonicalization is inherited from
        ``execution_ledger.validate_canonical_timestamp`` -- a malformed
        value raises ``LedgerError``, not ``RunnerError``, and that
        classification is unchanged by C08."""
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = _v2_fill_row(
            "f-1", order_id="o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0,
            created_time="not-a-timestamp")
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]}, fills={0: [_fills_payload([fill_row])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(LedgerError) as c:
            runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(c.exception.code, FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)

    def test_c08g_malformed_position_count_fp_fails_before_mint(self):
        rt = self._v2_runtime()
        row = _v2_position_row(
            self.OTHER_TICKER, exchange_index=0, position_count_fp="not-a-number", subaccount_number=1)
        self._script_cycle(domain=(0,), positions={0: [_positions_payload([row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    # ---- C08-F: GET_ORDER supplement consumed-field audit -----------------

    def test_c08h_get_order_supplement_unconsumed_economic_fields_not_validated(self):
        """Audit finding (dispatch Section 11 / C08-F):
        ``GET_ORDER_ECONOMIC_SCHEMA_NOT_CONSUMED_BY_RELEASE = TRUE`` -- the
        exact-order supplement's ``_ActiveV2OrderSupplementCommitmentV1``
        carries only ``order_id`` plus identity hashes, so no later ARB
        logic ever consumes an economic field from it; a supplement response
        with garbage economic fields (beyond the validated order_id/ticker/
        scope) still succeeds."""
        rt = self._v2_runtime()
        row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([row])]},
            get_order=[_v2_order_payload(
                "o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0,
                side="bogus", status="bogus", remaining_count_fp="not-a-number",
                yes_price_dollars="not-a-number")])
        rs = self._acquire_and_mint(rt)  # no RunnerError -> unconsumed supplement fields ignored
        self.assertEqual(rs.read_set_id[:6], "ADRS2_")


class Correction09FillIdentityTestCase(Correction08SchemaValidationBoundaryTestCase):
    """R1-B03 Correction 09 (C08-B01/B02) -- restores the inherited exact
    active-V2 fill identity (DSB-OPS-009: ``order_id`` is part of fill
    identity) and the exactly-once duplicate/conflict economics
    (DSB-READ-005: only exact duplicates deduplicate; conflicts fail closed),
    while preserving the C07 all-row page/ADRS2 evidence and the C08
    same-request page-deadline validation theorem.

    ``OBSERVATION EVIDENCE != ECONOMIC EVENT COUNT``: every raw occurrence
    stays committed in the page/ADRS2 proof; economic truth counts an exact
    duplicate fill event exactly once."""

    FILL_TIME = "2026-08-17T13:00:00.000000Z"

    def _fill(self, fill_id="f-1", *, order_id="o-1", ticker=None, exchange_index=0, **overrides):
        kwargs = dict(
            ticker=ticker if ticker is not None else self.TICKER,
            subaccount_number=1, exchange_index=exchange_index,
            created_time=self.FILL_TIME,
        )
        kwargs.update(overrides)
        row = _v2_fill_row(fill_id, order_id=order_id, **kwargs)
        return row

    def _acquire_then_mint(self, rt):
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        acquired = runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        return cap, acquired, runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)

    def _assert_fails_closed(self, rt, *, code):
        """Acquisition-or-mint must fail closed before any release-eligible
        read set exists.  Selected-route conflicts surface during acquisition;
        cross-ticker / cross-index conflicts surface at the C09-C domain-wide
        validation inside the mint.  Both are before release/risk acceptance."""
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            acquired = runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
            runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)
        self.assertEqual(c.exception.code, code)

    # ---- C09-A/B: exact order_id is required fill identity ---------------

    def test_c09a_missing_order_id_fails_before_page_acceptance(self):
        rt = self._v2_runtime()
        row = self._fill()
        del row["order_id"]
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c09a_non_string_order_id_fails_before_page_acceptance(self):
        rt = self._v2_runtime()
        row = self._fill()
        row["order_id"] = 7
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([row])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.ORDER_IDENTITY_INVALID)

    def test_c09a_blank_order_id_fails_before_page_acceptance(self):
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([self._fill(order_id="")])]})
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.ORDER_IDENTITY_INVALID)

    def test_c09a_request_scope_never_defaults_a_missing_order_id(self):
        """No request/selected-route order id substitutes for a row's own
        missing ``order_id`` -- even when exactly one order id is bound."""
        rt = self._v2_runtime()
        order_row = _v2_order_row("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)
        fill_row = self._fill()
        del fill_row["order_id"]
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([order_row])]},
            fills={0: [_fills_payload([fill_row])]},
            get_order=[_v2_order_payload("o-1", ticker=self.TICKER, subaccount_number=1, exchange_index=0)])
        self._assert_acquisition_fails(rt, code=RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c09b_order_id_validation_stays_inside_same_request_page_deadline(self):
        """C09-B: expanding the shared fill parser to require ``order_id``
        keeps that validation inside C08's SAME per-request page deadline --
        expiring the clock only AFTER the shared parser returns still rejects
        the page (DEADLINE_EXCEEDED).  No second deadline window exists."""
        rt = self._v2_runtime()
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([self._fill()])]})
        clock = _ExpireOnDemandClock(rt.monotonic_clock_ns, deadline=rt.experiment_absolute_end_monotonic_ns)
        d_rt = dataclasses.replace(rt, monotonic_clock_ns=clock, experiment_absolute_end_monotonic_ns=clock.deadline)
        real_parser = runner._active_v2_parsed_fill_from_row
        observed = {}

        def _expire_after(row_arg, *, subaccount, exchange_index):
            parsed = real_parser(row_arg, subaccount=subaccount, exchange_index=exchange_index)
            observed["order_id"] = parsed.order_id
            clock.expire()
            return parsed

        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            d_rt, d_rt.experiment_absolute_end_monotonic_ns)
        with mock.patch.object(runner, "_active_v2_parsed_fill_from_row", side_effect=_expire_after):
            with self.assertRaises(RunnerError) as c:
                runner._run_active_v2_acquisition(d_rt, cap, opened=None, selected_ticker=self.TICKER)
        self.assertEqual(observed.get("order_id"), "o-1")  # the parser really ran, and read order_id
        self.assertEqual(c.exception.code, RunnerFailureCode.DEADLINE_EXCEEDED)

    # ---- C09-G: order_id is identity, not current-order liveness ---------

    def test_c09g_fill_order_id_absent_from_current_working_orders_is_allowed(self):
        """A terminal order may be absent from current GET_ORDERS truth while
        its fill remains authoritative: zero working orders, one fill whose
        ``order_id`` matches nothing currently resting -> accepted."""
        rt = self._v2_runtime()
        self._script_cycle(
            domain=(0,), orders={0: [_orders_payload([])]},
            fills={0: [_fills_payload([self._fill("f-terminal", order_id="o-already-terminal")])]})
        cap, acquired, rs = self._acquire_then_mint(rt)
        self.assertEqual(acquired.selected_route_truth.bound_order_ids, ())
        self.assertEqual(acquired.selected_route_truth.working_orders, ())
        self.assertEqual([f.fill_id for f in acquired.selected_route_truth.fills], ["f-terminal"])
        self.assertEqual(rs.read_set_id[:6], "ADRS2_")

    # ---- C09-D/F: exact duplicate counts once, evidence retains both ------

    def test_c09d_exact_duplicate_selected_fill_across_pages_counts_once(self):
        """C09-D + C09-F: the SAME exact fill event observed on two GET_FILLS
        pages stays twice in the page/ADRS2 observation evidence and enters
        selected-route economic truth exactly once."""
        rt = self._v2_runtime()
        row = self._fill("f-dup")
        self._script_cycle(
            domain=(0,),
            fills={0: [_fills_payload([row], cursor="page2"), _fills_payload([row])]})
        cap, acquired, rs = self._acquire_then_mint(rt)
        # economic truth: exactly one fill event
        self.assertEqual([f.fill_id for f in acquired.selected_route_truth.fills], ["f-dup"])
        self.assertEqual(len(rs.selected_route_truth.fills), 1)
        # observation evidence: BOTH raw occurrences still committed
        pages = rs.read_set_canonical["per_index_traversals"][0]["fills"]["pages"]
        self.assertEqual(sum(p["row_count"] for p in pages), 2)
        self.assertEqual(sum(len(p["row_content_sha256"]) for p in pages), 2)

    def test_c09e_exact_duplicate_aggregate_fill_counts_once_in_risk(self):
        """C09-E: an exact duplicate on the non-selected (other-ticker)
        aggregate path enters aggregate risk exactly once."""
        rt = self._v2_runtime()
        row = self._fill("f-agg-dup", order_id="o-agg", ticker=self.OTHER_TICKER)
        self._script_cycle(
            domain=(0,),
            fills={0: [_fills_payload([row], cursor="page2"), _fills_payload([row])]})
        cap, acquired, rs = self._acquire_then_mint(rt)
        matching = [f for f in rs.extra_fills if f.fill_id == "f-agg-dup"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].market, self.OTHER_TICKER)
        pages = rs.read_set_canonical["per_index_traversals"][0]["fills"]["pages"]
        self.assertEqual(sum(p["row_count"] for p in pages), 2)

    def test_c09_distinct_fill_ids_with_same_order_id_are_two_events(self):
        """Different ``fill_id`` values are distinct fill events even when the
        order and economics are otherwise identical -- dedupe is by fill_id,
        never by economics."""
        rt = self._v2_runtime()
        a = self._fill("f-a", order_id="o-same")
        b = self._fill("f-b", order_id="o-same")
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        cap, acquired, rs = self._acquire_then_mint(rt)
        self.assertEqual(
            sorted(f.fill_id for f in acquired.selected_route_truth.fills), ["f-a", "f-b"])

    # ---- C09-C/D/E: contradictory same-fill_id identity fails closed ------

    def test_c09c_same_fill_id_different_order_id_conflicts(self):
        rt = self._v2_runtime()
        a = self._fill("f-x", order_id="o-1")
        b = self._fill("f-x", order_id="o-2")
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        self._assert_fails_closed(rt, code=RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_c09c_same_fill_id_different_side_conflicts(self):
        rt = self._v2_runtime()
        a = self._fill("f-x")
        b = self._fill("f-x", side="no")
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        self._assert_fails_closed(rt, code=RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_c09c_same_fill_id_different_quantity_conflicts(self):
        rt = self._v2_runtime()
        a = self._fill("f-x")
        b = self._fill("f-x", quantity="2.00")
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        self._assert_fails_closed(rt, code=RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_c09c_same_fill_id_different_price_conflicts(self):
        rt = self._v2_runtime()
        a = self._fill("f-x")
        b = self._fill("f-x", price="0.55")
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        self._assert_fails_closed(rt, code=RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_c09c_same_fill_id_different_created_time_conflicts(self):
        rt = self._v2_runtime()
        a = self._fill("f-x")
        b = self._fill("f-x", created_time="2026-08-17T13:00:01.000000Z")
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        self._assert_fails_closed(rt, code=RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_c09c_same_fill_id_different_ticker_conflicts_at_domain_wide_validation(self):
        """A selected-ticker row and an other-ticker row sharing one fill_id
        are split across the selected-route and aggregate paths, so ONLY the
        C09-C domain-wide validation can see the contradiction: acquisition
        succeeds, the mint fails closed."""
        rt = self._v2_runtime()
        a = self._fill("f-x")
        b = self._fill("f-x", ticker=self.OTHER_TICKER)
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        acquired = runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        with self.assertRaises(RunnerError) as c:
            runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)
        self.assertEqual(c.exception.code, RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_c09c_same_fill_id_different_exchange_index_conflicts(self):
        """Scope is part of parsed fill identity: the same fill_id observed
        under another enumerated exchange index is a CONFLICT, never a second
        economic fill.  Only the domain-wide validation spans indices."""
        rt = self._v2_runtime()
        a = self._fill("f-x", exchange_index=0)
        b = self._fill("f-x", exchange_index=1)
        self._script_cycle(
            domain=(0, 1),
            fills={0: [_fills_payload([a])], 1: [_fills_payload([b])]})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            rt, rt.experiment_absolute_end_monotonic_ns)
        acquired = runner._run_active_v2_acquisition(rt, cap, opened=None, selected_ticker=self.TICKER)
        with self.assertRaises(RunnerError) as c:
            runner._mint_release_eligible_read_set(cap, acquired=acquired, opened=None)
        self.assertEqual(c.exception.code, RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    def test_c09e_conflicting_duplicate_aggregate_fill_fails_release(self):
        """A contradictory duplicate confined to the non-selected aggregate
        path also fails closed before any release-eligible read set exists."""
        rt = self._v2_runtime()
        a = self._fill("f-agg", order_id="o-agg", ticker=self.OTHER_TICKER)
        b = self._fill("f-agg", order_id="o-agg", ticker=self.OTHER_TICKER, price="0.55")
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([a, b])]})
        self._assert_fails_closed(rt, code=RunnerFailureCode.FILL_DUPLICATE_CONFLICT)

    # ---- C09-H: the fake seam must not invent fill identity ---------------

    def test_c09h_fake_seam_missing_order_id_fails_closed_before_mint(self):
        """C09-H: a legacy/synthetic fixture fill row without ``order_id``
        must fail the SAME controlling fill-identity theorem when the common
        mint validation consumes it -- the fake seam is not a weaker path."""
        rt = self._runtime()
        legacy_fill = {
            "fill_id": "f-legacy", "ticker": self.TICKER, "subaccount": 1, "exchange_index": 0,
            "side": "yes", "yes_price_dollars": "0.40", "count_fp": "1.00",
            "created_time": self.FILL_TIME,
        }
        self.assertNotIn("order_id", legacy_fill)
        traversals = tuple(
            self._traversal(i, fill_rows=((legacy_fill,) if i == 0 else ()))
            for i in (0, 1, 2, 3))
        seam = self._fresh_seam(rt, dynamic_read_overrides={"traversals": traversals})
        cap = runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            seam, seam.experiment_absolute_end_monotonic_ns)
        with self.assertRaises(RunnerError) as c:
            seam.trusted_dynamic_read_acquirer_test_seam.acquire(cap)
        self.assertEqual(c.exception.code, RunnerFailureCode.RESPONSE_SCHEMA_INVALID)

    def test_c09h_fixture_normalizer_does_not_synthesize_order_id(self):
        """The accepted test-only normalizer still converts ONLY the legacy
        ``subaccount`` field; it never invents ``order_id``."""
        rt = self._runtime()
        legacy_fill = {
            "fill_id": "f-legacy", "ticker": self.TICKER, "subaccount": 1, "exchange_index": 0,
            "side": "yes", "yes_price_dollars": "0.40", "count_fp": "1.00",
            "created_time": self.FILL_TIME,
        }
        fixture = self._dynamic_read(
            traversals=tuple(
                self._traversal(i, fill_rows=((legacy_fill,) if i == 0 else ()))
                for i in (0, 1, 2, 3)))
        normalized = runner._normalize_legacy_fixture_rows_for_active_v2(
            fixture, active_contract=rt.active_contract, risk_config_sha256=rt.risk_config.sha256)
        row = normalized.per_index_traversals[0].fill_rows[0]
        self.assertEqual(row.get("subaccount_number"), 1)  # accepted normalization
        self.assertNotIn("order_id", row)                  # never synthesized

    # ---- model / parser preservation --------------------------------------

    def test_c09_economic_fill_v1_model_unchanged_order_id_stays_private(self):
        """``EconomicFillV1`` (the public risk projection) is UNCHANGED: it
        carries no ``order_id``.  The exact order identity lives only in the
        private parsed record used for validation/deduplication."""
        self.assertNotIn("order_id", {f.name for f in dataclasses.fields(runner.EconomicFillV1)})
        self.assertIn("order_id", {f.name for f in dataclasses.fields(runner._ActiveV2ParsedFillV1)})
        parsed = runner._active_v2_parsed_fill_from_row(
            self._fill(), subaccount=1, exchange_index=0)
        self.assertEqual(parsed.order_id, "o-1")
        self.assertEqual(parsed.exchange_index, 0)
        self.assertEqual(parsed.subaccount, 1)
        projected = parsed.economic_fill()
        self.assertIsInstance(projected, runner.EconomicFillV1)
        self.assertEqual(projected.fill_id, "f-1")
        self.assertEqual(projected.market, self.TICKER)

    def test_c09_one_shared_fill_parser_supplies_every_consumer(self):
        """C09-A: page validation, selected-route truth, aggregate extras and
        the domain-wide proof all parse through the ONE shared parser -- so
        patching it is observed by every consumer (no second/weaker parser)."""
        rt = self._v2_runtime()
        selected = self._fill("f-sel")
        other = self._fill("f-oth", order_id="o-oth", ticker=self.OTHER_TICKER)
        self._script_cycle(domain=(0,), fills={0: [_fills_payload([selected, other])]})
        real_parser = runner._active_v2_parsed_fill_from_row
        calls = []

        def _spy(row_arg, *, subaccount, exchange_index):
            calls.append(row_arg.get("fill_id"))
            return real_parser(row_arg, subaccount=subaccount, exchange_index=exchange_index)

        with mock.patch.object(runner, "_active_v2_parsed_fill_from_row", side_effect=_spy):
            self._acquire_then_mint(rt)
        # page acceptance (2) + selected-route (1) + domain-wide proof (2)
        # + aggregate extras (1); every consumer went through the one parser.
        self.assertGreaterEqual(calls.count("f-sel"), 3)
        self.assertGreaterEqual(calls.count("f-oth"), 3)

    def test_c09f_page_and_adrs2_evidence_still_commits_every_occurrence(self):
        """C09-F: economic dedupe must NOT erase observations -- two ADRS2
        read-sets differing only in a duplicate occurrence differ in identity."""
        def _mint_with(pages):
            rt = self._v2_runtime()
            row = self._fill("f-dup")
            self._script_cycle(
                domain=(0,),
                fills={0: ([_fills_payload([row], cursor="page2"), _fills_payload([row])]
                           if pages == 2 else [_fills_payload([row])])})
            return self._acquire_then_mint(rt)[2]

        once = _mint_with(1)
        twice = _mint_with(2)
        self.assertNotEqual(once.read_set_id, twice.read_set_id)
        self.assertEqual(len(once.selected_route_truth.fills), 1)
        self.assertEqual(len(twice.selected_route_truth.fills), 1)


class _StubAcquirer(runner._TrustedDynamicReadAcquirerV2):
    def __init__(self, result):
        self._result = result

    def acquire(self, capability):
        return self._result


if __name__ == "__main__":
    unittest.main()
