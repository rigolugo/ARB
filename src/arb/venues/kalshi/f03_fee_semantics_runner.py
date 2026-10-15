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
import re
import stat
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence, Tuple

import arb.venues.kalshi.minimal_market_maker_experiment_runner as _runner
from arb.execution_ledger import LedgerError, canonical_json_bytes, canonical_timestamp, end_writer_session, sha256_hex
from arb.venues.kalshi import f03_fee_semantics_analyzer as _an
from arb.venues.kalshi.ledger_binding import ActiveAuthorizationConsumptionV1, active_domain_commitment
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
    __slots__ = ("_inner", "_ledger", "_phase", "_route_a")

    def __init__(self, inner: Callable[..., object], ledger: F03BudgetLedgerV1) -> None:
        if not callable(inner):
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "read transport")
        self._inner = inner
        self._ledger = ledger
        self._phase = "UNSET"
        self._route_a = None

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def __call__(self, operation, prepared, deadline):
        if operation in _runner.WRITE_OPERATIONS:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "write operation on read transport")
        name = getattr(operation, "value", str(operation))
        # Route A (RA-02-005/007): the physical-start gate runs BEFORE the
        # charge, so a refused start is zero sends and zero quota.
        started = None if self._route_a is None else self._route_a._ra_before_read(name)
        self._ledger.charge_get(name, phase=self._phase)
        result = self._inner(operation, prepared, deadline)
        if started is not None:
            self._route_a._ra_after_read(name, started)
        return result


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
        route_a = self._transport._route_a
        started = None if route_a is None else route_a._ra_before_read("GET_MARKET_ORDERBOOK")
        self._ledger.charge_get("GET_MARKET_ORDERBOOK", phase=self._transport._phase)
        result = self._inner.execute(plan, deadline)
        if started is not None:
            route_a._ra_after_read("GET_MARKET_ORDERBOOK", started)
        return result


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
    send_gate: Callable[[str], None] | None = None,
) -> F03WriteOutcomeV1:
    """Reproduces the ``_gate_d_execute_create`` consumer sequence with only
    the bounded body delta: assessment -> scoped permit -> T1/T2/T3 -> charge
    at durable T3 -> freshness -> final active-domain equality -> trusted-T2
    binding -> the one adapter call -> protected classifier -> bounded
    authoritative post-CREATE reconciliation.  ``send_gate`` (Route A only)
    is the immediately-pre-adapter deadline gate: a refusal after the durable
    T3 is zero physical sends with the T3 slot consumed (never refunded)."""
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
    if send_gate is not None:
        try:
            send_gate("CREATE")
        except F03Halt as exc:
            return _out("FRESHNESS_EXPIRED_BEFORE_ADAPTER", charged=True, invoked=False, detail="ROUTE_A_DEADLINE: " + exc.detail, permit=permit)
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
    send_gate: Callable[[str], None] | None = None,
) -> F03WriteOutcomeV1:
    """Reproduces the ``_gate_d_execute_cancel`` sequence with the active
    pure T2 builder.  Only the exact proven-active F03 order is a target.
    ``send_gate`` is the Route-A immediately-pre-adapter deadline gate."""
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
    if send_gate is not None:
        try:
            send_gate("CANCEL")
        except F03Halt as exc:
            return _out("FRESHNESS_EXPIRED_BEFORE_ADAPTER", charged=True, invoked=False, detail="ROUTE_A_DEADLINE: " + exc.detail, permit=permit)
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
# Route A CORRECTION_01 (RA-02 / RA-03 / RA-04 / RA-08) -- support for the
# sanctioned protected F03 consumer of ``run_f03_release_orchestration_v1``.
#
# Nothing here selects a timing value.  The accepted reserve-policy registry
# below is EMPTY: every production profile is therefore
# ROUTE_A_FEASIBILITY_UNPROVEN and the protected entry stops before the
# durable authorization consumption.  A timing profile is data, never an
# authorization, receipt, signer, domain choice or writer proof.
# ---------------------------------------------------------------------------

ROUTE_A_TIMING_SCHEMA = "F03_ROUTE_A_TIMING_CONFIG_V1"
ROUTE_A_ROUTE = "ROUTE_A_300S"
ROUTE_A_FEASIBILITY_UNPROVEN = "ROUTE_A_FEASIBILITY_UNPROVEN"
ROUTE_A_PROFILE_INVALID = "ROUTE_A_PROFILE_INVALID"
ROUTE_A_PLAN_BINDING_SCHEMA = "F03_ROUTE_A_PLAN_BINDING_V1"
ROUTE_A_AUTHORIZATION_NS = 300 * 1_000_000_000
ROUTE_A_REQUEST_BOUND_NS = _runner.OPERATION_DEADLINE_MS * 1_000_000  # inherited <=10 s per request
ROUTE_A_TAIL_MAX_NS = RECONCILIATION_TAIL_NS  # R never exceeds the controlling F03 120 s maximum
ROUTE_A_TIMEOUT_KEYS = ("stage3_read", "market_read", "balance_read", "order_read", "fills_read",
                        "positions_read", "orderbook_read", "create", "cancel")
ROUTE_A_POLL_KEYS = ("order_status", "fills", "balance_checkpoint")
_ROUTE_A_TOP_KEYS = frozenset({
    "schema", "route", "requested_active_seconds", "reconciliation_tail_seconds",
    "per_operation_timeout_seconds", "poll_interval_seconds", "reserve_policy_id",
    "calibration_evidence_ref", "approved_profile_sha256",
})
_ROUTE_A_SECONDS_RE = re.compile(r"(0|[1-9][0-9]{0,3})(\.[0-9]{1,9})?")
_ROUTE_A_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_ROUTE_A_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_ROUTE_A_READ_TIMEOUT_KEY = MappingProxyType({
    "GET_MARKET": "market_read", "GET_BALANCE": "balance_read", "GET_ORDER": "order_read",
    "GET_ORDERS": "order_read", "GET_FILLS": "fills_read", "GET_POSITIONS": "positions_read",
    "GET_MARKET_ORDERBOOK": "orderbook_read",
})
OPERATOR_ATTEMPT_FILE_NAME = "OPERATOR_ATTEMPT_V1.json"
OPERATOR_ATTEMPT_SCHEMA = "F03_OPERATOR_ATTEMPT_V1"


class F03RouteATimingError(Exception):
    """Closed Route-A profile rejection.  ``classification`` is
    ``ROUTE_A_FEASIBILITY_UNPROVEN`` (no accepted executable schedule) or
    ``ROUTE_A_PROFILE_INVALID`` (malformed, tampered or out-of-bound bytes)."""

    def __init__(self, classification: str, detail: str) -> None:
        if classification not in (ROUTE_A_FEASIBILITY_UNPROVEN, ROUTE_A_PROFILE_INVALID):
            raise TypeError("closed route-A classification required")
        self.classification = classification
        self.detail = detail
        super().__init__(f"{classification}: {detail}")


def _route_a_invalid(detail: str) -> F03RouteATimingError:
    return F03RouteATimingError(ROUTE_A_PROFILE_INVALID, detail)


def _route_a_unproven(detail: str) -> F03RouteATimingError:
    return F03RouteATimingError(ROUTE_A_FEASIBILITY_UNPROVEN, detail)


def _route_a_seconds_ns(value: object, name: str) -> int | None:
    """``null`` -> ``None`` (UNSELECTED, never zero).  Otherwise an exact
    canonical positive decimal STRING of seconds (<=9 fractional digits, no
    sign / exponent / whitespace / unit) converted to integer nanoseconds."""
    if value is None:
        return None
    if type(value) is not str or _ROUTE_A_SECONDS_RE.fullmatch(value) is None:
        raise _route_a_invalid(name)
    whole, _, fraction = value.partition(".")
    nanoseconds = int(whole) * 1_000_000_000 + int(fraction.ljust(9, "0") or "0")
    if nanoseconds <= 0:
        raise _route_a_invalid(name + " must be positive")
    return nanoseconds


def _route_a_closed_seconds(value: object, keys: Tuple[str, ...], name: str) -> Mapping[str, int | None]:
    if type(value) is not dict or set(value) != set(keys):
        raise _route_a_invalid(name + " keys")
    return MappingProxyType({key: _route_a_seconds_ns(value[key], f"{name}.{key}") for key in keys})


@dataclass(frozen=True, slots=True)
class F03RouteATimingConfigV1:
    """Strictly parsed, immutable ``F03_ROUTE_A_TIMING_CONFIG_V1`` profile
    proposal.  ``None`` values are UNSELECTED; the profile is executable only
    when no runtime-required value is UNSELECTED."""

    raw_sha256: str
    raw_bytes: int
    semantic_sha256: str
    active_ns: int | None
    tail_ns: int | None
    timeouts_ns: Mapping[str, int | None]
    polls_ns: Mapping[str, int | None]
    reserve_policy_id: str | None
    calibration_evidence_ref: Mapping[str, str] | None
    approved_profile_sha256: str | None

    @property
    def unselected_fields(self) -> Tuple[str, ...]:
        missing = [name for name, value in (
            ("requested_active_seconds", self.active_ns), ("reconciliation_tail_seconds", self.tail_ns),
            ("reserve_policy_id", self.reserve_policy_id), ("calibration_evidence_ref", self.calibration_evidence_ref),
            ("approved_profile_sha256", self.approved_profile_sha256)) if value is None]
        missing += [f"per_operation_timeout_seconds.{k}" for k in ROUTE_A_TIMEOUT_KEYS if self.timeouts_ns[k] is None]
        missing += [f"poll_interval_seconds.{k}" for k in ROUTE_A_POLL_KEYS if self.polls_ns[k] is None]
        return tuple(missing)

    @property
    def executable(self) -> bool:
        return not self.unselected_fields


def parse_route_a_timing_config_v1(raw: bytes) -> F03RouteATimingConfigV1:
    """RA-03-001/002 strict decoder: UTF-8 without BOM; duplicate keys at any
    depth, unknown/missing keys, numeric JSON values (all precision fields are
    strings), non-finite constants, booleans or nested shapes other than the
    closed objects are rejected.  No default exists for any value."""
    if type(raw) is not bytes or not raw:
        raise _route_a_invalid("bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise _route_a_invalid("byte-order mark")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _route_a_invalid("utf-8") from None

    def _pairs(pairs):
        seen: dict = {}
        for key, value in pairs:
            if key in seen:
                raise _route_a_invalid("duplicate key")
            seen[key] = value
        return seen

    def _reject_number(_token):
        raise _route_a_invalid("numeric JSON value")

    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_float=_reject_number,
                              parse_int=_reject_number, parse_constant=_reject_number)
    except F03RouteATimingError:
        raise
    except ValueError:
        raise _route_a_invalid("malformed JSON") from None
    if type(document) is not dict or set(document) != _ROUTE_A_TOP_KEYS:
        raise _route_a_invalid("top-level keys")
    if document["schema"] != ROUTE_A_TIMING_SCHEMA or document["route"] != ROUTE_A_ROUTE:
        raise _route_a_invalid("schema/route")
    active = _route_a_seconds_ns(document["requested_active_seconds"], "requested_active_seconds")
    tail = _route_a_seconds_ns(document["reconciliation_tail_seconds"], "reconciliation_tail_seconds")
    timeouts = _route_a_closed_seconds(document["per_operation_timeout_seconds"], ROUTE_A_TIMEOUT_KEYS,
                                       "per_operation_timeout_seconds")
    polls = _route_a_closed_seconds(document["poll_interval_seconds"], ROUTE_A_POLL_KEYS, "poll_interval_seconds")
    policy_id = document["reserve_policy_id"]
    if policy_id is not None and (type(policy_id) is not str or _ROUTE_A_IDENTIFIER_RE.fullmatch(policy_id) is None):
        raise _route_a_invalid("reserve_policy_id")
    evidence = document["calibration_evidence_ref"]
    if evidence is not None:
        if (
            type(evidence) is not dict or set(evidence) != {"sha256", "schema", "environment_scope"}
            or type(evidence["sha256"]) is not str or _ROUTE_A_HEX64_RE.fullmatch(evidence["sha256"]) is None
            or type(evidence["schema"]) is not str or _ROUTE_A_IDENTIFIER_RE.fullmatch(evidence["schema"]) is None
            or evidence["environment_scope"] != "KALSHI_DEMO"
        ):
            raise _route_a_invalid("calibration_evidence_ref")
        evidence = MappingProxyType(dict(evidence))
    approved = document["approved_profile_sha256"]
    if approved is not None and (type(approved) is not str or _ROUTE_A_HEX64_RE.fullmatch(approved) is None):
        raise _route_a_invalid("approved_profile_sha256")
    semantic = sha256_hex(canonical_json_bytes({k: v for k, v in document.items() if k != "approved_profile_sha256"}))
    return F03RouteATimingConfigV1(
        raw_sha256=sha256_hex(raw), raw_bytes=len(raw), semantic_sha256=semantic, active_ns=active, tail_ns=tail,
        timeouts_ns=timeouts, polls_ns=polls, reserve_policy_id=policy_id, calibration_evidence_ref=evidence,
        approved_profile_sha256=approved,
    )


