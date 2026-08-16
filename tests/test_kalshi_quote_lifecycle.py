"""Offline tests for quote comparison, persisted market-maker intent, and the
corrected shared ``WriterEligibilityGate`` integration
(``KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_SPEC_03/04.md``).

MM-TEST-013A / MM-TEST-014 (dispatch category "E"): the T1/T2/T3 integration
tests in this file use the **real** ``arb.execution_ledger`` and the **real**
corrected ``WriterEligibilityGate`` against synthetic temporary SQLite
persistence reached through the real ``ledger_binding.py`` emergency/release
acquisition path (the same mechanism the predecessor test suite uses to reach
``WRITER_ELIGIBLE``) -- not a `_FakeLocked` substitute.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import arb.execution_ledger as ledger
from arb.execution_ledger import (
    AuthorityNamespaceBinding,
    EventType,
    canonical_json_bytes,
    initialize_authority_namespace,
    initialize_ledger_binding,
    start_writer_session,
)
from arb.venues.kalshi.emergency_cancel import EmergencyCancelGate, EmergencyRateConfigV1, EmergencyRateLane
from arb.venues.kalshi.ledger_binding import (
    LegacyIncidentContract,
    ReleaseEvaluationStateV1,
    ReleaseReconciliationSnapshotV1,
    ReleaseRiskSnapshotV1,
    acquire_emergency_control_only,
    acquire_release_only,
    canonical_kalshi_fill_payload,
)
from arb.venues.kalshi.minimal_market_maker import DesiredQuoteV1, QuoteSlot, SlotClassification, StrategyOwnedWorkingOrderV1
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    CandidateOrderV1,
    EconomicFillV1,
    FlowRiskLimits,
    FreshnessStampV1,
    MarketEconomicState,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
    WorkingOrderV1,
    WriterEligibilityGate,
)
from arb.venues.kalshi.quote_lifecycle import (
    CREATE_ORDER_ALLOWED_FIELDS,
    QuoteAction,
    QuoteLifecycleError,
    ReconstructedSlotOwnershipV1,
    VenueBindingV1,
    allocate_client_order_id,
    build_cancel_prepared_payload,
    build_cancel_writer_eligibility_assessment,
    build_create_prepared_payload,
    build_mm_cancel_intent_payload,
    build_mm_create_intent_payload,
    build_mm_create_order_body,
    build_writer_eligibility_assessment,
    candidate_for_desired_quote,
    compare_slot,
    issue_and_persist_write_permit,
    reconstruct_slot_ownership,
    select_write_action,
)

D = Decimal
TEST_CONFLICT_DOMAIN_REF = "KALSHI|KALSHI_DEMO|SYNTHETIC_MM_TEST|SUBACCOUNT=0"
# The synthetic release fixture crosses BOOT_HOLD -> SAFE_HELD (epoch 0 -> 1)
# then SAFE_HELD -> WRITER_ELIGIBLE, which the real ledger bumps again (-> 2).
WRITER_ELIGIBLE_RISK_STATE_EPOCH = 2


def risk_config() -> RiskLimitConfigV1:
    return RiskLimitConfigV1(
        1, TEST_CONFLICT_DOMAIN_REF, "USD",
        PerOrderRiskLimits(D("10"), D("10"), True, D("0.10"), 1_000),
        PerMarketRiskLimits(D("20"), D("20"), 10, D("20"), D("20")),
        AccountRiskLimits(D("100"), 50, D("100"), 0, D("0")),
        FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
        StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
        VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
    )


def working_order(*, slot: QuoteSlot = QuoteSlot.LOWER_YES_BID, yes_price: Decimal = D("0.44"), remaining: Decimal = D("1.00")) -> StrategyOwnedWorkingOrderV1:
    venue_side = "bid" if slot is QuoteSlot.LOWER_YES_BID else "ask"
    outcome_side = "YES" if slot is QuoteSlot.LOWER_YES_BID else "NO"
    return StrategyOwnedWorkingOrderV1(
        strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1", quote_slot=slot.value,
        quote_generation_id="qg_" + "1" * 32, client_order_id="11111111-1111-4111-8111-111111111111",
        venue_order_id="venue-order-1", venue_side=venue_side, outcome_side=outcome_side,
        yes_price=yes_price, initial_quantity=D("1.00"), remaining_quantity=remaining,
        authoritative_status="resting", source_intent_event_id="evt_1", source_order_identity_binding_event_id="evt_2",
        latest_order_observation_event_id="evt_3", ownership_basis_sha256="a" * 64,
    )


def desired(*, slot: QuoteSlot = QuoteSlot.LOWER_YES_BID, yes_price: Decimal = D("0.44")) -> DesiredQuoteV1:
    venue_side = "bid" if slot is QuoteSlot.LOWER_YES_BID else "ask"
    outcome_side = "YES" if slot is QuoteSlot.LOWER_YES_BID else "NO"
    return DesiredQuoteV1(slot.value, venue_side, outcome_side, yes_price, D("1.00"), "qg_" + "2" * 32)


# ---------------------------------------------------------------------------
# MM-CMP — per-slot comparison
# ---------------------------------------------------------------------------


def test_keep_when_exact_price_and_side_match() -> None:
    from arb.venues.kalshi.risk_control import PriceRangeV1
    grid = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(yes_price=D("0.44")), price_ranges=grid, keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.KEEP_EXISTING


def test_keep_when_one_grid_step_away() -> None:
    from arb.venues.kalshi.risk_control import PriceRangeV1
    grid = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    action = compare_slot(
        desired=desired(yes_price=D("0.45")), plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(yes_price=D("0.44")), price_ranges=grid, keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.KEEP_EXISTING


def test_cancel_then_reconcile_when_two_grid_steps_away() -> None:
    from arb.venues.kalshi.risk_control import PriceRangeV1
    grid = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    action = compare_slot(
        desired=desired(yes_price=D("0.46")), plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(yes_price=D("0.44")), price_ranges=grid, keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.CANCEL_THEN_RECONCILE_BEFORE_NEW


def test_cancel_existing_when_side_deliberately_suppressed() -> None:
    action = compare_slot(
        desired=None, plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(), price_ranges=(), keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.CANCEL_EXISTING


def test_partial_fill_with_positive_remaining_may_keep() -> None:
    from arb.venues.kalshi.risk_control import PriceRangeV1
    grid = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(yes_price=D("0.44"), remaining=D("0.40")), price_ranges=grid,
        keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.KEEP_EXISTING


def test_remaining_above_one_is_not_keep() -> None:
    from arb.venues.kalshi.risk_control import PriceRangeV1
    grid = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(yes_price=D("0.44"), remaining=D("1.01")), price_ranges=grid,
        keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is not QuoteAction.KEEP_EXISTING


def test_no_quote_when_absent_and_nothing_desired() -> None:
    action = compare_slot(
        desired=None, plan_valid=True, classification=SlotClassification.ABSENT.value, working_order=None,
        price_ranges=(), keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"),
        risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.NO_QUOTE


def test_create_new_when_absent_and_desired_and_writer_eligible() -> None:
    action = compare_slot(
        desired=desired(), plan_valid=True, classification=SlotClassification.ABSENT.value, working_order=None,
        price_ranges=(), keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"),
        risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.CREATE_NEW


def test_hold_when_not_writer_eligible() -> None:
    action = compare_slot(
        desired=desired(), plan_valid=True, classification=SlotClassification.ABSENT.value, working_order=None,
        price_ranges=(), keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"),
        risk_control_state="HALTED",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


def test_hold_on_invalid_plan_even_with_active_order() -> None:
    action = compare_slot(
        desired=desired(), plan_valid=False, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(), price_ranges=(), keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


def test_hold_on_ambiguous_or_conflict_classification() -> None:
    for classification in (SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, SlotClassification.CONFLICT.value):
        action = compare_slot(
            desired=desired(), plan_valid=True, classification=classification, working_order=None,
            price_ranges=(), keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"),
            risk_control_state="WRITER_ELIGIBLE",
        )
        assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


# ---------------------------------------------------------------------------
# MM-ARCH-002/003 — one-write serialization and deterministic precedence
# ---------------------------------------------------------------------------


def test_unresolved_anywhere_blocks_all_writes() -> None:
    actions = {QuoteSlot.LOWER_YES_BID.value: QuoteAction.HOLD_NO_STRATEGY_WRITE, QuoteSlot.UPPER_YES_ASK.value: QuoteAction.CREATE_NEW}
    assert select_write_action(actions, {}) is None


def test_cancel_precedes_create_across_slots() -> None:
    actions = {QuoteSlot.LOWER_YES_BID.value: QuoteAction.CREATE_NEW, QuoteSlot.UPPER_YES_ASK.value: QuoteAction.CANCEL_EXISTING}
    orders = {QuoteSlot.UPPER_YES_ASK.value: working_order(slot=QuoteSlot.UPPER_YES_ASK)}
    selected = select_write_action(actions, orders)
    assert selected is not None and selected.action == "CANCEL" and selected.quote_slot == QuoteSlot.UPPER_YES_ASK.value


def test_lower_precedes_upper_within_same_class() -> None:
    actions = {QuoteSlot.LOWER_YES_BID.value: QuoteAction.CREATE_NEW, QuoteSlot.UPPER_YES_ASK.value: QuoteAction.CREATE_NEW}
    selected = select_write_action(actions, {})
    assert selected is not None and selected.quote_slot == QuoteSlot.LOWER_YES_BID.value


def test_no_write_when_only_keep_or_no_quote() -> None:
    actions = {QuoteSlot.LOWER_YES_BID.value: QuoteAction.KEEP_EXISTING, QuoteSlot.UPPER_YES_ASK.value: QuoteAction.NO_QUOTE}
    assert select_write_action(actions, {}) is None


# ---------------------------------------------------------------------------
# MM-ID-002 — client-order-id allocation
# ---------------------------------------------------------------------------


def test_allocate_client_order_id_generates_when_absent() -> None:
    generated = allocate_client_order_id(persisted_client_order_id=None)
    assert isinstance(generated, str) and len(generated) == 36


def test_allocate_client_order_id_reuses_persisted() -> None:
    existing = "11111111-1111-4111-8111-111111111111"
    assert allocate_client_order_id(persisted_client_order_id=existing) == existing


def test_allocate_client_order_id_rejects_malformed_persisted_value() -> None:
    with pytest.raises(QuoteLifecycleError):
        allocate_client_order_id(persisted_client_order_id="not-a-uuid")


# ---------------------------------------------------------------------------
# MM-ID-003 — exact outer CREATE intent shape
# ---------------------------------------------------------------------------


def test_mm_create_intent_payload_has_no_top_level_request_id() -> None:
    payload = build_mm_create_intent_payload(
        execution_attempt_id="ea_" + "1" * 32, conflict_domain_ref="cd", incident_id="inc",
        client_order_id="11111111-1111-4111-8111-111111111111", capability_reference_id="cap_1",
        request_id="req_" + "2" * 32, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value, quote_generation_id="qg_" + "1" * 32,
        quote_plan_sha256="a" * 64, plan_input_sha256="b" * 64, source_book_snapshot_sha256="c" * 64,
        risk_config_sha256="d" * 64, risk_state_epoch=1, reconciliation_snapshot_sha256="e" * 64,
        venue_side="bid", outcome_side="YES", yes_price=D("0.44"), quantity=D("1.00"),
    )
    assert "request_id" not in payload
    assert payload["intent_payload"]["request_id"] == "req_" + "2" * 32
    assert payload["client_order_id"] == payload["intent_payload"]["client_order_id"]
    assert set(payload) == {
        "execution_attempt_id", "venue", "environment", "conflict_domain_ref", "incident_id", "operation_family",
        "client_order_id", "capability_reference_id", "intent_payload_schema_id", "intent_payload",
    }


def test_mm_create_order_body_exact_fields() -> None:
    binding = VenueBindingV1(adapter_payload_schema_id="schema-1")
    body = build_mm_create_order_body(
        ticker="TICK-1", client_order_id="11111111-1111-4111-8111-111111111111", venue_side="bid",
        yes_price=D("0.44"), quantity=D("1.00"), expiration_time=1_000_000, venue_binding=binding,
    )
    assert set(body) == CREATE_ORDER_ALLOWED_FIELDS
    assert body["post_only"] is True and body["reduce_only"] is False and body["cancel_order_on_pause"] is True
    assert body["price"] == "0.4400" and body["count"] == "1.00"


def test_create_prepared_payload_hash_self_consistent() -> None:
    binding = VenueBindingV1(adapter_payload_schema_id="schema-1")
    body = build_mm_create_order_body(
        ticker="TICK-1", client_order_id="11111111-1111-4111-8111-111111111111", venue_side="bid",
        yes_price=D("0.44"), quantity=D("1.00"), expiration_time=1_000_000, venue_binding=binding,
    )
    prepared = build_create_prepared_payload(
        request_id="req_" + "2" * 32, environment="KALSHI_DEMO",
        client_order_id="11111111-1111-4111-8111-111111111111", canonical_body=body, venue_binding=binding,
    )
    from arb.execution_ledger import sha256_hex
    identity = dict(prepared)
    supplied = identity.pop("prepared_request_sha256")
    assert sha256_hex(canonical_json_bytes(identity)) == supplied


# ---------------------------------------------------------------------------
# MM-TEST-013A / MM-TEST-014 (dispatch "E") -- real gate + real ledger
# ---------------------------------------------------------------------------


class _DeterministicInputs:
    def __init__(self) -> None:
        self.instant = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
        self.number = 900
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
        self.monotonic_value += 1
        return value


@pytest.fixture
def writer_eligible_ledger(tmp_path: Path):
    """Reach a genuinely evaluated, non-legacy WRITER_ELIGIBLE state on a real,
    temporary, synthetic execution ledger -- the same mechanism
    ``tests/test_kalshi_ledger_binding.py`` uses -- then reopen a real
    ``LockedLedger`` with a fresh normal-writer session, ready for
    ``WriterEligibilityGate.issue_permit``. Yields ``(locked, session_id, inputs)``.
    """

    authority_root = tmp_path / "authority"
    authority_root.mkdir()
    ledger_path = tmp_path / "execution.sqlite3"
    repository_root = Path(__file__).resolve().parents[1]
    inputs = _DeterministicInputs()
    binding = AuthorityNamespaceBinding.bind(
        authority_namespace_id="mm-quote-lifecycle-test-namespace",
        authority_namespace_root=authority_root,
        canonical_repository_root=repository_root,
    )
    contract = LegacyIncidentContract(conflict_domain_ref=TEST_CONFLICT_DOMAIN_REF)

    initialize_authority_namespace(binding, clock=inputs.clock, uuid_factory=inputs.uuid)
    initialize_ledger_binding(
        binding, conflict_domain_ref=contract.conflict_domain_ref, environment_classification=contract.environment,
        ledger_path=ledger_path, canonical_repository_root=repository_root, clock=inputs.clock, uuid_factory=inputs.uuid,
    )

    emergency = acquire_emergency_control_only(
        binding, canonical_repository_root=str(repository_root), contract=contract,
        expected_ledger_path=str(ledger_path), clock=inputs.clock, uuid_factory=inputs.uuid,
    )
    handle = emergency.handle
    assert handle is not None
    incident_id = "SYNTHETIC_MM_TEST_RELEASE_INCIDENT"
    proof_id = "SYNTHETIC_MM_TEST_RELEASE_PROOF"
    canonical_order = {
        "order_id": "synthetic-order-1", "status": "resting", "remaining_count_fp": "1.00",
        "market": "TICK-1", "outcome_side": "YES", "yes_price": D("0.50"), "cancel_order_on_pause": True,
    }
    order_event = handle.record_order_observation({
        "venue_order_id": "synthetic-order-1", "client_order_id": "synthetic-client-order-1",
        "source_request_id": "synthetic-release-order-read", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_order)).hexdigest(),
        "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
    }).events[-1]
    canonical_fill = canonical_kalshi_fill_payload(
        fill_id="synthetic-fill-1", order_id="synthetic-order-1", price=D("0.40"), quantity=D("1.00"), fee=D("0.01"),
        additional_fields={
            "market": "TICK-1", "outcome_side": "YES", "authoritative_created_time_utc": "2026-08-15T12:00:00.000000Z",
        },
    )
    fill_event = handle.record_fill_observation({
        "canonical_venue_payload": canonical_fill,
        "canonical_venue_payload_sha256": hashlib.sha256(canonical_json_bytes(canonical_fill)).hexdigest(),
        "client_order_id": "synthetic-client-order-1", "source_operation": "SYNTHETIC_FILL_READ",
        "source_request_id": "synthetic-release-fill-read", "venue_fill_id": "synthetic-fill-1",
        "venue_order_id": "synthetic-order-1", "venue_payload_schema_id": "synthetic-fill-v1",
    }).events[-1]
    handle.record_writer_proof_held({
        "writer_proof_id": proof_id, "conflict_domain_ref": contract.conflict_domain_ref,
        "held_reason": "SYNTHETIC_PREDECESSOR_HOLD", "protected_unresolved_write_event_ids": [],
    }, incident_id=incident_id)
    handle.record_reconciliation({
        "incident_id": incident_id, "disposition": "SYNTHETIC_AUTHORITATIVE_SAFE",
        "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED", "bound_order_id": None,
        "created_order_upper_bound": 0, "active_order_upper_bound": 0, "unknown_result": False,
        "writer_proof_release_eligible": True, "basis_event_ids": [],
        "adapter_reconciliation_schema_id": "SYNTHETIC_RECONCILIATION_V1",
    }, incident_id=incident_id)
    config = risk_config()
    before = handle.inspect_validated_projection()
    state_payload = {
        "previous_state": "BOOT_HOLD", "new_state": "SAFE_HELD", "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
        "risk_state_epoch_before": 0, "risk_state_epoch_after": 1, "risk_config_sha256": config.sha256,
        "related_emergency_action_id": None, "related_release_id": None, "predecessor_state_event_id": None,
        "observed_authority_trusted_sequence": before.last_sequence, "observed_authority_trusted_hash": before.terminal_event_hash,
        "observed_ledger_terminal_sequence": before.last_sequence, "observed_ledger_terminal_hash": before.terminal_event_hash,
    }
    handle.record_risk_control_state_changed(state_payload)
    normal_gate = WriterEligibilityGate(monotonic_clock_ns=inputs.monotonic_ns, wall_clock=inputs.clock, uuid_factory=inputs.uuid)
    lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
    emergency_gate = EmergencyCancelGate(
        handle=handle, rate_lane=lane, process_instance_id=normal_gate.process_instance_id,
        monotonic_clock_ns=inputs.monotonic_ns, wall_clock=inputs.clock, uuid_factory=inputs.uuid,
    )
    handle.close()

    market_data = {"ticker": "TICK-1", "reference_yes_price": D("0.50")}
    risk_snapshot = ReleaseRiskSnapshotV1(
        fills=(EconomicFillV1("TICK-1", "synthetic-fill-1", "YES", D("1.00"), D("0.40"), "2026-08-15T12:00:00.000000Z"),),
        working_orders=(WorkingOrderV1("TICK-1", "synthetic-order-1", "YES", D("1.00"), D("0.50")),),
        unresolved_write_count=0, unresolved_write_exposure_usd=D("0"), market_data_snapshot=market_data,
    )
    reconciliation = ReleaseReconciliationSnapshotV1(
        ("synthetic-order-1",), ("synthetic-order-1",), ("synthetic-fill-1",), (), (),
        (("synthetic-order-1", order_event.event_id),), (("synthetic-fill-1", fill_event.event_id),),
    )
    received_ns = inputs.monotonic_value
    received_at = ledger.canonical_timestamp(inputs.instant)

    release = acquire_release_only(
        binding, canonical_repository_root=str(repository_root), contract=contract,
        expected_ledger_path=str(ledger_path), clock=inputs.clock, uuid_factory=inputs.uuid,
        monotonic_clock_ns=inputs.monotonic_ns, release_wall_clock=inputs.clock,
    )
    release_handle = release.handle
    assert release_handle is not None
    market_stamp = FreshnessStampV1(normal_gate.process_instance_id, received_at, received_ns, "NONE", None, risk_snapshot.market_data_sha256)
    reconciliation_stamp = FreshnessStampV1(normal_gate.process_instance_id, received_at, received_ns, "NONE", None, reconciliation.sha256)
    state = ReleaseEvaluationStateV1(
        process_instance_id=normal_gate.process_instance_id, incident_id=incident_id, writer_proof_id=proof_id,
        risk_config=config, risk_snapshot=risk_snapshot, reconciliation_snapshot=reconciliation,
        market_freshness=market_stamp, reconciliation_freshness=reconciliation_stamp, venue_defense_evidence=None,
        normal_gate=normal_gate, emergency_gate=emergency_gate,
    )
    assessment = release_handle.evaluate_release(state)
    assert all(assessment.predicate_vector.values()), assessment.predicate_vector
    release_handle.record_risk_release(assessment)
    release_handle.release_writer_proof(assessment)
    release_handle.record_writer_eligible(assessment)
    release_handle.close()

    locked = ledger._open_locked(
        binding, conflict_domain_ref=contract.conflict_domain_ref, expected_environment=contract.environment,
        canonical_repository_root=repository_root, expected_ledger_path=ledger_path, clock=inputs.clock, uuid_factory=inputs.uuid,
    )
    assert locked.projection().risk_control_state == "WRITER_ELIGIBLE"
    session_id = start_writer_session(locked, prior_session_state="CLEAN")
    try:
        yield locked, session_id, inputs
    finally:
        locked.close()


def _assessment_and_payloads(*, request_id: str, execution_attempt_id: str):
    binding = VenueBindingV1(adapter_payload_schema_id="mm-create-v1")
    body = build_mm_create_order_body(
        ticker="TICK-1", client_order_id="11111111-1111-4111-8111-111111111111", venue_side="bid",
        yes_price=D("0.44"), quantity=D("1.00"), expiration_time=6_000_000_000, venue_binding=binding,
    )
    prepared = build_create_prepared_payload(
        request_id=request_id, environment="KALSHI_DEMO",
        client_order_id="11111111-1111-4111-8111-111111111111", canonical_body=body, venue_binding=binding,
    )
    candidate = CandidateOrderV1("TICK-1", "YES", D("1.00"), D("0.44"))
    state = MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0"))
    assessment = build_writer_eligibility_assessment(
        risk_assessment_id="ra_" + "1" * 32, request_id=request_id, candidate=candidate,
        market_economic_state=state, unresolved_exposure=D("0"), risk_config=risk_config(),
        prepared_request_sha256=prepared["prepared_request_sha256"], market_data_snapshot_sha256="a" * 64,
        market_data_freshness_identity_sha256="b" * 64, reconciliation_snapshot_sha256="c" * 64,
        reconciliation_freshness_identity_sha256="d" * 64, risk_state_epoch=WRITER_ELIGIBLE_RISK_STATE_EPOCH, freshness_deadline_monotonic_ns=999_999_999_999,
    )
    outer_intent = build_mm_create_intent_payload(
        execution_attempt_id=execution_attempt_id, conflict_domain_ref=TEST_CONFLICT_DOMAIN_REF,
        incident_id="SYNTHETIC_MM_TEST_CREATE_INCIDENT", client_order_id="11111111-1111-4111-8111-111111111111",
        capability_reference_id="cap_" + "1" * 8, request_id=request_id, strategy_instance_id="mm_" + "1" * 32,
        market_ticker="TICK-1", quote_slot=QuoteSlot.LOWER_YES_BID.value, quote_generation_id="qg_" + "1" * 32,
        quote_plan_sha256="a" * 64, plan_input_sha256="b" * 64, source_book_snapshot_sha256="c" * 64,
        risk_config_sha256=risk_config().sha256, risk_state_epoch=WRITER_ELIGIBLE_RISK_STATE_EPOCH, reconciliation_snapshot_sha256="c" * 64,
        venue_side="bid", outcome_side="YES", yes_price=D("0.44"), quantity=D("1.00"),
    )
    return assessment, outer_intent, prepared


def test_real_gate_real_ledger_accepts_corrected_t1_t2_t3_chain(writer_eligible_ledger) -> None:
    locked, session_id, _inputs = writer_eligible_ledger
    request_id = "req_" + "9" * 32
    execution_attempt_id = "ea_" + "8" * 32
    assessment, outer_intent, prepared = _assessment_and_payloads(request_id=request_id, execution_attempt_id=execution_attempt_id)
    gate = WriterEligibilityGate(monotonic_clock_ns=lambda: 1, wall_clock=lambda: datetime(2026, 8, 15, 13, tzinfo=timezone.utc))

    permit = issue_and_persist_write_permit(
        gate=gate, locked=locked, normal_writer_session_id=session_id, assessment=assessment,
        outer_intent_payload=outer_intent, prepared_payload=prepared,
    )

    t1, t2, t3 = locked.events[-3:]
    assert t1.event_type is EventType.EXECUTION_INTENT_RECORDED
    assert "request_id" not in t1.payload
    assert t1.payload["intent_payload"]["request_id"] == request_id
    assert t1.payload["execution_attempt_id"] == execution_attempt_id
    assert t1.execution_attempt_id == execution_attempt_id

    assert t2.event_type is EventType.REQUEST_PREPARED
    assert "execution_attempt_id" not in t2.payload
    assert t2.execution_attempt_id == execution_attempt_id
    assert t2.payload["request_id"] == request_id

    assert t3.event_type is EventType.WRITE_SEND_BOUNDARY_ENTERED
    assert "execution_attempt_id" not in t3.payload
    assert t3.execution_attempt_id is None
    assert t3.payload["request_id"] == request_id

    assert request_id != execution_attempt_id
    assert permit.request_id == request_id


def test_real_ledger_rejects_flat_top_level_request_id_fixture(writer_eligible_ledger) -> None:
    locked, session_id, _inputs = writer_eligible_ledger
    request_id = "req_" + "7" * 32
    assessment, _outer, prepared = _assessment_and_payloads(request_id=request_id, execution_attempt_id="ea_" + "6" * 32)
    gate = WriterEligibilityGate(monotonic_clock_ns=lambda: 1, wall_clock=lambda: datetime(2026, 8, 15, 13, tzinfo=timezone.utc))
    with pytest.raises(Exception):
        gate.issue_permit(
            locked=locked, normal_writer_session_id=session_id, assessment=assessment,
            intent_payload={"request_id": request_id}, prepared_payload=prepared,
        )


def test_real_gate_rejects_missing_execution_attempt_id(writer_eligible_ledger) -> None:
    locked, session_id, _inputs = writer_eligible_ledger
    request_id = "req_" + "5" * 32
    assessment, outer_intent, prepared = _assessment_and_payloads(request_id=request_id, execution_attempt_id="ea_" + "4" * 32)
    del outer_intent["execution_attempt_id"]
    gate = WriterEligibilityGate(monotonic_clock_ns=lambda: 1, wall_clock=lambda: datetime(2026, 8, 15, 13, tzinfo=timezone.utc))
    with pytest.raises(Exception):
        gate.issue_permit(
            locked=locked, normal_writer_session_id=session_id, assessment=assessment,
            intent_payload=outer_intent, prepared_payload=prepared,
        )


def test_real_gate_rejects_wrong_nested_request_id(writer_eligible_ledger) -> None:
    locked, session_id, _inputs = writer_eligible_ledger
    request_id = "req_" + "3" * 32
    assessment, outer_intent, prepared = _assessment_and_payloads(request_id=request_id, execution_attempt_id="ea_" + "2" * 32)
    outer_intent["intent_payload"]["request_id"] = "req_" + "0" * 32
    gate = WriterEligibilityGate(monotonic_clock_ns=lambda: 1, wall_clock=lambda: datetime(2026, 8, 15, 13, tzinfo=timezone.utc))
    with pytest.raises(Exception):
        gate.issue_permit(
            locked=locked, normal_writer_session_id=session_id, assessment=assessment,
            intent_payload=outer_intent, prepared_payload=prepared,
        )


def test_real_ledger_rejects_missing_t2_execution_attempt_parent(writer_eligible_ledger) -> None:
    """T2 (REQUEST_PREPARED) with null execution-attempt metadata must fail
    the real canonical ledger's parent-identity check directly (MM-TEST-013A #12)."""

    from arb.execution_ledger import EventInput

    locked, session_id, _inputs = writer_eligible_ledger
    request_id = "req_" + "1" * 30 + "aa"
    execution_attempt_id = "ea_" + "1" * 30 + "bb"
    assessment, outer_intent, prepared = _assessment_and_payloads(request_id=request_id, execution_attempt_id=execution_attempt_id)
    gate = WriterEligibilityGate(monotonic_clock_ns=lambda: 1, wall_clock=lambda: datetime(2026, 8, 15, 13, tzinfo=timezone.utc))
    permit = gate.issue_permit(
        locked=locked, normal_writer_session_id=session_id, assessment=assessment,
        intent_payload=outer_intent, prepared_payload=prepared,
    )
    gate.persist_intent(permit, locked)
    with pytest.raises(Exception):
        locked.append_batch((EventInput(EventType.REQUEST_PREPARED, prepared, session_id, None, None),))


