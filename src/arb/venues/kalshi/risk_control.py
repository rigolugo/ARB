"""Fail-closed persistent risk controls for the Kalshi Demo execution spine.

This module is deliberately transport-agnostic except for the one narrow
``NormalWriteAdapter`` capability wrapper at the bottom.  It performs no
network, credential, signing, filesystem, or environment access.
"""

from __future__ import annotations

import copy
import enum
import re
import threading
import unicodedata
import uuid
from collections import deque
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence

from arb.execution_ledger import (
    EventInput,
    EventType,
    FailureCode,
    LedgerError,
    LockedLedger,
    canonical_json_bytes,
    canonical_timestamp,
    deterministic_event_id,
    end_writer_session,
    sha256_hex,
    validate_canonical_timestamp,
)


ONE = Decimal("1.0000")
ZERO = Decimal("0")
UNKNOWN_UNBOUNDED = "UNKNOWN_UNBOUNDED"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RES = {
    "permit": re.compile(r"^nwp_[0-9a-f]{32}$"),
    "assessment": re.compile(r"^ra_[0-9a-f]{32}$"),
    "process": re.compile(r"^proc_[0-9a-f]{32}$"),
    "request": re.compile(r"^req_[0-9a-f]{32}$"),
    "session": re.compile(r"^ws_[0-9a-f]{32}$"),
    "event": re.compile(r"^evt_[0-9a-f]{32}$"),
}


class RiskControlCode(enum.StrEnum):
    RISK_LIMIT_CONFIG_MISSING = "RISK_LIMIT_CONFIG_MISSING"
    RISK_LIMIT_CONFIG_INVALID = "RISK_LIMIT_CONFIG_INVALID"
    RISK_NUMERIC_RANGE_UNSUPPORTED = "RISK_NUMERIC_RANGE_UNSUPPORTED"
    RISK_INPUT_UNAVAILABLE = "RISK_INPUT_UNAVAILABLE"
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
    MARKET_DATA_UNUSABLE = "MARKET_DATA_UNUSABLE"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    RECONCILIATION_STALE = "RECONCILIATION_STALE"
    CLOCK_REGRESSION = "CLOCK_REGRESSION"
    UNKNOWN_UNBOUNDED_EXPOSURE = "UNKNOWN_UNBOUNDED_EXPOSURE"
    NORMAL_WRITER_PERMIT_INVALID = "NORMAL_WRITER_PERMIT_INVALID"
    NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL = "NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL"
    NORMAL_WRITER_PERMIT_STAGE_MISMATCH = "NORMAL_WRITER_PERMIT_STAGE_MISMATCH"
    NORMAL_WRITER_PERMIT_EXPIRED = "NORMAL_WRITER_PERMIT_EXPIRED"
    NORMAL_WRITER_PERMIT_ALREADY_CONSUMED = "NORMAL_WRITER_PERMIT_ALREADY_CONSUMED"
    HALT_PERSISTENCE_FAILED = "HALT_PERSISTENCE_FAILED"


class RiskControlError(RuntimeError):
    def __init__(self, code: RiskControlCode) -> None:
        self.code = code
        super().__init__(code.value)


def _require_exact_bool(value: object) -> bool:
    if type(value) is not bool:
        raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
    return value


def _require_int(value: object, *, minimum: int = 0, positive: bool = False) -> int:
    if type(value) is not int or value < minimum or (positive and value == 0):
        raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
    return value


def _require_decimal(value: object, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
    if positive and value <= 0:
        raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
    if nonnegative and value < 0:
        raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
    return value


def _config_mapping(value: object) -> Mapping[str, object]:
    if not hasattr(value, "__dataclass_fields__"):
        raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
    return {field.name: _config_mapping(item) if hasattr(item, "__dataclass_fields__") else item for field in fields(value) for item in (getattr(value, field.name),)}


@dataclass(frozen=True, slots=True)
class PerOrderRiskLimits:
    max_contracts: Decimal
    max_worst_case_exposure_usd: Decimal
    price_reasonability_required: bool
    max_abs_reference_price_deviation_usd: Decimal
    max_market_data_age_ms: int


@dataclass(frozen=True, slots=True)
class PerMarketRiskLimits:
    max_abs_net_position_contracts: Decimal
    max_gross_exposure_usd: Decimal
    max_authoritative_working_orders: int
    max_working_contracts: Decimal
    max_working_order_exposure_usd: Decimal


@dataclass(frozen=True, slots=True)
class AccountRiskLimits:
    max_aggregate_exposure_usd: Decimal
    max_aggregate_working_orders: int
    max_aggregate_working_contracts: Decimal
    max_unresolved_write_count: int
    max_conservative_unresolved_write_exposure_usd: Decimal


@dataclass(frozen=True, slots=True)
class FlowRiskLimits:
    create_max_sends: int
    create_window_ms: int
    modify_replace_max_sends: int
    modify_replace_window_ms: int
    ordinary_cancel_max_sends: int
    ordinary_cancel_window_ms: int
    automated_execution_max_sends: int
    automated_execution_window_ms: int
    emergency_cancel_max_sends: int
    emergency_cancel_window_ms: int
    emergency_cancel_max_in_flight: int
    emergency_cancel_request_deadline_ms: int
    emergency_retry_max_attempts_per_target_per_action: int
    emergency_backoff_base_ms: int
    emergency_backoff_max_ms: int


@dataclass(frozen=True, slots=True)
class StateIntegrityLimits:
    max_reconciliation_lag_ms: int
    max_required_market_data_age_ms: int
    max_future_wall_clock_skew_ms: int
    max_reconciliation_attempts_per_cycle: int
    reconciliation_read_deadline_ms: int
    reconciliation_backoff_base_ms: int
    reconciliation_backoff_max_ms: int


@dataclass(frozen=True, slots=True)
class VenueDefensePolicy:
    order_group_mode: str
    required_order_group_id: str | None
    cancel_order_on_pause_required: bool
    reduce_only_policy: str
    post_only_policy: str


@dataclass(frozen=True, slots=True)
class RiskLimitConfigV1:
    schema_version: int
    conflict_domain: str
    currency: str
    per_order: PerOrderRiskLimits
    per_market: PerMarketRiskLimits
    conflict_domain_account: AccountRiskLimits
    flow: FlowRiskLimits
    state_integrity: StateIntegrityLimits
    venue_defense: VenueDefensePolicy

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1 or type(self.conflict_domain) is not str or not self.conflict_domain or self.currency != "USD":
            raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
        if (
            type(self.per_order) is not PerOrderRiskLimits
            or type(self.per_market) is not PerMarketRiskLimits
            or type(self.conflict_domain_account) is not AccountRiskLimits
            or type(self.flow) is not FlowRiskLimits
            or type(self.state_integrity) is not StateIntegrityLimits
            or type(self.venue_defense) is not VenueDefensePolicy
        ):
            raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
        for value in (self.per_order.max_contracts, self.per_order.max_worst_case_exposure_usd):
            _require_decimal(value, positive=True)
        _require_exact_bool(self.per_order.price_reasonability_required)
        _require_decimal(self.per_order.max_abs_reference_price_deviation_usd, nonnegative=True)
        _require_int(self.per_order.max_market_data_age_ms, positive=True)
        for value in (
            self.per_market.max_abs_net_position_contracts, self.per_market.max_gross_exposure_usd,
            self.per_market.max_working_contracts, self.per_market.max_working_order_exposure_usd,
            self.conflict_domain_account.max_aggregate_exposure_usd,
            self.conflict_domain_account.max_aggregate_working_contracts,
            self.conflict_domain_account.max_conservative_unresolved_write_exposure_usd,
        ):
            _require_decimal(value, nonnegative=True)
        for value in (
            self.per_market.max_authoritative_working_orders,
            self.conflict_domain_account.max_aggregate_working_orders,
            self.conflict_domain_account.max_unresolved_write_count,
            self.flow.create_max_sends, self.flow.modify_replace_max_sends,
            self.flow.ordinary_cancel_max_sends, self.flow.automated_execution_max_sends,
            self.flow.emergency_retry_max_attempts_per_target_per_action,
        ):
            _require_int(value)
        for value in (
            self.flow.create_window_ms, self.flow.modify_replace_window_ms,
            self.flow.ordinary_cancel_window_ms, self.flow.automated_execution_window_ms,
            self.flow.emergency_cancel_max_sends, self.flow.emergency_cancel_window_ms,
            self.flow.emergency_cancel_max_in_flight, self.flow.emergency_cancel_request_deadline_ms,
            self.flow.emergency_backoff_base_ms, self.state_integrity.max_reconciliation_lag_ms,
            self.state_integrity.max_required_market_data_age_ms,
            self.state_integrity.max_reconciliation_attempts_per_cycle,
            self.state_integrity.reconciliation_read_deadline_ms,
            self.state_integrity.reconciliation_backoff_base_ms,
        ):
            _require_int(value, positive=True)
        _require_int(self.flow.emergency_backoff_max_ms, positive=True)
        _require_int(self.state_integrity.max_future_wall_clock_skew_ms)
        _require_int(self.state_integrity.reconciliation_backoff_max_ms, positive=True)
        if self.flow.emergency_backoff_max_ms < self.flow.emergency_backoff_base_ms or self.state_integrity.reconciliation_backoff_max_ms < self.state_integrity.reconciliation_backoff_base_ms:
            raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
        policy = self.venue_defense
        if policy.order_group_mode not in {"NOT_REQUIRED", "REQUIRED_FOR_EXPERIMENT"}:
            raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
        if (policy.order_group_mode == "NOT_REQUIRED" and policy.required_order_group_id is not None) or (policy.order_group_mode == "REQUIRED_FOR_EXPERIMENT" and (type(policy.required_order_group_id) is not str or not policy.required_order_group_id)):
            raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)
        _require_exact_bool(policy.cancel_order_on_pause_required)
        if policy.reduce_only_policy not in {"NO_SAFETY_CREDIT", "REQUIRED_WHEN_OPERATION_IS_PROVEN_RISK_REDUCING"} or policy.post_only_policy != "NO_SAFETY_CREDIT":
            raise RiskControlError(RiskControlCode.RISK_LIMIT_CONFIG_INVALID)

    @property
    def sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(_config_mapping(self)))


