"""Offline acceptance tests for Revision-02 Kalshi Demo primary-domain
historical-incident resolution (read-only).

No socket, DNS, HTTP client, environment-secret read, account access, venue
request, or write operation is performed.  Every transport interaction is an
in-memory fake and every credential-related value is non-secret metadata.
"""
from __future__ import annotations

import dataclasses
import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from arb.venues.kalshi import write_result_reconciliation as wr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _response(value: object, *, status: int = 200, media_type: str = "application/json",
              retry_count: int = 0, redirect_count: int = 0) -> wr.RawHttpResponse:
    body = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return wr.RawHttpResponse(status=status, media_type=media_type, body_bytes=body,
                               retry_count=retry_count, redirect_count=redirect_count)


def _raw_response(raw: bytes, **kwargs: object) -> wr.RawHttpResponse:
    return wr.RawHttpResponse(
        status=int(kwargs.get("status", 200)), media_type=str(kwargs.get("media_type", "application/json")),
        body_bytes=raw, retry_count=int(kwargs.get("retry_count", 0)), redirect_count=int(kwargs.get("redirect_count", 0)),
    )


def _cutoff(**overrides: str) -> dict:
    value = {
        "market_settled_ts": "2026-08-11T10:00:00Z",
        "trades_created_ts": "2026-08-11T10:00:00Z",
        "orders_updated_ts": "2026-08-11T10:00:00Z",
        "market_positions_last_updated_ts": "2026-08-11T10:00:00Z",
    }
    value.update(overrides)
    return value


def _order(
    *,
    order_id: str = "order-target-001",
    client_order_id: str = wr.CLIENT_ORDER_ID,
    ticker: str = wr.TICKER,
    subaccount_number: object = 0,
    exchange_index: object = 0,
    outcome_side: str = "yes",
    book_side: str = "bid",
    yes_price_dollars: object = "0.0100",
    no_price_dollars: object = "0.9900",
    cancel_order_on_pause: object = True,
    status: Optional[str] = "resting",
    initial_count_fp: object = "1.00",
    fill_count_fp: object = "0.00",
    remaining_count_fp: object = "1.00",
    include_status: bool = True,
    include_counts: bool = True,
    include_exchange_index: bool = True,
) -> dict:
    value: Dict[str, object] = {
        "order_id": order_id, "client_order_id": client_order_id, "ticker": ticker,
        "subaccount_number": subaccount_number, "outcome_side": outcome_side, "book_side": book_side,
        "yes_price_dollars": yes_price_dollars, "no_price_dollars": no_price_dollars,
        "cancel_order_on_pause": cancel_order_on_pause,
    }
    if include_exchange_index:
        value["exchange_index"] = exchange_index
    if include_status and status is not None:
        value["status"] = status
    if include_counts:
        value["initial_count_fp"] = initial_count_fp
        value["fill_count_fp"] = fill_count_fp
        value["remaining_count_fp"] = remaining_count_fp
    return value


def _fill(
    *,
    fill_id: str = "fill-001",
    trade_id: str = "trade-001",
    order_id: str = "order-target-001",
    ticker: str = wr.TICKER,
    subaccount_number: object = 0,
    exchange_index: object = 0,
    count_fp: object = "1.00",
    yes_price_dollars: object = "0.0100",
    no_price_dollars: object = "0.9900",
    is_taker: object = False,
    fee_cost: object = "0.000000",
    market_ticker: Optional[str] = None,
    ts: Optional[str] = "2026-08-15T10:00:00Z",
) -> dict:
    value: Dict[str, object] = {
        "fill_id": fill_id, "trade_id": trade_id, "order_id": order_id, "ticker": ticker,
        "subaccount_number": subaccount_number, "exchange_index": exchange_index,
        "count_fp": count_fp, "yes_price_dollars": yes_price_dollars, "no_price_dollars": no_price_dollars,
        "is_taker": is_taker, "fee_cost": fee_cost,
    }
    if market_ticker is not None:
        value["market_ticker"] = market_ticker
    if ts is not None:
        value["ts"] = ts
    return value


def _filled_order(**changes: object) -> dict:
    values: Dict[str, object] = dict(status="executed", fill_count_fp="1.00", remaining_count_fp="0.00")
    values.update(changes)
    return _order(**values)


def _artifact(path: str) -> wr.ArtifactIdentity:
    return wr.ArtifactIdentity(path=path, bytes=1, sha256="0" * 64, git_blob="0" * 40)


def _capability(**changes: object) -> wr.HistoricalResolutionCapabilityEnvelope:
    values: Dict[str, object] = dict(
        environment=wr.ENVIRONMENT,
        rest_origin=wr.DEMO_REST_ORIGIN,
        credential_reference_names=("KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"),
        granted_capabilities=wr.REQUIRED_HISTORICAL_RESOLUTION_CAPABILITIES,
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
    return wr.HistoricalResolutionCapabilityEnvelope(**values)


def _input(**changes: object) -> wr.HistoricalResolutionInput:
    provenance = wr.HistoricalResolutionProvenance(
        implementation=_artifact("src/arb/venues/kalshi/write_result_reconciliation.py"),
        tests=_artifact("tests/test_kalshi_write_result_reconciliation.py"),
    )
    values: Dict[str, object] = dict(
        capability_envelope=_capability(),
        source_binding_manifest_bytes=wr.SOURCE_BINDING_MANIFEST_BYTES,
        provenance=provenance,
    )
    values.update(changes)
    return wr.HistoricalResolutionInput(**values)


class FakeTransport:
    """Configurable in-memory GET-only fake.  ``pages`` maps an operation to a
    list of page payloads (dicts) consumed in order; ``handler`` overrides
    per-request behavior for failure/edge-case tests."""

    def __init__(self, *, handler: Optional[Callable[["FakeTransport", wr.PreparedGetRequest, int], wr.RawHttpResponse]] = None):
        self.requests: List[wr.PreparedGetRequest] = []
        self.counts: Dict[wr.HistoricalResolutionOperation, int] = {}
        self.handler = handler or FakeTransport._default
        self.user_data_timestamp = {"as_of_time": "2026-08-19T23:42:00Z"}
        self.cutoff_sequence: List[dict] = [_cutoff(), _cutoff()]
        self.live_orders: List[dict] = []
        self.historical_orders: List[dict] = []
        self.exact_orders: Dict[str, dict] = {}
        self.live_fills: List[dict] = []
        self.historical_fills: List[dict] = []
        self.live_positions: List[dict] = []
        self.historical_positions: List[dict] = []
        self.settlements: List[dict] = []
        self._cutoff_calls = 0

    def send(self, request: wr.PreparedGetRequest) -> wr.RawHttpResponse:
        self.requests.append(request)
        ordinal = self.counts.get(request.operation, 0) + 1
        self.counts[request.operation] = ordinal
        return self.handler(self, request, ordinal)

    def _default(self, request: wr.PreparedGetRequest, ordinal: int) -> wr.RawHttpResponse:
        Op = wr.HistoricalResolutionOperation
        op = request.operation
        if op is Op.USER_DATA_TIMESTAMP:
            return _response(self.user_data_timestamp)
        if op is Op.HISTORICAL_CUTOFF:
            self._cutoff_calls += 1
            index = min(self._cutoff_calls - 1, len(self.cutoff_sequence) - 1)
            return _response(self.cutoff_sequence[index])
        if op is Op.LIVE_ORDERS:
            return _response({"orders": self.live_orders, "cursor": ""})
        if op is Op.HISTORICAL_ORDERS:
            return _response({"orders": self.historical_orders, "cursor": ""})
        if op is Op.EXACT_ORDER:
            order_id = request.path.rsplit("/", 1)[-1]
            order = self.exact_orders.get(order_id)
            if order is None:
                return _response({"error": "not_found"}, status=404)
            return _response({"order": order})
        if op is Op.LIVE_FILLS:
            return _response({"fills": self.live_fills, "cursor": ""})
        if op is Op.HISTORICAL_FILLS:
            return _response({"fills": self.historical_fills, "cursor": ""})
        if op is Op.LIVE_POSITIONS:
            return _response({"market_positions": self.live_positions, "cursor": ""})
        if op is Op.HISTORICAL_POSITIONS:
            return _response({"market_positions": self.historical_positions, "cursor": ""})
        if op is Op.SETTLEMENTS:
            return _response({"settlements": self.settlements, "cursor": ""})
        raise AssertionError(op)


class FakeClock:
    def __init__(self, *, start: float = 1000.0, step: float = 0.01):
        self.current = start
        self.step = step

    def __call__(self) -> float:
        value = self.current
        self.current += self.step
        return value


def _wall(iso: str = "2026-08-19T23:42:00Z") -> Callable[[], datetime]:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return lambda: dt


def _run(transport: FakeTransport, historical_input: Optional[wr.HistoricalResolutionInput] = None,
         *, wall_clock: Optional[Callable[[], datetime]] = None,
         monotonic_clock: Optional[Callable[[], float]] = None) -> wr.HistoricalResolutionResult:
    return wr.execute_historical_resolution_read(
        historical_input or _input(), transport,
        monotonic_clock=monotonic_clock or FakeClock(),
        wall_clock=wall_clock or _wall(),
    )

class ClosedSurfaceTests(unittest.TestCase):
    """RA1-TEST-001 / RA1-CAP-003: closed ten-operation GET-only surface."""

    def test_exactly_ten_operations(self) -> None:
        self.assertEqual(len(wr.HistoricalResolutionOperation), 10)
        expected = {
            "USER_DATA_TIMESTAMP", "HISTORICAL_CUTOFF", "LIVE_ORDERS", "HISTORICAL_ORDERS",
            "EXACT_ORDER", "LIVE_FILLS", "HISTORICAL_FILLS", "LIVE_POSITIONS",
            "HISTORICAL_POSITIONS", "SETTLEMENTS",
        }
        self.assertEqual({op.value for op in wr.HistoricalResolutionOperation}, expected)

    def test_prepared_request_has_no_writable_method_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(wr.PreparedGetRequest)}
        self.assertNotIn("method", field_names)
        request = wr.PreparedGetRequest(
            operation=wr.HistoricalResolutionOperation.HISTORICAL_CUTOFF, origin=wr.DEMO_REST_ORIGIN,
            path="/trade-api/v2/historical/cutoff", query={}, authentication_class=wr.AuthenticationClass.PUBLIC,
            page_ordinal=1, effective_deadline_monotonic=1.0,
        )
        self.assertEqual(request.method, "GET")

    def test_transport_protocol_has_no_generic_dispatch(self) -> None:
        import inspect
        members = {name for name, _ in inspect.getmembers(wr.HistoricalResolutionTransport) if not name.startswith("_")}
        self.assertEqual(members, {"send"})

    def test_get_only_contract_rejects_non_demo_origin(self) -> None:
        bad = wr.PreparedGetRequest(
            operation=wr.HistoricalResolutionOperation.HISTORICAL_CUTOFF, origin=wr.PRODUCTION_REST_ORIGIN,
            path="/trade-api/v2/historical/cutoff", query={}, authentication_class=wr.AuthenticationClass.PUBLIC,
            page_ordinal=1, effective_deadline_monotonic=1.0,
        )
        self.assertEqual(wr._validate_prepared_request(bad), wr.HaltCode.GET_ONLY_CONTRACT_VIOLATION)

    def test_get_only_contract_rejects_extra_query_key(self) -> None:
        bad = wr.PreparedGetRequest(
            operation=wr.HistoricalResolutionOperation.LIVE_ORDERS, origin=wr.DEMO_REST_ORIGIN,
            path="/trade-api/v2/portfolio/orders",
            query={"ticker": wr.TICKER, "min_ts": 1, "max_ts": 2, "limit": 1000, "subaccount": 0,
                   "exchange_index": 0, "status": "resting"},
            authentication_class=wr.AuthenticationClass.AUTHENTICATED, page_ordinal=1, effective_deadline_monotonic=1.0,
        )
        self.assertEqual(wr._validate_prepared_request(bad), wr.HaltCode.GET_ONLY_CONTRACT_VIOLATION)

    def test_historical_orders_query_excludes_unsupported_live_filters(self) -> None:
        query = wr._query_for(wr.HistoricalResolutionOperation.HISTORICAL_ORDERS, max_ts=123)
        self.assertEqual(set(query), {"ticker", "max_ts", "limit"})

    def test_historical_fills_query_excludes_unsupported_fields(self) -> None:
        query = wr._query_for(wr.HistoricalResolutionOperation.HISTORICAL_FILLS, max_ts=123)
        self.assertEqual(set(query), {"ticker", "max_ts", "limit"})

    def test_live_orders_query_exact(self) -> None:
        query = wr._query_for(wr.HistoricalResolutionOperation.LIVE_ORDERS, min_ts=1, max_ts=2)
        self.assertEqual(dict(query), {"ticker": wr.TICKER, "min_ts": 1, "max_ts": 2, "limit": 1000,
                                        "subaccount": 0, "exchange_index": 0})

    def test_live_fills_pre_binding_omits_order_id(self) -> None:
        query = wr._query_for(wr.HistoricalResolutionOperation.LIVE_FILLS, min_ts=1, max_ts=2)
        self.assertNotIn("order_id", query)

    def test_live_fills_post_binding_includes_order_id(self) -> None:
        query = wr._query_for(wr.HistoricalResolutionOperation.LIVE_FILLS, min_ts=1, max_ts=2, order_id="oid")
        self.assertEqual(query["order_id"], "oid")

    def test_no_generic_transport_interface_beyond_send(self) -> None:
        self.assertFalse(hasattr(wr.HistoricalResolutionTransport, "post"))
        self.assertFalse(hasattr(wr.HistoricalResolutionTransport, "request"))