def test_candidate_for_desired_quote_maps_slots_correctly() -> None:
    lower_candidate = candidate_for_desired_quote(market_ticker="TICK-1", desired=desired(slot=QuoteSlot.LOWER_YES_BID, yes_price=D("0.40")))
    assert lower_candidate.outcome_side == "YES"
    upper_candidate = candidate_for_desired_quote(market_ticker="TICK-1", desired=desired(slot=QuoteSlot.UPPER_YES_ASK, yes_price=D("0.60")))
    assert upper_candidate.outcome_side == "NO"


# ---------------------------------------------------------------------------
# Finding 01 — HALT / non-WRITER_ELIGIBLE never yields an ordinary strategy
# write, even for an otherwise-legitimate CANCEL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["HALTED", "BOOT_HOLD", "SAFE_HELD", "QUIESCENT_HELD", "RECONCILING", "EMERGENCY_CANCELING"])
def test_halted_active_order_desired_absent_holds_not_cancel(state: str) -> None:
    action = compare_slot(
        desired=None, plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(), price_ranges=(), keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state=state,
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


def test_halted_active_order_wrong_price_holds_not_cancel_then_reconcile() -> None:
    from arb.venues.kalshi.risk_control import PriceRangeV1
    grid = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    action = compare_slot(
        desired=desired(yes_price=D("0.46")), plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(yes_price=D("0.44")), price_ranges=grid, keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="HALTED",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


def test_halted_absent_desired_quote_holds() -> None:
    action = compare_slot(
        desired=desired(), plan_valid=True, classification=SlotClassification.ABSENT.value, working_order=None,
        price_ranges=(), keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"),
        risk_control_state="HALTED",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


def test_halted_exact_match_also_holds_not_keep() -> None:
    """Even a would-be KEEP is not selected while non-writer-eligible: the
    strategy makes no ordinary decision at all during HALT."""
    from arb.venues.kalshi.risk_control import PriceRangeV1
    grid = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=SlotClassification.ACTIVE_EXACT.value,
        working_order=working_order(yes_price=D("0.44")), price_ranges=grid, keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="HALTED",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


def test_no_write_selected_when_both_slots_hold_during_halt() -> None:
    actions = {
        QuoteSlot.LOWER_YES_BID.value: QuoteAction.HOLD_NO_STRATEGY_WRITE,
        QuoteSlot.UPPER_YES_ASK.value: QuoteAction.HOLD_NO_STRATEGY_WRITE,
    }
    assert select_write_action(actions, {}) is None


# ---------------------------------------------------------------------------
# Finding 05 — exact Create-V2 source-bound field values/types
# ---------------------------------------------------------------------------


def test_venue_binding_default_is_exact_source_bound_contract() -> None:
    binding = VenueBindingV1(adapter_payload_schema_id="schema-1")
    assert binding.subaccount == 0 and type(binding.subaccount) is int
    assert binding.exchange_index == 0 and type(binding.exchange_index) is int
    assert binding.self_trade_prevention_type == "taker_at_cross"
    assert binding.time_in_force == "good_till_canceled"


@pytest.mark.parametrize("bad_subaccount", ["0", False, 1, 0.0])
def test_venue_binding_rejects_non_exact_subaccount(bad_subaccount: object) -> None:
    with pytest.raises(QuoteLifecycleError):
        VenueBindingV1(subaccount=bad_subaccount, adapter_payload_schema_id="schema-1")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_exchange_index", ["0", False, 1, 0.0])
def test_venue_binding_rejects_non_exact_exchange_index(bad_exchange_index: object) -> None:
    with pytest.raises(QuoteLifecycleError):
        VenueBindingV1(exchange_index=bad_exchange_index, adapter_payload_schema_id="schema-1")  # type: ignore[arg-type]


def test_venue_binding_rejects_wrong_self_trade_prevention_type() -> None:
    with pytest.raises(QuoteLifecycleError):
        VenueBindingV1(self_trade_prevention_type="REJECT_TAKER", adapter_payload_schema_id="schema-1")


def test_venue_binding_rejects_wrong_time_in_force() -> None:
    with pytest.raises(QuoteLifecycleError):
        VenueBindingV1(time_in_force="immediate_or_cancel", adapter_payload_schema_id="schema-1")


def test_create_order_body_exact_source_bound_values() -> None:
    binding = VenueBindingV1(adapter_payload_schema_id="schema-1")
    body = build_mm_create_order_body(
        ticker="TICK-1", client_order_id="11111111-1111-4111-8111-111111111111", venue_side="ask",
        yes_price=D("0.60"), quantity=D("1.00"), expiration_time=1_000_000, venue_binding=binding,
    )
    assert body["subaccount"] == 0 and type(body["subaccount"]) is int
    assert body["exchange_index"] == 0 and type(body["exchange_index"]) is int
    assert body["self_trade_prevention_type"] == "taker_at_cross"
    assert body["time_in_force"] == "good_till_canceled"
    assert body["post_only"] is True
    assert body["cancel_order_on_pause"] is True
    assert body["reduce_only"] is False
    assert "order_group_id" not in body
    assert body["count"] == "1.00"
    assert body["side"] == "ask"


def test_create_order_body_rejects_float_price_and_quantity() -> None:
    binding = VenueBindingV1(adapter_payload_schema_id="schema-1")
    with pytest.raises(QuoteLifecycleError):
        build_mm_create_order_body(
            ticker="TICK-1", client_order_id="11111111-1111-4111-8111-111111111111", venue_side="bid",
            yes_price=0.44, quantity=D("1.00"), expiration_time=1, venue_binding=binding,  # type: ignore[arg-type]
        )
    with pytest.raises(QuoteLifecycleError):
        build_mm_create_order_body(
            ticker="TICK-1", client_order_id="11111111-1111-4111-8111-111111111111", venue_side="bid",
            yes_price=D("0.44"), quantity=1.00, expiration_time=1, venue_binding=binding,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Finding 04 — canonical ordinary CANCEL_ORDER_V2 binding
# ---------------------------------------------------------------------------


def test_cancel_prepared_payload_exact_operation_and_route() -> None:
    prepared = build_cancel_prepared_payload(
        request_id="req_" + "1" * 32, environment="KALSHI_DEMO", venue_order_id="venue-order-1",
        client_order_id="11111111-1111-4111-8111-111111111111", adapter_payload_schema_id="cancel-schema-1",
    )
    assert prepared["operation_name"] == "CANCEL_ORDER_V2"
    assert prepared["method"] == "DELETE"
    assert prepared["path_without_query"] == "/trade-api/v2/portfolio/events/orders/venue-order-1"
    assert prepared["venue_order_id"] == "venue-order-1"
    assert prepared["canonical_body"] is None and prepared["canonical_body_sha256"] is None


def test_cancel_prepared_payload_query_matches_canonical_cancel_query() -> None:
    from arb.venues.kalshi.order_lifecycle import build_cancel_query
    prepared = build_cancel_prepared_payload(
        request_id="req_" + "1" * 32, environment="KALSHI_DEMO", venue_order_id="venue-order-1",
        client_order_id="11111111-1111-4111-8111-111111111111", adapter_payload_schema_id="cancel-schema-1",
    )
    assert prepared["canonical_query"] == build_cancel_query()


def test_cancel_prepared_payload_hash_self_consistent() -> None:
    from arb.execution_ledger import sha256_hex
    prepared = build_cancel_prepared_payload(
        request_id="req_" + "1" * 32, environment="KALSHI_DEMO", venue_order_id="venue-order-1",
        client_order_id="11111111-1111-4111-8111-111111111111", adapter_payload_schema_id="cancel-schema-1",
    )
    identity = dict(prepared)
    supplied = identity.pop("prepared_request_sha256")
    assert sha256_hex(canonical_json_bytes(identity)) == supplied


def test_cancel_target_is_exact_venue_order_id_never_client_order_id() -> None:
    prepared = build_cancel_prepared_payload(
        request_id="req_" + "1" * 32, environment="KALSHI_DEMO", venue_order_id="venue-order-1",
        client_order_id="client-order-xyz", adapter_payload_schema_id="cancel-schema-1",
    )
    assert prepared["venue_order_id"] == "venue-order-1"
    assert "client-order-xyz" not in prepared["path_without_query"]


def test_cancel_writer_eligibility_assessment_uses_cancel_operation_kind() -> None:
    assessment = build_cancel_writer_eligibility_assessment(
        risk_assessment_id="ra_" + "1" * 32, request_id="req_" + "1" * 32, prepared_request_sha256="a" * 64,
        risk_config=risk_config(), market_data_snapshot_sha256="b" * 64, market_data_freshness_identity_sha256="c" * 64,
        reconciliation_snapshot_sha256="d" * 64, reconciliation_freshness_identity_sha256="e" * 64,
        risk_state_epoch=1, freshness_deadline_monotonic_ns=999_999_999_999,
    )
    assert assessment.operation_kind == "CANCEL_ORDER_V2"
    assert assessment.eligible is True


def test_no_cancel_all_surface_exists() -> None:
    import arb.venues.kalshi.quote_lifecycle as ql
    assert not any("cancel_all" in name.lower() for name in dir(ql))


# ---------------------------------------------------------------------------
# Finding 03 — restart exact ownership reconstruction (real ledger)
# ---------------------------------------------------------------------------


def test_reconstruct_ownership_absent_when_no_intent_persisted(writer_eligible_ledger) -> None:
    locked, _session_id, _inputs = writer_eligible_ledger
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.ABSENT.value
    assert result.working_order is None


def _persist_mm_create(locked, session_id, inputs, *, request_id: str, execution_attempt_id: str, client_order_id: str, quote_generation_id: str = "qg_" + "3" * 32):
    binding = VenueBindingV1(adapter_payload_schema_id="mm-create-v1")
    body = build_mm_create_order_body(
        ticker="TICK-1", client_order_id=client_order_id, venue_side="bid", yes_price=D("0.44"),
        quantity=D("1.00"), expiration_time=6_000_000_000, venue_binding=binding,
    )
    prepared = build_create_prepared_payload(
        request_id=request_id, environment="KALSHI_DEMO", client_order_id=client_order_id,
        canonical_body=body, venue_binding=binding,
    )
    candidate = CandidateOrderV1("TICK-1", "YES", D("1.00"), D("0.44"))
    state = MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0"))
    assessment = build_writer_eligibility_assessment(
        risk_assessment_id="ra_" + "1" * 32, request_id=request_id, candidate=candidate,
        market_economic_state=state, unresolved_exposure=D("0"), risk_config=risk_config(),
        prepared_request_sha256=prepared["prepared_request_sha256"], market_data_snapshot_sha256="a" * 64,
        market_data_freshness_identity_sha256="b" * 64, reconciliation_snapshot_sha256="c" * 64,
        reconciliation_freshness_identity_sha256="d" * 64, risk_state_epoch=WRITER_ELIGIBLE_RISK_STATE_EPOCH,
        freshness_deadline_monotonic_ns=999_999_999_999,
    )
    outer_intent = build_mm_create_intent_payload(
        execution_attempt_id=execution_attempt_id, conflict_domain_ref=TEST_CONFLICT_DOMAIN_REF,
        incident_id="SYNTHETIC_MM_TEST_RESTART_INCIDENT", client_order_id=client_order_id,
        capability_reference_id="cap_restart", request_id=request_id, strategy_instance_id="mm_" + "1" * 32,
        market_ticker="TICK-1", quote_slot=QuoteSlot.LOWER_YES_BID.value, quote_generation_id=quote_generation_id,
        quote_plan_sha256="a" * 64, plan_input_sha256="b" * 64, source_book_snapshot_sha256="c" * 64,
        risk_config_sha256=risk_config().sha256, risk_state_epoch=WRITER_ELIGIBLE_RISK_STATE_EPOCH,
        reconciliation_snapshot_sha256="c" * 64, venue_side="bid", outcome_side="YES", yes_price=D("0.44"), quantity=D("1.00"),
    )
    gate = WriterEligibilityGate(monotonic_clock_ns=lambda: 1, wall_clock=lambda: datetime(2026, 8, 15, 13, tzinfo=timezone.utc))
    issue_and_persist_write_permit(
        gate=gate, locked=locked, normal_writer_session_id=session_id, assessment=assessment,
        outer_intent_payload=outer_intent, prepared_payload=prepared,
    )


def test_reconstruct_ownership_unresolved_when_intent_persisted_but_no_binding(writer_eligible_ledger) -> None:
    locked, session_id, inputs = writer_eligible_ledger
    _persist_mm_create(
        locked, session_id, inputs, request_id="req_" + "a" * 32, execution_attempt_id="ea_" + "a" * 32,
        client_order_id="22222222-2222-4222-8222-222222222222",
    )
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value
    assert result.persisted_client_order_id == "22222222-2222-4222-8222-222222222222"


def test_reconstruct_ownership_active_exact_after_order_bound_and_observed_resting(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "33333333-3333-4333-8333-333333333333"
    _persist_mm_create(
        locked, session_id, inputs, request_id="req_" + "b" * 32, execution_attempt_id="ea_" + "b" * 32,
        client_order_id=client_order_id,
    )
    locked.append_batch((EventInput(ET.ORDER_IDENTITY_BOUND, {
        "client_order_id": client_order_id, "venue_order_id": "venue-order-restart-1", "venue": "KALSHI",
        "environment": "KALSHI_DEMO", "incident_id": "SYNTHETIC_MM_TEST_RESTART_INCIDENT",
        "binding_basis_event_ids": [],
    }, session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None),))
    canonical_order = {"order_id": "venue-order-restart-1", "status": "resting", "remaining_count_fp": "1.00"}
    locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
        "venue_order_id": "venue-order-restart-1", "client_order_id": client_order_id,
        "source_request_id": "synthetic-restart-read", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_order),
        "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
    }, session_id, None, None),))

    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.ACTIVE_EXACT.value
    assert result.working_order is not None
    assert result.working_order.venue_order_id == "venue-order-restart-1"
    assert result.working_order.remaining_quantity == D("1.00")
    assert result.persisted_client_order_id == client_order_id


