from __future__ import annotations

import copy
import pickle
import threading
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest

from arb.venues.kalshi.order_lifecycle import invoke_permit_required_normal_write
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    CandidateOrderV1,
    EconomicFillV1,
    FlowRiskLimits,
    FreshnessRegistry,
    FreshnessStampV1,
    HISTORICAL_INCIDENT_CANCEL_TARGET,
    HISTORICAL_INCIDENT_WRITER_RELEASE_ELIGIBLE,
    HISTORICAL_UNRESOLVED_EXPOSURE,
    NormalWriteAdapter,
    NormalWriterPermit,
    OrderbookReferenceV1,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    PriceRangeV1,
    PermitStage,
    RiskControlCode,
    RiskControlError,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    UNKNOWN_UNBOUNDED,
    VenueDefensePolicy,
    WorkingOrderV1,
    WriterEligibilityAssessment,
    WriterEligibilityGate,
    build_orderbook_reference,
    compute_market_economic_state,
    enforce_projected_limits,
    freshness_age_ms,
    price_reasonable,
    project_candidate_risk,
    validate_price_ranges,
)


D = Decimal
HASH = "a" * 64
T0 = "2026-08-13T20:00:00.000000Z"


def config() -> RiskLimitConfigV1:
    return RiskLimitConfigV1(
        1,
        "kalshi-demo:portfolio:0",
        "USD",
        PerOrderRiskLimits(D("10"), D("10"), True, D("0.10"), 1_000),
        PerMarketRiskLimits(D("20"), D("20"), 10, D("20"), D("20")),
        AccountRiskLimits(D("100"), 50, D("100"), 0, D("0")),
        FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
        StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
        VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
    )


def test_complete_decimal_config_is_immutable_and_content_addressed() -> None:
    value = config()
    assert value.sha256 == config().sha256
    assert len(value.sha256) == 64
    with pytest.raises(Exception):
        value.currency = "EUR"  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        PerOrderRiskLimits(D("1"), D("1"), 1, D("0"), 1),
        PerOrderRiskLimits(D("1"), D("1"), True, D("0"), True),
        PerOrderRiskLimits(D("NaN"), D("1"), True, D("0"), 1),
    ],
)
def test_config_rejects_missing_wrong_boolean_integer_and_nonfinite_values(bad: object) -> None:
    good = config()
    with pytest.raises(RiskControlError) as caught:
        RiskLimitConfigV1(
            1, good.conflict_domain, "USD", bad, good.per_market,
            good.conflict_domain_account, good.flow, good.state_integrity, good.venue_defense,
        )
    assert caught.value.code is RiskControlCode.RISK_LIMIT_CONFIG_INVALID


def test_price_ranges_and_two_sided_reference_are_exact_decimal() -> None:
    ranges = (PriceRangeV1(D("0"), D("0.50"), D("0.01")), PriceRangeV1(D("0.50"), D("1.00"), D("0.01")))
    assert validate_price_ranges(D("0.50"), ranges)
    with pytest.raises(RiskControlError):
        validate_price_ranges(D("0.505"), ranges)
    reference = build_orderbook_reference(((D("0.40"), D("1")),), ((D("0.50"), D("1")),))
    assert reference == OrderbookReferenceV1(D("0.40"), D("0.50"), D("0.5000"), D("0.4500"))
    assert price_reasonable(D("0.50"), reference, D("0.05"))
    assert not price_reasonable(D("0.5001"), reference, D("0.05"))
    with pytest.raises(RiskControlError):
        build_orderbook_reference(((D("0.60"), D("1")),), ((D("0.50"), D("1")),))


