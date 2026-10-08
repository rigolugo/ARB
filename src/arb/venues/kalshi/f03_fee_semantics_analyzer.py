"""Pure offline analyzer for the bounded R1-D07 F03 Demo fee-semantics test.

Implements the analyzer half of
``KALSHI_DEMO_R1_D07_F03_DEMO_FEE_SEMANTICS_TEST_SPEC_01_CORRECTION_02.md``
(sections 2, 7, 8, 12, 15, 17, 18, 24 and 25): exact Decimal fee arithmetic,
explicitly non-authoritative hidden-accumulator model hypotheses, interval
cash/API aggregate consistency, guarded single-fill identification, scoped
aggregate hypothesis discrimination, chronology/observational-equivalence
handling, the five QF03 decisions, strict evidence schema validation and the
shared-evidence sanitization scan.

This module is pure: it owns no network, signer, credential, ledger, file or
clock access and performs no import-time activity beyond constant
construction.  It never infers a per-fill net fee from aggregate equality,
never treats a model hypothesis as observed venue state, never assigns the
PDF table's intended account class from a numeric coincidence and never
closes F03 / P01-P09 / F07.  Every conclusion is scoped to the exact account
class, quantum, market, fee epoch, source edition and run interval supplied.
"""

from __future__ import annotations

import enum
import itertools
import json
import re
import uuid
from dataclasses import dataclass, field
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Clamped,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
from typing import Iterable, Mapping, Sequence, Tuple

# ---------------------------------------------------------------------------
# Section 2 -- controlling / supporting source identities (preserved raw bytes;
# no task-current freshness claim is made).
# ---------------------------------------------------------------------------

CONTROLLING_SPEC_ID = "KALSHI_DEMO_R1_D07_F03_DEMO_FEE_SEMANTICS_TEST_SPEC_01_CORRECTION_02"
CONTROLLING_SPEC_BYTES = 72523
CONTROLLING_SPEC_SHA256 = "de75554e381c0ab521878ac780ec84749fa54f68237ad9db51480e33527c93a4"

SOURCE_IDENTITIES: Mapping[str, Tuple[int, str]] = {
    "fee_rounding.md": (3786, "0e75e087de5e90897e59a19a13ccb5d554a417177a28fc3a9a05fee18152f669"),
    "kalshi-fee-schedule.pdf": (281129, "c326a69f596a11e8f8be2620402d39a8d4823920c21cc97c93a114d862699601"),
    "order_entry.md": (21157, "8ffdf6aa9eaea47d76256be16b8897bc47fd0742bdff54c44a5eea06786262f9"),
    "get_fills.md": (13145, "43bc3b8c639a91d222c4077414ee093b83c1b8c510dbca52f24a2e2939265303"),
    "changelog.md": (223587, "f4cfe650f7834686fa30629551171e5350e9f8d1b98eb41e89ff5eb52377f26b"),
    "FINDINGS_FOR_BRUNO.md": (11096, "58bd5fb50dc47858d4fb4844f0a2560e4d3f83fb0b00a32ccee9ddb956a9fb15"),
    "KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml": (
        325930, "99bdf4093d7eced607ba8b48cc99e3da862c35d99afa2a0c0f63f14eab9237ed",
    ),
}
FEE_SCHEDULE_EDITION = "2026-07-07"

# Evidence classes (F03-SRC-001): source constraints, mathematical hypotheses
# and observed results are always separate.
EVIDENCE_CLASS_SOURCE_CONSTRAINT = "SOURCE_CONSTRAINT"
EVIDENCE_CLASS_MODEL_HYPOTHESIS = "MODEL_HYPOTHESIS"
EVIDENCE_CLASS_OBSERVED = "OBSERVED_DEMO_RESULT"

# ---------------------------------------------------------------------------
# Section 7 -- exact source constants.
# ---------------------------------------------------------------------------

K_TAKER = Decimal("0.07")
K_MAKER = Decimal("0.0175")
QUANTUM_DIRECT = Decimal("0.0001")
QUANTUM_NON_DIRECT = Decimal("0.01")
TRADE_FEE_STEP = Decimal("0.000001")
MIN_FILL_QUANTITY = Decimal("0.01")
CREATE_QUANTITY = Decimal("1.00")
MAX_LIMIT_PRICE = Decimal("0.8000")
PDF_TABLE_ONE_CONTRACT_HALF_PRICE_FEE = Decimal("0.02")
MAX_POSITIVE_FILLS_PER_ORDER = 100
SPEC_TWO_ORDER_OUTLAY_BOUND_USD = Decimal("3.6352")
DISPATCH_OUTLAY_CEILING_USD = Decimal("10.00")
SPEC_TOTAL_ACQUIRED_QUANTITY_MAX = Decimal("2.00")
MAX_ORDERINGS_ENUMERATED = 5040

# ---------------------------------------------------------------------------
# Closed enumerations (section 8 / 12 / 17).
# ---------------------------------------------------------------------------


class F03AnalyzerError(ValueError):
    """Fail-closed analyzer/schema error.  ``code`` is a fixed classification;
    no message ever carries a balance value or a secret."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


class HaltCode(enum.StrEnum):
    CANONICAL_BASE_MISMATCH = "CANONICAL_BASE_MISMATCH"
    SOURCE_BINDING_UNRESOLVED = "SOURCE_BINDING_UNRESOLVED"
    DEMO_ORIGIN_MISMATCH = "DEMO_ORIGIN_MISMATCH"
    PRODUCTION_ORIGIN_PRESENT = "PRODUCTION_ORIGIN_PRESENT"
    ACCOUNT_CLASS_UNRESOLVED = "ACCOUNT_CLASS_UNRESOLVED"
    TARGET_DOMAIN_INELIGIBLE = "TARGET_DOMAIN_INELIGIBLE"
    HISTORICAL_PRIMARY_DOMAIN_PROHIBITED = "HISTORICAL_PRIMARY_DOMAIN_PROHIBITED"
    BASELINE_OPEN_ORDER_CONFLICT = "BASELINE_OPEN_ORDER_CONFLICT"
    BASELINE_UNKNOWN_EXPOSURE = "BASELINE_UNKNOWN_EXPOSURE"
    UNRELATED_ACTIVITY_PRESENT = "UNRELATED_ACTIVITY_PRESENT"
    MARKET_NOT_DISCRIMINATING = "MARKET_NOT_DISCRIMINATING"
    FEE_REGIME_UNRESOLVED = "FEE_REGIME_UNRESOLVED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ACTIVE_ORDER_LIMIT_VIOLATION = "ACTIVE_ORDER_LIMIT_VIOLATION"
    WRITE_LIMIT_CONSUMED = "WRITE_LIMIT_CONSUMED"
    CREATE_RESULT_AMBIGUOUS = "CREATE_RESULT_AMBIGUOUS"
    CANCEL_RESULT_AMBIGUOUS = "CANCEL_RESULT_AMBIGUOUS"
    ORDER_RECONCILIATION_INCOMPLETE = "ORDER_RECONCILIATION_INCOMPLETE"
    FILL_PAGINATION_INCOMPLETE = "FILL_PAGINATION_INCOMPLETE"
    PAGINATION_LIMIT_EXHAUSTED = "PAGINATION_LIMIT_EXHAUSTED"
    FILL_DUPLICATE_CONFLICT = "FILL_DUPLICATE_CONFLICT"
    BALANCE_OBSERVATION_INCOMPLETE = "BALANCE_OBSERVATION_INCOMPLETE"
    BALANCE_CHECKPOINT_FAILED = "BALANCE_CHECKPOINT_FAILED"
    BALANCE_CHECKPOINT_NOT_STABLE = "BALANCE_CHECKPOINT_NOT_STABLE"
    BALANCE_TIMESTAMP_REGRESSION = "BALANCE_TIMESTAMP_REGRESSION"
    INSUFFICIENT_EXISTING_BALANCE = "INSUFFICIENT_EXISTING_BALANCE"
    MEASUREMENT_HYPOTHESIS_DISCREPANCY = "MEASUREMENT_HYPOTHESIS_DISCREPANCY"
    SOURCE_SCOPE_CONFLICT = "SOURCE_SCOPE_CONFLICT"
    OFFICIAL_SOURCE_CONFLICT = "OFFICIAL_SOURCE_CONFLICT"
    SCOPE_EXPANSION_REQUIRED = "SCOPE_EXPANSION_REQUIRED"
    RUN_DEADLINE_EXCEEDED = "RUN_DEADLINE_EXCEEDED"
    CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE = "CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE"
    EVIDENCE_SANITIZATION_FAILED = "EVIDENCE_SANITIZATION_FAILED"


assert len(HaltCode) == 33


class QuestionStatus(enum.StrEnum):
    OBSERVED_MATCH = "OBSERVED_MATCH"
    OBSERVED_CONFLICT = "OBSERVED_CONFLICT"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ScopeMode(enum.StrEnum):
    SINGLE_FILL = "SINGLE_FILL"
    AGGREGATE_HYPOTHESIS = "AGGREGATE_HYPOTHESIS"
    AGGREGATE_CONSISTENCY = "AGGREGATE_CONSISTENCY"
    SOURCE_SCOPE = "SOURCE_SCOPE"


class CashEvidenceIndependence(enum.StrEnum):
    SHARED_AGGREGATE_IDENTITY = "SHARED_AGGREGATE_IDENTITY"
    INDEPENDENT_SINGLE_FILL_INTERVAL = "INDEPENDENT_SINGLE_FILL_INTERVAL"
    NONE = "NONE"


class AggregateConsistencyState(enum.StrEnum):
    UNTESTED = "UNTESTED"
    AGGREGATE_MATCH = "AGGREGATE_MATCH"
    AGGREGATE_CONFLICT = "AGGREGATE_CONFLICT"
    INCONCLUSIVE = "INCONCLUSIVE"


class PerFillIdentificationState(enum.StrEnum):
    SINGLE_FILL_IDENTIFIED = "SINGLE_FILL_IDENTIFIED"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    CONFLICT = "CONFLICT"


class UniqueDiscriminatorState(enum.StrEnum):
    UNIQUE_MATCH = "UNIQUE_MATCH"
    EQUAL_PREDICTIONS = "EQUAL_PREDICTIONS"
    NO_MATCH = "NO_MATCH"
    INELIGIBLE = "INELIGIBLE"


class CheckpointState(enum.StrEnum):
    STABLE = "STABLE"
    NOT_STABLE = "NOT_STABLE"
    FAILED = "FAILED"


class PredicateState(enum.StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNRESOLVED = "UNRESOLVED"


class AccountClass(enum.StrEnum):
    DIRECT = "DIRECT"
    NON_DIRECT = "NON_DIRECT"
    UNRESOLVED = "UNRESOLVED"


class Initializer(enum.StrEnum):
    ZERO = "ZERO"
    PRIOR_MODELED_RESIDUAL = "PRIOR_MODELED_RESIDUAL"


class RebateRule(enum.StrEnum):
    MAXIMAL = "MAXIMAL"
    NONE = "NONE"


class TerminalRule(enum.StrEnum):
    NO_CREDIT = "NO_CREDIT"
    FLOOR_TO_H_CREDIT = "FLOOR_TO_H_CREDIT"


QUESTION_IDS: Tuple[str, ...] = ("QF03-01", "QF03-02", "QF03-03", "QF03-04", "QF03-05")

# ---------------------------------------------------------------------------
# Exact Decimal discipline (F03-MATH-001).  Every intermediate is computed in a
# >=50-digit context that traps any inexact/rounded result; ceil/floor to a
# grid use ``to_integral_value`` (which never signals) on an exact quotient.
# ---------------------------------------------------------------------------

_EXACT_CONTEXT = Context(
    prec=60, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
    traps=[InvalidOperation, DivisionByZero, Overflow, Underflow, Inexact, Rounded, Subnormal, Clamped],
)

_FIXED_POINT_DOLLARS_RE = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]{1,6})?")
_FIXED_POINT_COUNT_RE = re.compile(r"(0|[1-9][0-9]*)\.[0-9]{2}")
_CANONICAL_DECIMAL_RE = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")
_UUID4_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_CANONICAL_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z")


def _require_decimal(value: object, *, name: str, nonnegative: bool = False, positive: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", name)
    if nonnegative and value < 0:
        raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", name)
    if positive and value <= 0:
        raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", name)
    return value


def exact_mul(*values: Decimal) -> Decimal:
    with localcontext(_EXACT_CONTEXT):
        result = Decimal(1)
        for value in values:
            result = result * value
        return result


def exact_add(*values: Decimal) -> Decimal:
    with localcontext(_EXACT_CONTEXT):
        result = Decimal(0)
        for value in values:
            result = result + value
        return result


def exact_sub(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(_EXACT_CONTEXT):
        return left - right


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    _require_decimal(step, name="step", positive=True)
    with localcontext(_EXACT_CONTEXT):
        quotient = value / step
        return quotient.to_integral_value(rounding=ROUND_CEILING) * step


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    _require_decimal(step, name="step", positive=True)
    with localcontext(_EXACT_CONTEXT):
        quotient = value / step
        return quotient.to_integral_value(rounding=ROUND_FLOOR) * step


def floor_units(value: Decimal, step: Decimal) -> int:
    """Exact integer floor(value / step)."""
    _require_decimal(step, name="step", positive=True)
    with localcontext(_EXACT_CONTEXT):
        return int((value / step).to_integral_value(rounding=ROUND_FLOOR))


def canonical_decimal_text(value: Decimal) -> str:
    """Plain notation, no exponent, no trailing fractional zeros, no negative
    zero (identical rule to the installed balance bridge's canonical text)."""
    _require_decimal(value, name="canonical value")
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def parse_fixed_point_dollars(lexeme: object, *, name: str) -> Decimal:
    """Exact ``FixedPointDollars`` lexeme: no exponent/plus/whitespace/comma,
    at most six fractional digits; parsed from the ORIGINAL string."""
    if type(lexeme) is not str or _FIXED_POINT_DOLLARS_RE.fullmatch(lexeme) is None:
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", name)
    return Decimal(lexeme)


def parse_fixed_point_count(lexeme: object, *, name: str) -> Decimal:
    """Exact response ``FixedPointCount`` lexeme (responses always emit 2dp)."""
    if type(lexeme) is not str or _FIXED_POINT_COUNT_RE.fullmatch(lexeme) is None:
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", name)
    return Decimal(lexeme)


def parse_canonical_decimal(lexeme: object, *, name: str) -> Decimal:
    """Canonical exact decimal string used in shared evidence (no exponent, no
    trailing fractional zero, no plus sign, no float)."""
    if type(lexeme) is not str or _CANONICAL_DECIMAL_RE.fullmatch(lexeme) is None or lexeme == "-0":
        raise F03AnalyzerError("SCHEMA_DECIMAL_INVALID", name)
    return Decimal(lexeme)


def quantum_for_account_class(account_class: object) -> Decimal:
    if account_class == AccountClass.DIRECT:
        return QUANTUM_DIRECT
    if account_class == AccountClass.NON_DIRECT:
        return QUANTUM_NON_DIRECT
    raise F03AnalyzerError(HaltCode.ACCOUNT_CLASS_UNRESOLVED.value)


def role_coefficient(*, is_taker: object) -> Decimal:
    if type(is_taker) is not bool:
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", "is_taker")
    return K_TAKER if is_taker else K_MAKER


# ---------------------------------------------------------------------------
# Section 7 -- per-fill exact arithmetic and the explicit hidden-accumulator
# model hypothesis rows.  Every accumulator / rebate / net value below is a
# MODEL_HYPOTHESIS, never observed venue state.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PublishedFillArithmeticV1:
    """Published mechanics only: model fee, six-decimal trade fee, revenue,
    floor-aligned balance change and rounding fee (0 <= rounding_fee < h)."""

    quantity: Decimal
    price: Decimal
    k: Decimal
    multiplier: Decimal
    h: Decimal
    model_fee: Decimal
    trade_fee: Decimal
    revenue: Decimal
    aligned_change: Decimal
    rounding_fee: Decimal


def published_fill_arithmetic(
    *, quantity: Decimal, price: Decimal, k: Decimal, multiplier: Decimal, h: Decimal,
    model_fee_override: Decimal | None = None, revenue_override: Decimal | None = None,
) -> PublishedFillArithmeticV1:
    """model_fee = k*M*c*p*(1-p); trade_fee = ceil6(model_fee);
    revenue = -c*p; aligned = floor_h(revenue - trade_fee);
    rounding = revenue - trade_fee - aligned.

    The two override parameters exist only for the published literal vector
    (whose source states model_fee/revenue directly); they are never used by
    observed-fill analysis."""
    _require_decimal(h, name="h", positive=True)
    if model_fee_override is None or revenue_override is None:
        _require_decimal(quantity, name="quantity", positive=True)
        _require_decimal(price, name="price")
        if not (Decimal(0) < price < Decimal(1)):
            raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "price")
        _require_decimal(k, name="k", positive=True)
        _require_decimal(multiplier, name="multiplier", positive=True)
        model_fee = exact_mul(k, multiplier, quantity, price, exact_sub(Decimal(1), price))
        revenue = exact_mul(Decimal(-1), quantity, price)
    else:
        model_fee = _require_decimal(model_fee_override, name="model_fee", nonnegative=True)
        revenue = _require_decimal(revenue_override, name="revenue")
    trade_fee = ceil_to_step(model_fee, TRADE_FEE_STEP)
    aligned_change = floor_to_step(exact_sub(revenue, trade_fee), h)
    rounding_fee = exact_sub(exact_sub(revenue, trade_fee), aligned_change)
    if not (Decimal(0) <= rounding_fee < h):  # pragma: no cover - floor identity
        raise F03AnalyzerError("ARITHMETIC_INVARIANT_VIOLATED", "rounding_fee")
    return PublishedFillArithmeticV1(
        quantity, price, k, multiplier, h, model_fee, trade_fee, revenue, aligned_change, rounding_fee,
    )