class CapabilityTests(unittest.TestCase):
    def test_eleven_independent_capabilities(self) -> None:
        self.assertEqual(len(wr.HistoricalResolutionCapabilityName), 11)
        self.assertEqual(len(wr.REQUIRED_HISTORICAL_RESOLUTION_CAPABILITIES), 11)

    def test_missing_one_capability_fails_closed(self) -> None:
        capabilities = frozenset(wr.HistoricalResolutionCapabilityName) - {wr.HistoricalResolutionCapabilityName.SETTLEMENT_LIST_READ}
        result = _run(FakeTransport(), _input(capability_envelope=_capability(granted_capabilities=capabilities)))
        self.assertEqual(result.halt_code, wr.HaltCode.CAPABILITY_MISSING)
        self.assertEqual(result.result_class, wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION)

    def test_production_endpoint_rejected(self) -> None:
        result = _run(FakeTransport(), _input(capability_envelope=_capability(rest_origin=wr.PRODUCTION_REST_ORIGIN)))
        self.assertEqual(result.halt_code, wr.HaltCode.PRODUCTION_ENDPOINT_PROHIBITED)

    def test_demo_writes_must_be_prohibited(self) -> None:
        result = _run(FakeTransport(), _input(capability_envelope=_capability(demo_writes=wr.CapabilityState.PERMITTED)))
        self.assertEqual(result.halt_code, wr.HaltCode.CAPABILITY_MISSING)

    def test_wrong_credential_reference_names_fails_closed(self) -> None:
        result = _run(FakeTransport(), _input(capability_envelope=_capability(credential_reference_names=("WRONG",))))
        self.assertEqual(result.halt_code, wr.HaltCode.SECRET_BOUNDARY_VIOLATION)

    def test_source_binding_drift_detected(self) -> None:
        result = _run(FakeTransport(), _input(source_binding_manifest_bytes=b"not-the-manifest"))
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED)
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)

    def test_operation_bindings_match_source_manifest(self) -> None:
        self.assertIsNone(wr.validate_source_binding_manifest(wr.SOURCE_BINDING_MANIFEST_BYTES))
        for name, (nbytes, digest) in wr.OPERATION_BINDING_IDENTITIES.items():
            self.assertEqual(len(digest), 64)
            self.assertGreater(nbytes, 0)

    def test_missing_artifact_identity_fails_closed(self) -> None:
        bad_provenance = wr.HistoricalResolutionProvenance(
            implementation=wr.ArtifactIdentity(path="", bytes=1, sha256="0" * 64, git_blob="0" * 40),
            tests=_artifact("t"),
        )
        result = _run(FakeTransport(), _input(provenance=bad_provenance))
        self.assertEqual(result.halt_code, wr.HaltCode.CONTROLLING_ARTIFACT_IDENTITY_MISMATCH)

class ScopeTests(unittest.TestCase):
    """RA1-TEST-003: reject wrong environment/scope inputs."""

    def test_wrong_environment_fails_closed(self) -> None:
        result = _run(FakeTransport(), _input(capability_envelope=_capability(environment="KALSHI_PRODUCTION")))
        self.assertEqual(result.halt_code, wr.HaltCode.DEMO_ENVIRONMENT_REQUIRED)

    def test_frozen_incident_identity_constants(self) -> None:
        self.assertEqual(wr.INCIDENT_ID, "KALSHI_DEMO_ONE_ORDER_LIFECYCLE_EXECUTION_01")
        self.assertEqual(wr.CONFLICT_DOMAIN_REF, "KALSHI|KALSHI_DEMO|ARB_KALSHI_DEMO_PRIMARY_ACCOUNT|SUBACCOUNT=0")
        self.assertEqual(wr.TICKER, "KXFEDDECISION-26SEP-H0")
        self.assertEqual(wr.CLIENT_ORDER_ID, "2e64d452-2cc2-43fa-a976-e8f996192252")
        self.assertEqual(wr.SUBACCOUNT, 0)
        self.assertEqual(wr.EXCHANGE_INDEX, 0)

    def test_historical_order_wrong_subaccount_locally_rejected(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_order(status="executed", subaccount_number=7)]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)

    def test_historical_order_wrong_ticker_locally_rejected(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_order(status="executed", ticker="OTHER-TICKER")]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)

    def test_wrong_client_order_id_never_matches(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_order(client_order_id="11111111-1111-1111-1111-111111111111")]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)


