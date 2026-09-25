"""Offline tests for the R1-D07 N1 user-proposed Strategy-1 test-parameter
profile mechanism (``strategy1_test_parameter_profile.py``).

Every ``PROFILE-01`` .. ``PROFILE-32`` row of
``R1-D07_N1_TEST_PROFILE_IMPLEMENTATION_TEST_REQUIREMENTS_01.md`` maps to at
least one test below; test names carry the row ID.  The three supplied
NONCONTROLLING example profiles are embedded as their exact bytes and their
expected raw/semantic identities are the controlling vectors (never
recomputed from rewritten fixtures).  No network, credential, venue,
deployed-state, or persistent execution-state access occurs.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import pickle
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import arb.venues.kalshi.strategy1_test_parameter_profile as profile_module
from arb.execution_ledger import canonical_json_bytes
from arb.venues.kalshi.risk_control import (
    AccountRiskLimits,
    FlowRiskLimits,
    PerMarketRiskLimits,
    PerOrderRiskLimits,
    RiskLimitConfigV1,
    StateIntegrityLimits,
    VenueDefensePolicy,
)
from arb.venues.kalshi.strategy1_test_parameter_profile import (
    AUTOMATIC_RETRIES,
    DEVIATION_LEAF,
    PROFILE_PARAMETER_KEYS,
    PROFILE_TOP_LEVEL_KEYS,
    VALIDATION_RESULT,
    WORKING_EXPOSURE_LEAF,
    ProfileFailureCode,
    ProfileRiskBindingV1,
    ProfileValidationError,
    ValidatedTestParameterProfileV1,
    bind_profile_risk,
    compute_parameter_set_sha256,
    derive_and_bind_strategy1_profile,
    derive_strategy1_risk_config,
    reconcile_profile_risk_binding,
    select_and_validate_test_parameter_profile,
    validate_test_parameter_profile_bytes,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

# Exact supplied NONCONTROLLING example bytes (no trailing newline).
CONSERVATIVE_BYTES = (
    b'{"authority":"NONE","parameters":{"per_market.max_working_order_exposure_usd":"0.30",'
    b'"per_order.max_abs_reference_price_deviation_usd":"0.10"},"profile_class":'
    b'"USER_PROPOSED_TEST_PARAMETERS","profile_id":"conservative","purpose":'
    b'"R1_D07_N1_STRATEGY1_SCENARIO_TEST","runtime_authorization":"NONE","schema_id":'
    b'"ARB_USER_PROPOSED_TEST_PARAMETERS_V1","schema_version":1}'
)
TRIAL_01_BYTES = (
    b'{"authority":"NONE","parameters":{"per_market.max_working_order_exposure_usd":"0.60",'
    b'"per_order.max_abs_reference_price_deviation_usd":"0.30"},"profile_class":'
    b'"USER_PROPOSED_TEST_PARAMETERS","profile_id":"trial_01","purpose":'
    b'"R1_D07_N1_STRATEGY1_SCENARIO_TEST","runtime_authorization":"NONE","schema_id":'
    b'"ARB_USER_PROPOSED_TEST_PARAMETERS_V1","schema_version":1}'
)
WIDER_TEST_BYTES = (
    b'{"authority":"NONE","parameters":{"per_market.max_working_order_exposure_usd":"0.80",'
    b'"per_order.max_abs_reference_price_deviation_usd":"0.50"},"profile_class":'
    b'"USER_PROPOSED_TEST_PARAMETERS","profile_id":"wider_test","purpose":'
    b'"R1_D07_N1_STRATEGY1_SCENARIO_TEST","runtime_authorization":"NONE","schema_id":'
    b'"ARB_USER_PROPOSED_TEST_PARAMETERS_V1","schema_version":1}'
)

EXAMPLE_VECTORS = {
    "conservative": (
        CONSERVATIVE_BYTES, 366,
        "54aee22303c93767a0ded3c057cdccc78a4b2a45a187af5690959f5f52d39552",
        "c1b199e41b00d416410ea9c141a881993118e3486a94e85df8687156289d3693",
        Decimal("0.10"), Decimal("0.30"),
    ),
    "trial_01": (
        TRIAL_01_BYTES, 362,
        "92f469aaf57e8d5323bf2c06be58f45219e014444a0eb4d29eab341f3d58dbc8",
        "a995c6b02f8107fbfae94d143bdf8a1febee05fc5f84e1661cb63419dcc02d9d",
        Decimal("0.30"), Decimal("0.60"),
    ),
    "wider_test": (
        WIDER_TEST_BYTES, 364,
        "7c7a295a9e375e4332bd676fa549f71b3d9b44add4f27b8aab60df5c679147c8",
        "106eef5d859634adc3d315a881c2ccc97810ba56bcb8ed0cc5d233217e8a6bb8",
        Decimal("0.50"), Decimal("0.80"),
    ),
}

C = ProfileFailureCode


def _doc(**overrides: object) -> dict:
    document: dict = {
        "schema_id": "ARB_USER_PROPOSED_TEST_PARAMETERS_V1",
        "schema_version": 1,
        "profile_id": "synthetic_scenario",
        "profile_class": "USER_PROPOSED_TEST_PARAMETERS",
        "purpose": "R1_D07_N1_STRATEGY1_SCENARIO_TEST",
        "authority": "NONE",
        "runtime_authorization": "NONE",
        "parameters": {
            DEVIATION_LEAF: "0.30",
            WORKING_EXPOSURE_LEAF: "0.60",
        },
    }
    document.update(overrides)
    return document


def _params(deviation: object = "0.30", exposure: object = "0.60") -> dict:
    return {DEVIATION_LEAF: deviation, WORKING_EXPOSURE_LEAF: exposure}


def _bytes(document: object, **dumps_kwargs: object) -> bytes:
    return json.dumps(document, **dumps_kwargs).encode("utf-8")


def fixed_strategy1_contract(
    *,
    deviation: Decimal = Decimal("0"),
    exposure: Decimal = Decimal("1.000000"),
    domain: str = "synthetic-conflict-domain",
) -> RiskLimitConfigV1:
    """A synthetic fixed C07/C08 Strategy-1 contract satisfying every
    TP-DERIVE-003 predicate.  The two profile-controlled leaves carry
    arbitrary placeholder values that derivation replaces."""
    return RiskLimitConfigV1(
        1, domain, "USD",
        PerOrderRiskLimits(Decimal("1.00"), Decimal("1.000000"), True, deviation, 1_000),
        PerMarketRiskLimits(Decimal("1.00"), Decimal("1.000000"), 1, Decimal("1.00"), exposure),
        AccountRiskLimits(Decimal("1.000000"), 1, Decimal("1.00"), 0, Decimal("0.000000")),
        FlowRiskLimits(1, 1_000, 0, 1_000, 1, 1_000, 1, 1_000, 1, 1_000, 1, 500, 0, 10, 100),
        StateIntegrityLimits(1_000, 1_000, 10, 1, 500, 10, 100),
        VenueDefensePolicy("NOT_REQUIRED", None, True, "NO_SAFETY_CREDIT", "NO_SAFETY_CREDIT"),
    )


def _leaves(config: RiskLimitConfigV1) -> dict:
    out: dict = {}
    for f in dataclasses.fields(config):
        value = getattr(config, f.name)
        if dataclasses.is_dataclass(value):
            for child in dataclasses.fields(value):
                out[f"{f.name}.{child.name}"] = getattr(value, child.name)
        else:
            out[f.name] = value
    return out


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(raw) + raw).hexdigest()


class _ProfileTestCase(unittest.TestCase):
    def assertProfileFails(self, code: ProfileFailureCode, raw: bytes) -> None:
        with self.assertRaises(ProfileValidationError) as ctx:
            validate_test_parameter_profile_bytes(raw)
        self.assertIs(ctx.exception.code, code)
        self.assertEqual(str(ctx.exception), code.value)

    def valid(self, raw: bytes) -> ValidatedTestParameterProfileV1:
        return validate_test_parameter_profile_bytes(raw)


class ExampleVectorTests(_ProfileTestCase):
    def _check(self, name: str) -> None:
        raw, size, raw_sha, param_sha, deviation, exposure = EXAMPLE_VECTORS[name]
        self.assertEqual(len(raw), size)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), raw_sha)
        profile = self.valid(raw)
        self.assertEqual(profile.profile_id, name)
        self.assertEqual(profile.raw_profile_sha256, raw_sha)
        self.assertEqual(profile.parameter_set_sha256, param_sha)
        self.assertEqual(profile.max_abs_reference_price_deviation_usd.as_tuple(), deviation.as_tuple())
        self.assertEqual(profile.max_working_order_exposure_usd.as_tuple(), exposure.as_tuple())

    def test_profile_01_conservative_exact_vectors(self) -> None:
        self._check("conservative")

    def test_profile_02_trial_01_exact_vectors(self) -> None:
        self._check("trial_01")

    def test_profile_03_wider_test_exact_vectors(self) -> None:
        self._check("wider_test")

    def test_semantic_preimage_is_installed_arb_canonical_decimal_json(self) -> None:
        self.assertEqual(
            canonical_json_bytes({DEVIATION_LEAF: Decimal("0.10"), WORKING_EXPOSURE_LEAF: Decimal("0.30")}),
            b'{"per_market.max_working_order_exposure_usd":{"$decimal":"0.3"},'
            b'"per_order.max_abs_reference_price_deviation_usd":{"$decimal":"0.1"}}',
        )
        self.assertEqual(
            compute_parameter_set_sha256(Decimal("0.10"), Decimal("0.30")),
            EXAMPLE_VECTORS["conservative"][3],
        )

    def test_example_bytes_match_supplied_register_identities(self) -> None:
        # The supplied EXAMPLE_PROFILE_REGISTER identities (noncontrolling).
        for name, (raw, _, raw_sha, param_sha, _, _) in EXAMPLE_VECTORS.items():
            with self.subTest(name=name):
                profile = self.valid(raw)
                self.assertEqual((profile.raw_profile_sha256, profile.parameter_set_sha256), (raw_sha, param_sha))


class SchemaTests(_ProfileTestCase):
    def test_profile_04_missing_required_top_level_field(self) -> None:
        for key in sorted(PROFILE_TOP_LEVEL_KEYS):
            with self.subTest(key=key):
                document = _doc()
                del document[key]
                self.assertProfileFails(C.PROFILE_TOP_LEVEL_KEYS_MISMATCH, _bytes(document))

    def test_profile_05_unknown_top_level_field(self) -> None:
        for extra in ("default", "g", "notes", "risk_values_selected"):
            with self.subTest(extra=extra):
                self.assertProfileFails(C.PROFILE_TOP_LEVEL_KEYS_MISMATCH, _bytes(_doc(**{extra: "x"})))

    def test_non_object_top_level_rejected(self) -> None:
        for raw in (b"[]", b'"x"', b"1", b"null"):
            with self.subTest(raw=raw):
                self.assertProfileFails(C.PROFILE_TOP_LEVEL_KEYS_MISMATCH, raw)

    def test_profile_06_unknown_or_replaced_parameter_key(self) -> None:
        added = _params()
        added["per_order.max_contracts"] = "1"
        replaced = {DEVIATION_LEAF: "0.30", "per_market.max_gross_exposure_usd": "0.60"}
        for parameters in (added, replaced, {DEVIATION_LEAF: "0.30"}, {}, [], "x"):
            with self.subTest(parameters=parameters):
                self.assertProfileFails(C.PROFILE_PARAMETER_KEYS_MISMATCH, _bytes(_doc(parameters=parameters)))

    def test_profile_07_g_is_never_a_profile_parameter(self) -> None:
        with_g = _params()
        with_g["G.max_ordinary_write_sends"] = "1"
        g_only = {DEVIATION_LEAF: "0.30", "G.max_ordinary_write_sends": "1"}
        for parameters in (with_g, g_only):
            with self.subTest(parameters=parameters):
                self.assertProfileFails(C.PROFILE_PARAMETER_KEYS_MISMATCH, _bytes(_doc(parameters=parameters)))
        self.assertProfileFails(C.PROFILE_TOP_LEVEL_KEYS_MISMATCH, _bytes(_doc(G={"max_ordinary_write_sends": 1})))
        self.assertNotIn("G.max_ordinary_write_sends", PROFILE_PARAMETER_KEYS)
        # No G surface anywhere on the carrier, binding, or derived config.
        profile = self.valid(CONSERVATIVE_BYTES)
        derived, binding = derive_and_bind_strategy1_profile(fixed_strategy1_contract(), profile)
        for obj in (profile, binding):
            for attr in dir(obj):
                self.assertNotIn("ordinary_write_sends", attr)
        self.assertFalse(any("ordinary_write_sends" in leaf for leaf in _leaves(derived)))

    def test_profile_21_authority_and_runtime_authorization_must_be_none(self) -> None:
        for field in ("authority", "runtime_authorization"):
            for value in ("ALL", "none", "NONE ", "", None, 0, ["NONE"], {"NONE": 1}):
                with self.subTest(field=field, value=value):
                    self.assertProfileFails(C.PROFILE_CONSTANT_MISMATCH, _bytes(_doc(**{field: value})))

    def test_other_constants_exact(self) -> None:
        cases = {
            "schema_id": ("ARB_USER_PROPOSED_TEST_PARAMETERS_V2", None),
            "schema_version": (2, True, 1.0, "1", 0),
            "profile_class": ("USER_SELECTED_RISK_POLICY",),
            "purpose": ("PRODUCTION",),
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertProfileFails(C.PROFILE_CONSTANT_MISMATCH, _bytes(_doc(**{field: value})))

    def test_profile_id_grammar(self) -> None:
        for good in ("a", "0", "trial_01", "wider-test", "a" * 64):
            with self.subTest(good=good):
                self.assertEqual(self.valid(_bytes(_doc(profile_id=good))).profile_id, good)
        for bad in ("", "_a", "-a", "A", "trial 01", "a" * 65, "trial.01", "tri\u00e9l", "a\n", 1, None):
            with self.subTest(bad=bad):
                self.assertProfileFails(C.PROFILE_ID_INVALID, _bytes(_doc(profile_id=bad)))


class DecimalTests(_ProfileTestCase):
    def test_profile_08_json_numeric_values_rejected_even_when_equal(self) -> None:
        for raw_value in (b"0.3", b"1", b"0", b"3e-1", b"true", b"null", b"[]", b"{}"):
            with self.subTest(value=raw_value):
                raw = (
                    b'{"authority":"NONE","parameters":{"per_market.max_working_order_exposure_usd":"0.60",'
                    b'"per_order.max_abs_reference_price_deviation_usd":' + raw_value + b'},'
                    b'"profile_class":"USER_PROPOSED_TEST_PARAMETERS","profile_id":"x","purpose":'
                    b'"R1_D07_N1_STRATEGY1_SCENARIO_TEST","runtime_authorization":"NONE","schema_id":'
                    b'"ARB_USER_PROPOSED_TEST_PARAMETERS_V1","schema_version":1}'
                )
                self.assertProfileFails(C.PROFILE_DECIMAL_TYPE_INVALID, raw)

    def test_float_literal_never_materialized_as_binary_float(self) -> None:
        with mock.patch("builtins.float", side_effect=AssertionError("binary float used")):
            with self.assertRaises(ProfileValidationError) as ctx:
                validate_test_parameter_profile_bytes(
                    _bytes(_doc()).replace(b'"0.30"', b"0.30")
                )
        self.assertIs(ctx.exception.code, C.PROFILE_DECIMAL_TYPE_INVALID)

    def test_profile_09_zero_deviation_rejected(self) -> None:
        for value in ("0", "0.0", "0.000000"):
            with self.subTest(value=value):
                self.assertProfileFails(C.PROFILE_DECIMAL_RANGE_INVALID, _bytes(_doc(parameters=_params(deviation=value))))

    def test_profile_10_zero_working_exposure_rejected(self) -> None:
        for value in ("0", "0.0", "0.000000"):
            with self.subTest(value=value):
                self.assertProfileFails(C.PROFILE_DECIMAL_RANGE_INVALID, _bytes(_doc(parameters=_params(exposure=value))))

    def test_profile_11_deviation_above_one_rejected(self) -> None:
        for value in ("1.000001", "1.0000000001", "2", "10"):
            with self.subTest(value=value):
                self.assertProfileFails(C.PROFILE_DECIMAL_RANGE_INVALID, _bytes(_doc(parameters=_params(deviation=value))))

    def test_profile_12_working_exposure_above_one_rejected(self) -> None:
        for value in ("1.000001", "1.0000000001", "2"):
            with self.subTest(value=value):
                self.assertProfileFails(C.PROFILE_DECIMAL_RANGE_INVALID, _bytes(_doc(parameters=_params(exposure=value))))

    def test_profile_13_malformed_or_forbidden_decimal_forms(self) -> None:
        forms = ("3e-1", "3E-1", "+0.3", "-0.3", " 0.3", "0.3 ", "00.30", "01", ".3", "3.", ".",
                 "", "0x1", "NaN", "Infinity", "-0", "1_0", "0,3", "\u0660.3", "\uff10.3", "0.3\n")
        for leaf in ("deviation", "exposure"):
            for form in forms:
                with self.subTest(leaf=leaf, form=form):
                    self.assertProfileFails(
                        C.PROFILE_DECIMAL_LEXICAL_INVALID, _bytes(_doc(parameters=_params(**{leaf: form})))
                    )

    def test_profile_26_sign_exponent_whitespace_rejected(self) -> None:
        for form in ("+0.3", "-0.3", "3e-1", " 0.3", "0.3 "):
            for leaf in ("deviation", "exposure"):
                with self.subTest(form=form, leaf=leaf):
                    self.assertProfileFails(
                        C.PROFILE_DECIMAL_LEXICAL_INVALID, _bytes(_doc(parameters=_params(**{leaf: form})))
                    )

    def test_profile_23_deviation_upper_bound_equality_valid(self) -> None:
        for value in ("1", "1.000000", "1.0"):
            with self.subTest(value=value):
                profile = self.valid(_bytes(_doc(parameters=_params(deviation=value))))
                self.assertEqual(profile.max_abs_reference_price_deviation_usd, Decimal("1"))

    def test_profile_24_working_exposure_upper_bound_equality_valid(self) -> None:
        for value in ("1", "1.000000", "1.0"):
            with self.subTest(value=value):
                profile = self.valid(_bytes(_doc(parameters=_params(exposure=value))))
                self.assertEqual(profile.max_working_order_exposure_usd, Decimal("1.000000"))

    def test_lexically_valid_small_and_scaled_values_accepted_without_quantization(self) -> None:
        profile = self.valid(_bytes(_doc(parameters=_params(deviation="0.0000001", exposure="0.123456789"))))
        self.assertEqual(profile.max_abs_reference_price_deviation_usd.as_tuple(), Decimal("0.0000001").as_tuple())
        self.assertEqual(profile.max_working_order_exposure_usd.as_tuple(), Decimal("0.123456789").as_tuple())


class EncodingAndJsonTests(_ProfileTestCase):
    def test_profile_14_duplicate_key_at_top_or_nested(self) -> None:
        top = CONSERVATIVE_BYTES[:-1] + b',"authority":"NONE"}'
        nested = CONSERVATIVE_BYTES.replace(
            b'"0.10"}', b'"0.10","per_order.max_abs_reference_price_deviation_usd":"0.10"}'
        )
        for raw in (top, nested):
            with self.subTest(raw=raw):
                self.assertProfileFails(C.PROFILE_DUPLICATE_KEY, raw)

    def test_profile_27_bom_prefixed_json_rejected(self) -> None:
        self.assertProfileFails(C.PROFILE_UTF8_INVALID, b"\xef\xbb\xbf" + CONSERVATIVE_BYTES)

    def test_invalid_utf8_rejected(self) -> None:
        self.assertProfileFails(C.PROFILE_UTF8_INVALID, CONSERVATIVE_BYTES.replace(b"conservative", b"conserv\xffative"))
        self.assertProfileFails(C.PROFILE_UTF8_INVALID, b'{"a":"\xc3"}')

    def test_empty_and_malformed_json_rejected(self) -> None:
        for raw in (b"", b" ", b"{", CONSERVATIVE_BYTES[:-1], b'{"a":1,}', b"{'a':1}"):
            with self.subTest(raw=raw):
                self.assertProfileFails(C.PROFILE_JSON_MALFORMED, raw)

    def test_nonstandard_json_constants_rejected(self) -> None:
        for constant in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(constant=constant):
                raw = CONSERVATIVE_BYTES.replace(b'"schema_version":1', b'"schema_version":' + constant)
                self.assertProfileFails(C.PROFILE_JSON_MALFORMED, raw)

    def test_non_bytes_input_rejected(self) -> None:
        for value in (CONSERVATIVE_BYTES.decode(), bytearray(CONSERVATIVE_BYTES), memoryview(CONSERVATIVE_BYTES), None):
            with self.subTest(value=type(value)):
                with self.assertRaises(ProfileValidationError):
                    validate_test_parameter_profile_bytes(value)  # type: ignore[arg-type]

    def test_errors_are_secret_safe_classifications_only(self) -> None:
        marker = "Bearer SYNTHETIC_TOKEN_NOT_A_SECRET"
        with self.assertRaises(ProfileValidationError) as ctx:
            validate_test_parameter_profile_bytes(_bytes(_doc(profile_id=marker)))
        self.assertEqual(str(ctx.exception), "PROFILE_ID_INVALID")
        self.assertNotIn("SYNTHETIC", repr(ctx.exception.args))


class IdentityTests(_ProfileTestCase):
    def test_profile_15_whitespace_key_order_display_scale_preserve_parameter_hash(self) -> None:
        base = self.valid(CONSERVATIVE_BYTES)
        document = json.loads(CONSERVATIVE_BYTES)
        pretty = _bytes(document, indent=2)
        reordered = _bytes(dict(reversed(list(document.items()))))
        scaled_document = json.loads(CONSERVATIVE_BYTES)
        scaled_document["parameters"] = _params(deviation="0.1", exposure="0.300000")
        scaled = _bytes(scaled_document)
        for raw in (pretty, reordered, scaled):
            with self.subTest(raw=raw):
                other = self.valid(raw)
                self.assertNotEqual(other.raw_profile_sha256, base.raw_profile_sha256)
                self.assertEqual(other.parameter_set_sha256, base.parameter_set_sha256)

    def test_profile_25_display_scale_0_30_vs_0_3(self) -> None:
        a = self.valid(_bytes(_doc(parameters=_params(deviation="0.30"))))
        b = self.valid(_bytes(_doc(parameters=_params(deviation="0.3"))))
        self.assertNotEqual(a.raw_profile_sha256, b.raw_profile_sha256)
        self.assertEqual(a.parameter_set_sha256, b.parameter_set_sha256)

    def test_profile_16_economic_change_changes_parameter_hash(self) -> None:
        base = self.valid(_bytes(_doc()))
        for parameters in (_params(deviation="0.31"), _params(exposure="0.61"), _params("0.60", "0.30")):
            with self.subTest(parameters=parameters):
                other = self.valid(_bytes(_doc(parameters=parameters)))
                self.assertNotEqual(other.parameter_set_sha256, base.parameter_set_sha256)

    def test_profile_metadata_not_in_parameter_hash(self) -> None:
        a = self.valid(_bytes(_doc(profile_id="alpha")))
        b = self.valid(_bytes(_doc(profile_id="beta")))
        self.assertNotEqual(a.raw_profile_sha256, b.raw_profile_sha256)
        self.assertEqual(a.parameter_set_sha256, b.parameter_set_sha256)

    def test_raw_hash_is_sha256_of_exact_bytes(self) -> None:
        raw = _bytes(_doc(), indent=3) + b"\n"
        self.assertEqual(self.valid(raw).raw_profile_sha256, hashlib.sha256(raw).hexdigest())


class SelectionTests(_ProfileTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        for name, (raw, *_rest) in EXAMPLE_VECTORS.items():
            (self.dir / f"{name}.json").write_bytes(raw)

    def test_profile_19_omitted_selection_fails_closed_without_io_or_default(self) -> None:
        with mock.patch.object(profile_module, "_read_profile_bytes", side_effect=AssertionError("io")):
            for kwargs in ({}, {"profile_path": None}, {"profile_path": ""}, {"validated_profile": None}):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ProfileValidationError) as ctx:
                        select_and_validate_test_parameter_profile(**kwargs)
                    self.assertIs(ctx.exception.code, C.PROFILE_SELECTION_MISSING)

    def test_profile_19_ambiguous_selection_fails_closed(self) -> None:
        carrier = self.valid(CONSERVATIVE_BYTES)
        with mock.patch.object(profile_module, "_read_profile_bytes", side_effect=AssertionError("io")):
            for kwargs in (
                {"profile_path": self.dir / "conservative.json", "validated_profile": carrier},
                {"profile_path": [self.dir / "conservative.json", self.dir / "trial_01.json"]},
                {"profile_path": (self.dir / "trial_01.json",)},
            ):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ProfileValidationError) as ctx:
                        select_and_validate_test_parameter_profile(**kwargs)
                    self.assertIs(ctx.exception.code, C.PROFILE_SELECTION_AMBIGUOUS)

    def test_profile_19_no_directory_scan_environment_default_or_fallback(self) -> None:
        scan_guard = AssertionError("directory scan")
        env = {"ARB_TEST_PARAMETER_PROFILE": str(self.dir / "conservative.json"), "ARB_DEFAULT_PROFILE": "conservative"}
        with mock.patch.dict(os.environ, env), \
                mock.patch("os.listdir", side_effect=scan_guard), \
                mock.patch("os.scandir", side_effect=scan_guard), \
                mock.patch("os.walk", side_effect=scan_guard), \
                mock.patch.object(Path, "iterdir", side_effect=scan_guard), \
                mock.patch.object(Path, "glob", side_effect=scan_guard):
            with self.assertRaises(ProfileValidationError) as ctx:
                select_and_validate_test_parameter_profile()
            self.assertIs(ctx.exception.code, C.PROFILE_SELECTION_MISSING)
            # A directory is not a registry: selecting it is a read failure,
            # never a first-file / "conservative" choice.
            with self.assertRaises(ProfileValidationError) as ctx:
                select_and_validate_test_parameter_profile(profile_path=self.dir)
            self.assertIs(ctx.exception.code, C.PROFILE_READ_FAILED)
            # Missing explicit file: no fallback to a sibling profile.
            with self.assertRaises(ProfileValidationError) as ctx:
                select_and_validate_test_parameter_profile(profile_path=self.dir / "absent.json")
            self.assertIs(ctx.exception.code, C.PROFILE_READ_FAILED)
            profile = select_and_validate_test_parameter_profile(profile_path=self.dir / "trial_01.json")
            self.assertEqual(profile.profile_id, "trial_01")
        for name in dir(profile_module):
            self.assertNotIn("DEFAULT", name.upper())
        source = (REPO_ROOT / "src/arb/venues/kalshi/strategy1_test_parameter_profile.py").read_text("utf-8")
        for forbidden in ("os.environ", "getenv", "listdir", "scandir", "glob(", "iterdir", "os.walk", "watch"):
            self.assertNotIn(forbidden, source)

    def test_explicit_path_read_exactly_once_and_no_retry(self) -> None:
        self.assertEqual(AUTOMATIC_RETRIES, 0)
        calls: list = []
        real = profile_module._read_profile_bytes

        def counting(path):
            calls.append(path)
            return real(path)

        with mock.patch.object(profile_module, "_read_profile_bytes", side_effect=counting):
            select_and_validate_test_parameter_profile(profile_path=self.dir / "wider_test.json")
        self.assertEqual(len(calls), 1)
        read_bytes_calls: list = []
        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=lambda p: read_bytes_calls.append(p) or (_ for _ in ()).throw(OSError("synthetic"))):
            with self.assertRaises(ProfileValidationError) as ctx:
                select_and_validate_test_parameter_profile(profile_path=self.dir / "wider_test.json")
        self.assertIs(ctx.exception.code, C.PROFILE_READ_FAILED)
        self.assertEqual(len(read_bytes_calls), 1)

    def test_already_loaded_carrier_selection_mode(self) -> None:
        carrier = self.valid(TRIAL_01_BYTES)
        with mock.patch.object(profile_module, "_read_profile_bytes", side_effect=AssertionError("io")):
            self.assertIs(select_and_validate_test_parameter_profile(validated_profile=carrier), carrier)
            with self.assertRaises(ProfileValidationError) as ctx:
                select_and_validate_test_parameter_profile(validated_profile=object())  # type: ignore[arg-type]
            self.assertIs(ctx.exception.code, C.PROFILE_IDENTITY_MISMATCH)


class CarrierImmutabilityTests(_ProfileTestCase):
    def test_carrier_cannot_be_forged_or_mutated(self) -> None:
        with self.assertRaises(ProfileValidationError) as ctx:
            ValidatedTestParameterProfileV1(
                object(), profile_id="forged",
                max_abs_reference_price_deviation_usd=Decimal("1"),
                max_working_order_exposure_usd=Decimal("1"),
                raw_profile_sha256="0" * 64, parameter_set_sha256="0" * 64,
            )
        self.assertIs(ctx.exception.code, C.PROFILE_IDENTITY_MISMATCH)
        carrier = self.valid(CONSERVATIVE_BYTES)
        for attr in ("profile_id", "raw_profile_sha256", "max_abs_reference_price_deviation_usd", "authority"):
            with self.subTest(attr=attr):
                with self.assertRaises(AttributeError):
                    setattr(carrier, attr, "x")
        with self.assertRaises(AttributeError):
            del carrier.profile_id
        self.assertIs(copy.copy(carrier), carrier)
        self.assertIs(copy.deepcopy(carrier), carrier)
        with self.assertRaises(TypeError):
            pickle.dumps(carrier)
        self.assertEqual(carrier, self.valid(CONSERVATIVE_BYTES))
        self.assertFalse(hasattr(carrier, "__dict__"))

    def test_binding_is_frozen_and_format_checked(self) -> None:
        binding = ProfileRiskBindingV1("x", "a" * 64, "b" * 64, "c" * 64)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            binding.profile_id = "y"  # type: ignore[misc]
        for args in (
            ("X", "a" * 64, "b" * 64, "c" * 64),
            ("x", "A" * 64, "b" * 64, "c" * 64),
            ("x", "a" * 63, "b" * 64, "c" * 64),
            ("x", "a" * 64, "b" * 64, None),
        ):
            with self.subTest(args=args):
                with self.assertRaises(ProfileValidationError) as ctx:
                    ProfileRiskBindingV1(*args)  # type: ignore[arg-type]
                self.assertIs(ctx.exception.code, C.PROFILE_IDENTITY_MISMATCH)
        self.assertEqual(
            [f.name for f in dataclasses.fields(ProfileRiskBindingV1)],
            ["profile_id", "raw_profile_sha256", "parameter_set_sha256", "derived_risk_config_sha256"],
        )


class DerivationTests(_ProfileTestCase):
    def test_profile_17_two_profiles_same_fixed_contract_differ_only_in_two_leaves(self) -> None:
        fixed = fixed_strategy1_contract()
        a = derive_strategy1_risk_config(fixed, self.valid(CONSERVATIVE_BYTES))
        b = derive_strategy1_risk_config(fixed, self.valid(WIDER_TEST_BYTES))
        self.assertIs(type(a), RiskLimitConfigV1)
        la, lb, lf = _leaves(a), _leaves(b), _leaves(fixed)
        self.assertEqual(set(la), set(lf))
        differing = {k for k in la if (type(la[k]), la[k]) != (type(lb[k]), lb[k])}
        self.assertEqual(differing, {DEVIATION_LEAF, WORKING_EXPOSURE_LEAF})
        for leaves in (la, lb):
            for key, value in lf.items():
                if key in PROFILE_PARAMETER_KEYS:
                    continue
                with self.subTest(key=key):
                    self.assertIs(type(leaves[key]), type(value))
                    self.assertEqual(leaves[key], value)
        self.assertEqual(la[DEVIATION_LEAF], Decimal("0.10"))
        self.assertEqual(la[WORKING_EXPOSURE_LEAF], Decimal("0.30"))
        self.assertNotEqual(a.sha256, b.sha256)
        # Deterministic.
        self.assertEqual(derive_strategy1_risk_config(fixed, self.valid(CONSERVATIVE_BYTES)).sha256, a.sha256)

    def test_derived_hash_is_installed_risk_config_sha256(self) -> None:
        fixed = fixed_strategy1_contract()
        profile = self.valid(TRIAL_01_BYTES)
        derived, binding = derive_and_bind_strategy1_profile(fixed, profile)
        expected = RiskLimitConfigV1(
            fixed.schema_version, fixed.conflict_domain, fixed.currency,
            dataclasses.replace(fixed.per_order, max_abs_reference_price_deviation_usd=Decimal("0.30")),
            dataclasses.replace(fixed.per_market, max_working_order_exposure_usd=Decimal("0.60")),
            fixed.conflict_domain_account, fixed.flow, fixed.state_integrity, fixed.venue_defense,
        )
        self.assertEqual(derived.sha256, expected.sha256)
        self.assertEqual(binding.derived_risk_config_sha256, derived.sha256)
        self.assertEqual(
            (binding.profile_id, binding.raw_profile_sha256, binding.parameter_set_sha256),
            ("trial_01", EXAMPLE_VECTORS["trial_01"][2], EXAMPLE_VECTORS["trial_01"][3]),
        )

    def test_equivalent_display_scale_yields_same_derived_hash(self) -> None:
        fixed = fixed_strategy1_contract()
        a = derive_strategy1_risk_config(fixed, self.valid(_bytes(_doc(parameters=_params("0.30", "0.60")))))
        b = derive_strategy1_risk_config(fixed, self.valid(_bytes(_doc(parameters=_params("0.3", "0.6")))))
        self.assertEqual(a.sha256, b.sha256)
        c = derive_strategy1_risk_config(fixed, self.valid(_bytes(_doc(parameters=_params("0.31", "0.60")))))
        self.assertNotEqual(a.sha256, c.sha256)

    def test_profile_18_profile_cannot_override_topology_flow_emergency_fields(self) -> None:
        for leaf in (
            "per_order.max_contracts", "per_market.max_authoritative_working_orders",
            "flow.create_max_sends", "flow.emergency_cancel_max_sends",
            "flow.emergency_retry_max_attempts_per_target_per_action",
            "state_integrity.max_reconciliation_lag_ms", "venue_defense.order_group_mode",
            "conflict_domain_account.max_unresolved_write_count", "conflict_domain", "currency",
            "schema_version",
        ):
            for parameters in ({**_params(), leaf: "2"}, {DEVIATION_LEAF: "0.30", leaf: "2"}):
                with self.subTest(leaf=leaf, parameters=parameters):
                    self.assertProfileFails(C.PROFILE_PARAMETER_KEYS_MISMATCH, _bytes(_doc(parameters=parameters)))
            with self.subTest(leaf=leaf, where="top-level"):
                # ``schema_version`` is itself a V1 key, so overriding it is a
                # constant mismatch; every other leaf is an unknown key.
                expected = C.PROFILE_CONSTANT_MISMATCH if leaf == "schema_version" else C.PROFILE_TOP_LEVEL_KEYS_MISMATCH
                self.assertProfileFails(expected, _bytes(_doc(**{leaf: "2"})))
        # Derivation itself substitutes nothing but the two leaves: the
        # carrier exposes only the two economic values.
        self.assertEqual(
            set(ValidatedTestParameterProfileV1.__slots__),
            {"profile_id", "max_abs_reference_price_deviation_usd", "max_working_order_exposure_usd",
             "raw_profile_sha256", "parameter_set_sha256"},
        )

    def test_profile_28_fixed_contract_invalid_or_nonconforming(self) -> None:
        profile = self.valid(CONSERVATIVE_BYTES)
        fixed = fixed_strategy1_contract()
        nonconforming = {
            "per_order.max_contracts": dataclasses.replace(fixed, per_order=dataclasses.replace(fixed.per_order, max_contracts=Decimal("2"))),
            "per_order.price_reasonability_required": dataclasses.replace(fixed, per_order=dataclasses.replace(fixed.per_order, price_reasonability_required=False)),
            "per_market.max_authoritative_working_orders": dataclasses.replace(fixed, per_market=dataclasses.replace(fixed.per_market, max_authoritative_working_orders=2)),
            "per_market.max_gross_exposure_usd": dataclasses.replace(fixed, per_market=dataclasses.replace(fixed.per_market, max_gross_exposure_usd=Decimal("2"))),
            "account.max_unresolved_write_count": dataclasses.replace(fixed, conflict_domain_account=dataclasses.replace(fixed.conflict_domain_account, max_unresolved_write_count=1)),
            "account.max_conservative_unresolved": dataclasses.replace(fixed, conflict_domain_account=dataclasses.replace(fixed.conflict_domain_account, max_conservative_unresolved_write_exposure_usd=Decimal("0.5"))),
            "flow.create_max_sends": dataclasses.replace(fixed, flow=dataclasses.replace(fixed.flow, create_max_sends=2)),
            "flow.modify_replace_max_sends": dataclasses.replace(fixed, flow=dataclasses.replace(fixed.flow, modify_replace_max_sends=1)),
            "flow.ordinary_cancel_max_sends": dataclasses.replace(fixed, flow=dataclasses.replace(fixed.flow, ordinary_cancel_max_sends=0)),
            "flow.automated_execution_max_sends": dataclasses.replace(fixed, flow=dataclasses.replace(fixed.flow, automated_execution_max_sends=2)),
            "flow.emergency_cancel_max_sends": dataclasses.replace(fixed, flow=dataclasses.replace(fixed.flow, emergency_cancel_max_sends=2)),
            "flow.emergency_cancel_max_in_flight": dataclasses.replace(fixed, flow=dataclasses.replace(fixed.flow, emergency_cancel_max_in_flight=2)),
            "flow.emergency_retry": dataclasses.replace(fixed, flow=dataclasses.replace(fixed.flow, emergency_retry_max_attempts_per_target_per_action=1)),
        }
        for label, contract in nonconforming.items():
            with self.subTest(label=label):
                with self.assertRaises(ProfileValidationError) as ctx:
                    derive_strategy1_risk_config(contract, profile)
                self.assertIs(ctx.exception.code, C.PROFILE_FIXED_CONTRACT_INVALID)
        # Missing / wrong-typed / not-a-RiskLimitConfigV1 inputs.
        broken_section = copy.copy(fixed)
        object.__setattr__(broken_section, "flow", None)
        wrong_type_leaf = copy.copy(fixed)
        object.__setattr__(wrong_type_leaf, "per_order", dataclasses.replace(fixed.per_order, max_contracts=1))
        mapping_form = json.loads(json.dumps(dataclasses.asdict(fixed), default=str))
        for label, contract in (("none", None), ("mapping", mapping_form), ("missing-section", broken_section), ("int-leaf", wrong_type_leaf)):
            with self.subTest(label=label):
                with self.assertRaises(ProfileValidationError) as ctx:
                    derive_strategy1_risk_config(contract, profile)  # type: ignore[arg-type]
                self.assertIs(ctx.exception.code, C.PROFILE_FIXED_CONTRACT_INVALID)

    def test_profile_29_third_leaf_difference_is_override_forbidden(self) -> None:
        fixed = fixed_strategy1_contract()
        profile = self.valid(CONSERVATIVE_BYTES)
        real = profile_module._substitute_profile_leaves
        tampers = {
            "flow.create_max_sends": lambda d: dataclasses.replace(d, flow=dataclasses.replace(d.flow, create_window_ms=d.flow.create_window_ms + 1)),
            "state_integrity": lambda d: dataclasses.replace(d, state_integrity=dataclasses.replace(d.state_integrity, max_reconciliation_lag_ms=2_000)),
            "conflict_domain": lambda d: dataclasses.replace(d, conflict_domain="other-domain"),
            "venue_defense": lambda d: dataclasses.replace(d, venue_defense=dataclasses.replace(d.venue_defense, cancel_order_on_pause_required=False)),
            "per_order.max_market_data_age_ms": lambda d: dataclasses.replace(d, per_order=dataclasses.replace(d.per_order, max_market_data_age_ms=999)),
            "decimal-scale-only": lambda d: dataclasses.replace(d, per_market=dataclasses.replace(d.per_market, max_gross_exposure_usd=Decimal("1.0"))),
            "profile-leaf-not-applied": lambda d: dataclasses.replace(d, per_order=dataclasses.replace(d.per_order, max_abs_reference_price_deviation_usd=Decimal("0.2"))),
            "not-a-config": lambda d: _leaves(d),
        }
        for label, tamper in tampers.items():
            with self.subTest(label=label):
                with mock.patch.object(profile_module, "_substitute_profile_leaves", side_effect=lambda f, p, t=tamper: t(real(f, p))):
                    with self.assertRaises(ProfileValidationError) as ctx:
                        derive_strategy1_risk_config(fixed, profile)
                self.assertIs(ctx.exception.code, C.PROFILE_OVERRIDE_FORBIDDEN)

    def test_derivation_rejects_non_carrier_profile(self) -> None:
        with self.assertRaises(ProfileValidationError) as ctx:
            derive_strategy1_risk_config(fixed_strategy1_contract(), {"per_order": "0.3"})  # type: ignore[arg-type]
        self.assertIs(ctx.exception.code, C.PROFILE_IDENTITY_MISMATCH)

    def test_fixed_contract_is_not_mutated_and_placeholder_leaves_are_irrelevant(self) -> None:
        profile = self.valid(WIDER_TEST_BYTES)
        f1 = fixed_strategy1_contract(deviation=Decimal("0"), exposure=Decimal("1.000000"))
        f2 = fixed_strategy1_contract(deviation=Decimal("0.7"), exposure=Decimal("0.2"))
        before = f1.sha256
        self.assertEqual(derive_strategy1_risk_config(f1, profile).sha256, derive_strategy1_risk_config(f2, profile).sha256)
        self.assertEqual(f1.sha256, before)


class BindingTests(_ProfileTestCase):
    def setUp(self) -> None:
        self.fixed = fixed_strategy1_contract()
        self.profile = self.valid(CONSERVATIVE_BYTES)
        self.derived, self.binding = derive_and_bind_strategy1_profile(self.fixed, self.profile)

    def test_exact_reconciliation_passes(self) -> None:
        bound = ProfileRiskBindingV1(
            "conservative", EXAMPLE_VECTORS["conservative"][2], EXAMPLE_VECTORS["conservative"][3],
            self.derived.sha256,
        )
        self.assertIs(reconcile_profile_risk_binding(self.binding, bound), self.binding)

    def test_profile_30_each_tuple_value_mismatch_fails_independently(self) -> None:
        other = "f" * 64
        for field in ("profile_id", "raw_profile_sha256", "parameter_set_sha256", "derived_risk_config_sha256"):
            with self.subTest(field=field):
                bound = dataclasses.replace(self.binding, **{field: "other" if field == "profile_id" else other})
                with self.assertRaises(ProfileValidationError) as ctx:
                    reconcile_profile_risk_binding(self.binding, bound)
                self.assertIs(ctx.exception.code, C.PROFILE_BINDING_MISMATCH)
        for bad in (None, dataclasses.astuple(self.binding), dataclasses.asdict(self.binding)):
            with self.subTest(bad=type(bad)):
                with self.assertRaises(ProfileValidationError) as ctx:
                    reconcile_profile_risk_binding(self.binding, bad)  # type: ignore[arg-type]
                self.assertIs(ctx.exception.code, C.PROFILE_BINDING_MISMATCH)

    def test_profile_20_path_mutation_after_binding_does_not_mutate_bound_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            path.write_bytes(CONSERVATIVE_BYTES)
            profile = select_and_validate_test_parameter_profile(profile_path=path)
            derived, binding = derive_and_bind_strategy1_profile(self.fixed, profile)
            retained = (profile, derived.sha256, binding)
            # Mutate the selected file: economic change + display-only change.
            path.write_bytes(WIDER_TEST_BYTES.replace(b"wider_test", b"conservative"))
            self.assertEqual((profile, derived.sha256, binding), retained)
            self.assertEqual(profile.max_abs_reference_price_deviation_usd, Decimal("0.10"))
            with mock.patch.object(profile_module, "_read_profile_bytes", side_effect=AssertionError("reread")):
                # Retained carrier reuse performs no reread / hot reload.
                self.assertIs(select_and_validate_test_parameter_profile(validated_profile=profile), profile)
                self.assertEqual(derive_and_bind_strategy1_profile(self.fixed, profile)[1], binding)
            # A subsequent fresh validation mismatches the bound tuple.
            revalidated = select_and_validate_test_parameter_profile(profile_path=path)
            _, observed = derive_and_bind_strategy1_profile(self.fixed, revalidated)
            with self.assertRaises(ProfileValidationError) as ctx:
                reconcile_profile_risk_binding(observed, binding)
            self.assertIs(ctx.exception.code, C.PROFILE_BINDING_MISMATCH)
            # Display-only mutation: parameter identity equal, raw identity not.
            path.write_bytes(CONSERVATIVE_BYTES.replace(b'"0.10"', b'"0.1"'))
            display = select_and_validate_test_parameter_profile(profile_path=path)
            _, observed = derive_and_bind_strategy1_profile(self.fixed, display)
            self.assertEqual(observed.parameter_set_sha256, binding.parameter_set_sha256)
            self.assertEqual(observed.derived_risk_config_sha256, binding.derived_risk_config_sha256)
            with self.assertRaises(ProfileValidationError) as ctx:
                reconcile_profile_risk_binding(observed, binding)
            self.assertIs(ctx.exception.code, C.PROFILE_BINDING_MISMATCH)

    def test_bind_rejects_non_carrier_inputs(self) -> None:
        for args in ((None, self.derived), (self.profile, None), (self.profile, _leaves(self.derived))):
            with self.subTest(args=args):
                with self.assertRaises(ProfileValidationError) as ctx:
                    bind_profile_risk(*args)  # type: ignore[arg-type]
                self.assertIs(ctx.exception.code, C.PROFILE_IDENTITY_MISMATCH)


class AuthorityTests(_ProfileTestCase):
    AUTHORITY_TOKENS = (
        "RISK_CONFIG_CONSUMPTION_AUTHORIZED", "RELEASE_ONLY_AUTHORIZED", "WRITER_PROOF_RELEASE_AUTHORIZED",
        "NORMAL_WRITER_AUTHORIZED", "GATE_D_AUTHORIZED", "VENUE_WRITE_AUTHORIZED", "PRODUCTION_AUTHORIZED",
    )

    def test_profile_31_valid_profile_without_runtime_authorization_is_validation_only(self) -> None:
        self.assertEqual(VALIDATION_RESULT, "VALID_SCENARIO_PARAMETERS")
        profile = self.valid(TRIAL_01_BYTES)
        derived, binding = derive_and_bind_strategy1_profile(fixed_strategy1_contract(), profile)
        for obj in (profile, binding):
            for attr in dir(obj):
                lowered = attr.lower()
                for word in ("authoriz", "permit", "release", "writer", "gate", "credential", "session"):
                    self.assertNotIn(word, lowered, (type(obj).__name__, attr))
        source = (REPO_ROOT / "src/arb/venues/kalshi/strategy1_test_parameter_profile.py").read_text("utf-8")
        for token in self.AUTHORITY_TOKENS:
            self.assertNotIn(token, source)
        for forbidden_import in ("ledger_binding", "order_lifecycle", "emergency_cancel", "socket", "http",
                                 "urllib", "requests", "ssl", "sqlite3", "subprocess", "datetime", "time"):
            self.assertNotIn(f"import {forbidden_import}", source)
            self.assertNotIn(f"from {forbidden_import}", source)
            self.assertNotIn(f"arb.venues.kalshi.{forbidden_import} import", source)
        self.assertNotIn("WriterEligibilityGate", source)

    def test_profile_32_repository_retained_profile_has_same_no_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            retained_dir = Path(tmp) / "profiles"
            retained_dir.mkdir()
            path = retained_dir / "trial_01.json"
            path.write_bytes(TRIAL_01_BYTES)
            retained = select_and_validate_test_parameter_profile(profile_path=path)
            external = validate_test_parameter_profile_bytes(TRIAL_01_BYTES)
        self.assertEqual(retained, external)
        self.assertEqual(json.loads(TRIAL_01_BYTES)["authority"], "NONE")
        self.assertEqual(json.loads(TRIAL_01_BYTES)["runtime_authorization"], "NONE")
        # Validation leaves no global selection / mutable module state behind.
        module_state = {
            name: value for name, value in vars(profile_module).items()
            if not name.startswith("__") and isinstance(value, (list, dict, set))
        }
        self.assertEqual(module_state, {})
        self.assertNotIn(retained, vars(profile_module).values())


class ProtectedPathTests(unittest.TestCase):
    PROTECTED_BLOBS = {
        "src/arb/execution_ledger.py": "608f4cd281525a8bf53fafa2b19eb23cc5b669ac",
        "src/arb/venues/kalshi/risk_control.py": "111685c8c1dc7735a53b45830d93844c329f23e3",
        "src/arb/venues/kalshi/minimal_market_maker.py": "be1bbfa31c7d814d48751f9b2399ef62c866d36e",
        "src/arb/venues/kalshi/order_lifecycle.py": "2ea2c40437626de7218dc318432db94e9bc9d4f5",
        "tests/test_kalshi_one_order_lifecycle.py": "850ed38cdb8fe526e9c947a003d8a1d5a433e3e5",
    }

    def test_profile_22_protected_lifecycle_and_dependencies_unmodified(self) -> None:
        """The protected one-order lifecycle source/test (run unchanged as a
        separate regression) and the reused protected dependencies keep
        their exact required-base Git blob identities."""
        for rel, blob in self.PROTECTED_BLOBS.items():
            with self.subTest(path=rel):
                self.assertEqual(_git_blob((REPO_ROOT / rel).read_bytes()), blob)


if __name__ == "__main__":
    unittest.main()