@dataclass(frozen=True, slots=True)
class HypothesisRowV1:
    """One MODEL_HYPOTHESIS row (spec section 7 H_MAXIMAL / no-rebate)."""

    arithmetic: PublishedFillArithmeticV1
    rebate_rule: str
    accumulator_before_hypothesis: Decimal
    before_rebate_hypothesis: Decimal
    rebate_hypothesis: Decimal
    net_fee_hypothesis: Decimal
    accumulator_after_hypothesis: Decimal
    balance_change_hypothesis: Decimal
    evidence_class: str = EVIDENCE_CLASS_MODEL_HYPOTHESIS

    def as_canonical_mapping(self) -> dict:
        a = self.arithmetic
        return {
            "quantity": canonical_decimal_text(a.quantity),
            "price": canonical_decimal_text(a.price),
            "k": canonical_decimal_text(a.k),
            "M": canonical_decimal_text(a.multiplier),
            "h": canonical_decimal_text(a.h),
            "accumulator_before_hypothesis": canonical_decimal_text(self.accumulator_before_hypothesis),
            "model_fee": canonical_decimal_text(a.model_fee),
            "trade_fee": canonical_decimal_text(a.trade_fee),
            "revenue": canonical_decimal_text(a.revenue),
            "aligned_change": canonical_decimal_text(a.aligned_change),
            "rounding_fee": canonical_decimal_text(a.rounding_fee),
            "before_rebate_hypothesis": canonical_decimal_text(self.before_rebate_hypothesis),
            "rebate_hypothesis": canonical_decimal_text(self.rebate_hypothesis),
            "net_fee_hypothesis": canonical_decimal_text(self.net_fee_hypothesis),
            "accumulator_after_hypothesis": canonical_decimal_text(self.accumulator_after_hypothesis),
            "balance_change_hypothesis": canonical_decimal_text(self.balance_change_hypothesis),
        }


def hypothesis_row(
    arithmetic: PublishedFillArithmeticV1, *, accumulator_before: Decimal, rebate_rule: str,
) -> HypothesisRowV1:
    """Published constraints permit b >= 0 on the h-grid, b <= A_pre and
    b <= trade_fee + rounding_fee.  H_MAXIMAL picks the maximum such b; NONE
    picks b = 0.  Neither is asserted as venue policy."""
    _require_decimal(accumulator_before, name="accumulator_before", nonnegative=True)
    h = arithmetic.h
    a_pre = exact_add(accumulator_before, arithmetic.rounding_fee)
    fee_before_rebate = exact_add(arithmetic.trade_fee, arithmetic.rounding_fee)
    if rebate_rule == RebateRule.MAXIMAL:
        units = min(floor_units(a_pre, h), floor_units(fee_before_rebate, h))
        rebate = exact_mul(Decimal(units), h)
    elif rebate_rule == RebateRule.NONE:
        rebate = Decimal(0)
    else:
        raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "rebate_rule")
    net_fee = exact_sub(fee_before_rebate, rebate)
    if net_fee < 0 or rebate > a_pre:  # pragma: no cover - guaranteed by min() above
        raise F03AnalyzerError("ARITHMETIC_INVARIANT_VIOLATED", "rebate cap")
    return HypothesisRowV1(
        arithmetic=arithmetic, rebate_rule=rebate_rule, accumulator_before_hypothesis=accumulator_before,
        before_rebate_hypothesis=a_pre, rebate_hypothesis=rebate, net_fee_hypothesis=net_fee,
        accumulator_after_hypothesis=exact_sub(a_pre, rebate),
        balance_change_hypothesis=exact_add(arithmetic.aligned_change, rebate),
    )


@dataclass(frozen=True, slots=True)
class FillModelInputV1:
    """One fill as consumed by the model: exact quantity/price, role
    coefficient k and applicable multiplier M (with provenance labels)."""

    quantity: Decimal
    price: Decimal
    k: Decimal
    multiplier: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class CandidateHypothesisV1:
    """A frozen, explicit candidate record: initializer, per-fill rebate rule
    and terminal adjustment rule.  Inclusion never makes it authoritative."""

    hypothesis_id: str
    initializer: str
    rebate_rule: str
    terminal_rule: str
    assumptions: Tuple[str, ...]
    initial_accumulator: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.initializer not in tuple(Initializer):
            raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "initializer")
        if self.rebate_rule not in tuple(RebateRule):
            raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "rebate_rule")
        if self.terminal_rule not in tuple(TerminalRule):
            raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "terminal_rule")
        _require_decimal(self.initial_accumulator, name="initial_accumulator", nonnegative=True)
        if self.initializer == Initializer.ZERO and self.initial_accumulator != 0:
            raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "zero initializer with nonzero start")
        if type(self.assumptions) is not tuple or not self.assumptions:
            raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "assumptions must be explicit")


@dataclass(frozen=True, slots=True)
class HypothesisPredictionV1:
    hypothesis: CandidateHypothesisV1
    rows: Tuple[HypothesisRowV1, ...]
    per_fill_net_total: Decimal
    terminal_credit: Decimal
    predicted_total: Decimal
    positive_rebate_total: Decimal
    modeled_residual: Decimal
    evidence_class: str = EVIDENCE_CLASS_MODEL_HYPOTHESIS


def terminal_credit(modeled_residual: Decimal, *, h: Decimal, terminal_rule: str) -> Decimal:
    """NO_CREDIT -> 0; FLOOR_TO_H_CREDIT -> floor_h(residual).  A non-grid
    residual refund is never invented against the balance quantum."""
    _require_decimal(modeled_residual, name="modeled_residual", nonnegative=True)
    if terminal_rule == TerminalRule.NO_CREDIT:
        return Decimal(0)
    if terminal_rule == TerminalRule.FLOOR_TO_H_CREDIT:
        return floor_to_step(modeled_residual, h)
    raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "terminal_rule")


def predict_sequence(
    fills: Sequence[FillModelInputV1], *, h: Decimal, hypothesis: CandidateHypothesisV1,
) -> HypothesisPredictionV1:
    """Ordered same-order (carry crosses maker/taker roles) prediction."""
    _require_decimal(h, name="h", positive=True)
    if type(fills) not in (list, tuple):
        raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "fills")
    accumulator = hypothesis.initial_accumulator
    rows: list[HypothesisRowV1] = []
    for fill in fills:
        if type(fill) is not FillModelInputV1:
            raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "fill type")
        arithmetic = published_fill_arithmetic(
            quantity=fill.quantity, price=fill.price, k=fill.k, multiplier=fill.multiplier, h=h,
        )
        row = hypothesis_row(arithmetic, accumulator_before=accumulator, rebate_rule=hypothesis.rebate_rule)
        rows.append(row)
        accumulator = row.accumulator_after_hypothesis
    net_total = exact_add(*(row.net_fee_hypothesis for row in rows))
    credit = terminal_credit(accumulator, h=h, terminal_rule=hypothesis.terminal_rule)
    return HypothesisPredictionV1(
        hypothesis=hypothesis, rows=tuple(rows), per_fill_net_total=net_total, terminal_credit=credit,
        predicted_total=exact_sub(net_total, credit),
        positive_rebate_total=exact_add(*(row.rebate_hypothesis for row in rows)),
        modeled_residual=accumulator,
    )


def default_candidate_family(*, carry_start: Decimal | None = None) -> Tuple[CandidateHypothesisV1, ...]:
    """F03-MA-006 default tested pairs.  Each pair differs in exactly one
    rule; the other rules are stated jointly."""
    family = [
        CandidateHypothesisV1(
            "MAXIMAL_ZERO_NO_TERMINAL", Initializer.ZERO, RebateRule.MAXIMAL, TerminalRule.NO_CREDIT,
            ("ZERO_INIT", "NO_TERMINAL_CREDIT", "NO_OTHER_ADJUSTMENTS"),
        ),
        CandidateHypothesisV1(
            "NO_REBATE_ZERO_NO_TERMINAL", Initializer.ZERO, RebateRule.NONE, TerminalRule.NO_CREDIT,
            ("ZERO_INIT", "NO_TERMINAL_CREDIT", "NO_OTHER_ADJUSTMENTS"),
        ),
        CandidateHypothesisV1(
            "MAXIMAL_ZERO_FLOOR_TERMINAL", Initializer.ZERO, RebateRule.MAXIMAL, TerminalRule.FLOOR_TO_H_CREDIT,
            ("ZERO_INIT", "QUANTUM_ROUNDED_RESIDUAL_CREDIT", "NO_OTHER_ADJUSTMENTS"),
        ),
    ]
    if carry_start is not None:
        family.append(CandidateHypothesisV1(
            "MAXIMAL_CARRY_NO_TERMINAL", Initializer.PRIOR_MODELED_RESIDUAL, RebateRule.MAXIMAL,
            TerminalRule.NO_CREDIT, ("PRIOR_MODELED_RESIDUAL_CARRY", "NO_TERMINAL_CREDIT", "NO_OTHER_ADJUSTMENTS"),
            initial_accumulator=carry_start,
        ))
    return tuple(family)


# ---------------------------------------------------------------------------
# Chronology (section 7): ties without an authoritative within-tie sequence
# require enumerating every ordering; only invariant aggregates are eligible.
# Arbitrary ID sorting never fabricates chronology.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TimedFillV1:
    fill: FillModelInputV1
    execution_time_key: object  # totally ordered authoritative time key
    within_tie_sequence: int | None = None


def admissible_orderings(fills: Sequence[TimedFillV1]) -> Tuple[Tuple[FillModelInputV1, ...], ...]:
    groups: dict[object, list[TimedFillV1]] = {}
    for item in fills:
        if type(item) is not TimedFillV1:
            raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "timed fill")
        groups.setdefault(item.execution_time_key, []).append(item)
    ordered_keys = sorted(groups)
    per_group: list[list[Tuple[FillModelInputV1, ...]]] = []
    total = 1
    for key in ordered_keys:
        members = groups[key]
        sequences = [m.within_tie_sequence for m in members]
        if len(members) > 1 and all(type(s) is int for s in sequences) and len(set(sequences)) == len(sequences):
            per_group.append([tuple(m.fill for m in sorted(members, key=lambda m: m.within_tie_sequence))])
            continue
        if len(members) > 1:
            count = 1
            for n in range(2, len(members) + 1):
                count *= n
            total *= count
            if total > MAX_ORDERINGS_ENUMERATED:
                raise F03AnalyzerError("CHRONOLOGY_ENUMERATION_BOUND_EXCEEDED")
            per_group.append([tuple(m.fill for m in perm) for perm in itertools.permutations(members)])
        else:
            per_group.append([(members[0].fill,)])
    orderings = []
    for combo in itertools.product(*per_group):
        orderings.append(tuple(f for part in combo for f in part))
    return tuple(orderings)


CHRONOLOGY_UNIQUE = "UNIQUE_AUTHORITATIVE_ORDER"
CHRONOLOGY_ENUMERATED = "TIED_ORDERINGS_ENUMERATED"
CHRONOLOGY_BOUND_EXCEEDED = "CHRONOLOGY_ENUMERATION_BOUND_EXCEEDED"
CHRONOLOGY_NO_FILLS = "NO_FILLS"


@dataclass(frozen=True, slots=True)
class ChronologyAssessmentV1:
    """The ONE coherent chronology eligibility result (F03 Correction01 F02).
    ``orderings`` is empty when the bounded enumeration cannot establish the
    admissible set; every consumer then reports non-identification instead of
    raising, fabricating an order or sorting by arbitrary identifiers."""

    state: str
    orderings: Tuple[Tuple[FillModelInputV1, ...], ...]

    @property
    def usable(self) -> bool:
        return self.state in (CHRONOLOGY_UNIQUE, CHRONOLOGY_ENUMERATED)

    @property
    def unique(self) -> bool:
        return self.state == CHRONOLOGY_UNIQUE


def assess_chronology(fills: Sequence[TimedFillV1]) -> ChronologyAssessmentV1:
    """Bounded (<= MAX_ORDERINGS_ENUMERATED) admissible-ordering assessment.
    Above the bound the state is CHRONOLOGY_ENUMERATION_BOUND_EXCEEDED with no
    orderings; malformed input still raises (fail closed, never evidence)."""
    if not fills:
        return ChronologyAssessmentV1(CHRONOLOGY_NO_FILLS, ((),))
    try:
        orderings = admissible_orderings(fills)
    except F03AnalyzerError as exc:
        if exc.code != "CHRONOLOGY_ENUMERATION_BOUND_EXCEEDED":
            raise
        return ChronologyAssessmentV1(CHRONOLOGY_BOUND_EXCEEDED, ())
    return ChronologyAssessmentV1(CHRONOLOGY_UNIQUE if len(orderings) == 1 else CHRONOLOGY_ENUMERATED, orderings)


@dataclass(frozen=True, slots=True)
class InvariantOutcomeV1:
    """Invariant prediction outcome for one hypothesis: values are ``None``
    whenever chronology is unusable or the outcome is order-dependent."""

    predicted_total: Decimal | None
    positive_rebate_total: Decimal | None
    modeled_residual: Decimal | None
    reason: str


def invariant_outcome(
    chronology: ChronologyAssessmentV1, *, h: Decimal, hypothesis: CandidateHypothesisV1,
) -> InvariantOutcomeV1:
    if type(chronology) is not ChronologyAssessmentV1:
        raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "chronology")
    if not chronology.usable:
        return InvariantOutcomeV1(None, None, None, chronology.state)
    outcomes = {(p.predicted_total, p.positive_rebate_total, p.modeled_residual)
                for p in (predict_sequence(o, h=h, hypothesis=hypothesis) for o in chronology.orderings)}
    if len(outcomes) != 1:
        totals = {o[0] for o in outcomes}
        if len(totals) == 1:
            return InvariantOutcomeV1(next(iter(totals)), None, None, "TOTAL_INVARIANT_COMPONENTS_ORDER_DEPENDENT")
        return InvariantOutcomeV1(None, None, None, "ORDER_DEPENDENT_PREDICTION")
    total, positive, residual = next(iter(outcomes))
    return InvariantOutcomeV1(total, positive, residual, "INVARIANT")


def invariant_prediction(
    fills: Sequence[TimedFillV1], *, h: Decimal, hypothesis: CandidateHypothesisV1,
) -> Decimal | None:
    """The predicted TOTAL if invariant across every admissible ordering,
    otherwise ``None`` (INCONCLUSIVE for that hypothesis)."""
    return invariant_outcome(assess_chronology(fills), h=h, hypothesis=hypothesis).predicted_total


# ---------------------------------------------------------------------------
# F03-MA-001..004 -- cash interval measurement and guarded identification.
# ---------------------------------------------------------------------------