def test_reconstruct_ownership_never_uses_price_similarity() -> None:
    """A price/side-matching foreign working order with no persisted MM
    intent is simply ABSENT ownership -- never adopted."""
    result = reconstruct_slot_ownership(
        (), strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.ABSENT.value
    assert result.working_order is None


def test_reconstruct_ownership_conflicting_client_ids_for_one_generation_fails_closed(writer_eligible_ledger) -> None:
    locked, session_id, inputs = writer_eligible_ledger
    _persist_mm_create(
        locked, session_id, inputs, request_id="req_" + "c" * 32, execution_attempt_id="ea_" + "c" * 32,
        client_order_id="44444444-4444-4444-8444-444444444444", quote_generation_id="qg_" + "9" * 32,
    )
    _persist_mm_create(
        locked, session_id, inputs, request_id="req_" + "d" * 32, execution_attempt_id="ea_" + "d" * 32,
        client_order_id="55555555-5555-4555-8555-555555555555", quote_generation_id="qg_" + "9" * 32,
    )
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.CONFLICT.value


def sha256_hex_of(value: dict) -> str:
    import hashlib
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


# ---------------------------------------------------------------------------
# Correction 02 — cancellation / restart evidence (real ledger + real gate)
# ---------------------------------------------------------------------------


def _persist_mm_cancel(
    locked, session_id, inputs, *, request_id: str, execution_attempt_id: str, client_order_id: str,
    target_venue_order_id: str, quote_generation_id: str,
):
    prepared = build_cancel_prepared_payload(
        request_id=request_id, environment="KALSHI_DEMO", venue_order_id=target_venue_order_id,
        client_order_id=client_order_id, adapter_payload_schema_id="mm-cancel-v1",
    )
    assessment = build_cancel_writer_eligibility_assessment(
        risk_assessment_id="ra_cancel_" + request_id[-8:], request_id=request_id,
        prepared_request_sha256=prepared["prepared_request_sha256"], risk_config=risk_config(),
        market_data_snapshot_sha256="a" * 64, market_data_freshness_identity_sha256="b" * 64,
        reconciliation_snapshot_sha256="c" * 64, reconciliation_freshness_identity_sha256="d" * 64,
        risk_state_epoch=WRITER_ELIGIBLE_RISK_STATE_EPOCH, freshness_deadline_monotonic_ns=999_999_999_999,
    )
    outer_intent = build_mm_cancel_intent_payload(
        execution_attempt_id=execution_attempt_id, conflict_domain_ref=TEST_CONFLICT_DOMAIN_REF,
        incident_id="SYNTHETIC_MM_TEST_CANCEL_INCIDENT", client_order_id=client_order_id,
        capability_reference_id="cap_cancel", request_id=request_id, strategy_instance_id="mm_" + "1" * 32,
        market_ticker="TICK-1", quote_slot=QuoteSlot.LOWER_YES_BID.value, quote_generation_id=quote_generation_id,
        target_venue_order_id=target_venue_order_id, reconciliation_snapshot_sha256="c" * 64,
    )
    gate = WriterEligibilityGate(monotonic_clock_ns=lambda: 1, wall_clock=lambda: datetime(2026, 8, 15, 13, tzinfo=timezone.utc))
    return issue_and_persist_write_permit(
        gate=gate, locked=locked, normal_writer_session_id=session_id, assessment=assessment,
        outer_intent_payload=outer_intent, prepared_payload=prepared,
    )


def _establish_active_exact_order(locked, session_id, inputs, *, client_order_id: str, venue_order_id: str, request_id: str, execution_attempt_id: str, remaining: str = "1.00"):
    from arb.execution_ledger import EventInput, EventType as ET
    _persist_mm_create(
        locked, session_id, inputs, request_id=request_id, execution_attempt_id=execution_attempt_id,
        client_order_id=client_order_id,
    )
    locked.append_batch((EventInput(ET.ORDER_IDENTITY_BOUND, {
        "client_order_id": client_order_id, "venue_order_id": venue_order_id, "venue": "KALSHI",
        "environment": "KALSHI_DEMO", "incident_id": "SYNTHETIC_MM_TEST_RESTART_INCIDENT",
        "binding_basis_event_ids": [],
    }, session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None),))
    canonical_order = {"order_id": venue_order_id, "status": "resting", "remaining_count_fp": remaining}
    locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": "synthetic-restart-read", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_order),
        "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
    }, session_id, None, None),))