@dataclass(frozen=True, slots=True)
class PriceRangeV1:
    start: Decimal
    end: Decimal
    step: Decimal

    def __post_init__(self) -> None:
        for value in (self.start, self.end, self.step):
            _require_decimal(value)
        if not ZERO <= self.start <= self.end <= ONE or self.step <= 0 or (self.end - self.start) % self.step != 0:
            raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)


def validate_price_ranges(price: Decimal, ranges: Sequence[PriceRangeV1]) -> bool:
    _require_decimal(price)
    if not ranges:
        raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
    previous: PriceRangeV1 | None = None
    containing: list[PriceRangeV1] = []
    for item in ranges:
        if type(item) is not PriceRangeV1:
            raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
        if previous is not None and (item.start <= previous.start or item.start < previous.end):
            raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
        if item.start <= price <= item.end:
            containing.append(item)
        previous = item
    if not 1 <= len(containing) <= 2:
        raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
    if any((price - item.start) % item.step != 0 for item in containing):
        raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
    return True


@dataclass(frozen=True, slots=True)
class OrderbookReferenceV1:
    best_yes_bid: Decimal
    best_no_bid: Decimal
    best_yes_ask: Decimal
    reference_yes_price: Decimal


def build_orderbook_reference(yes_levels: Sequence[tuple[Decimal, Decimal]], no_levels: Sequence[tuple[Decimal, Decimal]]) -> OrderbookReferenceV1:
    if not yes_levels or not no_levels:
        raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
    for levels in (yes_levels, no_levels):
        last: Decimal | None = None
        for price, quantity in levels:
            _require_decimal(price); _require_decimal(quantity, positive=True)
            if price < ZERO or price > ONE or last is not None and price <= last:
                raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
            last = price
    best_yes_bid = yes_levels[-1][0]
    best_no_bid = no_levels[-1][0]
    best_yes_ask = ONE - best_no_bid
    if best_yes_bid > best_yes_ask:
        raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE)
    return OrderbookReferenceV1(best_yes_bid, best_no_bid, best_yes_ask, (best_yes_bid + best_yes_ask) / Decimal("2"))


def price_reasonable(candidate_yes_price: Decimal, reference: OrderbookReferenceV1, maximum_deviation: Decimal) -> bool:
    _require_decimal(candidate_yes_price); _require_decimal(maximum_deviation, nonnegative=True)
    return abs(candidate_yes_price - reference.reference_yes_price) <= maximum_deviation


@dataclass(frozen=True, slots=True)
class FreshnessStampV1:
    process_instance_id: str
    received_at_utc: str
    received_monotonic_ns: int
    source_timestamp_kind: str
    source_timestamp_utc: str | None
    snapshot_sha256: str

    def __post_init__(self) -> None:
        if type(self.process_instance_id) is not str or _ID_RES["process"].fullmatch(self.process_instance_id) is None:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        validate_canonical_timestamp(self.received_at_utc)
        if type(self.received_monotonic_ns) is not int or self.received_monotonic_ns < 0 or self.source_timestamp_kind not in {"NONE", "VENUE_RFC3339_UTC", "VENUE_UNIX_MS"}:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        if (self.source_timestamp_kind == "NONE") != (self.source_timestamp_utc is None):
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        if self.source_timestamp_utc is not None:
            validate_canonical_timestamp(self.source_timestamp_utc)
        if type(self.snapshot_sha256) is not str or _HEX64_RE.fullmatch(self.snapshot_sha256) is None:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)


def _parse_timestamp(value: str) -> datetime:
    validate_canonical_timestamp(value)
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _delta_microseconds(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    return ((delta.days * 86_400) + delta.seconds) * 1_000_000 + delta.microseconds


def freshness_age_ms(
    stamp: FreshnessStampV1,
    *,
    current_process_instance_id: str,
    now_monotonic_ns: int,
    now_utc: str,
    max_age_ms: int,
    max_future_wall_clock_skew_ms: int,
    prior_monotonic_ns: int | None = None,
    stale_code: RiskControlCode = RiskControlCode.MARKET_DATA_STALE,
) -> int:
    if stamp.process_instance_id != current_process_instance_id:
        raise RiskControlError(stale_code)
    if type(now_monotonic_ns) is not int or now_monotonic_ns < stamp.received_monotonic_ns or prior_monotonic_ns is not None and now_monotonic_ns < prior_monotonic_ns:
        raise RiskControlError(RiskControlCode.CLOCK_REGRESSION)
    now_wall = _parse_timestamp(now_utc)
    received_wall = _parse_timestamp(stamp.received_at_utc)
    future_us = max(0, _delta_microseconds(received_wall, now_wall))
    if (future_us + 999) // 1000 > max_future_wall_clock_skew_ms:
        raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE if stale_code is RiskControlCode.MARKET_DATA_STALE else stale_code)
    if stamp.source_timestamp_utc is not None:
        source_wall = _parse_timestamp(stamp.source_timestamp_utc)
        source_future_us = max(0, _delta_microseconds(source_wall, received_wall))
        if (source_future_us + 999) // 1000 > max_future_wall_clock_skew_ms:
            raise RiskControlError(RiskControlCode.MARKET_DATA_UNUSABLE if stale_code is RiskControlCode.MARKET_DATA_STALE else stale_code)
    delta_ns = now_monotonic_ns - stamp.received_monotonic_ns
    age_ms = (delta_ns + 999_999) // 1_000_000
    if age_ms > max_age_ms:
        raise RiskControlError(stale_code)
    return age_ms


class FreshnessRegistry:
    """Retains the first receipt/completion stamp for an exact snapshot."""

    def __init__(self) -> None:
        self.__stamps: dict[str, FreshnessStampV1] = {}

    def accept(self, stamp: FreshnessStampV1) -> FreshnessStampV1:
        prior = self.__stamps.setdefault(stamp.snapshot_sha256, stamp)
        return prior


@dataclass(frozen=True, slots=True)
class EconomicFillV1:
    market: str
    fill_id: str
    outcome_side: str
    quantity: Decimal
    yes_price: Decimal
    authoritative_created_time_utc: str

    def __post_init__(self) -> None:
        if type(self.market) is not str or not self.market or type(self.fill_id) is not str or not self.fill_id or self.outcome_side not in {"YES", "NO"}:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        _require_decimal(self.quantity, nonnegative=True); _require_decimal(self.yes_price)
        if self.yes_price < ZERO or self.yes_price > ONE:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        validate_canonical_timestamp(self.authoritative_created_time_utc)


@dataclass(frozen=True, slots=True)
class WorkingOrderV1:
    market: str
    order_id: str
    outcome_side: str
    remaining_quantity: Decimal
    yes_price: Decimal
    status: str = "resting"

    def __post_init__(self) -> None:
        if type(self.market) is not str or not self.market or type(self.order_id) is not str or not self.order_id or self.outcome_side not in {"YES", "NO"} or self.status != "resting":
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        _require_decimal(self.remaining_quantity, positive=True); _require_decimal(self.yes_price)
        if not ZERO <= self.yes_price <= ONE:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)


@dataclass(frozen=True, slots=True)
class CandidateOrderV1:
    market: str
    outcome_side: str
    quantity: Decimal
    yes_price: Decimal

    def __post_init__(self) -> None:
        if type(self.market) is not str or not self.market or self.outcome_side not in {"YES", "NO"}:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        _require_decimal(self.quantity, positive=True); _require_decimal(self.yes_price)
        if not ZERO <= self.yes_price <= ONE:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)


@dataclass(frozen=True, slots=True)
class MarketEconomicState:
    filled_exposure_usd: Decimal
    signed_net_position: Decimal
    working_exposure_usd: Decimal
    working_bid_quantity: Decimal
    working_ask_quantity: Decimal
    working_order_count: int
    working_contracts: Decimal


def _liability(side: str, quantity: Decimal, yes_price: Decimal) -> Decimal:
    return quantity * (yes_price if side == "YES" else ONE - yes_price)


def compute_market_economic_state(
    market: str,
    fills: Sequence[EconomicFillV1],
    working_orders: Sequence[WorkingOrderV1],
) -> MarketEconomicState:
    unique: dict[str, EconomicFillV1] = {}
    for fill in fills:
        if fill.market != market:
            continue
        if fill.fill_id in unique and unique[fill.fill_id] != fill:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        unique[fill.fill_id] = fill
    yes_lots: deque[list[Decimal]] = deque()
    no_lots: deque[list[Decimal]] = deque()
    for fill in sorted(unique.values(), key=lambda value: (value.authoritative_created_time_utc, value.fill_id)):
        remaining = fill.quantity
        opposite = no_lots if fill.outcome_side == "YES" else yes_lots
        while remaining and opposite:
            consumed = min(remaining, opposite[0][0])
            remaining -= consumed
            opposite[0][0] -= consumed
            if opposite[0][0] == ZERO:
                opposite.popleft()
        if remaining:
            (yes_lots if fill.outcome_side == "YES" else no_lots).append([remaining, fill.yes_price])
    filled = sum((qty * price for qty, price in yes_lots), ZERO) + sum((qty * (ONE - price) for qty, price in no_lots), ZERO)
    signed = sum((qty for qty, _ in yes_lots), ZERO) - sum((qty for qty, _ in no_lots), ZERO)
    working_exposure = ZERO
    bid_qty = ZERO
    ask_qty = ZERO
    count = 0
    contracts = ZERO
    seen_orders: set[str] = set()
    for order in working_orders:
        if order.market != market:
            continue
        if order.order_id in seen_orders:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        seen_orders.add(order.order_id)
        count += 1
        contracts += order.remaining_quantity
        working_exposure += _liability(order.outcome_side, order.remaining_quantity, order.yes_price)
        if order.outcome_side == "YES":
            bid_qty += order.remaining_quantity
        else:
            ask_qty += order.remaining_quantity
    return MarketEconomicState(filled, signed, working_exposure, bid_qty, ask_qty, count, contracts)