class PaginationTests(unittest.TestCase):
    """RA1-TEST-007 / RA1-PAGE-001..003."""

    def test_first_request_omits_cursor_next_uses_exact_prior(self) -> None:
        transport = FakeTransport()
        pages = [
            {"orders": [], "cursor": "cursor-a"},
            {"orders": [], "cursor": ""},
        ]
        calls = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.LIVE_ORDERS:
                page = pages[calls["n"]]
                calls["n"] += 1
                if calls["n"] == 1:
                    self.assertNotIn("cursor", request.query)
                else:
                    self.assertEqual(request.query["cursor"], "cursor-a")
                return _response(page)
            return t._default(request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)

    def test_repeated_cursor_is_cycle(self) -> None:
        transport = FakeTransport()

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.LIVE_ORDERS:
                return _response({"orders": [], "cursor": "same"})
            return t._default(request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.PAGINATION_CURSOR_CYCLE)

    def test_malformed_cursor_fails_closed(self) -> None:
        transport = FakeTransport()

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.LIVE_ORDERS:
                return _response({"orders": [], "cursor": None})
            return t._default(request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.PAGINATION_CURSOR_MALFORMED)

    def test_page_cap_with_nonterminal_cursor_is_incomplete(self) -> None:
        transport = FakeTransport()
        counter = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.LIVE_ORDERS:
                counter["n"] += 1
                return _response({"orders": [], "cursor": f"cursor-{counter['n']}"})
            return t._default(request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.SOURCE_TRAVERSAL_INCOMPLETE)
        self.assertEqual(counter["n"], wr.MAX_LIVE_ORDER_PAGES)

    def test_duplicate_record_does_not_terminate_enumeration(self) -> None:
        transport = FakeTransport()
        transport.exact_orders["order-target-001"] = _order(status="resting")
        pages = [
            {"orders": [_order(status="resting")], "cursor": "c1"},
            {"orders": [_order(status="resting")], "cursor": ""},
        ]
        calls = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.LIVE_ORDERS:
                page = pages[calls["n"]]
                calls["n"] += 1
                return _response(page)
            return t._default(request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_ACTIVE)

class Correction01Tests(unittest.TestCase):
    """RA2-C01-001..006 and the mandatory C01-T01..T09 acceptance cases."""

    def test_c01_t01_live_direct_requires_exact_reread(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_order(status="resting")]
        transport.exact_orders["order-target-001"] = _order(status="resting")
        result = _run(transport)
        self.assertEqual(result.binding_source_class, wr.BindingSourceClass.LIVE_PRESENT)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.EXACT_ORDER), 1)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_ACTIVE)

    def test_c01_t02_live_reread_404_is_incomplete_not_nonexistence(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_order(status="resting")]
        # exact_orders left empty -> 404 on reread
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.DIRECT_LIVE_EXACT_ORDER_REVALIDATION_UNAVAILABLE)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ENDPOINT_OR_SOURCE_FAILURE)
        self.assertNotEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_AUTHORITATIVE_NONEXISTENCE_PROVEN)

    def test_c01_t03_historical_only_terminal_binds_with_zero_reread(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        result = _run(transport)
        self.assertEqual(result.binding_source_class, wr.BindingSourceClass.HISTORICAL_ONLY)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.EXACT_ORDER, 0), 0)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED)

    def test_c01_t04_historical_only_resting_is_partition_conflict(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_order(status="resting")]
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.HISTORICAL_ORDER_PARTITION_CONFLICT)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.EXACT_ORDER, 0), 0)

    def test_c01_t05_historical_wrong_scope_cannot_bind(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_order(status="executed", exchange_index=5)]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)

    def test_c01_t06_compatible_live_and_historical_requires_reread(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_filled_order()]
        transport.historical_orders = [_filled_order()]
        transport.exact_orders["order-target-001"] = _filled_order()
        result = _run(transport)
        self.assertEqual(result.binding_source_class, wr.BindingSourceClass.LIVE_AND_HISTORICAL_COMPATIBLE)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.EXACT_ORDER), 1)

    def test_c01_t07_contradictory_source_identity_fails_closed(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_order(status="executed", yes_price_dollars="0.0100")]
        transport.historical_orders = [_order(status="executed", yes_price_dollars="0.0200")]
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.ORDER_ID_DUPLICATE_CONFLICT)
        self.assertEqual(result.result_class, wr.ResultClass.READ_IDENTITY_AMBIGUOUS)

    def test_c01_t08_fill_derived_reread_mandatory(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="fill-derived-order")]
        transport.exact_orders["fill-derived-order"] = _order(order_id="fill-derived-order", status="resting")
        result = _run(transport)
        self.assertEqual(result.binding_source_class, wr.BindingSourceClass.FILL_DERIVED)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.EXACT_ORDER), 1)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_ACTIVE)

    def test_c01_t09_fill_derived_404_is_unresolved_not_shortcut(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="missing-order")]
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.CANDIDATE_EXACT_ORDER_UNAVAILABLE)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ENDPOINT_OR_SOURCE_FAILURE)


class Correction02Tests(unittest.TestCase):
    """RA2-C02-001..003 and the mandatory C02-T01..T12 acceptance cases."""

    def test_c02_t01_t02_t03_fill_derived_reuses_fills_zero_second_sends(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="order-target-001")]
        transport.exact_orders["order-target-001"] = _filled_order()
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_FILL_DERIVED_ORDER_BOUND_TERMINAL_RECONCILED)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.LIVE_FILLS), 1)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_FILLS), 1)
        payload = json.loads(result.evidence_json)
        self.assertEqual(payload["fill_discovery"]["fill_evidence_origin"], "PRE_BINDING_FILL_DISCOVERY_REUSED")
        self.assertTrue(payload["fill_discovery"]["live_fill_source_reused"])
        self.assertTrue(payload["fill_discovery"]["historical_fill_source_reused"])
        self.assertFalse(payload["fill_discovery"]["second_fill_traversal_performed"])

    def test_c02_t04_live_direct_terminal_one_fill_traversal_each_source(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_filled_order()]
        transport.exact_orders["order-target-001"] = _filled_order()
        transport.live_fills = [_fill()]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.LIVE_FILLS), 1)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_FILLS), 1)
        payload = json.loads(result.evidence_json)
        self.assertEqual(payload["fill_discovery"]["fill_evidence_origin"], "POST_BINDING_BOUND_ORDER_TRAVERSAL")

    def test_c02_t05_historical_direct_terminal_one_post_binding_traversal(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.LIVE_FILLS), 1)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_FILLS), 1)

    def test_c02_t06_incomplete_pre_binding_fill_traversal_is_economic_incomplete(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="order-target-001")]
        transport.exact_orders["order-target-001"] = _order(status="executed")
        counter = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.HISTORICAL_FILLS:
                counter["n"] += 1
                return _response({"fills": [], "cursor": f"cursor-{counter['n']}"})
            return FakeTransport._default(t, request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.SOURCE_TRAVERSAL_INCOMPLETE)

    def test_c02_t07_moving_cutoff_conflict_no_repair_resend(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="order-target-001")]
        transport.exact_orders["order-target-001"] = _order(status="executed")
        transport.cutoff_sequence = [_cutoff(trades_created_ts="2026-08-11T10:00:00Z"),
                                      _cutoff(trades_created_ts="2026-08-11T09:00:00Z")]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.LIVE_FILLS), 1)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_FILLS), 1)

    def test_c02_t08_fill_derived_terminal_maximum_116(self) -> None:
        self.assertEqual(wr.BRANCH_REQUEST_MAXIMA["FILL_DERIVED_TERMINAL"], 116)
        self.assertEqual(wr.GLOBAL_GET_SEND_MAXIMUM, 116)
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="order-target-001")]
        transport.exact_orders["order-target-001"] = _order(status="executed")
        result = _run(transport)
        self.assertLessEqual(result.request_count, 116)
        self.assertLessEqual(result.request_count, wr.GLOBAL_GET_SEND_MAXIMUM)

    def test_c02_t09_live_direct_maximum_109(self) -> None:
        self.assertEqual(wr.BRANCH_REQUEST_MAXIMA["LIVE_DIRECT_TERMINAL"], 109)
        transport = FakeTransport()
        transport.live_orders = [_order(status="executed")]
        transport.exact_orders["order-target-001"] = _order(status="executed")
        result = _run(transport)
        self.assertLessEqual(result.request_count, 109)

    def test_c02_t10_historical_direct_maximum_108(self) -> None:
        self.assertEqual(wr.BRANCH_REQUEST_MAXIMA["HISTORICAL_ONLY_DIRECT_TERMINAL"], 108)
        transport = FakeTransport()
        transport.historical_orders = [_order(status="executed")]
        result = _run(transport)
        self.assertLessEqual(result.request_count, 108)

    def test_c02_t11_unused_global_budget_cannot_fund_unplanned_get(self) -> None:
        state = wr._ExecutionState()
        state.branch = "HISTORICAL_ONLY_DIRECT_ACTIVE"
        for op in wr.HistoricalResolutionOperation:
            state.request_counts[op] = 0
        state.request_counts[wr.HistoricalResolutionOperation.HISTORICAL_ORDERS] = 45
        deadline = wr._Deadline(clock=FakeClock(), entry=1000.0)
        transport = FakeTransport()
        _, _, halt = wr._send_json(
            operation=wr.HistoricalResolutionOperation.LIVE_POSITIONS, transport=transport,
            deadline=deadline, state=state, page_ordinal=1,
        )
        self.assertEqual(halt, wr.HaltCode.BRANCH_REQUEST_BUDGET_EXHAUSTED)

    def test_c02_t12_nonterminal_cursor_at_page_cap_is_incomplete_regardless_of_budget(self) -> None:
        transport = FakeTransport()
        counter = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.HISTORICAL_ORDERS:
                counter["n"] += 1
                return _response({"orders": [], "cursor": f"c{counter['n']}"})
            return FakeTransport._default(t, request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.SOURCE_TRAVERSAL_INCOMPLETE)
        self.assertEqual(counter["n"], wr.MAX_HISTORICAL_ORDER_PAGES)
        self.assertLess(result.request_count, wr.GLOBAL_GET_SEND_MAXIMUM)

