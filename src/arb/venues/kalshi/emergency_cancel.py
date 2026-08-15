"""Exact-target, single-order emergency cancellation primitives.

The module contains no HTTP client and never loads credentials.  A caller may
inject only the single-order transport callable accepted by
``EmergencyCancelAdapter`` after persistent intent and send-boundary anchoring.
"""

from __future__ import annotations

import enum
import re
import threading
import uuid
from collections import deque
from dataclasses import dataclass, fields
from decimal import Decimal
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence

from arb.execution_ledger import canonical_json_bytes, canonical_timestamp, sha256_hex
from arb.venues.kalshi.ledger_binding import EmergencyControlLedgerHandle


CANCEL_SOURCE_BINDING_ID = "KSR-02_CANCEL_ORDER_V2_2026-08-13T20:18:41Z"
CANCEL_PATH_PREFIX = "/trade-api/v2/portfolio/events/orders/"
_ID_PATTERNS = {
    "action": re.compile(r"^ea_[0-9a-f]{32}$"),
    "attempt": re.compile(r"^ca_[0-9a-f]{32}$"),
    "request": re.compile(r"^req_[0-9a-f]{32}$"),
    "deadline": re.compile(r"^dl_[0-9a-f]{32}$"),
    "process": re.compile(r"^proc_[0-9a-f]{32}$"),
}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class EmergencyCancelCode(enum.StrEnum):
    EMERGENCY_TARGET_NOT_AUTHORITATIVE = "EMERGENCY_TARGET_NOT_AUTHORITATIVE"
    EMERGENCY_TARGET_NOT_ACTIVE = "EMERGENCY_TARGET_NOT_ACTIVE"
    EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE = "EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE"
    EMERGENCY_CANCEL_PERMIT_INVALID = "EMERGENCY_CANCEL_PERMIT_INVALID"
    EMERGENCY_CANCEL_PERMIT_CONSUMED = "EMERGENCY_CANCEL_PERMIT_CONSUMED"
    CANCEL_RESULT_EVIDENCE_CONFLICT = "CANCEL_RESULT_EVIDENCE_CONFLICT"
    CANCEL_UNRESOLVED = "CANCEL_UNRESOLVED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"


class EmergencyCancelError(RuntimeError):
    def __init__(self, code: EmergencyCancelCode) -> None:
        self.code = code
        super().__init__(code.value)


def _mint_uuid4(prefix: str, uuid_factory: Callable[[], uuid.UUID]) -> str:
    value = uuid_factory()
    if type(value) is not uuid.UUID or value.version != 4 or value.variant != uuid.RFC_4122:
        raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)
    return prefix + value.hex


@dataclass(frozen=True, slots=True)
class EmergencyActionId:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _ID_PATTERNS["action"].fullmatch(self.value) is None:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)

    @classmethod
    def mint(cls, uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4) -> "EmergencyActionId":
        return cls(_mint_uuid4("ea_", uuid_factory))


@dataclass(frozen=True, slots=True)
class CancelAttemptId:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _ID_PATTERNS["attempt"].fullmatch(self.value) is None:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)

    @classmethod
    def mint(cls, uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4) -> "CancelAttemptId":
        return cls(_mint_uuid4("ca_", uuid_factory))


@dataclass(frozen=True, slots=True)
class EmergencyCancelPreparedRequestV1:
    request_id: str
    target_order_id: str
    source_binding_id: str = CANCEL_SOURCE_BINDING_ID

    def __post_init__(self) -> None:
        if type(self.request_id) is not str or _ID_PATTERNS["request"].fullmatch(self.request_id) is None or type(self.target_order_id) is not str or not self.target_order_id or self.target_order_id != self.target_order_id.strip() or self.source_binding_id != CANCEL_SOURCE_BINDING_ID:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)

    @property
    def path_without_query(self) -> str:
        return CANCEL_PATH_PREFIX + self.target_order_id

    @property
    def canonical_object(self) -> Mapping[str, object]:
        return MappingProxyType({
            "request_schema_id": "KALSHI_EMERGENCY_CANCEL_PREPARED_REQUEST_V1",
            "request_id": self.request_id,
            "operation_name": "CANCEL_ORDER_V2",
            "method": "DELETE",
            "path_without_query": self.path_without_query,
            "canonical_query": {},
            "canonical_body": None,
            "target_order_id": self.target_order_id,
            "source_binding_id": self.source_binding_id,
        })

    @property
    def canonical_request_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(dict(self.canonical_object)))


