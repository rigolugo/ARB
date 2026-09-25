"""R1-D07 N1 user-proposed Strategy-1 test-parameter profile mechanism (V1).

Implements the local/offline, fail-closed mechanism of
`KALSHI_DEMO_R1_D07_N1_USER_PROPOSED_TEST_PARAMETERS_PROFILE_SPEC_01.md`
(bytes 24718, sha256
0a58a505373d602a13a9fb1e66d5addd36b53a8dda8c2a99ee744735f03eaedc) together
with its subordinate validation/identity, derivation, and experiment-binding
contracts:

    explicit selection (exactly one; no discovery API)
      -> one exact byte read (path mode; automatic retries 0)
      -> raw_profile_sha256 = SHA256(exact bytes)
      -> strict UTF-8 (no BOM) / duplicate-rejecting JSON
      -> exact V1 schema, constants, profile_id grammar, parameter key set
      -> JSON-string Decimal lexical grammar -> exact Decimal -> C07 ranges
      -> parameter_set_sha256 over the installed ARB canonical JSON/Decimal
      -> immutable ValidatedTestParameterProfileV1
      -> derive_strategy1_risk_config(fixed C07/C08 contract, profile)
         [exactly two leaves substituted; full differential check]
      -> ProfileRiskBindingV1 four-value tuple -> exact reconciliation

A validated profile proves only ``VALID_SCENARIO_PARAMETERS``.  Nothing in
this module grants, consumes, or implies any runtime authorization, risk
policy selection, G selection, release, writer, Gate-D, venue, credential,
or production capability.  There is no default profile, directory scan,
environment default, fallback, hot reload, persistence, network I/O, or
wall-clock authority here.

``RiskLimitConfigV1`` (protected ``risk_control.py``) and the canonical
JSON/Decimal serialization (protected ``execution_ledger.py``) are imported
read-only and reused exactly; neither is re-implemented.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from arb.execution_ledger import LedgerError, canonical_json_bytes
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    FlowRiskLimits,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    RiskControlError,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
)


__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "PROFILE_CLASS",
    "PURPOSE",
    "AUTHORITY",
    "RUNTIME_AUTHORIZATION",
    "VALIDATION_RESULT",
    "DEVIATION_LEAF",
    "WORKING_EXPOSURE_LEAF",
    "PROFILE_TOP_LEVEL_KEYS",
    "PROFILE_PARAMETER_KEYS",
    "AUTOMATIC_RETRIES",
    "ProfileFailureCode",
    "ProfileValidationError",
    "ValidatedTestParameterProfileV1",
    "ProfileRiskBindingV1",
    "compute_parameter_set_sha256",
    "validate_test_parameter_profile_bytes",
    "select_and_validate_test_parameter_profile",
    "derive_strategy1_risk_config",
    "bind_profile_risk",
    "derive_and_bind_strategy1_profile",
    "reconcile_profile_risk_binding",
]


# ---------------------------------------------------------------------------
# Exact V1 constants (TP-SCHEMA-001..004).
# ---------------------------------------------------------------------------

SCHEMA_ID = "ARB_USER_PROPOSED_TEST_PARAMETERS_V1"
SCHEMA_VERSION = 1
PROFILE_CLASS = "USER_PROPOSED_TEST_PARAMETERS"
PURPOSE = "R1_D07_N1_STRATEGY1_SCENARIO_TEST"
AUTHORITY = "NONE"
RUNTIME_AUTHORIZATION = "NONE"
# TP-AUTH-001: the ONLY meaning of successful validation.
VALIDATION_RESULT = "VALID_SCENARIO_PARAMETERS"

DEVIATION_LEAF = "per_order.max_abs_reference_price_deviation_usd"
WORKING_EXPOSURE_LEAF = "per_market.max_working_order_exposure_usd"

PROFILE_TOP_LEVEL_KEYS = frozenset({
    "schema_id",
    "schema_version",
    "profile_id",
    "profile_class",
    "purpose",
    "authority",
    "runtime_authorization",
    "parameters",
})
PROFILE_PARAMETER_KEYS = frozenset({DEVIATION_LEAF, WORKING_EXPOSURE_LEAF})

# TP-VAL-002 / TP-RUN-002.
AUTOMATIC_RETRIES = 0

_PROFILE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_DECIMAL_LEXICAL_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_UTF8_BOM = b"\xef\xbb\xbf"

_DEVIATION_MAX = Decimal("1")
_WORKING_EXPOSURE_MAX = Decimal("1.000000")


class ProfileFailureCode(enum.StrEnum):
    """TP-VAL-005 stable, secret-safe, machine-testable classifications.

    ``PROFILE_IMPLEMENTATION_EDIT_SET_INSUFFICIENT`` is the implementation-
    process stop code named by the controlling contract; no runtime path in
    this module raises it.
    """

    PROFILE_SELECTION_MISSING = "PROFILE_SELECTION_MISSING"
    PROFILE_SELECTION_AMBIGUOUS = "PROFILE_SELECTION_AMBIGUOUS"
    PROFILE_READ_FAILED = "PROFILE_READ_FAILED"
    PROFILE_UTF8_INVALID = "PROFILE_UTF8_INVALID"
    PROFILE_JSON_MALFORMED = "PROFILE_JSON_MALFORMED"
    PROFILE_DUPLICATE_KEY = "PROFILE_DUPLICATE_KEY"
    PROFILE_TOP_LEVEL_KEYS_MISMATCH = "PROFILE_TOP_LEVEL_KEYS_MISMATCH"
    PROFILE_CONSTANT_MISMATCH = "PROFILE_CONSTANT_MISMATCH"
    PROFILE_ID_INVALID = "PROFILE_ID_INVALID"
    PROFILE_PARAMETER_KEYS_MISMATCH = "PROFILE_PARAMETER_KEYS_MISMATCH"
    PROFILE_DECIMAL_TYPE_INVALID = "PROFILE_DECIMAL_TYPE_INVALID"
    PROFILE_DECIMAL_LEXICAL_INVALID = "PROFILE_DECIMAL_LEXICAL_INVALID"
    PROFILE_DECIMAL_RANGE_INVALID = "PROFILE_DECIMAL_RANGE_INVALID"
    PROFILE_IDENTITY_MISMATCH = "PROFILE_IDENTITY_MISMATCH"
    PROFILE_BINDING_MISMATCH = "PROFILE_BINDING_MISMATCH"
    PROFILE_HOT_RELOAD_PROHIBITED = "PROFILE_HOT_RELOAD_PROHIBITED"
    PROFILE_FIXED_CONTRACT_INVALID = "PROFILE_FIXED_CONTRACT_INVALID"
    PROFILE_OVERRIDE_FORBIDDEN = "PROFILE_OVERRIDE_FORBIDDEN"
    PROFILE_IMPLEMENTATION_EDIT_SET_INSUFFICIENT = "PROFILE_IMPLEMENTATION_EDIT_SET_INSUFFICIENT"


class ProfileValidationError(RuntimeError):
    """Fail-closed profile error.  The message is the classification only --
    never profile bytes, paths, or values (secret-safe by construction)."""

    def __init__(self, code: ProfileFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


def _fail(code: ProfileFailureCode) -> ProfileValidationError:
    return ProfileValidationError(code)


# ---------------------------------------------------------------------------
# Immutable carriers.
# ---------------------------------------------------------------------------

# Module-private mint key: only this module's validator can construct a
# ``ValidatedTestParameterProfileV1``, so a caller cannot forge a "validated"
# carrier whose identities were never computed from exact bytes.
_MINT_KEY = object()


class ValidatedTestParameterProfileV1:
    """Immutable validated-profile carrier (validation contract Section 1).

    It carries no authority field: validated authority is always ``NONE``.
    """

    __slots__ = (
        "profile_id",
        "max_abs_reference_price_deviation_usd",
        "max_working_order_exposure_usd",
        "raw_profile_sha256",
        "parameter_set_sha256",
    )

    def __init__(
        self,
        key: object,
        *,
        profile_id: str,
        max_abs_reference_price_deviation_usd: Decimal,
        max_working_order_exposure_usd: Decimal,
        raw_profile_sha256: str,
        parameter_set_sha256: str,
    ) -> None:
        if key is not _MINT_KEY:
            raise _fail(ProfileFailureCode.PROFILE_IDENTITY_MISMATCH)
        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(self, "max_abs_reference_price_deviation_usd", max_abs_reference_price_deviation_usd)
        object.__setattr__(self, "max_working_order_exposure_usd", max_working_order_exposure_usd)
        object.__setattr__(self, "raw_profile_sha256", raw_profile_sha256)
        object.__setattr__(self, "parameter_set_sha256", parameter_set_sha256)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ValidatedTestParameterProfileV1 is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("ValidatedTestParameterProfileV1 is immutable")

    def __copy__(self) -> "ValidatedTestParameterProfileV1":
        return self

    def __deepcopy__(self, memo: dict) -> "ValidatedTestParameterProfileV1":
        return self

    def __reduce_ex__(self, protocol: object):
        raise TypeError("ValidatedTestParameterProfileV1 is not serializable")

    def _identity(self) -> tuple:
        return (
            self.profile_id,
            self.max_abs_reference_price_deviation_usd.as_tuple(),
            self.max_working_order_exposure_usd.as_tuple(),
            self.raw_profile_sha256,
            self.parameter_set_sha256,
        )

    def __eq__(self, other: object) -> bool:
        if type(other) is not ValidatedTestParameterProfileV1:
            return NotImplemented
        return self._identity() == other._identity()

    def __hash__(self) -> int:
        return hash(self._identity())

    def __repr__(self) -> str:
        return (
            "ValidatedTestParameterProfileV1("
            f"profile_id={self.profile_id!r}, "
            f"raw_profile_sha256={self.raw_profile_sha256!r}, "
            f"parameter_set_sha256={self.parameter_set_sha256!r})"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ProfileRiskBindingV1:
    """TP-BIND-001 V1 profile/risk provenance tuple.  Evidence only -- it has
    no authority or permission semantics and contains no G value."""

    profile_id: str
    raw_profile_sha256: str
    parameter_set_sha256: str
    derived_risk_config_sha256: str

    def __post_init__(self) -> None:
        if type(self.profile_id) is not str or _PROFILE_ID_RE.fullmatch(self.profile_id) is None:
            raise _fail(ProfileFailureCode.PROFILE_IDENTITY_MISMATCH)
        for value in (self.raw_profile_sha256, self.parameter_set_sha256, self.derived_risk_config_sha256):
            if type(value) is not str or _HEX64_RE.fullmatch(value) is None:
                raise _fail(ProfileFailureCode.PROFILE_IDENTITY_MISMATCH)


# ---------------------------------------------------------------------------
# Identity (TP-ID-001..006).
# ---------------------------------------------------------------------------


def compute_parameter_set_sha256(deviation: Decimal, working_exposure: Decimal) -> str:
    """SHA-256 over the installed ARB canonical JSON of the parameter-only
    object (exact two dotted keys, Decimal-tagged values, no metadata)."""
    if type(deviation) is not Decimal or type(working_exposure) is not Decimal:
        raise _fail(ProfileFailureCode.PROFILE_DECIMAL_TYPE_INVALID)
    try:
        preimage = canonical_json_bytes({
            DEVIATION_LEAF: deviation,
            WORKING_EXPOSURE_LEAF: working_exposure,
        })
    except LedgerError:
        raise _fail(ProfileFailureCode.PROFILE_DECIMAL_RANGE_INVALID) from None
    return hashlib.sha256(preimage).hexdigest()


# ---------------------------------------------------------------------------
# Validation (TP-VAL-001..005, TP-DEC-001..006).
# ---------------------------------------------------------------------------


class _JsonNonStringNumber:
    """Parse-time marker for a JSON floating-point literal.  The literal is
    never converted to binary float; it only exists so the typed validation
    step can reject it as ``PROFILE_DECIMAL_TYPE_INVALID`` (or a constant
    mismatch) in the controlling order."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


