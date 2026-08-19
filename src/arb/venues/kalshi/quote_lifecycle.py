"""Quote comparison, persisted market-maker intent, and canonical writer-gate
integration for the minimal two-sided Kalshi Demo market-maker (Revision 03).

Implements ``KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_SPEC_03.md`` sections
18-26: exact logical quote ownership, existing-order comparison (KEEP /
CANCEL / CREATE / HOLD), cancel-before-replace, and the exact
``EXECUTION_INTENT_RECORDED`` intent envelope bound through the corrected
``WriterEligibilityGate``.

This module owns no credentials, signing, sockets, or venue transport. Every
normal write crosses the canonical ``WriterEligibilityGate`` /
``NormalWriteAdapter`` boundary. It never constructs a
``NormalWriterPermit`` directly, never bypasses the T1->T2->T3 append/anchor
sequence, and never issues raw SQL against the ledger/authority stores.

Interpretive note: the controlling specification gives the exact
``EXECUTION_INTENT_RECORDED`` payload shape for a market-maker CREATE
(MM-ID-003) but does not give a literal payload schema for an ordinary
strategy-driven CANCEL. This module extends the same architecture
(operation_family ``KALSHI_DEMO_MINIMAL_MM_CANCEL``, nested payload carrying
the same identity classes) consistently with MM-CANCEL-001/002, rather than
inventing an unrelated shape. A future bounded specification correction may
freeze that shape exactly; until then this is a documented implementation
choice, not a claim of literal spec text.
"""

from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from arb.execution_ledger import EventType, LedgerEvent, LockedLedger, canonical_json_bytes, sha256_hex
from arb.venues.kalshi.minimal_market_maker import (
    QUOTE_QUANTITY,
    DesiredQuoteV1,
    QuoteSlot,
    SlotClassification,
    StrategyOwnedWorkingOrderV1,
    grid_distance,
)
from arb.venues.kalshi.order_lifecycle import build_cancel_query, generate_client_order_id, is_valid_lowercase_uuid4
from arb.venues.kalshi.risk_control import (
    UNKNOWN_UNBOUNDED,
    CandidateOrderV1,
    EconomicFillV1,
    MarketEconomicState,
    NormalWriterPermit,
    PriceRangeV1,
    RiskControlError,
    RiskLimitConfigV1,
    WorkingOrderV1,
    WriterEligibilityAssessment,
    WriterEligibilityGate,
    compute_market_economic_state,
    enforce_projected_limits,
    project_candidate_risk,
)

ZERO = Decimal("0")
KEEP_MAX_REMAINING_QUANTITY = Decimal("1.00")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_QUOTE_GENERATION_ID_RE = re.compile(r"^qg_[0-9a-f]{32}$")
_CANCEL_INTENT_OUTER_KEYS = frozenset({
    "execution_attempt_id", "venue", "environment", "conflict_domain_ref", "incident_id",
    "operation_family", "client_order_id", "capability_reference_id", "intent_payload_schema_id",
    "intent_payload",
})
_CANCEL_INTENT_NESTED_KEYS = frozenset({
    "schema_revision", "request_id", "strategy_instance_id", "market_ticker", "quote_slot",
    "quote_generation_id", "target_venue_order_id", "reconciliation_snapshot_sha256", "client_order_id",
})
_CANCEL_INTENT_QUOTE_SLOT_VALUES = frozenset({QuoteSlot.LOWER_YES_BID.value, QuoteSlot.UPPER_YES_ASK.value})

CREATE_ORDER_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "ticker", "client_order_id", "side", "count", "price", "time_in_force",
    "self_trade_prevention_type", "expiration_time", "post_only",
    "cancel_order_on_pause", "reduce_only", "subaccount", "exchange_index",
})

_CREATE_REQUEST_PREPARED_KEYS = (
    "request_id", "operation_class", "venue", "environment", "operation_name", "method",
    "path_without_query", "canonical_query", "canonical_query_sha256", "canonical_body",
    "canonical_body_sha256", "client_order_id", "venue_order_id", "idempotency_key",
    "adapter_payload_schema_id",
)


class QuoteLifecycleError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class QuoteAction(enum.StrEnum):
    KEEP_EXISTING = "KEEP_EXISTING"
    NO_QUOTE = "NO_QUOTE"
    CANCEL_EXISTING = "CANCEL_EXISTING"
    CANCEL_THEN_RECONCILE_BEFORE_NEW = "CANCEL_THEN_RECONCILE_BEFORE_NEW"
    CREATE_NEW = "CREATE_NEW"
    HOLD_NO_STRATEGY_WRITE = "HOLD_NO_STRATEGY_WRITE"


_CANCEL_ACTIONS = (QuoteAction.CANCEL_EXISTING, QuoteAction.CANCEL_THEN_RECONCILE_BEFORE_NEW)


# ---------------------------------------------------------------------------
# MM-CMP — per-slot existing-order comparison
# ---------------------------------------------------------------------------


def compare_slot(
    *,
    desired: DesiredQuoteV1 | None,
    plan_valid: bool,
    classification: str,
    working_order: StrategyOwnedWorkingOrderV1 | None,
    price_ranges: Sequence[PriceRangeV1],
    keep_reprice_distance_grid_steps: int,
    best_yes_bid: Decimal | None,
    best_yes_ask: Decimal | None,
    risk_control_state: str,
) -> QuoteAction:
    """Exact per-slot KEEP/CANCEL/CREATE/HOLD/NO_QUOTE selection (MM-CMP-001..007).

    Writer eligibility is checked before any ordinary KEEP/CANCEL/CREATE
    decision: every non-``WRITER_ELIGIBLE`` risk-control state (``BOOT_HOLD``,
    ``HALTED``, ``SAFE_HELD``, ``QUIESCENT_HELD``, ``RECONCILING``,
    ``EMERGENCY_CANCELING``, or any other) yields ``HOLD_NO_STRATEGY_WRITE``
    unconditionally -- including for an ``ACTIVE_EXACT`` order whose desired
    quote disappears, reprices, or becomes inventory-suppressed. Emergency
    control, not the ordinary strategy comparison, owns hard-HALT
    cancellation.
    """

    if risk_control_state != "WRITER_ELIGIBLE":
        return QuoteAction.HOLD_NO_STRATEGY_WRITE
    if not plan_valid:
        return QuoteAction.HOLD_NO_STRATEGY_WRITE
    if classification in (SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, SlotClassification.CONFLICT.value):
        return QuoteAction.HOLD_NO_STRATEGY_WRITE

    if classification == SlotClassification.ACTIVE_EXACT.value:
        if working_order is None:
            # A structurally contradictory input (see minimal_market_maker's
            # own ownership-conflict check) must never reach this point with
            # a valid plan; treat defensively as HOLD.
            return QuoteAction.HOLD_NO_STRATEGY_WRITE
        if desired is None:
            return QuoteAction.CANCEL_EXISTING
        keep_ok = (
            working_order.remaining_quantity > ZERO
            and working_order.remaining_quantity <= KEEP_MAX_REMAINING_QUANTITY
            and working_order.venue_side == desired.venue_side
            and working_order.outcome_side == desired.outcome_side
        )
        if keep_ok and best_yes_bid is not None and best_yes_ask is not None:
            if desired.venue_side == "bid":
                keep_ok = working_order.yes_price < best_yes_ask
            else:
                keep_ok = working_order.yes_price > best_yes_bid
        if keep_ok:
            distance = grid_distance(working_order.yes_price, desired.yes_price, price_ranges)
            keep_ok = distance is not None and distance < keep_reprice_distance_grid_steps
        return QuoteAction.KEEP_EXISTING if keep_ok else QuoteAction.CANCEL_THEN_RECONCILE_BEFORE_NEW

    # ABSENT or TERMINAL_RECONCILED. Writer eligibility was already checked
    # unconditionally above.
    if desired is None:
        return QuoteAction.NO_QUOTE
    return QuoteAction.CREATE_NEW


