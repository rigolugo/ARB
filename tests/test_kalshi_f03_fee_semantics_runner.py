"""Offline synthetic integration tests for the F03 Demo fee-semantics runner.

Controls: KALSHI_DEMO_R1_D07_F03_DEMO_FEE_SEMANTICS_TEST_SPEC_01_CORRECTION_02
(sections 4-6, 9-11, 13-17, 23-25).  Every conformance test drives the REAL
pinned canonical substrate -- the active-domain ledger, Stage-3 release chain,
WriterEligibilityGate scoped/generic permits, durable T1->T2->T3 with trusted
anchor readback, the final active-domain equality gate, the trusted-T2
normal-write binding, the protected adapter/classifiers/reconciliation and the
installed balance reader -- with deterministic SYNTHETIC venue bytes behind the
inherited transport seams only.  No DNS/socket/HTTP, venue, account, real
credential or real signing activity occurs; the sanctioned-wire test fakes the
lowest socket/TLS boundary and signs with an in-process synthetic RSA key.
"""

from __future__ import annotations

import ast
import base64
import contextlib
import copy as copy_module
import dataclasses
import hashlib
import inspect
import json
import os
import pickle as pickle_module
import socket
import stat
import sys
import tempfile
import types
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from arb.execution_ledger import (
    AuthorityNamespaceBinding,
    FailureCode,
    LedgerError,
    canonical_json_bytes,
    end_writer_session,
    initialize_authority_namespace,
)
from arb.venues.kalshi import f03_fee_semantics_analyzer as A
from arb.venues.kalshi import f03_fee_semantics_runner as F
from arb.venues.kalshi.emergency_cancel import EmergencyCancelGate, EmergencyRateConfigV1, EmergencyRateLane
from arb.venues.kalshi.orderbook import KalshiNativeOrderBookLevel, KalshiNativeOrderBookSnapshot
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    FlowRiskLimits,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
    WriterEligibilityGate,
)
import arb.venues.kalshi.ledger_binding as ledger_binding
import arb.venues.kalshi.minimal_market_maker_experiment_runner as runner
import arb.venues.kalshi.quote_lifecycle as quote_lifecycle
from arb.venues.kalshi.minimal_market_maker_experiment_runner import RawOperationResponseV1, RunnerError, RunnerFailureCode, RunnerOperation

TICKER = "KXF03TEST-26AUG17-T50"
EVENT = "KXF03TEST-26AUG17"
SERIES = "KXF03TEST"
ACCOUNT = "ARB_KALSHI_DEMO_PRIMARY_ACCOUNT"
STRATEGY_ID = "mm_" + "d" * 32
LIMIT = D("0.5000")
FILL_TIME = "2026-08-17T13:00:01.000000Z"
FILL_TIME_2 = "2026-08-17T13:00:01.000001Z"
FILL_EPOCH = int(datetime(2026, 8, 17, 13, 0, 1, tzinfo=timezone.utc).timestamp())
SYNTH_KEY_ID = "SYNTHETIC-F03-DEMO-KEY-ID-DO-NOT-USE"

# Spec section 5 / 5.4 protected dependency pins at the required base.
PROTECTED_BLOBS = {
    "src/arb/execution_ledger.py": "608f4cd281525a8bf53fafa2b19eb23cc5b669ac",
    "src/arb/venues/kalshi/quote_lifecycle.py": "8d857abc15aafb2601a549f0bd8bbd7ed05d679b",
    "src/arb/venues/kalshi/risk_control.py": "111685c8c1dc7735a53b45830d93844c329f23e3",
    "src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py": "a169b8ebe13e7d8717966b8cabcba1495e0a8641",
    "src/arb/venues/kalshi/account_subaccount_probe.py": "1dc0e82c61b7dbd6b5a5e2ca2e9ed37ed3f75fe0",
    "src/arb/venues/kalshi/models.py": "628dee54853c09071f93556d404b45bf4e87755a",
    "src/arb/venues/kalshi/validation.py": "8f84f06f74604356daaa62662c7d74220ffef312",
    "src/arb/venues/kalshi/serialization.py": "df25df110775e2fc4542c63b8ce2c4e42eca5e34",
    "tests/test_kalshi_minimal_market_maker_experiment_runner.py": "e31c7bf789e4bb0684fbd3688f4fa3867388cff5",
    "tests/test_kalshi_shadow_experiment.py": "03e39ee183555d825b24e48317b6356c41fe98f1",
}

_RSA: dict = {}


def _synthetic_rsa():
    """In-process SYNTHETIC RSA-2048 key (never a real credential)."""
    if "pem" not in _RSA:
        from cryptography.hazmat.primitives import serialization as _ser
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _RSA["pem"] = key.private_bytes(_ser.Encoding.PEM, _ser.PrivateFormat.PKCS8, _ser.NoEncryption()).decode("ascii")
        _RSA["public"] = key.public_key()
    return _RSA["pem"], _RSA["public"]


class Clock:
    """Deterministic wall / monotonic / uuid inputs with explicit jumps."""

    def __init__(self) -> None:
        self.instant = datetime(2026, 8, 17, 13, 0, 0, tzinfo=timezone.utc)
        self.number = 9001
        self.mono = 5_000_000_000

    def clock(self) -> datetime:
        value = self.instant
        self.instant += timedelta(microseconds=1)
        return value

    def uuid(self) -> uuid.UUID:
        value = uuid.UUID(int=self.number, version=4)
        self.number += 1
        return value

    def monotonic_ns(self) -> int:
        value = self.mono
        self.mono += 1_000_000
        return value

    def jump(self, ns: int) -> None:
        self.mono += ns


def _json(payload, status=200) -> RawOperationResponseV1:
    return RawOperationResponseV1(http_status=status, content_type="application/json",
                                  body_bytes=json.dumps(payload).encode("utf-8"))


class FakeDemoVenue:
    """Stateful synthetic Kalshi Demo venue behind the inherited read/write
    seams.  Rows carry both legacy (``subaccount``) and active-V2
    (``subaccount_number``) scope fields so the protected legacy Gate-D and
    active-V2 validators both run unchanged."""

    def __init__(self, *, no_levels=((D("0.52"), D("0.30")), (D("0.55"), D("0.40"))), balances=(),
                 extra_orders=(), extra_positions=(), fill_cursor_loop=False) -> None:
        self.no_levels = tuple(no_levels)
        self.orders: dict = {}
        self.fills: list = []
        self.read_calls: list = []
        self.orderbook_calls = 0
        self.writes: list = []
        self.balances = list(balances)
        self.balance_calls = 0
        self.extra_orders = list(extra_orders)
        self.extra_positions = list(extra_positions)
        self.fill_cursor_loop = fill_cursor_loop
        self.create_fill_plan = None  # list of (qty, yes_price, created_time, fee)
        self.cancel_concurrent_fill = None
        self.create_raises = None
        self.cancel_raises = None
        self.n = 0
        # Live Stage-3 bookends (F04): exchange status S0/S1 and user-data
        # timestamp T0/T1, alternating per acquisition.
        self.status_payloads: list = []
        self.status_calls = 0
        self.udt_calls = 0
        self.udt_values = ("2026-08-17T12:59:59.950000Z", "2026-08-17T13:00:00.000000Z")
        self.exchange_domain = (0,)
        # Optional per-request override: ``hook(operation, prepared)`` returns a
        # response (or raises) to replace the default; ``None`` -> default.
        self.hook = None

    # -- reads ---------------------------------------------------------------
    def market(self) -> dict:
        return {"ticker": TICKER, "event_ticker": EVENT, "status": "active", "exchange_index": 0,
                "yes_bid_dollars": "0.45", "close_time": "2026-08-18T00:00:00Z",
                "price_ranges": [{"start": "0.00", "end": "1.00", "step": "0.01"}]}

    def _order_rows(self):
        return [dict(o) for o in self.orders.values()] + [dict(o) for o in self.extra_orders]

    def _position_rows(self):
        held = sum((D(f["count_fp"]) for f in self.fills), D("0"))
        rows = []
        if held:
            rows.append({"ticker": TICKER, "subaccount": 1, "subaccount_number": 1, "exchange_index": 0,
                         "position_count_fp": f"{held:.2f}"})
        return rows + [dict(r) for r in self.extra_positions]

    def send(self, operation, prepared, deadline):
        self.read_calls.append((operation, prepared))
        if self.hook is not None:
            override = self.hook(operation, prepared)
            if override is not None:
                return override
        query = dict(prepared.query) if getattr(prepared, "query", None) else {}
        if operation is RunnerOperation.GET_MARKET:
            return _json({"market": self.market()})
        if operation is RunnerOperation.GET_EXCHANGE_STATUS:
            self.status_calls += 1
            if self.status_payloads:
                item = self.status_payloads.pop(0)
                return item if isinstance(item, RawOperationResponseV1) else _json(item)
            return _json({"exchange_active": True, "trading_active": True, "exchange_index_statuses": [
                {"exchange_index": i, "exchange_active": True, "trading_active": True} for i in self.exchange_domain]})
        if operation is RunnerOperation.GET_USER_DATA_TIMESTAMP:
            value = self.udt_values[self.udt_calls % 2]
            self.udt_calls += 1
            return _json({"as_of_time": value})
        # The protected legacy Gate-D reads carry ticker/status filters; the
        # active-V2 domain reads never do (complete pages, local filtering).
        legacy = "ticker" in query
        if operation is RunnerOperation.GET_ORDERS:
            rows = self._order_rows()
            if legacy:
                rows = [r for r in rows if r["ticker"] == query["ticker"]]
            if "status" in query:
                rows = [r for r in rows if r["status"] == query["status"]]
            return _json({"orders": rows, "cursor": ""})
        if operation is RunnerOperation.GET_ORDER:
            order_id = prepared.full_path.rsplit("/", 1)[-1]
            row = self.orders.get(order_id)
            if row is None:
                return RawOperationResponseV1(http_status=404, content_type="application/json", body_bytes=b'{"error":"not_found"}')
            return _json({"order": dict(row)})
        if operation is RunnerOperation.GET_FILLS:
            rows = [dict(f) for f in self.fills if "order_id" not in query or f["order_id"] == query["order_id"]]
            if self.fill_cursor_loop and "limit" in query:
                return _json({"fills": rows, "cursor": "c-" + query.get("cursor", "0") + "x"})
            return _json({"fills": rows, "cursor": ""})
        if operation is RunnerOperation.GET_POSITIONS:
            rows = self._position_rows()
            if legacy:
                rows = [r for r in rows if r["ticker"] == query["ticker"]]
            return _json({"market_positions": rows, "event_positions": [], "cursor": ""})
        if operation is RunnerOperation.GET_BALANCE:
            self.balance_calls += 1
            item = self.balances.pop(0)
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, RawOperationResponseV1):
                return item
            dollars, ts = item
            return _json({"balance": 0, "balance_dollars": dollars, "portfolio_value": 0, "updated_ts": ts})
        raise AssertionError(f"unexpected read {operation}")

    def orderbook(self, ticker, deadline):
        self.orderbook_calls += 1
        snap = KalshiNativeOrderBookSnapshot(
            environment="KALSHI_DEMO", market_ticker=TICKER, method="GET", route_template="/markets/{ticker}/orderbook",
            full_request_path=f"/trade-api/v2/markets/{TICKER}/orderbook", endpoint_classification="AUTHENTICATED_READ_ONLY",
            request_timestamp_ms=1_755_000_000_000, request_started_monotonic_ns=1, request_completed_monotonic_ns=2,
            yes_levels=(KalshiNativeOrderBookLevel(price=D("0.40"), quantity=D("10")),),
            no_levels=tuple(KalshiNativeOrderBookLevel(price=p, quantity=q) for p, q in self.no_levels),
            canonical_level_ordering="ASCENDING_PRICE", response_byte_length=64, response_sha256="0" * 64,
            raw_openapi_sha256="0" * 64, source_binding_record_sha256="0" * 64, request_count=1, retry_count=0,
            redirect_count=0, gustavo_execution_authorization_id="TEST_AUTH", expected_implementation_commit="0" * 40,
            specification_sha256="0" * 64,
        )
        return snap.with_canonical_identity()

    # -- writes --------------------------------------------------------------
    def _fill(self, order_id, qty, price, created, fee):
        self.n += 1
        fid = f"fill-f03-{self.n}"
        no_price = str(D("1") - D(price))
        self.fills.append({
            "fill_id": fid, "trade_id": fid, "order_id": order_id, "ticker": TICKER, "market_ticker": TICKER,
            "side": "yes", "action": "buy", "outcome_side": "yes", "book_side": "bid", "subaccount": 1,
            "subaccount_number": 1, "exchange_index": 0, "yes_price_dollars": price, "no_price_dollars": no_price,
            "count_fp": qty, "is_taker": True, "created_time": created, "ts": FILL_EPOCH, "fee_cost": fee,
        })

    def apply_create(self, body: dict) -> dict:
        self.n += 1
        order_id = f"ord-f03-{self.n}"
        plan = self.create_fill_plan if self.create_fill_plan is not None else [
            ("0.40", "0.4500", FILL_TIME, "0.0070"), ("0.30", "0.4800", FILL_TIME_2, "0.0052")]
        for qty, price, created, fee in plan:
            self._fill(order_id, qty, price, created, fee)
        filled = sum((D(q) for q, *_ in plan), D("0"))
        remaining = D("1.00") - filled
        self.orders[order_id] = {
            "order_id": order_id, "client_order_id": body["client_order_id"], "ticker": TICKER, "side": "yes",
            "status": "resting" if remaining > 0 else "executed", "fill_count_fp": f"{filled:.2f}",
            "remaining_count_fp": f"{remaining:.2f}", "initial_count_fp": "1.00", "subaccount": 1,
            "subaccount_number": 1, "exchange_index": 0, "yes_price_dollars": body["price"],
        }
        return {"order_id": order_id, "client_order_id": body["client_order_id"], "fill_count": f"{filled:.2f}",
                "remaining_count": f"{remaining:.2f}", "ts_ms": 1_755_000_000_123}

    def apply_cancel(self, order_id: str) -> dict:
        row = self.orders[order_id]
        if self.cancel_concurrent_fill is not None:
            qty, price, created, fee = self.cancel_concurrent_fill
            self._fill(order_id, qty, price, created, fee)
            row["fill_count_fp"] = f"{D(row['fill_count_fp']) + D(qty):.2f}"
            row["remaining_count_fp"] = f"{D(row['remaining_count_fp']) - D(qty):.2f}"
        reduced = row["remaining_count_fp"]
        row["remaining_count_fp"] = "0.00"
        row["status"] = "canceled"
        return {"order_id": order_id, "reduced_by": reduced, "ts_ms": 1_755_000_000_456, "client_order_id": row["client_order_id"]}

    def write(self, prepared):
        """Synthetic one-arg normal-write transport (the NormalWriteAdapter
        ``transport(request)`` contract)."""
        self.writes.append(json.loads(json.dumps(prepared)))
        if prepared["operation_name"] == "CREATE_ORDER_V2":
            if self.create_raises is not None:
                raise self.create_raises
            return _json(self.apply_create(prepared["canonical_body"]), status=201)
        if self.cancel_raises is not None:
            raise self.cancel_raises
        return _json(self.apply_cancel(prepared["venue_order_id"]))


class F03HarnessTestCase(unittest.TestCase):
    """Genuine N1 active-domain ledger + Stage-3 release chain (mirrors the
    protected ActiveStage3EndToEndTestCase setup) with the F03 runner on top."""

    N1_CHECKPOINT_SHA = "879d311420d2f6a4e2c20b8f96e8107f3753a30923f0e2afdfb7f5668bcb9068"
    P02_SHA = "2fc189b2a807a6c22ab3e71e41a6cfa66415e3bda87e6c8e66c3eb6e8029c69b"
    CONTROLLED_TICKER = "KXAAAGASD-26SEP02-4.1200"
    SETTLED_TIME = "2026-09-02T14:41:43.665741Z"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository_root = Path(__file__).resolve().parents[1]
        authority_root = self.root / "authority"
        authority_root.mkdir()
        # F05: every experiment must durably claim <runs_root>/<run_id> first.
        self.runs_root = self.root / "runs"
        self.runs_root.mkdir()
        self.prohibited_roots = (self.repository_root, authority_root)
        self.inputs = Clock()
        (self.root / "state").mkdir()
        self.ledger_path = self.root / "state" / "active.sqlite3"
        self.binding = AuthorityNamespaceBinding.bind(
            authority_namespace_id="f03-ns", authority_namespace_root=authority_root,
            canonical_repository_root=self.repository_root)
        initialize_authority_namespace(self.binding, clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        self.domain_binding = ledger_binding.ExecutionDomainBindingV1(
            venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=ACCOUNT, subaccount=1, exchange_index=0)
        bootstrap = ledger_binding.DomainBootstrapContractV1(
            binding=self.domain_binding, bootstrap_class="KNOWN_NONEMPTY_PRESTACK",
            bootstrap_cutoff_at_utc="2026-09-01T00:00:00.000000Z",
            prestack_activity_completeness="COMPLETE_KNOWN_NONEMPTY_PRESTACK",
            unresolved_write_count=0, unresolved_cancel_count=0, working_order_truth="COMPLETE_ZERO",
            fill_truth="COMPLETE_KNOWN_NONZERO", position_truth="COMPLETE_KNOWN_NONZERO",
            retained_position_ticker=self.CONTROLLED_TICKER, retained_position_floor_contracts=D("1.00"))
        _, self.active_contract = ledger_binding.initialize_active_execution_domain_ledger(
            self.binding, canonical_repository_root=str(self.repository_root), domain_binding=self.domain_binding,
            bootstrap_contract=bootstrap, ledger_path=str(self.ledger_path), clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid)
        self.config = RiskLimitConfigV1(
            1, self.domain_binding.conflict_domain_ref, "USD",
            PerOrderRiskLimits(D("10"), D("10"), True, D("0.10"), 1_000),
            PerMarketRiskLimits(D("20"), D("20"), 10, D("20"), D("20")),
            AccountRiskLimits(D("100"), 50, D("100"), 0, D("0")),
            FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"))
        self._drive_to_safe_held()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _drive_to_safe_held(self) -> None:
        emergency = ledger_binding.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.active_contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        handle = emergency.handle
        handle.record_reconciliation({
            "incident_id": self.active_contract.incident_id, "disposition": "ACTIVE_SYNTHETIC_RESOLVED_SAFE",
            "write_closure_class": "AUTHORITATIVE_RESULT_CLOSED", "bound_order_id": None,
            "created_order_upper_bound": 0, "active_order_upper_bound": 0, "unknown_result": False,
            "writer_proof_release_eligible": True, "basis_event_ids": [],
            "adapter_reconciliation_schema_id": "SYNTHETIC_RESOLUTION_V1",
        }, incident_id=self.active_contract.incident_id)
        previous = handle.inspect_validated_projection()
        handle.record_risk_control_state_changed({
            "previous_state": "BOOT_HOLD", "new_state": "SAFE_HELD", "cause": "REPLAY_ALL_SAFETY_PREDICATES_PASS",
            "risk_state_epoch_before": 0, "risk_state_epoch_after": 1, "risk_config_sha256": self.config.sha256,
            "related_emergency_action_id": None, "related_release_id": None, "predecessor_state_event_id": None,
            "observed_authority_trusted_sequence": previous.last_sequence,
            "observed_authority_trusted_hash": previous.terminal_event_hash,
            "observed_ledger_terminal_sequence": previous.last_sequence,
            "observed_ledger_terminal_hash": previous.terminal_event_hash,
        })
        handle.close()

    @staticmethod
    def _hx(n):
        return format(n % (16 ** 64), "064x")

    def _surface(self, seed):
        return runner.PerIndexSurfaceTraversalV1(
            request_identity_sha256=self._hx(seed), page_response_digests=(self._hx(seed + 1),),
            page_economic_digests=(self._hx(seed + 2),), final_cursor_absent=True, pagination_complete=True)

    def _dynamic_read(self, cutoff):
        traversals = tuple(
            runner.PerIndexTraversalV1(exchange_index=i, orders=self._surface((i + 1) * 1000 + 10),
                                       fills=self._surface((i + 1) * 1000 + 40), positions=self._surface((i + 1) * 1000 + 70),
                                       order_rows=(), fill_rows=(), position_rows=())
            for i in (0, 1, 2, 3))
        read = runner.DynamicIndexDomainAccountWideReadV1(
            accepted_source_classification=runner._ACCOUNT_WIDE_SOURCE_CLASSIFICATION_V1,
            index_domain_enumeration_evidence_identity_sha256=self.P02_SHA, account_scope_ref=ACCOUNT,
            subaccount=1, selected_exchange_index=0,
            status_before=runner.ExchangeIndexStatusObservationV1(response_identity_sha256=self._hx(0x57a705), exchange_index_domain=(0, 1, 2, 3)),
            status_after=runner.ExchangeIndexStatusObservationV1(response_identity_sha256=self._hx(0x57a705), exchange_index_domain=(0, 1, 2, 3)),
            freshness_before=runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf0), as_of_time_utc="2026-08-17T12:59:59.700000Z"),
            freshness_after=runner.UserDataFreshnessWatermarkV1(response_identity_sha256=self._hx(0xf1), as_of_time_utc="2026-08-17T13:00:00.000000Z"),
            per_index_traversals=traversals, selected_route_reconciliation_cutoff_sha256=cutoff,
            read_set_identity_sha256=self._hx(0),
            settlement_reconciliation=runner.RetainedPositionSettlementReconciliationV1(
                settlement_evidence_identity_sha256=self.P02_SHA, ticker=self.CONTROLLED_TICKER, exchange_index=0,
                conflict_domain_ref=self.domain_binding.conflict_domain_ref, market_result="yes",
                settled_time_utc=self.SETTLED_TIME, yes_count_fp="1.00", settlement_response_identity_sha256=self._hx(0x5e77)))
        ident = runner.compute_dynamic_index_domain_read_set_identity(
            read, active_domain_binding_id=self.active_contract.domain_binding_id,
            active_domain_binding_sha256=self.active_contract.domain_binding_sha256,
            active_contract_sha256=self.active_contract.contract_sha256, risk_config_sha256=self.config.sha256)
        return dataclasses.replace(read, read_set_identity_sha256=ident)

    def _runtime(self, venue: FakeDemoVenue, *, write_transport=None, seam=True):
        normal_gate = WriterEligibilityGate(monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
                                            uuid_factory=self.inputs.uuid)
        emergency = ledger_binding.acquire_active_emergency_control_only_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.active_contract,
            expected_ledger_path=str(self.ledger_path), clock=self.inputs.clock, uuid_factory=self.inputs.uuid)
        emergency_gate = EmergencyCancelGate(
            handle=emergency.handle, rate_lane=EmergencyRateLane(EmergencyRateConfigV1(2, 1_000, 1, 500, 1, 10, 100)),
            process_instance_id=normal_gate.process_instance_id, monotonic_clock_ns=self.inputs.monotonic_ns,
            wall_clock=self.inputs.clock, uuid_factory=self.inputs.uuid, active_contract=self.active_contract)
        emergency.handle.close()
        rt = runner._build_active_experiment_runner_runtime_v2_for_test(
            normal_gate=normal_gate, emergency_gate=emergency_gate, send_operation_request=venue.send,
            fetch_orderbook=venue.orderbook, monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
            uuid_factory=self.inputs.uuid, risk_config=self.config, experiment_absolute_end_monotonic_ns=10 ** 18,
            authority_binding=self.binding, canonical_repository_root=str(self.repository_root),
            expected_ledger_path=str(self.ledger_path), domain_binding=self.domain_binding,
            active_contract=self.active_contract,
            route_qualification=runner.ActiveRouteQualificationV1(
                environment="KALSHI_DEMO", account_scope_ref=ACCOUNT, subaccount=1, exchange_index=0,
                operation_request_shape_id=runner._ACTIVE_ROUTE_REQUEST_SHAPE_ID,
                exchange_index_wire_policy="EMPIRICALLY_BOUND_AUTOROUTE",
                qualification_evidence_identity_sha256=self.N1_CHECKPOINT_SHA, provenance_class="PROJECT_EVIDENCE_RECORDED"),
            accepted_evidence_contract=runner.n1_accepted_evidence_contract(self.domain_binding),
            strategy_instance_id=STRATEGY_ID, minimum_spread_usd=D("0.0100"),
            gate_d_capability_reference_id="cap_f03_test", normal_write_transport=write_transport or venue.write)
        if not seam:
            return rt
        capability = runner._issue_pre_release_read_capability(
            process_instance_id=rt.normal_gate.process_instance_id, ticker=TICKER, runtime=rt)
        truth = runner.collect_authoritative_read_truth(capability, ticker=TICKER)
        fixture = self._dynamic_read(runner._active_reconciliation_cutoff_sha256(truth))
        fake = runner._FakeTrustedDynamicReadAcquirerV2(runtime=rt, fixture=fixture, selected_route_truth=truth, implied_request_count=72)
        rt = dataclasses.replace(rt, trusted_dynamic_read_acquirer_test_seam=fake)
        venue.read_calls.clear()
        venue.orderbook_calls = 0
        return rt

    def _plan(self, **over) -> F.F03RunPlanV1:
        values = dict(
            run_id=str(uuid.uuid4()), ticker=TICKER, event_ticker=EVENT, series_ticker=SERIES, account_class="DIRECT",
            account_class_evidence_id="SYNTHETIC-ATTESTATION-1", fee_epoch_id="FEE-SCHEDULE-2026-07-07", fee_type="quadratic",
            taker_multiplier=D("1"), maker_multiplier=D("1"), fee_regime_change_pending=False, order1_limit_price=LIMIT,
            order2_limit_price=None, expected_commit="1" * 40, expected_tree="2" * 40, expected_parent="3" * 40,
            implementation_artifacts={"src/arb/venues/kalshi/f03_fee_semantics_runner.py": "4" * 64},
        )
        values.update(over)
        return F.F03RunPlanV1(**values)

    def _observed(self, plan) -> F.F03ObservedIdentityV1:
        return F.F03ObservedIdentityV1(plan.expected_commit, plan.expected_tree, plan.expected_parent, dict(plan.implementation_artifacts))

    def _balances(self, b0="1000.0000", b1="999.6638"):
        return [(b0, FILL_EPOCH - 100), (b0, FILL_EPOCH - 100), (b1, FILL_EPOCH + 5), (b1, FILL_EPOCH + 5)]

    def _experiment(self, rt, plan, observed=None, *, runs_root=None, prohibited=None):
        return F.F03FeeExperimentRunnerV1(runtime=rt, plan=plan, observed_identity=observed or self._observed(plan),
                                          run_artifact_root=runs_root or self.runs_root,
                                          prohibited_roots=prohibited or self.prohibited_roots)

    def _run(self, venue, plan=None, *, write_transport=None, seam=True):
        rt = self._runtime(venue, write_transport=write_transport, seam=seam)
        plan = plan or self._plan()
        experiment = self._experiment(rt, plan)
        result = experiment.run()
        return experiment, result

    def _locked_events(self, experiment):
        return list(experiment.stage3.normal_writer_acquisition.handle.events) if experiment.stage3 else []


class EndToEndCompositionTests(F03HarnessTestCase):
    def test_full_order1_partial_fill_cancel_and_scoped_question_results(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        scoped = mock.patch.object(WriterEligibilityGate, "issue_strategy1_gate_d_create_permit", autospec=True,
                                   side_effect=WriterEligibilityGate.issue_strategy1_gate_d_create_permit)
        with scoped as scoped_spy:
            experiment, result = self._run(venue)
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual(result.final_state, "COMPLETE")
        self.assertEqual(experiment.machine.history, (
            "BOOT_HOLD", "SOURCE_BOUND", "PREFLIGHT_READS", "B0_CHECKPOINT", "CURRENT_PROCESS_WRITER_ADMISSION",
            "WRITER_ELIGIBLE", "ORDER1_PREPARED", "ORDER1_SEND_BOUNDARY", "ORDER1_RECONCILING", "ORDER1_TERMINAL",
            "B1_CHECKPOINT", "ORDER2_DECISION", "FINAL_RECONCILIATION_ONLY", "COMPLETE"))
        self.assertEqual(scoped_spy.call_count, 1)
        # Exactly one CREATE and one exact-target CANCEL reached the write seam.
        self.assertEqual([w["operation_name"] for w in venue.writes], ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        create, cancel = venue.writes
        self.assertIs(create["canonical_body"]["post_only"], False)
        self.assertEqual(create["canonical_body"]["subaccount"], 1)
        self.assertEqual(create["canonical_body"]["count"], "1.00")
        self.assertEqual(create["canonical_body"]["price"], "0.5000")
        self.assertEqual(cancel["canonical_query"], {"subaccount": 1, "exchange_index": 0})
        self.assertEqual(cancel["venue_order_id"], experiment.orders[0].order_id)
        self.assertTrue(cancel["request_id"].startswith("req_"))
        # Durable T1 -> T2 -> T3 for both writes, T2 byte-identical to the wire payload.
        events = self._locked_events(experiment)
        t2 = [e for e in events if e.event_type.name == "REQUEST_PREPARED"]
        self.assertEqual([json.loads(e.payload_json)["operation_name"] for e in t2], ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        for event, wire in zip(t2, venue.writes):
            self.assertEqual(canonical_json_bytes(json.loads(event.payload_json)), canonical_json_bytes(wire))
        types = [e.event_type.name for e in events]
        self.assertEqual(types.count("WRITE_SEND_BOUNDARY_ENTERED"), 2)
        # Counters: T3 charges, physical seam invocations, acquired quantity.
        self.assertEqual((experiment.ledger.create_t3, experiment.ledger.cancel_t3), (1, 1))
        self.assertEqual(experiment.ledger.acquired_quantity, D("0.70"))
        # Whole-run GET accounting = observed transport + special orderbook seam + protected Stage-3 count.
        self.assertEqual(experiment.ledger.get_count, len(venue.read_calls) + venue.orderbook_calls + 72)
        self.assertLessEqual(experiment.ledger.get_count, 200)
        self.assertNotIn(RunnerOperation.GET_MARKET_ORDERBOOK, [op for op, _ in venue.read_calls])
        balance_preps = [p for op, p in venue.read_calls if op is RunnerOperation.GET_BALANCE]
        self.assertEqual(len(balance_preps), 4)
        self.assertTrue(all(type(p) is runner.F03BalancePreparedRequestV1 for p in balance_preps))
        # Questions: unique positive-rebate aggregate discriminator for the
        # tested maximal-vs-none pair; terminal not excluded -> Q04 inconclusive.
        q = {r["question_id"]: r for r in result.question_results}
        self.assertEqual(q["QF03-01"]["status"], "OBSERVED_MATCH")
        self.assertEqual(q["QF03-01"]["scope_mode"], "AGGREGATE_HYPOTHESIS")
        self.assertIn("NO_TERMINAL_CREDIT", q["QF03-01"]["joint_assumptions"])
        self.assertEqual(q["QF03-02"]["status"], "INCONCLUSIVE")
        self.assertEqual(q["QF03-03"]["status"], "INCONCLUSIVE")
        self.assertEqual(q["QF03-04"]["status"], "INCONCLUSIVE")
        self.assertEqual(q["QF03-05"]["status"], "INCONCLUSIVE")
        for r in q.values():
            self.assertIn("F03_CLOSURE", r["does_not_prove"])
            self.assertIn("UNIVERSAL_VENUE_FEE_POLICY", r["does_not_prove"])
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(result.shared_record)))
        (interval,) = result.shared_record["cash_fee_intervals"]
        self.assertEqual((interval["cash_fee_total"], interval["api_fee_cost_total"], interval["principal_total"]),
                         ("0.0122", "0.0122", "0.324"))
        self.assertEqual(interval["unique_discriminator_state"], "UNIQUE_MATCH")
        self.assertEqual(interval["matched_hypothesis_id"], "MAXIMAL_ZERO_NO_TERMINAL")
        self.assertEqual({h["id"]: h["predicted_total"] for h in interval["candidate_hypotheses"]},
                         {"MAXIMAL_ZERO_NO_TERMINAL": "0.0122", "NO_REBATE_ZERO_NO_TERMINAL": "0.0123",
                          "MAXIMAL_ZERO_FLOOR_TERMINAL": "0.0122"})
        fees = result.shared_record["orders"][0]["observed_fill_fees"]
        self.assertEqual([f["api_fee_cost"]["lexeme"] for f in fees], ["0.0070", "0.0052"])
        self.assertTrue(all(f["observed_rebate"] is None and f["identified_net_fee"] is None for f in fees))
        self.assertEqual([r["net_fee_hypothesis"] for r in fees[1]["hypothesis_rows"]], ["0.0052", "0.0053"])
        self.assertEqual(result.shared_record["account_class_evidence_id"], "SYNTHETIC-ATTESTATION-1")
        anchors = result.shared_record["orders"][0]["ledger_anchors"]
        self.assertEqual([a["action"] for a in anchors], ["CREATE", "CANCEL"])
        for a in anchors:
            self.assertEqual(a["t2"]["sequence"], a["t1"]["sequence"] + 1)
            self.assertEqual(a["t3"]["sequence"], a["t2"]["sequence"] + 1)
        b0 = [r for r in result.shared_record["read_observations"] if r.get("phase") == "B0"][0]
        self.assertEqual(b0, {"phase": "B0", "sufficient_existing_balance": True, "conservative_incremental_bound": "1.8176"})
        text = json.dumps(result.shared_record)
        for leak in ("1000.0000", "999.6638", "balance_dollars", "stable_balance"):
            self.assertNotIn(leak, text)
        self.assertIn("NO_SELL_OR_FLATTEN_PERFORMED", result.remaining_inventory_note)
        self.assertFalse(result.unresolved_active_exposure)

    def test_terminal_credit_exclusion_evidence_enables_q04_aggregate_consistency(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        experiment, result = self._run(venue, self._plan(terminal_credit_exclusion_evidence_id="SYNTHETIC-EXCLUSION-1"))
        q = {r["question_id"]: r for r in result.question_results}
        self.assertEqual(q["QF03-04"]["status"], "OBSERVED_MATCH")
        self.assertIs(q["QF03-04"]["independent_support_for_fee_hypothesis"], False)
        self.assertEqual(q["QF03-04"]["cash_evidence_ids"], q["QF03-01"]["cash_evidence_ids"])
        # Multi-fill interval: still never a per-fill identification.
        self.assertEqual(q["QF03-05"]["status"], "INCONCLUSIVE")
        del experiment

    def test_fx_cancel_race(self) -> None:
        venue = FakeDemoVenue(balances=self._balances(b1="999.7710"))
        venue.create_fill_plan = [("0.20", "0.4500", FILL_TIME, "0.0035"), ("0.20", "0.4800", FILL_TIME_2, "0.0035")]
        venue.cancel_concurrent_fill = ("0.10", "0.5000", "2026-08-17T13:00:01.000002Z", "0.0018")
        experiment, result = self._run(venue)
        self.assertIsNone(result.halt, result.halt)
        order = experiment.orders[0]
        self.assertEqual(order.cancel.classification, "TERMINAL")
        # Authoritative fills include the concurrent fill; the pre-cancel
        # remainder is never assumed refunded.
        self.assertEqual(experiment.ledger.acquired_quantity, D("0.50"))
        self.assertEqual(len(order.fills), 3)
        self.assertEqual(order.remaining_quantity, "0")
        self.assertEqual(venue.writes[1]["operation_name"], "CANCEL_ORDER_V2")

    def test_full_fill_before_cancel_sends_no_cancel(self) -> None:
        venue = FakeDemoVenue(balances=self._balances(b1="999.4825"))
        venue.create_fill_plan = [("0.40", "0.4500", FILL_TIME, "0.0070"), ("0.60", "0.4800", FILL_TIME_2, "0.0105")]
        experiment, result = self._run(venue)
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual([w["operation_name"] for w in venue.writes], ["CREATE_ORDER_V2"])
        self.assertEqual(experiment.orders[0].terminal_classification, "FULL_FILL")
        self.assertEqual(experiment.ledger.cancel_t3, 0)


class WriteAmbiguityAndLimitTests(F03HarnessTestCase):
    def test_fx_create_ambiguous(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        venue.create_raises = TimeoutError("synthetic timeout after send boundary")
        experiment, result = self._run(venue)
        self.assertEqual(result.final_state, "HALTED_HELD")
        self.assertEqual(result.halt.code, A.HaltCode.CREATE_RESULT_AMBIGUOUS)
        self.assertEqual(experiment.ledger.create_t3, 1)
        self.assertEqual(len(venue.writes), 1)  # no resend
        self.assertEqual(experiment.orders[0].create.classification, "ADAPTER_EXCEPTION")
        projection = experiment.stage3.normal_writer_acquisition.handle  # session ended -> closed handle
        self.assertTrue(projection.closed)
        with self.assertRaises(F.F03Halt):
            experiment.machine.require_write_state()

    def test_fx_create_t3_no_physical(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        real = WriterEligibilityGate.persist_send_boundary
        clock = self.inputs

        def _boundary_then_time_passes(gate, permit, locked):
            real(gate, permit, locked)
            clock.jump(11_000_000_000)  # durable T3 committed, then the action freshness expires

        with mock.patch.object(WriterEligibilityGate, "persist_send_boundary", autospec=True, side_effect=_boundary_then_time_passes):
            experiment, result = self._run(venue)
        self.assertEqual(result.final_state, "HALTED_HELD")
        self.assertEqual(experiment.orders[0].create.classification, "FRESHNESS_EXPIRED_BEFORE_ADAPTER")
        self.assertEqual(experiment.ledger.create_t3, 1)  # CREATE unit spent at durable T3
        self.assertEqual(venue.writes, [])  # zero physical sends
        self.assertEqual(experiment.ledger.create_transport_invocations, 0)

    def test_fx_cancel_ambiguous(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        venue.cancel_raises = TimeoutError("synthetic cancel timeout")
        experiment, result = self._run(venue)
        self.assertEqual(result.final_state, "HALTED_HELD")
        self.assertEqual(result.halt.code, A.HaltCode.CANCEL_RESULT_AMBIGUOUS)
        self.assertEqual(experiment.ledger.cancel_t3, 1)
        self.assertEqual([w["operation_name"] for w in venue.writes], ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        self.assertTrue(result.unresolved_active_exposure)
        q = {r["question_id"]: r for r in result.question_results}
        self.assertTrue(all(r["status"] in ("INCONCLUSIVE", "NOT_OBSERVABLE") for r in q.values()))

    def test_fx_create3(self) -> None:
        ledger = F.F03BudgetLedgerV1()
        ledger.create_t3 = 2
        with self.assertRaises(F.F03Halt) as ctx:
            F.execute_f03_create(locked=None, session_id="", capability=None, adapter=None, runtime=None, ticker=TICKER,
                                 projection=None, truth=None, yes_price=LIMIT, active_trusted_read_set_id="", plan_sha256="",
                                 ledger=ledger)
        self.assertEqual(ctx.exception.code, A.HaltCode.WRITE_LIMIT_CONSUMED)
        with self.assertRaises(F.F03Halt) as ctx:
            ledger.charge_create_t3()
        self.assertEqual(ctx.exception.code, A.HaltCode.WRITE_LIMIT_CONSUMED)
        ledger.cancel_t3 = 2
        with self.assertRaises(F.F03Halt) as ctx:
            ledger.require_cancel_slot()
        self.assertEqual(ctx.exception.code, A.HaltCode.WRITE_LIMIT_CONSUMED)

    def test_fx_get_201(self) -> None:
        ledger = F.F03BudgetLedgerV1(get_count=200)
        calls = []
        guard = F._F03CountedReadTransportV1(lambda *a: calls.append(a), ledger)
        with self.assertRaises(F.F03Halt) as ctx:
            guard(RunnerOperation.GET_MARKET, object(), object())
        self.assertEqual(ctx.exception.code, A.HaltCode.BUDGET_EXCEEDED)
        self.assertEqual(calls, [])  # refused before the inherited transport
        with self.assertRaises(F.F03Halt):
            F._F03CountedReadTransportV1(lambda *a: None, F.F03BudgetLedgerV1())(RunnerOperation.CREATE_ORDER_V2, None, None)
        with self.assertRaises(F.F03Halt):
            ledger.require_get_capacity(1, purpose="x")

    def test_fx_deadline_tail(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        real = runner._gate_d_reconcile_post_create
        clock = self.inputs

        def _reconcile_then_active_interval_closes(**kwargs):
            result = real(**kwargs)
            clock.jump(F.ACTIVE_WRITE_INTERVAL_NS + 1)
            return result

        with mock.patch.object(runner, "_gate_d_reconcile_post_create", side_effect=_reconcile_then_active_interval_closes):
            experiment, result = self._run(venue)
        self.assertEqual(result.halt.code, A.HaltCode.RUN_DEADLINE_EXCEEDED)
        self.assertEqual([w["operation_name"] for w in venue.writes], ["CREATE_ORDER_V2"])  # no tail cancel
        self.assertEqual(experiment.ledger.cancel_t3, 0)
        self.assertLessEqual(experiment.tail_end_ns - experiment.active_end_ns, F.RECONCILIATION_TAIL_NS)
        self.assertTrue(result.unresolved_active_exposure)  # operator recovery outside this contract

    def test_foreign_t2_substitution_reaches_no_wire(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        real = runner._gate_d_prepare_normal_write_binding

        def _forged(**kwargs):
            prepared = dict(kwargs["prepared"])
            body = dict(prepared["canonical_body"])
            body["price"] = "0.6000"
            prepared["canonical_body"] = body
            prepared["canonical_body_sha256"] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
            identity = {k: v for k, v in prepared.items() if k != "prepared_request_sha256"}
            prepared["prepared_request_sha256"] = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
            kwargs["prepared"] = prepared  # self-consistent same-shaped replacement
            return real(**kwargs)

        with mock.patch.object(runner, "_gate_d_prepare_normal_write_binding", side_effect=_forged):
            experiment, result = self._run(venue)
        self.assertEqual(experiment.orders[0].create.classification, "TRUSTED_T2_BINDING_INVALID")
        self.assertEqual(venue.writes, [])
        self.assertEqual(result.final_state, "HALTED_HELD")

    def test_mutated_active_domain_commitment_blocks_before_transport(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        real = F.active_domain_commitment

        def _corrupt(contract, binding):
            out = dict(real(contract, binding))
            out["subaccount"] = out["subaccount"] + 1
            return out

        with mock.patch.object(F, "active_domain_commitment", side_effect=_corrupt):
            experiment, result = self._run(venue)
        self.assertEqual(venue.writes, [])
        self.assertIn(experiment.orders[0].create.classification, {
            "ACTIVE_DOMAIN_PERMIT_MISMATCH", "NORMAL_WRITER_PERMIT_DOMAIN_MISMATCH", "ACTIVE_DOMAIN_CONTRACT_MISMATCH",
            "PERMIT_ISSUANCE_FAILED", "ELIGIBLE_NOT_SENT"})
        self.assertEqual(result.final_state, "HALTED_HELD")

    def test_create_never_reaches_generic_permit_surface(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        venue.create_fill_plan = [("0.40", "0.4500", FILL_TIME, "0.0070"), ("0.60", "0.4800", FILL_TIME_2, "0.0105")]

        def _forbidden(*args, **kwargs):
            raise AssertionError("generic permit surface reached by F03 CREATE")

        with mock.patch.object(WriterEligibilityGate, "issue_permit", side_effect=_forbidden), \
                mock.patch.object(F, "issue_and_persist_write_permit", side_effect=_forbidden):
            experiment, result = self._run(venue, self._plan())
        self.assertEqual(experiment.orders[0].create.classification, "TERMINAL")
        self.assertEqual(len(venue.writes), 1)
        del result


class PreflightGateTests(F03HarnessTestCase):
    def _assert_no_writes(self, venue, experiment) -> None:
        self.assertEqual(venue.writes, [])
        self.assertEqual(experiment.ledger.create_t3, 0)
        self.assertIsNone(experiment.stage3)

    def test_fx_working_bound(self) -> None:
        venue = FakeDemoVenue(balances=self._balances(), extra_orders=[{
            "order_id": "unrelated-1", "client_order_id": str(uuid.uuid4()), "ticker": "KXOTHER-1", "side": "yes",
            "status": "resting", "fill_count_fp": "0.00", "remaining_count_fp": "1.00", "initial_count_fp": "1.00",
            "subaccount": 1, "subaccount_number": 1, "exchange_index": 0, "yes_price_dollars": "0.1000"}])
        experiment, result = self._run(venue)
        self.assertEqual(result.halt.code, A.HaltCode.BASELINE_OPEN_ORDER_CONFLICT)
        self._assert_no_writes(venue, experiment)

    def test_fx_unrelated_settlement(self) -> None:
        venue = FakeDemoVenue(balances=self._balances(), extra_positions=[{
            "ticker": "KXOTHER-1", "subaccount": 1, "subaccount_number": 1, "exchange_index": 0,
            "position_count_fp": "2.00", "yes_price_dollars": "0.3000", "position_as_of_utc": "2026-08-17T12:00:00.000000Z"}])
        experiment, result = self._run(venue)
        self.assertEqual(result.halt.code, A.HaltCode.UNRELATED_ACTIVITY_PRESENT)
        self._assert_no_writes(venue, experiment)
        q = {r["question_id"]: r for r in result.question_results}
        self.assertEqual(q["QF03-01"]["status"], "INCONCLUSIVE")

    def test_fx_pagecap(self) -> None:
        venue = FakeDemoVenue(balances=self._balances(), fill_cursor_loop=True)
        experiment, result = self._run(venue)
        self.assertEqual(result.halt.code, A.HaltCode.PAGINATION_LIMIT_EXHAUSTED)
        fills_pages = [p for op, p in venue.read_calls if op is RunnerOperation.GET_FILLS]
        self.assertEqual(len(fills_pages), 4)  # route page cap, no extra request
        self._assert_no_writes(venue, experiment)

    def test_fx_insufficient_balance(self) -> None:
        venue = FakeDemoVenue(balances=[("1.0000", 1), ("1.0000", 1)])
        experiment, result = self._run(venue)
        self.assertEqual(result.halt.code, A.HaltCode.INSUFFICIENT_EXISTING_BALANCE)
        self._assert_no_writes(venue, experiment)

    def test_account_class_unresolved_permits_reads_only(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        experiment, result = self._run(venue, self._plan(account_class="UNRESOLVED"))
        self.assertEqual(result.halt.code, A.HaltCode.ACCOUNT_CLASS_UNRESOLVED)
        self._assert_no_writes(venue, experiment)

    def test_market_not_discriminating_sends_nothing(self) -> None:
        venue = FakeDemoVenue(balances=self._balances(), no_levels=((D("0.55"), D("0.40")),))
        experiment, result = self._run(venue)
        self.assertEqual(result.halt.code, A.HaltCode.MARKET_NOT_DISCRIMINATING)
        self._assert_no_writes(venue, experiment)

    def test_primary_subaccount_zero_is_prohibited(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        rt = self._runtime(venue)
        binding0 = ledger_binding.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=ACCOUNT,
                                                          subaccount=0, exchange_index=0)
        fake_rt = mock.Mock(spec=["domain_binding", "active_contract"])
        fake_rt.domain_binding = binding0
        fake_rt.active_contract = rt.active_contract
        with self.assertRaises(F.F03Halt) as ctx:
            F.verify_domain_and_origin(fake_rt)
        self.assertEqual(ctx.exception.code, A.HaltCode.HISTORICAL_PRIMARY_DOMAIN_PROHIBITED)

    def test_source_binding_mismatch_halts_before_any_read(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        rt = self._runtime(venue)
        plan = self._plan()
        observed = F.F03ObservedIdentityV1("9" * 40, plan.expected_tree, plan.expected_parent, dict(plan.implementation_artifacts))
        result = self._experiment(rt, plan, observed).run()
        self.assertEqual(result.halt.code, A.HaltCode.CANONICAL_BASE_MISMATCH)
        self.assertEqual(venue.read_calls, [])

    def test_plan_rejects_unbounded_or_ambiguous_inputs(self) -> None:
        for over, code in (
            (dict(order1_limit_price=D("0.81")), A.HaltCode.BUDGET_EXCEEDED),
            (dict(order1_limit_price=D("0.5")), A.HaltCode.BUDGET_EXCEEDED),
            (dict(taker_multiplier=D("2")), A.HaltCode.FEE_REGIME_UNRESOLVED),
            (dict(maker_multiplier=D("1.5")), A.HaltCode.FEE_REGIME_UNRESOLVED),
            (dict(fee_regime_change_pending=True), A.HaltCode.FEE_REGIME_UNRESOLVED),
            (dict(fee_type="flat"), A.HaltCode.FEE_REGIME_UNRESOLVED),
            (dict(run_id="NOT-A-UUID"), A.HaltCode.SOURCE_BINDING_UNRESOLVED),
            (dict(account_class="GUESSED"), A.HaltCode.ACCOUNT_CLASS_UNRESOLVED),
        ):
            with self.subTest(over=over), self.assertRaises(F.F03Halt) as ctx:
                self._plan(**over)
            self.assertEqual(ctx.exception.code, code)

    def test_completed_run_id_cannot_be_re_executed(self) -> None:
        venue = FakeDemoVenue(balances=[("1.0000", 1), ("1.0000", 1)])
        plan = self._plan()
        rt = self._runtime(venue)
        self._experiment(rt, plan).run()
        with self.assertRaises(F.F03Halt):
            self._experiment(rt, plan)


def _snapshot(ordinal, dollars, ts, *, pid="proc_" + "a" * 32, domain=None):
    domain = domain or ledger_binding.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=ACCOUNT, subaccount=1, exchange_index=0)
    value = D(dollars)
    return runner.F03BalanceSnapshotV1(
        schema_revision=1, observation_id=f"f03bal_{ordinal:032x}", operation="GET_BALANCE",
        source_binding_id=runner.F03_BALANCE_SOURCE_BINDING_ID, source_raw_sha256=runner.F03_BALANCE_SOURCE_RAW_SHA256,
        request_id=f"req_{ordinal:032x}", request_identity_sha256=f"{ordinal:064x}", process_instance_id=pid,
        domain_binding_id=domain.binding_id, domain_binding_sha256=domain.binding_sha256, subaccount=1, exchange_index=0,
        request_ordinal=ordinal, balance_dollars_lexeme=dollars, balance_decimal=value,
        balance_canonical_text=runner._f03_canonical_decimal_text(value), balance_legacy_cents=0, portfolio_value_legacy_cents=0,
        updated_ts=ts, balance_breakdown_present=False, balance_breakdown=(), request_started_monotonic_ns=1,
        response_completed_monotonic_ns=2, request_started_utc="2026-08-17T13:00:00.000000Z",
        response_completed_utc="2026-08-17T13:00:00.000001Z", request_count=1, automatic_retry_count=0, followed_redirect_count=0)


class _ScriptedReader:
    def __init__(self, items) -> None:
        self.items = list(items)
        self.calls = []

    def __call__(self, runtime, *, request_ordinal):
        self.calls.append(request_ordinal)
        item = self.items.pop(0)
        if isinstance(item, tuple):
            dollars, ts = item
            return _snapshot(request_ordinal, dollars, ts)
        exc = RunnerError(RunnerFailureCode.RESPONSE_SCHEMA_INVALID, detail="synthetic")
        exc._arb_f03_balance_request_count = item
        raise exc


class BalanceCheckpointTests(unittest.TestCase):
    def _run(self, items, *, ledger=None, boundary="B0", latest=None):
        ledger = ledger or F.F03BudgetLedgerV1()
        reader = _ScriptedReader(items)
        record = F.F03BalanceCheckpointerV1(ledger).run(object(), boundary=boundary, latest_fill_execution_utc=latest, reader=reader)
        return record, reader, ledger

    def test_fx_checkpoint_zero_successes(self) -> None:
        with mock.patch.object(runner, "evaluate_f03_balance_checkpoint_v1", side_effect=AssertionError("must not be called")):
            record, reader, _ = self._run([1])
        self.assertEqual(record.state, "FAILED")
        self.assertFalse(record.evaluator_called)
        self.assertEqual(len(reader.calls), 1)  # no automatic retry
        self.assertEqual(F.checkpoint_zero_success_record("B1").state, "FAILED")

    def test_fx_checkpoint_one_success(self) -> None:
        ledger = F.F03BudgetLedgerV1(balance_gets=8)
        record, reader, _ = self._run([("1", 10)], ledger=ledger)
        self.assertEqual(record.state, "NOT_STABLE")
        self.assertTrue(record.evaluator_called)
        self.assertEqual(record.successes, 1)
        self.assertEqual(F.checkpoint_state(1, 0, None), "NOT_STABLE")

    def test_fx_checkpoint_two_equal(self) -> None:
        record, reader, _ = self._run([("1", 10), ("1.0000", 10)])
        self.assertEqual(record.state, "STABLE")
        self.assertEqual(record._private_stable_balance, D("1"))
        self.assertNotIn("1.0000", repr(record))

    def test_fx_checkpoint_three_last_equal(self) -> None:
        record, reader, _ = self._run([("1", 10), ("2", 11), ("2.0", 11)])
        self.assertEqual(record.state, "STABLE")
        self.assertEqual(record.attempts, 3)

    def test_fx_checkpoint_three_unequal(self) -> None:
        record, reader, _ = self._run([("1", 10), ("2", 11), ("3", 12)])
        self.assertEqual(record.state, "NOT_STABLE")
        self.assertEqual(len(reader.calls), 3)

    def test_fx_checkpoint_failure_plus_equal(self) -> None:
        record, reader, _ = self._run([("1", 10), 1])
        self.assertEqual(record.state, "FAILED")
        self.assertTrue(record.evaluator_called)
        evaluated = runner.evaluate_f03_balance_checkpoint_v1((_snapshot(1, "1", 10), _snapshot(2, "1", 10)), boundary="B0", failed_read_count=1)
        self.assertEqual(F.checkpoint_state(2, 1, evaluated), "FAILED")

    def test_fx_timestamp_regression(self) -> None:
        record, _, _ = self._run([("1", 100), ("1", 99)])
        self.assertEqual(record.halt_code, A.HaltCode.BALANCE_TIMESTAMP_REGRESSION.value)
        self.assertNotEqual(record.state, "STABLE")

    def test_fx_stale_watermark(self) -> None:
        latest = datetime.fromtimestamp(100, tz=timezone.utc)
        record, _, _ = self._run([("1", 99), ("1", 99)], latest=latest)
        self.assertEqual(record.state, "NOT_STABLE")
        self.assertTrue(record.stale_by_fill_watermark)

    def test_fx_no_wall_freshness_gate(self) -> None:
        record, _, _ = self._run([("1", 100), ("1", 100)])
        self.assertEqual(record.state, "STABLE")  # no client-wall freshness claim or gate

    def test_fx_fourth_checkpoint_attempt(self) -> None:
        ledger = F.F03BudgetLedgerV1()
        checkpointer = F.F03BalanceCheckpointerV1(ledger)
        checkpointer.run(object(), boundary="B0", reader=_ScriptedReader([("1", 1), ("2", 2), ("3", 3)]))
        with self.assertRaises(F.F03Halt) as ctx:  # never a fresh label / reset for the same bound
            checkpointer.run(object(), boundary="B0", reader=_ScriptedReader([("3", 3)]))
        self.assertEqual(ctx.exception.code, A.HaltCode.BUDGET_EXCEEDED)
        self.assertEqual(F.BALANCE_ATTEMPTS_PER_CHECKPOINT_MAX, 3)

    def test_fx_tenth_balance_get(self) -> None:
        reader = _ScriptedReader([("1", 1)])
        with self.assertRaises(F.F03Halt) as ctx:
            F.F03BalanceCheckpointerV1(F.F03BudgetLedgerV1(balance_gets=9)).run(object(), boundary="B0", reader=reader)
        self.assertEqual(ctx.exception.code, A.HaltCode.BUDGET_EXCEEDED)
        self.assertEqual(reader.calls, [])

    def test_request_ordinals_strictly_increase_for_the_run(self) -> None:
        ledger = F.F03BudgetLedgerV1()
        cp = F.F03BalanceCheckpointerV1(ledger)
        r0 = _ScriptedReader([("5", 1), ("5", 1)])
        r1 = _ScriptedReader([("4", 2), ("4", 2)])
        cp.run(object(), boundary="B0", reader=r0)
        cp.run(object(), boundary="B1", reader=r1)
        self.assertEqual(r0.calls + r1.calls, [1, 2, 3, 4])
        self.assertEqual(ledger.balance_gets, 4)


class InstalledBalanceReaderIntegrationTests(F03HarnessTestCase):
    def _guarded(self, venue, *, end=None):
        rt = self._runtime(venue, seam=False)
        ledger = F.F03BudgetLedgerV1(get_count=10)
        frt, guard = F.build_f03_runtime_v1(rt, ledger, active_end_monotonic_ns=end if end is not None else 10 ** 17)
        return frt, ledger

    def test_fx_post_boundary_failure(self) -> None:
        venue = FakeDemoVenue(balances=[RawOperationResponseV1(http_status=500, content_type="application/json", body_bytes=b"{}")])
        frt, ledger = self._guarded(venue)
        record = F.F03BalanceCheckpointerV1(ledger).run(frt, boundary="B0")
        self.assertEqual(record.state, "FAILED")
        self.assertEqual(record.attempts, 1)
        self.assertEqual(record.consumed_balance_gets, 1)
        self.assertEqual(ledger.get_count, 11)  # charged, never refunded
        self.assertEqual(venue.balance_calls, 1)  # no retry

    def test_fx_pre_boundary_failure(self) -> None:
        venue = FakeDemoVenue(balances=[("1", 1)])
        frt, ledger = self._guarded(venue)
        frt = dataclasses.replace(frt, experiment_absolute_end_monotonic_ns=0)  # deadline already passed
        record = F.F03BalanceCheckpointerV1(ledger).run(frt, boundary="B0")
        self.assertEqual(record.state, "FAILED")
        self.assertEqual(record.attempts, 1)
        self.assertEqual(record.consumed_balance_gets, 0)
        self.assertEqual(ledger.get_count, 10)
        self.assertEqual(venue.balance_calls, 0)

    def test_installed_reader_stable_checkpoint_and_sanitized_projection(self) -> None:
        venue = FakeDemoVenue(balances=[("1234.5600", 7), ("1234.56", 7)])
        frt, ledger = self._guarded(venue)
        record = F.F03BalanceCheckpointerV1(ledger).run(frt, boundary="B0")
        self.assertEqual(record.state, "STABLE")
        shared = json.dumps(record.shared_projection())
        self.assertNotIn("1234", shared)
        A.assert_shared_evidence_sanitized(json.loads(shared))
        self.assertEqual(ledger.get_count, 12)


class ActiveDomainCancelAndCreateBuilderTests(unittest.TestCase):
    def test_fx_active_domain_cancel(self) -> None:
        domain = ledger_binding.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=ACCOUNT,
                                                         subaccount=2, exchange_index=3)
        cid = str(uuid.UUID(int=77, version=4))
        with mock.patch.object(quote_lifecycle, "build_cancel_prepared_payload", side_effect=AssertionError("protected fixed-domain helper")), \
                mock.patch.object(runner, "build_cancel_prepared_payload", side_effect=AssertionError("protected fixed-domain helper")):
            prepared = F.build_f03_active_cancel_prepared_payload(request_id="req_" + "a" * 32, venue_order_id="ord-9",
                                                                  client_order_id=cid, domain_binding=domain)
        self.assertEqual(prepared["canonical_query"], {"subaccount": 2, "exchange_index": 3})
        self.assertEqual(prepared["request_id"], "req_" + "a" * 32)
        self.assertEqual(set(prepared), set(runner._GATE_D_T2_PREPARED_KEYS))
        identity = {k: v for k, v in prepared.items() if k != "prepared_request_sha256"}
        self.assertEqual(prepared["prepared_request_sha256"], hashlib.sha256(canonical_json_bytes(identity)).hexdigest())
        self.assertEqual(prepared["adapter_payload_schema_id"], runner._GATE_D_CANCEL_ADAPTER_PAYLOAD_SCHEMA_ID)
        self.assertEqual(runner._gate_d_wire_query_string(prepared["canonical_query"]), "exchange_index=3&subaccount=2")
        for bad in (dict(request_id="nope"), dict(venue_order_id=".."), dict(client_order_id="X")):
            args = dict(request_id="req_" + "a" * 32, venue_order_id="ord-9", client_order_id=cid, domain_binding=domain)
            args.update(bad)
            with self.assertRaises(F.F03Halt):
                F.build_f03_active_cancel_prepared_payload(**args)

    def test_fx_create_only_post_only(self) -> None:
        domain = ledger_binding.ExecutionDomainBindingV1(venue="KALSHI", environment="KALSHI_DEMO", account_scope_ref=ACCOUNT,
                                                         subaccount=1, exchange_index=0)
        vb = quote_lifecycle.VenueBindingV2(domain_binding=domain, exchange_index_wire_policy="EMPIRICALLY_BOUND_AUTOROUTE",
                                            adapter_payload_schema_id=runner._GATE_D_CREATE_ADAPTER_PAYLOAD_SCHEMA_ID)
        cid = str(uuid.UUID(int=78, version=4))
        protected, copied = F.build_non_post_only_create_body(ticker=TICKER, client_order_id=cid, yes_price=LIMIT,
                                                              expiration_time=1_800_000_000, venue_binding=vb)
        self.assertIs(protected["post_only"], True)
        self.assertEqual({k for k in protected if protected[k] != copied[k]}, {"post_only"})
        self.assertIs(copied["post_only"], False)
        prepared = quote_lifecycle.build_create_prepared_payload(request_id="req_" + "b" * 32, environment="KALSHI_DEMO",
                                                                 client_order_id=cid, canonical_body=copied, venue_binding=vb)
        self.assertEqual(prepared["canonical_body_sha256"], hashlib.sha256(canonical_json_bytes(copied)).hexdigest())
        self.assertNotEqual(prepared["canonical_body_sha256"], hashlib.sha256(canonical_json_bytes(protected)).hexdigest())
        with self.assertRaises(F.F03Halt):  # a silently rounded 4dp price is rejected
            F.build_non_post_only_create_body(ticker=TICKER, client_order_id=cid, yes_price=D("0.50001"),
                                              expiration_time=1, venue_binding=vb)
        self.assertIn(".issue_strategy1_gate_d_create_permit(", inspect.getsource(F.execute_f03_create))
        self.assertNotIn("issue_and_persist_write_permit(", inspect.getsource(F.execute_f03_create))
        self.assertIn("issue_and_persist_write_permit(", inspect.getsource(F.execute_f03_cancel))


class ReadSurfaceTests(unittest.TestCase):
    def test_fx_orderbook_special(self) -> None:
        source = inspect.getsource(F.F03ObservationCampaignV1)
        self.assertIn("issue_orderbook(", source)
        self.assertNotIn("GET_MARKET_ORDERBOOK, ordinal", source)
        self.assertNotIn(RunnerOperation.GET_MARKET_ORDERBOOK, runner._LiveDemoSignedReadTransport._ALLOWED_OPERATIONS)
        seam_source = inspect.getsource(F._F03CountedOrderbookSeamV1)
        self.assertIn("self._inner.execute(plan, deadline)", seam_source)

    def test_fx_balance_not_stage3(self) -> None:
        self.assertNotIn("GET_BALANCE", {m.value for m in runner.ActivePreReleaseReadOperationV2})
        self.assertNotIn(RunnerOperation.GET_BALANCE, runner.PRE_RELEASE_READ_OPERATIONS)
        self.assertEqual(len(runner.ActivePreReleaseReadOperationV2), 8)
        self.assertIn("read_f03_balance_snapshot_v1", inspect.getsource(F.F03BalanceCheckpointerV1))

    def test_portfolio_queries_carry_no_ticker_or_order_filter(self) -> None:
        for op in (runner.ActivePreReleaseReadOperationV2.GET_ORDERS, runner.ActivePreReleaseReadOperationV2.GET_FILLS,
                   runner.ActivePreReleaseReadOperationV2.GET_POSITIONS):
            query = runner._active_v2_canonical_query(op, subaccount=1, exchange_index=0, cursor_in="")
            self.assertEqual([k for k, _ in query], ["subaccount", "exchange_index", "limit"])


class StateMachineTests(unittest.TestCase):
    def test_only_listed_transitions_and_absorbing_hold(self) -> None:
        m = F.F03StateMachineV1()
        with self.assertRaises(F.F03Halt):
            m.advance(F.F03State.ORDER1_PREPARED)
        m.advance(F.F03State.SOURCE_BOUND)
        m.halt()
        self.assertIs(m.state, F.F03State.HALTED_HELD)
        for state in F.F03State:
            if state is F.F03State.HALTED_HELD:
                continue
            with self.assertRaises(F.F03Halt):
                m.advance(state)
        with self.assertRaises(F.F03Halt):
            m.require_write_state()

    def test_halt_codes_are_closed(self) -> None:
        with self.assertRaises(TypeError):
            F.F03Halt("NOT_A_CODE")
        self.assertEqual(len(A.HaltCode), 33)

    def test_counters_and_polls_are_bounded(self) -> None:
        ledger = F.F03BudgetLedgerV1()
        for _ in range(30):
            ledger.poll("ORDER", "k")
        with self.assertRaises(F.F03Halt):
            ledger.poll("ORDER", "k")
        ledger.reconciliation_round(0)
        with self.assertRaises(F.F03Halt):
            ledger.reconciliation_round(1)  # < 10 s spacing
        ledger.add_acquired(D("2.00"))
        with self.assertRaises(F.F03Halt):
            ledger.add_acquired(D("0.01"))


class EvidenceExportTests(unittest.TestCase):
    def test_containment_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            with self.assertRaises(F.F03Halt):
                F.require_output_containment(repo / "out", prohibited_roots=[repo])
            existing = root / "exists"
            existing.mkdir()
            with self.assertRaises(F.F03Halt):
                F.require_output_containment(existing, prohibited_roots=[repo])
            self.assertEqual(F.require_output_containment(root / "fresh", prohibited_roots=[repo]), (root / "fresh").resolve())

    def test_symlink_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "real"
            target.mkdir()
            link = root / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                try:  # Windows without symlink privilege: an unprivileged directory junction
                    import _winapi
                    _winapi.CreateJunction(str(target), str(link))
                except (ImportError, AttributeError, OSError):
                    self.skipTest("neither symlink nor junction creation is available on this host")
            with self.assertRaises(F.F03Halt):
                F.require_output_containment(link / "out", prohibited_roots=[root / "repo"])


def _code_only(source: str) -> str:
    import io
    import tokenize
    kept = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT):
            continue
        kept.append(tok.string)
    return " ".join(kept).replace(" (", "(").replace(" .", ".").replace(". ", ".")


class StaticConformanceTests(unittest.TestCase):
    def test_runner_owns_no_transport_signer_or_direct_authority(self) -> None:
        # Code tokens only: docstrings/comments that DESCRIBE prohibitions are excluded.
        source = _code_only(inspect.getsource(F))
        for forbidden in ("_perform_get(", "_auth_headers(", "_d07_demo_signed_auth_headers(", "NormalWriterPermit(",
                          "_NormalWriteOperationBindingV1(", "import socket", "import ssl", "http.client", "urllib",
                          "os.environ", "build_cancel_prepared_payload(", "monkeypatch", "unittest", "_PERMIT_CONSTRUCTION_KEY",
                          "_NORMAL_WRITE_BINDING_KEY", "_CAPABILITY_ISSUANCE_KEY", "issue_permit(", "_gate_d_execute_create(",
                          "_gate_d_execute_cancel(", ".transport._arm", "requests."):
            self.assertNotIn(forbidden, source, forbidden)
        for required in ("_gate_d_prepare_normal_write_binding(", "_gate_d_invoke_normal_write_adapter(",
                         "_require_active_gate_d_pre_adapter_equality(", "_gate_d_classify_create_result(",
                         "_gate_d_classify_cancel_result(", "check_cancel_conservation(", "_gate_d_reconcile_post_create(",
                         "build_account_aggregate_authority_expectation(", "read_f03_balance_snapshot_v1",
                         "evaluate_f03_balance_checkpoint_v1(", "project_f03_balance_snapshot_evidence_v1("):
            self.assertIn(required, source, required)

    def test_no_import_time_activity(self) -> None:
        tree = ast.parse(inspect.getsource(F))
        for node in tree.body:
            self.assertIsInstance(node, (ast.Expr, ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign,
                                         ast.AnnAssign, ast.Assert), ast.dump(node)[:80])
            if isinstance(node, ast.Expr):
                self.assertIsInstance(node.value, ast.Constant)  # docstring only
        self.assertEqual(F.__all__, [])

    def test_protected_dependencies_unchanged(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for rel, blob in PROTECTED_BLOBS.items():
            data = (root / rel).read_bytes()
            computed = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            self.assertEqual(computed, blob, rel)


@contextlib.contextmanager
def _socket_stack(test, venue, sent_log):
    """Fakes ONLY the lowest DNS/socket/TLS boundary under the sanctioned
    ``_DemoNormalWriteTransport``; responses are built from the exact bytes
    the production transport put on the wire."""

    class _State:
        sent = bytearray()
        chunks = None

    def _respond() -> bytes:
        head, _, body = bytes(_State.sent).partition(b"\r\n\r\n")
        lines = head.decode("ascii").split("\r\n")
        headers = dict(line.split(": ", 1) for line in lines[1:])
        sent_log.append((lines[0], headers, body))
        method, target, _ = lines[0].split(" ")
        if method == "POST":
            payload, status, reason = venue.apply_create(json.loads(body.decode("utf-8"))), 201, "Created"
        else:
            payload, status, reason = venue.apply_cancel(target.split("?")[0].rsplit("/", 1)[-1]), 200, "OK"
        data = json.dumps(payload).encode("utf-8")
        return (f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\n"
                f"Connection: close\r\n\r\n").encode("ascii") + data

    class _TLS:
        def settimeout(self, value):
            pass

        def do_handshake(self):
            pass

        def send(self, view):
            _State.sent += bytes(view)
            return len(view)

        def recv_into(self, buffer):
            if _State.chunks is None:
                data = _respond()
                _State.chunks = [data[i:i + 64] for i in range(0, len(data), 64)]
            if not _State.chunks:
                return 0
            chunk = _State.chunks.pop(0)
            buffer[:len(chunk)] = chunk
            return len(chunk)

        def close(self):
            _State.sent = bytearray()
            _State.chunks = None

    class _Raw:
        def settimeout(self, value):
            pass

        def connect(self, address):
            test.assertEqual(address, ("203.0.113.9", 443))

        def close(self):
            pass

    class _Ctx:
        def wrap_socket(self, sock, *, server_hostname, do_handshake_on_connect):
            test.assertEqual(server_hostname, "external-api.demo.kalshi.co")
            return _TLS()

    def _resolve(host, port, *, deadline, monotonic_clock_ns):
        test.assertEqual((host, port), ("external-api.demo.kalshi.co", 443))
        return [(socket.AF_INET, ("203.0.113.9", 443))]

    with mock.patch.object(runner, "_d07_live_signed_get_resolve_addresses", _resolve), \
            mock.patch("socket.socket", lambda *a, **k: _Raw()), \
            mock.patch("ssl.create_default_context", lambda *a, **k: _Ctx()):
        yield


class SanctionedWireConformanceTests(F03HarnessTestCase):
    def test_exact_active_query_and_body_reach_the_sanctioned_wire(self) -> None:
        """Unit evidence: Stage-3 through the protected fake acquirer seam."""
        self._sanctioned_wire(seam=True)

    def test_live_acquirer_exact_active_query_and_body_reach_the_sanctioned_wire(self) -> None:
        """Correction01 F04: NO acquirer seam -- the raw protected live Stage-3
        acquirer drives admission, then the sanctioned write transport."""
        venue = self._sanctioned_wire(seam=False)
        self.assertEqual((venue.status_calls, venue.udt_calls), (2, 2))

    def _sanctioned_wire(self, *, seam):
        venue = FakeDemoVenue(balances=self._balances())
        pem, public = _synthetic_rsa()
        rt = self._runtime(venue, seam=seam)
        self.assertEqual(rt.trusted_dynamic_read_acquirer_test_seam is None, not seam)
        transport = runner._DemoNormalWriteTransport(
            wall_clock=self.inputs.clock, monotonic_clock_ns=rt.monotonic_clock_ns,
            process_instance_id=rt.normal_gate.process_instance_id,
            env={"KALSHI_DEMO_API_KEY_ID": SYNTH_KEY_ID, "KALSHI_DEMO_PRIVATE_KEY_PEM": pem})
        rt = dataclasses.replace(rt, normal_write_transport=transport)
        plan = self._plan()
        sent: list = []
        with _socket_stack(self, venue, sent):
            experiment = self._experiment(rt, plan)
            result = experiment.run()
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual(transport.physical_send_attempts, 2)
        (create_line, create_headers, create_body), (cancel_line, cancel_headers, cancel_body) = sent
        self.assertEqual(create_line, "POST /trade-api/v2/portfolio/events/orders HTTP/1.1")
        body = json.loads(create_body.decode("utf-8"))
        self.assertIs(body["post_only"], False)
        self.assertEqual((body["subaccount"], body["count"], body["price"]), (1, "1.00", "0.5000"))
        order_id = experiment.orders[0].order_id
        self.assertEqual(cancel_line, f"DELETE /trade-api/v2/portfolio/events/orders/{order_id}?exchange_index=0&subaccount=1 HTTP/1.1")
        self.assertEqual(cancel_body, b"")
        from cryptography.hazmat.primitives import hashes as _hashes
        from cryptography.hazmat.primitives.asymmetric import padding as _padding
        for (line, headers, _), path in ((sent[0], "/trade-api/v2/portfolio/events/orders"),
                                         (sent[1], f"/trade-api/v2/portfolio/events/orders/{order_id}")):
            self.assertEqual(headers["KALSHI-ACCESS-KEY"], SYNTH_KEY_ID)
            method = line.split(" ")[0]
            public.verify(base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),
                          (headers["KALSHI-ACCESS-TIMESTAMP"] + method + path).encode("ascii"),
                          _padding.PSS(mgf=_padding.MGF1(_hashes.SHA256()), salt_length=32), _hashes.SHA256())
        text = json.dumps(result.shared_record)
        self.assertNotIn("KALSHI-ACCESS", text)
        self.assertNotIn("BEGIN", text)
        return venue


RUNNER_FIXTURE_CASES = (
    "FX_CHECKPOINT_ZERO_SUCCESSES", "FX_CHECKPOINT_ONE_SUCCESS", "FX_CHECKPOINT_TWO_EQUAL",
    "FX_CHECKPOINT_THREE_LAST_EQUAL", "FX_CHECKPOINT_THREE_UNEQUAL", "FX_CHECKPOINT_FAILURE_PLUS_EQUAL",
    "FX_TIMESTAMP_REGRESSION", "FX_STALE_WATERMARK", "FX_NO_WALL_FRESHNESS_GATE", "FX_POST_BOUNDARY_FAILURE",
    "FX_PRE_BOUNDARY_FAILURE", "FX_FOURTH_CHECKPOINT_ATTEMPT", "FX_TENTH_BALANCE_GET", "FX_GET_201", "FX_CREATE3",
    "FX_CREATE_T3_NO_PHYSICAL", "FX_CREATE_AMBIGUOUS", "FX_CANCEL_AMBIGUOUS", "FX_CANCEL_RACE", "FX_PAGECAP",
    "FX_ACTIVE_DOMAIN_CANCEL", "FX_CREATE_ONLY_POST_ONLY", "FX_ORDERBOOK_SPECIAL", "FX_BALANCE_NOT_STAGE3",
    "FX_INSUFFICIENT_BALANCE", "FX_DEADLINE_TAIL", "FX_WORKING_BOUND", "FX_UNRELATED_SETTLEMENT",
)


class FixtureOwnershipTests(unittest.TestCase):
    def test_every_runner_owned_oracle_case_has_a_seam_test(self) -> None:
        names = set()
        for case in (EndToEndCompositionTests, WriteAmbiguityAndLimitTests, PreflightGateTests, BalanceCheckpointTests,
                     InstalledBalanceReaderIntegrationTests, ActiveDomainCancelAndCreateBuilderTests, ReadSurfaceTests):
            names |= {n[len("test_"):].upper() for n in dir(case) if n.startswith("test_fx_")}
        self.assertEqual(set(RUNNER_FIXTURE_CASES), names)
        self.assertEqual(len(RUNNER_FIXTURE_CASES), 28)


class RunLevelEvidenceAndIsolationTests(F03HarnessTestCase):
    def test_shared_export_and_private_evidence_gate(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        experiment, result = self._run(venue)
        path = experiment.export_shared_evidence(result)
        self.assertEqual(path.parent, (self.runs_root / experiment.plan.run_id / "shared").resolve())
        data = path.read_bytes()
        A.validate_fee_experiment_run_v1(A.strict_json_loads(data))
        self.assertNotIn(b"1000.0000", data)
        with self.assertRaises(F.F03Halt):  # no overwrite / replay of a run folder
            experiment.export_shared_evidence(result)
        with self.assertRaises(F.F03Halt):  # never inside the canonical repository
            F.export_shared_run_evidence(result.shared_record, output_dir=self.repository_root / "f03_out",
                                         prohibited_roots=[self.repository_root])
        with self.assertRaises(F.F03Halt) as ctx:
            experiment.export_private_balance_evidence()
        self.assertEqual(ctx.exception.code, A.HaltCode.EVIDENCE_SANITIZATION_FAILED)

    def test_private_evidence_only_with_explicit_permission(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        experiment, result = self._run(venue, self._plan(private_evidence_permission=True))
        path = experiment.export_private_balance_evidence()
        self.assertEqual(path.parent, (self.runs_root / experiment.plan.run_id / "private").resolve())
        private = json.loads(path.read_text("utf-8"))
        self.assertEqual(private["checkpoints"], {"B0": "1000", "B1": "999.6638"})
        self.assertNotIn("999.6638", json.dumps(result.shared_record))

    def test_unrelated_fill_during_run_halts_and_blocks_attribution(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        real_create = venue.apply_create

        def _create_plus_unrelated(body):
            out = real_create(body)
            venue._fill("ord-unrelated-1", "0.10", "0.3000", FILL_TIME, "0.0010")
            return out

        venue.apply_create = _create_plus_unrelated
        experiment, result = self._run(venue)
        self.assertEqual(result.final_state, "HALTED_HELD")
        self.assertIn(result.halt.code, (A.HaltCode.UNRELATED_ACTIVITY_PRESENT, A.HaltCode.ORDER_RECONCILIATION_INCOMPLETE,
                                          A.HaltCode.BASELINE_UNKNOWN_EXPOSURE))
        q = {r["question_id"]: r for r in result.question_results}
        self.assertNotIn("OBSERVED_MATCH", {r["status"] for r in q.values()})
        del experiment

    def test_order2_not_admitted_without_worst_case_capacity(self) -> None:
        """Unit-seam evidence only: the fake Stage-3 seam charges the
        conservative 72 reads as consumed, so at the Order-2 decision the
        remaining capacity is below the 163-read reservation and the refusal
        cause is the capacity check (observed, not inferred)."""
        venue = FakeDemoVenue(balances=self._balances())
        capacity = []
        real_require = F.F03BudgetLedgerV1.require_get_capacity

        def _observe_capacity(ledger, needed, *, purpose):  # observation only: the real check, unchanged
            row = {"purpose": purpose, "needed": needed, "get_count": ledger.get_count, "remaining": ledger.remaining_gets()}
            try:
                real_require(ledger, needed, purpose=purpose)
            except F.F03Halt as exc:
                capacity.append(dict(row, refused=exc.code))
                raise
            capacity.append(dict(row, refused=None))

        with mock.patch.object(F.F03BudgetLedgerV1, "require_get_capacity", _observe_capacity):
            experiment, result = self._run(venue, self._plan(order2_limit_price=D("0.5000")))
        (order2_check,) = [c for c in capacity if c["purpose"] == "ORDER2 admission and lifecycle"]
        reservation = (F.STAGE3_ADMISSION_GET_RESERVATION + F.ORDER_LIFECYCLE_GET_RESERVATION
                       + F.FINAL_RECONCILIATION_GET_RESERVATION)
        self.assertEqual(reservation, 163)
        self.assertEqual(order2_check["needed"], reservation)
        self.assertLess(order2_check["remaining"], reservation)
        self.assertEqual(order2_check["refused"], A.HaltCode.BUDGET_EXCEEDED)
        self.assertNotIn("ORDER2_DECISION_TRUTH", _phase_ops_phases(experiment))
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual(len(experiment.orders), 1)
        self.assertEqual([w["operation_name"] for w in venue.writes], ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        self.assertIn("ORDER2_DECISION", experiment.machine.history)
        self.assertNotIn("ORDER2_PREPARED", experiment.machine.history)
        q = {r["question_id"]: r for r in result.question_results}
        self.assertEqual(q["QF03-02"]["status"], "INCONCLUSIVE")
        # One Stage-3 admission only: the Order-1 trusted read set is never reused.
        self.assertEqual(len(experiment.used_read_set_ids), 1)


# ---------------------------------------------------------------------------
# F03 Correction01 -- Marco BLOCK findings F01..F05.
# ---------------------------------------------------------------------------

STAGE3_LIVE_SEQUENCE = (
    "GET_EXCHANGE_STATUS", "GET_USER_DATA_TIMESTAMP", "GET_MARKET", "GET_MARKET_ORDERBOOK", "GET_ORDERS", "GET_FILLS",
    "GET_POSITIONS", "GET_USER_DATA_TIMESTAMP", "GET_EXCHANGE_STATUS",
)


def _phase_ops(experiment, phase):
    return [e["operation"] for e in experiment.ledger.request_log if e["phase"] == phase]


def _phase_ops_phases(experiment):
    return {e["phase"] for e in experiment.ledger.request_log}


class LiveStage3AcquirerConformanceTests(F03HarnessTestCase):
    """BLOCK F04: complete runs over the RAW protected live Stage-3 acquirer
    (no ``trusted_dynamic_read_acquirer_test_seam``) with synthetic bytes only
    behind the inherited transport/orderbook seams.  The fake-seam tests in
    the other classes remain labelled unit evidence."""

    def _live(self, venue, plan=None, *, hook=None):
        rt = self._runtime(venue, seam=False)
        self.assertIsNone(rt.trusted_dynamic_read_acquirer_test_seam)
        plan = plan or self._plan()
        experiment = self._experiment(rt, plan)
        if hook is not None:
            venue.hook = hook(experiment)
        return experiment, experiment.run()

    @staticmethod
    def _in_stage3(experiment):
        log = experiment.ledger.request_log
        return bool(log) and log[-1]["phase"] == "STAGE3_ADMISSION"

    def test_live_acquirer_full_run_through_cancel_and_final_result(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        read_phases = []
        real_read_phase = runner.run_pre_release_read_phase_v2

        def _observe(invocation, runtime):  # observation only: the real protected call, unchanged
            out = real_read_phase(invocation, runtime)
            read_phases.append(out)
            return out

        with mock.patch.object(runner, "run_pre_release_read_phase_v2", side_effect=_observe):
            experiment, result = self._live(venue)
        self.assertIsNone(result.halt, result.halt)
        # The PROTECTED capability's own consumed-request counter equals the
        # requests this run actually observed crossing its transport boundary.
        (read_phase,) = read_phases
        self.assertEqual(read_phase.status, "READ_PHASE_COMPLETE")
        self.assertEqual(read_phase.requests_consumed, 9)
        self.assertEqual(read_phase.requests_consumed, len(_phase_ops(experiment, "STAGE3_ADMISSION")))
        self.assertEqual(result.final_state, "COMPLETE")
        self.assertEqual([w["operation_name"] for w in venue.writes], ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        # Exact live Stage-3 request sequence for the selected domain (0,):
        # S0, T0, market, orderbook, orders/fills/positions, T1, S1 = 9 reads
        # (no GET_ORDER supplement: no resting order at admission).
        self.assertEqual(tuple(_phase_ops(experiment, "STAGE3_ADMISSION")), STAGE3_LIVE_SEQUENCE)
        self.assertEqual(len(STAGE3_LIVE_SEQUENCE), 9)
        self.assertEqual((venue.status_calls, venue.udt_calls), (2, 2))
        # Every GET crossed this run's observed boundary: nothing charged from
        # a protected counter, and the whole-run count is exactly observed.
        self.assertNotIn("PROTECTED_ACCOUNTED_READS", [e["operation"] for e in experiment.ledger.request_log])
        self.assertEqual(experiment.ledger.get_count, len(venue.read_calls) + venue.orderbook_calls)
        self.assertEqual(experiment.ledger.get_count, len(experiment.ledger.request_log))
        self.assertLessEqual(experiment.ledger.get_count, 200)
        self.assertEqual(len(experiment.used_read_set_ids), 1)
        q = {r["question_id"]: r for r in result.question_results}
        self.assertEqual(q["QF03-01"]["status"], "OBSERVED_MATCH")
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(result.shared_record)))
        self.assertEqual(result.shared_record["counters"]["get"], experiment.ledger.get_count)

    def test_live_acquirer_order2_reservation_limitation_is_reported_truthfully(self) -> None:
        """IF01 (Correction 02 report correction, no behaviour change): the live
        Stage-3 acquisition consumes 9 reads (72 is only the conservative
        reservation constant).  In this synthetic trace Order 1 leaves 36 GETs
        consumed at B1, so 164 remain against the 163-read Order-2 reservation:
        the capacity check PASSES.  The observed refusal is the protected
        Gate-D truth gate at the Order-2 decision (position corroboration
        CONFLICT -> BASELINE_UNKNOWN_EXPOSURE); separability is never reached.
        Order 2 is never sent and QF03-02 stays INCONCLUSIVE."""
        venue = FakeDemoVenue(balances=self._balances())
        capacity, truths, gate_d = [], [], []
        real_require = F.F03BudgetLedgerV1.require_get_capacity
        real_collect = runner.collect_authoritative_read_truth
        real_gate_d_truth = F.F03FeeExperimentRunnerV1._gate_d_truth

        def _observe_capacity(ledger, needed, *, purpose):  # observation only: the real check, unchanged
            row = {"purpose": purpose, "needed": needed, "get_count": ledger.get_count, "remaining": ledger.remaining_gets()}
            try:
                real_require(ledger, needed, purpose=purpose)
            except F.F03Halt as exc:
                capacity.append(dict(row, refused=exc.code))
                raise
            capacity.append(dict(row, refused=None))

        def _observe_collect(capability, *, ticker):  # observation only
            out = real_collect(capability, ticker=ticker)
            truths.append(out)
            return out

        def _observe_gate_d_truth(experiment_self, capability):  # observation only
            try:
                out = real_gate_d_truth(experiment_self, capability)
            except F.F03Halt as exc:
                gate_d.append(exc.code)
                raise
            gate_d.append(None)
            return out

        with mock.patch.object(F.F03BudgetLedgerV1, "require_get_capacity", _observe_capacity), \
                mock.patch.object(runner, "collect_authoritative_read_truth", side_effect=_observe_collect), \
                mock.patch.object(F.F03FeeExperimentRunnerV1, "_gate_d_truth", _observe_gate_d_truth), \
                mock.patch.object(A, "order2_reset_separable", side_effect=A.order2_reset_separable) as separable:
            experiment, result = self._live(venue, self._plan(order2_limit_price=D("0.5000")))
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual(len(_phase_ops(experiment, "STAGE3_ADMISSION")), 9)
        self.assertEqual(F.STAGE3_ADMISSION_GET_RESERVATION, 72)
        self.assertNotIn("ORDER2_PREPARED", experiment.machine.history)
        self.assertEqual({r["question_id"]: r["status"] for r in result.question_results}["QF03-02"], "INCONCLUSIVE")
        # Measured 9 vs conservative 72; remaining capacity vs the reservation.
        reservation = (F.STAGE3_ADMISSION_GET_RESERVATION + F.ORDER_LIFECYCLE_GET_RESERVATION
                       + F.FINAL_RECONCILIATION_GET_RESERVATION)
        self.assertEqual(reservation, 72 + (64 + 12 + 3) + 12)
        (order2_check,) = [c for c in capacity if c["purpose"] == "ORDER2 admission and lifecycle"]
        self.assertEqual((order2_check["get_count"], order2_check["remaining"], order2_check["needed"]), (36, 164, 163))
        self.assertIsNone(order2_check["refused"])  # capacity is NOT the refusal cause here
        # Actual refusal condition: the Order-2 decision Gate-D truth read.
        self.assertEqual(_phase_ops(experiment, "ORDER2_DECISION_TRUTH"),
                         ["GET_MARKET", "GET_MARKET_ORDERBOOK", "GET_ORDERS", "GET_POSITIONS"])
        self.assertEqual(gate_d[-1], A.HaltCode.BASELINE_UNKNOWN_EXPOSURE)
        self.assertTrue(all(code is None for code in gate_d[:-1]))
        last = truths[-1]
        self.assertEqual((last.orders_complete, last.fills_complete, last.position_corroboration), (True, True, "CONFLICT"))
        self.assertEqual(last.bound_order_ids, ())
        separable.assert_not_called()

    def _assert_blocked_before_writes(self, venue, experiment, result, code=A.HaltCode.TARGET_DOMAIN_INELIGIBLE):
        self.assertEqual(result.final_state, "HALTED_HELD")
        self.assertEqual(result.halt.code, code)
        self.assertEqual(venue.writes, [])
        self.assertEqual((experiment.ledger.create_t3, experiment.ledger.cancel_t3), (0, 0))
        self.assertIsNone(experiment.stage3)
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(result.shared_record)))

    def test_live_malformed_exchange_status_blocks_admission(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        experiment, result = self._live(venue, hook=lambda exp: (
            lambda op, p: _json({"exchange_active": True}) if op is RunnerOperation.GET_EXCHANGE_STATUS and self._in_stage3(exp) else None))
        self._assert_blocked_before_writes(venue, experiment, result)
        self.assertEqual(_phase_ops(experiment, "STAGE3_ADMISSION"), ["GET_EXCHANGE_STATUS"])

    def test_live_status_domain_without_selected_index_blocks_admission(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        status = {"exchange_active": True, "trading_active": True,
                  "exchange_index_statuses": [{"exchange_index": 1, "exchange_active": True, "trading_active": True}]}
        experiment, result = self._live(venue, hook=lambda exp: (
            lambda op, p: _json(status) if op is RunnerOperation.GET_EXCHANGE_STATUS and self._in_stage3(exp) else None))
        self._assert_blocked_before_writes(venue, experiment, result)

    def test_live_foreign_exchange_index_row_blocks_admission(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        row = {"order_id": "foreign-1", "client_order_id": str(uuid.UUID(int=5, version=4)), "ticker": TICKER, "side": "yes",
               "status": "canceled", "fill_count_fp": "0.00", "remaining_count_fp": "0.00", "initial_count_fp": "1.00",
               "subaccount": 1, "subaccount_number": 1, "exchange_index": 1, "yes_price_dollars": "0.1000"}
        experiment, result = self._live(venue, hook=lambda exp: (
            lambda op, p: _json({"orders": [row], "cursor": ""}) if op is RunnerOperation.GET_ORDERS and self._in_stage3(exp) else None))
        self._assert_blocked_before_writes(venue, experiment, result)
        self.assertEqual(_phase_ops(experiment, "STAGE3_ADMISSION")[-1], "GET_ORDERS")

    def test_live_partial_page_cursor_blocks_admission(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        experiment, result = self._live(venue, hook=lambda exp: (
            lambda op, p: _json({"fills": [], "cursor": "more"}) if op is RunnerOperation.GET_FILLS and self._in_stage3(exp) else None))
        self._assert_blocked_before_writes(venue, experiment, result)
        ops = _phase_ops(experiment, "STAGE3_ADMISSION")
        self.assertNotIn("GET_POSITIONS", ops)  # never accepted as a complete surface
        self.assertGreaterEqual(ops.count("GET_FILLS"), 1)

    def test_live_user_data_timestamp_regression_blocks_admission(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())

        def hook(exp):
            def _h(op, p):
                if op is RunnerOperation.GET_USER_DATA_TIMESTAMP and self._in_stage3(exp) and venue.udt_calls == 1:
                    venue.udt_calls += 1
                    return _json({"as_of_time": "2026-08-17T12:00:00.000000Z"})
                return None
            return _h

        experiment, result = self._live(venue, hook=hook)
        self._assert_blocked_before_writes(venue, experiment, result)

    def test_live_get_ceiling_refuses_inside_acquisition_before_transport(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())

        def hook(exp):
            def _h(op, p):
                if self._in_stage3(exp) and len(_phase_ops(exp, "STAGE3_ADMISSION")) == 1:
                    exp.ledger.get_count = 196  # synthetic: the run has consumed 196 GETs
                return None
            return _h

        experiment, result = self._live(venue, hook=hook)
        self._assert_blocked_before_writes(venue, experiment, result, code=A.HaltCode.BUDGET_EXCEEDED)
        refused = [e for e in experiment.ledger.request_log if e["state"] == "REFUSED_BEFORE_TRANSPORT"]
        self.assertEqual(len(refused), 1)
        self.assertEqual(experiment.ledger.get_count, 200)
        charged = [e for e in experiment.ledger.request_log if e["state"] == "CHARGED_AT_TRANSPORT_BOUNDARY"]
        self.assertEqual(len(charged), len(venue.read_calls) + venue.orderbook_calls)


def _counterexample_venue(test):
    """F01 exact counterexample: DIRECT h=.0001, p=.0101, k=.07, M=1, tied
    fills .01/.99 -> maximal .0007/.0008 (order dependent), NONE .0008,
    observed cash .0008 (= API total)."""
    venue = FakeDemoVenue(balances=test._balances(b1="999.9891"))
    venue.create_fill_plan = [("0.01", "0.0101", FILL_TIME, "0.0001"), ("0.99", "0.0101", FILL_TIME, "0.0007")]
    return venue


def _tied_venue(test, n):
    principal_and_fee = D("0.0468") * n  # n x (0.10 x 0.4500 + 0.0018)
    venue = FakeDemoVenue(balances=test._balances(b1=f"{D('1000') - principal_and_fee:.4f}"))
    venue.create_fill_plan = [("0.10", "0.4500", FILL_TIME, "0.0018")] * n
    return venue


class IncompleteFamilyRunnerTests(F03HarnessTestCase):
    """BLOCK F01 at full runner level (seam and live acquirer)."""

    def _assert_counterexample(self, experiment, result):
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual(experiment.orders[0].terminal_classification, "FULL_FILL")
        q = {r["question_id"]: r for r in result.question_results}
        self.assertEqual(q["QF03-01"]["status"], "INCONCLUSIVE")
        self.assertEqual(q["QF03-01"]["scoped_conclusion"], "NO_ELIGIBLE_POSITIVE_DISCRIMINATOR")
        self.assertNotIn(q["QF03-03"]["status"], ("OBSERVED_MATCH", "OBSERVED_CONFLICT"))
        (interval,) = result.shared_record["cash_fee_intervals"]
        self.assertEqual(interval["cash_fee_total"], "0.0008")
        self.assertEqual((interval["unique_discriminator_state"], interval["matched_hypothesis_id"]), ("INELIGIBLE", None))
        preds = {h["id"]: h["predicted_total"] for h in interval["candidate_hypotheses"]}
        self.assertIsNone(preds["MAXIMAL_ZERO_NO_TERMINAL"])
        self.assertEqual(preds["NO_REBATE_ZERO_NO_TERMINAL"], "0.0008")
        fees = result.shared_record["orders"][0]["observed_fill_fees"]
        self.assertEqual({f["chronology_state"] for f in fees}, {A.CHRONOLOGY_ENUMERATED})
        self.assertTrue(all(f["hypothesis_rows"] == [] for f in fees))
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(result.shared_record)))

    def test_f01_counterexample_full_runner_is_inconclusive(self) -> None:
        venue = _counterexample_venue(self)
        experiment, result = self._run(venue)
        self._assert_counterexample(experiment, result)

    def test_f01_counterexample_over_live_acquirer(self) -> None:
        venue = _counterexample_venue(self)
        experiment, result = self._run(venue, seam=False)
        self._assert_counterexample(experiment, result)


class ChronologyBoundRunnerTests(F03HarnessTestCase):
    """BLOCK F02: 6/7/8 tied fills (below / at / above the 5040 bound) always
    produce a complete validated result; never an escaping exception."""

    def _tied_run(self, n, plan=None):
        venue = _tied_venue(self, n)
        experiment, result = self._run(venue, plan)
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual(len(experiment.orders[0].fills), n)
        self.assertEqual([r["question_id"] for r in result.question_results], list(A.QUESTION_IDS))
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(result.shared_record)))
        return venue, experiment, result

    def test_f02_six_tied_fills_enumerated(self) -> None:
        _, _, result = self._tied_run(6)
        fees = result.shared_record["orders"][0]["observed_fill_fees"]
        self.assertEqual({f["chronology_state"] for f in fees}, {A.CHRONOLOGY_ENUMERATED})

    def test_f02_seven_tied_fills_at_the_bound(self) -> None:
        _, _, result = self._tied_run(7)
        fees = result.shared_record["orders"][0]["observed_fill_fees"]
        self.assertEqual({f["chronology_state"] for f in fees}, {A.CHRONOLOGY_ENUMERATED})

    def _assert_bound_exceeded(self, result):
        q = {r["question_id"]: r for r in result.question_results}
        self.assertEqual(q["QF03-01"]["status"], "INCONCLUSIVE")
        # F03-Q03-001: without an identified residual the terminal disposition
        # is NOT_OBSERVABLE or INCONCLUSIVE -- never a match or conflict.
        self.assertIn(q["QF03-03"]["status"], ("NOT_OBSERVABLE", "INCONCLUSIVE"))
        (interval,) = result.shared_record["cash_fee_intervals"]
        self.assertEqual((interval["unique_discriminator_state"], interval["matched_hypothesis_id"]), ("INELIGIBLE", None))
        self.assertTrue(all(h["predicted_total"] is None for h in interval["candidate_hypotheses"]))
        fees = result.shared_record["orders"][0]["observed_fill_fees"]
        self.assertEqual({f["chronology_state"] for f in fees}, {A.CHRONOLOGY_BOUND_EXCEEDED})
        self.assertTrue(all(f["hypothesis_rows"] == [] for f in fees))
        self.assertIsNone(result.shared_record["orders"][0]["hypothesis_accumulator_end"]["value"])

    def test_f02_eight_tied_fills_without_order2(self) -> None:
        _, experiment, result = self._tied_run(8)
        self._assert_bound_exceeded(result)
        self.assertEqual(result.final_state, "COMPLETE")

    def test_f02_eight_tied_fills_with_optional_order2_planned(self) -> None:
        venue, experiment, result = self._tied_run(8, self._plan(order2_limit_price=D("0.5000")))
        self._assert_bound_exceeded(result)
        self.assertIn("ORDER2_DECISION", experiment.machine.history)
        self.assertNotIn("ORDER2_PREPARED", experiment.machine.history)  # no carry identified -> no Order 2
        self.assertEqual([w["operation_name"] for w in venue.writes], ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        self.assertEqual({r["question_id"]: r["status"] for r in result.question_results}["QF03-02"], "INCONCLUSIVE")

    def test_f02_any_analyzer_non_identification_yields_five_inconclusive_results(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        with mock.patch.object(A, "decide_q03", side_effect=A.F03AnalyzerError("CHRONOLOGY_ENUMERATION_BOUND_EXCEEDED", "synthetic")):
            experiment, result = self._run(venue)
        self.assertIsNone(result.halt, result.halt)
        self.assertEqual([r["status"] for r in result.question_results], ["INCONCLUSIVE"] * 5)
        self.assertTrue(all(r["scoped_conclusion"].startswith("ANALYZER_NON_IDENTIFICATION_") for r in result.question_results))
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(result.shared_record)))
        del experiment


def _mutate(record, fn):
    obj = json.loads(json.dumps(record))
    fn(obj)
    return obj


class ClosedNestedSchemaExportTests(F03HarnessTestCase):
    """BLOCK F03: the export boundary validates every nested schema and every
    run / process / domain / source / evidence reference (closed objects,
    bool is never an int, exact lexemes, closed enums)."""

    def setUp(self) -> None:
        super().setUp()
        venue = FakeDemoVenue(balances=self._balances())
        self.experiment, self.result = self._run(venue)
        self.assertIsNone(self.result.halt, self.result.halt)
        self.record = self.result.shared_record

    def test_valid_record_round_trips_through_export(self) -> None:
        path = self.experiment.export_shared_evidence(self.result)
        loaded = A.strict_json_loads(path.read_bytes())
        A.validate_fee_experiment_run_v1(loaded)
        self.assertEqual(loaded, json.loads(json.dumps(self.record)))
        self.assertEqual(loaded["run_claim"]["claim_sha256"], self.experiment.run_claim_sha256)
        self.assertEqual(loaded["process_instance_id"], self.experiment.runtime.normal_gate.process_instance_id)
        self.assertEqual(loaded["domain_binding_id"], self.domain_binding.binding_id)
        self.assertEqual(loaded["domain_binding_sha256"], self.domain_binding.binding_sha256)

    def test_malformed_nested_keys_types_and_references_are_rejected_at_export(self) -> None:
        run_id = self.record["run_id"]
        o = lambda r: r["orders"][0]  # noqa: E731
        fee0 = lambda r: o(r)["observed_fill_fees"][0]  # noqa: E731
        snap0 = lambda r: r["balance_observations"][0]["snapshot_evidence"][0]  # noqa: E731
        q = lambda r, i: r["question_results"][i]  # noqa: E731
        mutations = {
            "order_extra_key": lambda r: o(r).update(extra=1),
            "order_index_bool": lambda r: o(r).update(probe_order_index=True),
            "order_missing_key": lambda r: o(r).pop("remaining_quantity"),
            "order_schema": lambda r: o(r).update(schema="FeeProbeOrderV2"),
            "write_t3_int_not_bool": lambda r: o(r)["create"].update(t3_charged=1),
            "write_extra_key": lambda r: o(r)["create"].update(raw="x"),
            "write_classification_unknown": lambda r: o(r)["create"].update(classification="MAYBE"),
            "response_classification_unbound": lambda r: o(r).update(response_classification="AMBIGUOUS"),
            "exact_order_foreign": lambda r: o(r)["exact_order_observations"][0].update(order_id="other"),
            "exact_order_extra": lambda r: o(r)["exact_order_observations"][0].update(ticker=TICKER),
            "fill_foreign_order": lambda r: o(r)["fills"][0].update(order_id="other"),
            "fill_bad_lexeme": lambda r: o(r)["fills"][0].update(fee_cost="7e-3"),
            "fill_taker_str": lambda r: o(r)["fills"][0].update(is_taker="true"),
            "anchor_event_unbound": lambda r: o(r)["ledger_anchors"][0]["t2"].update(event_id="evt_" + "0" * 32),
            "anchor_sequence_gap": lambda r: o(r)["ledger_anchors"][0]["t3"].update(sequence=o(r)["ledger_anchors"][0]["t3"]["sequence"] + 1),
            "anchor_request_unbound": lambda r: o(r)["ledger_anchors"][0].update(request_id="req_" + "0" * 32),
            "accumulator_authoritative": lambda r: o(r)["hypothesis_accumulator_end"].update(authoritative=True),
            "accumulator_extra": lambda r: o(r)["hypothesis_accumulator_start"].update(note="x"),
            "fill_fee_missing_model": lambda r: fee0(r).pop("model_fee"),
            "fill_fee_missing_chronology": lambda r: fee0(r).pop("chronology_state"),
            "fill_fee_foreign_subaccount": lambda r: fee0(r).update(subaccount_number=2),
            "fill_fee_observed_rebate": lambda r: fee0(r).update(observed_rebate="0.0001"),
            "fill_fee_h_not_run_quantum": lambda r: fee0(r)["h"].update(value="0.01"),
            "fill_fee_api_canonical_mismatch": lambda r: fee0(r)["api_fee_cost"].update(canonical="0.0071"),
            "hypothesis_row_extra": lambda r: fee0(r)["hypothesis_rows"][0].update(score="1"),
            "hypothesis_row_class": lambda r: fee0(r)["hypothesis_rows"][0].update(evidence_class="AUTHORITATIVE"),
            "fill_fees_not_order_fills": lambda r: o(r)["observed_fill_fees"].pop(),
            "checkpoint_extra": lambda r: r["balance_observations"][0].update(balance="1000"),
            "checkpoint_bool_as_int": lambda r: r["balance_observations"][0].update(successes=True),
            "checkpoint_accounting": lambda r: r["balance_observations"][0].update(attempts=3),
            "snapshot_foreign_process": lambda r: snap0(r).update(process_instance_id="proc_" + "f" * 32),
            "snapshot_foreign_domain": lambda r: snap0(r).update(domain_binding_sha256="0" * 64),
            "snapshot_source_hash": lambda r: snap0(r).update(source_raw_sha256="0" * 64),
            "snapshot_extra": lambda r: snap0(r).update(balance_dollars="1000.0000"),
            "read_observation_extra": lambda r: r["read_observations"][0].update(note="x"),
            "read_observation_phase": lambda r: r["read_observations"][0].update(phase="SOMETIME"),
            "read_observation_b0_missing": lambda r: [x for x in r["read_observations"] if x["phase"] == "B0"][0].pop("conservative_incremental_bound"),
            "utc_audit_extra": lambda r: r["utc_audit"].update(clock="x"),
            "halt_shape": lambda r: r.update(halt={"code": "NOT_A_CODE", "state_history": ["HALTED_HELD"]}),
            "fee_regime_extra": lambda r: r["fee_regime_inputs"].update(note="x"),
            "source_identities_altered": lambda r: next(iter(r["source_identities"].values())).update(bytes=1),
            "artifact_digest": lambda r: r["implementation_artifacts"].update({"x.py": "zz"}),
            "process_instance_malformed": lambda r: r.update(process_instance_id="process-1"),
            "domain_binding_unbound": lambda r: r.update(domain_binding_id="KEDB1_" + "0" * 64),
            "run_claim_foreign": lambda r: r["run_claim"].update(run_folder_name=str(uuid.uuid4())),
            "counters_bool": lambda r: r["counters"].update(get=True),
            "counters_economic_float": lambda r: r["counters"].update(worst_case_outlay_bound=1.8176),
            "exchange_index_bool": lambda r: r.update(exchange_index=False),
            "question_revision": lambda r: q(r, 0).update(schema="QuestionResultV2"),
            "counters_create_unbound": lambda r: r["counters"].update(create=2),
            "counters_acquired_unbound": lambda r: r["counters"].update(acquired_quantity="0.71"),
            "question_missing": lambda r: r["question_results"].pop(),
            "question_duplicate": lambda r: r["question_results"].__setitem__(1, json.loads(json.dumps(q(r, 0)))),
            "question_scope_foreign": lambda r: q(r, 0).update(market_ticker="KXOTHER-1"),
            "question_quantum_foreign": lambda r: q(r, 0).update(quantum="0.01"),
            "question_cash_unresolved": lambda r: q(r, 0).update(cash_evidence_ids=[run_id + ":I9"]),
            "question_source_identities": lambda r: q(r, 0).update(source_identities=[]),
            "interval_cash_id_foreign": lambda r: r["cash_fee_intervals"][0].update(cash_evidence_id=str(uuid.uuid4()) + ":I1"),
            "interval_order_unresolved": lambda r: r["cash_fee_intervals"][0].update(ordered_order_ids=["missing"]),
            "interval_checkpoint_unresolved": lambda r: r["cash_fee_intervals"][0].update(post_checkpoint_id="B2"),
            "interval_predicate_missing": lambda r: r["cash_fee_intervals"][0]["isolation_predicates"].popitem(),
            "interval_hypothesis_id": lambda r: r["cash_fee_intervals"][0]["candidate_hypotheses"][0].update(id="H"),
            "interval_fills_unbound": lambda r: r["cash_fee_intervals"][0].update(ordered_fill_ids=["fill-x", "fill-y"]),
        }
        for name, fn in mutations.items():
            with self.subTest(name):
                bad = _mutate(self.record, fn)
                with self.assertRaises(A.F03AnalyzerError):
                    A.validate_fee_experiment_run_v1(bad)
                out = self.root / "rejected" / name
                with self.assertRaises(F.F03Halt) as ctx:
                    F.export_shared_run_evidence(bad, output_dir=out, prohibited_roots=self.prohibited_roots)
                self.assertEqual(ctx.exception.code, A.HaltCode.EVIDENCE_SANITIZATION_FAILED)
                self.assertFalse(out.exists())  # validated before any output creation
        self.assertEqual(len(mutations), 63)


class SnapshotExactIntegerExportTests(F03HarnessTestCase):
    """Correction 02 residual F03: the four sanitized balance-snapshot numeric
    fields (schema_revision / request_count / automatic_retry_count /
    followed_redirect_count) require exact ``int`` before semantic equality,
    so a JSON boolean never satisfies a numeric schema revision or count."""

    SNAPSHOT_EXPECTED = {"schema_revision": 1, "request_count": 1, "automatic_retry_count": 0,
                         "followed_redirect_count": 0}

    def setUp(self) -> None:
        super().setUp()
        venue = FakeDemoVenue(balances=self._balances())
        self.experiment, self.result = self._run(venue)
        self.assertIsNone(self.result.halt, self.result.halt)
        self.assertEqual(self.result.final_state, "COMPLETE")
        self.record = self.result.shared_record
        self.export_root = self.root / "c02_snapshot_export"

    def _snapshots(self, record):
        return [s for cp in record["balance_observations"] for s in cp["snapshot_evidence"]]

    def _set_snapshot_field(self, key, value):
        def fn(r):
            r["balance_observations"][0]["snapshot_evidence"][0][key] = value
        return fn

    def _assert_rejected_by_validator_and_export(self, label, bad, key):
        with self.assertRaises(A.F03AnalyzerError) as ctx:
            A.validate_fee_experiment_run_v1(bad)
        self.assertEqual(ctx.exception.code, "SCHEMA_NESTED_INVALID", label)
        self.assertIn(key, ctx.exception.detail, label)
        # The strict JSON decoder retains booleans, so the same record decoded
        # from wire bytes is rejected identically.
        reloaded = A.strict_json_loads(json.dumps(bad).encode("utf-8"))
        with self.assertRaises(A.F03AnalyzerError) as ctx2:
            A.validate_fee_experiment_run_v1(reloaded)
        self.assertEqual(ctx2.exception.code, "SCHEMA_NESTED_INVALID", label)
        out = self.export_root / label
        with self.assertRaises(F.F03Halt) as halt:
            F.export_shared_run_evidence(bad, output_dir=out, prohibited_roots=self.prohibited_roots)
        self.assertEqual(halt.exception.code, A.HaltCode.EVIDENCE_SANITIZATION_FAILED, label)
        self.assertEqual(halt.exception.detail, "SCHEMA_NESTED_INVALID", label)
        self.assertFalse(out.exists(), label)  # validated before any output creation
        self.assertFalse(self.export_root.exists(), label)

    def _assert_bool_rejected(self, key, value):
        self.assertIs(type(value), bool)
        self.assertEqual(value, self.SNAPSHOT_EXPECTED[key])  # Python equality alone would admit it
        bad = _mutate(self.record, self._set_snapshot_field(key, value))
        self.assertIs(bad["balance_observations"][0]["snapshot_evidence"][0][key], value)
        self._assert_rejected_by_validator_and_export(f"{key}_bool", bad, key)

    def test_exact_integer_snapshot_fields_round_trip_through_export(self) -> None:
        snapshots = self._snapshots(self.record)
        self.assertTrue(snapshots)
        for snap in snapshots:
            for key, expected in self.SNAPSHOT_EXPECTED.items():
                self.assertIs(type(snap[key]), int, key)
                self.assertEqual(snap[key], expected, key)
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(self.record)))
        path = F.export_shared_run_evidence(self.record, output_dir=self.export_root / "valid",
                                            prohibited_roots=self.prohibited_roots)
        loaded = A.strict_json_loads(path.read_bytes())
        A.validate_fee_experiment_run_v1(loaded)
        self.assertEqual(loaded, json.loads(json.dumps(self.record)))
        for snap in self._snapshots(loaded):
            for key, expected in self.SNAPSHOT_EXPECTED.items():
                self.assertIs(type(snap[key]), int, key)
                self.assertEqual(snap[key], expected, key)

    def test_snapshot_schema_revision_true_is_rejected(self) -> None:
        self._assert_bool_rejected("schema_revision", True)

    def test_snapshot_request_count_true_is_rejected(self) -> None:
        self._assert_bool_rejected("request_count", True)

    def test_snapshot_automatic_retry_count_false_is_rejected(self) -> None:
        self._assert_bool_rejected("automatic_retry_count", False)

    def test_snapshot_followed_redirect_count_false_is_rejected(self) -> None:
        self._assert_bool_rejected("followed_redirect_count", False)

    def test_unsupported_numeric_null_string_and_float_snapshot_values_are_rejected(self) -> None:
        cases = {
            "schema_revision_unsupported_2": ("schema_revision", 2),
            "schema_revision_unsupported_0": ("schema_revision", 0),
            "request_count_unsupported_2": ("request_count", 2),
            "request_count_unsupported_0": ("request_count", 0),
            "automatic_retry_count_unsupported_1": ("automatic_retry_count", 1),
            "followed_redirect_count_unsupported_1": ("followed_redirect_count", 1),
            "schema_revision_negative": ("schema_revision", -1),
        }
        for key in self.SNAPSHOT_EXPECTED:
            cases[key + "_null"] = (key, None)
            cases[key + "_string"] = (key, str(self.SNAPSHOT_EXPECTED[key]))
            cases[key + "_float"] = (key, float(self.SNAPSHOT_EXPECTED[key]))
        self.assertEqual(len(cases), 19)
        for label, (key, value) in cases.items():
            with self.subTest(label):
                bad = _mutate(self.record, self._set_snapshot_field(key, value))
                with self.assertRaises(A.F03AnalyzerError):
                    A.validate_fee_experiment_run_v1(bad)
                out = self.export_root / label
                with self.assertRaises(F.F03Halt) as halt:
                    F.export_shared_run_evidence(bad, output_dir=out, prohibited_roots=self.prohibited_roots)
                self.assertEqual(halt.exception.code, A.HaltCode.EVIDENCE_SANITIZATION_FAILED)
                self.assertFalse(out.exists())
        self.assertFalse(self.export_root.exists())

    def test_every_snapshot_and_checkpoint_carries_the_exact_integer_guard(self) -> None:
        # Not only the first snapshot: each snapshot of each checkpoint is checked.
        positions = [(i, j) for i, cp in enumerate(self.record["balance_observations"])
                     for j in range(len(cp["snapshot_evidence"]))]
        self.assertGreater(len(positions), 1)
        for i, j in positions:
            for key, expected in self.SNAPSHOT_EXPECTED.items():
                with self.subTest(checkpoint=i, snapshot=j, field=key):
                    def fn(r, i=i, j=j, key=key, expected=expected):
                        r["balance_observations"][i]["snapshot_evidence"][j][key] = bool(expected)
                    bad = _mutate(self.record, fn)
                    with self.assertRaises(A.F03AnalyzerError) as ctx:
                        A.validate_fee_experiment_run_v1(bad)
                    self.assertIn(f"balance_observations[{i}].snapshot_evidence[{j}].{key}", ctx.exception.detail)


class DurableNonReplayAdmissionTests(F03HarnessTestCase):
    """BLOCK F05: mandatory DURABLE pre-execution non-replay admission."""

    def setUp(self) -> None:
        super().setUp()
        F.F03FeeExperimentRunnerV1._completed_run_ids.clear()

    def tearDown(self) -> None:
        F.F03FeeExperimentRunnerV1._completed_run_ids.clear()
        super().tearDown()

    def test_claim_is_durable_bound_and_precedes_every_read(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        rt = self._runtime(venue)
        plan = self._plan()
        experiment = self._experiment(rt, plan)
        claim_path = self.runs_root / plan.run_id / F.RUN_CLAIM_FILE_NAME
        seen = []
        venue.hook = lambda op, p: seen.append(claim_path.exists()) or None
        result = experiment.run()
        self.assertIsNone(result.halt, result.halt)
        self.assertTrue(seen and all(seen))  # the claim existed before the first read
        data = claim_path.read_bytes()
        claim = A.strict_json_loads(data)
        self.assertEqual(hashlib.sha256(data).hexdigest(), experiment.run_claim_sha256)
        self.assertEqual(claim, {
            "claim_schema": "F03_RUN_CLAIM_V1", "run_id": plan.run_id, "plan_sha256": experiment._plan_sha256(),
            "canonical_commit": plan.expected_commit, "canonical_tree": plan.expected_tree,
            "canonical_parent": plan.expected_parent, "implementation_artifacts": dict(plan.implementation_artifacts),
            "process_instance_id": rt.normal_gate.process_instance_id, "domain_binding_id": self.domain_binding.binding_id,
            "domain_binding_sha256": self.domain_binding.binding_sha256, "subaccount_number": 1, "exchange_index": 0,
            "ticker": TICKER,
            "source_identities": {n: {"bytes": b, "sha256": h} for n, (b, h) in sorted(A.SOURCE_IDENTITIES.items())},
            "balance_source_binding_id": "KALSHI_OPENAPI_3_29_0_GET_BALANCE_CANONICAL_BINDING_01",
        })
        self.assertEqual(claim["source_identities"], result.shared_record["source_identities"])
        self.assertEqual(result.shared_record["run_claim"]["claim_sha256"], experiment.run_claim_sha256)

    def _assert_rejected_without_reads(self, experiment, venue):
        before = (len(venue.read_calls), venue.orderbook_calls, len(venue.writes))
        with self.assertRaises(F.F03Halt) as ctx:
            experiment.run()
        self.assertEqual(ctx.exception.code, A.HaltCode.SCOPE_EXPANSION_REQUIRED)
        self.assertEqual((len(venue.read_calls), venue.orderbook_calls, len(venue.writes)), before)
        self.assertEqual(experiment.ledger.get_count, 0)
        self.assertIsNone(experiment.stage3)

    def test_duplicate_run_id_after_process_memory_is_lost_is_rejected(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        plan = self._plan()
        self._experiment(self._runtime(venue), plan).run()
        F.F03FeeExperimentRunnerV1._completed_run_ids.clear()  # fresh process: no in-memory record
        fresh_venue = FakeDemoVenue(balances=self._balances())
        fresh = self._experiment(self._runtime(fresh_venue), plan)
        self.assertNotEqual(fresh._base_runtime.normal_gate.process_instance_id, None)
        self._assert_rejected_without_reads(fresh, fresh_venue)

    def test_concurrent_instances_for_one_run_id_admit_exactly_one(self) -> None:
        venue_a = FakeDemoVenue(balances=self._balances())
        venue_b = FakeDemoVenue(balances=self._balances())
        plan = self._plan()
        first = self._experiment(self._runtime(venue_a), plan)
        second = self._experiment(self._runtime(venue_b), plan)  # both constructed before either runs
        first.claim()
        self._assert_rejected_without_reads(second, venue_b)

    def test_crash_after_claim_is_never_resumed(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        plan = self._plan()
        crashed = self._experiment(self._runtime(venue), plan)
        crashed.claim()
        del crashed  # process dies after the durable claim, before any read
        F.F03FeeExperimentRunnerV1._completed_run_ids.clear()
        restart_venue = FakeDemoVenue(balances=self._balances())
        restart = self._experiment(self._runtime(restart_venue), plan)
        self._assert_rejected_without_reads(restart, restart_venue)
        self.assertEqual(venue.read_calls, [])

    def test_existing_unclaimed_folder_is_also_rejected(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        plan = self._plan()
        (self.runs_root / plan.run_id).mkdir()
        self._assert_rejected_without_reads(self._experiment(self._runtime(venue), plan), venue)

    def test_claim_root_containment(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        rt = self._runtime(venue)
        for root in (self.repository_root, self.repository_root / "tests", self.root / "absent"):
            with self.subTest(root=str(root)):
                experiment = self._experiment(rt, self._plan(), runs_root=root)
                self._assert_rejected_without_reads(experiment, venue)
        # Repository / ledger-state / authority roots are excluded by the runner
        # itself even when the caller supplies only an unrelated root.
        unrelated = (self.root / "unrelated",)
        for root in (self.repository_root, self.ledger_path.parent, self.binding.authority_namespace_root):
            with self.subTest(derived=str(root)):
                plan = self._plan()
                experiment = self._experiment(rt, plan, runs_root=root, prohibited=unrelated)
                self._assert_rejected_without_reads(experiment, venue)
                self.assertFalse((Path(root) / plan.run_id).exists())  # nothing created inside a prohibited root
        with self.assertRaises(F.F03Halt):
            F.F03FeeExperimentRunnerV1(runtime=rt, plan=self._plan(), observed_identity=self._observed(self._plan()),
                                       run_artifact_root=self.runs_root, prohibited_roots=())
        with self.assertRaises(TypeError):  # the durable root is mandatory
            F.F03FeeExperimentRunnerV1(runtime=rt, plan=self._plan(), observed_identity=self._observed(self._plan()))

    def test_claim_root_through_junction_is_rejected(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        target = self.root / "real_runs"
        target.mkdir()
        link = self.root / "linked_runs"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi
                _winapi.CreateJunction(str(target), str(link))
            except (ImportError, AttributeError, OSError):
                self.skipTest("neither symlink nor junction creation is available on this host")
        experiment = self._experiment(self._runtime(venue), self._plan(), runs_root=link)
        before = len(venue.read_calls)
        with self.assertRaises(F.F03Halt):
            experiment.run()
        self.assertEqual(len(venue.read_calls), before)
        self.assertEqual(list(target.iterdir()), [])

    def test_durable_ledger_cross_check_blocks_create_for_an_already_charged_plan(self) -> None:
        venue = FakeDemoVenue(balances=self._balances())
        plan = self._plan()
        experiment = self._experiment(self._runtime(venue), plan)
        result = experiment.run()
        self.assertIsNone(result.halt, result.halt)
        events = self._locked_events(experiment)
        plan_sha = experiment._plan_sha256()
        bound = [e for e in events if e.event_type.name == "EXECUTION_INTENT_RECORDED"
                 and e.payload.get("intent_payload", {}).get("quote_plan_sha256") == plan_sha]
        self.assertEqual(len(bound), 1)  # the real durable payload shape is what the check reads
        locked = types.SimpleNamespace(events=events)
        experiment._require_no_prior_plan_create(locked)  # consistent with this run's own record
        # A replay whose claim folder was lost (different root, fresh process)
        # still meets the durable ledger before any CREATE.
        F.F03FeeExperimentRunnerV1._completed_run_ids.clear()
        other_root = self.root / "other_runs"
        other_root.mkdir()
        replay = self._experiment(self._runtime(FakeDemoVenue(balances=self._balances())), plan, runs_root=other_root)
        with self.assertRaises(F.F03Halt) as ctx:
            replay._require_no_prior_plan_create(locked)
        self.assertEqual(ctx.exception.code, A.HaltCode.WRITE_LIMIT_CONSUMED)
        self.assertIn("self._require_no_prior_plan_create(locked)", inspect.getsource(F.F03FeeExperimentRunnerV1.run_order))
        source = inspect.getsource(F.F03FeeExperimentRunnerV1.run_order)
        self.assertLess(source.index("_require_no_prior_plan_create"), source.index("execute_f03_create("))
        self.assertLess(inspect.getsource(F.F03FeeExperimentRunnerV1.run).index("self.claim()"),
                        inspect.getsource(F.F03FeeExperimentRunnerV1.run).index("self.bind_source()"))


# ---------------------------------------------------------------------------
# Route A CORRECTION_01 -- RA-T01..RA-T18 through the sealed protected
# ``run_f03_release_orchestration_v1`` entry.  Every scenario drives the REAL
# launcher-only carrier issuance, rows 1-8 admission, durable row-9
# consumption, row-10 sanctioned runtime, receipt-bound Stage 3 and the
# orchestration-owned writer cleanup over temporary synthetic authority /
# ledger stores.  Timing values below are NONRUNNABLE fake-clock fixtures
# (spec RA-09-003 illustration A=100 s, R=20 s, C=20 s, H=10 s), never
# selected runtime settings; the accepted-policy registry is patched per test
# only, the production registry stays EMPTY.
# ---------------------------------------------------------------------------

S = 1_000_000_000
RA_POLICY_ID = "SYNTHETIC-ROUTE-A-POLICY-TEST-ONLY"
RA_APPROVED_SHA = "a" * 64
RA_EVIDENCE_SHA = "e" * 64
RA_CLEAN = "CLEAN_SAFE_HELD_RELEASE_CONTINUATION_V1"
RA_BOOT = "PRE_RELEASE_BRIDGE_RELEASE_ORCHESTRATION_V1"
RA_TEMPLATE_PATH = None  # the bundled nonexecutable template is reproduced byte-for-byte below
RA_NONEXECUTABLE_TEMPLATE = (
    b'{\n  "schema": "F03_ROUTE_A_TIMING_CONFIG_V1",\n  "route": "ROUTE_A_300S",\n'
    b'  "requested_active_seconds": null,\n  "reconciliation_tail_seconds": null,\n'
    b'  "per_operation_timeout_seconds": {\n    "stage3_read": null,\n    "market_read": null,\n'
    b'    "balance_read": null,\n    "order_read": null,\n    "fills_read": null,\n    "positions_read": null,\n'
    b'    "orderbook_read": null,\n    "create": null,\n    "cancel": null\n  },\n'
    b'  "poll_interval_seconds": {\n    "order_status": null,\n    "fills": null,\n    "balance_checkpoint": null\n  },\n'
    b'  "reserve_policy_id": null,\n  "calibration_evidence_ref": null,\n  "approved_profile_sha256": null\n}\n'
)


def ra_profile_doc(**over) -> dict:
    doc = {
        "schema": "F03_ROUTE_A_TIMING_CONFIG_V1", "route": "ROUTE_A_300S",
        "requested_active_seconds": "100", "reconciliation_tail_seconds": "20",
        "per_operation_timeout_seconds": {k: "5" for k in F.ROUTE_A_TIMEOUT_KEYS},
        "poll_interval_seconds": {k: "1" for k in F.ROUTE_A_POLL_KEYS},
        "reserve_policy_id": RA_POLICY_ID,
        "calibration_evidence_ref": {"sha256": RA_EVIDENCE_SHA, "schema": "SYNTHETIC_CALIBRATION_TEST_ONLY",
                                     "environment_scope": "KALSHI_DEMO"},
        "approved_profile_sha256": RA_APPROVED_SHA,
    }
    doc.update(over)
    return doc


def ra_profile_bytes(doc=None) -> bytes:
    return json.dumps(doc if doc is not None else ra_profile_doc(), indent=2).encode("utf-8")


def ra_policy(raw: bytes | None = None, **over) -> F.F03RouteAReservePolicyV1:
    config = F.parse_route_a_timing_config_v1(raw if raw is not None else ra_profile_bytes())
    values = dict(policy_id=RA_POLICY_ID, approved_profile_sha256=RA_APPROVED_SHA,
                  profile_semantic_sha256=config.semantic_sha256, calibration_evidence_sha256=RA_EVIDENCE_SHA,
                  max_active_ns=200 * S, max_tail_ns=120 * S, local_closure_reserve_ns=20 * S, slack_ns=10 * S,
                  mandatory_read_reserve_ns=15 * S, write_cancel_reserve_ns=30 * S)
    values.update(over)
    return F.F03RouteAReservePolicyV1(**values)


def ra_registry(*policies):
    return mock.patch.object(F, "_ROUTE_A_ACCEPTED_RESERVE_POLICIES", types.MappingProxyType({p.policy_id: p for p in policies}))


def ra_schedule(**over) -> F.F03RouteAScheduleV1:
    values = dict(profile_raw_sha256="0" * 64, profile_raw_bytes=1, profile_semantic_sha256="0" * 64, policy_id=RA_POLICY_ID,
                  active_ns=100 * S, tail_ns=20 * S, closure_ns=20 * S, slack_ns=10 * S, mandatory_read_ns=15 * S,
                  write_cancel_ns=30 * S, timeouts_ns={k: 5 * S for k in F.ROUTE_A_TIMEOUT_KEYS},
                  polls_ns={k: 1 * S for k in F.ROUTE_A_POLL_KEYS})
    values.update(over)
    return F.F03RouteAScheduleV1(**values)


# RA-IMP-F01: the real primitive, captured at import, so the harness can tell
# whether a test has already substituted a directory-durability fault.
_REAL_ROUTE_A_FSYNC_DIRECTORY = F._route_a_fsync_directory

# D-11: NO real Win32 directory API call is authorized in this offline suite.
# For the whole module the production binding point is replaced by a trap; a
# native-Windows test installs its own recording fake inside a fixture.
_REAL_WIN32_LOADER = F._route_a_load_win32_directory_api
_WIN32_LOADER_TRAP_CALLS: list = []
_WIN32_TRAP_PATCHER = None


def _win32_loader_trap():
    _WIN32_LOADER_TRAP_CALLS.append(1)
    raise AssertionError("real Win32 directory API must never be loaded by offline tests (D-11)")


def setUpModule():  # noqa: N802 - unittest module fixture
    global _WIN32_TRAP_PATCHER
    _WIN32_TRAP_PATCHER = mock.patch.object(F, "_route_a_load_win32_directory_api", _win32_loader_trap)
    _WIN32_TRAP_PATCHER.start()


def tearDownModule():  # noqa: N802 - unittest module fixture
    _WIN32_TRAP_PATCHER.stop()
    assert F._route_a_load_win32_directory_api is _REAL_WIN32_LOADER
    assert _WIN32_LOADER_TRAP_CALLS == [], "a test reached the real Win32 binding point"


class _RecordingWin32:
    """TEST-ONLY recording fake of exactly CreateFileW / FlushFileBuffers /
    CloseHandle / GetLastError.  ``script`` maps ``(api, per-api ordinal)`` to
    ``(return_value, last_error)`` or an exception; ``hooks`` maps the same key
    to a callable run BEFORE the scripted result (filesystem/clock faults).
    Simulated success is NOT evidence of any real Windows durability."""

    def __init__(self, script=None, hooks=None) -> None:
        self.script = dict(script or {})
        self.hooks = dict(hooks or {})
        self.calls: list = []
        self.counts: dict = {}
        self.open_handles: set = set()
        self.closed: list = []
        self._last_error = 0
        self._next = 0x4000

    def _step(self, api, default):
        n = self.counts[api] = self.counts.get(api, 0) + 1
        hook = self.hooks.get((api, n))
        if hook is not None:
            hook()
        scripted = self.script.get((api, n))
        if isinstance(scripted, BaseException):
            raise scripted
        if scripted is None:
            return default
        value, error = scripted
        self._last_error = error
        return value

    def CreateFileW(self, *args):  # noqa: N802 - Win32 name
        self.calls.append(("CreateFileW", args))
        self._next += 4
        handle = self._step("CreateFileW", self._next)
        if F._route_a_win32_valid_handle(handle):
            self.open_handles.add(handle)
        return handle

    def FlushFileBuffers(self, handle):  # noqa: N802 - Win32 name
        self.calls.append(("FlushFileBuffers", (handle,)))
        return self._step("FlushFileBuffers", 1)

    def CloseHandle(self, handle):  # noqa: N802 - Win32 name
        self.calls.append(("CloseHandle", (handle,)))
        self.closed.append(handle)
        self.open_handles.discard(handle)
        return self._step("CloseHandle", 1)

    def GetLastError(self):  # noqa: N802 - Win32 name
        self.calls.append(("GetLastError", ()))
        return self._last_error

    def api_names(self):
        return [name for name, _ in self.calls if name != "GetLastError"]

    def opened_paths(self):
        return [args[0] for name, args in self.calls if name == "CreateFileW"]


@contextlib.contextmanager
def _ra_synthetic_credential_scope():
    """TEST-ONLY synthetic credential scope: no environment mutation and no
    credential material (production binds the real PATH->PEM bridge)."""
    yield


def _ra_canonical(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _ra_d07_envelope(**overrides) -> dict:
    doc = {
        "schema_version": 1, "authorization_id": "R1-D07-EXTERNAL-EXEC-AUTH-0001", "authorizing_authority": "Gustavo",
        "task_id": "R1-D07_READ_ONLY_STAGE3_LIVE_ENTRYPOINT_EXECUTION_01", "issue_date": "2026-09-06",
        "completion_rule": "single-request", "network_access": "PERMITTED", "demo_public_reads": "PERMITTED",
        "demo_authenticated_reads": "PERMITTED", "credential_use": "PERMITTED", "demo_writes": "PROHIBITED",
        "production_public_reads": "PROHIBITED", "production_authenticated_reads": "PROHIBITED",
        "production_writes": "PROHIBITED", "account_funding": "PROHIBITED", "code_changes": "PROHIBITED",
        "tests": "PROHIBITED", "artifact_generation": "PROHIBITED", "repository_commits": "PROHIBITED",
    }
    doc.update(overrides)
    return doc


def _ra_risk_json(config) -> str:
    document = {"schema_version": config.schema_version, "conflict_domain": config.conflict_domain, "currency": config.currency}
    objects = {"per_order": config.per_order, "per_market": config.per_market,
               "conflict_domain_account": config.conflict_domain_account, "flow": config.flow,
               "state_integrity": config.state_integrity, "venue_defense": config.venue_defense}
    for name, spec in runner._D07_RISK_SECTIONS.items():
        section = {}
        for field_name, kind in spec:
            value = getattr(objects[name], field_name)
            if kind == "decimal":
                section[field_name] = str(value)
            elif kind == "str_or_none":
                section[field_name] = None if value is None else str(value)
            else:
                section[field_name] = value
        document[name] = section
    return json.dumps(document, sort_keys=True)


class _RASequencedAcquirer(runner._FakeTrustedDynamicReadAcquirerV2):
    """Test-only seam: protected phase k mints its own distinct read set."""

    __slots__ = ("_specs", "_index")

    def __init__(self, specs):
        fixture, truth, count = specs[0]
        super().__init__(fixture=fixture, selected_route_truth=truth, implied_request_count=count)
        self._specs = list(specs)
        self._index = 0

    def acquire(self, capability):
        fixture, truth, count = self._specs[self._index]
        self._index += 1
        self._fixture, self._selected_route_truth, self._implied_request_count = fixture, truth, count
        return super().acquire(capability)


class RouteAHarnessTestCase(F03HarnessTestCase):
    """The F03 harness re-based on the protected orchestration package (exact
    Strategy-1 write-capable synthetic risk object, N1 subaccount 1)."""

    ENTRY = RA_CLEAN
    COMMIT, TREE, PARENT = "1" * 40, "2" * 40, "3" * 40

    def _drive_to_safe_held(self) -> None:
        self.config = RiskLimitConfigV1(
            1, self.domain_binding.conflict_domain_ref, "USD",
            PerOrderRiskLimits(D("10"), D("10"), True, D("0.10"), 1_000),
            PerMarketRiskLimits(D("20"), D("20"), 1, D("1.00"), D("1.000000")),
            AccountRiskLimits(D("100"), 1, D("1.00"), 0, D("0")),
            FlowRiskLimits(1, 1_000, 0, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
            StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
            VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"))
        self._packages = 0
        if self.ENTRY == RA_CLEAN:
            super()._drive_to_safe_held()

    # -- durable state ------------------------------------------------------
    def _event_types(self):
        import sqlite3
        connection = sqlite3.connect(str(self.ledger_path))
        try:
            return [row[0] for row in connection.execute("SELECT event_type FROM ledger_events ORDER BY sequence")]
        finally:
            connection.close()

    def _checkpoint(self) -> dict:
        import sqlite3
        opened = ledger_binding.read_active_local_safety_state_v1(
            self.binding, canonical_repository_root=str(self.repository_root), active_contract=self.active_contract,
            expected_ledger_path=str(self.ledger_path), no_repair=True)
        self.assertIsNone(opened.failure_code)
        projection = opened.projection
        connection = sqlite3.connect(str(self.ledger_path))
        try:
            rows = connection.execute("SELECT event_id FROM ledger_events WHERE event_type='RISK_CONTROL_STATE_CHANGED' "
                                      "ORDER BY sequence DESC LIMIT 1").fetchall()
        finally:
            connection.close()
        proof = self.active_contract.writer_proof_id
        return {
            "authority_instance_id": projection.authority_instance_id, "authority_namespace_id": projection.authority_namespace_id,
            "authority_store_path_identity_sha256": projection.authority_store_path_identity_sha256,
            "ledger_instance_id": projection.ledger_instance_id, "ledger_path_identity_sha256": projection.ledger_path_identity_sha256,
            "trusted_sequence": projection.trusted_sequence, "trusted_event_hash": projection.trusted_event_hash,
            "risk_control_state": projection.risk_control_state, "risk_state_epoch": projection.risk_state_epoch,
            "risk_state_event_id": rows[0][0] if rows else None, "writer_proof_id": proof,
            "writer_proof_state": projection.writer_proof_state_by_proof_id.get(proof),
            "writer_proof_release_eligible": projection.writer_proof_release_eligible_by_proof_id.get(proof),
            "active_risk_config_sha256": projection.active_risk_config_sha256,
        }

    # -- package -------------------------------------------------------------
    def _ra_package(self, plan, *, profile=None, max_ordinary=4, e_mut=None, d07=None, section_mut=None,
                    commit=None, tamper=None, invocation_id=None):
        self._packages += 1
        root = self.root / f"ra_package_{self._packages}"
        root.mkdir()
        contract = self.active_contract
        cls = self.ENTRY
        risk_bytes = _ra_risk_json(self.config).encode("utf-8")
        d07_bytes = json.dumps(d07 or _ra_d07_envelope(), sort_keys=True).encode("utf-8")
        profile = ra_profile_bytes() if profile is None else profile
        binding = {
            "authorization_set_id": f"set_ra_{self._packages}", "task_id": "task_ra_1",
            # NH-04-001: the invocation id IS U (= plan.run_id); the per-package
            # execution_attempt_id keeps its own distinct grammar and meaning.
            "execution_attempt_id": f"attempt_ra_{self._packages}",
            "invocation_id": plan.run_id if invocation_id is None else invocation_id,
            "orchestration_authorization_id": f"orch_ra_{self._packages}", "orchestration_authorization_class": cls,
            "repository": "rigolugo/ARB", "required_implementation_commit": commit or self.COMMIT,
            "required_implementation_tree": self.TREE, "required_implementation_parent": self.PARENT,
            "active_contract_id": contract.contract_id, "active_contract_sha256": contract.contract_sha256,
            "domain_binding_id": contract.domain_binding_id, "domain_binding_sha256": contract.domain_binding_sha256,
            "environment": "KALSHI_DEMO", "account_scope_ref": ACCOUNT, "subaccount": 1, "exchange_index": 0,
            "conflict_domain_ref": contract.conflict_domain_ref,
            "market_scope": {"scope_kind": "SINGLE_MARKET_TICKER", "ticker": TICKER},
            "risk_config_raw_sha256": hashlib.sha256(risk_bytes).hexdigest(), "risk_config_semantic_sha256": self.config.sha256,
            "process_continuity_mode": "ONE_PROCESS_ONE_INVOCATION_NO_RESTART", "absolute_deadline_seconds": 300,
            "deadline_policy": "ONE_INVOCATION_START_ABSOLUTE_DEADLINE_NO_RESET",
        }
        binding_hash = ledger_binding.compute_authorization_binding_sha256(binding)
        g = {key: binding[key] for key in runner._AUTH_BINDING_KEYS
             if key not in ("orchestration_authorization_id", "orchestration_authorization_class")}
        g.update(schema_version=2, authorization_class="USER_AUTHORIZED_GATE_D_EXECUTION_V2",
                 authorization_id=f"gate_ra_{self._packages}", authorizing_user="Test Approver",
                 orchestration_authorization_id=binding["orchestration_authorization_id"],
                 orchestration_authorization_class=cls, authorization_binding_sha256=binding_hash,
                 max_ordinary_write_sends=max_ordinary, max_cleanup_cancel_sends=0)
        g_bytes = _ra_canonical(g)
        variant = runner._ORCH_VARIANTS[cls]
        d07_id = json.loads(d07_bytes)["authorization_id"]
        o = {key: binding[key] for key in runner._ORCH_O_KEYS if key in binding}
        o.update(
            schema_version=1, authorization_class=cls, authorization_id=binding["orchestration_authorization_id"],
            authorizing_user="Test Approver", authorizing_authority="Test Authority", d07_read_authorization_id=d07_id,
            d07_read_authorization_sha256=hashlib.sha256(d07_bytes).hexdigest(),
            restart_policy="RESTART_REQUIRES_FRESH_AUTHORIZATION", entry_state_class=variant["entry_state_class"],
            authorized_stage3_phase_count=variant["authorized_stage3_phase_count"],
            max_pre_release_stage3_phases=variant["max_pre_release_stage3_phases"],
            per_phase_pre_release_read_request_max_v2=72,
            aggregate_pre_release_read_request_ceiling=variant["aggregate_pre_release_read_request_ceiling"],
            phase_1_role=variant["phase_1_role"], phase_2_role=variant["phase_2_role"],
            local_mutation_authority=list(variant["local_mutation_authority"]),
            gate_d_successor_authorization_id=g["authorization_id"],
            gate_d_successor_authorization_sha256=hashlib.sha256(g_bytes).hexdigest(),
            gate_d_successor_authorization_class="USER_AUTHORIZED_GATE_D_EXECUTION_V2",
            authorization_binding_sha256=binding_hash,
            authorization_consumption_policy="DURABLE_ARB_AUTHORIZATION_SET_CONSUMED_V1")
        o_bytes = _ra_canonical(o)
        section = {"consumer": "F03_ISOLATED_FEE_PROBE", "plan_binding_sha256": F.route_a_plan_binding_sha256(plan),
                   "timing_profile_bytes": len(profile), "timing_profile_sha256": hashlib.sha256(profile).hexdigest()}
        if section_mut:
            section_mut(section)
        e = {
            "schema_version": 1, "carrier_class": "ARB_USER_APPROVED_EXECUTION_AUTHORIZATION_EXPECTATIONS_V1",
            "execution_package_id": f"pkg_ra_{self._packages}", "authorization_set_id": binding["authorization_set_id"],
            "binding": binding, "authorization_binding_sha256": binding_hash,
            "d07": {"authorization_id": d07_id, "authorization_class": "TASK_AUTHORIZATION_CAPABILITY_ENVELOPE",
                    "bytes": len(d07_bytes), "sha256": hashlib.sha256(d07_bytes).hexdigest()},
            "orchestration": {"authorization_id": o["authorization_id"], "authorization_class": cls,
                              "bytes": len(o_bytes), "sha256": hashlib.sha256(o_bytes).hexdigest()},
            "gate_d": {"authorization_id": g["authorization_id"], "authorization_class": "USER_AUTHORIZED_GATE_D_EXECUTION_V2",
                       "bytes": len(g_bytes), "sha256": hashlib.sha256(g_bytes).hexdigest()},
            "risk_config": {"bytes": len(risk_bytes), "raw_sha256": hashlib.sha256(risk_bytes).hexdigest(),
                            "semantic_sha256": self.config.sha256},
            "entry_checkpoint": self._checkpoint(), "consumption_policy": "DURABLE_ARB_AUTHORIZATION_SET_CONSUMED_V1",
            "user_risk_choice_status": "USER_SELECTED_WRITE_CAPABLE",
            "gate_d_scope": {"max_ordinary_write_sends": max_ordinary, "max_cleanup_cancel_sends": 0},
            "f03_route_a": section,
        }
        if e_mut:
            e_mut(e)
        e_bytes = _ra_canonical(e)
        constants = runner._LauncherEmbeddedConstantsV1(
            execution_package_id=e["execution_package_id"], authorization_set_id=binding["authorization_set_id"],
            expectations_bytes=len(e_bytes), expectations_sha256=hashlib.sha256(e_bytes).hexdigest(),
            installed_implementation_commit=self.COMMIT, installed_implementation_tree=self.TREE,
            installed_implementation_parent=self.PARENT, bootstrap_contract_sha256=contract.bootstrap_contract_sha256,
            authority_namespace_id="f03-ns", authority_namespace_root=str(self.binding.authority_namespace_root),
            canonical_repository_root=str(self.repository_root), expected_ledger_path=str(self.ledger_path))
        for name, content in ((runner._ORCH_E_FILENAME, e_bytes), (runner._ORCH_O_FILENAME, o_bytes),
                              (runner._ORCH_G_FILENAME, g_bytes), (runner._ORCH_D07_FILENAME, d07_bytes),
                              (runner._ORCH_RISK_FILENAME, risk_bytes), (runner._ORCH_F03_TIMING_FILENAME, profile)):
            (root / name).write_bytes(content)
        if tamper:
            tamper(root)
        return constants, root

    @staticmethod
    def _ra_issue(package):
        """TEST-ONLY stand-in for the separately approved launcher (module-private seam)."""
        constants, root = package
        return runner._establish_trusted_execution_expectations(runner._LAUNCHER_ISSUANCE_KEY, constants, str(root))

    # -- runtime builder -----------------------------------------------------
    def _ra_dynamic_read(self, cutoff, tag):
        base = (tag + 1) * 100_000
        traversals = tuple(
            runner.PerIndexTraversalV1(exchange_index=i, orders=self._surface(base + (i + 1) * 1000 + 10),
                                       fills=self._surface(base + (i + 1) * 1000 + 40),
                                       positions=self._surface(base + (i + 1) * 1000 + 70),
                                       order_rows=(), fill_rows=(), position_rows=())
            for i in (0, 1, 2, 3))
        read = dataclasses.replace(self._dynamic_read(cutoff), per_index_traversals=traversals)
        ident = runner.compute_dynamic_index_domain_read_set_identity(
            read, active_domain_binding_id=self.active_contract.domain_binding_id,
            active_domain_binding_sha256=self.active_contract.domain_binding_sha256,
            active_contract_sha256=self.active_contract.contract_sha256, risk_config_sha256=self.config.sha256)
        return dataclasses.replace(read, read_set_identity_sha256=ident)

    def _ra_builder(self, venue, *, phases=1, implied=72, write_transport=None, after=None):
        def build(context):
            rt = runner.build_orchestrated_release_runtime_v1(
                context, send_operation_request=venue.send,
                fetch_orderbook=runner._TestOnlyActiveV2OrderbookSeam(venue.orderbook),
                strategy_instance_id=STRATEGY_ID, minimum_spread_usd=D("0.0100"),
                gate_d_capability_reference_id="cap_f03_test")
            assert type(rt.normal_write_transport) is runner._DemoNormalWriteTransport
            rt = dataclasses.replace(rt, normal_write_transport=write_transport or venue.write)
            specs = []
            for k in range(phases):
                capability = runner._issue_pre_release_read_capability(
                    process_instance_id=rt.normal_gate.process_instance_id, ticker=TICKER, runtime=rt)
                truth = runner.collect_authoritative_read_truth(capability, ticker=TICKER)
                specs.append((self._ra_dynamic_read(runner._active_reconciliation_cutoff_sha256(truth), k), truth, implied))
            rt = dataclasses.replace(rt, trusted_dynamic_read_acquirer_test_seam=_RASequencedAcquirer(specs))
            # Fixture preparation reads above are NOT protected-run reads.
            venue.read_calls.clear()
            venue.orderbook_calls = 0
            if after is not None:
                after(rt)
            return rt
        return build

    def _ra_hooked_builder(self, venue, hook, **kwargs):
        """Install a venue hook only AFTER fixture preparation (protected-run reads only)."""
        return self._ra_builder(venue, after=lambda rt: setattr(venue, "hook", hook), **kwargs)

    def _ra_inputs(self, plan, *, observed=None, runs_root=None):
        return runner.F03OrchestrationInputsV1(
            plan=plan, observed_identity=observed or self._observed(plan),
            run_artifact_root=str(runs_root or self.runs_root),
            prohibited_roots=tuple(str(p) for p in self.prohibited_roots))

    def _ra_synthetic_directory_flush(self, path) -> bool:
        """RA-IMP-T06 TEST-ONLY deterministic stand-in for a SUCCESSFUL documented
        directory-entry flush (a real directory is still required).  A mock is
        NOT evidence that any real Windows mechanism exists or is durable."""
        self.__dict__.setdefault("directory_flushes", []).append(Path(path))
        return Path(path).is_dir()

    # -- Stage A fixture selection (TEST-ONLY) -------------------------------
    # The sanctioned production route is unconditionally held before row 9
    # (F03_N1_HISTORY_CONTEXT_UNAVAILABLE) and after the attempt marker
    # (N1_ADMISSION_LINK_UNAVAILABLE).  The INHERITED RA-T / RA-IMP component
    # suites exercise the historical post-row-9 behavior only by replacing
    # those two module-private stops inside ``mock.patch`` fixtures (restored
    # on exit); RouteAStageAN1HoldTests drives the UNPATCHED stops.  A fixture
    # bypass is never a production grant, parameter, config or serialized input.
    RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = True
    RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP = True
    # Explicit branch selection on ANY host: the inherited suites keep the
    # historical accepted POSIX sequence; native-Windows suites select True
    # and install a recording fake kernel32 (never the real binding).
    RA_NATIVE_WINDOWS = False

    def _ra_run(self, venue, plan=None, *, package=None, policy=None, builder=None, inputs=None, capture=None,
                expectations=None, real_directory_durability=False, win32=None, **kwargs):
        plan = plan or self._plan()
        package = package or self._ra_package(plan)
        options = dict(monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
                       uuid_factory=self.inputs.uuid, credential_bridge=_ra_synthetic_credential_scope)
        options.update(kwargs)
        original_attach = F.F03FeeExperimentRunnerV1._route_a_attach

        def attach(experiment, ctx):
            if capture is not None:
                capture["experiment"] = experiment
                capture["ctx"] = ctx
            return original_attach(experiment, ctx)

        # The synthetic success seam applies only when the caller neither asks
        # for the real primitive nor already substituted its own fault.
        if real_directory_durability or F._route_a_fsync_directory is not _REAL_ROUTE_A_FSYNC_DIRECTORY:
            durability = contextlib.nullcontext()
        else:
            durability = mock.patch.object(F, "_route_a_fsync_directory", self._ra_synthetic_directory_flush)
        with contextlib.ExitStack() as stack:
            stack.enter_context(ra_registry(policy or ra_policy()))
            stack.enter_context(mock.patch.object(F.F03FeeExperimentRunnerV1, "_route_a_attach", attach))
            stack.enter_context(durability)
            if self.RA_NATIVE_WINDOWS is not None:
                stack.enter_context(mock.patch.object(F, "_ROUTE_A_NATIVE_WINDOWS", self.RA_NATIVE_WINDOWS))
            if win32 is not None:
                stack.enter_context(mock.patch.object(F, "_route_a_load_win32_directory_api", lambda: win32))
            if self.RA_FIXTURE_BYPASS_N1_HISTORY_HOLD:
                stack.enter_context(mock.patch.object(runner, "_orch_f03_require_n1_history_context", lambda: None))
            if self.RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP:
                stack.enter_context(mock.patch.object(
                    F.F03FeeExperimentRunnerV1, "_route_a_admission_link", lambda experiment, ctx: None))
            return runner.run_f03_release_orchestration_v1(
                trusted_expectations=expectations or self._ra_issue(package),
                runtime_builder=builder or self._ra_builder(venue),
                f03_inputs=inputs or self._ra_inputs(plan), **options)

    def _venue(self, **kwargs):
        return FakeDemoVenue(balances=self._balances(), **kwargs)

    def _ops(self, venue):
        return [getattr(op, "value", str(op)) for op, _ in venue.read_calls]

    def _physical_reads(self, venue):
        return len(venue.read_calls) + venue.orderbook_calls

    def _assert_stopped_before_consumption(self, ctx, code, baseline_types, venue, detail_part=None):
        self.assertEqual(ctx.exception.code, code, ctx.exception.detail)
        if detail_part is not None:
            self.assertIn(detail_part, ctx.exception.detail or "")
        self.assertEqual(self._event_types(), baseline_types)  # zero persistent effect, authorization UNUSED
        self.assertEqual(self._physical_reads(venue), 0)
        self.assertEqual(venue.writes, [])
        self.assertEqual(list(self.runs_root.iterdir()), [])

    def _assert_same_u_refused_before_row9(self, ctx, venue, baseline, runs_before):
        """NH-04-006 (Stage A U equality): a later package reusing an already
        consumed U shares the durable ``invocation_id`` uniqueness key, so the
        unchanged no-repair freshness classifier refuses it already inside
        rows 1-8 (CONFLICT; the same classifier also guards row 9 under lock)
        -- with zero new consumption, zero reads/writes and no new or
        rewritten run folder -- before the claim root is even consulted."""
        self.assertEqual(ctx.exception.code, RunnerFailureCode.AUTHORIZATION_SET_ID_CONFLICT)
        self.assertEqual(self._physical_reads(venue), 0)
        self.assertEqual(venue.writes, [])
        self.assertEqual(self._event_types()[baseline:], [])
        self.assertEqual(sorted(p.name for p in self.runs_root.iterdir()), runs_before)

    def _assert_started_reads_inside_caps(self, timing):
        for entry in timing["send_log"]:
            if entry["started"] and entry["kind"] in ("READ", "CREATE", "CANCEL"):
                self.assertLess(entry["now_ns"], entry["cap_ns"], entry)
                self.assertLess(entry["now_ns"], timing["TA"], entry)
        first, tail = timing["Tfirst_halt_or_close"], timing["Ttail_effective"]
        if first is not None:
            after = [e for e in timing["send_log"] if e["started"] and e["kind"] in ("READ", "CREATE", "CANCEL")
                     and e["now_ns"] >= first]
            self.assertTrue(all(e["kind"] == "READ" for e in after), after)  # never a write after the first event
            if tail is None:
                self.assertEqual(after, [])  # no tail authority -> zero signed tail starts
            else:
                self.assertTrue(all(e["now_ns"] < tail for e in after))


def _write_kinds(venue):
    return [w["operation_name"] for w in venue.writes]


class RouteAEndToEndTests(RouteAHarnessTestCase):
    """RA-T06 / RA-T08 / RA-T11 / RA-T15 / RA-T18 -- the one sanctioned path."""

    def test_ra_t06_t11_t15_clean_safe_held_one_phase_full_f03_consumer(self) -> None:
        venue = self._venue()
        capture: dict = {}
        baseline = len(self._event_types())
        with mock.patch.object(runner, "run_gate_d_ordinary_decision_loop", side_effect=AssertionError("ordinary loop")):
            result = self._ra_run(venue, capture=capture)
        f03 = result.f03_result
        self.assertIsNone(f03.halt, f03.halt)
        self.assertEqual(f03.final_state, "COMPLETE")
        self.assertEqual((result.route, result.entry_state_class), ("CLEAN_SAFE_HELD", "CLEAN_SAFE_HELD_HELD_RELEASE_ELIGIBLE"))
        self.assertEqual(result.phase_requests, (72,))
        self.assertEqual(len(result.trusted_dynamic_read_set_ids), 1)
        self.assertEqual(result.writer_cleanup, "ENDED")
        self.assertEqual(result.route_a_feasibility, "ROUTE_A_FEASIBILITY_UNPROVEN")
        # RA-T10: exact proven-active cancel target in the active (subaccount, exchange_index) domain.
        self.assertEqual(_write_kinds(venue), ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        create, cancel = venue.writes
        self.assertIs(create["canonical_body"]["post_only"], False)
        self.assertEqual(cancel["venue_order_id"], capture["experiment"].orders[0].order_id)
        self.assertEqual(cancel["canonical_query"], {"subaccount": 1, "exchange_index": 0})
        types_ = self._event_types()[baseline:]
        self.assertEqual(types_.count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)
        self.assertEqual((types_.count("WRITER_SESSION_STARTED"), types_.count("WRITER_SESSION_ENDED")), (1, 1))
        self.assertLess(types_.index("EXECUTION_AUTHORIZATION_SET_CONSUMED"), types_.index("WRITER_SESSION_STARTED"))
        # RA-T11: whole-run GET = observed physical F03 reads + the protected phase charge ONCE.
        timing = result.route_a_timing
        counters = timing["counters"]
        self.assertEqual(counters["get"], self._physical_reads(venue) + 72)
        self.assertLessEqual(counters["get"], F.GET_MAX)
        self.assertEqual((counters["balance_get"], counters["create_t3"], counters["cancel_t3"]), (4, 1, 1))
        self.assertEqual((counters["create_physical"], counters["cancel_physical"]), (1, 1))
        # RA-T02/04: the one row-0 clock; the active close is the first event; caps hold.
        self.assertEqual(timing["TA"] - timing["T0"], 300 * S)
        self.assertEqual(timing["T0"], result.invocation_started_monotonic_ns)
        self.assertEqual(timing["first_event_kind"], "ACTIVE_CLOSE")
        self.assertEqual(timing["Tactive_end"], F.route_a_active_end_ns(tw_ns=timing["TW"], ta_ns=timing["TA"], schedule=ra_schedule()))
        self.assertEqual(timing["Ttail_effective"], min(timing["Tactive_end"] + 20 * S, timing["Tfirst_halt_or_close"] + 20 * S,
                                                         timing["TA"] - 30 * S))
        self._assert_started_reads_inside_caps(timing)
        record = f03.shared_record
        self.assertEqual(record["run_started_ns"], timing["T0"])
        self.assertEqual(record["active_write_deadline_ns"], timing["Tactive_end"])
        self.assertEqual(record["reconciliation_deadline_ns"], timing["Ttail_effective"])
        # RA-T15: unchanged economics and the five closed statuses (same as the installed runner fixture).
        q = {r["question_id"]: r["status"] for r in f03.question_results}
        self.assertEqual(q, {"QF03-01": "OBSERVED_MATCH", "QF03-02": "INCONCLUSIVE", "QF03-03": "INCONCLUSIVE",
                             "QF03-04": "INCONCLUSIVE", "QF03-05": "INCONCLUSIVE"})
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(record)))
        # RA-T16: no balance amount / secret in shared or timing evidence; orchestration timeline ordered.
        text = json.dumps(record) + json.dumps(dict(timing)) + json.dumps(dict(result.orchestration_timeline))
        for leak in ("1000.0000", "999.6638", "balance_dollars", "PRIVATE KEY", "KALSHI_DEMO_PRIVATE_KEY"):
            self.assertNotIn(leak, text)
        line = result.orchestration_timeline
        order = ["T0", "T8", "T9", "T10", "Tcred", "TP1", "Twriter_cleanup", "Tcredential_removed", "Treceipt_revoked"]
        self.assertEqual([line[k] for k in order], sorted(line[k] for k in order))
        self.assertLess(timing["timeline"]["TM"], line["Tcred"])  # marker durable before the credential scope
        self.assertLess(timing["timeline"]["TB0"], timing["TW"])

    def test_ra_t08_phase_split_single_claim_receipt_bound_stage3_no_unguarded_admission(self) -> None:
        venue = self._venue()
        calls = {"claim": 0, "stage3": [], "phase": 0}
        real_claim = F.F03FeeExperimentRunnerV1.claim
        real_stage3 = runner._complete_stage3_active_release_and_normal_writer_v2
        real_phase = runner.run_pre_release_read_phase_v2

        def claim(experiment):
            calls["claim"] += 1
            return real_claim(experiment)

        def stage3(read_phase, runtime, **kwargs):
            calls["stage3"].append((kwargs.get("orchestration_receipt") is not None, self.inputs.mono,
                                    len(venue.read_calls) + venue.orderbook_calls))
            return real_stage3(read_phase, runtime, **kwargs)

        def phase(invocation, runtime):
            calls["phase"] += 1
            return real_phase(invocation, runtime)

        capture: dict = {}
        with mock.patch.object(F.F03FeeExperimentRunnerV1, "claim", claim), \
                mock.patch.object(F.F03FeeExperimentRunnerV1, "_admit_fresh", side_effect=AssertionError("unguarded admission")), \
                mock.patch.object(F, "end_writer_session", side_effect=AssertionError("consumer cleanup")), \
                mock.patch.object(runner, "_complete_stage3_active_release_and_normal_writer_v2", stage3), \
                mock.patch.object(runner, "run_pre_release_read_phase_v2", phase):
            result = self._ra_run(venue, capture=capture)
        self.assertIsNone(result.f03_result.halt, result.f03_result.halt)
        self.assertEqual(calls["claim"], 1)
        self.assertEqual(calls["phase"], 1)
        self.assertEqual(len(calls["stage3"]), 1)
        receipt_bound, at_mono, reads_before_release = calls["stage3"][0]
        self.assertTrue(receipt_bound)
        # F03 preflight (market/domain/orderbook) + stable B0 happened BEFORE the release.
        self.assertGreater(reads_before_release, 0)
        self.assertLess(result.route_a_timing["timeline"]["TB0"], at_mono)
        experiment = capture["experiment"]
        self.assertEqual(len(experiment.used_read_set_ids), 1)
        for refused in (experiment.run, experiment._admit_fresh, experiment._end_session):
            with self.assertRaises(F.F03Halt):
                refused()
        source = inspect.getsource(F.F03FeeExperimentRunnerV1._route_a_consume)
        for banned in ("claim(", "_admit_fresh(", "_end_session(", "end_writer_session(", "run_gate_d_ordinary_decision_loop"):
            self.assertNotIn(banned, _code_only(source))

    def test_ra_t08_optional_order2_reuses_the_same_receipt_session_and_read_set(self) -> None:
        venue = self._venue()
        capture: dict = {}
        baseline = len(self._event_types())
        result = self._ra_run(venue, self._plan(order2_limit_price=D("0.5000")), capture=capture)
        experiment = capture["experiment"]
        types_ = self._event_types()[baseline:]
        self.assertEqual(types_.count("WRITER_SESSION_STARTED"), 1)
        self.assertEqual(types_.count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)
        self.assertEqual(len(experiment.used_read_set_ids), 1)
        self.assertIn("ORDER2_DECISION", experiment.machine.history)
        self.assertLessEqual(experiment.ledger.create_t3, 2)
        self.assertLessEqual(experiment.ledger.create_t3 + experiment.ledger.cancel_t3, 4)
        sessions = {e.payload.get("normal_writer_session_id") for e in experiment.stage3.normal_writer_acquisition.handle.events
                    if e.event_type.name == "EXECUTION_INTENT_RECORDED"} - {None}
        self.assertLessEqual(len(sessions), 1)
        self.assertEqual(result.writer_cleanup, "ENDED")

    def test_ra_t08_order2_mechanics_same_session_and_protected_assessment_governs(self) -> None:
        """Mechanics only: the installed Gate-D position corroboration and the
        analyzer reset-separability predicate are relaxed TEST-ONLY so the
        optional Order 2 is reached; the protected Strategy-1 assessment then
        governs it (1.00-contract market capacity) -- no second release,
        session, consumption, T3 or physical send."""
        venue = FakeDemoVenue(balances=self._balances() + self._balances()[2:])
        capture: dict = {}

        def truth(experiment, capability):
            return runner.collect_authoritative_read_truth(capability, ticker=experiment.plan.ticker)

        baseline = len(self._event_types())
        with mock.patch.object(F.F03FeeExperimentRunnerV1, "_gate_d_truth", truth), \
                mock.patch.object(F._an, "order2_reset_separable", return_value=True), \
                mock.patch.object(F.F03FeeExperimentRunnerV1, "_admit_fresh", side_effect=AssertionError("re-admission")):
            result = self._ra_run(venue, self._plan(order2_limit_price=D("0.5000")), capture=capture)
        experiment = capture["experiment"]
        self.assertIn("ORDER2_PREPARED", experiment.machine.history)
        self.assertEqual([o.create.classification for o in experiment.orders], ["BOUND_ACTIVE", "ELIGIBLE_NOT_SENT"])
        self.assertEqual(_write_kinds(venue), ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        counters = result.route_a_timing["counters"]
        self.assertEqual((counters["create_t3"], counters["create_physical"]), (1, 1))
        types_ = self._event_types()[baseline:]
        for once in ("EXECUTION_AUTHORIZATION_SET_CONSUMED", "RISK_RELEASE_RECORDED", "WRITER_PROOF_RELEASED",
                     "WRITER_SESSION_STARTED", "WRITER_SESSION_ENDED"):
            self.assertEqual(types_.count(once), 1, once)
        self.assertEqual(len(experiment.used_read_set_ids), 1)
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.TARGET_DOMAIN_INELIGIBLE)
        self._assert_started_reads_inside_caps(result.route_a_timing)


class RouteABootHoldTests(RouteAHarnessTestCase):
    """RA-T06 BOOT_HOLD route: phase 1 -> bridge -> fresh phase 2 (new ADRS2)."""

    ENTRY = RA_BOOT

    def test_ra_t06_boot_hold_two_distinct_phases_then_f03_consumer(self) -> None:
        venue = self._venue()
        with mock.patch.object(runner, "run_gate_d_ordinary_decision_loop", side_effect=AssertionError("ordinary loop")):
            result = self._ra_run(venue, builder=self._ra_builder(venue, phases=2, implied=20))
        self.assertEqual(result.route, "BOOT_HOLD_R0")
        self.assertEqual(result.phase_requests, (20, 20))
        self.assertEqual(len(set(result.trusted_dynamic_read_set_ids)), 2)
        self.assertTrue(result.bridge_reconciliation_appended)
        self.assertIsNone(result.f03_result.halt, result.f03_result.halt)
        self.assertEqual(result.route_a_timing["counters"]["get"], self._physical_reads(venue) + 40)
        self.assertIn("TP2", result.orchestration_timeline)
        self.assertEqual(_write_kinds(venue), ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])

    def test_ra_t06_u2_boot_hold_worst_case_phase_reads_leave_no_order_reservation(self) -> None:
        venue = self._venue()
        baseline = len(self._event_types())
        result = self._ra_run(venue, builder=self._ra_builder(venue, phases=2, implied=72))
        self.assertEqual(result.phase_requests, (72, 72))
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.BUDGET_EXCEEDED)
        self.assertEqual(result.writer_cleanup, "NOT_ACQUIRED")
        self.assertNotIn("WRITER_SESSION_STARTED", self._event_types()[baseline:])
        self.assertEqual(venue.writes, [])
        self._assert_started_reads_inside_caps(result.route_a_timing)


class RouteAIdentityAndAdmissionTests(RouteAHarnessTestCase):
    """RA-T01 / RA-T02 / RA-T03 / RA-T05 / RA-T17 -- all stops before consumption
    or before any credential scope / signed read."""

    def test_ra_t01_plan_implementation_identity_mismatch_stops_before_consumption(self) -> None:
        venue = self._venue()
        plan = self._plan(expected_commit="4" * 40)
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan)
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.BRIDGE_AUTHORIZATION_IMPLEMENTATION_MISMATCH, baseline, venue)

    def test_ra_t01_observed_artifact_identity_mismatch_stops_before_consumption(self) -> None:
        venue = self._venue()
        plan = self._plan()
        observed = F.F03ObservedIdentityV1(plan.expected_commit, plan.expected_tree, plan.expected_parent, {"other.py": "5" * 64})
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, inputs=self._ra_inputs(plan, observed=observed))
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.BRIDGE_AUTHORIZATION_IMPLEMENTATION_MISMATCH, baseline, venue,
                                                "CANONICAL_BASE_MISMATCH")

    def test_ra_t01_plan_differs_from_authorized_plan_binding(self) -> None:
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan)
        swapped = dataclasses.replace(plan, order1_limit_price=D("0.4900"))
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, swapped, package=package)
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.AUTHORIZATION_EXPECTATION_IDENTITY_MISMATCH, baseline, venue,
                                                "F03 plan binding")

    def test_ra_t01_timing_file_differs_from_the_authorized_identity(self) -> None:
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan, tamper=lambda root: (root / runner._ORCH_F03_TIMING_FILENAME).write_bytes(
            ra_profile_bytes(ra_profile_doc(requested_active_seconds="90"))))
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, package=package)
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.AUTHORIZATION_EXPECTATION_IDENTITY_MISMATCH, baseline, venue,
                                                "ROUTE_A_PROFILE_INVALID")

    def test_ra_t01_timing_file_changed_after_consumption_stops_before_credential_scope(self) -> None:
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan)
        entered = []

        @contextlib.contextmanager
        def scope():
            entered.append(True)
            yield

        def tamper(_rt):
            (package[1] / runner._ORCH_F03_TIMING_FILENAME).write_bytes(ra_profile_bytes() + b" ")

        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, package=package, builder=self._ra_builder(venue, after=tamper), credential_bridge=scope)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.AUTHORIZATION_EXPECTATION_IDENTITY_MISMATCH)
        self.assertIn("credential scope entry", ctx.exception.detail)
        self.assertEqual(entered, [])
        self.assertEqual(self._physical_reads(venue), 0)
        self.assertIn("EXECUTION_AUTHORIZATION_SET_CONSUMED", self._event_types())  # consumed, never replayable
        self.assertNotIn("WRITER_SESSION_STARTED", self._event_types())

    def test_ra_t02_row0_precedes_slow_admission_and_admission_consumes_the_slack(self) -> None:
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan)
        expectations = self._ra_issue(package)
        root = object.__getattribute__(expectations, "_root")
        real_read = root.read_once
        first_sample = []
        real_mono = self.inputs.monotonic_ns

        def mono():
            value = real_mono()
            if not first_sample:
                first_sample.append(value)
            return value

        def slow(name):
            self.inputs.jump(40 * S)  # each authorization artifact read is slow
            return real_read(name)

        baseline = len(self._event_types())
        with mock.patch.object(root, "read_once", slow):
            result = self._ra_run(venue, plan, package=package, expectations=expectations, monotonic_clock_ns=mono)
        timing = result.route_a_timing
        self.assertEqual(result.invocation_started_monotonic_ns, first_sample[0])
        self.assertEqual((timing["T0"], timing["TA"]), (first_sample[0], first_sample[0] + 300 * S))
        self.assertGreaterEqual(result.orchestration_timeline["T8"] - timing["T0"], 160 * S)
        # 5 slow reads = 200 s of the ONE 300 s budget: TA - TW < A+R+C+H -> no active window, zero writes.
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.RUN_DEADLINE_EXCEEDED)
        self.assertIn("DEADLINE_RESERVATION_INSUFFICIENT", result.f03_result.halt.detail)
        self.assertEqual(venue.writes, [])
        self.assertIsNone(timing["Tactive_end"])
        consumed = [p for p in self._event_types()[baseline:] if p == "EXECUTION_AUTHORIZATION_SET_CONSUMED"]
        self.assertEqual(len(consumed), 1)
        self.assertEqual(result.writer_cleanup, "ENDED")
        self._assert_started_reads_inside_caps(timing)

    def test_ra_t02_moderate_admission_delay_never_resets_t0(self) -> None:
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan)
        expectations = self._ra_issue(package)
        root = object.__getattribute__(expectations, "_root")
        real_read = root.read_once

        def slow(name):
            self.inputs.jump(5 * S)
            return real_read(name)

        with mock.patch.object(root, "read_once", slow):
            result = self._ra_run(venue, plan, package=package, expectations=expectations)
        timing = result.route_a_timing
        self.assertIsNone(result.f03_result.halt, result.f03_result.halt)
        self.assertGreaterEqual(timing["TW"] - timing["T0"], 25 * S)
        self.assertEqual(timing["Tactive_end"], min(timing["TW"] + 100 * S, timing["TA"] - 50 * S))
        self.assertEqual(result.f03_result.shared_record["run_started_ns"], timing["T0"])
        self.assertLess(timing["timeline"]["TC"], timing["TW"])

    def test_ra_t03_t17_nonexecutable_template_stops_route_a_feasibility_unproven(self) -> None:
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan, profile=RA_NONEXECUTABLE_TEMPLATE)
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, package=package)
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.BRIDGE_AUTHORIZATION_DEADLINE_MISMATCH, baseline, venue,
                                                "ROUTE_A_FEASIBILITY_UNPROVEN|UNSELECTED")

    def test_ra_t17_production_registry_is_empty_so_every_profile_is_unproven(self) -> None:
        self.assertIsInstance(F._ROUTE_A_ACCEPTED_RESERVE_POLICIES, types.MappingProxyType)
        self.assertEqual(len(F._ROUTE_A_ACCEPTED_RESERVE_POLICIES), 0)
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan)
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            runner.run_f03_release_orchestration_v1(
                trusted_expectations=self._ra_issue(package), runtime_builder=self._ra_builder(venue),
                f03_inputs=self._ra_inputs(plan), monotonic_clock_ns=self.inputs.monotonic_ns, wall_clock=self.inputs.clock,
                uuid_factory=self.inputs.uuid, credential_bridge=_ra_synthetic_credential_scope)
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.BRIDGE_AUTHORIZATION_DEADLINE_MISMATCH, baseline, venue,
                                                "no accepted reserve policy")

    def test_ra_t05_d07_write_grant_is_never_accepted(self) -> None:
        venue = self._venue()
        plan = self._plan()
        package = self._ra_package(plan, d07=_ra_d07_envelope(demo_writes="PERMITTED"))
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, package=package)
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.BRIDGE_AUTHORIZATION_D07_LAYER_MISMATCH, baseline, venue)

    def test_ra_t05_t18_forged_or_cross_route_carriers_are_rejected(self) -> None:
        venue = self._venue()
        plan = self._plan()
        untrusted = RunnerFailureCode.AUTHORIZATION_EXPECTATION_UNTRUSTED
        for forged in ({"carrier_class": "x"}, object(), None):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan, expectations=forged or object())
            self.assertEqual(ctx.exception.code, untrusted)
        with self.assertRaises(RunnerError) as ctx:
            runner.TrustedExecutionExpectationsV1(object(), document={}, raw_sha256="0" * 64, raw_bytes=1,
                                                  constants=None, root=None)
        self.assertEqual(ctx.exception.code, untrusted)
        # An ordinary (non-F03) authorization cannot enter the F03 consumer ...
        ordinary = self._ra_package(plan, e_mut=lambda e: e.pop("f03_route_a"))
        baseline = self._event_types()
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, package=ordinary)
        self._assert_stopped_before_consumption(ctx, untrusted, baseline, venue, "not an F03 route-A authorization")
        # ... and an F03 authorization can never enter the ordinary Gate-D consumer (before row 0).
        f03_package = self._ra_package(plan)
        samples = []
        with self.assertRaises(RunnerError) as ctx:
            runner.run_release_orchestration_v1(
                trusted_expectations=self._ra_issue(f03_package), runtime_builder=self._ra_builder(venue),
                monotonic_clock_ns=lambda: samples.append(1) or self.inputs.monotonic_ns(),
                credential_bridge=_ra_synthetic_credential_scope)
        self.assertEqual(ctx.exception.code, untrusted)
        self.assertEqual(samples, [])
        self.assertEqual(self._event_types(), baseline)
        # A malformed / foreign consumer tag never issues a carrier.
        for mutate in (lambda s: s.update(consumer="GATE_D_ORDINARY"), lambda s: s.update(extra="x"),
                       lambda s: s.update(timing_profile_bytes=0), lambda s: s.update(plan_binding_sha256="Z" * 64)):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_issue(self._ra_package(plan, section_mut=mutate))
            self.assertEqual(ctx.exception.code, untrusted)

    def test_ra_t05_t18_protected_context_is_sealed_and_receipt_bound(self) -> None:
        with self.assertRaises(F.F03Halt):
            F.F03ProtectedContextV1(object(), receipt=None, schedule=ra_schedule(), plan_binding_sha256="0" * 64,
                                    max_ordinary_write_sends=4)
        with self.assertRaises(F.F03Halt) as ctx:
            F.F03ProtectedContextV1(runner._F03_PROTECTED_CONTEXT_KEY, receipt=types.SimpleNamespace(), schedule=ra_schedule(),
                                    plan_binding_sha256="0" * 64, max_ordinary_write_sends=4)
        self.assertEqual(ctx.exception.code, A.HaltCode.TARGET_DOMAIN_INELIGIBLE)
        venue = self._venue()
        capture: dict = {}
        self._ra_run(venue, capture=capture)
        ctx_obj, experiment = capture["ctx"], capture["experiment"]
        for operation in (lambda: copy_module.copy(ctx_obj), lambda: pickle_module.dumps(ctx_obj)):
            with self.assertRaises(TypeError):
                operation()
        with self.assertRaises(AttributeError):
            ctx_obj.ta_ns = 0
        self.assertEqual(repr(ctx_obj), "F03ProtectedContextV1(<redacted>)")
        before = (self._physical_reads(venue), len(venue.writes))
        # The receipt was revoked at the end of the invocation: every seam entry refuses.
        for call in (lambda: experiment._route_a_consume(ctx_obj, experiment.stage3),
                     lambda: experiment._route_a_pre_writer(ctx_obj, protected_phase_charges=()),
                     lambda: experiment._route_a_claim_and_mark(ctx_obj),
                     lambda: experiment._route_a_consume(types.SimpleNamespace(), None)):
            with self.assertRaises(F.F03Halt):
                call()
        self.assertEqual((self._physical_reads(venue), len(venue.writes)), before)

    def test_ra_t18_production_route_requires_the_sanctioned_transport_and_bridge(self) -> None:
        venue = self._venue()
        plan = self._plan()
        baseline = len(self._event_types())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KALSHI_DEMO_PRIVATE_KEY_PEM", None)
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan, credential_bridge=None)  # builder substitutes a fake write transport
            self.assertNotIn("KALSHI_DEMO_PRIVATE_KEY_PEM", os.environ)
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORCHESTRATION_PHASE_STATE_INVALID)
        self.assertIn("unsanctioned normal write transport", ctx.exception.detail)
        self.assertEqual(self._physical_reads(venue), 0)
        self.assertEqual(list(self.runs_root.iterdir()), [])
        self.assertNotIn("WRITER_SESSION_STARTED", self._event_types()[baseline:])
        params = set(inspect.signature(runner.run_f03_release_orchestration_v1).parameters)
        self.assertEqual(params, {"trusted_expectations", "runtime_builder", "f03_inputs", "monotonic_clock_ns", "wall_clock",
                                  "uuid_factory", "credential_bridge", "fault_hook"})
        self.assertNotIn("run_gate_d_ordinary_decision_loop", _code_only(inspect.getsource(runner.run_f03_release_orchestration_v1)))
        source = inspect.getsource(runner.run_f03_release_orchestration_v1)
        self.assertEqual(source.count("with bridge():"), 1)
        self.assertIn("_demo_path_to_pem_credential_bridge if credential_bridge is None else credential_bridge", source)
        order = [source.index(token) for token in (
            "start_ns = mono()", "_orch_admit_authorization_set(", "admit_route_a_timing_profile_v1(",
            "consume_active_execution_authorization_set_v1(", "runtime_builder(context)", "_route_a_claim_and_mark(",
            "with bridge():", "_orch_run_read_phase(", "_route_a_pre_writer(", "_complete_stage3_active_release_and_normal_writer_v2(",
            "_orch_verify_gate_d_linkage(", "_route_a_consume(", "_fail_closed_end_writer_session(", "receipt.revoke()")]
        self.assertEqual(order, sorted(order))
        ordinary = inspect.getsource(runner.run_release_orchestration_v1)
        self.assertLess(ordinary.index("_ORCH_E_F03_SECTION in trusted_expectations.document"), ordinary.index("start_ns = mono()"))
        self.assertNotIn("_route_a", ordinary)
        self.assertEqual(ordinary.count("run_gate_d_ordinary_decision_loop("), 1)  # the ordinary consumer is unchanged


class RouteATimingProfileTests(unittest.TestCase):
    """RA-T03 / RA-T17 strict profile parser and policy admission (no I/O)."""

    def _invalid(self, raw):
        with self.assertRaises(F.F03RouteATimingError) as ctx:
            F.parse_route_a_timing_config_v1(raw)
        self.assertEqual(ctx.exception.classification, F.ROUTE_A_PROFILE_INVALID)

    def _admit(self, raw, *policies):
        with ra_registry(*policies):
            return F.admit_route_a_timing_profile_v1(raw, expected_bytes=len(raw), expected_sha256=hashlib.sha256(raw).hexdigest())

    def _admit_fails(self, raw, classification, *policies):
        with self.assertRaises(F.F03RouteATimingError) as ctx:
            self._admit(raw, *policies)
        self.assertEqual(ctx.exception.classification, classification, ctx.exception.detail)
        return ctx.exception

    def test_ra_t03_valid_profile_parses_to_exact_integer_nanoseconds(self) -> None:
        config = F.parse_route_a_timing_config_v1(ra_profile_bytes(ra_profile_doc(requested_active_seconds="0.000000001")))
        self.assertEqual(config.active_ns, 1)
        self.assertTrue(config.executable)
        schedule = self._admit(ra_profile_bytes(), ra_policy())
        self.assertEqual((schedule.active_ns, schedule.tail_ns, schedule.closure_ns, schedule.slack_ns),
                         (100 * S, 20 * S, 20 * S, 10 * S))
        self.assertTrue(all(v == 5 * S for v in schedule.timeouts_ns.values()))

    def test_ra_t03_malformed_profiles_are_rejected(self) -> None:
        good = ra_profile_doc()
        cases = []
        for key in ("route", "approved_profile_sha256"):
            doc = dict(good)
            del doc[key]
            cases.append(ra_profile_bytes(doc))
        cases.append(ra_profile_bytes(dict(good, extra="x")))
        for value in (100, 100.0, True, "-1", "0", "0.000", "1e2", "100s", " 100", "100 ", "1.0000000001", "+5",
                      "01", "10000", "", "NaN"):
            cases.append(json.dumps(dict(good, requested_active_seconds=value)).encode())
        cases.append(json.dumps(good).replace('"requested_active_seconds": "100"', '"requested_active_seconds": NaN').encode())
        cases.append(json.dumps(good).replace('"route": "ROUTE_A_300S"', '"route": "ROUTE_A_300S", "route": "ROUTE_A_300S"').encode())
        cases.append(b"\xef\xbb\xbf" + ra_profile_bytes())
        cases.append(b"\xff\xfe")
        cases.append(b"")
        cases.append(b"[]")
        cases.append(json.dumps(dict(good, schema="f03_route_a_timing_config_v1")).encode())
        timeouts = dict(good["per_operation_timeout_seconds"])
        del timeouts["cancel"]
        cases.append(json.dumps(dict(good, per_operation_timeout_seconds=timeouts)).encode())
        cases.append(json.dumps(dict(good, poll_interval_seconds=dict(good["poll_interval_seconds"], extra="1"))).encode())
        cases.append(json.dumps(dict(good, calibration_evidence_ref=dict(good["calibration_evidence_ref"],
                                                                         environment_scope="KALSHI_PRODUCTION"))).encode())
        cases.append(json.dumps(dict(good, approved_profile_sha256="A" * 64)).encode())
        cases.append(json.dumps(dict(good, reserve_policy_id="bad id")).encode())
        for raw in cases:
            with self.subTest(raw=raw[:80]):
                self._invalid(raw)

    def test_ra_t03_t17_unselected_unbound_or_infeasible_profiles_are_unproven(self) -> None:
        exc = self._admit_fails(RA_NONEXECUTABLE_TEMPLATE, F.ROUTE_A_FEASIBILITY_UNPROVEN, ra_policy())
        self.assertIn("requested_active_seconds", exc.detail)
        partially_null = ra_profile_bytes(ra_profile_doc(reconciliation_tail_seconds=None))
        self._admit_fails(partially_null, F.ROUTE_A_FEASIBILITY_UNPROVEN, ra_policy())
        self._admit_fails(ra_profile_bytes(), F.ROUTE_A_FEASIBILITY_UNPROVEN)  # no accepted policy at all
        tampered = ra_profile_bytes(ra_profile_doc(approved_profile_sha256="b" * 64))
        self._admit_fails(tampered, F.ROUTE_A_FEASIBILITY_UNPROVEN, ra_policy())  # tampered digest
        self._admit_fails(ra_profile_bytes(), F.ROUTE_A_FEASIBILITY_UNPROVEN, ra_policy(calibration_evidence_sha256="d" * 64))
        changed = ra_profile_bytes(ra_profile_doc(requested_active_seconds="99"))
        self._admit_fails(changed, F.ROUTE_A_FEASIBILITY_UNPROVEN, ra_policy())  # semantic profile not the bound one
        short_tail = ra_profile_bytes(ra_profile_doc(reconciliation_tail_seconds="10"))
        self._admit_fails(short_tail, F.ROUTE_A_FEASIBILITY_UNPROVEN, ra_policy(short_tail))  # R < Q
        too_long = ra_profile_bytes(ra_profile_doc(requested_active_seconds="250"))
        self._admit_fails(too_long, F.ROUTE_A_FEASIBILITY_UNPROVEN, ra_policy(too_long, max_active_ns=290 * S))  # A+R+C+H = 300 s

    def test_ra_t03_t04_out_of_bound_profile_values_are_invalid(self) -> None:
        eleven = ra_profile_bytes(ra_profile_doc(per_operation_timeout_seconds={k: "10.000000001" for k in F.ROUTE_A_TIMEOUT_KEYS}))
        self._admit_fails(eleven, F.ROUTE_A_PROFILE_INVALID, ra_policy(eleven))  # > inherited 10 s request bound
        slow_poll = ra_profile_bytes(ra_profile_doc(poll_interval_seconds={k: "21" for k in F.ROUTE_A_POLL_KEYS}))
        self._admit_fails(slow_poll, F.ROUTE_A_PROFILE_INVALID, ra_policy(slow_poll))
        long_tail = ra_profile_bytes(ra_profile_doc(reconciliation_tail_seconds="121"))
        self._admit_fails(long_tail, F.ROUTE_A_PROFILE_INVALID, ra_policy(long_tail))
        raw = ra_profile_bytes()
        with ra_registry(ra_policy()), self.assertRaises(F.F03RouteATimingError) as ctx:
            F.admit_route_a_timing_profile_v1(raw, expected_bytes=len(raw), expected_sha256="0" * 64)
        self.assertEqual(ctx.exception.classification, F.ROUTE_A_PROFILE_INVALID)
        for bad in (dict(max_tail_ns=121 * S), dict(slack_ns=-1), dict(local_closure_reserve_ns=0), dict(max_active_ns=300 * S)):
            with self.subTest(policy=bad), self.assertRaises(F.F03RouteATimingError):
                ra_policy(**bad)


class RouteADeadlineArithmeticTests(unittest.TestCase):
    """RA-T04 / RA-T14 pure monotonic-nanosecond theorems (RA-09-003)."""

    def test_ra_t04_first_event_tail_counterexample_and_variants(self) -> None:
        schedule = ra_schedule()
        ta = 300 * S
        active_end = F.route_a_active_end_ns(tw_ns=50 * S, ta_ns=ta, schedule=schedule)
        self.assertEqual(active_end, 150 * S)
        cap = lambda first: F.route_a_tail_cap_ns(active_end_ns=active_end, first_event_ns=first, ta_ns=ta, schedule=schedule)
        self.assertEqual(cap(70 * S), 90 * S)  # NOT 170 s
        self.assertEqual(cap(150 * S), 170 * S)  # simultaneous close/HALT or scheduled close only
        self.assertEqual(cap(150 * S - 1), 170 * S - 1)  # HALT one tick before scheduled close
        self.assertEqual(F.route_a_active_end_ns(tw_ns=200 * S, ta_ns=ta, schedule=schedule), 250 * S)  # TA-R-C-H binds
        self.assertEqual(F.route_a_tail_cap_ns(active_end_ns=250 * S, first_event_ns=260 * S, ta_ns=ta, schedule=schedule), 270 * S)

    def test_ra_t04_t14_caps_never_exceed_any_bound_on_a_grid(self) -> None:
        schedule = ra_schedule()
        ta = 300 * S
        for tw in (0, 1, 50 * S, 149 * S, 150 * S - 1):
            active_end = F.route_a_active_end_ns(tw_ns=tw, ta_ns=ta, schedule=schedule)
            self.assertLessEqual(active_end, ta - 50 * S)
            self.assertLessEqual(active_end, tw + 100 * S)
            for first in (tw, tw + 1, active_end - 1, active_end, active_end + 1, ta - 1, ta, ta + 1):
                tail = F.route_a_tail_cap_ns(active_end_ns=active_end, first_event_ns=first, ta_ns=ta, schedule=schedule)
                self.assertLessEqual(tail, first + 20 * S)
                self.assertLessEqual(tail, active_end + 20 * S)
                self.assertLessEqual(tail, ta - 30 * S)
                self.assertLessEqual(tail - first, 20 * S)  # elapsed from the first event never exceeds R

    def test_ra_t14_physical_start_predicate_boundaries(self) -> None:
        ok = F.route_a_start_permitted
        cap, ta, attempt = 100, 300, 5
        self.assertTrue(ok(now_ns=94, cap_ns=cap, ta_ns=ta, attempt_ns=attempt))
        self.assertTrue(ok(now_ns=95, cap_ns=cap, ta_ns=ta, attempt_ns=attempt))  # complete attempt fits exactly
        for now in (96, 99, 100, 101):  # cap-1ns lacks a complete attempt; equality and later: zero starts
            self.assertFalse(ok(now_ns=now, cap_ns=cap, ta_ns=ta, attempt_ns=attempt), now)
        self.assertTrue(ok(now_ns=ta - 1, cap_ns=10 ** 6, ta_ns=ta, attempt_ns=1))
        for now in (ta, ta + 1):
            self.assertFalse(ok(now_ns=now, cap_ns=10 ** 6, ta_ns=ta, attempt_ns=0), now)
        self.assertFalse(ok(now_ns=10 ** 30, cap_ns=10 ** 30, ta_ns=10 ** 31, attempt_ns=0))  # no overflow semantics


class RouteAClaimMarkerTests(RouteAHarnessTestCase):
    """RA-T07 / RA-T16: claim -> durable attempt marker before ANY signed read."""

    def test_ra_t07_marker_is_durable_bound_and_precedes_the_first_signed_read(self) -> None:
        venue = self._venue()
        plan = self._plan()
        seen = []
        marker = self.runs_root / plan.run_id / F.OPERATOR_ATTEMPT_FILE_NAME
        hook = lambda op, prepared: seen.append(marker.exists()) or None
        capture: dict = {}
        self._ra_run(venue, plan, capture=capture, builder=self._ra_hooked_builder(venue, hook))
        self.assertTrue(seen and all(seen))
        folder = self.runs_root / plan.run_id
        claim_bytes = (folder / F.RUN_CLAIM_FILE_NAME).read_bytes()
        doc = json.loads(marker.read_bytes())
        self.assertEqual(doc["run_claim_sha256"], hashlib.sha256(claim_bytes).hexdigest())
        self.assertEqual(doc["attempt_ordinal"], 1)
        self.assertEqual(doc["plan_binding_sha256"], F.route_a_plan_binding_sha256(plan))
        self.assertEqual(doc["timing_profile_sha256"], hashlib.sha256(ra_profile_bytes()).hexdigest())
        self.assertEqual(set(doc), {"attempt_schema", "run_id", "attempt_ordinal", "run_claim_sha256", "plan_binding_sha256",
                                    "timing_profile_sha256", "reserve_policy_id", "authorization_receipt_digest",
                                    "process_instance_id"})
        self.assertEqual(capture["experiment"].operator_attempt_sha256, hashlib.sha256(marker.read_bytes()).hexdigest())

    def _assert_claim_stop(self, ctx, venue, baseline, detail_part):
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORCHESTRATION_PHASE_STATE_INVALID)
        self.assertIn(detail_part, ctx.exception.detail)
        self.assertEqual(self._physical_reads(venue), 0)
        self.assertEqual(venue.writes, [])
        types_ = self._event_types()[baseline:]
        self.assertEqual(types_.count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)  # consumed: no replay possible
        self.assertNotIn("WRITER_SESSION_STARTED", types_)

    def test_ra_t07_preexisting_run_folder_collision(self) -> None:
        venue = self._venue()
        plan = self._plan()
        (self.runs_root / plan.run_id).mkdir()
        baseline = len(self._event_types())
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan)
        self._assert_claim_stop(ctx, venue, baseline, "already claimed")

    def test_ra_t07_marker_fsync_failure_consumes_the_run_with_zero_reads(self) -> None:
        venue = self._venue()
        plan = self._plan()
        real_fsync = os.fsync
        calls = []

        def fsync(fd):
            calls.append(fd)
            if len(calls) == 2:  # claim file ok; the marker's content fsync fails
                raise OSError("synthetic fsync failure")
            return real_fsync(fd)

        baseline = len(self._event_types())
        # RA-IMP-F01: ONLY the marker FILE fsync fails here; directory-entry
        # durability is the synthetic success seam, so the two fault classes
        # stay distinct (directory faults: RouteADirectoryEntryDurabilityTests).
        with mock.patch.object(F.os, "fsync", fsync):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan)
        self._assert_claim_stop(ctx, venue, baseline, "OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker not durably written")
        self.assertEqual(len(calls), 2)
        self.assertEqual([p.resolve() for p in self.directory_flushes],
                         [(self.runs_root / plan.run_id).resolve(), self.runs_root.resolve()])
        self.assertTrue((self.runs_root / plan.run_id / F.RUN_CLAIM_FILE_NAME).exists())
        # The SAME run id can never be retried in a fresh package (and never in this process).
        venue_again = self._venue()
        baseline_again = len(self._event_types())
        runs_before = sorted(p.name for p in self.runs_root.iterdir())
        with self.assertRaises(RunnerError) as again:
            self._ra_run(venue_again, plan)
        self._assert_same_u_refused_before_row9(again, venue_again, baseline_again, runs_before)

    def test_ra_t07_preexisting_marker_is_never_overwritten(self) -> None:
        venue = self._venue()
        plan = self._plan()
        real_claim_folder = F.claim_run_folder

        def claim_then_plant(**kwargs):
            folder, sha = real_claim_folder(**kwargs)
            (folder / F.OPERATOR_ATTEMPT_FILE_NAME).write_bytes(b"{}")
            return folder, sha

        baseline = len(self._event_types())
        with mock.patch.object(F, "claim_run_folder", claim_then_plant):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan)
        self._assert_claim_stop(ctx, venue, baseline, "OPERATOR_ATTEMPT_ALREADY_CONSUMED")
        self.assertEqual((self.runs_root / plan.run_id / F.OPERATOR_ATTEMPT_FILE_NAME).read_bytes(), b"{}")

    def test_ra_t07_completed_run_is_never_replayed_even_after_process_state_loss(self) -> None:
        plan = self._plan()
        # A first attempt that halts before any writer leaves SAFE_HELD intact,
        # so a fresh valid authorization package can be issued for the retry.
        first = self._ra_run(FakeDemoVenue(balances=self._balances(b0="1.0000")), plan)
        self.assertEqual(first.f03_result.halt.code, A.HaltCode.INSUFFICIENT_EXISTING_BALANCE)
        for clear in (False, True):
            if clear:
                F.F03FeeExperimentRunnerV1._completed_run_ids.discard(plan.run_id)  # simulated fresh process
            venue = self._venue()
            baseline = len(self._event_types())
            runs_before = sorted(p.name for p in self.runs_root.iterdir())
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan)
            self._assert_same_u_refused_before_row9(ctx, venue, baseline, runs_before)

    def test_ra_t16_run_root_inside_the_repository_is_refused_before_any_read(self) -> None:
        venue = self._venue()
        plan = self._plan()
        baseline = len(self._event_types())
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, inputs=self._ra_inputs(plan, runs_root=self.repository_root / "tests"))
        self._assert_claim_stop(ctx, venue, baseline, "SCOPE_EXPANSION_REQUIRED")
        self.assertFalse((self.repository_root / "tests" / plan.run_id).exists())


class _DirectoryFlushOS:
    """TEST-ONLY proxy for module ``F``'s ``os`` (RA-IMP-F01).  Directory
    ``open``/``fstat``/``fsync``/``close`` are SIMULATED with deterministic,
    per-call fault injection and a call log; every other attribute and every
    non-directory descriptor is the real ``os``.  Simulated success is NOT
    evidence that a real Windows directory-durability mechanism exists."""

    NOT_DIR = "NOT_DIR"

    def __init__(self, faults=None, on_open=None, file_fsync_faults=None) -> None:
        self.faults = dict(faults or {})  # (operation, directory-call ordinal) -> exception | NOT_DIR
        self.file_fsync_faults = dict(file_fsync_faults or {})  # file-fsync ordinal -> exception
        self.on_open = on_open
        self.log: list = []
        self.file_fsyncs = 0
        self.dir_calls = 0
        self._fds: dict = {}
        self._next = 1_000_000

    def __getattr__(self, name):
        return getattr(os, name)

    def _fault(self, operation, ordinal):
        fault = self.faults.get((operation, ordinal))
        if isinstance(fault, BaseException):
            raise fault
        return fault

    def open(self, path, flags, *args, **kwargs):
        if not Path(path).is_dir():
            return os.open(path, flags, *args, **kwargs)
        self.dir_calls += 1
        ordinal = self.dir_calls
        self.log.append(("open", ordinal, Path(path).resolve()))
        if self.on_open is not None:
            self.on_open(ordinal)
        self._fault("open", ordinal)
        fd = self._next
        self._next += 1
        self._fds[fd] = ordinal
        return fd

    def fstat(self, fd):
        if fd not in self._fds:
            return os.fstat(fd)
        ordinal = self._fds[fd]
        self.log.append(("fstat", ordinal))
        mode = stat.S_IFREG if self._fault("fstat", ordinal) == self.NOT_DIR else stat.S_IFDIR
        return types.SimpleNamespace(st_mode=mode)

    def fsync(self, fd):
        if fd not in self._fds:
            self.file_fsyncs += 1
            fault = self.file_fsync_faults.get(self.file_fsyncs)
            if fault is not None:
                raise fault
            return os.fsync(fd)
        ordinal = self._fds[fd]
        self.log.append(("fsync", ordinal))
        self._fault("fsync", ordinal)

    def close(self, fd):
        if fd not in self._fds:
            return os.close(fd)
        ordinal = self._fds.pop(fd)
        self.log.append(("close", ordinal))
        self._fault("close", ordinal)


class RouteADirectoryEntryDurabilityTests(RouteAHarnessTestCase):
    """RA-IMP-T01..T08 (RA-IMP-F01 / RA-08-001): the RUN_CLAIM entry, the run
    folder entry and the OPERATOR_ATTEMPT_V1 entry must each be POSITIVELY
    durable before any credential scope or signed read; any unavailable,
    false, ambiguous or raising result halts with the run id consumed."""

    CLAIM_DETAIL = "RUN_ALREADY_CLAIMED: claim file directory-entry durability unproven"
    FOLDER_DETAIL = "RUN_ALREADY_CLAIMED: run folder directory-entry durability unproven"
    MARKER_DETAIL = "OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker directory-entry durability unproven"

    def _counting_scope(self):
        self.__dict__.setdefault("scope_entries", [])

        @contextlib.contextmanager
        def scope():
            self.scope_entries.append(1)
            yield
        return scope

    def _proxy_run(self, venue, plan, proxy, **kwargs):
        with mock.patch.object(F, "_ROUTE_A_DIRECTORY_FSYNC_PLATFORM_PROVEN", True), mock.patch.object(F, "os", proxy):
            return self._ra_run(venue, plan, real_directory_durability=True,
                                credential_bridge=self._counting_scope(), **kwargs)

    def _assert_durability_stop(self, ctx, venue, plan, baseline, detail, *, marker_written):
        self.assertEqual(ctx.exception.code, RunnerFailureCode.ORCHESTRATION_PHASE_STATE_INVALID)
        self.assertIn("SCOPE_EXPANSION_REQUIRED|" + detail, ctx.exception.detail)
        self.assertEqual(self._physical_reads(venue), 0)  # zero signed reads
        self.assertEqual(venue.writes, [])  # zero CREATE/CANCEL
        self.assertEqual(self.__dict__.get("scope_entries", []), [])  # credential scope never entered
        types_ = self._event_types()[baseline:]
        self.assertEqual(types_.count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)  # consumed exactly once
        self.assertNotIn("WRITER_SESSION_STARTED", types_)
        folder = self.runs_root / plan.run_id
        self.assertTrue((folder / F.RUN_CLAIM_FILE_NAME).is_file())  # the claim stays: run id consumed
        self.assertEqual((folder / F.OPERATOR_ATTEMPT_FILE_NAME).exists(), marker_written)
        known = self.__dict__.setdefault("known_runs", set())
        self.assertEqual({p.name for p in self.runs_root.iterdir()} - known, {plan.run_id})  # no fresh run id
        known.add(plan.run_id)
        self.assertIn(plan.run_id, F.F03FeeExperimentRunnerV1._completed_run_ids)

    def _resolved(self, plan):
        return (self.runs_root / plan.run_id).resolve(), self.runs_root.resolve()

    # -- RA-IMP-T01 ----------------------------------------------------------
    def test_ra_imp_t01_claim_directory_open_failure_or_false_flush_halts_before_signed_reads(self) -> None:
        for ordinal, detail in ((1, self.CLAIM_DETAIL), (2, self.FOLDER_DETAIL)):
            with self.subTest(ordinal=ordinal):
                venue, plan = self._venue(), self._plan()
                proxy = _DirectoryFlushOS({("open", ordinal): PermissionError(13, "synthetic directory open refusal")})
                baseline = len(self._event_types())
                with self.assertRaises(RunnerError) as ctx:
                    self._proxy_run(venue, plan, proxy)
                self._assert_durability_stop(ctx, venue, plan, baseline, detail, marker_written=False)
                self.assertEqual(proxy.dir_calls, ordinal)  # no hidden retry of the failed entry
                self.assertEqual(proxy.log[-1][:2], ("open", ordinal))
        venue, plan = self._venue(), self._plan()
        baseline = len(self._event_types())
        with mock.patch.object(F, "_route_a_fsync_directory", return_value=False):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan, credential_bridge=self._counting_scope())
        self._assert_durability_stop(ctx, venue, plan, baseline, self.CLAIM_DETAIL, marker_written=False)

    # -- RA-IMP-T02 ----------------------------------------------------------
    def test_ra_imp_t02_claim_directory_fsync_failure_with_intact_claim_is_not_file_fsync(self) -> None:
        for ordinal, detail in ((1, self.CLAIM_DETAIL), (2, self.FOLDER_DETAIL)):
            with self.subTest(ordinal=ordinal):
                venue, plan = self._venue(), self._plan()
                proxy = _DirectoryFlushOS({("fsync", ordinal): OSError(22, "synthetic directory fsync failure")})
                baseline = len(self._event_types())
                capture: dict = {}
                with self.assertRaises(RunnerError) as ctx:
                    self._proxy_run(venue, plan, proxy, capture=capture)
                self._assert_durability_stop(ctx, venue, plan, baseline, detail, marker_written=False)
                self.assertNotIn("not durably written", ctx.exception.detail)  # not the file-content class
                self.assertEqual(proxy.file_fsyncs, 1)  # the claim FILE fsync succeeded
                claim = (self.runs_root / plan.run_id / F.RUN_CLAIM_FILE_NAME).read_bytes()
                self.assertEqual(hashlib.sha256(claim).hexdigest(), capture["experiment"].run_claim_sha256)
                self.assertIsNone(capture["experiment"].operator_attempt_sha256)
                self.assertIn(("close", ordinal), proxy.log)  # descriptor still released
        # The separate FILE-content class: claim file fsync fails, no directory step is reached.
        venue, plan = self._venue(), self._plan()
        baseline = len(self._event_types())
        proxy = _DirectoryFlushOS(file_fsync_faults={1: OSError(5, "synthetic claim file fsync failure")})
        with self.assertRaises(RunnerError) as ctx:
            self._proxy_run(venue, plan, proxy)
        self.assertIn("run claim not durably written", ctx.exception.detail)
        self.assertEqual(proxy.dir_calls, 0)
        self.assertEqual(self._physical_reads(venue), 0)
        self.assertEqual(self._event_types()[baseline:].count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)

    # -- RA-IMP-T03 ----------------------------------------------------------
    def test_ra_imp_t03_marker_folder_directory_failure_after_marker_content_is_durable(self) -> None:
        for operation in ("open", "fsync"):
            with self.subTest(operation=operation):
                venue, plan = self._venue(), self._plan()
                proxy = _DirectoryFlushOS({(operation, 3): OSError(13, "synthetic marker directory failure")})
                baseline = len(self._event_types())
                capture: dict = {}
                with self.assertRaises(RunnerError) as ctx:
                    self._proxy_run(venue, plan, proxy, capture=capture)
                self._assert_durability_stop(ctx, venue, plan, baseline, self.MARKER_DETAIL, marker_written=True)
                self.assertEqual(proxy.file_fsyncs, 2)  # claim AND marker content fsyncs succeeded
                folder, root = self._resolved(plan)
                self.assertEqual([entry[2] for entry in proxy.log if entry[0] == "open"], [folder, root, folder])
                marker = json.loads((self.runs_root / plan.run_id / F.OPERATOR_ATTEMPT_FILE_NAME).read_bytes())
                self.assertEqual(marker["attempt_ordinal"], 1)  # marker readback was intact ...
                self.assertIsNone(capture["experiment"].operator_attempt_sha256)  # ... yet NOT accepted (UNCERTAIN/CONSUMED)
                self.assertNotIn("TM", capture["experiment"]._ra.timeline)

    # -- RA-IMP-T04 ----------------------------------------------------------
    def test_ra_imp_t04_helper_false_on_each_call_independently_halts_without_retry(self) -> None:
        details = {1: self.CLAIM_DETAIL, 2: self.FOLDER_DETAIL, 3: self.MARKER_DETAIL}
        for failing in (1, 2, 3):
            for result in (False, None, 1, "True", OSError("synthetic"), RuntimeError("synthetic")):
                with self.subTest(failing=failing, result=repr(result)):
                    venue, plan = self._venue(), self._plan()
                    calls: list = []

                    def helper(path, failing=failing, result=result):
                        calls.append(Path(path).resolve())
                        if len(calls) != failing:
                            return True
                        if isinstance(result, BaseException):
                            raise result
                        return result

                    baseline = len(self._event_types())
                    self.__dict__.pop("scope_entries", None)
                    with mock.patch.object(F, "_route_a_fsync_directory", helper):
                        with self.assertRaises(RunnerError) as ctx:
                            self._ra_run(venue, plan, credential_bridge=self._counting_scope())
                    self._assert_durability_stop(ctx, venue, plan, baseline, details[failing],
                                                 marker_written=failing == 3)
                    folder, root = self._resolved(plan)
                    self.assertEqual(calls, [folder, root, folder][:failing])  # exact order; no retry/fallback

    # -- RA-IMP-T05 ----------------------------------------------------------
    def test_ra_imp_t05_close_fstat_lifecycle_and_invalid_directory_are_conservative(self) -> None:
        cases = (
            ({("close", 1): OSError(9, "synthetic close failure")}, self.CLAIM_DETAIL, False),
            ({("close", 2): OSError(9, "synthetic close failure")}, self.FOLDER_DETAIL, False),
            ({("close", 3): OSError(9, "synthetic close failure")}, self.MARKER_DETAIL, True),
            ({("fstat", 2): _DirectoryFlushOS.NOT_DIR}, self.FOLDER_DETAIL, False),
            ({("open", 1): ValueError("synthetic descriptor error")}, self.CLAIM_DETAIL, False),
        )
        for faults, detail, marker_written in cases:
            with self.subTest(faults=repr(faults)):
                venue, plan = self._venue(), self._plan()
                proxy = _DirectoryFlushOS(faults)
                baseline = len(self._event_types())
                with self.assertRaises(RunnerError) as ctx:
                    self._proxy_run(venue, plan, proxy)
                self._assert_durability_stop(ctx, venue, plan, baseline, detail, marker_written=marker_written)
                opened = [entry[1] for entry in proxy.log if entry[0] == "open"]
                closed = [entry[1] for entry in proxy.log if entry[0] == "close"]
                self.assertEqual(closed, [n for n in opened if ("open", n) not in faults])  # no leaked descriptor
                if ("fstat", 2) in faults:
                    self.assertNotIn(("fsync", 2), proxy.log)  # a non-directory is never "flushed"
        # The primitive itself: invalid/absent directory and a regular file are never durable.
        missing = self.root / "absent_directory"
        regular = self.root / "regular_file"
        regular.write_bytes(b"x")
        with mock.patch.object(F, "_ROUTE_A_DIRECTORY_FSYNC_PLATFORM_PROVEN", True):
            for path in (missing, regular, Path("\x00invalid")):
                with self.subTest(path=path.name):
                    self.assertIs(F._route_a_fsync_directory(path), False)
        # Readback mismatch and exclusive-create collision stop BEFORE any directory step.
        venue, plan = self._venue(), self._plan()
        real_claim_folder = F.claim_run_folder
        proxy = _DirectoryFlushOS()
        with mock.patch.object(F, "claim_run_folder",
                               lambda **kw: (real_claim_folder(**kw)[0], "0" * 64)):
            with self.assertRaises(RunnerError) as ctx:
                self._proxy_run(venue, plan, proxy)
        self.assertIn("RUN_ALREADY_CLAIMED: claim readback mismatch", ctx.exception.detail)
        self.assertEqual((proxy.dir_calls, self._physical_reads(venue)), (0, 0))
        venue, plan = self._venue(), self._plan()
        (self.runs_root / plan.run_id).mkdir()
        proxy = _DirectoryFlushOS()
        with self.assertRaises(RunnerError) as ctx:
            self._proxy_run(venue, plan, proxy)
        self.assertIn("already claimed", ctx.exception.detail)
        self.assertEqual((proxy.dir_calls, self._physical_reads(venue)), (0, 0))

    # -- RA-IMP-T06 ----------------------------------------------------------
    def test_ra_imp_t06_simulated_documented_flush_success_permits_only_the_eligible_continuation(self) -> None:
        venue, plan = self._venue(), self._plan()
        at_first_read: list = []
        proxy = _DirectoryFlushOS()
        hook = lambda op, prepared: (at_first_read.append(proxy.dir_calls) if not at_first_read else None) or None
        capture: dict = {}
        result = self._proxy_run(venue, plan, proxy, capture=capture, builder=self._ra_hooked_builder(venue, hook))
        folder, root = self._resolved(plan)
        self.assertEqual(at_first_read, [3])  # all three entries flushed BEFORE the first signed read
        self.assertEqual([e for e in proxy.log if e[0] == "open"], [("open", 1, folder), ("open", 2, root), ("open", 3, folder)])
        for n in (1, 2, 3):
            self.assertEqual([e for e in proxy.log if e[1] == n and e[0] != "open"], [("fstat", n), ("fsync", n), ("close", n)])
        self.assertEqual(self.scope_entries, [1])  # exactly one credential scope, after the durable marker
        experiment = capture["experiment"]
        marker = (self.runs_root / plan.run_id / F.OPERATOR_ATTEMPT_FILE_NAME).read_bytes()
        self.assertEqual(experiment.operator_attempt_sha256, hashlib.sha256(marker).hexdigest())
        timeline = experiment._ra.timeline
        self.assertLess(timeline["TC"], timeline["TM"])
        self.assertEqual(timeline["TA"] - timeline["T0"], F.ROUTE_A_AUTHORIZATION_NS)  # 300 s unchanged
        self.assertGreater(self._physical_reads(venue), 0)
        self.assertIsNotNone(result)
        # A simulated success never changes the production constant: on Windows it stays unproven.
        self.assertIs(F._ROUTE_A_DIRECTORY_FSYNC_PLATFORM_PROVEN, os.name != "nt")
        self.assertEqual(len(F._ROUTE_A_ACCEPTED_RESERVE_POLICIES), 0)

    def test_ra_imp_t06_real_route_on_this_host_is_held_before_any_directory_primitive(self) -> None:
        """SUPERSEDES the historical RA-IMP-T06 real-host test, which asserted
        that on ``nt`` the real route failed closed at the POSIX claim
        primitive.  Under the accepted native-Windows policy the ``nt`` branch
        no longer uses that primitive, so that assertion is policy-obsolete.
        Replacement: the UNPATCHED sanctioned route on this host -- real
        platform dispatch and the real Stage A holds -- stops before row 9
        and reaches neither a directory primitive nor the Win32 binding (D-11:
        no real Win32 call).  The POSIX primitive itself is unchanged and is
        still never durable on ``nt``."""
        real = F._route_a_fsync_directory(self.runs_root)
        self.assertIs(type(real), bool)
        if os.name == "nt":
            self.assertIs(real, False)
        self.assertIs(F._ROUTE_A_NATIVE_WINDOWS, os.name == "nt")
        self.assertIs(F._ROUTE_A_DIRECTORY_FSYNC_PLATFORM_PROVEN, os.name != "nt")
        self.RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = False
        self.RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP = False
        self.RA_NATIVE_WINDOWS = None  # the real host dispatch, unpatched
        venue, plan = self._venue(), self._plan()
        baseline = self._event_types()
        primitive_calls: list = []
        with mock.patch.object(F, "_route_a_fsync_directory", lambda path: primitive_calls.append(path) or False):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan, credential_bridge=self._counting_scope())
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.AUTHORIZATION_EXPECTATION_MISSING, baseline, venue,
                                                "F03_N1_HISTORY_CONTEXT_UNAVAILABLE")
        self.assertEqual(primitive_calls, [])
        self.assertEqual(self.__dict__.get("scope_entries", []), [])
        self.assertEqual(_WIN32_LOADER_TRAP_CALLS, [])
        self.assertNotIn(plan.run_id, F.F03FeeExperimentRunnerV1._completed_run_ids)

    # -- RA-IMP-T07 ----------------------------------------------------------
    def test_ra_imp_t07_restart_after_uncertain_directory_flush_never_replays_or_rewrites(self) -> None:
        for failing, marker_written in ((2, False), (3, True)):
            with self.subTest(failing=failing):
                plan = self._plan()
                proxy = _DirectoryFlushOS({("fsync", failing): OSError(5, "synthetic uncertain flush")})
                with self.assertRaises(RunnerError):
                    self._proxy_run(self._venue(), plan, proxy)
                folder = self.runs_root / plan.run_id
                frozen = {p.name: p.read_bytes() for p in folder.iterdir()}
                runs_before = sorted(p.name for p in self.runs_root.iterdir())
                self.assertEqual(F.OPERATOR_ATTEMPT_FILE_NAME in frozen, marker_written)
                for fresh_process in (False, True):
                    if fresh_process:
                        F.F03FeeExperimentRunnerV1._completed_run_ids.discard(plan.run_id)
                    venue = self._venue()
                    baseline = len(self._event_types())
                    retry_proxy = _DirectoryFlushOS()  # even a now-"working" flush cannot rescue the run
                    self.__dict__.pop("scope_entries", None)
                    with self.assertRaises(RunnerError) as ctx:
                        self._proxy_run(venue, plan, retry_proxy)
                    # Stage A U equality: the consumed U is refused under lock at
                    # row 9 (CONFLICT), before any claim-root or directory step.
                    self._assert_same_u_refused_before_row9(ctx, venue, baseline, runs_before)
                    self.assertEqual(retry_proxy.dir_calls, 0)  # no later flush is accepted as proof
                    self.assertEqual(self.__dict__.get("scope_entries", []), [])
                    self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, frozen)  # no rewrite/repair
                self.assertEqual(sorted(p.name for p in self.runs_root.iterdir()), runs_before)  # no fresh run id

    # -- RA-IMP-T08 (static) -------------------------------------------------
    def test_ra_imp_t08_static_claim_and_marker_enforce_every_directory_entry(self) -> None:
        source = inspect.getsource(F.F03FeeExperimentRunnerV1._route_a_claim_and_mark)
        code = _code_only(source)
        self.assertEqual(code.count("_route_a_require_directory_entry_durable("), 3)
        self.assertNotIn("_route_a_fsync_directory(", code)  # no unchecked primitive call remains
        first, second, third = [i for i in range(len(source)) if source.startswith("_route_a_require_directory_entry_durable(", i)]
        self.assertLess(source.index("self.claim()"), first)
        self.assertLess(source.index("claim readback mismatch"), first)
        self.assertLess(second, source.index("marker = canonical_json_bytes("))
        self.assertLess(source.index("marker readback unavailable"), third)
        self.assertLess(third, source.index("self.operator_attempt_sha256 ="))
        self.assertLess(source.index("self.operator_attempt_sha256 ="), source.index('self._ra_mark("TM")'))
        helper = inspect.getsource(F._route_a_require_directory_entry_durable)
        self.assertIn("durable is not True", helper)
        self.assertIn("raise F03Halt(HaltCode.SCOPE_EXPANSION_REQUIRED, detail)", helper)
        primitive = inspect.getsource(F._route_a_fsync_directory)
        self.assertIn("_ROUTE_A_DIRECTORY_FSYNC_PLATFORM_PROVEN is not True", primitive)
        self.assertIn("stat.S_ISDIR(os.fstat(fd).st_mode)", primitive)
        orchestration = inspect.getsource(runner.run_f03_release_orchestration_v1)
        self.assertLess(orchestration.index("_route_a_claim_and_mark("), orchestration.index("with bridge():"))


# ---------------------------------------------------------------------------
# R1-D07 F03 Route A Windows storage STAGE A (incomplete, non-admitting).
# Gated sanctioned-orchestration proof (UNPATCHED holds) is kept separate from
# the synthetic component tests (fixture-bypassed pre-row-9 hold only).
# ---------------------------------------------------------------------------

N1_HOLD_DETAIL = "F03_N1_HISTORY_CONTEXT_UNAVAILABLE"
LINK_STOP_DETAIL = "N1_ADMISSION_LINK_UNAVAILABLE"
WIN_ARGS_TAIL = (0xC0000000, 0x00000007, None, 3, 0x02000000, None)
P_PHASE, DC_PHASE, DM_PHASE = "PARENT_AFTER_RUN_FOLDER_MKDIR", "RUN_FOLDER_AFTER_CLAIM", "RUN_FOLDER_AFTER_MARKER"
CLAIM_PREFIX, MARKER_PREFIX = "RUN_ALREADY_CLAIMED: ", "OPERATOR_ATTEMPT_ALREADY_CONSUMED: "


class _StageAHarnessMixin:
    """Counting probes shared by the Stage A suites (TEST-ONLY)."""

    def _scope(self):
        self.__dict__.setdefault("scope_entries", [])

        @contextlib.contextmanager
        def scope():
            self.scope_entries.append(1)
            yield
        return scope

    def _counting_builder(self, venue, **kwargs):
        built = self.__dict__.setdefault("builder_calls", [])
        inner = self._ra_builder(venue, **kwargs)

        def build(context):
            built.append(1)
            return inner(context)
        return build

    @contextlib.contextmanager
    def _consume_spy(self):
        calls = self.__dict__.setdefault("consume_calls", [])
        real = runner.consume_active_execution_authorization_set_v1

        def spy(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)
        with mock.patch.object(runner, "consume_active_execution_authorization_set_v1", spy):
            yield calls

    def _assert_n1_held(self, ctx, venue, plan, baseline_types, runs_before=()):
        """The sanctioned route stopped BEFORE row 9: zero consumption, runtime
        build, persistent mutation, claim/folder, credential scope, signed read,
        write send and Win32 activity."""
        self.assertEqual(ctx.exception.code, RunnerFailureCode.AUTHORIZATION_EXPECTATION_MISSING, ctx.exception.detail)
        self.assertTrue((ctx.exception.detail or "").startswith(N1_HOLD_DETAIL + "|"), ctx.exception.detail)
        self.assertEqual(self.__dict__.get("consume_calls", []), [])
        self.assertEqual(self.__dict__.get("builder_calls", []), [])
        self.assertEqual(self.__dict__.get("scope_entries", []), [])
        self.assertEqual(self._event_types(), baseline_types)
        self.assertEqual((self._physical_reads(venue), venue.writes), (0, []))
        self.assertEqual(sorted(p.name for p in self.runs_root.iterdir()), sorted(runs_before))
        self.assertNotIn(plan.run_id, F.F03FeeExperimentRunnerV1._completed_run_ids)
        self.assertEqual(_WIN32_LOADER_TRAP_CALLS, [])


class RouteAStageAN1HoldTests(_StageAHarnessMixin, RouteAHarnessTestCase):
    """STAGE-A-HOLD / NH-07-001 / Marco D-02: with the holds UNPATCHED, every
    sanctioned F03 Route A path stops before row 9 even when the timing
    profile, accepted-policy registry, plan, U equality and package shape all
    pass.  Only the reserve registry is fixture-populated (so timing passes)."""

    RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = False
    RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP = False

    def _held(self, venue, plan, *, package=None, **kwargs):
        baseline = self._event_types()
        runs_before = [p.name for p in self.runs_root.iterdir()]
        admitted = []
        real_admit = F.admit_route_a_timing_profile_v1

        def admit(*args, **kw):
            schedule = real_admit(*args, **kw)
            admitted.append(schedule)
            return schedule
        with self._consume_spy(), mock.patch.object(F, "admit_route_a_timing_profile_v1", admit):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan, package=package, builder=self._counting_builder(venue),
                             credential_bridge=kwargs.pop("credential_bridge", self._scope()), **kwargs)
        self.assertEqual(len(admitted), 1)  # the timing profile WAS admitted (otherwise-passing input)
        self.assertIs(type(admitted[0]), F.F03RouteAScheduleV1)
        self._assert_n1_held(ctx, venue, plan, baseline, runs_before)
        return ctx

    def test_stage_a_sanctioned_route_held_before_row9_with_otherwise_passing_inputs(self) -> None:
        for native in (False, True, None):
            with self.subTest(native_windows=native):
                self.RA_NATIVE_WINDOWS = native
                venue, plan = self._venue(), self._plan()
                self._held(venue, plan)

    def test_stage_a_positive_control_only_the_hold_prevented_row9(self) -> None:
        """Control: the SAME kind of package proceeds to exactly one durable
        consumption when (only) the pre-row-9 hold is fixture-replaced -- and
        then still stops at the mandatory post-marker link stop."""
        self.RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = True
        venue, plan = self._venue(), self._plan()
        baseline = len(self._event_types())
        with self._consume_spy() as consumed:
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan, credential_bridge=self._scope())
        self.assertEqual(consumed, [1])
        self.assertIn("SCOPE_EXPANSION_REQUIRED|" + LINK_STOP_DETAIL, ctx.exception.detail)
        self.assertEqual(self._event_types()[baseline:].count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)
        self.assertEqual(self.__dict__.get("scope_entries", []), [])

    def test_stage_a_hold_ignores_package_files_caller_inputs_and_existing_folders(self) -> None:
        def plant(root):
            (root / "F03_N1_HISTORY_CONTEXT_V1.json").write_bytes(_ra_canonical(
                {"schema": "F03_N1_HISTORY_CONTEXT_V1", "enrollment": "ACCEPTED", "issuer_tip": "CURRENT"}))
            (root / "F03_N1_ADMISSION_LINK_V1.json").write_bytes(_ra_canonical({"schema": "F03_N1_ADMISSION_LINK_V1"}))
        cases = ("plausible_n1_files", "fault_hook", "production_bridge_selected", "preexisting_u_folder",
                 "short_active_profile")
        for case in cases:
            with self.subTest(case=case):
                venue, plan = self._venue(), self._plan()
                kwargs: dict = {}
                package = None
                if case == "plausible_n1_files":
                    package = self._ra_package(plan, tamper=plant)
                elif case == "fault_hook":
                    kwargs["fault_hook"] = lambda stage: None
                elif case == "production_bridge_selected":
                    kwargs["credential_bridge"] = None  # the real PATH->PEM bridge would be bound, never entered
                elif case == "preexisting_u_folder":
                    (self.runs_root / plan.run_id).mkdir()
                elif case == "short_active_profile":
                    profile = ra_profile_bytes(ra_profile_doc(requested_active_seconds="10"))
                    package = self._ra_package(plan, profile=profile)
                    kwargs["policy"] = ra_policy(profile)
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("KALSHI_DEMO_PRIVATE_KEY_PEM", None)
                    self._held(venue, plan, package=package, **kwargs)
                    self.assertNotIn("KALSHI_DEMO_PRIVATE_KEY_PEM", os.environ)
                if case == "preexisting_u_folder":
                    self.assertEqual(list((self.runs_root / plan.run_id).iterdir()), [])  # untouched
                    (self.runs_root / plan.run_id).rmdir()  # test-owned synthetic folder only

    def test_stage_a_empty_production_registry_remains_additional_defense(self) -> None:
        venue, plan = self._venue(), self._plan()
        package = self._ra_package(plan)
        baseline = self._event_types()
        with self._consume_spy() as consumed:
            with self.assertRaises(RunnerError) as ctx:
                runner.run_f03_release_orchestration_v1(
                    trusted_expectations=self._ra_issue(package), runtime_builder=self._ra_builder(venue),
                    f03_inputs=self._ra_inputs(plan), monotonic_clock_ns=self.inputs.monotonic_ns,
                    wall_clock=self.inputs.clock, uuid_factory=self.inputs.uuid,
                    credential_bridge=_ra_synthetic_credential_scope)
        self.assertEqual(consumed, [])
        self._assert_stopped_before_consumption(ctx, RunnerFailureCode.BRIDGE_AUTHORIZATION_DEADLINE_MISMATCH, baseline, venue,
                                                "ROUTE_A_FEASIBILITY_UNPROVEN")
        self.assertEqual(len(F._ROUTE_A_ACCEPTED_RESERVE_POLICIES), 0)

    def test_stage_a_hold_is_structurally_unconditional_and_parameterless(self) -> None:
        hold = runner._orch_f03_require_n1_history_context
        self.assertEqual(list(inspect.signature(hold).parameters), [])
        hold_ast = ast.parse(inspect.getsource(hold)).body[0]
        statements = [s for s in hold_ast.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        self.assertEqual(len(statements), 1)
        self.assertIsInstance(statements[0], ast.Raise)
        with self.assertRaises(RunnerError) as ctx:
            hold()
        self.assertEqual(ctx.exception.code, RunnerFailureCode.AUTHORIZATION_EXPECTATION_MISSING)
        source = inspect.getsource(runner.run_f03_release_orchestration_v1)
        fn = ast.parse(source).body[0]
        top = [ast.get_source_segment(source, s) for s in fn.body]
        hold_index = [i for i, s in enumerate(top) if s == "_orch_f03_require_n1_history_context()"]
        self.assertEqual(len(hold_index), 1)  # ONE top-level, unconditional call (not nested in if/try/with)
        timing_index = next(i for i, s in enumerate(top) if "admit_route_a_timing_profile_v1(" in s)
        u_index = next(i for i, s in enumerate(top) if "_route_a_require_u_equality(" in s)
        consume_index = next(i for i, s in enumerate(top) if "consume_active_execution_authorization_set_v1(" in s)
        bridge_index = next(i for i, s in enumerate(top) if "with bridge():" in s)
        self.assertLess(timing_index, hold_index[0])
        self.assertLess(u_index, hold_index[0])
        self.assertLess(hold_index[0], consume_index)
        self.assertLess(consume_index, bridge_index)
        module_source = inspect.getsource(runner)
        self.assertEqual(module_source.count("_orch_f03_require_n1_history_context"), 2)  # def + the one call
        self.assertEqual(module_source.count(N1_HOLD_DETAIL + "|"), 1)  # raised from exactly one place
        # The post-marker link stop: an unconditional final raise, no file I/O.
        link = inspect.getsource(F.F03FeeExperimentRunnerV1._route_a_admission_link)
        link_ast = ast.parse("class _X:\n" + link).body[0].body[0]
        self.assertIsInstance(link_ast.body[-1], ast.Raise)
        self.assertIn(LINK_STOP_DETAIL, ast.get_source_segment("class _X:\n" + link, link_ast.body[-1]))
        for banned in ("open(", "write_bytes(", "mkdir(", "_route_a_win32_flush_directory("):
            self.assertNotIn(banned, _code_only(link))
        claim_at = source.index("experiment._route_a_claim_and_mark(f03_context)")
        link_at = source.index("experiment._route_a_admission_link(f03_context)")
        self.assertLess(claim_at, link_at)
        self.assertLess(link_at, source.index("except _f03.F03Halt as exc:", claim_at))
        self.assertLess(link_at, source.index("with bridge():"))
        # No new public parameter / constructor knob can select continuation.
        self.assertEqual(set(inspect.signature(runner.run_f03_release_orchestration_v1).parameters),
                         {"trusted_expectations", "runtime_builder", "f03_inputs", "monotonic_clock_ns", "wall_clock",
                          "uuid_factory", "credential_bridge", "fault_hook"})
        self.assertEqual(set(inspect.signature(F.F03FeeExperimentRunnerV1.__init__).parameters),
                         {"self", "runtime", "plan", "observed_identity", "run_artifact_root", "prohibited_roots",
                          "invocation_id"})

    def test_stage_a_link_stop_after_marker_halts_before_credentials_on_both_branches(self) -> None:
        self.RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = True  # component fixture: reach the post-marker stop only
        for native in (False, True):
            with self.subTest(native_windows=native):
                self.RA_NATIVE_WINDOWS = native
                self.__dict__.pop("scope_entries", None)
                venue, plan = self._venue(), self._plan()
                win32 = _RecordingWin32()
                capture: dict = {}
                baseline = len(self._event_types())
                with self.assertRaises(RunnerError) as ctx:
                    self._ra_run(venue, plan, capture=capture, win32=win32, credential_bridge=self._scope())
                self.assertEqual(ctx.exception.code, RunnerFailureCode.ORCHESTRATION_PHASE_STATE_INVALID)
                self.assertIn("F03 claim/attempt|SCOPE_EXPANSION_REQUIRED|" + LINK_STOP_DETAIL, ctx.exception.detail)
                folder = self.runs_root / plan.run_id
                self.assertEqual(sorted(p.name for p in folder.iterdir()), sorted([F.RUN_CLAIM_FILE_NAME, F.OPERATOR_ATTEMPT_FILE_NAME]))
                self.assertFalse((folder / "F03_N1_ADMISSION_LINK_V1.json").exists())  # no placeholder link
                self.assertEqual(self.__dict__.get("scope_entries", []), [])
                self.assertEqual((self._physical_reads(venue), venue.writes), (0, []))
                types_ = self._event_types()[baseline:]
                self.assertEqual(types_.count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)
                self.assertNotIn("WRITER_SESSION_STARTED", types_)
                self.assertIn(plan.run_id, F.F03FeeExperimentRunnerV1._completed_run_ids)
                timeline = capture["experiment"]._ra.timeline
                self.assertLess(timeline["TC"], timeline["TM"])
                self.assertLess(timeline["TM"], timeline["TL_UNAVAILABLE"])
                self.assertEqual(len(win32.api_names()), 9 if native else 0)


class RouteAStageAN1HoldBootHoldTests(_StageAHarnessMixin, RouteAHarnessTestCase):
    """The same unconditional pre-row-9 hold for the BOOT_HOLD entry class."""

    ENTRY = RA_BOOT
    RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = False
    RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP = False

    def test_stage_a_boot_hold_entry_is_held_before_row9(self) -> None:
        for native in (False, True):
            with self.subTest(native_windows=native):
                self.RA_NATIVE_WINDOWS = native
                venue, plan = self._venue(), self._plan()
                baseline = self._event_types()
                with self._consume_spy():
                    with self.assertRaises(RunnerError) as ctx:
                        self._ra_run(venue, plan, builder=self._counting_builder(venue, phases=2, implied=20),
                                     credential_bridge=self._scope())
                self._assert_n1_held(ctx, venue, plan, baseline)


class RouteAStageAUEqualityTests(_StageAHarnessMixin, RouteAHarnessTestCase):
    """NH-04-001/002/005: exact typed U = plan.run_id = binding/typed-expectation
    invocation_id (pre-row 9) = runner invocation_id = live receipt
    invocation_id (attach and every protected seam); per-command IDs keep their
    own meaning.  Component fixture: the pre-row-9 hold is fixture-replaced."""

    RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = True
    RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP = True

    def test_u_inequality_in_the_package_stops_before_row9(self) -> None:
        variants = {
            "other_uuid4": lambda u: str(uuid.uuid4()),
            "uuid1_not_v4": lambda u: str(uuid.UUID(int=uuid.UUID(u).int, version=1)),
            "uppercase": lambda u: u.upper(),
            "prefixed": lambda u: "inv_" + u,
            "hex_without_hyphens": lambda u: uuid.UUID(u).hex,
        }
        for name, derive in variants.items():
            with self.subTest(variant=name):
                venue, plan = self._venue(), self._plan()
                package = self._ra_package(plan, invocation_id=derive(plan.run_id))
                baseline = self._event_types()
                with self._consume_spy() as consumed:
                    with self.assertRaises(RunnerError) as ctx:
                        self._ra_run(venue, plan, package=package)
                self.assertEqual(consumed, [])
                self._assert_stopped_before_consumption(ctx, RunnerFailureCode.BRIDGE_AUTHORIZATION_INVOCATION_MISMATCH,
                                                        baseline, venue, "F03 run/invocation identity|")

    def test_u_equality_is_enforced_at_attach_and_at_every_later_seam(self) -> None:
        real_attach = F.F03FeeExperimentRunnerV1._route_a_attach
        for when in ("before_attach", "after_attach"):
            for native in (False, True):
                with self.subTest(when=when, native_windows=native):
                    self.RA_NATIVE_WINDOWS = native
                    self.__dict__.pop("scope_entries", None)

                    def attach(experiment, ctx, when=when):
                        if when == "before_attach":
                            experiment.invocation_id = str(uuid.uuid4())
                            return real_attach(experiment, ctx)
                        result = real_attach(experiment, ctx)
                        experiment.invocation_id = experiment.plan.run_id.upper()
                        return result
                    venue, plan = self._venue(), self._plan()
                    win32 = _RecordingWin32()
                    baseline = len(self._event_types())
                    with mock.patch.object(F.F03FeeExperimentRunnerV1, "_route_a_attach", attach):
                        with self.assertRaises(RunnerError) as ctx:
                            self._ra_run(venue, plan, win32=win32, credential_bridge=self._scope())
                    self.assertEqual(ctx.exception.code, RunnerFailureCode.ORCHESTRATION_PHASE_STATE_INVALID)
                    self.assertIn("TARGET_DOMAIN_INELIGIBLE|route-A run/invocation identity U inequality", ctx.exception.detail)
                    self.assertEqual(list(self.runs_root.iterdir()), [])  # no claim: refused before mkdir
                    self.assertEqual(win32.calls, [])
                    self.assertEqual((self._physical_reads(venue), venue.writes), (0, []))
                    self.assertEqual(self.__dict__.get("scope_entries", []), [])
                    self.assertEqual(self._event_types()[baseline:].count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)

    def test_u_binds_invocation_but_never_replaces_per_command_identities(self) -> None:
        venue, plan = self._venue(), self._plan()
        package = self._ra_package(plan)
        capture: dict = {}
        result = self._ra_run(venue, plan, package=package, capture=capture)
        self.assertIsNone(result.f03_result.halt, result.f03_result.halt)
        receipt = capture["ctx"].receipt
        self.assertEqual(receipt.invocation_id, plan.run_id)
        self.assertEqual(capture["experiment"].invocation_id, plan.run_id)
        self.assertEqual(receipt.execution_attempt_id, f"attempt_ra_{self._packages}")  # authorization attempt id unchanged
        self.assertEqual(_write_kinds(venue), ["CREATE_ORDER_V2", "CANCEL_ORDER_V2"])
        self.assertNotIn(plan.run_id, json.dumps(venue.writes))  # client-order / request ids are NOT U
        self.assertNotIn(plan.run_id, json.dumps([o.client_order_id for o in capture["experiment"].orders]))

    def test_u_equality_unit_rejects_every_normalization(self) -> None:
        u = str(uuid.uuid4())
        self.assertEqual(F._route_a_require_u_equality(u, u, u), u)
        for run_id, others in (
            (u.upper(), (u.upper(),)), ("{" + u + "}", ("{" + u + "}",)), (" " + u, (" " + u,)),
            (str(uuid.uuid1()), ()), (uuid.UUID(u), (u,)), (u, (u.upper(),)), (u, (u + " ",)), (u, (uuid.UUID(u),)),
            (u, (str(uuid.uuid4()),)), (u, (None,)), (u, (u, "x")),
        ):
            with self.subTest(run_id=repr(run_id), others=repr(others)):
                with self.assertRaises(F.F03Halt) as ctx:
                    F._route_a_require_u_equality(run_id, *others)
                self.assertEqual(ctx.exception.code, A.HaltCode.TARGET_DOMAIN_INELIGIBLE)


class RouteANativeWindowsStorageTests(_StageAHarnessMixin, RouteAHarnessTestCase):
    """WF-05..WF-11 / WFT-01..WFT-20 (offline synthetic): the native-Windows
    component with a RECORDING FAKE kernel32 on any host.  Component fixture:
    the pre-row-9 hold is fixture-replaced; the post-marker link stop is NOT,
    so every run ends at the mandatory N1_ADMISSION_LINK_UNAVAILABLE stop or
    earlier -- never in credential scope.  Simulated API success is not
    physical durability or target-volume qualification evidence."""

    RA_NATIVE_WINDOWS = True
    RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = True
    RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP = False

    def _win_run(self, win32, plan=None, **kwargs):
        self.__dict__.pop("scope_entries", None)
        venue = self._venue()
        plan = plan or self._plan()
        capture: dict = {}
        baseline = len(self._event_types())
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, plan, capture=capture, win32=win32, credential_bridge=self._scope(), **kwargs)
        return types.SimpleNamespace(ctx=ctx, venue=venue, plan=plan, capture=capture, baseline=baseline,
                                     folder=self.runs_root / plan.run_id)

    def _assert_halted_held(self, run, detail):
        """Terminal hold after row 9: U consumed exactly once, no credential
        scope, signed read, write send or writer session; records kept."""
        exc = run.ctx.exception
        self.assertEqual(exc.code, RunnerFailureCode.ORCHESTRATION_PHASE_STATE_INVALID, exc.detail)
        self.assertIn(detail, exc.detail)
        self.assertNotIn(str(self.root), exc.detail)  # sanitized: no resolved path in the detail
        self.assertEqual(self.__dict__.get("scope_entries", []), [])
        self.assertEqual((self._physical_reads(run.venue), run.venue.writes), (0, []))
        types_ = self._event_types()[run.baseline:]
        self.assertEqual(types_.count("EXECUTION_AUTHORIZATION_SET_CONSUMED"), 1)
        self.assertNotIn("WRITER_SESSION_STARTED", types_)
        self.assertIn(run.plan.run_id, F.F03FeeExperimentRunnerV1._completed_run_ids)
        self.assertFalse((run.folder / "F03_N1_ADMISSION_LINK_V1.json").exists())

    def _paths(self, plan):
        return str(self.runs_root.resolve()), str((self.runs_root / plan.run_id).resolve())

    # -- WFT-01 / WFT-10 (exact positive synthetic sequence) ----------------
    def test_wft01_exact_parent_then_child_sequence_readbacks_then_link_stop(self) -> None:
        plan = self._plan()
        folder = self.runs_root / plan.run_id
        seen: list = []
        hooks = {("CreateFileW", n): (lambda n=n: seen.append(
            (n, folder.is_dir(), (folder / F.RUN_CLAIM_FILE_NAME).exists(), (folder / F.OPERATOR_ATTEMPT_FILE_NAME).exists())))
            for n in (1, 2, 3)}
        win32 = _RecordingWin32(hooks=hooks)
        real_readback = F._route_a_readback_record

        def readback(path, expected, **kwargs):
            win32.calls.append(("READBACK", (Path(path).name,)))
            return real_readback(path, expected, **kwargs)
        with mock.patch.object(F, "_route_a_readback_record", readback):
            run = self._win_run(win32, plan)
        self._assert_halted_held(run, "SCOPE_EXPANSION_REQUIRED|" + LINK_STOP_DETAIL)
        self.assertEqual(win32.api_names(), [
            "CreateFileW", "FlushFileBuffers", "CloseHandle",                  # P after mkdir(D), before the claim
            "CreateFileW", "FlushFileBuffers", "CloseHandle", "READBACK",      # D after the claim, then readback
            "CreateFileW", "FlushFileBuffers", "CloseHandle", "READBACK"])     # D after the marker, then readback
        p_path, d_path = self._paths(plan)
        creates = [args for name, args in win32.calls if name == "CreateFileW"]
        self.assertEqual(creates, [(p_path,) + WIN_ARGS_TAIL, (d_path,) + WIN_ARGS_TAIL, (d_path,) + WIN_ARGS_TAIL])
        self.assertEqual(seen, [(1, True, False, False), (2, True, True, False), (3, True, True, True)])
        # One FlushFileBuffers and one CloseHandle per valid handle, same handle, nothing left open.
        handles = [args[0] for name, args in win32.calls if name == "FlushFileBuffers"]
        self.assertEqual(handles, win32.closed)
        self.assertEqual(len(set(handles)), 3)
        self.assertEqual(win32.open_handles, set())
        self.assertNotIn("GetLastError", [name for name, _ in win32.calls])  # only read after a failure
        self.assertEqual([e for e in [r for r, _ in win32.calls] if e == "READBACK"], ["READBACK", "READBACK"])
        self.assertEqual([args[0] for name, args in win32.calls if name == "READBACK"],
                         [F.RUN_CLAIM_FILE_NAME, F.OPERATOR_ATTEMPT_FILE_NAME])
        experiment = run.capture["experiment"]
        claim = (run.folder / F.RUN_CLAIM_FILE_NAME).read_bytes()
        marker = (run.folder / F.OPERATOR_ATTEMPT_FILE_NAME).read_bytes()
        self.assertEqual(experiment.run_claim_sha256, hashlib.sha256(claim).hexdigest())
        self.assertEqual(experiment.operator_attempt_sha256, hashlib.sha256(marker).hexdigest())
        self.assertEqual(claim, canonical_json_bytes(experiment._claim_object()))  # unchanged F03_RUN_CLAIM_V1
        doc = json.loads(marker)
        self.assertEqual(set(doc), {"attempt_schema", "run_id", "attempt_ordinal", "run_claim_sha256", "plan_binding_sha256",
                                    "timing_profile_sha256", "reserve_policy_id", "authorization_receipt_digest",
                                    "process_instance_id"})
        self.assertEqual((doc["run_id"], doc["run_claim_sha256"], doc["attempt_ordinal"]),
                         (plan.run_id, experiment.run_claim_sha256, 1))
        self.assertEqual(doc["authorization_receipt_digest"], run.capture["ctx"].receipt_digest)
        # WF-19: every storage step is a monotonic mark on the original row-0 clock, inside TA.
        timeline = experiment._ra.timeline
        order = ["WS_CLAIM_START", "WS_RUN_FOLDER_CREATED", f"WS_{P_PHASE}_START", f"WS_{P_PHASE}_END", "WS_CLAIM_WRITE",
                 f"WS_{DC_PHASE}_START", f"WS_{DC_PHASE}_END", "WS_CLAIM_READBACK", "TC", "WS_MARKER_WRITE",
                 f"WS_{DM_PHASE}_START", f"WS_{DM_PHASE}_END", "WS_MARKER_READBACK", "TM", "TL_UNAVAILABLE"]
        values = [timeline[k] for k in order]
        self.assertEqual(values, sorted(values))
        self.assertEqual(len(set(values)), len(values))
        self.assertEqual(timeline["TA"] - timeline["T0"], F.ROUTE_A_AUTHORIZATION_NS)
        self.assertLess(values[-1], timeline["TA"])
        self.assertGreater(values[0], timeline["T0"])
        log = experiment.route_a_timing_record()["storage_log"]
        self.assertEqual([e["phase"] for e in log], [P_PHASE, DC_PHASE, DM_PHASE])
        for entry in log:
            self.assertEqual((entry["open"], entry["flush"], entry["close"]), ("OK", "OK", "OK"))
            self.assertGreater(entry["elapsed_ns"], 0)
        self.assertNotIn(str(self.root), json.dumps(log))
        self.assertEqual(self.__dict__.get("directory_flushes", []), [])  # the POSIX primitive is never used on nt

    # -- WFT-05 / WFT-06 / WFT-07 ------------------------------------------
    def test_wft05_06_07_open_and_flush_failures_halt_independently_at_each_boundary(self) -> None:
        boundaries = {1: (CLAIM_PREFIX, P_PHASE, False, False), 2: (CLAIM_PREFIX, DC_PHASE, True, False),
                      3: (MARKER_PREFIX, DM_PHASE, True, True)}
        faults = {
            "open_null": (("CreateFileW", (None, 5)), "CreateFileW", "5"),
            "open_zero": (("CreateFileW", (0, 2)), "CreateFileW", "2"),
            "open_invalid_handle_value": (("CreateFileW", ((1 << 64) - 1, 32)), "CreateFileW", "32"),
            "open_minus_one": (("CreateFileW", (-1, 5)), "CreateFileW", "5"),
            "open_raises": (("CreateFileW", OSError("synthetic")), "CreateFileW", "EXCEPTION"),
            "flush_zero": (("FlushFileBuffers", (0, 1117)), "FlushFileBuffers", "1117"),
            "flush_bool_false": (("FlushFileBuffers", (False, 21)), "FlushFileBuffers", "21"),
            "flush_raises": (("FlushFileBuffers", RuntimeError("synthetic")), "FlushFileBuffers", "EXCEPTION"),
        }
        for ordinal, (prefix, phase, claim_exists, marker_exists) in boundaries.items():
            for name, ((api, scripted), failed_api, last_error) in faults.items():
                with self.subTest(boundary=phase, fault=name):
                    win32 = _RecordingWin32(script={(api, ordinal): scripted})
                    run = self._win_run(win32)
                    self._assert_halted_held(
                        run, f"SCOPE_EXPANSION_REQUIRED|{prefix}WINDOWS_DIRECTORY_FLUSH_FAILED phase={phase} "
                             f"api={failed_api} last_error={last_error}")
                    names = [n for n, _ in win32.calls]
                    self.assertEqual(names.count("CreateFileW"), ordinal)  # no retry, no later boundary
                    if last_error not in ("EXCEPTION",):
                        failing = max(i for i, (n, _) in enumerate(win32.calls) if n == failed_api)
                        self.assertEqual(names[failing + 1], "GetLastError")  # captured immediately
                    opened_valid = ordinal - (1 if api == "CreateFileW" else 0)
                    self.assertEqual(len(win32.closed), opened_valid)  # one close per VALID handle only
                    self.assertEqual(len(set(win32.closed)), len(win32.closed))
                    self.assertEqual(win32.open_handles, set())
                    self.assertEqual((run.folder / F.RUN_CLAIM_FILE_NAME).exists(), claim_exists)
                    self.assertEqual((run.folder / F.OPERATOR_ATTEMPT_FILE_NAME).exists(), marker_exists)
                    experiment = run.capture["experiment"]
                    self.assertIsNone(experiment.operator_attempt_sha256)
                    self.assertNotIn("TM", experiment._ra.timeline)
                    if ordinal == 1:
                        self.assertIsNone(experiment.run_claim_sha256)  # a child flush never substitutes for P

    # -- WFT-08 --------------------------------------------------------------
    def test_wft08_close_failures_are_recorded_separately_and_never_mask_the_first_failure(self) -> None:
        for ordinal, (prefix, phase) in {1: (CLAIM_PREFIX, P_PHASE), 2: (CLAIM_PREFIX, DC_PHASE),
                                         3: (MARKER_PREFIX, DM_PHASE)}.items():
            with self.subTest(case="close_zero_after_flush_ok", boundary=phase):
                win32 = _RecordingWin32(script={("CloseHandle", ordinal): (0, 6)})
                run = self._win_run(win32)
                self._assert_halted_held(run, f"{prefix}WINDOWS_DIRECTORY_CLOSE_FAILED phase={phase} api=CloseHandle last_error=6")
                self.assertNotIn("WINDOWS_DIRECTORY_FLUSH_FAILED", run.ctx.exception.detail)
                self.assertEqual(len(win32.closed), ordinal)
            with self.subTest(case="flush_and_close_fail", boundary=phase):
                win32 = _RecordingWin32(script={("FlushFileBuffers", ordinal): (0, 1117), ("CloseHandle", ordinal): (0, 6)})
                run = self._win_run(win32)
                detail = run.ctx.exception.detail
                self._assert_halted_held(run, f"{prefix}WINDOWS_DIRECTORY_FLUSH_FAILED phase={phase} api=FlushFileBuffers "
                                              f"last_error=1117; WINDOWS_DIRECTORY_CLOSE_FAILED phase={phase} "
                                              f"api=CloseHandle last_error=6")
                self.assertLess(detail.index("FLUSH_FAILED"), detail.index("CLOSE_FAILED"))  # first failure first
                self.assertEqual(len(win32.closed), ordinal)  # exactly one close attempt, no double close
            with self.subTest(case="close_raises", boundary=phase):
                win32 = _RecordingWin32(script={("CloseHandle", ordinal): OSError("synthetic")})
                run = self._win_run(win32)
                self._assert_halted_held(run, f"{prefix}WINDOWS_DIRECTORY_CLOSE_FAILED phase={phase} api=CloseHandle "
                                              f"last_error=EXCEPTION")
                self.assertEqual(len(win32.closed), ordinal)

    # -- WFT-09 --------------------------------------------------------------
    def test_wft09_successful_apis_with_divergent_readback_is_a_hard_halt(self) -> None:
        def flip(path):
            data = bytearray(path.read_bytes())
            data[-2] ^= 0x01
            path.write_bytes(bytes(data))

        def truncate(path):
            path.write_bytes(path.read_bytes()[:-1])
        for name, mutate in (("same_length_flip", flip), ("truncated", truncate)):
            for ordinal, (prefix, record) in {2: (CLAIM_PREFIX, F.RUN_CLAIM_FILE_NAME),
                                              3: (MARKER_PREFIX, F.OPERATOR_ATTEMPT_FILE_NAME)}.items():
                with self.subTest(mutation=name, record=record):
                    plan = self._plan()
                    target = self.runs_root / plan.run_id / record
                    win32 = _RecordingWin32(hooks={("FlushFileBuffers", ordinal): lambda target=target, m=mutate: m(target)})
                    run = self._win_run(win32, plan)
                    self._assert_halted_held(run, f"{prefix}WINDOWS_READBACK_MISMATCH byte/hash")
                    self.assertEqual(win32.api_names().count("CloseHandle"), ordinal)  # every API returned success
                    self.assertNotIn("GetLastError", [n for n, _ in win32.calls])
                    self.assertTrue(target.exists())  # the divergent record is kept, never repaired
                    self.assertIsNone(run.capture["experiment"].operator_attempt_sha256)
                    if ordinal == 2:
                        self.assertFalse((run.folder / F.OPERATOR_ATTEMPT_FILE_NAME).exists())

    # -- WFT-04 / WFT-15 -----------------------------------------------------
    def test_wft04_short_write_fsync_close_and_collision_failures_keep_partial_records(self) -> None:
        real_open = open

        class _Handle:
            def __init__(self, inner, short=False, close_error=False):
                self.inner, self.short, self.close_error = inner, short, close_error

            def write(self, data):
                if self.short:
                    return self.inner.write(data[:-1])
                return self.inner.write(data)

            def flush(self):
                return self.inner.flush()

            def fileno(self):
                return self.inner.fileno()

            def close(self):
                self.inner.close()
                if self.close_error:
                    raise OSError("synthetic close failure")

        def opener(target_name, **options):
            def fake_open(path, mode="r", *args, **kwargs):
                handle = real_open(path, mode, *args, **kwargs)
                if Path(path).name == target_name and mode == "xb":
                    return _Handle(handle, **options)
                return handle
            return fake_open

        claim_detail = "RUN_ALREADY_CLAIMED: run claim not durably written"
        marker_detail = "OPERATOR_ATTEMPT_ALREADY_CONSUMED: marker not durably written"
        cases = (
            ("claim_short_write", F.RUN_CLAIM_FILE_NAME, dict(short=True), claim_detail + " (short write)", 1),
            ("claim_close_failure", F.RUN_CLAIM_FILE_NAME, dict(close_error=True), claim_detail + " (close failed)", 1),
            ("marker_short_write", F.OPERATOR_ATTEMPT_FILE_NAME, dict(short=True), marker_detail + " (short write)", 2),
            ("marker_close_failure", F.OPERATOR_ATTEMPT_FILE_NAME, dict(close_error=True), marker_detail + " (close failed)", 2),
        )
        for name, record, options, detail, creates in cases:
            with self.subTest(case=name):
                win32 = _RecordingWin32()
                with mock.patch.object(F, "open", opener(record, **options), create=True):
                    run = self._win_run(win32)
                self._assert_halted_held(run, detail)
                self.assertEqual(win32.api_names().count("CreateFileW"), creates)  # no D flush after a failed write
                self.assertTrue((run.folder / record).exists())  # partial record left in place (no truncate/delete)
        real_fsync = os.fsync
        for name, failing_call, detail, creates in (("claim_fsync", 1, claim_detail + " (write/flush/fsync)", 1),
                                                    ("marker_fsync", 2, marker_detail + " (write/flush/fsync)", 2)):
            with self.subTest(case=name):
                calls: list = []

                def fsync(fd, failing_call=failing_call):
                    calls.append(fd)
                    if len(calls) == failing_call:
                        raise OSError(5, "synthetic file fsync failure")
                    return real_fsync(fd)
                win32 = _RecordingWin32()
                with mock.patch.object(F.os, "fsync", fsync):
                    run = self._win_run(win32)
                self._assert_halted_held(run, detail)
                self.assertEqual(win32.api_names().count("CreateFileW"), creates)
        for name, ordinal, record, detail in (
                ("claim_collision", 1, F.RUN_CLAIM_FILE_NAME, "SCOPE_EXPANSION_REQUIRED|RUN_ALREADY_CLAIMED: claim file already exists"),
                ("marker_collision", 2, F.OPERATOR_ATTEMPT_FILE_NAME, "SCOPE_EXPANSION_REQUIRED|OPERATOR_ATTEMPT_ALREADY_CONSUMED")):
            with self.subTest(case=name):
                plan = self._plan()
                planted = self.runs_root / plan.run_id / record
                win32 = _RecordingWin32(hooks={("FlushFileBuffers", ordinal): lambda planted=planted: planted.write_bytes(b"{}")})
                run = self._win_run(win32, plan)
                self._assert_halted_held(run, detail)
                self.assertEqual(planted.read_bytes(), b"{}")  # never overwritten
                self.assertEqual(win32.api_names().count("CreateFileW"), ordinal)

    # -- WFT-03 / WFT-02 -----------------------------------------------------
    def test_wft03_existing_run_folder_is_occupied_with_zero_native_calls(self) -> None:
        plan = self._plan()
        (self.runs_root / plan.run_id).mkdir()
        win32 = _RecordingWin32()
        run = self._win_run(win32, plan)
        self._assert_halted_held(run, "RUN_ALREADY_CLAIMED: run id already claimed (no replay/resume)")
        self.assertEqual(win32.calls, [])
        self.assertEqual(list(run.folder.iterdir()), [])

    def test_wft02_identity_drift_unsupported_api_and_containment_fail_closed(self) -> None:
        real_identity = F._route_a_directory_identity
        for drift_phase, prefix, claim_exists in (
                ("RUN_FOLDER_CONSISTENCY", CLAIM_PREFIX, False), (f"{P_PHASE}_POST_CLOSE", CLAIM_PREFIX, False),
                (f"{DC_PHASE}_PRE_OPEN", CLAIM_PREFIX, True), (f"{DM_PHASE}_POST_CLOSE", MARKER_PREFIX, True)):
            with self.subTest(drift=drift_phase):
                def identity(path, *, phase, detail_prefix, drift_phase=drift_phase):
                    value = real_identity(path, phase=phase, detail_prefix=detail_prefix)
                    return (value[0], value[1] + 1) if phase == drift_phase else value
                win32 = _RecordingWin32()
                with mock.patch.object(F, "_route_a_directory_identity", identity):
                    run = self._win_run(win32)
                self._assert_halted_held(run, f"{prefix}WINDOWS_STORAGE_IDENTITY_CHANGED")
                self.assertEqual((run.folder / F.RUN_CLAIM_FILE_NAME).exists(), claim_exists)
                self.assertEqual(win32.open_handles, set())
        with self.subTest(case="api_unsupported"):
            def unavailable():
                raise OSError("synthetic: native API unavailable")
            with mock.patch.object(F, "_route_a_load_win32_directory_api", unavailable):
                run = self._win_run(None)
            self._assert_halted_held(run, f"{CLAIM_PREFIX}WINDOWS_DIRECTORY_FLUSH_UNSUPPORTED phase={P_PHASE}")
            self.assertFalse((run.folder / F.RUN_CLAIM_FILE_NAME).exists())
        with self.subTest(case="root_inside_repository"):
            plan = self._plan()
            win32 = _RecordingWin32()
            run = self._win_run(win32, plan, inputs=self._ra_inputs(plan, runs_root=self.repository_root / "tests"))
            self.assertIn("SCOPE_EXPANSION_REQUIRED|run artifact root containment", run.ctx.exception.detail)
            self.assertEqual(win32.calls, [])
            self.assertFalse((self.repository_root / "tests" / plan.run_id).exists())

    # -- WFT-18 --------------------------------------------------------------
    def test_wft18_deadline_reached_inside_a_storage_step_halts_without_extending_ta(self) -> None:
        for ordinal, phase, claim_read in ((1, P_PHASE, False), (2, DC_PHASE, False), (3, DM_PHASE, True)):
            with self.subTest(boundary=phase):
                win32 = _RecordingWin32(hooks={("FlushFileBuffers", ordinal): lambda: self.inputs.jump(300 * S)})
                run = self._win_run(win32)
                self._assert_halted_held(run, f"RUN_DEADLINE_EXCEEDED|authorization expired at storage step {phase}_END")
                experiment = run.capture["experiment"]
                timeline = experiment._ra.timeline
                self.assertEqual(timeline["TA"] - timeline["T0"], F.ROUTE_A_AUTHORIZATION_NS)  # TA never moved
                self.assertGreaterEqual(timeline[f"WS_{phase}_END"], timeline["TA"])
                self.assertEqual(win32.api_names().count("CreateFileW"), ordinal)  # nothing after the deadline
                self.assertEqual(experiment.run_claim_sha256 is not None, claim_read)
                self.assertIsNone(experiment.operator_attempt_sha256)

    # -- WFT-11 / WFT-12 / WFT-13 --------------------------------------------
    def test_wft11_12_partial_windows_state_is_never_resumed_repaired_or_reissued(self) -> None:
        plan = self._plan()
        win32 = _RecordingWin32(script={("FlushFileBuffers", 3): (0, 1117)})
        run = self._win_run(win32, plan)
        self._assert_halted_held(run, f"{MARKER_PREFIX}WINDOWS_DIRECTORY_FLUSH_FAILED phase={DM_PHASE}")
        frozen = {p.name: p.read_bytes() for p in run.folder.iterdir()}
        runs_before = sorted(p.name for p in self.runs_root.iterdir())
        for fresh_process in (False, True):
            for hold_enforced in (False, True):
                with self.subTest(fresh_process=fresh_process, hold_enforced=hold_enforced):
                    if fresh_process:
                        F.F03FeeExperimentRunnerV1._completed_run_ids.discard(plan.run_id)
                    self.RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = not hold_enforced
                    retry = _RecordingWin32()  # even a now-"working" native flush cannot rescue the run
                    venue = self._venue()
                    baseline = len(self._event_types())
                    self.__dict__.pop("scope_entries", None)
                    with self.assertRaises(RunnerError) as ctx:
                        self._ra_run(venue, plan, win32=retry, credential_bridge=self._scope())
                    # With or without the pre-row-9 hold fixture, the consumed U is
                    # refused even earlier by the unchanged rows 1-8 classifier.
                    self._assert_same_u_refused_before_row9(ctx, venue, baseline, runs_before)
                    self.assertEqual(retry.calls, [])
                    self.assertEqual(self.__dict__.get("scope_entries", []), [])
                    self.assertEqual({p.name: p.read_bytes() for p in run.folder.iterdir()}, frozen)
                    self.assertEqual(sorted(p.name for p in self.runs_root.iterdir()), runs_before)
        self.RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = True

    # -- WFT-17 --------------------------------------------------------------
    def test_wft17_posix_branch_unchanged_and_never_reaches_win32(self) -> None:
        self.RA_NATIVE_WINDOWS = False
        win32 = _RecordingWin32()
        run = self._win_run(win32)
        self._assert_halted_held(run, LINK_STOP_DETAIL)
        self.assertEqual(win32.calls, [])  # no native call on the POSIX branch
        folder, root = run.folder.resolve(), self.runs_root.resolve()
        self.assertEqual([Path(p).resolve() for p in self.directory_flushes], [folder, root, folder])  # historical D, P, D
        self.assertEqual(run.capture["experiment"]._ra.storage_log, [])

    # -- WFT-10 / WFT-20 (static) --------------------------------------------
    def test_wft10_static_exact_win32_surface_and_forbidden_operations(self) -> None:
        self.assertEqual((F._WIN32_GENERIC_READ_WRITE, F._WIN32_FILE_SHARE_READ_WRITE_DELETE, F._WIN32_OPEN_EXISTING,
                          F._WIN32_FILE_FLAG_BACKUP_SEMANTICS), (0xC0000000, 0x00000007, 3, 0x02000000))
        raw_flush = inspect.getsource(F._route_a_win32_flush_directory)
        flush = _code_only(raw_flush)
        self.assertEqual(flush.count(".CreateFileW("), 1)
        self.assertEqual(flush.count(".FlushFileBuffers("), 1)
        self.assertEqual(flush.count(".CloseHandle("), 1)
        self.assertIn("api.CreateFileW(str(path), _WIN32_GENERIC_READ_WRITE, _WIN32_FILE_SHARE_READ_WRITE_DELETE, None,", raw_flush)
        self.assertIn("_WIN32_OPEN_EXISTING, _WIN32_FILE_FLAG_BACKUP_SEMANTICS, None)", raw_flush)
        self.assertLess(raw_flush.index("    finally:"), raw_flush.index("closed = api.CloseHandle(handle)"))
        binding = inspect.getsource(F._RouteAWin32DirectoryApiV1)
        self.assertIn('ctypes.WinDLL("kernel32", use_last_error=True)', binding)
        for name in ("CreateFileW", "FlushFileBuffers", "CloseHandle"):
            self.assertEqual(binding.count(f"kernel32.{name}"), 1, name)
        self.assertEqual(binding.count("kernel32."), 3)  # exactly three native functions bound
        whole = inspect.getsource(F)
        for forbidden in ("FILE_FLAG_WRITE_THROUGH", "FILE_FLAG_NO_BUFFERING", "FILE_FLAG_OPEN_REPARSE_POINT",
                          "FILE_FLAG_DELETE_ON_CLOSE", "FILE_FLAG_OVERLAPPED", "AdjustTokenPrivileges", "SeBackupPrivilege",
                          "SeRestorePrivilege", "DeviceIoControl", "\\\\\\\\.\\\\", "GENERIC_ALL", "winreg", "subprocess"):
            self.assertNotIn(forbidden, whole, forbidden)
        self.assertNotIn("import ctypes", whole.split("class _RouteAWin32DirectoryApiV1")[0])  # lazy: no import-time load
        raw_windows = inspect.getsource(F.F03FeeExperimentRunnerV1._route_a_claim_and_mark_native_windows)
        windows_code = _code_only(raw_windows)
        for banned in ("_route_a_fsync_directory(", "_route_a_require_directory_entry_durable(", "self.claim()",
                       "claim_run_folder(", "rmdir(", "unlink(", "rename(", "replace(", "remove(", "truncate("):
            self.assertNotIn(banned, windows_code, banned)
        windows = raw_windows
        positions = [windows.index(token) for token in (
            "os.mkdir(folder)", f'"{P_PHASE}"', "RUN_FOLDER_CONSISTENCY", "RUN_CLAIM_FILE_NAME, claim,",
            f'"{DC_PHASE}"', "self.run_claim_sha256 = _route_a_readback_record(", 'self._ra_mark("TC")',
            "OPERATOR_ATTEMPT_FILE_NAME, marker,", f'"{DM_PHASE}"', "attempt_sha256 = _route_a_readback_record(",
            'self._ra_mark("TM")')]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(windows.index("_completed_run_ids.add("), windows.index("os.mkdir(folder)"))  # U spent first
        posix = inspect.getsource(F.F03FeeExperimentRunnerV1._route_a_claim_and_mark)
        self.assertLess(posix.index("if _ROUTE_A_NATIVE_WINDOWS:"), posix.index("ra = self._route_a_require(ctx)"))
        self.assertNotIn("_route_a_win32", posix)
        # The WF-10 subcodes and Stage A stop names are detail strings, never enum members.
        stage_a_names = {F.WINDOWS_DIRECTORY_FLUSH_UNSUPPORTED, F.WINDOWS_DIRECTORY_FLUSH_FAILED,
                         F.WINDOWS_DIRECTORY_CLOSE_FAILED, F.WINDOWS_STORAGE_IDENTITY_CHANGED, F.WINDOWS_READBACK_MISMATCH,
                         N1_HOLD_DETAIL, LINK_STOP_DETAIL}
        for enum_cls in (A.HaltCode, RunnerFailureCode):
            self.assertEqual({m.value for m in enum_cls} & stage_a_names, set())
            self.assertEqual(set(enum_cls.__members__) & stage_a_names, set())

    # -- unit ----------------------------------------------------------------
    def test_unit_checked_flush_records_exact_arguments_and_last_error_order(self) -> None:
        directory = self.root / "unit_dir"
        directory.mkdir()
        for script, expected_names, detail in (
                ({}, ["CreateFileW", "FlushFileBuffers", "CloseHandle"], None),
                ({("CreateFileW", 1): (None, 3)}, ["CreateFileW", "GetLastError"], "api=CreateFileW last_error=3"),
                ({("FlushFileBuffers", 1): (0, 5)}, ["CreateFileW", "FlushFileBuffers", "GetLastError", "CloseHandle"],
                 "api=FlushFileBuffers last_error=5"),
                ({("CloseHandle", 1): (0, 6)}, ["CreateFileW", "FlushFileBuffers", "CloseHandle", "GetLastError"],
                 "WINDOWS_DIRECTORY_CLOSE_FAILED phase=UNIT api=CloseHandle last_error=6")):
            with self.subTest(script=repr(script)):
                win32 = _RecordingWin32(script=script)
                record: list = []
                with mock.patch.object(F, "_route_a_load_win32_directory_api", lambda: win32):
                    if detail is None:
                        F._route_a_win32_flush_directory(directory, phase="UNIT", detail_prefix="X: ", record=record)
                    else:
                        with self.assertRaises(F.F03Halt) as ctx:
                            F._route_a_win32_flush_directory(directory, phase="UNIT", detail_prefix="X: ", record=record)
                        self.assertEqual(ctx.exception.code, A.HaltCode.SCOPE_EXPANSION_REQUIRED)
                        self.assertTrue(ctx.exception.detail.startswith("X: "))
                        self.assertIn(detail, ctx.exception.detail)
                self.assertEqual([n for n, _ in win32.calls], expected_names)
                self.assertEqual(win32.calls[0], ("CreateFileW", (str(directory),) + WIN_ARGS_TAIL))
                self.assertEqual(len(record), 1)
        for handle, valid in ((None, False), (0, False), (-1, False), ((1 << 32) - 1, False), ((1 << 64) - 1, False),
                              (True, False), ("12", False), (1.0, False), (8, True), (0x4004, True)):
            with self.subTest(handle=repr(handle)):
                self.assertIs(F._route_a_win32_valid_handle(handle), valid)

    def test_unit_readback_rejects_malformed_noncanonical_unclosed_and_unbound_records(self) -> None:
        path = self.root / "record.json"
        good = canonical_json_bytes({"claim_schema": "S", "run_id": "u", "n": 1})
        path.write_bytes(good)
        self.assertEqual(F._route_a_readback_record(path, good, detail_prefix="P: ",
                                                    bound_fields={"claim_schema": "S", "run_id": "u"}),
                         hashlib.sha256(good).hexdigest())
        cases = (
            (b'{"a":1,"a":1}', {}, "malformed"), (b'{"a":1.5}', {}, "malformed"), (b'{"a":NaN}', {}, "malformed"),
            (b'{"b":1, "a":2}', {}, "noncanonical"), (b'[1]', {}, "noncanonical"), (b"\xff", {}, "malformed"),
            (good, {"run_id": "v"}, "bound field run_id"), (good, {"n": True}, "bound field n"),
            (good, {"missing": "x"}, "bound field missing"),
        )
        for raw, bound, detail in cases:
            with self.subTest(raw=raw, bound=bound):
                path.write_bytes(raw)
                with self.assertRaises(F.F03Halt) as ctx:
                    F._route_a_readback_record(path, raw, detail_prefix="P: ", bound_fields=bound)
                self.assertIn("P: WINDOWS_READBACK_MISMATCH", ctx.exception.detail)
                self.assertIn(detail, ctx.exception.detail)
        path.write_bytes(good[:-1] + b" ")  # same length, different bytes
        with self.assertRaises(F.F03Halt) as ctx:
            F._route_a_readback_record(path, good, detail_prefix="P: ", bound_fields={})
        self.assertIn("P: WINDOWS_READBACK_MISMATCH byte/hash", ctx.exception.detail)
        with self.assertRaises(F.F03Halt) as ctx:
            F._route_a_readback_record(self.root / "absent.json", good, detail_prefix="P: ", bound_fields={})
        self.assertIn("readback unavailable", ctx.exception.detail)

    def test_unit_directory_identity_is_a_plain_directory_consistency_check_only(self) -> None:
        directory = self.root / "plain"
        directory.mkdir()
        regular = self.root / "regular"
        regular.write_bytes(b"x")
        identity = F._route_a_directory_identity(directory, phase="U", detail_prefix="P: ")
        self.assertEqual(identity, F._route_a_directory_identity(directory, phase="U", detail_prefix="P: "))
        for path, detail in ((regular, "not a plain directory"), (self.root / "absent", "directory unavailable")):
            with self.subTest(path=path.name):
                with self.assertRaises(F.F03Halt) as ctx:
                    F._route_a_directory_identity(path, phase="U", detail_prefix="P: ")
                self.assertIn("P: WINDOWS_STORAGE_IDENTITY_CHANGED phase=U " + detail, ctx.exception.detail)
        link = self.root / "dir_link"
        try:
            os.symlink(directory, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            link = None  # symlink creation needs a privilege this unelevated host may lack
        if link is not None:
            with self.assertRaises(F.F03Halt):
                F._route_a_directory_identity(link, phase="U", detail_prefix="P: ")
        reparse = types.SimpleNamespace(st_mode=stat.S_IFDIR, st_dev=1, st_ino=2,
                                        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        with mock.patch.object(F.os, "lstat", lambda p: reparse):
            with self.assertRaises(F.F03Halt) as ctx:
                F._route_a_directory_identity(directory, phase="U", detail_prefix="P: ")
        self.assertIn("not a plain directory", ctx.exception.detail)


class StageAPinClosureTests(unittest.TestCase):
    """Marco D-04 acyclic pin closure: final R -> TS literal; current-base
    START_HERE -> TS literal (CANONICAL_PIN_MAINTENANCE); final TS -> TF
    literal; final R -> TF literal.  Nothing pins TF or F (no cycle)."""

    @staticmethod
    def _blob(path: Path) -> str:
        data = path.read_bytes()
        return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

    def test_pin_closure_is_consistent_and_acyclic(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ts_path = root / "tests" / "test_kalshi_shadow_experiment.py"
        module = ast.parse(ts_path.read_text(encoding="utf-8"))
        ts_pins = next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                       and any(getattr(t, "id", None) == "PROTECTED_BASE_BLOBS" for t in node.targets))
        r_rel = "src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py"
        tr_rel = "tests/test_kalshi_minimal_market_maker_experiment_runner.py"
        r_blob = self._blob(root / r_rel)
        self.assertEqual(ts_pins[r_rel], r_blob)
        self.assertEqual(PROTECTED_BLOBS[r_rel], r_blob)
        self.assertEqual(ts_pins["project_context/START_HERE.md"], self._blob(root / "project_context" / "START_HERE.md"))
        self.assertEqual(PROTECTED_BLOBS["tests/test_kalshi_shadow_experiment.py"], self._blob(ts_path))
        self.assertEqual(ts_pins[tr_rel], PROTECTED_BLOBS[tr_rel])  # TR protected and unchanged in both
        self.assertEqual(self._blob(root / tr_rel), "e31c7bf789e4bb0684fbd3688f4fa3867388cff5")
        for pinned in (ts_pins, PROTECTED_BLOBS):
            self.assertNotIn("tests/test_kalshi_f03_fee_semantics_runner.py", pinned)
            self.assertNotIn("src/arb/venues/kalshi/f03_fee_semantics_runner.py", pinned)


class RouteACleanupOwnershipTests(RouteAHarnessTestCase):
    """RA-T09 single orchestration-owned cleanup: writer -> PEM -> receipt."""

    def _ordered_run(self, venue, *, run_order=None, cleanup_raises=False):
        events: list = []
        real_cleanup = runner._fail_closed_end_writer_session
        real_revoke = ledger_binding.ActiveAuthorizationConsumptionV1.revoke

        def cleanup(handle, session_id):
            events.append("writer_cleanup")
            out = real_cleanup(handle, session_id)
            if cleanup_raises:  # failure REPORTED by the canonical cleanup (locks already released)
                raise RuntimeError("synthetic cleanup failure")
            return out

        def revoke(receipt):
            events.append("receipt_revoked")
            return real_revoke(receipt)

        @contextlib.contextmanager
        def scope():
            events.append("credential_scope_entered")
            try:
                yield
            finally:
                events.append("pem_removed")

        patches = [mock.patch.object(runner, "_fail_closed_end_writer_session", cleanup),
                   mock.patch.object(ledger_binding.ActiveAuthorizationConsumptionV1, "revoke", revoke)]
        if run_order is not None:
            patches.append(mock.patch.object(F.F03FeeExperimentRunnerV1, "run_order", run_order))
        capture: dict = {}
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            try:
                result = self._ra_run(venue, credential_bridge=scope, capture=capture)
            except BaseException as exc:  # noqa: BLE001 - asserted by callers
                return events, exc, capture
        return events, result, capture

    def test_ra_t09_success_cleanup_order(self) -> None:
        events, result, capture = self._ordered_run(self._venue())
        self.assertEqual(result.writer_cleanup, "ENDED")
        self.assertEqual(events, ["credential_scope_entered", "writer_cleanup", "pem_removed", "receipt_revoked"])
        with self.assertRaises(F.F03Halt):
            capture["ctx"].assert_live()

    def test_ra_t09_exception_after_writer_acquisition_cleans_once_and_preserves_primary_error(self) -> None:
        baseline = len(self._event_types())

        def boom(experiment, index, price):
            raise RuntimeError("synthetic primary failure")

        events, exc, capture = self._ordered_run(self._venue(), run_order=boom)
        self.assertIsInstance(exc, RuntimeError)
        self.assertEqual(str(exc), "synthetic primary failure")
        self.assertEqual(events, ["credential_scope_entered", "writer_cleanup", "pem_removed", "receipt_revoked"])
        types_ = self._event_types()[baseline:]
        self.assertEqual((types_.count("WRITER_SESSION_STARTED"), types_.count("WRITER_SESSION_ENDED")), (1, 1))
        with self.assertRaises(F.F03Halt):
            capture["ctx"].assert_live()

    def test_ra_t09_cleanup_failure_is_raised_never_swallowed(self) -> None:
        events, exc, capture = self._ordered_run(self._venue(), cleanup_raises=True)
        self.assertIsInstance(exc, RunnerError)
        self.assertEqual(exc.code, RunnerFailureCode.ORCHESTRATION_WRITER_CLEANUP_FAILED)
        self.assertEqual(events, ["credential_scope_entered", "writer_cleanup", "pem_removed", "receipt_revoked"])

    def test_ra_t09_cleanup_failure_never_masks_the_primary_error(self) -> None:
        def boom(experiment, index, price):
            raise RuntimeError("synthetic primary failure")

        events, exc, _ = self._ordered_run(self._venue(), run_order=boom, cleanup_raises=True)
        self.assertIsInstance(exc, RuntimeError)
        self.assertEqual(events.count("writer_cleanup"), 1)

    def test_ra_t09_t13_pre_writer_halt_mints_no_tail_and_no_writer(self) -> None:
        venue = self._venue(extra_orders=[{
            "order_id": "unrelated-1", "client_order_id": str(uuid.uuid4()), "ticker": "KXOTHER-1", "side": "yes",
            "status": "resting", "fill_count_fp": "0.00", "remaining_count_fp": "1.00", "initial_count_fp": "1.00",
            "subaccount": 1, "subaccount_number": 1, "exchange_index": 0, "yes_price_dollars": "0.1000"}])
        baseline = len(self._event_types())
        result = self._ra_run(venue)
        timing = result.route_a_timing
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.BASELINE_OPEN_ORDER_CONFLICT)
        self.assertEqual((timing["first_event_kind"], timing["tail_eligible"], timing["Ttail_effective"]), ("HALT", False, None))
        self.assertEqual(result.writer_cleanup, "NOT_ACQUIRED")
        self.assertNotIn("WRITER_SESSION_STARTED", self._event_types()[baseline:])
        self._assert_started_reads_inside_caps(timing)  # zero signed starts at/after the first event


class RouteAWriteAndTailTests(RouteAHarnessTestCase):
    """RA-T04 / RA-T10 / RA-T11 / RA-T12 / RA-T13 / RA-T14 integration."""

    def test_ra_t04_t10_ambiguous_create_latches_first_halt_and_bounds_the_tail(self) -> None:
        venue = self._venue()
        venue.create_raises = TimeoutError("synthetic timeout after send boundary")
        capture: dict = {}
        result = self._ra_run(venue, capture=capture)
        f03, timing = result.f03_result, result.route_a_timing
        self.assertEqual(f03.halt.code, A.HaltCode.CREATE_RESULT_AMBIGUOUS)
        self.assertEqual(_write_kinds(venue), ["CREATE_ORDER_V2"])  # no resend, no cancel guess
        self.assertEqual((timing["counters"]["create_t3"], timing["counters"]["create_physical"]), (1, 1))
        first = timing["Tfirst_halt_or_close"]
        self.assertEqual(timing["first_event_kind"], "HALT")
        self.assertLess(first, timing["Tactive_end"])
        self.assertEqual(timing["Ttail_effective"], min(first + 20 * S, timing["Tactive_end"] + 20 * S, timing["TA"] - 30 * S))
        self.assertEqual(timing["Ttail_effective"], first + 20 * S)
        self.assertTrue(any(e["kind"] == "READ" and e["started"] and e["now_ns"] >= first for e in timing["send_log"]))
        self._assert_started_reads_inside_caps(timing)
        # Repeated HALT / later error never relatches or slides the cap.
        experiment = capture["experiment"]
        self.inputs.jump(5 * S)
        experiment._halt(F.F03Halt(A.HaltCode.ORDER_RECONCILIATION_INCOMPLETE, "later error"))
        experiment._ra_latch_first_event("ACTIVE_CLOSE")
        self.assertEqual((experiment._ra.first_event_ns, experiment._ra.tail_end_ns), (first, timing["Ttail_effective"]))
        self.assertEqual(experiment.halt.code, A.HaltCode.CREATE_RESULT_AMBIGUOUS)

    def test_ra_t10_t14_deadline_immediately_before_create_adapter_is_zero_sends(self) -> None:
        venue = self._venue()
        real_binding = runner._gate_d_prepare_normal_write_binding

        def late_binding(**kwargs):
            out = real_binding(**kwargs)
            if kwargs["prepared"]["operation_name"] == "CREATE_ORDER_V2":
                self.inputs.jump(120 * S)  # past Tactive_end, before the adapter
            return out

        with mock.patch.object(runner, "_gate_d_prepare_normal_write_binding", late_binding):
            result = self._ra_run(venue)
        timing, f03 = result.route_a_timing, result.f03_result
        self.assertEqual(venue.writes, [])
        self.assertEqual((timing["counters"]["create_t3"], timing["counters"]["create_physical"]), (1, 0))  # T3 consumed, never refunded
        self.assertTrue(any(e["kind"] == "CREATE" and not e["started"] for e in timing["send_log"]))
        create = f03.shared_record["orders"][0]["create"]
        self.assertEqual(create["classification"], "FRESHNESS_EXPIRED_BEFORE_ADAPTER")  # existing closed class, zero send
        self.assertTrue(create["detail"].startswith("ROUTE_A_DEADLINE: "))
        self.assertFalse(create["transport_invoked"])
        self.assertEqual(f03.final_state, "HALTED_HELD")
        self._assert_started_reads_inside_caps(timing)

    def test_ra_t14_deadline_inside_active_cancel_holds_unresolved_exposure(self) -> None:
        venue = self._venue()
        real_binding = runner._gate_d_prepare_normal_write_binding

        def late_binding(**kwargs):
            out = real_binding(**kwargs)
            if kwargs["prepared"]["operation_name"] == "CANCEL_ORDER_V2":
                self.inputs.jump(120 * S)
            return out

        with mock.patch.object(runner, "_gate_d_prepare_normal_write_binding", late_binding):
            result = self._ra_run(venue)
        f03, timing = result.f03_result, result.route_a_timing
        self.assertEqual(_write_kinds(venue), ["CREATE_ORDER_V2"])
        self.assertEqual((timing["counters"]["cancel_t3"], timing["counters"]["cancel_physical"]), (1, 0))
        self.assertEqual(f03.halt.code, A.HaltCode.CANCEL_RESULT_AMBIGUOUS)
        self.assertTrue(f03.unresolved_active_exposure)
        self._assert_started_reads_inside_caps(timing)

    def test_ra_t04_insufficient_active_reserve_at_writer_admission_zero_writes(self) -> None:
        venue = self._venue()
        real_stage3 = runner._complete_stage3_active_release_and_normal_writer_v2

        def slow_release(read_phase, runtime, **kwargs):
            out = real_stage3(read_phase, runtime, **kwargs)
            self.inputs.jump(160 * S)  # TA - TW now below A+R+C+H
            return out

        with mock.patch.object(runner, "_complete_stage3_active_release_and_normal_writer_v2", slow_release):
            result = self._ra_run(venue)
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.RUN_DEADLINE_EXCEEDED)
        self.assertIn("DEADLINE_RESERVATION_INSUFFICIENT", result.f03_result.halt.detail)
        self.assertEqual(venue.writes, [])
        self.assertEqual(result.writer_cleanup, "ENDED")
        self.assertIsNone(result.route_a_timing["Ttail_effective"])
        self._assert_started_reads_inside_caps(result.route_a_timing)

    def test_ra_t14_authorization_expiry_before_claim_and_before_writer_admission(self) -> None:
        venue = self._venue()
        baseline = len(self._event_types())
        with self.assertRaises(RunnerError) as ctx:
            self._ra_run(venue, builder=self._ra_builder(venue, after=lambda rt: self.inputs.jump(301 * S)))
        self.assertEqual(ctx.exception.code, RunnerFailureCode.BRIDGE_AUTHORIZATION_DEADLINE_EXPIRED)
        self.assertEqual(self._physical_reads(venue), 0)
        self.assertEqual(list(self.runs_root.iterdir()), [])
        self.assertNotIn("WRITER_SESSION_STARTED", self._event_types()[baseline:])
        venue = self._venue()
        real_stage3 = runner._complete_stage3_active_release_and_normal_writer_v2

        def expired_release(read_phase, runtime, **kwargs):
            self.inputs.jump(300 * S)
            return real_stage3(read_phase, runtime, **kwargs)

        with mock.patch.object(runner, "_complete_stage3_active_release_and_normal_writer_v2", expired_release):
            result = self._ra_run(venue)
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.TARGET_DOMAIN_INELIGIBLE)
        self.assertEqual(result.writer_cleanup, "NOT_ACQUIRED")
        self.assertEqual(venue.writes, [])
        self._assert_started_reads_inside_caps(result.route_a_timing)

    def test_ra_t11_g_write_bound_below_create_plus_cancel_blocks_new_risk(self) -> None:
        venue = self._venue()
        plan = self._plan()
        result = self._ra_run(venue, plan, package=self._ra_package(plan, max_ordinary=1))
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.WRITE_LIMIT_CONSUMED)
        self.assertEqual(venue.writes, [])
        self.assertEqual(result.route_a_timing["counters"]["create_t3"], 0)

    def test_ra_t11_whole_run_counters_refuse_at_exact_limits(self) -> None:
        ledger = F.F03BudgetLedgerV1()
        for _ in range(F.GET_MAX):
            ledger.charge_get("GET_ORDERS", phase="X")
        with self.assertRaises(F.F03Halt):
            ledger.charge_get("GET_ORDERS", phase="X")
        self.assertEqual(ledger.get_count, 200)
        self.assertEqual(ledger.request_log[-1]["state"], "REFUSED_BEFORE_TRANSPORT")
        overflow = F.F03BudgetLedgerV1(get_count=190)
        with self.assertRaises(F.F03Halt):
            overflow.charge_unobserved_protected_gets(11, phase="PROTECTED_STAGE3_PHASE")
        for action in ("create", "cancel"):
            ledger = F.F03BudgetLedgerV1()
            charge = ledger.charge_create_t3 if action == "create" else ledger.charge_cancel_t3
            charge()
            charge()
            with self.assertRaises(F.F03Halt):
                charge()
        self.assertEqual(F.BALANCE_GETS_MAX, 9)

    def test_ra_t12_slow_response_is_incomplete_and_spends_quota(self) -> None:
        venue = self._venue()
        state = {"done": False}

        def slow(op, prepared):
            if op is RunnerOperation.GET_MARKET and not state["done"]:
                state["done"] = True
                self.inputs.jump(6 * S)  # body completes after the accepted 5 s attempt bound
            return None

        result = self._ra_run(venue, builder=self._ra_hooked_builder(venue, slow))
        timing = result.route_a_timing
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.RUN_DEADLINE_EXCEEDED)
        self.assertTrue(any(e["kind"] == "LATE_COMPLETION" for e in timing["send_log"]))
        self.assertEqual(timing["counters"]["get"], self._physical_reads(venue) + 72)  # the slow GET stays charged
        self.assertEqual(venue.writes, [])

    def test_ra_t12_truncated_body_fails_closed_with_quota_spent(self) -> None:
        venue = self._venue()
        hook = lambda op, prepared: (RawOperationResponseV1(http_status=200, content_type="application/json",
                                                            body_bytes=b'{"market": {"tick')
                                      if op is RunnerOperation.GET_MARKET else None)
        result = self._ra_run(venue, builder=self._ra_hooked_builder(venue, hook))
        self.assertIsNotNone(result.f03_result.halt)
        self.assertEqual(result.f03_result.final_state, "HALTED_HELD")
        self.assertEqual(result.route_a_timing["counters"]["get"], self._physical_reads(venue) + 72)
        self.assertEqual(venue.writes, [])

    def test_ra_t13_release_split_brain_or_insufficient_collateral_rejected_before_risk(self) -> None:
        venue = self._venue()
        with mock.patch.object(runner, "_complete_stage3_active_release_and_normal_writer_v2",
                               side_effect=RunnerError(RunnerFailureCode.STAGE_3K_REVALIDATION_FAILED)):
            result = self._ra_run(venue)
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.TARGET_DOMAIN_INELIGIBLE)
        self.assertEqual((result.writer_cleanup, venue.writes), ("NOT_ACQUIRED", []))
        poor = FakeDemoVenue(balances=self._balances(b0="1.0000"))
        result = self._ra_run(poor)
        self.assertEqual(result.f03_result.halt.code, A.HaltCode.INSUFFICIENT_EXISTING_BALANCE)
        self.assertEqual((result.writer_cleanup, poor.writes), ("NOT_ACQUIRED", []))
        primary = types.SimpleNamespace(
            domain_binding=types.SimpleNamespace(environment="KALSHI_DEMO", subaccount=0),
            active_contract=types.SimpleNamespace(environment="KALSHI_DEMO"))
        with self.assertRaises(F.F03Halt) as ctx:
            F.verify_domain_and_origin(primary)
        self.assertEqual(ctx.exception.code, A.HaltCode.HISTORICAL_PRIMARY_DOMAIN_PROHIBITED)

    def test_ra_t14_retrograde_clock_loses_continuity_and_stops_all_sends(self) -> None:
        venue = self._venue()
        state = {"armed": False}

        def back(op, prepared):
            if op is RunnerOperation.GET_BALANCE and not state["armed"]:
                state["armed"] = True
                self.inputs.mono -= 10 * S  # backward clock step
            return None

        result = self._ra_run(venue, builder=self._ra_hooked_builder(venue, back))
        timing = result.route_a_timing
        self.assertTrue(timing["continuity_lost"])
        self.assertEqual(venue.writes, [])
        self.assertIsNotNone(result.f03_result.halt)

    def test_ra_t15_counterexample_economics_unchanged_under_route_a(self) -> None:
        venue = _counterexample_venue(self)
        result = self._ra_run(venue)
        q = {r["question_id"]: r for r in result.f03_result.question_results}
        self.assertEqual(q["QF03-01"]["status"], "INCONCLUSIVE")
        self.assertEqual(q["QF03-01"]["scoped_conclusion"], "NO_ELIGIBLE_POSITIVE_DISCRIMINATOR")
        self.assertEqual({r["status"] for r in q.values()} - set(A.QuestionStatus), set())
        A.validate_fee_experiment_run_v1(json.loads(json.dumps(result.f03_result.shared_record)))


# ---------------------------------------------------------------------------
# Stage B SB-IN-001..003 (+ pure SB-IN-004) DRAFT-ONLY input decoder --
# R1-D07_F03_STAGE_B_CLOSED_INPUT_DRAFT_PARSER_IMPLEMENTATION_01.  Every input
# document and comparison pin below is SYNTHETIC MODEL INPUT built in memory:
# no fixture pin is actual source-applicability proof, no draft is admission,
# eligibility, observation, history, physical-identity or terminal-credit
# evidence, and no test here reads an evidence source, store, credential or the
# network.  Stale/unsupported real provenance is outside this structural slice;
# no runnable consumer of the draft exists.
# ---------------------------------------------------------------------------

DRAFT_RUN_ID = "1b4e28ba-2fa1-41d2-883f-0016d3cca427"
DRAFT_RUNNER_PATH = "src/arb/venues/kalshi/f03_fee_semantics_runner.py"
DRAFT_ANALYZER_PATH = "src/arb/venues/kalshi/f03_fee_semantics_analyzer.py"
DRAFT_SOURCES = {DRAFT_RUNNER_PATH: "4" * 64, DRAFT_ANALYZER_PATH: "5" * 64}  # SYNTHETIC comparison pins
DRAFT_REF_NAMES = ("market", "account_class", "fee_epoch", "fee_source", "risk", "domain", "source_snapshot", "timing",
                   "operator_selection", "terminal_credit")
DRAFT_TERMINAL_ID = "SYNTHETIC-TERMINAL-CREDIT-REF"
INVALID, PIN = F.F03_INPUTS_DRAFT_SCHEMA_INVALID, F.F03_INPUTS_DRAFT_PIN_MISMATCH
_DELETE = object()


def draft_ref(name, **over) -> dict:
    ref = {"logical_id": "SYNTHETIC-" + name.upper().replace("_", "-") + "-REF", "bytes": 2048, "sha256": "c" * 64}
    ref.update(over)
    return ref


def draft_doc() -> dict:
    """A closed, otherwise well-formed SYNTHETIC ``F03OperatorRuntimeInputsV1``
    (paired-null terminal credit, one order, DIRECT class)."""
    refs = {name: draft_ref(name) for name in DRAFT_REF_NAMES}
    refs["terminal_credit"] = None
    return {
        "schema": "F03OperatorRuntimeInputsV1",
        "run": {"run_id": DRAFT_RUN_ID, "private_evidence_permission": False},
        "market": {"ticker": TICKER, "event_ticker": EVENT, "series_ticker": SERIES,
                   "market_metadata_evidence_id": "SYNTHETIC-MARKET-REF"},
        "fee": {"account_class": "DIRECT", "account_class_evidence_id": "SYNTHETIC-ACCOUNT-CLASS-REF",
                "fee_epoch_id": "FEE-SCHEDULE-2026-07-07", "fee_type": "quadratic", "taker_multiplier": "1",
                "maker_multiplier": "1", "fee_regime_change_pending": False,
                "terminal_credit_exclusion_evidence_id": None},
        "orders": {"order1_limit_price": "0.5000", "order2_limit_price": None, "planned_order_count": 1},
        "implementation": {"expected_commit": "1" * 40, "expected_tree": "2" * 40, "expected_parent": "3" * 40,
                           "implementation_artifacts": {DRAFT_RUNNER_PATH: "4" * 64}},
        "source_and_scope": {
            "environment": "KALSHI_DEMO", "origin": "https://external-api.demo.kalshi.co",
            "authority_namespace_id": "ARB_KALSHI_DEMO_PRIMARY_AUTHORITY_V1", "subaccount": 1, "exchange_index": 0,
            "domain_binding_sha256": "d" * 64, "active_contract_sha256": "a" * 64, "risk_config_sha256": "b" * 64,
            "fee_source_binding_sha256": "e" * 64, "timing_profile_sha256": "f" * 64, "route": "ROUTE_A_300S",
            "canonical_strategy_G": "NOT_APPLICABLE_TO_ISOLATED_F03_PROBE"},
        "evidence_refs": refs,
    }


def draft_with(*changes, doc=None) -> dict:
    """``changes`` are ``(dotted_path, value)``; ``_DELETE`` removes the key."""
    doc = copy_module.deepcopy(draft_doc() if doc is None else doc)
    for path, value in changes:
        *parents, leaf = path.split(".") if path else [""]
        target = doc
        for part in parents:
            target = target[part]
        if value is _DELETE:
            del target[leaf]
        else:
            target[leaf] = value
    return doc


def draft_text_bytes(document) -> bytes:
    """``canonical_json_bytes`` layout WITHOUT its secret denylist (only to
    craft refused prohibited-field inputs)."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def draft_bytes(doc=None) -> bytes:
    return canonical_json_bytes(draft_doc() if doc is None else doc)


def draft_parse(raw, *, sources=None, expected_bytes=None, expected_sha=None):
    """The real pure decoder with explicit comparison pins (defaulting, in the
    TEST helper only, to the exact pins of ``raw`` and ``DRAFT_SOURCES``)."""
    return F.parse_f03_operator_runtime_inputs_draft_v1(
        raw, expected_raw_bytes=len(raw) if expected_bytes is None else expected_bytes,
        expected_raw_sha256=hashlib.sha256(raw).hexdigest() if expected_sha is None else expected_sha,
        expected_participating_sources=DRAFT_SOURCES if sources is None else sources)


def _thaw(value):
    if isinstance(value, types.MappingProxyType):
        return {key: _thaw(child) for key, child in value.items()}
    return value


def _replace_once(raw: bytes, old: bytes, new: bytes) -> bytes:
    assert raw.count(old) == 1, old
    return raw.replace(old, new, 1)


class _F03DraftAssertions(unittest.TestCase):
    def assert_refused(self, raw, classification, detail=None, **kwargs):
        with self.assertRaises(F.F03OperatorInputsDraftError) as ctx:
            draft_parse(raw, **kwargs)
        self.assertEqual(ctx.exception.classification, classification, ctx.exception.detail)
        if detail is not None:
            self.assertIn(detail, ctx.exception.detail)
        return ctx.exception

    def assert_doc_refused(self, doc, classification=INVALID, detail=None, **kwargs):
        return self.assert_refused(draft_bytes(doc), classification, detail, **kwargs)


class F03InputsDraftMappingTests(_F03DraftAssertions):
    """SB-IN-001/003 + dispatch evidence 1: exact one/two-order drafts, every
    mapped field and derived property, raw/source pin comparison.  A draft is
    never an admission or eligibility grant."""

    EXPECTED_PLAN = {
        "run_id": DRAFT_RUN_ID, "ticker": TICKER, "event_ticker": EVENT, "series_ticker": SERIES,
        "account_class": "DIRECT", "account_class_evidence_id": "SYNTHETIC-ACCOUNT-CLASS-REF",
        "fee_epoch_id": "FEE-SCHEDULE-2026-07-07", "fee_type": "quadratic", "taker_multiplier": D("1"),
        "maker_multiplier": D("1"), "fee_regime_change_pending": False, "order1_limit_price": D("0.5000"),
        "order2_limit_price": None, "expected_commit": "1" * 40, "expected_tree": "2" * 40,
        "expected_parent": "3" * 40, "implementation_artifacts": {DRAFT_RUNNER_PATH: "4" * 64},
        "terminal_credit_exclusion_evidence_id": None, "private_evidence_permission": False,
    }

    def test_one_order_draft_maps_all_19_plan_fields_exactly(self) -> None:
        raw = draft_bytes()
        draft = draft_parse(raw)
        plan = draft.plan
        self.assertIs(type(draft), F.F03OperatorRuntimeInputsDraftV1)
        self.assertIs(type(plan), F.F03RunPlanV1)
        self.assertEqual([item.name for item in dataclasses.fields(F.F03RunPlanV1)], list(self.EXPECTED_PLAN))
        for name, value in self.EXPECTED_PLAN.items():
            actual = getattr(plan, name)
            if name == "implementation_artifacts":
                self.assertIs(type(actual), types.MappingProxyType)
                self.assertEqual(dict(actual), value)
            else:
                self.assertEqual(actual, value, name)
                self.assertIs(type(actual), type(value), name)
        self.assertEqual(plan.order1_limit_price.as_tuple().exponent, -4)
        self.assertEqual(plan, F.F03RunPlanV1(**self.EXPECTED_PLAN))  # original constructor unchanged
        self.assertEqual((plan.planned_order_count, plan.quantum), (1, A.QUANTUM_DIRECT))
        self.assertIs(draft.raw, raw)
        self.assertEqual((draft.raw_bytes, draft.raw_sha256), (len(raw), hashlib.sha256(raw).hexdigest()))
        self.assertEqual(draft.plan_binding_sha256, F.route_a_plan_binding_sha256(plan))
        self.assertEqual(_thaw(draft.fields), json.loads(raw))
        self.assertEqual(draft.terminal_credit_reference, F.F03_INPUTS_TERMINAL_CREDIT_PAIRED_NULL)

    def test_two_order_and_class_variants_derive_count_and_quantum_by_existing_properties(self) -> None:
        cases = (
            ("0.7000", "DIRECT", 2, A.QUANTUM_DIRECT),
            ("0.0001", "NON_DIRECT", 2, A.QUANTUM_NON_DIRECT),
            ("0.8000", "NON_DIRECT", 2, A.QUANTUM_NON_DIRECT),
        )
        for order2, account_class, count, quantum in cases:
            with self.subTest(order2=order2, account_class=account_class):
                doc = draft_with(("orders.order2_limit_price", order2), ("orders.planned_order_count", 2),
                                 ("fee.account_class", account_class))
                plan = draft_parse(draft_bytes(doc)).plan
                self.assertEqual(plan.order2_limit_price, D(order2))
                self.assertEqual(plan.order2_limit_price.as_tuple().exponent, -4)
                self.assertEqual((plan.planned_order_count, plan.quantum), (count, quantum))

    def test_unresolved_class_remains_a_draft_with_no_quantum_and_no_grant(self) -> None:
        draft = draft_parse(draft_bytes(draft_with(("fee.account_class", "UNRESOLVED"))))
        self.assertEqual(draft.plan.account_class, "UNRESOLVED")
        self.assertIsNone(draft.plan.quantum)
        self.assertEqual([item.name for item in dataclasses.fields(F.F03OperatorRuntimeInputsDraftV1)],
                         ["raw", "raw_sha256", "raw_bytes", "fields", "plan", "plan_binding_sha256",
                          "terminal_credit_reference"])
        for item in dataclasses.fields(draft):
            self.assertIsNot(type(getattr(draft, item.name)), bool)  # no executable/admitted boolean
            self.assertNotIsInstance(getattr(draft, item.name), F.F03ObservedIdentityV1)
        for banned in ("admit", "eligib", "executable", "proof", "observed", "accepted"):
            self.assertFalse([name for name in dir(draft) if banned in name.lower()], banned)

    def test_raw_length_and_sha_pins_are_compared_and_must_be_well_formed(self) -> None:
        raw = draft_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        cases = {
            "length_plus_one": dict(expected_bytes=len(raw) + 1), "length_minus_one": dict(expected_bytes=len(raw) - 1),
            "other_sha": dict(expected_sha="0" * 64), "uppercase_sha": dict(expected_sha=sha.upper()),
            "short_sha": dict(expected_sha=sha[:63]), "bool_length": dict(expected_bytes=True),
            "zero_length": dict(expected_bytes=0), "string_length": dict(expected_bytes=str(len(raw))),
            "over_cap_length": dict(expected_bytes=F.F03_INPUTS_RAW_MAX_BYTES + 1),
        }
        for label, kwargs in cases.items():
            with self.subTest(label):
                self.assert_refused(raw, PIN, **kwargs)
        mutated = _replace_once(raw, b'"FEE-SCHEDULE-2026-07-07"', b'"FEE-SCHEDULE-2026-07-08"')
        self.assert_refused(mutated, PIN, "length/sha256", expected_bytes=len(raw), expected_sha=sha)

    def test_participating_source_pins_compare_only_and_never_select(self) -> None:
        raw = draft_bytes()
        # Superset pins: the plan map is the INPUT map, never the expected map.
        draft = draft_parse(raw, sources=dict(DRAFT_SOURCES))
        self.assertEqual(dict(draft.plan.implementation_artifacts), {DRAFT_RUNNER_PATH: "4" * 64})
        refused = {
            "path_not_expected": {DRAFT_ANALYZER_PATH: "5" * 64},
            "hash_differs": {DRAFT_RUNNER_PATH: "6" * 64},
            "no_case_folding": {DRAFT_RUNNER_PATH.upper(): "4" * 64},
            "empty_pins": {}, "pins_not_mapping": [(DRAFT_RUNNER_PATH, "4" * 64)],
            "absolute_pin_path": {"/" + DRAFT_RUNNER_PATH: "4" * 64},
            "uppercase_pin_sha": {DRAFT_RUNNER_PATH: "A" * 64},
            "case_alias_pins": {DRAFT_RUNNER_PATH: "4" * 64, DRAFT_RUNNER_PATH.replace("kalshi", "Kalshi"): "4" * 64},
            "too_many_pins": {f"src/p{i}.py": "4" * 64 for i in range(257)},
        }
        for label, sources in refused.items():
            with self.subTest(label):
                self.assert_refused(raw, PIN, sources=sources)
        mapped = draft_with(("implementation.implementation_artifacts", {DRAFT_RUNNER_PATH.upper(): "4" * 64}))
        self.assert_doc_refused(mapped, PIN, "not an expected participating source")
        signature = inspect.signature(F.parse_f03_operator_runtime_inputs_draft_v1)
        self.assertEqual([(p.name, p.kind, p.default is inspect.Parameter.empty) for p in signature.parameters.values()],
                         [("raw", inspect.Parameter.POSITIONAL_OR_KEYWORD, True),
                          ("expected_raw_bytes", inspect.Parameter.KEYWORD_ONLY, True),
                          ("expected_raw_sha256", inspect.Parameter.KEYWORD_ONLY, True),
                          ("expected_participating_sources", inspect.Parameter.KEYWORD_ONLY, True)])
        with self.assertRaises(TypeError):
            F.parse_f03_operator_runtime_inputs_draft_v1(raw, expected_raw_bytes=len(raw),
                                                         expected_raw_sha256=hashlib.sha256(raw).hexdigest())


class F03InputsDraftClosedSchemaTests(_F03DraftAssertions):
    """SB-IN-001/002 + dispatch evidence 2: closed keys at every level,
    duplicates at every depth, integer/bool/null/shape domains, BOM/UTF-8 and
    byte-exact canonical reproduction, resource edges without truncation."""

    LEVELS = ("", "run", "market", "fee", "orders", "implementation", "source_and_scope", "evidence_refs",
              "evidence_refs.market", "evidence_refs.account_class")

    @staticmethod
    def _at(doc, path):
        target = doc
        for part in filter(None, path.split(".")):
            target = target[part]
        return target

    def test_unknown_and_missing_keys_refused_at_every_closed_level(self) -> None:
        for level in self.LEVELS:
            keys = list(self._at(draft_doc(), level))
            prefix = level + "." if level else ""
            with self.subTest(level=level, change="unknown"):
                self.assert_doc_refused(draft_with((prefix + "unexpected_extra", "x")), detail="keys")
            for key in keys:
                with self.subTest(level=level, change="missing", key=key):
                    self.assert_doc_refused(draft_with((prefix + key, _DELETE)), detail="keys")

    def test_duplicate_keys_refused_at_every_depth_even_when_last_value_is_valid(self) -> None:
        raw = draft_bytes()
        fragments = (
            b'"schema":"F03OperatorRuntimeInputsV1"', ('"run_id":"%s"' % DRAFT_RUN_ID).encode(),
            b'"ticker":"' + TICKER.encode() + b'"', b'"fee_type":"quadratic"', b'"planned_order_count":1',
            ('"%s":"%s"' % (DRAFT_RUNNER_PATH, "4" * 64)).encode(), b'"subaccount":1',
            b'"logical_id":"SYNTHETIC-MARKET-REF"', b'"terminal_credit":null',
        )
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                self.assert_refused(_replace_once(raw, fragment, fragment + b"," + fragment), INVALID, "duplicate key")
        smuggled = _replace_once(raw, b'"private_evidence_permission":false',
                                 b'"private_evidence_permission":true,"private_evidence_permission":false')
        self.assert_refused(smuggled, INVALID, "duplicate key")

    def test_integer_bool_null_and_shape_domains(self) -> None:
        bad = [
            *[("orders.planned_order_count", v) for v in (True, False, "1", None, 0, 2, 3)],
            *[("source_and_scope.subaccount", v) for v in (True, 0, 2, "1", None)],
            *[("source_and_scope.exchange_index", v) for v in (False, 1, "0", None)],
            *[("evidence_refs.market.bytes", v) for v in (True, 0, "2048", None, (1 << 30) + 1)],
            *[("run.private_evidence_permission", v) for v in (True, 0, None, "false")],
            *[("fee.fee_regime_change_pending", v) for v in (True, 0, None, "false")],
            ("orders.order2_limit_price", 0), ("fee.terminal_credit_exclusion_evidence_id", 0),
            ("evidence_refs.terminal_credit", "SYNTHETIC-TERMINAL-CREDIT-REF"),
        ]
        nonnull_slots = (
            "schema", "run", "market", "fee", "orders", "implementation", "source_and_scope", "evidence_refs",
            "run.run_id", "market.ticker", "market.event_ticker", "market.series_ticker",
            "market.market_metadata_evidence_id", "fee.account_class", "fee.account_class_evidence_id",
            "fee.fee_epoch_id", "fee.fee_type", "fee.taker_multiplier", "fee.maker_multiplier",
            "orders.order1_limit_price", "implementation.expected_commit", "implementation.expected_tree",
            "implementation.expected_parent", "implementation.implementation_artifacts",
            *("source_and_scope." + key for key in draft_doc()["source_and_scope"]),
            *("evidence_refs." + name for name in DRAFT_REF_NAMES if name != "terminal_credit"),
            "evidence_refs.market.logical_id", "evidence_refs.market.sha256",
        )
        bad += [(slot, None) for slot in nonnull_slots]
        bad += [(slot, []) for slot in ("run", "market", "fee", "orders", "implementation", "source_and_scope",
                                        "evidence_refs", "evidence_refs.market", "implementation.implementation_artifacts")]
        bad += [("market.ticker", [TICKER]), ("implementation.implementation_artifacts", {}),
                ("evidence_refs.market", "SYNTHETIC-MARKET-REF"), ("run", "run")]
        for path, value in bad:
            with self.subTest(path=path, value=value):
                self.assert_doc_refused(draft_with((path, value)))
        self.assert_doc_refused(draft_with(("orders.order2_limit_price", "0.7000")), INVALID, "planned_order_count")
        for root in ([draft_doc()], None, "F03OperatorRuntimeInputsV1", 1, True):
            with self.subTest(root=root):
                self.assert_refused(canonical_json_bytes(root), INVALID)
        for accepted in (1, 1 << 30):
            with self.subTest(ref_bytes=accepted):
                draft = draft_parse(draft_bytes(draft_with(("evidence_refs.market.bytes", accepted))))
                self.assertEqual(draft.fields["evidence_refs"]["market"]["bytes"], accepted)

    def test_floats_nonfinite_constants_and_noncanonical_or_overlong_integer_tokens(self) -> None:
        raw = draft_bytes()
        cases = {
            b'"subaccount":1': (b'"subaccount":1.0', b'"subaccount":1e0', b'"subaccount":1E0', b'"subaccount":-1',
                                b'"subaccount":NaN', b'"subaccount":Infinity', b'"subaccount":-Infinity'),
            b'"exchange_index":0': (b'"exchange_index":-0', b'"exchange_index":0.0', b'"exchange_index":-0.0'),
            b'"bytes":2048,"logical_id":"SYNTHETIC-MARKET-REF"': (
                b'"bytes":99999999999,"logical_id":"SYNTHETIC-MARKET-REF"',
                b'"bytes":' + b"9" * 5000 + b',"logical_id":"SYNTHETIC-MARKET-REF"'),
        }
        for old, replacements in cases.items():
            for new in replacements:
                with self.subTest(new=new[:40]):
                    self.assert_refused(_replace_once(raw, old, new), INVALID)
        overlong = _replace_once(raw, b'"bytes":2048,"logical_id":"SYNTHETIC-MARKET-REF"',
                                 b'"bytes":' + b"9" * 5000 + b',"logical_id":"SYNTHETIC-MARKET-REF"')
        self.assert_refused(overlong, INVALID, "integer token")  # refused before int conversion
        self.assert_refused(_replace_once(raw, b'"subaccount":1', b'"subaccount":1.0'), INVALID, "float")

    def test_bom_utf8_and_exact_canonical_byte_reproduction(self) -> None:
        doc = draft_doc()
        raw = draft_bytes(doc)
        self.assert_refused(b"\xef\xbb\xbf" + raw, INVALID, "byte-order mark")
        for bad in (b"\xff", b"\xc0\xaf", b"\xed\xa0\x80"):
            with self.subTest(utf8=bad):
                self.assert_refused(_replace_once(raw, b'"quadratic"', b'"quadratic' + bad + b'"'), INVALID, "utf-8")
        reordered = dict(reversed(list(doc.items())))
        noncanonical = {
            "trailing_newline": raw + b"\n", "leading_space": b" " + raw,
            "indented": json.dumps(doc, sort_keys=True, indent=1).encode(),
            "unsorted_keys": json.dumps(reordered, separators=(",", ":")).encode(),
            "spaced_separators": json.dumps(doc, sort_keys=True).encode(),
            "escaped_letter": _replace_once(raw, b'"quadratic"', b'"quadr\\u0061tic"'),
            "escaped_slash": _replace_once(raw, b'"https://external', b'"https:\\/\\/external'),
        }
        for label, variant in noncanonical.items():
            with self.subTest(label):
                self.assertNotEqual(variant, raw)
                self.assertEqual(json.loads(variant), doc)  # semantically equivalent, still refused
                self.assert_refused(variant, INVALID, "canonical_json_bytes")
        for key in ("api_secret", "private_key_pem", "session_token", "authority_db_path", "claim_root"):
            with self.subTest(prohibited=key):
                self.assert_refused(draft_text_bytes(draft_with(("fee." + key, "x"))), INVALID)
        pem = draft_with(("market.market_metadata_evidence_id", "-----BEGIN PRIVATE KEY-----"))
        self.assert_refused(draft_text_bytes(pem), INVALID, "canonical encoding")
        non_ascii = draft_with(("market.market_metadata_evidence_id", "SYNTHETIC-\u00e9"))
        self.assert_doc_refused(non_ascii, INVALID, "market_metadata_evidence_id")

    @staticmethod
    def _path_of(total: int) -> str:
        parts, remaining = [], total - len("src/") - len(".py")
        while remaining > 0:
            take = min(200, remaining)
            if 0 < remaining - take < 2:
                take -= 2
            parts.append("a" * take)
            remaining -= take + 1
        path = "src/" + "/".join(parts) + ".py"
        if len(path) != total:
            path = path[:-3] + "b" * (total - len(path)) + ".py"
        return path

    def test_resource_edges_are_refused_never_truncated_or_normalized(self) -> None:
        raw = draft_bytes()
        self.assert_refused(b" " * (F.F03_INPUTS_RAW_MAX_BYTES + 1), INVALID, "resource cap")
        self.assert_refused(b"[" * 200_000 + b"]" * 200_000, INVALID, "malformed JSON")  # nesting -> closed refusal
        with self.assertRaises(TypeError):
            F.F03OperatorInputsDraftError("SOME_OTHER_CLASSIFICATION", "x")  # closed classifications only
        with mock.patch.object(F, "F03_INPUTS_RAW_MAX_BYTES", len(raw)):
            self.assertEqual(draft_parse(raw).raw_bytes, len(raw))
        with mock.patch.object(F, "F03_INPUTS_RAW_MAX_BYTES", len(raw) - 1):
            self.assert_refused(raw, INVALID, "resource cap")
        long_path, too_long = self._path_of(4096), self._path_of(4097)
        self.assertEqual((len(long_path), len(too_long)), (4096, 4097))
        sources = {**DRAFT_SOURCES, long_path: "7" * 64}
        doc = draft_with(("implementation.implementation_artifacts", {DRAFT_RUNNER_PATH: "4" * 64, long_path: "7" * 64}))
        self.assertIn(long_path, draft_parse(draft_bytes(doc), sources=sources).plan.implementation_artifacts)
        doc = draft_with(("implementation.implementation_artifacts", {DRAFT_RUNNER_PATH: "4" * 64, too_long: "7" * 64}))
        self.assert_doc_refused(doc, INVALID, "implementation_artifacts path", sources=sources)
        for component, ok in (("c" * 255, True), ("c" * 256, False)):
            with self.subTest(component=len(component)):
                path = "src/" + component
                doc = draft_with(("implementation.implementation_artifacts", {path: "7" * 64}))
                if ok:
                    self.assertEqual(dict(draft_parse(draft_bytes(doc), sources={path: "7" * 64}).plan
                                          .implementation_artifacts), {path: "7" * 64})
                else:
                    self.assert_doc_refused(doc, INVALID, sources={DRAFT_RUNNER_PATH: "4" * 64})
        full = {f"src/p{i:03d}.py": "8" * 64 for i in range(256)}
        draft = draft_parse(draft_bytes(draft_with(("implementation.implementation_artifacts", full))), sources=full)
        self.assertEqual(dict(draft.plan.implementation_artifacts), full)
        over = {**full, "src/p256.py": "8" * 64}
        self.assert_doc_refused(draft_with(("implementation.implementation_artifacts", over)), INVALID,
                                "object entry count", sources=full)
        for path, size in (("fee.fee_epoch_id", 128), ("evidence_refs.market.logical_id", 128),
                           ("market.market_metadata_evidence_id", 128), ("market.ticker", 200)):
            with self.subTest(path=path, size=size):
                section, key = path.split(".")[0], path.split(".")[-1]
                fields = draft_parse(draft_bytes(draft_with((path, "Z" * size)))).fields
                target = fields[section]["market"] if section == "evidence_refs" else fields[section]
                self.assertEqual(target[key], "Z" * size)  # accepted exactly, not truncated
                self.assert_doc_refused(draft_with((path, "Z" * (size + 1))))

    # -- CORRECTION_01 / Marco B-01: canonicalization-stage recursion ---------

    @staticmethod
    def _trapped_surfaces():
        import builtins
        import subprocess

        def trap(*_args, **_kwargs):
            raise AssertionError("pure draft parser touched a prohibited surface")
        surfaces = [
            (builtins, "open"), (os, "open"), (os, "stat"), (os, "lstat"), (os, "scandir"), (os, "listdir"),
            (os, "getenv"), (os, "mkdir"), (Path, "read_bytes"), (Path, "exists"), (Path, "resolve"),
            (socket, "socket"), (socket, "create_connection"), (socket, "getaddrinfo"), (subprocess, "Popen"),
            (F, "_route_a_load_win32_directory_api"), (F, "_route_a_win32_flush_directory"),
            (runner, "consume_active_execution_authorization_set_v1"), (ledger_binding, "read_active_local_safety_state_v1"),
        ]
        stack = contextlib.ExitStack()
        for owner, name in surfaces:
            stack.enter_context(mock.patch.object(owner, name, trap))
        return stack

    def _parse_observing_boundary(self, raw):
        """Run the REAL parser with pass-through spies on the REAL decoder and
        canonicalizer; return (refusal-or-None, first failing boundary, returned)."""
        sha = hashlib.sha256(raw).hexdigest()  # pins prepared before any spy/trap
        stages: list = []
        real_loads, real_canonical = json.loads, F.canonical_json_bytes

        def loads(*args, **kwargs):
            try:
                return real_loads(*args, **kwargs)
            except RecursionError:
                stages.append("decode")
                raise

        def canonical(document):
            try:
                return real_canonical(document)
            except RecursionError:
                stages.append("canonicalize")
                raise
        returned: list = []
        refusal = None
        with self._trapped_surfaces(), mock.patch.object(F.json, "loads", loads), \
                mock.patch.object(F, "canonical_json_bytes", canonical):
            try:
                returned.append(F.parse_f03_operator_runtime_inputs_draft_v1(
                    raw, expected_raw_bytes=len(raw), expected_raw_sha256=sha,
                    expected_participating_sources=DRAFT_SOURCES))
            except F.F03OperatorInputsDraftError as exc:
                refusal = exc
        return refusal, (stages[0] if stages else "shape"), returned

    def test_c01_t01_modeled_canonicalization_recursion_is_the_closed_schema_refusal(self) -> None:
        """MODELED (deterministic injection, not target behavior): JSON decoding
        really succeeds; RecursionError is injected only at F's canonicalization
        call.  The real parser must refuse with the existing closed schema
        classification -- no draft, no raw RecursionError, no side effects."""
        raw = draft_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        self.assertIs(type(draft_parse(raw)), F.F03OperatorRuntimeInputsDraftV1)  # otherwise valid input
        decoded: list = []
        canonical_calls: list = []
        real_loads = json.loads

        def loads(*args, **kwargs):
            decoded.append(real_loads(*args, **kwargs))
            return decoded[-1]

        def canonical(document):
            canonical_calls.append(document)
            raise RecursionError("MODELED canonicalizer recursion (test injection)")
        returned: list = []
        with self._trapped_surfaces(), mock.patch.object(F.json, "loads", loads), \
                mock.patch.object(F, "canonical_json_bytes", canonical):
            with self.assertRaises(F.F03OperatorInputsDraftError) as ctx:
                returned.append(F.parse_f03_operator_runtime_inputs_draft_v1(
                    raw, expected_raw_bytes=len(raw), expected_raw_sha256=sha,
                    expected_participating_sources=DRAFT_SOURCES))
        self.assertEqual(returned, [])
        self.assertNotIsInstance(ctx.exception, RecursionError)
        self.assertEqual(ctx.exception.classification, INVALID)
        self.assertEqual(ctx.exception.detail, "canonical encoding nesting")
        self.assertTrue(ctx.exception.__suppress_context__)
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0], real_loads(raw))  # decoding really succeeded first
        self.assertEqual(len(canonical_calls), 1)
        self.assertIs(canonical_calls[0], decoded[0])  # injected at the decode's canonicalization call only
        # Narrow boundary: LedgerError keeps its vocabulary; unrelated errors are not swallowed.
        ledger_failure = LedgerError(FailureCode.LEDGER_CANONICAL_ENCODING_FAILURE)
        with mock.patch.object(F, "canonical_json_bytes", mock.Mock(side_effect=ledger_failure)):
            refusal = self.assert_refused(raw, INVALID)
        self.assertEqual(refusal.detail, "canonical encoding")
        with mock.patch.object(F, "canonical_json_bytes", mock.Mock(side_effect=ValueError("unrelated defect"))):
            with self.assertRaises(ValueError):
                draft_parse(raw)

    NESTING_DEPTHS = (2, 10, 100, 500, 999, 1000, 1500, 2000, 5000, 20000, 100000)

    def _nesting_family(self):
        base = draft_bytes()
        run_fragment = ('"run":{"private_evidence_permission":false,"run_id":"%s"}' % DRAFT_RUN_ID).encode()
        for depth in self.NESTING_DEPTHS:
            yield depth, "array_root", b"[" * depth + b"]" * depth
            yield depth, "object_root", b'{"a":' * depth + b"1" + b"}" * depth
            yield depth, "under_run_key", _replace_once(base, run_fragment, b'"run":' + b"[" * depth + b"]" * depth)

    def test_c01_t02_bounded_malformed_nesting_family_through_real_helpers(self) -> None:
        """ACTUAL decoder/canonicalizer execution over a predetermined finite
        family (all <= 1 MiB).  Every shape is the closed schema refusal
        whichever boundary fails first; reached boundaries are recorded, no
        universal depth threshold is asserted."""
        observed: dict = {}
        for depth, shape, raw in self._nesting_family():
            with self.subTest(depth=depth, shape=shape):
                self.assertLessEqual(len(raw), F.F03_INPUTS_RAW_MAX_BYTES)
                refusal, boundary, returned = self._parse_observing_boundary(raw)
                self.assertEqual(returned, [])
                self.assertIsNotNone(refusal)
                self.assertEqual(refusal.classification, INVALID, refusal.detail)
                self.assertIn(boundary, ("decode", "canonicalize", "shape"))
                observed[f"{depth}/{shape}"] = boundary
        print("\nC01-T02 observed first-failing boundaries (python %s, recursionlimit %d): %s" % (
            sys.version.split()[0], sys.getrecursionlimit(), observed))

    def test_c01_t02_actual_canonicalizer_recursion_fixture_environment_labelled(self) -> None:
        """ACTUAL helper behavior, environment-labelled: fixed 2,000-deep
        fixtures decode with the real JSON decoder and then overflow the real
        protected canonicalizer on the recorded authoring runtime (CPython
        3.12.14, recursion limit 1000, Windows).  If another runtime does not
        reach that boundary the case is skipped, never treated as a depth
        theorem; C01-T01 remains the deterministic model."""
        environment = "python %s, recursionlimit %d" % (sys.version.split()[0], sys.getrecursionlimit())
        for shape, raw in (("array_root", b"[" * 2000 + b"]" * 2000),
                           ("object_root", b'{"a":' * 2000 + b"1" + b"}" * 2000)):
            with self.subTest(shape=shape):
                refusal, boundary, returned = self._parse_observing_boundary(raw)
                if boundary != "canonicalize":
                    self.skipTest(f"canonicalization-stage recursion not reached ({boundary}) on {environment}")
                self.assertEqual(returned, [])
                self.assertEqual((refusal.classification, refusal.detail), (INVALID, "canonical encoding nesting"))


class F03InputsDraftLexicalBoundaryTests(_F03DraftAssertions):
    """SB-IN-002 + dispatch evidence 3: UUID/Git/SHA/path/identifier and
    four-decimal price boundaries; canonical finite maker/taker text with
    adequate Decimal precision and no binary floats."""

    def test_uuid_git_sha_identifier_and_ticker_grammars(self) -> None:
        bad = [
            *[("run.run_id", v) for v in (DRAFT_RUN_ID.upper(), DRAFT_RUN_ID.replace("-41d2-", "-11d2-"),
                                           DRAFT_RUN_ID.replace("-883f-", "-c83f-"), "{" + DRAFT_RUN_ID + "}",
                                           DRAFT_RUN_ID.replace("-", ""), DRAFT_RUN_ID + " ", "")],
            *[("implementation." + k, v) for k in ("expected_commit", "expected_tree", "expected_parent")
              for v in ("A" * 40, "1" * 39, "1" * 41, "g" * 40)],
            *[("source_and_scope.domain_binding_sha256", v) for v in ("D" * 64, "d" * 63, "d" * 65, "z" * 64)],
            *[("evidence_refs.risk.sha256", v) for v in ("C" * 64, "c" * 63)],
            *[("fee.fee_epoch_id", v) for v in ("", "-LEAD", "A B", "A/B", "A\u00c4", "A\n")],
            *[("market." + k, v) for k in ("ticker", "event_ticker", "series_ticker")
              for v in ("", "A B", "A/B", "T" * 201, "A\u00c4")],
        ]
        for path, value in bad:
            with self.subTest(path=path, value=value):
                self.assert_doc_refused(draft_with((path, value)))
        for path, value in (("fee.fee_epoch_id", "a:b.c_d-e"), ("market.ticker", "A.b_c~d-1")):
            with self.subTest(accepted=value):
                self.assertEqual(draft_parse(draft_bytes(draft_with((path, value)))).fields[path.split(".")[0]]
                                 [path.split(".")[1]], value)

    def test_repository_path_grammar_is_strict_and_never_normalized(self) -> None:
        for path in ("/src/x.py", "C:/src/x.py", "src\\x.py", "src//x.py", "src/./x.py", "src/../x.py", "src/x.py/",
                     "src/x.", "src/x..", "src/x y.py", "", ".", "..", "\\\\?\\C:\\x.py", "//server/share/x.py",
                     "src/x.py:stream", "src/\u00e9.py"):
            with self.subTest(path=path):
                doc = draft_with(("implementation.implementation_artifacts", {path: "4" * 64}))
                self.assert_refused(draft_text_bytes(doc), INVALID)

    def test_four_decimal_limit_price_grammar_and_bounds(self) -> None:
        for price in ("0.0001", "0.5000", "0.8000"):
            with self.subTest(accepted=price):
                plan = draft_parse(draft_bytes(draft_with(("orders.order1_limit_price", price)))).plan
                self.assertEqual(str(plan.order1_limit_price), price)
                self.assertEqual(plan.order1_limit_price.as_tuple().exponent, -4)
        bad = ("0.5", "0.500", "0.50000", "0.0000", "0.8001", "1.0000", "00.5000", ".5000", "+0.5000", "-0.5000",
               "5E-1", "5.000E-1", "0.5000 ", " 0.5000", "NaN", "Infinity", "0,5000", "")
        for slot in ("orders.order1_limit_price", "orders.order2_limit_price"):
            for price in bad:
                with self.subTest(slot=slot, price=price):
                    changes = [(slot, price)]
                    if slot.endswith("order2_limit_price"):
                        changes.append(("orders.planned_order_count", 2))
                    self.assert_doc_refused(draft_with(*changes))
        raw = _replace_once(draft_bytes(), b'"order1_limit_price":"0.5000"', b'"order1_limit_price":0.5000')
        self.assert_refused(raw, INVALID, "float")

    def test_canonical_maker_and_exact_taker_decimal_text(self) -> None:
        tiny = "0." + "0" * 70 + "1"  # 73 significant characters: needs > default 28-digit context
        for text in ("1", "0.5", "0.0001", "0.25", "0.9999999999999999999999999999999999999999999999999999", tiny):
            with self.subTest(accepted=text):
                plan = draft_parse(draft_bytes(draft_with(("fee.maker_multiplier", text)))).plan
                self.assertIs(type(plan.maker_multiplier), D)
                self.assertEqual(plan.maker_multiplier, D(text))
                self.assertEqual(A.canonical_decimal_text(plan.maker_multiplier), text)
        for value in ("1.0", "0.50", "0.10", "0", "-0", "0.0", "1.5", "1E0", "1e-1", "+1", ".5", "01", "NaN", "sNaN",
                      "Infinity", " 1", "1 ", "", 1, True, None):
            with self.subTest(maker=value):
                self.assert_doc_refused(draft_with(("fee.maker_multiplier", value)))
        for value in ("1.0", "1.00", "01", "+1", "0.5", "1E0", 1, True, None, ""):
            with self.subTest(taker=value):
                self.assert_doc_refused(draft_with(("fee.taker_multiplier", value)))
        for path, value in (("fee.fee_type", "QUADRATIC"), ("fee.fee_type", "linear"), ("fee.account_class", "direct"),
                            ("fee.account_class", "UNKNOWN"), ("schema", "F03OperatorRuntimeInputsV2"),
                            ("source_and_scope.environment", "KALSHI_PRODUCTION"),
                            ("source_and_scope.origin", "https://api.elections.kalshi.com"),
                            ("source_and_scope.route", "ROUTE_B"), ("source_and_scope.canonical_strategy_G", "G1"),
                            ("source_and_scope.authority_namespace_id", "OTHER_NS")):
            with self.subTest(path=path, value=value):
                self.assert_doc_refused(draft_with((path, value)))


class F03InputsDraftDigestTests(_F03DraftAssertions):
    """SB-IN-003 + dispatch evidence 4: full-field mapping and full/raw/subset
    digest distinction; the installed ``_plan_sha256`` subset is unchanged."""

    @staticmethod
    def _subset(plan) -> str:
        return F.F03FeeExperimentRunnerV1._plan_sha256(types.SimpleNamespace(plan=plan))

    @staticmethod
    def _documented_subset(plan) -> str:
        price = lambda p: None if p is None else A.canonical_decimal_text(p)  # noqa: E731
        return hashlib.sha256(canonical_json_bytes({
            "schema": "F03_RUN_PLAN_V1", "run_id": plan.run_id, "ticker": plan.ticker,
            "order1_limit_price": price(plan.order1_limit_price), "order2_limit_price": price(plan.order2_limit_price),
            "account_class": plan.account_class, "fee_epoch_id": plan.fee_epoch_id})).hexdigest()

    def test_subset_collision_keeps_full_binding_and_raw_digest_distinct(self) -> None:
        base = draft_parse(draft_bytes())
        self.assertEqual(self._subset(base.plan), self._documented_subset(base.plan))  # no subset semantic change
        for path, value in (("market.event_ticker", "KXF03TEST-26AUG18"), ("fee.maker_multiplier", "0.5"),
                            ("market.series_ticker", "KXF03OTHER"), ("fee.account_class_evidence_id", "OTHER-ID")):
            with self.subTest(path=path):
                changes = [(path, value)]
                if path == "fee.account_class_evidence_id":
                    changes.append(("evidence_refs.account_class.logical_id", value))
                variant = draft_parse(draft_bytes(draft_with(*changes)))
                self.assertEqual(self._subset(variant.plan), self._subset(base.plan))  # old subset collides
                self.assertNotEqual(variant.plan_binding_sha256, base.plan_binding_sha256)  # full binding differs
                self.assertNotEqual(variant.raw_sha256, base.raw_sha256)
                self.assertEqual(variant.plan_binding_sha256, F.route_a_plan_binding_sha256(variant.plan))
        changed = draft_parse(draft_bytes(draft_with(("market.ticker", "KXF03TEST-26AUG17-T51"))))
        self.assertNotEqual(self._subset(changed.plan), self._subset(base.plan))
        self.assertEqual(len({base.raw_sha256, base.plan_binding_sha256, self._subset(base.plan)}), 3)
        as_dict = F.F03RunPlanV1(**{item.name: getattr(base.plan, item.name) for item in dataclasses.fields(base.plan)}
                                 | {"implementation_artifacts": dict(base.plan.implementation_artifacts)})
        self.assertEqual(F.route_a_plan_binding_sha256(as_dict), base.plan_binding_sha256)


class F03InputsDraftTerminalCreditTests(_F03DraftAssertions):
    """SB-IN-001/002/005 T-NULL / T-PROOF structural portion + dispatch
    evidence 5.  Paired null parses with no new gate; a matching nonnull pair
    is only an UNVERIFIED draft reference; half-null, mismatched or malformed
    purported-positive references are refused.  Analyzer conclusion rules
    (``SINGLE_FILL_IDENTIFIED`` / QF03) are untouched and not asserted here."""

    def _nonnull(self, *extra):
        return draft_with(("fee.terminal_credit_exclusion_evidence_id", DRAFT_TERMINAL_ID),
                          ("evidence_refs.terminal_credit", draft_ref("terminal_credit")), *extra)

    def test_paired_null_parses_and_maps_without_a_terminal_gate(self) -> None:
        draft = draft_parse(draft_bytes())
        self.assertIsNone(draft.plan.terminal_credit_exclusion_evidence_id)
        self.assertIsNone(draft.fields["evidence_refs"]["terminal_credit"])
        self.assertEqual(draft.terminal_credit_reference, F.F03_INPUTS_TERMINAL_CREDIT_PAIRED_NULL)
        self.assertEqual(draft.plan.planned_order_count, 1)  # the complete plan is still derived

    def test_matching_nonnull_pair_is_only_an_unverified_draft_reference(self) -> None:
        draft = draft_parse(draft_bytes(self._nonnull()))
        self.assertEqual(draft.plan.terminal_credit_exclusion_evidence_id, DRAFT_TERMINAL_ID)
        self.assertEqual(draft.terminal_credit_reference, F.F03_INPUTS_TERMINAL_CREDIT_UNVERIFIED_REF)
        self.assertEqual(_thaw(draft.fields["evidence_refs"]["terminal_credit"]), draft_ref("terminal_credit"))

    def test_half_null_mismatched_or_malformed_purported_positive_refs_are_refused(self) -> None:
        cases = {
            "id_without_ref": draft_with(("fee.terminal_credit_exclusion_evidence_id", DRAFT_TERMINAL_ID)),
            "ref_without_id": draft_with(("evidence_refs.terminal_credit", draft_ref("terminal_credit"))),
            "id_differs": self._nonnull(("fee.terminal_credit_exclusion_evidence_id", "SYNTHETIC-OTHER-REF")),
            "ref_missing_sha": self._nonnull(("evidence_refs.terminal_credit.sha256", _DELETE)),
            "ref_extra_key": self._nonnull(("evidence_refs.terminal_credit.verified", True)),
            "ref_zero_bytes": self._nonnull(("evidence_refs.terminal_credit.bytes", 0)),
            "ref_bad_sha": self._nonnull(("evidence_refs.terminal_credit.sha256", "C" * 64)),
            "ref_bad_logical_id": self._nonnull(("evidence_refs.terminal_credit.logical_id", "bad id"),
                                                ("fee.terminal_credit_exclusion_evidence_id", "bad id")),
            "ref_as_string": self._nonnull(("evidence_refs.terminal_credit", DRAFT_TERMINAL_ID)),
            "ref_as_true": self._nonnull(("evidence_refs.terminal_credit", True)),
            "id_empty": self._nonnull(("fee.terminal_credit_exclusion_evidence_id", "")),
        }
        details = {"id_without_ref": "both null or both nonnull", "ref_without_id": "both null or both nonnull",
                   "id_differs": "differs from evidence_refs.terminal_credit"}
        for label, doc in cases.items():
            with self.subTest(label):
                self.assert_doc_refused(doc, INVALID, details.get(label))
        raw = draft_bytes(self._nonnull())
        self.assert_refused(raw, PIN, expected_sha=hashlib.sha256(draft_bytes()).hexdigest())

    def test_account_class_evidence_id_must_equal_its_cited_ref(self) -> None:
        self.assert_doc_refused(draft_with(("fee.account_class_evidence_id", "SYNTHETIC-OTHER-REF")), INVALID,
                                "evidence_refs.account_class")


def _f03_draft_symbols():
    names = [name for name in vars(F) if name.startswith("_f03_inputs_")]
    return [getattr(F, name) for name in names] + [F.parse_f03_operator_runtime_inputs_draft_v1,
                                                   F.F03OperatorRuntimeInputsDraftV1, F.F03OperatorInputsDraftError]


class F03InputsDraftImmutabilityAndPurityTests(_F03DraftAssertions):
    """SB-IN-004 pure portion + dispatch evidence 6: recursive immutability,
    defensive copies, one raw snapshot; zero filesystem/native/Git/evidence/
    credential/transport activity; absent from every runtime entry path."""

    def test_draft_plan_and_fields_are_recursively_immutable(self) -> None:
        draft = draft_parse(draft_bytes())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            draft.plan = None
        with self.assertRaises(dataclasses.FrozenInstanceError):
            draft.plan.run_id = str(uuid.uuid4())
        with self.assertRaises(TypeError):
            draft.plan.implementation_artifacts[DRAFT_RUNNER_PATH] = "0" * 64
        with self.assertRaises(TypeError):
            draft.fields["run"]["run_id"] = str(uuid.uuid4())

        def walk(value):
            if isinstance(value, (dict, list)):
                self.fail("mutable container in draft fields")
            if isinstance(value, types.MappingProxyType):
                for child in value.values():
                    walk(child)
        walk(draft.fields)
        self.assertIs(type(draft.raw), bytes)
        self.assertEqual(hashlib.sha256(draft.raw).hexdigest(), draft.raw_sha256)
        for raw in (bytearray(draft.raw), memoryview(draft.raw), draft.raw.decode()):
            with self.subTest(raw_type=type(raw).__name__):
                with self.assertRaises(F.F03OperatorInputsDraftError) as ctx:
                    F.parse_f03_operator_runtime_inputs_draft_v1(
                        raw, expected_raw_bytes=draft.raw_bytes, expected_raw_sha256=draft.raw_sha256,
                        expected_participating_sources=DRAFT_SOURCES)
                self.assertEqual(ctx.exception.classification, INVALID)

    def test_mutating_decoded_and_pin_maps_cannot_alter_the_result(self) -> None:
        raw = draft_bytes()
        decoded: list = []
        real_loads = json.loads

        def capture(*args, **kwargs):
            decoded.append(real_loads(*args, **kwargs))
            return decoded[-1]
        sources = dict(DRAFT_SOURCES)
        with mock.patch.object(F.json, "loads", capture):
            draft = draft_parse(raw, sources=sources)
        self.assertEqual(len(decoded), 1)
        binding = draft.plan_binding_sha256
        decoded[0]["run"]["run_id"] = str(uuid.uuid4())
        decoded[0]["fee"]["maker_multiplier"] = "0.5"
        decoded[0]["implementation"]["implementation_artifacts"]["src/extra.py"] = "9" * 64
        sources[DRAFT_RUNNER_PATH] = "0" * 64
        sources["src/extra.py"] = "9" * 64
        self.assertEqual(_thaw(draft.fields), real_loads(raw))
        self.assertEqual(dict(draft.plan.implementation_artifacts), {DRAFT_RUNNER_PATH: "4" * 64})
        self.assertEqual((draft.plan.run_id, draft.plan.maker_multiplier), (DRAFT_RUN_ID, D("1")))
        self.assertEqual(F.route_a_plan_binding_sha256(draft.plan), binding)

        class FlippingPins(dict):  # a caller map whose later reads would differ
            reads = 0

            def items(self):
                FlippingPins.reads += 1
                return super().items() if FlippingPins.reads == 1 else {DRAFT_RUNNER_PATH: "0" * 64}.items()
        flipped = draft_parse(raw, sources=FlippingPins(DRAFT_SOURCES))
        self.assertEqual(FlippingPins.reads, 1)  # copied exactly once
        self.assertEqual(flipped.plan_binding_sha256, binding)

    def test_parser_performs_no_filesystem_native_git_env_or_transport_activity(self) -> None:
        import builtins
        import subprocess

        def trap(*_args, **_kwargs):
            raise AssertionError("pure draft parser touched a prohibited surface")
        surfaces = [
            (builtins, "open"), (os, "open"), (os, "stat"), (os, "lstat"), (os, "scandir"), (os, "listdir"),
            (os, "getenv"), (os, "mkdir"), (Path, "read_bytes"), (Path, "exists"), (Path, "resolve"),
            (socket, "socket"), (socket, "create_connection"), (socket, "getaddrinfo"), (subprocess, "Popen"),
            (F, "_route_a_load_win32_directory_api"), (F, "_route_a_win32_flush_directory"),
            (runner, "consume_active_execution_authorization_set_v1"), (ledger_binding, "read_active_local_safety_state_v1"),
        ]
        raw = draft_bytes(F03InputsDraftTerminalCreditTests._nonnull(None))
        with contextlib.ExitStack() as stack:
            for owner, name in surfaces:
                stack.enter_context(mock.patch.object(owner, name, trap))
            draft = draft_parse(raw)
        self.assertEqual(draft.terminal_credit_reference, F.F03_INPUTS_TERMINAL_CREDIT_UNVERIFIED_REF)
        for symbol in _f03_draft_symbols():
            code = _code_only(inspect.getsource(symbol))
            for banned in ("open(", "os.", "Path(", "pathlib", "subprocess", "socket", "ctypes", "environ", "getenv",
                           "read_bytes", "float(", "eval(", "exec(", "__import__", "callable(", "_runner.run",
                           "consume_", "F03ObservedIdentityV1(", "_route_a_win32", "sqlite"):
                self.assertNotIn(banned, code, (symbol.__name__, banned))

    def test_parser_is_absent_from_every_installed_runtime_entry_path(self) -> None:
        f_code = _code_only(inspect.getsource(F))
        self.assertEqual(f_code.count("parse_f03_operator_runtime_inputs_draft_v1("), 1)  # its definition only
        self.assertEqual(F.__all__, [])  # no new export
        r_code = _code_only(inspect.getsource(runner))
        for name in ("parse_f03_operator_runtime_inputs_draft_v1", "F03OperatorRuntimeInputsDraftV1",
                     "F03OperatorInputsDraftError", "_f03_inputs_"):
            self.assertNotIn(name, r_code, name)
            self.assertNotIn(name, _code_only(inspect.getsource(F.F03FeeExperimentRunnerV1)), name)
            for entry in (F.F03RunPlanV1, F.verify_source_binding, F.route_a_plan_binding_sha256,
                          F.parse_route_a_timing_config_v1, F.admit_route_a_timing_profile_v1):
                self.assertNotIn(name, _code_only(inspect.getsource(entry)), (entry.__name__, name))


class _F03InputsDraftHoldMixin(_StageAHarnessMixin):
    """Dispatch evidence 7 / STAGE-A-HOLD preserved: a plan derived by the
    draft decoder from otherwise structurally valid SYNTHETIC inputs is still
    stopped by the UNPATCHED unconditional pre-row-9 N1 hold -- zero
    consumption/append, receipt, credential bridge, signed GET, CREATE or
    CANCEL.  Synthetic positive controls elsewhere are not real admission
    proof; nothing here enables a live bypass."""

    RA_FIXTURE_BYPASS_N1_HISTORY_HOLD = False
    RA_FIXTURE_BYPASS_ADMISSION_LINK_STOP = False

    def _draft(self, *, terminal_ref: bool):
        doc = draft_with(("run.run_id", str(uuid.uuid4())), ("implementation.expected_commit", self.COMMIT),
                         ("implementation.expected_tree", self.TREE), ("implementation.expected_parent", self.PARENT))
        if terminal_ref:
            doc = draft_with(("fee.terminal_credit_exclusion_evidence_id", DRAFT_TERMINAL_ID),
                             ("evidence_refs.terminal_credit", draft_ref("terminal_credit")), doc=doc)
        baseline = self._event_types()
        draft = draft_parse(draft_bytes(doc))
        self.assertEqual(self._event_types(), baseline)  # decoding has no durable effect
        self.assertEqual(draft.plan, self._plan(
            run_id=draft.plan.run_id, account_class_evidence_id="SYNTHETIC-ACCOUNT-CLASS-REF",
            terminal_credit_exclusion_evidence_id=DRAFT_TERMINAL_ID if terminal_ref else None))
        return draft

    def _held_with(self, plan, **builder_kwargs):
        baseline = self._event_types()
        runs_before = [p.name for p in self.runs_root.iterdir()]
        admitted = []
        real_admit = F.admit_route_a_timing_profile_v1

        def admit(*args, **kw):
            admitted.append(real_admit(*args, **kw))
            return admitted[-1]
        venue = self._venue()
        with self._consume_spy(), mock.patch.object(F, "admit_route_a_timing_profile_v1", admit):
            with self.assertRaises(RunnerError) as ctx:
                self._ra_run(venue, plan, builder=self._counting_builder(venue, **builder_kwargs),
                             credential_bridge=self._scope())
        self.assertEqual(len(admitted), 1)  # timing admitted: the input is otherwise passing
        self._assert_n1_held(ctx, venue, plan, baseline, runs_before)


class F03InputsDraftStageAHoldTests(_F03InputsDraftHoldMixin, RouteAHarnessTestCase):
    def test_installed_entry_halts_before_consumption_with_valid_draft_plans(self) -> None:
        for native in (False, True, None):
            for terminal_ref in (False, True):
                with self.subTest(native_windows=native, terminal_ref=terminal_ref):
                    self.RA_NATIVE_WINDOWS = native
                    self._held_with(self._draft(terminal_ref=terminal_ref).plan)


class F03InputsDraftStageABootHoldTests(_F03InputsDraftHoldMixin, RouteAHarnessTestCase):
    ENTRY = RA_BOOT

    def test_boot_hold_entry_halts_before_consumption_with_a_valid_draft_plan(self) -> None:
        for native in (False, True):
            with self.subTest(native_windows=native):
                self.RA_NATIVE_WINDOWS = native
                self._held_with(self._draft(terminal_ref=False).plan, phases=2, implied=20)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