@dataclass(frozen=True, slots=True)
class ProjectedRiskV1:
    candidate_exposure_usd: Decimal
    worst_case_abs_net_position: Decimal
    projected_market_gross_exposure_usd: Decimal | str
    projected_working_order_count: int
    projected_working_contracts: Decimal
    projected_working_exposure_usd: Decimal


def project_candidate_risk(state: MarketEconomicState, candidate: CandidateOrderV1, unresolved_exposure: Decimal | str = ZERO) -> ProjectedRiskV1:
    candidate_exposure = _liability(candidate.outcome_side, candidate.quantity, candidate.yes_price)
    cb = candidate.quantity if candidate.outcome_side == "YES" else ZERO
    ca = candidate.quantity if candidate.outcome_side == "NO" else ZERO
    worst_net = max(abs(state.signed_net_position + state.working_bid_quantity + cb), abs(state.signed_net_position - state.working_ask_quantity - ca))
    gross: Decimal | str
    if unresolved_exposure == UNKNOWN_UNBOUNDED:
        gross = UNKNOWN_UNBOUNDED
    else:
        _require_decimal(unresolved_exposure, nonnegative=True)
        gross = state.filled_exposure_usd + state.working_exposure_usd + candidate_exposure + unresolved_exposure
    return ProjectedRiskV1(candidate_exposure, worst_net, gross, state.working_order_count + 1, state.working_contracts + candidate.quantity, state.working_exposure_usd + candidate_exposure)


def enforce_projected_limits(projected: ProjectedRiskV1, candidate: CandidateOrderV1, config: RiskLimitConfigV1) -> None:
    if projected.projected_market_gross_exposure_usd == UNKNOWN_UNBOUNDED:
        raise RiskControlError(RiskControlCode.UNKNOWN_UNBOUNDED_EXPOSURE)
    checks = (
        candidate.quantity <= config.per_order.max_contracts,
        projected.candidate_exposure_usd <= config.per_order.max_worst_case_exposure_usd,
        projected.worst_case_abs_net_position <= config.per_market.max_abs_net_position_contracts,
        projected.projected_market_gross_exposure_usd <= config.per_market.max_gross_exposure_usd,
        projected.projected_working_order_count <= config.per_market.max_authoritative_working_orders,
        projected.projected_working_contracts <= config.per_market.max_working_contracts,
        projected.projected_working_exposure_usd <= config.per_market.max_working_order_exposure_usd,
    )
    if not all(checks):
        raise RiskControlError(RiskControlCode.RISK_LIMIT_EXCEEDED)


# ---------------------------------------------------------------------------
# CORRECTION_07 C07-AGG-001..005 -- the one shared canonical conflict-domain
# account aggregate economic meaning.
#
# There is exactly ONE aggregate derivation in the system.  Release /
# current-state evaluation (``ledger_binding``) and CREATE candidate pre-send
# evaluation (``quote_lifecycle``) both call the functions below, so the two
# paths cannot drift into two numeric meanings (C07-AGG-001 / C07-06).
#
# No new risk-limit schema leaf is introduced: enforcement reuses the existing
# ``conflict_domain_account`` leaves (C07-AGG-002).
# ---------------------------------------------------------------------------

ACCOUNT_AGGREGATE_SCHEMA_ID = "ARB_KALSHI_ACCOUNT_AGGREGATE_V1"
ACCOUNT_AGGREGATE_UNIVERSE_COMPLETE = "COMPLETE"
_ADRS2_PREFIX = "ADRS2_"
_ADRS2_LENGTH = 70


@dataclass(frozen=True, slots=True)
class AccountAggregateTotalsV1:
    """Current complete conflict-domain account totals (C07-AGG-001).

    ``aggregate_exposure_usd`` counts unresolved-write exposure exactly once
    and then adds, for every market represented in the trusted universe, that
    market's filled exposure plus its working exposure.
    """

    unresolved_exposure_usd: Decimal
    aggregate_exposure_usd: Decimal
    aggregate_working_orders: int
    aggregate_working_contracts: Decimal
    markets: tuple[str, ...]


def compute_account_aggregate_totals(
    *,
    fills: Sequence[EconomicFillV1],
    working_orders: Sequence[WorkingOrderV1],
    unresolved_exposure: Decimal | str,
) -> AccountAggregateTotalsV1:
    """C07-AGG-001 shared account aggregate derivation.

    ``UNKNOWN_UNBOUNDED`` unresolved exposure fails closed here and is never
    converted to zero (C07-AGG-005).  Every economic value stays exact
    ``Decimal``; a non-``Decimal``/non-finite value cannot reach the gate
    because the element constructors already reject it, and this function
    additionally rejects a foreign element type.
    """

    if unresolved_exposure == UNKNOWN_UNBOUNDED:
        raise RiskControlError(RiskControlCode.UNKNOWN_UNBOUNDED_EXPOSURE)
    unresolved = _require_decimal(unresolved_exposure, nonnegative=True)
    fill_items = tuple(fills)
    order_items = tuple(working_orders)
    if any(type(item) is not EconomicFillV1 for item in fill_items) or any(
        type(item) is not WorkingOrderV1 for item in order_items
    ):
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    markets = tuple(sorted({item.market for item in fill_items} | {item.market for item in order_items}))
    aggregate_exposure = unresolved
    aggregate_working_orders = 0
    aggregate_working_contracts = ZERO
    for market in markets:
        state = compute_market_economic_state(market, fill_items, order_items)
        aggregate_exposure += state.filled_exposure_usd + state.working_exposure_usd
        aggregate_working_orders += state.working_order_count
        aggregate_working_contracts += state.working_contracts
    return AccountAggregateTotalsV1(
        unresolved, aggregate_exposure, aggregate_working_orders, aggregate_working_contracts, markets,
    )


@dataclass(frozen=True, slots=True)
class ProjectedAccountAggregateV1:
    """Candidate-adjusted CREATE totals (C07-AGG-001)."""

    candidate_exposure_usd: Decimal
    projected_exposure_usd: Decimal
    projected_working_orders: int
    projected_working_contracts: Decimal


def project_account_aggregate(
    totals: AccountAggregateTotalsV1, candidate: CandidateOrderV1,
) -> ProjectedAccountAggregateV1:
    """Add exactly the candidate liability, one working order, and the
    candidate quantity to the current account totals (C07-AGG-001).

    The candidate liability uses the identical exact binary-contract formula
    already used for the per-market projection -- there is no second economic
    schema and no offsetting/netting credit.
    """

    if type(totals) is not AccountAggregateTotalsV1 or type(candidate) is not CandidateOrderV1:
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    candidate_exposure = _liability(candidate.outcome_side, candidate.quantity, candidate.yes_price)
    return ProjectedAccountAggregateV1(
        candidate_exposure,
        totals.aggregate_exposure_usd + candidate_exposure,
        totals.aggregate_working_orders + 1,
        totals.aggregate_working_contracts + candidate.quantity,
    )


def enforce_account_aggregate_limits(
    projected: ProjectedAccountAggregateV1, config: RiskLimitConfigV1,
) -> None:
    """C07-AGG-002: the existing account leaves, compared inclusively.

    No ``max_aggregate_projected_exposure_usd`` field is added.
    """

    if type(projected) is not ProjectedAccountAggregateV1 or type(config) is not RiskLimitConfigV1:
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    account = config.conflict_domain_account
    if not (
        projected.projected_exposure_usd <= account.max_aggregate_exposure_usd
        and projected.projected_working_orders <= account.max_aggregate_working_orders
        and projected.projected_working_contracts <= account.max_aggregate_working_contracts
    ):
        raise RiskControlError(RiskControlCode.RISK_LIMIT_EXCEEDED)


def account_aggregate_current_state_within_limits(
    totals: AccountAggregateTotalsV1, config: RiskLimitConfigV1,
) -> bool:
    """Release / current-state form of the same inclusive comparison
    (C07-06).  Returns a predicate rather than raising because the release
    predicate vector is boolean; the numeric meaning is exactly
    ``enforce_account_aggregate_limits`` with no candidate added.
    """

    if type(totals) is not AccountAggregateTotalsV1 or type(config) is not RiskLimitConfigV1:
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    account = config.conflict_domain_account
    return (
        totals.aggregate_exposure_usd <= account.max_aggregate_exposure_usd
        and totals.aggregate_working_orders <= account.max_aggregate_working_orders
        and totals.aggregate_working_contracts <= account.max_aggregate_working_contracts
    )