# ---------------------------------------------------------------------------
# MM-ARCH-002/003 — one normal write in flight, deterministic action
# precedence
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SelectedWriteV1:
    quote_slot: str
    action: str  # "CANCEL" | "CREATE"
    target_venue_order_id: str | None
    desired: DesiredQuoteV1 | None


_SLOT_ORDER = {QuoteSlot.LOWER_YES_BID.value: 0, QuoteSlot.UPPER_YES_ASK.value: 1}


def select_write_action(
    actions: Mapping[str, QuoteAction],
    working_orders: Mapping[str, StrategyOwnedWorkingOrderV1 | None],
) -> SelectedWriteV1 | None:
    """At most one normal venue write per evaluation (MM-ARCH-002/003)."""

    if any(action is QuoteAction.HOLD_NO_STRATEGY_WRITE for action in actions.values()):
        return None
    cancel_slots = sorted(
        (slot for slot, action in actions.items() if action in _CANCEL_ACTIONS),
        key=lambda slot: _SLOT_ORDER[slot],
    )
    if cancel_slots:
        slot = cancel_slots[0]
        order = working_orders.get(slot)
        if order is None:
            raise QuoteLifecycleError("MM_CANCEL_TARGET_MISSING")
        return SelectedWriteV1(slot, "CANCEL", order.venue_order_id, None)
    create_slots = sorted(
        (slot for slot, action in actions.items() if action is QuoteAction.CREATE_NEW),
        key=lambda slot: _SLOT_ORDER[slot],
    )
    if create_slots:
        return SelectedWriteV1(create_slots[0], "CREATE", None, None)
    return None


# ---------------------------------------------------------------------------
# MM-ID-002/003 — client-order-id allocation and the exact persisted
# market-maker CREATE intent envelope
# ---------------------------------------------------------------------------


def allocate_client_order_id(*, persisted_client_order_id: str | None) -> str:
    """Reuse a persisted client-order id for a replayed quote generation;
    never mint a second one for the same persisted intent (MM-ID-002)."""

    if persisted_client_order_id is not None:
        if not is_valid_lowercase_uuid4(persisted_client_order_id):
            raise QuoteLifecycleError("MM_CLIENT_ORDER_ID_CONFLICT")
        return persisted_client_order_id
    return generate_client_order_id()


def build_mm_create_intent_payload(
    *,
    execution_attempt_id: str,
    conflict_domain_ref: str,
    incident_id: str,
    client_order_id: str,
    capability_reference_id: str,
    request_id: str,
    strategy_instance_id: str,
    market_ticker: str,
    quote_slot: str,
    quote_generation_id: str,
    quote_plan_sha256: str,
    plan_input_sha256: str,
    source_book_snapshot_sha256: str,
    risk_config_sha256: str,
    risk_state_epoch: int,
    reconciliation_snapshot_sha256: str,
    venue_side: str,
    outcome_side: str,
    yes_price: Decimal,
    quantity: Decimal,
    environment: str = "KALSHI_DEMO",
) -> dict:
    """Exact outer ``EXECUTION_INTENT_RECORDED`` payload for a market-maker
    CREATE (MM-ID-003). No top-level ``request_id``."""

    intent_payload = {
        "schema_revision": 1,
        "request_id": request_id,
        "strategy_instance_id": strategy_instance_id,
        "market_ticker": market_ticker,
        "quote_slot": quote_slot,
        "quote_generation_id": quote_generation_id,
        "quote_plan_sha256": quote_plan_sha256,
        "plan_input_sha256": plan_input_sha256,
        "source_book_snapshot_sha256": source_book_snapshot_sha256,
        "risk_config_sha256": risk_config_sha256,
        "risk_state_epoch": risk_state_epoch,
        "reconciliation_snapshot_sha256": reconciliation_snapshot_sha256,
        "venue_side": venue_side,
        "outcome_side": outcome_side,
        "yes_price": yes_price,
        "quantity": quantity,
        "client_order_id": client_order_id,
    }
    return {
        "execution_attempt_id": execution_attempt_id,
        "venue": "KALSHI",
        "environment": environment,
        "conflict_domain_ref": conflict_domain_ref,
        "incident_id": incident_id,
        "operation_family": "KALSHI_DEMO_MINIMAL_MM_CREATE",
        "client_order_id": client_order_id,
        "capability_reference_id": capability_reference_id,
        "intent_payload_schema_id": "KALSHI_MINIMAL_MM_QUOTE_INTENT_V1",
        "intent_payload": intent_payload,
    }


def build_mm_cancel_intent_payload(
    *,
    execution_attempt_id: str,
    conflict_domain_ref: str,
    incident_id: str,
    client_order_id: str,
    capability_reference_id: str,
    request_id: str,
    strategy_instance_id: str,
    market_ticker: str,
    quote_slot: str,
    quote_generation_id: str,
    target_venue_order_id: str,
    reconciliation_snapshot_sha256: str,
    environment: str = "KALSHI_DEMO",
) -> dict:
    """Ordinary strategy-driven CANCEL intent envelope, structurally
    parallel to the CREATE envelope (see module docstring: this exact shape
    is an implementation extension, not literal MM-ID-003 spec text)."""

    intent_payload = {
        "schema_revision": 1,
        "request_id": request_id,
        "strategy_instance_id": strategy_instance_id,
        "market_ticker": market_ticker,
        "quote_slot": quote_slot,
        "quote_generation_id": quote_generation_id,
        "target_venue_order_id": target_venue_order_id,
        "reconciliation_snapshot_sha256": reconciliation_snapshot_sha256,
        "client_order_id": client_order_id,
    }
    return {
        "execution_attempt_id": execution_attempt_id,
        "venue": "KALSHI",
        "environment": environment,
        "conflict_domain_ref": conflict_domain_ref,
        "incident_id": incident_id,
        "operation_family": "KALSHI_DEMO_MINIMAL_MM_CANCEL",
        "client_order_id": client_order_id,
        "capability_reference_id": capability_reference_id,
        "intent_payload_schema_id": "KALSHI_MINIMAL_MM_CANCEL_INTENT_V1",
        "intent_payload": intent_payload,
    }


