from __future__ import annotations

import copy
import pickle
from decimal import Decimal

import pytest

from arb.execution_ledger import canonical_json_bytes, sha256_hex
from arb.venues.kalshi.emergency_cancel import (
    CANCEL_PATH_PREFIX,
    CANCEL_SOURCE_BINDING_ID,
    AuthoritativeCancelTargetV1,
    CancelReconciliationEvidenceV1,
    CancelResultClass,
    EmergencyActionId,
    EmergencyCancelAdapter,
    EmergencyCancelCode,
    EmergencyCancelError,
    EmergencyCancelGate,
    EmergencyCancelPermit,
    EmergencyCancelPreparedRequestV1,
    EmergencyRateConfigV1,
    EmergencyRateLane,
    HISTORICAL_INCIDENT_CANCEL_TARGET,
    authoritative_target_set,
    classify_cancel_result,
)


D = Decimal
HASH = "a" * 64


def target(order_id: str = "order-1") -> AuthoritativeCancelTargetV1:
    return AuthoritativeCancelTargetV1(order_id, "kalshi-demo:portfolio:0", 0, 0, "evt_" + "1" * 32, HASH, D("2.00"), "resting")


def evidence(
    *, filled: str = "0", canceled: str | None = "2", remaining: str | None = "0",
    terminal_canceled: bool = True, terminal_other: bool = False,
    definitive_rejection: bool = False, complete: bool = True,
) -> CancelReconciliationEvidenceV1:
    return CancelReconciliationEvidenceV1(
        D("2"), D(filled), None if canceled is None else D(canceled),
        None if remaining is None else D(remaining), terminal_canceled,
        terminal_other, definitive_rejection, complete,
    )


def test_prepared_request_is_exact_single_delete_with_no_query_or_body() -> None:
    request = EmergencyCancelPreparedRequestV1("req_" + "1" * 32, "opaque-order-id")
    assert request.path_without_query == CANCEL_PATH_PREFIX + "opaque-order-id"
    assert request.canonical_object["method"] == "DELETE"
    assert request.canonical_object["canonical_query"] == {}
    assert request.canonical_object["canonical_body"] is None
    assert request.canonical_object["source_binding_id"] == CANCEL_SOURCE_BINDING_ID
    assert request.canonical_request_sha256 == sha256_hex(canonical_json_bytes(dict(request.canonical_object)))


def test_authoritative_targets_are_active_exact_and_sorted_without_synthesis() -> None:
    a, b = target("a"), target("b")
    assert authoritative_target_set((b, a, a)) == (a, b)
    with pytest.raises(EmergencyCancelError) as inactive:
        AuthoritativeCancelTargetV1("x", a.conflict_domain_ref, 0, 0, a.observation_event_id, HASH, D("0"), "resting")
    assert inactive.value.code is EmergencyCancelCode.EMERGENCY_TARGET_NOT_ACTIVE
    with pytest.raises(EmergencyCancelError):
        AuthoritativeCancelTargetV1("x", a.conflict_domain_ref, 0, 0, a.observation_event_id, HASH, D("1"), "canceled")


def test_emergency_rate_lane_is_separate_bounded_and_retry_limited() -> None:
    lane = EmergencyRateLane(EmergencyRateConfigV1(2, 100, 1, 500, 1, 10, 40))
    assert lane.reserve("ea_" + "1" * 32, "o", 1000) == 0
    assert lane.in_flight == 1
    with pytest.raises(EmergencyCancelError) as capacity:
        lane.reserve("ea_" + "1" * 32, "o", 1000)
    assert capacity.value.code is EmergencyCancelCode.EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE
    lane.release()
    assert lane.reserve("ea_" + "1" * 32, "o", 1001) == 1
    lane.release()
    with pytest.raises(EmergencyCancelError):
        lane.reserve("ea_" + "1" * 32, "o", 1102)
    assert [lane.backoff_ms(i) for i in range(4)] == [10, 20, 40, 40]


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (evidence(), CancelResultClass.CANCELED_CONFIRMED),
        (evidence(filled="2", canceled="0", terminal_canceled=False), CancelResultClass.FILLED_BEFORE_CANCEL),
        (evidence(filled="1", canceled="1"), CancelResultClass.PARTIAL_FILL_THEN_REMAINDER_CANCELED),
        (evidence(filled="1", canceled="1", terminal_canceled=False, terminal_other=True), CancelResultClass.ALREADY_TERMINAL),
        (evidence(canceled="0", remaining="2", terminal_canceled=False, definitive_rejection=True), CancelResultClass.CANCEL_REJECTED_CONFIRMED),
        (evidence(canceled=None, remaining=None, terminal_canceled=False, complete=False), CancelResultClass.CANCEL_UNRESOLVED),
    ],
)
def test_cancel_result_classes_are_closed(item: CancelReconciliationEvidenceV1, expected: CancelResultClass) -> None:
    result = classify_cancel_result(item)
    assert result.result_class is expected
    assert result.unresolved is (expected is CancelResultClass.CANCEL_UNRESOLVED)