@dataclass(frozen=True, slots=True)
class AuthoritativeCancelTargetV1:
    order_id: str
    conflict_domain_ref: str
    subaccount: int
    exchange_index: int
    observation_event_id: str
    observation_event_hash: str
    remaining_quantity: Decimal
    status: str

    def __post_init__(self) -> None:
        if type(self.order_id) is not str or not self.order_id or self.order_id != self.order_id.strip() or type(self.conflict_domain_ref) is not str or not self.conflict_domain_ref:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_TARGET_NOT_AUTHORITATIVE)
        if type(self.subaccount) is not int or not 0 <= self.subaccount <= 63 or type(self.exchange_index) is not int or self.exchange_index < 0:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_TARGET_NOT_AUTHORITATIVE)
        if type(self.observation_event_id) is not str or not self.observation_event_id.startswith("evt_") or type(self.observation_event_hash) is not str or _HEX64_RE.fullmatch(self.observation_event_hash) is None:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_TARGET_NOT_AUTHORITATIVE)
        if type(self.remaining_quantity) is not Decimal or not self.remaining_quantity.is_finite() or self.remaining_quantity <= 0 or self.status != "resting":
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_TARGET_NOT_ACTIVE)


def authoritative_target_set(targets: Sequence[AuthoritativeCancelTargetV1]) -> tuple[AuthoritativeCancelTargetV1, ...]:
    by_id: dict[str, AuthoritativeCancelTargetV1] = {}
    for target in targets:
        if type(target) is not AuthoritativeCancelTargetV1:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_TARGET_NOT_AUTHORITATIVE)
        if target.order_id in by_id and by_id[target.order_id] != target:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_TARGET_NOT_AUTHORITATIVE)
        by_id[target.order_id] = target
    return tuple(by_id[key] for key in sorted(by_id))


@dataclass(frozen=True, slots=True)
class EmergencyRateConfigV1:
    max_sends: int
    window_ms: int
    max_in_flight: int
    request_deadline_ms: int
    retry_max_attempts_per_target_per_action: int
    backoff_base_ms: int
    backoff_max_ms: int

    def __post_init__(self) -> None:
        positive = (self.max_sends, self.window_ms, self.max_in_flight, self.request_deadline_ms, self.backoff_base_ms, self.backoff_max_ms)
        if any(type(value) is not int or value <= 0 for value in positive) or type(self.retry_max_attempts_per_target_per_action) is not int or self.retry_max_attempts_per_target_per_action < 0 or self.backoff_max_ms < self.backoff_base_ms:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE)


class EmergencyRateLane:
    """Distinct local bounded emergency capacity; never a venue reservation."""

    def __init__(self, config: EmergencyRateConfigV1) -> None:
        self.__config = config
        self.__send_times_ms: deque[int] = deque()
        self.__in_flight = 0
        self.__attempts: dict[tuple[str, str], int] = {}
        self.__mutex = threading.Lock()

    def reserve(self, action_id: str, target_order_id: str, now_ms: int) -> int:
        if type(now_ms) is not int or now_ms < 0:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE)
        with self.__mutex:
            lower = now_ms - self.__config.window_ms
            while self.__send_times_ms and self.__send_times_ms[0] <= lower:
                self.__send_times_ms.popleft()
            key = (action_id, target_order_id)
            attempt_index = self.__attempts.get(key, 0)
            maximum_total = 1 + self.__config.retry_max_attempts_per_target_per_action
            if len(self.__send_times_ms) + 1 > self.__config.max_sends or self.__in_flight + 1 > self.__config.max_in_flight or attempt_index >= maximum_total:
                raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE)
            self.__send_times_ms.append(now_ms)
            self.__in_flight += 1
            self.__attempts[key] = attempt_index + 1
            return attempt_index

    def release(self) -> None:
        with self.__mutex:
            if self.__in_flight <= 0:
                raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE)
            self.__in_flight -= 1

    def backoff_ms(self, zero_based_retry_index: int) -> int:
        if type(zero_based_retry_index) is not int or zero_based_retry_index < 0:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_CAPACITY_UNAVAILABLE)
        if zero_based_retry_index >= self.__config.backoff_max_ms.bit_length():
            return self.__config.backoff_max_ms
        return min(self.__config.backoff_max_ms, self.__config.backoff_base_ms * (1 << zero_based_retry_index))

    @property
    def in_flight(self) -> int:
        with self.__mutex:
            return self.__in_flight