def test_restart_unresolved_cancel_blocks_replacement(writer_eligible_ledger) -> None:
    """A cancel has been persistently attempted (T1/T2/T3 all committed) for
    the exact strategy-owned order, but no authoritative terminal order
    observation or reconciliation proves the cancel actually closed the
    order. Restart reconstruction must not report this slot as a clean
    ACTIVE_EXACT order available for ordinary KEEP/CANCEL comparison, and it
    must not be reported as free for a fresh CREATE either."""
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "66666666-6666-4666-8666-666666666666"
    venue_order_id = "venue-order-cancel-1"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "e" * 32, execution_attempt_id="ea_" + "e" * 32,
    )
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "f" * 32, execution_attempt_id="ea_" + "f" * 32,
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "1" * 32,
    )
    # No ORDER_OBSERVED reflecting cancellation and no RECONCILIATION_RECORDED
    # exist yet: the cancel result is unresolved/ambiguous at restart.

    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification != SlotClassification.ACTIVE_EXACT.value, (
        "an order with an unresolved persisted cancel attempt must not be reported as a clean "
        "ACTIVE_EXACT order eligible for ordinary comparison"
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value

    # And composed through compare_slot, this must never select CREATE_NEW or
    # a fresh ordinary cancel -- only HOLD.
    action = compare_slot(
        desired=None, plan_valid=True, classification=result.classification, working_order=result.working_order,
        price_ranges=(), keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"),
        risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


def test_cancel_ack_alone_is_not_terminal_proof(writer_eligible_ledger) -> None:
    """A cancel has been persistently attempted and a transport-level HTTP
    acknowledgement has even been recorded, but no authoritative terminal
    ORDER_OBSERVED/RECONCILIATION_RECORDED proves the order actually closed.
    The old order must not be treated as absent/terminal merely because an
    ACK exists; CREATE_NEW must not become selectable."""
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "77777777-7777-4777-8777-777777777777"
    venue_order_id = "venue-order-cancel-2"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "1" * 30 + "01", execution_attempt_id="ea_" + "1" * 30 + "01",
    )
    permit = _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "1" * 30 + "02", execution_attempt_id="ea_" + "1" * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "2" * 32,
    )
    # A transport-level acknowledgement is recorded (HTTP 200), but this is
    # explicitly not authoritative terminal order truth.
    response_body = {"order": {"order_id": venue_order_id}}
    locked.append_batch((EventInput(ET.HTTP_RESPONSE_CLASSIFIED, {
        "request_id": permit.request_id, "http_status": 200, "response_media_type": "application/json",
        "response_byte_length": 32, "response_sha256": sha256_hex_of(response_body),
        "adapter_result_class": "CANCEL_ACKNOWLEDGED", "write_closure_class": "UNRESOLVED",
        "validated_identity_fields": [],
    }, session_id, None, None),))

    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification != SlotClassification.ABSENT.value, (
        "an HTTP acknowledgement of a cancel send is not authoritative terminal proof; the slot "
        "must not appear ABSENT/free for a fresh CREATE"
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value

    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=result.classification,
        working_order=result.working_order, price_ranges=(), keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is not QuoteAction.CREATE_NEW


def test_ambiguous_cancellation_blocks_replacement_and_no_blind_resend(writer_eligible_ledger) -> None:
    """Cancel transport result is explicitly unknown after send (the
    accepted TRANSPORT_UNKNOWN_AFTER_SEND classification). The old order
    must remain conservatively counted as potentially active, and the MM
    lifecycle surface must expose no resend/retry action for it."""
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "88888888-8888-4888-8888-888888888888"
    venue_order_id = "venue-order-cancel-3"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "2" * 30 + "01", execution_attempt_id="ea_" + "2" * 30 + "01",
    )
    permit = _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "2" * 30 + "02", execution_attempt_id="ea_" + "2" * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "3" * 32,
    )
    locked.append_batch((EventInput(ET.TRANSPORT_UNKNOWN_AFTER_SEND, {
        "request_id": permit.request_id, "unknown_class": "TRANSPORT_RESULT_UNKNOWN_AFTER_SEND",
        "write_closure_class": "UNRESOLVED",
    }, session_id, None, None),))

    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value
    assert result.working_order is None, "an ambiguous-cancel order must not be exposed as a clean working order"

    action = compare_slot(
        desired=None, plan_valid=True, classification=result.classification, working_order=result.working_order,
        price_ranges=(), keep_reprice_distance_grid_steps=2, best_yes_bid=D("0.40"), best_yes_ask=D("0.50"),
        risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE

    # No resend/retry surface exists anywhere in the module's public API.
    import arb.venues.kalshi.quote_lifecycle as ql
    assert not any(("resend" in name.lower() or "retry" in name.lower()) for name in dir(ql))


def test_fill_during_cancellation_updates_authoritative_truth_before_replacement(writer_eligible_ledger) -> None:
    """A fill is authoritatively observed for the exact target order while a
    cancel attempt against it remains unresolved. The fill must participate
    in authoritative state (via a fresh ORDER_OBSERVED reflecting reduced
    remaining quantity); replacement must still remain blocked until the
    order is authoritatively terminal/reconciled."""
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "99999999-9999-4999-8999-999999999999"
    venue_order_id = "venue-order-cancel-4"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "3" * 30 + "01", execution_attempt_id="ea_" + "3" * 30 + "01",
    )
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "3" * 30 + "02", execution_attempt_id="ea_" + "3" * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "4" * 32,
    )
    # A partial fill arrives while the cancel is in flight -- authoritative,
    # deduplicated fill evidence with its own exact fill_id.
    canonical_fill = {"fill_id": "fill-cancel-race-1", "order_id": venue_order_id, "market": "TICK-1", "outcome_side": "YES", "quantity": "0.40", "yes_price": "0.44"}
    locked.append_batch((EventInput(ET.FILL_OBSERVED, {
        "venue_fill_id": "fill-cancel-race-1", "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": "synthetic-fill-during-cancel", "source_operation": "SYNTHETIC_FILL_READ",
        "venue_payload_schema_id": "synthetic-fill-v1", "canonical_venue_payload": canonical_fill,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_fill),
    }, session_id, None, None),))
    # Authoritative order truth reflects the reduced remaining quantity but
    # is still resting (not yet terminal) -- the submitted limit price
    # (0.44) is never substituted for the authoritative fill price.
    canonical_order = {"order_id": venue_order_id, "status": "resting", "remaining_count_fp": "0.60"}
    locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": "synthetic-restart-read-2", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_order),
        "observation_semantic_class": "AUTHORITATIVE_ACTIVE_ORDER",
    }, session_id, None, None),))

    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    # The order still has an unresolved cancel attempt outstanding, so per
    # MM-CMP-002 predicate 9 ("no unresolved write exists for the slot ...")
    # it must not be exposed as a clean ACTIVE_EXACT order eligible even for
    # an ordinary KEEP -- not just blocked from CREATE_NEW.
    assert result.classification != SlotClassification.ACTIVE_EXACT.value, (
        "a fill arriving during an unresolved cancel does not clear the unresolved-cancel "
        "condition; the slot must still not be reported as a clean eligible ACTIVE_EXACT order"
    )
    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=result.classification,
        working_order=result.working_order, price_ranges=(), keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE


# ---------------------------------------------------------------------------
# Test 5 -- terminal closure still requires a fresh plan/permit chain
# (architectural: every plan/permit identity in this codebase is
# content-addressed and freshly computed from current input; there is no
# cache/reuse surface for a prior plan or permit to be replayed from)
# ---------------------------------------------------------------------------


def test_terminal_reconciled_old_order_frees_slot_but_grants_no_authority(writer_eligible_ledger) -> None:
    """After authoritative terminal reconciliation, the slot becomes
    TERMINAL_RECONCILED (free for a fresh plan) -- but nothing about the old
    order's identity is itself writer authority: no QuotePlanV1 or
    NormalWriterPermit is reconstructed by this function, and any
    replacement CREATE must go through fresh plan/risk/permit construction
    exactly like any other CREATE_NEW."""
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    venue_order_id = "venue-order-cancel-5"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "4" * 30 + "01", execution_attempt_id="ea_" + "4" * 30 + "01",
    )
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "4" * 30 + "02", execution_attempt_id="ea_" + "4" * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "5" * 32,
    )
    # Authoritative terminal order truth: canceled.
    canonical_order = {"order_id": venue_order_id, "status": "canceled", "remaining_count_fp": "0.00"}
    locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": "synthetic-restart-read-3", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_order),
        "observation_semantic_class": "AUTHORITATIVE_TERMINAL_ORDER",
    }, session_id, None, None),))
    # Authoritative reconciliation closes the incident for this exact order.
    locked.append_batch((EventInput(ET.RECONCILIATION_RECORDED, {
        "incident_id": "SYNTHETIC_MM_TEST_RESTART_INCIDENT", "disposition": "SYNTHETIC_AUTHORITATIVE_SAFE",
        "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED", "bound_order_id": venue_order_id,
        "created_order_upper_bound": 1, "active_order_upper_bound": 0, "unknown_result": False,
        "writer_proof_release_eligible": True, "basis_event_ids": [], "adapter_reconciliation_schema_id": "SYNTHETIC_RECONCILIATION_V1",
    }, session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None),))

    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.TERMINAL_RECONCILED.value
    assert result.working_order is None

    # The reconstruction result itself carries no plan/permit authority --
    # it is a plain ownership/classification record only.
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(ReconstructedSlotOwnershipV1)}
    assert "quote_plan" not in field_names.__class__.__name__.lower() or True  # structural sanity, see assertion below
    assert not {"plan", "permit"} & {name.split("_")[0] for name in field_names if "quote_plan" in name or "permit" in name}
    assert field_names == {"quote_slot", "classification", "working_order", "persisted_client_order_id"}

    # A fresh replacement decision, given the now-free slot, is only
    # CREATE_NEW when writer-eligible -- and still requires the caller to
    # separately obtain a brand new permit through issue_and_persist_write_permit
    # (compare_slot/reconstruct_slot_ownership never construct one).
    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=result.classification,
        working_order=result.working_order, price_ranges=(), keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.CREATE_NEW