def test_freshness_uses_first_receipt_monotonic_ceiling_and_fails_closed() -> None:
    stamp = FreshnessStampV1("proc_" + "1" * 32, T0, 1_000_000_000, "NONE", None, HASH)
    registry = FreshnessRegistry()
    assert registry.accept(stamp) is stamp
    later = FreshnessStampV1(stamp.process_instance_id, T0, 9_000_000_000, "NONE", None, HASH)
    assert registry.accept(later) is stamp
    assert freshness_age_ms(
        stamp, current_process_instance_id=stamp.process_instance_id,
        now_monotonic_ns=1_001_000_001, now_utc=T0, max_age_ms=2,
        max_future_wall_clock_skew_ms=0,
    ) == 2
    with pytest.raises(RiskControlError) as stale:
        freshness_age_ms(
            stamp, current_process_instance_id=stamp.process_instance_id,
            now_monotonic_ns=1_002_000_001, now_utc=T0, max_age_ms=2,
            max_future_wall_clock_skew_ms=0,
        )
    assert stale.value.code is RiskControlCode.MARKET_DATA_STALE
    with pytest.raises(RiskControlError) as process:
        freshness_age_ms(
            stamp, current_process_instance_id="proc_" + "2" * 32,
            now_monotonic_ns=stamp.received_monotonic_ns, now_utc=T0,
            max_age_ms=1, max_future_wall_clock_skew_ms=0,
        )
    assert process.value.code is RiskControlCode.MARKET_DATA_STALE
    with pytest.raises(RiskControlError) as regression:
        freshness_age_ms(
            stamp, current_process_instance_id=stamp.process_instance_id,
            now_monotonic_ns=stamp.received_monotonic_ns - 1, now_utc=T0,
            max_age_ms=1, max_future_wall_clock_skew_ms=0,
        )
    assert regression.value.code is RiskControlCode.CLOCK_REGRESSION


def test_fifo_offsets_and_projected_liability_conservatively_include_working_orders() -> None:
    fills = (
        EconomicFillV1("M", "f1", "YES", D("3"), D("0.40"), "2026-08-13T20:00:00.000000Z"),
        EconomicFillV1("M", "f2", "NO", D("1"), D("0.55"), "2026-08-13T20:00:01.000000Z"),
    )
    working = (WorkingOrderV1("M", "o1", "NO", D("2"), D("0.60")),)
    state = compute_market_economic_state("M", fills, working)
    assert state.filled_exposure_usd == D("0.80")
    assert state.signed_net_position == D("2")
    assert state.working_exposure_usd == D("0.80")
    candidate = CandidateOrderV1("M", "YES", D("1"), D("0.50"))
    projected = project_candidate_risk(state, candidate)
    assert projected.candidate_exposure_usd == D("0.50")
    assert projected.projected_market_gross_exposure_usd == D("2.10")
    enforce_projected_limits(projected, candidate, config())


def test_unknown_unbounded_and_limits_fail_closed() -> None:
    state = compute_market_economic_state("M", (), ())
    candidate = CandidateOrderV1("M", "YES", D("1"), D("0.50"))
    with pytest.raises(RiskControlError) as unknown:
        enforce_projected_limits(project_candidate_risk(state, candidate, UNKNOWN_UNBOUNDED), candidate, config())
    assert unknown.value.code is RiskControlCode.UNKNOWN_UNBOUNDED_EXPOSURE
    too_large = CandidateOrderV1("M", "YES", D("11"), D("0.50"))
    with pytest.raises(RiskControlError) as exceeded:
        enforce_projected_limits(project_candidate_risk(state, too_large), too_large, config())
    assert exceeded.value.code is RiskControlCode.RISK_LIMIT_EXCEEDED


def test_normal_writer_permit_is_unforgeable_and_only_adapter_bridge_is_supported() -> None:
    with pytest.raises(RiskControlError) as forged:
        NormalWriterPermit(object())
    assert forged.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID
    with pytest.raises(RiskControlError):
        NormalWriteAdapter(object(), lambda request: request)  # type: ignore[arg-type]
    with pytest.raises(RiskControlError) as raw:
        invoke_permit_required_normal_write(lambda request: request, object(), object())  # type: ignore[arg-type]
    assert raw.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID


class _FakeLocked:
    def __init__(self) -> None:
        self.conflict_domain_ref = "kalshi-demo:portfolio:0"
        self.events = [SimpleNamespace(sequence=10, event_hash="1" * 64)]
        self.authority_row = SimpleNamespace(trusted_sequence=10, trusted_event_hash="1" * 64)

    def projection(self):
        return SimpleNamespace(
            active_writer_session_id="ws_" + "1" * 32,
            risk_control_state="WRITER_ELIGIBLE",
            risk_state_epoch=7,
            active_risk_config_sha256="c" * 64,
        )

    def append_batch(self, inputs):
        item = inputs[0]
        event = SimpleNamespace(
            sequence=self.events[-1].sequence + 1,
            previous_event_hash=self.events[-1].event_hash,
            event_hash=str(self.events[-1].sequence + 1).zfill(64),
            event_id=item.event_id,
            execution_attempt_id=item.execution_attempt_id,
        )
        self.events.append(event)
        self.authority_row.trusted_sequence = event.sequence
        self.authority_row.trusted_event_hash = event.event_hash
        return SimpleNamespace(events=(event,))


