"""Permanent, reusable R1-D07 Kalshi Demo dynamic ticker selector.

Implements `KALSHI_DEMO_R1_D07_PERMANENT_DYNAMIC_TICKER_SELECTOR_SPEC_01.md`
as corrected by
`KALSHI_DEMO_R1_D07_PERMANENT_DYNAMIC_TICKER_SELECTOR_SPEC_01_CORRECTION_01.md`
for task `R1-D07_PERMANENT_DYNAMIC_TICKER_SELECTOR_IMPLEMENTATION_01_CORRECTION_01`.
This is a fresh-base correction of the Marco-BLOCKed predecessor candidate
`44b56b5b18498f75f52ad5ac41a5ecfb043ec33c`; that candidate is
NONCANONICAL_REFERENCE_CONTENT_SEED_ONLY and is not Git ancestry of this file.

Every invocation performs one fresh run of the accepted four-phase pipeline:

    A4 (complete bounded discovery)
    -> C1 (current authenticated full-orderbook validation)
    -> B1 (exact complete six-hour non-block trade recency)
    -> C2 (immediate fresh revalidation)
    -> exactly one selected ticker, or a deterministic fail-closed halt.

There is no caller-supplied ticker, candidate, or market override anywhere in
this module, and no frozen candidate set of any kind is embedded in this
source. Every candidate at every phase is produced by parsing a live (or, in
tests, injected-fake) Demo API response observed during that same call to
`select_d07_ticker`.

Correction-01 changes (BLOCK-SEL-01, BLOCK-SEL-02, CORRECTION-SEL-03)
-----------------------------------------------------------------------

* COR-01: every B1 trade-window page request -- including cursor
  continuations -- now sends the exact query parameter
  `is_block_trade=false` (the literal lowercase string `"false"`, never a
  boolean, `"True"`, `"1"`, or any other spelling), matching the accepted
  historical non-block-window contract. A returned row that nonetheless
  states `is_block_trade` is not exactly `False` still makes that ticker's
  window `TRADE_WINDOW_INCOMPLETE` -- the request-scope correction does not
  relax response validation.
* COR-02: A4 discovery restores the accepted predecessor's universe-
  integrity theorem. A non-object market row, a duplicate nonempty market
  ticker (within a page or across pages), a returned close time outside the
  exact frozen request window, or positive MVE evidence
  (`mve_collection_ticker`/`mve_selected_legs`) contradicting the request's
  `mve_filter=exclude` are all now global, deterministic A4 halts -- not
  silently skipped/excluded rows. Ordinary local eligibility failures
  (inactive status, wrong market-level exchange index, non-binary type, an
  invalid/crossed book, invalid price ranges, insufficient depth) remain
  ordinary per-candidate exclusions, never halts; `screen_a4_market`
  distinguishes the two by returning an explicit `scope_violation` flag
  alongside `eligible`.
* COR-03: `EnvironmentRsaSigner._resolve` now rejects the legacy/ambiguous
  `KALSHI_DEMO_PRIVATE_KEY_PEM` credential source outright (a deterministic
  halt before any file read or signing attempt) and maps every private-key
  read/parse failure -- unreadable file, malformed PEM, an unsupported or
  encrypted key under this contract, or a non-RSA key -- to a stable,
  secret-safe halt rather than letting a raw `OSError`/`ValueError`/
  `TypeError`/cryptography exception escape.

Network/credential boundary (Spec Section 9)
---------------------------------------------

* The only reachable REST origin is the Kalshi Demo origin
  (`DEMO_HOST`/`DEMO_PORT`); `PRODUCTION_REST_HOSTS` is asserted disjoint from
  it at import time and is never used to construct a request.
* The only HTTP method ever issued is `GET` -- no POST/PUT/PATCH/DELETE
  request is constructed anywhere in this module.
* `RealDemoTransport` issues exactly one request per call, with no retry
  loop and no redirect-following logic (a 3xx response is simply rejected as
  an unexpected status, exactly like any other non-200 status).
* `RealDemoTransport` never consults `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` or
  any other ambient proxy environment variable -- `http.client` connects
  directly to the pinned Demo host/port, which is the exact behavior
  `requests.Session(trust_env=False)` is used elsewhere in this codebase to
  obtain.
* Every response body is read through a hard byte cap
  (`MAX_RESPONSE_BYTES`); a body at or beyond the cap is a deterministic
  `RESPONSE_TOO_LARGE` halt, never a partial silent truncation treated as
  complete.
* Malformed/non-UTF-8/non-JSON/non-object bodies, duplicate JSON object
  keys, and non-finite JSON constants (`NaN`/`Infinity`/`-Infinity`) are all
  rejected deterministically as `RESPONSE_MALFORMED`.
* Pagination cursor cycles (A4, and per-ticker B1 trade pagination) are
  detected and halted rather than looped forever.
* Public phases (A4; the per-finalist `GET /markets/{ticker}` and
  `GET /markets/trades` reads in B1/C2) never construct or require a signer.
  Credential/key resolution happens only inside `EnvironmentRsaSigner._resolve`,
  which is reached for the first time only from the C1 batch-orderbook
  fetch -- never during a pure-public A4/B1 failure path.
* No secret value (API key ID, private key material, signature bytes) is
  ever placed in a halt's `detail`, in a success result field, or in any
  exception message raised by this module.

Public interface
----------------

    select_d07_ticker(transport=None, signer=None, now_utc=...) -> D07SelectionResult

    python -m arb.venues.kalshi.d07_market_selector

The CLI exposes no ticker/candidate/market override of any kind -- see
`_build_cli_parser`.
"""

from __future__ import annotations