@dataclass(frozen=True, slots=True)
class F03RouteAReservePolicyV1:
    """A separately ACCEPTED bounded timing policy (RA-03-003 (d)): the exact
    profile it admits, its calibration evidence, its ceilings and the
    conservative reserves ``C`` (local closure), ``H`` (slack), ``Q`` (mandatory
    remaining protected reads / reconciliation / evidence) and ``W`` (worst-case
    exact CANCEL path after a CREATE).  It can only lower, never raise, the
    protected 300 s / <=10 s / count / economic ceilings."""

    policy_id: str
    approved_profile_sha256: str
    profile_semantic_sha256: str
    calibration_evidence_sha256: str
    max_active_ns: int
    max_tail_ns: int
    local_closure_reserve_ns: int
    slack_ns: int
    mandatory_read_reserve_ns: int
    write_cancel_reserve_ns: int

    def __post_init__(self) -> None:
        if type(self.policy_id) is not str or _ROUTE_A_IDENTIFIER_RE.fullmatch(self.policy_id) is None:
            raise _route_a_invalid("policy id")
        for name in ("approved_profile_sha256", "profile_semantic_sha256", "calibration_evidence_sha256"):
            value = getattr(self, name)
            if type(value) is not str or _ROUTE_A_HEX64_RE.fullmatch(value) is None:
                raise _route_a_invalid("policy " + name)
        for name in ("max_active_ns", "max_tail_ns", "local_closure_reserve_ns", "mandatory_read_reserve_ns",
                     "write_cancel_reserve_ns"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise _route_a_invalid("policy " + name)
        if type(self.slack_ns) is not int or self.slack_ns < 0:
            raise _route_a_invalid("policy slack_ns")
        if self.max_tail_ns > ROUTE_A_TAIL_MAX_NS or self.max_active_ns >= ROUTE_A_AUTHORIZATION_NS:
            raise _route_a_invalid("policy ceilings exceed the protected bounds")


# RA-06/RA-07: NO reserve policy has been accepted.  The registry is
# intentionally empty and immutable; a policy can only be added by a
# separately reviewed source change bound to accepted calibration evidence.
_ROUTE_A_ACCEPTED_RESERVE_POLICIES: Mapping[str, F03RouteAReservePolicyV1] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class F03RouteAScheduleV1:
    """The admitted (policy-bound) Route-A schedule; integer nanoseconds."""

    profile_raw_sha256: str
    profile_raw_bytes: int
    profile_semantic_sha256: str
    policy_id: str
    active_ns: int
    tail_ns: int
    closure_ns: int
    slack_ns: int
    mandatory_read_ns: int
    write_cancel_ns: int
    timeouts_ns: Mapping[str, int]
    polls_ns: Mapping[str, int]


def admit_route_a_timing_profile_v1(raw: bytes, *, expected_bytes: int, expected_sha256: str) -> F03RouteAScheduleV1:
    """RA-02-003/004, RA-03, RA-07: exact authorized bytes -> strict profile
    -> accepted reserve policy -> nominal fit inside the 300 s authorization.
    Any absent or unaccepted bound is ROUTE_A_FEASIBILITY_UNPROVEN."""
    if type(raw) is not bytes or len(raw) != expected_bytes or sha256_hex(raw) != expected_sha256:
        raise _route_a_invalid("timing profile bytes/sha differ from the authorized identity")
    config = parse_route_a_timing_config_v1(raw)
    if not config.executable:
        raise _route_a_unproven("UNSELECTED: " + ",".join(config.unselected_fields))
    policy = _ROUTE_A_ACCEPTED_RESERVE_POLICIES.get(config.reserve_policy_id)
    if type(policy) is not F03RouteAReservePolicyV1 or policy.policy_id != config.reserve_policy_id:
        raise _route_a_unproven("no accepted reserve policy for the profile")
    if (
        policy.approved_profile_sha256 != config.approved_profile_sha256
        or policy.profile_semantic_sha256 != config.semantic_sha256
        or policy.calibration_evidence_sha256 != config.calibration_evidence_ref["sha256"]
    ):
        raise _route_a_unproven("profile is not the one bound by the accepted policy")
    if any(value > ROUTE_A_REQUEST_BOUND_NS for value in config.timeouts_ns.values()):
        raise _route_a_invalid("per-operation timeout above the inherited 10 s request bound")
    if config.active_ns > policy.max_active_ns or config.tail_ns > policy.max_tail_ns or config.tail_ns > ROUTE_A_TAIL_MAX_NS:
        raise _route_a_invalid("profile exceeds the accepted policy ceilings")
    if any(value > config.tail_ns for value in config.polls_ns.values()):
        raise _route_a_invalid("poll interval exceeds the reconciliation tail")
    if config.tail_ns < policy.mandatory_read_reserve_ns:
        raise _route_a_unproven("R does not cover the mandatory tail reserve Q")
    if (config.active_ns + config.tail_ns + policy.local_closure_reserve_ns + policy.slack_ns
            >= ROUTE_A_AUTHORIZATION_NS):
        raise _route_a_unproven("A+R+C+H does not fit inside the 300 s authorization")
    return F03RouteAScheduleV1(
        profile_raw_sha256=config.raw_sha256, profile_raw_bytes=config.raw_bytes,
        profile_semantic_sha256=config.semantic_sha256, policy_id=policy.policy_id,
        active_ns=config.active_ns, tail_ns=config.tail_ns, closure_ns=policy.local_closure_reserve_ns,
        slack_ns=policy.slack_ns, mandatory_read_ns=policy.mandatory_read_reserve_ns,
        write_cancel_ns=policy.write_cancel_reserve_ns, timeouts_ns=config.timeouts_ns, polls_ns=config.polls_ns,
    )


def route_a_active_end_ns(*, tw_ns: int, ta_ns: int, schedule: F03RouteAScheduleV1) -> int:
    """RA-02-004: computed ONCE at the writer admission instant ``TW``."""
    return min(tw_ns + schedule.active_ns, ta_ns - schedule.tail_ns - schedule.closure_ns - schedule.slack_ns)


def route_a_tail_cap_ns(*, active_end_ns: int, first_event_ns: int, ta_ns: int, schedule: F03RouteAScheduleV1) -> int:
    """RA-F01: ``min(Tactive_end+R, Tfirst_halt_or_close+R, TA-C-H)`` -- an
    upper cap only; it never grants a signed read by itself."""
    return min(active_end_ns + schedule.tail_ns, first_event_ns + schedule.tail_ns,
               ta_ns - schedule.closure_ns - schedule.slack_ns)


def route_a_start_permitted(*, now_ns: int, cap_ns: int, ta_ns: int, attempt_ns: int) -> bool:
    """RA-02-005/007 physical-start predicate: strictly before the effective
    cap AND before TA, with a complete accepted attempt still fitting."""
    return now_ns < cap_ns and now_ns < ta_ns and cap_ns - now_ns >= attempt_ns


def route_a_plan_binding_sha256(plan: "F03RunPlanV1") -> str:
    """The complete nonsecret F03 plan identity the authorization binds."""
    if type(plan) is not F03RunPlanV1:
        raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, "plan type")
    values: dict = {"schema": ROUTE_A_PLAN_BINDING_SCHEMA}
    for item in dataclasses.fields(F03RunPlanV1):
        value = getattr(plan, item.name)
        if type(value) is Decimal:
            value = _an.canonical_decimal_text(value)
        elif isinstance(value, Mapping):
            value = dict(sorted(value.items()))
        values[item.name] = value
    return sha256_hex(canonical_json_bytes(values))


# ---------------------------------------------------------------------------
# Stage B SB-IN-001..003 (and the pure part of SB-IN-004) -- DRAFT-ONLY closed
# ``F03OperatorRuntimeInputsV1`` decoding and immutable raw-to-plan derivation.
#
# Pure: the decoder takes immutable raw bytes plus caller-supplied
# COMPARISON-ONLY pins (raw length/SHA-256 and the expected participating-source
# path -> SHA-256 map) as explicit data.  It performs no filesystem, Git,
# native, evidence-source, credential or transport access and accepts no
# callable.  A draft establishes exact shape/lexical/type/integrity comparisons
# only; it never establishes source freshness, reviewer authenticity, history
# completeness, observation, physical identity, custody, current tip,
# eligibility or terminal-credit exclusion, and it never creates an
# ``F03ObservedIdentityV1``.  Caller pins do not show that a reviewer approved
# them.  Nothing here is called by orchestration or by any runner consumer; the
# Stage A pre-row-9 N1 hold and the post-marker link stop are unchanged.
# ---------------------------------------------------------------------------

F03_OPERATOR_INPUTS_SCHEMA = "F03OperatorRuntimeInputsV1"
F03_INPUTS_DRAFT_SCHEMA_INVALID = "F03_INPUTS_DRAFT_SCHEMA_INVALID"
F03_INPUTS_DRAFT_PIN_MISMATCH = "F03_INPUTS_DRAFT_PIN_MISMATCH"
# Draft terminal-credit reference dispositions (descriptions, never grants).
F03_INPUTS_TERMINAL_CREDIT_PAIRED_NULL = "PAIRED_NULL_NO_EXCLUSION_EVIDENCE_SUPPLIED"
F03_INPUTS_TERMINAL_CREDIT_UNVERIFIED_REF = "UNVERIFIED_DRAFT_REFERENCE_NOT_EXCLUSION_PROOF"
# SB-IN-002 resource caps.  A legitimate input above any cap needs a separate
# versioned limit review; nothing is truncated or normalized.
F03_INPUTS_RAW_MAX_BYTES = 1_048_576
_F03_INPUTS_STRING_MAX_BYTES = 4_096
_F03_INPUTS_REF_ID_MAX_BYTES = 256
_F03_INPUTS_MAP_MAX_ENTRIES = 256
# Parser resource bound for artifact-ref ``bytes`` (NOT an enrollment or
# evidence waiver): 1 .. 2**30.  Every supplied predecessor/evidence artifact
# is far below it (the largest is under 80 MB).  JSON integer tokens are
# refused before ``int`` conversion unless they are canonical and at most 10
# digits.
_F03_INPUTS_REF_BYTES_MAX = 1 << 30
_F03_INPUTS_INT_TOKEN_RE = re.compile(r"0|[1-9][0-9]{0,9}")
_F03_INPUTS_GIT_RE = re.compile(r"[0-9a-f]{40}")
_F03_INPUTS_PRICE_RE = re.compile(r"(0|[1-9][0-9]*)\.[0-9]{4}")
_F03_INPUTS_DECIMAL_RE = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")
_F03_INPUTS_PATH_RE = re.compile(r"[A-Za-z0-9_.-]{1,255}(/[A-Za-z0-9_.-]{1,255})*")
_F03_INPUTS_EVIDENCE_REF_KEYS = ("market", "account_class", "fee_epoch", "fee_source", "risk", "domain",
                                 "source_snapshot", "timing", "operator_selection", "terminal_credit")