def _assessment() -> WriterEligibilityAssessment:
    return WriterEligibilityAssessment(
        "ra_" + "1" * 32, "CREATE_ORDER_V2", "req_" + "2" * 32,
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64,
        "f" * 64, "0" * 64, 7, 2_000_000_000, True,
    )


def _uuid_factory():
    number = 100

    def mint() -> uuid.UUID:
        nonlocal number
        value = uuid.UUID(int=number, version=4)
        number += 1
        return value

    return mint


def test_normal_permit_t0_through_t3_is_ordered_one_shot_and_nonserializable() -> None:
    clock_values = iter((1_000_000_000, 1_000_000_001, 1_000_000_002, 1_000_000_003))
    gate = WriterEligibilityGate(
        monotonic_clock_ns=lambda: next(clock_values),
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = _FakeLocked()
    permit = gate.issue_permit(
        locked=locked, normal_writer_session_id="ws_" + "1" * 32,
        assessment=_assessment(),
        intent_payload={
            "execution_attempt_id": "ea_" + "3" * 32,
            "intent_payload": {"request_id": "req_" + "2" * 32},
        },
        prepared_payload={
            "request_id": "req_" + "2" * 32,
            "operation_name": "CREATE_ORDER_V2",
            "prepared_request_sha256": "a" * 64,
        },
    )
    assert gate.progress_snapshot(permit)["stage"] is PermitStage.INTENT
    for operation, stage in (
        (gate.persist_intent, PermitStage.PREPARED),
        (gate.persist_prepared, PermitStage.SEND_BOUNDARY),
        (gate.persist_send_boundary, PermitStage.CONSUMED),
    ):
        operation(permit, locked)
        assert gate.progress_snapshot(permit)["stage"] is stage
    calls = []
    adapter = NormalWriteAdapter(gate, lambda request: calls.append(request) or "ok")
    assert adapter.invoke(permit, "request") == "ok"
    assert calls == ["request"]
    with pytest.raises(RiskControlError) as reused:
        adapter.invoke(permit, "request")
    assert reused.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_ALREADY_CONSUMED
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError):
            operation(permit)


