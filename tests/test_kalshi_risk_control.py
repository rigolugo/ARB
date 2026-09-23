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
from arb.execution_ledger import canonical_json_bytes, sha256_hex
from arb.venues.kalshi.risk_control import (
    ACCOUNT_AGGREGATE_UNIVERSE_COMPLETE,
    AccountAggregateAuthorityExpectationV1,
    AccountAggregateInputV1,
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
    account_aggregate_current_state_within_limits,
    account_aggregate_snapshot_preimage,
    build_account_aggregate_authority_expectation,
    build_account_aggregate_snapshot,
    build_orderbook_reference,
    compute_account_aggregate_totals,
    compute_market_economic_state,
    enforce_account_aggregate_limits,
    enforce_projected_limits,
    freshness_age_ms,
    price_reasonable,
    project_account_aggregate,
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


FAKE_CONFLICT_DOMAIN_REF = "kalshi-demo:portfolio:0"
FAKE_AUTHORITY_NAMESPACE_ID = "fake-authority-namespace"
FAKE_AUTHORITY_INSTANCE_ID = "fake-authority-instance"
FAKE_LEDGER_INSTANCE_ID = "fake-ledger-instance"


class _FakeLocked:
    def __init__(self) -> None:
        self.conflict_domain_ref = FAKE_CONFLICT_DOMAIN_REF
        self.events = [SimpleNamespace(sequence=10, event_hash="1" * 64)]
        self.authority_row = SimpleNamespace(trusted_sequence=10, trusted_event_hash="1" * 64)
        # CORRECTION_01 Gate B reads the authoritative store identities
        # directly off the locked ledger.
        self.authority_meta = SimpleNamespace(
            authority_namespace_id=FAKE_AUTHORITY_NAMESPACE_ID,
            authority_instance_id=FAKE_AUTHORITY_INSTANCE_ID,
        )
        self.ledger_meta = SimpleNamespace(ledger_instance_id=FAKE_LEDGER_INSTANCE_ID)

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


# --- R1-B03 T26-T28, DSB-WRITER-007: active-domain permit commitments ------
from dataclasses import fields as _rc_fields
from arb.venues.kalshi.risk_control import (
    NormalWriterPermit as _NWP,
    WriterEligibilityAssessment as _WEA,
    compute_permit_domain_commitment_sha256 as _permit_digest,
)
from arb.execution_ledger import canonical_json_bytes as _cjb, sha256_hex as _sha


def test_dsb_writer_007_assessment_gains_active_fields() -> None:
    names = {f.name for f in _rc_fields(_WEA)}
    assert {"domain_binding_id", "domain_binding_sha256", "active_contract_id",
            "active_contract_sha256", "bootstrap_contract_sha256", "conflict_domain_ref",
            "account_scope_ref", "subaccount", "exchange_index", "environment",
            "incident_id", "writer_proof_id"} <= names
    # legacy construction (no active fields) still works
    a = _WEA(risk_assessment_id="ra_" + "0" * 32, operation_kind="CREATE_ORDER_V2",
             request_id="req_" + "0" * 32, candidate_request_sha256="a" * 64,
             candidate_economic_sha256="b" * 64, risk_config_sha256="c" * 64,
             market_data_snapshot_sha256="d" * 64, market_data_freshness_identity_sha256="e" * 64,
             reconciliation_snapshot_sha256="f" * 64, reconciliation_freshness_identity_sha256="1" * 64,
             risk_state_epoch=1, freshness_deadline_monotonic_ns=1, eligible=True)
    assert a.domain_binding_sha256 is None


def test_dsb_writer_007_permit_gains_active_fields_and_digest_helper() -> None:
    names = {f.name for f in _rc_fields(_NWP)}
    assert {"domain_binding_id", "domain_binding_sha256", "active_contract_id",
            "active_contract_sha256", "environment", "account_scope_ref", "subaccount",
            "exchange_index", "incident_id", "writer_proof_id", "bootstrap_contract_sha256",
            "permit_domain_commitment_sha256"} <= names


def test_dsb_writer_007_permit_domain_commitment_formula() -> None:
    # Correction 02 DSB-WRITER-007 / DSB-QUOTE-003: the digest additionally
    # folds in the exact trusted dynamic read-set identity so a permit cannot
    # be carried across current-read acquisitions.
    p = SimpleNamespace(
        account_scope_ref="ARB_KALSHI_DEMO_PRIMARY_ACCOUNT",
        active_contract_id="AEDC1_" + "0" * 64, active_contract_sha256="0" * 64,
        bootstrap_contract_sha256="1" * 64, conflict_domain_ref="KALSHI|KALSHI_DEMO|X|SUBACCOUNT=1",
        domain_binding_id="KEDB1_" + "2" * 64, domain_binding_sha256="2" * 64,
        environment="KALSHI_DEMO", exchange_index=0, incident_id="adi_" + "0" * 32,
        subaccount=1, writer_proof_id="adwp_" + "0" * 32,
        trusted_dynamic_read_set_id="ADRS2_" + "3" * 64)
    expected = _sha(_cjb({
        "account_scope_ref": p.account_scope_ref, "active_contract_id": p.active_contract_id,
        "active_contract_sha256": p.active_contract_sha256,
        "bootstrap_contract_sha256": p.bootstrap_contract_sha256,
        "conflict_domain_ref": p.conflict_domain_ref, "domain_binding_id": p.domain_binding_id,
        "domain_binding_sha256": p.domain_binding_sha256, "environment": p.environment,
        "exchange_index": p.exchange_index, "incident_id": p.incident_id,
        "subaccount": p.subaccount,
        "trusted_dynamic_read_set_id": p.trusted_dynamic_read_set_id,
        "writer_proof_id": p.writer_proof_id,
    }))
    assert _permit_digest(p) == expected


# ---------------------------------------------------------------------------
# CORRECTION_07 C06-RC-01..12 -- the shared conflict-domain account aggregate.
#
# These prove the ONE canonical aggregate derivation that both release /
# current-state evaluation and the CREATE candidate path consume
# (C07-AGG-001..005).  Every economic value is exact Decimal.
# ---------------------------------------------------------------------------


def _fill(market: str, fill_id: str, side: str, quantity: Decimal, yes_price: Decimal,
          created: str = "2026-08-13T20:00:00.000000Z") -> EconomicFillV1:
    return EconomicFillV1(market, fill_id, side, quantity, yes_price, created)


def _order(market: str, order_id: str, side: str, remaining: Decimal, yes_price: Decimal) -> WorkingOrderV1:
    return WorkingOrderV1(market, order_id, side, remaining, yes_price)


def aggregate_config(
    *,
    max_aggregate_exposure_usd: Decimal = D("100"),
    max_aggregate_working_orders: int = 50,
    max_aggregate_working_contracts: Decimal = D("100"),
) -> RiskLimitConfigV1:
    """``config()`` with only the three account leaves varied.  No new leaf is
    introduced (C07-AGG-002)."""
    base = config()
    return RiskLimitConfigV1(
        base.schema_version, base.conflict_domain, base.currency, base.per_order, base.per_market,
        AccountRiskLimits(
            max_aggregate_exposure_usd, max_aggregate_working_orders, max_aggregate_working_contracts,
            base.conflict_domain_account.max_unresolved_write_count,
            base.conflict_domain_account.max_conservative_unresolved_write_exposure_usd,
        ),
        base.flow, base.state_integrity, base.venue_defense,
    )


def test_c06_rc_01_shared_helper_sums_unresolved_plus_all_market_filled_and_working() -> None:
    """C06-RC-01: the aggregate is exactly unresolved + every market's filled
    exposure + every market's working exposure, in exact Decimal."""

    fills = (
        _fill("MKT-A", "f1", "YES", D("1.00"), D("0.40")),   # filled liability 0.4000
        _fill("MKT-B", "f2", "NO", D("2.00"), D("0.25")),    # filled liability 2 * 0.7500 = 1.5000
    )
    orders = (
        _order("MKT-A", "o1", "YES", D("1.00"), D("0.30")),  # working liability 0.3000
        _order("MKT-B", "o2", "NO", D("1.00"), D("0.90")),   # working liability 0.1000
    )
    totals = compute_account_aggregate_totals(
        fills=fills, working_orders=orders, unresolved_exposure=D("0.05"),
    )

    expected = D("0.05") + D("0.4000") + D("0.3000") + D("1.5000") + D("0.1000")
    assert totals.aggregate_exposure_usd == expected
    assert type(totals.aggregate_exposure_usd) is Decimal
    assert totals.unresolved_exposure_usd == D("0.05")
    assert totals.markets == ("MKT-A", "MKT-B")


def test_c06_rc_02_working_order_and_contract_totals_sum_across_markets() -> None:
    """C06-RC-02."""

    orders = (
        _order("MKT-A", "o1", "YES", D("1.00"), D("0.30")),
        _order("MKT-B", "o2", "NO", D("2.00"), D("0.90")),
        _order("MKT-C", "o3", "YES", D("3.00"), D("0.10")),
    )
    totals = compute_account_aggregate_totals(
        fills=(), working_orders=orders, unresolved_exposure=D("0"),
    )

    assert totals.aggregate_working_orders == 3
    assert totals.aggregate_working_contracts == D("6.00")
    assert totals.markets == ("MKT-A", "MKT-B", "MKT-C")


def test_c06_rc_03_candidate_projection_adds_liability_one_order_and_quantity() -> None:
    """C06-RC-03: exactly candidate liability + 1 order + candidate quantity."""

    totals = compute_account_aggregate_totals(
        fills=(), working_orders=(_order("MKT-A", "o1", "YES", D("1.00"), D("0.30")),),
        unresolved_exposure=D("0"),
    )
    candidate = CandidateOrderV1("MKT-B", "NO", D("2.00"), D("0.25"))
    projected = project_account_aggregate(totals, candidate)

    # NO candidate liability = quantity * (1.0000 - yes_price)
    assert projected.candidate_exposure_usd == D("2.00") * (D("1.0000") - D("0.25"))
    assert projected.projected_exposure_usd == totals.aggregate_exposure_usd + projected.candidate_exposure_usd
    assert projected.projected_working_orders == totals.aggregate_working_orders + 1
    assert projected.projected_working_contracts == totals.aggregate_working_contracts + D("2.00")


def _projected_for(*, fills=(), orders=(), unresolved=D("0"), candidate=None):
    totals = compute_account_aggregate_totals(
        fills=fills, working_orders=orders, unresolved_exposure=unresolved,
    )
    candidate = candidate or CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.50"))
    return totals, project_account_aggregate(totals, candidate)


def test_c06_rc_04_aggregate_exposure_equality_at_limit_passes() -> None:
    """C06-RC-04: inclusive `<=` at the exact configured limit."""

    _, projected = _projected_for(candidate=CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.50")))
    assert projected.projected_exposure_usd == D("0.50")
    # Exactly at the limit -> no exception.
    enforce_account_aggregate_limits(projected, aggregate_config(max_aggregate_exposure_usd=D("0.50")))


def test_c06_rc_05_aggregate_exposure_limit_plus_one_micro_usd_fails() -> None:
    """C06-RC-05: the minimum representable excess (0.000001) fails."""

    _, projected = _projected_for(candidate=CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.50")))
    limit = projected.projected_exposure_usd - D("0.000001")
    with pytest.raises(RiskControlError) as excinfo:
        enforce_account_aggregate_limits(projected, aggregate_config(max_aggregate_exposure_usd=limit))
    assert excinfo.value.code is RiskControlCode.RISK_LIMIT_EXCEEDED


def test_c06_rc_06_aggregate_working_order_equality_passes_and_plus_one_fails() -> None:
    """C06-RC-06."""

    orders = (_order("MKT-A", "o1", "YES", D("1.00"), D("0.30")),)
    _, projected = _projected_for(orders=orders)
    assert projected.projected_working_orders == 2

    enforce_account_aggregate_limits(projected, aggregate_config(max_aggregate_working_orders=2))
    with pytest.raises(RiskControlError) as excinfo:
        enforce_account_aggregate_limits(projected, aggregate_config(max_aggregate_working_orders=1))
    assert excinfo.value.code is RiskControlCode.RISK_LIMIT_EXCEEDED


def test_c06_rc_07_aggregate_working_contract_equality_passes_and_plus_hundredth_fails() -> None:
    """C06-RC-07: the minimum representable contract excess (0.01) fails."""

    orders = (_order("MKT-A", "o1", "YES", D("1.00"), D("0.30")),)
    _, projected = _projected_for(orders=orders)
    assert projected.projected_working_contracts == D("2.00")

    enforce_account_aggregate_limits(projected, aggregate_config(max_aggregate_working_contracts=D("2.00")))
    with pytest.raises(RiskControlError) as excinfo:
        enforce_account_aggregate_limits(
            projected, aggregate_config(max_aggregate_working_contracts=D("2.00") - D("0.01")),
        )
    assert excinfo.value.code is RiskControlCode.RISK_LIMIT_EXCEEDED


def test_c06_rc_08_unknown_unbounded_unresolved_exposure_fails_closed() -> None:
    """C06-RC-08 / C07-AGG-005: UNKNOWN is never converted to zero."""

    with pytest.raises(RiskControlError) as excinfo:
        compute_account_aggregate_totals(
            fills=(), working_orders=(), unresolved_exposure=UNKNOWN_UNBOUNDED,
        )
    assert excinfo.value.code is RiskControlCode.UNKNOWN_UNBOUNDED_EXPOSURE

    # And an aggregate input carrying it cannot even be constructed.
    with pytest.raises(RiskControlError):
        account_aggregate_input(unresolved_exposure_usd=UNKNOWN_UNBOUNDED)


def test_c06_rc_09_malformed_non_finite_or_float_economic_input_cannot_enter_the_gate() -> None:
    """C06-RC-09: float and non-finite economic values are rejected at the
    element boundary, so they can never reach the aggregate arithmetic."""

    with pytest.raises(RiskControlError):
        EconomicFillV1("MKT-A", "f1", "YES", 1.0, D("0.40"), T0)  # type: ignore[arg-type]
    with pytest.raises(RiskControlError):
        EconomicFillV1("MKT-A", "f1", "YES", D("1.00"), D("NaN"), T0)
    with pytest.raises(RiskControlError):
        WorkingOrderV1("MKT-A", "o1", "YES", D("1.00"), 0.3)  # type: ignore[arg-type]
    with pytest.raises(RiskControlError):
        compute_account_aggregate_totals(
            fills=(), working_orders=(), unresolved_exposure=0.0,  # type: ignore[arg-type]
        )
    # A foreign element type is rejected even if it quacks like a fill.
    with pytest.raises(RiskControlError):
        compute_account_aggregate_totals(
            fills=(SimpleNamespace(market="MKT-A"),), working_orders=(), unresolved_exposure=D("0"),
        )


def test_c06_rc_10_candidate_in_one_market_counts_exposure_from_another_market() -> None:
    """C06-RC-10: the account aggregate is genuinely cross-market -- a
    ticker-scoped view of MKT-A alone would miss the MKT-B exposure."""

    fills = (_fill("MKT-B", "f1", "YES", D("1.00"), D("0.60")),)
    orders = (_order("MKT-B", "o1", "YES", D("1.00"), D("0.20")),)
    totals, projected = _projected_for(
        fills=fills, orders=orders,
        candidate=CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.50")),
    )

    assert totals.markets == ("MKT-B",)
    assert totals.aggregate_exposure_usd == D("0.6000") + D("0.2000")
    assert projected.projected_exposure_usd == D("0.6000") + D("0.2000") + D("0.5000")
    assert projected.projected_working_orders == 2
    assert projected.projected_working_contracts == D("2.00")

    # A candidate-only view (no other market) would be strictly smaller.
    only_candidate = project_account_aggregate(
        compute_account_aggregate_totals(fills=(), working_orders=(), unresolved_exposure=D("0")),
        CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.50")),
    )
    assert only_candidate.projected_exposure_usd < projected.projected_exposure_usd


def test_c06_rc_11_filled_exposure_remains_after_the_order_stops_resting() -> None:
    """C06-RC-11: a fill's economic exposure survives its order leaving the
    working set -- it is not double counted and it is not dropped."""

    fills = (_fill("MKT-A", "f1", "YES", D("1.00"), D("0.40")),)
    with_order = compute_account_aggregate_totals(
        fills=fills, working_orders=(_order("MKT-A", "o1", "YES", D("1.00"), D("0.30")),),
        unresolved_exposure=D("0"),
    )
    without_order = compute_account_aggregate_totals(
        fills=fills, working_orders=(), unresolved_exposure=D("0"),
    )

    assert with_order.aggregate_exposure_usd == D("0.4000") + D("0.3000")
    assert without_order.aggregate_exposure_usd == D("0.4000")
    assert without_order.aggregate_working_orders == 0
    assert without_order.aggregate_working_contracts == D("0")


def test_c06_rc_12_unresolved_exposure_is_counted_exactly_once() -> None:
    """C06-RC-12: unresolved exposure appears once regardless of how many
    markets are represented."""

    orders = (
        _order("MKT-A", "o1", "YES", D("1.00"), D("0.10")),
        _order("MKT-B", "o2", "YES", D("1.00"), D("0.10")),
        _order("MKT-C", "o3", "YES", D("1.00"), D("0.10")),
    )
    unresolved = D("0.07")
    totals = compute_account_aggregate_totals(
        fills=(), working_orders=orders, unresolved_exposure=unresolved,
    )

    assert len(totals.markets) == 3
    assert totals.aggregate_exposure_usd == unresolved + D("0.3000")
    zero_unresolved = compute_account_aggregate_totals(
        fills=(), working_orders=orders, unresolved_exposure=D("0"),
    )
    assert totals.aggregate_exposure_usd - zero_unresolved.aggregate_exposure_usd == unresolved


# ---------------------------------------------------------------------------
# CORRECTION_07 C07-AGG-004/005 -- aggregate snapshot identity and
# fail-closed universe construction.
# ---------------------------------------------------------------------------


AGG_READ_SET_ID = "ADRS2_" + "b" * 64


def account_aggregate_input(**overrides) -> AccountAggregateInputV1:
    values = dict(
        conflict_domain_ref="kalshi-demo:portfolio:0",
        authority_namespace_id="ns-1",
        authority_instance_id="auth-1",
        ledger_instance_id="ledger-1",
        authority_trusted_sequence=7,
        authority_trusted_hash="c" * 64,
        ledger_terminal_sequence=7,
        ledger_terminal_hash="c" * 64,
        risk_config_sha256=config().sha256,
        trusted_dynamic_read_set_id=AGG_READ_SET_ID,
        reconciliation_snapshot_sha256="d" * 64,
        universe_completeness=ACCOUNT_AGGREGATE_UNIVERSE_COMPLETE,
        conflict_ids=(),
        fills=(),
        working_orders=(),
        unresolved_exposure_usd=D("0"),
    )
    values.update(overrides)
    return AccountAggregateInputV1(**values)


def test_c07_agg_005_incomplete_conflicting_or_unequal_tail_universe_fails_closed() -> None:
    """C07-AGG-005 / C06-LB-08: none of these can mint a usable aggregate
    input, so no snapshot and no eligible CREATE can follow."""

    # Incomplete universe.
    with pytest.raises(RiskControlError):
        account_aggregate_input(universe_completeness="INCOMPLETE")
    # Any identity conflict.
    with pytest.raises(RiskControlError):
        account_aggregate_input(conflict_ids=("order-identity:o1",))
    # Unequal authority / ledger tail.
    with pytest.raises(RiskControlError):
        account_aggregate_input(ledger_terminal_sequence=8)
    with pytest.raises(RiskControlError):
        account_aggregate_input(ledger_terminal_hash="e" * 64)
    # Malformed read-set identity (present but not the exact ADRS2 shape).
    with pytest.raises(RiskControlError):
        account_aggregate_input(trusted_dynamic_read_set_id="ADRS2_short")
    # Malformed hashes / sequences.
    with pytest.raises(RiskControlError):
        account_aggregate_input(risk_config_sha256="nope")
    with pytest.raises(RiskControlError):
        account_aggregate_input(authority_trusted_sequence=-1, ledger_terminal_sequence=-1)


def test_c07_agg_004_snapshot_preimage_binds_identity_and_economics() -> None:
    """C07-AGG-004: the aggregate digest preimage binds every identity and
    every economic value, so any change to any of them changes the digest and
    an unchanged universe reproduces it exactly.

    CORRECTION_01: this exercises the digest derivation directly, because
    minting a snapshot now additionally requires an authoritative expectation
    that only the locked-ledger acquisition boundary can produce.  The
    end-to-end authoritative path is proven against a REAL LockedLedger in
    ``tests/test_kalshi_quote_lifecycle.py`` (CORR01-QL-01..08).
    """

    candidate = CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.50"))

    def digest(**overrides) -> str:
        aggregate_input = account_aggregate_input(**overrides)
        totals = compute_account_aggregate_totals(
            fills=aggregate_input.fills, working_orders=aggregate_input.working_orders,
            unresolved_exposure=aggregate_input.unresolved_exposure_usd,
        )
        projected = project_account_aggregate(totals, candidate)
        return sha256_hex(canonical_json_bytes(
            account_aggregate_snapshot_preimage(aggregate_input, totals, projected),
        ))

    base = digest()
    assert len(base) == 64
    assert digest() == base

    # Every bound identity participates.
    assert digest(conflict_domain_ref="kalshi-demo:portfolio:9") != base
    assert digest(authority_namespace_id="other-namespace") != base
    assert digest(authority_instance_id="other-authority") != base
    assert digest(ledger_instance_id="other-ledger") != base
    assert digest(risk_config_sha256="0" * 64) != base
    assert digest(trusted_dynamic_read_set_id="ADRS2_" + "f" * 64) != base
    assert digest(reconciliation_snapshot_sha256="9" * 64) != base
    assert digest(authority_trusted_sequence=8, ledger_terminal_sequence=8) != base

    # Every bound economic value participates.
    assert digest(working_orders=(_order("MKT-B", "o9", "YES", D("1.00"), D("0.10")),)) != base
    assert digest(unresolved_exposure_usd=D("0.01")) != base


def test_c07_agg_004_snapshot_requires_an_authoritative_expectation() -> None:
    """CORRECTION_01: a snapshot can never be minted from a self-consistent
    aggregate alone.  An authoritative expectation is mandatory, and it is
    unforgeable -- it cannot be constructed directly, only produced by the
    locked-ledger acquisition boundary."""

    aggregate_input = account_aggregate_input()
    candidate = CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.50"))

    # The expectation type cannot be constructed without the private key.
    with pytest.raises(RiskControlError) as forged:
        AccountAggregateAuthorityExpectationV1(object())
    assert forged.value.code is RiskControlCode.RISK_INPUT_UNAVAILABLE

    # A non-expectation object is rejected outright.
    for impostor in (None, object(), aggregate_input):
        with pytest.raises(RiskControlError) as excinfo:
            build_account_aggregate_snapshot(
                aggregate_input=aggregate_input, candidate=candidate,
                config=config(), expectation=impostor,  # type: ignore[arg-type]
            )
        assert excinfo.value.code is RiskControlCode.RISK_INPUT_UNAVAILABLE

    # And it cannot be minted from a locked-like impostor either.
    with pytest.raises(RiskControlError):
        build_account_aggregate_authority_expectation(
            _FakeLocked(),  # type: ignore[arg-type]
            risk_config_sha256=config().sha256, trusted_dynamic_read_set_id=None,
            reconciliation_snapshot_sha256="d" * 64,
        )


def test_c07_agg_001_release_and_candidate_share_one_numeric_meaning() -> None:
    """C07-AGG-001 / C07-06: the current-state predicate and the candidate
    projection are the same derivation with and without the candidate."""

    fills = (_fill("MKT-A", "f1", "YES", D("1.00"), D("0.40")),)
    orders = (_order("MKT-B", "o1", "YES", D("1.00"), D("0.30")),)
    totals = compute_account_aggregate_totals(
        fills=fills, working_orders=orders, unresolved_exposure=D("0"),
    )
    exact = aggregate_config(
        max_aggregate_exposure_usd=totals.aggregate_exposure_usd,
        max_aggregate_working_orders=totals.aggregate_working_orders,
        max_aggregate_working_contracts=totals.aggregate_working_contracts,
    )
    # Current state exactly at every limit passes ...
    assert account_aggregate_current_state_within_limits(totals, exact) is True
    # ... and the same state plus any candidate no longer does.
    projected = project_account_aggregate(
        totals, CandidateOrderV1("MKT-A", "YES", D("1.00"), D("0.01")),
    )
    with pytest.raises(RiskControlError):
        enforce_account_aggregate_limits(projected, exact)


# ---------------------------------------------------------------------------
# CORRECTION_01 CORR01-RC-01..03 -- permit-boundary authoritative aggregate
# identity recheck (Gate B), and partial-binding rejection.
#
# Marco C07-IMPL-BLOCK-01: a deterministic self-hash is not authority proof.
# Permit issuance therefore rechecks the aggregate's own domain/store identity
# against the LIVE locked ledger, and its config/read-set/reconciliation
# identity against the assessment's authoritative top-level values.  Neither
# side of any comparison comes from the aggregate object.
# ---------------------------------------------------------------------------


AGG_PERMIT_SNAPSHOT_SHA = "7" * 64


def _aggregate_bound_assessment(**overrides) -> WriterEligibilityAssessment:
    """``_assessment()`` plus a COMPLETE, authoritative aggregate binding that
    matches ``_FakeLocked`` exactly.  Each keyword substitutes exactly one
    aggregate identity field, leaving every other value authoritative."""

    values = dict(
        account_aggregate_snapshot_sha256=AGG_PERMIT_SNAPSHOT_SHA,
        account_aggregate_authority_trusted_sequence=10,
        account_aggregate_authority_trusted_hash="1" * 64,
        account_aggregate_ledger_terminal_sequence=10,
        account_aggregate_ledger_terminal_hash="1" * 64,
        account_aggregate_conflict_domain_ref=FAKE_CONFLICT_DOMAIN_REF,
        account_aggregate_authority_namespace_id=FAKE_AUTHORITY_NAMESPACE_ID,
        account_aggregate_authority_instance_id=FAKE_AUTHORITY_INSTANCE_ID,
        account_aggregate_ledger_instance_id=FAKE_LEDGER_INSTANCE_ID,
        # `_assessment()` carries risk_config_sha256="c"*64 and
        # reconciliation_snapshot_sha256="f"*64; the aggregate must agree.
        account_aggregate_risk_config_sha256="c" * 64,
        account_aggregate_trusted_dynamic_read_set_id=None,
        account_aggregate_reconciliation_snapshot_sha256="f" * 64,
    )
    values.update(overrides)
    return WriterEligibilityAssessment(
        "ra_" + "1" * 32, "CREATE_ORDER_V2", "req_" + "2" * 32,
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64,
        "f" * 64, "0" * 64, 7, 2_000_000_000, True,
        **values,
    )


def _issue_with(assessment: WriterEligibilityAssessment, locked=None):
    gate = WriterEligibilityGate(
        monotonic_clock_ns=lambda: 1_000_000_000,
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = locked if locked is not None else _FakeLocked()
    permit = gate.issue_permit(
        locked=locked, normal_writer_session_id="ws_" + "1" * 32, assessment=assessment,
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
    return gate, locked, permit


def test_corr01_rc_00_exact_authoritative_aggregate_binding_is_accepted() -> None:
    """Baseline: a complete aggregate binding that matches the locked domain,
    store identities, assessment identities and tail exactly DOES obtain a
    permit -- so every rejection below is caused by the single substituted
    field, not by the gate rejecting everything."""

    _gate, _locked, permit = _issue_with(_aggregate_bound_assessment())
    assert permit.request_id == "req_" + "2" * 32


def test_corr01_rc_01_permit_rechecks_domain_and_store_identity() -> None:
    """CORR01-RC-01: an aggregate identity that no longer matches the LIVE
    locked conflict domain / authority namespace / authority instance /
    ledger instance yields NO permit.

    Each case substitutes exactly one field.  A self-consistent aggregate
    digest is present and syntactically valid in every case, which is exactly
    the blocked predecessor's gap.
    """

    for field, foreign in (
        ("account_aggregate_conflict_domain_ref", "kalshi-demo:portfolio:99"),
        ("account_aggregate_authority_namespace_id", "foreign-authority-namespace"),
        ("account_aggregate_authority_instance_id", "foreign-authority-instance"),
        ("account_aggregate_ledger_instance_id", "foreign-ledger-instance"),
    ):
        assessment = _aggregate_bound_assessment(**{field: foreign})
        locked = _FakeLocked()
        before = len(locked.events)
        with pytest.raises(RiskControlError) as excinfo:
            _issue_with(assessment, locked)
        assert excinfo.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID, field
        # No permit means no T1/T2/T3 lineage was appended at all.
        assert len(locked.events) == before, field


def test_corr01_rc_02_permit_rechecks_reconciliation_read_set_and_config_identity() -> None:
    """CORR01-RC-02: an aggregate identity that does not equal the
    assessment's own authoritative reconciliation / trusted read-set /
    risk-config identity yields NO permit."""

    for field, foreign in (
        ("account_aggregate_reconciliation_snapshot_sha256", "9" * 64),
        ("account_aggregate_trusted_dynamic_read_set_id", "ADRS2_" + "b" * 64),
        ("account_aggregate_risk_config_sha256", "0" * 64),
    ):
        assessment = _aggregate_bound_assessment(**{field: foreign})
        locked = _FakeLocked()
        before = len(locked.events)
        with pytest.raises(RiskControlError) as excinfo:
            _issue_with(assessment, locked)
        assert excinfo.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID, field
        assert len(locked.events) == before, field


def test_corr01_rc_02b_partial_aggregate_binding_is_invalid() -> None:
    """CORRECTION_01: a partial aggregate binding is never accepted.  Dropping
    any single bound identity to ``None`` rejects, so a caller cannot omit the
    fields the permit gate would otherwise recheck."""

    for field in (
        "account_aggregate_snapshot_sha256",
        "account_aggregate_authority_trusted_sequence",
        "account_aggregate_authority_trusted_hash",
        "account_aggregate_ledger_terminal_sequence",
        "account_aggregate_ledger_terminal_hash",
        "account_aggregate_conflict_domain_ref",
        "account_aggregate_authority_namespace_id",
        "account_aggregate_authority_instance_id",
        "account_aggregate_ledger_instance_id",
        "account_aggregate_risk_config_sha256",
        "account_aggregate_reconciliation_snapshot_sha256",
    ):
        assessment = _aggregate_bound_assessment(**{field: None})
        with pytest.raises(RiskControlError) as excinfo:
            _issue_with(assessment)
        assert excinfo.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID, field

    # A malformed (non-hex64) snapshot digest is equally rejected.
    with pytest.raises(RiskControlError):
        _issue_with(_aggregate_bound_assessment(account_aggregate_snapshot_sha256="not-a-sha"))


def test_corr01_rc_03_moved_authority_ledger_tail_remains_fail_closed() -> None:
    """CORR01-RC-03: an assessment built at T0 whose bound tail no longer
    equals the live tail keeps the existing unexpected-tail classification and
    appends nothing.

    The ordinary CANCEL / legacy path, which carries no aggregate binding at
    all, is unaffected.
    """

    locked = _FakeLocked()
    locked.events.append(SimpleNamespace(sequence=11, event_hash="2" * 64))
    locked.authority_row.trusted_sequence = 11
    locked.authority_row.trusted_event_hash = "2" * 64
    before = len(locked.events)

    # The assessment is still bound to sequence 10 / hash "1"*64.
    with pytest.raises(RiskControlError) as excinfo:
        _issue_with(_aggregate_bound_assessment(), locked)
    assert excinfo.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL
    assert len(locked.events) == before

    # An authority row that has not caught up to the terminal event is also
    # rejected with the same tail classification.
    stale = _FakeLocked()
    stale.authority_row.trusted_sequence = 9
    stale.authority_row.trusted_event_hash = "3" * 64
    with pytest.raises(RiskControlError) as unexpected:
        _issue_with(_aggregate_bound_assessment(), stale)
    assert unexpected.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL

    # No aggregate binding at all (ordinary CANCEL / legacy) still passes.
    _gate, _locked, permit = _issue_with(_assessment())
    assert permit.request_id == "req_" + "2" * 32


# ---------------------------------------------------------------------------
# CORRECTION_08 — scope discriminator.  The C07 account-aggregate binding is
# mandatory ONLY through the dedicated R1-D07 N1 Strategy-1 Gate-D CREATE
# entrypoint `issue_strategy1_gate_d_create_permit`.  The shared generic
# `issue_permit` keeps predecessor semantics for an ABSENT binding, rejects a
# PARTIAL_OR_MALFORMED binding, and keeps Gate-B for a COMPLETE binding.
# ---------------------------------------------------------------------------


C08_ACTIVE_READ_SET_ID = "ADRS2_" + "4" * 64

C08_AGGREGATE_FIELDS = (
    "account_aggregate_snapshot_sha256",
    "account_aggregate_authority_trusted_sequence",
    "account_aggregate_authority_trusted_hash",
    "account_aggregate_ledger_terminal_sequence",
    "account_aggregate_ledger_terminal_hash",
    "account_aggregate_conflict_domain_ref",
    "account_aggregate_authority_namespace_id",
    "account_aggregate_authority_instance_id",
    "account_aggregate_ledger_instance_id",
    "account_aggregate_risk_config_sha256",
    "account_aggregate_trusted_dynamic_read_set_id",
    "account_aggregate_reconciliation_snapshot_sha256",
)


def _c08_active_assessment(
    *, operation_kind: str = "CREATE_ORDER_V2", aggregate: bool = True, **overrides,
) -> WriterEligibilityAssessment:
    """An active (ADRS2) Strategy-1 assessment matching `_FakeLocked`, with a
    COMPLETE exact aggregate binding when ``aggregate`` is true and an ABSENT
    one otherwise.  Each keyword substitutes exactly one field."""

    values: dict[str, object] = dict(
        domain_binding_id="db_c08", domain_binding_sha256="5" * 64,
        active_contract_id="ac_c08", active_contract_sha256="6" * 64,
        bootstrap_contract_sha256="8" * 64, conflict_domain_ref=FAKE_CONFLICT_DOMAIN_REF,
        account_scope_ref="acct_c08", subaccount=1, exchange_index=0,
        environment="KALSHI_DEMO", incident_id="inc_c08", writer_proof_id="wp_c08",
        trusted_dynamic_read_set_id=C08_ACTIVE_READ_SET_ID,
    )
    if aggregate:
        values.update(
            account_aggregate_snapshot_sha256=AGG_PERMIT_SNAPSHOT_SHA,
            account_aggregate_authority_trusted_sequence=10,
            account_aggregate_authority_trusted_hash="1" * 64,
            account_aggregate_ledger_terminal_sequence=10,
            account_aggregate_ledger_terminal_hash="1" * 64,
            account_aggregate_conflict_domain_ref=FAKE_CONFLICT_DOMAIN_REF,
            account_aggregate_authority_namespace_id=FAKE_AUTHORITY_NAMESPACE_ID,
            account_aggregate_authority_instance_id=FAKE_AUTHORITY_INSTANCE_ID,
            account_aggregate_ledger_instance_id=FAKE_LEDGER_INSTANCE_ID,
            account_aggregate_risk_config_sha256="c" * 64,
            account_aggregate_trusted_dynamic_read_set_id=C08_ACTIVE_READ_SET_ID,
            account_aggregate_reconciliation_snapshot_sha256="f" * 64,
        )
    values.update(overrides)
    eligible = values.pop("eligible", True)
    return WriterEligibilityAssessment(
        "ra_" + "1" * 32, operation_kind, "req_" + "2" * 32,
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64,
        "f" * 64, "0" * 64, 7, 2_000_000_000, eligible,
        **values,
    )


def _c08_issue(entrypoint: str, assessment: WriterEligibilityAssessment, locked=None):
    """Issue through exactly one named public entrypoint of a fresh gate."""

    gate = WriterEligibilityGate(
        monotonic_clock_ns=lambda: 1_000_000_000,
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = locked if locked is not None else _FakeLocked()
    permit = getattr(gate, entrypoint)(
        locked=locked, normal_writer_session_id="ws_" + "1" * 32, assessment=assessment,
        intent_payload={
            "execution_attempt_id": "ea_" + "3" * 32,
            "intent_payload": {"request_id": "req_" + "2" * 32},
        },
        prepared_payload={
            "request_id": "req_" + "2" * 32,
            "operation_name": assessment.operation_kind,
            "prepared_request_sha256": "a" * 64,
        },
    )
    return gate, locked, permit


def _c08_assert_rejected_pre_permit(entrypoint: str, assessment, code, locked=None) -> None:
    """Rejected before permit construction: exact code, nothing appended,
    and the gate owns no outstanding permit (so no T1/T2/T3 and no transport
    can follow)."""

    gate = WriterEligibilityGate(
        monotonic_clock_ns=lambda: 1_000_000_000,
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = locked if locked is not None else _FakeLocked()
    before = len(locked.events)
    with pytest.raises(RiskControlError) as excinfo:
        getattr(gate, entrypoint)(
            locked=locked, normal_writer_session_id="ws_" + "1" * 32, assessment=assessment,
            intent_payload={
                "execution_attempt_id": "ea_" + "3" * 32,
                "intent_payload": {"request_id": "req_" + "2" * 32},
            },
            prepared_payload={
                "request_id": "req_" + "2" * 32,
                "operation_name": assessment.operation_kind,
                "prepared_request_sha256": "a" * 64,
            },
        )
    assert excinfo.value.code is code
    assert len(locked.events) == before
    assert gate.outstanding_permit_count == 0


def test_c08_rc_00_two_distinct_public_entrypoints_without_scope_flag() -> None:
    """C08-SCOPE-002/003: two distinct callable entrypoints exist, and
    neither public signature accepts a caller-selectable scope/mode/flag."""

    import inspect

    generic = WriterEligibilityGate.issue_permit
    scoped = WriterEligibilityGate.issue_strategy1_gate_d_create_permit
    assert callable(generic) and callable(scoped) and generic is not scoped
    expected = ["self", "locked", "normal_writer_session_id", "assessment", "intent_payload", "prepared_payload"]
    assert list(inspect.signature(generic).parameters) == expected
    assert list(inspect.signature(scoped).parameters) == expected
    assert "aggregate_gate" not in inspect.signature(generic).parameters
    # C08-DEF-003: the scope is not an assessment field either.
    assert not {f.name for f in _rc_fields(WriterEligibilityAssessment)} & {
        "scope", "mode", "is_c07", "require_aggregate",
    }


def test_c08_rc_01_generic_create_with_absent_aggregate_keeps_predecessor_behavior() -> None:
    """C08-RC-01 / C08-GEN-001/002 / C08-FAIL-006: a genuine CREATE_ORDER_V2
    with an ABSENT aggregate binding is not rejected by aggregate absence on
    the generic entrypoint -- legacy and active predecessor callers alike --
    so `operation_kind` alone never selects C07 scope.  The predecessor gates
    still decide the outcome."""

    for assessment in (_assessment(), _c08_active_assessment(aggregate=False)):
        assert assessment.operation_kind == "CREATE_ORDER_V2"
        assert all(getattr(assessment, name) is None for name in C08_AGGREGATE_FIELDS)
        gate, locked, permit = _c08_issue("issue_permit", assessment)
        assert type(permit) is NormalWriterPermit
        assert permit.operation_kind == "CREATE_ORDER_V2"
        assert gate.progress_snapshot(permit)["stage"] is PermitStage.INTENT

    # Predecessor gates still control: an ineligible ABSENT assessment and a
    # latched hard HALT are both still rejected with predecessor semantics.
    _c08_assert_rejected_pre_permit(
        "issue_permit", _c08_active_assessment(aggregate=False, eligible=False),
        RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
    )
    halted = WriterEligibilityGate(
        monotonic_clock_ns=lambda: 1_000_000_000,
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    halted.latch_hard_halt()
    with pytest.raises(RiskControlError) as excinfo:
        halted.issue_permit(
            locked=_FakeLocked(), normal_writer_session_id="ws_" + "1" * 32, assessment=_assessment(),
            intent_payload={"execution_attempt_id": "ea_" + "3" * 32,
                            "intent_payload": {"request_id": "req_" + "2" * 32}},
            prepared_payload={"request_id": "req_" + "2" * 32, "operation_name": "CREATE_ORDER_V2",
                              "prepared_request_sha256": "a" * 64},
        )
    assert excinfo.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID


def test_c08_rc_02_scoped_create_with_absent_aggregate_is_rejected_pre_permit() -> None:
    """C08-RC-02 / C08-SCOPED-002 / C08-FAIL-002: the dedicated Strategy-1
    Gate-D CREATE entrypoint rejects an ABSENT binding before permit
    construction -- no permit, no T1/T2/T3, no transport -- for both an active
    and a legacy (no read-set) assessment."""

    for assessment in (_c08_active_assessment(aggregate=False), _assessment()):
        _c08_assert_rejected_pre_permit(
            "issue_strategy1_gate_d_create_permit", assessment,
            RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
        )


def test_c08_rc_03_partial_or_malformed_aggregate_is_rejected_on_both_entrypoints() -> None:
    """C08-RC-03 / C08-GEN-003 / C08-SCOPED-002: parameterized over every
    aggregate binding field -- dropping any single field from a COMPLETE
    binding, or supplying any single field alone, is PARTIAL and never
    treated as ABSENT.  Malformed snapshot / read-set identities reject."""

    complete = _c08_active_assessment()
    for entrypoint in ("issue_permit", "issue_strategy1_gate_d_create_permit"):
        for name in C08_AGGREGATE_FIELDS:
            _c08_assert_rejected_pre_permit(
                entrypoint, _c08_active_assessment(**{name: None}),
                RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
            )
            lone = _c08_active_assessment(aggregate=False, **{name: getattr(complete, name)})
            _c08_assert_rejected_pre_permit(entrypoint, lone, RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
        for name, malformed in (
            ("account_aggregate_snapshot_sha256", "not-a-sha"),
            ("account_aggregate_snapshot_sha256", "A" * 64),
            ("account_aggregate_trusted_dynamic_read_set_id", "ADRS2_" + "4" * 63),
            ("account_aggregate_trusted_dynamic_read_set_id", "ADRS1_" + "4" * 64),
        ):
            _c08_assert_rejected_pre_permit(
                entrypoint, _c08_active_assessment(**{name: malformed}),
                RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
            )

    # Scoped only: a well-formed but NON-active read-set identity (legacy
    # None, or uppercase-hex ADRS2) is not the active ADRS2 identity.
    for read_set in (None, "ADRS2_" + "A" * 64):
        _c08_assert_rejected_pre_permit(
            "issue_strategy1_gate_d_create_permit",
            _c08_active_assessment(account_aggregate_trusted_dynamic_read_set_id=read_set),
            RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
        )
    # Scoped only: a legacy COMPLETE binding (no active read-set at all).
    _c08_assert_rejected_pre_permit(
        "issue_strategy1_gate_d_create_permit", _aggregate_bound_assessment(),
        RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
    )


def test_c08_rc_04_scoped_create_with_complete_exact_aggregate_reaches_shared_mechanics() -> None:
    """C08-RC-04 / C08-SCOPED-004/005/007: a COMPLETE exact binding passes
    Gate B and yields the SAME `NormalWriterPermit` type, driven through the
    SAME T0 -> T1 -> T2 -> T3 stage machine and adapter as a generic permit."""

    clock_values = iter((1_000_000_000, 1_000_000_001, 1_000_000_002, 1_000_000_003))
    gate = WriterEligibilityGate(
        monotonic_clock_ns=lambda: next(clock_values),
        wall_clock=lambda: datetime(2026, 8, 13, 20, tzinfo=timezone.utc),
        uuid_factory=_uuid_factory(),
    )
    locked = _FakeLocked()
    assessment = _c08_active_assessment()
    permit = gate.issue_strategy1_gate_d_create_permit(
        locked=locked, normal_writer_session_id="ws_" + "1" * 32, assessment=assessment,
        intent_payload={"execution_attempt_id": "ea_" + "3" * 32,
                        "intent_payload": {"request_id": "req_" + "2" * 32}},
        prepared_payload={"request_id": "req_" + "2" * 32, "operation_name": "CREATE_ORDER_V2",
                          "prepared_request_sha256": "a" * 64},
    )
    assert type(permit) is NormalWriterPermit
    assert permit.operation_kind == "CREATE_ORDER_V2"
    assert permit.trusted_dynamic_read_set_id == C08_ACTIVE_READ_SET_ID
    assert permit.permit_domain_commitment_sha256 is not None
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

    # The same exact assessment through the generic entrypoint yields a
    # permit with the identical field set (one permit type, one mechanism).
    _g, _l, generic_permit = _c08_issue("issue_permit", assessment)
    assert type(generic_permit) is type(permit)
    for name in ("operation_kind", "request_id", "candidate_request_sha256", "candidate_economic_sha256",
                 "risk_config_sha256", "trusted_dynamic_read_set_id", "permit_domain_commitment_sha256",
                 "initial_trusted_sequence", "initial_trusted_hash"):
        assert getattr(generic_permit, name) == getattr(permit, name), name

    # Predecessor gates still control the scoped path too.
    _c08_assert_rejected_pre_permit(
        "issue_strategy1_gate_d_create_permit", _c08_active_assessment(eligible=False),
        RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
    )


def test_c08_rc_05_scoped_entrypoint_rejects_every_non_create_operation() -> None:
    """C08-RC-05 / C08-SCOPED-001 / C08-FAIL-001: the scoped entrypoint
    rejects any non-CREATE operation before permit construction -- even with
    a complete exact aggregate binding -- while the ordinary generic CANCEL
    path stays valid under predecessor semantics (C08-RUN-006)."""

    for operation_kind in ("CANCEL_ORDER_V2", "create_order_v2", "CREATE_ORDER_V1", ""):
        for aggregate in (True, False):
            _c08_assert_rejected_pre_permit(
                "issue_strategy1_gate_d_create_permit",
                _c08_active_assessment(operation_kind=operation_kind, aggregate=aggregate),
                RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
            )
    # A non-assessment object is equally rejected before construction.
    with pytest.raises(RiskControlError) as excinfo:
        _c08_issue("issue_strategy1_gate_d_create_permit", SimpleNamespace(operation_kind="CREATE_ORDER_V2"))
    assert excinfo.value.code is RiskControlCode.NORMAL_WRITER_PERMIT_INVALID

    _gate, _locked, cancel_permit = _c08_issue(
        "issue_permit", _c08_active_assessment(operation_kind="CANCEL_ORDER_V2", aggregate=False),
    )
    assert cancel_permit.operation_kind == "CANCEL_ORDER_V2"


def test_c08_rc_06_generic_complete_aggregate_keeps_gate_b_anti_substitution() -> None:
    """C08-RC-06 / C08-GEN-004/005 / C08-FAIL-003/004: when a COMPLETE
    binding reaches the generic entrypoint, every C01 Gate-B equality stays
    active.  The exact binding passes; every single wrong identity rejects
    with NORMAL_WRITER_PERMIT_INVALID; a moved authority/ledger tail rejects
    with NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL.  The scoped entrypoint applies
    the identical Gate-B checks."""

    wrong_identities = (
        ("account_aggregate_conflict_domain_ref", "kalshi-demo:portfolio:99"),
        ("account_aggregate_authority_namespace_id", "foreign-authority-namespace"),
        ("account_aggregate_authority_instance_id", "foreign-authority-instance"),
        ("account_aggregate_ledger_instance_id", "foreign-ledger-instance"),
        ("account_aggregate_risk_config_sha256", "0" * 64),
        ("account_aggregate_trusted_dynamic_read_set_id", "ADRS2_" + "b" * 64),
        ("account_aggregate_reconciliation_snapshot_sha256", "9" * 64),
    )
    for entrypoint in ("issue_permit", "issue_strategy1_gate_d_create_permit"):
        _gate, _locked, permit = _c08_issue(entrypoint, _c08_active_assessment())
        assert type(permit) is NormalWriterPermit
        for name, foreign in wrong_identities:
            _c08_assert_rejected_pre_permit(
                entrypoint, _c08_active_assessment(**{name: foreign}),
                RiskControlCode.NORMAL_WRITER_PERMIT_INVALID,
            )
        # Tail movement: live tail advanced past the aggregate-bound tail,
        # and an authority row that has not caught up to the terminal event.
        moved = _FakeLocked()
        moved.events.append(SimpleNamespace(sequence=11, event_hash="2" * 64))
        moved.authority_row.trusted_sequence = 11
        moved.authority_row.trusted_event_hash = "2" * 64
        _c08_assert_rejected_pre_permit(
            entrypoint, _c08_active_assessment(), RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL, moved,
        )
        stale = _FakeLocked()
        stale.authority_row.trusted_sequence = 9
        stale.authority_row.trusted_event_hash = "3" * 64
        _c08_assert_rejected_pre_permit(
            entrypoint, _c08_active_assessment(), RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL, stale,
        )
        for name, value in (
            ("account_aggregate_authority_trusted_sequence", 9),
            ("account_aggregate_authority_trusted_hash", "3" * 64),
            ("account_aggregate_ledger_terminal_sequence", 9),
            ("account_aggregate_ledger_terminal_hash", "3" * 64),
        ):
            _c08_assert_rejected_pre_permit(
                entrypoint, _c08_active_assessment(**{name: value}),
                RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL,
            )

    # The legacy (no read-set) COMPLETE binding keeps its generic Gate-B
    # acceptance (C01 seed semantics are unchanged on the generic path).
    _gate, _locked, legacy_permit = _c08_issue("issue_permit", _aggregate_bound_assessment())
    assert legacy_permit.trusted_dynamic_read_set_id is None