# ---------------------------------------------------------------------------
# MM-VENUE-003 / MM-RISK-009 — canonical Create-V2 request preparation
# ---------------------------------------------------------------------------


# Exact accepted source-bound Create-V2 values inherited from the protected
# predecessor contract (order_lifecycle.py SUBACCOUNT/EXCHANGE_INDEX/
# TIME_IN_FORCE/SELF_TRADE_PREVENTION_TYPE/POST_ONLY/CANCEL_ORDER_ON_PAUSE/
# REDUCE_ONLY). These are not strategy-chosen and never vary per quote.
_SOURCE_BOUND_SUBACCOUNT = 0
_SOURCE_BOUND_EXCHANGE_INDEX = 0
_SOURCE_BOUND_TIME_IN_FORCE = "good_till_canceled"
_SOURCE_BOUND_SELF_TRADE_PREVENTION_TYPE = "taker_at_cross"
_SOURCE_BOUND_POST_ONLY = True
_SOURCE_BOUND_CANCEL_ORDER_ON_PAUSE = True
_SOURCE_BOUND_REDUCE_ONLY = False


def _is_exact_int(value: object) -> bool:
    return type(value) is int


@dataclass(frozen=True, slots=True)
class VenueBindingV1:
    """Source-bound values the strategy/lifecycle layer does not itself
    choose (MM-VENUE-003: "exact source-bound value", "accepted
    source-bound value"). Every field except ``adapter_payload_schema_id``
    is fixed to the exact accepted predecessor contract and independently
    validated here so a wrong-typed/wrong-valued caller input fails closed
    rather than being silently accepted."""

    subaccount: int = _SOURCE_BOUND_SUBACCOUNT
    exchange_index: int = _SOURCE_BOUND_EXCHANGE_INDEX
    self_trade_prevention_type: str = _SOURCE_BOUND_SELF_TRADE_PREVENTION_TYPE
    time_in_force: str = _SOURCE_BOUND_TIME_IN_FORCE
    adapter_payload_schema_id: str = ""

    def __post_init__(self) -> None:
        if not _is_exact_int(self.subaccount) or self.subaccount != _SOURCE_BOUND_SUBACCOUNT:
            raise QuoteLifecycleError("MM_INPUT_INVALID")
        if not _is_exact_int(self.exchange_index) or self.exchange_index != _SOURCE_BOUND_EXCHANGE_INDEX:
            raise QuoteLifecycleError("MM_INPUT_INVALID")
        if self.self_trade_prevention_type != _SOURCE_BOUND_SELF_TRADE_PREVENTION_TYPE:
            raise QuoteLifecycleError("MM_INPUT_INVALID")
        if self.time_in_force != _SOURCE_BOUND_TIME_IN_FORCE:
            raise QuoteLifecycleError("MM_INPUT_INVALID")
        if type(self.adapter_payload_schema_id) is not str or not self.adapter_payload_schema_id:
            raise QuoteLifecycleError("MM_INPUT_INVALID")


def build_mm_create_order_body(
    *, ticker: str, client_order_id: str, venue_side: str, yes_price: Decimal, quantity: Decimal,
    expiration_time: int, venue_binding: VenueBindingV1,
) -> dict:
    if venue_side not in ("bid", "ask"):
        raise QuoteLifecycleError("MM_INPUT_INVALID")
    if type(quantity) is not Decimal or type(yes_price) is not Decimal:
        raise QuoteLifecycleError("MM_INPUT_INVALID")
    if quantity != QUOTE_QUANTITY:
        raise QuoteLifecycleError("MM_INPUT_INVALID")
    if not (ZERO < yes_price < Decimal("1")):
        raise QuoteLifecycleError("MM_INPUT_INVALID")
    body = {
        "ticker": ticker,
        "client_order_id": client_order_id,
        "side": venue_side,
        "count": str(quantity.quantize(Decimal("0.01"))),
        "price": str(yes_price.quantize(Decimal("0.0001"))),
        "time_in_force": venue_binding.time_in_force,
        "self_trade_prevention_type": venue_binding.self_trade_prevention_type,
        "expiration_time": expiration_time,
        "post_only": _SOURCE_BOUND_POST_ONLY,
        "cancel_order_on_pause": _SOURCE_BOUND_CANCEL_ORDER_ON_PAUSE,
        "reduce_only": _SOURCE_BOUND_REDUCE_ONLY,
        "subaccount": venue_binding.subaccount,
        "exchange_index": venue_binding.exchange_index,
    }
    if set(body) != CREATE_ORDER_ALLOWED_FIELDS or "order_group_id" in body:
        raise QuoteLifecycleError("MM_INPUT_INVALID")
    return body


def build_create_prepared_payload(
    *, request_id: str, environment: str, client_order_id: str, canonical_body: Mapping[str, object],
    venue_binding: VenueBindingV1,
) -> dict:
    canonical_query: dict = {}
    canonical_query_sha256 = sha256_hex(canonical_json_bytes(canonical_query))
    canonical_body_sha256 = sha256_hex(canonical_json_bytes(canonical_body))
    identity = {
        "request_id": request_id,
        "operation_class": "WRITE",
        "venue": "KALSHI",
        "environment": environment,
        "operation_name": "CREATE_ORDER_V2",
        "method": "POST",
        "path_without_query": "/trade-api/v2/portfolio/events/orders",
        "canonical_query": canonical_query,
        "canonical_query_sha256": canonical_query_sha256,
        "canonical_body": dict(canonical_body),
        "canonical_body_sha256": canonical_body_sha256,
        "client_order_id": client_order_id,
        "venue_order_id": None,
        "idempotency_key": client_order_id,
        "adapter_payload_schema_id": venue_binding.adapter_payload_schema_id,
    }
    prepared_request_sha256 = sha256_hex(canonical_json_bytes(identity))
    return {**identity, "prepared_request_sha256": prepared_request_sha256}


def build_cancel_prepared_payload(
    *, request_id: str, environment: str, venue_order_id: str, client_order_id: str,
    adapter_payload_schema_id: str,
) -> dict:
    canonical_query = build_cancel_query()
    canonical_query_sha256 = sha256_hex(canonical_json_bytes(canonical_query))
    identity = {
        "request_id": request_id,
        "operation_class": "WRITE",
        "venue": "KALSHI",
        "environment": environment,
        "operation_name": "CANCEL_ORDER_V2",
        "method": "DELETE",
        "path_without_query": f"/trade-api/v2/portfolio/events/orders/{venue_order_id}",
        "canonical_query": canonical_query,
        "canonical_query_sha256": canonical_query_sha256,
        "canonical_body": None,
        "canonical_body_sha256": None,
        "client_order_id": client_order_id,
        "venue_order_id": venue_order_id,
        "idempotency_key": client_order_id,
        "adapter_payload_schema_id": adapter_payload_schema_id,
    }
    prepared_request_sha256 = sha256_hex(canonical_json_bytes(identity))
    return {**identity, "prepared_request_sha256": prepared_request_sha256}