import argparse
import base64
import enum
import http.client
import json
import os
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import (
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

__all__ = [
    "DEMO_HOST",
    "DEMO_PORT",
    "DEMO_ORIGIN",
    "BASE_PATH",
    "D07Phase",
    "D07HaltCode",
    "B1WindowStatus",
    "D07Error",
    "D07TypeError",
    "HttpResponse",
    "Transport",
    "Signer",
    "RealDemoTransport",
    "EnvironmentRsaSigner",
    "D07SelectionSuccess",
    "D07SelectionHalt",
    "D07SelectionResult",
    "classify_is_provisional",
    "screen_a4_market",
    "rank_a4",
    "discover_a4_candidates",
    "parse_native_side",
    "screen_c1_orderbook",
    "rank_c1",
    "build_c1_event_diverse_shortlist",
    "validate_c1",
    "fetch_b1_trade_window",
    "rank_b1",
    "evaluate_b1",
    "revalidate_c2",
    "select_d07_ticker",
]

# ---------------------------------------------------------------------------
# Exact Demo origin identities (Spec Section 9).
# ---------------------------------------------------------------------------

DEMO_HOST = "external-api.demo.kalshi.co"
DEMO_PORT = 443
DEMO_ORIGIN = f"https://{DEMO_HOST}"
BASE_PATH = "/trade-api/v2"

PATH_MARKETS = "/markets"
PATH_ORDERBOOKS = "/markets/orderbooks"
PATH_TRADES = "/markets/trades"

PRODUCTION_REST_HOSTS = frozenset(
    {"external-api.kalshi.com", "api.elections.kalshi.com"}
)
assert DEMO_HOST not in PRODUCTION_REST_HOSTS

API_KEY_ID_ENV = "KALSHI_DEMO_API_KEY_ID"
PRIVATE_KEY_PATH_ENV = "KALSHI_DEMO_PRIVATE_KEY_PATH"
# COR-03: forbidden legacy/ambiguous credential source. Its mere presence
# (nonempty) halts credential resolution before any file read or signing.
LEGACY_PRIVATE_KEY_PEM_ENV = "KALSHI_DEMO_PRIVATE_KEY_PEM"

# ---------------------------------------------------------------------------
# Exact accepted thresholds (Spec Sections 5-8).
# ---------------------------------------------------------------------------

MIN_SECONDS_TO_CLOSE = 30 * 60
MAX_SECONDS_TO_CLOSE = 72 * 60 * 60

A4_PAGE_LIMIT = 1000
A4_MAX_PAGES = 200
A4_RETAINED_COUNT = 100

C1_EVENT_DIVERSE_SHORTLIST_SIZE = 20
DEPTH_BAND = Decimal("0.02")

B1_LOOKBACK_SECONDS = 6 * 60 * 60
B1_PAGE_LIMIT = 1000
B1_MAX_PAGES_PER_TICKER = 20
B1_FINALIST_COUNT = 5

MAX_SELECTED_ASK = Decimal("0.8000")
MIN_EXECUTABLE_ASK_QTY = Decimal("1.00")

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
REQUEST_TIMEOUT_S = 20.0

ZERO = Decimal("0")
ONE = Decimal("1")


# ---------------------------------------------------------------------------
# Closed enums.
# ---------------------------------------------------------------------------


class D07Phase(enum.StrEnum):
    A4_DISCOVERY = "A4_DISCOVERY"
    C1_VALIDATION = "C1_VALIDATION"
    B1_TRADE_RECENCY = "B1_TRADE_RECENCY"
    C2_REVALIDATION = "C2_REVALIDATION"


class D07HaltCode(enum.StrEnum):
    MARKET_DISCOVERY_INCOMPLETE = "MARKET_DISCOVERY_INCOMPLETE"
    A4_NO_ELIGIBLE_CANDIDATES = "A4_NO_ELIGIBLE_CANDIDATES"
    A4_DUPLICATE_TICKER = "A4_DUPLICATE_TICKER"
    A4_SCOPE_CONTRADICTION = "A4_SCOPE_CONTRADICTION"
    C1_TICKER_SET_MISMATCH = "C1_TICKER_SET_MISMATCH"
    C1_NO_ELIGIBLE_SHORTLIST = "C1_NO_ELIGIBLE_SHORTLIST"
    B1_NO_FINALISTS = "B1_NO_FINALISTS"
    C2_TICKER_SET_MISMATCH = "C2_TICKER_SET_MISMATCH"
    C2_NO_ELIGIBLE_CANDIDATE = "C2_NO_ELIGIBLE_CANDIDATE"
    CURSOR_CYCLE_DETECTED = "CURSOR_CYCLE_DETECTED"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    RESPONSE_MALFORMED = "RESPONSE_MALFORMED"
    UNEXPECTED_HTTP_STATUS = "UNEXPECTED_HTTP_STATUS"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    CREDENTIAL_MISSING = "CREDENTIAL_MISSING"
    CREDENTIAL_SOURCE_AMBIGUOUS = "CREDENTIAL_SOURCE_AMBIGUOUS"
    CREDENTIAL_INVALID = "CREDENTIAL_INVALID"


class B1WindowStatus(enum.StrEnum):
    """Per-ticker B1 six-hour trade-window classification (Spec Section 7).
    Only `COMPLETE_ACTIVE` rows are ever ranked; `COMPLETE_ZERO` and
    `TRADE_WINDOW_INCOMPLETE` are both excluded, and an incomplete window is
    never treated as if it were complete."""

    COMPLETE_ACTIVE = "COMPLETE_ACTIVE"
    COMPLETE_ZERO = "COMPLETE_ZERO"
    TRADE_WINDOW_INCOMPLETE = "TRADE_WINDOW_INCOMPLETE"


class D07Error(ValueError):
    """Base class for this module's own typed validation failures. Never
    carries a secret value."""


class D07TypeError(D07Error):
    """Raised when an object at a public boundary is not of the exact
    expected runtime type."""


class _Halt(Exception):
    """Internal control-flow exception carrying the exact halt code, phase,
    and a secret-safe detail string. Caught only by `select_d07_ticker`."""

    def __init__(
        self,
        code: D07HaltCode,
        phase: D07Phase,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.phase = phase
        self.detail = detail


# ---------------------------------------------------------------------------
# Transport / Signer protocols and the one real (network-capable) transport.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes


class Transport(Protocol):
    def get(
        self,
        *,
        path: str,
        query: Sequence[Tuple[str, str]],
        headers: Mapping[str, str],
    ) -> HttpResponse:
        """Issue exactly one GET request and return its status/body. Tests
        inject a fake implementation; production uses `RealDemoTransport`."""
        ...


class Signer(Protocol):
    def sign(
        self, *, method: str, path: str, timestamp_ms_text: str
    ) -> Tuple[str, str]:
        """Returns `(api_key_id, base64_signature)`. Tests inject a fake
        implementation that never touches the real environment or a real
        private key."""
        ...


def _read_bounded(response: "http.client.HTTPResponse") -> bytes:
    """Reads at most `MAX_RESPONSE_BYTES + 1` bytes regardless of how large
    the server claims or attempts to send the body, so a malicious or
    misbehaving server cannot force unbounded memory use. The `+1` lets the
    caller deterministically detect and reject an oversized body rather than
    silently truncating it and treating the truncated prefix as complete."""

    limit = MAX_RESPONSE_BYTES + 1
    chunks: List[bytes] = []
    total = 0
    while total <= MAX_RESPONSE_BYTES:
        chunk = response.read(min(65536, limit - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


class RealDemoTransport:
    """The one network-capable `Transport` implementation. Connects only to
    the pinned Demo host/port over TLS, issues exactly one GET per call, and
    never consults ambient proxy environment variables (see module
    docstring)."""

    def __init__(self, *, timeout_s: float = REQUEST_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s

    def get(
        self,
        *,
        path: str,
        query: Sequence[Tuple[str, str]],
        headers: Mapping[str, str],
    ) -> HttpResponse:
        if not path.startswith(BASE_PATH):
            raise D07Error("path must start with the exact Demo base path")
        full_path = path if not query else f"{path}?{urlencode(list(query))}"
        context = ssl.create_default_context()
        connection = http.client.HTTPSConnection(
            DEMO_HOST, DEMO_PORT, timeout=self._timeout_s, context=context
        )
        try:
            connection.request("GET", full_path, headers=dict(headers))
            response = connection.getresponse()
            body = _read_bounded(response)
            return HttpResponse(status=response.status, body=body)
        finally:
            connection.close()


class EnvironmentRsaSigner:
    """Default production `Signer`. Resolves `KALSHI_DEMO_API_KEY_ID` and the
    private key file named by `KALSHI_DEMO_PRIVATE_KEY_PATH` lazily -- not at
    construction, and not until `sign()` is first called (which happens only
    from the C1 authenticated batch-orderbook fetch).

    COR-03: the legacy/ambiguous `KALSHI_DEMO_PRIVATE_KEY_PEM` source is
    rejected outright if present/nonempty, before any file is opened. Every
    key read/parse failure -- unreadable file, malformed PEM, an unsupported
    or encrypted key, or a non-RSA key -- maps to a stable `CREDENTIAL_INVALID`
    halt rather than letting a raw exception escape."""

    def __init__(self) -> None:
        self._key_id: Optional[str] = None
        self._private_key: Optional[rsa.RSAPrivateKey] = None

    def _resolve(self) -> None:
        if self._private_key is not None:
            return

        if os.environ.get(LEGACY_PRIVATE_KEY_PEM_ENV):
            raise _Halt(D07HaltCode.CREDENTIAL_SOURCE_AMBIGUOUS, D07Phase.C1_VALIDATION)

        key_id = os.environ.get(API_KEY_ID_ENV, "")
        key_path = os.environ.get(PRIVATE_KEY_PATH_ENV, "")
        if not key_id or not key_path:
            raise _Halt(D07HaltCode.CREDENTIAL_MISSING, D07Phase.C1_VALIDATION)

        try:
            with open(key_path, "rb") as handle:
                key_bytes = handle.read()
        except OSError as exc:
            raise _Halt(
                D07HaltCode.CREDENTIAL_INVALID,
                D07Phase.C1_VALIDATION,
                "private key file unreadable",
            ) from exc

        try:
            key = load_pem_private_key(key_bytes, password=None)
        except Exception as exc:  # noqa: BLE001 - any parse/format/encryption
            # failure (ValueError, TypeError, or a cryptography-specific
            # exception such as an unsupported/encrypted key) must not
            # escape as a raw exception; it maps to one stable, secret-safe
            # halt instead.
            raise _Halt(
                D07HaltCode.CREDENTIAL_INVALID,
                D07Phase.C1_VALIDATION,
                "private key unparseable",
            ) from exc

        if not isinstance(key, rsa.RSAPrivateKey):
            raise _Halt(
                D07HaltCode.CREDENTIAL_INVALID,
                D07Phase.C1_VALIDATION,
                "private key is not RSA",
            )

        self._key_id = key_id
        self._private_key = key

    def sign(
        self, *, method: str, path: str, timestamp_ms_text: str
    ) -> Tuple[str, str]:
        self._resolve()
        assert self._private_key is not None and self._key_id is not None
        message = (timestamp_ms_text + method + path).encode("utf-8")
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return self._key_id, base64.b64encode(signature).decode("ascii")


# ---------------------------------------------------------------------------
# Small value helpers (shared by every phase).
# ---------------------------------------------------------------------------


def _D(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed if parsed.is_finite() else None


def _valid_price_ranges(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        start, end, step = _D(item.get("start")), _D(item.get("end")), _D(item.get("step"))
        if start is None or end is None or step is None:
            return False
        if start < ZERO or end > ONE or start > end or step <= ZERO:
            return False
    return True


def _parse_utc_timestamp(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def classify_is_provisional(market: Mapping[str, object]) -> str:
    """Spec Section 5: an absent `is_provisional` field is observation-only
    -- `NOT_EXPOSED` -- and is never synthesized as `False`."""

    if "is_provisional" not in market:
        return "NOT_EXPOSED"
    value = market.get("is_provisional")
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    return "UNKNOWN"


def _reject_duplicate_keys(pairs: List[Tuple[str, object]]) -> dict:
    seen: set = set()
    result: dict = {}
    for key, value in pairs:
        if key in seen:
            raise D07Error(f"duplicate JSON key: {key}")
        seen.add(key)
        result[key] = value
    return result


def _reject_json_constant(token: str) -> None:
    raise D07Error(f"non-finite JSON constant is prohibited: {token}")


def _parse_json_body(body: bytes, *, phase: D07Phase) -> dict:
    if len(body) > MAX_RESPONSE_BYTES:
        raise _Halt(D07HaltCode.RESPONSE_TOO_LARGE, phase)
    try:
        text = body.decode("utf-8")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, D07Error) as exc:
        raise _Halt(D07HaltCode.RESPONSE_MALFORMED, phase, str(exc)) from exc
    if not isinstance(parsed, dict):
        raise _Halt(D07HaltCode.RESPONSE_MALFORMED, phase, "top level not an object")
    return parsed


def _get(
    transport: Transport,
    *,
    path: str,
    query: Sequence[Tuple[str, str]],
    headers: Mapping[str, str],
    phase: D07Phase,
) -> dict:
    try:
        response = transport.get(path=path, query=query, headers=headers)
    except _Halt:
        raise
    except Exception as exc:  # noqa: BLE001 - converted to a typed halt
        raise _Halt(D07HaltCode.TRANSPORT_FAILURE, phase, str(exc)) from exc
    if response.status != 200:
        raise _Halt(
            D07HaltCode.UNEXPECTED_HTTP_STATUS,
            phase,
            f"http_status={response.status}",
        )
    return _parse_json_body(response.body, phase=phase)


# ---------------------------------------------------------------------------
# A4 -- dynamic complete discovery (Spec Section 5; corrected COR-02).
# ---------------------------------------------------------------------------


def screen_a4_market(
    market: Mapping[str, object], *, min_close_ts: int, max_close_ts: int
) -> Tuple[bool, bool, dict]:
    """Pure. Never raises on malformed input -- a malformed field simply
    fails eligibility. Returns `(eligible, scope_violation, row)`.

    `scope_violation` is `True` only for the two request-scope/identity-
    integrity contradictions COR-02 requires the *caller* (A4 discovery) to
    treat as a global halt rather than an ordinary exclusion: a parseable
    close time outside the exact frozen request window, or positive MVE
    evidence contradicting `mve_filter=exclude`. It is always accompanied by
    `eligible=False`, but the reverse is not true -- most `eligible=False`
    rows (inactive status, wrong exchange index, non-binary type, an invalid
    book, bad price ranges, insufficient depth, an unparseable close time)
    have `scope_violation=False` and remain ordinary exclusions. Callers
    that do not need the A4 discovery-integrity distinction (C2 revalidation)
    may simply ignore `scope_violation` and use `eligible` alone."""

    ticker = market.get("ticker")
    event_ticker = market.get("event_ticker")
    status = market.get("status")
    exchange_index = market.get("exchange_index")
    market_type = market.get("market_type")

    close_dt = _parse_utc_timestamp(market.get("close_time"))
    close_ts = int(close_dt.timestamp()) if close_dt is not None else None

    bid, ask = _D(market.get("yes_bid_dollars")), _D(market.get("yes_ask_dollars"))
    bid_qty = _D(market.get("yes_bid_size_fp"))
    ask_qty = _D(market.get("yes_ask_size_fp"))
    volume_24h = _D(market.get("volume_24h_fp")) or ZERO
    volume = _D(market.get("volume_fp")) or ZERO
    open_interest = _D(market.get("open_interest_fp")) or ZERO
    liquidity = _D(market.get("liquidity_dollars")) or ZERO

    two_sided = (
        bid is not None
        and ask is not None
        and bid_qty is not None
        and ask_qty is not None
        and ZERO < bid <= ask < ONE
        and bid_qty > ZERO
        and ask_qty > ZERO
    )
    spread = (ask - bid) if two_sided else None
    min_depth = min(bid_qty, ask_qty) if two_sided else ZERO

    mve_collection_ticker = market.get("mve_collection_ticker")
    mve_selected_legs = market.get("mve_selected_legs")
    mve_violation = mve_collection_ticker not in (None, "") or (
        isinstance(mve_selected_legs, list) and len(mve_selected_legs) > 0
    )
    close_scope_violation = close_ts is not None and (
        close_ts < min_close_ts or close_ts > max_close_ts
    )
    scope_violation = close_scope_violation or mve_violation

    eligible = True
    if not isinstance(ticker, str) or not ticker:
        eligible = False
    if not isinstance(event_ticker, str) or not event_ticker:
        eligible = False
    if status != "active":
        eligible = False
    if (
        type(exchange_index) is not int
        or isinstance(exchange_index, bool)
        or exchange_index != 0
    ):
        eligible = False
    if market_type != "binary":
        eligible = False
    if close_ts is None or close_ts < min_close_ts or close_ts > max_close_ts:
        eligible = False
    if not _valid_price_ranges(market.get("price_ranges")):
        eligible = False
    if not two_sided:
        eligible = False
    if ask is None or ask > MAX_SELECTED_ASK:
        eligible = False
    if ask_qty is None or ask_qty < MIN_EXECUTABLE_ASK_QTY:
        eligible = False
    if mve_violation:
        eligible = False

    row = {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "close_ts": close_ts,
        "spread": spread,
        "min_depth": min_depth,
        "volume_24h": volume_24h,
        "volume": volume,
        "open_interest": open_interest,
        "liquidity": liquidity,
        "is_provisional_state": classify_is_provisional(market),
    }
    return eligible, scope_violation, row


def rank_a4(rows: Sequence[dict]) -> List[dict]:
    """Spec Section 5 ranking, exactly: spread asc; min two-sided depth
    desc; volume_24h desc; liquidity desc; open interest desc; volume desc;
    ticker asc."""

    return sorted(
        rows,
        key=lambda r: (
            r["spread"] if r["spread"] is not None else Decimal("999"),
            -r["min_depth"],
            -r["volume_24h"],
            -r["liquidity"],
            -r["open_interest"],
            -r["volume"],
            r["ticker"],
        ),
    )


def _fetch_markets_page(
    transport: Transport, *, cursor: str, min_close_ts: int, max_close_ts: int
) -> dict:
    query: List[Tuple[str, str]] = [
        ("limit", str(A4_PAGE_LIMIT)),
        ("min_close_ts", str(min_close_ts)),
        ("max_close_ts", str(max_close_ts)),
        ("mve_filter", "exclude"),
    ]
    if cursor:
        query.append(("cursor", cursor))
    payload = _get(
        transport,
        path=BASE_PATH + PATH_MARKETS,
        query=query,
        headers={"Accept": "application/json"},
        phase=D07Phase.A4_DISCOVERY,
    )
    if not isinstance(payload.get("markets"), list):
        raise _Halt(
            D07HaltCode.RESPONSE_MALFORMED,
            D07Phase.A4_DISCOVERY,
            "missing markets array",
        )
    return payload


def discover_a4_candidates(transport: Transport, *, anchor: datetime) -> List[dict]:
    """One fresh, complete, bounded discovery pass.

    COR-02: raises a global `_Halt` -- not a silent per-row exclusion -- on
    any non-object market row, any duplicate nonempty market ticker (within
    a page or across pages), any returned close time outside the exact
    frozen request window, or any positive MVE evidence contradicting
    `mve_filter=exclude`. Also raises on incomplete pagination or a cursor
    cycle. Returns up to `A4_RETAINED_COUNT` ranked eligible rows (possibly
    empty) when the discovered universe is otherwise scope/identity-clean."""

    anchor_ts = int(anchor.timestamp())
    min_close_ts = anchor_ts + MIN_SECONDS_TO_CLOSE
    max_close_ts = anchor_ts + MAX_SECONDS_TO_CLOSE

    cursor = ""
    seen_cursors: set = set()
    seen_tickers: set = set()
    eligible_rows: List[dict] = []

    for _ in range(A4_MAX_PAGES):
        payload = _fetch_markets_page(
            transport, cursor=cursor, min_close_ts=min_close_ts, max_close_ts=max_close_ts
        )
        for market in payload["markets"]:
            if not isinstance(market, dict):
                raise _Halt(
                    D07HaltCode.RESPONSE_MALFORMED,
                    D07Phase.A4_DISCOVERY,
                    "non-object market row",
                )

            ticker = market.get("ticker")
            if isinstance(ticker, str) and ticker:
                if ticker in seen_tickers:
                    raise _Halt(
                        D07HaltCode.A4_DUPLICATE_TICKER,
                        D07Phase.A4_DISCOVERY,
                        ticker,
                    )
                seen_tickers.add(ticker)

            eligible, scope_violation, row = screen_a4_market(
                market, min_close_ts=min_close_ts, max_close_ts=max_close_ts
            )
            if scope_violation:
                raise _Halt(
                    D07HaltCode.A4_SCOPE_CONTRADICTION,
                    D07Phase.A4_DISCOVERY,
                    row.get("ticker") if isinstance(row.get("ticker"), str) else None,
                )
            if eligible:
                eligible_rows.append(row)

        next_cursor = payload.get("cursor")
        if next_cursor in (None, ""):
            return rank_a4(eligible_rows)[:A4_RETAINED_COUNT]
        if not isinstance(next_cursor, str):
            raise _Halt(
                D07HaltCode.RESPONSE_MALFORMED,
                D07Phase.A4_DISCOVERY,
                "cursor was not string/null",
            )
        if next_cursor in seen_cursors:
            raise _Halt(D07HaltCode.CURSOR_CYCLE_DETECTED, D07Phase.A4_DISCOVERY)
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    raise _Halt(
        D07HaltCode.MARKET_DISCOVERY_INCOMPLETE,
        D07Phase.A4_DISCOVERY,
        f"page budget {A4_MAX_PAGES} exhausted with cursor remaining",
    )


# ---------------------------------------------------------------------------
# C1 -- current authenticated full-orderbook validation (Spec Section 6).
# ---------------------------------------------------------------------------


def parse_native_side(value: object) -> Tuple[bool, List[Tuple[Decimal, Decimal]]]:
    """Native YES/NO side parsing: a list of `[price, quantity]` pairs, each
    a valid open interval `(0, 1)` price with a positive quantity, no
    duplicate price level. Returns levels sorted best-first (descending
    price -- the native bid convention for both sides)."""

    if not isinstance(value, list):
        return False, []
    levels: List[Tuple[Decimal, Decimal]] = []
    seen_prices: set = set()
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            return False, []
        price, qty = _D(item[0]), _D(item[1])
        if price is None or qty is None or price <= ZERO or price >= ONE or qty <= ZERO:
            return False, []
        if price in seen_prices:
            return False, []
        seen_prices.add(price)
        levels.append((price, qty))
    levels.sort(key=lambda pair: pair[0], reverse=True)
    return True, levels


def _yes_asks_from_no_bids(
    no_levels: Sequence[Tuple[Decimal, Decimal]]
) -> List[Tuple[Decimal, Decimal]]:
    asks = [(ONE - price, qty) for price, qty in no_levels]
    asks.sort(key=lambda pair: pair[0])
    return asks


def _depth_within_band(
    levels: Sequence[Tuple[Decimal, Decimal]],
    best_price: Decimal,
    band: Decimal,
    *,
    is_bid: bool,
) -> Decimal:
    if is_bid:
        floor = best_price - band
        return sum((qty for price, qty in levels if price >= floor), ZERO)
    ceiling = best_price + band
    return sum((qty for price, qty in levels if price <= ceiling), ZERO)


def screen_c1_orderbook(item: Mapping[str, object], *, a4_row: Mapping[str, object]) -> Tuple[bool, dict]:
    """Pure. Consumes one `orderbook_fp` item plus the A4 row it was
    requested against; derives the analytical YES ask from native NO bids.
    Never raises -- a malformed book simply fails eligibility."""

    ticker = item.get("ticker")
    base_row = {
        "ticker": ticker,
        "event_ticker": a4_row["event_ticker"],
        "a4_rank": a4_row["a4_rank"],
        "spread": None,
        "volume_24h": a4_row["volume_24h"],
        "min_depth_2c": ZERO,
        "top_quantity": ZERO,
        "open_interest": a4_row["open_interest"],
    }

    orderbook = item.get("orderbook_fp")
    if not isinstance(orderbook, dict):
        return False, base_row

    yes_ok, yes_levels = parse_native_side(orderbook.get("yes_dollars"))
    no_ok, no_levels = parse_native_side(orderbook.get("no_dollars"))
    if not (yes_ok and no_ok):
        return False, base_row

    yes_asks = _yes_asks_from_no_bids(no_levels)
    if not yes_levels or not yes_asks:
        return False, base_row

    best_bid, best_bid_qty = yes_levels[0]
    best_ask, best_ask_qty = yes_asks[0]
    if best_bid >= best_ask:
        return False, base_row

    if best_ask > MAX_SELECTED_ASK or best_ask_qty < MIN_EXECUTABLE_ASK_QTY:
        return False, base_row

    spread = best_ask - best_bid
    bid_depth = _depth_within_band(yes_levels, best_bid, DEPTH_BAND, is_bid=True)
    ask_depth = _depth_within_band(yes_asks, best_ask, DEPTH_BAND, is_bid=False)

    row = {
        **base_row,
        "spread": spread,
        "min_depth_2c": min(bid_depth, ask_depth),
        "top_quantity": min(best_bid_qty, best_ask_qty),
    }
    return True, row


def rank_c1(rows: Sequence[dict]) -> List[dict]:
    """Spec Section 6 ranking, exactly: fresh spread asc; indicator
    (volume_24h > 0) desc; volume_24h desc; min two-sided 2-cent depth desc;
    min top quantity desc; open interest desc; A4 rank asc; ticker asc."""

    return sorted(
        rows,
        key=lambda r: (
            r["spread"],
            0 if r["volume_24h"] > ZERO else 1,
            -r["volume_24h"],
            -r["min_depth_2c"],
            -r["top_quantity"],
            -r["open_interest"],
            r["a4_rank"],
            r["ticker"],
        ),
    )


def build_c1_event_diverse_shortlist(ranked_rows: Sequence[dict]) -> List[dict]:
    """At most one candidate per `event_ticker`, in C1 rank order, up to
    `C1_EVENT_DIVERSE_SHORTLIST_SIZE`."""

    shortlist: List[dict] = []
    seen_events: set = set()
    for row in ranked_rows:
        if row["event_ticker"] in seen_events:
            continue
        seen_events.add(row["event_ticker"])
        shortlist.append(row)
        if len(shortlist) >= C1_EVENT_DIVERSE_SHORTLIST_SIZE:
            break
    return shortlist


def _fetch_batch_orderbooks(
    transport: Transport, signer: Signer, tickers: Sequence[str], *, phase: D07Phase
) -> dict:
    path = BASE_PATH + PATH_ORDERBOOKS
    timestamp_ms_text = str(int(time.time() * 1000))
    key_id, signature = signer.sign(
        method="GET", path=path, timestamp_ms_text=timestamp_ms_text
    )
    headers = {
        "Accept": "application/json",
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms_text,
    }
    payload = _get(
        transport,
        path=path,
        query=[("tickers", ticker) for ticker in tickers],
        headers=headers,
        phase=phase,
    )
    if not isinstance(payload.get("orderbooks"), list):
        raise _Halt(D07HaltCode.RESPONSE_MALFORMED, phase, "missing orderbooks array")
    return payload


def _index_orderbook_items(
    items: Sequence[object], requested: Sequence[str], *, phase: D07Phase, mismatch_code: D07HaltCode
) -> Dict[str, dict]:
    requested_set = set(requested)
    item_by_ticker: Dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            raise _Halt(D07HaltCode.RESPONSE_MALFORMED, phase, "non-object orderbook item")
        ticker = item.get("ticker")
        if (
            not isinstance(ticker, str)
            or ticker not in requested_set
            or ticker in item_by_ticker
        ):
            raise _Halt(mismatch_code, phase)
        item_by_ticker[ticker] = item
    if set(item_by_ticker) != requested_set or len(item_by_ticker) != len(requested):
        raise _Halt(mismatch_code, phase)
    return item_by_ticker


def validate_c1(transport: Transport, signer: Signer, a4_rows: Sequence[dict]) -> List[dict]:
    """C1: one authenticated batch orderbook fetch for exactly the A4
    output, exact requested/returned ticker-set equality, then eligibility
    plus event-diverse shortlisting. Raises `_Halt` if the shortlist is
    empty."""

    if not a4_rows:
        raise _Halt(D07HaltCode.A4_NO_ELIGIBLE_CANDIDATES, D07Phase.A4_DISCOVERY)

    a4_by_ticker = {
        row["ticker"]: {**row, "a4_rank": index + 1} for index, row in enumerate(a4_rows)
    }
    requested = list(a4_by_ticker.keys())

    payload = _fetch_batch_orderbooks(transport, signer, requested, phase=D07Phase.C1_VALIDATION)
    item_by_ticker = _index_orderbook_items(
        payload["orderbooks"],
        requested,
        phase=D07Phase.C1_VALIDATION,
        mismatch_code=D07HaltCode.C1_TICKER_SET_MISMATCH,
    )

    eligible_rows: List[dict] = []
    for ticker in requested:
        eligible, row = screen_c1_orderbook(item_by_ticker[ticker], a4_row=a4_by_ticker[ticker])
        if eligible:
            eligible_rows.append(row)

    shortlist = build_c1_event_diverse_shortlist(rank_c1(eligible_rows))
    if not shortlist:
        raise _Halt(D07HaltCode.C1_NO_ELIGIBLE_SHORTLIST, D07Phase.C1_VALIDATION)
    return shortlist


# ---------------------------------------------------------------------------
# B1 -- exact complete six-hour non-block trade recency (Spec Section 7;
# corrected COR-01).
# ---------------------------------------------------------------------------


def _screen_b1_trades_page(payload: Mapping[str, object], *, ticker: str, min_ts: int, max_ts: int) -> Optional[List[dict]]:
    """Returns the page's parsed trades, or `None` if the page contains any
    scope violation (wrong ticker, a row that states it is a block trade, a
    malformed field, or a timestamp outside the frozen window) -- callers
    treat `None` as grounds to classify the whole ticker window
    `TRADE_WINDOW_INCOMPLETE`. This is response validation, independent of
    and in addition to the `is_block_trade=false` request parameter COR-01
    adds -- a contradictory returned row still excludes the ticker."""

    trades = payload.get("trades")
    if not isinstance(trades, list):
        return None
    parsed: List[dict] = []
    for trade in trades:
        if not isinstance(trade, dict) or trade.get("ticker") != ticker:
            return None
        if trade.get("is_block_trade") is not False:
            return None
        qty = _D(trade.get("count_fp"))
        created = _parse_utc_timestamp(trade.get("created_time"))
        if qty is None or qty <= ZERO or created is None:
            return None
        created_ts = int(created.timestamp())
        if created_ts < min_ts or created_ts > max_ts:
            return None
        parsed.append({"qty": qty, "created_ts": created_ts})
    return parsed


def fetch_b1_trade_window(
    transport: Transport, *, ticker: str, anchor: datetime
) -> Tuple[B1WindowStatus, Optional[dict]]:
    """One frozen six-hour non-block trade-recency window for `ticker`.
    Complete pagination is required; an incomplete pagination, a cursor
    cycle, a non-200 status, a transport failure, or any scope violation all
    classify as `TRADE_WINDOW_INCOMPLETE` -- never treated as complete.

    COR-01: every page request -- the first page and every cursor
    continuation -- includes the exact query parameter
    `is_block_trade=false` (the literal lowercase string, never a boolean or
    any other spelling), matching the accepted non-block-window contract."""

    max_ts = int(anchor.timestamp())
    min_ts = max_ts - B1_LOOKBACK_SECONDS

    cursor: Optional[str] = None
    seen_cursors: set = set()
    trade_count = 0
    total_qty = ZERO
    latest_ts: Optional[int] = None

    for _ in range(B1_MAX_PAGES_PER_TICKER):
        query: List[Tuple[str, str]] = [
            ("limit", str(B1_PAGE_LIMIT)),
            ("ticker", ticker),
            ("min_ts", str(min_ts)),
            ("max_ts", str(max_ts)),
            ("is_block_trade", "false"),
        ]
        if cursor:
            query.append(("cursor", cursor))
        try:
            response = transport.get(
                path=BASE_PATH + PATH_TRADES, query=query, headers={"Accept": "application/json"}
            )
        except Exception:  # noqa: BLE001 - excluded, not a global halt
            return B1WindowStatus.TRADE_WINDOW_INCOMPLETE, None
        if response.status != 200:
            return B1WindowStatus.TRADE_WINDOW_INCOMPLETE, None
        try:
            payload = _parse_json_body(response.body, phase=D07Phase.B1_TRADE_RECENCY)
        except _Halt:
            return B1WindowStatus.TRADE_WINDOW_INCOMPLETE, None
        if "cursor" not in payload:
            return B1WindowStatus.TRADE_WINDOW_INCOMPLETE, None

        parsed = _screen_b1_trades_page(payload, ticker=ticker, min_ts=min_ts, max_ts=max_ts)
        if parsed is None:
            return B1WindowStatus.TRADE_WINDOW_INCOMPLETE, None
        for trade in parsed:
            trade_count += 1
            total_qty += trade["qty"]
            if latest_ts is None or trade["created_ts"] > latest_ts:
                latest_ts = trade["created_ts"]

        next_cursor = payload.get("cursor")
        if next_cursor in (None, ""):
            if trade_count == 0:
                return B1WindowStatus.COMPLETE_ZERO, {
                    "trade_count": 0,
                    "total_qty": ZERO,
                    "latest_age": None,
                }
            assert latest_ts is not None
            return B1WindowStatus.COMPLETE_ACTIVE, {
                "trade_count": trade_count,
                "total_qty": total_qty,
                "latest_age": max_ts - latest_ts,
            }
        if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
            return B1WindowStatus.TRADE_WINDOW_INCOMPLETE, None
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return B1WindowStatus.TRADE_WINDOW_INCOMPLETE, None


def rank_b1(rows: Sequence[dict]) -> List[dict]:
    """Spec Section 7 ranking, exactly: latest trade age asc; six-hour
    traded quantity desc; six-hour trade count desc; C1 current spread asc;
    C1 min two-sided 2-cent depth desc; C1 rank asc; ticker asc."""

    return sorted(
        rows,
        key=lambda r: (
            r["latest_age"],
            -r["total_qty"],
            -r["trade_count"],
            r["c1_spread"],
            -r["c1_min_depth_2c"],
            r["c1_rank"],
            r["ticker"],
        ),
    )


def evaluate_b1(transport: Transport, c1_shortlist: Sequence[dict], *, anchor: datetime) -> List[dict]:
    """B1: one fresh six-hour trade window per shortlisted ticker; only
    `COMPLETE_ACTIVE` windows are ranked. Raises `_Halt` if no finalist
    survives."""

    rows: List[dict] = []
    for index, c1_row in enumerate(c1_shortlist):
        status, window = fetch_b1_trade_window(transport, ticker=c1_row["ticker"], anchor=anchor)
        if status is not B1WindowStatus.COMPLETE_ACTIVE:
            continue
        assert window is not None
        rows.append(
            {
                "ticker": c1_row["ticker"],
                "event_ticker": c1_row["event_ticker"],
                "c1_rank": index + 1,
                "c1_spread": c1_row["spread"],
                "c1_min_depth_2c": c1_row["min_depth_2c"],
                "latest_age": window["latest_age"],
                "total_qty": window["total_qty"],
                "trade_count": window["trade_count"],
            }
        )

    finalists = rank_b1(rows)[:B1_FINALIST_COUNT]
    if not finalists:
        raise _Halt(D07HaltCode.B1_NO_FINALISTS, D07Phase.B1_TRADE_RECENCY)
    return finalists


# ---------------------------------------------------------------------------
# C2 -- immediate fresh revalidation (Spec Section 8).
# ---------------------------------------------------------------------------


def _fetch_market(transport: Transport, *, ticker: str) -> dict:
    path = BASE_PATH + "/markets/" + quote(ticker, safe="A-Za-z0-9._~-")
    payload = _get(
        transport,
        path=path,
        query=(),
        headers={"Accept": "application/json"},
        phase=D07Phase.C2_REVALIDATION,
    )
    market = payload.get("market")
    if not isinstance(market, dict):
        raise _Halt(
            D07HaltCode.RESPONSE_MALFORMED, D07Phase.C2_REVALIDATION, "missing market object"
        )
    if market.get("ticker") != ticker:
        raise _Halt(D07HaltCode.C2_TICKER_SET_MISMATCH, D07Phase.C2_REVALIDATION)
    return market


def revalidate_c2(
    transport: Transport, signer: Signer, b1_finalists: Sequence[dict], *, anchor: datetime
) -> dict:
    """C2: one exact `GET /markets/{ticker}` plus one authenticated batch
    orderbook fetch for exactly the current finalist set, full
    revalidation, then final selection. Raises `_Halt` if no candidate
    survives.

    Reuses `screen_a4_market` for market-metadata revalidation but, unlike
    A4 discovery, only its `eligible` output is consulted here -- a scope
    violation simply excludes that finalist from C2, exactly as an ordinary
    ineligibility would (COR-02 applies to A4 discovery-integrity only)."""

    if not b1_finalists:
        raise _Halt(D07HaltCode.B1_NO_FINALISTS, D07Phase.B1_TRADE_RECENCY)

    anchor_ts = int(anchor.timestamp())
    min_close_ts = anchor_ts + MIN_SECONDS_TO_CLOSE
    max_close_ts = anchor_ts + MAX_SECONDS_TO_CLOSE

    tickers = [row["ticker"] for row in b1_finalists]
    market_by_ticker = {ticker: _fetch_market(transport, ticker=ticker) for ticker in tickers}

    payload = _fetch_batch_orderbooks(transport, signer, tickers, phase=D07Phase.C2_REVALIDATION)
    item_by_ticker = _index_orderbook_items(
        payload["orderbooks"],
        tickers,
        phase=D07Phase.C2_REVALIDATION,
        mismatch_code=D07HaltCode.C2_TICKER_SET_MISMATCH,
    )

    candidates: List[dict] = []
    for index, b1_row in enumerate(b1_finalists):
        ticker = b1_row["ticker"]
        market_eligible, _scope_violation, market_row = screen_a4_market(
            market_by_ticker[ticker], min_close_ts=min_close_ts, max_close_ts=max_close_ts
        )
        if not market_eligible or market_row["event_ticker"] != b1_row["event_ticker"]:
            continue
        book_eligible, book_row = screen_c1_orderbook(
            item_by_ticker[ticker], a4_row={**market_row, "a4_rank": index}
        )
        if not book_eligible:
            continue
        candidates.append(
            {
                "ticker": ticker,
                "event_ticker": b1_row["event_ticker"],
                "b1_rank": index + 1,
                "spread": book_row["spread"],
            }
        )

    ranked = sorted(candidates, key=lambda r: (r["spread"], r["b1_rank"], r["ticker"]))
    if not ranked:
        raise _Halt(D07HaltCode.C2_NO_ELIGIBLE_CANDIDATE, D07Phase.C2_REVALIDATION)
    return ranked[0]


# ---------------------------------------------------------------------------
# Result types and top-level orchestration.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class D07SelectionSuccess:
    selected_ticker: str
    event_ticker: str
    discovery_anchor_utc: str
    a4_eligible_count: int
    c1_shortlist_count: int
    b1_finalist_count: int
    final_spread_dollars: str


@dataclass(frozen=True, slots=True)
class D07SelectionHalt:
    code: D07HaltCode
    phase: D07Phase
    detail: Optional[str] = None


@dataclass(frozen=True, slots=True)
class D07SelectionResult:
    """A disjoint result: exactly one of `success` or `halt`, never both,
    never neither."""

    success: Optional[D07SelectionSuccess] = None
    halt: Optional[D07SelectionHalt] = None

    def __post_init__(self) -> None:
        if (self.success is None) == (self.halt is None):
            raise D07Error("D07SelectionResult requires exactly one of success or halt")


def select_d07_ticker(
    *,
    transport: Optional[Transport] = None,
    signer: Optional[Signer] = None,
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> D07SelectionResult:
    """Run one fresh A4->C1->B1->C2 pass and return exactly one selected
    ticker, or a deterministic fail-closed halt. Never reuses a prior or
    historical ticker under any circumstance."""

    active_transport: Transport = transport if transport is not None else RealDemoTransport()
    active_signer: Signer = signer if signer is not None else EnvironmentRsaSigner()

    try:
        discovery_anchor = now_utc()
        a4_rows = discover_a4_candidates(active_transport, anchor=discovery_anchor)
        c1_shortlist = validate_c1(active_transport, active_signer, a4_rows)
        b1_finalists = evaluate_b1(active_transport, c1_shortlist, anchor=now_utc())
        selected = revalidate_c2(active_transport, active_signer, b1_finalists, anchor=now_utc())
    except _Halt as halt:
        return D07SelectionResult(
            halt=D07SelectionHalt(code=halt.code, phase=halt.phase, detail=halt.detail)
        )

    return D07SelectionResult(
        success=D07SelectionSuccess(
            selected_ticker=selected["ticker"],
            event_ticker=selected["event_ticker"],
            discovery_anchor_utc=discovery_anchor.isoformat().replace("+00:00", "Z"),
            a4_eligible_count=len(a4_rows),
            c1_shortlist_count=len(c1_shortlist),
            b1_finalist_count=len(b1_finalists),
            final_spread_dollars=format(selected["spread"], "f"),
        )
    )


# ---------------------------------------------------------------------------
# CLI. Exposes no ticker/candidate/market override of any kind.
# ---------------------------------------------------------------------------


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m arb.venues.kalshi.d07_market_selector",
        description=(
            "Run the permanent dynamic R1-D07 Kalshi Demo ticker selector: "
            "one fresh A4->C1->B1->C2 pass, never a caller-supplied ticker."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the result as a single JSON object instead of plain text.",
    )
    return parser


def _result_to_dict(result: D07SelectionResult) -> dict:
    if result.success is not None:
        success = result.success
        return {
            "status": "SUCCEEDED",
            "selected_ticker": success.selected_ticker,
            "event_ticker": success.event_ticker,
            "discovery_anchor_utc": success.discovery_anchor_utc,
            "a4_eligible_count": success.a4_eligible_count,
            "c1_shortlist_count": success.c1_shortlist_count,
            "b1_finalist_count": success.b1_finalist_count,
            "final_spread_dollars": success.final_spread_dollars,
        }
    assert result.halt is not None
    halt = result.halt
    return {
        "status": "HALTED",
        "code": halt.code.value,
        "phase": halt.phase.value,
        "detail": halt.detail,
    }


def _cli(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_cli_parser().parse_args(argv)
    result = select_d07_ticker()
    payload = _result_to_dict(result)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif result.success is not None:
        print(f"D07_SELECTED_TICKER={payload['selected_ticker']}")
        print(f"event_ticker={payload['event_ticker']}")
        print(f"discovery_anchor_utc={payload['discovery_anchor_utc']}")
    else:
        print(f"D07_HALTED code={payload['code']} phase={payload['phase']}", file=sys.stderr)
        if payload["detail"]:
            print(f"detail={payload['detail']}", file=sys.stderr)
    return 0 if result.success is not None else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
