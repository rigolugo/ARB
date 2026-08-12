"""Offline acceptance tests for post-halt exact write-result reconciliation.

No socket, DNS, HTTP client, environment-secret read, account access, venue
request, or write operation is performed.  Every transport interaction is an
in-memory fake and every credential-related value is non-secret metadata.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import re
import unittest
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from arb.venues.kalshi import write_result_reconciliation as wr


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _response(value: object, *, status: int = 200, media_type: str = "application/json",
              retry_count: int = 0, redirect_count: int = 0) -> wr.RawHttpResponse:
    return wr.RawHttpResponse(
        status=status,
        media_type=media_type,
        body_bytes=_json_bytes(value),
        retry_count=retry_count,
        redirect_count=redirect_count,
    )


def _raw_response(raw: bytes, **kwargs: object) -> wr.RawHttpResponse:
    return wr.RawHttpResponse(
        status=int(kwargs.get("status", 200)),
        media_type=str(kwargs.get("media_type", "application/json")),
        body_bytes=raw,
        retry_count=int(kwargs.get("retry_count", 0)),
        redirect_count=int(kwargs.get("redirect_count", 0)),
    )


def _cutoff() -> dict:
    return {
        "market_settled_ts": "2026-08-11T10:00:00Z",
        "trades_created_ts": "2026-08-11T10:00:00Z",
        "orders_updated_ts": "2026-08-11T10:00:00Z",
    }


def _order(
    *,
    order_id: str = "order-target-001",
    client_order_id: str = wr.CLIENT_ORDER_ID,
    ticker: str = wr.TICKER,
    subaccount_number: object = 0,
    outcome_side: str = "yes",
    book_side: str = "bid",
    yes_price_dollars: object = "0.0100",
    no_price_dollars: object = "0.9900",
    cancel_order_on_pause: object = True,
    status: str = "resting",
    initial_count_fp: object = "1.00",
    fill_count_fp: object = "0.00",
    remaining_count_fp: object = "1.00",
    expose_intent: bool = False,
    stp: Optional[str] = None,
) -> dict:
    value = {
        "order_id": order_id,
        "client_order_id": client_order_id,
        "ticker": ticker,
        "subaccount_number": subaccount_number,
        "outcome_side": outcome_side,
        "book_side": book_side,
        "yes_price_dollars": yes_price_dollars,
        "no_price_dollars": no_price_dollars,
        "cancel_order_on_pause": cancel_order_on_pause,
        "status": status,
        "initial_count_fp": initial_count_fp,
        "fill_count_fp": fill_count_fp,
        "remaining_count_fp": remaining_count_fp,
    }
    if stp is not None:
        value["self_trade_prevention_type"] = stp
    if expose_intent:
        value.update({
            "self_trade_prevention_type": wr.SELF_TRADE_PREVENTION_TYPE,
            "post_only": True,
            "time_in_force": wr.TIME_IN_FORCE,
            "reduce_only": False,
            "exchange_index": 0,
        })
    return value


def _fill(
    *,
    fill_id: str = "fill-001",
    trade_id: str = "trade-001",
    order_id: str = "order-target-001",
    ticker: str = wr.TICKER,
    subaccount_number: object = 0,
    outcome_side: str = "yes",
    book_side: str = "bid",
    count_fp: object = "1.00",
    yes_price_dollars: object = "0.0100",
    no_price_dollars: object = "0.9900",
    is_taker: object = False,
    fee_cost: object = "0.000000",
    market_ticker: Optional[str] = None,
) -> dict:
    value = {
        "fill_id": fill_id,
        "trade_id": trade_id,
        "order_id": order_id,
        "ticker": ticker,
        "subaccount_number": subaccount_number,
        "outcome_side": outcome_side,
        "book_side": book_side,
        "count_fp": count_fp,
        "yes_price_dollars": yes_price_dollars,
        "no_price_dollars": no_price_dollars,
        "is_taker": is_taker,
        "fee_cost": fee_cost,
        "created_time": "2026-08-11T10:00:00Z",
        "ts": "2026-08-11T10:00:00Z",
    }
    if market_ticker is not None:
        value["market_ticker"] = market_ticker
    return value


def _artifact(path: str) -> wr.ArtifactIdentity:
    return wr.ArtifactIdentity(path=path, bytes=1, sha256="0" * 64, git_blob="0" * 40)


def _capability(**changes: object) -> wr.ReconciliationCapabilityEnvelope:
    values = dict(
        environment=wr.ENVIRONMENT,
        rest_origin=wr.DEMO_REST_ORIGIN,
        credential_reference_names=("KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"),
        granted_capabilities=wr.REQUIRED_RECONCILIATION_CAPABILITIES,
        network_access=wr.CapabilityState.PERMITTED,
        demo_public_reads=wr.CapabilityState.PERMITTED,
        demo_authenticated_reads=wr.CapabilityState.PERMITTED,
        credential_use=wr.CapabilityState.PERMITTED,
        demo_writes=wr.CapabilityState.PROHIBITED,
        production_public_reads=wr.CapabilityState.PROHIBITED,
        production_authenticated_reads=wr.CapabilityState.PROHIBITED,
        production_writes=wr.CapabilityState.PROHIBITED,
        account_funding=wr.CapabilityState.PROHIBITED,
        websocket=wr.CapabilityState.PROHIBITED,
    )
    values.update(changes)
    return wr.ReconciliationCapabilityEnvelope(**values)


def _input(**changes: object) -> wr.ReconciliationInput:
    provenance = wr.ReconciliationProvenance(
        implementation=_artifact("src/arb/venues/kalshi/write_result_reconciliation.py"),
        tests=_artifact("tests/test_kalshi_write_result_reconciliation.py"),
    )
    values = dict(
        capability_envelope=_capability(),
        source_binding_manifest_bytes=wr.SOURCE_BINDING_MANIFEST_BYTES,
        provenance=provenance,
    )
    values.update(changes)
    return wr.ReconciliationInput(**values)


class FakeTransport:
    def __init__(self, handler: Optional[Callable[[wr.PreparedGetRequest, int], wr.RawHttpResponse]] = None):
        self.requests: List[wr.PreparedGetRequest] = []
        self.counts: Dict[wr.ReconciliationOperation, int] = defaultdict(int)
        self.handler = handler or self._default
        self.live_orders = [_order()]
        self.historical_orders: List[dict] = []
        self.exact_order = _order()
        self.live_fills: List[dict] = []
        self.historical_fills: List[dict] = []

    def send(self, request: wr.PreparedGetRequest) -> wr.RawHttpResponse:
        self.requests.append(request)
        self.counts[request.operation] += 1
        return self.handler(request, self.counts[request.operation])

    def _default(self, request: wr.PreparedGetRequest, ordinal: int) -> wr.RawHttpResponse:
        op = request.operation
        if op is wr.ReconciliationOperation.HISTORICAL_CUTOFF:
            return _response(_cutoff())
        if op is wr.ReconciliationOperation.LIVE_ORDERS:
            return _response({"orders": self.live_orders, "cursor": ""})
        if op is wr.ReconciliationOperation.HISTORICAL_ORDERS:
            return _response({"orders": self.historical_orders, "cursor": ""})
        if op is wr.ReconciliationOperation.EXACT_ORDER:
            return _response({"order": self.exact_order})
        if op is wr.ReconciliationOperation.LIVE_FILLS:
            return _response({"fills": self.live_fills, "cursor": ""})
        if op is wr.ReconciliationOperation.HISTORICAL_FILLS:
            return _response({"fills": self.historical_fills, "cursor": ""})
        raise AssertionError(op)


class FakeClock:
    def __init__(self, values: Optional[List[float]] = None, *, start: float = 100.0, step: float = 0.0):
        self.values = list(values or [])
        self.current = start
        self.step = step
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        if self.values:
            self.current = self.values.pop(0)
            return self.current
        value = self.current
        self.current += self.step
        return value


class ThresholdClock:
    """Return 0 until a selected monotonic boundary, then 181 seconds."""
    def __init__(self, threshold: int):
        self.threshold = threshold
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return 181.0 if self.calls >= self.threshold else 0.0


class ReconciliationTestCase(unittest.TestCase):
    def assertHalt(self, result: wr.ReconciliationResult, code: wr.HaltCode) -> None:
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_READ_FAILURE)
        self.assertEqual(result.halt_code, code)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.writer_proof_release_eligible)

    def assertIdentityViolation(self, result: wr.ReconciliationResult, code: wr.HaltCode) -> None:
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION)
        self.assertEqual(result.halt_code, code)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.writer_proof_release_eligible)
        self.assertIsNone(result.bound_order_id)

    def active_result(self) -> Tuple[wr.ReconciliationResult, FakeTransport]:
        t = FakeTransport()
        result = wr.execute_post_halt_reconciliation(_input(), t)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        return result, t

    def executed_result(self, *, fills: Optional[List[dict]] = None) -> Tuple[wr.ReconciliationResult, FakeTransport]:
        t = FakeTransport()
        t.live_orders = [_order(status="executed", fill_count_fp="1.00", remaining_count_fp="0.00")]
        t.exact_order = dict(t.live_orders[0])
        t.live_fills = fills if fills is not None else [_fill()]
        result = wr.execute_post_halt_reconciliation(_input(), t)
        return result, t


class TestCapabilityAndArchitecture(ReconciliationTestCase):
    def test_exact_demo_origin_accepted(self):
        plan = wr.plan_post_halt_reconciliation(_input())
        self.assertEqual(plan.origin, wr.DEMO_REST_ORIGIN)

    def test_compatibility_demo_host_rejected(self):
        with self.assertRaises(wr.ReconciliationPlanningError) as cm:
            wr.plan_post_halt_reconciliation(_input(capability_envelope=_capability(rest_origin="https://demo-api.kalshi.co")))
        self.assertEqual(cm.exception.halt_code, wr.HaltCode.DEMO_ENVIRONMENT_REQUIRED)

    def test_production_rejected_before_send(self):
        t = FakeTransport()
        r = wr.execute_post_halt_reconciliation(
            _input(capability_envelope=_capability(rest_origin="https://external-api.kalshi.com")), t
        )
        self.assertEqual(r.halt_code, wr.HaltCode.PRODUCTION_ENDPOINT_PROHIBITED)
        self.assertEqual(t.requests, [])

    def test_environment_must_be_demo(self):
        t = FakeTransport()
        r = wr.execute_post_halt_reconciliation(_input(capability_envelope=_capability(environment="KALSHI_PRODUCTION")), t)
        self.assertEqual(r.halt_code, wr.HaltCode.DEMO_ENVIRONMENT_REQUIRED)
        self.assertEqual(len(t.requests), 0)

    def test_authenticated_read_capability_required(self):
        t = FakeTransport()
        r = wr.execute_post_halt_reconciliation(
            _input(capability_envelope=_capability(demo_authenticated_reads=wr.CapabilityState.PROHIBITED)), t
        )
        self.assertEqual(r.halt_code, wr.HaltCode.CAPABILITY_MISSING)
        self.assertEqual(len(t.requests), 0)

    def test_each_exact_execution_capability_is_independently_required(self):
        for missing in wr.ReconciliationCapabilityName:
            with self.subTest(missing=missing.value):
                granted = frozenset(
                    capability for capability in wr.REQUIRED_RECONCILIATION_CAPABILITIES
                    if capability is not missing
                )
                t = FakeTransport()
                r = wr.execute_post_halt_reconciliation(
                    _input(capability_envelope=_capability(granted_capabilities=granted)), t
                )
                self.assertEqual(r.halt_code, wr.HaltCode.CAPABILITY_MISSING)
                self.assertEqual(t.requests, [])

    def test_credential_capability_does_not_imply_account_read_capabilities(self):
        t = FakeTransport()
        r = wr.execute_post_halt_reconciliation(
            _input(capability_envelope=_capability(
                granted_capabilities=frozenset({wr.ReconciliationCapabilityName.CREDENTIAL_USE})
            )), t
        )
        self.assertEqual(r.halt_code, wr.HaltCode.CAPABILITY_MISSING)
        self.assertEqual(t.requests, [])

    def test_authenticated_read_state_does_not_imply_exact_operation_capabilities(self):
        t = FakeTransport()
        r = wr.execute_post_halt_reconciliation(
            _input(capability_envelope=_capability(granted_capabilities=frozenset())), t
        )
        self.assertEqual(r.halt_code, wr.HaltCode.CAPABILITY_MISSING)
        self.assertEqual(t.requests, [])

    def test_credential_presence_does_not_grant_capability(self):
        cap = _capability(network_access=wr.CapabilityState.PROHIBITED)
        self.assertEqual(cap.credential_reference_names[0], "KALSHI_DEMO_API_KEY_ID")
        r = wr.execute_post_halt_reconciliation(_input(capability_envelope=cap), FakeTransport())
        self.assertEqual(r.halt_code, wr.HaltCode.CAPABILITY_MISSING)

    def test_write_capability_must_be_prohibited(self):
        r = wr.execute_post_halt_reconciliation(
            _input(capability_envelope=_capability(demo_writes=wr.CapabilityState.PERMITTED)), FakeTransport()
        )
        self.assertEqual(r.halt_code, wr.HaltCode.CAPABILITY_MISSING)

    def test_websocket_capability_must_be_prohibited(self):
        r = wr.execute_post_halt_reconciliation(
            _input(capability_envelope=_capability(websocket=wr.CapabilityState.PERMITTED)), FakeTransport()
        )
        self.assertEqual(r.halt_code, wr.HaltCode.CAPABILITY_MISSING)

    def test_credential_reference_names_are_exact(self):
        r = wr.execute_post_halt_reconciliation(
            _input(capability_envelope=_capability(credential_reference_names=("REAL_SECRET",))), FakeTransport()
        )
        self.assertEqual(r.halt_code, wr.HaltCode.SECRET_BOUNDARY_VIOLATION)

    def test_only_six_closed_operations(self):
        self.assertEqual(
            tuple(op.value for op in wr.ReconciliationOperation),
            ("HISTORICAL_CUTOFF", "LIVE_ORDERS", "HISTORICAL_ORDERS", "EXACT_ORDER", "LIVE_FILLS", "HISTORICAL_FILLS"),
        )

    def test_prepared_request_method_is_literal_get(self):
        _, t = self.active_result()
        self.assertTrue(t.requests)
        self.assertTrue(all(r.method == "GET" for r in t.requests))
        self.assertFalse("method" in {f.name for f in dataclasses.fields(wr.PreparedGetRequest)})

    def test_no_body_headers_or_url_surface(self):
        names = {f.name for f in dataclasses.fields(wr.PreparedGetRequest)}
        for forbidden in ("body", "headers", "url", "host", "method"):
            self.assertNotIn(forbidden, names)

    def test_executor_has_no_method_url_path_query_body_parameters(self):
        params = set(inspect.signature(wr.execute_post_halt_reconciliation).parameters)
        for forbidden in ("method", "url", "host", "path", "query", "headers", "body", "operation"):
            self.assertNotIn(forbidden, params)

    def test_no_network_client_imports(self):
        source = Path(wr.__file__).read_text(encoding="utf-8")
        for pattern in (r"^import socket$", r"^import requests$", r"^import urllib", r"^import http\.client"):
            self.assertIsNone(re.search(pattern, source, re.MULTILINE))

    def test_no_runtime_write_verbs_in_operation_specs(self):
        source = Path(wr.__file__).read_text(encoding="utf-8")
        self.assertNotIn('method="POST"', source)
        self.assertNotIn('method="DELETE"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="PUT"', source)

    def test_signing_message_uses_get_and_path_without_query(self):
        _, t = self.active_result()
        req = next(r for r in t.requests if r.authentication_class is wr.AuthenticationClass.AUTHENTICATED)
        msg = wr.build_prepared_get_signing_message(req, timestamp_ms_text="12345")
        self.assertEqual(msg, ("12345GET" + req.path).encode())
        self.assertNotIn(b"?", msg)

    def test_public_cutoff_is_public_and_uncredentialed_shape(self):
        _, t = self.active_result()
        req = t.requests[0]
        self.assertEqual(req.operation, wr.ReconciliationOperation.HISTORICAL_CUTOFF)
        self.assertEqual(req.authentication_class, wr.AuthenticationClass.PUBLIC)
        self.assertEqual(dict(req.query), {})


class TestSourceAndStrictParsing(ReconciliationTestCase):
    def test_exact_source_binding_manifest(self):
        self.assertEqual(len(wr.SOURCE_BINDING_MANIFEST_BYTES), 6451)
        self.assertEqual(hashlib.sha256(wr.SOURCE_BINDING_MANIFEST_BYTES).hexdigest(), wr.SOURCE_BINDING_MANIFEST_SHA256)
        self.assertIsNone(wr.validate_source_binding_manifest(wr.SOURCE_BINDING_MANIFEST_BYTES))

    def test_operation_binding_identities(self):
        parsed = json.loads(wr.SOURCE_BINDING_MANIFEST_BYTES)
        for name, (length, digest) in wr.OPERATION_BINDING_IDENTITIES.items():
            raw = _json_bytes(parsed["operations"][name])
            self.assertEqual(len(raw), length, name)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, name)

    def test_source_drift_rejected_before_send(self):
        bad = bytearray(wr.SOURCE_BINDING_MANIFEST_BYTES)
        bad[-2] = ord("0") if bad[-2] != ord("0") else ord("1")
        t = FakeTransport()
        r = wr.execute_post_halt_reconciliation(_input(source_binding_manifest_bytes=bytes(bad)), t)
        self.assertEqual(r.halt_code, wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)
        self.assertEqual(t.requests, [])

    def test_source_unavailable(self):
        r = wr.execute_post_halt_reconciliation(_input(source_binding_manifest_bytes=b""), FakeTransport())
        self.assertEqual(r.halt_code, wr.HaltCode.TASK_CURRENT_SOURCE_UNAVAILABLE)

    def test_malformed_json_rejected(self):
        def handler(req, n): return _raw_response(b"{")
        r = wr.execute_post_halt_reconciliation(_input(), FakeTransport(handler))
        self.assertEqual(r.halt_code, wr.HaltCode.CUTOFF_RESPONSE_INVALID)

    def test_duplicate_json_keys_rejected(self):
        raw = b'{"market_settled_ts":"2026-08-11T10:00:00Z","market_settled_ts":"2026-08-11T10:00:00Z","trades_created_ts":"2026-08-11T10:00:00Z","orders_updated_ts":"2026-08-11T10:00:00Z"}'
        r = wr.execute_post_halt_reconciliation(_input(), FakeTransport(lambda req, n: _raw_response(raw)))
        self.assertEqual(r.halt_code, wr.HaltCode.CUTOFF_RESPONSE_INVALID)

    def test_nonfinite_json_rejected(self):
        raw = b'{"market_settled_ts":NaN,"trades_created_ts":"2026-08-11T10:00:00Z","orders_updated_ts":"2026-08-11T10:00:00Z"}'
        r = wr.execute_post_halt_reconciliation(_input(), FakeTransport(lambda req, n: _raw_response(raw)))
        self.assertEqual(r.halt_code, wr.HaltCode.CUTOFF_RESPONSE_INVALID)

    def test_cutoff_required_fields(self):
        r = wr.execute_post_halt_reconciliation(_input(), FakeTransport(lambda req, n: _response({})))
        self.assertEqual(r.halt_code, wr.HaltCode.CUTOFF_RESPONSE_INVALID)

    def test_cutoff_timestamp_required_valid(self):
        bad = _cutoff(); bad["orders_updated_ts"] = "not-a-time"
        r = wr.execute_post_halt_reconciliation(_input(), FakeTransport(lambda req, n: _response(bad)))
        self.assertEqual(r.halt_code, wr.HaltCode.CUTOFF_RESPONSE_INVALID)

    def test_order_missing_required_field(self):
        t = FakeTransport(); bad = _order(); bad.pop("ticker"); t.live_orders = [bad]
        r = wr.execute_post_halt_reconciliation(_input(), t)
        self.assertHalt(r, wr.HaltCode.ORDER_REQUIRED_FIELD_MISSING)

    def test_fill_missing_required_field(self):
        r, t = self.executed_result(fills=[])
        # construct a fresh invalid run rather than relying on the prior result
        t = FakeTransport(); t.live_orders=[_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00")]; t.exact_order=dict(t.live_orders[0]); bad=_fill(); bad.pop("trade_id"); t.live_fills=[bad]
        r = wr.execute_post_halt_reconciliation(_input(), t)
        self.assertHalt(r, wr.HaltCode.FILL_REQUIRED_FIELD_MISSING)

    def test_bool_substituted_for_integer_rejected_order(self):
        t = FakeTransport(); t.live_orders=[_order(subaccount_number=True)]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertHalt(r,wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)

    def test_count_requires_exact_two_decimal_string(self):
        for bad in ("1", "1.0", "1.000", 1.0, 1, True, "1e0"):
            with self.subTest(bad=bad):
                t=FakeTransport(); t.live_orders=[_order(initial_count_fp=bad)]
                r=wr.execute_post_halt_reconciliation(_input(),t)
                self.assertHalt(r,wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)

    def test_money_accepts_through_six_decimals(self):
        t=FakeTransport(); t.live_orders=[_order(yes_price_dollars="0.010000")]; t.exact_order=dict(t.live_orders[0])
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)

    def test_money_rejects_seven_decimals_and_exponent(self):
        for bad in ("0.0100000", "1e-2", 0.01, True, " 0.01"):
            with self.subTest(bad=bad):
                t=FakeTransport(); t.live_orders=[_order(yes_price_dollars=bad)]
                r=wr.execute_post_halt_reconciliation(_input(),t)
                self.assertHalt(r,wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)

    def test_opaque_identifiers_preserved_exactly_no_trim(self):
        # A trailing-space client id is a distinct ID, therefore zero exact matches.
        t=FakeTransport(); t.live_orders=[_order(client_order_id=wr.CLIENT_ORDER_ID+" ")]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)

    def test_legacy_fields_absent_succeeds(self):
        r,_=self.active_result(); self.assertEqual(r.bound_order_id,"order-target-001")

    def test_canonical_direction_fields_load_bearing(self):
        t=FakeTransport(); t.live_orders=[_order(outcome_side="no")]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.halt_code,wr.HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)


    def test_fill_bool_as_integer_rejected(self):
        target=_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00")
        t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[_fill(subaccount_number=True)]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertHalt(r,wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)

    def test_malformed_fill_timestamp_when_exposed_rejected(self):
        target=_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00")
        bad=_fill(); bad["created_time"]="not-a-timestamp"
        t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[bad]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertHalt(r,wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)


class TestPaginationAndQueries(ReconciliationTestCase):
    def test_exact_request_order_and_queries(self):
        _,t=self.active_result()
        self.assertEqual([r.operation for r in t.requests], [
            wr.ReconciliationOperation.HISTORICAL_CUTOFF,
            wr.ReconciliationOperation.LIVE_ORDERS,
            wr.ReconciliationOperation.HISTORICAL_ORDERS,
            wr.ReconciliationOperation.EXACT_ORDER,
            wr.ReconciliationOperation.LIVE_FILLS,
            wr.ReconciliationOperation.HISTORICAL_FILLS,
        ])
        self.assertEqual(dict(t.requests[1].query),{"ticker":wr.TICKER,"subaccount":0,"limit":1000})
        self.assertEqual(dict(t.requests[2].query),{"ticker":wr.TICKER,"limit":1000})
        self.assertEqual(dict(t.requests[3].query),{})
        self.assertEqual(dict(t.requests[4].query),{"ticker":wr.TICKER,"order_id":"order-target-001","subaccount":0,"limit":1000})
        self.assertEqual(dict(t.requests[5].query),{"ticker":wr.TICKER,"limit":1000})

    def test_multipage_cursor_copied_exactly(self):
        token=" A+/=opaque%20cursor "
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF: return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:
                return _response({"orders": [] if n==1 else [_order()], "cursor": token if n==1 else ""})
            if req.operation is wr.ReconciliationOperation.HISTORICAL_ORDERS: return _response({"orders":[],"cursor":""})
            if req.operation is wr.ReconciliationOperation.EXACT_ORDER: return _response({"order":_order()})
            return _response({"fills":[],"cursor":""})
        t=FakeTransport(handler); r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        second=[x for x in t.requests if x.operation is wr.ReconciliationOperation.LIVE_ORDERS][1]
        self.assertEqual(second.query["cursor"],token)

    def test_repeated_cursor_halts(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:return _response({"orders":[],"cursor":"cycle"})
            raise AssertionError("must stop")
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler))
        self.assertHalt(r,wr.HaltCode.PAGINATION_CURSOR_CYCLE)

    def test_missing_cursor_halts(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            return _response({"orders":[]})
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler))
        self.assertHalt(r,wr.HaltCode.PAGINATION_CURSOR_MALFORMED)

    def test_null_cursor_halts(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            return _response({"orders":[],"cursor":None})
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler))
        self.assertHalt(r,wr.HaltCode.PAGINATION_CURSOR_MALFORMED)

    def test_nonstring_cursor_halts(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            return _response({"orders":[],"cursor":1})
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler))
        self.assertHalt(r,wr.HaltCode.PAGINATION_CURSOR_MALFORMED)

    def test_live_order_page_budget(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:return _response({"orders":[],"cursor":f"c{n}"})
            raise AssertionError
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler))
        self.assertHalt(r,wr.HaltCode.PAGE_BUDGET_EXHAUSTED); self.assertEqual(r.request_count,9)

    def test_historical_order_page_budget(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:return _response({"orders":[],"cursor":""})
            if req.operation is wr.ReconciliationOperation.HISTORICAL_ORDERS:return _response({"orders":[],"cursor":f"h{n}"})
            raise AssertionError
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler)); self.assertHalt(r,wr.HaltCode.PAGE_BUDGET_EXHAUSTED)

    def test_live_fill_page_budget(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:return _response({"orders":[_order()],"cursor":""})
            if req.operation is wr.ReconciliationOperation.HISTORICAL_ORDERS:return _response({"orders":[],"cursor":""})
            if req.operation is wr.ReconciliationOperation.EXACT_ORDER:return _response({"order":_order()})
            if req.operation is wr.ReconciliationOperation.LIVE_FILLS:return _response({"fills":[],"cursor":f"f{n}"})
            raise AssertionError
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler)); self.assertHalt(r,wr.HaltCode.PAGE_BUDGET_EXHAUSTED)

    def test_historical_fill_page_budget(self):
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:return _response({"orders":[_order()],"cursor":""})
            if req.operation is wr.ReconciliationOperation.HISTORICAL_ORDERS:return _response({"orders":[],"cursor":""})
            if req.operation is wr.ReconciliationOperation.EXACT_ORDER:return _response({"order":_order()})
            if req.operation is wr.ReconciliationOperation.LIVE_FILLS:return _response({"fills":[],"cursor":""})
            if req.operation is wr.ReconciliationOperation.HISTORICAL_FILLS:return _response({"fills":[],"cursor":f"z{n}"})
            raise AssertionError
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler)); self.assertHalt(r,wr.HaltCode.PAGE_BUDGET_EXHAUSTED)

    def test_no_page_skipped(self):
        cursors=[]
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:
                cursors.append(req.query.get("cursor")); return _response({"orders":[_order()] if n==3 else [],"cursor":{1:"one",2:"two",3:""}[n]})
            if req.operation is wr.ReconciliationOperation.HISTORICAL_ORDERS:return _response({"orders":[],"cursor":""})
            if req.operation is wr.ReconciliationOperation.EXACT_ORDER:return _response({"order":_order()})
            return _response({"fills":[],"cursor":""})
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler)); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE); self.assertEqual(cursors,[None,"one","two"])


    def test_global_request_budget_guard(self):
        clock=FakeClock(start=0.0,step=0.0)
        deadline=wr._Deadline(clock=clock,entry=0.0)
        state=wr._ExecutionState()
        # A synthetic internal state at the exact global ceiling must fail
        # before transport. This does not send anything.
        state.request_counts[wr.ReconciliationOperation.LIVE_ORDERS]=8
        state.request_counts[wr.ReconciliationOperation.HISTORICAL_ORDERS]=8
        state.request_counts[wr.ReconciliationOperation.LIVE_FILLS]=8
        state.request_counts[wr.ReconciliationOperation.HISTORICAL_FILLS]=8
        state.request_counts[wr.ReconciliationOperation.HISTORICAL_CUTOFF]=1
        state.request_counts[wr.ReconciliationOperation.EXACT_ORDER]=1
        t=FakeTransport()
        parsed,response,halt=wr._send_json(operation=wr.ReconciliationOperation.HISTORICAL_CUTOFF,transport=t,deadline=deadline,state=state,page_ordinal=1)
        self.assertIsNone(parsed); self.assertIsNone(response)
        # Per-operation guard is also closed at this state, so either guard
        # can be the first deterministic barrier.
        self.assertIn(halt,(wr.HaltCode.PAGE_BUDGET_EXHAUSTED,wr.HaltCode.GLOBAL_REQUEST_BUDGET_EXHAUSTED))
        self.assertEqual(t.requests,[])


class TestOrderMatchingAndIdentity(ReconciliationTestCase):
    def test_zero_match_remains_unresolved(self):
        t=FakeTransport(); t.live_orders=[]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        self.assertIsNone(r.halt_code); self.assertIsNone(r.bound_order_id)
        self.assertEqual((r.created_order_upper_bound,r.active_order_upper_bound),(1,1)); self.assertTrue(r.unknown_result); self.assertFalse(r.writer_proof_release_eligible)
        self.assertEqual(r.request_count,3)

    def test_live_only_target(self):
        r,t=self.active_result(); self.assertEqual(r.exact_client_order_id_match_count,1); self.assertEqual(t.counts[wr.ReconciliationOperation.EXACT_ORDER],1)

    def test_historical_only_terminal_target_no_exact_get(self):
        t=FakeTransport(); t.live_orders=[]; t.historical_orders=[_order(status="canceled",remaining_count_fp="1.00")]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL); self.assertEqual(t.counts[wr.ReconciliationOperation.EXACT_ORDER],0)

    def test_historical_only_resting_partition_conflict(self):
        t=FakeTransport(); t.live_orders=[]; t.historical_orders=[_order()]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertHalt(r,wr.HaltCode.SOURCE_PARTITION_CONFLICT)

    def test_compatible_duplicate_order_collapses(self):
        t=FakeTransport(); t.historical_orders=[_order()]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE); self.assertEqual(r.exact_client_order_id_match_count,1)

    def test_conflicting_duplicate_order_halts(self):
        t=FakeTransport(); t.historical_orders=[_order(yes_price_dollars="0.0099")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertIdentityViolation(r,wr.HaltCode.ORDER_ID_DUPLICATE_CONFLICT)

    def test_multiple_distinct_exact_matches_widen_upper_bound(self):
        t=FakeTransport(); t.live_orders=[_order(order_id="a"),_order(order_id="b")]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION)
        self.assertEqual(r.halt_code,wr.HaltCode.MULTIPLE_ORDER_IDS_FOR_CLIENT_ORDER_ID)
        self.assertEqual((r.created_order_upper_bound,r.active_order_upper_bound),(2,2)); self.assertIsNone(r.bound_order_id)

    def test_secondary_economics_never_choose_candidate(self):
        t=FakeTransport(); t.live_orders=[_order(order_id="a"),_order(order_id="b",yes_price_dollars="0.0099")]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION); self.assertEqual(r.created_order_upper_bound,2)

    def test_client_id_mismatch_yields_zero_not_secondary_match(self):
        t=FakeTransport(); t.live_orders=[_order(client_order_id="different")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.result_class,wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)

    def _identity_mismatch(self, **changes: object):
        t=FakeTransport(); t.live_orders=[_order(**changes)]
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION); self.assertEqual(r.halt_code,wr.HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)
        self.assertIsNone(r.bound_order_id)

    def test_ticker_invariant(self): self._identity_mismatch(ticker="OTHER")
    def test_subaccount_invariant(self):
        # live partition itself rejects off-scope subaccount as schema/scope drift before binding
        t=FakeTransport(); t.live_orders=[_order(subaccount_number=1)]; r=wr.execute_post_halt_reconciliation(_input(),t); self.assertHalt(r,wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)
    def test_outcome_invariant(self): self._identity_mismatch(outcome_side="no")
    def test_book_side_invariant(self): self._identity_mismatch(book_side="ask")
    def test_initial_quantity_invariant(self): self._identity_mismatch(initial_count_fp="2.00")
    def test_yes_limit_invariant(self): self._identity_mismatch(yes_price_dollars="0.0200")
    def test_cancel_on_pause_invariant(self): self._identity_mismatch(cancel_order_on_pause=False)
    def test_stp_when_exposed_invariant(self): self._identity_mismatch(stp="cancel_newest")

    def test_nonexposed_intent_fields_not_fabricated(self):
        r,_=self.active_result(); evidence=json.loads(r.evidence_json); matrix=evidence["order_match"]["identity_invariant_matrix"]
        self.assertEqual(matrix["post_only"],"FIELD_NOT_EXPOSED_BY_BOUND_SOURCE")
        self.assertEqual(matrix["time_in_force"],"FIELD_NOT_EXPOSED_BY_BOUND_SOURCE")
        self.assertEqual(matrix["reduce_only"],"FIELD_NOT_EXPOSED_BY_BOUND_SOURCE")
        self.assertEqual(matrix["exchange_index"],"FIELD_NOT_EXPOSED_BY_BOUND_SOURCE")

    def test_exposed_intent_fields_exact_succeeds(self):
        t=FakeTransport(); t.live_orders=[_order(expose_intent=True)]; t.exact_order=dict(t.live_orders[0]); r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)

    def test_exposed_intent_contradiction_halts(self):
        t=FakeTransport(); bad=_order(expose_intent=True); bad["post_only"]=False; t.live_orders=[bad]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.halt_code,wr.HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)


class TestExactOrderBehavior(ReconciliationTestCase):
    def test_live_candidate_exactly_one_exact_order_get(self):
        _,t=self.active_result(); self.assertEqual(t.counts[wr.ReconciliationOperation.EXACT_ORDER],1)

    def test_exact_order_id_mismatch(self):
        t=FakeTransport(); t.exact_order=_order(order_id="different")
        r=wr.execute_post_halt_reconciliation(_input(),t)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION); self.assertEqual(r.halt_code,wr.HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)

    def test_exact_order_client_id_mismatch(self):
        t=FakeTransport(); t.exact_order=_order(client_order_id="different")
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.halt_code,wr.HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)

    def test_exact_order_economic_mismatch(self):
        t=FakeTransport(); t.exact_order=_order(yes_price_dollars="0.0099")
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.halt_code,wr.HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)

    def test_state_change_during_reconciliation(self):
        t=FakeTransport(); t.exact_order=_order(status="canceled")
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertHalt(r,wr.HaltCode.ORDER_STATE_CHANGED_DURING_RECONCILIATION); self.assertEqual(r.bound_order_id,"order-target-001")


class TestFillReconciliation(ReconciliationTestCase):
    def test_zero_fills_active(self):
        r,_=self.active_result(); self.assertEqual(r.canonical_fill_count,0); self.assertEqual(r.canonical_fill_quantity,Decimal("0.00"))

    def test_one_fill_executed(self):
        r,_=self.executed_result(); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL); self.assertEqual(r.canonical_fill_count,1); self.assertEqual(r.canonical_fill_quantity,Decimal("1.00"))

    def test_multiple_fill_events_preserved(self):
        fills=[_fill(fill_id="f1",trade_id="t1",count_fp="0.40"),_fill(fill_id="f2",trade_id="t2",count_fp="0.60")]
        r,_=self.executed_result(fills=fills); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL); self.assertEqual(r.canonical_fill_count,2)

    def test_historical_only_fill(self):
        t=FakeTransport(); target=_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00"); t.live_orders=[target]; t.exact_order=dict(target); t.historical_fills=[_fill()]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL)

    def test_compatible_duplicate_fill_id_counts_once(self):
        t=FakeTransport(); target=_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00"); t.live_orders=[target]; t.exact_order=dict(target); f=_fill(); t.live_fills=[f]; t.historical_fills=[dict(f)]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.canonical_fill_count,1); self.assertEqual(r.canonical_fill_quantity,Decimal("1.00"))

    def test_conflicting_duplicate_fill_id_halts(self):
        t=FakeTransport(); target=_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00"); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[_fill()]; t.historical_fills=[_fill(yes_price_dollars="0.0099")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertIdentityViolation(r,wr.HaltCode.FILL_ID_DUPLICATE_CONFLICT)

    def test_not_deduped_by_economic_tuple(self):
        fills=[_fill(fill_id="f1",trade_id="t1",count_fp="0.50"),_fill(fill_id="f2",trade_id="t2",count_fp="0.50")]
        r,_=self.executed_result(fills=fills); self.assertEqual(r.canonical_fill_count,2)

    def test_live_fill_wrong_order_halts(self):
        target=_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[_fill(order_id="wrong")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertIdentityViolation(r,wr.HaltCode.FILL_WRONG_ORDER)

    def test_historical_unrelated_order_is_filtered_locally(self):
        t=FakeTransport(); t.historical_fills=[_fill(order_id="other")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE); self.assertEqual(r.canonical_fill_count,0)

    def test_fill_wrong_ticker(self):
        r,_=self.executed_result(fills=[_fill(ticker="OTHER")]); self.assertIdentityViolation(r,wr.HaltCode.FILL_SCOPE_MISMATCH)
    def test_fill_wrong_subaccount(self):
        r,_=self.executed_result(fills=[_fill(subaccount_number=1)]); self.assertIdentityViolation(r,wr.HaltCode.FILL_SCOPE_MISMATCH)
    def test_fill_wrong_outcome(self):
        r,_=self.executed_result(fills=[_fill(outcome_side="no")]); self.assertIdentityViolation(r,wr.HaltCode.FILL_SCOPE_MISMATCH)
    def test_fill_wrong_book_side(self):
        r,_=self.executed_result(fills=[_fill(book_side="ask")]); self.assertIdentityViolation(r,wr.HaltCode.FILL_SCOPE_MISMATCH)
    def test_fill_wrong_market_ticker(self):
        r,_=self.executed_result(fills=[_fill(market_ticker="OTHER")]); self.assertIdentityViolation(r,wr.HaltCode.FILL_SCOPE_MISMATCH)

    def test_post_only_taker_conflict(self):
        r,_=self.executed_result(fills=[_fill(is_taker=True)]); self.assertIdentityViolation(r,wr.HaltCode.POST_ONLY_TAKER_FILL_CONFLICT)

    def test_fill_price_at_limit_allowed(self):
        r,_=self.executed_result(fills=[_fill(yes_price_dollars="0.0100")]); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL)

    def test_fill_price_worse_than_limit(self):
        r,_=self.executed_result(fills=[_fill(yes_price_dollars="0.010001")]); self.assertIdentityViolation(r,wr.HaltCode.FILL_PRICE_WORSE_THAN_LIMIT)

    def test_overfill(self):
        target=_order(status="executed",fill_count_fp="1.00",remaining_count_fp="0.00"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[_fill(fill_id="f1",trade_id="t1",count_fp="0.60"),_fill(fill_id="f2",trade_id="t2",count_fp="0.50")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertIdentityViolation(r,wr.HaltCode.OVERFILL)

    def test_order_fill_count_mismatch(self):
        target=_order(status="canceled",fill_count_fp="0.50",remaining_count_fp="0.50"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertHalt(r,wr.HaltCode.FILL_ORDER_RECONCILIATION_MISMATCH)

    def test_decimal_principal_exact(self):
        fills=[_fill(fill_id="f1",trade_id="t1",count_fp="0.25",yes_price_dollars="0.0099"),_fill(fill_id="f2",trade_id="t2",count_fp="0.75",yes_price_dollars="0.0100")]
        r,_=self.executed_result(fills=fills); self.assertEqual(r.canonical_filled_principal,Decimal("0.009975"))

    def test_fee_exact_six_decimals(self):
        r,_=self.executed_result(fills=[_fill(fee_cost="0.040000")]); self.assertEqual(r.canonical_fee_cost,Decimal("0.040000")); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL)

    def test_fee_ceiling_exceeded(self):
        r,_=self.executed_result(fills=[_fill(fee_cost="0.040001")]); self.assertIdentityViolation(r,wr.HaltCode.FEE_RISK_EXCEEDS_LIMIT)

    def test_total_risk_ceiling_exceeded(self):
        # Fee itself remains <= .04 while principal+fee exceeds .05 by .000001.
        r,_=self.executed_result(fills=[_fill(yes_price_dollars="0.0100",fee_cost="0.040000")])
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL)
        # exact ceiling is permitted
        self.assertEqual(r.canonical_filled_principal+r.canonical_fee_cost,Decimal("0.050000"))

    def test_no_complement_synthesis(self):
        r,_=self.executed_result(fills=[_fill(no_price_dollars="0.123456")])
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL)


class TestOrderStateResults(ReconciliationTestCase):
    def test_active_result_exact_fields(self):
        r,_=self.active_result(); self.assertEqual((r.created_order_upper_bound,r.active_order_upper_bound),(1,1)); self.assertFalse(r.unknown_result); self.assertFalse(r.writer_proof_release_eligible); self.assertEqual(r.bound_order_id,"order-target-001")

    def test_terminal_executed_release_eligible(self):
        r,_=self.executed_result(); self.assertEqual((r.created_order_upper_bound,r.active_order_upper_bound),(1,0)); self.assertFalse(r.unknown_result); self.assertTrue(r.writer_proof_release_eligible)

    def test_canceled_zero_fill_terminal(self):
        target=_order(status="canceled",fill_count_fp="0.00",remaining_count_fp="1.00"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target)
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL); self.assertEqual(r.canonical_fill_quantity,Decimal("0.00"))

    def test_canceled_partial_fill_terminal(self):
        target=_order(status="canceled",fill_count_fp="0.40",remaining_count_fp="0.60"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[_fill(count_fp="0.40")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL); self.assertEqual(r.canonical_fill_quantity,Decimal("0.40"))

    def test_resting_partial_fill_active(self):
        target=_order(status="resting",fill_count_fp="0.40",remaining_count_fp="0.60"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[_fill(count_fp="0.40")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE); self.assertEqual(r.canonical_fill_quantity,Decimal("0.40"))

    def test_resting_requires_positive_remaining(self):
        target=_order(status="resting",fill_count_fp="0.00",remaining_count_fp="0.00"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target)
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertHalt(r,wr.HaltCode.ORDER_FILL_ARITHMETIC_NOT_PROVEN)

    def test_executed_requires_full_fill(self):
        target=_order(status="executed",fill_count_fp="0.50",remaining_count_fp="0.50"); t=FakeTransport(); t.live_orders=[target]; t.exact_order=dict(target); t.live_fills=[_fill(count_fp="0.50")]
        r=wr.execute_post_halt_reconciliation(_input(),t); self.assertHalt(r,wr.HaltCode.FILL_ORDER_RECONCILIATION_MISMATCH)

    def test_all_five_result_classes_enumerated(self):
        self.assertEqual(set(wr.ResultClass), {
            wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE,
            wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL,
            wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH,
            wr.ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION,
            wr.ResultClass.WRITE_UNRESOLVED_READ_FAILURE,
        })

    def test_read_failure_preserves_bound_order_id(self):
        t=FakeTransport()
        def handler(req,n):
            if req.operation is wr.ReconciliationOperation.HISTORICAL_CUTOFF:return _response(_cutoff())
            if req.operation is wr.ReconciliationOperation.LIVE_ORDERS:return _response({"orders":[_order()],"cursor":""})
            if req.operation is wr.ReconciliationOperation.HISTORICAL_ORDERS:return _response({"orders":[],"cursor":""})
            if req.operation is wr.ReconciliationOperation.EXACT_ORDER:raise OSError("synthetic receive failure")
            raise AssertionError
        t.handler=handler; r=wr.execute_post_halt_reconciliation(_input(),t); self.assertHalt(r,wr.HaltCode.TRANSPORT_READ_FAILURE); self.assertEqual(r.bound_order_id,"order-target-001"); self.assertEqual((r.created_order_upper_bound,r.active_order_upper_bound),(1,1))


class TestTransportAndDeadlines(ReconciliationTestCase):
    def test_retries_remain_zero(self):
        r,t=self.active_result(); self.assertEqual(r.retry_count,0); self.assertTrue(all(req.method=="GET" for req in t.requests))

    def test_nonzero_retry_rejected(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(lambda req,n:_response(_cutoff(),retry_count=1)))
        self.assertHalt(r,wr.HaltCode.TRANSPORT_READ_FAILURE); self.assertEqual(r.retry_count,1)

    def test_redirect_not_followed(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(lambda req,n:_response({},status=302,redirect_count=1)))
        self.assertHalt(r,wr.HaltCode.REDIRECT_PROHIBITED); self.assertEqual(r.request_count,1)

    def test_http_redirect_status_even_zero_redirect_count_rejected(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(lambda req,n:_response({},status=302)))
        self.assertHalt(r,wr.HaltCode.REDIRECT_PROHIBITED)

    def test_connect_failure(self):
        def handler(req,n): raise ConnectionError("synthetic")
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler)); self.assertHalt(r,wr.HaltCode.TRANSPORT_READ_FAILURE); self.assertEqual(r.request_count,1)

    def test_receive_failure(self):
        def handler(req,n): raise OSError("synthetic receive")
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler)); self.assertHalt(r,wr.HaltCode.TRANSPORT_READ_FAILURE)

    def test_unexpected_http_status(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(lambda req,n:_response({},status=500)))
        self.assertHalt(r,wr.HaltCode.UNEXPECTED_HTTP_STATUS)

    def test_wrong_media_type(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(lambda req,n:_response(_cutoff(),media_type="text/plain")))
        self.assertEqual(r.halt_code,wr.HaltCode.CUTOFF_RESPONSE_INVALID)

    def test_deadline_before_first_request(self):
        # Entry 0; validation/replanning calls advance past 180 seconds before send.
        clock=FakeClock(start=0.0,step=100.0)
        t=FakeTransport(); r=wr.execute_post_halt_reconciliation(_input(),t,monotonic_clock=clock)
        self.assertHalt(r,wr.HaltCode.MASTER_DEADLINE_EXHAUSTED); self.assertEqual(len(t.requests),0)

    def test_per_request_timeout(self):
        clock=FakeClock(start=0.0,step=0.0)
        def handler(req,n):
            clock.current += 11.0
            return _response(_cutoff())
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(handler),monotonic_clock=clock)
        self.assertHalt(r,wr.HaltCode.TRANSPORT_READ_FAILURE)

    def test_master_deadline_after_receive(self):
        clock=FakeClock(values=[0,0,0,0,0,179.999,180.0,180.0,180.0])
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(),monotonic_clock=clock)
        self.assertHalt(r,wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_deadline_during_parse_is_checked(self):
        # Clock progresses slightly on every boundary; enough calls eventually
        # cross the master deadline while strict parsing/page handling runs.
        clock=FakeClock(start=0.0,step=30.0)
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(),monotonic_clock=clock)
        self.assertEqual(r.halt_code,wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_effective_request_ceiling_is_10_seconds(self):
        clock=FakeClock(start=100.0,step=0.0); t=FakeTransport()
        r=wr.execute_post_halt_reconciliation(_input(),t,monotonic_clock=clock)
        self.assertEqual(r.result_class,wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        self.assertTrue(all(req.effective_deadline_monotonic == 110.0 for req in t.requests))


    def test_deadline_after_order_dedupe(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(),monotonic_clock=ThresholdClock(24))
        self.assertHalt(r,wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_deadline_after_fill_dedupe(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(),monotonic_clock=ThresholdClock(46))
        self.assertHalt(r,wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_deadline_after_decimal_reconciliation(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(),monotonic_clock=ThresholdClock(47))
        self.assertHalt(r,wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_deadline_during_evidence_result_construction(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(),monotonic_clock=ThresholdClock(49))
        self.assertHalt(r,wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(r.bound_order_id,"order-target-001")


class TestEvidenceAndSecrets(ReconciliationTestCase):
    
    def test_evidence_is_deterministic_for_same_inputs(self):
        # Evidence contains required runtime timing fields, so byte-level
        # determinism is tested under an explicitly deterministic clock.
        t1 = FakeTransport()
        t2 = FakeTransport()

        r1 = wr.execute_post_halt_reconciliation(
            _input(),
            t1,
            monotonic_clock=lambda: 0.0,
        )
        r2 = wr.execute_post_halt_reconciliation(
            _input(),
            t2,
            monotonic_clock=lambda: 0.0,
        )

        self.assertEqual(
            r1.result_class,
            wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE,
        )
        self.assertEqual(
            r2.result_class,
            wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE,
        )
        self.assertEqual(r1.evidence_json, r2.evidence_json)
        self.assertEqual(r1.evidence_sha256, r2.evidence_sha256)

    def test_evidence_is_utf8_hashable(self):
        r,_=self.active_result(); r.evidence_json.decode("utf-8"); self.assertEqual(hashlib.sha256(r.evidence_json).hexdigest(),r.evidence_sha256)

    def test_evidence_has_required_sections(self):
        r,_=self.active_result(); e=json.loads(r.evidence_json)
        for key in ("identities","frozen_scope","request_ledger","enumeration","order_match","fills","terminal"):
            self.assertIn(key,e)

    def test_zero_activity_counters(self):
        r,_=self.active_result(); self.assertEqual((r.production_activity,r.write_activity,r.funding_activity,r.websocket_activity),(0,0,0,0))

    def test_no_secret_or_signature_material_in_evidence(self):
        r,_=self.active_result(); text=r.evidence_json.decode().lower()
        for forbidden in ("-----begin private key-----","-----begin rsa private key-----","api-key-value","private_key_pem_value","authorization: bearer","signature_hash","raw_signature"):
            self.assertNotIn(forbidden,text)

    def test_no_environment_dump_in_evidence(self):
        r,_=self.active_result(); text=r.evidence_json.decode(); self.assertNotIn("CONDA_DEFAULT_ENV",text); self.assertNotIn("os.environ",text)

    def test_response_provenance_hashes_not_raw_bodies(self):
        r,_=self.active_result(); e=json.loads(r.evidence_json)
        self.assertTrue(all(item["response_sha256"] for item in e["request_ledger"]))
        self.assertNotIn("raw_response_body",e)

    def test_writer_proof_release_only_terminal(self):
        active,_=self.active_result(); terminal,_=self.executed_result(); self.assertFalse(active.writer_proof_release_eligible); self.assertTrue(terminal.writer_proof_release_eligible)

    def test_zero_match_never_releases_writer_proof(self):
        t=FakeTransport(); t.live_orders=[]; r=wr.execute_post_halt_reconciliation(_input(),t); self.assertFalse(r.writer_proof_release_eligible)

    def test_identity_violation_never_releases_writer_proof(self):
        t=FakeTransport(); t.live_orders=[_order(order_id="a"),_order(order_id="b")]; r=wr.execute_post_halt_reconciliation(_input(),t); self.assertFalse(r.writer_proof_release_eligible)

    def test_read_failure_never_releases_writer_proof(self):
        r=wr.execute_post_halt_reconciliation(_input(),FakeTransport(lambda req,n:_response({},status=500))); self.assertFalse(r.writer_proof_release_eligible)

    def test_request_ledger_only_get(self):
        r,_=self.active_result(); e=json.loads(r.evidence_json); self.assertTrue(all(x["method"]=="GET" for x in e["request_ledger"]))

    def test_frozen_incident_identity_in_evidence(self):
        r,_=self.active_result(); e=json.loads(r.evidence_json); self.assertEqual(e["frozen_scope"]["client_order_id"],wr.CLIENT_ORDER_ID); self.assertEqual(e["frozen_scope"]["ticker"],wr.TICKER)


FALLBACK_SNAPSHOT = "2026-08-11T10:00:00.2500000Z"
FALLBACK_OPENAPI_BYTES = 311201
FALLBACK_OPENAPI_SHA256 = "5a58b866d9034261cc0b2f9f5f31f44799cf72153270380d66fdb2523235fa78"


def _fallback_cutoff(*, trades_created_ts: str = "2026-06-12T00:00:00Z") -> dict:
    return {
        "market_settled_ts": "2026-06-12T00:00:00Z",
        "trades_created_ts": trades_created_ts,
        "orders_updated_ts": "2026-06-12T00:00:00Z",
    }


def _fallback_fill(
    *,
    fill_id: str = "fill-discovery-001",
    trade_id: str = "trade-discovery-001",
    order_id: str = "candidate-order-001",
    ticker: str = wr.TICKER,
    market_ticker: Optional[str] = wr.TICKER,
    subaccount_number: object = 0,
    outcome_side: Optional[str] = "yes",
    book_side: Optional[str] = "bid",
    count_fp: object = "0.25",
    yes_price_dollars: object = "0.0100",
    no_price_dollars: object = "0.9900",
    is_taker: object = False,
    fee_cost: object = "0.000000",
    created_time: object = "2026-08-11T02:00:00Z",
) -> dict:
    value = {
        "fill_id": fill_id,
        "trade_id": trade_id,
        "order_id": order_id,
        "ticker": ticker,
        "count_fp": count_fp,
        "yes_price_dollars": yes_price_dollars,
        "no_price_dollars": no_price_dollars,
        "is_taker": is_taker,
        "fee_cost": fee_cost,
        "created_time": created_time,
        "ts": 1786413600,
    }
    if market_ticker is not None:
        value["market_ticker"] = market_ticker
    if subaccount_number is not None:
        value["subaccount_number"] = subaccount_number
    if outcome_side is not None:
        value["outcome_side"] = outcome_side
    if book_side is not None:
        value["book_side"] = book_side
    return value


def _fallback_order(
    *,
    order_id: str = "candidate-order-001",
    client_order_id: str = wr.CLIENT_ORDER_ID,
    ticker: str = wr.TICKER,
    subaccount_number: object = 0,
    outcome_side: str = "yes",
    book_side: str = "bid",
    order_type: str = "limit",
    status: str = "resting",
    yes_price_dollars: object = "0.0100",
    no_price_dollars: object = "0.9900",
    initial_count_fp: object = "1.00",
    fill_count_fp: object = "0.25",
    remaining_count_fp: object = "0.75",
    cancel_order_on_pause: object = True,
    exchange_index: object = 0,
    last_update_time: Optional[str] = "2026-08-11T09:59:59Z",
) -> dict:
    value = {
        "order_id": order_id,
        "client_order_id": client_order_id,
        "ticker": ticker,
        "subaccount_number": subaccount_number,
        "outcome_side": outcome_side,
        "book_side": book_side,
        "type": order_type,
        "status": status,
        "yes_price_dollars": yes_price_dollars,
        "no_price_dollars": no_price_dollars,
        "initial_count_fp": initial_count_fp,
        "fill_count_fp": fill_count_fp,
        "remaining_count_fp": remaining_count_fp,
        "cancel_order_on_pause": cancel_order_on_pause,
        "exchange_index": exchange_index,
        "self_trade_prevention_type": wr.SELF_TRADE_PREVENTION_TYPE,
    }
    if last_update_time is not None:
        value["last_update_time"] = last_update_time
    return value


def _fallback_capability(**changes: object) -> wr.FillDiscoveryCapabilityEnvelope:
    values = dict(
        environment=wr.ENVIRONMENT,
        rest_origin=wr.DEMO_REST_ORIGIN,
        credential_reference_names=("KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"),
        granted_capabilities=wr.REQUIRED_FALLBACK_CAPABILITIES,
        network_access=wr.CapabilityState.PERMITTED,
        demo_public_reads=wr.CapabilityState.PERMITTED,
        demo_authenticated_reads=wr.CapabilityState.PERMITTED,
        credential_use=wr.CapabilityState.PERMITTED,
        demo_writes=wr.CapabilityState.PROHIBITED,
        production_public_reads=wr.CapabilityState.PROHIBITED,
        production_authenticated_reads=wr.CapabilityState.PROHIBITED,
        production_writes=wr.CapabilityState.PROHIBITED,
        account_funding=wr.CapabilityState.PROHIBITED,
        websocket=wr.CapabilityState.PROHIBITED,
    )
    values.update(changes)
    return wr.FillDiscoveryCapabilityEnvelope(**values)


def _fallback_input(**changes: object) -> wr.FillDiscoveryFallbackInput:
    values = dict(
        capability_envelope=_fallback_capability(),
        source_binding_manifest_bytes=wr.FALLBACK_SOURCE_BINDING_MANIFEST_BYTES,
        provenance=wr.ReconciliationProvenance(
            implementation=_artifact("src/arb/venues/kalshi/write_result_reconciliation.py"),
            tests=_artifact("tests/test_kalshi_write_result_reconciliation.py"),
            source_raw_openapi_bytes=FALLBACK_OPENAPI_BYTES,
            source_raw_openapi_sha256=FALLBACK_OPENAPI_SHA256,
        ),
        prior_result_class=wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH,
        prior_exact_client_order_id_match_count=0,
        prior_bound_order_id=None,
        prior_created_order_upper_bound=1,
        prior_active_order_upper_bound=1,
        prior_unknown_result=True,
        prior_writer_proof_release_eligible=False,
    )
    values.update(changes)
    return wr.FillDiscoveryFallbackInput(**values)


class FallbackFakeTransport:
    def __init__(self, handler: Optional[Callable[[wr.FallbackPreparedGetRequest, int], wr.RawHttpResponse]] = None):
        self.requests: List[wr.FallbackPreparedGetRequest] = []
        self.counts: Dict[wr.FallbackOperation, int] = defaultdict(int)
        self.handler = handler or self._default
        self.cutoff = _fallback_cutoff()
        self.live_fills: List[dict] = []
        self.historical_fills: List[dict] = []
        self.orders: Dict[str, dict] = {}

    def send(self, request: wr.FallbackPreparedGetRequest) -> wr.RawHttpResponse:
        self.requests.append(request)
        self.counts[request.operation] += 1
        return self.handler(request, self.counts[request.operation])

    def _default(self, request: wr.FallbackPreparedGetRequest, ordinal: int) -> wr.RawHttpResponse:
        if request.operation is wr.FallbackOperation.HISTORICAL_CUTOFF:
            return _response(self.cutoff)
        if request.operation is wr.FallbackOperation.LIVE_FILLS:
            return _response({"fills": self.live_fills, "cursor": ""})
        if request.operation is wr.FallbackOperation.HISTORICAL_FILLS:
            return _response({"fills": self.historical_fills, "cursor": ""})
        if request.operation is wr.FallbackOperation.EXACT_ORDER:
            order_id = request.path.rsplit("/", 1)[-1]
            return _response({"order": self.orders[order_id]})
        raise AssertionError(request.operation)


class FallbackTestCase(unittest.TestCase):
    def run_fallback(
        self,
        transport: Optional[FallbackFakeTransport] = None,
        *,
        fallback_input: Optional[wr.FillDiscoveryFallbackInput] = None,
        snapshot: str = FALLBACK_SNAPSHOT,
        clock: Optional[Callable[[], float]] = None,
    ) -> Tuple[wr.FillDiscoveryFallbackResult, FallbackFakeTransport]:
        actual_transport = transport or FallbackFakeTransport()
        result = wr.execute_fill_discovery_binding_fallback(
            fallback_input or _fallback_input(),
            actual_transport,
            fill_discovery_snapshot_utc=snapshot,
            monotonic_clock=clock,
        )
        return result, actual_transport

    def active_result(self) -> Tuple[wr.FillDiscoveryFallbackResult, FallbackFakeTransport]:
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill()]
        transport.orders["candidate-order-001"] = _fallback_order()
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        return result, transport

    def assertFallbackHalt(self, result: wr.FillDiscoveryFallbackResult, code: wr.HaltCode) -> None:
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_READ_FAILURE)
        self.assertEqual(result.halt_code, code)
        self.assertFalse(result.writer_proof_release_eligible)

    def assertFallbackIdentity(self, result: wr.FillDiscoveryFallbackResult, code: wr.HaltCode) -> None:
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_IDENTITY_VIOLATION)
        self.assertEqual(result.halt_code, code)
        self.assertIsNone(result.bound_order_id)
        self.assertFalse(result.writer_proof_release_eligible)


class TestFallbackArchitectureSourceAndTime(FallbackTestCase):
    def test_exact_source_manifest_and_operation_identities(self):
        self.assertEqual(len(wr.FALLBACK_SOURCE_BINDING_MANIFEST_BYTES), 4782)
        self.assertEqual(
            hashlib.sha256(wr.FALLBACK_SOURCE_BINDING_MANIFEST_BYTES).hexdigest(),
            wr.FALLBACK_SOURCE_BINDING_MANIFEST_SHA256,
        )
        self.assertIsNone(
            wr.validate_fallback_source_binding_manifest(wr.FALLBACK_SOURCE_BINDING_MANIFEST_BYTES)
        )
        parsed = json.loads(wr.FALLBACK_SOURCE_BINDING_MANIFEST_BYTES)
        for name, (length, digest) in wr.FALLBACK_OPERATION_BINDING_IDENTITIES.items():
            raw = _json_bytes(parsed["operations"][name])
            self.assertEqual(len(raw), length, name)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, name)

    def test_only_four_fallback_operations(self):
        self.assertEqual(
            tuple(operation.value for operation in wr.FallbackOperation),
            ("HISTORICAL_CUTOFF", "LIVE_FILLS", "HISTORICAL_FILLS", "EXACT_ORDER"),
        )

    def test_fallback_public_surface_has_no_arbitrary_http_shape(self):
        names = {field.name for field in dataclasses.fields(wr.FallbackPreparedGetRequest)}
        for forbidden in ("method", "body", "headers", "url", "host"):
            self.assertNotIn(forbidden, names)
        params = set(inspect.signature(wr.execute_fill_discovery_binding_fallback).parameters)
        for forbidden in ("method", "url", "host", "path", "query", "headers", "body", "operation"):
            self.assertNotIn(forbidden, params)

    def test_fallback_source_drift_halts_before_send(self):
        bad = bytearray(wr.FALLBACK_SOURCE_BINDING_MANIFEST_BYTES)
        bad[-2] = ord("0") if bad[-2] != ord("0") else ord("1")
        result, transport = self.run_fallback(
            fallback_input=_fallback_input(source_binding_manifest_bytes=bytes(bad))
        )
        self.assertFallbackHalt(result, wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)
        self.assertEqual(transport.requests, [])

    def test_task_current_raw_source_is_required(self):
        provenance = wr.ReconciliationProvenance(
            implementation=_artifact("source"),
            tests=_artifact("tests"),
        )
        result, transport = self.run_fallback(
            fallback_input=_fallback_input(provenance=provenance)
        )
        self.assertFallbackHalt(result, wr.HaltCode.TASK_CURRENT_SOURCE_UNAVAILABLE)
        self.assertEqual(transport.requests, [])

    def test_production_and_compatibility_origins_unreachable(self):
        for origin, expected in (
            ("https://external-api.kalshi.com", wr.HaltCode.PRODUCTION_ENDPOINT_PROHIBITED),
            ("https://demo-api.kalshi.co", wr.HaltCode.DEMO_ENVIRONMENT_REQUIRED),
        ):
            with self.subTest(origin=origin):
                result, transport = self.run_fallback(
                    fallback_input=_fallback_input(
                        capability_envelope=_fallback_capability(rest_origin=origin)
                    )
                )
                self.assertFallbackHalt(result, expected)
                self.assertEqual(transport.requests, [])

    def test_each_fallback_capability_is_independent(self):
        for missing in wr.FallbackCapabilityName:
            with self.subTest(missing=missing.value):
                granted = frozenset(
                    capability for capability in wr.REQUIRED_FALLBACK_CAPABILITIES
                    if capability is not missing
                )
                result, transport = self.run_fallback(
                    fallback_input=_fallback_input(
                        capability_envelope=_fallback_capability(granted_capabilities=granted)
                    )
                )
                self.assertFallbackHalt(result, wr.HaltCode.CAPABILITY_MISSING)
                self.assertEqual(transport.requests, [])

    def test_exact_predecessor_zero_match_state_required(self):
        result, transport = self.run_fallback(
            fallback_input=_fallback_input(prior_exact_client_order_id_match_count=1)
        )
        self.assertFallbackHalt(result, wr.HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH)
        self.assertEqual(transport.requests, [])

    def test_query_time_bounds_fractional_ceiling_are_exact(self):
        result, transport = self.run_fallback()
        self.assertEqual(result.query_min_ts, 1786411334)
        self.assertEqual(result.query_max_ts, 1786442402)
        live = next(request for request in transport.requests if request.operation is wr.FallbackOperation.LIVE_FILLS)
        self.assertEqual(live.query["min_ts"], 1786411334)
        self.assertEqual(live.query["max_ts"], 1786442402)

    def test_snapshot_at_lower_bound_is_accepted(self):
        result, _ = self.run_fallback(snapshot=wr.INCIDENT_LOWER_BOUND_UTC)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        self.assertEqual(result.query_max_ts, 1786411337)

    def test_snapshot_before_lower_bound_halts_before_network(self):
        result, transport = self.run_fallback(snapshot="2026-08-11T01:22:15.7100716Z")
        self.assertFallbackHalt(result, wr.HaltCode.FILL_TIMESTAMP_INVALID)
        self.assertEqual(transport.requests, [])

    def test_malformed_snapshot_halts_before_network(self):
        result, transport = self.run_fallback(snapshot="not-a-time")
        self.assertFallbackHalt(result, wr.HaltCode.FILL_TIMESTAMP_INVALID)
        self.assertEqual(transport.requests, [])

    def test_create_timestamp_is_not_required_or_inferred(self):
        result, _ = self.run_fallback()
        evidence = json.loads(result.evidence_json)
        self.assertFalse(evidence["time_envelope"]["create_send_timestamp_required"])
        self.assertEqual(
            evidence["time_envelope"]["incident_lower_bound_source"],
            "writer_proof.valid_from_utc",
        )
        self.assertNotIn("create_send_timestamp_utc", result.evidence_json.decode("utf-8"))


class TestFallbackPartitionQueriesAndPagination(FallbackTestCase):
    def test_cutoff_less_than_or_equal_lower_uses_live_only(self):
        for cutoff in ("2026-06-12T00:00:00Z", wr.INCIDENT_LOWER_BOUND_UTC):
            with self.subTest(cutoff=cutoff):
                transport = FallbackFakeTransport()
                transport.cutoff = _fallback_cutoff(trades_created_ts=cutoff)
                result, _ = self.run_fallback(transport)
                self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
                self.assertFalse(result.historical_fill_stream_required)
                self.assertEqual(
                    [request.operation for request in transport.requests],
                    [wr.FallbackOperation.HISTORICAL_CUTOFF, wr.FallbackOperation.LIVE_FILLS],
                )

    def test_cutoff_greater_than_lower_uses_live_then_historical(self):
        transport = FallbackFakeTransport()
        transport.cutoff = _fallback_cutoff(trades_created_ts="2026-08-11T02:00:00Z")
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        self.assertTrue(result.historical_fill_stream_required)
        self.assertEqual(
            [request.operation for request in transport.requests],
            [
                wr.FallbackOperation.HISTORICAL_CUTOFF,
                wr.FallbackOperation.LIVE_FILLS,
                wr.FallbackOperation.HISTORICAL_FILLS,
            ],
        )

    def test_exact_live_and_historical_query_allowlists(self):
        transport = FallbackFakeTransport()
        transport.cutoff = _fallback_cutoff(trades_created_ts="2026-08-11T02:00:00Z")
        self.run_fallback(transport)
        live = next(request for request in transport.requests if request.operation is wr.FallbackOperation.LIVE_FILLS)
        historical = next(
            request for request in transport.requests
            if request.operation is wr.FallbackOperation.HISTORICAL_FILLS
        )
        self.assertEqual(dict(live.query), {
            "ticker": wr.TICKER,
            "subaccount": 0,
            "min_ts": 1786411334,
            "max_ts": 1786442402,
            "limit": 1000,
        })
        self.assertNotIn("order_id", live.query)
        self.assertEqual(dict(historical.query), {
            "ticker": wr.TICKER,
            "max_ts": 1786442402,
            "limit": 1000,
        })
        for unsupported in ("min_ts", "order_id", "subaccount"):
            self.assertNotIn(unsupported, historical.query)

    def test_multi_page_live_and_historical_cursor_propagation(self):
        token_live = " opaque-live+/= "
        token_historical = " opaque-historical+/= "
        def handler(request, ordinal):
            if request.operation is wr.FallbackOperation.HISTORICAL_CUTOFF:
                return _response(_fallback_cutoff(trades_created_ts="2026-08-11T02:00:00Z"))
            if request.operation is wr.FallbackOperation.LIVE_FILLS:
                return _response({"fills": [], "cursor": token_live if ordinal == 1 else ""})
            if request.operation is wr.FallbackOperation.HISTORICAL_FILLS:
                return _response({"fills": [], "cursor": token_historical if ordinal == 1 else ""})
            raise AssertionError(request.operation)
        transport = FallbackFakeTransport(handler)
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        live = [request for request in transport.requests if request.operation is wr.FallbackOperation.LIVE_FILLS]
        historical = [request for request in transport.requests if request.operation is wr.FallbackOperation.HISTORICAL_FILLS]
        self.assertEqual(live[1].query["cursor"], token_live)
        self.assertEqual(historical[1].query["cursor"], token_historical)

    def test_cursor_cycle_malformed_and_page_budget_fail_closed(self):
        def cycle_handler(request, ordinal):
            if request.operation is wr.FallbackOperation.HISTORICAL_CUTOFF:
                return _response(_fallback_cutoff())
            return _response({"fills": [], "cursor": "cycle"})
        result, _ = self.run_fallback(FallbackFakeTransport(cycle_handler))
        self.assertFallbackHalt(result, wr.HaltCode.PAGINATION_CURSOR_CYCLE)

        def malformed_handler(request, ordinal):
            if request.operation is wr.FallbackOperation.HISTORICAL_CUTOFF:
                return _response(_fallback_cutoff())
            return _response({"fills": [], "cursor": None})
        result, _ = self.run_fallback(FallbackFakeTransport(malformed_handler))
        self.assertFallbackHalt(result, wr.HaltCode.PAGINATION_CURSOR_MALFORMED)

        def budget_handler(request, ordinal):
            if request.operation is wr.FallbackOperation.HISTORICAL_CUTOFF:
                return _response(_fallback_cutoff())
            return _response({"fills": [], "cursor": "cursor-" + str(ordinal)})
        result, transport = self.run_fallback(FallbackFakeTransport(budget_handler))
        self.assertFallbackHalt(result, wr.HaltCode.PAGE_BUDGET_EXHAUSTED)
        self.assertEqual(transport.counts[wr.FallbackOperation.LIVE_FILLS], 8)

    def test_pagination_does_not_stop_after_candidate_found(self):
        def handler(request, ordinal):
            if request.operation is wr.FallbackOperation.HISTORICAL_CUTOFF:
                return _response(_fallback_cutoff())
            if request.operation is wr.FallbackOperation.LIVE_FILLS:
                return _response({
                    "fills": [_fallback_fill()] if ordinal == 1 else [],
                    "cursor": "next" if ordinal == 1 else "",
                })
            if request.operation is wr.FallbackOperation.EXACT_ORDER:
                return _response({"order": _fallback_order()})
            raise AssertionError(request.operation)
        transport = FallbackFakeTransport(handler)
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        self.assertEqual(transport.counts[wr.FallbackOperation.LIVE_FILLS], 2)


class TestFallbackCandidateBindingAndPathSafety(FallbackTestCase):
    def test_zero_order_and_zero_fill_remains_unresolved(self):
        result, _ = self.run_fallback()
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        self.assertIsNone(result.halt_code)
        self.assertIsNone(result.bound_order_id)
        self.assertTrue(result.unknown_result)
        self.assertFalse(result.writer_proof_release_eligible)

    def test_candidate_is_derived_only_from_fill_order_id(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill(order_id="authoritative-order-id", trade_id=wr.CLIENT_ORDER_ID)]
        transport.orders["authoritative-order-id"] = _fallback_order(
            order_id="authoritative-order-id", client_order_id="different"
        )
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.candidate_order_ids, ("authoritative-order-id",))
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)

    def test_candidate_path_injection_shapes_are_rejected_before_exact_send(self):
        shapes = (
            "../escape",
            "..",
            "order/extra",
            "order?query=1",
            "order#fragment",
            "order\\extra",
            "order%2fextra",
            "order%5Cextra",
            "//evil.example/path",
            "https://evil.example",
            "order\x00control",
        )
        for shape in shapes:
            with self.subTest(shape=repr(shape)):
                transport = FallbackFakeTransport()
                transport.live_fills = [_fallback_fill(order_id=shape)]
                result, _ = self.run_fallback(transport)
                self.assertFallbackHalt(result, wr.HaltCode.GET_ONLY_CONTRACT_VIOLATION)
                self.assertEqual(transport.counts[wr.FallbackOperation.EXACT_ORDER], 0)

    def test_more_than_eight_candidates_halts_before_exact_reads(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [
            _fallback_fill(fill_id=f"fill-{index}", trade_id=f"trade-{index}", order_id=f"order-{index}")
            for index in range(9)
        ]
        result, _ = self.run_fallback(transport)
        self.assertFallbackHalt(result, wr.HaltCode.CANDIDATE_ORDER_ID_BUDGET_EXCEEDED)
        self.assertEqual(result.candidate_order_id_count, 9)
        self.assertEqual(transport.counts[wr.FallbackOperation.EXACT_ORDER], 0)

    def test_one_exact_client_match_binds_active_order(self):
        result, transport = self.active_result()
        self.assertEqual(result.bound_order_id, "candidate-order-001")
        self.assertEqual(result.validated_binding_count, 1)
        self.assertEqual(result.canonical_fill_quantity, Decimal("0.25"))
        self.assertEqual(transport.counts[wr.FallbackOperation.EXACT_ORDER], 1)

    def test_wrong_client_candidate_is_rejected_not_failed(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill()]
        transport.orders["candidate-order-001"] = _fallback_order(client_order_id="different")
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        self.assertEqual(result.validated_binding_count, 0)
        self.assertFalse(result.writer_proof_release_eligible)

    def test_all_bounded_candidates_checked_after_first_validates(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [
            _fallback_fill(fill_id="fill-a", trade_id="trade-a", order_id="candidate-a"),
            _fallback_fill(fill_id="fill-b", trade_id="trade-b", order_id="candidate-b"),
        ]
        transport.orders["candidate-a"] = _fallback_order(order_id="candidate-a")
        transport.orders["candidate-b"] = _fallback_order(
            order_id="candidate-b", client_order_id="different"
        )
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        self.assertEqual(result.bound_order_id, "candidate-a")
        self.assertEqual(transport.counts[wr.FallbackOperation.EXACT_ORDER], 2)

    def test_multiple_exact_bindings_are_identity_violation(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [
            _fallback_fill(fill_id="fill-a", trade_id="trade-a", order_id="candidate-a"),
            _fallback_fill(fill_id="fill-b", trade_id="trade-b", order_id="candidate-b"),
        ]
        transport.orders["candidate-a"] = _fallback_order(order_id="candidate-a")
        transport.orders["candidate-b"] = _fallback_order(order_id="candidate-b")
        result, _ = self.run_fallback(transport)
        self.assertFallbackIdentity(result, wr.HaltCode.MULTIPLE_ORDER_IDS_FOR_CLIENT_ORDER_ID)
        self.assertEqual(result.validated_binding_count, 2)
        self.assertEqual(transport.counts[wr.FallbackOperation.EXACT_ORDER], 2)

    def test_candidate_read_non_200_and_transport_failure_are_read_failures(self):
        for mode in ("404", "transport"):
            with self.subTest(mode=mode):
                def handler(request, ordinal):
                    if request.operation is wr.FallbackOperation.HISTORICAL_CUTOFF:
                        return _response(_fallback_cutoff())
                    if request.operation is wr.FallbackOperation.LIVE_FILLS:
                        return _response({"fills": [_fallback_fill()], "cursor": ""})
                    if mode == "transport":
                        raise TimeoutError("synthetic")
                    return _response({}, status=404)
                result, _ = self.run_fallback(FallbackFakeTransport(handler))
                self.assertFallbackHalt(result, wr.HaltCode.CANDIDATE_EXACT_ORDER_READ_FAILURE)

    def test_exact_client_plus_invariant_conflict_is_identity_violation(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill()]
        transport.orders["candidate-order-001"] = _fallback_order(ticker="OTHER")
        result, _ = self.run_fallback(transport)
        self.assertFallbackIdentity(result, wr.HaltCode.ORDER_IDENTITY_OR_ECONOMIC_MISMATCH)


class TestFallbackFillExactlyOnceEconomicsAndProof(FallbackTestCase):
    def test_equivalent_duplicate_fill_id_counts_once_and_preserves_trade_id(self):
        duplicate = _fallback_fill()
        transport = FallbackFakeTransport()
        transport.live_fills = [duplicate, dict(duplicate)]
        transport.orders["candidate-order-001"] = _fallback_order()
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        self.assertEqual(result.canonical_fill_count, 1)
        evidence = json.loads(result.evidence_json)
        self.assertEqual(
            evidence["bound_fill_reconciliation"]["bound_fills"][0]["trade_id"],
            "trade-discovery-001",
        )

    def test_conflicting_duplicate_fill_id_is_identity_violation(self):
        one = _fallback_fill()
        two = _fallback_fill(yes_price_dollars="0.0099")
        transport = FallbackFakeTransport()
        transport.live_fills = [one, two]
        result, _ = self.run_fallback(transport)
        self.assertFallbackIdentity(result, wr.HaltCode.FILL_ID_DUPLICATE_CONFLICT)

    def test_same_economics_different_fill_ids_are_not_deduped(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [
            _fallback_fill(fill_id="fill-a", trade_id="trade-a", count_fp="0.25"),
            _fallback_fill(fill_id="fill-b", trade_id="trade-b", count_fp="0.25"),
        ]
        transport.orders["candidate-order-001"] = _fallback_order(
            fill_count_fp="0.50", remaining_count_fp="0.50"
        )
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        self.assertEqual(result.canonical_fill_count, 2)
        self.assertEqual(result.canonical_fill_quantity, Decimal("0.50"))

    def test_out_of_window_fill_is_locally_rejected(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [
            _fallback_fill(created_time="2026-08-11T01:22:15.7100716Z")
        ]
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        self.assertEqual(result.candidate_order_id_count, 0)
        evidence = json.loads(result.evidence_json)
        self.assertEqual(
            evidence["discovery"]["rejected_fills"][0]["reason"],
            "OUTSIDE_EXACT_INCIDENT_INTERVAL",
        )

    def test_historical_missing_subaccount_requires_exact_order_proof(self):
        transport = FallbackFakeTransport()
        transport.cutoff = _fallback_cutoff(trades_created_ts="2026-08-11T02:00:00Z")
        transport.historical_fills = [_fallback_fill(subaccount_number=None)]
        transport.orders["candidate-order-001"] = _fallback_order()
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)

        transport = FallbackFakeTransport()
        transport.cutoff = _fallback_cutoff(trades_created_ts="2026-08-11T02:00:00Z")
        transport.historical_fills = [_fallback_fill(subaccount_number=None)]
        order = _fallback_order(); order.pop("subaccount_number")
        transport.orders["candidate-order-001"] = order
        result, _ = self.run_fallback(transport)
        self.assertFallbackHalt(result, wr.HaltCode.AUTHORITATIVE_SCHEMA_DRIFT)

    def test_post_only_taker_and_limit_price_conflicts(self):
        for changes, expected in (
            ({"is_taker": True}, wr.HaltCode.POST_ONLY_TAKER_FILL_CONFLICT),
            ({"yes_price_dollars": "0.0101"}, wr.HaltCode.FILL_PRICE_WORSE_THAN_LIMIT),
        ):
            with self.subTest(expected=expected.value):
                transport = FallbackFakeTransport()
                transport.live_fills = [_fallback_fill(**changes)]
                transport.orders["candidate-order-001"] = _fallback_order()
                result, _ = self.run_fallback(transport)
                self.assertFallbackIdentity(result, expected)

    def test_decimal_principal_fee_and_risk_are_exact(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [
            _fallback_fill(count_fp="0.25", yes_price_dollars="0.0100", fee_cost="0.000001")
        ]
        transport.orders["candidate-order-001"] = _fallback_order()
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.canonical_filled_principal, Decimal("0.002500"))
        self.assertEqual(result.canonical_fee_cost, Decimal("0.000001"))
        self.assertNotIn("float(", inspect.getsource(wr.execute_fill_discovery_binding_fallback))

    def test_fee_and_total_risk_bounds_fail_closed(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill(fee_cost="0.040001")]
        transport.orders["candidate-order-001"] = _fallback_order()
        result, _ = self.run_fallback(transport)
        self.assertFallbackIdentity(result, wr.HaltCode.FEE_RISK_EXCEEDS_LIMIT)

        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill(count_fp="1.00", fee_cost="0.040001")]
        transport.orders["candidate-order-001"] = _fallback_order(
            status="executed", fill_count_fp="1.00", remaining_count_fp="0.00"
        )
        result, _ = self.run_fallback(transport)
        self.assertFallbackIdentity(result, wr.HaltCode.FEE_RISK_EXCEEDS_LIMIT)

    def test_order_fill_mismatch_is_read_failure(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill()]
        transport.orders["candidate-order-001"] = _fallback_order(fill_count_fp="0.50")
        result, _ = self.run_fallback(transport)
        self.assertFallbackHalt(result, wr.HaltCode.FILL_ORDER_RECONCILIATION_MISMATCH)

    def test_no_complement_price_synthesis(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill(no_price_dollars="0.123456")]
        transport.orders["candidate-order-001"] = _fallback_order(no_price_dollars="0.123456")
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_ACTIVE)
        evidence = json.loads(result.evidence_json)
        self.assertEqual(
            evidence["bound_fill_reconciliation"]["bound_fills"][0]["no_price_dollars"],
            "0.123456",
        )

    def test_post_snapshot_order_mutation_fails_closed(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill()]
        transport.orders["candidate-order-001"] = _fallback_order(
            last_update_time="2026-08-11T10:00:00.2500001Z"
        )
        result, _ = self.run_fallback(transport)
        self.assertFallbackHalt(result, wr.HaltCode.ORDER_STATE_AFTER_DISCOVERY_SNAPSHOT)

    def test_terminal_executed_releases_only_after_exact_reconciliation(self):
        transport = FallbackFakeTransport()
        transport.live_fills = [_fallback_fill(count_fp="1.00")]
        transport.orders["candidate-order-001"] = _fallback_order(
            status="executed", fill_count_fp="1.00", remaining_count_fp="0.00"
        )
        result, _ = self.run_fallback(transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_RECONCILED_ORDER_EXISTS_TERMINAL)
        self.assertTrue(result.writer_proof_release_eligible)
        self.assertEqual(result.active_order_upper_bound, 0)


class TestFallbackTransportDeadlineEvidenceAndRegression(FallbackTestCase):
    def test_all_requests_are_get_only_and_exact_order_has_no_query(self):
        result, transport = self.active_result()
        self.assertTrue(all(request.method == "GET" for request in transport.requests))
        exact = next(request for request in transport.requests if request.operation is wr.FallbackOperation.EXACT_ORDER)
        self.assertEqual(dict(exact.query), {})
        self.assertEqual(
            wr.build_fallback_get_signing_message(exact, timestamp_ms_text="12345"),
            ("12345GET" + exact.path).encode("utf-8"),
        )

    def test_retry_redirect_and_non_200_fail_closed(self):
        for response, expected in (
            (_response(_fallback_cutoff(), retry_count=1), wr.HaltCode.TRANSPORT_READ_FAILURE),
            (_response(_fallback_cutoff(), status=302), wr.HaltCode.REDIRECT_PROHIBITED),
            (_response(_fallback_cutoff(), status=500), wr.HaltCode.UNEXPECTED_HTTP_STATUS),
        ):
            with self.subTest(expected=expected.value):
                result, _ = self.run_fallback(FallbackFakeTransport(lambda request, ordinal, r=response: r))
                self.assertFallbackHalt(result, expected)

    def test_deadline_before_request_and_per_request_ceiling(self):
        result, transport = self.run_fallback(clock=FakeClock(start=0.0, step=100.0))
        self.assertFallbackHalt(result, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(transport.requests, [])

        clock = FakeClock(start=0.0, step=0.0)
        def slow(request, ordinal):
            clock.current += 11.0
            return _response(_fallback_cutoff())
        result, _ = self.run_fallback(FallbackFakeTransport(slow), clock=clock)
        self.assertFallbackHalt(result, wr.HaltCode.TRANSPORT_READ_FAILURE)

    def test_evidence_is_deterministic_secret_safe_and_zero_activity(self):
        first, _ = self.run_fallback(clock=lambda: 0.0)
        second, _ = self.run_fallback(clock=lambda: 0.0)
        self.assertEqual(first.evidence_json, second.evidence_json)
        self.assertEqual(first.evidence_sha256, second.evidence_sha256)
        self.assertEqual(
            hashlib.sha256(first.evidence_json).hexdigest(),
            first.evidence_sha256,
        )
        evidence_text = first.evidence_json.decode("utf-8").lower()
        for forbidden in (
            "-----begin private key-----",
            "api-key-value",
            "raw_signature",
            "signature_hash",
            "os.environ",
        ):
            self.assertNotIn(forbidden, evidence_text)
        self.assertEqual(
            (first.retry_count, first.redirect_count, first.production_activity,
             first.write_activity, first.funding_activity, first.websocket_activity),
            (0, 0, 0, 0, 0, 0),
        )

    def test_evidence_has_complete_fallback_sections(self):
        result, _ = self.active_result()
        evidence = json.loads(result.evidence_json)
        for key in (
            "identities",
            "predecessor_result",
            "frozen_scope",
            "time_envelope",
            "request_ledger",
            "discovery",
            "candidate_validation",
            "bound_fill_reconciliation",
            "terminal",
        ):
            self.assertIn(key, evidence)
        self.assertTrue(all(item["method"] == "GET" for item in evidence["request_ledger"]))

    def test_predecessor_zero_match_behavior_remains_intact(self):
        transport = FakeTransport(); transport.live_orders = []
        result = wr.execute_post_halt_reconciliation(_input(), transport)
        self.assertEqual(result.result_class, wr.ResultClass.WRITE_UNRESOLVED_ZERO_MATCH)
        self.assertEqual(result.request_count, 3)
        self.assertEqual(
            [request.operation for request in transport.requests],
            [
                wr.ReconciliationOperation.HISTORICAL_CUTOFF,
                wr.ReconciliationOperation.LIVE_ORDERS,
                wr.ReconciliationOperation.HISTORICAL_ORDERS,
            ],
        )


if __name__ == "__main__":
    unittest.main()