_PERMIT_KEY = object()


@dataclass(frozen=True, slots=True, init=False)
class EmergencyCancelPermit:
    emergency_action_id: str
    cancel_attempt_id: str
    request_id: str
    target_order_id: str
    process_instance_id: str
    risk_state_epoch: int
    canonical_request_sha256: str
    authority_trusted_sequence: int
    authority_trusted_hash: str
    deadline_id: str
    deadline_absolute_monotonic_ns: int
    private_gate_identity: object

    def __init__(self, key: object, **values: object) -> None:
        if key is not _PERMIT_KEY:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def __copy__(self):
        raise TypeError("EmergencyCancelPermit cannot be copied")

    def __deepcopy__(self, memo):
        del memo
        raise TypeError("EmergencyCancelPermit cannot be deep-copied")

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("EmergencyCancelPermit cannot be serialized")


class EmergencyCancelGate:
    def __init__(
        self,
        *,
        handle: EmergencyControlLedgerHandle,
        rate_lane: EmergencyRateLane,
        process_instance_id: str,
        monotonic_clock_ns: Callable[[], int],
        wall_clock: Callable[[], object],
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        if type(handle) is not EmergencyControlLedgerHandle or type(rate_lane) is not EmergencyRateLane or type(process_instance_id) is not str or _ID_PATTERNS["process"].fullmatch(process_instance_id) is None:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)
        self.__handle = handle
        self.__lane = rate_lane
        self.__process = process_instance_id
        self.__monotonic = monotonic_clock_ns
        self.__wall = wall_clock
        self.__uuid = uuid_factory
        self.__identity = object()
        self.__states: dict[str, int] = {}
        self.__mutex = threading.Lock()

    @property
    def process_instance_id(self) -> str:
        return self.__process

    @property
    def outstanding_permit_count(self) -> int:
        """Return genuine unconsumed permit/action capacity held by this gate."""
        with self.__mutex:
            permits = sum(1 for state in self.__states.values() if state == 0)
        # A reserved emergency lane slot is itself outstanding emergency action
        # state even if a durable permit has not yet been returned to a caller.
        return max(permits, self.__lane.in_flight)

    def persist_intent_and_boundary(
        self,
        *,
        action_id: EmergencyActionId,
        target: AuthoritativeCancelTargetV1,
        risk_config_sha256: str | None,
        attempt_ordinal: int,
        deadline_budget_ms: int,
    ) -> tuple[EmergencyCancelPreparedRequestV1, EmergencyCancelPermit]:
        if type(action_id) is not EmergencyActionId or type(target) is not AuthoritativeCancelTargetV1 or type(attempt_ordinal) is not int or attempt_ordinal < 1 or type(deadline_budget_ms) is not int or deadline_budget_ms <= 0:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)
        projection = self.__handle.inspect_validated_projection()
        action = projection.emergency_actions_by_id.get(action_id.value)
        if action is None or target.order_id not in action["target_order_ids"]:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_TARGET_NOT_AUTHORITATIVE)
        start_ns = self.__monotonic()
        if type(start_ns) is not int or start_ns < 0:
            raise EmergencyCancelError(EmergencyCancelCode.DEADLINE_EXCEEDED)
        deadline_ns = start_ns + deadline_budget_ms * 1_000_000
        retry_index = self.__lane.reserve(action_id.value, target.order_id, start_ns // 1_000_000)
        attempt_id = CancelAttemptId.mint(self.__uuid)
        request_id = _mint_uuid4("req_", self.__uuid)
        deadline_id = _mint_uuid4("dl_", self.__uuid)
        timestamp = canonical_timestamp(self.__wall())
        intent_payload = {
            "emergency_action_id": action_id.value,
            "cancel_attempt_id": attempt_id.value,
            "target_order_id": target.order_id,
            "conflict_domain_ref": target.conflict_domain_ref,
            "subaccount": target.subaccount,
            "exchange_index": target.exchange_index,
            "source_binding_id": CANCEL_SOURCE_BINDING_ID,
            "risk_state_epoch": projection.risk_state_epoch,
            "risk_config_sha256": risk_config_sha256,
            "authoritative_order_observation_event_id": target.observation_event_id,
            "authoritative_order_observation_event_hash": target.observation_event_hash,
            "prior_order_status": "resting",
            "prior_remaining_count_fp": f"{target.remaining_quantity:.2f}",
            "attempt_ordinal": attempt_ordinal,
            "request_id": request_id,
            "intent_recorded_at_utc": timestamp,
        }
        try:
            intent = self.__handle.record_cancel_intent(intent_payload, recorded_at_utc=timestamp).events[-1]
            prepared = EmergencyCancelPreparedRequestV1(request_id, target.order_id)
            after_intent = self.__handle.inspect_validated_projection()
            boundary_time = canonical_timestamp(self.__wall())
            boundary_payload = {
                "emergency_action_id": action_id.value,
                "cancel_attempt_id": attempt_id.value,
                "target_order_id": target.order_id,
                "request_id": request_id,
                "canonical_request_sha256": prepared.canonical_request_sha256,
                "operation_name": "CANCEL_ORDER_V2",
                "method": "DELETE",
                "path_without_query": prepared.path_without_query,
                "attempt_ordinal": attempt_ordinal,
                "deadline_id": deadline_id,
                "deadline_budget_ms": deadline_budget_ms,
                "deadline_process_instance_id": self.__process,
                "deadline_started_monotonic_ns": start_ns,
                "deadline_absolute_monotonic_ns": deadline_ns,
                "predecessor_intent_event_id": intent.event_id,
                "predecessor_intent_event_hash": intent.event_hash,
                "predecessor_authority_trusted_sequence": after_intent.trusted_sequence,
                "predecessor_authority_trusted_hash": after_intent.trusted_event_hash,
                "predecessor_ledger_terminal_sequence": after_intent.last_sequence,
                "predecessor_ledger_terminal_hash": after_intent.terminal_event_hash,
                "write_ambiguity_rule": "CANCEL_MAY_HAVE_BEEN_SENT_AFTER_THIS_ANCHORED_EVENT",
                "boundary_recorded_at_utc": boundary_time,
            }
            self.__handle.record_cancel_send_boundary(boundary_payload, recorded_at_utc=boundary_time)
            after_boundary = self.__handle.inspect_validated_projection()
        except Exception:
            self.__lane.release()
            raise
        permit = EmergencyCancelPermit(_PERMIT_KEY,
            emergency_action_id=action_id.value, cancel_attempt_id=attempt_id.value,
            request_id=request_id, target_order_id=target.order_id,
            process_instance_id=self.__process, risk_state_epoch=after_boundary.risk_state_epoch,
            canonical_request_sha256=prepared.canonical_request_sha256,
            authority_trusted_sequence=after_boundary.trusted_sequence,
            authority_trusted_hash=after_boundary.trusted_event_hash,
            deadline_id=deadline_id, deadline_absolute_monotonic_ns=deadline_ns,
            private_gate_identity=self.__identity,
        )
        with self.__mutex:
            self.__states[attempt_id.value] = 0
        return prepared, permit

    def invoke(self, permit: EmergencyCancelPermit, prepared: EmergencyCancelPreparedRequestV1, transport: Callable[[EmergencyCancelPreparedRequestV1], object]) -> object:
        if type(permit) is not EmergencyCancelPermit or permit.private_gate_identity is not self.__identity or type(prepared) is not EmergencyCancelPreparedRequestV1 or prepared.request_id != permit.request_id or prepared.target_order_id != permit.target_order_id or prepared.canonical_request_sha256 != permit.canonical_request_sha256:
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)
        now = self.__monotonic()
        if now > permit.deadline_absolute_monotonic_ns:
            self.__lane.release()
            raise EmergencyCancelError(EmergencyCancelCode.DEADLINE_EXCEEDED)
        with self.__mutex:
            if self.__states.get(permit.cancel_attempt_id) != 0:
                raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_CONSUMED)
            self.__states[permit.cancel_attempt_id] = 1
        try:
            return transport(prepared)
        finally:
            self.__lane.release()