class StrictUtcTimestampTests(unittest.TestCase):
    """RA1-TIME-003 Correction 01: authoritative source timestamps must be
    strict UTC; non-zero-offset tz-aware values must not pass."""

    def test_time_c01_user_data_timestamp_nonzero_utc_offset_fails_closed(self) -> None:
        transport = FakeTransport()
        transport.user_data_timestamp = {"as_of_time": "2026-08-19T19:42:00-04:00"}
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)
        self.assertEqual(result.result_class, wr.ResultClass.READ_AUTHORITATIVE_RESPONSE_MALFORMED)

    def test_time_c01_user_data_timestamp_positive_offset_also_fails_closed(self) -> None:
        transport = FakeTransport()
        transport.user_data_timestamp = {"as_of_time": "2026-08-20T01:42:00+02:00"}
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)

    def test_time_c02_historical_cutoff_nonzero_utc_offset_fails_closed(self) -> None:
        transport = FakeTransport()
        transport.cutoff_sequence = [_cutoff(orders_updated_ts="2026-08-11T06:00:00-04:00"), _cutoff()]
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)

    def test_zero_offset_explicit_form_is_accepted_as_utc(self) -> None:
        self.assertTrue(wr._valid_utc_rfc3339("2026-08-19T23:42:00+00:00"))
        self.assertTrue(wr._valid_utc_rfc3339("2026-08-19T23:42:00Z"))
        self.assertFalse(wr._valid_utc_rfc3339("2026-08-19T23:42:00-04:00"))
        self.assertFalse(wr._valid_utc_rfc3339("2026-08-19T23:42:00+02:00"))
        self.assertFalse(wr._valid_utc_rfc3339("not-a-timestamp"))
        self.assertFalse(wr._valid_utc_rfc3339(12345))

    def test_time_c03_user_data_timestamp_post_before_pre_fails_closed(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        calls = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP:
                calls["n"] += 1
                value = "2026-08-19T23:42:00Z" if calls["n"] == 1 else "2026-08-19T23:41:00Z"
                return _response({"as_of_time": value})
            return FakeTransport._default(t, request, ordinal)

        transport.handler = handler
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.HISTORICAL_CUTOFF_OR_FRESHNESS_GAP)
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)

    def test_time_c04_user_data_timestamp_post_equal_pre_is_allowed(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.user_data_timestamp = {"as_of_time": "2026-08-19T23:42:00Z"}
        result = _run(transport)
        self.assertNotEqual(result.halt_code, wr.HaltCode.HISTORICAL_CUTOFF_OR_FRESHNESS_GAP)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED)

    def test_time_c05_user_data_timestamp_post_after_pre_does_not_alone_prove_coverage(self) -> None:
        # Freshness monotonicity passing must not, by itself, grant cutoff
        # partition coverage -- that is the separate PAGE-005 theorem.
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        calls = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP:
                calls["n"] += 1
                value = "2026-08-19T23:42:00Z" if calls["n"] == 1 else "2026-08-19T23:50:00Z"
                return _response({"as_of_time": value})
            return FakeTransport._default(t, request, ordinal)

        transport.handler = handler
        transport.cutoff_sequence = [
            _cutoff(orders_updated_ts="2026-08-11T10:00:00Z"),
            _cutoff(orders_updated_ts="2026-09-01T00:00:00Z"),
        ]
        result = _run(transport)
        # Freshness advanced fine, but the huge cutoff jump is unprovable by
        # our bounded query ceiling -> still fails on the separate theorem.
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)


class EconomicsTests(unittest.TestCase):
    def test_decimal_only_arithmetic(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill(count_fp="1.00", yes_price_dollars="0.0100", fee_cost="0.005000")]
        result = _run(transport)
        self.assertIsInstance(result.canonical_fill_quantity, Decimal)
        self.assertIsInstance(result.canonical_filled_principal, Decimal)
        self.assertEqual(result.canonical_fill_quantity, Decimal("1.00"))
        self.assertEqual(result.canonical_filled_principal, Decimal("0.010000"))
        self.assertEqual(result.canonical_fee_cost, Decimal("0.005000"))

    def test_zero_filled_quantity_is_not_rejection(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_order(status="canceled", fill_count_fp="0.00", remaining_count_fp="1.00")]
        result = _run(transport)
        self.assertIn(result.result_class, (
            wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED,
            wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE,
        ))
        self.assertEqual(result.canonical_fill_quantity, Decimal("0.00"))

    def test_submitted_limit_price_never_used_as_fill_price(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill(yes_price_dollars="0.0050")]
        result = _run(transport)
        self.assertEqual(result.canonical_filled_principal, Decimal("0.005000"))
        self.assertNotEqual(result.canonical_filled_principal, wr.LIMIT_PRICE)

    def test_order_aggregate_count_never_becomes_synthetic_fill(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        # No fills at all: order claims fill_count_fp="1.00" but zero fills observed.
        result = _run(transport)
        self.assertEqual(result.canonical_fill_quantity, Decimal("0.00"))
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE)

    def test_economic_bound_violation_marks_incomplete_not_negative(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill(fee_cost="1.000000")]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE)
        self.assertEqual(result.halt_code, wr.HaltCode.ECONOMIC_RISK_INVARIANT_VIOLATION)


class ActiveOrderTests(unittest.TestCase):
    def test_active_binding_sends_no_positions_or_settlements(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_order(status="resting")]
        transport.exact_orders["order-target-001"] = _order(status="resting")
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_ACTIVE)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.LIVE_POSITIONS, 0), 0)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.SETTLEMENTS, 0), 0)
        payload = json.loads(result.evidence_json)
        self.assertEqual(payload["terminal_result"]["writer_proof_state_after"], "HELD")
        self.assertFalse(payload["terminal_result"]["writer_proof_release_eligible_after"])

    def test_active_binding_preserves_writer_proof_held(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_order(status="resting")]
        transport.exact_orders["order-target-001"] = _order(status="resting")
        result = _run(transport)
        self.assertEqual(result.writer_proof_state_after, "HELD")
        self.assertFalse(result.writer_proof_release_eligible_after)
        self.assertFalse(result.persistent_state_accessed)
        self.assertFalse(result.persistent_state_mutated)