class _DuplicateKey(Exception):
    pass


class _NonStandardConstant(Exception):
    pass


def _duplicate_rejecting_object(pairs: list) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _reject_constant(_: str) -> object:
    raise _NonStandardConstant


def _exact_str(value: object, expected: str) -> bool:
    return type(value) is str and value == expected


def _require_json_string(value: object) -> str:
    # TP-DEC-001: JSON strings only (numbers, booleans, null, arrays, objects
    # rejected; no binary-float coercion).
    if type(value) is not str:
        raise _fail(ProfileFailureCode.PROFILE_DECIMAL_TYPE_INVALID)
    return value


def validate_test_parameter_profile_bytes(raw: bytes) -> ValidatedTestParameterProfileV1:
    """Validate one exact immutable byte buffer (TP-VAL-004 steps 3-14)."""
    if type(raw) is not bytes:
        raise _fail(ProfileFailureCode.PROFILE_READ_FAILED)
    if len(raw) == 0:
        raise _fail(ProfileFailureCode.PROFILE_JSON_MALFORMED)
    # Step 3: raw identity over exactly these bytes.
    raw_profile_sha256 = hashlib.sha256(raw).hexdigest()
    # Step 4: no BOM; strict UTF-8.
    if raw.startswith(_UTF8_BOM):
        raise _fail(ProfileFailureCode.PROFILE_UTF8_INVALID)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise _fail(ProfileFailureCode.PROFILE_UTF8_INVALID) from None
    # Step 5: JSON with duplicate-key rejection at every depth and no
    # non-standard constants; float literals are never materialized as float.
    try:
        document = json.loads(
            text,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_float=_JsonNonStringNumber,
            parse_constant=_reject_constant,
        )
    except _DuplicateKey:
        raise _fail(ProfileFailureCode.PROFILE_DUPLICATE_KEY) from None
    except (_NonStandardConstant, ValueError, RecursionError):
        raise _fail(ProfileFailureCode.PROFILE_JSON_MALFORMED) from None
    # Step 6: exact top-level key set.
    if type(document) is not dict or set(document) != PROFILE_TOP_LEVEL_KEYS:
        raise _fail(ProfileFailureCode.PROFILE_TOP_LEVEL_KEYS_MISMATCH)
    # Step 7: exact constants, then profile_id grammar.
    schema_version = document["schema_version"]
    if (
        not _exact_str(document["schema_id"], SCHEMA_ID)
        or type(schema_version) is not int
        or schema_version != SCHEMA_VERSION
        or not _exact_str(document["profile_class"], PROFILE_CLASS)
        or not _exact_str(document["purpose"], PURPOSE)
        or not _exact_str(document["authority"], AUTHORITY)
        or not _exact_str(document["runtime_authorization"], RUNTIME_AUTHORIZATION)
    ):
        raise _fail(ProfileFailureCode.PROFILE_CONSTANT_MISMATCH)
    profile_id = document["profile_id"]
    if type(profile_id) is not str or _PROFILE_ID_RE.fullmatch(profile_id) is None:
        raise _fail(ProfileFailureCode.PROFILE_ID_INVALID)
    # Step 8: exact parameter key set (G or any other leaf is a mismatch).
    parameters = document["parameters"]
    if type(parameters) is not dict or set(parameters) != PROFILE_PARAMETER_KEYS:
        raise _fail(ProfileFailureCode.PROFILE_PARAMETER_KEYS_MISMATCH)
    ordered_leaves = (DEVIATION_LEAF, WORKING_EXPOSURE_LEAF)
    # Step 9: JSON-string types.
    texts = [_require_json_string(parameters[leaf]) for leaf in ordered_leaves]
    # Step 10: exact lexical grammar (no sign/exponent/whitespace/leading zero).
    for text_value in texts:
        if _DECIMAL_LEXICAL_RE.fullmatch(text_value) is None:
            raise _fail(ProfileFailureCode.PROFILE_DECIMAL_LEXICAL_INVALID)
    # Step 11: direct exact Decimal parse; finite only.
    values: list[Decimal] = []
    for text_value in texts:
        try:
            parsed = Decimal(text_value)
        except InvalidOperation:
            raise _fail(ProfileFailureCode.PROFILE_DECIMAL_LEXICAL_INVALID) from None
        if not parsed.is_finite():
            raise _fail(ProfileFailureCode.PROFILE_DECIMAL_LEXICAL_INVALID)
        values.append(parsed)
    deviation, working_exposure = values
    # Step 12: C07 semantic ranges, upper-bound equality inclusive.
    if not (Decimal("0") < deviation <= _DEVIATION_MAX):
        raise _fail(ProfileFailureCode.PROFILE_DECIMAL_RANGE_INVALID)
    if not (Decimal("0") < working_exposure <= _WORKING_EXPOSURE_MAX):
        raise _fail(ProfileFailureCode.PROFILE_DECIMAL_RANGE_INVALID)
    # Step 13: semantic parameter identity.
    parameter_set_sha256 = compute_parameter_set_sha256(deviation, working_exposure)
    # Step 14: one immutable carrier.
    return ValidatedTestParameterProfileV1(
        _MINT_KEY,
        profile_id=profile_id,
        max_abs_reference_price_deviation_usd=deviation,
        max_working_order_exposure_usd=working_exposure,
        raw_profile_sha256=raw_profile_sha256,
        parameter_set_sha256=parameter_set_sha256,
    )