# ---------------------------------------------------------------------------
# MM-RISK-002..006 — CREATE candidate mapping and writer-eligibility
# assessment
# ---------------------------------------------------------------------------


def candidate_for_desired_quote(*, market_ticker: str, desired: DesiredQuoteV1) -> CandidateOrderV1:
    return CandidateOrderV1(market_ticker, desired.outcome_side, desired.quantity, desired.yes_price)


def build_writer_eligibility_assessment(
    *,
    risk_assessment_id: str,
    request_id: str,
    candidate: CandidateOrderV1,
    market_economic_state: MarketEconomicState,
    unresolved_exposure: Decimal | str,
    risk_config: RiskLimitConfigV1,
    prepared_request_sha256: str,
    market_data_snapshot_sha256: str,
    market_data_freshness_identity_sha256: str,
    reconciliation_snapshot_sha256: str,
    reconciliation_freshness_identity_sha256: str,
    risk_state_epoch: int,
    freshness_deadline_monotonic_ns: int,
) -> WriterEligibilityAssessment:
    candidate_economic_sha256 = sha256_hex(canonical_json_bytes({
        "market": candidate.market, "outcome_side": candidate.outcome_side,
        "quantity": candidate.quantity, "yes_price": candidate.yes_price,
    }))
    try:
        projected = project_candidate_risk(market_economic_state, candidate, unresolved_exposure)
        enforce_projected_limits(projected, candidate, risk_config)
        eligible = True
    except RiskControlError:
        eligible = False
    return WriterEligibilityAssessment(
        risk_assessment_id, "CREATE_ORDER_V2", request_id, prepared_request_sha256, candidate_economic_sha256,
        risk_config.sha256, market_data_snapshot_sha256, market_data_freshness_identity_sha256,
        reconciliation_snapshot_sha256, reconciliation_freshness_identity_sha256, risk_state_epoch,
        freshness_deadline_monotonic_ns, eligible,
    )


def _worst_case_abs_net_position(state: MarketEconomicState) -> Decimal:
    """Spec 06/07 MM07-ECON-001: the pure existing-state worst-case absolute
    net position -- no hypothetical candidate lot is ever added here (that
    would require a prohibited ``CandidateOrderV1``, MM06-ECON-001)."""

    return max(
        abs(state.signed_net_position + state.working_bid_quantity),
        abs(state.signed_net_position - state.working_ask_quantity),
    )


def _market_gross_exposure_usd(state: MarketEconomicState, unresolved_exposure_usd: Decimal) -> Decimal:
    return state.filled_exposure_usd + state.working_exposure_usd + unresolved_exposure_usd


def _cancel_state_within_limits(state: MarketEconomicState, unresolved_exposure_usd: Decimal, risk_config: RiskLimitConfigV1) -> bool:
    per_market = risk_config.per_market
    return (
        _worst_case_abs_net_position(state) <= per_market.max_abs_net_position_contracts
        and _market_gross_exposure_usd(state, unresolved_exposure_usd) <= per_market.max_gross_exposure_usd
        and state.working_order_count <= per_market.max_authoritative_working_orders
        and state.working_contracts <= per_market.max_working_contracts
        and state.working_exposure_usd <= per_market.max_working_order_exposure_usd
    )


def _market_economic_state_object(state: MarketEconomicState) -> dict:
    """Exact Spec 06 MM06-ECON-006 ``market_economic_state_object(s)``
    (preserved unchanged by Spec 07 MM07-HASH-001)."""

    return {
        "filled_exposure_usd": state.filled_exposure_usd,
        "signed_net_position": state.signed_net_position,
        "working_exposure_usd": state.working_exposure_usd,
        "working_bid_quantity": state.working_bid_quantity,
        "working_ask_quantity": state.working_ask_quantity,
        "working_order_count": state.working_order_count,
        "working_contracts": state.working_contracts,
    }


def _validate_cancel_transformation_invariants(
    *, pre_state: MarketEconomicState, post_state: MarketEconomicState, target: WorkingOrderV1,
) -> str | None:
    """MM07-ECON-005..009 (Spec 07 Correction 03, MM07-CLAR-TRANSFORM-001):
    explicit, load-bearing transformation invariants for the exact
    hypothetical single-order removal that produced ``post_state`` from
    ``pre_state``. Returns ``None`` only when every invariant holds exactly;
    otherwise a machine-readable violation reason.

    This is a pure function over the two already-independently-constructed
    states and the exact target -- it never recomputes, repairs, clamps, or
    normalizes either state. A contradictory post state (wrong order
    removed, two orders removed, target not removed, a mutated fill/signed-
    inventory quantity, or an ignored target quantity/side) is detected here
    and MUST NOT become eligible merely because both states independently
    satisfy the configured per-market maximum limits."""

    q = target.remaining_quantity
    if type(q) is not Decimal or q <= ZERO:
        return "TARGET_QUANTITY_NOT_POSITIVE"

    # MM07-ECON-005: fill-derived quantities are invariant -- the post state
    # must have been computed from the exact same authoritative fill
    # sequence as the pre state.
    if post_state.filled_exposure_usd != pre_state.filled_exposure_usd:
        return "FILLED_EXPOSURE_MUTATED"
    if post_state.signed_net_position != pre_state.signed_net_position:
        return "SIGNED_NET_POSITION_MUTATED"

    # MM07-ECON-006: working-order-count and working-contracts decrease by
    # exactly one order / exactly the target's remaining quantity -- never
    # merely `post <= pre`.
    if post_state.working_order_count != pre_state.working_order_count - 1:
        return "WORKING_ORDER_COUNT_NOT_EXACT_DECREMENT"
    if post_state.working_contracts != pre_state.working_contracts - q:
        return "WORKING_CONTRACTS_NOT_EXACT_DECREMENT"
    if post_state.working_contracts < ZERO:
        return "WORKING_CONTRACTS_NEGATIVE"

    # MM07-ECON-006: side-specific exact quantity transformation -- the
    # opposite side is byte-for-byte unchanged, never merely non-increasing.
    if target.outcome_side == "YES":
        if post_state.working_bid_quantity != pre_state.working_bid_quantity - q:
            return "WORKING_BID_QUANTITY_NOT_EXACT_DECREMENT"
        if post_state.working_ask_quantity != pre_state.working_ask_quantity:
            return "WORKING_ASK_QUANTITY_UNEXPECTEDLY_CHANGED"
    elif target.outcome_side == "NO":
        if post_state.working_ask_quantity != pre_state.working_ask_quantity - q:
            return "WORKING_ASK_QUANTITY_NOT_EXACT_DECREMENT"
        if post_state.working_bid_quantity != pre_state.working_bid_quantity:
            return "WORKING_BID_QUANTITY_UNEXPECTEDLY_CHANGED"
    else:
        return "TARGET_SIDE_INVALID"

    if post_state.working_bid_quantity < ZERO or post_state.working_ask_quantity < ZERO:
        return "WORKING_QUANTITY_NEGATIVE"

    # MM07-ECON-006/007: working exposure and market gross exposure are
    # non-increasing (the caller supplies the same finite unresolved
    # exposure to both states' gross-exposure evaluation).
    if post_state.working_exposure_usd > pre_state.working_exposure_usd:
        return "WORKING_EXPOSURE_INCREASED"

    # MM07-ECON-002..004: the frozen W(n,b,a) monotonicity theorem itself,
    # checked directly against the exact reconstructed states -- not
    # asserted, not hardcoded.
    if _worst_case_abs_net_position(post_state) > _worst_case_abs_net_position(pre_state):
        return "WORST_CASE_ABS_NET_POSITION_INCREASED"

    return None


