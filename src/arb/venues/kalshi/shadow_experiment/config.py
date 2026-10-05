"""Strict JSON experiment-configuration loader (``schema_version = 1``).

The configuration is EXPERIMENT INPUT ONLY.  It cannot grant, widen or
switch any capability: it has no write / production / retry / writer /
release / Gate-D field, and an unknown key of any spelling is rejected.

Rules (all fail closed with a secret-free ``ConfigError`` code + JSON path,
before any preflight, credential or network boundary is reached):

* exact UTF-8 JSON object; duplicate object keys rejected; ``NaN`` /
  ``Infinity`` / ``-Infinity`` constants rejected;
* every supported key is REQUIRED; unknown keys rejected at every level;
* integers must be JSON integers (``bool`` is never accepted as an integer);
* any JSON number with a fraction/exponent (binary float) is rejected
  anywhere in the document; decimal knobs must be decimal STRINGS of the
  plain form ``digits[.digits]`` (no sign, no exponent, no NaN/Infinity) and
  are parsed only with ``Decimal``;
* there is no default value for any knob: the JSON is the only source;
* the derived worst-case whole-run request ceiling must not exceed the
  immutable resource-safety bound ``constants.MAX_WHOLE_RUN_REQUESTS``
  (``CONFIG_REQUEST_CEILING_EXCEEDED``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Tuple

from . import constants as C


class ConfigError(ValueError):
    """Fixed, secret-free configuration rejection."""

    def __init__(self, code: str, path: str = "$", detail: str = "") -> None:
        super().__init__(f"{code} at {path}" + (f": {detail}" if detail else ""))
        self.code = code
        self.path = path
        self.detail = detail

    def to_dict(self) -> dict:
        return {"code": self.code, "path": self.path, "detail": self.detail}


class _FloatToken:
    """Marker for a JSON number with a fraction or exponent; never a value."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


_DECIMAL_LEXICAL = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]+)?")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_MAX_SCOPE_TEXT = 64

# ---- leaf kinds -------------------------------------------------------------
INT_POSITIVE = "INT_POSITIVE"
INT_OBSERVATION_EXCHANGE_INDEX = "INT_OBSERVATION_EXCHANGE_INDEX"
# ``trial_g`` is an evidence label only, but its domain is the already-canonical
# G domain: exactly the JSON integers 1..4 (no default, no conversion).
INT_TRIAL_G_LABEL = "INT_TRIAL_G_LABEL"
TRIAL_G_LABEL_DOMAIN = (1, 2, 3, 4)
BOOL = "BOOL"
SCOPE_TEXT = "SCOPE_TEXT"
RUN_ID = "RUN_ID"
DECIMAL_OPEN_UNIT = "DECIMAL_OPEN_UNIT"          # 0 < x < 1
DECIMAL_POSITIVE = "DECIMAL_POSITIVE"            # x > 0
DECIMAL_OPEN_UNIT_LIST = "DECIMAL_OPEN_UNIT_LIST"
SCHEMA_VERSION = "SCHEMA_VERSION"

# The complete, closed schema.  Every leaf is required; nothing else exists.
SCHEMA = {
    "schema_version": SCHEMA_VERSION,
    "run": {"run_id": RUN_ID},
    "selector": {
        "market_scope": {
            "exchange_index": INT_OBSERVATION_EXCHANGE_INDEX,
            "market_type": SCOPE_TEXT,
            "status": SCOPE_TEXT,
            "exclude_mve": BOOL,
        },
        "close_window": {
            "min_seconds_to_close": INT_POSITIVE,
            "max_seconds_to_close": INT_POSITIVE,
        },
        "a4": {
            "page_limit": INT_POSITIVE,
            "max_pages": INT_POSITIVE,
            "retained_count": INT_POSITIVE,
            "max_selected_ask": DECIMAL_OPEN_UNIT,
            "min_executable_ask_qty": DECIMAL_POSITIVE,
        },
        "c1": {
            "event_diverse_shortlist_size": INT_POSITIVE,
            "depth_band": DECIMAL_OPEN_UNIT,
        },
        "b1": {
            "lookback_seconds": INT_POSITIVE,
            "page_limit": INT_POSITIVE,
            "max_pages_per_ticker": INT_POSITIVE,
            "finalist_count": INT_POSITIVE,
            "exclude_block_trades": BOOL,
            "require_complete_active_window": BOOL,
        },
    },
    "shadow_experiment": {
        "trial_g": INT_TRIAL_G_LABEL,
        "minimum_spread_usd": DECIMAL_OPEN_UNIT_LIST,
    },
}