_F03_INPUTS_SCOPE_SHA256_KEYS = ("domain_binding_sha256", "active_contract_sha256", "risk_config_sha256",
                                 "fee_source_binding_sha256", "timing_profile_sha256")
_F03_INPUTS_SCOPE_CONSTANTS = MappingProxyType({
    "environment": "KALSHI_DEMO", "origin": DEMO_ORIGIN,
    "authority_namespace_id": "ARB_KALSHI_DEMO_PRIMARY_AUTHORITY_V1", "route": ROUTE_A_ROUTE,
    "canonical_strategy_G": "NOT_APPLICABLE_TO_ISOLATED_F03_PROBE",
})
_F03_INPUTS_KEYS = MappingProxyType({
    "root": frozenset({"schema", "run", "market", "fee", "orders", "implementation", "source_and_scope",
                       "evidence_refs"}),
    "run": frozenset({"run_id", "private_evidence_permission"}),
    "market": frozenset({"ticker", "event_ticker", "series_ticker", "market_metadata_evidence_id"}),
    "fee": frozenset({"account_class", "account_class_evidence_id", "fee_epoch_id", "fee_type", "taker_multiplier",
                      "maker_multiplier", "fee_regime_change_pending", "terminal_credit_exclusion_evidence_id"}),
    "orders": frozenset({"order1_limit_price", "order2_limit_price", "planned_order_count"}),
    "implementation": frozenset({"expected_commit", "expected_tree", "expected_parent", "implementation_artifacts"}),
    "source_and_scope": frozenset({"subaccount", "exchange_index", *_F03_INPUTS_SCOPE_CONSTANTS,
                                   *_F03_INPUTS_SCOPE_SHA256_KEYS}),
    "evidence_refs": frozenset(_F03_INPUTS_EVIDENCE_REF_KEYS),
    "artifact_ref": frozenset({"logical_id", "bytes", "sha256"}),
})


class F03OperatorInputsDraftError(Exception):
    """Closed draft-decoder refusal.  ``classification`` is
    ``F03_INPUTS_DRAFT_SCHEMA_INVALID`` (malformed, noncanonical, out-of-domain
    or inconsistent input) or ``F03_INPUTS_DRAFT_PIN_MISMATCH`` (malformed
    comparison pins, raw length/SHA-256 or participating-source mismatch)."""

    def __init__(self, classification: str, detail: str) -> None:
        if classification not in (F03_INPUTS_DRAFT_SCHEMA_INVALID, F03_INPUTS_DRAFT_PIN_MISMATCH):
            raise TypeError("closed draft-input classification required")
        self.classification = classification
        self.detail = detail
        super().__init__(f"{classification}: {detail}")


def _f03_inputs_invalid(detail: str) -> F03OperatorInputsDraftError:
    return F03OperatorInputsDraftError(F03_INPUTS_DRAFT_SCHEMA_INVALID, detail)


def _f03_inputs_pin_mismatch(detail: str) -> F03OperatorInputsDraftError:
    return F03OperatorInputsDraftError(F03_INPUTS_DRAFT_PIN_MISMATCH, detail)


def _f03_inputs_object(value: object, kind: str, name: str) -> dict:
    if type(value) is not dict:
        raise _f03_inputs_invalid(name + " must be an object")
    if set(value) != _F03_INPUTS_KEYS[kind]:
        raise _f03_inputs_invalid(name + " keys")
    return value


def _f03_inputs_text(value: object, name: str, pattern: "re.Pattern[str]",
                     max_bytes: int = _F03_INPUTS_STRING_MAX_BYTES) -> str:
    if type(value) is not str:
        raise _f03_inputs_invalid(name + " must be a string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise _f03_inputs_invalid(name + " utf-8") from None
    if size > max_bytes or pattern.fullmatch(value) is None:
        raise _f03_inputs_invalid(name)
    return value


def _f03_inputs_identifier(value: object, name: str) -> str:
    # Existing Route-A nonsecret identifier grammar (<=128 bytes) inside the
    # SB-IN-002 256-byte evidence-id cap.
    return _f03_inputs_text(value, name, _ROUTE_A_IDENTIFIER_RE, _F03_INPUTS_REF_ID_MAX_BYTES)


def _f03_inputs_repository_path(value: object, name: str) -> str:
    """Canonical repository-relative forward-slash path: no drive, absolute,
    device, backslash, empty, ``.``/``..`` or trailing-dot component; never
    normalized."""
    path = _f03_inputs_text(value, name, _F03_INPUTS_PATH_RE)
    if any(component.endswith(".") for component in path.split("/")):
        raise _f03_inputs_invalid(name + " path component")
    return path


def _f03_inputs_limit_price(value: object, name: str) -> Decimal:
    price = Decimal(_f03_inputs_text(value, name, _F03_INPUTS_PRICE_RE))
    if not (Decimal("0") < price <= _an.MAX_LIMIT_PRICE) or price.as_tuple().exponent != -4:
        raise _f03_inputs_invalid(name + " must be exact 4dp in (0, .8000]")
    return price


def _f03_inputs_maker_multiplier(value: object) -> Decimal:
    text = _f03_inputs_text(value, "fee.maker_multiplier", _F03_INPUTS_DECIMAL_RE)
    with localcontext() as context:
        context.prec = max(50, len(text) + 2)
        multiplier = Decimal(text)
        if not (Decimal("0") < multiplier <= Decimal("1")) or _an.canonical_decimal_text(multiplier) != text:
            raise _f03_inputs_invalid("fee.maker_multiplier must be canonical decimal text in (0, 1]")
    return multiplier


def _f03_inputs_integer(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not (low <= value <= high):
        raise _f03_inputs_invalid(name)
    return value


def _f03_inputs_artifact_ref(value: object, name: str) -> dict:
    ref = _f03_inputs_object(value, "artifact_ref", name)
    _f03_inputs_identifier(ref["logical_id"], name + ".logical_id")
    _f03_inputs_integer(ref["bytes"], name + ".bytes", 1, _F03_INPUTS_REF_BYTES_MAX)
    _f03_inputs_text(ref["sha256"], name + ".sha256", _an._HEX64_RE)
    return ref


def _f03_inputs_expected_sources(value: object) -> dict:
    """Defensive copy and validation of the caller's comparison-only
    participating-source pins (path -> SHA-256)."""
    if not isinstance(value, Mapping):
        raise _f03_inputs_pin_mismatch("expected participating sources must be a mapping")
    pins = dict(value.items())
    if not 1 <= len(pins) <= _F03_INPUTS_MAP_MAX_ENTRIES:
        raise _f03_inputs_pin_mismatch("expected participating source count")
    folded: set = set()
    for path, digest in pins.items():
        try:
            _f03_inputs_repository_path(path, "expected participating source")
            _f03_inputs_text(digest, "expected participating source sha256", _an._HEX64_RE)
        except F03OperatorInputsDraftError as exc:
            raise _f03_inputs_pin_mismatch(exc.detail) from None
        if path.casefold() in folded:
            raise _f03_inputs_pin_mismatch("expected participating sources contain a case alias")
        folded.add(path.casefold())
    return pins


def _f03_inputs_decode(raw: bytes) -> object:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise _f03_inputs_invalid("byte-order mark")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _f03_inputs_invalid("utf-8") from None

    def _pairs(pairs):
        if len(pairs) > _F03_INPUTS_MAP_MAX_ENTRIES:
            raise _f03_inputs_invalid("object entry count")
        seen: dict = {}
        for key, value in pairs:
            if key in seen:
                raise _f03_inputs_invalid("duplicate key")
            seen[key] = value
        return seen

    def _integer(token):
        if _F03_INPUTS_INT_TOKEN_RE.fullmatch(token) is None:
            raise _f03_inputs_invalid("integer token")
        return int(token)

    def _reject(_token):
        raise _f03_inputs_invalid("numeric JSON float or non-finite constant")

    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_float=_reject, parse_int=_integer,
                              parse_constant=_reject)
    except F03OperatorInputsDraftError:
        raise
    except (ValueError, RecursionError):
        raise _f03_inputs_invalid("malformed JSON") from None
    try:
        canonical = canonical_json_bytes(document)
    except LedgerError:
        raise _f03_inputs_invalid("canonical encoding") from None
    except RecursionError:
        # B-01: nesting that decodes but exceeds the recursive canonicalizer is
        # the same closed refusal (no schema permits such nesting).
        raise _f03_inputs_invalid("canonical encoding nesting") from None
    if canonical != raw:
        raise _f03_inputs_invalid("raw bytes are not canonical_json_bytes(parsed)")
    return document


def _f03_inputs_freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _f03_inputs_freeze(child) for key, child in value.items()})
    return value


@dataclass(frozen=True, slots=True)
class F03OperatorRuntimeInputsDraftV1:
    """DRAFT-ONLY structurally parsed ``F03OperatorRuntimeInputsV1``: the one
    immutable raw snapshot, its exact length/SHA-256, recursively frozen parsed
    fields, the exact SB-IN-003 derived plan and its complete
    ``route_a_plan_binding_sha256``.  It is not an admission, eligibility,
    observation or proof object, carries no executable flag and is consumed by
    no runtime path.  A nonnull terminal-credit reference remains an
    unverified draft reference, never independent exclusion evidence."""

    raw: bytes = field(repr=False)
    raw_sha256: str
    raw_bytes: int
    fields: Mapping[str, object] = field(repr=False)
    plan: F03RunPlanV1
    plan_binding_sha256: str
    terminal_credit_reference: str


