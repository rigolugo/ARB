"""Offline tests for the repository-resident configurable read-only shadow
experiment (architecture R1-D07_SHADOW_EXPERIMENT_CONFIGURABLE_SELECTOR_01;
installation R1-D07_SHADOW_CONFIGURABLE_EXPERIMENT_INFRASTRUCTURE_CANONICALIZATION_01).

Network is hard-blocked (socket construction raises) and sqlite3.connect is
blocked for every test.  Every live-like selector/capture test drives the
real code paths through deterministic FAKE HTTP responses parsed by the real
``http.client`` inside the real ``AccountedDemoTransport``.  Credentials are
synthetic only: an in-process generated RSA key written to a temp file and a
marker API-key id.  Canonical modules are imported read-only from this same
repository's ``src`` (never from an external checkout).

Experiment configurations used here are TEST FIXTURE BYTES constructed in this
test module only (the approved predecessor baseline and the accepted Test-02
input); no concrete experiment configuration is installed in the repository
as a default, example or policy.

Dispatch test theorems are tagged ``tNN`` (1..32) in the test method names.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import http.client
import inspect
import io
import itertools
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "src" / "arb" / "venues" / "kalshi" / "shadow_experiment"
RUNNER_PATH = REPO / "run_shadow_experiment.py"
for _p in (PKG.parent, REPO / "src", REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shadow_experiment import constants as C  # noqa: E402
from shadow_experiment import shadow_evaluator as EV  # noqa: E402
from shadow_experiment import canonical_binding as CB  # noqa: E402
from shadow_experiment import write_guard as WG  # noqa: E402
from shadow_experiment import config as CFG  # noqa: E402

MODS = CB.bind_canonical_modules(REPO)
SEL, MM, RISK, RUNNER = MODS["selector"], MODS["mm"], MODS["risk"], MODS["runner"]
import run_shadow_experiment as LAUNCHER  # noqa: E402
from shadow_experiment import configurable_selector as CS  # noqa: E402
from shadow_experiment import live_capture as LC  # noqa: E402
from shadow_experiment import sweep as SW  # noqa: E402
from shadow_experiment.transport import AccountedDemoTransport  # noqa: E402

# Approved predecessor baseline configuration bytes (985 bytes).  TEST FIXTURE ONLY:
# never installed in the repository as a default, example or policy.
BASELINE_BYTES = '''{
  "schema_version": 1,
  "run": {
    "run_id": "g1_shadow_experiment_02"
  },
  "selector": {
    "market_scope": {
      "exchange_index": 0,
      "market_type": "binary",
      "status": "active",
      "exclude_mve": true
    },
    "close_window": {
      "min_seconds_to_close": 1800,
      "max_seconds_to_close": 43200
    },
    "a4": {
      "page_limit": 500,
      "max_pages": 200,
      "retained_count": 100,
      "max_selected_ask": "0.8000",
      "min_executable_ask_qty": "1.00"
    },
    "c1": {
      "event_diverse_shortlist_size": 20,
      "depth_band": "0.0200"
    },
    "b1": {
      "lookback_seconds": 21600,
      "page_limit": 1000,
      "max_pages_per_ticker": 20,
      "finalist_count": 5,
      "exclude_block_trades": true,
      "require_complete_active_window": true
    }
  },
  "shadow_experiment": {
    "trial_g": 1,
    "minimum_spread_usd": [
      "0.0100",
      "0.0200",
      "0.0300",
      "0.0400",
      "0.0500"
    ]
  }
}
'''.encode("ascii")
BASELINE_SHA256 = "4cbbb61b1f86bae65de8eb378bb69efba4ea9fc3aa19b07230ba35edd7205169"
assert hashlib.sha256(BASELINE_BYTES).hexdigest() == BASELINE_SHA256
SURFACE_FILES = [RUNNER_PATH] + sorted(PKG.glob("*.py"))
SECRET_KEY_ID = "SYNTH-KEYID-SECRET-MARKER-7c1e"
TICKER = "KXSYNTH-26OCT04-T1"
ANCHOR = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
CLOSE_TIME = "2026-10-04T16:00:00Z"     # anchor + 4h: inside [30 min, 12 h]
TRADE_TIME = "2026-10-04T11:30:00Z"     # inside the 6 h B1 window
ONE_CENT_RANGES = [{"start": "0.0000", "end": "1.0000", "step": "0.0100"}]
OLD_FLAG = "--i-authorize-one-demo-read-only-shadow-g1-experiment-01"


def _no_network(*_a, **_k):
    raise AssertionError("network attempted in offline test")


def _no_sqlite(*_a, **_k):
    raise AssertionError("sqlite/ledger open attempted")


class OfflineBase(unittest.TestCase):
    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(socket, "socket", _no_network))
        stack.enter_context(mock.patch.object(socket, "create_connection", _no_network))
        stack.enter_context(mock.patch.object(sqlite3, "connect", _no_sqlite))
        self.addCleanup(stack.close)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.baseline_path = self.tmp / "baseline_config_fixture.json"
        self.baseline_path.write_bytes(BASELINE_BYTES)


# ---------------------------------------------------------------------------
# config helpers
# ---------------------------------------------------------------------------
def baseline_doc() -> dict:
    return json.loads(BASELINE_BYTES)


def to_bytes(doc) -> bytes:
    return json.dumps(doc, indent=2).encode("utf-8")


def with_value(path: str, value) -> bytes:
    doc = baseline_doc()
    node = doc
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return to_bytes(doc)


def without(path: str) -> bytes:
    doc = baseline_doc()
    node = doc
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[k]
    del node[keys[-1]]
    return to_bytes(doc)


def cfg_with(**overrides) -> CFG.ExperimentConfigV1:
    doc = baseline_doc()
    for path, value in overrides.items():
        node = doc
        keys = path.split("__")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return CFG.load_config_bytes(to_bytes(doc))


def leaf_paths(schema=CFG.SCHEMA, prefix=""):
    for key, sub in schema.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(sub, dict):
            yield from leaf_paths(sub, path)
        else:
            yield path


BASELINE = CFG.load_config_bytes(BASELINE_BYTES)


# ---------------------------------------------------------------------------
# fake HTTP stack feeding real http.client parsing through AccountedDemoTransport
# ---------------------------------------------------------------------------
class _FakeSock:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def makefile(self, mode="rb", *a, **k):
        return io.BytesIO(self.raw)


class _FakeConn:
    def __init__(self, router, log):
        self.router, self.log = router, log
        self.response = None

    def request(self, method, url, headers=None):
        self.log.append((method, url, dict(headers or {})))
        status, body, declared = self.router(method, url)
        cl = len(body) if declared is None else declared
        raw = (f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {cl}\r\n"
               f"Connection: close\r\n\r\n").encode() + body
        self.response = http.client.HTTPResponse(_FakeSock(raw), method="GET")

    def getresponse(self):
        self.response.begin()
        return self.response

    def close(self):
        pass


def mkt(ticker, event=None, **over):
    m = {"ticker": ticker, "event_ticker": event or ("EV-" + ticker), "status": "active", "market_type": "binary",
         "exchange_index": 0, "close_time": CLOSE_TIME, "yes_bid_dollars": "0.4000", "yes_ask_dollars": "0.4500",
         "yes_bid_size_fp": "10.00", "yes_ask_size_fp": "10.00", "volume_24h_fp": "5.00",
         "price_ranges": ONE_CENT_RANGES}
    m.update(over)
    return m


def book(yes=(("0.4000", "10.00"),), no=(("0.5500", "10.00"),)):
    return {"yes_dollars": [list(x) for x in yes], "no_dollars": [list(x) for x in no]}


ACTIVE = [{"is_block_trade": False, "count_fp": "1.00", "created_time": TRADE_TIME}]
ZERO_TRADES: list = []


class Universe:
    """Deterministic fake Kalshi Demo read surface for one selector run (+ snapshot)."""

    def __init__(self, markets, books=None, trades=None, *, a4_pages=1, c2_markets=None, c2_books=None,
                 positions=None, orders=None, short_path=None):
        self.markets = markets
        self.books = books or {}
        self.trades = trades or {}
        self.a4_pages = a4_pages
        self.c2_markets = c2_markets or {}
        self.c2_books = c2_books or {}
        self.positions = positions if positions is not None else {"market_positions": [], "event_positions": [],
                                                                   "cursor": ""}
        self.orders = orders if orders is not None else {"orders": [], "cursor": ""}
        self.short_path = short_path
        self.orderbook_calls = 0
        self.log: list = []

    def _book_item(self, ticker):
        source = self.c2_books if self.orderbook_calls > 1 and ticker in self.c2_books else self.books
        value = source.get(ticker, book())
        return {"ticker": ticker} if value is None else {"ticker": ticker, "orderbook_fp": value}

    def route(self, method, url):
        assert method == "GET", method
        parts = urlsplit(url)
        q = parse_qsl(parts.query)
        qd = dict(q)
        path = parts.path
        if path == SEL.BASE_PATH + "/markets":
            page = int(qd.get("cursor", "p0")[1:])
            last = page == self.a4_pages - 1
            payload = {"markets": self.markets if last else [], "cursor": "" if last else f"p{page + 1}"}
        elif path == SEL.BASE_PATH + "/markets/orderbooks":
            self.orderbook_calls += 1
            payload = {"orderbooks": [self._book_item(v) for k, v in q if k == "tickers"]}
        elif path == SEL.BASE_PATH + "/markets/trades":
            spec = self.trades.get(qd["ticker"], ACTIVE)
            if spec == "RAISE":
                raise ConnectionError("synthetic transport failure")
            if spec == "HTTP500":
                return 500, b'{"error":"x"}', None
            payload = {"trades": [{"ticker": qd["ticker"], **t} for t in spec], "cursor": ""}
        elif path.endswith("/portfolio/positions"):
            payload = self.positions
        elif path.endswith("/portfolio/orders"):
            payload = self.orders
        elif path.startswith(SEL.BASE_PATH + "/markets/"):
            ticker = path.rsplit("/", 1)[1]
            base = {m["ticker"]: m for m in self.markets if isinstance(m, dict) and m.get("ticker")}
            payload = {"market": self.c2_markets.get(ticker, base.get(ticker, mkt(ticker)))}
        else:
            raise AssertionError(url)
        body = json.dumps(payload).encode()
        short = self.short_path and path.endswith(self.short_path)
        return 200, body, (len(body) + 25 if short else None)

    def transport(self, ceiling=10_000):
        return AccountedDemoTransport(SEL, request_ceiling=ceiling,
                                      connection_factory=lambda: _FakeConn(self.route, self.log))


class FakeSigner:
    def __init__(self):
        self.calls = 0

    def sign(self, *, method, path, timestamp_ms_text):
        assert method == "GET"
        self.calls += 1
        return "SYNTH-NOT-A-REAL-KEY", "c2lnbmF0dXJl"


def run_selector(universe, cfg=BASELINE, sel=SEL, ceiling=10_000):
    t = universe.transport(ceiling)
    t.phase = "SELECTOR"
    signer = FakeSigner()
    result = CS.select_shadow_ticker(sel, cfg, transport=t, signer=signer, now_utc=lambda: ANCHOR)
    return result, t, signer


def simple_universe(n=3, **kw):
    return Universe([mkt(f"KXU-{i:02d}") for i in range(n)], **kw)


def _synthetic_key_file(tmp: Path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    p = tmp / "synthetic_demo_key.pem"
    p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    return p


# ---------------------------------------------------------------------------
# canonical binding / environment
# ---------------------------------------------------------------------------
class CanonicalBindingTests(OfflineBase):
    def test_imports_resolve_under_canonical_repo_src(self):
        src = (REPO / "src").resolve()
        for module in MODS.values():
            self.assertIn(src, Path(module.__file__).resolve().parents, module.__name__)

    def test_launcher_binds_its_own_repository_root(self):
        self.assertEqual(LAUNCHER.REPOSITORY_ROOT, REPO)
        self.assertEqual(LAUNCHER.PACKAGE_ROOT, PKG)
        self.assertEqual(Path(C.__file__).resolve().parent, PKG)
        self.assertEqual(Path(LAUNCHER.__file__).resolve(), RUNNER_PATH)

    def test_credential_presence_only_and_legacy_pem_refused(self):
        report = CB.PreflightReport()
        CB.verify_credential_presence(report, {C.API_KEY_ID_ENV: SECRET_KEY_ID, C.PRIVATE_KEY_PATH_ENV: "x"})
        self.assertNotIn(SECRET_KEY_ID, json.dumps(report.checks))
        with self.assertRaises(CB.PreconditionFailed):
            CB.verify_credential_presence(CB.PreflightReport(), {C.API_KEY_ID_ENV: "a", C.PRIVATE_KEY_PATH_ENV: "b",
                                                                 C.LEGACY_PRIVATE_KEY_PEM_ENV: "pem"})
        with self.assertRaises(CB.PreconditionFailed):
            CB.verify_credential_presence(CB.PreflightReport(), {C.API_KEY_ID_ENV: "a"})

    def test_interpreter_check_passes_for_bound_interpreter(self):
        report = CB.PreflightReport()
        CB.verify_interpreter(report)
        self.assertTrue(all(c["result"] == "PASS" for c in report.checks))


# ---------------------------------------------------------------------------
# t01-t08: strict JSON configuration
# ---------------------------------------------------------------------------
class ConfigTests(OfflineBase):
    def assertConfigError(self, raw: bytes, code: str, path_prefix: str | None = None):
        with self.assertRaises(CFG.ConfigError) as ctx:
            CFG.load_config_bytes(raw)
        self.assertEqual(ctx.exception.code, code, ctx.exception)
        if path_prefix is not None:
            self.assertTrue(ctx.exception.path.startswith(path_prefix), ctx.exception.path)
        return ctx.exception

    def test_t01_baseline_parses_and_normalizes_deterministically(self):
        self.assertEqual(hashlib.sha256(BASELINE_BYTES).hexdigest(), BASELINE_SHA256)
        a = CFG.load_config_bytes(BASELINE_BYTES)
        b = CFG.load_config_bytes(BASELINE_BYTES)
        self.assertEqual(a, b)
        s = a.selector
        self.assertEqual((s.market_scope.exchange_index, s.market_scope.market_type, s.market_scope.status,
                          s.market_scope.exclude_mve), (0, "binary", "active", True))
        self.assertEqual((s.close_window.min_seconds_to_close, s.close_window.max_seconds_to_close), (1800, 43200))
        self.assertEqual((s.a4.page_limit, s.a4.max_pages, s.a4.retained_count), (500, 200, 100))
        self.assertEqual((s.a4.max_selected_ask, s.a4.min_executable_ask_qty), (D("0.8000"), D("1.00")))
        self.assertEqual((s.c1.event_diverse_shortlist_size, s.c1.depth_band), (20, D("0.0200")))
        self.assertEqual((s.b1.lookback_seconds, s.b1.page_limit, s.b1.max_pages_per_ticker, s.b1.finalist_count,
                          s.b1.exclude_block_trades, s.b1.require_complete_active_window),
                         (21600, 1000, 20, 5, True, True))
        self.assertEqual(a.shadow_experiment.trial_g, 1)
        self.assertEqual(a.shadow_experiment.minimum_spread_usd,
                         (D("0.0100"), D("0.0200"), D("0.0300"), D("0.0400"), D("0.0500")))
        for value in (s.a4.max_selected_ask, s.a4.min_executable_ask_qty, s.c1.depth_band,
                      *a.shadow_experiment.minimum_spread_usd):
            self.assertIs(type(value), D)
        eff = CFG.effective_config_dict(a)
        self.assertEqual(eff, json.loads(BASELINE_BYTES))     # normalization is lossless for the baseline
        d1 = LAUNCHER._dump(CFG.effective_config_document(a))
        d2 = LAUNCHER._dump(CFG.effective_config_document(b))
        self.assertEqual(d1, d2)
        # key order / whitespace in the input does not change the effective config
        reordered = json.dumps(json.loads(BASELINE_BYTES), sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(CFG.effective_config_dict(CFG.load_config_bytes(reordered)), eff)

    def test_t02_unknown_key_fails(self):
        for path in ("extra", "run.extra", "selector.extra", "selector.market_scope.extra", "selector.a4.extra",
                     "selector.c1.extra", "selector.b1.extra", "selector.close_window.extra", "shadow_experiment.extra"):
            with self.subTest(path=path):
                self.assertConfigError(with_value(path, 1), "CONFIG_UNKNOWN_KEY")
        for capability_key in ("allow_writes", "production", "retries", "normal_writer", "gate_d",
                               "release_only", "writer_permit", "allow_production", "max_retries"):
            for parent in ("", "selector.", "run.", "shadow_experiment."):
                with self.subTest(key=parent + capability_key):
                    self.assertConfigError(with_value(parent + capability_key, True), "CONFIG_UNKNOWN_KEY")

    def test_t03_missing_required_key_fails_for_every_leaf(self):
        paths = list(leaf_paths())
        self.assertEqual(len(paths), 23)
        for path in paths:
            with self.subTest(path=path):
                self.assertConfigError(without(path), "CONFIG_MISSING_KEY", "$." + path)
        for section in ("run", "selector", "shadow_experiment", "selector.market_scope", "selector.close_window",
                        "selector.a4", "selector.c1", "selector.b1"):
            with self.subTest(section=section):
                self.assertConfigError(without(section), "CONFIG_MISSING_KEY")

    def test_t04_malformed_json_fails(self):
        cases = {
            b'{"schema_version": 1,': "CONFIG_JSON_MALFORMED",
            b'{"schema_version": 1,}': "CONFIG_JSON_MALFORMED",
            b"": "CONFIG_JSON_MALFORMED",
            b"\xef\xbb\xbf" + BASELINE_BYTES: "CONFIG_JSON_MALFORMED",
            b"\xff\xfe{}": "CONFIG_NOT_UTF8",
            b"[]": "CONFIG_TOP_LEVEL_NOT_OBJECT",
            b'"x"': "CONFIG_TOP_LEVEL_NOT_OBJECT",
            b'{"schema_version": 1, "schema_version": 1}': "CONFIG_DUPLICATE_KEY",
            BASELINE_BYTES.replace(b'"trial_g": 1', b'"trial_g": NaN'): "CONFIG_NONFINITE_CONSTANT",
            BASELINE_BYTES.replace(b'"trial_g": 1', b'"trial_g": Infinity'): "CONFIG_NONFINITE_CONSTANT",
            BASELINE_BYTES.replace(b'"trial_g": 1', b'"trial_g": -Infinity'): "CONFIG_NONFINITE_CONSTANT",
        }
        for raw, code in cases.items():
            with self.subTest(raw=raw[:40]):
                self.assertConfigError(raw, code)
        dup_nested = BASELINE_BYTES.replace(b'"depth_band": "0.0200"', b'"depth_band": "0.0200", "depth_band": "0.03"')
        self.assertConfigError(dup_nested, "CONFIG_DUPLICATE_KEY")
        with self.assertRaises(CFG.ConfigError):
            CFG.load_config_bytes(BASELINE_BYTES.decode())  # str is not exact bytes

    def test_t05_float_where_decimal_string_required_fails(self):
        for path in ("selector.a4.max_selected_ask", "selector.a4.min_executable_ask_qty", "selector.c1.depth_band"):
            with self.subTest(path=path):
                self.assertConfigError(with_value(path, 0.5), "CONFIG_FLOAT_PROHIBITED", "$." + path)
        self.assertConfigError(with_value("shadow_experiment.minimum_spread_usd", [0.01, "0.0200"]),
                               "CONFIG_FLOAT_PROHIBITED")
        # binary-float spellings of integers are rejected too
        self.assertConfigError(BASELINE_BYTES.replace(b'"max_pages": 200', b'"max_pages": 200.0'),
                               "CONFIG_FLOAT_PROHIBITED")
        self.assertConfigError(BASELINE_BYTES.replace(b'"max_pages": 200', b'"max_pages": 2e2'),
                               "CONFIG_FLOAT_PROHIBITED")
        # a JSON integer is not a decimal string either
        self.assertConfigError(with_value("selector.c1.depth_band", 0), "CONFIG_WRONG_TYPE")

    def test_t06_invalid_decimal_nan_infinity_fail(self):
        for bad in ("NaN", "nan", "Infinity", "-Infinity", "inf", "sNaN", "-0.5", "+0.5", "1e-2", "0.8.0", "",
                    " 0.8", "0.8 ", ".5", "5.", "0x1", "0,5", "08", "１"):
            with self.subTest(bad=bad):
                self.assertConfigError(with_value("selector.a4.max_selected_ask", bad), "CONFIG_DECIMAL_INVALID")
                self.assertConfigError(with_value("shadow_experiment.minimum_spread_usd", ["0.0100", bad]),
                                       "CONFIG_DECIMAL_INVALID")

    def test_t07_close_window_inversion_fails(self):
        doc = baseline_doc()
        doc["selector"]["close_window"] = {"min_seconds_to_close": 43200, "max_seconds_to_close": 1800}
        self.assertConfigError(to_bytes(doc), "CONFIG_CROSS_FIELD_INVALID")
        doc["selector"]["close_window"] = {"min_seconds_to_close": 1800, "max_seconds_to_close": 1800}
        self.assertConfigError(to_bytes(doc), "CONFIG_CROSS_FIELD_INVALID")
        doc["selector"]["close_window"] = {"min_seconds_to_close": 1800, "max_seconds_to_close": 1801}
        CFG.load_config_bytes(to_bytes(doc))

    def test_t08_bounds(self):
        range_cases = [
            ("selector.a4.max_selected_ask", "0"), ("selector.a4.max_selected_ask", "0.0000"),
            ("selector.a4.max_selected_ask", "1"), ("selector.a4.max_selected_ask", "1.0000"),
            ("selector.a4.max_selected_ask", "1.5"), ("selector.c1.depth_band", "0"),
            ("selector.c1.depth_band", "1"), ("selector.c1.depth_band", "2.0"),
            ("selector.a4.min_executable_ask_qty", "0"), ("selector.a4.min_executable_ask_qty", "0.00"),
        ]
        for path, value in range_cases:
            with self.subTest(path=path, value=value):
                self.assertConfigError(with_value(path, value), "CONFIG_VALUE_OUT_OF_RANGE", "$." + path)
        for spreads in (["0"], ["0.0000"], ["1"], ["1.0000"], ["0.0100", "1.5"]):
            with self.subTest(spreads=spreads):
                self.assertConfigError(with_value("shadow_experiment.minimum_spread_usd", spreads),
                                       "CONFIG_VALUE_OUT_OF_RANGE")
        self.assertConfigError(with_value("shadow_experiment.minimum_spread_usd", []), "CONFIG_EMPTY_LIST")
        self.assertConfigError(with_value("shadow_experiment.minimum_spread_usd", ["0.0100", "0.0100"]),
                               "CONFIG_DUPLICATE_VALUE")
        self.assertConfigError(with_value("shadow_experiment.minimum_spread_usd", ["0.01", "0.0100"]),
                               "CONFIG_DUPLICATE_VALUE")
        self.assertConfigError(with_value("shadow_experiment.minimum_spread_usd", "0.0100"), "CONFIG_WRONG_TYPE")
        int_paths = [p for p in leaf_paths() if _schema_kind(p) == CFG.INT_POSITIVE]
        # 10 INT_POSITIVE knobs; trial_g has its own closed 1..4 label kind (CORRECTION_01 F02, t39/t40)
        self.assertEqual(len(int_paths), 10)
        self.assertEqual(_schema_kind("shadow_experiment.trial_g"), CFG.INT_TRIAL_G_LABEL)
        for path in int_paths:
            for bad, code in ((0, "CONFIG_VALUE_OUT_OF_RANGE"), (-1, "CONFIG_VALUE_OUT_OF_RANGE"),
                              (True, "CONFIG_WRONG_TYPE"), (False, "CONFIG_WRONG_TYPE"), ("5", "CONFIG_WRONG_TYPE"),
                              (None, "CONFIG_WRONG_TYPE")):
                with self.subTest(path=path, bad=bad):
                    self.assertConfigError(with_value(path, bad), code, "$." + path)
        for path in ("selector.market_scope.exclude_mve", "selector.b1.exclude_block_trades",
                     "selector.b1.require_complete_active_window"):
            for bad in (1, 0, "true", None):
                with self.subTest(path=path, bad=bad):
                    self.assertConfigError(with_value(path, bad), "CONFIG_WRONG_TYPE")
        self.assertConfigError(with_value("selector.market_scope.exchange_index", 1), "CONFIG_VALUE_OUT_OF_RANGE")
        self.assertConfigError(with_value("selector.market_scope.exchange_index", True), "CONFIG_WRONG_TYPE")
        for path in ("selector.market_scope.status", "selector.market_scope.market_type"):
            for bad, code in (("", "CONFIG_VALUE_OUT_OF_RANGE"), (" active", "CONFIG_VALUE_OUT_OF_RANGE"),
                              ("x" * 65, "CONFIG_VALUE_OUT_OF_RANGE"), (1, "CONFIG_WRONG_TYPE")):
                with self.subTest(path=path, bad=bad):
                    self.assertConfigError(with_value(path, bad), code)
        for bad in ("", "has space", "-lead", "x" * 129, "a/b"):
            with self.subTest(run_id=bad):
                self.assertConfigError(with_value("run.run_id", bad), "CONFIG_VALUE_OUT_OF_RANGE")
        for bad, code in ((2, "CONFIG_SCHEMA_VERSION_UNSUPPORTED"), ("1", "CONFIG_WRONG_TYPE"),
                          (True, "CONFIG_WRONG_TYPE"), (0, "CONFIG_SCHEMA_VERSION_UNSUPPORTED")):
            with self.subTest(schema_version=bad):
                self.assertConfigError(with_value("schema_version", bad), code)
        # valid non-baseline values are accepted
        cfg = cfg_with(selector__a4__max_selected_ask="0.9999", selector__c1__depth_band="0.0001",
                       shadow_experiment__minimum_spread_usd=["0.0500", "0.0100"], shadow_experiment__trial_g=3)
        self.assertEqual(cfg.shadow_experiment.minimum_spread_usd, (D("0.0500"), D("0.0100")))  # order preserved


# leaf kind lookup for the bounds test
def _schema_kind(path: str):
    node = CFG.SCHEMA
    for k in path.split("."):
        node = node[k]
    return node



# ---------------------------------------------------------------------------
# t09/t10: CLI acknowledgement and validation ordering
# ---------------------------------------------------------------------------
class _Boom(AssertionError):
    pass


def _forbid(name):
    def f(*_a, **_k):
        raise _Boom(f"{name} reached")
    return f


class CliTests(OfflineBase):
    def _guarded_run(self, argv, *, forbid_config=False):
        """Run the launcher with every preflight / credential / signer / transport
        seam booby-trapped."""
        buf = io.StringIO()
        patches = [mock.patch.object(LAUNCHER, n, side_effect=_forbid(n)) for n in (
            "verify_repository_provenance", "verify_credential_presence", "verify_interpreter",
            "bind_canonical_modules", "scan_shadow_surface")]
        if forbid_config:
            patches.append(mock.patch.object(LAUNCHER, "load_config_bytes", side_effect=_forbid("config")))
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(buf))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            try:
                code = LAUNCHER.run(argv, signer_factory=_forbid("signer"), transport_factory=_forbid("transport"),
                                    select_fn=_forbid("selector"))
            except SystemExit as exc:   # argparse rejects unknown/abbreviated flags
                code = exc.code
        return code, buf.getvalue()

    def test_t09_flag_absent_refuses_before_config_credential_network(self):
        out = self.tmp / "never"
        for argv in ([], ["--config", str(self.baseline_path)], ["--config", str(self.baseline_path), "--output-dir", str(out)],
                     ["--config", str(self.tmp / "nonexistent.json"), "--output-dir", str(out)]):
            with self.subTest(argv=argv):
                code, text = self._guarded_run(argv, forbid_config=True)
                self.assertEqual(code, LAUNCHER.EXIT_REFUSED)
                self.assertIn("REFUSED", text)
                self.assertFalse(out.exists())
        for wrong in (OLD_FLAG, "--execute", "--execute-authorized", "--execute-authorized-run=1",
                      "--EXECUTE-AUTHORIZED-RUN", "--execute_authorized_run"):
            with self.subTest(flag=wrong):
                code, _ = self._guarded_run(["--config", str(self.baseline_path), "--output-dir", str(out), wrong],
                                            forbid_config=True)
                self.assertNotEqual(code, 0)
                self.assertFalse(out.exists())
        # replay + acknowledgement is ambiguous and refused before anything
        code, text = self._guarded_run(["--config", str(self.baseline_path), "--output-dir", str(out),
                                        "--replay-snapshot", "x", C.EXECUTION_ACKNOWLEDGEMENT_FLAG], forbid_config=True)
        self.assertEqual(code, LAUNCHER.EXIT_REFUSED)
        self.assertIn("MODE_AMBIGUOUS", text)

    def test_t10_flag_present_does_not_bypass_config_validation(self):
        out = self.tmp / "never"
        bad_configs = {
            "unknown": with_value("selector.a4.allow_writes", True),
            "missing": without("selector.b1.finalist_count"),
            "float": with_value("selector.c1.depth_band", 0.02),
            "malformed": b"{",
            "inverted": to_bytes({**baseline_doc(), "selector": {**baseline_doc()["selector"], "close_window": {
                "min_seconds_to_close": 10, "max_seconds_to_close": 5}}}),
        }
        for label, raw in bad_configs.items():
            with self.subTest(label=label):
                p = self.tmp / f"{label}.json"
                p.write_bytes(raw)
                code, text = self._guarded_run(["--config", str(p), "--output-dir", str(out),
                                                C.EXECUTION_ACKNOWLEDGEMENT_FLAG])
                self.assertEqual(code, LAUNCHER.EXIT_CONFIG_INVALID, text)
                self.assertIn("CONFIG_INVALID", text)
                self.assertFalse(out.exists())
        code, text = self._guarded_run(["--output-dir", str(out), C.EXECUTION_ACKNOWLEDGEMENT_FLAG])
        self.assertEqual(code, LAUNCHER.EXIT_REFUSED)
        self.assertIn("CONFIG_REQUIRED", text)
        code, text = self._guarded_run(["--config", str(self.tmp / "absent.json"), "--output-dir", str(out),
                                        C.EXECUTION_ACKNOWLEDGEMENT_FLAG])
        self.assertEqual(code, LAUNCHER.EXIT_CONFIG_INVALID)
        self.assertIn("CONFIG_UNREADABLE", text)
        code, text = self._guarded_run(["--config", str(self.baseline_path), C.EXECUTION_ACKNOWLEDGEMENT_FLAG])
        self.assertEqual(code, LAUNCHER.EXIT_REFUSED)
        self.assertIn("OUTPUT_DIR_REQUIRED", text)
        # a VALID config with the flag proceeds to preflight (the first trap)
        code_or_exc = None
        try:
            self._guarded_run(["--config", str(self.baseline_path), "--output-dir", str(out),
                               C.EXECUTION_ACKNOWLEDGEMENT_FLAG])
        except _Boom as exc:
            code_or_exc = str(exc)
        self.assertIn("reached", code_or_exc or "")
        self.assertFalse(out.exists())

    def test_old_experiment_specific_flag_absent_from_package(self):
        for path in SURFACE_FILES:
            self.assertNotIn(OLD_FLAG, path.read_text(encoding="utf-8"), path)
        self.assertFalse(hasattr(C, "AUTHORIZATION_FLAG"))
        self.assertEqual(C.EXECUTION_ACKNOWLEDGEMENT_FLAG, "--execute-authorized-run")


# ---------------------------------------------------------------------------
# t11-t14: config-derived request accounting
# ---------------------------------------------------------------------------
class RequestCeilingTests(OfflineBase):
    def test_t11_ceiling_derives_from_arbitrary_config_values(self):
        for a4p, sl, b1p, fin in ((7, 3, 11, 2), (1, 1, 1, 1), (13, 17, 19, 23), (100, 50, 3, 9)):
            with self.subTest(a4p=a4p, sl=sl, b1p=b1p, fin=fin):
                cfg = cfg_with(selector__a4__max_pages=a4p, selector__c1__event_diverse_shortlist_size=sl,
                               selector__b1__max_pages_per_ticker=b1p, selector__b1__finalist_count=fin)
                expected = a4p + 1 + sl * b1p + fin + 1
                self.assertEqual(CFG.selector_max_requests(cfg), expected)
                self.assertEqual(CFG.whole_run_request_ceiling(cfg), expected + 4)
        # knobs that cannot change the request count do not change the ceiling
        cfg = cfg_with(selector__a4__page_limit=7, selector__a4__retained_count=3, selector__b1__page_limit=9,
                       selector__b1__lookback_seconds=60, selector__c1__depth_band="0.5000")
        self.assertEqual(CFG.whole_run_request_ceiling(cfg), 611)

    def test_t12_transport_refuses_ceiling_plus_one_before_send(self):
        for cfg in (cfg_with(selector__a4__max_pages=2, selector__c1__event_diverse_shortlist_size=1,
                             selector__b1__max_pages_per_ticker=1, selector__b1__finalist_count=1), BASELINE):
            ceiling = CFG.whole_run_request_ceiling(cfg)
            with self.subTest(ceiling=ceiling):
                sends = []
                u = simple_universe()
                t = AccountedDemoTransport(SEL, request_ceiling=ceiling,
                                           connection_factory=lambda: _FakeConn(u.route, sends))
                path = SEL.BASE_PATH + "/markets/" + TICKER
                for _ in range(ceiling):
                    t.get(path=path, query=(), headers={})
                self.assertEqual((len(t.records), len(sends)), (ceiling, ceiling))
                self.assertTrue(all(r["outcome"] == "COMPLETED" and r["retry"] is False for r in t.records))
                with self.assertRaises(RuntimeError) as ctx:
                    t.get(path=path, query=(), headers={})
                self.assertEqual(str(ctx.exception), "REQUEST_CEILING_EXCEEDED")
                self.assertEqual((len(t.records), len(sends)), (ceiling, ceiling))   # no record, no send

    def test_t13_baseline_reproduces_predecessor_ceiling_611(self):
        self.assertEqual(CFG.selector_max_requests(BASELINE), 607)
        self.assertEqual(CFG.snapshot_request_count(), 4)
        self.assertEqual(CFG.whole_run_request_ceiling(BASELINE), 611)
        # equals the predecessor formula over the canonical selector's own constants
        self.assertEqual(SEL.A4_MAX_PAGES + 1 + SEL.C1_EVENT_DIVERSE_SHORTLIST_SIZE * SEL.B1_MAX_PAGES_PER_TICKER
                         + SEL.B1_FINALIST_COUNT + 1 + 4, 611)

    def test_t14_altered_config_changes_ceiling_and_launcher_uses_it(self):
        doc = baseline_doc()
        doc["selector"]["a4"]["max_pages"] = 50
        doc["selector"]["c1"]["event_diverse_shortlist_size"] = 3
        doc["selector"]["b1"]["max_pages_per_ticker"] = 2
        doc["selector"]["b1"]["finalist_count"] = 2
        raw = to_bytes(doc)
        cfg = CFG.load_config_bytes(raw)
        self.assertEqual(CFG.whole_run_request_ceiling(cfg), 50 + 1 + 6 + 2 + 1 + 4)
        self.assertEqual(CFG.whole_run_request_ceiling(CFG.load_config_bytes(raw)), 64)   # deterministic
        h = LaunchHarness()
        h.setup(self.tmp)
        code, out, text, transports, ceilings = h.run_live(simple_universe(), raw)
        self.assertEqual(code, 0, text)
        self.assertEqual(ceilings, [64])
        manifest = json.loads((out / "RUN_MANIFEST.json").read_bytes())
        self.assertEqual(manifest["request_accounting_plan"],
                         {"selector_max_requests": 60, "snapshot_request_count": 4, "whole_run_request_ceiling": 64})
        acct = json.loads((out / "READ_REQUEST_ACCOUNTING.json").read_bytes())
        self.assertEqual(acct["whole_run_request_ceiling"], 64)
        self.assertLessEqual(acct["request_count"], 64)


# ---------------------------------------------------------------------------
# t15/t16: selector consumes config, no hidden fallback; baseline parity
# ---------------------------------------------------------------------------
def _queries(log, suffix):
    out = []
    for _m, url, _h in log:
        parts = urlsplit(url)
        if parts.path == SEL.BASE_PATH + suffix:
            out.append(parse_qsl(parts.query))
    return out


class SelectorConfigConsumptionTests(OfflineBase):
    def test_t15_request_parameters_come_from_config(self):
        cfg = cfg_with(selector__a4__page_limit=37, selector__close_window__min_seconds_to_close=60,
                       selector__close_window__max_seconds_to_close=86400, selector__market_scope__exclude_mve=False,
                       selector__b1__page_limit=11, selector__b1__lookback_seconds=3600,
                       selector__b1__exclude_block_trades=False)
        u = simple_universe()
        result, t, _ = run_selector(u, cfg)
        self.assertIsNotNone(result.success, result.halt)
        a4q = dict(_queries(u.log, "/markets")[0])
        anchor_ts = int(ANCHOR.timestamp())
        self.assertEqual((a4q["limit"], a4q["min_close_ts"], a4q["max_close_ts"]),
                         ("37", str(anchor_ts + 60), str(anchor_ts + 86400)))
        self.assertNotIn("mve_filter", a4q)
        b1q = dict(_queries(u.log, "/markets/trades")[0])
        self.assertEqual((b1q["limit"], b1q["min_ts"], b1q["max_ts"]),
                         ("11", str(anchor_ts - 3600), str(anchor_ts)))
        self.assertNotIn("is_block_trade", b1q)
        # baseline sends the canonical scope parameters
        u2 = simple_universe()
        run_selector(u2, BASELINE)
        self.assertEqual(dict(_queries(u2.log, "/markets")[0])["mve_filter"], "exclude")
        self.assertEqual(dict(_queries(u2.log, "/markets/trades")[0])["is_block_trade"], "false")
        self.assertEqual(dict(_queries(u2.log, "/markets")[0])["limit"], "500")

    def test_t15_thresholds_change_selection_outcomes(self):
        anchor_ts = int(ANCHOR.timestamp())
        # A4 ask limit: ask 0.85 is excluded at 0.8000 and eligible at 0.9000
        hi = [mkt("KXHI", yes_ask_dollars="0.8500")]
        hi_books = {"KXHI": book(yes=(("0.8000", "10.00"),), no=(("0.1500", "10.00"),))}
        r, _, _ = run_selector(Universe(hi, hi_books), BASELINE)
        self.assertEqual(r.halt["code"], "A4_NO_ELIGIBLE_CANDIDATES")
        self.assertEqual(r.diagnostics["a4"]["rejected_ask_above_limit"], 1)
        r, _, _ = run_selector(Universe(hi, hi_books), cfg_with(selector__a4__max_selected_ask="0.9000"))
        self.assertEqual(r.success["selected_ticker"], "KXHI")
        # A4 min executable ask qty
        lowq = [mkt("KXLQ", yes_ask_size_fp="2.00")]
        r, _, _ = run_selector(Universe(lowq), cfg_with(selector__a4__min_executable_ask_qty="3.00"))
        self.assertEqual(r.diagnostics["a4"]["rejected_insufficient_ask_qty"], 1)
        # close window
        late = [mkt("KXLATE", close_time="2026-10-05T06:00:00Z")]      # anchor + 18h
        r, _, _ = run_selector(Universe(late), BASELINE)
        self.assertEqual(r.halt["code"], "A4_SCOPE_CONTRADICTION")       # preserved global contradiction
        r, _, _ = run_selector(Universe(late), cfg_with(selector__close_window__max_seconds_to_close=86400))
        self.assertEqual(r.success["selected_ticker"], "KXLATE")
        # scope: status / market type are config-driven
        r, _, _ = run_selector(Universe([mkt("KXSC", market_type="scalar")]),
                               cfg_with(selector__market_scope__market_type="scalar"))
        self.assertEqual(r.success["selected_ticker"], "KXSC")
        # C1 depth band changes the C1 ranking metric
        u = Universe([mkt("KXDA"), mkt("KXDB")],
                     {"KXDA": book(yes=(("0.3700", "50.00"), ("0.4000", "1.00")), no=(("0.5500", "1.00"), ("0.5200", "50.00"))),
                      "KXDB": book(yes=(("0.4000", "2.00"),), no=(("0.5500", "2.00"),))})
        r_narrow, _, _ = run_selector(u, cfg_with(selector__b1__finalist_count=1,
                                                  selector__c1__event_diverse_shortlist_size=1))
        u = Universe(u.markets, u.books)
        r_wide, _, _ = run_selector(u, cfg_with(selector__b1__finalist_count=1,
                                                selector__c1__event_diverse_shortlist_size=1,
                                                selector__c1__depth_band="0.0300"))
        self.assertEqual((r_narrow.success["selected_ticker"], r_wide.success["selected_ticker"]), ("KXDB", "KXDA"))
        # shortlist size / finalist count drive B1 and C2 request counts
        u = simple_universe(6)
        r, t, _ = run_selector(u, cfg_with(selector__c1__event_diverse_shortlist_size=4, selector__b1__finalist_count=2))
        self.assertEqual(len(_queries(u.log, "/markets/trades")), 4)
        c2_market_reads = [x for x in u.log if urlsplit(x[1]).path.startswith(SEL.BASE_PATH + "/markets/KXU-")]
        self.assertEqual(len(c2_market_reads), 2)
        self.assertEqual((r.success["c1_shortlist_count"], r.success["b1_finalist_count"]), (4, 2))
        # A4 retained count bounds the C1 request
        u = simple_universe(6)
        r, _, _ = run_selector(u, cfg_with(selector__a4__retained_count=2))
        self.assertEqual(len([v for k, v in _queries(u.log, "/markets/orderbooks")[0] if k == "tickers"]), 2)
        self.assertEqual(r.diagnostics["a4"]["retained_count"], 2)
        # A4 max pages bounds discovery
        u = simple_universe(2, a4_pages=3)
        r, _, _ = run_selector(u, cfg_with(selector__a4__max_pages=2))
        self.assertEqual(r.halt["code"], "MARKET_DISCOVERY_INCOMPLETE")
        self.assertEqual(r.diagnostics["a4"]["pages_requested"], 2)
        u = simple_universe(2, a4_pages=3)
        r, _, _ = run_selector(u, cfg_with(selector__a4__max_pages=3))
        self.assertIsNotNone(r.success)
        # B1 lookback excludes an old trade only when the window is short
        old = [{"is_block_trade": False, "count_fp": "1.00", "created_time": "2026-10-04T08:00:00Z"}]  # anchor - 4h
        u = Universe([mkt("KXOLD")], trades={"KXOLD": old})
        r, _, _ = run_selector(u, cfg_with(selector__b1__lookback_seconds=3600))
        self.assertEqual(r.diagnostics["b1"]["incomplete_reasons"]["PAGE_SCOPE_VIOLATION"], 1)
        u = Universe([mkt("KXOLD")], trades={"KXOLD": old})
        r, _, _ = run_selector(u, BASELINE)
        self.assertEqual(r.success["selected_ticker"], "KXOLD")
        self.assertEqual(anchor_ts, int(ANCHOR.timestamp()))
        # block-trade rows are a scope violation only while exclude_block_trades is true
        blk = [{"is_block_trade": True, "count_fp": "1.00", "created_time": TRADE_TIME}]
        r, _, _ = run_selector(Universe([mkt("KXBLK")], trades={"KXBLK": blk}), BASELINE)
        self.assertEqual(r.halt["code"], "B1_NO_FINALISTS")
        r, _, _ = run_selector(Universe([mkt("KXBLK")], trades={"KXBLK": blk}),
                               cfg_with(selector__b1__exclude_block_trades=False))
        self.assertEqual(r.success["selected_ticker"], "KXBLK")

    def test_t15_baseline_parity_with_canonical_selector(self):
        """Under the baseline config the configurable selector issues the exact
        same request sequence and selects the same ticker as canonical
        ``select_d07_ticker`` over the same deterministic fake universe."""
        markets = [mkt(f"KXP-{i:02d}", yes_bid_dollars=f"0.{30 + i:02d}00", yes_ask_dollars=f"0.{40 + i:02d}00",
                       volume_24h_fp=f"{i}.00") for i in range(25)]
        markets.append(mkt("KXP-DUPEV", event="EV-KXP-03"))
        markets.append(mkt("KXP-HIASK", yes_ask_dollars="0.9000"))
        books = {m["ticker"]: book(yes=((m["yes_bid_dollars"], "5.00"),),
                                   no=((format(D(1) - D(m["yes_ask_dollars"]), "f"), "6.00"),)) for m in markets}
        trades = {"KXP-02": ZERO_TRADES, "KXP-05": "HTTP500", "KXP-07": "RAISE"}
        for cfg_label in ("baseline",):
            ua, ub = Universe(markets, books, trades, a4_pages=3), Universe(markets, books, trades, a4_pages=3)
            ra, _, _ = run_selector(ua, BASELINE)
            ta = ub.transport()
            rb = SEL.select_d07_ticker(transport=ta, signer=FakeSigner(), now_utc=lambda: ANCHOR)
            self.assertIsNotNone(rb.success, rb.halt)
            self.assertEqual(ra.success["selected_ticker"], rb.success.selected_ticker, cfg_label)
            self.assertEqual(ra.success["final_spread_dollars"], rb.success.final_spread_dollars)
            self.assertEqual((ra.success["a4_retained_count"], ra.success["c1_shortlist_count"],
                              ra.success["b1_finalist_count"]),
                             (rb.success.a4_eligible_count, rb.success.c1_shortlist_count, rb.success.b1_finalist_count))
            self.assertEqual([u for _m, u, _h in ua.log], [u for _m, u, _h in ub.log])
        # pure screens are identical to the canonical screens under the baseline
        min_ts, max_ts = CS._close_bounds(BASELINE, ANCHOR)
        variants = markets + [mkt("X1", status="closed"), mkt("X2", exchange_index=1), mkt("X3", market_type="scalar"),
                              mkt("X4", close_time="bad"), mkt("X5", price_ranges=[]), mkt("X6", yes_bid_dollars=None),
                              mkt("X7", yes_ask_size_fp="0.50"), mkt("X8", mve_collection_ticker="M"),
                              mkt("X9", close_time="2026-10-05T06:00:00Z"), mkt("", event=""),
                              mkt("X10", exchange_index=True), mkt("X11", yes_bid_dollars="0.5000")]
        for m in variants:
            with self.subTest(ticker=m["ticker"]):
                ours = CS.screen_market(SEL, m, cfg=BASELINE, min_close_ts=min_ts, max_close_ts=max_ts)
                self.assertEqual(ours[:3], SEL.screen_a4_market(m, min_close_ts=min_ts, max_close_ts=max_ts))
        a4_row = {"event_ticker": "E", "a4_rank": 1, "volume_24h": D("1"), "open_interest": D("0")}
        book_variants = [book(), book(yes=(("0.6000", "1.00"),)), book(no=(("0.1000", "5.00"),)),
                         book(no=(("0.5500", "0.50"),)), {"yes_dollars": "x", "no_dollars": []}, None,
                         book(yes=(("0.3900", "3.00"), ("0.4000", "1.00")), no=(("0.5500", "4.00"), ("0.5400", "9.00")))]
        for i, b in enumerate(book_variants):
            item = {"ticker": "T"} if b is None else {"ticker": "T", "orderbook_fp": b}
            with self.subTest(book=i):
                ours = CS.screen_book(SEL, item, a4_row=a4_row, cfg=BASELINE)
                self.assertEqual(ours[:2], SEL.screen_c1_orderbook(item, a4_row=a4_row))

    def test_t16_no_hidden_fallback_to_predecessor_hard_coded_values(self):
        forbidden_attrs = {"MIN_SECONDS_TO_CLOSE", "MAX_SECONDS_TO_CLOSE", "A4_PAGE_LIMIT", "A4_MAX_PAGES",
                           "A4_RETAINED_COUNT", "C1_EVENT_DIVERSE_SHORTLIST_SIZE", "DEPTH_BAND",
                           "B1_LOOKBACK_SECONDS", "B1_PAGE_LIMIT", "B1_MAX_PAGES_PER_TICKER", "B1_FINALIST_COUNT",
                           "MAX_SELECTED_ASK", "MIN_EXECUTABLE_ASK_QTY", "MINIMUM_SPREAD_USD_MATRIX", "TRIAL_G"}
        forbidden_calls = {"screen_a4_market", "screen_c1_orderbook", "discover_a4_candidates", "validate_c1",
                           "fetch_b1_trade_window", "evaluate_b1", "revalidate_c2", "select_d07_ticker",
                           "build_c1_event_diverse_shortlist", "_fetch_markets_page", "_screen_b1_trades_page"}
        for path in SURFACE_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, forbidden_attrs | forbidden_calls, f"{path.name}:{node.lineno}")
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, forbidden_attrs, f"{path.name}:{node.lineno}")
        for name in ("TRIAL_G", "MINIMUM_SPREAD_USD_MATRIX", "QUOTE_QUANTITY", "AUTHORIZATION_FLAG",
                     "DEFAULT_OUTPUT_ROOT"):
            self.assertFalse(hasattr(C, name), name)
        # no default for any knob: the loader has no fallback dictionary
        src = inspect.getsource(CFG)
        self.assertNotIn(".get(", src.split("def load_config_bytes")[1].split("def selector_max_requests")[0])
        # behavioural proof: poison every canonical experiment constant in a module COPY
        poisoned = types.ModuleType(SEL.__name__ + "_poisoned_copy")
        poisoned.__dict__.update({k: v for k, v in vars(SEL).items() if k != "__name__"})
        poisoned.__dict__.update({"MIN_SECONDS_TO_CLOSE": 10 ** 9, "MAX_SECONDS_TO_CLOSE": 10 ** 9 + 1,
                                  "A4_PAGE_LIMIT": 1, "A4_MAX_PAGES": 0, "A4_RETAINED_COUNT": 0,
                                  "C1_EVENT_DIVERSE_SHORTLIST_SIZE": 0, "DEPTH_BAND": D("0"),
                                  "B1_LOOKBACK_SECONDS": 0, "B1_PAGE_LIMIT": 1, "B1_MAX_PAGES_PER_TICKER": 0,
                                  "B1_FINALIST_COUNT": 0, "MAX_SELECTED_ASK": D("0.0001"),
                                  "MIN_EXECUTABLE_ASK_QTY": D("100000")})
        ua, ub = simple_universe(4), simple_universe(4)
        ra, _, _ = run_selector(ua, BASELINE, sel=SEL)
        rb, _, _ = run_selector(ub, BASELINE, sel=poisoned)
        self.assertIsNotNone(rb.success, rb.halt)
        self.assertEqual(ra.success, rb.success)
        self.assertEqual([u for _m, u, _h in ua.log], [u for _m, u, _h in ub.log])
        self.assertEqual(SEL.A4_PAGE_LIMIT, 500)   # the real canonical module is untouched


# ---------------------------------------------------------------------------
# t17/t18: diagnostics funnel and relaxed-B1 SHADOW_ONLY semantics
# ---------------------------------------------------------------------------
def funnel_universe():
    markets = [
        mkt("", event="EV-ID"),                                        # missing identity
        mkt("M-STATUS", status="closed"),
        mkt("M-MULTI", status="closed", market_type="scalar"),         # first failure = status
        mkt("M-EXIDX", exchange_index=1),
        mkt("M-TYPE", market_type="scalar"),
        mkt("M-CLOSE", close_time="garbage"),
        mkt("M-RANGES", price_ranges=[]),
        mkt("M-ONESIDED", yes_bid_dollars=None),
        mkt("M-ASKHI", yes_ask_dollars="0.9000"),
        mkt("M-QTY", yes_ask_size_fp="0.50"),
    ] + [mkt(f"E{i}") for i in range(1, 8)] + [mkt("E8", event="EV-E7"), mkt("E9")]
    books = {"E2": None,                                                # orderbook_fp missing
             "E3": book(yes=(("0.6000", "10.00"),))}                    # crossed
    trades = {"E1": ACTIVE, "E4": ZERO_TRADES, "E5": "HTTP500", "E6": "RAISE", "E7": ACTIVE, "E9": ACTIVE}
    c2_markets = {"E1": mkt("E1", status="closed")}
    c2_books = {"E9": book(yes=(("0.6000", "10.00"),))}
    return Universe(markets, books, trades, c2_markets=c2_markets, c2_books=c2_books)


class DiagnosticsTests(OfflineBase):
    def test_t17_diagnostic_counters_match_deterministic_funnel(self):
        u = funnel_universe()
        r, t, _ = run_selector(u, BASELINE)
        self.assertIsNotNone(r.success, r.halt)
        self.assertEqual(r.success["selected_ticker"], "E7")
        d = r.diagnostics
        a4 = d["a4"]
        self.assertEqual((a4["pages_requested"], a4["market_rows_seen"], a4["eligible_count"], a4["retained_count"]),
                         (1, 19, 9, 9))
        self.assertEqual({k: a4[k] for k in CS.A4_REJECTION_ORDER}, {
            "rejected_missing_identity": 1, "rejected_status": 2, "rejected_exchange_index": 1,
            "rejected_market_type": 1, "rejected_close_window": 1, "rejected_price_ranges": 1,
            "rejected_not_two_sided": 1, "rejected_ask_above_limit": 1, "rejected_insufficient_ask_qty": 1,
            "rejected_mve": 0})
        self.assertEqual(a4["check_failures_nonexclusive"]["rejected_market_type"], 2)
        self.assertEqual(sum(a4[k] for k in CS.A4_REJECTION_ORDER) + a4["eligible_count"], a4["market_rows_seen"])
        c1 = d["c1"]
        self.assertEqual((c1["requested_count"], c1["rejected_malformed_or_ineligible_book"], c1["eligible_count"],
                          c1["event_duplicate_skipped"], c1["shortlist_count"]), (9, 2, 7, 1, 6))
        self.assertEqual(c1["rejection_reasons"]["BOOK_OBJECT_MISSING"], 1)
        self.assertEqual(c1["rejection_reasons"]["BOOK_CROSSED_OR_LOCKED"], 1)
        b1 = d["b1"]
        self.assertEqual((b1["ticker_count"], b1["complete_active_count"], b1["complete_zero_or_inactive_count"],
                          b1["incomplete_count"], b1["transport_failure_count"], b1["finalist_count"],
                          b1["pages_requested"]), (6, 3, 1, 2, 1, 3, 6))
        self.assertEqual(b1["incomplete_reasons"]["UNEXPECTED_HTTP_STATUS"], 1)
        self.assertEqual(b1["incomplete_reasons"]["TRANSPORT_FAILURE"], 1)
        c2 = d["c2"]
        self.assertEqual((c2["finalist_input_count"], c2["market_reject_count"], c2["book_reject_count"],
                          c2["surviving_count"]), (3, 1, 1, 1))
        self.assertEqual(c2["market_reject_reasons"], {"rejected_status": 1})
        self.assertEqual(c2["book_reject_reasons"]["BOOK_CROSSED_OR_LOCKED"], 1)
        self.assertIsNone(d["halt"])
        # request accounting agrees with the diagnostics: A4 1 + C1 1 + B1 6 + C2 3 + 1
        self.assertEqual(len(t.records), 12)
        self.assertEqual(sum(1 for r_ in t.records if r_["outcome"] == "TRANSPORT_FAILURE"), 1)

    def test_t17_accepted_live_shape_57_pages_1_candidate_b1_no_finalists(self):
        """Reproduces the accepted live funnel shape (57 A4 pages -> 1 C1
        candidate -> B1_NO_FINALISTS; 59 GETs) and shows the diagnostics now
        explain it (the one B1 window was COMPLETE_ZERO)."""
        u = Universe([mkt("KXONLY")], trades={"KXONLY": ZERO_TRADES}, a4_pages=57)
        r, t, _ = run_selector(u, BASELINE)
        self.assertEqual(r.halt["code"], "B1_NO_FINALISTS")
        self.assertEqual(len(t.records), 59)
        d = r.diagnostics
        self.assertEqual((d["a4"]["pages_requested"], d["c1"]["shortlist_count"], d["b1"]["ticker_count"],
                          d["b1"]["complete_zero_or_inactive_count"], d["b1"]["finalist_count"]), (57, 1, 1, 1, 0))
        self.assertFalse(d["c2"]["reached"])
        self.assertEqual(d["halt"]["code"], "B1_NO_FINALISTS")

    def test_t17_global_contradictions_preserved(self):
        cases = [
            ([mkt("A"), mkt("A")], "A4_DUPLICATE_TICKER", "DUPLICATE_TICKER"),
            ([mkt("A", close_time="2026-10-05T06:00:00Z")], "A4_SCOPE_CONTRADICTION", "CLOSE_TIME_OUTSIDE_REQUEST_WINDOW"),
            ([mkt("A", mve_selected_legs=[{"x": 1}])], "A4_SCOPE_CONTRADICTION", "MVE_EVIDENCE_CONTRADICTS_EXCLUDE"),
            ([mkt("A"), "not-an-object"], "RESPONSE_MALFORMED", "NON_OBJECT_MARKET_ROW"),
        ]
        for markets, code, contradiction in cases:
            with self.subTest(code=code, contradiction=contradiction):
                r, _, _ = run_selector(Universe(markets), BASELINE)
                self.assertEqual(r.halt["code"], code)
                self.assertEqual(r.diagnostics["a4"]["global_contradiction"], contradiction)
        # MVE evidence is not a contradiction when MVE exclusion is configured off
        r, _, _ = run_selector(Universe([mkt("A", mve_selected_legs=[{"x": 1}])]),
                               cfg_with(selector__market_scope__exclude_mve=False))
        self.assertEqual(r.success["selected_ticker"], "A")
        # C1 ticker-set mismatch remains a global halt
        u = simple_universe(2)
        orig = u._book_item
        u._book_item = lambda t: orig("WRONG")
        r, _, _ = run_selector(u, BASELINE)
        self.assertEqual(r.halt["code"], "C1_TICKER_SET_MISMATCH")

    def test_b1_request_ceiling_refusal_is_global_halt_not_silent_exclusion(self):
        u = simple_universe(3)
        r, t, _ = run_selector(u, BASELINE, ceiling=3)   # A4 1 + C1 1 + one B1 page
        self.assertEqual(r.halt["code"], "TRANSPORT_FAILURE")
        self.assertEqual(r.halt["detail"], "REQUEST_CEILING_EXCEEDED")
        self.assertEqual(len(t.records), 3)


class RelaxedB1Tests(OfflineBase):
    def test_t18_relaxed_mode_selects_zero_window_as_shadow_only(self):
        relaxed = cfg_with(selector__b1__require_complete_active_window=False)
        r, _, _ = run_selector(Universe([mkt("KXZ")], trades={"KXZ": ZERO_TRADES}), relaxed)
        self.assertEqual(r.success["selected_ticker"], "KXZ")
        self.assertTrue(r.success["selected_via_relaxed_b1"])
        self.assertEqual(r.success["selected_b1_window_status"], "COMPLETE_ZERO")
        self.assertEqual(r.success["selection_authority"], C.SHADOW_ONLY_AUTHORITY)
        self.assertEqual((r.success["writer_qualification"], r.success["trade_eligibility"]), ("NONE", "NONE"))
        self.assertIn("SHADOW_ONLY", r.success["b1_selection_mode"])
        self.assertEqual(r.diagnostics["b1"]["admitted_complete_zero_shadow_only"], 1)
        # strict mode never admits it
        r, _, _ = run_selector(Universe([mkt("KXZ")], trades={"KXZ": ZERO_TRADES}), BASELINE)
        self.assertEqual(r.halt["code"], "B1_NO_FINALISTS")
        # incomplete windows are never admitted, even relaxed
        for spec in ("HTTP500", "RAISE"):
            with self.subTest(spec=spec):
                r, _, _ = run_selector(Universe([mkt("KXI")], trades={"KXI": spec}), relaxed)
                self.assertEqual(r.halt["code"], "B1_NO_FINALISTS")
        # every COMPLETE_ACTIVE window ranks ahead of every relaxed COMPLETE_ZERO window
        u = Universe([mkt("KXA", yes_ask_dollars="0.4600"), mkt("KXZ")],
                     {"KXA": book(no=(("0.5400", "10.00"),))}, {"KXA": ACTIVE, "KXZ": ZERO_TRADES})
        r, _, _ = run_selector(u, cfg_with(selector__b1__require_complete_active_window=False,
                                           selector__b1__finalist_count=1))
        self.assertEqual(r.success["selected_ticker"], "KXA")
        self.assertFalse(r.success["selected_via_relaxed_b1"])

    def test_t18_relaxed_selection_cannot_become_writer_authority(self):
        h = LaunchHarness()
        h.setup(self.tmp)
        raw = with_value("selector.b1.require_complete_active_window", False)
        code, out, text, _t, _c = h.run_live(Universe([mkt(TICKER)], trades={TICKER: ZERO_TRADES}), raw)
        self.assertEqual(code, 0, text)
        sel_result = json.loads((out / "SELECTOR_RESULT.json").read_bytes())
        self.assertTrue(sel_result["result"]["selected_via_relaxed_b1"])
        self.assertEqual(sel_result["selection_authority"], C.SHADOW_ONLY_AUTHORITY)
        snap = json.loads((out / "LIVE_READ_SNAPSHOT_SANITIZED.json").read_bytes())
        self.assertEqual(snap["selection_authority"], C.SHADOW_ONLY_AUTHORITY)
        self.assertTrue(snap["selected_via_relaxed_b1"])
        for name in ("TERMINAL_RESULT.json", "RUN_MANIFEST.json", "SHADOW_MATRIX.json"):
            self.assertEqual(json.loads((out / name).read_bytes())["selection_authority"], C.SHADOW_ONLY_AUTHORITY)
        blob = b"".join(p.read_bytes() for p in out.iterdir())
        for token in (b"WRITER_ELIGIBLE", b"NormalWriterPermit", b"plan_sha256", b"quote_generation_id",
                      b'"risk_control_state"'):
            self.assertNotIn(token, blob)
        matrix = json.loads((out / "SHADOW_MATRIX.json").read_bytes())
        for row in matrix["rows"]:
            self.assertTrue(row["shadow_authority"].startswith("NON_AUTHORITATIVE"))
            with self.assertRaises(TypeError):
                MM.QuotePlanV1(**row)
        self.assertIn("SHADOW_ONLY", (out / "CAPABILITY_ACTIVITY.txt").read_text())


# ---------------------------------------------------------------------------
# deterministic fake git for in-repository provenance (no real repository
# state is required or mutated; on-disk blobs are computed from the real files)
# ---------------------------------------------------------------------------
FAKE_HEAD = "a" * 40
FAKE_TREE = "b" * 40
FAKE_PARENT = "c" * 40


def make_fake_git(*, origin="https://github.com/rigolugo/ARB.git", branch="main", status="", parents=(FAKE_PARENT,),
                  blob_overrides=None, committed_modules=None, untracked=()):
    blob_overrides = dict(blob_overrides or {})
    calls = []

    def fake_git(repo, *args):
        calls.append(args)
        if args == ("remote", "get-url", "origin"):
            return origin
        if args == ("rev-parse", "HEAD"):
            return FAKE_HEAD
        if args == ("rev-parse", "HEAD^{tree}"):
            return FAKE_TREE
        if args[:3] == ("rev-list", "--parents", "-n"):
            return " ".join((FAKE_HEAD, *parents))
        if args == ("symbolic-ref", "--short", "HEAD"):
            if branch is None:
                raise CB.PreconditionFailed("PRECONDITION_FAILED", "git symbolic-ref --short")
            return branch
        if args[:1] == ("status",):
            return status
        if args[:3] == ("ls-tree", "--name-only", "HEAD"):
            if committed_modules is not None:
                return "\n".join(committed_modules)
            return "\n".join(CB.self_surface_paths(repo)[1:])
        if args[:1] == ("rev-parse",) and args[1].startswith("HEAD:"):
            rel = args[1][len("HEAD:"):]
            if rel in untracked:
                raise CB.PreconditionFailed("PRECONDITION_FAILED", "git rev-parse")
            if rel in blob_overrides:
                return blob_overrides[rel]
            return CB._blob_id((Path(repo) / rel).read_bytes())
        raise AssertionError(f"unexpected git call {args}")
    fake_git.calls = calls
    return fake_git


def fake_live_provenance(**kw):
    def provenance(repo, report, *, live):
        return CB.verify_repository_provenance(repo, report, live=live, git=make_fake_git(**kw))
    return provenance


# ---------------------------------------------------------------------------
# launcher harness and end-to-end evidence (t14, t18, t19, t20, t22)
# ---------------------------------------------------------------------------
class LaunchHarness:
    def setup(self, tmp: Path):
        self.tmp = tmp
        self.key = _synthetic_key_file(tmp)
        self.env = {C.API_KEY_ID_ENV: SECRET_KEY_ID, C.PRIVATE_KEY_PATH_ENV: str(self.key)}
        self.signatures = []

    def run_live(self, universe, config_bytes=BASELINE_BYTES, *, out_name="out", select_fn=None):
        cfg_path = self.tmp / f"config_{out_name}.json"
        cfg_path.write_bytes(config_bytes)
        out = self.tmp / out_name
        transports, ceilings = [], []
        harness = self

        def tf(sel, ceiling):
            ceilings.append(ceiling)
            t = AccountedDemoTransport(sel, request_ceiling=ceiling,
                                       connection_factory=lambda: _FakeConn(universe.route, universe.log))
            transports.append(t)
            return t

        class RecordingSigner:
            def __init__(self, sel):
                self.inner = sel.EnvironmentRsaSigner()

            def sign(self, **kw):
                key_id, sig = self.inner.sign(**kw)
                harness.signatures.append(sig)
                return key_id, sig

        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=False), contextlib.redirect_stdout(buf), \
                mock.patch.object(LAUNCHER, "verify_repository_provenance", fake_live_provenance()):
            os.environ.pop(C.LEGACY_PRIVATE_KEY_PEM_ENV, None)
            code = LAUNCHER.run(["--config", str(cfg_path), "--output-dir", str(out),
                                 C.EXECUTION_ACKNOWLEDGEMENT_FLAG], env=os.environ, transport_factory=tf,
                                signer_factory=RecordingSigner, select_fn=select_fn, interpreter_check=False,
                                now_utc=lambda: ANCHOR)
        return code, out, buf.getvalue(), transports, ceilings


EVIDENCE_FILES = ("RUN_MANIFEST.json", "READ_REQUEST_ACCOUNTING.json", "SELECTOR_RESULT.json",
                  "SELECTOR_DIAGNOSTICS.json", "SELECTOR_CONFIG_INPUT.json", "SELECTOR_CONFIG_EFFECTIVE.json",
                  "LIVE_READ_SNAPSHOT_SANITIZED.json", "SHADOW_MATRIX.json", "SHADOW_MATRIX.csv",
                  "TERMINAL_RESULT.json", "CAPABILITY_ACTIVITY.txt", "EVIDENCE_MANIFEST.json")


class LauncherTests(OfflineBase):
    def setUp(self):
        super().setUp()
        self.h = LaunchHarness()
        self.h.setup(self.tmp)

    def test_t19_full_mocked_live_flow_emits_exact_config_evidence(self):
        u = simple_universe(3)
        u.markets[0]["ticker"] = TICKER
        code, out, text, transports, ceilings = self.h.run_live(u)
        self.assertEqual(code, 0, text)
        self.assertEqual(ceilings, [611])
        names = sorted(p.name for p in out.iterdir())
        self.assertEqual(sorted(EVIDENCE_FILES), names)
        self.assertEqual((out / "SELECTOR_CONFIG_INPUT.json").read_bytes(), BASELINE_BYTES)
        manifest = json.loads((out / "RUN_MANIFEST.json").read_bytes())
        self.assertEqual(manifest["config"]["sha256"], BASELINE_SHA256)
        self.assertEqual(manifest["config"]["bytes"], len(BASELINE_BYTES))
        self.assertEqual(manifest["config"]["filename_as_supplied"], str(self.tmp / "config_out.json"))
        eff_bytes = (out / "SELECTOR_CONFIG_EFFECTIVE.json").read_bytes()
        self.assertEqual(json.loads(eff_bytes), json.loads(LAUNCHER._dump(CFG.effective_config_document(BASELINE))))
        self.assertEqual(manifest["config"]["effective_sha256"], hashlib.sha256(eff_bytes).hexdigest())
        self.assertEqual(json.loads(eff_bytes)["derived"]["whole_run_request_ceiling"], 611)
        self.assertEqual(manifest["request_accounting_plan"],
                         {"selector_max_requests": 607, "snapshot_request_count": 4, "whole_run_request_ceiling": 611})
        ack = manifest["cli_acknowledgement"]
        self.assertEqual(ack, {"flag": "--execute-authorized-run", "acknowledgement_present": True,
                               "semantics": C.EXECUTION_ACKNOWLEDGEMENT_SEMANTICS,
                               "live_authorization": C.EXTERNAL_AUTHORIZATION_STATEMENT})
        self.assertEqual(manifest["mode"], "LIVE")
        self.assertEqual(manifest["run_id"], "g1_shadow_experiment_02")
        blob_text = b"".join(p.read_bytes() for p in out.iterdir()).decode("utf-8")
        for claim in ('"authorized": true', '"authorization_granted"', '"live_run_authorized": true'):
            self.assertNotIn(claim, blob_text)
        diag = json.loads((out / "SELECTOR_DIAGNOSTICS.json").read_bytes())
        self.assertEqual(diag["schema"], "ShadowSelectorDiagnosticsV1")
        self.assertTrue(all(diag[p]["reached"] for p in ("a4", "c1", "b1", "c2")))
        t = transports[0]
        snapshot_reads = [r for r in t.records if r["phase"].startswith("SNAPSHOT")]
        self.assertEqual([r["phase"] for r in snapshot_reads], list(C.SNAPSHOT_READ_PLAN))
        self.assertTrue(all(r["method"] == "GET" and r["outcome"] == "COMPLETED" for r in t.records))
        self.assertTrue(all(m == "GET" for m, _u, _h in u.log))
        self.assertEqual([r["authenticated"] for r in snapshot_reads], [False, True, True, True])
        q = dict(map(tuple, snapshot_reads[2]["query"]))
        self.assertEqual((q["subaccount"], q["exchange_index"]), ("1", "0"))
        acct = json.loads((out / "READ_REQUEST_ACCOUNTING.json").read_bytes())
        self.assertEqual(acct["request_count"], len(t.records))
        self.assertEqual(acct["methods"], ["GET"])
        self.assertEqual((acct["demo_write_count"], acct["automatic_retries"]), (0, 0))
        matrix = json.loads((out / "SHADOW_MATRIX.json").read_bytes())
        self.assertEqual([r["minimum_spread_usd"] for r in matrix["rows"]],
                         ["0.0100", "0.0200", "0.0300", "0.0400", "0.0500"])
        self.assertFalse(matrix["winner_selected"])
        term = json.loads((out / "TERMINAL_RESULT.json").read_bytes())
        self.assertEqual(term["config_sha256"], BASELINE_SHA256)
        self.assertTrue(term["no_profitability_claim"])
        ev = json.loads((out / "EVIDENCE_MANIFEST.json").read_bytes())
        for name, meta in ev["files"].items():
            data = (out / name).read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (meta["bytes"], meta["sha256"]))

    def test_sweep_uses_config_spreads_and_trial_g(self):
        raw = to_bytes({**baseline_doc(), "shadow_experiment": {"trial_g": 2,
                                                                 "minimum_spread_usd": ["0.0700", "0.0300"]}})
        u = simple_universe(2)
        code, out, text, _t, _c = self.h.run_live(u, raw)
        self.assertEqual(code, 0, text)
        matrix = json.loads((out / "SHADOW_MATRIX.json").read_bytes())
        self.assertEqual(matrix["minimum_spread_matrix"], ["0.0700", "0.0300"])
        self.assertEqual([r["minimum_spread_usd"] for r in matrix["rows"]], ["0.0700", "0.0300"])
        self.assertEqual({r["trial_G"] for r in matrix["rows"]}, {2})
        self.assertEqual(matrix["canonical_G_selection"], "UNSELECTED")

    def test_t20_replay_mode_is_network_and_credential_free(self):
        u = simple_universe(2)
        code, out, text, _t, _c = self.h.run_live(u)
        self.assertEqual(code, 0, text)
        replay_out = self.tmp / "replay"
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False), contextlib.redirect_stdout(buf):
            for name in (C.API_KEY_ID_ENV, C.PRIVATE_KEY_PATH_ENV, C.LEGACY_PRIVATE_KEY_PEM_ENV):
                os.environ.pop(name, None)
            with mock.patch.object(LAUNCHER, "verify_credential_presence", side_effect=_forbid("credentials")):
                rc = LAUNCHER.run(["--config", str(self.baseline_path),
                                   "--output-dir", str(replay_out), "--replay-snapshot",
                                   str(out / "LIVE_READ_SNAPSHOT_SANITIZED.json")],
                                  interpreter_check=False, transport_factory=_forbid("transport"),
                                  signer_factory=_forbid("signer"), select_fn=_forbid("selector"))
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertEqual((replay_out / "SHADOW_MATRIX.json").read_bytes(), (out / "SHADOW_MATRIX.json").read_bytes())
        self.assertEqual((replay_out / "SELECTOR_CONFIG_INPUT.json").read_bytes(), BASELINE_BYTES)
        diag = json.loads((replay_out / "SELECTOR_DIAGNOSTICS.json").read_bytes())
        self.assertFalse(diag["selector_invoked"])
        acct = json.loads((replay_out / "READ_REQUEST_ACCOUNTING.json").read_bytes())
        self.assertEqual(acct["request_count"], 0)
        self.assertIn("kalshi_demo_read_network = NONE", (replay_out / "CAPABILITY_ACTIVITY.txt").read_text())
        manifest = json.loads((replay_out / "RUN_MANIFEST.json").read_bytes())
        self.assertEqual(manifest["mode"], "REPLAY")
        self.assertFalse(manifest["cli_acknowledgement"]["acknowledgement_present"])
        # a replay snapshot of the wrong schema is refused
        bad = self.tmp / "bad_snapshot.json"
        bad.write_bytes(b'{"schema": "G1ShadowLiveSnapshotSanitizedV1"}')
        with contextlib.redirect_stdout(io.StringIO()):
            rc = LAUNCHER.run(["--config", str(self.baseline_path),
                               "--output-dir", str(self.tmp / "replay2"), "--replay-snapshot", str(bad)],
                              interpreter_check=False)
        self.assertEqual(rc, LAUNCHER.EXIT_PRECONDITION_FAILED)
        self.assertFalse((self.tmp / "replay2").exists())

    def test_t22_no_secret_values_in_any_output(self):
        u = simple_universe(2)
        code, out, text, transports, _c = self.h.run_live(u)
        self.assertEqual(code, 0, text)
        self.assertGreaterEqual(len(self.h.signatures), 4)   # C1, C2, snapshot book, positions, orders
        blob = b"".join(p.read_bytes() for p in out.iterdir()) + text.encode()
        blob += json.dumps(transports[0].records).encode()
        self.assertNotIn(SECRET_KEY_ID.encode(), blob)
        self.assertNotIn(str(self.h.key).encode(), blob)
        self.assertNotIn(b"PRIVATE KEY", blob)
        self.assertNotIn(self.h.key.read_bytes()[40:80], blob)
        for sig in self.h.signatures:
            self.assertNotIn(sig.encode(), blob)
        # the header VALUES really were sent (proves the scan is meaningful)
        sent = [h for _m, _u, h in u.log if "KALSHI-ACCESS-KEY" in h]
        self.assertTrue(sent and all(h["KALSHI-ACCESS-KEY"] == SECRET_KEY_ID for h in sent))

    def test_existing_output_dir_refused(self):
        (self.tmp / "out").mkdir()
        code, _, text, _t, _c = self.h.run_live(simple_universe())
        self.assertEqual(code, LAUNCHER.EXIT_PRECONDITION_FAILED)
        self.assertIn("PRECONDITION_FAILED", text)

    def test_incomplete_body_terminates_without_retry(self):
        for i, path in enumerate(("/portfolio/positions", "/portfolio/orders")):
            with self.subTest(path=path):
                u = simple_universe(2, short_path=path)
                code, out, _t, transports, _c = self.h.run_live(u, out_name=f"inc{i}")
                self.assertEqual(code, 0)
                term = json.loads((out / "TERMINAL_RESULT.json").read_bytes())
                self.assertEqual(term["terminal_classification"], "LIVE_READ_INCOMPLETE")
                self.assertFalse((out / "SHADOW_MATRIX.json").exists())
                hits = [r for r in transports[0].records if r["path"].endswith(path)]
                self.assertEqual(len(hits), 1)   # zero retries
                self.assertEqual(hits[0]["outcome"], "INCOMPLETE_RESPONSE_BODY")

    def test_nonflat_or_resting_or_paginated_inventory_stays_unknown(self):
        cases = {
            "nonzero_position": ({"market_positions": [{"ticker": "KXU-00", "subaccount": 1, "exchange_index": 0,
                                                        "position_count_fp": "2.00"}], "event_positions": [],
                                  "cursor": ""}, None),
            "paginated_positions": ({"market_positions": [], "event_positions": [], "cursor": "c1"}, None),
            "resting_order": (None, {"orders": [{"order_id": "o1", "ticker": "KXU-00", "subaccount": 1,
                                                 "exchange_index": 0, "status": "resting", "side": "yes",
                                                 "remaining_count_fp": "1.00", "yes_price_dollars": "0.3900"}],
                                     "cursor": ""}),
        }
        for i, (label, (pos, ords)) in enumerate(cases.items()):
            with self.subTest(label=label):
                u = Universe([mkt("KXU-00")], positions=pos, orders=ords)
                code, out, _t, _tr, _c = self.h.run_live(u, out_name=f"inv{i}")
                self.assertEqual(code, 0)
                m = json.loads((out / "SHADOW_MATRIX.json").read_bytes())
                self.assertEqual(m["terminal"], "SHADOW_INPUT_UNKNOWN")
                for row in m["rows"]:
                    self.assertIsNone(row["shadow_lower_candidate"])
                    self.assertIsNone(row["shadow_upper_candidate"])
                    self.assertEqual(row["inventory_observation"], "UNKNOWN")
                self.assertNotIn(b'"o1"', (out / "LIVE_READ_SNAPSHOT_SANITIZED.json").read_bytes())

    def test_selector_halt_is_terminal_with_diagnostics_and_no_snapshot_reads(self):
        u = Universe([mkt("KXONLY")], trades={"KXONLY": ZERO_TRADES})
        code, out, _t, transports, _c = self.h.run_live(u)
        self.assertEqual(code, 0)
        term = json.loads((out / "TERMINAL_RESULT.json").read_bytes())
        self.assertEqual(term["terminal_classification"], "SELECTOR_NO_CANDIDATE")
        self.assertEqual(term["selector_halt"]["code"], "B1_NO_FINALISTS")
        self.assertFalse(any(r["phase"].startswith("SNAPSHOT") for r in transports[0].records))
        self.assertFalse((out / "LIVE_READ_SNAPSHOT_SANITIZED.json").exists())
        diag = json.loads((out / "SELECTOR_DIAGNOSTICS.json").read_bytes())
        self.assertEqual(diag["b1"]["complete_zero_or_inactive_count"], 1)
        self.assertEqual(json.loads((out / "SELECTOR_RESULT.json").read_bytes())["selector_invocations"], 1)

    def test_exactly_one_selector_invocation(self):
        calls = []

        def counting(sel, cfg, **kw):
            calls.append(1)
            return CS.select_shadow_ticker(sel, cfg, **kw)
        code, _out, _t, _tr, _c = self.h.run_live(simple_universe(2), select_fn=counting)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)

    def test_production_wiring(self):
        self.assertIn("select_shadow_ticker", inspect.getsource(LC.run_live_capture))
        self.assertIn("s.EnvironmentRsaSigner()", inspect.getsource(LAUNCHER.run))
        self.assertIn("AccountedDemoTransport(sel, request_ceiling=request_ceiling)", inspect.getsource(LAUNCHER.run))
        self.assertNotIn("_demo_path_to_pem", inspect.getsource(LC))


# ---------------------------------------------------------------------------
# t21: static write-surface proof
# ---------------------------------------------------------------------------
class WriteGuardTests(OfflineBase):
    def test_t21_package_passes_static_guard(self):
        self.assertEqual(WG.scan_package(PKG), [])
        self.assertEqual(LAUNCHER.scan_shadow_surface(), [])

    def test_t21_guard_detects_write_constructs(self):
        verbs = ["PO" + "ST", "PU" + "T", "PAT" + "CH", "DEL" + "ETE"]
        for verb in verbs:
            with self.subTest(verb=verb):
                self.assertTrue(WG.scan_source(f'x = "{verb}"\n'))
                self.assertTrue(WG.scan_source(f'c.request("{verb}", "/x")\n'))
        for src in ("def create_order():\n    pass\n", "x.cancel_order()\n", "CreateOrder = 1\n",
                    "runner.RunnerOperation.CREATE_ORDER\n", "y = RunnerOperation.CANCEL\n",
                    "import sqlite3\n", "from arb.execution_ledger import x\n", "z.amend_order(1)\n",
                    "w.decrease_order(1)\n", "c.request(method, url)\n", "q = runner.NormalWriteAdapter\n"):
            with self.subTest(src=src):
                self.assertTrue(WG.scan_source(src), src)
        self.assertEqual(WG.scan_source("runner.RunnerOperation.GET_ORDERS\nc.request(\"GET\", u)\n"), [])

    def test_t21_transport_has_no_method_parameter_and_only_get(self):
        sig = inspect.signature(AccountedDemoTransport.get)
        self.assertEqual(list(sig.parameters), ["self", "path", "query", "headers"])
        self.assertFalse(any(hasattr(AccountedDemoTransport, n) for n in ("post", "delete", "put", "patch")))
        with self.assertRaises(RuntimeError):
            AccountedDemoTransport(types.SimpleNamespace(
                DEMO_HOST="external-api.kalshi.com", DEMO_PORT=443, BASE_PATH="/trade-api/v2",
                MAX_RESPONSE_BYTES=10, REQUEST_TIMEOUT_S=1.0,
                PRODUCTION_REST_HOSTS=SEL.PRODUCTION_REST_HOSTS), request_ceiling=1)
        t = AccountedDemoTransport(SEL, request_ceiling=1, connection_factory=_forbid("connect"))
        with self.assertRaises(RuntimeError):
            t.get(path="/evil", query=(), headers={})

    def test_t21_config_schema_has_no_capability_field(self):
        flat = json.dumps(CFG.SCHEMA).lower()
        for token in ("write", "production", "retr", "writer", "gate", "release", "permit", "credential",
                      "host", "origin", "method", "ceiling", "authoriz"):
            self.assertNotIn(token, flat, token)

    def test_no_header_values_recorded(self):
        u = simple_universe()
        t = u.transport(2)
        t.get(path=SEL.BASE_PATH + "/markets/" + TICKER, query=(),
              headers={"KALSHI-ACCESS-KEY": SECRET_KEY_ID, "KALSHI-ACCESS-SIGNATURE": "sig",
                       "KALSHI-ACCESS-TIMESTAMP": "1"})
        self.assertNotIn(SECRET_KEY_ID, json.dumps(t.records))
        self.assertTrue(t.records[0]["authenticated"])


# ---------------------------------------------------------------------------
# preserved: shadow evaluator differential equivalence vs canonical strategy
# (synthetic WRITER_ELIGIBLE fixtures offline only)
# ---------------------------------------------------------------------------
PROC = "proc_" + "1" * 32
ONE_CENT = (RISK.PriceRangeV1(D("0"), D("1.00"), D("0.01")),)
TWO_STEP = (RISK.PriceRangeV1(D("0"), D("0.50"), D("0.01")), RISK.PriceRangeV1(D("0.50"), D("1.00"), D("0.05")))


def risk_cfg(cap):
    return RISK.RiskLimitConfigV1(
        1, "kalshi-demo:portfolio:0", "USD",
        RISK.PerOrderRiskLimits(D("10"), D("10"), True, cap, 1_000),
        RISK.PerMarketRiskLimits(D("20"), D("20"), 10, D("20"), D("20")),
        RISK.AccountRiskLimits(D("100"), 50, D("100"), 0, D("0")),
        RISK.FlowRiskLimits(1, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 2, 1_000, 1, 500, 1, 10, 100),
        RISK.StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
        RISK.VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"))


def ob_snapshot(yes, no):
    ob = sys.modules["arb.venues.kalshi.orderbook"]
    return ob.KalshiNativeOrderBookSnapshot(
        environment="KALSHI_DEMO", market_ticker=TICKER, method="GET", route_template="/x",
        full_request_path="/x", endpoint_classification="PUBLIC", request_timestamp_ms=1,
        request_started_monotonic_ns=1, request_completed_monotonic_ns=2,
        yes_levels=tuple(ob.KalshiNativeOrderBookLevel(p, q) for p, q in yes),
        no_levels=tuple(ob.KalshiNativeOrderBookLevel(p, q) for p, q in no),
        canonical_level_ordering="ASCENDING", response_byte_length=10, response_sha256="a" * 64,
        raw_openapi_sha256="b" * 64, source_binding_record_sha256="c" * 64, request_count=1, retry_count=0,
        redirect_count=0, gustavo_execution_authorization_id="auth1", expected_implementation_commit="d" * 40,
        specification_sha256="e" * 64).with_canonical_identity()


def truth(i):
    return MM.build_economic_truth(
        signed_inventory_state="KNOWN", signed_net_position_contracts=i,
        market_economic_state=RISK.MarketEconomicState(D("0"), i, D("0"), D("0"), D("0"), 0, D("0")),
        unresolved_write_exposure_usd=D("0"), fill_history_completeness="COMPLETE",
        reconciliation_completeness="COMPLETE")


def working(slot, price, remaining):
    side = {"LOWER_YES_BID": ("bid", "YES"), "UPPER_YES_ASK": ("ask", "NO")}[slot]
    return MM.StrategyOwnedWorkingOrderV1(
        "mm_" + "1" * 32, TICKER, slot, "qg_" + "2" * 32, "cid1" + slot, "vid1" + slot, side[0], side[1],
        price, D("1.00"), remaining, "resting", "e1", "e2", "e3", "f" * 64)


def canonical_plan(yes, no, ranges, s, i, cap, slots=None, orders=()):
    cfg = MM.build_market_maker_config(strategy_instance_id="mm_" + "1" * 32, market_ticker=TICKER, minimum_spread_usd=s)
    rc = risk_cfg(cap)
    snap = ob_snapshot(yes, no)
    fresh = RISK.FreshnessStampV1(PROC, "2026-08-15T00:00:00.000000Z", 1_000_000_000, "NONE", None, "f" * 64)
    slots = slots or {"LOWER_YES_BID": "ABSENT", "UPPER_YES_ASK": "ABSENT"}
    inp = MM.MarketMakerInputV1(
        strategy_config=cfg, book_snapshot=snap, book_snapshot_sha256=snap.canonical_snapshot_sha256,
        book_freshness=fresh, price_ranges=ranges, price_grid_sha256=MM.compute_price_grid_sha256(ranges),
        risk_control_state="WRITER_ELIGIBLE",  # SYNTHETIC -- offline equivalence fixture only
        risk_state_epoch=1, risk_config=rc, risk_config_sha256=rc.sha256,
        reconciliation_snapshot_sha256="1" * 64, reconciliation_freshness=fresh, economic_truth=truth(i),
        strategy_working_orders=tuple(orders), slot_classifications=slots, process_instance_id=PROC,
        now_monotonic_ns=1_000_000_500, now_utc="2026-08-15T00:00:00.000000Z")
    return getattr(MM, "evaluate_market_maker" + "_input")(inp)


def shadow(yes, no, ranges, s, i, cap, **kw):
    inv = EV.ShadowInventoryInput(EV.INVENTORY_KNOWN, i, EV.SLOTS_ABSENT_OBSERVED, "synthetic")
    return EV.evaluate_shadow(MM, RISK, market_ticker=TICKER, minimum_spread_usd=s, yes_levels_ascending=yes,
                              no_levels_ascending=no, price_ranges=ranges, inventory=inv,
                              captured_book_identity="x" * 64, captured_at_utc="2026-01-01T00:00:00Z",
                              trial_G=1, trial_G_authority="NONCANONICAL_EXPERIMENT_INPUT", deviation_cap=cap, **kw)


class DifferentialEquivalenceTests(OfflineBase):
    def _compare(self, yes, no, ranges, s, i, cap, **kw):
        plan = canonical_plan(yes, no, ranges, s, i, cap, **{k: v for k, v in kw.items() if k in ("slots", "orders")})
        sh_kw = {k: v for k, v in kw.items() if k in ("w_lower", "w_upper", "lower_mode", "upper_mode")}
        obs = shadow(yes, no, ranges, s, i, cap, **sh_kw)
        self.assertEqual(plan.plan_classification, "VALID_DESIRED_STATE")
        lower = None if plan.lower_quote is None else format(plan.lower_quote.yes_price, "f")
        upper = None if plan.upper_quote is None else format(plan.upper_quote.yes_price, "f")
        self.assertEqual((obs.shadow_lower_candidate, obs.shadow_upper_candidate), (lower, upper), (yes, no, s, i, cap))
        self.assertEqual(tuple(plan.reason_codes), obs.suppression_reason_codes, (yes, no, s, i, cap))

    def test_matrix_of_books_spreads_positions_grids_caps(self):
        books = [(D("0.40"), D("0.50")), (D("0.05"), D("0.90")), (D("0.49"), D("0.50")), (D("0.50"), D("0.50")),
                 (D("0.20"), D("0.70")), (D("0.94"), D("0.04")), (D("0.30"), D("0.68")), (D("0.45"), D("0.45")),
                 (D("0.01"), D("0.97")), (D("0.55"), D("0.40"))]
        spreads = list(BASELINE.shadow_experiment.minimum_spread_usd) + [D("0.1000"), D("0.2500"), D("0.0001")]
        positions = [D("-1.5"), D("-1"), D("-0.01"), D("0"), D("0.01"), D("1"), D("2")]
        count = 0
        for (yb, nb), s, i, ranges, cap in itertools.product(books, spreads, positions, (ONE_CENT, TWO_STEP),
                                                              (D("1"), D("0.10"), D("0.02"))):
            if yb > D("1") - nb:
                continue  # crossed book: canonical NO_NEW_QUOTE_PLAN, outside geometry block
            yes = [(yb - D("0.01"), D("3")), (yb, D("7"))] if yb > D("0.01") else [(yb, D("7"))]
            no = [(nb - D("0.01"), D("2")), (nb, D("4"))] if nb > D("0.01") else [(nb, D("4"))]
            with self.subTest(yb=yb, nb=nb, s=s, i=i, cap=cap, grid=len(ranges)):
                self._compare(yes, no, ranges, s, i, cap)
                count += 1
        self.assertGreater(count, 2000)

    def test_active_exact_slots(self):
        yes, no = [(D("0.40"), D("5"))], [(D("0.50"), D("5"))]
        for wl, wu, i in ((D("1.00"), D("1.00"), D("0")), (D("0.50"), D("1.00"), D("0.60")),
                          (D("1.00"), D("0.40"), D("-0.70"))):
            with self.subTest(wl=wl, wu=wu, i=i):
                slots = {"LOWER_YES_BID": "ACTIVE_EXACT", "UPPER_YES_ASK": "ACTIVE_EXACT"}
                orders = (working("LOWER_YES_BID", D("0.40"), wl), working("UPPER_YES_ASK", D("0.60"), wu))
                self._compare(yes, no, ONE_CENT, D("0.02"), i, D("1"), slots=slots, orders=orders,
                              w_lower=wl, w_upper=wu, lower_mode="ACTIVE_EXACT", upper_mode="ACTIVE_EXACT")

    def test_unknown_inventory_never_coerced(self):
        inv = EV.ShadowInventoryInput(EV.INVENTORY_UNKNOWN, None, EV.SLOTS_UNKNOWN, "x")
        obs = EV.evaluate_shadow(MM, RISK, market_ticker=TICKER, minimum_spread_usd=D("0.02"),
                                 yes_levels_ascending=[(D("0.40"), D("5"))], no_levels_ascending=[(D("0.50"), D("5"))],
                                 price_ranges=ONE_CENT, inventory=inv, captured_book_identity="x",
                                 captured_at_utc="t", trial_G=1, trial_G_authority="NONCANONICAL_EXPERIMENT_INPUT")
        self.assertIsNone(obs.shadow_lower_candidate)
        self.assertIsNone(obs.shadow_upper_candidate)
        self.assertIn("INPUT_INVENTORY_UNKNOWN", obs.suppression_reason_codes)

    def test_shadow_output_is_not_a_quote_plan(self):
        obs = shadow([(D("0.40"), D("5"))], [(D("0.50"), D("5"))], ONE_CENT, D("0.02"), D("0"), None)
        with self.assertRaises(TypeError):
            MM.QuotePlanV1(**obs.to_dict())
        d = obs.to_dict()
        for k in ("plan_sha256", "risk_control_state", "quote_generation_id", "plan_classification"):
            self.assertNotIn(k, d)
        self.assertNotIn("WRITER_ELIGIBLE", json.dumps(d))


# ---------------------------------------------------------------------------
# t23-t32: repository-residence canonicalization theorems
# ---------------------------------------------------------------------------
REQUIRED_BASE_COMMIT = "6988439c35f8f666297ca30313be3666ce16cb29"
REQUIRED_BASE_TREE = "a49a5c969a07c1f2d9262630365f07cc206b7d12"
REQUIRED_BASE_PARENT = "9f0dae4ffd3cfa807ec0ea47f8949fc0029c1da4"
PROTECTED_BASE_BLOBS = {
    "project_context/GUARDRAILS.md": "d5b6e2ea986d651a8bdc6309b432389e72b17f3b",
    "project_context/START_HERE.md": "d36ab5543dc6883704599c49049afa27d8b295da",
    "src/arb/venues/kalshi/d07_market_selector.py": "46d0e4904c3d8342a54a89fa7e685b40ede24ea4",
    "src/arb/venues/kalshi/minimal_market_maker.py": "be1bbfa31c7d814d48751f9b2399ef62c866d36e",
    "src/arb/venues/kalshi/minimal_market_maker_experiment_runner.py": "eb455d9467448fcb2435abd3465bdf08e68b10fd",
    "src/arb/venues/kalshi/orderbook.py": "4d0c8b8407ddb941decaa5cf6a493ac6ab3063c5",
    "src/arb/venues/kalshi/risk_control.py": "111685c8c1dc7735a53b45830d93844c329f23e3",
    "tests/test_kalshi_d07_market_selector.py": "02dc6a12bd8883cd7c24fd8f9e3c1fba28c74096",
    "tests/test_kalshi_minimal_market_maker.py": "43e2a7fdbdbcfd769713e6e04cbaa321d8313e44",
    "tests/test_kalshi_minimal_market_maker_experiment_runner.py": "a92508c22029285e013a02f98c24779f6c4a895e",
}

# Accepted Test-02 configuration input (996 bytes).  TEST FIXTURE ONLY.
TEST02_CONFIG_BYTES = '''{
  "schema_version": 1,
  "run": {
    "run_id": "g1_shadow_experiment_02_broader_01"
  },
  "selector": {
    "market_scope": {
      "exchange_index": 0,
      "market_type": "binary",
      "status": "active",
      "exclude_mve": true
    },
    "close_window": {
      "min_seconds_to_close": 900,
      "max_seconds_to_close": 86400
    },
    "a4": {
      "page_limit": 500,
      "max_pages": 200,
      "retained_count": 100,
      "max_selected_ask": "0.9500",
      "min_executable_ask_qty": "1.00"
    },
    "c1": {
      "event_diverse_shortlist_size": 20,
      "depth_band": "0.0200"
    },
    "b1": {
      "lookback_seconds": 86400,
      "page_limit": 1000,
      "max_pages_per_ticker": 20,
      "finalist_count": 5,
      "exclude_block_trades": true,
      "require_complete_active_window": false
    }
  },
  "shadow_experiment": {
    "trial_g": 1,
    "minimum_spread_usd": [
      "0.0100",
      "0.0200",
      "0.0300",
      "0.0400",
      "0.0500"
    ]
  }
}
'''.encode("ascii")
TEST02_CONFIG_SHA256 = "0fc41fd48dc743dc51d81cd3a1c212fffce72e7ee3647973164e17c1d3a4e20f"
# Accepted Test-02 sanitized live snapshot (1440 bytes).  TEST FIXTURE ONLY.
TEST02_SNAPSHOT_BYTES = '''{
  "captured_at_utc": "2026-10-04T16:33:17.826672Z",
  "market": {
    "close_time": "2026-10-05T03:59:00Z",
    "event_ticker": "KXAAAGASDCA-26OCT05",
    "exchange_index": 0,
    "market_type": "binary",
    "price_ranges": [
      {
        "end": "1.0000",
        "start": "0.0000",
        "step": "0.0100"
      }
    ],
    "status": "active",
    "ticker": "KXAAAGASDCA-26OCT05-6.4100",
    "yes_ask_dollars": "0.0300",
    "yes_bid_dollars": "0.0200"
  },
  "market_ticker": "KXAAAGASDCA-26OCT05-6.4100",
  "observation_scope": {
    "exchange_index": 0,
    "subaccount": 1
  },
  "orderbook": {
    "book_identity_sha256": "1f26c8a0fb5d58346ceb240c0314abc369216be66f4e21a33f3654d6e7c9d6ad",
    "no_dollars_ascending": [
      [
        "0.9700",
        "10.00"
      ]
    ],
    "parse_ok": true,
    "yes_dollars_ascending": [
      [
        "0.0200",
        "10.00"
      ]
    ]
  },
  "orders_observation": {
    "resting": [],
    "row_count": 0,
    "state": "OBSERVED_NONE_RESTING"
  },
  "positions_observation": {
    "position_count_fp": [],
    "row_count": 0,
    "state": "OBSERVED_FLAT"
  },
  "run_id": "g1_shadow_experiment_02_broader_01",
  "schema": "ShadowExperimentSnapshotSanitizedV1",
  "selected_b1_window_status": "COMPLETE_ACTIVE",
  "selected_via_relaxed_b1": false,
  "selection_authority": "SHADOW_ONLY__NO_WRITER_QUALIFICATION__NO_TRADE_ELIGIBILITY__NO_RELEASE__NO_GATE_D__NO_WRITER_PERMIT"
}
'''.encode("ascii")
TEST02_SNAPSHOT_SHA256 = "3c56f2d5d18740734e0c8c9147dc24d99ad963dabc8e3cf3477b6ee67842f8af"
# Accepted Test-02 evidence identities that replay must reproduce exactly.
TEST02_MATRIX_JSON = (10440, "c19051faa8d7fb3e8a71cd865a2117953aa09522ab45d2e204848a950243a279")
TEST02_MATRIX_CSV = (1986, "259f8c8f07577f1ed479a166f317a4fc771aab4b2d1e6a8e6dbd3b49b67ace01")
assert hashlib.sha256(TEST02_CONFIG_BYTES).hexdigest() == TEST02_CONFIG_SHA256
assert hashlib.sha256(TEST02_SNAPSHOT_BYTES).hexdigest() == TEST02_SNAPSHOT_SHA256


def _surface_string_constants():
    for path in SURFACE_FILES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant):
                yield path, node


def _provenance_report(**kw):
    report = CB.PreflightReport()
    prov = CB.verify_repository_provenance(REPO, report, live=True, git=make_fake_git(**kw))
    return report, prov


class RepositoryResidenceTests(OfflineBase):
    def test_t23_installed_code_contains_no_static_canonical_commit_tree_parent_pin(self):
        for name in ("CANONICAL_COMMIT", "CANONICAL_TREE", "CANONICAL_PARENT", "CANONICAL_BLOBS", "SELECTOR_SHA256",
                     "SELECTOR_BYTES", "DEFAULT_CANONICAL_REPO"):
            self.assertFalse(hasattr(C, name), name)
        hex40 = __import__("re").compile(r"[0-9a-f]{40}")
        for path, node in _surface_string_constants():
            if isinstance(node.value, str):
                self.assertIsNone(hex40.search(node.value), f"{path.name}:{node.lineno}")
        for path in SURFACE_FILES:
            text = path.read_text(encoding="utf-8")
            for pinned in (REQUIRED_BASE_COMMIT, REQUIRED_BASE_TREE, REQUIRED_BASE_PARENT):
                self.assertNotIn(pinned, text, path.name)
            self.assertNotIn("--canonical-repo", text, path.name)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            LAUNCHER._build_parser().parse_args(["--canonical-repo", "x"])

    def test_t24_live_provenance_records_head_tree_sole_parent_and_committed_self_surface(self):
        report, prov = _provenance_report()
        self.assertTrue(all(c["result"] == "PASS" for c in report.checks))
        self.assertEqual((prov["head"], prov["tree"], prov["parents"]), (FAKE_HEAD, FAKE_TREE, [FAKE_PARENT]))
        self.assertEqual((prov["mode"], prov["branch"], prov["worktree_clean"]), ("LIVE", "main", True))
        self.assertEqual(prov["policy"], C.PROVENANCE_POLICY)
        surface = CB.self_surface_paths(REPO)
        self.assertEqual(surface[0], "run_shadow_experiment.py")
        self.assertEqual(sorted(surface[1:]), sorted(f"{C.PACKAGE_RELATIVE_DIR}/{p.name}" for p in PKG.glob("*.py")))
        self.assertEqual(len(surface), 11)
        self.assertEqual(sorted(prov["self_surface_blobs"]), sorted(surface))
        for rel, pair in prov["self_surface_blobs"].items():
            self.assertEqual(pair["on_disk"], CB._blob_id((REPO / rel).read_bytes()), rel)
            self.assertEqual(pair["on_disk"], pair["committed"], rel)
        self.assertEqual(sorted(prov["dependency_blobs"]), sorted(C.DEPENDENCY_RELATIVE_PATHS))
        names = [c["check"] for c in report.checks]
        for required in ("origin_is_rigolugo_ARB", "branch_is_main", "worktree_clean", "head_has_sole_parent",
                         "self_surface_module_set_committed", "self_surface_blob:run_shadow_experiment.py",
                         "dependency_blob:src/arb/venues/kalshi/d07_market_selector.py"):
            self.assertIn(required, names)
        # the launcher records the observed provenance in run evidence
        h = LaunchHarness()
        h.setup(self.tmp)
        code, out, text, _t, _c = h.run_live(simple_universe(2))
        self.assertEqual(code, 0, text)
        manifest = json.loads((out / "RUN_MANIFEST.json").read_bytes())
        rp = manifest["repository_provenance"]
        self.assertEqual((rp["head"], rp["tree"], rp["parents"]), (FAKE_HEAD, FAKE_TREE, [FAKE_PARENT]))
        self.assertEqual(sorted(rp["self_surface_blobs"]), sorted(surface))
        self.assertNotIn("canonical_commit", manifest)
        self.assertEqual(manifest["canonicalization_task_id"], C.CANONICALIZATION_TASK_ID)

    def test_t24_replay_records_real_repository_provenance_without_requiring_live_conditions(self):
        report = CB.PreflightReport()
        prov = CB.verify_repository_provenance(REPO, report, live=False)
        self.assertEqual(prov["head"], CB._git(REPO, "rev-parse", "HEAD"))
        self.assertEqual(prov["tree"], CB._git(REPO, "rev-parse", "HEAD^{tree}"))
        self.assertEqual(prov["mode"], "REPLAY")
        self.assertTrue(all(c["result"] == "PASS" for c in report.checks))
        self.assertNotIn("branch_is_main", [c["check"] for c in report.checks])

    def test_t25_live_mode_fails_closed_on_dirty_origin_branch_parent_or_uncommitted_surface(self):
        runner_rel = "run_shadow_experiment.py"
        module_rel = f"{C.PACKAGE_RELATIVE_DIR}/config.py"
        dep_rel = C.DEPENDENCY_RELATIVE_PATHS[0]
        cases = {
            "dirty": ({"status": " M run_shadow_experiment.py"}, "worktree_clean"),
            "untracked_file": ({"status": "?? stray.py"}, "worktree_clean"),
            "wrong_origin": ({"origin": "https://github.com/someone-else/ARB.git"}, "origin_is_rigolugo_ARB"),
            "wrong_branch": ({"branch": "claude/feature"}, "branch_is_main"),
            "detached_head": ({"branch": None}, "branch_is_main"),
            "merge_commit": ({"parents": (FAKE_PARENT, "d" * 40)}, "head_has_sole_parent"),
            "root_commit": ({"parents": ()}, "head_has_sole_parent"),
            "module_not_committed": ({"committed_modules": [module_rel]}, "self_surface_module_set_committed"),
            "runner_blob_differs": ({"blob_overrides": {runner_rel: "e" * 40}}, f"self_surface_blob:{runner_rel}"),
            "runner_untracked": ({"untracked": (runner_rel,)}, f"self_surface_blob:{runner_rel}"),
            "dependency_blob_differs": ({"blob_overrides": {dep_rel: "f" * 40}}, f"dependency_blob:{dep_rel}"),
        }
        for label, (kw, failed) in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(CB.PreconditionFailed) as ctx:
                    _provenance_report(**kw)
                self.assertEqual(ctx.exception.detail, failed)
        # launcher: a dirty live repository fails before credential presence/network; no output
        out = self.tmp / "never"
        buf = io.StringIO()
        with mock.patch.object(LAUNCHER, "verify_repository_provenance", fake_live_provenance(branch="dev")), \
                mock.patch.object(LAUNCHER, "verify_credential_presence", side_effect=_forbid("credentials")), \
                contextlib.redirect_stdout(buf):
            code = LAUNCHER.run(["--config", str(self.baseline_path), "--output-dir", str(out),
                                 C.EXECUTION_ACKNOWLEDGEMENT_FLAG], interpreter_check=False,
                                transport_factory=_forbid("transport"), signer_factory=_forbid("signer"),
                                select_fn=_forbid("selector"))
        self.assertEqual(code, LAUNCHER.EXIT_PRECONDITION_FAILED, buf.getvalue())
        self.assertIn("branch_is_main", buf.getvalue())
        self.assertFalse(out.exists())

    def test_t26_request_ceiling_above_611_fails_in_config_validation_before_credentials_or_network(self):
        self.assertEqual(C.MAX_WHOLE_RUN_REQUESTS, 611)
        over = {
            "a4_max_pages": with_value("selector.a4.max_pages", 201),
            "shortlist": with_value("selector.c1.event_diverse_shortlist_size", 21),
            "b1_pages": with_value("selector.b1.max_pages_per_ticker", 21),
            "finalists": with_value("selector.b1.finalist_count", 6),
            "pathological": with_value("selector.a4.max_pages", 10 ** 12),
        }
        for label, raw in over.items():
            with self.subTest(label=label):
                with self.assertRaises(CFG.ConfigError) as ctx:
                    CFG.load_config_bytes(raw)
                self.assertEqual(ctx.exception.code, "CONFIG_REQUEST_CEILING_EXCEEDED")
                self.assertNotIn("KALSHI", str(ctx.exception))
                p = self.tmp / f"{label}.json"
                p.write_bytes(raw)
                code, text = CliTests._guarded_run(self, ["--config", str(p), "--output-dir", str(self.tmp / "never"),
                                                          C.EXECUTION_ACKNOWLEDGEMENT_FLAG])
                self.assertEqual(code, LAUNCHER.EXIT_CONFIG_INVALID, text)
                self.assertIn("CONFIG_REQUEST_CEILING_EXCEEDED", text)
                self.assertFalse((self.tmp / "never").exists())
        # exact boundary: 611 accepted, 612 rejected
        self.assertEqual(CFG.whole_run_request_ceiling(cfg_with(selector__a4__max_pages=199,
                                                                selector__b1__finalist_count=6)), 611)
        with self.assertRaises(CFG.ConfigError):
            cfg_with(selector__a4__max_pages=200, selector__b1__finalist_count=6)
        # the bound is code-immutable: no config field can carry it
        self.assertNotIn("ceiling", json.dumps(CFG.SCHEMA).lower())
        self.assertNotIn("max_whole_run", json.dumps(CFG.SCHEMA).lower())

    def test_t27_baseline_and_accepted_test02_configs_derive_611_and_remain_valid(self):
        for label, raw in (("baseline", BASELINE_BYTES), ("test02", TEST02_CONFIG_BYTES)):
            with self.subTest(label=label):
                cfg = CFG.load_config_bytes(raw)
                self.assertEqual(CFG.selector_max_requests(cfg), 607)
                self.assertEqual(CFG.whole_run_request_ceiling(cfg), 611)
                self.assertEqual(CFG.whole_run_request_ceiling(cfg), C.MAX_WHOLE_RUN_REQUESTS)

    def test_t28_test02_config_and_snapshot_replay_reproduces_accepted_shadow_matrix_bytes(self):
        cfg_path = self.tmp / "test02_config_fixture.json"
        cfg_path.write_bytes(TEST02_CONFIG_BYTES)
        snap_path = self.tmp / "test02_snapshot_fixture.json"
        snap_path.write_bytes(TEST02_SNAPSHOT_BYTES)
        out = self.tmp / "replay_test02"
        buf = io.StringIO()
        with mock.patch.object(LAUNCHER, "verify_credential_presence", side_effect=_forbid("credentials")), \
                contextlib.redirect_stdout(buf):
            rc = LAUNCHER.run(["--config", str(cfg_path), "--output-dir", str(out), "--replay-snapshot",
                               str(snap_path)], interpreter_check=False, transport_factory=_forbid("transport"),
                              signer_factory=_forbid("signer"), select_fn=_forbid("selector"))
        self.assertEqual(rc, 0, buf.getvalue())
        matrix_json = (out / "SHADOW_MATRIX.json").read_bytes()
        matrix_csv = (out / "SHADOW_MATRIX.csv").read_bytes()
        self.assertEqual((len(matrix_json), hashlib.sha256(matrix_json).hexdigest()), TEST02_MATRIX_JSON)
        self.assertEqual((len(matrix_csv), hashlib.sha256(matrix_csv).hexdigest()), TEST02_MATRIX_CSV)
        self.assertEqual((out / "LIVE_READ_SNAPSHOT_SANITIZED.json").read_bytes(), TEST02_SNAPSHOT_BYTES)
        self.assertEqual((out / "SELECTOR_CONFIG_INPUT.json").read_bytes(), TEST02_CONFIG_BYTES)
        matrix = json.loads(matrix_json)
        self.assertEqual(matrix["terminal"], "SHADOW_EXPERIMENT_COMPLETE")
        self.assertEqual({r["market_ticker"] for r in matrix["rows"]}, {"KXAAAGASDCA-26OCT05-6.4100"})
        self.assertFalse(matrix["winner_selected"])
        self.assertEqual(matrix["canonical_G_selection"], "UNSELECTED")
        term = json.loads((out / "TERMINAL_RESULT.json").read_bytes())
        self.assertTrue(term["no_profitability_claim"])
        self.assertEqual(json.loads((out / "READ_REQUEST_ACCOUNTING.json").read_bytes())["request_count"], 0)

    def test_t29_no_concrete_experiment_config_or_default_installed_in_repository(self):
        config_keys = {"schema_version", "run", "selector", "shadow_experiment"}
        for path in REPO.rglob("*.json"):
            if ".git" in path.parts:
                continue
            self.assertFalse(path.name.startswith("selector_config"), path)
            try:
                doc = json.loads(path.read_bytes())
            except (ValueError, UnicodeDecodeError):
                continue
            self.assertFalse(isinstance(doc, dict) and config_keys <= set(doc), path)
        # no experiment parameter literal lives in installed source
        forbidden = {"0.9500", "0.8000", "0.0200", "0.0100", "0.0300", "0.0400", "0.0500", "1.00",
                     "g1_shadow_experiment_02", "g1_shadow_experiment_02_broader_01"}
        forbidden_ints = {900, 1800, 21600, 43200, 86400}
        for path, node in _surface_string_constants():
            self.assertNotIn(node.value, forbidden, f"{path.name}:{node.lineno}")
            if type(node.value) is int:
                self.assertNotIn(node.value, forbidden_ints, f"{path.name}:{node.lineno}")
        # every runner option other than the acknowledgement defaults to None (no default config)
        for action in LAUNCHER._build_parser()._actions:
            if action.dest not in ("help", "acknowledged"):
                self.assertIsNone(action.default, action.dest)

    def test_t30_protected_base_paths_remain_byte_and_git_blob_identical(self):
        for rel, blob in PROTECTED_BASE_BLOBS.items():
            with self.subTest(path=rel):
                self.assertEqual(CB._blob_id((REPO / rel).read_bytes()), blob)

    def test_t31_trial_g_remains_evidence_label_only(self):
        snapshot = json.loads(TEST02_SNAPSHOT_BYTES)
        doc = json.loads(TEST02_CONFIG_BYTES)
        matrices = {}
        for g in (1, 2, 3, 4):
            doc["shadow_experiment"]["trial_g"] = g
            matrices[g] = SW.run_sweep(MODS, CFG.load_config_bytes(to_bytes(doc)), snapshot)

        def strip(m):
            m = copy.deepcopy(m)
            m.pop("trial_G")
            for r in m["rows"]:
                r.pop("trial_G")
            return m
        for g in (2, 3, 4):
            self.assertEqual(strip(matrices[g]), strip(matrices[1]))
            self.assertEqual({r["trial_G"] for r in matrices[g]["rows"]}, {g})
            self.assertEqual(matrices[g]["trial_G_authority"], "NONCANONICAL_EXPERIMENT_INPUT")
            self.assertEqual(matrices[g]["canonical_G_selection"], "UNSELECTED")
        for path in SURFACE_FILES:
            text = path.read_text(encoding="utf-8")
            for token in ("max_ordinary_write_sends", "decision_cycle", "G_MECHANICS", "write_sends"):
                self.assertNotIn(token, text, path.name)
        # CORRECTION_01 F02: the label domain is exactly the canonical G domain 1..4
        self.assertEqual(CFG.TRIAL_G_LABEL_DOMAIN, (1, 2, 3, 4))
        for bad in (0, 5):
            with self.subTest(trial_g=bad):
                doc["shadow_experiment"]["trial_g"] = bad
                with self.assertRaises(CFG.ConfigError) as ctx:
                    CFG.load_config_bytes(to_bytes(doc))
                self.assertEqual((ctx.exception.code, ctx.exception.path),
                                 ("CONFIG_VALUE_OUT_OF_RANGE", "$.shadow_experiment.trial_g"))

    def test_t32_static_guard_proves_demo_get_only_zero_write_zero_retry_surface(self):
        self.assertEqual(LAUNCHER.scan_shadow_surface(), [])
        self.assertEqual(WG.scan_source(RUNNER_PATH.read_text(encoding="utf-8")), [])
        self.assertEqual(C.AUTOMATIC_RETRIES, 0)
        sig = inspect.signature(AccountedDemoTransport.get)
        self.assertEqual(list(sig.parameters), ["self", "path", "query", "headers"])
        transport_src = (PKG / "transport.py").read_text(encoding="utf-8")
        calls = [n for n in ast.walk(ast.parse(transport_src))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "request"]
        self.assertTrue(calls)
        self.assertTrue(all(isinstance(c.args[0], ast.Constant) and c.args[0].value == "GET" for c in calls))
        # the guard really scans the root runner: a write construct injected into it is detected
        poisoned = RUNNER_PATH.read_text(encoding="utf-8") + '\nx = "PO' + 'ST"\n'
        self.assertTrue(WG.scan_source(poisoned))
        with mock.patch.object(LAUNCHER, "scan_source", return_value=["poison"]):
            self.assertEqual(LAUNCHER.scan_shadow_surface()[:1], ["poison"])


# ---------------------------------------------------------------------------
# t33-t42: CORRECTION_01 (F01 output containment, F02 trial_g label domain)
# ---------------------------------------------------------------------------
SEED_PRESERVED_MODULE_SHA256 = {
    "__init__.py": "2e4d9376b9bf8b11ab148c06a2d4a38e03b5877f365f33f27cdc421a45162272",
    "canonical_binding.py": "5cf4c104ad2cccb825468708d9dd748ab9a043f7501f910a3a76c7088b0b3c48",
    "configurable_selector.py": "c4961b41e71f29eec87466f2b26c73d0a452aefe7a4f64864d926ef093882abf",
    "constants.py": "685e0ff35df3ac49cbacdda0d8dd506dd64d2423fac7b647467f35a2c1951fb9",
    "live_capture.py": "f2312144e0cf2337a7b75d20f4b0cf4182cbd3f6e005c0a571473a02249c7166",
    "shadow_evaluator.py": "923b8008d557c8118207ef36a5cfee96751d42a830ca86094c6294c1bf3d2f21",
    "sweep.py": "5998526dde3c3982189b2599cc5f3136259e5fd3bc26ab5937493b22097aaec4",
    "transport.py": "c36537752b5cf00526e825d93b03d1bca01d9a71af31de9e74b0c319b85a1094",
    "write_guard.py": "5eb5ee4893c6b864d1568df1b84f6976a0649773ab12a7178c04bb06bafbe4e4",
}
PROBE = "shadow_out_containment_probe_c01"


def _repo_status():
    return CB._git(REPO, "status", "--porcelain=v1", "--untracked-files=all")


class OutputContainmentTests(OfflineBase):
    """F01: the resolved --output-dir must be outside the repository, in both
    modes, checked before credential presence, signer/transport/selector and
    any output creation."""

    def _run(self, out_arg, *, replay=False):
        argv = ["--config", str(self.baseline_path), "--output-dir", str(out_arg)]
        if replay:
            snap = self.tmp / "snapshot_fixture.json"
            snap.write_bytes(TEST02_SNAPSHOT_BYTES)
            argv += ["--replay-snapshot", str(snap)]
        else:
            argv.append(C.EXECUTION_ACKNOWLEDGEMENT_FLAG)
        buf = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(LAUNCHER, "verify_repository_provenance", fake_live_provenance()))
            for name in ("verify_credential_presence", "_new_output_dir", "bind_canonical_modules"):
                stack.enter_context(mock.patch.object(LAUNCHER, name, side_effect=_forbid(name)))
            stack.enter_context(contextlib.redirect_stdout(buf))
            code = LAUNCHER.run(argv, env={}, interpreter_check=False, transport_factory=_forbid("transport"),
                                signer_factory=_forbid("signer"), select_fn=_forbid("selector"))
        return code, buf.getvalue()

    def assertRejected(self, out_arg, *, created=None):
        for replay in (False, True):
            with self.subTest(out=str(out_arg), replay=replay):
                before = _repo_status()
                code, text = self._run(out_arg, replay=replay)
                self.assertEqual(code, LAUNCHER.EXIT_PRECONDITION_FAILED, text)
                doc = json.loads(text)
                self.assertEqual((doc["status"], doc["failed_check"]),
                                 ("PRECONDITION_FAILED", "OUTPUT_DIR_INSIDE_REPOSITORY"))
                self.assertEqual(doc["checks"][-1], {"check": "output_dir_outside_repository", "result": "FAIL",
                                                     "observed": "OUTPUT_DIR_INSIDE_REPOSITORY"})
                self.assertNotIn(PROBE, text)
                self.assertEqual(_repo_status(), before)
                if created is not None:
                    self.assertFalse(created.exists(), created)

    def test_t33_output_equal_to_repository_root_rejected(self):
        self.assertRejected(REPO)
        self.assertRejected(Path(str(REPO) + os.sep))

    def test_t34_absolute_repository_descendant_rejected(self):
        target = REPO / PROBE / "nested"
        self.assertRejected(target, created=REPO / PROBE)
        self.assertRejected(REPO / "src" / PROBE, created=REPO / "src" / PROBE)
        if os.name == "nt":   # Windows: case-insensitive comparison
            self.assertRejected(Path(str(REPO).upper()) / PROBE, created=REPO / PROBE)
            self.assertRejected(Path(str(REPO).lower()) / PROBE, created=REPO / PROBE)

    def test_t35_relative_and_dotdot_paths_resolving_into_repository_rejected(self):
        with contextlib.chdir(REPO):
            self.assertRejected(Path(PROBE), created=REPO / PROBE)
            self.assertRejected(Path(".") / PROBE / "x", created=REPO / PROBE)
            self.assertRejected(Path("."), created=None)
            self.assertRejected(Path("..") / REPO.name / PROBE, created=REPO / PROBE)
        with contextlib.chdir(REPO / "src"):
            self.assertRejected(Path("..") / PROBE, created=REPO / PROBE)
        self.assertRejected(REPO / "src" / ".." / PROBE, created=REPO / PROBE)
        if self.tmp.anchor.lower() == REPO.anchor.lower():   # climb out of tmp with '..' and back into the repo
            climbed = Path(self.tmp, *([".."] * (len(self.tmp.parts) - 1)), *REPO.parts[1:], PROBE)
            self.assertIn("..", climbed.parts)
            self.assertRejected(climbed, created=REPO / PROBE)

    def test_t36_alias_parent_resolving_into_repository_rejected(self):
        # (a) deterministic resolution seam: an external-looking alias whose real target is the repo
        alias = self.tmp / "alias_to_repo"
        real_resolve = LAUNCHER._resolved_path_for_containment

        def fake_resolve(path):
            p = Path(path)
            if p == alias or alias in p.parents:
                return REPO / p.relative_to(alias)
            return real_resolve(p)
        with mock.patch.object(LAUNCHER, "_resolved_path_for_containment", side_effect=fake_resolve):
            self.assertRejected(alias / PROBE, created=REPO / PROBE)
        # without the alias mapping the same path is external and passes containment
        report = CB.PreflightReport()
        LAUNCHER._validate_output_target(alias / PROBE, REPO, report)
        self.assertEqual(report.checks[-1]["result"], "PASS")
        # the production helper performs real filesystem resolution, never lexical prefix matching
        self.assertIn(".resolve(strict=False)", inspect.getsource(LAUNCHER._resolved_path_for_containment))
        self.assertIn(".resolve(strict=True)", inspect.getsource(LAUNCHER._validate_output_target))
        body = inspect.getsource(LAUNCHER._is_equal_or_descendant)
        self.assertIn("commonpath", body)
        self.assertNotIn("startswith(", body)

    def test_t36_real_junction_or_symlink_parent_rejected_when_available(self):
        holder = Path(tempfile.mkdtemp())
        link = holder / "link_to_repo"
        made = None
        try:
            import _winapi
            _winapi.CreateJunction(str(REPO), str(link))
            made = "junction"
        except (ImportError, AttributeError, OSError):
            try:
                os.symlink(str(REPO), str(link), target_is_directory=True)
                made = "symlink"
            except (OSError, NotImplementedError):
                made = None
        try:
            if made is None:
                self.skipTest("no unprivileged junction/symlink available on this host")
            self.assertEqual(Path(link).resolve(), REPO.resolve())
            self.assertRejected(link / PROBE, created=REPO / PROBE)
        finally:
            # remove ONLY the link itself (never recurse through it), then the empty holder
            if made == "junction":
                self.assertTrue(os.path.isjunction(link))
                os.rmdir(link)
            elif made == "symlink":
                (os.rmdir if os.name == "nt" else os.unlink)(link)
            os.rmdir(holder)

    def test_t37_safe_external_targets_pass_containment(self):
        repo_real = REPO.resolve()
        for target in (self.tmp / "out", REPO.parent / "arb_local" / "runs" / "x",
                       REPO.parent / (REPO.name + "_sibling") / "x", REPO.parent / (REPO.name + "x")):
            with self.subTest(target=str(target)):
                self.assertFalse(LAUNCHER._is_equal_or_descendant(target.resolve(strict=False), repo_real))
                report = CB.PreflightReport()
                LAUNCHER._validate_output_target(target, REPO, report)
                self.assertEqual(report.checks, [{"check": "output_dir_outside_repository", "result": "PASS",
                                                  "observed": "PASS"}])
                self.assertFalse(target.exists())   # the containment check itself never creates anything
        self.assertFalse(LAUNCHER._is_equal_or_descendant(Path("D:/elsewhere"), Path("C:/repo")))
        # full live and replay runs to an external target still succeed and record the PASS check
        h = LaunchHarness()
        h.setup(self.tmp)
        code, out, text, _t, _c = h.run_live(simple_universe(2))
        self.assertEqual(code, 0, text)
        checks = json.loads((out / "RUN_MANIFEST.json").read_bytes())["preflight"]
        names = [c["check"] for c in checks]
        self.assertIn("output_dir_outside_repository", names)
        self.assertLess(names.index("output_dir_outside_repository"), names.index("api_key_id_present"))
        self.assertLess(names.index("output_dir_outside_repository"), names.index("output_dir_new"))

    def test_t38_rejection_precedes_credentials_network_and_filesystem_mutation(self):
        target = REPO / PROBE / "deep" / "deeper"
        before_status = _repo_status()
        before_protected = {rel: (REPO / rel).read_bytes() for rel in PROTECTED_BASE_BLOBS}
        # _run booby-traps credential presence, _new_output_dir (mkdir), canonical binding,
        # signer, transport and selector: reaching any of them would raise _Boom, not return 3.
        for replay in (False, True):
            code, text = self._run(target, replay=replay)
            self.assertEqual(code, LAUNCHER.EXIT_PRECONDITION_FAILED, text)
            self.assertEqual(json.loads(text)["failed_check"], "OUTPUT_DIR_INSIDE_REPOSITORY")
            self.assertFalse((REPO / PROBE).exists())
        self.assertEqual(_repo_status(), before_status)
        self.assertEqual({rel: (REPO / rel).read_bytes() for rel in PROTECTED_BASE_BLOBS}, before_protected)
        # an existing in-repository directory is also rejected by containment (not by "already exists")
        code, text = self._run(REPO / "tests")
        self.assertEqual(json.loads(text)["failed_check"], "OUTPUT_DIR_INSIDE_REPOSITORY")

    def test_t39_trial_g_label_domain_1_to_4_accepted(self):
        for g in (1, 2, 3, 4):
            with self.subTest(trial_g=g):
                cfg = cfg_with(shadow_experiment__trial_g=g)
                self.assertEqual(cfg.shadow_experiment.trial_g, g)
                self.assertEqual(CFG.effective_config_dict(cfg)["shadow_experiment"]["trial_g"], g)
        # economics equivalence across G labels is proven by t31

    def test_t40_trial_g_invalid_range_type_and_float_rejected(self):
        path = "$.shadow_experiment.trial_g"
        cases = [(v, "CONFIG_VALUE_OUT_OF_RANGE") for v in (-1, 0, 5, 6, 10 ** 9)]
        cases += [(v, "CONFIG_WRONG_TYPE") for v in (True, False, "1", None, [], {}, [1], {"g": 1})]
        for value, code in cases:
            with self.subTest(trial_g=value):
                with self.assertRaises(CFG.ConfigError) as ctx:
                    CFG.load_config_bytes(with_value("shadow_experiment.trial_g", value))
                self.assertEqual((ctx.exception.code, ctx.exception.path), (code, path))
                if code == "CONFIG_VALUE_OUT_OF_RANGE":
                    self.assertEqual(ctx.exception.detail, "must be an integer in 1..4")
        self.assertIn(b'"trial_g": 1,', BASELINE_BYTES)
        for token in (b"1.0", b"1e0", b"1E0", b"2.0"):
            with self.subTest(token=token):
                with self.assertRaises(CFG.ConfigError) as ctx:
                    CFG.load_config_bytes(BASELINE_BYTES.replace(b'"trial_g": 1,', b'"trial_g": ' + token + b","))
                self.assertEqual((ctx.exception.code, ctx.exception.path), ("CONFIG_FLOAT_PROHIBITED", path))
        # the remaining INT_POSITIVE knobs keep their unchanged semantics (5 stays valid elsewhere)
        self.assertEqual(cfg_with(selector__b1__finalist_count=5).selector.b1.finalist_count, 5)

    def test_t41_accepted_test02_g1_replay_exact_bytes_preserved(self):
        self.assertEqual(json.loads(TEST02_CONFIG_BYTES)["shadow_experiment"]["trial_g"], 1)
        RepositoryResidenceTests.test_t28_test02_config_and_snapshot_replay_reproduces_accepted_shadow_matrix_bytes(
            self)

    def test_t42_seed_preserved_modules_and_protected_canonical_paths_exact(self):
        self.assertEqual(sorted(SEED_PRESERVED_MODULE_SHA256), sorted(
            p.name for p in PKG.glob("*.py") if p.name != "config.py"))
        for name, digest in SEED_PRESERVED_MODULE_SHA256.items():
            with self.subTest(module=name):
                self.assertEqual(hashlib.sha256((PKG / name).read_bytes()).hexdigest(), digest)
        for rel, blob in PROTECTED_BASE_BLOBS.items():
            with self.subTest(path=rel):
                self.assertEqual(CB._blob_id((REPO / rel).read_bytes()), blob)


if __name__ == "__main__":
    unittest.main()