def _target_working_order_object(order: WorkingOrderV1) -> dict:
    """Exact Spec 06 MM06-ECON-006 ``target_working_order_object`` (preserved
    unchanged by Spec 07 MM07-HASH-001)."""

    return {
        "market": order.market,
        "order_id": order.order_id,
        "outcome_side": order.outcome_side,
        "remaining_quantity": order.remaining_quantity,
        "yes_price": order.yes_price,
        "status": order.status,
    }


def _cancel_ineligible_economic_sha256(*, request_id: str, target_venue_order_id: str, reason: str) -> str:
    """Deterministic, secret-safe compatibility-slot hash used only when the
    full Spec-06/07 ``cancel_operation_economic_object`` cannot be
    constructed at all (no exact target, unbounded exposure). ``eligible``
    is always ``False`` in this path, so this hash never gates a permit."""

    return sha256_hex(canonical_json_bytes({
        "schema_revision": 1, "operation_kind": "CANCEL_ORDER_V2", "request_id": request_id,
        "target_venue_order_id": target_venue_order_id, "ineligible_reason": reason,
    }))


def build_cancel_writer_eligibility_assessment(
    *,
    risk_assessment_id: str,
    request_id: str,
    strategy_instance_id: str,
    market_ticker: str,
    quote_slot: str,
    quote_generation_id: str,
    target_venue_order_id: str,
    client_order_id: str,
    authoritative_fills: Sequence[EconomicFillV1],
    authoritative_working_orders: Sequence[WorkingOrderV1],
    unresolved_exposure_usd: Decimal | str,
    prepared_request_sha256: str,
    risk_config: RiskLimitConfigV1,
    market_data_snapshot_sha256: str,
    market_data_freshness_identity_sha256: str,
    reconciliation_snapshot_sha256: str,
    reconciliation_freshness_identity_sha256: str,
    risk_state_epoch: int,
    freshness_deadline_monotonic_ns: int,
) -> WriterEligibilityAssessment:
    """Ordinary strategy-driven CANCEL_ORDER_V2 assessment (Spec 06 Section
    8, corrected rationale in Spec 07 Sections 5-9): the exact two-outcome
    economic proof -- never the unconditional "cancellation is
    risk-reducing" shortcut, and never simplified merely because Spec 07
    proves the frozen ``worst_case_abs_net_position`` formula cannot expand
    under single-order removal (MM07-ECON-001..004). Never constructs or
    reuses a ``CandidateOrderV1`` (MM06-ECON-001). ``eligible`` is ``True``
    only when an exact single target is proven present in
    ``authoritative_working_orders``, ``unresolved_exposure_usd`` is a
    finite nonnegative ``Decimal`` (never ``UNKNOWN_UNBOUNDED``), and BOTH
    the pre-cancel and post-target-removed economic states -- each
    genuinely, independently constructed via ``compute_market_economic_state``
    -- satisfy every configured per-market limit (MM06-ECON-002..004,007;
    MM07-ECON-005..009)."""

    def _ineligible(reason: str) -> WriterEligibilityAssessment:
        candidate_economic_sha256 = _cancel_ineligible_economic_sha256(
            request_id=request_id, target_venue_order_id=target_venue_order_id, reason=reason,
        )
        return WriterEligibilityAssessment(
            risk_assessment_id, "CANCEL_ORDER_V2", request_id, prepared_request_sha256, candidate_economic_sha256,
            risk_config.sha256, market_data_snapshot_sha256, market_data_freshness_identity_sha256,
            reconciliation_snapshot_sha256, reconciliation_freshness_identity_sha256, risk_state_epoch,
            freshness_deadline_monotonic_ns, False,
        )

    if unresolved_exposure_usd == UNKNOWN_UNBOUNDED:
        return _ineligible("UNKNOWN_UNBOUNDED_EXPOSURE")
    if (
        type(unresolved_exposure_usd) is not Decimal
        or not unresolved_exposure_usd.is_finite()
        or unresolved_exposure_usd < ZERO
    ):
        return _ineligible("UNRESOLVED_EXPOSURE_INVALID")

    matching_targets = [order for order in authoritative_working_orders if order.order_id == target_venue_order_id]
    if len(matching_targets) != 1:
        return _ineligible("TARGET_NOT_EXACTLY_ONE")
    target_working_order = matching_targets[0]
    if target_working_order.market != market_ticker:
        return _ineligible("TARGET_MARKET_MISMATCH")

    try:
        # MM07-ECON-008/009: both states are genuinely, independently
        # recomputed from the exact authoritative fill sequence -- the post
        # state is never inferred, hardcoded, or copied from the pre state.
        pre_cancel_state = compute_market_economic_state(market_ticker, authoritative_fills, authoritative_working_orders)
        remaining_working_orders = [
            order for order in authoritative_working_orders if order.order_id != target_venue_order_id
        ]
        post_target_removed_state = compute_market_economic_state(market_ticker, authoritative_fills, remaining_working_orders)
    except RiskControlError:
        return _ineligible("ECONOMIC_STATE_UNAVAILABLE")

    cancel_operation_economic_object = {
        "schema_revision": 1,
        "operation_kind": "CANCEL_ORDER_V2",
        "request_id": request_id,
        "strategy_instance_id": strategy_instance_id,
        "market_ticker": market_ticker,
        "quote_slot": quote_slot,
        "quote_generation_id": quote_generation_id,
        "target_venue_order_id": target_venue_order_id,
        "client_order_id": client_order_id,
        "market_data_snapshot_sha256": market_data_snapshot_sha256,
        "market_data_freshness_identity_sha256": market_data_freshness_identity_sha256,
        "reconciliation_snapshot_sha256": reconciliation_snapshot_sha256,
        "reconciliation_freshness_identity_sha256": reconciliation_freshness_identity_sha256,
        "pre_cancel_market_economic_state": _market_economic_state_object(pre_cancel_state),
        "target_working_order": _target_working_order_object(target_working_order),
        "post_target_removed_market_economic_state": _market_economic_state_object(post_target_removed_state),
        "unresolved_exposure_usd": unresolved_exposure_usd,
    }
    candidate_economic_sha256 = sha256_hex(canonical_json_bytes(cancel_operation_economic_object))

    # MM07-ECON-005..009 (Correction 03 Defect 01): every applicable
    # transformation invariant must hold exactly before the two-state limit
    # checks are even consulted -- a contradictory post state (wrong/extra
    # removal, mutated fills/inventory, ignored quantity/side) never becomes
    # eligible merely because both states independently satisfy the
    # configured maximum limits. The hash above is still computed over the
    # exact (possibly contradictory) reconstructed states either way.
    transformation_violation = _validate_cancel_transformation_invariants(
        pre_state=pre_cancel_state, post_state=post_target_removed_state, target=target_working_order,
    )
    eligible = (
        transformation_violation is None
        and _cancel_state_within_limits(pre_cancel_state, unresolved_exposure_usd, risk_config)
        and _cancel_state_within_limits(post_target_removed_state, unresolved_exposure_usd, risk_config)
    )

    return WriterEligibilityAssessment(
        risk_assessment_id, "CANCEL_ORDER_V2", request_id, prepared_request_sha256, candidate_economic_sha256,
        risk_config.sha256, market_data_snapshot_sha256, market_data_freshness_identity_sha256,
        reconciliation_snapshot_sha256, reconciliation_freshness_identity_sha256, risk_state_epoch,
        freshness_deadline_monotonic_ns, eligible,
    )


