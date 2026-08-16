"""Pure deterministic minimal two-sided Kalshi Demo market-maker strategy.

Implements ``KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_SPEC_03.md`` sections
8-22: strategy configuration, the authoritative strategy input contract, the
exact validated price-grid helpers, the minimal two-sided quote algorithm,
non-circular inventory evaluation, and the ``QuotePlanV1`` output contract.

This module owns no credentials, signing, sockets, transport callables,
ledger/authority connections, writer-lock acquisition, or emergency-release
authority. It consumes validated immutable inputs and returns immutable
strategy intent only. ``QuotePlanV1`` is never writer authority.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from arb.execution_ledger import canonical_json_bytes, sha256_hex
from arb.venues.kalshi.orderbook import KalshiNativeOrderBookSnapshot
from arb.venues.kalshi.risk_control import (
    FreshnessStampV1,
    MarketEconomicState,
    PriceRangeV1,
    RiskControlCode,
    RiskControlError,
    RiskLimitConfigV1,
    build_orderbook_reference,
    freshness_age_ms,
    price_reasonable,
    validate_price_ranges,
)

ZERO = Decimal("0")
ONE = Decimal("1.0000")
UNKNOWN_UNBOUNDED = "UNKNOWN_UNBOUNDED"
INVENTORY_THRESHOLD = Decimal("1.00")
QUOTE_QUANTITY = Decimal("1.00")

_STRATEGY_INSTANCE_ID_RE = re.compile(r"^mm_[0-9a-f]{32}$")
_QUOTE_GENERATION_ID_RE = re.compile(r"^qg_[0-9a-f]{32}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_CONFIG_DOMAIN = b"ARB_KALSHI_MINIMAL_MM_CONFIG_V1\x00"
_PLAN_INPUT_DOMAIN = b"ARB_KALSHI_MINIMAL_MM_PLAN_INPUT_V1\x00"
_QUOTE_PLAN_DOMAIN = b"ARB_KALSHI_MINIMAL_MM_QUOTE_PLAN_V1\x00"
_QUOTE_GENERATION_DOMAIN = b"ARB_KALSHI_MINIMAL_MM_QUOTE_GENERATION_V1\x00"
_PRICE_GRID_DOMAIN = b"ARB_KALSHI_MINIMAL_MM_PRICE_GRID_V1\x00"
_ECONOMIC_TRUTH_DOMAIN = b"ARB_KALSHI_MINIMAL_MM_ECONOMIC_TRUTH_V1\x00"
_FRESHNESS_IDENTITY_DOMAIN = b"ARB_KALSHI_MINIMAL_MM_FRESHNESS_IDENTITY_V1\x00"

_FIXED_INVENTORY_THRESHOLD = Decimal("1.00")
_FIXED_KEEP_REPRICE_DISTANCE = 2
_FIXED_MAX_TARGET_EXPOSURE = Decimal("1.000000")
_FIXED_LOCKED_BOOK_POLICY = "SUPPRESS_BOTH"
_FIXED_QUOTE_TIF_POLICY = "ACCEPTED_GTC_POST_ONLY_LIFECYCLE"


class MarketMakerFailure(enum.StrEnum):
    MM_INPUT_INVALID = "MM_INPUT_INVALID"
    MM_BOOK_STALE = "MM_BOOK_STALE"
    MM_RECONCILIATION_STALE = "MM_RECONCILIATION_STALE"
    MM_RECONCILIATION_INCOMPLETE = "MM_RECONCILIATION_INCOMPLETE"
    MM_FILL_HISTORY_INCOMPLETE = "MM_FILL_HISTORY_INCOMPLETE"
    MM_FILL_IDENTITY_CONFLICT = "MM_FILL_IDENTITY_CONFLICT"
    MM_UNKNOWN_INVENTORY = "MM_UNKNOWN_INVENTORY"
    MM_SIGNED_INVENTORY_TRUTH_MISMATCH = "MM_SIGNED_INVENTORY_TRUTH_MISMATCH"
    MM_UNKNOWN_INVENTORY_SHAPE_INVALID = "MM_UNKNOWN_INVENTORY_SHAPE_INVALID"
    MM_UNKNOWN_UNBOUNDED_EXPOSURE = "MM_UNKNOWN_UNBOUNDED_EXPOSURE"
    MM_PRICE_GRID_INVALID = "MM_PRICE_GRID_INVALID"
    MM_STRATEGY_ORDER_OWNERSHIP_CONFLICT = "MM_STRATEGY_ORDER_OWNERSHIP_CONFLICT"
    MM_UNRESOLVED_STRATEGY_WRITE = "MM_UNRESOLVED_STRATEGY_WRITE"
    MM_PLAN_STALE = "MM_PLAN_STALE"
    MM_CONFIG_HASH_MISMATCH = "MM_CONFIG_HASH_MISMATCH"


class ReasonCode(enum.StrEnum):
    TWO_SIDED_NEUTRAL = "TWO_SIDED_NEUTRAL"
    LOWER_SUPPRESSED_INVENTORY = "LOWER_SUPPRESSED_INVENTORY"
    UPPER_SUPPRESSED_INVENTORY = "UPPER_SUPPRESSED_INVENTORY"
    LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE = "LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE"
    UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE = "UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE"
    LOWER_SUPPRESSED_PRICE_REASONABILITY = "LOWER_SUPPRESSED_PRICE_REASONABILITY"
    UPPER_SUPPRESSED_PRICE_REASONABILITY = "UPPER_SUPPRESSED_PRICE_REASONABILITY"
    BOTH_SUPPRESSED_LOCKED_BOOK = "BOTH_SUPPRESSED_LOCKED_BOOK"
    BOTH_SUPPRESSED_TARGET_EXPOSURE = "BOTH_SUPPRESSED_TARGET_EXPOSURE"
    INPUT_BOOK_INVALID = "INPUT_BOOK_INVALID"
    INPUT_BOOK_STALE = "INPUT_BOOK_STALE"
    INPUT_RECONCILIATION_STALE = "INPUT_RECONCILIATION_STALE"
    INPUT_RECONCILIATION_INCOMPLETE = "INPUT_RECONCILIATION_INCOMPLETE"
    INPUT_FILL_HISTORY_INCOMPLETE = "INPUT_FILL_HISTORY_INCOMPLETE"
    INPUT_FILL_IDENTITY_CONFLICT = "INPUT_FILL_IDENTITY_CONFLICT"
    INPUT_INVENTORY_UNKNOWN = "INPUT_INVENTORY_UNKNOWN"
    INPUT_SIGNED_INVENTORY_TRUTH_MISMATCH = "INPUT_SIGNED_INVENTORY_TRUTH_MISMATCH"
    INPUT_UNKNOWN_INVENTORY_SHAPE_INVALID = "INPUT_UNKNOWN_INVENTORY_SHAPE_INVALID"
    INPUT_EXPOSURE_UNKNOWN_UNBOUNDED = "INPUT_EXPOSURE_UNKNOWN_UNBOUNDED"
    INPUT_RISK_STATE_NOT_WRITER_ELIGIBLE = "INPUT_RISK_STATE_NOT_WRITER_ELIGIBLE"
    INPUT_RISK_CONFIG_MISMATCH = "INPUT_RISK_CONFIG_MISMATCH"
    INPUT_RISK_EPOCH_MISMATCH = "INPUT_RISK_EPOCH_MISMATCH"
    INPUT_PRICE_GRID_INVALID = "INPUT_PRICE_GRID_INVALID"
    INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT = "INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT"
    INPUT_UNRESOLVED_STRATEGY_WRITE = "INPUT_UNRESOLVED_STRATEGY_WRITE"
    INPUT_PROCESS_FRESHNESS_INVALID = "INPUT_PROCESS_FRESHNESS_INVALID"


class MarketMakerInputError(RuntimeError):
    """Raised only for structurally contradictory input that MUST be
    rejected before any deterministic identity (economic-truth hash,
    plan-input hash, or plan hash) may be accepted or formed."""

    def __init__(self, code: MarketMakerFailure, *, reason_code: ReasonCode | str | None = None) -> None:
        self.code = code
        self.reason_code = str(reason_code) if reason_code is not None else code.value
        super().__init__(self.reason_code)


class QuoteSlot(enum.StrEnum):
    LOWER_YES_BID = "LOWER_YES_BID"
    UPPER_YES_ASK = "UPPER_YES_ASK"


_SLOT_VENUE_SIDE: Mapping[QuoteSlot, str] = {
    QuoteSlot.LOWER_YES_BID: "bid",
    QuoteSlot.UPPER_YES_ASK: "ask",
}
_SLOT_OUTCOME_SIDE: Mapping[QuoteSlot, str] = {
    QuoteSlot.LOWER_YES_BID: "YES",
    QuoteSlot.UPPER_YES_ASK: "NO",
}


class SlotClassification(enum.StrEnum):
    ABSENT = "ABSENT"
    ACTIVE_EXACT = "ACTIVE_EXACT"
    TERMINAL_RECONCILED = "TERMINAL_RECONCILED"
    UNRESOLVED_OR_AMBIGUOUS = "UNRESOLVED_OR_AMBIGUOUS"
    CONFLICT = "CONFLICT"


class SignedInventoryState(enum.StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class Completeness(enum.StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class PlanClassification(enum.StrEnum):
    VALID_DESIRED_STATE = "VALID_DESIRED_STATE"
    NO_NEW_QUOTE_PLAN = "NO_NEW_QUOTE_PLAN"


# ---------------------------------------------------------------------------
# MM-CFG-001..003 — strategy configuration
# ---------------------------------------------------------------------------


def _config_object(fields: Mapping[str, object]) -> dict:
    return {
        "schema_revision": fields["schema_revision"],
        "strategy_instance_id": fields["strategy_instance_id"],
        "market_ticker": fields["market_ticker"],
        "quote_quantity": fields["quote_quantity"],
        "inventory_suppress_threshold_contracts": fields["inventory_suppress_threshold_contracts"],
        "minimum_spread_usd": fields["minimum_spread_usd"],
        "keep_reprice_distance_grid_steps": fields["keep_reprice_distance_grid_steps"],
        "max_strategy_target_working_exposure_usd": fields["max_strategy_target_working_exposure_usd"],
        "locked_book_policy": fields["locked_book_policy"],
        "quote_tif_policy": fields["quote_tif_policy"],
    }


def _compute_config_sha256(fields: Mapping[str, object]) -> str:
    return sha256_hex(_CONFIG_DOMAIN + canonical_json_bytes(_config_object(fields)))


@dataclass(frozen=True, slots=True)
class MinimalMarketMakerConfigV1:
    schema_revision: int
    strategy_instance_id: str
    market_ticker: str
    quote_quantity: Decimal
    inventory_suppress_threshold_contracts: Decimal
    minimum_spread_usd: Decimal
    keep_reprice_distance_grid_steps: int
    max_strategy_target_working_exposure_usd: Decimal
    locked_book_policy: str
    quote_tif_policy: str
    config_sha256: str

    def __post_init__(self) -> None:
        if type(self.schema_revision) is not int or self.schema_revision != 1:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.strategy_instance_id) is not str or _STRATEGY_INSTANCE_ID_RE.fullmatch(self.strategy_instance_id) is None:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.market_ticker) is not str or not self.market_ticker:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.quote_quantity) is not Decimal or self.quote_quantity != QUOTE_QUANTITY:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if (
            type(self.inventory_suppress_threshold_contracts) is not Decimal
            or self.inventory_suppress_threshold_contracts != _FIXED_INVENTORY_THRESHOLD
        ):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.minimum_spread_usd) is not Decimal or not self.minimum_spread_usd.is_finite():
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if not (ZERO < self.minimum_spread_usd < Decimal("1")):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.minimum_spread_usd != self.minimum_spread_usd.quantize(Decimal("0.0001")):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.keep_reprice_distance_grid_steps != _FIXED_KEEP_REPRICE_DISTANCE:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if (
            type(self.max_strategy_target_working_exposure_usd) is not Decimal
            or self.max_strategy_target_working_exposure_usd != _FIXED_MAX_TARGET_EXPOSURE
        ):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.locked_book_policy != _FIXED_LOCKED_BOOK_POLICY:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.quote_tif_policy != _FIXED_QUOTE_TIF_POLICY:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        recomputed = _compute_config_sha256(_config_object(
            {
                "schema_revision": self.schema_revision,
                "strategy_instance_id": self.strategy_instance_id,
                "market_ticker": self.market_ticker,
                "quote_quantity": self.quote_quantity,
                "inventory_suppress_threshold_contracts": self.inventory_suppress_threshold_contracts,
                "minimum_spread_usd": self.minimum_spread_usd,
                "keep_reprice_distance_grid_steps": self.keep_reprice_distance_grid_steps,
                "max_strategy_target_working_exposure_usd": self.max_strategy_target_working_exposure_usd,
                "locked_book_policy": self.locked_book_policy,
                "quote_tif_policy": self.quote_tif_policy,
            }
        ))
        if recomputed != self.config_sha256:
            raise MarketMakerInputError(MarketMakerFailure.MM_CONFIG_HASH_MISMATCH)


def build_market_maker_config(
    *, strategy_instance_id: str, market_ticker: str, minimum_spread_usd: Decimal,
) -> MinimalMarketMakerConfigV1:
    fields = {
        "schema_revision": 1,
        "strategy_instance_id": strategy_instance_id,
        "market_ticker": market_ticker,
        "quote_quantity": QUOTE_QUANTITY,
        "inventory_suppress_threshold_contracts": _FIXED_INVENTORY_THRESHOLD,
        "minimum_spread_usd": minimum_spread_usd,
        "keep_reprice_distance_grid_steps": _FIXED_KEEP_REPRICE_DISTANCE,
        "max_strategy_target_working_exposure_usd": _FIXED_MAX_TARGET_EXPOSURE,
        "locked_book_policy": _FIXED_LOCKED_BOOK_POLICY,
        "quote_tif_policy": _FIXED_QUOTE_TIF_POLICY,
    }
    config_sha256 = _compute_config_sha256(fields)
    return MinimalMarketMakerConfigV1(**fields, config_sha256=config_sha256)


# ---------------------------------------------------------------------------
# MM-IN-004..006 — MarketMakerEconomicTruthV1
# ---------------------------------------------------------------------------


def _economic_truth_object_exact(fields: Mapping[str, object]) -> dict:
    state = fields["market_economic_state"]
    if state is not None:
        state_object = {
            "filled_exposure_usd": state.filled_exposure_usd,
            "signed_net_position": state.signed_net_position,
            "working_exposure_usd": state.working_exposure_usd,
            "working_bid_quantity": state.working_bid_quantity,
            "working_ask_quantity": state.working_ask_quantity,
            "working_order_count": state.working_order_count,
            "working_contracts": state.working_contracts,
        }
    else:
        state_object = None
    return {
        "schema_revision": fields["schema_revision"],
        "signed_inventory_state": fields["signed_inventory_state"],
        "signed_net_position_contracts": fields["signed_net_position_contracts"],
        "unresolved_write_exposure_usd": fields["unresolved_write_exposure_usd"],
        "unresolved_write_request_ids": list(fields["unresolved_write_request_ids"]),
        "protected_unresolved_legacy_write_count": fields["protected_unresolved_legacy_write_count"],
        "unresolved_write_count": fields["unresolved_write_count"],
        "fill_history_completeness": fields["fill_history_completeness"],
        "fill_identity_conflict_ids": list(fields["fill_identity_conflict_ids"]),
        "reconciliation_completeness": fields["reconciliation_completeness"],
        "market_economic_state": state_object,
    }


def _compute_economic_truth_sha256(fields: Mapping[str, object]) -> str:
    return sha256_hex(_ECONOMIC_TRUTH_DOMAIN + canonical_json_bytes(_economic_truth_object_exact(fields)))


def _sorted_unique_tuple(value: object) -> bool:
    return type(value) is tuple and all(type(item) is str for item in value) and list(value) == sorted(set(value))


@dataclass(frozen=True, slots=True)
class MarketMakerEconomicTruthV1:
    schema_revision: int
    signed_inventory_state: str
    signed_net_position_contracts: Decimal | None
    unresolved_write_exposure_usd: Decimal | str
    unresolved_write_request_ids: tuple[str, ...]
    protected_unresolved_legacy_write_count: int
    unresolved_write_count: int
    fill_history_completeness: str
    fill_identity_conflict_ids: tuple[str, ...]
    reconciliation_completeness: str
    market_economic_state: MarketEconomicState | None
    economic_truth_sha256: str

    def __post_init__(self) -> None:
        if type(self.schema_revision) is not int or self.schema_revision != 1:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.signed_inventory_state not in (SignedInventoryState.KNOWN.value, SignedInventoryState.UNKNOWN.value):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        # 1: exact type/union-shape validation; 2: structural invariants.
        if type(self.unresolved_write_exposure_usd) is not str or self.unresolved_write_exposure_usd != UNKNOWN_UNBOUNDED:
            if type(self.unresolved_write_exposure_usd) is not Decimal or not self.unresolved_write_exposure_usd.is_finite() or self.unresolved_write_exposure_usd < ZERO:
                raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if not _sorted_unique_tuple(self.unresolved_write_request_ids):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.protected_unresolved_legacy_write_count) is not int or self.protected_unresolved_legacy_write_count < 0:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if (
            type(self.unresolved_write_count) is not int
            or self.unresolved_write_count != len(self.unresolved_write_request_ids) + self.protected_unresolved_legacy_write_count
        ):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.fill_history_completeness not in (Completeness.COMPLETE.value, Completeness.INCOMPLETE.value):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if not _sorted_unique_tuple(self.fill_identity_conflict_ids):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.reconciliation_completeness not in (Completeness.COMPLETE.value, Completeness.INCOMPLETE.value):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        # 3/4: KNOWN/UNKNOWN union invariant, including the mandatory
        # signed-position equality, evaluated before any hash acceptance.
        if self.signed_inventory_state == SignedInventoryState.KNOWN.value:
            if (
                type(self.signed_net_position_contracts) is not Decimal
                or not self.signed_net_position_contracts.is_finite()
                or type(self.market_economic_state) is not MarketEconomicState
                or type(self.market_economic_state.signed_net_position) is not Decimal
                or not self.market_economic_state.signed_net_position.is_finite()
            ):
                raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
            if self.signed_net_position_contracts != self.market_economic_state.signed_net_position:
                raise MarketMakerInputError(
                    MarketMakerFailure.MM_SIGNED_INVENTORY_TRUTH_MISMATCH,
                    reason_code=ReasonCode.INPUT_SIGNED_INVENTORY_TRUTH_MISMATCH,
                )
        else:
            if self.signed_net_position_contracts is not None or self.market_economic_state is not None:
                raise MarketMakerInputError(
                    MarketMakerFailure.MM_UNKNOWN_INVENTORY_SHAPE_INVALID,
                    reason_code=ReasonCode.INPUT_UNKNOWN_INVENTORY_SHAPE_INVALID,
                )
        # 4/5/6: only now may the record be serialized/hashed and its
        # supplied identity accepted.
        recomputed = _compute_economic_truth_sha256(
            {
                "schema_revision": self.schema_revision,
                "signed_inventory_state": self.signed_inventory_state,
                "signed_net_position_contracts": self.signed_net_position_contracts,
                "unresolved_write_exposure_usd": self.unresolved_write_exposure_usd,
                "unresolved_write_request_ids": self.unresolved_write_request_ids,
                "protected_unresolved_legacy_write_count": self.protected_unresolved_legacy_write_count,
                "unresolved_write_count": self.unresolved_write_count,
                "fill_history_completeness": self.fill_history_completeness,
                "fill_identity_conflict_ids": self.fill_identity_conflict_ids,
                "reconciliation_completeness": self.reconciliation_completeness,
                "market_economic_state": self.market_economic_state,
            }
        )
        if recomputed != self.economic_truth_sha256:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)

    @property
    def is_fail_closed(self) -> bool:
        return (
            self.signed_inventory_state != SignedInventoryState.KNOWN.value
            or self.unresolved_write_exposure_usd == UNKNOWN_UNBOUNDED
            or self.unresolved_write_count > 0
            or self.protected_unresolved_legacy_write_count > 0
            or self.fill_history_completeness != Completeness.COMPLETE.value
            or bool(self.fill_identity_conflict_ids)
            or self.reconciliation_completeness != Completeness.COMPLETE.value
        )


def build_economic_truth(
    *,
    signed_inventory_state: str,
    unresolved_write_exposure_usd: Decimal | str,
    fill_history_completeness: str,
    reconciliation_completeness: str,
    signed_net_position_contracts: Decimal | None = None,
    market_economic_state: MarketEconomicState | None = None,
    unresolved_write_request_ids: tuple[str, ...] = (),
    protected_unresolved_legacy_write_count: int = 0,
    fill_identity_conflict_ids: tuple[str, ...] = (),
) -> MarketMakerEconomicTruthV1:
    unresolved_write_count = len(unresolved_write_request_ids) + protected_unresolved_legacy_write_count
    fields = {
        "schema_revision": 1,
        "signed_inventory_state": signed_inventory_state,
        "signed_net_position_contracts": signed_net_position_contracts,
        "unresolved_write_exposure_usd": unresolved_write_exposure_usd,
        "unresolved_write_request_ids": tuple(unresolved_write_request_ids),
        "protected_unresolved_legacy_write_count": protected_unresolved_legacy_write_count,
        "unresolved_write_count": unresolved_write_count,
        "fill_history_completeness": fill_history_completeness,
        "fill_identity_conflict_ids": tuple(fill_identity_conflict_ids),
        "reconciliation_completeness": reconciliation_completeness,
        "market_economic_state": market_economic_state,
    }
    economic_truth_sha256 = _compute_economic_truth_sha256(fields)
    return MarketMakerEconomicTruthV1(**fields, economic_truth_sha256=economic_truth_sha256)


# ---------------------------------------------------------------------------
# MM-IN-007 — strategy-owned working orders
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyOwnedWorkingOrderV1:
    strategy_instance_id: str
    market_ticker: str
    quote_slot: str
    quote_generation_id: str
    client_order_id: str
    venue_order_id: str
    venue_side: str
    outcome_side: str
    yes_price: Decimal
    initial_quantity: Decimal
    remaining_quantity: Decimal
    authoritative_status: str
    source_intent_event_id: str
    source_order_identity_binding_event_id: str
    latest_order_observation_event_id: str
    ownership_basis_sha256: str

    def __post_init__(self) -> None:
        if self.quote_slot not in (QuoteSlot.LOWER_YES_BID.value, QuoteSlot.UPPER_YES_ASK.value):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        slot = QuoteSlot(self.quote_slot)
        if self.venue_side != _SLOT_VENUE_SIDE[slot] or self.outcome_side != _SLOT_OUTCOME_SIDE[slot]:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.authoritative_status != "resting":
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.remaining_quantity) is not Decimal or self.remaining_quantity <= ZERO:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.initial_quantity) is not Decimal or self.initial_quantity <= ZERO:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if type(self.yes_price) is not Decimal or not (ZERO <= self.yes_price <= ONE):
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        for value in (
            self.strategy_instance_id, self.market_ticker, self.quote_generation_id,
            self.client_order_id, self.venue_order_id,
        ):
            if type(value) is not str or not value:
                raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)


# ---------------------------------------------------------------------------
# MM-GRID — exact grid helper definitions and price-grid identity
# ---------------------------------------------------------------------------


def _range_floor_le(range_: PriceRangeV1, x: Decimal) -> Decimal | None:
    if x < range_.start:
        return None
    upper = min(x, range_.end)
    steps = int((upper - range_.start) // range_.step)
    return range_.start + steps * range_.step


def _range_ceil_ge(range_: PriceRangeV1, x: Decimal) -> Decimal | None:
    if x > range_.end:
        return None
    lower = max(x, range_.start)
    steps = int((lower - range_.start) // range_.step)
    candidate = range_.start + steps * range_.step
    if candidate < lower:
        candidate += range_.step
    if candidate > range_.end:
        return None
    return candidate


def grid_floor(x: Decimal, ranges: Sequence[PriceRangeV1]) -> Decimal | None:
    best: Decimal | None = None
    for range_ in ranges:
        candidate = _range_floor_le(range_, x)
        if candidate is not None and (best is None or candidate > best):
            best = candidate
    return best


def grid_ceil(x: Decimal, ranges: Sequence[PriceRangeV1]) -> Decimal | None:
    best: Decimal | None = None
    for range_ in ranges:
        candidate = _range_ceil_ge(range_, x)
        if candidate is not None and (best is None or candidate < best):
            best = candidate
    return best


def grid_prev(g: Decimal, ranges: Sequence[PriceRangeV1]) -> Decimal | None:
    best: Decimal | None = None
    for range_ in ranges:
        if range_.start >= g:
            continue
        candidate = _range_floor_le(range_, g)
        if candidate is not None and candidate >= g:
            stepped_back = candidate - range_.step
            candidate = stepped_back if stepped_back >= range_.start else None
        if candidate is not None and candidate < g and (best is None or candidate > best):
            best = candidate
    return best


def grid_next(g: Decimal, ranges: Sequence[PriceRangeV1]) -> Decimal | None:
    best: Decimal | None = None
    for range_ in ranges:
        if range_.end <= g:
            continue
        candidate = _range_ceil_ge(range_, g)
        if candidate is not None and candidate <= g:
            stepped_forward = candidate + range_.step
            candidate = stepped_forward if stepped_forward <= range_.end else None
        if candidate is not None and candidate > g and (best is None or candidate < best):
            best = candidate
    return best


def grid_distance(a: Decimal, b: Decimal, ranges: Sequence[PriceRangeV1], *, limit: int = 10_000) -> int | None:
    if a == b:
        return 0
    forward = a < b
    current = a
    steps = 0
    while current != b:
        current = grid_next(current, ranges) if forward else grid_prev(current, ranges)
        if current is None:
            return None
        steps += 1
        if steps > limit:
            return None
    return steps


def _price_grid_object(ranges: Sequence[PriceRangeV1]) -> list:
    return [{"start": r.start, "end": r.end, "step": r.step} for r in ranges]


def compute_price_grid_sha256(ranges: Sequence[PriceRangeV1]) -> str:
    return sha256_hex(_PRICE_GRID_DOMAIN + canonical_json_bytes(_price_grid_object(ranges)))


def _validated_price_grid(ranges: Sequence[PriceRangeV1]) -> bool:
    try:
        probe = ranges[0].start if ranges else ZERO
        validate_price_ranges(probe, ranges)
    except RiskControlError:
        return False
    return True


def compute_mm_freshness_identity_sha256(stamp: FreshnessStampV1) -> str:
    """Exact Revision-05 whole-``FreshnessStampV1`` identity (not
    ``stamp.snapshot_sha256``, which identifies only the underlying data
    snapshot). Used for both ``book_freshness_identity_sha256`` and
    ``reconciliation_freshness_identity_sha256`` in the plan-input object."""

    if type(stamp) is not FreshnessStampV1:
        raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
    freshness_identity_object = {
        "process_instance_id": stamp.process_instance_id,
        "received_at_utc": stamp.received_at_utc,
        "received_monotonic_ns": stamp.received_monotonic_ns,
        "source_timestamp_kind": stamp.source_timestamp_kind,
        "source_timestamp_utc": stamp.source_timestamp_utc,
        "snapshot_sha256": stamp.snapshot_sha256,
    }
    return sha256_hex(_FRESHNESS_IDENTITY_DOMAIN + canonical_json_bytes(freshness_identity_object))


# ---------------------------------------------------------------------------
# MM-PLAN — QuotePlanV1 output contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DesiredQuoteV1:
    quote_slot: str
    venue_side: str
    outcome_side: str
    yes_price: Decimal
    quantity: Decimal
    quote_generation_id: str

    def __post_init__(self) -> None:
        slot = QuoteSlot(self.quote_slot)
        if self.venue_side != _SLOT_VENUE_SIDE[slot] or self.outcome_side != _SLOT_OUTCOME_SIDE[slot]:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if self.quantity != QUOTE_QUANTITY:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)
        if _QUOTE_GENERATION_ID_RE.fullmatch(self.quote_generation_id) is None:
            raise MarketMakerInputError(MarketMakerFailure.MM_INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class QuotePlanV1:
    schema_revision: int
    strategy_instance_id: str
    market_ticker: str
    strategy_config_sha256: str
    plan_input_sha256: str
    source_book_snapshot_sha256: str
    book_freshness_identity_sha256: str
    price_grid_sha256: str
    risk_control_state: str
    risk_state_epoch: int
    risk_config_sha256: str
    reconciliation_snapshot_sha256: str
    reconciliation_freshness_identity_sha256: str
    economic_truth_sha256: str
    signed_inventory_state: str
    signed_net_position_contracts: Decimal | None
    lower_quote: DesiredQuoteV1 | None
    upper_quote: DesiredQuoteV1 | None
    plan_classification: str
    reason_codes: tuple[str, ...]
    effective_at_utc: str
    not_after_monotonic_ns: int
    plan_sha256: str


# ---------------------------------------------------------------------------
# Strategy input contract and evaluation entry point (MM-IN, MM-REF,
# MM-QUOTE, MM-INV, MM-EXP, MM-PLAN)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarketMakerInputV1:
    strategy_config: MinimalMarketMakerConfigV1
    book_snapshot: KalshiNativeOrderBookSnapshot
    book_snapshot_sha256: str
    book_freshness: FreshnessStampV1
    price_ranges: tuple[PriceRangeV1, ...]
    price_grid_sha256: str
    risk_control_state: str
    risk_state_epoch: int
    risk_config: RiskLimitConfigV1
    risk_config_sha256: str
    reconciliation_snapshot_sha256: str
    reconciliation_freshness: FreshnessStampV1
    economic_truth: MarketMakerEconomicTruthV1
    strategy_working_orders: tuple[StrategyOwnedWorkingOrderV1, ...]
    slot_classifications: Mapping[str, str]
    process_instance_id: str
    now_monotonic_ns: int
    now_utc: str


def _working_order_for_slot(input_: MarketMakerInputV1, slot: QuoteSlot) -> StrategyOwnedWorkingOrderV1 | None:
    matches = [order for order in input_.strategy_working_orders if order.quote_slot == slot.value]
    if len(matches) != 1:
        return None
    return matches[0]


def _plan_input_object(input_: MarketMakerInputV1) -> dict:
    working_orders_sorted = sorted(input_.strategy_working_orders, key=lambda order: (order.quote_slot, order.venue_order_id))
    return {
        "schema_revision": 1,
        "strategy_config_sha256": input_.strategy_config.config_sha256,
        "market_ticker": input_.strategy_config.market_ticker,
        "book_snapshot_sha256": input_.book_snapshot_sha256,
        "book_freshness_identity_sha256": compute_mm_freshness_identity_sha256(input_.book_freshness),
        "price_grid_sha256": input_.price_grid_sha256,
        "risk_control_state": input_.risk_control_state,
        "risk_state_epoch": input_.risk_state_epoch,
        "risk_config_sha256": input_.risk_config_sha256,
        "reconciliation_snapshot_sha256": input_.reconciliation_snapshot_sha256,
        "reconciliation_freshness_identity_sha256": compute_mm_freshness_identity_sha256(input_.reconciliation_freshness),
        "economic_truth": _economic_truth_object_exact(
            {
                "schema_revision": input_.economic_truth.schema_revision,
                "signed_inventory_state": input_.economic_truth.signed_inventory_state,
                "signed_net_position_contracts": input_.economic_truth.signed_net_position_contracts,
                "unresolved_write_exposure_usd": input_.economic_truth.unresolved_write_exposure_usd,
                "unresolved_write_request_ids": input_.economic_truth.unresolved_write_request_ids,
                "protected_unresolved_legacy_write_count": input_.economic_truth.protected_unresolved_legacy_write_count,
                "unresolved_write_count": input_.economic_truth.unresolved_write_count,
                "fill_history_completeness": input_.economic_truth.fill_history_completeness,
                "fill_identity_conflict_ids": input_.economic_truth.fill_identity_conflict_ids,
                "reconciliation_completeness": input_.economic_truth.reconciliation_completeness,
                "market_economic_state": input_.economic_truth.market_economic_state,
            }
        ) | {"economic_truth_sha256": input_.economic_truth.economic_truth_sha256},
        "strategy_working_orders": [
            {
                "strategy_instance_id": order.strategy_instance_id,
                "market_ticker": order.market_ticker,
                "quote_slot": order.quote_slot,
                "quote_generation_id": order.quote_generation_id,
                "client_order_id": order.client_order_id,
                "venue_order_id": order.venue_order_id,
                "venue_side": order.venue_side,
                "outcome_side": order.outcome_side,
                "yes_price": order.yes_price,
                "initial_quantity": order.initial_quantity,
                "remaining_quantity": order.remaining_quantity,
                "authoritative_status": order.authoritative_status,
                "source_intent_event_id": order.source_intent_event_id,
                "source_order_identity_binding_event_id": order.source_order_identity_binding_event_id,
                "latest_order_observation_event_id": order.latest_order_observation_event_id,
                "ownership_basis_sha256": order.ownership_basis_sha256,
            }
            for order in working_orders_sorted
        ],
        "process_instance_id": input_.process_instance_id,
    }


def compute_plan_input_sha256(input_: MarketMakerInputV1) -> str:
    return sha256_hex(_PLAN_INPUT_DOMAIN + canonical_json_bytes(_plan_input_object(input_)))


def compute_quote_generation_id(
    *, strategy_instance_id: str, market_ticker: str, quote_slot: str, plan_input_sha256: str,
    venue_side: str, outcome_side: str, yes_price: Decimal, quantity: Decimal,
) -> str:
    obj = {
        "strategy_instance_id": strategy_instance_id,
        "market_ticker": market_ticker,
        "quote_slot": quote_slot,
        "plan_input_sha256": plan_input_sha256,
        "venue_side": venue_side,
        "outcome_side": outcome_side,
        "yes_price": yes_price,
        "quantity": quantity,
    }
    digest = sha256_hex(_QUOTE_GENERATION_DOMAIN + canonical_json_bytes(obj))
    return f"qg_{digest[:32]}"


def _plan_object(fields: Mapping[str, object]) -> dict:
    def quote_dict(quote: DesiredQuoteV1 | None) -> dict | None:
        if quote is None:
            return None
        return {
            "quote_slot": quote.quote_slot, "venue_side": quote.venue_side, "outcome_side": quote.outcome_side,
            "yes_price": quote.yes_price, "quantity": quote.quantity, "quote_generation_id": quote.quote_generation_id,
        }

    return {
        "schema_revision": fields["schema_revision"],
        "strategy_instance_id": fields["strategy_instance_id"],
        "market_ticker": fields["market_ticker"],
        "strategy_config_sha256": fields["strategy_config_sha256"],
        "plan_input_sha256": fields["plan_input_sha256"],
        "source_book_snapshot_sha256": fields["source_book_snapshot_sha256"],
        "book_freshness_identity_sha256": fields["book_freshness_identity_sha256"],
        "price_grid_sha256": fields["price_grid_sha256"],
        "risk_control_state": fields["risk_control_state"],
        "risk_state_epoch": fields["risk_state_epoch"],
        "risk_config_sha256": fields["risk_config_sha256"],
        "reconciliation_snapshot_sha256": fields["reconciliation_snapshot_sha256"],
        "reconciliation_freshness_identity_sha256": fields["reconciliation_freshness_identity_sha256"],
        "economic_truth_sha256": fields["economic_truth_sha256"],
        "signed_inventory_state": fields["signed_inventory_state"],
        "signed_net_position_contracts": fields["signed_net_position_contracts"],
        "lower_quote": quote_dict(fields["lower_quote"]),
        "upper_quote": quote_dict(fields["upper_quote"]),
        "plan_classification": fields["plan_classification"],
        "reason_codes": list(fields["reason_codes"]),
        "effective_at_utc": fields["effective_at_utc"],
        "not_after_monotonic_ns": fields["not_after_monotonic_ns"],
    }


def _compute_plan_sha256(fields: Mapping[str, object]) -> str:
    return sha256_hex(_QUOTE_PLAN_DOMAIN + canonical_json_bytes(_plan_object(fields)))


def evaluate_market_maker_input(input_: MarketMakerInputV1) -> QuotePlanV1:
    """Evaluate ``input_`` and return a deterministic, content-addressed
    ``QuotePlanV1``.

    A structurally contradictory ``MarketMakerEconomicTruthV1`` never
    reaches this function successfully -- it is rejected at construction
    time (``MarketMakerInputError``) before any identity is formed, per
    MM-IN-009. Every input that does reach this function yields a valid,
    hashable ``QuotePlanV1``: either ``VALID_DESIRED_STATE`` or a
    fail-closed ``NO_NEW_QUOTE_PLAN`` with explicit reason codes. Neither
    form is writer authority.
    """
    reasons: set[str] = set()
    valid = True

    plan_input_sha256 = compute_plan_input_sha256(input_)

    if input_.book_snapshot.market_ticker != input_.strategy_config.market_ticker:
        valid = False
        reasons.add(ReasonCode.INPUT_BOOK_INVALID.value)
    if not input_.book_snapshot.canonical_snapshot_sha256 or input_.book_snapshot.compute_identity_sha256() != input_.book_snapshot.canonical_snapshot_sha256:
        valid = False
        reasons.add(ReasonCode.INPUT_BOOK_INVALID.value)
    if input_.book_snapshot.canonical_snapshot_sha256 != input_.book_snapshot_sha256:
        valid = False
        reasons.add(ReasonCode.INPUT_BOOK_INVALID.value)

    reference = None
    try:
        reference = build_orderbook_reference(
            tuple((level.price, level.quantity) for level in input_.book_snapshot.yes_levels),
            tuple((level.price, level.quantity) for level in input_.book_snapshot.no_levels),
        )
    except RiskControlError:
        valid = False
        reasons.add(ReasonCode.INPUT_BOOK_INVALID.value)

    try:
        freshness_age_ms(
            input_.book_freshness, current_process_instance_id=input_.process_instance_id,
            now_monotonic_ns=input_.now_monotonic_ns, now_utc=input_.now_utc,
            max_age_ms=input_.risk_config.per_order.max_market_data_age_ms,
            max_future_wall_clock_skew_ms=input_.risk_config.state_integrity.max_future_wall_clock_skew_ms,
        )
    except RiskControlError:
        valid = False
        reasons.add(ReasonCode.INPUT_BOOK_STALE.value)

    try:
        freshness_age_ms(
            input_.reconciliation_freshness, current_process_instance_id=input_.process_instance_id,
            now_monotonic_ns=input_.now_monotonic_ns, now_utc=input_.now_utc,
            max_age_ms=input_.risk_config.state_integrity.max_reconciliation_lag_ms,
            max_future_wall_clock_skew_ms=input_.risk_config.state_integrity.max_future_wall_clock_skew_ms,
            stale_code=RiskControlCode.RECONCILIATION_STALE,
        )
    except RiskControlError:
        valid = False
        reasons.add(ReasonCode.INPUT_RECONCILIATION_STALE.value)

    if not _validated_price_grid(input_.price_ranges):
        valid = False
        reasons.add(ReasonCode.INPUT_PRICE_GRID_INVALID.value)
    elif compute_price_grid_sha256(input_.price_ranges) != input_.price_grid_sha256:
        valid = False
        reasons.add(ReasonCode.INPUT_PRICE_GRID_INVALID.value)

    if input_.risk_config.sha256 != input_.risk_config_sha256:
        valid = False
        reasons.add(ReasonCode.INPUT_RISK_CONFIG_MISMATCH.value)

    if input_.risk_control_state != "WRITER_ELIGIBLE":
        # Every non-WRITER_ELIGIBLE state (BOOT_HOLD, HALTED, SAFE_HELD,
        # QUIESCENT_HELD, RECONCILING, EMERGENCY_CANCELING, or any other)
        # fails closed to NO_NEW_QUOTE_PLAN. Hard-HALT cleanup belongs to
        # emergency control, never to an ordinary strategy decision.
        valid = False
        reasons.add(ReasonCode.INPUT_RISK_STATE_NOT_WRITER_ELIGIBLE.value)

    if input_.economic_truth.reconciliation_completeness != Completeness.COMPLETE.value:
        valid = False
        reasons.add(ReasonCode.INPUT_RECONCILIATION_INCOMPLETE.value)
    if input_.economic_truth.fill_history_completeness != Completeness.COMPLETE.value:
        valid = False
        reasons.add(ReasonCode.INPUT_FILL_HISTORY_INCOMPLETE.value)
    if input_.economic_truth.fill_identity_conflict_ids:
        valid = False
        reasons.add(ReasonCode.INPUT_FILL_IDENTITY_CONFLICT.value)
    if input_.economic_truth.unresolved_write_count > 0:
        valid = False
        reasons.add(ReasonCode.INPUT_UNRESOLVED_STRATEGY_WRITE.value)
    if input_.economic_truth.unresolved_write_exposure_usd == UNKNOWN_UNBOUNDED:
        valid = False
        reasons.add(ReasonCode.INPUT_EXPOSURE_UNKNOWN_UNBOUNDED.value)
    if input_.economic_truth.signed_inventory_state != SignedInventoryState.KNOWN.value:
        valid = False
        reasons.add(ReasonCode.INPUT_INVENTORY_UNKNOWN.value)

    for slot in QuoteSlot:
        classification = input_.slot_classifications.get(slot.value)
        matching_order_count = sum(1 for order in input_.strategy_working_orders if order.quote_slot == slot.value)
        if classification not in (member.value for member in SlotClassification):
            valid = False
            reasons.add(ReasonCode.INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT.value)
        elif classification == SlotClassification.CONFLICT.value:
            valid = False
            reasons.add(ReasonCode.INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT.value)
        elif classification == SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value:
            valid = False
            reasons.add(ReasonCode.INPUT_UNRESOLVED_STRATEGY_WRITE.value)
        elif classification == SlotClassification.ACTIVE_EXACT.value and matching_order_count != 1:
            valid = False
            reasons.add(ReasonCode.INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT.value)
        elif classification in (SlotClassification.ABSENT.value, SlotClassification.TERMINAL_RECONCILED.value) and matching_order_count != 0:
            valid = False
            reasons.add(ReasonCode.INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT.value)

    lower_quote: DesiredQuoteV1 | None = None
    upper_quote: DesiredQuoteV1 | None = None
    signed_position: Decimal | None = input_.economic_truth.signed_net_position_contracts

    if valid and reference is not None:
        if reference.best_yes_bid == reference.best_yes_ask:
            reasons.add(ReasonCode.BOTH_SUPPRESSED_LOCKED_BOOK.value)
        else:
            lower_classification = input_.slot_classifications.get(QuoteSlot.LOWER_YES_BID.value)
            upper_classification = input_.slot_classifications.get(QuoteSlot.UPPER_YES_ASK.value)
            lower_order = _working_order_for_slot(input_, QuoteSlot.LOWER_YES_BID)
            upper_order = _working_order_for_slot(input_, QuoteSlot.UPPER_YES_ASK)

            w_lower = lower_order.remaining_quantity if lower_classification == SlotClassification.ACTIVE_EXACT.value and lower_order is not None else ZERO
            w_upper = upper_order.remaining_quantity if upper_classification == SlotClassification.ACTIVE_EXACT.value and upper_order is not None else ZERO

            i = signed_position if signed_position is not None else ZERO

            lower_side_eligible = True
            upper_side_eligible = True

            if lower_classification == SlotClassification.ACTIVE_EXACT.value:
                if not (i + w_lower <= INVENTORY_THRESHOLD):
                    lower_side_eligible = False
                    reasons.add(ReasonCode.LOWER_SUPPRESSED_INVENTORY.value)
            elif lower_classification in (SlotClassification.ABSENT.value, SlotClassification.TERMINAL_RECONCILED.value):
                if not (i + QUOTE_QUANTITY <= INVENTORY_THRESHOLD):
                    lower_side_eligible = False
                    reasons.add(ReasonCode.LOWER_SUPPRESSED_INVENTORY.value)
            else:
                lower_side_eligible = False

            if upper_classification == SlotClassification.ACTIVE_EXACT.value:
                if not (i - w_upper >= -INVENTORY_THRESHOLD):
                    upper_side_eligible = False
                    reasons.add(ReasonCode.UPPER_SUPPRESSED_INVENTORY.value)
            elif upper_classification in (SlotClassification.ABSENT.value, SlotClassification.TERMINAL_RECONCILED.value):
                if not (i - QUOTE_QUANTITY >= -INVENTORY_THRESHOLD):
                    upper_side_eligible = False
                    reasons.add(ReasonCode.UPPER_SUPPRESSED_INVENTORY.value)
            else:
                upper_side_eligible = False

            m = reference.reference_yes_price
            s = input_.strategy_config.minimum_spread_usd
            raw_lower = m - (s / 2)
            raw_upper = m + (s / 2)
            maker_lower_ceiling = grid_prev(reference.best_yes_ask, input_.price_ranges)
            maker_upper_floor = grid_next(reference.best_yes_bid, input_.price_ranges)

            lower_candidate: Decimal | None = None
            upper_candidate: Decimal | None = None

            if lower_side_eligible:
                if maker_lower_ceiling is None:
                    reasons.add(ReasonCode.LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
                else:
                    lower_candidate = grid_floor(min(raw_lower, maker_lower_ceiling), input_.price_ranges)
                    if lower_candidate is None or not (ZERO < lower_candidate < ONE) or not (lower_candidate < reference.best_yes_ask):
                        lower_candidate = None
                        reasons.add(ReasonCode.LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)

            if upper_side_eligible:
                if maker_upper_floor is None:
                    reasons.add(ReasonCode.UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
                else:
                    upper_candidate = grid_ceil(max(raw_upper, maker_upper_floor), input_.price_ranges)
                    if upper_candidate is None or not (ZERO < upper_candidate < ONE) or not (upper_candidate > reference.best_yes_bid):
                        upper_candidate = None
                        reasons.add(ReasonCode.UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)

            if lower_candidate is not None and upper_candidate is not None:
                if not (upper_candidate > lower_candidate and upper_candidate - lower_candidate >= s):
                    lower_candidate = None
                    upper_candidate = None
                    reasons.add(ReasonCode.LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
                    reasons.add(ReasonCode.UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)

            if lower_candidate is not None and not price_reasonable(lower_candidate, reference, input_.risk_config.per_order.max_abs_reference_price_deviation_usd):
                lower_candidate = None
                reasons.add(ReasonCode.LOWER_SUPPRESSED_PRICE_REASONABILITY.value)
            if upper_candidate is not None and not price_reasonable(upper_candidate, reference, input_.risk_config.per_order.max_abs_reference_price_deviation_usd):
                upper_candidate = None
                reasons.add(ReasonCode.UPPER_SUPPRESSED_PRICE_REASONABILITY.value)

            target_exposure = ZERO
            if lower_candidate is not None:
                target_exposure += QUOTE_QUANTITY * lower_candidate
            if upper_candidate is not None:
                target_exposure += QUOTE_QUANTITY * (ONE - upper_candidate)
            if target_exposure > input_.strategy_config.max_strategy_target_working_exposure_usd:
                lower_candidate = None
                upper_candidate = None
                reasons.add(ReasonCode.BOTH_SUPPRESSED_TARGET_EXPOSURE.value)

            if lower_candidate is None and upper_candidate is None and not reasons:
                reasons.add(ReasonCode.TWO_SIDED_NEUTRAL.value)

            if lower_candidate is not None:
                lower_quote = DesiredQuoteV1(
                    quote_slot=QuoteSlot.LOWER_YES_BID.value, venue_side=_SLOT_VENUE_SIDE[QuoteSlot.LOWER_YES_BID],
                    outcome_side=_SLOT_OUTCOME_SIDE[QuoteSlot.LOWER_YES_BID], yes_price=lower_candidate,
                    quantity=QUOTE_QUANTITY,
                    quote_generation_id=compute_quote_generation_id(
                        strategy_instance_id=input_.strategy_config.strategy_instance_id,
                        market_ticker=input_.strategy_config.market_ticker,
                        quote_slot=QuoteSlot.LOWER_YES_BID.value, plan_input_sha256=plan_input_sha256,
                        venue_side=_SLOT_VENUE_SIDE[QuoteSlot.LOWER_YES_BID],
                        outcome_side=_SLOT_OUTCOME_SIDE[QuoteSlot.LOWER_YES_BID],
                        yes_price=lower_candidate, quantity=QUOTE_QUANTITY,
                    ),
                )
            if upper_candidate is not None:
                upper_quote = DesiredQuoteV1(
                    quote_slot=QuoteSlot.UPPER_YES_ASK.value, venue_side=_SLOT_VENUE_SIDE[QuoteSlot.UPPER_YES_ASK],
                    outcome_side=_SLOT_OUTCOME_SIDE[QuoteSlot.UPPER_YES_ASK], yes_price=upper_candidate,
                    quantity=QUOTE_QUANTITY,
                    quote_generation_id=compute_quote_generation_id(
                        strategy_instance_id=input_.strategy_config.strategy_instance_id,
                        market_ticker=input_.strategy_config.market_ticker,
                        quote_slot=QuoteSlot.UPPER_YES_ASK.value, plan_input_sha256=plan_input_sha256,
                        venue_side=_SLOT_VENUE_SIDE[QuoteSlot.UPPER_YES_ASK],
                        outcome_side=_SLOT_OUTCOME_SIDE[QuoteSlot.UPPER_YES_ASK],
                        yes_price=upper_candidate, quantity=QUOTE_QUANTITY,
                    ),
                )

    plan_classification = (
        PlanClassification.VALID_DESIRED_STATE.value if valid else PlanClassification.NO_NEW_QUOTE_PLAN.value
    )
    if not valid:
        lower_quote = None
        upper_quote = None

    effective_at_utc = max(input_.book_freshness.received_at_utc, input_.reconciliation_freshness.received_at_utc)
    not_after_monotonic_ns = min(
        input_.book_freshness.received_monotonic_ns + input_.risk_config.per_order.max_market_data_age_ms * 1_000_000,
        input_.reconciliation_freshness.received_monotonic_ns + input_.risk_config.state_integrity.max_reconciliation_lag_ms * 1_000_000,
    )

    fields = {
        "schema_revision": 1,
        "strategy_instance_id": input_.strategy_config.strategy_instance_id,
        "market_ticker": input_.strategy_config.market_ticker,
        "strategy_config_sha256": input_.strategy_config.config_sha256,
        "plan_input_sha256": plan_input_sha256,
        "source_book_snapshot_sha256": input_.book_snapshot_sha256,
        "book_freshness_identity_sha256": compute_mm_freshness_identity_sha256(input_.book_freshness),
        "price_grid_sha256": input_.price_grid_sha256,
        "risk_control_state": input_.risk_control_state,
        "risk_state_epoch": input_.risk_state_epoch,
        "risk_config_sha256": input_.risk_config_sha256,
        "reconciliation_snapshot_sha256": input_.reconciliation_snapshot_sha256,
        "reconciliation_freshness_identity_sha256": compute_mm_freshness_identity_sha256(input_.reconciliation_freshness),
        "economic_truth_sha256": input_.economic_truth.economic_truth_sha256,
        "signed_inventory_state": input_.economic_truth.signed_inventory_state,
        "signed_net_position_contracts": signed_position if valid else input_.economic_truth.signed_net_position_contracts,
        "lower_quote": lower_quote,
        "upper_quote": upper_quote,
        "plan_classification": plan_classification,
        "reason_codes": tuple(sorted(reasons)),
        "effective_at_utc": effective_at_utc,
        "not_after_monotonic_ns": not_after_monotonic_ns,
    }
    plan_sha256 = _compute_plan_sha256(fields)
    return QuotePlanV1(**fields, plan_sha256=plan_sha256)
