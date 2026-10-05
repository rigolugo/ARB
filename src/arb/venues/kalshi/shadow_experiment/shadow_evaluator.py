"""Local-only, NON-AUTHORITATIVE shadow quote evaluator.

This mirrors ONLY the deterministic price / inventory / suppression geometry
of canonical ``arb.venues.kalshi.minimal_market_maker.evaluate_market_maker_input``
(the block that runs once every validity gate has passed) and reuses the
canonical pure helpers for every primitive: ``build_orderbook_reference``,
``price_reasonable``, ``grid_floor`` / ``grid_ceil`` / ``grid_prev`` /
``grid_next``, the canonical price-grid validation, ``ReasonCode`` values,
``INVENTORY_THRESHOLD``, ``QUOTE_QUANTITY`` and the fixed maximum target
working exposure of ``build_market_maker_config``.

It never takes, synthesizes or emits a risk-control state.  Its output,
``ShadowQuoteObservationV1``, is not a ``QuotePlanV1``, carries no plan /
generation / permit identity, and is not consumable by any execution path.
Unknown inputs stay ``UNKNOWN``; no missing value is coerced to zero.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple

SCHEMA = "ShadowQuoteObservationV1"
AUTHORITY = "NON_AUTHORITATIVE_SHADOW_OBSERVATION__NOT_A_QUOTE_PLAN__NOT_WRITER_AUTHORITY"
EVALUATOR_VERSION = "g1-shadow-evaluator-1"

INVENTORY_KNOWN = "KNOWN"                       # offline equivalence tests only
INVENTORY_KNOWN_FLAT_OBSERVED = "KNOWN_FLAT_OBSERVED"
INVENTORY_UNKNOWN = "UNKNOWN"
SLOTS_ABSENT_OBSERVED = "ABSENT_OBSERVED"
SLOTS_UNKNOWN = "UNKNOWN"

NOTE_REASONABILITY_NOT_EVALUATED = "SHADOW_PRICE_REASONABILITY_NOT_EVALUATED_RISK_CONFIG_UNBOUND"
NOTE_SLOT_OWNERSHIP_UNKNOWN = "SHADOW_WORKING_ORDER_OWNERSHIP_UNKNOWN"


def evaluator_identity() -> dict:
    source = Path(__file__).read_bytes()
    return {"evaluator": "shadow_experiment.shadow_evaluator", "version": EVALUATOR_VERSION,
            "sha256": hashlib.sha256(source).hexdigest(), "bytes": len(source)}


@dataclass(frozen=True)
class ShadowInventoryInput:
    state: str                                  # KNOWN | KNOWN_FLAT_OBSERVED | UNKNOWN
    signed_position: Optional[Decimal]          # None unless state is KNOWN / KNOWN_FLAT_OBSERVED
    slots: str                                  # ABSENT_OBSERVED | UNKNOWN
    basis: str                                  # human-readable observation basis


@dataclass(frozen=True)
class ShadowQuoteObservationV1:
    shadow_schema: str
    shadow_authority: str
    market_ticker: str
    trial_G: int
    trial_G_authority: str
    minimum_spread_usd: str
    captured_book_identity: str
    captured_at_utc: str
    best_yes_bid: Optional[str]
    best_yes_ask: Optional[str]
    reference_yes_price: Optional[str]
    observed_top_spread: Optional[str]
    raw_lower: Optional[str]
    raw_upper: Optional[str]
    geometry_lower_candidate_assuming_flat_absent: Optional[str]
    geometry_upper_candidate_assuming_flat_absent: Optional[str]
    geometry_reason_codes: Tuple[str, ...]
    shadow_lower_candidate: Optional[str]
    shadow_upper_candidate: Optional[str]
    quantity: Optional[str]
    inventory_observation: str
    inventory_signed_position: Optional[str]
    working_order_observation: str
    observation_basis: str
    suppression_reason_codes: Tuple[str, ...]
    shadow_notes: Tuple[str, ...]
    projected_lower_side_exposure_usd: Optional[str]
    projected_upper_side_exposure_usd: Optional[str]
    projected_target_working_exposure_usd: Optional[str]
    price_reasonability: str
    evaluator: Mapping[str, object]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["geometry_reason_codes"] = list(self.geometry_reason_codes)
        data["suppression_reason_codes"] = list(self.suppression_reason_codes)
        data["shadow_notes"] = list(self.shadow_notes)
        data["evaluator"] = dict(self.evaluator)
        return data


def _s(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


def _geometry(mm, risk, reference, ranges, s: Decimal, *, i: Decimal, w_lower: Decimal, w_upper: Decimal,
              lower_mode: str, upper_mode: str, deviation_cap: Optional[Decimal], reasons: set, notes: set):
    """Exact mirror of the canonical post-validity geometry block.

    ``lower_mode`` / ``upper_mode`` are the canonical slot classification
    values (ABSENT / TERMINAL_RECONCILED / ACTIVE_EXACT / other)."""
    ZERO, ONE = mm.ZERO, mm.ONE
    RC = mm.ReasonCode
    SC = mm.SlotClassification
    if reference.best_yes_bid == reference.best_yes_ask:
        reasons.add(RC.BOTH_SUPPRESSED_LOCKED_BOOK.value)
        return None, None
    lower_side_eligible = True
    upper_side_eligible = True
    if lower_mode == SC.ACTIVE_EXACT.value:
        if not (i + w_lower <= mm.INVENTORY_THRESHOLD):
            lower_side_eligible = False
            reasons.add(RC.LOWER_SUPPRESSED_INVENTORY.value)
    elif lower_mode in (SC.ABSENT.value, SC.TERMINAL_RECONCILED.value):
        if not (i + mm.QUOTE_QUANTITY <= mm.INVENTORY_THRESHOLD):
            lower_side_eligible = False
            reasons.add(RC.LOWER_SUPPRESSED_INVENTORY.value)
    else:
        lower_side_eligible = False
    if upper_mode == SC.ACTIVE_EXACT.value:
        if not (i - w_upper >= -mm.INVENTORY_THRESHOLD):
            upper_side_eligible = False
            reasons.add(RC.UPPER_SUPPRESSED_INVENTORY.value)
    elif upper_mode in (SC.ABSENT.value, SC.TERMINAL_RECONCILED.value):
        if not (i - mm.QUOTE_QUANTITY >= -mm.INVENTORY_THRESHOLD):
            upper_side_eligible = False
            reasons.add(RC.UPPER_SUPPRESSED_INVENTORY.value)
    else:
        upper_side_eligible = False

    m = reference.reference_yes_price
    raw_lower = m - (s / 2)
    raw_upper = m + (s / 2)
    maker_lower_ceiling = mm.grid_prev(reference.best_yes_ask, ranges)
    maker_upper_floor = mm.grid_next(reference.best_yes_bid, ranges)
    lower_candidate = None
    upper_candidate = None
    if lower_side_eligible:
        if maker_lower_ceiling is None:
            reasons.add(RC.LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
        else:
            lower_candidate = mm.grid_floor(min(raw_lower, maker_lower_ceiling), ranges)
            if lower_candidate is None or not (ZERO < lower_candidate < ONE) or not (lower_candidate < reference.best_yes_ask):
                lower_candidate = None
                reasons.add(RC.LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
    if upper_side_eligible:
        if maker_upper_floor is None:
            reasons.add(RC.UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
        else:
            upper_candidate = mm.grid_ceil(max(raw_upper, maker_upper_floor), ranges)
            if upper_candidate is None or not (ZERO < upper_candidate < ONE) or not (upper_candidate > reference.best_yes_bid):
                upper_candidate = None
                reasons.add(RC.UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
    if lower_candidate is not None and upper_candidate is not None:
        if not (upper_candidate > lower_candidate and upper_candidate - lower_candidate >= s):
            lower_candidate = None
            upper_candidate = None
            reasons.add(RC.LOWER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
            reasons.add(RC.UPPER_SUPPRESSED_NO_SAFE_GRID_PRICE.value)
    if deviation_cap is None:
        notes.add(NOTE_REASONABILITY_NOT_EVALUATED)
    else:
        if lower_candidate is not None and not risk.price_reasonable(lower_candidate, reference, deviation_cap):
            lower_candidate = None
            reasons.add(RC.LOWER_SUPPRESSED_PRICE_REASONABILITY.value)
        if upper_candidate is not None and not risk.price_reasonable(upper_candidate, reference, deviation_cap):
            upper_candidate = None
            reasons.add(RC.UPPER_SUPPRESSED_PRICE_REASONABILITY.value)
    target_exposure = ZERO
    if lower_candidate is not None:
        target_exposure += mm.QUOTE_QUANTITY * lower_candidate
    if upper_candidate is not None:
        target_exposure += mm.QUOTE_QUANTITY * (ONE - upper_candidate)
    if target_exposure > mm._FIXED_MAX_TARGET_EXPOSURE:
        lower_candidate = None
        upper_candidate = None
        reasons.add(RC.BOTH_SUPPRESSED_TARGET_EXPOSURE.value)
    if lower_candidate is None and upper_candidate is None and not reasons:
        reasons.add(RC.TWO_SIDED_NEUTRAL.value)
    return lower_candidate, upper_candidate


def evaluate_shadow(mm, risk, *, market_ticker: str, minimum_spread_usd: Decimal,
                    yes_levels_ascending: Sequence[Tuple[Decimal, Decimal]],
                    no_levels_ascending: Sequence[Tuple[Decimal, Decimal]],
                    price_ranges: Sequence, inventory: ShadowInventoryInput,
                    captured_book_identity: str, captured_at_utc: str,
                    trial_G: int, trial_G_authority: str,
                    deviation_cap: Optional[Decimal] = None,
                    w_lower: Decimal = Decimal("0"), w_upper: Decimal = Decimal("0"),
                    lower_mode: Optional[str] = None, upper_mode: Optional[str] = None) -> ShadowQuoteObservationV1:
    """Deterministic.  ``deviation_cap`` / ``w_*`` / ``*_mode`` exist only so
    the offline differential tests can reproduce canonical cases exactly; the
    live path passes ``deviation_cap=None`` and never ACTIVE_EXACT slots."""
    if type(minimum_spread_usd) is not Decimal:
        raise TypeError("minimum_spread_usd must be Decimal")
    RC = mm.ReasonCode
    SC = mm.SlotClassification
    s = minimum_spread_usd
    reasons_geo: set = set()
    reasons: set = set()
    notes: set = set()
    reference = None
    try:
        reference = risk.build_orderbook_reference(tuple(yes_levels_ascending), tuple(no_levels_ascending))
    except risk.RiskControlError:
        reasons_geo.add(RC.INPUT_BOOK_INVALID.value)
        reasons.add(RC.INPUT_BOOK_INVALID.value)
    grid_ok = mm._validated_price_grid(tuple(price_ranges))
    if not grid_ok:
        reasons_geo.add(RC.INPUT_PRICE_GRID_INVALID.value)
        reasons.add(RC.INPUT_PRICE_GRID_INVALID.value)

    geo_lower = geo_upper = None
    lower = upper = None
    raw_lower = raw_upper = None
    if reference is not None and grid_ok:
        raw_lower = reference.reference_yes_price - (s / 2)
        raw_upper = reference.reference_yes_price + (s / 2)
        geo_notes: set = set()
        geo_lower, geo_upper = _geometry(
            mm, risk, reference, tuple(price_ranges), s, i=Decimal("0"), w_lower=Decimal("0"), w_upper=Decimal("0"),
            lower_mode=SC.ABSENT.value, upper_mode=SC.ABSENT.value, deviation_cap=deviation_cap,
            reasons=reasons_geo, notes=geo_notes)
        notes |= geo_notes
        if inventory.state == INVENTORY_UNKNOWN or inventory.signed_position is None:
            reasons.add(RC.INPUT_INVENTORY_UNKNOWN.value)
        elif inventory.slots != SLOTS_ABSENT_OBSERVED and lower_mode is None:
            notes.add(NOTE_SLOT_OWNERSHIP_UNKNOWN)
            reasons.add(RC.INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT.value)
        else:
            lower, upper = _geometry(
                mm, risk, reference, tuple(price_ranges), s, i=inventory.signed_position,
                w_lower=w_lower, w_upper=w_upper,
                lower_mode=lower_mode or SC.ABSENT.value, upper_mode=upper_mode or SC.ABSENT.value,
                deviation_cap=deviation_cap, reasons=reasons, notes=notes)

    q = mm.QUOTE_QUANTITY
    exposure_lower = q * lower if lower is not None else None
    exposure_upper = q * (mm.ONE - upper) if upper is not None else None
    target = None
    if lower is not None or upper is not None:
        target = (exposure_lower or Decimal("0")) + (exposure_upper or Decimal("0"))
    return ShadowQuoteObservationV1(
        shadow_schema=SCHEMA, shadow_authority=AUTHORITY, market_ticker=market_ticker,
        trial_G=trial_G, trial_G_authority=trial_G_authority, minimum_spread_usd=format(s, "f"),
        captured_book_identity=captured_book_identity, captured_at_utc=captured_at_utc,
        best_yes_bid=_s(reference.best_yes_bid) if reference else None,
        best_yes_ask=_s(reference.best_yes_ask) if reference else None,
        reference_yes_price=_s(reference.reference_yes_price) if reference else None,
        observed_top_spread=_s(reference.best_yes_ask - reference.best_yes_bid) if reference else None,
        raw_lower=_s(raw_lower), raw_upper=_s(raw_upper),
        geometry_lower_candidate_assuming_flat_absent=_s(geo_lower),
        geometry_upper_candidate_assuming_flat_absent=_s(geo_upper),
        geometry_reason_codes=tuple(sorted(reasons_geo)),
        shadow_lower_candidate=_s(lower), shadow_upper_candidate=_s(upper),
        quantity=_s(q) if (lower is not None or upper is not None) else None,
        inventory_observation=inventory.state,
        inventory_signed_position=_s(inventory.signed_position),
        working_order_observation=inventory.slots,
        observation_basis=inventory.basis,
        suppression_reason_codes=tuple(sorted(reasons)),
        shadow_notes=tuple(sorted(notes)),
        projected_lower_side_exposure_usd=_s(exposure_lower),
        projected_upper_side_exposure_usd=_s(exposure_upper),
        projected_target_working_exposure_usd=_s(target),
        price_reasonability="EVALUATED" if deviation_cap is not None else "NOT_EVALUATED_RISK_CONFIG_UNBOUND",
        evaluator=evaluator_identity(),
    )