class PositionSettlementLimitationTests(unittest.TestCase):
    def test_historical_position_absence_cannot_prove_subaccount_zero_closure(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.historical_positions = []
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        self.assertFalse(payload["position_evidence"]["historical_subaccount_scope_proven"])

    def test_settlement_rows_cannot_create_order_identity(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.settlements = [{"ticker": wr.TICKER, "settled_time": "2026-08-19T00:00:00Z"}]
        result = _run(transport)
        self.assertEqual(result.bound_order_id, "order-target-001")


class FailureClassTests(unittest.TestCase):
    def _fail_op(self, op: wr.HistoricalResolutionOperation, response: wr.RawHttpResponse) -> wr.HistoricalResolutionResult:
        transport = FakeTransport()

        def handler(t, request, ordinal):
            if request.operation is op:
                return response
            return FakeTransport._default(t, request, ordinal)

        transport.handler = handler
        return _run(transport)

    def test_http_400(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _response({}, status=400))
        self.assertEqual(result.halt_code, wr.HaltCode.UNEXPECTED_HTTP_STATUS)

    def test_http_401(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _response({}, status=401))
        self.assertEqual(result.halt_code, wr.HaltCode.UNEXPECTED_HTTP_STATUS)

    def test_http_403(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _response({}, status=403))
        self.assertEqual(result.halt_code, wr.HaltCode.UNEXPECTED_HTTP_STATUS)

    def test_http_404(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.HISTORICAL_CUTOFF, _response({}, status=404))
        self.assertEqual(result.halt_code, wr.HaltCode.UNEXPECTED_HTTP_STATUS)

    def test_http_429(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _response({}, status=429))
        self.assertEqual(result.halt_code, wr.HaltCode.UNEXPECTED_HTTP_STATUS)

    def test_http_5xx(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _response({}, status=503))
        self.assertEqual(result.halt_code, wr.HaltCode.UNEXPECTED_HTTP_STATUS)

    def test_redirect_rejected(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _response({}, status=302))
        self.assertEqual(result.halt_code, wr.HaltCode.REDIRECT_PROHIBITED)

    def test_nonzero_retry_count_is_contract_violation(self) -> None:
        result = self._fail_op(
            wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP,
            _response({"as_of_time": "2026-08-19T23:42:00Z"}, retry_count=1),
        )
        self.assertEqual(result.halt_code, wr.HaltCode.TRANSPORT_READ_FAILURE)

    def test_nonzero_redirect_count_is_prohibited(self) -> None:
        result = self._fail_op(
            wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP,
            _response({"as_of_time": "2026-08-19T23:42:00Z"}, redirect_count=1),
        )
        self.assertEqual(result.halt_code, wr.HaltCode.REDIRECT_PROHIBITED)

    def test_transport_exception_is_read_failure(self) -> None:
        def handler(t, request, ordinal):
            raise ConnectionError("boom")

        transport = FakeTransport(handler=handler)
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.TRANSPORT_READ_FAILURE)

    def test_malformed_json_rejected(self) -> None:
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _raw_response(b"{not json"))
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)

    def test_duplicate_json_keys_rejected(self) -> None:
        raw = b'{"as_of_time":"2026-08-19T23:42:00Z","as_of_time":"2026-08-19T23:43:00Z"}'
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _raw_response(raw))
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)

    def test_nan_infinity_rejected(self) -> None:
        raw = b'{"as_of_time":NaN}'
        result = self._fail_op(wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP, _raw_response(raw))
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)

    def test_wrong_media_type_rejected(self) -> None:
        result = self._fail_op(
            wr.HistoricalResolutionOperation.USER_DATA_TIMESTAMP,
            _response({"as_of_time": "2026-08-19T23:42:00Z"}, media_type="text/html"),
        )
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED)

    def test_zero_retries_constant(self) -> None:
        self.assertEqual(wr.HTTP_RETRIES, 0)
        self.assertEqual(wr.REDIRECTS_FOLLOWED, 0)

class DeadlineTests(unittest.TestCase):
    def test_deadline_exhausted_before_any_send(self) -> None:
        state = {"calls": 0}

        def clock() -> float:
            state["calls"] += 1
            if state["calls"] == 1:
                return 1000.0
            return 1000.0 + wr.MASTER_DEADLINE_MS / 1000.0 + 1.0

        transport = FakeTransport()
        result = _run(transport, monotonic_clock=clock)
        self.assertEqual(result.halt_code, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(len(transport.requests), 0)

    def test_deadline_crossed_during_parse_is_exhaustion(self) -> None:
        entry = 1000.0
        # Advance far past the deadline on the very first clock read after entry
        # (the read used to check remaining budget prior to parsing the body).
        values = [entry, entry, entry + wr.MASTER_DEADLINE_MS / 1000.0 + 5.0]

        def clock_seq():
            if values:
                return values.pop(0)
            return entry + wr.MASTER_DEADLINE_MS / 1000.0 + 5.0

        transport = FakeTransport()
        result = _run(transport, monotonic_clock=clock_seq)
        self.assertEqual(result.halt_code, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_deadline_crossed_after_transport_is_exhaustion_not_stale_success(self) -> None:
        # RA1-BOUND-002 Correction 02: a deadline already exhausted by the time
        # _build_result runs must produce READ_MASTER_DEADLINE_EXHAUSTED, never
        # silently return whatever ordinary result_class the caller selected
        # before transport completed.
        state = wr._ExecutionState()
        deadline = wr._Deadline(clock=lambda: 99999999.0, entry=0.0)
        inp = _input()
        result = wr._build_result(
            historical_resolution_input=inp, state=state, deadline=deadline, ctx={},
            result_class=wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN, halt_code=None,
        )
        self.assertIsInstance(result, wr.HistoricalResolutionResult)
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(result.halt_code, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def _build_result_with_expiry_at_call(self, expire_at_call: int) -> wr.HistoricalResolutionResult:
        counter = {"n": 0}

        def clock() -> float:
            counter["n"] += 1
            if counter["n"] >= expire_at_call:
                return 10_000_000.0
            return 100.0

        state = wr._ExecutionState()
        deadline = wr._Deadline(clock=clock, entry=100.0)
        return wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=deadline, ctx={},
            result_class=wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN, halt_code=None,
        )

    def test_bound_c01_deadline_expires_before_evidence_payload_construction(self) -> None:
        result = self._build_result_with_expiry_at_call(1)
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_bound_c02_deadline_expires_before_canonical_serialization_hash(self) -> None:
        result = self._build_result_with_expiry_at_call(2)
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_bound_c03_deadline_expires_during_or_after_artifact_hashing(self) -> None:
        result = self._build_result_with_expiry_at_call(3)
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_bound_c04_deadline_expires_immediately_before_terminal_return(self) -> None:
        result = self._build_result_with_expiry_at_call(5)
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_bound_c05_deadline_valid_through_final_boundary_returns_ordinary_result(self) -> None:
        state = wr._ExecutionState()
        deadline = wr._Deadline(clock=FakeClock(start=100.0, step=0.01), entry=100.0)
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=deadline, ctx={},
            result_class=wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN, halt_code=None,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)
        self.assertIsNone(result.halt_code)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_deadline_exhausted_path_never_recurses_into_build_result(self) -> None:
        # The deadline-exhaustion terminal construction must be a single
        # bounded pass: constructing it for a result_class that is *already*
        # READ_MASTER_DEADLINE_EXHAUSTED must not re-enter the checkpoint
        # logic (no infinite loop / no repeated evidence construction).
        state = wr._ExecutionState()
        deadline = wr._Deadline(clock=lambda: 99999999.0, entry=0.0)
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=deadline, ctx={},
            result_class=wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED, halt_code=wr.HaltCode.MASTER_DEADLINE_EXHAUSTED,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_per_request_ceiling_and_master_deadline_are_frozen(self) -> None:
        self.assertEqual(wr.MASTER_DEADLINE_MS, 180_000)
        self.assertEqual(wr.PER_REQUEST_CEILING_MS, 10_000)
        self.assertEqual(wr.MASTER_DEADLINE_MS, 180_000, "correction must not raise the deadline")


class TerminalPrecedenceDeadlineTests(unittest.TestCase):
    """RA1-BOUND-002 + RA1-RES-004 Correction 02: deadline exhaustion (tier 2)
    must not erase an already-observed tier-1 capability/environment/
    provenance/source-drift defect, but must still override every lower
    tier (malformed/ambiguous response, identity ambiguity, source failure/
    incompleteness, history-interval gaps, and every positive/zero-match
    terminal class)."""

    @staticmethod
    def _expired_deadline() -> wr._Deadline:
        return wr._Deadline(clock=lambda: 99999999.0, entry=0.0)

    def test_res_bound_c01_source_drift_outranks_deadline(self) -> None:
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_SOURCE_DRIFT,
            halt_code=wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))
        payload = json.loads(result.evidence_json)
        self.assertEqual(payload["terminal_result"]["result_class"], "READ_SOURCE_DRIFT")
        self.assertEqual(payload["terminal_result"]["halt_code"], "AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED")

    def test_res_bound_c02_capability_scope_violation_outranks_deadline(self) -> None:
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION,
            halt_code=wr.HaltCode.CAPABILITY_MISSING,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION)
        self.assertEqual(result.halt_code, wr.HaltCode.CAPABILITY_MISSING)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_res_bound_c03_ordinary_success_loses_to_deadline(self) -> None:
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED, halt_code=None,
            bound_order_id="order-target-001",
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(result.halt_code, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_res_bound_c04_lower_precedence_unresolved_result_loses_to_deadline(self) -> None:
        # READ_SOURCE_TRAVERSAL_INCOMPLETE is precedence tier 5; deadline
        # exhaustion is tier 2 and must override it per the controlling table.
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_SOURCE_TRAVERSAL_INCOMPLETE, halt_code=wr.HaltCode.SOURCE_TRAVERSAL_INCOMPLETE,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(result.halt_code, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_res_bound_c04_zero_match_result_loses_to_deadline(self) -> None:
        # Precedence tier 9 (zero-match negative theorem) is also below deadline.
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN, halt_code=None,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)

    def test_res_bound_c05_malformed_response_loses_to_deadline(self) -> None:
        # Precedence tier 3 (malformed/ambiguous response) ranks below
        # deadline exhaustion (tier 2) in the controlling table.
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_AUTHORITATIVE_RESPONSE_MALFORMED,
            halt_code=wr.HaltCode.AUTHORITATIVE_RESPONSE_MALFORMED,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(result.halt_code, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)

    def test_res_bound_c05_identity_ambiguous_loses_to_deadline(self) -> None:
        # Precedence tier 4 also ranks below deadline exhaustion.
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_IDENTITY_AMBIGUOUS, halt_code=wr.HaltCode.ORDER_ID_DUPLICATE_CONFLICT,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)

    def test_res_bound_c06_no_recursion_at_every_checkpoint(self) -> None:
        # Force expiry from the very first checkpoint for both a tier-1
        # (preserved) and a lower-tier (overridden) result_class, and confirm
        # each terminates deterministically with exactly one final result.
        for result_class, halt_code in (
            (wr.ResultClass.READ_SOURCE_DRIFT, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED),
            (wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION, wr.HaltCode.CAPABILITY_MISSING),
            (wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE, wr.HaltCode.HISTORY_INTERVAL_UNOBSERVABLE),
            (wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN, None),
        ):
            with self.subTest(result_class=result_class):
                state = wr._ExecutionState()
                result = wr._build_result(
                    historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
                    result_class=result_class, halt_code=halt_code,
                )
                self.assertIsInstance(result, wr.HistoricalResolutionResult)
                self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_res_bound_c07_evidence_valid_for_preserved_higher_precedence_result(self) -> None:
        state = wr._ExecutionState()
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=self._expired_deadline(), ctx={},
            result_class=wr.ResultClass.READ_SOURCE_DRIFT,
            halt_code=wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
        )
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))
        payload = json.loads(result.evidence_json)
        self.assertEqual(payload["artifact_integrity"]["artifact_sha256"], result.evidence_sha256)
        self.assertEqual(payload["historical_resolution_evidence_schema_revision"], 2)

    def test_res_bound_c08_source_drift_plus_expired_deadline_sends_zero_requests(self) -> None:
        # Integration-level: source-drift is detected at P0 validation, before
        # any transport call, so it is inherently zero-send; confirm the
        # combined precedence/deadline path does not add any repair sends.
        transport = FakeTransport()
        bad_input = _input(source_binding_manifest_bytes=b"not-the-manifest")
        result = _run(transport, bad_input)
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        self.assertEqual(len(transport.requests), 0)

    def test_res_bound_c08_capability_violation_sends_zero_requests(self) -> None:
        transport = FakeTransport()
        bad_input = _input(capability_envelope=_capability(rest_origin=wr.PRODUCTION_REST_ORIGIN))
        result = _run(transport, bad_input)
        self.assertEqual(result.result_class, wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION)
        self.assertEqual(len(transport.requests), 0)