# ---- typed effective configuration -----------------------------------------
@dataclass(frozen=True)
class MarketScopeConfig:
    exchange_index: int
    market_type: str
    status: str
    exclude_mve: bool


@dataclass(frozen=True)
class CloseWindowConfig:
    min_seconds_to_close: int
    max_seconds_to_close: int


@dataclass(frozen=True)
class A4Config:
    page_limit: int
    max_pages: int
    retained_count: int
    max_selected_ask: Decimal
    min_executable_ask_qty: Decimal


@dataclass(frozen=True)
class C1Config:
    event_diverse_shortlist_size: int
    depth_band: Decimal


@dataclass(frozen=True)
class B1Config:
    lookback_seconds: int
    page_limit: int
    max_pages_per_ticker: int
    finalist_count: int
    exclude_block_trades: bool
    require_complete_active_window: bool


@dataclass(frozen=True)
class SelectorConfig:
    market_scope: MarketScopeConfig
    close_window: CloseWindowConfig
    a4: A4Config
    c1: C1Config
    b1: B1Config


@dataclass(frozen=True)
class ShadowExperimentConfig:
    trial_g: int
    minimum_spread_usd: Tuple[Decimal, ...]


@dataclass(frozen=True)
class ExperimentConfigV1:
    schema_version: int
    run_id: str
    selector: SelectorConfig
    shadow_experiment: ShadowExperimentConfig


# ---- strict JSON parsing ----------------------------------------------------
def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("CONFIG_DUPLICATE_KEY", "$", key)
        result[key] = value
    return result


def _reject_constant(token: str):
    raise ConfigError("CONFIG_NONFINITE_CONSTANT", "$", token)


def parse_config_json(raw: bytes) -> dict:
    if type(raw) is not bytes:
        raise ConfigError("CONFIG_WRONG_TYPE", "$", "config input must be exact bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError("CONFIG_NOT_UTF8", "$") from None
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                              parse_constant=_reject_constant, parse_float=_FloatToken)
    except ConfigError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ConfigError("CONFIG_JSON_MALFORMED", "$", type(exc).__name__) from None
    if type(document) is not dict:
        raise ConfigError("CONFIG_TOP_LEVEL_NOT_OBJECT", "$")
    return document


def _reject_floats_anywhere(node, path: str) -> None:
    if isinstance(node, _FloatToken):
        raise ConfigError("CONFIG_FLOAT_PROHIBITED", path, "binary JSON number; use a decimal string")
    if type(node) is dict:
        for key in sorted(node):
            _reject_floats_anywhere(node[key], f"{path}.{key}")
    elif type(node) is list:
        for index, item in enumerate(node):
            _reject_floats_anywhere(item, f"{path}[{index}]")


def _decimal(value, path: str, *, open_unit: bool) -> Decimal:
    if type(value) is not str:
        raise ConfigError("CONFIG_WRONG_TYPE", path, "decimal string required")
    if _DECIMAL_LEXICAL.fullmatch(value) is None:
        raise ConfigError("CONFIG_DECIMAL_INVALID", path, "plain decimal string digits[.digits] required")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise ConfigError("CONFIG_DECIMAL_INVALID", path) from None
    if not parsed.is_finite():
        raise ConfigError("CONFIG_DECIMAL_INVALID", path, "non-finite")
    if open_unit and not (Decimal("0") < parsed < Decimal("1")):
        raise ConfigError("CONFIG_VALUE_OUT_OF_RANGE", path, "must satisfy 0 < value < 1")
    if not open_unit and not parsed > Decimal("0"):
        raise ConfigError("CONFIG_VALUE_OUT_OF_RANGE", path, "must be > 0")
    return parsed


