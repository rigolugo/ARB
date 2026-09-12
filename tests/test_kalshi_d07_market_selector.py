"""Tests for the permanent R1-D07 dynamic ticker selector
(`arb.venues.kalshi.d07_market_selector`), including Correction-01
(BLOCK-SEL-01, BLOCK-SEL-02, CORRECTION-SEL-03).

Every test uses an injected fake transport and/or fake signer, or a
synthetic local key file, and a fixed clock. No test performs real network
I/O, reads a real credential, or constructs any request beyond what the fake
transports below simulate.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import ec, rsa as rsa_mod

from arb.venues.kalshi import d07_market_selector as selector
from arb.venues.kalshi.d07_market_selector import (
    BASE_PATH,
    PATH_MARKETS,
    PATH_ORDERBOOKS,
    PATH_TRADES,
    B1WindowStatus,
    D07HaltCode,
    D07Phase,
    D07SelectionResult,
    HttpResponse,
    _Halt,
    build_c1_event_diverse_shortlist,
    classify_is_provisional,
    discover_a4_candidates,
    evaluate_b1,
    fetch_b1_trade_window,
    parse_native_side,
    rank_a4,
    rank_b1,
    rank_c1,
    revalidate_c2,
    screen_a4_market,
    screen_c1_orderbook,
    select_d07_ticker,
    validate_c1,
)

ANCHOR = datetime(2027, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
ZERO = Decimal("0")


def _clock(value: datetime = ANCHOR):
    return lambda: value


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _a4_window():
    min_ts = int(ANCHOR.timestamp()) + selector.MIN_SECONDS_TO_CLOSE
    max_ts = int(ANCHOR.timestamp()) + selector.MAX_SECONDS_TO_CLOSE
    return min_ts, max_ts


# ---------------------------------------------------------------------------
# Fakes.
# ---------------------------------------------------------------------------


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._markets_pages: list[bytes] = []
        self._orderbooks_responses: list[bytes] = []
        self._trades_pages: dict[str, list[bytes]] = {}
        self._market_responses: dict[str, bytes] = {}

    def queue_markets_page(self, payload: dict) -> None:
        self._markets_pages.append(json.dumps(payload).encode("utf-8"))

    def queue_orderbooks_response(self, payload: dict) -> None:
        self._orderbooks_responses.append(json.dumps(payload).encode("utf-8"))

    def queue_trades_page(self, ticker: str, payload: dict) -> None:
        self._trades_pages.setdefault(ticker, []).append(json.dumps(payload).encode("utf-8"))

    def set_market_response(self, ticker: str, payload: dict) -> None:
        self._market_responses[ticker] = json.dumps(payload).encode("utf-8")

    def get(self, *, path, query, headers) -> HttpResponse:
        query_dict: dict[str, list[str]] = {}
        for key, value in query:
            query_dict.setdefault(key, []).append(value)
        self.calls.append({"path": path, "query": query_dict, "headers": dict(headers)})

        if path == BASE_PATH + PATH_MARKETS:
            return HttpResponse(status=200, body=self._markets_pages.pop(0))
        if path == BASE_PATH + PATH_ORDERBOOKS:
            return HttpResponse(status=200, body=self._orderbooks_responses.pop(0))
        if path == BASE_PATH + PATH_TRADES:
            ticker = query_dict["ticker"][0]
            return HttpResponse(status=200, body=self._trades_pages[ticker].pop(0))
        if path.startswith(BASE_PATH + "/markets/"):
            ticker = path.rsplit("/", 1)[-1]
            return HttpResponse(status=200, body=self._market_responses[ticker])
        raise AssertionError(f"unexpected path: {path}")


class FakeSigner:
    def __init__(self, *, key_id: str = "TEST-KEY", signature: str = "FAKE-SIGNATURE-VALUE", forbid: bool = False) -> None:
        self.key_id = key_id
        self.signature = signature
        self.forbid = forbid
        self.calls = 0

    def sign(self, *, method: str, path: str, timestamp_ms_text: str):
        if self.forbid:
            raise AssertionError("signer.sign() must not be called on this path")
        self.calls += 1
        return self.key_id, self.signature


def make_market(
    ticker: str,
    event_ticker: str,
    *,
    seconds_to_close: int = 3600,
    bid: str = "0.40",
    ask: str = "0.42",
    bid_qty: str = "500",
    ask_qty: str = "500",
    status: str = "active",
    exchange_index: int = 0,
    market_type: str = "binary",
    volume_24h: str = "0",
    volume: str = "0",
    open_interest: str = "0",
    liquidity: str = "0",
    price_ranges=None,
    mve_collection_ticker=None,
    mve_selected_legs=None,
    include_is_provisional: bool = False,
    is_provisional=False,
    anchor: datetime = ANCHOR,
) -> dict:
    if price_ranges is None:
        price_ranges = [{"start": "0", "end": "1", "step": "0.01"}]
    market = {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "status": status,
        "exchange_index": exchange_index,
        "market_type": market_type,
        "close_time": _iso(anchor + timedelta(seconds=seconds_to_close)),
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
        "yes_bid_size_fp": bid_qty,
        "yes_ask_size_fp": ask_qty,
        "volume_24h_fp": volume_24h,
        "volume_fp": volume,
        "open_interest_fp": open_interest,
        "liquidity_dollars": liquidity,
        "price_ranges": price_ranges,
    }
    if mve_collection_ticker is not None:
        market["mve_collection_ticker"] = mve_collection_ticker
    if mve_selected_legs is not None:
        market["mve_selected_legs"] = mve_selected_legs
    if include_is_provisional:
        market["is_provisional"] = is_provisional
    return market


def make_orderbook_item(ticker: str, *, yes_levels, no_levels) -> dict:
    return {"ticker": ticker, "orderbook_fp": {"yes_dollars": yes_levels, "no_dollars": no_levels}}


def make_trade(
    ticker: str,
    *,
    count_fp: str,
    created_time: str,
    trade_id: str,
    is_block_trade: bool = False,
) -> dict:
    return {
        "ticker": ticker,
        "trade_id": trade_id,
        "count_fp": count_fp,
        "created_time": created_time,
        "yes_price_dollars": "0.50",
        "no_price_dollars": "0.50",
        "is_block_trade": is_block_trade,
        "taker_outcome_side": "yes",
        "taker_book_side": "yes",
    }


def _write_rsa_key(tmp_path: Path) -> Path:
    key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=ser.Encoding.PEM,
        format=ser.PrivateFormat.PKCS8,
        encryption_algorithm=ser.NoEncryption(),
    )
    path = tmp_path / "synthetic_rsa_key.pem"
    path.write_bytes(pem)
    return path


def _write_ec_key(tmp_path: Path) -> Path:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=ser.Encoding.PEM,
        format=ser.PrivateFormat.PKCS8,
        encryption_algorithm=ser.NoEncryption(),
    )
    path = tmp_path / "synthetic_ec_key.pem"
    path.write_bytes(pem)
    return path


def _clear_credential_env(monkeypatch) -> None:
    monkeypatch.delenv(selector.LEGACY_PRIVATE_KEY_PEM_ENV, raising=False)
    monkeypatch.delenv(selector.API_KEY_ID_ENV, raising=False)
    monkeypatch.delenv(selector.PRIVATE_KEY_PATH_ENV, raising=False)


# ---------------------------------------------------------------------------
# Static non-hardcoding theorem (Spec Sections 4, 10) plus Correction-01
# static evidence requirements (Spec Section 6).
# ---------------------------------------------------------------------------


def _source_path() -> Path:
    return Path(inspect.getfile(selector))


def _source_text() -> str:
    return _source_path().read_text(encoding="utf-8")


def test_no_hardcoded_historical_ticker_literal_in_source():
    tree = ast.parse(_source_text())
    import re as _re

    hits = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _re.fullmatch(r"KX[A-Z0-9._~-]+", node.value)
    ]
    assert hits == []


def test_no_frozen_candidate_payload_constants_in_source():
    text = _source_text()
    for forbidden in ("A4_CANDIDATES", "C1_SHORTLIST", "B1_FINALISTS"):
        assert forbidden not in text


def test_no_write_capable_http_method_in_source():
    text = _source_text()
    for verb in ('"POST"', '"PUT"', '"PATCH"', '"DELETE"', "'POST'", "'PUT'", "'PATCH'", "'DELETE'"):
        assert verb not in text


def test_no_production_host_used_to_build_a_request():
    text = _source_text()
    for host in selector.PRODUCTION_REST_HOSTS:
        assert text.count(host) == 1


def test_cli_has_no_ticker_candidate_or_market_override():
    parser = selector._build_cli_parser()
    for forbidden in ("--ticker", "--candidate", "--market"):
        with pytest.raises(SystemExit):
            parser.parse_args([forbidden, "X"])
    parsed = parser.parse_args(["--json"])
    assert parsed.json is True


def test_source_evidence_b1_sends_is_block_trade_false():
    text = _source_text()
    assert '("is_block_trade", "false")' in text


def test_source_evidence_a4_global_halt_paths_present():
    text = _source_text()
    assert "A4_DUPLICATE_TICKER" in text
    assert "A4_SCOPE_CONTRADICTION" in text
    assert "non-object market row" in text


def test_source_evidence_legacy_pem_rejected_and_deterministic_parse_mapping():
    text = _source_text()
    assert "LEGACY_PRIVATE_KEY_PEM_ENV" in text
    assert "CREDENTIAL_SOURCE_AMBIGUOUS" in text
    assert "CREDENTIAL_INVALID" in text


# ---------------------------------------------------------------------------
# A4 -- eligibility, ranking, is_provisional, exchange index.
# ---------------------------------------------------------------------------


def test_is_provisional_absent_is_not_exposed():
    market = make_market("T1", "E1")
    assert "is_provisional" not in market
    assert classify_is_provisional(market) == "NOT_EXPOSED"


def test_is_provisional_present_true_false_and_unknown():
    assert classify_is_provisional({"is_provisional": True}) == "TRUE"
    assert classify_is_provisional({"is_provisional": False}) == "FALSE"
    assert classify_is_provisional({"is_provisional": "weird"}) == "UNKNOWN"


def test_a4_exchange_index_controls_selection():
    min_ts, max_ts = _a4_window()
    eligible, scope, _ = screen_a4_market(make_market("T1", "E1", exchange_index=0), min_close_ts=min_ts, max_close_ts=max_ts)
    assert eligible is True and scope is False

    ineligible, scope2, _ = screen_a4_market(make_market("T2", "E2", exchange_index=1), min_close_ts=min_ts, max_close_ts=max_ts)
    assert ineligible is False and scope2 is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "closed"),
        ("market_type", "scalar"),
        ("ask", "0.9000"),
        ("ask_qty", "0.5"),
    ],
)
def test_a4_eligibility_rejects_out_of_bound_fields(field, value):
    min_ts, max_ts = _a4_window()
    eligible, scope, _ = screen_a4_market(make_market("T1", "E1", **{field: value}), min_close_ts=min_ts, max_close_ts=max_ts)
    assert eligible is False
    assert scope is False  # ordinary exclusion, not a scope/integrity contradiction


def test_a4_close_time_outside_window_is_scope_violation():
    min_ts, max_ts = _a4_window()
    too_soon_eligible, too_soon_scope, _ = screen_a4_market(
        make_market("T1", "E1", seconds_to_close=60), min_close_ts=min_ts, max_close_ts=max_ts
    )
    assert too_soon_eligible is False
    assert too_soon_scope is True

    too_late_eligible, too_late_scope, _ = screen_a4_market(
        make_market("T2", "E2", seconds_to_close=selector.MAX_SECONDS_TO_CLOSE + 3600),
        min_close_ts=min_ts,
        max_close_ts=max_ts,
    )
    assert too_late_eligible is False
    assert too_late_scope is True


def test_a4_unparseable_close_time_is_ordinary_exclusion_not_scope_violation():
    min_ts, max_ts = _a4_window()
    market = make_market("T1", "E1")
    market["close_time"] = "not-a-timestamp"
    eligible, scope, _ = screen_a4_market(market, min_close_ts=min_ts, max_close_ts=max_ts)
    assert eligible is False
    assert scope is False


def test_a4_mve_contradiction_is_scope_violation():
    min_ts, max_ts = _a4_window()
    collection_eligible, collection_scope, _ = screen_a4_market(
        make_market("T1", "E1", mve_collection_ticker="COLLECTION-1"), min_close_ts=min_ts, max_close_ts=max_ts
    )
    assert collection_eligible is False
    assert collection_scope is True

    legs_eligible, legs_scope, _ = screen_a4_market(
        make_market("T2", "E2", mve_selected_legs=["A", "B"]), min_close_ts=min_ts, max_close_ts=max_ts
    )
    assert legs_eligible is False
    assert legs_scope is True

    clean_eligible, clean_scope, _ = screen_a4_market(make_market("T3", "E3"), min_close_ts=min_ts, max_close_ts=max_ts)
    assert clean_eligible is True
    assert clean_scope is False


def test_a4_ranking_tie_breaks_exact_order():
    rows = [
        {"ticker": "B", "event_ticker": "E1", "spread": Decimal("0.02"), "min_depth": Decimal("10"),
         "volume_24h": Decimal("5"), "volume": Decimal("5"), "open_interest": Decimal("5"), "liquidity": Decimal("5")},
        {"ticker": "A", "event_ticker": "E2", "spread": Decimal("0.01"), "min_depth": Decimal("1"),
         "volume_24h": Decimal("1"), "volume": Decimal("1"), "open_interest": Decimal("1"), "liquidity": Decimal("1")},
        {"ticker": "C", "event_ticker": "E3", "spread": Decimal("0.01"), "min_depth": Decimal("50"),
         "volume_24h": Decimal("1"), "volume": Decimal("1"), "open_interest": Decimal("1"), "liquidity": Decimal("1")},
    ]
    ranked = rank_a4(rows)
    assert [r["ticker"] for r in ranked] == ["C", "A", "B"]


# ---------------------------------------------------------------------------
# A4 discovery pipeline: query shape, pagination, cursor cycle, page cap,
# and the Correction-01 (COR-02) global fail-closed integrity halts.
# ---------------------------------------------------------------------------


def test_a4_query_shape_frozen_window_and_no_status_param():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [], "cursor": ""})
    discover_a4_candidates(transport, anchor=ANCHOR)

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["path"] == BASE_PATH + PATH_MARKETS
    assert call["query"]["limit"] == [str(selector.A4_PAGE_LIMIT)]
    assert call["query"]["mve_filter"] == ["exclude"]
    expected_min = str(int(ANCHOR.timestamp()) + selector.MIN_SECONDS_TO_CLOSE)
    expected_max = str(int(ANCHOR.timestamp()) + selector.MAX_SECONDS_TO_CLOSE)
    assert call["query"]["min_close_ts"] == [expected_min]
    assert call["query"]["max_close_ts"] == [expected_max]
    assert "status" not in call["query"]
    assert "cursor" not in call["query"]


def test_a4_complete_pagination_across_multiple_pages():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [make_market("T1", "E1")], "cursor": "PAGE2"})
    transport.queue_markets_page({"markets": [make_market("T2", "E2")], "cursor": ""})
    rows = discover_a4_candidates(transport, anchor=ANCHOR)
    assert {row["ticker"] for row in rows} == {"T1", "T2"}
    assert len(transport.calls) == 2
    assert "cursor" not in transport.calls[0]["query"]
    assert transport.calls[1]["query"]["cursor"] == ["PAGE2"]


def test_a4_cursor_cycle_is_detected_and_halts():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [], "cursor": "LOOP"})
    transport.queue_markets_page({"markets": [], "cursor": "LOOP"})
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.CURSOR_CYCLE_DETECTED
    assert excinfo.value.phase is D07Phase.A4_DISCOVERY


def test_a4_page_budget_exhaustion_fails_closed():
    transport = FakeTransport()
    for i in range(selector.A4_MAX_PAGES):
        transport.queue_markets_page({"markets": [], "cursor": f"CURSOR-{i}"})
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.MARKET_DISCOVERY_INCOMPLETE


def test_a4_zero_eligible_candidates_produces_empty_list_not_a_fallback():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [], "cursor": ""})
    rows = discover_a4_candidates(transport, anchor=ANCHOR)
    assert rows == []


def test_a4_response_malformed_missing_markets_array():
    transport = FakeTransport()
    transport.queue_markets_page({"cursor": ""})
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.RESPONSE_MALFORMED


def test_duplicate_json_key_is_rejected():
    transport = FakeTransport()
    transport._markets_pages.append(b'{"markets": [], "cursor": "", "cursor": ""}')
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.RESPONSE_MALFORMED


def test_non_finite_json_constant_is_rejected():
    transport = FakeTransport()
    transport._markets_pages.append(b'{"markets": [], "cursor": "", "extra": NaN}')
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.RESPONSE_MALFORMED


def test_response_too_large_halts():
    transport = FakeTransport()
    oversized = json.dumps({"markets": [], "cursor": "", "pad": "x" * (selector.MAX_RESPONSE_BYTES + 1)}).encode()
    transport._markets_pages.append(oversized)
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.RESPONSE_TOO_LARGE


# --- COR-02: global fail-closed discovery-integrity halts ---


def test_a4_non_object_market_row_halts():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": ["not-a-dict"], "cursor": ""})
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.RESPONSE_MALFORMED


def test_a4_duplicate_ticker_in_same_page_halts():
    transport = FakeTransport()
    transport.queue_markets_page(
        {"markets": [make_market("T1", "E1"), make_market("T1", "E2")], "cursor": ""}
    )
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.A4_DUPLICATE_TICKER


def test_a4_duplicate_ticker_across_pages_halts():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [make_market("T1", "E1")], "cursor": "PAGE2"})
    transport.queue_markets_page({"markets": [make_market("T1", "E1")], "cursor": ""})
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.A4_DUPLICATE_TICKER


def test_a4_close_time_scope_contradiction_halts_discovery():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [make_market("T1", "E1", seconds_to_close=60)], "cursor": ""})
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.A4_SCOPE_CONTRADICTION
    assert excinfo.value.phase is D07Phase.A4_DISCOVERY


def test_a4_mve_collection_scope_contradiction_halts_discovery():
    transport = FakeTransport()
    transport.queue_markets_page(
        {"markets": [make_market("T1", "E1", mve_collection_ticker="COLLECTION-1")], "cursor": ""}
    )
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.A4_SCOPE_CONTRADICTION


def test_a4_mve_legs_scope_contradiction_halts_discovery():
    transport = FakeTransport()
    transport.queue_markets_page(
        {"markets": [make_market("T1", "E1", mve_selected_legs=["A"])], "cursor": ""}
    )
    with pytest.raises(_Halt) as excinfo:
        discover_a4_candidates(transport, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.A4_SCOPE_CONTRADICTION


def test_a4_ordinary_ineligibility_remains_exclusion_not_halt():
    transport = FakeTransport()
    transport.queue_markets_page(
        {
            "markets": [
                make_market("INACTIVE", "E1", status="closed"),
                make_market("WRONG-INDEX", "E2", exchange_index=1),
                make_market("GOOD", "E3"),
            ],
            "cursor": "",
        }
    )
    rows = discover_a4_candidates(transport, anchor=ANCHOR)
    assert [row["ticker"] for row in rows] == ["GOOD"]


def test_a4_normal_multi_page_discovery_and_ranking_unaffected_by_correction():
    transport = FakeTransport()
    transport.queue_markets_page(
        {"markets": [make_market("T1", "E1", volume_24h="100")], "cursor": "PAGE2"}
    )
    transport.queue_markets_page(
        {"markets": [make_market("T2", "E2", volume_24h="10")], "cursor": ""}
    )
    rows = discover_a4_candidates(transport, anchor=ANCHOR)
    assert [row["ticker"] for row in rows] == ["T1", "T2"]


# ---------------------------------------------------------------------------
# C1 -- native parsing, derived ask, event diversity, ranking, ticker-set equality.
# ---------------------------------------------------------------------------


def test_c1_native_yes_no_parsing_and_derived_ask():
    ok, levels = parse_native_side([["0.40", "100"], ["0.39", "50"]])
    assert ok is True
    assert levels == [(Decimal("0.40"), Decimal("100")), (Decimal("0.39"), Decimal("50"))]

    a4_row = {"event_ticker": "E1", "a4_rank": 1, "volume_24h": Decimal("10"), "open_interest": Decimal("10")}
    item = make_orderbook_item("T1", yes_levels=[["0.40", "100"]], no_levels=[["0.55", "80"]])
    eligible, row = screen_c1_orderbook(item, a4_row=a4_row)
    assert eligible is True
    assert row["spread"] == Decimal("0.45") - Decimal("0.40")


def test_c1_rejects_crossed_book():
    a4_row = {"event_ticker": "E1", "a4_rank": 1, "volume_24h": Decimal("0"), "open_interest": Decimal("0")}
    item = make_orderbook_item("T1", yes_levels=[["0.70", "10"]], no_levels=[["0.35", "10"]])
    eligible, _ = screen_c1_orderbook(item, a4_row=a4_row)
    assert eligible is False


def test_c1_rejects_ask_above_max_or_qty_below_min():
    a4_row = {"event_ticker": "E1", "a4_rank": 1, "volume_24h": Decimal("0"), "open_interest": Decimal("0")}
    item = make_orderbook_item("T1", yes_levels=[["0.10", "10"]], no_levels=[["0.15", "10"]])
    eligible, _ = screen_c1_orderbook(item, a4_row=a4_row)
    assert eligible is False


def test_c1_ranking_tie_breaks_exact_order():
    rows = [
        {"ticker": "B", "event_ticker": "E1", "a4_rank": 2, "spread": Decimal("0.01"), "volume_24h": ZERO,
         "min_depth_2c": Decimal("5"), "top_quantity": Decimal("5"), "open_interest": Decimal("5")},
        {"ticker": "A", "event_ticker": "E2", "a4_rank": 1, "spread": Decimal("0.01"), "volume_24h": Decimal("1"),
         "min_depth_2c": Decimal("1"), "top_quantity": Decimal("1"), "open_interest": Decimal("1")},
    ]
    ranked = rank_c1(rows)
    assert [r["ticker"] for r in ranked] == ["A", "B"]


def test_c1_event_diverse_shortlist_keeps_first_per_event():
    ranked_rows = [
        {"ticker": "T1", "event_ticker": "E1"},
        {"ticker": "T2", "event_ticker": "E1"},
        {"ticker": "T3", "event_ticker": "E2"},
    ]
    shortlist = build_c1_event_diverse_shortlist(ranked_rows)
    assert [r["ticker"] for r in shortlist] == ["T1", "T3"]


def test_c1_dynamic_a4_consumption_and_exact_requested_set():
    transport = FakeTransport()
    a4_rows = [
        {"ticker": "T1", "event_ticker": "E1", "spread": Decimal("0.01"), "min_depth": Decimal("10"),
         "volume_24h": Decimal("1"), "volume": Decimal("1"), "open_interest": Decimal("1"), "liquidity": Decimal("1")},
        {"ticker": "T2", "event_ticker": "E2", "spread": Decimal("0.01"), "min_depth": Decimal("10"),
         "volume_24h": Decimal("1"), "volume": Decimal("1"), "open_interest": Decimal("1"), "liquidity": Decimal("1")},
    ]
    transport.queue_orderbooks_response(
        {
            "orderbooks": [
                make_orderbook_item("T1", yes_levels=[["0.40", "100"]], no_levels=[["0.55", "100"]]),
                make_orderbook_item("T2", yes_levels=[["0.30", "100"]], no_levels=[["0.65", "100"]]),
            ]
        }
    )
    signer = FakeSigner()
    shortlist = validate_c1(transport, signer, a4_rows)
    assert signer.calls == 1
    assert transport.calls[0]["query"]["tickers"] == ["T1", "T2"]
    assert {row["ticker"] for row in shortlist} == {"T1", "T2"}


def test_c1_ticker_set_mismatch_halts():
    transport = FakeTransport()
    a4_rows = [
        {"ticker": "T1", "event_ticker": "E1", "spread": Decimal("0.01"), "min_depth": Decimal("10"),
         "volume_24h": Decimal("1"), "volume": Decimal("1"), "open_interest": Decimal("1"), "liquidity": Decimal("1")},
    ]
    transport.queue_orderbooks_response(
        {"orderbooks": [make_orderbook_item("UNREQUESTED", yes_levels=[["0.4", "1"]], no_levels=[["0.6", "1"]])]}
    )
    with pytest.raises(_Halt) as excinfo:
        validate_c1(transport, FakeSigner(), a4_rows)
    assert excinfo.value.code is D07HaltCode.C1_TICKER_SET_MISMATCH


def test_c1_no_eligible_shortlist_halts():
    transport = FakeTransport()
    a4_rows = [
        {"ticker": "T1", "event_ticker": "E1", "spread": Decimal("0.01"), "min_depth": Decimal("10"),
         "volume_24h": Decimal("1"), "volume": Decimal("1"), "open_interest": Decimal("1"), "liquidity": Decimal("1")},
    ]
    transport.queue_orderbooks_response({"orderbooks": [make_orderbook_item("T1", yes_levels=[], no_levels=[])]})
    with pytest.raises(_Halt) as excinfo:
        validate_c1(transport, FakeSigner(), a4_rows)
    assert excinfo.value.code is D07HaltCode.C1_NO_ELIGIBLE_SHORTLIST


def test_a4_no_eligible_candidates_halts_before_any_c1_call():
    with pytest.raises(_Halt) as excinfo:
        validate_c1(FakeTransport(), FakeSigner(forbid=True), [])
    assert excinfo.value.code is D07HaltCode.A4_NO_ELIGIBLE_CANDIDATES


# ---------------------------------------------------------------------------
# B1 -- exact ticker queries, frozen window, complete/incomplete, ranking,
# and the Correction-01 (COR-01) non-block query requirement.
# ---------------------------------------------------------------------------


def test_b1_exact_query_shape_including_is_block_trade_false():
    transport = FakeTransport()
    transport.queue_trades_page("T1", {"trades": [], "cursor": ""})
    fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)

    call = transport.calls[0]
    assert call["path"] == BASE_PATH + PATH_TRADES
    assert call["query"]["ticker"] == ["T1"]
    assert call["query"]["is_block_trade"] == ["false"]
    expected_max = str(int(ANCHOR.timestamp()))
    expected_min = str(int(ANCHOR.timestamp()) - selector.B1_LOOKBACK_SECONDS)
    assert call["query"]["max_ts"] == [expected_max]
    assert call["query"]["min_ts"] == [expected_min]


def test_b1_continuation_page_also_includes_is_block_trade_false():
    transport = FakeTransport()
    transport.queue_trades_page("T1", {"trades": [], "cursor": "PAGE2"})
    transport.queue_trades_page("T1", {"trades": [], "cursor": ""})
    fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)

    assert len(transport.calls) == 2
    assert transport.calls[0]["query"]["is_block_trade"] == ["false"]
    assert "cursor" not in transport.calls[0]["query"]
    assert transport.calls[1]["query"]["is_block_trade"] == ["false"]
    assert transport.calls[1]["query"]["cursor"] == ["PAGE2"]


def test_b1_is_block_trade_value_is_exact_lowercase_string_not_alternate_spelling():
    transport = FakeTransport()
    transport.queue_trades_page("T1", {"trades": [], "cursor": ""})
    fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)
    values = transport.calls[0]["query"]["is_block_trade"]
    assert values == ["false"]
    assert values != ["False"]
    assert values != ["true"]
    assert values != ["1"]


def test_b1_complete_active_window():
    transport = FakeTransport()
    transport.queue_trades_page(
        "T1",
        {
            "trades": [
                make_trade("T1", count_fp="10", created_time=_iso(ANCHOR - timedelta(minutes=30)), trade_id="A"),
                make_trade("T1", count_fp="5", created_time=_iso(ANCHOR - timedelta(minutes=10)), trade_id="B"),
            ],
            "cursor": "",
        },
    )
    status, window = fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)
    assert status is B1WindowStatus.COMPLETE_ACTIVE
    assert window["trade_count"] == 2
    assert window["total_qty"] == Decimal("15")
    assert window["latest_age"] == 600


def test_b1_complete_zero_trade_window_is_excluded_not_ranked():
    transport = FakeTransport()
    transport.queue_trades_page("T1", {"trades": [], "cursor": ""})
    status, window = fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)
    assert status is B1WindowStatus.COMPLETE_ZERO
    assert window["trade_count"] == 0


def test_b1_cursor_cycle_is_incomplete_not_complete():
    transport = FakeTransport()
    transport.queue_trades_page("T1", {"trades": [], "cursor": "LOOP"})
    transport.queue_trades_page("T1", {"trades": [], "cursor": "LOOP"})
    status, window = fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)
    assert status is B1WindowStatus.TRADE_WINDOW_INCOMPLETE
    assert window is None


def test_b1_scope_violation_ticker_mismatch_is_incomplete():
    transport = FakeTransport()
    transport.queue_trades_page(
        "T1",
        {"trades": [make_trade("OTHER", count_fp="1", created_time=_iso(ANCHOR), trade_id="X")], "cursor": ""},
    )
    status, window = fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)
    assert status is B1WindowStatus.TRADE_WINDOW_INCOMPLETE
    assert window is None


def test_b1_returned_block_trade_row_still_makes_window_incomplete():
    transport = FakeTransport()
    transport.queue_trades_page(
        "T1",
        {"trades": [make_trade("T1", count_fp="1", created_time=_iso(ANCHOR), trade_id="X", is_block_trade=True)], "cursor": ""},
    )
    status, window = fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)
    assert status is B1WindowStatus.TRADE_WINDOW_INCOMPLETE
    assert window is None
    # The request itself still asked for non-block trades only.
    assert transport.calls[0]["query"]["is_block_trade"] == ["false"]


def test_b1_never_treats_partial_page_as_complete_when_page_budget_exhausted():
    transport = FakeTransport()
    for i in range(selector.B1_MAX_PAGES_PER_TICKER):
        transport.queue_trades_page("T1", {"trades": [], "cursor": f"C{i}"})
    status, window = fetch_b1_trade_window(transport, ticker="T1", anchor=ANCHOR)
    assert status is B1WindowStatus.TRADE_WINDOW_INCOMPLETE
    assert window is None


def test_b1_ranking_tie_breaks_exact_order():
    rows = [
        {"ticker": "B", "event_ticker": "E1", "c1_rank": 1, "c1_spread": Decimal("0.01"), "c1_min_depth_2c": Decimal("1"),
         "latest_age": 100, "total_qty": Decimal("1"), "trade_count": 1},
        {"ticker": "A", "event_ticker": "E2", "c1_rank": 2, "c1_spread": Decimal("0.01"), "c1_min_depth_2c": Decimal("1"),
         "latest_age": 50, "total_qty": Decimal("1"), "trade_count": 1},
    ]
    ranked = rank_b1(rows)
    assert [r["ticker"] for r in ranked] == ["A", "B"]


def test_b1_dynamic_c1_consumption_and_no_finalists_halts():
    transport = FakeTransport()
    c1_shortlist = [{"ticker": "T1", "event_ticker": "E1", "spread": Decimal("0.01"), "min_depth_2c": Decimal("1")}]
    transport.queue_trades_page("T1", {"trades": [], "cursor": ""})
    with pytest.raises(_Halt) as excinfo:
        evaluate_b1(transport, c1_shortlist, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.B1_NO_FINALISTS


def test_b1_evaluates_multiple_shortlist_entries_and_ranks_them():
    transport = FakeTransport()
    c1_shortlist = [
        {"ticker": "T1", "event_ticker": "E1", "spread": Decimal("0.01"), "min_depth_2c": Decimal("1")},
        {"ticker": "T2", "event_ticker": "E2", "spread": Decimal("0.01"), "min_depth_2c": Decimal("1")},
    ]
    transport.queue_trades_page(
        "T1",
        {"trades": [make_trade("T1", count_fp="5", created_time=_iso(ANCHOR - timedelta(minutes=5)), trade_id="A")], "cursor": ""},
    )
    transport.queue_trades_page(
        "T2",
        {"trades": [make_trade("T2", count_fp="5", created_time=_iso(ANCHOR - timedelta(minutes=50)), trade_id="B")], "cursor": ""},
    )
    finalists = evaluate_b1(transport, c1_shortlist, anchor=ANCHOR)
    assert [row["ticker"] for row in finalists] == ["T1", "T2"]


# ---------------------------------------------------------------------------
# C2 -- fresh revalidation and final selection.
# ---------------------------------------------------------------------------


def test_c2_dynamic_b1_consumption_fresh_revalidation_and_final_ranking():
    transport = FakeTransport()
    b1_finalists = [
        {"ticker": "T1", "event_ticker": "E1"},
        {"ticker": "T2", "event_ticker": "E2"},
    ]
    transport.set_market_response("T1", {"market": make_market("T1", "E1", bid="0.30", ask="0.33")})
    transport.set_market_response("T2", {"market": make_market("T2", "E2", bid="0.30", ask="0.31")})
    transport.queue_orderbooks_response(
        {
            "orderbooks": [
                make_orderbook_item("T1", yes_levels=[["0.30", "10"]], no_levels=[["0.67", "10"]]),
                make_orderbook_item("T2", yes_levels=[["0.30", "10"]], no_levels=[["0.69", "10"]]),
            ]
        }
    )
    selected = revalidate_c2(transport, FakeSigner(), b1_finalists, anchor=ANCHOR)
    assert selected["ticker"] == "T2"


def test_c2_no_eligible_candidate_halts():
    transport = FakeTransport()
    b1_finalists = [{"ticker": "T1", "event_ticker": "E1"}]
    transport.set_market_response("T1", {"market": make_market("T1", "E1", status="closed")})
    transport.queue_orderbooks_response(
        {"orderbooks": [make_orderbook_item("T1", yes_levels=[["0.30", "10"]], no_levels=[["0.65", "10"]])]}
    )
    with pytest.raises(_Halt) as excinfo:
        revalidate_c2(transport, FakeSigner(), b1_finalists, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.C2_NO_ELIGIBLE_CANDIDATE


def test_c2_ticker_set_mismatch_on_market_fetch_halts():
    transport = FakeTransport()
    b1_finalists = [{"ticker": "T1", "event_ticker": "E1"}]
    transport.set_market_response("T1", {"market": make_market("WRONG", "E1")})
    with pytest.raises(_Halt) as excinfo:
        revalidate_c2(transport, FakeSigner(), b1_finalists, anchor=ANCHOR)
    assert excinfo.value.code is D07HaltCode.C2_TICKER_SET_MISMATCH


# ---------------------------------------------------------------------------
# COR-03: deterministic credential-source/parse closure.
# ---------------------------------------------------------------------------


def test_credential_legacy_pem_present_halts_before_file_read(monkeypatch, tmp_path):
    _clear_credential_env(monkeypatch)
    monkeypatch.setenv(
        selector.LEGACY_PRIVATE_KEY_PEM_ENV,
        "-----BEGIN PRIVATE KEY-----\nSYNTHETIC\n-----END PRIVATE KEY-----",
    )
    monkeypatch.setenv(selector.API_KEY_ID_ENV, "KEYID")
    monkeypatch.setenv(selector.PRIVATE_KEY_PATH_ENV, str(tmp_path / "does-not-exist.pem"))
    signer = selector.EnvironmentRsaSigner()
    with pytest.raises(_Halt) as excinfo:
        signer.sign(method="GET", path="/x", timestamp_ms_text="1")
    assert excinfo.value.code is D07HaltCode.CREDENTIAL_SOURCE_AMBIGUOUS


def test_credential_missing_key_id_or_path_halts(monkeypatch):
    _clear_credential_env(monkeypatch)
    signer = selector.EnvironmentRsaSigner()
    with pytest.raises(_Halt) as excinfo:
        signer.sign(method="GET", path="/x", timestamp_ms_text="1")
    assert excinfo.value.code is D07HaltCode.CREDENTIAL_MISSING


def test_credential_unreadable_path_halts_deterministically(monkeypatch, tmp_path):
    _clear_credential_env(monkeypatch)
    monkeypatch.setenv(selector.API_KEY_ID_ENV, "KEYID")
    monkeypatch.setenv(selector.PRIVATE_KEY_PATH_ENV, str(tmp_path / "missing.pem"))
    signer = selector.EnvironmentRsaSigner()
    with pytest.raises(_Halt) as excinfo:
        signer.sign(method="GET", path="/x", timestamp_ms_text="1")
    assert excinfo.value.code is D07HaltCode.CREDENTIAL_INVALID


def test_credential_malformed_pem_halts_deterministically_not_a_raw_exception(monkeypatch, tmp_path):
    _clear_credential_env(monkeypatch)
    bad = tmp_path / "bad.pem"
    bad.write_bytes(b"this is not a real PEM key")
    monkeypatch.setenv(selector.API_KEY_ID_ENV, "KEYID")
    monkeypatch.setenv(selector.PRIVATE_KEY_PATH_ENV, str(bad))
    signer = selector.EnvironmentRsaSigner()
    with pytest.raises(_Halt) as excinfo:
        signer.sign(method="GET", path="/x", timestamp_ms_text="1")
    assert excinfo.value.code is D07HaltCode.CREDENTIAL_INVALID


def test_credential_non_rsa_key_halts_deterministically(monkeypatch, tmp_path):
    _clear_credential_env(monkeypatch)
    ec_path = _write_ec_key(tmp_path)
    monkeypatch.setenv(selector.API_KEY_ID_ENV, "KEYID")
    monkeypatch.setenv(selector.PRIVATE_KEY_PATH_ENV, str(ec_path))
    signer = selector.EnvironmentRsaSigner()
    with pytest.raises(_Halt) as excinfo:
        signer.sign(method="GET", path="/x", timestamp_ms_text="1")
    assert excinfo.value.code is D07HaltCode.CREDENTIAL_INVALID


def test_credential_valid_rsa_key_resolves_and_signs_and_is_cached(monkeypatch, tmp_path):
    _clear_credential_env(monkeypatch)
    rsa_path = _write_rsa_key(tmp_path)
    monkeypatch.setenv(selector.API_KEY_ID_ENV, "KEYID")
    monkeypatch.setenv(selector.PRIVATE_KEY_PATH_ENV, str(rsa_path))
    signer = selector.EnvironmentRsaSigner()

    key_id, signature = signer.sign(method="GET", path="/x", timestamp_ms_text="1")
    assert key_id == "KEYID"
    assert isinstance(signature, str) and len(signature) > 0

    # Remove the key file; a cached signer must not need to reread it.
    rsa_path.unlink()
    key_id_2, signature_2 = signer.sign(method="GET", path="/y", timestamp_ms_text="2")
    assert key_id_2 == "KEYID"
    assert isinstance(signature_2, str) and len(signature_2) > 0


def test_credential_halt_detail_never_contains_secret_or_path(monkeypatch, tmp_path):
    _clear_credential_env(monkeypatch)
    marker_path = tmp_path / "SECRET-MARKER-PATH-9f3a.pem"
    marker_path.write_bytes(b"SECRET-PEM-BYTES-MARKER-1234")
    monkeypatch.setenv(selector.API_KEY_ID_ENV, "KEYID-MARKER-abcd")
    monkeypatch.setenv(selector.PRIVATE_KEY_PATH_ENV, str(marker_path))
    signer = selector.EnvironmentRsaSigner()
    with pytest.raises(_Halt) as excinfo:
        signer.sign(method="GET", path="/x", timestamp_ms_text="1")
    detail = excinfo.value.detail or ""
    assert "SECRET-MARKER-PATH-9f3a" not in detail
    assert "SECRET-PEM-BYTES-MARKER" not in detail
    assert "KEYID-MARKER-abcd" not in detail


# ---------------------------------------------------------------------------
# Credential deferral and secret safety (end-to-end).
# ---------------------------------------------------------------------------


def test_credential_resolution_not_entered_during_pure_public_a4_failure():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [], "cursor": ""})
    result = select_d07_ticker(transport=transport, signer=FakeSigner(forbid=True), now_utc=_clock())
    assert result.halt is not None
    assert result.halt.code is D07HaltCode.A4_NO_ELIGIBLE_CANDIDATES


def test_secrets_never_appear_in_result_repr():
    transport = FakeTransport()
    a4_market = make_market("T1", "E1")
    transport.queue_markets_page({"markets": [a4_market], "cursor": ""})
    transport.queue_orderbooks_response({"orderbooks": [make_orderbook_item("T1", yes_levels=[], no_levels=[])]})
    signer = FakeSigner(signature="TOP-SECRET-SIGNATURE-MARKER")
    result = select_d07_ticker(transport=transport, signer=signer, now_utc=_clock())
    assert signer.calls == 1
    assert "TOP-SECRET-SIGNATURE-MARKER" not in repr(result)
    assert "TOP-SECRET-SIGNATURE-MARKER" not in str(result)


# ---------------------------------------------------------------------------
# End-to-end: deterministic success, no stale fallback, fresh A4 flows to C1.
# ---------------------------------------------------------------------------


def _wire_full_success_pipeline(transport: FakeTransport) -> None:
    transport.queue_markets_page(
        {
            "markets": [
                make_market("SIM-ALPHA-1", "SIM-ALPHA", bid="0.40", ask="0.42", volume_24h="100"),
                make_market("SIM-BETA-1", "SIM-BETA", bid="0.20", ask="0.21", volume_24h="50"),
            ],
            "cursor": "",
        }
    )
    transport.queue_orderbooks_response(
        {
            "orderbooks": [
                make_orderbook_item("SIM-ALPHA-1", yes_levels=[["0.40", "500"]], no_levels=[["0.58", "500"]]),
                make_orderbook_item("SIM-BETA-1", yes_levels=[["0.20", "500"]], no_levels=[["0.79", "500"]]),
            ]
        }
    )
    transport.queue_trades_page(
        "SIM-ALPHA-1",
        {"trades": [make_trade("SIM-ALPHA-1", count_fp="10", created_time=_iso(ANCHOR - timedelta(minutes=5)), trade_id="A")], "cursor": ""},
    )
    transport.queue_trades_page(
        "SIM-BETA-1",
        {"trades": [make_trade("SIM-BETA-1", count_fp="10", created_time=_iso(ANCHOR - timedelta(minutes=5)), trade_id="B")], "cursor": ""},
    )
    transport.set_market_response("SIM-ALPHA-1", {"market": make_market("SIM-ALPHA-1", "SIM-ALPHA", bid="0.40", ask="0.42")})
    transport.set_market_response("SIM-BETA-1", {"market": make_market("SIM-BETA-1", "SIM-BETA", bid="0.20", ask="0.21")})
    transport.queue_orderbooks_response(
        {
            "orderbooks": [
                make_orderbook_item("SIM-ALPHA-1", yes_levels=[["0.40", "500"]], no_levels=[["0.58", "500"]]),
                make_orderbook_item("SIM-BETA-1", yes_levels=[["0.20", "500"]], no_levels=[["0.79", "500"]]),
            ]
        }
    )


def test_successful_synthetic_end_to_end_pipeline():
    transport = FakeTransport()
    _wire_full_success_pipeline(transport)
    result = select_d07_ticker(transport=transport, signer=FakeSigner(), now_utc=_clock())
    assert result.success is not None
    assert result.success.selected_ticker in {"SIM-ALPHA-1", "SIM-BETA-1"}


def test_regression_fresh_a4_output_not_historical_constants_flows_to_c1():
    transport = FakeTransport()
    _wire_full_success_pipeline(transport)
    select_d07_ticker(transport=transport, signer=FakeSigner(), now_utc=_clock())
    orderbooks_call = next(c for c in transport.calls if c["path"] == BASE_PATH + PATH_ORDERBOOKS)
    requested_tickers = set(orderbooks_call["query"]["tickers"])
    assert requested_tickers == {"SIM-ALPHA-1", "SIM-BETA-1"}
    for ticker in requested_tickers:
        assert not ticker.startswith("KX")


def test_regression_b1_queries_include_is_block_trade_false_end_to_end():
    transport = FakeTransport()
    _wire_full_success_pipeline(transport)
    select_d07_ticker(transport=transport, signer=FakeSigner(), now_utc=_clock())
    trade_calls = [c for c in transport.calls if c["path"] == BASE_PATH + PATH_TRADES]
    assert trade_calls
    for call in trade_calls:
        assert call["query"]["is_block_trade"] == ["false"]


def test_deterministic_behavior_under_injected_clock_and_transport():
    transport_a = FakeTransport()
    _wire_full_success_pipeline(transport_a)
    result_a = select_d07_ticker(transport=transport_a, signer=FakeSigner(), now_utc=_clock())

    transport_b = FakeTransport()
    _wire_full_success_pipeline(transport_b)
    result_b = select_d07_ticker(transport=transport_b, signer=FakeSigner(), now_utc=_clock())

    assert result_a.success is not None and result_b.success is not None
    assert result_a.success.selected_ticker == result_b.success.selected_ticker
    assert result_a.success.discovery_anchor_utc == result_b.success.discovery_anchor_utc


def test_no_stale_or_historical_fallback_when_a4_has_zero_output():
    transport = FakeTransport()
    transport.queue_markets_page({"markets": [], "cursor": ""})
    result = select_d07_ticker(transport=transport, signer=FakeSigner(forbid=True), now_utc=_clock())
    assert result.halt is not None
    assert result.halt.code is D07HaltCode.A4_NO_ELIGIBLE_CANDIDATES
    assert result.success is None


def test_selection_result_requires_exactly_one_of_success_or_halt():
    with pytest.raises(selector.D07Error):
        D07SelectionResult()
    with pytest.raises(selector.D07Error):
        D07SelectionResult(
            success=selector.D07SelectionSuccess(
                selected_ticker="T1",
                event_ticker="E1",
                discovery_anchor_utc="2027-01-01T00:00:00Z",
                a4_eligible_count=1,
                c1_shortlist_count=1,
                b1_finalist_count=1,
                final_spread_dollars="0.01",
            ),
            halt=selector.D07SelectionHalt(code=D07HaltCode.B1_NO_FINALISTS, phase=D07Phase.B1_TRADE_RECENCY),
        )