def _read_profile_bytes(path: "str | os.PathLike[str]") -> bytes:
    """Exactly one read of the explicitly selected path (automatic retries 0).
    Any read failure (missing file, directory, permission) is terminal."""
    try:
        return Path(path).read_bytes()
    except (OSError, ValueError):
        raise _fail(ProfileFailureCode.PROFILE_READ_FAILED) from None


def select_and_validate_test_parameter_profile(
    *,
    profile_path: "str | os.PathLike[str] | None" = None,
    validated_profile: "ValidatedTestParameterProfileV1 | None" = None,
) -> ValidatedTestParameterProfileV1:
    """TP-VAL-001: exactly one explicit selection -- an exact profile path OR
    one already-loaded immutable validated carrier.  There is no discovery,
    default, environment default, directory scan, first-file choice, or
    fallback; missing/multiple selections fail before any profile I/O."""
    path_given = profile_path is not None and not (type(profile_path) is str and profile_path == "")
    carrier_given = validated_profile is not None
    if path_given and carrier_given:
        raise _fail(ProfileFailureCode.PROFILE_SELECTION_AMBIGUOUS)
    if not path_given and not carrier_given:
        raise _fail(ProfileFailureCode.PROFILE_SELECTION_MISSING)
    if carrier_given:
        if type(validated_profile) is not ValidatedTestParameterProfileV1:
            raise _fail(ProfileFailureCode.PROFILE_IDENTITY_MISMATCH)
        return validated_profile
    if not isinstance(profile_path, (str, os.PathLike)):
        # A collection of candidate paths is an ambiguous selection.
        raise _fail(ProfileFailureCode.PROFILE_SELECTION_AMBIGUOUS)
    raw = _read_profile_bytes(profile_path)
    return validate_test_parameter_profile_bytes(raw)