# ---------------------------------------------------------------------------
# MM06-INTENT-001..008 / MM06-TARGET-001..002 / MM06-REQ-001..002 -- exact
# ordinary CANCEL intent schema and cross-object binding validation (Spec 06
# Sections 5-7, preserved unchanged by Spec 07 MM07-CANCEL-001). Defense-in-
# depth: the runner calls this before T1/transport so a malformed intent, a
# mismatched request/target identity, or a wrong built-in type/null field can
# never reach the ledger or the adapter.
# ---------------------------------------------------------------------------


def _require_nonempty_nfc_str(value: object) -> str:
    if type(value) is not str or not value or unicodedata.normalize("NFC", value) != value:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    return value


def _require_lowercase_uuid4(value: object) -> str:
    if type(value) is not str or not is_valid_lowercase_uuid4(value):
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    return value


def _require_hex64(value: object) -> str:
    if type(value) is not str or _HEX64_RE.fullmatch(value) is None:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    return value


def validate_mm_cancel_intent_payload(payload: object) -> Mapping[str, object]:
    """Exact Spec-06 Section 5 outer/nested key-set, type, nullability, and
    identity-grammar validation for an ordinary CANCEL
    ``EXECUTION_INTENT_RECORDED`` payload (MM06-INTENT-001..003, preserved
    unchanged by Spec 07 MM07-CANCEL-001). Raises ``QuoteLifecycleError`` on
    any violation -- missing key, extra key, wrong built-in type, null where
    prohibited, or malformed identity. Returns the validated nested
    ``intent_payload`` mapping on success."""

    if type(payload) is not dict or set(payload) != _CANCEL_INTENT_OUTER_KEYS:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_OUTER_SHAPE_INVALID")

    execution_attempt_id = _require_nonempty_nfc_str(payload["execution_attempt_id"])
    if payload["venue"] != "KALSHI":
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    if payload["environment"] != "KALSHI_DEMO":
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    conflict_domain_ref = _require_nonempty_nfc_str(payload["conflict_domain_ref"])
    _require_nonempty_nfc_str(payload["incident_id"])
    if payload["operation_family"] != "KALSHI_DEMO_MINIMAL_MM_CANCEL":
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    outer_client_order_id = _require_lowercase_uuid4(payload["client_order_id"])
    _require_nonempty_nfc_str(payload["capability_reference_id"])
    if payload["intent_payload_schema_id"] != "KALSHI_MINIMAL_MM_CANCEL_INTENT_V1":
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")

    nested = payload["intent_payload"]
    if type(nested) is not dict or set(nested) != _CANCEL_INTENT_NESTED_KEYS:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_NESTED_SHAPE_INVALID")
    if type(nested["schema_revision"]) is not int or nested["schema_revision"] != 1:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    request_id = _require_nonempty_nfc_str(nested["request_id"])
    _require_nonempty_nfc_str(nested["strategy_instance_id"])
    _require_nonempty_nfc_str(nested["market_ticker"])
    if nested["quote_slot"] not in _CANCEL_INTENT_QUOTE_SLOT_VALUES:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    quote_generation_id = nested["quote_generation_id"]
    if type(quote_generation_id) is not str or _QUOTE_GENERATION_ID_RE.fullmatch(quote_generation_id) is None:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_FIELD_INVALID")
    _require_nonempty_nfc_str(nested["target_venue_order_id"])
    _require_hex64(nested["reconciliation_snapshot_sha256"])
    nested_client_order_id = _require_lowercase_uuid4(nested["client_order_id"])

    # MM06-INTENT-004/005: exact equality bindings within the payload.
    if nested_client_order_id != outer_client_order_id:
        raise QuoteLifecycleError("MM_CANCEL_INTENT_BINDING_MISMATCH")
    if request_id in (execution_attempt_id, outer_client_order_id, conflict_domain_ref):
        raise QuoteLifecycleError("MM_CANCEL_INTENT_BINDING_MISMATCH")

    return nested


def validate_cancel_request_binding(
    *,
    outer_intent_payload: Mapping[str, object],
    prepared_payload: Mapping[str, object],
    assessment: WriterEligibilityAssessment,
    target_venue_order_id: str,
) -> None:
    """Exact cross-object equality required before T1/transport
    (MM06-INTENT-004, MM06-TARGET-001..002, MM06-REQ-002; preserved
    unchanged by Spec 07 MM07-CANCEL-002/003). Never targets by
    ``client_order_id``, ticker, price, time, or fuzzy match -- the only
    accepted target is the exact authoritative ``target_venue_order_id``
    bound identically across the intent, the prepared DELETE request, and
    the assessment. Raises ``QuoteLifecycleError`` on any mismatch."""

    nested = validate_mm_cancel_intent_payload(dict(outer_intent_payload))
    request_id = nested["request_id"]
    nested_target = nested["target_venue_order_id"]

    if nested_target != target_venue_order_id:
        raise QuoteLifecycleError("MM_CANCEL_TARGET_MISMATCH")

    expected_path_suffix = "/" + target_venue_order_id
    if (
        prepared_payload.get("request_id") != request_id
        or prepared_payload.get("operation_name") != "CANCEL_ORDER_V2"
        or prepared_payload.get("method") != "DELETE"
        or prepared_payload.get("venue_order_id") != target_venue_order_id
        or prepared_payload.get("client_order_id") != nested["client_order_id"]
        or type(prepared_payload.get("path_without_query")) is not str
        or not prepared_payload["path_without_query"].endswith(expected_path_suffix)
    ):
        raise QuoteLifecycleError("MM_CANCEL_TARGET_MISMATCH")

    if (
        assessment.operation_kind != "CANCEL_ORDER_V2"
        or assessment.request_id != request_id
        or assessment.candidate_request_sha256 != prepared_payload.get("prepared_request_sha256")
        or assessment.reconciliation_snapshot_sha256 != nested["reconciliation_snapshot_sha256"]
    ):
        raise QuoteLifecycleError("MM_CANCEL_INTENT_BINDING_MISMATCH")


