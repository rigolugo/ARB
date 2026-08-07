"""Offline unit tests for the capability-envelope contract: JSON parsing,
direct object construction, canonical serialization, identity, and
requested-capability authorization (Candidate 02 Sections 16 and 20;
Implementation 02 Correction 2: complete capability-envelope validation
enforced identically for both the JSON-parsing route and the direct
public-object-construction route; Implementation 03: canonical,
ASCII-only `issue_date` validation; Implementation 04: exact built-in
`str` type required for `issue_date`, rejecting every `str` subclass
before any regex, slicing, or content interpretation; Implementation 05:
the complete envelope invariant is enforced at construction AND
re-enforced at every public consumption boundary -- `validate()`,
`canonical_capability_envelope_bytes()`, and
`capability_envelope_identity()` -- behind an exact runtime type gate)."""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import dataclass

from arb.venues.kalshi import (
    AuthorizationValue as AV,
    HaltCode,
    NonSecretConfigurationInput as Input,
    RequestedCapability as RC,
    TaskAuthorizationCapabilityEnvelope as Envelope,
    validate,
)
from arb.venues.kalshi.errors import (
    CapabilityEnvelopeError,
    CapabilityEnvelopeTypeError,
    DuplicateCapabilityKeyError,
    InvalidCapabilityValueError,
    MissingCapabilityFieldError,
    NonFiniteCapabilityValueError,
    UnknownCapabilityFieldError,
)
from arb.venues.kalshi.serialization import (
    canonical_capability_envelope_bytes,
    capability_envelope_identity,
    parse_capability_envelope_json,
)

_DEMO_REST = "https://external-api.demo.kalshi.co/trade-api/v2"
_DEMO_WS = "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"

_VALID_OBJ = {
    "schema_version": 1,
    "authorization_id": "AUTH1",
    "authorizing_authority": "Gustavo",
    "task_id": "T1",
    "issue_date": "2026-08-06",
    "completion_rule": "single-attempt",
    "network_access": "PROHIBITED",
    "demo_public_reads": "PERMITTED",
    "demo_authenticated_reads": "PROHIBITED",
    "demo_writes": "PROHIBITED",
    "production_public_reads": "PROHIBITED",
    "production_authenticated_reads": "PROHIBITED",
    "production_writes": "PROHIBITED",
    "credential_use": "PROHIBITED",
    "account_funding": "PROHIBITED",
    "code_changes": "PERMITTED",
    "tests": "PERMITTED",
    "artifact_generation": "PERMITTED",
    "repository_commits": "PERMITTED",
}

_CAPABILITY_FIELDS = [
    "network_access",
    "demo_public_reads",
    "demo_authenticated_reads",
    "demo_writes",
    "production_public_reads",
    "production_authenticated_reads",
    "production_writes",
    "credential_use",
    "account_funding",
    "code_changes",
    "tests",
    "artifact_generation",
    "repository_commits",
]

_METADATA_FIELDS = [
    "authorization_id",
    "authorizing_authority",
    "task_id",
    "completion_rule",
]

# Implementation 03: adversarial issue_date forms that a naive `\d` +
# `match()`/`$` pattern would incorrectly accept.
_TRAILING_NEWLINE_DATE = "2026-08-06\n"
_FULLWIDTH_DIGIT_DATE = "２０２６-０８-０６"
_ARABIC_INDIC_DIGIT_DATE = "٢٠٢٦-٠٨-٠٦"
_REJECTED_ADVERSARIAL_DATES = (
    _TRAILING_NEWLINE_DATE,
    _FULLWIDTH_DIGIT_DATE,
    _ARABIC_INDIC_DIGIT_DATE,
)


# Implementation 04: str subclasses used to prove the exact-built-in-str
# type gate rejects every subclass before any content interpretation.
class _PlainStrSubclass(str):
    """An ordinary str subclass with no overrides. Its content alone
    would otherwise look like a perfectly valid date."""


class _RaisingSliceStrSubclass(str):
    """A str subclass whose __getitem__ raises AssertionError if ever
    invoked. If the exact-type gate is implemented correctly (checked
    before any slicing), this exception must never fire — only
    InvalidCapabilityValueError should be raised."""

    def __getitem__(self, item):  # noqa: D401 - test double
        raise AssertionError(
            "__getitem__ must never be called for a rejected str subclass"
        )


class _LyingEqStrSubclass(str):
    """A str subclass overriding __eq__/__hash__ to always claim
    equality. Proves that no instance-level method override can spoof
    `type(value) is str`."""

    def __eq__(self, other):  # noqa: D401 - test double
        return True

    def __hash__(self):
        return 0