ISOLATION_PREDICATES: Tuple[str, ...] = (
    "BOTH_BOUNDS_STABLE",
    "COMPLETE_ACTIVE_DOMAIN_ORDERS_FILLS_POSITIONS",
    "NO_UNRELATED_WORKING_ORDER_IN_DOMAIN",
    "NO_TEST_WORKING_ORDER_AT_EITHER_BOUND",
    "NO_PREEXISTING_UNSETTLED_POSITION_RISK",
    "NO_CROSS_DOMAIN_OR_FEE_EPOCH_CHANGE",
    "NO_TEST_ID_COLLISION",
    "NO_UNEXPLAINED_BALANCE_EVENT",
    "NO_SETTLEMENT_TRANSFER_ADJUSTMENT_EFFECT",
    "MARKET_CLOSE_AFTER_ACTIVE_END_PLUS_120S",
    "FEE_FIELDS_COMPLETE",
    "NO_EXTERNAL_THIRD_PARTY_CHARGE",
)


@dataclass(frozen=True, slots=True)
class CashIntervalInputV1:
    """Sanitized interval inputs: the incremental cash delta (B_pre - B_post),
    never an absolute balance.  ``api_fee_costs`` keep one entry per complete
    authoritative fill; ``None`` marks a missing source fee field."""

    interval_id: str
    pre_checkpoint_state: str
    post_checkpoint_state: str
    cash_delta_pre_minus_post: Decimal | None
    principals: Tuple[Decimal, ...]
    api_fee_costs: Tuple[Decimal | None, ...]
    isolation_predicates: Mapping[str, str]
    terminal_credit_excluded: bool
    cash_evidence_id: str


@dataclass(frozen=True, slots=True)
class CashIntervalResultV1:
    interval_id: str
    fill_count: int
    principal_total: Decimal | None
    cash_fee_total: Decimal | None
    api_fee_cost_total: Decimal | None
    aggregate_fee_cost_consistency_state: str
    per_fill_fee_identification_state: str
    identified_net_fee: Decimal | None
    eligibility: bool
    rejection_codes: Tuple[str, ...]
    economic_record: str  # COMPLETE | INCOMPLETE
    cash_evidence_id: str
    # Aggregate hypothesis comparison models the terminal rule explicitly as a
    # joint assumption of every candidate (F03-ISO-002), so it is eligible
    # when every OTHER isolation/measurement predicate passes.  Cash/API
    # consistency and single-fill identification additionally require the
    # independent terminal-credit exclusion (``eligibility``).
    hypothesis_comparison_eligible: bool = False


def interval_cash_delta_from_private(b_pre: Decimal, b_post: Decimal) -> Decimal:
    """Private-only conversion of two exact absolute balances into the
    shareable incremental delta.  The absolute values never leave the caller."""
    return exact_sub(_require_decimal(b_pre, name="b_pre"), _require_decimal(b_post, name="b_post"))


def analyze_cash_interval(data: CashIntervalInputV1) -> CashIntervalResultV1:
    """F_cash = (B_pre - B_post) - P; F_api = sum(api fee_cost).  Equality is
    only aggregate consistency.  Exactly one complete fill in a fully
    isolated stable interval with the terminal credit excluded identifies that
    interval's single-fill net cash fee; multi-fill cash is NOT_IDENTIFIABLE."""
    if type(data) is not CashIntervalInputV1:
        raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "interval")
    if len(data.principals) != len(data.api_fee_costs):
        raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "fill count mismatch")
    rejection: list[str] = []
    fill_count = len(data.principals)
    if data.pre_checkpoint_state != CheckpointState.STABLE or data.post_checkpoint_state != CheckpointState.STABLE:
        rejection.append("CHECKPOINT_NOT_STABLE")
    for name in ISOLATION_PREDICATES:
        state = data.isolation_predicates.get(name, PredicateState.UNRESOLVED)
        if state not in tuple(PredicateState):
            raise F03AnalyzerError("SCHEMA_ENUM_INVALID", "isolation predicate state")
        if state != PredicateState.PASS:
            rejection.append("ISOLATION_" + name + "_" + state)
    for name in data.isolation_predicates:
        if name not in ISOLATION_PREDICATES:
            raise F03AnalyzerError("SCHEMA_ENUM_INVALID", "unknown isolation predicate")
    if not data.terminal_credit_excluded:
        rejection.append("TERMINAL_CREDIT_NOT_EXCLUDED")
    economic_record = "COMPLETE"
    if any(item is None for item in data.api_fee_costs):
        economic_record = "INCOMPLETE"
        rejection.append("FEE_FIELD_MISSING")
    if data.cash_delta_pre_minus_post is None:
        rejection.append("CASH_OBSERVATION_MISSING")
    principal_total = exact_add(*(_require_decimal(p, name="principal", positive=True) for p in data.principals)) if fill_count else Decimal(0)
    cash_fee_total = None
    if data.cash_delta_pre_minus_post is not None:
        cash_fee_total = exact_sub(_require_decimal(data.cash_delta_pre_minus_post, name="cash delta"), principal_total)
    api_total = None
    if economic_record == "COMPLETE":
        api_total = exact_add(*(_require_decimal(v, name="api_fee_cost") for v in data.api_fee_costs)) if fill_count else Decimal(0)
    eligible = not rejection and fill_count > 0
    hypothesis_eligible = (
        fill_count > 0 and cash_fee_total is not None and economic_record == "COMPLETE"
        and all(code == "TERMINAL_CREDIT_NOT_EXCLUDED" for code in rejection)
    )
    if fill_count == 0:
        rejection.append("NO_FILLS")
    if not eligible or cash_fee_total is None or api_total is None:
        aggregate = AggregateConsistencyState.INCONCLUSIVE if fill_count else AggregateConsistencyState.UNTESTED
    elif cash_fee_total == api_total:
        aggregate = AggregateConsistencyState.AGGREGATE_MATCH
    else:
        aggregate = AggregateConsistencyState.AGGREGATE_CONFLICT
    identified: Decimal | None = None
    if fill_count == 0:
        per_fill = PerFillIdentificationState.NOT_ATTEMPTED
    elif not eligible or cash_fee_total is None:
        per_fill = PerFillIdentificationState.NOT_IDENTIFIABLE
    elif fill_count != 1:
        per_fill = PerFillIdentificationState.NOT_IDENTIFIABLE
    elif cash_fee_total < 0:
        # A negative residual is never forced into a negative fee/rebate.
        per_fill = PerFillIdentificationState.CONFLICT
    else:
        per_fill = PerFillIdentificationState.SINGLE_FILL_IDENTIFIED
        identified = cash_fee_total
    return CashIntervalResultV1(
        interval_id=data.interval_id, fill_count=fill_count, principal_total=principal_total,
        cash_fee_total=cash_fee_total, api_fee_cost_total=api_total,
        aggregate_fee_cost_consistency_state=aggregate.value, per_fill_fee_identification_state=per_fill.value,
        identified_net_fee=identified, eligibility=eligible, rejection_codes=tuple(rejection),
        economic_record=economic_record, cash_evidence_id=data.cash_evidence_id,
        hypothesis_comparison_eligible=hypothesis_eligible,
    )


def observed_rebates_for_interval(result: CashIntervalResultV1, *, fill_count: int) -> Tuple[None, ...]:
    """Observed per-fill rebates are NEVER emitted from aggregate API equality:
    every entry is ``None`` unless a fill net fee was independently identified
    (which this aggregate path does not do for multi-fill intervals)."""
    del result
    return tuple(None for _ in range(fill_count))


# ---------------------------------------------------------------------------
# F03-MA-005..006 -- scoped aggregate hypothesis discrimination.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiscriminationResultV1:
    state: str
    matched_hypothesis_id: str | None
    matching_ids: Tuple[str, ...]
    equivalent_untested_alternatives: Tuple[str, ...]
    ineligibility_reason: str | None = None


def discriminate(
    predictions: Mapping[str, Decimal | None], *, observed: Decimal | None, h: Decimal, eligible: bool,
    required_ids: Sequence[str] | None = None,
) -> DiscriminationResultV1:
    """UNIQUE_MATCH only when the COMPLETE explicitly tested family (>= 2
    members, every member's prediction available) is compared, exactly one
    prediction equals the observed total AND every rival differs from it by
    >= h.  An absent / uncomputable / order-dependent member (``None``) or a
    singleton family makes the discriminator INELIGIBLE -- a rival is never
    dropped to manufacture a unique match or conflict."""
    _require_decimal(h, name="h", positive=True)
    family = tuple(predictions) if required_ids is None else tuple(required_ids)
    if not eligible or observed is None:
        return DiscriminationResultV1(UniqueDiscriminatorState.INELIGIBLE.value, None, (), (), "MEASUREMENT_INELIGIBLE")
    if len(family) < 2 or len(set(family)) != len(family):
        return DiscriminationResultV1(UniqueDiscriminatorState.INELIGIBLE.value, None, (), (), "FAMILY_NOT_A_RIVAL_COMPARISON")
    if set(predictions) != set(family):
        return DiscriminationResultV1(UniqueDiscriminatorState.INELIGIBLE.value, None, (), family, "FAMILY_MEMBER_ABSENT")
    for key in family:
        value = predictions[key]
        if value is None:
            return DiscriminationResultV1(UniqueDiscriminatorState.INELIGIBLE.value, None, (), family,
                                          "FAMILY_MEMBER_PREDICTION_UNAVAILABLE")
        if type(key) is not str or type(value) is not Decimal or not value.is_finite():
            raise F03AnalyzerError("ECONOMIC_INPUT_INVALID", "prediction")
    matches = tuple(sorted(key for key, value in predictions.items() if value == observed))
    if not matches:
        return DiscriminationResultV1(UniqueDiscriminatorState.NO_MATCH.value, None, (), ())
    if len(matches) > 1:
        return DiscriminationResultV1(UniqueDiscriminatorState.EQUAL_PREDICTIONS.value, None, matches, matches)
    matched = matches[0]
    near = tuple(sorted(
        key for key, value in predictions.items()
        if key != matched and abs(exact_sub(value, observed)) < h
    ))
    if near:
        return DiscriminationResultV1(UniqueDiscriminatorState.EQUAL_PREDICTIONS.value, None, matches, (matched,) + near)
    return DiscriminationResultV1(UniqueDiscriminatorState.UNIQUE_MATCH.value, matched, matches, ())


# ---------------------------------------------------------------------------
# Section 12 -- QF03 decision rules.  Every result carries scope, explicit
# joint assumptions, observational equivalents, proves / does_not_prove and
# counts the same cash evidence once across questions.
# ---------------------------------------------------------------------------

_UNIVERSAL_NONCLAIMS: Tuple[str, ...] = (
    "UNIVERSAL_VENUE_FEE_POLICY",
    "PRODUCTION_EQUIVALENCE",
    "PROFITABILITY_OR_ARBITRAGE",
    "F03_CLOSURE",
    "P01_P09_CLOSURE",
)


@dataclass(frozen=True, slots=True)
class QuestionScopeV1:
    account_class: str
    quantum: str
    market_ticker: str
    event_ticker: str
    series_ticker: str
    fee_epoch: str
    source_identities: Tuple[str, ...]

    def as_mapping(self) -> dict:
        return {
            "account_class": self.account_class, "quantum": self.quantum,
            "market_ticker": self.market_ticker, "event_ticker": self.event_ticker,
            "series_ticker": self.series_ticker, "fee_epoch": self.fee_epoch,
            "source_identities": list(self.source_identities),
        }


def _question_result(
    question_id: str, status: str, *, scope: QuestionScopeV1, scope_mode: str, conclusion: str,
    cash_evidence_ids: Sequence[str] = (), independence: str = CashEvidenceIndependence.NONE.value,
    independent_support: bool = False, joint_assumptions: Sequence[str] = (),
    equivalents: Sequence[str] = (), proves: Sequence[str] = (), does_not_prove: Sequence[str] = (),
    subobservations: Sequence[Mapping[str, object]] = (), evidence_refs: Sequence[str] = (),
) -> dict:
    if question_id not in QUESTION_IDS or status not in tuple(QuestionStatus) or scope_mode not in tuple(ScopeMode):
        raise F03AnalyzerError("SCHEMA_ENUM_INVALID", "question result")
    # Shared evidence carries exact built-in strings only (never enum objects).
    status = QuestionStatus(status).value
    scope_mode = ScopeMode(scope_mode).value
    independence = CashEvidenceIndependence(independence).value
    unique_cash = sorted(set(cash_evidence_ids))
    result = {
        "schema": "QuestionResultV1",
        "question_id": question_id,
        "status": status,
        "scoped_conclusion": conclusion,
        "scope_mode": scope_mode,
        **scope.as_mapping(),
        "evidence_refs": list(evidence_refs),
        "calculation_refs": [],
        "cash_evidence_ids": unique_cash,
        "independent_cash_evidence_count": len(unique_cash) if independence == CashEvidenceIndependence.INDEPENDENT_SINGLE_FILL_INTERVAL else 0,
        "cash_evidence_independence": independence,
        "independent_support_for_fee_hypothesis": bool(independent_support),
        "joint_assumptions": list(joint_assumptions),
        "equivalent_untested_alternatives": list(equivalents),
        "proves": list(proves),
        "does_not_prove": sorted(set(does_not_prove) | set(_UNIVERSAL_NONCLAIMS)),
        "subobservations": [dict(item) for item in subobservations],
    }
    validate_question_result_v1(result)
    return result


@dataclass(frozen=True, slots=True)
class Q01InputV1:
    integrity_eligible: bool
    interval: CashIntervalResultV1 | None
    discrimination: DiscriminationResultV1 | None
    maximal_hypothesis_ids: Tuple[str, ...] = ()
    # ``None``: the matched hypothesis' positive-rebate component is not
    # invariant across the admissible orderings (never treated as > 0).
    matched_positive_rebate_total: Decimal | None = Decimal("0")
    joint_assumptions: Tuple[str, ...] = ()
    cap_bound_prediction: Decimal | None = None