# ---------------------------------------------------------------------------
# Correction 03 -- exact cancel-hold closure-rule edge cases
# ---------------------------------------------------------------------------


def _setup_cancelled_order_with_cancel_intent(locked, session_id, inputs, *, suffix: str):
    """Establish an ACTIVE_EXACT order, persist a matching MM cancel intent
    against it, then record a terminal ORDER_OBSERVED(canceled) -- but no
    RECONCILIATION_RECORDED yet. Returns venue_order_id."""
    from arb.execution_ledger import EventInput, EventType as ET
    client_order_id = f"b{suffix}0000-0000-4000-8000-000000000000"
    venue_order_id = f"venue-order-closure-{suffix}"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + suffix * 30 + "01", execution_attempt_id="ea_" + suffix * 30 + "01",
    )
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + suffix * 30 + "02", execution_attempt_id="ea_" + suffix * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + suffix * 32,
    )
    canonical_order = {"order_id": venue_order_id, "status": "canceled", "remaining_count_fp": "1.00"}
    locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": "synthetic-closure-read", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_order),
        "observation_semantic_class": "AUTHORITATIVE_TERMINAL_ORDER",
    }, session_id, None, None),))
    return venue_order_id


def _reconciliation_payload(*, bound_order_id, write_closure_class="AUTHORITATIVE_RESULT_CLOSED", unknown_result=False, active_order_upper_bound=0):
    return {
        "incident_id": "SYNTHETIC_MM_TEST_RESTART_INCIDENT", "disposition": "SYNTHETIC_AUTHORITATIVE_SAFE",
        "write_closure_class": write_closure_class, "bound_order_id": bound_order_id,
        "created_order_upper_bound": 1, "active_order_upper_bound": active_order_upper_bound,
        "unknown_result": unknown_result, "writer_proof_release_eligible": True, "basis_event_ids": [],
        "adapter_reconciliation_schema_id": "SYNTHETIC_RECONCILIATION_V1",
    }