@dataclass(frozen=True, slots=True)
class AccountAggregateInputV1:
    """The complete, identity-bound trusted conflict-domain universe.

    Construction itself is the C07-AGG-005 fail-closed gate: an incomplete
    universe, any identity conflict, an unequal authority/ledger tail, a
    malformed identity, an unknown/unbounded unresolved exposure, or a
    missing trusted read-set identity makes the object unconstructable, so no
    aggregate snapshot can be minted and no CREATE assessment can become
    eligible.
    """

    conflict_domain_ref: str
    authority_namespace_id: str
    authority_instance_id: str
    ledger_instance_id: str
    authority_trusted_sequence: int
    authority_trusted_hash: str
    ledger_terminal_sequence: int
    ledger_terminal_hash: str
    risk_config_sha256: str
    # C07-AGG-004 binds "trusted_dynamic_read_set_id / required reconciliation
    # identity".  The active revision-2 runtime always supplies the exact
    # ``ADRS2_<64hex>`` read-set identity; the legacy SUBACCOUNT=0 path has no
    # such identity and binds ``None`` here, remaining bound to the required
    # reconciliation snapshot identity below.  Either way the snapshot cannot
    # be carried across a different trusted read acquisition.
    trusted_dynamic_read_set_id: str | None
    reconciliation_snapshot_sha256: str
    universe_completeness: str
    conflict_ids: tuple[str, ...]
    fills: tuple[EconomicFillV1, ...]
    working_orders: tuple[WorkingOrderV1, ...]
    unresolved_exposure_usd: Decimal | str

    def __post_init__(self) -> None:
        unavailable = RiskControlCode.RISK_INPUT_UNAVAILABLE
        for value in (
            self.conflict_domain_ref, self.authority_namespace_id, self.authority_instance_id,
            self.ledger_instance_id, self.universe_completeness,
        ):
            if type(value) is not str or not value or unicodedata.normalize("NFC", value) != value:
                raise RiskControlError(unavailable)
        for value in (
            self.authority_trusted_hash, self.ledger_terminal_hash, self.risk_config_sha256,
            self.reconciliation_snapshot_sha256,
        ):
            if type(value) is not str or _HEX64_RE.fullmatch(value) is None:
                raise RiskControlError(unavailable)
        for value in (self.authority_trusted_sequence, self.ledger_terminal_sequence):
            if type(value) is not int or value < 0:
                raise RiskControlError(unavailable)
        read_set_id = self.trusted_dynamic_read_set_id
        if read_set_id is not None and (
            type(read_set_id) is not str
            or len(read_set_id) != _ADRS2_LENGTH
            or read_set_id[:6] != _ADRS2_PREFIX
            or _HEX64_RE.fullmatch(read_set_id[6:]) is None
        ):
            raise RiskControlError(unavailable)
        # C07-AGG-005 / C06-LB-08: an unequal authority/ledger tail can never
        # mint a usable aggregate snapshot.
        if (self.authority_trusted_sequence, self.authority_trusted_hash) != (
            self.ledger_terminal_sequence, self.ledger_terminal_hash
        ):
            raise RiskControlError(unavailable)
        # C07-AGG-003 / C07-AGG-005: an incomplete universe or any identity
        # conflict fails closed and is never treated as "no other exposure".
        if self.universe_completeness != ACCOUNT_AGGREGATE_UNIVERSE_COMPLETE or self.conflict_ids != ():
            raise RiskControlError(unavailable)
        if type(self.fills) is not tuple or type(self.working_orders) is not tuple:
            raise RiskControlError(unavailable)
        if any(type(item) is not EconomicFillV1 for item in self.fills) or any(
            type(item) is not WorkingOrderV1 for item in self.working_orders
        ):
            raise RiskControlError(unavailable)
        if self.unresolved_exposure_usd == UNKNOWN_UNBOUNDED:
            raise RiskControlError(RiskControlCode.UNKNOWN_UNBOUNDED_EXPOSURE)
        _require_decimal(self.unresolved_exposure_usd, nonnegative=True)


@dataclass(frozen=True, slots=True)
class AccountAggregateSnapshotV1:
    """Deterministic aggregate snapshot identity (C07-AGG-004).

    ``sha256`` binds the domain/authority/ledger/config/read-set identities
    together with the exact current and projected aggregate economics, so a
    candidate assessment cannot be carried across a changed authority/ledger
    tail or a different trusted read acquisition.
    """

    aggregate_input: AccountAggregateInputV1
    totals: AccountAggregateTotalsV1
    projected: ProjectedAccountAggregateV1
    sha256: str

    @property
    def authority_trusted_sequence(self) -> int:
        return self.aggregate_input.authority_trusted_sequence

    @property
    def authority_trusted_hash(self) -> str:
        return self.aggregate_input.authority_trusted_hash

    @property
    def ledger_terminal_sequence(self) -> int:
        return self.aggregate_input.ledger_terminal_sequence

    @property
    def ledger_terminal_hash(self) -> str:
        return self.aggregate_input.ledger_terminal_hash


def account_aggregate_snapshot_preimage(
    aggregate_input: AccountAggregateInputV1,
    totals: AccountAggregateTotalsV1,
    projected: ProjectedAccountAggregateV1,
) -> dict[str, object]:
    """Exact C07-AGG-004 hash preimage.  Every economic value is an exact
    ``Decimal`` encoded by the existing canonical encoder; no float
    conversion occurs anywhere in this preimage."""

    return {
        "schema_id": ACCOUNT_AGGREGATE_SCHEMA_ID,
        "conflict_domain_ref": aggregate_input.conflict_domain_ref,
        "authority_namespace_id": aggregate_input.authority_namespace_id,
        "authority_instance_id": aggregate_input.authority_instance_id,
        "ledger_instance_id": aggregate_input.ledger_instance_id,
        "authority_trusted_sequence": aggregate_input.authority_trusted_sequence,
        "authority_trusted_hash": aggregate_input.authority_trusted_hash,
        "ledger_terminal_sequence": aggregate_input.ledger_terminal_sequence,
        "ledger_terminal_hash": aggregate_input.ledger_terminal_hash,
        "risk_config_sha256": aggregate_input.risk_config_sha256,
        "trusted_dynamic_read_set_id": aggregate_input.trusted_dynamic_read_set_id,
        "reconciliation_snapshot_sha256": aggregate_input.reconciliation_snapshot_sha256,
        "universe_completeness": aggregate_input.universe_completeness,
        "markets": list(totals.markets),
        "unresolved_exposure_usd": totals.unresolved_exposure_usd,
        "current_aggregate_exposure_usd": totals.aggregate_exposure_usd,
        "current_aggregate_working_orders": totals.aggregate_working_orders,
        "current_aggregate_working_contracts": totals.aggregate_working_contracts,
        "candidate_exposure_usd": projected.candidate_exposure_usd,
        "projected_aggregate_exposure_usd": projected.projected_exposure_usd,
        "projected_aggregate_working_orders": projected.projected_working_orders,
        "projected_aggregate_working_contracts": projected.projected_working_contracts,
    }


_AGGREGATE_EXPECTATION_KEY = object()

# CORRECTION_01 C07-IMPL-BLOCK-01: the exact identity fields that must compare
# equal between the aggregate universe actually supplied and the independently
# sourced authoritative expectation.  A deterministic self-hash proves internal
# consistency only; it is NOT authority proof.
ACCOUNT_AGGREGATE_IDENTITY_FIELDS = (
    "conflict_domain_ref",
    "authority_namespace_id",
    "authority_instance_id",
    "ledger_instance_id",
    "authority_trusted_sequence",
    "authority_trusted_hash",
    "ledger_terminal_sequence",
    "ledger_terminal_hash",
    "risk_config_sha256",
    "trusted_dynamic_read_set_id",
    "reconciliation_snapshot_sha256",
)


@dataclass(frozen=True, slots=True, init=False)
class AccountAggregateAuthorityExpectationV1:
    """CORRECTION_01 Gate A — the authoritative expected aggregate identity.

    This object is an UNFORGEABLE trusted product of the locked-ledger
    acquisition boundary: it can only be produced by
    ``build_account_aggregate_authority_expectation``, which reads every
    store/domain/tail value directly from the live ``LockedLedger`` and takes
    the remaining current-context identities from the caller's own
    authoritative invocation state.

    It is deliberately NOT derivable from an ``AccountAggregateInputV1``, so a
    caller cannot satisfy both sides of the comparison from one mutated
    object.
    """

    conflict_domain_ref: str
    authority_namespace_id: str
    authority_instance_id: str
    ledger_instance_id: str
    authority_trusted_sequence: int
    authority_trusted_hash: str
    ledger_terminal_sequence: int
    ledger_terminal_hash: str
    risk_config_sha256: str
    trusted_dynamic_read_set_id: str | None
    reconciliation_snapshot_sha256: str

    def __init__(self, key: object, **values: object) -> None:
        if key is not _AGGREGATE_EXPECTATION_KEY:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])


def build_account_aggregate_authority_expectation(
    locked: LockedLedger,
    *,
    risk_config_sha256: str,
    trusted_dynamic_read_set_id: str | None,
    reconciliation_snapshot_sha256: str,
) -> AccountAggregateAuthorityExpectationV1:
    """CORRECTION_01 Gate A source of truth.

    Every store/domain/tail value is read from the live ``LockedLedger``; the
    config, trusted read-set and reconciliation identities come from the
    caller's current invocation context.  Nothing here is copied from the
    aggregate object being validated.
    """

    if type(locked) is not LockedLedger or getattr(locked, "closed", False):
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    tail = locked.events[-1]
    authority = locked.authority_row
    if (authority.trusted_sequence, authority.trusted_event_hash) != (tail.sequence, tail.event_hash):
        # An authority row that has not caught up to the terminal ledger event
        # cannot mint an authoritative expectation.
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    return AccountAggregateAuthorityExpectationV1(
        _AGGREGATE_EXPECTATION_KEY,
        conflict_domain_ref=locked.conflict_domain_ref,
        authority_namespace_id=locked.authority_meta.authority_namespace_id,
        authority_instance_id=locked.authority_meta.authority_instance_id,
        ledger_instance_id=locked.ledger_meta.ledger_instance_id,
        authority_trusted_sequence=authority.trusted_sequence,
        authority_trusted_hash=authority.trusted_event_hash,
        ledger_terminal_sequence=tail.sequence,
        ledger_terminal_hash=tail.event_hash,
        risk_config_sha256=risk_config_sha256,
        trusted_dynamic_read_set_id=trusted_dynamic_read_set_id,
        reconciliation_snapshot_sha256=reconciliation_snapshot_sha256,
    )


