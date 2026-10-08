"""Bounded R1-D07 F03 Kalshi Demo fee-semantics experiment runner.

Implements the runner half of
``KALSHI_DEMO_R1_D07_F03_DEMO_FEE_SEMANTICS_TEST_SPEC_01_CORRECTION_02.md``
(sections 3-6, 9-11, 13-17, 20, 23-25) as a COMPOSITION of the pinned,
unmodified canonical substrate:

* reads -- the eight frozen Active-V2 semantic operations through the
  protected ``_ActiveV2OperationAdapter`` / ``_prepare_active_v2_request`` /
  ``_active_v2_paginate_surface`` chain (complete active-domain pages, then
  LOCAL filtering), the special orderbook seam via ``issue_orderbook`` and the
  installed dedicated balance consumer ``read_f03_balance_snapshot_v1`` with
  ``evaluate_f03_balance_checkpoint_v1``;
* writer admission -- the protected Stage-3 active release chain
  (``run_pre_release_read_phase_v2`` ->
  ``_complete_stage3_active_release_and_normal_writer_v2``);
* CREATE -- the ``_gate_d_execute_create`` consumer SEQUENCE with exactly one
  pre-hash body delta (``post_only`` true -> false) and the scoped
  ``issue_strategy1_gate_d_create_permit``;
* CANCEL -- an F03-local pure active-domain T2 builder followed by the
  protected cancel assessment / intent / binding validation / generic permit /
  T1-T3 / final equality / trusted-T2 binding / adapter / classifier /
  conservation sequence of ``_gate_d_execute_cancel``.

This module owns NO physical transport, signer, credential loader, generic HTTP
client or permit constructor; it never monkeypatches or rebinds protected
globals, never calls ``_perform_get`` / ``_auth_headers`` /
``_d07_demo_signed_auth_headers``, and never constructs a
``NormalWriterPermit`` or ``_NormalWriteOperationBindingV1`` directly.  It has
no import-time activity beyond constant construction.  It does not repair the
repository-wide ``ACTIVE_DOMAIN_ORDINARY_CANCEL_ROUTE_MISMATCH`` nor the
Gate-D post-unresolved next-cycle termination finding; an unknown write is an
irreversible run halt instead.  No result here closes F03, P01-P09 or F07, and
code availability grants no Demo execution authority.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping, Sequence, Tuple

import arb.venues.kalshi.minimal_market_maker_experiment_runner as _runner
from arb.execution_ledger import LedgerError, canonical_json_bytes, canonical_timestamp, end_writer_session, sha256_hex
from arb.venues.kalshi import f03_fee_semantics_analyzer as _an
from arb.venues.kalshi.ledger_binding import active_domain_commitment
from arb.venues.kalshi.minimal_market_maker import QUOTE_QUANTITY, DesiredQuoteV1, QuoteSlot
from arb.venues.kalshi.order_lifecycle import SendOutcome, check_cancel_conservation
from arb.venues.kalshi.quote_lifecycle import (
    CREATE_ORDER_ALLOWED_FIELDS,
    QuoteLifecycleError,
    VenueBindingV2,
    active_prepared_request_domain_metadata,
    build_cancel_writer_eligibility_assessment,
    build_create_prepared_payload,
    build_mm_cancel_intent_payload,
    build_mm_create_intent_payload,
    build_mm_create_order_body,
    build_writer_eligibility_assessment,
    candidate_for_desired_quote,
    issue_and_persist_write_permit,
    reconstruct_slot_ownership,
    validate_cancel_request_binding,
)
from arb.venues.kalshi.risk_control import (
    FreshnessStampV1,
    NormalWriteAdapter,
    RiskControlError,
    build_account_aggregate_authority_expectation,
    compute_market_economic_state,
)
from arb.venues.kalshi.ledger_binding import build_account_aggregate_input

HaltCode = _an.HaltCode

TASK_ID = "R1-D07_F03_DEMO_FEE_SEMANTICS_TEST_IMPLEMENTATION_01"
REQUIRED_BASE_COMMIT = "700745828c4d823a3f963f2fff8455d00ff2d739"
REQUIRED_BASE_TREE = "b20ede8e9a17abc95284a46792824ba9b09c8f85"
REQUIRED_BASE_PARENT = "4c94077c6a80d8023d8c77fcdad4f5804de51756"
DEMO_ORIGIN = "https://external-api.demo.kalshi.co"

# Section 13 / 24 hard whole-run limits.
ACTIVE_WRITE_INTERVAL_NS = 900 * 1_000_000_000
RECONCILIATION_TAIL_NS = 120 * 1_000_000_000
GET_MAX = 200
CREATE_MAX = 2
CANCEL_MAX = 2
BALANCE_ATTEMPTS_PER_CHECKPOINT_MAX = _runner.F03_BALANCE_CHECKPOINT_READ_MAX
BALANCE_CHECKPOINTS_MAX = _runner.F03_BALANCE_CHECKPOINTS_PER_RUN_MAX
BALANCE_GETS_MAX = _runner.F03_BALANCE_READS_PER_RUN_MAX
EXACT_ORDER_POLLS_PER_ORDER_MAX = 30
FILL_POLLS_PER_ORDER_MAX = 30
POST_TERMINAL_RECONCILIATION_ROUNDS_MAX = 12
POST_TERMINAL_ROUND_SPACING_NS = 10 * 1_000_000_000
ROUTE_PAGE_CAP = 4
TOTAL_ACQUIRED_QUANTITY_MAX = _an.SPEC_TOTAL_ACQUIRED_QUANTITY_MAX
# Worst-case GET reservations used to pre-flight capacity (F03-COUNT-002).
STAGE3_ADMISSION_GET_RESERVATION = _runner.PRE_RELEASE_READ_REQUEST_MAX_V2  # 72
# One F03 campaign: orders(2)+fills(4)+positions(2) route page caps + 2 exact
# orders + market + orderbook.
DOMAIN_CAMPAIGN_GET_RESERVATION = 2 + 4 + 2 + 2 + 1 + 1
# One order lifecycle uses ONE protected Gate-D capability (64-read ceiling)
# covering truth, post-CREATE visibility/fill reconciliation and the cancel
# reads, plus its terminal campaign and one bounded balance checkpoint.
ORDER_LIFECYCLE_GET_RESERVATION = (
    _runner.GATE_D_READ_REQUEST_MAX + DOMAIN_CAMPAIGN_GET_RESERVATION + BALANCE_ATTEMPTS_PER_CHECKPOINT_MAX
)
FINAL_RECONCILIATION_GET_RESERVATION = DOMAIN_CAMPAIGN_GET_RESERVATION

assert BALANCE_ATTEMPTS_PER_CHECKPOINT_MAX == 3 and BALANCE_CHECKPOINTS_MAX == 3 and BALANCE_GETS_MAX == 9


class F03Halt(Exception):
    """Closed experiment halt; ``code`` is a ``HaltCode`` member.  A halt is
    never converted into a favorable QF03 decision."""

    def __init__(self, code: HaltCode, detail: str = "") -> None:
        if type(code) is not HaltCode:
            raise TypeError("closed halt code required")
        self.code = code
        self.detail = detail
        super().__init__(code.value if not detail else f"{code.value}: {detail}")


# ---------------------------------------------------------------------------
# Section 9 / 25 -- closed experiment state machine.
# ---------------------------------------------------------------------------


class F03State(enum.StrEnum):
    BOOT_HOLD = "BOOT_HOLD"
    SOURCE_BOUND = "SOURCE_BOUND"
    PREFLIGHT_READS = "PREFLIGHT_READS"
    B0_CHECKPOINT = "B0_CHECKPOINT"
    CURRENT_PROCESS_WRITER_ADMISSION = "CURRENT_PROCESS_WRITER_ADMISSION"
    WRITER_ELIGIBLE = "WRITER_ELIGIBLE"
    ORDER1_PREPARED = "ORDER1_PREPARED"
    ORDER1_SEND_BOUNDARY = "ORDER1_SEND_BOUNDARY"
    ORDER1_RECONCILING = "ORDER1_RECONCILING"
    ORDER1_TERMINAL = "ORDER1_TERMINAL"
    B1_CHECKPOINT = "B1_CHECKPOINT"
    ORDER2_DECISION = "ORDER2_DECISION"
    ORDER2_PREPARED = "ORDER2_PREPARED"
    ORDER2_SEND_BOUNDARY = "ORDER2_SEND_BOUNDARY"
    ORDER2_RECONCILING = "ORDER2_RECONCILING"
    ORDER2_TERMINAL = "ORDER2_TERMINAL"
    B2_CHECKPOINT = "B2_CHECKPOINT"
    FINAL_RECONCILIATION_ONLY = "FINAL_RECONCILIATION_ONLY"
    COMPLETE = "COMPLETE"
    HALTED_HELD = "HALTED_HELD"


_S = F03State
_TRANSITIONS: Mapping[F03State, frozenset] = {
    _S.BOOT_HOLD: frozenset({_S.SOURCE_BOUND}),
    _S.SOURCE_BOUND: frozenset({_S.PREFLIGHT_READS}),
    _S.PREFLIGHT_READS: frozenset({_S.B0_CHECKPOINT}),
    _S.B0_CHECKPOINT: frozenset({_S.CURRENT_PROCESS_WRITER_ADMISSION}),
    _S.CURRENT_PROCESS_WRITER_ADMISSION: frozenset({_S.WRITER_ELIGIBLE}),
    _S.WRITER_ELIGIBLE: frozenset({_S.ORDER1_PREPARED, _S.FINAL_RECONCILIATION_ONLY}),
    _S.ORDER1_PREPARED: frozenset({_S.ORDER1_SEND_BOUNDARY, _S.FINAL_RECONCILIATION_ONLY}),
    _S.ORDER1_SEND_BOUNDARY: frozenset({_S.ORDER1_RECONCILING}),
    _S.ORDER1_RECONCILING: frozenset({_S.ORDER1_TERMINAL}),
    _S.ORDER1_TERMINAL: frozenset({_S.B1_CHECKPOINT}),
    _S.B1_CHECKPOINT: frozenset({_S.ORDER2_DECISION}),
    _S.ORDER2_DECISION: frozenset({_S.ORDER2_PREPARED, _S.FINAL_RECONCILIATION_ONLY}),
    _S.ORDER2_PREPARED: frozenset({_S.ORDER2_SEND_BOUNDARY, _S.FINAL_RECONCILIATION_ONLY}),
    _S.ORDER2_SEND_BOUNDARY: frozenset({_S.ORDER2_RECONCILING}),
    _S.ORDER2_RECONCILING: frozenset({_S.ORDER2_TERMINAL}),
    _S.ORDER2_TERMINAL: frozenset({_S.B2_CHECKPOINT}),
    _S.B2_CHECKPOINT: frozenset({_S.FINAL_RECONCILIATION_ONLY}),
    _S.FINAL_RECONCILIATION_ONLY: frozenset({_S.COMPLETE}),
    _S.COMPLETE: frozenset(),
    _S.HALTED_HELD: frozenset(),
}
_WRITE_STATES = frozenset({_S.ORDER1_PREPARED, _S.ORDER1_RECONCILING, _S.ORDER2_PREPARED, _S.ORDER2_RECONCILING})


class F03StateMachineV1:
    """Only the listed normal transitions exist; any state may enter
    ``HALTED_HELD``, which is absorbing and write-prohibiting."""

    __slots__ = ("_state", "_history")

    def __init__(self) -> None:
        self._state = F03State.BOOT_HOLD
        self._history: list[str] = [F03State.BOOT_HOLD.value]

    @property
    def state(self) -> F03State:
        return self._state

    @property
    def history(self) -> Tuple[str, ...]:
        return tuple(self._history)

    def advance(self, target: F03State) -> None:
        if type(target) is not F03State:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "state type")
        if target is F03State.HALTED_HELD:
            self.halt()
            return
        if target not in _TRANSITIONS[self._state]:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, f"illegal transition {self._state.value}->{target.value}")
        self._state = target
        self._history.append(target.value)

    def halt(self) -> None:
        if self._state is not F03State.HALTED_HELD:
            self._state = F03State.HALTED_HELD
            self._history.append(F03State.HALTED_HELD.value)

    def require_write_state(self) -> None:
        if self._state not in _WRITE_STATES:
            raise F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "write not permitted in " + self._state.value)


# ---------------------------------------------------------------------------
# Sections 13 / 24 -- whole-run counters and the request ledger.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class F03BudgetLedgerV1:
    """Observational whole-run accounting plus pre-transport refusal.  Charges
    are never refunded; physical-send counters are separate from durable T3
    write charges."""

    get_count: int = 0
    create_t3: int = 0
    cancel_t3: int = 0
    create_transport_invocations: int = 0
    cancel_transport_invocations: int = 0
    balance_gets: int = 0
    balance_checkpoints: int = 0
    acquired_quantity: Decimal = Decimal("0")
    redirects: int = 0
    automatic_retries: int = 0
    exact_order_polls: dict = field(default_factory=dict)
    fill_polls: dict = field(default_factory=dict)
    reconciliation_rounds: int = 0
    last_round_ns: int | None = None
    request_log: list = field(default_factory=list)

    def remaining_gets(self) -> int:
        return GET_MAX - self.get_count

    def require_get_capacity(self, needed: int, *, purpose: str) -> None:
        if type(needed) is not int or needed < 0 or self.get_count + needed > GET_MAX:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "GET capacity for " + purpose)

    def charge_get(self, operation: str, *, phase: str) -> int:
        if self.get_count >= GET_MAX:
            self.request_log.append({"ordinal": None, "operation": operation, "phase": phase, "state": "REFUSED_BEFORE_TRANSPORT"})
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "GET<=200")
        self.get_count += 1
        self.request_log.append({"ordinal": self.get_count, "operation": operation, "phase": phase, "state": "CHARGED_AT_TRANSPORT_BOUNDARY"})
        return self.get_count

    def charge_unobserved_protected_gets(self, count: int, *, phase: str) -> None:
        """Conservative charge for protected-capability-accounted reads that
        did not cross this run's observed transport boundary (e.g. a synthetic
        acquisition seam).  Exceeding the ceiling halts."""
        if type(count) is not int or count < 0:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "protected read count")
        if self.get_count + count > GET_MAX:
            self.get_count = GET_MAX
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "protected reads exceed GET<=200")
        self.get_count += count
        if count:
            self.request_log.append({"ordinal": self.get_count, "operation": "PROTECTED_ACCOUNTED_READS", "phase": phase, "count": count, "state": "CHARGED_FROM_PROTECTED_COUNTER"})

    def charge_create_t3(self) -> None:
        if self.create_t3 >= CREATE_MAX:
            raise F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "CREATE<=2")
        self.create_t3 += 1

    def charge_cancel_t3(self) -> None:
        if self.cancel_t3 >= CANCEL_MAX:
            raise F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "CANCEL<=2")
        self.cancel_t3 += 1

    def require_create_slot(self) -> None:
        if self.create_t3 >= CREATE_MAX:
            raise F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "CREATE<=2")

    def require_cancel_slot(self) -> None:
        if self.cancel_t3 >= CANCEL_MAX:
            raise F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "CANCEL<=2")

    def poll(self, kind: str, order_key: str) -> None:
        table = self.exact_order_polls if kind == "ORDER" else self.fill_polls
        limit = EXACT_ORDER_POLLS_PER_ORDER_MAX if kind == "ORDER" else FILL_POLLS_PER_ORDER_MAX
        if table.get(order_key, 0) >= limit:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, kind + " polls<=30")
        table[order_key] = table.get(order_key, 0) + 1

    def reconciliation_round(self, now_ns: int) -> None:
        if self.reconciliation_rounds >= POST_TERMINAL_RECONCILIATION_ROUNDS_MAX:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "reconciliation rounds<=12")
        if self.last_round_ns is not None and now_ns - self.last_round_ns < POST_TERMINAL_ROUND_SPACING_NS:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "reconciliation round spacing>=10s")
        self.reconciliation_rounds += 1
        self.last_round_ns = now_ns

    def add_acquired(self, quantity: Decimal) -> None:
        total = _an.exact_add(self.acquired_quantity, quantity)
        if total > TOTAL_ACQUIRED_QUANTITY_MAX:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "acquired quantity<=2.00")
        self.acquired_quantity = total

    def counters_projection(self, *, worst_case_bound: Decimal) -> dict:
        return {
            "get": self.get_count, "create": self.create_t3, "cancel": self.cancel_t3,
            "redirects": self.redirects, "automatic_retries": self.automatic_retries,
            "acquired_quantity": _an.canonical_decimal_text(self.acquired_quantity),
            "worst_case_outlay_bound": _an.canonical_decimal_text(worst_case_bound),
        }


# ---------------------------------------------------------------------------
# F03-COUNT-001 -- observational guards at the EXISTING consumption boundary.
# They delegate to the inherited transport / special orderbook seam unchanged;
# they only charge (and refuse at the ceiling) immediately before it.
# ---------------------------------------------------------------------------


class _F03CountedReadTransportV1:
    __slots__ = ("_inner", "_ledger", "_phase")

    def __init__(self, inner: Callable[..., object], ledger: F03BudgetLedgerV1) -> None:
        if not callable(inner):
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "read transport")
        self._inner = inner
        self._ledger = ledger
        self._phase = "UNSET"

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def __call__(self, operation, prepared, deadline):
        if operation in _runner.WRITE_OPERATIONS:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "write operation on read transport")
        self._ledger.charge_get(getattr(operation, "value", str(operation)), phase=self._phase)
        return self._inner(operation, prepared, deadline)


class _F03CountedOrderbookSeamV1(_runner._ActiveV2OrderbookSeam):
    """The special orderbook seam, unchanged: ``prepare`` is delegated with no
    charge; ``execute`` charges one GET then delegates (never the generic
    signed reader)."""

    __slots__ = ("_inner", "_ledger", "_transport")

    def __init__(self, inner: object, ledger: F03BudgetLedgerV1, transport: _F03CountedReadTransportV1) -> None:
        if not isinstance(inner, _runner._ActiveV2OrderbookSeam):
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "orderbook seam")
        self._inner = inner
        self._ledger = ledger
        self._transport = transport

    def prepare(self, ticker):
        return self._inner.prepare(ticker)

    def execute(self, plan, deadline):
        self._ledger.charge_get("GET_MARKET_ORDERBOOK", phase=self._transport._phase)
        return self._inner.execute(plan, deadline)


def build_f03_runtime_v1(
    runtime: "_runner.ExperimentRunnerRuntimeV2", ledger: F03BudgetLedgerV1, *, active_end_monotonic_ns: int,
) -> Tuple["_runner.ExperimentRunnerRuntimeV2", _F03CountedReadTransportV1]:
    """Compose the run runtime: the inherited read transport and orderbook
    seam wrapped by the observational guards, and the fixed active-phase cap
    as ``experiment_absolute_end_monotonic_ns`` (never later than the
    supplied runtime's own end).  Re-validated by the protected
    ``ExperimentRunnerRuntimeV2.__post_init__``."""
    if type(runtime) is not _runner.ExperimentRunnerRuntimeV2:
        raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "runtime type")
    guard = _F03CountedReadTransportV1(runtime.send_operation_request, ledger)
    seam = _F03CountedOrderbookSeamV1(runtime.fetch_orderbook, ledger, guard)
    end = min(int(active_end_monotonic_ns), runtime.experiment_absolute_end_monotonic_ns)
    rt = dataclasses.replace(runtime, send_operation_request=guard, fetch_orderbook=seam,
                             experiment_absolute_end_monotonic_ns=end)
    return rt, guard


def with_phase_end(runtime: "_runner.ExperimentRunnerRuntimeV2", end_ns: int) -> "_runner.ExperimentRunnerRuntimeV2":
    """Fixed phase cap (F03-COUNT-004): the cap only ever moves earlier."""
    return dataclasses.replace(runtime, experiment_absolute_end_monotonic_ns=min(end_ns, runtime.experiment_absolute_end_monotonic_ns))


# ---------------------------------------------------------------------------
# Section 6 / 25 -- explicit nonsecret execution inputs and source binding.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class F03RunPlanV1:
    run_id: str
    ticker: str
    event_ticker: str
    series_ticker: str
    account_class: str
    account_class_evidence_id: str
    fee_epoch_id: str
    fee_type: str
    taker_multiplier: Decimal
    maker_multiplier: Decimal
    fee_regime_change_pending: bool
    order1_limit_price: Decimal
    order2_limit_price: Decimal | None
    expected_commit: str
    expected_tree: str
    expected_parent: str
    implementation_artifacts: Mapping[str, str]
    terminal_credit_exclusion_evidence_id: str | None = None
    private_evidence_permission: bool = False

    def __post_init__(self) -> None:
        try:
            if _an._UUID4_RE.fullmatch(self.run_id) is None:
                raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, "run_id")
        except TypeError:
            raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, "run_id") from None
        for name in ("ticker", "event_ticker", "series_ticker", "fee_epoch_id", "account_class_evidence_id"):
            value = getattr(self, name)
            if type(value) is not str or not value:
                raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, name)
        if _runner._TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, "ticker grammar")
        if self.account_class not in tuple(_an.AccountClass):
            raise F03Halt(HaltCode.ACCOUNT_CLASS_UNRESOLVED, "account class")
        if self.fee_type != "quadratic":
            raise F03Halt(HaltCode.FEE_REGIME_UNRESOLVED, "fee type")
        if type(self.taker_multiplier) is not Decimal or self.taker_multiplier != Decimal("1"):
            raise F03Halt(HaltCode.FEE_REGIME_UNRESOLVED, "taker multiplier must be exactly 1")
        if type(self.maker_multiplier) is not Decimal or not (Decimal("0") < self.maker_multiplier <= Decimal("1")):
            raise F03Halt(HaltCode.FEE_REGIME_UNRESOLVED, "maker multiplier")
        if self.fee_regime_change_pending is not False:
            raise F03Halt(HaltCode.FEE_REGIME_UNRESOLVED, "pending fee-rule change")
        for price in (self.order1_limit_price, self.order2_limit_price):
            if price is None and price is self.order2_limit_price:
                continue
            if (type(price) is not Decimal or not price.is_finite() or not (Decimal("0") < price <= _an.MAX_LIMIT_PRICE)
                    or price.as_tuple().exponent != -4):
                raise F03Halt(HaltCode.BUDGET_EXCEEDED, "limit price must be exact 4dp in (0, .8000]")
        for name in ("expected_commit", "expected_tree", "expected_parent"):
            value = getattr(self, name)
            if type(value) is not str or len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
                raise F03Halt(HaltCode.CANONICAL_BASE_MISMATCH, name)
        if not isinstance(self.implementation_artifacts, Mapping) or not self.implementation_artifacts:
            raise F03Halt(HaltCode.CANONICAL_BASE_MISMATCH, "implementation artifacts")
        for path, digest in self.implementation_artifacts.items():
            if type(path) is not str or type(digest) is not str or _an._HEX64_RE.fullmatch(digest) is None:
                raise F03Halt(HaltCode.CANONICAL_BASE_MISMATCH, "implementation artifact identity")
        if type(self.private_evidence_permission) is not bool:
            raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, "private evidence permission")

    @property
    def quantum(self) -> Decimal | None:
        if self.account_class == _an.AccountClass.UNRESOLVED:
            return None
        return _an.quantum_for_account_class(self.account_class)

    @property
    def planned_order_count(self) -> int:
        return 1 if self.order2_limit_price is None else 2


@dataclass(frozen=True, slots=True)
class F03ObservedIdentityV1:
    """Nonsecret observed runtime identity supplied by the separately
    reviewed operator package (F03-PRE-001)."""

    commit: str
    tree: str
    parent: str
    implementation_artifacts: Mapping[str, str]


def verify_source_binding(plan: F03RunPlanV1, observed: F03ObservedIdentityV1) -> None:
    """F03-PRE-001 / F03-SRC-001..003: exact identity equality and exact
    controlling source constants; any mismatch halts before any read."""
    if type(observed) is not F03ObservedIdentityV1:
        raise F03Halt(HaltCode.CANONICAL_BASE_MISMATCH, "observed identity")
    if (observed.commit, observed.tree, observed.parent) != (plan.expected_commit, plan.expected_tree, plan.expected_parent):
        raise F03Halt(HaltCode.CANONICAL_BASE_MISMATCH, "commit/tree/parent")
    if dict(observed.implementation_artifacts) != dict(plan.implementation_artifacts):
        raise F03Halt(HaltCode.CANONICAL_BASE_MISMATCH, "implementation artifacts")
    if (
        _runner.F03_BALANCE_SOURCE_RAW_SHA256 != _an.SOURCE_IDENTITIES["KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml"][1]
        or _runner.F03_BALANCE_SOURCE_RAW_BYTES != _an.SOURCE_IDENTITIES["KALSHI_CURRENT_OPENAPI_SOURCE_RESOLUTION_01.yaml"][0]
        or _runner.DEMO_ORIGIN != DEMO_ORIGIN
    ):
        raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, "balance source binding")


def verify_domain_and_origin(runtime: "_runner.ExperimentRunnerRuntimeV2") -> None:
    """F03-PRE-002/003 -- Demo exactly; explicit numbered subaccount; the
    historical primary subaccount 0 is prohibited for this experiment."""
    b = runtime.domain_binding
    if _runner.DEMO_ORIGIN != DEMO_ORIGIN or _runner.DEMO_HOST != "external-api.demo.kalshi.co":
        raise F03Halt(HaltCode.DEMO_ORIGIN_MISMATCH, "origin")
    if b.environment != "KALSHI_DEMO" or runtime.active_contract.environment != "KALSHI_DEMO":
        raise F03Halt(HaltCode.PRODUCTION_ORIGIN_PRESENT, "environment")
    if type(b.subaccount) is not int or b.subaccount == 0:
        raise F03Halt(HaltCode.HISTORICAL_PRIMARY_DOMAIN_PROHIBITED, "subaccount 0")
    if (
        type(runtime.strategy_instance_id) is not str or not runtime.strategy_instance_id
        or type(runtime.gate_d_capability_reference_id) is not str or not runtime.gate_d_capability_reference_id
        or not callable(runtime.normal_write_transport)
        or type(runtime.risk_config) is not _runner.RiskLimitConfigV1
    ):
        raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "runtime gate-d bindings")


# ---------------------------------------------------------------------------
# Section 4.1 -- F03 observation campaigns over the frozen Active-V2 chain.
# Each campaign uses one protected trusted capability (never minting a
# read-set) and is marked consumed at its end.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class F03DomainSnapshotV1:
    """Complete active-domain pages (orders/fills/positions) for the active
    (subaccount, exchange_index) domain; rows retained raw after protected
    page/scope/economic validation, then filtered LOCALLY."""

    order_rows: Tuple[Mapping[str, object], ...]
    fill_rows: Tuple[Mapping[str, object], ...]
    position_rows: Tuple[Mapping[str, object], ...]
    page_commitments: Tuple[str, ...]
    complete: bool


class F03ObservationCampaignV1:
    __slots__ = ("_runtime", "_ledger", "_guard", "_capability", "_adapter", "_ordinal", "_phase")

    def __init__(self, runtime, ledger: F03BudgetLedgerV1, guard: _F03CountedReadTransportV1, *, phase: str, reserve: int) -> None:
        ledger.require_get_capacity(reserve, purpose=phase)
        self._runtime = runtime
        self._ledger = ledger
        self._guard = guard
        self._phase = phase
        guard.set_phase(phase)
        self._capability = _runner._issue_trusted_dynamic_pre_release_read_capability_v2(
            runtime, runtime.experiment_absolute_end_monotonic_ns,
        )
        self._adapter = _runner._ActiveV2OperationAdapter(
            runtime, absolute_invocation_deadline_ns=runtime.experiment_absolute_end_monotonic_ns,
        )
        self._ordinal = [0]

    def close(self) -> None:
        self._capability.mark_consumed()

    def __enter__(self) -> "F03ObservationCampaignV1":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _next(self) -> int:
        self._ordinal[0] += 1
        return self._ordinal[0]

    def market(self, ticker: str) -> Mapping[str, object]:
        parsed, _raw, deadline = self._adapter.issue_json(
            self._capability, _runner.ActivePreReleaseReadOperationV2.GET_MARKET, ordinal=self._next(),
            subaccount=self._runtime.domain_binding.subaccount, ticker=ticker,
        )
        market = parsed.get("market") if type(parsed) is dict else None
        if type(market) is not dict or market.get("ticker") != ticker:
            raise F03Halt(HaltCode.SOURCE_SCOPE_CONFLICT, "market identity")
        _runner.check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=_runner.DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return market

    def orderbook(self, ticker: str):
        snapshot, deadline = self._adapter.issue_orderbook(self._capability, ordinal=self._next(), ticker=ticker)
        _runner.check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=_runner.DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return snapshot

    def exact_order(self, order_id: str) -> Mapping[str, object]:
        parsed, _raw, deadline = self._adapter.issue_json(
            self._capability, _runner.ActivePreReleaseReadOperationV2.GET_ORDER, ordinal=self._next(),
            subaccount=self._runtime.domain_binding.subaccount, order_id=order_id,
        )
        row = parsed.get("order") if type(parsed) is dict else None
        if type(row) is not dict or row.get("order_id") != order_id:
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "exact order row")
        b = self._runtime.domain_binding
        _runner._active_v2_scope_guard(row, subaccount=b.subaccount, exchange_index=b.exchange_index)
        _runner.check_deadline(deadline, self._runtime.monotonic_clock_ns(), checkpoint=_runner.DeadlineCheckpoint.AFTER_RESULT_CONSTRUCTION)
        return row

    def domain(self, *, selected_ticker: str) -> F03DomainSnapshotV1:
        """Complete domain pagination (route page caps, terminal cursor) with
        NO ticker/order/status/time filter; a nonempty cursor at the cap is
        ``PAGINATION_LIMIT_EXHAUSTED`` and nothing local is complete."""
        b = self._runtime.domain_binding
        out: dict = {}
        commitments: list[str] = []
        for operation in (_runner.ActivePreReleaseReadOperationV2.GET_ORDERS,
                          _runner.ActivePreReleaseReadOperationV2.GET_FILLS,
                          _runner.ActivePreReleaseReadOperationV2.GET_POSITIONS):
            try:
                surface, rows = _runner._active_v2_paginate_surface(
                    self._adapter, self._capability, operation, ordinal_box=self._ordinal,
                    subaccount=b.subaccount, exchange_index=b.exchange_index, selected_ticker=selected_ticker,
                )
            except _runner.RunnerError as exc:
                if exc.code is _runner.RunnerFailureCode.DYNAMIC_READ_PAGINATION_INCOMPLETE:
                    raise F03Halt(HaltCode.PAGINATION_LIMIT_EXHAUSTED, operation.value) from None
                if exc.code is _runner.RunnerFailureCode.DYNAMIC_READ_CURSOR_CYCLE:
                    raise F03Halt(HaltCode.FILL_PAGINATION_INCOMPLETE, operation.value) from None
                raise
            out[operation] = rows
            commitments.extend(p.canonical_content_digest_sha256 for p in surface.pages)
        return F03DomainSnapshotV1(
            order_rows=tuple(out[_runner.ActivePreReleaseReadOperationV2.GET_ORDERS]),
            fill_rows=tuple(out[_runner.ActivePreReleaseReadOperationV2.GET_FILLS]),
            position_rows=tuple(out[_runner.ActivePreReleaseReadOperationV2.GET_POSITIONS]),
            page_commitments=tuple(commitments), complete=True,
        )


def _position_nonzero(row: Mapping[str, object]) -> bool:
    try:
        return _runner._position_count_from_row(row) != 0
    except _runner.RunnerError:
        return True  # unknown is never zero


def assess_baseline_isolation(snapshot: F03DomainSnapshotV1, *, ticker: str, known_test_order_ids: Sequence[str] = ()) -> None:
    """F03-PRE-006 / F03-ISO-001: no working order anywhere in the measured
    domain, no position that could settle during the measurement, complete
    pages.  Any violation halts before writer admission / CREATE."""
    if not snapshot.complete:
        raise F03Halt(HaltCode.BASELINE_UNKNOWN_EXPOSURE, "incomplete domain")
    for row in snapshot.order_rows:
        if row.get("status") == "resting" and row.get("order_id") not in known_test_order_ids:
            raise F03Halt(HaltCode.BASELINE_OPEN_ORDER_CONFLICT, "working order in measured domain")
    for row in snapshot.position_rows:
        if _position_nonzero(row):
            raise F03Halt(HaltCode.UNRELATED_ACTIVITY_PRESENT, "pre-existing position may settle during measurement")
    del ticker


# ---------------------------------------------------------------------------
# F03-PRE-004 / F03-ISO-001 -- current market metadata gate (no prefix
# inference; no series/fee API; explicit inputs verified where exposed).
# ---------------------------------------------------------------------------


def _parse_utc(value: object) -> datetime | None:
    if type(value) is not str:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def verify_market_metadata(
    market: Mapping[str, object], *, plan: F03RunPlanV1, active_end_utc: datetime, limit_prices: Sequence[Decimal],
) -> None:
    if market.get("ticker") != plan.ticker:
        raise F03Halt(HaltCode.SOURCE_SCOPE_CONFLICT, "ticker")
    if market.get("event_ticker") != plan.event_ticker:
        raise F03Halt(HaltCode.SOURCE_SCOPE_CONFLICT, "event relation")
    if "series_ticker" in market and market.get("series_ticker") != plan.series_ticker:
        raise F03Halt(HaltCode.SOURCE_SCOPE_CONFLICT, "series relation")
    if market.get("status") not in ("active", "open"):
        raise F03Halt(HaltCode.MARKET_NOT_DISCRIMINATING, "market not open/tradable")
    for key, expected in (("fee_type", plan.fee_type),):
        if key in market and market.get(key) != expected:
            raise F03Halt(HaltCode.OFFICIAL_SOURCE_CONFLICT, key)
    if "fee_multiplier" in market:
        try:
            observed = Decimal(str(market.get("fee_multiplier")))
        except InvalidOperation:
            raise F03Halt(HaltCode.OFFICIAL_SOURCE_CONFLICT, "fee_multiplier") from None
        if observed != plan.taker_multiplier:
            raise F03Halt(HaltCode.OFFICIAL_SOURCE_CONFLICT, "fee_multiplier")
    close = _parse_utc(market.get("close_time"))
    if close is None or (close - active_end_utc).total_seconds() <= 120:
        raise F03Halt(HaltCode.MARKET_NOT_DISCRIMINATING, "close/settlement not later than active_end+120s")
    try:
        ranges = _runner._parse_price_ranges(market.get("price_ranges"))
    except _runner.RunnerError:
        raise F03Halt(HaltCode.MARKET_NOT_DISCRIMINATING, "price grid") from None
    for price in limit_prices:
        if not any(r.start <= price <= r.end and (price - r.start) % r.step == 0 for r in ranges):
            raise F03Halt(HaltCode.MARKET_NOT_DISCRIMINATING, "limit price not on grid")


# ---------------------------------------------------------------------------
# F03-BAL-002..004 -- bounded balance checkpoints over the installed reader.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class F03CheckpointRecordV1:
    boundary: str
    state: str
    attempts: int
    successes: int
    consumed_balance_gets: int
    failed_reads: int
    failure_codes: Tuple[str, ...]
    observation_evidence: Tuple[Mapping[str, object], ...]
    final_updated_ts: int | None
    stale_by_fill_watermark: bool
    evaluator_called: bool
    halt_code: str | None
    # Process-local exact stable balance (never exported to shared evidence).
    _private_stable_balance: Decimal | None = field(default=None, repr=False, compare=False)

    def shared_projection(self) -> dict:
        return {
            "schema": "BalanceCheckpointV1", "boundary": self.boundary, "state": self.state,
            "attempts": self.attempts, "successes": self.successes, "consumed_balance_gets": self.consumed_balance_gets,
            "failed_reads": self.failed_reads, "failure_codes": list(self.failure_codes),
            "snapshot_evidence": [dict(e) for e in self.observation_evidence],
            "final_updated_ts": self.final_updated_ts, "stale_by_fill_watermark": self.stale_by_fill_watermark,
            "evaluator_called": self.evaluator_called, "halt_code": self.halt_code,
        }


class F03BalanceCheckpointerV1:
    """Request ordinals strictly increase for the whole run; checkpoint and
    whole-run GET slots are reserved before the reader; failures consume an
    attempt and are never refunded or retried."""

    __slots__ = ("_ledger", "_ordinal", "_attempts_used")

    def __init__(self, ledger: F03BudgetLedgerV1) -> None:
        self._ledger = ledger
        self._ordinal = 0
        self._attempts_used: dict[str, int] = {}

    def run(self, runtime, *, boundary: str, latest_fill_execution_utc: datetime | None = None,
            reader: Callable[..., object] | None = None) -> F03CheckpointRecordV1:
        read = reader if reader is not None else _runner.read_f03_balance_snapshot_v1
        if boundary not in _runner.F03_BALANCE_CHECKPOINT_BOUNDARIES or boundary in self._attempts_used:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "checkpoint boundary")
        if self._ledger.balance_checkpoints >= BALANCE_CHECKPOINTS_MAX:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "checkpoints<=3")
        self._ledger.balance_checkpoints += 1
        self._attempts_used[boundary] = 0
        snapshots: list = []
        failures: list[str] = []
        consumed = 0
        failed = 0

        def _attempt() -> bool:
            nonlocal consumed, failed
            if self._attempts_used[boundary] >= BALANCE_ATTEMPTS_PER_CHECKPOINT_MAX:
                raise F03Halt(HaltCode.BUDGET_EXCEEDED, "attempts/checkpoint<=3")
            if self._ledger.balance_gets >= BALANCE_GETS_MAX:
                raise F03Halt(HaltCode.BUDGET_EXCEEDED, "balance GET<=9")
            self._ledger.require_get_capacity(1, purpose="balance " + boundary)
            self._attempts_used[boundary] += 1
            self._ordinal += 1
            try:
                snapshot = read(runtime, request_ordinal=self._ordinal)
            except _runner.RunnerError as exc:
                count = getattr(exc, "_arb_f03_balance_request_count", 1)
                count = count if count in (0, 1) else 1
                consumed += count
                self._ledger.balance_gets += count
                failed += 1
                failures.append(exc.code.value)
                return False
            except F03Halt:
                raise
            except Exception:
                # Unexpected uncategorized exception after entry: conservatively
                # one consumed request, FAILED; detail never exposed.
                consumed += 1
                self._ledger.balance_gets += 1
                failed += 1
                failures.append("UNCLASSIFIED_EXCEPTION")
                return False
            consumed += 1
            self._ledger.balance_gets += 1
            snapshots.append(snapshot)
            return True

        def _record(state: str, *, evaluator_called: bool, checkpoint=None, halt: str | None = None) -> F03CheckpointRecordV1:
            evidence = tuple(_runner.project_f03_balance_snapshot_evidence_v1(s).canonical_object() for s in snapshots)
            private = None
            if checkpoint is not None and checkpoint.state == "STABLE":
                private = Decimal(checkpoint.stable_balance_canonical_text)
            return F03CheckpointRecordV1(
                boundary=boundary, state=state, attempts=self._attempts_used[boundary], successes=len(snapshots),
                consumed_balance_gets=consumed, failed_reads=failed, failure_codes=tuple(failures),
                observation_evidence=evidence,
                final_updated_ts=(checkpoint.final_updated_ts if checkpoint is not None else (snapshots[-1].updated_ts if snapshots else None)),
                stale_by_fill_watermark=bool(checkpoint.stale_by_fill_watermark) if checkpoint is not None else False,
                evaluator_called=evaluator_called, halt_code=halt, _private_stable_balance=private,
            )

        for _ in range(2):
            try:
                ok = _attempt()
            except F03Halt as exc:
                if not snapshots or exc.code is not HaltCode.BUDGET_EXCEEDED:
                    raise
                # One successful observation can never be STABLE.
                evaluated = self._evaluate(snapshots, boundary, failed, latest_fill_execution_utc)
                return _record(checkpoint_state(len(snapshots), failed, evaluated), evaluator_called=True,
                               halt=HaltCode.BUDGET_EXCEEDED.value)
            if not ok:
                break
        if failed:
            evaluated = None
            called = False
            if snapshots:
                evaluated = self._evaluate(snapshots, boundary, failed, latest_fill_execution_utc)
                called = True
            return _record(_an.CheckpointState.FAILED.value, evaluator_called=called, checkpoint=None if evaluated is None or isinstance(evaluated, str) else evaluated,
                           halt=HaltCode.BALANCE_CHECKPOINT_FAILED.value)
        evaluated = self._evaluate(snapshots, boundary, 0, latest_fill_execution_utc)
        if isinstance(evaluated, str):
            return _record(_an.CheckpointState.NOT_STABLE.value, evaluator_called=True, halt=evaluated)
        if evaluated.state == "STABLE":
            return _record(_an.CheckpointState.STABLE.value, evaluator_called=True, checkpoint=evaluated)
        unequal = snapshots[-1].balance_decimal != snapshots[-2].balance_decimal
        if unequal and not evaluated.stale_by_fill_watermark:
            # Only a successful but unequal pair may obtain the third observation.
            if not _attempt():
                return _record(_an.CheckpointState.FAILED.value, evaluator_called=True, halt=HaltCode.BALANCE_CHECKPOINT_FAILED.value)
            evaluated = self._evaluate(snapshots, boundary, 0, latest_fill_execution_utc)
            if isinstance(evaluated, str):
                return _record(_an.CheckpointState.NOT_STABLE.value, evaluator_called=True, halt=evaluated)
            if evaluated.state == "STABLE":
                return _record(_an.CheckpointState.STABLE.value, evaluator_called=True, checkpoint=evaluated)
        return _record(_an.CheckpointState.NOT_STABLE.value, evaluator_called=True, checkpoint=evaluated,
                       halt=HaltCode.BALANCE_CHECKPOINT_NOT_STABLE.value)

    @staticmethod
    def _evaluate(snapshots, boundary, failed, latest_fill_execution_utc):
        try:
            return _runner.evaluate_f03_balance_checkpoint_v1(
                tuple(snapshots), boundary=boundary, failed_read_count=failed,
                latest_fill_execution_utc=latest_fill_execution_utc,
            )
        except _runner.RunnerError as exc:
            if exc.code is _runner.RunnerFailureCode.F03_BALANCE_TIMESTAMP_REGRESSION:
                return HaltCode.BALANCE_TIMESTAMP_REGRESSION.value
            return HaltCode.BALANCE_CHECKPOINT_NOT_STABLE.value


def checkpoint_state(successes: int, failed_reads: int, evaluated: object) -> str:
    """F03-BAL-002 state rule: any failed read -> FAILED (never reset); zero
    successes -> FAILED (the nonempty-only evaluator is not called); one
    success -> NOT_STABLE; otherwise the unchanged installed evaluator's
    verdict (a regression/rejection string -> NOT_STABLE)."""
    if failed_reads > 0 or successes == 0:
        return _an.CheckpointState.FAILED.value
    if successes == 1 or isinstance(evaluated, str) or evaluated is None:
        return _an.CheckpointState.NOT_STABLE.value
    return _an.CheckpointState.STABLE.value if evaluated.state == "STABLE" else _an.CheckpointState.NOT_STABLE.value


def checkpoint_zero_success_record(boundary: str) -> F03CheckpointRecordV1:
    """Zero successful observations: FAILED, no value, evaluator NOT called."""
    return F03CheckpointRecordV1(boundary, _an.CheckpointState.FAILED.value, 0, 0, 0, 0, (), (), None, False, False,
                                 HaltCode.BALANCE_CHECKPOINT_FAILED.value)


# ---------------------------------------------------------------------------
# Section 5.1 -- non-post-only CREATE composition (D01 repair).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class F03WriteOutcomeV1:
    action: str  # CREATE | CANCEL
    request_id: str
    client_order_id: str
    venue_order_id: str | None
    assessment_eligible: bool
    t3_charged: bool
    transport_invoked: bool
    classification: str
    detail: str | None
    prepared_request_sha256: str
    intent_event_id: str | None
    prepared_event_id: str | None
    send_boundary_event_id: str | None
    send_started_monotonic_ns: int | None = None
    send_completed_monotonic_ns: int | None = None
    send_started_utc: str | None = None
    send_completed_utc: str | None = None


def build_non_post_only_create_body(
    *, ticker: str, client_order_id: str, yes_price: Decimal, expiration_time: int, venue_binding: VenueBindingV2,
) -> Tuple[dict, dict]:
    """Steps 1-6 of F03-D01-CREATE-001: protected builder output, copied,
    exact key set, only ``post_only`` true -> false.  Returns (protected,
    copied) so the delta is provable."""
    protected = build_mm_create_order_body(
        ticker=ticker, client_order_id=client_order_id, venue_side="bid", yes_price=yes_price,
        quantity=QUOTE_QUANTITY, expiration_time=expiration_time, venue_binding=venue_binding,
    )
    copied = dict(protected)
    if set(copied) != set(CREATE_ORDER_ALLOWED_FIELDS):
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "create key set")
    if copied.get("post_only") is not True:
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "protected post_only must be exact true")
    if copied["price"] != str(yes_price) or copied["count"] != "1.00":
        raise F03Halt(HaltCode.BUDGET_EXCEEDED, "silent rounding of price/count")
    copied["post_only"] = False
    for key in CREATE_ORDER_ALLOWED_FIELDS:
        if key == "post_only":
            continue
        if copied[key] != protected[key] or type(copied[key]) is not type(protected[key]):
            raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "non-post_only field differs")
    return protected, copied


def _freshness_identities(runtime, truth) -> Tuple[str, str, str, str, int, str]:
    reconciliation_snapshot_sha256 = sha256_hex(canonical_json_bytes(_runner._gate_d_reconciliation_snapshot_object(truth)))
    market_data_snapshot_sha256 = sha256_hex(canonical_json_bytes(_runner._market_data_snapshot(truth.market, truth.orderbook)))
    now_ns = runtime.monotonic_clock_ns()
    now_utc = canonical_timestamp(runtime.wall_clock())
    pid = runtime.normal_gate.process_instance_id
    market_fresh = _runner.compute_mm_freshness_identity_sha256(
        FreshnessStampV1(pid, now_utc, now_ns, "NONE", None, market_data_snapshot_sha256))
    recon_fresh = _runner.compute_mm_freshness_identity_sha256(
        FreshnessStampV1(pid, now_utc, now_ns, "NONE", None, reconciliation_snapshot_sha256))
    return (reconciliation_snapshot_sha256, market_data_snapshot_sha256, market_fresh, recon_fresh, now_ns, now_utc)


def execute_f03_create(
    *, locked, session_id: str, capability, adapter: NormalWriteAdapter, runtime, ticker: str,
    projection, truth, yes_price: Decimal, active_trusted_read_set_id: str, plan_sha256: str,
    ledger: F03BudgetLedgerV1, uuid_factory: Callable[[], uuid.UUID] | None = None,
) -> F03WriteOutcomeV1:
    """Reproduces the ``_gate_d_execute_create`` consumer sequence with only
    the bounded body delta: assessment -> scoped permit -> T1/T2/T3 -> charge
    at durable T3 -> freshness -> final active-domain equality -> trusted-T2
    binding -> the one adapter call -> protected classifier -> bounded
    authoritative post-CREATE reconciliation."""
    ledger.require_create_slot()
    if type(runtime) is not _runner.ExperimentRunnerRuntimeV2:
        raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "runtime type")
    make_uuid = uuid_factory or runtime.uuid_factory
    reconstruction = reconstruct_slot_ownership(
        locked.events, strategy_instance_id=runtime.strategy_instance_id, market_ticker=ticker,
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    if reconstruction.classification not in ("ABSENT", "TERMINAL_RECONCILED") or reconstruction.working_order is not None:
        raise F03Halt(HaltCode.ACTIVE_ORDER_LIMIT_VIOLATION, "slot not free")
    client_order_id = str(uuid.UUID(hex=make_uuid().hex, version=4))
    if not _an._UUID4_RE.fullmatch(client_order_id):
        raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, "client order id")
    request_id = f"req_{runtime.uuid_factory().hex}"
    execution_attempt_id = f"ea_{runtime.uuid_factory().hex}"
    quote_generation_id = f"qg_{runtime.uuid_factory().hex}"
    recon_sha, market_sha, market_fresh, recon_fresh, now_ns, _now_utc = _freshness_identities(runtime, truth)
    unresolved = _runner._gate_d_unresolved_exposure_usd(projection, truth)
    freshness_deadline = now_ns + _runner.OPERATION_DEADLINE_MS * 1_000_000
    write_deadline = _runner._gate_d_write_operation_deadline(
        runtime=runtime, request_id=request_id, operation_name="CREATE_ORDER_V2",
        started_monotonic_ns=now_ns, freshness_deadline_monotonic_ns=freshness_deadline,
    )
    _runner._require_active_route_qualified(runtime)
    commitment = active_domain_commitment(runtime.active_contract, runtime.domain_binding)
    venue_binding = VenueBindingV2(
        domain_binding=runtime.domain_binding,
        exchange_index_wire_policy=runtime.route_qualification.exchange_index_wire_policy,
        adapter_payload_schema_id=_runner._GATE_D_CREATE_ADAPTER_PAYLOAD_SCHEMA_ID,
    )
    expiration_time = int(runtime.wall_clock().timestamp()) + _runner._GATE_D_CREATE_EXPIRATION_WINDOW_SECONDS
    _protected_body, body = build_non_post_only_create_body(
        ticker=ticker, client_order_id=client_order_id, yes_price=yes_price,
        expiration_time=expiration_time, venue_binding=venue_binding,
    )
    prepared = build_create_prepared_payload(
        request_id=request_id, environment="KALSHI_DEMO", client_order_id=client_order_id,
        canonical_body=body, venue_binding=venue_binding,
    )
    desired = DesiredQuoteV1(QuoteSlot.LOWER_YES_BID.value, "bid", "YES", yes_price, QUOTE_QUANTITY, quote_generation_id)
    state = compute_market_economic_state(ticker, truth.fills, truth.working_orders)
    candidate = candidate_for_desired_quote(market_ticker=ticker, desired=desired)
    try:
        aggregate_input = build_account_aggregate_input(
            locked, risk_config_sha256=runtime.risk_config.sha256, unresolved_exposure_usd=unresolved,
            trusted_dynamic_read_set_id=active_trusted_read_set_id, reconciliation_snapshot_sha256=recon_sha,
        )
    except (RiskControlError, LedgerError):
        aggregate_input = None
    try:
        expectation = build_account_aggregate_authority_expectation(
            locked, risk_config_sha256=runtime.risk_config.sha256,
            trusted_dynamic_read_set_id=active_trusted_read_set_id, reconciliation_snapshot_sha256=recon_sha,
        )
    except (RiskControlError, LedgerError):
        expectation = None
    assessment = build_writer_eligibility_assessment(
        risk_assessment_id=f"ra_{runtime.uuid_factory().hex}", request_id=request_id, candidate=candidate,
        market_economic_state=state, unresolved_exposure=unresolved, risk_config=runtime.risk_config,
        prepared_request_sha256=prepared["prepared_request_sha256"], market_data_snapshot_sha256=market_sha,
        market_data_freshness_identity_sha256=market_fresh, reconciliation_snapshot_sha256=recon_sha,
        reconciliation_freshness_identity_sha256=recon_fresh, risk_state_epoch=projection.risk_state_epoch,
        freshness_deadline_monotonic_ns=freshness_deadline, active_domain_commitment=commitment,
        trusted_dynamic_read_set_id=active_trusted_read_set_id, account_aggregate_input=aggregate_input,
        account_aggregate_expectation=expectation,
    )
    intent = build_mm_create_intent_payload(
        execution_attempt_id=execution_attempt_id, conflict_domain_ref=locked.conflict_domain_ref,
        incident_id=runtime.gate_d_incident_id, client_order_id=client_order_id,
        capability_reference_id=runtime.gate_d_capability_reference_id, request_id=request_id,
        strategy_instance_id=runtime.strategy_instance_id, market_ticker=ticker,
        quote_slot=QuoteSlot.LOWER_YES_BID.value, quote_generation_id=quote_generation_id,
        quote_plan_sha256=plan_sha256, plan_input_sha256=plan_sha256,
        source_book_snapshot_sha256=truth.orderbook.canonical_snapshot_sha256,
        risk_config_sha256=runtime.risk_config.sha256, risk_state_epoch=projection.risk_state_epoch,
        reconciliation_snapshot_sha256=recon_sha, venue_side="bid", outcome_side="YES",
        yes_price=yes_price, quantity=QUOTE_QUANTITY,
    )

    def _out(classification, *, charged, invoked, order_id=None, detail=None, permit=None, t0=None, t1=None, u0=None, u1=None):
        return F03WriteOutcomeV1(
            "CREATE", request_id, client_order_id, order_id, assessment.eligible, charged, invoked, classification, detail,
            prepared["prepared_request_sha256"],
            getattr(permit, "intent_event_id", None), getattr(permit, "prepared_event_id", None),
            getattr(permit, "send_boundary_event_id", None), t0, t1, u0, u1,
        )

    if not assessment.eligible:
        return _out("ELIGIBLE_NOT_SENT", charged=False, invoked=False)
    try:
        permit = runtime.normal_gate.issue_strategy1_gate_d_create_permit(
            locked=locked, normal_writer_session_id=session_id, assessment=assessment,
            intent_payload=intent, prepared_payload=prepared,
        )
        runtime.normal_gate.persist_intent(permit, locked)
        runtime.normal_gate.persist_prepared(permit, locked)
        runtime.normal_gate.persist_send_boundary(permit, locked)
    except (RiskControlError, LedgerError):
        return _out("PERMIT_ISSUANCE_FAILED", charged=False, invoked=False)
    ledger.charge_create_t3()  # charged exactly at durable T3, even if never sent
    if runtime.monotonic_clock_ns() > permit.freshness_deadline_monotonic_ns:
        return _out("FRESHNESS_EXPIRED_BEFORE_ADAPTER", charged=True, invoked=False, permit=permit)
    metadata = active_prepared_request_domain_metadata(venue_binding, canonical_request_sha256=prepared["prepared_request_sha256"])
    mismatch = _runner._require_active_gate_d_pre_adapter_equality(
        runtime=runtime, locked=locked, assessment=assessment, permit=permit, prepared_domain_metadata=metadata,
        prepared_request_sha256=prepared["prepared_request_sha256"], active_trusted_read_set_id=active_trusted_read_set_id,
    )
    if mismatch is not None:
        return _out(mismatch, charged=True, invoked=False, permit=permit)
    binding = _runner._gate_d_prepare_normal_write_binding(
        runtime=runtime, locked=locked, permit=permit, prepared=prepared, deadline=write_deadline,
    )
    if type(binding) is not _runner._NormalWriteOperationBindingV1:
        return _out(binding, charged=True, invoked=False, permit=permit)
    t0 = runtime.monotonic_clock_ns()
    u0 = canonical_timestamp(runtime.wall_clock())
    try:
        ledger.create_transport_invocations += 1
        raw = _runner._gate_d_invoke_normal_write_adapter(
            runtime=runtime, adapter=adapter, permit=permit, prepared=prepared, binding=binding,
        )
    except Exception:
        return _out("ADAPTER_EXCEPTION", charged=True, invoked=True, permit=permit, t0=t0, u0=u0)
    t1 = runtime.monotonic_clock_ns()
    u1 = canonical_timestamp(runtime.wall_clock())
    outcome, order_id, fields_ = _runner._gate_d_classify_create_result(
        raw, expected_client_order_id=client_order_id, deadline=write_deadline, monotonic_clock_ns=runtime.monotonic_clock_ns,
    )
    try:
        _runner._gate_d_record_http_response_classified(
            locked, session_id=session_id, request_id=request_id, raw_response=raw, write_closure_class="UNRESOLVED",
            adapter_result_class=outcome.value, validated_identity_fields=fields_,
        )
    except (LedgerError, RiskControlError):
        return _out("AMBIGUOUS", charged=True, invoked=True, order_id=order_id, detail="PERSISTENCE_FAILED", permit=permit, t0=t0, t1=t1, u0=u0, u1=u1)
    if outcome is not SendOutcome.DEFINITIVE_SUCCESS or order_id is None:
        return _out("AMBIGUOUS", charged=True, invoked=True, permit=permit, t0=t0, t1=t1, u0=u0, u1=u1)
    reconciliation = _runner._gate_d_reconcile_post_create(
        locked=locked, session_id=session_id, capability=capability, runtime=runtime, request_id=request_id,
        client_order_id=client_order_id, response_order_id=order_id, ticker=ticker, expected_outcome_side="YES",
        trusted_prepared_yes_price=Decimal(binding.trusted_t2["canonical_body"]["price"]), raw_response=raw,
        validated_identity_fields=fields_,
    )
    return _out(reconciliation.classification, charged=True, invoked=True, order_id=order_id,
                detail=reconciliation.detail, permit=permit, t0=t0, t1=t1, u0=u0, u1=u1)


# ---------------------------------------------------------------------------
# Section 5.2 -- dynamic numbered-subaccount CANCEL composition (D01 repair).
# ---------------------------------------------------------------------------


def build_f03_active_cancel_prepared_payload(
    *, request_id: str, venue_order_id: str, client_order_id: str, domain_binding,
) -> dict:
    """F03-D01-CANCEL-001 pure constructor: identical to the protected
    ``build_cancel_prepared_payload`` identity except the canonical query is
    derived from the ACTIVE domain.  Owns no transport/signer/permit/ledger/
    risk/retry behaviour.  The protected fixed-domain helper is never called."""
    if type(domain_binding) is not _runner.ExecutionDomainBindingV1:
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "domain binding")
    if type(request_id) is not str or _runner._F03_REQUEST_ID_PATTERN.fullmatch(request_id) is None:
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "request_id")
    if type(venue_order_id) is not str or _runner._ORDER_ID_PATTERN.fullmatch(venue_order_id) is None or venue_order_id in (".", ".."):
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "venue_order_id")
    if type(client_order_id) is not str or _an._UUID4_RE.fullmatch(client_order_id) is None:
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "client_order_id")
    subaccount, exchange_index = domain_binding.subaccount, domain_binding.exchange_index
    if type(subaccount) is not int or type(exchange_index) is not int:
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "domain ints")
    canonical_query = {"subaccount": subaccount, "exchange_index": exchange_index}
    identity = {
        "request_id": request_id,
        "operation_class": "WRITE",
        "venue": "KALSHI",
        "environment": "KALSHI_DEMO",
        "operation_name": "CANCEL_ORDER_V2",
        "method": "DELETE",
        "path_without_query": f"/trade-api/v2/portfolio/events/orders/{venue_order_id}",
        "canonical_query": canonical_query,
        "canonical_query_sha256": sha256_hex(canonical_json_bytes(canonical_query)),
        "canonical_body": None,
        "canonical_body_sha256": None,
        "client_order_id": client_order_id,
        "venue_order_id": venue_order_id,
        "idempotency_key": client_order_id,
        "adapter_payload_schema_id": _runner._GATE_D_CANCEL_ADAPTER_PAYLOAD_SCHEMA_ID,
    }
    prepared = {**identity, "prepared_request_sha256": sha256_hex(canonical_json_bytes(identity))}
    if set(prepared) != set(_runner._GATE_D_T2_PREPARED_KEYS):
        raise F03Halt(HaltCode.CANONICAL_CANCEL_SUBSTRATE_INCOMPATIBLE, "T2 key set")
    return prepared


def execute_f03_cancel(
    *, locked, session_id: str, capability, adapter: NormalWriteAdapter, runtime, ticker: str,
    projection, truth, target_venue_order_id: str, active_trusted_read_set_id: str, ledger: F03BudgetLedgerV1,
) -> F03WriteOutcomeV1:
    """Reproduces the ``_gate_d_execute_cancel`` sequence with the active
    pure T2 builder.  Only the exact proven-active F03 order is a target."""
    ledger.require_cancel_slot()
    reconstruction = reconstruct_slot_ownership(
        locked.events, strategy_instance_id=runtime.strategy_instance_id, market_ticker=ticker,
        quote_slot=QuoteSlot.LOWER_YES_BID.value,
    )
    working = reconstruction.working_order
    if working is None or working.venue_order_id != target_venue_order_id or reconstruction.classification != "ACTIVE_EXACT":
        raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "target not proven active")
    request_id = f"req_{runtime.uuid_factory().hex}"
    execution_attempt_id = f"ea_{runtime.uuid_factory().hex}"
    recon_sha, market_sha, market_fresh, recon_fresh, now_ns, _now_utc = _freshness_identities(runtime, truth)
    freshness_deadline = now_ns + _runner.OPERATION_DEADLINE_MS * 1_000_000
    write_deadline = _runner._gate_d_write_operation_deadline(
        runtime=runtime, request_id=request_id, operation_name="CANCEL_ORDER_V2",
        started_monotonic_ns=now_ns, freshness_deadline_monotonic_ns=freshness_deadline,
    )
    _runner._require_active_route_qualified(runtime)
    commitment = active_domain_commitment(runtime.active_contract, runtime.domain_binding)
    prepared = build_f03_active_cancel_prepared_payload(
        request_id=request_id, venue_order_id=target_venue_order_id, client_order_id=working.client_order_id,
        domain_binding=runtime.domain_binding,
    )
    unresolved = _runner._gate_d_unresolved_exposure_usd(projection, truth)
    assessment = build_cancel_writer_eligibility_assessment(
        active_domain_commitment=commitment, trusted_dynamic_read_set_id=active_trusted_read_set_id,
        risk_assessment_id=f"ra_{runtime.uuid_factory().hex}", request_id=request_id,
        strategy_instance_id=runtime.strategy_instance_id, market_ticker=ticker, quote_slot=QuoteSlot.LOWER_YES_BID.value,
        quote_generation_id=working.quote_generation_id, target_venue_order_id=target_venue_order_id,
        client_order_id=working.client_order_id, authoritative_fills=truth.fills,
        authoritative_working_orders=truth.working_orders, unresolved_exposure_usd=unresolved,
        prepared_request_sha256=prepared["prepared_request_sha256"], risk_config=runtime.risk_config,
        market_data_snapshot_sha256=market_sha, market_data_freshness_identity_sha256=market_fresh,
        reconciliation_snapshot_sha256=recon_sha, reconciliation_freshness_identity_sha256=recon_fresh,
        risk_state_epoch=projection.risk_state_epoch, freshness_deadline_monotonic_ns=freshness_deadline,
    )
    intent = build_mm_cancel_intent_payload(
        execution_attempt_id=execution_attempt_id, conflict_domain_ref=locked.conflict_domain_ref,
        incident_id=runtime.gate_d_incident_id, client_order_id=working.client_order_id,
        capability_reference_id=runtime.gate_d_capability_reference_id, request_id=request_id,
        strategy_instance_id=runtime.strategy_instance_id, market_ticker=ticker,
        quote_slot=QuoteSlot.LOWER_YES_BID.value, quote_generation_id=working.quote_generation_id,
        target_venue_order_id=target_venue_order_id, reconciliation_snapshot_sha256=recon_sha,
    )

    def _out(classification, *, charged, invoked, detail=None, permit=None, t0=None, t1=None, u0=None, u1=None):
        return F03WriteOutcomeV1(
            "CANCEL", request_id, working.client_order_id, target_venue_order_id, assessment.eligible, charged, invoked,
            classification, detail, prepared["prepared_request_sha256"],
            getattr(permit, "intent_event_id", None), getattr(permit, "prepared_event_id", None),
            getattr(permit, "send_boundary_event_id", None), t0, t1, u0, u1,
        )

    try:
        validate_cancel_request_binding(outer_intent_payload=intent, prepared_payload=prepared, assessment=assessment,
                                        target_venue_order_id=target_venue_order_id)
    except QuoteLifecycleError:
        return _out("TARGET_BINDING_INVALID", charged=False, invoked=False)
    if not assessment.eligible:
        return _out("ELIGIBLE_NOT_SENT", charged=False, invoked=False)
    try:
        permit = issue_and_persist_write_permit(
            gate=runtime.normal_gate, locked=locked, normal_writer_session_id=session_id, assessment=assessment,
            outer_intent_payload=intent, prepared_payload=prepared,
        )
    except (RiskControlError, LedgerError):
        return _out("PERMIT_ISSUANCE_FAILED", charged=False, invoked=False)
    ledger.charge_cancel_t3()
    try:
        validate_cancel_request_binding(outer_intent_payload=intent, prepared_payload=prepared, assessment=assessment,
                                        target_venue_order_id=target_venue_order_id)
    except QuoteLifecycleError:
        return _out("TARGET_BINDING_INVALID", charged=True, invoked=False, permit=permit)
    if runtime.monotonic_clock_ns() > permit.freshness_deadline_monotonic_ns:
        return _out("FRESHNESS_EXPIRED_BEFORE_ADAPTER", charged=True, invoked=False, permit=permit)
    metadata = {
        "conflict_domain_ref": runtime.domain_binding.conflict_domain_ref,
        "domain_binding_id": runtime.domain_binding.binding_id,
        "domain_binding_sha256": runtime.domain_binding.binding_sha256,
        "exchange_index": runtime.domain_binding.exchange_index,
        "exchange_index_wire_policy": runtime.route_qualification.exchange_index_wire_policy,
        "canonical_request_sha256": prepared["prepared_request_sha256"],
        "subaccount": runtime.domain_binding.subaccount,
    }
    mismatch = _runner._require_active_gate_d_pre_adapter_equality(
        runtime=runtime, locked=locked, assessment=assessment, permit=permit, prepared_domain_metadata=metadata,
        prepared_request_sha256=prepared["prepared_request_sha256"], active_trusted_read_set_id=active_trusted_read_set_id,
    )
    if mismatch is not None:
        return _out(mismatch, charged=True, invoked=False, permit=permit)
    binding = _runner._gate_d_prepare_normal_write_binding(
        runtime=runtime, locked=locked, permit=permit, prepared=prepared, deadline=write_deadline,
    )
    if type(binding) is not _runner._NormalWriteOperationBindingV1:
        return _out(binding, charged=True, invoked=False, permit=permit)
    t0 = runtime.monotonic_clock_ns()
    u0 = canonical_timestamp(runtime.wall_clock())
    try:
        ledger.cancel_transport_invocations += 1
        raw = _runner._gate_d_invoke_normal_write_adapter(
            runtime=runtime, adapter=adapter, permit=permit, prepared=prepared, binding=binding,
        )
    except Exception:
        return _out("ADAPTER_EXCEPTION", charged=True, invoked=True, permit=permit, t0=t0, u0=u0)
    t1 = runtime.monotonic_clock_ns()
    u1 = canonical_timestamp(runtime.wall_clock())
    send_outcome, body = _runner._gate_d_classify_cancel_result(
        raw, expected_order_id=target_venue_order_id, expected_client_order_id=working.client_order_id,
    )
    reduced_by: Decimal | None = None
    fields_: dict = {}
    if send_outcome is SendOutcome.DEFINITIVE_SUCCESS:
        reduced_by = _runner._gate_d_parse_cancel_fixed_point_count(body.get("reduced_by"))
        fields_ = {"order_id": body.get("order_id"), "reduced_by": body.get("reduced_by"), "ts_ms": body.get("ts_ms")}
        if "client_order_id" in body:
            fields_["client_order_id"] = body.get("client_order_id")
    classification = "AMBIGUOUS"
    try:
        status, row = _runner._gate_d_read_order_status(capability, order_id=target_venue_order_id)
    except _runner.RunnerError:
        status, row = "", {}
    fresh_fills: tuple = ()
    if status in _runner._GATE_D_TERMINAL_ORDER_STATUSES:
        b = runtime.domain_binding
        violation = _runner._gate_d_validate_terminal_order_identity(
            row, expected_order_id=target_venue_order_id, expected_client_order_id=working.client_order_id,
            expected_ticker=ticker, expected_outcome_side=working.outcome_side, expected_yes_price=working.yes_price,
            expected_subaccount=b.subaccount, expected_exchange_index=b.exchange_index,
        )
        if violation is not None:
            classification = "TERMINAL_UNRECONCILED"
        else:
            try:
                fresh_fills, complete = _runner._gate_d_fetch_fresh_fills_for_order(capability, ticker=ticker, order_id=target_venue_order_id)
            except _runner.RunnerError:
                fresh_fills, complete = (), False
            if not complete or _runner._gate_d_fresh_fill_reconciliation_violation(order_row=row, fresh_fills=fresh_fills) is not None:
                classification = "TERMINAL_UNRECONCILED"
            else:
                total = sum((f.quantity for f in fresh_fills), Decimal("0"))
                if status == "canceled":
                    if reduced_by is None or check_cancel_conservation(final_fill_quantity=total, reduced_by=reduced_by) is not None:
                        classification = "TERMINAL_UNRECONCILED"
                    else:
                        classification = "TERMINAL"
                else:
                    classification = "TERMINAL" if total == QUOTE_QUANTITY else "TERMINAL_UNRECONCILED"
        if classification == "TERMINAL":
            _runner._gate_d_record_terminal_order_observation(
                locked, session_id=session_id, venue_order_id=target_venue_order_id,
                client_order_id=working.client_order_id, order_row=row,
            )
            durable = {e.payload.get("venue_fill_id") for e in locked.events if e.event_type.name == "FILL_OBSERVED"}
            for fill in fresh_fills:
                if fill.fill_id not in durable:
                    _runner._gate_d_record_fill_observation(
                        locked, session_id=session_id, venue_order_id=target_venue_order_id,
                        client_order_id=working.client_order_id, fill=fill,
                    )
            _runner._gate_d_record_closing_reconciliation(
                locked, session_id=session_id, incident_id=runtime.gate_d_incident_id, bound_order_id=target_venue_order_id,
            )
    elif status == "resting":
        classification = "STILL_ACTIVE"
    _runner._gate_d_record_http_response_classified(
        locked, session_id=session_id, request_id=request_id, raw_response=raw,
        write_closure_class="AUTHORITATIVE_RESULT_CLOSED" if classification == "TERMINAL" else "UNRESOLVED",
        adapter_result_class=send_outcome.value, validated_identity_fields=fields_,
    )
    return _out(classification, charged=True, invoked=True, permit=permit, t0=t0, t1=t1, u0=u0, u1=u1)


# ---------------------------------------------------------------------------
# Section 10.2 -- fee-field fill collection (complete domain pages, LOCAL
# filtering by exact order/domain/ticker).
# ---------------------------------------------------------------------------


def collect_order_fee_fills(
    snapshot: F03DomainSnapshotV1, *, order_id: str, ticker: str, domain_binding,
) -> Tuple[_an.ObservedFillFeeFieldsV1, ...]:
    if not snapshot.complete:
        raise F03Halt(HaltCode.FILL_PAGINATION_INCOMPLETE, "domain incomplete")
    selected = [row for row in snapshot.fill_rows if row.get("order_id") == order_id]
    parsed: dict = {}
    try:
        items = [
            _an.parse_fill_fee_fields(row, expected_subaccount=domain_binding.subaccount,
                                      expected_exchange_index=domain_binding.exchange_index,
                                      expected_ticker=ticker, expected_order_id=order_id)
            for row in selected
        ]
        parsed = _an.merge_fill_observations(parsed, items)
    except _an.F03AnalyzerError as exc:
        if exc.code == HaltCode.FILL_DUPLICATE_CONFLICT.value:
            raise F03Halt(HaltCode.FILL_DUPLICATE_CONFLICT, exc.detail) from None
        if exc.code == HaltCode.OFFICIAL_SOURCE_CONFLICT.value:
            raise F03Halt(HaltCode.OFFICIAL_SOURCE_CONFLICT, exc.detail) from None
        raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, exc.code) from None
    fills = tuple(sorted(parsed.values(), key=lambda f: (f.created_time, f.fill_id)))
    if len([f for f in fills if f.quantity > 0]) > _an.MAX_POSITIVE_FILLS_PER_ORDER:
        raise F03Halt(HaltCode.FILL_DUPLICATE_CONFLICT, ">100 positive fills")
    return fills


def fill_model_inputs(fills: Sequence[_an.ObservedFillFeeFieldsV1], *, maker_multiplier: Decimal) -> Tuple[_an.TimedFillV1, ...]:
    out = []
    for f in fills:
        k = _an.role_coefficient(is_taker=f.is_taker)
        multiplier = Decimal("1") if f.is_taker else maker_multiplier
        out.append(_an.TimedFillV1(_an.FillModelInputV1(f.quantity, f.yes_price, k, multiplier), f.created_time, None))
    return tuple(out)


# ---------------------------------------------------------------------------
# Section 16 -- sanitized shared evidence exporter (closed projections and
# real-path containment checked before any output creation).
# ---------------------------------------------------------------------------


def _resolved_components(path: Path) -> Path:
    """Component-wise check on the UNRESOLVED absolute path (a resolved path
    would already have followed the link), then the real resolved path."""
    absolute = Path(os.path.abspath(path))
    probe = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        probe = probe / part
        if probe.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(probe)):
            raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, "symlink/junction in output path")
    return absolute.resolve(strict=False)


def require_output_containment(output_dir: Path, *, prohibited_roots: Sequence[Path]) -> Path:
    """Output must resolve OUTSIDE the canonical repository, ledger/state and
    credential roots (component-wise real paths), must not traverse a
    symlink/junction, and must not already exist (no overwrite/replay)."""
    target = _resolved_components(Path(output_dir))
    for root in prohibited_roots:
        real_root = Path(root).resolve(strict=False)
        if target == real_root or real_root in target.parents or target in real_root.parents:
            raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, "output path containment")
    if target.exists():
        raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, "run output already exists")
    return target


RUN_CLAIM_FILE_NAME = "RUN_CLAIM.json"
RUN_CLAIM_SCHEMA = "F03_RUN_CLAIM_V1"


def claim_run_folder(*, run_artifact_root: Path, prohibited_roots: Sequence[Path], claim: Mapping[str, object]) -> Tuple[Path, str]:
    """F03 Correction01 (BLOCK F05): mandatory DURABLE pre-execution
    non-replay admission.  The run folder ``<root>/<run_id>`` is created with
    one atomic ``os.mkdir`` (fails if it exists -- a duplicate, concurrent or
    fresh-process attempt for the same run id) and the claim is written with
    exclusive create, BEFORE any venue read.  A crash after the claim leaves
    it in place: a claimed run is never resumed or re-executed."""
    root = _resolved_components(Path(run_artifact_root))
    for prohibited in prohibited_roots:
        real = Path(prohibited).resolve(strict=False)
        if root == real or real in root.parents or root in real.parents:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run artifact root containment")
    if not root.is_dir():
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run artifact root absent")
    run_id = claim.get("run_id")
    if type(run_id) is not str or _an._UUID4_RE.fullmatch(run_id) is None:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run claim id")
    folder = root / run_id
    try:
        os.mkdir(folder)
    except FileExistsError:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run id already claimed (no replay/resume)") from None
    except OSError:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run claim folder not creatable") from None
    data = canonical_json_bytes(dict(claim))
    try:
        with open(folder / RUN_CLAIM_FILE_NAME, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        # The folder itself is the claim: an unwritten claim file still
        # blocks every later attempt for this run id (fail closed).
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run claim not durably written") from None
    return folder, sha256_hex(data)


def export_shared_run_evidence(record: Mapping[str, object], *, output_dir: Path, prohibited_roots: Sequence[Path]) -> Path:
    try:
        _an.validate_fee_experiment_run_v1(dict(record))
    except _an.F03AnalyzerError as exc:
        raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, exc.code) from None
    target = require_output_containment(output_dir, prohibited_roots=prohibited_roots)
    target.mkdir(parents=True, exist_ok=False)
    path = target / "FeeExperimentRunV1.sanitized.json"
    data = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    with open(path, "xb") as handle:
        handle.write(data)
    return path


# ---------------------------------------------------------------------------
# Orchestration -- the closed experiment flow (sections 9-11, 15, 20, 25).
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class F03OrderRecordV1:
    probe_order_index: int
    client_order_id: str | None = None
    order_id: str | None = None
    limit_price: Decimal | None = None
    create: F03WriteOutcomeV1 | None = None
    cancel: F03WriteOutcomeV1 | None = None
    exact_order_rows: list = field(default_factory=list)
    fills: Tuple[_an.ObservedFillFeeFieldsV1, ...] = ()
    terminal_classification: str | None = None
    remaining_quantity: str | None = None
    hypothesis_start: Decimal | None = None
    hypothesis_end: Decimal | None = None
    ledger_anchors: list = field(default_factory=list)

    def shared_projection(self) -> dict:
        def _w(o: F03WriteOutcomeV1 | None):
            if o is None:
                return None
            return {
                "request_id": o.request_id, "classification": o.classification, "t3_charged": o.t3_charged,
                "transport_invoked": o.transport_invoked, "prepared_request_sha256": o.prepared_request_sha256,
                "intent_event_id": o.intent_event_id, "prepared_event_id": o.prepared_event_id,
                "send_boundary_event_id": o.send_boundary_event_id, "detail": o.detail,
                "send_started_monotonic_ns": o.send_started_monotonic_ns,
                "send_completed_monotonic_ns": o.send_completed_monotonic_ns,
                "send_started_utc": o.send_started_utc, "send_completed_utc": o.send_completed_utc,
            }
        return {
            "schema": "FeeProbeOrderV1", "probe_order_index": self.probe_order_index,
            "client_order_id": self.client_order_id, "order_id": self.order_id,
            "side": "bid", "outcome_side": "YES", "quantity": "1",
            "limit_price": _an.canonical_decimal_text(self.limit_price) if self.limit_price is not None else None,
            "time_in_force": "good_till_canceled", "create": _w(self.create), "cancel": _w(self.cancel),
            "response_classification": self.create.classification if self.create else None,
            "exact_order_observations": list(self.exact_order_rows),
            "fills": [
                {"fill_id": f.fill_id, "trade_id": f.trade_id, "order_id": f.order_id, "ticker": f.ticker,
                 "count_fp": f.count_lexeme, "yes_price_dollars": f.yes_price_lexeme, "is_taker": f.is_taker,
                 "created_time": f.created_time, "fee_cost": f.fee_cost_lexeme}
                for f in self.fills
            ],
            "terminal_classification": self.terminal_classification, "remaining_quantity": self.remaining_quantity,
            "ledger_anchors": [dict(a) for a in self.ledger_anchors],
            "hypothesis_accumulator_start": {"evidence_class": _an.EVIDENCE_CLASS_MODEL_HYPOTHESIS, "authoritative": False,
                                             "value": _an.canonical_decimal_text(self.hypothesis_start) if self.hypothesis_start is not None else None},
            "hypothesis_accumulator_end": {"evidence_class": _an.EVIDENCE_CLASS_MODEL_HYPOTHESIS, "authoritative": False,
                                           "value": _an.canonical_decimal_text(self.hypothesis_end) if self.hypothesis_end is not None else None},
        }


@dataclass(frozen=True, slots=True)
class F03RunResultV1:
    final_state: str
    halt: F03Halt | None
    shared_record: Mapping[str, object]
    question_results: Tuple[Mapping[str, object], ...]
    unresolved_active_exposure: bool
    remaining_inventory_note: str


class F03FeeExperimentRunnerV1:
    """The bounded F03 Demo fee-semantics experiment.  One instance == one
    run id; a completed or halted run is never re-executed or resumed."""

    _completed_run_ids: set = set()

    def __init__(self, *, runtime, plan: F03RunPlanV1, observed_identity: F03ObservedIdentityV1,
                 run_artifact_root: Path, prohibited_roots: Sequence[Path], invocation_id: str | None = None) -> None:
        if plan.run_id in F03FeeExperimentRunnerV1._completed_run_ids:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run id already executed")
        if run_artifact_root is None or not prohibited_roots:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "durable run claim root required")
        self.run_artifact_root = Path(run_artifact_root)
        self.prohibited_roots = tuple(Path(p) for p in prohibited_roots)
        self.run_folder: Path | None = None
        self.run_claim_sha256: str | None = None
        self.plan = plan
        self.observed_identity = observed_identity
        self.machine = F03StateMachineV1()
        self.ledger = F03BudgetLedgerV1()
        self._base_runtime = runtime
        self.runtime = None
        self.guard: _F03CountedReadTransportV1 | None = None
        self.balance = F03BalanceCheckpointerV1(self.ledger)
        self.checkpoints: dict[str, F03CheckpointRecordV1] = {}
        self.orders: list[F03OrderRecordV1] = []
        self.read_observations: list = []
        self.halt: F03Halt | None = None
        self.stage3 = None
        self.used_read_set_ids: list[str] = []
        self.run_started_ns: int | None = None
        self.active_end_ns: int | None = None
        self.tail_end_ns: int | None = None
        self.utc_audit: dict = {}
        self.invocation_id = invocation_id or plan.run_id
        self.baseline_identity: str | None = None
        self.final_identity: str | None = None
        self.baseline_fill_ids: frozenset = frozenset()
        self._interval_predicates: dict = {}
        self._interval_analysis: dict = {}
        self.baseline_order_ids: frozenset = frozenset()
        self.isolation: dict[str, str] = {name: _an.PredicateState.UNRESOLVED.value for name in _an.ISOLATION_PREDICATES}
        self.unresolved_active_exposure = False
        self.bound = _an.conservative_outlay_bound(
            order_count=plan.planned_order_count, max_limit_price=_an.MAX_LIMIT_PRICE, taker_multiplier=plan.taker_multiplier,
        )

    # -- helpers -------------------------------------------------------------

    def _halt(self, exc: F03Halt) -> None:
        if self.halt is None:
            self.halt = exc
        self.machine.halt()
        if self.active_end_ns is not None and self.tail_end_ns is None and self.runtime is not None:
            now = self.runtime.monotonic_clock_ns()
            self.tail_end_ns = min(self.active_end_ns, now) + RECONCILIATION_TAIL_NS

    def _active_deadline_check(self) -> None:
        if self.runtime.monotonic_clock_ns() >= self.active_end_ns:
            raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "active write interval closed")

    def _campaign(self, phase: str, reserve: int = DOMAIN_CAMPAIGN_GET_RESERVATION) -> F03ObservationCampaignV1:
        return F03ObservationCampaignV1(self.runtime, self.ledger, self.guard, phase=phase, reserve=reserve)

    def _plan_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes({
            "schema": "F03_RUN_PLAN_V1", "run_id": self.plan.run_id, "ticker": self.plan.ticker,
            "order1_limit_price": _an.canonical_decimal_text(self.plan.order1_limit_price),
            "order2_limit_price": None if self.plan.order2_limit_price is None else _an.canonical_decimal_text(self.plan.order2_limit_price),
            "account_class": self.plan.account_class, "fee_epoch_id": self.plan.fee_epoch_id,
        }))

    def _claim_object(self) -> dict:
        b = self._base_runtime.domain_binding
        return {
            "claim_schema": RUN_CLAIM_SCHEMA, "run_id": self.plan.run_id, "plan_sha256": self._plan_sha256(),
            "canonical_commit": self.plan.expected_commit, "canonical_tree": self.plan.expected_tree,
            "canonical_parent": self.plan.expected_parent,
            "implementation_artifacts": dict(sorted(self.plan.implementation_artifacts.items())),
            "process_instance_id": self._base_runtime.normal_gate.process_instance_id,
            "domain_binding_id": b.binding_id, "domain_binding_sha256": b.binding_sha256,
            "subaccount_number": b.subaccount, "exchange_index": b.exchange_index, "ticker": self.plan.ticker,
            "source_identities": {name: {"bytes": size, "sha256": sha} for name, (size, sha) in sorted(_an.SOURCE_IDENTITIES.items())},
            "balance_source_binding_id": _runner.F03_BALANCE_SOURCE_BINDING_ID,
        }

    def claim(self) -> None:
        """Mandatory durable non-replay admission (before ANY venue read)."""
        if self.run_folder is not None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run already claimed by this instance")
        # The runtime's own repository / ledger-state / authority roots are
        # always excluded, independent of the caller-supplied roots.
        rt = self._base_runtime
        authority = getattr(rt, "authority_binding", None)
        repository = getattr(rt, "canonical_repository_root", None)
        ledger = getattr(rt, "expected_ledger_path", None)
        if authority is None or not repository or not ledger:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "runtime roots unresolved for run claim containment")
        derived = (Path(repository), Path(authority.authority_namespace_root), Path(ledger).parent)
        self.run_folder, self.run_claim_sha256 = claim_run_folder(
            run_artifact_root=self.run_artifact_root, prohibited_roots=tuple(self.prohibited_roots) + derived,
            claim=self._claim_object(),
        )

    def _require_no_prior_plan_create(self, locked) -> None:
        """Durable-ledger cross-check before every CREATE: the number of CREATE
        intents bound to this exact plan (which binds the run id) must equal
        the CREATEs this run instance has already recorded."""
        plan_sha = self._plan_sha256()
        durable = 0
        for event in locked.events:
            if event.event_type.name != "EXECUTION_INTENT_RECORDED":
                continue
            payload = event.payload.get("intent_payload")
            if isinstance(payload, Mapping) and payload.get("quote_plan_sha256") == plan_sha:
                durable += 1
        local = sum(1 for o in self.orders if o.create is not None and o.create.intent_event_id is not None)
        if durable != local:
            raise F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "durable ledger already holds a CREATE intent for this run plan")

    # -- phases --------------------------------------------------------------

    def bind_source(self) -> None:
        verify_source_binding(self.plan, self.observed_identity)
        verify_domain_and_origin(self._base_runtime)
        _an.require_plan_within_outlay_bound(self.bound)
        self.run_started_ns = self._base_runtime.monotonic_clock_ns()
        self.active_end_ns = self.run_started_ns + ACTIVE_WRITE_INTERVAL_NS
        self.runtime, self.guard = build_f03_runtime_v1(self._base_runtime, self.ledger, active_end_monotonic_ns=self.active_end_ns)
        self.utc_audit["run_started_utc"] = canonical_timestamp(self.runtime.wall_clock())
        self.machine.advance(F03State.SOURCE_BOUND)

    def preflight(self) -> None:
        self.machine.advance(F03State.PREFLIGHT_READS)
        active_end_utc = self.runtime.wall_clock() + _seconds(ACTIVE_WRITE_INTERVAL_NS)
        limits = [self.plan.order1_limit_price] + ([self.plan.order2_limit_price] if self.plan.order2_limit_price is not None else [])
        with self._campaign("PREFLIGHT") as campaign:
            market = campaign.market(self.plan.ticker)
            verify_market_metadata(market, plan=self.plan, active_end_utc=active_end_utc, limit_prices=limits)
            snapshot = campaign.domain(selected_ticker=self.plan.ticker)
            book = campaign.orderbook(self.plan.ticker)
        assess_baseline_isolation(snapshot, ticker=self.plan.ticker)
        opportunity = _an.order1_opportunity(
            tuple((lvl.price, lvl.quantity) for lvl in book.no_levels), limit_price=self.plan.order1_limit_price,
        )
        self.read_observations.append({"phase": "PREFLIGHT", "page_commitments": list(snapshot.page_commitments),
                                       "opportunity": opportunity.reason, "table_price_level_present": opportunity.table_price_level_present})
        self.baseline_identity = sha256_hex(canonical_json_bytes(list(snapshot.page_commitments)))
        self.baseline_fill_ids = frozenset(str(r.get("fill_id")) for r in snapshot.fill_rows)
        self.baseline_order_ids = frozenset(str(r.get("order_id")) for r in snapshot.order_rows)
        if self.plan.account_class == _an.AccountClass.UNRESOLVED:
            raise F03Halt(HaltCode.ACCOUNT_CLASS_UNRESOLVED, "fee-discriminating CREATE prohibited")
        if not opportunity.eligible:
            raise F03Halt(HaltCode.MARKET_NOT_DISCRIMINATING, opportunity.reason)
        for name in ("COMPLETE_ACTIVE_DOMAIN_ORDERS_FILLS_POSITIONS", "NO_UNRELATED_WORKING_ORDER_IN_DOMAIN",
                     "NO_PREEXISTING_UNSETTLED_POSITION_RISK", "NO_TEST_ID_COLLISION", "MARKET_CLOSE_AFTER_ACTIVE_END_PLUS_120S",
                     "NO_CROSS_DOMAIN_OR_FEE_EPOCH_CHANGE"):
            self.isolation[name] = _an.PredicateState.PASS.value
        # Operator execution premise (spec F03-ISO-001): no manual funding /
        # transfer / adjustment during the run.  It cannot be proven and is
        # carried as an explicit joint premise in every conclusion.
        self.isolation["NO_SETTLEMENT_TRANSFER_ADJUSTMENT_EFFECT"] = _an.PredicateState.PASS.value
        # Direct members carry no third-party/FCM fee; a non-direct account's
        # external charges are unknown and stay UNRESOLVED (ineligible).
        self.isolation["NO_EXTERNAL_THIRD_PARTY_CHARGE"] = (
            _an.PredicateState.PASS.value if self.plan.account_class == _an.AccountClass.DIRECT
            else _an.PredicateState.UNRESOLVED.value
        )

    def checkpoint(self, boundary: str, *, latest_fill_execution_utc: datetime | None = None) -> F03CheckpointRecordV1:
        self.guard.set_phase("BALANCE_" + boundary)
        record = self.balance.run(self.runtime, boundary=boundary, latest_fill_execution_utc=latest_fill_execution_utc)
        self.checkpoints[boundary] = record
        if record.state != _an.CheckpointState.STABLE:
            raise F03Halt(HaltCode(record.halt_code or HaltCode.BALANCE_CHECKPOINT_NOT_STABLE.value), boundary)
        return record

    def b0(self) -> None:
        self.machine.advance(F03State.B0_CHECKPOINT)
        record = self.checkpoint("B0")
        sufficient = record._private_stable_balance is not None and record._private_stable_balance >= self.bound.plan_strict_upper
        # Shared evidence carries only the predicate and the bound, never the amount.
        self.read_observations.append({"phase": "B0", "sufficient_existing_balance": sufficient,
                                       "conservative_incremental_bound": _an.canonical_decimal_text(self.bound.plan_strict_upper)})
        if not sufficient:
            raise F03Halt(HaltCode.INSUFFICIENT_EXISTING_BALANCE, "existing balance below conservative incremental bound")

    def admit(self) -> None:
        """Canonical current-process writer admission through the protected
        Stage-3 chain; a state string never mints authority."""
        self.machine.advance(F03State.CURRENT_PROCESS_WRITER_ADMISSION)
        self.ledger.require_get_capacity(
            STAGE3_ADMISSION_GET_RESERVATION + ORDER_LIFECYCLE_GET_RESERVATION + FINAL_RECONCILIATION_GET_RESERVATION,
            purpose="admission and ORDER1 lifecycle",
        )
        self._admit_fresh()
        self.machine.advance(F03State.WRITER_ELIGIBLE)

    def _admit_fresh(self) -> None:
        self.ledger.require_get_capacity(STAGE3_ADMISSION_GET_RESERVATION, purpose="stage3 admission")
        self.guard.set_phase("STAGE3_ADMISSION")
        before = self.ledger.get_count
        invocation = _runner.ExperimentRunnerInvocationV2(invocation_id=self.invocation_id, market_ticker=self.plan.ticker)
        try:
            read_phase = _runner.run_pre_release_read_phase_v2(invocation, self.runtime)
        except _runner.RunnerError:
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "stage3 read phase failed") from None
        observed = self.ledger.get_count - before
        protected = read_phase.requests_consumed if type(read_phase.requests_consumed) is int else 0
        if observed > max(protected, 0) and protected > 0:
            raise F03Halt(HaltCode.BUDGET_EXCEEDED, "observed reads disagree with protected stage3 accounting")
        self.ledger.charge_unobserved_protected_gets(max(protected - observed, 0), phase="STAGE3_ADMISSION")
        if read_phase.status != "READ_PHASE_COMPLETE":
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "stage3 locally blocked")
        try:
            stage3 = _runner._complete_stage3_active_release_and_normal_writer_v2(read_phase, self.runtime)
        except _runner.RunnerError:
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "release/normal writer admission failed") from None
        rsid = stage3.trusted_dynamic_read_set_id
        if rsid in self.used_read_set_ids:
            _runner._fail_closed_end_writer_session(stage3.normal_writer_acquisition.handle, stage3.normal_writer_session_id)
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "stale trusted read set reuse")
        projection = stage3.normal_writer_acquisition.handle.projection()
        if (projection.risk_control_state != "WRITER_ELIGIBLE" or projection.unresolved_write_request_ids
                or projection.protected_unresolved_legacy_write_count != 0):
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "writer state")
        self.used_read_set_ids.append(rsid)
        self.stage3 = stage3

    def _end_session(self) -> None:
        if self.stage3 is not None:
            handle = self.stage3.normal_writer_acquisition.handle
            if handle is not None and not handle.closed:
                end_writer_session(handle, writer_session_id=self.stage3.normal_writer_session_id)

    def _gate_d_capability(self):
        """ONE protected Gate-D read capability per order lifecycle (the same
        closed six-operation surface and 64-read ceiling the Gate-D loop uses)."""
        return _runner._issue_gate_d_read_capability(
            process_instance_id=self.runtime.normal_gate.process_instance_id, ticker=self.plan.ticker, runtime=self.runtime,
        )

    def _gate_d_truth(self, capability):
        truth = _runner.collect_authoritative_read_truth(capability, ticker=self.plan.ticker)
        if not truth.orders_complete or not truth.fills_complete or truth.position_corroboration != "CORROBORATED":
            raise F03Halt(HaltCode.BASELINE_UNKNOWN_EXPOSURE, "gate-d truth incomplete")
        return truth

    def run_order(self, index: int, limit_price: Decimal) -> F03OrderRecordV1:
        prepared_state = F03State.ORDER1_PREPARED if index == 1 else F03State.ORDER2_PREPARED
        self.machine.advance(prepared_state)
        record = F03OrderRecordV1(probe_order_index=index, limit_price=limit_price)
        self.orders.append(record)
        self._active_deadline_check()
        # F03-COUNT-002: the complete worst-case order lifecycle plus the final
        # reconciliation must fit inside GET<=200 before CREATE begins.
        self.ledger.require_get_capacity(ORDER_LIFECYCLE_GET_RESERVATION + FINAL_RECONCILIATION_GET_RESERVATION,
                                         purpose=f"ORDER{index} lifecycle")
        locked = self.stage3.normal_writer_acquisition.handle
        capability = self._gate_d_capability()
        self.guard.set_phase(f"ORDER{index}_TRUTH")
        truth = self._gate_d_truth(capability)
        opportunity = _an.order1_opportunity(
            tuple((lvl.price, lvl.quantity) for lvl in truth.orderbook.no_levels), limit_price=limit_price,
        )
        if not opportunity.eligible:
            # Fresh revalidation failed: no CREATE, no write budget consumed.
            self.machine.advance(F03State.FINAL_RECONCILIATION_ONLY)
            record.terminal_classification = "NOT_SENT_MARKET_NOT_DISCRIMINATING"
            return record
        self.machine.require_write_state()
        self._require_no_prior_plan_create(locked)
        adapter = NormalWriteAdapter(self.runtime.normal_gate, self.runtime.normal_write_transport)
        self.guard.set_phase(f"ORDER{index}_CREATE")
        outcome = execute_f03_create(
            locked=locked, session_id=self.stage3.normal_writer_session_id, capability=capability, adapter=adapter,
            runtime=self.runtime, ticker=self.plan.ticker, projection=locked.projection(), truth=truth,
            yes_price=limit_price, active_trusted_read_set_id=self.stage3.trusted_dynamic_read_set_id,
            plan_sha256=self._plan_sha256(), ledger=self.ledger,
        )
        record.create = outcome
        record.client_order_id = outcome.client_order_id
        record.order_id = outcome.venue_order_id
        anchor = self._anchor(locked, outcome)
        if anchor is not None:
            record.ledger_anchors.append(anchor)
        if not outcome.t3_charged:
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "CREATE not admitted: " + outcome.classification)
        self.machine.advance(F03State.ORDER1_SEND_BOUNDARY if index == 1 else F03State.ORDER2_SEND_BOUNDARY)
        self.machine.advance(F03State.ORDER1_RECONCILING if index == 1 else F03State.ORDER2_RECONCILING)
        if outcome.classification not in ("BOUND_ACTIVE", "TERMINAL"):
            # Unknown/ambiguous CREATE: slot consumed, every later CREATE prohibited.
            raise F03Halt(HaltCode.CREATE_RESULT_AMBIGUOUS, outcome.classification)
        if outcome.classification == "BOUND_ACTIVE":
            self._active_deadline_check()
            self.guard.set_phase(f"ORDER{index}_CANCEL_TRUTH")
            truth = self._gate_d_truth(capability)
            if any(w.order_id == outcome.venue_order_id for w in truth.working_orders):
                self.machine.require_write_state()
                self.guard.set_phase(f"ORDER{index}_CANCEL")
                cancel = execute_f03_cancel(
                    locked=locked, session_id=self.stage3.normal_writer_session_id, capability=capability, adapter=adapter,
                    runtime=self.runtime, ticker=self.plan.ticker, projection=locked.projection(), truth=truth,
                    target_venue_order_id=outcome.venue_order_id, active_trusted_read_set_id=self.stage3.trusted_dynamic_read_set_id,
                    ledger=self.ledger,
                )
                record.cancel = cancel
                anchor = self._anchor(locked, cancel)
                if anchor is not None:
                    record.ledger_anchors.append(anchor)
                if cancel.classification != "TERMINAL":
                    if cancel.t3_charged:
                        # Ambiguous CANCEL: slot consumed, order/exposure stays
                        # unresolved, no second cancel send for this order.
                        self.unresolved_active_exposure = True
                        raise F03Halt(HaltCode.CANCEL_RESULT_AMBIGUOUS, cancel.classification)
                    raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "cancel not admitted: " + cancel.classification)
            else:
                # Filled completely before cancel: no cancel is sent; close the
                # durable slot only from exact authoritative terminal proof.
                self._close_executed_without_cancel(record, capability)
        self._terminal_reconcile(record)
        self.machine.advance(F03State.ORDER1_TERMINAL if index == 1 else F03State.ORDER2_TERMINAL)
        return record

    @staticmethod
    def _anchor(locked, outcome: F03WriteOutcomeV1) -> dict | None:
        """Durable T1/T2/T3 sequence/hash anchors of one probe write."""
        if outcome is None or outcome.send_boundary_event_id is None:
            return None
        by_id = {e.event_id: e for e in locked.events}
        out = {"action": outcome.action, "request_id": outcome.request_id}
        for name, event_id in (("t1", outcome.intent_event_id), ("t2", outcome.prepared_event_id), ("t3", outcome.send_boundary_event_id)):
            event = by_id.get(event_id)
            out[name] = None if event is None else {"event_id": event.event_id, "sequence": event.sequence, "event_hash": event.event_hash}
        return out

    def _close_executed_without_cancel(self, record: F03OrderRecordV1, capability) -> None:
        """Mirror of the protected executed-closure branch: exact terminal row
        identity, complete fresh fills reconciling to the fixed quantity, then
        the protected durable observation/fill/closing-reconciliation helpers."""
        locked = self.stage3.normal_writer_acquisition.handle
        status, row = _runner._gate_d_read_order_status(capability, order_id=record.order_id)
        if status != "executed":
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "bound order neither working nor executed")
        b = self.runtime.domain_binding
        violation = _runner._gate_d_validate_terminal_order_identity(
            row, expected_order_id=record.order_id, expected_client_order_id=record.client_order_id,
            expected_ticker=self.plan.ticker, expected_outcome_side="YES", expected_yes_price=record.limit_price,
            expected_subaccount=b.subaccount, expected_exchange_index=b.exchange_index,
        )
        if violation is not None:
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, violation)
        fills, complete = _runner._gate_d_fetch_fresh_fills_for_order(capability, ticker=self.plan.ticker, order_id=record.order_id)
        if (not complete or _runner._gate_d_fresh_fill_reconciliation_violation(order_row=row, fresh_fills=fills) is not None
                or sum((f.quantity for f in fills), Decimal("0")) != QUOTE_QUANTITY):
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "executed closure proof")
        session_id = self.stage3.normal_writer_session_id
        _runner._gate_d_record_terminal_order_observation(
            locked, session_id=session_id, venue_order_id=record.order_id, client_order_id=record.client_order_id, order_row=row,
        )
        durable = {e.payload.get("venue_fill_id") for e in locked.events if e.event_type.name == "FILL_OBSERVED"}
        for fill in fills:
            if fill.fill_id not in durable:
                _runner._gate_d_record_fill_observation(
                    locked, session_id=session_id, venue_order_id=record.order_id, client_order_id=record.client_order_id, fill=fill,
                )
        _runner._gate_d_record_closing_reconciliation(
            locked, session_id=session_id, incident_id=self.runtime.gate_d_incident_id, bound_order_id=record.order_id,
        )

    def _terminal_reconcile(self, record: F03OrderRecordV1) -> None:
        """Exact-order state + complete fill quantity must reconcile before a
        terminal normal state (never from a timeout)."""
        key = record.client_order_id or ""
        self.ledger.poll("ORDER", key)
        self.ledger.poll("FILL", key)
        with self._campaign(f"ORDER{record.probe_order_index}_TERMINAL") as campaign:
            row = campaign.exact_order(record.order_id)
            snapshot = campaign.domain(selected_ticker=self.plan.ticker)
        status = row.get("status")
        if status not in ("executed", "canceled"):
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "order not terminal")
        try:
            for key in ("fill_count_fp", "remaining_count_fp", "initial_count_fp"):
                _an.parse_fixed_point_count(row.get(key), name=key)
        except _an.F03AnalyzerError:
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "order counts") from None
        if row.get("order_id") != record.order_id:
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "exact order identity")
        record.exact_order_rows.append({k: row.get(k) for k in ("order_id", "status", "fill_count_fp", "remaining_count_fp", "initial_count_fp")})
        fills = collect_order_fee_fills(snapshot, order_id=record.order_id, ticker=self.plan.ticker,
                                        domain_binding=self.runtime.domain_binding)
        filled = _an.exact_add(*(f.quantity for f in fills)) if fills else Decimal("0")
        try:
            order_fill_count = _an.parse_fixed_point_count(row.get("fill_count_fp"), name="fill_count_fp")
            remaining = _an.parse_fixed_point_count(row.get("remaining_count_fp"), name="remaining_count_fp")
        except _an.F03AnalyzerError:
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "order counts") from None
        if filled != order_fill_count:
            raise F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "fill quantity does not reconcile")
        record.fills = fills
        record.terminal_classification = "FULL_FILL" if status == "executed" else "CANCELED_REMAINDER"
        record.remaining_quantity = _an.canonical_decimal_text(remaining)
        self.ledger.add_acquired(filled)
        if any(r.get("status") == "resting" for r in snapshot.order_rows):
            self.isolation["NO_TEST_WORKING_ORDER_AT_EITHER_BOUND"] = _an.PredicateState.FAIL.value
            raise F03Halt(HaltCode.UNRELATED_ACTIVITY_PRESENT, "working order at bound")
        self.isolation["NO_TEST_WORKING_ORDER_AT_EITHER_BOUND"] = _an.PredicateState.PASS.value
        self._require_no_unrelated_activity(snapshot)
        self.read_observations.append({"phase": f"ORDER{record.probe_order_index}_TERMINAL", "page_commitments": list(snapshot.page_commitments)})

    def _require_no_unrelated_activity(self, snapshot: F03DomainSnapshotV1) -> None:
        """F03-PRE-009: every order/fill that appeared in the measured domain
        since the baseline must be an exact probe identity; otherwise cash and
        timing conclusions are not attributable and new CREATEs stop."""
        probe_orders = {o.order_id for o in self.orders if o.order_id}
        new_orders = {str(r.get("order_id")) for r in snapshot.order_rows} - set(self.baseline_order_ids)
        new_fills = [r for r in snapshot.fill_rows if str(r.get("fill_id")) not in self.baseline_fill_ids]
        if not new_orders <= probe_orders or any(r.get("order_id") not in probe_orders for r in new_fills):
            self.isolation["NO_UNEXPLAINED_BALANCE_EVENT"] = _an.PredicateState.FAIL.value
            raise F03Halt(HaltCode.UNRELATED_ACTIVITY_PRESENT, "unrelated order/fill since baseline")
        self.isolation["NO_UNEXPLAINED_BALANCE_EVENT"] = _an.PredicateState.PASS.value

    def _latest_fill_time(self, record: F03OrderRecordV1) -> datetime | None:
        times = [_parse_utc(f.created_time) for f in record.fills]
        times = [t for t in times if t is not None]
        return max(times) if times else None

    def order2_decision(self) -> bool:
        self.machine.advance(F03State.ORDER2_DECISION)
        if self.plan.order2_limit_price is None:
            return False
        order1 = self.orders[0]
        if not order1.fills or self.plan.quantum is None:
            return False
        h = self.plan.quantum
        chronology = self._chronology(order1)
        outcome = _an.invariant_outcome(chronology, h=h, hypothesis=_an.default_candidate_family()[0])
        if outcome.modeled_residual is None:
            # Above the enumeration bound or order-dependent: no carry is
            # identified, so the optional Order 2 is not sent.
            return False
        carry = outcome.modeled_residual
        order1.hypothesis_start = Decimal("0")
        order1.hypothesis_end = carry
        try:
            self._active_deadline_check()
            # A fresh admission + the complete Order-2 lifecycle + the final
            # reconciliation must fit the remaining GET capacity (worst case).
            self.ledger.require_get_capacity(
                STAGE3_ADMISSION_GET_RESERVATION + ORDER_LIFECYCLE_GET_RESERVATION + FINAL_RECONCILIATION_GET_RESERVATION,
                purpose="ORDER2 admission and lifecycle",
            )
        except F03Halt:
            return False
        self.guard.set_phase("ORDER2_DECISION_TRUTH")
        try:
            truth = self._gate_d_truth(self._gate_d_capability())
        except (F03Halt, _runner.RunnerError):
            return False
        opp = _an.order1_opportunity(tuple((lvl.price, lvl.quantity) for lvl in truth.orderbook.no_levels),
                                     limit_price=self.plan.order2_limit_price)
        if not opp.eligible:
            return False
        paths = _an.possible_fill_paths(opp.executable_levels, maker_multiplier=self.plan.maker_multiplier)
        if not _an.order2_reset_separable(paths, h=h, carry_start=carry):
            return False
        # Fresh current-process admission: a NEW trusted read set, never the
        # Order-1 read set or permit.
        self._end_session()
        try:
            self._admit_fresh()
        except F03Halt:
            return False
        return True

    def final_reconciliation(self) -> None:
        if self.machine.state is not F03State.HALTED_HELD:
            self.machine.advance(F03State.FINAL_RECONCILIATION_ONLY)
        with self._campaign("FINAL_RECONCILIATION") as campaign:
            snapshot = campaign.domain(selected_ticker=self.plan.ticker)
        self.final_identity = sha256_hex(canonical_json_bytes(list(snapshot.page_commitments)))
        test_ids = {o.order_id for o in self.orders if o.order_id}
        if any(r.get("status") == "resting" and r.get("order_id") in test_ids for r in snapshot.order_rows):
            self.unresolved_active_exposure = True
        self.read_observations.append({"phase": "FINAL", "page_commitments": list(snapshot.page_commitments)})
        self._require_no_unrelated_activity(snapshot)

    def run(self) -> F03RunResultV1:
        # The durable claim precedes every read; a rejected claim raises to the
        # caller with zero venue requests (nothing to reconcile or report).
        self.claim()
        try:
            self.bind_source()
            self.preflight()
            self.b0()
            self.admit()
            self.run_order(1, self.plan.order1_limit_price)
            if self.machine.state is F03State.ORDER1_TERMINAL:
                self.machine.advance(F03State.B1_CHECKPOINT)
                self.checkpoint("B1", latest_fill_execution_utc=self._latest_fill_time(self.orders[0]))
                if self.order2_decision():
                    self.run_order(2, self.plan.order2_limit_price)
                    if self.machine.state is F03State.ORDER2_TERMINAL:
                        self.machine.advance(F03State.B2_CHECKPOINT)
                        self.checkpoint("B2", latest_fill_execution_utc=self._latest_fill_time(self.orders[1]))
            self.final_reconciliation()
            self.machine.advance(F03State.COMPLETE)
        except F03Halt as exc:
            self._halt(exc)
            self._bounded_tail()
        except _runner.RunnerError as exc:
            self._halt(F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, exc.code.value))
            self._bounded_tail()
        finally:
            try:
                self._end_session()
            except Exception:
                pass
            F03FeeExperimentRunnerV1._completed_run_ids.add(self.plan.run_id)
        return self._result()

    def _bounded_tail(self) -> None:
        """HALTED_HELD: bounded read-only reconciliation only, within the fixed
        tail and remaining GET capacity; never a write, never a restart."""
        if self.runtime is None or self.active_end_ns is None or self.stage3 is None:
            return
        try:
            tail_end = self.tail_end_ns if self.tail_end_ns is not None else self.active_end_ns + RECONCILIATION_TAIL_NS
            self.runtime = with_phase_end(dataclasses.replace(self.runtime, experiment_absolute_end_monotonic_ns=tail_end), tail_end)
            if self.ledger.remaining_gets() < DOMAIN_CAMPAIGN_GET_RESERVATION:
                return
            with self._campaign("HALTED_TAIL") as campaign:
                snapshot = campaign.domain(selected_ticker=self.plan.ticker)
            self.read_observations.append({"phase": "HALTED_TAIL", "page_commitments": list(snapshot.page_commitments)})
            test_ids = {o.order_id for o in self.orders if o.order_id}
            if any(r.get("status") == "resting" and r.get("order_id") in test_ids for r in snapshot.order_rows):
                self.unresolved_active_exposure = True
        except (F03Halt, _runner.RunnerError):
            return

    def export_shared_evidence(self, result: "F03RunResultV1") -> Path:
        """Sanitized shared record into ``<claimed run folder>/shared``."""
        if self.run_folder is None:
            raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, "no claimed run folder")
        return export_shared_run_evidence(result.shared_record, output_dir=self.run_folder / "shared",
                                          prohibited_roots=self.prohibited_roots)

    def export_private_balance_evidence(self) -> Path:
        """User-local exact balance evidence for arithmetic reproduction.
        Refused unless the reviewed plan carries explicit private-evidence
        permission; written to ``<claimed run folder>/private``, never into a
        shared record."""
        if self.plan.private_evidence_permission is not True:
            raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, "private evidence not permitted")
        if self.run_folder is None:
            raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, "no claimed run folder")
        target = require_output_containment(self.run_folder / "private", prohibited_roots=self.prohibited_roots)
        target.mkdir(parents=True, exist_ok=False)
        payload = {
            "schema": "F03_PRIVATE_BALANCE_EVIDENCE_V1", "run_id": self.plan.run_id, "classification": "USER_LOCAL_PRIVATE",
            "checkpoints": {b: (None if cp._private_stable_balance is None else _an.canonical_decimal_text(cp._private_stable_balance))
                            for b, cp in self.checkpoints.items()},
        }
        path = target / "F03_PRIVATE_BALANCE_EVIDENCE.json"
        with open(path, "xb") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return path

    # -- analysis + sanitized projection -------------------------------------

    def _scope(self) -> _an.QuestionScopeV1:
        q = self.plan.quantum
        return _an.QuestionScopeV1(
            account_class=self.plan.account_class, quantum=_an.canonical_decimal_text(q) if q is not None else "UNRESOLVED",
            market_ticker=self.plan.ticker, event_ticker=self.plan.event_ticker, series_ticker=self.plan.series_ticker,
            fee_epoch=self.plan.fee_epoch_id,
            source_identities=tuple(f"{name}:{sha}" for name, (_b, sha) in sorted(_an.SOURCE_IDENTITIES.items())),
        )

    def _interval(self, interval_id: str, pre: str, post: str, order: F03OrderRecordV1 | None) -> _an.CashIntervalResultV1 | None:
        pre_cp, post_cp = self.checkpoints.get(pre), self.checkpoints.get(post)
        if order is None or pre_cp is None or post_cp is None:
            return None
        delta = None
        if pre_cp._private_stable_balance is not None and post_cp._private_stable_balance is not None:
            delta = _an.interval_cash_delta_from_private(pre_cp._private_stable_balance, post_cp._private_stable_balance)
        predicates = dict(self.isolation)
        predicates["BOTH_BOUNDS_STABLE"] = (_an.PredicateState.PASS.value if pre_cp.state == post_cp.state == "STABLE"
                                            else _an.PredicateState.FAIL.value)
        predicates["FEE_FIELDS_COMPLETE"] = _an.PredicateState.PASS.value if order.fills else _an.PredicateState.UNRESOLVED.value
        self._interval_predicates[interval_id] = dict(predicates)
        return _an.analyze_cash_interval(_an.CashIntervalInputV1(
            interval_id=interval_id, pre_checkpoint_state=pre_cp.state, post_checkpoint_state=post_cp.state,
            cash_delta_pre_minus_post=delta,
            principals=tuple(_an.exact_mul(f.quantity, f.yes_price) for f in order.fills),
            api_fee_costs=tuple(f.api_fee_cost for f in order.fills), isolation_predicates=predicates,
            terminal_credit_excluded=self.plan.terminal_credit_exclusion_evidence_id is not None,
            cash_evidence_id=f"{self.plan.run_id}:{interval_id}",
        ))

    def _chronology(self, order: F03OrderRecordV1) -> "_an.ChronologyAssessmentV1":
        return _an.assess_chronology(fill_model_inputs(order.fills, maker_multiplier=self.plan.maker_multiplier))

    def question_results(self) -> Tuple[dict, ...]:
        """All five scoped results.  Any analyzer non-identification that
        escapes the explicit paths is converted into five truthful
        INCONCLUSIVE results (never an exception that loses the run record)."""
        try:
            return self._question_results()
        except _an.F03AnalyzerError as exc:
            self._interval_analysis = {}
            return self._inconclusive_question_results("ANALYZER_NON_IDENTIFICATION_" + exc.code)

    def _inconclusive_question_results(self, conclusion: str) -> Tuple[dict, ...]:
        scope = self._scope()
        mode = {"QF03-04": _an.ScopeMode.AGGREGATE_CONSISTENCY.value, "QF03-05": _an.ScopeMode.SOURCE_SCOPE.value}
        return tuple(
            _an._question_result(qid, _an.QuestionStatus.INCONCLUSIVE, scope=scope,
                                 scope_mode=mode.get(qid, _an.ScopeMode.AGGREGATE_HYPOTHESIS.value), conclusion=conclusion,
                                 does_not_prove=("ANY_FEE_SEMANTICS_CONCLUSION",))
            for qid in _an.QUESTION_IDS
        )

    def _question_results(self) -> Tuple[dict, ...]:
        scope = self._scope()
        integrity = self.halt is None
        o1 = self.orders[0] if self.orders else None
        o2 = self.orders[1] if len(self.orders) > 1 else None
        i1 = self._interval("I1", "B0", "B1", o1)
        i2 = self._interval("I2", "B1", "B2", o2)
        h = self.plan.quantum
        disc = None
        maximal_ids: tuple = ()
        positive = Decimal("0")
        assumptions: tuple = ()
        cap_pred = None
        terminal_disc = None
        if i1 is not None and h is not None and o1 is not None and o1.fills:
            chronology = self._chronology(o1)
            family = _an.default_candidate_family()
            # Q01 tested pair: maximal vs no rebate (zero init + no terminal
            # credit jointly); Q03 tested pair: no-terminal vs floor-credit
            # (same zero init + maximal per-fill rule).  Each pair is compared
            # on its own; an only-terminal-differing twin never blocks Q01.
            q01_pair = (family[0], family[1])
            q03_pair = (family[0], family[2])

            outcomes = {hyp.hypothesis_id: _an.invariant_outcome(chronology, h=h, hypothesis=hyp) for hyp in family}

            def _preds(pair):
                # EVERY member of the tested family is present; an uncomputable
                # or order-dependent member is None (F01: never dropped).
                return {hyp.hypothesis_id: outcomes[hyp.hypothesis_id].predicted_total for hyp in pair}

            disc = _an.discriminate(_preds(q01_pair), observed=i1.cash_fee_total, h=h,
                                    eligible=i1.hypothesis_comparison_eligible,
                                    required_ids=tuple(hyp.hypothesis_id for hyp in q01_pair))
            terminal_disc = _an.discriminate(_preds(q03_pair), observed=i1.cash_fee_total, h=h,
                                             eligible=i1.hypothesis_comparison_eligible,
                                             required_ids=tuple(hyp.hypothesis_id for hyp in q03_pair))
            maximal_ids = (family[0].hypothesis_id,)
            if disc.matched_hypothesis_id is not None:
                matched = next(hyp for hyp in q01_pair if hyp.hypothesis_id == disc.matched_hypothesis_id)
                positive = outcomes[matched.hypothesis_id].positive_rebate_total
                assumptions = matched.assumptions
            if len(o1.fills) == 1:
                timed = fill_model_inputs(o1.fills, maker_multiplier=self.plan.maker_multiplier)
                cap_pred = _an.predict_sequence((timed[0].fill,), h=h, hypothesis=family[0]).predicted_total
        self._interval_analysis = {"I1": (i1, o1, disc), "I2": (i2, o2, None)}
        q1 = _an.decide_q01(_an.Q01InputV1(integrity, i1, disc, maximal_ids, positive, assumptions, cap_pred), scope=scope)
        zero_pred = carry_pred = None
        if i2 is not None and h is not None and o1 is not None and o1.hypothesis_end is not None:
            chronology2 = self._chronology(o2)
            zero_pred = _an.invariant_outcome(chronology2, h=h, hypothesis=_an.default_candidate_family()[0]).predicted_total
            carry_pred = (_an.invariant_outcome(chronology2, h=h, hypothesis=_an.default_candidate_family(carry_start=o1.hypothesis_end)[3]).predicted_total
                          if o1.hypothesis_end > 0 else None)
        q2 = _an.decide_q02(_an.Q02InputV1(
            integrity, o2 is not None, i2 is not None and i2.hypothesis_comparison_eligible,
            i2.cash_fee_total if i2 is not None else None, zero_pred, carry_pred, h or _an.QUANTUM_NON_DIRECT,
            ("MAXIMAL_PER_FILL_RULE", "NO_TERMINAL_CREDIT", "NO_OTHER_ADJUSTMENTS"),
            i2.cash_evidence_id if i2 is not None else "",
        ), scope=scope)
        residual = o1.hypothesis_end if o1 is not None else None
        if residual is None and o1 is not None and o1.fills and h is not None:
            # MODEL_HYPOTHESIS residual of Order 1 (zero init, maximal rule),
            # only when invariant across every admissible ordering.
            end = _an.invariant_outcome(self._chronology(o1), h=h, hypothesis=_an.default_candidate_family()[0]).modeled_residual
            if end is not None:
                residual = end
                o1.hypothesis_start, o1.hypothesis_end = Decimal("0"), residual
        q3 = _an.decide_q03(_an.Q03InputV1(
            integrity, residual, h or _an.QUANTUM_NON_DIRECT, False, i1 is not None and i1.cash_fee_total is not None,
            terminal_disc, ("ZERO_INIT", "MAXIMAL_PER_FILL_RULE", "NO_OTHER_ADJUSTMENTS"),
            tuple(o.terminal_classification or "UNKNOWN" for o in self.orders),
            i1.cash_evidence_id if i1 is not None else "",
        ), scope=scope)
        q4 = _an.decide_q04(_an.Q04InputV1(integrity, i1, tuple(q1["cash_evidence_ids"])), scope=scope)
        single = i1.identified_net_fee if i1 is not None else None
        f1 = o1.fills[0] if o1 is not None and len(o1.fills) == 1 else None
        q5 = _an.decide_q05(_an.Q05InputV1(
            self.plan.account_class, single, f1.quantity if f1 else None, f1.yes_price if f1 else None,
            (Decimal("1") if f1 and f1.is_taker else self.plan.maker_multiplier) if f1 else None,
            False, i1.cash_evidence_id if i1 is not None else "",
        ), scope=scope)
        return (q1, q2, q3, q4, q5)

    def _candidate_records(self, order: F03OrderRecordV1, h: Decimal) -> list:
        records = []
        chronology = self._chronology(order)
        for hyp in _an.default_candidate_family():
            outcome = _an.invariant_outcome(chronology, h=h, hypothesis=hyp)
            total, positive, residual = outcome.predicted_total, outcome.positive_rebate_total, outcome.modeled_residual
            records.append({
                "id": hyp.hypothesis_id, "initializer": str(hyp.initializer), "rebate_rule": str(hyp.rebate_rule),
                "terminal_rule": str(hyp.terminal_rule), "assumptions": list(hyp.assumptions),
                "predicted_total": None if total is None else _an.canonical_decimal_text(total),
                "positive_rebate_total": None if positive is None else _an.canonical_decimal_text(positive),
                "modeled_residual": None if residual is None else _an.canonical_decimal_text(residual),
            })
        return records

    def _interval_record(self, interval_id: str, pre: str, post: str) -> dict | None:
        result, order, disc = self._interval_analysis.get(interval_id, (None, None, None))
        if result is None or order is None:
            return None
        h = self.plan.quantum

        def dec(value):
            return None if value is None else _an.canonical_decimal_text(value)

        record = {
            "schema": "CashFeeIntervalV1", "interval_id": interval_id, "pre_checkpoint_id": pre, "post_checkpoint_id": post,
            "ordered_order_ids": [order.order_id], "ordered_fill_ids": [f.fill_id for f in order.fills],
            "fill_count": result.fill_count, "principal_total": dec(result.principal_total),
            "cash_fee_total": dec(result.cash_fee_total), "api_fee_cost_total": dec(result.api_fee_cost_total),
            "aggregate_fee_cost_consistency_state": result.aggregate_fee_cost_consistency_state,
            "per_fill_fee_identification_state": result.per_fill_fee_identification_state,
            "isolation_predicates": {name: {"state": state, "evidence_refs": []}
                                     for name, state in sorted(self._interval_predicates.get(interval_id, {}).items())},
            "eligibility": result.eligibility, "rejection_codes": list(result.rejection_codes),
            "cash_evidence_id": result.cash_evidence_id,
            "candidate_hypotheses": self._candidate_records(order, h) if h is not None else [],
            "unique_discriminator_state": disc.state if disc is not None else _an.UniqueDiscriminatorState.INELIGIBLE.value,
            "matched_hypothesis_id": disc.matched_hypothesis_id if disc is not None else None,
        }
        _an.validate_cash_fee_interval_v1(record)
        return record

    def _observed_fill_fee_records(self, order: F03OrderRecordV1) -> list:
        """ObservedFillFeeV1: source fields + published arithmetic + explicitly
        non-authoritative hypothesis rows.  ``observed_rebate`` stays null:
        it is never derived from aggregate-equal API values."""
        h = self.plan.quantum
        out = []
        result = self._interval_analysis.get("I1" if order.probe_order_index == 1 else "I2", (None, None, None))[0]
        single = (result is not None and len(order.fills) == 1 and result.per_fill_fee_identification_state
                  == _an.PerFillIdentificationState.SINGLE_FILL_IDENTIFIED.value)
        accumulators = {rule: Decimal("0") for rule in _an.RebateRule}
        chronology = self._chronology(order)
        unique_order = chronology.unique
        for f in order.fills:
            k = _an.role_coefficient(is_taker=f.is_taker)
            m = Decimal("1") if f.is_taker else self.plan.maker_multiplier
            rec = {
                "schema": "ObservedFillFeeV1", "fill_id": f.fill_id, "trade_id": f.trade_id, "order_id": f.order_id,
                "ticker": f.ticker, "market_ticker": f.market_ticker, "subaccount_number": f.subaccount_number,
                "exchange_index": f.exchange_index, "outcome_side": f.outcome_side, "book_side": f.book_side,
                "count_fp": f.count_lexeme, "yes_price_dollars": f.yes_price_lexeme, "no_price_dollars": f.no_price_lexeme,
                "is_taker": f.is_taker, "created_time": f.created_time, "ts": f.ts,
                "api_fee_cost": {"lexeme": f.fee_cost_lexeme, "canonical": _an.canonical_decimal_text(f.api_fee_cost)},
                "k": {"value": _an.canonical_decimal_text(k), "provenance": "kalshi-fee-schedule.pdf ROLE_COEFFICIENT"},
                "M": {"value": _an.canonical_decimal_text(m), "provenance": "fee_regime_inputs"},
                "h": {"value": None if h is None else _an.canonical_decimal_text(h),
                      "provenance": "fee_rounding.md + ACCOUNT_CLASS_ATTESTATION"},
                "per_fill_fee_identification_state": (result.per_fill_fee_identification_state if result is not None
                                                      else _an.PerFillIdentificationState.NOT_ATTEMPTED.value),
                "identified_net_fee": _an.canonical_decimal_text(result.identified_net_fee) if single else None,
                "observed_rebate": None,
                "observed_rebate_null_reason": "NOT_INDEPENDENTLY_IDENTIFIED_PER_FILL",
                "hypothesis_rows": [], "completeness": "COMPLETE",
                "model_fee": None, "trade_fee": None, "revenue": None, "aligned_change": None, "rounding_fee": None,
                "chronology_state": chronology.state,
            }
            if h is not None:
                a = _an.published_fill_arithmetic(quantity=f.quantity, price=f.yes_price, k=k, multiplier=m, h=h)
                rec.update({
                    "model_fee": _an.canonical_decimal_text(a.model_fee), "trade_fee": _an.canonical_decimal_text(a.trade_fee),
                    "revenue": _an.canonical_decimal_text(a.revenue), "aligned_change": _an.canonical_decimal_text(a.aligned_change),
                    "rounding_fee": _an.canonical_decimal_text(a.rounding_fee),
                })
                if unique_order:
                    for rule in _an.RebateRule:
                        row = _an.hypothesis_row(a, accumulator_before=accumulators[rule], rebate_rule=rule)
                        accumulators[rule] = row.accumulator_after_hypothesis
                        rec["hypothesis_rows"].append(dict(row.as_canonical_mapping(), rebate_rule=str(rule),
                                                           initializer="ZERO",
                                                           evidence_class=_an.EVIDENCE_CLASS_MODEL_HYPOTHESIS))
            out.append(rec)
        return out

    def _result(self) -> F03RunResultV1:
        questions = self.question_results()
        b = self._base_runtime.domain_binding
        record = {
            "schema": "FeeExperimentRunV1",
            "run_id": self.plan.run_id,
            "environment": "KALSHI_DEMO",
            "origin": DEMO_ORIGIN,
            "canonical_commit": self.plan.expected_commit,
            "canonical_tree": self.plan.expected_tree,
            "canonical_parent": self.plan.expected_parent,
            "implementation_artifacts": dict(self.plan.implementation_artifacts),
            "subaccount_number": b.subaccount,
            "exchange_index": b.exchange_index,
            "ticker": self.plan.ticker,
            "event_ticker": self.plan.event_ticker,
            "series_ticker": self.plan.series_ticker,
            "source_identities": {name: {"bytes": size, "sha256": sha} for name, (size, sha) in sorted(_an.SOURCE_IDENTITIES.items())},
            "account_class_evidence_state": self.plan.account_class,
            "quantum": _an.canonical_decimal_text(self.plan.quantum) if self.plan.quantum is not None else None,
            "run_started_ns": self.run_started_ns or 0,
            "active_write_deadline_ns": self.active_end_ns or 0,
            "reconciliation_deadline_ns": self.tail_end_ns or ((self.active_end_ns or 0) + RECONCILIATION_TAIL_NS),
            "utc_audit": dict(self.utc_audit),
            "counters": self.ledger.counters_projection(worst_case_bound=self.bound.plan_strict_upper),
            "baseline_reconciliation_identity": self.baseline_identity,
            "final_reconciliation_identity": self.final_identity,
            "account_class_evidence_id": self.plan.account_class_evidence_id,
            "fee_regime_inputs": {
                "fee_epoch_id": self.plan.fee_epoch_id, "fee_type": self.plan.fee_type,
                "fee_schedule_edition": _an.FEE_SCHEDULE_EDITION,
                "taker_multiplier": _an.canonical_decimal_text(self.plan.taker_multiplier),
                "maker_multiplier": _an.canonical_decimal_text(self.plan.maker_multiplier),
                "provenance": "REVIEWED_NONSECRET_EXECUTION_INPUT_VERIFIED_AGAINST_BOUNDED_MARKET_EVIDENCE_WHERE_EXPOSED",
            },
            "orders": [dict(o.shared_projection(), observed_fill_fees=self._observed_fill_fee_records(o)) for o in self.orders],
            "cash_fee_intervals": [rec for rec in (self._interval_record("I1", "B0", "B1"), self._interval_record("I2", "B1", "B2"))
                                   if rec is not None],
            "balance_observations": [cp.shared_projection() for cp in self.checkpoints.values()],
            "read_observations": list(self.read_observations),
            "question_results": list(questions),
            "halt": None if self.halt is None else {"code": self.halt.code.value, "state_history": list(self.machine.history)},
            "process_instance_id": self._base_runtime.normal_gate.process_instance_id,
            "domain_binding_id": b.binding_id,
            "domain_binding_sha256": b.binding_sha256,
            "run_claim": {"claim_schema": RUN_CLAIM_SCHEMA, "claim_sha256": self.run_claim_sha256,
                          "run_folder_name": self.plan.run_id},
        }
        try:
            _an.validate_fee_experiment_run_v1(record)
        except _an.F03AnalyzerError as exc:
            raise F03Halt(HaltCode.EVIDENCE_SANITIZATION_FAILED, exc.code) from None
        acquired = _an.canonical_decimal_text(self.ledger.acquired_quantity)
        return F03RunResultV1(
            final_state=self.machine.state.value, halt=self.halt, shared_record=record, question_results=questions,
            unresolved_active_exposure=self.unresolved_active_exposure,
            remaining_inventory_note=f"USER_HELD_DEMO_POSITION_ACQUIRED={acquired}; NO_SELL_OR_FLATTEN_PERFORMED",
        )


def _seconds(ns: int):
    from datetime import timedelta
    return timedelta(microseconds=ns // 1000)


__all__: list[str] = []