def _leaf(kind: str, value, path: str):
    if kind == SCHEMA_VERSION:
        if type(value) is not int:
            raise ConfigError("CONFIG_WRONG_TYPE", path, "integer required")
        if value != C.CONFIG_SCHEMA_VERSION:
            raise ConfigError("CONFIG_SCHEMA_VERSION_UNSUPPORTED", path, str(value))
        return value
    if kind in (INT_POSITIVE, INT_OBSERVATION_EXCHANGE_INDEX, INT_TRIAL_G_LABEL):
        if type(value) is not int:          # excludes bool (type(True) is bool)
            raise ConfigError("CONFIG_WRONG_TYPE", path, "integer required (boolean is not an integer)")
        if kind == INT_POSITIVE and value <= 0:
            raise ConfigError("CONFIG_VALUE_OUT_OF_RANGE", path, "must be > 0")
        if kind == INT_TRIAL_G_LABEL and value not in TRIAL_G_LABEL_DOMAIN:
            raise ConfigError("CONFIG_VALUE_OUT_OF_RANGE", path, "must be an integer in 1..4")
        if kind == INT_OBSERVATION_EXCHANGE_INDEX and value != C.OBSERVATION_EXCHANGE_INDEX:
            raise ConfigError("CONFIG_VALUE_OUT_OF_RANGE", path,
                              "must equal the code-immutable observation exchange_index "
                              f"{C.OBSERVATION_EXCHANGE_INDEX}")
        return value
    if kind == BOOL:
        if type(value) is not bool:
            raise ConfigError("CONFIG_WRONG_TYPE", path, "boolean required")
        return value
    if kind == SCOPE_TEXT:
        if type(value) is not str:
            raise ConfigError("CONFIG_WRONG_TYPE", path, "string required")
        if not value or value != value.strip() or len(value) > _MAX_SCOPE_TEXT:
            raise ConfigError("CONFIG_VALUE_OUT_OF_RANGE", path, "non-empty trimmed string <= 64 chars required")
        return value
    if kind == RUN_ID:
        if type(value) is not str:
            raise ConfigError("CONFIG_WRONG_TYPE", path, "string required")
        if _RUN_ID.fullmatch(value) is None:
            raise ConfigError("CONFIG_VALUE_OUT_OF_RANGE", path, "[A-Za-z0-9][A-Za-z0-9._-]{0,127} required")
        return value
    if kind == DECIMAL_OPEN_UNIT:
        return _decimal(value, path, open_unit=True)
    if kind == DECIMAL_POSITIVE:
        return _decimal(value, path, open_unit=False)
    if kind == DECIMAL_OPEN_UNIT_LIST:
        if type(value) is not list:
            raise ConfigError("CONFIG_WRONG_TYPE", path, "array of decimal strings required")
        if not value:
            raise ConfigError("CONFIG_EMPTY_LIST", path)
        parsed = tuple(_decimal(item, f"{path}[{i}]", open_unit=True) for i, item in enumerate(value))
        if len(set(parsed)) != len(parsed):
            raise ConfigError("CONFIG_DUPLICATE_VALUE", path, "spread values must be distinct")
        return parsed
    raise AssertionError(kind)  # pragma: no cover - closed schema


def _walk(schema: dict, node, path: str) -> dict:
    if type(node) is not dict:
        raise ConfigError("CONFIG_WRONG_TYPE", path, "object required")
    unknown = sorted(set(node) - set(schema))
    if unknown:
        raise ConfigError("CONFIG_UNKNOWN_KEY", f"{path}.{unknown[0]}")
    missing = sorted(set(schema) - set(node))
    if missing:
        raise ConfigError("CONFIG_MISSING_KEY", f"{path}.{missing[0]}")
    out = {}
    for key in sorted(schema):
        sub = schema[key]
        out[key] = _walk(sub, node[key], f"{path}.{key}") if type(sub) is dict else _leaf(sub, node[key], f"{path}.{key}")
    return out


def load_config_bytes(raw: bytes) -> ExperimentConfigV1:
    """Exact bytes -> validated, typed, normalized configuration."""
    document = parse_config_json(raw)
    _reject_floats_anywhere(document, "$")
    v = _walk(SCHEMA, document, "$")
    s = v["selector"]
    cw = s["close_window"]
    if not cw["min_seconds_to_close"] < cw["max_seconds_to_close"]:
        raise ConfigError("CONFIG_CROSS_FIELD_INVALID", "$.selector.close_window",
                          "min_seconds_to_close must be < max_seconds_to_close")
    cfg = ExperimentConfigV1(
        schema_version=v["schema_version"],
        run_id=v["run"]["run_id"],
        selector=SelectorConfig(
            market_scope=MarketScopeConfig(**s["market_scope"]),
            close_window=CloseWindowConfig(**cw),
            a4=A4Config(**s["a4"]),
            c1=C1Config(**s["c1"]),
            b1=B1Config(**s["b1"]),
        ),
        shadow_experiment=ShadowExperimentConfig(**v["shadow_experiment"]),
    )
    ceiling = whole_run_request_ceiling(cfg)
    if type(ceiling) is not int or ceiling <= 0:  # pragma: no cover - guaranteed by the schema
        raise ConfigError("CONFIG_CROSS_FIELD_INVALID", "$", "request ceiling not a positive integer")
    if ceiling > C.MAX_WHOLE_RUN_REQUESTS:
        raise ConfigError("CONFIG_REQUEST_CEILING_EXCEEDED", "$.selector",
                          f"derived whole-run request ceiling {ceiling} exceeds the immutable maximum "
                          f"{C.MAX_WHOLE_RUN_REQUESTS}")
    return cfg