class LateDeadlineObservationTests(unittest.TestCase):
    """RA1-BOUND-002 + RA1-RES-004 Correction 03: the clock MUST be consulted
    (Question A) at every checkpoint even when the currently selected result
    already outranks deadline exhaustion (Question B); a late crossing
    observed after a tier-1 result's evidence was already built/hashed must
    still be reflected in the final evidence rather than a stale
    below-deadline snapshot, without any recursive/looping reconstruction."""

    MASTER_S = wr.MASTER_DEADLINE_MS / 1000.0

    def _clock_expiring_at_call(self, expire_at_call: int, *, entry: float = 100.0, late_by: float = 5.0):
        counter = {"n": 0}

        def clock() -> float:
            counter["n"] += 1
            if counter["n"] >= expire_at_call:
                return entry + self.MASTER_S + late_by
            return entry

        return clock, counter

    def _build(self, result_class: wr.ResultClass, halt_code, expire_at_call: int):
        clock, counter = self._clock_expiring_at_call(expire_at_call)
        state = wr._ExecutionState()
        deadline = wr._Deadline(clock=clock, entry=100.0)
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=deadline, ctx={},
            result_class=result_class, halt_code=halt_code,
        )
        return result, counter

    # -- source drift (checkpoints 2/3/4 correspond to clock calls 3/4/5) --

    def test_res_bound_late_c01_source_drift_crosses_after_payload_construction(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_SOURCE_DRIFT, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
            expire_at_call=3,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        self.assertEqual(result.halt_code, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))
        payload = json.loads(result.evidence_json)
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)
        self.assertGreater(counter["n"], 1, "later checkpoints must actually consult the clock")

    def test_res_bound_late_c02_source_drift_crosses_before_hashing(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_SOURCE_DRIFT, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
            expire_at_call=3,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        payload = json.loads(result.evidence_json)
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_res_bound_late_c03_source_drift_crosses_during_or_after_hashing(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_SOURCE_DRIFT, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
            expire_at_call=4,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        payload = json.loads(result.evidence_json)
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))
        self.assertEqual(payload["artifact_integrity"]["hash_verification"], "PASS")

    def test_res_bound_late_c04_source_drift_crosses_before_final_return(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_SOURCE_DRIFT, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
            expire_at_call=5,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        payload = json.loads(result.evidence_json)
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    # -- capability/scope violation (same checkpoint mechanics) --

    def test_res_bound_late_c05_capability_scope_crosses_after_payload_construction(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION, wr.HaltCode.CAPABILITY_MISSING, expire_at_call=3,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION)
        self.assertEqual(result.halt_code, wr.HaltCode.CAPABILITY_MISSING)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))
        payload = json.loads(result.evidence_json)
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)

    def test_res_bound_late_c06_capability_scope_crosses_post_hash(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION, wr.HaltCode.CAPABILITY_MISSING, expire_at_call=4,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION)
        payload = json.loads(result.evidence_json)
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    def test_res_bound_late_c07_capability_scope_crosses_at_final_return(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION, wr.HaltCode.CAPABILITY_MISSING, expire_at_call=5,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION)
        payload = json.loads(result.evidence_json)
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    # -- lower precedence still yields --

    def test_res_bound_late_c08_lower_precedence_result_still_yields_to_late_deadline(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_SOURCE_TRAVERSAL_INCOMPLETE, wr.HaltCode.SOURCE_TRAVERSAL_INCOMPLETE, expire_at_call=1,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_MASTER_DEADLINE_EXHAUSTED)
        self.assertEqual(result.halt_code, wr.HaltCode.MASTER_DEADLINE_EXHAUSTED)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    # -- deadline observation is not short-circuited --

    def test_res_bound_late_c09_deadline_observation_not_short_circuited(self) -> None:
        # Deadline never expires: every checkpoint must still consult the
        # clock for a tier-1 result (5 calls: 4 checkpoints + 1 elapsed_ms
        # read), proving no precedence guard suppressed the clock read itself.
        counter = {"n": 0}

        def never_expires() -> float:
            counter["n"] += 1
            return 100.0

        state = wr._ExecutionState()
        deadline = wr._Deadline(clock=never_expires, entry=100.0)
        result = wr._build_result(
            historical_resolution_input=_input(), state=state, deadline=deadline, ctx={},
            result_class=wr.ResultClass.READ_SOURCE_DRIFT, halt_code=wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
        )
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        self.assertGreaterEqual(counter["n"], 5, "all four checkpoints plus the elapsed_ms read must consult the clock")
        payload = json.loads(result.evidence_json)
        self.assertLess(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)

    # -- bounded finalization / no recursion --

    def test_res_bound_late_c10_bounded_finalization_no_recursion(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_SOURCE_DRIFT, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
            expire_at_call=1,  # expired from the very first observation onward
        )
        self.assertIsInstance(result, wr.HistoricalResolutionResult)
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        # Exactly one patch-and-rehash pass: 4 checkpoint reads + 1 elapsed_ms
        # read + 1 corrected elapsed_ms read = 6, never unbounded/looping.
        self.assertEqual(counter["n"], 6)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))

    # -- evidence consistency --

    def test_res_bound_late_c11_evidence_consistency_for_tier1_plus_late_deadline(self) -> None:
        result, counter = self._build(
            wr.ResultClass.READ_SOURCE_DRIFT, wr.HaltCode.AUTHORITATIVE_SOURCE_DRIFT_SPEC_REVISION_REQUIRED,
            expire_at_call=3,
        )
        payload = json.loads(result.evidence_json)
        recomputed = wr._sha256(wr._canonical_json_bytes(
            {**payload, "artifact_integrity": {**payload["artifact_integrity"], "artifact_sha256": None}}
        ))
        self.assertEqual(recomputed, payload["artifact_integrity"]["artifact_sha256"])
        self.assertEqual(payload["terminal_result"]["result_class"], "READ_SOURCE_DRIFT")
        self.assertGreaterEqual(payload["terminal_result"]["elapsed_ms"], wr.MASTER_DEADLINE_MS)
        self.assertEqual(result.evidence_sha256, payload["artifact_integrity"]["artifact_sha256"])

    # -- zero transport changes (integration level) --

    def test_res_bound_late_c12_source_drift_plus_late_deadline_sends_zero_requests(self) -> None:
        clock, _counter = self._clock_expiring_at_call(3, entry=100.0)
        transport = FakeTransport()
        bad_input = _input(source_binding_manifest_bytes=b"not-the-manifest")
        result = _run(transport, bad_input, monotonic_clock=clock)
        self.assertEqual(result.result_class, wr.ResultClass.READ_SOURCE_DRIFT)
        self.assertEqual(len(transport.requests), 0)

    def test_res_bound_late_c12_capability_violation_plus_late_deadline_sends_zero_requests(self) -> None:
        clock, _counter = self._clock_expiring_at_call(3, entry=100.0)
        transport = FakeTransport()
        bad_input = _input(capability_envelope=_capability(rest_origin=wr.PRODUCTION_REST_ORIGIN))
        result = _run(transport, bad_input, monotonic_clock=clock)
        self.assertEqual(result.result_class, wr.ResultClass.READ_CAPABILITY_OR_SCOPE_VIOLATION)
        self.assertEqual(len(transport.requests), 0)


