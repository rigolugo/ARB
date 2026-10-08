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
import dataclasses
import hashlib
import inspect
import json
import socket
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
    "src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py": "eb455d9467448fcb2435abd3465bdf08e68b10fd",
    "src/arb/venues/kalshi/account_subaccount_probe.py": "1dc0e82c61b7dbd6b5a5e2ca2e9ed37ed3f75fe0",
    "src/arb/venues/kalshi/models.py": "628dee54853c09071f93556d404b45bf4e87755a",
    "src/arb/venues/kalshi/validation.py": "8f84f06f74604356daaa62662c7d74220ffef312",
    "src/arb/venues/kalshi/serialization.py": "df25df110775e2fc4542c63b8ce2c4e42eca5e34",
    "tests/test_kalshi_minimal_market_maker_experiment_runner.py": "a92508c22029285e013a02f98c24779f6c4a895e",
    "tests/test_kalshi_shadow_experiment.py": "93d0e0fce8e8fe7d1de3b4f62e562c1b70cfb7a1",
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