# ---------------------------------------------------------------------------
# MM-RISK-008/009 — the exact T0->T1->T2->T3 successor chain through the
# corrected WriterEligibilityGate. Transport is never invoked here.
# ---------------------------------------------------------------------------


def issue_and_persist_write_permit(
    *,
    gate: WriterEligibilityGate,
    locked: LockedLedger,
    normal_writer_session_id: str,
    assessment: WriterEligibilityAssessment,
    outer_intent_payload: Mapping[str, object],
    prepared_payload: Mapping[str, object],
) -> NormalWriterPermit:
    """Issue a fresh permit and durably persist T1 (EXECUTION_INTENT_RECORDED),
    T2 (REQUEST_PREPARED), and T3 (WRITE_SEND_BOUNDARY_ENTERED) in order.
    Raises before any of these complete if the assessment/payloads are
    invalid, HALT is latched, or the trusted tail moves unexpectedly.
    Transport remains the caller's responsibility via ``NormalWriteAdapter``
    (MM-RISK-001/003)."""

    permit = gate.issue_permit(
        locked=locked,
        normal_writer_session_id=normal_writer_session_id,
        assessment=assessment,
        intent_payload=outer_intent_payload,
        prepared_payload=prepared_payload,
    )
    gate.persist_intent(permit, locked)
    gate.persist_prepared(permit, locked)
    gate.persist_send_boundary(permit, locked)
    return permit


def _decimal_from_replayed_field(value: object) -> Decimal | None:
    """A value read back from a replayed ledger event payload. Real
    persisted Decimals round-trip through execution_ledger's own canonical
    ``{"$decimal": "<text>"}`` tag (see ``execution_ledger._canonical_value``
    / ``_validate_decimal_tags``); a plain ``Decimal`` is also accepted for
    values that were never round-tripped through storage (e.g. in offline
    tests using a fake locked ledger)."""

    if type(value) is Decimal:
        return value
    if isinstance(value, Mapping) and set(value) == {"$decimal"} and type(value.get("$decimal")) is str:
        try:
            return Decimal(value["$decimal"])
        except InvalidOperation:
            return None
    return None


# ---------------------------------------------------------------------------
# MM-ID-005 / MM-RST — read-only restart ownership reconstruction
# ---------------------------------------------------------------------------
#
# Uses only the already-canonical, already-replayed ``LockedLedger.events``
# sequence (the same public surface risk_control.py itself reads via
# ``locked.events[-1]``) -- no raw SQL, no new database, no shadow replay
# engine. A slot is ACTIVE_EXACT / TERMINAL_RECONCILED / UNRESOLVED_OR_
# AMBIGUOUS / CONFLICT / ABSENT purely from this exact persisted evidence
# chain; price, quantity, ticker+side, and timestamps are never identity
# proof (MM-ID-005). The exact accepted terminal-status vocabulary here
# (``"canceled"``, ``"executed"``) is the same one ``order_lifecycle.py``'s
# protected ``SUPPORTED_ORDER_STATUSES`` already freezes (MM07-CLAR-002):
# never ``status != "resting"``.


@dataclass(frozen=True, slots=True)
class ReconstructedSlotOwnershipV1:
    quote_slot: str
    classification: str
    working_order: StrategyOwnedWorkingOrderV1 | None
    persisted_client_order_id: str | None


def _mm_create_intents_for_slot(
    events: Sequence[LedgerEvent], *, strategy_instance_id: str, market_ticker: str, quote_slot: str,
) -> list[LedgerEvent]:
    matches = []
    for event in events:
        if event.event_type is not EventType.EXECUTION_INTENT_RECORDED:
            continue
        payload = event.payload
        if payload.get("operation_family") != "KALSHI_DEMO_MINIMAL_MM_CREATE":
            continue
        nested = payload.get("intent_payload")
        if not isinstance(nested, Mapping):
            continue
        if (
            nested.get("strategy_instance_id") == strategy_instance_id
            and nested.get("market_ticker") == market_ticker
            and nested.get("quote_slot") == quote_slot
        ):
            matches.append(event)
    return matches


def _mm_cancel_intents_for_venue_order(
    events: Sequence[LedgerEvent], *, venue_order_id: str,
) -> list[LedgerEvent]:
    matches = []
    for event in events:
        if event.event_type is not EventType.EXECUTION_INTENT_RECORDED:
            continue
        payload = event.payload
        if payload.get("operation_family") != "KALSHI_DEMO_MINIMAL_MM_CANCEL":
            continue
        nested = payload.get("intent_payload")
        if not isinstance(nested, Mapping):
            continue
        if nested.get("target_venue_order_id") == venue_order_id:
            matches.append(event)
    return matches


def _qualifying_closing_reconciliation_exists(
    events: Sequence[LedgerEvent], *, venue_order_id: str, after_sequence: int,
) -> bool:
    """The one shared authoritative-closure predicate (MM-CMP-006 /
    MM-FILL-003..006 / MM-VALID-001 / MM-REPL-002): the mere existence of
    *any* ``RECONCILIATION_RECORDED`` naming this exact ``venue_order_id``
    is never sufficient. A qualifying reconciliation must:

    1. be strictly later (higher ledger sequence) than ``after_sequence`` --
       the exact evidence it claims to close;
    2. bind ``bound_order_id`` to this exact ``venue_order_id``;
    3. carry ``write_closure_class == "AUTHORITATIVE_RESULT_CLOSED"``;
    4. carry ``unknown_result is False``;
    5. carry ``active_order_upper_bound == 0``.

    Used both for Correction-03's cancel hold and Correction-04's terminal-
    order closure so the two never define authoritative closure differently.
    """

    for event in events:
        if event.event_type is not EventType.RECONCILIATION_RECORDED:
            continue
        if event.sequence <= after_sequence:
            continue  # a reconciliation predating the evidence cannot close it
        payload = event.payload
        if (
            payload.get("bound_order_id") == venue_order_id
            and payload.get("write_closure_class") == "AUTHORITATIVE_RESULT_CLOSED"
            and payload.get("unknown_result") is False
            and payload.get("active_order_upper_bound") == 0
        ):
            return True
    return False


def _cancel_hold_active(events: Sequence[LedgerEvent], *, venue_order_id: str) -> bool:
    """MM-REPL-002 / MM-FILL-005: an exact persisted MM cancel intent against
    this exact ``venue_order_id`` holds the slot unresolved -- regardless of
    HTTP acknowledgement, raw terminal order observation, local timeout,
    restart, or elapsed time -- until a *later* (higher-sequence) qualifying
    ``RECONCILIATION_RECORDED`` for this exact ``venue_order_id`` proves
    authoritative closure. If more than one matching cancel intent exists,
    only the latest one's resolution matters (no favorable-older-attempt
    selection, no blind resend)."""

    cancel_intents = _mm_cancel_intents_for_venue_order(events, venue_order_id=venue_order_id)
    if not cancel_intents:
        return False
    latest_cancel = max(cancel_intents, key=lambda event: event.sequence)
    return not _qualifying_closing_reconciliation_exists(
        events, venue_order_id=venue_order_id, after_sequence=latest_cancel.sequence,
    )


