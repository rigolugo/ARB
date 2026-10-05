"""Phase A: one config-driven selector invocation, then exactly four GET reads
(market, orderbook, positions, orders) producing one sanitized snapshot.

Only GET surfaces are reachable.  Credentials are used only through the
canonical selector ``EnvironmentRsaSigner`` (path-based key; the legacy PEM
environment variable must be absent).  No temporary PEM bridge, no ledger,
no authority namespace, no writer/release object is ever constructed.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from . import constants as C
from .config import ExperimentConfigV1
from .configurable_selector import select_shadow_ticker
from .transport import IncompleteResponseBody

SNAPSHOT_SCHEMA = "ShadowExperimentSnapshotSanitizedV1"

_LIVE_READ_FAILED_HALT_CODES = (
    "TRANSPORT_FAILURE", "UNEXPECTED_HTTP_STATUS", "RESPONSE_MALFORMED", "RESPONSE_TOO_LARGE",
    "CREDENTIAL_MISSING", "CREDENTIAL_SOURCE_AMBIGUOUS", "CREDENTIAL_INVALID", "CURSOR_CYCLE_DETECTED",
    "MARKET_DISCOVERY_INCOMPLETE")


class CaptureTerminal(RuntimeError):
    def __init__(self, classification: str, detail: str = "") -> None:
        super().__init__(classification)
        self.classification = classification
        self.detail = detail


def _halt_to_terminal(halt_detail: Optional[str], default: str) -> str:
    if halt_detail and "INCOMPLETE_RESPONSE_BODY" in halt_detail:
        return "LIVE_READ_INCOMPLETE"
    return default


def _signed_headers(signer, path: str) -> dict:
    ts = str(int(time.time() * 1000))
    key_id, signature = signer.sign(method="GET", path=path, timestamp_ms_text=ts)
    return {"Accept": "application/json", "KALSHI-ACCESS-KEY": key_id,
            "KALSHI-ACCESS-SIGNATURE": signature, "KALSHI-ACCESS-TIMESTAMP": ts}


def _call(sel, fn, *args, **kwargs):
    """Run one canonical selector helper; map its typed halt / our transport
    exceptions to a fixed terminal classification (never retried)."""
    try:
        return fn(*args, **kwargs)
    except sel._Halt as halt:
        raise CaptureTerminal(_halt_to_terminal(halt.detail, "LIVE_READ_FAILED"),
                              f"{halt.code.value}:{halt.phase.value}") from None
    except IncompleteResponseBody:
        raise CaptureTerminal("LIVE_READ_INCOMPLETE", "INCOMPLETE_RESPONSE_BODY") from None


def _private_read(mods, transport, signer, operation, ticker: str) -> dict:
    sel, runner = mods["selector"], mods["runner"]
    prepared = runner.prepare_runner_operation_request(
        operation, path_parameters={}, ticker=ticker, request_ordinal=1,
        subaccount=C.OBSERVATION_SUBACCOUNT, exchange_index=C.OBSERVATION_EXCHANGE_INDEX)
    if prepared.method != "GET" or prepared.body is not None:
        raise CaptureTerminal("PRECONDITION_FAILED", "non-GET prepared request")
    headers = _signed_headers(signer, prepared.signed_path_without_query)
    return _call(sel, sel._get, transport, path=prepared.full_path, query=list(prepared.query),
                 headers=headers, phase=sel.D07Phase.C2_REVALIDATION)


def _positions_observation(mods, payload: dict, ticker: str) -> dict:
    runner = mods["runner"]
    rows = payload.get("market_positions")
    cursor = payload.get("cursor")
    if type(rows) is not list or type(payload.get("event_positions")) is not list or type(cursor) is not str:
        return {"state": "UNKNOWN", "reason": "POSITIONS_SCHEMA_UNEXPECTED", "observed_keys": sorted(payload)}
    if cursor != "":
        return {"state": "UNKNOWN", "reason": "POSITIONS_PAGINATION_INCOMPLETE", "row_count": len(rows)}
    values = []
    for row in rows:
        if (type(row) is not dict or row.get("ticker") != ticker
                or row.get("subaccount") != C.OBSERVATION_SUBACCOUNT
                or row.get("exchange_index") != C.OBSERVATION_EXCHANGE_INDEX
                or type(row.get("subaccount")) is not int or type(row.get("exchange_index")) is not int):
            return {"state": "UNKNOWN", "reason": "POSITION_ROW_SCOPE_UNEXPECTED", "row_count": len(rows)}
        try:
            values.append(runner._position_count_from_row(row))
        except runner.RunnerError:
            return {"state": "UNKNOWN", "reason": "POSITION_ROW_SCHEMA_UNEXPECTED", "row_count": len(rows)}
    if not values or all(v == 0 for v in values):
        return {"state": "OBSERVED_FLAT", "row_count": len(rows),
                "position_count_fp": [format(v, "f") for v in values]}
    return {"state": "OBSERVED_NONZERO_SIGN_CONVENTION_UNBOUND", "row_count": len(rows),
            "position_count_fp": [format(v, "f") for v in values]}


def _orders_observation(mods, payload: dict, ticker: str) -> dict:
    runner = mods["runner"]
    rows = payload.get("orders")
    cursor = payload.get("cursor")
    if type(rows) is not list or (cursor is not None and type(cursor) is not str):
        return {"state": "UNKNOWN", "reason": "ORDERS_SCHEMA_UNEXPECTED", "observed_keys": sorted(payload)}
    if cursor not in (None, ""):
        return {"state": "UNKNOWN", "reason": "ORDERS_PAGINATION_INCOMPLETE", "row_count": len(rows)}
    resting = []
    for row in rows:
        try:
            order = runner._working_order_from_raw(
                row, expected_ticker=ticker, expected_subaccount=C.OBSERVATION_SUBACCOUNT,
                expected_exchange_index=C.OBSERVATION_EXCHANGE_INDEX)
        except runner.RunnerError:
            return {"state": "UNKNOWN", "reason": "ORDER_ROW_UNEXPECTED", "row_count": len(rows)}
        if order is not None:
            # account identifiers (order ids) are deliberately not retained
            resting.append({"outcome_side": order.outcome_side, "yes_price": format(order.yes_price, "f"),
                            "remaining_quantity": format(order.remaining_quantity, "f")})
    return {"state": "OBSERVED_NONE_RESTING" if not resting else "OBSERVED_RESTING_OWNERSHIP_UNKNOWN",
            "row_count": len(rows), "resting": resting}


def run_live_capture(mods: dict, cfg: ExperimentConfigV1, transport, signer, *,
                     select_fn: Optional[Callable] = None,
                     now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict:
    sel, runner = mods["selector"], mods["runner"]
    select = select_fn or select_shadow_ticker
    selector_invocations = 0

    # ---- exactly one selector invocation ----------------------------------
    transport.phase = "SELECTOR"
    selector_invocations += 1
    if selector_invocations > C.SELECTOR_INVOCATION_MAX:
        raise CaptureTerminal("PRECONDITION_FAILED", "selector bound")
    result = select(sel, cfg, transport=transport, signer=signer, now_utc=now_utc)
    base = {"selector_invocations": selector_invocations, "selector_result": result.to_dict(),
            "selector_diagnostics": result.diagnostics}
    if result.success is None:
        halt = result.halt
        code = _halt_to_terminal(halt.get("detail"), "SELECTOR_NO_CANDIDATE")
        if halt["code"] in _LIVE_READ_FAILED_HALT_CODES and code != "LIVE_READ_INCOMPLETE":
            code = "LIVE_READ_FAILED"
        return {**base, "terminal": code, "snapshot": None}
    ticker = result.success["selected_ticker"]

    try:
        # ---- exactly four snapshot reads ---------------------------------
        transport.phase = "SNAPSHOT_MARKET"
        market = _call(sel, sel._fetch_market, transport, ticker=ticker)
        transport.phase = "SNAPSHOT_ORDERBOOK"
        book_payload = _call(sel, sel._fetch_batch_orderbooks, transport, signer, [ticker],
                             phase=sel.D07Phase.C2_REVALIDATION)
        captured_at = now_utc().isoformat().replace("+00:00", "Z")
        transport.phase = "SNAPSHOT_POSITIONS"
        positions = _private_read(mods, transport, signer, runner.RunnerOperation.GET_POSITIONS, ticker)
        transport.phase = "SNAPSHOT_ORDERS"
        orders = _private_read(mods, transport, signer, runner.RunnerOperation.GET_ORDERS, ticker)
    except CaptureTerminal as term:
        return {**base, "terminal": term.classification, "terminal_detail": term.detail, "snapshot": None}

    items = [i for i in book_payload["orderbooks"] if isinstance(i, dict) and i.get("ticker") == ticker]
    if len(items) != 1 or not isinstance(items[0].get("orderbook_fp"), dict):
        return {**base, "terminal": "LIVE_READ_FAILED", "terminal_detail": "ORDERBOOK_ITEM_UNEXPECTED",
                "snapshot": None}
    ob = items[0]["orderbook_fp"]
    yes_ok, yes_levels = sel.parse_native_side(ob.get("yes_dollars"))
    no_ok, no_levels = sel.parse_native_side(ob.get("no_dollars"))
    book = {"yes_dollars_ascending": [[format(p, "f"), format(q, "f")] for p, q in sorted(yes_levels)],
            "no_dollars_ascending": [[format(p, "f"), format(q, "f")] for p, q in sorted(no_levels)],
            "parse_ok": bool(yes_ok and no_ok)}
    book["book_identity_sha256"] = hashlib.sha256(
        json.dumps(book, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "run_id": cfg.run_id,
        "market_ticker": ticker,
        "captured_at_utc": captured_at,
        "selection_authority": C.SHADOW_ONLY_AUTHORITY,
        "selected_b1_window_status": result.success["selected_b1_window_status"],
        "selected_via_relaxed_b1": result.success["selected_via_relaxed_b1"],
        "market": {k: market.get(k) for k in (
            "ticker", "event_ticker", "status", "market_type", "exchange_index", "close_time",
            "yes_bid_dollars", "yes_ask_dollars", "price_ranges")},
        "orderbook": book,
        "positions_observation": _positions_observation(mods, positions, ticker),
        "orders_observation": _orders_observation(mods, orders, ticker),
        "observation_scope": {"subaccount": C.OBSERVATION_SUBACCOUNT, "exchange_index": C.OBSERVATION_EXCHANGE_INDEX},
    }
    return {**base, "terminal": None, "snapshot": snapshot}


def inventory_from_snapshot(ev_module, snapshot: dict):
    pos = snapshot["positions_observation"]["state"]
    orders = snapshot["orders_observation"]["state"]
    if pos == "OBSERVED_FLAT" and orders == "OBSERVED_NONE_RESTING":
        return ev_module.ShadowInventoryInput(
            ev_module.INVENTORY_KNOWN_FLAT_OBSERVED, Decimal("0"), ev_module.SLOTS_ABSENT_OBSERVED,
            "venue positions page complete with no nonzero row; orders page complete with no resting order "
            "(venue observation, not ledger economic truth)")
    slots = ev_module.SLOTS_ABSENT_OBSERVED if orders == "OBSERVED_NONE_RESTING" else ev_module.SLOTS_UNKNOWN
    return ev_module.ShadowInventoryInput(
        ev_module.INVENTORY_UNKNOWN, None, slots, f"positions={pos}; orders={orders}")