def require_account_aggregate_identity(
    aggregate_input: AccountAggregateInputV1,
    expectation: AccountAggregateAuthorityExpectationV1,
) -> None:
    """CORRECTION_01 Gate A: exact equality on every C07-AGG-005 identity.

    Any single mismatched field fails closed with the existing risk-input
    semantics, so a foreign conflict domain, authority namespace/instance,
    ledger instance, risk-config identity, trusted read-set identity,
    reconciliation identity, or authority/ledger tail can never support an
    eligible CREATE assessment.
    """

    if (
        type(aggregate_input) is not AccountAggregateInputV1
        or type(expectation) is not AccountAggregateAuthorityExpectationV1
    ):
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    for name in ACCOUNT_AGGREGATE_IDENTITY_FIELDS:
        actual = getattr(aggregate_input, name)
        expected = getattr(expectation, name)
        if type(actual) is not type(expected) or actual != expected:
            raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)


def build_account_aggregate_snapshot(
    *,
    aggregate_input: AccountAggregateInputV1,
    candidate: CandidateOrderV1,
    config: RiskLimitConfigV1,
    expectation: AccountAggregateAuthorityExpectationV1,
) -> AccountAggregateSnapshotV1:
    """Derive and bind the candidate-aware account aggregate snapshot.

    CORRECTION_01: the snapshot can only be minted after the supplied
    aggregate universe has been proven identical, field by field, to the
    independently sourced authoritative expectation.  The digest below then
    records an already-authoritative identity; it never substitutes for one.

    This function establishes IDENTITY only; it deliberately does not decide
    economic eligibility, so the snapshot digest exists for an over-limit
    candidate too and can participate in the candidate economic identity.
    Limit enforcement is the separate ``enforce_account_aggregate_limits``
    call.
    """

    if (
        type(aggregate_input) is not AccountAggregateInputV1
        or type(candidate) is not CandidateOrderV1
        or type(config) is not RiskLimitConfigV1
    ):
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    require_account_aggregate_identity(aggregate_input, expectation)
    if aggregate_input.risk_config_sha256 != config.sha256:
        raise RiskControlError(RiskControlCode.RISK_INPUT_UNAVAILABLE)
    totals = compute_account_aggregate_totals(
        fills=aggregate_input.fills,
        working_orders=aggregate_input.working_orders,
        unresolved_exposure=aggregate_input.unresolved_exposure_usd,
    )
    projected = project_account_aggregate(totals, candidate)
    digest = sha256_hex(canonical_json_bytes(
        account_aggregate_snapshot_preimage(aggregate_input, totals, projected),
    ))
    return AccountAggregateSnapshotV1(aggregate_input, totals, projected, digest)


@dataclass(frozen=True, slots=True)
class WriterEligibilityAssessment:
    risk_assessment_id: str
    operation_kind: str
    request_id: str
    candidate_request_sha256: str
    candidate_economic_sha256: str
    risk_config_sha256: str
    market_data_snapshot_sha256: str
    market_data_freshness_identity_sha256: str
    reconciliation_snapshot_sha256: str
    reconciliation_freshness_identity_sha256: str
    risk_state_epoch: int
    freshness_deadline_monotonic_ns: int
    eligible: bool
    # DSB-WRITER-007 active execution-domain commitments.  ``None`` on the
    # legacy SUBACCOUNT=0 path (which never issues a normal-writer permit);
    # populated by the revision-2 active runtime.  The reconciliation-snapshot
    # and risk-assessment hashes computed by the active runtime include
    # ``active_contract_sha256`` and ``domain_binding_sha256``.
    domain_binding_id: str | None = None
    domain_binding_sha256: str | None = None
    active_contract_id: str | None = None
    active_contract_sha256: str | None = None
    bootstrap_contract_sha256: str | None = None
    conflict_domain_ref: str | None = None
    account_scope_ref: str | None = None
    subaccount: int | None = None
    exchange_index: int | None = None
    environment: str | None = None
    incident_id: str | None = None
    writer_proof_id: str | None = None
    # Correction 02 DSB-WRITER-007 / DSB-QUOTE-003: the exact private trusted
    # dynamic read-set identity (``ADRS2_<64hex>``) supporting current risk,
    # so a permit/assessment cannot be carried across current-read
    # acquisitions.  ``None`` on the legacy path.
    trusted_dynamic_read_set_id: str | None = None
    # CORRECTION_07 C07-AGG-004: the exact candidate-aware conflict-domain
    # account aggregate snapshot digest, plus the authority/ledger tail that
    # aggregate state was derived over.  ``None`` on the legacy path and on
    # the ordinary CANCEL path (which projects no CREATE candidate).
    # CORRECTION_08: the aggregate binding is mandatory only through the
    # dedicated ``issue_strategy1_gate_d_create_permit`` entrypoint; the
    # generic ``issue_permit`` accepts an ABSENT binding under predecessor
    # semantics, so ``operation_kind`` alone never selects C07 scope.
    account_aggregate_snapshot_sha256: str | None = None
    account_aggregate_authority_trusted_sequence: int | None = None
    account_aggregate_authority_trusted_hash: str | None = None
    account_aggregate_ledger_terminal_sequence: int | None = None
    account_aggregate_ledger_terminal_hash: str | None = None
    # CORRECTION_01 Gate B: the aggregate universe's own domain/store and
    # current-context identities are carried here so permit issuance can
    # INDEPENDENTLY recheck them against the live LockedLedger and against
    # this assessment's own authoritative top-level identities.  Without
    # these a permit could accept a post-assessment substitution whose
    # self-hash is merely internally consistent.
    account_aggregate_conflict_domain_ref: str | None = None
    account_aggregate_authority_namespace_id: str | None = None
    account_aggregate_authority_instance_id: str | None = None
    account_aggregate_ledger_instance_id: str | None = None
    account_aggregate_risk_config_sha256: str | None = None
    account_aggregate_trusted_dynamic_read_set_id: str | None = None
    account_aggregate_reconciliation_snapshot_sha256: str | None = None


_PERMIT_CONSTRUCTION_KEY = object()


@dataclass(frozen=True, slots=True, init=False)
class NormalWriterPermit:
    permit_id: str
    risk_assessment_id: str
    process_instance_id: str
    normal_writer_session_id: str
    conflict_domain_ref: str
    operation_kind: str
    request_id: str
    candidate_request_sha256: str
    candidate_economic_sha256: str
    risk_config_sha256: str
    market_data_snapshot_sha256: str
    market_data_freshness_identity_sha256: str
    reconciliation_snapshot_sha256: str
    reconciliation_freshness_identity_sha256: str
    risk_state_epoch: int
    initial_trusted_sequence: int
    initial_trusted_hash: str
    initial_ledger_sequence: int
    initial_ledger_hash: str
    intent_event_id: str
    prepared_event_id: str
    send_boundary_event_id: str
    issued_at_utc: str
    issued_monotonic_ns: int
    freshness_deadline_monotonic_ns: int
    private_gate_instance_identity: object
    # DSB-WRITER-007 active execution-domain commitments (``None`` on the
    # legacy path).  ``permit_domain_commitment_sha256`` is the exact
    # canonical digest of the active commitment tuple.
    domain_binding_id: str | None = None
    domain_binding_sha256: str | None = None
    active_contract_id: str | None = None
    active_contract_sha256: str | None = None
    environment: str | None = None
    account_scope_ref: str | None = None
    subaccount: int | None = None
    exchange_index: int | None = None
    incident_id: str | None = None
    writer_proof_id: str | None = None
    bootstrap_contract_sha256: str | None = None
    # Correction 02 DSB-WRITER-007 / DSB-QUOTE-003.
    trusted_dynamic_read_set_id: str | None = None
    permit_domain_commitment_sha256: str | None = None

    def __init__(self, key: object, **values: object) -> None:
        if key is not _PERMIT_CONSTRUCTION_KEY:
            raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
        for field in fields(type(self)):
            object.__setattr__(self, field.name, values[field.name])

    def __copy__(self):
        raise TypeError("NormalWriterPermit cannot be copied")

    def __deepcopy__(self, memo):
        del memo
        raise TypeError("NormalWriterPermit cannot be deep-copied")

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("NormalWriterPermit cannot be serialized")


_ACTIVE_ASSESSMENT_FIELDS = (
    "domain_binding_id", "domain_binding_sha256", "active_contract_id",
    "active_contract_sha256", "bootstrap_contract_sha256", "account_scope_ref",
    "subaccount", "exchange_index", "environment", "incident_id", "writer_proof_id",
    "trusted_dynamic_read_set_id",
)


def compute_permit_domain_commitment_sha256(permit: "NormalWriterPermit") -> str:
    """Exact DSB-WRITER-007 canonical digest of a permit's active commitment
    tuple.  Correction 02 folds the trusted dynamic read-set identity into
    the digest so the permit is bound to one current-read acquisition."""
    return sha256_hex(canonical_json_bytes({
        "account_scope_ref": permit.account_scope_ref,
        "active_contract_id": permit.active_contract_id,
        "active_contract_sha256": permit.active_contract_sha256,
        "bootstrap_contract_sha256": permit.bootstrap_contract_sha256,
        "conflict_domain_ref": permit.conflict_domain_ref,
        "domain_binding_id": permit.domain_binding_id,
        "domain_binding_sha256": permit.domain_binding_sha256,
        "environment": permit.environment,
        "exchange_index": permit.exchange_index,
        "incident_id": permit.incident_id,
        "subaccount": permit.subaccount,
        "trusted_dynamic_read_set_id": permit.trusted_dynamic_read_set_id,
        "writer_proof_id": permit.writer_proof_id,
    }))


