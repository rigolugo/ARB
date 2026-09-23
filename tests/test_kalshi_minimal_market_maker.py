"""Offline tests for the pure deterministic minimal market-maker strategy
(``KALSHI_DEMO_MINIMAL_TWO_SIDED_MARKET_MAKER_SPEC_03/04.md``).

All tests are offline: synthetic Decimal inputs, no network, no venue, no
credentials, no real ledger/authority mutation.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from arb.venues.kalshi.orderbook import KalshiNativeOrderBookLevel, KalshiNativeOrderBookSnapshot
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    FlowRiskLimits,
    FreshnessStampV1,
    MarketEconomicState,
    OrderbookReferenceV1,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    PriceRangeV1,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
    build_orderbook_reference,
    price_reasonable,
)
from arb.venues.kalshi.minimal_market_maker import (
    MarketMakerEconomicTruthV1,
    MarketMakerInputError,
    MarketMakerInputV1,
    MinimalMarketMakerConfigV1,
    PlanClassification,
    QuoteSlot,
    ReasonCode,
    SlotClassification,
    build_economic_truth,
    build_market_maker_config,
    compute_mm_freshness_identity_sha256,
    compute_price_grid_sha256,
    compute_quote_generation_id,
    evaluate_market_maker_input,
    grid_ceil,
    grid_distance,
    grid_floor,
    grid_next,
    grid_prev,
)

D = Decimal


def risk_config(*, deviation_cap: Decimal = D("0.10")) -> RiskLimitConfigV1:
    """``deviation_cap`` is the exact ``per_order.max_abs_reference_price_
    deviation_usd`` leaf (CORRECTION_07 C07-PRICE-001).  It is a parameter
    only so tests can construct the exact C07 boundary cases; no value is
    selected or defaulted by this project."""
    return RiskLimitConfigV1(
        1, "kalshi-demo:portfolio:0", "USD",
        PerOrderRiskLimits(D("10"), D("10"), True, deviation_cap, 1_000),
        PerMarketRiskLimits(D("20"), D("20"), 10, D("20"), D("20")),
        AccountRiskLimits(D("100"), 50, D("100"), 0, D("0")),
        FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
        StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
        VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
    )


ONE_CENT_GRID = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
TWO_STEP_GRID = (
    PriceRangeV1(D("0"), D("0.50"), D("0.01")),
    PriceRangeV1(D("0.50"), D("1.00"), D("0.05")),
)


def config(*, spread: Decimal = D("0.02")) -> MinimalMarketMakerConfigV1:
    return build_market_maker_config(
        strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1", minimum_spread_usd=spread,
    )


def book_snapshot(*, yes_bid: Decimal = D("0.40"), no_bid: Decimal = D("0.50"), ticker: str = "TICK-1") -> KalshiNativeOrderBookSnapshot:
    return KalshiNativeOrderBookSnapshot(
        environment="KALSHI_DEMO", market_ticker=ticker, method="GET",
        route_template="/x", full_request_path="/x", endpoint_classification="PUBLIC",
        request_timestamp_ms=1, request_started_monotonic_ns=1, request_completed_monotonic_ns=2,
        yes_levels=(KalshiNativeOrderBookLevel(yes_bid, D("100")),),
        no_levels=(KalshiNativeOrderBookLevel(no_bid, D("100")),),
        canonical_level_ordering="ASCENDING", response_byte_length=10, response_sha256="a" * 64,
        raw_openapi_sha256="b" * 64, source_binding_record_sha256="c" * 64,
        request_count=1, retry_count=0, redirect_count=0,
        gustavo_execution_authorization_id="auth1", expected_implementation_commit="d" * 40,
        specification_sha256="e" * 64,
    ).with_canonical_identity()


PROC = "proc_" + "1" * 32


def fresh(sha: str = "f" * 64, *, monotonic_ns: int = 1_000_000_000) -> FreshnessStampV1:
    return FreshnessStampV1(PROC, "2026-08-15T00:00:00.000000Z", monotonic_ns, "NONE", None, sha)


def neutral_truth() -> MarketMakerEconomicTruthV1:
    return build_economic_truth(
        signed_inventory_state="KNOWN",
        signed_net_position_contracts=D("0"),
        market_economic_state=MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"),
        fill_history_completeness="COMPLETE",
        reconciliation_completeness="COMPLETE",
    )


def make_input(
    *,
    ranges=ONE_CENT_GRID,
    truth: MarketMakerEconomicTruthV1 | None = None,
    yes_bid: Decimal = D("0.40"),
    no_bid: Decimal = D("0.50"),
    cfg: MinimalMarketMakerConfigV1 | None = None,
    working_orders=(),
    slot_classifications=None,
    now_monotonic_ns: int = 1_000_000_500,
    book_freshness: FreshnessStampV1 | None = None,
    reconciliation_freshness: FreshnessStampV1 | None = None,
    risk_control_state: str = "WRITER_ELIGIBLE",
    risk_cfg: RiskLimitConfigV1 | None = None,
) -> MarketMakerInputV1:
    cfg = cfg or config()
    risk_cfg = risk_cfg if risk_cfg is not None else risk_config()
    truth = truth if truth is not None else neutral_truth()
    snap = book_snapshot(yes_bid=yes_bid, no_bid=no_bid, ticker=cfg.market_ticker)
    book_fresh = book_freshness or fresh("f" * 64)
    recon_fresh = reconciliation_freshness or fresh("a" * 64)
    slots = slot_classifications or {
        QuoteSlot.LOWER_YES_BID.value: SlotClassification.ABSENT.value,
        QuoteSlot.UPPER_YES_ASK.value: SlotClassification.ABSENT.value,
    }
    return MarketMakerInputV1(
        strategy_config=cfg, book_snapshot=snap, book_snapshot_sha256=snap.canonical_snapshot_sha256,
        book_freshness=book_fresh, price_ranges=ranges, price_grid_sha256=compute_price_grid_sha256(ranges),
        risk_control_state=risk_control_state, risk_state_epoch=1, risk_config=risk_cfg,
        risk_config_sha256=risk_cfg.sha256, reconciliation_snapshot_sha256="1" * 64,
        reconciliation_freshness=recon_fresh, economic_truth=truth, strategy_working_orders=working_orders,
        slot_classifications=slots, process_instance_id=PROC, now_monotonic_ns=now_monotonic_ns,
        now_utc="2026-08-15T00:00:00.000000Z",
    )


# ---------------------------------------------------------------------------
# A. Config
# ---------------------------------------------------------------------------


def test_config_hash_deterministic_and_recomputed() -> None:
    one = config()
    two = config()
    assert one.config_sha256 == two.config_sha256
    assert len(one.config_sha256) == 64


def test_config_rejects_bad_strategy_instance_id() -> None:
    with pytest.raises(MarketMakerInputError):
        build_market_maker_config(strategy_instance_id="not-valid", market_ticker="T", minimum_spread_usd=D("0.02"))


@pytest.mark.parametrize("bad_spread", [D("0"), D("1"), D("1.5"), D("-0.01"), D("0.02345")])
def test_config_rejects_invalid_spread(bad_spread: Decimal) -> None:
    with pytest.raises(MarketMakerInputError):
        build_market_maker_config(strategy_instance_id="mm_" + "1" * 32, market_ticker="T", minimum_spread_usd=bad_spread)


def test_config_rejects_float_spread() -> None:
    with pytest.raises(MarketMakerInputError):
        MinimalMarketMakerConfigV1(
            1, "mm_" + "1" * 32, "T", D("1.00"), D("1.00"), 0.02,  # type: ignore[arg-type]
            2, D("1.000000"), "SUPPRESS_BOTH", "ACCEPTED_GTC_POST_ONLY_LIFECYCLE", "0" * 64,
        )


def test_config_hash_mismatch_rejected() -> None:
    good = config()
    with pytest.raises(MarketMakerInputError):
        MinimalMarketMakerConfigV1(
            good.schema_revision, good.strategy_instance_id, good.market_ticker, good.quote_quantity,
            good.inventory_suppress_threshold_contracts, good.minimum_spread_usd,
            good.keep_reprice_distance_grid_steps, good.max_strategy_target_working_exposure_usd,
            good.locked_book_policy, good.quote_tif_policy, "0" * 64,
        )


# ---------------------------------------------------------------------------
# B. Economic truth (MM-TEST-013B / MM-CORR-002)
# ---------------------------------------------------------------------------


def test_known_equal_signed_position_is_valid() -> None:
    truth = build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=D("1.0"),
        market_economic_state=MarketEconomicState(D("0"), D("1.00"), D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"), fill_history_completeness="COMPLETE",
        reconciliation_completeness="COMPLETE",
    )
    assert truth.signed_net_position_contracts == D("1.0")


@pytest.mark.parametrize("strategy_value,state_value", [(D("1"), D("2")), (D("-1"), D("1")), (D("2"), D("-2"))])
def test_known_mismatch_signed_position_rejected(strategy_value: Decimal, state_value: Decimal) -> None:
    with pytest.raises(MarketMakerInputError) as caught:
        build_economic_truth(
            signed_inventory_state="KNOWN", signed_net_position_contracts=strategy_value,
            market_economic_state=MarketEconomicState(D("0"), state_value, D("0"), D("0"), D("0"), 0, D("0")),
            unresolved_write_exposure_usd=D("0"), fill_history_completeness="COMPLETE",
            reconciliation_completeness="COMPLETE",
        )
    assert caught.value.reason_code == ReasonCode.INPUT_SIGNED_INVENTORY_TRUTH_MISMATCH.value


def test_unknown_requires_null_null_shape() -> None:
    truth = build_economic_truth(
        signed_inventory_state="UNKNOWN", unresolved_write_exposure_usd="UNKNOWN_UNBOUNDED",
        fill_history_completeness="INCOMPLETE", reconciliation_completeness="INCOMPLETE",
    )
    assert truth.signed_net_position_contracts is None
    assert truth.market_economic_state is None
    assert len(truth.economic_truth_sha256) == 64


def test_unknown_with_finite_state_rejected() -> None:
    with pytest.raises(MarketMakerInputError) as caught:
        build_economic_truth(
            signed_inventory_state="UNKNOWN",
            market_economic_state=MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0")),
            unresolved_write_exposure_usd="UNKNOWN_UNBOUNDED", fill_history_completeness="INCOMPLETE",
            reconciliation_completeness="INCOMPLETE",
        )
    assert caught.value.reason_code == ReasonCode.INPUT_UNKNOWN_INVENTORY_SHAPE_INVALID.value


def test_unknown_with_finite_signed_value_rejected() -> None:
    with pytest.raises(MarketMakerInputError):
        build_economic_truth(
            signed_inventory_state="UNKNOWN", signed_net_position_contracts=D("0"),
            unresolved_write_exposure_usd="UNKNOWN_UNBOUNDED", fill_history_completeness="INCOMPLETE",
            reconciliation_completeness="INCOMPLETE",
        )


def test_economic_truth_hash_mismatch_rejected() -> None:
    good = neutral_truth()
    with pytest.raises(MarketMakerInputError):
        MarketMakerEconomicTruthV1(
            good.schema_revision, good.signed_inventory_state, good.signed_net_position_contracts,
            good.unresolved_write_exposure_usd, good.unresolved_write_request_ids,
            good.protected_unresolved_legacy_write_count, good.unresolved_write_count,
            good.fill_history_completeness, good.fill_identity_conflict_ids,
            good.reconciliation_completeness, good.market_economic_state, "0" * 64,
        )


def test_decimal_scale_equivalence_is_equality() -> None:
    assert D("1.0") == D("1.00")
    truth_a = build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=D("1.0"),
        market_economic_state=MarketEconomicState(D("0"), D("1.00"), D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"), fill_history_completeness="COMPLETE",
        reconciliation_completeness="COMPLETE",
    )
    truth_b = build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=D("1.00"),
        market_economic_state=MarketEconomicState(D("0"), D("1.0"), D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"), fill_history_completeness="COMPLETE",
        reconciliation_completeness="COMPLETE",
    )
    assert truth_a.economic_truth_sha256 == truth_b.economic_truth_sha256


# ---------------------------------------------------------------------------
# C. Grid helpers and price-grid hash (MM-GRID, MM-TEST-001/012C)
# ---------------------------------------------------------------------------


def test_grid_helpers_exact() -> None:
    assert grid_floor(D("0.455"), ONE_CENT_GRID) == D("0.45")
    assert grid_ceil(D("0.455"), ONE_CENT_GRID) == D("0.46")
    assert grid_prev(D("0.45"), ONE_CENT_GRID) == D("0.44")
    assert grid_next(D("0.45"), ONE_CENT_GRID) == D("0.46")
    assert grid_distance(D("0.40"), D("0.43"), ONE_CENT_GRID) == 3
    assert grid_distance(D("0.40"), D("0.40"), ONE_CENT_GRID) == 0


def test_grid_helpers_adjacent_different_steps() -> None:
    # Crossing the 0.50 boundary between a 1-cent and a 5-cent range.
    assert grid_next(D("0.49"), TWO_STEP_GRID) == D("0.50")
    assert grid_next(D("0.50"), TWO_STEP_GRID) == D("0.55")
    assert grid_prev(D("0.55"), TWO_STEP_GRID) == D("0.50")
    assert grid_prev(D("0.50"), TWO_STEP_GRID) == D("0.49")


def test_grid_helpers_none_at_boundary() -> None:
    assert grid_prev(D("0"), ONE_CENT_GRID) is None
    assert grid_next(D("1.00"), ONE_CENT_GRID) is None
    assert grid_floor(D("-1"), ONE_CENT_GRID) is None
    assert grid_ceil(D("2"), ONE_CENT_GRID) is None


def test_price_grid_hash_deterministic_and_scale_insensitive() -> None:
    a = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    b = (PriceRangeV1(D("0.0"), D("1.0000"), D("0.010")),)
    assert compute_price_grid_sha256(a) == compute_price_grid_sha256(b)


def test_price_grid_hash_changes_with_step() -> None:
    a = (PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
    b = (PriceRangeV1(D("0"), D("1.00"), D("0.02")),)
    assert compute_price_grid_sha256(a) != compute_price_grid_sha256(b)


def test_price_grid_hash_preserves_shared_boundary_ranges_distinctly() -> None:
    assert compute_price_grid_sha256(TWO_STEP_GRID) != compute_price_grid_sha256((PriceRangeV1(D("0"), D("1.00"), D("0.01")),))


def test_price_ranges_reject_float_field() -> None:
    with pytest.raises(Exception):
        PriceRangeV1(0.0, D("1.00"), D("0.01"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# D. Quote algorithm and plan determinism (MM-QUOTE, MM-TEST-001/002)
# ---------------------------------------------------------------------------


def test_neutral_state_yields_two_sided_plan_with_exact_liability() -> None:
    plan = evaluate_market_maker_input(make_input())
    assert plan.plan_classification == PlanClassification.VALID_DESIRED_STATE.value
    assert plan.lower_quote is not None and plan.upper_quote is not None
    assert plan.lower_quote.venue_side == "bid" and plan.lower_quote.outcome_side == "YES"
    assert plan.upper_quote.venue_side == "ask" and plan.upper_quote.outcome_side == "NO"
    lower_liability = plan.lower_quote.quantity * plan.lower_quote.yes_price
    upper_liability = plan.upper_quote.quantity * (Decimal("1.0000") - plan.upper_quote.yes_price)
    assert lower_liability == D("1.00") * plan.lower_quote.yes_price
    assert upper_liability == D("1.00") * (Decimal("1.0000") - plan.upper_quote.yes_price)


def test_plan_determinism_same_input_same_hash() -> None:
    input_ = make_input()
    plan1 = evaluate_market_maker_input(input_)
    plan2 = evaluate_market_maker_input(input_)
    assert plan1.plan_sha256 == plan2.plan_sha256
    assert plan1.plan_input_sha256 == plan2.plan_input_sha256


def test_plan_identity_changes_with_book_identity() -> None:
    plan_a = evaluate_market_maker_input(make_input(yes_bid=D("0.40")))
    plan_b = evaluate_market_maker_input(make_input(yes_bid=D("0.41")))
    assert plan_a.plan_input_sha256 != plan_b.plan_input_sha256
    assert plan_a.plan_sha256 != plan_b.plan_sha256


def test_locked_book_suppresses_both_with_sole_reason() -> None:
    plan = evaluate_market_maker_input(make_input(yes_bid=D("0.50"), no_bid=D("0.50")))
    assert plan.plan_classification == PlanClassification.VALID_DESIRED_STATE.value
    assert plan.lower_quote is None and plan.upper_quote is None
    assert plan.reason_codes == (ReasonCode.BOTH_SUPPRESSED_LOCKED_BOOK.value,)


def test_crossed_book_yields_no_new_quote_plan() -> None:
    plan = evaluate_market_maker_input(make_input(yes_bid=D("0.60"), no_bid=D("0.60")))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert plan.lower_quote is None and plan.upper_quote is None


def test_stale_book_yields_no_new_quote_plan() -> None:
    stale = fresh("f" * 64, monotonic_ns=0)
    plan = evaluate_market_maker_input(make_input(book_freshness=stale, now_monotonic_ns=10_000_000_000))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_BOOK_STALE.value in plan.reason_codes


def test_stale_reconciliation_yields_no_new_quote_plan() -> None:
    stale = fresh("a" * 64, monotonic_ns=0)
    plan = evaluate_market_maker_input(make_input(reconciliation_freshness=stale, now_monotonic_ns=10_000_000_000))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_RECONCILIATION_STALE.value in plan.reason_codes


def test_price_grid_identity_mismatch_yields_no_new_quote_plan() -> None:
    input_ = make_input()
    tampered = replace(input_, price_grid_sha256="0" * 64)
    plan = evaluate_market_maker_input(tampered)
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_PRICE_GRID_INVALID.value in plan.reason_codes


# ---------------------------------------------------------------------------
# E. Inventory (MM-INV, MM-TEST-003)
# ---------------------------------------------------------------------------


def truth_known(position: Decimal) -> MarketMakerEconomicTruthV1:
    return build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=position,
        market_economic_state=MarketEconomicState(D("0"), position, D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"), fill_history_completeness="COMPLETE",
        reconciliation_completeness="COMPLETE",
    )


def test_inventory_at_positive_boundary_still_allows_lower() -> None:
    # I=0, fresh lower candidate -> extreme=+1.00, allowed at the boundary.
    plan = evaluate_market_maker_input(make_input(truth=truth_known(D("0"))))
    assert plan.lower_quote is not None


def test_inventory_above_positive_extreme_suppresses_lower() -> None:
    plan = evaluate_market_maker_input(make_input(truth=truth_known(D("0.01"))))
    assert plan.lower_quote is None
    assert ReasonCode.LOWER_SUPPRESSED_INVENTORY.value in plan.reason_codes
    assert plan.upper_quote is not None


def test_inventory_below_negative_extreme_suppresses_upper() -> None:
    plan = evaluate_market_maker_input(make_input(truth=truth_known(D("-0.01"))))
    assert plan.upper_quote is None
    assert ReasonCode.UPPER_SUPPRESSED_INVENTORY.value in plan.reason_codes
    assert plan.lower_quote is not None


def test_unknown_inventory_yields_no_new_quote_plan() -> None:
    unknown_truth = build_economic_truth(
        signed_inventory_state="UNKNOWN", unresolved_write_exposure_usd=D("0"),
        fill_history_completeness="COMPLETE", reconciliation_completeness="COMPLETE",
    )
    plan = evaluate_market_maker_input(make_input(truth=unknown_truth))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert plan.signed_inventory_state == "UNKNOWN"
    assert plan.signed_net_position_contracts is None


def test_unknown_unbounded_exposure_yields_no_new_quote_plan() -> None:
    unbounded_truth = build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=D("0"),
        market_economic_state=MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd="UNKNOWN_UNBOUNDED", fill_history_completeness="COMPLETE",
        reconciliation_completeness="COMPLETE",
    )
    plan = evaluate_market_maker_input(make_input(truth=unbounded_truth))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_EXPOSURE_UNKNOWN_UNBOUNDED.value in plan.reason_codes


def test_unresolved_strategy_write_blocks_plan() -> None:
    truth = build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=D("0"),
        market_economic_state=MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"), unresolved_write_request_ids=("req_" + "1" * 32,),
        fill_history_completeness="COMPLETE", reconciliation_completeness="COMPLETE",
    )
    plan = evaluate_market_maker_input(make_input(truth=truth))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_UNRESOLVED_STRATEGY_WRITE.value in plan.reason_codes


def test_fill_identity_conflict_blocks_plan() -> None:
    truth = build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=D("0"),
        market_economic_state=MarketEconomicState(D("0"), D("0"), D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"), fill_identity_conflict_ids=("fill_conflict_1",),
        fill_history_completeness="COMPLETE", reconciliation_completeness="COMPLETE",
    )
    plan = evaluate_market_maker_input(make_input(truth=truth))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_FILL_IDENTITY_CONFLICT.value in plan.reason_codes


def test_ownership_conflict_blocks_plan() -> None:
    slots = {
        QuoteSlot.LOWER_YES_BID.value: SlotClassification.CONFLICT.value,
        QuoteSlot.UPPER_YES_ASK.value: SlotClassification.ABSENT.value,
    }
    plan = evaluate_market_maker_input(make_input(slot_classifications=slots))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_STRATEGY_ORDER_OWNERSHIP_CONFLICT.value in plan.reason_codes


# ---------------------------------------------------------------------------
# Quote-generation identity (MM-PLAN-005)
# ---------------------------------------------------------------------------


def test_quote_generation_id_format_and_determinism() -> None:
    kwargs = dict(
        strategy_instance_id="mm_" + "1" * 32, market_ticker="TICK-1", quote_slot="LOWER_YES_BID",
        plan_input_sha256="a" * 64, venue_side="bid", outcome_side="YES", yes_price=D("0.44"), quantity=D("1.00"),
    )
    first = compute_quote_generation_id(**kwargs)
    second = compute_quote_generation_id(**kwargs)
    assert first == second
    assert first.startswith("qg_") and len(first) == 35
    changed = compute_quote_generation_id(**{**kwargs, "yes_price": D("0.45")})
    assert changed != first


# ---------------------------------------------------------------------------
# Finding 01 — non-WRITER_ELIGIBLE strategy behavior fails closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state", ["HALTED", "BOOT_HOLD", "SAFE_HELD", "QUIESCENT_HELD", "RECONCILING", "EMERGENCY_CANCELING"],
)
def test_non_writer_eligible_state_yields_no_new_quote_plan(state: str) -> None:
    plan = evaluate_market_maker_input(make_input(risk_control_state=state))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert plan.lower_quote is None and plan.upper_quote is None
    assert ReasonCode.INPUT_RISK_STATE_NOT_WRITER_ELIGIBLE.value in plan.reason_codes


def test_writer_eligible_state_is_unaffected_by_the_new_check() -> None:
    plan = evaluate_market_maker_input(make_input(risk_control_state="WRITER_ELIGIBLE"))
    assert plan.plan_classification == PlanClassification.VALID_DESIRED_STATE.value
    assert ReasonCode.INPUT_RISK_STATE_NOT_WRITER_ELIGIBLE.value not in plan.reason_codes


# ---------------------------------------------------------------------------
# Finding 02 — Revision-05 exact freshness identity
# ---------------------------------------------------------------------------


def _reference_stamp(**overrides) -> FreshnessStampV1:
    fields = dict(
        process_instance_id="proc_" + "1" * 32,
        received_at_utc="2026-08-15T12:00:00.000000Z",
        received_monotonic_ns=5_000_000_000,
        source_timestamp_kind="NONE",
        source_timestamp_utc=None,
        snapshot_sha256="a" * 64,
    )
    fields.update(overrides)
    return FreshnessStampV1(**fields)


def test_freshness_identity_exact_reference_vector() -> None:
    result = compute_mm_freshness_identity_sha256(_reference_stamp())
    assert result == "9659579b0636eeb469dd0bf341b4c1a2c4b220bdac18a3a79dd4fe3c9c17e10c"


def test_freshness_identity_deterministic_for_identical_stamp() -> None:
    assert compute_mm_freshness_identity_sha256(_reference_stamp()) == compute_mm_freshness_identity_sha256(_reference_stamp())


def test_freshness_identity_differs_from_snapshot_hash() -> None:
    stamp = _reference_stamp()
    assert compute_mm_freshness_identity_sha256(stamp) != stamp.snapshot_sha256


def test_freshness_identity_changes_with_received_at_utc() -> None:
    base = compute_mm_freshness_identity_sha256(_reference_stamp())
    changed = compute_mm_freshness_identity_sha256(_reference_stamp(received_at_utc="2026-08-15T12:00:01.000000Z"))
    assert base != changed


def test_freshness_identity_changes_with_received_monotonic_ns() -> None:
    base = compute_mm_freshness_identity_sha256(_reference_stamp())
    changed = compute_mm_freshness_identity_sha256(_reference_stamp(received_monotonic_ns=5_000_000_001))
    assert base != changed


def test_freshness_identity_changes_with_source_timestamp() -> None:
    base = compute_mm_freshness_identity_sha256(_reference_stamp())
    changed = compute_mm_freshness_identity_sha256(
        _reference_stamp(source_timestamp_kind="VENUE_RFC3339_UTC", source_timestamp_utc="2026-08-15T12:00:00.000000Z")
    )
    assert base != changed


def test_freshness_identity_changes_with_process_instance_id() -> None:
    base = compute_mm_freshness_identity_sha256(_reference_stamp())
    changed = compute_mm_freshness_identity_sha256(_reference_stamp(process_instance_id="proc_" + "2" * 32))
    assert base != changed


def test_freshness_identity_changes_with_snapshot_sha256() -> None:
    base = compute_mm_freshness_identity_sha256(_reference_stamp())
    changed = compute_mm_freshness_identity_sha256(_reference_stamp(snapshot_sha256="b" * 64))
    assert base != changed


def test_freshness_identity_rejects_non_stamp_input() -> None:
    with pytest.raises(MarketMakerInputError):
        compute_mm_freshness_identity_sha256(object())  # type: ignore[arg-type]


def test_book_freshness_identity_change_moves_plan_input_hash_with_unchanged_snapshot() -> None:
    base_stamp = fresh("f" * 64, monotonic_ns=1_000_000_000)
    changed_stamp = FreshnessStampV1(
        base_stamp.process_instance_id, "2026-08-15T00:00:00.000001Z", base_stamp.received_monotonic_ns,
        base_stamp.source_timestamp_kind, base_stamp.source_timestamp_utc, base_stamp.snapshot_sha256,
    )
    plan_a = evaluate_market_maker_input(make_input(book_freshness=base_stamp))
    plan_b = evaluate_market_maker_input(make_input(book_freshness=changed_stamp))
    assert base_stamp.snapshot_sha256 == changed_stamp.snapshot_sha256
    assert plan_a.plan_input_sha256 != plan_b.plan_input_sha256
    assert plan_a.book_freshness_identity_sha256 != plan_b.book_freshness_identity_sha256
    assert plan_a.source_book_snapshot_sha256 == plan_b.source_book_snapshot_sha256


def test_reconciliation_freshness_identity_change_moves_plan_input_hash_with_unchanged_snapshot() -> None:
    base_stamp = fresh("a" * 64, monotonic_ns=1_000_000_000)
    changed_stamp = FreshnessStampV1(
        base_stamp.process_instance_id, "2026-08-15T00:00:00.000001Z", base_stamp.received_monotonic_ns,
        base_stamp.source_timestamp_kind, base_stamp.source_timestamp_utc, base_stamp.snapshot_sha256,
    )
    plan_a = evaluate_market_maker_input(make_input(reconciliation_freshness=base_stamp))
    plan_b = evaluate_market_maker_input(make_input(reconciliation_freshness=changed_stamp))
    assert base_stamp.snapshot_sha256 == changed_stamp.snapshot_sha256
    assert plan_a.plan_input_sha256 != plan_b.plan_input_sha256
    assert plan_a.reconciliation_freshness_identity_sha256 != plan_b.reconciliation_freshness_identity_sha256
    assert plan_a.reconciliation_snapshot_sha256 == plan_b.reconciliation_snapshot_sha256


def test_expired_book_freshness_remains_unusable_regardless_of_identity() -> None:
    stale = fresh("f" * 64, monotonic_ns=0)
    plan = evaluate_market_maker_input(make_input(book_freshness=stale, now_monotonic_ns=10_000_000_000))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_BOOK_STALE.value in plan.reason_codes


def test_prior_process_book_freshness_remains_unusable() -> None:
    foreign = FreshnessStampV1("proc_" + "9" * 32, "2026-08-15T00:00:00.000000Z", 1_000_000_000, "NONE", None, "f" * 64)
    plan = evaluate_market_maker_input(make_input(book_freshness=foreign))
    assert plan.plan_classification == PlanClassification.NO_NEW_QUOTE_PLAN.value
    assert ReasonCode.INPUT_BOOK_STALE.value in plan.reason_codes


# ---------------------------------------------------------------------------
# CORRECTION_07 C07-MM-01..04 -- reference-price deviation cap against the
# ACTUAL installed strategy.
#
# These tests exercise `src/arb/venues/kalshi/minimal_market_maker.py`
# unchanged.  C07-PRICE-006 forbids modifying that source for this
# correction, and C07-13 lists it as a protected, non-writable dependency:
# the dynamic price-reasonability theorem is already implemented there and
# only needs to be proven.
#
# All four cases run the real `evaluate_market_maker_input` pipeline, so the
# candidate prices are the strategy's own grid/maker-adjusted candidates, not
# hand-written stand-ins.
# ---------------------------------------------------------------------------


def _reference_for(*, yes_bid: Decimal, no_bid: Decimal) -> OrderbookReferenceV1:
    """The exact reference the strategy itself derives from this book."""
    return build_orderbook_reference(((yes_bid, D("100")),), ((no_bid, D("100")),))


# Scenario A: one-cent grid, spread 0.02, book 0.40 / 0.50.
#   reference_yes_price = 0.4500, lower candidate 0.44, upper candidate 0.46,
#   so D_candidate is exactly 0.0100 on both sides.
_A_YES_BID = D("0.40")
_A_NO_BID = D("0.50")
_A_SPREAD = D("0.02")
_A_D_CANDIDATE = D("0.0100")

# Scenario B: two-step grid (0.01 below 0.50, 0.05 above), spread 0.02,
#   book 0.50 / 0.40.  reference_yes_price = 0.5500 and the coarse 0.05 grid
#   pushes the candidates to 0.50 / 0.60, so D_candidate is exactly 0.0500 --
#   five times the half-spread.
_B_YES_BID = D("0.50")
_B_NO_BID = D("0.40")
_B_SPREAD = D("0.02")
_B_D_CANDIDATE = D("0.0500")


def _plan_with_cap(cap: Decimal, *, ranges, yes_bid: Decimal, no_bid: Decimal, spread: Decimal):
    return evaluate_market_maker_input(make_input(
        ranges=ranges, yes_bid=yes_bid, no_bid=no_bid, cfg=config(spread=spread),
        risk_cfg=risk_config(deviation_cap=cap),
    ))


def test_c07_mm_01_zero_cap_suppresses_an_otherwise_surviving_candidate() -> None:
    """C07-MM-01 / C07-PRICE-004: with a strictly positive strategy spread the
    strategy DOES produce real lower/upper candidates, but a proof-only zero
    deviation cap suppresses both by price reasonability.

    This is the exact defect C07 corrects: a fixed cap of zero is not a
    write-capable Strategy-1 selection because it admits no actual candidate.
    """

    # The same book/spread with a positive cap yields two real candidates ...
    baseline = _plan_with_cap(
        D("0.10"), ranges=ONE_CENT_GRID, yes_bid=_A_YES_BID, no_bid=_A_NO_BID, spread=_A_SPREAD,
    )
    assert baseline.plan_classification == PlanClassification.VALID_DESIRED_STATE.value
    assert baseline.lower_quote is not None and baseline.upper_quote is not None

    reference = _reference_for(yes_bid=_A_YES_BID, no_bid=_A_NO_BID)
    assert abs(baseline.lower_quote.yes_price - reference.reference_yes_price) == _A_D_CANDIDATE
    assert abs(baseline.upper_quote.yes_price - reference.reference_yes_price) == _A_D_CANDIDATE

    # ... and a zero cap suppresses both of those very candidates.
    plan = _plan_with_cap(
        D("0"), ranges=ONE_CENT_GRID, yes_bid=_A_YES_BID, no_bid=_A_NO_BID, spread=_A_SPREAD,
    )
    assert plan.lower_quote is None
    assert plan.upper_quote is None
    assert ReasonCode.LOWER_SUPPRESSED_PRICE_REASONABILITY.value in plan.reason_codes
    assert ReasonCode.UPPER_SUPPRESSED_PRICE_REASONABILITY.value in plan.reason_codes


def test_c07_mm_02_cap_exactly_equal_to_d_candidate_passes() -> None:
    """C07-MM-02 / C07-PRICE-003 / C07-12: equality is inclusive.

    ``selected_cap == D_candidate`` survives price reasonability, subject to
    every other strategy gate (which this book/grid also satisfies).
    """

    plan = _plan_with_cap(
        _A_D_CANDIDATE, ranges=ONE_CENT_GRID, yes_bid=_A_YES_BID, no_bid=_A_NO_BID, spread=_A_SPREAD,
    )
    reference = _reference_for(yes_bid=_A_YES_BID, no_bid=_A_NO_BID)

    assert plan.plan_classification == PlanClassification.VALID_DESIRED_STATE.value
    assert plan.lower_quote is not None and plan.upper_quote is not None
    assert abs(plan.lower_quote.yes_price - reference.reference_yes_price) == _A_D_CANDIDATE
    assert abs(plan.upper_quote.yes_price - reference.reference_yes_price) == _A_D_CANDIDATE
    assert ReasonCode.LOWER_SUPPRESSED_PRICE_REASONABILITY.value not in plan.reason_codes
    assert ReasonCode.UPPER_SUPPRESSED_PRICE_REASONABILITY.value not in plan.reason_codes


def test_c07_mm_03_cap_one_exact_decimal_below_d_candidate_suppresses() -> None:
    """C07-MM-03 / C07-12: one exact Decimal increment below the boundary
    suppresses the candidate.  The comparison is exact Decimal arithmetic and
    C07 imposes no new quantization on this leaf, so the below-boundary value
    is constructed as an exact smaller Decimal."""

    below = _A_D_CANDIDATE - D("0.0001")
    assert below < _A_D_CANDIDATE

    plan = _plan_with_cap(
        below, ranges=ONE_CENT_GRID, yes_bid=_A_YES_BID, no_bid=_A_NO_BID, spread=_A_SPREAD,
    )
    assert plan.lower_quote is None
    assert plan.upper_quote is None
    assert ReasonCode.LOWER_SUPPRESSED_PRICE_REASONABILITY.value in plan.reason_codes
    assert ReasonCode.UPPER_SUPPRESSED_PRICE_REASONABILITY.value in plan.reason_codes


def test_c07_mm_04_cap_must_not_be_derived_from_half_the_spread() -> None:
    """C07-MM-04 / C07-PRICE-005: no half-spread derivation is valid.

    On a coarse price grid the maker/grid adjustment moves the actual
    candidate well away from ``reference +/- minimum_spread_usd / 2``.  Here
    ``D_candidate`` is 0.0500 while ``minimum_spread_usd / 2`` is 0.0100, so a
    cap auto-derived as half the spread would suppress a candidate the user's
    real selection admits.  The cap is therefore an independent user choice
    and is never inferred from the strategy spread.
    """

    reference = _reference_for(yes_bid=_B_YES_BID, no_bid=_B_NO_BID)
    half_spread = _B_SPREAD / D("2")

    baseline = _plan_with_cap(
        D("0.10"), ranges=TWO_STEP_GRID, yes_bid=_B_YES_BID, no_bid=_B_NO_BID, spread=_B_SPREAD,
    )
    assert baseline.lower_quote is not None and baseline.upper_quote is not None
    lower_deviation = abs(baseline.lower_quote.yes_price - reference.reference_yes_price)
    upper_deviation = abs(baseline.upper_quote.yes_price - reference.reference_yes_price)
    assert lower_deviation == _B_D_CANDIDATE
    assert upper_deviation == _B_D_CANDIDATE
    # The load-bearing inequality: the real deviation is NOT the half-spread.
    assert lower_deviation != half_spread
    assert upper_deviation != half_spread

    # A half-spread-derived cap would wrongly suppress both real candidates.
    derived = _plan_with_cap(
        half_spread, ranges=TWO_STEP_GRID, yes_bid=_B_YES_BID, no_bid=_B_NO_BID, spread=_B_SPREAD,
    )
    assert derived.lower_quote is None
    assert derived.upper_quote is None
    assert ReasonCode.LOWER_SUPPRESSED_PRICE_REASONABILITY.value in derived.reason_codes
    assert ReasonCode.UPPER_SUPPRESSED_PRICE_REASONABILITY.value in derived.reason_codes

    # The user's own exact selection admits them.
    selected = _plan_with_cap(
        _B_D_CANDIDATE, ranges=TWO_STEP_GRID, yes_bid=_B_YES_BID, no_bid=_B_NO_BID, spread=_B_SPREAD,
    )
    assert selected.lower_quote is not None
    assert selected.upper_quote is not None


def test_c07_mm_05_price_reasonable_is_the_exact_inclusive_deviation_predicate() -> None:
    """C07-PRICE-003 directly on the installed pure predicate: equality
    passes, any excess fails, and the cap is never widened."""

    reference = _reference_for(yes_bid=_A_YES_BID, no_bid=_A_NO_BID)
    candidate = D("0.44")
    deviation = abs(candidate - reference.reference_yes_price)

    assert deviation == _A_D_CANDIDATE
    assert price_reasonable(candidate, reference, deviation) is True
    assert price_reasonable(candidate, reference, deviation - D("0.0001")) is False
    assert price_reasonable(candidate, reference, deviation + D("0.0001")) is True
    assert price_reasonable(candidate, reference, D("0")) is False