# ---- config-derived request accounting --------------------------------------
def selector_max_requests(cfg: ExperimentConfigV1) -> int:
    """Worst-case selector GET count, derived ONLY from the effective config:

        A4 max_pages
        + 1 C1 batch-orderbook request
        + C1 shortlist size * B1 max_pages_per_ticker
        + B1 finalist_count C2 market reads
        + 1 C2 batch-orderbook request
    """
    s = cfg.selector
    return (s.a4.max_pages
            + 1
            + s.c1.event_diverse_shortlist_size * s.b1.max_pages_per_ticker
            + s.b1.finalist_count
            + 1)


def snapshot_request_count() -> int:
    return len(C.SNAPSHOT_READ_PLAN)


def whole_run_request_ceiling(cfg: ExperimentConfigV1) -> int:
    return selector_max_requests(cfg) + snapshot_request_count()


def b1_selection_mode(cfg: ExperimentConfigV1) -> str:
    if cfg.selector.b1.require_complete_active_window:
        return "STRICT_COMPLETE_ACTIVE_ONLY"
    return "RELAXED_COMPLETE_ACTIVE_OR_COMPLETE_ZERO__SHADOW_ONLY"


def effective_config_dict(cfg: ExperimentConfigV1) -> dict:
    """Normalized effective configuration (decimal strings via ``format(d, 'f')``)."""
    s = cfg.selector
    f = lambda d: format(d, "f")  # noqa: E731
    return {
        "schema_version": cfg.schema_version,
        "run": {"run_id": cfg.run_id},
        "selector": {
            "market_scope": {"exchange_index": s.market_scope.exchange_index,
                             "market_type": s.market_scope.market_type,
                             "status": s.market_scope.status,
                             "exclude_mve": s.market_scope.exclude_mve},
            "close_window": {"min_seconds_to_close": s.close_window.min_seconds_to_close,
                             "max_seconds_to_close": s.close_window.max_seconds_to_close},
            "a4": {"page_limit": s.a4.page_limit, "max_pages": s.a4.max_pages,
                   "retained_count": s.a4.retained_count, "max_selected_ask": f(s.a4.max_selected_ask),
                   "min_executable_ask_qty": f(s.a4.min_executable_ask_qty)},
            "c1": {"event_diverse_shortlist_size": s.c1.event_diverse_shortlist_size,
                   "depth_band": f(s.c1.depth_band)},
            "b1": {"lookback_seconds": s.b1.lookback_seconds, "page_limit": s.b1.page_limit,
                   "max_pages_per_ticker": s.b1.max_pages_per_ticker, "finalist_count": s.b1.finalist_count,
                   "exclude_block_trades": s.b1.exclude_block_trades,
                   "require_complete_active_window": s.b1.require_complete_active_window},
        },
        "shadow_experiment": {"trial_g": cfg.shadow_experiment.trial_g,
                              "minimum_spread_usd": [f(x) for x in cfg.shadow_experiment.minimum_spread_usd]},
    }


def effective_config_document(cfg: ExperimentConfigV1) -> dict:
    """``SELECTOR_CONFIG_EFFECTIVE.json`` content: effective config + derived facts."""
    return {
        "schema": "ShadowExperimentEffectiveConfigV1",
        "config_authority": C.CONFIG_AUTHORITY,
        "effective_config": effective_config_dict(cfg),
        "derived": {
            "selector_max_requests": selector_max_requests(cfg),
            "snapshot_request_count": snapshot_request_count(),
            "whole_run_request_ceiling": whole_run_request_ceiling(cfg),
            "b1_selection_mode": b1_selection_mode(cfg),
            "trial_g_authority": C.TRIAL_G_AUTHORITY,
            "minimum_spread_authority": C.MINIMUM_SPREAD_AUTHORITY,
            "canonical_G_selection": C.CANONICAL_G_SELECTION,
            "selected_market_count_max": C.SELECTED_MARKET_COUNT_MAX,
            "automatic_retries": C.AUTOMATIC_RETRIES,
        },
    }