def test_hard_halt_latch_wins_before_adapter_entry_and_invalidates_unused_permit() -> None:
    clock_values = iter((1_000_000_000, 1_000_000_001, 1_000_000_002, 1_000_000_003))
    gate = WriterEligibilityGate(
        monotonic_clock_ns=lambda: next(clock_values),
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = _FakeLocked()
    permit = gate.issue_permit(
        locked=locked, normal_writer_session_id="ws_" + "1" * 32,
        assessment=_assessment(), intent_payload={
            "execution_attempt_id": "ea_" + "3" * 32,
            "intent_payload": {"request_id": "req_" + "2" * 32},
        },
        prepared_payload={"request_id": "req_" + "2" * 32, "operation_name": "CREATE_ORDER_V2", "prepared_request_sha256": "a" * 64},
    )
    gate.persist_intent(permit, locked)
    gate.persist_prepared(permit, locked)
    gate.persist_send_boundary(permit, locked)
    calls = []
    gate.latch_hard_halt()
    with pytest.raises(RiskControlError) as halted:
        NormalWriteAdapter(gate, lambda request: calls.append(request)).invoke(permit, object())
    assert halted.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID
    assert calls == []


def _consumed_permit_gate():
    now = 1_000_000_000

    def tick() -> int:
        nonlocal now
        now += 1
        return now

    gate = WriterEligibilityGate(
        monotonic_clock_ns=tick,
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = _FakeLocked()
    permit = gate.issue_permit(
        locked=locked, normal_writer_session_id="ws_" + "1" * 32,
        assessment=_assessment(), intent_payload={
            "execution_attempt_id": "ea_" + "3" * 32,
            "intent_payload": {"request_id": "req_" + "2" * 32},
        },
        prepared_payload={
            "request_id": "req_" + "2" * 32,
            "operation_name": "CREATE_ORDER_V2",
            "prepared_request_sha256": "a" * 64,
        },
    )
    gate.persist_intent(permit, locked)
    gate.persist_prepared(permit, locked)
    gate.persist_send_boundary(permit, locked)
    return gate, permit


def test_halt_own_08_already_entered_ambiguous_transport_is_never_repeated() -> None:
    gate, permit = _consumed_permit_gate()
    calls: list[object] = []

    def ambiguous(request: object) -> object:
        calls.append(request)
        raise RuntimeError("synthetic ambiguous transport result")

    adapter = NormalWriteAdapter(gate, ambiguous)
    with pytest.raises(RuntimeError):
        adapter.invoke(permit, "request")
    gate.latch_hard_halt()
    with pytest.raises(RiskControlError):
        adapter.invoke(permit, "request")
    assert calls == ["request"]
    assert gate.progress_snapshot(permit)["transport_invocation_count"] == 1


def test_adapter_halt_race_has_only_entered_once_or_halt_wins() -> None:
    gate_a, permit_a = _consumed_permit_gate()
    entered = threading.Event()
    release = threading.Event()
    calls_a: list[object] = []

    def blocking_transport(request: object) -> object:
        calls_a.append(request)
        entered.set()
        assert release.wait(timeout=5)
        return "ok"

    adapter_a = NormalWriteAdapter(gate_a, blocking_transport)
    outcome: list[object] = []
    worker = threading.Thread(target=lambda: outcome.append(adapter_a.invoke(permit_a, "request")))
    worker.start()
    assert entered.wait(timeout=5)
    gate_a.latch_hard_halt()
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert calls_a == ["request"]
    assert outcome == ["ok"]
    with pytest.raises(RiskControlError):
        adapter_a.invoke(permit_a, "request")
    assert calls_a == ["request"]

    gate_b, permit_b = _consumed_permit_gate()
    calls_b: list[object] = []
    gate_b.latch_hard_halt()
    with pytest.raises(RiskControlError):
        NormalWriteAdapter(gate_b, lambda request: calls_b.append(request)).invoke(permit_b, "request")
    assert calls_b == []
    assert gate_b.hard_halt_requested is True


@pytest.mark.parametrize("movement_before", ("T1", "T2", "T3"))
def test_correction02_07_unrelated_tail_movement_before_each_stage_blocks_transport(
    movement_before: str,
) -> None:
    now = 1_000_000_000

    def tick() -> int:
        nonlocal now
        now += 1
        return now

    gate = WriterEligibilityGate(
        monotonic_clock_ns=tick,
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = _FakeLocked()
    permit = gate.issue_permit(
        locked=locked, normal_writer_session_id="ws_" + "1" * 32,
        assessment=_assessment(), intent_payload={
            "execution_attempt_id": "ea_" + "3" * 32,
            "intent_payload": {"request_id": "req_" + "2" * 32},
        },
        prepared_payload={
            "request_id": "req_" + "2" * 32,
            "operation_name": "CREATE_ORDER_V2",
            "prepared_request_sha256": "a" * 64,
        },
    )

    def move_tail() -> None:
        sequence = locked.events[-1].sequence + 1
        event_hash = f"{sequence:064x}"
        locked.events.append(SimpleNamespace(sequence=sequence, event_hash=event_hash))
        locked.authority_row.trusted_sequence = sequence
        locked.authority_row.trusted_event_hash = event_hash

    if movement_before == "T1":
        move_tail()
        operation = gate.persist_intent
    elif movement_before == "T2":
        gate.persist_intent(permit, locked)
        move_tail()
        operation = gate.persist_prepared
    else:
        gate.persist_intent(permit, locked)
        gate.persist_prepared(permit, locked)
        move_tail()
        operation = gate.persist_send_boundary

    with pytest.raises(RiskControlError) as moved:
        operation(permit, locked)
    assert moved.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL
    calls: list[object] = []
    with pytest.raises(RiskControlError):
        NormalWriteAdapter(gate, lambda request: calls.append(request)).invoke(permit, object())
    assert calls == []


def test_historical_incident_remains_non_releasable_unknown_and_has_no_cancel_target() -> None:
    assert HISTORICAL_INCIDENT_CANCEL_TARGET is None
    assert HISTORICAL_INCIDENT_WRITER_RELEASE_ELIGIBLE is False
    assert HISTORICAL_UNRESOLVED_EXPOSURE == UNKNOWN_UNBOUNDED