def parse_f03_operator_runtime_inputs_draft_v1(
    raw: bytes, *, expected_raw_bytes: int, expected_raw_sha256: str,
    expected_participating_sources: Mapping[str, str],
) -> F03OperatorRuntimeInputsDraftV1:
    """SB-IN-001/002 closed strict decoder and SB-IN-003 exact plan mapping
    (pure; draft only).  UTF-8 without BOM; ``raw`` must equal
    ``canonical_json_bytes(parsed)`` byte for byte; duplicate/unknown/absent
    keys at every level, JSON floats, non-finite constants, noncanonical or
    overlong integers, bool in integer slots and any null outside the three
    permitted slots are refused.  Every plan field is mapped explicitly (no
    default); ``implementation_artifacts`` must be a sorted subset of the
    caller's expected participating-source pins with identical SHA-256."""
    if type(raw) is not bytes or not raw or len(raw) > F03_INPUTS_RAW_MAX_BYTES:
        raise _f03_inputs_invalid("raw input must be nonempty bytes within the resource cap")
    if (type(expected_raw_bytes) is not int or not 1 <= expected_raw_bytes <= F03_INPUTS_RAW_MAX_BYTES
            or type(expected_raw_sha256) is not str or _an._HEX64_RE.fullmatch(expected_raw_sha256) is None):
        raise _f03_inputs_pin_mismatch("expected raw pins")
    expected_sources = _f03_inputs_expected_sources(expected_participating_sources)
    raw_sha256 = sha256_hex(raw)
    if len(raw) != expected_raw_bytes or raw_sha256 != expected_raw_sha256:
        raise _f03_inputs_pin_mismatch("raw input length/sha256 differ from the expected pins")
    root = _f03_inputs_object(_f03_inputs_decode(raw), "root", "root")
    if root["schema"] != F03_OPERATOR_INPUTS_SCHEMA:
        raise _f03_inputs_invalid("schema")

    run = _f03_inputs_object(root["run"], "run", "run")
    run_id = _f03_inputs_text(run["run_id"], "run.run_id", _an._UUID4_RE)
    if run["private_evidence_permission"] is not False:
        raise _f03_inputs_invalid("run.private_evidence_permission must be false")

    market = _f03_inputs_object(root["market"], "market", "market")
    tickers = {name: _f03_inputs_text(market[name], "market." + name, _runner._TICKER_PATTERN)
               for name in ("ticker", "event_ticker", "series_ticker")}
    _f03_inputs_identifier(market["market_metadata_evidence_id"], "market.market_metadata_evidence_id")

    fee = _f03_inputs_object(root["fee"], "fee", "fee")
    if type(fee["account_class"]) is not str or fee["account_class"] not in tuple(_an.AccountClass):
        raise _f03_inputs_invalid("fee.account_class")
    account_class_evidence_id = _f03_inputs_identifier(fee["account_class_evidence_id"], "fee.account_class_evidence_id")
    fee_epoch_id = _f03_inputs_identifier(fee["fee_epoch_id"], "fee.fee_epoch_id")
    if fee["fee_type"] != "quadratic":
        raise _f03_inputs_invalid("fee.fee_type")
    if fee["taker_multiplier"] != "1":
        raise _f03_inputs_invalid("fee.taker_multiplier must be exactly '1'")
    maker_multiplier = _f03_inputs_maker_multiplier(fee["maker_multiplier"])
    if fee["fee_regime_change_pending"] is not False:
        raise _f03_inputs_invalid("fee.fee_regime_change_pending must be false")
    terminal_id = fee["terminal_credit_exclusion_evidence_id"]
    if terminal_id is not None:
        _f03_inputs_identifier(terminal_id, "fee.terminal_credit_exclusion_evidence_id")

    orders = _f03_inputs_object(root["orders"], "orders", "orders")
    order1 = _f03_inputs_limit_price(orders["order1_limit_price"], "orders.order1_limit_price")
    order2 = (None if orders["order2_limit_price"] is None
              else _f03_inputs_limit_price(orders["order2_limit_price"], "orders.order2_limit_price"))
    planned_order_count = _f03_inputs_integer(orders["planned_order_count"], "orders.planned_order_count", 1, 2)
    if planned_order_count != 1 + int(order2 is not None):
        raise _f03_inputs_invalid("orders.planned_order_count disagrees with order2_limit_price")

    implementation = _f03_inputs_object(root["implementation"], "implementation", "implementation")
    git = {name: _f03_inputs_text(implementation[name], "implementation." + name, _F03_INPUTS_GIT_RE)
           for name in ("expected_commit", "expected_tree", "expected_parent")}
    artifacts = implementation["implementation_artifacts"]
    if type(artifacts) is not dict or not 1 <= len(artifacts) <= _F03_INPUTS_MAP_MAX_ENTRIES:
        raise _f03_inputs_invalid("implementation.implementation_artifacts must be a nonempty bounded map")
    if list(artifacts) != sorted(artifacts):
        raise _f03_inputs_invalid("implementation.implementation_artifacts keys must be sorted")
    for path, digest in artifacts.items():
        _f03_inputs_repository_path(path, "implementation.implementation_artifacts path")
        _f03_inputs_text(digest, "implementation.implementation_artifacts sha256", _an._HEX64_RE)
        if path not in expected_sources:
            raise _f03_inputs_pin_mismatch("implementation artifact is not an expected participating source")
        if expected_sources[path] != digest:
            raise _f03_inputs_pin_mismatch("implementation artifact sha256 differs from the expected pin")

    scope = _f03_inputs_object(root["source_and_scope"], "source_and_scope", "source_and_scope")
    for name, constant in _F03_INPUTS_SCOPE_CONSTANTS.items():
        if scope[name] != constant:
            raise _f03_inputs_invalid("source_and_scope." + name)
    _f03_inputs_integer(scope["subaccount"], "source_and_scope.subaccount", 1, 1)
    _f03_inputs_integer(scope["exchange_index"], "source_and_scope.exchange_index", 0, 0)
    for name in _F03_INPUTS_SCOPE_SHA256_KEYS:
        _f03_inputs_text(scope[name], "source_and_scope." + name, _an._HEX64_RE)

    refs = _f03_inputs_object(root["evidence_refs"], "evidence_refs", "evidence_refs")
    for name in _F03_INPUTS_EVIDENCE_REF_KEYS:
        if name == "terminal_credit" and refs[name] is None:
            continue
        _f03_inputs_artifact_ref(refs[name], "evidence_refs." + name)
    if account_class_evidence_id != refs["account_class"]["logical_id"]:
        raise _f03_inputs_invalid("fee.account_class_evidence_id differs from evidence_refs.account_class")
    terminal_ref = refs["terminal_credit"]
    if (terminal_id is None) != (terminal_ref is None):
        raise _f03_inputs_invalid("terminal-credit exclusion id/ref must be both null or both nonnull")
    if terminal_ref is not None and terminal_ref["logical_id"] != terminal_id:
        raise _f03_inputs_invalid("terminal-credit exclusion id differs from evidence_refs.terminal_credit")

    try:
        plan = F03RunPlanV1(
            run_id=run_id, ticker=tickers["ticker"], event_ticker=tickers["event_ticker"],
            series_ticker=tickers["series_ticker"], account_class=fee["account_class"],
            account_class_evidence_id=account_class_evidence_id, fee_epoch_id=fee_epoch_id, fee_type=fee["fee_type"],
            taker_multiplier=Decimal(fee["taker_multiplier"]), maker_multiplier=maker_multiplier,
            fee_regime_change_pending=fee["fee_regime_change_pending"], order1_limit_price=order1,
            order2_limit_price=order2, expected_commit=git["expected_commit"], expected_tree=git["expected_tree"],
            expected_parent=git["expected_parent"],
            implementation_artifacts=MappingProxyType(dict(sorted(artifacts.items()))),
            terminal_credit_exclusion_evidence_id=terminal_id,
            private_evidence_permission=run["private_evidence_permission"],
        )
    except F03Halt as exc:
        raise _f03_inputs_invalid("plan: " + str(exc)) from None
    if plan.planned_order_count != planned_order_count:
        raise _f03_inputs_invalid("planned order count")
    return F03OperatorRuntimeInputsDraftV1(
        raw=raw, raw_sha256=raw_sha256, raw_bytes=len(raw), fields=_f03_inputs_freeze(root), plan=plan,
        plan_binding_sha256=route_a_plan_binding_sha256(plan),
        terminal_credit_reference=(F03_INPUTS_TERMINAL_CREDIT_PAIRED_NULL if terminal_id is None
                                   else F03_INPUTS_TERMINAL_CREDIT_UNVERIFIED_REF),
    )


# RA-08-001 / RA-IMP-F01: a directory-entry durability primitive is accepted
# ONLY where its documented contract covers the entry.  POSIX ``fsync`` of an
# ``O_RDONLY`` directory descriptor is that documented mechanism.  On Windows
# (``os.name == "nt"``) this POSIX primitive is never proven: ``os.open`` of a
# directory is refused (observed PermissionError/errno 13 on NTFS), so it is
# NEVER assumed there and is never retried as a fallback (WF-09 / WF-14).  The
# native-Windows branch uses only the separate checked directory-handle flush
# component below (RA-08-001-WINDOWS-F03); that component is practical
# Windows/Demo operational flush acceptance, not a durability proof, and in
# Stage A it is unreachable from sanctioned orchestration (pre-row-9 N1 hold).
_ROUTE_A_DIRECTORY_FSYNC_PLATFORM_PROVEN = os.name != "nt"


def _route_a_fsync_directory(path: Path) -> bool:
    """Directory-entry durability primitive.  ``True`` ONLY when the platform
    mechanism is proven AND ``open(dir, O_RDONLY)``, the descriptor is a
    directory, ``fsync`` and ``close`` all completed.  Every failure, refusal,
    exception or unsupported platform is ``False`` -- never assumed durable."""
    if _ROUTE_A_DIRECTORY_FSYNC_PLATFORM_PROVEN is not True:
        return False
    try:
        fd = os.open(path, os.O_RDONLY)
    except Exception:
        return False
    durable = False
    try:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            os.fsync(fd)
            durable = True
    except Exception:
        durable = False
    finally:
        try:
            os.close(fd)
        except Exception:
            durable = False
    return durable


def _route_a_require_directory_entry_durable(path: Path, detail: str) -> None:
    """RA-08-001: halt unless the directory entry is positively durable.  The
    caller has already consumed the run id; an uncertain result is consumed,
    never retried, and no later fsync/readback is accepted as proof of it."""
    try:
        durable = _route_a_fsync_directory(path)
    except Exception:
        durable = False
    if durable is not True:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, detail)


# ---------------------------------------------------------------------------
# R1-D07 F03 Windows storage Stage A (WF-05..WF-11, RA-08-001-WINDOWS-F03).
#
# INCOMPLETE, NON-ADMITTING component.  The sanctioned orchestration stops
# unconditionally before row 9 (F03_N1_HISTORY_CONTEXT_UNAVAILABLE) and, as
# defense in depth, after the attempt marker (N1_ADMISSION_LINK_UNAVAILABLE),
# so this native-Windows sequence is reachable only through deterministic
# synthetic test fixtures.  A successful CreateFileW / FlushFileBuffers /
# CloseHandle sequence is a REQUESTED operating-system flush of the directory
# handle (practical Windows/Demo operational flush acceptance only); it is NOT
# proof that a directory entry survives an OS crash or sudden power loss.
# Pathname ``lstat`` identity checks are non-qualifying consistency
# diagnostics: they do not establish the identity of the opened handle, an
# enrolled host/volume/epoch or no-restore continuity (D-06/D-07 deferred).
# ---------------------------------------------------------------------------

# Branch selection.  The POSIX branch keeps the historical accepted sequence
# unchanged (WF-14); this native branch is never a cross-platform fallback.
_ROUTE_A_NATIVE_WINDOWS = os.name == "nt"

# WF-06 exact CreateFileW parameter set (no other flag, no volume handle, no
# privilege adjustment, no inheritable handle: NULL security attributes).
_WIN32_GENERIC_READ_WRITE = 0xC0000000
_WIN32_FILE_SHARE_READ_WRITE_DELETE = 0x00000007
_WIN32_OPEN_EXISTING = 3
_WIN32_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_WIN32_INVALID_HANDLE_VALUES = frozenset({-1, (1 << 32) - 1, (1 << 64) - 1})

WINDOWS_DIRECTORY_FLUSH_UNSUPPORTED = "WINDOWS_DIRECTORY_FLUSH_UNSUPPORTED"
WINDOWS_DIRECTORY_FLUSH_FAILED = "WINDOWS_DIRECTORY_FLUSH_FAILED"
WINDOWS_DIRECTORY_CLOSE_FAILED = "WINDOWS_DIRECTORY_CLOSE_FAILED"
WINDOWS_STORAGE_IDENTITY_CHANGED = "WINDOWS_STORAGE_IDENTITY_CHANGED"
WINDOWS_READBACK_MISMATCH = "WINDOWS_READBACK_MISMATCH"