def _active_permit_commitment_from_assessment(
    assessment: "WriterEligibilityAssessment", *, conflict_domain_ref: str,
) -> dict[str, object]:
    """Derive the active-domain permit commitment fields from the assessment.

    Legacy (SUBACCOUNT=0) assessments carry no active commitments -> every
    field is ``None`` and no commitment digest is computed.  For an active
    assessment every commitment field must be present and the assessment's
    conflict domain must equal the locked revision-2 ledger's conflict domain
    (DSB-WRITER-007 / NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH).
    """
    present = [getattr(assessment, name) is not None for name in _ACTIVE_ASSESSMENT_FIELDS]
    if not any(present):
        return {name: None for name in (
            "domain_binding_id", "domain_binding_sha256", "active_contract_id",
            "active_contract_sha256", "environment", "account_scope_ref", "subaccount",
            "exchange_index", "incident_id", "writer_proof_id", "bootstrap_contract_sha256",
            "trusted_dynamic_read_set_id", "permit_domain_commitment_sha256",
        )}
    read_set_id = assessment.trusted_dynamic_read_set_id
    if (
        not all(present)
        or assessment.conflict_domain_ref != conflict_domain_ref
        or type(read_set_id) is not str
        or read_set_id[:6] != "ADRS2_"
        or len(read_set_id) != 70
    ):
        raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
    fields_out = {name: getattr(assessment, name) for name in (
        "domain_binding_id", "domain_binding_sha256", "active_contract_id",
        "active_contract_sha256", "environment", "account_scope_ref", "subaccount",
        "exchange_index", "incident_id", "writer_proof_id", "bootstrap_contract_sha256",
        "trusted_dynamic_read_set_id",
    )}
    digest = sha256_hex(canonical_json_bytes({
        "account_scope_ref": fields_out["account_scope_ref"],
        "active_contract_id": fields_out["active_contract_id"],
        "active_contract_sha256": fields_out["active_contract_sha256"],
        "bootstrap_contract_sha256": fields_out["bootstrap_contract_sha256"],
        "conflict_domain_ref": conflict_domain_ref,
        "domain_binding_id": fields_out["domain_binding_id"],
        "domain_binding_sha256": fields_out["domain_binding_sha256"],
        "environment": fields_out["environment"],
        "exchange_index": fields_out["exchange_index"],
        "incident_id": fields_out["incident_id"],
        "subaccount": fields_out["subaccount"],
        "trusted_dynamic_read_set_id": fields_out["trusted_dynamic_read_set_id"],
        "writer_proof_id": fields_out["writer_proof_id"],
    }))
    fields_out["permit_domain_commitment_sha256"] = digest
    return fields_out


def _assessment_aggregate_binding_core(
    assessment: "WriterEligibilityAssessment",
) -> tuple[object, ...]:
    """The aggregate binding fields that are mandatory in every COMPLETE
    binding.  ``account_aggregate_trusted_dynamic_read_set_id`` is excluded
    because ``None`` is its legitimate value on the legacy non-ADRS2 path."""

    return (
        assessment.account_aggregate_snapshot_sha256,
        assessment.account_aggregate_authority_trusted_sequence,
        assessment.account_aggregate_authority_trusted_hash,
        assessment.account_aggregate_ledger_terminal_sequence,
        assessment.account_aggregate_ledger_terminal_hash,
        assessment.account_aggregate_conflict_domain_ref,
        assessment.account_aggregate_authority_namespace_id,
        assessment.account_aggregate_authority_instance_id,
        assessment.account_aggregate_ledger_instance_id,
        assessment.account_aggregate_risk_config_sha256,
        assessment.account_aggregate_reconciliation_snapshot_sha256,
    )


def _assessment_aggregate_binding_absent(assessment: "WriterEligibilityAssessment") -> bool:
    """CORRECTION_08 C08-DEF-004 ABSENT: every aggregate binding field,
    including the aggregate read-set identity, is ``None``.  A lone
    aggregate read-set identity is a PARTIAL binding, never ABSENT."""

    return (
        all(item is None for item in _assessment_aggregate_binding_core(assessment))
        and assessment.account_aggregate_trusted_dynamic_read_set_id is None
    )


def _require_generic_aggregate_binding(
    assessment: "WriterEligibilityAssessment", locked: LockedLedger, tail: object,
) -> None:
    """CORRECTION_08 C08-GEN-002..005 aggregate gate for the shared generic
    ``WriterEligibilityGate.issue_permit`` entrypoint.

    ABSENT is passed through unchanged, so a non-C07 caller (the ordinary
    CANCEL operation, the accepted one-order-lifecycle CREATE spine, the
    legacy non-aggregate path) keeps its predecessor semantics even for a
    genuine ``CREATE_ORDER_V2``: ``operation_kind`` alone never selects C07
    aggregate scope (C08-SCOPE-001/005).  PARTIAL_OR_MALFORMED and COMPLETE
    bindings receive the full CORRECTION_01 Gate-B validation.
    """

    if _assessment_aggregate_binding_absent(assessment):
        return
    _require_assessment_aggregate_binding(assessment, locked, tail)


def _require_strategy1_gate_d_create_aggregate_binding(
    assessment: "WriterEligibilityAssessment", locked: LockedLedger, tail: object,
) -> None:
    """CORRECTION_08 C08-SCOPED-002..004 aggregate gate for the dedicated
    R1-D07 N1 Strategy-1 Gate-D CREATE entrypoint.

    ABSENT and PARTIAL_OR_MALFORMED are both invalid.  COMPLETE additionally
    requires a well-formed non-null ``ADRS2_<64hex>`` aggregate read-set
    identity equal to the assessment's active ``trusted_dynamic_read_set_id``
    and then every CORRECTION_01 Gate-B equality.
    """

    read_set_id = assessment.account_aggregate_trusted_dynamic_read_set_id
    if (
        type(read_set_id) is not str
        or len(read_set_id) != _ADRS2_LENGTH
        or read_set_id[:6] != _ADRS2_PREFIX
        or _HEX64_RE.fullmatch(read_set_id[6:]) is None
        or read_set_id != assessment.trusted_dynamic_read_set_id
        or any(item is None for item in _assessment_aggregate_binding_core(assessment))
    ):
        raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
    _require_assessment_aggregate_binding(assessment, locked, tail)


def _require_assessment_aggregate_binding(
    assessment: "WriterEligibilityAssessment", locked: LockedLedger, tail: object,
) -> None:
    """CORRECTION_07 C07-AGG-004 permit-issuance anti-substitution gate for a
    binding that is not ABSENT.

    Permit issuance MUST reject if the active locked tail no longer equals
    the tail that aggregate state was derived over, or if the bound identity
    is partial or malformed.  A candidate assessment therefore cannot be
    carried across a changed authority/ledger tail.

    An aggregate BREACH never reaches this gate at all: the aggregate limits
    are enforced inside ``build_writer_eligibility_assessment``, a breach
    makes the assessment ineligible, and permit issuance already refuses a
    non-eligible assessment.  So an aggregate failure emits no permit, no
    send-boundary event, and invokes no transport.

    Whether an ABSENT binding is acceptable is decided by the calling
    entrypoint gate (CORRECTION_08), never here.
    """

    # CORRECTION_01: a PARTIAL aggregate binding is invalid.  The read-set
    # identity is intentionally excluded from this completeness tuple because
    # ``None`` is its legitimate value on the legacy non-ADRS2 path; it is
    # compared for exact equality against the assessment below either way.
    if any(item is None for item in _assessment_aggregate_binding_core(assessment)):
        raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
    if (
        type(assessment.account_aggregate_snapshot_sha256) is not str
        or _HEX64_RE.fullmatch(assessment.account_aggregate_snapshot_sha256) is None
    ):
        raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
    # CORRECTION_01 Gate B — independent authoritative recheck.
    #
    # The domain and store identities are compared against the LIVE
    # LockedLedger, and the config / read-set / reconciliation identities
    # against this assessment's own authoritative top-level values.  Neither
    # side is taken from the aggregate object, so a caller-constructed or
    # post-assessment-substituted aggregate identity cannot pass merely
    # because its self-hash is internally consistent.
    #
    # Ownership note: this does NOT re-decide the predecessor
    # DSB-WRITER-007/008 active-domain commitment, which is a separate object
    # validated by its own gate and keeps its own exact classification.
    if (
        assessment.account_aggregate_conflict_domain_ref != locked.conflict_domain_ref
        or assessment.account_aggregate_authority_namespace_id
        != locked.authority_meta.authority_namespace_id
        or assessment.account_aggregate_authority_instance_id
        != locked.authority_meta.authority_instance_id
        or assessment.account_aggregate_ledger_instance_id
        != locked.ledger_meta.ledger_instance_id
        or assessment.account_aggregate_risk_config_sha256 != assessment.risk_config_sha256
        or assessment.account_aggregate_reconciliation_snapshot_sha256
        != assessment.reconciliation_snapshot_sha256
        or assessment.account_aggregate_trusted_dynamic_read_set_id
        != assessment.trusted_dynamic_read_set_id
    ):
        raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
    # Tail movement retains the existing unexpected-tail classification.
    if (
        assessment.account_aggregate_authority_trusted_sequence,
        assessment.account_aggregate_authority_trusted_hash,
        assessment.account_aggregate_ledger_terminal_sequence,
        assessment.account_aggregate_ledger_terminal_hash,
    ) != (
        tail.sequence, tail.event_hash, tail.sequence, tail.event_hash,
    ) or (
        locked.authority_row.trusted_sequence, locked.authority_row.trusted_event_hash,
    ) != (tail.sequence, tail.event_hash):
        raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL)