def decide_q01(data: Q01InputV1, *, scope: QuestionScopeV1) -> dict:
    """F03-Q01-001.  Cap-only or rebate-0 never gives overall OBSERVED_MATCH;
    positive maximality needs a uniquely discriminating aggregate prediction
    (or independently identified positive rebate with supported start)."""
    subs: list[dict] = []
    interval = data.interval
    cash_ids = [interval.cash_evidence_id] if interval is not None and interval.cash_fee_total is not None else []
    base = dict(scope=scope, cash_evidence_ids=cash_ids,
                independence=CashEvidenceIndependence.SHARED_AGGREGATE_IDENTITY.value if cash_ids else CashEvidenceIndependence.NONE.value,
                does_not_prove=("PER_FILL_REBATE_FROM_API_FEE_COST", "UNIVERSAL_MAXIMALITY"))
    if interval is not None and interval.per_fill_fee_identification_state == PerFillIdentificationState.SINGLE_FILL_IDENTIFIED and data.cap_bound_prediction is not None:
        subs.append({"subobservation": "CAP_BOUND_MATCH" if interval.identified_net_fee == data.cap_bound_prediction else "CAP_BOUND_CONFLICT"})
    if not data.integrity_eligible:
        return _question_result("QF03-01", QuestionStatus.INCONCLUSIVE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                conclusion="INTEGRITY_OR_MEASUREMENT_INELIGIBLE", subobservations=subs, **base)
    if interval is None or interval.fill_count == 0 or interval.cash_fee_total is None:
        return _question_result("QF03-01", QuestionStatus.NOT_OBSERVABLE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                conclusion="REQUIRED_CASH_INTERVAL_ABSENT", subobservations=subs, **base)
    if interval.aggregate_fee_cost_consistency_state == AggregateConsistencyState.AGGREGATE_CONFLICT:
        subs.append({"subobservation": HaltCode.MEASUREMENT_HYPOTHESIS_DISCREPANCY.value})
        return _question_result("QF03-01", QuestionStatus.INCONCLUSIVE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                conclusion="CASH_API_CONFLICT_BLOCKS_ATTRIBUTION", subobservations=subs, **base)
    disc = data.discrimination
    if disc is None or disc.state == UniqueDiscriminatorState.INELIGIBLE:
        return _question_result("QF03-01", QuestionStatus.INCONCLUSIVE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                conclusion="NO_ELIGIBLE_POSITIVE_DISCRIMINATOR", subobservations=subs, **base)
    if disc.state == UniqueDiscriminatorState.EQUAL_PREDICTIONS:
        return _question_result("QF03-01", QuestionStatus.INCONCLUSIVE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                conclusion="EQUAL_COMPETING_AGGREGATE_PREDICTIONS", equivalents=disc.equivalent_untested_alternatives,
                                subobservations=subs, **base)
    if disc.state == UniqueDiscriminatorState.NO_MATCH:
        subs.append({"subobservation": HaltCode.MEASUREMENT_HYPOTHESIS_DISCREPANCY.value})
        return _question_result("QF03-01", QuestionStatus.INCONCLUSIVE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                conclusion="NO_TESTED_HYPOTHESIS_MATCHES", subobservations=subs, **base)
    if not data.joint_assumptions:
        raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "joint assumptions must be explicit")
    if disc.matched_hypothesis_id in data.maximal_hypothesis_ids:
        if data.matched_positive_rebate_total is None:
            return _question_result("QF03-01", QuestionStatus.INCONCLUSIVE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                    conclusion="POSITIVE_REBATE_COMPONENT_ORDER_DEPENDENT",
                                    joint_assumptions=data.joint_assumptions, subobservations=subs, **base)
        if data.matched_positive_rebate_total <= 0:
            return _question_result("QF03-01", QuestionStatus.INCONCLUSIVE, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                    conclusion="MATCH_WITHOUT_POSITIVE_REBATE_IS_NOT_MAXIMALITY_EVIDENCE",
                                    joint_assumptions=data.joint_assumptions, subobservations=subs, **base)
        subs.append({"subobservation": "AGGREGATE_POSITIVE_REBATE_DISCRIMINATOR_MATCH"})
        return _question_result("QF03-01", QuestionStatus.OBSERVED_MATCH, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                                conclusion="TESTED_JOINT_MAXIMAL_HYPOTHESIS_UNIQUELY_MATCHES_INTERVAL_TOTAL",
                                joint_assumptions=data.joint_assumptions,
                                equivalents=("UNTESTED_REBATE_FAMILIES_WITH_EQUAL_INTERVAL_TOTAL",),
                                proves=("SCOPED_INTERVAL_TOTAL_MATCH",), subobservations=subs, **base)
    return _question_result("QF03-01", QuestionStatus.OBSERVED_CONFLICT, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS,
                            conclusion="TESTED_JOINT_MAXIMAL_HYPOTHESIS_CONFLICTS_WITH_UNIQUE_RIVAL_MATCH",
                            joint_assumptions=data.joint_assumptions,
                            equivalents=("UNTESTED_REBATE_FAMILIES_WITH_EQUAL_INTERVAL_TOTAL",),
                            proves=("SCOPED_JOINT_HYPOTHESIS_CONFLICT",),
                            subobservations=subs, **{**base, "does_not_prove": base["does_not_prove"] + ("UNIVERSAL_POLICY_FALSIFICATION",)})


@dataclass(frozen=True, slots=True)
class Q02InputV1:
    integrity_eligible: bool
    order2_sent: bool
    i2_eligible: bool
    cash: Decimal | None
    zero_predicted: Decimal | None
    carry_predicted: Decimal | None
    h: Decimal
    joint_assumptions: Tuple[str, ...] = ()
    cash_evidence_id: str = ""


def decide_q02(data: Q02InputV1, *, scope: QuestionScopeV1) -> dict:
    """F03-Q02-001 -- scoped zero-start versus modeled carry-start pair."""
    subs = [{"subobservation": "AMEND_REPLACE_SUBCASE", "status": QuestionStatus.NOT_APPLICABLE.value}]
    cash_ids = [data.cash_evidence_id] if data.cash_evidence_id and data.cash is not None else []
    base = dict(scope=scope, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS, cash_evidence_ids=cash_ids,
                independence=CashEvidenceIndependence.SHARED_AGGREGATE_IDENTITY.value if cash_ids else CashEvidenceIndependence.NONE.value,
                subobservations=subs, does_not_prove=("UNIVERSAL_NEW_ORDER_INITIALIZER", "OBSERVED_ACCUMULATOR"))
    if not data.integrity_eligible:
        return _question_result("QF03-02", QuestionStatus.INCONCLUSIVE, conclusion="INTEGRITY_OR_MEASUREMENT_INELIGIBLE", **base)
    if not data.order2_sent or not data.i2_eligible:
        return _question_result("QF03-02", QuestionStatus.INCONCLUSIVE, conclusion="I2_ABSENT_OR_INELIGIBLE", **base)
    if data.cash is None:
        return _question_result("QF03-02", QuestionStatus.NOT_OBSERVABLE, conclusion="I2_CASH_OBSERVABLE_ABSENT", **base)
    if data.zero_predicted is None or data.carry_predicted is None:
        return _question_result("QF03-02", QuestionStatus.INCONCLUSIVE, conclusion="PREDICTIONS_NOT_ORDERING_INVARIANT", **base)
    if abs(exact_sub(data.zero_predicted, data.carry_predicted)) < data.h:
        return _question_result("QF03-02", QuestionStatus.INCONCLUSIVE, conclusion="ZERO_AND_CARRY_PREDICTIONS_NOT_SEPARATED_BY_H",
                                equivalents=("ZERO_START", "CARRY_START"), **base)
    if not data.joint_assumptions:
        raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "joint assumptions must be explicit")
    if data.cash == data.zero_predicted:
        return _question_result("QF03-02", QuestionStatus.OBSERVED_MATCH, conclusion="TESTED_ZERO_VS_CARRY_PAIR",
                                joint_assumptions=data.joint_assumptions, proves=("SCOPED_ZERO_START_MATCH_FOR_TESTED_PAIR",),
                                equivalents=("UNTESTED_INITIALIZERS_WITH_EQUAL_I2_TOTAL",), **base)
    if data.cash == data.carry_predicted:
        return _question_result("QF03-02", QuestionStatus.OBSERVED_CONFLICT, conclusion="JOINT_ZERO_START_HYPOTHESIS",
                                joint_assumptions=data.joint_assumptions, proves=("SCOPED_JOINT_ZERO_START_CONFLICT",),
                                equivalents=("UNTESTED_INITIALIZERS_WITH_EQUAL_I2_TOTAL",),
                                **{**base, "does_not_prove": base["does_not_prove"] + ("UNIVERSAL_POLICY_FALSIFICATION",)})
    return _question_result("QF03-02", QuestionStatus.INCONCLUSIVE, conclusion="NO_TESTED_INITIALIZER_MATCHES",
                            subobservations=subs + [{"subobservation": HaltCode.MEASUREMENT_HYPOTHESIS_DISCREPANCY.value}],
                            **{k: v for k, v in base.items() if k != "subobservations"})


@dataclass(frozen=True, slots=True)
class Q03InputV1:
    integrity_eligible: bool
    modeled_residual: Decimal | None
    h: Decimal
    explicit_terminal_accumulator_event: bool
    terminal_cash_observable: bool
    unique_total_discriminator: DiscriminationResultV1 | None = None
    joint_assumptions: Tuple[str, ...] = ()
    terminal_classes: Tuple[str, ...] = ()
    cash_evidence_id: str = ""


def decide_q03(data: Q03InputV1, *, scope: QuestionScopeV1) -> dict:
    """F03-Q03-001 -- terminal residual disposition is never assigned causal
    attribution from an equal total; residual < h is nondiscriminating."""
    credits: list[str] = []
    if data.modeled_residual is not None:
        credits = [canonical_decimal_text(terminal_credit(data.modeled_residual, h=data.h, terminal_rule=rule))
                   for rule in (TerminalRule.NO_CREDIT, TerminalRule.FLOOR_TO_H_CREDIT)]
    subs = [{"subobservation": "PREDICTED_TERMINAL_CREDITS", "values": credits},
            {"subobservation": "TERMINAL_CLASSES", "values": list(data.terminal_classes)}]
    cash_ids = [data.cash_evidence_id] if data.cash_evidence_id else []
    base = dict(scope=scope, scope_mode=ScopeMode.AGGREGATE_HYPOTHESIS, subobservations=subs, cash_evidence_ids=cash_ids,
                independence=CashEvidenceIndependence.SHARED_AGGREGATE_IDENTITY.value if cash_ids else CashEvidenceIndependence.NONE.value,
                does_not_prove=("DISCARD_VS_HIDDEN_PRESERVATION", "TERMINAL_CAUSAL_ATTRIBUTION", "TERMINAL_CREDIT_TIMING"))
    if not data.integrity_eligible:
        return _question_result("QF03-03", QuestionStatus.INCONCLUSIVE, conclusion="INTEGRITY_OR_MEASUREMENT_INELIGIBLE", **base)
    if not data.terminal_cash_observable or data.modeled_residual is None:
        return _question_result("QF03-03", QuestionStatus.NOT_OBSERVABLE, conclusion="TERMINAL_DISPOSITION_NOT_OBSERVABLE", **base)
    if data.modeled_residual < data.h:
        return _question_result("QF03-03", QuestionStatus.INCONCLUSIVE, conclusion="RESIDUAL_BELOW_QUANTUM_NONDISCRIMINATING",
                                equivalents=("DISCARD", "HIDDEN_PRESERVATION", "ROUNDED_ZERO_REFUND"), **base)
    disc = data.unique_total_discriminator
    if data.explicit_terminal_accumulator_event is False and (disc is None or disc.state != UniqueDiscriminatorState.UNIQUE_MATCH):
        return _question_result("QF03-03", QuestionStatus.INCONCLUSIVE, conclusion="NO_TERMINAL_EVENT_OR_UNIQUE_TOTAL_DISCRIMINATOR", **base)
    if not data.joint_assumptions:
        raise F03AnalyzerError("HYPOTHESIS_RULE_INVALID", "joint assumptions must be explicit")
    return _question_result("QF03-03", QuestionStatus.OBSERVED_MATCH, conclusion="CONDITIONAL_INTERVAL_TOTAL_MATCH_UNDER_COMPLETE_JOINT_MODEL",
                            joint_assumptions=data.joint_assumptions, proves=("SCOPED_INTERVAL_TOTAL_MATCH",),
                            equivalents=("ALTERNATE_PER_FILL_FEES_OR_ADJUSTMENTS_WITH_EQUAL_TOTAL",), **base)


@dataclass(frozen=True, slots=True)
class Q04InputV1:
    integrity_eligible: bool
    interval: CashIntervalResultV1 | None
    reused_cash_evidence_ids: Tuple[str, ...] = ()


def decide_q04(data: Q04InputV1, *, scope: QuestionScopeV1) -> dict:
    """F03-Q04-001 -- the narrow cash/API identity; when its cash identity is
    reused by Q01/Q02 it gives NO independent support to a fee hypothesis."""
    interval = data.interval
    cash_ids = [interval.cash_evidence_id] if interval is not None and interval.cash_fee_total is not None else []
    distinct = sorted(set(cash_ids) | set(data.reused_cash_evidence_ids))
    subs = [
        {"subobservation": "PHYSICAL_MICROSECOND_SIMULTANEITY", "status": QuestionStatus.NOT_OBSERVABLE.value},
        {"subobservation": "OUTSIDE_ACCOUNT_SETTLEMENT_TIMING", "status": QuestionStatus.NOT_OBSERVABLE.value},
        {"subobservation": "DISTINCT_CASH_INTERVAL_COUNT", "value": len(distinct)},
    ]
    base = dict(scope=scope, scope_mode=ScopeMode.AGGREGATE_CONSISTENCY, cash_evidence_ids=cash_ids,
                independence=CashEvidenceIndependence.SHARED_AGGREGATE_IDENTITY.value if cash_ids else CashEvidenceIndependence.NONE.value,
                independent_support=False, subobservations=subs,
                does_not_prove=("PER_FILL_FEE_ASSOCIATION", "CLIENT_WALL_FRESHNESS", "FULL_POSTING_CAUSALITY",
                                "INDEPENDENT_VALIDATION_OF_FEE_HYPOTHESIS"))
    if not data.integrity_eligible:
        return _question_result("QF03-04", QuestionStatus.INCONCLUSIVE, conclusion="INTEGRITY_OR_MEASUREMENT_INELIGIBLE", **base)
    if interval is None or interval.cash_fee_total is None or interval.fill_count == 0:
        return _question_result("QF03-04", QuestionStatus.NOT_OBSERVABLE, conclusion="CASH_OBSERVABLE_ABSENT", **base)
    state = interval.aggregate_fee_cost_consistency_state
    if state == AggregateConsistencyState.AGGREGATE_MATCH:
        return _question_result("QF03-04", QuestionStatus.OBSERVED_MATCH, conclusion="F_CASH_EQUALS_F_API_FOR_ELIGIBLE_INTERVAL",
                                proves=("AGGREGATE_FEE_COST_CONSISTENCY_FOR_INTERVAL",), **base)
    if state == AggregateConsistencyState.AGGREGATE_CONFLICT:
        return _question_result("QF03-04", QuestionStatus.OBSERVED_CONFLICT, conclusion="ACCOUNTING_MEASUREMENT_DISCREPANCY_NOT_REBATE_POLICY",
                                proves=("AGGREGATE_FEE_COST_DISCREPANCY_FOR_INTERVAL",), **base)
    return _question_result("QF03-04", QuestionStatus.INCONCLUSIVE, conclusion="AGGREGATE_CONSISTENCY_NOT_ELIGIBLE", **base)


@dataclass(frozen=True, slots=True)
class Q05InputV1:
    account_class: str
    single_fill_identified_net_fee: Decimal | None
    fill_quantity: Decimal | None
    fill_price: Decimal | None
    multiplier: Decimal | None
    authoritative_table_class_statement: bool = False
    cash_evidence_id: str = ""


def decide_q05(data: Q05InputV1, *, scope: QuestionScopeV1) -> dict:
    """F03-Q05-001 -- a numeric comparison can narrow an exact-DIRECT-cell
    reading but never assigns the PDF table's intended account class."""
    subs: list[dict] = []
    table_cell = (
        data.fill_quantity == Decimal("1") and data.fill_price == Decimal("0.5") and data.multiplier == Decimal("1")
    )
    cash_ids = [data.cash_evidence_id] if data.cash_evidence_id and data.single_fill_identified_net_fee is not None else []
    base = dict(scope=scope, scope_mode=ScopeMode.SOURCE_SCOPE, cash_evidence_ids=cash_ids,
                independence=CashEvidenceIndependence.INDEPENDENT_SINGLE_FILL_INTERVAL.value if cash_ids else CashEvidenceIndependence.NONE.value,
                does_not_prove=("PDF_TABLE_INTENDED_ACCOUNT_CLASS", "ACCOUNT_CLASS_FROM_AMOUNT_ROUNDING"))
    if data.account_class not in (AccountClass.DIRECT, AccountClass.NON_DIRECT):
        return _question_result("QF03-05", QuestionStatus.INCONCLUSIVE, conclusion="ACCOUNT_CLASS_UNRESOLVED", **base)
    if not table_cell or data.single_fill_identified_net_fee is None:
        subs.append({"subobservation": "TABLE_PRICE_FILL", "status": QuestionStatus.NOT_APPLICABLE.value})
        return _question_result("QF03-05", QuestionStatus.INCONCLUSIVE, conclusion="NO_ELIGIBLE_TABLE_CELL_FILL", subobservations=subs, **base)
    predicted = exact_mul(K_TAKER, Decimal("1"), Decimal("1"), Decimal("0.5"), Decimal("0.5"))
    predicted = ceil_to_step(predicted, TRADE_FEE_STEP)
    if data.account_class == AccountClass.NON_DIRECT:
        predicted = exact_add(predicted, published_fill_arithmetic(
            quantity=Decimal("1"), price=Decimal("0.5"), k=K_TAKER, multiplier=Decimal("1"), h=QUANTUM_NON_DIRECT,
        ).rounding_fee)
    conflicts = data.single_fill_identified_net_fee != PDF_TABLE_ONE_CONTRACT_HALF_PRICE_FEE
    subs.append({
        "subobservation": "TABLE_CELL_COMPARISON",
        "identified_net_fee": canonical_decimal_text(data.single_fill_identified_net_fee),
        "class_predicted_net_fee": canonical_decimal_text(predicted),
        "table_value": canonical_decimal_text(PDF_TABLE_ONE_CONTRACT_HALF_PRICE_FEE),
        "table_as_exact_direct_fee_conflicts": bool(conflicts and data.account_class == AccountClass.DIRECT),
        "pdf_intended_account_class": None,
    })
    if not data.authoritative_table_class_statement:
        return _question_result("QF03-05", QuestionStatus.INCONCLUSIVE, conclusion="NO_AUTHORITATIVE_TABLE_SCOPE_STATEMENT",
                                subobservations=subs, **base)
    # An authoritative table-scope statement is a future reviewed input; none
    # exists in the supplied sources, so this branch is never reached by a run.
    return _question_result("QF03-05", QuestionStatus.INCONCLUSIVE, conclusion="TABLE_SCOPE_STATEMENT_REQUIRES_SEPARATE_REVIEW",
                            subobservations=subs, **base)