def _authoritative_terminal_reconciliation_exists(
    events: Sequence[LedgerEvent], *, venue_order_id: str, latest_observation_sequence: int,
) -> bool:
    """MM-CMP-006 / MM-FILL-003..006 / MM-VALID-001: a terminal-looking raw
    order observation (``status`` of ``canceled``/``executed``) is not
    itself a reconciled slot. The qualifying closing reconciliation must
    postdate both the latest order observation *and* every ``FILL_OBSERVED``
    for this exact ``venue_order_id`` -- a later fill invalidates older
    closure proof and requires a fresh reconciliation."""

    fill_sequences = [
        event.sequence for event in events
        if event.event_type is EventType.FILL_OBSERVED and event.payload.get("venue_order_id") == venue_order_id
    ]
    after_sequence = max([latest_observation_sequence, *fill_sequences])
    return _qualifying_closing_reconciliation_exists(
        events, venue_order_id=venue_order_id, after_sequence=after_sequence,
    )


def reconstruct_slot_ownership(
    events: Sequence[LedgerEvent], *, strategy_instance_id: str, market_ticker: str, quote_slot: str,
) -> ReconstructedSlotOwnershipV1:
    """Reconstruct exact strategy ownership for one quote slot from replayed
    ledger events only. Never infers ownership from price/quantity/ticker+
    side similarity; only the exact persisted identity chain (MM-ID-005):
    ``EXECUTION_INTENT_RECORDED`` -> exact persisted ``client_order_id`` ->
    accepted ``ORDER_IDENTITY_BOUND`` -> latest ``ORDER_OBSERVED`` ->
    ``RECONCILIATION_RECORDED``."""

    intents = _mm_create_intents_for_slot(
        events, strategy_instance_id=strategy_instance_id, market_ticker=market_ticker, quote_slot=quote_slot,
    )
    if not intents:
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.ABSENT.value, None, None)

    by_generation: dict[str, list[LedgerEvent]] = {}
    for event in intents:
        generation_id = event.payload["intent_payload"].get("quote_generation_id")
        by_generation.setdefault(generation_id, []).append(event)

    # Fail closed if any one persisted quote generation ever claims more than
    # one client_order_id (MM-ID-002: never mint a second client_order_id
    # for the same persisted generation; a second distinct value observed in
    # history is an unresolvable conflict, not a reconstruction to prefer).
    for generation_events in by_generation.values():
        client_ids = {event.payload["intent_payload"].get("client_order_id") for event in generation_events}
        if len(client_ids) > 1:
            return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.CONFLICT.value, None, None)

    latest_intent = max(intents, key=lambda event: event.sequence)
    nested = latest_intent.payload["intent_payload"]
    persisted_client_order_id = nested.get("client_order_id")
    if not isinstance(persisted_client_order_id, str) or not persisted_client_order_id:
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, None)

    bindings = [
        event for event in events
        if event.event_type is EventType.ORDER_IDENTITY_BOUND
        and event.payload.get("client_order_id") == persisted_client_order_id
    ]
    if not bindings:
        # Intent persisted but no accepted client->venue-order binding yet:
        # an unresolved CREATE. No active ownership; new CREATE is blocked
        # by the caller's own unresolved-write economic-truth input, not by
        # this reconstruction returning a phantom order.
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
    bound_venue_order_ids = {event.payload.get("venue_order_id") for event in bindings}
    if len(bound_venue_order_ids) > 1:
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.CONFLICT.value, None, persisted_client_order_id)
    venue_order_id = bindings[-1].payload.get("venue_order_id")
    if not isinstance(venue_order_id, str) or not venue_order_id:
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)

    if _cancel_hold_active(events, venue_order_id=venue_order_id):
        # An outstanding MM cancel intent against this exact order that is
        # not yet closed by a later authoritative reconciliation holds the
        # slot unresolved regardless of the raw latest order status.
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)

    observations = [
        event for event in events
        if event.event_type is EventType.ORDER_OBSERVED and event.payload.get("venue_order_id") == venue_order_id
    ]
    if not observations:
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
    latest_observation = max(observations, key=lambda event: event.sequence)
    canonical_order = latest_observation.payload.get("canonical_venue_payload")
    if not isinstance(canonical_order, Mapping):
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
    status = canonical_order.get("status")

    if status == "resting":
        remaining_field = canonical_order.get("remaining_count_fp")
        remaining_quantity = _decimal_from_replayed_field(remaining_field)
        if remaining_quantity is None and type(remaining_field) is str:
            try:
                remaining_quantity = Decimal(remaining_field)
            except InvalidOperation:
                remaining_quantity = None
        if remaining_quantity is None:
            return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
        if remaining_quantity <= ZERO:
            return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
        persisted_yes_price = _decimal_from_replayed_field(nested.get("yes_price"))
        if persisted_yes_price is None:
            return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
        working_order = StrategyOwnedWorkingOrderV1(
            strategy_instance_id=strategy_instance_id, market_ticker=market_ticker, quote_slot=quote_slot,
            quote_generation_id=nested.get("quote_generation_id"), client_order_id=persisted_client_order_id,
            venue_order_id=venue_order_id, venue_side=nested.get("venue_side"), outcome_side=nested.get("outcome_side"),
            yes_price=persisted_yes_price, initial_quantity=QUOTE_QUANTITY, remaining_quantity=remaining_quantity,
            authoritative_status="resting", source_intent_event_id=latest_intent.event_id,
            source_order_identity_binding_event_id=bindings[-1].event_id,
            latest_order_observation_event_id=latest_observation.event_id,
            ownership_basis_sha256=sha256_hex(canonical_json_bytes({
                "intent_event_id": latest_intent.event_id, "binding_event_id": bindings[-1].event_id,
                "observation_event_id": latest_observation.event_id,
            })),
        )
        # An active order without complete authoritative reconciliation is
        # still exact/proven (KEEP/CANCEL comparison covers it); only a
        # terminal order requires reconciliation before the slot frees up.
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.ACTIVE_EXACT.value, working_order, persisted_client_order_id)

    if status in ("canceled", "executed"):
        if not _authoritative_terminal_reconciliation_exists(
            events, venue_order_id=venue_order_id, latest_observation_sequence=latest_observation.sequence,
        ):
            return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
        return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.TERMINAL_RECONCILED.value, None, persisted_client_order_id)

    return ReconstructedSlotOwnershipV1(quote_slot, SlotClassification.UNRESOLVED_OR_AMBIGUOUS.value, None, persisted_client_order_id)