class EmergencyCancelAdapter:
    """Exact single-order DELETE adapter; exposes no batch or risk-increasing API."""

    __slots__ = ("__gate", "__transport")

    def __init__(self, gate: EmergencyCancelGate, transport: Callable[[EmergencyCancelPreparedRequestV1], object]) -> None:
        if type(gate) is not EmergencyCancelGate or not callable(transport):
            raise EmergencyCancelError(EmergencyCancelCode.EMERGENCY_CANCEL_PERMIT_INVALID)
        self.__gate = gate
        self.__transport = transport

    def cancel(self, permit: EmergencyCancelPermit, prepared: EmergencyCancelPreparedRequestV1) -> object:
        return self.__gate.invoke(permit, prepared, self.__transport)


class CancelResultClass(enum.StrEnum):
    CANCELED_CONFIRMED = "CANCELED_CONFIRMED"
    FILLED_BEFORE_CANCEL = "FILLED_BEFORE_CANCEL"
    PARTIAL_FILL_THEN_REMAINDER_CANCELED = "PARTIAL_FILL_THEN_REMAINDER_CANCELED"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"
    CANCEL_REJECTED_CONFIRMED = "CANCEL_REJECTED_CONFIRMED"
    CANCEL_UNRESOLVED = "CANCEL_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class CancelReconciliationEvidenceV1:
    prior_remaining: Decimal
    filled_quantity: Decimal
    canceled_quantity: Decimal | None
    remaining_quantity: Decimal | None
    terminal_canceled: bool
    terminal_other: bool
    definitive_rejection: bool
    authoritative_complete: bool