# ---------------------------------------------------------------------------
# Section 8 -- strict evidence schemas.
# ---------------------------------------------------------------------------


def _reject_constant(name: str) -> object:
    raise F03AnalyzerError("SCHEMA_NONFINITE_REJECTED", name)


def _reject_float(text: str) -> object:
    raise F03AnalyzerError("SCHEMA_ECONOMIC_FLOAT_REJECTED", text)


def _pairs_no_duplicates(pairs: Sequence[Tuple[str, object]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise F03AnalyzerError("SCHEMA_DUPLICATE_KEY", key)
        seen[key] = value
    return seen


def strict_json_loads(data: bytes | str) -> object:
    """UTF-8, duplicate-key rejecting, float/NaN/Infinity rejecting JSON."""
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise F03AnalyzerError("SCHEMA_UTF8_INVALID") from None
    elif isinstance(data, str):
        text = data
    else:
        raise F03AnalyzerError("SCHEMA_INPUT_TYPE")
    return json.loads(text, object_pairs_hook=_pairs_no_duplicates, parse_float=_reject_float,
                      parse_constant=_reject_constant)


def _req(obj: Mapping[str, object], key: str) -> object:
    if key not in obj:
        raise F03AnalyzerError("SCHEMA_MISSING_KEY", key)
    return obj[key]


def _req_type(obj: Mapping[str, object], key: str, kind: type) -> object:
    value = _req(obj, key)
    if type(value) is not kind:
        raise F03AnalyzerError("SCHEMA_TYPE_INVALID", key)
    return value


def _req_enum(obj: Mapping[str, object], key: str, allowed: Iterable[str]) -> str:
    value = _req(obj, key)
    if type(value) is not str or value not in tuple(allowed):
        raise F03AnalyzerError("SCHEMA_ENUM_INVALID", key)
    return value


def _req_decimal_or_null(obj: Mapping[str, object], key: str) -> Decimal | None:
    value = _req(obj, key)
    if value is None:
        return None
    return parse_canonical_decimal(value, name=key)


def _no_unknown(obj: Mapping[str, object], allowed: Iterable[str], name: str) -> None:
    extra = set(obj) - set(allowed)
    if extra:
        raise F03AnalyzerError("SCHEMA_UNKNOWN_KEY", name + ":" + ",".join(sorted(extra)))


_CASH_INTERVAL_KEYS = (
    "schema", "interval_id", "pre_checkpoint_id", "post_checkpoint_id", "ordered_order_ids", "ordered_fill_ids",
    "fill_count", "principal_total", "cash_fee_total", "api_fee_cost_total", "aggregate_fee_cost_consistency_state",
    "per_fill_fee_identification_state", "isolation_predicates", "eligibility", "rejection_codes", "cash_evidence_id",
    "candidate_hypotheses", "unique_discriminator_state", "matched_hypothesis_id",
)
FORBIDDEN_SHARED_KEYS = frozenset({
    "balance", "balance_dollars", "balance_decimal", "balance_canonical_text", "balance_legacy_cents",
    "portfolio_value", "portfolio_value_legacy_cents", "balance_breakdown", "stable_balance_canonical_text",
    "b_pre", "b_post", "B_pre", "B_post", "absolute_balance", "raw_body", "raw_response", "response_sha256",
    "authorization", "private_key", "api_key", "signature",
})
SECRET_MARKERS: Tuple[str, ...] = (
    "-----BEGIN", "PRIVATE KEY", "KALSHI-ACCESS-KEY", "KALSHI-ACCESS-SIGNATURE", "KALSHI-ACCESS-TIMESTAMP",
    "Authorization:", "Bearer ", "KALSHI_DEMO_PRIVATE_KEY", "KALSHI_DEMO_API_KEY",
)

# ---------------------------------------------------------------------------
# F03 Correction01 (BLOCK F03): closed nested evidence schemas.  Every nested
# object is an EXACT key set; ints exclude bool; economic values are exact
# canonical / source lexemes; enums are closed; references are resolved
# against the run / process / domain / source / evidence graph.  The
# recursive forbidden-marker scan remains an additional defence only.
# ---------------------------------------------------------------------------

BALANCE_SOURCE_BINDING_ID = "KALSHI_OPENAPI_3_29_0_GET_BALANCE_CANONICAL_BINDING_01"
DEMO_ORIGIN = "https://external-api.demo.kalshi.co"
_HEX40_RE = re.compile(r"[0-9a-f]{40}")
_REQ_ID_RE = re.compile(r"req_[0-9a-f]{32}")
_EVT_ID_RE = re.compile(r"evt_[0-9a-f]{32}")
_PROC_RE = re.compile(r"proc_[0-9a-f]{32}")
_ORDER_ID_RE = re.compile(r"[A-Za-z0-9._~-]{1,200}")
_TICKER_RE = re.compile(r"[A-Za-z0-9._~-]{1,200}")
_F03BAL_OBS_RE = re.compile(r"f03bal_[0-9a-f]{32}")
CANDIDATE_HYPOTHESIS_IDS = (
    "MAXIMAL_ZERO_NO_TERMINAL", "NO_REBATE_ZERO_NO_TERMINAL", "MAXIMAL_ZERO_FLOOR_TERMINAL", "MAXIMAL_CARRY_NO_TERMINAL",
)
READ_OBSERVATION_PHASES = ("PREFLIGHT", "B0", "ORDER1_TERMINAL", "ORDER2_TERMINAL", "FINAL", "HALTED_TAIL")
WRITE_CLASSIFICATIONS = (
    "ELIGIBLE_NOT_SENT", "TARGET_BINDING_INVALID", "PERMIT_ISSUANCE_FAILED", "FRESHNESS_EXPIRED_BEFORE_ADAPTER",
    "TRUSTED_T2_BINDING_INVALID", "ADAPTER_EXCEPTION", "TERMINAL", "TERMINAL_UNRECONCILED", "STILL_ACTIVE",
    "BOUND_ACTIVE", "AMBIGUOUS", "ACTIVE_DOMAIN_PERMIT_MISMATCH", "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH",
    "ACTIVE_DOMAIN_CONTRACT_MISMATCH",
)
TERMINAL_CLASSIFICATIONS = ("FULL_FILL", "CANCELED_REMAINDER", "NOT_SENT_MARKET_NOT_DISCRIMINATING")
RUN_STATES = (
    "BOOT_HOLD", "SOURCE_BOUND", "PREFLIGHT_READS", "B0_CHECKPOINT", "CURRENT_PROCESS_WRITER_ADMISSION",
    "WRITER_ELIGIBLE", "ORDER1_PREPARED", "ORDER1_SEND_BOUNDARY", "ORDER1_RECONCILING", "ORDER1_TERMINAL",
    "B1_CHECKPOINT", "ORDER2_DECISION", "ORDER2_PREPARED", "ORDER2_SEND_BOUNDARY", "ORDER2_RECONCILING",
    "ORDER2_TERMINAL", "B2_CHECKPOINT", "FINAL_RECONCILIATION_ONLY", "COMPLETE", "HALTED_HELD",
)


def _schema_fail(path: str, what: str = "") -> F03AnalyzerError:
    return F03AnalyzerError("SCHEMA_NESTED_INVALID", path + (":" + what if what else ""))


def _exact_obj(value: object, keys: Iterable[str], path: str) -> dict:
    if type(value) is not dict:
        raise _schema_fail(path, "not an object")
    if set(value) != set(keys):
        raise _schema_fail(path, "key set " + ",".join(sorted(set(value) ^ set(keys))))
    return value


def _str(value: object, path: str, *, pattern: "re.Pattern | None" = None, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or value == "" or (pattern is not None and pattern.fullmatch(value) is None):
        raise _schema_fail(path, "string")
    return value


def _int(value: object, path: str, *, minimum: int | None = 0, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or (minimum is not None and value < minimum):
        raise _schema_fail(path, "int")
    return value


def _bool(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise _schema_fail(path, "bool")
    return value


def _enum(value: object, allowed: Iterable[str], path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or value not in tuple(allowed):
        raise _schema_fail(path, "enum")
    return value


def _canon(value: object, path: str, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    try:
        return parse_canonical_decimal(value, name=path)
    except F03AnalyzerError:
        raise _schema_fail(path, "canonical decimal") from None


def _lexeme(value: object, path: str, *, count: bool = False) -> Decimal:
    try:
        return parse_fixed_point_count(value, name=path) if count else parse_fixed_point_dollars(value, name=path)
    except F03AnalyzerError:
        raise _schema_fail(path, "source lexeme") from None


def _timestamp(value: object, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or _CANONICAL_TIMESTAMP_RE.fullmatch(value) is None:
        raise _schema_fail(path, "timestamp")
    return value


def _str_list(value: object, path: str, *, pattern: "re.Pattern | None" = None, unique: bool = False) -> list:
    if type(value) is not list:
        raise _schema_fail(path, "list")
    for index, item in enumerate(value):
        _str(item, f"{path}[{index}]", pattern=pattern)
    if unique and len(set(value)) != len(value):
        raise _schema_fail(path, "duplicate")
    return value


def _obj_list(value: object, path: str) -> list:
    if type(value) is not list:
        raise _schema_fail(path, "list")
    return value


_QUESTION_RESULT_KEYS = (
    "schema", "question_id", "status", "scoped_conclusion", "scope_mode", "account_class", "quantum",
    "market_ticker", "event_ticker", "series_ticker", "fee_epoch", "source_identities", "evidence_refs",
    "calculation_refs", "cash_evidence_ids", "independent_cash_evidence_count", "cash_evidence_independence",
    "independent_support_for_fee_hypothesis", "joint_assumptions", "equivalent_untested_alternatives",
    "proves", "does_not_prove", "subobservations",
)
_SUBOBSERVATION_KEYS = frozenset({
    "subobservation", "status", "value", "values", "identified_net_fee", "class_predicted_net_fee", "table_value",
    "table_as_exact_direct_fee_conflicts", "pdf_intended_account_class",
})


def validate_question_result_v1(obj: object) -> Mapping[str, object]:
    if type(obj) is not dict:
        raise F03AnalyzerError("SCHEMA_TYPE_INVALID", "QuestionResultV1")
    _no_unknown(obj, _QUESTION_RESULT_KEYS, "QuestionResultV1")
    for key in _QUESTION_RESULT_KEYS:
        _req(obj, key)
    if obj["schema"] != "QuestionResultV1":
        raise F03AnalyzerError("SCHEMA_REVISION_UNKNOWN", "QuestionResultV1")
    _req_enum(obj, "question_id", QUESTION_IDS)
    _req_enum(obj, "status", (s.value for s in QuestionStatus))
    _req_enum(obj, "scope_mode", (s.value for s in ScopeMode))
    _req_enum(obj, "cash_evidence_independence", (s.value for s in CashEvidenceIndependence))
    _req_enum(obj, "account_class", (s.value for s in AccountClass))
    for key in ("scoped_conclusion", "market_ticker", "event_ticker", "series_ticker", "fee_epoch", "quantum"):
        _str(obj[key], "QuestionResultV1." + key)
    if obj["quantum"] != "UNRESOLVED":
        _canon(obj["quantum"], "QuestionResultV1.quantum")
    _req_type(obj, "independent_support_for_fee_hypothesis", bool)
    _int(obj["independent_cash_evidence_count"], "QuestionResultV1.independent_cash_evidence_count")
    for key in ("source_identities", "evidence_refs", "calculation_refs", "cash_evidence_ids", "joint_assumptions",
                "equivalent_untested_alternatives", "proves", "does_not_prove"):
        _str_list(obj[key], "QuestionResultV1." + key)
    if len(set(obj["cash_evidence_ids"])) != len(obj["cash_evidence_ids"]):
        raise F03AnalyzerError("SCHEMA_DUPLICATE_EVIDENCE", "cash_evidence_ids")
    for index, sub in enumerate(_obj_list(obj["subobservations"], "QuestionResultV1.subobservations")):
        if type(sub) is not dict or "subobservation" not in sub or not set(sub) <= _SUBOBSERVATION_KEYS:
            raise _schema_fail(f"QuestionResultV1.subobservations[{index}]")
        _str(sub["subobservation"], f"subobservations[{index}].subobservation")
        if "status" in sub:
            _enum(sub["status"], (s.value for s in QuestionStatus), f"subobservations[{index}].status")
        if "value" in sub:
            _int(sub["value"], f"subobservations[{index}].value")
        if "values" in sub:
            _str_list(sub["values"], f"subobservations[{index}].values")
        for key in ("identified_net_fee", "class_predicted_net_fee", "table_value"):
            if key in sub:
                _canon(sub[key], f"subobservations[{index}].{key}")
        if "table_as_exact_direct_fee_conflicts" in sub:
            _bool(sub["table_as_exact_direct_fee_conflicts"], f"subobservations[{index}].table")
        if "pdf_intended_account_class" in sub and sub["pdf_intended_account_class"] is not None:
            raise _schema_fail(f"subobservations[{index}].pdf_intended_account_class", "must be null")
    if obj["status"] == QuestionStatus.OBSERVED_MATCH and obj["scope_mode"] == ScopeMode.AGGREGATE_HYPOTHESIS and not obj["joint_assumptions"]:
        raise F03AnalyzerError("SCHEMA_ASSUMPTIONS_REQUIRED", "aggregate observed match")
    if obj["question_id"] == "QF03-04" and obj["independent_support_for_fee_hypothesis"] is not False:
        raise F03AnalyzerError("SCHEMA_Q04_INDEPENDENCE_INVALID")
    return obj


_CANDIDATE_KEYS = ("id", "initializer", "rebate_rule", "terminal_rule", "assumptions", "predicted_total",
                   "positive_rebate_total", "modeled_residual")


def validate_cash_fee_interval_v1(obj: object) -> Mapping[str, object]:
    if type(obj) is not dict:
        raise F03AnalyzerError("SCHEMA_TYPE_INVALID", "CashFeeIntervalV1")
    _no_unknown(obj, _CASH_INTERVAL_KEYS, "CashFeeIntervalV1")
    for key in _CASH_INTERVAL_KEYS:
        _req(obj, key)
    if obj["schema"] != "CashFeeIntervalV1":
        raise F03AnalyzerError("SCHEMA_REVISION_UNKNOWN", "CashFeeIntervalV1")
    _enum(obj["interval_id"], ("I1", "I2"), "interval_id")
    _enum(obj["pre_checkpoint_id"], ("B0", "B1"), "pre_checkpoint_id")
    _enum(obj["post_checkpoint_id"], ("B1", "B2"), "post_checkpoint_id")
    _str_list(obj["ordered_order_ids"], "ordered_order_ids", pattern=_ORDER_ID_RE, unique=True)
    _str_list(obj["ordered_fill_ids"], "ordered_fill_ids", unique=True)
    if _int(obj["fill_count"], "fill_count") != len(obj["ordered_fill_ids"]):
        raise _schema_fail("fill_count", "does not equal ordered_fill_ids")
    _bool(obj["eligibility"], "eligibility")
    for key in ("principal_total", "cash_fee_total", "api_fee_cost_total"):
        _req_decimal_or_null(obj, key)
    _req_enum(obj, "aggregate_fee_cost_consistency_state", (s.value for s in AggregateConsistencyState))
    _req_enum(obj, "per_fill_fee_identification_state", (s.value for s in PerFillIdentificationState))
    _req_enum(obj, "unique_discriminator_state", (s.value for s in UniqueDiscriminatorState))
    preds = _req_type(obj, "isolation_predicates", dict)
    if set(preds) != set(ISOLATION_PREDICATES):
        raise _schema_fail("isolation_predicates", "incomplete predicate set")
    for name, entry in preds.items():
        _exact_obj(entry, ("state", "evidence_refs"), "isolation_predicates." + name)
        _req_enum(entry, "state", (s.value for s in PredicateState))
        _str_list(entry["evidence_refs"], "isolation_predicates." + name + ".evidence_refs")
    if obj["eligibility"] and any(e["state"] != PredicateState.PASS for e in preds.values()):
        raise _schema_fail("eligibility", "eligible with non-PASS predicate")
    ids = []
    for index, hyp in enumerate(_obj_list(obj["candidate_hypotheses"], "candidate_hypotheses")):
        _exact_obj(hyp, _CANDIDATE_KEYS, f"candidate_hypotheses[{index}]")
        ids.append(_enum(hyp["id"], CANDIDATE_HYPOTHESIS_IDS, f"candidate_hypotheses[{index}].id"))
        _req_enum(hyp, "initializer", (s.value for s in Initializer))
        _req_enum(hyp, "rebate_rule", (s.value for s in RebateRule))
        _req_enum(hyp, "terminal_rule", (s.value for s in TerminalRule))
        for key in ("predicted_total", "positive_rebate_total", "modeled_residual"):
            _req_decimal_or_null(hyp, key)
        if not _str_list(hyp["assumptions"], f"candidate_hypotheses[{index}].assumptions"):
            raise F03AnalyzerError("SCHEMA_ASSUMPTIONS_REQUIRED", "hypothesis")
    if len(set(ids)) != len(ids):
        raise _schema_fail("candidate_hypotheses", "duplicate id")
    matched = obj["matched_hypothesis_id"]
    if matched is not None and matched not in ids:
        raise _schema_fail("matched_hypothesis_id", "unresolved reference")
    if (obj["unique_discriminator_state"] == UniqueDiscriminatorState.UNIQUE_MATCH) != (matched is not None):
        raise _schema_fail("matched_hypothesis_id", "inconsistent with discriminator state")
    _str_list(obj["rejection_codes"], "rejection_codes")
    _str(obj["cash_evidence_id"], "cash_evidence_id")
    assert_shared_evidence_sanitized(obj)
    return obj


_WRITE_KEYS = (
    "request_id", "classification", "t3_charged", "transport_invoked", "prepared_request_sha256", "intent_event_id",
    "prepared_event_id", "send_boundary_event_id", "detail", "send_started_monotonic_ns", "send_completed_monotonic_ns",
    "send_started_utc", "send_completed_utc",
)
_ORDER_KEYS = (
    "schema", "probe_order_index", "client_order_id", "order_id", "side", "outcome_side", "quantity", "limit_price",
    "time_in_force", "create", "cancel", "response_classification", "exact_order_observations", "fills",
    "terminal_classification", "remaining_quantity", "ledger_anchors", "hypothesis_accumulator_start",
    "hypothesis_accumulator_end", "observed_fill_fees",
)
_ORDER_FILL_KEYS = ("fill_id", "trade_id", "order_id", "ticker", "count_fp", "yes_price_dollars", "is_taker",
                    "created_time", "fee_cost")
_EXACT_ORDER_KEYS = ("order_id", "status", "fill_count_fp", "remaining_count_fp", "initial_count_fp")
_ANCHOR_KEYS = ("action", "request_id", "t1", "t2", "t3")
_ANCHOR_EVENT_KEYS = ("event_id", "sequence", "event_hash")
_ACCUMULATOR_KEYS = ("evidence_class", "authoritative", "value")
_OBSERVED_FILL_FEE_KEYS = (
    "schema", "fill_id", "trade_id", "order_id", "ticker", "market_ticker", "subaccount_number", "exchange_index",
    "outcome_side", "book_side", "count_fp", "yes_price_dollars", "no_price_dollars", "is_taker", "created_time", "ts",
    "api_fee_cost", "k", "M", "h", "per_fill_fee_identification_state", "identified_net_fee", "observed_rebate",
    "observed_rebate_null_reason", "hypothesis_rows", "completeness", "model_fee", "trade_fee", "revenue",
    "aligned_change", "rounding_fee", "chronology_state",
)
_HYPOTHESIS_ROW_KEYS = (
    "quantity", "price", "k", "M", "h", "accumulator_before_hypothesis", "model_fee", "trade_fee", "revenue",
    "aligned_change", "rounding_fee", "before_rebate_hypothesis", "rebate_hypothesis", "net_fee_hypothesis",
    "accumulator_after_hypothesis", "balance_change_hypothesis", "rebate_rule", "initializer", "evidence_class",
)
_CHECKPOINT_KEYS = (
    "schema", "boundary", "state", "attempts", "successes", "consumed_balance_gets", "failed_reads", "failure_codes",
    "snapshot_evidence", "final_updated_ts", "stale_by_fill_watermark", "evaluator_called", "halt_code",
)
_SNAPSHOT_EVIDENCE_KEYS = (
    "schema_revision", "observation_id", "source_binding_id", "source_raw_sha256", "operation", "request_identity_sha256",
    "process_instance_id", "domain_binding_id", "domain_binding_sha256", "subaccount", "exchange_index",
    "request_ordinal", "balance_scale", "updated_ts", "request_started_utc", "response_completed_utc",
    "request_started_monotonic_ns", "response_completed_monotonic_ns", "request_count", "automatic_retry_count",
    "followed_redirect_count", "parse_state", "result_state",
)
_RUN_KEYS = (
    "schema", "run_id", "environment", "origin", "canonical_commit", "canonical_tree", "canonical_parent",
    "implementation_artifacts", "subaccount_number", "exchange_index", "ticker", "event_ticker", "series_ticker",
    "source_identities", "account_class_evidence_state", "quantum", "run_started_ns", "active_write_deadline_ns",
    "reconciliation_deadline_ns", "utc_audit", "counters", "baseline_reconciliation_identity",
    "final_reconciliation_identity", "orders", "balance_observations", "read_observations", "question_results", "halt",
    "account_class_evidence_id", "fee_regime_inputs", "cash_fee_intervals", "process_instance_id", "domain_binding_id",
    "domain_binding_sha256", "run_claim",
)
_COUNTER_KEYS = (
    "get", "create", "cancel", "redirects", "automatic_retries", "acquired_quantity", "worst_case_outlay_bound",
)
_FEE_REGIME_KEYS = ("fee_epoch_id", "fee_type", "fee_schedule_edition", "taker_multiplier", "maker_multiplier", "provenance")
_RUN_CLAIM_KEYS = ("claim_schema", "claim_sha256", "run_folder_name")


def _validate_write(value: object, path: str) -> dict | None:
    if value is None:
        return None
    w = _exact_obj(value, _WRITE_KEYS, path)
    _str(w["request_id"], path + ".request_id", pattern=_REQ_ID_RE)
    _enum(w["classification"], WRITE_CLASSIFICATIONS, path + ".classification")
    _bool(w["t3_charged"], path + ".t3_charged")
    _bool(w["transport_invoked"], path + ".transport_invoked")
    _str(w["prepared_request_sha256"], path + ".prepared_request_sha256", pattern=_HEX64_RE)
    for key in ("intent_event_id", "prepared_event_id", "send_boundary_event_id"):
        _str(w[key], path + "." + key, pattern=_EVT_ID_RE, nullable=True)
    _str(w["detail"], path + ".detail", nullable=True)
    _int(w["send_started_monotonic_ns"], path + ".send_started_monotonic_ns", nullable=True)
    _int(w["send_completed_monotonic_ns"], path + ".send_completed_monotonic_ns", nullable=True)
    _timestamp(w["send_started_utc"], path + ".send_started_utc", nullable=True)
    _timestamp(w["send_completed_utc"], path + ".send_completed_utc", nullable=True)
    if w["t3_charged"] != (w["send_boundary_event_id"] is not None):
        raise _schema_fail(path, "T3 charge without durable boundary reference")
    if w["transport_invoked"] and not w["t3_charged"]:
        raise _schema_fail(path, "transport without T3")
    return w


def _validate_order(order: object, index: int, run: Mapping[str, object]) -> dict:
    path = f"orders[{index}]"
    o = _exact_obj(order, _ORDER_KEYS, path)
    if o["schema"] != "FeeProbeOrderV1":
        raise F03AnalyzerError("SCHEMA_REVISION_UNKNOWN", path)
    if type(o["probe_order_index"]) is not int or o["probe_order_index"] not in (1, 2):
        raise _schema_fail(path + ".probe_order_index")
    _str(o["client_order_id"], path + ".client_order_id", pattern=_UUID4_RE, nullable=True)
    _str(o["order_id"], path + ".order_id", pattern=_ORDER_ID_RE, nullable=True)
    if (o["side"], o["outcome_side"], o["quantity"], o["time_in_force"]) != ("bid", "YES", "1", "good_till_canceled"):
        raise _schema_fail(path, "direction/quantity/tif")
    limit = _canon(o["limit_price"], path + ".limit_price")
    if not (Decimal(0) < limit <= MAX_LIMIT_PRICE):
        raise _schema_fail(path + ".limit_price", "bound")
    create = _validate_write(o["create"], path + ".create")
    cancel = _validate_write(o["cancel"], path + ".cancel")
    if cancel is not None and (create is None or o["order_id"] is None):
        raise _schema_fail(path + ".cancel", "cancel without bound create")
    _enum(o["response_classification"], WRITE_CLASSIFICATIONS, path + ".response_classification", nullable=True)
    if (create is None) != (o["response_classification"] is None) or (create is not None and create["classification"] != o["response_classification"]):
        raise _schema_fail(path + ".response_classification", "does not reference create classification")
    for j, row in enumerate(_obj_list(o["exact_order_observations"], path + ".exact_order_observations")):
        r = _exact_obj(row, _EXACT_ORDER_KEYS, f"{path}.exact_order_observations[{j}]")
        if r["order_id"] != o["order_id"]:
            raise _schema_fail(f"{path}.exact_order_observations[{j}]", "foreign order reference")
        _enum(r["status"], ("executed", "canceled", "resting"), f"{path}.exact_order_observations[{j}].status")
        for key in ("fill_count_fp", "remaining_count_fp", "initial_count_fp"):
            _lexeme(r[key], f"{path}.exact_order_observations[{j}].{key}", count=True)
    fill_ids = []
    for j, row in enumerate(_obj_list(o["fills"], path + ".fills")):
        f = _exact_obj(row, _ORDER_FILL_KEYS, f"{path}.fills[{j}]")
        fill_ids.append(_str(f["fill_id"], f"{path}.fills[{j}].fill_id"))
        if f["trade_id"] != f["fill_id"] or f["order_id"] != o["order_id"] or f["ticker"] != run["ticker"]:
            raise _schema_fail(f"{path}.fills[{j}]", "identity/order/ticker reference")
        _lexeme(f["count_fp"], f"{path}.fills[{j}].count_fp", count=True)
        _lexeme(f["yes_price_dollars"], f"{path}.fills[{j}].yes_price_dollars")
        _lexeme(f["fee_cost"], f"{path}.fills[{j}].fee_cost")
        _bool(f["is_taker"], f"{path}.fills[{j}].is_taker")
        _timestamp(f["created_time"], f"{path}.fills[{j}].created_time")
    if len(set(fill_ids)) != len(fill_ids):
        raise _schema_fail(path + ".fills", "duplicate fill")
    _enum(o["terminal_classification"], TERMINAL_CLASSIFICATIONS, path + ".terminal_classification", nullable=True)
    _canon(o["remaining_quantity"], path + ".remaining_quantity", nullable=True)
    for j, anchor in enumerate(_obj_list(o["ledger_anchors"], path + ".ledger_anchors")):
        a = _exact_obj(anchor, _ANCHOR_KEYS, f"{path}.ledger_anchors[{j}]")
        _enum(a["action"], ("CREATE", "CANCEL"), f"{path}.ledger_anchors[{j}].action")
        ref = create if a["action"] == "CREATE" else cancel
        if ref is None or a["request_id"] != ref["request_id"]:
            raise _schema_fail(f"{path}.ledger_anchors[{j}]", "unresolved write reference")
        sequences = []
        for key, ref_key in (("t1", "intent_event_id"), ("t2", "prepared_event_id"), ("t3", "send_boundary_event_id")):
            e = _exact_obj(a[key], _ANCHOR_EVENT_KEYS, f"{path}.ledger_anchors[{j}].{key}")
            if e["event_id"] != ref[ref_key]:
                raise _schema_fail(f"{path}.ledger_anchors[{j}].{key}", "event reference mismatch")
            sequences.append(_int(e["sequence"], f"{path}.ledger_anchors[{j}].{key}.sequence", minimum=1))
            _str(e["event_hash"], f"{path}.ledger_anchors[{j}].{key}.event_hash", pattern=_HEX64_RE)
        if sequences != [sequences[0], sequences[0] + 1, sequences[0] + 2]:
            raise _schema_fail(f"{path}.ledger_anchors[{j}]", "T1/T2/T3 not contiguous")
    for key in ("hypothesis_accumulator_start", "hypothesis_accumulator_end"):
        acc = _exact_obj(o[key], _ACCUMULATOR_KEYS, f"{path}.{key}")
        if acc["evidence_class"] != EVIDENCE_CLASS_MODEL_HYPOTHESIS or acc["authoritative"] is not False:
            raise _schema_fail(f"{path}.{key}", "must be a non-authoritative model hypothesis")
        _canon(acc["value"], f"{path}.{key}.value", nullable=True)
    fee_ids = []
    for j, rec in enumerate(_obj_list(o["observed_fill_fees"], path + ".observed_fill_fees")):
        fee_ids.append(_validate_observed_fill_fee(rec, f"{path}.observed_fill_fees[{j}]", order=o, run=run))
    if fee_ids != fill_ids:
        raise _schema_fail(path + ".observed_fill_fees", "does not reference exactly the order fills in order")
    return o


def _validate_observed_fill_fee(rec: object, path: str, *, order: Mapping[str, object], run: Mapping[str, object]) -> str:
    r = _exact_obj(rec, _OBSERVED_FILL_FEE_KEYS, path)
    if r["schema"] != "ObservedFillFeeV1":
        raise F03AnalyzerError("SCHEMA_REVISION_UNKNOWN", path)
    fid = _str(r["fill_id"], path + ".fill_id")
    if (r["trade_id"] != fid or r["order_id"] != order["order_id"] or r["ticker"] != run["ticker"]
            or r["market_ticker"] != run["ticker"] or r["exchange_index"] != run["exchange_index"]
            or type(r["exchange_index"]) is not int):
        raise _schema_fail(path, "identity/domain reference")
    if r["subaccount_number"] is not None and (type(r["subaccount_number"]) is not int or r["subaccount_number"] != run["subaccount_number"]):
        raise _schema_fail(path + ".subaccount_number", "foreign subaccount")
    if (r["outcome_side"], r["book_side"]) != ("yes", "bid"):
        raise _schema_fail(path, "direction")
    _lexeme(r["count_fp"], path + ".count_fp", count=True)
    _lexeme(r["yes_price_dollars"], path + ".yes_price_dollars")
    _lexeme(r["no_price_dollars"], path + ".no_price_dollars")
    _bool(r["is_taker"], path + ".is_taker")
    _timestamp(r["created_time"], path + ".created_time")
    _int(r["ts"], path + ".ts", nullable=True)
    fee = _exact_obj(r["api_fee_cost"], ("lexeme", "canonical"), path + ".api_fee_cost")
    if canonical_decimal_text(_lexeme(fee["lexeme"], path + ".api_fee_cost.lexeme")) != fee["canonical"]:
        raise _schema_fail(path + ".api_fee_cost", "canonical mismatch")
    for key in ("k", "M", "h"):
        entry = _exact_obj(r[key], ("value", "provenance"), f"{path}.{key}")
        _canon(entry["value"], f"{path}.{key}.value", nullable=(key == "h"))
        _str(entry["provenance"], f"{path}.{key}.provenance")
    if r["k"]["value"] not in (canonical_decimal_text(K_TAKER), canonical_decimal_text(K_MAKER)):
        raise _schema_fail(path + ".k", "not a source role coefficient")
    if r["h"]["value"] != run["quantum"]:
        raise _schema_fail(path + ".h", "not the run quantum")
    _enum(r["per_fill_fee_identification_state"], (s.value for s in PerFillIdentificationState), path + ".per_fill_state")
    _canon(r["identified_net_fee"], path + ".identified_net_fee", nullable=True)
    if r["identified_net_fee"] is not None and r["per_fill_fee_identification_state"] != PerFillIdentificationState.SINGLE_FILL_IDENTIFIED:
        raise _schema_fail(path + ".identified_net_fee", "without single-fill identification")
    if r["observed_rebate"] is not None:
        raise _schema_fail(path + ".observed_rebate", "never emitted from aggregate evidence")
    _str(r["observed_rebate_null_reason"], path + ".observed_rebate_null_reason")
    _enum(r["completeness"], ("COMPLETE",), path + ".completeness")
    for key in ("model_fee", "trade_fee", "revenue", "aligned_change", "rounding_fee"):
        _canon(r[key], f"{path}.{key}", nullable=r["h"]["value"] is None)
    _enum(r["chronology_state"], (CHRONOLOGY_UNIQUE, CHRONOLOGY_ENUMERATED, CHRONOLOGY_BOUND_EXCEEDED), path + ".chronology_state")
    rows = _obj_list(r["hypothesis_rows"], path + ".hypothesis_rows")
    if rows and r["chronology_state"] != CHRONOLOGY_UNIQUE:
        raise _schema_fail(path + ".hypothesis_rows", "per-fill rows require a unique authoritative order")
    for j, row in enumerate(rows):
        x = _exact_obj(row, _HYPOTHESIS_ROW_KEYS, f"{path}.hypothesis_rows[{j}]")
        for key in _HYPOTHESIS_ROW_KEYS[:16]:
            _canon(x[key], f"{path}.hypothesis_rows[{j}].{key}")
        _enum(x["rebate_rule"], (s.value for s in RebateRule), f"{path}.hypothesis_rows[{j}].rebate_rule")
        _enum(x["initializer"], (s.value for s in Initializer), f"{path}.hypothesis_rows[{j}].initializer")
        if x["evidence_class"] != EVIDENCE_CLASS_MODEL_HYPOTHESIS:
            raise _schema_fail(f"{path}.hypothesis_rows[{j}].evidence_class")
    return fid


def _validate_checkpoint(cp: object, index: int, run: Mapping[str, object]) -> str:
    path = f"balance_observations[{index}]"
    c = _exact_obj(cp, _CHECKPOINT_KEYS, path)
    if c["schema"] != "BalanceCheckpointV1":
        raise F03AnalyzerError("SCHEMA_REVISION_UNKNOWN", path)
    boundary = _enum(c["boundary"], ("B0", "B1", "B2"), path + ".boundary")
    _enum(c["state"], (s.value for s in CheckpointState), path + ".state")
    attempts = _int(c["attempts"], path + ".attempts")
    successes = _int(c["successes"], path + ".successes")
    consumed = _int(c["consumed_balance_gets"], path + ".consumed_balance_gets")
    failed = _int(c["failed_reads"], path + ".failed_reads")
    if attempts > 3 or successes + failed != attempts or consumed > attempts:
        raise _schema_fail(path, "attempt accounting")
    if c["state"] == CheckpointState.STABLE and (successes < 2 or failed):
        raise _schema_fail(path, "STABLE requires >=2 successes and no failure")
    if failed and c["state"] != CheckpointState.FAILED:
        raise _schema_fail(path, "failed read must be FAILED")
    _str_list(c["failure_codes"], path + ".failure_codes")
    if len(c["failure_codes"]) != failed:
        raise _schema_fail(path + ".failure_codes", "count")
    evidence = _obj_list(c["snapshot_evidence"], path + ".snapshot_evidence")
    if len(evidence) != successes:
        raise _schema_fail(path + ".snapshot_evidence", "count")
    for j, ev in enumerate(evidence):
        e = _exact_obj(ev, _SNAPSHOT_EVIDENCE_KEYS, f"{path}.snapshot_evidence[{j}]")
        # Exact int typing precedes semantic equality: bool is never an int
        # (True == 1, False == 0) and an integral float is never an int.
        for key in ("schema_revision", "request_count", "automatic_retry_count", "followed_redirect_count"):
            _int(e[key], f"{path}.snapshot_evidence[{j}].{key}")
        if (e["schema_revision"] != 1 or e["operation"] != "GET_BALANCE" or e["source_binding_id"] != BALANCE_SOURCE_BINDING_ID
                or e["source_raw_sha256"] != SOURCE_IDENTITIES["KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml"][1]
                or e["process_instance_id"] != run["process_instance_id"] or e["domain_binding_id"] != run["domain_binding_id"]
                or e["domain_binding_sha256"] != run["domain_binding_sha256"] or e["subaccount"] != run["subaccount_number"]
                or e["exchange_index"] != run["exchange_index"] or e["parse_state"] != "RESPONSE_VALIDATED"
                or e["result_state"] != "SNAPSHOT_CONSTRUCTED" or e["request_count"] != 1
                or e["automatic_retry_count"] != 0 or e["followed_redirect_count"] != 0):
            raise _schema_fail(f"{path}.snapshot_evidence[{j}]", "run/process/domain/source binding")
        _str(e["observation_id"], f"{path}.snapshot_evidence[{j}].observation_id", pattern=_F03BAL_OBS_RE)
        _str(e["request_identity_sha256"], f"{path}.snapshot_evidence[{j}].request_identity_sha256", pattern=_HEX64_RE)
        for key in ("subaccount", "exchange_index", "request_ordinal", "balance_scale", "updated_ts",
                    "request_started_monotonic_ns", "response_completed_monotonic_ns"):
            _int(e[key], f"{path}.snapshot_evidence[{j}].{key}")
        _timestamp(e["request_started_utc"], f"{path}.snapshot_evidence[{j}].request_started_utc")
        _timestamp(e["response_completed_utc"], f"{path}.snapshot_evidence[{j}].response_completed_utc")
    _int(c["final_updated_ts"], path + ".final_updated_ts", nullable=True)
    _bool(c["stale_by_fill_watermark"], path + ".stale_by_fill_watermark")
    _bool(c["evaluator_called"], path + ".evaluator_called")
    if successes == 0 and c["evaluator_called"]:
        raise _schema_fail(path + ".evaluator_called", "evaluator called with zero successes")
    _enum(c["halt_code"], (h.value for h in HaltCode), path + ".halt_code", nullable=True)
    return boundary


def _validate_read_observation(obs: object, index: int) -> None:
    path = f"read_observations[{index}]"
    if type(obs) is not dict:
        raise _schema_fail(path)
    phase = _enum(obs.get("phase"), READ_OBSERVATION_PHASES, path + ".phase")
    if phase == "PREFLIGHT":
        _exact_obj(obs, ("phase", "page_commitments", "opportunity", "table_price_level_present"), path)
        _str(obs["opportunity"], path + ".opportunity")
        _bool(obs["table_price_level_present"], path + ".table_price_level_present")
    elif phase == "B0":
        _exact_obj(obs, ("phase", "sufficient_existing_balance", "conservative_incremental_bound"), path)
        _bool(obs["sufficient_existing_balance"], path + ".sufficient_existing_balance")
        _canon(obs["conservative_incremental_bound"], path + ".conservative_incremental_bound")
        return
    else:
        _exact_obj(obs, ("phase", "page_commitments"), path)
    _str_list(obs["page_commitments"], path + ".page_commitments", pattern=_HEX64_RE)


def _expected_source_identity_strings() -> list:
    return [f"{name}:{sha}" for name, (_b, sha) in sorted(SOURCE_IDENTITIES.items())]


def validate_fee_experiment_run_v1(obj: object) -> Mapping[str, object]:
    """Strict CLOSED ``FeeExperimentRunV1`` (sanitized shared projection) with
    every nested record validated and every reference resolved against the
    run / process / domain / source / evidence graph."""
    if type(obj) is not dict:
        raise F03AnalyzerError("SCHEMA_TYPE_INVALID", "FeeExperimentRunV1")
    _no_unknown(obj, _RUN_KEYS, "FeeExperimentRunV1")
    for key in _RUN_KEYS:
        _req(obj, key)
    if obj["schema"] != "FeeExperimentRunV1":
        raise F03AnalyzerError("SCHEMA_REVISION_UNKNOWN", "FeeExperimentRunV1")
    run_id = _req_type(obj, "run_id", str)
    if _UUID4_RE.fullmatch(run_id) is None:
        raise F03AnalyzerError("SCHEMA_ID_INVALID", "run_id")
    if obj["environment"] != "KALSHI_DEMO" or obj["origin"] != DEMO_ORIGIN:
        raise F03AnalyzerError(HaltCode.DEMO_ORIGIN_MISMATCH.value)
    for key in ("canonical_commit", "canonical_tree", "canonical_parent"):
        _str(obj[key], key, pattern=_HEX40_RE)
    arts = obj["implementation_artifacts"]
    if type(arts) is not dict or not arts:
        raise _schema_fail("implementation_artifacts")
    for path, digest in arts.items():
        _str(path, "implementation_artifacts.key")
        _str(digest, "implementation_artifacts." + path, pattern=_HEX64_RE)
    _int(obj["subaccount_number"], "subaccount_number", minimum=1)
    _int(obj["exchange_index"], "exchange_index")
    for key in ("ticker", "event_ticker", "series_ticker"):
        _str(obj[key], key, pattern=_TICKER_RE)
    expected_sources = {name: {"bytes": size, "sha256": sha} for name, (size, sha) in sorted(SOURCE_IDENTITIES.items())}
    if obj["source_identities"] != expected_sources:
        raise _schema_fail("source_identities", "not the controlling source identities")
    account_class = _enum(obj["account_class_evidence_state"], (s.value for s in AccountClass), "account_class_evidence_state")
    if account_class == AccountClass.UNRESOLVED:
        if obj["quantum"] is not None:
            raise _schema_fail("quantum", "unresolved class carries no quantum")
    elif _canon(obj["quantum"], "quantum") != quantum_for_account_class(account_class):
        raise _schema_fail("quantum", "does not match account class")
    for key in ("run_started_ns", "active_write_deadline_ns", "reconciliation_deadline_ns"):
        _int(obj[key], key)
    if obj["active_write_deadline_ns"] < obj["run_started_ns"] or obj["reconciliation_deadline_ns"] < obj["run_started_ns"]:
        raise _schema_fail("deadlines", "ordering")
    if type(obj["utc_audit"]) is not dict:
        raise _schema_fail("utc_audit")
    if obj["utc_audit"]:
        _exact_obj(obj["utc_audit"], ("run_started_utc",), "utc_audit")
        _timestamp(obj["utc_audit"]["run_started_utc"], "utc_audit.run_started_utc")
    counters = _exact_obj(obj["counters"], _COUNTER_KEYS, "counters")
    for key in ("get", "create", "cancel", "redirects", "automatic_retries"):
        _int(counters[key], "counters." + key)
    acquired = _canon(counters["acquired_quantity"], "counters.acquired_quantity")
    _canon(counters["worst_case_outlay_bound"], "counters.worst_case_outlay_bound")
    if counters["get"] > 200 or counters["create"] > 2 or counters["cancel"] > 2 or counters["redirects"] != 0 or counters["automatic_retries"] != 0:
        raise F03AnalyzerError(HaltCode.BUDGET_EXCEEDED.value, "counters")
    for key in ("baseline_reconciliation_identity", "final_reconciliation_identity"):
        _str(obj[key], key, pattern=_HEX64_RE, nullable=True)
    _str(obj["process_instance_id"], "process_instance_id", pattern=_PROC_RE)
    _str(obj["domain_binding_id"], "domain_binding_id")
    _str(obj["domain_binding_sha256"], "domain_binding_sha256", pattern=_HEX64_RE)
    if obj["domain_binding_id"] != "KEDB1_" + obj["domain_binding_sha256"]:
        raise _schema_fail("domain_binding_id", "does not bind domain_binding_sha256")
    claim = _exact_obj(obj["run_claim"], _RUN_CLAIM_KEYS, "run_claim")
    if claim["claim_schema"] != "F03_RUN_CLAIM_V1" or claim["run_folder_name"] != run_id:
        raise _schema_fail("run_claim", "claim does not bind this run")
    _str(claim["claim_sha256"], "run_claim.claim_sha256", pattern=_HEX64_RE)
    _str(obj["account_class_evidence_id"], "account_class_evidence_id")
    fee = _exact_obj(obj["fee_regime_inputs"], _FEE_REGIME_KEYS, "fee_regime_inputs")
    if fee["fee_type"] != "quadratic" or fee["fee_schedule_edition"] != FEE_SCHEDULE_EDITION or _canon(fee["taker_multiplier"], "taker_multiplier") != 1:
        raise _schema_fail("fee_regime_inputs")
    maker = _canon(fee["maker_multiplier"], "maker_multiplier")
    if not (Decimal(0) < maker <= Decimal(1)):
        raise _schema_fail("fee_regime_inputs.maker_multiplier")
    _str(fee["fee_epoch_id"], "fee_regime_inputs.fee_epoch_id")
    _str(fee["provenance"], "fee_regime_inputs.provenance")
    # -- orders ---------------------------------------------------------------
    orders = _obj_list(obj["orders"], "orders")
    if len(orders) > 2:
        raise _schema_fail("orders", "more than two probe orders")
    order_by_id = {}
    for index, order in enumerate(orders):
        o = _validate_order(order, index, obj)
        if o["probe_order_index"] != index + 1:
            raise _schema_fail(f"orders[{index}].probe_order_index", "order sequence")
        if o["order_id"] is not None:
            if o["order_id"] in order_by_id:
                raise _schema_fail("orders", "duplicate order id")
            order_by_id[o["order_id"]] = o
    create_charged = sum(1 for o in orders if o["create"] is not None and o["create"]["t3_charged"])
    cancel_charged = sum(1 for o in orders if o["cancel"] is not None and o["cancel"]["t3_charged"])
    if counters["create"] != create_charged or counters["cancel"] != cancel_charged:
        raise _schema_fail("counters", "write counters do not reference the order records")
    fill_total = exact_add(*(Decimal(f["count_fp"]) for o in orders for f in o["fills"])) if any(o["fills"] for o in orders) else Decimal(0)
    if acquired != fill_total or acquired > SPEC_TOTAL_ACQUIRED_QUANTITY_MAX:
        raise _schema_fail("counters.acquired_quantity", "does not equal referenced authoritative fills")
    # -- checkpoints / read observations ----------------------------------------
    boundaries = [_validate_checkpoint(cp, i, obj) for i, cp in enumerate(_obj_list(obj["balance_observations"], "balance_observations"))]
    if len(set(boundaries)) != len(boundaries) or len(boundaries) > 3:
        raise _schema_fail("balance_observations", "duplicate/excess boundary")
    for i, obs in enumerate(_obj_list(obj["read_observations"], "read_observations")):
        _validate_read_observation(obs, i)
    # -- intervals ------------------------------------------------------------
    cash_ids = set()
    for i, interval in enumerate(_obj_list(obj["cash_fee_intervals"], "cash_fee_intervals")):
        validate_cash_fee_interval_v1(interval)
        if interval["cash_evidence_id"] != f"{run_id}:{interval['interval_id']}" or interval["cash_evidence_id"] in cash_ids:
            raise _schema_fail(f"cash_fee_intervals[{i}].cash_evidence_id", "not bound to this run")
        cash_ids.add(interval["cash_evidence_id"])
        if interval["pre_checkpoint_id"] not in boundaries or interval["post_checkpoint_id"] not in boundaries:
            raise _schema_fail(f"cash_fee_intervals[{i}]", "unresolved checkpoint reference")
        referenced_fills = []
        for order_id in interval["ordered_order_ids"]:
            if order_id not in order_by_id:
                raise _schema_fail(f"cash_fee_intervals[{i}].ordered_order_ids", "unresolved order reference")
            referenced_fills.extend(f["fill_id"] for f in order_by_id[order_id]["fills"])
        if sorted(referenced_fills) != sorted(interval["ordered_fill_ids"]):
            raise _schema_fail(f"cash_fee_intervals[{i}].ordered_fill_ids", "does not equal referenced order fills")
    # -- questions: exactly QF03-01..05, one each, scope + source + cash refs ---
    questions = _obj_list(obj["question_results"], "question_results")
    for result in questions:
        validate_question_result_v1(result)
    if [r["question_id"] for r in questions] != list(QUESTION_IDS):
        raise _schema_fail("question_results", "must be exactly QF03-01..05 once each in order")
    expected_quantum = obj["quantum"] if obj["quantum"] is not None else "UNRESOLVED"
    for r in questions:
        if (r["account_class"], r["quantum"], r["market_ticker"], r["event_ticker"], r["series_ticker"], r["fee_epoch"]) != (
                account_class, expected_quantum, obj["ticker"], obj["event_ticker"], obj["series_ticker"], fee["fee_epoch_id"]):
            raise _schema_fail("question_results." + r["question_id"], "scope not bound to this run")
        if r["source_identities"] != _expected_source_identity_strings():
            raise _schema_fail("question_results." + r["question_id"], "source identities")
        if not set(r["cash_evidence_ids"]) <= cash_ids:
            raise _schema_fail("question_results." + r["question_id"], "unresolved cash evidence reference")
    # -- halt -----------------------------------------------------------------
    halt = obj["halt"]
    if halt is not None:
        h = _exact_obj(halt, ("code", "state_history"), "halt")
        _enum(h["code"], (c.value for c in HaltCode), "halt.code")
        history = _obj_list(h["state_history"], "halt.state_history")
        for i, state in enumerate(history):
            _enum(state, RUN_STATES, f"halt.state_history[{i}]")
        if not history or history[-1] != "HALTED_HELD":
            raise _schema_fail("halt.state_history", "halt must end HALTED_HELD")
    assert_shared_evidence_sanitized(obj)
    return obj


def assert_shared_evidence_sanitized(obj: object, *, path: str = "$") -> None:
    """Recursive whitelist-companion scan: absolute-balance keys and known
    credential/header/PEM markers in shared output fail closed with
    ``EVIDENCE_SANITIZATION_FAILED``.  Economic floats are also rejected."""
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if type(key) is not str:
                raise F03AnalyzerError(HaltCode.EVIDENCE_SANITIZATION_FAILED.value, path)
            if key in FORBIDDEN_SHARED_KEYS:
                raise F03AnalyzerError(HaltCode.EVIDENCE_SANITIZATION_FAILED.value, path + "." + key)
            assert_shared_evidence_sanitized(value, path=path + "." + key)
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            assert_shared_evidence_sanitized(value, path=f"{path}[{index}]")
    elif isinstance(obj, str):
        upper = obj.upper()
        for marker in SECRET_MARKERS:
            if marker.upper() in upper:
                raise F03AnalyzerError(HaltCode.EVIDENCE_SANITIZATION_FAILED.value, path)
    elif isinstance(obj, float):
        raise F03AnalyzerError(HaltCode.EVIDENCE_SANITIZATION_FAILED.value, path + " float")
    elif obj is None or isinstance(obj, (bool, int)):
        return
    else:
        raise F03AnalyzerError(HaltCode.EVIDENCE_SANITIZATION_FAILED.value, path + " type")


# ---------------------------------------------------------------------------
# F03-SRC-002 / F03-DIRECTION-001 -- the extra pure fee-field parser over a raw
# GET_FILLS row already accepted by the protected active-V2 page validation.
# It never weakens or replaces the protected parser; it only reads the
# additional source-bound fee/role/time fields from get_fills.md.
# ---------------------------------------------------------------------------

_FILL_REQUIRED_SOURCE_FIELDS = (
    "fill_id", "exchange_index", "trade_id", "order_id", "ticker", "market_ticker", "outcome_side",
    "book_side", "count_fp", "yes_price_dollars", "no_price_dollars", "is_taker", "fee_cost",
)


@dataclass(frozen=True, slots=True)
class ObservedFillFeeFieldsV1:
    fill_id: str
    trade_id: str
    order_id: str
    ticker: str
    market_ticker: str
    exchange_index: int
    subaccount_number: int | None
    outcome_side: str
    book_side: str
    count_lexeme: str
    quantity: Decimal
    yes_price_lexeme: str
    yes_price: Decimal
    no_price_lexeme: str
    is_taker: bool
    created_time: str
    ts: int | None
    fee_cost_lexeme: str
    api_fee_cost: Decimal

    def identity_tuple(self) -> tuple:
        return (self.fill_id, self.trade_id, self.order_id, self.ticker, self.market_ticker, self.exchange_index,
                self.subaccount_number, self.outcome_side, self.book_side, self.count_lexeme, self.yes_price_lexeme,
                self.no_price_lexeme, self.is_taker, self.created_time, self.ts, self.fee_cost_lexeme)


def parse_fill_fee_fields(
    row: Mapping[str, object], *, expected_subaccount: int, expected_exchange_index: int,
    expected_ticker: str, expected_order_id: str,
) -> ObservedFillFeeFieldsV1:
    """Absent field / ambiguous direction / missing time makes the economic
    record incomplete (``SOURCE_FIELD_MALFORMED``); probe fills must match
    the exact submitted buy-YES direction, market, order and domain."""
    if not isinstance(row, Mapping):
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", "row")
    for name in _FILL_REQUIRED_SOURCE_FIELDS + ("created_time",):
        if name not in row or row[name] is None:
            raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", name)
    fill_id, trade_id, order_id = row["fill_id"], row["trade_id"], row["order_id"]
    ticker, market_ticker = row["ticker"], row["market_ticker"]
    for name, value in (("fill_id", fill_id), ("trade_id", trade_id), ("order_id", order_id), ("ticker", ticker), ("market_ticker", market_ticker)):
        if type(value) is not str or value == "":
            raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", name)
    if trade_id != fill_id:  # get_fills.md: legacy name, same as fill_id
        raise F03AnalyzerError(HaltCode.OFFICIAL_SOURCE_CONFLICT.value, "trade_id")
    if market_ticker != ticker:  # get_fills.md: legacy name, same as ticker
        raise F03AnalyzerError(HaltCode.OFFICIAL_SOURCE_CONFLICT.value, "market_ticker")
    if ticker != expected_ticker or order_id != expected_order_id:
        raise F03AnalyzerError("FILL_SCOPE_MISMATCH", "ticker/order")
    exchange_index = row["exchange_index"]
    if type(exchange_index) is not int or exchange_index != expected_exchange_index:
        raise F03AnalyzerError("FILL_SCOPE_MISMATCH", "exchange_index")
    sub = row.get("subaccount_number")
    if sub is not None and (type(sub) is not int or sub != expected_subaccount):
        raise F03AnalyzerError("FILL_SCOPE_MISMATCH", "subaccount_number")
    outcome_side, book_side = row["outcome_side"], row["book_side"]
    if outcome_side != "yes" or book_side != "bid":
        raise F03AnalyzerError("FILL_DIRECTION_MISMATCH", "outcome/book side")
    if "side" in row and row["side"] != "yes":
        raise F03AnalyzerError("FILL_DIRECTION_MISMATCH", "legacy side")
    if "action" in row and row["action"] != "buy":
        raise F03AnalyzerError("FILL_DIRECTION_MISMATCH", "legacy action")
    quantity = parse_fixed_point_count(row["count_fp"], name="count_fp")
    if quantity <= 0 or quantity > CREATE_QUANTITY:
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", "count_fp bound")
    yes_price = parse_fixed_point_dollars(row["yes_price_dollars"], name="yes_price_dollars")
    parse_fixed_point_dollars(row["no_price_dollars"], name="no_price_dollars")
    if not (Decimal(0) < yes_price < Decimal(1)):
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", "yes_price bound")
    if type(row["is_taker"]) is not bool:
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", "is_taker")
    created = row["created_time"]
    if type(created) is not str or _CANONICAL_TIMESTAMP_RE.fullmatch(created) is None:
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", "created_time")
    ts = row.get("ts")
    if ts is not None and (type(ts) is not int or ts < 0):
        raise F03AnalyzerError("SOURCE_FIELD_MALFORMED", "ts")
    api_fee = parse_fixed_point_dollars(row["fee_cost"], name="fee_cost")
    return ObservedFillFeeFieldsV1(
        fill_id=fill_id, trade_id=trade_id, order_id=order_id, ticker=ticker, market_ticker=market_ticker,
        exchange_index=exchange_index, subaccount_number=sub, outcome_side=outcome_side, book_side=book_side,
        count_lexeme=row["count_fp"], quantity=quantity, yes_price_lexeme=row["yes_price_dollars"],
        yes_price=yes_price, no_price_lexeme=row["no_price_dollars"], is_taker=row["is_taker"],
        created_time=created, ts=ts, fee_cost_lexeme=row["fee_cost"], api_fee_cost=api_fee,
    )


def merge_fill_observations(
    existing: Mapping[str, ObservedFillFeeFieldsV1], new: Iterable[ObservedFillFeeFieldsV1],
) -> dict:
    """Duplicate authoritative fills contribute once; any conflicting
    identity/quantity/price/role/fee/time halts ``FILL_DUPLICATE_CONFLICT``."""
    merged = dict(existing)
    for item in new:
        prior = merged.get(item.fill_id)
        if prior is None:
            merged[item.fill_id] = item
        elif prior.identity_tuple() != item.identity_tuple():
            raise F03AnalyzerError(HaltCode.FILL_DUPLICATE_CONFLICT.value, "fill identity conflict")
    if len([v for v in merged.values() if v.quantity > 0]) > MAX_POSITIVE_FILLS_PER_ORDER * 2:
        raise F03AnalyzerError(HaltCode.FILL_DUPLICATE_CONFLICT.value, "positive fill bound")
    return merged


# ---------------------------------------------------------------------------
# F03-BUDGET-003 -- conservative outlay bound recomputed from source constants.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OutlayBoundV1:
    max_positive_fills_per_order: int
    max_principal: Decimal
    max_trade_fee_sum: Decimal
    rounding_fee_sum_strict_upper: Decimal
    per_order_strict_upper: Decimal
    plan_strict_upper: Decimal


def conservative_outlay_bound(*, order_count: int, max_limit_price: Decimal, taker_multiplier: Decimal) -> OutlayBoundV1:
    """Per order: <=100 positive fills; six-decimal-ceiled taker trade fees
    <= k*M*q*max p(1-p) + 100 ulp; unrebatable rounding < 100 * h_nondirect;
    principal <= q*L.  Two orders at L=.8, M=1 give the spec's 3.6352."""
    if type(order_count) is not int or order_count not in (1, 2):
        raise F03AnalyzerError(HaltCode.BUDGET_EXCEEDED.value, "order_count")
    _require_decimal(max_limit_price, name="max_limit_price", positive=True)
    _require_decimal(taker_multiplier, name="taker_multiplier", positive=True)
    max_fills = int(exact_mul(CREATE_QUANTITY, Decimal(1)) / MIN_FILL_QUANTITY)
    p_star = min(max_limit_price, Decimal("0.5"))
    model_max = exact_mul(K_TAKER, taker_multiplier, CREATE_QUANTITY, p_star, exact_sub(Decimal(1), p_star))
    trade_sum = exact_add(model_max, exact_mul(Decimal(max_fills), TRADE_FEE_STEP))
    rounding_upper = exact_mul(Decimal(max_fills), QUANTUM_NON_DIRECT)
    principal = exact_mul(CREATE_QUANTITY, max_limit_price)
    per_order = exact_add(principal, trade_sum, rounding_upper)
    return OutlayBoundV1(max_fills, principal, trade_sum, rounding_upper, per_order,
                         exact_mul(Decimal(order_count), per_order))


def require_plan_within_outlay_bound(bound: OutlayBoundV1) -> None:
    if bound.plan_strict_upper > SPEC_TWO_ORDER_OUTLAY_BOUND_USD or bound.plan_strict_upper > DISPATCH_OUTLAY_CEILING_USD:
        raise F03AnalyzerError(HaltCode.BUDGET_EXCEEDED.value, "outlay bound")


# ---------------------------------------------------------------------------
# Section 10.1 / 11 -- orderbook opportunity predicate for the buy-YES probe.
# The YES ask ladder is the protected canonical reference transformation
# (``best_yes_ask = 1 - best_no_bid``, risk_control.build_orderbook_reference);
# no other complement is synthesized.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpportunityV1:
    eligible: bool
    reason: str
    executable_levels: Tuple[Tuple[Decimal, Decimal], ...]
    cumulative_quantity: Decimal
    table_price_level_present: bool


def order1_opportunity(
    no_bid_levels: Sequence[Tuple[Decimal, Decimal]], *, limit_price: Decimal, price_step: Decimal | None = None,
) -> OpportunityV1:
    """Order 1 precondition: >= 2 distinct immediately executable YES-ask
    levels through the limit, complete visible cumulative quantity in
    [0.02, 0.99] and < 1.00, so the planned 1.00 order is expected to take
    >= 2 levels and rest a remainder (not guaranteed)."""
    _require_decimal(limit_price, name="limit_price", positive=True)
    if limit_price > MAX_LIMIT_PRICE or limit_price != limit_price.quantize(Decimal("0.0001")):
        return OpportunityV1(False, "LIMIT_PRICE_INVALID", (), Decimal(0), False)
    if price_step is not None and (exact_mul(limit_price, Decimal(1)) % price_step) != 0:
        return OpportunityV1(False, "LIMIT_PRICE_NOT_ON_GRID", (), Decimal(0), False)
    levels: list[Tuple[Decimal, Decimal]] = []
    for price, quantity in no_bid_levels:
        _require_decimal(price, name="no_price")
        _require_decimal(quantity, name="quantity", positive=True)
        yes_ask = exact_sub(Decimal(1), price)
        if yes_ask <= limit_price:
            levels.append((yes_ask, quantity))
    levels.sort(key=lambda item: item[0])
    distinct_prices = {price for price, _ in levels}
    cumulative = exact_add(*(quantity for _, quantity in levels)) if levels else Decimal(0)
    table = any(price == Decimal("0.5") for price, _ in levels)
    if len(distinct_prices) < 2:
        return OpportunityV1(False, HaltCode.MARKET_NOT_DISCRIMINATING.value, tuple(levels), cumulative, table)
    if not (Decimal("0.02") <= cumulative <= Decimal("0.99")) or cumulative >= CREATE_QUANTITY:
        return OpportunityV1(False, HaltCode.MARKET_NOT_DISCRIMINATING.value, tuple(levels), cumulative, table)
    return OpportunityV1(True, "ELIGIBLE", tuple(levels), cumulative, table)


def possible_fill_paths(levels: Sequence[Tuple[Decimal, Decimal]], *, taker: bool = True, maker_multiplier: Decimal = Decimal("1")) -> Tuple[Tuple[FillModelInputV1, ...], ...]:
    """Visible-book fill paths for the planned 1.00 order: taking each level
    whole, then (when a remainder rests) an optional maker remainder fill.
    Used only for the Order-2 pre-send >= h separation check."""
    taken: list[FillModelInputV1] = []
    for price, quantity in levels:
        taken.append(FillModelInputV1(quantity, price, K_TAKER if taker else K_MAKER))
    remainder = exact_sub(CREATE_QUANTITY, exact_add(*(q for _, q in levels))) if levels else CREATE_QUANTITY
    paths = [tuple(taken)]
    if remainder > 0 and levels:
        paths.append(tuple(taken) + (FillModelInputV1(remainder, levels[-1][0], K_MAKER, maker_multiplier),))
    return tuple(paths)


def order2_reset_separable(
    paths: Sequence[Sequence[FillModelInputV1]], *, h: Decimal, carry_start: Decimal,
) -> bool:
    """Order 2 is admissible only when zero-start and carry-start aggregate
    predictions differ by >= h under EVERY admitted fill path."""
    if carry_start <= 0 or not paths:
        return False
    zero = CandidateHypothesisV1("Z", Initializer.ZERO, RebateRule.MAXIMAL, TerminalRule.NO_CREDIT, ("ZERO_INIT",))
    carry = CandidateHypothesisV1("C", Initializer.PRIOR_MODELED_RESIDUAL, RebateRule.MAXIMAL, TerminalRule.NO_CREDIT,
                                  ("PRIOR_MODELED_RESIDUAL_CARRY",), initial_accumulator=carry_start)
    for path in paths:
        a = predict_sequence(tuple(path), h=h, hypothesis=zero).predicted_total
        b = predict_sequence(tuple(path), h=h, hypothesis=carry).predicted_total
        if abs(exact_sub(a, b)) < h:
            return False
    return True


def new_lowercase_uuid4(factory: object = uuid.uuid4) -> str:
    value = factory() if callable(factory) else None
    if type(value) is not uuid.UUID or value.version != 4:
        raise F03AnalyzerError("SCHEMA_ID_INVALID", "uuid4")
    text = str(value)
    if _UUID4_RE.fullmatch(text) is None:
        raise F03AnalyzerError("SCHEMA_ID_INVALID", "uuid4")
    return text


__all__: list[str] = []