class EvidenceSchemaTests(unittest.TestCase):
    def test_top_level_keys_exact(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        expected = {
            "historical_resolution_evidence_schema_revision", "task_id", "provenance", "scope",
            "immutable_incident", "source_binding", "external_research_provenance", "capability_record",
            "time_envelope", "request_log", "cutoff_observations", "user_data_timestamp_observations",
            "order_discovery", "fill_discovery", "position_evidence", "settlement_evidence",
            "binding_decision", "economic_reconciliation", "completeness_assessment",
            "negative_closure_assessment", "counters", "terminal_result", "secret_redaction",
            "artifact_integrity",
        }
        self.assertEqual(set(payload.keys()), expected)
        self.assertEqual(payload["historical_resolution_evidence_schema_revision"], 2)

    def test_canonical_json_is_sorted_and_compact(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        text = result.evidence_json.decode("utf-8")
        self.assertNotIn(", ", text)
        self.assertNotIn(": ", text)
        self.assertFalse(text.endswith("\n"))

    def test_integrity_hash_round_trip(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        self.assertTrue(wr.verify_evidence_artifact_integrity(result.evidence_json))
        payload = json.loads(result.evidence_json)
        self.assertEqual(payload["artifact_integrity"]["artifact_sha256"], result.evidence_sha256)

    def test_tampered_evidence_fails_integrity(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        payload["counters"]["request_count"] = 999999
        tampered = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertFalse(wr.verify_evidence_artifact_integrity(tampered))

    def test_request_log_excludes_secret_fields(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        text = result.evidence_json.decode("utf-8")
        for forbidden in ("KALSHI-ACCESS-SIGNATURE", "KALSHI-ACCESS-TIMESTAMP", "Authorization:", "BEGIN PRIVATE KEY"):
            self.assertNotIn(forbidden, text)

    def test_historical_only_evidence_invariants(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        binding = payload["binding_decision"]
        self.assertEqual(binding["binding_source_class"], "HISTORICAL_ONLY")
        self.assertFalse(binding["exact_order_reread_required"])
        self.assertFalse(binding["exact_order_reread_performed"])
        self.assertEqual(binding["exact_order_reread_reason"], "NOT_REQUIRED_HISTORICAL_ONLY")

    def test_fill_derived_evidence_invariants(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="order-target-001")]
        transport.exact_orders["order-target-001"] = _filled_order()
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        binding = payload["binding_decision"]
        self.assertEqual(binding["binding_source_class"], "FILL_DERIVED")
        self.assertTrue(binding["exact_order_reread_required"])
        self.assertTrue(binding["exact_order_reread_performed"])
        self.assertEqual(binding["exact_order_reread_reason"], "FILL_DERIVED_IDENTITY_BINDING")
        self.assertEqual(payload["fill_discovery"]["fill_evidence_origin"], "PRE_BINDING_FILL_DISCOVERY_REUSED")

    def test_counters_carry_branch_and_global_budget(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        counters = payload["counters"]
        self.assertEqual(counters["theoretical_maximum_planned_get_sends"], 116)
        self.assertEqual(counters["global_get_send_maximum"], 116)
        self.assertIn("planned_branch", counters)
        self.assertIn("theoretical_branch_request_max", counters)


class SecretSafetyTests(unittest.TestCase):
    def test_signing_message_has_no_secret_material(self) -> None:
        request = wr.PreparedGetRequest(
            operation=wr.HistoricalResolutionOperation.HISTORICAL_CUTOFF, origin=wr.DEMO_REST_ORIGIN,
            path="/trade-api/v2/historical/cutoff", query={}, authentication_class=wr.AuthenticationClass.PUBLIC,
            page_ordinal=1, effective_deadline_monotonic=1.0,
        )
        message = wr.build_prepared_get_signing_message(request, timestamp_ms_text="1755000000000")
        self.assertEqual(message, b"1755000000000GET/trade-api/v2/historical/cutoff")
        self.assertNotIn(b"KALSHI-ACCESS", message)

    def test_signing_message_rejects_non_get_shaped_request(self) -> None:
        bad = wr.PreparedGetRequest(
            operation=wr.HistoricalResolutionOperation.LIVE_ORDERS, origin=wr.PRODUCTION_REST_ORIGIN,
            path="/trade-api/v2/portfolio/orders", query={}, authentication_class=wr.AuthenticationClass.AUTHENTICATED,
            page_ordinal=1, effective_deadline_monotonic=1.0,
        )
        with self.assertRaises(ValueError):
            wr.build_prepared_get_signing_message(bad, timestamp_ms_text="123")

    def test_credential_reference_names_are_metadata_only(self) -> None:
        cap = _capability()
        self.assertEqual(cap.credential_reference_names, ("KALSHI_DEMO_API_KEY_ID", "KALSHI_DEMO_PRIVATE_KEY_PEM"))
        self.assertNotIn("BEGIN PRIVATE KEY", str(cap.credential_reference_names))

class NegativeTheoremTests(unittest.TestCase):
    """RA1-NEG-001..007 / RA1-TEST-019/029/030: negative closure is
    structurally unreachable under Revision 02."""

    def test_negative_result_class_exists_in_closed_enum(self) -> None:
        self.assertIn(
            wr.ResultClass.READ_ZERO_MATCH_AUTHORITATIVE_NONEXISTENCE_PROVEN,
            list(wr.ResultClass),
        )

    def test_negative_result_class_cannot_be_constructed_by_build_result(self) -> None:
        state = wr._ExecutionState()
        deadline = wr._Deadline(clock=FakeClock(), entry=1000.0)
        with self.assertRaises(AssertionError):
            wr._build_result(
                historical_resolution_input=_input(), state=state, deadline=deadline, ctx={},
                result_class=wr.ResultClass.READ_ZERO_MATCH_AUTHORITATIVE_NONEXISTENCE_PROVEN, halt_code=None,
            )

    def test_complete_zero_traversal_never_reaches_negative_class(self) -> None:
        transport = FakeTransport()  # everything empty, terminal cursors reached immediately
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)
        payload = json.loads(result.evidence_json)
        self.assertFalse(payload["negative_closure_assessment"]["authoritative_nonexistence_proven"])
        self.assertFalse(payload["negative_closure_assessment"]["revision_02_negative_closure_permitted"])

    def test_negative_closure_predicate_vector_has_22_predicates(self) -> None:
        vector = wr._negative_closure_assessment(orders_complete=True, fills_complete=True, cutoff_regressed=False, zero_match=True)
        predicate_keys = [k for k in vector if k.startswith("predicate_N")]
        self.assertEqual(len(predicate_keys), 22)
        for i in range(1, 23):
            self.assertIn(f"predicate_N{i:02d}", vector)

    def test_revision_02_negative_closure_permitted_constant_is_false(self) -> None:
        self.assertFalse(wr.REVISION_02_NEGATIVE_CLOSURE_PERMITTED)

    def test_retention_lower_bound_never_proven_even_with_terminal_cursors(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        self.assertFalse(payload["completeness_assessment"]["retention_lower_bound_proven"])


class WriteBoundaryTests(unittest.TestCase):
    """RA1-CAP-003 / RA1-NOWRITE-001..002 / RA1-TEST-024."""

    def test_no_write_verb_assigned_as_a_request_method(self) -> None:
        import inspect
        source = inspect.getsource(wr)
        for verb in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn(f'method="{verb}"', source)
            self.assertNotIn(f"method='{verb}'", source)
            self.assertNotIn(f"method: str = \"{verb}\"", source)

    def test_capability_envelope_has_no_write_or_trading_fields(self) -> None:
        field_names = {f.name for f in dataclasses.fields(wr.HistoricalResolutionCapabilityEnvelope)}
        for forbidden in ("cancel", "create", "amend", "decrease", "replace", "funding_transfer", "order_write"):
            self.assertNotIn(forbidden, field_names)

    def test_no_cancel_or_create_function_exported(self) -> None:
        exported = {name for name in dir(wr) if not name.startswith("_")}
        for forbidden in ("cancel_order", "create_order", "amend_order", "replace_order", "fund_account"):
            self.assertNotIn(forbidden, exported)


class PersistentStateAndStage3Tests(unittest.TestCase):
    def test_result_never_reports_persistent_mutation(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        self.assertFalse(result.persistent_state_accessed)
        self.assertFalse(result.persistent_state_mutated)
        payload = json.loads(result.evidence_json)
        self.assertFalse(payload["terminal_result"]["persistent_state_accessed"])
        self.assertFalse(payload["terminal_result"]["persistent_state_mutated"])

    def test_writer_proof_never_released_by_this_module(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        result = _run(transport)
        self.assertEqual(result.writer_proof_state_after, "HELD")
        self.assertFalse(result.writer_proof_release_eligible_after)

    def test_no_stage3_capability_names_defined_in_module_namespace(self) -> None:
        for forbidden in ("PreReleaseReadCapabilityV1", "CurrentProcessReleaseCompletionV1",
                          "NormalWriterPermit", "NORMAL_WRITER", "WRITER_ELIGIBLE"):
            self.assertFalse(hasattr(wr, forbidden), forbidden)


class CandidateAndConflictTests(unittest.TestCase):
    def test_candidate_budget_overflow(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(fill_id=f"fill-{i}", order_id=f"order-{i}") for i in range(9)]
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.CANDIDATE_ORDER_ID_BUDGET_EXCEEDED)
        self.assertEqual(result.result_class, wr.ResultClass.READ_MULTIPLE_CANDIDATE_ORDER_IDS)

    def test_multiple_bound_candidates_fail_closed(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(fill_id="f1", order_id="order-a"), _fill(fill_id="f2", order_id="order-b")]
        transport.exact_orders["order-a"] = _order(order_id="order-a", status="resting")
        transport.exact_orders["order-b"] = _order(order_id="order-b", status="resting")
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.MULTIPLE_CANDIDATE_ORDER_IDS)

    def test_duplicate_fill_id_conflict(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [
            _fill(fill_id="dup", fee_cost="0.000000"),
            _fill(fill_id="dup", fee_cost="0.001000"),
        ]
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.FILL_ID_DUPLICATE_CONFLICT)

    def test_duplicate_order_id_conflict(self) -> None:
        transport = FakeTransport()
        transport.live_orders = [_order(yes_price_dollars="0.0100")]
        transport.historical_orders = [_order(yes_price_dollars="0.0200", status="executed")]
        result = _run(transport)
        self.assertEqual(result.halt_code, wr.HaltCode.ORDER_ID_DUPLICATE_CONFLICT)

    def test_wrong_candidate_client_order_id_is_rejected_not_unresolved(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="order-x")]
        transport.exact_orders["order-x"] = _order(order_id="order-x", client_order_id="00000000-0000-0000-0000-000000000000", status="resting")
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_ZERO_MATCH_NEGATIVE_THEOREM_NOT_PROVEN)


class MovingCutoffForwardTests(unittest.TestCase):
    def test_forward_cutoff_movement_is_not_a_gap(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [
            _cutoff(orders_updated_ts="2026-08-11T10:00:00Z"),
            _cutoff(orders_updated_ts="2026-08-11T11:00:00Z"),
        ]
        result = _run(transport)
        self.assertNotEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)


class MovingCutoffCoverageTheoremTests(unittest.TestCase):
    """RA1-PAGE-005 / RA1-TEST-018 Correction 03: monotonicity alone is not
    coverage proof; the theorem requires the traversal's own declared query
    ceiling to have already reached the POST-observed partition boundary."""

    def test_page_c01_pre_equals_post_with_complete_traversals_passes(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        result = _run(transport)  # default cutoff_sequence is PRE==POST
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED)
        payload = json.loads(result.evidence_json)
        self.assertEqual(payload["binding_decision"]["binding_source_class"], "HISTORICAL_ONLY")

    def test_page_c02_cutoff_advances_within_query_ceiling_passes(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [
            _cutoff(orders_updated_ts="2026-08-11T10:00:00Z", trades_created_ts="2026-08-11T10:00:00Z"),
            _cutoff(orders_updated_ts="2026-08-12T10:00:00Z", trades_created_ts="2026-08-12T10:00:00Z"),
        ]
        result = _run(transport)  # evaluation_snapshot_utc = 2026-08-19T23:42:00Z >> post cutoff
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED)

    def test_page_c03_historical_side_proves_coverage_for_historical_only_branch(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [_cutoff(), _cutoff(orders_updated_ts="2026-08-15T00:00:00Z")]
        result = _run(transport)
        self.assertEqual(result.binding_source_class, wr.BindingSourceClass.HISTORICAL_ONLY)
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_RECONCILED)

    def test_page_c04_orders_cutoff_advances_beyond_query_ceiling_is_unobservable(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [
            _cutoff(),
            _cutoff(orders_updated_ts="2026-09-01T00:00:00Z"),  # past evaluation_snapshot_utc
        ]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)
        self.assertEqual(result.halt_code, wr.HaltCode.HISTORY_INTERVAL_UNOBSERVABLE)

    def test_page_c05_cutoff_advances_beyond_ceiling_during_multipage_traversal(self) -> None:
        transport = FakeTransport()
        pages = [
            {"orders": [], "cursor": "c1"},
            {"orders": [_filled_order()], "cursor": ""},
        ]
        calls = {"n": 0}

        def handler(t, request, ordinal):
            if request.operation is wr.HistoricalResolutionOperation.HISTORICAL_ORDERS:
                page = pages[calls["n"]]
                calls["n"] += 1
                return _response(page)
            return FakeTransport._default(t, request, ordinal)

        transport.handler = handler
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [_cutoff(), _cutoff(orders_updated_ts="2026-09-01T00:00:00Z")]
        result = _run(transport)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)

    def test_page_c06_orders_proven_fills_unproven_economics_cannot_claim_complete(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [
            _cutoff(),
            _cutoff(trades_created_ts="2026-09-01T00:00:00Z"),  # FILLS unproven; ORDERS unaffected
        ]
        result = _run(transport)
        # Identity (ORDERS-based) still binds; only economic completeness degrades.
        self.assertEqual(result.bound_order_id, "order-target-001")
        self.assertEqual(result.result_class, wr.ResultClass.READ_POSITIVE_ORDER_BOUND_TERMINAL_ECONOMIC_INCOMPLETE)
        payload = json.loads(result.evidence_json)
        self.assertFalse(payload["economic_reconciliation"]["reconciliation_complete"])

    def test_page_c07_fill_derived_reused_evidence_coverage_unprovable_fails_closed(self) -> None:
        transport = FakeTransport()
        transport.live_fills = [_fill(order_id="order-target-001")]
        transport.exact_orders["order-target-001"] = _filled_order()
        transport.cutoff_sequence = [
            _cutoff(),
            _cutoff(trades_created_ts="2026-09-01T00:00:00Z"),
        ]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)
        # Correction 02 still holds: no repair/second fill traversal was sent.
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.LIVE_FILLS), 1)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_FILLS), 1)

    def test_page_c08_cutoff_regression_fails_closed(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [
            _cutoff(orders_updated_ts="2026-08-11T10:00:00Z"),
            _cutoff(orders_updated_ts="2026-08-11T09:00:00Z"),
        ]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)
        self.assertEqual(result.halt_code, wr.HaltCode.HISTORY_INTERVAL_UNOBSERVABLE)

    def test_page_c09_coverage_failure_issues_zero_repair_gets(self) -> None:
        transport = FakeTransport()
        transport.historical_orders = [_filled_order()]
        transport.historical_fills = [_fill()]
        transport.cutoff_sequence = [_cutoff(), _cutoff(orders_updated_ts="2026-09-01T00:00:00Z")]
        result = _run(transport)
        self.assertEqual(result.result_class, wr.ResultClass.READ_HISTORY_INTERVAL_UNOBSERVABLE)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_ORDERS), 1)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_FILLS), 1)
        self.assertEqual(transport.counts.get(wr.HistoricalResolutionOperation.HISTORICAL_CUTOFF), 2)