# ---------------------------------------------------------------------------
# Derivation (TP-DERIVE-001..006).
# ---------------------------------------------------------------------------

_FIXED_SECTION_TYPES = (
    ("per_order", PerOrderRiskLimits),
    ("per_market", PerMarketRiskLimits),
    ("conflict_domain_account", AccountRiskLimits),
    ("flow", FlowRiskLimits),
    ("state_integrity", StateIntegrityLimits),
    ("venue_defense", VenueDefensePolicy),
)

# TP-DERIVE-003 preserved fixed predicates: (dotted leaf, kind, exact value).
_FIXED_PREDICATES: tuple[tuple[str, str, object], ...] = (
    ("per_order.max_contracts", "decimal", Decimal("1.00")),
    ("per_order.max_worst_case_exposure_usd", "decimal", Decimal("1.000000")),
    ("per_order.price_reasonability_required", "bool", True),
    ("per_market.max_abs_net_position_contracts", "decimal", Decimal("1.00")),
    ("per_market.max_gross_exposure_usd", "decimal", Decimal("1.000000")),
    ("per_market.max_authoritative_working_orders", "int", 1),
    ("per_market.max_working_contracts", "decimal", Decimal("1.00")),
    ("conflict_domain_account.max_aggregate_exposure_usd", "decimal", Decimal("1.000000")),
    ("conflict_domain_account.max_aggregate_working_orders", "int", 1),
    ("conflict_domain_account.max_aggregate_working_contracts", "decimal", Decimal("1.00")),
    ("conflict_domain_account.max_unresolved_write_count", "int", 0),
    ("conflict_domain_account.max_conservative_unresolved_write_exposure_usd", "decimal", Decimal("0.000000")),
    ("flow.create_max_sends", "int", 1),
    ("flow.modify_replace_max_sends", "int", 0),
    ("flow.ordinary_cancel_max_sends", "int", 1),
    ("flow.automated_execution_max_sends", "int", 1),
    ("flow.emergency_cancel_max_sends", "int", 1),
    ("flow.emergency_cancel_max_in_flight", "int", 1),
    ("flow.emergency_retry_max_attempts_per_target_per_action", "int", 0),
)