@dataclass(frozen=True, slots=True)
class CancelResultV1:
    result_class: CancelResultClass
    canceled_quantity: Decimal | None
    filled_quantity: Decimal
    remaining_quantity: Decimal | None
    unresolved: bool
    write_closure_class: str


def classify_cancel_result(evidence: CancelReconciliationEvidenceV1) -> CancelResultV1:
    if type(evidence) is not CancelReconciliationEvidenceV1:
        raise EmergencyCancelError(EmergencyCancelCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
    for value in (evidence.prior_remaining, evidence.filled_quantity):
        if type(value) is not Decimal or not value.is_finite() or value < 0:
            raise EmergencyCancelError(EmergencyCancelCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
    if not evidence.authoritative_complete or evidence.canceled_quantity is None or evidence.remaining_quantity is None:
        return CancelResultV1(CancelResultClass.CANCEL_UNRESOLVED, evidence.canceled_quantity, evidence.filled_quantity, evidence.remaining_quantity, True, "UNRESOLVED")
    canceled = evidence.canceled_quantity
    remaining = evidence.remaining_quantity
    if type(canceled) is not Decimal or type(remaining) is not Decimal or canceled < 0 or remaining < 0 or evidence.prior_remaining != evidence.filled_quantity + canceled + remaining:
        raise EmergencyCancelError(EmergencyCancelCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
    if evidence.filled_quantity == evidence.prior_remaining and canceled == 0 and remaining == 0:
        result = CancelResultClass.FILLED_BEFORE_CANCEL
    elif evidence.definitive_rejection and remaining > 0 and canceled == 0:
        result = CancelResultClass.CANCEL_REJECTED_CONFIRMED
    elif evidence.terminal_canceled and evidence.filled_quantity == 0 and canceled == evidence.prior_remaining and remaining == 0:
        result = CancelResultClass.CANCELED_CONFIRMED
    elif evidence.terminal_canceled and ZERO < evidence.filled_quantity < evidence.prior_remaining and remaining == 0:
        result = CancelResultClass.PARTIAL_FILL_THEN_REMAINDER_CANCELED
    elif evidence.terminal_other and remaining == 0:
        result = CancelResultClass.ALREADY_TERMINAL
    else:
        raise EmergencyCancelError(EmergencyCancelCode.CANCEL_RESULT_EVIDENCE_CONFLICT)
    return CancelResultV1(result, canceled, evidence.filled_quantity, remaining, False, "AUTHORITATIVE_RESULT_CLOSED")


ZERO = Decimal("0")
HISTORICAL_INCIDENT_CANCEL_TARGET = None


__all__ = [
    "AuthoritativeCancelTargetV1", "CANCEL_PATH_PREFIX", "CANCEL_SOURCE_BINDING_ID",
    "CancelAttemptId", "CancelReconciliationEvidenceV1", "CancelResultClass", "CancelResultV1",
    "EmergencyActionId", "EmergencyCancelAdapter", "EmergencyCancelCode", "EmergencyCancelError",
    "EmergencyCancelGate", "EmergencyCancelPermit", "EmergencyCancelPreparedRequestV1",
    "EmergencyRateConfigV1", "EmergencyRateLane", "HISTORICAL_INCIDENT_CANCEL_TARGET",
    "authoritative_target_set", "classify_cancel_result",
]