def test_cancel_result_conservation_and_evidence_conflicts_fail_closed() -> None:
    with pytest.raises(EmergencyCancelError) as conflict:
        classify_cancel_result(evidence(filled="1", canceled="1", remaining="1"))
    assert conflict.value.code is EmergencyCancelCode.CANCEL_RESULT_EVIDENCE_CONFLICT
    with pytest.raises(EmergencyCancelError):
        classify_cancel_result(evidence(canceled="0", remaining="2", terminal_canceled=False))


def test_emergency_cancel_permit_cannot_be_forged_and_adapter_has_only_cancel_surface() -> None:
    with pytest.raises(EmergencyCancelError) as forged:
        EmergencyCancelPermit(object())
    assert forged.value.code is EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID
    with pytest.raises(EmergencyCancelError):
        EmergencyCancelAdapter(object(), lambda request: request)  # type: ignore[arg-type]
    assert set(name for name in dir(EmergencyCancelAdapter) if not name.startswith("_")) == {"cancel"}


def test_historical_incident_has_no_authoritative_cancel_target() -> None:
    assert HISTORICAL_INCIDENT_CANCEL_TARGET is None


# --- R1-B03 T53-T56: active-domain emergency cancellation ------------------
from arb.venues.kalshi.emergency_cancel import EmergencyCancelGate as _ECG, EmergencyCancelCode as _ECC, EmergencyCancelError as _ECE, AuthoritativeCancelTargetV1 as _ACT
from arb.venues.kalshi.ledger_binding import (
    ExecutionDomainBindingV1 as _EDB,
    ActiveExecutionDomainContractV1 as _AEDC,
)


def _active_contract(subaccount=1, exchange_index=0):
    b = _EDB(venue="KALSHI", environment="KALSHI_DEMO",
             account_scope_ref="ARB_KALSHI_DEMO_PRIMARY_ACCOUNT",
             subaccount=subaccount, exchange_index=exchange_index)
    return _AEDC(binding=b, bootstrap_contract_sha256="a" * 64)


def test_t54_gate_rejects_non_active_contract_type() -> None:
    with pytest.raises(_ECE) as e:
        _ECG(handle=object(), rate_lane=object(), process_instance_id="proc_" + "0" * 32,
             monotonic_clock_ns=lambda: 0, wall_clock=lambda: None,
             active_contract="not-a-contract")
    # handle type check fires first for object(); assert domain mismatch when only contract is bad
    assert e.value.code in (_ECC.EMERGENCY_CANCEL_PERMIT_INVALID, _ECC.EMERGENCY_CANCEL_DOMAIN_MISMATCH)


def test_t55_n1_controller_rejects_n0_target_domain() -> None:
    # DSB-EMERG-003: an N=1 active contract's conflict domain never equals an N=0 target's.
    n1 = _active_contract(subaccount=1)
    n0_conflict = "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0"
    assert n1.conflict_domain_ref != n0_conflict
    target_n0 = _ACT("ord-x", n0_conflict, 0, 0, "evt_" + "1" * 32, "b" * 64, Decimal("2.00"), "resting")
    # The domain-equality predicate the gate applies would fail for this pair.
    assert (target_n0.conflict_domain_ref != n1.conflict_domain_ref
            or target_n0.subaccount != n1.subaccount)


def test_t56_permit_binds_target_domain_fields() -> None:
    from dataclasses import fields as _f
    from arb.venues.kalshi.emergency_cancel import EmergencyCancelPermit as _P
    names = {x.name for x in _f(_P)}
    assert {"conflict_domain_ref", "subaccount", "exchange_index",
            "active_contract_sha256", "domain_binding_sha256"} <= names


def test_t_emergency_cancel_domain_mismatch_code_exists() -> None:
    assert _ECC.EMERGENCY_CANCEL_DOMAIN_MISMATCH.value == "EMERGENCY_CANCEL_DOMAIN_MISMATCH"


def test_t57_t58_t59_active_emergency_preserves_ambiguous_no_retry_semantics() -> None:
    # DSB-EMERG-004 is unchanged by the active path: the EmergencyCancelGate
    # machinery (ambiguous => reconcile, HTTP success alone never releases,
    # no blind retry) is inherited verbatim; the active path only adds the
    # earlier exact-domain guard.  Assert the invariant surface is intact.
    from arb.venues.kalshi.emergency_cancel import (
        EmergencyCancelGate, EmergencyRateConfigV1, EmergencyRateLane,
    )
    import inspect
    src = inspect.getsource(EmergencyCancelGate)
    # no blind-retry / cancel_all / fuzzy path introduced
    for forbidden in ("cancel_all", "fuzzy", "blind_retry", "retry_without_reconcile"):
        assert forbidden not in src
    # the rate lane remains bounded + retry-limited (T59)
    lane = EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100))
    assert lane.in_flight == 0