class _RouteAWin32DirectoryApiV1:
    """Lazy, module-private native binding of exactly three kernel32 calls.
    Constructed only on native Windows at the moment of a flush; nothing is
    loaded at import time and no caller can supply a production substitute."""

    __slots__ = ("_create", "_flush", "_close", "_last_error")

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("native Windows directory API unavailable on this platform")
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        create.restype = wintypes.HANDLE
        flush = kernel32.FlushFileBuffers
        flush.argtypes = (wintypes.HANDLE,)
        flush.restype = wintypes.BOOL
        close = kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        self._create, self._flush, self._close = create, flush, close
        self._last_error = ctypes.get_last_error

    def CreateFileW(self, name, access, share, security, disposition, flags, template):
        return self._create(name, access, share, security, disposition, flags, template)

    def FlushFileBuffers(self, handle):
        return self._flush(handle)

    def CloseHandle(self, handle):
        return self._close(handle)

    def GetLastError(self):
        return self._last_error()


def _route_a_load_win32_directory_api() -> _RouteAWin32DirectoryApiV1:
    """The ONE production binding point (module-private; tests replace it with
    a recording fake inside a fixture).  No public hook or configuration."""
    return _RouteAWin32DirectoryApiV1()


def _route_a_win32_last_error(api: object) -> object:
    """``GetLastError`` captured immediately after a failing call; an
    unreadable value is recorded, never invented."""
    try:
        value = api.GetLastError()
    except Exception:
        return "UNAVAILABLE"
    return value if type(value) is int else "UNAVAILABLE"


def _route_a_win32_valid_handle(handle: object) -> bool:
    return type(handle) is int and handle != 0 and handle not in _WIN32_INVALID_HANDLE_VALUES


def _route_a_win32_flush_directory(path: Path, *, phase: str, detail_prefix: str, record: list) -> None:
    """WF-06 / WF-11 checked native directory-handle flush of exactly ``path``.

    ``CreateFileW(path, GENERIC_READ|GENERIC_WRITE, FILE_SHARE_READ|WRITE|
    DELETE, NULL, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, NULL)``; a NULL /
    INVALID_HANDLE_VALUE / non-integer handle fails (nothing to close);
    otherwise ``FlushFileBuffers`` exactly once (nonzero required) and
    ``CloseHandle`` exactly once in ``finally`` (nonzero required).  The first
    failure is preserved and a close failure is reported separately, never
    masking it.  No retry, no fallback primitive, no path in the detail."""
    entry = {"phase": phase, "open": None, "flush": None, "close": None,
             "open_last_error": None, "flush_last_error": None, "close_last_error": None}
    record.append(entry)
    try:
        api = _route_a_load_win32_directory_api()
    except Exception:
        entry["open"] = "UNSUPPORTED"
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      f"{detail_prefix}{WINDOWS_DIRECTORY_FLUSH_UNSUPPORTED} phase={phase}") from None
    try:
        handle = api.CreateFileW(str(path), _WIN32_GENERIC_READ_WRITE, _WIN32_FILE_SHARE_READ_WRITE_DELETE, None,
                                 _WIN32_OPEN_EXISTING, _WIN32_FILE_FLAG_BACKUP_SEMANTICS, None)
    except Exception:
        entry["open"] = "EXCEPTION"
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      f"{detail_prefix}{WINDOWS_DIRECTORY_FLUSH_FAILED} phase={phase} api=CreateFileW "
                      f"last_error=EXCEPTION") from None
    if not _route_a_win32_valid_handle(handle):
        entry["open"] = "FAILED"
        entry["open_last_error"] = _route_a_win32_last_error(api)
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      f"{detail_prefix}{WINDOWS_DIRECTORY_FLUSH_FAILED} phase={phase} api=CreateFileW "
                      f"last_error={entry['open_last_error']}")
    entry["open"] = "OK"
    first: str | None = None
    try:
        try:
            flushed = api.FlushFileBuffers(handle)
        except Exception:
            entry["flush"] = "EXCEPTION"
            first = (f"{WINDOWS_DIRECTORY_FLUSH_FAILED} phase={phase} api=FlushFileBuffers "
                     f"last_error=EXCEPTION")
        else:
            if type(flushed) is not int or flushed == 0:
                entry["flush"] = "FAILED"
                entry["flush_last_error"] = _route_a_win32_last_error(api)
                first = (f"{WINDOWS_DIRECTORY_FLUSH_FAILED} phase={phase} api=FlushFileBuffers "
                         f"last_error={entry['flush_last_error']}")
            else:
                entry["flush"] = "OK"
    finally:
        try:
            closed = api.CloseHandle(handle)
        except Exception:
            entry["close"] = "EXCEPTION"
            entry["close_last_error"] = "EXCEPTION"
        else:
            if type(closed) is not int or closed == 0:
                entry["close"] = "FAILED"
                entry["close_last_error"] = _route_a_win32_last_error(api)
            else:
                entry["close"] = "OK"
    close_failure = None
    if entry["close"] != "OK":
        close_failure = (f"{WINDOWS_DIRECTORY_CLOSE_FAILED} phase={phase} api=CloseHandle "
                         f"last_error={entry['close_last_error']}")
    if first is not None:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      detail_prefix + first + ("" if close_failure is None else "; " + close_failure))
    if close_failure is not None:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, detail_prefix + close_failure)


def _route_a_directory_identity(path: Path, *, phase: str, detail_prefix: str) -> Tuple[int, int]:
    """Non-qualifying pathname consistency diagnostic (D-06): ``lstat`` must
    report a real directory that is neither a symlink nor a reparse point;
    returns ``(st_dev, st_ino)`` for pre/post comparison only."""
    try:
        st = os.lstat(path)
    except OSError:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      f"{detail_prefix}{WINDOWS_STORAGE_IDENTITY_CHANGED} phase={phase} directory unavailable") from None
    if (
        not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)
        or getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      f"{detail_prefix}{WINDOWS_STORAGE_IDENTITY_CHANGED} phase={phase} not a plain directory")
    return (st.st_dev, st.st_ino)


def _route_a_write_exclusive_record(path: Path, data: bytes, *, collision_detail: str, write_detail: str) -> None:
    """WF-08 (4)/(5): exclusive create, complete write (short write refused),
    ``flush()``, ``os.fsync()`` while open, then ONE checked ``close()``.  The
    first failure is preserved; a close failure is reported separately.  A
    partially written record is left in place (no truncate/delete/repair)."""
    try:
        handle = open(path, "xb")
    except FileExistsError:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, collision_detail) from None
    except OSError:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, write_detail + " (exclusive create)") from None
    first: str | None = None
    try:
        try:
            written = handle.write(data)
            if type(written) is not int or written != len(data):
                first = "short write"
            else:
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            first = "write/flush/fsync"
    finally:
        close_failed = False
        try:
            handle.close()
        except OSError:
            close_failed = True
    if first is not None:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      f"{write_detail} ({first}{'; close failed' if close_failed else ''})")
    if close_failed:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, write_detail + " (close failed)")


def _route_a_readback_record(path: Path, expected: bytes, *, detail_prefix: str,
                             bound_fields: Mapping[str, object]) -> str:
    """WF-08 exact readback: identical byte length and SHA-256, a strict
    canonical JSON object (duplicate keys / non-integer numbers / constants
    rejected) with exactly the expected closed key set and the bound values.
    Immediate consistency only -- never crash/power-loss survival evidence."""
    mismatch = f"{detail_prefix}{WINDOWS_READBACK_MISMATCH}"
    try:
        raw = path.read_bytes()
    except OSError:
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, mismatch + " readback unavailable") from None
    if len(raw) != len(expected) or sha256_hex(raw) != sha256_hex(expected):
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, mismatch + " byte/hash")

    def _pairs(pairs):
        seen: dict = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("duplicate key")
            seen[key] = value
        return seen

    def _reject(_token):
        raise ValueError("non-integer number")

    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_float=_reject,
                              parse_constant=_reject)
        reference = json.loads(expected.decode("utf-8"))
        canonical = canonical_json_bytes(document) if type(document) is dict else None
    except (UnicodeDecodeError, ValueError, LedgerError):
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, mismatch + " malformed") from None
    if type(document) is not dict or canonical != raw or set(document) != set(reference):
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, mismatch + " noncanonical/closed keys")
    for key, value in bound_fields.items():
        if key not in document or type(document[key]) is not type(value) or document[key] != value:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, mismatch + " bound field " + key)
    return sha256_hex(raw)


def _route_a_require_u_equality(run_id: object, *invocation_ids: object) -> str:
    """NH-04-001 / NH-04-005: ``U`` is one canonical lowercase UUID4 string and
    every identity-bearing invocation value is exactly that typed string -- no
    case folding, trimming, regeneration or alias.  Inequality is a halt."""
    if type(run_id) is not str or _an._UUID4_RE.fullmatch(run_id) is None:
        raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "route-A U is not a canonical lowercase UUID4")
    for value in invocation_ids:
        if type(value) is not str or value != run_id:
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "route-A run/invocation identity U inequality")
    return run_id


class F03ProtectedContextV1:
    """Sealed private carrier between the protected orchestration and its one
    F03 consumer (RA-04-004).  Constructible only with the orchestration's
    module-private key; it carries the LIVE consumed receipt (never serialized
    or recreated), the immutable row-0 ``T0``/``TA`` taken from that receipt,
    the admitted schedule, the authorized plan binding and the G write bound."""

    __slots__ = ("receipt", "process_instance_id", "t0_ns", "ta_ns", "schedule", "plan_binding_sha256",
                 "max_ordinary_write_sends", "receipt_digest")

    def __init__(self, key: object, *, receipt: object, schedule: F03RouteAScheduleV1,
                 plan_binding_sha256: str, max_ordinary_write_sends: int) -> None:
        if key is not _runner._F03_PROTECTED_CONTEXT_KEY:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "direct context construction")
        if type(receipt) is not ActiveAuthorizationConsumptionV1:
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "receipt type")
        t0, ta = receipt.invocation_started_monotonic_ns, receipt.absolute_deadline_monotonic_ns
        if type(t0) is not int or type(ta) is not int or t0 < 0 or ta - t0 != ROUTE_A_AUTHORIZATION_NS:
            raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "receipt T0/TA")
        if type(schedule) is not F03RouteAScheduleV1 or type(plan_binding_sha256) is not str:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "context inputs")
        if type(max_ordinary_write_sends) is not int or max_ordinary_write_sends < 0:
            raise F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "G ordinary write bound")
        for name, value in (
            ("receipt", receipt), ("process_instance_id", receipt.process_instance_id), ("t0_ns", t0), ("ta_ns", ta),
            ("schedule", schedule), ("plan_binding_sha256", plan_binding_sha256),
            ("max_ordinary_write_sends", max_ordinary_write_sends),
            ("receipt_digest", sha256_hex(canonical_json_bytes({
                "consumption_event_id": receipt.consumption_event_id,
                "consumption_event_hash": receipt.consumption_event_hash,
                "consumption_sequence": receipt.consumption_sequence,
                "authorization_set_id": receipt.authorization_set_id}))),
        ):
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("F03ProtectedContextV1 is immutable")

    def __copy__(self):
        raise TypeError("F03ProtectedContextV1 cannot be copied")

    __deepcopy__ = __copy__

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("F03ProtectedContextV1 cannot be serialized")

    def __repr__(self) -> str:
        return "F03ProtectedContextV1(<redacted>)"

    def assert_live(self) -> None:
        try:
            self.receipt.assert_live(process_instance_id=self.process_instance_id)
        except LedgerError:
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "consumption receipt not live") from None