def _valid_direct_kwargs() -> dict:
    """A valid set of direct-construction kwargs mirroring _VALID_OBJ, but
    using real AuthorizationValue members instead of raw JSON strings."""

    kwargs = dict(_VALID_OBJ)
    for name in _CAPABILITY_FIELDS:
        kwargs[name] = AV(kwargs[name])
    return kwargs


def _envelope(**overrides: AV) -> Envelope:
    fields = dict(
        schema_version=1,
        authorization_id="AUTH1",
        authorizing_authority="Gustavo",
        task_id="T1",
        issue_date="2026-08-06",
        completion_rule="single-attempt",
        network_access=AV.PROHIBITED,
        demo_public_reads=AV.PERMITTED,
        demo_authenticated_reads=AV.PROHIBITED,
        demo_writes=AV.PROHIBITED,
        production_public_reads=AV.PROHIBITED,
        production_authenticated_reads=AV.PROHIBITED,
        production_writes=AV.PROHIBITED,
        credential_use=AV.PROHIBITED,
        account_funding=AV.PROHIBITED,
        code_changes=AV.PERMITTED,
        tests=AV.PERMITTED,
        artifact_generation=AV.PERMITTED,
        repository_commits=AV.PERMITTED,
    )
    fields.update(overrides)
    return Envelope(**fields)


def _config(**overrides) -> Input:
    fields = dict(
        environment="KALSHI_DEMO",
        environment_source_field="ARB_KALSHI_ENVIRONMENT",
        rest_endpoint=_DEMO_REST,
        websocket_endpoint=_DEMO_WS,
        requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
        capability_envelope=_envelope(),
        config_schema_revision=1,
        endpoint_allowlist_revision="candidate-02",
    )
    fields.update(overrides)
    return Input(**fields)