class ExternalResearchProvenanceTests(unittest.TestCase):
    def test_external_research_marked_non_controlling(self) -> None:
        transport = FakeTransport()
        result = _run(transport)
        payload = json.loads(result.evidence_json)
        for entry in payload["external_research_provenance"]:
            self.assertEqual(entry["authority_class"], "NON_CONTROLLING_EXTERNAL_RESEARCH")


class ResultTaxonomyTests(unittest.TestCase):
    def test_result_class_has_exactly_22_members(self) -> None:
        self.assertEqual(len(wr.ResultClass), 22)

    def test_binding_source_class_closed_set(self) -> None:
        self.assertEqual(
            {c.value for c in wr.BindingSourceClass},
            {"NONE", "LIVE_PRESENT", "HISTORICAL_ONLY", "LIVE_AND_HISTORICAL_COMPATIBLE", "FILL_DERIVED", "CONFLICT"},
        )

    def test_exact_reread_reason_closed_set(self) -> None:
        self.assertEqual(
            {c.value for c in wr.ExactOrderRereadReason},
            {"NONE", "LIVE_DIRECT_REVALIDATION", "FILL_DERIVED_IDENTITY_BINDING", "NOT_REQUIRED_HISTORICAL_ONLY"},
        )

    def test_route_a_disposition_constants_match_spec(self) -> None:
        self.assertFalse(wr.HISTORICAL_ONLY_DIRECT_BINDING_EXACT_REREAD_REQUIRED)
        self.assertTrue(wr.FILL_DERIVED_CANDIDATE_EXACT_REREAD_REQUIRED)
        self.assertFalse(wr.FILL_DERIVED_POST_BINDING_SECOND_FILL_TRAVERSAL)
        self.assertEqual(wr.THEORETICAL_MAXIMUM_PLANNED_GET_SENDS, 116)
        self.assertEqual(wr.GLOBAL_GET_SEND_MAXIMUM, 116)


if __name__ == "__main__":
    unittest.main()
