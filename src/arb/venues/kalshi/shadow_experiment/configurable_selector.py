"""Task-local, NONCANONICAL, config-driven A4 -> C1 -> B1 -> C2 shadow selector
with funnel diagnostics.

Refactored from the canonical selector ``arb.venues.kalshi.d07_market_selector``
(pinned blob ``46d0e490...``).  Every THRESHOLD / LIMIT / RANKING KNOB is read
from the validated ``ExperimentConfigV1`` passed in; the canonical module's
own experiment constants (page limits, page budgets, retained/shortlist/
finalist counts, close window, ask/quantity limits, depth band, lookback) are
never read by this module.  Every threshold-free, safety-relevant primitive is
REUSED from the bound canonical module rather than copied:

    _get / _parse_json_body (status-200 only, byte cap, strict JSON, no
    duplicate keys, no NaN/Infinity), _fetch_batch_orderbooks (the signed
    GET), _fetch_market, _index_orderbook_items (exact ticker-set equality),
    parse_native_side, _yes_asks_from_no_bids, _depth_within_band, _D,
    _valid_price_ranges, _parse_utc_timestamp, classify_is_provisional,
    rank_a4, rank_c1, _Halt / D07HaltCode / D07Phase, BASE_PATH, PATH_*.

Preserved fail-closed global contradictions (never weakened for diagnostics):
non-object A4 row, duplicate A4 ticker, A4 close time outside the frozen
request window, positive MVE evidence while ``exclude_mve`` is true, A4
incomplete pagination / cursor cycle, C1/C2 ticker-set mismatch, any non-200
or malformed A4/C1/C2 response.  B1 per-ticker window failures remain per-
ticker exclusions exactly as in the canonical selector, EXCEPT that a request
refused by the run's request ceiling is a global halt (stricter than canonical:
a ceiling refusal must never silently drop later B1 candidates).

B1 semantics.  ``require_complete_active_window = true`` reproduces the
canonical rule (only ``COMPLETE_ACTIVE`` windows rank).  ``false`` additionally
admits ``COMPLETE_ZERO`` windows (ranked strictly after every
``COMPLETE_ACTIVE`` window).  ``TRADE_WINDOW_INCOMPLETE`` is NEVER admitted in
either mode (an incomplete window is never treated as complete).  A candidate
selected through the relaxed rule is labelled SHADOW_ONLY and creates no
writer qualification, trade eligibility, release, Gate-D or writer-permit
authority -- nor does any selection made by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from . import constants as C
from .config import ExperimentConfigV1, b1_selection_mode
from .transport import IncompleteResponseBody, RequestCeilingExceeded

A4_REJECTION_ORDER = (
    "rejected_missing_identity",
    "rejected_status",
    "rejected_exchange_index",
    "rejected_market_type",
    "rejected_close_window",
    "rejected_price_ranges",
    "rejected_not_two_sided",
    "rejected_ask_above_limit",
    "rejected_insufficient_ask_qty",
    "rejected_mve",
)

C1_REJECTION_ORDER = (
    "BOOK_OBJECT_MISSING",
    "BOOK_SIDE_UNPARSEABLE",
    "BOOK_ONE_SIDED",
    "BOOK_CROSSED_OR_LOCKED",
    "BOOK_ASK_ABOVE_LIMIT",
    "BOOK_ASK_QTY_INSUFFICIENT",
)

B1_INCOMPLETE_REASONS = (
    "TRANSPORT_FAILURE",
    "INCOMPLETE_RESPONSE_BODY",
    "UNEXPECTED_HTTP_STATUS",
    "RESPONSE_MALFORMED",
    "CURSOR_FIELD_MISSING",
    "PAGE_SCOPE_VIOLATION",
    "CURSOR_INVALID_OR_CYCLE",
    "PAGE_BUDGET_EXHAUSTED",
)

DIAGNOSTIC_LIMITATIONS = (
    "A4 rejected_* counters are EXCLUSIVE first-failure classifications in A4_REJECTION_ORDER; "
    "a4.check_failures_nonexclusive counts every failing check per row.",
    "A4 rejected_close_window counts only missing/unparseable close times: a parseable close time outside "
    "the frozen request window is a preserved global A4_SCOPE_CONTRADICTION halt, not a rejection.",
    "A4 rejected_mve is structurally 0: with exclude_mve=true positive MVE evidence is a preserved global "
    "A4_SCOPE_CONTRADICTION halt; with exclude_mve=false MVE markets are not rejected.",
    "A4 rows without a usable identity are counted in rejected_missing_identity even when later checks also fail.",
    "C1/C2 book rejection reasons are exclusive first-failure classifications in C1_REJECTION_ORDER.",
    "B1 transport_failure_count counts per-ticker transport exceptions (including INCOMPLETE_RESPONSE_BODY); "
    "non-200 statuses and malformed bodies are counted separately in incomplete_reasons.",
    "Counters reflect only phases reached before a halt; unreached phases keep reached=false.",
)


def new_diagnostics(cfg: ExperimentConfigV1) -> dict:
    return {
        "schema": "ShadowSelectorDiagnosticsV1",
        "authority": "DIAGNOSTIC_OBSERVATION_ONLY",
        "run_id": cfg.run_id,
        "b1_selection_mode": b1_selection_mode(cfg),
        "a4": {"reached": False, "pages_requested": 0, "market_rows_seen": 0,
               **{k: 0 for k in A4_REJECTION_ORDER},
               "check_failures_nonexclusive": {k: 0 for k in A4_REJECTION_ORDER},
               "global_contradiction": None,
               "eligible_count": 0, "retained_count": 0},
        "c1": {"reached": False, "requested_count": 0, "rejected_malformed_or_ineligible_book": 0,
               "rejection_reasons": {k: 0 for k in C1_REJECTION_ORDER},
               "eligible_count": 0, "event_duplicate_skipped": 0, "shortlist_count": 0},
        "b1": {"reached": False, "ticker_count": 0, "pages_requested": 0, "complete_active_count": 0,
               "complete_zero_or_inactive_count": 0, "incomplete_count": 0, "transport_failure_count": 0,
               "incomplete_reasons": {k: 0 for k in B1_INCOMPLETE_REASONS},
               "admitted_complete_active": 0, "admitted_complete_zero_shadow_only": 0, "finalist_count": 0},
        "c2": {"reached": False, "finalist_input_count": 0, "market_reject_count": 0,
               "market_reject_reasons": {}, "book_reject_count": 0,
               "book_reject_reasons": {k: 0 for k in C1_REJECTION_ORDER}, "surviving_count": 0},
        "halt": None,
        "limitations": list(DIAGNOSTIC_LIMITATIONS),
    }


# ---------------------------------------------------------------------------
# market-metadata screen (A4 discovery and C2 revalidation)
# ---------------------------------------------------------------------------
def screen_market(sel, market, *, cfg: ExperimentConfigV1, min_close_ts: int, max_close_ts: int):
    """Pure.  Returns ``(eligible, scope_violation, row, failures)``.

    With the baseline configuration ``(eligible, scope_violation, row)`` is
    identical to canonical ``screen_a4_market``.  ``failures`` lists every
    failing check in ``A4_REJECTION_ORDER`` order."""
    scope, a4 = cfg.selector.market_scope, cfg.selector.a4
    D, ZERO, ONE = sel._D, sel.ZERO, sel.ONE
    ticker = market.get("ticker")
    event_ticker = market.get("event_ticker")
    status = market.get("status")
    exchange_index = market.get("exchange_index")
    market_type = market.get("market_type")

    close_dt = sel._parse_utc_timestamp(market.get("close_time"))
    close_ts = int(close_dt.timestamp()) if close_dt is not None else None

    bid, ask = D(market.get("yes_bid_dollars")), D(market.get("yes_ask_dollars"))
    bid_qty = D(market.get("yes_bid_size_fp"))
    ask_qty = D(market.get("yes_ask_size_fp"))
    volume_24h = D(market.get("volume_24h_fp")) or ZERO
    volume = D(market.get("volume_fp")) or ZERO
    open_interest = D(market.get("open_interest_fp")) or ZERO
    liquidity = D(market.get("liquidity_dollars")) or ZERO

    two_sided = (bid is not None and ask is not None and bid_qty is not None and ask_qty is not None
                 and ZERO < bid <= ask < ONE and bid_qty > ZERO and ask_qty > ZERO)
    spread = (ask - bid) if two_sided else None
    min_depth = min(bid_qty, ask_qty) if two_sided else ZERO

    mve_collection_ticker = market.get("mve_collection_ticker")
    mve_selected_legs = market.get("mve_selected_legs")
    mve_positive = mve_collection_ticker not in (None, "") or (
        isinstance(mve_selected_legs, list) and len(mve_selected_legs) > 0)
    mve_violation = scope.exclude_mve and mve_positive
    close_scope_violation = close_ts is not None and (close_ts < min_close_ts or close_ts > max_close_ts)
    scope_violation = close_scope_violation or mve_violation

    failures = []
    if not isinstance(ticker, str) or not ticker or not isinstance(event_ticker, str) or not event_ticker:
        failures.append("rejected_missing_identity")
    if status != scope.status:
        failures.append("rejected_status")
    if type(exchange_index) is not int or isinstance(exchange_index, bool) or exchange_index != scope.exchange_index:
        failures.append("rejected_exchange_index")
    if market_type != scope.market_type:
        failures.append("rejected_market_type")
    if close_ts is None or close_ts < min_close_ts or close_ts > max_close_ts:
        failures.append("rejected_close_window")
    if not sel._valid_price_ranges(market.get("price_ranges")):
        failures.append("rejected_price_ranges")
    if not two_sided:
        failures.append("rejected_not_two_sided")
    if ask is None or ask > a4.max_selected_ask:
        failures.append("rejected_ask_above_limit")
    if ask_qty is None or ask_qty < a4.min_executable_ask_qty:
        failures.append("rejected_insufficient_ask_qty")
    if mve_violation:
        failures.append("rejected_mve")

    row = {"ticker": ticker, "event_ticker": event_ticker, "close_ts": close_ts, "spread": spread,
           "min_depth": min_depth, "volume_24h": volume_24h, "volume": volume, "open_interest": open_interest,
           "liquidity": liquidity, "is_provisional_state": sel.classify_is_provisional(market)}
    return not failures, scope_violation, row, failures


def _close_bounds(cfg: ExperimentConfigV1, anchor: datetime):
    anchor_ts = int(anchor.timestamp())
    cw = cfg.selector.close_window
    return anchor_ts + cw.min_seconds_to_close, anchor_ts + cw.max_seconds_to_close


# ---------------------------------------------------------------------------
# A4 -- complete bounded discovery
# ---------------------------------------------------------------------------
def discover_a4(sel, transport, cfg: ExperimentConfigV1, *, anchor: datetime, diag: dict) -> list:
    a4cfg, scope = cfg.selector.a4, cfg.selector.market_scope
    d = diag["a4"]
    d["reached"] = True
    min_close_ts, max_close_ts = _close_bounds(cfg, anchor)
    cursor, seen_cursors, seen_tickers, eligible_rows = "", set(), set(), []
    phase = sel.D07Phase.A4_DISCOVERY

    for _ in range(a4cfg.max_pages):
        query = [("limit", str(a4cfg.page_limit)), ("min_close_ts", str(min_close_ts)),
                 ("max_close_ts", str(max_close_ts))]
        if scope.exclude_mve:
            query.append(("mve_filter", "exclude"))
        if cursor:
            query.append(("cursor", cursor))
        d["pages_requested"] += 1
        payload = sel._get(transport, path=sel.BASE_PATH + sel.PATH_MARKETS, query=query,
                           headers={"Accept": "application/json"}, phase=phase)
        if not isinstance(payload.get("markets"), list):
            raise sel._Halt(sel.D07HaltCode.RESPONSE_MALFORMED, phase, "missing markets array")
        for market in payload["markets"]:
            d["market_rows_seen"] += 1
            if not isinstance(market, dict):
                d["global_contradiction"] = "NON_OBJECT_MARKET_ROW"
                raise sel._Halt(sel.D07HaltCode.RESPONSE_MALFORMED, phase, "non-object market row")
            ticker = market.get("ticker")
            if isinstance(ticker, str) and ticker:
                if ticker in seen_tickers:
                    d["global_contradiction"] = "DUPLICATE_TICKER"
                    raise sel._Halt(sel.D07HaltCode.A4_DUPLICATE_TICKER, phase, ticker)
                seen_tickers.add(ticker)
            eligible, scope_violation, row, failures = screen_market(
                sel, market, cfg=cfg, min_close_ts=min_close_ts, max_close_ts=max_close_ts)
            if scope_violation:
                d["global_contradiction"] = ("CLOSE_TIME_OUTSIDE_REQUEST_WINDOW"
                                             if "rejected_close_window" in failures
                                             else "MVE_EVIDENCE_CONTRADICTS_EXCLUDE")
                raise sel._Halt(sel.D07HaltCode.A4_SCOPE_CONTRADICTION, phase,
                                row.get("ticker") if isinstance(row.get("ticker"), str) else None)
            if eligible:
                eligible_rows.append(row)
            else:
                d[failures[0]] += 1
                for name in failures:
                    d["check_failures_nonexclusive"][name] += 1
        next_cursor = payload.get("cursor")
        if next_cursor in (None, ""):
            retained = sel.rank_a4(eligible_rows)[:a4cfg.retained_count]
            d["eligible_count"] = len(eligible_rows)
            d["retained_count"] = len(retained)
            return retained
        if not isinstance(next_cursor, str):
            raise sel._Halt(sel.D07HaltCode.RESPONSE_MALFORMED, phase, "cursor was not string/null")
        if next_cursor in seen_cursors:
            raise sel._Halt(sel.D07HaltCode.CURSOR_CYCLE_DETECTED, phase)
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    d["eligible_count"] = len(eligible_rows)
    raise sel._Halt(sel.D07HaltCode.MARKET_DISCOVERY_INCOMPLETE, phase,
                    f"page budget {a4cfg.max_pages} exhausted with cursor remaining")


# ---------------------------------------------------------------------------
# C1 -- authenticated full-orderbook validation + event-diverse shortlist
# ---------------------------------------------------------------------------
def screen_book(sel, item, *, a4_row, cfg: ExperimentConfigV1):
    """Pure.  Returns ``(eligible, row, reason)``; ``(eligible, row)`` equals
    canonical ``screen_c1_orderbook`` under the baseline configuration."""
    a4cfg, band = cfg.selector.a4, cfg.selector.c1.depth_band
    ZERO = sel.ZERO
    base_row = {"ticker": item.get("ticker"), "event_ticker": a4_row["event_ticker"],
                "a4_rank": a4_row["a4_rank"], "spread": None, "volume_24h": a4_row["volume_24h"],
                "min_depth_2c": ZERO, "top_quantity": ZERO, "open_interest": a4_row["open_interest"]}
    orderbook = item.get("orderbook_fp")
    if not isinstance(orderbook, dict):
        return False, base_row, "BOOK_OBJECT_MISSING"
    yes_ok, yes_levels = sel.parse_native_side(orderbook.get("yes_dollars"))
    no_ok, no_levels = sel.parse_native_side(orderbook.get("no_dollars"))
    if not (yes_ok and no_ok):
        return False, base_row, "BOOK_SIDE_UNPARSEABLE"
    yes_asks = sel._yes_asks_from_no_bids(no_levels)
    if not yes_levels or not yes_asks:
        return False, base_row, "BOOK_ONE_SIDED"
    best_bid, best_bid_qty = yes_levels[0]
    best_ask, best_ask_qty = yes_asks[0]
    if best_bid >= best_ask:
        return False, base_row, "BOOK_CROSSED_OR_LOCKED"
    if best_ask > a4cfg.max_selected_ask:
        return False, base_row, "BOOK_ASK_ABOVE_LIMIT"
    if best_ask_qty < a4cfg.min_executable_ask_qty:
        return False, base_row, "BOOK_ASK_QTY_INSUFFICIENT"
    bid_depth = sel._depth_within_band(yes_levels, best_bid, band, is_bid=True)
    ask_depth = sel._depth_within_band(yes_asks, best_ask, band, is_bid=False)
    return True, {**base_row, "spread": best_ask - best_bid, "min_depth_2c": min(bid_depth, ask_depth),
                  "top_quantity": min(best_bid_qty, best_ask_qty)}, None


def build_shortlist(ranked_rows, *, size: int, diag_c1: dict) -> list:
    shortlist, seen_events = [], set()
    for row in ranked_rows:
        if row["event_ticker"] in seen_events:
            diag_c1["event_duplicate_skipped"] += 1
            continue
        seen_events.add(row["event_ticker"])
        shortlist.append(row)
        if len(shortlist) >= size:
            break
    return shortlist


def validate_c1(sel, transport, signer, cfg: ExperimentConfigV1, a4_rows, *, diag: dict) -> list:
    if not a4_rows:
        raise sel._Halt(sel.D07HaltCode.A4_NO_ELIGIBLE_CANDIDATES, sel.D07Phase.A4_DISCOVERY)
    d = diag["c1"]
    d["reached"] = True
    a4_by_ticker = {row["ticker"]: {**row, "a4_rank": i + 1} for i, row in enumerate(a4_rows)}
    requested = list(a4_by_ticker)
    d["requested_count"] = len(requested)
    payload = sel._fetch_batch_orderbooks(transport, signer, requested, phase=sel.D07Phase.C1_VALIDATION)
    items = sel._index_orderbook_items(payload["orderbooks"], requested, phase=sel.D07Phase.C1_VALIDATION,
                                       mismatch_code=sel.D07HaltCode.C1_TICKER_SET_MISMATCH)
    eligible_rows = []
    for ticker in requested:
        eligible, row, reason = screen_book(sel, items[ticker], a4_row=a4_by_ticker[ticker], cfg=cfg)
        if eligible:
            eligible_rows.append(row)
        else:
            d["rejected_malformed_or_ineligible_book"] += 1
            d["rejection_reasons"][reason] += 1
    d["eligible_count"] = len(eligible_rows)
    shortlist = build_shortlist(sel.rank_c1(eligible_rows), size=cfg.selector.c1.event_diverse_shortlist_size,
                                diag_c1=d)
    d["shortlist_count"] = len(shortlist)
    if not shortlist:
        raise sel._Halt(sel.D07HaltCode.C1_NO_ELIGIBLE_SHORTLIST, sel.D07Phase.C1_VALIDATION)
    return shortlist


# ---------------------------------------------------------------------------
# B1 -- exact complete trade-recency window
# ---------------------------------------------------------------------------
def _screen_trades_page(sel, payload, *, ticker: str, min_ts: int, max_ts: int, exclude_block_trades: bool):
    trades = payload.get("trades")
    if not isinstance(trades, list):
        return None
    parsed = []
    for trade in trades:
        if not isinstance(trade, dict) or trade.get("ticker") != ticker:
            return None
        flag = trade.get("is_block_trade")
        if exclude_block_trades and flag is not False:
            return None
        if not exclude_block_trades and type(flag) is not bool:
            return None
        qty = sel._D(trade.get("count_fp"))
        created = sel._parse_utc_timestamp(trade.get("created_time"))
        if qty is None or qty <= sel.ZERO or created is None:
            return None
        created_ts = int(created.timestamp())
        if created_ts < min_ts or created_ts > max_ts:
            return None
        parsed.append({"qty": qty, "created_ts": created_ts})
    return parsed


def fetch_trade_window(sel, transport, cfg: ExperimentConfigV1, *, ticker: str, anchor: datetime, diag_b1: dict):
    """Returns ``(status, window, incomplete_reason, transport_failure)``.
    A request refused by the run request ceiling is a GLOBAL halt."""
    b1 = cfg.selector.b1
    W = sel.B1WindowStatus
    max_ts = int(anchor.timestamp())
    min_ts = max_ts - b1.lookback_seconds
    cursor, seen_cursors = None, set()
    trade_count, total_qty, latest_ts = 0, sel.ZERO, None
    for _ in range(b1.max_pages_per_ticker):
        query = [("limit", str(b1.page_limit)), ("ticker", ticker), ("min_ts", str(min_ts)),
                 ("max_ts", str(max_ts))]
        if b1.exclude_block_trades:
            query.append(("is_block_trade", "false"))
        if cursor:
            query.append(("cursor", cursor))
        diag_b1["pages_requested"] += 1
        try:
            response = transport.get(path=sel.BASE_PATH + sel.PATH_TRADES, query=query,
                                     headers={"Accept": "application/json"})
        except RequestCeilingExceeded:
            raise sel._Halt(sel.D07HaltCode.TRANSPORT_FAILURE, sel.D07Phase.B1_TRADE_RECENCY,
                            "REQUEST_CEILING_EXCEEDED") from None
        except IncompleteResponseBody:
            return W.TRADE_WINDOW_INCOMPLETE, None, "INCOMPLETE_RESPONSE_BODY", True
        except Exception:  # noqa: BLE001 - per-ticker exclusion, exactly as canonical
            return W.TRADE_WINDOW_INCOMPLETE, None, "TRANSPORT_FAILURE", True
        if response.status != 200:
            return W.TRADE_WINDOW_INCOMPLETE, None, "UNEXPECTED_HTTP_STATUS", False
        try:
            payload = sel._parse_json_body(response.body, phase=sel.D07Phase.B1_TRADE_RECENCY)
        except sel._Halt:
            return W.TRADE_WINDOW_INCOMPLETE, None, "RESPONSE_MALFORMED", False
        if "cursor" not in payload:
            return W.TRADE_WINDOW_INCOMPLETE, None, "CURSOR_FIELD_MISSING", False
        parsed = _screen_trades_page(sel, payload, ticker=ticker, min_ts=min_ts, max_ts=max_ts,
                                     exclude_block_trades=b1.exclude_block_trades)
        if parsed is None:
            return W.TRADE_WINDOW_INCOMPLETE, None, "PAGE_SCOPE_VIOLATION", False
        for trade in parsed:
            trade_count += 1
            total_qty += trade["qty"]
            if latest_ts is None or trade["created_ts"] > latest_ts:
                latest_ts = trade["created_ts"]
        next_cursor = payload.get("cursor")
        if next_cursor in (None, ""):
            if trade_count == 0:
                return W.COMPLETE_ZERO, {"trade_count": 0, "total_qty": sel.ZERO, "latest_age": None}, None, False
            return W.COMPLETE_ACTIVE, {"trade_count": trade_count, "total_qty": total_qty,
                                       "latest_age": max_ts - latest_ts}, None, False
        if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
            return W.TRADE_WINDOW_INCOMPLETE, None, "CURSOR_INVALID_OR_CYCLE", False
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return W.TRADE_WINDOW_INCOMPLETE, None, "PAGE_BUDGET_EXHAUSTED", False


def rank_b1(rows) -> list:
    """Canonical B1 ordering, prefixed by an admission-class key that is
    constant (0) in strict mode, so strict ordering equals canonical
    ``rank_b1``; relaxed COMPLETE_ZERO rows always rank after every
    COMPLETE_ACTIVE row."""
    return sorted(rows, key=lambda r: (
        0 if r["b1_window_status"] == "COMPLETE_ACTIVE" else 1,
        r["latest_age"] if r["latest_age"] is not None else 0,
        -r["total_qty"], -r["trade_count"], r["c1_spread"], -r["c1_min_depth_2c"], r["c1_rank"], r["ticker"]))


def evaluate_b1(sel, transport, cfg: ExperimentConfigV1, shortlist, *, anchor: datetime, diag: dict) -> list:
    b1 = cfg.selector.b1
    d = diag["b1"]
    d["reached"] = True
    d["ticker_count"] = len(shortlist)
    W = sel.B1WindowStatus
    rows = []
    for index, c1_row in enumerate(shortlist):
        status, window, reason, transport_failure = fetch_trade_window(
            sel, transport, cfg, ticker=c1_row["ticker"], anchor=anchor, diag_b1=d)
        if status is W.COMPLETE_ACTIVE:
            d["complete_active_count"] += 1
        elif status is W.COMPLETE_ZERO:
            d["complete_zero_or_inactive_count"] += 1
        else:
            d["incomplete_count"] += 1
            d["incomplete_reasons"][reason] += 1
            if transport_failure:
                d["transport_failure_count"] += 1
        admitted = status is W.COMPLETE_ACTIVE or (
            status is W.COMPLETE_ZERO and not b1.require_complete_active_window)
        if not admitted:
            continue
        if status is W.COMPLETE_ACTIVE:
            d["admitted_complete_active"] += 1
        else:
            d["admitted_complete_zero_shadow_only"] += 1
        rows.append({"ticker": c1_row["ticker"], "event_ticker": c1_row["event_ticker"], "c1_rank": index + 1,
                     "c1_spread": c1_row["spread"], "c1_min_depth_2c": c1_row["min_depth_2c"],
                     "latest_age": window["latest_age"], "total_qty": window["total_qty"],
                     "trade_count": window["trade_count"], "b1_window_status": status.value})
    finalists = rank_b1(rows)[:b1.finalist_count]
    d["finalist_count"] = len(finalists)
    if not finalists:
        raise sel._Halt(sel.D07HaltCode.B1_NO_FINALISTS, sel.D07Phase.B1_TRADE_RECENCY)
    return finalists


# ---------------------------------------------------------------------------
# C2 -- immediate fresh revalidation
# ---------------------------------------------------------------------------
def revalidate_c2(sel, transport, signer, cfg: ExperimentConfigV1, finalists, *, anchor: datetime,
                  diag: dict) -> dict:
    if not finalists:
        raise sel._Halt(sel.D07HaltCode.B1_NO_FINALISTS, sel.D07Phase.B1_TRADE_RECENCY)
    d = diag["c2"]
    d["reached"] = True
    d["finalist_input_count"] = len(finalists)
    min_close_ts, max_close_ts = _close_bounds(cfg, anchor)
    tickers = [row["ticker"] for row in finalists]
    markets = {ticker: sel._fetch_market(transport, ticker=ticker) for ticker in tickers}
    payload = sel._fetch_batch_orderbooks(transport, signer, tickers, phase=sel.D07Phase.C2_REVALIDATION)
    items = sel._index_orderbook_items(payload["orderbooks"], tickers, phase=sel.D07Phase.C2_REVALIDATION,
                                       mismatch_code=sel.D07HaltCode.C2_TICKER_SET_MISMATCH)
    candidates = []
    for index, b1_row in enumerate(finalists):
        ticker = b1_row["ticker"]
        eligible, _scope_violation, market_row, failures = screen_market(
            sel, markets[ticker], cfg=cfg, min_close_ts=min_close_ts, max_close_ts=max_close_ts)
        if not eligible or market_row["event_ticker"] != b1_row["event_ticker"]:
            reason = failures[0] if failures else "EVENT_TICKER_CHANGED"
            d["market_reject_count"] += 1
            d["market_reject_reasons"][reason] = d["market_reject_reasons"].get(reason, 0) + 1
            continue
        book_ok, book_row, book_reason = screen_book(sel, items[ticker], a4_row={**market_row, "a4_rank": index},
                                                     cfg=cfg)
        if not book_ok:
            d["book_reject_count"] += 1
            d["book_reject_reasons"][book_reason] += 1
            continue
        candidates.append({"ticker": ticker, "event_ticker": b1_row["event_ticker"], "b1_rank": index + 1,
                           "spread": book_row["spread"], "b1_window_status": b1_row["b1_window_status"]})
    d["surviving_count"] = len(candidates)
    ranked = sorted(candidates, key=lambda r: (r["spread"], r["b1_rank"], r["ticker"]))
    if not ranked:
        raise sel._Halt(sel.D07HaltCode.C2_NO_ELIGIBLE_CANDIDATE, sel.D07Phase.C2_REVALIDATION)
    return ranked[0]


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConfigurableSelectionResult:
    """Exactly one of ``success`` / ``halt``.  ``diagnostics`` always present."""

    success: Optional[dict]
    halt: Optional[dict]
    diagnostics: dict

    def __post_init__(self) -> None:
        if (self.success is None) == (self.halt is None):
            raise ValueError("exactly one of success or halt is required")

    def to_dict(self) -> dict:
        return dict(self.success) if self.success is not None else dict(self.halt)


def select_shadow_ticker(sel, cfg: ExperimentConfigV1, *, transport, signer,
                         now_utc: Callable[[], datetime]) -> ConfigurableSelectionResult:
    """One fresh config-driven A4 -> C1 -> B1 -> C2 pass.  Never reuses a
    prior or historical ticker; no caller-supplied ticker exists."""
    diag = new_diagnostics(cfg)
    try:
        discovery_anchor = now_utc()
        a4_rows = discover_a4(sel, transport, cfg, anchor=discovery_anchor, diag=diag)
        shortlist = validate_c1(sel, transport, signer, cfg, a4_rows, diag=diag)
        finalists = evaluate_b1(sel, transport, cfg, shortlist, anchor=now_utc(), diag=diag)
        selected = revalidate_c2(sel, transport, signer, cfg, finalists, anchor=now_utc(), diag=diag)
    except sel._Halt as halt:
        diag["halt"] = {"code": halt.code.value, "phase": halt.phase.value, "detail": halt.detail}
        return ConfigurableSelectionResult(
            success=None, halt={"status": "HALTED", "code": halt.code.value, "phase": halt.phase.value,
                                "detail": halt.detail}, diagnostics=diag)
    relaxed = selected["b1_window_status"] != "COMPLETE_ACTIVE"
    success = {
        "status": "SUCCEEDED",
        "selected_ticker": selected["ticker"],
        "event_ticker": selected["event_ticker"],
        "discovery_anchor_utc": discovery_anchor.isoformat().replace("+00:00", "Z"),
        "a4_retained_count": len(a4_rows),
        "c1_shortlist_count": len(shortlist),
        "b1_finalist_count": len(finalists),
        "final_spread_dollars": format(selected["spread"], "f"),
        "b1_selection_mode": b1_selection_mode(cfg),
        "selected_b1_window_status": selected["b1_window_status"],
        "selected_via_relaxed_b1": relaxed,
        "selection_authority": C.SHADOW_ONLY_AUTHORITY,
        "writer_qualification": "NONE",
        "trade_eligibility": "NONE",
    }
    return ConfigurableSelectionResult(success=success, halt=None, diagnostics=diag)
