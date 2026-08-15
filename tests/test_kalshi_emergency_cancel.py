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