class ParseCapabilityEnvelopeJsonTests(unittest.TestCase):
    def test_valid_envelope_parses(self) -> None:
        envelope = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        self.assertEqual(envelope.schema_version, 1)
        self.assertEqual(envelope.demo_public_reads, AV.PERMITTED)

    def test_all_thirteen_capability_fields_required_each_individually(self) -> None:
        self.assertEqual(len(_CAPABILITY_FIELDS), 13)
        for name in _CAPABILITY_FIELDS:
            obj = copy.deepcopy(_VALID_OBJ)
            del obj[name]
            with self.assertRaises(MissingCapabilityFieldError):
                parse_capability_envelope_json(json.dumps(obj))

    def test_unknown_field_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["unexpected_field"] = "PERMITTED"
        with self.assertRaises(UnknownCapabilityFieldError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_duplicate_json_key_rejected(self) -> None:
        text = json.dumps(_VALID_OBJ)
        duplicated = text[:-1] + ',"network_access":"PERMITTED"}'
        with self.assertRaises(DuplicateCapabilityKeyError):
            parse_capability_envelope_json(duplicated)

    def test_boolean_authorization_value_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["network_access"] = True
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_blank_authorization_value_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["network_access"] = ""
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_null_authorization_value_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["network_access"] = None
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_unknown_authorization_token_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["network_access"] = "SOMETIMES"
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_integer_authorization_value_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["network_access"] = 1
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_float_value_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["schema_version"] = 1.0
        with self.assertRaises(NonFiniteCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_nested_float_value_rejected(self) -> None:
        text = json.dumps(_VALID_OBJ)[:-1] + ',"nested":{"x":1.5}}'
        with self.assertRaises((NonFiniteCapabilityValueError, UnknownCapabilityFieldError)):
            parse_capability_envelope_json(text)

    def test_nan_rejected(self) -> None:
        text = json.dumps(_VALID_OBJ)[:-1] + ',"schema_version":NaN}'
        with self.assertRaises((NonFiniteCapabilityValueError, DuplicateCapabilityKeyError)):
            parse_capability_envelope_json(text)

    def test_infinity_rejected(self) -> None:
        text = json.dumps(_VALID_OBJ)[:-1] + ',"extra_probe":Infinity}'
        with self.assertRaises((NonFiniteCapabilityValueError, UnknownCapabilityFieldError)):
            parse_capability_envelope_json(text)

    def test_wrong_schema_version_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["schema_version"] = 2
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_boolean_schema_version_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["schema_version"] = True
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_blank_each_metadata_field_rejected(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                obj = copy.deepcopy(_VALID_OBJ)
                obj[name] = ""
                with self.assertRaises(InvalidCapabilityValueError):
                    parse_capability_envelope_json(json.dumps(obj))

    def test_whitespace_only_metadata_field_rejected(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                obj = copy.deepcopy(_VALID_OBJ)
                obj[name] = "   "
                with self.assertRaises(InvalidCapabilityValueError):
                    parse_capability_envelope_json(json.dumps(obj))

    def test_non_string_metadata_field_rejected(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                obj = copy.deepcopy(_VALID_OBJ)
                obj[name] = 12345
                with self.assertRaises(InvalidCapabilityValueError):
                    parse_capability_envelope_json(json.dumps(obj))

    def test_malformed_issue_date_rejected_via_json(self) -> None:
        for bad in ("2026-8-6", "2026/08/06", "", "   "):
            with self.subTest(issue_date=bad):
                obj = copy.deepcopy(_VALID_OBJ)
                obj["issue_date"] = bad
                with self.assertRaises(InvalidCapabilityValueError):
                    parse_capability_envelope_json(json.dumps(obj))

    def test_impossible_calendar_date_rejected_via_json(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["issue_date"] = "2026-02-30"
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_non_string_issue_date_rejected(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["issue_date"] = 20260806
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_valid_ascii_issue_date_accepted_via_json(self) -> None:
        envelope = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        self.assertEqual(envelope.issue_date, "2026-08-06")

    def test_trailing_newline_issue_date_rejected_via_json(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["issue_date"] = _TRAILING_NEWLINE_DATE
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_fullwidth_digit_issue_date_rejected_via_json(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["issue_date"] = _FULLWIDTH_DIGIT_DATE
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_arabic_indic_digit_issue_date_rejected_via_json(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["issue_date"] = _ARABIC_INDIC_DIGIT_DATE
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(obj))

    def test_all_adversarial_issue_dates_rejected_via_json(self) -> None:
        for bad in _REJECTED_ADVERSARIAL_DATES:
            with self.subTest(issue_date=repr(bad)):
                obj = copy.deepcopy(_VALID_OBJ)
                obj["issue_date"] = bad
                with self.assertRaises(InvalidCapabilityValueError):
                    parse_capability_envelope_json(json.dumps(obj))

    def test_json_string_route_produces_ordinary_builtin_str(self) -> None:
        # json.loads always yields plain built-in str for JSON strings, so
        # the JSON route automatically satisfies the Implementation 04
        # exact-str-type requirement; this asserts that fact directly.
        envelope = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        self.assertIs(type(envelope.issue_date), str)


class DirectObjectConstructionBypassTests(unittest.TestCase):
    """Correction 2 (Implementation 02), the Implementation 03
    canonical-`issue_date` fix, and the Implementation 04 exact-built-in-
    `str` type gate: direct public-object construction must enforce the
    identical semantic contract as JSON parsing."""

    def test_valid_direct_construction_succeeds(self) -> None:
        envelope = Envelope(**_valid_direct_kwargs())
        self.assertEqual(envelope.schema_version, 1)

    def test_wrong_schema_version_direct_construction_rejected(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["schema_version"] = 2
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_boolean_schema_version_direct_construction_rejected(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["schema_version"] = True
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_blank_each_metadata_field_direct_construction_rejected(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                kwargs = _valid_direct_kwargs()
                kwargs[name] = ""
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    def test_whitespace_metadata_field_direct_construction_rejected(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                kwargs = _valid_direct_kwargs()
                kwargs[name] = "   "
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    def test_non_string_metadata_field_direct_construction_rejected(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                kwargs = _valid_direct_kwargs()
                kwargs[name] = 42
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    def test_malformed_issue_date_direct_construction_rejected(self) -> None:
        for bad in ("2026-8-6", "2026/08/06", "", "   "):
            with self.subTest(issue_date=bad):
                kwargs = _valid_direct_kwargs()
                kwargs["issue_date"] = bad
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    def test_impossible_calendar_date_direct_construction_rejected(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = "2026-02-30"
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_valid_ascii_issue_date_accepted_via_direct_construction(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = "2026-08-06"
        envelope = Envelope(**kwargs)
        self.assertEqual(envelope.issue_date, "2026-08-06")

    def test_trailing_newline_issue_date_rejected_direct_construction(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = _TRAILING_NEWLINE_DATE
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_fullwidth_digit_issue_date_rejected_direct_construction(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = _FULLWIDTH_DIGIT_DATE
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_arabic_indic_digit_issue_date_rejected_direct_construction(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = _ARABIC_INDIC_DIGIT_DATE
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_all_adversarial_issue_dates_rejected_direct_construction(self) -> None:
        for bad in _REJECTED_ADVERSARIAL_DATES:
            with self.subTest(issue_date=repr(bad)):
                kwargs = _valid_direct_kwargs()
                kwargs["issue_date"] = bad
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    def test_non_authorization_value_field_rejected_raw_string(self) -> None:
        for name in _CAPABILITY_FIELDS:
            with self.subTest(field=name):
                kwargs = _valid_direct_kwargs()
                kwargs[name] = "PERMITTED"  # raw str, not AuthorizationValue
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    def test_non_authorization_value_field_rejected_boolean(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["network_access"] = True
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_non_authorization_value_field_rejected_none(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["network_access"] = None
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_invalid_envelope_can_never_reach_validate_success(self) -> None:
        # An invalid envelope cannot even be constructed, so it cannot be
        # threaded into validate() to produce a ValidatedDemoProfile.
        kwargs = _valid_direct_kwargs()
        kwargs["schema_version"] = 99
        with self.assertRaises(InvalidCapabilityValueError):
            bad_envelope = Envelope(**kwargs)  # noqa: F841 — never assigned

    def test_json_and_direct_construction_agree_on_valid_input(self) -> None:
        from_json = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        from_direct = Envelope(**_valid_direct_kwargs())
        self.assertEqual(from_json, from_direct)

    def test_json_and_direct_construction_agree_on_bad_schema_version(self) -> None:
        json_obj = copy.deepcopy(_VALID_OBJ)
        json_obj["schema_version"] = 2
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(json_obj))
        kwargs = _valid_direct_kwargs()
        kwargs["schema_version"] = 2
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_json_and_direct_construction_agree_on_bad_issue_date(self) -> None:
        json_obj = copy.deepcopy(_VALID_OBJ)
        json_obj["issue_date"] = "2026-02-30"
        with self.assertRaises(InvalidCapabilityValueError):
            parse_capability_envelope_json(json.dumps(json_obj))
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = "2026-02-30"
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_json_and_direct_construction_agree_on_each_adversarial_issue_date(
        self,
    ) -> None:
        for bad in _REJECTED_ADVERSARIAL_DATES:
            with self.subTest(issue_date=repr(bad)):
                json_obj = copy.deepcopy(_VALID_OBJ)
                json_obj["issue_date"] = bad
                with self.assertRaises(InvalidCapabilityValueError):
                    parse_capability_envelope_json(json.dumps(json_obj))
                kwargs = _valid_direct_kwargs()
                kwargs["issue_date"] = bad
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    # -- Implementation 04: exact built-in str type gate ------------------

    def test_builtin_str_valid_date_accepted(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = "2026-08-06"
        envelope = Envelope(**kwargs)
        self.assertIs(type(envelope.issue_date), str)

    def test_ordinary_str_subclass_rejected_despite_valid_content(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = _PlainStrSubclass("2026-08-06")
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_malicious_slicing_str_subclass_rejected_before_getitem_runs(self) -> None:
        # The underlying content is a perfectly valid date, and __getitem__
        # would raise AssertionError if ever invoked. Only
        # InvalidCapabilityValueError may be observed here — anything else
        # (including AssertionError propagating out) means the type gate
        # did not short-circuit before content interpretation.
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = _RaisingSliceStrSubclass("2026-08-06")
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_lying_eq_str_subclass_rejected(self) -> None:
        # An overridden __eq__/__hash__ cannot spoof type(value) is str.
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = _LyingEqStrSubclass("2026-08-06")
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_str_subclass_with_invalid_underlying_content_also_rejected(self) -> None:
        # Belt-and-suspenders: even if somehow the type gate were bypassed,
        # this content is an impossible calendar date and must still fail.
        # Constructed here via the plain subclass (no method overrides).
        kwargs = _valid_direct_kwargs()
        kwargs["issue_date"] = _PlainStrSubclass("2026-02-30")
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)


class CanonicalSerializationTests(unittest.TestCase):
    def test_canonical_bytes_are_sorted_and_compact(self) -> None:
        envelope = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        canonical = canonical_capability_envelope_bytes(envelope)
        self.assertNotIn(b" ", canonical)
        decoded = json.loads(canonical.decode("utf-8"))
        self.assertEqual(list(decoded.keys()), sorted(decoded.keys()))

    def test_identity_is_deterministic(self) -> None:
        envelope_a = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        envelope_b = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        self.assertEqual(
            capability_envelope_identity(envelope_a),
            capability_envelope_identity(envelope_b),
        )
        self.assertTrue(capability_envelope_identity(envelope_a).startswith("sha256:"))

    def test_key_order_does_not_change_identity(self) -> None:
        reordered = dict(reversed(list(_VALID_OBJ.items())))
        envelope_a = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        envelope_b = parse_capability_envelope_json(json.dumps(reordered))
        self.assertEqual(
            capability_envelope_identity(envelope_a),
            capability_envelope_identity(envelope_b),
        )

    def test_insignificant_whitespace_does_not_change_identity(self) -> None:
        spaced = json.dumps(_VALID_OBJ, indent=4)
        envelope_a = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        envelope_b = parse_capability_envelope_json(spaced)
        self.assertEqual(
            capability_envelope_identity(envelope_a),
            capability_envelope_identity(envelope_b),
        )

    def test_changed_semantic_field_changes_identity(self) -> None:
        obj = copy.deepcopy(_VALID_OBJ)
        obj["demo_public_reads"] = "PROHIBITED"
        envelope_a = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        envelope_b = parse_capability_envelope_json(json.dumps(obj))
        self.assertNotEqual(
            capability_envelope_identity(envelope_a),
            capability_envelope_identity(envelope_b),
        )

    def test_canonical_serialization_roundtrips_through_json_parser(self) -> None:
        # Canonical serialization must never emit a date that the JSON
        # parser would subsequently reject.
        envelope = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        canonical = canonical_capability_envelope_bytes(envelope)
        reparsed = parse_capability_envelope_json(canonical.decode("utf-8"))
        self.assertEqual(envelope, reparsed)


class RequestedCapabilityAuthorizationTests(unittest.TestCase):
    def test_public_read_authorized_when_envelope_permits(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
                capability_envelope=_envelope(
                    demo_public_reads=AV.PERMITTED, credential_use=AV.PROHIBITED
                ),
            )
        )
        self.assertIsNotNone(result.success)

    def test_public_read_not_authorized_when_envelope_prohibits(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.DEMO_PUBLIC_REST_READ.value,
                capability_envelope=_envelope(demo_public_reads=AV.PROHIBITED),
            )
        )
        self.assertEqual(result.halt.code, HaltCode.CAPABILITY_NOT_AUTHORIZED)

    def test_authenticated_read_not_authorized_when_envelope_prohibits(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.DEMO_AUTHENTICATED_READ.value,
                capability_envelope=_envelope(
                    demo_authenticated_reads=AV.PROHIBITED, credential_use=AV.PERMITTED
                ),
            )
        )
        self.assertEqual(result.halt.code, HaltCode.CAPABILITY_NOT_AUTHORIZED)

    def test_demo_write_always_prohibited(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.DEMO_WRITE.value,
                capability_envelope=_envelope(
                    demo_writes=AV.PERMITTED, credential_use=AV.PERMITTED
                ),
            )
        )
        self.assertEqual(result.halt.code, HaltCode.WRITE_CAPABILITY_PROHIBITED)

    def test_production_public_read_always_prohibited(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.PRODUCTION_PUBLIC_REST_READ.value,
                capability_envelope=_envelope(production_public_reads=AV.PERMITTED),
            )
        )
        self.assertEqual(result.halt.code, HaltCode.PRODUCTION_ACCESS_PROHIBITED)

    def test_production_authenticated_read_always_prohibited(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.PRODUCTION_AUTHENTICATED_READ.value,
                capability_envelope=_envelope(
                    production_authenticated_reads=AV.PERMITTED,
                    credential_use=AV.PERMITTED,
                ),
            )
        )
        self.assertEqual(result.halt.code, HaltCode.PRODUCTION_ACCESS_PROHIBITED)

    def test_production_write_always_prohibited(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.PRODUCTION_WRITE.value,
                capability_envelope=_envelope(
                    production_writes=AV.PERMITTED, credential_use=AV.PERMITTED
                ),
            )
        )
        self.assertEqual(result.halt.code, HaltCode.PRODUCTION_ACCESS_PROHIBITED)

    def test_missing_capability_field_halts(self) -> None:
        result = validate(_config(capability_envelope=None))
        self.assertEqual(result.halt.code, HaltCode.CAPABILITY_FIELD_MISSING)

    def test_unrecognized_requested_capability_token_halts(self) -> None:
        result = validate(_config(requested_capability="DEMO_SUPER_READ"))
        self.assertEqual(result.halt.code, HaltCode.CAPABILITY_FIELD_MISSING)

    def test_capability_failure_never_returns_partial_profile(self) -> None:
        result = validate(
            _config(
                requested_capability=RC.DEMO_WRITE.value,
                capability_envelope=_envelope(demo_writes=AV.PERMITTED),
            )
        )
        self.assertIsNone(result.success)


class _DuckTypedEnvelope:
    """A plain object carrying every attribute name a real envelope has.
    It is not a `TaskAuthorizationCapabilityEnvelope`, so the exact-type
    gate must reject it regardless of attribute content."""

    def __init__(self, **attributes) -> None:
        for name, value in attributes.items():
            setattr(self, name, value)


class _ThirteenFieldsOnlyEnvelope:
    """Carries all thirteen authorization attributes but no schema_version
    and no metadata fields at all."""

    def __init__(self) -> None:
        for name in _CAPABILITY_FIELDS:
            setattr(self, name, AV.PROHIBITED)


@dataclass(frozen=True, slots=True)
class _PostInitSuppressingEnvelope(Envelope):
    """A subclass that overrides `__post_init__` to a no-op, so
    construction-time validation is skipped entirely. Consumption
    boundaries must reject it on exact runtime type, before its (possibly
    invalid) field values are ever consulted."""

    def __post_init__(self) -> None:  # noqa: D401 - test double
        return None


class _SchemaVersionIntSubclass(int):
    """An `int` subclass. Compares equal to 1 but is not exactly `int`."""


class _BlankSpoofingStr(str):
    """A `str` subclass whose `strip()` lies, claiming non-blank content
    while the underlying value is whitespace only. The exact-type gate
    must reject it before `strip()` is ever called."""

    def strip(self, *args, **kwargs):  # noqa: D401 - test double
        return "definitely-not-blank"


def _valid_envelope() -> Envelope:
    return Envelope(**_valid_direct_kwargs())


def _mutated(envelope: Envelope, name: str, value) -> Envelope:
    """Bypass the frozen-dataclass guard the way an attacker or a bug
    would, producing an envelope whose current state violates the
    invariant even though construction succeeded."""

    object.__setattr__(envelope, name, value)
    return envelope


class CapabilityEnvelopeTrustBoundaryTests(unittest.TestCase):
    """Implementation 05: the complete envelope invariant is re-enforced
    at every public consumption boundary behind an exact runtime type
    gate. Prior successful `__post_init__` execution is never accepted as
    evidence of current validity."""

    # -- helpers ---------------------------------------------------------

    def _assert_validate_rejects(self, envelope) -> None:
        result = validate(_config(capability_envelope=envelope))
        self.assertIsNone(result.success)
        self.assertEqual(result.halt.code, HaltCode.CAPABILITY_FIELD_MISSING)

    def _assert_serialization_rejects(self, envelope, expected_exc) -> None:
        with self.assertRaises(expected_exc):
            canonical_capability_envelope_bytes(envelope)

    def _assert_identity_rejects(self, envelope, expected_exc) -> None:
        with self.assertRaises(expected_exc):
            capability_envelope_identity(envelope)

    # -- 1/2: duck-typed objects ----------------------------------------

    def test_duck_typed_thirteen_fields_only_cannot_validate(self) -> None:
        self._assert_validate_rejects(_ThirteenFieldsOnlyEnvelope())

    def test_duck_typed_thirteen_fields_only_cannot_serialize_or_identify(self) -> None:
        fake = _ThirteenFieldsOnlyEnvelope()
        self._assert_serialization_rejects(fake, CapabilityEnvelopeTypeError)
        self._assert_identity_rejects(fake, CapabilityEnvelopeTypeError)

    def test_duck_typed_complete_attribute_match_still_rejected(self) -> None:
        # Every attribute name AND value is correct; only the type differs.
        # Rejection must therefore be attributable to the type gate alone.
        fake = _DuckTypedEnvelope(**_valid_direct_kwargs())
        self._assert_validate_rejects(fake)
        self._assert_serialization_rejects(fake, CapabilityEnvelopeTypeError)
        self._assert_identity_rejects(fake, CapabilityEnvelopeTypeError)

    # -- 3/4/5: subclass suppressing __post_init__ -----------------------

    def test_post_init_suppressing_subclass_constructs_but_cannot_validate(self) -> None:
        # Construction succeeds precisely because __post_init__ is a no-op,
        # proving the subclass really did skip construction-time checks.
        sneaky = _PostInitSuppressingEnvelope(
            **{**_valid_direct_kwargs(), "schema_version": 999}
        )
        self.assertEqual(sneaky.schema_version, 999)
        self._assert_validate_rejects(sneaky)

    def test_post_init_suppressing_subclass_cannot_serialize(self) -> None:
        sneaky = _PostInitSuppressingEnvelope(
            **{**_valid_direct_kwargs(), "schema_version": 999}
        )
        self._assert_serialization_rejects(sneaky, CapabilityEnvelopeTypeError)

    def test_post_init_suppressing_subclass_cannot_produce_identity(self) -> None:
        sneaky = _PostInitSuppressingEnvelope(
            **{**_valid_direct_kwargs(), "schema_version": 999}
        )
        self._assert_identity_rejects(sneaky, CapabilityEnvelopeTypeError)

    def test_subclass_rejected_on_type_even_when_all_fields_valid(self) -> None:
        # Fields are entirely valid here, so the only possible cause of
        # rejection is the exact-runtime-type gate.
        sneaky = _PostInitSuppressingEnvelope(**_valid_direct_kwargs())
        self._assert_validate_rejects(sneaky)
        self._assert_serialization_rejects(sneaky, CapabilityEnvelopeTypeError)
        self._assert_identity_rejects(sneaky, CapabilityEnvelopeTypeError)

    # -- 6/7: schema_version exact int ----------------------------------

    def test_int_subclass_schema_version_not_one_fails_construction(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["schema_version"] = _SchemaVersionIntSubclass(2)
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_int_subclass_schema_version_equal_one_fails_construction(self) -> None:
        # Value compares equal to 1, so only the exact-type rule can reject it.
        kwargs = _valid_direct_kwargs()
        kwargs["schema_version"] = _SchemaVersionIntSubclass(1)
        self.assertEqual(kwargs["schema_version"], 1)
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_bool_schema_version_fails_construction(self) -> None:
        kwargs = _valid_direct_kwargs()
        kwargs["schema_version"] = True
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_int_subclass_schema_version_by_mutation_rejected_everywhere(self) -> None:
        envelope = _mutated(
            _valid_envelope(), "schema_version", _SchemaVersionIntSubclass(1)
        )
        self._assert_validate_rejects(envelope)
        self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)
        self._assert_identity_rejects(envelope, InvalidCapabilityValueError)

    # -- 8/9: exact-str metadata ----------------------------------------

    def test_str_subclass_spoofing_blank_authorization_id_fails_construction(self) -> None:
        spoof = _BlankSpoofingStr("   ")
        self.assertEqual(spoof.strip(), "definitely-not-blank")
        kwargs = _valid_direct_kwargs()
        kwargs["authorization_id"] = spoof
        with self.assertRaises(InvalidCapabilityValueError):
            Envelope(**kwargs)

    def test_str_subclass_spoofing_blank_rejected_for_each_metadata_field(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                kwargs = _valid_direct_kwargs()
                kwargs[name] = _BlankSpoofingStr("   ")
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    def test_plain_str_subclass_rejected_for_each_metadata_field(self) -> None:
        # Ordinary subclass with genuinely valid content: rejection is
        # therefore attributable to the exact-type rule, not the content.
        class _PlainMeta(str):
            pass

        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                kwargs = _valid_direct_kwargs()
                kwargs[name] = _PlainMeta("perfectly-fine-value")
                with self.assertRaises(InvalidCapabilityValueError):
                    Envelope(**kwargs)

    # -- 10/11: mutated schema_version ----------------------------------

    def test_mutated_invalid_schema_version_cannot_validate(self) -> None:
        self._assert_validate_rejects(_mutated(_valid_envelope(), "schema_version", 2))

    def test_mutated_invalid_schema_version_cannot_serialize_or_identify(self) -> None:
        envelope = _mutated(_valid_envelope(), "schema_version", 2)
        self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)
        self._assert_identity_rejects(envelope, InvalidCapabilityValueError)

    # -- 12/13: mutated metadata ----------------------------------------

    def test_mutated_blank_metadata_cannot_validate(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                self._assert_validate_rejects(_mutated(_valid_envelope(), name, "   "))

    def test_mutated_blank_metadata_cannot_serialize_or_identify(self) -> None:
        for name in _METADATA_FIELDS:
            with self.subTest(field=name):
                envelope = _mutated(_valid_envelope(), name, "")
                self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)
                self._assert_identity_rejects(envelope, InvalidCapabilityValueError)

    def test_mutated_invalid_issue_date_cannot_be_consumed(self) -> None:
        envelope = _mutated(_valid_envelope(), "issue_date", "2026-02-30")
        self._assert_validate_rejects(envelope)
        self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)
        self._assert_identity_rejects(envelope, InvalidCapabilityValueError)

    # -- 14/15: mutated authorization fields ----------------------------

    def test_mutated_raw_string_capability_field_cannot_validate(self) -> None:
        self._assert_validate_rejects(
            _mutated(_valid_envelope(), "network_access", "PROHIBITED")
        )

    def test_mutated_raw_string_capability_field_cannot_serialize_or_identify(self) -> None:
        envelope = _mutated(_valid_envelope(), "network_access", "PROHIBITED")
        self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)
        self._assert_identity_rejects(envelope, InvalidCapabilityValueError)

    def test_mutated_capability_field_rejected_for_each_of_thirteen(self) -> None:
        for name in _CAPABILITY_FIELDS:
            with self.subTest(field=name):
                envelope = _mutated(_valid_envelope(), name, "PERMITTED")
                self._assert_validate_rejects(envelope)
                self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)

    def test_mutated_unrelated_enum_capability_field_rejected(self) -> None:
        envelope = _mutated(_valid_envelope(), "network_access", RC.DEMO_WRITE)
        self._assert_validate_rejects(envelope)
        self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)

    def test_mutated_none_capability_field_rejected(self) -> None:
        envelope = _mutated(_valid_envelope(), "credential_use", None)
        self._assert_validate_rejects(envelope)
        self._assert_serialization_rejects(envelope, InvalidCapabilityValueError)

    # -- 16/17/18/19: valid paths still work, and agree ------------------

    def test_valid_direct_construction_still_accepted_at_all_boundaries(self) -> None:
        envelope = _valid_envelope()
        result = validate(_config(capability_envelope=envelope))
        self.assertIsNotNone(result.success)
        self.assertIsInstance(canonical_capability_envelope_bytes(envelope), bytes)
        self.assertTrue(capability_envelope_identity(envelope).startswith("sha256:"))

    def test_valid_json_parsing_still_accepted_at_all_boundaries(self) -> None:
        envelope = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        result = validate(_config(capability_envelope=envelope))
        self.assertIsNotNone(result.success)
        self.assertIsInstance(canonical_capability_envelope_bytes(envelope), bytes)
        self.assertTrue(capability_envelope_identity(envelope).startswith("sha256:"))

    def test_canonical_serialization_of_valid_envelope_reparses(self) -> None:
        envelope = _valid_envelope()
        canonical = canonical_capability_envelope_bytes(envelope)
        reparsed = parse_capability_envelope_json(canonical.decode("utf-8"))
        self.assertEqual(envelope, reparsed)
        self.assertEqual(
            capability_envelope_identity(envelope),
            capability_envelope_identity(reparsed),
        )

    def test_direct_and_json_routes_agree_across_all_boundaries(self) -> None:
        from_direct = _valid_envelope()
        from_json = parse_capability_envelope_json(json.dumps(_VALID_OBJ))
        self.assertEqual(from_direct, from_json)
        self.assertEqual(
            canonical_capability_envelope_bytes(from_direct),
            canonical_capability_envelope_bytes(from_json),
        )
        self.assertEqual(
            capability_envelope_identity(from_direct),
            capability_envelope_identity(from_json),
        )
        self.assertEqual(
            validate(_config(capability_envelope=from_direct)).success,
            validate(_config(capability_envelope=from_json)).success,
        )

    def test_shared_invariant_agrees_across_validate_and_serialization(self) -> None:
        # For every mutation, all three boundaries must agree on rejection;
        # none may diverge from the others.
        mutations = (
            ("schema_version", 2),
            ("authorization_id", "   "),
            ("issue_date", "2026-13-01"),
            ("network_access", "PERMITTED"),
        )
        for name, value in mutations:
            with self.subTest(field=name):
                envelope = _mutated(_valid_envelope(), name, value)
                self._assert_validate_rejects(envelope)
                self._assert_serialization_rejects(envelope, CapabilityEnvelopeError)
                self._assert_identity_rejects(envelope, CapabilityEnvelopeError)

    # -- failure-mode hygiene -------------------------------------------

    def test_invalid_envelope_halt_is_secret_safe_and_deterministic(self) -> None:
        envelope = _mutated(_valid_envelope(), "authorization_id", "   ")
        first = validate(_config(capability_envelope=envelope)).halt
        second = validate(_config(capability_envelope=envelope)).halt
        self.assertEqual(str(first), str(second))
        # Only fixed, non-secret classification metadata is rendered; no
        # raw exception text escapes into the halt.
        self.assertIn("capability_envelope", str(first))
        self.assertIn("missing_or_invalid", str(first))

    def test_serialization_failures_raise_capability_envelope_errors_only(self) -> None:
        envelope = _mutated(_valid_envelope(), "schema_version", 2)
        with self.assertRaises(CapabilityEnvelopeError):
            canonical_capability_envelope_bytes(envelope)
        with self.assertRaises(CapabilityEnvelopeError):
            capability_envelope_identity(envelope)


if __name__ == "__main__":
    unittest.main()