class PermitStage(enum.StrEnum):
    INTENT = "INTENT"
    PREPARED = "PREPARED"
    SEND_BOUNDARY = "SEND_BOUNDARY"
    CONSUMED = "CONSUMED"
    INVALIDATED = "INVALIDATED"


@dataclass(slots=True)
class NormalWriterPermitProgress:
    permit_id: str
    stage: PermitStage
    expected_trusted_sequence: int
    expected_trusted_hash: str
    expected_ledger_sequence: int
    expected_ledger_hash: str
    last_monotonic_ns: int
    transport_invocation_count: int

    def __copy__(self):
        raise TypeError("permit progress is private")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("permit progress cannot be serialized")


@dataclass(slots=True)
class _PermitContext:
    permit: NormalWriterPermit
    progress: NormalWriterPermitProgress
    locked: LockedLedger
    intent_payload: Mapping[str, object]
    prepared_payload: Mapping[str, object]
    execution_attempt_id: str


class WriterEligibilityGate:
    """Process-local permit issuer and adapter-entry/hard-HALT arbiter."""

    def __init__(self, *, monotonic_clock_ns: Callable[[], int], wall_clock: Callable[[], datetime], uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4) -> None:
        self.__mutex = threading.RLock()
        self.__monotonic = monotonic_clock_ns
        self.__wall = wall_clock
        self.__uuid = uuid_factory
        self.__identity = object()
        self.__process_instance_id = f"proc_{uuid_factory().hex}"
        self.__contexts: dict[str, _PermitContext] = {}
        self.__hard_halt_requested = False

    @property
    def process_instance_id(self) -> str:
        return self.__process_instance_id

    @property
    def hard_halt_requested(self) -> bool:
        with self.__mutex:
            return self.__hard_halt_requested

    @property
    def outstanding_permit_count(self) -> int:
        """Return the number of genuine not-entered permits owned by this gate.

        This is intentionally read-only.  Release evaluation uses it to bind
        the no-outstanding-permits predicate to process-local capability state
        without exposing the private progress records or a permit mutation
        surface.
        """
        with self.__mutex:
            return sum(
                1
                for context in self.__contexts.values()
                if context.progress.transport_invocation_count == 0
                and context.progress.stage is not PermitStage.INVALIDATED
            )

    def issue_permit(
        self,
        *,
        locked: LockedLedger,
        normal_writer_session_id: str,
        assessment: WriterEligibilityAssessment,
        intent_payload: Mapping[str, object],
        prepared_payload: Mapping[str, object],
    ) -> NormalWriterPermit:
        """Shared predecessor-compatible permit entrypoint (C08-GEN-001..006).

        An ABSENT aggregate binding does not by itself reject; a partial or
        malformed binding rejects; a complete binding keeps the CORRECTION_01
        Gate-B anti-substitution checks.  This entrypoint never grants the
        R1-D07 N1 Strategy-1 Gate-D CREATE scope, which is reachable only
        through ``issue_strategy1_gate_d_create_permit``."""

        return self.__issue_permit_with_aggregate_gate(
            locked=locked, normal_writer_session_id=normal_writer_session_id,
            assessment=assessment, intent_payload=intent_payload,
            prepared_payload=prepared_payload,
            aggregate_gate=_require_generic_aggregate_binding,
        )

    def issue_strategy1_gate_d_create_permit(
        self,
        *,
        locked: LockedLedger,
        normal_writer_session_id: str,
        assessment: WriterEligibilityAssessment,
        intent_payload: Mapping[str, object],
        prepared_payload: Mapping[str, object],
    ) -> NormalWriterPermit:
        """Dedicated R1-D07 N1 Strategy-1 Gate-D CREATE permit entrypoint
        (C08-SCOPED-001..007).  The entrypoint itself is the C07 scope
        discriminator: it accepts only ``CREATE_ORDER_V2`` and requires a
        COMPLETE aggregate binding with the active ``ADRS2_<64hex>`` read-set
        identity plus every Gate-B equality.  It shares the private permit
        construction/state machine with ``issue_permit`` and never falls
        back to it."""

        if (
            type(assessment) is not WriterEligibilityAssessment
            or assessment.operation_kind != "CREATE_ORDER_V2"
        ):
            raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
        return self.__issue_permit_with_aggregate_gate(
            locked=locked, normal_writer_session_id=normal_writer_session_id,
            assessment=assessment, intent_payload=intent_payload,
            prepared_payload=prepared_payload,
            aggregate_gate=_require_strategy1_gate_d_create_aggregate_binding,
        )

    def __issue_permit_with_aggregate_gate(
        self,
        *,
        locked: LockedLedger,
        normal_writer_session_id: str,
        assessment: WriterEligibilityAssessment,
        intent_payload: Mapping[str, object],
        prepared_payload: Mapping[str, object],
        aggregate_gate: Callable[[WriterEligibilityAssessment, LockedLedger, object], None],
    ) -> NormalWriterPermit:
        """The one shared permit construction/state-machine mechanism behind
        both public entrypoints (C08-SCOPED-005)."""

        with self.__mutex:
            nested_intent_payload = intent_payload.get("intent_payload")
            execution_attempt_id = intent_payload.get("execution_attempt_id")
            if (
                self.__hard_halt_requested
                or type(assessment) is not WriterEligibilityAssessment
                or assessment.eligible is not True
                or not isinstance(nested_intent_payload, Mapping)
                or nested_intent_payload.get("request_id") != assessment.request_id
                or prepared_payload.get("request_id") != assessment.request_id
                or prepared_payload.get("operation_name") != assessment.operation_kind
                or prepared_payload.get("prepared_request_sha256") != assessment.candidate_request_sha256
                or type(execution_attempt_id) is not str
                or not execution_attempt_id
                or unicodedata.normalize("NFC", execution_attempt_id) != execution_attempt_id
                or execution_attempt_id in (assessment.request_id, prepared_payload.get("client_order_id"))
            ):
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
            projection = locked.projection()
            if projection.active_writer_session_id != normal_writer_session_id or projection.risk_control_state != "WRITER_ELIGIBLE" or projection.risk_state_epoch != assessment.risk_state_epoch:
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
            tail = locked.events[-1]
            aggregate_gate(assessment, locked, tail)
            now = self.__monotonic()
            if type(now) is not int or now < 0 or now > assessment.freshness_deadline_monotonic_ns:
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_EXPIRED)
            permit_id = f"nwp_{self.__uuid().hex}"
            stage_ids = tuple(f"evt_{self.__uuid().hex}" for _ in range(3))
            active_commitment = _active_permit_commitment_from_assessment(
                assessment, conflict_domain_ref=locked.conflict_domain_ref,
            )
            values = dict(
                permit_id=permit_id, risk_assessment_id=assessment.risk_assessment_id,
                process_instance_id=self.__process_instance_id,
                normal_writer_session_id=normal_writer_session_id,
                conflict_domain_ref=locked.conflict_domain_ref, operation_kind=assessment.operation_kind,
                request_id=assessment.request_id, candidate_request_sha256=assessment.candidate_request_sha256,
                candidate_economic_sha256=assessment.candidate_economic_sha256,
                risk_config_sha256=assessment.risk_config_sha256,
                market_data_snapshot_sha256=assessment.market_data_snapshot_sha256,
                market_data_freshness_identity_sha256=assessment.market_data_freshness_identity_sha256,
                reconciliation_snapshot_sha256=assessment.reconciliation_snapshot_sha256,
                reconciliation_freshness_identity_sha256=assessment.reconciliation_freshness_identity_sha256,
                risk_state_epoch=assessment.risk_state_epoch,
                initial_trusted_sequence=tail.sequence, initial_trusted_hash=tail.event_hash,
                initial_ledger_sequence=tail.sequence, initial_ledger_hash=tail.event_hash,
                intent_event_id=stage_ids[0], prepared_event_id=stage_ids[1], send_boundary_event_id=stage_ids[2],
                issued_at_utc=canonical_timestamp(self.__wall()), issued_monotonic_ns=now,
                freshness_deadline_monotonic_ns=assessment.freshness_deadline_monotonic_ns,
                private_gate_instance_identity=self.__identity,
                **active_commitment,
            )
            permit = NormalWriterPermit(_PERMIT_CONSTRUCTION_KEY, **values)
            progress = NormalWriterPermitProgress(permit_id, PermitStage.INTENT, tail.sequence, tail.event_hash, tail.sequence, tail.event_hash, now, 0)
            self.__contexts[permit_id] = _PermitContext(
                permit, progress, locked, MappingProxyType(dict(intent_payload)),
                MappingProxyType(dict(prepared_payload)), execution_attempt_id,
            )
            return permit

    def _context(self, permit: NormalWriterPermit) -> _PermitContext:
        if type(permit) is not NormalWriterPermit or permit.private_gate_instance_identity is not self.__identity or permit.process_instance_id != self.__process_instance_id:
            raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
        context = self.__contexts.get(permit.permit_id)
        if context is None or context.permit is not permit:
            raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
        return context

    def progress_snapshot(self, permit: NormalWriterPermit) -> Mapping[str, object]:
        with self.__mutex:
            progress = self._context(permit).progress
            return MappingProxyType({field.name: getattr(progress, field.name) for field in fields(progress)})

    def _advance(
        self,
        permit: NormalWriterPermit,
        locked: LockedLedger,
        expected_stage: PermitStage,
        event_type: EventType,
        payload: Mapping[str, object],
        event_id: str,
        next_stage: PermitStage,
        *,
        execution_attempt_id: str | None,
    ) -> None:
        with self.__mutex:
            context = self._context(permit)
            progress = context.progress
            if self.__hard_halt_requested or progress.stage is not expected_stage:
                progress.stage = PermitStage.INVALIDATED
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_STAGE_MISMATCH)
            now = self.__monotonic()
            if now < progress.last_monotonic_ns:
                progress.stage = PermitStage.INVALIDATED
                raise RiskControlError(RiskControlCode.CLOCK_REGRESSION)
            if now > permit.freshness_deadline_monotonic_ns:
                progress.stage = PermitStage.INVALIDATED
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_EXPIRED)
            tail = locked.events[-1]
            if (tail.sequence, tail.event_hash) != (progress.expected_trusted_sequence, progress.expected_trusted_hash) or (locked.authority_row.trusted_sequence, locked.authority_row.trusted_event_hash) != (tail.sequence, tail.event_hash):
                progress.stage = PermitStage.INVALIDATED
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL)
            timestamp = canonical_timestamp(self.__wall())
            result = locked.append_batch((EventInput(event_type, payload, permit.normal_writer_session_id, payload.get("incident_id") if type(payload.get("incident_id")) is str else None, execution_attempt_id, event_id=event_id, recorded_at_utc=timestamp),))
            persisted = result.events[-1]
            if (
                persisted.sequence != tail.sequence + 1
                or persisted.previous_event_hash != tail.event_hash
                or persisted.event_id != event_id
                or persisted.execution_attempt_id != execution_attempt_id
            ):
                progress.stage = PermitStage.INVALIDATED
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL)
            progress.stage = next_stage
            progress.expected_trusted_sequence = persisted.sequence
            progress.expected_trusted_hash = persisted.event_hash
            progress.expected_ledger_sequence = persisted.sequence
            progress.expected_ledger_hash = persisted.event_hash
            progress.last_monotonic_ns = now

    def persist_intent(self, permit: NormalWriterPermit, locked: LockedLedger) -> None:
        context = self._context(permit)
        self._advance(
            permit, locked, PermitStage.INTENT, EventType.EXECUTION_INTENT_RECORDED, context.intent_payload,
            permit.intent_event_id, PermitStage.PREPARED, execution_attempt_id=context.execution_attempt_id,
        )

    def persist_prepared(self, permit: NormalWriterPermit, locked: LockedLedger) -> None:
        context = self._context(permit)
        self._advance(
            permit, locked, PermitStage.PREPARED, EventType.REQUEST_PREPARED, context.prepared_payload,
            permit.prepared_event_id, PermitStage.SEND_BOUNDARY, execution_attempt_id=context.execution_attempt_id,
        )

    def persist_send_boundary(self, permit: NormalWriterPermit, locked: LockedLedger) -> None:
        context = self._context(permit)
        boundary = {
            "request_id": permit.request_id,
            "operation_name": context.prepared_payload["operation_name"],
            "prepared_request_sha256": context.prepared_payload["prepared_request_sha256"],
            "write_ambiguity_rule": "WRITE_MAY_HAVE_BEEN_SENT_AFTER_THIS_COMMIT",
        }
        self._advance(
            permit, locked, PermitStage.SEND_BOUNDARY, EventType.WRITE_SEND_BOUNDARY_ENTERED, boundary,
            permit.send_boundary_event_id, PermitStage.CONSUMED, execution_attempt_id=None,
        )

    def invoke_transport(self, permit: NormalWriterPermit, transport: Callable[[object], object], request: object) -> object:
        with self.__mutex:
            context = self._context(permit)
            progress = context.progress
            if self.__hard_halt_requested or progress.stage is not PermitStage.CONSUMED:
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
            locked = context.locked
            if getattr(locked, "closed", False):
                progress.stage = PermitStage.INVALIDATED
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL)
            projection = locked.projection()
            tail = locked.events[-1]
            if (
                projection.active_writer_session_id != permit.normal_writer_session_id
                or projection.risk_control_state != "WRITER_ELIGIBLE"
                or projection.risk_state_epoch != permit.risk_state_epoch
                or getattr(projection, "active_risk_config_sha256", None) != permit.risk_config_sha256
                or (tail.sequence, tail.event_hash)
                != (progress.expected_trusted_sequence, progress.expected_trusted_hash)
                or (locked.authority_row.trusted_sequence, locked.authority_row.trusted_event_hash)
                != (tail.sequence, tail.event_hash)
            ):
                progress.stage = PermitStage.INVALIDATED
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_UNEXPECTED_TAIL)
            if progress.transport_invocation_count != 0:
                raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_ALREADY_CONSUMED)
            progress.transport_invocation_count = 1
        return transport(request)

    def latch_hard_halt(self) -> None:
        with self.__mutex:
            self.__hard_halt_requested = True
            for context in self.__contexts.values():
                if context.progress.transport_invocation_count == 0:
                    context.progress.stage = PermitStage.INVALIDATED

    def persist_case_a_halt(
        self,
        *,
        locked: LockedLedger,
        normal_writer_session_id: str,
        risk_config_sha256: str | None,
    ) -> Mapping[str, object]:
        self.latch_hard_halt()
        projection = locked.projection()
        if projection.active_writer_session_id != normal_writer_session_id or projection.risk_control_state != "WRITER_ELIGIBLE":
            raise RiskControlError(RiskControlCode.HALT_PERSISTENCE_FAILED)
        previous = locked.events[-1]
        payload = {
            "previous_state": "WRITER_ELIGIBLE", "new_state": "HALTED", "cause": "HARD_SAFETY_VIOLATION",
            "risk_state_epoch_before": projection.risk_state_epoch,
            "risk_state_epoch_after": projection.risk_state_epoch + 1,
            "risk_config_sha256": risk_config_sha256,
            "related_emergency_action_id": None, "related_release_id": None,
            "predecessor_state_event_id": next((event.event_id for event in reversed(locked.events) if event.event_type is EventType.RISK_CONTROL_STATE_CHANGED), None),
            "observed_authority_trusted_sequence": previous.sequence,
            "observed_authority_trusted_hash": previous.event_hash,
            "observed_ledger_terminal_sequence": previous.sequence,
            "observed_ledger_terminal_hash": previous.event_hash,
        }
        try:
            result = locked.append_batch((EventInput(EventType.RISK_CONTROL_STATE_CHANGED, payload, normal_writer_session_id),))
        except LedgerError as exc:
            raise RiskControlError(RiskControlCode.HALT_PERSISTENCE_FAILED) from exc
        halt_event = result.events[-1]
        if (locked.authority_row.trusted_sequence, locked.authority_row.trusted_event_hash) != (halt_event.sequence, halt_event.event_hash):
            raise RiskControlError(RiskControlCode.HALT_PERSISTENCE_FAILED)
        end_writer_session(locked, writer_session_id=normal_writer_session_id)
        return MappingProxyType({"halt_event_id": halt_event.event_id, "halt_sequence": halt_event.sequence, "locks_released": True})