@dataclass(slots=True)
class _F03RouteARunStateV1:
    """Process-local Route-A timing state.  ``first_event_ns`` is latched once
    and never overwritten; every cap only moves earlier."""

    ctx: F03ProtectedContextV1
    t0_ns: int
    ta_ns: int
    tw_ns: int | None = None
    active_end_ns: int | None = None
    first_event_ns: int | None = None
    first_event_kind: str | None = None
    tail_end_ns: int | None = None
    tail_eligible: bool = False
    continuity_lost: bool = False
    last_now_ns: int | None = None
    timeline: dict = field(default_factory=dict)
    send_log: list = field(default_factory=list)
    # WF-11 nonsecret native-Windows storage record (phase / API result /
    # GetLastError integers only; never a path or credential).
    storage_log: list = field(default_factory=list)


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
        # Route A (RA-04): set only through the sealed protected-context seam.
        self._ra: _F03RouteARunStateV1 | None = None
        self.operator_attempt_sha256: str | None = None

    # -- helpers -------------------------------------------------------------

    def _halt(self, exc: F03Halt) -> None:
        if self.halt is None:
            self.halt = exc
        self.machine.halt()
        if self._ra is not None:
            self._ra_latch_first_event("HALT")
            return
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

    # -- Route A sealed seam (RA-04-005 steps 5-10) ---------------------------
    # Every entry requires the ONE F03ProtectedContextV1 minted by the
    # protected orchestration and a live consumption receipt.

    def _route_a_require(self, ctx: object) -> _F03RouteARunStateV1:
        ra = self._ra
        if type(ctx) is not F03ProtectedContextV1 or ra is None or ctx is not ra.ctx:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "route-A protected context")
        ctx.assert_live()
        # NH-04-005: U is rechecked against the immutable live receipt at every
        # protected seam boundary (runner attributes are never trusted alone).
        _route_a_require_u_equality(self.plan.run_id, self.invocation_id, ctx.receipt.invocation_id)
        return ra

    def _ra_now(self) -> int:
        """The row-0 monotonic clock; retrograde / invalid -> continuity lost,
        after which no further network send is permitted."""
        ra = self._ra
        value = self._base_runtime.monotonic_clock_ns()
        if (type(value) is not int or value < 0 or value < ra.t0_ns
                or (ra.last_now_ns is not None and value < ra.last_now_ns)):
            ra.continuity_lost = True
            ra.tail_eligible = False
            raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "monotonic clock continuity lost")
        ra.last_now_ns = value
        return value

    def _ra_mark(self, name: str) -> int:
        value = self._ra_now()
        self._ra.timeline.setdefault(name, value)
        return value

    def _ra_refuse(self, kind: str, key: str, now: int | None, cap: int | None, detail: str) -> F03Halt:
        self._ra.send_log.append({"kind": kind, "operation": key, "now_ns": now, "cap_ns": cap, "started": False})
        return F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, detail + " (zero physical send)")

    def _ra_read_cap(self) -> int:
        ra = self._ra
        s = ra.ctx.schedule
        if ra.first_event_ns is not None:
            if not ra.tail_eligible or ra.tail_end_ns is None:
                raise self._ra_refuse("READ", "TAIL", None, None, "no read-only tail authority")
            cap = ra.tail_end_ns
        elif ra.active_end_ns is not None:
            cap = ra.active_end_ns
        else:
            # Pre-writer protected reads: never into the closure/slack reserve.
            cap = ra.ta_ns - s.closure_ns - s.slack_ns
        return min(cap, ra.ta_ns)

    def _ra_before_read(self, operation: str) -> int:
        """RA-02-005/007: before EACH physical read/page/poll start compare the
        fresh monotonic time with the effective cap and TA, require a live
        receipt and an admissible complete attempt (accepted per-operation
        timeout, itself <= the inherited 10 s bound)."""
        ra = self._ra
        key = _ROUTE_A_READ_TIMEOUT_KEY.get(operation, "stage3_read")
        if ra.continuity_lost:
            raise self._ra_refuse("READ", operation, None, None, "clock continuity lost")
        now = self._ra_now()
        try:
            ra.ctx.assert_live()
        except F03Halt:
            ra.tail_eligible = False
            raise self._ra_refuse("READ", operation, now, None, "receipt not live") from None
        cap = self._ra_read_cap()
        timeout = ra.ctx.schedule.timeouts_ns[key]
        if not route_a_start_permitted(now_ns=now, cap_ns=cap, ta_ns=ra.ta_ns, attempt_ns=timeout):
            raise self._ra_refuse("READ", operation, now, cap, "read start at/after the effective cap")
        ra.send_log.append({"kind": "READ", "operation": operation, "now_ns": now, "cap_ns": cap, "started": True})
        return now

    def _ra_after_read(self, operation: str, started_ns: int) -> None:
        """A response completing after its accepted attempt bound is recorded
        as incomplete (quota stays spent, nothing inferred from it)."""
        ra = self._ra
        key = _ROUTE_A_READ_TIMEOUT_KEY.get(operation, "stage3_read")
        finished = self._ra_now()
        if finished - started_ns > ra.ctx.schedule.timeouts_ns[key]:
            ra.send_log.append({"kind": "LATE_COMPLETION", "operation": operation, "now_ns": finished,
                                "cap_ns": started_ns + ra.ctx.schedule.timeouts_ns[key], "started": True})
            raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "response completed after the accepted attempt bound (incomplete)")

    def _ra_before_write(self, action: str) -> None:
        """Immediately pre-adapter: writes only inside the admitted active
        window, never after the first HALT/active close, within G."""
        ra = self._ra
        if ra.continuity_lost:
            raise self._ra_refuse(action, action, None, None, "clock continuity lost")
        now = self._ra_now()
        if ra.first_event_ns is not None or ra.active_end_ns is None:
            raise self._ra_refuse(action, action, now, None, "no write after the first HALT/active close")
        ra.ctx.assert_live()
        if self.ledger.create_t3 + self.ledger.cancel_t3 > ra.ctx.max_ordinary_write_sends:
            raise self._ra_refuse(action, action, now, None, "G ordinary write bound")
        cap = min(ra.active_end_ns, ra.ta_ns)
        timeout = ra.ctx.schedule.timeouts_ns["create" if action == "CREATE" else "cancel"]
        if not route_a_start_permitted(now_ns=now, cap_ns=cap, ta_ns=ra.ta_ns, attempt_ns=timeout):
            raise self._ra_refuse(action, action, now, cap, "write start at/after the active cap")
        ra.send_log.append({"kind": action, "operation": action, "now_ns": now, "cap_ns": cap, "started": True})

    def _ra_new_create_block(self) -> F03Halt | None:
        """RA-02-006 / RA-05-004: ``None`` only if a NEW CREATE risk boundary is
        admissible now (active window open, both remaining-time inequalities
        strictly above ``W+Q+C+H``, and the CREATE plus its possible exact
        CANCEL inside the G ordinary write bound)."""
        ra = self._ra
        s = ra.ctx.schedule
        now = self._ra_now()
        if ra.first_event_ns is not None or ra.active_end_ns is None or ra.continuity_lost:
            return F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "no new CREATE after the first HALT/active close")
        need = s.write_cancel_ns + s.mandatory_read_ns + s.closure_ns + s.slack_ns
        # Strict: remaining == reserve is NOT sufficient for new risk.
        if not (ra.ta_ns - now > need and ra.active_end_ns - now > need):
            return F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "DEADLINE_RESERVATION_INSUFFICIENT before a new CREATE risk boundary")
        if self.ledger.create_t3 + self.ledger.cancel_t3 + 2 > ra.ctx.max_ordinary_write_sends:
            return F03Halt(HaltCode.WRITE_LIMIT_CONSUMED, "G ordinary write bound cannot cover CREATE plus exact CANCEL")
        return None

    def _ra_require_new_create_risk(self) -> None:
        self._ra.ctx.assert_live()
        block = self._ra_new_create_block()
        if block is not None:
            raise block

    def _ra_latch_first_event(self, kind: str) -> None:
        """RA-02-002/004: latch ``Tfirst_halt_or_close`` exactly once; a later
        HALT / close / error never overwrites it or postpones the cap."""
        ra = self._ra
        if ra.first_event_ns is not None:
            return
        try:
            now = self._ra_now()
        except F03Halt:
            ra.first_event_kind = kind + "_CLOCK_INVALID"
            return
        ra.first_event_ns = now
        ra.first_event_kind = kind
        ra.timeline.setdefault("Tfirst_halt_or_close", now)
        if ra.active_end_ns is None:
            # A first event before the protected writer admission mints no
            # signed tail capability (nothing to reconcile, no read grant).
            ra.tail_eligible = False
            return
        cap = route_a_tail_cap_ns(active_end_ns=ra.active_end_ns, first_event_ns=now, ta_ns=ra.ta_ns,
                                  schedule=ra.ctx.schedule)
        ra.tail_end_ns = cap
        self.tail_end_ns = cap
        ra.timeline.setdefault("Ttail_effective", cap)
        ra.tail_eligible = self.stage3 is not None and not ra.continuity_lost

    def _ra_enter_tail(self) -> None:
        ra = self._ra
        if not ra.tail_eligible or ra.tail_end_ns is None or self.runtime is None:
            raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "no read-only tail authority")
        ra.ctx.assert_live()
        self.runtime = dataclasses.replace(self.runtime, experiment_absolute_end_monotonic_ns=min(ra.tail_end_ns, ra.ta_ns))

    def _route_a_tail(self) -> None:
        """Conditional read-only tail (RA-02-007): only with an already-live
        receipt, credential scope, protected read authority, writer evidence
        and remaining quota; never a write, reconnect, restart or relatch."""
        ra = self._ra
        if self.stage3 is None or ra.first_event_ns is None or not ra.tail_eligible or ra.continuity_lost:
            return
        try:
            self._ra_enter_tail()
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

    def _route_a_attach(self, ctx: object) -> None:
        """Bind the one protected context (after row 10, before any claim or
        credential scope): runtime / receipt / plan identity, source binding,
        Demo numbered-subaccount domain and the outlay bound."""
        if type(ctx) is not F03ProtectedContextV1:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "route-A protected context")
        if self._ra is not None or self.run_folder is not None or self.machine.state is not F03State.BOOT_HOLD:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "runner already attached, claimed or started")
        ctx.assert_live()
        rt = self._base_runtime
        if (
            type(rt) is not _runner.ExperimentRunnerRuntimeV2
            or rt.normal_gate.process_instance_id != ctx.process_instance_id
            or rt.experiment_absolute_end_monotonic_ns != ctx.ta_ns
        ):
            raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "runtime does not carry the receipt process/TA")
        # NH-04-001/005: plan.run_id == binding/runner invocation_id == live
        # receipt invocation_id, exact canonical lowercase UUID4 (no fallback to
        # the legacy permissive ``invocation_id or plan.run_id`` override).
        _route_a_require_u_equality(self.plan.run_id, self.invocation_id, ctx.receipt.invocation_id)
        if route_a_plan_binding_sha256(self.plan) != ctx.plan_binding_sha256:
            raise F03Halt(HaltCode.SOURCE_BINDING_UNRESOLVED, "plan differs from the authorized plan binding")
        verify_source_binding(self.plan, self.observed_identity)
        verify_domain_and_origin(rt)
        _an.require_plan_within_outlay_bound(self.bound)
        self._ra = _F03RouteARunStateV1(ctx=ctx, t0_ns=ctx.t0_ns, ta_ns=ctx.ta_ns)
        self.run_started_ns = ctx.t0_ns
        self._ra.timeline["T0"] = ctx.t0_ns
        self._ra.timeline["TA"] = ctx.ta_ns

    def _route_a_claim_and_mark(self, ctx: object) -> None:
        """RA-04-005 step 5 / RA-08-001: exclusive RUN_CLAIM (fsync + readback
        + directory-entry durability) then the distinct exclusive
        OPERATOR_ATTEMPT_V1 marker (fsync + readback + directory-entry
        durability) bound to the exact claim SHA, BEFORE any signed read.  Any
        failure leaves the run id consumed (no retry, no fresh run id).

        This body is the historical accepted POSIX sequence (WF-14 / D-08).
        Native Windows uses only the separate checked WF-07/WF-08 sequence."""
        if _ROUTE_A_NATIVE_WINDOWS:
            return self._route_a_claim_and_mark_native_windows(ctx)
        ra = self._route_a_require(ctx)
        if self._ra_now() >= ra.ta_ns:
            raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "authorization expired before the run claim")
        F03FeeExperimentRunnerV1._completed_run_ids.add(self.plan.run_id)
        self.claim()
        self._ra_mark("TC")
        try:
            readback = (self.run_folder / RUN_CLAIM_FILE_NAME).read_bytes()
        except OSError:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "RUN_ALREADY_CLAIMED: claim readback unavailable") from None
        if sha256_hex(readback) != self.run_claim_sha256:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "RUN_ALREADY_CLAIMED: claim readback mismatch")
        # RA-08-001 / RA-IMP-F01: the claim is durable only once BOTH directory
        # entries are: RUN_CLAIM.json in the run folder, and the run folder in
        # the run artifact root.  Unproven => halt, run id stays consumed.
        _route_a_require_directory_entry_durable(
            self.run_folder, "RUN_ALREADY_CLAIMED: claim file directory-entry durability unproven")
        _route_a_require_directory_entry_durable(
            self.run_folder.parent, "RUN_ALREADY_CLAIMED: run folder directory-entry durability unproven")
        marker = canonical_json_bytes({
            "attempt_schema": OPERATOR_ATTEMPT_SCHEMA, "run_id": self.plan.run_id, "attempt_ordinal": 1,
            "run_claim_sha256": self.run_claim_sha256, "plan_binding_sha256": ctx.plan_binding_sha256,
            "timing_profile_sha256": ctx.schedule.profile_raw_sha256, "reserve_policy_id": ctx.schedule.policy_id,
            "authorization_receipt_digest": ctx.receipt_digest, "process_instance_id": ctx.process_instance_id,
        })
        path = self.run_folder / OPERATOR_ATTEMPT_FILE_NAME
        try:
            with open(path, "xb") as handle:
                handle.write(marker)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "OPERATOR_ATTEMPT_ALREADY_CONSUMED") from None
        except OSError:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker not durably written") from None
        try:
            if path.read_bytes() != marker:
                raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker readback mismatch")
        except OSError:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker readback unavailable") from None
        _route_a_require_directory_entry_durable(
            self.run_folder, "OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker directory-entry durability unproven")
        self.operator_attempt_sha256 = sha256_hex(marker)
        self._ra_mark("TM")

    # -- native-Windows storage component (Stage A; see module notes) ----------

    def _ra_storage_step(self, name: str) -> int:
        """WF-19: every storage step is charged to the ORIGINAL row-0 T0 / TA
        clock (no new budget, reserve or window); at/after TA it halts."""
        now = self._ra_mark("WS_" + name)
        if now >= self._ra.ta_ns:
            raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "authorization expired at storage step " + name)
        return now

    def _route_a_claim_target(self) -> Tuple[Path, Path]:
        """The exact ``(P, D)`` pair: the same containment, root and run-id
        checks as the legacy ``claim()`` / ``claim_run_folder`` (both left
        unchanged), WITHOUT creating anything."""
        rt = self._base_runtime
        authority = getattr(rt, "authority_binding", None)
        repository = getattr(rt, "canonical_repository_root", None)
        ledger = getattr(rt, "expected_ledger_path", None)
        if authority is None or not repository or not ledger:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "runtime roots unresolved for run claim containment")
        prohibited = tuple(self.prohibited_roots) + (
            Path(repository), Path(authority.authority_namespace_root), Path(ledger).parent)
        root = _resolved_components(Path(self.run_artifact_root))
        for item in prohibited:
            real = Path(item).resolve(strict=False)
            if root == real or real in root.parents or root in real.parents:
                raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run artifact root containment")
        if not root.is_dir():
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run artifact root absent")
        run_id = self.plan.run_id
        if type(run_id) is not str or _an._UUID4_RE.fullmatch(run_id) is None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run claim id")
        return root, root / run_id

    def _route_a_marker_object(self, ctx: F03ProtectedContextV1) -> dict:
        """The unchanged accepted ``F03_OPERATOR_ATTEMPT_V1`` key set/values."""
        return {
            "attempt_schema": OPERATOR_ATTEMPT_SCHEMA, "run_id": self.plan.run_id, "attempt_ordinal": 1,
            "run_claim_sha256": self.run_claim_sha256, "plan_binding_sha256": ctx.plan_binding_sha256,
            "timing_profile_sha256": ctx.schedule.profile_raw_sha256, "reserve_policy_id": ctx.schedule.policy_id,
            "authorization_receipt_digest": ctx.receipt_digest, "process_instance_id": ctx.process_instance_id,
        }

    def _route_a_native_flush(self, path: Path, expected_identity: Tuple[int, int], phase: str,
                              detail_prefix: str) -> None:
        """One checked directory-handle flush of exactly ``path`` with
        non-qualifying pre-open / post-close pathname consistency checks and
        WF-19 start/end marks on the row-0 clock."""
        ra = self._ra
        start = self._ra_storage_step(phase + "_START")
        if _route_a_directory_identity(path, phase=phase + "_PRE_OPEN", detail_prefix=detail_prefix) != expected_identity:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                          f"{detail_prefix}{WINDOWS_STORAGE_IDENTITY_CHANGED} phase={phase} pre-open")
        _route_a_win32_flush_directory(path, phase=phase, detail_prefix=detail_prefix, record=ra.storage_log)
        if _route_a_directory_identity(path, phase=phase + "_POST_CLOSE", detail_prefix=detail_prefix) != expected_identity:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                          f"{detail_prefix}{WINDOWS_STORAGE_IDENTITY_CHANGED} phase={phase} post-close")
        end = self._ra_storage_step(phase + "_END")
        ra.storage_log[-1]["elapsed_ns"] = end - start

    def _route_a_claim_and_mark_native_windows(self, ctx: object) -> None:
        """WF-07 / WF-08 steps (3)-(5), native Windows only (RA-08-001-WINDOWS-
        F03): exclusive ``mkdir(D)`` -> checked flush of the parent ``P`` ->
        ``D`` consistency check -> exclusive ``RUN_CLAIM.json`` (complete write,
        ``flush``, ``fsync``, checked close) -> checked flush of ``D`` -> exact
        byte/hash/closed-field readback -> the distinct exclusive
        ``OPERATOR_ATTEMPT_V1.json`` with the same write / ``D`` flush /
        readback sequence.  ``U`` is spent before ``mkdir``; every failure is a
        terminal halt with the run id consumed (no retry, repair, rename,
        delete or fresh run id).  The admission link (step 6) is a separate
        mandatory stop in Stage A."""
        ra = self._route_a_require(ctx)
        self._ra_storage_step("CLAIM_START")
        if self.run_folder is not None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "run already claimed by this instance")
        F03FeeExperimentRunnerV1._completed_run_ids.add(self.plan.run_id)
        claim_prefix, marker_prefix = "RUN_ALREADY_CLAIMED: ", "OPERATOR_ATTEMPT_ALREADY_CONSUMED: "
        root, folder = self._route_a_claim_target()
        root_identity = _route_a_directory_identity(root, phase="ROOT_BEFORE_MKDIR", detail_prefix=claim_prefix)
        try:
            os.mkdir(folder)
        except FileExistsError:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "RUN_ALREADY_CLAIMED: run id already claimed (no replay/resume)") from None
        except OSError:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "RUN_ALREADY_CLAIMED: run claim folder not creatable") from None
        self.run_folder = folder
        self._ra_storage_step("RUN_FOLDER_CREATED")
        folder_identity = _route_a_directory_identity(folder, phase="RUN_FOLDER_AFTER_MKDIR", detail_prefix=claim_prefix)
        # WF-07: P is flushed after mkdir(D) and BEFORE the claim file exists.
        self._route_a_native_flush(root, root_identity, "PARENT_AFTER_RUN_FOLDER_MKDIR", claim_prefix)
        if (
            _route_a_directory_identity(folder, phase="RUN_FOLDER_CONSISTENCY", detail_prefix=claim_prefix) != folder_identity
            or _route_a_directory_identity(root, phase="ROOT_CONSISTENCY", detail_prefix=claim_prefix) != root_identity
        ):
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                          f"{claim_prefix}{WINDOWS_STORAGE_IDENTITY_CHANGED} phase=RUN_FOLDER_CONSISTENCY")
        claim = canonical_json_bytes(self._claim_object())
        self._ra_storage_step("CLAIM_WRITE")
        _route_a_write_exclusive_record(
            folder / RUN_CLAIM_FILE_NAME, claim, collision_detail="RUN_ALREADY_CLAIMED: claim file already exists",
            write_detail="RUN_ALREADY_CLAIMED: run claim not durably written")
        self._route_a_native_flush(folder, folder_identity, "RUN_FOLDER_AFTER_CLAIM", claim_prefix)
        self._ra_storage_step("CLAIM_READBACK")
        self.run_claim_sha256 = _route_a_readback_record(
            folder / RUN_CLAIM_FILE_NAME, claim, detail_prefix=claim_prefix,
            bound_fields={"claim_schema": RUN_CLAIM_SCHEMA, "run_id": self.plan.run_id})
        self._ra_mark("TC")
        marker = canonical_json_bytes(self._route_a_marker_object(ra.ctx))
        self._ra_storage_step("MARKER_WRITE")
        _route_a_write_exclusive_record(
            folder / OPERATOR_ATTEMPT_FILE_NAME, marker, collision_detail="OPERATOR_ATTEMPT_ALREADY_CONSUMED",
            write_detail="OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker not durably written")
        self._route_a_native_flush(folder, folder_identity, "RUN_FOLDER_AFTER_MARKER", marker_prefix)
        self._ra_storage_step("MARKER_READBACK")
        attempt_sha256 = _route_a_readback_record(
            folder / OPERATOR_ATTEMPT_FILE_NAME, marker, detail_prefix=marker_prefix,
            bound_fields={"attempt_schema": OPERATOR_ATTEMPT_SCHEMA, "run_id": self.plan.run_id, "attempt_ordinal": 1,
                          "run_claim_sha256": self.run_claim_sha256, "plan_binding_sha256": ra.ctx.plan_binding_sha256,
                          "authorization_receipt_digest": ra.ctx.receipt_digest,
                          "process_instance_id": ra.ctx.process_instance_id})
        self.operator_attempt_sha256 = attempt_sha256
        self._ra_mark("TM")

    def _route_a_admission_link(self, ctx: object) -> None:
        """WF-08 step (6) / NH-07-003 / WF-16: the exclusive
        ``F03_N1_ADMISSION_LINK_V1.json`` would follow the marker.  Its format,
        placement, privacy projection and trusted N1 history context are NOT
        accepted (Stage B; D-07/D-09/D-10), so in Stage A this is a MANDATORY
        STOP on every platform: no placeholder file, no empty link and never a
        continuation to credential scope or a signed read.  The run id stays
        consumed and held."""
        self._route_a_require(ctx)
        if self.run_folder is None or self.operator_attempt_sha256 is None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "claim/attempt marker missing")
        self._ra_mark("TL_UNAVAILABLE")
        raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED,
                      "N1_ADMISSION_LINK_UNAVAILABLE: no accepted N1 admission link in Stage A (run id consumed and held)")

    def _route_a_pre_writer(self, ctx: object, *, protected_phase_charges: Sequence[int]) -> bool:
        """RA-04-005 step 7, inside the one credential scope after the
        protected read phase(s) and BEFORE the receipt-bound release: charge
        the protected phase reads once into the whole-run ledger, then the
        unchanged F03 source/preflight/isolation/B0 logic.  ``False`` = halted
        (no writer may be admitted)."""
        ra = self._route_a_require(ctx)
        if self.run_folder is None or self.operator_attempt_sha256 is None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "claim/attempt marker missing")
        try:
            for charge in protected_phase_charges:
                if type(charge) is not int or charge < 0:
                    raise F03Halt(HaltCode.BUDGET_EXCEEDED, "protected phase charge")
                self.ledger.charge_unobserved_protected_gets(charge, phase="PROTECTED_STAGE3_PHASE")
            self._ra_mark("TP")
            schedule = ra.ctx.schedule
            pre_cap = ra.ta_ns - schedule.closure_ns - schedule.slack_ns
            self.runtime, self.guard = build_f03_runtime_v1(self._base_runtime, self.ledger, active_end_monotonic_ns=pre_cap)
            self.guard._route_a = self
            self.utc_audit["run_started_utc"] = canonical_timestamp(self.runtime.wall_clock())
            self.machine.advance(F03State.SOURCE_BOUND)
            self.preflight()
            self.b0()
            self._ra_mark("TB0")
            self.machine.advance(F03State.CURRENT_PROCESS_WRITER_ADMISSION)
            self.ledger.require_get_capacity(ORDER_LIFECYCLE_GET_RESERVATION + FINAL_RECONCILIATION_GET_RESERVATION,
                                             purpose="ORDER1 lifecycle after protected admission")
            return True
        except F03Halt as exc:
            self._halt(exc)
        except _runner.RunnerError as exc:
            self._halt(F03Halt(HaltCode.ORDER_RECONCILIATION_INCOMPLETE, exc.code.value))
        return False

    def _route_a_consume(self, ctx: object, stage3: object) -> F03RunResultV1:
        """RA-04-005 step 9 -- the one-shot dedicated consumer of the
        receipt-bound Stage-3 result: writer admission instant ``TW``, the
        conservative active window, then the unchanged Order1 / optional
        Order2 (same session) / B1 / B2 / final reconciliation.  It never
        claims again, admits again, ends the writer session or calls the
        ordinary Gate-D loop."""
        ra = self._route_a_require(ctx)
        try:
            if self.machine.state is not F03State.CURRENT_PROCESS_WRITER_ADMISSION or self.stage3 is not None:
                raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "consumer phase order")
            acquisition = getattr(stage3, "normal_writer_acquisition", None)
            if (
                type(stage3) is not _runner._Stage3ActiveReleaseAndNormalWriterResultV1
                or stage3.process_instance_id != ra.ctx.process_instance_id
                or acquisition is None or acquisition.handle is None or acquisition.handle.closed
            ):
                raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "receipt-bound Stage-3 lineage")
            rsid = stage3.trusted_dynamic_read_set_id
            if rsid in self.used_read_set_ids:
                raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "stale trusted read set reuse")
            projection = acquisition.handle.projection()
            if (projection.risk_control_state != "WRITER_ELIGIBLE" or projection.unresolved_write_request_ids
                    or projection.protected_unresolved_legacy_write_count != 0):
                raise F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "writer state")
            self.used_read_set_ids.append(rsid)
            self.stage3 = stage3
            tw = self._ra_mark("TW")
            ra.tw_ns = tw
            schedule = ra.ctx.schedule
            # RA-02-004: strict admission inequality at the single TW.
            if not ra.ta_ns - tw > schedule.active_ns + schedule.tail_ns + schedule.closure_ns + schedule.slack_ns:
                raise F03Halt(HaltCode.RUN_DEADLINE_EXCEEDED, "DEADLINE_RESERVATION_INSUFFICIENT at writer admission")
            ra.active_end_ns = route_a_active_end_ns(tw_ns=tw, ta_ns=ra.ta_ns, schedule=schedule)
            self.active_end_ns = ra.active_end_ns
            ra.timeline["Tactive_end"] = ra.active_end_ns
            self.runtime = with_phase_end(self.runtime, ra.active_end_ns)
            self.machine.advance(F03State.WRITER_ELIGIBLE)
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
        return self._route_a_finish()

    def _route_a_writer_admission_failed(self, ctx: object, detail: str) -> F03RunResultV1:
        """The protected receipt-bound release / normal-writer admission did not
        produce a writer: HALTED_HELD, no write, no tail."""
        self._route_a_require(ctx)
        self._halt(F03Halt(HaltCode.TARGET_DOMAIN_INELIGIBLE, "receipt-bound release/normal writer admission failed: " + detail))
        return self._route_a_finish()

    def _route_a_finish_without_writer(self, ctx: object) -> F03RunResultV1:
        if type(ctx) is not F03ProtectedContextV1 or self._ra is None or ctx is not self._ra.ctx:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "route-A protected context")
        if self.halt is None or self.stage3 is not None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "finish without writer requires a pre-writer halt")
        return self._route_a_finish()

    def _route_a_finish(self) -> F03RunResultV1:
        F03FeeExperimentRunnerV1._completed_run_ids.add(self.plan.run_id)
        return self._result()

    def route_a_timing_record(self) -> dict:
        """Nonsecret monotonic timing / cap / send evidence (integers only)."""
        ra = self._ra
        if ra is None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "not a Route-A runner")
        schedule = ra.ctx.schedule
        return {
            "route_a_feasibility": ROUTE_A_FEASIBILITY_UNPROVEN,
            "T0": ra.t0_ns, "TA": ra.ta_ns, "TW": ra.tw_ns, "Tactive_end": ra.active_end_ns,
            "Tfirst_halt_or_close": ra.first_event_ns, "first_event_kind": ra.first_event_kind,
            "Ttail_effective": ra.tail_end_ns, "tail_eligible": ra.tail_eligible, "continuity_lost": ra.continuity_lost,
            "timeline": dict(ra.timeline), "send_log": [dict(entry) for entry in ra.send_log],
            "timing_profile_sha256": schedule.profile_raw_sha256, "reserve_policy_id": schedule.policy_id,
            "counters": {"get": self.ledger.get_count, "balance_get": self.ledger.balance_gets,
                         "create_t3": self.ledger.create_t3, "cancel_t3": self.ledger.cancel_t3,
                         "create_physical": self.ledger.create_transport_invocations,
                         "cancel_physical": self.ledger.cancel_transport_invocations},
            "run_claim_sha256": self.run_claim_sha256, "operator_attempt_sha256": self.operator_attempt_sha256,
            "storage_log": [dict(entry) for entry in ra.storage_log],
        }

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
        if self._ra is not None:
            # Route A: the market must outlast the immutable authorization end TA
            # (+120 s below), never a fresh 900 s interval.
            active_end_utc = self.runtime.wall_clock() + _seconds(max(self._ra.ta_ns - self._ra_now(), 0))
        else:
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
        if self._ra is not None:
            # RA-04-005 step 8: the Route-A consumer never runs an unreceipted
            # Stage-3 release / normal-writer admission of its own.
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "unreceipted admission refused on the protected route")
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
        if self._ra is not None:
            # RA-04-005 step 10: the protected orchestration is the single
            # writer-cleanup owner; the consumer never ends the session.
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "writer cleanup is owned by the protected orchestration")
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
        if self._ra is not None:
            self._ra_require_new_create_risk()
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
        if self._ra is not None:
            # RA-02-006: re-test the full reserve at the CREATE risk boundary itself.
            self._ra_require_new_create_risk()
        self._require_no_prior_plan_create(locked)
        adapter = NormalWriteAdapter(self.runtime.normal_gate, self.runtime.normal_write_transport)
        self.guard.set_phase(f"ORDER{index}_CREATE")
        outcome = execute_f03_create(
            locked=locked, session_id=self.stage3.normal_writer_session_id, capability=capability, adapter=adapter,
            runtime=self.runtime, ticker=self.plan.ticker, projection=locked.projection(), truth=truth,
            yes_price=limit_price, active_trusted_read_set_id=self.stage3.trusted_dynamic_read_set_id,
            plan_sha256=self._plan_sha256(), ledger=self.ledger,
            send_gate=None if self._ra is None else self._ra_before_write,
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
                    ledger=self.ledger, send_gate=None if self._ra is None else self._ra_before_write,
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
            if self._ra is not None:
                # Route A (RA-05-003): no second admission exists -- Order 2 reuses
                # the SAME receipt, writer session and read set, so only its own
                # lifecycle + the final reconciliation are reserved; the full
                # time/write reserve is re-tested (failure suppresses Order 2).
                self.ledger.require_get_capacity(
                    ORDER_LIFECYCLE_GET_RESERVATION + FINAL_RECONCILIATION_GET_RESERVATION,
                    purpose="ORDER2 lifecycle (same protected session)",
                )
                self._ra_require_new_create_risk()
            else:
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
        if self._ra is not None:
            # Route A: the orchestration owns the one writer session; it is
            # never ended or re-admitted here (no new permit authority).
            return True
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
        if self._ra is not None:
            # The actual active close: latch (first event wins), no further
            # write, and the read-only tail window replaces the active cap.
            self._ra_latch_first_event("ACTIVE_CLOSE")
            self._ra_enter_tail()
        with self._campaign("FINAL_RECONCILIATION") as campaign:
            snapshot = campaign.domain(selected_ticker=self.plan.ticker)
        self.final_identity = sha256_hex(canonical_json_bytes(list(snapshot.page_commitments)))
        test_ids = {o.order_id for o in self.orders if o.order_id}
        if any(r.get("status") == "resting" and r.get("order_id") in test_ids for r in snapshot.order_rows):
            self.unresolved_active_exposure = True
        self.read_observations.append({"phase": "FINAL", "page_commitments": list(snapshot.page_commitments)})
        self._require_no_unrelated_activity(snapshot)

    def run(self) -> F03RunResultV1:
        if self._ra is not None:
            raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, "a protected Route-A runner never uses the unreceipted run()")
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
        if self._ra is not None:
            self._route_a_tail()
            return
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
        if self._ra is not None:
            # Route A: deadlines are the row-0-derived caps (never 900/120); a
            # run without an admitted active window records T0 for both.
            active_deadline = self._ra.active_end_ns if self._ra.active_end_ns is not None else self._ra.t0_ns
            reconciliation_deadline = self._ra.tail_end_ns if self._ra.tail_end_ns is not None else active_deadline
        else:
            active_deadline = self.active_end_ns or 0
            reconciliation_deadline = self.tail_end_ns or ((self.active_end_ns or 0) + RECONCILIATION_TAIL_NS)
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
            "active_write_deadline_ns": active_deadline,
            "reconciliation_deadline_ns": reconciliation_deadline,
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