def _leaf(config: RiskLimitConfigV1, dotted: str) -> object:
    section, name = dotted.split(".", 1)
    return getattr(getattr(config, section), name)


def _flatten_leaves(config: RiskLimitConfigV1) -> dict[str, object]:
    """Every leaf of the installed ``RiskLimitConfigV1`` keyed by dotted path
    (top-level scalars keyed by their own name)."""
    leaves: dict[str, object] = {}
    for field in dataclasses.fields(config):
        value = getattr(config, field.name)
        if dataclasses.is_dataclass(value):
            for child in dataclasses.fields(value):
                leaves[f"{field.name}.{child.name}"] = getattr(value, child.name)
        else:
            leaves[field.name] = value
    return leaves


def _leaf_identical(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is Decimal:
        return left.as_tuple() == right.as_tuple()  # type: ignore[union-attr]
    return left == right


def _require_fixed_contract(fixed: object) -> RiskLimitConfigV1:
    """Fixed-contract precondition (derivation contract Section 2).  The
    profile layer never invents, defaults, or repairs a predecessor leaf."""
    if type(fixed) is not RiskLimitConfigV1:
        raise _fail(ProfileFailureCode.PROFILE_FIXED_CONTRACT_INVALID)
    for section, section_type in _FIXED_SECTION_TYPES:
        if type(getattr(fixed, section, None)) is not section_type:
            raise _fail(ProfileFailureCode.PROFILE_FIXED_CONTRACT_INVALID)
    try:
        # Re-run the installed canonical invariants on the exact input.
        fixed.__post_init__()
    except RiskControlError:
        raise _fail(ProfileFailureCode.PROFILE_FIXED_CONTRACT_INVALID) from None
    for dotted, kind, expected in _FIXED_PREDICATES:
        observed = _leaf(fixed, dotted)
        if kind == "decimal":
            ok = type(observed) is Decimal and observed.is_finite() and observed == expected
        elif kind == "int":
            ok = type(observed) is int and observed == expected
        else:
            ok = type(observed) is bool and observed is expected
        if not ok:
            raise _fail(ProfileFailureCode.PROFILE_FIXED_CONTRACT_INVALID)
    return fixed


def _substitute_profile_leaves(
    fixed: RiskLimitConfigV1, profile: ValidatedTestParameterProfileV1
) -> RiskLimitConfigV1:
    """Exactly the two approved substitutions, through the installed
    ``RiskLimitConfigV1`` constructor (``dataclasses.replace`` re-runs its
    canonical ``__post_init__``)."""
    return dataclasses.replace(
        fixed,
        per_order=dataclasses.replace(
            fixed.per_order,
            max_abs_reference_price_deviation_usd=profile.max_abs_reference_price_deviation_usd,
        ),
        per_market=dataclasses.replace(
            fixed.per_market,
            max_working_order_exposure_usd=profile.max_working_order_exposure_usd,
        ),
    )


def _require_two_leaf_differential(
    fixed: RiskLimitConfigV1,
    derived: object,
    profile: ValidatedTestParameterProfileV1,
) -> RiskLimitConfigV1:
    """TP-DERIVE-006 full differential check over every leaf."""
    if type(derived) is not RiskLimitConfigV1:
        raise _fail(ProfileFailureCode.PROFILE_OVERRIDE_FORBIDDEN)
    fixed_leaves = _flatten_leaves(fixed)
    derived_leaves = _flatten_leaves(derived)
    if set(fixed_leaves) != set(derived_leaves):
        raise _fail(ProfileFailureCode.PROFILE_OVERRIDE_FORBIDDEN)
    for dotted, fixed_value in fixed_leaves.items():
        if dotted in PROFILE_PARAMETER_KEYS:
            continue
        if not _leaf_identical(fixed_value, derived_leaves[dotted]):
            raise _fail(ProfileFailureCode.PROFILE_OVERRIDE_FORBIDDEN)
    if not _leaf_identical(derived_leaves[DEVIATION_LEAF], profile.max_abs_reference_price_deviation_usd):
        raise _fail(ProfileFailureCode.PROFILE_OVERRIDE_FORBIDDEN)
    if not _leaf_identical(derived_leaves[WORKING_EXPOSURE_LEAF], profile.max_working_order_exposure_usd):
        raise _fail(ProfileFailureCode.PROFILE_OVERRIDE_FORBIDDEN)
    return derived


def derive_strategy1_risk_config(
    fixed_c07_c08_strategy1_contract: RiskLimitConfigV1,
    validated_test_profile: ValidatedTestParameterProfileV1,
) -> RiskLimitConfigV1:
    """TP-DERIVE-001: deterministic, local, no G, no profile metadata."""
    fixed = _require_fixed_contract(fixed_c07_c08_strategy1_contract)
    if type(validated_test_profile) is not ValidatedTestParameterProfileV1:
        raise _fail(ProfileFailureCode.PROFILE_IDENTITY_MISMATCH)
    try:
        derived = _substitute_profile_leaves(fixed, validated_test_profile)
    except RiskControlError:
        raise _fail(ProfileFailureCode.PROFILE_FIXED_CONTRACT_INVALID) from None
    return _require_two_leaf_differential(fixed, derived, validated_test_profile)


# ---------------------------------------------------------------------------
# Binding and reconciliation (TP-BIND-001..005, TP-RUN-004).
# ---------------------------------------------------------------------------


def bind_profile_risk(
    validated_test_profile: ValidatedTestParameterProfileV1,
    derived_risk_config: RiskLimitConfigV1,
) -> ProfileRiskBindingV1:
    if type(validated_test_profile) is not ValidatedTestParameterProfileV1:
        raise _fail(ProfileFailureCode.PROFILE_IDENTITY_MISMATCH)
    if type(derived_risk_config) is not RiskLimitConfigV1:
        raise _fail(ProfileFailureCode.PROFILE_IDENTITY_MISMATCH)
    return ProfileRiskBindingV1(
        profile_id=validated_test_profile.profile_id,
        raw_profile_sha256=validated_test_profile.raw_profile_sha256,
        parameter_set_sha256=validated_test_profile.parameter_set_sha256,
        derived_risk_config_sha256=derived_risk_config.sha256,
    )


def derive_and_bind_strategy1_profile(
    fixed_c07_c08_strategy1_contract: RiskLimitConfigV1,
    validated_test_profile: ValidatedTestParameterProfileV1,
) -> tuple[RiskLimitConfigV1, ProfileRiskBindingV1]:
    derived = derive_strategy1_risk_config(fixed_c07_c08_strategy1_contract, validated_test_profile)
    return derived, bind_profile_risk(validated_test_profile, derived)


def reconcile_profile_risk_binding(
    observed: ProfileRiskBindingV1, bound: ProfileRiskBindingV1
) -> ProfileRiskBindingV1:
    """Exact four-value identity equality only: no fuzzy identity, nearest
    profile, path-name equivalence, last-write-wins, or fallback."""
    if type(observed) is not ProfileRiskBindingV1 or type(bound) is not ProfileRiskBindingV1:
        raise _fail(ProfileFailureCode.PROFILE_BINDING_MISMATCH)
    if (
        observed.profile_id != bound.profile_id
        or observed.raw_profile_sha256 != bound.raw_profile_sha256
        or observed.parameter_set_sha256 != bound.parameter_set_sha256
        or observed.derived_risk_config_sha256 != bound.derived_risk_config_sha256
    ):
        raise _fail(ProfileFailureCode.PROFILE_BINDING_MISMATCH)
    return observed