def test_terminal_observation_without_reconciliation_still_unresolved(writer_eligible_ledger) -> None:
    locked, session_id, inputs = writer_eligible_ledger
    _setup_cancelled_order_with_cancel_intent(locked, session_id, inputs, suffix="1")
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_reconciliation_with_unknown_result_true_does_not_clear(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id = _setup_cancelled_order_with_cancel_intent(locked, session_id, inputs, suffix="2")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id, unknown_result=True),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_reconciliation_with_write_closure_class_unresolved_does_not_clear(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id = _setup_cancelled_order_with_cancel_intent(locked, session_id, inputs, suffix="3")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id, write_closure_class="UNRESOLVED"),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_reconciliation_with_active_order_upper_bound_above_zero_does_not_clear(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id = _setup_cancelled_order_with_cancel_intent(locked, session_id, inputs, suffix="4")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id, active_order_upper_bound=1),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_reconciliation_for_a_different_bound_order_id_does_not_clear(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    _setup_cancelled_order_with_cancel_intent(locked, session_id, inputs, suffix="5")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id="some-other-venue-order"),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_reconciliation_older_than_cancel_intent_does_not_clear(writer_eligible_ledger) -> None:
    """A RECONCILIATION_RECORDED persisted BEFORE the cancel intent (e.g. left
    over from an earlier, unrelated closure) must not be treated as proof
    that this later cancel attempt closed."""
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "c6000000-0000-4000-8000-000000000000"
    venue_order_id = "venue-order-closure-6"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "6" * 30 + "01", execution_attempt_id="ea_" + "6" * 30 + "01",
    )
    # An authoritative closing reconciliation for this exact order is
    # persisted first (e.g. stale from an earlier attempt) ...
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    # ... and only afterward is a fresh cancel intent persisted.
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "6" * 30 + "02", execution_attempt_id="ea_" + "6" * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "6" * 32,
    )
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_authoritative_terminal_reconciliation_after_cancel_intent_clears(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id = _setup_cancelled_order_with_cancel_intent(locked, session_id, inputs, suffix="7")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.TERMINAL_RECONCILED.value
    assert result.working_order is None


def test_multiple_cancel_attempts_latest_unresolved_remains_held(writer_eligible_ledger) -> None:
    """An earlier cancel attempt against this exact order was authoritatively
    closed, but a second, later cancel intent against the (by-then already
    closed) order remains unresolved -- the slot must remain held on the
    latest attempt, never silently preferring the earlier resolved one."""
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "c8000000-0000-4000-8000-000000000000"
    venue_order_id = "venue-order-closure-8"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "8" * 30 + "01", execution_attempt_id="ea_" + "8" * 30 + "01",
    )
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "8" * 30 + "02", execution_attempt_id="ea_" + "8" * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "8" * 32,
    )
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    # A second cancel intent is persisted afterward (synthetic: e.g. a
    # duplicate/late-arriving attempt), with no reconciliation following it.
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "8" * 30 + "03", execution_attempt_id="ea_" + "8" * 30 + "03",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "9" * 32,
    )
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_no_second_cancel_action_selected_while_first_cancel_unresolved(writer_eligible_ledger) -> None:
    """Composed through compare_slot and select_write_action, an unresolved
    cancel must never yield a second ordinary CANCEL_EXISTING /
    CANCEL_THEN_RECONCILE_BEFORE_NEW decision -- only HOLD."""
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "c9000000-0000-4000-8000-000000000000"
    venue_order_id = "venue-order-closure-9"
    _establish_active_exact_order(
        locked, session_id, inputs, client_order_id=client_order_id, venue_order_id=venue_order_id,
        request_id="req_" + "9" * 30 + "01", execution_attempt_id="ea_" + "9" * 30 + "01",
    )
    _persist_mm_cancel(
        locked, session_id, inputs, request_id="req_" + "9" * 30 + "02", execution_attempt_id="ea_" + "9" * 30 + "02",
        client_order_id=client_order_id, target_venue_order_id=venue_order_id, quote_generation_id="qg_" + "1" * 5 + "9" * 27,
    )
    result = reconstruct_slot_ownership(
        locked.events, strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1",
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    for desired_quote in (None, desired(yes_price=D("0.44")), desired(yes_price=D("0.60"))):
        action = compare_slot(
            desired=desired_quote, plan_valid=True, classification=result.classification,
            working_order=result.working_order, price_ranges=(), keep_reprice_distance_grid_steps=2,
            best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
        )
        assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE
        assert action not in (QuoteAction.CANCEL_EXISTING, QuoteAction.CANCEL_THEN_RECONCILE_BEFORE_NEW, QuoteAction.CREATE_NEW, QuoteAction.KEEP_EXISTING)
    actions = {QuoteSlot.LOWER_YES_BID.value: QuoteAction.HOLD_NO_STRATEGY_WRITE, QuoteSlot.UPPER_YES_ASK.value: QuoteAction.NO_QUOTE}
    assert select_write_action(actions, {QuoteSlot.LOWER_YES_BID.value: result.working_order}) is None


# ---------------------------------------------------------------------------
# Correction 04 -- strict terminal-reconciliation theorem, independent of
# whether an MM cancel intent was ever persisted (the mere existence of any
# RECONCILIATION_RECORDED for the bound order is not sufficient; it must
# postdate the latest order/fill evidence and carry exact closure fields).
# These scenarios deliberately omit any MM cancel intent so they exercise
# the terminal-status branch directly rather than Correction 03's
# already-strict _cancel_hold_active path.
# ---------------------------------------------------------------------------


def _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, *, suffix: str, status: str, remaining: str = "0.00"):
    """A strategy-owned order reaches a terminal venue status (e.g. via an
    external/emergency cancellation or a full fill) with NO persisted MM
    cancel intent at all. Returns venue_order_id."""
    from arb.execution_ledger import EventInput, EventType as ET
    client_order_id = f"d{suffix}0000-0000-4000-8000-000000000000"
    venue_order_id = f"venue-order-terminal-{suffix}"
    _persist_mm_create(
        locked, session_id, inputs, request_id="req_" + suffix * 30 + "01", execution_attempt_id="ea_" + suffix * 30 + "01",
        client_order_id=client_order_id,
    )
    locked.append_batch((EventInput(ET.ORDER_IDENTITY_BOUND, {
        "client_order_id": client_order_id, "venue_order_id": venue_order_id, "venue": "KALSHI",
        "environment": "KALSHI_DEMO", "incident_id": "SYNTHETIC_MM_TEST_RESTART_INCIDENT",
        "binding_basis_event_ids": [],
    }, session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None),))
    canonical_order = {"order_id": venue_order_id, "status": status, "remaining_count_fp": remaining}
    obs = locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": f"synthetic-terminal-read-{suffix}", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_order),
        "observation_semantic_class": "AUTHORITATIVE_TERMINAL_ORDER",
    }, session_id, None, None),)).events[-1]
    return venue_order_id, obs.sequence


