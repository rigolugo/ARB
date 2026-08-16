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
    CandidateOrderV1,
    MarketEconomicState,
    NormalWriterPermit,
    PriceRangeV1,
    RiskControlError,
    RiskLimitConfigV1,
    WriterEligibilityAssessment,
    WriterEligibilityGate,
    enforce_projected_limits,
    project_candidate_risk,
)

ZERO = Decimal("0")
KEEP_MAX_REMAINING_QUANTITY = Decimal("1.00")

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


def build_cancel_writer_eligibility_assessment(
    *,
    risk_assessment_id: str,
    request_id: str,
    prepared_request_sha256: str,
    risk_config: RiskLimitConfigV1,
    market_data_snapshot_sha256: str,
    market_data_freshness_identity_sha256: str,
    reconciliation_snapshot_sha256: str,
    reconciliation_freshness_identity_sha256: str,
    risk_state_epoch: int,
    freshness_deadline_monotonic_ns: int,
) -> WriterEligibilityAssessment:
    """Ordinary strategy-driven CANCEL_ORDER_V2 assessment. Cancellation is
    risk-reducing (never increases candidate exposure), so unlike CREATE it
    carries no candidate-risk projection: eligibility here is unconditional
    for a genuine cancel target -- the shared gate itself still enforces
    hard-HALT, nested request binding, and trusted-tail invariants
    independently of this ``eligible`` flag."""

    candidate_economic_sha256 = sha256_hex(canonical_json_bytes({"operation": "CANCEL_ORDER_V2", "request_id": request_id}))
    return WriterEligibilityAssessment(
        risk_assessment_id, "CANCEL_ORDER_V2", request_id, prepared_request_sha256, candidate_economic_sha256,
        risk_config.sha256, market_data_snapshot_sha256, market_data_freshness_identity_sha256,
        reconciliation_snapshot_sha256, reconciliation_freshness_identity_sha256, risk_state_epoch,
        freshness_deadline_monotonic_ns, True,
    )


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
# proof (MM-ID-005).


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