class NormalWriteAdapter:
    """Only supported normal transport surface: exact permit plus bound request."""

    __slots__ = ("__gate", "__transport")

    def __init__(self, gate: WriterEligibilityGate, transport: Callable[[object], object]) -> None:
        if type(gate) is not WriterEligibilityGate or not callable(transport):
            raise RiskControlError(RiskControlCode.NORMAL_WRITER_PERMIT_INVALID)
        self.__gate = gate
        self.__transport = transport

    def invoke(self, permit: NormalWriterPermit, request: object) -> object:
        return self.__gate.invoke_transport(permit, self.__transport, request)


HISTORICAL_INCIDENT_CANCEL_TARGET = None
HISTORICAL_INCIDENT_WRITER_RELEASE_ELIGIBLE = False
HISTORICAL_UNRESOLVED_EXPOSURE = UNKNOWN_UNBOUNDED


__all__ = [
    "ACCOUNT_AGGREGATE_IDENTITY_FIELDS", "ACCOUNT_AGGREGATE_SCHEMA_ID",
    "ACCOUNT_AGGREGATE_UNIVERSE_COMPLETE", "AccountAggregateAuthorityExpectationV1",
    "build_account_aggregate_authority_expectation", "require_account_aggregate_identity",
    "AccountAggregateInputV1", "AccountAggregateSnapshotV1", "AccountAggregateTotalsV1",
    "ProjectedAccountAggregateV1", "account_aggregate_current_state_within_limits",
    "account_aggregate_snapshot_preimage", "build_account_aggregate_snapshot",
    "compute_account_aggregate_totals", "enforce_account_aggregate_limits",
    "project_account_aggregate",
    "AccountRiskLimits", "CandidateOrderV1", "EconomicFillV1", "FlowRiskLimits",
    "FreshnessRegistry", "FreshnessStampV1", "HISTORICAL_INCIDENT_CANCEL_TARGET",
    "HISTORICAL_INCIDENT_WRITER_RELEASE_ELIGIBLE", "HISTORICAL_UNRESOLVED_EXPOSURE",
    "MarketEconomicState", "NormalWriteAdapter", "NormalWriterPermit",
    "NormalWriterPermitProgress", "OrderbookReferenceV1", "PerMarketRiskLimits",
    "PerOrderRiskLimits", "PermitStage", "PriceRangeV1", "ProjectedRiskV1",
    "RiskControlCode", "RiskControlError", "RiskLimitConfigV1", "StateIntegrityLimits",
    "UNKNOWN_UNBOUNDED", "VenueDefensePolicy", "WorkingOrderV1", "WriterEligibilityAssessment",
    "WriterEligibilityGate", "build_orderbook_reference", "compute_market_economic_state",
    "enforce_projected_limits", "freshness_age_ms", "price_reasonable",
    "project_candidate_risk", "validate_price_ranges",
    "compute_permit_domain_commitment_sha256",
]