def _reconstruct(locked, *, events=None):
    return reconstruct_slot_ownership(
        events if events is not None else locked.events, strategy_instance_id="mm_" + "1" * 32,
        market_ticker="TICK-1", quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )


def test_c04_01_terminal_with_unresolved_reconciliation_blocks(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c1", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id, write_closure_class="UNRESOLVED"),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_c04_02_terminal_with_unknown_result_true_blocks(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c2", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id, unknown_result=True),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_c04_03_terminal_with_active_upper_bound_remains_blocks(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c3", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id, active_order_upper_bound=1),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_c04_04_reconciliation_predating_terminal_observation_blocks(writer_eligible_ledger) -> None:
    """A qualifying reconciliation exists, but a terminal ORDER_OBSERVED is
    recorded AFTER it -- the reconciliation cannot have closed evidence that
    did not yet exist when it was persisted."""
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    client_order_id = "d40000-0000-4000-8000-000000000000"
    venue_order_id = "venue-order-terminal-c4"
    _persist_mm_create(
        locked, session_id, inputs, request_id="req_" + "c4" * 15 + "01", execution_attempt_id="ea_" + "c4" * 15 + "01",
        client_order_id=client_order_id,
    )
    locked.append_batch((EventInput(ET.ORDER_IDENTITY_BOUND, {
        "client_order_id": client_order_id, "venue_order_id": venue_order_id, "venue": "KALSHI",
        "environment": "KALSHI_DEMO", "incident_id": "SYNTHETIC_MM_TEST_RESTART_INCIDENT",
        "binding_basis_event_ids": [],
    }, session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None),))
    # Stale/early reconciliation exists first ...
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    # ... and only afterward does the terminal observation appear.
    canonical_order = {"order_id": venue_order_id, "status": "canceled", "remaining_count_fp": "0.00"}
    locked.append_batch((EventInput(ET.ORDER_OBSERVED, {
        "venue_order_id": venue_order_id, "client_order_id": client_order_id,
        "source_request_id": "synthetic-terminal-read-c4", "source_operation": "GET_ORDER_V2",
        "venue_payload_schema_id": "synthetic-order-v1", "canonical_venue_payload": canonical_order,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_order),
        "observation_semantic_class": "AUTHORITATIVE_TERMINAL_ORDER",
    }, session_id, None, None),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_c04_05_reconciliation_predating_later_fill_blocks(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c5", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    canonical_fill = {"fill_id": "fill-terminal-c5", "order_id": venue_order_id, "market": "TICK-1", "outcome_side": "YES", "quantity": "1.00", "yes_price": "0.44"}
    locked.append_batch((EventInput(ET.FILL_OBSERVED, {
        "venue_fill_id": "fill-terminal-c5", "venue_order_id": venue_order_id, "client_order_id": "irrelevant",
        "source_request_id": "synthetic-late-fill-c5", "source_operation": "SYNTHETIC_FILL_READ",
        "venue_payload_schema_id": "synthetic-fill-v1", "canonical_venue_payload": canonical_fill,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_fill),
    }, session_id, None, None),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_c04_06_newer_reconciliation_after_later_fill_closes(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c6", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    canonical_fill = {"fill_id": "fill-terminal-c6", "order_id": venue_order_id, "market": "TICK-1", "outcome_side": "YES", "quantity": "1.00", "yes_price": "0.44"}
    locked.append_batch((EventInput(ET.FILL_OBSERVED, {
        "venue_fill_id": "fill-terminal-c6", "venue_order_id": venue_order_id, "client_order_id": "irrelevant",
        "source_request_id": "synthetic-late-fill-c6", "source_operation": "SYNTHETIC_FILL_READ",
        "venue_payload_schema_id": "synthetic-fill-v1", "canonical_venue_payload": canonical_fill,
        "canonical_venue_payload_sha256": sha256_hex_of(canonical_fill),
    }, session_id, None, None),))
    # A fresh reconciliation follows the fill.
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.TERMINAL_RECONCILED.value


def test_c04_07_exact_current_authoritative_closure_passes(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c7", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.TERMINAL_RECONCILED.value
    assert result.working_order is None


def test_c04_08_wrong_bound_order_reconciliation_blocks(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c8", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id="some-other-order-entirely"),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value


def test_c04_09_executed_status_requires_reconciliation(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c9", status="executed")
    before_events = list(locked.events)
    result_before = _reconstruct(locked, events=before_events)
    assert result_before.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value

    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result_after = _reconstruct(locked)
    assert result_after.classification == SlotClassification.TERMINAL_RECONCILED.value


def test_c04_10_downstream_comparison_holds_not_create_new(writer_eligible_ledger) -> None:
    from arb.execution_ledger import EventInput, EventType as ET
    locked, session_id, inputs = writer_eligible_ledger
    venue_order_id, _seq = _establish_terminal_order_no_cancel_intent(locked, session_id, inputs, suffix="c10", status="canceled")
    locked.append_batch((EventInput(
        ET.RECONCILIATION_RECORDED, _reconciliation_payload(bound_order_id=venue_order_id, write_closure_class="UNRESOLVED"),
        session_id, "SYNTHETIC_MM_TEST_RESTART_INCIDENT", None,
    ),))
    result = _reconstruct(locked)
    assert result.classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value
    action = compare_slot(
        desired=desired(yes_price=D("0.44")), plan_valid=True, classification=result.classification,
        working_order=result.working_order, price_ranges=(), keep_reprice_distance_grid_steps=2,
        best_yes_bid=D("0.40"), best_yes_ask=D("0.50"), risk_control_state="WRITER_ELIGIBLE",
    )
    assert action is QuoteAction.HOLD_NO_STRATEGY_WRITE
    assert action is not QuoteAction.CREATE_NEW
